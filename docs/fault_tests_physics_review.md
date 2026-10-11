# Fault-test physics and the limits of the evidence

These are **generated, conditional circuit scenarios**. They answer what the saved lumped circuit would do under a declared switch or stage condition. They do not establish that the physical CPRI machine has that switch, fault, connection, rating or measured response. A scenario is run at the saved charge; it is never silently re-optimized to recover the requested crest.

## Chopped lightning impulse

Front-, crest- and tail-chopped lightning impulses are real testing categories: the [HIGHVOLT manufacturer's test-system page](https://www.highvolt.com/en/productdetail/impulse-voltage-and-current-test-systems/ip) lists all three. Its [system brochure](https://www.highvolt.com/fileadmin/downloads/products/product-brochures/impulse_voltage_and_current_test_systems/3-40-en_ip_brochure.pdf) explains that a chopping gap provides fast breakdown and that the connections affect circuit inductance. This supports a switched circuit representation; it does not provide CPRI-specific switch parameters.

The implemented idealized event closes an additional **finite-resistance load-to-return branch**, optionally with branch inductance, at the entered time. Until this time, the same saved healthy circuit is used. Generator and load capacitor voltages remain continuous. Existing series-inductor current remains continuous; a newly connected branch inductor begins at zero current. Load voltage can then fall rapidly, undershoot and ring according to the passive network. Setting every sample after the event to zero would erase that circuit behavior and is not used.

The branch resistance and inductance are hypothetical scenario inputs. A real gap has a statistical firing delay, pre-discharge, nonlinear arc resistance, geometry-dependent capacitance/inductance and a measuring system response. These effects require additional data/models. The existing generator load capacitance remains unchanged before the ideal event, so this is not a prediction of the pre-discharge loading of an actual chopping gap.

The reduced equations after closure, with all values in SI units, are:

- `Cg dVg/dt = -Vg/Rt - Iseries`.
- `Lseries dIseries/dt = Vg - Rf Iseries - Vl`; for zero series inductance, `Iseries=(Vg-Vl)/Rf`.
- `Cl dVl/dt = Iseries - Ishunt`.
- `Lshunt dIshunt/dt = Vl - Rshunt Ishunt`; for zero shunt inductance, `Ishunt=Vl/Rshunt`.

All capacitors and inductors are included in the total modeled stored energy. Its derivative is `-Vg²/Rt - Rf Iseries² - Rshunt Ishunt²`, so a positive-resistance passive scenario cannot gain energy after the event. This is a numerical correctness check, not a personnel-safety calculation or a pulse-rating determination.

A chopped impulse is not an ordinary full 1.2/50 pulse. Report the prospective healthy waveform separately from the actual chopped waveform, chopping instant, voltage immediately before closure, available collapse crossings and undershoot. Ordinary full-wave 50% timing must not be represented as a tail qualification when the voltage fell because of the chop. A front-chopped scenario does not prove that the hypothetical prospective crest was reached. Peak-time classification is relative to the healthy waveform, not a substitute for a certified standards evaluation.

The [official IEC 60060-1:2025 listing](https://webstore.iec.ch/en/publication/65088) identifies a revised fourth edition and changes to impulse terminology. The paid standard's full requirements have not been reproduced or implemented in this feature. Existing hackathon waveform conventions remain unchanged, and this tool makes **no IEC compliance or certified chopped-wave measurement claim**.

## Generator stage conditions

A Marx generator charges stage capacitors in parallel and erects them in series so their voltages add, as explained by the [TU Darmstadt high-voltage laboratory](https://www.hst.tu-darmstadt.de/forschung_hst/laborausstattung_hst/imp_spg_hst/index.en.jsp). That principle permits two bounded, distinct hypotheses:

1. **Uncharged but fully erected stage(s).** Every capacitor and the original shaping network remain in the conductive erected stack, but the selected stage capacitor(s) initially contribute zero voltage. The initial erected voltage becomes `(n-k) × saved_charge × efficiency`, while the equivalent capacitance `Cstage/n` and original total resistances remain. The linear lumped model therefore predicts an exactly proportional lower waveform and the same relative shape. This assumption requires full successful erection; it is not a simulation of a gap that stays open.
2. **Conductive stage bypass.** A declared conductive replacement removes selected stage capacitors and their per-stage shaping-network contributions from this assumed series model. The remaining stack has `n-k` active stages, `Cstage/(n-k)`, `(n-k)Rf_stage` and `(n-k)Rt_stage`. Its shape can change, and the charge remains the saved charge. This explicitly assumed bypass is not equivalent to an open gap or delayed ignition.

For the all-uncharged fully erected conductive stack, zero output follows from zero initial lumped energy. The tool must not report ordinary front/tail metrics or a nominal waveform pass for that unresolved zero trace. An all-bypassed stack is rejected because no erected generator remains within this model; no substitute topology is invented.

An actual **open gap, incomplete erection, delayed ignition, internal flashover or individual stage breakdown** requires a stage-resolved switching circuit and machine connection details. [Matsumoto's IEEJ primary research](https://www.jstage.jst.go.jp/article/ieejpes1990/116/12/116_12_1555/_article/-char/en) studies ignition waveform distortion and measured internal high-frequency oscillations; [Haddow's University of Glasgow thesis](https://theses.gla.ac.uk/73628/) attributes erection transients to the generator's stray fields. Their findings are a reason to reject an overly broad “one failed stage means one stage less” claim. Open-gap failure is therefore not presented as a supported prediction.

Stage positions are a visual selection in this lumped representation. The same number of selected identical stages has the same response regardless of their positions. The display cannot identify the physical failed stage or model location-dependent insulation stresses.

The source-energy quantity is the **accessible initial energy of the lumped equivalent**. In an individually uncharged fully erected stack, unequal stage voltages can retain internal redistribution energy not represented by the single equivalent capacitor. It must not be labelled the physical bank's total residual energy. No recommendation to raise the charge to compensate for a real fault is provided.

## Independent verification

The predeclared protocol is `artifacts/fault_tests/v1/protocol.json`. Its 38 fixed configurations compare the published curves against separately constructed Kirchhoff ODEs integrated with Radau and BDF in SI units. It also checks pre-event identity, event continuity, passive energy, zero-inductance analytic limits, fixed-charge proportionality/bypass changes, published-sample metric extraction and invalid inputs. The production modal/matrix helpers are not used to construct the independent reference.

CPRI uses the supplied 12-stage machine with 0.125 µF/stage; workbook scenarios use the separate 15-stage 3 µF/stage reference. Selected active stages do not redefine available stages. Verification cases with custom ringing parameters are hypothetical and have no hardware rating assertion.

Numerical agreement shows the code solves the specified equations. Laboratory waveforms and confirmed as-fired settings are still needed to quantify real machine accuracy. These generated cases do not enter measured calibration, held-out evaluation, frozen model weights or previous completed studies.

## Personnel boundary

The interface is a simulation and teaching aid. It must not issue instructions to insert a physical bypass, alter spark gaps or deliberately fault equipment. Physical work belongs to qualified, authorized staff under the site's reviewed procedure with independently confirmed isolation/stored-energy controls, barriers/interlocks and emergency planning. Checklist ticks or a generated low output do not establish that a real stage or bank is discharged or safe to touch. Unknown equipment pulse ratings, mounting and clearances remain unknown.
