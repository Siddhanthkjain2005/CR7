"""Constant-coefficient, passive lumped fault circuits with an exact event handover.

The healthy circuit is the existing solver, at the *saved charging voltage*.
Chopping connects an assumed series R/L shunt across the load capacitor. It does
not clip voltage samples or renormalize a waveform to a requested crest.

State coordinates after the event are energy-normalized voltages, in kV:
    vg, sqrt(Cl/Cg)*vl, sqrt(L/Cg)*i_series, sqrt(Ls/Cg)*i_shunt
Currents in that expression are in kA. Zero-L branches are eliminated using
Ohm's law. This improves conditioning without changing Kirchhoff equations.
"""
from copy import deepcopy
import math

import numpy as np
from scipy.linalg import eig, expm, solve_continuous_lyapunov
from scipy.optimize import brentq

from ..diagnostics.reference import circuit_args
from ..physics import circuit
from . import VERSION
from .models import ChoppedImpulse, StageFailure

ASSUMPTIONS = [
    'Generated hypothetical experiment; no measured waveform or laboratory fault validation.',
    'Saved recommended charge is held fixed. No target matching or optimization is performed in the fault experiment.',
    'Lumped series Marx equivalent: Cg = Cstage / active stages, total front and tail resistance = stages × per-stage value.',
    'The loss factor multiplies the erected source voltage once, as in the existing circuit model.',
]
LIMITATIONS = [
    'Spark-gap delay, arc voltage, distributed capacitance, electromagnetic fields and location-dependent stage faults are not modeled.',
    'These simulations do not establish IEC chopped-impulse compliance or real CPRI accuracy.',
    'Predicted current, reversal and energy are conditional on assumed R/L values; no component pulse rating or safe-to-fire decision is supplied.',
    'Physical experiments require authorized qualified personnel and the laboratory’s approved procedures, barriers, interlocks and stored-energy controls.',
]
METRIC_KEYS = ('front_us', 'tail_us', 'crest_kv', 'peak_time_us')


def _finite_scalar(value, name, low, high, inclusive_low=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'The saved {name} is unknown or non-finite; no fault result is returned.')
    if (value < low if inclusive_low else value <= low) or value > high:
        raise ValueError(f'The saved {name} is outside this fault solver’s bounded physical range.')
    return float(value)


def validate_snapshot(snapshot):
    """Unknown topology and capacitance are not silently replaced by assumptions."""
    if snapshot.get('inputs', {}).get('connection_mode') != 'series_marx_equivalent':
        raise ValueError('Fault tests require an explicitly saved series_marx_equivalent connection mode. An unknown or open spark-gap chain is unsupported.')
    p = snapshot.get('profile') or {}
    if snapshot.get('inputs', {}).get('include_base_c') and p.get('base_c_pf') is None:
        raise ValueError('The included base capacitance is unknown. Record it before simulating a fault.')
    _finite_scalar(p.get('stage_c_uf'), 'stage capacitance', 0, 100)
    s = snapshot.get('settings') or {}
    n = s.get('stages')
    if type(n) is not int or not 2 <= n <= 30:
        raise ValueError('The saved active stage count must be a whole number from 2 to 30.')
    _finite_scalar(s.get('charge_kv_stage'), 'charging voltage', 0, 1000)
    _finite_scalar(s.get('front_r_stage'), 'front resistance', 0, 1e8)
    _finite_scalar(s.get('tail_r_stage'), 'tail resistance', 0, 1e8)
    for key in ('load_c_pf', 'divider_c_pf', 'stray_c_pf', 'l_uh'):
        _finite_scalar(snapshot.get('circuit_inputs', {}).get(key), key, 0, 100000 if key != 'l_uh' else 10000,
                       inclusive_low=key != 'load_c_pf')
    _finite_scalar(snapshot.get('efficiency'), 'loss factor', 0, 1)
    fitted = snapshot.get('effective_parameters') or {}
    known = {'loss_scale', 'extra_load_pf', 'tail_scale', 'front_scale', 'extra_l_uh',
             'calibration_id', 'shots', 'source_type', 'hypothetical'}
    if set(fitted) - known:
        raise ValueError('The saved fitted parameter model contains unsupported parameters. No parameters were silently dropped.')
    for k in set(fitted) & {'loss_scale', 'extra_load_pf', 'tail_scale', 'front_scale', 'extra_l_uh'}:
        if isinstance(fitted[k], bool) or not isinstance(fitted[k], (int, float)) or not math.isfinite(fitted[k]):
            raise ValueError('Saved effective parameters must be finite.')
    args = circuit_args(snapshot)
    for key, upper in [('stage_c_uf', 100), ('charge_kv_stage', 1000), ('front_r_stage', 1e8),
                       ('tail_r_stage', 1e8), ('total_c_pf', 500000), ('efficiency', 2)]:
        _finite_scalar(args[key], f'effective {key}', 0, upper)
    _finite_scalar(args['l_uh'], 'effective inductance', 0, 20000, inclusive_low=True)
    if snapshot.get('impulse_type') not in ('Lightning', 'Switching'):
        raise ValueError('The saved impulse type is unknown.')
    return args


def _healthy(args, impulse):
    result = circuit.simulate(**args, impulse_type=impulse, include_waveform=True)
    return result


def _reference(snapshot, args):
    return {
        'run_id': snapshot.get('run_id'), 'candidate_id': snapshot.get('candidate_id'),
        'inputs': deepcopy(snapshot['inputs']), 'settings': deepcopy(snapshot['settings']),
        'profile': deepcopy(snapshot['profile']), 'circuit_inputs': deepcopy(snapshot['circuit_inputs']),
        'snapshot_sha256': snapshot.get('sha256'), 'circuit_args': args,
        'effective_parameters': deepcopy(snapshot.get('effective_parameters')),
        'solver_note': (None if snapshot['inputs'].get('solver') == 'circuit' else
                        'The saved recommendation uses workbook/ML metrics. These fault experiments re-solve the physical circuit at the saved settings; the healthy crest may differ.'),
        'one_shot_metric_correction': ('Not applied: a one-shot metric correction does not define a physical circuit waveform.'
                                       if snapshot['inputs'].get('calibration_id') else None),
        'nominal_charge_kv_stage': snapshot['settings']['charge_kv_stage'],
        'nominal_efficiency': snapshot['efficiency'],
        'physics_version': snapshot.get('physics_version', circuit.VERSION),
    }


def _metrics(result, waveform=None, chopped=False):
    wave = waveform or result['waveform']
    values = np.asarray(wave['voltage_kv'])
    crest = result.get('crest_kv', 0.)
    minimum = float(min(0., np.min(values)))
    out = {k: result.get(k) for k in ('crest_kv', 'peak_time_us', 'front_us', 'tail_us', 't30_us', 't90_us', 't50_us', 'virtual_origin_us')}
    out.update(minimum_kv=minimum, reversal_pct=(100 * abs(minimum) / crest if crest > 0 else 0.),
               minimum_voltage_basis=('Resolved continuous extrema included in the published chopped waveform.' if chopped
                                      else 'Minimum of the published circuit samples; no continuous negative-peak refinement is claimed.'),
               definition=('Positive crest and geometric 30–90%/50% descriptors of the chopped circuit; these are not chopped-impulse standard acceptance metrics.'
                           if chopped else 'Existing circuit solver: Lightning virtual front and half-value tail; Switching time to peak and half-value time.'),
               front_tail_status=('Chopped waveform descriptors only; no full-wave or IEC compliance assessment.' if chopped else
                                  'No output: front and tail are undefined.' if crest == 0 else 'Resolved circuit descriptors.'))
    return out


def reference_view(snapshot):
    args = validate_snapshot(snapshot)
    healthy = _healthy(args, snapshot['impulse_type'])
    peak = healthy['peak_time_us']
    return {'version': VERSION, 'reference': _reference(snapshot, args),
            'healthy': {'metrics': _metrics(healthy), 'waveform': {**healthy['waveform'], 'label': 'Healthy circuit at saved charge'}},
            'defaults': {'front_chop_time_us': peak * .5, 'tail_chop_time_us': peak * 2,
                         'shunt_r_ohm': 10., 'shunt_l_uh': 1.},
            'limits': {'chop_time_max_us': min(100000., healthy['waveform']['time_us'][-1]),
                       'shunt_r_ohm': [0.5, 10000], 'shunt_l_uh': [0., 10000],
                       'stage_indices': [1, args['stages']]},
            'supported': {'chopped_impulse': snapshot['impulse_type'] == 'Lightning', 'stage_failure': True},
            'assumptions': ASSUMPTIONS, 'limitations': LIMITATIONS}


class _LinearResponse:
    """Stable constant system; exact matrix exponential with a checked modal fast path."""
    def __init__(self, matrix, initial):
        self.matrix = np.asarray(matrix, float)
        self.initial = np.asarray(initial, float)
        eigen, vectors = eig(self.matrix)
        if not np.isfinite(eigen).all() or not np.all(eigen.real < 0):
            raise ValueError('Could not resolve finite stable passive post-event modes. Review extreme circuit ratios.')
        self.eigen = eigen
        self.vectors = vectors
        self.condition = float(np.linalg.cond(vectors))
        av = self.matrix @ vectors
        dv = vectors * eigen
        denominator = np.abs(self.matrix) @ np.abs(vectors) + np.abs(dv)
        residual = np.max(np.abs(av - dv) / np.maximum(denominator, np.finfo(float).tiny))
        self.modal = self.condition < 1e6 and residual < 1e-10
        self.coefficients = np.linalg.solve(vectors, self.initial) if self.modal else None
        self.slow_seconds = 1 / min(-eigen.real)
        if max(-eigen.real) / min(-eigen.real) > 1e12:
            raise ValueError('Post-event circuit time constants exceed the verified numerical range; no result returned.')

    def states(self, times):
        t = np.asarray(times, float)
        if t.ndim == 0:
            if t == 0:
                return self.initial.copy()
            if self.modal:
                return np.real(self.vectors @ (self.coefficients * np.exp(self.eigen * t)))
            return expm(self.matrix * float(t)) @ self.initial
        if self.modal:
            states = np.real(self.vectors @ (self.coefficients[:, None] * np.exp(self.eigen[:, None] * t[None, :])))
            states[:, t == 0] = self.initial[:, None]
            return states
        return np.stack([expm(self.matrix * float(x)) @ self.initial for x in t], axis=1)


def _healthy_states(modes, times):
    t = np.asarray(times, float)
    if t.ndim == 0:
        return np.real(modes['vectors'] @ (modes['coefficients'] * np.exp(modes['eigen'] * t)))
    return np.real(modes['vectors'] @ (modes['coefficients'][:, None] * np.exp(modes['eigen'][:, None] * t[None, :])))


def _physical_state(modes, state, shunt_current_a=0):
    return {'generator_voltage_kv': float(state[0]), 'load_voltage_kv': float(state[modes['out_index']]),
            'series_current_a': (float(state[1] * 1000) if modes['use_inductance'] else
                                 float((state[0] - state[1]) / modes['rf'] * 1000)),
            'shunt_current_a': float(shunt_current_a)}


def _post_model(modes, event_state, shunt_r, shunt_l):
    cg, cl, rf, rt = (modes[k] for k in ('cg', 'cl', 'rf', 'rt'))
    load_scale = np.sqrt(cl / cg)
    use_l = modes['use_inductance']
    use_shunt_l = shunt_l > 0
    count = 2 + int(use_l) + int(use_shunt_l)
    matrix = np.zeros((count, count))
    matrix[0, 0] = -1 / (rt * cg)
    initial = np.zeros(count)
    initial[0] = event_state[0]
    initial[1] = event_state[modes['out_index']] * load_scale
    series_index = 2 if use_l else None
    shunt_index = 2 + int(use_l) if use_shunt_l else None
    if use_l:
        l = modes['l']
        matrix[0, series_index] = -1 / np.sqrt(l * cg)
        matrix[series_index, 0] = 1 / np.sqrt(l * cg)
        matrix[1, series_index] = 1 / np.sqrt(l * cl)
        matrix[series_index, 1] = -1 / np.sqrt(l * cl)
        matrix[series_index, series_index] = -rf / l
        initial[series_index] = event_state[1] * np.sqrt(l / cg)
    else:
        matrix[0, 0] -= 1 / (rf * cg)
        matrix[0, 1] = matrix[1, 0] = 1 / (rf * np.sqrt(cg * cl))
        matrix[1, 1] -= 1 / (rf * cl)
    if use_shunt_l:
        matrix[1, shunt_index] = -1 / np.sqrt(shunt_l * cl)
        matrix[shunt_index, 1] = 1 / np.sqrt(shunt_l * cl)
        matrix[shunt_index, shunt_index] = -shunt_r / shunt_l
    else:
        matrix[1, 1] -= 1 / (shunt_r * cl)
    response = _LinearResponse(matrix, initial)
    return response, load_scale, series_index, shunt_index


def _post_grid(response, end, shunt_r, shunt_l, cl):
    rates = np.abs(response.eigen)
    fast = 1 / max(rates)
    grid = np.unique(np.r_[0., np.geomspace(max(1e-15, fast * .001), end, 1600),
                           np.linspace(0, min(end, fast * 30), 400)])
    # Explicitly resolve oscillatory modes while their envelope is significant.
    for eigen in response.eigen:
        if abs(eigen.imag) > 0:
            duration = min(end, 24 / -eigen.real)
            step = 2 * np.pi / abs(eigen.imag) / 32
            required = int(np.ceil(duration / step)) + 1
            if required > 24000:
                raise ValueError('This assumed branch is too weakly damped for the bounded waveform sampler. Increase damping or narrow the scenario.')
            grid = np.union1d(grid, np.linspace(0, duration, max(2, required)))
    if len(grid) > 30000:
        raise ValueError('Post-event waveform exceeds the bounded sampler.')
    return grid


def _root(func, left, right):
    return brentq(func, float(left), float(right), xtol=max(np.finfo(float).tiny, min(1e-15, (right - left) * 1e-10)), rtol=1e-14)


def _extrema(grid, derivative):
    values = np.asarray([derivative(float(t)) for t in grid])
    indices = np.flatnonzero(values[:-1] * values[1:] < 0)
    roots = [_root(derivative, grid[i], grid[i + 1]) for i in indices]
    # An analytic crest can already be on the grid with exactly zero
    # derivative. A strict sign-change bracket would otherwise miss it.
    zeros = np.flatnonzero(values[1:-1] == 0) + 1
    roots += [float(grid[i]) for i in zeros if values[i - 1] * values[i + 1] < 0]
    return sorted(set(roots))


def _geometric_metrics(times, values, voltage, derivative, impulse, extrema_override=None):
    """Signed positive crest, continuous extrema, then exact threshold crossings."""
    grid = np.asarray(times)
    extrema = _extrema(grid, derivative) if extrema_override is None else extrema_override
    candidates = np.unique(np.r_[grid[0], grid[-1], extrema])
    candidate_values = np.asarray([voltage(float(t)) for t in candidates])
    peak = int(np.argmax(candidate_values))
    tp = float(candidates[peak])
    crest = float(candidate_values[peak])
    extra = list(extrema)
    if crest <= 0:
        return {'crest_kv': 0., 'peak_time_us': None, 'front_us': None, 'tail_us': None}, extra
    search = np.unique(np.r_[grid, candidates, tp])
    curve = np.asarray([voltage(float(t)) for t in search])
    peak_index = int(np.searchsorted(search, tp))
    def crossing(fraction, rising):
        a, b = ((0, peak_index) if rising else (peak_index, len(search) - 1))
        level = fraction * crest
        left = curve[a:b]; right = curve[a + 1:b + 1]
        match = ((left <= level) & (right >= level)) if rising else ((left >= level) & (right <= level))
        found = np.flatnonzero(match)
        if not len(found):
            return None
        i = int(found[0]) + a
        result = _root(lambda t: voltage(t) - level, search[i], search[i + 1])
        extra.append(result)
        return result * 1e6
    t30, t90, t50 = crossing(.3, True), crossing(.9, True), crossing(.5, False)
    virtual = t30 - .5 * (t90 - t30) if t30 is not None and t90 is not None else None
    result = {'crest_kv': crest, 'peak_time_us': tp * 1e6, 't30_us': t30, 't90_us': t90, 't50_us': t50,
              'virtual_origin_us': virtual,
              'front_us': 1.67 * (t90 - t30) if t30 is not None and t90 is not None else None,
              'tail_us': t50 - virtual if t50 is not None and virtual is not None else None}
    return result, extra


def _stored_energy(modes, state):
    vg = state[0]
    vl = state[modes['out_index']]
    energy = .5 * (modes['cg'] * vg ** 2 + modes['cl'] * vl ** 2) * 1e6
    if modes['use_inductance']:
        energy += .5 * modes['l'] * state[1] ** 2 * 1e6
    return float(energy)


def _quadratic_integral(response, q, end):
    """Integral z'Qz dt from the Lyapunov identity; no plot-grid quadrature."""
    p = solve_continuous_lyapunov(response.matrix.T, -q)
    z0 = response.initial
    ze = response.states(end)
    result = float(z0 @ p @ z0 - ze @ p @ ze)
    return max(0., result)


def _chopped(args, healthy, request):
    if request.chop_time_us > min(100000., healthy['waveform']['time_us'][-1]):
        raise ValueError('Chopping time is beyond the resolved healthy waveform. Choose a time within the reference range.')
    baseline_peak = healthy['peak_time_us']
    eps = max(1e-12, baseline_peak * 1e-9)
    if abs(request.chop_time_us - baseline_peak) <= eps:
        raise ValueError(f'The event is at the healthy crest ({baseline_peak:.9g} µs), neither a front nor tail chop. Move it away from the crest.')
    actual = 'front' if request.chop_time_us < baseline_peak else 'tail'
    if request.chop_mode != actual:
        raise ValueError(f'This time is on the {actual} of the healthy circuit (crest at {baseline_peak:.9g} µs). Select the matching mode or change the event time.')
    modes = circuit._modes(**args)
    tc = request.chop_time_us * 1e-6
    event_state = _healthy_states(modes, tc)
    rs = request.shunt_r_ohm
    ls = request.shunt_l_uh * 1e-6
    response, load_scale, series_index, shunt_index = _post_model(modes, event_state, rs, ls)
    end = 12 * response.slow_seconds
    if not math.isfinite(end) or end > 10:
        raise ValueError('The post-event decay is outside the bounded simulated time range.')
    post_times = _post_grid(response, end, rs, ls, modes['cl'])
    healthy_times = np.asarray(healthy['waveform']['time_us']) * 1e-6
    pre_times = np.unique(np.r_[healthy_times[healthy_times < tc], np.linspace(0, tc, 400)])
    times = np.unique(np.r_[pre_times, tc + post_times, tc])
    def voltage(t):
        return float(_healthy_states(modes, t)[modes['out_index']]) if t < tc else float(response.states(t - tc)[1] / load_scale)
    def derivative(t):
        if t < tc:
            states = _healthy_states(modes, t)
            current = states[1] if modes['use_inductance'] else (states[0] - states[1]) / modes['rf']
            return float(current / modes['cl'])
        return float((response.matrix @ response.states(t - tc))[1] / load_scale)
    values = np.asarray([voltage(t) for t in times])
    # Derivative is discontinuous for a resistive shunt. Split at the event,
    # include the event itself as a possible corner maximum or minimum.
    event_extrema = _extrema(pre_times, derivative) if len(pre_times) > 1 else []
    if baseline_peak * 1e-6 < tc:
        event_extrema.append(baseline_peak * 1e-6)
    event_extrema += [tc]
    event_extrema += [tc + t for t in _extrema(post_times, lambda t: float((response.matrix @ response.states(t))[1] / load_scale))]
    times = np.unique(np.r_[times, event_extrema])
    # The two derivative domains are separate. A resistive-switch corner is
    # an exact candidate, never a fictitious continuous derivative root.
    metrics, extra = _geometric_metrics(times, values, voltage, derivative, 'Lightning', event_extrema)
    points = np.unique(np.r_[times, extra, tc])
    values = np.asarray([voltage(t) for t in points])
    exported_times_us = points * 1e6
    # Keep the declared event timestamp exact in the exported grid. Unit
    # round-tripping can otherwise produce an adjacent floating-point value.
    exported_times_us[points == tc] = request.chop_time_us
    states = response.states(post_times)
    energy_ratios = np.sum(states ** 2, axis=0) / float(np.sum(response.initial ** 2))
    if float(np.max(energy_ratios)) > 1 + 1e-8 or float(max(0., np.max(np.diff(energy_ratios)))) > 1e-8:
        raise ValueError('The post-event solution did not preserve passive energy decay. No fault result returned.')
    power_scale = modes['cg'] * 1e6
    q_total = -(response.matrix + response.matrix.T) * .5 * power_scale
    q_shunt = np.zeros_like(response.matrix)
    if shunt_index is not None:
        q_shunt[shunt_index, shunt_index] = rs / ls * power_scale
        current = lambda t: float(response.states(t)[shunt_index] * np.sqrt(modes['cg'] / ls) * 1000)
        di_dt = lambda t: float((response.matrix @ response.states(t))[shunt_index] * np.sqrt(modes['cg'] / ls) * 1000 / 1e6)
        current_derivative = lambda t: float((response.matrix @ response.states(t))[shunt_index])
        second_derivative = lambda t: float((response.matrix @ response.matrix @ response.states(t))[shunt_index])
    else:
        q_shunt[1, 1] = power_scale / (rs * modes['cl'])
        current = lambda t: float(response.states(t)[1] / load_scale / rs * 1000)
        di_dt = lambda t: float((response.matrix @ response.states(t))[1] / load_scale / rs * 1000 / 1e6)
        current_derivative = lambda t: float((response.matrix @ response.states(t))[1])
        second_derivative = lambda t: float((response.matrix @ response.matrix @ response.states(t))[1])
    current_times = np.unique(np.r_[post_times, _extrema(post_times, current_derivative)])
    derivative_times = np.unique(np.r_[post_times, _extrema(post_times, second_derivative)])
    peak_current = max(abs(current(t)) for t in current_times)
    max_di_dt = max(abs(di_dt(t)) for t in derivative_times) if ls > 0 else None
    initial_terminal = .5 * modes['cg'] * (modes['initial'] * 1000) ** 2
    event_energy = _stored_energy(modes, event_state)
    final_energy = .5 * modes['cg'] * 1e6 * float(np.sum(response.states(end) ** 2))
    post_loss = _quadratic_integral(response, q_total, end)
    shunt_loss = _quadratic_integral(response, q_shunt, end)
    balance_error = abs(event_energy - final_energy - post_loss) / max(event_energy, 1e-30)
    if balance_error > 1e-7:
        raise ValueError('Could not verify post-event dissipation balance for this extreme circuit. No result returned.')
    raw_input_kj = .5 * args['stage_c_uf'] * 1e-6 * (args['charge_kv_stage'] * 1000) ** 2 * args['stages'] / 1000
    pre = _physical_state(modes, event_state)
    post = {**pre, 'shunt_current_a': 0. if ls > 0 else pre['load_voltage_kv'] / rs * 1000}
    return {'metrics': metrics, 'waveform': {'time_us': exported_times_us.tolist(), 'voltage_kv': values.tolist(),
                                           'kind': 'generated_chopped_circuit', 'label': f'{actual.title()}-chopped circuit at saved charge'}}, {
        'chop_time_us': request.chop_time_us, 'baseline_peak_time_us': baseline_peak,
        'classification': actual, 'voltage_at_chop_kv': pre['load_voltage_kv'], 'pre_state': pre, 'post_state': post,
        'shunt_r_ohm': rs, 'shunt_l_uh': request.shunt_l_uh, 'shunt_peak_current_a': peak_current,
        'max_shunt_abs_di_dt_a_per_us': max_di_dt,
        'current_rate_note': ('Finite assumed branch inductance; conditional model prediction.' if ls > 0 else
                              'Zero-inductance ideal-switch current jumps algebraically. No finite instantaneous di/dt is defined.'),
        'branch_provenance': 'User-declared hypothetical R/L, not verified chopping-gap equipment.',
        'time_definition': 'Elapsed since circuit trigger, not measured from virtual origin.',
    }, {
        'healthy_input_kj': raw_input_kj, 'fault_input_kj': raw_input_kj,
        'healthy_terminal_equivalent_kj': initial_terminal / 1000, 'fault_terminal_equivalent_kj': initial_terminal / 1000,
        'energy_at_event_kj': event_energy / 1000, 'remaining_energy_kj': final_energy / 1000,
        'shunt_dissipated_kj': shunt_loss / 1000, 'pre_event_dissipated_kj': (initial_terminal - event_energy) / 1000,
        'post_event_dissipated_kj': post_loss / 1000, 'balance_relative_error': balance_error,
        'definition': 'Input stage energy is sum(0.5 Cstage Vcharge²). Terminal-equivalent model energy includes the squared voltage-loss factor. Dissipation is solved from the post-event passive state equations, not plot-grid integration.',
    }, {
        'post_event_maximum_energy_ratio': float(np.max(energy_ratios)),
        'post_event_maximum_energy_increase_ratio': float(max(0., np.max(np.diff(energy_ratios)))),
        'event_voltage_continuity': True, 'inductor_current_continuity': True,
        'energy_balance_relative_error': balance_error, 'numerical_method': 'Exact constant-system matrix exponential with checked energy-normalized modal fast path; continuous extrema and threshold roots.',
        'post_event_modal_condition': response.condition, 'post_event_matrix_exponential_fallback': not response.modal,
        'original_charge_held_fixed': True, 'output_renormalized': False,
    }


def _stage_failure(args, healthy, request, impulse):
    n = args['stages']
    selected = sorted(request.stage_indices)
    if max(selected) > n:
        raise ValueError(f'Stage indices must name the saved active stack (1–{n}).')
    failed_count = len(selected)
    fraction = request.remaining_charge_fraction
    fault_args = {**args}
    if request.failure_mode == 'bypassed':
        if failed_count >= n:
            raise ValueError('Bypassing every stage leaves no erected generator. This scenario is unsupported.')
        fault_args['stages'] = n - failed_count
        ratio = (n - failed_count) / n
        contributions = [0. if i in selected else 1. for i in range(1, n + 1)]
        note = 'A conductive bypass excludes the selected stage capacitor and its per-stage front/tail sections. This is an explicitly altered topology, not a spark gap that fails to close.'
    else:
        contributions = [fraction if i in selected else 1. for i in range(1, n + 1)]
        ratio = sum(contributions) / n
        fault_args['charge_kv_stage'] = args['charge_kv_stage'] * ratio
        note = 'All N stages remain erected and their gaps are assumed conducting. Selected stage capacitors begin at reduced charge. Cg, total Rf and total Rt remain unchanged; only the sum of initial stage voltages changes.'
    if ratio == 0:
        wave = {**healthy['waveform'], 'voltage_kv': [0.] * len(healthy['waveform']['time_us'])}
        fault = {'crest_kv': 0., 'peak_time_us': None, 'front_us': None, 'tail_us': None,
                 't30_us': None, 't90_us': None, 't50_us': None, 'virtual_origin_us': None, 'waveform': wave}
    else:
        fault = circuit.simulate(**fault_args, impulse_type=impulse, include_waveform=True)
    input_single = .5 * args['stage_c_uf'] * 1e-6 * (args['charge_kv_stage'] * 1000) ** 2 / 1000
    healthy_input = n * input_single
    fault_input = sum(x * x for x in contributions) * input_single
    healthy_terminal = healthy_input * args['efficiency'] ** 2
    if request.failure_mode == 'bypassed':
        fault_terminal = fault_input * args['efficiency'] ** 2
    else:
        fault_terminal = healthy_terminal * ratio ** 2
    return {'metrics': _metrics(fault), 'waveform': {**fault['waveform'], 'kind': 'generated_stage_failure_circuit',
                                                   'label': 'Reduced-charge conducting stack' if request.failure_mode == 'uncharged_conducting' else 'Conductively bypassed stack'}}, {
        'mode': request.failure_mode, 'stage_indices': selected, 'remaining_charge_fraction': fraction,
        'healthy_stage_count': n, 'fault_stage_count': fault_args['stages'], 'source_voltage_ratio': ratio,
        'stage_charge_fractions': contributions, 'fault_circuit_args': fault_args,
        'stage_position_scope': 'Numbers identify selected conceptual stages only. The lumped model predicts no dependence on their physical locations.',
        'charge_kv_stage_held_fixed': args['charge_kv_stage'],
        'effective_mean_charge_kv_stage': fault_args['charge_kv_stage'], 'mode_note': note,
        'unsupported_failure': 'A spark gap that does not fire can leave an open chain; its distributed transient is not represented by either supported mode.',
    }, {
        'healthy_input_kj': healthy_input, 'fault_input_kj': fault_input,
        'healthy_terminal_equivalent_kj': healthy_terminal, 'fault_terminal_equivalent_kj': fault_terminal,
        'remaining_energy_kj': None, 'shunt_dissipated_kj': None,
        'unmodeled_internal_offset_energy_kj': max(0., fault_input * args['efficiency'] ** 2 - fault_terminal),
        'bypassed_capacitor_charge_note': ('Excluded capacitors can retain physical stored charge; bypass does not establish discharge or safety.' if request.failure_mode == 'bypassed' else None),
        'fault_input_scope': ('Energy in modeled contributing stages only; excluded original capacitors may retain charge and their residual energy is unverified.'
                              if request.failure_mode == 'bypassed' else
                              'Sum of the modeled initial charges squared of all N erected stage capacitors, including reduced-charge stages.'),
        'balance_relative_error': None,
        'definition': ('Healthy input energy describes the original charged bank. Fault input energy includes only modeled contributing stages; excluded original capacitors may retain charge and their residual energy is unverified. The bypass does not establish discharge. Original contributing-stage charge is not reoptimized.'
                       if request.failure_mode == 'bypassed' else
                       'Input energy sums modeled stage capacitor charges squared. Unequal-charge conducting stages have internal charge-offset energy that is not accessible in the lumped terminal equivalent. Their original stage charge is not reoptimized.'),
    }, {
        'original_charge_held_fixed': True, 'output_renormalized': False,
        'same_capacitance_and_resistance_for_reduced_charge': request.failure_mode == 'uncharged_conducting',
        'failure_is_not_open_gap_misfire': True, 'numerical_method': circuit.VERSION,
    }


def _common_waveforms(args, healthy, fault, impulse, event=None):
    """Both exported curves share a grid containing all reported metric points."""
    healthy_times = np.asarray(healthy['waveform']['time_us'])
    fault_times = np.asarray(fault['waveform']['time_us'])
    times = np.union1d(healthy_times, fault_times)
    healthy_voltage = circuit.response(**args, times_us=times)
    if event and 'chop_time_us' in event:
        modes = circuit._modes(**args)
        tc = event['chop_time_us'] * 1e-6
        initial = _healthy_states(modes, tc)
        response, load_scale, _, _ = _post_model(modes, initial, event['shunt_r_ohm'], event['shunt_l_uh'] * 1e-6)
        fault_voltage = healthy_voltage.copy()
        mask = times >= event['chop_time_us']
        fault_voltage[mask] = response.states(times[mask] * 1e-6 - tc)[1] / load_scale
    elif event and event.get('source_voltage_ratio') == 0:
        fault_voltage = np.zeros_like(times)
    else:
        fault_voltage = circuit.response(**event['fault_circuit_args'], times_us=times)
    return {**healthy['waveform'], 'time_us': times.tolist(), 'voltage_kv': healthy_voltage.tolist(),
            'label': 'Healthy circuit at saved charge'}, {**fault['waveform'], 'time_us': times.tolist(), 'voltage_kv': fault_voltage.tolist()}


def simulate_fault(snapshot, request):
    args = validate_snapshot(snapshot)
    impulse = snapshot['impulse_type']
    healthy = _healthy(args, impulse)
    if isinstance(request, ChoppedImpulse):
        if impulse != 'Lightning':
            raise ValueError('Front/tail-chopped tests here support Lightning only. Switching chopped impulses require a separate validated definition.')
        fault, event, energy, checks = _chopped(args, healthy, request)
    elif isinstance(request, StageFailure):
        fault, event, energy, checks = _stage_failure(args, healthy, request, impulse)
    else:
        raise ValueError('Unsupported fault test type.')
    healthy_wave, fault_wave = _common_waveforms(args, healthy, fault, impulse, event)
    healthy_metrics = _metrics(healthy, healthy_wave)
    fault_metrics = _metrics(fault['metrics'], fault_wave, isinstance(request, ChoppedImpulse))
    comparison = {'crest_change_pct': 100 * (fault_metrics['crest_kv'] / healthy_metrics['crest_kv'] - 1),
                  'peak_time_change_us': (fault_metrics['peak_time_us'] - healthy_metrics['peak_time_us'] if fault_metrics['peak_time_us'] is not None else None)}
    for key in ('front_us', 'tail_us'):
        comparison[key.replace('_us', '_change_pct')] = (100 * (fault_metrics[key] / healthy_metrics[key] - 1)
                                                        if fault_metrics[key] is not None else None)
    result = {'version': VERSION, 'request': request.model_dump(), 'reference': _reference(snapshot, args),
              'healthy': {'metrics': healthy_metrics, 'waveform': healthy_wave},
              'fault': {'metrics': fault_metrics, 'waveform': fault_wave},
              'comparison': comparison, 'event': event, 'energy': energy, 'checks': checks,
              'assumptions': [*ASSUMPTIONS], 'limitations': [*LIMITATIONS],
              'source_type': 'generated_hypothetical_fault', 'hardware_control': False,
              'laboratory_validation': 'Not established', 'compliance_assessment': 'Not performed for fault waveforms'}
    # Store only finite JSON. A rejected numerical case never creates a saved
    # experiment or mutates its original recommendation.
    def finite(value):
        if isinstance(value, (float, np.floating)) and not math.isfinite(value):
            raise ValueError('Non-finite fault result; no experiment saved.')
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        if isinstance(value, (list, tuple)):
            for v in value: finite(v)
    finite(result)
    return result
