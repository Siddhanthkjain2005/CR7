'use client';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {
  Activity, ArrowRight, CircleStop, Download, FileText, FlaskConical, GitCompareArrows, History, LoaderCircle, Microscope, Play, Plus, RotateCcw, Save, Sparkles, Stethoscope, Upload,
} from 'lucide-react';
import {api, apiUrl, Data, fmt, post, shortId, signed, stamp} from '@/lib/api';
import {DIAGNOSTIC_STEPS, ORIGINS, groupHypotheses, paramText, statusTone, stepStates, uploadedLabel} from '@/lib/diagnostics';
import {Badge, Empty, KindTag, Notice, PageHeading, Panel} from '../ui';
import {useWorkspace} from '../workspace';
import CaptureTimeField from '../capture-time-field';
import {captureTimeNow} from '@/lib/capture-time';
import Digitizer, {DigitizationQuality} from './digitizer';
import DiagnosticsChart, {Curve} from './diagnostics-chart';

const LAST = 'impulsetwin-last-diagnostic';
const COLOURS = {target: '#8a96a0', prediction: '#0b7d8e', uploaded: '#b8860b', fitted: '#a52f7e'};

function remember(sid: string | null) {
  try {
    if (sid) localStorage.setItem(LAST, sid);
    else localStorage.removeItem(LAST);
  } catch {
    /* storage unavailable: the session id stays in the address */
  }
}

export function WaveformDiagnostics() {
  const [view, setView] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [wanted, setWanted] = useState<{run?: string; candidate?: string}>({});

  const open = useCallback(async (sid: string) => {
    setLoading(true);
    setError('');
    try {
      const v = await api(`/api/diagnostics/${sid}`);
      setView(v);
      remember(sid);
      window.history.replaceState(null, '', `?session=${sid}`);
    } catch (e) {
      setError((e as Error).message);
      remember(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const sid = q.get('session');
    if (q.get('run')) setWanted({run: q.get('run') || undefined, candidate: q.get('candidate') || undefined});
    let last: string | null = null;
    try {
      last = localStorage.getItem(LAST);
    } catch {
      last = null;
    }
    if (sid) open(sid);
    else if (last && !q.get('run')) open(last);
    else setLoading(false);
  }, [open]);

  const accept = (v: Data) => {
    setView(v);
    remember(v.session.session_id);
    window.history.replaceState(null, '', `?session=${v.session.session_id}`);
  };
  const close = () => {
    setView(null);
    remember(null);
    window.history.replaceState(null, '', '?');
  };

  return (
    <>
      <PageHeading tag="Test setup" title="Waveform Diagnostics"
        description="Compare a recorded waveform with the circuit prediction at the settings actually fired, then look for physically meaningful explanations of any difference. Nothing here changes a saved run, a model or a calibration."
        action={view ? <button className="button" onClick={close}><Plus size={15} aria-hidden /> New diagnosis</button> : <Badge tone="amber">Diagnosis, not certification</Badge>} />
      {error && <Notice tone="red" role="alert" title="That step did not complete">{error}</Notice>}
      {loading ? (
        <p className="diag-loading" role="status"><LoaderCircle size={16} className="spin" aria-hidden /> Loading diagnosis…</p>
      ) : view ? (
        <Session view={view} onView={accept} onError={setError} />
      ) : (
        <Start wanted={wanted} onView={accept} onError={setError} onOpen={open} />
      )}
    </>
  );
}

// ------------------------------------------------------------------ start

function Start({wanted, onView, onError, onOpen}: {wanted: Data; onView: (v: Data) => void; onError: (m: string) => void; onOpen: (sid: string) => void}) {
  const w = useWorkspace();
  const [runs, setRuns] = useState<Data[] | null>(null);
  const [sessions, setSessions] = useState<Data[] | null>(null);
  const [busy, setBusy] = useState('');
  useEffect(() => {
    api('/api/runs').then(r => setRuns(r.slice(0, 8))).catch(() => setRuns([]));
    api('/api/diagnostics').then(setSessions).catch(() => setSessions([]));
  }, []);
  async function create(runId: string, candidateId = '') {
    setBusy(runId);
    try {
      onView(await post('/api/diagnostics', {run_id: runId, candidate_id: candidateId}));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  async function demo() {
    setBusy('demo');
    try {
      onView(await post('/api/diagnostics/demo', {}));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  const loaded = w.run && w.candidate;
  return (
    <div className="diag-start">
      <Panel title="1 · Choose the reference" eyebrow="The prediction the waveform is compared with">
        {wanted.run && (
          <div className="diag-choice diag-choice-primary">
            <div>
              <strong>Diagnose run {shortId(wanted.run)}</strong>
              <span>Opened from a saved result{wanted.candidate ? ` · candidate ${shortId(wanted.candidate)}` : ''}.</span>
            </div>
            <button className="button primary" disabled={!!busy} onClick={() => create(wanted.run, wanted.candidate || '')}>
              {busy === wanted.run ? <LoaderCircle size={15} className="spin" aria-hidden /> : <Stethoscope size={15} aria-hidden />} Start with this result
            </button>
          </div>
        )}
        {loaded && !wanted.run && (
          <div className="diag-choice diag-choice-primary">
            <div>
              <strong>{w.run!.inputs.impulse_type} · {fmt(w.run!.inputs.test_kv, 0)} kV · rank {w.candidate!.rank}</strong>
              <span>Loaded run {shortId(w.run!.id)} · {w.run!.profile.name} · {w.candidate!.settings.stages} stages × {fmt(w.candidate!.settings.charge_kv_stage, 1)} kV</span>
            </div>
            <button className="button primary" disabled={!!busy} onClick={() => create(w.run!.id, w.candidate!.id)}>
              {busy === w.run!.id ? <LoaderCircle size={15} className="spin" aria-hidden /> : <Stethoscope size={15} aria-hidden />} Use the loaded result
            </button>
          </div>
        )}
        <div className="diag-choice">
          <div>
            <strong>Generate a new reference</strong>
            <span>Use the existing workflow to recommend settings. On the result, choose “Diagnose this waveform”.</span>
          </div>
          <Link className="button" href="/">Configure &amp; recommend <ArrowRight size={14} aria-hidden /></Link>
        </div>
        {runs === null ? <p className="field-help">Loading saved runs…</p> : runs.length > 0 && (
          <div className="diag-runs">
            <p className="field-label">Or pick a saved run</p>
            <ul>
              {runs.map(r => (
                <li key={r.id}>
                  <button className="diag-run" disabled={!!busy} onClick={() => create(r.id)}>
                    <span><b>{r.inputs.impulse_type} · {fmt(r.inputs.test_kv, 0)} kV</b> {r.profile}</span>
                    <small>Run {shortId(r.id)} · {stamp(r.created_at)} · rank 1</small>
                    {busy === r.id && <LoaderCircle size={14} className="spin" aria-hidden />}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
      <div className="stack">
        <Panel title="Generated demonstration" action={<KindTag kind="generated">Generated</KindTag>}>
          <p className="panel-note">A rendered plot image of a simulated shot whose front resistor network is 18% below nominal. It shows the whole workflow; it is not a laboratory record and says nothing about real-machine accuracy.</p>
          <button className="button" disabled={!!busy} onClick={demo}>
            {busy === 'demo' ? <LoaderCircle size={15} className="spin" aria-hidden /> : <Sparkles size={15} aria-hidden />} Open the demonstration
          </button>
        </Panel>
        <Panel title="Saved diagnoses" action={<History size={16} aria-hidden />}>
          {sessions === null ? <p className="field-help">Loading…</p> : sessions.length ? (
            <ul className="diag-sessions">
              {sessions.slice(0, 10).map(s => (
                <li key={s.session_id}>
                  <button className="text-button" onClick={() => onOpen(s.session_id)}>{s.title}</button>
                  <small>{s.note} · revision {s.revision} · {stamp(s.updated_at)}{s.demo ? ' · demonstration' : ''}</small>
                </li>
              ))}
            </ul>
          ) : <Empty title="No diagnoses yet">Choose a reference to start; every step is saved as you go.</Empty>}
        </Panel>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ session

function Session({view, onView, onError}: {view: Data; onView: (v: Data) => void; onError: (m: string) => void}) {
  const sid = view.session.session_id;
  const states = stepStates(view);
  const ref = view.reference;
  const demo = view.session.demo || view.upload?.origin === 'demonstration';
  return (
    <>
      <div className="context-bar">
        <div>
          <strong>{view.session.title}</strong>
          <span>Diagnosis {shortId(sid)} · revision {view.session.revision} · reference run {shortId(ref.run_id)} · {ref.profile_label}</span>
        </div>
        <div className="context-actions">
          {demo && <KindTag kind="generated">Generated demonstration</KindTag>}
          {view.upload?.source === 'image' && <KindTag kind="reconstruction">Digitized from image — approximate</KindTag>}
          <a className="button small" href={apiUrl(`/api/diagnostics/${sid}/report`)} target="_blank" rel="noreferrer"><FileText size={14} aria-hidden /> Report</a>
          <a className="button small" href={apiUrl(`/api/diagnostics/${sid}/export.json`)}><Download size={14} aria-hidden /> JSON</a>
        </div>
      </div>
      <ol className="flow diag-flow" aria-label="Diagnosis steps">
        {DIAGNOSTIC_STEPS.map((s, i) => (
          <li key={s.id} className={states[s.id] === 'done' ? 'done' : states[s.id] === 'current' ? 'on' : states[s.id] === 'stale' ? 'stale' : ''}>
            <a href={`#diag-${s.id}`}><span>{i + 1}</span>{s.name}{states[s.id] === 'stale' && <em> · out of date</em>}</a>
          </li>
        ))}
      </ol>
      {Object.values(view.stale || {}).map((text, i) => <Notice key={i} tone="amber" title="Out of date">{String(text)}</Notice>)}
      <ReferenceStep view={view} onView={onView} onError={onError} />
      <UploadStep view={view} onView={onView} onError={onError} />
      <CalibrateStep view={view} onView={onView} onError={onError} />
      <CompareStep view={view} onView={onView} onError={onError} />
      <InvestigateStep view={view} onView={onView} onError={onError} />
    </>
  );
}

type StepProps = {view: Data; onView: (v: Data) => void; onError: (m: string) => void};
const FIRED: [string, string, string, number][] = [
  ['stages', 'Active stages', '', 0], ['charge_kv_stage', 'Charge per stage', 'kV', 2], ['front_r_stage', 'Front resistance / stage', 'Ω', 2],
  ['tail_r_stage', 'Tail resistance / stage', 'Ω', 2], ['load_c_pf', 'Test-object capacitance', 'pF', 1], ['divider_c_pf', 'Divider capacitance', 'pF', 1],
  ['stray_c_pf', 'Stray capacitance', 'pF', 1], ['l_uh', 'Inductance', 'µH', 2], ['efficiency', 'Loss factor', '', 3],
];

function recommendedValue(ref: Data, key: string) {
  return key === 'efficiency' ? ref.efficiency : key in ref.settings ? ref.settings[key] : ref.circuit_inputs[key];
}

function ReferenceStep({view, onView, onError}: StepProps) {
  const sid = view.session.session_id;
  const ref = view.reference;
  const af = ref.as_fired;
  const [values, setValues] = useState<Data>(() => Object.fromEntries((af?.declared_fields || []).map((k: string) => [k, k in (af.settings || {}) ? af.settings[k] : k === 'efficiency' ? af.efficiency : af.circuit_inputs[k]])));
  const [uncertain, setUncertain] = useState<string[]>(af?.uncertain_fields || []);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setValues(Object.fromEntries((af?.declared_fields || []).map((k: string) => [k, k in (af.settings || {}) ? af.settings[k] : k === 'efficiency' ? af.efficiency : af.circuit_inputs[k]])));
    setUncertain(af?.uncertain_fields || []);
  }, [af]);
  async function save(clear = false) {
    setBusy(true);
    try {
      const body = clear ? {values: {}, uncertain: []} : {values: Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '' && v !== null && v !== undefined).map(([k, v]) => [k, Number(v)])), uncertain};
      onView(await post(`/api/diagnostics/${sid}/as-fired`, body));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const m = (af?.prediction || ref.prediction).metrics;
  return (
    <Panel id="diag-reference" title="1 · Reference and settings actually fired" eyebrow={`Snapshot ${ref.snapshot_version} · ${ref.physics_version}`}>
      {ref.solver_note && <Notice tone="info">{ref.solver_note}</Notice>}
      <div className="diag-two">
        <dl className="kv">
          <div><dt>Generator</dt><dd>{ref.profile_label} · {ref.profile.max_stages} stages × {fmt(ref.profile.stage_c_uf, 3)} µF</dd></div>
          <div><dt>Request</dt><dd>{ref.impulse_type} · {fmt(ref.test_kv, 0)} kV</dd></div>
          <div><dt>Recommended setting</dt><dd>{ref.settings.stages} stages × {fmt(ref.settings.charge_kv_stage, 2)} kV · front {fmt(ref.settings.front_r_stage, 2)} Ω · tail {fmt(ref.settings.tail_r_stage, 2)} Ω per stage</dd></div>
          <div><dt>Load side</dt><dd>{fmt(ref.circuit_inputs.load_c_pf, 0)} + {fmt(ref.circuit_inputs.divider_c_pf, 0)} + {fmt(ref.circuit_inputs.stray_c_pf, 0)} pF{ref.include_base_c ? ` + ${fmt(ref.base_c_pf, 0)} pF base` : ''} = {fmt(ref.total_c_pf, 0)} pF · L {fmt(ref.circuit_inputs.l_uh, 1)} µH</dd></div>
          <div><dt>Loss factor</dt><dd>{fmt(ref.efficiency, 3)} — {ref.loss_factor.meaning}</dd></div>
          <div><dt>Topology</dt><dd>{ref.topology}</dd></div>
          <div><dt>{af ? 'Prediction at the as-fired settings' : 'Circuit prediction'}</dt><dd>Front {fmt(m.front_us, 3)} µs · tail {fmt(m.tail_us, 2)} µs · crest {fmt(m.crest_kv, 1)} kV</dd></div>
        </dl>
        <div className="diag-fired">
          <h3>Settings actually fired</h3>
          <p className="field-help">Hardware diagnosis needs the settings of this shot. Enter what you know; leave a field empty to assume the recommended value. Mark a value uncertain to let the diagnosis test it.</p>
          <div className="fired-grid">
            {FIRED.map(([k, label, unit, digits]) => (
              <div key={k} className="fired-row">
                <label className="field">
                  <span>{label}</span>
                  <span className="number-input">
                    <input type="number" step={k === 'stages' ? 1 : 'any'} placeholder={fmt(recommendedValue(ref, k), digits)} value={values[k] ?? ''}
                      onChange={e => setValues(v => ({...v, [k]: e.target.value === '' ? '' : Number(e.target.value)}))} />
                    {unit && <span>{unit}</span>}
                  </span>
                </label>
                <label className="uncertain">
                  <input type="checkbox" checked={uncertain.includes(k)} onChange={() => setUncertain(u => (u.includes(k) ? u.filter(x => x !== k) : [...u, k]))} /> uncertain
                </label>
              </div>
            ))}
          </div>
          <div className="button-row">
            <button className="button primary small" disabled={busy} onClick={() => save()}>{busy ? <LoaderCircle size={14} className="spin" aria-hidden /> : <Save size={14} aria-hidden />} Record and re-solve</button>
            {af && <button className="button small" disabled={busy} onClick={() => save(true)}><RotateCcw size={14} aria-hidden /> Clear</button>}
          </div>
          {af ? (
            <>
              <p className="field-help">{af.note} Declared: {af.declared_fields.join(', ') || 'none'}. Assumed unchanged: {af.assumed_unchanged.join(', ')}.</p>
              {af.differences.length > 0 && <p className="field-help">Differs from the recommendation: {af.differences.map((d: Data) => `${d.label} ${fmt(d.fired, 3)} (recommended ${fmt(d.recommended, 3)})`).join('; ')}.</p>}
              {af.rating_flags.map((f: Data, i: number) => <Notice key={i} tone="amber" title="Outside the generator ratings">{f.message}</Notice>)}
            </>
          ) : (
            <Notice tone="amber" title="As-fired settings not recorded">The comparison will use the recommended settings and the hardware diagnosis is limited.</Notice>
          )}
        </div>
      </div>
      <details className="disclosure open-questions" open>
        <summary>Open questions that move the prediction</summary>
        <div className="disclosure-body diag-questions">
          {ref.open_questions.map((q: Data) => <div key={q.id}><strong>{q.title}</strong><p>{q.text}</p></div>)}
        </div>
      </details>
    </Panel>
  );
}

function UploadStep({view, onView, onError}: StepProps) {
  const sid = view.session.session_id;
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<Data>({origin: '', expected_polarity: 'positive', captured_at: '', instrument: '', session_label: '', shot_label: '', notes: '',
    time_column: 'time_us', voltage_column: 'voltage_kv', time_unit: 'us', voltage_unit: 'kV', voltage_side: 'high_voltage', divider_ratio: 1, divider_ratio_source: '', baseline_kv: 0, onset_us: 0});
  useEffect(() => {
    // Client-only, once per form: keep later edits and deliberately blank times.
    const capturedAt = captureTimeNow();
    setForm(current => ({...current, captured_at: current.captured_at || capturedAt}));
  }, []);
  const [busy, setBusy] = useState(false);
  const isCsv = !!file && (/\.csv$/i.test(file.name) || file.type === 'text/csv');
  const up = view.upload;
  const [replace, setReplace] = useState(!up);
  useEffect(() => setReplace(!up), [up?.id]);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !form.origin) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append('file', file);
      Object.entries(form).forEach(([k, v]) => {
        if (String(v).trim() === '' && ['captured_at', 'instrument', 'session_label', 'shot_label', 'notes', 'divider_ratio_source'].includes(k)) return;
        body.append(k, String(v));
      });
      onView(await api(`/api/diagnostics/${sid}/upload`, {method: 'POST', body}));
      setFile(null);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel id="diag-upload" title="2 · Upload the waveform" eyebrow="Raw CSV is preferred; PNG, JPEG and WebP images are digitized locally">
      <div className="diag-two">
        {!replace ? (
          <div className="replace-box">
            <p className="panel-note">The waveform on the right is stored with its checksum. Uploading another one starts the calibration and comparison again; earlier records are kept.</p>
            <button className="button" onClick={() => setReplace(true)}><Upload size={15} aria-hidden /> Upload a different waveform</button>
          </div>
        ) : (
        <form onSubmit={send} className="trial-form">
          <label className={`drop ${file ? 'drop-has' : ''}`}>
            <Upload size={24} aria-hidden />
            <strong>{file ? file.name : 'Choose a CSV or a plot image'}</strong>
            <span>{file ? `${fmt(file.size / 1024, 1)} KB · stored unchanged with its SHA-256` : 'CSV up to 5 MB · PNG, JPEG or WebP up to 15 MB'}</span>
            <input type="file" accept=".csv,text/csv,image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] || null)} />
          </label>
          <fieldset className="purpose">
            <legend>Where does it come from?</legend>
            {ORIGINS.map(([id, label, help]) => (
              <label key={id} className="radio">
                <input type="radio" name="origin" checked={form.origin === id} onChange={() => setForm({...form, origin: id})} />
                <span>{label}<small>{help}</small></span>
              </label>
            ))}
          </fieldset>
          {isCsv && (
            <details className="disclosure" open>
              <summary>CSV columns, units and scaling</summary>
              <div className="disclosure-body">
                <div className="two-fields">
                  <label className="field"><span>Time column</span><input value={form.time_column} onChange={e => setForm({...form, time_column: e.target.value})} /></label>
                  <label className="field"><span>Voltage column</span><input value={form.voltage_column} onChange={e => setForm({...form, voltage_column: e.target.value})} /></label>
                  <label className="field"><span>Time unit</span><select value={form.time_unit} onChange={e => setForm({...form, time_unit: e.target.value})}><option value="ns">ns</option><option value="us">µs</option><option value="ms">ms</option><option value="s">s</option></select></label>
                  <label className="field"><span>Voltage unit</span><select value={form.voltage_unit} onChange={e => setForm({...form, voltage_unit: e.target.value})}><option>V</option><option>kV</option><option>MV</option></select></label>
                </div>
                <div className="purpose">
                  <span className="field-label">The values are</span>
                  <label className="radio"><input type="radio" checked={form.voltage_side === 'high_voltage'} onChange={() => setForm({...form, voltage_side: 'high_voltage', divider_ratio: 1})} /><span>High voltage at the test object</span></label>
                  <label className="radio"><input type="radio" checked={form.voltage_side === 'instrument'} onChange={() => setForm({...form, voltage_side: 'instrument'})} /><span>The instrument signal (divider output)</span></label>
                </div>
                {form.voltage_side === 'instrument' && (
                  <div className="two-fields">
                    <label className="field"><span>Divider ratio</span><input type="number" step="any" value={form.divider_ratio} onChange={e => setForm({...form, divider_ratio: Number(e.target.value)})} /></label>
                    <label className="field"><span>Source of the ratio</span><input value={form.divider_ratio_source} onChange={e => setForm({...form, divider_ratio_source: e.target.value})} /></label>
                  </div>
                )}
                <div className="two-fields">
                  <label className="field"><span>Baseline (kV)</span><input type="number" step="any" value={form.baseline_kv} onChange={e => setForm({...form, baseline_kv: Number(e.target.value)})} /></label>
                  <label className="field"><span>Impulse onset (µs)</span><input type="number" step="any" value={form.onset_us} onChange={e => setForm({...form, onset_us: Number(e.target.value)})} /></label>
                </div>
              </div>
            </details>
          )}
          <div className="two-fields">
            <label className="field"><span>Expected polarity</span>
              <select value={form.expected_polarity} onChange={e => setForm({...form, expected_polarity: e.target.value})}>
                <option value="positive">Positive</option><option value="negative">Negative</option><option value="unknown">Not known</option>
              </select>
            </label>
            <CaptureTimeField value={form.captured_at} onChange={captured_at => setForm(current => ({...current, captured_at}))} />
          </div>
          <details className="disclosure">
            <summary>Instrument, session and shot</summary>
            <div className="disclosure-body">
              <label className="field"><span>Instrument</span><input value={form.instrument} placeholder="Digitizer, divider, probe" onChange={e => setForm({...form, instrument: e.target.value})} /></label>
              <div className="two-fields">
                <label className="field"><span>Session</span><input value={form.session_label} onChange={e => setForm({...form, session_label: e.target.value})} /></label>
                <label className="field"><span>Shot</span><input value={form.shot_label} onChange={e => setForm({...form, shot_label: e.target.value})} /></label>
              </div>
              <label className="field"><span>Notes</span><textarea className="plain" rows={2} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></label>
            </div>
          </details>
          <button className="button primary full" type="submit" disabled={busy || !file || !form.origin}>
            {busy ? <LoaderCircle size={15} className="spin" aria-hidden /> : <Upload size={15} aria-hidden />} {form.origin ? 'Upload and keep the original' : 'Declare the origin to upload'}
          </button>
        </form>
        )}
        <div>
          {up ? (
            <dl className="kv">
              <div><dt>Declared origin</dt><dd>{up.origin_label} <small className="block">{up.origin_scope}</small></dd></div>
              <div><dt>File</dt><dd>{up.original_filename || 'Not recorded'} · {fmt(up.bytes / 1024, 1)} KB{up.image ? ` · ${up.image.format.toUpperCase()} ${up.image.width}×${up.image.height} px` : ''}</dd></div>
              <div><dt>SHA-256</dt><dd><code className="hash">{up.sha256}</code></dd></div>
              <div><dt>Evidence</dt><dd>{up.label}</dd></div>
              <div><dt>Session / shot</dt><dd>{up.session_label || '—'} / {up.shot_label || '—'}</dd></div>
              <div><dt>Use</dt><dd>{up.admission}</dd></div>
            </dl>
          ) : (
            <Empty title="No waveform yet">Upload the raw CSV if you have it. A photo or screenshot works too, with lower-quality evidence.</Empty>
          )}
        </div>
      </div>
    </Panel>
  );
}

function CalibrateStep({view, onView, onError}: StepProps) {
  const sid = view.session.session_id;
  const up = view.upload;
  const dg = view.digitization;
  return (
    <Panel id="diag-calibrate" title="3 · Calibrate and review" eyebrow={up?.source === 'image' ? 'Geometry, confirmed axes and the extracted trace' : 'Samples and quality'}>
      {!up ? (
        <p className="panel-note">Upload a waveform first.</p>
      ) : up.source === 'image' ? (
        <Digitizer key={up.id} sid={sid} view={view} onView={onView} onError={onError} />
      ) : dg ? (
        <DigitizationQuality record={dg} />
      ) : null}
    </Panel>
  );
}

function CompareStep({view, onView, onError}: StepProps) {
  const sid = view.session.session_id;
  const cmp = view.comparison;
  const inv = view.investigation;
  const [basis, setBasis] = useState<string>(cmp?.alignment?.basis || 'none');
  const [shift, setShift] = useState<number>(cmp?.alignment?.basis === 'manual' ? cmp.alignment.time_shift_us : 0);
  const [ranges, setRanges] = useState<string>((cmp?.excluded_ranges_us || []).map((r: number[]) => `${r[0]}–${r[1]}`).join('; '));
  const [normalized, setNormalized] = useState(false);
  const [busy, setBusy] = useState(false);
  const ready = !!view.digitization;
  async function run() {
    setBusy(true);
    try {
      const excluded = ranges.split(/[;,]/).map(s => s.trim()).filter(Boolean).map(s => s.split(/[–-]/).map(Number));
      if (excluded.some(r => r.length !== 2 || r.some(x => !Number.isFinite(x)))) throw new Error('Write excluded ranges as start–end in µs, separated by semicolons.');
      onView(await post(`/api/diagnostics/${sid}/compare`, {alignment: {basis, time_shift_us: basis === 'manual' ? shift : 0}, excluded_ranges_us: excluded}));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const curves = useMemo<Curve[]>(() => {
    if (!cmp) return [];
    const ref = view.reference;
    const prediction = (ref.as_fired?.prediction || ref.prediction).waveform;
    const norm = (v: number[]) => {
      const m = Math.max(...v);
      return v.map(x => x / (m || 1));
    };
    const list: Curve[] = [];
    if (!normalized && ref.target) list.push({id: 'target', label: 'Illustrative target shape', time_us: ref.target.time_us, values: ref.target.voltage_kv, colour: COLOURS.target, dash: 'dashed', width: 1.4, note: 'Drawn through the target values; not a prediction.'});
    list.push({id: 'prediction', label: cmp.prediction_label, time_us: prediction.time_us, values: normalized ? norm(prediction.voltage_kv) : prediction.voltage_kv, colour: COLOURS.prediction, width: 2.4,
      note: cmp.prediction_basis === 'as_fired' ? 'Re-solved at the settings actually fired.' : 'At the recommended settings (as-fired not recorded).'});
    list.push({id: 'uploaded', label: uploadedLabel(view), time_us: cmp.observed.time_us, values: normalized ? cmp.normalized_view.observed.value : cmp.observed.voltage_kv, colour: COLOURS.uploaded, width: 1.8,
      note: `Baseline ${fmt(cmp.observed.transform.baseline_kv, 2)} kV removed, time from the entered onset${cmp.alignment.time_shift_us ? ` and shifted ${signed(cmp.alignment.time_shift_us, 3)} µs (recorded)` : ''}.`});
    if (!normalized && inv && !view.stale?.investigation) {
      (inv.fitted_curves || []).slice(0, 2).forEach((c: Data, i: number) => list.push({id: `fit-${c.hypothesis_id}`, label: c.label, time_us: c.time_us, values: c.voltage_kv, colour: i ? '#c46b2c' : COLOURS.fitted, dash: 'dotted', width: 2,
        note: 'Shown only after diagnosis. An explanation, not a measurement.'}));
    }
    return list;
  }, [cmp, inv, view, normalized]);
  return (
    <Panel id="diag-compare" title="4 · Compare with the circuit prediction" eyebrow="Existing metric definitions, re-extracted from the plotted samples">
      {!ready ? <p className="panel-note">Upload and calibrate a waveform first.</p> : (
        <>
          <div className="diag-controls">
            <div className="field">
              <span>Time alignment</span>
              <div className="segmented segmented-small" role="radiogroup" aria-label="Time alignment">
                {[['none', 'None'], ['manual', 'Shift by'], ['match_30_percent', 'Match 30% crossing']].map(([id, label]) => (
                  <button key={id} type="button" role="radio" aria-checked={basis === id} className={basis === id ? 'active' : ''} onClick={() => setBasis(id)}>{label}</button>
                ))}
              </div>
            </div>
            {basis === 'manual' && <label className="field"><span>Shift (µs)</span><input type="number" step="any" value={shift} onChange={e => setShift(Number(e.target.value))} /></label>}
            <label className="field"><span>Exclude time ranges (µs)</span><input value={ranges} placeholder="e.g. 0.2–0.4; 30–35" onChange={e => setRanges(e.target.value)} /></label>
            <button className="button primary" disabled={busy} onClick={run}>{busy ? <LoaderCircle size={15} className="spin" aria-hidden /> : <GitCompareArrows size={15} aria-hidden />} {cmp ? 'Compare again' : 'Compare'}</button>
          </div>
          {cmp && (
            <>
              {view.stale?.comparison && <Notice tone="amber">{view.stale.comparison}</Notice>}
              {cmp.diagnosis_limited && <Notice tone="amber" title="Diagnosis limited">{cmp.diagnosis_limited}</Notice>}
              {cmp.polarity_issue && <Notice tone="red" title="Polarity">{cmp.polarity_issue.message}</Notice>}
              {(cmp.plausibility || []).map((p: Data, i: number) => <Notice key={i} tone="red" title="Check units first">{p.message}</Notice>)}
              <div className="diag-view-toggle">
                <label className="radio"><input type="checkbox" checked={normalized} onChange={() => setNormalized(n => !n)} />
                  <span>Normalized shape view<small>Each curve divided by its own crest. This view hides any crest mismatch; the residual plot is off while it is on.</small></span></label>
              </div>
              <DiagnosticsChart curves={curves} residual={cmp.residual} normalized={normalized} />
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Metric</th><th className="num">Uploaded</th><th className="num">Prediction</th><th className="num">Difference</th><th>Status</th></tr></thead>
                  <tbody>
                    {cmp.metrics.map((r: Data) => (
                      <tr key={r.metric}>
                        <td>{r.label} · {r.unit}</td>
                        <td className="num">{fmt(r.observed, r.unit === 'kV' ? 1 : 3)}</td>
                        <td className="num">{fmt(r.predicted, r.unit === 'kV' ? 1 : 3)}</td>
                        <td className="num">{r.difference != null ? `${signed(r.difference, r.unit === 'kV' ? 1 : 3)} (${signed(r.difference_pct, 1)}%)` : '—'}</td>
                        <td><Badge tone={statusTone(r.status)}>{r.status}</Badge>{r.reason && <small className="block">{r.reason}</small>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <dl className="kv">
                {cmp.whole_waveform?.normalized_mismatch != null && (
                  <div><dt>Whole waveform</dt><dd>Normalized mismatch {fmt(cmp.whole_waveform.normalized_mismatch, 2)} · RMS difference {fmt(cmp.whole_waveform.rms_pct_of_predicted_crest, 2)}% of the predicted crest over {cmp.whole_waveform.samples_compared} samples. <small className="block">{cmp.whole_waveform.meaning} {cmp.whole_waveform.weighting}</small></dd></div>
                )}
                <div><dt>Ringing after the crest</dt><dd>Uploaded {cmp.oscillation.observed.turns_after_peak} reversals · prediction {cmp.oscillation.predicted.turns_after_peak} · undershoot {fmt(cmp.oscillation.observed.undershoot_pct, 1)}% vs {fmt(cmp.oscillation.predicted.undershoot_pct, 1)}%</dd></div>
                <div><dt>Baseline before onset</dt><dd>{cmp.baseline.pre_onset_samples ? `${fmt(cmp.baseline.pre_onset_mean_pct, 2)}% of the predicted crest over ${cmp.baseline.pre_onset_samples} samples` : 'No samples before the onset'}</dd></div>
                <div><dt>Alignment</dt><dd>{cmp.alignment.basis === 'none' ? 'None' : `${cmp.alignment.basis.replaceAll('_', ' ')}: ${signed(cmp.alignment.time_shift_us, 3)} µs`} · {cmp.alignment.note}</dd></div>
                <div><dt>Uncertainty</dt><dd>{cmp.uncertainty_basis}</dd></div>
              </dl>
            </>
          )}
        </>
      )}
    </Panel>
  );
}

function InvestigateStep({view, onView, onError}: StepProps) {
  const router = useRouter();
  const w = useWorkspace();
  const sid = view.session.session_id;
  const cmp = view.comparison;
  const inv = view.investigation;
  const [job, setJob] = useState<Data | null>(null);
  const [explored, setExplored] = useState<Data | null>(null);
  const [exploring, setExploring] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  async function poll(id: string) {
    try {
      const j = await api(`/api/diagnostics/jobs/${id}`);
      setJob(j);
      if (j.state === 'running') timer.current = setTimeout(() => poll(id), 400);
      else {
        if (j.state === 'failed') onError(`The investigation failed: ${j.error}`);
        onView(await api(`/api/diagnostics/${sid}`));
      }
    } catch (e) {
      onError((e as Error).message);
      setJob(null);
    }
  }
  async function start() {
    setExplored(null);
    try {
      const r = await post(`/api/diagnostics/${sid}/investigate`, {});
      setJob({id: r.job_id, state: 'running', done: 0, total: 1, step: 'Starting'});
      poll(r.job_id);
    } catch (e) {
      onError((e as Error).message);
    }
  }
  async function cancel() {
    if (!job?.id) return;
    try {
      setJob(await post(`/api/diagnostics/jobs/${job.id}/cancel`, {}));
    } catch (e) {
      onError((e as Error).message);
    }
  }
  async function explore(id: string) {
    setExploring(id);
    try {
      setExplored(await post(`/api/diagnostics/${sid}/explore`, {hypothesis_id: id}));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setExploring('');
    }
  }
  const running = job?.state === 'running';
  const blocked = cmp && !cmp.quantitative_allowed;
  const groups = groupHypotheses(inv);
  const verdict = inv?.verdict;
  return (
    <>
      <Panel id="diag-investigate" title="5 · Possible causes" eyebrow="Inverse analysis with the existing circuit solver: bounded least squares from several starts">
        {!cmp ? <p className="panel-note">Compare the waveform first.</p> : (
          <>
            <div className="button-row">
              <button className="button primary" disabled={running || !!blocked || !!view.stale?.comparison} onClick={start}>
                {running ? <LoaderCircle size={15} className="spin" aria-hidden /> : <Play size={15} aria-hidden />} {inv ? 'Investigate again' : 'Investigate possible causes'}
              </button>
              {running && <button className="button" onClick={cancel}><CircleStop size={15} aria-hidden /> Cancel</button>}
              {blocked && <span className="field-help">Quantitative diagnosis is disabled for this waveform: see the comparison and quality flags. A visual comparison is still shown above.</span>}
            </div>
            {job && job.state !== 'finished' && (
              <div className="job" role="status" aria-live="polite">
                <div className="job-bar"><i style={{width: `${Math.round((100 * (job.done || 0)) / (job.total || 1))}%`}} /></div>
                <span>{job.state === 'cancelled' ? 'Cancelled — nothing was saved.' : job.state === 'failed' ? `Failed: ${job.error}` : `${job.step} (${job.done}/${job.total})`}</span>
              </div>
            )}
            {inv && (
              <>
                {view.stale?.investigation && <Notice tone="amber">{view.stale.investigation}</Notice>}
                <div className={`verdict verdict-${statusTone(verdict.label)}`}>
                  <Badge tone={statusTone(verdict.label)}>{verdict.label}</Badge>
                  <p>{verdict.message}</p>
                </div>
                {verdict.requires_review && <Notice tone="amber" title="Requires review">{verdict.requires_review}</Notice>}
                {verdict.limited && <Notice tone="amber" title="Diagnosis limited">{verdict.limited}</Notice>}
                {inv.residual_structure && <p className="field-help">After the best explanation: {inv.residual_structure.meaning}</p>}
                {groups.map(g => (
                  <div key={g.category} className="hyp-group">
                    <h3>{g.name}</h3>
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Explanation</th><th>Status</th><th className="num">Mismatch</th><th className="num">Better than prediction</th><th>Fitted values</th></tr></thead>
                        <tbody>
                          {g.items.map(h => (
                            <tr key={h.id}>
                              <td>{h.title}<small className="block">{h.group}</small></td>
                              <td><Badge tone={statusTone(h.status)}>{h.status}</Badge>{h.reason && <small className="block">{h.reason}</small>}{h.needs_more_measurement && ['Possible cause', 'Several explanations fit', 'Consistent with this waveform'].includes(h.status) && <small className="block">Additional measurement needed</small>}</td>
                              <td className="num">{fmt(h.mismatch, 2)}</td>
                              <td className="num">{h.improvement_pct != null ? `${fmt(h.improvement_pct, 0)}%` : '—'}</td>
                              <td>{Object.entries(h.parameters || {}).map(([k, v]) => paramText(k, v)).join(' · ') || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
                <p className="field-help">
                  Mismatch 1 means agreement within the stated uncertainty; baseline (no change) {fmt(inv.hypotheses.find((h: Data) => h.id === 'baseline')?.mismatch, 2)}. {inv.statement} Ranking: {inv.policy.penalty}. {inv.samples_fitted} samples, {inv.evaluations} circuit solutions, {fmt(inv.elapsed_s, 1)} s.
                </p>
              </>
            )}
          </>
        )}
      </Panel>
      <Panel id="diag-findings" title="6 · Findings, checks and export" eyebrow="For qualified laboratory staff">
        {!inv ? <p className="panel-note">Findings appear after the investigation.</p> : !inv.findings?.length ? (
          <Empty title={verdict.label === 'No change needed' ? 'Nothing to explain' : 'No explanation fits'} icon={<Microscope size={26} />}>
            {verdict.label === 'No change needed' ? 'The recording agrees with the prediction at the compared settings.' : verdict.message}
          </Empty>
        ) : (
          <div className="findings">
            {inv.findings.map((f: Data) => (
              <article key={f.hypothesis_id} className="finding">
                <header>
                  <Badge tone={statusTone(f.status)}>{f.status}</Badge>
                  <h3>{f.title}</h3>
                  <span className="finding-meta">{f.category} · {f.component_group}</span>
                </header>
                <p>{f.explanation}</p>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Quantity</th><th>Nominal</th><th>Effective (fitted)</th></tr></thead>
                    <tbody>{f.values.map((v: Data, i: number) => <tr key={i}><td>{v.quantity}</td><td>{v.nominal}</td><td>{v.effective}</td></tr>)}</tbody>
                  </table>
                </div>
                <p className="finding-fit">Mismatch {fmt(f.fit.mismatch_before, 2)} → {fmt(f.fit.mismatch_after, 2)} ({fmt(f.fit.improvement_pct, 0)}% better) with {f.fit.free_parameters} fitted quantit{f.fit.free_parameters === 1 ? 'y' : 'ies'}.</p>
                {f.supporting_evidence.length > 0 && <><h4>Supporting</h4><ul>{f.supporting_evidence.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
                {f.contradicting_evidence.length > 0 && <><h4>Against</h4><ul>{f.contradicting_evidence.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
                {f.ambiguity.length > 0 && <><h4>Ambiguity</h4><ul>{f.ambiguity.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
                <h4>How to check</h4>
                <ul>{f.verification.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
                <p className="field-help">{f.safety} {f.not_a_fault_statement}</p>
                {f.predicted_effect_if_confirmed && (
                  <p className="field-help">If confirmed, the recommended setting would give front {fmt(f.predicted_effect_if_confirmed.metrics_if_confirmed.front_us, 3)} µs, tail {fmt(f.predicted_effect_if_confirmed.metrics_if_confirmed.tail_us, 2)} µs, crest {fmt(f.predicted_effect_if_confirmed.metrics_if_confirmed.crest_kv, 1)} kV
                    {f.predicted_effect_if_confirmed.limits_if_confirmed ? ` (${f.predicted_effect_if_confirmed.limits_if_confirmed.nominal_pass ? 'inside' : 'outside'} the challenge limits)` : ''}. {f.predicted_effect_if_confirmed.note}</p>
                )}
                {['Hardware hypothesis', 'Model limitation'].includes(f.category) && (
                  <button className="button small" disabled={!!exploring || !!view.stale?.investigation} onClick={() => explore(f.hypothesis_id)}>
                    {exploring === f.hypothesis_id ? <LoaderCircle size={14} className="spin" aria-hidden /> : <Activity size={14} aria-hidden />} Explore a corrected configuration
                  </button>
                )}
              </article>
            ))}
          </div>
        )}
        {explored && (
          <div className="explored">
            <Notice tone="info" title={explored.exploration.label}>{explored.exploration.note}</Notice>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Rank</th><th>Setting</th><th className="num">Front µs</th><th className="num">Tail µs</th><th className="num">Crest kV</th><th>Limits</th></tr></thead>
                <tbody>
                  {explored.candidates.map((c: Data) => (
                    <tr key={c.id}>
                      <td>{c.rank}</td>
                      <td>{c.settings.stages} × {fmt(c.settings.charge_kv_stage, 2)} kV · {fmt(c.settings.front_r_stage, 2)} Ω / {fmt(c.settings.tail_r_stage, 2)} Ω</td>
                      <td className="num">{fmt(c.hybrid.front_us, 3)}</td><td className="num">{fmt(c.hybrid.tail_us, 2)}</td><td className="num">{fmt(c.hybrid.crest_kv, 1)}</td>
                      <td><Badge tone={c.compliance?.nominal_pass ? 'green' : 'red'}>{c.compliance?.nominal_pass ? 'Nominal pass' : 'Outside limits'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button className="button small" onClick={async () => { await w.loadRun(explored.run_id); router.push('/'); }}>
              <FlaskConical size={14} aria-hidden /> Open this hypothetical run
            </button>
          </div>
        )}
        <div className="button-row export-row">
          <a className="button" href={apiUrl(`/api/diagnostics/${sid}/report`)} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden /> Open the report</a>
          <a className="button" href={apiUrl(`/api/diagnostics/${sid}/export.json`)}><Download size={15} aria-hidden /> Download JSON</a>
          <Link className="button" href="/trial-calibrator/"><FlaskConical size={15} aria-hidden /> Compare measurement (calibration and evaluation)</Link>
        </div>
        <p className="field-help">Diagnoses never become corrections. To use a measured shot for calibration or independent evaluation, import its raw CSV on Compare measurement, where the shared admission checks apply. Image-derived samples cannot be used there.</p>
      </Panel>
    </>
  );
}
