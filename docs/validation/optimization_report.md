# ImpulseTwin AI — final optimization and engineering hardening

Completed 6 October 2026 on `feat/engineering-hardening`, based on current main `047841f587c4b00bc8d018d5174961d3356eebbf`. The existing product is preserved; the changes address demonstrated numerical, constraint, inference and UI weaknesses. No deployment, model training, Hidden Test tuning or laboratory validation claim occurred. Machine-readable evidence: [optimization_report.json](../../artifacts/optimization_report.json).

## Baseline

Current main collected 237 tests. The first Windows run terminated with a native pandas/access violation rather than a completed assertion summary; [failure log](../../artifacts/hardening/baseline/backend_tests_native_failure.txt) is retained. An unchanged isolated checkout with native threads bounded to 1 passed **237/237** in 408.22 s, with 2 pre-existing warnings ([JUnit](../../artifacts/hardening/baseline/backend-tests-isolated.xml)). Frontend typecheck/build passed. Total-suite elapsed time is not used as an optimization speed claim.

The initial before-change profile is retained at [baseline/runtime.json](../../artifacts/hardening/baseline/runtime.json). For a comparable environment, the immutable main checkout was profiled again with the same native-thread settings as the new version: [controlled baseline](../../artifacts/hardening/baseline_controlled/runtime.json), [after](../../artifacts/hardening/after/runtime.json). Three sequential repetitions per request include a separately recorded first call; reported warm median uses repetitions 2 and 3. cProfile is a separate fourth call, and cumulative subroutine times overlap. Fixed requests, sources and 45 frozen hashes were recorded before changes.

## Changes made and why

| Area | Demonstrated weakness and retained correction |
|---|---|
| Circuit numerics | RC eigenvalues could lose the slow decay; an absolute tiny-L cutoff could remove significant ringing. Compute stable analytic RC rates/crest, check the dimensionless inductance ratio, and refine roots with bracket-scaled tolerance. Return an explicit error when continuous crest/decay is unresolved. |
| Candidate eligibility | The ideal source-voltage estimate excluded valid underdamped load crests. Solve actual circuit charge before hardware rejection; retain the exact early guard for reference mode and all actual voltage/energy limits. |
| Circuit runtime | A fixed linear circuit was solved twice just to normalize crest. Reuse its invariant times/eigenvalues/normalized-energy diagnostics and scale charge/crest; final plotted waveform is recomputed at actual charge. |
| Inference runtime | Per-row pandas slicing and repeated scalar workbook calculations dominated inference. Use one ordered base array, an exact batch-local calculator cache and vectorized frozen support comparisons. |
| Hardware/API | Physical lower bounds were over-attributed to the PDF, and direct simulation could ignore an independently stated energy limit. Mark 50 kV/two-stage floors as application assumptions and enforce both stated energy ratings. |
| UI | Defaults and labels obscured the primary physical path. Fresh UI/Judge opens CPRI/circuit/physics, waits for explicit stock, identifies residual-off/single-model/base-C scope and preserves operator numeric inputs. Saved trial provenance/admission uses actual backend evidence. Browser QA also found a pre-existing locale hydration mismatch: en-IN build hints differed from en-US client hints. Using the existing deterministic formatter, rebuilding and checking a fresh origin removed the console error ([React diagnostic](https://react.dev/errors/418)). Typography, spacing, focus and mobile navigation are cleaner; 11 destinations and 7 Judge steps remain. |
| Reproducibility | Record native-thread settings and retain failed attempts. Dev/verifier/audit scripts default native threads to 1, respect explicit caller overrides and preserve earlier evidence outputs. Passing reruns do not prove the native crash's root cause. |

Every retained change has focused regression evidence followed by the full suite and numerical/search comparison. No model artifacts, feature order/scaling, interval widths, OOD thresholds, optimization weights, network catalogs or benchmark protocol were changed.

## Physics and units

The nodal topology is unchanged: generator capacitor with tail shunt, front-R/L series branch and load capacitor. `Cg=Cstage×10^-6/n`, `Cl=(load+divider+stray+optional base)×10^-12`, `Rf=n×Rf_stage`, `Rt=n×Rt_stage`, `L=L_uH×10^-6`. Initial erected voltage is `n×charge_kV×1000×efficiency`, with discharged load and zero initial current. Energy derivative is `-Vg²/Rt-Rf I²`, so passive inductive transfer may exceed initial source **voltage** without creating **energy**. Details and equations: [assumptions](../../docs/assumptions.md).

For zero L, decay sum is `(1/Rt+1/Rf)/Cg+1/(Rf Cl)`, product is `1/(Rt Rf Cg Cl)`, the fast rate is `(sum+sqrt(sum²-4product))/2` and the slow rate is `product/fast`. The single peak is `log(fast/slow)/(fast-slow)`. These stabilize the same equations. Tiny positive L uses RC only under the existing small-L cutoff when `L/(Rf² Cseries)≤10^-8`; otherwise full RLC is retained. Root tolerance is capped at 10^-15 s and scales with bracket width. Solver **v2.1** distinguishes this numerical policy; earlier calibration scopes do not transfer. The damping ratio is explicitly a load-branch approximation and null at zero L.

CPRI 0.125 µF at 200 kV gives 2.5 kJ/stage and 30 kJ across 12 stages, matching source ratings. Charging-bank energy uses pre-loss charge; the initial circuit energy is smaller by efficiency². µs/s, µH/H, µF/F, pF/F, kV/V and J/kJ scaling is protected by analytic RC, energy and dimensionally similar circuit tests. 545 pF is counted once only when included.

The matched CPRI request remains **11 stages, 181.902790 kV/stage, 30 Ω/520 Ω, 1.186781/53.743527 µs, 1425 kV, 22.748430 kJ**. Residual trust is 0; nominal model compliance and 144/144 separate-seed/corner checks pass. Efficiency and hardware tolerances are held fixed in those checks. This is finite model evidence, not a probability or laboratory certification. Deliberately poor LI 465 Ω front and SI 30 Ω front still fail timing.

The 1,128-case generated numerical grid covers low/high L, C, R and stiff ratios. Previously 840/840 ordinary-extreme and 285/288 stiff cases returned metrics; now 805/840 and 271/288 do. The additional 49 cases explicitly reject unresolved continuous crests rather than returning a plotting-grid crest; 3 lost-decay failures remain diagnostic. All resolved cases have finite positive metrics and passive-energy ratio≤1+10^-8. Some grid inputs exceed practical/UI ranges. [Before](../../artifacts/hardening/physics_stability_before.json), [after](../../artifacts/hardening/physics_stability_after.json).

## Optimizer and ML

A controlled workbook-capacitance development case with 8 stages, 30 Ω front/30 Ω tail and 80 µH was rejected because the ideal estimate required 217.2256 kV/stage. The actual passive circuit needs 191.419731 kV/stage for 1425 kV, with 0.912652/51.125687 µs and valid energy. It is now retained. Increasing the requested crest to 1490 kV or lowering either energy rating still rejects it. This case is an explicit synthetic development inventory, separate from CPRI stock.

Linear normalization matches independent full solves for LI 100/1300/1425 kV and SI 100/1100 kV. Scoring still orders nominal compliance first, uncertainty/scenario containment second and weighted objective third. Weights remain 0.30 front, 0.30 tail, 0.40 crest, 0.003 components, 0.08 OOD, 0.03 stage utilization and 0.03 uncertainty. Shortlists and tie handling are unchanged.

**4,096 complete inference dictionaries match original code exactly**, across LI/SI × workbook/CPRI × hybrid/physics. Corrections remain zero in all unsupported/physics groups. Support comparisons retain asymmetric `rtol=10^-10,atol=10^-8`; the scalar workbook calculator's rounding and all-input batch-local cache are tested. Homogeneous impulse batches remain the existing inference contract. [Inference evidence](../../artifacts/hardening/inference_equivalence.json).

## Performance before/after

Seconds per complete optimization, including ranking, waveform work and fixed-settings verification:

| Fixed request | Before warm median(s) | After warm median(s) | Runtime change |
|---|---:|---:|---:|
| default_lightning | 7.140 | 4.715 | -34.0% |
| default_switching | 6.350 | 5.627 | -11.4% |
| cpri_matched_1425 | 4.024 | 4.195 | +4.3% |

CPRI evaluates 11 stage/network pairs instead of 4 to avoid premature exclusions; 3 remain hardware-feasible and all ranked settings are unchanged. Its small+4.3% warm-median change overlaps observed repetition ranges and is accepted for the corrected search eligibility. No CPRI speedup is claimed. Workbook winners, ranking, nominal status and fixed-verification counts also remain unchanged within 1e-8 metric tolerance.

The controlled paired 512-row inference microbench uses 9 warmed repetitions:

| Impulse | Support check before→after | Full inference before→after |
|---|---:|---:|
| Lightning | 187.50 → 5.00 ms | 645.44 → 85.19 ms |
| Switching | 181.52 → 4.65 ms | 843.53 → 220.47 ms |

These microbench speedups are not end-to-end claims. After profiles attribute LI/SI cumulative time respectively to network selection 1.676/1.777 s, circuit 2.953/3.813 s, inference 1.152/1.395 s, robustness 0.626/0.698 s and fixed verification 3.480/4.545 s. Metric reconstruction is 0.189/0.243 s; those overlapping cProfile values carry overhead. Serialization after is 29.86/37.55 ms and HTML report creation 5.49/6.62 ms. Full profiles and before/after serialization/report timings are retained in the runtime records. No broad refactor or persistent cache was justified.

## Search quality and regression

All 4 declared small-space exhaustive comparisons preserve top 1 agreement, top 3 containment and rank 1 with zero objective/waveform/component/margin gap before and after. **All four best candidates fail nominal waveform limits**; these fixtures establish bounded/exhaustive ranking agreement for their reference-solver spaces, not physical success or global circuit optimality. The overshoot and matched CPRI regressions cover separate circuit cases. [Current benchmark summary](../../artifacts/search_quality/summary.json).

Final backend: **263/263 PASS**, 0 failures/errors, 4 warnings (2 existing warnings and 2 Windows pytest-cache permission warnings). All 237 old tests remain; 26 targeted tests add 11 physics, 11 optimizer and 4 engineering/API cases. Existing negative-polarity, delayed-Switching, sparse/clipped acquisition, calibration scoping, frozen V1, inventory and agreement checks pass. Frontend typecheck/build, local static assets, 45 protected hashes and fresh-database external-network-denied smoke pass. The release verifier is **PARTIAL** only because other platforms/physically disconnected-browser rehearsal remain untested. [Release JSON](../../artifacts/release_readiness.json), [JUnit](../../artifacts/release_checks/backend-tests.xml), [browser review](../../artifacts/hardening/browser_review.json).

Two additional **predeclared CPRI circuit development cases** (Lightning and Switching) also retain top-1/top-3 agreement and zero gap before/after; both bounded and exhaustive winners nominally pass. Each evaluates 45 bounded versus 108 exhaustive candidates. LI remains 11 stages, 181.902790 kV/stage and 30/520 Ω; SI remains 11 stages, 141.116226 kV/stage and 4165/22000 Ω. Single-run bounded times were 6.230→4.891 s and 6.758→5.005 s respectively; these are not repeated warm-median claims. Explicit hypothetical stock, unchanged baseline/current hashes and both results are retained in [circuit development comparison](../../artifacts/hardening/circuit_search_comparison.json). These two cases were added for primary-path coverage, not held-out evaluation or tuning, and share the same physics/charging/scorer. They cannot establish physical accuracy or global optimality.

## Known assumptions and weaknesses

- CPRI source values are primary physical references per the organizer clarification supplied by the user; this pass is not independent machine-nameplate verification.
- Actual resistor quantities, pulse ratings, voltage grading, permitted mounting/connections and physical operating minima remain unknown; demo counts are operator assumptions.
- 650/250/55 pF load/divider/stray, 12 uH and 0.83 efficiency are editable example inputs, not measurements; 545 pF additional shunt interpretation must avoid double-counting.
- One lumped capacitor/tail-shunt/front-RL/load topology; auxiliary charging/potential/discharge resistors and sphere gaps are preserved metadata but omitted from pulse equations.
- Efficiency is applied once as voltage loss; charging rating energy is before loss, circuit initial energy is smaller by efficiency squared.
- Waveform metric definitions and tolerances follow the challenge/workbook provenance; no universal standards-conformance claim is created.
- No measured laboratory accuracy is established. Measurements are not a prerequisite for this challenge; generated tests do not replace independent physical evaluation.
- Bounded nearest-five network search is not globally optimal. The four unchanged exhaustive fixtures are reference-solver spaces and all winners fail nominal waveform limits; they demonstrate ranking agreement only.
- CPRI residual ML remains disabled. Synthetic interval widths and unsupported-profile sensitivity envelopes have no calibrated CPRI/laboratory coverage; finite scenario fractions are not success probabilities.
- Extreme stiff circuits may explicitly fail continuous crest/decay resolution. The stress grid includes values outside practical/accepted UI ranges and is not a reliability population.
- The separately mentioned CPRI pseudo-laboratory pack was not present in main or the attachment. Existing generated acquisition fixtures and new controlled cases were used instead.
- macOS/Linux, a second physical laptop and physically disconnected browser rehearsal were not newly executed; Python transitive dependencies are not fully locked. The verifier carries forward its historical clean-install record; no new dependency installation was performed in this hardening.
- The initial Windows pandas/native access violation is retained; bounded-thread isolated/full reruns passed, but this does not prove its root cause or universal prevention.
- Historical release ZIP/QA/experiment records remain historical. Use this branch source and regenerated static export for the current build; no new distributable ZIP or deployment.

## Attempts rejected or not pursued

- **Deduplicate selected per-output model predictions**: Frozen V1 already selects distinct estimators for all three outputs in each impulse type; no redundant prediction to remove. Not implemented.
- **Tune weights, enlarge production shortlist, add new network logic**: Four declared comparisons showed zero gaps; no evidence justified more complexity. Existing weights, tie/rank priority and catalogs retained.
- **Change CPRI topology/equations to chase benchmark timing or force workbook ML transfer**: Dimensional/passive-energy audit and matched regression support existing equations; transfer evidence is absent. Not attempted.
- **Accept plotting-grid crest after continuous root failure**: Removed existing fallback; unresolved numerical claims are reported as failures.
- **Add persistent cross-request cache, train V6 or tune exposed Hidden Test**: Unnecessary state/evaluation risks and outside authorized scientific scope. No fitting, model promotion or Hidden Test tuning.

## Recommended hackathon configuration

Use **CPRI physical profile, circuit solver, physics-only**, with explicit operator parasitics/efficiency/layout and actual counted inventory. For a reproducible generated walkthrough, the matched Lightning preset uses 1425 kV, 650/250/55 pF, optional 545 pF included, 12 µH, 0.83 and clearly declared assumed stock. Present its nominal pass and finite scenarios with their scope; do not label a single primary circuit as independent model agreement.

Keep workbook/reference/frozen V1 as a separate synthetic benchmarking view under its existing support gate. Use the existing 7 Judge steps and identify generated feedback as generated. Obtain missing stock/pulse/mounting/minimum-limit information before physical setup. Future independent captures can establish laboratory performance; they are not required to solve the current challenge. Run locally with `python scripts/dev.py`; no deployment occurred.

Reproduce with `python scripts/profile_pipeline.py --label rerun`, `python scripts/audit_circuit_stability.py --root . --output artifacts/hardening/circuit-rerun.json`, `python -m scripts.benchmark_search_quality` and `python scripts/verify_release.py`. Extract the baseline registry from the stated main commit and pass it to `scripts/audit_inference_equivalence.py --baseline-source <path> --output <new-record>`. Use `--source-root <immutable-checkout>` for paired pipeline baselines; do not overwrite historical evidence.
