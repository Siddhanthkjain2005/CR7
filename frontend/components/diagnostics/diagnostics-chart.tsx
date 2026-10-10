'use client';
import {useEffect, useMemo, useRef, useState} from 'react';
import {Maximize2} from 'lucide-react';
import {Data} from '@/lib/api';

/**
 * Overlay of the separately labelled curves with a residual plot underneath.
 * Both plots share one time axis, one zoom and one cursor. Samples are plotted
 * as given; nothing is smoothed, resampled, stretched or normalized unless the
 * labelled normalized view is switched on.
 */
export type Curve = {id: string; label: string; time_us: number[]; values: number[]; colour: string; dash?: 'dashed' | 'dotted'; width?: number; note?: string};

export default function DiagnosticsChart({curves, residual, normalized = false, height = 420}: {curves: Curve[]; residual?: {time_us: number[]; kv: number[]} | null; normalized?: boolean; height?: number}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState('');
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const shown = useMemo(() => curves.filter(c => !hidden[c.id]), [curves, hidden]);
  const span = useMemo(() => {
    const all = curves.flatMap(c => [c.time_us[0], c.time_us[c.time_us.length - 1]]).filter(Number.isFinite);
    const observed = curves.find(c => c.id === 'uploaded');
    const end = observed ? observed.time_us[observed.time_us.length - 1] : Math.max(...all);
    return [Math.min(0, ...all.filter(v => v < 0)), end];
  }, [curves]);

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    import('echarts')
      .then(e => {
        if (cancelled || !el.current) return;
        chart.current = e.init(el.current, undefined, {renderer: 'canvas'});
        observer = new ResizeObserver(() => chart.current?.resize());
        observer.observe(el.current);
        setReady(true);
      })
      .catch(err => !cancelled && setFailed(String(err?.message || err)));
    return () => {
      cancelled = true;
      observer?.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || !chart.current) return;
    const withResidual = !!residual && residual.time_us.length > 0 && !normalized;
    const label = '#5b6872', split = '#e6ebec', axis = '#b9c4c8', text = '#15202a';
    const grids = withResidual
      ? [{left: 70, right: 24, top: 22, height: '54%'}, {left: 70, right: 24, top: '70%', bottom: 64}]
      : [{left: 70, right: 24, top: 22, bottom: 64}];
    const tick = (v: number) => v.toLocaleString('en-US', {maximumSignificantDigits: 4});
    const xAxis = grids.map((_, i) => ({
      type: 'value', gridIndex: i, min: span[0], max: span[1], name: i === grids.length - 1 ? 'Time (µs)' : '', nameLocation: 'middle', nameGap: 24,
      axisLabel: {show: i === grids.length - 1, color: label, fontSize: 12, formatter: tick, showMaxLabel: false}, axisLine: {lineStyle: {color: axis}}, axisTick: {show: false},
      splitLine: {lineStyle: {color: split}},
    }));
    const yAxis = [
      {type: 'value', gridIndex: 0, name: normalized ? 'Fraction of own crest' : 'Voltage (kV)', nameTextStyle: {color: label, padding: [0, 0, 4, 0]}, axisLabel: {color: label, fontSize: 12, formatter: tick}, splitLine: {lineStyle: {color: split}}},
      ...(withResidual ? [{type: 'value', gridIndex: 1, name: 'Difference (kV)', splitNumber: 2, nameTextStyle: {color: label}, axisLabel: {color: label, fontSize: 11, formatter: tick}, splitLine: {lineStyle: {color: split}}}] : []),
    ];
    const series: Data[] = shown.map(c => ({
      name: c.label, type: 'line', xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, smooth: false, sampling: undefined,
      lineStyle: {color: c.colour, width: c.width ?? 2, type: c.dash || 'solid'}, itemStyle: {color: c.colour},
      data: c.time_us.map((t, i) => [t, c.values[i]]), z: c.id === 'uploaded' ? 6 : 4,
    }));
    if (withResidual) {
      series.push({name: 'Uploaded minus prediction', type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
        lineStyle: {color: '#6d4bd8', width: 1.4}, itemStyle: {color: '#6d4bd8'}, data: residual!.time_us.map((t, i) => [t, residual!.kv[i]]),
        markLine: {silent: true, symbol: 'none', lineStyle: {color: axis}, data: [{yAxis: 0}], label: {show: false}}});
    }
    chart.current.setOption({
      animation: false, backgroundColor: 'transparent', textStyle: {fontFamily: 'Barlow, system-ui, sans-serif', color: label},
      grid: grids, xAxis, yAxis, series,
      tooltip: {trigger: 'axis', backgroundColor: '#fff', borderColor: '#c9d2d6', textStyle: {color: text, fontSize: 13},
        valueFormatter: (v: number) => (normalized ? Number(v).toFixed(4) : `${Number(v).toFixed(2)} kV`)},
      axisPointer: {link: [{xAxisIndex: 'all'}], label: {backgroundColor: '#47555f'}},
      dataZoom: [{type: 'inside', xAxisIndex: withResidual ? [0, 1] : [0], filterMode: 'none'},
                 {type: 'slider', xAxisIndex: withResidual ? [0, 1] : [0], height: 16, bottom: 6, filterMode: 'none', brushSelect: false}],
    }, {notMerge: true, lazyUpdate: true});
  }, [ready, shown, residual, normalized, span]);

  return (
    <div className="diag-chart">
      <div className="diag-series" role="group" aria-label="Show or hide curves">
        {curves.map(c => (
          <label key={c.id} className={`diag-series-item ${hidden[c.id] ? 'off' : ''}`}>
            <input type="checkbox" checked={!hidden[c.id]} onChange={() => setHidden(h => ({...h, [c.id]: !h[c.id]}))} />
            <i style={{borderTopColor: c.colour, borderTopStyle: c.dash === 'dashed' ? 'dashed' : c.dash === 'dotted' ? 'dotted' : 'solid'}} aria-hidden />
            <span>
              <b>{c.label}</b>
              {c.note && <small>{c.note}</small>}
            </span>
          </label>
        ))}
      </div>
      <div ref={el} style={{height}} role="img" className="diag-chart-canvas"
        aria-label={`Voltage against time for: ${shown.map(c => c.label).join(', ') || 'no curves'}${residual && !normalized ? ', with the difference plotted below' : ''}. Scroll to zoom; both plots share the zoom and cursor.`} />
      {failed && <p className="chart-error">The chart library could not load ({failed}). The tables below hold every number.</p>}
      <div className="chart-tools">
        <span>Scroll or use the slider to zoom · both plots share one cursor · tick a curve to show or hide it</span>
        <button type="button" className="chart-reset" onClick={() => chart.current?.dispatchAction({type: 'dataZoom', start: 0, end: 100})}>
          <Maximize2 size={13} aria-hidden /> Reset zoom
        </button>
      </div>
    </div>
  );
}
