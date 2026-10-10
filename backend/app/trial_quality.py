"""Conservative acquisition review for local trial feedback, not IEC certification.

Metrics remain the original linear-interpolation results. This review neither
resamples a waveform nor infers instrument bandwidth, saturation or uncertainty.
"""
import numpy as np

from .physics.compliance import RULES


VERSION = 'waveform-acquisition-review-v3'
MIN_RISING_INTERVALS = 4
MIN_POST_HALF_INTERVALS = 4
MIN_POST_HALF_TAIL_FRACTION = .02
RESOLUTION_HALFWIDTH_FRACTION = .25
DEFINITION_TYPES = {
    'virtual front/origin': 'Lightning',
    'challenge time to peak/from explicit onset': 'Switching',
}


def review_context(measured, impulse_type, rules):
    """Resolve a recorded challenge scale without guessing an unknown impulse."""
    inferred = DEFINITION_TYPES.get(measured.get('definition'))
    if impulse_type is None:
        impulse_type = inferred
    if impulse_type not in ('Lightning', 'Switching'):
        raise ValueError('A known impulse type is required for capture-resolution review.')
    if inferred is not None and inferred != impulse_type:
        raise ValueError('The impulse type conflicts with the saved extraction definition.')
    selected = RULES if rules is None else rules
    if not isinstance(selected, dict) or not selected.get('id') or not selected.get('version'):
        raise ValueError('Versioned challenge rules are required for capture-resolution review.')
    rule = selected[impulse_type]
    limits = {}
    for metric in ('front', 'tail'):
        lower, upper = float(rule[f'{metric}_min_us']), float(rule[f'{metric}_max_us'])
        if not np.isfinite([lower, upper]).all() or not 0 < lower < upper:
            raise ValueError('Challenge timing limits must be finite, positive and ordered.')
        limits[metric] = RESOLUTION_HALFWIDTH_FRACTION * (upper - lower) / 2
    return {'impulse_type': impulse_type, 'rules_id': selected['id'],
            'rules_version': selected['version'],
            'rules_source': 'current_default' if rules is None else 'supplied_rules',
            'resolution_halfwidth_fraction': RESOLUTION_HALFWIDTH_FRACTION,
            'maximum_peak_neighbor_span_us': limits['front'],
            'maximum_half_value_bracket_span_us': limits['tail']}


def assess_waveform(time_us, voltage_kv, measured, *, impulse_type=None, rules=None):
    issues = []
    metrics = {'sample_count': 0, 'rising_intervals_30_90': 0,
               'minimum_rising_intervals': MIN_RISING_INTERVALS,
               'flat_crest_max_consecutive_samples': 0}
    try:
        context = review_context(measured, impulse_type, rules)
        metrics.update(context)
    except (AttributeError, TypeError, ValueError, KeyError):
        context = None
        issues.append({'code': 'missing_review_context', 'message':
            'A known impulse type and valid versioned challenge timing rules are required '
            'to review acquired peak and half-value resolution. Review the saved setup metadata.'})
    try:
        t = np.asarray(time_us, dtype=float)
        raw = np.asarray(voltage_kv, dtype=float)
        if (t.ndim != 1 or raw.ndim != 1 or len(t) != len(raw) or len(t) < 10
                or not np.isfinite(t).all() or not np.isfinite(raw).all()
                or not (np.diff(t) > 0).all()):
            raise ValueError('Missing or invalid stored waveform samples.')
        metrics['sample_count'] = len(t)
        t30, t90 = float(measured['t30_us']), float(measured['t90_us'])
        baseline = float(measured.get('baseline_kv', 0))
        polarity = float(measured['polarity'])
        crest = float(measured['crest_kv'])
        if (not np.isfinite([t30, t90, baseline, polarity, crest]).all()
                or not t[0] <= t30 < t90 <= t[-1] or crest <= 0 or polarity not in (-1, 1)):
            raise ValueError('Stored extraction metadata cannot support acquisition review.')
        # Count acquired adjacent intervals intersecting the measured rising window.
        # Total CSV row count is insufficient when the front is sampled sparsely.
        intervals = int(np.sum((t[:-1] < t90) & (t[1:] > t30)))
        metrics['rising_intervals_30_90'] = intervals
        if intervals < MIN_RISING_INTERVALS:
            issues.append({'code': 'sparse_rising_limb', 'message':
                f'Only {intervals} acquired intervals span the rising 30–90% window; '
                f'at least {MIN_RISING_INTERVALS} are required for this local-calibration heuristic. '
                'Capture the rising limb at a higher sampling rate before creating a correction.'})
        v = (raw - baseline) * polarity
        peak = int(np.argmax(v))
        if (peak in (0, len(v) - 1)
                or not np.isclose(v[peak], crest, rtol=1e-9, atol=1e-12)):
            raise ValueError('The saved crest does not match a resolved interior acquired peak.')
        # These spans describe acquired resolution, not an uncertainty bound on
        # the underlying signal. In particular, no hidden crest is reconstructed.
        peak_span = float(t[peak + 1] - t[peak - 1])
        metrics.update(peak_sample_index=peak,
                       peak_neighbor_times_us=[float(t[peak - 1]), float(t[peak + 1])],
                       peak_neighbor_span_us=peak_span)
        matches = np.flatnonzero((v[peak:-1] >= crest * .5) & (v[peak + 1:] <= crest * .5))
        if not len(matches):
            raise ValueError('No acquired falling half-value bracket is available.')
        half_index = peak + int(matches[0])
        half_span = float(t[half_index + 1] - t[half_index])
        metrics.update(half_value_bracket_indices=[half_index, half_index + 1],
                       half_value_bracket_times_us=[float(t[half_index]), float(t[half_index + 1])],
                       half_value_bracket_span_us=half_span)
        # A falling threshold at the record boundary can be a capture transition,
        # rather than an acquired impulse tail. Retain enough samples and time
        # after it for review; never extrapolate or change extracted metrics.
        tail = float(measured['tail_us'])
        half_time = float(measured['t50_us'])
        if not np.isfinite([tail, half_time]).all() or tail <= 0:
            raise ValueError('Positive finite tail metadata required.')
        post_intervals = len(t) - half_index - 2
        post_span = float(t[-1] - half_time)
        required_span = MIN_POST_HALF_TAIL_FRACTION * tail
        metrics.update(post_half_value_intervals=post_intervals,
                       minimum_post_half_value_intervals=MIN_POST_HALF_INTERVALS,
                       post_half_value_span_us=post_span,
                       minimum_post_half_value_span_us=required_span,
                       minimum_post_half_tail_fraction=MIN_POST_HALF_TAIL_FRACTION)
        if post_intervals < MIN_POST_HALF_INTERVALS or post_span + 1e-10 < required_span:
            issues.append({'code': 'incomplete_falling_limb', 'message':
                'The falling half-value crossing is too close to the capture boundary. '
                f'Acquire at least {MIN_POST_HALF_INTERVALS} further intervals and '
                f'{required_span:g} µs beyond it (2% of the extracted tail) before '
                'calibration or accuracy evaluation. A record-end transition cannot '
                'establish a complete impulse tail.'})
        if context:
            if peak_span > context['maximum_peak_neighbor_span_us'] + 1e-10:
                issues.append({'code': 'unresolved_peak', 'message':
                    f'The acquired neighbors around the crest span {peak_span:g} µs, exceeding '
                    f"the {context['maximum_peak_neighbor_span_us']:g} µs application review limit "
                    '(25% of the challenge front/peak tolerance half-width). Capture the crest '
                    'at higher time resolution before calibration or accuracy evaluation.'})
            if half_span > context['maximum_half_value_bracket_span_us'] + 1e-10:
                issues.append({'code': 'unresolved_half_value', 'message':
                    f'The acquired falling half-value bracket spans {half_span:g} µs, exceeding '
                    f"the {context['maximum_half_value_bracket_span_us']:g} µs application review limit "
                    '(25% of the challenge tail tolerance half-width). Capture the half-value '
                    'crossing at higher time resolution before calibration or accuracy evaluation.'})
        # Exact or numerically equal plateaus are review flags, not a saturation diagnosis.
        at_crest = np.isclose(v, crest, rtol=0, atol=max(abs(crest) * 1e-9, 1e-12))
        longest = current = 0
        for equal in at_crest:
            current = current + 1 if equal else 0
            longest = max(longest, current)
        metrics['flat_crest_max_consecutive_samples'] = longest
        if longest >= 3:
            issues.append({'code': 'flat_crest', 'message':
                'A sustained flat crest may be clipped or quantized. Review the acquisition '
                'range and waveform before creating a correction; clipping is not proven.'})
    except (TypeError, ValueError, KeyError):
        issues.append({'code': 'missing_acquisition_evidence', 'message':
            'Stored waveform samples or extraction metadata are missing or invalid. '
            'Re-upload the original CSV to review acquisition quality before calibration.'})
    allowed = not issues
    return {'version': VERSION, 'status': 'usable' if allowed else 'review_required',
            'calibration_allowed': allowed, 'evaluation_allowed': allowed, 'issues': issues, 'metrics': metrics,
            'scope': 'Acquisition heuristics only, not IEC certification or an instrument uncertainty estimate. '
                     'Peak-neighbor and falling half-value bracket spans must not exceed 25% of their '
                     'selected challenge timing tolerance half-widths. These limits are application review '
                     'preferences, not waveform error bounds. At least four acquired intervals and '
                     '2% of the extracted tail duration must remain beyond the falling half-value '
                     'crossing; this is a capture-completeness heuristic, not waveform classification. '
                     'No resampling, smoothing or changes to raw '
                     'samples or extracted metrics. Passing does not establish laboratory accuracy.'}
