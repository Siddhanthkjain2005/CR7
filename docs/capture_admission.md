# Capture admission — branch `codex/waveform-diagnostics`

An external validation of `codex/effective-parameter-calibration` found three calibration defects. This file describes how they were reproduced and fixed. A fourth issue, out-of-rating as-fired settings, is fixed alongside them.

## What was wrong

| # | Defect reported by the external validation | Root cause |
|---|---|---|
| 1 | A constructed 0.7 µs main front with a separate precursor was reported as about 0.9 µs, marked **NOMINAL PASS** and admitted to calibration. | The analyzer takes the *first* 30 % and 90 % crossings before the crest. A precursor above 30 % moves the 30 % crossing earlier. Nothing checked that both crossings lie on one connected rise. |
| 2 | Uploading the opposite of the expected polarity was flagged, yet the calibration API still accepted the capture. | The mismatch was written only into the upload's copy of the quality record. `calibrate`, the parameter fit, the evaluation and the laboratory summary each recomputed the acquisition review without the declared polarity. |
| 3 | A shot fired at 97 % of the recommended charge matched its physics prediction, yet a −42.75 kV correction was applied to the original setup. | The one-shot correction was always measured against the prediction for the *recommended* settings. The 3 % lower charge (3 % of 1425 kV = 42.75 kV) was mistaken for model bias. |
| 4 | Out-of-rating as-fired settings were not flagged. | The upload re-simulated the as-fired settings without checking them against the generator ratings. |

Each defect is reproduced by `tests/test_capture_admission.py`. On the previous commit (`2de2d4c`):

- the precursor, shelf and polarity cases all showed `NOMINAL PASS`;
- the evaluation accepted a capture with mismatched polarity;
- the as-fired case had no model-error field.

## What changed

**One shared admission check.** `backend/app/capture_admission.py` decides whether a saved capture may be used for a *one-shot correction*, a *parameter fit* or an *independent evaluation*. The following all call it:

- `POST /api/trials/{id}/calibrate`
- `POST /api/parameter-calibrations`
- `POST /api/evaluations` (and its re-verification for evidence levels)
- the laboratory summary

A disabled button is not the safeguard: direct API calls get the same answer.

**Acquisition review v4** (`backend/app/trial_quality.py`) adds the following checks. None of them resamples, smooths or rewrites anything.

| Check | Code | Can a reviewer accept it? |
|---|---|---|
| The recording returns below 30 % of crest after the first 30 % crossing and before the crest. The idea comes from an uncommitted v4 change in the team's checkout; its tolerance is now 4× the pre-trigger noise, estimated from samples before 10 % of crest. | `disconnected_rising_limb` | No |
| The rise rate between first crossings of 20, 25 … 90 % stalls to less than a third of the rate both before and after it (a shelf, precursor or front oscillation). | `two_stage_rise` | Yes, with a recorded reason |
| After first reaching 90 % the signal falls below 90 % again before the crest. | `dip_after_90_percent` | Yes, with a recorded reason |
| The declared expected polarity does not match the recording. | `polarity_mismatch` | No |

For the precursor case, the front of the connected main limb (0.70 µs) is reported **for review only**. The analyzer's 0.894 µs stays the stored value and is never substituted. The provisional status becomes **REVIEW REQUIRED**.

**As-fired settings are not model bias.** When the settings actually fired differ from the recommendation, the upload records three separate quantities:

| Quantity | Meaning |
|---|---|
| `bias` (kept for history) | Measured minus the saved prediction for the recommended settings |
| `model_residual` | Measured minus the circuit prediction at the as-fired settings. This is the model error. |
| `configuration_difference` | The same circuit at the as-fired settings minus the same circuit at the recommended settings |

In that case no one-shot offset is formed, and `calibrate` refuses with an explanation. The parameter fit is the right tool, because it re-simulates the as-fired settings. In the external validation's case the model residual is about zero and the fit changes nothing. Independent evaluation also refuses shots fired at other settings, because it scores the prediction saved for the recommended settings.

**Out-of-rating as-fired settings** are flagged using the same ratings as the optimizer:

- stage count outside the profile,
- charge above the stage rating,
- stage energy or total energy above the rating.

A shot that was fired cannot be un-fired, so the upload is kept. The flags must be accepted by a recorded review before the shot is used. A stage count above the generator's stage count is still rejected at upload.

**Review decisions are append-only.** `POST /api/trials/{id}/reviews` stores a `capture_review` record with:

- the decision: `accept_flags`, `exclude` or `reinstate`;
- the codes being accepted;
- the reviewer and the reason;
- the file checksum and the quality version.

The capture, its samples and its metrics are never rewritten. `GET /api/trials/{id}/admission` shows the live admission for each use and the review history. Blocking issues cannot be accepted:

- polarity mismatch,
- disconnected rise,
- changed file bytes,
- validation purpose for correction or fitting,
- calibration purpose for evaluation,
- image-derived samples.

## Interface

**Compare measurement** shows the following:

- the model error at the as-fired settings next to the difference from the saved prediction;
- a note explaining that a settings change is a configuration difference;
- a "Can this capture be used?" panel for the three uses, with a form for recording reviews.

The one-shot offset button reads "Fired at other settings: use the parameter fit" when that applies.

## Not changed

- Metric definitions, compliance limits, the circuit solver and saved runs are unchanged.
- Historical trial records are not edited. Admission is recomputed from their stored samples and declarations. A record from before this change that lacks the `instrument` block is treated as having polarity `auto`.
