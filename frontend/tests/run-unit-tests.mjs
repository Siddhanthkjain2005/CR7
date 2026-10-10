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
for (const name of ['api', 'generator-model', 'inventory', 'series', 'diagnostics']) {
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
