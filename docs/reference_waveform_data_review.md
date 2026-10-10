# Independent waveform reference data review

Reviewed 7 October 2026. This review concerns waveform extraction and acquisition admission. It does not provide new component-setting training rows, rescore the exposed challenge test, or establish six-output model accuracy.

## Retrieved public metrology records

The [VTT/PTB cable-effects dataset, DOI 10.5281/zenodo.6340016](https://zenodo.org/records/6340016) is a primary deposit by Jussi Havunen, Stephan Passon, Jari Hällström, Johann Meisner and Tim Christoph Schlüterbusch. The preserved API metadata states publication date 9 March 2022, open access and **CC BY 4.0**. Cite these creators, the dataset title, DOI, and the license when redistributing or adapting it.

Files are saved without alteration in `data/external/metrology/zenodo_6340016/`. The downloaded workbook is 1,585,194 bytes. Its MD5 matches the repository checksum `62b08bf71bd6af952b5c7b8c16a68fde`. Its complete SHA-256 is recorded in the adjacent manifest.

Read-only inspection found three sheets, `50ohm_16meter`, `1Mohm_16meter` and `50ohm_1.5meter`, each containing 22,000 paired numeric samples. The first column increments by 5 ns from zero to 109.995 µs. The second column contains approximately −0.45 V or −0.9 V plateaus. The [associated VTT paper](https://cris.vtt.fi/ws/files/82593647/Empirical_Characterization_of_Cable_Effects_on_a_Reference_Lightning_Impulse_Voltage_Divider.pdf) describes falling-step divider measurements, with these output-voltage scales. These are **measured step responses**, not complete lightning or switching impulses. The metadata's figure numbering belongs to its publication version and must not be used to assert that a final-paper figure is an independent parameter label.

Consequently, these records can test admission of an inappropriate capture or characterize measurement response. They cannot supply front/tail/crest ground truth for an impulse regressor. A voltage-divider scale factor, component setting and certified impulse-reference parameters are not supplied for these three sheets. The input unit conversion used for inspection is seconds to microseconds and volts to kilovolts; it does not recover generator voltage.

## Independently observed admission weakness

Inspection of the unmodified current analyzer and acquisition review on 7 October produced the following results with zero supplied baseline:

| Measured step-response sheet | Extracted front (µs) | Extracted tail (µs) | Falling half crossing (µs) | Current acquisition admission |
| --- | ---: | ---: | ---: | --- |
| 50ohm_16meter | 0.036729 | 104.513685 | 109.982267 | Usable, calibration allowed |
| 1Mohm_16meter | 0.036709 | 104.516552 | 109.982251 | Usable, calibration allowed |
| 50ohm_1.5meter | 0.015905 | 104.506551 | 109.982124 | Rejected for sparse rising limb |

The first two records have an apparent half crossing only about 13 ns before the capture ends. Their long plateaus and final record discontinuity do not constitute the falling limb of a complete LI/SI waveform. Adequate acquired samples around a local peak are insufficient to establish a suitable impulse record. This observation motivates a separate admission regression for an unresolved falling limb or record-end transition. It does **not** justify rejecting all noisy records using the analyzer's local-maxima count, nor changing nominal challenge compliance tolerances. Any such correction needs both suitable impulse and unsuitable-step regression fixtures and a documented application heuristic.

This is source-admission evidence. It is not a measured prediction-error benchmark, a reference extractor certification, or a laboratory calibration.

## Other trusted sources reviewed

| Source | What it supports | Data availability and limit |
| --- | --- | --- |
| [IEC 61083-2:2013](https://webstore.iec.ch/en/publication/4471) | Official software test waveforms, reference values, acceptance limits and TDG | The official product is sold. No licensed open TDG sample package was located in this bounded search. No purchase was made. Third-party software mirrors were excluded. |
| [PTB HV-com² workshop](https://www.ptb.de/empir2020/fileadmin/documents/empir-2020/HV-com2/documents/HV-com2_Workshop_WP1.pdf) | Metrology consortium collected real composite/combined records and compared evaluation software | The public presentation provides methods and illustrations; no public raw-sample download with reference labels was located. Those complex AC/DC combinations also exceed the app's current single-impulse scope. |
| [BIPM COOMET.EM-S21](https://www.bipm.org/kcdb/comparison?id=669) and [final report](https://www.bipm.org/documents/d/guest/coomet-em-s21) | Approved comparison of switching-impulse measuring systems; 250/2500 µs timing and amplitude comparison | Published comparison results are not a raw waveform corpus or input-setting prediction dataset. Do not treat instrument uncertainty as our model accuracy. |
| [NPL SupraEMI waveform library](https://empir.npl.co.uk/supraemi/waveform-library/) | Open power-quality/EMI waveform recordings | These are low-voltage grid EMI signals and unsuitable for labeling HV impulse-generator front/tail/crest outputs. |

## Definition compatibility

The [official IEC 60060-1:2025 description](https://webstore.iec.ch/en/publication/65088) states that the switching-impulse definition now uses a front time and describes 170/2500 µs. The challenge uses the historical 250 µs **time to peak** and 2500 µs tail. These parameters are different quantities. Preserve the challenge's supplied limits and labels. Do not silently replace them with the current standard's front-time definition when importing outside data.

Fresh generated analytic impulses can independently test interpolation, polarity, time/baseline offsets, sampling and admission when their expected quantities come from mathematical roots or prescribed vertices rather than the app's own metric reconstruction. Keep those records explicitly synthetic. They cannot be called new laboratory data or a held-out final challenge result.
