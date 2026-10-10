# Independent circuit verification results — 7 October 2026

**Six of six numerical agreement channels pass.** This is a separate generated-data verification of the CPRI circuit implementation. It does not change V1’s saved 5/6-versus-kNN test, establish laboratory accuracy or measure an ML improvement.

## Registered generation and boundaries

The parameter-only manifest and complete thresholds were saved before generating any reference labels. There are 240 cases, 120 per impulse type; ID hashes assign 80 development and 40 evaluation cases per type. No model is fit or selected. The production source hash was frozen before outcomes; every reference was generated and hashed before the production circuit solver was imported for comparison. The completed evaluation is now exposed and cannot serve as untouched data for later tuning.

The independent implementation integrates normalized capacitor charge and inductor flux with SciPy Radau and BDF; a tighter Radau solve checks refinement. It imports neither production modal equations/coefficients nor waveform reconstruction, workbook observed labels or learned corrections. Continuous extrema and directed threshold roots use the integrated dense solution. This is a different numerical implementation of the **same disclosed lumped topology**, not a different verified physical model.

All 240 references pass the fixed solver/refinement agreement limit of 0.001% and normalized passive-energy increase/overshoot limit of 1e-8. No rows were resampled or excluded. The runtime comparison evaluates 40 fixed cases of each impulse type. A channel passes if at least 95% of requested cases have valid results, the 95th-percentile relative difference is at most 0.05%, and the worst difference is at most 0.2%. Failures remain in the requested denominators.

## Evaluation result

| Channel | Available / requested | RMSE, physical units | 95th percentile difference | Worst difference |
|---|---:|---:|---:|---:|
| Lightning Front | 40 / 40 | 7.4309e-11 µs | 1.0609e-09% | 2.1051e-09% |
| Lightning Tail | 40 / 40 | 8.6093e-11 µs | 2.1034e-10% | 2.7809e-10% |
| Lightning Crest | 40 / 40 | 4.2273e-10 kV | 1.2333e-10% | 1.5709e-10% |
| Switching Peak | 40 / 40 | 1.8283e-09 µs | 1.0773e-08% | 1.2347e-08% |
| Switching Tail | 40 / 40 | 3.4028e-09 µs | 2.2942e-10% | 4.5499e-10% |
| Switching Crest | 40 / 40 | 4.0295e-10 kV | 1.2876e-10% | 1.3326e-10% |

The single local run took **120.533 seconds**, with $0 cloud spend. No production circuit change was needed to achieve the declared numerical agreement. These tiny differences describe solver agreement, not instrument precision or physical prediction error.

## Assumptions and useful data

The source CPRI values are 12 stages maximum, 0.125µF per stage, front resistance 30/465/3700Ω, Lightning tail 520Ω and Switching tail 22000Ω per stage. Stages 2–12 and charges 50–200kV/stage are study settings; the lower bounds are application assumptions. Total capacitance 600–4000pF includes the 545pF contribution once. Inductance 0–30µH and efficiency 0.83 are assumed. Actual inventory, allowed mounting, component pulse ratings, spark-gap dynamics and distributed effects are not validated. Nominally noncompliant wave shapes remain in the study.

Each generated CSV is labeled in the adjacent parameter manifest and reference-label records as `independent_generated_simulation`. Units are microseconds and kilovolts. Waveform samples are plotted/exported values; reference metrics use continuous integrated crossings. These files are numerical fixtures, **not measured captures, certified waveform standards or new workbook residual training labels**.

Trusted external data identified a separate acquisition weakness: divider step responses could pass admission when a record-end discontinuity appeared to be the half-value crossing. Acquisition review v3 now requires at least four further acquired intervals and 2% of the extracted tail duration after that crossing. This application heuristic requests a longer record, preserving raw samples and metrics. Tests use unchanged VTT/PTB source data and suitable full impulse controls. No standards threshold or extractor certification is claimed.

## Reproduce and continue

`make verify-independent-circuit PYTHON=python3` refuses to overwrite the registered run. Protocol, predictions and summary are in `artifacts/independent_simulation/v1/`; generated parameter manifests, reference labels and 240 waveforms are in `data/generated/independent_circuit_v1/`. Independent tests recompute saved channel statistics, check energy/voltage scaling, retain unavailable-case denominators and verify previous source/experiment hashes. The original feasibility prototype is preserved separately.

For a **new accuracy** claim, obtain complete unused generator settings and actual unchopped captures or an organizer evaluator dataset. Public external sources inspected here did not supply that six-output mapping. Do not retune on this exposed numerical evaluation or the original exposed workbook test. The Model lab presents the three different scorecards separately: V1 saved test 5/6, V2 development 6/6, and numerical verification 6/6.

See [the simulation design](independent_simulation_data_protocol.md), [trusted-data search](trusted_waveform_data_search.md) and [capture plan](laboratory_capture_plan.md). The [NPTEL generator analysis](https://archive.nptel.ac.in/content/storage2/courses/108104048/lecture20/slide1.htm) supports the roles of the charged capacitor, load and shaping resistors; it does not identify this machine’s actual topology.
