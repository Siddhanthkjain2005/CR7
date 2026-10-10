// Pure helpers for the Waveform Diagnostics page (unit-tested in tests/run-unit-tests.mjs).
export type Data = Record<string, any>;

export const DIAGNOSTIC_STEPS = [
  {id: 'reference', name: 'Reference'},
  {id: 'upload', name: 'Upload'},
  {id: 'calibrate', name: 'Calibrate & review'},
  {id: 'compare', name: 'Compare'},
  {id: 'investigate', name: 'Investigate'},
  {id: 'findings', name: 'Findings & export'},
] as const;
export type StepId = (typeof DIAGNOSTIC_STEPS)[number]['id'];

/** Per-step state from the saved session view: done, current, stale or waiting. */
export function stepStates(view: Data | null | undefined): Record<StepId, 'done' | 'current' | 'stale' | 'waiting'> {
  const out = {} as Record<StepId, 'done' | 'current' | 'stale' | 'waiting'>;
  const next = (view?.next_step || 'reference') as StepId;
  const order = DIAGNOSTIC_STEPS.map(s => s.id);
  const stale = view?.stale || {};
  order.forEach(id => {
    if (id === 'compare' && stale.comparison) out[id] = 'stale';
    else if (id === 'investigate' && stale.investigation) out[id] = 'stale';
    else if (id === next) out[id] = 'current';
    else out[id] = order.indexOf(id) < order.indexOf(next) ? 'done' : 'waiting';
  });
  if (next === 'findings') out.findings = 'done';
  return out;
}

export const ORIGINS: [string, string, string][] = [
  ['physical_experiment', 'Physical experiment', 'Declared as a recording of a real shot. A file or photo does not prove this.'],
  ['software_simulation', 'Software simulation', 'Output of a circuit simulator or another model.'],
  ['demonstration', 'Demonstration', 'Made for rehearsal or teaching.'],
  ['unknown', 'Unknown', 'Origin not known.'],
];

/** Tone for a hypothesis or metric status. */
export function statusTone(status: string | null | undefined): 'green' | 'cyan' | 'amber' | 'red' | 'neutral' | 'unknown' {
  switch (status) {
    case 'Possible cause':
      return 'cyan';
    case 'Several explanations fit':
    case 'Requires review':
    case 'Approximate':
      return 'amber';
    case 'Consistent with this waveform':
    case 'Compared':
    case 'No change needed':
      return 'green';
    case 'Cannot explain with the current model':
    case 'Does not match':
      return 'red';
    case 'Insufficient capture':
    case 'Not tested':
    case 'Not needed':
      return 'unknown';
    default:
      return 'neutral';
  }
}

export const CATEGORY_ORDER = ['hardware', 'configuration', 'measurement', 'model'] as const;
export const CATEGORY_NAMES: Record<string, string> = {
  hardware: 'Hardware hypotheses',
  configuration: 'Configuration differences',
  measurement: 'Measurement issues',
  model: 'Model limitations',
};

/** Hypotheses grouped by category (baseline first), keeping the backend's ranking inside each group. */
export function groupHypotheses(investigation: Data | null | undefined): {category: string; name: string; items: Data[]}[] {
  if (!investigation?.hypotheses) return [];
  const rank = new Map<string, number>((investigation.ranking || []).map((id: string, i: number) => [id, i]));
  const sorted = [...investigation.hypotheses].sort((a: Data, b: Data) => (rank.get(a.id) ?? 99) - (rank.get(b.id) ?? 99));
  return CATEGORY_ORDER.map(c => ({category: c, name: CATEGORY_NAMES[c], items: sorted.filter((h: Data) => h.category === c)})).filter(g => g.items.length);
}

const PARAM: Record<string, [string, string, number]> = {
  front_factor: ['Front network', '×', 3],
  tail_factor: ['Tail network', '×', 3],
  extra_load_pf: ['Load-side capacitance', 'pF', 0],
  inductance_uh: ['Inductance', 'µH', 1],
  charge_factor: ['Charge', '×', 3],
  efficiency_factor: ['Loss factor', '×', 3],
  gain: ['Measurement gain', '×', 3],
  time_shift_us: ['Time offset', 'µs', 3],
  baseline_kv: ['Baseline offset', 'kV', 1],
  stages: ['Stages', '', 0],
};

/** Plain text for one fitted quantity, e.g. "Front network 0.822×" or "Load-side capacitance +350 pF". */
export function paramText(name: string, value: unknown): string {
  const [label, unit, digits] = PARAM[name] || [name, '', 3];
  if (typeof value !== 'number' || !Number.isFinite(value)) return `${label} —`;
  if (unit === '×') return `${label} ${value.toFixed(digits)}×`;
  const signed = name === 'extra_load_pf' || name === 'time_shift_us' || name === 'baseline_kv';
  const text = value.toFixed(digits);
  return `${label} ${signed && value > 0 ? '+' : ''}${text}${unit ? ` ${unit}` : ''}`;
}

/** Anchors implied by an oscilloscope graticule (same arithmetic as the backend). */
export function perDivisionAnchors(g: Data): {x: [number, number][]; y: [number, number][]} | null {
  const need = ['left_px', 'right_px', 'top_px', 'bottom_px', 'time_per_div', 'volts_per_div'];
  if (need.some(k => typeof g?.[k] !== 'number' || !Number.isFinite(g[k]))) return null;
  const nx = g.divisions_x ?? 10, ny = g.divisions_y ?? 8, t0 = g.time_at_left ?? 0, v0 = g.value_at_center ?? 0;
  return {
    x: [[g.left_px, t0], [g.right_px, t0 + nx * g.time_per_div]],
    y: [[(g.top_px + g.bottom_px) / 2, v0], [g.top_px, v0 + (ny / 2) * g.volts_per_div]],
  };
}

/** Problems with a draft axis calibration, in plain words (empty when it can be submitted). */
export function calibrationGaps(axes: Data): string[] {
  const gaps: string[] = [];
  if (axes.x_scale === 'log' || axes.y_scale === 'log') gaps.push('Logarithmic axes are not supported; only linear axes can be digitized');
  if (axes.voltage_side === 'high_voltage' && Number(axes.divider_ratio) !== 1) gaps.push('the axis already shows high voltage, so the divider ratio must be 1');
  if (axes.voltage_side === 'instrument' && Number(axes.divider_ratio) !== 1 && !String(axes.divider_ratio_source || '').trim()) gaps.push('source of the divider ratio');
  if (axes.mode === 'per_division') {
    if (!perDivisionAnchors(axes.grid || {})) gaps.push('graticule edges, time/div and volts/div');
  } else {
    const pairs = [axes.x_anchors, axes.y_anchors];
    const names = ['two time anchors', 'two voltage anchors'];
    pairs.forEach((p: Data[] | undefined, i) => {
      const ok = Array.isArray(p) && p.length === 2 && p.every(a => Number.isFinite(a?.px) && Number.isFinite(a?.value));
      if (!ok) gaps.push(names[i]);
      else if (Math.abs(p[1].px - p[0].px) < 20) gaps.push(`${names[i]} at least 20 px apart`);
      else if (p[1].value === p[0].value) gaps.push(`${names[i]} with different values`);
    });
  }
  return gaps;
}

/** Point from a pointer event to working-image pixels via the SVG's own transform. */
export function toImagePoint(svg: {getScreenCTM(): DOMMatrix | null; createSVGPoint(): DOMPoint}, clientX: number, clientY: number): [number, number] | null {
  const m = svg.getScreenCTM();
  if (!m) return null;
  const p = svg.createSVGPoint();
  p.x = clientX;
  p.y = clientY;
  const q = p.matrixTransform(m.inverse());
  return [q.x, q.y];
}

/** Label of the uploaded waveform: never lets a photo look like a laboratory record. */
export function uploadedLabel(view: Data | null | undefined): string {
  const up = view?.upload;
  if (!up) return 'Uploaded waveform';
  if (up.source === 'image') return 'Digitized from image — approximate';
  return up.label || 'Uploaded samples';
}

/** Short summary of a quality record's flags for headings. */
export function flagSummary(quality: Data | null | undefined): string {
  const flags: Data[] = quality?.flags || [];
  if (!flags.length) return 'No quality flags';
  return `${flags.length} quality flag${flags.length === 1 ? '' : 's'}`;
}
