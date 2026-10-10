"""Does fitting generator parameters from one reduced-voltage shot improve predictions?

  python -m scripts.evaluate_parameter_calibration --output artifacts/parameter_calibration/v1

SIMULATED STUDY. A "true" generator is simulated with circuit differences the
production model does not know about (a different loss, extra capacitance, a
charging-resistor discharge path, part of the tail resistance at the load, a
spark-gap resistance and extra inductance). This stands in for a real machine
until measured shots exist; it is not laboratory evidence.

Workflow mirrored from the laboratory checklist:
  1. Recommend settings with the declared (uncalibrated) model.
  2. Fire the recommended setting at 50 % charge on the true generator: one
     calibration shot.
  3. Fit effective parameters from that shot.
  4. Predict validation shots at other settings and voltages with
     (a) the uncalibrated model, (b) the existing one-shot metric offset, which
     only applies to identical settings and requests within 1 %, and
     (c) fitted parameters; compare each with the true generator.
  5. Re-recommend with fitted parameters and fire it on the true generator.
The protocol and promotion gate are written before any scenario is run.
"""
import argparse
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from backend.app.optimization.engine import optimize
from backend.app.physics.compliance import check, RULES
from backend.app.physics.parameter_calibration import fit, predict as fitted_predict, VERSION
from backend.app.physics.waveform_metrics import analyze
from backend.app.physics.circuit import VERSION as CIRCUIT_VERSION
from backend.app.schemas import OptimizeRequest

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('front_us', 'tail_us', 'crest_kv')
STOCK = {'front': [{'ohm': 30, 'count_per_stage': 2}, {'ohm': 465, 'count_per_stage': 2}, {'ohm': 3700, 'count_per_stage': 2}],
         'tail': [{'ohm': 520, 'count_per_stage': 2}, {'ohm': 22000, 'count_per_stage': 2}],
         'provenance': 'Study assumption: two units per CPRI source value per stage'}
BASE = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
            load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83, inventory_override=STOCK)
TARGETS = {'Lightning': 1425, 'Switching': 1050}
# Differences between the true generator and the declared model (unknown to the model).
SCENARIOS = {
    'control_no_difference': {},
    'less_loss_more_stray': {'efficiency_scale': 1.08, 'extra_stray_pf': 250},
    'charging_resistor_path': {'extra_shunt_ohm_per_stage': 135000, 'efficiency_scale': .97},
    'tail_partly_at_load': {'tail_load_fraction': .3},
    'spark_resistance_and_inductance': {'spark_ohm_per_stage': 3, 'extra_l_uh': 10, 'extra_stray_pf': 100},
    'combined': {'tail_load_fraction': .15, 'extra_shunt_ohm_per_stage': 135000, 'efficiency_scale': 1.05,
                 'extra_stray_pf': 150, 'extra_l_uh': 5},
}
GATE = {
    'G1_crest': 'Per impulse type, median |crest error| over all mismatch scenarios and validation shots with fitted parameters <= 50 % of the uncalibrated median.',
    'G2_timing': 'Per impulse type, median |front| and |tail| errors with fitted parameters <= the uncalibrated medians.',
    'G3_recommendations': 'Recommendations re-made with fitted parameters pass on the true generator at least as often as uncalibrated ones in every scenario and impulse type, and more often in total.',
    'G4_no_regression': 'No scenario/impulse/metric where the fitted-parameter p95 |error| exceeds the uncalibrated p95 by more than 2 percentage points.',
    'G5_control': 'With no true difference, fitted-parameter errors stay below 0.5 % for every metric.',
    'decision': 'All five must hold for the fitted-parameter workflow to be offered in the application; otherwise it stays an experiment.',
}


def true_generator(stages, charge, rf_stage, rt_stage, cfg, scenario, impulse):
    """Measured stand-in: an independent ODE of the true circuit, metrics from dense samples."""
    s = SCENARIOS[scenario]
    n = stages
    cg = .125e-6/n
    cl = (cfg['load_c_pf'] + cfg['divider_c_pf'] + cfg['stray_c_pf'] + 545 + s.get('extra_stray_pf', 0))*1e-12
    rf = n*(rf_stage + s.get('spark_ohm_per_stage', 0))
    rt = n*rt_stage
    inductance = (cfg['l_uh'] + s.get('extra_l_uh', 0))*1e-6
    v0 = n*charge*cfg['efficiency']*s.get('efficiency_scale', 1)*1e3
    f = s.get('tail_load_fraction', 0)
    g_gen = (1 - f)/rt + (1/(n*s['extra_shunt_ohm_per_stage']) if s.get('extra_shunt_ohm_per_stage') else 0)
    g_load = f/rt

    def rhs(t, y):
        vg, current, vl = y
        return [(-current - g_gen*vg)/cg, (vg - rf*current - vl)/inductance, (current - g_load*vl)/cl]
    jac = np.array([[-g_gen/cg, -1/cg, 0], [1/inductance, -rf/inductance, -1/inductance], [0, 1/cl, -g_load/cl]])
    horizon = 12*(rt*(cg + cl) + rf*cl)
    sol = solve_ivp(rhs, (0, horizon), [v0, 0, 0], method='Radau', jac=jac, rtol=1e-9, atol=1e-9*v0, dense_output=True,
                    max_step=horizon/4000)
    fast = max(rf*cl, math.sqrt(inductance*cl))
    t = np.unique(np.r_[np.linspace(0, 60*fast, 6000), np.geomspace(fast*1e-3, horizon, 8000)])
    m = analyze(t*1e6, sol.sol(t)[2]/1e3, impulse)
    return {k: float(m[k]) for k in KEYS}


def request(impulse, **kw):
    return OptimizeRequest(**{**BASE, 'impulse_type': impulse, 'test_kv': TARGETS[impulse], **kw})


def shot_inputs(settings, impulse, charge=None):
    return {'stages': settings['stages'], 'charge_kv_stage': charge if charge is not None else settings['charge_kv_stage'],
            'front_r_stage': settings['front_r_stage'], 'tail_r_stage': settings['tail_r_stage'], 'stage_c_uf': .125,
            'total_c_pf': BASE['load_c_pf'] + BASE['divider_c_pf'] + BASE['stray_c_pf'] + 545, 'l_uh': BASE['l_uh'],
            'efficiency': BASE['efficiency'], 'impulse_type': impulse}


def rel(pred, truth):
    return {k: 100*(pred[k]/truth[k] - 1) for k in KEYS}


NOISE = None  # set by --measurement-noise: relative 1-sigma errors on the calibration shot's extracted metrics


def run_scenario(scenario, impulse):
    base = optimize(request(impulse))
    top = base['candidates'][0]['settings']
    cal_charge = .5*top['charge_kv_stage']
    measured = true_generator(top['stages'], cal_charge, top['front_r_stage'], top['tail_r_stage'], BASE, scenario, impulse)
    if NOISE:
        rng = np.random.default_rng(list(SCENARIOS).index(scenario)*2 + (impulse == 'Switching'))
        measured = {k: v*(1 + NOISE[k]*rng.standard_normal()) for k, v in measured.items()}
    fitted = fit([{**shot_inputs(top, impulse, cal_charge), 'measured': measured}])
    params = fitted['parameters']
    calibration_offset = {k: measured[k] - fitted_predict(shot_inputs(top, impulse, cal_charge), None)[k] for k in KEYS}
    validation = []
    settings_list = [('rank1_full_voltage', top, top['charge_kv_stage'])]
    settings_list += [(f'rank{c["rank"]}_full_voltage', c['settings'], c['settings']['charge_kv_stage']) for c in base['candidates'][1:5]]
    settings_list += [('rank1_75pct_voltage', top, .75*top['charge_kv_stage'])]
    try:
        fewer = optimize(request(impulse, stage_max=top['stages'] - 2))['candidates'][0]['settings']
        settings_list.append(('two_fewer_stages', fewer, fewer['charge_kv_stage']))
    except ValueError:
        pass
    for label, s, charge in settings_list:
        truth = true_generator(s['stages'], charge, s['front_r_stage'], s['tail_r_stage'], BASE, scenario, impulse)
        shot = shot_inputs(s, impulse, charge)
        plain = fitted_predict(shot, None)
        with_params = fitted_predict(shot, params)
        # Existing one-shot offset: only when settings are identical and the request within 1 %.
        same = (s['stages'] == top['stages'] and abs(s['front_r_stage'] - top['front_r_stage']) < 1e-8
                and abs(s['tail_r_stage'] - top['tail_r_stage']) < 1e-8 and abs(charge/cal_charge - 1) <= .01)
        offset = {k: plain[k] + (calibration_offset[k] if same else 0) for k in KEYS}
        validation.append({'shot': label, 'settings': {**s, 'charge_kv_stage': charge}, 'truth': truth,
                           'error_pct': {'uncalibrated': rel(plain, truth), 'metric_offset': rel(offset, truth),
                                         'fitted_parameters': rel(with_params, truth)},
                           'metric_offset_applied': same})
    # Recommendations on the true generator.
    record = {'id': f'study-{scenario}-{impulse}', 'parameters': params, 'fit': {k: v for k, v in fitted.items() if k != 'parameters'},
              'scope': {'generator_profile': base['profile'], 'impulse_type': impulse, 'layout_id': 'default-layout',
                        'include_base_c': True, 'physics_version': CIRCUIT_VERSION}, 'source_type': 'simulated_study'}
    recal = optimize(request(impulse), parameter_calibration=record)
    def fired(run):
        s = run['candidates'][0]['settings']
        truth = true_generator(s['stages'], s['charge_kv_stage'], s['front_r_stage'], s['tail_r_stage'], BASE, scenario, impulse)
        return {'settings': s, 'truth': truth, 'truth_pass': check(impulse, TARGETS[impulse], truth)['nominal_pass'],
                'predicted_pass': run['candidates'][0]['compliance']['nominal_pass']}
    return {'scenario': scenario, 'impulse_type': impulse, 'calibration_shot': {'settings': {**top, 'charge_kv_stage': cal_charge}, 'measured': measured},
            'fit': fitted, 'validation': validation,
            'recommendation': {'uncalibrated': fired(base), 'fitted_parameters': fired(recal)}}


def summarize(results):
    out = {}
    for impulse in TARGETS:
        rows = [v for r in results if r['impulse_type'] == impulse and r['scenario'] != 'control_no_difference' for v in r['validation']]
        out[impulse] = {method: {k: {'median_abs_pct': statistics.median(abs(v['error_pct'][method][k]) for v in rows),
                                     'p95_abs_pct': float(np.percentile([abs(v['error_pct'][method][k]) for v in rows], 95)),
                                     'worst_abs_pct': max(abs(v['error_pct'][method][k]) for v in rows)} for k in KEYS}
                        for method in ('uncalibrated', 'metric_offset', 'fitted_parameters')}
        out[impulse]['validation_shots'] = len(rows)
    return out


def gates(results, summary):
    g = {}
    g['G1_crest'] = all(summary[t]['fitted_parameters']['crest_kv']['median_abs_pct'] <= .5*summary[t]['uncalibrated']['crest_kv']['median_abs_pct'] for t in TARGETS)
    g['G2_timing'] = all(summary[t]['fitted_parameters'][k]['median_abs_pct'] <= summary[t]['uncalibrated'][k]['median_abs_pct'] for t in TARGETS for k in ('front_us', 'tail_us'))
    passes = {(r['scenario'], r['impulse_type']): (r['recommendation']['uncalibrated']['truth_pass'], r['recommendation']['fitted_parameters']['truth_pass']) for r in results}
    g['G3_recommendations'] = all(b >= a for a, b in passes.values()) and sum(b for _, b in passes.values()) > sum(a for a, _ in passes.values())
    worst = []
    for r in results:
        for k in KEYS:
            u = np.percentile([abs(v['error_pct']['uncalibrated'][k]) for v in r['validation']], 95)
            f = np.percentile([abs(v['error_pct']['fitted_parameters'][k]) for v in r['validation']], 95)
            worst.append(f - u)
    g['G4_no_regression'] = bool(max(worst) <= 2.0)
    control = [v for r in results if r['scenario'] == 'control_no_difference' for v in r['validation']]
    g['G5_control'] = all(abs(v['error_pct']['fitted_parameters'][k]) < .5 for v in control for k in KEYS)
    g = {k: bool(v) for k, v in g.items()}
    g['all_pass'] = all(g.values())
    g['largest_p95_increase_pp'] = float(max(worst))
    g['recommendation_truth_passes'] = {'uncalibrated': sum(a for a, _ in passes.values()), 'fitted_parameters': sum(b for _, b in passes.values()),
                                        'cases': len(passes)}
    return g


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/parameter_calibration/v1')
    parser.add_argument('--measurement-noise', action='store_true',
                        help='Sensitivity run: perturb the calibration shot metrics (crest 0.5 %, front 2 %, tail 1 %, one sigma).')
    args = parser.parse_args()
    global NOISE
    if args.measurement_noise:
        NOISE = {'crest_kv': .005, 'front_us': .02, 'tail_us': .01}
    out = ROOT/args.output
    out.mkdir(parents=True, exist_ok=True)
    protocol = {'version': 'parameter-calibration-study-v1', 'declared_at': datetime.now(timezone.utc).isoformat(),
                'evidence_type': 'SIMULATED MODEL-MISMATCH STUDY (not laboratory evidence)',
                'method': VERSION, 'scenarios': SCENARIOS, 'targets_kv': TARGETS, 'stock': STOCK, 'base_request': {k: v for k, v in BASE.items() if k != 'inventory_override'},
                'calibration_shot': 'Rank-1 setting at 50 % of its recommended charge; one shot.',
                'validation_shots': 'Ranks 1-5 at full charge, rank 1 at 75 % charge, best setting with two fewer stages.',
                'measurement_noise_on_calibration_shot': NOISE,
                'gate': GATE, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out/'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    started = time.time()
    results = []
    for scenario in SCENARIOS:
        for impulse in TARGETS:
            results.append(run_scenario(scenario, impulse))
            r = results[-1]
            print(scenario, impulse, {k: round(v, 4) for k, v in r['fit']['parameters'].items()},
                  'pass', r['recommendation']['uncalibrated']['truth_pass'], '->', r['recommendation']['fitted_parameters']['truth_pass'], flush=True)
    summary = summarize(results)
    decision = gates(results, summary)
    result = {'version': 'parameter-calibration-study-v1', 'protocol_sha256': hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),
              'summary': summary, 'gates': decision, 'results': results,
              'what_this_shows': 'Whether one reduced-voltage calibration shot, through three fitted circuit parameters, improves predictions '
                                 'at other settings of a simulated generator that differs from the declared model. Real shots are needed to confirm it.',
              'elapsed_seconds': round(time.time() - started, 1)}
    (out/'results.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8')
    print(json.dumps({'summary': summary, 'gates': decision}, indent=1, default=float))


if __name__ == '__main__':
    main()
