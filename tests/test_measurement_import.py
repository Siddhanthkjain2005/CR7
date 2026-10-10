"""Measured-waveform import: purpose separation, instrument scale, polarity and as-fired settings."""
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app import main, storage
from backend.app.physics.circuit import simulate

STOCK = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1}],
         'tail': [{'ohm': 520, 'count_per_stage': 1}], 'provenance': 'Test assumption: one unit per value per stage'}
REQUEST = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
               load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83, test_kv=1425,
               inventory_override=STOCK)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    database = create_engine('sqlite:///' + str(tmp_path / 'lab.sqlite3'), connect_args={'check_same_thread': False})
    storage.metadata.create_all(database)
    monkeypatch.setattr(storage, 'engine', database)
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    client = TestClient(main.app)
    response = client.post('/api/optimize', json=REQUEST)
    assert response.status_code == 200, response.text
    yield client, response.json()
    database.dispose()


def shot(run, scale=1.0, sign=1.0, stages=None, charge=None):
    c = run['candidates'][0]; s = c['settings']; p = run['profile']; i = run['inputs']
    total = i['load_c_pf'] + i['divider_c_pf'] + i['stray_c_pf'] + p['base_c_pf']
    wave = simulate(stages or s['stages'], charge or s['charge_kv_stage'], s['front_r_stage'], s['tail_r_stage'],
                    p['stage_c_uf'], total, i['l_uh'], i['efficiency'], 'Lightning', True)['waveform']
    t, v = np.array(wave['time_us']), np.array(wave['voltage_kv'])
    keep = t <= 400
    return 'time_us,voltage_kv\n' + '\n'.join(f'{a:.12g},{sign * b / scale:.12g}' for a, b in zip(t[keep], v[keep]))


def upload(client, run, content, **fields):
    data = {'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id'], 'source_type': 'generated_stress_test', **fields}
    return client.post('/api/trials/upload', data=data, files={'file': ('shot.csv', content, 'text/csv')})


def test_validation_capture_can_never_become_a_correction(lab):
    client, run = lab
    trial = upload(client, run, shot(run), capture_purpose='validation').json()
    assert trial['capture_purpose'] == 'validation'
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 422 and 'never used to correct' in response.json()['detail']


def test_calibration_capture_is_rejected_from_independent_evaluation(lab, monkeypatch):
    client, run = lab
    ids = []
    for factor in (1.0, 1.01, 1.02):
        trial = upload(client, run, shot(run, scale=factor), capture_purpose='calibration').json()
        ids.append(trial['id'])
    response = client.post('/api/evaluations', json={'trial_ids': ids})
    assert response.status_code == 422 and 'calibration capture' in response.json()['detail']


def test_divider_scale_is_applied_explicitly_and_needs_a_source(lab):
    client, run = lab
    content = shot(run, scale=1000)  # recorded at a 1000:1 divider output
    missing = upload(client, run, content, voltage_scale='1000')
    assert missing.status_code == 422 and 'source of the voltage scale' in missing.json()['detail']
    trial = upload(client, run, content, voltage_scale='1000', voltage_scale_source='Divider certificate 1000:1').json()
    assert trial['measured']['crest_kv'] == pytest.approx(run['candidates'][0]['physics']['crest_kv'], rel=1e-6)
    assert trial['instrument']['voltage_scale'] == 1000
    assert any('scale factor 1000' in step for step in trial['processing']['steps'])


def test_unexpected_polarity_is_reported_not_hidden(lab):
    client, run = lab
    trial = upload(client, run, shot(run, sign=-1), expected_polarity='positive').json()
    assert trial['instrument']['detected_polarity'] == 'negative'
    assert not trial['quality']['calibration_allowed']
    assert any(issue['code'] == 'polarity_mismatch' for issue in trial['quality']['issues'])


def test_as_fired_settings_are_resimulated_without_measured_information(lab):
    client, run = lab
    c = run['candidates'][0]
    fired = c['settings']['charge_kv_stage'] * .97
    trial = upload(client, run, shot(run, charge=fired), as_fired_charge_kv_stage=str(fired)).json()
    assert trial['as_fired']['changed_fields'] == ['charge_kv_stage']
    assert trial['as_fired']['prediction']['crest_kv'] == pytest.approx(trial['measured']['crest_kv'], rel=1e-5)
    # The saved prediction is unchanged and still differs by the 3% charge reduction.
    assert trial['predicted']['crest_kv'] == pytest.approx(c['hybrid']['crest_kv'])
    assert trial['bias'][2] == pytest.approx(-.03 * c['hybrid']['crest_kv'], rel=1e-3)
    bad = upload(client, run, shot(run), as_fired_stages='13')
    assert bad.status_code == 422 and 'outside the generator profile' in bad.json()['detail']
