import json
from pathlib import Path

from backend.app.ml.benchmark_scorecard import compare, scorecard

ROOT = Path(__file__).resolve().parents[1]


def test_preserved_test_and_development_counts_are_separate():
    hidden = json.loads((ROOT / 'artifacts/models/hidden_test_evaluation.json').read_text())
    v2 = json.loads((ROOT / 'artifacts/experiments/v2/summary.json').read_text())
    result = scorecard(hidden, v2)
    physics, knn = result['frozen_v1']['comparisons']
    assert physics['lower_error_targets'] == 6
    assert knn['lower_error_targets'] == 5
    assert knn['higher_error_targets'] == 1
    crest = knn['targets'][-1]
    assert crest['impulse_type'] == 'Switching' and crest['target'] == 'Crest voltage'
    assert crest['rmse_reduction_pct'] < 0
    assert result['development_v2']['comparisons'][1]['lower_error_targets'] == 6
    assert result['development_v2']['active_default_changed'] is False


def test_absent_or_nonfinite_metrics_never_count_as_a_pass():
    tables = {'Lightning': {'model': {'rmse': [1., float('nan')]}, 'baseline': {'rmse': [2., 3., 4.]}}}
    result = compare(tables, 'model', 'baseline')
    assert result['recorded_targets'] == result['lower_error_targets'] == 1
    assert sum(row['verdict'] == 'NOT RECORDED' for row in result['targets']) == 5
    assert result['targets'][1]['model_rmse'] is None


def test_equal_or_zero_errors_are_not_fabricated_improvements():
    tables = {'Lightning': {'model': {'rmse': [0., 1., 2.]}, 'baseline': {'rmse': [0., 1., 0.]}}}
    result = compare(tables, 'model', 'baseline')
    assert result['tied_targets'] == 2
    assert result['higher_error_targets'] == 1
    assert result['lower_error_targets'] == 0
    assert all(row['rmse_reduction_pct'] is None for row in (result['targets'][0], result['targets'][2]))


def test_missing_development_results_remain_absent():
    result = scorecard({})
    assert result['development_v2'] is None
    assert all(c['recorded_targets'] == 0 for c in result['frozen_v1']['comparisons'])


def test_models_endpoint_returns_separate_evidence_and_focused_study():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    response = client.get('/api/models')
    assert response.status_code == 200
    data = response.json()
    assert data['benchmark_scorecard']['frozen_v1']['comparisons'][1]['lower_error_targets'] == 5
    assert data['benchmark_scorecard']['development_v2']['comparisons'][1]['lower_error_targets'] == 6
    # V6/V7 crest studies live on codex/switching-crest-review, not this branch.
    assert 'experiment_v6' not in data and 'experiment_v7' not in data
