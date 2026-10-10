"""Train and evaluate the circuit surrogate under a protocol declared before testing.

  python -m scripts.train_circuit_surrogate --data data/generated/circuit_dataset_v1_pilot --learning-curve
  python -m scripts.train_circuit_surrogate --data data/generated/circuit_dataset_v1 --final

Model selection uses only the validation split. The frozen test split is scored
once, after protocol.json (with the promotion gate) has been written.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor

from backend.app.ml.surrogate import features, targets, untransform, load
from backend.app.physics.compliance import RULES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/models/circuit_surrogate_v1'
KEYS = ('front_us', 'tail_us', 'crest_kv')
GATE = {
    'scope': 'Frozen test rows that the circuit resolved and that lie inside the surrogate feature domain.',
    'accuracy': {'p95_relative_error_pct_max': {'front_us': 1.0, 'tail_us': 1.0, 'crest_kv': .5},
                 'worst_relative_error_pct_max': 5.0, 'by': 'impulse type and output'},
    'classification': {'timing_decision_disagreement_pct_max': 2.0, 'false_pass_pct_of_circuit_fails_max': 2.0},
    'use_if_passed': 'Screening of constructible settings only. Every shortlisted setting is re-simulated with the '
                     'circuit; surrogate metrics are never shown as predictions.',
    'search_promotion': 'Separately decided by the evaluation pack: equal-or-better top-1 versus the current bounded '
                        'search in >=95% of cases AND (strictly better in >=10% of cases OR median runtime <= 80%).',
}
ARCHITECTURES = [(32, 32), (64, 64), (96, 96)]
# Validated support: the practical sampling regimes around constructible settings.
# 'wide' and 'extreme' rows are kept in the dataset and reported as out-of-support.
PRACTICAL = ('tight_target', 'near_target', 'stock_network')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_data(folder):
    folder = ROOT/folder
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        if digest(folder/name) != expected:
            raise SystemExit(f'{name} does not match its manifest checksum.')
    frame = pd.read_csv(folder/'dataset.csv.gz')
    test_groups = sorted(frame.loc[frame.split == 'test', 'group_id'].unique())
    if hashlib.sha256('\n'.join(test_groups).encode()).hexdigest() != manifest['split']['test_groups_sha256']:
        raise SystemExit('Frozen test split changed.')
    return frame[frame.status == 'ok'].reset_index(drop=True), manifest


def matrices(frame):
    x, scales = features(frame.stages, frame.front_r_stage, frame.tail_r_stage, frame.stage_c_uf, frame.total_c_pf,
                         frame.l_uh, frame.impulse_type)
    y = targets(frame.front_us, frame.tail_us, frame.crest_kv, frame.stages, frame.charge_kv_stage, frame.efficiency, scales)
    return x, y, scales


def fit(x, y, hidden, seed=7):
    x_mean, x_std = x.mean(0), x.std(0) + 1e-12
    y_mean, y_std = y.mean(0), y.std(0) + 1e-12
    # Full-batch L-BFGS: adam with early stopping plateaued at 3-8% p95 error in the
    # pilot/learning-curve runs (recorded in learning_curve.json).
    model = MLPRegressor(hidden_layer_sizes=hidden, activation='tanh', solver='lbfgs', max_iter=4000,
                         max_fun=8000, tol=1e-10, random_state=seed)
    model.fit((x - x_mean)/x_std, (y - y_mean)/y_std)
    arrays = {'x_mean': x_mean, 'x_std': x_std, 'y_mean': y_mean, 'y_std': y_std}
    for i, (w, b) in enumerate(zip(model.coefs_, model.intercepts_)):
        arrays[f'w{i}'] = w; arrays[f'b{i}'] = b
    return arrays, len(model.coefs_), model.n_iter_


def numpy_predict(arrays, layers, x):
    h = (x - arrays['x_mean'])/arrays['x_std']
    for i in range(layers):
        h = h @ arrays[f'w{i}'] + arrays[f'b{i}']
        if i < layers - 1:
            h = np.tanh(h)
    return h*arrays['y_std'] + arrays['y_mean']


def errors(frame, predicted):
    truth = frame[list(KEYS)].to_numpy(float)
    rel = 100*np.abs(predicted/truth - 1)
    result = {}
    for typ in ('Lightning', 'Switching'):
        mask = (frame.impulse_type == typ).to_numpy()
        if not mask.any():
            continue
        result[typ] = {key: {'n': int(mask.sum()), 'median_pct': float(np.median(rel[mask, j])),
                             'p95_pct': float(np.percentile(rel[mask, j], 95)),
                             'worst_pct': float(rel[mask, j].max())} for j, key in enumerate(KEYS)}
    return result


def decisions(frame, predicted):
    agree, false_pass, fails = [], 0, 0
    for (_, row), pred in zip(frame.iterrows(), predicted):
        rule = RULES[row.impulse_type]
        ok = lambda f, t: rule['front_min_us'] <= f <= rule['front_max_us'] and rule['tail_min_us'] <= t <= rule['tail_max_us']
        truth, guess = ok(row.front_us, row.tail_us), ok(pred[0], pred[1])
        agree.append(truth == guess)
        if not truth:
            fails += 1; false_pass += guess
    return {'rows': len(agree), 'timing_decision_disagreement_pct': 100*(1 - float(np.mean(agree))),
            'circuit_fail_rows': fails, 'false_pass_rows': int(false_pass),
            'false_pass_pct_of_circuit_fails': 100*false_pass/max(fails, 1)}


def domain(x):
    lower, upper = [], []
    return {'lower': np.percentile(x[:, :3], 0.5, axis=0).tolist(), 'upper': np.percentile(x[:, :3], 99.5, axis=0).tolist(),
            'definition': 'Central 99% box of the training features (log Cg/Cl, log Rt/Rf, log L/(Rf^2 Cs)).'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--learning-curve', action='store_true')
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    frame, manifest = load_data(args.data)
    support = frame.sampling_regime.isin(PRACTICAL)
    outside_test = frame[(frame.split == 'test') & ~support].reset_index(drop=True)
    train, val, test = (frame[(frame.split == s) & support].reset_index(drop=True) for s in ('train', 'validation', 'test'))
    xt, yt, _ = matrices(train)
    xv, _, sv = matrices(val)
    if args.learning_curve:
        curve = []
        for size in [n for n in (250, 500, 1000, 2000, 4000, 8000, 16000, 32000) if n <= len(train)] + [len(train)]:
            idx = np.random.default_rng(3).permutation(len(train))[:size]
            arrays, layers, iterations = fit(xt[idx], yt[idx], (64, 64))
            pred = untransform(numpy_predict(arrays, layers, xv), val.stages, val.charge_kv_stage, val.efficiency, sv)
            e = errors(val, pred)
            curve.append({'train_rows': int(size), 'iterations': int(iterations),
                          'validation_p95_pct': {t: {k: round(v['p95_pct'], 4) for k, v in e[t].items()} for t in e}})
            print(json.dumps(curve[-1]))
        Path(ROOT/args.data/'learning_curve.json').write_text(json.dumps(curve, indent=2) + '\n', encoding='utf-8')
        return
    if not args.final:
        raise SystemExit('Choose --learning-curve or --final.')
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {'version': 'circuit-surrogate-v1-protocol', 'declared_at': datetime.now(timezone.utc).isoformat(),
                'dataset': args.data, 'dataset_manifest_sha256': digest(ROOT/args.data/'manifest.json'),
                'test_groups_sha256': manifest['split']['test_groups_sha256'], 'architectures': ARCHITECTURES,
                'selection': 'Lowest mean validation p95 relative error over the six type/output channels.',
                'training_support': list(PRACTICAL), 'solver': 'lbfgs',
                'gate': GATE, 'trainer_sha256': digest(__file__)}
    (OUT/'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n', encoding='utf-8')
    started = time.time()
    trials = []
    for hidden in ARCHITECTURES:
        arrays, layers, iterations = fit(xt, yt, hidden)
        pred = untransform(numpy_predict(arrays, layers, xv), val.stages, val.charge_kv_stage, val.efficiency, sv)
        e = errors(val, pred)
        score = float(np.mean([e[t][k]['p95_pct'] for t in e for k in KEYS]))
        trials.append({'hidden': hidden, 'validation_mean_p95_pct': score, 'iterations': int(iterations), 'validation': e})
        print(hidden, round(score, 4))
        if score <= min(t['validation_mean_p95_pct'] for t in trials):
            best = (arrays, layers, hidden)
    arrays, layers, hidden = best
    meta = {'version': 'circuit-surrogate-v1', 'layers': layers, 'hidden': list(hidden), 'activation': 'tanh',
            'inputs': ['log(Cg/Cl)', 'log(Rt_total/Rf_total)', 'log(L/(Rf_total^2 Cseries)) floored at 1e-12', 'switching flag'],
            'outputs': ['log(front_us/(Rf_total Cl))', 'log(tail_us/(Rt_total (Cg+Cl)))', 'crest/(n charge efficiency)'],
            'trained_on': args.data, 'train_rows': len(train), 'feature_domain': domain(xt),
            'reproduces': manifest['circuit_model'], 'surrogate_of_solver': True}
    np.savez(OUT/'weights.npz', **arrays)
    (OUT/'model.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    load.cache_clear()
    model = load(str(OUT))
    xs, ss = features(test.stages, test.front_r_stage, test.tail_r_stage, test.stage_c_uf, test.total_c_pf, test.l_uh, test.impulse_type)
    inside = model.inside_domain(xs)
    predicted, _ = model.predict(test.stages, test.charge_kv_stage, test.front_r_stage, test.tail_r_stage, test.stage_c_uf,
                                 test.total_c_pf, test.l_uh, test.efficiency, test.impulse_type)
    in_test = test[inside].reset_index(drop=True)
    e = errors(in_test, predicted[inside])
    d = decisions(in_test, predicted[inside])
    g = GATE['accuracy']
    accuracy_pass = all(e[t][k]['p95_pct'] <= g['p95_relative_error_pct_max'][k] and e[t][k]['worst_pct'] <= g['worst_relative_error_pct_max']
                        for t in e for k in KEYS)
    classification_pass = (d['timing_decision_disagreement_pct'] <= GATE['classification']['timing_decision_disagreement_pct_max']
                           and d['false_pass_pct_of_circuit_fails'] <= GATE['classification']['false_pass_pct_of_circuit_fails_max'])
    # Runtime: vectorized surrogate versus the production circuit solver.
    from backend.app.physics.circuit import simulate
    sample = in_test.head(400)
    t0 = time.perf_counter()
    for _, r in sample.iterrows():
        simulate(int(r.stages), r.charge_kv_stage, r.front_r_stage, r.tail_r_stage, r.stage_c_uf, r.total_c_pf, r.l_uh,
                 r.efficiency, r.impulse_type, False)
    circuit_ms = (time.perf_counter() - t0)/len(sample)*1e3
    big = pd.concat([in_test]*max(1, 20000//max(len(in_test), 1)), ignore_index=True)
    t0 = time.perf_counter()
    model.predict(big.stages, big.charge_kv_stage, big.front_r_stage, big.tail_r_stage, big.stage_c_uf, big.total_c_pf,
                  big.l_uh, big.efficiency, big.impulse_type)
    surrogate_ms = (time.perf_counter() - t0)/len(big)*1e3
    xo, _ = features(outside_test.stages, outside_test.front_r_stage, outside_test.tail_r_stage, outside_test.stage_c_uf,
                     outside_test.total_c_pf, outside_test.l_uh, outside_test.impulse_type)
    outside_ok = outside_test[outside_test.status == 'ok'] if 'status' in outside_test else outside_test
    gated_out = float(1 - model.inside_domain(xo).mean()) if len(xo) else None
    summary_outside = {'rows': len(outside_test), 'fraction_rejected_by_domain_gate': gated_out,
                       'note': 'Wide/extreme regimes are outside validated support; the domain gate is expected to reject most of them.'}
    summary = {'version': 'circuit-surrogate-v1', 'protocol_sha256': digest(OUT/'protocol.json'),
               'out_of_support_test': summary_outside,
               'selected_architecture': list(hidden), 'model_selection': trials,
               'test_rows_total': len(test), 'test_rows_inside_domain': int(inside.sum()),
               'test_errors_vs_circuit': e, 'test_timing_decisions': d,
               'accuracy_gate_pass': bool(accuracy_pass), 'classification_gate_pass': bool(classification_pass),
               'screening_use_allowed': bool(accuracy_pass and classification_pass),
               'runtime_ms_per_setting': {'circuit_solver': circuit_ms, 'surrogate_batched': surrogate_ms,
                                          'speedup': circuit_ms/max(surrogate_ms, 1e-9)},
               'what_this_shows': 'How closely a fast surrogate reproduces the circuit solver on unseen configuration groups. '
                                  'It is not evidence of physical or laboratory accuracy.',
               'elapsed_seconds': round(time.time() - started, 1)}
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['test_errors_vs_circuit', 'test_timing_decisions', 'accuracy_gate_pass',
                                               'classification_gate_pass', 'runtime_ms_per_setting']}, indent=1))


if __name__ == '__main__':
    main()
