# Independent simulation data protocol

Prepared 7 October 2026. This is a design for a separately registered study,
not a completed ML experiment or a replacement for the saved workbook test.
No V1–V7 weights, calibration rows or exposed test results may be changed by it.

## What this can establish

A separately implemented transient integrator can produce useful **generated
simulation data** without calling the production predictor. Agreement between
its transient solution and the production modal solution verifies numerical
implementation of an assumed circuit. It cannot establish laboratory accuracy,
correct missing hardware facts, or convert the existing workbook final-test
score of 5/6 against kNN into 6/6. The six outputs in a new simulation study are
Lightning front/tail/crest and Switching time-to-peak/tail/crest; they need their
own scorecard and must not be combined with the saved workbook scorecard.

The physical primary profile remains the supplied CPRI 12-stage, 0.125 µF per
stage specification. Its connection notation is ambiguous, so a lumped series
Marx equivalent remains an explicit modeling assumption. Public CPRI pages
describe different machines and do not resolve this ambiguity. NPTEL's official
course supports the standard charged-capacitor, load-capacitor and front/tail
resistor model, while also showing that alternative resistor placements matter.
It does not verify this particular generator or its parasitic parameters.

## Independent reference equations

Use physical generator charge `qg`, load charge `ql` and branch magnetic flux
`phi`, with all internal values in SI units:

```
Cg = Cstage / stages
Cl = specified total load capacitance
Rf = stages * front resistor per stage
Rt = stages * tail resistor per stage
V0 = stages * charge voltage per stage * assumed voltage efficiency

dqg/dt = -qg/(Cg*Rt) - phi/L
dql/dt = phi/L
dphi/dt = qg/Cg - ql/Cl - Rf*phi/L

qg(0) = Cg*V0; ql(0) = 0; phi(0) = 0
Vload(t) = ql(t)/Cl
```

For exactly zero inductance, solve the branch current algebraically as
`I = (qg/Cg - ql/Cl)/Rf`; integrate the two charge equations. Do not use a
small-L cutoff in the independent reference. Small positive inductance is a
stiff ODE and should be treated by an implicit solver. Normalize charge/flux
and time so component units do not set the numerical tolerance accidentally.

The reference must not import `backend.app.physics.circuit`, its eigenvectors,
modal coefficients, output samples, waveform reconstruction, or ML corrections.
It must not read the existing processed observed labels. Its metric extractor
must independently locate continuous extrema and directed 30%, 90% and falling
50% crossings from dense integration output. Lightning follows the challenge's
virtual-origin definition; Switching uses time from the explicit zero onset.
These definitions are shared requirements, rather than learned parameters.

Passive energy provides an independent invariant:

```
E = qg²/(2*Cg) + ql²/(2*Cl) + phi²/(2*L)
dE/dt = -(qg/Cg)²/Rt - Rf*(phi/L)² <= 0
```

Retain all extrema for ringing cases and select the global positive crest.
An unresolved crossing, end-of-window crest, integration failure or energy
violation is a recorded failure, never a silently dropped row.

## Solver feasibility already checked

`ngspice` and `spice` were not found on the current PATH; no installation was
performed. SciPy 1.16.1 is installed. A temporary, independent charge/flux
prototype used Radau (`rtol=1e-9`) and BDF (`rtol=1e-10`) on six predeclared
cases spanning both impulse types, 2/11/12 stages, 0/12/30 µH and total loads
800/1500/4000 pF. Both solvers completed all cases. Their largest relative
front/tail/crest difference was approximately `4.69e-8`. Both solves cost
roughly 0.12–0.15 seconds per case on this computer. These six cases establish
solver feasibility only; they are neither laboratory observations nor a
registered blind accuracy dataset.

Temporary files: `/tmp/impulsetwin-independent-sim/prototype.py`,
`prototype_protocol.json` and `prototype_results.json`. The prototype's metrics
must not be used to tune the production model or select a favorable study seed.

## Proposed bounded study, register before generating labels

Before any labels, save a JSON protocol, source hashes, generator source hash,
parameter-only manifests, split IDs and thresholds. Make run output immutable;
refuse to overwrite completed output. This document is a proposal and does not
itself register a parameter manifest or execute that study.

- Generate 240 parameter rows: 120 Lightning and 120 Switching. Allocate
  80/type to development and 40/type to a sealed numerical holdout using a
  fixed, recorded hash assignment. Sample parameters before computing any
  outputs; do not resample failed or noncompliant settings.
- Use stages 2–12, charge 50–200 kV/stage, stage capacitance 0.125 µF, and
  front values 30/465/3700 Ω per stage with Lightning tail 520 Ω and Switching
  tail 22000 Ω per stage. Include every listed front resistor value for both
  impulse types, including nominally unsuccessful wave shapes.
- Total capacitance 600–4000 pF and inductance 0–30 µH are **study assumptions**,
  not independently measured properties. Include exactly zero L and boundary
  cases. The base 545 pF enters the specified total only once. An efficiency of
  0.83 is a disclosed initial-voltage assumption; it is not a measured loss.
- The modeled resistor values do not certify quantities, mounting or pulse
  ratings. No new statement about available laboratory inventory is created.
- Solve every case with Radau at `rtol=1e-9`, `atol=1e-12` after normalization.
  Independently verify with BDF at `rtol=1e-10`, `atol=1e-13`, and a tighter
  Radau solve. Use a predetermined adaptive horizon based only on circuit
  parameters, not production predictions; retain unsuccessful completions.
- Predeclare reference acceptance: all three metrics change less than 0.001%
  under solver/tolerance refinement, crest is interior, every required crossing
  exists, and normalized energy increase is below `1e-8`. Publish acceptance
  and failures over **all requested rows**, including solver disagreement.
- Freeze the production predictor's inputs and hash before opening holdout
  labels. Score the serving circuit mode against the independent reference;
  report RMSE, median/p95/worst relative errors, accepted/requested counts and
  runtime for each of the six channels. A proposed numerical agreement gate is
  p95 error at most 0.05% and worst error at most 0.2%, with at least 95% of
  requested cases receiving accepted independent references. Do not change
  thresholds after the results are known.
- This is a circuit implementation comparison. Workbook kNN and workbook
  residual ML have no validated CPRI transfer and are not suitable primary
  baselines here. If development data later supports a surrogate, fit only on
  development rows, freeze the surrogate and protocol, then open a separate
  previously unused holdout once. Do not claim improvement from fitting a
  surrogate to outputs of the same predictor it is compared with.

A 240-case reference study with three implicit solves per row should need
minutes of local CPU work and little memory; cloud training is unnecessary.
Record actual runtime rather than presenting this feasibility estimate as a
completed benchmark.

## Optional SPICE corroboration

An installed ngspice can provide a third independent implementation of the
same circuit: `Cg` and `Rt` from erected generator node to ground, `Rf` and `L`
in series to the load node, and `Cl` to ground. Set the generator capacitor's
initial voltage to `V0`, load capacitor voltage and inductor current to zero,
then use transient analysis with explicit initial conditions (`uic`). Save the
complete deck, solver version, raw waveform, logs and all failures. Repeat with
halved maximum timestep and tighter tolerances; compare Gear and trapezoidal
integration so numerical ringing is not mistaken for physical ringing. A
default DC operating point would discharge this source-free circuit and is
not the intended initial condition.

Do not fabricate measured noise or assume a known error distribution. A
distributed generator, gap dynamics or uncertain component values can form a
separate sensitivity study once their models and ranges have credible sources.
Assumed perturbations remain assumptions; they do not become independent
physical ground truth by being simulated.

## Primary sources consulted

- [NPTEL, Analysis of Single Stage Impulse Generator](https://archive.nptel.ac.in/content/storage2/courses/108104048/lecture20/slide1.htm):
  circuit roles, initial charging and alternative resistor placements.
- [SciPy solve_ivp documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html):
  Radau/BDF, dense output, event and tolerance behavior. The current web
  documentation is newer than the installed SciPy version, so record the local
  version and check used options against that installation.
- [ngspice official documentation](https://ngspice.sourceforge.io/docs.html)
  and [version 47 manual](https://ngspice.sourceforge.io/docs/ngspice-47-manual.pdf):
  capacitor/inductor initial conditions, `.tran`, `uic`, timestep and integration
  methods. A simulator's numerical convergence does not validate hardware.
- [CPRI Impulse and Power Frequency Test Laboratory](https://www.cpri.res.in/en/content/impulse-power-frequency-test-laboratory):
  describes a 3 MV/150 kJ installation; it is separate from the supplied
  12-stage/30 kJ hackathon profile and supplies no corresponding raw captures.

No external raw measured dataset has been acquired by this design task.
