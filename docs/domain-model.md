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
    admissibility_notes: List[str]
    validation_notes: List[str]
```

### Critical Separation of Semantics:
* `confidence`: Model extraction certainty from text.
* `source_trust`: Deterministic evaluation of institutional authority.
* `applicability`: Alignment with physical plant equipment.
* `corroboration`: Multi-source independent verification.

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

