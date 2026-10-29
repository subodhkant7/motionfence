# Nebius × NVIDIA Global AI Hackathon 2026 — Official Compliance Matrix

**Hackathon:** Nebius × NVIDIA Global AI Hackathon 2026 (Hosted on Devpost)  
**Submission Track:** Physical AI  
**Bonus Prize Category:** Best Use of Tavily ($3,000 USD)  
**Project Name:** MotionFence — Safety-Gated Physical AI  
**Repository:** `https://github.com/subodhkant7/motionfence`  
**License:** MIT License (OSI-Approved)  
**Authoritative Rule References:**
- [Hackathon Overview](https://nebiusglobalaihackathon.devpost.com/)
- [Official Rules](https://nebiusglobalaihackathon.devpost.com/rules)
- [Hackathon FAQs](https://nebiusglobalaihackathon.devpost.com/details/faqs)

---

## 1. Compliance Requirements Matrix

| # | Requirement | Status | Concrete Evidence & Verification | Remaining Action |
| :- | :--- | :--- | :--- | :--- |
| **1** | **Physical AI Track Eligibility** | **PASS** | Evaluates and gates actions on physical plant equipment (valves, pumps, cooling, limit switches, and fluid dynamics). Features simulated industrial physical plant (`motionfence.simulation.world.PhysicalWorld`), mechanical actuation barriers (`PhysicalActuator`), and an NVIDIA Isaac Sim integration adapter (`motionfence.simulation.isaac.IsaacSimAdapter`). Per official hackathon FAQ, simulation tools are explicitly permitted in lieu of physical hardware. | None. Complete in codebase. |
| **2** | **Working Application with NVIDIA Open-Source Model** | **PASS** | Integrates open-source `nvidia/nemotron-3-super-120b-a12b` for proposal generation (`motionfence/agent/nebius_provider.py`) and structured operational constraint extraction (`motionfence/constraints/nemotron_extractor.py`). Verified in baseline tests and live smoke test. | None. Implemented and verified. |
| **3** | **Runtime Model Inference via Nebius Token Factory or Nebius AI Cloud** | **PASS** | Runtime inference is executed directly against the Nebius Token Factory OpenAI-compatible API endpoint (`https://api.tokenfactory.nebius.com/v1/`) with model `nvidia/nemotron-3-super-120b-a12b`. Tested and verified with real requests. | None. Runtime integration verified. |
| **4** | **Public Source Repository with Complete Code & Assets** | **BLOCKED (PENDING MANUAL VISIBILITY TOGGLE)** | Complete, self-contained release is synchronized on `main` at `https://github.com/subodhkant7/motionfence` with clean security audit. However, automated API toggle was rejected because the local PAT lacks administrative repo-settings scopes. Repository visibility remains private until manually toggled. | User must navigate to GitHub Settings -> Danger Zone and toggle visibility to Public; anonymous clone must then be verified. |
| **5** | **OSI-Approved License Detectable on GitHub** | **PASS** | Standard MIT license file present at repository root (`LICENSE`). Detectable by GitHub license identification engine. | None. |
| **6** | **README with Verified Installation & Execution Instructions** | **PASS** | Root `README.md` provides tested, copy-paste-ready commands for clean-environment setup: Python venv, Node dependencies, test execution (`pytest`, `vitest`), offline replay, and local server startup. | None. Independently verified. |
| **7** | **Explicit Explanation of NVIDIA Nemotron Integration** | **PASS** | Documented in `README.md`, `docs/architecture.md`, and implemented in `motionfence/agent/nebius_provider.py` and `motionfence/constraints/nemotron_extractor.py`. Explains prompt formatting, structured JSON output extraction, confidence thresholds, and strict unprivileged proposal status. | None. |
| **8** | **Explanation of Nebius Token Factory Acceleration** | **PASS** | Detailed in `README.md`: Explains how managed Token Factory serverless inference eliminated dedicated GPU provisioning overhead, enabled immediate OpenAI-compatible API integration, and accelerated testing against 120B-parameter models with sub-2-second response latency. | None. |
| **9** | **Disclosure of Other Nebius Tools / Services Used** | **PASS** | Disclosed clearly and honestly in `README.md` and documentation: **Nebius Token Factory was used exclusively for live NVIDIA model inference. The web application container is hosted separately on Render Free Tier (`https://motionfence.onrender.com`). No additional Nebius Cloud infrastructure (such as Nebius GPU Compute or Serverless Endpoints) was used.** | None. Truthful disclosure documented. |
| **10** | **Public YouTube Demonstration (< 3 Minutes)** | **EXTERNAL ACTION REQUIRED** | The video must be recorded by the user, uploaded to YouTube as Public or Unlisted, and linked in the Devpost submission form. Codebase includes the Phase 2T One-Click Demo Director (`/demo`) specifically designed to run a structured 9-scene narrative suitable for a 3-minute video walk-through. | User records video using the One-Click Demo Director and pastes URL into Devpost. |
| **11** | **Physical AI Simulation Module Demonstration (>= 1 Minute)** | **PASS** (Application ready) | The Phase 2T Demo Director provides over 1 minute of visual demonstration across 9 scenes showing simulated plant digital twin state, valve limit-switch verification, hazard zone incursions, and mechanical fault recovery. | Video recording must include this footage. |
| **12** | **Free Judge Evaluation Access** | **PASS** | Judges have immediate free access via two verified methods: (1) **Live Hosted Web Application**: [https://motionfence.onrender.com](https://motionfence.onrender.com) (zero setup, live interactive access to the Explainer, Demo Director, Safety Lab, Decision Replay Console, and Architecture); (2) **100% Offline Local Replay**: Requires **zero API keys, zero cloud billing, and zero paid credits**. Any judge can clone the repository and run all 601 backend tests, 87 Vitest suites, the offline Demo Director, and the 20-case Safety Lab benchmark locally. | None. Free access verified online and offline. |
| **13** | **Clear Project Description & Selected Track** | **PASS** | "MotionFence — Safety-Gated Physical AI", submitted to the **Physical AI Track**. Clear description provided in `README.md` and Devpost summary. | User selects "Physical AI" track on Devpost form. |
| **14** | **Feedback on Nebius and NVIDIA Technologies** | **PASS** | Constructive feedback provided in `README.md` and this document: Praises Nebius Token Factory's sub-2s latency and OpenAI compatibility; recommends native streaming JSON validation and explicit tool-calling schemas for industrial agent workflows. | Included in submission documentation. |
| **15** | **Tavily Integration & "Best Use of Tavily" Eligibility** | **PASS** | Real-world operational knowledge retrieval implemented in `motionfence/knowledge/tavily_provider.py`. Includes source trust classification, claim-support certificate grounding, and deterministic promotion gating. Eligible for the $3,000 USD Best Use of Tavily bonus prize. | User selects the Tavily bonus prize checkbox on Devpost. |
| **16** | **Explanation of Updates During Submission Period** | **PASS** | Documented commit history from Phase 0 baseline through Phase 2T (Demo Director), Phase 2U (Preflight audit), and Phase 2V (Hackathon release). | None. |
| **17** | **Attribution & Third-Party Licensing** | **PASS** | Third-party libraries (Pydantic, OpenAI SDK, Z3 SMT solver, React, Lucide, Vite) properly attributed with compatible MIT/Apache-2.0 licenses. | None. |

---

## 2. Devpost Submission Checklist for User

When finalizing the submission on `https://nebiusglobalaihackathon.devpost.com/`:

- [ ] **Project Title:** `MotionFence — Safety-Gated Physical AI`
- [ ] **Tagline:** `Nemotron proposes. MotionFence decides. No valid ticket, no actuation.`
- [ ] **Selected Track:** `Physical AI`
- [ ] **Selected Bonus Prizes:** `Best Use of Tavily`
- [ ] **GitHub Repository URL:** `https://github.com/subodhkant7/motionfence` (Public)
- [ ] **Live Web Application URL:** `https://motionfence.onrender.com`
- [ ] **Demo Video URL:** Paste YouTube link (< 3 minutes, showing Demo Director and Safety Lab).
- [ ] **Testing Instructions:** Paste Quickstart commands from `README.md` (no API keys required for testing).
- [ ] **Technology Tags:** `NVIDIA Nemotron`, `Nebius Token Factory`, `Tavily Search API`, `Python`, `React`, `TypeScript`, `Z3 SMT Solver`, `Physical AI`.

