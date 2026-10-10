# ImpulseTwin AI

Physics-guided decision support for high-voltage impulse-generator setup. It recommends counted resistor/stage configurations before the next physical trial and makes the evidence, uncertainty and source assumptions inspectable.

The laboratory workflow often repeats analytical estimates, physical adjustments and trial shots. ImpulseTwin combines the CPRI physical generator profile, an explicit lumped Marx/RLC model and counted inventory constraints to propose a defensible starting point. The separate workbook profile supports reference reproduction and synthetic ML benchmarking. Frozen residual ML applies only to supported workbook calculator settings; it remains disabled for the CPRI profile and circuit mode.

The engineering UI and Judge Mode now start with the **CPRI physical profile and circuit physics**. Source stock quantities are unknown, so enter actual counts or a clearly labeled operator assumption before optimizing. The displayed load, divider, stray capacitance, inductance and efficiency are editable example inputs, not measured machine parameters. The 545 pF source capacitance is included explicitly and must be excluded if already represented by the divider/system inputs.

**Hardening verification:** final verification pending. The current change rationale, before/after checks and remaining limits will be recorded in [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md) and `artifacts/optimization_report.json`. Earlier dated release reports remain historical evidence.

## Judge workflow (10 October 2026)

Open **http://127.0.0.1:8000/** for the primary workflow: **Configure test → Recommend settings → Inspect waveform → Compare measurement**.

- **Configure test:** generator profile (or a custom generator with complete ratings), impulse type, desired crest in V or kV, test-object capacitance and divider capacitance. Stray capacitance, inductance and the loss factor sit under *Circuit assumptions*. Stock, engine and equipment reference have their own sections. Every assumption is saved with the run.
- **Results:** these lead with the waveform plot and say plainly what produced it, for example "Circuit prediction" or "Outside validated ML range; workbook-equation metrics used". The metrics shown are re-extracted from the plotted curve. Next come the conceptual 3D stack, the recommended stages and charge per stage, the front and tail resistor construction, deviations from target, the hardware and waveform verdicts and a few ranked alternatives. Detailed engineering evidence is collapsed underneath.
- **Compare measurement:** imports a measured CSV with its purpose (independent validation or calibration), divider scale, polarity, onset, session and shot, and the settings actually fired. The unchanged circuit is re-simulated at the as-fired settings.

What is demonstrated, and what is not, is in [docs/accuracy_report.md](docs/accuracy_report.md). The supporting documents are:

- [physics audit](docs/physics_audit.md)
- [laboratory validation checklist](docs/laboratory_validation_checklist.md)
- the evaluation pack, which you can re-run with `python -m scripts.evaluation_pack`

The static UI must be rebuilt after a source change: `cd frontend && npm run build -- --webpack` (Node 22).

## Architecture

```mermaid
flowchart LR
  A[Request + source profile] --> B[CPRI circuit physics or separate workbook reference]
  B --> C[Counted resistor / stage search]
  C --> D[Supported ML or physics fallback]
  D --> E[Limits + uncertainty + ranking]
  E --> F[Independent RLC + fixed-setting challenge]
  F --> G[Model evidence card + Judge Mode]
  E --> H[Saved prediction + raw trial]
  H --> I[Scoped calibration / independent measured evaluation]
  I --> G
```

[Architecture detail](docs/architecture.md) explains ownership and data flow. Post-ranking challenges do not rerank candidates.

## Evidence available

- **Synthetic benchmark:** frozen V1 reduced macro tolerance-normalized RMSE by 41.9265% versus physics on the original supplied Hidden Test. This is error reduction, not an accuracy percentage. Saved results are preserved; Hidden Test was not reused for tuning.
- **Development experiments:** V2 remains optional/experimental. V3, V4 and V5 remain non-promoted. Their development CV comparisons cannot be added to the V1 result. [Timeline](docs/experiment_timeline.md).
- **Saved search-quality evidence:** the previous release's bounded winner matches exhaustive enumeration in all four declared small synthetic cases, with zero objective gaps. The current hardening comparison is recorded separately in the optimization report. These small cases do not establish a global optimum. [Protocol and limits](docs/optimizer_quality_benchmark.md).
- **Generated trial feedback:** exercises upload, quality review and scoped calibration, always labeled as generated.
- **Measured laboratory accuracy:** pending actual independent captures. The [laboratory evidence workflow](docs/laboratory_evidence.md) is ready to accept and evaluate them without mixing sources.

## Important limits

The organizer clarification supplied for this hardening identifies the problem-statement parameters as the actual/reference CPRI generator inputs: 12 maximum stages, 200 kV/stage, 0.125 µF/stage and 2.5 kJ/stage / 30 kJ total. The workbook's 15-stage / 3 µF synthetic reference remains separate. CPRI stock counts, pulse ratings, permitted mounting, physical minimum operating voltage/stages and the role of 545 pF remain unverified. The configured 50 kV and two-stage lower bounds are application assumptions. Unknown inventory requires an explicit operator override. Equipment test levels are not invented when no authoritative catalog exists.

Reference and circuit predictions may disagree. Synthetic uncertainty and finite scenario checks do not guarantee laboratory performance. The workbook's static validation-table discrepancy remains unresolved. This software is decision support, not a hardware controller or IEC certification. [Source reconciliation](docs/source_reconciliation.md).

Circuit **v2.1** keeps the same physical equations while stabilizing the zero-inductance analytic solution, retaining significant tiny inductance and refining fast crossings at an appropriate numerical tolerance. It returns an explicit diagnostic if continuous crest or decay modes cannot be resolved. The matched CPRI Lightning regression retains approximately 11 stages, 181.90 kV/stage, 1.187 µs front, 53.744 µs tail and 22.75 kJ stored charging energy. [Model assumptions and units](docs/assumptions.md).

## Run locally

Use Python 3.12. Frozen models and the static UI are included, so training and Node are unnecessary to run the prepared app.

```sh
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -r requirements.txt
python scripts/dev.py
```

Open **http://127.0.0.1:8000/** (the guided seven-step walkthrough remains at `/judge/`). For exact Windows PowerShell, macOS and Linux installation/build commands, see [local setup and release readiness](docs/release_readiness.md). Setup needs internet for dependencies; inference runs locally after preparation.

## Demo and engineering views

**Judge Mode** guides a 4–6 minute tour: problem → request → exact configuration → evidence → alternatives → trial feedback → summary. Predictions and labels come from actual backend results. [Demo guide](docs/judge_mode.md).

Engineering pages retain waveform exploration, trial calibration, setup-change planning, model metrics, history and reports. **Laboratory Evidence**, **Hardware Verification**, **Experiment Timeline** and **Search Quality** make the supporting evidence easier to inspect. [Evidence levels](docs/evidence_levels.md), [hardware provenance](docs/hardware_verification.md), [test-object references](docs/test_object_reference.md).

The 6 October hardening passes 263 backend tests, frontend checks and desktop/mobile browser review while preserving frozen evidence. Before/after timings, search comparisons, numerical corrections and remaining limits are in [the optimization report](OPTIMIZATION_REPORT.md); progress is recorded in [AGENTS.md](AGENTS.md).

## Validate a release

```sh
python scripts/verify_release.py
```

The verifier checks frozen hashes, configuration/models, tests, frontend typecheck/build, static assets and a fresh database with external network blocked in-process. It writes `artifacts/release_readiness.json` with PASS / FAIL / NOT TESTED. Unverified platforms and disconnected-laptop rehearsal remain explicit.

No deployment is included. Confirm the remaining hardware metadata for physical application. Independent measured captures can later establish laboratory performance; they are not a prerequisite for the current physics-based challenge solution. Original implementation history and deeper results are preserved in [project history](docs/project_history.md), [PROJECT_STATE.md](PROJECT_STATE.md), and [HANDOFF.md](HANDOFF.md).
