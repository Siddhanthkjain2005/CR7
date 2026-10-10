'use client';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Box, ChevronDown, ChevronUp, Layers3, Minus, Play, Plus, RotateCcw, RotateCw, Square} from 'lucide-react';
import type {GeneratorEngine, SceneView, AnchorMap} from './engine';
import GeneratorElevation from './elevation';
import {GeneratorModel, ohmText, valueColor} from '@/lib/generator-model';
import {fmt} from '@/lib/api';
import {useInView, useQuietMotion} from '@/lib/motion';

type Mode = '3d' | '2d';
type Status = 'idle' | 'loading' | 'ready' | 'unsupported' | 'failed' | 'lost';

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

function quality(): 'high' | 'low' {
  const cores = navigator.hardwareConcurrency || 4;
  const touch = matchMedia?.('(pointer: coarse)').matches;
  return cores >= 6 && !touch && (window.devicePixelRatio || 1) <= 2.5 ? 'high' : 'low';
}

const STATE_TEXT: Record<string, string> = {
  active: 'Active in this saved candidate',
  inactive: 'Not used by this candidate',
  shared: 'Active before and after',
  added: 'Newly active in the target plan',
  removed: 'Deactivated by the target plan',
};

export interface GeneratorViewProps {
  model: GeneratorModel | null;
  view?: SceneView;
  /** Illustrative output glow (0..1) and its caption, driven by the plotted waveform cursor. */
  pulse?: {fraction: number; label: string} | null;
  /** Changing this value plays the illustrative erection sequence once. */
  playKey?: number;
  height?: number | string;
  compact?: boolean;
  caption?: string;
  emptyText?: string;
}

export default function GeneratorView({model, view = 'overview', pulse = null, playKey = 0, height = 520, compact = false, caption, emptyText}: GeneratorViewProps) {
  const host = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engine = useRef<GeneratorEngine | null>(null);
  const [mode, setMode] = useState<Mode>('3d');
  const [status, setStatus] = useState<Status>('idle');
  const [anchors, setAnchors] = useState<AnchorMap>({});
  const [hover, setHover] = useState<{stage: number; x: number; y: number} | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [size, setSize] = useState({w: 0, h: 0});
  const narrow = size.w > 0 && size.w < 400;
  const quiet = useQuietMotion();
  const inView = useInView(host);
  const lastPlay = useRef(playKey);
  const modelRef = useRef(model);
  modelRef.current = model;

  useEffect(() => {
    try {
      if (localStorage.getItem('impulsetwin-scene-mode') === '2d') setMode('2d');
    } catch {
      /* storage unavailable */
    }
  }, []);
  const chooseMode = (m: Mode) => {
    setMode(m);
    try {
      localStorage.setItem('impulsetwin-scene-mode', m);
    } catch {
      /* ignore */
    }
  };

  // Create / destroy the WebGL engine (lazy-loaded chunk).
  useEffect(() => {
    if (mode !== '3d') return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!webglAvailable()) {
      setStatus('unsupported');
      return;
    }
    let cancelled = false;
    let instance: GeneratorEngine | null = null;
    let resize: ResizeObserver | null = null;
    setStatus('loading');
    import('./engine')
      .then(({GeneratorEngine}) => {
        if (cancelled) return;
        try {
          instance = new GeneratorEngine(canvas, {
            quality: quality(),
            onHover: (stage, x, y) => setHover(stage === null ? null : {stage, x, y}),
            onSelect: stage => setSelected(stage),
            onAnchors: a => setAnchors(a),
            onContextLost: () => setStatus('lost'),
            onSequence: p => setPlaying(p),
          });
        } catch {
          setStatus('failed');
          return;
        }
        engine.current = instance;
        instance.setQuiet(quiet);
        const rect = canvas.parentElement!.getBoundingClientRect();
        instance.resize(rect.width, rect.height);
        instance.setModel(modelRef.current);
        instance.setView(view, true);
        resize = new ResizeObserver(entries => {
          const r = entries[0].contentRect;
          instance?.resize(r.width, r.height);
          setSize({w: r.width, h: r.height});
        });
        resize.observe(canvas.parentElement!);
        setStatus('ready');
      })
      .catch(() => !cancelled && setStatus('failed'));
    return () => {
      cancelled = true;
      resize?.disconnect();
      instance?.dispose();
      engine.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, attempt]);

  useEffect(() => {
    engine.current?.setModel(model);
    setSelected(null);
  }, [model, status]);
  useEffect(() => {
    engine.current?.setView(view);
  }, [view, status]);
  useEffect(() => {
    engine.current?.setPulse(pulse ? pulse.fraction : null);
  }, [pulse, status]);
  useEffect(() => {
    engine.current?.setQuiet(quiet);
  }, [quiet, status]);
  useEffect(() => {
    engine.current?.setActive(inView);
  }, [inView, status]);
  useEffect(() => {
    if (playKey !== lastPlay.current && status === 'ready') {
      lastPlay.current = playKey;
      // Let the new model settle into place before the sequence starts.
      const t = setTimeout(() => engine.current?.play(), quiet ? 0 : 420);
      return () => clearTimeout(t);
    }
  }, [playKey, status, quiet]);

  const select = useCallback(
    (i: number | null) => {
      setSelected(i);
      engine.current?.focusStage(i);
    },
    [],
  );

  const onKey = (e: React.KeyboardEvent) => {
    const eng = engine.current;
    if (!eng || !model) return;
    const handled = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '_', '0', 'PageUp', 'PageDown', 'Escape'];
    if (!handled.includes(e.key)) return;
    e.preventDefault();
    if (e.key === 'ArrowLeft') eng.orbit(-0.18, 0);
    if (e.key === 'ArrowRight') eng.orbit(0.18, 0);
    if (e.key === 'ArrowUp') eng.orbit(0, -0.08);
    if (e.key === 'ArrowDown') eng.orbit(0, 0.08);
    if (e.key === '+' || e.key === '=') eng.zoom(0.88);
    if (e.key === '-' || e.key === '_') eng.zoom(1.14);
    if (e.key === '0' || e.key === 'Escape') {
      eng.reset();
      setSelected(null);
    }
    if (e.key === 'PageUp') select(Math.min(model.maxStages - 1, (selected ?? -1) + 1));
    if (e.key === 'PageDown') select(Math.max(0, (selected ?? model.maxStages) - 1));
  };

  const fallback = mode === '2d' || status === 'unsupported' || status === 'failed' || status === 'lost';
  const legend = useMemo(() => {
    if (!model) return [];
    const rows: {color: string; text: string}[] = [];
    if (model.mode === 'transition') {
      rows.push({color: '#9fb0bc', text: 'Kept on shared stages'}, {color: '#3fd29a', text: 'Added / newly active'}, {color: '#ff6f5c', text: 'Removed / deactivated'});
    } else {
      [model.front, model.tail].forEach(net =>
        [...new Set(net.parts.map(p => p.ohm))].forEach(ohm => {
          const text = `${ohmText(ohm)} ${net.role}`;
          if (!rows.some(r => r.text === text)) rows.push({color: valueColor(ohm, net), text});
        }),
      );
    }
    return rows;
  }, [model]);

  const stageInfo = (i: number) => {
    if (!model) return null;
    const state = model.stages[i];
    const lit = state === 'active' || state === 'shared' || state === 'added';
    return (
      <>
        <strong>
          Stage {i + 1} of {model.maxStages}
        </strong>
        <span>{STATE_TEXT[state] || state}</span>
        {lit && model.chargeKv !== null && <span>Charge {fmt(model.chargeKv, 2)} kV per stage (saved)</span>}
        {lit && (
          <span>
            Front {model.front.topology} · Tail {model.tail.topology}
          </span>
        )}
      </>
    );
  };

  const labelsShown = !compact && !narrow && status === 'ready' && !fallback && model;
  // Place labels in priority order and drop any that would collide or sit under the overlays.
  const placedLabels = useMemo(() => {
    if (!labelsShown || !model) return [];
    const outlineOnly = model.activeStages === 0;
    const texts: [keyof AnchorMap, string][] = outlineOnly
      ? [['stack', `Profile outline · ${model.maxStages} stages, nothing solved`]]
      : [
      ['stack', `${model.activeStages} of ${model.maxStages} stages active`],
      ['front', `Front bank · ${model.front.topology}`],
      ['tail', `Tail bank · ${model.tail.topology}`],
      ['output', 'Lead to divider and test object'],
      ['gap', 'Sphere gap · illustrative'],
      ['ghost', model.mode === 'transition' ? '' : 'Unused stages, dimmed'],
        ];
    const boxes: {x0: number; x1: number; y0: number; y1: number}[] = [];
    const out: {key: string; text: string; x: number; y: number; left: boolean}[] = [];
    const fits = (box: {x0: number; x1: number; y0: number; y1: number}) =>
      !(box.y0 < 44 || (size.h && box.y1 > size.h - 58) || box.x0 < 4 || (size.w && box.x1 > size.w - 46)) && !boxes.some(b => b.x0 < box.x1 && box.x0 < b.x1 && b.y0 < box.y1 && box.y0 < b.y1);
    for (const [key, text] of texts) {
      const a = anchors[key];
      if (!a?.visible || !text) continue;
      const w = text.length * 6.6 + 28;
      const prefersLeft = key === 'stack' || key === 'front' || key === 'ghost';
      // Try the preferred side first, then the other side; drop the label if neither fits.
      for (const left of prefersLeft ? [true, false] : [false, true]) {
        const box = {x0: left ? a.x - w : a.x - 4, x1: left ? a.x + 4 : a.x + w, y0: a.y - 12, y1: a.y + 12};
        if (!fits(box)) continue;
        boxes.push(box);
        out.push({key, text, x: a.x, y: a.y, left});
        break;
      }
    }
    return out;
  }, [labelsShown, model, anchors, size]);
  return (
    <div className={`scene ${compact ? 'scene-compact' : ''}`} style={{height}} ref={host}>
      <div className="scene-head">
        <span className="kind kind-conceptual">Conceptual schematic</span>
        {caption && <span className="scene-caption">{caption}</span>}
      </div>
      {!model ? (
        <div className="scene-empty">
          <Layers3 size={30} aria-hidden />
          <p>{emptyText || 'The stack appears after a saved recommendation is loaded.'}</p>
        </div>
      ) : fallback ? (
        <div className="scene-fallback">
          {status === 'lost' && <p className="scene-alert">The 3D view lost its graphics context. The 2D elevation shows the same saved information.</p>}
          {(status === 'unsupported' || status === 'failed') && mode === '3d' && <p className="scene-alert">3D graphics are unavailable in this browser. Showing the 2D elevation with the same saved information.</p>}
          <GeneratorElevation model={model} selected={selected} onSelect={i => setSelected(i)} pulse={pulse?.fraction} />
        </div>
      ) : null}
      {mode === '3d' && status !== 'unsupported' && status !== 'failed' && status !== 'lost' && (
        <div className="scene-canvas" hidden={!model} tabIndex={model ? 0 : -1} onKeyDown={onKey} role="group" aria-label="Conceptual 3D stack. Arrow keys rotate, plus and minus zoom, Page Up and Page Down select a stage, 0 resets the view." aria-describedby="scene-help">
          <canvas ref={canvasRef} aria-hidden />
          {status === 'loading' && <div className="scene-loading">Preparing 3D view…</div>}
        </div>
      )}
      <p id="scene-help" className="sr-only">
        Drag to rotate, scroll while focused or pinch to zoom. The same stage information is available in the stage list.
      </p>
      {placedLabels.map(l => (
        <span key={l.key} className={`scene-label scene-label-${l.key} ${l.left ? 'scene-label-left' : ''}`} style={{transform: `translate(${Math.round(l.x)}px, ${Math.round(l.y)}px)`}}>
          <i aria-hidden />
          <b>{l.text}</b>
        </span>
      ))}
      {hover && !fallback && model && (
        <div className="scene-tip" style={{transform: `translate(${Math.round(hover.x + 14)}px, ${Math.round(hover.y + 10)}px)`}} role="status">
          {stageInfo(hover.stage)}
        </div>
      )}
      {model && (
        <div className="scene-controls" aria-label="View controls">
          {mode === '3d' && status === 'ready' && (
            <>
              <button type="button" onClick={() => engine.current?.orbit(-0.35, 0)} aria-label="Rotate left" title="Rotate left">
                <RotateCcw size={15} />
              </button>
              <button type="button" onClick={() => engine.current?.orbit(0.35, 0)} aria-label="Rotate right" title="Rotate right">
                <RotateCw size={15} />
              </button>
              <button type="button" onClick={() => engine.current?.zoom(0.82)} aria-label="Zoom in" title="Zoom in">
                <Plus size={15} />
              </button>
              <button type="button" onClick={() => engine.current?.zoom(1.2)} aria-label="Zoom out" title="Zoom out">
                <Minus size={15} />
              </button>
              <button type="button" onClick={() => (engine.current?.reset(), setSelected(null))} aria-label="Reset view" title="Reset view">
                <Square size={13} />
              </button>
              <button type="button" className="scene-play" hidden={model.activeStages === 0} onClick={() => engine.current?.play()} disabled={playing} aria-label="Play illustrative erection sequence" title="Illustrative erection sequence (not spark-gap physics)">
                <Play size={14} /> <span>Illustrate</span>
              </button>
            </>
          )}
          {status === 'lost' && (
            <button type="button" onClick={() => (setStatus('idle'), setAttempt(a => a + 1))}>
              Restart 3D
            </button>
          )}
          <button type="button" className="scene-mode" onClick={() => chooseMode(mode === '3d' ? '2d' : '3d')} aria-pressed={mode === '2d'} title={mode === '3d' ? 'Show the 2D elevation' : 'Show the 3D view'}>
            <Box size={14} aria-hidden /> {mode === '3d' ? '2D' : '3D'}
          </button>
        </div>
      )}
      {model && !compact && !fallback && (
        <div className="scene-stages" role="group" aria-label="Stages">
          <button type="button" onClick={() => select(Math.min(model.maxStages - 1, (selected ?? -1) + 1))} aria-label="Select the next stage up" className="scene-step">
            <ChevronUp size={13} />
          </button>
          <div className="scene-stage-list">
            {model.stages
              .map((state, i) => ({state, i}))
              .reverse()
              .map(({state, i}) => (
                <button
                  type="button"
                  key={i}
                  className={`stage-pip stage-pip-${state} ${selected === i ? 'selected' : ''}`}
                  aria-pressed={selected === i}
                  aria-label={`Stage ${i + 1}: ${STATE_TEXT[state] || state}`}
                  onClick={() => select(selected === i ? null : i)}
                >
                  {i + 1}
                </button>
              ))}
          </div>
          <button type="button" onClick={() => select(Math.max(0, (selected ?? model.maxStages) - 1))} aria-label="Select the next stage down" className="scene-step">
            <ChevronDown size={13} />
          </button>
        </div>
      )}
      {model && selected !== null && (
        <div className="scene-card" role="status">
          {stageInfo(selected)}
          <button type="button" className="scene-card-close" onClick={() => select(null)} aria-label="Clear stage selection">
            ×
          </button>
        </div>
      )}
      {model && pulse && (
        <div className="scene-pulse" role="status">
          <span className="kind kind-conceptual">Illustrative</span> {pulse.label}
        </div>
      )}
      {model && !compact && legend.length > 0 && (
        <ul className="scene-legend" aria-label="Resistor colour key">
          {legend.map(row => (
            <li key={row.text}>
              <i style={{background: row.color}} aria-hidden />
              {row.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
