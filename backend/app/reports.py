"""Self-contained, printable engineering discussion reports."""
import html


def report_html(run):
    def e(value):
        return html.escape(str(value), quote=True)

    def number(value, digits=3):
        return f'{value:,.{digits}f}'

    def table(headers, rows):
        head = ''.join(f'<th scope="col">{e(v)}</th>' for v in headers)
        body = ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows)
        return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

    def badge(label, kind='neutral'):
        return f'<span class="badge {kind}">{e(label)}</span>'

    c = run['candidates'][0]
    s = c['settings']
    inputs = run['inputs']
    wave = c.get('waveform')
    cross = c.get('circuit_crosscheck')
    nominal = c['compliance']['nominal_pass']
    status_kind = 'good' if c['compliance']['robust_pass'] else ('caution' if nominal else 'danger')
    solver_name = 'Workbook reference' if inputs['solver'] == 'reference' else 'Lumped equivalent circuit'
    rule = run['rules'][inputs['impulse_type']]

    provenance = table(['Configuration', 'Recorded value'], [
        ['Generator', f'{e(run["profile"]["name"])} · version {e(run["profile"]["version"])}'],
        ['Generator source', e(run['profile']['source'])],
        ['Inventory source / assumption', e(run['inventory_provenance'])],
        ['Prediction method', e(solver_name)],
        ['Residual model', e(run['model_version'])],
        ['Challenge rules', f'{e(run["rules"]["label"])} · version {e(run["rules"]["version"])}'],
        ['Rule source', e(run['rules']['source'])],
        ['Waveform definition', e(rule['definition'])],
    ])
    setup = table(['Setting', 'Value', 'Operating margin'], [
        ['Active stages', e(s['stages']), f'Allowed {e(run["profile"]["min_stages"])}–{e(run["profile"]["max_stages"])} stages'],
        ['Charge per stage', f'{number(s["charge_kv_stage"])} kV', f'{number(s["voltage_margin_kv_stage"])} kV below stage limit'],
        ['Stage voltage utilization', f'{number(s["stage_utilization"] * 100, 1)}%', f'{number(run["profile"]["stage_kv"], 0)} kV stage rating'],
        ['Stored energy', f'{number(s["stored_energy_kj"])} kJ', f'{number(s["energy_margin_kj"])} kJ below total limit'],
        ['Front network per stage', f'{e(c["front_network"]["topology"])}<br><span class="muted">Equivalent {number(s["front_r_stage"])} Ω</span>', f'{e(c["front_network"]["count_per_stage"])} parts / stage'],
        ['Tail network per stage', f'{e(c["tail_network"]["topology"])}<br><span class="muted">Equivalent {number(s["tail_r_stage"])} Ω</span>', f'{e(c["tail_network"]["count_per_stage"])} parts / stage'],
    ])

    if cross:
        disagrees = cross['compliance']['nominal_pass'] != nominal
        cross_kind = 'danger' if not cross['compliance']['nominal_pass'] else 'caution'
        heading = 'Model disagreement — investigate before applying settings' if disagrees else 'Independent circuit cross-check'
        comparison = table(['Metric', 'Reference / hybrid', 'Independent circuit', 'Challenge limits'], [
            [e(r['name']), f'{number(r["predicted"])} {e(r["unit"])}', f'{number(cross[k])} {e(r["unit"])}', f'{number(r["lower"])}–{number(r["upper"])} {e(r["unit"])}']
            for r, k in zip(c['compliance']['rows'], ['front_us', 'tail_us', 'crest_kv'])])
        cross_note = f'''<aside class="callout {'danger-callout' if disagrees else 'caution-callout'}"><h2>{e(heading)}</h2><p>The headline status uses the workbook reference and its selected correction. The independent circuit reports {badge(cross['compliance']['status'], cross_kind)} for the same settings.</p>{comparison}<p class="small">The reference curve reconstructs predicted metrics. The circuit solves a separate lumped RLC equivalent; neither has laboratory validation. Its status is a waveform-only check without calibrated intervals. A passing reference result does not establish that the physical circuit will pass.</p></aside>'''
    else:
        cross_note = '<aside class="callout caution-callout"><p>This waveform comes from a lumped equivalent circuit. Its topology and assumed loss factor require measured validation; this result does not establish laboratory compliance.</p></aside>'
    if c.get('model_agreement'):
        agreement=c['model_agreement']
        outcome='Both nominal model checks pass' if agreement['both_nominal_pass'] else 'No agreement at this setting'
        cross_note+=f'<aside class="callout caution-callout"><h2>Search requiring model agreement</h2><p><strong>{e(outcome)}</strong>. {number(agreement["sampled_both_pass_pct"],1)}% of {e(agreement["scenario_count"])} sampled parasitic scenarios pass both models.</p><p>{e(agreement["scope"])} {e(agreement["scenario_note"])}</p></aside>'

    chart = '<p class="muted">A curve could not be reconstructed for these metrics. The numeric results below remain the basis for compliance.</p>'
    if wave:
        xmax = rule['tail_target_us'] * 1.4
        primary_label = 'Circuit prediction' if wave['kind'] == 'equivalent_circuit' else 'Shape reconstructed from predicted metrics'
        curves = [(wave, primary_label, '#087f8c', '' if wave['kind'] == 'equivalent_circuit' else '7 4')]
        if c.get('physics_waveform') and inputs['solver'] == 'reference':
            curves.append((c['physics_waveform'], 'Workbook-equation metrics (reconstructed shape)', '#6173a5', '5 4'))
        if run.get('target_waveform'):
            curves.append((run['target_waveform'], 'Target shape', '#7d8991', '3 5'))
        if cross and cross.get('waveform'):
            curves.append((cross['waveform'], 'Circuit simulation (cross-check)', '#bd5141', ''))
        ymax = max(max(w['voltage_kv']) for w, _, _, _ in curves) * 1.12
        lines, legend, grid = [], [], []
        for curve, label, color, dash in curves:
            pts = ' '.join(f'{70+x/xmax*890:.2f},{250-y/ymax*210:.2f}' for x, y in zip(curve['time_us'], curve['voltage_kv']) if 0 <= x <= xmax)
            lines.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-dasharray="{dash}"/>')
            legend.append(f'<span><i style="background:{color}"></i>{e(label)}</span>')
        for j in range(5):
            x, y = 70 + j * 890 / 4, 250 - j * 210 / 4
            grid.append(f'<path d="M{x:.2f} 40V250 M70 {y:.2f}H960" stroke="#e1e8ec" stroke-width="1"/><text x="{x:.2f}" y="270" text-anchor="middle">{number(xmax*j/4, 1)}</text><text x="60" y="{y+4:.2f}" text-anchor="end">{number(ymax*j/4, 0)}</text>')
        kind = ('Shape reconstructed from three predicted metrics; it is not an independently simulated waveform'
                if wave['kind'] == 'metric_reconstruction' else 'Lumped-circuit simulation at the recommended settings')
        consistency = c.get('waveform_consistency') or {}
        if consistency.get('primary') and consistency['primary'].get('metrics'):
            worst = max(row['relative_difference'] for row in consistency['primary']['metrics'].values())
            kind += (f'. Metrics re-extracted from the plotted samples differ from the reported metrics by at most {worst * 100:.4f}%'
                     + (' (within documented tolerance)' if consistency.get('consistent') else ' (OUTSIDE documented tolerance — review)'))
            if consistency.get('relationship') == 'locally_corrected_metrics_shown_separately':
                kind += '. Locally corrected metrics are listed below and are not drawn as a curve'
        chart = f'''<figure class="waveform"><div class="chart-legend">{''.join(legend)}</div><svg viewBox="0 0 1000 305" role="img" aria-label="Predicted impulse voltage plotted against time">{''.join(grid)}<path d="M70 40V250H960" fill="none" stroke="#70838f"/>{''.join(lines)}<text x="515" y="297" text-anchor="middle">Time (µs)</text><text x="70" y="25">Voltage (kV)</text></svg><figcaption>{e(kind)}. Compliance is calculated from numeric metrics, not from this chart. The plot shows the first {number(xmax, 1)} µs.</figcaption></figure>'''

    compliance = table(['Metric', 'Target', 'Prediction', 'Allowed range', 'Deviation', 'Nominal result'], [
        [e(r['name']), f'{number(r["target"])} {e(r["unit"])}', f'{number(r["predicted"])} {e(r["unit"])}', f'{number(r["lower"])}–{number(r["upper"])} {e(r["unit"])}', f'{r["deviation_pct"]:+.2f}%', badge('PASS' if r['pass'] else 'FAIL', 'good' if r['pass'] else 'danger')]
        for r in c['compliance']['rows']])
    interval_rows = []
    for j, r in enumerate(c['compliance']['rows']):
        lower, upper = c['uncertainty']['lower'][j], c['uncertainty']['upper'][j]
        contained = lower >= r['lower'] and upper <= r['upper']
        label = 'Inside limits' if contained else ('Overlaps / exceeds limits' if r['pass'] else 'Point estimate outside limits')
        interval_rows.append([e(r['name']), f'{number(lower)}–{number(upper)} {e(r["unit"])}', f'{number(r["lower"])}–{number(r["upper"])} {e(r["unit"])}', badge(label, 'good' if contained and r['pass'] else 'caution')])
    intervals = table(['Metric', 'Prediction envelope', 'Challenge limits', 'Envelope containment'], interval_rows)
    coverage = c['uncertainty'].get('coverage_claim')
    coverage_text = f'Calibration level: {coverage * 100:.0f}% under the stated synthetic-data assumptions; see the method and coverage limits.' if coverage is not None else 'No calibrated statistical coverage is claimed for this envelope.'
    support_names = {'in_distribution': 'Within training support', 'limited_support': 'Limited training support', 'out_of_distribution': 'Outside training support', 'profile_not_calibrated': 'Generator profile not calibrated', 'physics_mode': 'Physics only'}
    support = support_names.get(c['ood']['state'], c['ood']['state'].replace('_', ' '))
    robustness = c['robustness']
    parameter_names = {'load_c_pf': 'Test-object capacitance', 'divider_c_pf': 'Divider capacitance', 'stray_c_pf': 'Stray capacitance', 'l_uh': 'Connection inductance'}
    sensitivity = table(['Parameter changed by +5%', 'Largest relative change across waveform metrics'], [[e(parameter_names.get(k, k)), f'{number(v, 2)}%'] for k, v in robustness.get('sensitivity_5pct', {}).items()])

    component_rows = []
    for name, network in [('Front', c['front_network']), ('Tail', c['tail_network'])]:
        for part in network['components']:
            available = part.get('available_per_stage')
            total = part.get('total_required', part['count_per_stage'] * s['stages'])
            known = available is not None and part['count_per_stage'] <= available
            component_rows.append([e(name), f'{number(part["ohm"])} Ω', e(part['count_per_stage']), e(total), e(available) if available is not None else 'Not recorded', e(available * s['stages']) if available is not None else 'Not recorded', badge('Within stock' if known else 'Verify stock', 'good' if known else 'caution')])
    components = table(['Function', 'Resistor value', 'Required / stage', 'Required total', 'Available / stage', 'Available on active stages', 'Stock check'], component_rows)
    alternatives = table(['Rank', 'Stages', 'Charge / stage', 'Front network / stage', 'Tail network / stage', 'Model status', 'Weighted cost'], [
        [e(x['rank']), e(x['settings']['stages']), f'{number(x["settings"]["charge_kv_stage"])} kV', e(x['front_network']['topology']), e(x['tail_network']['topology']), badge(x['compliance']['status'], 'good' if x['compliance']['robust_pass'] else ('caution' if x['compliance']['nominal_pass'] else 'danger')), number(x['score'], 4)] for x in run['candidates']])
    score_names = {'front_deviation': 'Front / peak deviation', 'tail_deviation': 'Tail deviation', 'crest_deviation': 'Crest deviation', 'setup_complexity': 'Component count / setup complexity', 'ood_penalty': 'Training-support penalty', 'operating_margin_penalty': 'Stage-voltage utilization penalty', 'uncertainty_penalty': 'Prediction-envelope penalty'}
    scores = table(['Rank-one cost contribution', 'Weighted value'], [[e(score_names.get(k, k.replace('_', ' '))), number(v, 4)] for k, v in c['score_breakdown'].items()] + [['Total weighted cost', f'<strong>{number(c["score"], 4)}</strong>']])

    labels = {'profile_id': 'Generator profile', 'impulse_type': 'Impulse type', 'test_kv': 'Requested crest voltage', 'load_c_pf': 'Test-object capacitance', 'divider_c_pf': 'Divider capacitance', 'stray_c_pf': 'Stray capacitance', 'l_uh': 'Connection inductance', 'efficiency': 'Expected voltage efficiency', 'solver': 'Prediction method', 'model_mode': 'Residual correction mode', 'connection_mode': 'Connection model', 'layout_id': 'Physical layout identifier', 'stage_min': 'Requested minimum stages', 'stage_max': 'Requested maximum stages', 'inventory_override': 'Explicit inventory override', 'max_components_per_network': 'Maximum parts per network', 'include_base_c': 'Include profile base capacitance', 'uncertainty_pct': 'Assumed parasitic range', 'monte_carlo_samples': 'Parasitic scenarios', 'equipment_reference_kv': 'Equipment reference voltage', 'equipment_reference_source': 'Equipment reference source', 'confirm_reference_mismatch': 'Equipment mismatch explicitly confirmed', 'calibration_id': 'Requested local correction'}
    units = {'test_kv': ' kV', 'load_c_pf': ' pF', 'divider_c_pf': ' pF', 'stray_c_pf': ' pF', 'l_uh': ' µH', 'equipment_reference_kv': ' kV'}
    input_rows = []
    for key, value in inputs.items():
        if key == 'inventory_override': value = f'Yes — {value["provenance"]}. Quantities appear in the component plan.' if value else 'No — profile stock is used'
        elif key == 'require_model_agreement': value = 'Required across workbook and independent circuit' if value else 'Single prediction engine with independent review'
        elif key == 'profile_id': value = run['profile']['name']
        elif key == 'solver': value = solver_name
        elif key == 'model_mode': value = {'hybrid':'Trust-gated residual correction','physics':'Physics only','experimental_v2':'Experimental V2 residual correction (development evidence)'}.get(value,value)
        elif key == 'connection_mode': value = 'Series Marx equivalent'
        elif key == 'efficiency': value = f'{number(value * 100, 1)}%'
        elif key == 'uncertainty_pct': value = f'±{number(value, 1)}% in capacitance and inductance'
        elif value is None: value = 'Not specified'
        elif isinstance(value, bool): value = 'Yes' if value else 'No'
        elif key in units: value = number(value) + units[key]
        input_rows.append([e(labels.get(key, key.replace('_', ' ').capitalize())), e(value)])
    input_table = table(['Input', 'Recorded value'], input_rows)

    calibration = ''
    review, local = run.get('calibration_review'), c.get('calibration')
    if review or local:
        applied = bool(local) or bool(review and review.get('applied'))
        correction = local or review
        source = correction.get('source_type', 'not recorded')
        source_label = {'measured_lab': 'Measured laboratory waveform', 'generated_stress_test': 'Generated demonstration waveform'}.get(source, source)
        if applied:
            bias = local['bias'] if local else review['correction']
            detail = table(['Metric', 'Saved additive correction'], [[e(r['name']), f'{b:+.3f} {e(r["unit"])}'] for r, b in zip(c['compliance']['rows'], bias)])
            if not local: detail += '<p>The correction applies to the reviewed original setting, not the rank-one alternative shown above.</p>'
        else:
            detail = f'<p>{e(review.get("reason", "No matching candidate was found."))}</p>'
        calibration = f'''<section><h2>Trial-shot feedback</h2><div class="callout caution-callout"><p><strong>{'Scoped correction applied' if applied else 'Saved correction not applied'}</strong> · source: {e(source_label)} · record {e(correction['id'])}</p>{detail}<p>A one-shot additive correction is unvalidated. It does not retrain production models or establish interval coverage. It applies only to the saved profile, rules, model, layout, solver, resistor topology and settings, with inputs within 1%. Reduced-voltage to full-voltage transfer is not inferred.</p></div></section>'''
    reason_list = ''.join(f'<li>{e(v)}</li>' for v in c['explanation'])
    warnings = ''.join(f'<li>{e(v)}</li>' for v in run['warnings'])
    verification=''
    if c.get('verification'):
        v=c['verification'];w=v['worst_case']
        verification=f'''<aside class="callout {'caution-callout' if v['all_checks_pass'] else 'danger-callout'}"><h2>Post-ranking settings challenge</h2><p><strong>{e(v['passed'])}/{e(v['total'])} scenarios pass every checked model.</strong> Separate samples: {e(v['fresh_samples']['passed'])}/{e(v['fresh_samples']['total'])}; boundary corners: {e(v['boundary_corners']['passed'])}/{e(v['boundary_corners']['total'])}. {e(v['unique_scenarios'])} distinct scenarios.</p><p>Most limiting: {e(w['limiting_model'])}, {e(w['limiting_metric'])} = {number(w['predicted'])} {e(w['unit'])}, allowed {number(w['allowed_lower'])}–{number(w['allowed_upper'])}. Margin: {number(w['minimum_margin_fraction']*100,1)}% of the allowed half-range.</p><p class="small">{e(v['scope'])}</p></aside>'''
    ranking_order=' → '.join(run['ranking_config']['ranking_order'])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ImpulseTwin report {e(run['id'])}</title>
<style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#edf2f5;color:#182f3e;font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}main{{max-width:1100px;margin:28px auto;background:#fff;padding:46px 50px;box-shadow:0 8px 30px #162d3e0c}}header{{border-bottom:2px solid #173447;padding-bottom:25px;margin-bottom:26px}}.eyebrow{{color:#087f8c;font-size:11px;letter-spacing:1.8px;text-transform:uppercase;font-weight:700}}h1{{font-size:37px;line-height:1.15;margin:9px 0 7px;letter-spacing:-1px}}h2{{font-size:20px;line-height:1.3;margin:0 0 14px;color:#183c50}}section{{margin-top:32px}}p{{margin:9px 0 15px}}.subtitle{{font-size:16px;color:#576d7a}}.meta{{display:flex;gap:24px;flex-wrap:wrap;color:#627783;font-size:12px}}.toolbar{{max-width:1100px;margin:20px auto 0;padding:0 8px}}button{{border:0;border-radius:7px;background:#173f51;color:#fff;padding:11px 18px;font-weight:600;cursor:pointer}}.summary{{background:#f0f7f9;border:1px solid #d5e7ec;padding:20px 24px;margin:24px 0}}.summary-line{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:16px;font-weight:600}}.badge{{display:inline-block;border-radius:4px;padding:3px 8px;white-space:normal;font-size:11px;font-weight:700;line-height:1.4;background:#e8eef2;color:#435b6a}}.good{{background:#e6f3ee;color:#1f674c}}.caution{{background:#fff2dc;color:#805416}}.danger{{background:#fdebe8;color:#9c3d30}}.callout{{padding:18px 20px;margin:22px 0;border:1px solid #eadfcb;border-left:4px solid #b68532;background:#fffcf7}}.callout h2{{font-size:18px;margin-bottom:10px}}.danger-callout{{background:#fff7f5;border-color:#edd3cd;border-left-color:#b74b3d}}.small,.muted,figcaption{{font-size:12px;color:#607583}}.table-wrap{{width:100%;overflow-x:auto;margin:12px 0}}table{{width:100%;border-collapse:collapse;font-size:12px;line-height:1.45}}th,td{{padding:10px 11px;vertical-align:top;border-bottom:1px solid #dfe7eb;text-align:left;overflow-wrap:anywhere}}th{{background:#eef4f6;color:#365362;font-size:11px;font-weight:700}}tbody tr:last-child td{{border-bottom:1px solid #c7d6df}}td:first-child{{font-weight:500}}.waveform{{margin:14px 0 20px;border:1px solid #dde7ec;padding:15px 16px 12px}}svg{{width:100%;height:auto;display:block;font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;fill:#607582}}.chart-legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#536b78;padding-left:8px}}.chart-legend span{{display:flex;align-items:center;gap:6px}}.chart-legend i{{display:inline-block;width:18px;height:3px}}figcaption{{border-top:1px solid #e7edf0;padding-top:9px;margin-top:4px}}ul{{padding-left:21px}}li{{margin:7px 0}}footer{{border-top:1px solid #cbd9e2;margin-top:34px;padding-top:18px;color:#607582;font-size:11px}}.footer-note{{margin-bottom:8px;font-weight:600;color:#425e6f}}
@media(max-width:700px){{main{{margin:12px;padding:28px 20px}}h1{{font-size:30px}}th,td{{padding:8px}}.meta{{gap:10px}}}}
@page{{size:A4;margin:13mm}}@media print{{body{{background:white;font-size:10pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}}main{{max-width:none;margin:0;padding:0;box-shadow:none}}.toolbar{{display:none}}header{{padding-bottom:14px}}h1{{font-size:27pt}}h2{{font-size:14pt;break-after:avoid}}section{{margin-top:22px}}table{{font-size:8.3pt}}th,td{{padding:7px 8px}}thead{{display:table-header-group}}tr,.summary,figure{{break-inside:avoid}}.table-wrap{{overflow:visible}}p,li{{orphans:3;widows:3}}.callout{{padding:12px 14px}}footer{{font-size:8pt}}}}
</style></head><body><div class="toolbar"><button type="button" onclick="window.print()">Print / save PDF</button></div><main>
<header><div class="eyebrow">Physics-guided high-voltage decision support</div><h1>ImpulseTwin AI</h1><p class="subtitle">Laboratory setup discussion report</p><div class="meta"><span>Run <strong>{e(run['id'])}</strong></span><span>Recorded {e(run['created_at'])}</span><span>{e(inputs['impulse_type'])} impulse</span></div></header>
<div class="summary"><div class="summary-line">{badge(c['compliance']['status'], status_kind)}<span>{e(solver_name)} result · {number(inputs['test_kv'], 0)} kV requested crest</span></div><p>Under {e(run['rules']['label'])}. Decision support; engineer verification required. This is a model prediction, not a measured test result.</p>{'<p><strong>No nominally compliant candidate was found. The setup below is a diagnostic alternative.</strong></p>' if not nominal else ''}</div>
{cross_note}
{verification}
<section><h2>1. Configuration and provenance</h2>{provenance}</section>
<section><h2>2. {'Rank-one setup' if nominal else 'Rank-one diagnostic setup'}</h2>{setup}<p class="small">{e(c['setup_component_count'])} total front/tail parts across {e(s['stages'])} active stages. Stock arithmetic and declared ratings are checked; permitted mounting and resistor pulse ratings require engineering confirmation.</p>{chart}{compliance}</section>
<section><h2>3. Uncertainty and training support</h2><p><strong>{e(support)}</strong> · residual-correction weight {number(c['ood']['trust_weight'], 3)}<br>{e(c['uncertainty']['method'])}</p>{intervals}<p class="small">{e(coverage_text)} {e(c['uncertainty'].get('coverage_limit', ''))}</p><p>Parasitic ranges: ±{number(inputs['uncertainty_pct'], 1)}% · {e(robustness['samples'])} finite scenarios · {number(robustness['nominal_scenario_pass_pct'], 1)}% of sampled point predictions pass.</p><p class="small">{e(robustness['note'])}</p>{sensitivity}</section>
<section><h2>4. Resistor component plan</h2>{components}<p class="small">Availability totals refer to the active stages and the declared per-stage stock. Inventory provenance: {e(run['inventory_provenance'])}.</p></section>
<section><h2>5. Ranked alternatives and reasoning</h2>{alternatives}<p class="small">Ranking order: {e(ranking_order)}. The bounded shortlist is not proof of a global optimum.</p>{scores}<ul>{reason_list}</ul></section>
{calibration}
<section><h2>6. Recorded inputs</h2>{input_table}</section>
<section><h2>7. Limits of this result</h2><ul>{warnings}</ul><p>Published workbook validation-table discrepancy remains documented in source reconciliation. All trained models use supplied synthetic records; no laboratory validation or measured reduction in trial shots has been established.</p></section>
<footer><p class="footer-note">Retain this report with the approved laboratory setup and measured waveform record.</p>Sources: HV IG Problem Statement.pdf; Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx; PowerNext_AI_Track1_Briefing_Transcript.md.<br>Run {e(run['id'])} · model {e(run['model_version'])} · generator {e(run['profile']['version'])} · challenge rules {e(run['rules']['version'])}</footer>
</main></body></html>'''
