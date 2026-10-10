"""Local trace extraction from a plot image, with confirmed axis calibration.

No external AI and no fitted ideal impulse: samples are the pixels of the selected
curve, converted with the axis calibration the user confirmed. Gaps stay gaps,
manual points stay marked, and nothing is smoothed.
"""
import math

import numpy as np
from scipy import ndimage

from ..physics.waveform_metrics import analyze, crossing
from ..trial_quality import rising_limb_review
from .imaging import background_color

VERSION = 'trace-digitizer-v1'
TIME_UNITS = {'ns': 1e-3, 'us': 1., 'µs': 1., 'ms': 1e3, 's': 1e6}
VOLT_UNITS = {'V': 1e-3, 'kV': 1., 'MV': 1e3}
LINE_FRACTION = .9          # straight same-colour lines spanning this share of the plot are grid/axes
MIN_FRONT_PIXELS = 4        # the 30–90 % rise must span at least this many pixel columns
MC_DRAWS = 60               # digitization-spread draws


# ---------------------------------------------------------------- calibration

def calibration(axes):
    """Validate a confirmed axis calibration and return linear pixel→value maps."""
    if not isinstance(axes, dict):
        raise ValueError('Confirm the axis calibration first.')
    for axis in ('x_scale', 'y_scale'):
        if axes.get(axis, 'linear') != 'linear':
            raise ValueError('Logarithmic axes are not supported for digitization in this version. Only linear time '
                             'and voltage axes can be converted to samples; use the raw CSV export instead.')
    if axes.get('time_unit') not in TIME_UNITS or axes.get('voltage_unit') not in VOLT_UNITS:
        raise ValueError('Choose the time unit (ns, µs, ms, s) and voltage unit (V, kV, MV) printed on the axes.')
    side = axes.get('voltage_side')
    ratio = float(axes.get('divider_ratio') or 1.)
    if side not in ('high_voltage', 'instrument'):
        raise ValueError('Say whether the voltage axis shows the high voltage at the test object or the instrument '
                         '(divider output) signal.')
    if not (math.isfinite(ratio) and ratio > 0):
        raise ValueError('The divider ratio must be a positive number.')
    if side == 'high_voltage' and ratio != 1:
        raise ValueError('The voltage axis already shows high voltage. Applying a divider ratio as well would count '
                         'the divider twice; set the ratio to 1 or choose "instrument signal".')
    if side == 'instrument' and ratio != 1 and not str(axes.get('divider_ratio_source') or '').strip():
        raise ValueError('Give the source of the divider ratio (for example the divider certificate).')
    mode = axes.get('mode', 'anchors')
    if mode == 'per_division':
        g = axes.get('grid') or {}
        try:
            left, right, top, bottom = (float(g[k]) for k in ('left_px', 'right_px', 'top_px', 'bottom_px'))
            nx, ny = int(g.get('divisions_x', 10)), int(g.get('divisions_y', 8))
            tdiv, vdiv = float(g['time_per_div']), float(g['volts_per_div'])
            t0, v0 = float(g.get('time_at_left', 0.)), float(g.get('value_at_center', 0.))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Per-division calibration needs the graticule edges, divisions, time/div and volts/div.') from error
        if not (right - left > 40 and bottom - top > 40 and nx > 0 and ny > 0 and tdiv > 0 and vdiv > 0):
            raise ValueError('The graticule must be at least 40 px each way, with positive divisions and scales.')
        xa = [{'px': left, 'value': t0}, {'px': right, 'value': t0 + nx * tdiv}]
        ya = [{'px': (top + bottom) / 2, 'value': v0}, {'px': top, 'value': v0 + ny / 2 * vdiv}]
    elif mode == 'anchors':
        xa, ya = axes.get('x_anchors') or [], axes.get('y_anchors') or []
    else:
        raise ValueError('Calibration mode must be anchors or per_division.')
    if len(xa) != 2 or len(ya) != 2:
        raise ValueError('Give two time anchors and two voltage anchors (pixel position and axis value).')
    try:
        (x1, t1), (x2, t2) = [(float(a['px']), float(a['value'])) for a in xa]
        (y1, v1), (y2, v2) = [(float(a['px']), float(a['value'])) for a in ya]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Anchors need a pixel position and an axis value.') from error
    if not np.isfinite([x1, x2, t1, t2, y1, y2, v1, v2]).all():
        raise ValueError('Anchor values must be finite.')
    if abs(x2 - x1) < 20 or abs(y2 - y1) < 20:
        raise ValueError('Place each pair of anchors at least 20 px apart.')
    if t1 == t2 or v1 == v2:
        raise ValueError('Each pair of anchors needs two different axis values.')
    unc = float(axes.get('anchor_uncertainty_px', 1.))
    if not (0 <= unc <= 20):
        raise ValueError('Anchor uncertainty must be 0–20 px.')
    ts, vs = TIME_UNITS[axes['time_unit']], VOLT_UNITS[axes['voltage_unit']] * (ratio if side == 'instrument' else 1.)
    return {'x': (x1, t1 * ts, x2, t2 * ts), 'y': (y1, v1 * vs, y2, v2 * vs), 'anchor_uncertainty_px': unc,
            'us_per_px': abs((t2 - t1) * ts / (x2 - x1)), 'kv_per_px': abs((v2 - v1) * vs / (y2 - y1)),
            'time_direction': 'left_to_right' if (t2 - t1) / (x2 - x1) > 0 else 'right_to_left',
            'voltage_direction': 'up' if (v2 - v1) / (y2 - y1) < 0 else 'down',
            'voltage_scale_applied': ratio if side == 'instrument' else 1., 'voltage_side': side, 'mode': mode,
            'x_anchors': xa, 'y_anchors': ya}


def to_physical(cal, xs, ys):
    x1, t1, x2, t2 = cal['x']; y1, v1, y2, v2 = cal['y']
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    return t1 + (xs - x1) * (t2 - t1) / (x2 - x1), v1 + (ys - y1) * (v2 - v1) / (y2 - y1)


def to_pixels(cal, ts, vs):
    x1, t1, x2, t2 = cal['x']; y1, v1, y2, v2 = cal['y']
    return x1 + (np.asarray(ts) - t1) * (x2 - x1) / (t2 - t1), y1 + (np.asarray(vs) - v1) * (y2 - y1) / (v2 - v1)


# ---------------------------------------------------------------- colour

def _lab(rgb):
    c = np.asarray(rgb, float) / 255.
    c = np.where(c > .04045, ((c + .055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]]).T
    xyz = xyz / np.array([.95047, 1., 1.08883])
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def trace_colour(rgb, seed, radius=4):
    """Colour of the curve under the user's click (the nearest non-background pixels)."""
    h, w = rgb.shape[:2]
    x, y = int(round(seed[0])), int(round(seed[1]))
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError('The trace selection point is outside the working image.')
    bg = _lab(background_color(rgb)[None, :])[0]
    for r in (radius, radius * 2, radius * 4):
        x0, x1, y0, y1 = max(0, x - r), min(w, x + r + 1), max(0, y - r), min(h, y + r + 1)
        patch = rgb[y0:y1, x0:x1].reshape(-1, 3)
        lab = _lab(patch)
        far = np.linalg.norm(lab - bg, axis=1)
        if (far > 25).sum() >= 2:
            chosen = patch[far >= np.percentile(far[far > 25], 50)] if (far > 25).sum() > 4 else patch[far > 25]
            return np.median(chosen, axis=0)
    raise ValueError('No curve was found near the selected point. Click directly on the waveform line.')


# ---------------------------------------------------------------- extraction

def _runs(column):
    idx = np.flatnonzero(column)
    if not len(idx):
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[breaks + 1]]
    ends = np.r_[idx[breaks], idx[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def extract(rgb, seed, *, plot_box=None, tolerance=28., edits=None):
    """Continuity-aware extraction of one curve.

    Returns pixel samples (working-image coordinates, pixel centres) with their
    pixel uncertainties, and records every judgement made along the way.
    """
    h, w = rgb.shape[:2]
    box = plot_box or [0, 0, w, h]
    bx0, by0, bx1, by1 = [int(round(v)) for v in box]
    bx0, by0, bx1, by1 = max(0, bx0), max(0, by0), min(w, bx1), min(h, by1)
    if bx1 - bx0 < 40 or by1 - by0 < 40:
        raise ValueError('The plot area must be at least 40×40 px.')
    colour = trace_colour(rgb, seed)
    if not 5 <= float(tolerance) <= 80:
        raise ValueError('Colour tolerance must be between 5 and 80 (CIE ΔE).')
    # Colour distance only inside the plot area, in float32, to bound memory on large images.
    target = _lab(colour[None, :])[0].astype(np.float32)
    mask = np.zeros((h, w), bool)
    for r0 in range(by0, by1, 256):
        r1 = min(by1, r0 + 256)
        block = _lab(rgb[r0:r1, bx0:bx1].astype(np.float32)).astype(np.float32)
        mask[r0:r1, bx0:bx1] = np.linalg.norm(block - target, axis=-1) <= tolerance
    flags, notes = [], []
    # Straight same-colour lines spanning most of the plot are grid or axis lines.
    removed_rows = [int(r) for r in range(by0, by1) if mask[r, bx0:bx1].sum() > LINE_FRACTION * (bx1 - bx0)]
    removed_cols = [int(c) for c in range(bx0, bx1) if mask[by0:by1, c].sum() > LINE_FRACTION * (by1 - by0)]
    for r in removed_rows:
        mask[r, :] = False
    for c in removed_cols:
        mask[:, c] = False
    if removed_rows or removed_cols:
        notes.append({'code': 'lines_removed', 'message': f'{len(removed_rows)} horizontal and {len(removed_cols)} vertical '
                      'straight lines in the trace colour span most of the plot and were treated as grid/axis lines. '
                      'Trace samples on those pixel rows or columns are missing, not interpolated.'})
    # Connected pieces: the one at the click is the curve; others are counted, not used.
    labels, count = ndimage.label(ndimage.binary_dilation(mask, iterations=1), structure=np.ones((3, 3)))
    sx, sy = int(round(seed[0])), int(round(seed[1]))
    window = labels[max(0, sy - 8):sy + 9, max(0, sx - 8):sx + 9]
    near = window[window > 0]
    if not len(near):
        raise ValueError('The selected colour is not present at the clicked point inside the plot area.')
    main = int(np.bincount(near).argmax())
    sizes = ndimage.sum(mask, labels, index=np.arange(1, count + 1)) if count else []
    # Column tracking from the click, outwards, on the full mask.
    thickness_samples = []
    for c in range(max(bx0, sx - 3), min(bx1, sx + 4)):
        for a, b in _runs(mask[:, c]):
            if labels[a, c] == main and b - a + 1 <= 12:
                thickness_samples.append(b - a + 1)
    thickness = float(np.median(thickness_samples)) if thickness_samples else 2.
    max_jump = max(6., .03 * (by1 - by0), 2 * thickness)
    max_gap = max(3, int(.05 * (bx1 - bx0)))
    tracked = {}
    ambiguous_cols = []

    def walk(direction):
        ref = None
        slope = 0.
        gap = 0
        c = sx
        while bx0 <= c < bx1:
            runs = _runs(mask[:, c])
            if ref is None:
                choices = sorted(runs, key=lambda r: 0 if r[0] <= sy <= r[1] else min(abs(r[0] - sy), abs(r[1] - sy)))
                if not choices or min(abs(choices[0][0] - sy), abs(choices[0][1] - sy)) > max_jump and not choices[0][0] <= sy <= choices[0][1]:
                    return
                pick = choices[0]
            else:
                predicted = (ref[0] + ref[1]) / 2 + slope * (gap + 1)
                allowed = max_jump * (1 + gap)

                def dist(r):
                    if r[0] - 1 <= ref[1] and r[1] + 1 >= ref[0]:
                        return 0.
                    return min(abs(r[0] - ref[1]), abs(r[1] - ref[0]), abs((r[0] + r[1]) / 2 - predicted))
                candidates = [r for r in runs if dist(r) <= allowed]
                if not candidates:
                    gap += 1
                    if gap > max_gap:
                        return
                    c += direction
                    continue
                candidates.sort(key=lambda r: (dist(r), abs((r[0] + r[1]) / 2 - predicted)))
                if len(candidates) > 1 and dist(candidates[1]) == dist(candidates[0]) == 0:
                    ambiguous_cols.append(c)
                pick = candidates[0]
                centre_prev = (ref[0] + ref[1]) / 2
                slope = ((pick[0] + pick[1]) / 2 - centre_prev) / (gap + 1)
            tracked[c] = pick
            ref, gap = pick, 0
            c += direction
    walk(1)
    walk(-1)
    if not tracked:
        raise ValueError('No continuous curve could be followed from the selected point.')
    cols = np.array(sorted(tracked))
    used = set(np.unique(labels[[tracked[c][0] for c in cols], cols]).tolist()) - {0}
    others = [int(i + 1) for i, s in enumerate(sizes) if (i + 1) not in used and s >= 3]
    if others:
        notes.append({'code': 'other_objects_ignored', 'message': f'{len(others)} other objects in the trace colour '
                      '(text, legend marks or other curves) were not part of the followed curve and were ignored.'})
    # One sample per tracked column at the column centre. Where the curve is steep the column's
    # run spans many rows: the sample sits at the middle of that span and carries half the span as
    # voltage uncertainty, so a near-vertical front is never given false time detail.
    samples = []          # (x, y, sigma_x_px, sigma_y_px, kind)
    steep = {c for c in cols if tracked[c][1] - tracked[c][0] + 1 > 2.5 * thickness}
    for c in cols.tolist():
        a, b = tracked[c]
        kind = 'observed_span' if c in steep else 'observed'
        samples.append((c + .5, (a + b) / 2 + .5, .5 / math.sqrt(3), max(.5, (b - a + 1) / 2), kind))
    edits = edits or {}
    removed = 0
    for zone in edits.get('erase', []):
        x0, y0, x1, y1 = [float(v) for v in zone]
        keep = [s for s in samples if not (min(x0, x1) <= s[0] <= max(x0, x1) and min(y0, y1) <= s[1] <= max(y0, y1))]
        removed += len(samples) - len(keep)
        samples = keep
    for point in edits.get('add', []):
        samples.append((float(point[0]), float(point[1]), 1., 1., 'manual'))
    if not samples:
        raise ValueError('Every trace sample was removed.')
    samples.sort(key=lambda s: s[0])
    tops = [tracked[c][0] for c in cols]
    bottoms = [tracked[c][1] for c in cols]
    touch_top = int(sum(t <= by0 + 1 for t in tops))
    touch_bottom = int(sum(b >= by1 - 2 for b in bottoms))
    if touch_top >= 3 or touch_bottom >= 3:
        flags.append({'code': 'clipping', 'message': 'The trace runs along the edge of the plot area for '
                      f'{max(touch_top, touch_bottom)} columns. The waveform may be clipped by the display; values there '
                      'are not real extremes.'})
    if ambiguous_cols:
        flags.append({'code': 'ambiguous_selection', 'message': f'Two branches of the same colour touched in {len(ambiguous_cols)} '
                      'columns; the branch continuing the selected curve was kept. Check the overlay there.',
                      'columns': [int(ambiguous_cols[0]), int(ambiguous_cols[-1])]})
    if thickness > 6:
        flags.append({'code': 'thick_trace', 'message': f'The trace is about {thickness:.0f} px thick; each sample carries '
                      'half that thickness as uncertainty.'})
    span = cols[-1] - cols[0] + 1
    covered = len(cols)
    multi = sum(1 for c in cols if sum(1 for a, b in _runs(mask[by0:by1, c]) if b - a >= 1) >= 2)
    if multi > .2 * len(cols):
        flags.append({'code': 'multiple_same_colour_curves', 'message': f'{multi} of {len(cols)} columns hold more than one '
                      'stroke of the selected colour. Where the curves overlap they cannot be told apart; check the overlay '
                      'and erase the other curve, or use a capture with one curve per colour.'})
    for side, edge, at in (('start', bx0, cols[0]), ('end', bx1 - 1, cols[-1])):
        if abs(at - edge) > .05 * (bx1 - bx0):
            probe = rgb[by0:by1, max(bx0, at - 3 if side == 'start' else at):min(bx1, at + 1 if side == 'start' else at + 4)]
            bg = _lab(background_color(rgb)[None, :])[0]
            other = (np.linalg.norm(_lab(probe.reshape(-1, 3)) - bg, axis=1) > 25).sum() > 0
            flags.append({'code': 'trace_ends_early', 'side': side, 'message':
                          f'The curve could not be followed to the {side} of the plot area' +
                          (' — another curve or object covers it there.' if other else '.') +
                          ' That part is missing; it is not interpolated or extrapolated.'})
    gaps = []
    for a, b in zip(cols[:-1], cols[1:]):
        if b - a > 1:
            gaps.append([int(a), int(b)])
    return {'samples': samples, 'colour_rgb': [float(v) for v in colour], 'tolerance': float(tolerance),
            'thickness_px': thickness, 'plot_box': [bx0, by0, bx1, by1], 'columns': [int(cols[0]), int(cols[-1])],
            'column_coverage': covered / max(1, span), 'gaps_px': gaps, 'removed_by_edit': removed,
            'manual_points': len(edits.get('add', [])), 'flags': flags, 'notes': notes,
            'steep_columns': len(steep), 'max_jump_px': max_jump}


# ---------------------------------------------------------------- physical samples and quality

def physical_samples(cal, extraction):
    """Convert pixel samples to (µs, kV) with propagated uncertainty. Equal-time samples keep only
    the one continuing the curve, so time stays strictly increasing (recorded)."""
    s = extraction['samples']
    xs = np.array([p[0] for p in s]); ys = np.array([p[1] for p in s])
    sxp = np.array([p[2] for p in s]); syp = np.array([p[3] for p in s])
    kinds = [p[4] for p in s]
    t, v = to_physical(cal, xs, ys)
    x1, _, x2, _ = cal['x']; y1, _, y2, _ = cal['y']
    a = cal['anchor_uncertainty_px']
    # Anchor uncertainty propagates with distance from each anchor (linear map).
    fx = np.sqrt(((x2 - xs) / (x2 - x1)) ** 2 + ((xs - x1) / (x2 - x1)) ** 2)
    fy = np.sqrt(((y2 - ys) / (y2 - y1)) ** 2 + ((ys - y1) / (y2 - y1)) ** 2)
    sigma_t = cal['us_per_px'] * np.sqrt(sxp ** 2 + (a * fx) ** 2)
    sigma_v = cal['kv_per_px'] * np.sqrt(syp ** 2 + (a * fy) ** 2)
    # Per-sample part only (pixel quantization and trace thickness). Anchor placement moves all
    # samples together (an axis offset or scale) and is tested as a measurement hypothesis instead.
    ind_t = cal['us_per_px'] * sxp
    ind_v = cal['kv_per_px'] * syp
    order = np.argsort(t, kind='stable')
    t, v, sigma_t, sigma_v = t[order], v[order], sigma_t[order], sigma_v[order]
    ind_t, ind_v = ind_t[order], ind_v[order]
    kinds = [kinds[i] for i in order]
    xs, ys = xs[order], ys[order]
    keep = np.r_[True, np.diff(t) > 1e-9 * max(1., abs(t).max())]
    # Within a run of equal times keep the last (the curve's continuation).
    if not keep.all():
        idx = np.arange(len(t))
        groups = np.cumsum(keep) - 1
        last = np.zeros(groups.max() + 1, int)
        last[groups] = idx
        sel = np.zeros(len(t), bool); sel[last] = True
        dropped = int((~sel).sum())
    else:
        sel = keep; dropped = 0
    return {'time_us': t[sel].tolist(), 'voltage_kv': v[sel].tolist(), 'sigma_t_us': sigma_t[sel].tolist(),
            'sigma_v_kv': sigma_v[sel].tolist(), 'independent_sigma_t_us': ind_t[sel].tolist(),
            'independent_sigma_v_kv': ind_v[sel].tolist(), 'kind': [kinds[i] for i in np.flatnonzero(sel)],
            'pixel_x': xs[sel].tolist(), 'pixel_y': ys[sel].tolist(), 'equal_time_samples_dropped': dropped}


def analyse_samples(t, v, impulse_type, baseline_kv, onset_us, expected_polarity, *, sample_sigma_kv=None,
                    us_per_px=None, thickness_px=None, check_flat_crest=False):
    """Existing metric definitions on the displayed samples, with explicit capture limits.

    For digitized samples, pass the pixel scale and trace thickness: a rise narrower
    than max(4 px, 2 × thickness) is reported as unresolved, not as a value.
    """
    t, v = np.asarray(t, float), np.asarray(v, float)
    out = {'metrics': None, 'available': {'front': False, 'tail': False, 'crest': False}, 'issues': [], 'notes': []}
    if len(t) < 10:
        out['issues'].append({'code': 'too_few_samples', 'message': 'Fewer than 10 samples were extracted.'})
        return out
    centred = v - baseline_kv
    polarity = 1 if abs(centred.max()) >= abs(centred.min()) else -1
    out['detected_polarity'] = 'positive' if polarity > 0 else 'negative'
    if expected_polarity in ('positive', 'negative') and expected_polarity != out['detected_polarity']:
        out['issues'].append({'code': 'polarity_mismatch', 'message': f"The trace is {out['detected_polarity']} but "
                              f'{expected_polarity} was expected. It is not flipped to hide this.'})
    m = centred * polarity
    peak = int(np.argmax(m)); crest = float(m[peak])
    if check_flat_crest:
        # Recorded samples (not pixels): three or more equal maxima suggest a clipped recorder range.
        at_crest = np.isclose(m, crest, rtol=0, atol=max(abs(crest) * 1e-9, 1e-12))
        run_, longest = 0, 0
        for equal in at_crest:
            run_ = run_ + 1 if equal else 0
            longest = max(longest, run_)
        if longest >= 3:
            out['issues'].append({'code': 'clipping', 'message': f'{longest} consecutive samples sit exactly at the maximum. '
                                  'The recording may be clipped by the recorder range; the crest is not a real extreme.'})
    if crest <= 0 or peak in (0, len(m) - 1):
        out['issues'].append({'code': 'crest_unresolved', 'message': 'The crest is at the edge of the extracted trace; '
                              'the capture does not contain a complete crest.'})
        return out
    if m[0] > .3 * crest:
        out['issues'].append({'code': 'missing_rising_limb', 'message': 'The trace starts above 30% of crest, so the rise is '
                              'not captured. Front time: insufficient capture.'})
    after = m[peak:]
    falls = bool((after <= .5 * crest).any())
    rising_ok = bool(m[0] <= .3 * crest)
    try:
        metrics = analyze(t, v, impulse_type, baseline_kv, onset_us if impulse_type == 'Switching' else 0.)
        out['metrics'] = metrics
        out['available'] = {'front': rising_ok, 'tail': falls, 'crest': True}
    except ValueError as error:
        # Report what the capture supports, with the same crossing definition; never extrapolate a tail.
        partial = {'crest_kv': crest, 'peak_time_us': float(t[peak]), 'baseline_kv': float(baseline_kv),
                   'polarity': polarity, 'time_origin_us': float(onset_us if impulse_type == 'Switching' else 0.)}
        try:
            partial['t30_us'] = crossing(t[:peak + 1], m[:peak + 1], crest * .3)
            partial['t90_us'] = crossing(t[:peak + 1], m[:peak + 1], crest * .9)
            if impulse_type == 'Lightning':
                partial['front_us'] = 1.67 * (partial['t90_us'] - partial['t30_us'])
                partial['virtual_origin_us'] = partial['t30_us'] - .5 * (partial['t90_us'] - partial['t30_us'])
            elif t[0] <= onset_us < partial['t30_us']:
                partial['front_us'] = float(t[peak] - onset_us)
        except ValueError:
            pass
        out['partial'] = partial
        out['available'] = {'front': rising_ok and 'front_us' in partial, 'tail': False, 'crest': True}
        out['issues'].append({'code': 'metrics_incomplete', 'message': f'Not every metric can be extracted: {error}'})
    if not falls:
        out['issues'].append({'code': 'missing_falling_limb', 'message': 'The trace never falls to 50% of crest after the '
                              'peak. Tail (time to half-value): insufficient capture — it is not extrapolated.'})
    mm = out['metrics'] or out.get('partial') or {}
    resolved = True
    if us_per_px and 't30_us' in mm and 't90_us' in mm:
        rise_px = (mm['t90_us'] - mm['t30_us']) / us_per_px
        need = max(MIN_FRONT_PIXELS, 2 * (thickness_px or 0))
        out['rise_30_90_px'] = float(rise_px)
        if rise_px < need:
            resolved = False
            out['available']['front'] = False
            out['issues'].append({'code': 'front_unresolved', 'message': f'The 30–90% rise spans only {rise_px:.1f} px '
                                  f'(at least {need:.0f} px are needed for a {thickness_px or 0:.0f} px thick trace at '
                                  f'{us_per_px:.3g} µs per pixel). The front time is below what this image resolves; it is '
                                  'reported as unresolved, not as a value.'})
    if out['metrics'] and out['available']['front']:
        limb, issues, notes = rising_limb_review(
            t, m, crest, mm['t30_us'], mm['t90_us'], peak,
            tolerance_kv=None if sample_sigma_kv is None else 2 * sample_sigma_kv,
            stall_check=us_per_px is None or out.get('rise_30_90_px', 0) >= 15)
        out['rising_limb'] = limb
        out['issues'].extend(issues)
        out['notes'].extend(notes)
    return out


def quality(cal, extraction, physical, analysis, impulse_type, plot_width_px):
    """Plain quality summary; no invented confidence percentage."""
    t = np.asarray(physical['time_us']); v = np.asarray(physical['voltage_kv'])
    reasons = []
    flags = list(extraction['flags'])
    m = analysis.get('metrics') or analysis.get('partial')
    resolution = {'us_per_px': cal['us_per_px'], 'kv_per_px': cal['kv_per_px'],
                  'median_sigma_t_us': float(np.median(physical['sigma_t_us'])),
                  'median_sigma_v_kv': float(np.median(physical['sigma_v_kv']))}
    if 'rise_30_90_px' in analysis:
        resolution['rise_30_90_px'] = analysis['rise_30_90_px']
    if m:
        resolution['crest_px'] = float(m['crest_kv'] / cal['kv_per_px'])
        if resolution['crest_px'] < 50:
            flags.append({'code': 'low_voltage_resolution', 'message': f"The crest is only {resolution['crest_px']:.0f} px tall; "
                          'voltage values carry large pixel uncertainty.'})
    if plot_width_px < 300:
        flags.append({'code': 'low_resolution', 'message': f'The plot area is only {plot_width_px} px wide.'})
    gaps = []
    for a, b in extraction['gaps_px']:
        ta, _ = to_physical(cal, [a + .5], [0]); tb, _ = to_physical(cal, [b + .5], [0])
        gaps.append([float(min(ta[0], tb[0])), float(max(ta[0], tb[0]))])
    covered = extraction['column_coverage']
    # A metric crossing that falls inside a missing portion is not supported by samples.
    if m:
        for key, label in (('t30_us', '30% crossing'), ('t90_us', '90% crossing'), ('t50_us', 'half-value crossing'), ('peak_time_us', 'crest')):
            for a, b in gaps:
                if key in m and m[key] is not None and a < m[key] < b:
                    flags.append({'code': 'crossing_in_gap', 'message': f'The {label} falls inside a missing portion of the trace '
                                  f'({a:.3g}–{b:.3g} µs); it is interpolated across the gap and needs review.'})
    # Ringing: alternating extrema larger than the pixel uncertainty.
    shallow = np.array([k != 'observed_span' for k in physical['kind']])
    if shallow.sum() > 5:
        vs = v[shallow]
        dv = np.diff(vs); thresh = max(3 * resolution['median_sigma_v_kv'], .01 * float(np.max(np.abs(vs)) or 1.))
        turns = 0; last = 0; acc = 0.
        for d in dv:
            acc += d
            if abs(acc) > thresh:
                sign = 1 if acc > 0 else -1
                if last and sign != last:
                    turns += 1
                last, acc = sign, 0.
        resolution['direction_changes'] = turns
        if turns > 2:
            flags.append({'code': 'ringing', 'message': f'The trace changes direction {turns} times by more than 1% of its '
                          'largest value and three times its pixel uncertainty (steep columns are not counted): '
                          'oscillation or ringing is present.'})
    for issue in analysis['issues']:
        flags.append(issue)
    for code in ('polarity_mismatch', 'crest_unresolved', 'too_few_samples'):
        if any(f['code'] == code for f in flags):
            reasons.append(code)
    # Trace-integrity problems block a quantitative diagnosis. Waveform features such as a precursor
    # or a two-stage rise do not: they mark the affected metric "Requires review" and are part of
    # what the diagnosis has to explain.
    if any(f['code'] in ('clipping', 'multiple_same_colour_curves') for f in flags):
        reasons.append('trace_integrity')
    quantitative = m is not None and not reasons
    spread = digitization_spread(cal, physical, impulse_type, analysis) if analysis.get('metrics') else None
    return {'version': VERSION, 'calibration': {k: cal[k] for k in ('us_per_px', 'kv_per_px', 'time_direction',
                                                                    'voltage_direction', 'voltage_scale_applied',
                                                                    'voltage_side', 'mode', 'anchor_uncertainty_px')},
            'trace': {'samples': len(t), 'observed': sum(k.startswith('observed') for k in physical['kind']),
                      'manual': sum(k == 'manual' for k in physical['kind']), 'column_coverage': covered,
                      'thickness_px': extraction['thickness_px'], 'equal_time_samples_dropped': physical['equal_time_samples_dropped']},
            'time_range_us': [float(t.min()), float(t.max())] if len(t) else None,
            'missing_portions_us': gaps, 'resolution': resolution, 'flags': flags, 'notes': extraction['notes'] + analysis.get('notes', []),
            'metric_availability': {k: bool(v) for k, v in analysis['available'].items()}, 'digitization_spread': spread,
            'quantitative_comparison_allowed': quantitative, 'blocking_reasons': reasons,
            'evidence_class': 'image_digitized',
            'label': 'Digitized from image — approximate',
            'scope': 'Samples are pixels of the selected curve converted with the confirmed axis calibration. Uncertainty '
                     'combines anchor placement, trace thickness and pixel size. The spread below shows how metrics move '
                     'within that uncertainty; it is not a probability that the digitization is correct. Image-derived '
                     'samples never enter calibration or laboratory-accuracy workflows.'}


def digitization_spread(cal, physical, impulse_type, analysis, draws=MC_DRAWS, seed=11):
    """How much the metrics move when anchors and samples move within their pixel uncertainty."""
    rng = np.random.default_rng(seed)
    t = np.asarray(physical['time_us']); v = np.asarray(physical['voltage_kv'])
    st = np.asarray(physical['sigma_t_us']); sv = np.asarray(physical['sigma_v_kv'])
    m = analysis['metrics']
    rows = []
    for _ in range(draws):
        # Correlated anchor error: one gain/offset per axis; independent pixel error per sample.
        gain_t = 1 + rng.normal(0, cal['anchor_uncertainty_px'] * math.sqrt(2) / max(abs(cal['x'][2] - cal['x'][0]), 1))
        gain_v = 1 + rng.normal(0, cal['anchor_uncertainty_px'] * math.sqrt(2) / max(abs(cal['y'][2] - cal['y'][0]), 1))
        tt = t[0] + (t - t[0]) * gain_t + rng.normal(0, 1, len(t)) * st * .5
        vv = v * gain_v + rng.normal(0, 1, len(v)) * sv * .5
        order = np.argsort(tt); tt, vv = tt[order], vv[order]
        keep = np.r_[True, np.diff(tt) > 0]
        try:
            r = analyze(tt[keep], vv[keep], impulse_type, m['baseline_kv'], m['time_origin_us'])
            rows.append([r['front_us'], r['tail_us'], r['crest_kv']])
        except ValueError:
            continue
    if len(rows) < draws // 2:
        return {'available': False, 'reason': 'Metrics could not be re-extracted for most perturbed draws.'}
    a = np.array(rows)
    keys = ['front_us', 'tail_us', 'crest_kv']
    return {'available': True, 'draws': len(rows),
            'p05': dict(zip(keys, np.percentile(a, 5, axis=0).tolist())),
            'p95': dict(zip(keys, np.percentile(a, 95, axis=0).tolist())),
            'method': 'Anchors perturbed by their stated pixel uncertainty (as an axis gain error) and each sample by half its '
                      'pixel uncertainty; metrics re-extracted with the same definitions. 5th–95th percentile of the draws.'}
