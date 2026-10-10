'use client';
import {useEffect, useState} from 'react';
import Link from 'next/link';
import {ArrowRight, CircleDashed, FileClock, FlaskConical, Microscope, Upload} from 'lucide-react';
import {api, Data, fmt, isNum} from '@/lib/api';
import {Badge, Empty, KindTag, Notice, PageHeading, Panel, Segmented, Skeleton} from './ui';

const trialSources: Record<string, string> = {
  synthetic_benchmark: 'synthetic_benchmark',
  generated_demo: 'generated_demo',
  generated_stress_test: 'generated_demo',
  measured_lab: 'measured_lab',
};
export function trialSourceType(trial: Data): string {
  if (typeof trial.evidence?.source_type === 'string') return trialSources[trial.evidence.source_type] || 'unknown';
  // Historical records lack the backend evidence snapshot. Embedded non-lab origin
  // still defeats a measured declaration, matching the backend admission policy.
  const embedded = trial.provenance?.embedded_metadata?.source_type;
  if (embedded != null && trialSources[embedded] !== 'measured_lab') return trialSources[embedded] || 'unknown';
  return trialSources[trial.source_type] || 'unknown';
}
export function sourceLabel(source: string): string {
  return source === 'measured_lab'
    ? 'Measured lab'
    : source === 'synthetic_benchmark'
      ? 'Synthetic benchmark'
      : source === 'generated_demo' || source === 'generated_stress_test'
        ? 'Generated demo'
        : 'Unknown source';
}
export function SourceBadge({trial}: {trial: Data}) {
  const source = trialSourceType(trial);
  const kind = source === 'measured_lab' ? 'measured' : source === 'synthetic_benchmark' ? 'synthetic' : source === 'generated_demo' ? 'generated' : 'unknown';
  return <KindTag kind={kind}>{sourceLabel(source).toUpperCase()}</KindTag>;
}

export function EvidenceCard({evidence}: {evidence?: Data}) {
  if (!evidence) return <p className="panel-note">Evidence classification not recorded for this saved recommendation.</p>;
  // Levels 0–5 name the highest recorded evidence activity; they are not a cumulative score,
  // so only the attained level is marked.
  return (
    <div className="evidence-card">
      <div className="evidence-level">
        <ol className="evidence-ladder" aria-label="Evidence level, 0 to 5">
          {Array.from({length: 6}, (_, i) => (
            <li key={i} className={i === evidence.level ? 'on' : ''} aria-current={i === evidence.level ? 'true' : undefined}>
              {i}
            </li>
          ))}
        </ol>
        <div>
          <span>Level {evidence.level ?? '—'} · highest activity recorded</span>
          <h3>{evidence.label}</h3>
        </div>
      </div>
      <ul className="evidence-checks">
        {evidence.checks?.map((row: Data) => {
          const status = String(row.status ?? 'Not recorded');
          const tone = status === 'FAIL' ? 'red' : status === 'PASS' ? 'green' : /pending|not verified|outside|off|unknown|not recorded/i.test(status) ? 'unknown' : 'neutral';
          return (
            <li key={row.label}>
              <span>{row.label}</span>
              <Badge tone={tone}>{status}</Badge>
            </li>
          );
        })}
      </ul>
      <p className="panel-note">{evidence.scope}</p>
    </div>
  );
}

function Count({label, value, note}: {label: string; value: unknown; note: string}) {
  return (
    <div className="count">
      <span>{label}</span>
      <strong className={isNum(value) && value === 0 ? 'zero' : ''}>{isNum(value) || typeof value === 'string' ? String(value) : 'Not recorded'}</strong>
      <small>{note}</small>
    </div>
  );
}

const STATUS_KIND: Record<string, 'simulation' | 'reconstruction' | 'assumption' | 'unknown'> = {
  'SOURCE PROVIDED': 'simulation',
  DERIVED: 'reconstruction',
  ASSUMED: 'assumption',
  UNKNOWN: 'unknown',
};

export default function EvidencePage({kind}: {kind: 'laboratory' | 'hardware' | 'timeline' | 'search'}) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(''),
    [profile, setProfile] = useState(0),
    [attempt, setAttempt] = useState(0);
  const endpoint = {laboratory: 'laboratory-evidence', hardware: 'hardware-integrity', timeline: 'experiment-timeline', search: 'search-quality'}[kind];
  const titles = {laboratory: 'Laboratory evidence', hardware: 'Hardware verification', timeline: 'Experiment timeline', search: 'Search quality'};
  const descriptions = {
    laboratory: 'Trace each capture to its source, saved prediction and acquisition review. Only eligible measured captures can count as evidence.',
    hardware: 'What the sources state, what is derived, what the application assumes, and what is still unknown, for each separate generator profile.',
    timeline: 'Every saved model study with its protocol and decision. One active default; rejected studies stay visible.',
    search: 'Bounded search compared with exhaustive enumeration on small, declared synthetic spaces.',
  };
  useEffect(() => {
    let alive = true;
    setError('');
    api(`/api/${endpoint}`)
      .then(d => {
        if (!alive) return;
        setData(d);
        if (kind === 'hardware') setProfile(Math.max(0, d.findIndex((p: Data) => p.profile_id === 'cpri_problem_brief_profile')));
      })
      .catch(e => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [endpoint, kind, attempt]);
  return (
    <>
      <PageHeading title={titles[kind]} description={descriptions[kind]} tag="Evidence" />
      {error && (
        <Notice
          tone="red"
          role="alert"
          title="Saved evidence could not be read"
          action={
            <button className="button small" onClick={() => setAttempt(a => a + 1)}>
              Retry
            </button>
          }
        >
          {error}
        </Notice>
      )}
      {!data && !error && (
        <Panel>
          <Skeleton lines={5} />
        </Panel>
      )}
      {data && kind === 'laboratory' && <Laboratory data={data} />}
      {data && kind === 'hardware' && <Hardware data={data} profile={profile} setProfile={setProfile} />}
      {data && kind === 'timeline' && <Timeline data={data} />}
      {data && kind === 'search' && <SearchQuality data={data} />}
    </>
  );
}

function Laboratory({data}: {data: Data}) {
  const empty = !!data.empty_message || !data.captures?.length;
  return (
    <>
      <div className="counts">
        <Count label="Measured captures" value={data.measured_captures} note="Declared measured laboratory shots" />
        <Count label="Usable for calibration" value={data.usable_for_calibration} note="Passed source and acquisition admission" />
        <Count label="Eligible for independent evaluation" value={data.eligible_for_independent_evaluation} note="Evaluation needs at least three" />
        <Count label="Excluded from evaluation" value={data.excluded_captures} note="Reasons listed per capture" />
      </div>
      {empty && (
        <section className="lab-empty" aria-labelledby="lab-empty-title">
          <div className="lab-empty-text">
            <KindTag kind="unknown">No measured evidence recorded</KindTag>
            <h2 id="lab-empty-title">No laboratory measurements have been loaded.</h2>
            <p>{(data.empty_message || '').replace('No laboratory measurements have been loaded.', '').trim() || 'Synthetic performance does not establish laboratory accuracy.'} This page fills in only from real captures imported against a saved prediction.</p>
            <div className="heading-actions">
              <Link className="button primary" href="/trial-calibrator/">
                <Upload size={15} aria-hidden /> Import and review a waveform
              </Link>
              <Link className="button" href="/">
                Make a saved prediction first <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
          </div>
          <ol className="pipeline" aria-label="Path for measured evidence">
            {[
              ['Saved prediction', 'Optimize first; the prediction is frozen before any shot is uploaded.'],
              ['Raw measured capture', 'Original CSV bytes, units, onset and instrument metadata are kept.'],
              ['Acquisition review', 'Crest, half-value and tail completeness are checked; failures are excluded.'],
              ['Scoped calibration', 'One shot corrects only the matching profile, layout and settings.'],
              ['Independent evaluation', 'At least three eligible, distinct captures; calibration sources excluded.'],
            ].map(([title, text], i) => {
              const count = [null, data.measured_captures, data.usable_for_calibration, null, data.eligible_for_independent_evaluation][i];
              return (
                <li key={title}>
                  <span className="pipeline-n">{i + 1}</span>
                  <div>
                    <strong>{title}</strong>
                    <p>{text}</p>
                  </div>
                  {isNum(count) && (
                    <span className="pipeline-count" title="Measured captures at this step">
                      {count}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      )}
      <Panel
        title="Capture provenance"
        eyebrow={data.scope}
        action={
          <Link className="button small" href="/trial-calibrator/">
            <FlaskConical size={14} aria-hidden /> Upload or evaluate captures
          </Link>
        }
      >
        {data.captures?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Capture and setup</th>
                  <th>Acquisition review</th>
                  <th>Calibration</th>
                  <th>Evaluation / exclusions</th>
                </tr>
              </thead>
              <tbody>
                {data.captures.map((r: Data) => (
                  <tr key={r.source_id}>
                    <td>
                      <SourceBadge trial={r} />
                    </td>
                    <td>
                      <code>{r.source_id}</code>
                      <small className="block">
                        {r.impulse_type || 'Unknown impulse'} · {r.generator_profile || 'Unknown profile'}
                      </small>
                      <small className="block">
                        {r.layout_id || 'Unknown layout'} · {r.model_version || 'Unknown model'}
                      </small>
                      <small className="block">Captured {r.captured_at || 'not recorded'} · instrument {r.measurement_instrument || 'not recorded'}</small>
                    </td>
                    <td>{r.quality_status || <span className="unrecorded">Not recorded</span>}</td>
                    <td>
                      <Badge tone={r.eligible_for_calibration ? 'green' : 'unknown'}>{r.eligible_for_calibration ? 'Eligible' : 'Excluded'}</Badge>
                    </td>
                    <td>{r.eligible_for_external_accuracy ? <Badge tone="green">Eligible</Badge> : <span className="exclusions">{(r.exclusion_reasons || []).join(' ') || 'Not eligible'}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No captures recorded" icon={<Microscope size={26} />}>
            Captures appear here after an upload in the trial calibrator, with their source type and admission decision.
          </Empty>
        )}
      </Panel>
      <div className="group-grid">
        {[
          ['source', data.by_source],
          ['impulse type', data.by_impulse],
          ['profile', data.by_profile],
          ['layout', data.by_layout],
          ['model version', data.by_model],
        ].map(([name, values]) => (
          <Panel key={name as string} title={`By ${name}`} tone="quiet">
            {values && Object.keys(values).length ? (
              <dl className="kv">
                {Object.entries(values as Data).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="unrecorded">No measured captures</p>
            )}
          </Panel>
        ))}
      </div>
    </>
  );
}

function Hardware({data, profile, setProfile}: {data: Data[]; profile: number; setProfile: (i: number) => void}) {
  const p = data[profile];
  if (!p) return <Empty title="No generator profiles recorded" />;
  const counts = (p.parameters || []).reduce((acc: Record<string, number>, r: Data) => ({...acc, [r.status]: (acc[r.status] || 0) + 1}), {});
  return (
    <>
      <div className="profile-switch">
        <Segmented label="Generator profile" value={String(profile)} onChange={v => setProfile(Number(v))} options={data.map((x: Data, i: number) => [String(i), x.profile_name] as const)} />
      </div>
      <section className="conflict" aria-label="Separate source profiles">
        <div>
          <span className="kind kind-simulation">Problem statement · CPRI</span>
          <strong>
            {p.conflict.problem_statement.max_stages} stages · {p.conflict.problem_statement.stage_c_uf} µF / stage
          </strong>
        </div>
        <div className="conflict-vs" aria-hidden>
          ≠
        </div>
        <div>
          <span className="kind kind-synthetic">Workbook · synthetic reference</span>
          <strong>
            {p.conflict.workbook.max_stages} stages · {p.conflict.workbook.stage_c_uf} µF / stage
          </strong>
        </div>
        <p>
          <b>{p.conflict.status}.</b> {p.conflict.message}
        </p>
      </section>
      <div className="status-counts">
        {['SOURCE PROVIDED', 'DERIVED', 'ASSUMED', 'UNKNOWN'].map(s => (
          <div key={s} className={`status-count status-${STATUS_KIND[s]}`}>
            <span className={`kind kind-${STATUS_KIND[s]}`}>{s.toLowerCase().replace(/^\w/, ch => ch.toUpperCase())}</span>
            <strong>{counts[s] || 0}</strong>
          </div>
        ))}
      </div>
      <Panel title={p.profile_name} eyebrow={p.scope} action={<Badge tone={p.physical_hardware_verified ? 'green' : 'amber'}>{p.physical_hardware_verified ? 'Physical hardware verified' : 'Physical verification pending'}</Badge>}>
        {p.inventory_override_required && <Notice tone="amber">Stock quantities are unknown. Optimization requires an explicit operator inventory with provenance.</Notice>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Value</th>
                <th>Status</th>
                <th>Source and interpretation</th>
              </tr>
            </thead>
            <tbody>
              {p.parameters.map((r: Data) => {
                const missing = r.value === null || (Array.isArray(r.value) && !r.value.length);
                return (
                  <tr key={r.parameter} className={`param-${STATUS_KIND[r.status] || 'unknown'}`}>
                    <td>{r.label}</td>
                    <td>{missing ? <span className="unrecorded">Unknown</span> : Array.isArray(r.value) ? r.value.join(', ') : String(r.value)}</td>
                    <td>
                      <span className={`kind kind-${STATUS_KIND[r.status] || 'unknown'}`}>{r.status}</span>
                    </td>
                    <td>
                      {r.source || <span className="unrecorded">Not supplied</span>}
                      <small className="block">
                        Profile v{r.profile_version} · source date {r.source_date || 'unknown'}
                      </small>
                      {r.note && <small className="block">{r.note}</small>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      {p.notes?.length > 0 && (
        <Panel title="Unresolved physical facts" tone="quiet">
          <ul className="notes-list">
            {p.notes.map((n: string) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}

function Timeline({data}: {data: Data}) {
  return (
    <>
      <Notice tone="info" title={`Active model: ${data.active_model}`}>
        {data.scope}
      </Notice>
      <ol className="timeline">
        {data.experiments.map((e: Data) => {
          const tone = e.status === 'PROMOTED' ? 'green' : e.status === 'REJECTED' ? 'amber' : 'cyan';
          return (
            <li key={e.name} className={`timeline-item timeline-${e.status?.toLowerCase()}`}>
              <div className="timeline-node" aria-hidden>
                {e.name}
              </div>
              <article className="timeline-card">
                <header>
                  <div>
                    <h3>
                      {e.name} · <span>{e.version || 'No saved artifact'}</span>
                    </h3>
                    <p className="timeline-hypothesis">{e.hypothesis}</p>
                  </div>
                  <div className="heading-actions">
                    <KindTag kind={/DEVELOPMENT/.test(e.evidence_type) ? 'synthetic' : 'reconstruction'}>{e.evidence_type}</KindTag>
                    <Badge tone={tone}>{e.status}</Badge>
                  </div>
                </header>
                <dl className="kv">
                  <div>
                    <dt>Protocol</dt>
                    <dd>{e.protocol}</dd>
                  </div>
                  <div>
                    <dt>Comparator</dt>
                    <dd>{e.baseline || <span className="unrecorded">Not recorded</span>}</dd>
                  </div>
                  {e.performance_change_pct != null && (
                    <div>
                      <dt>{e.performance_change_scope ? 'Target error reduction' : 'Macro error reduction'}</dt>
                      <dd>
                        <strong>{fmt(e.performance_change_pct, 4)}%</strong> under this development comparison
                        {e.performance_change_scope && <small className="block">{e.performance_change_scope}</small>}
                      </dd>
                    </div>
                  )}
                  <div>
                    <dt>Promotion criterion</dt>
                    <dd>{e.promotion_criterion}</dd>
                  </div>
                  <div>
                    <dt>Decision</dt>
                    <dd>{e.decision}</dd>
                  </div>
                  <div>
                    <dt>Hidden Test evaluated</dt>
                    <dd>{typeof e.hidden_test_evaluated === 'boolean' ? (e.hidden_test_evaluated ? 'Yes' : 'No') : <span className="unrecorded">Not recorded</span>}</dd>
                  </div>
                </dl>
                <details className="source-details">
                  <summary>Saved artifact identity</summary>
                  <dl className="kv">
                    <div>
                      <dt>Evidence file</dt>
                      <dd>
                        <code>{e.evidence_path}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Evidence SHA-256</dt>
                      <dd>
                        <code>{e.evidence_sha256}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Dataset SHA-256</dt>
                      <dd>
                        <code>{e.dataset}</code>
                      </dd>
                    </div>
                    {e.protocol_hash_matches != null && (
                      <div>
                        <dt>Protocol hash</dt>
                        <dd>{e.protocol_hash_matches ? 'Match' : 'Mismatch'}</dd>
                      </div>
                    )}
                  </dl>
                </details>
              </article>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function SearchQuality({data}: {data: Data}) {
  if (data.status === 'PENDING') return <Empty title="Search quality benchmark pending" icon={<FileClock size={26} />}>{data.message}</Empty>;
  const maxEval = Math.max(1, ...data.cases.map((c: Data) => c.exhaustive_evaluated || 0));
  return (
    <>
      <div className="heading-actions" style={{marginBottom: 14}}>
        <KindTag kind="synthetic">Synthetic engineering benchmark</KindTag>
        <span className="muted">Declared fixtures · not physical validation · not a global-optimum proof</span>
      </div>
      <div className="counts">
        <Count label="Top-1 match" value={isNum(data.top1_match_rate) ? `${fmt(data.top1_match_rate * 100, 0)}%` : null} note="Bounded winner equals exhaustive winner" />
        <Count label="Top-3 containment" value={isNum(data.top3_containment_rate) ? `${fmt(data.top3_containment_rate * 100, 0)}%` : null} note="Exhaustive best within bounded top 3" />
        <Count label="Worst objective gap" value={isNum(data.worst_objective_gap) ? fmt(data.worst_objective_gap, 5) : null} note="Lower is better; 0 means equal" />
        <Count label="Median runtime speed-up" value={isNum(data.median_runtime_speedup) ? `${fmt(data.median_runtime_speedup, 2)}×` : null} note="Machine-dependent timing" />
      </div>
      <Panel title="Bounded versus exhaustive, per declared case" eyebrow={data.scope}>
        <div className="sq-cases">
          {data.cases.map((c: Data) => (
            <div className="sq-case" key={c.id}>
              <div className="sq-case-head">
                <strong>{c.id}</strong>
                <Badge tone={c.same_best_candidate ? 'green' : 'amber'}>{c.same_best_candidate ? 'Same winner' : `Exhaustive rank ${c.bounded_winner_exhaustive_rank ?? 'not found'}`}</Badge>
                {c.bounded_nominal_pass === false && c.exhaustive_nominal_pass === false && <Badge tone="unknown">Nominal fail in both</Badge>}
                {typeof c.bounded_nominal_pass === 'boolean' && typeof c.exhaustive_nominal_pass === 'boolean' && c.bounded_nominal_pass !== c.exhaustive_nominal_pass && <Badge tone="amber">Nominal result differs</Badge>}
              </div>
              <div className="sq-bars" aria-label={`Evaluated ${c.bounded_evaluated} bounded and ${c.exhaustive_evaluated} exhaustive candidates`}>
                <div>
                  <span>Bounded</span>
                  <i style={{width: `${(c.bounded_evaluated / maxEval) * 100}%`}} />
                  <b>{c.bounded_evaluated}</b>
                </div>
                <div>
                  <span>Exhaustive</span>
                  <i className="ex" style={{width: `${(c.exhaustive_evaluated / maxEval) * 100}%`}} />
                  <b>{c.exhaustive_evaluated}</b>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fixed case</th>
                <th className="num">Exhaustive rank of bounded winner</th>
                <th className="num">Objective gap</th>
                <th className="num">Waveform error difference</th>
                <th className="num">Part difference</th>
                <th className="num">Evaluated bounded / exhaustive</th>
                <th className="num">Seconds bounded / exhaustive</th>
              </tr>
            </thead>
            <tbody>
              {data.cases.map((c: Data) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td className="num">{c.bounded_winner_exhaustive_rank ?? 'Not found'}</td>
                  <td className="num">{fmt(c.objective_gap, 5)}</td>
                  <td className="num">{fmt(c.waveform_error_difference, 5)}</td>
                  <td className="num">{c.component_count_difference}</td>
                  <td className="num">
                    {c.bounded_evaluated} / {c.exhaustive_evaluated}
                  </td>
                  <td className="num">
                    {fmt(c.bounded_seconds)} / {fmt(c.exhaustive_seconds)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-note">
          <CircleDashed size={13} aria-hidden style={{display: 'inline', verticalAlign: '-2px'}} /> {data.limitation}
        </p>
      </Panel>
    </>
  );
}
