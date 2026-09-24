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

## 3. Candidate Constraints & Conflicts (Phase 2A)

Structured operational rules extracted from knowledge evidence.

```python
class CandidateConstraint(BaseModel):
    constraint_id: str
    constraint_type: ConstraintType      # PROHIBITION, REQUIREMENT, PRECONDITION, POSTCONDITION, INFORMATIONAL
    action: Optional[ActionType]         # e.g., CLOSE_VALVE, or None if global
    target: str                          # Physical target (e.g., 'valve_b')
    condition: Dict[str, Any]            # Trigger predicates (e.g., {'pump_p1': 'ACTIVE'})
    source_evidence_id: str              # Strict reference to KnowledgeEvidence ID
    confidence: float                    # Extraction confidence [0.0, 1.0]
    created_at: float
    status: ConstraintStatus             # CANDIDATE, VALIDATED, REJECTED, ACTIVE, CONFLICTED, STALE
    description: str                     # Human-readable rule text
    validation_notes: List[str]          # Audit notes from validator
```

### Conflict Report:
```python
class ConstraintConflictReport(BaseModel):
    conflict: bool = True
    constraint_a_id: str
    constraint_b_id: str
    severity: str                        # 'LOW', 'MEDIUM', 'HIGH'
    details: str                         # Summary of mutual contradiction
    timestamp: float
```

---

## 4. Evidence (Sensor Telemetry)

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

## 5. ActionProposal

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

## 6. Policy & PolicyDecision

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

## 7. AuthorizationTicket

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

## 8. VerificationResult

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

## 9. Runtime Observability Events

[`EventType`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/events.py#L10) captures lifecycle and model activity:

* `INTENT_RECEIVED`: Human operational intent registered.
* `KNOWLEDGE_QUERY_REQUESTED`: Knowledge retrieval initiated.
* `KNOWLEDGE_RESULT_RECEIVED`: Evidence received from knowledge provider.
* `KNOWLEDGE_RESULT_REJECTED`: Knowledge evidence rejected due to missing provenance.
* `CONSTRAINT_CANDIDATE_CREATED`: Structured constraint extracted from text.
* `CONSTRAINT_VALIDATED`: Candidate constraint passed structural and provenance validation.
* `CONSTRAINT_REJECTED`: Candidate constraint rejected (e.g. unknown evidence reference).
* `CONSTRAINT_ACTIVATED`: Candidate constraint promoted to active policy rule.
* `CONSTRAINT_STALE`: Constraint marked stale due to aged documentation.
* `CONSTRAINT_CONFLICT`: Mutual contradiction detected between constraints.
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
