# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-29%20passed-brightgreen.svg)](tests/)

Built for the **Nebius x NVIDIA Global AI Hackathon 2026** (Physical AI Track).

---

## 1. What is MotionFence?

**MotionFence** is an independent, deterministic runtime authorization gateway governing AI-driven embodied agents and physical systems.

In MotionFence, an AI agent proposes what physical actions should happen, but a deterministic, rule-based runtime engine independently decides whether each physical action is **allowed**, **denied**, or **requires additional evidence** before any physical actuator can move.

---

## 2. Why Does It Exist?

Autonomous reasoning models (such as LLMs and vision-language-action models) excel at high-level reasoning and perceptual synthesis, but they are inherently probabilistic. In physical and industrial environments, probabilistic execution is dangerous:

* Visual ambiguity can lead a model to actuate the wrong valve or switch.
* Sensor noise or lens flare can trigger ungrounded emergency procedures.
* Prompt injections or agent delusions can bypass basic prompt-level safety instructions.
* Mechanical failures can occur even after a valid command is dispatched.

**Core Architectural Invariant**:
> **An LLM must never have direct authority over an actuator.**
> The model proposes actions and interprets evidence; deterministic, un-bypassable MotionFence code controls physical execution authority.

---

## 3. The Core Control Loop

MotionFence operates via a strict 6-stage lifecycle:

```text
                 Human Intent
                      │
                      ▼
              Agent / Proposal
                      │
                      ▼
              Evidence Model
                      │
                      ▼
             Policy Evaluation
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        DENY     NEED_EVIDENCE   ALLOW
                                      │
                                      ▼
                               Action Runtime
                                      │
                                      ▼
                              World / Actuator
                                      │
                                      ▼
                               Verification
                                      │
                                      ▼
                              Verified Outcome
```

1. **Observe**: Ingest physical observations (visual, thermal, pressure, zone safety) with explicit confidence scores and sensor provenance.
2. **Propose**: The agent system formulates an unprivileged [`ActionProposal`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py) with rationale and supporting evidence.
3. **Evaluate Policy**: The [`PolicyEngine`](file:///Users/urjasoft/Documents/MotionFence/motionfence/policy/engine.py) (100% deterministic, **zero LLM code**) checks declarative safety invariants, cross-sensor contradictions, and confidence bounds.
4. **Authorize / Deny / Request Evidence**:
   - `ALLOW`: Mints a cryptographically signed, single-use, time-bounded [`AuthorizationTicket`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py).
   - `DENY`: Rejects the action with structured, auditable reasons.
   - `NEED_MORE_EVIDENCE`: Pauses actuation and triggers targeted inspection sensors.
5. **Act**: The [`PhysicalActuator`](file:///Users/urjasoft/Documents/MotionFence/motionfence/simulation/actuator.py) strictly validates the ticket signature, expiration, and target binding before physically moving any mechanism.
6. **Verify**: The [`PostActionVerifier`](file:///Users/urjasoft/Documents/MotionFence/motionfence/runtime/verification.py) compares ground-truth post-state against expected invariants, distinguishing between **command dispatched** and **desired physical outcome verified**.

---

## 4. Current Status (Phase 0)

Phase 0 establishes the core software-first foundation of MotionFence with zero external hardware requirements:

- [x] **Domain Models**: Complete Pydantic v2 domain schemas ([`WorldState`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/world.py), [`Evidence`](file:///Users/urjasoft/Documents/MotionFence/motionfence/evidence/models.py), [`ActionProposal`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py), [`Policy`](file:///Users/urjasoft/Documents/MotionFence/motionfence/policy/models.py), [`PolicyDecision`](file:///Users/urjasoft/Documents/MotionFence/motionfence/policy/models.py), [`VerificationResult`](file:///Users/urjasoft/Documents/MotionFence/motionfence/runtime/verification.py)).
- [x] **Deterministic Policy Engine**: Full invariant enforcement (confidence threshold, safety zone clearance, cooling preservation, contradiction check).
- [x] **Contradiction Detector**: Multi-sensor discrepancy analyzer comparing disparate modalities (vision vs pressure telemetry).
- [x] **Stateful Physical Simulator**: Miniature plant environment simulating two valves, fluid leak dynamics, cooling loop, safety zones, and mechanical jamming faults.
- [x] **Authority Isolation**: Actuator enforces HMAC-SHA256 authorization tickets; raw unapproved proposals are rejected with [`UnauthorizedActionError`](file:///Users/urjasoft/Documents/MotionFence/motionfence/simulation/exceptions.py).
- [x] **Post-Action Verifier**: Ground-truth state verification catching discrepancies and mechanical faults.
- [x] **Automated Test Suite**: 29 automated pytest cases verifying policy, simulator, contradiction, verification, and authority isolation invariants.
- [x] **Interactive Demonstration**: End-to-end runnable terminal demo illustrating the complete leak isolation workflow.

---

## 5. Planned Integrations

The following integrations are intentionally architected behind clean interfaces for subsequent phases and are **not yet implemented**:

* `PLANNED`: **Nebius Token Factory / NVIDIA Nemotron**: Remote LLM provider implementing the [`ActionProposalProvider`](file:///Users/urjasoft/Documents/MotionFence/motionfence/agent/provider.py) protocol via Nebius AI Cloud.
* `PLANNED`: **Tavily SOP Knowledge Retrieval**: Knowledge provider retrieving engineering plant standard operating procedures via Tavily.
* `PLANNED`: **Hardware Adapter Layer**: ROS 2 / Modbus / GPIO bridge to physically actuate servo valves without altering the core policy architecture.
* `PLANNED`: **Web Telemetry UI**: Real-time observability dashboard consuming MotionFence [`RuntimeEvent`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/events.py) streams.

---

## 6. Quickstart & Installation

### Prerequisites
* Python 3.12 or Python 3.13
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

## 7. Running the Simulator Demonstration

Execute the interactive end-to-end physical simulation demo:

```bash
python -m motionfence.simulation.demo
```

### Expected Output Summary:
1. **Human Intent**: *"Isolate the leaking line while keeping cooling active."*
2. **Ambient Observation**: Wide-angle cameras observe both Valve A (conf `0.74`) and Valve B (conf `0.78`).
3. **Proposal 1**: Agent proposes `CLOSE_VALVE` on Valve B with confidence `0.78`.
4. **Policy Decision 1**: **`NEED_MORE_EVIDENCE`** (target confidence `0.78 < 0.90` required). Actuation is blocked.
5. **Targeted Inspection**: PTU thermal camera (conf `0.96`) and zoom optical camera (conf `0.95`) confirm Valve B leak.
6. **Policy Decision 2**: **`ALLOW`** (all invariants and confidence satisfied).
7. **Execution**: Runtime issues HMAC-signed [`AuthorizationTicket`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py); actuator physically transitions Valve B to `CLOSED`.
8. **Verification**: Ground-truth physical state inspected: Valve B `CLOSED`, Cooling `ACTIVE`, Leak `RESOLVED` → **`VERIFIED`**.

---

## 8. Running Automated Tests

Run the full automated test suite covering security invariants, simulator physics, policy rules, and verification:

```bash
pytest
```

Or run via the convenience script:

```bash
./scripts/run_tests.sh
```

---

## 9. Documentation

For detailed architectural and design specifications:
* [Architecture Overview](docs/architecture.md): System decomposition, execution sequence diagrams, and module boundaries.
* [Security & Authority Model](docs/security-model.md): Threat modeling, actuator isolation, and cryptographic ticket verification.
* [Domain Models](docs/domain-model.md): Field-level schema definitions for WorldState, Evidence, Policy, and Verification.
* [Demo Scenario](docs/demo-scenario.md): In-depth walkthrough of the industrial leak isolation scenario and failure modes.

---

## 10. License

MotionFence is licensed under the [MIT License](LICENSE).
