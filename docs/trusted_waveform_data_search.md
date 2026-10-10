# Trusted external-data search — 7 October 2026

The bounded search identified useful public numeric data, but **no reviewed
dataset supports a new six-output final-test claim**. Training this generator
requires known per-shot stages, charging voltage, stage capacitance, front/tail
resistors, object/divider/stray capacitance, inductance and compatible measured
Lightning and Switching outputs. A waveform from another apparatus without
those inputs cannot supply the missing supervision. Missing units and hardware
parameters were not invented.

| Primary source | Retrieved and inspected | Appropriate use |
|---|---|---|
| [VTT/PTB cable-effects data, DOI 10.5281/zenodo.6340016](https://zenodo.org/records/6340016) | CC BY 4.0 workbook; three measured divider step responses of 22,000 samples each; original checksum verified | Independent capture-admission negative controls. These are steps, not complete LI/SI impulses. Two exposed an end-of-capture admission weakness, now covered by regressions. |
| [UHV lightning-divider linearity, DOI 10.5281/zenodo.8435957](https://zenodo.org/records/8435957) | CC BY 4.0 workbook from VTT/RISE/VSL/PTB and partners; original checksum verified | Divider calibration and measurement context. Numeric calibration/charging results, not per-shot generator training rows or raw impulse traces. |
| [Positive-leader branching data, DOI 10.5281/zenodo.20539246](https://zenodo.org/records/20539246) | CC BY 4.0 Figure 2 voltage CSV, 9,987 rows; checksum verified; [linked research article](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2026JD046897) | External waveform audit material. CSV has no header/verified units or complete circuit metadata; sharp decay needs chopped/breakdown review. It remains quarantined from scoring and fitting. |
| [Single-level impulse generator, DOI 10.17632/6g9cccrvvc.1](https://data.mendeley.com/datasets/6g9cccrvvc/1) | Public metadata inspected; explicitly numerical simulation of a Lightning impulse, CC BY 4.0 | External simulated example. One waveform family with incomplete circuit metadata cannot provide six-output measured validation. Numeric file was not retrieved. |
| [University of Strathclyde impulse-driven surface flashover](https://pureportal.strath.ac.uk/en/datasets/data-for-characteristics-of-impulse-driven-surface-flashover-acro/) | Repository describes 1,600 voltage/current records from different pulse generators; download returned 403 | Domain mismatch: flashover, fast pulses and incomplete compatible setup mapping. Failure retained; access controls were not bypassed. |
| [IEC 61083-2:2013 reference software data](https://webstore.iec.ch/en/publication/4471) | Official TDG/reference-waveform product located; open licensed files not found | Appropriate future extractor conformance evidence if a lawful copy is supplied. No paid purchase or third-party mirror used. |

Original files and public metadata are preserved under `data/external/`, with
attribution, license, SHA-256 and publisher checksums alongside them. The detailed
eligibility audit and rejected candidates are in
`artifacts/external_data/source_review.json`. The step-response reproduction and
definition compatibility are in `reference_waveform_data_review.md`.

The admission correction flags a half-value crossing that leaves fewer than
four acquired intervals or less than 2% of the extracted tail duration before
the record ends. These are conservative application preferences, not IEC
limits, a saturation diagnosis or automatic waveform classification. It
preserves the raw samples and extracted values, and requests a longer capture
before calibration/evaluation. Suitable full impulse controls remain usable.

The primary physical CPRI profile has no validated transfer from workbook ML.
Generating data with a separate transient integrator can check the assumed
circuit implementation and produce clearly labeled simulation fixtures. It
cannot create measured outcomes or erase the old final-test regression. See
`independent_simulation_data_protocol.md` and the completed numerical report for
the separate scope. External records are not merged into the frozen synthetic
CSV, V1–V7 studies or laboratory histories.

The next input for an independent generator-accuracy comparison remains a fresh
complete dataset with actual settings and untouched voltage/time captures,
or organizer evaluation data held out from development. The existing app can
review and score new captured shots against predictions saved before outcomes.
