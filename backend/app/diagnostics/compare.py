"""Quantitative comparison of a recorded waveform with the circuit prediction.

Uses the existing metric definitions, re-extracted from the samples that are
plotted. Any time alignment is explicit, recorded and shown; nothing is
stretched, normalized or extrapolated to hide a mismatch.
"""
import numpy as np

from ..physics.waveform_metrics import analyze
from .digitize import analyse_samples

VERSION = 'waveform-comparison-v1'
REGION_POLICY = ('Region-balanced weighting: the rise (onset to 90% of crest), the crest region (90% before to 80% '
                 'after the peak) and the tail (after that) each carry one third of the total weight, however many '
                 'samples each holds, so a long densely sampled tail cannot dominate the rise.')


def regions(t, v_pred, crest_time):
    """Region index per sample from the prediction shape: 0 rise, 1 crest, 2 tail."""
    v_pred = np.asarray(v_pred); t = np.asarray(t)
    crest = v_pred.max() if len(v_pred) else 1.
    out = np.full(len(t), 2)
    out[t <= crest_time] = 0
    near = (v_pred >= .9 * crest) & (t <= crest_time) | (v_pred >= .8 * crest) & (t > crest_time)
    out[near] = 1
    out[t < 0] = -1          # before the onset: reported (baseline) but not fitted
    return out


def balanced_weights(region):
    w = np.zeros(len(region))
    present = [r for r in (0, 1, 2) if (region == r).any()]
    for r in present:
        n = (region == r).sum()
        w[region == r] = 1. / (len(present) * n)
    return w


def mismatch(t, v_obs, sigma, v_model, region):
    """Region-balanced RMS of (model − observed)/uncertainty; 1 means 'within the stated uncertainty'."""
    w = balanced_weights(region)
    z = (np.asarray(v_model) - np.asarray(v_obs)) / np.asarray(sigma)
    total = float(np.sqrt(np.sum(w * z * z)))
    per = {name: (float(np.sqrt(np.mean(z[region == r] ** 2))) if (region == r).any() else None)
           for r, name in enumerate(('rise', 'crest', 'tail'))}
    return total, per


def oscillation(t, v, tolerance):
    """Direction changes after the peak larger than the tolerance, and the largest undershoot."""
    v = np.asarray(v); peak = int(np.argmax(v)); crest = float(v[peak])
    turns, last, acc, swing = 0, 0, 0., 0.
    after = v[peak:]
    for d in np.diff(after):
        acc += d
        if abs(acc) > tolerance:
            sign = 1 if acc > 0 else -1
            if last and sign != last:
                turns += 1
                swing = max(swing, abs(acc))
            last, acc = sign, 0.
    undershoot = float(max(0., -after.min()) / crest * 100) if crest > 0 else 0.
    return {'turns_after_peak': turns, 'largest_swing_pct': 100 * swing / crest if crest > 0 else None,
            'undershoot_pct': undershoot}


def frame(observed, baseline_kv, onset_us, polarity, shift_us):
    """Comparison frame: time from the entered onset (plus a recorded shift), positive magnitude."""
    t = np.asarray(observed['time_us'], float) - onset_us - shift_us
    v = (np.asarray(observed['voltage_kv'], float) - baseline_kv) * polarity
    return t, v


def compare(snapshot, prediction, observed, *, impulse_type, baseline_kv, onset_us, expected_polarity,
            alignment=None, excluded_ranges=(), quantitative_allowed=True, sample_sigma=None, pixel=None):
    """observed: {'time_us','voltage_kv','sigma_t_us'?,'sigma_v_kv'?}; prediction: circuit waveform dict."""
    alignment = dict(alignment or {'basis': 'none', 'time_shift_us': 0.})
    t_raw = np.asarray(observed['time_us'], float); v_raw = np.asarray(observed['voltage_kv'], float)
    centred = v_raw - baseline_kv
    detected = 1 if abs(centred.max()) >= abs(centred.min()) else -1
    polarity_issue = None
    if expected_polarity in ('positive', 'negative') and {'positive': 1, 'negative': -1}[expected_polarity] != detected:
        polarity_issue = {'code': 'polarity_mismatch', 'message': f"The recording is {'positive' if detected > 0 else 'negative'} "
                          f'but {expected_polarity} was expected. The comparison uses its magnitude and flags this; the '
                          'recording is not flipped in storage.'}
    pt = np.asarray(prediction['time_us'], float); pv = np.asarray(prediction['voltage_kv'], float)
    shift = 0.
    if alignment.get('basis') == 'manual':
        shift = float(alignment.get('time_shift_us') or 0.)
        if not np.isfinite(shift) or abs(shift) > .5 * (pt[-1] - pt[0]):
            raise ValueError('The time shift must be finite and smaller than half the predicted record.')
    elif alignment.get('basis') == 'match_30_percent':
        t0, v0 = frame(observed, baseline_kv, onset_us, detected, 0.)
        try:
            mo = analyse_samples(t0, v0, impulse_type, 0., 0., None)
            obs30 = (mo['metrics'] or mo.get('partial') or {})['t30_us']
            pred30 = analyze(pt, pv, impulse_type, 0., 0.)['t30_us']
            shift = float(obs30 - pred30)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('The 30% crossings needed for this alignment are not available.') from error
    elif alignment.get('basis') not in ('none', None):
        raise ValueError('Alignment must be none, manual or match_30_percent.')
    alignment = {'basis': alignment.get('basis') or 'none', 'time_shift_us': shift,
                 'note': 'Observed time = recorded time − entered onset − this shift. No stretching or rescaling.'}
    t, v = frame(observed, baseline_kv, onset_us, detected, shift)
    # Residuals are normalized by the per-sample (independent) uncertainty; anchor placement is a
    # common-mode error handled by the measurement hypotheses (time offset, gain).
    sv = observed.get('independent_sigma_v_kv', observed.get('sigma_v_kv'))
    st = observed.get('independent_sigma_t_us', observed.get('sigma_t_us'))
    sigma_v = np.asarray(sv if sv is not None else np.full(len(t), sample_sigma if sample_sigma else max(1e-3, .002 * np.abs(v).max())), float)
    sigma_t = np.asarray(st if st is not None else np.zeros(len(t)), float)
    # Metrics, re-extracted from exactly the plotted samples (comparison frame).
    obs_an = analyse_samples(t, v, impulse_type, 0., 0., None,
                             sample_sigma_kv=None if pixel is None else float(np.median(sigma_v)),
                             us_per_px=None if pixel is None else pixel['us_per_px'],
                             thickness_px=None if pixel is None else pixel['thickness_px'])
    pred_m = analyze(pt, pv, impulse_type, 0., 0.)
    obs_m = obs_an['metrics'] or obs_an.get('partial') or {}
    labels = {'crest_kv': ('Crest voltage', 'kV'), 'front_us': ('Front time' if impulse_type == 'Lightning' else 'Time to peak', 'µs'),
              'tail_us': ('Time to half-value', 'µs')}
    plausibility = []
    for key in ('front_us', 'tail_us'):
        if obs_m.get(key) and pred_m.get(key):
            ratio = obs_m[key] / pred_m[key]
            if ratio > 20 or ratio < 1 / 20:
                plausibility.append({'code': 'implausible_time_scale', 'message': f'The recorded {labels[key][0].lower()} is '
                                     f'{ratio:.3g}× the prediction. Check the time unit and axis values first: a unit mistake looks '
                                     'like a huge mismatch. If the units are right, the recording is far from the predicted '
                                     'impulse (for example strong ringing reaches half value on its first swing) and a '
                                     'quantitative diagnosis is not attempted.'})
    if obs_m.get('crest_kv') and pred_m.get('crest_kv'):
        ratio = obs_m['crest_kv'] / pred_m['crest_kv']
        if ratio > 5 or ratio < .2:
            plausibility.append({'code': 'implausible_voltage_scale', 'message': f'The recorded crest is {ratio:.3g}× the '
                                 'prediction. Check the voltage unit, the divider ratio and whether it was applied twice.'})
    if plausibility:
        quantitative_allowed = False
    review_codes = {i['code'] for i in obs_an['issues']} & {'disconnected_rising_limb', 'two_stage_rise', 'dip_after_90_percent', 'polarity_mismatch'}
    rows = []
    avail = obs_an['available']
    for key, gate in (('crest_kv', 'crest'), ('front_us', 'front'), ('tail_us', 'tail')):
        label, unit = labels[key]
        row = {'metric': key, 'label': label, 'unit': unit, 'predicted': pred_m[key]}
        if not avail.get(gate) or key not in obs_m:
            row.update(status='Insufficient capture', observed=None,
                       reason={'crest': 'No resolved crest in the recording.', 'front': 'The rise is not captured or not resolved.',
                               'tail': 'The recording does not fall to half value; the tail is not extrapolated.'}[gate])
        elif review_codes and key in ('front_us', 'tail_us') or polarity_issue:
            row.update(status='Requires review', observed=obs_m[key], difference=obs_m[key] - pred_m[key],
                       difference_pct=100 * (obs_m[key] / pred_m[key] - 1),
                       reason='A review flag on the recording affects this metric: ' + ', '.join(sorted(review_codes | ({'polarity_mismatch'} if polarity_issue else set()))))
        elif not quantitative_allowed:
            row.update(status='Approximate', observed=obs_m[key], difference=obs_m[key] - pred_m[key],
                       difference_pct=100 * (obs_m[key] / pred_m[key] - 1),
                       reason='Visual comparison only: the digitization does not support a quantitative diagnosis.')
        else:
            row.update(status='Compared', observed=obs_m[key], difference=obs_m[key] - pred_m[key],
                       difference_pct=100 * (obs_m[key] / pred_m[key] - 1))
        rows.append(row)
    # Whole-waveform residual on observed times inside the predicted record; never extrapolated.
    inside = (t >= 0) & (t <= pt[-1])
    for a, b in excluded_ranges or ():
        inside &= ~((t >= min(a, b)) & (t <= max(a, b)))
    model_at_obs = np.interp(t, pt, pv)
    slope = np.gradient(pv, pt) if len(pt) > 2 else np.zeros(len(pt))
    sigma = np.sqrt(sigma_v ** 2 + (np.interp(t, pt, slope) * sigma_t) ** 2)
    sigma = np.maximum(sigma, 1e-9 + 1e-6 * np.abs(pv).max())
    region = regions(t, model_at_obs, pred_m['peak_time_us'])
    residual = v - model_at_obs
    whole = {}
    if inside.sum() >= 10:
        total, per = mismatch(t[inside], v[inside], sigma[inside], model_at_obs[inside], region[inside])
        whole = {'normalized_mismatch': total, 'normalized_by_region': per,
                 'rms_kv': float(np.sqrt(np.mean(residual[inside] ** 2))),
                 'rms_pct_of_predicted_crest': float(100 * np.sqrt(np.mean(residual[inside] ** 2)) / pred_m['crest_kv']),
                 'max_abs_kv': float(np.max(np.abs(residual[inside]))), 'samples_compared': int(inside.sum()),
                 'weighting': REGION_POLICY,
                 'meaning': 'Normalized mismatch is the region-balanced RMS of the difference divided by the stated sample '
                            'uncertainty: about 1 means the curves agree within that uncertainty.'}
    beyond = float(max(0., t[-1] - pt[-1])) if len(t) else 0.
    pre = v[t < 0]
    baseline = {'pre_onset_samples': int(len(pre)),
                'pre_onset_mean_pct': float(100 * pre.mean() / pred_m['crest_kv']) if len(pre) else None}
    tol = max(3 * float(np.median(sigma_v)), .01 * float(np.abs(v).max()))
    shape = {'observed': oscillation(t, v, tol), 'predicted': oscillation(pt, pv, tol)}
    normalized = {'label': 'Normalized shape — each curve divided by its own crest. This view hides any crest mismatch.',
                  'observed': {'time_us': t.tolist(), 'value': (v / max(v.max(), 1e-12)).tolist()},
                  'predicted': {'time_us': pt.tolist(), 'value': (pv / max(pv.max(), 1e-12)).tolist()}}
    return {'version': VERSION, 'alignment': alignment, 'impulse_type': impulse_type,
            'observed': {'label': 'Uploaded waveform', 'time_us': t.tolist(), 'voltage_kv': v.tolist(),
                         'sigma_kv': sigma.tolist(), 'region': region.tolist(), 'admitted': inside.tolist(),
                         'detected_polarity': 'positive' if detected > 0 else 'negative',
                         'transform': {'baseline_kv': baseline_kv, 'onset_us': onset_us, 'polarity_applied': detected,
                                       'time_shift_us': shift}},
            'residual': {'time_us': t[inside].tolist(), 'kv': residual[inside].tolist(),
                         'label': 'Uploaded minus prediction (only where both exist)'},
            'metrics': rows, 'observed_metrics': obs_m, 'predicted_metrics': {k: pred_m[k] for k in ('front_us', 'tail_us', 'crest_kv', 'peak_time_us', 't30_us', 't90_us', 't50_us')},
            'observed_analysis': {k: obs_an[k] for k in ('issues', 'notes', 'available')},
            'whole_waveform': whole, 'baseline': baseline, 'oscillation': shape,
            'polarity_issue': polarity_issue, 'beyond_prediction_us': beyond, 'plausibility': plausibility, 'excluded_ranges_us': [list(map(float, r)) for r in (excluded_ranges or ())],
            'normalized_view': normalized, 'quantitative_allowed': bool(quantitative_allowed) and polarity_issue is None,
            'scope': 'Metrics use the application\'s existing definitions on the plotted samples. Differences describe this '
                     'recording against this circuit prediction; they are not laboratory accuracy.'}
