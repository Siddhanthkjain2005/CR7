"""One fixed independent-solver benchmark; no ML fit or old test predictions."""
import csv
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from threadpoolctl import threadpool_limits

from scripts.independent_impulse_reference import solve, METRICS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/independent_simulation/v1'
DATA = ROOT / 'data/generated/independent_circuit_v1'
VERSION = 'independent-circuit-verification-v1'
SEED = 20261007


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parameter_cases():
    rng = np.random.default_rng(SEED)
    rows = []
    for impulse in ('Lightning', 'Switching'):
        for index in range(120):
            row = {'id': f'{impulse.lower()}-{index:03d}', 'impulse_type': impulse,
                   'stages': int(rng.integers(2, 13)), 'stage_c_uf': .125,
                   'charge_kv_stage': float(rng.uniform(50, 200)),
                   'front_r_stage': float(rng.choice([30, 465, 3700])),
                   'tail_r_stage': 520. if impulse == 'Lightning' else 22000.,
                   'total_c_pf': float(rng.uniform(600, 4000)),
                   'l_uh': 0. if index % 10 == 0 else float(rng.uniform(.1, 30)),
                   'efficiency': .83, 'source_type': 'independent_generated_simulation'}
            if index < 12:
                row.update(stages=2 if index < 6 else 12,
                           charge_kv_stage=50. if index % 2 == 0 else 200.,
                           front_r_stage=float([30, 465, 3700][index % 3]),
                           total_c_pf=600. if index % 2 == 0 else 4000.,
                           l_uh=0. if index % 2 == 0 else 30.)
            rows.append(row)
        group = rows[-120:]
        ordered = sorted(group, key=lambda row: hashlib.sha256(
            ('independent-numerical-v1:' + row['id']).encode()).hexdigest())
        for index, row in enumerate(ordered):
            row['split'] = 'development' if index < 80 else 'evaluation'
    return rows


def acceptance(solutions):
    primary = solutions[0]
    differences = {metric: max(abs(other[metric]/primary[metric]-1)
                               for other in solutions[1:]) for metric in METRICS}
    accepted = all(np.isfinite(s[metric]) and s[metric] > 0
                   for s in solutions for metric in METRICS)
    accepted = accepted and max(differences.values()) <= 1e-5
    accepted = accepted and all(s['maximum_energy_ratio'] <= 1+1e-8
                               and s['maximum_energy_increase_ratio'] <= 1e-8 for s in solutions)
    return bool(accepted), differences


def summary(records):
    channels = []
    for impulse in ('Lightning', 'Switching'):
        requested = [r for r in records if r['case']['impulse_type'] == impulse
                     and r['case']['split'] == 'evaluation']
        eligible = [r for r in requested if r.get('reference_accepted') and r.get('production')]
        for metric in METRICS:
            truth = np.array([r['reference'][metric] for r in eligible])
            prediction = np.array([r['production'][metric] for r in eligible])
            errors = prediction-truth
            relative = abs(errors/truth)*100
            p95 = float(np.quantile(relative, .95)) if len(relative) else None
            worst = float(np.max(relative)) if len(relative) else None
            passed = (len(eligible) >= .95*len(requested) and len(eligible) > 0
                      and p95 <= .05 and worst <= .2)
            channels.append({'impulse_type': impulse, 'metric': metric,
                             'unit': 'kV' if metric == 'crest_kv' else 'µs',
                             'requested_evaluation_cases': len(requested),
                             'accepted_prediction_cases': len(eligible),
                             'rmse': float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
                             'p95_relative_error_pct': p95, 'worst_relative_error_pct': worst,
                             'numerical_agreement_pass': bool(passed)})
    return {'version': VERSION, 'evidence_type': 'GENERATED NUMERICAL VERIFICATION',
            'channels': channels, 'passing_channels': sum(c['numerical_agreement_pass'] for c in channels),
            'expected_channels': 6, 'requested_cases': len(records),
            'reference_accepted_cases': sum(r.get('reference_accepted', False) for r in records),
            'scope': 'Independent integrator versus production modal solver of the same assumed CPRI lumped topology. Evaluation cases were fixed before labels. Numerical agreement is neither physical validation nor V1/V2-versus-kNN accuracy. It cannot change the preserved workbook final-test 5/6 result.',
            'model_weights_changed': False, 'old_test_predictions_evaluated': False,
            'laboratory_accuracy_established': False, 'cloud_spend_usd': 0}


def write_once(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def run():
    if (OUTPUT/'protocol.json').exists():
        print('Registered numerical study exists; no overwrite or retuning.', flush=True)
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    cases = parameter_cases()
    preserved = json.loads((ROOT/'artifacts/experiments/v7/protocol.json').read_text())['preserved_sha256']
    preserved = dict(preserved)
    for path in (ROOT/'artifacts/experiments/v7').rglob('*'):
        if path.is_file(): preserved[str(path.relative_to(ROOT))] = sha(path)
    preserved['backend/app/ml/experiment_v7.py'] = sha(ROOT/'backend/app/ml/experiment_v7.py')
    assert all(sha(ROOT/path) == value for path, value in preserved.items())
    production_path = ROOT/'backend/app/physics/circuit.py'
    protocol = {'version': VERSION, 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
                'seed': SEED, 'parameter_only_cases': cases,
                'generator_sha256': sha(ROOT/'scripts/independent_impulse_reference.py'),
                'runner_sha256': sha(Path(__file__)), 'production_sha256_before_labels': sha(production_path),
                'preserved_sha256': preserved,
                'solver_settings': [['Radau', 1e-9, 1e-12], ['BDF', 1e-10, 1e-13], ['Radau', 1e-11, 1e-14]],
                'reference_gate': 'All three metrics positive/finite; solver/refinement relative differences <=1e-5; normalized passive energy overshoot/increase <=1e-8.',
                'numerical_agreement_gate': 'Each evaluation channel: >=95% of 40 requested cases has an accepted reference and production prediction; p95 relative error <=0.05%, worst <=0.2%. All failures remain in denominators.',
                'assumptions': 'Supplied 12-stage/0.125uF profile; lumped erected generator C shunted by Rt, Rf/L series into load C. Resistor values are source values but actual inventory/topology/pulse ratings remain unknown. Total load600..4000pF includes545pF once; L0..30uH and voltage efficiency0.83 are assumed, not measured.',
                'splits': '80development/40evaluation per type by parameter-ID hash, before labels. No model is fit. Prototype feasibility cases were not used to choose a favorable seed or thresholds.',
                'scope': 'Generated numerical verification, not new measured outcomes. Different numerical implementation, same assumed topology. No workbook observed outcomes or residual models enter reference generation.',
                'stopping_rule': 'One240-case run, no resampling or dropped failures, no serving/model/threshold changes after results.',
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__}}
    write_once(OUTPUT/'protocol.json', protocol)
    write_once(DATA/'parameter_manifest.json', cases)
    started = time.perf_counter()
    records = []
    try:
        # Finish and freeze reference labels before importing the production solver.
        for i, case in enumerate(cases):
            record = {'case': case}
            try:
                solutions = [solve(case, method, rtol, atol, waveform=(index == 2))
                             for index, (method, rtol, atol) in enumerate(protocol['solver_settings'])]
                accepted, differences = acceptance(solutions)
                record.update(reference_accepted=accepted, solver_relative_differences=differences,
                              solver_metrics=[{k: v for k, v in s.items() if k != 'waveform'} for s in solutions],
                              reference={k: v for k, v in solutions[2].items() if k != 'waveform'})
                with (DATA/(case['id']+'.csv')).open('x', newline='') as stream:
                    writer = csv.writer(stream); writer.writerow(['time_us', 'voltage_kv'])
                    writer.writerows(zip(solutions[2]['waveform']['time_us'], solutions[2]['waveform']['voltage_kv']))
            except Exception as error:
                record.update(reference_accepted=False, reference_failure=f'{type(error).__name__}: {error}')
            records.append(record)
            if (i+1) % 20 == 0: print(f'Independent references {i+1}/{len(cases)} complete', flush=True)
        write_once(DATA/'reference_labels.json', records)
        reference_sha = sha(DATA/'reference_labels.json')
        assert sha(production_path) == protocol['production_sha256_before_labels']
        from backend.app.physics.circuit import simulate
        for record in records:
            if not record.get('reference_accepted'): continue
            case = record['case']
            try:
                result = simulate(**{k: case[k] for k in ('stages', 'charge_kv_stage', 'front_r_stage',
                                  'tail_r_stage', 'stage_c_uf', 'total_c_pf', 'l_uh', 'efficiency', 'impulse_type')},
                                  include_waveform=False)
                record['production'] = {metric: result[metric] for metric in METRICS}
            except Exception as error:
                record['production_failure'] = f'{type(error).__name__}: {error}'
        assert all(sha(ROOT/path) == value for path, value in preserved.items())
        result = summary(records)
        result.update(protocol_sha256=sha(OUTPUT/'protocol.json'), reference_labels_sha256=reference_sha,
                      elapsed_seconds=time.perf_counter()-started,
                      preserved_artifacts_verified=True)
        write_once(OUTPUT/'predictions.json', records)
        write_once(OUTPUT/'summary.json', result)
        print(json.dumps(result, indent=2), flush=True)
    except Exception as error:
        write_once(OUTPUT/'failure.json', {'error': f'{type(error).__name__}: {error}'})
        raise


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        run()
