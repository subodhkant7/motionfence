import { ExecutionMode, ScenarioData } from '../types'
import {
  PresentationFrame,
  PresentationOutcome,
  PresentationPlantState,
  PresentationTimeline,
  StageStatus,
} from '../types/presentation'

type RecordValue = Record<string, unknown>
const obj = (v: unknown): RecordValue =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
    ? (v as RecordValue)
    : {}
const str = (v: unknown): string | undefined =>
  typeof v === 'string' && v.length > 0 ? v : undefined
const num = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const own = (v: RecordValue, k: string) =>
  Object.prototype.hasOwnProperty.call(v, k)
const text = (v: unknown) => str(v) ?? 'NOT_RECORDED'
// An explicit null in the authoritative envelope must never resurrect an older nested result.
const field = (v: RecordValue, k: string, fallback: unknown) =>
  own(v, k) ? v[k] : fallback
const keys = [
  'observe',
  'evidence',
  'proposal',
  'policy',
  'authorization',
  'world_change',
  'revalidation',
  'execution',
  'verification',
  'recovery',
] as const
const labels = [
  'OBSERVE',
  'EVIDENCE',
  'PROPOSAL',
  'POLICY',
  'AUTHORIZE',
  'WORLD CHANGE',
  'REVALIDATE',
  'EXECUTE',
  'VERIFY',
  'RECOVER',
]

// Custom postconditions use dotted own-property paths in the recorded world.
// Missing paths are distinct from an explicitly recorded null. Arrays/objects may
// be compared as JSON leaves; array indexing and prototype traversal are unsupported.
function resolveWorldPath(
  world: unknown,
  path: string
): { found: boolean; value?: unknown } {
  const parts = path.split('.')
  if (parts.some((part) => !part)) return { found: false }
  let value = world
  for (const part of parts) {
    if (
      value === null ||
      typeof value !== 'object' ||
      Array.isArray(value) ||
      !own(value as RecordValue, part)
    )
      return { found: false }
    value = (value as RecordValue)[part]
  }
  return { found: true, value }
}

function sameEvidenceValue(a: unknown, b: unknown): boolean {
  if (a === null || b === null) return a === null && b === null
  if (typeof a === 'number' || typeof b === 'number')
    return num(a) !== undefined && num(b) !== undefined && a === b
  if (typeof a === 'string' || typeof a === 'boolean') return a === b
  if (Array.isArray(a))
    return (
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((value, i) => sameEvidenceValue(value, b[i]))
    )
  if (typeof a !== 'object' || typeof b !== 'object' || Array.isArray(b))
    return false
  return (
    Object.keys(obj(a)).length === Object.keys(obj(b)).length &&
    Object.entries(obj(a)).every(
      ([key, value]) =>
        own(obj(b), key) && sameEvidenceValue(value, obj(b)[key])
    )
  )
}

function matchesFinalWorld(value: unknown, world: unknown): boolean {
  return Object.entries(obj(obj(value).expected_postconditions)).every(
    ([path, expected]) => {
      const resolved = resolveWorldPath(world, path)
      return resolved.found && sameEvidenceValue(resolved.value, expected)
    }
  )
}

export function verificationPassed(
  value: unknown,
  actionValue: unknown,
  world: unknown,
  preWorld: unknown
): boolean {
  const v = obj(value),
    action = obj(actionValue),
    expected = obj(v.expected_postconditions),
    observed = obj(v.observed_postconditions)
  const target = str(action.target),
    actionId = str(action.id ?? action.proposal_id)
  if (
    !target ||
    !actionId ||
    !str(action.action_type) ||
    v.action_id !== actionId ||
    v.target !== target
  )
    return false
  const required: RecordValue = { cooling: 'ACTIVE' }
  if (
    action.action_type === 'CLOSE_VALVE' ||
    action.action_type === 'OPEN_VALVE'
  ) {
    required[`valves.${target}`] =
      action.action_type === 'CLOSE_VALVE' ? 'CLOSED' : 'OPEN'
    if (
      action.action_type === 'CLOSE_VALVE' &&
      (obj(obj(preWorld).leak).target === target ||
        obj(obj(world).leak).target === target)
    )
      required['leak.active'] = false
  }
  return (
    v.status === 'VERIFIED' &&
    v.action_occurred === true &&
    v.is_verified !== false &&
    Array.isArray(v.discrepancies) &&
    v.discrepancies.length === 0 &&
    Object.entries(required).every(
      ([path, requiredValue]) =>
        own(expected, path) &&
        own(observed, path) &&
        sameEvidenceValue(expected[path], requiredValue) &&
        sameEvidenceValue(observed[path], requiredValue)
    ) &&
    Object.entries(expected).every(
      ([path, expectedValue]) =>
        own(observed, path) && sameEvidenceValue(observed[path], expectedValue)
    ) &&
    matchesFinalWorld(v, world)
  )
}
const verificationFailed = (value: unknown) => {
  const v = obj(value)
  return (
    ['FAILED', 'VERIFICATION_FAILED'].includes(text(v.status)) ||
    v.is_verified === false ||
    arr(v.discrepancies).length > 0 ||
    Object.entries(obj(v.expected_postconditions)).some(
      ([k, val]) =>
        own(obj(v.observed_postconditions), k) &&
        !sameEvidenceValue(obj(v.observed_postconditions)[k], val)
    )
  )
}

function worldPlant(value: unknown): PresentationPlantState {
  const w = obj(value),
    leak = obj(w.leak),
    readings = obj(obj(obj(w.observations).pressure_main).reading)
  return {
    stage_name: 'recorded world state',
    timestamp: num(w.timestamp),
    pump_state: text(obj(w.pumps).pump_p1),
    valve_b_state: text(obj(w.valves).valve_b),
    cooling_state: text(w.cooling),
    human_zone: text(w.human_zone),
    actuator_status: 'NOT_RECORDED',
    world_version: num(w.version ?? w.world_version),
    leak_active:
      typeof (leak.active ?? w.leak_active) === 'boolean'
        ? ((leak.active ?? w.leak_active) as boolean)
        : undefined,
    pressure_psi: num(readings.pressure_psi),
    flow_rate_lpm: num(leak.flow_rate_lpm ?? w.leak_flow_rate_lpm),
  }
}

/** No scenario identifiers participate in any evidence or outcome decision. */
export function derivePresentationTimeline(
  scenarioId: string,
  scenarioData: ScenarioData | null,
  currentMode?: ExecutionMode
): PresentationTimeline {
  const d = obj(scenarioData),
    r = obj(d.decision_record ?? d.execution_record)
  const pre = obj(d.pre_state ?? r.world_state_snapshot),
    post = obj(d.post_state)
  const provider = obj(r.provider_metadata)
  const mode =
    currentMode ??
    (['LIVE', 'REPLAY', 'OFFLINE_TEST'].includes(text(d.current_execution_mode))
      ? (d.current_execution_mode as ExecutionMode)
      : 'REPLAY')
  const p = obj(field(d, 'policy_decision', r.policy_decision))
  const policyRaw = field(d, 'policy_decision', r.policy_decision)
  const decisions = [
    str(policyRaw),
    str(p.decision),
    str(p.decision_type),
    typeof p.is_allowed === 'boolean'
      ? p.is_allowed
        ? 'ALLOW'
        : 'DENY'
      : undefined,
  ].filter(Boolean)
  const policy = decisions.includes('DENY')
    ? 'DENY'
    : decisions.includes('ALLOW')
      ? 'ALLOW'
      : 'UNKNOWN'
  const nestedPolicy = str(r.policy_decision)
  const policyConflict =
    (decisions.includes('DENY') && decisions.includes('ALLOW')) ||
    (!!nestedPolicy && policy !== 'UNKNOWN' && nestedPolicy !== policy) ||
    (policy === 'ALLOW' &&
      arr(p.reasons).some((reason) => obj(reason).status === 'failed'))
  const proposal = obj(field(d, 'proposal', r.action_proposal))
  const ticket = obj(
    field(d, 'ticket', d.authorization_ticket ?? d.initial_ticket)
  )
  const hw = obj(
    field(d, 'execution_result', d.hardware_execution ?? r.execution_result)
  )
  const v = field(
    d,
    'verification_result',
    d.post_action_verification ?? r.verification_result
  )
  const verification = obj(v)
  const recovery = obj(field(d, 'recovery_result', d.recovery_lifecycle))
  const retryExecution = obj(
    d.retry_execution ?? recovery.retry_execution_result
  )
  const freshTicket = obj(d.fresh_ticket ?? recovery.fresh_ticket)
  const recoveryExecutionRecorded =
    retryExecution.execution_status === 'ACTUATED' &&
    retryExecution.ticket_status === 'VALID' &&
    retryExecution.signature_status === 'VALID' &&
    !!str(freshTicket.signature) &&
    !!str(freshTicket.world_state_hash) &&
    !!str(freshTicket.ticket_id) &&
    freshTicket.ticket_id !== ticket.ticket_id &&
    retryExecution.ticket_id === freshTicket.ticket_id &&
    retryExecution.target === freshTicket.target &&
    retryExecution.requested_action === freshTicket.action_type
  const finalV = field(
    d,
    'retry_verification',
    recovery.retry_verification_result ?? recovery.final_verification_result
  )
  const primaryVerified = verificationPassed(v, proposal, post, pre)
  let finalVerified = verificationPassed(finalV, freshTicket, post, pre)
  if (
    !recoveryExecutionRecorded ||
    obj(finalV).action_id !== freshTicket.proposal_id ||
    obj(finalV).target !== freshTicket.target
  )
    finalVerified = false
  if (
    num(obj(finalV).timestamp) === undefined ||
    num(obj(v).timestamp) === undefined ||
    (obj(finalV).timestamp as number) <= (obj(v).timestamp as number)
  )
    finalVerified = false
  const retryTime = num(retryExecution.timestamp)
  const freshIssued = num(freshTicket.issued_at)
  const freshExpires = num(freshTicket.expires_at)
  const failedVerificationTime = num(verification.timestamp)
  if (
    retryTime === undefined ||
    freshIssued === undefined ||
    freshExpires === undefined ||
    failedVerificationTime === undefined ||
    freshIssued <= failedVerificationTime ||
    retryTime < freshIssued ||
    retryTime > freshExpires ||
    (num(obj(finalV).timestamp) ?? -Infinity) < retryTime
  )
    finalVerified = false
  const events = arr(d.events).map(obj)
  const event = (name: string) => events.find((e) => e.event_type === name)
  const reval = obj(d.revalidation_result)
  const revalStatus =
    str(reval.status ?? d.revalidation_status ?? r.revalidation_status) ??
    (event('HARDWARE_TICKET_VALIDATED') ? 'PASSED' : 'NOT_RECORDED')
  const blocked = !['PASSED', 'VALID', 'NOT_RECORDED'].includes(revalStatus)
  const hwStatus =
    str(hw.execution_status) ??
    (hw.success === true
      ? 'EXECUTED'
      : hw.success === false
        ? 'FAILED'
        : 'NOT_RECORDED')
  const executed = ['ACTUATED', 'EXECUTED', 'SUCCESS'].includes(hwStatus)
  const fault =
    hwStatus === 'HARDWARE_FAULT' ||
    (str(hw.fault_injected) !== undefined && hw.fault_injected !== 'NONE')
  const rejected = ['LOCKED', 'INVALID_TICKET', 'REJECTED', 'BLOCKED'].includes(
    hwStatus
  )
  const recoveryPresent = Object.keys(recovery).length > 0
  const recoverySuccess =
    ['SUCCESS', 'RECOVERED'].includes(
      text(recovery.outcome ?? recovery.status)
    ) && recovery.component_status !== 'QUARANTINED'
  const recoveryFailed = ['FAILED', 'FAILURE', 'ABORTED'].includes(
    text(recovery.outcome ?? recovery.status)
  )
  const hasTicket = !!str(ticket.ticket_id)
  const signedTicket =
    hasTicket && !!str(ticket.signature) && !!str(ticket.world_state_hash)
  const completeTicket =
    signedTicket &&
    !!str(ticket.proposal_id) &&
    !!str(ticket.target) &&
    !!str(ticket.action_type) &&
    num(ticket.world_state_version) !== undefined &&
    num(ticket.issued_at) !== undefined &&
    num(ticket.expires_at) !== undefined &&
    (ticket.expires_at as number) > (ticket.issued_at as number)
  const validAtExecution =
    hw.ticket_status === 'VALID' &&
    hw.signature_status === 'VALID' &&
    hw.ticket_id === ticket.ticket_id
  const mutation =
    Object.keys(obj(pre.valves)).some(
      (k) =>
        own(obj(post.valves), k) && obj(pre.valves)[k] !== obj(post.valves)[k]
    ) ||
    Object.keys(obj(pre.pumps)).some(
      (k) => own(obj(post.pumps), k) && obj(pre.pumps)[k] !== obj(post.pumps)[k]
    )
  const unauthorized = (policy === 'DENY' || blocked) && (executed || mutation)
  const reasons = arr(p.reasons).length ? arr(p.reasons) : arr(r.policy_reasons)
  const reasonText = (value: unknown) =>
    str(value) ??
    str(obj(value).details) ??
    str(obj(value).constraint) ??
    'NOT_RECORDED'
  const evidenceItems = arr(obj(r.snapshots).evidence)
  const evidenceRecorded =
    evidenceItems.length > 0 ||
    arr(r.sensor_evidence_ids).length > 0 ||
    !!obj(d.telemetry_observation).raw_record_hash
  const noActuation = !Object.keys(hw).length && !hasTicket
  const drift = obj(d.world_change_event ?? d.world_drift_event)
  const beforeVersion = num(drift.issuance_version ?? drift.version_at_issuance)
  const afterVersion = num(drift.drift_version ?? drift.version_at_revalidation)
  const driftRecorded =
    beforeVersion !== undefined &&
    afterVersion !== undefined &&
    beforeVersion !== afterVersion
  const issues: string[] = []
  if (
    executed &&
    str(r.authorization_ticket_id) &&
    r.authorization_ticket_id !== ticket.ticket_id
  )
    issues.push('Ticket ID contradicts the finalized decision record')
  if (
    own(d, 'execution_result') &&
    Object.keys(hw).length &&
    Object.keys(obj(r.execution_result)).length &&
    (hw.execution_status !== obj(r.execution_result).execution_status ||
      hw.ticket_id !== obj(r.execution_result).ticket_id)
  )
    issues.push('Conflicting hardware execution records')
  if (
    own(d, 'verification_result') &&
    Object.keys(verification).length &&
    Object.keys(obj(r.verification_result)).length &&
    verification.status !== obj(r.verification_result).status
  )
    issues.push('Conflicting verification records')
  if (policyConflict) issues.push('Contradictory policy fields')
  if (unauthorized)
    issues.push(
      'Recorded actuation or mutation contradicts denied/blocked authorization'
    )
  if (executed && !completeTicket)
    issues.push('Execution lacks a recorded signed authorization ticket')
  if (executed && !validAtExecution)
    issues.push(
      'Execution-time ticket validation is not recorded or inconsistent'
    )
  if (
    executed &&
    (verification.action_id !== proposal.id ||
      verification.target !== proposal.target) &&
    Object.keys(verification).length
  )
    issues.push(
      'Verification does not identify the recorded proposal and target'
    )
  if (
    executed &&
    (ticket.proposal_id !== proposal.id ||
      ticket.target !== proposal.target ||
      ticket.action_type !== proposal.action_type)
  )
    issues.push('Ticket does not identify the recorded proposal/action/target')
  if (executed && fault)
    issues.push('Execution success contradicts recorded actuator fault')
  const policyTimestamp =
    num(p.timestamp) ??
    num(
      event(
        policy === 'DENY'
          ? 'ENCLAVE_AUTHORIZATION_DENIED'
          : 'ENCLAVE_AUTHORIZATION_REQUESTED'
      )?.timestamp
    )
  const execTimestamp = num(hw.timestamp)
  const verifyTimestamp = num(verification.timestamp)
  if (
    num(ticket.expires_at) !== undefined &&
    execTimestamp !== undefined &&
    execTimestamp > (ticket.expires_at as number)
  )
    issues.push('Execution occurred after recorded ticket expiry')
  if (
    executed &&
    primaryVerified &&
    (execTimestamp === undefined || verifyTimestamp === undefined)
  )
    issues.push('Execution/verification chronology is not recorded')
  if (
    execTimestamp !== undefined &&
    verifyTimestamp !== undefined &&
    verifyTimestamp < execTimestamp
  )
    issues.push('Verification predates execution')
  if (
    num(ticket.issued_at) !== undefined &&
    policyTimestamp !== undefined &&
    (num(ticket.issued_at) as number) < policyTimestamp
  )
    issues.push('Ticket predates policy')
  const verificationConsistent = matchesFinalWorld(v, post)
  if (verification.status === 'VERIFIED' && !verificationConsistent)
    issues.push(
      'Verification postconditions do not resolve to the recorded final plant state'
    )

  const recoveryAction = freshTicket.action_type ?? proposal.action_type
  const recoveryTarget = str(freshTicket.target ?? proposal.target)
  const recoveredValve = recoveryTarget
    ? obj(post.valves)[recoveryTarget]
    : undefined
  const recoveryWorldContradiction =
    recoveryAction === 'CLOSE_VALVE'
      ? (recoveredValve !== undefined && recoveredValve !== 'CLOSED') ||
        (obj(post.leak).target === recoveryTarget &&
          obj(post.leak).active === true)
      : recoveryAction === 'OPEN_VALVE' &&
        recoveredValve !== undefined &&
        recoveredValve !== 'OPEN'

  const outcomeAt = (index: number): PresentationOutcome => {
    if (!scenarioData) return 'UNKNOWN'
    if (index >= 3 && policyConflict) return 'UNVERIFIED'
    if (index >= 7 && unauthorized) return 'ERROR'
    if (index >= 3 && policy === 'DENY') return 'DENIED'
    if (index >= 6 && blocked) return 'BLOCKED'
    if (index >= 9 && recoveryPresent) {
      if (
        recoveryFailed ||
        recovery.component_status === 'QUARANTINED' ||
        verificationFailed(finalV) ||
        (verificationFailed(v) && !str(recoveryAction)) ||
        (recoverySuccess && recoveryWorldContradiction)
      )
        return 'VERIFICATION_FAILED'
      return recoverySuccess && finalVerified && issues.length === 0
        ? 'RECOVERED'
        : 'UNVERIFIED'
    }
    if (index >= 8 && (verificationFailed(v) || fault))
      return 'VERIFICATION_FAILED'
    if (
      index >= 8 &&
      executed &&
      policy === 'ALLOW' &&
      completeTicket &&
      validAtExecution &&
      primaryVerified &&
      issues.length === 0
    )
      return 'NOMINAL'
    if (index >= 7 && rejected) return 'BLOCKED'
    if (
      index >= 3 &&
      noActuation &&
      evidenceRecorded &&
      !mutation &&
      issues.length === 0
    )
      return 'COMPLETED'
    return 'UNVERIFIED'
  }

  // Snapshots are discrete source records, never synthesized stage templates. Reuse the
  // exact object on both panels. Names below describe recorded snapshot phases, not routes.
  const snapshotPhases: Record<string, number> = {
    initial: 0,
    post_actuation: 7,
    authorized: 4,
    denied: 3,
    drifted: 5,
    fault_injected: 7,
    actuated: 7,
    verified: 8,
    locked: 7,
    locked_toctou: 6,
    recovered: 9,
  }
  const snapshots = arr(d.digital_twin_snapshots)
    .map((value, index) => ({ value: obj(value), index }))
    .filter(
      (s) =>
        str(s.value.stage_name) !== undefined &&
        num(s.value.timestamp) !== undefined &&
        num(s.value.world_version) !== undefined &&
        [
          'pump_state',
          'valve_b_state',
          'cooling_state',
          'human_zone',
          'actuator_status',
        ].every((k) => str(s.value[k]) !== undefined) &&
        [
          'valve_b_angle_deg',
          'human_distance_m',
          'pressure_psi',
          'flow_rate_lpm',
        ].every(
          (k) =>
            !own(s.value, k) ||
            s.value[k] === null ||
            num(s.value[k]) !== undefined
        ) &&
        (!own(s.value, 'leak_active') ||
          typeof s.value.leak_active === 'boolean')
    )
    .sort(
      (a, b) =>
        (num(a.value.timestamp) as number) - (num(b.value.timestamp) as number)
    )
  const snapshotMatches = (snapshot: RecordValue, world: RecordValue) => {
    const actual = worldPlant(world)
    return [
      'valve_b_state',
      'pump_state',
      'cooling_state',
      'human_zone',
      'world_version',
      'leak_active',
    ].every((key) => {
      const expected = actual[key as keyof PresentationPlantState]
      return (
        expected === undefined ||
        expected === 'NOT_RECORDED' ||
        snapshot[key] === expected
      )
    })
  }
  const snapshotReference = (phase: number) =>
    phase <= 4
      ? pre
      : phase >= 9
        ? post
        : phase >= 7
          ? obj(hw.observed_state)
          : {}
  for (const snapshot of snapshots) {
    const phase = snapshotPhases[text(snapshot.value.stage_name)]
    if (
      phase !== undefined &&
      !snapshotMatches(snapshot.value, snapshotReference(phase))
    )
      issues.push(
        `Physical snapshot ${snapshot.index} contradicts its recorded world/hardware state`
      )
  }
  const initial = worldPlant(pre)
  const stateFor = (
    index: number
  ): { state: PresentationPlantState; path: string } => {
    let selected: { state: PresentationPlantState; path: string } = {
      state: initial,
      path: Object.keys(pre).length ? 'pre_state' : 'NOT_RECORDED',
    }
    for (const s of snapshots) {
      const recordedPhase = snapshotPhases[text(s.value.stage_name)]
      const phase =
        recordedPhase === undefined
          ? undefined
          : Math.max(
              recordedPhase,
              s.value.actuator_status === 'VERIFIED' ? 8 : 0
            )
      if (phase === undefined || phase > index) continue
      if (!snapshotMatches(s.value, snapshotReference(phase))) continue
      if (
        phase === 0 &&
        str(obj(pre.valves).valve_b) &&
        s.value.valve_b_state !== obj(pre.valves).valve_b
      )
        continue
      if (phase === 4 && !hasTicket) continue
      if (phase === 5 && !driftRecorded) continue
      if (phase === 6 && !blocked) continue
      if (phase === 7 && !Object.keys(hw).length) continue
      if (phase === 8 && (!primaryVerified || outcomeAt(8) !== 'NOMINAL'))
        continue
      if (phase === 9 && !recoveryPresent) continue
      if (
        phase === 9 &&
        s.value.actuator_status === 'VERIFIED' &&
        outcomeAt(9) !== 'RECOVERED'
      ) {
        // Keep the actual terminal world, without borrowing an unsupported
        // verification label from the physical visualization snapshot.
        selected = { state: worldPlant(post), path: 'post_state' }
        continue
      }
      // A NO_OP's initial stroke cannot borrow a later successful recovery state.
      if (
        phase === 7 &&
        fault &&
        s.value.valve_b_state !== obj(pre.valves).valve_b
      )
        continue
      selected = {
        state: s.value as PresentationPlantState,
        path: `digital_twin_snapshots[${s.index}]`,
      }
    }
    // Hardware observations and final world states are independent source snapshots
    // too. Project only their recorded fields if a dedicated twin snapshot is absent.
    if (
      !snapshots.length &&
      index >= (recoveryPresent ? 9 : 8) &&
      Object.keys(post).length &&
      (Object.keys(hw).length || driftRecorded)
    )
      return { state: worldPlant(post), path: 'post_state' }
    if (
      index >= 7 &&
      Object.keys(obj(hw.observed_state)).length &&
      (selected.state.timestamp === undefined ||
        (execTimestamp !== undefined &&
          selected.state.timestamp < execTimestamp))
    )
      return {
        state: worldPlant(hw.observed_state),
        path: 'execution_result.observed_state',
      }
    return selected
  }
  const statuses: StageStatus[] = [
    (str(obj(pre.valves).valve_b) &&
      str(pre.human_zone) &&
      num(pre.version) !== undefined) ||
    snapshots.some(
      (s) => s.value.stage_name === 'initial' && snapshotMatches(s.value, pre)
    )
      ? 'PASSED'
      : 'UNVERIFIED',
    evidenceRecorded ? 'PASSED' : 'UNVERIFIED',
    str(proposal.action_type) && str(proposal.target) && str(proposal.rationale)
      ? 'PASSED'
      : 'UNVERIFIED',
    policyConflict || policy === 'UNKNOWN' || !reasons.length
      ? 'UNVERIFIED'
      : policy === 'DENY'
        ? 'DENIED'
        : 'PASSED',
    policy === 'DENY' && !hasTicket
      ? 'NOT_APPLICABLE'
      : completeTicket &&
          policy === 'ALLOW' &&
          !!event('ENCLAVE_AUTHORIZATION_GRANTED')
        ? 'PASSED'
        : 'UNVERIFIED',
    driftRecorded
      ? 'PASSED'
      : Object.keys(drift).length
        ? 'UNVERIFIED'
        : 'NOT_APPLICABLE',
    blocked
      ? 'BLOCKED'
      : revalStatus === 'PASSED' && hasTicket
        ? 'PASSED'
        : policy === 'DENY' || noActuation
          ? 'NOT_APPLICABLE'
          : 'UNVERIFIED',
    unauthorized
      ? 'FAILED'
      : fault || hwStatus === 'FAILED'
        ? 'FAILED'
        : rejected
          ? 'BLOCKED'
          : executed &&
              completeTicket &&
              validAtExecution &&
              policy === 'ALLOW' &&
              !blocked &&
              issues.length === 0
            ? 'PASSED'
            : noActuation || policy === 'DENY'
              ? 'NOT_APPLICABLE'
              : 'UNVERIFIED',
    verificationFailed(v)
      ? 'FAILED'
      : primaryVerified && outcomeAt(8) === 'NOMINAL'
        ? 'PASSED'
        : rejected || noActuation
          ? 'NOT_APPLICABLE'
          : 'UNVERIFIED',
    recoveryFailed || verificationFailed(finalV)
      ? 'FAILED'
      : recoveryPresent
        ? outcomeAt(9) === 'RECOVERED'
          ? 'PASSED'
          : 'UNVERIFIED'
        : fault ||
            verificationFailed(v) ||
            Object.keys(obj(d.recovery_plan)).length
          ? 'UNVERIFIED'
          : 'NOT_APPLICABLE',
  ]
  const inferenceProvider = text(
    d.original_inference_provider ?? provider.provider ?? d.provider
  )
  const model = text(provider.model ?? d.model)
  const recordedInference =
    Object.keys(proposal).length > 0 &&
    inferenceProvider === 'nebius' &&
    /nemotron/i.test(model)
  const evidenceTimestamps = [
    num(pre.timestamp),
    undefined,
    num(proposal.timestamp),
    policyTimestamp,
    num(ticket.issued_at),
    num(
      snapshots.find((s) => s.value.stage_name === 'drifted')?.value.timestamp
    ),
    num(reval.timestamp) ??
      num(
        event(
          blocked ? 'HARDWARE_TICKET_REJECTED' : 'HARDWARE_TICKET_VALIDATED'
        )?.timestamp
      ),
    execTimestamp,
    verifyTimestamp,
    finalVerified
      ? num(obj(finalV).timestamp)
      : num(event('RECOVERY_COMPLETED')?.timestamp),
  ]
  const frames: PresentationFrame[] = keys.map((stageKey, i) => {
    const physical = stateFor(i)
    return {
      scenarioId,
      stageIndex: i,
      evidenceTimestamp: evidenceTimestamps[i],
      stageKey,
      stageLabel: `${i + 1}. ${labels[i]}`,
      stageStatus: statuses[i],
      outcome: outcomeAt(i),
      stageSubtitle: [
        'Recorded plant observation',
        evidenceRecorded
          ? 'Recorded evidence references'
          : 'Evidence NOT_RECORDED',
        recordedInference
          ? 'Recorded model proposal — zero actuator authority'
          : 'Proposal source NOT_RECORDED',
        `Policy ${policy}`,
        signedTicket
          ? 'Signature recorded; validity requires execution-time evidence'
          : 'Authorization NOT_RECORDED',
        driftRecorded
          ? `Recorded version change v${beforeVersion} → v${afterVersion}`
          : 'State drift NOT_RECORDED',
        `Revalidation ${revalStatus}`,
        `Hardware ${hwStatus}`,
        `Verification ${text(verification.status)}`,
        recoveryPresent
          ? `Recovery reported ${text(recovery.outcome ?? recovery.status)}; final verification ${finalVerified ? 'VERIFIED' : 'UNVERIFIED'}`
          : 'Recovery result NOT_RECORDED',
      ][i],
      plantState: physical.state,
      sourceSnapshotPath: physical.path,
      cameraPreset:
        i === 5 && driftRecorded
          ? 'safety_zone'
          : i === 7 || i === 6
            ? 'actuator'
            : i === 9
              ? 'recovery'
              : i === 2 || i === 8
                ? 'valve_b'
                : 'full',
      provenanceMode: mode,
      originalSourceMode: text(
        d.original_source_mode ??
          provider.source_mode ??
          d.original_execution_mode ??
          d.execution_mode
      ),
      inferenceProvider,
      inferenceLabel: recordedInference
        ? 'RECORDED NEMOTRON INFERENCE'
        : 'INFERENCE NOT_RECORDED',
      physicalBackend: text(d.physical_backend ?? r.physical_backend),
      recordHash: str(d.record_hash ?? d.sha256_hash ?? r.record_hash),
      timestamp: num(physical.state.timestamp),
      sourcePaths: [physical.path],
      evidenceIssues: issues,
    }
  })
  frames[2].proposal = {
    action: text(proposal.action_type),
    target: text(proposal.target),
    rationale: text(proposal.rationale),
    confidence: num(proposal.model_confidence),
    provider: inferenceProvider,
    model,
    rawProposalHash: str(
      proposal.raw_proposal_hash ?? provider.raw_proposal_hash
    ),
  }
  frames[3].policy = {
    decision: policy,
    rulesEvaluated: reasons.length || undefined,
    ruleViolations: reasons
      .filter((r) => obj(r).status === 'failed')
      .map(reasonText),
    reason: reasons.length
      ? reasons.map(reasonText).join(' · ')
      : 'NOT_RECORDED',
  }
  frames[4].authorization = {
    status: signedTicket
      ? 'SIGNATURE_RECORDED'
      : hasTicket
        ? 'UNVERIFIED'
        : policy === 'DENY' &&
            ((own(d, 'ticket') && d.ticket === null) ||
              (own(r, 'authorization_ticket_id') &&
                r.authorization_ticket_id === null))
          ? 'NOT_ISSUED'
          : 'NOT_RECORDED',
    ticketId: str(ticket.ticket_id),
    plantHash: str(ticket.world_state_hash),
    expiresInSeconds:
      num(ticket.expires_at) !== undefined &&
      num(ticket.issued_at) !== undefined
        ? (ticket.expires_at as number) - (ticket.issued_at as number)
        : undefined,
    algorithm: str(ticket.algorithm),
    validity: 'UNVERIFIED',
    consumption: 'NOT_RECORDED',
  }
  frames[5].worldChange = {
    previousVersion: beforeVersion,
    newVersion: afterVersion,
    driftDetected: driftRecorded ? true : undefined,
    description: driftRecorded
      ? `${text(drift.field)}: ${text(drift.before ?? drift.from_value)} → ${text(drift.after ?? drift.to_value)}`
      : 'No state drift event recorded; stability is not independently verified.',
    sensorTrigger: str(drift.trigger),
  }
  frames[6].revalidation = {
    status: revalStatus,
    expectedHash: str(
      reval.expected_hash ??
        r.ticket_world_state_hash ??
        ticket.world_state_hash
    ),
    actualHash: str(reval.actual_hash ?? r.execution_context_hash),
    versionMatch:
      num(r.ticket_world_state_version) !== undefined &&
      num(r.execution_context_version) !== undefined
        ? r.ticket_world_state_version === r.execution_context_version
        : undefined,
    barriersChecked: Array.isArray(reval.checks)
      ? reval.checks.length
      : undefined,
  }
  frames[7].execution = {
    status: hwStatus,
    actuatorId: text(hw.hardware_id ?? hw.actuator_id),
    commandedAngle: num(hw.commanded_angle_deg),
    faultInjected: str(hw.fault_injected),
    busVoltageV: num(hw.bus_voltage_v),
    ticketValidity: text(hw.ticket_status),
    ticketConsumption:
      ticket.consumed === true && Object.keys(hw).length
        ? 'CONSUMED (recorded terminal ticket)'
        : ticket.consumed === false && Object.keys(hw).length
          ? 'NOT_CONSUMED (recorded terminal ticket)'
          : 'NOT_RECORDED',
  }
  const verificationStatus =
    statuses[8] === 'PASSED'
      ? 'VERIFIED'
      : statuses[8] === 'FAILED'
        ? 'VERIFICATION_FAILED'
        : !Object.keys(verification).length
          ? statuses[8] === 'NOT_APPLICABLE'
            ? 'NOT_REACHED'
            : 'NOT_RECORDED'
          : 'UNVERIFIED'
  frames[8].stageSubtitle = `Verification ${verificationStatus}`
  frames[8].verification = {
    status: verificationStatus,
    isVerified: statuses[8] === 'PASSED',
    limitSwitchReadback: str(
      obj(verification.observed_postconditions)[
        `valves.${text(proposal.target)}`
      ]
    ),
    commandedState: str(
      obj(verification.expected_postconditions)[
        `valves.${text(proposal.target)}`
      ]
    ),
    sensorContradiction: verificationFailed(v),
  }
  frames[9].recovery = {
    failureDetection:
      event('ACTION_FAILURE_DETECTED') || verificationFailed(v)
        ? 'DETECTED'
        : 'NOT_RECORDED',
    containment: event('CONTAINMENT_STARTED') ? 'STARTED' : 'NOT_RECORDED',
    quarantine:
      event('COMPONENT_QUARANTINED') ||
      recovery.component_status === 'QUARANTINED'
        ? 'QUARANTINED'
        : event('COMPONENT_MARKED_SUSPECT')
          ? 'SUSPECT (recorded)'
          : 'NOT_RECORDED',
    proposal:
      event('RECOVERY_ACTION_PROPOSED') ||
      Object.keys(obj(d.recovery_plan)).length
        ? 'PROPOSED'
        : 'NOT_RECORDED',
    execution: Object.keys(retryExecution).length
      ? text(retryExecution.execution_status)
      : 'NOT_RECORDED',
    reportedOutcome: text(recovery.outcome ?? recovery.status),
    componentStatus: text(recovery.component_status),
    finalVerification: finalVerified
      ? 'VERIFIED'
      : Object.keys(obj(finalV)).length
        ? 'UNVERIFIED'
        : 'NOT_RECORDED',
    status: recoveryPresent
      ? outcomeAt(9) === 'RECOVERED'
        ? 'RECOVERED'
        : recoveryFailed
          ? 'FAILED'
          : 'UNVERIFIED'
      : 'NOT_RECORDED',
    recoveryPath: str(
      recovery.recovery_strategy ?? obj(d.recovery_plan).strategy
    ),
    quarantinedValve:
      str(d.quarantined_component) ??
      (recovery.component_status === 'QUARANTINED'
        ? str(proposal.target)
        : undefined),
    isPostRecoveryVerified: finalVerified,
    disclosureNotice: !finalVerified
      ? 'FINAL INDEPENDENT VERIFICATION NOT RECORDED OR FAILED'
      : undefined,
  }
  frames.forEach((f, i) =>
    f.sourcePaths.push(
      [
        'pre_state',
        'decision_record.sensor_evidence_ids / snapshots.evidence',
        'decision_record.action_proposal',
        'policy_decision',
        'ticket',
        'world_change_event',
        'decision_record.revalidation_status / events',
        'execution_result',
        'verification_result',
        'recovery_result / retry_verification',
      ][i]
    )
  )
  return {
    scenarioId,
    scenarioTitle: text(d.title ?? scenarioId).replace(
      /\blive\b/gi,
      mode === 'LIVE' ? 'Live' : 'Recorded'
    ),
    overallOutcome: outcomeAt(9),
    frames,
  }
}

export function displayedStageStatus(
  frame: PresentationFrame,
  activeIndex: number
): StageStatus {
  return frame.stageIndex > activeIndex ? 'PENDING' : frame.stageStatus
}
