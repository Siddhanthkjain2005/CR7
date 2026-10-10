'use client';
import {GeneratorModel, NetworkModel, KEPT_COLOR, layoutTree, valueColor, PartDelta, StageState} from '@/lib/generator-model';

/**
 * 2D elevation of the conceptual stack. Same information as the 3D scene:
 * active/inactive (or shared/new/deactivated) stages and the counted
 * front/tail banks per stage. Used when WebGL is unavailable or by choice.
 */
const STAGE_H = 30;
const W = 520;

type Rod = {ohm: number; a0: number; a1: number; c: number; kind: 'keep' | 'added' | 'removed'};

function bankRods(net: NetworkModel, model: GeneratorModel, state: StageState, deltas?: PartDelta[]): {rods: Rod[]; lanes: number} {
  if (model.mode === 'transition' && deltas) {
    if (state === 'inactive') return {rods: [], lanes: 1};
    const list: Rod[] = [];
    deltas.forEach(d => {
      const keep = state === 'shared' ? d.retained : 0;
      const added = state === 'shared' ? d.added : state === 'added' ? d.after : 0;
      const removed = state === 'shared' ? d.removed : state === 'removed' ? d.before : 0;
      for (let k = 0; k < keep; k++) list.push({ohm: d.ohm, a0: 0, a1: 1, c: 0, kind: 'keep'});
      for (let k = 0; k < added; k++) list.push({ohm: d.ohm, a0: 0, a1: 1, c: 0, kind: 'added'});
      for (let k = 0; k < removed; k++) list.push({ohm: d.ohm, a0: 0, a1: 1, c: 0, kind: 'removed'});
    });
    list.forEach((r, i) => (r.c = i + 0.5));
    return {rods: list, lanes: Math.max(1, list.length)};
  }
  if (net.tree) {
    const l = layoutTree(net.tree);
    return {rods: l.leaves.map(x => ({...x, kind: 'keep' as const})), lanes: l.width};
  }
  const list = net.parts.flatMap(p => Array.from({length: p.perStage}, () => p.ohm));
  return {rods: list.map((ohm, i) => ({ohm, a0: 0, a1: 1, c: i + 0.5, kind: 'keep' as const})), lanes: Math.max(1, list.length)};
}

export default function GeneratorElevation({model, selected, onSelect, pulse}: {model: GeneratorModel; selected: number | null; onSelect: (i: number | null) => void; pulse?: number | null}) {
  const n = model.maxStages;
  const top = 40;
  const height = top + n * STAGE_H + 64;
  const deckX = 150, deckW = 190;
  const y = (i: number) => top + (n - 1 - i) * STAGE_H; // stage 1 at the bottom
  const activeTop = y(Math.max(0, model.activeStages - 1));
  const glow = pulse ?? 0;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="elevation" role="img" aria-label={`Conceptual elevation: ${model.activeStages} of ${model.maxStages} stages active. Front ${model.front.topology}, tail ${model.tail.topology} per stage.`}>
      <defs>
        <pattern id="elev-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#2a3a47" strokeWidth="2" />
        </pattern>
      </defs>
      <text x={deckX - 96} y={top - 18} className="elev-head">Front bank / stage</text>
      <text x={deckX + deckW + 10} y={top - 18} className="elev-head">Tail bank / stage</text>
      {model.stages.map((state, i) => {
        const yy = y(i);
        const lit = state === 'active' || state === 'shared' || state === 'added';
        const stroke = state === 'added' ? '#3fd29a' : state === 'removed' ? '#ff6f5c' : lit ? '#7f97a8' : '#33444f';
        const front = bankRods(model.front, model, state, model.transition?.front);
        const tail = bankRods(model.tail, model, state, model.transition?.tail);
        const bank = (rods: Rod[], lanes: number, x0: number, net: NetworkModel) => {
          const w = Math.min(84, lanes * 11 + 6);
          return rods.map((r, k) => {
            const cx = x0 + 3 + (r.c / lanes) * (w - 6);
            const y0 = yy + 4 + r.a0 * (STAGE_H - 8), y1 = yy + 4 + r.a1 * (STAGE_H - 8);
            const color = r.kind === 'added' ? '#3fd29a' : r.kind === 'removed' ? '#ff6f5c' : model.mode === 'transition' ? KEPT_COLOR : valueColor(r.ohm, net);
            return <line key={k} x1={cx} x2={cx} y1={y0 + 1.5} y2={y1 - 1.5} stroke={color} strokeWidth={4} strokeLinecap="round" opacity={lit || r.kind === 'removed' ? (r.kind === 'removed' ? 0.65 : 1) : 0.25} strokeDasharray={r.kind === 'removed' ? '2 3' : undefined} />;
          });
        };
        return (
          <g
            key={i}
            className={`elev-stage ${selected === i ? 'selected' : ''}`}
            onClick={() => onSelect(selected === i ? null : i)}
          >
            <rect x={deckX} y={yy} width={deckW} height={STAGE_H - 2} rx={3} fill={lit ? '#18242e' : 'url(#elev-hatch)'} stroke={selected === i ? '#ffffff' : stroke} strokeWidth={selected === i ? 2 : 1} strokeDasharray={lit ? undefined : '3 3'} />
            <rect x={deckX + 52} y={yy + 8} width={70} height={STAGE_H - 18} rx={2} fill={lit ? '#0f2a30' : 'none'} stroke={lit ? '#2cc6da' : '#3c4c58'} strokeWidth={1} />
            <circle cx={deckX + deckW - 22} cy={yy + 9} r={3.2} fill="#cfd8de" opacity={lit ? 0.9 : 0.25} />
            <circle cx={deckX + deckW - 22} cy={yy + 19} r={3.2} fill="#cfd8de" opacity={lit ? 0.9 : 0.25} />
            <text x={deckX - 104} y={yy + STAGE_H / 2 + 3} className="elev-stage-label" textAnchor="start">
              S{i + 1}
            </text>
            {bank(front.rods, front.lanes, deckX - 82, model.front)}
            {bank(tail.rods, tail.lanes, deckX + deckW + 8, model.tail)}
            {(state === 'added' || state === 'removed') && (
              <text x={deckX + deckW / 2 + 52} y={yy + STAGE_H / 2 + 3} className={`elev-delta ${state}`} textAnchor="middle">
                {state === 'added' ? '+ newly active' : '− deactivated'}
              </text>
            )}
          </g>
        );
      })}
      <rect x={deckX - 16} y={top + n * STAGE_H} width={deckW + 32} height={14} rx={2} fill="#2b3740" />
      <path d={`M ${deckX + deckW} ${activeTop + 2} C ${deckX + deckW + 70} ${activeTop - 10}, ${W - 70} ${top - 6}, ${W - 46} ${top + 10}`} fill="none" stroke="#2cc6da" strokeWidth={2 + glow * 2} opacity={0.5 + glow * 0.5} />
      <rect x={W - 54} y={top + 10} width={16} height={n * STAGE_H - 10} rx={4} fill="#7a3f2e" opacity={0.85} />
      <text x={W - 46} y={top + n * STAGE_H + 30} className="elev-head" textAnchor="middle">
        Divider · object
      </text>
      <text x={deckX + deckW / 2} y={top + n * STAGE_H + 34} className="elev-foot" textAnchor="middle">
        {model.activeStages} of {model.maxStages} stages active · conceptual elevation, not to scale
      </text>
    </svg>
  );
}
