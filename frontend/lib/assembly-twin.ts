import {Data, isNum} from './api';
import {GeneratorModel, modelFromCandidate} from './generator-model';

export type AssemblyPartId = 'stages' | 'front' | 'tail' | 'inductance' | 'load';
export const ASSEMBLY_ORDER: readonly AssemblyPartId[] = ['stages', 'front', 'tail', 'inductance', 'load'];

export interface AssemblyPart {
  id: AssemblyPartId;
  symbol: string;
  title: string;
  shortTitle: string;
  explanation: string;
  analogy: string;
  precaution: string;
  checkpoint: string;
}

export interface AssemblyTwinModel {
  /** A virtual plan belongs to the full saved snapshot, not just its displayed ID. */
  key: string;
  generator: GeneratorModel;
  stageCapacitanceUf: number | null;
  generatorCapacitanceUf: number | null;
  frontPerStageOhm: number | null;
  totalFrontOhm: number | null;
  tailPerStageOhm: number | null;
  totalTailOhm: number | null;
  inductanceUh: number | null;
  capacitance: {
    loadPf: number | null;
    dividerPf: number | null;
    strayPf: number | null;
    basePf: number | null;
    includeBase: boolean | null;
    totalPf: number | null;
  };
  stockProvenance: string | null;
  hasEffectiveParameters: boolean;
  seriesEquivalent: boolean;
  nominalPass: boolean | null;
  parts: AssemblyPart[];
}

const PARTS: AssemblyPart[] = [
  {
    id: 'stages', symbol: 'Cₛ', title: 'Stage capacitor bank', shortTitle: 'Stage bank',
    explanation: 'The generator stores electrical energy in its stage capacitors. The saved recommendation chooses how many stages are active and a charge for each stage. In the erected series equivalent, bank capacitance is the stage capacitance divided by the active stage count.',
    analogy: 'Think of separate energy buckets. The picture groups them; it does not show how to connect real buckets.',
    precaution: 'Capacitors may retain hazardous energy after the supply is off. Real equipment must remain under the site’s isolation and stored-energy procedures; only qualified, authorized personnel can verify those conditions.',
    checkpoint: 'I reviewed the saved stage count, capacitance and stored-energy warning.',
  },
  {
    id: 'front', symbol: 'Rᶠ', title: 'Front resistor network', shortTitle: 'Front network',
    explanation: 'This resistor group helps shape the fast rising part of the impulse. Its saved value is per stage. The series-Marx circuit represents all active stages by n × that value. Interactions with C and L also affect the rise.',
    analogy: 'It is like a narrow passage controlling how quickly energy reaches the test object.',
    precaution: 'A resistance match is not proof that a physical resistor is suitable. Pulse-energy ratings, insulation, mounting and condition need documented engineering review. The drawing cannot inspect them.',
    checkpoint: 'I reviewed the per-stage network and its unknown physical ratings.',
  },
  {
    id: 'tail', symbol: 'Rᵗ', title: 'Tail resistor network', shortTitle: 'Tail network',
    explanation: 'This separate resistor group influences the falling part of the impulse. The assumed lumped circuit places its equivalent across the generator capacitance. It is not interchangeable with the front network just because both are resistors.',
    analogy: 'It is like a drain that changes how long the stored energy lasts.',
    precaution: 'A predicted waveform decay does not prove stored charge has been removed. Qualified staff must independently verify isolation and stored-energy controls under the approved site procedure.',
    checkpoint: 'I reviewed the tail network and the difference between waveform decay and verified isolation.',
  },
  {
    id: 'inductance', symbol: 'L', title: 'Connection inductance', shortTitle: 'Layout / L',
    explanation: 'L represents the inductance of the assumed current path. It resists rapid changes in current and may affect ringing. This model value does not necessarily describe a separate coil to install.',
    analogy: 'Think of energy having momentum: it cannot change speed instantly.',
    precaution: 'Physical layout, grounding, bonding and protective clearances require a qualified laboratory review. Browser geometry is schematic and supplies no installation dimensions or grounding verification.',
    checkpoint: 'I reviewed L as a layout assumption, not an instruction to install a coil.',
  },
  {
    id: 'load', symbol: 'Cₗ', title: 'Load-side capacitance', shortTitle: 'Load / C',
    explanation: 'The load-side total groups the test object, divider, stray capacitance and the profile’s basic capacitance when included. These are different sources of capacitance; the total is not a shopping list for one extra capacitor.',
    analogy: 'It is the combined size of the receiving buckets, including effects that are not separate visible parts.',
    precaution: 'The divider, test object and nearby conductive structures can change both exposure and the waveform. Ratings, barriers, interlocks and the laboratory’s measurement arrangement need independent verification; this picture cannot establish personal safety.',
    checkpoint: 'I reviewed the separate load contributions and the limits of this virtual layout.',
  },
];

const numberOrNull = (value: unknown): number | null => isNum(value) ? value : null;
const textOrNull = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value : null;

/** Display-only derivation from the saved recommendation; never changes its settings or solves a circuit. */
export function assemblyModelFromCandidate(run: Data | null | undefined, candidate: Data | null | undefined): AssemblyTwinModel | null {
  const generator = modelFromCandidate(run, candidate, run?.profile);
  if (!generator || !run || !candidate) return null;
  const profile = run.profile || {};
  const inputs = run.inputs || {};
  const settings = candidate.settings;
  const includeBase = typeof inputs.include_base_c === 'boolean' ? inputs.include_base_c : null;
  const loadPf = numberOrNull(inputs.load_c_pf);
  const dividerPf = numberOrNull(inputs.divider_c_pf);
  const strayPf = numberOrNull(inputs.stray_c_pf);
  const basePf = includeBase === false ? 0 : includeBase === true ? numberOrNull(profile.base_c_pf) : null;
  const terms = [loadPf, dividerPf, strayPf, basePf];
  const totalPf = terms.every(isNum) ? (terms as number[]).reduce((a, b) => a + b, 0) : null;
  const stageCapacitanceUf = numberOrNull(profile.stage_c_uf);
  const frontPerStageOhm = numberOrNull(settings.front_r_stage);
  const tailPerStageOhm = numberOrNull(settings.tail_r_stage);
  const seriesEquivalent = inputs.connection_mode === 'series_marx_equivalent';
  const n = generator.activeStages;
  const hasEffectiveParameters = !!(run.parameter_calibration_review || profile.effective_parameters);
  const snapshot = {
    run: run.id, candidate: candidate.id, profile, inputs, settings,
    front: candidate.front_network, tail: candidate.tail_network,
    inventory_provenance: run.inventory_provenance,
    parameter_calibration_review: run.parameter_calibration_review,
  };
  return {
    key: JSON.stringify(snapshot), generator, stageCapacitanceUf,
    generatorCapacitanceUf: seriesEquivalent && stageCapacitanceUf !== null && n > 0 ? stageCapacitanceUf / n : null,
    frontPerStageOhm, tailPerStageOhm,
    totalFrontOhm: seriesEquivalent && frontPerStageOhm !== null && n > 0 ? frontPerStageOhm * n : null,
    totalTailOhm: seriesEquivalent && tailPerStageOhm !== null && n > 0 ? tailPerStageOhm * n : null,
    inductanceUh: numberOrNull(inputs.l_uh),
    capacitance: {loadPf, dividerPf, strayPf, basePf, includeBase, totalPf},
    stockProvenance: textOrNull(run.inventory_provenance) || textOrNull(inputs.inventory_override?.provenance),
    hasEffectiveParameters, seriesEquivalent,
    nominalPass: typeof candidate.compliance?.nominal_pass === 'boolean' ? candidate.compliance.nominal_pass : null,
    parts: PARTS.map(part => ({...part})),
  };
}

/** Teaching order only. It is not a sequence for physically assembling or energizing equipment. */
export function canPlaceAssemblyPart(id: AssemblyPartId, placed: readonly AssemblyPartId[], briefingReviewed: boolean, stale = false): boolean {
  if (stale || !briefingReviewed || placed.includes(id)) return false;
  const index = ASSEMBLY_ORDER.indexOf(id);
  return index >= 0 && ASSEMBLY_ORDER.slice(0, index).every(part => placed.includes(part));
}
