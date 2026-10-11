// Frontend behaviour checks for the pure modules behind the redesigned controls.
// Uses only the project's existing TypeScript dependency: lib/*.ts files are
// transpiled to a temporary directory and exercised with node:test.
// Run: cd frontend && npm run test:unit
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'impulsetwin-unit-'));
for (const name of ['api', 'generator-model', 'inventory', 'series', 'diagnostics', 'assembly-twin', 'fault-tests', 'capture-time']) {
  const source = fs.readFileSync(path.join(root, 'lib', `${name}.ts`), 'utf8');
  let code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020}}).outputText;
  code = code.replace(/from '\.\/([\w-]+)'/g, "from './$1.mjs'");
  fs.writeFileSync(path.join(out, `${name}.mjs`), code);
}
const load = name => import(pathToFileURL(path.join(out, `${name}.mjs`)).href);
const api = await load('api');
const gm = await load('generator-model');
const inv = await load('inventory');
const series = await load('series');
const diag = await load('diagnostics');
const assembly = await load('assembly-twin');
const fault = await load('fault-tests');
const captureTime = await load('capture-time');

test('capture autofill retains the instant across UTC, fractional offsets and daylight saving', () => {
  const previousZone = process.env.TZ;
  try {
    for (const [zone, instant, expected] of [
      ['UTC', '2026-10-11T08:35:09.987Z', '2026-10-11T08:35:09+00:00'],
      ['Asia/Kolkata', '2026-10-11T08:35:09.987Z', '2026-10-11T14:05:09+05:30'],
      ['Asia/Kathmandu', '2026-10-11T23:59:01Z', '2026-10-12T05:44:01+05:45'],
      ['America/New_York', '2026-01-01T00:01:02Z', '2025-12-31T19:01:02-05:00'],
      ['America/New_York', '2026-07-01T00:01:02Z', '2026-06-30T20:01:02-04:00'],
      ['America/New_York', '2026-11-01T05:30:02Z', '2026-11-01T01:30:02-04:00'],
      ['America/New_York', '2026-11-01T06:30:02Z', '2026-11-01T01:30:02-05:00'],
    ]) {
      process.env.TZ = zone;
      const result = captureTime.captureTimeNow(new Date(instant));
      assert.equal(result, expected);
      assert.equal(Date.parse(result), Math.floor(Date.parse(instant) / 1000) * 1000);
    }
  } finally {
    if (previousZone === undefined) delete process.env.TZ;
    else process.env.TZ = previousZone;
  }
});

// Topology strings and saved equivalents as produced by backend/app/optimization/networks.py.
const NETWORKS = [
  ['1×30Ω', 30, [[30, 1]]],
  ['2×20Ω', 40, [[20, 2]]],
  ['30Ω ∥ 465Ω', 28.181818181818183, [[30, 1], [465, 1]]],
  ['30Ω ∥ (465Ω + 3700Ω)', (30 * 4165) / 4195, [[30, 1], [465, 1], [3700, 1]]],
  ['30Ω ∥ 465Ω ∥ 3700Ω', 1 / (1 / 30 + 1 / 465 + 1 / 3700), [[30, 1], [465, 1], [3700, 1]]],
  ['15Ω + (10Ω ∥ 75Ω)', 23.823529411764707, [[10, 1], [15, 1], [75, 1]]],
  ['20Ω + (5Ω ∥ 20Ω)', 24, [[5, 1], [20, 2]]],
  ['1×465Ω + 1×3700Ω', 4165, [[465, 1], [3700, 1]]],
  ['3×520Ω in parallel', 520 / 3, [[520, 3]]],
  ['(10Ω + 15Ω) ∥ (20Ω)', 1 / (1 / 25 + 1 / 20), [[10, 1], [15, 1], [20, 1]]],
];
const parts = list => list.map(([ohm, perStage]) => ({ohm, perStage, total: null, available: null}));

test('verified topology trees reproduce saved equivalents and counts', () => {
  for (const [topology, eq, counts] of NETWORKS) {
    const tree = gm.verifiedTree(topology, eq, parts(counts));
    assert.ok(tree, `parsed ${topology}`);
    assert.ok(Math.abs(gm.equivalentOhm(tree) - eq) < 1e-6 * eq, `equivalent of ${topology}`);
  }
});

test('topology text that disagrees with saved values is not drawn as wiring', () => {
  assert.equal(gm.verifiedTree('30Ω ∥ 465Ω', 30, parts([[30, 1], [465, 1]])), null, 'wrong equivalent');
  assert.equal(gm.verifiedTree('2×20Ω', 40, parts([[20, 1]])), null, 'wrong count');
  assert.equal(gm.verifiedTree('30Ω + 465Ω ∥ 10Ω', null, []), null, 'mixed operators without parentheses');
  assert.equal(gm.verifiedTree('Not recorded', null, []), null);
});

test('schematic layout keeps series along and parallel across', () => {
  const tree = gm.verifiedTree('30Ω ∥ (465Ω + 3700Ω)', (30 * 4165) / 4195, parts([[30, 1], [465, 1], [3700, 1]]));
  const layout = gm.layoutTree(tree);
  assert.equal(layout.width, 2);
  assert.equal(layout.leaves.length, 3);
  const series = layout.leaves.filter(l => l.ohm !== 30);
  assert.ok(series[0].a1 <= series[1].a0 + 1e-9, 'series parts follow each other');
});

test('request comparison treats absent and null optional fields alike', () => {
  const saved = {...api.initialInputs, stage_min: null, inventory_override: null, calibration_id: null, confirm_reference_mismatch: false};
  assert.equal(api.requestKey(saved), api.requestKey({...api.initialInputs}));
  const reordered = Object.fromEntries(Object.entries(saved).reverse());
  assert.equal(api.requestKey(saved), api.requestKey(reordered));
  assert.notEqual(api.requestKey(saved), api.requestKey({...saved, test_kv: 1430}));
  assert.notEqual(api.requestKey(saved), api.requestKey({...saved, inventory_override: {front: [], tail: [], provenance: 'x'}}));
});

test('profile and solver transitions keep their deliberate resets', () => {
  const draft = {...api.initialInputs, inventory_override: {front: [], tail: [], provenance: 'x'}, calibration_id: 'c1', require_model_agreement: true, confirm_reference_mismatch: true};
  const workbook = api.profileInputs(draft, 'workbook_reference_profile');
  assert.equal(workbook.solver, 'reference');
  assert.equal(workbook.model_mode, 'hybrid');
  assert.equal(workbook.include_base_c, false);
  for (const key of ['inventory_override', 'calibration_id']) assert.equal(workbook[key], null);
  assert.equal(workbook.require_model_agreement, false);
  assert.equal(workbook.confirm_reference_mismatch, false);
  const cpri = api.profileInputs(workbook, 'cpri_problem_brief_profile');
  assert.equal(cpri.solver, 'circuit');
  assert.equal(cpri.model_mode, 'physics');
  assert.equal(cpri.include_base_c, true);
  const circuit = api.solverInputs({...workbook, model_mode: 'experimental_v2', require_model_agreement: true}, 'circuit');
  assert.equal(circuit.model_mode, 'physics');
  assert.equal(circuit.require_model_agreement, false);
  const reference = api.solverInputs({...workbook, model_mode: 'experimental_v2', require_model_agreement: true}, 'reference');
  assert.equal(reference.model_mode, 'experimental_v2');
  assert.equal(reference.require_model_agreement, true);
  // "Try V2": workbook profile plus the experimental mode.
  const v2 = {...api.profileInputs(api.initialInputs, 'workbook_reference_profile'), model_mode: 'experimental_v2'};
  assert.equal(v2.profile_id, 'workbook_reference_profile');
  assert.equal(v2.solver, 'reference');
});

test('stock editor emits exactly the existing inventory_override payload', () => {
  const override = {front: [{ohm: 30, count_per_stage: 1}, {ohm: 465, count_per_stage: 2}], tail: [{ohm: 520, count_per_stage: 1}], provenance: 'Engineer counted rack B'};
  const built = inv.overrideFromDraft(inv.draftFromOverride(override));
  assert.deepEqual(built, {value: override});
  const blankRows = {...inv.draftFromOverride(override), front: [...inv.draftFromOverride(override).front, {ohm: '', count: ''}]};
  assert.deepEqual(inv.overrideFromDraft(blankRows), {value: override}, 'blank rows are ignored');
  assert.ok('error' in inv.overrideFromDraft({...inv.draftFromOverride(override), provenance: ''}), 'provenance required');
  assert.ok('error' in inv.overrideFromDraft({...inv.draftFromOverride(override), front: [{ohm: '30', count: ''}]}), 'count required');
  assert.ok('error' in inv.overrideFromDraft({...inv.draftFromOverride(override), front: [{ohm: '30', count: '1.5'}]}), 'whole units only');
  assert.ok('error' in inv.overrideFromDraft(inv.emptyDraft()), 'empty stock is not a payload');
});

test('time cursor reads plotted samples without inventing data', () => {
  const t = [0, 1, 2, 4], v = [0, 10, 20, 0];
  assert.equal(series.sampleAt(t, v, 1.5), 15);
  assert.equal(series.sampleAt(t, v, 3), 10);
  assert.equal(series.sampleAt(t, v, -1), 0, 'clamped before first sample');
  assert.equal(series.sampleAt(t, v, 9), 0, 'clamped after last sample');
  assert.equal(series.sampleAt(undefined, v, 1), null);
});

test('scene model follows the saved candidate and keeps unknowns unknown', () => {
  const run = {id: 'run123456789', inputs: {impulse_type: 'Lightning'}, profile: {name: 'CPRI', max_stages: 12, stage_kv: 200}};
  const candidate = {
    id: 'c1', rank: 1,
    settings: {stages: 11, charge_kv_stage: 181.9, stage_utilization: 0.91, stored_energy_kj: 22.7},
    front_network: {topology: '1×30Ω', equivalent_ohm: 30, components: [{ohm: 30, count_per_stage: 1, total_required: 11, available_per_stage: 1}], total_components: 11},
    tail_network: {topology: '1×520Ω', equivalent_ohm: 520, components: [{ohm: 520, count_per_stage: 1}], total_components: 11},
  };
  const model = gm.modelFromCandidate(run, candidate, run.profile);
  assert.equal(model.maxStages, 12);
  assert.equal(model.activeStages, 11);
  assert.deepEqual(model.stages.slice(-2), ['active', 'inactive']);
  assert.equal(model.tail.parts[0].available, null, 'missing availability stays null, not 0');
  assert.equal(gm.modelFromCandidate(run, {id: 'x'}, run.profile), null);
});

test('before/after model separates shared, newly active and deactivated stages', () => {
  const review = {id: 't1', baseline: {run_id: 'b', candidate_id: 'c11', settings: {stages: 12}}, target: {impulse_type: 'Lightning'}};
  const option = {
    candidate_id: 'c8', original_rank: 1, settings: {stages: 10, charge_kv_stage: 190}, active_stages_added: 0, active_stages_deactivated: 2,
    networks: {
      front: {baseline_topology: '30Ω ∥ 465Ω', target_topology: '1×30Ω', connection_plan_changed: true, parts: [{ohm: 30, baseline_per_stage: 1, target_per_stage: 1}, {ohm: 465, baseline_per_stage: 1, target_per_stage: 0}]},
      tail: {baseline_topology: '1×520Ω', target_topology: '1×520Ω', connection_plan_changed: false, parts: [{ohm: 520, baseline_per_stage: 1, target_per_stage: 1}]},
    },
  };
  const model = gm.modelFromTransition(review, option, {profile: {max_stages: 12}, candidates: []});
  assert.deepEqual(model.stages.slice(8), ['shared', 'shared', 'removed', 'removed']);
  assert.deepEqual(model.transition.front.find(d => d.ohm === 465), {ohm: 465, before: 1, after: 0, retained: 0, added: 0, removed: 1});
  assert.equal(model.transition.deactivated, 2);
});

test('formatting distinguishes zero from missing', () => {
  assert.equal(api.fmt(0, 2), '0.00');
  assert.equal(api.fmt(null), '—');
  assert.equal(api.fmt(Number.NaN), '—');
  assert.equal(api.signed(0.004, 2), '0.00');
  assert.equal(api.signed(1.5, 1), '+1.5');
  assert.equal(api.signed(undefined), '—');
});

test('custom generator needs every rating and is reset when leaving the profile', () => {
  const custom = api.profileInputs(api.initialInputs, api.CUSTOM_PROFILE_ID);
  assert.equal(custom.solver, 'circuit');
  assert.equal(custom.model_mode, 'physics');
  assert.equal(custom.inventory_override, null);
  assert.ok(api.customProfileGaps(custom.custom_profile).includes('stage capacitance'));
  const complete = {...custom.custom_profile, name: 'Lab', source: 'Nameplate', max_stages: 6, stage_kv: 100, stage_c_uf: 0.5, energy_stage_kj: 2.5, energy_total_kj: 15};
  assert.deepEqual(api.customProfileGaps(complete), []);
  assert.equal(api.customProfileView(complete).voltage_max_kv, 600);
  const back = api.profileInputs({...custom, custom_profile: complete}, 'cpri_problem_brief_profile');
  assert.equal(back.custom_profile, null);
  assert.equal(api.requestKey({...api.initialInputs}), api.requestKey({...api.initialInputs, custom_profile: null}));
});

test('diagnostic steps follow the saved session and show stale results', () => {
  const s = diag.stepStates({next_step: 'compare', stale: {}});
  assert.deepEqual([s.reference, s.upload, s.calibrate, s.compare, s.investigate], ['done', 'done', 'done', 'current', 'waiting']);
  const stale = diag.stepStates({next_step: 'compare', stale: {comparison: 'x', investigation: 'y'}});
  assert.equal(stale.compare, 'stale');
  assert.equal(stale.investigate, 'stale');
  assert.equal(diag.stepStates({next_step: 'findings', stale: {}}).findings, 'done');
  assert.equal(diag.stepStates(null).reference, 'current');
});

test('axis calibration gaps refuse log axes, double divider and close anchors', () => {
  const base = {mode: 'anchors', voltage_side: 'high_voltage', divider_ratio: 1, x_anchors: [{px: 10, value: 0}, {px: 400, value: 60}], y_anchors: [{px: 500, value: 0}, {px: 40, value: 1600}]};
  assert.deepEqual(diag.calibrationGaps(base), []);
  assert.ok(diag.calibrationGaps({...base, x_scale: 'log'})[0].startsWith('Logarithmic'));
  assert.ok(diag.calibrationGaps({...base, divider_ratio: 1000}).some(g => g.includes('divider ratio must be 1')));
  assert.ok(diag.calibrationGaps({...base, voltage_side: 'instrument', divider_ratio: 1000}).includes('source of the divider ratio'));
  assert.ok(diag.calibrationGaps({...base, x_anchors: [{px: 10, value: 0}, {px: 20, value: 60}]}).some(g => g.includes('20 px')));
  assert.ok(diag.calibrationGaps({...base, y_anchors: [{px: 500, value: 0}, {px: 40, value: 0}]}).some(g => g.includes('different values')));
});

test('oscilloscope divisions give the same anchors as the backend', () => {
  const a = diag.perDivisionAnchors({left_px: 100, right_px: 1100, top_px: 50, bottom_px: 850, divisions_x: 10, divisions_y: 8, time_per_div: 6, time_at_left: -6, volts_per_div: 300, value_at_center: 400});
  assert.deepEqual(a.x, [[100, -6], [1100, 54]]);
  assert.deepEqual(a.y, [[450, 400], [50, 1600]]);
  assert.equal(diag.perDivisionAnchors({left_px: 1}), null);
});

test('hypotheses are grouped by category and fitted values read plainly', () => {
  const inv = {ranking: ['b', 'a'], hypotheses: [
    {id: 'baseline', category: null}, {id: 'a', category: 'hardware'}, {id: 'b', category: 'hardware'}, {id: 'g', category: 'measurement'}]};
  const groups = diag.groupHypotheses(inv);
  assert.deepEqual(groups.map(g => g.category), ['hardware', 'measurement']);
  assert.deepEqual(groups[0].items.map(h => h.id), ['b', 'a']);
  assert.equal(diag.paramText('front_factor', 0.8217), 'Front network 0.822×');
  assert.equal(diag.paramText('extra_load_pf', 350.4), 'Load-side capacitance +350 pF');
  assert.equal(diag.paramText('time_shift_us', -0.0654), 'Time offset -0.065 µs');
  assert.equal(diag.statusTone('Possible cause'), 'cyan');
  assert.equal(diag.statusTone('Cannot explain with the current model'), 'red');
  assert.equal(diag.uploadedLabel({upload: {source: 'image', label: 'anything'}}), 'Digitized from image — approximate');
});

const assemblyFixture = () => ({
  run: {
    id: 'saved-cpri',
    inputs: {impulse_type: 'Lightning', connection_mode: 'series_marx_equivalent', load_c_pf: 650, divider_c_pf: 250, stray_c_pf: 55, include_base_c: true, l_uh: 12},
    profile: {name: 'CPRI source reference', max_stages: 12, stage_kv: 200, stage_c_uf: 0.125, base_c_pf: 545},
    inventory_provenance: 'Assumed stock — generated demonstration',
  },
  candidate: {
    id: 'c1', rank: 1,
    settings: {stages: 11, charge_kv_stage: 181.90279026170387, front_r_stage: 30, tail_r_stage: 520, stored_energy_kj: 22.748430},
    front_network: {topology: '1×30Ω', equivalent_ohm: 30, components: [{ohm: 30, count_per_stage: 1, total_required: 11}], total_components: 11},
    tail_network: {topology: '1×520Ω', equivalent_ohm: 520, components: [{ohm: 520, count_per_stage: 1, total_required: 11}], total_components: 11},
    compliance: {nominal_pass: true},
  },
});

test('assembly twin keeps stage storage distinct from the saved load-side contributions', () => {
  const {run, candidate} = assemblyFixture();
  const model = assembly.assemblyModelFromCandidate(run, candidate);
  assert.equal(model.stageCapacitanceUf, 0.125);
  assert.equal(model.generatorCapacitanceUf, 0.125 / 11, 'series equivalent uses active stages, not the 12 available stages');
  assert.deepEqual(model.capacitance, {loadPf: 650, dividerPf: 250, strayPf: 55, basePf: 545, includeBase: true, totalPf: 1500});
  assert.equal(model.frontPerStageOhm, 30);
  assert.equal(model.totalFrontOhm, 330);
  assert.equal(model.tailPerStageOhm, 520);
  assert.equal(model.totalTailOhm, 5720);
  assert.equal(model.inductanceUh, 12);
  assert.equal(model.stockProvenance, 'Assumed stock — generated demonstration');
});

test('assembly twin does not infer series totals for an unrecorded or different connection mode', () => {
  const {run, candidate} = assemblyFixture();
  for (const connection_mode of [undefined, 'unverified_layout']) {
    const model = assembly.assemblyModelFromCandidate({...run, inputs: {...run.inputs, connection_mode}}, candidate);
    assert.equal(model.seriesEquivalent, false);
    assert.equal(model.totalFrontOhm, null);
    assert.equal(model.totalTailOhm, null);
    assert.equal(model.generatorCapacitanceUf, null);
    assert.equal(model.frontPerStageOhm, 30, 'recorded per-stage values remain visible');
  }
});

test('assembly twin preserves unknown values and distinguishes excluded base from unknown base', () => {
  const {run, candidate} = assemblyFixture();
  const unknown = {...run, profile: {name: 'Partial record', max_stages: 12}, inventory_provenance: undefined, inputs: {...run.inputs, l_uh: undefined}};
  const model = assembly.assemblyModelFromCandidate(unknown, candidate);
  assert.equal(model.stageCapacitanceUf, null);
  assert.equal(model.generatorCapacitanceUf, null);
  assert.equal(model.generator.stageRatingKv, null);
  assert.equal(model.generator.front.parts[0].available, null);
  assert.equal(model.inductanceUh, null);
  assert.equal(model.stockProvenance, null);
  assert.equal(model.capacitance.basePf, null);
  assert.equal(model.capacitance.totalPf, null, 'unknown included contribution must not silently become zero');
  const excluded = assembly.assemblyModelFromCandidate({...unknown, inputs: {...unknown.inputs, include_base_c: false}}, candidate);
  assert.equal(excluded.capacitance.basePf, 0);
  assert.equal(excluded.capacitance.totalPf, 955);
  const undecided = assembly.assemblyModelFromCandidate({...run, inputs: {...run.inputs, include_base_c: undefined}}, candidate);
  assert.equal(undecided.capacitance.includeBase, null);
  assert.equal(undecided.capacitance.totalPf, null);
  const zeros = assembly.assemblyModelFromCandidate({...run, inputs: {...run.inputs, load_c_pf: 0, divider_c_pf: 0, stray_c_pf: 0, l_uh: 0, include_base_c: false}}, candidate);
  assert.equal(zeros.capacitance.totalPf, 0);
  assert.equal(zeros.inductanceUh, 0);
});

test('assembly twin retains the verified topology gate without repairing mismatched saved wiring', () => {
  const {run, candidate} = assemblyFixture();
  const bad = {...candidate, front_network: {...candidate.front_network, topology: '30Ω ∥ 465Ω'}};
  const model = assembly.assemblyModelFromCandidate(run, bad);
  assert.equal(model.generator.front.tree, null);
  assert.equal(model.generator.tail.tree.kind, 'R');
  assert.equal(assembly.assemblyModelFromCandidate(run, {id: 'missing-settings'}), null);
});

test('assembly progress identity follows the full immutable saved snapshot', () => {
  const {run, candidate} = assemblyFixture();
  const before = JSON.stringify({run, candidate});
  const freeze = value => {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  };
  freeze(run); freeze(candidate);
  const model = assembly.assemblyModelFromCandidate(run, candidate);
  assert.equal(JSON.stringify({run, candidate}), before);
  const changes = [
    [{...run, id: 'other-run'}, candidate],
    [run, {...candidate, id: 'other-rank'}],
    [{...run, profile: {...run.profile, stage_c_uf: 3}}, candidate],
    [{...run, inputs: {...run.inputs, load_c_pf: 800}}, candidate],
    [run, {...candidate, settings: {...candidate.settings, stages: 10}}],
    [run, {...candidate, front_network: {...candidate.front_network, topology: 'not recorded'}}],
    [{...run, inventory_provenance: 'Counted by operator'}, candidate],
    [{...run, parameter_calibration_review: {id: 'new-calibration'}}, candidate],
  ];
  for (const [nextRun, nextCandidate] of changes) assert.notEqual(assembly.assemblyModelFromCandidate(nextRun, nextCandidate).key, model.key);
  assert.equal(model.hasEffectiveParameters, false);
  assert.equal(assembly.assemblyModelFromCandidate(changes.at(-1)[0], candidate).hasEffectiveParameters, true);
  model.parts[0].title = 'changed display copy';
  assert.equal(assembly.assemblyModelFromCandidate(run, candidate).parts[0].title, 'Stage capacitor bank');
});

test('virtual placement requires the briefing and ordered groups and blocks stale plans', () => {
  const order = ['stages', 'front', 'tail', 'inductance', 'load'];
  assert.deepEqual(assembly.ASSEMBLY_ORDER, order);
  for (const [index, part] of order.entries()) {
    const prior = order.slice(0, index);
    assert.equal(assembly.canPlaceAssemblyPart(part, prior, true), true);
    assert.equal(assembly.canPlaceAssemblyPart(part, prior, false), false, 'briefing acknowledgement required');
    assert.equal(assembly.canPlaceAssemblyPart(part, prior, true, true), false, 'unsolved edits block progress');
    assert.equal(assembly.canPlaceAssemblyPart(part, [...prior, part], true), false, 'duplicate placement blocked');
    if (index > 0) assert.equal(assembly.canPlaceAssemblyPart(part, prior.slice(1), true), false, 'a missing preceding group cannot be skipped');
  }
  assert.equal(assembly.canPlaceAssemblyPart('unknown', [], true), false);
});

const faultReference = () => ({
  supported: {chopped_impulse: true, stage_failure: true},
  healthy: {metrics: {crest_kv: 1425, peak_time_us: 2.5}, waveform: {time_us: [0, 0.5, 2.5, 50, 300], voltage_kv: [0, 800, 1425, 750, 5]}},
});
const chopRequest = {test_type: 'chopped_impulse', chop_mode: 'front', chop_time_us: 0.5, shunt_r_ohm: 5, shunt_l_uh: 1};

test('fault experiment identity invalidates results when the saved electrical setup changes', () => {
  const {run, candidate} = assemblyFixture();
  const key = fault.faultSnapshotKey(run, candidate);
  assert.ok(key);
  assert.equal(fault.faultSnapshotKey(null, candidate), '');
  assert.equal(fault.faultSnapshotKey(run, null), '');
  for (const [r, c] of [
    [{...run, id: 'another-run'}, candidate],
    [run, {...candidate, id: 'another-candidate'}],
    [{...run, inputs: {...run.inputs, load_c_pf: 750}}, candidate],
    [{...run, profile: {...run.profile, stage_c_uf: 3}}, candidate],
    [run, {...candidate, settings: {...candidate.settings, charge_kv_stage: 175}}],
    [{...run, parameter_calibration_review: {id: 'new-fit'}}, candidate],
    [run, {...candidate, calibration: {id: 'new-one-shot-offset'}}],
  ]) assert.notEqual(fault.faultSnapshotKey(r, c), key);
});

test('front and tail chopping are distinguished using prospective peak rather than front-time target', () => {
  const ref = faultReference();
  assert.equal(fault.classifyChop(2, 2.5), 'front', '2 microseconds can still precede the peak');
  assert.equal(fault.classifyChop(2.5, 2.5), 'at_peak');
  assert.equal(fault.classifyChop(5, 2.5), 'tail');
  assert.deepEqual(fault.faultRequestProblems(chopRequest, ref, 11), []);
  assert.ok(fault.faultRequestProblems({...chopRequest, chop_mode: 'tail'}, ref, 11).length);
  assert.ok(fault.faultRequestProblems({...chopRequest, chop_time_us: 2.5}, ref, 11).length);
  assert.ok(fault.faultRequestProblems({...chopRequest, chop_time_us: 301, chop_mode: 'tail'}, ref, 11).length);
});

test('fault controls allow a resistive zero-inductance shunt and reject nonphysical numbers', () => {
  const ref = faultReference();
  assert.deepEqual(fault.faultRequestProblems({...chopRequest, shunt_l_uh: 0}, ref, 11), []);
  for (const patch of [{shunt_l_uh: -1}, {shunt_l_uh: Infinity}, {shunt_r_ohm: 0}, {shunt_r_ohm: NaN}, {chop_time_us: NaN}, {chop_time_us: -1}])
    assert.ok(fault.faultRequestProblems({...chopRequest, ...patch}, ref, 11).length, JSON.stringify(patch));
});

test('uncharged conducting stages and a bypassed stack have distinct zero-contribution limits', () => {
  const ref = faultReference();
  const uncharged = {test_type: 'stage_failure', failure_mode: 'uncharged_conducting', stage_indices: [1, 2, 3], remaining_charge_fraction: 0};
  assert.deepEqual(fault.faultRequestProblems(uncharged, ref, 3), []);
  assert.ok(fault.faultRequestProblems({...uncharged, failure_mode: 'bypassed'}, ref, 3).length, 'bypassing every stage leaves no generator');
  assert.deepEqual(fault.faultRequestProblems({...uncharged, failure_mode: 'bypassed', stage_indices: [1]}, ref, 3), []);
  assert.ok(fault.faultRequestProblems({...uncharged, failure_mode: 'bypassed', stage_indices: [1], remaining_charge_fraction: 0.5}, ref, 3).length);
  for (const stage_indices of [[], [0], [4], [1, 1], [1.5]])
    assert.ok(fault.faultRequestProblems({...uncharged, stage_indices}, ref, 3).length);
  for (const remaining_charge_fraction of [-0.1, 1.1, NaN])
    assert.ok(fault.faultRequestProblems({...uncharged, remaining_charge_fraction}, ref, 3).length);
});

test('unsupported fault types stay unavailable and stage identifiers remain one based', () => {
  const ref = {...faultReference(), supported: {chopped_impulse: false, stage_failure: true}};
  assert.ok(fault.faultRequestProblems(chopRequest, ref, 11).some(p => p.includes('Lightning')));
  assert.deepEqual(fault.selectedStageIndices([3, 1, 1, -1, 0, 12, 2.2], 11), [1, 3]);
});

test('changing fault parameters marks the old generated result as a different experiment', () => {
  assert.equal(fault.faultRequestKey(chopRequest), fault.faultRequestKey(Object.fromEntries(Object.entries(chopRequest).reverse())));
  for (const patch of [{chop_time_us: 0.6}, {shunt_l_uh: 2}, {shunt_r_ohm: 10}, {chop_mode: 'tail'}])
    assert.notEqual(fault.faultRequestKey({...chopRequest, ...patch}), fault.faultRequestKey(chopRequest));
});
