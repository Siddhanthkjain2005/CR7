"""Offline reports of the immutable generated experiment and its assumptions."""
import csv
import html
import io
import json


def csv_text(record):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['# Generated hypothetical fault; no laboratory validation; no hardware control'])
    writer.writerow([f'# Fault test {record["id"]}; saved run {record["reference"]["run_id"]}; version {record["version"]}'])
    writer.writerow(['time_us', 'healthy_voltage_kv', 'fault_voltage_kv'])
    writer.writerows(zip(record['healthy']['waveform']['time_us'], record['healthy']['waveform']['voltage_kv'],
                         record['fault']['waveform']['voltage_kv']))
    return stream.getvalue()


def report_html(record):
    escape = lambda value: html.escape(str(value))
    title = record['request'].get('title') or ('Front/tail chopped impulse' if record['request']['test_type'] == 'chopped_impulse' else 'Generator stage failure')
    healthy = record['healthy']['metrics']
    fault = record['fault']['metrics']
    def number(value):
        return 'Undefined / not established' if value is None else f'{value:,.9g}' if isinstance(value, (int, float)) else escape(value)
    rows = ''.join(f'<tr><td>{label}</td><td>{number(healthy.get(key))}</td><td>{number(fault.get(key))}</td></tr>'
                   for key, label in [('crest_kv', 'Positive crest (kV)'), ('peak_time_us', 'Time of crest (µs)'),
                                      ('front_us', 'Geometric front descriptor (µs)'), ('tail_us', 'Geometric tail descriptor (µs)'),
                                      ('minimum_kv', 'Minimum voltage (kV)'), ('reversal_pct', 'Negative reversal / positive crest (%)')])
    assumptions = ''.join(f'<li>{escape(s)}</li>' for s in record['assumptions'])
    limits = ''.join(f'<li>{escape(s)}</li>' for s in record['limitations'])
    bypass_notice = (f'<p class="notice"><strong>Bypassed capacitor charge remains unverified.</strong> '
                     f'{escape(record["energy"]["bypassed_capacitor_charge_note"])} '
                     f'{escape(record["energy"].get("fault_input_scope", ""))}</p>'
                     if record['energy'].get('bypassed_capacitor_charge_note') else '')
    # SVG uses only saved finite samples and fixed markup; labels are escaped.
    t = record['healthy']['waveform']['time_us']
    a = record['healthy']['waveform']['voltage_kv']
    b = record['fault']['waveform']['voltage_kv']
    maximum = max(max(a), max(b), 1.)
    minimum = min(min(a), min(b), 0.)
    display_end = min(t[-1], max(healthy['tail_us'] * 2.5, (record.get('event', {}).get('chop_time_us') or 0) * 1.2))
    def points(values):
        chosen = [(time, value) for time, value in zip(t, values) if time <= display_end]
        stride = max(1, len(chosen) // 2400)
        return ' '.join(f'{40 + time / display_end * 760:.4f},{30 + (maximum - value) / (maximum - minimum) * 300:.4f}' for time, value in chosen[::stride])
    plot = f'<svg viewBox="0 0 840 380" role="img" aria-label="Generated healthy and fault waveforms"><rect x="40" y="30" width="760" height="300" fill="#f3f7fa"/><polyline points="{points(a)}" fill="none" stroke="#087e8b" stroke-width="2"/><polyline points="{points(b)}" fill="none" stroke="#d45542" stroke-width="2"/><text x="40" y="355">0 µs</text><text x="680" y="355">{display_end:.4g} µs</text><text x="40" y="20">{maximum:.4g} kV</text><text x="480" y="375">Healthy: teal · Fault: coral</text></svg>'
    payload = {k: record[k] for k in ('request', 'reference', 'event', 'energy', 'checks', 'comparison')}
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)} · ImpulseTwin</title>
<style>body{{font:16px system-ui;color:#16313d;max-width:1080px;margin:36px auto;padding:24px}}h1{{font-size:30px}}.notice{{padding:18px;background:#fff4d6;border:1px solid #dec27a;border-radius:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #d6e1e6}}pre{{font-size:12px;background:#eef3f6;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere}}svg{{width:100%}}li{{margin-bottom:10px}}@media print{{body{{margin:0}}pre{{font-size:10px}}}}</style>
<h1>{escape(title)}</h1><p>Immutable experiment {escape(record['id'])} · {escape(record['created_at'])} · {escape(record['version'])}</p>
<p class="notice"><strong>Generated hypothetical circuit experiment.</strong> No laboratory validation, no hardware control, no safe-to-fire decision and no fault-waveform compliance certification. Original charging voltage is held fixed.</p>
{bypass_notice}
{plot}<table><thead><tr><th>Descriptor</th><th>Healthy circuit</th><th>Fault circuit</th></tr></thead><tbody>{rows}</tbody></table>
<p>{escape(fault['definition'])}</p><h2>Model assumptions</h2><ul>{assumptions}</ul><h2>Practical limits and person safety</h2><ul>{limits}</ul>
<h2>Exact saved settings and numerical audit</h2><pre>{escape(json.dumps(payload, indent=2, allow_nan=False))}</pre></html>'''
