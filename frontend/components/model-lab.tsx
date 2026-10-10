'use client';
import {useEffect, useState} from 'react';
import Link from 'next/link';
import {ArrowDownToLine, ArrowRight, ArrowUpRight, ShieldCheck} from 'lucide-react';
import {api, apiUrl, Data, fmt, isNum, profileInputs, stamp} from '@/lib/api';
import {Badge, KindTag, Notice, PageHeading, Panel, Segmented, Skeleton} from './ui';
import {useWorkspace} from './workspace';
import PooledExperiment from './pooled-experiment';
import BenchmarkComparison from './benchmark-comparison';
import EvaluationEvidence from './evaluation-evidence';

const OUTPUTS = [
  ['Lightning', 0, 'Front time', 'µs'],
  ['Lightning', 1, 'Tail time', 'µs'],
  ['Lightning', 2, 'Crest voltage', 'kV'],
  ['Switching', 0, 'Peak time', 'µs'],
  ['Switching', 1, 'Tail time', 'µs'],
  ['Switching', 2, 'Crest voltage', 'kV'],
] as const;

/** The six frozen-V1 outputs side by side: error measures and baseline verdicts from saved results. */
function SixOutputs({data}: {data: Data}) {
  const comparisons: Data[] = data.benchmark_scorecard?.frozen_v1?.comparisons || [];
  const verdict = (baseline: string, impulse: string, target: string) => comparisons.find(c => c.baseline === baseline)?.targets?.find((t: Data) => t.impulse_type === impulse && t.target === target);
  return (
    <Panel title="Frozen V1 · six outputs on the saved synthetic Hidden Test" eyebrow="Recorded once after V1 was frozen. Lower error is better. These are regression errors, not a percentage of correct laboratory shots." action={<Badge tone="cyan">Default model · V1</Badge>}>
      <div className="six">
        {OUTPUTS.map(([impulse, i, name, unit]) => {
          const m = data.hidden_test?.metrics?.[impulse]?.['Selected hybrid'];
          const vsPhysics = verdict('Physics only', impulse, name);
          const vsKnn = verdict('Exact workbook kNN', impulse, name);
          const verdictText = (v: Data | undefined) =>
            !v || v.verdict === 'NOT RECORDED' ? <span className="unrecorded">Not recorded</span> : v.verdict === 'TIE' ? 'Equal error' : <span className={v.verdict === 'LOWER ERROR' ? 'positive' : 'negative'}>{fmt(Math.abs(v.rmse_reduction_pct), 1)}% {v.verdict === 'LOWER ERROR' ? 'lower' : 'higher'}</span>;
          return (
            <article key={`${impulse}-${i}`} className={`six-cell ${vsKnn?.verdict === 'HIGHER ERROR' ? 'six-exception' : ''}`}>
              <header>
                <span>{impulse}</span>
                <strong>{name}</strong>
              </header>
              <div className="six-primary">
                <b>{fmt(m?.mape_pct?.[i], 3)}</b>
                <small>% MAPE</small>
              </div>
              <div className="six-rmse">
                RMSE {fmt(m?.rmse?.[i], i === 2 ? 3 : 5)} {unit}
              </div>
              <dl>
                <div>
                  <dt>vs physics</dt>
                  <dd>{verdictText(vsPhysics)}</dd>
                </div>
                <div>
                  <dt>vs workbook kNN</dt>
                  <dd>{verdictText(vsKnn)}</dd>
                </div>
              </dl>
            </article>
          );
        })}
      </div>
      <div className="six-foot">
        <span>MAPE: mean absolute percentage error · RMSE: root mean squared error in the output’s units.</span>
        <span>Recorded {data.hidden_test?.evaluated_at ? stamp(data.hidden_test.evaluated_at) : 'in the frozen model registry'} · {data.hidden_test?.policy}</span>
      </div>
      <Notice tone="amber">
        These saved scores evaluate residual predictions before runtime support and scenario gating; optimizer results may fall back to physics. Laboratory accuracy is still unknown: new measured shots across layouts, loads and hardware settings are needed.
      </Notice>
    </Panel>
  );
}

function EvidenceKinds({data}: {data: Data}) {
  const frozen: Data[] = data.benchmark_scorecard?.frozen_v1?.comparisons || [];
  const physics = frozen.find(c => c.baseline === 'Physics only');
  const knn = frozen.find(c => c.baseline === 'Exact workbook kNN');
  const dev = data.benchmark_scorecard?.development_v2?.comparisons?.find((c: Data) => c.baseline === 'Matched exact kNN');
  const num = data.independent_circuit_verification;
  const cards: [string, React.ReactNode, React.ReactNode, string, React.ReactNode][] = [
    ['Frozen V1 · synthetic Hidden Test', <KindTag key="k" kind="synthetic">Synthetic benchmark</KindTag>, `${physics?.lower_error_targets ?? '—'} / 6 · ${knn?.lower_error_targets ?? '—'} / 6`, 'Outputs with lower error vs physics · vs exact workbook kNN (Switching crest is the exception)', <a key="a" href="#six">Six outputs</a>],
    ['Optional V2 · development CV', <KindTag key="k" kind="synthetic">Development evidence</KindTag>, `${dev?.lower_error_targets ?? '—'} / 6`, 'Outputs beating matched kNN in its own development folds. Experimental; no new independent test.', <a key="a" href="#v2">V2 experiment</a>],
    ['CPRI circuit · numerical verification', <KindTag key="k" kind="simulation">Generated simulation</KindTag>, num ? `${num.passing_channels} / ${num.expected_channels}` : '—', 'Numerical agreement channels against an independent integrator of the same assumed topology. Not ML accuracy.', <a key="a" href="#numerical">Verification</a>],
    ['Measured laboratory accuracy', <KindTag key="k" kind="unknown">Not established</KindTag>, 'None', 'No complete, compatible measured per-shot dataset has been evaluated.', <Link key="a" href="/laboratory-evidence/">Laboratory evidence</Link>],
  ];
  return (
    <div className="kinds">
      {cards.map(([title, tag, value, text, link]) => (
        <article key={title}>
          {tag}
          <h3>{title}</h3>
          <strong>{value}</strong>
          <p>{text}</p>
          <span className="kinds-link">{link}</span>
        </article>
      ))}
    </div>
  );
}

function V2Experiment({experiment}: {experiment: Data}) {
  const {inputs, setInputs} = useWorkspace();
  const [type, setType] = useState('Lightning'),
    [target, setTarget] = useState(0);
  const cv = experiment.nested_cv?.[type];
  const unit = target === 2 ? 'kV' : 'µs';
  const improvement = cv?.improvement_vs_v1_pct?.[target];
  const selection = experiment.selection?.[type] || [];
  return (
    <Panel id="v2" title={`V2 experiment · ${experiment.version || 'model search'}`} eyebrow={experiment.evaluation_scope || 'Nested cross-validation within official Train only; no V2 evaluation on the official Hidden Test.'} action={<Badge tone="amber">Experimental · no Hidden Test evaluation</Badge>}>
      <Notice tone="info">
        The matched V1 comparator refits historically selected parameters. Feature bases were explored on Train, so all V2 cross-validation scores are development evidence, not an unbiased independent test. They evaluate residual predictions before runtime support and scenario gating.{' '}
        <a href={apiUrl('/api/documents/accuracy_v2_results')} target="_blank" rel="noreferrer">
          V2 method and limitations <ArrowUpRight size={12} aria-hidden />
        </a>
      </Notice>
      <div className="filter-row">
        <Segmented label="Impulse type" value={type} onChange={setType} options={[['Lightning', 'Lightning'], ['Switching', 'Switching']]} />
        <select aria-label="V2 target metric" value={target} onChange={e => setTarget(Number(e.target.value))}>
          <option value={0}>{type === 'Lightning' ? 'Front' : 'Peak'} time · µs</option>
          <option value={1}>Tail time · µs</option>
          <option value={2}>Crest voltage · kV</option>
        </select>
        <KindTag kind="synthetic">Official Train · nested CV</KindTag>
      </div>
      {cv?.metrics ? (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Matched evaluation</th>
                  <th className="num">MAE ({unit})</th>
                  <th className="num">RMSE ({unit})</th>
                  <th className="num">MAPE (%)</th>
                  <th className="num">Within-type R²</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(cv.metrics).map(([name, m]: [string, any]) => (
                  <tr key={name} className={name === 'V2 search' ? 'experiment-row' : ''}>
                    <td>
                      {name} {name === 'V2 search' && <Badge tone="amber">Experiment</Badge>}
                    </td>
                    <td className="num">{fmt(m.mae?.[target], 5)}</td>
                    <td className="num">{fmt(m.rmse?.[target], 5)}</td>
                    <td className="num">{fmt(m.mape_pct?.[target], 3)}</td>
                    <td className="num">{fmt(m.r2?.[target], 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="delta-line">
            <span>V2 RMSE compared with matched V1 refit</span>
            <strong className={typeof improvement === 'number' && improvement >= 0 ? 'positive' : 'negative'}>{typeof improvement === 'number' ? `${fmt(Math.abs(improvement), 2)}% ${improvement >= 0 ? 'lower error' : 'higher error'}` : 'Not available'}</strong>
            <small>Same outer Train folds. Do not compare this change directly with the saved Hidden Test scores above.</small>
          </div>
        </>
      ) : (
        <p className="panel-note">Nested-CV results for this regime have not been supplied by the experiment.</p>
      )}
      <div className="promotion">
        <ShieldCheck size={18} aria-hidden />
        <div>
          <strong>{experiment.promotion?.eligible ? 'Optional candidate available · V1 remains the default' : 'V1 remains the default · V2 did not pass the development gate'}</strong>
          <p>{experiment.promotion?.reason || 'No promotion decision supplied. V1 remains the default model.'}</p>
          {experiment.promotion?.eligible && (
            <Link className="button small" href="/" onClick={() => setInputs({...profileInputs(inputs, 'workbook_reference_profile'), model_mode: 'experimental_v2'})}>
              Try V2 on workbook profile <ArrowRight size={13} aria-hidden />
            </Link>
          )}
        </div>
      </div>
      <details className="source-details">
        <summary>Candidate choices and fold stability</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Target</th>
                <th>Selected candidate</th>
                <th>Physics basis</th>
                <th>Residual form</th>
              </tr>
            </thead>
            <tbody>
              {selection.map((item: Data, i: number) => (
                <tr key={i}>
                  <td>{['Front / peak', 'Tail', 'Crest'][i] || i + 1}</td>
                  <td>{item.name}</td>
                  <td>{typeof item.basis === 'object' ? JSON.stringify(item.basis) : String(item.basis ?? 'Not supplied')}</td>
                  <td>{typeof item.relative === 'boolean' ? (item.relative ? 'Relative residual' : 'Absolute residual') : String(item.relative ?? 'Not supplied')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {Array.isArray(cv?.fold_rmse) && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Outer Train fold</th>
                  <th className="num">V2 RMSE ({unit})</th>
                </tr>
              </thead>
              <tbody>
                {cv.fold_rmse.map((row: number[], i: number) => (
                  <tr key={i}>
                    <td>Fold {i + 1}</td>
                    <td className="num">{fmt(row[target], 5)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="panel-note">Candidate search and model selection occur within training folds. This panel displays experimental synthetic evidence; new measured laboratory data is still required.</p>
      </details>
    </Panel>
  );
}

export function ModelLab() {
  const [data, setData] = useState<Data | null>(null),
    [error, setError] = useState(''),
    [type, setType] = useState('Lightning'),
    [split, setSplit] = useState('hidden'),
    [target, setTarget] = useState(0),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setError('');
    api('/api/models')
      .then(setData)
      .catch(e => setError(e.message));
  }, [attempt]);
  const results = data && (split === 'validation' ? data.validation : data.hidden_test.metrics)?.[type];
  return (
    <>
      <PageHeading
        tag="Evidence"
        title="Model lab"
        description="What the evaluation pack, the circuit surrogate and the saved workbook models demonstrate, each labelled with its kind of evidence. Simulation agreement is never reported as measured accuracy."
        action={
          <a className="button small" href={apiUrl('/api/documents/data_audit')} target="_blank" rel="noreferrer">
            Open data audit <ArrowUpRight size={14} aria-hidden />
          </a>
        }
      />
      {error && (
        <Notice tone="red" role="alert" title="Model registry could not be read" action={<button className="button small" onClick={() => setAttempt(a => a + 1)}>Retry</button>}>
          {error}
        </Notice>
      )}
      <EvaluationEvidence />
      <h2 className="model-lab-subhead">Workbook benchmark models (supplied synthetic data)</h2>
      {!data ? (
        !error && (
          <Panel>
            <Skeleton lines={6} />
          </Panel>
        )
      ) : (
        <>
          <EvidenceKinds data={data} />
          <div className="facts">
            <div>
              <span>Data provenance</span>
              <strong>Supplied synthetic</strong>
              <small>2,000 records · no laboratory accuracy claim</small>
            </div>
            <div>
              <span>Source splits · Train / Validation / Hidden</span>
              <strong>1,400 / 300 / 300</strong>
              <small>Original Train, Validation and Hidden Test labels</small>
            </div>
            <div>
              <span>Model registry</span>
              <strong>{data.version}</strong>
              <small>Per-target, per-regime model selection</small>
            </div>
          </div>
          <div id="six" className="anchor-target">
            <SixOutputs data={data} />
          </div>
          <div id="numerical" className="anchor-target">
            <BenchmarkComparison data={data} />
          </div>
          <Notice tone="info" title="Pooled R² can hide weak engineering performance.">
            Lightning and Switching operate on very different time scales. Compare each target within its own impulse type, and use the untouched final test only after the configuration is frozen.
          </Notice>
          <Panel
            title={`${type} · ${['front / peak time', 'tail time', 'crest voltage'][target]}`}
            eyebrow="All candidate model families, per split"
            action={<Badge tone="cyan">{split === 'validation' ? 'Official Validation' : 'Final Hidden Test'}</Badge>}
          >
            <div className="filter-row">
              <Segmented label="Impulse type" value={type} onChange={setType} options={[['Lightning', 'Lightning'], ['Switching', 'Switching']]} />
              <Segmented
                label="Data split"
                value={split}
                onChange={setSplit}
                options={[
                  ['validation', 'Validation · model selection'],
                  ['hidden', 'Hidden Test · frozen pipeline'],
                ]}
              />
              <select aria-label="Target metric" value={target} onChange={e => setTarget(Number(e.target.value))}>
                <option value={0}>{type === 'Lightning' ? 'Front' : 'Peak'} time · µs</option>
                <option value={1}>Tail time · µs</option>
                <option value={2}>Crest voltage · kV</option>
              </select>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th className="num">MAE</th>
                    <th className="num">RMSE</th>
                    <th className="num">MAPE</th>
                    <th className="num">Within-type R²</th>
                    <th className="num">RMSE vs physics</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(results || {}).map(([name, m]: [string, any]) => (
                    <tr className={name === 'Selected hybrid' ? 'highlight-row' : ''} key={name}>
                      <td>
                        {name} {name === 'Selected hybrid' && <Badge tone="cyan">Selected</Badge>}
                      </td>
                      <td className="num">{fmt(m.mae?.[target], 4)}</td>
                      <td className="num">{fmt(m.rmse?.[target], 4)}</td>
                      <td className="num">{fmt(m.mape_pct?.[target], 2)}%</td>
                      <td className={`num ${isNum(m.r2?.[target]) && m.r2[target] < 0 ? 'negative' : ''}`}>{fmt(m.r2?.[target], 4)}</td>
                      <td className={`num ${name === 'Physics only' ? 'muted' : m.rmse_improvement_vs_physics_pct?.[target] >= 0 ? 'positive' : 'negative'}`}>
                        {name === 'Physics only' ? 'Baseline' : `${fmt(Math.abs(m.rmse_improvement_vs_physics_pct?.[target]), 2)}% ${m.rmse_improvement_vs_physics_pct?.[target] >= 0 ? 'lower error' : 'higher error'}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="panel-note">
              Units: {target === 2 ? 'kV' : 'µs'} for MAE and RMSE. Negative R² remains visible. {split === 'hidden' ? data.hidden_test.policy : 'Validation guides model selection; it is not a final independent test.'}
            </p>
          </Panel>
          <div className="bottom-grid">
            <Panel title="What the hybrid actually uses">
              <div className="selection-models">
                {data.selection[type].map((name: string, i: number) => (
                  <div key={i}>
                    <span>{['Front / peak', 'Tail', 'Crest'][i]}</span>
                    <strong>{name}</strong>
                    <Badge>Residual model</Badge>
                  </div>
                ))}
              </div>
              <p className="panel-note">{data.interval_method}. Residual correction is shrunk or disabled outside training support.</p>
              <details className="source-details">
                <summary>
                  Reproducibility and tuning <ArrowDownToLine size={13} aria-hidden />
                </summary>
                <p className="panel-note">{data.training_protocol}</p>
                <pre className="code-data">{JSON.stringify(data.cv[type], null, 2)}</pre>
                <p className="panel-note">
                  Dataset SHA-256 <code>{data.dataset_sha256}</code>
                </p>
                <p className="panel-note">
                  Frozen configuration <code>{data.frozen_config_sha256}</code>
                </p>
              </details>
            </Panel>
            <Panel title="Benchmark boundaries">
              <ol className="explanation">
                <li>{data.training_protocol}</li>
                <li>The workbook’s exact formula and cached-case parity pass. Its published hardcoded metric table is inconsistent with evaluation on the supplied split.</li>
                <li>Switching training resistances are not constructible from the literal supplied front stock. Constructible recommendations must be checked for OOD individually.</li>
              </ol>
              <a className="button text-button" href={apiUrl('/api/documents/source_reconciliation')} target="_blank" rel="noreferrer">
                Inspect source reconciliation <ArrowUpRight size={14} aria-hidden />
              </a>
            </Panel>
          </div>
          <div className="section-title">
            <h2>Development studies</h2>
            <p>Separate protocols; their improvements cannot be added to V1’s saved test result. See the experiment timeline for decisions.</p>
          </div>
          {data.experiment_v2 && <V2Experiment experiment={data.experiment_v2} />}
          {data.experiment_v3 && (
            <Panel title="Smooth-model accuracy ablation · V3" action={<Badge tone="amber">No promotion</Badge>}>
              <p className="panel-note">
                A further search over smooth, robust and blended models improved macro development error by {fmt(data.experiment_v3.macro_improvement_pct, 2)}% versus a historical V2 refit. {data.experiment_v3.decision}
              </p>
              <p className="panel-note">{data.experiment_v3.scope} Calibration, Validation and Hidden Test outcomes were not evaluated.</p>
            </Panel>
          )}
          {data.experiment_v4 && <PooledExperiment experiment={data.experiment_v4} />}
          {data.experiment_v5 && (
            <Panel title="Bounded-error accuracy study · V5" eyebrow="Saved Train development study" action={<Badge tone="amber">No promotion</Badge>}>
              <p className="panel-note">
                Twelve configurations tested whether extreme residuals and quantile centers could improve prediction. Macro development error fell {fmt(data.experiment_v5.macro_improvement_pct, 2)}% against the historical V2 refit, with {fmt(data.experiment_v5.improvement_vs_matched_control_pct, 2)}% improvement beyond the matched Ridge control search. The declared promotion gate requires at least 5% overall improvement. {data.experiment_v5.decision}
              </p>
              <p className="panel-note">{data.experiment_v5.scope} Calibration, Validation and Hidden Test outcomes were not evaluated.</p>
              <a className="button text-button" href={apiUrl('/api/documents/accuracy_v5_results')} target="_blank" rel="noreferrer">
                Read V5 method and results <ArrowUpRight size={13} aria-hidden />
              </a>
            </Panel>
          )}
        </>
      )}
    </>
  );
}
