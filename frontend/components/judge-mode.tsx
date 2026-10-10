'use client';
import {useCallback, useEffect, useMemo, useState} from 'react';
import Link from 'next/link';
import {ArrowLeft, ArrowRight, Expand, FileText, FlaskConical, LoaderCircle, Shrink, Upload} from 'lucide-react';
import {api, apiUrl, Data, fmt, post, profileInputs, solverInputs, human, shortId, isNum} from '@/lib/api';
import {Badge, KindTag, Notice, PassFail, Status, Working} from './ui';
import {useWorkspace} from './workspace';
import {EvidenceCard, SourceBadge, sourceLabel, trialSourceType} from './evidence-pages';
import EngineeringChart from './engineering-chart';
import GeneratorView from './generator/generator-view';
import type {SceneView} from './generator/engine';
import {GeneratorModel, modelFromCandidate} from '@/lib/generator-model';
import {MetricGauges, metricName} from './hall';
import NetworkSchematic from './network-schematic';
import InventoryEditor from './inventory-editor';
import {InventoryDraft, draftFromOverride, emptyDraft, overrideFromDraft} from '@/lib/inventory';

const steps = ['The problem', 'Test request', 'Configuration', 'Evidence', 'Alternatives', 'Trial feedback', 'Summary'];
const VIEWS: SceneView[] = ['overview', 'overview', 'stack', 'overview', 'stack', 'output', 'overview'];

function outline(profile: Data | undefined): GeneratorModel | null {
  if (!profile || !isNum(profile.max_stages)) return null;
  const empty = {topology: 'Not solved', equivalentOhm: null, parts: [], tree: null, perStageCount: 0, totalComponents: null};
  return {
    key: `profile:${profile.id}`,
    mode: 'candidate',
    title: profile.name,
    profileName: profile.name,
    impulse: '',
    maxStages: profile.max_stages,
    activeStages: 0,
    chargeKv: null,
    stageRatingKv: profile.stage_kv ?? null,
    utilization: null,
    storedEnergyKj: null,
    front: {...empty, role: 'front'},
    tail: {...empty, role: 'tail'},
    stages: Array.from({length: profile.max_stages}, () => 'inactive'),
  };
}

export default function JudgeMode() {
  const w = useWorkspace();
  const [step, setStep] = useState(0),
    [judge, setJudge] = useState<Data | null>(null),
    [objects, setObjects] = useState<Data[]>([]),
    [draft, setDraft] = useState<Data>(w.inputs),
    [review, setReview] = useState<Data | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [trial, setTrial] = useState<Data | null>(null),
    [origin, setOrigin] = useState('generated_stress_test'),
    [stockEnabled, setStockEnabled] = useState(() => !!w.inputs.inventory_override),
    [stock, setStock] = useState<InventoryDraft>(() => draftFromOverride(w.inputs.inventory_override)),
    [requestEdited, setRequestEdited] = useState(() => !!w.run && JSON.stringify(w.inputs) !== JSON.stringify(w.run.inputs)),
    [preview, setPreview] = useState<string | null>(null),
    [full, setFull] = useState(false);

  useEffect(() => {
    api('/api/test-objects')
      .then(d => setObjects(d.objects))
      .catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    let alive = true;
    setJudge(null);
    setTrial(null);
    if (w.run)
      api(`/api/runs/${w.run.id}/judge`)
        .then(d => {
          if (alive) setJudge(d);
        })
        .catch(e => {
          if (alive) setError(e.message);
        });
    return () => {
      alive = false;
    };
  }, [w.run]);
  useEffect(() => {
    if (w.run && !requestEdited) {
      setDraft(w.run.inputs);
      setStockEnabled(!!w.run.inputs.inventory_override);
      setStock(draftFromOverride(w.run.inputs.inventory_override));
    }
  }, [w.run, requestEdited]);
  useEffect(() => {
    const onChange = () => setFull(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const candidate = judge?.candidates?.[w.selected] || judge?.candidates?.[0];
  const locked = (i: number) => i > 1 && (!judge || requestEdited);
  const go = useCallback((i: number) => setStep(s => (i < 0 || i >= steps.length || (i > 1 && (!judge || requestEdited)) ? s : i)), [judge, requestEdited]);

  // Presentation clickers send PageDown/PageUp or arrow keys.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el?.closest('input, select, textarea, [contenteditable], .scene-canvas, [role="radiogroup"]')) return;
      if (e.key === 'PageDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        go(step + 1);
      }
      if (e.key === 'PageUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        go(step - 1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, step]);

  const change = (key: string, value: any) => {
    setDraft({...draft, [key]: value, confirm_reference_mismatch: false});
    setReview(null);
    setRequestEdited(true);
  };
  async function recommend() {
    setLoading(true);
    setError('');
    try {
      let inventoryOverride: Data | null = null;
      if (stockEnabled) {
        const built = overrideFromDraft(stock);
        if ('error' in built) throw new Error(`${built.error} Open “Counted stock” to correct it.`);
        inventoryOverride = built.value;
      }
      if (selectedProfile?.units_per_value_per_stage == null && !inventoryOverride)
        throw new Error('Stock quantities are unknown. Open “Counted stock” and enter counts per stage with provenance, or select an explicitly assumed-stock demo in the engineering workspace.');
      const values = {...draft, inventory_override: inventoryOverride};
      const check = await post('/api/test-objects/validate', values);
      setReview(check);
      if (check.confirmation_required) return;
      const result = await w.optimize(values);
      if (result) {
        setJudge(await api(`/api/runs/${result.id}/judge`));
        setRequestEdited(false);
        setStep(2);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function upload(file: File, source: string) {
    if (!judge || !candidate) return;
    setLoading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('run_id', judge.id);
      form.append('candidate_id', candidate.id);
      form.append('source_type', source);
      setTrial(await api('/api/trials/upload', {method: 'POST', body: form}));
      setJudge(await api(`/api/runs/${judge.id}/judge`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function demonstrate() {
    if (!judge || !candidate) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(apiUrl(`/api/runs/${judge.id}/demo-waveform?candidate_id=${candidate.id}`));
      if (!response.ok) throw new Error('Generated waveform request failed');
      await upload(new File([await response.blob()], 'generated-demonstration.csv', {type: 'text/csv'}), 'generated_stress_test');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  const activeTrial = trial?.candidate_id === candidate?.id ? trial : judge?.trials?.find((t: Data) => t.candidate_id === candidate?.id);
  const trialOrigin = activeTrial ? trialSourceType(activeTrial) : 'unknown';
  const calibrationAdmitted =
    typeof activeTrial?.evidence?.eligible_for_calibration === 'boolean'
      ? activeTrial.evidence.eligible_for_calibration
      : ['generated_demo', 'measured_lab'].includes(trialOrigin) && activeTrial?.quality?.calibration_allowed === true;
  const trialSourceDescription =
    (
      {
        measured_lab: 'Operator-labeled laboratory capture',
        generated_demo: 'GENERATED DEMONSTRATION — NOT LABORATORY EVIDENCE',
        synthetic_benchmark: 'SYNTHETIC BENCHMARK — NOT MEASURED LABORATORY DATA',
        unknown: 'UNKNOWN SOURCE — ORIGIN REQUIRES REVIEW',
      } as Record<string, string>
    )[trialOrigin] || 'UNKNOWN SOURCE — ORIGIN REQUIRES REVIEW';
  const selectedProfile = w.profiles.find(p => p.id === draft.profile_id);
  const circuitPrimary = judge?.inputs.solver === 'circuit';
  const predictionLabel = circuitPrimary ? 'Circuit prediction' : candidate?.ood.trust_weight > 0 ? 'ML-corrected metrics (reconstructed shape)' : 'Workbook metrics (reconstructed shape)';
  const stockMissing = selectedProfile?.units_per_value_per_stage == null && !stockEnabled;

  const previewed = preview ? judge?.candidates?.find((c: Data) => c.id === preview) : null;
  const sceneModel = useMemo(() => {
    if (step <= 1 && (requestEdited || !judge || !candidate)) return outline(selectedProfile);
    const shown = previewed || candidate;
    return judge && shown ? modelFromCandidate(judge, shown, judge.profile) : outline(selectedProfile);
  }, [step, requestEdited, judge, candidate, previewed, selectedProfile]);
  const sceneCaption =
    step <= 1 && (requestEdited || !judge)
      ? `${selectedProfile?.name || 'Profile'} outline · request not solved yet`
      : judge && (previewed || candidate)
        ? `Saved run ${shortId(judge.id)} · ${previewed ? `previewing rank ${previewed.rank}` : `rank ${candidate.rank}`}`
        : 'No saved recommendation';
  const showWave = judge && candidate && (step === 2 || step === 3 || step === 5);
  const measured = step === 5 && activeTrial ? {...(activeTrial.comparison_waveform || activeTrial.waveform), kind: trialOrigin} : undefined;

  const toggleFull = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      /* full screen not permitted */
    }
  };

  return (
    <div className="judge">
      <div className="judge-top">
        <div className="judge-title">
          <p>Judge Mode · 4–6 minute guided demonstration</p>
          <h1>From request to evidence</h1>
        </div>
        <div className="judge-tools">
          <button className="hall-button" onClick={toggleFull} aria-pressed={full}>
            {full ? <Shrink size={15} aria-hidden /> : <Expand size={15} aria-hidden />} {full ? 'Exit full screen' : 'Present full screen'}
          </button>
          <Link className="hall-button" href="/">
            Engineering workspace
          </Link>
        </div>
      </div>
      <nav className="judge-rail" aria-label="Demonstration steps">
        <ol>
          {steps.map((s, i) => (
            <li key={s}>
              <button aria-current={i === step ? 'step' : undefined} className={i === step ? 'active' : i < step ? 'done' : ''} disabled={locked(i)} onClick={() => setStep(i)}>
                <span>{i + 1}</span>
                {s}
              </button>
            </li>
          ))}
        </ol>
        <div className="judge-progress" aria-hidden>
          <i style={{width: `${(step / (steps.length - 1)) * 100}%`}} />
        </div>
      </nav>
      {(error || w.error) && (
        <div className="judge-alert" role="alert">
          {error || w.error}
        </div>
      )}
      <div className="judge-stage">
        <div className="judge-visual">
          <GeneratorView model={sceneModel} view={VIEWS[step]} playKey={w.runSerial} height={showWave ? 'calc(100% - 248px)' : '100%'} caption={sceneCaption} compact={step === 1} />
          {showWave && (
            <div className="judge-wave">
              <EngineeringChart
                theme="hall"
                waveform={candidate.waveform}
                target={judge.target_waveform}
                circuit={candidate.circuit_crosscheck?.waveform}
                measured={measured}
                measuredLabel={`Uploaded trial · ${sourceLabel(trialOrigin).toLowerCase()}`}
                predictionLabel={predictionLabel}
                crestBounds={candidate.compliance?.rows?.[2] ? [candidate.compliance.rows[2].lower, candidate.compliance.rows[2].upper] : undefined}
                height={210}
                showKey={false}
              />
            </div>
          )}
        </div>
        <section className="judge-narrative" aria-live="polite" key={step}>
          <p className="judge-step-id">
            Step {step + 1} of {steps.length} · {steps[step]}
          </p>
          {step === 0 && (
            <div className="judge-intro">
              <h2>A stronger starting setup. An inspectable reason why.</h2>
              <p className="judge-lead">Impulse testing can require repeated physical changes to resistor networks and active generator stages before the waveform meets its limits.</p>
              <ol className="judge-loop">
                {['Analytical estimate', 'Adjust hardware', 'Trial shot', 'Inspect waveform', 'Repeat'].map((s, i) => (
                  <li key={s}>
                    <span>{i + 1}</span>
                    {s}
                  </li>
                ))}
              </ol>
              <p className="judge-goal">ImpulseTwin combines physics, counted hardware and supported ML correction before the next physical trial.</p>
              <p className="judge-small">Simulation and synthetic benchmarks are available. Measured laboratory accuracy remains pending until new captures are evaluated. The stack on the left is a conceptual schematic, not a model of the real machine.</p>
            </div>
          )}

          {step === 1 && (
            <div className="judge-request">
              <h2>What impulse is needed?</h2>
              <p className="judge-lead">CPRI physical parameters are the engineering reference. Load, parasitics, efficiency and stock remain explicit operator inputs.</p>
              <div className="judge-fields">
                <label>
                  Impulse type
                  <select
                    value={draft.impulse_type}
                    onChange={e => {
                      setDraft({...draft, impulse_type: e.target.value, test_object_id: null, confirm_reference_mismatch: false});
                      setRequestEdited(true);
                      setReview(null);
                    }}
                  >
                    <option>Lightning</option>
                    <option>Switching</option>
                  </select>
                </label>
                <label>
                  Requested crest (kV)
                  <input type="number" min="1" value={draft.test_kv} onChange={e => change('test_kv', Number(e.target.value))} />
                </label>
                <label>
                  Generator profile
                  <select
                    value={draft.profile_id}
                    onChange={e => {
                      setDraft(profileInputs(draft, e.target.value));
                      setStockEnabled(false);
                      setStock(emptyDraft());
                      setRequestEdited(true);
                      setReview(null);
                    }}
                  >
                    {w.profiles.map(p => (
                      <option value={p.id} key={p.id} disabled={!p.enabled}>
                        {p.name}
                        {!p.enabled ? ' — incomplete' : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Object capacitance (pF)
                  <input type="number" min="1" value={draft.load_c_pf} onChange={e => change('load_c_pf', Number(e.target.value))} />
                </label>
                <label className="span-2">
                  Optional equipment reference
                  <select value={draft.test_object_id || ''} onChange={e => change('test_object_id', e.target.value || null)}>
                    <option value="">No catalog selection</option>
                    {objects
                      .filter(o => o.impulse_type === draft.impulse_type)
                      .map(o => (
                        <option key={o.id} value={o.id}>
                          {o.name} — {o.status.toUpperCase()}
                        </option>
                      ))}
                  </select>
                </label>
                {draft.solver === 'reference' && (
                  <label className="judge-checkbox span-2">
                    <input type="checkbox" checked={!!draft.require_model_agreement} onChange={e => change('require_model_agreement', e.target.checked)} /> Search for agreement across both models
                  </label>
                )}
              </div>
              <div className="judge-engine">
                <Badge tone="cyan">{draft.solver === 'circuit' ? 'Primary Marx / RLC circuit' : 'Reference equations + cross-check'}</Badge>
                <Badge tone={draft.profile_id === 'workbook_reference_profile' && draft.solver === 'reference' && draft.model_mode !== 'physics' ? 'cyan' : 'neutral'}>
                  {draft.profile_id === 'workbook_reference_profile' && draft.solver === 'reference' && draft.model_mode !== 'physics' ? 'ML subject to backend support gate' : 'Residual ML off'}
                </Badge>
                <p>
                  {selectedProfile?.source}. {draft.profile_id === 'cpri_problem_brief_profile' ? 'Workbook residual transfer is unsupported.' : 'Synthetic workbook reference and benchmark profile.'} {draft.include_base_c ? 'Profile base capacitance is included once.' : 'Profile base capacitance is excluded.'}
                </p>
              </div>
              <details className="judge-details" open={stockMissing || stockEnabled}>
                <summary>Counted stock {stockMissing ? '· required' : stockEnabled ? '· explicit inventory' : ''}</summary>
                <label className="judge-checkbox">
                  <input
                    type="checkbox"
                    checked={stockEnabled}
                    onChange={e => {
                      setStockEnabled(e.target.checked);
                      setRequestEdited(true);
                    }}
                  />{' '}
                  Use explicit inventory (required when source counts are unknown)
                </label>
                {stockEnabled && (
                  <InventoryEditor
                    draft={stock}
                    onChange={d => {
                      setStock(d);
                      setRequestEdited(true);
                    }}
                    profile={selectedProfile}
                    impulse={draft.impulse_type}
                    idPrefix="judge"
                  />
                )}
              </details>
              <details className="judge-details">
                <summary>Advanced parameters and operator reference</summary>
                <div className="judge-fields">
                  <label>
                    Primary prediction engine
                    <select
                      value={draft.solver}
                      onChange={e => {
                        setDraft(solverInputs(draft, e.target.value));
                        setRequestEdited(true);
                        setReview(null);
                      }}
                    >
                      <option value="circuit">Equivalent Marx / RLC circuit · physics only</option>
                      <option value="reference">Reference equations + circuit cross-check</option>
                    </select>
                  </label>
                  <label>
                    Residual correction
                    <select
                      disabled={draft.solver === 'circuit' || draft.profile_id !== 'workbook_reference_profile'}
                      value={draft.solver === 'circuit' || draft.profile_id !== 'workbook_reference_profile' ? 'physics' : draft.model_mode}
                      onChange={e => change('model_mode', e.target.value)}
                    >
                      <option value="physics">Physics only</option>
                      <option value="hybrid">Frozen V1 · workbook support gate</option>
                      <option value="experimental_v2">Experimental V2 · workbook development</option>
                    </select>
                  </label>
                  {[
                    ['divider_c_pf', 'Divider C (pF)'],
                    ['stray_c_pf', 'Stray C (pF)'],
                    ['l_uh', 'Inductance (µH)'],
                    ['efficiency', 'Efficiency'],
                    ['uncertainty_pct', 'Parasitic variation (%)'],
                  ].map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input type="number" step="any" value={draft[key]} onChange={e => change(key, Number(e.target.value))} />
                    </label>
                  ))}
                  <label>
                    Layout ID
                    <input value={draft.layout_id} onChange={e => change('layout_id', e.target.value)} />
                  </label>
                  <label className="judge-checkbox span-2">
                    <input type="checkbox" checked={!!draft.include_base_c} onChange={e => change('include_base_c', e.target.checked)} />
                    <span>
                      Include profile base capacitance ({fmt(selectedProfile?.base_c_pf, 0)} pF)
                      <small className="block">Exclude it if this capacitance is already represented by the divider or system inputs.</small>
                    </span>
                  </label>
                  <label>
                    Operator reference (kV)
                    <input type="number" value={draft.equipment_reference_kv ?? ''} onChange={e => change('equipment_reference_kv', e.target.value ? Number(e.target.value) : null)} />
                  </label>
                  <label>
                    Reference source
                    <input value={draft.equipment_reference_source || ''} onChange={e => change('equipment_reference_source', e.target.value || null)} />
                  </label>
                </div>
              </details>
              {stockMissing && (
                <p className="judge-guidance" id="judge-stock-guidance">
                  CPRI source stock quantities are unknown. Supply actual counts or clearly label the inventory assumption in Counted stock. A generated demonstration does not verify stock.
                </p>
              )}
              {review && (
                <div className="judge-review">
                  <Badge tone="amber">{String(review.status).toUpperCase().replaceAll('_', ' ')}</Badge>
                  <p>{review.message}</p>
                  {review.mismatch && (
                    <label className="judge-checkbox">
                      <input type="checkbox" checked={!!draft.confirm_reference_mismatch} onChange={e => setDraft({...draft, confirm_reference_mismatch: e.target.checked})} /> I confirm that the requested test level is intentional.
                    </label>
                  )}
                </div>
              )}
              <div className="judge-cta">
                <button className="judge-primary" aria-describedby={stockMissing ? 'judge-stock-guidance' : undefined} disabled={loading || w.busy || stockMissing} onClick={recommend}>
                  {loading || w.busy ? <LoaderCircle size={17} className="spin" aria-hidden /> : null}
                  {loading || w.busy ? 'Evaluating declared hardware…' : 'Find a starting configuration'}
                  <ArrowRight size={17} aria-hidden />
                </button>
                {(loading || w.busy) && <Working>Solving on the local engine</Working>}
                {requestEdited && judge && !loading && <span className="judge-small">Later steps unlock when this edited request is solved.</span>}
              </div>
            </div>
          )}

          {step === 2 && candidate && (
            <div className="judge-config">
              <h2>{candidate.compliance.nominal_pass ? 'A feasible simulated starting point' : 'Diagnostic alternative — waveform outside limits'}</h2>
              <p className="judge-small">
                Run {judge?.id} · {judge?.profile.name} · {judge?.inputs.impulse_type}
              </p>
              <div className="judge-engine">
                <Badge tone="cyan">{circuitPrimary ? 'Primary circuit model' : 'Reference model + circuit cross-check'}</Badge>
                <Badge>{candidate.ood.trust_weight > 0 ? `Residual weight ${fmt(candidate.ood.trust_weight, 2)}` : 'Residual ML off'}</Badge>
                <Status value={candidate.compliance.status} />
              </div>
              <div className="judge-numbers">
                <div>
                  <strong>{candidate.settings.stages}</strong>
                  <span>active stages</span>
                </div>
                <i aria-hidden>×</i>
                <div>
                  <strong>{fmt(candidate.settings.charge_kv_stage)}</strong>
                  <span>kV per stage</span>
                </div>
              </div>
              {(
                [
                  ['Front', candidate.front_network],
                  ['Tail', candidate.tail_network],
                ] as const
              ).map(([name, network]) => {
                const nm = sceneModel && !previewed ? (name === 'Front' ? sceneModel.front : sceneModel.tail) : null;
                return (
                  <div className="judge-network" key={name}>
                    <div>
                      <span>
                        {name} resistor / stage · {fmt(network.equivalent_ohm)} Ω
                      </span>
                      <strong>{network.topology}</strong>
                      <small>{network.total_components} components across all stages</small>
                    </div>
                    {nm && <NetworkSchematic net={nm} />}
                  </div>
                );
              })}
              <p className="judge-small">
                {candidate.setup_component_count} total components · {fmt(candidate.settings.stored_energy_kj)} kJ · {fmt(candidate.settings.stage_utilization * 100)}% stage-voltage utilization
              </p>
              <div className="judge-metrics">
                {(['front_us', 'tail_us', 'crest_kv'] as const).map((key, i) => (
                  <div key={key}>
                    <span>{metricName(i, judge?.inputs.impulse_type)}</span>
                    <strong>
                      {fmt(candidate.hybrid[key], 3)} <small>{i === 2 ? 'kV' : 'µs'}</small>
                    </strong>
                    <PassFail pass={candidate.compliance.rows?.[i]?.pass} />
                  </div>
                ))}
              </div>
              <p className="judge-caveat">Counted construction and declared ratings checked. Actual pulse ratings, mounting and allowed physical connections still need verification.</p>
            </div>
          )}

          {step === 3 && candidate && (
            <div className="judge-evidence">
              <h2>What supports this setup?</h2>
              <p className="judge-lead">Evidence is explicit. Disagreement and missing measurements remain visible.</p>
              <EvidenceCard evidence={candidate.evidence} />
              <MetricGauges candidate={candidate} impulse={judge?.inputs.impulse_type} theme="hall" />
              <p className="judge-small">
                {candidate.uncertainty.method}. {candidate.uncertainty.coverage_limit}
              </p>
            </div>
          )}

          {step === 4 && judge && (
            <div className="judge-alternatives">
              <h2>More than one useful starting point.</h2>
              <p className="judge-small">{judge.alternative_scope}</p>
              <div className="alt-grid" onMouseLeave={() => setPreview(null)}>
                {judge.alternatives.map((a: Data) => (
                  <article key={a.candidate.id} onMouseEnter={() => setPreview(a.candidate.id)} onFocus={() => setPreview(a.candidate.id)} className={preview === a.candidate.id ? 'previewing' : ''}>
                    <div className="alt-labels">
                      {a.labels.map((label: string) => (
                        <Badge key={label} tone="cyan">
                          {label}
                        </Badge>
                      ))}
                    </div>
                    <h3>
                      {a.candidate.settings.stages} stages · {fmt(a.candidate.settings.charge_kv_stage, 1)} kV
                    </h3>
                    <dl>
                      <div>
                        <dt>Components</dt>
                        <dd>{a.candidate.setup_component_count}</dd>
                      </div>
                      <div>
                        <dt>Waveform error cost</dt>
                        <dd>{fmt(a.candidate.accuracy_cost, 4)}</dd>
                      </div>
                      <div>
                        <dt>Stage headroom</dt>
                        <dd>{fmt(a.candidate.settings.voltage_margin_kv_stage)} kV</dd>
                      </div>
                      <div>
                        <dt>{circuitPrimary ? 'Primary circuit nominal' : 'Independent circuit nominal'}</dt>
                        <dd>
                          {circuitPrimary
                            ? a.candidate.compliance.nominal_pass
                              ? 'PASS'
                              : 'FAIL'
                            : a.candidate.circuit_crosscheck?.compliance.nominal_pass
                              ? 'PASS'
                              : a.candidate.circuit_crosscheck
                                ? 'FAIL'
                                : 'NOT VERIFIED'}
                        </dd>
                      </div>
                    </dl>
                    <Badge tone={a.candidate.compliance.nominal_pass ? 'green' : 'red'}>{a.candidate.compliance.nominal_pass ? 'Nominal pass' : 'Diagnostic fail'}</Badge>
                    <button
                      className="hall-button"
                      onClick={() => {
                        w.setSelected(judge.candidates.findIndex((c: Data) => c.id === a.candidate.id));
                        setPreview(null);
                        setStep(2);
                      }}
                    >
                      Inspect this setup <ArrowRight size={14} aria-hidden />
                    </button>
                  </article>
                ))}
              </div>
              <p className="judge-small">Hover or focus a card to preview its saved stack on the left.</p>
              <Link className="hall-link" href="/compare/">
                Compare changes from a saved physical setup <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
          )}

          {step === 5 && candidate && (
            <div className="judge-trial">
              <h2>Prediction versus trial.</h2>
              <p className="judge-lead">Save the prediction first. Preserve the raw capture. Review acquisition quality before calibration or evaluation.</p>
              <div className="judge-trial-actions">
                <button className="judge-primary" disabled={loading} onClick={demonstrate}>
                  {loading ? <LoaderCircle size={16} className="spin" aria-hidden /> : <FlaskConical size={16} aria-hidden />}
                  {loading ? 'Loading trial…' : 'Load generated demonstration'}
                </button>
                <label>
                  CSV source
                  <select value={origin} onChange={e => setOrigin(e.target.value)}>
                    <option value="generated_stress_test">GENERATED DEMO</option>
                    <option value="measured_lab">MEASURED LAB — operator declaration</option>
                  </select>
                </label>
                <label className="judge-file">
                  <Upload size={15} aria-hidden /> Upload CSV (time_us, voltage_kv)
                  <input
                    type="file"
                    accept=".csv"
                    disabled={loading}
                    onChange={e => {
                      const file = e.target.files?.[0];
                      if (file) upload(file, origin);
                      e.target.value = '';
                    }}
                  />
                </label>
              </div>
              <p className="judge-small">Judge upload uses µs and kV with zero baseline and onset. Use Trial calibrator for other units, delayed or negative-baseline captures.</p>
              {activeTrial ? (
                <>
                  <div className={`judge-source judge-source-${trialOrigin}`}>
                    <SourceBadge trial={activeTrial} />
                    <strong>{trialSourceDescription}</strong>
                  </div>
                  <table className="judge-table">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Saved prediction</th>
                        <th>Uploaded trial</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(['front_us', 'tail_us', 'crest_kv'] as const).map((k, i) => (
                        <tr key={k}>
                          <td>{metricName(i, judge?.inputs.impulse_type)}</td>
                          <td>{fmt(candidate.hybrid[k], 4)}</td>
                          <td>{fmt(activeTrial.measured?.[k], 4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="judge-caveat">
                    Acquisition review: {activeTrial.quality?.status || 'unknown'}.{' '}
                    {calibrationAdmitted ? 'Source and acquisition admission met; the backend rechecks the original capture before local correction.' : 'Not admitted for local correction; review source and acquisition quality.'} Generated and synthetic data are excluded from measured laboratory accuracy.
                  </p>
                </>
              ) : (
                <div className="judge-empty">
                  <FlaskConical size={26} aria-hidden />
                  <h3>No trial selected for this candidate.</h3>
                  <p>Load a clearly labeled demonstration or upload an actual capture.</p>
                </div>
              )}
              <Link className="hall-link" href="/trial-calibrator/">
                Open full trial calibration and accuracy review <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
          )}

          {step === 6 && candidate && judge && (
            <div className="judge-summary">
              <h2>Every recommendation carries its evidence.</h2>
              <ul className="judge-checks">
                {[
                  ['Workbook synthetic benchmark (separate profile)', w.source?.dataset_hash_matches_frozen_model ? 'AVAILABLE · HASH VERIFIED' : 'NOT VERIFIED'],
                  [circuitPrimary ? 'Primary circuit model' : 'Independent circuit cross-check', circuitPrimary ? 'ACTIVE · PHYSICS ONLY' : candidate.circuit_crosscheck ? 'AVAILABLE' : 'NOT VERIFIED'],
                  ['Second-model comparison', candidate.circuit_crosscheck ? 'PERFORMED' : 'NOT PERFORMED'],
                  ['Counted hardware constraints', candidate.front_network.inventory_feasible && candidate.tail_network.inventory_feasible ? 'CHECKED' : 'UNKNOWN'],
                  ['ML support check', candidate.ood.trust_weight > 0 ? human(candidate.ood.state) : 'RESIDUAL OFF · ' + human(candidate.ood.state)],
                  ['Measured laboratory captures', String(judge.laboratory.measured_captures)],
                  ['Measured evaluation of this setup', candidate.evidence.evaluation_ids.length ? 'AVAILABLE · REVIEW ERRORS' : 'PENDING'],
                ].map(([name, status]) => (
                  <li key={name}>
                    <span>{name}</span>
                    <Badge tone={/NOT|UNKNOWN|PENDING|^0$/.test(status) ? 'unknown' : 'neutral'}>{status}</Badge>
                  </li>
                ))}
              </ul>
              <p className="judge-lead">The next evidence comes from verified stock, instrumented trial shots and independent measured evaluation.</p>
              <div className="judge-trial-actions">
                <Link href="/laboratory-evidence/" className="hall-button">
                  Laboratory readiness
                </Link>
                <a href={apiUrl(`/api/runs/${judge.id}/report`)} target="_blank" rel="noreferrer" className="judge-primary">
                  <FileText size={16} aria-hidden /> Open engineering report <ArrowRight size={16} aria-hidden />
                </a>
              </div>
            </div>
          )}

          {step > 1 && !judge && !requestEdited && w.run && (
            <div className="judge-empty">
              <Working>Loading the saved run’s evidence</Working>
            </div>
          )}
        </section>
      </div>
      <div className="judge-nav">
        <button className="hall-button" disabled={step === 0} onClick={() => setStep(step - 1)}>
          <ArrowLeft size={16} aria-hidden /> Back
        </button>
        <span>
          {step + 1} / {steps.length} · {steps[step]}
          <small>Arrow keys or a presentation clicker also move between steps</small>
        </span>
        <button className="judge-primary" disabled={step === 6 || (step === 1 && (!judge || requestEdited))} onClick={() => setStep(step + 1)}>
          Next <ArrowRight size={16} aria-hidden />
        </button>
      </div>
      <p className="judge-foot">
        <KindTag kind="conceptual">Conceptual</KindTag> The 3D stack is schematic and driven by the saved candidate. Any glow or firing sequence is illustrative, not computed spark-gap or field physics.
      </p>
    </div>
  );
}
