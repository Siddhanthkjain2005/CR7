# Assumptions and unresolved source questions

Updated 6 October 2026. The organizer clarification supplied for this hardening identifies the problem-statement parameters as the actual/reference CPRI generator inputs. This establishes the CPRI profile as the primary engineering reference; it does not supply missing inventory, physical connections or measurement evidence. Earlier dated source-review notes remain historical records.

## Source inputs and operator assumptions

| Item | Interpretation |
|---|---|
| CPRI maximum stages, stage voltage and capacitance | Source inputs: 12, 200 kV/stage and 0.125 µF/stage |
| CPRI energy ratings | Source inputs: 2.5 kJ/stage and 30 kJ total; internally consistent with `0.5 C V²` at 200 kV/stage |
| CPRI front/tail values and auxiliary components | Preserve the supplied values; their exact pulse-time connection remains a lumped-model assumption |
| Minimum operating voltage and active stages | Physical minima are unverified. Configured 50 kV and two-stage bounds are application assumptions, not established machine limits |
| CPRI resistor counts, pulse ratings, permitted mounting and connections | Unknown until supplied; use explicit stock counts and provenance, never workbook quantities |
| 545 pF basic capacitance | Source value; inclusion as an additional shunt load is an explicit interpretation. Exclude it when already included in divider/system capacitance |
| Load/divider/stray C, connection L, efficiency and layout | Operator inputs. UI values of 650/250/55 pF, 12 µH and 0.83 efficiency are editable regression examples, not measurements |
| Workbook 15-stage / 3 µF profile | Separate synthetic mathematical reference, with derived 60 kJ/stage / 900 kJ total ratings |
| Workbook stock quantities | Four of each listed value per stage in the synthetic reference; these do not establish CPRI stock or permitted physical arrangements |

The incomplete briefing profile remains disabled. No profile fills unknown quantities from another profile. Missing authoritative equipment test levels remain unknown; operator references retain their supplied provenance.

## Equivalent circuit and dimensions

The retained topology is a generator capacitor shunted by tail resistance, feeding the load capacitor through front resistance and connection inductance. For `n` active stages, the physical equations below use SI units:

```text
Cg = Cstage_µF × 10⁻⁶ / n                  [F]
Cl = (load + divider + stray + included_base)_pF × 10⁻¹² [F]
Rf = n × front_network_ohm_per_stage        [Ω]
Rt = n × tail_network_ohm_per_stage         [Ω]
L  = connection_inductance_µH × 10⁻⁶        [H]
Vg(0) = n × charge_kV_per_stage × 1000 × efficiency [V]
Vl(0) = 0; I(0) = 0

Cg dVg/dt = -Vg/Rt - I
L dI/dt   = Vg - Rf I - Vl
Cl dVl/dt = I
```

At zero inductance, `I=(Vg−Vl)/Rf` gives the same two-capacitor RC topology. Charging resistance, potential/discharge resistances and sphere-gap dimensions remain preserved profile inputs; the solver does not infer a pulse-time connection for those components from incomplete topology information. It does not model spark-gap dynamics, distributed capacitance, electromagnetic fields or resistor pulse heating.

Charging-bank energy is `n × 0.5 × Cstage × (charge_kV × 1000)² / 1000` kJ. It equals the ideal erected-bank energy with capacitance `Cstage/n` and voltage `n × charge`. Supplied ratings remain limits against which this computed energy is checked; the calculation does not replace a source rating. The one voltage-efficiency factor gives an initial circuit energy smaller by `efficiency²`; it is not applied twice. Circuit energy includes both capacitors and, when present, `0.5 L I²`. Its derivative is `−Vg²/Rt − Rf I²`, so this passive topology cannot create energy. A lost stable decay mode is a numerical resolution failure, not physical circuit instability.

Times calculated in seconds convert to µs by `×10⁶`; voltage converts between kV and V by `×1000`; energy converts from J to kJ by `/1000`. The matched CPRI Lightning example sums `650+250+55+545=1500` pF once. It retains approximately 11 stages, 181.90 kV/stage, 1.187 µs front, 53.744 µs tail, 1425 kV crest and 22.75 kJ charging energy. These are model/regression results.

## Circuit v2.1 numerical policy

- The physical nodal equations are unchanged. The zero-inductance branch computes its two decay rates and single crest analytically, using decay-product/fast-rate to avoid cancellation of the slow mode.
- A tiny positive inductance is omitted only under the existing absolute small-L shortcut when `L/(Rf² Cseries) ≤ 10⁻⁸`, where `Cseries=Cg Cl/(Cg+Cl)`. A significant ratio retains the full RLC branch even below the former absolute cutoff.
- Continuous crossing roots use a tolerance scaled to their bracket, capped at the previous `10⁻¹⁵` seconds. Unresolved continuous RLC crests and finite stable decay modes return explicit diagnostic failures.
- The displayed damping ratio is the approximation `Rf/2 × sqrt(Cl/L)`. It describes the load branch alone, omits generator/tail coupling and is null for zero inductance.
- The solver version is **v2.1**. A calibration scoped to an earlier numerical policy does not automatically transfer.

Lightning uses `1.67 × (t90−t30)` front time and half-value time relative to the virtual origin `t30−0.5×(t90−t30)`. Switching retains the challenge's 250/2500 µs targets and uses time to peak and falling half-value from an explicit onset. Uploaded waveform metrics use the acquired samples with explicit baseline, polarity and onset; no default smoothing, resampling or raw-data changes are introduced. Sparse, unresolved and flat-crest acquisition checks remain admission requirements for calibration/evaluation.

## Evidence and remaining limits

- CPRI and circuit mode remain physics-only. Frozen V1 residual correction is restricted to supported workbook/reference calculator settings. No transfer accuracy is established for arbitrary hardware interventions or the physical CPRI profile.
- Prediction intervals are synthetic-data empirical/conformal intervals only. OOD and other profiles have no claimed statistical coverage. Nominal pass, interval containment and finite scenario pass fractions are distinct model statements; scenario fractions are not probabilities.
- No measured laboratory dataset or authoritative equipment BIL catalog was supplied. Measured captures are not a prerequisite for solving this challenge; they are necessary for a future independent laboratory performance claim. Generated stress/demo data stays labeled generated and cannot establish laboratory accuracy.
- Ranking weights remain versioned engineering choices in `config/optimization.json`. Component count is a setup-complexity proxy, not a measured count of changes from an installed setup. Bounded network/shortlist search does not prove a globally optimal result.
- Published workbook Model Validation metrics cannot yet be reproduced from its own formulas and labeled split; exact cached-case/helper parity is verified separately. Obtain the metric-generation script before claiming published-table parity.
- Deployment is excluded from this hardening. No new training, Hidden Test tuning, cloud resources or paid services are introduced.

Final full regression passes 263 tests; frontend typecheck/build and browser review pass. The measured performance/search comparisons and explicit remaining platform/evidence limits are in `docs/validation/optimization_report.md` and `artifacts/optimization_report.json`.
