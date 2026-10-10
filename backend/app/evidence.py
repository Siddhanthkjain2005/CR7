"""Conservative evidence views over immutable runs, raw captures and evaluations."""
from collections import Counter
from datetime import datetime
import hashlib
from pathlib import Path

from .trial_quality import assess_waveform
from .trial_evaluation import normalized_capture, same_capture, evaluate_trials
from .trial_provenance import classified_source

SOURCES = {'synthetic_benchmark': 'synthetic_benchmark', 'generated_demo': 'generated_demo',
           'generated_stress_test': 'generated_demo', 'measured_lab': 'measured_lab'}
LABELS = {'synthetic_benchmark': 'SYNTHETIC BENCHMARK', 'generated_demo': 'GENERATED DEMO',
          'measured_lab': 'MEASURED LAB', 'unknown': 'UNKNOWN SOURCE'}


def source_type(record):
    return classified_source(record)


def evidence_record(trial, run, quality=None):
    quality = quality or trial.get('quality') or {}
    candidate = next((c for c in run.get('candidates', []) if c['id'] == trial.get('candidate_id')), {})
    inputs = run.get('inputs', {})
    origin = source_type(trial)
    return {'schema_version': '1.0.0', 'source_type': origin, 'source_label': LABELS[origin],
            'source_id': trial.get('id') or trial.get('raw_sha256'),
            'captured_at': trial.get('captured_at'), 'imported_at': trial.get('created_at'),
            'run_id': trial.get('run_id'), 'candidate_id': trial.get('candidate_id'),
            'generator_profile': inputs.get('profile_id'), 'layout_id': inputs.get('layout_id'),
            'impulse_type': inputs.get('impulse_type'), 'model_version': run.get('model_version'),
            'solver_version': candidate.get('physics', {}).get('diagnostics', {}).get('model',
                               'workbook-reference-v1' if inputs.get('solver') == 'reference' else None),
            'raw_file_sha256': trial.get('raw_sha256'),
            'measurement_instrument': trial.get('measurement_instrument'),
            'operator_notes': trial.get('operator_notes'), 'quality_status': quality.get('status', 'unknown'),
            'eligible_for_calibration': origin in ('generated_demo', 'measured_lab') and quality.get('calibration_allowed') is True,
            # Full raw-file, duplicate, lineage and saved-prediction checks are required later.
            'eligible_for_external_accuracy': False,
            'origin_assurance': 'Operator declaration and embedded provenance, not authenticated laboratory origin.'}


def reviewed_calibration_origin(calibration, lookup, root):
    """Recheck a calibration's original source without rewriting saved audit records."""
    declared = source_type(calibration)
    trial_id = calibration.get('trial_id')
    try:
        trial = lookup(trial_id, 'trial')
        run = lookup(trial['run_id'], 'run')
        origin = source_type(trial)
        if declared not in ('generated_demo', 'measured_lab') or origin not in ('generated_demo', 'measured_lab'):
            raise ValueError('Calibration source is not an explicitly classified trial waveform.')
        raw = (Path(root) / trial['raw_path']).resolve()
        if not raw.is_relative_to(Path(root).resolve()) or not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest() != trial['raw_sha256']:
            raise ValueError('Original calibration CSV is missing or changed.')
        if not any(c['id'] == trial['candidate_id'] for c in run['candidates']):
            raise ValueError('Original calibration candidate is missing.')
        normalized_capture(trial, run)
        # Neither the calibration label nor its source record can upgrade a demo.
        resolved = 'generated_demo' if 'generated_demo' in (declared, origin) else 'measured_lab'
        normalized = 'generated_stress_test' if resolved == 'generated_demo' else resolved
        status = 'DOWNGRADED' if declared == 'measured_lab' and resolved == 'generated_demo' else 'VERIFIED'
        message = ('Generated source provenance overrides the historical measured-calibration label.'
                   if status == 'DOWNGRADED' else 'Original source, saved candidate, CSV hash and acquisition review verified.')
    except (KeyError, ValueError, TypeError, OSError) as exc:
        normalized, status = 'unknown', 'UNVERIFIABLE'
        message = f'Calibration origin requires review: {exc}'
    return {**calibration, 'source_type': normalized,
            'source_review': {'status': status, 'declared_source_type': calibration.get('source_type'),
                              'trial_id': trial_id, 'message': message,
                              'audit_record_changed': False,
                              'scope': 'Source classification and file/acquisition checks; laboratory origin remains operator-declared.'}}


def recommendation_evidence(candidate, evaluation_ids=()):
    nominal = candidate.get('compliance', {}).get('nominal_pass') is True
    cross = (candidate.get('circuit_crosscheck') or {}).get('compliance', {}).get('nominal_pass')
    ml = candidate.get('ood', {}).get('trust_weight') == 1
    verification = candidate.get('verification') or {}
    challenged = (verification.get('all_checks_pass') is True and verification.get('total', 0) > 0
                  and verification.get('unique_scenarios', 0) > 1
                  and verification.get('passed') == verification.get('total') and nominal and cross is True)
    cal = candidate.get('calibration') or {}
    calibrated = cal.get('source_type') == 'measured_lab' and bool(cal.get('id'))
    hardware = all(candidate.get(k, {}).get('inventory_feasible') is True for k in ('front_network', 'tail_network'))
    level = 0
    if ml: level = 1
    if nominal and cross is True: level = 2
    if challenged: level = 3
    if calibrated: level = 4
    if evaluation_ids: level = 5
    names = ['Physics estimate', 'Synthetic ML supported', 'Dual-model agreement',
             'Scenario challenged', 'Locally calibrated (measured)', 'Independent measured evaluation available']
    facts = [
        {'label': 'Counted hardware construction', 'status': 'PASS' if hardware else 'UNKNOWN'},
        {'label': 'ML inside synthetic support', 'status': 'PASS' if ml else 'OUTSIDE SUPPORT / OFF'},
        {'label': 'Primary nominal waveform', 'status': 'PASS' if nominal else 'FAIL' if candidate.get('compliance') else 'UNKNOWN'},
        {'label': 'Independent circuit nominal waveform', 'status': 'PASS' if cross is True else 'FAIL' if cross is False else 'NOT VERIFIED'},
        {'label': 'Fixed-setting challenge', 'status': f"{verification.get('passed', 0)}/{verification.get('total', 0)} passed" if verification else 'NOT VERIFIED'},
        {'label': 'Measured local calibration', 'status': 'AVAILABLE' if calibrated else 'PENDING'},
        {'label': 'Independent measured evaluation', 'status': 'AVAILABLE' if evaluation_ids else 'PENDING'},
    ]
    return {'version': '1.0.0', 'level': level, 'label': names[level], 'checks': facts,
            'evaluation_ids': list(evaluation_ids), 'nominal_pass': nominal,
            'scope': 'Highest evidence activity attained, not a safety score or a cumulative guarantee. Lower checks can still fail. Measured evaluation availability does not imply acceptable errors, certification or generalization.'}


def laboratory_summary(trials, calibrations, lookup, root):
    """Count all records; never turn a missing quality/integrity check into a PASS."""
    records, captures, calibration_captures = [], [], []
    calibration_ids = {c.get('trial_id') for c in calibrations}
    ancestry_complete = True
    for identifier in calibration_ids:
        try:
            t = lookup(identifier, 'trial')
            calibration_captures.append((t.get('raw_sha256'), normalized_capture(t, lookup(t['run_id'], 'run'))))
        except (KeyError, ValueError, TypeError):
            ancestry_complete = False
    for trial in sorted(trials, key=lambda t: t.get('created_at', '')):
        reasons = []
        try:
            run = lookup(trial['run_id'], 'run')
            wave = trial.get('waveform') or {}
            quality = assess_waveform(wave.get('time_us'), wave.get('voltage_kv'), trial['measured'],
                                     impulse_type=run['inputs']['impulse_type'], rules=run.get('rules', {}))
            record = evidence_record(trial, run, quality)
            if not quality['evaluation_allowed']:
                reasons.extend(i['message'] for i in quality['issues'])
            path = (Path(root) / trial['raw_path']).resolve()
            if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != trial['raw_sha256']:
                reasons.append('Original CSV missing or hash changed.')
                record['eligible_for_calibration'] = False
            if not any(c['id'] == trial['candidate_id'] for c in run['candidates']):
                reasons.append('Original saved candidate missing.')
                record['eligible_for_calibration'] = False
            if datetime.fromisoformat(run['created_at']) > datetime.fromisoformat(trial['created_at']):
                reasons.append('Prediction was not saved before upload.')
            if quality['evaluation_allowed']:
                capture = normalized_capture(trial, run)
                if any(trial['raw_sha256'] == h or same_capture(capture, other) for h, other in captures):
                    reasons.append('Duplicate capture; repeated imports are not independent shots.')
                captures.append((trial['raw_sha256'], capture))
                if trial['id'] in calibration_ids or any(trial['raw_sha256'] == h or same_capture(capture, other) for h, other in calibration_captures):
                    reasons.append('Capture used for calibration; reserve new shots for evaluation.')
            if not ancestry_complete:
                reasons.append('Calibration-source audit records need review.')
        except (KeyError, ValueError, TypeError, OSError) as exc:
            record = evidence_record(trial, {})
            record['eligible_for_calibration'] = False
            reasons.append(f'Audit context cannot be verified: {exc}')
        if record['source_type'] != 'measured_lab':
            reasons.append('Not a measured laboratory capture.')
        record['eligible_for_external_accuracy'] = not reasons
        record['exclusion_reasons'] = reasons
        records.append(record)
    measured = [r for r in records if r['source_type'] == 'measured_lab']
    def groups(key):
        return dict(Counter(r.get(key) or 'unknown' for r in measured))
    return {'version': '1.0.0', 'measured_captures': len(measured),
            'usable_for_calibration': sum(r['eligible_for_calibration'] for r in measured),
            'eligible_for_independent_evaluation': sum(r['eligible_for_external_accuracy'] for r in measured),
            'excluded_captures': sum(not r['eligible_for_external_accuracy'] for r in measured),
            'by_source': dict(Counter(r['source_type'] for r in records)),
            'by_impulse': groups('impulse_type'), 'by_profile': groups('generator_profile'),
            'by_layout': groups('layout_id'), 'by_model': groups('model_version'), 'captures': records,
            'empty_message': 'No laboratory measurements have been loaded. Synthetic performance does not establish laboratory accuracy.' if not measured else None,
            'scope': 'Eligibility is an admission check. Submit 3–100 distinct captures to the existing evaluation workflow for full cross-capture ancestry checks and grouped error metrics. No laboratory accuracy is inferred from counts.'}


def validated_evaluation_ids(run, candidate, evaluations, lookup, root):
    identifiers = []
    for evaluation in evaluations:
        rows = evaluation.get('trial_predictions', [])
        matching = [r for r in rows if r.get('run_id') == run['id'] and r.get('candidate_id') == candidate['id']]
        if not matching or evaluation.get('source_type') != 'measured_lab':
            continue
        try:
            # Recheck original bytes and independence before displaying the highest level.
            refreshed = evaluate_trials([r['trial_id'] for r in rows], lookup, root)
            if refreshed['trial_predictions'] == rows:
                identifiers.append(evaluation['id'])
        except (KeyError, ValueError, TypeError, OSError):
            continue
    return identifiers
