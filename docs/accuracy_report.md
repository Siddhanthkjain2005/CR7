# Accuracy report — what is demonstrated (10 October 2026)

Branch `codex/hardening-judge-workflow`. **No measured generator waveform with known settings has been supplied, so no laboratory accuracy is claimed.**

The organizers will test against a real impulse generator. Measured agreement can only be established then, using the workflow and checklist below.

## Three kinds of evidence, kept apart

| Evidence | What it shows | Result |
|---|---|---|
| Numerical agreement (same equations) | Recommendations are re-simulated by an independent charge/flux integrator | Every displayed metric matches to below 0.0000005 %, and every plotted curve to below 0.008 % NRMSE |
| Agreement between circuit models | How much predictions depend on the assumed circuit form | Workbook equations differ by 5–53 %; topology variants differ by up to 12 % for CPRI Switching (`docs/physics_audit.md`) |
| Measured agreement | Real shots versus saved predictions | **None yet.** `docs/laboratory_validation_checklist.md` describes the shots to take. |

## Evaluation pack (36 requests)

Run `python -m scripts.evaluation_pack` to reproduce it. Results are in `artifacts/evaluation_pack/v1/results.json`.

The pack covers:

- Both impulse types, at low, mid, typical and high feasible voltages.
- Small and large loads and parasitics.
- With and without the 545 pF base capacitance, and with no extra loss.
- Restricted stage ranges, and one, two or four units of stock per value.
- Workbook settings inside and outside V1 support, on both engines.
- A complete custom 6-stage generator.
- Nine requests that must be rejected: above the profile limit, above the circuit-reachable crest, too few stages, no stock, an incomplete profile, an energy rating too low, inconsistent custom ratings, and an invalid engine combination.

**All 36 behaved as expected:** 27 recommendations and 9 rejections. Two expectations were corrected after the first run; see "Disclosures" at the end.

For the top three settings of each recommendation, the table compares the displayed values with the independent re-simulation. Errors are median / 95th percentile / worst absolute percentage.

| Profile · impulse · engine | Requests | Crest % | Front or peak % | Tail % | False passes |
|---|---|---|---|---|---|
| CPRI · Lightning · circuit | 11 | 0 / 0 / 0 | ≤ 2e-8 | ≤ 2e-8 | 0 of 33 |
| CPRI · Switching · circuit | 7 | ≤ 1e-8 | ≤ 2e-7 | ≤ 2e-8 | 0 of 21 |
| Workbook · Lightning · circuit | 3 | 0 | ≤ 1e-8 | ≤ 2e-8 | 0 of 9 |
| Workbook · Switching · circuit | 1 | ≤ 1e-8 | ≤ 1.4e-7 | ≤ 2e-8 | 0 of 3 |
| Custom · Lightning / Switching · circuit | 2 | 0 | ≤ 5e-7 | ≤ 2e-8 | 0 of 6 |
| **Workbook · Lightning · workbook equations + V1** | 2 | 4.3 / 5.0 / 5.1 | 25.5 / 33.6 / 33.7 | 6.7 / 7.4 / 7.4 | **6 of 6** |
| **Workbook · Switching · workbook equations** | 1 | 15.9 | 49.4 | 20.4 | **3 of 3** |

What this means:

- **The circuit path is internally consistent.** What the application plots, reports and decides on is exactly what the circuit equations give at the recommended settings. Hardware limits were never exceeded (0 violations).
- **Workbook-equation predictions are not confirmed by the circuit.** Each of the 9 passes the workbook engine showed fails when the same settings are simulated with the circuit. That engine stays a labelled workbook benchmark; CPRI and custom generators always use the circuit.
- **Recommendation quality.** In all 14 requests small enough to solve exhaustively, the bounded search found the same top setting as exhaustive search (14/14, zero objective gap).
- **Baseline.** The supplied workbook calculator's own settings, simulated with the circuit, met the challenge limits in **0 of 27** requests and missed the requested crest by a median 13 % (stock not checked). The optimizer's top setting passes the independent re-simulation in 20 of 27 requests. In the other 7, no constructible setting passes, and the result is shown as a diagnostic.
- **Runtime.** The median recommendation takes 1.9 s on one CPU core, and the slowest 4.2 s, including the post-ranking scenario checks.

## Where machine learning contributes

| Role | Status | Evidence |
|---|---|---|
| Residual correction (workbook data) | Frozen V1, unchanged | 41.9 % macro error reduction versus physics on the saved synthetic Hidden Test; 5/6 outputs better than workbook kNN. Active only inside its workbook support; elsewhere the circuit or workbook physics is used. |
| Residual correction (CPRI or custom) | **Not used** | No independent labels exist. A model trained on simulator output cannot correct the simulator. |
| Forward surrogate of the circuit (new, `artifacts/models/circuit_surrogate_v1`) | Trained and gated | 59,903 simulated rows (CPRI, workbook and custom families; failures and infeasible settings kept); grouped split; test frozen before model selection. On the frozen test the 95th-percentile error is ≤ 0.34 % for every output, and the worst is 1.54 %. Timing decisions disagree with the circuit on 0.03 % of rows. It is about 570 times faster per setting. The learning curve plateaus from about 4,000 rows. |
| Surrogate-screened network search | **Evaluated, not promoted** | Equal or better top setting in 24/24 requests, and strictly better in 1, at about 4 % more runtime. That fails the promotion rule declared in advance, so the default search is unchanged. |

Wherever ML is outside validated support, the app says "Outside validated ML range; circuit prediction used" or shows the workbook-equation basis. The surrogate never produces a displayed prediction.

## What still needs real-generator measurements

1. **Loss convention.** The circuit's own voltage utilisation (0.86 for Lightning) is multiplied by the assumed extra loss factor (0.83). If 0.83 was meant as the overall efficiency, the recommended charge is about 20 % too high (182 rather than 151 kV per stage). One reduced-voltage shot settles this.
2. **545 pF base capacitance.** Whether it is already inside the divider capacitance moves the Lightning front by about 36 %.
3. **Circuit form for Switching.** The tail-resistor position and the charging-resistor paths move the Switching tail by about 12–13 %.
4. **Repeatability, spark-gap behaviour and divider response.** These are only measurable on the machine.

## Reproduce

```bash
python -m pytest                                   # backend regression and new tests
python -m scripts.physics_audit                    # model-form audit
python -m scripts.generate_circuit_dataset --rows 40000 --seed 23 --output data/generated/circuit_dataset_v1
python -m scripts.train_circuit_surrogate --data data/generated/circuit_dataset_v1 --final
python -m scripts.evaluation_pack
```

## Disclosures

- After the first evaluation-pack run, two requests expected to produce recommendations (CPRI Lightning at 1900 kV and workbook at 2600 kV) were found to exceed the crest the circuit can reach within its stage-voltage rating. Their expected outcome was corrected to rejection, and feasible high-voltage requests were added. No model, search or limit was changed.
- The surrogate was first trained with a regression algorithm (adam with early stopping) that plateaued at 3–8 % error. It was retrained with L-BFGS restricted to the practical sampling regimes before the frozen test was scored once. The wide and extreme sampling regimes are reported as out of support; the domain gate rejects 53 % of them.
- All checks ran in a Linux sandbox (Python 3.13, scikit-learn 1.9). Surrogate weights are stored as plain arrays, so inference does not depend on the scikit-learn version.
