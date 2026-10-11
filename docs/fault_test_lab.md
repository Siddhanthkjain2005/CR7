# Fault Test Lab

This feature compares a saved healthy generator setup with an explicitly assumed fault. It is a generated circuit experiment, not a physical test, laboratory accuracy result, or permission to operate equipment.

## Where to find it

Recommend a setup, then choose **Fault test lab** beside **Assemble digitally**. The lab uses the selected saved candidate. Changing the form pauses experiments until the request is restored or a new recommendation is saved. Changing the saved candidate clears the displayed experiment.

The original charging voltage is held fixed. Fault results are not scaled back to the requested crest. This makes a reduction in output visible instead of hiding it with a new recommendation.

## Front- and tail-chopped lightning impulses

Choose front or tail chopping, an interruption time measured from the simulation trigger, and an assumed resistance and inductance for the chopping branch. The circuit switches a finite discharge branch across the load-side capacitance at that time. The post-event curve is solved from the electrical state immediately before the event.

Capacitor voltages and existing inductor currents remain continuous. With branch inductance, its current begins at zero. A branch with zero inductance uses a resistive current relation instead. The model can therefore show a rapid collapse and, where the assumptions produce it, a subsequent voltage reversal. It does not just replace the remaining samples with zero.

Front or tail is determined relative to the healthy circuit's prospective peak, not the requested 1.2 microsecond front parameter. A front-time parameter is not the same thing as the time of peak voltage. Chopped results do not receive a standard full-lightning-impulse pass badge or a fabricated 50 microsecond tail.

The chopping branch values are illustrative circuit assumptions. They are not CPRI equipment specifications or component recommendations. Gap arc dynamics, triggering scatter, distributed fields, measuring-system response and actual equipment withstand are outside this model.

## Generator stage failure

Two different hypotheses are available:

1. **Uncharged stage; conducting stack.** Selected stage capacitors have zero or reduced initial charge, but every stage's gap still conducts. The number of erected capacitors and the front/tail network totals stay fixed. In this ideal lumped model the terminal excitation decreases, so voltage amplitude changes without inventing a stage-location effect. The selected stage numbers are a conceptual display only.
2. **Deliberately bypassed stage.** The selected stages are removed from the equivalent erected stack. The effective generator capacitance and total front/tail resistances are recalculated from the remaining stage count. The original per-stage charging voltage and per-stage resistor values remain fixed. This is an assumed conductive bypass configuration, not an unfired spark gap.

A spark gap that fails to fire can break the series path and can involve capacitive coupling or delayed breakdown. That event requires a distributed stage/gap model and is explicitly not represented by simply using one fewer healthy stage.

The total energy initially stored in unequal stage capacitors is distinct from the energy visible to the terminal equivalent. Both must be labelled separately. A zero terminal waveform does not prove that physical capacitors are discharged or safe to approach.

## Evidence and preservation

Fault experiments are saved as their own record kind with the reference setup, request, version, generated provenance and exportable waveforms. They do not become laboratory captures, calibration shots or independent model evaluations. Saved recommendation rankings, CPRI/workbook profile separation, source data, frozen ML weights and completed studies are preserved.

If the original recommendation used workbook equations, the healthy overlay is explicitly an equivalent-circuit cross-check at that same hardware setting. If effective circuit parameters were fitted, their saved values and provenance must remain visible. One-shot metric offsets are not substituted for a circuit state.

Read [the physics review](fault_tests_physics_review.md) for equations, primary sources and limitations. Independent numerical verification and integration checks are recorded separately from the existing accuracy studies; they verify implementation within the stated topology, not real CPRI equipment accuracy.

## Verified CPRI demonstration

For the supplied CPRI Lightning example, the saved healthy setup has 11 active stages, 181.90279026170387 kV per stage, 30 Ω front and 520 Ω tail per stage, and 1,500 pF combined load-side capacitance. Its prospective circuit crest is 1,425 kV and occurs at 2.1266904956507546 µs after the trigger.

| Generated scenario | Fault crest | Interpretation |
|---|---:|---|
| Front chop at 1.0633452478253773 µs; assumed 10 Ω / 1 µH shunt | 1,341.0867117 kV | The pulse is interrupted before the prospective healthy peak. |
| Tail chop at 4.253380991301509 µs; same assumed shunt | 1,425 kV | The healthy crest has already occurred; the later decay and reversal change. |
| One completely uncharged stage; full conducting stack | 1,295.4545455 kV | Terminal excitation is 10/11 of healthy; the ideal relative shape stays the same. |
| One deliberately bypassed stage | 1,312.2912218 kV | The smaller equivalent stack changes capacitance and resistance totals, so shape changes too. |

These are reproducible generated examples, not readings from a CPRI experiment. The branch's 10 Ω and 1 µH values are illustrative assumptions, not hardware specifications. A tail chop retaining the healthy crest is correct because it acts after that peak.

## Verification record

The completed numerical study retains 38 predeclared attempts: 34 resolved scenarios and four correct unsupported all-bypass rejections. All seven gates pass against separate Radau/BDF integration and analytic RC controls. The worst voltage discrepancy is approximately 0.000001512% of healthy crest. This quantifies numerical agreement with the declared equations; it does not quantify agreement with real equipment.

Initial verification found four zero-inductance tail-chop crest metrics that disagreed with their correct exported curves. The original failures remain saved, along with the unchanged-protocol rerun and the implementation corrections. Later non-numerical energy-scope and nominal-efficiency wording changes are disclosed separately.

The final full backend suite passes 438 tests, including 32 focused API/feature tests and 42 independent physics regressions. The production frontend builds, all 27 unit tests and 17 isolated browser interaction/layout checks pass. Original source/data/model preservation and fresh-database external-network-denied smoke pass. Tests use generated data; physical measurements, device-specific behavior and real laboratory safety remain outside these checks.
