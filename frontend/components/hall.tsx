'use client';
import {useEffect, useMemo, useState} from 'react';
import {Crosshair, X} from 'lucide-react';
import EngineeringChart from './engineering-chart';
import {ToleranceGauge, Segmented} from './ui';
import {Data, fmt, isNum} from '@/lib/api';
import {sampleAt} from '@/lib/series';

export function predictionLabelFor(run: Data | null | undefined, c: Data | null | undefined): string {
  if (!run || !c) return 'Prediction';
  if (run.inputs?.solver === 'circuit') return 'Circuit prediction';
  if (c.ood?.trust_weight === 0) return 'Workbook metrics (reconstructed shape)';
  if (run.inputs?.model_mode === 'experimental_v2') return 'V2-corrected metrics (reconstructed shape)';
  return 'ML-corrected metrics (reconstructed shape)';
}

export function metricName(i: number, impulse: string | undefined) {
  return i === 0 ? (impulse === 'Switching' ? 'Peak time' : 'Front time') : i === 1 ? 'Time to half-value' : 'Crest voltage';
}

/** Three tolerance gauges for the selected candidate's nominal prediction and envelope. */
export function MetricGauges({candidate, impulse, theme = 'paper'}: {candidate: Data; impulse?: string; theme?: 'paper' | 'hall'}) {
  const rows: Data[] = candidate?.compliance?.rows || [];
  return (
    <div className={`gauges gauges-${theme}`}>
      {rows.slice(0, 3).map((r, i) => (
        <ToleranceGauge
          key={r.name}
          theme={theme}
          label={metricName(i, impulse)}
          unit={r.unit}
          lower={r.lower}
          upper={r.upper}
          target={r.target}
          value={r.predicted}
          interval={[candidate.uncertainty?.lower?.[i], candidate.uncertainty?.upper?.[i]]}
          pass={r.pass}
          digits={i === 2 ? 1 : 3}
        />
      ))}
    </div>
  );
}

/**
 * Oscilloscope-style view of the saved candidate's waveform with an optional
 * time cursor. The cursor reads the plotted prediction samples (linear
 * interpolation between actual samples) to drive an illustrative glow.
 */
export function Scope({
  run,
  candidate,
  measured,
  measuredLabel,
  onPulse,
  revealKey,
  height = 330,
}: {
  run: Data;
  candidate: Data;
  measured?: Data;
  measuredLabel?: string;
  onPulse?: (p: {fraction: number; label: string} | null) => void;
  revealKey?: number;
  height?: number;
}) {
  const [front, setFront] = useState(false);
  const [cursor, setCursor] = useState<number | null>(null);
  const label = predictionLabelFor(run, candidate);
  const target = run.target_waveform;
  const timeEnd: number = front ? (target?.time_us?.at(-1) || 100) * 0.035 : target?.time_us?.at(-1) || candidate.waveform?.time_us?.at(-1) || 100;
  const wave = candidate.waveform;
  const peak = useMemo(() => (Array.isArray(wave?.voltage_kv) ? Math.max(...wave.voltage_kv.filter((v: unknown) => isNum(v))) : null), [wave]);
  useEffect(() => setCursor(null), [run.id, candidate.id]);
  useEffect(() => {
    if (!onPulse) return;
    if (cursor === null || !peak) return onPulse(null);
    const v = sampleAt(wave?.time_us, wave?.voltage_kv, cursor);
    if (v === null) return onPulse(null);
    onPulse({fraction: Math.max(0, v / peak), label: `${fmt(v, 1)} kV at ${fmt(cursor, cursor < 10 ? 3 : 1)} µs on the plotted ${label.toLowerCase()}`});
  }, [cursor, peak, wave, label, onPulse]);
  const crest = candidate.compliance?.rows?.[2];
  return (
    <div className="scope">
      <div className="scope-head">
        <div className="scope-crest">
          <span className="scope-crest-value">{fmt(candidate.hybrid?.crest_kv, 1)}</span>
          <span className="scope-crest-unit">kV crest · {label.toLowerCase()}</span>
        </div>
        <Segmented
          size="small"
          label="Time window"
          value={front ? 'front' : 'full'}
          onChange={v => setFront(v === 'front')}
          options={[
            ['full', 'Full wave'],
            ['front', run.inputs?.impulse_type === 'Switching' ? 'Peak detail' : 'Front detail'],
          ]}
        />
      </div>
      <EngineeringChart
        theme="hall"
        height={height}
        waveform={wave}
        physics={run.inputs?.solver === 'reference' ? candidate.physics_waveform : undefined}
        physicsLabel="Workbook equations (reconstructed shape)"
        circuit={candidate.circuit_crosscheck?.waveform}
        target={target}
        predictionLabel={label}
        measured={measured}
        measuredLabel={measuredLabel}
        front={front}
        crestBounds={crest ? [crest.lower, crest.upper] : undefined}
        cursorUs={cursor}
        onCursor={onPulse ? t => setCursor(Math.max(0, Math.min(timeEnd, t))) : undefined}
        revealKey={revealKey}
      />
      {onPulse && (
        <div className="scope-cursor">
          <Crosshair size={15} aria-hidden />
          <label htmlFor={`cursor-${candidate.id}`}>Time cursor</label>
          <input
            id={`cursor-${candidate.id}`}
            type="range"
            min={0}
            max={timeEnd}
            step={timeEnd / 600}
            value={cursor ?? 0}
            onChange={e => setCursor(Number(e.target.value))}
            aria-valuetext={cursor === null ? 'Off' : `${fmt(cursor, 3)} microseconds`}
          />
          <output>{cursor === null ? 'Off' : `${fmt(cursor, cursor < 10 ? 3 : 1)} µs`}</output>
          {cursor !== null && (
            <button type="button" className="scope-cursor-clear" onClick={() => setCursor(null)} aria-label="Remove time cursor">
              <X size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
