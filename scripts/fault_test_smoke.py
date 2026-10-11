"""Exercise saved fault experiments in a fresh database with no external network."""
import json
import os
from pathlib import Path
import socket
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix='impulse-fault-smoke-') as folder:
        os.environ['IMPULSETWIN_DB'] = str(Path(folder) / 'fresh.sqlite3')
        original_connect, original_dns = socket.socket.connect, socket.getaddrinfo

        def connect(sock, address):
            if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
                raise RuntimeError('External network forbidden during fault smoke')
            return original_connect(sock, address)

        def dns(host, *args, **kwargs):
            if host not in ('127.0.0.1', '::1', 'localhost', None):
                raise RuntimeError('External DNS forbidden during fault smoke')
            return original_dns(host, *args, **kwargs)

        socket.socket.connect, socket.getaddrinfo = connect, dns
        from fastapi.testclient import TestClient
        from backend.app.main import app
        from backend.app import storage

        try:
            with TestClient(app) as client:
                assert client.get('/api/health').json()['hardware_control'] is False
                response = client.post('/api/optimize', json={
                    'profile_id': 'cpri_problem_brief_profile', 'impulse_type': 'Lightning',
                    'test_kv': 1425, 'load_c_pf': 650, 'divider_c_pf': 250, 'stray_c_pf': 55,
                    'l_uh': 12, 'efficiency': .83, 'include_base_c': True,
                    'solver': 'circuit', 'model_mode': 'physics',
                    'stage_min': 11, 'stage_max': 11, 'monte_carlo_samples': 8,
                    'inventory_override': {
                        'front': [{'ohm': 30, 'count_per_stage': 1}],
                        'tail': [{'ohm': 520, 'count_per_stage': 1}],
                        'provenance': 'Generated smoke demonstration: assumed stock, not laboratory inventory',
                    },
                })
                assert response.status_code == 200, response.text
                run = response.json()
                original = client.get(f"/api/runs/{run['id']}").json()
                candidate = run['candidates'][0]
                path = f"/api/runs/{run['id']}/candidates/{candidate['id']}/fault-tests"
                response = client.get(path + '/reference')
                assert response.status_code == 200, response.text
                reference = response.json()
                defaults = reference['defaults']
                cases = [
                    {'test_type': 'chopped_impulse', 'chop_mode': 'front',
                     'chop_time_us': defaults['front_chop_time_us'],
                     'shunt_r_ohm': defaults['shunt_r_ohm'], 'shunt_l_uh': defaults['shunt_l_uh']},
                    {'test_type': 'chopped_impulse', 'chop_mode': 'tail',
                     'chop_time_us': defaults['tail_chop_time_us'],
                     'shunt_r_ohm': defaults['shunt_r_ohm'], 'shunt_l_uh': defaults['shunt_l_uh']},
                    {'test_type': 'stage_failure', 'failure_mode': 'uncharged_conducting',
                     'stage_indices': [1], 'remaining_charge_fraction': 0},
                    {'test_type': 'stage_failure', 'failure_mode': 'bypassed',
                     'stage_indices': [1], 'remaining_charge_fraction': 0},
                ]
                evidence_before = {k: len(storage.list_records(k, None)) for k in
                                   ('trial', 'calibration', 'parameter_calibration', 'evaluation')}
                summary = []
                for case in cases:
                    response = client.post(path, json=case)
                    assert response.status_code == 200, response.text
                    record = response.json()
                    assert record['reference']['settings']['charge_kv_stage'] == candidate['settings']['charge_kv_stage']
                    for suffix in ('', '/json', '/csv', '/report'):
                        exported = client.get('/api/fault-tests/' + record['id'] + suffix)
                        assert exported.status_code == 200, (suffix, exported.text)
                    assert client.get('/api/fault-tests/' + record['id'] + '/json').json() == record
                    if case['test_type'] == 'stage_failure':
                        assert record['fault']['metrics']['crest_kv'] < record['healthy']['metrics']['crest_kv']
                    json.dumps(record, allow_nan=False)
                    summary.append({'request': case, 'id': record['id'],
                                    'healthy_crest_kv': record['healthy']['metrics']['crest_kv'],
                                    'fault_crest_kv': record['fault']['metrics']['crest_kv']})
                assert client.get(f"/api/runs/{run['id']}").json() == original
                assert {k: len(storage.list_records(k, None)) for k in evidence_before} == evidence_before
                print(json.dumps({'status': 'PASS', 'fresh_database': True, 'external_network_denied': True,
                                  'exports': 'saved JSON, raw CSV and HTML report',
                                  'recommendation_unchanged': True, 'no_calibration_or_lab_evidence_created': True,
                                  'cases': summary}))
        finally:
            storage.engine.dispose()
            socket.socket.connect, socket.getaddrinfo = original_connect, original_dns


if __name__ == '__main__':
    main()
