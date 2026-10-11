# ImpulseTwin AI — five-minute judge pitch

**Working format:** five minutes including a live demonstration. Confirm the organizer's actual time allowance before the finale. Rehearse with the local app already running and a saved report available.

## Value proposition

ImpulseTwin AI helps an impulse-test engineer choose and inspect a stronger starting setup before changing hardware and taking the next shot. It combines physics, carefully evaluated residual models and a bounded stock-aware search to propose stage counts, charging voltage and actual resistor constructions. It shows where training support ends, exposes disagreement with an independent circuit model and turns a trial waveform into a correction restricted to the tested configuration. The result is a reproducible engineering decision record, with laboratory benefit to be measured through paired field trials.

For a judge's RLC question, use **Explore R, L and C** on the Optimizer: the saved Lightning agreement example with object capacitance +30% crosses the circuit front-time limit while the supply remains fixed. Compare both raw models and distinguish reconstruction from circuit simulation. Keep this as an optional explanation so the five-minute pitch stays within time. See `rlc_sensitivity.md`.

## 0:00–0:40 — start with the physical decision

“An impulse-test engineer needs the right crest, front and tail. Reaching them can mean changing active stages and physically replacing front or tail resistors, then taking another shot.

“Our question is practical: before that next shot, can we give the engineer a better starting setup, explain the components it needs and show how much confidence the evidence deserves?

“This is ImpulseTwin AI. Every recommendation connects a predicted waveform to a component plan and an inspectable record.”

*Show the Optimizer and its inputs. Keep the selected generator profile visible.*

## 0:40–1:20 — establish source fidelity

“We began by reproducing the supplied workbook. Its displayed example and all 1,400 cached neighbor distances and weights match our implementation.

“Then we checked the assumptions. The workbook uses 15 stages and 3 microfarads per stage; the PDF machine has 12 stages and 0.125 microfarads per stage. Those are separate profiles. Mixing them would change stored energy and waveform behavior.

“We also found that every supplied Switching front-resistance setting exceeds the entire workbook front stock's all-series maximum. That is why predicting a good waveform alone cannot establish a usable hardware plan.”

*Briefly show Generator profiles. Keep the static workbook validation-table discrepancy available in source reconciliation for questions; do not claim parity with that table.*

## 1:20–2:10 — make the recommendation concrete

“Here is a Lightning request. The optimizer searches stage counts and bounded resistor constructions. It rejects candidates that exceed declared stock counts, stage voltage or energy limits before ranking them.

“The result shows charging voltage, the exact resistor network and component usage. We can compare alternatives with a saved current setup: resistor changes on shared stages, stage activation and charging adjustments. The planner finds the closest nominally passing option while keeping the original optimizer ranking and its challenge evidence separate.

“The status distinguishes a point prediction from containment of the returned uncertainty intervals and sampled parasitic scenarios. Pulse ratings, mounting and permitted physical connections still need confirmation from the laboratory.”

*Show the first candidate's construction plan and one alternative. Point to the visible uncertainty and compliance labels.*

## 2:10–2:55 — show a guard that changes the decision

“Now look at the independent circuit cross-check. The workbook approximation and the lumped RLC solver can disagree. We display that disagreement because it changes what an engineer should trust.

“For the Lightning example, the agreement search finds another counted setup that passes both models. We then challenge the fixed settings with 128 separate samples and all 16 boundary corners, without reranking on those results. This is simulation evidence, not lab validation.

“Switching solver changes the actual prediction path; workbook residuals are not transferred into the circuit solver. Move outside training support and the learned correction turns off. Request an impossible voltage and the software rejects it.

“These checks prevent silent extrapolation. They support the engineer's review; they do not replace laboratory interlocks or prove the circuit model is correct.”

*Show the cross-check, switch solver, then demonstrate the OOD and impossible-voltage presets. Skip extra clicks if behind time.*

## 2:55–3:35 — show the measured contribution of ML

“We compared five residual-model families, selected models using Validation and froze the configuration before evaluating Hidden Test.

“On that untouched synthetic test split, all six outputs improve RMSE over physics. The reductions range from about 13 to 53 percent. Five of six also improve over the exact workbook kNN. Switching crest is 4.9 percent worse than kNN, and we retain that result.

“These are per-impulse, per-target results. They establish improvement on the supplied synthetic benchmark, not laboratory accuracy or a measured reduction in trial shots.”

*Open Model lab. Point to the six individual comparisons rather than a pooled R² headline.*

## 3:35–4:30 — close the loop without hiding provenance

“A prediction becomes more useful when a trial can challenge it. Here we upload a generated demonstration waveform, explicitly labeled as generated. The app records the original file, units and configuration, then extracts crest, front and tail numerically.

“Its measured-minus-predicted difference can become a local correction. That correction is restricted to matching hardware, settings and model context. One shot does not retrain the production models or justify transfer from reduced voltage to full voltage.

“The report brings together the input, construction plan, waveform semantics, alternatives, uncertainty and source provenance, so another engineer can review the decision.”

*Use Trial calibrator with the prepared generated sample. Show the scoped correction review and open the saved report. Never describe this sample as a laboratory measurement.*

*If asked how we prevent misleading accuracy claims: explain the crest/tail acquisition review. A demonstrated sparse capture appeared to pass after missing the true crest; it is now retained for inspection but blocked from calibration and scoring. For new measured shots, show false-PASS counts and worst errors using the original saved limits. Do not show synthetic fixtures as laboratory outcomes.*

## 4:30–5:00 — finish with a testable next step

“Our contribution is a complete local workflow that connects physics, available hardware, supported learning and traceable trial feedback.

“The next validation is concrete: confirm CPRI stock and pulse ratings, collect paired reduced-voltage waveforms across layouts, then compare first-shot compliance, total shots and physical setup changes against the existing workflow on held-out cases.

“The proof of concept runs locally. Cloud hosting remains deferred. We are ready to demonstrate the workflow and to measure its laboratory value.”

## Sixty-second backup pitch

“ImpulseTwin AI helps an impulse-test engineer select a stronger starting setup before the next physical resistor change and shot. It combines physics with residual learning, then searches actual resistor constructions subject to declared stock, voltage and energy limits.

“The app shows the component plan, uncertainty, alternatives and an independent circuit cross-check. Outside training support, the learned correction switches off. A trial waveform feeds an auditable correction restricted to the tested configuration.

“We reproduced the workbook's example and every cached neighbor distance and weight. On the frozen synthetic Hidden Test, all six outputs improve RMSE over physics and five improve over exact kNN. This does not establish laboratory accuracy.

“The next step is verified CPRI inventory and paired field trials measuring first-shot compliance, total shots and setup changes. The complete proof of concept runs locally; cloud deployment is deferred.”

## Demo transition lines

- **Inputs → component plan:** “Let's turn this requested waveform into hardware the stock arithmetic can support.”
- **Plan → independent check:** “Before accepting that result, let's see whether a second physical model agrees.”
- **Physics → Model lab:** “Now we can isolate what the learned residual correction adds on the supplied benchmark.”
- **Benchmark → trial:** “The benchmark is synthetic. This is how an actual trial would enter the workflow, using a clearly labeled generated sample today.”
- **Trial → report:** “The final output is a decision another engineer can inspect and reproduce.”

## Evidence behind the spoken claims

- Exact workbook reproduction and source exceptions: [source reconciliation](source_reconciliation.md).
- Frozen split policy and all six errors: [data audit](data_audit.md), `artifacts/models/hidden_test_evaluation.json`.
- Implemented acceptance evidence and external limits: [accuracy report](accuracy_report.md).
- Detailed click sequence and fallback: [demo script](demo_script.md).

Do not claim a guaranteed win, global optimum, complete IEC certification, measured shot reduction, laboratory accuracy or verified mechanical/pulse compatibility. Keep generated samples separate from measured trials. If the live app is unavailable, use the saved report and the sixty-second version; do not invent an execution result.


Current judging-source audit: `judging_criteria_evidence.md`. The public event confirms 10–11 October 2026, but no finale scoring weights were found; screening criteria must not be relabeled as final-round marks. The five-minute format above remains a rehearsal assumption.
