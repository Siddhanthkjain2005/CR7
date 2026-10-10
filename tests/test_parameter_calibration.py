"""Effective generator parameters fitted from calibration shots."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from backend.app import main, storage
from backend.app.optimization.engine import optimize
from backend.app.physics.circuit import simulate, VERSION as CIRCUIT_VERSION
from backend.app.physics.parameter_calibration import fit, predict
from backend.app.schemas import OptimizeRequest

ROOT = Path(__file__).resolve().parents[1]
STOCK = {'front': [{'ohm': 30, 'count_per_stage': 2}, {'ohm': 465, 'count_per_stage': 2}],
         'tail': [{'ohm': 520, 'count_per_stage': 2}], 'provenance': 'Test assumption: two units per value per stage'}
REQUEST = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
               load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83, test_kv=1425, inventory_override=STOCK)
TRUE = {'loss_scale': 1.06, 'extra_load_pf': 180.0, 'tail_scale': .93}


def shot(stages=11, charge=90., rf=30., rt=520., impulse='Lightning'):
    return {'stages': stages, 'charge_kv_stage': charge, 'front_r_stage': rf, 'tail_r_stage': rt, 'stage_c_uf': .125,
            'total_c_pf': 1500., 'l_uh': 12., 'efficiency': .83, 'impulse_type': impulse}


def test_fit_recovers_parameters_inside_the_fitted_family():
    shots = [{**shot(charge=q, rf=rf), 'measured': predict(shot(charge=q, rf=rf), TRUE)} for q, rf in [(90, 30), (120, 24)]]
    result = fit(shots)
    assert result['converged']
    for key, value in TRUE.items():
        assert result['parameters'][key] == pytest.approx(value, rel=2e-3, abs=.5)
    # A weak prior toward the declared model leaves a small, bounded residual.
    assert all(abs(v) < .05 for r in result['residual_pct'] for v in r.values())


def test_no_difference_fits_neutral_parameters():
    result = fit([{**shot(), 'measured': predict(shot(), None)}])
    assert result['parameters']['loss_scale'] == pytest.approx(1, abs=1e-5)
    assert abs(result['parameters']['extra_load_pf']) < .5
    assert result['parameters']['tail_scale'] == pytest.approx(1, abs=1e-5)


def record(params, impulse='Lightning'):
    profile = optimize(OptimizeRequest(**REQUEST))['profile']
    return {'id': 'pc1', 'parameters': params, 'fit': {'shots': 1, 'residual_pct': []}, 'source_type': 'generated_stress_test',
            'scope': {'generator_profile': profile, 'impulse_type': impulse, 'layout_id': 'default-layout',
                      'include_base_c': True, 'physics_version': CIRCUIT_VERSION}}


def test_fitted_parameters_change_every_candidate_consistently():
    run = optimize(OptimizeRequest(**REQUEST), parameter_calibration=record(TRUE))
    assert run['parameter_calibration_review']['parameters'] == TRUE
    p = run['profile']
    for c in run['candidates']:
        s = c['settings']
        fresh = simulate(s['stages'], s['charge_kv_stage'], s['front_r_stage'], s['tail_r_stage']*TRUE['tail_scale'], p['stage_c_uf'],
                         1500 + TRUE['extra_load_pf'], 12, .83*TRUE['loss_scale'], 'Lightning', False)
        for key in ('front_us', 'tail_us', 'crest_kv'):
            assert c['physics'][key] == pytest.approx(fresh[key], rel=1e-9)
        assert c['waveform_consistency']['consistent']
    with pytest.raises(ValueError, match='different generator'):
        optimize(OptimizeRequest(**{**REQUEST, 'impulse_type': 'Switching', 'test_kv': 1050,
                                    'inventory_override': {**STOCK, 'tail': [{'ohm': 22000, 'count_per_stage': 2}]}}),
                 parameter_calibration=record(TRUE))


def test_request_rules():
    with pytest.raises(ValidationError, match='circuit prediction only'):
        OptimizeRequest(parameter_calibration_id='x', solver='reference')
    with pytest.raises(ValidationError, match='not both'):
        OptimizeRequest(**REQUEST, parameter_calibration_id='x', calibration_id='y')


@pytest.fixture
def lab(tmp_path, monkeypatch):
    database = create_engine('sqlite:///' + str(tmp_path / 'lab.sqlite3'), connect_args={'check_same_thread': False})
    storage.metadata.create_all(database)
    monkeypatch.setattr(storage, 'engine', database)
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    client = TestClient(main.app)
    run = client.post('/api/optimize', json=REQUEST).json()
    yield client, run
    database.dispose()


def capture(run, charge_fraction=.5):
    s = run['candidates'][0]['settings']
    fired = {**s, 'charge_kv_stage': s['charge_kv_stage']*charge_fraction}
    true = simulate(fired['stages'], fired['charge_kv_stage'], fired['front_r_stage'], fired['tail_r_stage']*TRUE['tail_scale'], .125,
                    1500 + TRUE['extra_load_pf'], 12, .83*TRUE['loss_scale'], 'Lightning', True)['waveform']
    t, v = np.array(true['time_us']), np.array(true['voltage_kv'])
    keep = t <= 400
    return fired, 'time_us,voltage_kv\n' + '\n'.join(f'{a:.12g},{b:.12g}' for a, b in zip(t[keep], v[keep]))


def upload(client, run, fired, content, purpose):
    data = {'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id'], 'source_type': 'generated_stress_test',
            'capture_purpose': purpose, 'as_fired_charge_kv_stage': str(fired['charge_kv_stage'])}
    return client.post('/api/trials/upload', data=data, files={'file': ('shot.csv', content, 'text/csv')})


def test_api_fits_from_calibration_capture_and_refuses_validation_capture(lab):
    client, run = lab
    fired, content = capture(run)
    validation = upload(client, run, fired, content, 'validation').json()
    refused = client.post('/api/parameter-calibrations', json={'trial_ids': [validation['id']]})
    assert refused.status_code == 422 and 'independent validation' in refused.json()['detail']
    trial = upload(client, run, fired, content, 'calibration').json()
    created = client.post('/api/parameter-calibrations', json={'trial_ids': [trial['id']]})
    assert created.status_code == 200, created.text
    fitted = created.json()
    for key, value in TRUE.items():
        assert fitted['parameters'][key] == pytest.approx(value, rel=.02, abs=5)
    assert fitted['source_type'] == 'generated_stress_test' and not fitted['production_model_changed']
    rerun = client.post('/api/optimize', json={**REQUEST, 'parameter_calibration_id': fitted['id']})
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()['parameter_calibration_review']['id'] == fitted['id']


def test_study_artifact_records_protocol_and_gates():
    folder = ROOT/'artifacts/parameter_calibration/v1'
    result = json.loads((folder/'results.json').read_text())
    assert result['protocol_sha256'] == hashlib.sha256((folder/'protocol.json').read_bytes()).hexdigest()
    assert set(result['gates']) >= {'G1_crest', 'G2_timing', 'G3_recommendations', 'G4_no_regression', 'G5_control', 'all_pass'}
    assert 'SIMULATED' in json.loads((folder/'protocol.json').read_text())['evidence_type']


def test_shots_used_for_fitting_cannot_enter_independent_evaluation(lab):
    client, run = lab
    fired, content = capture(run)
    data = lambda r, purpose, charge: {'run_id': r['run_id'], 'candidate_id': r['candidates'][0]['id'], 'source_type': 'measured_lab',
                                       'capture_purpose': purpose, 'as_fired_charge_kv_stage': str(charge)}
    trial = client.post('/api/trials/upload', data=data(run, 'calibration', fired['charge_kv_stage']),
                        files={'file': ('cal.csv', content, 'text/csv')}).json()
    fitted = client.post('/api/parameter-calibrations', json={'trial_ids': [trial['id']]}).json()
    calibrated = client.post('/api/optimize', json={**REQUEST, 'parameter_calibration_id': fitted['id']}).json()
    ids = []
    for fraction in (.6, .7):
        f, c = capture(calibrated, fraction)
        ids.append(client.post('/api/trials/upload', data=data(calibrated, 'validation', f['charge_kv_stage']),
                               files={'file': (f'v{fraction}.csv', c, 'text/csv')}).json()['id'])
    reused = client.post('/api/trials/upload', data=data(calibrated, 'validation', fired['charge_kv_stage']),
                         files={'file': ('again.csv', content, 'text/csv')}).json()
    response = client.post('/api/evaluations', json={'trial_ids': ids + [reused['id']]})
    assert response.status_code == 422 and 'fit the generator parameters' in response.json()['detail']
