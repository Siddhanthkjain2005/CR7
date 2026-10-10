"""Protect the envelope objective, fold separation, and immutable evidence."""
import csv
import json

import numpy as np
import pandas as pd
import pytest

from backend.app.ml import experiment_v2 as v2, experiment_v5 as v5
from backend.app.ml.reference_knn import ROOT, FEATURES, OBSERVED, PHYSICS, RESIDUAL


def synthetic_frame(count=24):
    rng = np.random.default_rng(12)
    columns = set(FEATURES + PHYSICS + OBSERVED + RESIDUAL + ['Stages', 'Charge_kV_Stage'])
    frame = pd.DataFrame({name: rng.uniform(1., 3., count) for name in sorted(columns)})
    frame['Test_kV'] = np.linspace(1350., 1500., count)
    frame['ID'] = np.arange(count)
    frame['Split'] = 'Train'
    frame['Impulse_Type'] = 'Lightning'
    frame[RESIDUAL] = frame[PHYSICS].to_numpy() * .0125
    frame[OBSERVED] = frame[PHYSICS].to_numpy() + frame[RESIDUAL].to_numpy()
    return frame


def test_minimax_recovers_center_of_known_bounded_linear_signal():
    x = np.repeat(np.linspace(-2., 2., 15), 2)[:, None]
    noise = np.tile([-.2, .2], 15)
    y = 1.7 + .4 * x.ravel() + noise
    model = v5.EnvelopeRegressor('Minimax envelope', 1).fit(x, y)
    np.testing.assert_allclose(model.predict(x), 1.7 + .4 * x.ravel(), atol=1e-10)
    max_error = np.max(np.abs(model.predict(x) - y))
    assert model.radius_ * model.target_scaler_.scale_[0] == pytest.approx(max_error)


@pytest.mark.parametrize('method', v5.METHODS)
@pytest.mark.parametrize('relative', [False, True])
def test_prediction_units_and_frozen_transforms(method, relative):
    frame = synthetic_frame()
    for target in range(3):
        if not relative:
            frame[RESIDUAL[target]] = .0125
        spec = {'name': method, 'relative': relative, 'degree': 2}
        model = v5.fit(frame, target, spec)
        before = model.input_scaler_.mean_.copy()
        query = frame.copy()
        query[PHYSICS[target]] *= 2
        query[RESIDUAL + OBSERVED] = 1e12
        expected = .0125 * query[PHYSICS[target]] if relative else np.full(len(query), .0125)
        np.testing.assert_allclose(v5.predict(model, query, target, spec), expected, atol=1e-10)
        query['Load_C_pF'] *= 100
        v5.predict(model, query, target, spec)
        np.testing.assert_array_equal(model.input_scaler_.mean_, before)


def test_features_exclude_outcomes_and_metadata():
    frame = synthetic_frame()
    poisoned = frame.copy()
    poisoned[RESIDUAL + OBSERVED + PHYSICS] = -1e12
    poisoned['ID'] = -1
    poisoned['Split'] = 'Hidden Test'
    for target in range(3):
        np.testing.assert_array_equal(v5.x_features(frame, target), v5.x_features(poisoned, target))


def test_loader_excludes_calibration_and_test_before_numeric_parsing(tmp_path):
    frame = synthetic_frame(4)
    frame.loc[1, 'Impulse_Type'] = 'Switching'
    frame.loc[3, 'Split'] = 'Hidden Test'
    rows = frame.to_dict(orient='records')
    for row in rows[2:]:
        for column in OBSERVED + RESIDUAL:
            row[column] = 'FORBIDDEN OUTCOME: must never parse'
    path = tmp_path / 'source.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=frame.columns)
        writer.writeheader()
        writer.writerows(rows)
    split = {'fit_ids': {'Lightning': [0], 'Switching': [1]},
             'calibration_ids': {'Lightning': [2], 'Switching': []}}
    selected = v5.load_fit_frames(split, path)
    assert selected['Lightning'].ID.tolist() == [0]
    assert selected['Switching'].ID.tolist() == [1]


def test_inner_fits_exclude_their_held_rows(monkeypatch):
    frame = synthetic_frame()
    original_fit, original_predict = v5.fit, v5.predict
    original_base_fit, original_base_predict = v2.fit_spec, v2.predict_spec
    calls = []

    def fitting(fn):
        def wrapped(rows, target, spec):
            model = fn(rows, target, spec)
            model.audit_training_ids_ = set(rows.ID)
            calls.append(model.audit_training_ids_)
            return model
        return wrapped

    def predicting(fn):
        def wrapped(model, rows, target, spec):
            assert not model.audit_training_ids_ & set(rows.ID)
            return fn(model, rows, target, spec)
        return wrapped

    monkeypatch.setattr(v5, 'fit', fitting(original_fit))
    monkeypatch.setattr(v5, 'predict', predicting(original_predict))
    monkeypatch.setattr(v2, 'fit_spec', fitting(original_base_fit))
    monkeypatch.setattr(v2, 'predict_spec', predicting(original_base_predict))
    baseline = {'name': 'Ridge', 'basis': 'minimal mechanism', 'relative': True, 'params': {'alpha': .01}}
    _, _, log = v5.select(frame, 0, baseline, 'Lightning')
    assert len(calls) == 3 * (1 + len(v5.spec_grid()))
    assert all(len(ids) == 16 for ids in calls)
    assert len(log['all_candidate_scores']) == 24
    assert set(sum([fold['held_ids'] for fold in log['inner_folds']], [])) == set(frame.ID)


def test_fallback_threshold_and_matched_control_scope():
    scores = [
        {'spec': {'name': 'Ridge control', 'blend': 1.}, 'normalized_mse': .99},
        {'spec': {'name': 'Minimax envelope', 'blend': .5}, 'normalized_mse': .7},
    ]
    assert v5.choose(scores, 1., ['Ridge control'])[0]['blend'] == 0
    assert v5.choose(scores, 1., v5.METHODS)[0]['name'] == 'Minimax envelope'
    assert v5.gate(np.ones(6), np.full(6, .94), [6.] * 6)[2]
    assert not v5.gate(np.ones(6), np.full(6, .96), [4.] * 6)[2]
    assert not v5.gate(np.ones(6), np.full(6, .9), [10.] * 5 + [-2.01])[2]


def test_completed_experiment_refuses_to_read_labels_or_retune(tmp_path, monkeypatch):
    (tmp_path / 'summary.json').write_text('{}')
    monkeypatch.setattr(v5, 'OUTPUT', tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError('Frozen experiment may not load data or retrain')

    monkeypatch.setattr(v5, 'load_fit_frames', forbidden)
    monkeypatch.setattr(v5, 'select', forbidden)
    v5.run()


def test_stored_record_recomputes_and_excludes_all_forbidden_ids():
    path = ROOT / 'artifacts/experiments/v5'
    protocol = json.loads((path / 'protocol.json').read_text())
    summary = json.loads((path / 'summary.json').read_text())
    records = json.loads((path / 'oof_predictions.json').read_text())
    fit_ids = set(sum(protocol['fit_ids'].values(), []))
    excluded = set(sum(protocol['excluded_calibration_ids'].values(), []))
    assert len(records) == len({row['id'] for row in records}) == 1120
    assert {row['id'] for row in records} == fit_ids
    assert not fit_ids & excluded
    assert summary['protocol_sha256'] == v2.sha(path / 'protocol.json')
    assert protocol['runner_sha256'] == v2.sha(ROOT / 'backend/app/ml/experiment_v5.py')
    assert protocol['helper_sha256'] == v2.sha(ROOT / 'backend/app/ml/experiment_v2.py')
    # Historical protocol included untracked macOS Finder metadata. Preserve every
    # scientific artifact hash and normalize path separators without editing the protocol.
    expected = {k: v for k, v in protocol['preserved_sha256'].items() if not k.endswith('/.DS_Store')}
    actual = {k.replace(chr(92), '/'): v for k, v in v5.preserved_artifacts().items()
              if not k.replace(chr(92), '/').endswith('/.DS_Store')}
    # Independently named later studies can add files. Every artifact registered
    # by V5 must still exist with exactly its recorded bytes.
    assert expected.items() <= actual.items()
    frames = v5.load_fit_frames({'fit_ids': protocol['fit_ids'],
                                 'calibration_ids': protocol['excluded_calibration_ids']})
    baseline, candidate, gains = [], [], []
    for typ in v2.TYPES:
        by_id = {row['id']: row for row in records if row['type'] == typ}
        for fold_index, choices in enumerate(summary['fold_choices'][typ]):
            outer_held = {row['id'] for row in by_id.values() if row['fold'] == fold_index}
            outer_train = set(protocol['fit_ids'][typ]) - outer_held
            for choice in choices:
                for inner in choice['inner_folds']:
                    inner_train, inner_held = set(inner['train_ids']), set(inner['held_ids'])
                    assert inner_train.isdisjoint(inner_held)
                    assert inner_train | inner_held == outer_train
                    assert not (inner_train | inner_held) & outer_held
        frame = frames[typ]
        for name, key in [('Historical V2 refit', 'v2_refit_prediction'),
                          ('V5 envelope search', 'v5_prediction'),
                          ('Matched Ridge control search', 'ridge_control_prediction')]:
            predictions = np.array([by_id[int(id_)][key] for id_ in frame.ID])
            recomputed = v2.metric_report(frame, predictions, typ)
            assert recomputed.keys() == summary['nested_cv'][typ]['metrics'][name].keys()
            for metric, values in recomputed.items():
                np.testing.assert_allclose(values, summary['nested_cv'][typ]['metrics'][name][metric], rtol=1e-12, atol=1e-14)
        for row in by_id.values():
            held = {r['id'] for r in by_id.values() if r['fold'] == row['fold']}
            assert len(row['train_ids']) == len(set(row['train_ids'])) == 448
            assert set(row['train_ids']) == set(protocol['fit_ids'][typ]) - held
            assert not set(row['train_ids']) & excluded
        table = summary['nested_cv'][typ]['metrics']
        baseline.extend(table['Historical V2 refit']['normalized_rmse_tolerance'])
        candidate.extend(table['V5 envelope search']['normalized_rmse_tolerance'])
        gains.extend(100 * (1 - np.array(table['V5 envelope search']['rmse']) /
                            table['Historical V2 refit']['rmse']))
    macro, worst, eligible = v5.gate(baseline, candidate, gains)
    assert summary['macro_improvement_pct'] == pytest.approx(macro)
    assert summary['worst_target_improvement_pct'] == pytest.approx(worst)
    assert summary['promotion_eligible'] == eligible
    assert not any(summary[key] for key in ['hidden_test_evaluated', 'validation_evaluated',
                                            'calibration_evaluated', 'final_models_created'])


def test_v5_evidence_is_readable_and_not_a_serving_option():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    models = client.get('/api/models').json()
    assert models['version'] == 'residual-competition-v1'
    study = models['experiment_v5']
    assert study['promotion_eligible'] is False
    assert study['macro_improvement_pct'] == pytest.approx(1.0920818719435732)
    response = client.get('/api/models/' + study['version'] + '/metrics')
    assert response.status_code == 200 and response.json()['final_models_created'] is False
    assert client.get('/api/documents/accuracy_v5_results').status_code == 200
    assert client.get('/api/documents/judging_criteria').status_code == 200
    assert client.post('/api/optimize', json={'model_mode': study['version']}).status_code == 422
