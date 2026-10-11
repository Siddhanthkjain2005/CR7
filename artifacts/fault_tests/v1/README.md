# Fault-scenario numerical verification v1

**34/34 generated numerical scenarios agree with separately constructed Radau and BDF Kirchhoff integration. Four additional all-bypassed cases correctly reject an unsupported topology.** This demonstrates solution correctness for the declared lumped circuits; physical CPRI fault accuracy remains unknown.

- The registered protocol has 38 fixed cases: 18 chopped impulses (six front, twelve tail), 16 supported stage conditions and four unsupported all-bypassed cases. CPRI and workbook parameter families stay distinct.
- The protocol and original hash were saved before scoring. `pre_scoring_contract_clarification.json` clarifies the four expected unsupported rejections without changing case inputs or acceptance tolerances.
- The first execution had four real metric defects: zero/negligible-inductance tail chops retained the correct curve but lost the analytic pre-chop crest during extrema extraction. `initial_results.json` and `initial_execution/*.npz` preserve those failures.
- `corrections.json` discloses the narrowly scoped correctness repairs. `results.json` and `corrected_execution/*.npz` are the unchanged-protocol rerun: all seven applicable gates pass.
- Worst exported voltage difference against the independent methods is `1.511947864e-8` of the healthy crest (approximately `0.000001512%`). This is **numerical agreement for the same assumed equations**, not a measured waveform accuracy percentage.
- Unit regressions separately exercise nonfinite/boolean/nonphysical requests, incorrect chop category, unsupported open-gap modes, snapshot preservation, conceptual stage position invariance, partial-charge accessible/internal-energy separation and fast finite-R/L reversal at nearby event phases. See `tests/test_fault_tests_independent.py` and `verification_summary.json`.

The NPZ files contain `time_us`, both exported voltages, independently integrated Radau/BDF fault voltages and independently calculated passive energy. They are generated scenario evidence. They do not enter the ML weights, old completed studies, measured calibration or independent laboratory evaluation.

No physical gap adjustment, conductive-bypass operation, energization instruction, equipment pulse rating, standard conformity or personnel safety certification is provided. Read `docs/fault_tests_physics_review.md` for the model equations, source links and limitations.
