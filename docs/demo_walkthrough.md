# Five-minute demonstration

[← Documentation](README.md) · [Live demo](https://cr7-impulsetwin-730856d9.azurewebsites.net/)

Tell one connected story: request a waveform, inspect the hardware, explore a generated fault, compare a generated capture and export the record.

## Configure and recommend · 0:00–1:00

Choose **CPRI Lightning · matched example, assumed stock** and click **Recommend settings**. The request is **1,425 kV**; preset resistor quantities are assumptions, not confirmed laboratory stock.

Explain: “We enter the voltage, impulse type, capacitances and circuit assumptions. The system searches within the ratings and stock counts we declared.”

## Inspect the configuration · 1:00–1:45

Show the waveform, crest/timing, stages, charging voltage and resistor networks. The recorded matched example has approximately **11 stages**, **181.90 kV/stage**, **30 Ω front / 520 Ω tail per stage**, **1.187 µs front** and **53.744 µs tail** under its stated assumptions. Changed inputs can change these results.

Explain: “Charging voltage is solved to meet the nominal target crest. A real shot can differ because of losses, parasitics, triggering and the measuring system.”

Front time is not the instant of maximum voltage. Nominal pass, scenario results and physical evidence are different checks.

## Assemble digitally · 1:45–2:30

Click **Assemble digitally**. Place virtual groups, inspect the RLC values and review briefings. Use button/keyboard alternatives if needed.

Explain: “The conceptual twin makes this configuration easier to inspect. Reading a briefing does not authorize physical assembly or energization.”

Completion remains **Virtual review complete · physical authorization pending**.

## Explore generated faults · 2:30–3:30

Open **Fault test lab** on the saved candidate:

- **Front chop:** use illustrative defaults; interruption precedes the healthy peak.
- **Tail chop:** the healthy crest may remain unchanged because the event occurs after it.
- **Uncharged conducting stage:** retain the conducting stack while reducing a stage's initial charge.
- **Conductive bypass:** exclude a stage from the equivalent stack and recalculate its capacitance/resistance totals.

Explain: “Charge stays fixed, so the fault's change remains visible. We do not scale the output back to the target.”

Open-gap misfire/delayed erection are unsupported hypotheses. Chopped curves are not classified as standard full-wave compliance results.

## Compare a capture · 3:30–4:30

Open **Waveform Diagnostics** and use its labelled generated demonstration. Show the origin, reference/as-fired settings and plot-calibration controls. Raw CSV is preferred; photos need axis calibration and trace selection. Where required, use **Record and re-solve** before interpreting residuals.

Explain: “We compare against the prediction at the settings actually fired. Inverse analysis can rank possible explanations; one graph cannot uniquely prove which physical component failed.”

Image-derived samples do not enter calibration or laboratory-accuracy evaluation. An autofilled timestamp is the device time, remains editable and does not prove the capture time.

## Export and conclude · 4:30–5:00

Show exports, saved history and evidence views. The [pitch deck](https://github.com/Siddhanthkjain2005/CR7/blob/codex/assembly-twin/presentations/CR7_ImpulseTwin_AI_Vertical_Architecture.pptx) provides the architecture and team introduction.

Explain: “ImpulseTwin connects configuration search, inspectable physics, visual hardware understanding and capture feedback. Software/numerical checks are recorded. Independent measurements on the real generator are needed to establish laboratory accuracy.”

## Rehearsal

Start the app in advance, prepare a saved example and keep the local installation as a fallback. Use generated files on the shared demo. Keep prediction-basis, stock, conceptual-twin and generated-data labels visible so the result can be interpreted correctly.
