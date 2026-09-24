# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-92%20passed-brightgreen.svg)](tests/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory%20API-purple.svg)](https://tokenfactory.nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron--3--Super--120B-76B900.svg)](https://build.nvidia.com)
[![Tavily Search](https://img.shields.io/badge/Tavily-Search%20API-blue.svg)](https://tavily.com)

Built for the **Nebius x NVIDIA Global AI Hackathon 2026** (Physical AI Track).

---

## 1. What is MotionFence?

**MotionFence** is an independent, deterministic runtime authorization gateway governing AI-driven embodied agents and physical systems.

In MotionFence, an AI agent proposes what physical actions should happen, but a deterministic, rule-based runtime engine independently decides whether each physical action is **allowed**, **denied**, or **requires additional evidence** before any physical actuator can move.

### Product Thesis
> **MotionFence does not trust the model, the sensor, or external knowledge independently. It cross-checks evidence, converts relevant knowledge into structured candidate constraints, validates those constraints deterministically, assesses institutional evidence trust and plant applicability, and authorizes physical actions only when the complete policy state permits them.**

*Disclaimer: MotionFence is an architectural research prototype developed for the Nebius x NVIDIA AI Hackathon, not an industrially certified safety-critical SIL-4 controller. It does not claim formal certification or regulatory compliance.*

---

## 2. Why Does It Exist?

Autonomous reasoning models (such as LLMs and vision-language-action models) excel at high-level reasoning and perceptual synthesis, but they are inherently probabilistic. In physical and industrial environments, probabilistic execution is dangerous:

* Visual ambiguity can lead a model to actuate the wrong valve or switch.
* Sensor noise or lens flare can trigger ungrounded emergency procedures.
* Prompt injections or agent delusions can bypass basic prompt-level safety instructions.
* External web search (e.g. Tavily) returns heterogeneous sources: OEM manuals, technical papers, but also forum threads, social media posts, and scraped mirrors.
* Structural validity and provenance do not prove that retrieved knowledge is authoritative enough to influence a safety-relevant physical action.

### Critical Architectural Invariants
1. **SOURCE EXISTS ≠ SOURCE IS TRUSTWORTHY ≠ CLAIM IS APPLICABLE ≠ CLAIM IS SUFFICIENT FOR AUTHORIZATION**: External knowledge remains untrusted evidence.
2. **Tavily provides discovery and external evidence. It does not provide authority.**
3. **Nemotron interprets evidence. It does not provide authority.**
4. **The deterministic MotionFence runtime decides whether evidence is admissible and whether an action is authorized.**
5. **Actuator isolation remains absolute**: Actuators require single-use HMAC-SHA256 signed `AuthorizationTicket` minted strictly by `PolicyEngine`.

---

## 3. The Core Control Loop

Phase 2B introduces explicit Source Assessment, Corroboration, and Admissibility Gating:

```text
Tavily / Local Knowledge
        ↓
KnowledgeEvidence (Provenance, URL, Freshness)
        ↓
Source Trust Assessment (Category: OEM, Standards, Community, Unknown)
        ↓
Evidence Role Assignment (DISCOVERY vs SUPPORTING vs AUTHORIZATION_RELEVANT)
        ↓
Nemotron / Local Constraint Extraction (Structured Pydantic Model)
        ↓
Constraint Admissibility Gate (Authority, Corroboration, Equipment Applicability)
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
* **`STRUCTURALLY_VALID`** (or `VALIDATED`): Schema is well-formed and cites existing, registered evidence.
* **`ADMISSIBLE`**: Sourced from sufficiently authoritative origin, applicable to target equipment, fresh, and corroborated where needed.
* **`ACTIVE`**: Evaluated by deterministic PolicyEngine during physical authorization decisions.
* **`REJECTED` / `CONFLICTED` / `STALE`**: Inadmissible due to invalid schema, contradictions, or expired freshness.

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

