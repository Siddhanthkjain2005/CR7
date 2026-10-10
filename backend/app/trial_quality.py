"""Conservative acquisition review for local trial feedback, not IEC certification.

Metrics remain the original linear-interpolation results. This review neither
resamples a waveform nor infers instrument bandwidth, saturation or uncertainty.
"""
import numpy as np

from .physics.compliance import RULES


VERSION = 'waveform-acquisition-review-v4'
MIN_RISING_INTERVALS = 4
MIN_POST_HALF_INTERVALS = 4
MIN_POST_HALF_TAIL_FRACTION = .02
RESOLUTION_HALFWIDTH_FRACTION = .25
# Floating-point allowance only, not an inferred acquisition-noise bound.
# (Adopted from the uncommitted v4 connection check in the team's checkout.)
RISING_CONNECTION_RTOL = 1e-9
RISING_CONNECTION_ATOL_KV = 1e-12
# Recrossings smaller than NOISE_MULTIPLE x the pre-trigger noise are not
# counted. The noise is estimated from the acquired samples before the signal
# first reaches 10% of crest (robust MAD of first differences / sqrt 2); with
# fewer than MIN_PRETRIGGER_SAMPLES no noise is inferred and only roundoff is allowed.
NOISE_MULTIPLE = 4.0
MIN_PRETRIGGER_SAMPLES = 20
# Rise-rate profile between first crossings of 20, 25, ..., 90 % of crest.
# A smooth lumped-circuit rise has one rate maximum (its inflection). A stall
# whose rate is three times lower than the rate both before and after it is a
# second rising stage: a precursor, shelf or front oscillation. Heuristic only.
STALL_LEVELS = tuple(round(x, 2) for x in np.arange(.20, .901, .05))
STALL_RATE_FACTOR = 3.0
# Issues a qualified reviewer may accept with a recorded reason. All other
# issues block calibration and evaluation outright.
REVIEWABLE = {'two_stage_rise', 'dip_after_90_percent'}
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


def _polarity(measured):
    try:
        value = float(measured['polarity'])
    except (KeyError, TypeError, ValueError):
        return None
    return int(value) if value in (-1, 1) else None


def review_trial(trial, run):
    """Acquisition review of a stored capture, including its declared polarity.

    Every backend path that reuses a saved capture calls this, so no route can
    skip a check the upload applied.
    """
    wave = trial.get('waveform') or {}
    instrument = trial.get('instrument') or {}
    return assess_waveform(wave.get('time_us'), wave.get('voltage_kv'), trial.get('measured') or {},
                           impulse_type=run['inputs']['impulse_type'], rules=run.get('rules', {}),
                           expected_polarity=instrument.get('expected_polarity'))


def first_rising_crossings(t, v, crest, levels, peak):
    """Interpolated first upward crossing of each level before the peak (None if absent)."""
    found = []
    for fraction in levels:
        level = crest * fraction
        a, b = v[:peak], v[1:peak + 1]
        hits = np.flatnonzero((a <= level) & (b >= level))
        if not len(hits):
            found.append(None)
            continue
        i = int(hits[0])
        found.append(float(t[i]) if b[i] == a[i] else float(t[i] + (t[i + 1] - t[i]) * (level - a[i]) / (b[i] - a[i])))
    return found


def rising_limb_review(t, v, crest, t30, t90, peak, *, tolerance_kv=None, stall_check=True):
    """Check that the analyzer's 30/90 % crossings describe one connected rising limb.

    Returns (metrics, issues, notes). Nothing is substituted: the analyzer's
    first-crossing metrics stay the reported values; a connected-limb front is
    reported only as a diagnostic so the reviewer can see what is at stake.
    """
    metrics, issues, notes = {}, [], []
    level30 = crest * .3
    roundoff = max(crest * RISING_CONNECTION_RTOL, RISING_CONNECTION_ATOL_KV)
    start = first_rising_crossings(t, v, crest, (.1,), peak)[0]
    pre = v[t < start] if start is not None else v[:0]
    pre = pre[:int(len(pre) * .9)]  # guard band before the rise
    noise = None
    if len(pre) >= MIN_PRETRIGGER_SAMPLES:
        d = np.diff(pre)
        noise = float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))
    tolerance = max(roundoff, NOISE_MULTIPLE * noise) if noise is not None else roundoff
    if tolerance_kv is not None:
        # A caller with a stated sample uncertainty (e.g. digitized pixels) supplies it.
        tolerance = max(roundoff, float(tolerance_kv))
    metrics.update(pre_trigger_samples=int(len(pre)), pre_trigger_noise_kv=noise,
                   recrossing_tolerance_kv=tolerance,
                   recrossing_tolerance_basis=('stated sample uncertainty' if tolerance_kv is not None else
                                               f'{NOISE_MULTIPLE:g} x pre-trigger noise' if noise is not None and tolerance > roundoff
                                               else 'floating-point roundoff only (no pre-trigger record to estimate noise)'
                                               if noise is None else 'floating-point roundoff (no pre-trigger noise detected)'))
    t_peak = float(t[peak])
    # The boundary levels are interpolated crossings; only acquired interior
    # samples can establish a return below 30 %.
    inside = (t > t30) & (t < t_peak)
    below = inside & (v < level30 - tolerance)
    returns = np.flatnonzero(below)
    connected = not len(returns)
    metrics.update(rising_30_level_kv=level30, rising_connection_tolerance_kv=tolerance,
                   rising_window_minimum_kv=float(min(level30, np.min(v[inside], initial=np.inf))),
                   rising_below_30_interior_samples=int(len(returns)), rising_limb_connected=connected)
    if not connected:
        metrics['rising_below_30_time_range_us'] = [float(t[returns[0]]), float(t[returns[-1]])]
        # Diagnostic only: the limb that finally reaches the crest.
        last = int(returns[-1])
        try:
            seg_t, seg_v = t[last:peak + 1], v[last:peak + 1]
            a = first_rising_crossings(seg_t, seg_v, crest, (.3, .9), len(seg_t) - 1)
            if None not in a:
                metrics['connected_limb_t30_us'], metrics['connected_limb_t90_us'] = a
                metrics['connected_limb_front_us'] = 1.67 * (a[1] - a[0])
        except (IndexError, ValueError):
            pass
        issues.append({'code': 'disconnected_rising_limb', 'reviewable': False, 'message':
            'The recorded waveform returns below 30% of crest after the first rising 30% crossing and before the crest. '
            'The analyzer\'s first 30% and 90% crossings therefore belong to different rising events (for example a '
            'precursor and the main front), so the reported front is not the front of one impulse. '
            + (f"The connected main limb alone would give a front of {metrics['connected_limb_front_us']:.3g} µs; "
               if 'connected_limb_front_us' in metrics else '')
            + 'it is shown for review only and is not substituted. Review the precursor or recrossing before calibration '
              'or accuracy evaluation.'})
    # Crossing-time rate profile (two-stage rise, connected or not).
    times = first_rising_crossings(t, v, crest, STALL_LEVELS, peak)
    pairs = [(STALL_LEVELS[k], STALL_LEVELS[k + 1], times[k], times[k + 1]) for k in range(len(times) - 1)
             if times[k] is not None and times[k + 1] is not None]
    rates = [((b - a) * crest) / (tb - ta) if tb > ta else np.inf for a, b, ta, tb in pairs]
    stalls = []
    for k in range(1, len(rates) - 1 if stall_check else 1):
        before, after = max(rates[:k]), max(rates[k + 1:])
        if rates[k] * STALL_RATE_FACTOR < before and rates[k] * STALL_RATE_FACTOR < after:
            stalls.append(k)
    metrics['rise_rate_levels_pct'] = [round(100 * p[0]) for p in pairs]
    metrics['rise_rate_kv_per_us'] = [None if not np.isfinite(r) else float(r) for r in rates]
    metrics['rise_stall_factor'] = STALL_RATE_FACTOR
    if stalls:
        worst = min(stalls, key=lambda k: rates[k])
        lo, hi, ta, tb = pairs[worst]
        metrics.update(rise_stall_levels_pct=[round(100 * lo), round(100 * hi)], rise_stall_duration_us=float(tb - ta),
                       rise_stall_time_us=[float(ta), float(tb)])
        affects = any(pairs[k][1] > .3 + 1e-9 for k in stalls)
        if affects and connected:
            issues.append({'code': 'two_stage_rise', 'reviewable': True, 'message':
                f'The rise stalls between {round(100 * lo)}% and {round(100 * hi)}% of crest for {tb - ta:.3g} µs and then '
                'accelerates again (rise rate more than 3× lower than before and after). A precursor, shelf or front '
                'oscillation can move the 30% crossing and change the reported front. A qualified reviewer must accept '
                'or exclude this capture before calibration or accuracy evaluation.'})
        elif not affects:
            notes.append({'code': 'precursor_below_30_percent', 'message':
                f'A stall below 30% of crest ({round(100 * lo)}–{round(100 * hi)}%) suggests a small precursor. It does '
                'not move the 30% or 90% crossings, so the extracted metrics are unaffected.'})
    # After the first 90 % crossing the signal should not fall back below 90 % before the crest.
    level90 = crest * .9
    after90 = (t > t90) & (t < t_peak) & (v < level90 - tolerance)
    if np.any(after90) and connected:
        dip = float(np.min(v[after90]))
        metrics['dip_after_90_minimum_pct'] = 100 * dip / crest
        issues.append({'code': 'dip_after_90_percent', 'reviewable': True, 'message':
            f'After first reaching 90% of crest the waveform falls back to {100 * dip / crest:.1f}% before its maximum. '
            'The crest may be an oscillation peak rather than the impulse crest; no test-voltage curve is fitted here. '
            'A qualified reviewer must accept or exclude this capture.'})
    return metrics, issues, notes


def assess_waveform(time_us, voltage_kv, measured, *, impulse_type=None, rules=None, expected_polarity=None):
    issues = []
    notes = []
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
        limb_metrics, limb_issues, limb_notes = rising_limb_review(t, v, crest, t30, t90, peak)
        metrics.update(limb_metrics)
        issues.extend(limb_issues)
        notes.extend(limb_notes)
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
    # The operator's declared polarity is part of the capture record. A mismatch
    # blocks every use; the waveform is never flipped to hide it.
    if expected_polarity not in (None, 'auto'):
        detected = {1: 'positive', -1: 'negative'}.get(_polarity(measured))
        metrics['expected_polarity'] = expected_polarity
        metrics['detected_polarity'] = detected
        if expected_polarity not in ('positive', 'negative'):
            issues.append({'code': 'polarity_declaration_invalid', 'message':
                'The recorded expected polarity is not positive, negative or auto.'})
        elif detected != expected_polarity:
            issues.append({'code': 'polarity_mismatch', 'message':
                f'The capture is {detected or "of unknown polarity"} but the operator expected {expected_polarity}. '
                'Check divider polarity and channel wiring; the waveform was not flipped to hide this. '
                'It cannot be used for calibration, parameter fitting or accuracy evaluation.'})
    for issue in issues:
        issue.setdefault('reviewable', issue['code'] in REVIEWABLE)
    allowed = not issues
    return {'version': VERSION, 'status': 'usable' if allowed else 'review_required',
            'calibration_allowed': allowed, 'evaluation_allowed': allowed, 'issues': issues, 'notes': notes,
            'metrics': metrics,
            'scope': 'Acquisition heuristics only, not IEC certification or an instrument uncertainty estimate. '
                     'Peak-neighbor and falling half-value bracket spans must not exceed 25% of their '
                     'selected challenge timing tolerance half-widths. These limits are application review '
                     'preferences, not waveform error bounds. At least four acquired intervals and '
                     '2% of the extracted tail duration must remain beyond the falling half-value '
                     'crossing; this is a capture-completeness heuristic, not waveform classification. '
                     'The rising 30% crossing must stay connected to the crest (no acquired return below 30% by more than '
                     '4× the pre-trigger noise estimated from samples before 10% of crest, or roundoff when there is no '
                     'pre-trigger record). A rise whose rate between '
                     '20% and 90% stalls to less than a third of the rate before and after it, or a fall below 90% '
                     'after first reaching it, requires a recorded review. A declared polarity must match. '
                     'No resampling, smoothing or changes to raw '
                     'samples or extracted metrics. Passing does not establish laboratory accuracy.'}
