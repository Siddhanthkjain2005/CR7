"""Versioned simulation dataset for the forward problem (hardware settings -> waveform).

Run:  python -m scripts.generate_circuit_dataset --rows 2000 --seed 11 --output data/generated/circuit_dataset_v1_pilot
      python -m scripts.generate_circuit_dataset --rows 40000 --seed 23 --output data/generated/circuit_dataset_v1

Labels are simulated outcomes of the production lumped Marx/RLC circuit (solver v2.1)
at the sampled settings; requested targets never become labels. Failures, ringing,
non-compliant and hardware-infeasible settings are retained and flagged.

This data is a SURROGATE target: a model trained on it reproduces the circuit
solver. It cannot improve physical accuracy and is not laboratory evidence.
"""
import argparse
import gzip
import hashlib
import io
import json
import math
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.optimization.networks import networks
from backend.app.physics.circuit import simulate, VERSION as CIRCUIT_VERSION
from backend.app.physics.compliance import RULES

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'circuit-dataset-v1'
PROFILES = {p['id']: p for p in json.loads((ROOT/'config/generator_profiles.json').read_text(encoding='utf-8'))}
# Waveform grid relative to each row's own half-value time (dimensionless).
GRID = np.r_[0., np.geomspace(1e-3, 3.0, 95)]
SPLIT = {'train': .70, 'validation': .15, 'test': .15}


def family_hardware(rng, family):
    if family == 'cpri':
        p = PROFILES['cpri_problem_brief_profile']
    elif family == 'workbook':
        p = PROFILES['workbook_reference_profile']
    else:
        # Custom hardware of the same series-Marx equivalent topology.
        max_stages = int(rng.integers(4, 21))
        stage_kv = float(rng.uniform(50, 300))
        stage_c = float(math.exp(rng.uniform(math.log(.03), math.log(3.))))
        energy = .5*stage_c*1e-6*(stage_kv*1e3)**2/1e3
        return {'family': 'custom', 'max_stages': max_stages, 'stage_kv': stage_kv, 'stage_c_uf': stage_c,
                'energy_stage_kj': energy, 'energy_total_kj': max_stages*energy, 'base_c_pf': 0.,
                'stock_front': None, 'stock_tail': None}
    return {'family': family, 'max_stages': p['max_stages'], 'stage_kv': p['stage_kv'], 'stage_c_uf': p['stage_c_uf'],
            'energy_stage_kj': p['energy_stage_kj'], 'energy_total_kj': p['energy_total_kj'],
            'base_c_pf': p['base_c_pf'] or 0., 'stock_front': p['front_values'],
            'stock_tail': {'Lightning': p['lightning_tail_values'], 'Switching': p['switching_tail_values']}}


def nearest_constructible(values, target, rng):
    """A constructible network value near the target from one unit of each value per stage
    (two units for small catalogues). Used only to sample realistic discrete settings."""
    count = 2 if len(values) <= 4 else 1
    items = networks(tuple(sorted((float(v), count) for v in values)), 6)
    ranked = sorted(items, key=lambda n: abs(math.log(n['equivalent_ohm']/target)))[:4]
    return float(ranked[int(rng.integers(0, len(ranked)))]['equivalent_ohm'])


def sample_config(rng, idx):
    family = rng.choice(['cpri', 'workbook', 'custom'], p=[.4, .3, .3])
    hw = family_hardware(rng, family)
    impulse = 'Lightning' if rng.random() < .5 else 'Switching'
    n = int(rng.integers(2, hw['max_stages'] + 1))
    load = float(math.exp(rng.uniform(math.log(100), math.log(5000))))
    divider = float(rng.uniform(0, 1500))
    stray = float(rng.uniform(0, 500))
    base = hw['base_c_pf'] if (hw['base_c_pf'] and rng.random() < .5) else 0.
    l_uh = 0. if rng.random() < .1 else float(rng.uniform(0, 50))
    efficiency = float(rng.uniform(.7, 1.))
    cl = (load + divider + stray + base)*1e-12
    cg = hw['stage_c_uf']*1e-6/n
    rule = RULES[impulse]
    regime = rng.choice(['tight_target', 'near_target', 'stock_network', 'wide', 'extreme'], p=[.25, .29, .2, .23, .03])
    if regime == 'extreme':
        # Stiff and degenerate corners retained so numerical failures stay in the data.
        rf_stage = float(math.exp(rng.uniform(math.log(1e-3), math.log(1e5))))
        rt_stage = float(math.exp(rng.uniform(math.log(1e-2), math.log(1e7))))
        l_uh = float(math.exp(rng.uniform(math.log(1e-6), math.log(1e4))))
        load = float(math.exp(rng.uniform(math.log(1), math.log(1e5))))
        cl = (load + divider + stray + base)*1e-12
    elif regime == 'wide':
        rf_stage = float(math.exp(rng.uniform(math.log(.5), math.log(20000))))
        rt_stage = float(math.exp(rng.uniform(math.log(2), math.log(100000))))
    else:
        # Rough continuous targets (same heuristics as the optimizer seeds), then
        # perturbed by up to 3x so labels include non-compliant waveforms.
        # Seed constants were adjusted once after inspecting the pilot's median
        # front/tail ratios; they only shape sampling density, never labels.
        if impulse == 'Lightning':
            rf_total = rule['front_target_us']*1e-6/(3.2*cl)*1.35
        else:
            rf_total = rule['front_target_us']*1e-6/(1.67*cl)*.25*1.6
        rt_total = rule['tail_target_us']*1e-6/(.693*(cg + cl))
        spread = math.log(1.35) if regime == 'tight_target' else math.log(3)
        rf_stage = rf_total/n*math.exp(rng.uniform(-spread, spread))
        rt_stage = rt_total/n*math.exp(rng.uniform(-spread, spread))
        if regime == 'stock_network' and hw['stock_front']:
            rf_stage = nearest_constructible(hw['stock_front'], rf_stage, rng)
            rt_stage = nearest_constructible(hw['stock_tail'][impulse], rt_stage, rng)
        elif regime == 'stock_network':
            regime = 'near_target'
    return {'config_index': idx, 'family': hw['family'], 'max_stages': hw['max_stages'], 'stage_kv_rating': hw['stage_kv'],
            'stage_c_uf': hw['stage_c_uf'], 'energy_stage_kj_rating': hw['energy_stage_kj'],
            'energy_total_kj_rating': hw['energy_total_kj'], 'impulse_type': impulse, 'sampling_regime': regime,
            'stages': n, 'front_r_stage': rf_stage, 'tail_r_stage': rt_stage, 'load_c_pf': load,
            'divider_c_pf': divider, 'stray_c_pf': stray, 'base_c_pf': base, 'total_c_pf': load+divider+stray+base,
            'l_uh': l_uh, 'efficiency': efficiency}


def group_id(config):
    keys = ['family', 'max_stages', 'stage_kv_rating', 'stage_c_uf', 'impulse_type', 'stages', 'front_r_stage',
            'tail_r_stage', 'total_c_pf', 'l_uh', 'efficiency']
    text = json.dumps({k: (round(config[k], 10) if isinstance(config[k], float) else config[k]) for k in keys}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def split_for(group):
    # Deterministic grouped split: every amplitude-scaled member of a configuration
    # family lands in the same split.
    u = int(group, 16)/16**16
    return 'train' if u < SPLIT['train'] else 'validation' if u < SPLIT['train'] + SPLIT['validation'] else 'test'


def label(config, charge):
    row = {**config, 'charge_kv_stage': charge}
    n, q = config['stages'], charge
    energy_stage = .5*config['stage_c_uf']*1e-6*(q*1e3)**2/1e3
    row.update(stored_energy_kj=n*energy_stage,
               hardware_feasible=bool(q <= config['stage_kv_rating']*(1+1e-12)
                                      and energy_stage <= config['energy_stage_kj_rating']*(1+1e-9)
                                      and n*energy_stage <= config['energy_total_kj_rating']*(1+1e-9)))
    try:
        result = simulate(n, q, config['front_r_stage'], config['tail_r_stage'], config['stage_c_uf'],
                          config['total_c_pf'], config['l_uh'], config['efficiency'], config['impulse_type'], True)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        row.update(status='unresolved', error=str(exc)[:160])
        return row, None
    rule = RULES[config['impulse_type']]
    row.update(status='ok', error='', front_us=result['front_us'], tail_us=result['tail_us'], crest_kv=result['crest_kv'],
               peak_time_us=result['peak_time_us'], t30_us=result['t30_us'], t90_us=result['t90_us'], t50_us=result['t50_us'],
               voltage_utilization=result['crest_kv']/(n*q*config['efficiency']),
               local_maxima=result['local_maxima_count'], ringing=bool(result['ringing_detected']),
               damping_ratio=result['diagnostics']['damping_ratio'],
               max_energy_ratio=result['diagnostics']['maximum_energy_ratio'],
               timing_compliant=bool(rule['front_min_us'] <= result['front_us'] <= rule['front_max_us']
                                     and rule['tail_min_us'] <= result['tail_us'] <= rule['tail_max_us']))
    wave = result['waveform']
    t = np.asarray(wave['time_us']); v = np.asarray(wave['voltage_kv'])
    sampled = np.interp(GRID*result['t50_us'], t, v)/result['crest_kv']
    return row, sampled.astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=2000, help='configurations to sample (each gives 1-2 charge levels)')
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--output', default='data/generated/circuit_dataset_v1_pilot')
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    started = time.time()
    rows, waves = [], []
    for idx in range(args.rows):
        config = sample_config(rng, idx)
        g = group_id(config)
        levels = 1 if rng.random() < .5 else 2
        for level in range(levels):
            fraction = float(rng.uniform(.15, 1.1))
            row, wave = label({**config, 'group_id': g, 'split': split_for(g), 'amplitude_member': level},
                              fraction*config['stage_kv_rating'])
            rows.append(row)
            waves.append(wave if wave is not None else np.full(len(GRID), np.nan, np.float32))
    frame = pd.DataFrame(rows)
    frame.insert(0, 'row_id', [f'r{i:06d}' for i in range(len(frame))])
    frame['provenance'] = 'independently_simulated:' + CIRCUIT_VERSION
    out = ROOT/args.output
    out.mkdir(parents=True, exist_ok=True)
    csv_bytes = frame.to_csv(index=False, float_format='%.10g', lineterminator='\n').encode()
    with gzip.GzipFile(out/'dataset.csv.gz', 'wb', mtime=0) as handle:
        handle.write(csv_bytes)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, grid=GRID, waveforms=np.vstack(waves).astype(np.float16), row_id=frame['row_id'].to_numpy().astype('U8'))
    (out/'waveforms.npz').write_bytes(buffer.getvalue())
    test_groups = sorted(frame.loc[frame.split == 'test', 'group_id'].unique())
    ok = frame[frame.status == 'ok']
    manifest = {
        'version': VERSION, 'seed': args.seed, 'configurations': args.rows, 'rows': len(frame),
        'generator': 'scripts/generate_circuit_dataset.py',
        'generator_sha256': hashlib.sha256((ROOT/'scripts/generate_circuit_dataset.py').read_bytes()).hexdigest(),
        'circuit_model': CIRCUIT_VERSION, 'challenge_rules_version': RULES['version'],
        'labels': 'Simulated outcomes of the production lumped circuit at the sampled settings; never requested targets.',
        'provenance_classes': {'supplied_workbook_data': 'data/processed/synthetic_dataset.csv (not included here)',
                               'independently_simulated': 'this dataset', 'measured': 'none',
                               'measurement_noise_stress_tests': 'separate; not included here'},
        'surrogate_warning': 'Models trained on these labels reproduce the circuit solver. This does not improve physical accuracy.',
        'split': {'method': 'Deterministic hash of the configuration group (all inputs except charge voltage); amplitude-scaled members share a split.',
                  'fractions': SPLIT, 'counts': frame.split.value_counts().to_dict(),
                  'test_group_count': len(test_groups),
                  'test_groups_sha256': hashlib.sha256('\n'.join(test_groups).encode()).hexdigest(),
                  'frozen_before_model_selection': True},
        'waveform_grid': 'Voltage/crest at time = grid × t50 (dimensionless grid stored in waveforms.npz).',
        'summary': {'status': frame.status.value_counts().to_dict(),
                    'family': frame.family.value_counts().to_dict(),
                    'impulse_type': frame.impulse_type.value_counts().to_dict(),
                    'sampling_regime': frame.sampling_regime.value_counts().to_dict(),
                    'hardware_feasible_fraction': float(frame.hardware_feasible.mean()),
                    'timing_compliant_fraction_of_resolved': float(ok.timing_compliant.mean()) if len(ok) else None,
                    'ringing_fraction_of_resolved': float(ok.ringing.mean()) if len(ok) else None},
        'files': {name: hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['dataset.csv.gz', 'waveforms.npz']},
        'elapsed_seconds': round(time.time() - started, 1), 'platform': platform.platform(),
        'numpy': np.__version__, 'pandas': pd.__version__,
    }
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ['rows', 'elapsed_seconds', 'summary']}, indent=1))


if __name__ == '__main__':
    main()
