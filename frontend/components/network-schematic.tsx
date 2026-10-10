'use client';
import {NetworkModel, ResistorTree, ohmText, valueColor} from '@/lib/generator-model';

/**
 * IEC-style schematic of one stage's counted resistor network, drawn from the
 * backend topology text only when that text reproduces the saved equivalent
 * resistance and per-stage counts. Otherwise the counted parts are listed
 * without a wiring claim.
 */
const R_W = 46, R_H = 14, CELL_W = 86, CELL_H = 40, GAP = 6, RAIL = 14;

type Box = {w: number; h: number};
function size(t: ResistorTree): Box {
  if (t.kind === 'R') return {w: CELL_W, h: CELL_H};
  const s = t.children.map(size);
  if (t.kind === 'series') return {w: s.reduce((a, b) => a + b.w, 0), h: Math.max(...s.map(b => b.h))};
  return {w: Math.max(...s.map(b => b.w)) + RAIL * 2, h: s.reduce((a, b) => a + b.h, 0) + GAP * (s.length - 1)};
}

function draw(t: ResistorTree, x: number, y: number, net: NetworkModel, out: React.ReactNode[], key: string) {
  const b = size(t);
  const mid = y + b.h / 2;
  if (t.kind === 'R') {
    const cx = x + b.w / 2;
    out.push(
      <g key={key}>
        <line x1={x} x2={cx - R_W / 2} y1={mid} y2={mid} className="sch-wire" />
        <line x1={cx + R_W / 2} x2={x + b.w} y1={mid} y2={mid} className="sch-wire" />
        <rect x={cx - R_W / 2} y={mid - R_H / 2} width={R_W} height={R_H} rx={2} className="sch-r" />
        <rect x={cx - R_W / 2 + 3} y={mid - R_H / 2 + 3} width={6} height={R_H - 6} rx={1} fill={valueColor(t.ohm, net)} />
        <text x={cx + 4} y={mid - R_H / 2 - 5} textAnchor="middle" className="sch-label">
          {ohmText(t.ohm)}
        </text>
      </g>,
    );
    return;
  }
  if (t.kind === 'series') {
    let cx = x;
    t.children.forEach((c, i) => {
      const cb = size(c);
      // Children shorter than the series row are centred and joined with wires.
      draw(c, cx, y + (b.h - cb.h) / 2, net, out, `${key}s${i}`);
      cx += cb.w;
    });
    return;
  }
  const left = x + RAIL / 2, right = x + b.w - RAIL / 2;
  let cy = y;
  const mids: number[] = [];
  t.children.forEach((c, i) => {
    const cb = size(c);
    const cx = x + RAIL + (b.w - RAIL * 2 - cb.w) / 2;
    const cm = cy + cb.h / 2;
    mids.push(cm);
    out.push(<line key={`${key}l${i}`} x1={left} x2={cx} y1={cm} y2={cm} className="sch-wire" />);
    out.push(<line key={`${key}r${i}`} x1={cx + cb.w} x2={right} y1={cm} y2={cm} className="sch-wire" />);
    draw(c, cx, cy, net, out, `${key}p${i}`);
    cy += cb.h + GAP;
  });
  out.push(<line key={`${key}rl`} x1={left} x2={left} y1={mids[0]} y2={mids[mids.length - 1]} className="sch-wire" />);
  out.push(<line key={`${key}rr`} x1={right} x2={right} y1={mids[0]} y2={mids[mids.length - 1]} className="sch-wire" />);
  out.push(<line key={`${key}il`} x1={x} x2={left} y1={mid} y2={mid} className="sch-wire" />);
  out.push(<line key={`${key}ir`} x1={right} x2={x + b.w} y1={mid} y2={mid} className="sch-wire" />);
  out.push(<circle key={`${key}dl`} cx={left} cy={mid} r={2.4} className="sch-node" />);
  out.push(<circle key={`${key}dr`} cx={right} cy={mid} r={2.4} className="sch-node" />);
}

export default function NetworkSchematic({net}: {net: NetworkModel}) {
  if (!net.tree) {
    return (
      <div className="sch-unverified">
        <p>Counted parts per stage (wiring text not interpreted):</p>
        <ul>
          {net.parts.map(p => (
            <li key={p.ohm}>
              <i style={{background: valueColor(p.ohm, net)}} aria-hidden /> {p.perStage} × {ohmText(p.ohm)}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const b = size(net.tree);
  const pad = 14;
  const W = b.w + pad * 2, H = b.h + 18;
  const nodes: React.ReactNode[] = [];
  draw(net.tree, pad, 12, net, nodes, 'n');
  const mid = 12 + b.h / 2;
  return (
    <svg className="schematic" viewBox={`0 0 ${W} ${H}`} style={{maxWidth: Math.min(W * 1.25, 520)}} role="img" aria-label={`${net.role === 'front' ? 'Front' : 'Tail'} network per stage: ${net.topology}, ${ohmText(net.equivalentOhm)} equivalent.`}>
      <circle cx={pad - 4} cy={mid} r={3.4} className="sch-terminal" />
      <circle cx={W - pad + 4} cy={mid} r={3.4} className="sch-terminal" />
      <line x1={pad - 1} x2={pad} y1={mid} y2={mid} className="sch-wire" />
      {nodes}
    </svg>
  );
}
