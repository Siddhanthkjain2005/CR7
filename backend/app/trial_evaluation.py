"""Score saved predictions on new laboratory captures, without fitting a model."""
from datetime import datetime
import hashlib
from pathlib import Path

import numpy as np

from .capture_admission import admit, explain, open_quality_issues
from .trial_provenance import classified_source
from .decision_metrics import captured_limits, nominal_decision, saved_envelope_decision, summarize_decisions


KEYS = ('front_us', 'tail_us', 'crest_kv')
VERSION = 'saved-prediction-laboratory-review-v2'


def normalized_capture(trial, run):
    wave = trial.get('waveform') or {}
    processing = trial.get('processing') or {}
    measured = trial.get('measured') or {}
    # Shared acquisition review, including the declared polarity; reviewable
    # flags count only after a recorded review accepted them.
    _, issues = open_quality_issues(trial, run)
    if issues:
        raise ValueError(f"Trial {trial['id']} needs capture review before evaluation.")
    return (np.asarray(wave['time_us']) - float(processing.get('time_origin_us', 0)),
            (np.asarray(wave['voltage_kv']) - float(measured.get('baseline_kv', 0)))
            * float(measured['polarity']))


def same_capture(left, right):
    return (left[0].shape == right[0].shape
            and np.allclose(left[0], right[0], rtol=1e-12, atol=1e-10)
            and np.allclose(left[1], right[1], rtol=1e-12, atol=1e-8))


def evaluate_trials(trial_ids, lookup, root):
    if not 3 <= len(trial_ids) <= 100 or len(set(trial_ids)) != len(trial_ids):
        raise ValueError('Select 3–100 distinct laboratory trial IDs.')

    def get(identifier, kind):
        try:
            return lookup(identifier, kind)
        except KeyError:
            raise ValueError(f'Missing {kind} {identifier}; its original audit record is required.')

    def candidate(run, identifier):
        selected = next((c for c in run['candidates'] if c['id'] == identifier), None)
        if selected is None:
            raise ValueError('A trial is not associated with its original saved candidate.')
        return selected

    trials = [get(identifier, 'trial') for identifier in trial_ids]
    captures = []
    capture_cache = {}
    admissions = {}
    evaluation_hashes = {trial['raw_sha256'] for trial in trials}
    for trial in trials:
        if trial.get('capture_purpose') == 'calibration':
            raise ValueError(f"Trial {trial['id']} was recorded as a calibration capture; independent evaluation needs validation captures.")
        if classified_source(trial) != 'measured_lab':
            raise ValueError('Synthetic demos cannot enter the laboratory accuracy review.')
        path = (Path(root) / trial['raw_path']).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != trial['raw_sha256']:
            raise ValueError(f"Trial {trial['id']} has missing or changed original CSV bytes.")
        trial_run = get(trial['run_id'], 'run')
        admission = admit(trial, trial_run, 'evaluation', root=root)
        # A changed firing setting is reported after the lineage checks below,
        # so a capture reused for fitting is named for that reason first.
        early = {**admission, 'blocking': [i for i in admission['blocking'] if i['code'] != 'as_fired_settings_differ']}
        if early['blocking'] or early['awaiting_review']:
            quality_codes = {i['code'] for i in admission['quality']['issues']}
            prefix = 'needs capture review before evaluation: ' if quality_codes & {i['code'] for i in early['blocking'] + early['awaiting_review']} else ''
            raise ValueError(f"Trial {trial['id']} {prefix}{explain(early)}")
        admissions[trial['id']] = admission
        capture = normalized_capture(trial, trial_run)
        if any(trial['raw_sha256'] == previous['raw_sha256'] or same_capture(capture, other)
               for previous, other in zip(trials[:len(captures)], captures)):
            raise ValueError('Repeated imports of the same waveform cannot count as new shots.')
        captures.append(capture)
        capture_cache[trial['id']] = capture

    groups = {}
    rows = []
    for trial in trials:
        run = get(trial['run_id'], 'run')
        c = candidate(run, trial['candidate_id'])
        if datetime.fromisoformat(run['created_at']) > datetime.fromisoformat(trial['created_at']):
            raise ValueError('A prediction must be saved before its evaluation capture is uploaded.')
        calibration = c.get('calibration') or {}
        calibration_id = calibration.get('id')
        ancestors = []
        seen = set()
        while calibration_id:
            if calibration_id in seen or len(seen) >= 100:
                raise ValueError('Calibration ancestry cannot be verified.')
            seen.add(calibration_id)
            cal = get(calibration_id, 'calibration')
            source = get(cal['trial_id'], 'trial')
            if source['id'] not in capture_cache:
                capture_cache[source['id']] = normalized_capture(source, get(source['run_id'], 'run'))
            # Check every ancestor, including previous shots whose corrections were replaced.
            if (source['raw_sha256'] in evaluation_hashes
                    or any(same_capture(capture_cache[source['id']], capture) for capture in captures)):
                raise ValueError('An evaluation waveform contributed to calibration. Select new shots that were not used to correct these predictions.')
            if datetime.fromisoformat(cal['created_at']) > datetime.fromisoformat(run['created_at']):
                raise ValueError('The applied calibration must predate the saved prediction.')
            ancestors.append(calibration_id)
            source_run = get(source['run_id'], 'run')
            source_candidate = candidate(source_run, source['candidate_id'])
            calibration_id = (source_candidate.get('calibration') or {}).get('id')
        fitted_id = run['inputs'].get('parameter_calibration_id')
        if fitted_id:
            fitted = get(fitted_id, 'parameter_calibration')
            used = set(fitted.get('raw_sha256', []))
            if used & evaluation_hashes:
                raise ValueError('An evaluation waveform was used to fit the generator parameters of this prediction. Select new shots.')
            for source_id in fitted.get('trial_ids', []):
                source = get(source_id, 'trial')
                if source['id'] not in capture_cache:
                    capture_cache[source['id']] = normalized_capture(source, get(source['run_id'], 'run'))
                if any(same_capture(capture_cache[source['id']], capture) for capture in captures):
                    raise ValueError('An evaluation waveform was used to fit the generator parameters of this prediction. Select new shots.')
            if datetime.fromisoformat(fitted['created_at']) > datetime.fromisoformat(run['created_at']):
                raise ValueError('The fitted parameters must predate the saved prediction.')
            ancestors.append(fitted_id)
        differ = [i for i in admissions[trial['id']]['blocking'] if i['code'] == 'as_fired_settings_differ']
        if differ:
            raise ValueError(f"Trial {trial['id']}: {differ[0]['message']}")
        inputs = run['inputs']
        impulse = inputs['impulse_type']
        limits = captured_limits(run)
        scales = limits['normalization_halfwidth']
        measured = np.array([trial['measured'][k] for k in KEYS], dtype=float)
        recorded = np.array([c['hybrid'][k] for k in KEYS], dtype=float)
        prior = np.array(calibration.get('bias', [0, 0, 0]), dtype=float)
        predictors = {'physics': np.array([c['physics'][k] for k in KEYS], dtype=float),
                      'original_model': recorded - prior, 'recorded_prediction': recorded}
        if (not np.isfinite(measured).all() or (measured <= 0).any()
                or any(not np.isfinite(p).all() or (p <= 0).any() for p in predictors.values())):
            raise ValueError('Measured values and saved predictions must be finite and positive.')
        context = {k: inputs[k] for k in ['profile_id', 'layout_id', 'solver', 'impulse_type']}
        context.update(profile_version=run['profile'].get('version'), model_version=run['model_version'],
                       model_mode=inputs['model_mode'],
                       physics_version=(c['physics'].get('diagnostics') or {}).get('model', 'workbook-reference-v1'),
                       rules_id=limits['id'], rules_version=limits['version'], rules_sha256=limits['sha256'])
        group_key = tuple(context.values())
        group = groups.setdefault(group_key, {'context': context, 'trial_ids': [], 'measured': [], 'scales': [], 'rows': [],
                                               'predictions': {name: [] for name in predictors}})
        group['trial_ids'].append(trial['id']); group['measured'].append(measured); group['scales'].append(scales)
        for name, prediction in predictors.items():
            group['predictions'][name].append(prediction)
        row = {'trial_id': trial['id'], 'run_id': run['id'], 'candidate_id': c['id'],
                     'raw_sha256': trial['raw_sha256'], 'context': context,
                     'calibration_ancestry_ids': ancestors,
                     'calibration_source': calibration.get('source_type'),
                     'ml_support': (c.get('ood') or {}).get('state', (c.get('ood') or {}).get('status')),
                     'ml_trust_weight': (c.get('ood') or {}).get('trust_weight'),
                     'uncertainty_status': c.get('compliance', {}).get('status'),
                     'inputs': inputs, 'settings': c['settings'],
                     'front_network': c['front_network'], 'tail_network': c['tail_network'],
                     'measured': measured.tolist(), 'predictions': {k: v.tolist() for k, v in predictors.items()},
                     'challenge_limits': limits,
                     'measured_decision': nominal_decision(measured, limits),
                     'prediction_decisions': {name: nominal_decision(p, limits) for name, p in predictors.items()},
                     'saved_envelope_decision': saved_envelope_decision(c.get('uncertainty'), recorded, limits)}
        rows.append(row); group['rows'].append(row)
    results = []
    for group in groups.values():
        measured = np.array(group['measured']); scales = np.array(group['scales'])
        metrics = {}
        for name, predictions in group['predictions'].items():
            error = np.array(predictions) - measured
            metrics[name] = {'mae': np.mean(abs(error), axis=0).tolist(),
                             'rmse': np.sqrt(np.mean(error ** 2, axis=0)).tolist(),
                             'mape_pct': (100 * np.mean(abs(error) / measured, axis=0)).tolist(),
                             'normalized_rmse_tolerance': np.sqrt(np.mean((error / scales) ** 2, axis=0)).tolist(),
                             'worst_absolute_error': np.max(abs(error), axis=0).tolist(),
                             'worst_normalized_error_tolerance': np.max(abs(error) / scales, axis=0).tolist()}
            worst_row, worst_target = np.unravel_index(np.argmax(abs(error) / scales), error.shape)
            metrics[name]['worst_case'] = {'trial_id': group['trial_ids'][worst_row], 'metric': KEYS[worst_target],
                'absolute_error': float(abs(error[worst_row, worst_target])),
                'normalized_error_tolerance': float(abs(error[worst_row, worst_target]) / scales[worst_row, worst_target])}
        for name in metrics:
            baseline = np.array(metrics['physics']['rmse']); rmse = np.array(metrics[name]['rmse'])
            metrics[name]['rmse_reduction_vs_physics_pct'] = [float(100 * (1 - a / b)) if b > 0 else None for a, b in zip(rmse, baseline)]
        results.append({'context': group['context'], 'sample_count': len(measured), 'trial_ids': group['trial_ids'],
                        'units': ['µs', 'µs', 'kV'], 'metrics': metrics,
                        'decisions': summarize_decisions(group['rows']),
                        'sample_note': 'Small operator-selected sample; no generalization or laboratory success probability is established.'})
    return {'version': VERSION, 'source_type': 'measured_lab', 'trial_count': len(trials),
            'groups': results, 'trial_predictions': rows,
            'models_refit': False, 'production_model_changed': False,
            'calibration_overlap_checked': True, 'duplicate_captures_checked': True,
            'scope': 'Errors and nominal waveform decisions of predictions saved before upload on operator-labeled laboratory captures. Calibration-source captures and duplicate waveforms are excluded. Acquisition checks do not certify instruments or authenticity. Groups retain profile, layout, solver/physics version, model version/mode, impulse type and captured challenge rules. False-PASS rates include explicit denominators; absent outcome classes are not treated as evidence of perfect accuracy. Saved envelope containment is separate. No confidence interval, optimizer-wide accuracy, hardware approval or automatic model promotion is claimed.'}
