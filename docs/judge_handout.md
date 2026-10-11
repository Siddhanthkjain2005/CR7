# ImpulseTwin AI

**From a requested impulse to an inspectable setup and a traceable next trial.**

Impulse testing requires physical changes to stages and front/tail resistors. ImpulseTwin AI helps an engineer choose a stronger starting setup by combining physics, residual learning and stock-aware search. It returns a concrete component plan with uncertainty and alternatives, then analyzes a trial waveform and records a correction restricted to the tested configuration.

## Four decisions the workflow supports

| Engineering question | What the local proof of concept provides |
|---|---|
| Can we construct this setting from the declared stock? | Bounded series/parallel/mixed search; exact component counts; stage-voltage and energy filters. |
| Does the learned correction apply here? | Generator/profile separation and explicit training-support gating; physics fallback when support is insufficient. |
| Do the physical models agree? | Independent lumped RLC waveform and numeric metric extraction beside the workbook-based prediction. |
| What did the trial teach us? | Raw waveform provenance, unit mapping, numerical crest/front/tail extraction and a configuration-scoped correction. |

## Frozen synthetic benchmark

The supplied split is preserved: 1,400 Train, 300 Validation and 300 Hidden Test rows. Fit/calibration separation precedes model selection; the selected configuration was frozen before the saved one-time Hidden Test evaluation.

| Hidden Test output | Physics RMSE | Selected RMSE | Reduction |
|---|---:|---:|---:|
| Lightning front (µs) | 0.01029 | 0.007379 | 28.3% |
| Lightning tail (µs) | 0.7317 | 0.6368 | 13.0% |
| Lightning crest (kV) | 11.60 | 5.490 | 52.7% |
| Switching peak (µs) | 2.171 | 1.749 | 19.4% |
| Switching tail (µs) | 32.50 | 26.78 | 17.6% |
| Switching crest (kV) | 8.234 | 4.121 | 50.0% |

**All six improve over physics; five improve over exact workbook kNN.** Switching crest is 4.9% worse than kNN. These results describe the supplied synthetic distribution, not laboratory accuracy or shot savings.

## Evidence and limits

The workbook's displayed example and all 1,400 cached neighbor distances/weights are reproduced. Its static validation-table discrepancy remains documented. The PDF, workbook and incomplete briefing profiles are kept separate. All 1,000 supplied Switching front-resistance settings exceed the workbook stock's 5,740 Ω/stage all-series maximum.

Stock arithmetic and declared voltage/energy bounds are checked. Mounting, pulse ratings and permitted physical connections need laboratory confirmation. Uncertainty is marginal under synthetic assumptions; circuit disagreement and OOD remain visible. The search is bounded and does not prove a global optimum. Challenge-rule checks are not complete IEC certification.

## Next validation

Confirm CPRI inventory and ratings; collect paired reduced-voltage waveforms across layouts; freeze a field protocol and compare first-shot compliance, total trial shots and physical component changes on held-out cases. Generated demonstrations stay separate from measured trials.

**Local app:** `http://127.0.0.1:8000` after starting the prepared package. Inference requires no external model service. Cloud deployment is deferred.

**Review trail:** `docs/source_reconciliation.md` · `docs/data_audit.md` · `docs/accuracy_report.md` · `artifacts/models/hidden_test_evaluation.json`.
