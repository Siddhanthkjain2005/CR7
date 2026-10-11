'use client';

import {useId, useMemo, useState} from 'react';
import {ArrowRight, Box, Check, ChevronRight, CircleHelp, GripVertical, Layers3, Minus, Plus, RotateCcw, ShieldAlert, TriangleAlert} from 'lucide-react';
import {Data, fmt, isNum, shortId} from '@/lib/api';
import {ohmText} from '@/lib/generator-model';
import {useQuietMotion} from '@/lib/motion';
import {ASSEMBLY_ORDER, AssemblyPartId, AssemblyTwinModel, assemblyModelFromCandidate, canPlaceAssemblyPart} from '@/lib/assembly-twin';
import GeneratorView from './generator/generator-view';
import NetworkSchematic from './network-schematic';

export interface AssemblyTwinProps {
  run: Data;
  candidate: Data;
  /** The draft no longer matches the saved recommendation represented here. */
  draftEdited?: boolean;
}

const SPOTS: Record<AssemblyPartId, {x: number; y: number; color: string}> = {
  stages: {x: 135, y: 195, color: '#75ddd6'},
  front: {x: 355, y: 125, color: '#e7ad78'},
  tail: {x: 355, y: 292, color: '#d8a4b9'},
  inductance: {x: 565, y: 125, color: '#b5c7ee'},
  load: {x: 760, y: 220, color: '#b9dcb6'},
};

function partValue(part: AssemblyPartId, model: AssemblyTwinModel): string {
  if (part === 'stages') return `${model.generator.activeStages} active stages`;
  if (part === 'front') return `${ohmText(model.frontPerStageOhm)} / stage`;
  if (part === 'tail') return `${ohmText(model.tailPerStageOhm)} / stage`;
  if (part === 'inductance') return `${fmt(model.inductanceUh, 3)} µH`;
  return `${fmt(model.capacitance.totalPf, 2)} pF · nominal total`;
}

function matchingNetwork(setting: number | null, equivalent: number | null): boolean {
  return isNum(setting) && isNum(equivalent) && Math.abs(setting - equivalent) <= Math.max(1e-6, Math.abs(setting) * 1e-6);
}

function PartGlyph({part, count, placed}: {part: AssemblyPartId; count: number; placed: boolean}) {
  if (part === 'stages') {
    const visible = Math.min(6, Math.max(1, count));
    return <g className="at-glyph at-capacitor-bank" aria-hidden="true">
      {Array.from({length: visible}, (_, i) => <g key={i} transform={`translate(${(i % 2) * 28 - 14},${Math.floor(i / 2) * -21 + 17})`}>
        <path d="M-17 -10 L2 -17 L18 -9 L-1 -2 Z" className="at-glyph-top" />
        <path d="M-17 -10 L-17 7 L-1 15 L-1 -2 Z" className="at-glyph-side" />
        <path d="M-1 -2 L18 -9 L18 8 L-1 15 Z" className="at-glyph-face" />
        <path d="M3 -4 L13 -8 M3 2 L13 -2" className="at-glyph-detail" />
      </g>)}
      <text x="0" y="54" textAnchor="middle" className="at-glyph-count">{count} stages · grouped view</text>
    </g>;
  }
  if (part === 'front' || part === 'tail') return <g className="at-glyph" aria-hidden="true">
    <path d="M-45 -8 L-29 -16 L37 -16 L49 -7 L34 3 L-31 3 Z" className="at-glyph-top" />
    <path d="M-45 -8 L-45 10 L-31 21 L34 21 L49 10 L49 -7 L34 3 L-31 3 Z" className="at-glyph-face" />
    <path d="M-23 -14 L-23 3 L-23 20 M0 -14 L0 3 L0 20 M22 -14 L22 3 L22 20" className="at-glyph-band" />
    <path d="M-62 5 L-45 5 M49 5 L64 5" className="at-glyph-detail" />
  </g>;
  if (part === 'inductance') return <g className="at-glyph" aria-hidden="true">
    <path d="M-51 7 L-39 7 C-39 -25 -16 -25 -16 7 C-16 -25 7 -25 7 7 C7 -25 30 -25 30 7 C30 -25 53 -25 53 7 L64 7" className="at-coil" />
    <path d="M-43 27 L57 27" className="at-glyph-shadow" />
    <text x="5" y="48" textAnchor="middle" className="at-glyph-count">Equivalent layout effect</text>
  </g>;
  return <g className="at-glyph" aria-hidden="true">
    <path d="M-24 -27 L12 -39 L36 -26 L0 -14 Z" className="at-glyph-top" />
    <path d="M-24 -27 L-24 31 L0 45 L0 -14 Z" className="at-glyph-side" />
    <path d="M0 -14 L36 -26 L36 31 L0 45 Z" className="at-glyph-face" />
    <path d="M8 -1 L28 -8 M8 7 L28 0" className="at-glyph-detail" />
    <circle cx="20" cy="22" r="4" className={placed ? 'at-glyph-indicator placed' : 'at-glyph-indicator'} />
  </g>;
}

function Facts({part, model, availableStages}: {part: AssemblyPartId; model: AssemblyTwinModel; availableStages: number | null}) {
  const {generator: g, capacitance: c} = model;
  const rows: [string, string][] = part === 'stages' ? [
    ['Active / saved available stages', `${g.activeStages} / ${availableStages === null ? 'Not recorded' : availableStages}`],
    ['Saved charge / stage', `${fmt(g.chargeKv, 3)} kV`],
    ['Stage capacitance · profile', `${fmt(model.stageCapacitanceUf, 6)} µF`],
    ['Erected equivalent · Cₛ / n', `${fmt(model.generatorCapacitanceUf, 6)} µF`],
    ['Saved stored energy', `${fmt(g.storedEnergyKj, 3)} kJ`],
  ] : part === 'front' || part === 'tail' ? [
    ['Saved resistance / stage', ohmText(part === 'front' ? model.frontPerStageOhm : model.tailPerStageOhm)],
    ['Series-model equivalent · n × R', ohmText(part === 'front' ? model.totalFrontOhm : model.totalTailOhm)],
    ['Saved parts / stage', g[part].parts.length ? String(g[part].perStageCount) : 'Not recorded'],
    ['Saved total parts', g[part].totalComponents === null ? 'Not recorded' : String(g[part].totalComponents)],
  ] : part === 'inductance' ? [
    ['Saved connection L', `${fmt(model.inductanceUh, 3)} µH`],
    ['Physical coil specified?', 'Not recorded · L is a lumped model value'],
    ['Physical dimensions', 'Not recorded'],
  ] : [
    ['Test object', `${fmt(c.loadPf, 2)} pF`],
    ['Divider', `${fmt(c.dividerPf, 2)} pF`],
    ['Stray', `${fmt(c.strayPf, 2)} pF`],
    ['Profile basic capacitance', c.includeBase === false ? 'Excluded in saved request' : c.includeBase === null ? 'Inclusion not recorded' : `${fmt(c.basePf, 2)} pF · included`],
    ['Nominal load-side total', `${fmt(c.totalPf, 2)} pF`],
  ];
  return <dl className="at-facts">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function AssemblyWorkspace({model, run, candidate, draftEdited}: AssemblyTwinProps & {model: AssemblyTwinModel}) {
  const [placed, setPlaced] = useState<AssemblyPartId[]>([]);
  const [reviewed, setReviewed] = useState<Partial<Record<AssemblyPartId, boolean>>>({});
  const [selected, setSelected] = useState<AssemblyPartId>('stages');
  const [exploded, setExploded] = useState(true);
  const [view, setView] = useState<'workbench' | 'generator'>('workbench');
  const [dragOver, setDragOver] = useState(false);
  const [announcement, setAnnouncement] = useState('Virtual components are waiting in the tray.');
  const quiet = useQuietMotion();
  const svgId = useId().replace(/:/g, '');
  const availableStages = isNum(run.profile?.max_stages) ? run.profile.max_stages : null;
  const next = ASSEMBLY_ORDER.find(id => !placed.includes(id));
  const complete = placed.length === ASSEMBLY_ORDER.length;
  const active = model.parts.find(part => part.id === selected)!;
  const canPlace = canPlaceAssemblyPart(selected, placed, !!reviewed[selected], !!draftEdited);
  const wired = complete && model.seriesEquivalent && !!model.generator.front.tree && !!model.generator.tail.tree
    && matchingNetwork(model.frontPerStageOhm, model.generator.front.equivalentOhm)
    && matchingNetwork(model.tailPerStageOhm, model.generator.tail.equivalentOhm);

  const place = (id: AssemblyPartId) => {
    const part = model.parts.find(p => p.id === id)!;
    if (!canPlaceAssemblyPart(id, placed, !!reviewed[id], !!draftEdited)) {
      setSelected(id);
      setAnnouncement(draftEdited ? 'The request changed. Recommend new settings before continuing.' : placed.includes(id) ? `${part.title} is already in the virtual layout.` : 'Review this component’s briefing and add the earlier groups first.');
      return;
    }
    const updated = [...placed, id];
    setPlaced(updated);
    const following = ASSEMBLY_ORDER.find(p => !updated.includes(p));
    if (following) setSelected(following);
    setAnnouncement(`${part.title} added virtually. ${following ? 'The next component briefing is selected.' : 'Virtual review complete. Physical authorization is still pending.'}`);
  };
  const remove = (id: AssemblyPartId) => {
    const index = ASSEMBLY_ORDER.indexOf(id);
    setPlaced(placed.filter(p => ASSEMBLY_ORDER.indexOf(p) < index));
    setReviewed(previous => Object.fromEntries(Object.entries(previous).filter(([p]) => ASSEMBLY_ORDER.indexOf(p as AssemblyPartId) < index)));
    setSelected(id);
    setAnnouncement('This group and the later virtual groups were removed. Their briefings need review again.');
  };
  const reset = () => {
    setPlaced([]); setReviewed({}); setSelected('stages'); setExploded(true);
    setAnnouncement('Virtual plan reset. The saved recommendation is unchanged.');
  };

  return <section id="assembly-twin" className="assembly-twin" data-quiet={quiet ? 'true' : 'false'} aria-labelledby="assembly-twin-title">
    <header className="at-heading">
      <div><span className="at-eyebrow"><Box size={14} aria-hidden /> From recommendation to understanding</span><h2 id="assembly-twin-title">Assemble your digital twin</h2><p>Explore the saved R, L and C configuration. Place virtual groups, inspect their role, and review a safety briefing at each step.</p></div>
      <span className={`at-status ${model.nominalPass === false ? 'at-status-warning' : ''}`}><span aria-hidden />{model.nominalPass === false ? 'Diagnostic alternative · waveform outside limits' : 'No live hardware connection'}</span>
    </header>
    <div className="at-summary">
      <div><span>Saved candidate</span><strong>{shortId(run.id)} · rank {candidate.rank ?? '—'}</strong></div>
      <div><span>Active stages</span><strong>{model.generator.activeStages}<small> / {availableStages === null ? 'available not recorded' : availableStages}</small></strong></div>
      <div><span>Charge / stage</span><strong>{fmt(model.generator.chargeKv, 2)} <small>kV</small></strong></div>
      <div><span>Stored energy</span><strong>{fmt(model.generator.storedEnergyKj, 2)} <small>kJ · saved prediction</small></strong></div>
    </div>
    {draftEdited && <div className="at-stale" role="status"><TriangleAlert size={18} aria-hidden /><p>The request has changed. This twin still shows the saved candidate; recommend new settings to continue the virtual plan.</p></div>}
    {model.hasEffectiveParameters && <div className="at-calibration-note"><CircleHelp size={16} aria-hidden /><p>This run includes fitted effective parameters. The workshop shows the saved nominal hardware inputs; fitted corrections are separate model values, not measured replacement components.</p></div>}
    <div className="at-progress">
      <span><strong>{placed.length} / {ASSEMBLY_ORDER.length}</strong> virtual groups placed</span>
      <div className="at-progress-track" role="progressbar" aria-label="Virtual assembly progress" aria-valuemin={0} aria-valuemax={5} aria-valuenow={placed.length}><span style={{width: `${placed.length * 20}%`}} /></div>
      <span>{complete ? 'Physical review pending' : 'Teaching order only'}</span>
    </div>
    <ol className="at-phase-ribbon" aria-label="Virtual assembly phases">
      {model.parts.map((part, index) => <li key={part.id}><button type="button" className={`at-phase ${selected === part.id ? 'selected' : ''} ${placed.includes(part.id) ? 'placed' : ''}`} aria-pressed={selected === part.id} aria-current={selected === part.id ? 'step' : undefined} onClick={() => setSelected(part.id)}><span>{placed.includes(part.id) ? <Check size={13} aria-hidden /> : index + 1}</span>{part.shortTitle}<ChevronRight size={12} aria-hidden /></button></li>)}
    </ol>
    <div className="at-layout">
      <div className="at-workbench">
        <div className="at-toolbar">
          <div className="segmented" aria-label="Twin view"><button type="button" className={view === 'workbench' ? 'active' : ''} aria-pressed={view === 'workbench'} onClick={() => setView('workbench')}><Box size={14} aria-hidden />Virtual workbench</button><button type="button" className={view === 'generator' ? 'active' : ''} aria-pressed={view === 'generator'} onClick={() => setView('generator')}><Layers3 size={14} aria-hidden />Saved 3D overview</button></div>
          <button type="button" className="at-reset" onClick={reset}><RotateCcw size={14} aria-hidden />Reset virtual plan</button>
        </div>
        {view === 'generator' ? <div className="at-generator"><GeneratorView model={model.generator} height={420} view="overview" caption="Conceptual schematic · full saved configuration. Workshop progress does not change the recommendation." /></div> : <div className={`at-scene ${dragOver ? 'drag-over' : ''}`} onDragOver={e => { if (!draftEdited) {e.preventDefault(); setDragOver(true);} }} onDragLeave={() => setDragOver(false)} onDrop={e => {e.preventDefault(); setDragOver(false); const id = e.dataTransfer.getData('application/x-impulsetwin-assembly'); if (ASSEMBLY_ORDER.includes(id as AssemblyPartId)) place(id as AssemblyPartId);}}>
          <div className="at-scene-topline"><span>Conceptual schematic · virtual assembly only</span><button type="button" aria-pressed={exploded} onClick={() => setExploded(!exploded)}>{exploded ? 'Exploded view' : 'Assembled view'}<Layers3 size={13} aria-hidden /></button></div>
          <svg className="at-schematic" viewBox="0 0 900 425" role="group" aria-label="Virtual RLC component layout. Select a group to inspect it. Geometry is schematic.">
            <defs><pattern id={`${svgId}-grid`} width="35" height="35" patternUnits="userSpaceOnUse"><path d="M35 0H0V35" fill="none" stroke="currentColor" strokeWidth=".45" /></pattern><linearGradient id={`${svgId}-board`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#16383e" /><stop offset="1" stopColor="#0e232c" /></linearGradient></defs>
            <ellipse cx="457" cy="325" rx="366" ry="60" className="at-board-shadow" />
            <path d="M45 117L555 29L865 254L353 383Z" fill={`url(#${svgId}-board)`} className="at-board" />
            <path d="M45 117L45 134L353 400L865 270L865 254L353 383Z" className="at-board-edge" />
            <path d="M45 117L555 29L865 254L353 383Z" fill={`url(#${svgId}-grid)`} className="at-board-grid" />
            {wired && <g className="at-wire" aria-label="Relationship paths for the assumed lumped equivalent, not installation wiring"><path d="M135 195L205 156L355 125L565 125L760 220M205 156L355 292M135 240L240 325L355 325L760 325L760 264M355 315L355 325" /></g>}
            {model.parts.map(part => {
              const spot = SPOTS[part.id], isPlaced = placed.includes(part.id), isSelected = selected === part.id;
              const offset = exploded ? (isPlaced ? -22 : -44) : 0;
              return <g key={part.id} className="at-slot" data-placed={isPlaced ? 'true' : 'false'} data-selected={isSelected ? 'true' : 'false'} style={{'--at-part-color': spot.color} as React.CSSProperties} transform={`translate(${spot.x},${spot.y})`} role="button" tabIndex={0} aria-label={`${part.title}, ${partValue(part.id, model)}, ${isPlaced ? 'virtually placed' : 'not yet placed'}. Inspect component.`} aria-pressed={isSelected} onClick={() => setSelected(part.id)} onKeyDown={e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); setSelected(part.id);}}}>
                <path d="M-70 22L6 -1L78 35L1 60Z" className="at-slot-platform" />
                {exploded && <path d={`M0 28L0 ${offset + 7}`} className="at-guide" />}
                <g className="at-raised-part" transform={`translate(0,${offset})`}><PartGlyph part={part.id} count={model.generator.activeStages} placed={isPlaced} /></g>
                <g transform="translate(0,76)"><text textAnchor="middle" className="at-scene-label">{part.symbol} · {part.shortTitle}</text><text y="20" textAnchor="middle" className="at-scene-value">{partValue(part.id, model)}</text></g>
                {isPlaced && <g transform="translate(63,4)" className="at-placement-mark"><circle r="10" /><path d="M-4 0L-1 3L5 -4" /></g>}
              </g>;
            })}
          </svg>
          <p className="at-scene-caption">{wired ? 'Relationship paths follow the assumed series-Marx lumped model. They are not a physical connection or mounting plan.' : 'Groups are shown separately. Electrical relationship paths appear only with a completed virtual layout and verified saved resistor trees.'}</p>
        </div>}
        <div className="at-tray-heading"><span><GripVertical size={14} aria-hidden />Component tray</span><small>Drag to the workbench or use Add virtually</small></div>
        <div className="at-palette">
          {model.parts.map(part => <article className={`at-part ${placed.includes(part.id) ? 'placed' : ''} ${selected === part.id ? 'selected' : ''}`} key={part.id} data-selected={selected === part.id ? 'true' : 'false'} data-placed={placed.includes(part.id) ? 'true' : 'false'} style={{'--at-part-color': SPOTS[part.id].color} as React.CSSProperties} draggable={!draftEdited && !placed.includes(part.id)} onDragStart={e => {e.dataTransfer.setData('application/x-impulsetwin-assembly', part.id); e.dataTransfer.effectAllowed = 'copy'; setSelected(part.id);}}>
            <button type="button" className="at-part-inspect" onClick={() => setSelected(part.id)} aria-pressed={selected === part.id}><span className="at-part-icon" aria-hidden>{part.symbol}</span><strong>{part.shortTitle}</strong><span className="at-part-value">{partValue(part.id, model)}</span></button>
            <div className="at-part-actions">{placed.includes(part.id) ? <button type="button" onClick={() => remove(part.id)} disabled={!!draftEdited} aria-label={`Remove ${part.title} and later virtual groups`}><Minus size={12} aria-hidden />Remove</button> : <button type="button" onClick={() => place(part.id)} disabled={!canPlaceAssemblyPart(part.id, placed, !!reviewed[part.id], !!draftEdited)} aria-label={`Add ${part.title} virtually`}><Plus size={12} aria-hidden />Add virtually</button>}</div>
          </article>)}
        </div>
        <p className="at-order-note">This order teaches the model. It is not a physical assembly, wiring, discharge or energization procedure.</p>
      </div>
      <aside className="at-inspector" aria-labelledby="at-inspector-title">
        <div className="at-inspector-heading"><span className="at-part-icon" style={{'--at-part-color': SPOTS[selected].color} as React.CSSProperties} aria-hidden>{active.symbol}</span><div><span>Component {ASSEMBLY_ORDER.indexOf(selected) + 1} / 5</span><h3 id="at-inspector-title">{active.title}</h3></div></div>
        <p className="at-explanation">{active.explanation}</p><p className="at-analogy"><CircleHelp size={15} aria-hidden />{active.analogy}</p>
        <Facts part={selected} model={model} availableStages={availableStages} />
        {(selected === 'front' || selected === 'tail') && <div className="at-network-detail"><span>{model.generator[selected].tree ? 'Verified saved per-stage topology' : 'Wiring unavailable · saved parts only'}</span><NetworkSchematic net={model.generator[selected]} /><p>{model.generator[selected].topology}</p></div>}
        <div className="at-briefing"><div><ShieldAlert size={19} aria-hidden /><h4>Before any real-world work</h4></div><p>{active.precaution}</p><label className="at-checkpoint"><input type="checkbox" checked={!!reviewed[selected]} disabled={!!draftEdited || placed.includes(selected)} onChange={e => setReviewed({...reviewed, [selected]: e.target.checked})} /><span><strong>Briefing reviewed</strong>{active.checkpoint}</span></label><small>A tick records reading in this browser. It does not verify the equipment or authorize work.</small></div>
        {placed.includes(selected) ? <p className="at-added"><Check size={15} aria-hidden />This group is in the virtual layout.</p> : <button type="button" className="button primary at-add" disabled={!canPlace} onClick={() => place(selected)}><Plus size={15} aria-hidden />Add {active.shortTitle.toLowerCase()} virtually<ArrowRight size={15} aria-hidden /></button>}
        {!canPlace && !placed.includes(selected) && !draftEdited && <p className="at-step-hint">{next !== selected ? `Place ${model.parts.find(part => part.id === next)?.shortTitle.toLowerCase()} first in this teaching sequence.` : 'Read this briefing and mark it reviewed to add the virtual group.'}</p>}
      </aside>
    </div>
    <div className={`at-completion ${complete ? 'complete' : ''}`}><ShieldAlert size={21} aria-hidden /><div><h3>{complete ? 'Virtual review complete · physical authorization pending' : 'Personal safety is an independent laboratory review'}</h3><p>Any proposed real work needs an approved hazard and task plan, qualified authorized personnel and the laboratory’s site procedures. This proposed workflow is not for lone work: the laboratory must arrange appropriate supervision and a trained, briefed second person for emergencies. Staff independently verify isolation, stored-energy controls, barriers, interlocks, grounding, equipment ratings and the emergency plan, and select personal protection for the actual hazard. Interlocks do not replace isolation.</p></div></div>
    <div className="at-unknowns"><strong>Still unknown to this twin</strong><ul><li>Physical installation and mounting · <strong>Not verified</strong></li><li>Insulation and protective clearances · <strong>Not verified</strong></li><li>Pulse ratings and component condition · <strong>Not verified</strong></li><li>Actual isolation, grounding and interlock state · <strong>Not verified</strong></li><li>Required personal protection and site authorization · <strong>Not verified</strong></li></ul><p><strong>Saved stock provenance:</strong> {model.stockProvenance || 'Not recorded · do not assume laboratory stock.'}</p></div>
    <footer className="at-footer"><span>Briefing references; the laboratory’s approved procedure governs.</span><a href="https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333" target="_blank" rel="noreferrer">Electrical work practices</a><a href="https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.335" target="_blank" rel="noreferrer">Personnel safeguards</a><a href="https://electricalsafety.lbl.gov/electrical-safety/emergency-response/" target="_blank" rel="noreferrer">Emergency preparedness</a></footer>
    <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
  </section>;
}

export default function AssemblyTwin(props: AssemblyTwinProps) {
  const model = useMemo(() => assemblyModelFromCandidate(props.run, props.candidate), [props.run, props.candidate]);
  if (!model) return null;
  // A changed saved configuration immediately destroys the prior virtual plan.
  return <AssemblyWorkspace key={model.key} {...props} model={model} />;
}
