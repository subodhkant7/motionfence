# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20passed-brightgreen.svg)](tests/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory%20API-purple.svg)](https://tokenfactory.nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron--3--Super--120B-76B900.svg)](https://build.nvidia.com)
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

## 5. Implementation Status

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
| **Nebius Token Factory / Nemotron** | `IMPLEMENTED` | `LIVE PENDING CREDENTIALS` (Smoke script ready) |
| **Tavily Knowledge Provider** | `IMPLEMENTED` | `LIVE VERIFIED` (Real Tavily search verified) |
| **Hardware Actuators (ROS 2/GPIO)** | `PLANNED` | Phase 3 |

---

## 6. Quickstart & Offline Installation

MotionFence is built **offline-first**: zero external API keys are needed to run the complete test suite or interactive CLI demo.

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

## 7. Running Automated Tests

Run the full automated test suite (**92 tests, 100% passing offline**):

```bash
pytest
```

Or run via the test runner script:

```bash
./scripts/run_tests.sh
```

---

## 8. Interactive Terminal Demonstration

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

## 9. Live Smoke Tests (External Providers)

### Nebius Token Factory (NVIDIA Nemotron Action Proposals)
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
python scripts/smoke_nebius.py
```

### Nebius Token Factory (NVIDIA Nemotron Constraint Extraction)
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
python scripts/smoke_nebius_constraint_extraction.py
```

### Tavily Search API
```bash
export TAVILY_API_KEY="your-tavily-api-key"
python scripts/smoke_tavily.py
```

---

## 10. Architectural Documentation

For comprehensive specifications:
* [Architecture Overview](docs/architecture.md): Complete control loop, trust model, and sequence flows.
* [Security & Authority Model](docs/security-model.md): Invariant proofs, threat modeling, and authority isolation boundaries.
* [Domain & Knowledge Models](docs/domain-model.md): Detailed schemas for WorldState, KnowledgeEvidence, SourceTrustAssessment, CandidateConstraint, and Tickets.
* [Demonstration Scenarios](docs/demo-scenario.md): In-depth walkthrough of all physical and knowledge-grounded operational scenarios.

---

## 11. License

MotionFence is licensed under the [MIT License](LICENSE).

