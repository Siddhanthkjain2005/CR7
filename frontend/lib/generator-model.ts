import {Data, isNum, shortId} from './api';

/**
 * Conceptual generator model for the 3D scene and its 2D fallback.
 *
 * Everything here is derived from a SAVED backend record (run + candidate, or a
 * saved setup-transition option). Nothing is solved, estimated or invented:
 * unknown values stay null. Geometry produced from this model is schematic.
 */

export type ResistorTree =
  | {kind: 'R'; ohm: number}
  | {kind: 'series' | 'parallel'; children: ResistorTree[]};

export interface NetworkPart {
  ohm: number;
  perStage: number;
  total: number | null;
  available: number | null;
}

export interface NetworkModel {
  role: 'front' | 'tail';
  topology: string;
  equivalentOhm: number | null;
  parts: NetworkPart[];
  /** Series/parallel tree parsed from the backend topology text, kept only when it reproduces the saved equivalent and counts. */
  tree: ResistorTree | null;
  perStageCount: number;
  totalComponents: number | null;
}

export type StageState = 'active' | 'inactive' | 'shared' | 'added' | 'removed';

export interface PartDelta {
  ohm: number;
  before: number;
  after: number;
  retained: number;
  added: number;
  removed: number;
}

export interface TransitionModel {
  baselineStages: number;
  targetStages: number;
  added: number;
  deactivated: number;
  front: PartDelta[];
  tail: PartDelta[];
  baselineTopology: {front: string; tail: string};
  targetTopology: {front: string; tail: string};
  frontChanged: boolean;
  tailChanged: boolean;
}

export interface GeneratorModel {
  key: string;
  mode: 'candidate' | 'transition';
  title: string;
  profileName: string;
  impulse: string;
  maxStages: number;
  activeStages: number;
  chargeKv: number | null;
  stageRatingKv: number | null;
  utilization: number | null;
  storedEnergyKj: number | null;
  front: NetworkModel;
  tail: NetworkModel;
  stages: StageState[];
  transition?: TransitionModel;
}

/* ------------------------------------------------------------------ */
/* Topology parsing                                                    */
/* ------------------------------------------------------------------ */

type Token = {t: '(' | ')' | '+' | '∥'} | {t: 'num'; v: number} | {t: 'x'} | {t: 'ohm'} | {t: 'par'};

function tokenize(text: string): Token[] | null {
  const tokens: Token[] = [];
  let i = 0;
  const s = text.replace(/Ω/g, 'Ω');
  while (i < s.length) {
    const ch = s[i];
    if (ch === ' ') { i++; continue; }
    if (ch === '(' || ch === ')' || ch === '+' || ch === '∥') { tokens.push({t: ch} as Token); i++; continue; }
    if (ch === '×') { tokens.push({t: 'x'}); i++; continue; }
    if (ch === 'Ω') { tokens.push({t: 'ohm'}); i++; continue; }
    if (s.startsWith('in parallel', i)) { tokens.push({t: 'par'}); i += 11; continue; }
    const m = /^[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?/i.exec(s.slice(i));
    if (m) { tokens.push({t: 'num', v: Number(m[0])}); i += m[0].length; continue; }
    return null;
  }
  return tokens;
}

function parseTree(text: string): ResistorTree | null {
  const tokens = tokenize(text);
  if (!tokens) return null;
  let p = 0;
  const peek = () => tokens[p];
  function term(): ResistorTree | null {
    const tok = peek();
    if (!tok) return null;
    if (tok.t === '(') {
      p++;
      const inner = expr();
      if (!inner || peek()?.t !== ')') return null;
      p++;
      return inner;
    }
    if (tok.t !== 'num') return null;
    p++;
    if (peek()?.t === 'x') {
      p++;
      const value = peek();
      if (!value || value.t !== 'num') return null;
      p++;
      if (peek()?.t !== 'ohm') return null;
      p++;
      const count = tok.v;
      if (!Number.isInteger(count) || count < 1 || count > 60) return null;
      const leaves: ResistorTree[] = Array.from({length: count}, () => ({kind: 'R', ohm: value.v}));
      if (peek()?.t === 'par') {
        p++;
        return count === 1 ? leaves[0] : {kind: 'parallel', children: leaves};
      }
      return count === 1 ? leaves[0] : {kind: 'series', children: leaves};
    }
    if (peek()?.t !== 'ohm') return null;
    p++;
    return {kind: 'R', ohm: tok.v};
  }
  function expr(): ResistorTree | null {
    const first = term();
    if (!first) return null;
    const items = [first];
    let op: '+' | '∥' | null = null;
    while (peek() && (peek().t === '+' || peek().t === '∥')) {
      const next = peek().t as '+' | '∥';
      if (op && op !== next) return null; // mixed operators without parentheses: refuse to guess
      op = next;
      p++;
      const t = term();
      if (!t) return null;
      items.push(t);
    }
    if (items.length === 1) return first;
    const kind = op === '+' ? 'series' : 'parallel';
    // Flatten same-kind children so "a + b + c" and "(a + b) + c" render alike.
    const children = items.flatMap(c => (c.kind === kind ? (c as {children: ResistorTree[]}).children : [c]));
    return {kind, children};
  }
  const tree = expr();
  return tree && p === tokens.length ? tree : null;
}

export function equivalentOhm(tree: ResistorTree): number {
  if (tree.kind === 'R') return tree.ohm;
  const values = tree.children.map(equivalentOhm);
  return tree.kind === 'series' ? values.reduce((a, b) => a + b, 0) : 1 / values.reduce((a, b) => a + 1 / b, 0);
}

export function leafCounts(tree: ResistorTree, into = new Map<number, number>()): Map<number, number> {
  if (tree.kind === 'R') into.set(tree.ohm, (into.get(tree.ohm) || 0) + 1);
  else tree.children.forEach(c => leafCounts(c, into));
  return into;
}

/** Parses a backend topology string and keeps it only if it reproduces the saved equivalent and counts. */
export function verifiedTree(topology: string, equivalent: number | null, parts: NetworkPart[]): ResistorTree | null {
  const tree = typeof topology === 'string' ? parseTree(topology) : null;
  if (!tree) return null;
  if (isNum(equivalent)) {
    const eq = equivalentOhm(tree);
    if (Math.abs(eq - equivalent) > Math.max(1e-6, Math.abs(equivalent) * 1e-6)) return null;
  }
  const counts = leafCounts(tree);
  if (parts.length) {
    if (counts.size !== parts.filter(p => p.perStage > 0).length) return null;
    for (const part of parts) {
      if (part.perStage > 0 && counts.get(part.ohm) !== part.perStage) return null;
    }
  }
  return tree;
}

/* ------------------------------------------------------------------ */
/* Builders                                                            */
/* ------------------------------------------------------------------ */

function network(role: 'front' | 'tail', raw: Data | undefined): NetworkModel {
  const parts: NetworkPart[] = Array.isArray(raw?.components)
    ? raw!.components
        .filter((c: Data) => isNum(c?.ohm))
        .map((c: Data) => ({
          ohm: c.ohm,
          perStage: isNum(c.count_per_stage) ? c.count_per_stage : 0,
          total: isNum(c.total_required) ? c.total_required : null,
          available: isNum(c.available_per_stage) ? c.available_per_stage : null,
        }))
    : [];
  const equivalent = isNum(raw?.equivalent_ohm) ? raw!.equivalent_ohm : null;
  const topology = typeof raw?.topology === 'string' ? raw!.topology : 'Not recorded';
  return {
    role,
    topology,
    equivalentOhm: equivalent,
    parts,
    tree: verifiedTree(topology, equivalent, parts),
    perStageCount: parts.reduce((a, p) => a + p.perStage, 0),
    totalComponents: isNum(raw?.total_components) ? raw!.total_components : null,
  };
}

/** Builds the scene model for a saved run's candidate. */
export function modelFromCandidate(run: Data | null | undefined, candidate: Data | null | undefined, profile?: Data | null): GeneratorModel | null {
  if (!run || !candidate?.settings) return null;
  const prof = profile || run.profile || {};
  const settings = candidate.settings;
  const active = isNum(settings.stages) ? Math.max(0, Math.round(settings.stages)) : 0;
  const max = Math.max(active, isNum(prof.max_stages) ? prof.max_stages : active);
  return {
    key: `${run.id}:${candidate.id}`,
    mode: 'candidate',
    title: `Run ${shortId(run.id)} · rank ${candidate.rank ?? '—'}`,
    profileName: prof.name || 'Profile not recorded',
    impulse: run.inputs?.impulse_type || '',
    maxStages: max,
    activeStages: active,
    chargeKv: isNum(settings.charge_kv_stage) ? settings.charge_kv_stage : null,
    stageRatingKv: isNum(prof.stage_kv) ? prof.stage_kv : null,
    utilization: isNum(settings.stage_utilization) ? settings.stage_utilization : null,
    storedEnergyKj: isNum(settings.stored_energy_kj) ? settings.stored_energy_kj : null,
    front: network('front', candidate.front_network),
    tail: network('tail', candidate.tail_network),
    stages: Array.from({length: max}, (_, i) => (i < active ? 'active' : 'inactive')),
  };
}

function deltas(parts: Data[] | undefined): PartDelta[] {
  return (parts || [])
    .filter(p => isNum(p?.ohm))
    .map(p => {
      const before = isNum(p.baseline_per_stage) ? p.baseline_per_stage : 0;
      const after = isNum(p.target_per_stage) ? p.target_per_stage : 0;
      return {ohm: p.ohm, before, after, retained: Math.min(before, after), added: Math.max(0, after - before), removed: Math.max(0, before - after)};
    });
}

/**
 * Builds a before/after model from a saved setup-transition option. Shared,
 * newly active and deactivated stages follow the saved stage counts; part
 * changes follow the saved per-stage counts. This is a planning picture of
 * saved plans, not authenticated installed hardware.
 */
export function modelFromTransition(review: Data, option: Data, targetRun: Data | null | undefined): GeneratorModel | null {
  const baseline = review?.baseline?.settings;
  const target = option?.settings;
  if (!baseline || !target || !isNum(baseline.stages) || !isNum(target.stages)) return null;
  const candidate = targetRun?.candidates?.find((c: Data) => c.id === option.candidate_id);
  const prof = targetRun?.profile || {};
  const b = Math.round(baseline.stages), t = Math.round(target.stages);
  const max = Math.max(b, t, isNum(prof.max_stages) ? prof.max_stages : 0);
  const stages: StageState[] = Array.from({length: max}, (_, i) => {
    const inB = i < b, inT = i < t;
    return inB && inT ? 'shared' : inT ? 'added' : inB ? 'removed' : 'inactive';
  });
  const nets = option.networks || {};
  const front = network('front', candidate?.front_network || {topology: nets.front?.target_topology, equivalent_ohm: nets.front?.target_equivalent_ohm, components: []});
  const tail = network('tail', candidate?.tail_network || {topology: nets.tail?.target_topology, equivalent_ohm: nets.tail?.target_equivalent_ohm, components: []});
  return {
    key: `transition:${review.id}:${option.candidate_id}`,
    mode: 'transition',
    title: `Saved ${shortId(review.baseline.run_id)} rank → rank ${option.original_rank}`,
    profileName: review.baseline.profile_name || prof.name || 'Profile not recorded',
    impulse: review.target?.impulse_type || '',
    maxStages: max,
    activeStages: t,
    chargeKv: isNum(target.charge_kv_stage) ? target.charge_kv_stage : null,
    stageRatingKv: isNum(prof.stage_kv) ? prof.stage_kv : null,
    utilization: isNum(target.stage_utilization) ? target.stage_utilization : null,
    storedEnergyKj: isNum(target.stored_energy_kj) ? target.stored_energy_kj : null,
    front,
    tail,
    stages,
    transition: {
      baselineStages: b,
      targetStages: t,
      added: isNum(option.active_stages_added) ? option.active_stages_added : Math.max(0, t - b),
      deactivated: isNum(option.active_stages_deactivated) ? option.active_stages_deactivated : Math.max(0, b - t),
      front: deltas(nets.front?.parts),
      tail: deltas(nets.tail?.parts),
      baselineTopology: {front: nets.front?.baseline_topology || 'Not recorded', tail: nets.tail?.baseline_topology || 'Not recorded'},
      targetTopology: {front: nets.front?.target_topology || front.topology, tail: nets.tail?.target_topology || tail.topology},
      frontChanged: !!nets.front?.connection_plan_changed,
      tailChanged: !!nets.tail?.connection_plan_changed,
    },
  };
}

/* ------------------------------------------------------------------ */
/* Shared visual vocabulary                                            */
/* ------------------------------------------------------------------ */

/** Stable colour per resistor value within one network (index in sorted value list). */
// Front values use warm/blue hues, tail values a separate set, so the two banks never share a colour.
export const VALUE_COLORS = {front: ['#d08a4c', '#7f9bd8', '#d9c27a', '#9fc0e8'], tail: ['#e3a3b5', '#b7d36a', '#c792c9', '#f0b98a']};
/** Colour for parts kept unchanged in a before/after (transition) view. */
export const KEPT_COLOR = '#9fb0bc';

export function valueColor(ohm: number, net: NetworkModel): string {
  const values = [...new Set(net.parts.map(p => p.ohm))].sort((a, b) => a - b);
  const i = values.indexOf(ohm);
  const set = VALUE_COLORS[net.role];
  return set[(i < 0 ? 0 : i) % set.length];
}

export function ohmText(v: number | null | undefined): string {
  if (!isNum(v)) return '—';
  if (v >= 1e6) return `${(v / 1e6).toLocaleString('en-US', {maximumFractionDigits: 3})} MΩ`;
  if (v >= 1e4) return `${(v / 1e3).toLocaleString('en-US', {maximumFractionDigits: 3})} kΩ`;
  return `${v.toLocaleString('en-US', {maximumFractionDigits: 3})} Ω`;
}

/** Layout of a resistor tree in a unit box: series stacks along "along", parallel spreads across. */
export interface LeafBox {ohm: number; a0: number; a1: number; c: number}

export function layoutTree(tree: ResistorTree): {leaves: LeafBox[]; width: number} {
  // width = number of parallel lanes needed; length is normalized to 1.
  function width(t: ResistorTree): number {
    if (t.kind === 'R') return 1;
    const w = t.children.map(width);
    return t.kind === 'series' ? Math.max(...w) : w.reduce((a, b) => a + b, 0);
  }
  const leaves: LeafBox[] = [];
  function place(t: ResistorTree, a0: number, a1: number, c0: number, lanes: number) {
    if (t.kind === 'R') {
      leaves.push({ohm: t.ohm, a0, a1, c: c0 + lanes / 2});
      return;
    }
    if (t.kind === 'series') {
      const n = t.children.length;
      t.children.forEach((child, i) => {
        const w = width(child);
        place(child, a0 + ((a1 - a0) * i) / n, a0 + ((a1 - a0) * (i + 1)) / n, c0 + (lanes - w) / 2, w);
      });
      return;
    }
    let c = c0;
    t.children.forEach(child => {
      const w = width(child);
      place(child, a0, a1, c, w);
      c += w;
    });
  }
  const total = width(tree);
  place(tree, 0, 1, 0, total);
  return {leaves, width: total};
}
