"""Evaluate Waveform Diagnostics on fresh generated fixtures (protocol declared first).

python -m scripts.evaluate_waveform_diagnostics [--out artifacts/waveform_diagnostics/v1]

Runs every fixture through the real API in an isolated temporary database and
folder. Stand-in recordings are simulated or rendered: this is not real-machine
accuracy. See artifacts/waveform_diagnostics/v1/protocol.json.
"""
import argparse
import hashlib
import io
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
KEYS = ('front_us', 'tail_us', 'crest_kv')


def setup(tmp):
    import os
    os.environ['IMPULSETWIN_DB'] = str(tmp / 'evaluation.sqlite3')
    from backend.app import main, storage
    from sqlalchemy import create_engine
    engine = create_engine('sqlite:///' + str(tmp / 'evaluation.sqlite3'), connect_args={'check_same_thread': False})
    storage.metadata.create_all(engine)
    storage.engine = engine
    main.ROOT = tmp
    from fastapi.testclient import TestClient
    return TestClient(main.app)


STOCK = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1}],
         'tail': [{'ohm': 520, 'count_per_stage': 1}], 'provenance': 'Evaluation assumption: one unit per value per stage'}
CPRI = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
            load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83)


def continuous(base, impulse, front_target, tail_target):
    """Front and tail resistance per stage solved (continuously) to the target times."""
    from backend.app.physics.circuit import simulate
    b = dict(base)

    def solve(key, metric, target):
        x = b[key]
        f = lambda lr: simulate(*{**b, key: math.exp(lr)}.values(), impulse, False)[metric] - target
        return math.exp(brentq(f, math.log(x / 20), math.log(x * 20), xtol=1e-10))
    for _ in range(5):
        b['front_r_stage'] = solve('front_r_stage', 'front_us', front_target)
        b['tail_r_stage'] = solve('tail_r_stage', 'tail_us', tail_target)
    return b


def make_settings(client):
    """Three reference sessions' runs and their as-fired declarations."""
    out = {}
    run = client.post('/api/optimize', json={**CPRI, 'impulse_type': 'Lightning', 'test_kv': 1425, 'inventory_override': STOCK}).json()
    out['cpri_lightning'] = {'run': run, 'as_fired': None, 'impulse': 'Lightning'}
    si_stock = {'front': [{'ohm': v, 'count_per_stage': 2} for v in (500, 1000, 2000, 4000)],
                'tail': [{'ohm': v, 'count_per_stage': 2} for v in (5000, 10000, 20000)], 'provenance': 'Evaluation assumption'}
    run = client.post('/api/optimize', json={**CPRI, 'impulse_type': 'Switching', 'test_kv': 1050, 'inventory_override': si_stock})
    assert run.status_code == 200, run.text
    out['cpri_switching'] = {'run': run.json(), 'impulse': 'Switching', 'targets': (250., 2500.)}
    run = client.post('/api/optimize', json={'profile_id': 'workbook_reference_profile', 'impulse_type': 'Lightning', 'test_kv': 1425,
                                             'solver': 'circuit', 'model_mode': 'physics'})
    assert run.status_code == 200, run.text
    out['workbook_lightning'] = {'run': run.json(), 'impulse': 'Lightning', 'targets': (1.2, 50.)}
    return out


def new_session(client, setting, as_fired='recommended', extra_values=None, uncertain=()):
    run = setting['run']
    view = client.post('/api/diagnostics', json={'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id']}).json()
    sid = view['session']['session_id']
    ref = view['reference']
    values = {}
    if setting.get('targets'):
        from backend.app.diagnostics.reference import circuit_args
        base = circuit_args(ref)
        solved = continuous(base, setting['impulse'], *setting['targets'])
        values.update(front_r_stage=solved['front_r_stage'], tail_r_stage=solved['tail_r_stage'])
    if as_fired == 'recommended':
        values.update(stages=ref['settings']['stages'], charge_kv_stage=ref['settings']['charge_kv_stage'])
    values.update(extra_values or {})
    if values:
        r = client.post(f'/api/diagnostics/{sid}/as-fired', json={'values': values, 'uncertain': list(uncertain)})
        assert r.status_code == 200, r.text
        view = r.json()
    return sid, view


def base_of(view):
    ref = view['reference']
    return dict((ref['as_fired'] or {}).get('prediction', ref['prediction'])['circuit_args'])


def times(impulse, t_end=None):
    if impulse == 'Lightning':
        end = t_end or 150.
        return np.r_[np.arange(-2, 0, .01), np.arange(0, 10, .005), np.arange(10, end, .05)]
    end = t_end or 12000.
    return np.r_[np.arange(-200, 0, 2.), np.arange(0, 1000, .5), np.arange(1000, end, 5.)]


def truth_curve(base, params, t, impulse):
    from backend.app.diagnostics.inverse import model_curve
    return model_curve(base, params, t)


def topology_variant(base, t, fraction=.4):
    """Independent ODE: part of the tail conductance at the load side (not the lumped model's topology)."""
    n = base['stages']; cg = base['stage_c_uf'] * 1e-6 / n; cl = base['total_c_pf'] * 1e-12
    rf = n * base['front_r_stage']; rt = n * base['tail_r_stage']; inductance = max(base['l_uh'], 1e-3) * 1e-6
    v0 = n * base['charge_kv_stage'] * base['efficiency']
    g_gen, g_load = (1 - fraction) / rt, fraction / rt

    def rhs(_, y):
        vg, current, vl = y
        return [(-current - g_gen * vg) / cg, (vg - rf * current - vl) / inductance, (current - g_load * vl) / cl]
    horizon = max(t) * 1e-6 * 1.05
    sol = solve_ivp(rhs, (0, horizon), [v0, 0, 0], method='Radau', rtol=1e-10, atol=1e-9 * v0, dense_output=True)
    v = sol.sol(np.clip(t, 0, None) * 1e-6)[2]
    return np.where(t > 0, v, 0.)


def csv_text(t, v):
    return 'time_us,voltage_kv\n' + '\n'.join(f'{a:.10g},{b:.10g}' for a, b in zip(t, v))


def run_csv(client, sid, text, **fields):
    data = {'origin': 'software_simulation', 'expected_polarity': 'positive', **fields}
    r = client.post(f'/api/diagnostics/{sid}/upload', data=data, files={'file': ('fixture.csv', text, 'text/csv')})
    if r.status_code != 200:
        return {'upload_error': r.json()['detail']}
    return diagnose(client, sid)


def diagnose(client, sid):
    from backend.app.diagnostics import jobs
    cmp = client.post(f'/api/diagnostics/{sid}/compare', json={})
    if cmp.status_code != 200:
        return {'compare_error': cmp.json()['detail']}
    comparison = cmp.json()['comparison']
    out = {'metrics': [{k: r.get(k) for k in ('metric', 'status', 'observed', 'predicted')} for r in comparison['metrics']],
           'quantitative_allowed': comparison['quantitative_allowed'],
           'normalized_mismatch': (comparison.get('whole_waveform') or {}).get('normalized_mismatch'),
           'plausibility': [p['code'] for p in comparison.get('plausibility') or []],
           'polarity_issue': bool(comparison.get('polarity_issue'))}
    started = client.post(f'/api/diagnostics/{sid}/investigate')
    if started.status_code != 200:
        out['investigation_refused'] = started.json()['detail'][:200]
        return out
    status = jobs.wait(started.json()['job_id'], 300)
    if status['state'] != 'finished':
        out['investigation_state'] = status['state']; out['error'] = status.get('error')
        return out
    inv = client.get(f'/api/diagnostics/{sid}').json()['investigation']
    out.update(verdict=inv['verdict']['label'], limited=bool(inv['verdict'].get('limited')), leading=inv['leading'],
               requires_review=bool(inv['verdict'].get('requires_review')),
               fitted={h['id']: h['parameters'] for h in inv['hypotheses'] if h['id'] in inv['leading']},
               findings=len(inv.get('findings') or []), elapsed_s=inv['elapsed_s'],
               residual_systematic=(inv.get('residual_structure') or {}).get('systematic'))
    return out


def fitted_error(result, hypothesis, truth):
    params = (result.get('fitted') or {}).get(hypothesis)
    if not params:
        return None
    errs = {}
    for name, value in truth.items():
        got = params.get(name)
        if got is None:
            return None
        allowance = 20. if name == 'extra_load_pf' else 2. if name == 'inductance_uh' else 0.
        errs[name] = {'truth': value, 'fitted': got, 'within_5pct': abs(got - value) <= max(.05 * abs(value), allowance)}
    return errs


def csv_cases(client, settings, rng):
    cases = []

    def add(family, name, setting_key, params=None, *, as_fired='recommended', extra=None, transform=None, fields=None,
            hypothesis=None, uncertain=(), af_values=None, curve=None, t_end=None):
        setting = settings[setting_key]
        sid, view = new_session(client, setting, as_fired, af_values, uncertain)
        base = base_of(view)
        if af_values and 'charge_kv_stage' in af_values:
            pass
        t = times(setting['impulse'], t_end)
        truth_base = dict(base)
        if as_fired == 'none' and af_values is None and params and 'charge_factor' in params:
            pass
        v = curve(truth_base, t) if curve else truth_curve(truth_base, params or {}, t, setting['impulse'])
        crest = float(np.max(np.abs(v)))
        if extra is not None:
            v = v + extra(t, crest)
        sigma = (fields or {}).pop('_noise', .003) if fields else .003
        v = v + rng.normal(0, sigma * crest, len(t))
        if transform:
            t, v = transform(t, v, crest)
        started = time.monotonic()
        result = run_csv(client, sid, csv_text(t, v), **(fields or {}))
        result.update(family=family, name=name, setting=setting_key, truth=params or {}, hypothesis=hypothesis,
                      wall_s=time.monotonic() - started)
        if hypothesis and params:
            result['fit_check'] = fitted_error(result, hypothesis, {k: v for k, v in params.items() if k != 'charge_factor'})
        cases.append(result)
        print(f"  {family:22s} {name:34s} -> {result.get('verdict', result.get('investigation_refused', result.get('compare_error', result.get('upload_error'))))!s:40.40s} {result.get('leading', '')}", flush=True)

    for key in settings:
        add('no_change', f'{key} unchanged', key)
    for params, hyp in [({'front_factor': .75}, 'front_network'), ({'front_factor': 1.3}, 'front_network'),
                        ({'tail_factor': .7}, 'tail_network'), ({'tail_factor': 1.35}, 'tail_network'),
                        ({'extra_load_pf': 350.}, 'effective_capacitance'), ({'extra_load_pf': -300.}, 'effective_capacitance'),
                        ({'inductance_uh': 35.}, 'inductance')]:
        add('single_in_model', f'cpri_lightning {params}', 'cpri_lightning', params, hypothesis=hyp)
    for key in ('cpri_switching', 'workbook_lightning'):
        add('single_in_model', f'{key} front 0.8', key, {'front_factor': .8}, hypothesis='front_network')
        add('single_in_model', f'{key} tail 1.25', key, {'tail_factor': 1.25}, hypothesis='tail_network')
    add('combined_in_model', 'front 0.85 + tail 1.2', 'cpri_lightning', {'front_factor': .85, 'tail_factor': 1.2}, hypothesis='front_and_tail')
    add('combined_in_model', 'capacitance +300 + inductance 30', 'cpri_lightning', {'extra_load_pf': 300., 'inductance_uh': 30.},
        hypothesis='capacitance_and_inductance')
    add('ambiguous_amplitude', 'gain 0.94, as-fired recorded', 'cpri_lightning', {'gain': .94})
    add('ambiguous_amplitude', 'charge 0.95, as-fired not recorded', 'cpri_lightning', {'charge_factor': .95}, as_fired='none')
    osc = lambda t, c: np.where(t > 0, .06 * c * np.sin(2 * np.pi * 4 * t) * np.exp(-t / 2.), 0)
    slow = lambda t, c: np.where(t > 0, .12 * c * (1 - np.exp(-t / 30.)), 0)
    add('off_model', '(a) 4 MHz oscillation', 'cpri_lightning', extra=osc)
    add('off_model', '(b) slow second tail component', 'cpri_lightning', extra=slow)
    add('off_model', '(c) oscillation and slow tail', 'cpri_lightning', extra=lambda t, c: osc(t, c) + slow(t, c))
    add('off_model', '(d) precursor 35%', 'cpri_lightning', extra=lambda t, c: .35 * c * np.exp(-.5 * ((t + .1) / .03) ** 2))
    add('topology_variant', '40% of tail at load side', 'cpri_lightning', curve=lambda b, t: topology_variant(b, t))
    add('noise_and_scale', 'noise 1.5% + front 0.8', 'cpri_lightning', {'front_factor': .8}, hypothesis='front_network',
        fields={'_noise': .015})
    add('noise_and_scale', 'gain 1.03', 'cpri_lightning', {'gain': 1.03})
    add('negative_polarity', 'negative declared positive', 'cpri_lightning', transform=lambda t, v, c: (t, -v))
    add('ringing_in_model', 'L 80 uH, front x0.25', 'cpri_lightning', {'inductance_uh': 80., 'front_factor': .25})
    add('clipping', 'clipped at 92% of crest', 'cpri_lightning', transform=lambda t, v, c: (t, np.minimum(v, .92 * c)))
    add('missing_falling_limb', 'record ends at 20 us', 'cpri_lightning', t_end=20.)
    charge = settings['cpri_lightning']['run']['candidates'][0]['settings']['charge_kv_stage']
    add('different_settings', '95% charge, as-fired recorded', 'cpri_lightning', as_fired='recommended',
        af_values={'charge_kv_stage': .95 * charge})
    add('different_settings', '95% charge, not recorded', 'cpri_lightning', {'charge_factor': .95}, as_fired='none')
    add('unit_mistake', 'ms labelled as us', 'cpri_lightning', transform=lambda t, v, c: (t * 1000, v))
    return cases


def image_cases(client, settings, out_folder):
    from backend.app.diagnostics import render
    from PIL import Image, ImageDraw
    setting = settings['cpri_lightning']
    cases = []
    manual = out_folder / 'manual'
    manual.mkdir(parents=True, exist_ok=True)

    def add(name, params=None, *, size=(1600, 900), width=1.4, time_range=(-1, 60), voltage_range=(-100, 1600), second=None,
            photo=False, scope=False, overlay=False, t_end=None):
        sid, view = new_session(client, setting)
        base = base_of(view)
        end = t_end or time_range[1]
        t = np.r_[np.linspace(0, 10, 5000), np.linspace(10, end, 3000)]
        v = truth_curve(base, params or {}, t, 'Lightning')
        from backend.app.physics.circuit import simulate
        from backend.app.diagnostics.inverse import model_metrics
        truth_m = model_metrics(base, params or {}, 'Lightning')[0]
        curves = []
        if second:
            curves.append({'t': np.r_[time_range[0], 0, t], 'v': np.r_[0, 0, .8 * v], 'color': second, 'width': width})
        curves.append({'t': np.r_[time_range[0], 0, t], 'v': np.r_[0, 0, v], 'color': '#f0d020' if scope else '#1d4ed8', 'width': width})
        ticks = {'x': list(np.linspace(time_range[0], time_range[1], 11)), 'y': list(np.linspace(voltage_range[0], voltage_range[1], 9))} if scope else None
        png, truth = render.render_plot(curves, time_range=time_range, voltage_range=voltage_range, size=size,
                                        style='scope' if scope else 'plot', ticks=ticks)
        transforms = {}
        data = png
        if photo:
            pb = truth['plot_box']
            data, forward = render.warp(png, [(80, 110), (size[0] - 60, 50), (size[0] - 10, size[1] + 20), (40, size[1] - 40)], quality=80)
            from backend.app.diagnostics.imaging import map_points
            transforms = {'corners': map_points(forward, [(pb[0], pb[1]), (pb[2], pb[1]), (pb[2], pb[3]), (pb[0], pb[3])]).tolist()}
        up = client.post(f'/api/diagnostics/{sid}/upload', data={'origin': 'demonstration', 'expected_polarity': 'positive'},
                         files={'file': ('fixture.' + ('jpg' if photo else 'png'), data, 'image/jpeg' if photo else 'image/png')})
        assert up.status_code == 200, up.text
        preview = client.post(f'/api/diagnostics/{sid}/image/preview', json=transforms).json()
        W, H = preview['transform']['working_size']
        if photo:
            axes = {'mode': 'anchors', 'x_anchors': [{'px': 0, 'value': time_range[0]}, {'px': W, 'value': time_range[1]}],
                    'y_anchors': [{'px': H, 'value': voltage_range[0]}, {'px': 0, 'value': voltage_range[1]}]}
            plot_box = [2, 2, W - 2, H - 2]
            to_px = lambda tt, vv: ((tt - time_range[0]) / (time_range[1] - time_range[0]) * W, H - (vv - voltage_range[0]) / (voltage_range[1] - voltage_range[0]) * H)
        elif scope:
            pb = truth['plot_box']
            axes = {'mode': 'per_division', 'grid': {'left_px': pb[0], 'right_px': pb[2], 'top_px': pb[1], 'bottom_px': pb[3],
                    'divisions_x': 10, 'divisions_y': 8, 'time_per_div': (time_range[1] - time_range[0]) / 10, 'time_at_left': time_range[0],
                    'volts_per_div': (voltage_range[1] - voltage_range[0]) / 8, 'value_at_center': (voltage_range[0] + voltage_range[1]) / 2}}
            plot_box = pb
            to_px = lambda tt, vv: render.pixel_of(truth, tt, vv)
        else:
            x0, t0, x1, t1 = truth['x']; y0, v0, y1, v1 = truth['y']
            axes = {'mode': 'anchors', 'x_anchors': [{'px': x0, 'value': t0}, {'px': x1, 'value': t1}],
                    'y_anchors': [{'px': y0, 'value': v0}, {'px': y1, 'value': v1}]}
            plot_box = truth['plot_box']
            to_px = lambda tt, vv: render.pixel_of(truth, tt, vv)
        axes.update(time_unit='us', voltage_unit='kV', voltage_side='high_voltage', divider_ratio=1, anchor_uncertainty_px=1)
        seed_t = min(15., .7 * end)
        seed = list(to_px(seed_t, float(np.interp(seed_t, t, v))))
        d = client.post(f'/api/diagnostics/{sid}/digitize', json={'transforms': transforms, 'plot_box': plot_box, 'seed': seed,
                                                                  'axes': axes, 'expected_polarity': 'positive'})
        if d.status_code != 200:
            cases.append({'family': 'image', 'name': name, 'digitize_error': d.json()['detail']})
            print(f'  image {name:40s} -> digitize error: {d.json()["detail"][:80]}')
            return
        dig = d.json()['digitization']
        q = dig['quality']
        m = dig['analysis'].get('metrics') or dig['analysis'].get('partial') or {}
        avail = q['metric_availability']
        errors = {}
        spread = q.get('digitization_spread') or {}
        for key, gate in (('front_us', 'front'), ('tail_us', 'tail'), ('crest_kv', 'crest')):
            if avail.get(gate) and m.get(key) is not None:
                inside = (spread.get('available') and spread['p05'][key] <= truth_m[key] <= spread['p95'][key]) if spread else None
                errors[key] = {'truth': truth_m[key], 'digitized': m[key], 'error_pct': 100 * (m[key] / truth_m[key] - 1),
                               'spread_contains_truth': inside}
        result = {'family': 'image', 'name': name, 'truth': params or {}, 'metric_errors': errors,
                  'flags': [f['code'] for f in q['flags']], 'quantitative_allowed': q['quantitative_comparison_allowed'],
                  'availability': avail, 'samples': q['trace']['samples']}
        result.update({f'diagnosis_{k}': v for k, v in diagnose(client, sid).items() if k in ('verdict', 'leading', 'metrics', 'investigation_refused', 'quantitative_allowed')})
        if overlay:
            # Draw the extracted samples over the working image for the manual check.
            import base64
            img = Image.open(io.BytesIO(base64.b64decode(preview['png_base64']))).convert('RGB')
            scale = preview['preview_scale']
            draw = ImageDraw.Draw(img)
            pts = [(x * scale, y * scale) for x, y in dig['overlay']['working_px']]
            for x, y in pts[::1]:
                draw.ellipse([x - 1.2, y - 1.2, x + 1.2, y + 1.2], fill=(230, 40, 40))
            path = manual / f"{name.replace(' ', '_').replace('/', '_')}.png"
            img.save(path)
            result['overlay_png'] = str(path.relative_to(out_folder))
        cases.append(result)
        summary = ', '.join('%s: %+.2f%%' % (k, e['error_pct']) for k, e in errors.items())
        verdict = result.get('diagnosis_verdict', result.get('diagnosis_investigation_refused', ''))
        print(f"  image {name:40s} -> flags {result['flags']} errors {{{summary}}} {str(verdict)[:40]}", flush=True)

    add('clean', overlay=True)
    add('low resolution', size=(480, 300))
    add('thick trace', width=6, overlay=True)
    add('second curve other colour', second='#d03030')
    add('second curve same colour', second='#1d4ed8', overlay=True)
    add('perspective photo', photo=True, overlay=True)
    add('oscilloscope per-division', scope=True, time_range=(-6, 54), voltage_range=(-800, 1600))
    add('clipped display', voltage_range=(-100, 1300))
    add('record ends at 20 us', time_range=(-1, 20))
    add('front x0.8 clean', {'front_factor': .8})
    return cases


def gates(csv, images):
    by = lambda fam: [c for c in csv if c['family'] == fam]
    g = {}
    g['G1_no_change'] = all(c.get('verdict') == 'No change needed' for c in by('no_change'))
    singles = by('single_in_model')
    ok = []
    for c in singles:
        identified = c.get('hypothesis') in (c.get('leading') or [])
        close = c.get('fit_check') and all(e['within_5pct'] for e in c['fit_check'].values())
        ok.append(bool(identified and close))
    g['G2_single_identified'] = {'pass': sum(ok) >= .8 * len(ok), 'identified_and_within_5pct': f'{sum(ok)}/{len(ok)}'}
    hardware = {'front_network', 'tail_network', 'effective_capacitance', 'inductance', 'front_and_tail', 'capacitance_and_inductance', 'front_and_capacitance'}
    g['G3_no_confident_false_cause'] = all(not (c.get('verdict') == 'Possible cause' and len(c.get('leading') or []) == 1
                                                and c['leading'][0] in hardware) for c in by('off_model'))
    g['G4_amplitude_competition'] = all(c.get('verdict') != 'Possible cause' and len(c.get('leading') or []) >= 2 for c in by('ambiguous_amplitude'))
    reported = []
    for c in images:
        if c['name'] in ('clean', 'perspective photo', 'oscilloscope per-division'):
            for key, e in c.get('metric_errors', {}).items():
                limit = {'crest_kv': 1.5, 'tail_us': 3., 'front_us': 6.}[key]
                reported.append((abs(e['error_pct']) <= limit, e['spread_contains_truth']))
    g['G5_image_round_trip'] = {'pass': bool(reported) and all(a for a, _ in reported) and sum(bool(b) for _, b in reported) >= 2 / 3 * len(reported),
                                'within_limits': f'{sum(a for a, _ in reported)}/{len(reported)}',
                                'spread_contains_truth': f'{sum(bool(b) for _, b in reported)}/{len(reported)}'}
    def guarded(c):
        if not c.get('quantitative_allowed', True):
            return True
        return all(m['status'] in ('Requires review', 'Insufficient capture') for m in c.get('metrics', []))
    integrity = by('clipping') + by('negative_polarity') + by('unit_mistake')
    img_integrity = [c for c in images if c['name'] in ('second curve same colour', 'clipped display')]
    g['G6_integrity'] = all(guarded(c) for c in integrity) and all(not c.get('quantitative_allowed', True) or not c.get('availability', {}).get('crest', True) for c in img_integrity)
    tails = [m for c in by('missing_falling_limb') for m in c.get('metrics', []) if m['metric'] == 'tail_us']
    img_tail = [c for c in images if c['name'] == 'record ends at 20 us']
    g['G7_no_extrapolation'] = all(m['observed'] is None for m in tails) and all(not c.get('availability', {}).get('tail', False) for c in img_tail)
    diff = by('different_settings')
    recorded = [c for c in diff if 'as-fired recorded' in c['name']]
    unrecorded = [c for c in diff if 'not recorded' in c['name']]
    g['G8_settings_difference'] = (all(c.get('verdict') == 'No change needed' for c in recorded)
                                   and all(c.get('limited') and 'charge' in (c.get('leading') or []) for c in unrecorded))
    flat = {k: (v['pass'] if isinstance(v, dict) else v) for k, v in g.items()}
    g['all_pass'] = all(flat.values())
    return g


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'artifacts/waveform_diagnostics/v1'))
    args = parser.parse_args()
    out = Path(args.out)
    protocol_path = out / 'protocol.json'
    protocol = json.loads(protocol_path.read_text())
    rng = np.random.default_rng(protocol['seed'])
    started = time.time()
    with tempfile.TemporaryDirectory() as folder:
        client = setup(Path(folder))
        settings = make_settings(client)
        print('CSV fixtures'); csv = csv_cases(client, settings, rng)
        print('Image fixtures'); images = image_cases(client, settings, out)
    result = {'version': protocol['version'], 'protocol_sha256': hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
              'evidence_type': protocol['evidence_type'], 'seed': protocol['seed'], 'csv_cases': csv, 'image_cases': images,
              'gates': gates(csv, images), 'elapsed_s': time.time() - started,
              'not_established': protocol['not_established'],
              'case_revisions': json.loads((out / 'case_revisions.json').read_text()) if (out / 'case_revisions.json').exists() else []}
    (out / 'results.json').write_text(json.dumps(result, indent=1, default=float))
    print(json.dumps(result['gates'], indent=1))


if __name__ == '__main__':
    main()
