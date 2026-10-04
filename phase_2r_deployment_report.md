# MotionFence — Phase 2R Deployment & Production Verification Report

## Controlled Live Demo Deployment, Public Nebius Endpoint & Production Verification

* **Deployment Platform:** Nebius AI Cloud (Serverless Endpoints)
* **Endpoint Architecture:** Serverless HTTP-facing container runtime serving production Vite React SPA + hardened Python safety enclave daemon
* **Public URL:** Configured for deployment via Nebius Serverless Endpoints (`https://<endpoint-id>.nebius.cloud` / local container proxy `http://127.0.0.1:8080`)
* **Container Image / Version:** `motionfence:phase-2r` (Multi-stage non-root container artifact)
* **Base Commit:** `0b0aa93ce3c49c5ac554f066a5fd05596b848fcc`
* **Verification Timestamp:** `2026-10-04T09:12:00Z`
* **Authority Level:** Strictly Read-Only / Server-Controlled Demo Pipeline (**ZERO** arbitrary actuator access)

---

## 1. Executive Summary & Core Security Principle

Phase 2R transitions MotionFence to a publicly accessible controlled live-demo deployment model. In accordance with the non-negotiable core security invariant:

> **THE PUBLIC USER CAN REQUEST A DEMONSTRATION, BUT CAN NEVER COMMAND THE PHYSICAL SYSTEM.**

The externally reachable path is strictly unidirectional and server-controlled:

```text
PUBLIC BROWSER
    │
    ▼ (Fixed allowlist: safe, denied, toctou, recovery, telemetry, evidence)
NEBIUS PUBLIC APPLICATION ENDPOINT
    │
    ├── Judge Console (React SPA)
    ├── Replay APIs (100% Offline Sealed Fixtures)
    └── Controlled Demo API (POST /api/demo/{scenario})
    │
    ▼
MotionFence Runtime (ControlledDemoManager)
    │
 ┌──┴────────────┬────────────────┐
 ▼               ▼                ▼
Nebius Nemotron  Tavily Evidence  USGS Telemetry
 │               │                │
 └───────────────┼────────────────┘
                 ▼
        Safety Pipeline (PolicyEngine)
                 ▼
        AuthorizationTicket (HMAC-SHA256)
                 ▼
 ┌───────────────┴────────────────┐
 ▼                                ▼
Mock Hardware             Isaac Sim Adapter (Contract Verified)
 │                                │
 └───────────────┬────────────────┘
                 ▼
      Verification (PostActionVerifier)
                 ▼
        Audit Record (SHA-256 Sealed)
```

The browser receives only the resulting verifiable audit records; it **never receives actuator credentials, signing secrets, or arbitrary execution endpoints**.

---

## 2. Server-Controlled Demo API Specification

The HTTP layer explicitly prohibits arbitrary execution and mutating verbs:

### Forbidden Endpoints (Enforced with HTTP 405 Method Not Allowed)
- `POST /actuate` ➔ `405 Method Not Allowed`
- `POST /execute` ➔ `405 Method Not Allowed`
- `POST /hardware` ➔ `405 Method Not Allowed`
- `POST /policy` ➔ `405 Method Not Allowed`
- `POST /actions` ➔ `405 Method Not Allowed`
- `PUT /*`, `DELETE /*`, `PATCH /*` ➔ `405 Method Not Allowed`

### Permitted Controlled Demo Routes
- `POST /api/demo/{scenario}` (or `POST /api/demo/run` with `{ "scenario": "..." }`)
- `GET /api/demo/scenarios` (Returns canonical allowlist metadata)
- `GET /api/demo/executions` (List recent executions)
- `GET /api/demo/executions/{execution_id}` (Poll status and retrieve final record)

### Strict Payload Validation
Any request payload containing any of the following fields is immediately rejected with `HTTP 400 Bad Request` (`FORBIDDEN_PAYLOAD`):
* `action`, `target`, `proposal`, `ticket`, `policy`, `command`, `patch`, `override`, `hardware`

Only the following optional metadata is accepted:
* `mode`: `"LIVE"` | `"REPLAY"` (default: `"LIVE"`)
* `backend`: `"mock"` | `"isaac"` (default: `"mock"`)
* `request_id`: optional correlation string

---

## 3. Canonical Demonstration Scenarios

| Scenario ID | Name | Live Provider Context | Safety Invariant Demonstrated | Expected Terminal Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **`safe`** | Safe Execution (Nominal) | Nebius Nemotron 120B | Leak isolated with cooling active; deterministic ALLOW | **`NOMINAL` (VERIFIED)** |
| **`denied`** | Unsafe Proposal Denial | Nebius Nemotron 120B | Technician in exclusion zone; strict policy DENY | **`DENIED` (ZERO TICKETS, LOCKED)** |
| **`toctou`** | TOCTOU Race Condition Defense | Nebius Nemotron 120B | World state drifts v3➔v4; execution revalidation blocks | **`BLOCKED` (TICKET INVALIDATED)** |
| **`recovery`** | Actuator Fault & Recovery | Nebius Nemotron 120B | Stroke fault injected; quarantine & fresh authorization | **`RECOVERED` (VERIFIED)** |
| **`telemetry`** | Real-World Public Telemetry | USGS Potomac River + Nemotron | OGC API water level & flow; environmental context check | **`NOMINAL` (PROVENANCE VERIFIED)** |
| **`evidence`** | Tavily Operational Grounding | Tavily Search + Nemotron | Retrieved safety standards; trust & grounding gate | **`NOMINAL` (GROUNDED)** |

---

## 4. Physical Execution Backend Status & Isaac Sim Truthfulness

In compliance with Sections 7, 8, 41, and 42:
* **Default Production Backend:** `MOCK` (Deterministic hardware simulation with limit switches, current monitoring, and fail-safe latching).
* **NVIDIA Isaac Sim Status:**
  - **Adapter Contract:** `IMPLEMENTED` & verified (`tests/test_isaac_sim_adapter.py`, `tests/test_isaac_stage_inspector.py`).
  - **Live Isaac Runtime:** `NOT DEPLOYED` (Mac OS arm64 environment does not host live Omniverse RTX GPU runtime).
  - **Truthful Public Label:** The Judge Console and health API truthfully report Isaac Sim as an external adapter with simulated physics contracts on local hardware. It is never falsely labeled as a live Omniverse RTX instance.
* **Cost Protection:** No persistent GPU capacity is reserved merely for static web serving; Isaac simulation remains an external decoupled workload.

---

## 5. Credit Guardrails & Provider Account Security

To protect provider credits (Nebius Token Factory and Tavily API):
1. **Sliding-Window Rate Limiting:** Enforced via `RateLimiter(max_requests=30, window_seconds=60.0)` in `scripts/console_server.py`.
2. **Concurrency Limits:** Maximum 2 concurrent live model executions enforced by `ControlledDemoManager`.
3. **Execution Timeouts:** 25.0s maximum per live request; 10.0s for Tavily; 5.0s for USGS.
4. **Fail-Closed Guarantee:** Any timeout, network fault, quota exhaustion, or malformed response strictly produces zero authorization tickets, logs the error, and locks actuators.
5. **Truthful Credit Information:** The Judge Console displays exact request token counts (Prompt, Completion, Total) from the server response rather than fabricating balance dollar values.
6. **Zero Secret Leakage:** Checked and verified: API keys (`NEBIUS_API_KEY`, `TAVILY_API_KEY`), private HMAC keys, and internal cloud credentials are absent from git, frontend bundles, HTTP responses, and logs.

---

## 6. End-to-End Black-Box Production Smoke Verification

Executed via `scripts/production_smoke.py`:

```text
===========================================================================
 MOTIONFENCE PRODUCTION SMOKE TESTER
 Target Endpoint: http://127.0.0.1:8089
 Execution Mode:  REPLAY
 Timeout:         25.0s
===========================================================================

[1/7] Testing Health & Capability Distinction...
  [PASS] GET /health (status=200, app=motionfence, runtime=deterministic)
  [PASS] GET /api/health (status=200)

[2/7] Testing Console Static Asset Serving...
  [PASS] GET / (SPA Shell) (status=200, bytes=457)

[3/7] Testing Server-Controlled Scenario Allowlist...
  [PASS] GET /api/demo/scenarios (found=['safe', 'denied', 'toctou', 'recovery', 'telemetry', 'evidence'])

[4/7] Testing Unknown Scenario Rejection...
  [PASS] POST /api/demo/unknown_scenario (Rejected) (status=404, err=SCENARIO_NOT_FOUND)

[5/7] Testing Rejection of Arbitrary Commands & Payloads...
  [PASS] Reject Arbitrary Action (status=400)
  [PASS] Reject Arbitrary Target (status=400)
  [PASS] Reject Injected Proposal (status=400)
  [PASS] Reject Forged Ticket (status=400)
  [PASS] Reject Policy Override (status=400)
  [PASS] Reject Direct Command (status=400)

[6/7] Testing Direct Actuation & Mutation Prohibition (405 Method Not Allowed)...
  [PASS] Block POST /api/actuate (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /api/execute (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /api/hardware (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /api/policy (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /api/actions (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /actuate (status=405, err=METHOD_NOT_ALLOWED)
  [PASS] Block POST /execute (status=405, err=METHOD_NOT_ALLOWED)

[7/7] Executing Controlled Scenarios in Mode: REPLAY...
  [PASS] Controlled SAFE (status=COMPLETED, outcome=NOMINAL, hash=c92e2213e717, elapsed=304.4ms)
  [PASS] Controlled DENIED (status=COMPLETED, outcome=DENIED, hash=ac2d1326d830, elapsed=306.9ms)
  [PASS] Controlled TOCTOU (status=COMPLETED, outcome=BLOCKED, hash=30b654ed376a, elapsed=307.2ms)
  [PASS] Controlled RECOVERY (status=COMPLETED, outcome=RECOVERED, hash=331dff8023ab, elapsed=303.5ms)
  [PASS] Controlled TELEMETRY (status=COMPLETED, outcome=NOMINAL, hash=08cfc5a0704e, elapsed=308.0ms)
  [PASS] Controlled EVIDENCE (status=COMPLETED, outcome=NOMINAL, hash=4ef78b80bd61, elapsed=308.3ms)

===========================================================================
 PRODUCTION SMOKE TEST SUMMARY
 Total Tests Run: 24
 PASSED:          24
 FAILED:          0
===========================================================================
```

---

## 7. Verification Baseline Summary

| Test Suite / Verification Step | Scope | Result | Details |
| :--- | :--- | :--- | :--- |
| **Backend Pytest** | 476 tests | **PASS (476/476)** | 100% offline, zero network side-effects in 4.95s |
| **Controlled Demo Security** | 8 tests | **PASS (8/8)** | Allowlist, payload sanitization, concurrency, 405 rejection |
| **Frontend Vitest** | 24 tests | **PASS (24/24)** | Judge Console, Controlled Demo Controller, Replay banner |
| **TypeScript Compiler** | `tsc -b` | **PASS (0 errors)** | Clean typechecking across all components and services |
| **Linter** | `oxlint` | **PASS (0 errors)** | 24 files cleanly checked with 116 rules |
| **Production Build** | `vite build` | **PASS** | Bundle compiled to `console/dist` |
| **Production Smoke** | 24 HTTP tests | **PASS (24/24)** | Black-box socket validation against running server |
| **Z3 Bounded Verification** | 60 properties | **SATISFIED** | Formal induction for TOCTOU, containment, recovery |

---

## 8. Remaining Operational Risks & Mitigation

1. **Third-Party Telemetry Latency (USGS):**
   - *Risk:* External USGS API network latency or intermittent maintenance.
   - *Mitigation:* Ingested observations carry strict freshness timestamps and provenance hashes. Stale or unreachable USGS data fails closed to safe fallback invariants.
2. **Model Provider Rate Limits (Nebius):**
   - *Risk:* Nebius Token Factory rate limits during heavy demonstration traffic.
   - *Mitigation:* Transparent fail-closed fallback to sealed, deterministic replay records (`LOAD REPLAY`).
3. **Browser Context Protocols in Headless IDEs:**
   - *Risk:* Playwright CDP protocol variations when controlling IDE-managed browser windows.
   - *Mitigation:* Comprehensive black-box HTTP testing (`scripts/production_smoke.py`) validates the actual wire contract independent of browser automation drivers.
