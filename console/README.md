# MotionFence Web Console & Public Interface

The MotionFence frontend is a zero-authority, read-only single-page application (SPA) built with React 19, TypeScript, and Vite. It serves as the primary visual interface for judges, researchers, and operators to inspect AI-proposed industrial actions, deterministic policy evaluations, cryptographic authorization tickets, pre-actuation revalidation barriers, and post-action verification outcomes.

---

## Key Views and Application Routes

The frontend provides five integrated views accessible via routing or navigation controls:

| Route | View Component | Description |
| :--- | :--- | :--- |
| **`/`** | `LandingPage` | **Product Explainer & Overview**: Core thesis, interactive architecture diagram, live Nemotron proposal flow, and security FAQs. |
| **`/demo`** (or `/?director=1`) | `DemoDirector` | **One-Click Demo Director (Phase 2T)**: Automated 9-scene guided demonstration walking through the entire safety lifecycle. |
| **`/safety-lab`** | `SafetyLabView` | **Public Safety Lab & Benchmark Dashboard**: 20-case quantitative benchmark suite, cryptographic disclosures, and scenario inspector. |
| **`/console`** | `DecisionReplay`, `PolicyFirewall`, `TrajectoryViewer`, `AssurancePanel` | **Interactive Judge Console**: Deep-dive inspection of chronological decision stages, HMAC ticket signatures, state drift, and Z3 SMT proofs. |
| **`/architecture`** | `LandingPage` (Architecture section) | **Zero-Authority Architecture & Threat Model**: Detailed breakdown of trust boundaries, fail-closed guarantees, and cryptographic invariants. |

---

## Core Security Invariant: Zero Browser Authority

In alignment with the core MotionFence security principles:
1. **Zero Execution Authority**: The web interface has no credentials, cannot mint `AuthorizationTicket` objects, and cannot directly invoke physical actuators.
2. **Fixed Scenario Allowlists**: Demonstration runs are strictly limited to canonical pre-approved scenarios (`safe`, `denied`, `toctou`, `recovery`, `telemetry`, `evidence`).
3. **Transparent Execution Labeling**: The interface explicitly distinguishes between `LIVE` inference (via Nebius Token Factory), `REPLAY` (100% offline deterministic fixtures), and simulated actuator outcomes.

---

## Technology Stack

- **Framework**: React 19 (`react`, `react-dom`)
- **Language**: TypeScript (`tsc -b`)
- **Build System**: Vite 8 (`vite build`)
- **Linter**: Oxlint (`oxlint`)
- **Test Framework**: Vitest (`vitest run`) with `@testing-library/react` and `jsdom`
- **Iconography**: Lucide React (`lucide-react`)

---

## Development & Testing Workflow

### Prerequisites
- Node.js 20+ (LTS recommended)
- npm 10+

### Installation
Install dependencies deterministically using `npm ci`:
```bash
npm ci
```

### Running Automated Tests
Execute the Vitest component and integration test suite:
```bash
npm test
```
*Current test suite: 68 tests passing across 6 test files.*

### Linting
Run the fast Oxlint linter:
```bash
npm run lint
```

### Production Build
Compile and bundle the production SPA into `dist/`:
```bash
npm run build
```

### Local Development Server
Start the Vite development server with Hot Module Replacement (HMR):
```bash
npm run dev
```
The console will be accessible at `http://localhost:5173/`. When run alongside the Python backend server (`scripts/console_server.py`), API requests are proxied seamlessly to port 8080.
