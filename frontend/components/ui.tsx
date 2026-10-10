'use client';
import {ReactNode, useId} from 'react';
import {Check, CircleDashed, CircleAlert, Info, Minus, TriangleAlert, X} from 'lucide-react';
import {fmt, isNum} from '@/lib/api';

export type Tone = 'neutral' | 'green' | 'red' | 'amber' | 'cyan' | 'unknown' | 'violet';

export function Badge({children, tone = 'neutral', title}: {children: ReactNode; tone?: string; title?: string}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

/** Uncertainty-envelope / compliance status with an icon and text, never colour alone. */
export function Status({value}: {value: string | null | undefined}) {
  const v = value || '';
  const tone = v.includes('ROBUST') ? 'green' : v === 'FAIL' ? 'red' : v ? 'amber' : 'unknown';
  const Icon = tone === 'green' ? Check : tone === 'red' ? X : tone === 'amber' ? CircleAlert : CircleDashed;
  return (
    <Badge tone={tone}>
      <Icon size={12} strokeWidth={2.4} aria-hidden /> {v || 'Not recorded'}
    </Badge>
  );
}

export function PassFail({pass, passText = 'Pass', failText = 'Fail'}: {pass: boolean | null | undefined; passText?: string; failText?: string}) {
  if (typeof pass !== 'boolean')
    return (
      <Badge tone="unknown">
        <CircleDashed size={12} aria-hidden /> Not recorded
      </Badge>
    );
  return (
    <Badge tone={pass ? 'green' : 'red'}>
      {pass ? <Check size={12} strokeWidth={2.4} aria-hidden /> : <X size={12} strokeWidth={2.4} aria-hidden />} {pass ? passText : failText}
    </Badge>
  );
}

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = '',
  id,
  tone,
}: {
  title?: ReactNode;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  tone?: 'hall' | 'sheet' | 'quiet';
}) {
  const headingId = useId();
  return (
    <section id={id} className={`panel ${tone ? `panel-${tone}` : ''} ${className}`} aria-labelledby={title ? headingId : undefined}>
      {title && (
        <div className="panel-heading">
          <div className="panel-titles">
            <h2 id={headingId}>{title}</h2>
            {eyebrow && <p className="panel-kicker">{eyebrow}</p>}
          </div>
          {action && <div className="panel-action">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeading({title, description, tag, action}: {title: string; description: string; tag?: string; action?: ReactNode}) {
  return (
    <header className="page-heading">
      <div>
        {tag && <p className="page-tag">{tag}</p>}
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action && <div className="page-actions">{action}</div>}
    </header>
  );
}

export function Empty({title, children, icon}: {title: string; children?: ReactNode; icon?: ReactNode}) {
  return (
    <div className="empty">
      <div className="empty-mark" aria-hidden>
        {icon || <EmptyWave />}
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

function EmptyWave() {
  return (
    <svg width="64" height="28" viewBox="0 0 64 28" fill="none">
      <path d="M2 26 C6 26 7 3 12 3 C20 3 28 16 62 22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M2 26 H62" stroke="currentColor" strokeOpacity=".35" strokeWidth="1" strokeDasharray="2 3" />
    </svg>
  );
}

export function Notice({
  tone = 'info',
  title,
  children,
  role,
  id,
  action,
}: {
  tone?: 'info' | 'amber' | 'red' | 'green' | 'neutral';
  title?: ReactNode;
  children?: ReactNode;
  role?: 'alert' | 'status';
  id?: string;
  action?: ReactNode;
}) {
  const Icon = tone === 'red' ? TriangleAlert : tone === 'amber' ? CircleAlert : tone === 'green' ? Check : Info;
  return (
    <div className={`notice notice-${tone}`} role={role} id={id}>
      <Icon size={16} aria-hidden className="notice-icon" />
      <div className="notice-body">
        {title && <strong>{title}</strong>}
        {children && <div>{children}</div>}
      </div>
      {action && <div className="notice-action">{action}</div>}
    </div>
  );
}

/** Small tag that names what kind of evidence or curve something is. */
export function KindTag({kind, children}: {kind: 'simulation' | 'reconstruction' | 'generated' | 'synthetic' | 'measured' | 'unknown' | 'assumption' | 'conceptual'; children: ReactNode}) {
  return <span className={`kind kind-${kind}`}>{children}</span>;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size,
}: {
  options: readonly (readonly [T, ReactNode])[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  size?: 'small';
}) {
  return (
    <div className={`segmented ${size === 'small' ? 'segmented-small' : ''}`} role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button
          type="button"
          role="radio"
          aria-checked={value === v}
          key={v}
          className={value === v ? 'active' : ''}
          onClick={() => onChange(v)}
          onKeyDown={e => {
            if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
            e.preventDefault();
            const i = options.findIndex(o => o[0] === value);
            const next = options[(i + (e.key === 'ArrowRight' ? 1 : options.length - 1)) % options.length][0];
            onChange(next);
            const group = e.currentTarget.parentElement;
            requestAnimationFrame(() => (group?.querySelector('[aria-checked="true"]') as HTMLElement | null)?.focus());
          }}
          tabIndex={value === v ? 0 : -1}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

/** A value with its unit, keeping missing values visibly missing. */
export function Readout({label, value, digits = 2, unit, sub, tone, size}: {label: ReactNode; value: unknown; digits?: number; unit?: string; sub?: ReactNode; tone?: 'pass' | 'fail' | 'attention'; size?: 'large' | 'small'}) {
  return (
    <div className={`readout ${size ? `readout-${size}` : ''} ${tone ? `readout-${tone}` : ''}`}>
      <span className="readout-label">{label}</span>
      <span className="readout-value">
        {isNum(value) ? fmt(value, digits) : typeof value === 'string' || typeof value === 'number' ? String(value) : 'Not recorded'}
        {unit && isNum(value) && <small>{unit}</small>}
      </span>
      {sub && <span className="readout-sub">{sub}</span>}
    </div>
  );
}

/**
 * Tolerance gauge: allowed band, target tick, nominal value and (optionally)
 * the uncertainty interval. Positions are proportional; numbers stay printed.
 */
export function ToleranceGauge({
  label,
  unit,
  lower,
  upper,
  target,
  value,
  interval,
  pass,
  digits = 3,
  theme = 'paper',
}: {
  label: string;
  unit: string;
  lower: number;
  upper: number;
  target: number;
  value: number | null | undefined;
  interval?: [number | null | undefined, number | null | undefined];
  pass: boolean | null | undefined;
  digits?: number;
  theme?: 'paper' | 'hall';
}) {
  const span = upper - lower;
  const lo = lower - span * 0.35, hi = upper + span * 0.35;
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100))}%`;
  const has = isNum(value);
  const iv = interval && isNum(interval[0]) && isNum(interval[1]) ? (interval as [number, number]) : null;
  const deviation = has && isNum(target) && target !== 0 ? ((value! - target) / target) * 100 : null;
  const clipped = has && (value! < lo || value! > hi);
  return (
    <div className={`gauge gauge-${theme} ${pass === false ? 'gauge-fail' : pass ? 'gauge-pass' : ''}`}>
      <div className="gauge-top">
        <span className="gauge-label">{label}</span>
        <span className="gauge-state">
          {typeof pass === 'boolean' ? (pass ? <Check size={13} strokeWidth={2.6} aria-hidden /> : <X size={13} strokeWidth={2.6} aria-hidden />) : <Minus size={13} aria-hidden />}
          <span>{typeof pass === 'boolean' ? (pass ? 'Within limits' : 'Outside limits') : 'Not recorded'}</span>
        </span>
      </div>
      <div className="gauge-value">
        {has ? fmt(value, digits) : '—'}
        <small>{unit}</small>
        {deviation !== null && <span className="gauge-dev">{deviation > 0 ? '+' : ''}{fmt(deviation, 2)}% vs target</span>}
      </div>
      <div className="gauge-track" aria-hidden>
        <span className="gauge-band" style={{left: pos(lower), width: `calc(${pos(upper)} - ${pos(lower)})`}} />
        {iv && <span className="gauge-interval" style={{left: pos(iv[0]), width: `calc(${pos(iv[1])} - ${pos(iv[0])})`}} />}
        <span className="gauge-target" style={{left: pos(target)}} />
        {has && <span className={`gauge-marker ${clipped ? 'clipped' : ''}`} style={{left: pos(value!)}} />}
      </div>
      <div className="gauge-scale">
        <span>{fmt(lower, digits > 2 ? 2 : digits)}</span>
        <span>target {fmt(target, digits > 2 ? 2 : digits)}</span>
        <span>{fmt(upper, digits > 2 ? 2 : digits)}</span>
      </div>
      {iv && (
        <div className="gauge-interval-text">
          Envelope {fmt(iv[0], digits)}–{fmt(iv[1], digits)} {unit}
        </div>
      )}
    </div>
  );
}

export function Skeleton({lines = 3}: {lines?: number}) {
  return (
    <div className="skeleton" aria-hidden>
      {Array.from({length: lines}, (_, i) => (
        <span key={i} style={{width: `${92 - i * 14}%`}} />
      ))}
    </div>
  );
}

/** Indeterminate activity: no invented percentages or phases. */
export function Working({children}: {children: ReactNode}) {
  return (
    <span className="working" role="status">
      <span className="working-bar" aria-hidden />
      {children}
    </span>
  );
}

export function Unrecorded({children = 'Not recorded'}: {children?: ReactNode}) {
  return <span className="unrecorded">{children}</span>;
}
