# Conceptual assembly digital twin

This additive frontend workshop appears after a saved recommendation, below the existing recommended setup. **Assemble digitally** in the page header jumps to it. Its purpose is to explain the recommended configuration and rehearse its review; it is not an installation drawing, a verified physical twin or permission to energize equipment.

## What is shown

The workbench uses the saved run and selected candidate. Virtual groups represent the stage capacitor bank, front resistor network, tail resistor network, effective connection-loop inductance and combined load-side capacitance. Each group has a plain explanation, its saved values and a safety briefing. Users can place a group by dragging it or using its button, inspect it, review the next phase and reset the virtual plan.

The existing generator 3D overview remains available with its 2D fallback. The workshop's raised schematic has exploded and assembled views. These are conceptual geometry, not actual mounting dimensions. Motion respects the operating system preference and the app's Quiet motion switch. No new external runtime assets or dependencies are used.

Stage capacitance is separate from load capacitance. In the explicitly recorded series-Marx equivalent only, erected capacitance is C_stage / active stages and whole-network resistance is active stages × per-stage resistance. The load-side sum retains test-object, divider, stray and optional base contributions separately; unknown values stay unknown. Effective connection inductance is not an instruction to buy or install a coil. Fitted effective parameters remain separate from nominal hardware values.

Actual resistor branch detail is drawn only from the existing `verifiedTree` admission. Whole-equivalent connections additionally require a supported series model and consistent saved network values. Unsupported or unverified connections remain undrawn. An out-of-limit candidate is labelled a diagnostic alternative.

## Virtual state and evidence

The workshop does not call a mutation endpoint, rerun the recommendation, change a waveform, modify inventory, apply a correction or train a model. Its placement and briefing state is local and belongs to the complete saved snapshot. Changing the candidate or snapshot starts a new virtual plan. An edited request is labelled stale and cannot continue placement as though the saved plan answered the edited request.

Checkmarks mean **briefing reviewed**. They do not verify a real installation. Completion stays **Virtual review complete · physical authorization pending**. There is no physical safety score, firing control or live equipment connection.

## Person safety

Physical work requires qualified, authorized laboratory staff and the facility's approved task plan, hazard assessment and procedures. The view explains the need for isolation, prevention of re-energization, independent stored-energy verification, documented component suitability, grounding/bonding and protection review, barriers, an exclusion zone and emergency preparation. It does not prescribe high-voltage assembly, discharge operations, PPE ratings, clearance distances or timings. Pulse ratings, mounting, clearances, installed condition, interlocks and personnel protection remain **not verified** by the app.

The briefing is supported by these primary references. They are guidance sources, not a statement that US regulations govern a CPRI facility; local procedures and approvals govern the real task.

- [OSHA 1910.333 — Selection and use of work practices](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333)
- [OSHA 1910.335 — Safeguards for personnel protection](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.335)
- [Berkeley Lab — Electrical Injury Emergency Response](https://electricalsafety.lbl.gov/electrical-safety/emergency-response/)

Backend, scientific models, saved results, source data and the existing API contract are preserved. Test and retention details are recorded separately in `artifacts/qa/october11_assembly_twin_review.json`.
