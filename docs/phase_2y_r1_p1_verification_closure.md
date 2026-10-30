# PR #2 — final P1 verification-contract closure

Parent commit: `e717001e8c80d920e98b909ca5ae0c67ca3e5aa5`. Branch: `codex/phase-2y-r1-evidence-closure`. The correction commit SHA is recorded in the final P1 section of [PR #2](https://github.com/subodhkant7/motionfence/pull/2).

This correction addresses the two verification defects only. It changes three production files, three test files, and this report. The existing layout, provider configuration, infrastructure, video, and previous validation artifacts are unchanged. The five pre-existing local whitespace edits remain outside the commit.

## Defect 1: raw VERIFIED could contradict the validated stage

The previous card expression fell back to the recorded status whenever the weak `verificationPassed()` predicate returned false. Thus a record with `status=VERIFIED` and contradictory/missing evidence could show a VERIFIED card beside a failed or unverified stage.

The card now derives its status from the validated stage result and evidence presence. The stage subtitle uses the same status; the overall outcome and Director continue to consume the validated timeline. No raw VERIFIED fallback remains.

| Evidence/result at the verification stage | Card/subtitle | Stage badge | Overall/Director |
| --- | --- | --- | --- |
| Complete correlated action, authorization, chronology and physical verification | VERIFIED | PASSED | NOMINAL / VERIFIED |
| Explicit failure or conflicting expected/observed readback | VERIFICATION_FAILED | FAILED | VERIFICATION_FAILED |
| Partial, stale, wrong-target, unresolved or insufficient proof | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Verification absent after execution | NOT_RECORDED | UNVERIFIED | UNVERIFIED |
| Verification not reached after recorded rejection | NOT_REACHED | NOT_APPLICABLE | Recorded DENIED/BLOCKED |

A recovery snapshot's raw VERIFIED actuator label also cannot substitute for final verification. When that label is unsupported, the frame uses the recorded final world state without claiming actuator verification. This preserves the actual valve position.

## Defect 2: unrelated postconditions could prove a valve operation

TypeScript `verificationPassed()` and Python `_recorded_verification_passed()` now require action-specific evidence, correlated to the actual action ID and target:

- CLOSE_VALVE requires explicit expected and observed `valves.<actual target> = CLOSED`, also resolved as CLOSED in the final world.
- OPEN_VALVE requires the corresponding explicit OPEN postcondition, observations, and final-world state.
- Both require explicit expected and observed `cooling = ACTIVE`, consistent with the final world.
- Closing the leak target identified in either pre-state or post-state also requires explicit expected/observed `leak.active = false`, consistent with the final world.
- Every additional declared expected postcondition must be observed, resolvable in the final world, and equal to its expected value. Unknown paths are rejected even when expected and observed values are both null.

Recovery uses the fresh ticket's action type, action ID and target, matched to the recorded retry action and target. It no longer assumes a hardcoded valve-B closure. Existing authorization and chronology checks remain required. The normal safe-execution fixtures continue to pass.

The runtime's `PostActionVerifier` applies the same path rules when constructing verification records. Custom conditions supplement the required valve/cooling/leak invariants; they cannot override them.

## Custom-path compatibility contract

Paths are non-empty, dot-separated, case-sensitive keys into the recorded world. TypeScript traverses own properties only; Python traverses the JSON serialization of WorldState. For example, `observations.pressure_main.reading.pressure_psi` and `external_observations.custom.nullable` are valid when all their keys exist.

Missing keys, missing parents, traversal through scalar values, inherited properties/methods, array indexing, and implicit aliases do not resolve. A method name such as `model_dump` is not a world-state field. An explicitly recorded mapping key such as `external_observations.custom.constructor` remains ordinary data and is supported.

A present null is distinct from a missing path. Null can be an additional custom postcondition only when the actual world contains that path with null; it cannot replace required valve/cooling/leak proof. JSON scalars, arrays and objects are supported as leaf values and compared structurally. Numbers must be finite, and booleans are distinct from numbers. A changed nested value invalidates the proof.

## Regression evidence

Before correction, the initial new frontend suite reproduced **16 failures out of 19 cases**, and the initial new backend suite reproduced **13 failures out of 16 cases**. Additional cases were then added for custom-path compatibility, invariant overrides, missing action IDs and unsupported recovery snapshot labels.

The final frontend suite adds **20 cases**. It covers all nine requested adversarial categories, including actual rendered verification cards, stage badges, captions, overall outcomes and Director statuses. The backend adds **24 cases** covering record evaluation and verification-record construction. Positive checks preserve valid CLOSE_VALVE, OPEN_VALVE, recovery, and custom scalar/structured/null proofs.

| Gate | Result |
| --- | --- |
| Targeted frontend: new contract suite plus stage and Director regressions | **79 passed**, 3 files |
| Targeted backend: evidence contract, verifier, controlled-demo security | **57 passed** |
| Full frontend | **137 passed**, 9 files |
| Full backend | **644 passed** |
| Production TypeScript/Vite build | Passed; existing large-chunk warning remains |
| Lint | Exit 0, zero errors; **83 existing warnings**, unchanged from PR starting commit |
| Expanded Safety Lab | **20/20 passed**; unsafe actuation and false-verification rates remain zero in this benchmark |
| Bounded assurance | **62/62 satisfied**, zero violated/unknown |

Targeted tests ran before the full gates. This closure uses rendered React regression tests for status alignment; it does not regenerate the video or previous browser captures. The complete test commands are:

```sh
npm run test --prefix console -- src/test/verification_contract.test.tsx src/test/decision_twin_stage.test.tsx src/test/director.test.tsx --reporter=dot
.venv/bin/python -m pytest tests/test_presentation_evidence_contract.py tests/test_verification.py tests/test_controlled_demo_security.py -q
npm run test --prefix console -- --reporter=dot
.venv/bin/python -m pytest tests/ -q
npm run build --prefix console
npm run lint --prefix console
.venv/bin/python scripts/run_safety_benchmark.py --all --suite expanded --export /tmp/motionfence-p1-benchmark.json
.venv/bin/python scripts/run_assurance.py --output /tmp/motionfence-p1-assurance.json
```

## Changed files

- `console/src/services/frameDerivation.ts` — validated display status, action-specific postconditions, final-world path resolution and recovery context.
- `motionfence/runtime/controlled_demo.py` — corresponding record-evaluation requirements for primary and recovery verification.
- `motionfence/runtime/verification.py` — presence-aware custom path resolution and invariant-preserving verification construction.
- `console/src/test/verification_contract.test.tsx` — new adversarial and rendered alignment regressions.
- `tests/test_presentation_evidence_contract.py` — action-specific primary/recovery record mutations and valid custom/OPEN_VALVE cases.
- `tests/test_verification.py` — custom-path and invariant-override construction tests.
- `docs/phase_2y_r1_p1_verification_closure.md` — this focused correction report.

Both P1 defects are closed by the passing regressions. Historical evidence gaps still remain explicitly unverified; they were not reconstructed. Existing lint/build warnings and the bounded nature of assurance remain disclosed. PR #2 remains open for review. No merge, force-push, Render deployment, video regeneration, Google Cloud change or additional infrastructure was performed.
