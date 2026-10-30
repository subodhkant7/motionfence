# Phase 2Y-R2 — safety-invariant closure and release gate

**Verdict: READY TO MERGE**, subject to human review and the exact-head merge procedure below. Deployment and video recapture remain held.

Starting commit: `20aa90dd024a8f936057e99531998de5813eba26`. Expected and fetched `origin/main`: `d2c6f3cb95f3b74e796ca5f5776be3e03d43f83c`. Branch: `codex/phase-2y-r1-evidence-closure`. The final correction SHA is recorded in the R2 section of [PR #2](https://github.com/subodhkant7/motionfence/pull/2) and the release handoff accompanying this report. This document is part of that correction commit.

## Failure definition and root cause

Expected: a recorded policy DENY plus ticket issuance for that decision is an ERROR, even when hardware stays LOCKED and the plant is unchanged. Actual at the starting commit: both evaluators returned DENIED because the denial branch checked only actuation or plant mutation. The TypeScript authorization stage could be unverified while the overall result still claimed ordinary denial.

The reproducer holds the denied scenario identifier, policy, execution and snapshots constant and changes only authorization evidence. Before the fix, **8 of 17 new frontend cases failed**, and **2 of 11 new backend cases failed**. The valid-denial and unauthorized-actuation controls already passed. These are assertion failures reproducing the defect, not updated expectations accepting the old behavior. Confidence in this isolated reporting defect and correction is high.

## Corrected behavior and source changes

| Record | Python outcome | Presentation outcome | Authorization display / physical state |
| --- | --- | --- | --- |
| DENY, null ticket, LOCKED or not invoked, zero mutation | DENIED | DENIED | NOT_ISSUED where explicitly recorded; actual OPEN snapshot |
| DENY, issued current ticket, zero mutation | ERROR | ERROR from policy stage onward | FAILED authorization stage, ERROR card, explicit issue; actual OPEN snapshot |
| DENY, correlated enclave issuance event without ticket object | ERROR | ERROR | Same failure; no ticket/signature reconstructed |
| DENY, current canonical issuance ID without ticket object | Not a field in LiveDemoRecord | ERROR | ID disclosed with ERROR; no signature reconstructed |
| DENY, unauthorized ACTUATED hardware or valve mutation | ERROR | ERROR | Failed safety result; physical state still comes from recorded evidence |
| DENY, rejected hardware input ID or unrelated historical grant | DENIED | DENIED | Neither proves current issuance |
| ALLOW, valid correlated authorization and physical verification | NOMINAL | NOMINAL / Director VERIFIED | Existing P1 contract required |
| TOCTOU revalidation block, zero actuation | BLOCKED | BLOCKED | Actual locked/open snapshot |

Python changes are limited to `evaluate_stage_outcome()` in [controlled_demo.py](../motionfence/runtime/controlled_demo.py). It detects the current run's ticket and correlated `ENCLAVE_AUTHORIZATION_GRANTED` events before returning an ordinary denial. It does not mint or validate a new ticket, sign anything, execute hardware, or change SafetyEnclave.

The decisive Python diff is:

```diff
+        ticket_issued = bool(rec.ticket and rec.ticket.ticket_id)
+        # Also recognize an ENCLAVE_AUTHORIZATION_GRANTED event with a
+        # non-empty ticket_id and the current proposal_id (see source loop).
-        if actuated:
+        if ticket_issued or actuated:
             return StageOutcome.ERROR
```

TypeScript changes are limited to [frameDerivation.ts](../console/src/services/frameDerivation.ts). It inspects current envelope ticket slots (`ticket`, `authorization_ticket`, `initial_ticket`), correlated grant events, and the current canonical decision's issuance ID. A DENY in the canonical decision remains authoritative even when an envelope policy alias claims ALLOW. Contradiction takes precedence over ordinary DENIED and generic policy-conflict UNVERIFIED outcomes. Policy/authorization stages, authorization card, narration, issue disclosure and overall/Director outcome consume this result.

The decisive TypeScript diff is:

```diff
+    if (
+      index >= 3 &&
+      (deniedIssuance || (deniedPolicyRecorded && unauthorized))
+    )
+      return 'ERROR'
     if (index >= 3 && policyConflict) return 'UNVERIFIED'
     if (index >= 7 && unauthorized) return 'ERROR'
     if (index >= 3 && policy === 'DENY') return 'DENIED'
```

The authorization card now displays ERROR and `INVALID (POLICY DENY)` for issuance despite denial. Recorded hardware LOCKED remains a physical fact; it does not erase the issuance violation. Future lifecycle stages remain PENDING until playback reaches them. No simulated movement is introduced. No Stage, Director, WebGL renderer, ticket-authority or SafetyEnclave source changes were necessary.

## Issuance and identifier semantics

`LiveDemoRecord.ticket` represents the ticket issued for that run. A non-empty ticket ID in this current-run object establishes recorded issuance, even if its signature, chronology or target correlation would subsequently fail validation. A null ticket is not issuance. A hardware request's `ticket_id` alone is caller input and may have been rejected; it cannot establish issuance.

The enclave's `ENCLAVE_AUTHORIZATION_GRANTED` event is emitted after minting and carries `proposal_id` and `ticket_id`. The evaluators require a non-empty ticket ID and the denied action's exact non-empty proposal ID. A grant for a historical proposal, or an AUTHORIZATION_REQUESTED event, is not a grant for the current action.

The frontend canonical `decision_record.authorization_ticket_id` has the audit-model meaning “Minted HMAC ticket ID if authorized, else None.” Both `runtime/core.py` and `live_record_to_scenario_data()` populate it from the minted ticket. The frontend correlates the owning `action_proposal.id` with the currently displayed proposal before treating this field as issuance. An unrelated historical identifier cannot create current authority. Python's LiveDemoRecord has no separate canonical decision-ID field; its equivalent independent evidence is the correlated issuance event. No schema or backend protocol was added.

The limited cross-module review checked these source semantics, null handling, rejection versus issuance, action correlation, ERROR precedence, nominal and TOCTOU paths, and the prior P1 physical-verification predicates. TypeScript's canonical-envelope support accounts for its richer serialized input; it does not fabricate a missing Python ticket.

## Regression and quality evidence

New frontend coverage adds **17 cases**: full/minimal ticket records, aliases masked by null, correlated issuance events, canonical issuance IDs, null/not-invoked/LOCKED controls, rejected IDs, historical grants/IDs, request-only events, unauthorized actuation/mutation, nominal/TOCTOU controls, missing authorization, conflicting policy fields, actual rendered authorization/Director alignment and unchanged plant snapshot identity.

New backend coverage adds **11 cases** for the shared record semantics, including valid denial, issuance without mutation, independent correlated issuance, historical/request-only events, rejected hardware IDs, unauthorized actuation/mutation and nominal/TOCTOU controls. The P1 suites for action-specific valve evidence, recovery and custom postcondition resolution remain passing.

| Gate | Final result |
| --- | --- |
| Targeted frontend: R2, P1, stage and Director | **96 passed**, 4 files |
| Targeted backend: evidence contract, security and verifier | **68 passed** |
| Full frontend | **154 passed**, 10 files |
| Full backend | **655 passed** |
| Production build | Passed; existing large-chunk warning |
| Lint | Passed, zero errors; **83 existing warnings** |
| Expanded Safety Lab | **20/20 passed** |
| Bounded assurance | **62/62 satisfied**, zero violated/unknown |
| Chromium, built production bundle, 1920×1080 | **11 status/source/mesh checks**, zero page errors |

Commands, with targeted checks run before full gates:

```sh
npm --prefix console test -- src/test/denial_authorization_contract.test.tsx src/test/verification_contract.test.tsx src/test/decision_twin_stage.test.tsx src/test/director.test.tsx --reporter=dot
.venv/bin/python -m pytest tests/test_presentation_evidence_contract.py tests/test_controlled_demo_security.py tests/test_verification.py -q
npm --prefix console test -- --run
.venv/bin/python -m pytest tests/ -q
npm --prefix console run build
npm --prefix console run lint
.venv/bin/python scripts/run_safety_benchmark.py --all --suite expanded --export /tmp/motionfence-r2-benchmark.json
.venv/bin/python scripts/run_assurance.py --output /tmp/motionfence-r2-assurance.json
```

## Actual browser verification

A loopback server served the new built production bundle with `MOTIONFENCE_ALLOW_PUBLIC_LIVE=false`. Cached Chromium ran headlessly with SwiftShader WebGL, a 1920×1080 viewport and reduced-motion preference. The real renderer received snapshots, and its applied valve-wheel rotation was checked against those snapshots: OPEN = 0 radians; the valid nominal CLOSED state = π/2. Source equality, Director status, stage/card status, issue disclosure, REPLAY provenance and viewport bounds were asserted. Both screenshots below were also opened and visually inspected.

The contradictory case is an explicitly injected adversarial record: Playwright modifies only the browser's GET execution response by adding one current-action ticket field to the denied record. Original policy, snapshots, server summary and fixture hash remain unchanged. It is not a production/server record or fresh cryptographically sealed evidence. The presentation correctly overrides the unchanged server DENIED summary. No fixture or server data is persisted. Existing Three.js deprecation/shadow warnings and SwiftShader readback warnings occurred; there were no page errors.

- [Authorization failure screenshot](../output/playwright/phase2y-r2/contradictory_authorization_1920x1080.png): ERROR Director/outcome/card, FAILED policy and authorization, explicit contradiction, OPEN valve and occupied zone.
- [Execution screenshot](../output/playwright/phase2y-r2/contradictory_execution_1920x1080.png): ERROR outcome persists while recorded hardware remains LOCKED and the valve remains OPEN.
- [Machine-readable browser evidence](../output/playwright/phase2y-r2/browser-evidence.json): all 11 valid and adversarial checks, source snapshots and observed mesh angles.
- [Browser check script](../scripts/visual_qa_phase2y_r2.js): use Playwright CLI `run-code --filename` from the output directory, with the local replay page open at 1920×1080.

## Changed files and local preservation

The R2 correction includes two production files, two test files, one bounded browser-check script, this report, two screenshots and one browser evidence JSON:

1. `motionfence/runtime/controlled_demo.py`
2. `console/src/services/frameDerivation.ts`
3. `tests/test_presentation_evidence_contract.py`
4. `console/src/test/denial_authorization_contract.test.tsx`
5. `scripts/visual_qa_phase2y_r2.js`
6. `docs/phase_2y_r2_release_gate.md`
7. `output/playwright/phase2y-r2/browser-evidence.json`
8. `output/playwright/phase2y-r2/contradictory_authorization_1920x1080.png`
9. `output/playwright/phase2y-r2/contradictory_execution_1920x1080.png`

SHA-256 content checks against the task-start copies confirm that all five prior local whitespace edits are unchanged and excluded from staging: `WebGLIndustrialPlant.css`, `WebGLIndustrialPlant.tsx`, `DecisionTwinStage.css`, `console/src/types/presentation.ts`, and `scripts/visual_qa_phase2y.py`. Previous P1 code is retained; no existing test expectation was weakened. No reset, rebase, force-push or additional PR is used.

## Merge and release handoff

PR #2 targets main and was open, unmerged and mergeable against the expected main at baseline. Its final head, open/unmerged status, mergeability and base are rechecked after push and recorded in the PR's R2 section. There are no known code/test blockers for the scoped merge. Human review is still required. Existing warnings, historical unverified recovery evidence, schematic geometry and bounded-assurance limits remain disclosed.

For the reviewer/release owner:

1. Open PR #2, confirm the final R2 SHA from its body equals the current head, review the complete PR diff and the focused R2 files, and check required reviews/status checks. If head or base changed after this report, rerun affected gates; do not approve a different commit using these results.
2. Confirm the existing Render service's deployment trigger before merging. Its current auto-deploy setting was not inspected or changed here. Coordinate the deployment hold before merge if updating main would automatically deploy.
3. Once review and required checks pass, use GitHub's **Squash and merge** on PR #2. With an authenticated CLI, the equivalent exact-head guard is `gh pr merge 2 --repo subodhkant7/motionfence --squash --match-head-commit <FINAL_R2_SHA>`. Do not add `--admin`, `--auto` or bypass checks. Stop on a mismatch or failed check.
4. Record the resulting main merge SHA. Do not stage the preserved local edits or reset this working tree to update it; use a separate clean checkout for subsequent release validation.

**Render readiness:** the correction is ready at the source/build/local-replay level. Deployment is held for separate approval. This task does not rebuild the Docker image, inspect Render's live settings, claim current production smoke success or deploy. Before release, build/smoke the existing Dockerfile from the reviewed merge SHA, retain `MOTIONFENCE_ALLOW_PUBLIC_LIVE=false`, and deploy that reviewed revision through the existing Render service only when authorized. Verify health, REPLAY provenance, nominal, denial, TOCTOU and historical recovery labels after deployment. No new service, GPU or credential change is needed for this reporting correction.

**Final V3 video recapture:** wait until PR review and the approved release revision are settled. Recapture from that revision at 1920×1080 with visible REPLAY/mock-simulation provenance. Show nominal verification only after the complete contract passes; valid hazard denial must show no ticket and no valve movement; TOCTOU must show revalidation BLOCKED and no actuation. Historical recovery stays UNVERIFIED without a later independent correlated verification. If illustrating the new contradiction, label it as an injected adversarial record, show ERROR and the stationary recorded plant, and do not describe it as successful denial. Retain the prior source/hash/measurement limitations and bounded-assurance disclosure. Update narration/captions to the actual rendered statuses before exporting V3. No video was regenerated here.

No merge, Render deployment, Google Cloud change, paid infrastructure, credential change or public-live setting change was performed. Stop after updating the existing PR and delivering this handoff.
