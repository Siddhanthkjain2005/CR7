# Waveform Diagnostics

**Test setup → Waveform Diagnostics** (`/diagnostics/`), or **Diagnose this waveform** on a saved result.

The page compares a recorded waveform with the circuit prediction at the settings actually fired. It then looks for physically meaningful explanations of any difference.

It does not:

- change a saved run, a model, a calibration or a stored capture;
- create a correction;
- claim that a component is faulty.

Real CPRI accuracy is unknown until real recordings with known causes are available.

## Workflow

| Step | What happens | Record |
|---|---|---|
| 1 Reference | Choose a saved run and candidate, or generate a new reference with the existing optimizer. A versioned snapshot freezes the profile, impulse type, settings, load/divider/stray capacitance, 545 pF choice, inductance, loss factor and its meaning, topology, physics version, rules and any fitted generator parameters. The three open questions stay visible: loss factor, 545 pF, resistor connection. Enter the settings actually fired; they are re-solved with the same solver. Mark any value as uncertain to let the diagnosis test it. | `diagnostic_reference` (new revision per change) |
| 2 Upload | Raw CSV (preferred) or a PNG, JPEG or WebP image. The type is checked from the bytes, never from the filename. The original is stored under its SHA-256, never under the uploaded filename. You also declare the origin (physical experiment, software simulation, demonstration or unknown), the capture time, instrument, session and shot. | `diagnostic_upload` |
| 3 Calibrate and review | For images: straighten (with a suggested angle) and crop, or correct perspective from the four plot corners. Then set the plot area, two anchors per axis or oscilloscope divisions, units, axis type and voltage side (high voltage, or the instrument signal with a divider ratio and its source). Finally pick the trace and run the extraction. The overlay of the extracted samples on the image is shown before you compare. For CSVs: the unit and divider conversion, and the quality flags. | `diagnostic_digitization` |
| 4 Compare | Separately labelled curves: illustrative target shape, circuit prediction (at the as-fired settings when recorded), the uploaded waveform, and after diagnosis the fitted explanations. The plots share a cursor and zoom, curves can be shown or hidden, and a residual plot sits below. A metric table shows the crest, front or time to peak, and tail with a status for each: Compared / Approximate / Requires review / Insufficient capture. Also shown: whole-waveform mismatch, ringing and undershoot, and the pre-onset baseline. | `diagnostic_comparison` |
| 5 Investigate | Physics-based inverse analysis in a background job, with progress and a Cancel button. | `diagnostic_investigation` |
| 6 Findings and export | For each explanation: plain explanation, component group, supporting and contradicting evidence, nominal and fitted effective value, fit improvement, ambiguity, how a qualified person can check it, and the simulated effect at the recommended setting if confirmed. Also available: a self-contained HTML report, a JSON export, and "Explore a corrected configuration". | — |

Every step is saved. Re-opening the page, or the `?session=` link, restores the diagnosis. Changing an earlier input marks the comparison and investigation **out of date** instead of mixing versions; each record names the records it was computed from.

## Digitization (local, no external AI)

- **Libraries.** Pillow, numpy and scipy only. OCR uses a local Tesseract binary when one is installed, and only suggests tick values; you confirm every anchor. Without OCR, values are entered by hand.
- **Image transforms.** Rotation, crop and perspective are recorded steps, each with a matrix from the working image back to the original. The extracted samples can therefore always be drawn on the photograph they came from.
- **Trace extraction.** A colour match (CIE ΔE) at the clicked point, then continuity-aware column tracking. Straight same-colour lines spanning nearly the whole plot are treated as grid lines; other objects in the trace colour (text, legend, other curves) are counted and ignored. Each steep column becomes one sample at its centre, carrying half its vertical span as uncertainty, so a near-vertical front is never given false time detail. Gaps stay gaps. Manual points stay marked as manual. Nothing is smoothed, and no ideal impulse is fitted into the samples.
- **Flags.** The following are flagged:
  - clipping at the plot edge or a flat recorder top;
  - more than one curve in the same colour;
  - a trace that cannot be followed to the edge;
  - thick traces;
  - low resolution;
  - a front narrower than max(4 px, 2 × thickness), reported as unresolved rather than as a value;
  - a missing rising or falling limb;
  - ringing;
  - a precursor or disconnected rise, using the same check as the capture admission;
  - crossings inside a missing portion;
  - unevenly spaced grid lines, which may mean a log axis;
  - a time or voltage scale implausible against the prediction, which suggests a unit mistake.
- **Uncertainty.** Per sample, the uncertainty combines pixel size, trace thickness and anchor placement. The **digitization spread** is the 5–95 % range of each metric when the anchors and samples are moved within that uncertainty. It is not a probability that the digitization is right, and no confidence percentage is invented.
- **Calibration safeguards.** Logarithmic axes are refused with an explanation. A divider ratio on an axis that already shows high voltage is refused, because it would count the divider twice.
- **Quantitative diagnosis is disabled** when trace integrity or calibration information is missing:
  - polarity mismatch,
  - unresolved crest,
  - clipping,
  - same-colour curves,
  - implausible units.

  The visual comparison stays available.
- **Image-derived samples** are labelled "Digitized from image — approximate". They never enter calibration, parameter fitting or laboratory-accuracy workflows; the shared capture admission blocks the class `image_digitized`. A declared physical-experiment origin is recorded as a declaration only: a photo does not verify laboratory provenance.

## Comparison rules

- Metrics use the existing definitions:
  - Lightning: 1.67 × (t90 − t30) and the virtual origin;
  - Switching: time to peak from the entered onset.
- They are re-extracted from exactly the samples that are plotted.
- No tail value is given without a falling limb, and nothing is extrapolated.
- Any time alignment (none, a manual shift, or matching the 30 % crossings) is recorded and shown. Nothing is stretched.
- The normalized-shape view is optional and labelled as hiding crest mismatch.
- **Residual normalization.** Residuals are divided by the per-sample uncertainty. For images that is pixel size and thickness; anchor placement moves all samples together and is tested as a measurement hypothesis instead. For CSVs it is a stated tolerance: the larger of the pre-onset noise and 1 % of the predicted crest.
- **Region-balanced weighting.** The rise, the crest region and the tail each carry one third of the weight, so a long densely sampled tail cannot dominate the rise. Samples before the onset are reported but not fitted.

## Inverse analysis (`backend/app/diagnostics/inverse.py`)

The existing lumped circuit is re-solved through `circuit.response()`. It shares its modal solution with `simulate()`; the refactor was checked bitwise identical on 3,000 random circuits. Fits use `scipy.optimize.least_squares`, bounded and scaled, from several starts, and every distinct good solution is kept.

| Category | Explanations (free quantities) |
|---|---|
| Hardware hypotheses | front network (× nominal total), tail network, effective load-side capacitance (total only), circuit inductance; combinations front + tail, capacitance + inductance, front + capacitance |
| Configuration differences | charge per stage, number of stages. Tested only when the as-fired value was not recorded or was declared uncertain. |
| Measurement issues | gain (divider ratio), time origin, baseline; combination gain + time origin |
| Model limitations | loss-factor convention; combinations with the front or tail network. "Missing physics" is reported from the structure of what remains after the best fit. |

**Ranking and verdict.**

- **Ranking score.** Explanations are ranked by `mismatch² + 2 × free parameters / 90`.
- **Consistent.** An explanation counts as consistent when its region-balanced mismatch is ≤ 1.5 and no region exceeds 2.5.
- **Nested combinations.** A combination that only adds an unneeded quantity to a simpler consistent explanation is marked "Not needed".
- **Indistinguishable explanations.** Explanations whose fitted curves coincide are reported as rivals. Charge, loss factor and gain change only the amplitude, so they always compete.
- **Identifiability.** For each fit the analysis reports parameters at a bound, a local uncertainty, the correlation (trade-off), a ±10 % profile and multiple good fits.

The verdict labels are:

- No change needed
- Possible cause
- Several explanations fit
- Cannot explain with the current model: "The current equivalent-circuit model cannot adequately explain this recording."

A finding can also be marked **Additional measurement needed**, and the verdict states **Requires review** when the recording itself carries review flags.

Fit scores rank explanations of one recording; they are not fault probabilities. Capacitance is identified only as an effective total, and the resistor networks only as a whole, never as one stage resistor. Without as-fired settings the diagnosis is marked **limited**.

**Explore a corrected configuration.** The existing optimizer runs with the fitted effective values as a hypothetical generator, with its stock and ratings unchanged. The new effective-parameter keys `front_scale` and `extra_l_uh` default to no change. The result is saved as a separate run labelled hypothetical. A fitted continuous resistance is an effective value, not a part to install, and nothing is applied anywhere automatically.

## Evaluation (protocol committed before the fixtures ran)

Run `python -m scripts.evaluate_waveform_diagnostics`. The protocol, results, disclosed revisions and manual overlay checks are in `artifacts/waveform_diagnostics/v1`. Every fixture runs through the real API in an isolated database.

The fixtures are generated:

- CSVs from the lumped circuit with 0.3 % noise;
- off-model features it cannot produce;
- an independent ODE of a different topology;
- matplotlib plots digitized back.

| Gate | Result |
|---|---|
| G1 No-change recordings → "No change needed" | **Pass**, 3/3 (CPRI LI and SI, workbook LI) |
| G2 Single in-model change identified, fitted value within 5 % | **Pass**, 11/11. Front, tail, capacitance and inductance on CPRI LI; front and tail on CPRI SI and workbook LI. Fitted values within 0.5 % of the truth. |
| G3 Off-model recordings never confidently blamed on one hardware part | **Fail**, 1 of 4. A slow second tail component of 12 % of crest was absorbed by an effective tail resistance of 1.37×, within the 1 % comparison tolerance, and reported as "Possible cause: tail network". The 4 MHz oscillation, oscillation plus slow tail, and the 35 % precursor were not attributed. |
| G4 Amplitude-only differences keep competing explanations | **Pass**: gain vs loss factor, plus charge when as-fired is not recorded |
| G5 Image round trips (clean plot, perspective JPEG photo, oscilloscope divisions) | **Pass**, 9/9 within limits: crest within 0.05 %, tail within 0.15 %, front within 1 %. The spread contains the truth in 8/9. |
| G6 Integrity cases (clipping, same-colour curves, negative polarity, unit mistake, clipped display) | **Pass**: diagnosis disabled or metrics marked |
| G7 Missing falling limb (CSV and image) | **Pass**: the tail is never reported |
| G8 Shot at 95 % charge | **Pass**. With as-fired recorded: "No change needed". Without it: limited, with charge among the explanations. |

**Other results, reported without a gate:**

- Workbook LI front ×0.8 gave "Several explanations fit" (front network vs capacitance + inductance).
- 1.5 % noise with front ×0.8 gave front network vs capacitance.
- A strongly ringing in-model case (80 µH, front ×0.25) trips the unit-plausibility guard and is not diagnosed quantitatively.
- 40 % of the tail at the load side is within tolerance of the declared model ("No change needed").
- Low resolution, thick trace and a second curve in another colour digitize within 3 %.

**Revisions after the first run** (`case_revisions.json`):

- A save bug, fixed: non-finite identifiability values blocked storage in two cases.
- Two wording changes: a "Requires review" note next to the verdict, and a clearer unit-plausibility message.

No threshold or fixture changed. All runs together took 74 s.

**What this does not show.** Stand-in recordings come from the same lumped circuit or from deliberately added features. Real screenshots, real spark-gap and divider behaviour, and real component faults are not represented. Diagnostic accuracy on the real CPRI generator and on laboratory photos is unknown.

## API (additive, `/api/diagnostics`)

| Method | Path | Purpose |
|---|---|---|
| GET | `` | List saved diagnoses |
| POST | `` | Start from `{run_id, candidate_id}` |
| POST | `/demo` | Start the labelled generated demonstration |
| GET | `/{id}` | Session view: current records, staleness, revision history |
| POST | `/{id}/as-fired` | Record the settings actually fired: `{values, uncertain}` |
| POST | `/{id}/upload` | Upload a CSV or image (multipart) with the origin declaration |
| GET | `/{id}/image/original` | Original image bytes (checksum verified) |
| POST | `/{id}/image/preview` | Working image after transforms, plus suggestions |
| POST | `/{id}/digitize` | Extract with transforms, plot area, trace point, edits and axes |
| POST | `/{id}/compare` | Compare with `{alignment, excluded_ranges_us}` |
| POST | `/{id}/investigate` | Start the investigation (returns `job_id`) |
| GET | `/jobs/{job}` | Job progress |
| POST | `/jobs/{job}/cancel` | Cancel a job |
| POST | `/{id}/explore` | Hypothetical optimizer run for one explanation |
| GET | `/{id}/report` | Self-contained HTML report |
| GET | `/{id}/export.json` | JSON export |
