"""Mock physical hardware endpoint implementation.

SECURITY INVARIANTS:
1. NO VALID MOTIONFENCE AUTHORIZATION TICKET = NO ACTUATION.
2. Mock hardware endpoint sits downstream of MotionFence and has ZERO authority to:
   - Decide policy or evaluate safety rules.
   - Mint AuthorizationTickets.
   - Bypass execution-time revalidation.
   - Modify production policies or world state outside validated commands.
3. Consumed tickets are tracked to guarantee strict single-use semantics.
4. Hardware faults are deterministically injected to feed existing verification and recovery.
"""

from typing import Any, Dict, Optional, Set
import threading
import time
import uuid

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import WorldState, ValveState, CoolingState
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
    HardwareStatus,
)
from motionfence.hardware.interface import HardwareEndpoint
from motionfence.hardware.validation import HardwareTicketValidator


class MockHardwareEndpoint(HardwareEndpoint):
    """Deterministic software representation of an industrial physical actuator endpoint.

    Sits at the final physical boundary, receiving ActionProposals accompanied by
    cryptographically signed AuthorizationTickets. Delegates nominal physical state
    mutation to the underlying PhysicalActuator while enforcing hardware-boundary
    safety invariants and deterministic fault injection.
    """

    def __init__(
        self,
        world: PhysicalWorld,
        hardware_id: str = "HWR_ACTUATOR_VALVE_01",
        actuator_type: ActuatorType = ActuatorType.VALVE_ACTUATOR,
        secret_key: str = "motionfence_runtime_kernel_secret",
        event_bus: Optional[EventBus] = None,
        underlying_actuator: Optional[PhysicalActuator] = None,
    ) -> None:
        self._world = world
        self._hardware_id = hardware_id
        self._actuator_type = actuator_type
        self._validator = HardwareTicketValidator(secret_key=secret_key)
        self._event_bus = event_bus
        self._actuator = underlying_actuator or PhysicalActuator(world, secret_key=secret_key)

        # Operational state
        self._lock = threading.Lock()
        self._consumed_tickets: Set[str] = set()
        self._fault_mode: HardwareFaultType = HardwareFaultType.NONE
        self._is_locked: bool = False
        self._last_status: HardwareExecutionStatus = HardwareExecutionStatus.WAITING
        self._start_time: float = time.time()
        self._execution_history: list[HardwareExecutionRecord] = []

    @property
    def hardware_id(self) -> str:
        return self._hardware_id

    @property
    def actuator_type(self) -> ActuatorType:
        return self._actuator_type

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    @property
    def consumed_tickets(self) -> Set[str]:
        return set(self._consumed_tickets)

    def inject_fault(self, fault: HardwareFaultType) -> None:
        """Inject a deterministic hardware fault mode."""
        self._fault_mode = fault
        self._emit(
            EventType.HARDWARE_FAULT_INJECTED,
            f"Hardware endpoint '{self._hardware_id}' fault injected: {fault.value}.",
            payload={"hardware_id": self._hardware_id, "fault": fault.value},
        )

    def clear_fault(self) -> None:
        """Reset fault injection mode to nominal."""
        self._fault_mode = HardwareFaultType.NONE

    def unlock(self) -> None:
        """Reset locked state to WAITING (requires external operator / reset)."""
        self._is_locked = False
        self._last_status = HardwareExecutionStatus.WAITING

    def get_observed_state(self, target: Optional[str] = None) -> Dict[str, Any]:
        """Read sensory telemetry from the underlying physical plant."""
        current_state = self._world.get_state()
        observed: Dict[str, Any] = {
            "valves": {k: v.value for k, v in current_state.valves.items()},
            "cooling": current_state.cooling.value,
            "human_zone": current_state.human_zone.value,
            "pumps": dict(current_state.pumps),
            "leak_active": current_state.leak.active,
            "leak_flow_rate_lpm": current_state.leak.flow_rate_lpm,
            "world_version": current_state.version,
        }
        if target:
            observed["target"] = target
            observed["target_state"] = current_state.valves.get(target, ValveState.CLOSED).value
        return observed

    def get_status(self) -> HardwareStatus:
        """Return diagnostic health snapshot of the hardware endpoint."""
        current_state = self._world.get_state()
        return HardwareStatus(
            hardware_id=self._hardware_id,
            actuator_type=self._actuator_type,
            is_locked=self._is_locked,
            current_target="valve_b",
            last_status=self._last_status,
            consumed_ticket_count=len(self._consumed_tickets),
            active_fault=self._fault_mode,
            uptime_seconds=time.time() - self._start_time,
        )

    def receive_and_actuate(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
        *,
        correlation_id: Optional[str] = None,
    ) -> HardwareExecutionRecord:
        """Process incoming ticket and command physical actuation strictly if valid.

        Enforces:
        - Validation of ticket presence, signature, expiration, target, action, and single-use.
        - Immediate consumption to prevent replay.
        - Execution delegation to PhysicalActuator or deterministic fault simulation.
        - Emission of structured audit events.
        """
        start_ts = time.time()
        corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:10]}"
        ticket_id = ticket.ticket_id if ticket else None

        # 1. Event: Ticket Received
        self._emit(
            EventType.HARDWARE_TICKET_RECEIVED,
            f"Hardware '{self._hardware_id}' received request for {proposal.action_type.value} on {proposal.target}.",
            payload={
                "hardware_id": self._hardware_id,
                "proposal_id": proposal.id,
                "ticket_id": ticket_id,
                "action": proposal.action_type.value,
                "target": proposal.target,
                "correlation_id": corr_id,
            },
        )

        # 2. Hardware-boundary ticket validation & execution under atomicity lock
        with self._lock:
            current_world_version = self._world.version
            val_res = self._validator.validate(
                proposal=proposal,
                ticket=ticket,
                consumed_ticket_ids=self._consumed_tickets,
                current_world_version=current_world_version,
            )

            # 3. Handle validation rejection
            if not val_res.is_valid:
                self._is_locked = True
                self._last_status = val_res.status
                observed = self.get_observed_state(proposal.target)

                # Emit specific rejection events
                if val_res.status == HardwareExecutionStatus.REPLAYED_TICKET:
                    self._emit(
                        EventType.HARDWARE_REPLAY_REJECTED,
                        f"Hardware rejected replayed ticket '{ticket_id}'. Actuator LOCKED.",
                        payload={"ticket_id": ticket_id, "reasons": val_res.reasons, "correlation_id": corr_id},
                    )
                else:
                    self._emit(
                        EventType.HARDWARE_TICKET_REJECTED,
                        f"Hardware ticket validation failed ({val_res.status.value}): {'; '.join(val_res.reasons)}",
                        payload={"ticket_id": ticket_id, "status": val_res.status.value, "reasons": val_res.reasons, "correlation_id": corr_id},
                    )

                self._emit(
                    EventType.HARDWARE_ACTUATION_BLOCKED,
                    f"Hardware actuation strictly BLOCKED on '{proposal.target}'. Terminal state: LOCKED.",
                    payload={"status": val_res.status.value, "target": proposal.target, "correlation_id": corr_id},
                )

                record = HardwareExecutionRecord(
                    hardware_id=self._hardware_id,
                    actuator_type=self._actuator_type,
                    target=proposal.target,
                    requested_action=proposal.action_type.value,
                    ticket_id=ticket_id,
                    ticket_status=val_res.status.value,
                    signature_status="VALID" if val_res.signature_valid else "INVALID",
                    execution_status=val_res.status,
                    observed_state=observed,
                    correlation_id=corr_id,
                    timestamp=time.time(),
                    fault_injected=self._fault_mode,
                    message=f"Actuation rejected: {'; '.join(val_res.reasons)}",
                    execution_latency_ms=(time.time() - start_ts) * 1000.0,
                )
                self._execution_history.append(record)
                return record

            # 4. Validation passed: emit validated event and track consumed ticket
            assert ticket is not None
            self._consumed_tickets.add(ticket.ticket_id)

            self._emit(
                EventType.HARDWARE_TICKET_VALIDATED,
                f"Hardware ticket '{ticket.ticket_id}' validated successfully. Authorizing physical actuation.",
                payload={"ticket_id": ticket.ticket_id, "target": proposal.target, "correlation_id": corr_id},
            )

            self._emit(
                EventType.HARDWARE_ACTUATION_STARTED,
                f"Hardware energizing actuator for {proposal.action_type.value} on {proposal.target}...",
                payload={"hardware_id": self._hardware_id, "target": proposal.target, "action": proposal.action_type.value},
            )

            # 5. Execute actuation (or simulate deterministic hardware fault)
            active_fault = self._fault_mode
            exec_status = HardwareExecutionStatus.ACTUATED
            exec_message = f"Actuator {self._hardware_id} successfully actuated {proposal.target}."

            if active_fault == HardwareFaultType.NO_OP:
                # NO_OP: Hardware accepts command, but physical stroke completely fails
                # Physical state is NOT mutated
                exec_status = HardwareExecutionStatus.HARDWARE_FAULT
                exec_message = f"Hardware mechanical fault: Actuator energized, but mechanical linkage failed to move {proposal.target}."
            elif active_fault == HardwareFaultType.PARTIAL_ACTUATION:
                # PARTIAL_ACTUATION: Valve moves partially (e.g. leak rate is reduced by 50%, but not zeroed)
                if proposal.action_type == ActionType.CLOSE_VALVE:
                    # Valve remains partially OPEN
                    self._world.valves[proposal.target] = ValveState.OPEN
                    if proposal.target == self._world.leak_target:
                        self._world.leak.flow_rate_lpm = 7.1
                        self._world.leak.severity = 0.40
                    self._world.version += 1
                exec_status = HardwareExecutionStatus.HARDWARE_FAULT
                exec_message = f"Hardware mechanical fault: Valve {proposal.target} stroked partially (50%); seal unseated."
            elif active_fault == HardwareFaultType.WRONG_FINAL_STATE:
                # WRONG_FINAL_STATE: Inverts expected outcome
                if proposal.action_type == ActionType.CLOSE_VALVE:
                    self._world.valves[proposal.target] = ValveState.OPEN
                elif proposal.action_type == ActionType.OPEN_VALVE:
                    self._world.valves[proposal.target] = ValveState.CLOSED
                self._world.version += 1
                exec_status = HardwareExecutionStatus.HARDWARE_FAULT
                exec_message = f"Hardware mechanical fault: Actuator drove {proposal.target} into incorrect inverted position."
            elif active_fault == HardwareFaultType.DELAYED_ACTUATION:
                # DELAYED_ACTUATION: Nominal actuation but with simulated latency
                time.sleep(0.01)
                # Delegate nominal mutation to existing PhysicalActuator
                self._actuator.execute(proposal=proposal, ticket=ticket)
                exec_status = HardwareExecutionStatus.ACTUATED
                exec_message = f"Actuator {self._hardware_id} completed delayed stroke on {proposal.target}."
            else:
                # NOMINAL: Delegate directly to existing PhysicalActuator
                # PhysicalActuator preserves its own jammed_valve checks and world transitions
                res = self._actuator.execute(proposal=proposal, ticket=ticket)
                if not res.success:
                    exec_status = HardwareExecutionStatus.HARDWARE_FAULT
                    exec_message = f"Physical actuator failure: {res.message}"
                else:
                    exec_status = HardwareExecutionStatus.ACTUATED
                    exec_message = res.message

            ticket.consumed = True
            self._last_status = exec_status

            # 6. Read sensory telemetry after actuation
            observed = self.get_observed_state(proposal.target)

            self._emit(
                EventType.HARDWARE_OBSERVATION_RECORDED,
                f"Hardware observed telemetry after actuation on {proposal.target}: valve={observed.get('target_state', 'UNKNOWN')}.",
                payload=observed,
            )

            if exec_status == HardwareExecutionStatus.ACTUATED:
                self._emit(
                    EventType.HARDWARE_ACTUATION_COMPLETED,
                    exec_message,
                    payload={"hardware_id": self._hardware_id, "target": proposal.target, "status": exec_status.value},
                )
            else:
                self._emit(
                    EventType.HARDWARE_ACTUATION_BLOCKED,
                    exec_message,
                    payload={"hardware_id": self._hardware_id, "target": proposal.target, "status": exec_status.value},
                )

            record = HardwareExecutionRecord(
                hardware_id=self._hardware_id,
                actuator_type=self._actuator_type,
                target=proposal.target,
                requested_action=proposal.action_type.value,
                ticket_id=ticket.ticket_id,
                ticket_status="VALID",
                signature_status="VALID",
                execution_status=exec_status,
                observed_state=observed,
                correlation_id=corr_id,
                timestamp=time.time(),
                fault_injected=active_fault,
                message=exec_message,
                execution_latency_ms=(time.time() - start_ts) * 1000.0,
            )
            self._execution_history.append(record)
            return record

    def _emit(self, event_type: EventType, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Helper to emit events to EventBus if connected."""
        if self._event_bus:
            self._event_bus.emit(event_type, message, payload=payload or {})
