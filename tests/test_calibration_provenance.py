"""Isolated generated fixtures verify source labels; they are not lab evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app import main, storage
from backend.app.evidence import recommendation_evidence
from backend.app.physics.waveform_metrics import waveform_from_metrics


@pytest.fixture
def provenance_store(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'audit.sqlite3'),
                           connect_args={'check_same_thread': False})
    storage.metadata.create_all(engine)
    monkeypatch.setattr(storage, 'engine', engine)
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    template = json.loads((Path(__file__).resolve().parents[1] /
                           'data/demo/lightning_reference_run.json').read_text())
    run = storage.put('run', 'provenance-fixture-run', template)
    yield TestClient(main.app), run
    engine.dispose()


def import_fixture(client, run, embedded):
    candidate = run['candidates'][0]
    wave = waveform_from_metrics(*[candidate['hybrid'][k]
                                   for k in ('front_us', 'tail_us', 'crest_kv')])
    prefix = f'# source_type={embedded}\n' if embedded else ''
    csv = prefix + 'time_us,voltage_kv\n' + '\n'.join(
        f'{t:.15g},{v:.15g}' for t, v in zip(wave['time_us'], wave['voltage_kv']))
    response = client.post('/api/trials/upload',
                           data={'run_id': run['id'], 'source_type': 'measured_lab'},
                           files={'file': ('generated-test-fixture.csv', csv, 'text/csv')})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('embedded', ['generated_stress_test', 'generated_demo'])
def test_historical_measured_label_cannot_upgrade_demo_calibration(provenance_store, embedded):
    client, run = provenance_store
    trial = import_fixture(client, run, embedded)
    # Reproduce a historical/imported operator label. Original generated provenance
    # and raw bytes remain intact, so the conservative classification must win.
    legacy = deepcopy(trial)
    legacy['source_type'] = 'measured_lab'
    trial = storage.put('trial', 'legacy-' + trial['id'], legacy)
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 200, response.text
    calibration = response.json()
    assert calibration['source_type'] == 'generated_stress_test'
    assert storage.get(calibration['id'], 'calibration')['source_type'] == 'generated_stress_test'
    assert storage.get(trial['id'], 'trial')['source_type'] == 'measured_lab'
    candidate = deepcopy(run['candidates'][0])
    candidate['calibration'] = calibration
    evidence = recommendation_evidence(candidate)
    assert evidence['level'] < 4
    assert next(r['status'] for r in evidence['checks']
                if r['label'] == 'Measured local calibration') == 'PENDING'


@pytest.mark.parametrize('embedded', [None, 'measured_lab'])
def test_actual_measured_source_is_preserved(provenance_store, embedded):
    client, run = provenance_store
    trial = import_fixture(client, run, embedded)
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 200, response.text
    calibration = response.json()
    assert calibration['source_type'] == 'measured_lab'
    candidate = deepcopy(run['candidates'][0])
    candidate['calibration'] = calibration
    assert recommendation_evidence(candidate)['level'] == 4


def test_synthetic_benchmark_cannot_become_trial_calibration(provenance_store):
    client, run = provenance_store
    trial = import_fixture(client, run, 'synthetic_benchmark')
    legacy = deepcopy(trial)
    legacy['source_type'] = 'measured_lab'
    trial = storage.put('trial', 'legacy-' + trial['id'], legacy)
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 422
    assert storage.list_records('calibration') == []


def historical_calibration(client, run, embedded='generated_demo'):
    trial = import_fixture(client, run, embedded)
    legacy_trial = deepcopy(trial)
    legacy_trial['source_type'] = 'measured_lab'
    trial = storage.put('trial', 'historical-' + trial['id'], legacy_trial)
    response = client.post(f"/api/trials/{trial['id']}/calibrate")
    assert response.status_code == 200, response.text
    legacy = response.json()
    # Reproduce the old creation bug while preserving the immutable original record.
    legacy['source_type'] = 'measured_lab'
    calibration = storage.put('calibration', 'historical-' + legacy['id'], legacy)
    return trial, calibration


def saved_calibrated_run(run, calibration):
    snapshot = deepcopy(run)
    candidate = snapshot['candidates'][0]
    candidate['calibration'] = {k: calibration[k] for k in ('id', 'bias', 'source_type')}
    candidate['ood']['lab_calibrated'] = True
    for i, key in enumerate(('front_us', 'tail_us', 'crest_kv')):
        candidate['hybrid'][key] += calibration['bias'][i]
    candidate['prediction'] = [candidate['hybrid'][k] for k in ('front_us', 'tail_us', 'crest_kv')]
    snapshot['calibration_review'] = {'id': calibration['id'], 'applied': True,
                                      'source_type': 'measured_lab'}
    return storage.put('run', 'historical-calibrated-run', snapshot)


def test_old_mislabeled_calibration_is_normalized_when_applied(provenance_store):
    client, run = provenance_store
    trial, calibration = historical_calibration(client, run)
    before = storage.get(calibration['id'], 'calibration')
    candidate = run['candidates'][0]
    response = client.post('/api/optimize', json={**run['inputs'],
        'stage_min': candidate['settings']['stages'], 'stage_max': candidate['settings']['stages'],
        'monte_carlo_samples': 8, 'calibration_id': calibration['id']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['calibration_review']['applied']
    assert result['calibration_review']['source_type'] == 'generated_stress_test'
    applied = [c for c in result['candidates'] if c['calibration']]
    assert applied
    assert all(c['calibration']['source_type'] == 'generated_stress_test'
               and c['ood']['lab_calibrated'] is False and c['evidence']['level'] < 4 for c in applied)
    assert storage.get(calibration['id'], 'calibration') == before
    assert storage.get(trial['id'], 'trial')['source_type'] == 'measured_lab'


def test_old_saved_run_gets_corrected_evidence_without_rewriting_predictions(provenance_store):
    client, run = provenance_store
    _, calibration = historical_calibration(client, run)
    old = saved_calibrated_run(run, calibration)
    response = client.get(f"/api/runs/{old['id']}/judge")
    assert response.status_code == 200, response.text
    view = response.json()
    candidate = view['candidates'][0]
    assert candidate['calibration']['source_type'] == 'generated_stress_test'
    assert candidate['calibration']['source_review']['status'] == 'DOWNGRADED'
    assert candidate['ood']['lab_calibrated'] is False
    assert candidate['evidence']['level'] < 4
    assert view['calibration_review']['source_type'] == 'generated_stress_test'
    assert candidate['hybrid'] == old['candidates'][0]['hybrid']
    assert storage.get(old['id'], 'run') == old
    assert storage.get(calibration['id'], 'calibration') == calibration


@pytest.mark.parametrize('problem', ['changed_raw', 'missing_raw', 'missing_trial'])
def test_unverifiable_old_calibration_cannot_be_applied_or_presented_as_measured(provenance_store, problem):
    client, run = provenance_store
    trial, calibration = historical_calibration(client, run, 'measured_lab')
    if problem == 'changed_raw':
        (main.ROOT / trial['raw_path']).write_text('changed source bytes')
    elif problem == 'missing_raw':
        (main.ROOT / trial['raw_path']).unlink()
    else:
        changed = deepcopy(calibration)
        changed['trial_id'] = 'missing-source-trial'
        calibration = storage.put('calibration', 'missing-source-calibration', changed)
    old = saved_calibrated_run(run, calibration)
    before = storage.get(calibration['id'], 'calibration')
    response = client.post('/api/optimize', json={**run['inputs'], 'calibration_id': calibration['id']})
    assert response.status_code == 422, response.text
    assert 'Calibration origin requires review' in response.text
    view = client.get(f"/api/runs/{old['id']}/judge").json()
    candidate = view['candidates'][0]
    assert candidate['calibration']['source_type'] == 'unknown'
    assert candidate['calibration']['source_review']['status'] == 'UNVERIFIABLE'
    assert candidate['ood']['lab_calibrated'] is False
    assert candidate['evidence']['level'] < 4
    assert candidate['hybrid'] == old['candidates'][0]['hybrid']
    assert storage.get(old['id'], 'run') == old
    assert storage.get(calibration['id'], 'calibration') == before


def test_intact_measured_calibration_keeps_its_saved_evidence(provenance_store):
    client, run = provenance_store
    _, calibration = historical_calibration(client, run, 'measured_lab')
    old = saved_calibrated_run(run, calibration)
    view = client.get(f"/api/runs/{old['id']}/judge").json()
    assert view['candidates'][0]['calibration']['source_type'] == 'measured_lab'
    assert view['candidates'][0]['calibration']['source_review']['status'] == 'VERIFIED'
    assert view['candidates'][0]['evidence']['level'] == 4
    assert storage.get(old['id'], 'run') == old
