"""Versioned reference snapshots: the setting a waveform is compared with.

A snapshot freezes everything the circuit prediction depends on. As-fired
settings are recorded separately and re-solved with the same solver; the
original recommendation is never silently used in their place.
"""
import hashlib
import json

from ..physics.circuit import simulate, VERSION as CIRCUIT_VERSION
from ..physics.waveform_metrics import waveform_from_metrics
from ..capture_admission import rating_flags, LABELS as SETTING_LABELS

SNAPSHOT_VERSION = 'diagnostic-reference-v1'
SETTING_KEYS = ('stages', 'charge_kv_stage', 'front_r_stage', 'tail_r_stage')
CIRCUIT_KEYS = ('load_c_pf', 'divider_c_pf', 'stray_c_pf', 'l_uh')
FIRED_KEYS = SETTING_KEYS + CIRCUIT_KEYS + ('efficiency',)
TOPOLOGY = ('Lumped series Marx equivalent: the erected generator capacitance C_stage/n is shunted by the total tail '
            'resistance n·R_tail and discharges through the total front resistance n·R_front and the connection '
            'inductance L into the load-side capacitance (test object + divider + stray, plus the 545 pF base '
            'capacitance when included). One factor scales the erected voltage n·charge.')
OPEN_QUESTIONS = [
    {'id': 'loss_factor', 'title': 'Meaning of the loss factor',
     'text': 'The efficiency input multiplies the erected voltage once. Whether the stated value (for example 0.83) is an '
             'extra spark/connection loss on top of the circuit\'s own voltage utilisation, or the overall efficiency, is '
             'not settled. It moves the predicted crest directly.'},
    {'id': 'base_capacitance', 'title': '545 pF base capacitance',
     'text': 'Whether the 545 pF basic capacitance is already inside the divider or stray capacitance is not settled. '
             'Counting it twice or not at all moves the Lightning front by tens of percent.'},
    {'id': 'resistor_connection', 'title': 'How the resistors are connected',
     'text': 'The model places the whole tail resistance across the generator capacitance and the front resistance in '
             'series. Tail resistors partly at the load side, or charging resistors conducting during the pulse, are '
             'other topologies the lumped model does not represent.'},
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def total_capacitance(profile, inputs, circuit):
    base = (profile.get('base_c_pf') or 0) if inputs.get('include_base_c') else 0
    return circuit['load_c_pf'] + circuit['divider_c_pf'] + circuit['stray_c_pf'] + base


def circuit_args(snapshot, settings=None, circuit=None, efficiency=None):
    """Arguments of the existing solver for this snapshot (fitted generator parameters included)."""
    s = settings or snapshot['settings']
    c = circuit or snapshot['circuit_inputs']
    fitted = snapshot.get('effective_parameters') or {}
    total = total_capacitance(snapshot['profile'], snapshot['inputs'], c) + fitted.get('extra_load_pf', 0.)
    eta = (snapshot['efficiency'] if efficiency is None else efficiency) * fitted.get('loss_scale', 1.)
    return dict(stages=int(s['stages']), charge_kv_stage=float(s['charge_kv_stage']),
                front_r_stage=float(s['front_r_stage']) * fitted.get('front_scale', 1.),
                tail_r_stage=float(s['tail_r_stage']) * fitted.get('tail_scale', 1.),
                stage_c_uf=float(snapshot['profile']['stage_c_uf']), total_c_pf=float(total),
                l_uh=float(c['l_uh']) + fitted.get('extra_l_uh', 0.), efficiency=float(eta))


def solve(snapshot, settings=None, circuit=None, efficiency=None):
    args = circuit_args(snapshot, settings, circuit, efficiency)
    result = simulate(*args.values(), snapshot['impulse_type'], True)
    return {'metrics': {k: result[k] for k in ('front_us', 'tail_us', 'crest_kv')},
            'waveform': {'time_us': result['waveform']['time_us'], 'voltage_kv': result['waveform']['voltage_kv']},
            'circuit_args': args, 'model': result['diagnostics']['model'],
            'damping_ratio': result['diagnostics']['damping_ratio']}


def target_shape(impulse_type, rules, test_kv):
    rule = rules[impulse_type]
    wave = waveform_from_metrics(rule['front_target_us'], rule['tail_target_us'], test_kv, impulse_type)
    return {'label': 'Illustrative target shape', 'kind': 'target_illustration',
            'metrics': {'front_us': rule['front_target_us'], 'tail_us': rule['tail_target_us'], 'crest_kv': test_kv},
            'time_us': wave['time_us'], 'voltage_kv': wave['voltage_kv'],
            'note': 'Double-exponential shape drawn through the challenge target values. It illustrates the target; it is '
                    'not a prediction and is never used for diagnosis.'}


def snapshot_from_run(run, candidate_id=''):
    candidates = run.get('candidates') or []
    candidate = next((c for c in candidates if c['id'] == candidate_id), None) if candidate_id else (candidates[0] if candidates else None)
    if candidate is None:
        raise ValueError('The selected candidate does not belong to this saved run.')
    inputs = run['inputs']
    profile = run['profile']
    if not profile.get('stage_c_uf'):
        raise ValueError('The saved profile has no stage capacitance, so no circuit prediction can be made.')
    settings = {k: candidate['settings'][k] for k in SETTING_KEYS}
    circuit = {k: inputs[k] for k in CIRCUIT_KEYS}
    snap = {
        'snapshot_version': SNAPSHOT_VERSION, 'run_id': run['id'], 'candidate_id': candidate['id'],
        'rank': candidate.get('rank'), 'run_created_at': run.get('created_at'),
        'profile': profile, 'profile_label': profile.get('name'),
        'inputs': {k: inputs.get(k) for k in ('profile_id', 'impulse_type', 'test_kv', 'layout_id', 'solver',
                                               'include_base_c', 'parameter_calibration_id', 'calibration_id')},
        'impulse_type': inputs['impulse_type'], 'test_kv': inputs['test_kv'],
        'settings': settings, 'circuit_inputs': circuit, 'efficiency': inputs['efficiency'],
        'networks': {k: {'topology': (candidate.get(k) or {}).get('topology'),
                         'equivalent_ohm': (candidate.get(k) or {}).get('equivalent_ohm')} for k in ('front_network', 'tail_network')},
        'base_c_pf': profile.get('base_c_pf') or 0, 'include_base_c': bool(inputs.get('include_base_c')),
        'total_c_pf': total_capacitance(profile, inputs, circuit),
        'loss_factor': {'value': inputs['efficiency'],
                        'meaning': 'One voltage factor applied to the erected voltage n × charge; it stands for assumed '
                                   'spark-gap and connection loss. See the open question on its meaning.'},
        'effective_parameters': profile.get('effective_parameters'),
        'topology': TOPOLOGY, 'physics_version': CIRCUIT_VERSION, 'rules': run.get('rules'),
        'rules_version': (run.get('rules') or {}).get('version'), 'open_questions': OPEN_QUESTIONS,
        'saved_prediction': {'label': 'Saved recommendation prediction', 'metrics': candidate.get('hybrid'),
                             'solver': inputs.get('solver')},
    }
    snap['prediction'] = {'label': 'Circuit prediction', 'settings_basis': 'recommended', **solve(snap)}
    snap['target'] = target_shape(snap['impulse_type'], snap['rules'], snap['test_kv'])
    snap['solver_note'] = (None if inputs.get('solver') == 'circuit' else
                           'The saved recommendation used the workbook reference equations. Diagnostics use the equivalent '
                           'circuit, the only model here that produces a waveform; its values can differ from the saved ones.')
    snap['sha256'] = digest({k: snap[k] for k in ('run_id', 'candidate_id', 'settings', 'circuit_inputs', 'efficiency',
                                                  'profile', 'physics_version', 'effective_parameters')})
    return snap


def as_fired(snapshot, declared, uncertain=()):
    """Record the settings actually fired and re-solve the same circuit for them.

    ``declared`` holds only fields the operator entered; others keep the
    recommended value and are marked as assumed-unchanged.
    """
    unknown = sorted(set(declared) - set(FIRED_KEYS))
    if unknown:
        raise ValueError(f"Unknown as-fired fields: {', '.join(unknown)}.")
    bad = sorted(set(uncertain) - set(FIRED_KEYS))
    if bad:
        raise ValueError(f"Unknown uncertain fields: {', '.join(bad)}.")
    settings = {k: declared.get(k, snapshot['settings'][k]) for k in SETTING_KEYS}
    circuit = {k: declared.get(k, snapshot['circuit_inputs'][k]) for k in CIRCUIT_KEYS}
    efficiency = declared.get('efficiency', snapshot['efficiency'])
    if type(settings['stages']) is not int and not float(settings['stages']).is_integer():
        raise ValueError('Active stages must be a whole number.')
    settings['stages'] = int(settings['stages'])
    p = snapshot['profile']
    if not p['min_stages'] <= settings['stages'] <= p['max_stages']:
        raise ValueError(f"{settings['stages']} active stages is outside this generator ({p['min_stages']}–{p['max_stages']}); "
                         'a generator cannot fire more stages than it has.')
    values = [settings['charge_kv_stage'], settings['front_r_stage'], settings['tail_r_stage'], circuit['load_c_pf'], efficiency]
    if any(not isinstance(v, (int, float)) or v != v or v <= 0 for v in values) or \
            min(circuit['divider_c_pf'], circuit['stray_c_pf'], circuit['l_uh']) < 0 or efficiency > 1:
        raise ValueError('As-fired values must be finite and positive (capacitances and inductance may be zero; efficiency at most 1).')
    solved = solve(snapshot, settings, circuit, efficiency)
    differences = []
    for key in FIRED_KEYS:
        before = snapshot['settings'].get(key, snapshot['circuit_inputs'].get(key, snapshot['efficiency'] if key == 'efficiency' else None))
        after = settings.get(key, circuit.get(key, efficiency if key == 'efficiency' else None))
        if abs(float(after) - float(before)) > 1e-9 * max(abs(float(before)), 1e-12):
            differences.append({'field': key, 'label': SETTING_LABELS.get(key, 'loss factor'), 'recommended': before, 'fired': after})
    return {'declared_fields': sorted(declared), 'uncertain_fields': sorted(set(uncertain)),
            'assumed_unchanged': sorted(set(FIRED_KEYS) - set(declared)),
            'settings': settings, 'circuit_inputs': circuit, 'efficiency': efficiency,
            'differences': differences, 'rating_flags': rating_flags(p, settings),
            'prediction': {'label': 'Circuit prediction at the as-fired settings', 'settings_basis': 'as_fired', **solved},
            'note': 'Same solver and assumptions re-solved at the settings actually fired. No measured information enters it.'}
