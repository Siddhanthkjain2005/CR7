# Continue ImpulseTwin AI

## Capture admission fixes and Waveform Diagnostics — 11 October 2026

Branch `codex/waveform-diagnostics` from `codex/effective-parameter-calibration`. It is local only and has not been pushed. Read `docs/capture_admission.md` and `docs/waveform_diagnostics.md`.

- **Defects fixed.** Three calibration defects found by the external validation are fixed in shared backend logic, so they apply on every route, not only in the UI:
  1. A precursor no longer shows as a nominal pass.
  2. A polarity mismatch is blocked everywhere.
  3. A shot fired at other settings is compared with its as-fired prediction and never corrects the original setting.

  Out-of-rating as-fired settings need a recorded review.
- **New page.** Waveform Diagnostics (Test setup) compares a CSV or a photo of a waveform with the circuit prediction at the settings actually fired. It then fits physically meaningful explanations with the existing solver. Fit scores are not fault probabilities.
- **Evaluation.** Generated fixtures only: 7 of 8 declared gates pass, and one off-model case is wrongly attributed (G3, reported, not tuned). Real CPRI accuracy is unknown.
- **Rebuild needed.** Rebuild `frontend/out` with Node 22 before demoing.

## Judge workflow and practical evaluation — 10 October 2026

Branch `codex/hardening-judge-workflow` from `feat/engineering-hardening` (`efde726`). Read `AGENTS.md`, `docs/accuracy_report.md`, `docs/physics_audit.md` and `docs/laboratory_validation_checklist.md`.

- **Waveforms.** Every plotted waveform is labelled, and its metrics are re-extracted from the plotted samples.
- **New tools.** A custom generator profile (complete ratings, same topology), measured import with purpose, scale, polarity and as-fired re-simulation, a versioned simulation dataset, a gated circuit surrogate (not promoted for search) and a 36-request evaluation pack.
- **Interface.** The primary interface is `/`. The seven-step walkthrough remains at `/judge/`.
- **Rebuild needed.** Rebuild `frontend/out` with Node 22 before running the app; the committed export predates this branch.
- **Not established.** No measured accuracy; see the checklist.

## Engineering hardening handoff — 6 October 2026

Continue `feat/engineering-hardening`, based on main `047841f587c4b00bc8d018d5174961d3356eebbf`. Read `AGENTS.md`, `OPTIMIZATION_REPORT.md`, `artifacts/optimization_report.json`, `PROJECT_STATE.md` and `docs/assumptions.md`. **Final verification:** 263 backend tests, frontend typecheck/build, frozen hashes, fresh-database/local assets and desktop/mobile browser checks pass. Four exhaustive fixtures retain rank 1/zero gap; 4,096 inference outputs match original code exactly. Overall readiness is PARTIAL for unexecuted platform/disconnected-browser checks. Historical counts and archives below retain their earlier scope.

The engineering UI/Judge default is the CPRI physical profile with circuit physics and workbook residual ML disabled. The supplied clarification identifies its 12-stage / 200 kV / 0.125 µF / 2.5 kJ-per-stage / 30 kJ-total values as the actual/reference generator parameters. Workbook 15-stage / 3 µF remains a separate synthetic reference and frozen V1 benchmark. CPRI stock is unknown: require explicit counted inventory/provenance before optimizing. Load/parasitic/efficiency example inputs and the configured 50 kV/two-stage application floors must not be presented as measurements or verified operating minima. Include 545 pF only when it is not already represented elsewhere.

Circuit v2.1 changes numerical handling, not the physical equations: stable analytic RC modes/peak, a dimensionless safeguard for significant tiny inductance, scale-aware crossing roots and explicit unresolved crest/decay diagnostics. Earlier solver-version calibrations are rejected. The matched 1425 kV CPRI Lightning case and poor-resistor timing failures are protected by regression tests. The unchanged baseline passed 237 tests in isolation after an initial native Windows crash; the hardened full suite passes 263. Keep the failed process log and avoid claiming its root cause is established.

Keep nominal model compliance, uncertainty containment, sampled scenario fractions, generated feedback and measured evaluation distinct. Preserve frozen V1–V5 evidence and the exposed Hidden Test. Do not train another model, deploy, fabricate laboratory claims or expand product scope. Remaining physical facts to obtain are actual stock, pulse ratings, mounting/topology rules and minimum operating limits. Independent measured waveforms can validate future laboratory performance; they are not required to solve the current challenge.

The sections below are preserved historical handoffs. Use the current source and final hardening report for this pass rather than assuming an earlier ZIP or QA count is current.

Two additional predeclared CPRI circuit development comparisons (LI and SI) pass nominally and retain bounded/exhaustive top-1/top-3 agreement with zero gap before/after. Their explicit assumed stock and shared-physics limitations are recorded in `artifacts/hardening/circuit_search_comparison.json`; they are not held-out evaluation or physical validation.

## Evidence and Judge Mode update — 3 October 2026

The evidence/release feature branch adds unified capture provenance, Laboratory Evidence, Hardware Verification, a versioned test-object catalog, deterministic recommendation evidence levels, a controlled exhaustive search benchmark, saved-artifact experiment timeline and seven-step Judge Mode. Existing engineering workflows and frozen V1–V5 evidence remain preserved. README now links deep history rather than accumulating every release note.

Use `python scripts/verify_release.py` for the current report and `docs/release_readiness.md` for cross-platform setup. Original QA files and release ZIP are historical; the latest source and rebuilt static frontend on this branch are authoritative for this update. Windows clean setup, automated checks and fresh-database/offline-process checks are recorded in the new release report; untested platforms remain explicit. No deployment or new model training occurred.


Repository: https://github.com/Siddhanthkjain2005/Impulse

Read this guide, then `PROJECT_STATE.md`, `docs/judging_criteria_evidence.md` and `docs/accuracy_progress.md`. Source discrepancies are documented in `docs/source_reconciliation.md`; detailed search and experiment results are linked below. The finale readiness deadline is 10 October 2026. Official event dates are 10–11 October.

## Continuation snapshot — 3 October 2026

The latest handoff includes the working local app, prebuilt UI, frozen model artifacts, original supplied sources, V2–V5 experiment evidence, 198 passing backend tests, fallback reports and the offline release ZIP. The most recent work improves capture-quality review and measured-shot decision reporting, adds RLC sensitivity and setup-change planning, and documents the organizer's published expectations.

V1 remains the default; V2 is an explicit experimental option. V3, V4 and V5 failed their promotion gates. The recorded V1 synthetic benchmark improves macro error by 41.9265% versus physics; V2's 5.3656% improvement is development CV evidence. No measured laboratory accuracy or 100% accuracy has been established. Keep these evidence types separate when presenting.

Continue in this order:

1. Run the prepared app and verify installation on a second laptop; rehearse with internet disconnected. Keep the 10 October readiness deadline in view.
2. Confirm actual generator settings, stock quantities, component ratings and allowed connections with the laboratory team. Keep conflicting workbook, PDF and briefing profiles separate.
3. Obtain real waveform captures with full setup metadata. Save predictions before uploads, separate calibration and evaluation captures, and follow `docs/laboratory_capture_plan.md`. Use the existing measured-shot review to report errors and false PASS/FAIL decisions.
4. Address demonstrated failures and presentation usability, then freeze the demo and rehearse `docs/demo_script.md` and `docs/judges_qa.md`. Preserve all failed-study and frozen-test evidence.

For another coding assistant, paste [the continuation prompt](docs/continuation_prompt.md). It carries the project's goals, current decisions, constraints and next tasks. Cloud deployment remains deferred by the owner.

## Start the application

Use Python 3.12. The prebuilt interface and model artifacts are committed, so Node is only needed when modifying or rebuilding the frontend.

```sh
git clone https://github.com/Siddhanthkjain2005/Impulse.git
cd Impulse
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make demo PYTHON=.venv/bin/python
```

Open http://127.0.0.1:8000. API documentation is available at http://127.0.0.1:8000/docs. No cloud credentials or external inference services are required.

## Make and verify changes

Install Node 22+ for frontend development:

```sh
cd frontend
npm ci
cd ..
make build
make test PYTHON=.venv/bin/python
```

The latest recorded backend suite has 198 passing tests. Browser, build, offline-asset and model-freeze evidence is in `artifacts/qa_summary.json` and `artifacts/qa/`. A clean installation on a second machine still needs rehearsal.

Create a feature branch for changes. Do not force-push or replace the preserved model evidence.

## Important continuation constraints

- Each ranked candidate now has 144 post-ranking scenario checks. Inspect failures and the worst-case inputs; these checks never rerank candidates. Circuit v2 refines continuous waveform crossings.
- The new agreement search is optional: preset G or the button beside a failed circuit cross-check. It finds both-model nominal passes for the default Lightning case; uncertainty remains MARGINAL. V3 did not meet its promotion gate and was not activated.
- V1 is the default. V2 is available through the optimizer's advanced residual-correction selector and is explicitly experimental.
- V2's 5.37% macro error improvement is Train cross-validation development evidence, with a small Lightning-tail regression. It is not a new untouched test or laboratory accuracy claim.
- Preserve `artifacts/models/hidden_test_evaluation.json` and the frozen V1 models. Do not reuse the exposed Hidden Test for tuning or overwrite the completed V2 experiment. New experiments need separate names and untouched final data.
- All supplied training outcomes are synthetic and compliant. Arbitrary resistor/stage interventions and constructible Switching hardware lack corresponding training evidence; runtime support checks disable learned corrections where appropriate.
- Workbook, PDF and briefing generator profiles disagree. Keep them separate. Real stock quantities, pulse ratings, mounting and laboratory waveforms remain unverified.
- Cloud training was authorized using the user's reported $300 credit, but no resources or spending were needed. Cloud deployment remains explicitly deferred until the user requests it. No credentials are included.
- Never label generated rehearsal CSVs as measured laboratory shots. Live histories, raw uploaded trials, dependencies, caches and temporary files are excluded from Git.

## Where to work

| Area | Location |
|---|---|
| API, runtime support and experiment serving | `backend/app/main.py`, `backend/app/ml/registry.py` |
| Physics and compliance | `backend/app/physics/` |
| Hardware search and ranking | `backend/app/optimization/` |
| Frozen V1 training and separate V2 search | `backend/app/ml/train.py`, `backend/app/ml/experiment_v2.py` |
| UI source / prepared interface | `frontend/` / `frontend/out/` |
| Original sources and processed records | `data/source/`, `data/processed/` |
| Optional experiment training dependencies | `requirements-experiments.txt` |
| Judge pitch, demo and remaining validation | `docs/` |
| Five generated fallback reports and CSVs | `reports/demo_*.html`, `data/demo/` |
| Packaged offline handoff | `release/ImpulseTwin_AI_Local_PoC.zip` |

The release ZIP includes the latest verified local handoff. Use the repository for subsequent development; regenerate the archive with `python -m scripts.package_release` after recording successful QA if you need a new release.

Latest feedback changes: see `docs/trial_feedback_update.md` for repeated-shot calibration, capture review, selected-candidate CSVs and the run-evidence views. The capture checks are application heuristics, not measurement-system certification.

For new laboratory evidence, use Trial calibrator → Verify accuracy on new shots. Keep evaluation captures separate from all calibration ancestors. The original raw CSVs must be present. See `docs/accuracy_progress.md`; test fixtures are synthetic and do not populate live laboratory scores.

For the hardware-change demonstration, open Compare → Plan changes from a saved setup, select a baseline run/candidate, and export Printable change plan. It compares the same generator/layout and does not change the optimizer ranking. See `docs/setup_transition_planner.md`.

For the RLC explanation, open Optimizer → Explore R, L and C. Preview object capacitance +30% on the Lightning agreement case, select Equivalent circuit and Front / peak detail, and explain the front-time limit crossing. Preview audit JSON preserves the generated evidence. Resistor previews are hypothetical; saved recommendations remain unchanged. See `docs/rlc_sensitivity.md`.


## Latest pooled accuracy study

The V4 Train-only experiment tested 48 shared/partially pooled configurations with both impulse types held out in every shared fit. No pooled candidate passed the inner selection gate; additional macro improvement was 0.0000%, and V1/V2 remain unchanged. The Model lab now records this result. Read `docs/accuracy_v4_results.md` before further tuning; preserve the frozen evidence and obtain new measured outcomes for independent accuracy evaluation. No cloud resources were created.


## Accuracy and judging update — 3 October 2026

Official and supplied expectations are mapped in `docs/judging_criteria_evidence.md`; no finale numeric weights were found. Prioritize accurate predictions, feasible counted hardware, both impulse types, numeric compliance and credible measured feedback. Public event dates are 10–11 October; team readiness remains 10 October.

V5 added 1.0921% macro Train development improvement versus a historical V2 refit (0.2363% beyond a matched Ridge control), below its 5% gate. It was not promoted; V1/V2 and old model evidence remain frozen. See `docs/accuracy_v5_results.md`.

Capture-resolution review now blocks three demonstrated sparse-waveform false passes from calibration and scoring, preserving raw samples and provisional extracted values. The measured-shot review adds false PASS/FAIL counts, denominators, worst-shot errors, saved-rule snapshots and separate envelope containment. See `docs/capture_resolution_review.md` and `docs/measured_decision_review.md`. No new laboratory accuracy result exists. Website previews were omitted at the user's request for this update; automated checks are recorded separately.
