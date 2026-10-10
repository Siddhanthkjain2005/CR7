# Calibrating the generator from measured shots — branch `codex/effective-parameter-calibration`

## Why

When the organizers fire the real machine, the first shots will usually be at reduced voltage. The existing one-shot correction cannot use such a shot to improve the full-voltage recommendation. It adds a metric offset only when the hardware settings are identical and the request is within 1 %.

The physics audit also showed that the largest prediction uncertainties are physical. Three effects carry most of it:

- the loss convention,
- capacitance not represented in the inputs (for example the 545 pF question),
- how the tail and charging resistors conduct.

Because these effects are physical, they can be fitted as physical parameters.

## Method

Version: `effective-parameter-calibration-v1` (`backend/app/physics/parameter_calibration.py`).

The lumped circuit keeps its topology. Three effective parameters are fitted by bounded least squares to the measured crest, front (or peak) and tail of one or more calibration shots, at their as-fired settings:

| Parameter | Meaning | Bounds |
|---|---|---|
| `loss_scale` | Multiplies the assumed extra loss factor | 0.6–1.25 |
| `extra_load_pf` | Load-side capacitance not represented in the inputs | −40 % to +150 % of the declared load-side total |
| `tail_scale` | Multiplies the total tail resistance (extra discharge paths) | 0.5–1.6 |

A weak prior pulls the fit toward "no change". The fit reports the residual on each shot, any parameter sitting at a bound, and the Jacobian condition.

The fitted parameters are then used for **every** setting of the same generator, impulse type, layout and base-capacitance choice:

- recommendations,
- scenario checks,
- fixed-setting verification,
- R/L/C sensitivity,
- as-fired re-simulation.

Recommendations still re-solve the circuit, and hardware limits still apply.

## Safeguards

- Only captures recorded as **Calibration** (or unspecified older captures) can be used. Validation captures are refused.
- Each capture must pass the shared admission (`docs/capture_admission.md`): acquisition review including the declared polarity and the connected-rise check, unchanged original bytes, an explicitly classified source, and a recorded review of any out-of-rating as-fired settings.
- All captures must come from the same generator, impulse type, layout and base-capacitance choice, and from runs that do not already use fitted parameters.
- Any capture used for fitting, or a re-import of it, is rejected by the independent evaluation of predictions that used those parameters. The fit must also predate those predictions.
- The fitted values are effective values of the lumped model, not measured component values. The production model is never retrained.

## Evidence (simulated model-mismatch study)

Run `python -m scripts.evaluate_parameter_calibration`. Results are in `artifacts/parameter_calibration/v1`; the protocol and gates were written before any scenario ran.

A stand-in "true" generator is an independent ODE with differences the model does not know about. There are six scenarios, each run for Lightning and Switching:

| Scenario | Difference from the declared model |
|---|---|
| Control | None |
| Less loss, more stray | Loss 8 % lower, 250 pF more stray capacitance |
| Charging-resistor path | Charging-resistor discharge path (11 × 135 kΩ) |
| Tail partly at load | 30 % of the tail conductance at the load |
| Spark resistance and inductance | 3 Ω/stage spark resistance, 10 µH extra inductance |
| Combined | A combination of the above |

Each scenario follows the same steps:

1. Recommend settings with the declared model.
2. Fire the recommended setting at 50 % charge on the stand-in generator, to give one calibration shot.
3. Fit the three parameters from that shot.
4. Predict ranks 1–5 at full charge, rank 1 at 75 % charge, and a setting with two fewer stages where one exists.
5. Re-recommend with the fitted parameters and fire that recommendation on the stand-in generator.

Errors are median / worst absolute percentage against the stand-in generator, over the five mismatch scenarios:

| | Declared model | One-shot offset | Fitted parameters |
|---|---|---|---|
| Lightning front | 4.10 / 13.0 % | 4.10 / 13.0 % | 0.006 / 0.03 % |
| Lightning tail | 0.86 / 2.5 % | 0.86 / 2.5 % | 0.001 / 0.01 % |
| Lightning crest | 2.92 / 5.3 % | 2.92 / 5.3 % | 0.001 / 0.03 % |
| Switching peak | 3.71 / 10.3 % | 3.71 / 10.3 % | 0.024 / 0.40 % |
| Switching tail | 3.15 / 15.2 % | 3.15 / 15.2 % | 0.005 / 0.60 % |
| Switching crest | 4.07 / 5.2 % | 4.07 / 5.2 % | 0.003 / 0.48 % |

The one-shot offset cannot transfer to other settings or voltages, so its errors equal the declared model's.

- **Recommendations on the stand-in generator:** 6 of 12 pass with the declared model, and **12 of 12 after fitting**.
- **Gates:** all five declared gates passed. The largest increase in any 95th-percentile error was 0.003 percentage points.

**With measurement noise on the calibration shot** (`--measurement-noise`: crest 0.5 %, front 2 %, tail 1 %, one sigma; results in `artifacts/parameter_calibration/v1_measurement_noise`):

- Errors are still roughly halved. Lightning front goes from 4.1 / 13.0 % to 2.1 / 3.5 %, Lightning crest from 2.9 / 5.3 % to 0.7 / 1.3 %, and Switching tail from 3.1 / 15.2 % to 1.3 / 2.8 %.
- Recommendations still go from 6/12 to 12/12.
- The no-difference control gate fails, as it must once noise is present (fitted errors above 0.5 %).

This is the reason the laboratory checklist asks for three repeat shots: averaging them reduces the noise.

## What this does not show

The stand-in generators are smooth lumped-circuit variants chosen by us. A real machine adds nonlinear spark-gap behaviour, divider response and instrument effects. Real calibration and validation shots are required to establish laboratory accuracy. The application keeps calibration and validation captures separate so that this can be done honestly.

## Using it

1. On **Compare measurement**, import a reduced-voltage shot as **Calibration**, recording the settings actually fired.
2. Press **Fit generator parameters from this shot**, then **Recommend again with the fitted generator**.
3. The results page says "Circuit prediction with generator parameters fitted from 1 calibration shot". The fitted values appear under engineering evidence.
4. Import later shots as **Independent validation** and run the independent evaluation.
