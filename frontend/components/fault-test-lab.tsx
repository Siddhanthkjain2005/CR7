'use client';

import {useEffect, useRef, useState} from 'react';
import {Activity, ArrowRight, Check, ChevronDown, CircleHelp, Download, FlaskConical, Layers3, LoaderCircle, Play, RotateCcw, Scissors, ShieldAlert, TriangleAlert} from 'lucide-react';
import {Data, fmt, isNum, shortId, signed, stamp} from '@/lib/api';
import {useQuietMotion} from '@/lib/motion';
import {ChopMode, FaultReference, FaultRequest, FaultResult, FaultTestType, StageFailureMode, faultExportUrl, faultRequestKey, faultRequestProblems, faultSnapshotKey, loadFaultReference, runFaultTest, selectedStageIndices} from '@/lib/fault-tests';
import EngineeringChart from './engineering-chart';

export interface FaultTestLabProps {run: Data | null; candidate: Data | null; draftEdited?: boolean;}

function numericInput(value: string): number {return value.trim() === '' ? Number.NaN : Number(value);}
function quantities(value: unknown, unit: string, digits = 3): string {return isNum(value) ? `${fmt(value, digits)} ${unit}` : 'Not available';}
function list(value: unknown): string[] {return Array.isArray(value) ? value.filter(v => typeof v === 'string') : [];}

function StageStack({count, selected, mode, fraction, interactive, disabled, onSelect}: {
  count: number; selected: number[]; mode: StageFailureMode; fraction: number; interactive: boolean; disabled: boolean; onSelect: (stage: number) => void;
}) {
  return <div className="ft-stage-stack">
    <div className="ft-stage-heading"><Layers3 size={16} aria-hidden /><strong>Saved generator stack</strong><span>Conceptual schematic</span></div>
    <div className="ft-stage-grid" role={interactive ? 'group' : undefined} aria-label={interactive ? 'Select stages for the generated fault' : 'Saved healthy stage configuration'}>
      {Array.from({length: count}, (_, index) => index + 1).reverse().map(stage => {
        const altered = interactive && selected.includes(stage);
        const text = altered ? mode === 'bypassed' ? 'Bypassed in model' : `${fmt(fraction * 100, 0)}% charge` : 'Saved charge';
        return <button type="button" key={stage} className={`ft-stage ${altered ? 'altered' : ''} ${altered && mode === 'bypassed' ? 'bypassed' : ''}`} aria-pressed={altered} disabled={disabled || !interactive} aria-label={`Stage ${stage}, ${text}. ${interactive ? 'Toggle fault selection.' : 'Healthy reference.'}`} onClick={() => onSelect(stage)}>
          <span className="ft-stage-id">S{stage}</span><span className="ft-stage-capacitor" aria-hidden><i /><i /></span><span className="ft-stage-state">{text}</span>{altered && <Check size={13} aria-hidden />}
        </button>;
      })}
    </div>
    <p>Stage numbers identify your selection. The lumped model combines their contributions; it cannot distinguish a fault near the top from one near the bottom.</p>
  </div>;
}

function Metrics({result}: {result: FaultResult}) {
  const chopped = result.request.test_type === 'chopped_impulse';
  const healthy = result.healthy.metrics, fault = result.fault.metrics;
  const rows: [string, string, string][] = [
    ['Positive crest', quantities(healthy.crest_kv, 'kV', 2), quantities(fault.crest_kv, 'kV', 2)],
    ['Time of positive peak · from trigger', quantities(healthy.peak_time_us, 'µs'), quantities(fault.peak_time_us, 'µs')],
    ['Front metric', quantities(healthy.front_us, 'µs'), `${quantities(fault.front_us, 'µs')}${chopped && isNum(fault.front_us) ? ' · descriptor' : ''}`],
    ['Time to half-value metric', quantities(healthy.tail_us, 'µs'), `${quantities(fault.tail_us, 'µs')}${chopped && isNum(fault.tail_us) ? ' · descriptor' : ''}`],
    ['Minimum voltage', quantities(healthy.minimum_kv, 'kV', 2), quantities(fault.minimum_kv, 'kV', 2)],
    ['Voltage reversal · relative to positive crest', quantities(healthy.reversal_pct, '%', 2), quantities(fault.reversal_pct, '%', 2)],
  ];
  return <div className="ft-metric-table-wrap"><table className="ft-metric-table"><caption>Extracted from each simulated waveform at the same saved charge</caption><thead><tr><th scope="col">Quantity</th><th scope="col">Healthy circuit</th><th scope="col">Generated fault</th></tr></thead><tbody>{rows.map(([label, baseline, changed]) => <tr key={label}><th scope="row">{label}</th><td>{baseline}</td><td>{changed}</td></tr>)}</tbody></table>
    {chopped && <p className="ft-metric-boundary"><CircleHelp size={15} aria-hidden />Chopping changes the pulse definition. A collapse or half-crossing after the chop is not a standard full-impulse tail metric. Unavailable metrics stay unavailable.</p>}
    <p className="ft-technical-note"><strong>Fault metric definition:</strong> {fault.definition || 'Definition not recorded.'} {fault.front_tail_status || ''}</p>
  </div>;
}

function ResultPanel({result, front, setFront}: {result: FaultResult; front: boolean; setFront: (value: boolean) => void}) {
  const chopped = result.request.test_type === 'chopped_impulse';
  const stageRequest = result.request.test_type === 'stage_failure' ? result.request : null;
  const bypassed = stageRequest?.failure_mode === 'bypassed';
  const event = result.event;
  const healthy = result.healthy.metrics, fault = result.fault.metrics;
  const end = Math.max(result.healthy.waveform.time_us.at(-1) || 0, result.fault.waveform.time_us.at(-1) || 0);
  const healthyPeak = isNum(healthy.peak_time_us) ? healthy.peak_time_us : 0;
  const faultPeak = isNum(fault.peak_time_us) ? fault.peak_time_us : 0;
  const detailEnd = chopped ? Math.min(end, Math.max(healthyPeak * 2.5, (event.chop_time_us || 0) * 1.35)) : Math.min(end, Math.max(healthyPeak, faultPeak) * 3);
  return <div className="ft-result">
    <div className="ft-result-heading"><div><span className="ft-result-eyebrow">Saved generated experiment · {shortId(result.id)}</span><h3>{chopped ? `${event.classification === 'front' ? 'Front' : 'Tail'}-chopped lightning impulse` : stageRequest?.failure_mode === 'bypassed' ? 'Deliberately bypassed stage scenario' : 'Reduced-charge conducting stage scenario'}</h3><p>{chopped ? `An assumed shunt closes at ${fmt(event.chop_time_us, 4)} µs after the trigger.` : `Stages ${stageRequest?.stage_indices.join(', ') || 'not recorded'} are changed in the model. The remaining stages keep their saved charge.`}</p></div><span className="ft-generated"><FlaskConical size={13} aria-hidden />Generated · not measured</span></div>
    <div className="ft-impact-grid">
      <div><span>Fault positive crest</span><strong>{fmt(fault.crest_kv, 2)} <small>kV</small></strong><p>Healthy: {fmt(healthy.crest_kv, 2)} kV</p></div>
      <div><span>Change in crest</span><strong>{signed(result.comparison.crest_change_pct, 2)} <small>%</small></strong><p>At the same saved charging voltage</p></div>
      <div><span>{chopped ? 'Voltage immediately before chop' : bypassed ? 'Energy in contributing stages' : 'Fault modeled input energy'}</span><strong>{chopped ? fmt(event.voltage_at_chop_kv, 2) : fmt(result.energy.fault_input_kj, 3)} <small>{chopped ? 'kV' : 'kJ'}</small></strong><p>{chopped ? `Healthy peak at ${fmt(event.baseline_peak_time_us, 4)} µs` : `Healthy: ${fmt(result.energy.healthy_input_kj, 3)} kJ`}</p></div>
      <div><span>Negative voltage reversal</span><strong>{fmt(fault.reversal_pct, 2)} <small>%</small></strong><p>Relative to the fault’s positive crest</p></div>
    </div>
    {bypassed && <div className="ft-notice warning" role="note"><ShieldAlert size={17} aria-hidden /><p><strong>Excluded capacitors may still hold charge.</strong> The energy above counts only the stages contributing to this modeled pulse. Energy remaining in physically excluded capacitors is unverified; this result does not mean they are discharged or safe to approach.</p></div>}
    <div className="ft-chart-shell">
      <div className="ft-chart-heading"><span><Activity size={15} aria-hidden />Healthy and fault · unchanged charge</span><div className="segmented" aria-label="Fault waveform zoom"><button type="button" className={!front ? 'active' : ''} aria-pressed={!front} onClick={() => setFront(false)}>Full wave</button><button type="button" className={front ? 'active' : ''} aria-pressed={front} onClick={() => setFront(true)}>{chopped ? 'Chop / front detail' : 'Front / peak detail'}</button></div></div>
      <EngineeringChart waveform={result.fault.waveform} physics={result.healthy.waveform} predictionLabel="Generated fault · circuit" physicsLabel="Healthy · same saved circuit" theme="hall" height={310} timeMaxUs={end} front={front} frontMaxUs={detailEnd} cursorUs={chopped ? event.chop_time_us : null} showKey={false} />
      <div className="ft-chart-key"><span><i className="ft-trace-healthy" aria-hidden />Healthy circuit · green dotted</span><span><i className="ft-trace-fault" aria-hidden />Generated fault · cyan solid</span>{chopped && <span><i className="ft-trace-event" aria-hidden />Chop instant · violet marker</span>}</div>
      <p>Exact simulated samples, with no smoothing or target-crest rescaling. Both curves use the saved configuration and the same declared circuit assumptions.</p>
    </div>
    <Metrics result={result} />
    <div className="ft-experiment-details">
      <div className="ft-event-facts"><h4>{chopped ? 'Event and energy audit' : 'Stage contribution audit'}</h4><dl>{(chopped ? [
        ['Calculated event type', event.classification === 'front' ? 'Before the healthy peak · front chop' : 'After the healthy peak · tail chop'],
        ['Time after trigger', quantities(event.chop_time_us, 'µs', 4)],
        ['Peak simulated shunt current', quantities(event.shunt_peak_current_a, 'A', 2)],
        ['Maximum |di/dt| in assumed shunt', quantities(event.max_shunt_abs_di_dt_a_per_us, 'A/µs', 2)],
        ['Dissipated in assumed shunt', quantities(result.energy.shunt_dissipated_kj, 'kJ', 6)],
        ['Energy remaining at simulation end', quantities(result.energy.remaining_energy_kj, 'kJ', 6)],
      ] : [
        ['Modeled conducting stages · healthy → fault', `${event.healthy_stage_count ?? '—'} → ${event.fault_stage_count ?? '—'}`],
        ['Changed stage identities', stageRequest?.stage_indices.map(stage => `S${stage}`).join(', ') || 'Not recorded'],
        ['Charge retained by a selected stage', quantities(stageRequest ? stageRequest.remaining_charge_fraction * 100 : null, '%', 1)],
        ['Fault / healthy source voltage ratio', quantities(event.source_voltage_ratio, '×', 6)],
        ['Healthy modeled input energy', quantities(result.energy.healthy_input_kj, 'kJ', 6)],
        [bypassed ? 'Energy in contributing stages' : 'Fault modeled input energy', quantities(result.energy.fault_input_kj, 'kJ', 6)],
      ]).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p>{result.energy.definition || ''}</p></div>
      <div className="ft-reading"><h4>How to read this experiment</h4>{chopped ? <><p>The curve follows the healthy circuit up to the selected instant. The added shunt then redirects current and discharges the load-side capacitance.</p><p>With inductance, voltage cannot vanish instantaneously. The post-chop transient can ring and reverse polarity. Its shape depends on the assumed shunt, not only on the chop time.</p><p>Reported shunt current is a model output. It is not a current rating or a construction recommendation.</p></> : stageRequest?.failure_mode === 'bypassed' ? <><p>A bypass changes the number of contributing stages, the erected equivalent capacitance and the series-model resistance totals. The pulse can change shape as well as crest.</p><p>This is a deliberate topology change. It is not a model of a gap remaining open, flashover or unsafe hardware rewiring.</p></> : <><p>Each selected stage retains only the declared fraction of its original charge, but the full stack is assumed erected and conducting. The stage capacitors and resistor totals remain in the model.</p><p>That explains why lost charge can mainly reduce amplitude in this simplified circuit. The shape may remain the same. A real gap misfire requires a different, distributed switching model.</p></>}<div className="ft-fixed-note"><Check size={14} aria-hidden />No new optimization, ML correction or automatic charge increase is performed.</div></div>
    </div>
    <details className="ft-audit"><summary><ChevronDown size={15} aria-hidden />Model assumptions, numerical checks and saved provenance</summary><div className="ft-audit-grid"><div><h4>Assumptions</h4><ul>{list(result.assumptions).map((item, index) => <li key={index}>{item}</li>)}</ul><h4>Practical limitations</h4><ul>{list(result.limitations).map((item, index) => <li key={index}>{item}</li>)}</ul></div><div><h4>Saved reference</h4><p>{result.reference.solver_note}</p><dl><div><dt>Simulation version</dt><dd>{result.version}</dd></div><div><dt>Saved experiment</dt><dd>{stamp(result.created_at)}</dd></div><div><dt>Reference snapshot SHA-256</dt><dd className="ft-checksum">{result.reference.snapshot_sha256 || 'Not recorded'}</dd></div></dl><h4>Numerical audit · model consistency only</h4><pre>{JSON.stringify(result.checks, null, 2)}</pre><p>These checks examine the numerical solution. They do not establish laboratory accuracy or IEC certification.</p></div></div></details>
    <div className="ft-export"><div><strong>Keep the complete experiment</strong><span>Both curves, event inputs, assumptions and the saved reference are retained.</span></div><nav aria-label="Export generated fault experiment"><a className="button small" href={faultExportUrl(result.id, 'json')}><Download size={14} aria-hidden />Audit JSON</a><a className="button small" href={faultExportUrl(result.id, 'csv')}><Download size={14} aria-hidden />Waveform CSV</a><a className="button small" href={faultExportUrl(result.id, 'report')} target="_blank" rel="noreferrer"><Download size={14} aria-hidden />HTML report</a></nav></div>
  </div>;
}

function FaultWorkspace({run, candidate, draftEdited}: {run: Data; candidate: Data; draftEdited: boolean}) {
  const quiet = useQuietMotion();
  const [testType, setTestType] = useState<FaultTestType>('chopped_impulse');
  const [chopMode, setChopMode] = useState<ChopMode>('tail');
  const [failureMode, setFailureMode] = useState<StageFailureMode>('uncharged_conducting');
  const [stageIndices, setStageIndices] = useState<number[]>([1]);
  const [fraction, setFraction] = useState('0');
  const [timeUs, setTimeUs] = useState('');
  const [shuntR, setShuntR] = useState('10');
  const [shuntL, setShuntL] = useState('1');
  const [reference, setReference] = useState<FaultReference | null>(null);
  const [referenceBusy, setReferenceBusy] = useState(true);
  const [referenceError, setReferenceError] = useState('');
  const [referenceReload, setReferenceReload] = useState(0);
  const [savedResult, setSavedResult] = useState<{key: string; data: FaultResult} | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [front, setFront] = useState(false);
  const requestNumber = useRef(0), requestAbort = useRef<AbortController | null>(null);
  const stageCount = candidate.settings.stages as number;
  const selected = selectedStageIndices(stageIndices, stageCount);
  const request: FaultRequest = testType === 'chopped_impulse'
    ? {test_type: testType, chop_mode: chopMode, chop_time_us: numericInput(timeUs), shunt_r_ohm: numericInput(shuntR), shunt_l_uh: numericInput(shuntL)}
    : {test_type: testType, failure_mode: failureMode, stage_indices: selected, remaining_charge_fraction: failureMode === 'bypassed' ? 0 : numericInput(fraction)};
  const controlKey = faultRequestKey(request);
  const currentKey = useRef(controlKey); currentKey.current = controlKey;
  const staleRef = useRef(draftEdited); staleRef.current = draftEdited;
  const problems = reference ? faultRequestProblems(request, reference, stageCount) : [];
  const result = !draftEdited && savedResult?.key === controlKey ? savedResult.data : null;

  useEffect(() => {
    if (draftEdited) {setReferenceBusy(false); return;}
    const controller = new AbortController();
    setReferenceBusy(true); setReferenceError(''); setReference(null);
    loadFaultReference(run.id, candidate.id, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setReference(value);
      setTimeUs(String(value.defaults.tail_chop_time_us));
      setChopMode('tail'); setShuntR(String(value.defaults.shunt_r_ohm)); setShuntL(String(value.defaults.shunt_l_uh));
      if (!value.supported.chopped_impulse && value.supported.stage_failure) setTestType('stage_failure');
    }).catch(reason => {if (!controller.signal.aborted) setReferenceError(reason.message || 'The saved circuit reference could not be loaded.');})
      .finally(() => {if (!controller.signal.aborted) setReferenceBusy(false);});
    return () => controller.abort();
  }, [run.id, candidate.id, referenceReload, draftEdited]);
  useEffect(() => {
    requestNumber.current++; requestAbort.current?.abort(); setBusy(false); setError(''); setSavedResult(null);
  }, [controlKey, draftEdited]);
  useEffect(() => () => {requestNumber.current++; requestAbort.current?.abort();}, []);

  const selectTest = (value: FaultTestType) => {setTestType(value); setFront(false);};
  const selectChop = (value: ChopMode) => {setChopMode(value); if (reference) setTimeUs(String(value === 'front' ? reference.defaults.front_chop_time_us : reference.defaults.tail_chop_time_us));};
  const simulate = async () => {
    if (!reference || referenceBusy || draftEdited || problems.length) return;
    const ticket = ++requestNumber.current;
    const controller = new AbortController(); requestAbort.current?.abort(); requestAbort.current = controller;
    const submittedKey = controlKey;
    setBusy(true); setError('');
    try {
      const value = await runFaultTest(run.id, candidate.id, request, controller.signal);
      if (!controller.signal.aborted && ticket === requestNumber.current && currentKey.current === submittedKey && !staleRef.current)
        setSavedResult({key: submittedKey, data: value});
    } catch (reason) {if (!controller.signal.aborted && ticket === requestNumber.current && currentKey.current === submittedKey) setError((reason as Error).message);}
    finally {if (ticket === requestNumber.current) setBusy(false);}
  };
  const toggleStage = (stage: number) => setStageIndices(previous => previous.includes(stage) ? previous.filter(value => value !== stage) : [...previous, stage]);
  const reset = () => {
    requestNumber.current++; requestAbort.current?.abort(); setBusy(false);
    setStageIndices([1]); setFraction('0'); setFailureMode('uncharged_conducting');
    setChopMode('tail'); setFront(false);
    if (reference) {setTimeUs(String(reference.defaults.tail_chop_time_us)); setShuntR(String(reference.defaults.shunt_r_ohm)); setShuntL(String(reference.defaults.shunt_l_uh));}
    setSavedResult(null); setError('');
  };
  const referenceReady = !!reference && !referenceBusy;
  const disabled = draftEdited || !referenceReady;
  const hasFitted = !!(run.parameter_calibration_review || run.profile?.effective_parameters);

  return <section className="fault-test-lab" id="fault-test-lab" aria-labelledby="fault-test-lab-title" data-quiet={quiet ? 'true' : 'false'}>
    <header className="ft-heading"><div><span className="ft-eyebrow"><FlaskConical size={14} aria-hidden />Fault Test Lab</span><h2 id="fault-test-lab-title">What happens when the impulse changes?</h2><p>Interrupt a lightning pulse or remove a stage’s contribution. Compare the healthy and altered circuit at the same saved charging voltage.</p></div><span className="ft-generated"><Activity size={14} aria-hidden />Physics experiment · no hardware control</span></header>
    <div className="ft-saved-summary"><div><span>Saved setup</span><strong>{shortId(run.id)} · rank {candidate.rank ?? '—'}</strong></div><div><span>Active stages</span><strong>{stageCount}</strong></div><div><span>Fixed charge / healthy stage</span><strong>{fmt(candidate.settings.charge_kv_stage, 3)} <small>kV</small></strong></div><div><span>Healthy circuit crest</span><strong>{reference ? fmt(reference.healthy.metrics.crest_kv, 2) : '—'} <small>kV</small></strong></div></div>
    <div className="ft-evidence"><FlaskConical size={16} aria-hidden /><p><strong>Generated fault simulation · same assumed lumped topology · laboratory accuracy unknown.</strong> This is a model study, with no IEC certification, real fault diagnosis or safe-to-fire decision.</p></div>
    {draftEdited && <div className="ft-notice warning" role="status"><TriangleAlert size={17} aria-hidden /><p>The request has changed. Fault simulations are paused. Recommend new settings or restore the saved inputs before continuing.</p></div>}
    {run.inputs?.solver === 'reference' && <div className="ft-notice"><CircleHelp size={17} aria-hidden /><p>Your recommendation uses workbook metrics. This experiment instead solves the independent circuit at its saved settings. The healthy circuit crest can therefore differ from the requested crest; it is not an ML prediction.</p></div>}
    {(hasFitted || candidate.calibration) && <div className="ft-notice"><CircleHelp size={17} aria-hidden /><p>{hasFitted ? `This saved setup contains fitted effective parameters${run.parameter_calibration_review?.source_type ? ` from ${run.parameter_calibration_review.source_type === 'measured_lab' ? 'declared laboratory calibration captures' : ['generated_demo', 'generated_stress_test', 'synthetic_benchmark', 'simulated'].includes(run.parameter_calibration_review.source_type) ? 'generated or simulated calibration captures' : `captures with declared origin: ${run.parameter_calibration_review.source_type}`}` : ' with no capture origin recorded here'}. ` : ''}The reference audit states exactly which effective values are applied. A one-shot correction to three metrics is not a physical fault waveform and is not silently added.</p></div>}
    <div className="ft-test-selector" role="group" aria-label="Choose a generated fault test">
      <button type="button" className={`ft-test-card ${testType === 'chopped_impulse' ? 'selected' : ''}`} aria-pressed={testType === 'chopped_impulse'} onClick={() => selectTest('chopped_impulse')} disabled={draftEdited}><Scissors size={23} aria-hidden /><span><strong>Front &amp; tail chopping</strong><small>Close an assumed R–L shunt at a declared instant and follow the interruption transient.</small></span><ArrowRight size={17} aria-hidden /></button>
      <button type="button" className={`ft-test-card ${testType === 'stage_failure' ? 'selected' : ''}`} aria-pressed={testType === 'stage_failure'} onClick={() => selectTest('stage_failure')} disabled={draftEdited}><Layers3 size={23} aria-hidden /><span><strong>Generator stage failure</strong><small>Reduce a stage’s charge or compare a deliberately bypassed stage in the equivalent model.</small></span><ArrowRight size={17} aria-hidden /></button>
    </div>
    {referenceBusy && !draftEdited && <div className="ft-loading" role="status"><LoaderCircle size={20} aria-hidden />Solving the healthy circuit at the saved charge…</div>}
    {referenceError && <div className="ft-notice error" role="alert"><TriangleAlert size={17} aria-hidden /><p>{referenceError}</p><button type="button" className="button small" disabled={draftEdited} onClick={() => setReferenceReload(value => value + 1)}>Retry reference</button></div>}
    <div className="ft-lab-layout">
      <form className="ft-controls" onSubmit={event => {event.preventDefault(); void simulate();}}>
        <div className="ft-controls-heading"><span>{testType === 'chopped_impulse' ? '01 · Declare the chop event' : '02 · Declare a stage scenario'}</span><button type="button" className="ft-reset" onClick={reset} disabled={disabled}><RotateCcw size={13} aria-hidden />Reset example</button></div>
        {testType === 'chopped_impulse' ? <>
          <div className="segmented ft-mode" role="group" aria-label="Requested chop classification"><button type="button" className={chopMode === 'front' ? 'active' : ''} aria-pressed={chopMode === 'front'} disabled={disabled} onClick={() => selectChop('front')}>Front chop</button><button type="button" className={chopMode === 'tail' ? 'active' : ''} aria-pressed={chopMode === 'tail'} disabled={disabled} onClick={() => selectChop('tail')}>Tail chop</button></div>
          <p className="ft-control-description">{chopMode === 'front' ? 'Interrupt before the healthy pulse reaches its positive peak.' : 'Interrupt after the healthy pulse reaches its positive peak.'}</p>
          <label className="field"><span>Chop time after the trigger <small>µs</small></span><input type="number" required min="0.000001" max={reference?.limits?.chop_time_max_us ?? 100000} step="any" value={timeUs} disabled={disabled} onChange={event => setTimeUs(event.target.value)} /></label>
          <div className="ft-time-reference"><Activity size={14} aria-hidden /><span>Healthy peak: <strong>{reference ? fmt(reference.healthy.metrics.peak_time_us, 4) : '—'} µs</strong><small>The backend classifies the event relative to the healthy peak, not the T₁ front metric. Time is measured from the trigger, not the virtual waveform origin.{reference?.limits && ` Resolved event window: above 0 to ${fmt(reference.limits.chop_time_max_us, 3)} µs.`}</small></span></div>
          <button type="button" className="ft-example-time" disabled={disabled} onClick={() => selectChop(chopMode)}>Use illustrative {chopMode}-chop time</button>
          <fieldset className="ft-shunt"><legend>Assumed chopping branch</legend><p>Illustrative assumptions — not a hardware specification.</p><div><label className="field"><span>Shunt resistance <small>Ω</small></span><input required type="number" min="0.5" max="10000" step="any" value={shuntR} disabled={disabled} onChange={event => setShuntR(event.target.value)} /></label><label className="field"><span>Shunt inductance <small>µH</small></span><input required type="number" min="0" max="10000" step="any" value={shuntL} disabled={disabled} onChange={event => setShuntL(event.target.value)} /></label></div><p>The assumed branch closes across the load-side voltage. Finite inductance determines the fast transient and possible reversal. Zero inductance selects the ideal R-only approximation.</p></fieldset>
        </> : <>
          <label className="field"><span>Failure assumption</span><select value={failureMode} disabled={disabled} onChange={event => setFailureMode(event.target.value as StageFailureMode)}><option value="uncharged_conducting">Reduced charge · full stack conducting</option><option value="bypassed">Deliberate stage bypass · topology changes</option></select></label>
          <p className="ft-control-description">{failureMode === 'uncharged_conducting' ? 'The gap is assumed to conduct and the capacitor stays in the erected stack. Only its initial charge changes.' : 'Selected stages are removed from the equivalent stack. Capacitance and series-model resistances are re-derived.'}</p>
          {failureMode === 'uncharged_conducting' && <><label className="field"><span>Charge retained by each selected stage <small>fraction 0–1</small></span><input required type="number" min="0" max="1" step="any" value={fraction} disabled={disabled} onChange={event => setFraction(event.target.value)} /></label><input type="range" min="0" max="1" step="0.05" value={Number.isFinite(numericInput(fraction)) ? Math.min(1, Math.max(0, numericInput(fraction))) : 0} aria-label="Selected stage remaining charge fraction" disabled={disabled} onChange={event => setFraction(event.target.value)} /><div className="ft-fraction-shortcuts">{[0, 0.5, 1].map(value => <button type="button" key={value} disabled={disabled} onClick={() => setFraction(String(value))}>{value === 0 ? 'Zero charge' : value === 1 ? 'Healthy control' : '50% charge'}</button>)}</div></>}
          <StageStack count={stageCount} selected={selected} mode={failureMode} fraction={numericInput(fraction)} interactive disabled={disabled} onSelect={toggleStage} />
          <p className="ft-selected-stages">Selected: <strong>{selected.length ? selected.map(stage => `S${stage}`).join(', ') : 'None — choose a stage'}</strong></p>
          <div className="ft-open-gap"><TriangleAlert size={15} aria-hidden /><p><strong>Open-gap misfire is not simulated.</strong> A gap that fails to fire can isolate parts of the stack; that requires stage-by-stage switching and distributed parasitics. Neither mode claims to reproduce it.</p></div>
        </>}
        {!!problems.length && !disabled && <ul className="ft-problems" aria-live="polite">{problems.map(problem => <li key={problem}>{problem}</li>)}</ul>}
        <button type="submit" className="button primary ft-run" disabled={disabled || busy || !!problems.length}>{busy ? <LoaderCircle size={16} aria-hidden /> : <Play size={16} aria-hidden />}{busy ? 'Solving the fault transient…' : 'Simulate and compare'}<ArrowRight size={15} aria-hidden /></button>
        <p className="ft-control-footnote">The requested crest is not used to re-scale either curve. Saved charge, load and efficiency remain fixed unless this scenario explicitly changes the contributing stages.</p>
      </form>
      <div className="ft-output" aria-busy={busy}>
        {error && <div className="ft-notice error" role="alert"><TriangleAlert size={17} aria-hidden /><p>{error}</p></div>}
        {result ? <ResultPanel result={result} front={front} setFront={setFront} /> : <div className="ft-empty"><div className="ft-empty-illustration" aria-hidden><svg viewBox="0 0 540 180"><path className="ft-empty-grid" d="M20 40H520M20 80H520M20 120H520M80 15V155M180 15V155M280 15V155M380 15V155M480 15V155" /><path className="ft-empty-healthy" d="M20 145L72 145C74 105 77 40 92 31C139 17 179 53 223 75C281 107 369 130 520 145" /><path className="ft-empty-fault" d={testType === 'chopped_impulse' ? 'M20 145L72 145C74 105 77 40 92 31C139 17 179 53 223 75L247 162C257 171 266 130 279 143L520 145' : 'M20 145L72 145C74 126 77 86 92 81C139 65 179 93 223 109C281 129 369 141 520 145'} /><path className="ft-empty-event" d="M228 16V162" /></svg><span>Illustration only · not a computed result</span></div><span className="ft-empty-eyebrow">A controlled comparison</span><h3>{testType === 'chopped_impulse' ? 'Watch the interruption change the pulse' : 'See the cost of a lost stage contribution'}</h3><p>{testType === 'chopped_impulse' ? 'Declare the instant and assumed branch, then compare the entire transient with the healthy pulse. Crest, event voltage, reversal and energy are reported separately.' : 'Choose one or more stages. First try zero charge with a conducting stack, then compare a deliberate bypass to see why these are different physical assumptions.'}</p><ol><li><span>1</span>Keep the saved healthy setup as the reference.</li><li><span>2</span>Declare exactly what changes in the model.</li><li><span>3</span>Compare both curves and inspect the numerical audit.</li></ol><p className="ft-empty-boundary"><CircleHelp size={15} aria-hidden />A convincing highlight is a transparent experiment with honest limitations. A matching simulation is not proof of a real generator’s fault behavior.</p></div>}
      </div>
    </div>
    <footer className="ft-safety"><ShieldAlert size={20} aria-hidden /><div><strong>Software experiments only · person safety requires laboratory controls</strong><p>Chopping and generator faults can involve severe transient current, voltage reversal and stored energy. A zero predicted output or a bypassed stage does not mean a physical bank is discharged or safe to approach. Do not reproduce these virtual scenarios on equipment from this screen. Any real test requires qualified authorized personnel, the laboratory’s approved test plan, rated equipment, isolation and stored-energy verification, barriers, interlocks and emergency arrangements. This model cannot verify any of those conditions.</p></div></footer>
  </section>;
}

export default function FaultTestLab({run, candidate, draftEdited = false}: FaultTestLabProps) {
  const key = faultSnapshotKey(run, candidate);
  if (!key || !run || !candidate) return null;
  return <FaultWorkspace key={key} run={run} candidate={candidate} draftEdited={draftEdited} />;
}
