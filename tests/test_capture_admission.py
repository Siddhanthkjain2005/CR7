"""Shared capture admission: the three defects found by the external review, reproduced first.

1. A precursor in front of a 0.7 µs main front was reported as a ~0.9 µs front,
   marked NOMINAL PASS and admitted to calibration.
2. A declared-polarity mismatch was flagged at upload, but the calibration API
   accepted the capture anyway.
3. A shot fired at 97 % of the recommended charge matched its as-fired physics
   prediction, yet a −3 % crest correction (−42.75 kV at 1425 kV) was applied
   to the original setting.
Also: as-fired settings outside the generator ratings need a recorded review.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app import main, storage
from backend.app.physics.circuit import simulate
from backend.app.physics.waveform_metrics import waveform_from_metrics

STOCK = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1}],
         'tail': [{'ohm': 520, 'count_per_stage': 1}], 'provenance': 'Test assumption: one unit per value per stage'}
REQUEST = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
               load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83, test_kv=1425,
               inventory_override=STOCK)
REVIEW = {'reviewer': 'Test reviewer', 'reason': 'Reviewed the capture and the rating record for this test.'}


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


def csv(t, v):
    return 'time_us,voltage_kv\n' + '\n'.join(f'{a:.12g},{b:.12g}' for a, b in zip(t, v))


def circuit_shot(run, charge=None, sign=1.0):
    c = run['candidates'][0]; s = c['settings']; p = run['profile']; i = run['inputs']
    total = i['load_c_pf'] + i['divider_c_pf'] + i['stray_c_pf'] + p['base_c_pf']
    wave = simulate(s['stages'], charge or s['charge_kv_stage'], s['front_r_stage'], s['tail_r_stage'],
                    p['stage_c_uf'], total, i['l_uh'], i['efficiency'], 'Lightning', True)['waveform']
    t, v = np.array(wave['time_us']), np.array(wave['voltage_kv'])
    keep = t <= 400
    return csv(t[keep], sign * v[keep])


def main_front(kind):
    """0.7/50 µs main impulse at 2 µs, with a separate precursor or a shelf in front of it."""
    w = waveform_from_metrics(0.7, 50, 1425, 'Lightning', points=4000)
    t = np.round(np.arange(0, 160, 0.005), 6)
    v = np.interp(t - 2.0, w['time_us'], w['voltage_kv'], left=0)
    if kind == 'precursor':
        v = v + .35 * 1425 * np.exp(-.5 * ((t - 1.98) / .03) ** 2)
    elif kind == 'shelf':
        shelf = np.where(t >= 1.9, .33 * 1425 * (1 - np.exp(-(t - 1.9) / .01)), 0)
        v = np.where(t < 4, np.maximum(v, shelf), v)
    return csv(t, v)


def upload(client, run, content, **fields):
    data = {'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id'],
            'source_type': 'generated_stress_test', 'capture_purpose': 'calibration', **fields}
    response = client.post('/api/trials/upload', data=data, files={'file': ('shot.csv', content, 'text/csv')})
    assert response.status_code == 200, response.text
    return response.json()


def codes(items):
    return {i['code'] for i in items}


def fit(client, trial):
    return client.post('/api/parameter-calibrations', json={'trial_ids': [trial['id']]})


# Defect 1 -----------------------------------------------------------------

def test_precursor_cannot_pass_or_enter_calibration(lab):
    client, run = lab
    trial = upload(client, run, main_front('precursor'))
    # The analyzer's first-crossing metric is preserved, not rewritten ...
    assert trial['measured']['front_us'] == pytest.approx(.894, abs=.01)
    # ... but it is never shown as a nominal pass, and the connected main limb is reported for review.
    assert trial['compliance']['status'] == 'REVIEW REQUIRED'
    issue = next(i for i in trial['quality']['issues'] if i['code'] == 'disconnected_rising_limb')
    assert issue['reviewable'] is False
    assert trial['quality']['metrics']['connected_limb_front_us'] == pytest.approx(.70, abs=.01)
    # Every route refuses it, and a reviewer cannot wave it through.
    for response in (client.post(f"/api/trials/{trial['id']}/calibrate"), fit(client, trial)):
        assert response.status_code == 422 and 'returns below 30%' in response.json()['detail']
    review = client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'accept_flags',
                         'codes': ['disconnected_rising_limb'], **REVIEW})
    assert review.status_code == 422 and 'cannot be accepted' in review.json()['detail']
    assert not storage.list_records('calibration') and not storage.list_records('parameter_calibration')


def test_connected_shelf_needs_a_recorded_review(lab):
    client, run = lab
    trial = upload(client, run, main_front('shelf'))
    assert trial['compliance']['status'] == 'REVIEW REQUIRED'
    assert 'two_stage_rise' in codes(trial['quality']['issues'])
    response = fit(client, trial)
    assert response.status_code == 422 and 'Awaiting a recorded review' in response.json()['detail']
    accepted = client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'accept_flags',
                           'codes': ['two_stage_rise'], **REVIEW})
    assert accepted.status_code == 200 and accepted.json()['decision'] == 'accept_flags'
    admission = client.get(f"/api/trials/{trial['id']}/admission").json()
    assert admission['uses']['parameter_fit']['admitted'] is True
    assert 'two_stage_rise' in codes(admission['uses']['parameter_fit']['accepted_by_review'])
    # The stored capture and its metrics are untouched by the review.
    assert storage.get(trial['id'], 'trial')['measured'] == trial['measured']


# Defect 2 -----------------------------------------------------------------

def test_declared_polarity_mismatch_blocks_every_route(lab):
    client, run = lab
    trial = upload(client, run, circuit_shot(run, sign=-1), expected_polarity='positive')
    assert trial['compliance']['status'] == 'REVIEW REQUIRED'
    assert trial['admission']['local_correction']['admitted'] is False
    for response in (client.post(f"/api/trials/{trial['id']}/calibrate"), fit(client, trial)):
        assert response.status_code == 422 and 'expected positive' in response.json()['detail']
    # A record saved without the upload's quality copy is re-checked from its instrument declaration.
    legacy = storage.get(trial['id'], 'trial')
    for key in ('quality', 'admission'):
        legacy.pop(key)
    storage.put('trial', 'legacy-polarity', {k: v for k, v in legacy.items() if k not in ('id', 'created_at')})
    assert client.post('/api/trials/legacy-polarity/calibrate').status_code == 422
    refused = client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'accept_flags',
                          'codes': ['polarity_mismatch'], **REVIEW})
    assert refused.status_code == 422
    assert not storage.list_records('calibration') and not storage.list_records('parameter_calibration')


def test_polarity_mismatch_blocks_independent_evaluation(lab):
    client, run = lab
    ids = []
    for i, scale in enumerate((1.0, 1.001, 1.002)):
        text = circuit_shot(run, sign=-1 if i == 0 else 1)
        if scale != 1:
            lines = text.splitlines()
            text = '\n'.join([lines[0]] + [f"{r.split(',')[0]},{float(r.split(',')[1]) * scale:.12g}" for r in lines[1:]])
        ids.append(upload(client, run, text, capture_purpose='validation', source_type='measured_lab',
                          expected_polarity='positive')['id'])
    response = client.post('/api/evaluations', json={'trial_ids': ids})
    assert response.status_code == 422 and 'review' in response.json()['detail']


# Defect 3 -----------------------------------------------------------------

def test_shot_at_different_charge_is_not_treated_as_model_bias(lab):
    client, run = lab
    c = run['candidates'][0]
    fired = .97 * c['settings']['charge_kv_stage']
    trial = upload(client, run, circuit_shot(run, charge=fired), as_fired_charge_kv_stage=str(fired))
    crest = c['hybrid']['crest_kv']
    # History is kept: the shot is 3 % below the saved prediction for the recommended setting ...
    assert trial['bias'][2] == pytest.approx(-.03 * crest, rel=1e-3)
    # ... but that is the configuration change, and the model error at the as-fired setting is ~zero.
    assert trial['model_residual']['basis'].startswith('circuit prediction at the as-fired')
    assert np.allclose(trial['model_residual']['values'], 0, atol=1e-3 * crest)
    assert trial['configuration_difference']['values'][2] == pytest.approx(-.03 * crest, rel=1e-3)
    assert trial['calibration_bias'] is None and 'differ' in trial['calibration_bias_withheld']
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 422 and 'fired at different settings' in response.json()['detail']
    assert not storage.list_records('calibration')
    # The parameter fit re-simulates the as-fired setting and finds nothing to change.
    fitted = fit(client, trial)
    assert fitted.status_code == 200, fitted.text
    assert fitted.json()['parameters']['loss_scale'] == pytest.approx(1, abs=2e-3)
    assert abs(fitted.json()['fit']['residual_pct'][0]['crest_kv']) < .05


def test_matching_as_fired_settings_still_allow_a_scoped_offset(lab):
    client, run = lab
    c = run['candidates'][0]
    trial = upload(client, run, circuit_shot(run), as_fired_charge_kv_stage=str(c['settings']['charge_kv_stage']))
    assert trial['settings_review']['same_as_recommended'] is True
    assert trial['calibration_bias'] is not None
    assert client.post(f"/api/trials/{trial['id']}/calibrate").status_code == 200


# Out-of-rating as-fired settings -----------------------------------------

def test_out_of_rating_shot_needs_review_and_reviews_are_append_only(lab):
    client, run = lab
    trial = upload(client, run, circuit_shot(run, charge=205.0), as_fired_charge_kv_stage='205')
    flags = codes(trial['as_fired']['rating_flags'])
    assert {'as_fired_charge_above_rating', 'as_fired_stage_energy_above_rating'} <= flags
    assert flags <= codes(trial['admission']['parameter_fit']['awaiting_review'])
    response = fit(client, trial)
    assert response.status_code == 422 and 'exceeds the 200 kV stage rating' in response.json()['detail']
    ok = client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'accept_flags', 'codes': sorted(flags), **REVIEW})
    assert ok.status_code == 200
    assert fit(client, trial).status_code == 200
    # Exclusion and reinstatement are further records; nothing is overwritten.
    client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'exclude', **REVIEW})
    excluded = fit(client, trial)
    assert excluded.status_code == 422 and 'excluded' in excluded.json()['detail']
    client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'reinstate', **REVIEW})
    history = client.get(f"/api/trials/{trial['id']}/admission").json()['review']['history']
    assert [h['decision'] for h in history] == ['accept_flags', 'exclude', 'reinstate']
    assert client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'accept_flags', 'codes': [],
                       **REVIEW}).status_code == 422


def test_review_requires_reviewer_and_reason(lab):
    client, run = lab
    trial = upload(client, run, circuit_shot(run))
    assert client.post(f"/api/trials/{trial['id']}/reviews", json={'decision': 'exclude', 'reviewer': 'x',
                       'reason': 'short'}).status_code == 422
