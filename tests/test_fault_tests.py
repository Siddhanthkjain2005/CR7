"""Hypothetical fault API boundaries and topology semantics (no model fitting)."""
from copy import deepcopy
import json
import math
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from backend.app import storage
from backend.app.diagnostics.reference import snapshot_from_run
from backend.app.fault_tests.models import ChoppedImpulse, StageFailure
from backend.app.fault_tests.simulation import reference_view, simulate_fault
from backend.app.main import app
from backend.app.optimization.engine import profile_for
from backend.app.physics.circuit import simulate
from backend.app.physics.compliance import RULES
from backend.app.physics.waveform_metrics import analyze
from backend.app.schemas import OptimizeRequest


def saved_run(impulse='Lightning', solver='circuit', fitted=None):
    inputs = OptimizeRequest(impulse_type=impulse, solver=solver, model_mode='physics',
                             load_c_pf=850, divider_c_pf=500, stray_c_pf=150, l_uh=18.5, efficiency=.82).model_dump()
    # profile_for returns the serving registry's shared object. A malformed
    # snapshot fixture must never change later tests' actual hardware profile.
    profile = deepcopy(profile_for('workbook_reference_profile'))
    if fitted:
        profile = {**profile, 'effective_parameters': fitted}
    settings = {'stages': 9, 'charge_kv_stage': 190., 'front_r_stage': 40., 'tail_r_stage': 24.}
    if impulse == 'Switching':
        settings.update(front_r_stage=4000., tail_r_stage=1100.)
    physical = simulate(**settings, stage_c_uf=3., total_c_pf=1500., l_uh=18.5, efficiency=.82,
                        impulse_type=impulse)
    return {'id': uuid.uuid4().hex[:12], 'inputs': inputs, 'profile': profile, 'rules': RULES,
            'created_at': '2026-10-11T00:00:00+00:00',
            'candidates': [{'id': 'c1', 'rank': 1, 'settings': settings,
                            'hybrid': {k: physical[k] for k in ('front_us', 'tail_us', 'crest_kv')},
                            'front_network': {'topology': 'series', 'equivalent_ohm': 40.},
                            'tail_network': {'topology': 'series', 'equivalent_ohm': 24.}}]}


def snapshot(run=None):
    run = run or saved_run()
    snap = snapshot_from_run(run, 'c1')
    snap['inputs'] = {**snap['inputs'], 'connection_mode': run['inputs']['connection_mode']}
    return snap


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'fault.sqlite3'), connect_args={'check_same_thread': False})
    storage.metadata.create_all(engine)
    monkeypatch.setattr(storage, 'engine', engine)
    with TestClient(app) as client:
        yield client
    engine.dispose()


def write_run(run):
    return storage.put('run', run['id'], {k: v for k, v in run.items() if k not in ('id', 'created_at')})


def stage(mode='uncharged_conducting', indices=None, fraction=0):
    return StageFailure(test_type='stage_failure', failure_mode=mode,
                        stage_indices=indices or [1], remaining_charge_fraction=fraction)


def chop(snap, mode='front', inductance=1):
    ref = reference_view(snap)
    return ChoppedImpulse(test_type='chopped_impulse', chop_mode=mode,
                          chop_time_us=ref['defaults'][f'{mode}_chop_time_us'],
                          shunt_r_ohm=10, shunt_l_uh=inductance)


@pytest.mark.parametrize('field,value', [('chop_time_us', True), ('shunt_r_ohm', False),
                                        ('shunt_l_uh', True), ('shunt_r_ohm', '10'),
                                        ('chop_time_us', float('nan')), ('shunt_l_uh', float('inf'))])
def test_chop_rejects_nonphysical_json_numbers(field, value):
    body = dict(test_type='chopped_impulse', chop_mode='front', chop_time_us=.7, shunt_r_ohm=10, shunt_l_uh=1)
    body[field] = value
    with pytest.raises(ValidationError): ChoppedImpulse(**body)


@pytest.mark.parametrize('indices', [[True], [1.0], ['1'], [0], [31], [1, 1], []])
def test_stage_indices_are_actual_unique_whole_stage_numbers(indices):
    with pytest.raises(ValidationError): stage(indices=indices) if indices else StageFailure(
        test_type='stage_failure', failure_mode='uncharged_conducting', stage_indices=[])


def test_chopped_exact_event_and_tail_crest_not_renormalized():
    snap = snapshot()
    ref = reference_view(snap)
    front = simulate_fault(snap, chop(snap))
    tail = simulate_fault(snap, chop(snap, 'tail'))
    assert front['fault']['metrics']['crest_kv'] < front['healthy']['metrics']['crest_kv']
    assert tail['fault']['metrics']['crest_kv'] == pytest.approx(ref['healthy']['metrics']['crest_kv'], rel=1e-11)
    assert tail['fault']['metrics']['tail_us'] < tail['healthy']['metrics']['tail_us']
    assert not front['checks']['output_renormalized']
    assert front['checks']['original_charge_held_fixed']
    for result in (front, tail):
        assert result['energy']['balance_relative_error'] < 1e-8
        assert result['energy']['shunt_dissipated_kj'] <= result['energy']['energy_at_event_kj'] * (1 + 1e-8)
        for key in ('generator_voltage_kv', 'load_voltage_kv', 'series_current_a'):
            assert result['event']['pre_state'][key] == result['event']['post_state'][key]
        assert result['event']['post_state']['shunt_current_a'] == 0
        time = np.asarray(result['healthy']['waveform']['time_us'])
        assert np.any(time == result['event']['chop_time_us'])
        before = time < result['event']['chop_time_us']
        np.testing.assert_array_equal(np.asarray(result['healthy']['waveform']['voltage_kv'])[before],
                                      np.asarray(result['fault']['waveform']['voltage_kv'])[before])
        assert result['compliance_assessment'].startswith('Not performed')


def test_resistive_chop_preserves_capacitor_state_and_has_no_finite_jump_didt():
    snap = snapshot()
    result = simulate_fault(snap, chop(snap, inductance=0))
    event = result['event']
    assert event['post_state']['load_voltage_kv'] == event['pre_state']['load_voltage_kv']
    assert event['post_state']['shunt_current_a'] == pytest.approx(event['voltage_at_chop_kv'] * 1000 / 10)
    assert event['max_shunt_abs_di_dt_a_per_us'] is None
    assert 'jumps algebraically' in event['current_rate_note']


def test_chop_exported_positive_metrics_exactly_reextract_when_polarity_positive():
    snap = snapshot()
    result = simulate_fault(snap, chop(snap))
    wave = result['fault']['waveform']
    assert result['fault']['metrics']['reversal_pct'] < 100
    extracted = analyze(wave['time_us'], wave['voltage_kv'])
    for key in ('crest_kv', 'front_us', 'tail_us'):
        assert extracted[key] == pytest.approx(result['fault']['metrics'][key], rel=1e-8)


@pytest.mark.parametrize('fraction', [0., .25, .75, 1.])
def test_conducting_stage_is_amplitude_change_at_fixed_n_not_bypass(fraction):
    snap = snapshot()
    result = simulate_fault(snap, stage(indices=[2, 6], fraction=fraction))
    ratio = (7 + 2 * fraction) / 9
    assert result['event']['source_voltage_ratio'] == ratio
    assert result['event']['fault_stage_count'] == 9
    assert result['fault']['metrics']['crest_kv'] == pytest.approx(result['healthy']['metrics']['crest_kv'] * ratio, rel=1e-12)
    assert result['fault']['metrics']['front_us'] == pytest.approx(result['healthy']['metrics']['front_us'], rel=1e-11)
    assert result['fault']['metrics']['tail_us'] == pytest.approx(result['healthy']['metrics']['tail_us'], rel=1e-11)
    assert result['event']['charge_kv_stage_held_fixed'] == 190
    assert result['reference']['settings']['charge_kv_stage'] == 190
    assert result['energy']['fault_input_kj'] == pytest.approx(result['energy']['healthy_input_kj'] * (7 + 2 * fraction ** 2) / 9)
    if fraction < 1:
        assert result['energy']['unmodeled_internal_offset_energy_kj'] > 0


def test_full_uncharge_has_finite_zero_waveform_with_undefined_front_tail():
    result = simulate_fault(snapshot(), stage(indices=list(range(1, 10))))
    assert result['fault']['metrics']['crest_kv'] == 0
    assert result['fault']['metrics']['front_us'] is None
    assert result['fault']['metrics']['tail_us'] is None
    assert result['fault']['metrics']['peak_time_us'] is None
    assert not np.any(result['fault']['waveform']['voltage_kv'])
    assert result['energy']['fault_input_kj'] == 0
    json.dumps(result, allow_nan=False)


def test_bypass_recalculates_n_capacitance_and_resistors_without_increasing_charge():
    snap = snapshot()
    result = simulate_fault(snap, stage('bypassed', [3, 4]))
    args = result['event']['fault_circuit_args']
    assert args['stages'] == 7
    assert args['charge_kv_stage'] == 190
    expected = simulate(**args, impulse_type='Lightning')
    assert result['fault']['metrics']['crest_kv'] == expected['crest_kv']
    assert result['fault']['metrics']['front_us'] != result['healthy']['metrics']['front_us']
    assert result['fault']['metrics']['tail_us'] != result['healthy']['metrics']['tail_us']
    assert 'retain physical stored charge' in result['energy']['bypassed_capacitor_charge_note']
    with pytest.raises(ValueError, match='every stage'):
        simulate_fault(snap, stage('bypassed', list(range(1, 10))))


def test_stage_location_is_explicitly_not_a_distributed_prediction():
    snap = snapshot()
    a = simulate_fault(snap, stage(indices=[1]))
    b = simulate_fault(snap, stage(indices=[9]))
    assert a['fault']['waveform'] == b['fault']['waveform']
    assert 'no dependence' in a['event']['stage_position_scope']
    assert 'open chain' in a['event']['unsupported_failure']


def test_effective_parameters_are_applied_with_saved_provenance():
    fitted = {'loss_scale': .92, 'extra_load_pf': 350., 'tail_scale': 1.1,
              'front_scale': 1.05, 'extra_l_uh': 3., 'source_type': 'generated_stress_test', 'calibration_id': 'example-fit'}
    snap = snapshot(saved_run(fitted=fitted))
    result = simulate_fault(snap, stage())
    args = result['reference']['circuit_args']
    assert args['total_c_pf'] == 1850
    assert args['l_uh'] == 21.5
    assert args['front_r_stage'] == 42
    assert args['tail_r_stage'] == pytest.approx(26.4)
    assert args['efficiency'] == pytest.approx(.82 * .92)
    assert result['reference']['nominal_efficiency'] == .82
    assert result['reference']['nominal_efficiency'] != args['efficiency']
    assert result['reference']['physics_version']
    assert result['reference']['effective_parameters'] == fitted
    expected = simulate(**args, impulse_type='Lightning')
    assert result['healthy']['metrics']['crest_kv'] == expected['crest_kv']
    snap['effective_parameters']['unknown_parameter'] = 1
    with pytest.raises(ValueError, match='unsupported parameters'): reference_view(snap)


def test_unknown_connection_and_unknown_included_capacitance_reject():
    snap = snapshot()
    snap['inputs'].pop('connection_mode')
    with pytest.raises(ValueError, match='explicitly saved'): reference_view(snap)
    snap = snapshot()
    snap['inputs']['include_base_c'] = True
    snap['profile']['base_c_pf'] = None
    with pytest.raises(ValueError, match='unknown'): reference_view(snap)


def test_invalid_snapshot_fixture_cannot_mutate_serving_profile_registry():
    original = deepcopy(profile_for('workbook_reference_profile'))
    snap = snapshot()
    snap['profile']['base_c_pf'] = None
    snap['profile']['front_values'].clear()
    assert profile_for('workbook_reference_profile') == original


def test_switching_chop_rejected_but_stage_failure_supported():
    snap = snapshot(saved_run('Switching'))
    assert reference_view(snap)['supported']['chopped_impulse'] is False
    with pytest.raises(ValueError, match='Lightning only'): simulate_fault(snap, chop(snap))
    result = simulate_fault(snap, stage())
    assert result['fault']['metrics']['crest_kv'] > 0
    assert result['fault']['metrics']['front_us'] == pytest.approx(result['healthy']['metrics']['front_us'])


def test_mode_time_and_bypass_fraction_mismatch_are_rejected():
    snap = snapshot()
    req = chop(snap)
    req.chop_mode = 'tail'
    with pytest.raises(ValueError, match='on the front'): simulate_fault(snap, req)
    req.chop_time_us = reference_view(snap)['healthy']['metrics']['peak_time_us']
    with pytest.raises(ValueError, match='neither a front nor tail'): simulate_fault(snap, req)
    with pytest.raises(ValidationError, match='contribution fraction'): stage('bypassed', [1], .2)


def test_api_record_export_roundtrip_and_original_run_remains_unchanged(api):
    run = write_run(saved_run(solver='reference'))
    before = deepcopy(storage.get(run['id'], 'run'))
    base = f'/api/runs/{run["id"]}/candidates/c1/fault-tests'
    ref = api.get(base + '/reference')
    assert ref.status_code == 200, ref.text
    assert ref.json()['reference']['solver_note']
    response = api.post(base, json=stage().model_dump())
    assert response.status_code == 200, response.text
    result = response.json()
    eid = result['id']
    assert api.get(f'/api/fault-tests/{eid}').json() == result
    assert api.get(f'/api/fault-tests/{eid}/json').json() == result
    csv = api.get(f'/api/fault-tests/{eid}/csv')
    assert csv.status_code == 200 and 'healthy_voltage_kv,fault_voltage_kv' in csv.text
    assert len(csv.text.splitlines()) == len(result['fault']['waveform']['time_us']) + 3
    report = api.get(f'/api/fault-tests/{eid}/report')
    assert report.status_code == 200 and 'no safe-to-fire decision' in report.text
    assert result['source_type'] == 'generated_hypothetical_fault'
    assert storage.list_records('fault_test')[0]['id'] == eid
    assert storage.list_records('trial') == []
    assert storage.list_records('calibration') == []
    assert storage.get(run['id'], 'run') == before


def test_one_shot_correction_is_not_silently_applied_to_fault_waveform(api):
    run = saved_run()
    run['inputs']['calibration_id'] = 'old-metric-offset'
    record = write_run(run)
    response = api.get(f'/api/runs/{record["id"]}/candidates/c1/fault-tests/reference')
    assert response.status_code == 200
    assert response.json()['reference']['one_shot_metric_correction'].startswith('Not applied')


def test_api_missing_records_invalid_candidate_and_open_gap_request(api):
    assert api.get('/api/runs/missing/candidates/c1/fault-tests/reference').status_code == 404
    assert api.get('/api/fault-tests/missing').status_code == 404
    run = write_run(saved_run())
    assert api.post(f'/api/runs/{run["id"]}/candidates/other/fault-tests', json=stage().model_dump()).status_code == 422
    body = stage().model_dump()
    body['failure_mode'] = 'gap_did_not_fire'
    base = f'/api/runs/{run["id"]}/candidates/c1/fault-tests'
    assert api.post(base, json=body).status_code == 422
    assert api.post(base, json={**stage().model_dump(), 'stage_indices': [True]}).status_code == 422
    assert api.post(base, json={**stage().model_dump(), 'extra': True}).status_code == 422
    assert storage.list_records('fault_test') == []


def test_bypassed_energy_labels_and_report_never_imply_capacitors_are_discharged(api):
    run = write_run(saved_run())
    result = api.post(f'/api/runs/{run["id"]}/candidates/c1/fault-tests', json=stage('bypassed').model_dump()).json()
    assert 'contributing stages only' in result['energy']['fault_input_scope']
    assert 'residual energy is unverified' in result['energy']['definition']
    report = api.get(f'/api/fault-tests/{result["id"]}/report').text
    assert '<strong>Bypassed capacitor charge remains unverified.</strong>' in report
    assert 'bypass does not establish discharge or safety' in report
