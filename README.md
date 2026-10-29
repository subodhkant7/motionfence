# MotionFence — Safety-Gated Physical AI

> **Nemotron proposes. MotionFence decides. No valid ticket, no actuation.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Backend Tests](https://img.shields.io/badge/pytest-601%20passed-success.svg)](tests/)
[![Frontend Tests](https://img.shields.io/badge/vitest-87%20passed-success.svg)](console/src/test/)
[![Safety Benchmark](https://img.shields.io/badge/Safety%20Lab-20%2F20%20passed-brightgreen.svg)](motionfence/benchmark/)
[![Nebius Token Factory](https://img.shields.io/badge/Nebius-Token%20Factory-purple.svg)](https://nebius.com/)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron%20120B-76B900.svg)](https://build.nvidia.com/)
[![Tavily Search](https://img.shields.io/badge/Tavily-Search%20API-orange.svg)](https://tavily.com/)
[![Render Deployment](https://img.shields.io/badge/Render-Live%20Demo-brightgreen.svg)](https://motionfence.onrender.com)

**MotionFence** is an open-source, deterministic runtime authorization gateway for AI-proposed actions in physical and industrial environments. It introduces a strict zero-authority boundary: probabilistic Large Language Models propose actions and extract constraints, but **never possess execution credentials, cannot command actuators, and cannot override deterministic safety policy**.

Every physical mutation requires an authenticated, single-use, state-bound cryptographic ticket verified immediately prior to execution and checked against independent physical ground truth post-action.

---

## Live Production Deployment

MotionFence is deployed and live on Render's Free tier in the Singapore region:

- **Public Web Application**: [https://motionfence.onrender.com](https://motionfence.onrender.com)
- **One-Click Demo Director**: [https://motionfence.onrender.com/demo](https://motionfence.onrender.com/demo) (or [/?director=1](https://motionfence.onrender.com/?director=1))
- **Quantitative Safety Lab**: [https://motionfence.onrender.com/safety-lab](https://motionfence.onrender.com/safety-lab)
- **Decision Replay Console**: [https://motionfence.onrender.com/console](https://motionfence.onrender.com/console)
- **System Architecture Deep Dive**: [https://motionfence.onrender.com/architecture](https://motionfence.onrender.com/architecture)
- **Health & Readiness Probe**: [https://motionfence.onrender.com/health](https://motionfence.onrender.com/health)

### Deployment Architecture & Spending Guardrails
- **Hosting Tier**: Render Free Web Service (Docker container runtime, single instance, 512 MB RAM, spins down after 15 minutes of inactivity).
- **Outcome Integrity Contract**: The runtime enforces strict fail-closed outcome states: `NOMINAL`, `DENIED`, `BLOCKED`, `RECOVERED`, `VERIFICATION_FAILED`, `UNVERIFIED`, and `UNKNOWN`. An action is never assumed verified simply because it was dispatched or simulated.
- **Public Cost Boundary**: In public cloud mode, demo executions run under deterministic offline replay (`execution_mode=OFFLINE_DETERMINISTIC_REPLAY`), preventing unauthorized third-party billing while preserving full cryptographic provenance hashing and identical safety guarantees. Live API calls remain strictly bounded to authenticated administrative runs.

---

## What Makes MotionFence Different

High-consequence physical systems (chemical valves, robotic manipulators, emergency pumps) cannot tolerate probabilistic hallucinations, latent state drift, or ungrounded retrieval claims.

```
┌─────────────────────────────── PROBABILISTIC AI (UNPRIVILEGED) ───────────────────────────────┐
│                                                                                               │
│   NVIDIA Nemotron 120B                Tavily Search API                 USGS Streamflow       │
│  (Action Proposals / Rules)        (Operational Knowledge)             (Public Telemetry)     │
│             │                                 │                                │              │
└─────────────┼─────────────────────────────────┼────────────────────────────────┼──────────────┘
              ▼                                 ▼                                ▼
┌─────────────┴─────────────────────────────────┴────────────────────────────────┴──────────────┐
│ MOTIONFENCE ZERO-AUTHORITY GATEWAY                                                            │
│                                                                                               │
│  1. Lexical Grounding Gate: Verify candidate constraints against raw source text certificates │
│  2. Deterministic Policy Engine: Hard safety invariants + sensor contradiction analysis       │
│  3. Safety Enclave: Mints single-use HMAC-SHA256 AuthorizationTicket bound to plant hash v3   │
│  4. Pre-Stroke TOCTOU Revalidation: World state checked at t_exec; aborts if plant drifted v4 │
│  5. Physical Boundary: Actuator executes ONLY with valid cryptographic ticket                 │
│  6. Independent Post-Action Verification: Limit-switch readback checked against ground truth  │
│  7. Autonomous Recovery: Linkage fault detected -> quarantine valve -> fresh authorization    │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Probabilistic Proposals vs. Deterministic Authorization**: The AI model has zero credentials and cannot directly call hardware.
2. **Empirical Evidence Grounding**: Retrieved documentation is evidence, not policy. Claims require cryptographic `ClaimSupportCertificate` lexical verification before promotion.
3. **HMAC-SHA256 State-Bound Tickets**: Single-use execution tickets are cryptographically bound to a specific plant version hash.
4. **Pre-Stroke TOCTOU Revalidation**: Defends against modeled Time-of-Check to Time-of-Use state drift. If simulated plant conditions drift between proposal and actuation (e.g. a worker enters the modeled hazard zone), pre-stroke revalidation detects the version hash mismatch and aborts execution.
5. **Post-Action Verification & Modeled Recovery**: Actuator command dispatch does not equal physical success. Independent simulated limit-switch checks detect modeled mechanical failures (e.g. solenoid jams) and trigger autonomous safe recovery.
6. **Zero-Authority Replay & Formal SMT Assurance**: 100% deterministically reproducible offline with sub-millisecond execution, paired with 60 bounded temporal safety invariants verified over modeled transitions via the Z3 SMT solver.

---

## NVIDIA & Nebius Implementation

MotionFence integrates the open-source **`nvidia/nemotron-3-super-120b-a12b`** model running on the **Nebius Token Factory** managed inference platform.

- **NVIDIA Open Model**: `nvidia/nemotron-3-super-120b-a12b`
- **Inference Provider**: Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1/`)
- **Agent Integration**: [`motionfence/agent/nebius_provider.py`](motionfence/agent/nebius_provider.py)
- **Constraint Extractor**: [`motionfence/constraints/nemotron_extractor.py`](motionfence/constraints/nemotron_extractor.py)

### How Nebius Token Factory Accelerated Development
1. **Serverless Managed Inference**: Allowed immediate development and real-time testing against a massive 120-billion-parameter model without provisioning, managing, or idling expensive dedicated GPU nodes.
2. **OpenAI API Compatibility**: Standard OpenAI-compatible protocol allowed frictionless integration using standard Python SDKs.
3. **Rapid Iteration & Low Latency**: In our Phase 2Q live validation benchmarks, Nebius Token Factory demonstrated observed average response latencies of **~1.86 seconds** across 10 real queries with strict token output capping (9,654 total tokens processed).
4. **Cost-Aware Safety Limits**: Token output limits (`max_output_tokens=600`) and structured schema prompts prevented token runaways during development.

> **Infrastructure Disclosure**: Nebius Token Factory was used for live NVIDIA model inference. The full-stack web application is hosted publicly on Render ([https://motionfence.onrender.com](https://motionfence.onrender.com)). No additional Nebius Cloud infrastructure (such as Nebius GPU Compute or Serverless Endpoints) was used.

---

## Tavily Operational Knowledge Search Integration

MotionFence integrates the **Tavily Search API** ([`motionfence/knowledge/tavily_provider.py`](motionfence/knowledge/tavily_provider.py)) to discover and retrieve operational engineering documentation, standard operating procedures (SOPs), and equipment safety manuals.

- **Role Separation**: Retrieved web documents are treated as untrusted discovery evidence, **never** as executable policy.
- **Source Trust Classification**: Evaluates source domains into structured origin tiers (`FIRST_PARTY_OFFICIAL`, `STANDARDS_BODY`, `VENDOR_MANUAL`, `THIRD_PARTY_MIRROR`).
- **Deterministic Claim Grounding**: `LocalDeterministicClaimGrounder` issues a `ClaimSupportCertificate` confirming extracted candidate rules have direct lexical support in source text before promotion to active policy.
- **Observed Validation Metrics**: During Phase 2Q live validation runs, Tavily handled 10 operational search queries with an average response latency of **~2.96 seconds**.
- **Controlled Demo Fallback**: When live Tavily credentials are omitted or network search is disabled, the controlled demo and Safety Lab safely fall back to versioned offline fixtures (`offline_fixture`), labeled transparently in the UI.

---

## Physical AI Simulation & Limitations

MotionFence targets industrial physical AI applications where software directly influences the physical world:

- **Simulated Industrial Plant**: In-memory digital twin (`motionfence/simulation/world.py`) simulating double-isolation pipe branches, isolation valves, emergency pumps, cooling loops, limit switches, and vapor plume dynamics.
- **Mock Hardware Boundary**: Hardware interface (`motionfence/hardware/mock.py`) enforcing single-use HMAC-SHA256 authorization ticket consumption and atomic concurrency barriers.
- **Fault Injection**: Modeled mechanical linkage faults (`NO_OP`), solenoid jams, limit-switch discrepancies, and post-actuation fluid leaks.
- **NVIDIA Isaac Sim Integration Contract**: [`motionfence/simulation/isaac/adapter.py`](motionfence/simulation/isaac/adapter.py) provides a contract-verified adapter for OpenUSD industrial scenes (`isaac_sim/motionfence_industrial_cell.usda`).

> [!IMPORTANT]
> **Simulation Boundary Disclosure**: Native NVIDIA Isaac Sim execution and actual physical industrial actuator wiring (PLCs, Modbus, GPIO) have **not** been connected. All actuation, sensor readbacks, and post-action checks run in software simulation. The web-based 3D viewport is an in-browser digital twin representation, not native Isaac Sim.

---

## Safety Lab & Quantitative Benchmark Results

MotionFence features a reproducible **20-case quantitative safety benchmark** ([`motionfence/benchmark/`](motionfence/benchmark/)) evaluating system resilience across 11 adversarial variants, TOCTOU state drifts, and actuator linkage faults:

| Evaluation Metric | Ratio / Denominator | Result | Description |
| :--- | :--- | :--- | :--- |
| **Benchmark Scenarios Passing** | **20 / 20** | **100%** | Full suite execution under deterministic replay |
| **Unsafe Simulated Actuations** | **0 / 12** | **0% (100% blocked)** | Hazard zone, cooling violations, and drift blocked |
| **False Verifications** | **0 / 2** | **0% (100% detected)** | Mechanical stroke faults and limit mismatches caught |
| **False Denials on Safe Proposals** | **0 / 4** | **0% (100% permitted)** | Valid safe isolation proposals successfully approved |
| **Fail-Closed Gate Cases** | **7 / 7** | **100% fail-closed** | Missing tickets, bad signatures, and drift fail closed |
| **Independent Verification Coverage**| **7 / 7** | **100% verified** | Every executed action independently post-verified |

*These metrics reflect software simulation tests under modeled conditions and do not constitute real-world industrial SIL certification.*

---

## Verified Installation & Quickstart

MotionFence is completely self-contained. **No API keys, cloud billing, or network access are required** to run tests, replay demonstrations, or launch the application in offline deterministic mode.

### 1. Prerequisites
- **Python**: 3.12 or higher
- **Node.js**: 20 or higher (with npm)
- **Git**

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone https://github.com/subodhkant7/motionfence.git
cd motionfence

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python package in editable mode with test and Z3 assurance dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# Install frontend dependencies
npm --prefix console ci
```

### 3. Run Automated Quality Gates
```bash
# Run all 601 backend unit, integration, and security tests
.venv/bin/pytest -q

# Run all 87 frontend Vitest component tests
npm --prefix console test -- --run

# Run frontend linter
npm --prefix console run lint

# Build production frontend bundle
npm --prefix console run build
```

### 4. Run Offline Demonstrations & Formal Verification
```bash
# Run the 20-scenario reproducible Safety Lab benchmark
.venv/bin/python scripts/run_safety_benchmark.py

# Verify 60 bounded temporal safety properties with the Z3 SMT solver
.venv/bin/python scripts/run_assurance.py

# Run standalone offline CLI safety scenario demonstration
.venv/bin/python scripts/run_demo.py
```

### 5. Launch the Application Locally
In two terminal windows:

```bash
# Terminal 1: Launch backend console server (serves API and offline fixtures)
.venv/bin/python scripts/console_server.py --host 127.0.0.1 --port 8080

# Terminal 2: Launch Vite development server
npm --prefix console run dev
```

Open your browser to **`http://localhost:5173/`** to explore the interactive interface.

---

## Application Views & Navigation

The MotionFence frontend provides five specialized views:

| URL Route | Interface | Purpose |
| :--- | :--- | :--- |
| **`/`** | **Product Explainer** | Interactive architectural walkthrough, system thesis, and interactive FAQ |
| **`/demo`** (or `/?director=1`) | **One-Click Demo Director** | Automated 9-scene guided demonstration of the entire safety lifecycle |
| **`/safety-lab`** | **Public Safety Lab** | Quantitative 20-scenario benchmark dashboard with SHA-256 evidence bundles |
| **`/console`** | **Judge Replay Console** | Chronological 10-stage decision inspector, HMAC ticket cards, and SMT proofs |
| **`/architecture`** | **Architecture Deep-Dive** | Threat model, fail-closed boundaries, and cryptographic invariants |

---

## Optional Live Integrations

To run live inference with Nebius Token Factory or live search with Tavily, copy `.env.example` to `.env` and provide your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
MOTIONFENCE_ENV=development
MOTIONFENCE_KERNEL_SECRET=replace_with_random_32_plus_char_secret_for_tickets

# Nebius Token Factory (NVIDIA Nemotron Inference)
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b

# Tavily Search API (Operational Knowledge Retrieval)
TAVILY_API_KEY=your_tavily_api_key_here
```

> [!WARNING]
> Live inference scripts (`scripts/live_nebius_demo.py`, `scripts/live_validation.py`) make outbound requests to external APIs that consume live account credits. Never commit `.env` or secret keys to version control.

---

## Safety & Assurance Disclosure

MotionFence is an experimental software research prototype developed for the **Nebius × NVIDIA Global AI Hackathon 2026**.

- It is **not** certified under IEC 61508 (Functional Safety) or ISO 13849 (Safety of Machinery).
- It must **not** be connected directly to hazardous physical machinery without certified physical emergency-stop interlocks and hardware safety PLCs.
- Actuator execution, limit switches, and sensor readbacks operate in software simulation.
- Formal mathematical verification using the Z3 SMT solver guarantees correctness over the specified symbolic models and bounded discrete horizons ($H = 1..5$), not physical electrical circuits or real-world physics.

---

## Documentation & Repository Structure

- [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) — Authoritative implementation status matrix.
- [`docs/architecture.md`](docs/architecture.md) — System architecture, control loops, and subsystem boundaries.
- [`docs/security-model.md`](docs/security-model.md) — Cryptographic threat model, zero-authority invariants, and audit trails.
- [`docs/domain-model.md`](docs/domain-model.md) — Plant state, sensor representations, and ticket specifications.
- [`docs/demo-scenario.md`](docs/demo-scenario.md) — Detailed scenario catalog across all baseline and adversarial variants.
- [`LICENSE`](LICENSE) — Open-source MIT License.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
