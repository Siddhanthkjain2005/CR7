"""Findings for qualified laboratory staff, generated from the fitted simulations.

Every number here comes from re-solving the circuit with the fitted effective
values; the wording only names what was simulated. No component is declared
faulty: a finding says what is consistent with the recording and how to check it.
"""
from ..physics.compliance import check
from .inverse import model_metrics, CATEGORIES, parameter_space

SAFETY = ('Checks are for qualified high-voltage laboratory staff only, with the generator de-energised, discharged, '
          'earthed and isolated under the laboratory\'s own procedures.')
KEYS = ('front_us', 'tail_us', 'crest_kv')
NAMES = {'front_us': 'front time', 'tail_us': 'time to half-value', 'crest_kv': 'crest voltage'}

# What a qualified person can measure to confirm or rule out each quantity, and
# which value to compare with. Values are filled from the fit.
VERIFY = {
    'front_factor': ('Measure the total front resistance of the active stages (low-voltage resistance bridge across the '
                     'front resistor chain, generator de-energised) and compare it with {nominal}. This fit corresponds to '
                     'about {effective}.'),
    'tail_factor': ('Measure the total tail (discharge) resistance of the active stages and check for parallel discharge '
                    'paths such as charging resistors. Nominal {nominal}; this fit corresponds to about {effective}.'),
    'extra_load_pf': ('Measure the load-side capacitance (test object, divider and connections) with a capacitance bridge and '
                      'confirm whether the 545 pF base capacitance is already inside the divider value. Declared {nominal}; '
                      'this fit corresponds to about {effective}.'),
    'inductance_uh': ('Review the connection layout (lead length, loop area, earth return). An inductance of about '
                      '{effective} versus the declared {nominal} would follow from a longer or wider loop.'),
    'charge_factor': ('Check the charging-voltage record of this shot (charging unit reading or log). This fit corresponds '
                      'to about {effective} per stage versus {nominal} recorded.'),
    'efficiency_factor': ('Settle what the loss factor means (extra spark/connection loss or overall efficiency). This fit '
                          'corresponds to an effective factor of {effective} versus {nominal} assumed.'),
    'gain': ('Check the divider ratio and recorder scale against the divider calibration certificate, for example with a '
             'reference measurement at low voltage. This fit corresponds to a scale {effective} of the declared one.'),
    'time_shift_us': ('Check the trigger position and the time origin entered for this recording. This fit corresponds to '
                      'a {effective} offset.'),
    'baseline_kv': ('Check the recorder baseline (offset before the impulse). This fit corresponds to {effective}.'),
    'stages': ('Check the shot log and the gap settings for how many stages fired. This fit corresponds to {effective} '
               'instead of {nominal}.'),
}


def _fmt(value, unit):
    if unit == '×':
        return f'{value:.3g}×'
    return f'{value:.4g} {unit}'


def nominal_effective(name, value, base):
    """Nominal and effective physical values of one fitted quantity."""
    n = base['stages']
    if name == 'front_factor':
        nominal = base['front_r_stage'] * n
        return f'{nominal:.4g} Ω total ({base["front_r_stage"]:.4g} Ω per stage × {n})', f'{nominal * value:.4g} Ω total ({value:.3g}× nominal)'
    if name == 'tail_factor':
        nominal = base['tail_r_stage'] * n
        return f'{nominal:.4g} Ω total ({base["tail_r_stage"]:.4g} Ω per stage × {n})', f'{nominal * value:.4g} Ω total ({value:.3g}× nominal)'
    if name == 'extra_load_pf':
        return f'{base["total_c_pf"]:.4g} pF', f'{base["total_c_pf"] + value:.4g} pF ({value:+.4g} pF)'
    if name == 'inductance_uh':
        return f'{base["l_uh"]:.4g} µH', f'{value:.4g} µH'
    if name == 'charge_factor':
        return f'{base["charge_kv_stage"]:.4g} kV', f'{base["charge_kv_stage"] * value:.4g} kV ({value:.3g}×)'
    if name == 'efficiency_factor':
        return f'{base["efficiency"]:.3g}', f'{base["efficiency"] * value:.3g} ({value:.3g}×)'
    if name == 'gain':
        return '1×', f'{value:.3g}×'
    if name == 'time_shift_us':
        return '0 µs', f'{value:+.3g} µs'
    if name == 'baseline_kv':
        return '0 kV', f'{value:+.3g} kV'
    if name == 'stages':
        return f'{n} stages', f'{int(value)} stages'
    return '', ''


def _limits(impulse_type, test_kv, metrics):
    try:
        result = check(impulse_type, test_kv, metrics)
        return {'nominal_pass': result['nominal_pass'], 'rows': [{'name': r['name'], 'pass': r['pass']} for r in result['rows']]}
    except (KeyError, ValueError, TypeError):
        return None


def finding(hypothesis, base, comparison, investigation, snapshot):
    """Plain-language finding for one fitted hypothesis, from simulations."""
    impulse = snapshot['impulse_type']
    params = {k: v for k, v in hypothesis['parameters'].items() if k != 'stages'}
    stages = hypothesis.get('stages')
    fitted_metrics, _ = model_metrics(base, params, impulse, stages)
    observed = comparison.get('observed_metrics') or {}
    predicted = comparison['predicted_metrics']
    supporting, contradicting = [], []
    for key in KEYS:
        if key not in observed or observed.get(key) is None:
            continue
        row = next((r for r in comparison['metrics'] if r['metric'] == key), {})
        if row.get('status') not in ('Compared', 'Approximate'):
            continue
        before = abs(predicted[key] - observed[key]); after = abs(fitted_metrics[key] - observed[key])
        text = (f'{NAMES[key].capitalize()}: recorded {observed[key]:.4g}, circuit prediction {predicted[key]:.4g}, '
                f'with this explanation {fitted_metrics[key]:.4g}.')
        if after < before * .7 and before > 1e-9:
            supporting.append(text)
        elif after > before * 1.1 + 1e-9:
            contradicting.append(text + ' This explanation moves it further from the recording.')
    per = hypothesis.get('by_region') or {}
    for region, value in per.items():
        if value is not None and value > 2.5:
            contradicting.append(f'A clear difference remains in the {region} region (normalized mismatch {value:.2g}).')
    ident = hypothesis.get('identifiability') or {}
    ambiguity = []
    for other in hypothesis.get('indistinguishable_from') or []:
        o = next(h for h in investigation['hypotheses'] if h['id'] == other)
        ambiguity.append(f'{o["title"]} produces the same curve; this recording cannot tell them apart.')
    if ident.get('trade_off'):
        ambiguity.append('The two fitted quantities trade off against each other (correlation '
                         f'{ident.get("correlation", 0):.2f}); only their combined effect is determined.')
    for name in ident.get('at_bound') or []:
        ambiguity.append(f'{parameter_space(base, predicted, impulse)[name][0]} is at the edge of its allowed range; '
                         'the true value may lie further out or the explanation may be wrong.')
    if ident.get('poorly_determined'):
        ambiguity.append('Some fitted values are poorly determined: ' + ', '.join(ident['poorly_determined']) + '.')
    if ident.get('multiple_good_fits'):
        ambiguity.append('Different starting points led to different good fits.')
    if hypothesis.get('id') in ('effective_capacitance', 'capacitance_and_inductance', 'front_and_capacitance'):
        ambiguity.append('Capacitance is identified only as the effective load-side total, not per component.')
    if hypothesis.get('id') in ('front_network', 'tail_network', 'front_and_tail'):
        ambiguity.append('The fit describes the whole resistor network of the active stages, not any individual stage resistor.')
    names = hypothesis['parameter_names']
    values = []
    checks = []
    space = parameter_space(base, predicted, impulse)
    for name in names:
        value = hypothesis['parameters'][name]
        nominal, effective = nominal_effective(name, value, base)
        values.append({'quantity': space[name][0] if name in space else 'Active stages', 'nominal': nominal, 'effective': effective})
        checks.append(VERIFY[name].format(nominal=nominal, effective=effective))
    # Predicted effect at the recommended setting if this explanation is confirmed (hardware/model only).
    effect = None
    if hypothesis['category'] in ('hardware', 'model'):
        rec = snapshot['settings']
        rec_base = {**base, 'stages': rec['stages'], 'charge_kv_stage': rec['charge_kv_stage'],
                    'front_r_stage': rec['front_r_stage'], 'tail_r_stage': rec['tail_r_stage']}
        hw = {k: v for k, v in params.items() if k in ('front_factor', 'tail_factor', 'extra_load_pf', 'inductance_uh', 'efficiency_factor')}
        try:
            confirmed, _ = model_metrics(rec_base, hw, impulse)
            nominal_rec, _ = model_metrics(rec_base, {}, impulse)
            effect = {'setting': 'recommended setting', 'metrics_if_confirmed': confirmed, 'metrics_as_predicted': nominal_rec,
                      'limits_if_confirmed': _limits(impulse, snapshot['test_kv'], confirmed),
                      'note': 'Simulated with the fitted effective values at the recommended setting. Hypothetical until the '
                              'check above confirms the explanation.'}
        except ValueError:
            effect = None
    plain = {
        'hardware': 'The recording is reproduced when the circuit is solved with {what}. Nothing else in the circuit was changed.',
        'configuration': 'The recording is reproduced when the shot is solved with {what}: the shot may not have been fired '
                         'as recorded.',
        'measurement': 'The recording is reproduced when the measurement is assumed to have {what}; the generator itself '
                       'may be behaving as predicted.',
        'model': 'The recording is reproduced when the model assumption is changed to {what}; this is a question about the '
                 'model\'s convention, not a hardware fault.',
    }[hypothesis['category']].format(what=' and '.join(f"{v['quantity'].lower()} {v['effective']}" for v in values))
    return {'hypothesis_id': hypothesis['id'], 'title': hypothesis['title'], 'status': hypothesis['status'],
            'category': CATEGORIES[hypothesis['category']], 'component_group': hypothesis['group'],
            'explanation': plain, 'supporting_evidence': supporting, 'contradicting_evidence': contradicting,
            'values': values, 'fit': {'mismatch_before': investigation['baseline_mismatch'], 'mismatch_after': hypothesis['mismatch'],
                                      'improvement_pct': hypothesis.get('improvement_pct'), 'free_parameters': hypothesis['free_parameters']},
            'ambiguity': ambiguity, 'verification': checks, 'safety': SAFETY,
            'fitted_metrics': fitted_metrics, 'predicted_effect_if_confirmed': effect,
            'additional_measurement_needed': hypothesis.get('needs_more_measurement', False),
            'not_a_fault_statement': 'Consistency with one recording does not show that a component is faulty.'}


def findings(investigation, base, comparison, snapshot, limit=6):
    """Findings for the leading and other consistent explanations, best first."""
    baseline = next(h for h in investigation['hypotheses'] if h['id'] == 'baseline')
    investigation['baseline_mismatch'] = baseline['mismatch']
    order = {hid: i for i, hid in enumerate(investigation['ranking'])}
    chosen = [h for h in investigation['hypotheses'] if h.get('status') in ('Possible cause', 'Several explanations fit', 'Consistent with this waveform')
              and h['id'] != 'baseline']
    chosen.sort(key=lambda h: order.get(h['id'], 99))
    return [finding(h, base, comparison, investigation, snapshot) for h in chosen[:limit]]


EXPLORE_MAP = {'front_factor': 'front_scale', 'tail_factor': 'tail_scale', 'extra_load_pf': 'extra_load_pf',
               'efficiency_factor': 'loss_scale', 'inductance_uh': 'extra_l_uh'}


def hypothetical_parameters(hypothesis, base):
    """Effective generator parameters for exploring a corrected configuration, or a reason why not."""
    if hypothesis['category'] in ('configuration', 'measurement'):
        return None, ('This explanation is about how the shot was fired or measured, not about the generator, so there is '
                      'no corrected generator configuration to explore. Re-fire at the intended settings or correct the measurement.')
    out = {}
    for name, value in hypothesis['parameters'].items():
        key = EXPLORE_MAP.get(name)
        if key is None:
            continue
        out[key] = value - base['l_uh'] if name == 'inductance_uh' else value
    return out, None
