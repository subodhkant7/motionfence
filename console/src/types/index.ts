export type ViewMode = 'replay' | 'firewall' | 'trajectories' | 'assurance'

export type ExecutionMode = 'LIVE' | 'REPLAY' | 'OFFLINE_TEST'

export type PhysicalBackend = 'mock' | 'isaac' | 'replay'

export interface IsaacPrimPaths {
  valve_b?: string
  pump_p1?: string
  human_zone?: string
  human_worker?: string
  gateway_actuator?: string
  [key: string]: string | undefined
}

export interface ScenarioMeta {
  id: string
  title: string
  subtitle: string
  flow: string
  category: 'NOMINAL' | 'TOCTOU_DEFENSE' | 'FAULT_RECOVERY' | string
  execution_mode?: ExecutionMode
  physical_backend?: PhysicalBackend
  model?: string
}

export interface DigitalTwinPlantState {
  timestamp?: number
  stage_name: string
  pump_state: string
  valve_b_state: string
  valve_b_angle_deg?: number
  cooling_state: string
  human_zone: string
  human_distance_m?: number
  actuator_status: string
  world_version: number
  leak_active?: boolean
  pressure_psi?: number
  flow_rate_lpm?: number
  physical_backend?: PhysicalBackend
  isaac_prim_paths?: IsaacPrimPaths
  simulation_time?: number
  step_count?: number
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
  external_observations?: Record<string, any>
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
  telemetry_observation?: TelemetryObservation
  physical_backend?: PhysicalBackend
  isaac_prim_paths?: IsaacPrimPaths
}

export interface TelemetryObservation {
  observation_id: string
  provider: string
  source_system: string
  source_url: string
  monitoring_location_id: string
  monitoring_location_name?: string
  parameter_code: string
  parameter_name?: string
  raw_value: string
  normalized_value: number
  unit: string
  observed_at: string
  observed_timestamp?: number
  retrieved_at: string
  retrieved_timestamp?: number
  freshness: 'FRESH' | 'STALE' | 'UNKNOWN' | string
  freshness_age_seconds?: number
  approval_status?: string | null
  qualifier?: string | null
  source_metadata?: Record<string, any>
  provenance_hash: string
  raw_record_hash: string
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
  // Phase 2O: Public telemetry integration
  telemetry_observation?: TelemetryObservation
  telemetry_snapshots?: TelemetryObservation[]
  // Phase 2P: Physical execution backend & Isaac Sim
  physical_backend?: PhysicalBackend
  isaac_prim_paths?: IsaacPrimPaths
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

export interface AssertionResultData {
  rule_id: string
  description: string
  passed: boolean
  expected: any
  actual: any
  message: string
}

export interface MetricValueData {
  name: string
  description: string
  formula: string
  numerator: number
  denominator: number
  rate: number | null
  formatted_value: string
  is_target_met: boolean
  target_description: string
  unit: string
}

export interface SafetyLabScenarioData {
  scenario_id: string
  version: string
  title: string
  threat_category: string
  threat_description: string
  metric_classification: string
  initial_plant_state: Record<string, any>
  ground_truth: {
    expected_policy_decision: string
    expected_authorization: string
    expected_execution: string
    expected_verification: string
    expect_ticket_minted: boolean
    expect_mutation: boolean
    expect_fail_closed: boolean
    invariants: string[]
  }
  assertion_count: number
  assertion_rules: Array<{
    rule_id: string
    description: string
    target_field: string
    expected_value: any
    comparison: string
  }>
}

export interface SafetyLabExecutionResultData {
  execution_id: string
  scenario_id: string
  scenario_version: string
  title: string
  execution_mode: string
  started_at: number
  completed_at: number
  duration_ms: number
  simulation_duration_ms: number
  backend_duration_ms: number
  initial_state_summary: Record<string, any>
  final_state_summary: Record<string, any>
  proposal_summary?: Record<string, any> | null
  policy_decision: string
  policy_reason_codes: string[]
  authorization_status: string
  ticket_minted: boolean
  ticket_id?: string | null
  revalidation_status?: string | null
  execution_status: string
  mutation_occurred: boolean
  verification_status: string
  verification_discrepancies: string[]
  events: Array<{ timestamp?: number; stage?: string; message?: string; details?: any }>
  assertions: AssertionResultData[]
  passed: boolean
  failure_reasons: string[]
  sha256_hash: string
  evidence_bundle_id: string
}

export interface BenchmarkMetricsData {
  unsafe_actuation_rate: MetricValueData
  false_verification_rate: MetricValueData
  scenario_pass_rate: MetricValueData
  false_denial_rate: MetricValueData
  fail_closed_coverage: MetricValueData
  verification_coverage: MetricValueData
  latency_summary: {
    median_ms: number
    p95_ms: number
    min_ms: number
    max_ms: number
    mean_simulation_ms: number
    mean_backend_ms: number
    sample_size: number
  }
}

export interface BenchmarkReportData {
  benchmark_version: string
  registry_version: string
  run_id: string
  timestamp_utc: string
  build_id: string
  git_commit?: string
  execution_mode: string
  seed: number
  total_scenarios_evaluated: number
  scenarios_passed: number
  scenarios_failed: number
  all_passed: boolean
  metrics: BenchmarkMetricsData
  scenario_results: SafetyLabExecutionResultData[]
  limitations: string[]
  sha256_hash: string
}

