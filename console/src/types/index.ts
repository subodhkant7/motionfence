export type ViewMode = 'replay' | 'firewall' | 'trajectories' | 'assurance'

export type ExecutionMode = 'LIVE' | 'REPLAY' | 'OFFLINE_TEST'

export interface ScenarioMeta {
  id: string
  title: string
  subtitle: string
  flow: string
  category: 'NOMINAL' | 'TOCTOU_DEFENSE' | 'FAULT_RECOVERY' | string
  execution_mode?: ExecutionMode
  model?: string
}

export interface DigitalTwinPlantState {
  timestamp?: number
  stage_name: string
  pump_state: string
  valve_b_state: string
  cooling_state: string
  human_zone: string
  actuator_status: string
  world_version: number
  leak_active?: boolean
  pressure_psi?: number
  flow_rate_lpm?: number
}

export interface ObservationReading {
  [key: string]: any
}

export interface SensorObservation {
  sensor_id?: string
  sensor_type?: string
  target?: string
  reading?: ObservationReading
  confidence?: number
  timestamp?: number
  metadata?: Record<string, any>
}

export interface WorldState {
  valves: Record<string, string>
  cooling: string
  human_zone: string
  pumps: Record<string, string>
  leak?: {
    active: boolean
    target: string
    severity: number
    flow_rate_lpm: number
  }
  version: number
  timestamp?: number
  observations?: Record<string, SensorObservation>
}

export interface EvidenceItem {
  id: string
  source: string
  target: string
  observation: Record<string, any>
  confidence: number
  timestamp: number
  provenance: string
  metadata?: Record<string, any>
  trust_status?: string
  applicability?: string
  claim_support?: string
}

export interface ActionProposal {
  id: string
  action_type: string
  target: string
  parameters?: Record<string, any>
  rationale: string
  model_confidence: number
  supporting_evidence_ids: string[]
  timestamp?: number
}

export interface PolicyDecision {
  decision_type?: string
  is_allowed?: boolean
  reasons: string[]
  checked_constraints?: string[]
}

export interface AuthorizationTicket {
  ticket_id: string
  action_type: string
  target: string
  issued_at: number
  expires_at: number
  world_state_version: number
  world_state_hash: string
  policy_version: string
  constraint_set_hash?: string
  evidence_context_hash?: string
  nonce: string
  status?: 'VALID' | 'INVALIDATED' | 'CONSUMED'
  invalidation_reason?: string
}

export interface ExecutionResult {
  success: boolean
  action_id: string
  ticket_id: string
  executed_action: string
  target: string
  message: string
  state_version_before: number
  state_version_after: number
}

export interface VerificationResult {
  action_id: string
  target: string
  action_occurred: boolean
  expected_postconditions: Record<string, any>
  observed_postconditions: Record<string, any>
  status: string
  discrepancies: string[]
}

export interface DecisionRecord {
  decision_id: string
  sequence_number: number
  created_at: number
  finalized_at?: number
  is_finalized: boolean
  record_hash?: string
  previous_record_hash?: string
  intent: string
  world_state_snapshot: WorldState
  sensor_evidence_ids: string[]
  action_proposal?: ActionProposal
  policy_decision: string
  policy_reasons: string[]
  authorization_ticket_id?: string
  execution_result?: ExecutionResult
  verification_result?: VerificationResult
  runtime_version: string
  policy_version: string
  schema_version: string
  provider_metadata?: Record<string, any>
  snapshots?: {
    evidence?: EvidenceItem[]
    knowledge?: any[]
  }
  authorization_context_hash?: string
  ticket_world_state_version?: number
  ticket_world_state_hash?: string
  revalidation_status?: string
  revalidation_reasons?: string[]
  execution_context_version?: number
  execution_context_hash?: string
}

export interface ScenarioData {
  scenario_id: string
  title: string
  subtitle: string
  flow_summary: string
  category: string
  decision_record: DecisionRecord
  events: any[]
  pre_state: WorldState
  post_state: WorldState
  policy_decision?: PolicyDecision
  ticket?: AuthorizationTicket
  initial_ticket?: AuthorizationTicket
  execution_result?: ExecutionResult
  verification_result?: VerificationResult
  world_change_event?: {
    trigger: string
    field: string
    from_value: string
    to_value: string
    version_at_issuance: number
    version_at_revalidation: number
  }
  // Recovery scenario fields
  failure_record?: any
  quarantine_records?: Record<string, any>
  quarantined_component?: string
  quarantine_reason?: string
  recovery_plan?: any
  fresh_ticket?: AuthorizationTicket
  retry_execution?: ExecutionResult
  retry_verification?: VerificationResult
  outcome?: string
  is_recovered?: boolean
  unsafe_retries?: number
  // Phase 2N: Live demo and digital twin metadata
  execution_mode?: ExecutionMode
  provider?: string
  model?: string
  token_usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    [key: string]: any
  }
  digital_twin_snapshots?: DigitalTwinPlantState[]
  record_hash?: string
  sha256_hash?: string
}

export interface MutationItem {
  evaluation_id: string
  mutation: {
    mutation_id: string
    parent_policy_hash: string
    mutated_policy_hash: string
    mutation_type: string
    mutation_target: string
    before_value: any
    after_value: any
    description: string
    relevance: string
    created_at: number
    parent_mutations?: string[]
    mutation_depth?: number
  }
  regression_type: string
  firewall_decision: 'ACCEPT' | 'REJECT' | 'INCONCLUSIVE'
  baseline_unsafe_allows: number
  mutated_unsafe_allows: number
  new_unsafe_allows: number
  violated_properties: string[]
  counterexample?: {
    counterexample_id: string
    mutation_id: string
    action_type: string
    target: string
    human_zone: string
    cooling: string
    contradiction_severity: string
    confidence: number
    baseline_decision: string
    mutated_decision: string
    regression: string
    explanation: string
    minimized_scenario: Record<string, any>
  }
  diff_explanation: string
  duration_seconds: number
  survived: boolean
  mutation_depth: number
  interaction_type: 'NO_INTERACTION' | 'ADDITIVE' | 'AMPLIFYING' | 'CONFLICTING' | 'MASKING'
  formal_regressions: string[]
  authorization_boundary_regressions: string[]
}

export interface FirewallReport {
  report_id: string
  timestamp: number
  baseline_policy_id: string
  baseline_policy_hash: string
  total_mutations: number
  safety_relevant_mutations: number
  detected_regressions: number
  survived_mutations: number
  overall_decision: 'ACCEPT' | 'REJECT' | 'INCONCLUSIVE'
  results: MutationItem[]
  single_mutations_tested?: number
  compound_mutations_tested?: number
  interaction_classifications?: Record<string, number>
  trajectories_tested?: number
  repair_proposals_generated?: number
  repairs_rejected?: number
  repairs_accepted_by_validation?: number
  inconclusive_repairs?: number
}

export interface RepairProposal {
  mutation_id: string
  mutation_type: string
  target_field: string
  before_value: any
  after_value: any
  regression_type: string
  counterexample_ref?: string
  repair_status: 'VALIDATED' | 'REJECTED' | 'INCONCLUSIVE'
  proposed_patch: Record<string, any>
  safety_rationale: string
  is_authoritative: boolean
  is_applied: boolean
}

export interface TrajectoryStepData {
  step_index: number
  event_name: string
  action?: string
  target?: string
  fault?: string
  observed_state: Record<string, any>
  hidden_ground_truth: Record<string, any>
  revalidation_passed: boolean
  execution_status: string
}

export interface DynamicTrajectoryData {
  trajectory_id: string
  description: string
  depth: number
  outcome: string
  is_regression: boolean
  failing_step_index?: number
  minimized_steps: string[]
  explanation: string
  timesteps: TrajectoryStepData[]
}

export interface AssuranceProperty {
  property_id: string
  name: string
  description: string
  subsystem: string
  status: 'SATISFIED' | 'VIOLATED' | 'UNKNOWN'
  bounded_model: string
  formula: string
  counterexample?: any
}

export interface AssuranceReport {
  total_properties: number
  satisfied: number
  violated: number
  unknown: number
  limitation_notice: string
  properties: AssuranceProperty[]
}
