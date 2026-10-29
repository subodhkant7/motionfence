# MotionFence — Phase 2S Actual Nebius Deployment & Verification Report

> [!NOTE]
> **Historical Milestone Record:** This document records historical testing and platform analysis evidence from Phase 2S. For the current, authoritative implementation status, test results, and benchmark metrics, refer to [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) and [`README.md`](README.md).

* **Deployment Target:** Nebius AI Cloud (Serverless Endpoints / AI Studio)
* **Resource Type:** Hardened Multi-Stage Container (`motionfence:phase-2s`)
* **Evaluated Target Commit:** `aa8e2551bf534e565ad0c384e4f2081d63673f44`
* **Evaluation Timestamp:** `2026-10-10T10:35:00Z`
* **Verification Scope:** Full End-to-End Black-Box Verification (Docker Production Container, Pytest, Vitest, TypeScript, Oxlint, Live Provider Smoke)

---

## 1. Executive Summary & Deployment Assessment

In Phase 2S, MotionFence was prepared, containerized, and subjected to rigorous production verification, black-box security regression testing, and live provider validation.

### Nebius Platform Analysis & Deployment Status

In accordance with Sections 2, 3, and 16:
* **Nebius CLI:** Installed at `/Users/urjasoft/.nebius/bin/nebius` (v0.12.283).
* **Identity & Authentication:** The provided `NEBIUS_API_KEY` authenticates successfully against `api.nebius.cloud:443` as service account `serviceaccount-e00nhevy1krg9bv96z` belonging to AI Studio project `aiproject-e00sk4q9c9nwhhee54` under tenant user `tenantuseraccount-e00andyh2m7vmq06s6` (`aitenant-e00rca10br7sy8rz32` in `federation-e00studio-google`).
* **Inference vs. Cloud Infrastructure Scope:** The API key is strictly an **AI Studio / Token Factory** credential. It grants access to Nebius Token Factory inference endpoints (`https://api.tokenfactory.nebius.com/v1/`).
* **Infrastructure Permissions Blocker:** When invoking Nebius Cloud control-plane infrastructure commands (`nebius ai endpoint`, `nebius registry`, `nebius compute`), the API returns:
  ```text
  rpc error: code = PermissionDenied desc = you do not have permission to access the requested object (Code: 55)
  Service registry error Auth (Code: 15)
  ```
* **Architecture & Billing Blocker:**
  - `nebius ai endpoint create` is a GPU compute service exclusively supporting platforms `gpu-h100-sxm`, `gpu-h200-sxm`, and `gpu-l40s-d` (defaulting to NVIDIA H100 SXM GPUs).
  - Nebius Serverless Endpoints does not currently support CPU-only container hosting.
  - Per Section 2: *"Do not choose GPU infrastructure for the web application unless technically necessary. Do not deploy Kubernetes."*
  - Per Section 3: *"The approximately $25 Token Factory credit and 8,000 Tavily credits must not be assumed to cover application hosting or other Nebius compute. Do not create expensive billable GPU resources. If deployment requires a resource whose cost or billing implications cannot be established, stop before creating it and report the exact blocker."*
* **Outcome:** The application cannot be provisioned on a public Nebius Serverless GPU endpoint without incurring unauthorized billable GPU infrastructure costs and without a service account granted Cloud Control Plane infrastructure roles. Per Section 16, **success is not fabricated**. All local container and live provider verifications have been fully executed.

---

## 2. Production Container Build & Secret Isolation

The multi-stage production Dockerfile (`Dockerfile`) was built and verified (`motionfence:phase-2s`):

* **Runtime User:** Strictly non-root unprivileged user `motionfence` (`uid=10001(motionfence) gid=10001(motionfence)`).
* **Context & Secret Exclusion:** Verified that `.env`, `.venv`, `.git`, `node_modules`, `tests`, `*.pem`, `*.key`, and `*.secret` are absent from `/app`.
* **Frontend SPA Presence:** Verified `/app/console/dist/index.html`, `/app/console/dist/assets/`, and icons are present and correctly mapped.
* **Minimal Footprint:** No heavy Omniverse / Isaac Sim binaries or simulation assets (`*.usd`, `*.usda`) are packaged in the web runtime container.
* **Frontend Secret Cleanliness:** Bundle inspection confirmed 0 API keys, HMAC secrets, or private environment variables are present in compiled JavaScript or HTML.

---

## 3. Production Environment & Startup Validation

The production secret gate was tested in isolated container runs:

| Test Case | Configuration | Result | Error / Behavior |
| :--- | :--- | :--- | :--- |
| **Missing Kernel Secret** | `MOTIONFENCE_ENV=production` | **REJECTED (Exit 1)** | `RuntimeError: PRODUCTION SECURITY VIOLATION: Refusing to start with missing or default test secret.` |
| **Weak Kernel Secret** | `MOTIONFENCE_KERNEL_SECRET=short_secret` | **REJECTED (Exit 1)** | `RuntimeError: PRODUCTION SECURITY VIOLATION: Secret must be at least 32 characters.` |
| **Default Kernel Secret** | `MOTIONFENCE_KERNEL_SECRET=motionfence_runtime_kernel_secret` | **REJECTED (Exit 1)** | `RuntimeError: PRODUCTION SECURITY VIOLATION: Refusing to start with default test secret.` |
| **Wildcard CORS** | `MOTIONFENCE_CORS_ORIGIN=*` | **REJECTED (Exit 1)** | `RuntimeError: PRODUCTION SECURITY VIOLATION: Wildcard CORS origin ('*') is strictly prohibited in production.` |
| **Valid High-Entropy Secret** | `MOTIONFENCE_KERNEL_SECRET=<48-byte URL-safe>` | **ACCEPTED (Exit 0)** | Server starts cleanly on `0.0.0.0:8080`, operational check PASS. |

---

## 4. End-to-End Black-Box Smoke Test Results

Executed via `scripts/production_smoke.py` against the production container on port 8089 in both `REPLAY` and `LIVE` modes:

### Summary

* **Total Tests Run:** 24
* **Passed:** 24
* **Failed:** 0

### Test Breakdown

1. **Health Endpoints:**
   - `GET /health` ➔ `200 OK` (`status: healthy`, `safety_runtime: deterministic`)
   - `GET /api/health` ➔ `200 OK`
2. **Judge Console Shell:**
   - `GET /` ➔ `200 OK` (SPA shell index.html served with nosniff headers)
3. **Controlled Demo Allowlist:**
   - `GET /api/demo/scenarios` ➔ `200 OK` (Canonical 6 scenarios returned)
4. **Unknown Scenario Rejection:**
   - `POST /api/demo/unknown_scenario` ➔ `404 Not Found` (`SCENARIO_NOT_FOUND`)
5. **Rejection of Arbitrary Payloads & Actuator Commands (HTTP 400 Bad Request):**
   - Injected `action` ➔ Rejected
   - Injected `target` ➔ Rejected
   - Injected `proposal` ➔ Rejected
   - Forged `ticket` ➔ Rejected
   - Policy `override` ➔ Rejected
   - Direct `command` ➔ Rejected
6. **Strict Mutation & Actuation Prohibition (HTTP 405 Method Not Allowed):**
   - `POST /api/actuate` ➔ `405 Method Not Allowed`
   - `POST /api/execute` ➔ `405 Method Not Allowed`
   - `POST /api/hardware` ➔ `405 Method Not Allowed`
   - `POST /api/policy` ➔ `405 Method Not Allowed`
   - `POST /api/actions` ➔ `405 Method Not Allowed`
   - `POST /actuate` ➔ `405 Method Not Allowed`
   - `POST /execute` ➔ `405 Method Not Allowed`
7. **Canonical Controlled Scenarios:**
   - `safe` ➔ `COMPLETED`, outcome: `NOMINAL`, deterministic authorization verification PASS
   - `denied` ➔ `COMPLETED`, outcome: `DENIED`, zero tickets issued, actuator locked PASS
   - `toctou` ➔ `COMPLETED`, outcome: `BLOCKED`, ticket invalidated on drift PASS
   - `recovery` ➔ `COMPLETED`, outcome: `RECOVERED`, stroke fault quarantined PASS
   - `telemetry` ➔ `COMPLETED`, outcome: `NOMINAL`, real-world USGS telemetry context PASS
   - `evidence` ➔ `COMPLETED`, outcome: `NOMINAL`, Tavily operational grounding PASS

---

## 5. Live Execution vs. Offline Replay

* **LIVE Execution Mode:**
  - Real calls dispatched to Nebius Token Factory (`nvidia/nemotron-3-super-120b-a12b`), Tavily Search API, and USGS Water Services.
  - Measured latencies:
    - `safe`: 4,933.8 ms (Nemotron proposal + deterministic enclave verification)
    - `denied`: 2,777.8 ms (Nemotron proposal + exclusion zone denial)
    - `toctou`: 3,095.7 ms (Nemotron proposal + version race invalidation)
    - `recovery`: 2,168.6 ms (Nemotron proposal + recovery sequence)
    - `telemetry`: 10,221.7 ms (USGS live telemetry + Nemotron reasoning)
    - `evidence`: 6,791.1 ms (Tavily search grounding + Nemotron reasoning)
* **REPLAY Execution Mode:**
  - 100% offline sealed fixtures; average execution duration ~310 ms.
  - Zero external network requests made to Nebius, Tavily, USGS, or Isaac Sim.
  - Transparently and prominently displays `[REPLAY RECORD]` banner in the Judge Console.
  - Fails safe: never mislabels replay execution as live.

---

## 6. Rate Limiting & Concurrency Topology

* **Deployment Model:** Single-process container instance.
* **Scope:** Rate limiting is **process-local** using an in-memory sliding window:
  - Per-client limit: 10 demo requests per 60 seconds per IP.
  - Global ceiling: 30 demo requests per 60 seconds.
  - Maximum concurrent live executions: 2 (enforced by `ControlledDemoManager`).
  - Request payload ceiling: 64 KB.
* **Proxy Trust Rules:** Incoming `X-Forwarded-For` headers are only trusted if the peer socket IP matches `MOTIONFENCE_TRUSTED_PROXIES`. Otherwise, the direct socket address is enforced.

---

## 7. Isaac Sim Status

* **Isaac Adapter:** `IMPLEMENTED` & contract-verified (`motionfence/simulation/isaac_adapter.py`, `tests/test_isaac_sim_adapter.py`).
* **Isaac Runtime:** `NOT DEPLOYED` (Omniverse RTX GPU physics runtime is not active in the lightweight web container).
* **Public Labeling:** Judge Console and API truthfully report `isaac_runtime: unavailable` and use `mock` hardware as the active backend.

---

## 8. Test Suites & Verification Baseline

| Test Suite | Scope | Result | Execution Time |
| :--- | :--- | :--- | :--- |
| **Backend Pytest** | 547 tests | **547 / 547 PASSED** | 8.39s |
| **Frontend Vitest** | 24 tests | **24 / 24 PASSED** | 2.81s |
| **TypeScript Compiler** | `npx tsc --noEmit` & `npx tsc -b` | **0 Errors** | Clean |
| **Linter (`oxlint`)** | 24 files, 116 rules | **0 Errors** (59 warnings) | 83ms |
| **Production Frontend Build** | `vite build` | **BUILT** | 392ms |
| **Container Smoke (REPLAY)** | 24 HTTP checks | **24 / 24 PASSED** | 2.1s |
| **Container Smoke (LIVE)** | 24 HTTP checks | **24 / 24 PASSED** | 30.2s |

---

## 9. Remaining Operational Inputs & Blockers

1. **Cloud Control Plane Access:** To provision an internet-facing container endpoint on Nebius, a Nebius Cloud service account with infrastructure provisioning roles (`ai.endpoints.editor` or `compute.admin`) is required.
2. **CPU-Oriented Container Runtime:** If deploying to Nebius Serverless Endpoints, Nebius currently allocates GPU infrastructure (`gpu-h100-sxm`), which requires dedicated cloud billing allocation. Alternatively, a lightweight VM or CPU container host should be designated.
3. **Public Deployed URL:** Once a container host or proxy is assigned, `MOTIONFENCE_CORS_ORIGIN` should be configured to match the exact public HTTPS domain, or left unset for same-origin serving.
