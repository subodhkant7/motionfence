# Phase 2Y-R1 corrective evidence report

Corrective branch: `codex/phase-2y-r1-evidence-closure`. Baseline/current main verified as `d2c6f3cb95f3b74e796ca5f5776be3e03d43f83c`. Production deployment is held for review. Public live inference remains disabled; no production deploy, merge, cloud change, visibility change, paid service, or model request was performed.

## Findings and correction

The Phase 2Y derivation used scenario-name tests to invent policy results, proposal confidence/hash, authorization IDs/hashes, nine successful barriers, voltage, plant versions/sensor readings, verification, and recovery. The renderer independently supplied measurements and could rebuild its scene or retain transforms across playback changes. The Director also accepted terminal summaries before playback reached their supporting evidence.

Both split panels now receive a single **source-derived** frame. Scenario IDs supply identity/title only. An explicit null authoritative field cannot resurrect an older nested result. Missing measurements, hashes, reasons, and results remain `NOT_RECORDED`, `UNKNOWN`, `UNVERIFIED`, or `NOT_APPLICABLE`. Contradictory policy, ticket/action correlation, chronology, verification/post-state, and categorical physical snapshots suppress success. Raw recorded physical position remains distinct from verified outcome.

The detailed audit path and its controlled-demo pipeline contained a second copy of the same template defect. Their displayed stages now use the shared contract. Actual telemetry remains available; requesting Isaac cannot relabel an historical record's missing backend or manufacture prim paths, joint angles, or worker proximity. The existing industrial WebGL plant and split layout are preserved. Source labels, recovery disclosures, header wrapping, and scrolling were adjusted narrowly for readability.

## Source-to-frame contract

| Display | Recorded authority | Missing/contradictory evidence |
| --- | --- | --- |
| Observation/physical state | `pre_state`, validated-shape `digital_twin_snapshots`, `hardware_execution.observed_state`, `post_state` | Unknown fields; categorical conflicts reject the conflicting snapshot and suppress success |
| Evidence | Decision evidence IDs/items or actual telemetry provenance | Evidence not recorded; IDs are references, not an assertion that every claim was validated |
| Proposal | `decision_record.action_proposal` / canonical `proposal`, provider metadata | No invented action, rationale, confidence, model, or proposal hash |
| Policy | Recorded policy decision, actual reason rows | `UNKNOWN`/`UNVERIFIED`; ALLOW with failed rule or conflicting duplicate verdict cannot pass |
| Authorization | Actual ticket ID/signature/hash, issue/expiry times, authorization event | Signature presence is labelled `SIGNATURE_RECORDED`; execution validity remains unverified at issuance |
| Drift/revalidation | Recorded drift versions and validation/rejection events/results | No inferred drift from a route; absent actual hash remains unknown |
| Execution | Actual hardware result, matching ticket/action/target, recorded validation | No invented stroke, voltage, ticket consumption or successful execution |
| Verification | Actual action/target correlation, postconditions, matching observations, chronology and final world | Missing, failed, stale or contradictory verification cannot pass |
| Recovery | Failure/containment/suspect/quarantine/proposal events, reported result, distinct fresh ticket, retry execution and later independent verification | A closed final valve and reported SUCCESS alone remain `UNVERIFIED`; explicit failure stays failed |
| Provenance | Current execution envelope/context, original source mode/provider, recorded physical backend | Historical LIVE never upgrades the current REPLAY session; missing physical backend stays unknown |

Every stage is navigable. Future stage badges/subtitles remain pending, completed stages show their recorded result, and unreached stages are not applicable. The header, Director captions, audit pipeline, and renderer use the current playback stage. The terminal outcome is never displayed early. Scrubs and scenario changes select actual recorded states directly; no intermediate physical snapshots or unrelated strokes are synthesized. Numerical valve angles and worker distances are never inferred for the HUD from schematic geometry.

For safe execution, the source OPEN/v3 to CLOSED/v4 transition is shown, followed separately by recorded verification. Denial preserves the recorded open valve. TOCTOU displays the actual CLEAR/v3 to OCCUPIED/v4 transition and rejected execution. NO_OP holds the valve open through failed verification. Recovery then shows its recorded final state with the independent verification gap clearly disclosed.

## Validation

See [machine-readable gates](evidence/phase_2y_r1/quality-gates.json), [20-case Safety Lab report](evidence/phase_2y_r1/safety-lab-20.json), and [bounded assurance report](evidence/phase_2y_r1/bounded-assurance.json). Complete command output is beside these artifacts.

- Frontend: 8 files, **117 tests passed**. The presentation suite contains **26 cases**, covering all 16 requested adversarial matrix entries and mutations to policy, rationale, sensors, ticket expiry, action correlation, verification, chronology, and snapshots. Two actual renderer/HUD tests cover missing measurements and rewind. Audit/controller tests verify future-stage pending status and requested LIVE/Isaac fallback provenance.
- Backend: **620 tests passed**, including 19 added contract checks covering renamed scenarios, incomplete/failing recovery, a positively correlated recovery proof, missing final verification fields, stale verification, missing fresh authorization/execution, incorrect targets, contradictory readback, telemetry verification absence, recorded sensor sourcing, and primary action/ticket/verification correlation mutations.
- Production TypeScript/Vite build passed. The existing large-chunk warning remains.
- Lint passed with zero errors. The checked-in gate summary records the exact warning count and the baseline comparison (96 baseline warnings); lint policy was not weakened.
- Safety Lab: **20/20** expanded scenarios passed. Unsafe actuation and false-verification rates remain zero in this bounded benchmark.
- Assurance: **62/62** checks satisfied (60 registered properties plus two temporal checks), zero violated/unknown. This is bounded modeled assurance, not real-world safety certification.
- Chromium/WebGL at **1920×1080**: **12 source/mesh assertions** across safe, denied, TOCTOU and fault/recovery, including rewind and scenario switching; zero page errors. Each supplied plant snapshot is checked against the actual API source, and the applied valve mesh rotation is checked independently of DOM presence. Browser tests ran against the built production bundle and the final-code local replay server with public live disabled.

Screenshots and raw browser assertions are in [the browser evidence folder](../output/playwright/phase2y-r1/browser-evidence.json). Representative captures:

| Evidence | Capture |
| --- | --- |
| Safe independent verification | [Safe](../output/playwright/phase2y-r1/safe_verification_1920x1080.png) |
| Denial with stationary valve | [Denied](../output/playwright/phase2y-r1/denied_execution_1920x1080.png) |
| Real version/zone transition and rejection | [TOCTOU](../output/playwright/phase2y-r1/toctou_revalidation_1920x1080.png) |
| NO_OP with open valve | [Fault](../output/playwright/phase2y-r1/recovery_execution_1920x1080.png) |
| Reported recovery without independent proof | [Recovery disclosure](../output/playwright/phase2y-r1/recovery_recovery_1920x1080.png) |

## Antigravity video V3 handoff

The complete six-scene, ten-stage map is [source-map.json](evidence/phase_2y_r1/source-map.json). It includes source file SHA-256, original record hash/mode, every available source event timestamp, actual snapshots, and missing final recovery verification. Browser captures use `motionfence/fixtures/live_validation/*.json`; bundled offline console fixtures have different historical timestamps and must not be substituted silently.

At 1× playback, stage starts relative to record load are: Observe 0.0s; Evidence 1.9s; Proposal 3.8s; Policy 5.7s; Authorize 7.6s; World change 9.5s; Revalidate 11.4s; Execute 13.3s; Verify 15.2s; Recover 17.1s. These are presentation pacing, not source-event elapsed time or guaranteed absolute video timestamps. Use stage counters and source timestamps for editing. Automatic scene dwell allows all ten stages to be reached; manual scene selection stays under operator control.

| Scene/cut | Actual source timestamp (Unix seconds) | Visible evidence and appropriate wording |
| --- | --- | --- |
| Safe: authorized to actuated | `1791101352.281688` → `1791101352.282172` | OPEN/v3 → CLOSED/v4. Say recorded actuation, then cut separately to verifier `1791101352.282228` |
| Denial: policy to lock | `1791101354.1938932` → `1791101354.194241` | DENY/LOCKED; valve remains OPEN. Worker was already OCCUPIED in the initial source; do not narrate a new entry here |
| TOCTOU: authorized to drifted | `1791101356.2855418` → `1791101356.285595` | CLEAR/v3 → OCCUPIED/v4; then locked source `1791101356.28585`. Do not invent an actual comparison hash when absent |
| Fault: failed stroke to failed verification | `1791101358.9040158` → `1791101358.904087` | NO_OP with OPEN valve; failure detected. No successful physical stroke |
| Recovery: recorded terminal state | `1791101358.906016` | CLOSED/v4 recorded, reported SUCCESS, final independent verification NOT_RECORDED. Hold the disclosure visibly; do not call this verified RECOVERED |

Use the active stage subtitle as the scene caption. Keep current `REPLAY (OFFLINE FIXTURE)` and `RECORDED NEMOTRON INFERENCE` labels visible. Frame the source reference and the changing hardware state together; allow the camera to settle. The rail scrolls the expanded evidence into view, and critical recovery badges/disclosures now use readable text.

Remove or qualify these original narration claims:

- Fresh/live Nemotron, USGS or Tavily inference/retrieval during public Render replay.
- Universal 96% confidence, fabricated proposal/ticket/hash values, 14 rules, nine verified barriers, measured 24V, or 2m/5m worker measurements without those exact source fields.
- A hash mismatch when only a version-change rejection was recorded.
- Quarantine where the record says SUSPECT, or a completed physical retry/fresh authorization without their actual records.
- Independently verified recovery, upstream valve-A isolation, or restored physical outcomes inferred solely from the scene name or closed final valve.
- Universal telemetry/evidence actuation or universal zero plant mutation based on route identity. The supplied canonical records can contain governed hardware actions; records without actuation show none.
- Per-scene sub-millisecond replay or certification claims unsupported by a measured artifact. Assurance remains explicitly bounded.

## Remaining limits and deployment readiness

Historical recovery fixtures omit final independent verification and detailed fresh retry proof. They intentionally cannot display independently verified recovery. This report does not reconstruct missing events. Historical records also omit measured angle/distance/voltage, some comparison hashes, and physical-backend metadata; these remain unknown.

Historical twin pressure values were generated by an older visualization helper and differ from the canonical pressure sensor observations. They are labelled **recorded twin pressure**, not a measured sensor reading. Sealed historical fixtures were preserved. Future snapshot generation now reads the actual recorded pressure observation; a missing observation stays absent. Categorical world/hardware inconsistencies fail closed. Worker placement and valve geometry remain schematic.

Existing record hashes cover a limited canonical subset; they do not independently authenticate every sensor/snapshot field or provide current ticket signature validation. Full source-file hashes in the source map provide artifact identification. The UI does not advertise an unperformed integrity check. The frontend suite still emits some pre-existing React act/WebGL deprecation warnings; production build and lint warnings are reported without hiding them.

The corrective candidate is ready for review with passing local gates. Production remains **not deployed / held for corrective-report review**. No automatic merge or deployment is authorized by this report. Video V3 should be captured only from this reviewed correction, with unverified recovery language retained.

## Changed files

Presentation: `console/src/services/frameDerivation.ts`, `console/src/types/presentation.ts`, `console/src/types/index.ts`, `console/src/components/Stage/DecisionTwinStage.tsx` and `.css`, `console/src/components/DigitalTwin/WebGLIndustrialPlant.tsx` and `.css`.

Integration/provenance: `console/src/services/api.ts`, `console/src/App.tsx`, `console/src/components/Director/DemoDirector.tsx`, `DirectorSceneSequence.ts`, `console/src/components/DecisionReplay/DecisionReplay.tsx`, `LiveDemoController.tsx`.

Backend: `motionfence/runtime/controlled_demo.py`, `motionfence/runtime/live_demo.py`.

Verification: `console/src/test/decision_twin_stage.test.tsx`, `plant_evidence.test.tsx`, `director.test.tsx`, `console.test.tsx`, `tests/test_presentation_evidence_contract.py`, `scripts/visual_qa_phase2y_r1.py`, this report, `docs/evidence/phase_2y_r1/*`, and `output/playwright/phase2y-r1/*`.

Five pre-existing whitespace-only local edits were preserved outside the corrective commit, including the original `scripts/visual_qa_phase2y.py` edit.
