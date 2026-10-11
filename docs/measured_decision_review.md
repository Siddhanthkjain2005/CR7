# Measured waveform decisions and worst-case error

Updated 3 October 2026. The existing saved-prediction review now reports engineering decisions alongside regression error. It uses distinct operator-labeled laboratory captures whose predictions were saved before upload, excludes calibration ancestors and duplicate waveforms, and never fits the evaluation outcomes.

## What changed

Each capture is first checked for sufficient acquired rising, crest and falling-half-value resolution. Unresolved captures cannot calibrate or enter the review, even when an older saved quality report marked them usable. The original samples, extracted values and nominal arithmetic remain available; their status is **REVIEW REQUIRED** with provisional measurement evidence. The three demonstrated sparse-capture false passes are documented in `capture_resolution_review.md`.

For an eligible capture, the evaluator compares the measured front/peak, tail and crest against the rule snapshot saved with its original run. It evaluates physics, the original model without the local bias, and the actual saved prediction against those same limits. The following counts are reported separately for each model:

| Count | Predicted waveform | Extracted measured waveform |
|---|---|---|
| True PASS | All three values within limits | All three within limits |
| False PASS | All three within limits | At least one outside |
| False FAIL | At least one outside | All three within limits |
| True FAIL | At least one outside | At least one outside |

Every rate includes its numerator and denominator. False PASS among measured failures and measured failure among predicted passes answer different questions, so both are retained. If a denominator is zero, the rate is null and displayed as not estimable. If all selected measurements share the same outcome, the review explicitly says performance on the missing class has not been established. No all-pass selection can silently become a claim of zero false-pass risk.

Worst absolute and tolerance-normalized errors are recorded for each output. The largest normalized miss includes its capture ID, output name and physical-unit error. Normalization uses half the saved limit range, including the original requested crest and crest tolerance. No current global rule can silently change a saved run's score.

## Preserved context and uncertainty

Grouping retains the impulse, generator/profile version, layout, solver/physics version, model version/mode and a hash of the complete saved challenge rules. Two rule snapshots with the same nominal version but different limits are separated. Missing or invalid rule snapshots block the review.

Each evidence row contains the original settings, counted networks, measured values, three predictions, nominal decisions, rule snapshot/hash, ML support state and calibration ancestry. The ML support field now reads the recorded `state` key correctly; older `status` records remain compatible.

The saved prediction envelope is reported independently as contained, overlapping, outside or unavailable. A malformed interval, reversed bounds or an interval that excludes its saved prediction is unavailable. The review also counts measured failures among contained envelopes. It does not claim a new coverage guarantee or treat unavailable intervals as passes. Nominal waveform decisions do not validate mounting, stock, pulse ratings, instrument uncertainty or overall laboratory compliance.

## Interpretation

These are descriptive results on a small, operator-selected sample. Capture origin is operator-labeled and acquisition checks are heuristics. Instrument bandwidth, calibration and authenticity are not certified. Near-boundary decisions can still depend on measurement uncertainty. No confidence interval, generalization estimate, laboratory success probability or automatic promotion is inferred.

This capability reports false passes, false failures and worst errors, supporting the organizer's emphasis on numeric compliance. It is not a newly discovered weighted judging criterion. Current official and supplied expectations are audited in `judging_criteria_evidence.md`.

## Verification and use

Use **Trial calibrator → Verify accuracy on new shots** with at least three eligible captures. Review each group and download its evidence JSON. Save failed shots as well as passes, and keep evaluation shots out of all correction-development lineages. Old saved evaluation records remain unchanged.

Tests use isolated synthetic fixtures only. They cover all four decision outcomes for Lightning and Switching, exact boundaries, zero denominators, captured-rule separation, correct normalization, worst-shot identity, interval availability, current quality rechecks of legacy captures and three sparse nominal passes blocked from calibration and scoring. These fixtures do not populate the live laboratory review.

Files: `backend/app/decision_metrics.py`, `backend/app/trial_evaluation.py`, `backend/app/trial_quality.py`, `tests/test_decision_metrics.py`, `tests/test_trial_evaluation.py`, `tests/test_capture_resolution.py`.
