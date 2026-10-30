# Phase 2Z production release

MERGE: VERIFIED. PRODUCTION DEPLOYMENT: VERIFIED. PUBLIC SCENARIO SAFETY: VERIFIED. V3 VIDEO HANDOFF: READY.

PR #2 was squash-merged using reviewed-head concurrency guard `f0c31bcf08ba2fc18b56023eed38b49ae6616704`. The merge and main revision is `53cdf88a5fc53bcc2236a67290a3d3c4ece47cd3`, parent `d2c6f3cb95f3b74e796ca5f5776be3e03d43f83c`. The reviewed and merged trees both equal `1d4350f7f5854aeea391c6784b7108e154efb58b`. No unexpected commit entered main. Main had no protection rules, required checks, submitted reviews or open review threads when checked; no bypass or auto-merge was used.

## Artifact and deployment controls

Release worktree `/tmp/motionfence-phase2z-release` was detached at the actual merge, with an empty tracked/untracked status at build. Dependencies were reused locally for frontend tests; the Docker build ran its own npm installation. The original working tree's five whitespace edits were neither staged nor overwritten; task-start SHA-256 hashes are retained for final comparison.

The existing Dockerfile was built at the reviewed head and again at the actual merge. Merged image: `sha256:d10114594b68520454113fbffb478356844e1b1cc7c7517e51766734e9e0ebbc`. Production startup rejected missing, repository-default and short secrets in the reviewed image; the merged tree is identical and its image started in production mode with a generated ephemeral test secret. No production credential was used in the local image. An exact-value scan of the application image found no configured local provider/kernel credentials or .env files. Dockerfile exclusions keep .env, keys and local environments outside the context. No credentials were supplied as build arguments. This is a bounded scan, not an independent image supply-chain audit.

Render service `srv-dbhsujajnfac73c8jmp0` remains **Free**, **Singapore**, Docker runtime, one instance. Initial auto-deploy was `commit` on main. The hold was explicitly announced, set to `off`, and independently read back before merge. **Auto-deploy remains off** after release; no implicit re-enabling was performed. Existing credentials and secret storage were unchanged. The service does not explicitly set MOTIONFENCE_ALLOW_PUBLIC_LIVE; the merged source defaults it to false. The local production runtime reported false, public health exposes REPLAY/OFFLINE_TEST only, and a public request for LIVE actually completed as REPLAY. No fresh paid provider call was made.

Deployment `dep-dbi88nrbc2fs73acq8f0` was explicitly triggered with commitId `53cdf88a5fc53bcc2236a67290a3d3c4ece47cd3`; Render reported live at `2026-10-30T11:50:45Z`. Source/build is performed by Render from that pinned Git revision; the local image is not uploaded. Prior live deploy `dep-dbhug71srm7s73e0ieog` at baseline d2c6f3c was recorded as the rollback candidate. No rollback was required. If a release failure later requires rollback, confirm retained artifact availability and invoke Render's existing rollback mechanism; keep auto-deploy off to avoid reintroducing a bad revision. No migrations were introduced by this release.

## Newly executed verification

| Gate | Result |
| --- | --- |
| Targeted frontend/backend | 96 / 68 passed |
| Full frontend | 154 passed, 10 files |
| Full backend after frontend assets built | 655 passed |
| Expanded Safety Lab | 20/20 |
| Bounded assurance | 62 satisfied, 0 violated/unknown |
| Existing Dockerfile, reviewed and merged revisions | Built successfully |
| Production startup and secret rejection | Passed as described above |
| Local merged-image browser | 18 source/mesh/status checks passed |
| Real public browser at 1920×1080 | 18 source/mesh/status checks passed; zero page errors |

The first clean-checkout backend run had three traversal assertions fail and one skip because console/dist was absent. Building the frontend assets and rerunning produced 655 passed. No test expectation was weakened. The existing production_smoke.py returned 23/24 because it still expects historical recovery to be RECOVERED. Its actual response was UNVERIFIED, correctly required by the reviewed evidence contract. An independent six-scenario outcome check and both full browser runs confirmed that contract. The stale smoke-script expectation remains a maintenance limitation; it was not used to claim 24/24 success.

Build warnings include the existing large chunk and Node engine warnings for development tooling under the Dockerfile's Node 20 builder; the build completed. Three.js/SwiftShader warnings remain nonfatal. No native Isaac Sim or physical hardware validation is claimed.

## Public behavior

Actual checks targeted https://motionfence.onrender.com, not a local substitute. `/health`, `/demo`, `/console`, `/safety-lab`, and `/architecture` returned successful responses. Separate real-browser checks also confirmed that console, Safety Lab and architecture modules render substantive content with zero page errors ([module evidence](release_evidence/phase2z/public-modules.json)). Scenario safety was checked through genuine browser execution, real WebGL initialization, source data attributes, applied valve-wheel rotations, card/Director labels and frame bounds, rather than HTTP status alone.

| Scene | Actual behavior |
| --- | --- |
| Safe | OPEN at observe; CLOSED at execution while still UNVERIFIED; VERIFIED only at verification |
| Denied | NOT_ISSUED authorization, DENIED, OPEN through execution |
| TOCTOU | Recorded world drift; BLOCKED at revalidation/execution; OPEN |
| Mechanical | OPEN failed stroke, VERIFICATION_FAILED, containment record; historical final CLOSED position remains UNVERIFIED |
| Telemetry | Source-labelled recorded context; OPEN observation, actual recorded CLOSE execution, correlated VERIFIED result |
| Evidence | Recorded provenance; OPEN pre-state, actual recorded CLOSE execution, correlated VERIFIED result |

Telemetry/evidence retrieval is not itself physical proof. Where a visualization snapshot is unsuitable, the interface explicitly uses canonical pre_state, post_state or execution_result.observed_state. Independent browser assertions compared those categorical world fields (including hardware world_version) with the actual execution GET response. Catalog snapshot identity alone is insufficient. Initial harness assumptions requiring every source to be a raw catalog snapshot were corrected without changing source code or expected safety outcomes.

[Public browser results](release_evidence/phase2z/public-browser.json), [nominal screenshot](release_evidence/phase2z/safe.png), [recovery disclosure screenshot](release_evidence/phase2z/recovery.png), and [public spending guard result](release_evidence/phase2z/spending-guard.json) are retained. The browser-check script uses the already cached Playwright installation/executable on this machine; adapt those two tool paths if reproducing elsewhere. Both decision rail and plant fit the 1920×1080 viewport; nominal and recovery captures were visually inspected. Geometry remains schematic and cameras intentionally focus different regions.

## Assurance count reconciliation and documentation

The source registry has **60 registered property IDs** (`AssurancePropertyRegistry.list_all()`). scripts/run_assurance.py additionally appends cooling-preservation and dynamic-human-incursion temporal findings. Thus a run has **62 findings/checks across 60 distinct property IDs**, not 62 independent registered properties. The two temporal findings reuse existing IDs. README counts now describe this distinction and the newly executed 655 backend / 154 frontend tests. Bounded-model satisfaction is not a real-world safety proof or SIL certification.

These documentation-only updates follow the deployed merge on main under the verified auto-deploy hold. They do not alter the deployed runtime revision. The final documentation/main SHA is recorded in the completion report; production remains pinned to 53cdf88a5fc53bcc2236a67290a3d3c4ece47cd3. No implementation phase was begun.

## Devpost / operator release identifiers

- Source: https://github.com/subodhkant7/motionfence/commit/53cdf88a5fc53bcc2236a67290a3d3c4ece47cd3
- PR: https://github.com/subodhkant7/motionfence/pull/2 (merged).
- Application: https://motionfence.onrender.com
- Verified demo: https://motionfence.onrender.com/demo
- Render deploy: dep-dbi88nrbc2fs73acq8f0, Free Singapore existing service.
- Video handoff: [Antigravity V3](phase_2z_antigravity_v3.md).

Remaining risks: Free-tier cold starts, existing lint/build/renderer warnings, stale production-smoke recovery expectation, historical missing independent recovery verification and schematic physical geometry. Public provider spending remains guarded. Native Isaac runtime is unavailable; adapters/contracts are not evidence of native Isaac execution. No Google Cloud, GPU infrastructure, credential changes, Devpost/YouTube upload or video generation occurred.
