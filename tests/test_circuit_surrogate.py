"""Circuit surrogate: portable numpy inference, gated domain, never a displayed prediction."""
import json
from pathlib import Path

import numpy as np
import pytest

from backend.app.ml.surrogate import load, features
from backend.app.physics.circuit import simulate

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'artifacts/models/circuit_surrogate_v1'


@pytest.fixture(scope='module')
def model():
    return load(str(FOLDER))


def test_protocol_was_declared_before_the_recorded_test_result():
    protocol = json.loads((FOLDER/'protocol.json').read_text())
    summary = json.loads((FOLDER/'summary.json').read_text())
    import hashlib
    assert summary['protocol_sha256'] == hashlib.sha256((FOLDER/'protocol.json').read_bytes()).hexdigest()
    assert protocol['test_groups_sha256'] == json.loads((ROOT/'data/generated/circuit_dataset_v1/manifest.json').read_text())['split']['test_groups_sha256']
    assert summary['accuracy_gate_pass'] in (True, False) and 'what_this_shows' in summary


def test_inference_is_plain_numpy_and_matches_fresh_circuit_solves(model):
    rng = np.random.default_rng(41)
    rows, truth = [], []
    for _ in range(80):
        n = int(rng.integers(4, 12)); cl = float(rng.uniform(900, 2500)); cg = .125e-6/n
        impulse = 'Lightning' if rng.random() < .5 else 'Switching'
        if impulse == 'Lightning':
            rf = 1.2e-6/(3.2*cl*1e-12)*1.35/n*np.exp(rng.uniform(-.25, .25)); rt = 50e-6/(.693*(cg + cl*1e-12))/n
        else:
            rf = 250e-6/(1.67*cl*1e-12)*.4/n*np.exp(rng.uniform(-.25, .25)); rt = 2500e-6/(.693*(cg + cl*1e-12))/n
        rows.append((n, 150., rf, rt, .125, cl, 12., .9, impulse))
        r = simulate(n, 150., rf, rt, .125, cl, 12., .9, impulse, False)
        truth.append([r['front_us'], r['tail_us'], r['crest_kv']])
    cols = list(zip(*rows))
    predicted, inside = model.predict(*[np.asarray(c) for c in cols])
    assert inside.mean() > .9
    rel = np.abs(predicted[inside]/np.asarray(truth)[inside] - 1)*100
    assert np.percentile(rel, 95) < 2.0


def test_settings_far_outside_training_support_are_flagged(model):
    _, inside = model.predict(np.array([2]), np.array([100.]), np.array([1e5]), np.array([1.]), np.array([.125]),
                              np.array([100.]), np.array([0.]), np.array([.9]), np.array(['Lightning']))
    assert not inside[0]


def test_artifact_has_no_pickled_estimator():
    with np.load(FOLDER/'weights.npz', allow_pickle=False) as data:
        assert all(data[k].dtype.kind == 'f' for k in data.files)
    meta = json.loads((FOLDER/'model.json').read_text())
    assert meta['surrogate_of_solver'] is True


def test_evidence_endpoints_serve_saved_artifacts_without_running_them():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    surrogate = client.get('/api/verification/surrogate')
    assert surrogate.status_code == 200
    assert surrogate.json()['summary'] == json.loads((FOLDER/'summary.json').read_text())
    audit = client.get('/api/verification/physics-audit')
    assert audit.status_code == 200 and audit.json()['version'] == 'physics-audit-v1'
    pack = client.get('/api/evaluation-pack')
    assert pack.status_code == 200 and 'records' not in pack.json()
    assert client.get('/api/evaluation-pack?records=true').json()['records']
