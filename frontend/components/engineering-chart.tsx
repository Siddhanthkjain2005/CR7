'use client';
import {useEffect, useMemo, useRef, useState} from 'react';
import {Maximize2} from 'lucide-react';
import {Data, fmt} from '@/lib/api';
import {useQuietMotion} from '@/lib/motion';

/**
 * Engineering waveform chart. Plots the backend's actual samples without
 * smoothing, resampling or invented points. A reveal animation only clips the
 * already-drawn canvas; coordinates and values are never animated.
 */

type Theme = 'paper' | 'hall';
const PALETTE: Record<Theme, Record<string, string>> = {
  hall: {target: '#93a3ae', physics: '#7bcf83', prediction: '#2cc6da', circuit: '#e35db8', measured: '#f2c94c', axis: '#33434f', split: '#1c2a35', label: '#9aabb7', text: '#e4ebef', band: 'rgba(44,198,218,.10)', cursor: '#a28dff', tipBg: '#0b1218', tipBorder: '#2c3d4a'},
  paper: {target: '#6a7883', physics: '#2d7a3c', prediction: '#0b7d8e', circuit: '#a52f7e', measured: '#8a6800', axis: '#b9c4c8', split: '#e6ebec', label: '#5b6872', text: '#15202a', band: 'rgba(11,125,142,.08)', cursor: '#4b39a8', tipBg: '#ffffff', tipBorder: '#c9d2d6'},
};

/** Human description of what a plotted series is. */
export function waveformKind(w: Data | undefined, role: string): string {
  if (!w) return '';
  const kind = w.kind;
  if (role === 'target') return 'Target shape reconstructed from the challenge metrics; not a prediction.';
  if (kind === 'equivalent_circuit') return 'Simulated by the lumped Marx/RLC circuit; spark-gap and distributed effects omitted.';
  if (kind === 'metric_reconstruction') return 'Reconstructed from three predicted metrics; not an independently predicted waveform.';
  if (kind === 'measured_lab') return 'Captured samples declared as a laboratory measurement.';
  if (kind === 'generated_stress_test' || kind === 'generated_demo') return 'Generated demonstration samples; not laboratory evidence.';
  if (kind === 'synthetic_benchmark') return 'Synthetic benchmark samples; not laboratory evidence.';
  if (role === 'measured') return 'Uploaded samples with unknown origin; provenance requires review.';
  return w.note || 'Kind not recorded.';
}

export default function EngineeringChart({
  waveform,
  physics,
  target,
  circuit,
  measured,
  height = 330,
  front = false,
  crestBounds,
  predictionLabel = 'Prediction',
  physicsLabel = 'Physics',
  timeMaxUs,
  frontMaxUs,
  theme = 'paper',
  cursorUs,
  onCursor,
  revealKey,
  showKey = true,
  measuredLabel = 'Uploaded trial',
}: {
  waveform?: Data;
  physics?: Data;
  target?: Data;
  circuit?: Data;
  measured?: Data;
  height?: number;
  front?: boolean;
  crestBounds?: number[];
  predictionLabel?: string;
  physicsLabel?: string;
  timeMaxUs?: number;
  frontMaxUs?: number;
  theme?: Theme;
  cursorUs?: number | null;
  onCursor?: (t: number) => void;
  revealKey?: string | number;
  showKey?: boolean;
  measuredLabel?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const cursorCb = useRef(onCursor);
  cursorCb.current = onCursor;
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState('');
  const quiet = useQuietMotion();
  const [revealing, setRevealing] = useState(false);
  const colors = PALETTE[theme];

  const series = useMemo(
    () =>
      (
        [
          ['target', target, 'Target shape', 'dashed', 1.4],
          ['physics', physics, physicsLabel, 'dotted', 1.6],
          ['prediction', waveform, predictionLabel, 'solid', 2.6],
          ['circuit', circuit, 'Circuit simulation (cross-check)', 'solid', 1.8],
          ['measured', measured, measuredLabel, 'solid', 2],
        ] as const
      ).filter(([, w]) => w && Array.isArray(w.time_us) && Array.isArray(w.voltage_kv)),
    [target, physics, waveform, circuit, measured, predictionLabel, physicsLabel, measuredLabel],
  );

  // Create the chart once per mount.
  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    import('echarts')
      .then(e => {
        if (cancelled || !el.current) return;
        const chart = e.init(el.current, undefined, {renderer: 'canvas'});
        chartRef.current = chart;
        observer = new ResizeObserver(() => chart.resize());
        observer.observe(el.current);
        chart.getZr().on('click', (params: any) => {
          if (!cursorCb.current) return;
          const point = [params.offsetX, params.offsetY];
          if (!chart.containPixel('grid', point)) return;
          const [t] = chart.convertFromPixel('grid', point);
          if (Number.isFinite(t)) cursorCb.current(t);
        });
        setReady(true);
      })
      .catch(err => !cancelled && setFailed(String(err?.message || err)));
    return () => {
      cancelled = true;
      observer?.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  // Apply data/options whenever inputs change (no re-creation, no data animation).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !ready) return;
    const timeEnd = front ? (frontMaxUs ?? (target?.time_us?.at(-1) || 100) * 0.035) : (timeMaxUs ?? target?.time_us?.at(-1));
    chart.setOption(
      {
        animation: false,
        backgroundColor: 'transparent',
        textStyle: {fontFamily: 'Barlow, system-ui, sans-serif', color: colors.label},
        legend: {type: 'scroll', bottom: 0, left: 'center', itemWidth: 22, itemHeight: 8, icon: 'roundRect', textStyle: {color: colors.text, fontSize: 13}, inactiveColor: theme === 'hall' ? '#3d4c57' : '#c3ccd0'},
        tooltip: {
          trigger: 'axis',
          backgroundColor: colors.tipBg,
          borderColor: colors.tipBorder,
          textStyle: {color: colors.text, fontSize: 13, fontFamily: 'Barlow, system-ui, sans-serif'},
          axisPointer: {type: 'cross', lineStyle: {color: colors.label}, label: {backgroundColor: theme === 'hall' ? '#22313d' : '#47555f'}},
          valueFormatter: (v: number) => `${Number(v).toFixed(3)} kV`,
          order: 'seriesDesc',
        },
        grid: {left: 64, right: 22, top: 26, bottom: 64},
        xAxis: {
          type: 'value',
          name: 'Time (µs)',
          nameLocation: 'middle',
          nameGap: 30,
          nameTextStyle: {color: colors.label, fontSize: 13},
          min: 0,
          max: timeEnd,
          axisLine: {lineStyle: {color: colors.axis}},
          axisTick: {show: false},
          splitLine: {lineStyle: {color: colors.split}},
          axisLabel: {color: colors.label, fontSize: 12, formatter: (v: number) => v.toLocaleString('en-US', {maximumSignificantDigits: 5})},
        },
        yAxis: {
          type: 'value',
          name: 'Voltage (kV)',
          nameTextStyle: {color: colors.label, fontSize: 13, padding: [0, 0, 6, 0]},
          axisLine: {show: false},
          axisLabel: {color: colors.label, fontSize: 12, formatter: (v: number) => v.toLocaleString('en-US')},
          splitLine: {lineStyle: {color: colors.split}},
        },
        dataZoom: [{type: 'inside', filterMode: 'none'}],
        series: series.map(([role, w, name, type, width]) => {
          const data = (w as Data).time_us.map((t: number, i: number) => [t, (w as Data).voltage_kv[i]]);
          const color = colors[role];
          const main = role === 'prediction';
          return {
            name,
            type: 'line',
            showSymbol: false,
            smooth: false,
            sampling: undefined,
            z: main ? 5 : role === 'measured' ? 6 : 3,
            lineStyle: {color, width, type, ...(main && theme === 'hall' ? {shadowBlur: 10, shadowColor: 'rgba(44,198,218,.45)'} : {})},
            itemStyle: {color},
            emphasis: {focus: 'series'},
            data,
            ...(main
              ? {
                  areaStyle: {color: {type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{offset: 0, color: theme === 'hall' ? 'rgba(44,198,218,.16)' : 'rgba(11,125,142,.10)'}, {offset: 1, color: 'rgba(44,198,218,0)'}]}},
                  markArea: crestBounds && crestBounds.every(v => Number.isFinite(v)) ? {silent: true, itemStyle: {color: colors.band}, label: {show: true, position: 'insideTopRight', color: colors.label, fontSize: 11, formatter: 'Allowed crest'}, data: [[{yAxis: crestBounds[0]}, {yAxis: crestBounds[1]}]]} : undefined,
                  markLine:
                    typeof cursorUs === 'number' && Number.isFinite(cursorUs)
                      ? {silent: true, symbol: 'none', animation: false, lineStyle: {color: colors.cursor, width: 1.5, type: 'solid'}, label: {formatter: `t = ${fmt(cursorUs, cursorUs < 10 ? 3 : 1)} µs`, color: colors.cursor, fontSize: 12, position: 'end', distance: 4, rotate: 0}, data: [{xAxis: cursorUs}]}
                      : undefined,
                }
              : {}),
          };
        }),
      },
      {notMerge: true, lazyUpdate: true},
    );
  }, [ready, series, front, crestBounds, timeMaxUs, frontMaxUs, target, cursorUs, colors, theme]);

  // One reveal per new result: a clip sweep over the static canvas.
  useEffect(() => {
    if (revealKey === undefined || quiet) return;
    setRevealing(true);
    const t = setTimeout(() => setRevealing(false), 1000);
    return () => clearTimeout(t);
  }, [revealKey, quiet]);

  const summary = series.map(([, , name]) => name).join(', ');
  return (
    <div className={`chart chart-${theme}`}>
      <div
        className={`engineering-chart ${revealing ? 'chart-reveal' : ''}`}
        ref={el}
        style={{height}}
        role="img"
        aria-label={`Impulse voltage versus time. Series: ${summary || 'none'}. Scroll or pinch inside the plot to zoom, drag to pan, use the legend to show or hide a series.`}
      />
      {failed && <p className="chart-error">The chart library could not load ({failed}). Numerical results remain available in the tables.</p>}
      <div className="chart-tools">
        <span>Scroll to zoom · drag to pan · legend toggles a series{onCursor ? ' · click to place the time cursor' : ''}</span>
        <button type="button" className="chart-reset" onClick={() => chartRef.current?.dispatchAction({type: 'dataZoom', start: 0, end: 100})}>
          <Maximize2 size={13} aria-hidden /> Reset zoom
        </button>
      </div>
      {showKey && series.length > 0 && (
        <ul className="trace-key">
          {series.map(([role, w, name]) => (
            <li key={role}>
              <i className={`trace-swatch trace-${role}`} aria-hidden />
              <span>
                <b>{name}</b> {waveformKind(w as Data, role)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
