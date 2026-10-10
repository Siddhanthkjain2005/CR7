# Physics audit — 10 October 2026

Reproduce with `python -m scripts.physics_audit` (writes `artifacts/physics_audit/v1/audit.json`).
The audit covers four representative settings: the recorded CPRI 1425 kV Lightning and 1050 kV Switching recommendations, and the workbook calculator's own 1425 kV setting.

The audit keeps three levels of evidence apart. They must not be added together or reported as one number.

| Level | What was compared | Result |
|---|---|---|
| Numerical agreement for the same equations | Production modal solver against two separate integrators: the charge/flux Radau integrator in `scripts/independent_impulse_reference.py`, and a state-space ODE solve | Below 0.0005 % on every metric and case. Earlier, 240 generated cases passed 6/6 channels (`artifacts/independent_simulation/v1`). |
| Agreement between different circuit models | Workbook equations, the tail resistor moved to the load side, and a hypothetical extra discharge path | Differences of several percent to tens of percent (table below). This is model-form uncertainty, not solver error. |
| Agreement with measurements | None available | No measured waveform from a generator with known settings has been supplied, so physical accuracy is not established. |

## Equivalent circuit and units

The production model is the series Marx equivalent:

- The erected capacitance `Cg = C_stage/n` is shunted by the total tail resistance `Rt = n·Rt_stage`.
- It feeds the load-side capacitance `Cl = load + divider + stray (+ base, if included)` through the total front resistance `Rf = n·Rf_stage` and the connection inductance `L`.

For the CPRI 1425 kV case this gives 11.36 nF, 1500 pF, 330 Ω, 5720 Ω and 12 µH. The stored energy is `n·½·C_stage·V²` = 22.75 kJ, against a 30 kJ rating.

The passive energy ratio never exceeds 1 (maximum 1.000), so the model creates no energy.

- Stage capacitance (0.125 µF CPRI, 3 µF workbook) is never mixed with stray capacitance.
- Available stages are a hardware input; active stages are a recommendation output.

## Model-form sensitivity

Each figure is the change in a metric relative to the production lumped circuit.

| Case | Workbook equations | Tail resistor on load side | Charging resistors as extra discharge path (hypothetical) | 545 pF base excluded |
|---|---|---|---|---|
| CPRI LI 1425 kV, front / tail / crest | −24.2 / −5.1 / +16.5 % | −3.8 / +4.1 / −4.1 % | −0.02 / −0.37 / −0.01 % | −35.7 / −5.7 / +5.3 % |
| CPRI SI 1050 kV, peak / tail / crest | −52.9 / −12.6 / +22.7 % | −7.3 / +11.9 / −11.5 % | −3.5 / −12.6 / −1.0 % | −27.7 / −7.4 / +6.6 % |
| Workbook LI 1425 kV (calculator setting) | −33.5 / −7.1 / +4.6 % | −63.2 / +180.7 / −65.4 % | — | — |

What these mean for a real test:

1. **The workbook equations are not a valid predictor for the CPRI machine.** They assume crest = n × charge × efficiency and ignore the voltage division between Cg and Cl. On CPRI hardware they overstate the crest by 17–23 % and misplace the front by 24–53 %. CPRI recommendations therefore use the circuit, and the reference engine stays a workbook benchmark.
2. **Where the tail resistance sits in the real machine matters,** most of all for Switching (±12 %). The CPRI connection details are not supplied, so the standard Marx equivalent is kept. This is the largest known model-form uncertainty, and it is a key reason to calibrate against measured shots (see `docs/laboratory_validation_checklist.md`).
3. **Charging resistors are negligible for Lightning but could shorten the Switching tail by about 13 %** if one column of them (11 × 135 kΩ) conducts during the pulse. Their pulse-time connection is not supplied, so they are not added to the model; this is a bound, not a correction.
4. **Whether the 545 pF base capacitance is already included** inside the divider or system capacitance changes the Lightning front by 36 %. Settle this with CPRI before the test. The application asks for it explicitly and records the choice.

## Loss and efficiency convention

The circuit already loses voltage through the Cg/Cl division and tail discharge. Its own voltage utilisation is 0.858 for CPRI Lightning and 0.815 for Switching.

The `efficiency` input is applied once more, on top, as a factor on the initial erected voltage. With the example value 0.83, the overall crest per erected kV is 0.712 for Lightning and 0.676 for Switching.

- If 0.83 is meant as an *additional* spark-gap and connection loss, the recommended 181.9 kV per stage is consistent.
- If the operator means the workbook's *overall* efficiency, losses are counted twice. The charge needed would then be about 151 kV per stage, not 182.

This cannot be decided from the supplied sources. The interface now labels the input as an "Additional loss factor" in circuit mode, explains the difference, and saves it with every run. The default stays at the existing example value so existing evidence is not silently changed. A first measured shot at known settings would settle it (see the checklist).

## Waveform definitions (challenge convention, unchanged)

- Lightning front: `T1 = 1.67 × (t90 − t30)` on the rising edge. Virtual origin: `O1 = t30 − 0.5 × (t90 − t30)`. Tail: `T2 = t50 − O1`.
- Switching: time to peak and time to half-value are both measured from the true origin, which is t = 0 in simulation and an explicit onset for captures. The 30–90 % interval is reported for reference (96.3 µs in the CPRI case).
- Standards editions define switching time-to-peak differently. The challenge targets (1.2/50 µs and 250/2500 µs) and the definitions above are kept; no standards certification is claimed.

## Effects the model omits

The following are omitted because no circuit information was supplied. They are not invented.

- Spark-gap resistance, arc inductance and firing jitter.
- Distributed stage-to-ground capacitance and stage inductance.
- Charging, potential and grounding resistor paths during the pulse (bounded above).
- Divider internal damping and lead geometry beyond one lumped inductance.

Measured shots at known settings are the way to quantify these (see the laboratory checklist).
