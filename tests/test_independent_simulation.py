"""Independent numeric reference evidence and immutable benchmark boundaries."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.independent_impulse_reference import solve, METRICS
from scripts.benchmark_independent_impulses import parameter_cases, acceptance, summary

ROOT = Path(__file__).resolve().parents[1]


def test_parameter_manifest_is_fixed_balanced_and_does_not_use_outcomes():
    rows = parameter_cases()
    assert rows == parameter_cases() and len({r['id'] for r in rows}) == 240
    for impulse in ('Lightning', 'Switching'):
        group = [r for r in rows if r['impulse_type'] == impulse]
        assert len(group) == 120
        assert sum(r['split'] == 'evaluation' for r in group) == 40
        assert {r['front_r_stage'] for r in group} == {30, 465, 3700}
        assert any(r['l_uh'] == 0 for r in group)
        assert all(r['stage_c_uf'] == .125 and 2 <= r['stages'] <= 12 for r in group)
    assert all('prediction' not in r and 'observed' not in r for r in rows)


@pytest.mark.parametrize('impulse', ['Lightning', 'Switching'])
def test_independent_solver_scales_voltage_and_conserves_passive_energy(impulse):
    case = {**parameter_cases()[6], 'impulse_type': impulse}
    a = solve(case, waveform=True)
    b = solve({**case, 'charge_kv_stage': case['charge_kv_stage']*.5})
    assert b['front_us'] == pytest.approx(a['front_us'], rel=1e-10)
    assert b['tail_us'] == pytest.approx(a['tail_us'], rel=1e-10)
    assert b['crest_kv'] == pytest.approx(a['crest_kv']*.5, rel=1e-10)
    assert a['maximum_energy_ratio'] <= 1+1e-8
    assert a['maximum_energy_increase_ratio'] <= 1e-8
    assert np.isfinite(a['waveform']['voltage_kv']).all()
    assert np.all(np.diff(a['waveform']['time_us']) > 0)
    assert a['source_type'] == 'independent_generated_simulation'


def test_reference_acceptance_rejects_disagreement_and_energy_creation():
    a = {metric: 100. for metric in METRICS}
    a.update(maximum_energy_ratio=1., maximum_energy_increase_ratio=0.)
    assert acceptance([a, a, a])[0]
    assert not acceptance([a, {**a, 'crest_kv': 101.}, a])[0]
    assert not acceptance([a, {**a, 'maximum_energy_ratio': 1.01}, a])[0]


def test_unavailable_predictions_remain_in_evaluation_denominator():
    rows = [{'case': r, 'reference_accepted': False} for r in parameter_cases()]
    result = summary(rows)
    assert result['passing_channels'] == 0
    assert all(r['requested_evaluation_cases'] == 40 for r in result['channels'])
    assert all(r['accepted_prediction_cases'] == 0 and r['rmse'] is None for r in result['channels'])


def test_saved_independent_score_recomputes_and_preserves_prior_evidence():
    folder = ROOT/'artifacts/independent_simulation/v1'
    if not (folder/'summary.json').exists():
        pytest.skip('Registered reference run has not completed.')
    records = json.loads((folder/'predictions.json').read_text())
    saved = json.loads((folder/'summary.json').read_text())
    protocol = json.loads((folder/'protocol.json').read_text())
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    assert saved['protocol_sha256'] == digest(folder/'protocol.json')
    assert protocol['generator_sha256'] == digest(ROOT/'scripts/independent_impulse_reference.py')
    assert protocol['runner_sha256'] == digest(ROOT/'scripts/benchmark_independent_impulses.py')
    assert [r['case'] for r in records] == protocol['parameter_only_cases']
    assert summary(records)['channels'] == saved['channels']
    assert not saved['laboratory_accuracy_established']
    assert not saved['model_weights_changed'] and not saved['old_test_predictions_evaluated']
    # V6/V7 crest studies were recorded on codex/switching-crest-review and are not
    # carried on this branch; every preserved file that is present must match.
    later_studies = ('artifacts/experiments/v6/', 'artifacts/experiments/v7/',
                     'backend/app/ml/experiment_v6.py', 'backend/app/ml/experiment_v7.py')
    preserved = {path: expected for path, expected in protocol['preserved_sha256'].items()
                 if (ROOT/path).exists() or not path.startswith(later_studies)}
    assert all(digest(ROOT/path) == expected for path, expected in preserved.items())


def test_api_reads_saved_numerical_evidence_without_fitting_or_changing_scores():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    result = client.get('/api/verification/independent-circuit')
    assert result.status_code == 200
    saved = json.loads((ROOT/'artifacts/independent_simulation/v1/summary.json').read_text())
    assert result.json() == saved
    data = client.get('/api/models').json()
    assert data['independent_circuit_verification'] == saved
    assert data['benchmark_scorecard']['frozen_v1']['comparisons'][1]['lower_error_targets'] == 5
    assert saved['passing_channels'] == 6 and not saved['laboratory_accuracy_established']
