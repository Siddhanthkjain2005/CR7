"""Shared admission of a saved capture for correction, parameter fitting and evaluation.

Every backend route that reuses a stored capture calls :func:`admit`. A disabled
button in the interface is not a safeguard: the same rules apply to direct API
calls. Admission never rewrites the stored capture, its samples or its extracted
metrics; reviewer decisions are separate, append-only records.
"""
import hashlib
import math
from pathlib import Path

from .trial_quality import review_trial
from .trial_provenance import classified_source

VERSION = 'capture-admission-v1'
USES = ('local_correction', 'parameter_fit', 'evaluation')
SETTING_KEYS = ('stages', 'charge_kv_stage', 'front_r_stage', 'tail_r_stage')
CIRCUIT_KEYS = ('load_c_pf', 'divider_c_pf', 'stray_c_pf', 'l_uh')
LABELS = {'stages': 'active stages', 'charge_kv_stage': 'charge per stage', 'front_r_stage': 'front resistance per stage',
          'tail_r_stage': 'tail resistance per stage', 'load_c_pf': 'test-object capacitance',
          'divider_c_pf': 'divider capacitance', 'stray_c_pf': 'stray capacitance', 'l_uh': 'connection inductance'}
# Relative difference treated as "the same setting" (entry rounding only).
SAME_SETTING_RTOL = 1e-9
REVIEW_DECISIONS = ('accept_flags', 'exclude', 'reinstate')


def rating_flags(profile, settings):
    """Out-of-rating checks on settings that were actually fired.

    Uses the same ratings as the optimizer and setup-transition checks. A shot
    already fired cannot be undone, so these are review flags, not upload errors.
    """
    flags = []
    try:
        n, q = settings['stages'], float(settings['charge_kv_stage'])
        lo, hi = profile.get('min_stages'), profile.get('max_stages')
        if lo is not None and hi is not None and not lo <= n <= hi:
            flags.append(('as_fired_stages_outside_profile', f'{n} active stages is outside the profile range {lo}–{hi}.'))
        if q > float(profile['stage_kv']) + 1e-9:
            flags.append(('as_fired_charge_above_rating',
                          f"Charge {q:g} kV per stage exceeds the {float(profile['stage_kv']):g} kV stage rating."))
        c = profile.get('stage_c_uf')
        if c:
            energy = .5 * c * 1e-6 * (q * 1000) ** 2 / 1000
            if profile.get('energy_stage_kj') and energy > profile['energy_stage_kj'] + 1e-9:
                flags.append(('as_fired_stage_energy_above_rating',
                              f"Stage energy {energy:.4g} kJ exceeds the {profile['energy_stage_kj']:g} kJ stage rating."))
            if profile.get('energy_total_kj') and n * energy > profile['energy_total_kj'] + 1e-9:
                flags.append(('as_fired_total_energy_above_rating',
                              f"Total stored energy {n * energy:.4g} kJ exceeds the {profile['energy_total_kj']:g} kJ rating."))
        for key in ('front_r_stage', 'tail_r_stage'):
            if not (isinstance(settings.get(key), (int, float)) and math.isfinite(settings[key]) and settings[key] > 0):
                flags.append(('as_fired_resistance_invalid', f'The fired {LABELS[key]} is not a positive finite value.'))
    except (KeyError, TypeError, ValueError):
        flags.append(('as_fired_rating_unverifiable', 'The fired settings could not be checked against the generator ratings.'))
    return [{'code': code, 'reviewable': True, 'message': message + ' Record a qualified review before this shot is used.'}
            for code, message in flags]


def setting_review(trial, run, candidate):
    """What was fired compared with what was recommended."""
    fired = trial.get('as_fired') or {}
    settings = fired.get('settings') or {k: candidate['settings'][k] for k in SETTING_KEYS}
    circuit = fired.get('circuit_inputs') or {k: run['inputs'][k] for k in CIRCUIT_KEYS}
    differences = []
    for key in SETTING_KEYS:
        differences.append((key, candidate['settings'][key], settings[key]))
    for key in CIRCUIT_KEYS:
        differences.append((key, run['inputs'][key], circuit[key]))
    changed = []
    for key, recommended, value in differences:
        scale = max(abs(float(recommended)), abs(float(value)), 1e-12)
        if abs(float(value) - float(recommended)) > SAME_SETTING_RTOL * scale:
            changed.append({'field': key, 'label': LABELS[key], 'recommended': recommended, 'fired': value,
                            'ratio': (float(value) / float(recommended)) if float(recommended) else None})
    return {'as_fired_recorded': bool(fired), 'same_as_recommended': not changed, 'differences': changed,
            'settings': settings, 'circuit_inputs': circuit,
            'rating_flags': rating_flags(run['profile'], settings),
            'stock_note': ('Fired resistances differ from the recommended counted-stock networks; their construction '
                           'was not checked against stock.') if any(d['field'] in ('front_r_stage', 'tail_r_stage') for d in changed) else None}


def review_state(reviews):
    """Fold append-only review decisions (oldest first) into the current state."""
    accepted, excluded, history = set(), False, []
    for record in sorted(reviews, key=lambda r: r.get('created_at', '')):
        decision = record.get('decision')
        if decision == 'accept_flags':
            accepted.update(record.get('codes') or [])
        elif decision == 'exclude':
            excluded = True
        elif decision == 'reinstate':
            excluded = False
        history.append({k: record.get(k) for k in ('id', 'created_at', 'decision', 'codes', 'reviewer', 'reason')})
    return {'accepted_codes': sorted(accepted), 'excluded': excluded, 'history': history}


def stored_reviews(trial_id):
    """Recorded review decisions for one capture (append-only storage records)."""
    from . import storage
    return [r for r in storage.list_records('capture_review', None) if r.get('trial_id') == trial_id]


def open_quality_issues(trial, run, reviews=None):
    """Acquisition issues still open after recorded reviews (reviewable ones may be accepted)."""
    quality = review_trial(trial, run)
    accepted = set(review_state(stored_reviews(trial.get('id')) if reviews is None else reviews)['accepted_codes'])
    return quality, [i for i in quality['issues'] if not (i.get('reviewable') and i['code'] in accepted)]


def raw_bytes_intact(trial, root):
    try:
        raw = (Path(root) / trial['raw_path']).resolve()
        return raw.is_relative_to(Path(root).resolve()) and raw.is_file() and \
            hashlib.sha256(raw.read_bytes()).hexdigest() == trial['raw_sha256']
    except (KeyError, TypeError, OSError):
        return False


def admit(trial, run, use, *, root, reviews=None):
    """Decide whether one stored capture may be used for ``use``.

    Returns blocking issues (never overridable), issues awaiting a recorded
    review, and accepted reviewable issues. ``admitted`` is true only when
    nothing blocks and nothing awaits review.
    """
    if use not in USES:
        raise ValueError(f'Unknown capture use {use}.')
    blocking, awaiting, accepted = [], [], []
    if reviews is None:
        reviews = stored_reviews(trial.get('id'))
    state = review_state(reviews)
    candidate = next((c for c in run.get('candidates', []) if c['id'] == trial.get('candidate_id')), None)
    purpose = trial.get('capture_purpose')
    if use in ('local_correction', 'parameter_fit') and purpose == 'validation':
        blocking.append({'code': 'validation_purpose', 'message':
            'This capture was recorded for independent validation. Validation captures are never used to correct '
            'predictions or fit parameters; upload a separate calibration capture.'})
    if use == 'evaluation' and purpose == 'calibration':
        blocking.append({'code': 'calibration_purpose', 'message':
            f"Trial {trial.get('id')} was recorded as a calibration capture; independent evaluation needs validation captures."})
    source = classified_source(trial)
    if trial.get('evidence_class') == 'image_digitized' or trial.get('source_type') == 'digitized_image':
        blocking.append({'code': 'image_digitized', 'message':
            'Digitized from an image — approximate. Image-derived samples never enter calibration or accuracy workflows.'})
    elif use == 'evaluation' and source != 'measured_lab':
        blocking.append({'code': 'not_measured', 'message': 'Synthetic demos cannot enter the laboratory accuracy review.'})
    elif use != 'evaluation' and source not in ('generated_demo', 'measured_lab'):
        blocking.append({'code': 'unclassified_source', 'message':
            'Only explicitly classified captures can create a correction or fit generator parameters.'})
    if not raw_bytes_intact(trial, root):
        blocking.append({'code': 'raw_bytes_changed', 'message':
            'Original capture CSV is missing or changed. Restore its original bytes before using it.'})
    quality = review_trial(trial, run)
    for issue in quality['issues']:
        if issue.get('reviewable') and issue['code'] in state['accepted_codes']:
            accepted.append(issue)
        elif issue.get('reviewable'):
            awaiting.append(issue)
        else:
            blocking.append(issue)
    settings = None
    if candidate is None:
        blocking.append({'code': 'candidate_missing', 'message': 'The saved candidate of this capture is missing.'})
    else:
        try:
            settings = setting_review(trial, run, candidate)
        except (KeyError, TypeError, ValueError):
            blocking.append({'code': 'settings_unverifiable', 'message': 'The fired settings could not be compared with the recommendation.'})
    if settings:
        for flag in settings['rating_flags']:
            (accepted if flag['code'] in state['accepted_codes'] else awaiting).append(flag)
        if not settings['same_as_recommended'] and use in ('local_correction', 'evaluation'):
            changed = ', '.join(f"{d['label']} {d['fired']:g} (recommended {d['recommended']:g})" for d in settings['differences'])
            message = ('This shot was fired at different settings: ' + changed + '. ')
            if use == 'local_correction':
                message += ('A one-shot offset is defined only for the identical setting, so it would mistake the effect '
                            'of the changed settings for model error. Compare against the prediction at the as-fired '
                            'settings, and use "Fit generator parameters", which re-simulates the as-fired settings.')
            else:
                message += ('Independent evaluation scores the prediction saved for the recommended settings; a shot at '
                            'other settings measures the configuration change, not that prediction.')
            blocking.append({'code': 'as_fired_settings_differ', 'message': message})
    if state['excluded']:
        blocking.append({'code': 'excluded_by_review', 'message': 'A recorded review excluded this capture from calibration and evaluation.'})
    return {'version': VERSION, 'use': use, 'admitted': not blocking and not awaiting,
            'blocking': blocking, 'awaiting_review': awaiting, 'accepted_by_review': accepted,
            'quality': quality, 'settings': settings, 'review': state,
            'scope': 'Admission checks on the saved capture and its records; the stored samples, metrics and raw file '
                     'are never changed. Reviews are recorded decisions, not proof of laboratory origin.'}


def explain(admission):
    """Single message for an API error."""
    parts = [i['message'] for i in admission['blocking']]
    if admission['awaiting_review']:
        parts.append('Awaiting a recorded review: ' + ' '.join(i['message'] for i in admission['awaiting_review']))
    return ' '.join(parts)
