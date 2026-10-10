"""Check that a displayed waveform, its reported metrics and compliance agree.

Every waveform the application plots is re-analysed here with the same
interpolation analyser used for uploaded captures. The result records what the
curve is, which metrics are reported beside it and how far the metrics extracted
from the exact plotted samples differ from them.
"""
from .compliance import check
from .waveform_metrics import analyze

VERSION = 'waveform-metric-consistency-v1'
KEYS = ('front_us', 'tail_us', 'crest_kv')

# Documented numerical tolerances for re-extraction from plotted samples. They
# cover interpolation between samples and root-finding tolerance, not physics.
TOLERANCE = {'front_us': 0.005, 'tail_us': 0.005, 'crest_kv': 0.001}

KINDS = {
    'equivalent_circuit': ('Circuit prediction', 'simulated',
                           'Lumped Marx/RLC circuit solution for the recommended hardware settings.'),
    'metric_reconstruction': ('Shape reconstructed from predicted metrics', 'reconstruction',
                              'Double-exponential curve drawn through three predicted metrics. '
                              'It is not an independently simulated or predicted physical waveform.'),
}


def describe(wave):
    label, origin, meaning = KINDS.get((wave or {}).get('kind'), ('Waveform', 'unknown', 'Unclassified curve.'))
    return {'kind': (wave or {}).get('kind'), 'label': label, 'origin': origin, 'meaning': meaning}


def extract(wave, impulse_type):
    """Metrics from the exact samples that are plotted."""
    measured = analyze(wave['time_us'], wave['voltage_kv'], impulse_type)
    return {k: float(measured[k]) for k in KEYS}


def compare(curve_metrics, reported, impulse_type, test_kv):
    rows = {}
    for key in KEYS:
        value, shown = curve_metrics[key], float(reported[key])
        relative = abs(value - shown) / max(abs(shown), 1e-12)
        rows[key] = {'reported': shown, 'from_curve': value, 'relative_difference': relative,
                     'tolerance': TOLERANCE[key], 'within_tolerance': relative <= TOLERANCE[key]}
    same_decision = (check(impulse_type, test_kv, curve_metrics)['nominal_pass']
                     == check(impulse_type, test_kv, {k: float(reported[k]) for k in KEYS})['nominal_pass'])
    return rows, same_decision


def waveform_consistency(candidate, impulse_type, test_kv):
    """Consistency record for the primary curve and the circuit cross-check."""
    wave = candidate.get('waveform')
    reported = candidate.get('hybrid') or {}
    corrected = bool(candidate.get('calibration'))
    record = {'version': VERSION, 'tolerance': TOLERANCE,
              'method': 'Metrics re-extracted from the plotted samples with the same interpolation analyser '
                        'used for uploaded captures, then compared with the metrics shown beside the curve.'}
    if not wave:
        return {**record, 'primary': None, 'consistent': False,
                'note': 'No waveform could be drawn for this candidate; its metrics are not shown as a curve.'}
    primary = describe(wave)
    try:
        curve_metrics = extract(wave, impulse_type)
    except ValueError as exc:
        return {**record, 'primary': {**primary, 'error': str(exc)}, 'consistent': False,
                'note': 'The plotted samples could not be analysed; treat the metrics as unverified.'}
    if corrected and wave.get('kind') == 'equivalent_circuit':
        # A local calibration shifts the reported metrics, but the circuit curve is
        # not corrected. Compare the curve with the uncorrected circuit metrics and
        # say so, rather than drawing corrected numbers beside an uncorrected curve.
        rows, same = compare(curve_metrics, candidate['physics'], impulse_type, test_kv)
        relationship = 'locally_corrected_metrics_shown_separately'
        note = ('The curve is the uncorrected circuit prediction. The locally corrected metrics are listed '
                'separately and are not drawn as a waveform.')
    else:
        rows, same = compare(curve_metrics, reported, impulse_type, test_kv)
        relationship = 'curve_matches_reported_metrics'
        note = ('Reported metrics are re-extracted from the plotted circuit samples.'
                if wave.get('kind') == 'equivalent_circuit' else
                'The reconstructed shape reproduces the reported metrics; it carries no extra physical information.')
    consistent = all(r['within_tolerance'] for r in rows.values()) and same
    result = {**record, 'primary': {**primary, 'metrics': rows, 'same_compliance_decision': same},
              'relationship': relationship, 'consistent': consistent, 'note': note}
    cross = candidate.get('circuit_crosscheck')
    if cross and cross.get('waveform'):
        try:
            cross_rows, cross_same = compare(extract(cross['waveform'], impulse_type), cross, impulse_type, test_kv)
            result['circuit_crosscheck'] = {**describe(cross['waveform']), 'metrics': cross_rows,
                                            'same_compliance_decision': cross_same}
            result['consistent'] = consistent and cross_same and all(r['within_tolerance'] for r in cross_rows.values())
        except ValueError as exc:
            result['circuit_crosscheck'] = {**describe(cross['waveform']), 'error': str(exc)}
            result['consistent'] = False
    return result
