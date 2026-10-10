'use client';
import {useCallback, useEffect, useMemo, useState} from 'react';
import Link from 'next/link';
import {ArrowDownToLine, ArrowRight, Check, ChevronDown, Download, FlaskConical, GitCompareArrows, LoaderCircle, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, TriangleAlert, Zap} from 'lucide-react';
import {EvidenceCard, trialSourceType, sourceLabel} from './evidence-pages';
import {api, apiUrl, Data, fmt, human, initialInputs, workbookInputs, profileInputs, solverInputs, post, requestKey, stamp, shortId, age, isNum, signed, CUSTOM_PROFILE_ID, customProfileGaps, customProfileView} from '@/lib/api';
import {Badge, KindTag, Notice, Panel, PassFail, Segmented, Status, Working} from './ui';
import {useWorkspace} from './workspace';
import SettingsVerification from './settings-verification';
import RlcSensitivity from './rlc-sensitivity';
import {comparisonWaveform} from '@/lib/trial-waveform';
import GeneratorView from './generator/generator-view';
import type {SceneView} from './generator/engine';
import {modelFromCandidate, GeneratorModel} from '@/lib/generator-model';
import {MetricGauges, Scope, predictionLabelFor} from './hall';
import NetworkSchematic from './network-schematic';
import InventoryEditor from './inventory-editor';
import {InventoryDraft, draftFromOverride, overrideFromDraft} from '@/lib/inventory';

const primaryFields = [
  ['load_c_pf', 'Test-object capacitance', 'pF', 1, 100000],
  ['divider_c_pf', 'Divider capacitance', 'pF', 0, 100000],
] as const;
const assumptionFields = [
  ['stray_c_pf', 'Stray capacitance', 'pF', 0, 100000],
  ['l_uh', 'Connection inductance', 'µH', 0, 10000],
] as const;
const customFields: [string, string, string, string][] = [
  ['max_stages', 'Available stages', '', '1'],
  ['stage_kv', 'Stage voltage rating', 'kV', 'any'],
  ['stage_c_uf', 'Stage capacitance', 'µF', 'any'],
  ['energy_stage_kj', 'Stage energy rating', 'kJ', 'any'],
  ['energy_total_kj', 'Total energy rating', 'kJ', 'any'],
  ['base_c_pf', 'Basic (internal) capacitance', 'pF', 'any'],
];

/** Plain explanation of what produced the plotted curve and its metrics. */
export function predictionBasis(run: Data | null | undefined, c: Data | null | undefined): string {
  if (!run || !c) return '';
  if (c.calibration) return 'Circuit prediction with a local correction from one shot (corrected metrics listed separately)';
  if (run.parameter_calibration_review) {
    const n = run.parameter_calibration_review.shots;
    return `Circuit prediction with generator parameters fitted from ${n} calibration shot${n === 1 ? '' : 's'}`;
  }
  if (run.inputs?.solver === 'circuit') return 'Circuit prediction';
  if ((c.ood?.trust_weight ?? 0) > 0) return 'Workbook metrics with ML correction; curve reconstructed from those metrics';
  if (run.inputs?.model_mode !== 'physics') return 'Outside validated ML range; workbook-equation metrics used, curve reconstructed from them';
  return 'Workbook-equation metrics; curve reconstructed from them';
}

const STEPS = ['Configure test', 'Recommend settings', 'Inspect waveform', 'Compare measurement'];

const PARAM_LABEL: Record<string, string> = {load_c_pf: 'test-object capacitance', divider_c_pf: 'divider capacitance', stray_c_pf: 'stray capacitance', l_uh: 'connection inductance'};

const PRESETS = [
  ['pdf-lightning', 'CPRI Lightning · matched example, assumed stock'],
  ['pdf-switching', 'CPRI Switching · assumed stock'],
  ['reference', 'Workbook Lightning · synthetic benchmark'],
  ['agreement', 'Workbook Lightning · agreement across models'],
  ['switching', 'Workbook Switching · constructible example'],
  ['ood', 'Workbook · outside ML support'],
  ['impossible', 'CPRI · out-of-range rejection'],
] as const;

function profileOutline(profile: Data | undefined): GeneratorModel | null {
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
    stageRatingKv: isNum(profile.stage_kv) ? profile.stage_kv : null,
    utilization: null,
    storedEnergyKj: null,
    front: {...empty, role: 'front'},
    tail: {...empty, role: 'tail'},
    stages: Array.from({length: profile.max_stages}, () => 'inactive'),
  };
}

export default function Optimizer() {
  const w = useWorkspace();
  const {inputs, setInputs, profiles, run, candidate: c, busy, error, optimize} = w;
  const [preset, setPreset] = useState('current');
  const [inventoryEnabled, setInventoryEnabled] = useState(false);
  const [draft, setDraft] = useState<InventoryDraft>(() => draftFromOverride(inputs.inventory_override));
  const [review, setReview] = useState<Data | null>(null);
  const [objects, setObjects] = useState<Data[]>([]);
  const [reference, setReference] = useState<Data | null>(null);
  const [refError, setRefError] = useState('');
  const [view, setView] = useState<SceneView>('overview');
  const [pulse, setPulse] = useState<{fraction: number; label: string} | null>(null);
  const [now, setNow] = useState(0);
  const custom = inputs.profile_id === CUSTOM_PROFILE_ID;
  const p = custom ? customProfileView(inputs.custom_profile) : profiles.find(x => x.id === inputs.profile_id);
  const stockUnknown = p ? p.units_per_value_per_stage == null : false;
  const customGaps = custom ? customProfileGaps(inputs.custom_profile) : [];
  const [crestUnit, setCrestUnit] = useState<'kV' | 'V'>('kV');

  useEffect(() => {
    setPreset('current');
  }, [inputs]);
  // Keep the stock table in step with saved/preset inventory (same rule as the original JSON editor).
  // A profile change always resets the stock table, matching profileInputs().
  const overrideKey = requestKey({o: inputs.inventory_override, profile: inputs.profile_id});
  useEffect(() => {
    setInventoryEnabled(!!inputs.inventory_override);
    setDraft(draftFromOverride(inputs.inventory_override));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overrideKey]);
  useEffect(() => {
    api('/api/test-objects')
      .then(d => setObjects(d.objects || []))
      .catch(() => setObjects([]));
  }, []);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, [run?.id]);

  const built = inventoryEnabled ? overrideFromDraft(draft) : null;
  const effectiveInventory = !inventoryEnabled ? null : built && 'value' in built ? built.value : {invalid: true};
  const {setDraftOverride} = w;
  const effectiveKey = requestKey({o: effectiveInventory});
  useEffect(() => {
    setDraftOverride({inventory_override: effectiveInventory});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveKey, setDraftOverride]);
  useEffect(() => () => setDraftOverride(null), [setDraftOverride]);
  const changed = w.draftEdited;

  function choosePreset(value: string) {
    setPreset(value);
    setReview(null);
    const vals: Data = {...workbookInputs};
    if (value === 'agreement') Object.assign(vals, {require_model_agreement: true});
    if (value === 'switching') Object.assign(vals, {impulse_type: 'Switching', test_kv: 1025, load_c_pf: 1240, divider_c_pf: 740, stray_c_pf: 320});
    if (value === 'ood') Object.assign(vals, {test_kv: 500});
    if (value === 'pdf-lightning' || value === 'pdf-switching') {
      const switching = value === 'pdf-switching';
      Object.assign(vals, initialInputs, {
        impulse_type: switching ? 'Switching' : 'Lightning',
        test_kv: switching ? 1050 : 1425,
        inventory_override: {
          front: [
            {ohm: 30, count_per_stage: 1},
            {ohm: 465, count_per_stage: 1},
            {ohm: 3700, count_per_stage: 1},
          ],
          tail: [{ohm: switching ? 22000 : 520, count_per_stage: 1}],
          provenance: 'Demo assumption: one unit per source value per stage; not verified CPRI stock',
        },
      });
    }
    if (value === 'impossible') Object.assign(vals, initialInputs, {test_kv: 2800});
    setInputs(vals);
  }

  const set = (patch: Data) => {
    setInputs({...inputs, ...patch});
    setReview(null);
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const values: Data = {...inputs};
    if (inventoryEnabled) {
      const result = overrideFromDraft(draft);
      if ('error' in result) {
        w.setError(result.error);
        return;
      }
      values.inventory_override = result.value;
    } else values.inventory_override = null;
    if (values.equipment_reference_kv || values.test_object_id) {
      try {
        const check = await post('/api/test-objects/validate', values);
        setReview(check);
        if (check.confirmation_required) return;
      } catch (err) {
        w.setError((err as Error).message);
        return;
      }
    }
    await optimize(values);
  }

  const model = useMemo(() => (run && c ? modelFromCandidate(run, c, run.profile) : profileOutline(p ?? undefined)), [run, c, p]);
  const measured = w.trial?.run_id === run?.id && w.trial?.candidate_id === c?.id ? comparisonWaveform(w.trial) : undefined;
  const measuredKind = w.trial ? trialSourceType(w.trial) : 'unknown';
  const onPulse = useCallback((v: {fraction: number; label: string} | null) => setPulse(v), []);
  useEffect(() => setPulse(null), [run?.id, c?.id]);
  const engineText = run?.inputs?.solver === 'reference' ? 'Reference model' : 'Circuit model';
  const disagreement = c?.circuit_crosscheck && !c.circuit_crosscheck.compliance.nominal_pass;

  return (
    <>
      <header className="workbench-heading">
        <div>
          <p className="page-tag">Impulse test setup</p>
          <h1>Recommend generator settings</h1>
          <ol className="workflow-steps" aria-label="Workflow">
            {STEPS.map((label, i) => {
              const done = i === 0 ? !!run : i < 3 ? !!run : !!(w.trial && w.trial.run_id === run?.id);
              const current = i === 0 ? !run : i === 1 ? !!run && changed : i === 2 ? !!run && !changed : false;
              const body = (
                <>
                  <span className="workflow-num">{done ? <Check size={13} aria-hidden /> : i + 1}</span>
                  {label}
                </>
              );
              return (
                <li key={label} className={`${done ? 'done' : ''} ${current ? 'current' : ''}`} aria-current={current ? 'step' : undefined}>
                  {i === 3 ? <Link href="/trial-calibrator/">{body}</Link> : i === 2 && run ? <a href="#results">{body}</a> : body}
                </li>
              );
            })}
          </ol>
        </div>
        <div className="page-actions">
          {run && (
            <a className="button small" href="#rlc-sensitivity">
              <SlidersHorizontal size={14} aria-hidden /> Explore R, L &amp; C
            </a>
          )}
          {run ? (
            <a className="button small" target="_blank" rel="noreferrer" href={apiUrl(`/api/runs/${run.id}/report`)}>
              <Download size={14} aria-hidden /> Export report
            </a>
          ) : (
            <span className="button small disabled" aria-disabled="true">
              <Download size={14} aria-hidden /> Export report
            </span>
          )}
        </div>
      </header>

      <div className="notices">
        {error && (
          <Notice tone="red" role="alert" title="No new recommendation generated">
            {error}
            {run && (
              <span className="notice-sub">
                Still showing saved run {shortId(run.id)} from {stamp(run.created_at)}
                {now ? ` (${age(run.created_at, now)})` : ''}. It does not answer the edited request.
              </span>
            )}
          </Notice>
        )}
        {stockUnknown && !inventoryEnabled && (
          <Notice tone="amber" title="Stock counts are required for this profile" id="stock-guidance">
            The source lists resistor values but no quantities. Enter counted stock with its provenance in <a href="#stock">Counted stock</a>, or choose a clearly labelled assumed-stock demo preset.
          </Notice>
        )}
        {inputs.parameter_calibration_id && (
          <Notice
            tone="info"
            title="Fitted generator parameters are in use"
            action={
              <button className="button small" type="button" onClick={() => set({parameter_calibration_id: null})}>
                Use the declared model
              </button>
            }
          >
            Predictions use loss, extra load capacitance and tail resistance fitted from calibration shots (record {inputs.parameter_calibration_id}). They apply to every setting of this generator and impulse type.
          </Notice>
        )}
        {inputs.require_model_agreement && (
          <Notice tone="info">Agreement search changes resistor settings and charging voltage to meet both model checks. It keeps the original tolerances and uncertainty assumptions. Model agreement is not laboratory validation.</Notice>
        )}
        {inputs.model_mode === 'experimental_v2' && (
          <Notice tone="amber" title="Experimental V2 selected">
            Evidence is limited to Train nested cross-validation; V2 has no Hidden Test or laboratory validation. V1 remains the default. {inputs.solver === 'circuit' ? 'Circuit mode still disables residual corrections.' : ''}
          </Notice>
        )}
        {inventoryEnabled && draft.provenance.trim() && (
          <Notice tone="neutral">
            <KindTag kind="assumption">Stock provenance</KindTag> {draft.provenance}
          </Notice>
        )}
      </div>

      <div className="workbench">
        <form className="request" onSubmit={submit} aria-labelledby="request-title">
          <div className="request-head">
            <h2 id="request-title">Configure test</h2>
            <label className="preset">
              <span className="sr-only">Demo preset</span>
              <select value={preset} onChange={e => choosePreset(e.target.value)} aria-label="Load a demo preset">
                <option value="current" disabled>
                  Demo presets…
                </option>
                {PRESETS.map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="field">
            <span>Generator profile</span>
            <select value={inputs.profile_id} onChange={e => setInputs(profileInputs(inputs, e.target.value))}>
              {profiles.map(x => (
                <option key={x.id} value={x.id}>
                  {x.name}
                  {!x.enabled ? ' · inspect only' : ''}
                </option>
              ))}
              {!profiles.length && !custom && <option value={inputs.profile_id}>Loading profiles…</option>}
              <option value={CUSTOM_PROFILE_ID}>Custom generator — enter complete ratings</option>
            </select>
          </label>
          <p className="request-source">
            {p ? (
              <>
                {p.source}
                {p.kind === 'synthetic_reference' ? '. Synthetic calculator and ML benchmark profile.' : p.id === 'cpri_problem_brief_profile' ? '. Primary CPRI physical reference; residual ML disabled. Load, parasitics and losses are operator inputs.' : custom ? '. Same series Marx equivalent circuit only; other topologies are not supported.' : '.'}{' '}
                {!custom && <Link href="/profiles/">Provenance</Link>}
              </>
            ) : (
              'Loading source provenance…'
            )}
          </p>

          {custom && (
            <fieldset className="custom-profile">
              <legend>Custom generator ratings</legend>
              <label className="field">
                <span>Name</span>
                <input value={inputs.custom_profile?.name ?? ''} onChange={e => set({custom_profile: {...inputs.custom_profile, name: e.target.value}})} placeholder="e.g. University lab 6-stage" />
              </label>
              <label className="field">
                <span>Source of these ratings</span>
                <input value={inputs.custom_profile?.source ?? ''} onChange={e => set({custom_profile: {...inputs.custom_profile, source: e.target.value}})} placeholder="Nameplate, manual or test certificate" />
              </label>
              <div className="request-fields">
                {customFields.map(([key, label, unit, step]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <span className="number-input">
                      <input type="number" min={key === 'max_stages' ? 2 : 0} step={step} value={inputs.custom_profile?.[key] ?? ''} onChange={e => set({custom_profile: {...inputs.custom_profile, [key]: e.target.value === '' ? null : Number(e.target.value)}})} />
                      {unit && <span>{unit}</span>}
                    </span>
                  </label>
                ))}
              </div>
              <small className="field-help">Energy ratings are checked against ½·C·V². Resistor values and counts come from the counted stock below.</small>
              {customGaps.length > 0 && <p className="field-error">Still needed: {customGaps.join(', ')}.</p>}
            </fieldset>
          )}

          <div className="request-impulse">
            <Segmented
              label="Impulse type"
              value={inputs.impulse_type}
              onChange={v => set({impulse_type: v, parameter_calibration_id: null})}
              options={[
                ['Lightning', <><Zap size={14} aria-hidden /> Lightning</>],
                ['Switching', <><Zap size={14} aria-hidden /> Switching</>],
              ]}
            />
            <span className="request-target">
              Challenge {inputs.impulse_type === 'Lightning' ? '1.2 / 50' : '250 / 2500'} µs
            </span>
          </div>

          <div className="field field-crest">
            <span id="crest-label">Desired crest voltage</span>
            <div className="crest-row">
              <span className="number-input">
                <input
                  required
                  type="number"
                  aria-labelledby="crest-label"
                  step="any"
                  min={0}
                  value={inputs.test_kv === '' || inputs.test_kv == null ? '' : crestUnit === 'V' ? Number((inputs.test_kv * 1000).toPrecision(12)) : inputs.test_kv}
                  onChange={e => set({test_kv: e.target.value === '' ? '' : crestUnit === 'V' ? Number(e.target.value) / 1000 : Number(e.target.value)})}
                />
                <span>{crestUnit}</span>
              </span>
              <Segmented size="small" label="Voltage unit" value={crestUnit} onChange={v => setCrestUnit(v as 'kV' | 'V')} options={[['kV', 'kV'], ['V', 'V']]} />
            </div>
            <small>
              {isNum(inputs.test_kv) ? `${fmt(inputs.test_kv, 3)} kV sent to the solver · ` : ''}profile range {fmt(p?.voltage_min_kv, 0)}–{fmt(p?.voltage_max_kv, 0)} kV
            </small>
          </div>
          <div className="request-fields">
            {primaryFields.map(([key, label, unit, min, max]) => (
              <label className="field" key={key}>
                <span>{label}</span>
                <span className="number-input">
                  <input required type="number" value={inputs[key] ?? ''} min={min} max={max} step="any" onChange={e => set({[key]: e.target.value === '' ? '' : Number(e.target.value)})} />
                  <span>{unit}</span>
                </span>
                {inputs.profile_id === 'workbook_reference_profile' && inputs[key] === workbookInputs[key] && <small>Workbook default</small>}
              </label>
            ))}
          </div>

          <details className="disclosure" id="assumptions">
            <summary>
              Circuit assumptions
              <small>
                stray {fmt(inputs.stray_c_pf, 0)} pF · L {fmt(inputs.l_uh, 1)} µH · {inputs.solver === 'circuit' ? 'extra loss' : 'efficiency'} {fmt(inputs.efficiency, 2)}
              </small>
              <ChevronDown size={16} className="chev" aria-hidden />
            </summary>
            <div className="disclosure-body">
              <div className="request-fields">
                {assumptionFields.map(([key, label, unit, min, max]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <span className="number-input">
                      <input required type="number" value={inputs[key] ?? ''} min={min} max={max} step="any" onChange={e => set({[key]: e.target.value === '' ? '' : Number(e.target.value)})} />
                      <span>{unit}</span>
                    </span>
                  </label>
                ))}
                <label className="field">
                  <span>{inputs.solver === 'circuit' ? 'Additional loss factor' : 'Overall efficiency (workbook)'}</span>
                  <span className="number-input">
                    <input required type="number" value={inputs.efficiency ?? ''} min={0.051} max={1} step="any" onChange={e => set({efficiency: e.target.value === '' ? '' : Number(e.target.value)})} />
                    <span>η</span>
                  </span>
                </label>
              </div>
              <p className="field-help">
                {inputs.solver === 'circuit'
                  ? 'The circuit already computes its own voltage utilisation (divider and tail losses). This factor is applied on top for losses it does not model, such as spark gaps; 1.0 means none. Do not enter the workbook’s overall efficiency here.'
                  : 'The workbook equations assume crest = stages × charge × efficiency.'}{' '}
                These are editable assumptions, not measured machine facts; they are saved with every run.
              </p>
            </div>
          </details>

          <details className="disclosure" id="stock" open={stockUnknown || inventoryEnabled}>
            <summary>
              Counted stock
              <small>{inventoryEnabled ? 'Explicit inventory' : stockUnknown ? 'Required' : `Profile stock · ${p?.units_per_value_per_stage ?? '—'} per value per stage`}</small>
              <ChevronDown size={16} className="chev" aria-hidden />
            </summary>
            <div className="disclosure-body">
              <label className="checkbox">
                <input type="checkbox" checked={inventoryEnabled} onChange={e => setInventoryEnabled(e.target.checked)} />
                <span>
                  Use explicit inventory
                  <small>CPRI source values do not specify quantities. Enter verified counts or explicitly label the stock assumption.</small>
                </span>
              </label>
              {inventoryEnabled && <InventoryEditor draft={draft} onChange={setDraft} profile={p} impulse={inputs.impulse_type} idPrefix="opt" />}
              {inventoryEnabled && built && 'error' in built && <p className="field-error">{built.error}</p>}
            </div>
          </details>

          <details className="disclosure">
            <summary>
              <Settings2 size={15} aria-hidden /> Engine and limits
              <small>{inputs.solver === 'circuit' ? 'Marx / RLC circuit' : 'Reference equations'} · ±{fmt(inputs.uncertainty_pct, 0)}%</small>
              <ChevronDown size={16} className="chev" aria-hidden />
            </summary>
            <div className="disclosure-body">
              <label className="field">
                <span>Prediction engine</span>
                <select value={inputs.solver} onChange={e => setInputs(solverInputs(inputs, e.target.value))}>
                  <option value="reference">Reference equations + circuit cross-check</option>
                  <option value="circuit">Equivalent Marx / RLC circuit · physics only</option>
                </select>
              </label>
              {inputs.solver === 'reference' && (
                <label className="checkbox">
                  <input type="checkbox" checked={!!inputs.require_model_agreement} onChange={e => set({require_model_agreement: e.target.checked})} />
                  Require both models to meet nominal limits
                </label>
              )}
              <label className="field">
                <span>Residual correction</span>
                <select
                  disabled={inputs.solver === 'circuit' || inputs.profile_id !== 'workbook_reference_profile'}
                  value={inputs.solver === 'circuit' || inputs.profile_id !== 'workbook_reference_profile' ? 'physics' : inputs.model_mode}
                  onChange={e => set({model_mode: e.target.value})}
                >
                  <option value="hybrid">V1 · default trust-gated hybrid</option>
                  <option value="experimental_v2">V2 candidate · development evidence</option>
                  <option value="physics">Physics only</option>
                </select>
                <small>
                  {inputs.profile_id !== 'workbook_reference_profile'
                    ? 'Residual transfer to this physical profile is unsupported; ML remains off.'
                    : inputs.solver === 'circuit'
                      ? 'Circuit mode uses physical simulation; workbook residual ML remains off.'
                      : 'V1 is the frozen default for supported workbook settings.'}
                </small>
              </label>
              <label className="field">
                <span>Parasitic uncertainty ± (%)</span>
                <input type="number" min="0" max="30" step="any" value={inputs.uncertainty_pct} onChange={e => set({uncertainty_pct: Number(e.target.value)})} />
                <small>Assumed independent ranges in C and L.</small>
              </label>
              <div className="two-fields">
                {(['stage_min', 'stage_max'] as const).map(k => (
                  <label className="field" key={k}>
                    <span>{k === 'stage_min' ? 'Min stages' : 'Max stages'}</span>
                    <input type="number" placeholder="Profile" min="2" max="30" value={inputs[k] ?? ''} onChange={e => set({[k]: e.target.value ? Number(e.target.value) : null})} />
                  </label>
                ))}
              </div>
              <label className="field">
                <span>Layout identifier</span>
                <input required value={inputs.layout_id} onChange={e => set({layout_id: e.target.value})} />
                <small>Series Marx equivalent connection.</small>
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={!!inputs.include_base_c} onChange={e => set({include_base_c: e.target.checked})} />
                <span>
                  Include profile base capacitance{isNum(p?.base_c_pf) ? ` (${fmt(p!.base_c_pf, 0)} pF)` : ''}
                  <small>Exclude it if the divider or system inputs already represent it.</small>
                </span>
              </label>
            </div>
          </details>

          <details className="disclosure" open={!!(inputs.equipment_reference_kv || inputs.test_object_id || review)}>
            <summary>
              Equipment reference
              <small>{inputs.equipment_reference_kv ? `${fmt(inputs.equipment_reference_kv, 0)} kV · operator` : inputs.test_object_id ? 'Catalog entry' : 'Optional'}</small>
              <ChevronDown size={16} className="chev" aria-hidden />
            </summary>
            <div className="disclosure-body">
              <p className="field-help">Equipment test levels are separate from generator capacity. Catalog levels can be unknown; an operator value needs a source.</p>
              <label className="field">
                <span>Catalog reference</span>
                <select value={inputs.test_object_id || ''} onChange={e => set({test_object_id: e.target.value || null, confirm_reference_mismatch: false})}>
                  <option value="">No catalog selection</option>
                  {objects
                    .filter(o => o.impulse_type === inputs.impulse_type)
                    .map(o => (
                      <option key={o.id} value={o.id}>
                        {o.name} · {o.recommended_test_level_kv ? `${o.recommended_test_level_kv} kV` : 'level unknown'}
                      </option>
                    ))}
                </select>
              </label>
              <label className="field">
                <span>Operator reference voltage</span>
                <span className="number-input">
                  <input type="number" min="1" placeholder="Optional verified reference" value={inputs.equipment_reference_kv ?? ''} onChange={e => set({equipment_reference_kv: e.target.value ? Number(e.target.value) : null, confirm_reference_mismatch: false})} />
                  <span>kV</span>
                </span>
              </label>
              {inputs.equipment_reference_kv && (
                <label className="field">
                  <span>Reference source</span>
                  <input required value={inputs.equipment_reference_source || ''} onChange={e => set({equipment_reference_source: e.target.value})} placeholder="Document, clause or person" />
                </label>
              )}
              {(inputs.equipment_reference_kv || inputs.test_object_id) && (
                <label className="checkbox">
                  <input type="checkbox" checked={!!inputs.confirm_reference_mismatch} onChange={e => setInputs({...inputs, confirm_reference_mismatch: e.target.checked})} />
                  I verified that any mismatch with this reference is intentional.
                </label>
              )}
              {review && (
                <Notice tone={review.confirmation_required ? 'amber' : review.mismatch ? 'amber' : 'neutral'} role="status" title={human(review.status)}>
                  {review.message}
                  {review.confirmation_required && <span className="notice-sub">Tick the confirmation above, then optimize again. Nothing was solved.</span>}
                </Notice>
              )}
            </div>
          </details>

          <div className="request-submit">
            <button className="button primary large full" disabled={busy || p?.enabled === false || (stockUnknown && !inventoryEnabled) || customGaps.length > 0} type="submit" aria-describedby={stockUnknown && !inventoryEnabled ? 'stock-guidance' : undefined}>
              {busy ? <LoaderCircle className="spin" size={18} aria-hidden /> : <Sparkles size={18} aria-hidden />}
              {busy ? 'Solving request…' : 'Recommend settings'}
            </button>
            <p>
              {p?.enabled === false
                ? 'This profile is incomplete and can only be inspected.'
                : customGaps.length > 0
                  ? 'Complete the custom generator ratings first.'
                  : stockUnknown && !inventoryEnabled
                    ? 'Supply stock counts or choose an assumed-stock demo.'
                    : 'Voltage, energy and stock limits are enforced; impossible requests are rejected.'}
            </p>
          </div>
        </form>

        <div className="workbench-main">
        <section id="results" className={`hall ${changed ? 'hall-stale' : ''}`} aria-label="Recommended settings: waveform and conceptual generator stack">
          <div className="hall-bar">
            <div className="hall-id">
              {run && c ? (
                <>
                  <strong>
                    Run {shortId(run.id)} · rank {c.rank}
                  </strong>
                  <span>
                    {run.inputs.impulse_type} {fmt(run.inputs.test_kv, 0)} kV · {run.profile?.name} · {engineText.toLowerCase()} · saved {stamp(run.created_at)}
                  </span>
                </>
              ) : (
                <>
                  <strong>No saved recommendation</strong>
                  <span>{p ? `${p.name} outline · ${p.max_stages} stages` : 'Profile outline appears once profiles load'}</span>
                </>
              )}
            </div>
            <Segmented
              size="small"
              label="Camera view"
              value={view}
              onChange={setView}
              options={[
                ['overview', 'Overview'],
                ['stack', 'Stages'],
                ['front', 'Front bank'],
                ['tail', 'Tail bank'],
                ['output', 'Output'],
              ]}
            />
          </div>
          {busy && (
            <div className="hall-status">
              <Working>Solving on the local engine. The saved result below stays until a new one is returned.</Working>
            </div>
          )}
          {changed && !busy && (
            <div className="hall-status hall-status-stale">Showing saved run {shortId(run?.id)}. Your edited request has not been solved; optimize to update.</div>
          )}
          <div className="hall-body">
            <div className="hall-scope">
              {run && c ? (
                <Scope
                  run={run}
                  candidate={c}
                  measured={measured ? {...measured, kind: measuredKind} : undefined}
                  measuredLabel={`Uploaded trial · ${sourceLabel(measuredKind).toLowerCase()}`}
                  onPulse={onPulse}
                  revealKey={w.runSerial}
                  height={318}
                />
              ) : (
                <div className="scope-empty">
                  <svg viewBox="0 0 320 120" aria-hidden>
                    <path d="M8 108 H312" stroke="#2c3d4a" />
                    <path d="M8 108 C18 108 22 22 34 22 C70 22 120 70 312 96" fill="none" stroke="#2c3d4a" strokeDasharray="4 5" strokeWidth="2" />
                  </svg>
                  <h3>{busy ? 'Solving your first setup…' : 'The waveform appears after a recommendation'}</h3>
                  <p>Curves come only from saved backend results: circuit simulations, metric reconstructions or uploaded captures, each labelled.</p>
                </div>
              )}
            </div>
            <div className="hall-scene">
              <GeneratorView
                model={model}
                view={view}
                pulse={pulse}
                playKey={w.runSerial}
                height="100%"
                caption={run && c ? `${c.settings.stages} of ${model?.maxStages ?? '—'} stages · front ${c.front_network.topology} · tail ${c.tail_network.topology}` : 'Profile outline only · no recommendation yet'}
                emptyText="Profiles are loading."
              />
            </div>
          </div>
          {run && c && <MetricGauges candidate={c} impulse={run.inputs.impulse_type} theme="hall" />}
          {run && c && (
            <p className="hall-basis">
              <strong>{predictionBasis(run, c)}.</strong>{' '}
              {c.waveform_consistency?.primary?.metrics
                ? c.waveform_consistency.consistent
                  ? `Metrics above are re-extracted from the plotted curve (largest difference ${fmt(100 * Math.max(...Object.values(c.waveform_consistency.primary.metrics as Data).map((m: Data) => m.relative_difference)), 4)}%).`
                  : 'Warning: metrics re-extracted from the plotted curve do not match the reported metrics; review before use.'
                : ''}{' '}
              Nominal compliance uses the point prediction; the uncertainty envelope is reported separately below.
            </p>
          )}
        </section>

      {run && c && (
        <div className="setup-grid">
          <section className="setup" aria-labelledby="setup-title">
            <div className="setup-head">
              <div>
                <p className="page-tag">Rank {c.rank} · {engineText}</p>
                <h2 id="setup-title">{c.compliance.nominal_pass ? 'Recommended setup' : 'Closest setup found · waveform outside limits'}</h2>
              </div>
              <div className="heading-actions">
                <PassFail pass={c.compliance.nominal_pass} passText="Waveform inside limits" failText="Waveform outside limits" />
                <PassFail pass={c.settings.voltage_margin_kv_stage >= 0 && c.settings.energy_margin_kj >= 0} passText="Within voltage, energy and stock limits" failText="Hardware limit exceeded" />
              </div>
            </div>
            <div className="setup-hero">
              <div className="setup-number">
                <strong>{c.settings.stages}</strong>
                <span>active stages of {run.profile?.max_stages ?? '—'}</span>
              </div>
              <span className="setup-times" aria-hidden>
                ×
              </span>
              <div className="setup-number">
                <strong>{fmt(c.settings.charge_kv_stage, 2)}</strong>
                <span>kV charge per stage · rating {fmt(run.profile?.stage_kv, 0)} kV</span>
              </div>
            </div>
            {disagreement && (
              <Notice
                tone="amber"
                title="Independent circuit waveform outside limits"
                action={
                  !run.inputs.require_model_agreement && (
                    <button className="button small" disabled={busy} onClick={() => optimize({...run.inputs, require_model_agreement: true, calibration_id: null})}>
                      <ShieldCheck size={14} aria-hidden /> Find settings passing both models
                    </button>
                  )
                }
              >
                {c.circuit_crosscheck.compliance.rows
                  .filter((r: Data) => !r.pass)
                  .map((r: Data) => r.name)
                  .join(' + ')}{' '}
                · an engineering diagnostic, not a software-test failure.
              </Notice>
            )}
            <div className="networks">
              {(
                [
                  ['Front', c.front_network, model?.front],
                  ['Tail', c.tail_network, model?.tail],
                ] as const
              ).map(([name, net, nm]) => (
                <article className="network" key={name}>
                  <header>
                    <span>{name} resistor per stage</span>
                    <strong>
                      {fmt(name === 'Front' ? c.settings.front_r_stage : c.settings.tail_r_stage, 2)} <small>Ω</small>
                    </strong>
                  </header>
                  {nm && <NetworkSchematic net={nm} />}
                  <p className="network-topology">{net.topology}</p>
                  <div className="table-wrap compact-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Value</th>
                          <th className="num">Per stage</th>
                          <th className="num">Total</th>
                          <th className="num">Stock / stage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {net.components.map((part: Data) => (
                          <tr key={part.ohm}>
                            <td>{fmt(part.ohm, part.ohm % 1 ? 2 : 0)} Ω</td>
                            <td className="num">{part.count_per_stage}</td>
                            <td className="num">{part.total_required ?? '—'}</td>
                            <td className="num">{part.available_per_stage ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="network-foot">{net.total_components} components across all active stages</p>
                </article>
              ))}
            </div>
            <div className="margins">
              <div>
                <span>Stage headroom</span>
                <strong>{fmt(c.settings.voltage_margin_kv_stage, 2)} kV</strong>
              </div>
              <div>
                <span>Stored energy</span>
                <strong>{fmt(c.settings.stored_energy_kj, 2)} kJ</strong>
              </div>
              <div>
                <span>Energy headroom</span>
                <strong>
                  {fmt(c.settings.energy_margin_kj, 2)} kJ{isNum(c.settings.energy_margin_pct) ? ` · ${fmt(c.settings.energy_margin_pct, 1)}%` : ''}
                </strong>
              </div>
              <div>
                <span>Stage-voltage use</span>
                <strong>{fmt(c.settings.stage_utilization * 100, 1)}%</strong>
              </div>
              <div>
                <span>Total components</span>
                <strong>{c.setup_component_count}</strong>
              </div>
            </div>
          </section>

          <aside className="candidates" aria-labelledby="cand-title">
            <div className="candidates-head">
              <h2 id="cand-title">Ranked alternatives</h2>
              <span>
                {run.search?.hardware_feasible ?? '—'} hardware-feasible of {run.search?.evaluated ?? '—'} evaluated
              </span>
            </div>
            <ol className="candidate-list">
              {run.candidates.map((item: Data, i: number) => {
                const max = run.profile?.max_stages || item.settings.stages;
                const state = item.compliance.robust_pass ? 'robust' : item.compliance.nominal_pass ? 'nominal' : 'fail';
                return (
                  <li key={item.id}>
                    <button className={`candidate ${w.selected === i ? 'selected' : ''}`} aria-pressed={w.selected === i} onClick={() => w.setSelected(i)}>
                      <span className="candidate-rank">{item.rank ?? i + 1}</span>
                      <span className="candidate-body">
                        <strong>
                          {item.settings.stages} stages · {fmt(item.settings.charge_kv_stage, 1)} kV
                        </strong>
                        <small>
                          Rf {fmt(item.settings.front_r_stage, 1)} Ω · Rt {fmt(item.settings.tail_r_stage, 1)} Ω · {item.setup_component_count} parts
                        </small>
                        <span className="candidate-stages" aria-hidden>
                          {Array.from({length: max}, (_, k) => (
                            <i key={k} className={k < item.settings.stages ? 'on' : ''} />
                          ))}
                        </span>
                      </span>
                      <span className={`candidate-state candidate-${state}`}>
                        {state === 'robust' ? <Check size={13} aria-hidden /> : state === 'fail' ? <TriangleAlert size={13} aria-hidden /> : null}
                        {state === 'robust' ? 'Robust' : state === 'nominal' ? 'Nominal' : 'Fails'}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            <p className="candidates-note">Nominal = predicted waveform inside the challenge limits. Robust = the uncertainty envelope is also inside.</p>
            <div className="candidates-links">
              <Link className="button small" href="/compare/">
                <GitCompareArrows size={14} aria-hidden /> Compare scores &amp; plans
              </Link>
              <Link className="button small primary" href="/trial-calibrator/">
                <FlaskConical size={14} aria-hidden /> Compare a measured waveform
              </Link>
            </div>
          </aside>
        </div>
      )}
        </div>
      </div>

      {run && c && (
        <details className="evidence-disclosure" id="evidence">
          <summary>
            <span>
              <strong>Engineering evidence and diagnostics</strong>
              <small>Limits and envelope, fixed-setting challenge, scenario checks, why this setup, models, R/L/C sensitivity</small>
            </span>
            <ChevronDown size={18} className="chev" aria-hidden />
          </summary>
          <div className="section-title">
            <h2>Evidence for rank {c.rank}</h2>
            <nav className="anchor-nav" aria-label="Evidence sections">
              <a href="#limits">Limits &amp; envelope</a>
              <a href="#evidence-level">Evidence level</a>
              {c.verification && <a href="#challenge">Fixed-setting challenge</a>}
              {c.model_agreement && <a href="#agreement">Model agreement</a>}
              <a href="#why">Why this setup</a>
              <a href="#models">Models &amp; parity</a>
              <a href="#rlc-sensitivity">R, L &amp; C</a>
              {run.calibration_review && <a href="#calibration">Calibration review</a>}
            </nav>
          </div>
          <div className="evidence-grid">
            <Panel id="limits" title={run.inputs.solver === 'reference' ? 'Reference-model limits' : 'Circuit-model limits'} eyebrow="Nominal prediction and uncertainty envelope are separate results" action={<Status value={c.compliance.status} />}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th className="num">Nominal</th>
                      <th className="num">Allowed</th>
                      <th className="num">Envelope</th>
                      <th>Nominal check</th>
                      <th>Envelope inside limits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.compliance.rows.map((r: Data, i: number) => (
                      <tr key={r.name}>
                        <td>{r.name}</td>
                        <td className="num">
                          {fmt(r.predicted, i === 2 ? 1 : 3)} {r.unit}
                          <small className="block">{signed(r.deviation_pct)}% vs target</small>
                        </td>
                        <td className="num">
                          {fmt(r.lower, i === 2 ? 0 : 2)}–{fmt(r.upper, i === 2 ? 0 : 2)}
                        </td>
                        <td className="num">
                          {fmt(c.uncertainty.lower[i], i === 2 ? 1 : 3)}–{fmt(c.uncertainty.upper[i], i === 2 ? 1 : 3)}
                        </td>
                        <td>
                          <PassFail pass={r.pass} passText="PASS" failText="FAIL" />
                        </td>
                        <td>
                          <Badge tone={r.robust ? 'green' : 'amber'}>{r.robust ? 'Within limits' : 'Overlaps limit'}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">
                {c.uncertainty.method}. {c.uncertainty.coverage_claim ? c.uncertainty.coverage_limit || 'Synthetic coverage only; no laboratory coverage claim.' : c.uncertainty.coverage_limit || ''} Parasitic variation ±{run.inputs.uncertainty_pct}% included.
              </p>
              <div className="support">
                <ShieldCheck size={18} aria-hidden />
                <div>
                  <strong>
                    {run.inputs.profile_id === 'cpri_problem_brief_profile'
                      ? 'CPRI physics · residual ML disabled'
                      : c.ood.state === 'physics_mode'
                        ? 'Physics-only mode · residual disabled'
                        : c.ood.trust_weight >= 0.99
                          ? 'ML inside training support'
                          : c.ood.trust_weight > 0
                            ? 'ML correction reduced'
                            : 'Physics-led · outside ML support'}{' '}
                    <Badge tone={c.ood.trust_weight >= 0.99 ? 'cyan' : 'amber'}>{human(c.ood.state)}</Badge>
                  </strong>
                  <p>
                    Residual weight {fmt(c.ood.trust_weight, 2)} · nearest training distance {fmt(c.ood.nearest_distance, 2)}. {c.ood.lab_calibrated ? 'Local laboratory calibration applied.' : 'No measured laboratory calibration.'}
                  </p>
                </div>
              </div>
            </Panel>
            {run.parameter_calibration_review && (
              <Panel id="fitted-parameters" title="Fitted generator parameters" eyebrow={`From ${run.parameter_calibration_review.shots} calibration shot(s) · ${run.parameter_calibration_review.source_type === 'measured_lab' ? 'measured' : 'generated or simulated'}`}>
                <div className="crosscheck">
                  <div>
                    <span>Loss scale on the assumed factor</span>
                    <strong>×{fmt(run.parameter_calibration_review.parameters.loss_scale, 4)}</strong>
                  </div>
                  <div>
                    <span>Extra load-side capacitance</span>
                    <strong>{fmt(run.parameter_calibration_review.parameters.extra_load_pf, 1)} pF</strong>
                  </div>
                  <div>
                    <span>Effective tail resistance</span>
                    <strong>×{fmt(run.parameter_calibration_review.parameters.tail_scale, 4)}</strong>
                  </div>
                </div>
                <p className="panel-note">{run.parameter_calibration_review.note} These are effective values of the lumped circuit, not measured component values.</p>
              </Panel>
            )}
            <Panel id="scenarios" title="Parasitic scenario checks" eyebrow="Finite simulation evidence, not a probability of laboratory success">
              <div className="scenario">
                <div className="scenario-top">
                  <span>Search scenarios passing nominal limits</span>
                  <strong>
                    {c.robustness.samples ? `${Math.round((c.robustness.nominal_scenario_pass_pct / 100) * c.robustness.samples)} of ${c.robustness.samples}` : '—'}
                  </strong>
                </div>
                <div className="meter" role="img" aria-label={`${fmt(c.robustness.nominal_scenario_pass_pct, 0)} percent of ${c.robustness.samples} sampled scenarios`}>
                  <span style={{width: `${Math.max(0, Math.min(100, c.robustness.nominal_scenario_pass_pct || 0))}%`}} />
                </div>
                <small>
                  Each scenario varies load, divider, stray capacitance and inductance by up to ±{fmt(run.inputs.uncertainty_pct, 0)}% and re-runs the prediction. Most sensitive input: {PARAM_LABEL[c.robustness.most_sensitive_parameter] || c.robustness.most_sensitive_parameter}.
                </small>
              </div>
            </Panel>
            <Panel id="evidence-level" title="Recommendation evidence" eyebrow="Highest evidence activity attained; not a safety score">
              <EvidenceCard evidence={c.evidence} />
            </Panel>
          </div>
          {c.verification && (
            <div id="challenge" className="anchor-target">
              <SettingsVerification candidate={c} />
            </div>
          )}
          {c.model_agreement && (
            <Panel
              id="agreement"
              title="Agreement across two models"
              action={
                <Badge tone={c.model_agreement.both_nominal_pass ? 'green' : 'red'}>{c.model_agreement.both_nominal_pass ? 'Both nominal checks pass' : 'No agreement found'}</Badge>
              }
            >
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th className="num">Reference prediction</th>
                      <th className="num">Independent circuit</th>
                      <th className="num">Allowed range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.compliance.rows.map((r: Data, i: number) => (
                      <tr key={r.name}>
                        <td>{r.name}</td>
                        <td className="num">
                          {fmt(r.predicted, 3)} {r.unit}
                        </td>
                        <td className="num">
                          {fmt(c.circuit_crosscheck?.[['front_us', 'tail_us', 'crest_kv'][i]], 3)} {r.unit}
                        </td>
                        <td className="num">
                          {fmt(r.lower, 2)}–{fmt(r.upper, 2)} {r.unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {c.model_agreement.raw_crest_charge_windows && !c.model_agreement.raw_crest_charge_windows.overlap && (
                <Notice tone="amber">
                  Charging voltage alone cannot reconcile crest at this resistor network. Raw reference needs {fmt(c.model_agreement.raw_crest_charge_windows.reference_kv_stage[0], 2)}–{fmt(c.model_agreement.raw_crest_charge_windows.reference_kv_stage[1], 2)} kV/stage; the circuit needs{' '}
                  {fmt(c.model_agreement.raw_crest_charge_windows.circuit_kv_stage[0], 2)}–{fmt(c.model_agreement.raw_crest_charge_windows.circuit_kv_stage[1], 2)} kV/stage. These ranges do not overlap, even before hardware caps.
                </Notice>
              )}
              <p className="panel-note">
                Both models pass in {fmt(c.model_agreement.sampled_both_pass_pct, 1)}% of {c.model_agreement.scenario_count} sampled parasitic scenarios. This fraction is not a probability of laboratory success. {c.model_agreement.scope} The separate uncertainty-envelope result remains {c.compliance.status}.
              </p>
            </Panel>
          )}
          <div className="evidence-grid">
            <Panel id="why" title="Why this configuration?" action={<Badge tone="cyan">Explainable ranking</Badge>}>
              <ol className="explanation">
                {c.explanation.map((s: string) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Layer</th>
                      <th className="num">{run.inputs.impulse_type === 'Switching' ? 'Peak' : 'Front'} µs</th>
                      <th className="num">Tail µs</th>
                      <th className="num">Crest kV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Physics', c.physics],
                      ['Final prediction', c.hybrid],
                    ].map(([name, v]) => (
                      <tr key={String(name)}>
                        <td>{String(name)}</td>
                        <td className="num">{fmt((v as Data).front_us, 4)}</td>
                        <td className="num">{fmt((v as Data).tail_us, 3)}</td>
                        <td className="num">{fmt((v as Data).crest_kv, 2)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td>Applied ML correction</td>
                      {c.correction.map((v: number, i: number) => (
                        <td key={i} className="num">
                          {signed(v, i === 0 ? 5 : 3)}
                        </td>
                      ))}
                    </tr>
                    {Array.isArray(c.raw_residual) && (
                      <tr>
                        <td>
                          Raw residual (before support gate)
                          <small className="block">Trust weight {fmt(c.ood.trust_weight, 2)} applied</small>
                        </td>
                        {c.raw_residual.map((v: number, i: number) => (
                          <td key={i} className="num muted">
                            {signed(v, i === 0 ? 5 : 3)}
                          </td>
                        ))}
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">Most sensitive parameter: {PARAM_LABEL[c.robustness.most_sensitive_parameter] || human(c.robustness.most_sensitive_parameter)}. Sensitivity uses a separate +5% physics perturbation.</p>
            </Panel>
            <Panel id="models" title={run.inputs.solver === 'circuit' ? 'Primary circuit model' : 'Independent physics cross-check'} action={<Badge tone="amber">Model limitations</Badge>}>
              {c.circuit_crosscheck ? (
                <>
                  <Notice tone="amber">Reference formulas and the equivalent circuit can disagree. A reference PASS is not laboratory validation.</Notice>
                  <div className="crosscheck">
                    <div>
                      <span>{run.inputs.impulse_type === 'Switching' ? 'Peak time' : 'Front time'}</span>
                      <strong>{fmt(c.circuit_crosscheck.front_us, 3)} µs</strong>
                    </div>
                    <div>
                      <span>Time to half</span>
                      <strong>{fmt(c.circuit_crosscheck.tail_us, 2)} µs</strong>
                    </div>
                    <div>
                      <span>Crest</span>
                      <strong>{fmt(c.circuit_crosscheck.crest_kv, 1)} kV</strong>
                    </div>
                  </div>
                  <p className="crosscheck-status">
                    Circuit numeric compliance <Status value={c.circuit_crosscheck.compliance.status} />
                  </p>
                </>
              ) : (
                <p className="panel-note">The equivalent Marx / RLC circuit is the primary model in this run. Residual ML is disabled. A separate second-model comparison was not performed.</p>
              )}
              {c.physics?.diagnostics?.model && (
                <dl className="kv model-kv">
                  <div>
                    <dt>Circuit model</dt>
                    <dd>{c.physics.diagnostics.model}</dd>
                  </div>
                  {c.physics.diagnostics.limitations && (
                    <div>
                      <dt>Limitations</dt>
                      <dd>{c.physics.diagnostics.limitations}</dd>
                    </div>
                  )}
                </dl>
              )}
              <details className="source-details">
                <summary>Source parity evidence</summary>
                <p className="panel-note">Reproduce the supplied Lightning calculator separately from the inventory optimizer.</p>
                <button
                  className="button small"
                  onClick={async () => {
                    setRefError('');
                    try {
                      setReference(await api('/api/reference'));
                    } catch (e) {
                      setRefError((e as Error).message);
                    }
                  }}
                >
                  <Check size={14} aria-hidden /> Load golden workbook case
                </button>
                {reference && (
                  <div className="reference-result">
                    <Badge tone="green">Golden case verified</Badge>
                    <p>
                      {fmt(reference.hybrid.front_us, 5)} / {fmt(reference.hybrid.tail_us, 5)} µs · {fmt(reference.hybrid.crest_kv, 4)} kV
                    </p>
                    <small>Exact cached case and formula parity. The workbook’s hardcoded validation metric table remains inconsistent with formula-based evaluation.</small>
                  </div>
                )}
                {refError && <p className="negative">{refError}</p>}
                <a href={apiUrl('/api/documents/source_reconciliation')} target="_blank" rel="noreferrer">
                  Read the documented discrepancy <ArrowRight size={13} aria-hidden />
                </a>
              </details>
            </Panel>
          </div>
          <RlcSensitivity run={run} candidate={c} />
          {run.calibration_review && (
            <Panel
              id="calibration"
              title="Local calibration review"
              action={<Badge tone={run.calibration_review.applied ? 'cyan' : 'amber'}>{run.calibration_review.applied ? 'Matched configuration corrected' : 'No matching scope'}</Badge>}
            >
              <p className="panel-note">{run.calibration_review.reason || run.calibration_review.next_adjustment_note}</p>
              {run.calibration_review.corrected_prediction && (
                <div className="crosscheck">
                  <div>
                    <span>Corrected front / peak</span>
                    <strong>{fmt(run.calibration_review.corrected_prediction.front_us, 3)} µs</strong>
                  </div>
                  <div>
                    <span>Corrected tail</span>
                    <strong>{fmt(run.calibration_review.corrected_prediction.tail_us, 3)} µs</strong>
                  </div>
                  <div>
                    <span>Corrected crest</span>
                    <strong>{fmt(run.calibration_review.corrected_prediction.crest_kv, 2)} kV</strong>
                  </div>
                </div>
              )}
              <p className="panel-note">
                {run.calibration_review.applied
                  ? run.calibration_review.retained_in_top_five
                    ? 'The matched configuration remains in the top five.'
                    : 'The matched configuration ranked outside the top five; its corrected evidence is retained.'
                  : 'No correction applied.'}
                {run.calibration_review.source_type ? ` Calibration source: ${sourceLabel(run.calibration_review.source_type === 'generated_stress_test' ? 'generated_demo' : run.calibration_review.source_type).toLowerCase()}.` : ''}
              </p>
            </Panel>
          )}
          <div className="run-footer">
            <span>
              Run <code>{run.id}</code> · saved {stamp(run.created_at)} · {run.model_version}
            </span>
            <a href={apiUrl(`/api/runs/${run.id}/json`)}>
              <ArrowDownToLine size={14} aria-hidden /> Download audit JSON
            </a>
          </div>
        </details>
      )}
    </>
  );
}
