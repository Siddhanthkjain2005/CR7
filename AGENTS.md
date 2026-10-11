# ImpulseTwin AI — engineering handoff and progress

## ISO capture-time autofill — 11 October 2026

The owner postponed the walkthrough video and requested only timestamp autofill.
Waveform Diagnostics and Compare measurement now fill `captured_at` once on the
client with the device's local date/time, seconds and explicit ISO 8601 offset.
The value remains editable; **Use current time** refreshes it and **Clear time**
leaves it omitted as before. Keep the device-clock explanation: autofill is not
proof of a recording's actual capture time. Trial metadata says **Included on
upload** while it is a draft. No backend, scientific results or defaults changed.

Node 22 typecheck/build, 28 frontend unit tests (including fractional time zones,
date rollover and daylight saving), six focused browser interaction checks in an
isolated local store, and fresh-database external-network-denied smoke with 31
local assets pass. Both forms visibly contain an actual value, not a placeholder.
No browser console errors. See `artifacts/qa/october11_iso_autofill_review.json`.
The export is rebuilt; refresh the port 8000 page. Local edits only, no video,
push, deployment or cloud use.

## Fault Test Lab — 11 October 2026 (`codex/assembly-twin`)

The owner requested Front/Tail-Chopped Lightning Impulse and Generator Stage-Failure highlights. Both are implemented in the local CR7 copy, with a **Fault test lab** link beside **Assemble digitally** and an integrated section below the assembly workshop. Read `docs/fault_test_lab.md`, `docs/fault_tests_physics_review.md` and `artifacts/qa/october11_fault_tests_review.json`.

- Chopping closes an assumed finite R / optional L shunt across load capacitance. Exact state handover, passive energy decay, continuous extrema/crossings, shared healthy/fault sample grid and no target-crest rescaling. Chopped metrics are geometric descriptors, never full-wave compliance claims.
- Stage scenarios distinguish reduced-charge **fully erected conducting** stages from a declared conductive bypass. Open-gap misfire, delayed erection and distributed stage-position effects are unsupported. Bypassing every stage is rejected; all-uncharged conducting stages produce zero output with undefined timing. Bypassed capacitors may retain charge: displayed bypass energy counts only contributing stages.
- Saved `fault_test` records retain settings, nominal loss factor, effective parameters, version, generated provenance, energy scope and JSON/CSV/HTML exports. They never enter calibration, measured evidence or prior evaluation studies. Charging voltage is held fixed.
- Independent predeclared verification: 34 numerical scenarios plus four expected all-bypass rejections; all seven gates pass. Worst Radau/BDF voltage discrepancy is 0.000001512% of healthy crest within the same assumed equations. Initial four metric failures, three numerical corrections and later wording/provenance edits remain disclosed. Preserve this completed evidence; real CPRI fault accuracy is unknown.
- Final checks: **438 backend tests**, **27 frontend unit tests**, Node 22 typecheck/production build, **17 isolated browser checks**, exact downloaded CSV/JSON values, **543 original protected files** (main only adds router import/registration), and fresh-database external-network-denied smoke including 31 local assets pass. A new test-fixture global-profile leak was reproduced and corrected in the new fixture only; the pristine GitHub baseline passes 364 tests. Existing production calibration code and tests remain unchanged.
- Main server is restarted on port 8000 with saved owner history retained. Temporary port 8002 server/tab are stopped/closed; Quiet preference and viewport override restored. No screenshots/aesthetic review or real touchscreen/cross-browser/hardware validation. Local edits only; no push, deployment, cloud spend or model fit.

New backend is additive under `backend/app/fault_tests`; existing physics, optimizer, schemas, API exports, dependencies, datasets, models and completed studies remain protected. Keep all person-safety and conditional-model labels during future edits.

## Conceptual assembly digital twin — 11 October 2026 (`codex/assembly-twin`)

The owner requested an appealing RLC assembly view and person-safety briefings after recommendation. This additive frontend workshop is complete below the saved setup; use **Assemble digitally**. Read `docs/assembly_digital_twin.md` and `artifacts/qa/october11_assembly_twin_review.json`.

- Five virtual groups, drag/drop and keyboard/button alternatives, exploded/assembled schematic, component inspector, staged briefing review, remove/reset and saved-snapshot reset. Existing 3D view and 2D fallback retained. Edited requests pause placement.
- Stage and load capacitance remain distinct. Series-model totals are labelled derived and unknown facts stay unknown. Wiring still requires verified saved resistor trees. Fitted parameters are separate from nominal hardware inputs.
- Checkmarks mean briefing read only. Completion remains **Virtual review complete · physical authorization pending**. Keep these boundaries: no hardware control, physical assembly/energization recipes, safe-to-fire score, invented pulse/mounting/clearance facts or physical-safety certification.
- Node 22 typecheck/production build, all 21 frontend tests (six new), 14 isolated browser interaction/layout checks, phone and desktop widths, 361 protected hashes and fresh-database external-network-denied smoke pass. Zero browser console errors. No screenshots/visual aesthetic review or full backend-suite rerun for this frontend-only change.
- CR7 now resides at `/Users/swetha/Downloads/HACKTHON_WIN/CR7`; the old `/private/tmp/impulse-cr7-oct11` checkout was moved with its saved history intact. Main app is served locally on port 8000. Temporary QA server/tab are cleaned up after verification.
- Local edits and rebuilt export only; no push, cloud use or deployment. Preserve frozen studies, defaults, API exports and the safety/source labels during future changes.

## Capture admission fixes and Waveform Diagnostics — 11 October 2026 (`codex/waveform-diagnostics`)

Built on `codex/effective-parameter-calibration` (`2de2d4c`). Local branch; not pushed. Read `docs/capture_admission.md` and `docs/waveform_diagnostics.md`.

- [x] **External validation defects, each reproduced by a failing test on `2de2d4c` first** (`tests/test_capture_admission.py`).
  1. **Precursor.** Precursor and recrossing fronts no longer show NOMINAL PASS. Acquisition review v4 adds a connected-rise check (noise-aware), a stalled-rise check and a dip-after-90 % check. The connected main-limb front is shown for review only, never substituted.
  2. **Polarity.** The declared polarity is re-checked on every route: correction, parameter fit, evaluation and laboratory summary.
  3. **Different firing settings.** A shot at other settings is compared with the as-fired prediction (`model_residual`, `configuration_difference`). It can no longer create an offset on the original setting.
  4. **Out-of-rating settings.** Out-of-rating as-fired settings need an append-only recorded review.
- [x] **One shared admission** (`backend/app/capture_admission.py`) used by every route. Reviews are append-only `capture_review` records (`POST /api/trials/{id}/reviews`, `GET /api/trials/{id}/admission`).
- [x] **Waveform Diagnostics** (`/diagnostics/`, additive `/api/diagnostics`): versioned reference and as-fired snapshots, CSV or image upload with origin declaration and checksum, local digitization with recorded transforms, comparison, physics inverse analysis, findings, report, hypothetical exploration and a labelled generated demonstration. Image-derived samples never enter calibration or evaluation.
- [x] **Solver refactor.** `circuit.response()` shares the modal solution with `simulate()`, which is bitwise identical on 3,000 random circuits. The `front_scale` and `extra_l_uh` effective keys default to no change and are set only by an explicit hypothetical exploration.
- [x] **Evaluation.** The protocol was committed before the fixtures ran (`artifacts/waveform_diagnostics/v1`). 7 of 8 gates pass. **G3 fails:** a slow second tail component is absorbed by an effective tail resistance and reported as "Possible cause: tail network". The post-run fixes (one save bug, two wording changes, one memory bound) are disclosed in `case_revisions.json`; no threshold or fixture changed.
- [x] **Verification:**
  - backend tests, frontend typecheck and 15 unit tests;
  - harness browser checks for the new page, existing behaviours and the admission UI;
  - protected hashes.

  The Next production build could not run in this sandbox. Rebuild `frontend/out` with Node 22 (`cd frontend && npm run build -- --webpack`).
- **Not established.** Real CPRI accuracy, and diagnosis on real photos and real faults, are unknown.

## Better approach — 10 October 2026 (`codex/effective-parameter-calibration`)

Built on `codex/hardening-judge-workflow`.

- **New method.** Calibration shots fit three effective circuit parameters (loss scale, extra load-side capacitance, effective tail resistance). They are applied at every setting of the same generator, impulse type and layout.
- **Why.** The existing one-shot offset only applies to identical settings within 1 % of the request, so it cannot use a reduced-voltage shot.
- **Evidence.** The simulated model-mismatch study (`artifacts/parameter_calibration/v1`, gates declared first) passes all gates:
  - Median errors fall from 3–4 % to below 0.03 %.
  - Recommendations passing on the stand-in generator rise from 6/12 to 12/12.
  - With measurement noise (`v1_measurement_noise`), errors are roughly halved and recommendations still go from 6/12 to 12/12.
- **Safeguards.** Validation captures cannot fit parameters, and fit captures are excluded from independent evaluation.
- **Not established.** This is simulation evidence only; read `docs/parameter_calibration.md`.

## Current task — 10 October 2026 (supersedes earlier task-specific limits)

Branch `codex/hardening-judge-workflow`, based on `feat/engineering-hardening` (`efde726`).
The organizer clarification allows other datasets and appropriately generated
synthetic data; correctness, practical evaluation and a simple judge interface
come first. New training and UI redesign are authorized. Historical datasets,
model artifacts and experiment results are preserved; the saved Hidden Test is
not used for tuning. Keep CPRI (12 stages, 0.125 µF/stage) and workbook
(15 stages, 3 µF/stage) parameters separate. Stage capacitance is not stray
capacitance; available stages are an input, active stages an output.

Progress (updated as work lands):

- [x] Baseline on `efde726`: 263/263 backend tests pass (Linux sandbox, Python 3.13).
- [x] Waveform audit: every plotted curve is labelled (circuit prediction, shape
  reconstructed from metrics, target shape, measured). Metrics are re-extracted
  from the exact plotted samples and checked against the displayed metrics
  (`waveform_consistency`); circuit metrics come from the final solve at the
  recommended charge. Locally corrected metrics are never drawn on an
  uncorrected curve.
- [x] Physics audit (`scripts/physics_audit.py`): independent integrator agrees
  to ~1e-6 %; workbook equations and alternative topologies differ by several
  to tens of percent; the efficiency input stacks on top of the circuit's own
  voltage utilisation (see `docs/physics_audit.md`).
- [x] Ported from `codex/switching-crest-review`: slow-pole verification fix,
  acquisition review v3, calibration-origin review, external data review
  (incl. Zenodo 8435957) and the independent numerical verification.
- [x] Custom generator profile (complete ratings, same series-Marx topology,
  circuit only); profiles renamed; equipment-reference message replaced.
- [x] Measured import: capture purpose (validation never calibrates; calibration
  never evaluates), divider scale with source, expected polarity, session/shot,
  as-fired re-simulation.
- [x] Versioned simulation dataset `data/generated/circuit_dataset_v1` (59,903 rows from
  40,000 configurations; CPRI, workbook and custom families; failures, ringing and
  infeasible settings kept; grouped split; test frozen by hash). Labels are circuit
  outcomes, never targets. Learning curve plateaus near 4,000 rows.
- [x] Circuit surrogate `artifacts/models/circuit_surrogate_v1` (numpy weights, protocol
  declared before the single test scoring): frozen-test p95 error <= 0.34 %, worst
  1.54 %, ~570x faster. Used only for screening; surrogate-screened search was
  equal-or-better in 24/24 requests but strictly better in only 1 at ~4 % more runtime,
  so it is NOT promoted and the default search is unchanged.
- [x] Evaluation pack `scripts/evaluation_pack.py`: 36 requests, 36/36 expected outcomes,
  0 false passes on the circuit path, 14/14 bounded = exhaustive; workbook-equation
  engine shows 9/9 passes that fail in the circuit (kept as a labelled benchmark);
  workbook calculator settings pass 0/27 in the circuit.
- [x] Judge UI: Configure test -> Recommend settings -> Inspect waveform -> Compare
  measurement; 3D generator stack and resistor schematics; V/kV crest; custom
  generator; evidence collapsed; Model lab leads with what is demonstrated.
- [x] Reports: `docs/accuracy_report.md`, `docs/physics_audit.md`,
  `docs/laboratory_validation_checklist.md`; QA in `artifacts/qa/october10_*`.
- [x] Verification: 327 backend tests, 45 protected hashes, registry, external checksums,
  frontend typecheck and 11 unit tests, harness render/hydration/behaviour checks.
  The Next production build could not run in this sandbox: rebuild `frontend/out`
  with Node 22 (`cd frontend && npm run build -- --webpack`) before demoing.

Open questions for the team (they move predictions the most): whether the 0.83
efficiency input is an extra loss or the overall efficiency; whether 545 pF is already
inside the divider capacitance; how the tail and charging resistors are connected.

## Current task — 6 October 2026

Work from `feat/engineering-hardening`, based on current main commit
`047841f587c4b00bc8d018d5174961d3356eebbf`. The user requests the final
optimization/hardening brief and a selective cleanup of the existing UI.
The detailed final evidence is in `OPTIMIZATION_REPORT.md` and
`artifacts/optimization_report.json`.

## Engineering constraints

- CPRI's problem-statement profile is the primary physical reference. Keep the
  15-stage/3 µF workbook benchmark separate from the 12-stage/0.125 µF machine.
- Preserve supplied sources, frozen V1 weights, saved Hidden Test results and
  V2–V5 experiment evidence. Do not tune on Hidden Test or fit another ML version.
- CPRI recommendations use circuit physics; workbook residual ML has no validated
  transfer to this profile. Unsupported corrections remain disabled.
- Unknown stock quantities, mounting and pulse ratings stay unknown. Demo stock
  is an explicitly labeled assumption, never a statement of laboratory inventory.
- Generated captures remain generated. Measured data is not a prerequisite for
  this hardening task and no laboratory-accuracy claim is created.
- Preserve the existing product scope, pages and seven Judge Mode steps. Improve
  readability and correct ambiguous labels/defaults. Do not deploy.

## Progress

- [x] Read the new brief and inspect current main; prior evidence work is merged.
- [x] Record protected file hashes, fixed runtime/profile snapshots and four
  bounded/exhaustive comparisons before backend changes.
- [x] Baseline frontend typecheck and production build pass on Windows.
- [x] Preserve the initial Windows native crash log; unchanged isolated baseline
  passes 237 tests with bounded native threads. The crash root cause is unproven.
- [x] Reproduce CPRI 1425 kV: 11 stages, 181.902790 kV/stage, 30 Ω/520 Ω,
  22.748430 kJ. No change to CPRI physical equations is justified.
- [x] Identify early circuit charge filtering that excludes valid inductive
  overshoot setups; retain actual solved voltage/energy limits.
- [x] Identify numerical edge cases in absolute tiny-L reduction and crossing
  tolerance; audit stable zero-inductance formulation before keeping a correction.
- [x] Profile pandas support-check/base-slicing overhead; preserve ML outputs,
  thresholds and scalar workbook rounding during optimization.
- [x] Implement focused fixes: circuit numerical policy v2.1, actual-charge stage
  eligibility, single-solve normalization, exact inference batching, energy limits.
- [x] Add 26 targeted regressions; all 263 backend tests pass. Four warnings:
  existing pytest-option/Starlette notices and two Windows cache permissions.
- [x] Preserve all ranked settings/metrics in the three pipeline comparisons;
  4,096 inference outputs exactly match original code. Four exhaustive fixtures
  retain rank 1 and zero gap; all are nominal failures, so scope remains limited.
- [x] Predeclare and execute two additional CPRI circuit development comparisons.
  LI and SI both nominally pass; bounded/exhaustive top-1/top-3 match with zero
  gap before/after. These are development checks with assumed stock, not held-out
  physical validation, and no weights/shortlists/models were tuned.
- [x] Polish navigation/typography, CPRI defaults, stock/ML/second-model labels,
  saved-trial source/admission and preservation of pending operator requests.
- [x] Verify desktop CPRI walkthrough, generated feedback and mobile layout.
  Fresh browser found a pre-existing server/client locale mismatch; deterministic
  numeric hints, rebuilt export and fresh-origin review now yield zero errors.
- [x] Final frontend typecheck/build, 23 local static assets and fresh-database
  external-network-denied smoke pass. Other platforms/disconnected browser remain
  explicitly untested; overall release status is PARTIAL for those omissions.
- [x] Produce both final optimization reports and retained browser/runtime/search/
  test records. Workbook LI/SI warm medians improve 34.0%/11.4%; CPRI is 4.3%
  slower while checking 11 rather than 4 stage/network pairs for correctness.

The separate CPRI pseudo-laboratory waveform pack mentioned in the brief is not
present in current main or the supplied new attachment. Existing generated
fixtures and new narrowly scoped synthetic regression cases cover failure modes;
they are not treated as supplied measurements.

## Starting locally

Use the repository Python environment with `PYTHONUTF8=1` and run
`python scripts/dev.py`, then open `http://127.0.0.1:8000/judge/`.
See `docs/release_readiness.md` for installation and platform limitations.
The old release ZIP and earlier QA summaries are historical records.
