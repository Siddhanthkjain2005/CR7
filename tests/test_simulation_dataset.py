"""Versioned simulation dataset: provenance, grouped splits, honest labels, retained failures."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.physics.circuit import simulate

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'data/generated/circuit_dataset_v1'


@pytest.fixture(scope='module')
def data():
    manifest = json.loads((FOLDER/'manifest.json').read_text())
    return pd.read_csv(FOLDER/'dataset.csv.gz'), manifest


def test_files_match_manifest_and_frozen_test_split(data):
    frame, manifest = data
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((FOLDER/name).read_bytes()).hexdigest() == digest
    test_groups = sorted(frame.loc[frame.split == 'test', 'group_id'].unique())
    assert hashlib.sha256('\n'.join(test_groups).encode()).hexdigest() == manifest['split']['test_groups_sha256']
    assert len(frame) == manifest['rows']


def test_configuration_groups_never_cross_splits(data):
    frame, _ = data
    assert (frame.groupby('group_id').split.nunique() == 1).all()
    # Amplitude-scaled members of one configuration share its group.
    assert frame.groupby('group_id').size().max() >= 2


def test_labels_are_simulated_outcomes_not_requested_targets(data):
    frame, _ = data
    ok = frame[frame.status == 'ok'].sample(60, random_state=5)
    for _, r in ok.iterrows():
        fresh = simulate(int(r.stages), r.charge_kv_stage, r.front_r_stage, r.tail_r_stage, r.stage_c_uf, r.total_c_pf,
                         r.l_uh, r.efficiency, r.impulse_type, False)
        for key in ('front_us', 'tail_us', 'crest_kv'):
            assert r[key] == pytest.approx(fresh[key], rel=1e-8)
    # Most labelled waveforms are not compliant: failures are kept.
    assert 0.05 < frame.loc[frame.status == 'ok', 'timing_compliant'].mean() < 0.5


def test_failures_infeasible_and_profiles_are_retained_and_distinguishable(data):
    frame, manifest = data
    assert (frame.status == 'unresolved').sum() > 0
    assert frame.loc[frame.status == 'unresolved', 'front_us'].isna().all()
    assert (~frame.hardware_feasible).sum() > 0
    assert set(frame.family) == {'cpri', 'workbook', 'custom'}
    cpri = frame[frame.family == 'cpri']
    assert (cpri.stage_c_uf == .125).all() and (cpri.max_stages == 12).all()
    workbook = frame[frame.family == 'workbook']
    assert (workbook.stage_c_uf == 3).all() and (workbook.max_stages == 15).all()
    assert manifest['provenance_classes']['measured'] == 'none'
    assert frame.provenance.str.startswith('independently_simulated').all()


def test_waveform_store_is_normalized_by_each_rows_crest(data):
    frame, _ = data
    with np.load(FOLDER/'waveforms.npz') as store:
        waves, ids = store['waveforms'].astype(float), store['row_id']
    assert list(ids) == list(frame.row_id)
    ok = (frame.status == 'ok').to_numpy()
    assert np.nanmax(np.abs(waves[ok])) <= 2.0
    assert np.isnan(waves[~ok]).all()
