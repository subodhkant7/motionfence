# MotionFence Domain Models

This document details the core typed domain models that establish deterministic boundaries between agent perception, operational knowledge, policy evaluation, actuator execution, and post-action verification.

All models are implemented using **Pydantic v2** with strict typing and runtime validation.

---

## 1. WorldState

Represents an immutable snapshot of the ground-truth physical environment.

```python
class WorldState(BaseModel):
    valves: Dict[str, ValveState] = {"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN}
    cooling: CoolingState = CoolingState.ACTIVE
    leak: LeakState = LeakState(active=True, target="valve_b", severity=0.85)
    human_zone: HumanZoneState = HumanZoneState.CLEAR
    pumps: Dict[str, str] = {"pump_p1": "ACTIVE"}  # Auxiliary pump states
    observations: Dict[str, SensorObservation]
    version: int = 1
    timestamp: float
```

### Enumerations & Components:
* [`ValveState`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/world.py#L9): `OPEN`, `CLOSED`, `JAMMED`, `TRANSITIONING`
* [`CoolingState`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/world.py#L17): `ACTIVE`, `INACTIVE`, `DEGRADED`
* [`HumanZoneState`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/world.py#L24): `CLEAR`, `OCCUPIED`, `WARNING`
* [`LeakState`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/world.py#L31): `active: bool`, `target: Optional[str]`, `severity: float`, `flow_rate_lpm: float`

---

## 2. Knowledge Evidence (Phase 2A)

Represents operational documentation, engineering manuals, and plant SOPs retrieved from local fixtures or external search engines (Tavily).

```python
class KnowledgeEvidence(BaseModel):
    id: str                               # e.g., 'kb_fixture_001', 'kb_tavily_1'
    query: str                            # Query used for retrieval
    title: str                            # Document section title
    source_url: str                       # URL or local URI (e.g. 'local://plant_manual_v1')
    content: str                          # Extracted text snippet or operating guidance
    retrieved_at: float                   # Timestamp of retrieval
    source_metadata: Dict[str, Any]       # Section number, category, search score
    provenance: str                       # Detailed attribution (e.g., 'local_fixture:plant_safety_manual_v1')
    confidence: float                     # Confidence score [0.0, 1.0]
    trust_status: TrustStatus             # Categorical trust qualification
```

### Trust & Freshness States:
* [`TrustStatus`](file:///Users/urjasoft/Documents/MotionFence/motionfence/knowledge/models.py#L10):
  - `UNVERIFIED_EXTERNAL`: Retrieved from external sources (Tavily). Untrusted evidence.
  - `LOCAL_FIXTURE`: Deterministic local plant fixture.
  - `VALIDATED`: Formally verified against ground truth or engineering registry.
  - `STALE`: Outdated documentation requiring recertification.
  - `REJECTED`: Missing provenance, malformed, or explicitly untrusted.
* [`FreshnessStatus`](file:///Users/urjasoft/Documents/MotionFence/motionfence/knowledge/models.py#L19):
  - `FRESH`: Within nominal validity window.
  - `AGING`: Approaching expiration threshold.
  - `STALE`: Exceeded freshness threshold (> 30 days default).

---

## 3. Evidence Trust & Admissibility Models (Phase 2B)

Phase 2B formalizes the boundary between external discovery evidence and executable authorization authority.

### 3.1 SourceTrustAssessment
```python
class SourceTrustAssessment(BaseModel):
    evidence_id: str                      # Cites KnowledgeEvidence ID
    source_type: Optional[str]            # Categorical source type
    source_category: SourceCategory       # Origin taxonomy
    authority_level: AuthorityLevel       # Graded authoritative weight
    evidence_role: EvidenceRole           # Operational role assignment
    relevance: float                      # Industrial operational relevance [0.0, 1.0]
    provenance_quality: str               # e.g., 'VERIFIED_OEM_MANUFACTURER'
    freshness: FreshnessStatus            # FRESH, AGING, STALE
    trust_score: float                    # Internal prioritization metric (NOT objective truth)
    reasons: List[str]                    # Auditable deterministic rationale
```

### 3.2 Taxonomies:
* **`SourceCategory`**:
  - `FIRST_PARTY_OFFICIAL`: Internal plant safety manuals, site SOPs.
  - `MANUFACTURER_DOCUMENTATION`: Verified OEM equipment manuals (e.g. KSB, Flowserve).
  - `REGULATORY_OR_STANDARDS`: Accredited engineering standards (ASME, ISO, OSHA).
  - `CURATED_TECHNICAL_SOURCE`: Peer-reviewed engineering papers, verified publishers.
  - `GENERAL_TECHNICAL_SOURCE`: General industrial blogs, non-OEM technical guides.
  - `COMMUNITY_OR_USER_CONTENT`: Social media, Reddit, Scribd, user forums.
  - `UNKNOWN`: Unverifiable or unattributed origin.

* **`AuthorityLevel`**: `HIGH`, `MEDIUM`, `LOW`, `UNTRUSTED`.

* **`EvidenceRole`**:
  - `DISCOVERY`: Alerts operators to potential issues; **cannot independently activate safety prohibitions**.
  - `SUPPORTING`: Provides auxiliary guidance; requires multi-source corroboration before activating safety prohibitions.
  - `AUTHORIZATION_RELEVANT`: Authoritative; qualified to directly establish active policy rules.
  - `REJECTED`: Inadmissible.

* **`CorroborationStatus`**:
  - `CORROBORATED`: Independently confirmed by multiple distinct qualified sources.
  - `SINGLE_SOURCE`: Derived from a single authoritative source.
  - `DUPLICATE_SOURCE`: Near-duplicate verbatim citations / scraped mirror content (Jaccard >= 0.85).
  - `UNSUPPORTED`: Insufficient authority to corroborate claim.

### 3.3 PlantContext & Applicability
```python
class PlantContext(BaseModel):
    plant_profile: str = "industrial_fluid_plant"
    equipment_type: str = "centrifugal_pump"
    equipment_model: Optional[str] = "P100-A"
    equipment_id: str = "pump_p1"
    operating_mode: str = "nominal"
    authorized_targets: List[str] = ["valve_a", "valve_b", "pump_p1"]

class Applicability(str, Enum):
    DIRECT = "DIRECT"        # Matches target equipment ID and plant context
    PARTIAL = "PARTIAL"      # Generic guidance for equipment class without plant-specific model
    UNKNOWN = "UNKNOWN"      # Context cannot be confirmed from document
    MISMATCH = "MISMATCH"    # Foreign equipment family or operating mode
```

---

## 4. Candidate Constraints & Conflicts

Structured operational rules extracted from knowledge evidence.

```python
class CandidateConstraint(BaseModel):
    constraint_id: str
    constraint_type: ConstraintType      # PROHIBITION, REQUIREMENT, PRECONDITION, POSTCONDITION, INFORMATIONAL
    action: Optional[ActionType]         # e.g., CLOSE_VALVE, or None if global
    target: str                          # Physical target (e.g., 'valve_b')
    condition: Dict[str, Any]            # Trigger predicates (e.g., {'pump_p1': 'ACTIVE'})
    source_evidence_id: str              # Strict reference to KnowledgeEvidence ID
    confidence: float                    # Model extraction confidence [0.0, 1.0]
    created_at: float
    status: ConstraintStatus             # CANDIDATE, STRUCTURALLY_VALID, ADMISSIBLE, ACTIVE, REJECTED, CONFLICTED, STALE
    description: str                     # Human-readable rule text
    claim_text: Optional[str]            # Exact quoted text from evidence
    extraction_rationale: Optional[str]  # Model extraction rationale
    evidence_role: Optional[EvidenceRole]
    source_trust: Optional[SourceTrustAssessment]
    applicability: Applicability
    corroboration: CorroborationStatus
    support_certificate: Optional[ClaimSupportCertificate] = None  # Empirical provenance certificate (Phase 2C)
    grounding_status: Optional[str] = None                         # SUPPORTED, INSUFFICIENT, REJECTED
    support_type: Optional[str] = None                             # DIRECT, PARAPHRASE, INFERENCE, etc.
    admissibility_notes: List[str]
    validation_notes: List[str]
```

### Critical Separation of Semantics:
* `confidence`: Model extraction certainty from text.
* `grounding_status`: Empirical proof that source contains claim.
* `source_trust`: Deterministic evaluation of institutional authority.
* `applicability`: Alignment with physical plant equipment.
* `corroboration`: Multi-source independent verification.

---

## 4.5 Claim Grounding Models (Phase 2C)

Phase 2C bridges the gap between source existence and claim veracity.

### ClaimSupportCertificate
```python
class ClaimSupportCertificate(BaseModel):
    certificate_id: str                   # e.g., 'cert_ddd085128a'
    candidate_constraint_id: str          # Target CandidateConstraint ID
    source_evidence_id: str               # Referenced KnowledgeEvidence ID
    claim_text: str                       # Full text of the operational claim
    support_type: SupportType             # DIRECT, PARAPHRASE, INFERENCE, AMBIGUOUS, UNSUPPORTED, CONTRADICTED
    support_span: Optional[str]           # Supporting verbatim or normalized text span
    start_offset: Optional[int]           # Character start index in source evidence content
    end_offset: Optional[int]             # Character end index in source evidence content
    support_status: SupportStatus         # SUPPORTED, INSUFFICIENT, REJECTED
    model_confidence: float               # Model extraction confidence [0.0, 1.0]
    grounding_notes: str                  # Auditable deterministic grounding explanation
    rejection_reason: GroundingRejectionReason # NONE, CLAIM_DISTORTION, CLAIM_NEGATION_MISMATCH, etc.
    assertions: List[ClaimAssertion]      # Decomposed atomic assertions if compound claim
    created_at: float
```

### Enumerations:
* **`SupportType`**:
  - `DIRECT`: Explicit, substantial match in source text.
  - `PARAPHRASE`: Meaning and scope preserved without distortion.
  - `INFERENCE`: Unstated deduction, causal claim, or model commentary.
  - `AMBIGUOUS`: Vague, weak advice, or multi-interpretable statement.
  - `UNSUPPORTED`: Claim not present or ungrounded in cited evidence.
  - `CONTRADICTED`: Source explicitly asserts the opposite or claim is distorted.

* **`SupportStatus`**:
  - `SUPPORTED`: Authorized for admissibility evaluation.
  - `INSUFFICIENT`: Retained for operator explanation only; cannot activate policy.
  - `REJECTED`: Hard failure; distorted, contradicted, or ungrounded.

* **`GroundingRejectionReason`**:
  - `NONE`, `CLAIM_DISTORTION`, `CLAIM_NEGATION_MISMATCH`, `CLAIM_CONDITION_LOST`, `CLAIM_SCOPE_MISMATCH`, `INVENTED_NUMERIC_THRESHOLD`, `UNSUPPORTED_CLAIM`, `CONTRADICTORY_SOURCE`, `MISSING_EVIDENCE`, `UNVERIFIED_CAUSAL_INFERENCE`.

### ClaimAssertion
```python
class ClaimAssertion(BaseModel):
    assertion_text: str                   # Decomposed statement or clause
    support_type: SupportType
    support_status: SupportStatus
    support_span: Optional[str]
    start_offset: Optional[int]
    end_offset: Optional[int]
    notes: str
```

### Conflict Report:
```python
class ConstraintConflictReport(BaseModel):
    conflict: bool = True
    constraint_a_id: str
    constraint_b_id: str
    conflict_category: ConflictCategory  # SOURCE_CONFLICT, POLICY_CONFLICT, APPLICABILITY_CONFLICT, FRESHNESS_CONFLICT
    severity: str                        # 'LOW', 'MEDIUM', 'HIGH'
    details: str                         # Summary of mutual contradiction
    timestamp: float
```

---

## 5. Evidence (Sensor Telemetry)

Represents an individual physical observation with explicit provenance, confidence, and target mapping.

```python
class Evidence(BaseModel):
    id: str
    source: EvidenceSource  # VISION, PRESSURE_SENSOR, THERMAL_SENSOR, ACOUSTIC_SENSOR, HUMAN_OPERATOR
    target: str             # e.g., 'valve_b', 'manifold_line'
    observation: Dict[str, Any]
    confidence: float       # 0.00 to 1.00
    timestamp: float
    provenance: str         # Instrument ID or model version (e.g., 'camera_overhead:v1')
    metadata: Dict[str, Any]
```

### Contradiction Detection:
* [`ContradictionReport`](file:///Users/urjasoft/Documents/MotionFence/motionfence/evidence/models.py#L37):
  - `contradiction: bool`
  - `sources: List[str]`
  - `severity: ContradictionSeverity` (`NONE`, `LOW`, `MEDIUM`, `HIGH`)
  - `target: Optional[str]`
  - `details: str`

---

## 6. ActionProposal

An unprivileged suggestion generated by an AI reasoning agent (such as NVIDIA Nemotron).

```python
class ActionProposal(BaseModel):
    id: str
    action_type: ActionType  # INSPECT, GATHER_EVIDENCE, CLOSE_VALVE, OPEN_VALVE, ADJUST_COOLING
    target: str              # Actuator ID (e.g., 'valve_b')
    parameters: Dict[str, Any]
    rationale: str
    model_confidence: float  # 0.00 to 1.00
    supporting_evidence_ids: List[str]
    timestamp: float
```

---

## 7. Policy & PolicyDecision

The declarative specification of safety rules, physical invariants, active knowledge constraints, and the deterministic decision verdict.

### Policy Specification:
```python
class Policy(BaseModel):
    id: str = "policy_leak_isolation"
    name: str = "Leak Isolation and Safety Policy"
    objective: str
    min_target_confidence: float = 0.90
    require_human_zone_clear: bool = True
    require_cooling_active: bool = True
    prohibited_actions: List[ActionType] = [ActionType.ADJUST_COOLING]
    allowed_actuator_targets: List[str] = ["valve_a", "valve_b"]
    max_tolerated_contradiction: ContradictionSeverity = ContradictionSeverity.NONE
    expected_postconditions: Dict[str, Any]
    active_constraints: List[CandidateConstraint] = []
```

### Policy Decision:
```python
class PolicyDecision(BaseModel):
    decision: DecisionType  # ALLOW, DENY, NEED_MORE_EVIDENCE
    proposal_id: str
    target: str
    reasons: List[PolicyReason]
    contradiction_severity: ContradictionSeverity
    timestamp: float
```

---

## 8. AuthorizationTicket

A single-use, cryptographically signed permission token minted exclusively when the Policy Engine returns `ALLOW`.

```python
class AuthorizationTicket(BaseModel):
    ticket_id: str
    proposal_id: str
    action_type: ActionType
    target: str
    issued_at: float
    expires_at: float
    authorized_by: str
    signature: str        # HMAC-SHA256 signature
    consumed: bool = False
```

---

## 9. VerificationResult

An audit record produced after physical execution to confirm ground truth vs declared postconditions.

```python
class VerificationResult(BaseModel):
    action_id: str
    target: str
    action_occurred: bool
    expected_postconditions: Dict[str, Any]
    observed_postconditions: Dict[str, Any]
    status: VerificationStatus  # VERIFIED, VERIFICATION_FAILED
    discrepancies: List[str]
    timestamp: float
```

---

## 10. Runtime Observability Events

[`EventType`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/events.py#L10) captures complete lifecycle, trust, and model activity:

* `INTENT_RECEIVED`: Human operational intent registered.
* `KNOWLEDGE_QUERY_REQUESTED`: Knowledge retrieval initiated.
* `KNOWLEDGE_RESULT_RECEIVED`: Evidence received from knowledge provider.
* `KNOWLEDGE_RESULT_REJECTED`: Knowledge evidence rejected due to missing provenance.
* `SOURCE_ASSESSED`: Deterministic assessment of knowledge source category and authority.
* `EVIDENCE_CLASSIFIED`: Operational role assigned (`DISCOVERY`, `SUPPORTING`, `AUTHORIZATION_RELEVANT`).
* `EVIDENCE_CORROBORATED`: Claim corroborated by independent qualified sources.
* `EVIDENCE_INSUFFICIENT`: Weak/community source insufficient for authorization.
* `CONSTRAINT_EXTRACTED`: Constraint extracted from text by Nemotron or local extractor.
* `CONSTRAINT_CANDIDATE_CREATED`: Structured candidate constraint created.
* `CONSTRAINT_VALIDATED`: Candidate constraint passed structural schema check.
* `CONSTRAINT_ADMISSIBILITY_CHECKED`: Admissibility gate evaluated.
* `CONSTRAINT_ADMISSIBLE`: Constraint passed institutional authority and equipment applicability checks.
* `CONSTRAINT_NOT_ADMISSIBLE`: Constraint failed authority or applicability checks.
* `CONSTRAINT_ACTIVATED`: Candidate constraint promoted to active policy rule.
* `CONSTRAINT_STALE`: Constraint marked stale due to aged documentation.
* `CONSTRAINT_CONFLICT`: Mutual contradiction detected between constraints or base policy.
* `OBSERVATION_RECORDED`: Physical sensors observed and cataloged.
* `MODEL_REQUESTED`: Prompt dispatched to NVIDIA Nemotron on Nebius Token Factory.
* `MODEL_RESPONSE_RECEIVED`: Model response received with latency metrics.
* `MODEL_RESPONSE_REJECTED`: Model output rejected due to invalid schema or unknown evidence citations.
* `MODEL_PROVIDER_ERROR`: Network timeout, authentication failure, or provider exception.
* `ACTION_PROPOSAL_VALIDATED`: Model proposal validated into typed domain object.
* `ACTION_PROPOSED`: Action proposed to the runtime.
* `POLICY_EVALUATED`: Deterministic policy evaluation completed.
* `ACTION_DENIED`: Action blocked by hard invariant or knowledge prohibition.
* `MORE_EVIDENCE_REQUIRED`: Action deferred pending targeted multi-modal evidence or recertification.
* `ACTION_AUTHORIZED`: Ticket minted for verified proposal.
* `ACTION_EXECUTED`: Actuator completed command dispatch.
* `POSTCONDITION_VERIFIED`: Post-actuation physical state matches required invariants.
* `POSTCONDITION_FAILED`: Postcondition discrepancy detected in ground-truth reality.
* `DECISION_CREATED`: DecisionRecord initialized for cycle.
* `DECISION_FINALIZED`: DecisionRecord completed and marked immutable.
* `DECISION_HASHED`: Cryptographic canonical SHA-256 hash computed.
* `DECISION_REPLAYED`: Offline deterministic replay executed.
* `REPLAY_MATCH`: Replayed policy evaluation matches recorded verdict.
* `REPLAY_DIVERGENCE`: Replayed policy evaluation diverges from recorded verdict.
* `INTEGRITY_FAILURE`: DecisionRecord hash or historical chain linkage invalid.
* `ENCLAVE_AUTHORIZATION_REQUESTED`: Enclave received authorization request.
* `ENCLAVE_AUTHORIZATION_GRANTED`: Safety Enclave validated invariants and minted ticket.
* `ENCLAVE_AUTHORIZATION_DENIED`: Safety Enclave denied authorization.

---

## 11. Decision Records, Replay Models & Safety Enclave (Phase 2D)

Phase 2D establishes complete provenance capture, tamper-evident audit chains, offline deterministic replay, and isolated Safety Enclave authorization.

### 11.1 DecisionRecord
```python
class DecisionRecord(BaseModel):
    decision_id: str                      # e.g., 'dec_1723857735fc'
    created_at: float                     # Timestamp of cycle initiation
    finalized_at: Optional[float]         # Timestamp of finalization
    sequence_number: int                  # Monotonically increasing chain index
    previous_record_hash: str             # Parent record SHA-256 (or 'GENESIS')
    record_hash: str                      # SHA-256(canonical_bytes + previous_hash)
    intent: str                           # Operator human intent
    world_state_snapshot: WorldState      # Ground-truth physical environment snapshot
    sensor_evidence_ids: List[str]        # Physical sensor observations
    knowledge_evidence_ids: List[str]     # Retrieved documentation IDs
    source_assessment_ids: List[str]      # Source trust assessment IDs
    claim_support_certificate_ids: List[str] # Empirical grounding certificate IDs
    candidate_constraint_ids: List[str]   # Extracted constraint IDs
    active_constraint_ids: List[str]      # Grounded, admissible constraints evaluated by policy
    action_proposal: Optional[ActionProposal] # Proposed action
    policy_decision: Optional[DecisionType] # ALLOW, DENY, NEED_MORE_EVIDENCE
    decision_category: DecisionCategory   # Explicit outcome category
    policy_reasons: List[str]             # Explanatory rationale
    authorization_ticket_id: Optional[str] # Single-use ticket ID (if ALLOW)
    execution_result: Optional[ExecutionResult] # Actuator dispatch outcome
    verification_result: Optional[VerificationResult] # Ground-truth postcondition result
    runtime_version: str = "0.4.0"        # MotionFence runtime version
    policy_version: str = "2026.1"        # Evaluated policy ruleset version
    schema_version: str = "1.0.0"         # Audit schema specification version
    provider_metadata: Dict[str, Any]     # LLM provider, model, latency, safe token counts
    execution_mode: ExecutionMode         # LIVE, REPLAY, FIXTURE
    source_mode: SourceMode               # LIVE_MODEL_RESPONSE, LOCAL_CACHE_REPLAY, etc.
    is_finalized: bool                    # Immutable freeze flag
```

### 11.2 Decision Categories & Execution Modes
* **`DecisionCategory`**: `ALLOW`, `DENY`, `NEED_MORE_EVIDENCE`, `EXECUTION_FAILED`, `VERIFICATION_FAILED`.
* **`ExecutionMode`**: `LIVE`, `REPLAY`, `FIXTURE`.
* **`SourceMode`**: `LIVE_MODEL_RESPONSE`, `LIVE_TAVILY_RESPONSE`, `LOCAL_FIXTURE`, `LOCAL_CACHE_REPLAY`.

### 11.3 Safety Enclave Models
```python
class EnclaveAuthorizationRequest(BaseModel):
    proposal: ActionProposal
    world_state: WorldState
    active_constraints: List[CandidateConstraint]
    policy_decision: PolicyDecision
    correlation_id: str

class EnclaveAuthorizationResult(BaseModel):
    authorized: bool
    ticket: Optional[AuthorizationTicket]
    reasons: List[str]
    enclave_timestamp: float
```


---

## 12. Bounded Assurance & Adversarial Evaluation Models (Phase 2E)

Phase 2E establishes bounded SMT invariant analysis (via Z3), bounded temporal transition checking, and automated property-based adversarial falsification.

### 12.1 FormalState
Minimal, machine-checkable formal abstraction of the physical world state:
```python
class FormalState(BaseModel):
    valve_b_open: bool = True
    pump_active: bool = False
    cooling_active: bool = True
    human_zone_occupied: bool = False
    leak_present: bool = False
    timestamp: float = 0.0

    @classmethod
    def from_world_state(cls, ws: WorldState) -> "FormalState": ...
    def to_world_state(self) -> WorldState: ...
```

### 12.2 AssuranceFinding
Result of an invariant or temporal property verification:
```python
class AssuranceFinding(BaseModel):
    finding_id: str
    property_id: str
    property_name: str
    status: FindingStatus          # SATISFIED, VIOLATED, UNKNOWN, NOT_APPLICABLE
    severity: FindingSeverity      # INFO, LOW, MEDIUM, HIGH, CRITICAL
    scope: AssuranceScope          # STATIC_INVARIANT, BOUNDED_TRANSITION, TEMPORAL_SEQUENCE, POLICY_BOUNDARY
    observed_state: Dict[str, Any]
    counterexample: Optional[Dict[str, Any]] = None
    explanation: str
    created_at: float
```

### 12.3 Adversarial Evaluation Models
```python
class AdversarialCaseResult(BaseModel):
    case_id: str
    scenario_type: str             # e.g., 'boundary_fuzzing', 'contradiction', 'knowledge_adversary'
    outcome_category: AdversarialOutcomeCategory # UNSAFE_ALLOW, UNEXPECTED_DENY, etc.
    is_unsafe_failure: bool        # True if FALSE ALLOW detected
    proposal_action: str
    proposal_target: str
    model_confidence: float
    formal_state: FormalState
    policy_decision: Optional[str]
    reasons: List[str]
    shrink_steps: int = 0
    timestamp: float

class AssuranceReport(BaseModel):
    report_id: str
    run_timestamp: float
    execution_time_seconds: float
    seed: Optional[int] = None
    runtime_version: str = "0.5.0"
    policy_version: str = "2026.1"
    properties_checked: int = 0
    properties_satisfied: int = 0
    properties_violated: int = 0
    unknown_properties: int = 0
    findings: List[AssuranceFinding] = []
    counterexamples: List[Dict[str, Any]] = []
    adversarial_cases_generated: int = 0
    adversarial_failures: int = 0
    outcome_counts: Dict[str, int] = {}
    adversarial_cases: List[AdversarialCaseResult] = []


---

## 13. State-Bound Authorization & TOCTOU Defense Models (Phase 2F)

Phase 2F models the deterministic binding between authorization decisions and physical/environmental contexts to prevent Time-of-Check vs Time-of-Use (**TOCTOU**) races.

### 13.1 AuthorizationContext
Represents the deterministic snapshot of the full authorization environment at ticket issuance:
```python
class AuthorizationContext(BaseModel):
    context_id: str = Field(default_factory=lambda: f"ctx_{uuid.uuid4().hex[:12]}")
    proposal_id: str                      # ID of the authorized ActionProposal
    action_type: ActionType               # Authorized action type
    target: str                           # Authorized target
    world_state_version: int              # Monotonic world state version at authorization
    world_state_hash: str                 # SHA-256 of canonical world state at authorization
    policy_version: str                   # Policy version string at authorization
    constraint_set_hash: str              # SHA-256 of canonical active constraint set
    evidence_context_hash: str            # SHA-256 of canonical safety-relevant evidence
    created_at: float = Field(default_factory=time.time)
```

### 13.2 AuthorizationRevalidationResult
Typed outcome of the deterministic pre-actuation revalidation check:
```python
class RevalidationStatus(str, Enum):
    VALID = "VALID"                       # Context intact; actuation permitted
    STALE = "STALE"                       # Generic context expiration
    WORLD_STATE_CHANGED = "WORLD_STATE_CHANGED" # Physical world drifted (human, pump, cooling, etc.)
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED" # Supporting sensor evidence invalidated or changed
    POLICY_CHANGED = "POLICY_CHANGED"     # Active policy version modified
    CONSTRAINT_CHANGED = "CONSTRAINT_CHANGED" # Active constraint set modified
    TICKET_EXPIRED = "TICKET_EXPIRED"     # TTL exceeded
    TARGET_MISMATCH = "TARGET_MISMATCH"   # Commanded target diverged from ticket
    ACTION_MISMATCH = "ACTION_MISMATCH"   # Commanded action type diverged from ticket
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH" # Canonical context hash mismatch

class AuthorizationRevalidationResult(BaseModel):
    status: RevalidationStatus
    reasons: List[str]
    expected_context_hash: str
    observed_context_hash: str
    expected_world_version: int
    observed_world_version: int
    timestamp: float
```

### 13.3 State-Bound AuthorizationTicket (Phase 2F Extensions)
The `AuthorizationTicket` encapsulates cryptographic context bindings:
```python
class AuthorizationTicket(BaseModel):
    ticket_id: str
    proposal_id: str
    action_type: ActionType
    target: str
    issued_at: float
    expires_at: float
    authorized_by: str
    signature: str                        # HMAC-SHA256 signature
    consumed: bool = False                # Single-use enforcement
    # Phase 2F state-binding fields
    authorization_context_hash: str       # SHA-256 digest of AuthorizationContext
    world_state_version: int              # Monotonic plant state version at minting
    world_state_hash: str                 # SHA-256 of canonical physical state at minting
    policy_version: str                   # Active policy version string
    constraint_set_hash: str              # Active constraint set digest
    evidence_context_hash: str            # Active sensor evidence digest
    nonce: str                            # Single-use random nonce
```

---

## 14. Active Evidence Acquisition & Capability Models (Phase 2G)

Phase 2G models deterministic capability policies and typed information-gathering actions for autonomous uncertainty recovery.

### 14.1 ActionClass & Action Classification
```python
class ActionClass(str, Enum):
    INFORMATION_ACTION = "INFORMATION_ACTION"     # Perception / evidence gathering only
    CONSEQUENTIAL_ACTION = "CONSEQUENTIAL_ACTION" # Physical plant actuator mutation

# INFORMATION_ACTIONS:
# INSPECT_TARGET, RESAMPLE_SENSOR, CHANGE_VIEWPOINT,
# READ_SENSOR, WAIT_FOR_STABLE_STATE, QUERY_KNOWLEDGE

# CONSEQUENTIAL_ACTIONS:
# CLOSE_VALVE, OPEN_VALVE, START_PUMP, STOP_PUMP
```

### 14.2 CapabilityPolicy
```python
class CapabilityType(str, Enum):
    OBSERVE = "OBSERVE"
    INSPECT = "INSPECT"
    READ_SENSOR = "READ_SENSOR"
    QUERY_KNOWLEDGE = "QUERY_KNOWLEDGE"
    REORIENT_SENSOR = "REORIENT_SENSOR"
    ACTUATE = "ACTUATE"                           # Consequential physical actuation

class CapabilityPolicy(BaseModel):
    policy_id: str
    name: str
    allowed_capabilities: Set[CapabilityType]
    prohibited_capabilities: Set[CapabilityType]
    max_rate_per_cycle: int = 10
    allow_consequential_actuation: bool = False
```

### 14.3 InformationAction & InformationActionResult
```python
class InformationGainLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class InformationAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"info_{uuid.uuid4().hex[:8]}")
    action_type: ActionType                       # Must be an INFORMATION_ACTION
    target: str
    reason: str
    expected_evidence: List[str]
    confidence: float = 0.90
    predicted_information_gain: InformationGainLevel = InformationGainLevel.MEDIUM
    parameters: Dict[str, Any] = {}
    created_at: float = Field(default_factory=time.time)

class InformationActionResult(BaseModel):
    action_id: str
    success: bool
    action_type: ActionType
    target: str
    observation: Optional[SensorObservation] = None
    observed_information_gain: InformationGainLevel = InformationGainLevel.LOW
    message: str = ""
    timestamp: float = Field(default_factory=time.time)
```

### 14.4 EvidenceAcquisitionPlan
```python
class EvidenceAcquisitionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    action: ActionType                            # Validated strictly as INFORMATION_ACTION
    target: str
    reason: str
    expected_evidence: List[str]
    confidence: float
    predicted_information_gain: InformationGainLevel = InformationGainLevel.MEDIUM
    parameters: Dict[str, Any] = {}
```

### 14.5 DecisionRecord Phase 2G Extensions
The immutable `DecisionRecord` records all active evidence gathering provenance:
```python
class DecisionRecord(BaseModel):
    # Core Phase 2D fields ...
    # Phase 2G Active Evidence fields:
    evidence_action_ids: List[str] = []
    evidence_acquisition_iterations: int = 0
    evidence_budget: int = 0
    predicted_information_gain: Optional[str] = None
    observed_information_gain: Optional[str] = None
```


