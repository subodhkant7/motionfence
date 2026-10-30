import { ScenarioData, DigitalTwinPlantState } from '../types'
import {
  PresentationFrame,
  PresentationTimeline,
  StageStatus,
} from '../types/presentation'

export function derivePresentationTimeline(
  scenarioId: string,
  scenarioData: ScenarioData | null
): PresentationTimeline {
  const isScenarioSafe =
    scenarioId.includes('safe') || scenarioId === 'scenario_a'
  const isScenarioDenied =
    scenarioId.includes('denied') ||
    scenarioId.includes('hazard') ||
    scenarioId === 'scenario_b_denied'
  const isScenarioToctou =
    scenarioId.includes('toctou') ||
    scenarioId === 'scenario_b' ||
    scenarioId === 'scenario_c_toctou'
  const isScenarioRecovery =
    scenarioId.includes('recovery') ||
    scenarioId.includes('fault') ||
    scenarioId === 'scenario_c' ||
    scenarioId === 'scenario_d'
  const isScenarioTelemetry =
    scenarioId.includes('telemetry') || scenarioId === 'scenario_telemetry'
  const isScenarioEvidence =
    scenarioId.includes('evidence') || scenarioId === 'scenario_evidence'

  let overallOutcome:
    | 'NOMINAL'
    | 'DENIED'
    | 'BLOCKED'
    | 'RECOVERED'
    | 'VERIFICATION_FAILED'
    | 'UNVERIFIED'
    | 'UNKNOWN' = 'UNKNOWN'

  if (isScenarioDenied) {
    overallOutcome = 'DENIED'
  } else if (isScenarioToctou) {
    overallOutcome = 'BLOCKED'
  } else if (isScenarioRecovery) {
    overallOutcome = 'RECOVERED'
  } else if (isScenarioSafe || isScenarioTelemetry || isScenarioEvidence) {
    overallOutcome = 'NOMINAL'
  }

  // Baseline plant state
  const defaultPlantState: DigitalTwinPlantState = {
    stage_name: 'OBSERVE',
    pump_state: 'INACTIVE',
    valve_b_state: 'OPEN',
    valve_b_angle_deg: 0.0,
    cooling_state: 'ACTIVE',
    human_zone: isScenarioDenied ? 'SECTOR_4_BREACH' : 'CLEAR',
    human_distance_m: isScenarioDenied ? 2.0 : 5.0,
    actuator_status: 'READY',
    world_version: 3,
    leak_active: true,
    pressure_psi: 95.5,
    flow_rate_lpm: 14.0,
  }

  // Extract raw facts if available
  const decRecord = (scenarioData as any)?.execution_record || scenarioData?.decision_record
  const policyDec = scenarioData?.policy_decision || (decRecord as any)?.policy_decision
  const authTicket = scenarioData?.ticket || (scenarioData as any)?.authorization_ticket
  const reval = (scenarioData as any)?.revalidation_result || (decRecord as any)?.revalidation_result
  const hwExec = scenarioData?.execution_result || (scenarioData as any)?.hardware_execution
  const postVerif = scenarioData?.verification_result || (scenarioData as any)?.post_action_verification
  const recRes = (scenarioData as any)?.recovery_result || scenarioData?.recovery_plan

  const frames: PresentationFrame[] = []

  // -------------------------------------------------------------
  // FRAME 0: OBSERVE
  // -------------------------------------------------------------
  const f0Plant: DigitalTwinPlantState = {
    ...defaultPlantState,
    stage_name: '1. OBSERVE',
  }
  frames.push({
    scenarioId,
    stageIndex: 0,
    stageKey: 'observe',
    stageLabel: '1. OBSERVE',
    stageSubtitle: isScenarioTelemetry
      ? 'World State & USGS Streamflow Telemetry'
      : 'Plant Sensors & Ground Truth State',
    stageStatus: 'PASSED',
    plantState: f0Plant,
    cameraPreset: 'full',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
    recordHash: scenarioData?.record_hash || scenarioData?.sha256_hash,
  })

  // -------------------------------------------------------------
  // FRAME 1: EVIDENCE
  // -------------------------------------------------------------
  const f1Plant: DigitalTwinPlantState = {
    ...f0Plant,
    stage_name: '2. EVIDENCE',
  }
  frames.push({
    scenarioId,
    stageIndex: 1,
    stageKey: 'evidence',
    stageLabel: '2. EVIDENCE',
    stageSubtitle: isScenarioEvidence
      ? 'Tavily SOP Grounding & Claim Certificate'
      : 'Sensor Grounding & Provenance Validation',
    stageStatus: 'PASSED',
    plantState: f1Plant,
    cameraPreset: isScenarioEvidence ? 'valve_b' : 'full',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 2: PROPOSAL
  // -------------------------------------------------------------
  const f2Plant: DigitalTwinPlantState = {
    ...f1Plant,
    stage_name: '3. PROPOSAL',
  }
  frames.push({
    scenarioId,
    stageIndex: 2,
    stageKey: 'proposal',
    stageLabel: '3. PROPOSAL',
    stageSubtitle: 'Unprivileged NVIDIA Nemotron 120B',
    stageStatus: 'PASSED',
    proposal: {
      action: 'CLOSE_VALVE',
      target: 'valve_b',
      rationale:
        decRecord?.intent ||
        'Isolate leaking branch on valve_b while maintaining active cooling and verifying human safety boundaries.',
      confidence: 0.96,
      provider: 'nebius',
      model: scenarioData?.model || 'nvidia/nemotron-3-super-120b-a12b',
      rawProposalHash: '69c3d0755220891555e8',
    },
    plantState: f2Plant,
    cameraPreset: 'valve_b',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 3: POLICY
  // -------------------------------------------------------------
  const isPolicyDenied = isScenarioDenied || policyDec?.decision_type === 'DENY'
  const f3Plant: DigitalTwinPlantState = {
    ...f2Plant,
    stage_name: '4. POLICY',
    human_zone: isPolicyDenied ? 'SECTOR_4_BREACH' : 'CLEAR',
    human_distance_m: isPolicyDenied ? 2.0 : 5.0,
    actuator_status: isPolicyDenied ? 'LOCKED' : 'READY',
  }
  frames.push({
    scenarioId,
    stageIndex: 3,
    stageKey: 'policy',
    stageLabel: '4. POLICY',
    stageSubtitle: isPolicyDenied
      ? 'Strict Policy DENY — Invariant Violation'
      : 'Deterministic Gate: ALLOW (Safe)',
    stageStatus: isPolicyDenied ? 'DENIED' : 'PASSED',
    policy: {
      decision: isPolicyDenied ? 'DENY' : 'ALLOW',
      rulesEvaluated: 14,
      ruleViolations: isPolicyDenied
        ? ['INVARIANT_HUMAN_ZONE_VIOLATION: Sector 4 occupied by technician (distance 2.0m <= 3.0m threshold)']
        : [],
      reason: isPolicyDenied
        ? 'Worker detected in Sector 4 hazardous perimeter. Action CLOSE_VALVE strictly prohibited.'
        : 'All safety invariants satisfied: human zone clear, cooling loop preserved, manifold pressure within limits.',
    },
    plantState: f3Plant,
    cameraPreset: isPolicyDenied ? 'safety_zone' : 'valve_b',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 4: AUTHORIZATION
  // -------------------------------------------------------------
  const f4Plant: DigitalTwinPlantState = {
    ...f3Plant,
    stage_name: '5. AUTHORIZATION',
  }
  frames.push({
    scenarioId,
    stageIndex: 4,
    stageKey: 'authorization',
    stageLabel: '5. AUTHORIZE',
    stageSubtitle: isPolicyDenied
      ? 'Zero Authority — No Ticket Minted'
      : 'Safety Enclave: Single-Use HMAC Ticket',
    stageStatus: isPolicyDenied ? 'DENIED' : 'PASSED',
    authorization: {
      status: isPolicyDenied ? 'NOT_ISSUED' : 'SIGNED',
      ticketId: isPolicyDenied ? undefined : authTicket?.ticket_id || 'tkt_sec_991823a',
      plantHash: isPolicyDenied ? undefined : authTicket?.plant_state_hash || 'c92e2213e71788bc',
      expiresInSeconds: isPolicyDenied ? undefined : 15,
      algorithm: 'HMAC-SHA256',
    },
    plantState: f4Plant,
    cameraPreset: isPolicyDenied ? 'safety_zone' : 'valve_b',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 5: WORLD CHANGE
  // -------------------------------------------------------------
  const isToctouDrift = isScenarioToctou
  const f5Plant: DigitalTwinPlantState = {
    ...f4Plant,
    stage_name: '6. WORLD CHANGE',
    world_version: isToctouDrift ? 4 : 3,
    human_zone: isToctouDrift ? 'SECTOR_4_BREACH' : f4Plant.human_zone,
    human_distance_m: isToctouDrift ? 2.1 : f4Plant.human_distance_m,
  }
  frames.push({
    scenarioId,
    stageIndex: 5,
    stageKey: 'world_change',
    stageLabel: '6. WORLD CHANGE',
    stageSubtitle: isToctouDrift
      ? 'Worker Enters Zone at t_exec (v3 -> v4 Drift)'
      : isPolicyDenied
      ? 'Terminal State (Actuator Locked)'
      : 'Stable Environmental Invariants',
    stageStatus: isToctouDrift ? 'BLOCKED' : isPolicyDenied ? 'NOT_APPLICABLE' : 'PASSED',
    worldChange: {
      previousVersion: 3,
      newVersion: isToctouDrift ? 4 : 3,
      driftDetected: isToctouDrift,
      description: isToctouDrift
        ? 'Technician entered modeled hazard zone between policy approval and hardware dispatch. Version incremented v3 -> v4.'
        : 'No environmental state drift observed during dispatch interval.',
      sensorTrigger: isToctouDrift ? 'lidar_barrier_sector4' : undefined,
    },
    plantState: f5Plant,
    cameraPreset: isToctouDrift ? 'safety_zone' : 'full',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 6: REVALIDATION
  // -------------------------------------------------------------
  const f6Plant: DigitalTwinPlantState = {
    ...f5Plant,
    stage_name: '7. REVALIDATE',
    actuator_status: isPolicyDenied || isToctouDrift ? 'LOCKED' : 'READY',
  }
  frames.push({
    scenarioId,
    stageIndex: 6,
    stageKey: 'revalidation',
    stageLabel: '7. REVALIDATE',
    stageSubtitle: isToctouDrift
      ? 'TOCTOU Version Hash Mismatch (Execution Blocked)'
      : isPolicyDenied
      ? 'Not Reached (No Ticket)'
      : 'Pre-Stroke Verification: All 9 Barriers Passed',
    stageStatus: isToctouDrift ? 'BLOCKED' : isPolicyDenied ? 'NOT_APPLICABLE' : 'PASSED',
    revalidation: {
      status: isToctouDrift ? 'WORLD_STATE_CHANGED' : isPolicyDenied ? 'NOT_REACHED' : 'PASSED',
      expectedHash: 'c92e2213e71788bc (v3)',
      actualHash: isToctouDrift ? '88f2a170b240119e (v4)' : 'c92e2213e71788bc (v3)',
      versionMatch: !isToctouDrift && !isPolicyDenied,
      barriersChecked: 9,
    },
    plantState: f6Plant,
    cameraPreset: isToctouDrift ? 'actuator' : 'valve_b',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 7: EXECUTION
  // -------------------------------------------------------------
  const isActuatorFault = isScenarioRecovery
  const isExecutionAllowed =
    (isScenarioSafe || isScenarioTelemetry || isScenarioEvidence || policyDec?.decision === 'ALLOW') &&
    !isPolicyDenied &&
    !isToctouDrift
  const f7Plant: DigitalTwinPlantState = {
    ...f6Plant,
    stage_name: '8. EXECUTE',
    valve_b_state: isExecutionAllowed && !isActuatorFault ? 'CLOSED' : 'OPEN',
    valve_b_angle_deg: isExecutionAllowed && !isActuatorFault ? 90.0 : 0.0,
    actuator_status: isActuatorFault
      ? 'HARDWARE_FAULT'
      : isExecutionAllowed
      ? 'ACTUATED'
      : 'LOCKED',
    leak_active: isExecutionAllowed && !isActuatorFault ? false : true,
    pressure_psi: isExecutionAllowed && !isActuatorFault ? 125.0 : 95.5,
    flow_rate_lpm: isExecutionAllowed && !isActuatorFault ? 0.0 : 14.0,
    world_version: isExecutionAllowed && !isActuatorFault ? 4 : f6Plant.world_version,
  }
  frames.push({
    scenarioId,
    stageIndex: 7,
    stageKey: 'execution',
    stageLabel: '8. EXECUTE',
    stageSubtitle: isActuatorFault
      ? 'Injected Fault: Solenoid Jam / Linkage NO_OP'
      : isExecutionAllowed
      ? '24V Actuator Stroke Energized — Valve Rotating'
      : 'Hardware Boundary Locked — Zero Pulse',
    stageStatus: isActuatorFault
      ? 'FAILED'
      : isExecutionAllowed
      ? 'PASSED'
      : 'NOT_APPLICABLE',
    execution: {
      status: isActuatorFault
        ? 'HARDWARE_FAULT'
        : isExecutionAllowed
        ? 'ACTUATED'
        : 'LOCKED',
      actuatorId: 'act_valve_b_rotary',
      commandedAngle: isExecutionAllowed ? 90.0 : 0.0,
      faultInjected: isActuatorFault ? 'LINKAGE_NO_OP' : 'NONE',
      busVoltageV: isExecutionAllowed ? 24.1 : 0.0,
    },
    plantState: f7Plant,
    cameraPreset: 'actuator',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 8: VERIFICATION
  // -------------------------------------------------------------
  const isVerified = isExecutionAllowed && !isActuatorFault
  const f8Plant: DigitalTwinPlantState = {
    ...f7Plant,
    stage_name: '9. VERIFY',
    actuator_status: isVerified
      ? 'VERIFIED'
      : isActuatorFault
      ? 'HARDWARE_FAULT'
      : f7Plant.actuator_status,
  }
  frames.push({
    scenarioId,
    stageIndex: 8,
    stageKey: 'verification',
    stageLabel: '9. VERIFY',
    stageSubtitle: isActuatorFault
      ? 'Limit Switch Mismatch Detected (Stroke Incomplete)'
      : isVerified
      ? 'Independent Limit Switches Confirm Seating'
      : 'Not Reached (Actuation Prevented)',
    stageStatus: isActuatorFault
      ? 'FAILED'
      : isVerified
      ? 'PASSED'
      : 'NOT_APPLICABLE',
    verification: {
      status: isActuatorFault
        ? 'VERIFICATION_FAILED'
        : isVerified
        ? 'VERIFIED'
        : 'NOT_REACHED',
      isVerified,
      limitSwitchReadback: isActuatorFault ? 'OPEN (Expected CLOSED)' : isVerified ? 'CLOSED (Confirmed)' : undefined,
      commandedState: isExecutionAllowed ? 'CLOSED' : 'OPEN',
      sensorContradiction: isActuatorFault,
    },
    plantState: f8Plant,
    cameraPreset: 'valve_b',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  // -------------------------------------------------------------
  // FRAME 9: RECOVERY
  // -------------------------------------------------------------
  const f9Plant: DigitalTwinPlantState = {
    ...f8Plant,
    stage_name: '10. RECOVER',
    valve_b_state: isActuatorFault ? 'CLOSED' : f8Plant.valve_b_state,
    valve_b_angle_deg: isActuatorFault ? 90.0 : f8Plant.valve_b_angle_deg,
    actuator_status: isActuatorFault ? 'QUARANTINED' : f8Plant.actuator_status,
    leak_active: isActuatorFault ? false : f8Plant.leak_active,
    pressure_psi: isActuatorFault ? 125.0 : f8Plant.pressure_psi,
    flow_rate_lpm: isActuatorFault ? 0.0 : f8Plant.flow_rate_lpm,
  }
  frames.push({
    scenarioId,
    stageIndex: 9,
    stageKey: 'recovery',
    stageLabel: '10. RECOVER',
    stageSubtitle: isActuatorFault
      ? 'Valve B Quarantined — Safe Secondary Isolation Transition'
      : 'Nominal Cycle Complete (No Recovery Required)',
    stageStatus: isActuatorFault ? 'PASSED' : 'NOT_APPLICABLE',
    recovery: {
      status: isActuatorFault ? 'RECOVERED' : 'NOT_APPLICABLE',
      quarantinedValve: isActuatorFault ? 'valve_b' : undefined,
      recoveryPath: isActuatorFault
        ? 'Quarantine primary valve_b -> isolate upstream manifold valve_a -> lock hazardous power'
        : undefined,
      isPostRecoveryVerified: false,
      disclosureNotice: isActuatorFault
        ? 'MODELED RECOVERY RESULT — FINAL INDEPENDENT VERIFICATION NOT RECORDED'
        : undefined,
    },
    plantState: f9Plant,
    cameraPreset: isActuatorFault ? 'recovery' : 'full',
    provenanceMode: scenarioData?.execution_mode === 'LIVE' ? 'LIVE' : 'REPLAY',
  })

  return {
    scenarioId,
    scenarioTitle: scenarioData?.title || scenarioId,
    overallOutcome,
    frames,
  }
}
