# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-63%20passed-brightgreen.svg)](tests/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory%20API-purple.svg)](https://tokenfactory.nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron--3--Super--120B-76B900.svg)](https://build.nvidia.com)
[![Tavily Search](https://img.shields.io/badge/Tavily-Search%20API-blue.svg)](https://tavily.com)

Built for the **Nebius x NVIDIA Global AI Hackathon 2026** (Physical AI Track).

---

## 1. What is MotionFence?

**MotionFence** is an independent, deterministic runtime authorization gateway governing AI-driven embodied agents and physical systems.

In MotionFence, an AI agent proposes what physical actions should happen, but a deterministic, rule-based runtime engine independently decides whether each physical action is **allowed**, **denied**, or **requires additional evidence** before any physical actuator can move.

### Product Thesis
> **MotionFence does not trust the model, the sensor, or external knowledge independently. It cross-checks evidence, converts relevant knowledge into structured candidate constraints, validates those constraints deterministically, and authorizes physical actions only when the complete policy state permits them.**

*Disclaimer: MotionFence is an architectural research prototype developed for the Nebius x NVIDIA AI Hackathon, not an industrially certified safety-critical SIL-4 controller.*

---

## 2. Why Does It Exist?

Autonomous reasoning models (such as LLMs and vision-language-action models) excel at high-level reasoning and perceptual synthesis, but they are inherently probabilistic. In physical and industrial environments, probabilistic execution is dangerous:

* Visual ambiguity can lead a model to actuate the wrong valve or switch.
* Sensor noise or lens flare can trigger ungrounded emergency procedures.
* Prompt injections or agent delusions can bypass basic prompt-level safety instructions.
* External knowledge bases or online search results may contain stale or conflicting operating instructions.
* Mechanical failures can occur even after a valid command is dispatched.

### Critical Architectural Invariants
1. **Invariant A — External Knowledge is Untrusted**: Retrieved text from Tavily or local manuals is untrusted evidence, not executable policy. It can never directly actuate machinery.
2. **Invariant B — Model Output is Untrusted**: NVIDIA Nemotron / LLMs may propose actions and candidate rules, but possess **zero authority** over WorldState or Actuators.
3. **Invariant C — Deterministic Policy Remains Authoritative**: Physical mutation is gated exclusively by `PolicyEngine -> AuthorizationTicket -> Actuator`.
4. **Invariant D — Verification Remains Independent**: Actuator execution is not proof of success; ground truth is verified independently.

---

## 3. The Core Control Loop

Phase 2A expands the control loop with evidence-grounded knowledge constraints:

```text
External / Local Knowledge (Tavily / SOPs)
        │
        ▼
Knowledge Evidence (Provenance, TrustStatus, Freshness)
        │
        ▼
Candidate Constraint (Structured Pydantic Model)
        │
        ▼
Deterministic Validation (Schema, References, Freshness)
        │
        ▼
Active Policy Constraint (Promoted & Conflict-Checked)
        │
        ▼
Nemotron Action Proposal (Unprivileged)
        │
        ▼
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

## 4. Operational Knowledge & Policy Constraints (Phase 2A)

Phase 2A introduces:
* **Knowledge Providers**: Clean abstraction via `KnowledgeProvider` protocol, supporting:
  - [`LocalKnowledgeProvider`](file:///Users/urjasoft/Documents/MotionFence/motionfence/knowledge/local_provider.py): Deterministic offline synthetic plant manuals (prohibitions, procedures, contradictions, stale sources, missing provenance).
  - [`TavilyKnowledgeProvider`](file:///Users/urjasoft/Documents/MotionFence/motionfence/knowledge/tavily_provider.py): Real Tavily Search API client with timeout safety, credential validation, and provenance retention.
* **KnowledgeEvidence Model**: Structured model capturing `query`, `title`, `source_url`, `content`, `provenance`, `confidence`, `retrieved_at`, and explicit `TrustStatus` (`UNVERIFIED_EXTERNAL`, `LOCAL_FIXTURE`, `VALIDATED`, `STALE`, `REJECTED`).
* **Candidate Constraints**: Extracted via `ConstraintExtractor` into typed models (`PROHIBITION`, `REQUIREMENT`, `PRECONDITION`, `POSTCONDITION`, `INFORMATIONAL`). Harmless operating procedures remain informational and never falsely become prohibitions.
* **Strict Evidence Discipline**: `ConstraintValidator` strictly rejects any constraint citing non-existent evidence IDs (e.g. `kb_hallucinated_999`).
* **Conflict Detection**: `ConstraintConflictDetector` identifies mutual contradictions between knowledge sources (e.g., prohibition vs permissive emergency rule) and flags them as `CONFLICTED`, causing `PolicyEngine` to block execution.
* **Freshness Lifecycle**: Evidence aging beyond configurable thresholds is flagged `STALE`, triggering `NEED_MORE_EVIDENCE` for recertification.

---

## 5. Implementation Status

| Component | Status | Verification State |
| :--- | :--- | :--- |
| **Domain Models & State** | `IMPLEMENTED` | `OFFLINE VERIFIED` (22 tests) |
| **Deterministic Policy Engine** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Policy tests) |
| **Authority Isolation & HMAC Tickets** | `IMPLEMENTED` | `OFFLINE VERIFIED` (7 security tests) |
| **Simulator & Mechanical Verifier** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Simulator tests) |
| **Local Knowledge & Fixtures** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Synthetic manual) |
| **Constraint Extractor & Validator** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Extractor tests) |
| **Conflict & Freshness Engines** | `IMPLEMENTED` | `OFFLINE VERIFIED` (Conflict tests) |
| **Nebius Token Factory / Nemotron** | `IMPLEMENTED` | `LIVE PENDING CREDENTIALS` |
| **Tavily Knowledge Provider** | `IMPLEMENTED` | `LIVE PENDING CREDENTIALS` |
| **Hardware Actuators (ROS 2/GPIO)** | `PLANNED` | Phase 3 |
| **Observability Telemetry Dashboard** | `PLANNED` | Phase 2B |

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

### Environment Configuration (Optional for Live External APIs)
```bash
cp .env.example .env
# Optional: Set NEBIUS_API_KEY and TAVILY_API_KEY when live credentials are available
```

---

## 7. Running Automated Tests

Run the full automated test suite (**63 tests, 100% passing offline**):

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
# Offline deterministic mode with local plant knowledge
python -m motionfence.simulation.demo --provider local --knowledge local
```

### Executed Offline Scenarios:
1. **Scenario 1 (Leak Isolation)**: Ambient wide-angle ambiguity triggers `NEED_MORE_EVIDENCE`; targeted multi-modal thermal/optical inspection resolves target to Valve B; Policy issues `ALLOW`; Actuator closes valve; Verifier confirms `VERIFIED`.
2. **Scenario 2 (Knowledge-Derived Prohibition)**: Knowledge says *"Valve B must not be closed while Pump P1 is active"*; Policy strictly **DENIES** closure; Valve B remains OPEN (no ticket, no actuation).
3. **Scenario 3 (Preconditions Satisfied)**: Pump P1 stopped; prohibition condition ceases to hold; Policy issues `ALLOW`; Valve B safely closed.
4. **Scenario 4 (Harmless Procedure)**: Routine SOP *"Visual inspection should be performed"* classified as `INFORMATIONAL`; does NOT falsely block valid closure.
5. **Scenario 5 (Conflicting Knowledge Sources)**: Standard manual (prohibition) conflicts with emergency guideline (permission); detector flags `CONFLICTED`; execution strictly blocked.
6. **Scenario 6 (Stale Knowledge Handling)**: Archived 90-day-old specification flagged `STALE`; policy forces `NEED_MORE_EVIDENCE` for recertification.

---

## 9. Live Smoke Tests (External Providers)

Live smoke test scripts are included to verify external integrations when credentials become available:

### Nebius Token Factory (NVIDIA Nemotron)
```bash
export NEBIUS_API_KEY="your-nebius-api-key"
python scripts/smoke_nebius.py
```
*(If no key is configured, reports `NEBIUS SMOKE TEST: SKIPPED (No API Key)` and exits safely).*

### Tavily Search API
```bash
export TAVILY_API_KEY="your-tavily-api-key"
python scripts/smoke_tavily.py
```
*(If no key is configured, reports `TAVILY SMOKE TEST: SKIPPED — no API key configured` and exits safely).*

---

## 10. Architectural Documentation

For comprehensive specifications:
* [Architecture Overview](docs/architecture.md): Complete control loop, knowledge retrieval architecture, and sequence flows.
* [Security & Authority Model](docs/security-model.md): Invariant proofs, threat modeling, and authority isolation boundaries.
* [Domain & Knowledge Models](docs/domain-model.md): Detailed schemas for WorldState, KnowledgeEvidence, CandidateConstraint, and Tickets.
* [Demonstration Scenarios](docs/demo-scenario.md): In-depth walkthrough of all 6 physical and knowledge-grounded operational scenarios.

---

## 11. License

MotionFence is licensed under the [MIT License](LICENSE).
