"""Custom generators: complete ratings, same supported topology, circuit only."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import app
from backend.app.optimization.engine import optimize
from backend.app.schemas import OptimizeRequest

LAB = {'name': 'Lab 6-stage 600 kV', 'source': 'Test fixture nameplate', 'max_stages': 6,
       'stage_kv': 100, 'stage_c_uf': .5, 'energy_stage_kj': 2.5, 'energy_total_kj': 15}
STOCK = {'front': [{'ohm': 20, 'count_per_stage': 2}, {'ohm': 50, 'count_per_stage': 2}, {'ohm': 100, 'count_per_stage': 1}],
         'tail': [{'ohm': 400, 'count_per_stage': 2}, {'ohm': 800, 'count_per_stage': 1}, {'ohm': 10000, 'count_per_stage': 2}],
         'provenance': 'Test fixture: assumed counted stock'}
BASE = dict(profile_id='custom_generator', custom_profile=LAB, inventory_override=STOCK, solver='circuit',
            model_mode='physics', load_c_pf=800, divider_c_pf=300, stray_c_pf=100, l_uh=8, efficiency=.95)


def test_custom_generator_recommends_within_its_own_ratings():
    run = optimize(OptimizeRequest(**BASE, test_kv=400))
    assert run['profile']['id'] == 'custom_generator' and run['profile']['kind'] == 'custom_hardware'
    assert run['profile']['voltage_max_kv'] == 600
    for c in run['candidates']:
        s = c['settings']
        assert 2 <= s['stages'] <= 6 and s['charge_kv_stage'] <= 100 + 1e-9
        assert s['stored_energy_kj'] <= 15 + 1e-9
        assert c['ood']['trust_weight'] == 0 and c['ood']['state'] == 'physics_mode'
        assert c['waveform']['kind'] == 'equivalent_circuit' and c['waveform_consistency']['consistent']
        allowed = {i['ohm'] for i in STOCK['front']}
        assert {part['ohm'] for part in c['front_network']['components']} <= allowed


def test_custom_generator_rejects_impossible_requests():
    with pytest.raises(ValueError, match='outside'):
        optimize(OptimizeRequest(**BASE, test_kv=900))


@pytest.mark.parametrize('change,message', [
    ({'energy_stage_kj': 5}, '0.5·C·V²'),
    ({'energy_total_kj': 30}, 'Total energy'),
    ({'voltage_max_kv': 700}, 'erected charging voltage'),
])
def test_inconsistent_custom_ratings_are_rejected(change, message):
    with pytest.raises(ValidationError, match=message):
        OptimizeRequest(**{**BASE, 'custom_profile': {**LAB, **change}}, test_kv=400)


def test_custom_generator_requires_stock_and_circuit_prediction():
    with pytest.raises(ValidationError, match='inventory'):
        OptimizeRequest(**{**BASE, 'inventory_override': None}, test_kv=400)
    with pytest.raises(ValidationError, match='circuit prediction'):
        OptimizeRequest(**{**BASE, 'solver': 'reference', 'model_mode': 'hybrid'}, test_kv=400)
    with pytest.raises(ValidationError, match='only used with the custom'):
        OptimizeRequest(custom_profile=LAB, test_kv=400)


def test_custom_generator_api_round_trip_and_simulate():
    client = TestClient(app)
    response = client.post('/api/optimize', json={**BASE, 'test_kv': 400})
    assert response.status_code == 200, response.text
    run = response.json()
    c = run['candidates'][0]
    sim = client.post('/api/simulate', json={'inputs': run['inputs'], 'settings': {k: c['settings'][k] for k in
                      ['stages', 'charge_kv_stage', 'front_r_stage', 'tail_r_stage']}})
    assert sim.status_code == 200, sim.text
    assert sim.json()['crest_kv'] == pytest.approx(c['physics']['crest_kv'], rel=1e-9)
    report = client.get(f"/api/runs/{run['run_id']}/report")
    assert report.status_code == 200 and 'Custom generator — Lab 6-stage 600 kV' in report.text


def test_profiles_are_renamed_and_missing_equipment_reference_is_informational():
    names = {p['id']: p['name'] for p in TestClient(app).get('/api/generator-profiles').json()}
    assert names['cpri_problem_brief_profile'] == 'CPRI generator — up to 12 stages'
    assert names['workbook_reference_profile'] == 'Workbook reference — up to 15 stages'
    run = optimize(OptimizeRequest(**BASE, test_kv=400))
    assert run['test_object_review']['message'] == 'Equipment test-level reference unavailable. The entered target voltage is used.'
    assert not run['test_object_review']['confirmation_required']
