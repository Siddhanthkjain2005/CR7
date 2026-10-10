"""Physics-based inverse analysis with the existing equivalent-circuit solver.

Each hypothesis frees a few effective quantities of the lumped circuit (or of the
measurement) and is fitted by bounded, scaled least squares from several starts.
Competing explanations are kept, compared with a complexity penalty, and checked
for identifiability. Fit scores rank explanations; they are not fault probabilities.
"""
import math
import time

import numpy as np
from scipy.optimize import least_squares

from ..physics.circuit import response, simulate
from .compare import balanced_weights, regions

VERSION = 'physics-inverse-analysis-v1'
CONSISTENT = 1.5          # region-balanced normalized mismatch at or below this agrees within uncertainty
REGION_LIMIT = 2.5        # and no single region may exceed this
N_EFFECTIVE = 90          # information per recording assumed by the complexity penalty (policy, see docs)
NEAR_TIE = .5             # several explanations "fit" when their penalized scores are this close (relative)
MAX_PER_REGION = 400      # samples per region used for fitting (even decimation; weights unchanged)
CATEGORIES = {'hardware': 'Hardware hypothesis', 'configuration': 'Configuration difference',
              'measurement': 'Measurement issue', 'model': 'Model limitation'}
NO_FIT_MESSAGE = 'The current equivalent-circuit model cannot adequately explain this recording.'


def parameter_space(base, predicted, impulse_type):
    """Bounds of every free quantity, as (label, unit, lower, upper, log-scaled, no-change value)."""
    ctot, l, eta = base['total_c_pf'], base['l_uh'], base['efficiency']
    shift = .5 * predicted['front_us'] if impulse_type == 'Lightning' else .25 * predicted['front_us']
    return {
        'front_factor': ('Front network resistance', '×', .4, 2.5, True, 1.),
        'tail_factor': ('Tail network resistance', '×', .4, 2.5, True, 1.),
        'extra_load_pf': ('Load-side capacitance change', 'pF', -.6 * ctot, 1.5 * ctot, False, 0.),
        'inductance_uh': ('Total circuit inductance', 'µH', 0., max(4 * l, l + 40.), False, l),
        'charge_factor': ('Charge per stage', '×', .7, 1.3, False, 1.),
        'efficiency_factor': ('Loss factor', '×', .7, min(1.25, 1 / eta), False, 1.),
        'gain': ('Measurement gain', '×', .7, 1.3, False, 1.),
        'time_shift_us': ('Recording time offset', 'µs', -shift, shift, False, 0.),
        'baseline_kv': ('Recording baseline offset', 'kV', -.05 * predicted['crest_kv'], .05 * predicted['crest_kv'], False, 0.),
    }


HYPOTHESES = [
    # id, title, category, component group, parameters, needs (setting that must be declared uncertain)
    ('front_network', 'Front resistor network differs from nominal', 'hardware', 'Front resistor network', ['front_factor'], None),
    ('tail_network', 'Tail resistor network differs from nominal', 'hardware', 'Tail resistor network', ['tail_factor'], None),
    ('effective_capacitance', 'Load-side capacitance differs from the declared total', 'hardware',
     'Load-side capacitance (test object, divider, stray, 545 pF base)', ['extra_load_pf'], None),
    ('inductance', 'Circuit inductance differs from the declared value', 'hardware', 'Connection and generator inductance', ['inductance_uh'], None),
    ('charge', 'Charging voltage differs from the recorded value', 'configuration', 'Charging voltage', ['charge_factor'], 'charge_kv_stage'),
    ('stages', 'A different number of stages fired', 'configuration', 'Active stages', [], 'stages'),
    ('loss_convention', 'Loss factor differs from the assumption', 'model', 'Loss convention (efficiency factor)', ['efficiency_factor'], None),
    ('gain', 'Measurement gain differs (divider ratio or scale)', 'measurement', 'Voltage divider and recording scale', ['gain'], None),
    ('timing', 'Recording time origin is offset', 'measurement', 'Trigger and time origin', ['time_shift_us'], None),
    ('baseline_offset', 'Recording baseline is offset', 'measurement', 'Recorder baseline', ['baseline_kv'], None),
    # A few justified two-parameter combinations.
    ('front_and_tail', 'Both resistor networks differ', 'hardware', 'Front and tail resistor networks', ['front_factor', 'tail_factor'], None),
    ('capacitance_and_inductance', 'Load-side capacitance and inductance differ', 'hardware',
     'Load-side capacitance and connection inductance', ['extra_load_pf', 'inductance_uh'], None),
    ('front_and_capacitance', 'Front network and load-side capacitance differ', 'hardware',
     'Front resistor network and load-side capacitance', ['front_factor', 'extra_load_pf'], None),
    ('loss_and_front', 'Loss factor and front network differ', 'model', 'Loss convention and front resistor network', ['efficiency_factor', 'front_factor'], None),
    ('loss_and_tail', 'Loss factor and tail network differ', 'model', 'Loss convention and tail resistor network', ['efficiency_factor', 'tail_factor'], None),
    ('gain_and_timing', 'Measurement gain and time origin differ', 'measurement', 'Divider scale and trigger', ['gain', 'time_shift_us'], None),
]
AMPLITUDE_ONLY = {'charge', 'loss_convention', 'gain'}
FIELD_NAMES = {'charge_kv_stage': 'charge per stage', 'stages': 'number of active stages'}


class Cancelled(Exception):
    pass


def model_curve(base, params, times_us, stages=None):
    """Load voltage of the modified circuit (and measurement) at the observed times."""
    n = stages or base['stages']
    total = base['total_c_pf'] + params.get('extra_load_pf', 0.)
    if total <= 0:
        raise ValueError('Non-positive load-side capacitance.')
    v = response(n, base['charge_kv_stage'] * params.get('charge_factor', 1.),
                 base['front_r_stage'] * params.get('front_factor', 1.), base['tail_r_stage'] * params.get('tail_factor', 1.),
                 base['stage_c_uf'], total, params.get('inductance_uh', base['l_uh']),
                 base['efficiency'] * params.get('efficiency_factor', 1.),
                 np.asarray(times_us) - params.get('time_shift_us', 0.))
    return v * params.get('gain', 1.) + params.get('baseline_kv', 0.)


def model_metrics(base, params, impulse_type, stages=None):
    """Metrics of the fitted circuit itself (no measurement terms), from the existing solver."""
    n = stages or base['stages']
    r = simulate(n, base['charge_kv_stage'] * params.get('charge_factor', 1.),
                 base['front_r_stage'] * params.get('front_factor', 1.), base['tail_r_stage'] * params.get('tail_factor', 1.),
                 base['stage_c_uf'], base['total_c_pf'] + params.get('extra_load_pf', 0.),
                 params.get('inductance_uh', base['l_uh']), base['efficiency'] * params.get('efficiency_factor', 1.),
                 impulse_type, True)
    metrics = {k: r[k] for k in ('front_us', 'tail_us', 'crest_kv')}
    g = params.get('gain', 1.)
    metrics['crest_kv'] *= g  # what the recorder would show
    return metrics, r['waveform']


def _decimate(t, v, sigma, region, limit=MAX_PER_REGION):
    keep = np.zeros(len(t), bool)
    for r in (0, 1, 2):
        idx = np.flatnonzero(region == r)
        if len(idx) > limit:
            idx = idx[np.round(np.linspace(0, len(idx) - 1, limit)).astype(int)]
        keep[idx] = True
    return t[keep], v[keep], sigma[keep], region[keep]


class Problem:
    def __init__(self, base, observed, impulse_type, predicted):
        self.base = base
        self.impulse_type = impulse_type
        t = np.asarray(observed['time_us'], float); v = np.asarray(observed['voltage_kv'], float)
        sigma = np.asarray(observed['sigma_kv'], float)
        admitted = np.asarray(observed.get('admitted', np.ones(len(t), bool)), bool)
        t, v, sigma = t[admitted], v[admitted], sigma[admitted]
        region = regions(t, np.interp(t, predicted['time_us'], predicted['voltage_kv']), predicted['peak_time_us'])
        self.t, self.v, self.sigma, self.region = _decimate(t, v, sigma, region)
        self.w = np.sqrt(balanced_weights(self.region))
        self.space = parameter_space(base, predicted, impulse_type)
        self.evaluations = 0

    def physical(self, names, u):
        out = {}
        for name, x in zip(names, u):
            _, _, lo, hi, log, _ = self.space[name]
            out[name] = math.exp(math.log(lo) + x * (math.log(hi) - math.log(lo))) if log else lo + x * (hi - lo)
        return out

    def scaled(self, name, value):
        _, _, lo, hi, log, _ = self.space[name]
        return (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo)) if log else (value - lo) / (hi - lo)

    def residual(self, names, u, stages=None):
        self.evaluations += 1
        try:
            model = model_curve(self.base, self.physical(names, u), self.t, stages)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            return np.full(len(self.t), 1e3) * self.w
        return self.w * (model - self.v) / self.sigma

    def mismatch(self, names, u, stages=None):
        r = self.residual(names, u, stages)
        total = float(np.sqrt(np.sum(r * r)))
        z = (r / np.where(self.w > 0, self.w, 1))
        per = {name: (float(np.sqrt(np.mean(z[self.region == k] ** 2))) if (self.region == k).any() else None)
               for k, name in enumerate(('rise', 'crest', 'tail'))}
        return total, per


def _starts(problem, names):
    nominal = [min(1., max(0., problem.scaled(n, problem.space[n][5]))) for n in names]
    grid = [.2, .5, .8] if len(names) == 1 else [.25, .75]
    starts = [nominal]
    if len(names) == 1:
        starts += [[g] for g in grid]
    else:
        starts += [[a, b] for a in grid for b in grid]
    return starts


def fit_one(problem, names, stages=None, deadline=None, cancel=None):
    """Bounded least squares from several starts; keeps every distinct local solution."""
    if not names:
        total, per = problem.mismatch([], [], stages)
        return {'parameters': {}, 'scaled': [], 'mismatch': total, 'by_region': per, 'solutions': [], 'jacobian': None}
    solutions = []
    for start in _starts(problem, names):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if deadline is not None and time.monotonic() > deadline:
            break
        result = least_squares(lambda u: problem.residual(names, u, stages), np.clip(start, 1e-6, 1 - 1e-6),
                               bounds=(np.zeros(len(names)), np.ones(len(names))), x_scale='jac', method='trf',
                               max_nfev=60 * len(names), diff_step=1e-4)
        total, per = problem.mismatch(names, result.x, stages)
        solutions.append({'scaled': result.x.tolist(), 'mismatch': total, 'by_region': per, 'jac': result.jac, 'start': list(start)})
    best = min(solutions, key=lambda s: s['mismatch'])
    distinct = []
    for s in sorted(solutions, key=lambda s: s['mismatch']):
        if all(np.max(np.abs(np.array(s['scaled']) - np.array(d['scaled']))) > .05 for d in distinct):
            distinct.append(s)
    good = [s for s in distinct if s['mismatch'] <= best['mismatch'] * 1.1 + .05]
    return {'parameters': problem.physical(names, best['scaled']), 'scaled': best['scaled'], 'mismatch': best['mismatch'],
            'by_region': best['by_region'], 'jacobian': best['jac'],
            'solutions': [{'parameters': problem.physical(names, s['scaled']), 'mismatch': s['mismatch']} for s in good],
            'starts': len(solutions)}


def identifiability(problem, names, fit, stages=None):
    """Bounds, local uncertainty (policy N_EFFECTIVE), correlation and a ±10 % profile."""
    if not names:
        return {}
    u = np.array(fit['scaled'])
    at_bound = [n for n, x in zip(names, u) if x < 1e-3 or x > 1 - 1e-3]
    jac = np.asarray(fit['jacobian'], float)
    info = jac.T @ jac * N_EFFECTIVE
    cond = float(np.linalg.cond(info)) if np.isfinite(info).all() else float('inf')
    out = {'at_bound': at_bound, 'condition_number': cond if math.isfinite(cond) else None, 'parameters': {}}
    try:
        cov = np.linalg.inv(info)
        sd = np.sqrt(np.clip(np.diag(cov), 0, None))
        corr = cov / np.outer(sd, sd) if (sd > 0).all() else None
    except np.linalg.LinAlgError:
        sd, corr = np.full(len(names), np.inf), None
    for i, name in enumerate(names):
        value = fit['parameters'][name]
        _, _, lo, hi, log, nominal = problem.space[name]
        # Convert the scaled standard deviation to physical units locally.
        dx = (value * (math.log(hi) - math.log(lo)) if log else (hi - lo)) * sd[i]
        profile = {}
        for step in (-.1, .1):
            moved = dict(fit['parameters'])
            moved[name] = value * (1 + step) if abs(value) > 1e-12 else value + step * (hi - lo)
            if lo <= moved[name] <= hi:
                uu = [problem.scaled(n, moved[n]) for n in names]
                profile[f'{int(step * 100):+d}%'] = problem.mismatch(names, uu, stages)[0]
        out['parameters'][name] = {'value': value, 'local_sd': float(dx) if np.isfinite(dx) else None,
                                   'relative_sd': float(abs(dx / value)) if value and np.isfinite(dx) else None,
                                   'profile_mismatch': profile}
    if corr is not None and len(names) > 1:
        out['correlation'] = float(corr[0, 1])
    weak = [n for n, p in out['parameters'].items()
            if p['local_sd'] is None or (p['relative_sd'] is not None and p['relative_sd'] > .5)]
    out['poorly_determined'] = weak
    out['trade_off'] = bool(len(names) > 1 and out.get('correlation') is not None and abs(out['correlation']) > .95)
    out['multiple_good_fits'] = len(fit.get('solutions', [])) > 1
    out['unstable'] = out['multiple_good_fits'] or not math.isfinite(cond) or cond > 1e8
    return out


def investigate(base, observed, predicted, impulse_type, *, uncertain=(), as_fired_recorded=True,
                profile=None, progress=None, cancel=None, budget_s=90.):
    """Run every applicable hypothesis; return ranked results with identifiability and verdict."""
    started = time.monotonic(); deadline = started + budget_s
    problem = Problem(base, observed, impulse_type, predicted)
    plan = []
    for hid, title, category, group, names, needs in HYPOTHESES:
        if needs and as_fired_recorded and needs not in uncertain:
            plan.append((hid, title, category, group, names, needs, 'skip'))
            continue
        plan.append((hid, title, category, group, names, needs, 'fit'))
    stage_options = []
    if profile and (not as_fired_recorded or 'stages' in uncertain):
        stage_options = [n for n in range(base['stages'] - 2, base['stages'] + 3)
                         if n != base['stages'] and profile['min_stages'] <= n <= profile['max_stages']]
    total_steps = 1 + sum(1 for p in plan if p[-1] == 'fit' and p[0] != 'stages') + len(stage_options)
    done = 0

    def tick(label):
        nonlocal done
        done += 1
        if progress:
            progress(done, total_steps, label)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
    baseline = fit_one(problem, [])
    tick('Baseline: circuit prediction at the compared settings')
    results = [{'id': 'baseline', 'title': 'No change: the circuit prediction as compared', 'category': None,
                'group': None, 'parameter_names': [], 'parameters': {}, 'mismatch': baseline['mismatch'],
                'by_region': baseline['by_region'], 'free_parameters': 0}]
    for hid, title, category, group, names, needs, action in plan:
        if action == 'skip':
            results.append({'id': hid, 'title': title, 'category': category, 'group': group, 'parameter_names': names,
                            'status': 'Not tested', 'reason': f'The {FIELD_NAMES.get(needs, needs)} was recorded as fired and not declared uncertain, so it stays fixed.'})
            continue
        if hid == 'stages':
            best = None
            for n in stage_options:
                fit = fit_one(problem, [], n, deadline, cancel)
                tick(f'Stages: {n}')
                if best is None or fit['mismatch'] < best[1]['mismatch']:
                    best = (n, fit)
            if best is None:
                results.append({'id': hid, 'title': title, 'category': category, 'group': group, 'parameter_names': [],
                                'status': 'Not tested', 'reason': 'No other stage count is possible on this generator.'})
                continue
            results.append({'id': hid, 'title': title, 'category': category, 'group': group, 'parameter_names': ['stages'],
                            'parameters': {'stages': best[0]}, 'mismatch': best[1]['mismatch'], 'by_region': best[1]['by_region'],
                            'free_parameters': 1, 'stages': best[0], 'identifiability': {'at_bound': [], 'discrete': True}})
            continue
        if time.monotonic() > deadline:
            results.append({'id': hid, 'title': title, 'category': category, 'group': group, 'parameter_names': names,
                            'status': 'Not tested', 'reason': 'Stopped at the compute budget.'})
            continue
        fit = fit_one(problem, names, None, deadline, cancel)
        ident = identifiability(problem, names, fit)
        results.append({'id': hid, 'title': title, 'category': category, 'group': group, 'parameter_names': names,
                        'parameters': fit['parameters'], 'mismatch': fit['mismatch'], 'by_region': fit['by_region'],
                        'free_parameters': len(names), 'identifiability': ident, 'alternative_solutions': fit['solutions'],
                        'starts': fit['starts']})
        tick(title)
    return rank(results, problem, base, impulse_type, as_fired_recorded, time.monotonic() - started)


def score(result):
    return result['mismatch'] ** 2 + 2 * result['free_parameters'] / N_EFFECTIVE


def consistent(result):
    per = [v for v in (result.get('by_region') or {}).values() if v is not None]
    return result.get('mismatch') is not None and result['mismatch'] <= CONSISTENT and all(v <= REGION_LIMIT for v in per)


def rank(results, problem, base, impulse_type, as_fired_recorded, elapsed):
    fitted = [r for r in results if r.get('mismatch') is not None]
    baseline = next(r for r in fitted if r['id'] == 'baseline')
    for r in fitted:
        r['penalized_score'] = score(r)
        r['consistent'] = consistent(r)
        r['improvement_pct'] = (100 * (baseline['mismatch'] - r['mismatch']) / baseline['mismatch']
                                if baseline['mismatch'] > 0 else 0.)
    # Explanations whose fitted curves coincide cannot be told apart by this recording.
    curves = {}
    for r in fitted:
        if r['id'] == 'baseline':
            continue
        try:
            curves[r['id']] = model_curve(base, {k: v for k, v in r['parameters'].items() if k != 'stages'},
                                          problem.t, r.get('stages'))
        except ValueError:
            pass
    sigma = problem.sigma
    names = {r['id']: set(r['parameter_names']) for r in fitted}
    for r in fitted:
        # Nested hypotheses (one contains the other's quantities) are the same explanation, not a rival.
        twins = [o for o in curves if o != r['id'] and r['id'] in curves
                 and not (names[o] <= names[r['id']] or names[r['id']] <= names[o])
                 and np.sqrt(np.mean(((curves[o] - curves[r['id']]) / sigma) ** 2)) < .1]
        r['indistinguishable_from'] = twins
    candidates = sorted([r for r in fitted if r['id'] != 'baseline'], key=lambda r: r['penalized_score'])
    good = [r for r in candidates if r['consistent'] and r['penalized_score'] < baseline['penalized_score']]
    # A combination that contains a simpler consistent explanation and does not beat it after the
    # complexity penalty adds nothing: it is the same explanation with an unneeded extra quantity.
    redundant = set()
    for r in good:
        names = set(r['parameter_names'])
        if any(o is not r and set(o['parameter_names']) < names and o['penalized_score'] <= r['penalized_score'] for o in good):
            redundant.add(r['id'])
    good = [r for r in good if r['id'] not in redundant]
    if baseline['consistent']:
        verdict = {'label': 'No change needed',
                   'message': 'The recording agrees with the circuit prediction at the compared settings within the stated '
                              'uncertainty. There is no mismatch to explain.'}
        lead = []
    elif not good:
        verdict = {'label': 'Cannot explain with the current model', 'message': NO_FIT_MESSAGE}
        lead = []
    else:
        best = good[0]
        close = [r for r in good if r['penalized_score'] <= best['penalized_score'] * (1 + NEAR_TIE) + .02]
        groups = {r['group'] for r in close}
        if len(close) > 1 and len(groups) > 1:
            verdict = {'label': 'Several explanations fit',
                       'message': f'{len(close)} explanations from different parts of the system fit this recording about '
                                  'equally well. Additional measurement is needed to tell them apart.'}
        else:
            verdict = {'label': 'Possible cause', 'message': f"{best['title']} is consistent with this waveform."}
        lead = close
    lead_ids = {r['id'] for r in lead}
    for r in results:
        if r.get('status') == 'Not tested':
            continue
        if r['id'] == 'baseline':
            r['status'] = 'Consistent with this waveform' if r['consistent'] else 'Does not match'
        elif r['id'] in lead_ids:
            r['status'] = 'Possible cause' if verdict['label'] == 'Possible cause' and r is lead[0] else 'Several explanations fit'
        elif r['id'] in redundant:
            r['status'] = 'Not needed'
            r['reason'] = 'Fits as well only because it contains a simpler explanation; the extra quantity does not improve the fit.'
        elif r['consistent']:
            r['status'] = 'Consistent with this waveform'
        else:
            r['status'] = 'Does not explain the mismatch'
        ident = r.get('identifiability') or {}
        r['needs_more_measurement'] = bool(r['indistinguishable_from'] or ident.get('poorly_determined') or ident.get('trade_off')
                                           or ident.get('at_bound') or ident.get('multiple_good_fits'))
    if not as_fired_recorded:
        verdict['limited'] = ('The settings actually fired were not recorded, so configuration differences cannot be ruled '
                              'out and any hardware explanation is limited.')
    systematic = residual_structure(problem, base, lead[0] if lead else (candidates[0] if candidates else baseline))
    return {'version': VERSION, 'verdict': verdict, 'hypotheses': results, 'ranking': [r['id'] for r in candidates],
            'leading': [r['id'] for r in lead], 'residual_structure': systematic,
            'policy': {'consistent_mismatch': CONSISTENT, 'region_limit': REGION_LIMIT, 'n_effective': N_EFFECTIVE,
                       'near_tie': NEAR_TIE, 'penalty': 'score = mismatch² + 2 × free parameters / 90',
                       'weighting': 'Region-balanced: rise, crest region and tail each carry one third of the weight.',
                       'decimation': f'At most {MAX_PER_REGION} samples per region, evenly spaced; weights unchanged.'},
            'samples_fitted': int(len(problem.t)), 'evaluations': problem.evaluations, 'elapsed_s': elapsed,
            'statement': 'Fit scores rank explanations of this recording. They are not probabilities that a component is '
                         'faulty, and no component is shown to be faulty by a fit.'}


def residual_structure(problem, base, result):
    """Is what remains random scatter or a systematic shape (missing physics)?"""
    try:
        params = {k: v for k, v in (result.get('parameters') or {}).items() if k != 'stages'}
        model = model_curve(base, params, problem.t, result.get('stages'))
    except ValueError:
        return None
    z = (problem.v - model) / problem.sigma
    signs = np.sign(z[np.abs(z) > .5])
    runs = int(1 + np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else len(signs)
    n = len(signs)
    expected = (n + 1) / 2 if n else 0
    systematic = bool(n >= 20 and runs < .3 * expected and np.sqrt(np.mean(z * z)) > 1)
    worst = None
    if len(z):
        k = int(np.argmax(np.abs(z)))
        worst = {'time_us': float(problem.t[k]), 'normalized': float(z[k]),
                 'region': ('rise', 'crest', 'tail')[int(problem.region[k])]}
    return {'sign_runs': runs, 'expected_runs_if_random': expected, 'systematic': systematic, 'largest': worst,
            'meaning': ('A systematic remaining difference that no hypothesis removes points to physics the lumped circuit '
                        'does not contain (for example distributed elements, spark-gap dynamics or the measuring system '
                        'response).' if systematic else 'What remains looks like scatter within the stated uncertainty.')}
