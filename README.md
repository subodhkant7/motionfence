# MotionFence

> **Deterministic Runtime Authorization Layer for AI-Generated Physical Actions**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-41%20passed-brightgreen.svg)](tests/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory%20API-purple.svg)](https://tokenfactory.nebius.com)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron--3--Super--120B-76B900.svg)](https://build.nvidia.com)

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
        NVIDIA Nemotron (Nebius AI)
                      │
                      ▼
              Action Proposal
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
2. **Propose**: The agent system ([`NebiusNemotronProvider`](file:///Users/urjasoft/Documents/MotionFence/motionfence/agent/nebius_provider.py)) formulates an unprivileged [`ActionProposal`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py) with rationale and supporting evidence.
3. **Evaluate Policy**: The [`PolicyEngine`](file:///Users/urjasoft/Documents/MotionFence/motionfence/policy/engine.py) (100% deterministic, **zero LLM code**) checks declarative safety invariants, cross-sensor contradictions, and confidence bounds.
4. **Authorize / Deny / Request Evidence**:
   - `ALLOW`: Mints a cryptographically signed, single-use, time-bounded [`AuthorizationTicket`](file:///Users/urjasoft/Documents/MotionFence/motionfence/models/actions.py).
   - `DENY`: Rejects the action with structured, auditable reasons.
   - `NEED_MORE_EVIDENCE`: Pauses actuation and triggers targeted inspection sensors.
5. **Act**: The [`PhysicalActuator`](file:///Users/urjasoft/Documents/MotionFence/motionfence/simulation/actuator.py) strictly validates the ticket signature, expiration, and target binding before physically moving any mechanism.
6. **Verify**: The [`PostActionVerifier`](file:///Users/urjasoft/Documents/MotionFence/motionfence/runtime/verification.py) compares ground-truth post-state against expected invariants, distinguishing between **command dispatched** and **desired physical outcome verified**.

---

## 4. Nebius Token Factory + NVIDIA Nemotron Integration

MotionFence integrates with **Nebius Token Factory** to serve **NVIDIA Nemotron** models (default: `nvidia/nemotron-3-super-120b-a12b`).

### Key Implementation Principles:
1. **Zero Actuator Authority**: Nemotron serves strictly as a proposal generator. It receives zero actuator handles and zero ticket-signing secrets.
2. **Strict Evidence Discipline**: The provider verifies that every evidence ID cited by the model actually exists in the runtime's evidence registry. Any hallucinated reference is immediately rejected.
3. **Structured Output Validation**: Raw model JSON is validated against strict Pydantic schemas before entering the policy layer.
4. **Bounded Retries & Timeout Safety**: Transient network failures retry with exponential backoff; timeouts fail safely with **zero physical state mutation**.
5. **Offline Safety**: All unit and CI tests run completely offline without requiring network access or `NEBIUS_API_KEY`.

---

## 5. Current Implementation Status

- [x] **Domain Models**: Complete Pydantic v2 schemas for states, evidence, actions, tickets, and verifications.
- [x] **Deterministic Policy Engine**: Full invariant enforcement (confidence threshold, safety zone clearance, cooling preservation, contradiction check).
- [x] **Contradiction Detector**: Multi-sensor discrepancy analyzer comparing disparate modalities (vision vs pressure telemetry).
- [x] **Stateful Physical Simulator**: Miniature plant environment simulating two valves, fluid leak dynamics, cooling loop, safety zones, and mechanical jamming faults.
- [x] **Authority Isolation**: Actuator enforces HMAC-SHA256 authorization tickets; raw unapproved proposals are rejected with [`UnauthorizedActionError`](file:///Users/urjasoft/Documents/MotionFence/motionfence/simulation/exceptions.py).
- [x] **Nebius & NVIDIA Nemotron Integration**: Implemented [`NebiusNemotronProvider`](file:///Users/urjasoft/Documents/MotionFence/motionfence/agent/nebius_provider.py) supporting OpenAI-compatible Token Factory endpoints with bounded retries and evidence validation.
- [x] **Post-Action Verifier**: Ground-truth state verification catching discrepancies and mechanical faults.
- [x] **Automated Test Suite**: 41 automated pytest cases verifying policy, simulator, contradiction, verification, authority isolation, and Nebius provider contracts.
- [x] **Live Smoke Test**: [`scripts/smoke_nebius.py`](file:///Users/urjasoft/Documents/MotionFence/scripts/smoke_nebius.py) for validating live connectivity to Nebius Token Factory.
- [x] **Multi-Scenario Terminal Demo**: Interactive terminal demo illustrating leak isolation, safety zone incursion, and contradiction detection.

### Planned Subsequent Enhancements
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

### Environment Configuration (Optional for Live Nebius Inference)
```bash
cp .env.example .env
# Edit .env and set your Nebius Token Factory API key:
# NEBIUS_API_KEY="your-token-factory-key"
```

---

## 7. Running the Simulator Demonstration

Execute the interactive multi-scenario terminal demonstration:

```bash
# Offline deterministic mode (no API key required)
python -m motionfence.simulation.demo --provider local

# Live Nebius Token Factory mode (requires NEBIUS_API_KEY)
export NEBIUS_API_KEY="your-key"
python -m motionfence.simulation.demo --provider nebius
```

### Demonstration Scenarios:
1. **Scenario 1 (Leak Isolation)**: Ambient wide-angle ambiguity triggers `NEED_MORE_EVIDENCE`; targeted multi-modal thermal/optical inspection resolves target to Valve B; Policy issues `ALLOW`; Actuator closes valve; Verifier confirms `VERIFIED`.
2. **Scenario 2 (Safety Incursion)**: Human enters safety zone; Model proposes `CLOSE_VALVE`; Policy strictly **DENIES** actuation; Physical world state remains unaltered.
3. **Scenario 3 (Contradiction Detection)**: Vision detects leak, but pressure sensor reports normal line pressure; Policy detects high-severity contradiction and **DENIES** actuation.

---

## 8. Running the Live Nebius Smoke Test

To verify connectivity with Nebius Token Factory and NVIDIA Nemotron:

```bash
export NEBIUS_API_KEY="your-nebius-api-key"
python scripts/smoke_nebius.py
```

---

## 9. Running Automated Tests

Run the full automated test suite (41 tests, runs completely offline):

```bash
pytest
```

Or run via the convenience script:

```bash
./scripts/run_tests.sh
```

---

## 10. Documentation

For detailed architectural and design specifications:
* [Architecture Overview](docs/architecture.md): System decomposition, sequence flow diagrams, and Nebius integration architecture.
* [Security & Authority Model](docs/security-model.md): Threat modeling, actuator isolation, and cryptographic ticket verification.
* [Domain Models](docs/domain-model.md): Field-level schema definitions for WorldState, Evidence, Policy, and Verification.
* [Demo Scenario](docs/demo-scenario.md): In-depth walkthrough of the industrial leak isolation scenario and failure modes.

---

## 11. License

MotionFence is licensed under the [MIT License](LICENSE).
