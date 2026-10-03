# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-441%20passed-brightgreen.svg)](tests/)
[![Z3 Assurance](https://img.shields.io/badge/Z3%20Assurance-56%20properties-blueviolet.svg)](tests/)
[![Console](https://img.shields.io/badge/Judge%20Console-React%20%2B%20Vite-orange.svg)](console/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory%20API-purple.svg)](https://tokenfactory.nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron--3--Super--120B-76B900.svg)](https://build.nvidia.com)
[![USGS OGC API](https://img.shields.io/badge/USGS-Water%20Data%20OGC%20API-003366.svg)](https://api.waterdata.usgs.gov/ogcapi/v1/)
[![Tavily Search](https://img.shields.io/badge/Tavily-Search%20API-blue.svg)](https://tavily.com)


Built for the **Nebius x NVIDIA Global AI Hackathon 2026** (Physical AI Track).

---

## 1. What is MotionFence?

**MotionFence** is an independent, deterministic runtime authorization gateway governing AI-driven embodied agents and physical systems.

In MotionFence, an AI agent proposes what physical actions should happen, but a deterministic, rule-based runtime engine independently decides whether each physical action is **allowed**, **denied**, or **requires additional evidence** before any physical actuator can move.

### Product Thesis
> **SOURCE EXISTS ≠ SOURCE IS TRUSTWORTHY ≠ CLAIM IS PRESENT IN SOURCE ≠ CLAIM IS DIRECTLY SUPPORTED ≠ CLAIM IS APPLICABLE ≠ CLAIM IS SUFFICIENT FOR AUTHORIZATION**
>
> A model citing a real source does not prove that the extracted claim is actually supported by that source. MotionFence cross-checks empirical evidence, grounds claims deterministically via `ClaimSupportCertificate`, evaluates institutional source trust and equipment applicability, and authorizes physical actions only when policy requirements are strictly satisfied.

*Disclaimer: MotionFence is an architectural research prototype developed for the Nebius x NVIDIA AI Hackathon, not an industrially certified safety-critical SIL-4 controller. It does not claim formal certification or regulatory compliance.*

---

## 2. Why Does It Exist?

Autonomous reasoning models (such as LLMs and vision-language-action models) excel at high-level reasoning and perceptual synthesis, but they are inherently probabilistic. In physical and industrial environments, probabilistic execution is dangerous:

* Visual ambiguity can lead a model to actuate the wrong valve or switch.
* Sensor noise or lens flare can trigger ungrounded emergency procedures.
* Prompt injections or agent delusions can bypass basic prompt-level safety instructions.
* External web search (e.g. Tavily) returns heterogeneous sources: OEM manuals, technical papers, forum threads, and mirrors.
* Models hallucinate causal explanations, broaden equipment scope (e.g. "Valve B" → "all valves"), drop critical conditions, or reverse modal polarity ("may" → "must not").
* Structural validity and provenance do not prove that retrieved knowledge is authoritative or that an extracted claim is supported.

### Critical Architectural Invariants
1. **Model extraction possesses ZERO authority**: Neither Nemotron nor external tools can activate constraints or mint tickets.
2. **Claim Grounding is deterministic**: Modality, negations, conditions, scopes, and numeric thresholds are strictly verified against source spans.
3. **Inference ≠ Fact**: Causal statements not explicitly in source are classified as `INFERENCE` / `INSUFFICIENT` and cannot become active policy facts.
4. **Actuator isolation remains absolute**: Actuators require single-use HMAC-SHA256 signed `AuthorizationTicket` minted strictly by `PolicyEngine`.

---

## 3. The Core Control Loop

```text
Knowledge Evidence (Tavily / Local OEM / Plant Manuals)
      ↓
Source Assessment (Category: OEM, Standards, Community, Unknown)
      ↓
Nemotron Claim Extraction (Structured CandidateConstraint)
      ↓
Claim Grounding (LocalDeterministicClaimGrounder → ClaimSupportCertificate)
      ↓
Admissibility Gate (Authority, Corroboration, Equipment Applicability)
      ↓
Deterministic Validation (Schema, References, Freshness)
      ↓
ACTIVE POLICY CONSTRAINT (or Retained Discovery / Inadmissible)
      ↓
Nemotron Action Proposal (Unprivileged)
      ↓
Deterministic PolicyEngine (LLM-Free Gating)
      │
  ┌───┴───────────────┬──────────────────┐
  ▼                   ▼                  ▼
ALLOW               DENY           NEED_MORE_EVIDENCE
  │
  ▼
AuthorizationTicket (HMAC-SHA256 Signed, Single-Use)
  │
  ▼
Physical Actuator Execution
  │
  ▼
Independent Post-Action Verification
```

---

## 4. Evidence Trust & Constraint Admissibility (Phase 2B)

### 4.1 Distinction Between Constraint States
* **`CANDIDATE`**: Newly extracted rule; unvalidated.
* **`STRUCTURALLY_VALID`**: Schema is well-formed and cites existing, registered evidence.
* **`ADMISSIBLE`**: Sourced from sufficiently authoritative origin, applicable to target equipment, fresh, corroborated where needed, and empirically grounded.
* **`ACTIVE`**: Evaluated by deterministic PolicyEngine during physical authorization decisions.
* **`REJECTED` / `CONFLICTED` / `STALE`**: Inadmissible due to invalid schema, contradictions, or expired freshness.

---

## 5. Claim Grounding & Decision Integrity (Phase 2C)

Phase 2C guarantees that extracted claims are verified against raw source text before admissibility evaluation.

### 5.1 Claim Support Certificate
Every candidate constraint receives a cryptographically auditable `ClaimSupportCertificate`:
* `certificate_id`: Unique identifier (e.g. `cert_ddd085128a`).
* `candidate_constraint_id`: Target candidate constraint ID.
* `source_evidence_id`: Exact ID of referenced KnowledgeEvidence.
* `claim_text`: Extracted operational claim text.
* `support_type`: `DIRECT`, `PARAPHRASE`, `INFERENCE`, `AMBIGUOUS`, `UNSUPPORTED`, `CONTRADICTED`.
* `support_status`: `SUPPORTED`, `INSUFFICIENT`, `REJECTED`.
* `support_span`, `start_offset`, `end_offset`: Exact or normalized source span.
* `model_confidence`: Extractor confidence (strictly isolated from grounding status).
* `assertions`: Decomposed atomic assertions for compound claims.

### 5.2 Grounding Defense Rules
1. **Direct Support Requirement**: Safety-critical prohibitions must have explicit support in source.
2. **Causal Decomposition**: If source states *"Valve B must not be closed while Pump P1 is active"* and model adds *"because closing it causes hydraulic shock"*, Assertion A is `SUPPORTED` but Assertion B is `INFERENCE`. The ungrounded causal rationale cannot become an active policy fact.
3. **Negation Safety**: Modal reversals (`may` → `must not`, `permitted` → `forbidden`) are flagged as `CONTRADICTED` / `CLAIM_NEGATION_MISMATCH`.
4. **Conditionality Preservation**: Dropping operating conditions (`while Pump P1 is active` → `never`) is rejected as `CLAIM_CONDITION_LOST`.
5. **Scope Preservation**: Generalizing equipment (`Valve B` → `all valves`) is rejected as `CLAIM_SCOPE_MISMATCH`.
6. **Numeric Threshold Integrity**: Invented or altered numbers (e.g. `50 psi` → `80 psi`) are rejected as `INVENTED_NUMERIC_THRESHOLD`.


### 4.2 Source Categories & Evidence Roles
* **`FIRST_PARTY_OFFICIAL`** / **`MANUFACTURER_DOCUMENTATION`** / **`REGULATORY_OR_STANDARDS`**:
  - Assigned role: `AUTHORIZATION_RELEVANT`
  - High authority; qualified to independently establish safety prohibitions.
* **`GENERAL_TECHNICAL_SOURCE`**:
  - Assigned role: `SUPPORTING`
  - Medium authority; requires independent multi-source corroboration before activating safety prohibitions.
* **`COMMUNITY_OR_USER_CONTENT`** (e.g. Reddit, Scribd, Facebook, forum posts):
  - Assigned role: `DISCOVERY`
  - Low authority; preserved for auditability and operator awareness, but **cannot independently activate safety prohibitions**.
* **`UNKNOWN`**:
  - Unverifiable domain; discovery only.

### 4.3 Multi-Source Corroboration & Deduplication
`CorroborationEngine` determines whether operational claims are independently supported:
* If OEM manual + ASME standards independently support a rule: **`CORROBORATED`** -> Admissible.
* If multiple web citations contain near-duplicate/scraped mirror text (evaluated via Jaccard text similarity >= 0.85): **`DUPLICATE_SOURCE`** -> Rejected as independent corroboration.

### 4.4 Plant Context & Applicability
Constraints are checked against `PlantContext` (`plant_profile`, `equipment_type`, `equipment_model`, `equipment_id`, `operating_mode`, `authorized_targets`):
* **`DIRECT`**: Matches equipment ID and model.
* **`PARTIAL`**: Generic guidance for equipment class without model match.
* **`MISMATCH`**: Foreign equipment model (e.g., Slurry Pump P200 vs Plant Centrifugal P100) or unauthorized target. Mismatch is strictly inadmissible.
* **`UNKNOWN`**: Context cannot be confirmed; cannot activate safety constraints.

### 4.5 NVIDIA Nemotron Constraint Extractor
[`NemotronConstraintExtractor`](file:///Users/urjasoft/Documents/MotionFence/motionfence/constraints/nemotron_extractor.py) connects to Nebius Token Factory (`nvidia/nemotron-3-super-120b-a12b`):
* Interprets evidence and outputs structured JSON conforming to `NemotronExtractedItem`.
* Decouples `model_confidence` from `source_trust` and `applicability`.
* Strictly validates cited evidence IDs against the registered evidence pool. Any hallucinated ID is discarded.
* Zero actuation authority: Nemotron cannot activate constraints, mint tickets, or execute actions.

---

## 6. Decision Records, Deterministic Replay & Safety Enclave (Phase 2D)

Phase 2D makes every consequential MotionFence physical decision explainable, replayable, tamper-evident, provenance-complete, and independently verifiable offline without re-running models.

### 6.1 Core Decision Chain
Every physical action decision reconstructs the complete chain:
```text
Human Intent
    ↓
World Observation
    ↓
Knowledge Evidence
    ↓
Source Assessment
    ↓
Claim Extraction
    ↓
Claim Grounding (ClaimSupportCertificate)
    ↓
Constraint Admissibility
    ↓
Action Proposal
    ↓
Deterministic Policy Evaluation
    ↓
SAFETY ENCLAVE Authorization (HMAC-SHA256 AuthorizationTicket)
    ↓
Physical Execution
    ↓
Postcondition Verification
```

### 6.2 DecisionRecord & Canonical Serialization
Every cycle creates an immutable, typed `DecisionRecord`:
* **Provenance snapshot**: Stores `decision_id`, `created_at`, `intent`, `world_state_snapshot`, referenced sensor/evidence IDs, certificates, and constraints.
* **Deterministic outcomes**: Categorized as `ALLOW`, `DENY`, `NEED_MORE_EVIDENCE`, `EXECUTION_FAILED`, or `VERIFICATION_FAILED`.
* **Zero secrets**: No API keys, credentials, or transient auth tokens are ever persisted.
* **Canonical hashing**: Strict lexicographical sorting, whitespace elimination, float normalization, and SHA-256 hashing ensure `same logical decision → same canonical bytes → same hash`.
* **Hash-linked chain**: Each record binds to `previous_record_hash`. Historical tampering breaks chain integrity.

### 6.3 Safety Enclave
* The `SafetyEnclave` ([`motionfence/runtime/enclave.py`](file:///Users/urjasoft/Documents/MotionFence/motionfence/runtime/enclave.py)) defines a strict boundary around physical authorization.
* Encapsulates `TicketAuthority`: **Only** the Safety Enclave may mint `AuthorizationTicket`.
* Contains zero LLMs, zero Tavily calls, zero web retrieval, and zero natural language parsing.

### 6.4 Deterministic Replay Engine
* The `DecisionReplayEngine` ([`motionfence/audit/replay.py`](file:///Users/urjasoft/Documents/MotionFence/motionfence/audit/replay.py)) reconstructs all 10 decision lifecycle steps offline.
* **Critical replay invariants**:
  1. Replay can mutate WorldState: **NO**
  2. Replay can mint AuthorizationTicket: **NO**
  3. Replay can call real actuator: **NO**
  4. Replay can call Tavily or Nemotron: **NO**
* Validates recorded vs replayed policy evaluation (`REPLAY_MATCH` vs `REPLAY_DIVERGENCE`).

---

## 7. Bounded Assurance & Adversarial Evaluation (Phase 2E)

Phase 2E turns MotionFence safety assertions into machine-checkable assurance evidence, bounded formal analysis, and property-based adversarial falsification.

### 7.1 Important Assurance Boundary & Scope
> **BOUNDED PROPERTY SATISFIED ≠ REAL-WORLD SAFETY PROVEN**
>
> SMT/Z3 mathematical proofs and bounded invariant checks apply strictly to the modeled state variables, bounded execution horizons, and deterministic transition specifications represented in MotionFence. They do not constitute formal proofs of physical-world safety or formal SIL-4 hardware certification.

### 7.2 Two Complementary Analysis Mechanisms
1. **Bounded Formal Analysis (`motionfence/assurance/checker.py`)**:
   - Leverages the **Z3 SMT Solver** to evaluate safety invariants over symbolic state spaces.
   - Strictly isolated to the assurance analysis package; Z3 never participates in real-time runtime authorization.
   - When a property is violated, extracts a concrete, human-readable counterexample and minimizes it to root-cause variables.
2. **Automated Adversarial Falsification (`motionfence/assurance/adversarial.py`, `evaluator.py`)**:
   - Combinatorial property-based fuzzing targeting exact confidence boundaries (`0.89`, `0.899`, `0.90`, `0.901`).
   - Generates multi-sensor contradictory evidence pairs to verify deterministic gating.
   - Injects distorted claims (dropped conditions, inverted modal polarity, broadened equipment scope, fabricated numbers) to test claim grounding.
   - Tests source-trust attacks (Reddit/forum posts, duplicate scraped mirrors, foreign pump manuals, stale bulletins).
   - Prioritizes discovering critical `FALSE_ALLOW` hazards over false rejections.

---

---

## 8. State-Bound Authorization, TOCTOU Defense & Execution-Time Revalidation (Phase 2F)

Phase 2F resolves the fundamental Time-of-Check vs Time-of-Use (**TOCTOU**) vulnerability in physical actuation:

> **Authorization is state-bound and expires when its safety context changes.**
>
> A decision that was safe when authorized is not guaranteed to remain safe when executed if the physical world, evidence context, policy, or constraint set drifts between authorization and execution.

### 8.1 Conceptual Pipeline
```text
Policy ALLOW
    ↓
State-Bound AuthorizationTicket (HMAC-SHA256, Nonce, Monotonic Version, Context Hash)
    ↓
Execution-Time Revalidation Gate (Deterministic, Locally Decidable, <1ms, 0 Model Calls)
    ↓
Physical Actuator Execution (ONLY if Authorization Context Remains 100% Valid)
```

### 8.2 The TOCTOU Threat Model
MotionFence explicitly models and deterministically defends against 6 drift vectors:
1. **World-State Drift**: Safety-relevant physical state changes (e.g. Human enters restricted zone, cooling stops, pump starts) between policy evaluation and actuator movement.
2. **Policy Drift**: Active policy version changes (e.g. Emergency shutdown rule deployed) after ticket issuance.
3. **Constraint Drift**: Active constraint set hash changes (e.g. New prohibition introduced).
4. **Evidence Drift**: Sensor evidence changes or contradicts the original authorization basis.
5. **Target / Action Tampering**: Post-authorization tampering with target actuator or commanded motion.
6. **Ticket Replay Across Contexts**: Using an otherwise valid cryptographic ticket after world state has advanced.

### 8.3 Technical Implementation
* **Monotonic World Versioning**: `world_state.version` increments strictly monotonically on every physical transition.
* **Deterministic Canonical State Hashing**: `compute_world_state_hash()` generates a SHA-256 digest over normalized, canonical JSON of all safety-relevant state fields.
* **`AuthorizationContext`**: Encapsulates `(proposal_id, action_type, target, world_state_version, world_state_hash, policy_version, constraint_set_hash, evidence_context_hash)`.
* **`ExecutionTimeRevalidator`**: Purely static, deterministic pre-actuation gate. Produces typed `AuthorizationRevalidationResult` (`VALID`, `STALE`, `WORLD_STATE_CHANGED`, `EVIDENCE_CHANGED`, `POLICY_CHANGED`, `CONSTRAINT_CHANGED`, `TICKET_EXPIRED`, `TARGET_MISMATCH`, `ACTION_MISMATCH`, `CONTEXT_MISMATCH`).
* **Offline Deterministic Replay**: Reconstructs TOCTOU divergence offline (e.g. Issuance at v42 vs execution at v43) and identifies `TICKET_REVALIDATION_FAILED` with zero model or actuator calls.
* **Bounded SMT Invariants (Z3)**: Extended registry to 11 formal properties, adding `PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT`, `PROP_009_POLICY_VERSION_BINDING`, `PROP_010_CONSTRAINT_SET_BINDING`, and `PROP_011_EXECUTION_TIME_VALIDITY`.

---

## 9. Adversarial Physical Environment & Scenario Evaluation Engine (Phase 2H)

Phase 2H turns adversarial evaluation from model-centric perturbations to **physical-world disturbances**:

> **Create an adversarial physical-environment engine that actively attempts to make MotionFence fail, while preserving the complete deterministic authority boundary.**

### 9.1 The Adversarial World Thesis
Rather than assuming perceptual fidelity, Phase 2H introduces an autonomous disturbance generator:
```text
AI uncertainty + Adversarial environment + Sensor faults + State drift + Actuator faults + Knowledge faults
                                                    ↓
                                               MotionFence
                                                    ↓
                                         Recover / Refuse / Act
                                                    ↓
                                               Verification
```

### 9.2 Typed Fault Taxonomy & Scheduling
* **Human Faults**: `HUMAN_ENTERS_ZONE`, `HUMAN_LEAVES_ZONE`, `HUMAN_MOVEMENT_DURING_EXECUTION`.
* **Equipment Faults**: `PUMP_STARTS_UNEXPECTEDLY`, `PUMP_STOPS_UNEXPECTEDLY`, `VALVE_JAM`, `VALVE_PARTIAL_MOVE`, `COOLING_DEGRADES`.
* **Sensor Faults**: `SENSOR_NOISE`, `SENSOR_STUCK`, `SENSOR_DROPOUT`, `SENSOR_BIAS`, `SENSOR_CONTRADICTION`.
* **Perception Faults**: `TARGET_OCCLUDED`, `TARGET_AMBIGUITY_INCREASES`, `OBJECT_APPEARANCE_CHANGE`, `VIEWPOINT_LOSS`.
* **Knowledge Faults**: `KNOWLEDGE_STALE`, `KNOWLEDGE_CONFLICT`, `SOURCE_DISAPPEARS`, `SOURCE_CONTENT_CHANGES`.
* **Timing Faults**: `STATE_CHANGE_AFTER_OBSERVATION`, `STATE_CHANGE_AFTER_POLICY`, `STATE_CHANGE_AFTER_TICKET`, `STATE_CHANGE_BEFORE_EXECUTION`.
* **Actuator Faults**: `ACTUATOR_NO_OP`, `ACTUATOR_PARTIAL`, `ACTUATOR_DELAY`, `ACTUATOR_WRONG_STATE`, `ACTUATOR_JAM`.

### 9.3 Standard Scenario Corpus (Scenarios A through L)
* **Scenario A**: Human enters zone immediately after ticket issuance (TOCTOU race).
* **Scenario B**: Auxiliary pump activates unexpectedly after policy evaluation.
* **Scenario C**: Cooling degrades to INACTIVE during active evidence acquisition.
* **Scenario D**: Pressure transducer is stuck at nominal reading despite active leak.
* **Scenario E**: Vision sensor and pressure sensor contradict on pipe state.
* **Scenario F**: Target optical path is occluded by steam obscuration.
* **Scenario G**: Actuator solenoid experiences mechanical jam.
* **Scenario H**: Valve stops halfway in TRANSITIONING state.
* **Scenario I**: Operational knowledge becomes stale after ticket issuance.
* **Scenario J**: Global safety policy version shifts prior to execution.
* **Scenario K**: Two compound faults (sensor dropout + human entry).
* **Scenario L**: Three compound faults (pressure noise + pump start + valve jam).

### 9.4 Bounded Assurance Properties (`PROP_018`–`PROP_023`)
* **PROP_018**: Modeled unsafe human-zone transition cannot produce an executable consequential action.
* **PROP_019**: Safety-relevant sensor contradiction cannot improve authorization without admissible new evidence.
* **PROP_020**: Actuator fault cannot produce `VERIFIED` unless postconditions hold.
* **PROP_021**: Safety degradation cannot convert previous DENY into ALLOW without a new authorization cycle.
* **PROP_022**: Adversarial environment cannot directly mint or alter authorization.
* **PROP_023**: Stale state-bound ticket cannot execute after modeled environmental drift.

---

## 10. Implementation Status

| Component | Status | Verification State |
| :--- | :--- | :--- |
| **Domain Models & State** | `IMPLEMENTED` | `OFFLINE VERIFIED` (22 tests) |
| **Deterministic Policy Engine** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Policy tests) |
| **Authority Isolation & HMAC Tickets** | `IMPLEMENTED` | `OFFLINE VERIFIED` (7 security tests) |
| **Simulator & Mechanical Verifier** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Simulator tests) |
| **Local Knowledge & Fixtures** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Synthetic manual) |
| **Source Trust & Evidence Roles** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Trust classification tests) |
| **Admissibility & Applicability** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Admissibility tests) |
| **Corroboration & Deduplication** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Corroboration tests) |
| **Constraint Extractor & Validator** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Validator tests) |
| **Nemotron Constraint Extractor** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Transport mock tests) |
| **Conflict & Freshness Engines** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Conflict tests) |
| **Claim Grounding & Certificates** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Phase 2C tests) |
| **Decision Records & Hash Chain** | `IMPLEMENTED` | `OFFLINE VERIFIED` (19 Phase 2D integrity tests) |
| **Safety Enclave Isolation** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Enclave tests) |
| **Deterministic Replay Engine** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Replay security tests) |
| **Bounded SMT Assurance (Z3)** | `IMPLEMENTED` | `OFFLINE VERIFIED` (23 formal assurance properties) |
| **Adversarial Evaluation Engine** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Adversarial fuzzing tests) |
| **State-Bound Authorization (TOCTOU)** | `IMPLEMENTED` | `OFFLINE VERIFIED` (47 Phase 2F revalidation tests) |
| **Active Evidence Acquisition** | `IMPLEMENTED` | `OFFLINE VERIFIED` (33 Phase 2G recovery tests) |
| **Adversarial Physical Environment** | `IMPLEMENTED` | `OFFLINE VERIFIED` (43 Phase 2H environment tests) |
| **Nebius Token Factory / Nemotron** | `IMPLEMENTED` | `LIVE VERIFIED` (Token Factory + Nemotron live verified) |
| **Tavily Knowledge Provider** | `IMPLEMENTED` | `LIVE VERIFIED` (Real Tavily search verified) |
| **Hardware Actuators (ROS 2/GPIO)** | `PLANNED` | Phase 3 |

---

## 11. Quickstart & Offline Installation

MotionFence is built **offline-first**: zero external API keys are needed to run the complete test suite, assurance engine, or interactive CLI demo.

### Prerequisites
* Python 3.12 or 3.13
* Virtual environment tool (`venv`)

### Setup
```bash
# Clone the repository
git clone https://github.com/subodhkant7/motionfence.git
cd motionfence

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

---

## 12. Running Automated Tests

Run the full automated test suite (**267 tests, 100% passing offline**):

```bash
pytest
```

Or run via the test runner script:

```bash
./scripts/run_tests.sh
```

---

## 13. Adversarial Physical Environment CLI Tools (Phase 2H)

```bash
# 1. Run Large-Scale Adversarial Environment Evaluation (1,000 cases)
python scripts/run_adversarial_environment.py --seed 42 --cases 1000

# 2. Replay an Adversarial Scenario Offline (Zero Network / Zero LLM)
python scripts/replay_adversarial_scenario.py SCENARIO_A_HUMAN_TOCTOU

# 3. Delta-Debugging Fault Minimization (Shrink Compound Multi-Fault Failures)
python scripts/minimize_adversarial_failure.py
```

Run formal Z3 SMT invariant verification, bounded temporal transition checks, and property-based adversarial fuzzing completely offline:

```bash
# 1. Run Bounded Formal Assurance Invariant Checks (Z3 SMT Solver)
python scripts/run_assurance.py

# 2. Run Adversarial Evaluation & Property-Based Fuzzing
python scripts/run_adversarial_eval.py --seed 42 --cases 1000

# 3. Replay & Diagnose an Adversarial Case
python scripts/replay_adversarial_case.py --sample
```

---

## 12. CLI Deterministic Replay & Audit Tool

Replay and audit any recorded MotionFence decision offline without network or models:

```bash
# Replay a sample deterministic decision
python scripts/replay_decision.py --sample

# Replay an archived decision by ID
python scripts/replay_decision.py dec_1723857735fc --audit-dir .motionfence_audit
```

---

## 13. Active Evidence Acquisition & Safe Recovery CLI Tools (Phase 2G)

Execute autonomous evidence-gathering and recovery cycles when encountering uncertainty, and replay audit records deterministically offline:

```bash
# 1. Run Autonomous Ambiguity Resolution (INSPECT_TARGET)
python scripts/run_evidence_recovery.py --scenario ambiguous-target

# 2. Run Autonomous Sensor Contradiction Resolution (RESAMPLE_SENSOR)
python scripts/run_evidence_recovery.py --scenario contradiction

# 3. Deterministic Offline Replay of Evidence Acquisition Cycle
python scripts/replay_evidence_recovery.py <run_id>
```

### 10-Step Recovery Lifecycle Output:
```text
[01] OBSERVE               Initial sensor observation pool registered
[02] PROPOSE               Unprivileged ActionProposal generated
[03] POLICY                NEED_MORE_EVIDENCE issued under uncertainty
[04] EVIDENCE PROPOSED     Bounded information action selected (zero actuator authority)
[05] EVIDENCE AUTHORIZED   Validated against CapabilityPolicy (ACTUATE strictly prohibited)
[06] NEW EVIDENCE          EvidenceActionGateway executes bounded perception update
[07] POLICY RE-EVALUATION  Deterministic re-evaluation with updated empirical telemetry
[08] VERDICT               ALLOW / DENY / NEED_MORE_EVIDENCE
[09] ACT                   Actuator executes only upon SafetyEnclave ticket issuance
[10] VERIFY                Postcondition verifier independently validates physical plant
```

---

## 14. Interactive Terminal Demonstration

Run the interactive demonstration completely offline:

```bash
# Offline deterministic mode with local plant knowledge and admissibility gating
python -m motionfence.simulation.demo --provider local --knowledge local
```

### Executed Scenarios:
1. **Scenario 1 (Leak Isolation)**: Ambient wide-angle ambiguity triggers `NEED_MORE_EVIDENCE`; targeted inspection resolves target to Valve B; Policy issues `ALLOW`; Actuator executes; Verifier confirms `VERIFIED`.
2. **Scenario 2 (Knowledge-Derived Prohibition)**: Official plant manual prohibition *"Valve B must not be closed while Pump P1 is active"*; Policy strictly **DENIES** closure; Valve B remains OPEN (no ticket, no actuation).
3. **Scenario 3 (Preconditions Satisfied)**: Pump P1 stopped; prohibition condition ceases to hold; Policy issues `ALLOW`; Valve B safely closed.
4. **Scenario 4 (Harmless Procedure)**: Routine SOP *"Visual inspection should be performed"* classified as `INFORMATIONAL`; does NOT falsely block valid closure.
5. **Scenario 5 (Conflicting Knowledge Sources)**: Standard manual (prohibition) conflicts with emergency guideline (permission); detector flags `CONFLICTED`; execution strictly blocked.
6. **Scenario 6 (Stale Knowledge Handling)**: Archived 90-day-old specification flagged `STALE`; policy forces `NEED_MORE_EVIDENCE` for recertification.
7. **Scenario 7 (Multi-Source Corroboration)**: OEM manual (`ksb.com`) + ASME standards (`asme.org`) independently corroborate prohibition -> promoted to `ACTIVE` -> strictly blocks actuation.
8. **Scenario 8 (Weak Community Source)**: Reddit forum post claiming Valve B is unsafe -> classified as `COMMUNITY_OR_USER_CONTENT` (`DISCOVERY` role) -> **NOT admissible as prohibition** -> valid physical action proceeds safely.
9. **Scenario 9 (Applicability Mismatch)**: Manual for Slurry Pump Model P200-B evaluated against plant's Centrifugal P100-A -> `MISMATCH` -> foreign constraint does not block local operations.
10. **Scenario 10 (Adversarial Causal Injection)**: Model claims closure causes hydraulic shock when source contains no causal statement -> classified `INFERENCE` / `INSUFFICIENT` -> core rule accepted, inference cannot become safety policy.
11. **Scenario 11 (Adversarial Negation Reversal)**: Model flips permission "may be closed" to "must not be closed" -> classified `CONTRADICTED` / `CLAIM_NEGATION_MISMATCH` -> strictly rejected.
12. **Scenario 12 (Adversarial Condition Dropping)**: Model drops "while Pump P1 is active" to claim "must never be closed" -> rejected as `CLAIM_CONDITION_LOST`.
13. **Scenario 13 (Adversarial Scope Broadening)**: Model generalizes "Valve B" to "all valves" -> rejected as `CLAIM_SCOPE_MISMATCH`.
14. **Scenario 14 (Adversarial Threshold Tampering)**: Model alters line pressure threshold from 50 psi to 80 psi -> rejected as `INVENTED_NUMERIC_THRESHOLD`.

---

## 15. Fault Containment, Quarantine & Autonomous Recovery (Phase 2I)

When an authorized physical action fails or a sensing component becomes unreliable, MotionFence autonomously contains the failure, determines what remains trustworthy, quarantines unsafe components when necessary, gathers additional evidence, and initiates a fresh authorization cycle without silently reusing stale authority.

### Extended Recovery Lifecycle
```text
Observe → Propose → Policy → Authorize → Revalidate → Act → Verify
                                                               │
                                       ┌───────────────────────┴──────────────────────┐
                                       ▼                                              ▼
                                   VERIFIED                                         FAILED
                                                                                      │
                                                                           Failure Classification
                                                                                      │
                                                                                 Containment
                                                                                      │
                                                                                 Quarantine?
                                                                                      │
                                                                                Recovery Plan
                                                                                      │
                                                                                New Evidence
                                                                                      │
                                                                                Re-evaluate
                                                                                      │
                                                                             Fresh Authorization
```

### Deterministic Failure Taxonomy
* `ACTUATOR_NO_OP`: Commanded state unchanged after actuation.
* `ACTUATOR_PARTIAL`: Actuator halted mid-stroke in TRANSITIONING state.
* `ACTUATOR_DELAY`: Actuator stroke latency exceeded bounded threshold.
* `ACTUATOR_WRONG_STATE`: Actuator seated into uncommanded or contradictory physical state.
* `SENSOR_FAILURE`: Transducer disconnected, zero confidence, or hardware failure.
* `SENSOR_STALE`: Telemetry timestamp exceeds maximum freshness threshold.
* `SENSOR_CONTRADICTION`: Telemetry conflicts with corroborated multi-sensor readings.
* `ENVIRONMENT_DRIFT`: Physical safety state mutated prior to execution.
* `POLICY_FAILURE`: Policy version drifted after ticket issuance.
* `KNOWLEDGE_FAILURE`: Safety constraints mutated or invalidated.

### Scoped Quarantine & Finite Budgets
* **Scoped Quarantine**: When a component (e.g. `valve_b`) is quarantined, consequential actions (`CLOSE_VALVE`, `OPEN_VALVE`) are blocked on that target, while diagnostic actions (`INSPECT_TARGET`, `READ_SENSOR`) remain permitted. Other plant components (`valve_a`) remain fully operational.
* **Deterministic Escalation**: 1 failure → `SUSPECT`, 2 failures → `RECOVERY_REQUIRED`, 3 consecutive failures → `QUARANTINED`.
* **Zero Unsafe Retries**: `unsafe_retries == 0` strictly enforced. Reusing a consumed or stale ticket unconditionally raises `UnauthorizedActionError`.
* **Finite Recovery Budget**: Recovery attempts and steps are strictly bounded to prevent infinite loops (`MAX_RECOVERY_ATTEMPTS = 3`).

### Formal Bounded Properties (Z3 SMT Verification)
* **`PROP_024`**: Verified action failures unconditionally invalidate authority tickets.
* **`PROP_025`**: Quarantined components cannot execute blocked consequential capabilities.
* **`PROP_026`**: Autonomous recovery cannot silently reuse stale consequential authorization.
* **`PROP_027`**: Every consequential recovery action requires a fresh policy reevaluation and enclave authorization cycle.
* **`PROP_028`**: Sensor quarantine strictly excludes untrusted evidence from active authorization context.
* **`PROP_029`**: Recovery attempts are bounded by a finite budget.
* **`PROP_030`**: Recovery planning cannot escalate informational actions into consequential execution.

### Recovery CLI Tools
```bash
# Execute autonomous fault containment and recovery scenarios
python scripts/run_recovery.py --scenario actuator-no-op
python scripts/run_recovery.py --scenario repeated-failure
python scripts/run_recovery.py --scenario alternate-path
python scripts/run_recovery.py --scenario sensor-quarantine
python scripts/run_recovery.py --scenario budget-exhaustion

# Replay recovery traces offline (100% offline, side-effect free, no models, no tickets, no actuators)
python scripts/replay_recovery.py audit_records/rec_actuator-no-op_<timestamp>.json

# Manage component quarantine registry
python scripts/quarantine_component.py --status valve_b
python scripts/quarantine_component.py --quarantine valve_b --reason "Mechanical friction"
python scripts/quarantine_component.py --recertify valve_b --evidence "ev_repaired_01"
```

---

## 16. Policy Mutation Firewall & Safety Regression Detection (Phase 2J)

Phase 2J validates a canonical corpus of safety-relevant policy mutations. MotionFence treats policy changes as potentially unsafe until proven otherwise:
```text
Policy Candidate
      ↓
Policy Mutation Engine (Detached Clones Only)
      ↓
Adversarial Probes & Scenario Evaluation
      ↓
Bounded Assurance (Z3 SMT Solver: PROP_031–PROP_036)
      ↓
Regression Decision (ACCEPT / REJECT / INCONCLUSIVE → REJECT)
```

### Core Mutation Capabilities
* **Deterministic Mutation Corpus**: Covers 10 canonical safety attack vectors (human-zone guard removal, cooling invariant deletion, confidence weakening 0.90→0.70, contradiction blocking removal, scope expansion, stale knowledge acceptance, evidence requirement removal, TOCTOU revalidation removal, recovery budget expansion, and quarantine bypass) plus non-safety metadata modifications.
* **Separation of Unsafe ALLOW Metrics**: Independently tracks `baseline_unsafe_allows`, `mutated_unsafe_allows`, and `new_unsafe_allows = max(0, mutated_unsafe_allows - baseline_unsafe_allows)`.
* **Automatic Counterexample Search & Minimization**: Isolates the exact minimal scenario parameters explaining why a mutation broke a safety boundary.
* **Conservative Firewall Verdicts**: `INCONCLUSIVE` conservative fallback directly maps to `REJECT`.
* **Zero Authority Isolation**: The mutation engine and evaluator operate on detached policy clones with zero ticket minting, zero physical actuation, and zero external network calls.
* **Formal Assurance (PROP_031–PROP_036)**: Formally proved in Z3 SMT that policy mutations cannot silently disable human safety guards, weaken confidence checks, bypass contradiction gating, or evade state-bound authorization.

### Policy Mutation CLI & CI Tools
```bash
# Execute specific safety mutation attack
python scripts/run_policy_mutation.py --mutation human-zone-guard
python scripts/run_policy_mutation.py --mutation confidence-threshold

# Run complete canonical safety mutation suite
python scripts/run_policy_mutation.py --all-safety-mutations

# Replay mutation analysis deterministically (100% offline, zero network, zero actuation)
python scripts/replay_policy_mutation.py <mutation_id_or_file>

# CI-compatible policy firewall check (exits with code 0 if all dangerous regressions caught)
python scripts/policy_firewall.py [--baseline <policy-file>]
```

---

## 17. Combinatorial Policy Attacks, Dynamic Trajectories & Safe Repair Proposals (Phase 2K)

Phase 2K extends isolated safety mutation analysis into bounded compound mutations, dynamic physical trajectories, and safe repair proposals.

```text
Compound / Trajectory Attack Candidate
      ↓
Combinatorial Mutator (Pairwise & Selected Triplets)
      ↓
Interaction Classifier (NO_INTERACTION, ADDITIVE, AMPLIFYING, CONFLICTING, MASKING)
      ↓
Dynamic Trajectory Exploration (Depths 3, 5, 8 with Fault Injection)
      ↓
Bounded Assurance (Z3 SMT Solver: PROP_037–PROP_044)
      ↓
Policy Repair Synthesizer (Minimal Conservative Patches)
      ↓
Detached Policy Repair Validator (Monotonicity Check + Trajectory Revalidation)
      ↓
Safe Repair Verdict (ACCEPT / REJECT / INCONCLUSIVE → REJECT)
```

### Core Capabilities
* **Bounded Compound Mutations**: Systematically generates pairwise combinations across orthogonal safety dimensions (e.g., human-zone bypass + cooling invariant removal, TOCTOU bypass + confidence reduction) and canonical triplets to detect emergent vulnerabilities that appear only when multiple defenses degrade simultaneously.
* **Deterministic Interaction Classification**: Classifies combinatorial attack interactions into `NO_INTERACTION`, `ADDITIVE`, `AMPLIFYING`, `CONFLICTING`, and `MASKING` to highlight non-linear safety boundary erosion.
* **Bounded Dynamic Trajectory Exploration**: Simulates sequential multi-step physical trajectories at exploration depths of 3, 5, and 8 steps under injected sensor noise, state-version desynchronization, concurrent command conflicts, and degraded network conditions. Trajectory minimization isolates the precise minimal prefix leading to safety violations.
* **Safe, Non-Authoritative Repair Proposals**: Generates minimal structural patches (`PolicyRepairProposal`) targeted at detected regressions. Repair proposals are strictly advisory, carry ZERO execution authority, and must pass the full detached validation pipeline (`PolicyRepairValidator`) before acceptance.
* **Monotonicity Enforcement**: Validates that candidate repairs do not introduce regressions on previously passing scenarios (`SAFETY_MONOTONICITY_PRESERVED`). Inconclusive evaluations fail closed (`REPAIR_INCONCLUSIVE` → `REJECT`).
* **Formal Assurance (PROP_037–PROP_044)**: Formally proved in Z3 SMT that compound mutations preserve regression detection, interaction classifications are deterministic, trajectory step bounds are strictly enforced, non-authoritative repairs cannot self-authorize, and repair validation preserves safety monotonicity.

### Explicit Limitations
> [!IMPORTANT]
> **Bounded Assurance Disclaimer**: Phase 2K performs bounded combinatorial evaluation and dynamic trajectory exploration over modeled state spaces. It **does NOT** claim universal safety, exhaustive trajectory coverage over arbitrary state transitions, or complete combinatorial coverage across infinite state spaces. All repair proposals are non-authoritative recommendations requiring external operator review and promotion.

### Combinatorial & Trajectory CLI Tools
```bash
# Run policy firewall with compound mutation evaluation
python scripts/policy_firewall.py --compound

# Run policy firewall with dynamic trajectory evaluation
python scripts/policy_firewall.py --trajectory

# Run complete evaluation suite (single, compound, trajectories, and repairs)
python scripts/policy_firewall.py --full --seed 42

# Replay dynamic trajectory offline (100% offline, side-effect free)
python scripts/replay_trajectory.py <trajectory_id_or_file>

# Replay mutation analysis deterministically with interaction breakdown
python scripts/replay_policy_mutation.py <mutation_id_or_file>
```

---

## 18. Safety Case & Judge Console (Phase 2L)

The **MotionFence Judge Console** is a specialized, industrial mission-control interface built for judges, safety auditors, and operators. It makes the entire 10-stage runtime safety lifecycle understandable within 30 seconds:

```text
OBSERVE → EVIDENCE → PROPOSE → POLICY → AUTHORIZE → WORLD CHANGE → REVALIDATE → ACT → VERIFY → RECOVER
```

### Core Architecture & Principles
* **Real Operational Data**: Visualizes canonical, reproducible MotionFence execution and audit records (`DecisionRecord`, `AuthorizationTicket`, `RevalidationContext`, `FailureRecord`). Zero fake telemetry, zero invented metrics, and zero simulated AI confidence graphs.
* **Strict Read-Only Zero Authority**: The console is cryptographically and architecturally detached from actuation. It possesses **ZERO authority** to mint authorization tickets, issue actuator stroke commands, override safety invariants, or auto-apply policy repair proposals to production. The backend rejects all modifying requests (`POST`, `PUT`, `DELETE`, `PATCH`) with `405 Method Not Allowed` and sends `X-MotionFence-Authority: STRICTLY_READ_ONLY`.
* **Subsystem Architecture**:
  * **Frontend**: React 19 + TypeScript + Vite + Framer Motion in [`console/`](console/).
  * **Backend**: Lightweight read-only HTTP server in [`scripts/console_server.py`](scripts/console_server.py) with offline fallback fixtures in [`console/src/data/`](console/src/data/).
  * **Fixture Generator**: Deterministic canonical test suite generator in [`scripts/generate_judge_fixtures.py`](scripts/generate_judge_fixtures.py).

### Four Primary Operator Views
1. **Decision Replay (Landing View)**:
   * **10 Chronological Lifecycle Stages**: Step-by-step playback scrubber (`PLAY`, `PAUSE`, step forward/backward, variable speed 0.5x–2x).
   * **Core Evidence Distinction**: Prominently displays `SOURCE EXISTS ≠ SOURCE TRUSTWORTHY ≠ CLAIM SUPPORTED ≠ AUTHORIZATION SUFFICIENT`.
   * **3 Canonical Evaluation Scenarios**:
     * **Scenario A (Nominal Execution)**: Agent proposes valve closure; policy checks pass, enclave mints HMAC ticket, 9 revalidation barriers verify, valve actuates, postcondition verified.
     * **Scenario B (TOCTOU Revalidation Defense)**: Human enters hazardous zone after ticket issuance; execution-time revalidation detects world version drift ($v_1 \to v_2$), marks ticket **`INVALIDATED`**, and aborts physical actuation before any hardware moves.
     * **Scenario C (Actuator Failure & Autonomous Recovery)**: Actuator stroke fails despite reported success; postcondition verification detects limit switch mismatch, triggers containment, quarantines `valve_b`, synthesizes recovery plan, and proves fresh authorization is required (**NO STALE TOKEN REUSE**).
2. **Policy Mutation Firewall (Phase 2J / 2K)**:
   * **Exact Metric Breakdown**: 6 top-level categories without score collapse: **11** Single Safety Mutations, **9** Compound Attacks, **18** Dynamic Trajectories, **19** Detected Regressions, **0** Escaped Regressions, **19** Repair Proposals (**8** Validated, **8** Rejected, **3** Fail-Closed Inconclusive).
   * **Mutation Drill-Down Modal**: Detailed diff of baseline vs mutated attack values, minimized counterexample traces, and violated formal monotonicity guarantees.
   * **Non-Authoritative Safe Repair Proposals**: Displays candidate conservative patches with explicit non-authoritative disclaimers and fail-closed rejections.
3. **Dynamic Trajectories**:
   * **Dual-State Separation**: Side-by-side comparison of **1. Observed State (Runtime Telemetry Perception)** vs **2. Hidden Ground Truth (Physical Reality)**.
   * **Temporal Scrubber**: Explores sequential execution steps ($t_0 \to t_1 \to t_2$) with environmental fault injection indicators (`ACTUATOR_NO_OP`, `SENSOR_CORRUPTION`).
4. **Formal Assurance (44 Bounded Z3 Properties)**:
   * **Prominent Scope Limitation Disclaimer**: *"Formal results are bounded proofs over the modeled MotionFence state space; they are not proofs of unrestricted real-world physical safety."*
   * **Interactive Registry**: Filter by subsystem (`Policy`, `TOCTOU`, `Fault`, `Mutation`, `Combinatorial`), view SMT-LIB predicates, and verify bounded refutation proofs.

### Quickstart CLI Commands
```bash
# 1. Generate canonical evaluation fixtures
python scripts/generate_judge_fixtures.py

# 2. Start the read-only Python console API server (port 8080)
python scripts/console_server.py --port 8080

# 3. In another terminal, run the Vite Judge Console dev server
cd console
npm install
npm run dev

# 4. Open http://127.0.0.1:5173 in any modern browser
```

### Verification & Testing
* **Backend Security Invariants**: Dedicated tests across 19 suites verifying zero authority, 405 method rejection, hardware boundaries, and strict read-only headers (Total: **405 pytest tests passing**).
* **Frontend Component Tests**: 15 Vitest component tests in [`console/src/test/console.test.tsx`](console/src/test/console.test.tsx) verifying all 4 screens, lifecycle transitions, invalidation states, dual-state trajectory separation, and accessibility toggles (**15/15 tests passing**).

---

## 19. Mock Physical Hardware Boundary

### Actuator Security Architecture

MotionFence does not grant the AI direct actuator authority.

The agent proposes an action.

MotionFence evaluates policy and evidence.

SafetyEnclave issues authorization only when permitted.

The mock hardware endpoint accepts only valid MotionFence authorization.

Invalid, expired, replayed, mismatched, or stale authorization is rejected.

The endpoint is a deterministic software representation of a physical actuator and does not claim to be physical hardware.

### Key Architectural Invariants

* **NO VALID MOTIONFENCE AUTHORIZATION TICKET = NO ACTUATION**: Without a valid cryptographic `AuthorizationTicket`, the hardware endpoint remains locked.
* **VALID AT AUTHORIZATION TIME ≠ VALID AT EXECUTION TIME**: Execution-time revalidation guarantees that environmental drift (e.g. human entering hazard zone) invalidates tickets before hardware mutation can occur.
* **ZERO ENDPOINT AUTHORITY**: The mock hardware endpoint has zero policy authority, zero ticket-minting authority, zero model provider authority, and zero repair approval authority. It only verifies whether presented authorization is cryptographically and semantically valid for the requested physical mutation.
* **DETERMINISTIC REPLAY IS ZERO-MUTATION**: Hardware replay is 100% offline, side-effect free, and cannot stroke actuators, modify world state, or mint tickets.

### Four Canonical Hardware Boundary Scenarios

| Scenario | Agent Proposal | Policy Verdict | Ticket Status | Hardware State | Actuation Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Allowed** | `CLOSE_VALVE valve_b` | `ALLOW` | Valid HMAC-SHA256 | `ACTUATED` | Physical state mutated; postcondition verified |
| **2. Denied** | `CLOSE_VALVE valve_b` (hazard) | `DENY` | Not Issued | `LOCKED` | Zero physical mutation; valve remains open |
| **3. Stale Ticket** | `CLOSE_VALVE valve_b` | `ALLOW` (v3) | Drift to v4 | `INVALID_TICKET` / `LOCKED` | TOCTOU blocked at boundary; valve preserved |
| **4. Hardware Fault**| `CLOSE_VALVE valve_b` | `ALLOW` | Valid | `HARDWARE_FAULT` | No-op fault injected; PostActionVerifier detects failure |

### Terminal Visual Representation
```text
┌────────────────────────────────────────────┐
│ MOCK PHYSICAL HARDWARE — NOMINAL           │
├────────────────────────────────────────────┤
│ Pump P1            INACTIVE               │
│ Valve B            CLOSED                 │
│ Safety Zone        CLEAR                  │
│ Ticket             tkt_ab4a81...          │
│ Authorization      VALID                  │
│ Actuator           ACTUATED               │
└────────────────────────────────────────────┘
```

### CLI Demonstration & Replay Commands
```bash
# Run all four canonical scenarios and write transcripts to motionfence/fixtures/hardware_demo/
python scripts/run_hardware_boundary_demo.py --scenario all

# Run individual scenarios
python scripts/run_hardware_boundary_demo.py --scenario allowed
python scripts/run_hardware_boundary_demo.py --scenario denied
python scripts/run_hardware_boundary_demo.py --scenario stale-ticket
python scripts/run_hardware_boundary_demo.py --scenario actuator-failure

# 100% offline, side-effect-free, read-only replay of hardware execution events
python scripts/replay_hardware_event.py --sample
```

### Bounded Formal Verification (51 Z3 Assurance Properties)
Seven dedicated hardware boundary invariant properties (`PROP_045` through `PROP_051`) are verified via bounded SMT-LIB model checking:
* `PROP_045_HARDWARE_CANNOT_ACTUATE_WITHOUT_AUTHORIZATION`
* `PROP_046_INVALID_TICKET_CANNOT_ACTUATE`
* `PROP_047_EXPIRED_TICKET_CANNOT_ACTUATE`
* `PROP_048_REPLAYED_TICKET_CANNOT_ACTUATE`
* `PROP_049_TARGET_MISMATCH_CANNOT_ACTUATE`
* `PROP_050_ACTION_MISMATCH_CANNOT_ACTUATE`
* `PROP_051_STALE_AUTHORIZATION_CANNOT_ACTUATE`

---

## 20. Live Smoke Tests (External Providers)

### Nebius Token Factory (NVIDIA Nemotron Action Proposals)
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
python scripts/smoke_nebius.py
```

### Nebius Token Factory (NVIDIA Nemotron Constraint Extraction)
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
# Live request (consumes API tokens)
python scripts/smoke_nebius_constraint_extraction.py
# Cached replay (0 live API calls, labeled REPLAY)
python scripts/smoke_nebius_constraint_extraction.py --reuse-cached
```

### Tavily Search API
```bash
export TAVILY_API_KEY="your-tavily-api-key"
python scripts/smoke_tavily.py
```

---

## 21. Live Physical AI Demonstration (Phase 2N)

Phase 2N establishes the first fully integrated demonstration path for physical AI runtime safety:

**LIVE NEMOTRON → MOTIONFENCE → JUDGE CONSOLE → MOCK HARDWARE → DIGITAL TWIN**
*(with deterministic offline replay fallback)*

### Core Separation of Concerns
1. **Nemotron proposes**: NVIDIA Nemotron (`nvidia/nemotron-3-super-120b-a12b`) on Nebius Token Factory formulates high-level ActionProposals from sensory context. It possesses **zero actuation credentials** and **zero authority** over policy.
2. **MotionFence decides**: Deterministic `PolicyEngine` independently evaluates proposals against hard invariant constraints, evidence grounding, and human safety zone boundaries.
3. **SafetyEnclave authorizes**: Only an affirmative `ALLOW` verdict allows the isolated enclave to mint a state-bound `AuthorizationTicket` signed via HMAC-SHA256.
4. **Mock Hardware enforces boundary**: The `MockHardwareEndpoint` validates the cryptographic signature, target binding, action alignment, single-use anti-replay consumption, and state version before permitting any actuator stroke.
5. **PhysicalWorld / Digital Twin reflects state**: The deterministic simulation updates physical reality, visualized simultaneously via ASCII CLI art and the React-based 2D Plant Digital Twin in the Judge Console.
6. **PostActionVerifier confirms outcome**: Compares commanded action against observed postcondition sensors, initiating containment and autonomous recovery if mechanical fault occurs.
7. **Replay reproduces deterministically**: 100% offline, side-effect-free replay verifies cryptographic SHA-256 record hashes without invoking external models or network sockets.

> **Engineering Disclaimer:**
> *The digital twin and mock hardware are software representations used for demonstration and validation. They do not claim equivalence to certified industrial hardware.*

### Canonical Live Demonstration Scenarios
* **Scenario A — Nominal Safe Execution**: Live Nemotron proposes valve isolation under verified leak conditions; MotionFence authorizes; Mock Hardware actuates; Postcondition verified.
* **Scenario B — Unsafe Proposal Denial**: Human technician occupies safety zone; Live Nemotron proposes valve closure; MotionFence strictly returns `DENY`; No ticket is minted; Mock Hardware remains locked; Zero physical mutation occurs.
* **Scenario C — TOCTOU Revalidation Defense**: MotionFence mints a ticket bound to World version `v3`. An environmental drift occurs before execution (`v3` → `v4`, human enters zone). `ExecutionTimeRevalidator` detects version mismatch; ticket is invalidated; Mock Hardware strictly blocks actuation.
* **Scenario D — Actuator Failure & Recovery**: Live Nemotron proposal is authorized. A hardware mechanical fault is injected (limit switch mismatch). `PostActionVerifier` detects discrepancy; ticket is invalidated; component is quarantined; an autonomous recovery plan is formulated, evaluated, freshly authorized, and verified.

### Executing Live Scenarios (Nebius Token Factory)
```bash
# Set your Nebius API Key in .env (never logged, never committed)
export NEBIUS_API_KEY="your-nebius-api-key"

# Run canonical live demonstration scenarios
python scripts/live_nebius_demo.py --scenario safe
python scripts/live_nebius_demo.py --scenario denied
python scripts/live_nebius_demo.py --scenario toctou
python scripts/live_nebius_demo.py --scenario recovery
python scripts/live_nebius_demo.py --scenario all
```

### Deterministic Offline Replay (Zero Network, Zero Model Calls)
```bash
# Replay individual canonical records offline with SHA-256 integrity verification
python scripts/replay_live_demo.py --scenario safe
python scripts/replay_live_demo.py --scenario toctou

# Replay all canonical records offline
python scripts/replay_live_demo.py --all
```

---

## 22. Real-World Public Telemetry (Phase 2O)

Phase 2O integrates **real-world public telemetry** through the modern **USGS Water Data OGC API**, demonstrating how MotionFence ingests live physical observations without giving those observations, the AI model, or the UI direct actuator authority.

### Canonical Data Flow
```text
REAL PUBLIC API (USGS OGC API latest-continuous)
      ↓
PublicTelemetryProvider (USGSOgcTelemetryProvider)
      ↓
Telemetry Normalizer (TelemetryNormalizer)
      ↓
ObservationSnapshot (Provenance, Timestamps, Freshness, Payload Hash)
      ↓
Evidence / WorldState Adapter (TelemetryEvidenceAdapter)
      ↓
MotionFence Runtime
├── Evidence (`environmental.usgs.*`)
├── Grounding & Trust (`usgs.gov` standards domain)
├── Freshness Evaluation (`FRESH` / `STALE` / `UNKNOWN`)
├── Deterministic Policy (`PolicyEngine`)
└── State-Bound Authorization (`SafetyEnclave` HMAC Ticket)
      ↓
Mock Hardware Endpoint (`MockHardwareEndpoint`)
      ↓
PhysicalWorld / Digital Twin Simulation
```

### Core Separation & Semantic Honesty
> **REAL OBSERVATION ≠ COMPLETE PHYSICAL STATE**
>
> and
>
> **REAL OBSERVATION ≠ AUTOMATIC AUTHORIZATION**

* **Observation vs. Actuation**: The public API is strictly an OBSERVATION source. It never connects directly to `SafetyEnclave`, ticket minting, policy mutation, or hardware actuation.
* **Separation of Models**: Real public telemetry (e.g. Potomac River discharge) is distinct from modeled control-system state (e.g. Pump P1, Valve B, human safety zone), which is distinct from hidden ground truth used for adversarial testing.
* **Fail-Closed Principle**: On transport failure, HTTP 4xx/5xx errors, schema mismatches, or missing parameters, the telemetry provider fails closed (`NO_DATA`, `TRANSPORT_ERROR`). Absence of external observation can never produce an implicit `ALLOW`.
* **Stale Evidence Remains Stale**: Real timestamps are compared against acquisition times. If an observation exceeds the freshness window (2 hours), its status is classified as `STALE`, lowering confidence and preventing stale data from masquerading as current state.
* **Bounded Z3 Invariants**: Extended from 51 to 56 formal properties, verifying that external telemetry has zero actuator authority (`PROP_052`), missing observations cannot create authorizations (`PROP_053`), stale evidence cannot be presented as fresh (`PROP_054`), replayed observations cannot claim live status (`PROP_055`), and provenance remains cryptographically bound (`PROP_056`).

### Canonical USGS Monitoring Location
* **API Family**: `https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items`
* **Station ID**: `USGS-01646500`
* **Station Name**: `POTOMAC RIVER NEAR WASH, DC LITTLE FALLS PUMP STA`
* **Parameters**:
  * `00060`: Discharge / Streamflow (`ft³/s`)
  * `00065`: Gage height (`ft`)

### Public Telemetry CLI Usage

```bash
# 1. Fetch live public telemetry from USGS OGC API and evaluate through MotionFence
python scripts/live_public_telemetry.py

# 2. Query a specific configured monitoring location
python scripts/live_public_telemetry.py --location USGS-01646500

# 3. Deterministic offline replay of recorded real observations (Zero network, zero credentials)
python scripts/replay_public_telemetry.py --sample

# 4. Replay the full integrated telemetry scenario (USGS + Nemotron)
python scripts/replay_live_demo.py --scenario telemetry

# 5. Live end-to-end demonstration with real USGS API and live Nebius Token Factory
python scripts/live_nebius_demo.py --scenario telemetry
```

---

## 23. Architectural Documentation

For comprehensive specifications:
* [Architecture Overview](docs/architecture.md): Complete control loop, trust model, Safety Enclave, bounded assurance, and sequence flows.
* [Security & Authority Model](docs/security-model.md): Invariant proofs, threat modeling, Safety Enclave, bounded assurance, and authority isolation boundaries.
* [Domain & Knowledge Models](docs/domain-model.md): Detailed schemas for WorldState, KnowledgeEvidence, DecisionRecord, AssuranceFinding, and Tickets.
* [Demonstration Scenarios](docs/demo-scenario.md): In-depth walkthrough of all physical, knowledge-grounded, and assurance operational scenarios.

---

## 24. License

MotionFence is licensed under the [MIT License](LICENSE).



