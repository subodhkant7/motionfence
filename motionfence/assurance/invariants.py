"""Specification and registry of machine-checkable safety invariant properties."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from motionfence.assurance.models import FindingSeverity, AssuranceScope


@dataclass
class AssuranceProperty:
    """Definition of a machine-checkable safety property."""
    property_id: str
    name: str
    description: str
    severity: FindingSeverity
    scope: AssuranceScope
    check_fn: Optional[Callable] = None


class AssurancePropertyRegistry:
    """Extensible registry of bounded assurance and safety properties."""

    def __init__(self) -> None:
        self._properties: Dict[str, AssuranceProperty] = {}
        self._register_default_properties()

    def register(self, prop: AssuranceProperty) -> None:
        """Register a new property into the assurance suite."""
        self._properties[prop.property_id] = prop

    def get(self, property_id: str) -> Optional[AssuranceProperty]:
        """Retrieve a registered property by ID."""
        return self._properties.get(property_id)

    def list_all(self) -> List[AssuranceProperty]:
        """List all currently registered properties in deterministic order."""
        return sorted(self._properties.values(), key=lambda p: p.property_id)

    def _register_default_properties(self) -> None:
        """Register the core MotionFence Phase 2E bounded safety properties."""
        # Property 1: Human-zone prohibition
        self.register(
            AssuranceProperty(
                property_id="PROP_001_HUMAN_ZONE_PROHIBITION",
                name="Human-Zone Actuation Prohibition",
                description="If human_zone == OCCUPIED, valve actuation commands cannot be authorized (ALLOW is prohibited).",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 2: Cooling preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_002_COOLING_PRESERVATION",
                name="Cooling System Preservation",
                description="An ALLOW authorization decision cannot occur if the cooling system is INACTIVE or DEGRADED.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 3: Unauthorized mutation impossible
        self.register(
            AssuranceProperty(
                property_id="PROP_003_UNAUTHORIZED_MUTATION_IMPOSSIBLE",
                name="Actuator Authority Isolation",
                description="PhysicalWorld state cannot mutate unless executed with a valid, matching, unconsumed AuthorizationTicket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 4: Conflicted policy blocks authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_004_CONFLICTED_POLICY_BLOCKS_AUTHORIZATION",
                name="Conflicted Knowledge Policy Gating",
                description="If active knowledge constraints contain an unresolved mutual conflict, Policy cannot return ALLOW.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 5: Stale safety constraint blocks unsafe authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_005_STALE_SAFETY_CONSTRAINT_BLOCKS_AUTHORIZATION",
                name="Stale Safety Knowledge Gating",
                description="Stale safety-relevant knowledge constraints cannot silently authorize physical action without recertification.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 6: Contradictory evidence gating
        self.register(
            AssuranceProperty(
                property_id="PROP_006_CONTRADICTORY_EVIDENCE_GATING",
                name="Sensor Contradiction Gating",
                description="High-severity sensor contradictions across physical modalities must block ALLOW verdicts.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 7: Bounded temporal cooling preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_007_TEMPORAL_COOLING_PRESERVATION",
                name="Temporal Cooling Preservation Across Horizon",
                description="Cooling system must remain ACTIVE throughout all sequential valve transitions across bounded horizon H.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.TEMPORAL_SAFETY,
            )
        )

        # Phase 2F Properties: TOCTOU Defense & State-Bound Authorization

        # Property 8: No execution after safety-state drift
        self.register(
            AssuranceProperty(
                property_id="PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT",
                name="No Execution After Safety-State Drift",
                description="If safety-relevant world state changes after authorization, the original ticket cannot authorize execution.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 9: Policy version binding
        self.register(
            AssuranceProperty(
                property_id="PROP_009_POLICY_VERSION_BINDING",
                name="Policy Version Binding",
                description="A ticket bound to policy version X cannot execute under incompatible policy version Y.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 10: Constraint-set binding
        self.register(
            AssuranceProperty(
                property_id="PROP_010_CONSTRAINT_SET_BINDING",
                name="Constraint Set Binding",
                description="A ticket bound to constraint set H1 cannot execute under H2.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 11: Execution-time validity
        self.register(
            AssuranceProperty(
                property_id="PROP_011_EXECUTION_TIME_VALIDITY",
                name="Execution-Time Validity",
                description="Execution requires a currently valid authorization context — all bindings must match.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2G Properties: Active Evidence Acquisition & Capability Boundaries

        # Property 12: Information actions cannot mutate consequential state
        self.register(
            AssuranceProperty(
                property_id="PROP_012_INFO_ACTION_NO_CONSEQUENTIAL_MUTATION",
                name="Information Actions Cannot Mutate Consequential State",
                description="Bounded information-gathering actions mutate only perception/sensor state and cannot mutate valves, pumps, or cooling.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 13: Information planner cannot authorize consequential actions
        self.register(
            AssuranceProperty(
                property_id="PROP_013_PLANNER_CANNOT_AUTHORIZE_CONSEQUENTIAL",
                name="Information Planner Cannot Authorize Consequential Actions",
                description="EvidenceAcquisitionPlanner possesses zero actuator authority and cannot mint AuthorizationTickets or bypass Safety Enclave.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 14: Evidence budget is finite
        self.register(
            AssuranceProperty(
                property_id="PROP_014_EVIDENCE_BUDGET_FINITE",
                name="Evidence Budget Finite Bound",
                description="Active evidence acquisition loop terminates deterministically within a strictly bounded iteration budget.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 15: Evidence acquisition cannot bypass policy
        self.register(
            AssuranceProperty(
                property_id="PROP_015_EVIDENCE_CANNOT_BYPASS_POLICY",
                name="Evidence Acquisition Cannot Bypass Policy",
                description="Gathering additional evidence does not bypass policy rules; physical actuation still strictly requires ALLOW.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 16: Additional evidence does not imply authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_016_NEW_EVIDENCE_DOES_NOT_IMPLY_ALLOW",
                name="Additional Evidence Does Not Imply Authorization",
                description="Acquiring new sensor evidence does not inherently guarantee or force an ALLOW verdict when safety invariants are compromised.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 17: Planner cannot escalate action class
        self.register(
            AssuranceProperty(
                property_id="PROP_017_PLANNER_CANNOT_ESCALATE_ACTION_CLASS",
                name="Planner Cannot Escalate Action Class",
                description="EvidenceAcquisitionPlanner is strictly confined to INFORMATION_ACTIONS and cannot propose consequential actions.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2H Properties: Adversarial Physical Environment & Robustness Bounds

        # Property 18: Unsafe human-zone transition safety
        self.register(
            AssuranceProperty(
                property_id="PROP_018_HUMAN_ZONE_TRANSITION_SAFETY",
                name="Unsafe Human-Zone Transition Safety",
                description="A modeled unsafe human-zone transition (CLEAR -> OCCUPIED) cannot produce an executable consequential action.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 19: Sensor contradiction no ungrounded allow
        self.register(
            AssuranceProperty(
                property_id="PROP_019_SENSOR_CONTRADICTION_NO_UNGROUNDED_ALLOW",
                name="Sensor Contradiction No Ungrounded Allow",
                description="A safety-relevant sensor contradiction cannot improve authorization without admissible new evidence.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 20: Actuator fault verification
        self.register(
            AssuranceProperty(
                property_id="PROP_020_ACTUATOR_FAULT_VERIFICATION",
                name="Actuator Fault Verification Invariant",
                description="An actuator fault (jam, partial move, no-op) cannot produce VERIFIED unless all physical postconditions hold.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 21: Safety degradation monotonicity
        self.register(
            AssuranceProperty(
                property_id="PROP_021_SAFETY_DEGRADATION_MONOTONICITY",
                name="Safety Degradation Monotonicity",
                description="A safety degradation cannot convert a previous DENY into ALLOW without a new valid authorization cycle.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 22: Adversarial environment zero authority
        self.register(
            AssuranceProperty(
                property_id="PROP_022_ADVERSARIAL_ENV_ZERO_AUTHORITY",
                name="Adversarial Environment Zero Authority",
                description="An adversarial physical environment cannot directly mint, alter, or bypass authorization tickets.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 23: Stale ticket environmental drift
        self.register(
            AssuranceProperty(
                property_id="PROP_023_STALE_TICKET_ENVIRONMENTAL_DRIFT",
                name="Stale Ticket Environmental Drift",
                description="A stale state-bound ticket cannot execute after modeled environmental drift has invalidated its context.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2I Properties: Fault Containment, Quarantine & Autonomous Recovery

        # Property 24: Failed actions invalidate authority
        self.register(
            AssuranceProperty(
                property_id="PROP_024_FAILED_ACTIONS_INVALIDATE_AUTHORITY",
                name="Failed Actions Invalidate Authority",
                description="A verified action failure unconditionally invalidates the associated ticket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 25: Quarantined components cannot execute blocked capabilities
        self.register(
            AssuranceProperty(
                property_id="PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE",
                name="Quarantined Components Cannot Execute Blocked Capabilities",
                description="Quarantined components are strictly prevented from executing blocked consequential capabilities.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 26: Recovery cannot reuse stale consequential authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_026_RECOVERY_CANNOT_REUSE_STALE_AUTHORIZATION",
                name="Recovery Cannot Reuse Stale Authorization",
                description="Autonomous recovery cannot silently reuse previous consequential authorization tickets.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 27: Recovery requires deterministic policy reevaluation
        self.register(
            AssuranceProperty(
                property_id="PROP_027_RECOVERY_REQUIRES_POLICY_REEVALUATION",
                name="Recovery Requires Policy Reevaluation",
                description="Every consequential recovery action requires a fresh deterministic policy reevaluation and authorization cycle.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 28: Sensor quarantine removes unsafe evidence from authorization context
        self.register(
            AssuranceProperty(
                property_id="PROP_028_SENSOR_QUARANTINE_REMOVES_UNSAFE_EVIDENCE",
                name="Sensor Quarantine Removes Unsafe Evidence",
                description="Telemetry and claims from quarantined sensors are strictly excluded from authorization-relevant context.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 29: Recovery budget is finite
        self.register(
            AssuranceProperty(
                property_id="PROP_029_RECOVERY_BUDGET_IS_FINITE",
                name="Recovery Budget Is Finite",
                description="Recovery attempts are strictly bounded by a finite budget to prevent infinite recovery cycles.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 30: Recovery cannot escalate capability class
        self.register(
            AssuranceProperty(
                property_id="PROP_030_RECOVERY_CANNOT_ESCALATE_CAPABILITY",
                name="Recovery Cannot Escalate Capability Class",
                description="Autonomous recovery planning cannot escalate informational actions into consequential physical actions.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2J Properties: Policy Mutation Firewall & Safety Regression Detection

        # Property 31: Human-zone guard removal detection
        self.register(
            AssuranceProperty(
                property_id="PROP_031_MUTATION_HUMAN_ZONE_GUARD_REMOVAL_DETECTED",
                name="Human-Zone Guard Mutation Detection",
                description="A policy mutation that removes a hard human-safety constraint must be detected as a regression.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 32: Confidence weakening detection
        self.register(
            AssuranceProperty(
                property_id="PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE",
                name="Target Confidence Weakening Assurance Detection",
                description="A policy mutation that weakens target-confidence requirements must not evade assurance detection.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 33: Contradiction removal detection
        self.register(
            AssuranceProperty(
                property_id="PROP_033_MUTATION_CONTRADICTION_REMOVAL_DETECTED",
                name="Contradiction Blocking Removal Detection",
                description="A policy mutation that removes contradiction blocking must be detected.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 34: State-bound authorization preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION",
                name="State-Bound Authorization Invariant Preservation",
                description="A policy mutation cannot silently disable state-bound authorization.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 35: Execution revalidation preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_035_MUTATION_CANNOT_DISABLE_EXECUTION_REVALIDATION",
                name="Execution Revalidation Invariant Preservation",
                description="A policy mutation cannot silently disable execution-time revalidation.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 36: Recovery containment preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_036_MUTATION_CANNOT_DISABLE_RECOVERY_CONTAINMENT",
                name="Recovery Containment Invariant Preservation",
                description="A policy mutation cannot silently disable recovery containment.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2K Properties: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs

        # Property 37: Compound safety mutation detection
        self.register(
            AssuranceProperty(
                property_id="PROP_037_COMPOUND_SAFETY_MUTATION_DETECTED",
                name="Compound Safety Mutation Detection",
                description="Compound policy mutations combining multiple weakened controls must be detected as regressions.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 38: Amplifying mutation interaction detection
        self.register(
            AssuranceProperty(
                property_id="PROP_038_AMPLIFYING_MUTATION_INTERACTION_DETECTED",
                name="Amplifying Mutation Interaction Detection",
                description="When mutations combine to produce unsafe ALLOWs that neither produced alone, the amplifying interaction must be classified and detected.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 39: Dynamic trajectory regression remains blockable
        self.register(
            AssuranceProperty(
                property_id="PROP_039_TRAJECTORY_REGRESSION_REMAINS_BLOCKABLE",
                name="Dynamic Trajectory Regression Blockability",
                description="Physical environment regressions discovered during dynamic trajectory exploration must remain interceptable by TOCTOU revalidation.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 40: Repair proposal cannot modify production policy
        self.register(
            AssuranceProperty(
                property_id="PROP_040_REPAIR_PROPOSAL_CANNOT_MODIFY_PRODUCTION_POLICY",
                name="Repair Proposal Authority Isolation",
                description="A policy repair proposal cannot directly mutate the live production policy or production baseline.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 41: Repair must pass existing safety firewall
        self.register(
            AssuranceProperty(
                property_id="PROP_041_REPAIR_MUST_PASS_EXISTING_SAFETY_FIREWALL",
                name="Repair Safety Firewall Gate",
                description="A candidate policy repair cannot be accepted unless it passes formal checks, adversarial probes, and dynamic trajectories.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 42: Repair cannot weaken authorization boundary
        self.register(
            AssuranceProperty(
                property_id="PROP_042_REPAIR_CANNOT_WEAKEN_AUTHORIZATION_BOUNDARY",
                name="Repair Authorization Boundary Monotonicity",
                description="A proposed repair cannot weaken the authorization boundary or permit actions prohibited under baseline policy.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 43: Trajectory counterexample is reproducible
        self.register(
            AssuranceProperty(
                property_id="PROP_043_TRAJECTORY_COUNTEREXAMPLE_IS_REPRODUCIBLE",
                name="Trajectory Counterexample Reproducibility",
                description="Dynamic trajectory regressions produce deterministic, reproducible counterexamples under identical seed.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 44: Inconclusive repair is not auto applied
        self.register(
            AssuranceProperty(
                property_id="PROP_044_INCONCLUSIVE_REPAIR_IS_NOT_AUTO_APPLIED",
                name="Inconclusive Repair Fail-Closed Gating",
                description="Repair proposals whose safety value cannot be derived deterministically must fail closed and cannot be automatically applied.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2M: Mock Hardware & Actuator Boundary Properties (45 - 51)
        # Property 45: Hardware cannot actuate without authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_045_HARDWARE_CANNOT_ACTUATE_WITHOUT_AUTHORIZATION",
                name="Hardware Zero Actuation Without Authorization",
                description="The physical hardware endpoint cannot actuate without a valid AuthorizationTicket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 46: Invalid ticket cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_046_INVALID_TICKET_CANNOT_ACTUATE",
                name="Hardware Rejection of Invalid Cryptographic Signature",
                description="The physical hardware endpoint cannot actuate when presented with an invalid cryptographic ticket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 47: Expired ticket cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_047_EXPIRED_TICKET_CANNOT_ACTUATE",
                name="Hardware Rejection of Expired Authorization",
                description="The physical hardware endpoint cannot actuate when presented with an expired AuthorizationTicket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 48: Replayed ticket cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_048_REPLAYED_TICKET_CANNOT_ACTUATE",
                name="Hardware Anti-Replay Consumption Defense",
                description="The physical hardware endpoint cannot actuate when presented with an already consumed AuthorizationTicket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 49: Target mismatch cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_049_TARGET_MISMATCH_CANNOT_ACTUATE",
                name="Hardware Target Binding Defense",
                description="The physical hardware endpoint cannot actuate when the ticket target does not match the requested target.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 50: Action mismatch cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_050_ACTION_MISMATCH_CANNOT_ACTUATE",
                name="Hardware Action Binding Defense",
                description="The physical hardware endpoint cannot actuate when the ticket action does not match the requested action.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 51: Stale authorization cannot actuate
        self.register(
            AssuranceProperty(
                property_id="PROP_051_STALE_AUTHORIZATION_CANNOT_ACTUATE",
                name="Hardware State-Bound Drift Defense",
                description="The physical hardware endpoint cannot actuate when the authorization context reflects a stale world state version.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Phase 2O: Real-World Public Telemetry & Provenance Invariants (52 - 56)
        # Property 52: External telemetry has no actuation authority
        self.register(
            AssuranceProperty(
                property_id="PROP_052_EXTERNAL_TELEMETRY_HAS_NO_ACTUATION_AUTHORITY",
                name="External Telemetry Actuation Isolation",
                description="External physical observations possess zero direct actuation authority; actuation requires state-bound ticket authorization.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 53: Missing external observation cannot create authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_053_MISSING_EXTERNAL_OBSERVATION_CANNOT_CREATE_AUTHORIZATION",
                name="Telemetry Failure Fail-Closed Gating",
                description="A missing, unparseable, or transport-failed external observation cannot trigger authorization; missing telemetry fails closed.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 54: Stale external evidence cannot be presented as fresh
        self.register(
            AssuranceProperty(
                property_id="PROP_054_STALE_EXTERNAL_EVIDENCE_CANNOT_BE_PRESENTED_AS_FRESH",
                name="Telemetry Temporal Freshness Integrity",
                description="An external observation whose age exceeds the freshness threshold cannot be classified or presented as fresh.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 55: Replayed external observation cannot claim live status
        self.register(
            AssuranceProperty(
                property_id="PROP_055_REPLAYED_EXTERNAL_OBSERVATION_CANNOT_CLAIM_LIVE_STATUS",
                name="Telemetry Replay vs Live Operational Separation",
                description="An external observation originating from offline cache or fixture replay cannot claim live acquisition status.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 56: Telemetry source provenance remains bound to observation
        self.register(
            AssuranceProperty(
                property_id="PROP_056_TELEMETRY_SOURCE_PROVENANCE_REMAINS_BOUND_TO_OBSERVATION",
                name="Telemetry Cryptographic Provenance Binding",
                description="External telemetry observations cannot be admitted into policy context without preserving source origin lineage and cryptographic hash.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )





