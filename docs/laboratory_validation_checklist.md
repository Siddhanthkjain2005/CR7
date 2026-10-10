# Laboratory validation checklist

Use this list when the team can fire the real generator. Until actual captures are imported, **no physical test has taken place** and no laboratory accuracy is claimed.

## Before the session

- [ ] Confirm the generator configuration actually available on the day:
  - [ ] Stage count, stage capacitance and charging-voltage limit.
  - [ ] Front and tail resistor values and the number of each per stage.
  - [ ] How the resistors are connected inside each stage.
- [ ] Settle the two ambiguities that move predictions the most (`docs/physics_audit.md`):
  - [ ] Whether the 545 pF basic capacitance is already inside the divider or system capacitance. It moves the Lightning front by about 36 %.
  - [ ] Whether the charging resistors conduct during the pulse. This can shorten the Switching tail by up to about 13 %.
- [ ] Record the divider ratio and its calibration certificate, the digitizer, the sampling rate, the record length and the trigger settings.
- [ ] Enter the counted stock in the inventory editor, with its provenance (who counted, when).
- [ ] For every planned shot, save a recommendation **before** firing. Predictions must exist before outcomes.

## Representative shot plan

Plan **three repeat shots per setting**; repeats show shot-to-shot spread. Label each import with its session and shot number.

| # | Purpose | Impulse | Level | Why |
|---|---|---|---|---|
| 1–3 | Calibration | Lightning | ~50 % of target | Low-risk first look at the loss factor and timing |
| 4–6 | Validation | Lightning | Target (e.g. 1425 kV) | Main accuracy check at the recommended setting |
| 7–9 | Validation | Lightning | A ranked alternative | Different resistor network, same request |
| 10–12 | Calibration | Switching | ~50 % of target | Tail and loss check for the long-front case |
| 13–15 | Validation | Switching | Target (e.g. 1050 kV) | Main Switching accuracy check |
| 16–18 | Validation | Either | Different stage count | Checks transfer across stage counts |

Keep calibration and validation captures separate:

- In the import form, choose **Calibration** or **Independent validation**.
- Validation captures can never create a correction.
- Calibration captures are refused by the independent evaluation.

## For each shot

- [ ] Fire at the recommended settings. If anything differed, enter it under **Settings actually fired**: stage count, charge, resistors, load, divider, stray capacitance or inductance.
- [ ] Export the raw time–voltage CSV without filtering, smoothing, time-shifting or rescaling.
- [ ] Import it on **Compare measurement** with:
  - [ ] The units, the divider scale factor and the source of that factor.
  - [ ] The expected polarity and the physical onset time.
  - [ ] The capture time, instrument, session and shot number.
- [ ] Check the acquisition review. Resolve any of these before using the shot:
  - [ ] Unresolved crest.
  - [ ] Too few samples on the rising edge.
  - [ ] Incomplete tail.
  - [ ] Polarity mismatch.
- [ ] Keep the raw file. The application stores it byte-for-byte, with its SHA-256.

## After the session

- [ ] Run **Independent evaluation** on at least three validation shots per group. It reports error statistics and false-pass counts against the predictions saved before the shots.
- [ ] Report the results as:
  - [ ] Per impulse type and metric: median and worst errors, with sample counts.
  - [ ] False passes (predicted pass, measured fail) and false fails.
  - [ ] Shot-to-shot spread from the repeats.
- [ ] If a calibration shot shows a consistent crest offset, review the loss-factor assumption first. If it shows timing offsets, review the inductance and the base-capacitance choice first. Record any change as a new assumption, not as a model retrain.
- [ ] Do not retrain any model on validation shots.
