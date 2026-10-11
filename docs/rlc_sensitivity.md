# RLC sensitivity explorer

The briefing (20:01–20:16 and 24:58–25:37) asks teams to explain the roles of resistance, inductance and capacitance. **Explore R, L and C** on the Optimizer now supports that demonstration.

## Rehearse the comparison

1. Load the Lightning agreement preset, select rank 1, and click **Explore R, L & C** beside Export report to jump to the panel.
2. In **Explore R, L and C**, choose test-object capacitance and preview **+30%**.
3. Select **Equivalent circuit** and **Front / peak detail**.
4. Explain the change from 850 to 1,105 pF while nine active stages, charging voltage and efficiency stay fixed.

In the archived agreement example, the circuit front time moves from approximately **1.417 to 1.665 µs** (+17.49%), exceeding the unchanged 1.56 µs upper limit. Tail changes from 52.927 to 53.468 µs and crest from 1,397.727 to 1,389.585 kV. This is a generated model comparison, not an observed laboratory result. It does not invalidate the saved 144 checks at ±5%; the new preview changes one input by +30% and is separate evidence.

Switch to **Workbook equations** to see the same input change under the reference model. The workbook holds crest independent of RLC at fixed stage count, charge and efficiency; the circuit can change crest through load transfer. Their different behavior is visible instead of being hidden in a shared trend claim.

## What is held fixed

Each preview varies exactly one of front resistance per stage, tail resistance per stage, object capacitance, divider capacitance, stray capacitance or connection inductance. Percentage changes are restricted to −30% through +30% and must still satisfy simulation input bounds. Changing an input that is zero by a percentage leaves it zero; the interface states that no change occurred.

Active stages, charging voltage, efficiency, captured generator profile and all other inputs remain fixed. Resistor previews use hypothetical equivalent values: **they have no newly verified stock construction**. Run a new optimization to obtain counted parts. Neither saved ranking nor saved uncertainty status changes.

## Evidence and limits

- Both raw physics models are recomputed using the saved profile and current versioned equations. No residual ML inference or local trial correction is applied.
- Reference curves reconstruct three predicted metrics with a double exponential. Circuit curves come from the lumped model. An impossible reconstruction retains valid numeric metrics and states that no curve is available.
- The table checks nominal waveform limits only. It does not apply an uncertainty envelope or provide stock, laboratory or continuous-range approval.
- Effects apply to these inputs and models. The comparison does not establish interactions, a universal monotonic relationship or measured accuracy improvement.
- **Preview audit JSON** preserves source-run hash, captured inputs/profile, before/after settings, both model versions and generated curves. Changing a parameter or candidate hides the previous preview until the matching comparison is generated.

API: `POST /api/runs/{run_id}/candidates/{candidate_id}/sensitivity`, then `GET /api/sensitivity/{id}/json`. Regression coverage is in `tests/test_sensitivity.py` and browser evidence is recorded in `artifacts/qa_summary.json`.
