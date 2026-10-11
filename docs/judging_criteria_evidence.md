# Track 1 judging evidence and accuracy priorities

Reviewed 3 October 2026. Scope: supplied organizer material, verified public event pages and existing project evidence. No website preview, application UI review, deployment, training or new test-set evaluation was performed for this audit.

**The evidence supports prioritizing accurate waveform prediction, physically usable settings, numeric compliance and a clear working proof of concept. No Track 1 finale scoring rubric or numerical judging weights were found in the reviewed sources.** The priority order below is our engineering assessment, not organizer-assigned marks.

## Source authority

| Source | Authority and appropriate use |
|---|---|
| [Supplied problem statement](../data/source/HV IG Problem Statement.pdf), all four pages | Primary supplied challenge specification. Pages 1–3 state expected modules, inputs, outputs and constraints; page 4 adds range and measured-data guidance. All pages were text-extracted and visually inspected. |
| [Supplied expert briefing transcript](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md) | Direct record supplied by the team, with timestamps. Useful for operational priorities and the expert's answers; automatic transcription contains obvious technical/name errors, so do not infer missing precision from it. |
| [Supplied workbook](../data/source/Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx) | Reference calculator and synthetic benchmark, not evidence of laboratory validation. Its exported [Model Card rows 4–12](../data/processed/model_card.csv) explicitly identifies synthetic data and the need for actual reduced-voltage trials. |
| Existing project reports | Evidence of work already recorded. They are secondary engineering claims, not organizer instructions. This audit did not rerun their experiments or infer completion from file existence alone. |

## Verified public event evidence

Checked using text retrieval on 3 October 2026; no browser preview was opened.

| Official source | Verified finding | What it does not establish |
|---|---|---|
| [CPRI event notice](https://cpri.res.in/en/content/powernext-ai-2026-24-hour-hackathon-undergraduate-engineering-students-karnataka-manipal), “Start Date” / “End Date” | The event is 10–11 October 2026. CPRI identifies the event's registration site as powernext-ai.in. | No scoring rubric or exact submission cutoff. |
| [Event site](https://www.powernext-ai.in/), “Key dates” / “Hackathon Rules” | Preparation runs through 9 October; the finale includes presentations and evaluation. Submission must reach the official portal before its timer expires. Manipulating data, benchmarks, demonstrations or results to misrepresent a solution can lead to disqualification. | No numerical final-round weights, presentation duration or upload specification in the retrieved page. |
| [Official Track 1 abstract](https://www.powernext-ai.in/problem-statements), Challenge 01 | Physics plus ML should predict waveforms and recommend stage utilization, charging voltage and front/tail settings for both stated impulse types. Practical objectives include waveform accuracy and less preparation/trial effort. | No scoring weights or mandated ML family. |
| [Official problem page](https://www.powernext-ai.in/problem-statements), “Registration Process & Rules” | Detailed resources and further instructions go directly to team leads by email. | Public retrieval cannot establish that no private finalist rubric exists. |
| [Event brochure](https://www.powernext-ai.in/Brochure%20POWERNEXT%20AI.pdf), page 5, “How it works” | Finalists bring developed solutions to the 24-hour event. | The six-page brochure does not publish a finale scoring matrix. |
| [Organizer-listed Unstop event](https://api.unstop.com/hackathons/powernext-ai-manipal-institute-of-technology-bengaluru-1745296), “Screening Round” | Its explicit evaluation factors are prediction accuracy, abnormal-data detection, unseen-data performance, reproducibility and engineering reasoning. **These are scoped to screening.** | They must not be relabeled as the Track 1 finale rubric. The main site's linked Unstop page produced no readable text; the indexed organizer listing was readable. |

The team’s **10 October 2026 readiness deadline remains the planning target**. The now-verified two-day public event schedule is not permission to delay preparation. The exact final upload time and contents still require the team-lead instructions. The former screening page returned HTTP 404 during this audit; no missing content was inferred.

## Confirmed challenge deliverables and expert emphasis

PDF references below are page numbers and named sections. Transcript links point to the exact starting line; ranges and timestamps identify the complete passage.

| Expectation | Primary evidence | Interpretation for this project |
|---|---|---|
| Working software proof of concept; web app preferred | PDF p1 “Expected Solution”; [transcript lines 517–535](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 11:28–11:54 | A working demonstration is expected. Browser-only JavaScript/kNN describes the expert's prototype; the same passage permits exported models or a Python API. No mandated frontend/backend stack is stated. |
| Lightning 1.2/50 µs and Switching 250/2500 µs | PDF p1 “Challenge Statement”; [lines 769–811](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 16:59–18:00 | Show both challenge regimes with their definitions and source-tagged numeric limits. Do not silently substitute another standard/version. |
| Stage count, charging voltage, front and tail settings; predicted front/peak, tail and crest | PDF pp1–2 “Challenge Statement” / “Expected Outputs”; [lines 1177–1189](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 26:33–26:50 | These are the core engineering outputs, rather than a generic prediction score. |
| Physics first, learned correction, feasible ratings and tolerances | PDF pp1–2 modules 1–3; [lines 313–337](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 6:48–7:21 | Preserve separate physics and corrected predictions and hard operating constraints. |
| Multiple feasible alternatives, ranked by performance/compliance | PDF p1 “Challenge Statement”, p2 module 3, p3 “Compliance Information” | Alternatives are explicitly required. Exactly five alternatives and a particular weighted score are internal choices, not official criteria. |
| Numeric deviations, within/outside limits, target/predicted plots and performance display | PDF p2 module 4; p3 “Compliance Information” / “Visualization” | Results must be inspectable. An additional cosmetic redesign is not evidence of better accuracy. |
| Handle changing load/divider/stray capacitance, inductance and layout | PDF p3 “Additional Guidance”; [lines 313–319](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 6:48–6:57; [391–403](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 8:36–8:52 | Model/setup identity and parasitic sensitivity matter. Defaults must remain identifiable assumptions. |
| Actual generator parameters and operating limits | PDF p3 hardware list; p4 first paragraph and annotated figure | PDF-specific target: approximately 50–2400 kV, at least two active stages, subject to operating constraints. This does not promise every voltage has a feasible setting, and does not identify the separate workbook/briefing generator as the same machine. |
| Reduce physical resistor changes and trial effort | PDF p1 “Problem Overview”; [lines 283–313](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 6:07–6:48; [379–385](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 8:19–8:27 | Practical laboratory benefit is a central aim. Actual shot/time savings still need measurement; component-count or transition estimates are proxies. |
| Explain resistor combinations to a less-experienced user | [Lines 409–439](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 8:59–9:40; [979–1015](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 21:55–22:41 | Present a concrete counted series/parallel plan and the source of default inputs; do not invent unknown hardware quantities. |
| Improve accuracy beyond the initial model | [Lines 925–937](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 20:33–20:51; [1021–1045](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 22:49–23:24 | The expert explicitly confirms accuracy improvement as the student objective. Use regression error in physical units, separated by impulse and target; no “100% accuracy” threshold is specified. |
| Explain model comparisons and tuning | PDF p3 “Suggested Technical Approach”, item 5; [lines 1105–1111](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 24:41–24:50 | Comparing algorithms is suggested and explanation is emphasized. There is no official minimum model count, required family or cloud-compute requirement. |
| Wrong-voltage handling and equipment/BIL cross-check | [Lines 1051–1087](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 23:32–24:18 | Expert-proposed enhancement. Range rejection alone does not establish that a hardware-valid requested BIL is correct for a particular device. Use an authoritative source or explicit operator reference; missing catalog entries must remain unknown. |
| Understand R, L and C rather than treating the model as a black box | [Lines 1117–1147](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 24:58–25:37 | Be able to explain a controlled RLC sensitivity example and its assumptions. No requirement for a 3D generator animation is present. |
| Measured-waveform calibration and validation | PDF p4 second paragraph; workbook Model Card [rows 11–12](../data/processed/model_card.csv) | Explicitly important guidance and the route to laboratory accuracy. It is not evidence that measurements were supplied, or an explicit disqualification rule if unavailable. |

The transcript's opening says the session explains success criteria ([lines 91–109](../data/source/PowerNext_AI_Track1_Briefing_Transcript.md), 2:05–2:27), but neither that statement nor the discussion supplies numeric weights. The exact workbook-parity gate, OOD/conformal mechanisms, five alternatives, report export, chosen frameworks, P0/P1 labels and five-minute pitch are project design/rehearsal choices unless independently supported above.

## Prioritized gap assessment

These are priorities for verified accuracy and a defensible finale demonstration, not official scoring weights. Existing evidence is cited as recorded; no new laboratory claim is made.

| Priority | Current evidence and gap | Concrete next result |
|---|---|---|
| 1. Acquire new outcome evidence | [Accuracy progress lines 7–24](../docs/accuracy_progress.md) reports V1's 41.9265% macro tolerance-normalized RMSE reduction versus physics on the saved synthetic test; this is not an accuracy percentage. V4 produced no additional development gain ([V4 lines 3–11](../docs/accuracy_v4_results.md)). No measured laboratory result exists. | Use the existing [capture protocol](../docs/laboratory_capture_plan.md): save settings/predictions before captures, separate calibration from fresh evaluation, retain failures, and report MAE/RMSE by impulse, output and confirmed configuration. If data remains unavailable, preserve “laboratory validation pending” rather than manufacturing a new score. |
| 2. Confirm the physical setup used for judging | [Source reconciliation lines 9–31](../docs/source_reconciliation.md) records the 12-stage/0.125 µF PDF versus 15-stage/3 µF workbook distinction. PDF quantities, mounting and pulse ratings remain unknown. | Obtain a dated organizer/engineer confirmation of profile, resistor quantities, allowed network arrangements, ratings and the role of 545 pF. Record it as a new source without rewriting the original sources. Preserve profile-specific constraints and unknowns until confirmed. |
| 3. Validate recommendations away from calculator-selected settings | [Train-signal audit lines 34–49](../docs/residual_signal_train_only.md) finds every fit setting reproduces the calculator's selected setting. [Data audit lines 7–10](../docs/data_audit.md) records all-pass synthetic labels and Switching settings beyond available stock. | Design approved new captures with deliberate resistor/stage variations and held-out configurations. In the interim, keep calculator-setting support gates, count actual parts and separate ML-supported predictions from physics fallback. More training on the same observations cannot supply the missing intervention evidence. |
| 4. Demonstrate both impulse regimes honestly | [Search results lines 17–35](../docs/search_v4_results.md) preserve model-agreement failures and separate PDF circuit-mode successes with assumed stock. | Carry one reproducible Lightning example and one clearly labeled Switching example. For each, display profile/stock provenance, exact settings, each model's compliance and why ML is active or off. Do not present circuit-only success as independent model agreement or lab success. |
| 5. Complete the wrong-voltage story with provenance | Existing range/reference checks are recorded in [Accuracy report](accuracy_progress.md); [assumptions line 8](../docs/assumptions.md) confirms no authoritative BIL catalog. | Show one impossible voltage rejection and one equipment-reference mismatch. A future catalog needs equipment identity, impulse/test type, applicable source/version and provenance. A syntactically valid voltage cannot by itself establish the right test level. |
| 6. Make the accuracy contribution easy to verify | [Data audit lines 17–36](../docs/data_audit.md) shows six gains over physics, five over exact kNN and a 4.88% Switching-crest regression versus kNN; pooled R² hides scale differences. | Present a six-row baseline/kNN/selected error table and the frozen selection protocol. Retain the regression and source-table discrepancy. State separately what the software checks, what simulation suggests and what measurements establish. Do not add percentages from V1/V2/V3 comparisons. |
| 7. Turn practical benefit into a measurable claim | Existing transition planning and capture workflows support preparation, but no observed first-shot success, shot-count reduction or setup-time improvement has been reported ([judge handout lines 33–39](../docs/judge_handout.md)). | Predefine the comparison: first-shot compliance, total shots, actual component/stage changes and preparation time against the existing workflow on fresh cases. Until executed, call these intended benefits and planning estimates. |
| 8. Resolve submission format and freeze evidence | [Current rehearsal script line 3](../docs/judge_pitch.md) explicitly assumes five minutes. [Readiness questions lines 23–31](../docs/finale_readiness.md) remain open. | Team lead checks the private finalist instructions for rubric, exact cutoff, repository/archive/deck requirements, demo duration and expected onsite work. Freeze the runnable local package plus source/metric evidence before 10 October and record a disconnected-network rehearsal on the actual laptop. Public hosting has not been established as a requirement. |

## Unknowns that must remain explicit

- Final-round rubric, weights, tie-breakers and any accuracy pass threshold.
- Required submission files, exact final portal cutoff, presentation/Q&A duration and onsite build expectations.
- Which physical generator profile and stock judges will use, and whether an authoritative equipment/BIL table will be supplied.
- Whether measured shots or a fresh blind evaluator dataset will be supplied before or during the finale.
- The source script for the workbook's static validation table; its mismatch with reproducible formula evaluation is documented at [source reconciliation line 78](../docs/source_reconciliation.md).

No organizer was contacted by this audit. The official problem page establishes that further instructions may already exist in team-lead email; inspect those before treating any public-source omission as an absence of a rule.

## Source identity for repeatable review

Line references above refer to the files as reviewed. SHA-256 identifiers:

| File | SHA-256 |
|---|---|
| Briefing transcript | `ee211fe0ff67e369aed415a53a7231654b777388142c73a29788a73be7db95d9` |
| Supplied problem PDF | `9ab169fbda5eb612a7ff9ccfbadca8e85f5b49c2257c23388945d4e7c5532e93` |
| Supplied workbook | `e855eadbe4d6da2579316e89e025e6990f9ba3c522a5af96d1dd2a5522d77480` |
