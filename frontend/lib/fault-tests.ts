import {api, apiUrl, Data, isNum, stableKey} from './api';

export type FaultTestType = 'chopped_impulse' | 'stage_failure';
export type ChopMode = 'front' | 'tail';
export type StageFailureMode = 'uncharged_conducting' | 'bypassed';

export interface FaultWaveform {
  time_us: number[];
  voltage_kv: number[];
  kind?: string;
  label?: string;
}
export interface FaultMetrics {
  crest_kv: number;
  peak_time_us: number | null;
  front_us: number | null;
  tail_us: number | null;
  minimum_kv: number;
  reversal_pct: number;
  definition: string;
  front_tail_status: string;
}
export interface FaultTrace {metrics: FaultMetrics; waveform: FaultWaveform;}
export interface FaultReference {
  reference: Data;
  healthy: FaultTrace;
  defaults: {front_chop_time_us: number; tail_chop_time_us: number; shunt_r_ohm: number; shunt_l_uh: number};
  limits?: {chop_time_max_us: number; shunt_r_ohm: number[]; shunt_l_uh: number[]; stage_indices: number[]};
  supported: {chopped_impulse: boolean; stage_failure: boolean};
  assumptions: string[];
  limitations: string[];
}
export type FaultRequest = {
  test_type: 'chopped_impulse'; chop_mode: ChopMode; chop_time_us: number; shunt_r_ohm: number; shunt_l_uh: number;
} | {
  test_type: 'stage_failure'; failure_mode: StageFailureMode; stage_indices: number[]; remaining_charge_fraction: number;
};
export interface FaultResult {
  id: string; created_at: string; version: string; request: FaultRequest;
  reference: Data; healthy: FaultTrace; fault: FaultTrace;
  comparison: Data; event: Data; energy: Data; assumptions: string[]; limitations: string[]; checks: Data;
}

/** The entire saved circuit snapshot is part of the local experiment identity. */
export function faultSnapshotKey(run: Data | null, candidate: Data | null): string {
  if (!run?.id || !candidate?.id || !isNum(candidate.settings?.stages) || candidate.settings.stages < 1) return '';
  return stableKey({run: run.id, candidate: candidate.id, inputs: run.inputs, profile: run.profile,
    settings: candidate.settings, parameter_calibration_review: run.parameter_calibration_review,
    calibration: candidate.calibration});
}

/** One-based positions are explanatory identifiers; their position is not resolved by the lumped model. */
export function selectedStageIndices(indices: readonly number[], count: number): number[] {
  return [...new Set(indices)].filter(i => Number.isInteger(i) && i >= 1 && i <= count).sort((a, b) => a - b);
}

export function classifyChop(timeUs: number, peakUs: number): ChopMode | 'at_peak' {
  if (Math.abs(timeUs - peakUs) <= Math.max(1e-12, peakUs * 1e-9)) return 'at_peak';
  return timeUs < peakUs ? 'front' : 'tail';
}

export function faultRequestKey(request: FaultRequest): string {return stableKey(request);}

export function faultRequestProblems(request: FaultRequest, reference: FaultReference, stageCount: number): string[] {
  const problems: string[] = [];
  if (!reference.supported[request.test_type]) problems.push(request.test_type === 'chopped_impulse'
    ? 'Chopped-impulse exploration is available for supported Lightning setups only.' : 'This circuit topology does not support stage-failure exploration.');
  if (request.test_type === 'chopped_impulse') {
    const peak = reference.healthy.metrics.peak_time_us;
    const end = reference.healthy.waveform.time_us.at(-1);
    if (!isNum(request.chop_time_us) || request.chop_time_us <= 0 || request.chop_time_us > 100000 || !isNum(end) || request.chop_time_us > end)
      problems.push('Enter a positive chop time within the healthy simulation window.');
    else if (!isNum(peak)) problems.push('The healthy peak time is unavailable; this event cannot be classified.');
    else if (classifyChop(request.chop_time_us, peak) !== request.chop_mode)
      problems.push(request.chop_mode === 'front' ? 'A front chop must happen before the healthy peak.' : 'A tail chop must happen after the healthy peak.');
    if (!isNum(request.shunt_r_ohm) || request.shunt_r_ohm < 0.5 || request.shunt_r_ohm > 10000) problems.push('The assumed shunt resistance must be between 0.5 and 10,000 Ω within this simulation’s bounds.');
    if (!isNum(request.shunt_l_uh) || request.shunt_l_uh < 0 || request.shunt_l_uh > 10000) problems.push('The assumed shunt inductance must be between 0 and 10,000 µH within this simulation’s bounds.');
  } else {
    const selected = selectedStageIndices(request.stage_indices, stageCount);
    if (!selected.length || selected.length !== request.stage_indices.length) problems.push('Select at least one valid saved stage.');
    if (request.failure_mode === 'bypassed' && selected.length >= stageCount) problems.push('A bypass simulation must retain at least one contributing stage.');
    if (!isNum(request.remaining_charge_fraction) || request.remaining_charge_fraction < 0 || request.remaining_charge_fraction > 1)
      problems.push('Remaining charge fraction must be between 0 and 1.');
    if (request.failure_mode === 'bypassed' && request.remaining_charge_fraction !== 0) problems.push('A deliberately bypassed stage has zero contribution.');
  }
  return problems;
}

export const loadFaultReference = (runId: string, candidateId: string, signal?: AbortSignal): Promise<FaultReference> =>
  api(`/api/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/fault-tests/reference`, {signal});
export const runFaultTest = (runId: string, candidateId: string, request: FaultRequest, signal?: AbortSignal): Promise<FaultResult> =>
  api(`/api/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/fault-tests`, {method: 'POST', body: JSON.stringify(request), signal});
export const faultExportUrl = (id: string, format: 'json' | 'csv' | 'report') => apiUrl(`/api/fault-tests/${encodeURIComponent(id)}/${format}`);
