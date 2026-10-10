"""Waveform Diagnostics: records, digitization, comparison, inverse analysis and safeguards."""
import copy
import hashlib
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app import main, storage
from backend.app.capture_admission import admit
from backend.app.diagnostics import digitize, imaging, inverse, jobs, render
from backend.app.diagnostics.inverse import model_curve
from backend.app.physics.circuit import response, simulate

STOCK = {'front': [{'ohm': 30, 'count_per_stage': 1}, {'ohm': 465, 'count_per_stage': 1}],
         'tail': [{'ohm': 520, 'count_per_stage': 1}], 'provenance': 'Test assumption: one unit per value per stage'}
REQUEST = dict(profile_id='cpri_problem_brief_profile', solver='circuit', model_mode='physics', include_base_c=True,
               load_c_pf=650, divider_c_pf=250, stray_c_pf=55, l_uh=12, efficiency=.83, test_kv=1425,
               inventory_override=STOCK)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    database = create_engine('sqlite:///' + str(tmp_path / 'diag.sqlite3'), connect_args={'check_same_thread': False})
    storage.metadata.create_all(database)
    monkeypatch.setattr(storage, 'engine', database)
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    client = TestClient(main.app)
    run = client.post('/api/optimize', json=REQUEST)
    assert run.status_code == 200, run.text
    yield client, run.json(), tmp_path
    database.dispose()


def session(client, run):
    response_ = client.post('/api/diagnostics', json={'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id']})
    assert response_.status_code == 200, response_.text
    return response_.json()


def base_args(view):
    reference = view['reference']
    return (reference['as_fired'] or {}).get('prediction', reference['prediction'])['circuit_args']


def csv_for(base, params=None, *, t_end=150., noise=0., seed=0, extra=None, sign=1.):
    t = np.r_[np.arange(-2, 0, .01), np.arange(0, 10, .005), np.arange(10, t_end, .05)]
    v = model_curve(base, params or {}, t)
    if extra is not None:
        v = v + extra(t)
    if noise:
        v = v + np.random.default_rng(seed).normal(0, noise, len(t))
    v = sign * v
    return 'time_us,voltage_kv\n' + '\n'.join(f'{a:.9g},{b:.9g}' for a, b in zip(t, v))


def upload_csv(client, sid, text, **fields):
    data = {'origin': 'software_simulation', 'expected_polarity': 'positive', **fields}
    r = client.post(f'/api/diagnostics/{sid}/upload', data=data, files={'file': ('shot.csv', text, 'text/csv')})
    assert r.status_code == 200, r.text
    return r.json()


def investigate(client, sid):
    started = client.post(f'/api/diagnostics/{sid}/investigate')
    assert started.status_code == 200, started.text
    status = jobs.wait(started.json()['job_id'])
    assert status['state'] == 'finished', status
    return client.get(f'/api/diagnostics/{sid}').json()


# ---------------------------------------------------------------- reference


def test_reference_snapshot_is_versioned_and_reuses_the_solver(lab):
    client, run, _ = lab
    view = session(client, run)
    ref = view['reference']
    assert ref['snapshot_version'] == 'diagnostic-reference-v1'
    assert ref['profile']['stage_c_uf'] == .125 and ref['profile']['max_stages'] == 12
    assert ref['total_c_pf'] == pytest.approx(650 + 250 + 55 + 545)
    c = run['candidates'][0]
    for key in ('front_us', 'tail_us', 'crest_kv'):
        assert ref['prediction']['metrics'][key] == pytest.approx(c['physics'][key], rel=1e-9)
    assert ref['target']['label'] == 'Illustrative target shape'
    assert {q['id'] for q in ref['open_questions']} == {'loss_factor', 'base_capacitance', 'resistor_connection'}
    assert view['next_step'] == 'upload'


def test_as_fired_settings_are_resolved_separately_and_flagged(lab):
    client, run, _ = lab
    view = session(client, run)
    first = view['reference']['id']
    charge = run['candidates'][0]['settings']['charge_kv_stage']
    fired = client.post(f"/api/diagnostics/{view['session']['session_id']}/as-fired",
                        json={'values': {'charge_kv_stage': 205.}, 'uncertain': ['stages']}).json()
    af = fired['reference']['as_fired']
    assert af['prediction']['label'] == 'Circuit prediction at the as-fired settings'
    assert af['prediction']['metrics']['crest_kv'] == pytest.approx(fired['reference']['prediction']['metrics']['crest_kv'] * 205 / charge, rel=1e-6)
    assert {f['code'] for f in af['rating_flags']} >= {'as_fired_charge_above_rating'}
    assert af['uncertain_fields'] == ['stages'] and 'front_r_stage' in af['assumed_unchanged']
    # The earlier reference revision is kept.
    assert storage.get(first, 'diagnostic_reference')['as_fired'] is None
    bad = client.post(f"/api/diagnostics/{view['session']['session_id']}/as-fired", json={'values': {'stages': 13}})
    assert bad.status_code == 422 and 'cannot fire more stages' in bad.json()['detail']


# ---------------------------------------------------------------- uploads


def test_upload_validation_never_trusts_the_filename(lab):
    client, run, root = lab
    sid = session(client, run)['session']['session_id']
    fake = client.post(f'/api/diagnostics/{sid}/upload', data={'origin': 'unknown'},
                       files={'file': ('shot.png', b'GIF89a' + b'\x00' * 200, 'image/png')})
    assert fake.status_code == 422
    png, _ = render.render_plot([{'t': [0, 1], 'v': [0, 1]}], time_range=(0, 1), voltage_range=(0, 1), size=(400, 300))
    ok = client.post(f'/api/diagnostics/{sid}/upload', data={'origin': 'physical_experiment'},
                     files={'file': ('../../evil name.png', png, 'image/png')})
    assert ok.status_code == 200, ok.text
    up = ok.json()['upload']
    assert up['sha256'] == hashlib.sha256(png).hexdigest()
    assert up['stored_path'].endswith(up['sha256'] + '.png') and 'evil' not in up['stored_path']
    assert up['origin_label'] == 'Physical experiment (declared)' and 'does not verify' in up['origin_scope']
    assert client.get(f'/api/diagnostics/{sid}/image/original').content == png
    tiny = io.BytesIO()
    from PIL import Image
    Image.new('RGB', (20, 20), 'white').save(tiny, format='PNG')
    small = client.post(f'/api/diagnostics/{sid}/upload', data={'origin': 'unknown'}, files={'file': ('a.png', tiny.getvalue(), 'image/png')})
    assert small.status_code == 422


def test_double_divider_and_log_axes_are_refused():
    axes = {'mode': 'anchors', 'time_unit': 'us', 'voltage_unit': 'kV', 'voltage_side': 'high_voltage', 'divider_ratio': 1000,
            'x_anchors': [{'px': 0, 'value': 0}, {'px': 500, 'value': 50}], 'y_anchors': [{'px': 400, 'value': 0}, {'px': 0, 'value': 1500}]}
    with pytest.raises(ValueError, match='twice'):
        digitize.calibration(axes)
    with pytest.raises(ValueError, match='Logarithmic'):
        digitize.calibration({**axes, 'divider_ratio': 1, 'x_scale': 'log'})
    with pytest.raises(ValueError, match='20 px'):
        digitize.calibration({**axes, 'divider_ratio': 1, 'x_anchors': [{'px': 0, 'value': 0}, {'px': 5, 'value': 50}]})
    scope = digitize.calibration({**axes, 'voltage_side': 'instrument', 'voltage_unit': 'V', 'divider_ratio': 1000,
                                  'divider_ratio_source': 'Certificate'})
    assert scope['kv_per_px'] == pytest.approx(1500 / 400)  # 1500 V at the instrument × 1000 = 1500 kV


# ---------------------------------------------------------------- digitization round trip


def rendered_case(base, params=None, *, t_end=60., size=(1600, 900), photo=False):
    t = np.r_[np.linspace(0, 10, 4000), np.linspace(10, t_end, 2000)]
    v = model_curve(base, params or {}, t)
    png, truth = render.render_plot([{'t': np.r_[-1, 0, t], 'v': np.r_[0, 0, v], 'color': '#1d4ed8', 'width': 1.4}],
                                    time_range=(-1, t_end), voltage_range=(-100, 1600), size=size)
    return png, truth, t, v


def test_rendered_image_round_trip_recovers_metrics_within_digitization_spread(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    base = base_args(view)
    png, truth, t, v = rendered_case(base)
    up = client.post(f'/api/diagnostics/{sid}/upload', data={'origin': 'demonstration'}, files={'file': ('plot.png', png, 'image/png')})
    assert up.status_code == 200
    x0, t0, x1, t1 = truth['x']; y0, v0, y1, v1 = truth['y']
    axes = {'mode': 'anchors', 'time_unit': 'us', 'voltage_unit': 'kV', 'voltage_side': 'high_voltage', 'divider_ratio': 1,
            'x_anchors': [{'px': x0, 'value': t0}, {'px': x1, 'value': t1}], 'y_anchors': [{'px': y0, 'value': v0}, {'px': y1, 'value': v1}]}
    seed = render.pixel_of(truth, 20, float(np.interp(20, t, v)))
    d = client.post(f'/api/diagnostics/{sid}/digitize', json={'plot_box': truth['plot_box'], 'seed': list(seed), 'axes': axes,
                                                              'expected_polarity': 'positive'})
    assert d.status_code == 200, d.text
    dig = d.json()['digitization']
    truth_m = simulate(*base.values(), 'Lightning', False)
    m = dig['analysis']['metrics']
    assert m['crest_kv'] == pytest.approx(truth_m['crest_kv'], rel=.01)
    assert m['tail_us'] == pytest.approx(truth_m['tail_us'], rel=.02)
    assert m['front_us'] == pytest.approx(truth_m['front_us'], rel=.05)
    spread = dig['quality']['digitization_spread']
    assert spread['p05']['front_us'] <= truth_m['front_us'] <= spread['p95']['front_us']
    assert dig['label'] == 'Digitized from image — approximate'
    assert dig['quality']['evidence_class'] == 'image_digitized'
    assert len(dig['overlay']['original_px']) == len(dig['samples']['time_us'])
    assert set(dig['samples']['kind']) <= {'observed', 'observed_span'}  # no fitted ideal impulse inserted


def test_photo_with_perspective_is_rectified_from_the_plot_corners():
    base = dict(stages=11, charge_kv_stage=181.9, front_r_stage=30., tail_r_stage=520., stage_c_uf=.125, total_c_pf=1500.,
                l_uh=12., efficiency=.83)
    png, truth, t, v = rendered_case(base, size=(1400, 860))
    pb = truth['plot_box']
    photo, forward = render.warp(png, [(70, 100), (1300, 40), (1350, 900), (30, 820)], quality=85)
    corners = imaging.map_points(forward, [(pb[0], pb[1]), (pb[2], pb[1]), (pb[2], pb[3]), (pb[0], pb[3])]).tolist()
    work, record = imaging.apply(imaging.oriented(photo), {'corners': corners})
    W, H = record['working_size']
    cal = digitize.calibration({'mode': 'anchors', 'time_unit': 'us', 'voltage_unit': 'kV', 'voltage_side': 'high_voltage',
                                'divider_ratio': 1, 'x_anchors': [{'px': 0, 'value': -1}, {'px': W, 'value': 60}],
                                'y_anchors': [{'px': H, 'value': -100}, {'px': 0, 'value': 1600}]})
    seed = digitize.to_pixels(cal, 20, float(np.interp(20, t, v)))
    ex = digitize.extract(work, seed, plot_box=[2, 2, W - 2, H - 2])
    ph = digitize.physical_samples(cal, ex)
    m = digitize.analyse_samples(ph['time_us'], ph['voltage_kv'], 'Lightning', 0., 0., 'positive')['metrics']
    truth_m = simulate(*base.values(), 'Lightning', False)
    assert m['crest_kv'] == pytest.approx(truth_m['crest_kv'], rel=.015)
    assert m['tail_us'] == pytest.approx(truth_m['tail_us'], rel=.03)
    # The overlay maps back into the photograph.
    back = imaging.map_points(np.array(record['working_to_original']), [[0, 0], [W, H]])
    assert np.allclose(back, [corners[0], corners[2]], atol=1.)


def test_missing_falling_limb_is_insufficient_capture_not_extrapolated(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), t_end=20.))
    cmp = client.post(f'/api/diagnostics/{sid}/compare', json={}).json()['comparison']
    tail = next(r for r in cmp['metrics'] if r['metric'] == 'tail_us')
    assert tail['status'] == 'Insufficient capture' and tail['observed'] is None
    assert next(r for r in cmp['metrics'] if r['metric'] == 'front_us')['status'] == 'Compared'
    assert max(cmp['residual']['time_us']) <= 20.


def test_precursor_and_polarity_flags_reach_the_comparison(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    base = base_args(view)
    text = csv_for(base, extra=lambda t: .35 * 1425 * np.exp(-.5 * ((t - .02) / .03) ** 2) * (t > -0.2))
    upload_csv(client, sid, text)
    cmp = client.post(f'/api/diagnostics/{sid}/compare', json={}).json()['comparison']
    codes = {i['code'] for i in cmp['observed_analysis']['issues']}
    if 'disconnected_rising_limb' in codes or 'two_stage_rise' in codes:
        assert next(r for r in cmp['metrics'] if r['metric'] == 'front_us')['status'] == 'Requires review'
    upload_csv(client, sid, csv_for(base, sign=-1.))
    cmp = client.post(f'/api/diagnostics/{sid}/compare', json={}).json()['comparison']
    assert cmp['polarity_issue'] and not cmp['quantitative_allowed']
    assert all(r['status'] in ('Requires review', 'Insufficient capture') for r in cmp['metrics'])
    assert client.post(f'/api/diagnostics/{sid}/investigate').status_code == 409


def test_alignment_is_explicit_and_recorded(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'time_shift_us': .2}))
    plain = client.post(f'/api/diagnostics/{sid}/compare', json={}).json()['comparison']
    aligned = client.post(f'/api/diagnostics/{sid}/compare', json={'alignment': {'basis': 'manual', 'time_shift_us': .2}}).json()['comparison']
    assert plain['alignment']['time_shift_us'] == 0 and aligned['alignment']['time_shift_us'] == .2
    assert aligned['whole_waveform']['normalized_mismatch'] < plain['whole_waveform']['normalized_mismatch']
    assert 'hides any crest mismatch' in aligned['normalized_view']['label']


# ---------------------------------------------------------------- inverse analysis


@pytest.mark.parametrize('params, expected', [
    ({}, ('No change needed', None)),
    ({'front_factor': .8}, ('Possible cause', 'front_network')),
    ({'tail_factor': 1.3}, ('Possible cause', 'tail_network')),
    ({'extra_load_pf': 400.}, ('Possible cause', 'effective_capacitance')),
])
def test_physics_inverse_analysis_finds_the_changed_part(lab, params, expected):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    client.post(f'/api/diagnostics/{sid}/as-fired', json={'values': {'charge_kv_stage': run['candidates'][0]['settings']['charge_kv_stage']}})
    view = client.get(f'/api/diagnostics/{sid}').json()
    upload_csv(client, sid, csv_for(base_args(view), params, noise=3., seed=4))
    assert client.post(f'/api/diagnostics/{sid}/compare', json={}).status_code == 200
    inv = investigate(client, sid)['investigation']
    assert inv['verdict']['label'] == expected[0]
    if expected[1]:
        assert inv['leading'][0] == expected[1]
        lead = next(h for h in inv['hypotheses'] if h['id'] == expected[1])
        for name, value in params.items():
            assert lead['parameters'][name] == pytest.approx(value, rel=.03, abs=10)
        finding = inv['findings'][0]
        assert finding['verification'] and finding['safety'].startswith('Checks are for qualified')
        assert 'faulty' in finding['not_a_fault_statement']
    assert 'not probabilities' in inv['statement']


def test_amplitude_only_mismatch_keeps_competing_explanations(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'gain': .94}, noise=3., seed=5))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    inv = investigate(client, sid)['investigation']
    assert inv['verdict']['label'] == 'Several explanations fit'
    leading = set(inv['leading'])
    # Charge is free because the as-fired settings were not recorded: diagnosis is limited.
    assert {'gain', 'loss_convention'} <= leading
    assert inv['verdict'].get('limited')
    gain = next(h for h in inv['hypotheses'] if h['id'] == 'gain')
    assert 'loss_convention' in gain['indistinguishable_from'] and gain['needs_more_measurement']


def test_off_model_recording_is_not_forced_into_an_explanation(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    base = base_args(view)
    # A slow second tail component and a 4 MHz oscillation: neither exists in the lumped circuit.
    extra = lambda t: np.where(t > 0, .12 * 1425 * (1 - np.exp(-t / 30.)) + .06 * 1425 * np.sin(2 * np.pi * 4 * t) * np.exp(-t / 2.), 0)
    upload_csv(client, sid, csv_for(base, extra=extra, noise=3., seed=6))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    inv = investigate(client, sid)['investigation']
    assert inv['verdict']['label'] == 'Cannot explain with the current model'
    assert inv['verdict']['message'] == 'The current equivalent-circuit model cannot adequately explain this recording.'
    assert not inv['findings']


def test_investigation_can_be_cancelled(lab, monkeypatch):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'front_factor': .8}))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    original = inverse.fit_one

    def slow(*args, **kwargs):
        import time
        time.sleep(.2)
        return original(*args, **kwargs)
    monkeypatch.setattr(inverse, 'fit_one', slow)
    job = client.post(f'/api/diagnostics/{sid}/investigate').json()['job_id']
    client.post(f'/api/diagnostics/jobs/{job}/cancel')
    status = jobs.wait(job)
    assert status['state'] == 'cancelled'
    assert client.get(f'/api/diagnostics/{sid}').json()['investigation'] is None


def test_changing_inputs_marks_downstream_results_stale(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'front_factor': .8}))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    investigate(client, sid)
    changed = client.post(f'/api/diagnostics/{sid}/as-fired', json={'values': {'l_uh': 20.}}).json()
    assert set(changed['stale']) == {'comparison', 'investigation'} and changed['next_step'] == 'compare'
    assert client.post(f'/api/diagnostics/{sid}/explore', json={'hypothesis_id': 'front_network'}).status_code == 409


# ---------------------------------------------------------------- safeguards and preservation


def test_image_derived_samples_never_enter_calibration_or_evaluation(lab):
    _, run, root = lab
    trial = {'id': 'x', 'run_id': run['run_id'], 'candidate_id': run['candidates'][0]['id'], 'evidence_class': 'image_digitized',
             'source_type': 'measured_lab', 'capture_purpose': 'calibration', 'raw_path': 'missing.csv', 'raw_sha256': '0'}
    for use in ('local_correction', 'parameter_fit', 'evaluation'):
        result = admit(trial, run, use, root=root, reviews=[])
        assert not result['admitted'] and 'image_digitized' in {i['code'] for i in result['blocking']}


def test_exploration_is_hypothetical_and_leaves_the_saved_run_unchanged(lab):
    client, run, _ = lab
    before = json.dumps(storage.get(run['run_id'], 'run'), sort_keys=True)
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'front_factor': .8}, noise=3., seed=7))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    investigate(client, sid)
    explored = client.post(f'/api/diagnostics/{sid}/explore', json={'hypothesis_id': 'front_network'})
    assert explored.status_code == 200, explored.text
    body = explored.json()
    assert body['exploration']['hypothetical'] is True and 'Hypothetical' in body['exploration']['label']
    assert body['exploration']['effective_parameters'] == {'front_scale': pytest.approx(.8, rel=.03)}
    assert json.dumps(storage.get(run['run_id'], 'run'), sort_keys=True) == before
    measurement = client.post(f'/api/diagnostics/{sid}/explore', json={'hypothesis_id': 'gain'})
    assert measurement.status_code == 422 and 'not about the generator' in measurement.json()['detail']


def test_report_and_export_state_the_evidence_class(lab):
    client, run, _ = lab
    view = session(client, run)
    sid = view['session']['session_id']
    upload_csv(client, sid, csv_for(base_args(view), {'tail_factor': 1.2}, noise=3., seed=8))
    client.post(f'/api/diagnostics/{sid}/compare', json={})
    investigate(client, sid)
    report = client.get(f'/api/diagnostics/{sid}/report')
    assert report.status_code == 200 and '<script' not in report.text
    assert 'not probabilities' in report.text and 'Illustrative target shape' in report.text
    exported = client.get(f'/api/diagnostics/{sid}/export.json').json()
    assert exported['investigation']['verdict']['label'] in ('Possible cause', 'Several explanations fit')


def test_demonstration_is_labelled_generated(lab):
    client, _, _ = lab
    view = client.post('/api/diagnostics/demo').json()
    assert view['session']['demo'] is True
    assert view['upload']['origin'] == 'demonstration' and 'not a laboratory record' in view['upload']['origin_scope']
    assert view['upload']['demo_hints']['note'].startswith('Exact axis positions')


def test_response_matches_the_plotted_circuit_curve():
    r = simulate(11, 181.9, 30, 520, .125, 1500, 12, .83, 'Lightning', True)
    v = response(11, 181.9, 30, 520, .125, 1500, 12, .83, r['waveform']['time_us'])
    assert np.allclose(v[1:], r['waveform']['voltage_kv'][1:], rtol=0, atol=1e-9 * r['crest_kv'])
