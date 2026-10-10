"""Self-contained HTML report of a diagnostic session (no scripts, no external assets)."""
import html
import math
from datetime import datetime, timezone

E = html.escape
COLOURS = {'target': '#8a8f98', 'prediction': '#1f6f5c', 'uploaded': '#1d4ed8', 'fitted': '#b45309', 'residual': '#7c3aed'}


def _num(v, digits=4):
    if not isinstance(v, (int, float)) or v != v or v in (math.inf, -math.inf):
        return '—'
    return f'{v:.{digits}g}'


def _ticks(lo, hi, n=6):
    span = hi - lo or 1.
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.ceil(lo / step) * step
    out = []
    while start <= hi + 1e-9 * span:
        out.append(round(start, 10)); start += step
    return out


def svg_chart(series, *, width=860, height=320, x_label='Time (µs)', y_label='Voltage (kV)', x_range=None):
    pts = [(x, y) for s in series for x, y in zip(s['x'], s['y']) if isinstance(y, (int, float)) and y == y]
    if not pts:
        return '<p>No data to plot.</p>'
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1 = x_range or (min(xs), max(xs))
    y0, y1 = min(ys + [0]), max(ys)
    pad = .06 * (y1 - y0 or 1); y0 -= pad; y1 += pad
    L, R, T, B = 64, 16, 14, 40
    sx = lambda x: L + (x - x0) / ((x1 - x0) or 1) * (width - L - R)
    sy = lambda y: T + (y1 - y) / ((y1 - y0) or 1) * (height - T - B)
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{E(y_label)} against {E(x_label)}" class="chart">']
    for t in _ticks(x0, x1):
        out.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{T}" y2="{height - B}" class="grid"/>'
                   f'<text x="{sx(t):.1f}" y="{height - B + 16}" text-anchor="middle">{_num(t, 4)}</text>')
    for t in _ticks(y0, y1):
        out.append(f'<line x1="{L}" x2="{width - R}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" class="grid"/>'
                   f'<text x="{L - 6}" y="{sy(t) + 4:.1f}" text-anchor="end">{_num(t, 4)}</text>')
    out.append(f'<text x="{(L + width - R) / 2}" y="{height - 6}" text-anchor="middle">{E(x_label)}</text>')
    out.append(f'<text x="14" y="{(T + height - B) / 2}" transform="rotate(-90 14 {(T + height - B) / 2})" text-anchor="middle">{E(y_label)}</text>')
    for s in series:
        step = max(1, len(s['x']) // 1500)
        path = ' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x, y in list(zip(s['x'], s['y']))[::step] if x0 <= x <= x1)
        dash = ' stroke-dasharray="6 4"' if s.get('dash') else ''
        out.append(f'<polyline fill="none" stroke="{s["colour"]}" stroke-width="{s.get("width", 1.6)}"{dash} points="{path}"/>')
    out.append('</svg>')
    legend = ''.join(f'<span><i style="background:{s["colour"]}"></i>{E(s["label"])}</span>' for s in series)
    return ''.join(out) + f'<div class="legend">{legend}</div>'


def _table(rows, head):
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table><thead><tr>{"".join(f"<th>{E(h)}</th>" for h in head)}</tr></thead><tbody>{body}</tbody></table>'


def report_html(view):
    s = view['session']; ref = view['reference'] or {}; up = view['upload'] or {}; dg = view['digitization'] or {}
    cmp = view['comparison']; inv = view['investigation']; stale = view['stale']
    fired = ref.get('as_fired')
    parts = []
    demo = s.get('demo') or up.get('origin') == 'demonstration'
    parts.append(f'<header><h1>Waveform diagnostic — {E(s.get("title", ""))}</h1>'
                 f'<p>Session {E(s["session_id"])} · revision {s["revision"]} · report generated '
                 f'{datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")} · {E(view["version"])}</p>'
                 + ('<p class="banner">Generated demonstration. The recording was produced by the application; it is not a '
                    'laboratory record.</p>' if demo else '')
                 + '<p class="banner neutral">Diagnostic comparison only. No laboratory accuracy, certification or fault '
                   'finding is claimed. Image-derived samples never enter calibration or accuracy workflows.</p></header>')
    for key, text in stale.items():
        parts.append(f'<p class="banner warn">{E(text)}</p>')
    if ref:
        st = ref['settings']; ci = ref['circuit_inputs']
        rows = [['Generator profile', E(str(ref.get('profile_label')))], ['Impulse type / request', f"{E(ref['impulse_type'])} · {_num(ref['test_kv'])} kV"],
                ['Active stages', str(st['stages'])], ['Charge per stage', f"{_num(st['charge_kv_stage'])} kV"],
                ['Stage capacitance', f"{_num(ref['profile']['stage_c_uf'])} µF"],
                ['Front / tail resistance per stage', f"{_num(st['front_r_stage'])} Ω / {_num(st['tail_r_stage'])} Ω"],
                ['Load / divider / stray', f"{_num(ci['load_c_pf'])} / {_num(ci['divider_c_pf'])} / {_num(ci['stray_c_pf'])} pF"],
                ['545 pF base capacitance', 'included' if ref.get('include_base_c') else 'not included'],
                ['Total load-side capacitance', f"{_num(ref['total_c_pf'])} pF"], ['Inductance', f"{_num(ci['l_uh'])} µH"],
                ['Loss factor', f"{_num(ref['efficiency'], 3)} — {E(ref['loss_factor']['meaning'])}"],
                ['Physics', E(ref['physics_version'])], ['Rules', E(str(ref.get('rules_version')))],
                ['Snapshot', f"{E(ref['snapshot_version'])} · run {E(ref['run_id'])} · candidate {E(ref['candidate_id'])}"]]
        parts.append('<section><h2>1. Reference</h2>' + _table(rows, ['Item', 'Value']) +
                     f'<p class="small">{E(ref["topology"])}</p><h3>Open questions that move the prediction</h3><ul>' +
                     ''.join(f'<li><b>{E(q["title"])}.</b> {E(q["text"])}</li>' for q in ref['open_questions']) + '</ul>')
        if fired:
            diffs = [[E(d['label']), _num(d['recommended']), _num(d['fired'])] for d in fired['differences']] or [['No difference declared', '', '']]
            parts.append('<h3>Settings actually fired</h3>' + _table(diffs, ['Field', 'Recommended', 'Fired']) +
                         f'<p class="small">Declared: {E(", ".join(fired["declared_fields"]) or "none")}. Assumed unchanged: '
                         f'{E(", ".join(fired["assumed_unchanged"]))}. Declared uncertain: {E(", ".join(fired["uncertain_fields"]) or "none")}.</p>' +
                         ''.join(f'<p class="banner warn">{E(f["message"])}</p>' for f in fired['rating_flags']))
        else:
            parts.append('<p class="banner warn">The settings actually fired were not recorded. Hardware diagnosis is limited.</p>')
        parts.append('</section>')
    if up:
        rows = [['Declared origin', E(up.get('origin_label', ''))], ['File', E(up.get('original_filename') or 'not recorded')],
                ['SHA-256', f'<code>{E(up["sha256"])}</code>'], ['Size', f"{up['bytes']} bytes"],
                ['Evidence class', E(up.get('label', ''))]]
        if up.get('image'):
            rows.append(['Image', f"{up['image']['format'].upper()} {up['image']['width']}×{up['image']['height']} px"])
        rows += [['Captured at', E(str(up.get('captured_at') or 'not recorded'))], ['Instrument', E(str(up.get('instrument') or 'not recorded'))],
                 ['Session / shot', E(f"{up.get('session_label') or '—'} / {up.get('shot_label') or '—'}")]]
        parts.append('<section><h2>2. Uploaded waveform</h2>' + _table(rows, ['Item', 'Value']) +
                     f'<p class="small">{E(up.get("origin_scope", ""))} {E(up.get("admission", ""))}</p>')
        if dg:
            q = dg['quality']
            if dg['source'] == 'image':
                cal = dg['calibration']
                parts.append('<h3>Digitization</h3>' + _table([
                    ['Transforms', E(', '.join(st['step'] for st in dg['transform']['steps']) or 'none')],
                    ['Calibration', f"{E(cal['mode'])}; {_num(cal['us_per_px'])} µs/px; {_num(cal['kv_per_px'])} kV/px; anchors ±{_num(cal['anchor_uncertainty_px'])} px"],
                    ['Voltage axis', E(f"{cal['voltage_side']} (scale applied ×{cal['voltage_scale_applied']:g})")],
                    ['Samples', f"{q['trace']['samples']} ({q['trace']['manual']} manual)"],
                    ['Trace thickness', f"{_num(q['trace']['thickness_px'], 3)} px"],
                    ['Missing portions', E('; '.join(f'{a:.4g}–{b:.4g} µs' for a, b in q['missing_portions_us']) or 'none')]], ['Item', 'Value']))
                spread = q.get('digitization_spread') or {}
                if spread.get('available'):
                    parts.append('<p class="small">Digitization spread (5th–95th percentile): ' + '; '.join(
                        f"{k.replace('_us', ' (µs)').replace('_kv', ' (kV)')} {_num(spread['p05'][k])}–{_num(spread['p95'][k])}" for k in ('front_us', 'tail_us', 'crest_kv')) +
                        f'. {E(spread["method"])}</p>')
            flags = q.get('flags') or []
            if flags:
                parts.append('<h3>Quality flags</h3><ul>' + ''.join(f'<li>{E(f["message"])}</li>' for f in flags) + '</ul>')
            parts.append(f'<p>Quantitative diagnosis: <b>{"allowed" if q["quantitative_comparison_allowed"] else "disabled — visual comparison only"}</b>.</p>')
        parts.append('</section>')
    if cmp:
        series = []
        if ref.get('target'):
            series.append({'x': ref['target']['time_us'], 'y': ref['target']['voltage_kv'], 'colour': COLOURS['target'], 'label': 'Illustrative target shape', 'dash': True})
        pred = (fired or {}).get('prediction') or ref.get('prediction')
        series.append({'x': pred['waveform']['time_us'], 'y': pred['waveform']['voltage_kv'], 'colour': COLOURS['prediction'], 'label': cmp['prediction_label']})
        series.append({'x': cmp['observed']['time_us'], 'y': cmp['observed']['voltage_kv'], 'colour': COLOURS['uploaded'],
                       'label': cmp.get('evidence_label') or 'Uploaded waveform'})
        if inv and inv.get('fitted_curves'):
            c = inv['fitted_curves'][0]
            series.append({'x': c['time_us'], 'y': c['voltage_kv'], 'colour': COLOURS['fitted'], 'label': c['label'], 'dash': True})
        t_obs = cmp['observed']['time_us']
        rng = (min(t_obs + [0]), max(t_obs))
        rows = []
        for r in cmp['metrics']:
            rows.append([E(r['label']), _num(r.get('observed')), _num(r['predicted']),
                         (f"{r['difference']:+.4g} ({r['difference_pct']:+.3g}%)" if r.get('difference') is not None else '—'),
                         E(r['status']) + (f'<br><span class="small">{E(r["reason"])}</span>' if r.get('reason') else '')])
        ww = cmp.get('whole_waveform') or {}
        parts.append('<section><h2>3. Comparison</h2>' + svg_chart(series, x_range=rng) +
                     (svg_chart([{'x': cmp['residual']['time_us'], 'y': cmp['residual']['kv'], 'colour': COLOURS['residual'], 'label': 'Uploaded minus prediction'}],
                                height=200, y_label='Difference (kV)', x_range=rng) if cmp['residual']['time_us'] else '') +
                     _table(rows, ['Metric', 'Uploaded', 'Prediction', 'Difference', 'Status']) +
                     f'<p class="small">Alignment: {E(cmp["alignment"]["basis"])}, time shift {_num(cmp["alignment"]["time_shift_us"])} µs. '
                     f'{E(cmp["alignment"]["note"])} {E(cmp.get("uncertainty_basis") or "")}</p>' +
                     (f'<p>Whole-waveform normalized mismatch {_num(ww.get("normalized_mismatch"), 3)}; RMS difference '
                      f'{_num(ww.get("rms_pct_of_predicted_crest"), 3)}% of predicted crest. {E(ww.get("meaning", ""))} {E(ww.get("weighting", ""))}</p>' if ww else '') +
                     (f'<p class="banner warn">{E(cmp["diagnosis_limited"])}</p>' if cmp.get('diagnosis_limited') else '') + '</section>')
    if inv:
        verdict = inv['verdict']
        rows = []
        for h in inv['hypotheses']:
            params = ', '.join(f'{k} {_num(v)}' for k, v in (h.get('parameters') or {}).items())
            rows.append([E(h['title']), E(h.get('status', '')), _num(h.get('mismatch'), 3), _num(h.get('improvement_pct'), 3), E(params or '—')])
        parts.append(f'<section><h2>4. Possible causes</h2><p class="verdict"><b>{E(verdict["label"])}.</b> {E(verdict["message"])}'
                     + (f' {E(verdict["limited"])}' if verdict.get('limited') else '') + '</p>'
                     + _table(rows, ['Explanation', 'Status', 'Normalized mismatch', 'Improvement %', 'Fitted values'])
                     + f'<p class="small">{E(inv["statement"])} Ranking: {E(inv["policy"]["penalty"])}. {E(inv["policy"]["weighting"])}</p>')
        rs = inv.get('residual_structure') or {}
        if rs:
            parts.append(f'<p class="small">Remaining difference: {E(rs.get("meaning", ""))}</p>')
        parts.append('</section><section><h2>5. Findings and checks</h2>')
        for f in inv.get('findings') or []:
            parts.append(f'<article><h3>{E(f["title"])} <span class="tag">{E(f["status"])}</span></h3>'
                         f'<p><b>{E(f["category"])}</b> · {E(f["component_group"])}</p><p>{E(f["explanation"])}</p>'
                         + _table([[E(v['quantity']), E(v['nominal']), E(v['effective'])] for v in f['values']], ['Quantity', 'Nominal', 'Effective (fitted)'])
                         + (f'<p><b>Supporting:</b></p><ul>' + ''.join(f'<li>{E(x)}</li>' for x in f['supporting_evidence']) + '</ul>' if f['supporting_evidence'] else '')
                         + (f'<p><b>Against:</b></p><ul>' + ''.join(f'<li>{E(x)}</li>' for x in f['contradicting_evidence']) + '</ul>' if f['contradicting_evidence'] else '')
                         + (f'<p><b>Ambiguity:</b></p><ul>' + ''.join(f'<li>{E(x)}</li>' for x in f['ambiguity']) + '</ul>' if f['ambiguity'] else '')
                         + '<p><b>How to check:</b></p><ul>' + ''.join(f'<li>{E(x)}</li>' for x in f['verification']) + '</ul>'
                         + f'<p class="small">{E(f["safety"])} {E(f["not_a_fault_statement"])}</p>'
                         + (('<p class="small">If confirmed, the recommended setting would give ' + ', '.join(
                             f"{k.replace('_us', '').replace('_kv', '')} {_num(v)}" for k, v in f['predicted_effect_if_confirmed']['metrics_if_confirmed'].items())
                             + f" (simulated). {E(f['predicted_effect_if_confirmed']['note'])}</p>") if f.get('predicted_effect_if_confirmed') else '')
                         + '</article>')
        if not inv.get('findings'):
            parts.append('<p>No explanation is consistent with the recording; no finding is listed.</p>')
        parts.append('</section>')
    style = ('body{font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif;color:#1c2430;max-width:960px;margin:32px auto;padding:0 20px}'
             'h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:28px 0 8px;border-bottom:1px solid #d9dee5;padding-bottom:4px}'
             'h3{font-size:16px;margin:18px 0 6px}table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border-bottom:1px solid #e4e8ee;'
             'padding:6px 8px;text-align:left;vertical-align:top;font-size:14px}th{background:#f4f6f9}.small{font-size:13px;color:#4b5563}'
             '.banner{background:#fdecec;color:#7f1d1d;padding:8px 12px;border-radius:6px}.banner.neutral{background:#eef2f7;color:#1f2937}'
             '.banner.warn{background:#fff6e5;color:#7a4b00}.chart{width:100%;height:auto;font-size:11px;fill:#4b5563}'
             '.chart .grid{stroke:#e5e7eb}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin:4px 0 12px}'
             '.legend i{display:inline-block;width:14px;height:3px;margin-right:6px;vertical-align:middle}'
             'article{border:1px solid #e4e8ee;border-radius:8px;padding:4px 16px 8px;margin:12px 0}.tag{font-size:12px;'
             'background:#eef2f7;padding:2px 8px;border-radius:10px;margin-left:6px;font-weight:500}.verdict{font-size:16px}'
             'code{font-size:12px;word-break:break-all}@media print{body{margin:0}}')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Waveform diagnostic {E(s["session_id"])}</title><style>{style}</style></head><body>' + ''.join(parts) + '</body></html>')
