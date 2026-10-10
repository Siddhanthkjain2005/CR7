'use client';
import {useEffect, useRef, useState} from 'react';
import Link from 'next/link';
import {ArrowRight, CheckCheck, ChevronDown, Download, FileCheck2, FlaskConical, LoaderCircle, RefreshCw, Upload} from 'lucide-react';
import {api, apiUrl, Data, fmt, human, post, shortId, signed} from '@/lib/api';
import {Badge, Empty, KindTag, Notice, PageHeading, Panel, Status} from './ui';
import {useWorkspace} from './workspace';
import EngineeringChart from './engineering-chart';
import TrialQuality from './trial-quality';
import TrialEvaluator from './trial-evaluator';
import {comparisonWaveform} from '@/lib/trial-waveform';
import {sourceLabel, trialSourceType} from './evidence-pages';
import {metricName} from './hall';

const AS_FIRED: [string, string, string][] = [
  ['stages', 'Active stages', ''],
  ['charge_kv_stage', 'Charge per stage', 'kV'],
  ['front_r_stage', 'Front resistance / stage', 'Ω'],
  ['tail_r_stage', 'Tail resistance / stage', 'Ω'],
  ['load_c_pf', 'Test-object capacitance', 'pF'],
  ['divider_c_pf', 'Divider capacitance', 'pF'],
  ['stray_c_pf', 'Stray capacitance', 'pF'],
  ['l_uh', 'Connection inductance', 'µH'],
];

export function TrialCalibrator() {
  const w = useWorkspace();
  const {run, candidate: c, trial, setTrial, calibration, setCalibration} = w;
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [result, setResult] = useState<Data | null>(null),
    [dragging, setDragging] = useState(false),
    [form, setForm] = useState<Data>({
      time_column: 'time_us',
      voltage_column: 'voltage_kv',
      time_unit: 'us',
      voltage_unit: 'kV',
      baseline_kv: 0,
      time_origin_us: 0,
      source_type: 'generated_stress_test',
      captured_at: '',
      measurement_instrument: '',
      operator_notes: '',
      capture_purpose: 'validation',
      voltage_scale: 1,
      voltage_scale_source: '',
      expected_polarity: 'auto',
      session_id: '',
      shot_label: '',
    });
  const [asFired, setAsFired] = useState<Data>({});
  const [trialRun, setTrialRun] = useState<Data | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let alive = true;
    if (trial)
      api(`/api/runs/${trial.run_id}`)
        .then(r => alive && setTrialRun(r))
        .catch(e => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [trial]);
  const trialCandidate = trialRun?.id === trial?.run_id ? trialRun?.candidates.find((x: Data) => x.id === trial?.candidate_id) : null;
  const relevant = trial && trial.run_id === run?.id && trial.candidate_id === c?.id;
  const origin = trial ? trialSourceType(trial) : 'unknown';

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !run || !c || busy) return;
    setBusy(true);
    setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('run_id', run.id);
      body.append('candidate_id', c.id);
      Object.entries(form).forEach(([k, v]) => {
        // Optional metadata is omitted when blank so the backend stores "not recorded".
        if (['captured_at', 'measurement_instrument', 'operator_notes', 'voltage_scale_source', 'session_id', 'shot_label'].includes(k) && String(v).trim() === '') return;
        body.append(k, String(v));
      });
      // As-fired values are sent only when the operator entered them.
      Object.entries(asFired).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined) body.append(`as_fired_${k}`, String(v));
      });
      setTrial(await api('/api/trials/upload', {method: 'POST', body}));
      setCalibration(null);
      setResult(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function calibrate() {
    if (!trial) return;
    setBusy(true);
    setError('');
    try {
      const cal = await post(`/api/trials/${trial.id}/calibrate`, {});
      setCalibration(cal);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function rerun() {
    if (!run || !calibration) return;
    const r = await w.optimize({...run.inputs, calibration_id: calibration.id});
    if (r) setResult(r.calibration_review || {applied: r.candidates.some((x: Data) => x.calibration)});
  }
  const pickFile = (f: File | null) => {
    setFile(f);
    setError('');
  };
  return (
    <>
      <PageHeading tag="Test setup · step 4" title="Compare measurement" description="Import a measured time–voltage capture and compare it with the saved prediction. Raw files are kept byte-for-byte; nothing is time-warped, rescaled or smoothed to hide a difference." action={<Badge tone="amber">Uploads never train the model</Badge>} />
      {(error || w.error) && (
        <Notice tone="red" role="alert" title="The backend did not accept this step">
          {error || w.error}
        </Notice>
      )}
      {!run || !c ? (
        <Empty title="Start with a saved recommendation" icon={<FlaskConical size={26} />}>
          <Link href="/">Recommend settings first</Link> so the measurement is compared with a complete, saved configuration.
        </Empty>
      ) : (
        <>
          <div className="context-bar">
            <div>
              <strong>
                {run.inputs.impulse_type} · {fmt(run.inputs.test_kv, 0)} kV · rank {c.rank}
              </strong>
              <span>
                Run {run.id} · {run.profile.name} · layout {run.inputs.layout_id}
              </span>
            </div>
            <a className="button small" href={apiUrl(`/api/runs/${run.id}/demo-waveform?candidate_id=${encodeURIComponent(c.id)}`)}>
              <Download size={14} aria-hidden /> Download generated demo CSV
            </a>
          </div>
          <ol className="flow">
            {['Import capture', 'Compare with saved prediction', 'Scoped correction', 'Independent evaluation'].map((s, i) => (
              <li key={s} className={(i === 0 && trial) || (i === 1 && trial) || (i === 2 && calibration) ? 'done' : (i === 0 && !trial) || (i === 2 && trial && !calibration) ? 'on' : ''}>
                <span>{i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <div className="trial-grid">
            <Panel title="1 · Import analyzer CSV" action={<Upload size={16} aria-hidden />}>
              <form onSubmit={upload} className="trial-form">
                <label
                  className={`drop ${dragging ? 'drop-active' : ''} ${file ? 'drop-has' : ''}`}
                  onDragOver={e => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={e => {
                    e.preventDefault();
                    setDragging(false);
                    pickFile(e.dataTransfer.files?.[0] || null);
                  }}
                >
                  <Upload size={24} aria-hidden />
                  <strong>{file ? file.name : 'Choose or drop a waveform CSV'}</strong>
                  <span>{file ? `${fmt(file.size / 1024, 1)} KB · will be stored byte-for-byte` : 'Time and voltage columns · UTF-8 · up to 5 MB'}</span>
                  <input ref={fileInput} type="file" required accept=".csv,text/csv" onChange={e => pickFile(e.target.files?.[0] || null)} />
                </label>
                <fieldset className="purpose">
                  <legend>What is this capture for?</legend>
                  <label className="radio">
                    <input type="radio" name="purpose" checked={form.capture_purpose === 'validation'} onChange={() => setForm({...form, capture_purpose: 'validation'})} />
                    <span>
                      Independent validation
                      <small>Compared with the prediction only. Never used to correct predictions.</small>
                    </span>
                  </label>
                  <label className="radio">
                    <input type="radio" name="purpose" checked={form.capture_purpose === 'calibration'} onChange={() => setForm({...form, capture_purpose: 'calibration'})} />
                    <span>
                      Calibration
                      <small>May create a scoped local correction. Excluded from independent evaluation.</small>
                    </span>
                  </label>
                </fieldset>
                <label className="field">
                  <span>Data provenance</span>
                  <select value={form.source_type} onChange={e => setForm({...form, source_type: e.target.value})}>
                    <option value="generated_stress_test">Synthetic demo / generated stress test</option>
                    <option value="measured_lab">Actual measured laboratory shot</option>
                  </select>
                  <small>Embedded generated provenance cannot be relabelled as laboratory data; the backend decides the final classification.</small>
                </label>
                <div className="two-fields">
                  {[
                    ['time_column', 'Time column'],
                    ['voltage_column', 'Voltage column'],
                  ].map(([k, label]) => (
                    <label key={k} className="field">
                      <span>{label}</span>
                      <input required value={form[k]} onChange={e => setForm({...form, [k]: e.target.value})} />
                    </label>
                  ))}
                </div>
                <div className="two-fields">
                  <label className="field">
                    <span>Time unit</span>
                    <select value={form.time_unit} onChange={e => setForm({...form, time_unit: e.target.value})}>
                      {[
                        ['ns', 'ns'],
                        ['us', 'µs'],
                        ['ms', 'ms'],
                        ['s', 's'],
                      ].map(([u, t]) => (
                        <option key={u} value={u}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Voltage unit</span>
                    <select value={form.voltage_unit} onChange={e => setForm({...form, voltage_unit: e.target.value})}>
                      {['V', 'kV', 'MV'].map(u => (
                        <option key={u}>{u}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <details className="disclosure" open={form.baseline_kv !== 0 || form.time_origin_us !== 0}>
                  <summary>
                    Preprocessing
                    <small>
                      Baseline {fmt(form.baseline_kv, 2)} kV · onset {fmt(form.time_origin_us, 2)} µs
                    </small>
                    <ChevronDown size={16} className="chev" aria-hidden />
                  </summary>
                  <div className="disclosure-body">
                    <label className="field">
                      <span>Baseline to subtract (kV)</span>
                      <input type="number" step="any" value={form.baseline_kv} onChange={e => setForm({...form, baseline_kv: Number(e.target.value)})} />
                    </label>
                    <label className="field">
                      <span>Physical impulse onset (µs)</span>
                      <input type="number" step="any" value={form.time_origin_us} onChange={e => setForm({...form, time_origin_us: Number(e.target.value)})} />
                      <small>Explicit physical origin for time-to-peak / half extraction; not inferred from the first sample.</small>
                    </label>
                    <div className="two-fields">
                      <label className="field">
                        <span>Voltage scale factor</span>
                        <input type="number" step="any" min={0} value={form.voltage_scale} onChange={e => setForm({...form, voltage_scale: Number(e.target.value)})} />
                        <small>Divider ratio applied after the unit, e.g. 1000 when the file holds divider-output volts.</small>
                      </label>
                      <label className="field">
                        <span>Expected polarity</span>
                        <select value={form.expected_polarity} onChange={e => setForm({...form, expected_polarity: e.target.value})}>
                          <option value="auto">Detect from the capture</option>
                          <option value="positive">Positive</option>
                          <option value="negative">Negative</option>
                        </select>
                        <small>A mismatch is reported, never silently flipped.</small>
                      </label>
                    </div>
                    {Number(form.voltage_scale) !== 1 && (
                      <label className="field">
                        <span>Source of the scale factor</span>
                        <input required value={form.voltage_scale_source} placeholder="Divider calibration certificate, date" onChange={e => setForm({...form, voltage_scale_source: e.target.value})} />
                      </label>
                    )}
                  </div>
                </details>
                <details className="disclosure">
                  <summary>
                    Capture metadata
                    <small>{form.captured_at || form.measurement_instrument ? 'Recorded' : 'Optional · not recorded'}</small>
                    <ChevronDown size={16} className="chev" aria-hidden />
                  </summary>
                  <div className="disclosure-body">
                    <label className="field">
                      <span>Captured at (ISO 8601)</span>
                      <input value={form.captured_at} placeholder="2026-10-10T14:05:00+05:30" onChange={e => setForm({...form, captured_at: e.target.value})} />
                    </label>
                    <label className="field">
                      <span>Measurement instrument</span>
                      <input value={form.measurement_instrument} placeholder="Digitizer, divider and probe identity" onChange={e => setForm({...form, measurement_instrument: e.target.value})} />
                    </label>
                    <div className="two-fields">
                      <label className="field">
                        <span>Session</span>
                        <input value={form.session_id} placeholder="Test session or campaign" onChange={e => setForm({...form, session_id: e.target.value})} />
                      </label>
                      <label className="field">
                        <span>Shot</span>
                        <input value={form.shot_label} placeholder="Shot number" onChange={e => setForm({...form, shot_label: e.target.value})} />
                      </label>
                    </div>
                    <label className="field">
                      <span>Operator notes</span>
                      <textarea className="plain" rows={2} value={form.operator_notes} onChange={e => setForm({...form, operator_notes: e.target.value})} />
                    </label>
                  </div>
                </details>
                <details className="disclosure">
                  <summary>
                    Settings actually fired
                    <small>{Object.values(asFired).some(v => v !== '' && v != null) ? 'Recorded · prediction re-simulated' : 'Optional · same as recommended'}</small>
                    <ChevronDown size={16} className="chev" aria-hidden />
                  </summary>
                  <div className="disclosure-body">
                    <p className="field-help">Fill in only what differed from the recommendation. The unchanged circuit model is re-run at these settings so the comparison is like-for-like; no measured data enters the model.</p>
                    <div className="two-fields">
                      {AS_FIRED.map(([k, label, unit]) => (
                        <label key={k} className="field">
                          <span>{label}</span>
                          <span className="number-input">
                            <input
                              type="number"
                              step={k === 'stages' ? 1 : 'any'}
                              placeholder={fmt(c && k in c.settings ? c.settings[k] : run.inputs[k], k === 'stages' ? 0 : 2)}
                              value={asFired[k] ?? ''}
                              onChange={e => setAsFired({...asFired, [k]: e.target.value === '' ? '' : Number(e.target.value)})}
                            />
                            {unit && <span>{unit}</span>}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                </details>
                <button className="button primary full" type="submit" disabled={busy || !file}>
                  {busy ? <LoaderCircle size={16} className="spin" aria-hidden /> : <FileCheck2 size={16} aria-hidden />} Extract and compare waveform
                </button>
              </form>
            </Panel>
            <div className="stack">
              <Panel title="2 · Captured versus predicted" action={trial && <KindTag kind={origin === 'measured_lab' ? 'measured' : origin === 'synthetic_benchmark' ? 'synthetic' : origin === 'generated_demo' ? 'generated' : 'unknown'}>{sourceLabel(origin)}</KindTag>}>
                {trial ? (
                  <>
                    {!relevant && (
                      <Notice tone="info">
                        This comparison keeps the original trial run {shortId(trial.run_id)} and its hardware settings. The selected run or candidate has changed.
                      </Notice>
                    )}
                    <EngineeringChart
                      waveform={trialCandidate?.waveform}
                      physics={trialCandidate?.physics_waveform}
                      target={trialRun?.target_waveform}
                      predictionLabel={trialRun?.inputs.solver === 'circuit' ? 'Circuit prediction' : 'Original prediction'}
                      measured={{...comparisonWaveform(trial), kind: origin}}
                      measuredLabel={`Uploaded trial · ${sourceLabel(origin).toLowerCase()}`}
                      height={320}
                    />
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Metric</th>
                            <th className="num">Physics</th>
                            <th className="num">Saved prediction</th>
                            {trial.as_fired && <th className="num">Prediction at as-fired settings</th>}
                            <th className="num">Measured</th>
                            <th className="num">Measured − saved</th>
                          </tr>
                        </thead>
                        <tbody>
                          {['front_us', 'tail_us', 'crest_kv'].map((k, i) => (
                            <tr key={k}>
                              <td>
                                {metricName(i, trialRun?.inputs?.impulse_type)} · {i === 2 ? 'kV' : 'µs'}
                              </td>
                              <td className="num">{fmt(trial.physics?.[k], 3)}</td>
                              <td className="num">{fmt(trial.predicted?.[k], 3)}</td>
                              {trial.as_fired && <td className="num">{fmt(trial.as_fired.prediction?.[k], 3)}</td>}
                              <td className="num">{fmt(trial.measured?.[k], 3)}</td>
                              <td className="num">{signed(trial.bias?.[i], 4)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="panel-note">
                      {trial.processing?.steps?.join(' · ')}. Detected polarity: {trial.processing?.polarity}. The plot shows baseline-corrected positive magnitude and time from the entered physical onset; the original CSV is preserved (SHA-256 <code>{trial.raw_sha256}</code>).
                    </p>
                    <dl className="kv capture-meta">
                      <div>
                        <dt>Original file</dt>
                        <dd>{trial.original_filename || <span className="unrecorded">Not recorded</span>}</dd>
                      </div>
                      <div>
                        <dt>Captured at</dt>
                        <dd>{trial.captured_at || <span className="unrecorded">Not recorded</span>}</dd>
                      </div>
                      <div>
                        <dt>Instrument</dt>
                        <dd>{trial.measurement_instrument || <span className="unrecorded">Not recorded</span>}</dd>
                      </div>
                      <div>
                        <dt>Operator notes</dt>
                        <dd>{trial.operator_notes || <span className="unrecorded">Not recorded</span>}</dd>
                      </div>
                      <div>
                        <dt>Capture purpose</dt>
                        <dd>{trial.capture_purpose === 'validation' ? 'Independent validation (never used for correction)' : trial.capture_purpose === 'calibration' ? 'Calibration (excluded from independent evaluation)' : 'Not recorded'}</dd>
                      </div>
                      <div>
                        <dt>Session / shot</dt>
                        <dd>{trial.session_id || trial.shot_label ? `${trial.session_id || '—'} / ${trial.shot_label || '—'}` : <span className="unrecorded">Not recorded</span>}</dd>
                      </div>
                      {trial.instrument && (
                        <div>
                          <dt>Instrument scale and polarity</dt>
                          <dd>
                            ×{fmt(trial.instrument.voltage_scale, 4)}
                            {trial.instrument.voltage_scale_source ? ` (${trial.instrument.voltage_scale_source})` : ''} · detected {trial.instrument.detected_polarity}
                            {trial.instrument.expected_polarity !== 'auto' ? `, expected ${trial.instrument.expected_polarity}` : ''}
                          </dd>
                        </div>
                      )}
                      {trial.as_fired && (
                        <div>
                          <dt>As-fired changes</dt>
                          <dd>{trial.as_fired.changed_fields.join(', ')} · {trial.as_fired.note}</dd>
                        </div>
                      )}
                      {trial.compliance && (
                        <div>
                          <dt>Provisional comparison with saved limits</dt>
                          <dd>
                            <Status value={trial.compliance.status} /> {trial.compliance.provisional ? <small className="block">Provisional until capture resolution is reviewed.</small> : null}
                          </dd>
                        </div>
                      )}
                    </dl>
                    <TrialQuality trial={trial} />
                  </>
                ) : (
                  <Empty title="Your next shot completes the picture">Upload actual analyzer data, or use the clearly labelled generated demo CSV to rehearse the workflow.</Empty>
                )}
              </Panel>
              <Panel title="3 · Apply a local correction" action={<Badge tone="cyan">Scoped</Badge>}>
                {trial ? (
                  <>
                    <p className="panel-note">A single shot updates only the matching profile, layout, solver and hardware settings with inputs within 1%. Transfer from reduced voltage to full voltage is not inferred.</p>
                    {!calibration ? (
                      <button className="button" disabled={busy || trial.quality?.calibration_allowed === false || trial.capture_purpose === 'validation'} onClick={calibrate}>
                        {busy ? <LoaderCircle className="spin" size={15} aria-hidden /> : <CheckCheck size={15} aria-hidden />}{' '}
                        {trial.capture_purpose === 'validation' ? 'Validation captures are never used for correction' : trial.quality?.calibration_allowed === false ? 'Review capture before calibration' : 'Create scoped calibration'}
                      </button>
                    ) : (
                      <>
                        <div className="calibration-ready">
                          <CheckCheck size={20} aria-hidden />
                          <div>
                            <strong>Calibration {calibration.id} saved</strong>
                            <span>{human(calibration.source_type)} · production model unchanged</span>
                          </div>
                        </div>
                        <p className="panel-note">{calibration.limitation}</p>
                        <button className="button primary" disabled={w.busy} onClick={rerun}>
                          {w.busy ? <LoaderCircle className="spin" size={15} aria-hidden /> : <RefreshCw size={15} aria-hidden />} Re-optimize with this calibration
                        </button>
                      </>
                    )}
                    {result && (
                      <div className="calibration-result">
                        <Badge tone={result.applied ? 'cyan' : 'amber'}>{result.applied ? 'Local correction evaluated' : 'Scope did not match'}</Badge>
                        <p>{result.reason || result.next_adjustment_note || result.message || result.limitation || 'Inspect the updated run and matched-setting review below. The corrected candidate may rank outside the top five.'}</p>
                        {result.settings && (
                          <div className="calibration-setting">
                            <strong>
                              {result.settings.stages} stages × {fmt(result.settings.charge_kv_stage, 2)} kV / stage
                            </strong>
                            <span>
                              Front {fmt(result.settings.front_r_stage, 2)} Ω / stage · Tail {fmt(result.settings.tail_r_stage, 2)} Ω / stage
                            </span>
                            <small>{result.retained_in_top_five ? 'Matched hardware remains in top five.' : 'Matched hardware is retained for review outside the top five.'}</small>
                          </div>
                        )}
                        {result.corrected_prediction && (
                          <div className="table-wrap">
                            <table>
                              <thead>
                                <tr>
                                  <th>Metric</th>
                                  <th className="num">Original model</th>
                                  <th className="num">Total correction</th>
                                  <th className="num">Corrected prediction</th>
                                </tr>
                              </thead>
                              <tbody>
                                {['front_us', 'tail_us', 'crest_kv'].map((k, i) => (
                                  <tr key={k}>
                                    <td>{['Front / peak µs', 'Tail µs', 'Crest kV'][i]}</td>
                                    <td className="num">{fmt(trial.calibration_lineage?.base_prediction?.[k] ?? calibration?.calibration_lineage?.base_prediction?.[k] ?? trial.predicted[k], 3)}</td>
                                    <td className="num">{signed(result.correction?.[i], 3)}</td>
                                    <td className="num">
                                      <strong>{fmt(result.corrected_prediction[k], 3)}</strong>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        {result.compliance && (
                          <>
                            <p className="crosscheck-status">
                              Corrected model compliance <Status value={result.compliance.status} />
                            </p>
                            {!result.uncertainty?.coverage_claim && (
                              <Notice tone="info">
                                Interval coverage is unvalidated after one-shot calibration. Any ROBUST PASS describes containment within the stated model envelope, not a calibrated probability of laboratory success.
                              </Notice>
                            )}
                          </>
                        )}
                        <details className="source-details">
                          <summary>Matched-setting calibration review</summary>
                          <pre className="code-data">{JSON.stringify(result, null, 2)}</pre>
                        </details>
                        <Link href="/" className="button text-button">
                          Inspect updated recommendation <ArrowRight size={14} aria-hidden />
                        </Link>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="panel-note">Upload and review a waveform to enable calibration. No production model is retrained by this workflow.</p>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}
      <TrialEvaluator refreshToken={trial?.id} />
    </>
  );
}
