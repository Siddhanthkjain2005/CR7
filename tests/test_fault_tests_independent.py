"""Independent numerical and public-contract regressions for fault scenarios."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from scripts.verify_fault_tests import (independent_response, production_case,
                                       published_sample_metrics,
                                       rc_shunt_exponential,
                                       snapshot_for_configuration)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / 'artifacts/fault_tests/v1/protocol.json').read_text())
CASES = {case['id']: case for case in PROTOCOL['cases']}


def _fault_wave(result):
    return result['fault']['waveform']


def _healthy_wave(result):
    return result['healthy']['waveform']


@pytest.mark.parametrize('case_id', [
    'cpri_11_front_shunt_R', 'cpri_12_tail_shunt_RL',
    'workbook_10_tail_shunt_damped', 'zero_l_front_shunt_R',
    'ringing_tail_shunt_RL',
])
def test_chop_curve_agrees_with_separate_si_nodal_integration(case_id):
    case = CASES[case_id]
    result = production_case(case)
    wave = _fault_wave(result)
    reference = independent_response(case['configuration'], wave['time_us'],
                                     chop_time_us=case['chop_time_us'],
                                     shunt_r_ohm=case['shunt_r_ohm'],
                                     shunt_l_uh=case['shunt_l_uh'])
    scale = max(_healthy_wave(result)['voltage_kv'])
    assert np.max(np.abs(np.array(wave['voltage_kv'])-reference['voltage_kv']))/scale <= 1e-5
    e = reference['energy_j']
    assert max(0., float(np.diff(e).max())) / e[0] <= 1e-8
    for name in ('generator_v', 'load_v', 'series_a'):
        if name in reference['event_before']:
            assert reference['event_after'][name] == reference['event_before'][name]
    if case['shunt_l_uh'] > 0:
        assert reference['event_after']['shunt_a'] == 0


def test_zero_inductance_chop_matches_independent_rc_matrix_exponential():
    case = CASES['zero_l_front_shunt_R']
    result = production_case(case)
    wave = _fault_wave(result)
    analytic = rc_shunt_exponential(case['configuration'], wave['time_us'],
                                   case['chop_time_us'], case['shunt_r_ohm'])
    np.testing.assert_allclose(wave['voltage_kv'], analytic,
                               atol=1e-7*max(_healthy_wave(result)['voltage_kv']), rtol=0)


@pytest.mark.parametrize('case_id', ['cpri_11_uncharged_1', 'workbook_10_uncharged_9'])
def test_uncharged_conductive_stage_reduces_source_without_shape_or_charge_retuning(case_id):
    case = CASES[case_id]
    result = production_case(case)
    wave = _fault_wave(result)
    n = case['configuration']['stages']; k = len(case['failed_stages'])
    healthy_at_times = independent_response(case['configuration'], wave['time_us'])['voltage_kv']
    np.testing.assert_allclose(wave['voltage_kv'], healthy_at_times*(n-k)/n,
                               atol=1e-5*max(_healthy_wave(result)['voltage_kv']), rtol=0)


def test_bypass_response_recomputes_capacitance_and_shaping_resistance_at_original_charge():
    case = CASES['cpri_11_bypass_1']
    result = production_case(case)
    wave = _fault_wave(result)
    correct = independent_response(case['configuration'], wave['time_us'], active_stages=10)['voltage_kv']
    wrong_voltage_only = independent_response(case['configuration'], wave['time_us'], source_fraction=10/11)['voltage_kv']
    scale = max(_healthy_wave(result)['voltage_kv'])
    assert np.max(np.abs(np.array(wave['voltage_kv'])-correct))/scale < 1e-5
    assert np.max(np.abs(np.array(wave['voltage_kv'])-wrong_voltage_only))/scale > 1e-3


def test_stage_positions_are_not_given_unmodelled_location_effects():
    case = CASES['cpri_11_uncharged_1']
    other = deepcopy(case); other['failed_stages'] = [11]
    first, last = production_case(case), production_case(other)
    assert _fault_wave(first) == _fault_wave(last)


def test_generated_source_profile_snapshot_is_unchanged_by_fault_simulation():
    from backend.app.fault_tests.simulation import simulate_fault
    from backend.app.fault_tests.models import StageFailure
    configuration = CASES['cpri_11_uncharged_1']['configuration']
    snapshot = snapshot_for_configuration(configuration)
    before = deepcopy(snapshot)
    simulate_fault(snapshot, StageFailure(test_type='stage_failure',
                                         failure_mode='uncharged_conducting', stage_indices=[1]))
    assert snapshot == before
    assert snapshot['profile']['max_stages'] == 12
    assert snapshot['profile']['stage_c_uf'] == .125
    workbook = snapshot_for_configuration(CASES['workbook_10_uncharged_1']['configuration'])
    assert workbook['profile']['max_stages'] == 15
    assert workbook['profile']['stage_c_uf'] == 3


def test_protocol_is_registered_and_not_changed_after_scoring():
    registration = json.loads((ROOT/'artifacts/fault_tests/v1/protocol_registration.json').read_text())
    assert hashlib.sha256((ROOT/'artifacts/fault_tests/v1/protocol.json').read_bytes()).hexdigest() == registration['sha256']
    assert registration['created_before_production_scoring'] is True


@pytest.mark.parametrize('field,value', [
    ('chop_time_us', 0), ('chop_time_us', float('nan')), ('chop_time_us', float('inf')),
    ('chop_time_us', True), ('shunt_r_ohm', 0), ('shunt_r_ohm', -.1),
    ('shunt_r_ohm', True), ('shunt_l_uh', -1), ('shunt_l_uh', float('inf')),
    ('shunt_l_uh', False),
])
def test_chop_input_rejects_nonphysical_nonfinite_or_boolean_values(field, value):
    from backend.app.fault_tests.models import ChoppedImpulse
    request = dict(test_type='chopped_impulse', chop_mode='front', chop_time_us=.4,
                   shunt_r_ohm=20., shunt_l_uh=0.)
    request[field] = value
    with pytest.raises(ValidationError):
        ChoppedImpulse(**request)


@pytest.mark.parametrize('fields', [
    {'stage_indices': [True]}, {'stage_indices': [1, 1]}, {'stage_indices': [0]},
    {'stage_indices': [31]}, {'stage_indices': [1.2]},
    {'remaining_charge_fraction': float('nan')}, {'remaining_charge_fraction': True},
    {'failure_mode': 'open_gap'}, {'failure_mode': 'misfire'},
])
def test_stage_input_rejects_unknown_gap_faults_and_invalid_selected_stages(fields):
    from backend.app.fault_tests.models import StageFailure
    request = dict(test_type='stage_failure', failure_mode='uncharged_conducting',
                   stage_indices=[1], remaining_charge_fraction=0.)
    request.update(fields)
    with pytest.raises(ValidationError):
        StageFailure(**request)


def test_all_bypassed_is_rejected_instead_of_inventing_remaining_generator_topology():
    case = CASES['cpri_11_bypass_11']
    with pytest.raises(ValueError):
        production_case(case)


def test_chop_category_must_agree_with_prospective_healthy_peak():
    from backend.app.fault_tests.models import ChoppedImpulse
    from backend.app.fault_tests.simulation import simulate_fault
    snap = snapshot_for_configuration(CASES['cpri_11_front_shunt_R']['configuration'])
    with pytest.raises(ValueError):
        simulate_fault(snap, ChoppedImpulse(test_type='chopped_impulse', chop_mode='tail',
                                           chop_time_us=.4, shunt_r_ohm=20., shunt_l_uh=0.))


@pytest.mark.parametrize('case_id', [
    'zero_l_tail_shunt_RL', 'zero_l_tail_shunt_damped',
    'negligible_l_tail_shunt_RL', 'negligible_l_tail_shunt_damped',
])
def test_tail_chop_does_not_lose_analytic_healthy_crest_at_exact_zero_derivative(case_id):
    """Initial predeclared execution exposed four metric/curve inconsistencies."""
    result = production_case(CASES[case_id])
    wave = _fault_wave(result)
    extracted = published_sample_metrics(wave['time_us'], wave['voltage_kv'])
    for key in ('crest_kv', 'peak_time_us', 'front_us', 'tail_us'):
        assert result['fault']['metrics'][key] == pytest.approx(extracted[key], rel=1e-8, abs=1e-8)
    assert result['fault']['metrics']['crest_kv'] == pytest.approx(result['healthy']['metrics']['crest_kv'], rel=1e-12)


@pytest.mark.parametrize('event_time_us', [.4, .401, .417])
def test_fast_ring_and_nearby_event_phases_resolve_signed_extrema(event_time_us):
    """Extra regressions, separate from the frozen v1 numerical case score."""
    case = deepcopy(CASES['ringing_front_shunt_R'])
    case.update(chop_time_us=event_time_us, shunt_r_ohm=.5, shunt_l_uh=.001)
    result = production_case(case)
    wave = _fault_wave(result)
    reference = independent_response(case['configuration'], wave['time_us'],
                                     chop_time_us=event_time_us, shunt_r_ohm=.5,
                                     shunt_l_uh=.001, method='Radau')
    scale = max(_healthy_wave(result)['voltage_kv'])
    assert np.max(np.abs(reference['voltage_kv']-wave['voltage_kv']))/scale < 1e-5
    # Probe a separate, dense early-switch grid, rather than only the solver's
    # published times. Finite-L fast reversal must not disappear between samples.
    dense_times = np.unique(np.r_[np.linspace(0,event_time_us,600),
                                  np.linspace(event_time_us,event_time_us+.12,12001)])
    dense = independent_response(case['configuration'], dense_times,
                                 chop_time_us=event_time_us, shunt_r_ohm=.5, shunt_l_uh=.001)
    reported_min = result['fault']['metrics']['minimum_kv']
    assert reported_min <= float(min(dense['voltage_kv'])) + scale*1e-4
    assert reported_min < -scale*.01
    reported_crest = result['fault']['metrics']['crest_kv']
    assert reported_crest >= float(max(dense['voltage_kv'])) - scale*1e-4


@pytest.mark.parametrize('remaining_fraction', [.4, 1.])
def test_partial_stage_charge_keeps_input_energy_distinct_from_accessible_terminal_energy(remaining_fraction):
    from backend.app.fault_tests.models import StageFailure
    from backend.app.fault_tests.simulation import simulate_fault
    c = CASES['cpri_11_uncharged_1']['configuration']
    snapshot = snapshot_for_configuration(c)
    result = simulate_fault(snapshot, StageFailure(test_type='stage_failure',
                            failure_mode='uncharged_conducting', stage_indices=[2,7],
                            remaining_charge_fraction=remaining_fraction))
    n = c['stages']; ratio = (n-2+2*remaining_fraction)/n
    single_kj = .5*c['stage_c_uf']*1e-6*(c['charge_kv_stage']*1000)**2/1000
    input_energy = (n-2+2*remaining_fraction**2)*single_kj
    terminal_energy = n*single_kj*c['efficiency']**2*ratio**2
    energy = result['energy']
    assert energy['fault_input_kj'] == pytest.approx(input_energy, rel=1e-13)
    assert energy['fault_terminal_equivalent_kj'] == pytest.approx(terminal_energy, rel=1e-13)
    assert energy['unmodeled_internal_offset_energy_kj'] == pytest.approx(
                            input_energy*c['efficiency']**2-terminal_energy, abs=1e-12)
    np.testing.assert_allclose(_fault_wave(result)['voltage_kv'],
                               np.array(_healthy_wave(result)['voltage_kv'])*ratio,
                               rtol=1e-12, atol=1e-10)
    assert result['event']['charge_kv_stage_held_fixed'] == c['charge_kv_stage']
