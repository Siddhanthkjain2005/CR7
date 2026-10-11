# ImpulseTwin AI project state

## Current packaged version — 11 October 2026

Branch `codex/assembly-twin`, based on CR7 main `b02baeb`, contains the conceptual
assembly workshop, additive chopped-impulse/stage-failure lab and ISO capture-time
autofill. The frontend export has been rebuilt with Node 22. Read the latest
`HANDOFF.md` section and `AGENTS.md` for setup, verification and model limitations.
Latest checks are 438 backend tests for the fault implementation and 28 frontend
unit tests after timestamp autofill; the backend suite was not rerun for the
frontend-only timestamp change. Numerical verification is not laboratory accuracy.
The owner authorized a CR7 GitHub push; cloud deployment and video remain deferred.

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

## Engineering hardening — 6 October 2026

Current work starts from main commit `047841f587c4b00bc8d018d5174961d3356eebbf` on `feat/engineering-hardening`. Its scope is correctness, numerical stability, bounded-search/runtime efficiency, source clarity and restrained UI polish. No new product features, deployment, model training or Hidden Test tuning are part of this pass. The task record is in `AGENTS.md`; the final rationale and measured comparison are in `OPTIMIZATION_REPORT.md` and `artifacts/optimization_report.json`.

The organizer clarification supplied for this task identifies the problem-statement parameters as the actual/reference CPRI generator inputs. The UI and Judge Mode therefore start with the **CPRI physical profile, circuit solver and residual ML off**. The separate workbook 15-stage / 3 µF reference retains frozen V1 synthetic benchmarking and its supported reference-solver ML path. Unknown CPRI stock quantities require explicit counts and provenance. The UI's parasitic/efficiency values are editable model examples; configured 50 kV/two-stage lower bounds are application assumptions, not established physical minima. The 545 pF contribution is explicit and must be counted only once.

Circuit v2.1 preserves the nodal equations and topology while stabilizing analytic zero-inductance modes/crest, retaining significant tiny inductance and refining fast crossings at a scale-aware tolerance. Unresolved continuous crests or stable decay modes produce diagnostic failures. Older calibration scopes do not transfer to the new solver version. The CPRI Lightning regression retains 11 stages, approximately 181.90 kV/stage, 1.187 µs front, 53.744 µs tail, 1425 kV crest and 22.75 kJ charging-bank energy. See `docs/assumptions.md` for equations, units, numerical policy and omitted physical dynamics.

Final verification passes **263 backend tests** (all 237 previous tests plus 26 targeted regressions), frontend typecheck/build, 45 protected hashes, local asset/fresh-database smoke and desktop/mobile browser checks. Four exhaustive fixtures retain top-1/top-3 agreement and zero gap; 4,096 inference outputs match original code. Workbook LI/SI warm runtime improves 34.0%/11.4%; CPRI checks more stage counts and is 4.3% slower. The final optimization report records methods, the initial native Windows baseline crash and all limits. Prior test counts, release ZIPs and dated QA below describe their original releases. Nominal pass, interval containment and finite scenario fractions remain separate model statements. Generated data remains generated; measured laboratory accuracy remains unestablished.

For physical application, obtain actual stock counts, pulse ratings, permitted mounting/connection rules and minimum operating limits. Measured voltage-time captures are not a prerequisite for the current challenge solution; they can later support independent laboratory performance evaluation. Keep the historical record below intact when continuing.

The primary path also has two newly predeclared CPRI circuit development comparisons, LI and SI. Before and after, both bounded/exhaustive winners nominally pass with top-1/top-3 agreement and zero gap. These use assumed stock and shared physics/scoring, so they improve search coverage evidence without becoming physical or held-out validation. No tuning followed the results.

## Evidence and Judge Mode update — 3 October 2026

The evidence/release feature branch adds unified capture provenance, Laboratory Evidence, Hardware Verification, a versioned test-object catalog, deterministic recommendation evidence levels, a controlled exhaustive search benchmark, saved-artifact experiment timeline and seven-step Judge Mode. Existing engineering workflows and frozen V1–V5 evidence remain preserved. README now links deep history rather than accumulating every release note.

Use `python scripts/verify_release.py` for the current report and `docs/release_readiness.md` for cross-platform setup. Original QA files and release ZIP are historical; the latest source and rebuilt static frontend on this branch are authoritative for this update. Windows clean setup, automated checks and fresh-database/offline-process checks are recorded in the new release report; untested platforms remain explicit. No deployment or new model training occurred.


Readiness deadline: **10 October 2026**. Inputs reviewed: supplied master prompt, Track 1 archive, and briefing transcript. Updated 3 October 2026. Current status: working local engineering proof of concept with a separate optional V2 accuracy candidate; earlier browser reviews and current automated release evidence are recorded in `artifacts/qa_summary.json`. The latest update has no browser preview, as requested by the user.

## Implemented and verified

- Original sources preserved, six workbook sheets exported, full formulas/cached-cell snapshot and SHA manifests retained.
- Exact 1425 kV golden case and every one of the 1,400 cached neighbor distances/weights reproduced.
- Separate PDF, workbook and incomplete briefing profiles, with source provenance and explicit stock assumptions.
- Reference equations and independent lumped RLC simulation, shared waveform extraction, energy diagnostics and versioned challenge compliance.
- Counted discrete resistor networks, hard voltage/energy/inventory filters, five ranked alternatives and transparent score terms.
- Frozen V1 per-regime residual model competition, one-time final synthetic test, OOD gating, synthetic marginal intervals and sampled parasitic scenarios.
- A strengthened model-support guard requires calculator-selected stages, charge and resistor settings as well as range/distance support; arbitrary setting interventions receive physics fallback. Unsupported parasitic scenarios widen envelopes and remove calibrated coverage claims.
- Separate targetwise V2 experiment with nested Train CV, frozen candidate, disjoint calibration, joint synthetic envelopes and an explicit optional selector. V1 remains the default.
- Six-page responsive local interface, interactive numeric waveforms, model evidence, profiles, run history and comparison.
- Raw CSV preservation, explicit units/polarity/onset, generated-data labeling, scoped one-shot correction and retained original-setting review.
- Local audit histories, readable print-ready reports, five regenerated offline fallback reports, generated rehearsal CSVs and judge preparation documents. Reference/circuit disagreement remains prominent in each applicable report.
- **198 backend regression/E2E tests pass** with zero failures/errors. Latest frontend typecheck and static build pass. Static asset verification finds 17 local assets, no remote/missing assets and successful local serving. Earlier dated browser checks verified the accuracy dashboard, optional V2 optimizer and mobile layouts. This update intentionally omits website previews; see QA artifacts for exact scope.

## Demonstrated benchmark

All six selected outputs improve RMSE over physics on the frozen synthetic Hidden Test; five improve on exact workbook kNN. Switching crest is 4.88% worse than kNN. The model was not changed in response. These results do not establish laboratory accuracy, first-shot success or reduced setup changes.

The optional V2 candidate improves macro tolerance-normalized RMSE by **5.3656%** in a matched-row nested Train CV development comparison. Five outputs improve; Lightning tail is **0.5192% worse**. Prior feature exploration and V1 family/hyperparameter selection limit the interpretation; this is not an unbiased final test estimate. Final weights/configuration were frozen before disjoint calibration. No new Hidden Test evaluation or laboratory evaluation was performed.

The V2 search ran locally in **54.96 seconds** with **$0 cloud spend**. Independent SHA checks confirm the V1 model, registry and saved Hidden Test artifact remain unchanged relative to the preregistered protocol. Candidate, protocol and frozen-selection hashes also match. Evidence: `artifacts/qa/freeze_and_release_review.json`; detailed results: `docs/accuracy_v2_results.md`.

Benchmark scores evaluate residual predictions before runtime support and scenario gating. The optimizer can fall back to physics and widen its envelope; the saved errors are not a laboratory or complete-optimizer accuracy estimate.

## Remaining external limits

- The workbook's hardcoded Model Validation table disagrees with evaluation of its own formulas; source reconciliation records the unresolved exception.
- Actual CPRI resistor quantities, allowed mountings, pulse ratings, machine configuration and the role of 545 pF need confirmation.
- No measured laboratory waveforms or verified equipment BIL catalog were supplied. Circuit topology and uncertainty need engineer/laboratory validation.
- Constructible Switching settings differ from training stock and are flagged outside model support. The bounded optimizer does not prove a global optimum.
- V1's shared original-unit CV objective can be dominated by larger-unit targets. V2 uses separate target searches and tolerance-scaled scoring, but new independent data is still needed for an external accuracy claim; the exposed Hidden Test must not become a tuning set.
- Fresh-machine installation on a second laptop and a physically disconnected-network rehearsal remain team tasks before the finale. Archive verification on the current machine is recorded separately.

## Cloud hold

The user authorized additional compute and explicitly deferred cloud deployment. **No cloud resources were created, no cloud credit was spent and no cloud deployment was performed.** The compact V2 search needed only local compute. The $300 credit remains available for a justified later bottleneck; deployment awaits explicit authorization. Local inference requires no external service.

## Start here

Run `make demo` or double-click `Start_ImpulseTwin.command` on the prepared Mac. Open `http://127.0.0.1:8000`. Rehearse with `docs/demo_script.md`, `docs/judge_pitch.md`, `docs/judges_qa.md` and `docs/finale_readiness.md`. Review the optional experiment through `docs/accuracy_v2_results.md`.

The release input inspection confirms live SQLite histories and raw uploads are excluded. The ZIP includes source, frozen models, optional V2 evidence, static interface, five reports and executed QA. Its manifest and extracted application checks are recorded in the release verification.

## Latest agreement and accuracy work

Optional two-model agreement search, clearer waveform-failure labels, an agreement comparison table, and a fifth fallback report are implemented. Three of five declared engineering diagnostic cases gain nominal agreement; Switching and PDF examples remain failures. The default Lightning agreement case passes both simulations in 32 sampled parasitic scenarios but remains MARGINAL under its unsupported-settings uncertainty envelope. This is not laboratory accuracy.

The further V3 Train-only nested search achieved 1.0339% macro improvement versus a historical V2 refit and failed the 5% gate. V1/V2 remain unchanged. Calibration bias is now applied only to scenarios within the saved 1% input scope. See `docs/accuracy_v3_results.md` and the latest QA records.

## Search and numerical verification update

Expanded four-part series/parallel networks (six parts for small catalogs) and identical parallel banks now preserve stock counts and earlier target choices. Circuit v2 refines continuous crossing times and passes independent time-domain integration tests. Every returned setup receives 128 fresh-seed samples and 16 boundary corners after ranking; these do not reorder results. The UI shows their limiting condition and overlays the independent circuit waveform. The default Lightning agreement, two additional Lightning cases and both PDF circuit presets pass all sampled checks. Two model-agreement cases still fail, and uncertainty remains MARGINAL. See `docs/search_v4_results.md` and `artifacts/experiments/search_v4/final_summary.json`. No cloud compute was necessary.

## Trial feedback and evidence update

Repeated-shot calibration retains the total correction relative to the original model and records parent lineage. Selected-candidate demo downloads and explicit candidate validation prevent misattributed waveforms. New calibration creation reviews acquisition resolution and flat crests while retaining raw uploads. Run history and Compare separate nominal agreement, fresh scenario checks and unchanged uncertainty status, with missing legacy evidence left unknown. See `docs/trial_feedback_update.md`. This update does not retrain models or establish measured accuracy.

## Saved-prediction laboratory accuracy review

The new `/api/evaluations` workflow scores at least three distinct operator-labeled measured captures against their pre-upload saved predictions. It verifies original CSV hashes, rejects duplicate waveforms and recursively excludes every applied calibration source. It reports errors separately by impulse, profile/version, layout, solver and model version without fitting or promotion. The UI is in Trial calibrator. Current frozen V1 synthetic macro error reduction is 41.9265% versus physics; this update does not add a measured accuracy result. See `docs/accuracy_progress.md`.

## Saved setup transition planner

Compare now calculates front/tail component changes from a saved baseline and chooses the closest nominally passing option by declared change preference. It requires recorded nominal model, stock and recomputed rating checks; challenge results remain separate and cannot rerank the option. Stage activation/deactivation quantities are distinct from shared-stage parts. Printable HTML and JSON preserve both source-record hashes. Optimizer trial curves now use the same normalized comparison as Trial calibrator. See `docs/setup_transition_planner.md`.

## RLC educational sensitivity

Optimizer now compares one changed R, L or C value with the saved setup under both raw physics models, with fixed active stages, charging voltage and efficiency. Nominal waveform limits, hypothetical resistor values, different curve sources and unchanged saved uncertainty remain explicit. The audit export hashes its source run and captures both current physics versions. No ML residuals or calibration transfer are applied. See `docs/rlc_sensitivity.md`.


## Latest pooled accuracy study

The V4 Train-only experiment tested 48 shared/partially pooled configurations with both impulse types held out in every shared fit. No pooled candidate passed the inner selection gate; additional macro improvement was 0.0000%, and V1/V2 remain unchanged. The Model lab now records this result. Read `docs/accuracy_v4_results.md` before further tuning; preserve the frozen evidence and obtain new measured outcomes for independent accuracy evaluation. No cloud resources were created.


## Accuracy and judging update — 3 October 2026

Official and supplied expectations are mapped in `docs/judging_criteria_evidence.md`; no finale numeric weights were found. Prioritize accurate predictions, feasible counted hardware, both impulse types, numeric compliance and credible measured feedback. Public event dates are 10–11 October; team readiness remains 10 October.

V5 added 1.0921% macro Train development improvement versus a historical V2 refit (0.2363% beyond a matched Ridge control), below its 5% gate. It was not promoted; V1/V2 and old model evidence remain frozen. See `docs/accuracy_v5_results.md`.

Capture-resolution review now blocks three demonstrated sparse-waveform false passes from calibration and scoring, preserving raw samples and provisional extracted values. The measured-shot review adds false PASS/FAIL counts, denominators, worst-shot errors, saved-rule snapshots and separate envelope containment. See `docs/capture_resolution_review.md` and `docs/measured_decision_review.md`. No new laboratory accuracy result exists. Website previews were omitted at the user's request for this update; automated checks are recorded separately.
