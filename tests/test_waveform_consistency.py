"""Plotted waveform, reported metrics, compliance and exports must agree."""
import copy

import numpy as np
import pytest

from backend.app.optimization.engine import optimize
from backend.app.physics.circuit import simulate
from backend.app.physics.consistency import TOLERANCE, waveform_consistency
from backend.app.physics.waveform_metrics import analyze
from backend.app.reports import report_html
from backend.app.schemas import OptimizeRequest

STOCK = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1},
                   {'ohm': 3700, 'count_per_stage': 1}],
         'tail': [{'ohm': 520, 'count_per_stage': 1}, {'ohm': 22000, 'count_per_stage': 1}],
         'provenance': 'Test assumption: one unit per source value per stage'}
CPRI = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics',
            include_base_c=True, load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12,
            efficiency=.83, inventory_override=STOCK)
KEYS = ('front_us', 'tail_us', 'crest_kv')


@pytest.fixture(scope='module')
def runs():
    return {
        'cpri_li': optimize(OptimizeRequest(**CPRI, test_kv=1425)),
        'cpri_si': optimize(OptimizeRequest(**CPRI, test_kv=1050, impulse_type='Switching')),
        'workbook_li': optimize(OptimizeRequest()),
    }


@pytest.mark.parametrize('name', ['cpri_li', 'cpri_si', 'workbook_li'])
def test_every_returned_curve_reproduces_its_reported_metrics(runs, name):
    run = runs[name]
    for c in run['candidates']:
        record = c['waveform_consistency']
        assert record['consistent'], record
        assert record['primary']['same_compliance_decision']
        extracted = analyze(c['waveform']['time_us'], c['waveform']['voltage_kv'], run['inputs']['impulse_type'])
        for key in KEYS:
            assert extracted[key] == pytest.approx(c['hybrid'][key], rel=TOLERANCE[key])
        # The displayed metric rows are the compliance rows.
        assert [r['predicted'] for r in c['compliance']['rows']] == [c['hybrid'][k] for k in KEYS]


def test_circuit_metrics_come_from_the_final_plotted_solve_not_a_target_assignment(runs):
    run = runs['cpri_li']
    p = run['profile']
    for c in run['candidates']:
        s = c['settings']
        total = run['inputs']['load_c_pf'] + run['inputs']['divider_c_pf'] + run['inputs']['stray_c_pf'] + p['base_c_pf']
        fresh = simulate(s['stages'], s['charge_kv_stage'], s['front_r_stage'], s['tail_r_stage'], p['stage_c_uf'],
                         total, run['inputs']['l_uh'], run['inputs']['efficiency'], 'Lightning', True)
        for key in KEYS:
            assert c['physics'][key] == pytest.approx(fresh[key], rel=1e-12)
        # The crest equals the request only because the recommended charge is set
        # explicitly; it is a solved value, within numerical tolerance.
        assert c['physics']['crest_kv'] == pytest.approx(1425, rel=1e-9)
        assert c['waveform']['metric_points_included']
        for key in ('t30_us', 't90_us', 't50_us', 'peak_time_us'):
            assert min(abs(np.array(c['waveform']['time_us']) - c['physics'][key])) < 1e-9


def test_reference_curve_is_labelled_as_metric_reconstruction_and_crosscheck_is_simulated(runs):
    c = runs['workbook_li']['candidates'][0]
    record = c['waveform_consistency']
    assert c['waveform']['kind'] == 'metric_reconstruction'
    assert record['primary']['origin'] == 'reconstruction'
    assert 'not an independently simulated' in record['primary']['meaning']
    assert record['circuit_crosscheck']['origin'] == 'simulated'
    assert runs['workbook_li']['target_waveform']['label'] == 'Target shape'


def test_corrected_metrics_are_never_drawn_on_an_uncorrected_circuit_curve(runs):
    c = copy.deepcopy(runs['cpri_li']['candidates'][0])
    bias = np.array([.02, -1.0, 3.0])
    c['calibration'] = {'id': 'cal1', 'bias': bias.tolist(), 'source_type': 'generated_stress_test'}
    c['prediction'] = (np.array(c['prediction']) + bias).tolist()
    c['hybrid'] = dict(zip(KEYS, c['prediction']))
    record = waveform_consistency(c, 'Lightning', 1425)
    assert record['relationship'] == 'locally_corrected_metrics_shown_separately'
    assert record['consistent']
    assert 'not drawn' in record['note']


def test_a_curve_that_disagrees_with_its_metrics_is_flagged(runs):
    c = copy.deepcopy(runs['cpri_li']['candidates'][0])
    c['hybrid'] = {**c['hybrid'], 'tail_us': c['hybrid']['tail_us'] * 1.03}
    record = waveform_consistency(c, 'Lightning', 1425)
    assert not record['consistent']
    assert not record['primary']['metrics']['tail_us']['within_tolerance']


def test_exported_report_names_the_curve_and_its_consistency(runs):
    run = {**runs['workbook_li'], 'id': 'r1', 'created_at': '2026-10-10T00:00:00Z'}
    html = report_html(run)
    assert 'Shape reconstructed from three predicted metrics' in html
    assert 'within documented tolerance' in html
    run = {**runs['cpri_li'], 'id': 'r2', 'created_at': '2026-10-10T00:00:00Z'}
    assert 'Lumped-circuit simulation at the recommended settings' in report_html(run)
