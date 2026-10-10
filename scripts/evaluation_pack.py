"""Reproducible evaluation pack for unknown judge inputs.

  python -m scripts.evaluation_pack --output artifacts/evaluation_pack/v1

Every case is a full optimizer request. Recommended settings are re-simulated
with the independent charge/flux integrator (same topology, different numerics),
compared with what the application displays, and checked against hardware limits.
Simulation agreement is reported separately from measured performance (none).
"""
import argparse
import hashlib
import json
import math
import platform
import statistics
import time
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from backend.app.data.workbook_reference import calculate
from backend.app.optimization.engine import optimize, resolve_profile, stock_for
from backend.app.optimization.surrogate_search import selector, exhaustive_selector, catalogue_size
from backend.app.physics.circuit import simulate
from backend.app.physics.compliance import check, RULES
from backend.app.schemas import OptimizeRequest
from scripts.independent_impulse_reference import solve as independent_solve

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('front_us', 'tail_us', 'crest_kv')

ONE = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1}, {'ohm': 3700, 'count_per_stage': 1}],
       'tail': [{'ohm': 520, 'count_per_stage': 1}, {'ohm': 22000, 'count_per_stage': 1}],
       'provenance': 'Evaluation assumption: one unit per CPRI source value per stage'}
TWO = {**ONE, 'front': [{**i, 'count_per_stage': 2} for i in ONE['front']], 'tail': [{**i, 'count_per_stage': 2} for i in ONE['tail']],
       'provenance': 'Evaluation assumption: two units per CPRI source value per stage'}
RICH = {**ONE, 'front': [{**i, 'count_per_stage': 4} for i in ONE['front']], 'tail': [{**i, 'count_per_stage': 4} for i in ONE['tail']],
        'provenance': 'Evaluation assumption: four units per CPRI source value per stage'}
CPRI = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
            load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83)
LAB = {'name': 'Evaluation 6-stage 600 kV', 'source': 'Evaluation fixture ratings', 'max_stages': 6, 'stage_kv': 100,
       'stage_c_uf': .5, 'energy_stage_kj': 2.5, 'energy_total_kj': 15}
LAB_STOCK = {'front': [{'ohm': 20, 'count_per_stage': 2}, {'ohm': 50, 'count_per_stage': 2}, {'ohm': 100, 'count_per_stage': 1}],
             'tail': [{'ohm': 400, 'count_per_stage': 2}, {'ohm': 800, 'count_per_stage': 1}, {'ohm': 10000, 'count_per_stage': 2},
                      {'ohm': 33000, 'count_per_stage': 2}],
             'provenance': 'Evaluation assumption: counted stock'}
CUSTOM = dict(profile_id='custom_generator', custom_profile=LAB, inventory_override=LAB_STOCK, solver='circuit',
              model_mode='physics', load_c_pf=800, divider_c_pf=300, stray_c_pf=100, l_uh=8, efficiency=.95)
WORKBOOK = dict(profile_id='workbook_reference_profile')
WB_SI = dict(WORKBOOK, impulse_type='Switching', test_kv=1025, load_c_pf=1240, divider_c_pf=740, stray_c_pf=320)


def case(cid, group, description, request, expect='recommendation'):
    return {'id': cid, 'group': group, 'description': description, 'request': request, 'expect': expect}


CASES = [
    # CPRI Lightning, low/typical/high voltages
    case('cpri-li-300', 'voltage', 'CPRI LI, low voltage', {**CPRI, 'test_kv': 300, 'inventory_override': ONE}),
    case('cpri-li-900', 'voltage', 'CPRI LI, mid voltage', {**CPRI, 'test_kv': 900, 'inventory_override': ONE}),
    case('cpri-li-1425', 'voltage', 'CPRI LI, matched example', {**CPRI, 'test_kv': 1425, 'inventory_override': ONE}),
    case('cpri-li-1650', 'voltage', 'CPRI LI, high feasible voltage', {**CPRI, 'test_kv': 1650, 'inventory_override': ONE}),
    case('cpri-li-1900', 'rejection', 'CPRI LI 1900 kV: above the circuit-reachable crest (about 1.71 MV at 200 kV/stage and loss factor 0.83)',
         {**CPRI, 'test_kv': 1900, 'inventory_override': ONE}, 'rejection'),
    # CPRI Switching
    case('cpri-si-300', 'voltage', 'CPRI SI, low voltage', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 300, 'inventory_override': ONE}),
    case('cpri-si-800', 'voltage', 'CPRI SI, mid voltage', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 800, 'inventory_override': ONE}),
    case('cpri-si-1050', 'voltage', 'CPRI SI, typical', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 1050, 'inventory_override': ONE}),
    case('cpri-si-1500', 'voltage', 'CPRI SI, high voltage', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 1500, 'inventory_override': ONE}),
    # Loads and parasitics
    case('cpri-li-small-load', 'parasitics', 'CPRI LI, 300 pF object, 5 µH', {**CPRI, 'test_kv': 1425, 'load_c_pf': 300, 'l_uh': 5, 'inventory_override': ONE}),
    case('cpri-li-large-load', 'parasitics', 'CPRI LI, 2000 pF object, 500 pF divider, 30 µH',
         {**CPRI, 'test_kv': 1425, 'load_c_pf': 2000, 'divider_c_pf': 500, 'stray_c_pf': 150, 'l_uh': 30, 'inventory_override': ONE}),
    case('cpri-li-no-base', 'parasitics', 'CPRI LI, 545 pF base excluded', {**CPRI, 'test_kv': 1425, 'include_base_c': False, 'inventory_override': ONE}),
    case('cpri-si-large-load', 'parasitics', 'CPRI SI, 2000 pF object, 30 µH',
         {**CPRI, 'impulse_type': 'Switching', 'test_kv': 1050, 'load_c_pf': 2000, 'l_uh': 30, 'inventory_override': ONE}),
    case('cpri-li-eff-1', 'parasitics', 'CPRI LI, no extra loss factor (efficiency 1.0)', {**CPRI, 'test_kv': 1425, 'efficiency': 1.0, 'inventory_override': ONE}),
    # Stage constraints and stock quantities
    case('cpri-li-stages-6-8', 'constraints', 'CPRI LI 1200 kV limited to 6-8 stages',
         {**CPRI, 'test_kv': 1200, 'stage_min': 6, 'stage_max': 8, 'inventory_override': ONE}),
    case('cpri-li-two-units', 'stock', 'CPRI LI, two units per value', {**CPRI, 'test_kv': 1425, 'inventory_override': TWO}),
    case('cpri-li-four-units', 'stock', 'CPRI LI, four units per value', {**CPRI, 'test_kv': 1425, 'inventory_override': RICH}),
    case('cpri-si-two-units', 'stock', 'CPRI SI, two units per value', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 1050, 'inventory_override': TWO}),
    case('cpri-si-four-units', 'stock', 'CPRI SI, four units per value', {**CPRI, 'impulse_type': 'Switching', 'test_kv': 1050, 'inventory_override': RICH}),
    # Workbook profile: inside / outside ML support, both engines
    case('wb-li-ref-in-support', 'ml_support', 'Workbook LI default, reference engine with V1 (in support)', {**WORKBOOK}),
    case('wb-li-ref-outside', 'ml_support', 'Workbook LI with 40 µH, outside V1 support', {**WORKBOOK, 'l_uh': 40}),
    case('wb-si-ref', 'ml_support', 'Workbook SI preset, reference engine', {**WB_SI}),
    case('wb-li-circuit', 'engine', 'Workbook LI, circuit engine', {**WORKBOOK, 'solver': 'circuit', 'model_mode': 'physics'}),
    case('wb-si-circuit', 'engine', 'Workbook SI, circuit engine', {**WB_SI, 'solver': 'circuit', 'model_mode': 'physics'}),
    case('wb-li-low', 'voltage', 'Workbook LI 400 kV, circuit engine', {**WORKBOOK, 'test_kv': 400, 'solver': 'circuit', 'model_mode': 'physics'}),
    case('wb-li-high', 'voltage', 'Workbook LI 2250 kV, circuit engine (high feasible)', {**WORKBOOK, 'test_kv': 2250, 'solver': 'circuit', 'model_mode': 'physics'}),
    case('wb-li-2600', 'rejection', 'Workbook LI 2600 kV, circuit engine: above the circuit-reachable crest (about 2.36 MV)',
         {**WORKBOOK, 'test_kv': 2600, 'solver': 'circuit', 'model_mode': 'physics'}, 'rejection'),
    # Custom generator of the supported topology
    case('custom-li-400', 'custom', 'Custom 6-stage generator LI 400 kV', {**CUSTOM, 'test_kv': 400}),
    case('custom-si-300', 'custom', 'Custom 6-stage generator SI 300 kV', {**CUSTOM, 'impulse_type': 'Switching', 'test_kv': 300}),
    # Hardware violations and unsupported configurations: a rejection is the correct outcome
    case('cpri-li-2800', 'rejection', 'CPRI LI above the 2400 kV profile limit', {**CPRI, 'test_kv': 2800, 'inventory_override': ONE}, 'rejection'),
    case('cpri-li-3-stages', 'rejection', 'CPRI LI 1425 kV restricted to 2-3 stages', {**CPRI, 'test_kv': 1425, 'stage_max': 3, 'inventory_override': ONE}, 'rejection'),
    case('cpri-no-stock', 'rejection', 'CPRI without counted stock', {**CPRI, 'test_kv': 1425}, 'rejection'),
    case('briefing-3mv', 'rejection', 'Incomplete 3 MV briefing profile', {'profile_id': 'briefing_3mv_profile', 'test_kv': 1425}, 'rejection'),
    case('custom-energy-too-low', 'rejection', 'Custom generator, 590 kV with 2 kJ/stage rating',
         {**CUSTOM, 'custom_profile': {**LAB, 'energy_stage_kj': 2.0, 'energy_total_kj': 12}, 'test_kv': 590}, 'rejection'),
    case('custom-inconsistent-rating', 'rejection', 'Custom generator whose stage energy exceeds 0.5 C V²',
         {**CUSTOM, 'custom_profile': {**LAB, 'energy_stage_kj': 9}, 'test_kv': 400}, 'rejection'),
    case('agreement-with-circuit', 'rejection', 'Agreement search requested with the circuit engine',
         {**CPRI, 'test_kv': 1425, 'require_model_agreement': True, 'inventory_override': ONE}, 'rejection'),
]


def independent(run, c, waveform=False):
    p, i, s = run['profile'], run['inputs'], c['settings']
    total = i['load_c_pf'] + i['divider_c_pf'] + i['stray_c_pf'] + ((p.get('base_c_pf') or 0) if i['include_base_c'] else 0)
    return independent_solve({'stages': s['stages'], 'charge_kv_stage': s['charge_kv_stage'], 'front_r_stage': s['front_r_stage'],
                              'tail_r_stage': s['tail_r_stage'], 'stage_c_uf': p['stage_c_uf'], 'total_c_pf': total,
                              'l_uh': i['l_uh'], 'efficiency': i['efficiency'], 'impulse_type': i['impulse_type']}, waveform=waveform)


def waveform_error(displayed, reference):
    """Normalized RMS: sqrt(mean((v_shown - v_ref)^2)) / crest_ref over 0..2·t50_ref at 600 points."""
    t_ref, v_ref = np.asarray(reference['time_us']), np.asarray(reference['voltage_kv'])
    crest = v_ref.max()
    t50 = t_ref[np.flatnonzero(v_ref >= .5*crest)[-1]]
    grid = np.linspace(0, 2*t50, 600)
    shown = np.interp(grid, displayed['time_us'], displayed['voltage_kv'])
    ref = np.interp(grid, t_ref, v_ref)
    return {'nrmse_pct': float(100*np.sqrt(np.mean((shown - ref)**2))/crest),
            'max_abs_pct_of_crest': float(100*np.max(np.abs(shown - ref))/crest)}


def hardware_ok(run, c):
    p, s = run['profile'], c['settings']
    e_stage = .5*p['stage_c_uf']*1e-6*(s['charge_kv_stage']*1e3)**2/1e3
    return bool(s['charge_kv_stage'] <= p['stage_kv'] + 1e-9 and e_stage <= p['energy_stage_kj'] + 1e-9
                and s['stages']*e_stage <= p['energy_total_kj'] + 1e-9 and p['min_stages'] <= s['stages'] <= p['max_stages'])


def candidate_record(run, c):
    i = run['inputs']
    ref = independent(run, c, waveform=True)
    shown = {k: c['hybrid'][k] for k in KEYS}
    truth = {k: ref[k] for k in KEYS}
    shown_pass = c['compliance']['nominal_pass']
    true_pass = check(i['impulse_type'], i['test_kv'], truth)['nominal_pass']
    return {'rank': c['rank'], 'settings': c['settings'], 'front_topology': c['front_network']['topology'],
            'tail_topology': c['tail_network']['topology'], 'displayed': shown, 'independent_circuit': truth,
            'relative_error_pct': {k: 100*(shown[k]/truth[k] - 1) for k in KEYS},
            'waveform_error': waveform_error(c['waveform'], ref['waveform']) if c.get('waveform') else None,
            'displayed_curve': (c.get('waveform') or {}).get('kind'),
            'displayed_pass': shown_pass, 'independent_pass': true_pass,
            'false_pass': bool(shown_pass and not true_pass), 'false_fail': bool(true_pass and not shown_pass),
            'hardware_within_ratings': hardware_ok(run, c),
            'ml_trust_weight': c['ood']['trust_weight'], 'ml_support': c['ood']['state'],
            'consistency': c['waveform_consistency']['consistent']}


def workbook_baseline(req, run):
    """What the supplied workbook calculator recommends, judged by the circuit (stock ignored)."""
    p = run['profile']
    ref = calculate(impulse_type=req.impulse_type, test_kv=req.test_kv, load_c_pf=req.load_c_pf, divider_c_pf=req.divider_c_pf,
                    stray_c_pf=req.stray_c_pf + ((p.get('base_c_pf') or 0) if req.include_base_c else 0), l_uh=req.l_uh,
                    efficiency=req.efficiency, max_stages=p['max_stages'], max_stage_kv=p['stage_kv'], stage_c_uf=p['stage_c_uf'])
    if not ref['physics_feasible'] or ref['front_r_stage'] <= 0 or ref['tail_r_stage'] <= 0:
        return {'status': 'calculator infeasible'}
    total = req.load_c_pf + req.divider_c_pf + req.stray_c_pf + ((p.get('base_c_pf') or 0) if req.include_base_c else 0)
    try:
        sim = simulate(ref['stages'], ref['charge_kv_stage'], ref['front_r_stage'], ref['tail_r_stage'], p['stage_c_uf'], total,
                       req.l_uh, req.efficiency, req.impulse_type, False)
    except ValueError as exc:
        return {'status': 'unresolved', 'error': str(exc)}
    verdict = check(req.impulse_type, req.test_kv, sim)
    return {'status': 'simulated', 'settings': {k: ref[k] for k in ['stages', 'charge_kv_stage', 'front_r_stage', 'tail_r_stage']},
            'circuit_metrics': {k: sim[k] for k in KEYS}, 'circuit_nominal_pass': verdict['nominal_pass'],
            'deviation_pct': {k: 100*(sim[k]/t - 1) for k, t in zip(KEYS, [RULES[req.impulse_type]['front_target_us'],
                                                                         RULES[req.impulse_type]['tail_target_us'], req.test_kv])},
            'stock_checked': False}


def top_key(run):
    c = run['candidates'][0]
    return [not c['compliance']['nominal_pass'], not c['compliance']['robust_pass'], round(c['score'], 9)]


def run_case(item, surrogate_selector):
    record = {k: item[k] for k in ['id', 'group', 'description', 'expect']}
    try:
        req = OptimizeRequest(**item['request'])
    except ValidationError as exc:
        record.update(outcome='rejected', stage='request_validation', reason=exc.errors()[0]['msg'],
                      correct=item['expect'] == 'rejection')
        return record
    started = time.perf_counter()
    try:
        run = optimize(req)
    except ValueError as exc:
        record.update(outcome='rejected', stage='optimizer', reason=str(exc), runtime_s=time.perf_counter() - started,
                      correct=item['expect'] == 'rejection')
        return record
    runtime = time.perf_counter() - started
    record.update(outcome='recommendation', runtime_s=runtime, correct=item['expect'] == 'recommendation',
                  profile=run['profile']['id'], impulse_type=req.impulse_type, engine=req.solver,
                  test_kv=req.test_kv, top_status=run['candidates'][0]['compliance']['status'],
                  search=run['search'], candidates=[candidate_record(run, c) for c in run['candidates'][:3]])
    record['baseline_workbook_calculator'] = workbook_baseline(req, run)
    p = resolve_profile(req)
    if req.solver == 'circuit':
        front_stock, tail_stock, _ = stock_for(req, p)
        sizes = catalogue_size(req, front_stock, tail_stock)
        record['catalogue_networks'] = {'front': sizes[0], 'tail': sizes[1]}
        if sizes[0]*sizes[1] <= 400:
            t0 = time.perf_counter()
            exhaustive = optimize(req, _network_selector=exhaustive_selector())
            record['exhaustive'] = {'runtime_s': time.perf_counter() - t0, 'evaluated': exhaustive['search']['evaluated'],
                                    'top_key': top_key(exhaustive), 'bounded_top_key': top_key(run),
                                    'top1_agrees': exhaustive['candidates'][0]['settings'] == run['candidates'][0]['settings'],
                                    'bounded_top1_in_exhaustive_top3': any(c['settings'] == run['candidates'][0]['settings']
                                                                           for c in exhaustive['candidates'][:3]),
                                    'objective_gap': run['candidates'][0]['score'] - exhaustive['candidates'][0]['score'],
                                    'same_nominal_status': run['candidates'][0]['compliance']['nominal_pass'] == exhaustive['candidates'][0]['compliance']['nominal_pass']}
        if surrogate_selector is not None:
            t0 = time.perf_counter()
            expanded = optimize(req, _network_selector=surrogate_selector)
            key, base = top_key(expanded), top_key(run)
            record['surrogate_expanded'] = {'runtime_s': time.perf_counter() - t0, 'evaluated': expanded['search']['evaluated'],
                                            'top_key': key, 'current_top_key': base,
                                            'equal_or_better': key <= base, 'strictly_better': key < base,
                                            'top1_settings': expanded['candidates'][0]['settings'],
                                            'top1_independent_pass': candidate_record(expanded, expanded['candidates'][0])['independent_pass']}
    return record


def stats(values):
    values = sorted(abs(v) for v in values)
    if not values:
        return None
    return {'n': len(values), 'median': statistics.median(values), 'p95': float(np.percentile(values, 95)), 'worst': values[-1]}


def aggregate(records):
    groups = {}
    for r in records:
        if r['outcome'] != 'recommendation':
            continue
        key = f"{r['profile']} | {r['impulse_type']} | {r['engine']}"
        g = groups.setdefault(key, {'cases': 0, 'candidates': [], 'runtime': []})
        g['cases'] += 1; g['runtime'].append(r['runtime_s']); g['candidates'] += r['candidates']
    summary = {}
    for key, g in groups.items():
        cands = g['candidates']
        summary[key] = {
            'cases': g['cases'], 'candidates_checked': len(cands),
            'crest_error_pct': stats([c['relative_error_pct']['crest_kv'] for c in cands]),
            'front_or_peak_error_pct': stats([c['relative_error_pct']['front_us'] for c in cands]),
            'tail_error_pct': stats([c['relative_error_pct']['tail_us'] for c in cands]),
            'waveform_nrmse_pct': stats([c['waveform_error']['nrmse_pct'] for c in cands if c['waveform_error']]),
            'false_passes': sum(c['false_pass'] for c in cands), 'false_fails': sum(c['false_fail'] for c in cands),
            'independent_passes': sum(c['independent_pass'] for c in cands),
            'hardware_violations': sum(not c['hardware_within_ratings'] for c in cands),
            'runtime_s': stats(g['runtime'])}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/evaluation_pack/v1')
    parser.add_argument('--no-surrogate', action='store_true')
    args = parser.parse_args()
    surrogate = None
    surrogate_summary = ROOT/'artifacts/models/circuit_surrogate_v1/summary.json'
    if not args.no_surrogate and surrogate_summary.exists() and json.loads(surrogate_summary.read_text())['screening_use_allowed']:
        surrogate = selector()
    started = time.time()
    records = []
    for item in CASES:
        records.append(run_case(item, surrogate))
        r = records[-1]
        print(f"{r['id']:28s} {r['outcome']:15s} correct={r['correct']} {r.get('top_status', r.get('reason', ''))[:70]}", flush=True)
    recs = [r for r in records if r['outcome'] == 'recommendation']
    exhaustive = [r['exhaustive'] for r in recs if 'exhaustive' in r]
    expanded = [r['surrogate_expanded'] for r in recs if 'surrogate_expanded' in r]
    baseline = [r['baseline_workbook_calculator'] for r in recs if r['baseline_workbook_calculator'].get('status') == 'simulated']
    current_runtimes = [r['runtime_s'] for r in recs if 'surrogate_expanded' in r]
    result = {
        'version': 'evaluation-pack-v1', 'cases': len(records),
        'case_revisions': ['After the first run, cpri-li-1900 and workbook 2600 kV were found to exceed the crest the circuit can reach '
                           'within the stage-voltage rating; their expected outcome was corrected to rejection and feasible high-voltage '
                           'cases (CPRI 1650 kV, workbook 2250 kV) were added. No model, search or limit was changed.'],
        'case_definitions_sha256': hashlib.sha256(json.dumps(CASES, sort_keys=True).encode()).hexdigest(),
        'outcomes': {'recommendations': len(recs), 'rejections': len(records) - len(recs),
                     'expected_outcome_matched': sum(r['correct'] for r in records)},
        'simulation_agreement_by_profile': aggregate(records),
        'error_definitions': {
            'relative_error_pct': '100 × (displayed metric / independent re-simulation − 1) for the top three candidates.',
            'waveform_nrmse_pct': 'sqrt(mean((displayed − independent)²)) / independent crest over 0–2·t50 at 600 points.',
            'false_pass': 'Displayed nominal PASS while the independent re-simulation FAILS a challenge limit.'},
        'recommendation_quality': {
            'exhaustive_comparisons': len(exhaustive),
            'top1_agreement': sum(e['top1_agrees'] for e in exhaustive),
            'bounded_top1_in_exhaustive_top3': sum(e['bounded_top1_in_exhaustive_top3'] for e in exhaustive),
            'same_nominal_status': sum(e['same_nominal_status'] for e in exhaustive),
            'max_objective_gap': max((e['objective_gap'] for e in exhaustive), default=None)},
        'baseline_workbook_calculator': {
            'cases_simulated': len(baseline), 'circuit_nominal_passes': sum(b['circuit_nominal_pass'] for b in baseline),
            'crest_deviation_pct': stats([b['deviation_pct']['crest_kv'] for b in baseline]),
            'scope': 'Unconstrained workbook-calculator settings (stock not checked) simulated with the circuit.'},
        'surrogate_expanded_search': None if not expanded else {
            'cases': len(expanded), 'equal_or_better': sum(e['equal_or_better'] for e in expanded),
            'strictly_better': sum(e['strictly_better'] for e in expanded),
            'median_runtime_s': statistics.median(e['runtime_s'] for e in expanded),
            'current_median_runtime_s': statistics.median(current_runtimes),
            'promotion_rule': 'equal-or-better top-1 in >=95% of cases AND (strictly better in >=10% OR median runtime <= 80%)'},
        'records': records,
        'measured_performance': 'None. No measured generator waveform with known settings is available; nothing here is laboratory accuracy.',
        'elapsed_seconds': round(time.time() - started, 1), 'platform': platform.platform(),
    }
    if expanded:
        s = result['surrogate_expanded_search']
        s['promoted'] = (s['equal_or_better'] >= .95*s['cases']
                         and (s['strictly_better'] >= .10*s['cases'] or s['median_runtime_s'] <= .8*s['current_median_runtime_s']))
    out = ROOT/args.output
    out.mkdir(parents=True, exist_ok=True)
    (out/'results.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['outcomes', 'recommendation_quality', 'baseline_workbook_calculator',
                                              'surrogate_expanded_search']}, indent=1, default=float))
    for key, value in result['simulation_agreement_by_profile'].items():
        print(key, json.dumps({k: (v if not isinstance(v, dict) else {a: round(b, 6) if isinstance(b, float) else b for a, b in v.items()})
                               for k, v in value.items()}, default=float))


if __name__ == '__main__':
    main()
