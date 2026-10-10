'use client';
import {useEffect, useMemo, useRef, useState, PointerEvent as ReactPointerEvent} from 'react';
import {Crop, Crosshair, Eraser, LoaderCircle, MousePointerClick, Move, Plus, RotateCw, ScanLine, Square, Wand2} from 'lucide-react';
import {Data, fmt, post} from '@/lib/api';
import {calibrationGaps, perDivisionAnchors, toImagePoint} from '@/lib/diagnostics';
import {Badge, Notice} from '../ui';

type Tool = 'plot' | 'x0' | 'x1' | 'y0' | 'y1' | 'trace' | 'erase' | 'add' | 'corner' | 'crop' | 'none';
type Rect = [number, number, number, number];
const TOOL_HELP: Record<Tool, string> = {
  plot: 'Drag a rectangle around the plot area (inside the axes).',
  x0: 'Click the first time anchor: a tick on the time axis whose value you know.',
  x1: 'Click the second time anchor, far from the first.',
  y0: 'Click the first voltage anchor: a tick on the voltage axis whose value you know.',
  y1: 'Click the second voltage anchor, far from the first.',
  trace: 'Click directly on the waveform you want to extract.',
  erase: 'Drag a rectangle over samples to remove (for example a legend or another curve).',
  add: 'Click to add a manual point. Manual points stay marked as manual.',
  corner: 'Click the plot corners in order: top-left, top-right, bottom-right, bottom-left.',
  crop: 'Drag the area to keep.',
  none: '',
};

function initialAxes(): Data {
  return {mode: 'anchors', time_unit: 'us', voltage_unit: 'kV', voltage_side: 'high_voltage', divider_ratio: 1, divider_ratio_source: '',
    anchor_uncertainty_px: 1, x_scale: 'linear', y_scale: 'linear', x_anchors: [{px: null, value: null}, {px: null, value: null}],
    y_anchors: [{px: null, value: null}, {px: null, value: null}], grid: {divisions_x: 10, divisions_y: 8, time_at_left: 0, value_at_center: 0}};
}

function load(sid: string): Data | null {
  try {
    const raw = localStorage.getItem(`impulsetwin-digitizer-${sid}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function Digitizer({sid, view, onView, onError}: {sid: string; view: Data; onView: (v: Data) => void; onError: (m: string) => void}) {
  const upload = view.upload;
  const existing = view.digitization?.source === 'image' && view.digitization.upload_id === upload.id ? view.digitization : null;
  const saved = useMemo(() => load(sid), [sid]);
  const [geometry, setGeometry] = useState<Data>(existing?.transform ? fromRecord(existing) : saved?.geometry || {mode: 'rotate', rotate_deg: 0, crop: null, corners: []});
  const [applied, setApplied] = useState<Data | null>(null); // transforms used for the current working preview
  const [preview, setPreview] = useState<Data | null>(null);
  const [original, setOriginal] = useState<Data | null>(null);
  const [tool, setTool] = useState<Tool>('none');
  const [axes, setAxes] = useState<Data>(existing?.axes || saved?.axes || initialAxes());
  const [plotBox, setPlotBox] = useState<Rect | null>(existing?.plot_box || saved?.plotBox || null);
  const [seed, setSeed] = useState<[number, number] | null>(existing?.seed || saved?.seed || null);
  const [edits, setEdits] = useState<Data>(existing?.edits || saved?.edits || {erase: [], add: []});
  const [tolerance, setTolerance] = useState<number>(existing?.tolerance || saved?.tolerance || 28);
  const [meta, setMeta] = useState<Data>({baseline_kv: existing?.baseline_kv ?? 0, onset_us: existing?.onset_us ?? 0,
    expected_polarity: existing?.expected_polarity || upload.expected_polarity || 'positive'});
  const [drag, setDrag] = useState<Rect | null>(null);
  const [busy, setBusy] = useState('');
  const svg = useRef<SVGSVGElement>(null);
  const start = useRef<[number, number] | null>(null);

  // Remember the draft so a reload keeps the user's work (convenience only).
  useEffect(() => {
    try {
      localStorage.setItem(`impulsetwin-digitizer-${sid}`, JSON.stringify({geometry, axes, plotBox, seed, edits, tolerance}));
    } catch {
      /* storage unavailable */
    }
  }, [sid, geometry, axes, plotBox, seed, edits, tolerance]);

  async function fetchPreview(transforms: Data) {
    return post(`/api/diagnostics/${sid}/image/preview`, transforms);
  }
  // Oriented original (no transforms) for straightening and corner picking.
  useEffect(() => {
    let alive = true;
    setBusy('Loading image');
    fetchPreview({})
      .then(p => {
        if (!alive) return;
        setOriginal(p);
        if (existing?.transform) applyGeometry(fromRecord(existing), true);
      })
      .catch(e => alive && onError(e.message))
      .finally(() => alive && setBusy(''));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upload.id]);

  function transformsOf(g: Data): Data {
    if (g.mode === 'corners') return g.corners?.length === 4 ? {corners: g.corners} : {};
    return {rotate_deg: Number(g.rotate_deg) || 0, ...(g.crop ? {crop: g.crop} : {})};
  }

  async function applyGeometry(g = geometry, keepPicks = false) {
    const transforms = transformsOf(g);
    setBusy('Applying geometry');
    try {
      const p = await fetchPreview(transforms);
      setPreview(p);
      setApplied(transforms);
      setTool('plot');
      if (!keepPicks && JSON.stringify(transforms) !== JSON.stringify(applied || {})) {
        // Picks belong to the previous working image; start them again.
        setPlotBox(p.suggestions?.plot_frame_px || null);
        setSeed(null);
        setEdits({erase: [], add: []});
        setAxes((a: Data) => ({...a, x_anchors: [{px: null, value: a.x_anchors?.[0]?.value ?? null}, {px: null, value: a.x_anchors?.[1]?.value ?? null}],
          y_anchors: [{px: null, value: a.y_anchors?.[0]?.value ?? null}, {px: null, value: a.y_anchors?.[1]?.value ?? null}]}));
      }
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const stageImage = preview || original;
  const size: [number, number] = preview ? preview.transform.working_size : original ? original.transform.working_size : [1, 1];
  const onOriginal = !preview;

  function point(e: ReactPointerEvent): [number, number] | null {
    return svg.current ? toImagePoint(svg.current, e.clientX, e.clientY) : null;
  }
  function down(e: ReactPointerEvent) {
    const p = point(e);
    if (!p) return;
    start.current = p;
    if (tool === 'plot' || tool === 'erase' || tool === 'crop') {
      (e.target as Element).setPointerCapture?.(e.pointerId);
      setDrag([p[0], p[1], p[0], p[1]]);
    }
  }
  function move(e: ReactPointerEvent) {
    if (!drag || !start.current) return;
    const p = point(e);
    if (p) setDrag([start.current[0], start.current[1], p[0], p[1]]);
  }
  function up(e: ReactPointerEvent) {
    const p = point(e);
    const s = start.current;
    start.current = null;
    if (!p || !s) return;
    const rect: Rect = [Math.min(s[0], p[0]), Math.min(s[1], p[1]), Math.max(s[0], p[0]), Math.max(s[1], p[1])];
    setDrag(null);
    if (tool === 'plot') return rect[2] - rect[0] > 20 && rect[3] - rect[1] > 20 && setPlotBox(rect.map(Math.round) as Rect);
    if (tool === 'erase') return rect[2] - rect[0] > 2 && setEdits((x: Data) => ({...x, erase: [...x.erase, rect]}));
    if (tool === 'crop') {
      const offset = geometry.crop ? [geometry.crop[0], geometry.crop[1]] : [0, 0];
      return setGeometry((g: Data) => ({...g, crop: [rect[0] + offset[0], rect[1] + offset[1], rect[2] + offset[0], rect[3] + offset[1]].map(Math.round)}));
    }
    if (tool === 'corner' && onOriginal) {
      // Corners are recorded in the oriented image's own pixels (the view may be downscaled).
      const q = applyMatrix(original?.transform?.working_to_original, p);
      return setGeometry((g: Data) => ({...g, corners: [...(g.corners || []), q].slice(-4)}));
    }
    if (tool === 'trace') return setSeed([Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]);
    if (tool === 'add') return setEdits((x: Data) => ({...x, add: [...x.add, [p[0], p[1]]]}));
    if (tool === 'x0' || tool === 'x1' || tool === 'y0' || tool === 'y1') {
      const key = tool[0] === 'x' ? 'x_anchors' : 'y_anchors';
      const index = Number(tool[1]);
      const px = tool[0] === 'x' ? p[0] : p[1];
      setAxes((a: Data) => {
        const list = [...a[key]];
        list[index] = {...list[index], px: Math.round(px * 10) / 10};
        return {...a, [key]: list};
      });
      setTool(tool === 'x0' ? 'x1' : tool === 'y0' ? 'y1' : 'none');
    }
  }

  function demoHints() {
    const h = upload.demo_hints;
    const r1 = (v: number) => Math.round(v * 10) / 10;
    setPlotBox(h.plot_box.map((v: number) => Math.round(v)) as Rect);
    setSeed([r1(h.seed_px[0]), r1(h.seed_px[1])]);
    setAxes({...initialAxes(), ...h.axes,
      x_anchors: h.axes.x_anchors.map((a: Data) => ({...a, px: r1(a.px)})), y_anchors: h.axes.y_anchors.map((a: Data) => ({...a, px: r1(a.px)}))});
    setMeta(m => ({...m, expected_polarity: 'positive'}));
  }

  const gaps = calibrationGaps(axes);
  if (!plotBox) gaps.push('plot area');
  if (!seed) gaps.push('a point on the waveform');

  async function extract() {
    if (!applied) return;
    setBusy('Extracting trace');
    try {
      const body = {transforms: applied, plot_box: plotBox, seed, tolerance, edits, axes: cleanAxes(axes), ...meta};
      onView(await post(`/api/diagnostics/${sid}/digitize`, body));
      setTool('none');
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy('');
    }
  }

  const overlay: number[][] = existing && preview && JSON.stringify(transformsOf(fromRecord(existing))) === JSON.stringify(applied) ? existing.overlay.working_px : [];
  const suggestions = (preview || original)?.suggestions;
  const ocr: Data[] = suggestions?.ocr?.numbers || [];
  const anchorsShown = axes.mode === 'per_division' ? perDivisionAnchors(axes.grid || {}) : null;
  const toolButtons: [Tool, string, typeof Square][] = onOriginal
    ? geometry.mode === 'corners'
      ? [['corner', 'Corners', Crosshair]]
      : []
    : [
        ['plot', 'Plot area', Square],
        ['x0', 'Time anchors', MousePointerClick],
        ['y0', 'Voltage anchors', MousePointerClick],
        ['trace', 'Pick trace', ScanLine],
        ['erase', 'Erase', Eraser],
        ['add', 'Add point', Plus],
        ...(geometry.mode === 'rotate' ? ([['crop', 'Crop', Crop]] as [Tool, string, typeof Square][]) : []),
      ];

  return (
    <div className="digitizer">
      <div className="digitizer-steps" role="group" aria-label="Digitizing steps">
        <span className={preview ? 'done' : 'on'}>A · Straighten or correct perspective</span>
        <span className={preview && !gaps.length ? 'done' : preview ? 'on' : ''}>B · Plot area, axes and trace</span>
        <span className={existing ? 'done' : ''}>C · Extract and check the overlay</span>
      </div>
      <div className="digitizer-geometry">
        <div className="segmented segmented-small geometry-mode" role="radiogroup" aria-label="Geometry correction">
          {[
            ['rotate', 'Straighten and crop'],
            ['corners', 'Four plot corners (perspective)'],
          ].map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={geometry.mode === id} className={geometry.mode === id ? 'active' : ''}
              onClick={() => { setGeometry((g: Data) => ({...g, mode: id})); setPreview(null); setTool(id === 'corners' ? 'corner' : 'none'); }}>
              {label}
            </button>
          ))}
        </div>
        {geometry.mode === 'rotate' ? (
          <label className="field rotate-field">
            <span>Rotation (clockwise, degrees)</span>
            <span className="rotate-row">
              <input type="range" min={-10} max={10} step={0.05} value={geometry.rotate_deg} aria-label="Rotation in degrees"
                onChange={e => setGeometry((g: Data) => ({...g, rotate_deg: Number(e.target.value)}))} />
              <input type="number" step={0.05} min={-45} max={45} value={geometry.rotate_deg} aria-label="Rotation value"
                onChange={e => setGeometry((g: Data) => ({...g, rotate_deg: Number(e.target.value)}))} />
            </span>
            {suggestions?.deskew && (
              <small>
                Suggested from straight lines: {fmt(suggestions.deskew.degrees_clockwise, 2)}° ({suggestions.deskew.confidence}).{' '}
                <button type="button" className="text-button" onClick={() => setGeometry((g: Data) => ({...g, rotate_deg: suggestions.deskew.degrees_clockwise}))}>Use it</button>
              </small>
            )}
            {geometry.crop && <small>Crop kept: {geometry.crop.join(', ')} px <button type="button" className="text-button" onClick={() => setGeometry((g: Data) => ({...g, crop: null}))}>Remove crop</button></small>}
          </label>
        ) : (
          <p className="field-help">
            {(geometry.corners || []).length}/4 corners placed{' '}
            {(geometry.corners || []).length > 0 && <button type="button" className="text-button" onClick={() => setGeometry((g: Data) => ({...g, corners: []}))}>Start again</button>}
            {preview && <button type="button" className="text-button" onClick={() => { setPreview(null); setTool('corner'); }}>Show the original to re-place corners</button>}
          </p>
        )}
        <button type="button" className="button small primary" disabled={!!busy || (geometry.mode === 'corners' && (geometry.corners || []).length !== 4)} onClick={() => applyGeometry()}>
          {busy === 'Applying geometry' ? <LoaderCircle size={14} className="spin" aria-hidden /> : <RotateCw size={14} aria-hidden />} Apply geometry
        </button>
      </div>

      {toolButtons.length > 0 && (
        <div className="digitizer-tools" role="toolbar" aria-label="Image tools">
          {toolButtons.map(([id, label, Icon]) => (
            <button key={id} type="button" className={`button small ${tool === id || (id === 'x0' && tool === 'x1') || (id === 'y0' && tool === 'y1') ? 'primary' : ''}`} aria-pressed={tool === id}
              onClick={() => setTool(tool === id ? 'none' : id)}>
              <Icon size={14} aria-hidden /> {label}
            </button>
          ))}
          {upload.demo_hints && !onOriginal && (
            <button type="button" className="button small" onClick={demoHints} title={upload.demo_hints.note}>
              <Wand2 size={14} aria-hidden /> Fill in the demonstration&apos;s known positions
            </button>
          )}
        </div>
      )}
      {tool !== 'none' && TOOL_HELP[tool] && <p className="digitizer-help" role="status"><Move size={13} aria-hidden /> {TOOL_HELP[tool]}</p>}

      <div className={`digitizer-stage ${tool !== 'none' ? 'is-picking' : ''}`}>
        {stageImage ? (
          <svg ref={svg} viewBox={`0 0 ${size[0]} ${size[1]}`} role="img"
            aria-label={onOriginal ? 'Uploaded image as recorded' : 'Working image after the recorded geometry steps, with your picks and the extracted trace'}
            onPointerDown={down} onPointerMove={move} onPointerUp={up}>
            <image href={`data:image/png;base64,${stageImage.png_base64}`} x={0} y={0} width={size[0]} height={size[1]} preserveAspectRatio="none" />
            {onOriginal && (geometry.corners || []).map((c: [number, number], i: number) => {
              const v = applyMatrix(inverseMatrix(original?.transform?.working_to_original), c);
              return (
                <g key={i} className="pick-corner">
                  <circle cx={v[0]} cy={v[1]} r={Math.max(4, size[0] / 220)} />
                  <text x={v[0] + 8} y={v[1] - 8}>{['Top left', 'Top right', 'Bottom right', 'Bottom left'][i]}</text>
                </g>
              );
            })}
            {!onOriginal && plotBox && <rect className="pick-plot" x={plotBox[0]} y={plotBox[1]} width={plotBox[2] - plotBox[0]} height={plotBox[3] - plotBox[1]} />}
            {!onOriginal && axes.mode === 'anchors' && axes.x_anchors.map((a: Data, i: number) => Number.isFinite(a.px) && (
              <g key={`x${i}`} className="pick-anchor"><line x1={a.px} x2={a.px} y1={0} y2={size[1]} /><text x={a.px + 4} y={size[1] - 8}>t{i + 1}{a.value != null ? ` = ${a.value}` : ''}</text></g>
            ))}
            {!onOriginal && axes.mode === 'anchors' && axes.y_anchors.map((a: Data, i: number) => Number.isFinite(a.px) && (
              <g key={`y${i}`} className="pick-anchor"><line x1={0} x2={size[0]} y1={a.px} y2={a.px} /><text x={6} y={a.px - 4}>v{i + 1}{a.value != null ? ` = ${a.value}` : ''}</text></g>
            ))}
            {!onOriginal && anchorsShown && (
              <g className="pick-anchor">
                {anchorsShown.x.map(([px], i) => <line key={`gx${i}`} x1={px} x2={px} y1={0} y2={size[1]} />)}
                {anchorsShown.y.map(([px], i) => <line key={`gy${i}`} x1={0} x2={size[0]} y1={px} y2={px} />)}
              </g>
            )}
            {!onOriginal && edits.erase.map((r: Rect, i: number) => <rect key={`e${i}`} className="pick-erase" x={r[0]} y={r[1]} width={r[2] - r[0]} height={r[3] - r[1]} />)}
            {!onOriginal && overlay.length > 1 && <polyline className="trace-overlay" points={overlay.map(p => p.join(',')).join(' ')} />}
            {!onOriginal && edits.add.map((p: number[], i: number) => <circle key={`a${i}`} className="pick-manual" cx={p[0]} cy={p[1]} r={Math.max(3, size[0] / 400)} />)}
            {!onOriginal && seed && <circle className="pick-seed" cx={seed[0]} cy={seed[1]} r={Math.max(5, size[0] / 200)} />}
            {drag && <rect className="pick-drag" x={drag[0]} y={drag[1]} width={drag[2] - drag[0]} height={drag[3] - drag[1]} />}
          </svg>
        ) : (
          <p className="digitizer-loading">{busy ? <><LoaderCircle size={16} className="spin" aria-hidden /> {busy}…</> : 'Image not loaded.'}</p>
        )}
      </div>
      {overlay.length > 0 && <p className="field-help">Red line: the {overlay.length} extracted samples drawn on the working image. Check that it follows the curve everywhere before comparing.</p>}

      {!onOriginal && (
        <div className="digitizer-form">
          <fieldset>
            <legend>Axis calibration</legend>
            <div className="segmented segmented-small" role="radiogroup" aria-label="Calibration method">
              {[
                ['anchors', 'Two anchors per axis'],
                ['per_division', 'Oscilloscope divisions'],
              ].map(([id, label]) => (
                <button key={id} type="button" role="radio" aria-checked={axes.mode === id} className={axes.mode === id ? 'active' : ''} onClick={() => setAxes((a: Data) => ({...a, mode: id}))}>
                  {label}
                </button>
              ))}
            </div>
            {axes.mode === 'anchors' ? (
              <div className="anchor-grid">
                {(['x_anchors', 'y_anchors'] as const).map(key =>
                  axes[key].map((a: Data, i: number) => (
                    <div key={`${key}${i}`} className="anchor-row">
                      <span className="anchor-name">{key === 'x_anchors' ? `Time anchor ${i + 1}` : `Voltage anchor ${i + 1}`}</span>
                      <label>
                        <span>{key === 'x_anchors' ? 'x' : 'y'} pixel</span>
                        <input type="number" step="any" value={a.px ?? ''} onChange={e => setAxes((s: Data) => setAnchor(s, key, i, 'px', e.target.value))} />
                      </label>
                      <label>
                        <span>Axis value</span>
                        <input type="number" step="any" value={a.value ?? ''} onChange={e => setAxes((s: Data) => setAnchor(s, key, i, 'value', e.target.value))} />
                      </label>
                      <button type="button" className="button small" onClick={() => setTool((key === 'x_anchors' ? `x${i}` : `y${i}`) as Tool)}>
                        <Crosshair size={13} aria-hidden /> Place
                      </button>
                    </div>
                  )),
                )}
              </div>
            ) : (
              <div className="grid-fields">
                {[
                  ['left_px', 'Graticule left (px)'], ['right_px', 'Graticule right (px)'], ['top_px', 'Graticule top (px)'], ['bottom_px', 'Graticule bottom (px)'],
                  ['divisions_x', 'Horizontal divisions'], ['divisions_y', 'Vertical divisions'], ['time_per_div', 'Time per division'], ['time_at_left', 'Time at left edge'],
                  ['volts_per_div', 'Voltage per division'], ['value_at_center', 'Voltage at centre line'],
                ].map(([k, label]) => (
                  <label key={k} className="field">
                    <span>{label}</span>
                    <input type="number" step="any" value={axes.grid?.[k] ?? ''} onChange={e => setAxes((s: Data) => ({...s, grid: {...s.grid, [k]: e.target.value === '' ? null : Number(e.target.value)}}))} />
                  </label>
                ))}
                {plotBox && (
                  <button type="button" className="button small" onClick={() => setAxes((s: Data) => ({...s, grid: {...s.grid, left_px: plotBox[0], top_px: plotBox[1], right_px: plotBox[2], bottom_px: plotBox[3]}}))}>
                    Use the plot area as the graticule
                  </button>
                )}
              </div>
            )}
            {ocr.length > 0 && axes.mode === 'anchors' && (
              <div className="ocr-chips">
                <span className="field-help">Numbers read locally from the image (suggestions — check each one):</span>
                <div>
                  {ocr.slice(0, 24).map((n: Data, i: number) => {
                    const cx = (n.box_px[0] + n.box_px[2]) / 2, cy = (n.box_px[1] + n.box_px[3]) / 2;
                    return (
                      <button key={i} type="button" className="chip" title={`at ${Math.round(cx)}, ${Math.round(cy)} px`}
                        onClick={() => setAxes((s: Data) => fillFromOcr(s, n.value, cx, cy))}>
                        {n.text}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {suggestions?.ocr && !suggestions.ocr.available && <p className="field-help">{suggestions.ocr.message}</p>}
            {suggestions?.possibly_logarithmic_time_axis && <Notice tone="amber">The vertical grid lines are unevenly spaced. If the time axis is logarithmic, it cannot be digitized here.</Notice>}
            <div className="grid-fields">
              <label className="field"><span>Time unit on the axis</span>
                <select value={axes.time_unit} onChange={e => setAxes((s: Data) => ({...s, time_unit: e.target.value}))}>
                  <option value="ns">ns</option><option value="us">µs</option><option value="ms">ms</option><option value="s">s</option>
                </select>
              </label>
              <label className="field"><span>Voltage unit on the axis</span>
                <select value={axes.voltage_unit} onChange={e => setAxes((s: Data) => ({...s, voltage_unit: e.target.value}))}>
                  <option>V</option><option>kV</option><option>MV</option>
                </select>
              </label>
              <label className="field"><span>Time axis scale</span>
                <select value={axes.x_scale} onChange={e => setAxes((s: Data) => ({...s, x_scale: e.target.value}))}><option value="linear">Linear</option><option value="log">Logarithmic</option></select>
              </label>
              <label className="field"><span>Voltage axis scale</span>
                <select value={axes.y_scale} onChange={e => setAxes((s: Data) => ({...s, y_scale: e.target.value}))}><option value="linear">Linear</option><option value="log">Logarithmic</option></select>
              </label>
            </div>
            <div className="purpose">
              <span className="field-label">The voltage axis shows</span>
              <label className="radio"><input type="radio" checked={axes.voltage_side === 'high_voltage'} onChange={() => setAxes((s: Data) => ({...s, voltage_side: 'high_voltage', divider_ratio: 1}))} />
                <span>High voltage at the test object<small>The divider ratio is already applied; it is not applied again.</small></span></label>
              <label className="radio"><input type="radio" checked={axes.voltage_side === 'instrument'} onChange={() => setAxes((s: Data) => ({...s, voltage_side: 'instrument'}))} />
                <span>The instrument signal (divider output)<small>The divider ratio below converts it to high voltage.</small></span></label>
            </div>
            {axes.voltage_side === 'instrument' && (
              <div className="two-fields">
                <label className="field"><span>Divider ratio</span><input type="number" step="any" min={0} value={axes.divider_ratio} onChange={e => setAxes((s: Data) => ({...s, divider_ratio: Number(e.target.value)}))} /></label>
                <label className="field"><span>Source of the ratio</span><input value={axes.divider_ratio_source} placeholder="Divider certificate, date" onChange={e => setAxes((s: Data) => ({...s, divider_ratio_source: e.target.value}))} /></label>
              </div>
            )}
          </fieldset>
          <fieldset>
            <legend>Recording details</legend>
            <div className="grid-fields">
              <label className="field"><span>Baseline (kV, after scaling)</span><input type="number" step="any" value={meta.baseline_kv} onChange={e => setMeta(m => ({...m, baseline_kv: Number(e.target.value)}))} /></label>
              <label className="field"><span>Impulse onset (µs)</span><input type="number" step="any" value={meta.onset_us} onChange={e => setMeta(m => ({...m, onset_us: Number(e.target.value)}))} /><small>Physical start of the impulse on this record.</small></label>
              <label className="field"><span>Expected polarity</span>
                <select value={meta.expected_polarity} onChange={e => setMeta(m => ({...m, expected_polarity: e.target.value}))}>
                  <option value="positive">Positive</option><option value="negative">Negative</option><option value="unknown">Not known</option>
                </select>
              </label>
              <label className="field"><span>Anchor placement uncertainty (px)</span><input type="number" step={0.5} min={0} max={20} value={axes.anchor_uncertainty_px} onChange={e => setAxes((s: Data) => ({...s, anchor_uncertainty_px: Number(e.target.value)}))} /></label>
              <label className="field"><span>Colour tolerance (ΔE {tolerance})</span><input type="range" min={5} max={80} value={tolerance} onChange={e => setTolerance(Number(e.target.value))} aria-label="Colour tolerance" /></label>
              <div className="field">
                <span>Picks</span>
                <small>Plot area {plotBox ? plotBox.join(', ') : 'not set'} · trace point {seed ? seed.join(', ') : 'not set'} · {edits.erase.length} erased area{edits.erase.length === 1 ? '' : 's'} · {edits.add.length} manual point{edits.add.length === 1 ? '' : 's'}
                  {(edits.erase.length > 0 || edits.add.length > 0) && <> · <button type="button" className="text-button" onClick={() => setEdits({erase: [], add: []})}>Clear edits</button></>}
                </small>
              </div>
            </div>
          </fieldset>
          {gaps.length > 0 && <p className="field-help">Still needed: {gaps.join('; ')}.</p>}
          <button type="button" className="button primary" disabled={!!busy || gaps.length > 0} onClick={extract}>
            {busy === 'Extracting trace' ? <LoaderCircle size={15} className="spin" aria-hidden /> : <ScanLine size={15} aria-hidden />} Extract trace
          </button>
        </div>
      )}
      {existing && <DigitizationQuality record={existing} />}
    </div>
  );
}

function setAnchor(s: Data, key: 'x_anchors' | 'y_anchors', i: number, field: 'px' | 'value', raw: string): Data {
  const list = [...s[key]];
  list[i] = {...list[i], [field]: raw === '' ? null : Number(raw)};
  return {...s, [key]: list};
}

function fillFromOcr(s: Data, value: number, cx: number, cy: number): Data {
  // Fill the first incomplete anchor: time anchors use the label's x, voltage anchors its y.
  for (const key of ['x_anchors', 'y_anchors'] as const) {
    const i = s[key].findIndex((a: Data) => a.px == null || a.value == null);
    if (i >= 0) {
      const list = [...s[key]];
      list[i] = {px: Math.round((key === 'x_anchors' ? cx : cy) * 10) / 10, value};
      return {...s, [key]: list};
    }
  }
  return s;
}

function cleanAxes(a: Data): Data {
  const out: Data = {...a, divider_ratio: a.voltage_side === 'high_voltage' ? 1 : Number(a.divider_ratio)};
  if (a.mode === 'per_division') {
    delete out.x_anchors;
    delete out.y_anchors;
  }
  return out;
}

function applyMatrix(m: number[][] | undefined, p: [number, number]): [number, number] {
  if (!m) return p;
  const w = m[2][0] * p[0] + m[2][1] * p[1] + m[2][2];
  return [(m[0][0] * p[0] + m[0][1] * p[1] + m[0][2]) / w, (m[1][0] * p[0] + m[1][1] * p[1] + m[1][2]) / w];
}

function inverseMatrix(m: number[][] | undefined): number[][] | undefined {
  if (!m) return undefined;
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (!det) return undefined;
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det], [B / det, (a * i - c * g) / det, -(a * f - c * d) / det], [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}

function fromRecord(record: Data): Data {
  const steps: Data[] = record.transform?.steps || [];
  const corners = steps.find(s => s.step === 'perspective');
  if (corners) return {mode: 'corners', corners: corners.corners, rotate_deg: 0, crop: null};
  const rotate = steps.find(s => s.step === 'rotate');
  const crop = steps.find(s => s.step === 'crop');
  return {mode: 'rotate', rotate_deg: rotate?.degrees_clockwise || 0, crop: crop?.box || null, corners: []};
}

export function DigitizationQuality({record}: {record: Data}) {
  const q = record.quality || {};
  const spread = q.digitization_spread || {};
  const avail = q.metric_availability || {};
  const m = record.analysis?.metrics || record.analysis?.partial || {};
  return (
    <div className="quality-card">
      <div className="quality-head">
        <strong>{record.label || q.label || 'Uploaded samples'}</strong>
        <Badge tone={q.quantitative_comparison_allowed ? 'green' : 'amber'}>{q.quantitative_comparison_allowed ? 'Quantitative comparison allowed' : 'Visual comparison only'}</Badge>
      </div>
      <dl className="kv">
        {record.source === 'image' && (
          <>
            <div><dt>Scale</dt><dd>{fmt(q.calibration?.us_per_px, 4)} µs per pixel · {fmt(q.calibration?.kv_per_px, 3)} kV per pixel · anchors ±{fmt(q.calibration?.anchor_uncertainty_px, 1)} px</dd></div>
            <div><dt>Trace</dt><dd>{q.trace?.samples} samples ({q.trace?.manual} manual) · {fmt(100 * (q.trace?.column_coverage || 0), 0)}% of the followed span · {fmt(q.trace?.thickness_px, 1)} px thick</dd></div>
            <div><dt>Missing portions</dt><dd>{(q.missing_portions_us || []).length ? q.missing_portions_us.map((g: number[]) => `${fmt(g[0], 3)}–${fmt(g[1], 3)} µs`).join(', ') : 'None'}</dd></div>
            <div><dt>Digitization spread</dt><dd>{spread.available ? ['front_us', 'tail_us', 'crest_kv'].map(k => `${k === 'crest_kv' ? 'crest' : k === 'front_us' ? 'front' : 'tail'} ${fmt(spread.p05[k], 3)}–${fmt(spread.p95[k], 3)}`).join(' · ') : 'Not available for this trace'}</dd></div>
          </>
        )}
        {q.time_range_us && <div><dt>Time range</dt><dd>{fmt(q.time_range_us[0], 3)} to {fmt(q.time_range_us[1], 3)} µs</dd></div>}
        <div><dt>Metrics supported</dt><dd>Front {avail.front ? `yes (${fmt(m.front_us, 4)} µs)` : 'no'} · tail {avail.tail ? `yes (${fmt(m.tail_us, 4)} µs)` : 'no — insufficient capture'} · crest {avail.crest ? `yes (${fmt(m.crest_kv, 4)} kV)` : 'no'}</dd></div>
      </dl>
      {(q.flags || []).length > 0 && (
        <ul className="flag-list">
          {q.flags.map((f: Data, i: number) => <li key={i}><Badge tone="amber">{f.code.replaceAll('_', ' ')}</Badge> {f.message}</li>)}
        </ul>
      )}
      {(q.notes || []).length > 0 && <ul className="flag-list notes">{q.notes.map((f: Data, i: number) => <li key={i}>{f.message}</li>)}</ul>}
      <p className="field-help">{q.scope}</p>
    </div>
  );
}
