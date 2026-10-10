'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {ArrowRight} from 'lucide-react';
import {Data, fmt, human, shortId} from '@/lib/api';
import {Badge, Empty, PageHeading, Panel, Status} from './ui';
import {useWorkspace} from './workspace';
import SetupTransitionPlanner from './setup-transition-planner';
import {AgreementEvidence, NominalEvidence, VerificationEvidence, candidateEvidence} from './run-evidence';

export function Compare() {
  const {run, setSelected, selected} = useWorkspace();
  const router = useRouter();
  const [visible, setVisible] = useState<number[]>([0, 1, 2, 3, 4]);
  const candidates: Data[] = run?.candidates || [];
  const cs = candidates.filter((_, i) => visible.includes(i));
  const inputs = run?.inputs || {};
  const solver = inputs.solver || 'reference';
  const ranking = Array.isArray(run?.ranking_config?.ranking_order)
    ? run!.ranking_config.ranking_order.join(' → ')
    : inputs.require_model_agreement
      ? 'Both nominal model checks → sampled agreement → uncertainty-envelope containment → weighted cost'
      : 'Nominal compliance → uncertainty-envelope containment → weighted cost';
  const evidence = (c: Data) => candidateEvidence(c, inputs);
  const inspect = (id: string) => {
    setSelected(candidates.findIndex(candidate => candidate.id === id));
    router.push('/');
  };
  const rows: [string, (c: Data) => React.ReactNode, string?][] = [
    ['Primary nominal limits', c => <NominalEvidence value={evidence(c).primary_nominal_pass} />, 'Evidence'],
    ['Agreement at nominal inputs', c => <AgreementEvidence agreement={evidence(c).agreement} solver={solver} />],
    ['Uncertainty-envelope status', c => <Status value={c.compliance?.status} />],
    ['Search samples · primary pass', c => (typeof c.robustness?.nominal_scenario_pass_pct === 'number' ? `${fmt(c.robustness.nominal_scenario_pass_pct, 1)}%` : 'Not recorded')],
    ...(inputs.require_model_agreement
      ? ([['Search samples · both models pass', (c: Data) => (typeof c.model_agreement?.sampled_both_pass_pct === 'number' ? `${fmt(c.model_agreement.sampled_both_pass_pct, 1)}%` : 'Not recorded')]] as [string, (c: Data) => React.ReactNode][])
      : []),
    ['Post-ranking challenge', c => <VerificationEvidence verification={evidence(c).verification} />],
    [
      'Smallest challenged limit margin',
      c =>
        typeof c.verification?.worst_case?.minimum_margin_fraction === 'number' ? (
          <span className={c.verification.worst_case.minimum_margin_fraction >= 0 ? 'positive' : 'negative'}>{fmt(c.verification.worst_case.minimum_margin_fraction * 100, 1)}%</span>
        ) : (
          'Not recorded'
        ),
    ],
    ['Distinct challenged scenarios', c => c.verification?.unique_scenarios ?? 'Not recorded'],
    [`Primary ${inputs.impulse_type === 'Switching' ? 'peak' : 'front'} time (µs)`, c => fmt(c.hybrid?.front_us, 4), 'Predicted waveform'],
    ['Primary tail time (µs)', c => fmt(c.hybrid?.tail_us, 3)],
    ['Primary crest voltage (kV)', c => fmt(c.hybrid?.crest_kv, 3)],
    ...(solver === 'reference'
      ? ([
          [`Circuit ${inputs.impulse_type === 'Switching' ? 'peak' : 'front'} time (µs)`, (c: Data) => fmt(c.circuit_crosscheck?.front_us, 4)],
          ['Circuit tail time (µs)', (c: Data) => fmt(c.circuit_crosscheck?.tail_us, 3)],
          ['Circuit crest voltage (kV)', (c: Data) => fmt(c.circuit_crosscheck?.crest_kv, 3)],
        ] as [string, (c: Data) => React.ReactNode][])
      : []),
    ['Stages', c => c.settings.stages, 'Hardware'],
    ['Charging kV / stage', c => fmt(c.settings.charge_kv_stage, 3)],
    ['Front network', c => c.front_network.topology],
    ['Tail network', c => c.tail_network.topology],
    ['Total component count', c => c.setup_component_count],
    ['Stage headroom (kV)', c => fmt(c.settings.voltage_margin_kv_stage, 3)],
    ['Energy margin (kJ)', c => fmt(c.settings.energy_margin_kj, 2)],
    ['ML support', c => (c.ood?.state ? human(c.ood.state) : 'Not recorded')],
    ['Weighted ranking cost', c => <strong>{fmt(c.score, 4)}</strong>, 'Ranking'],
  ];
  return (
    <>
      <PageHeading tag="Engineering" title="Compare settings" description="Engineering trade-offs in the original search order, and the hardware changes needed from a saved setup. New challenge results never change the ranking." action={run && <Badge>Run {shortId(run.id)}</Badge>} />
      {!run ? (
        <Empty title="Run an optimization first">
          <Link href="/">Open the optimizer</Link> to create a saved run with ranked candidates.
        </Empty>
      ) : (
        <>
          <div className="context-bar">
            <div>
              <strong>
                {inputs.impulse_type} · {fmt(inputs.test_kv, 0)} kV
              </strong>
              <span>
                {run.profile?.name} · {run.model_version}
              </span>
            </div>
            <Badge>Simulation evidence</Badge>
          </div>
          <SetupTransitionPlanner run={run} />
          <div className="ranking-strip">
            <span>Ranking priority</span>
            <p>{ranking}</p>
            <small>Lower weighted cost breaks ties after the preceding checks. Post-ranking scenarios are additional evidence, not a ranking input.</small>
          </div>
          <Panel
            title={`${solver === 'reference' ? 'Reference-model' : 'Circuit-model'} candidate comparison`}
            action={<Badge tone="cyan">{cs.length} shown</Badge>}
          >
            <div className="filter-row" role="group" aria-label="Candidates to compare">
              {candidates.map((c, i) => (
                <label className={`chip-check ${visible.includes(i) ? 'on' : ''}`} key={c.id}>
                  <input type="checkbox" checked={visible.includes(i)} onChange={e => setVisible(e.target.checked ? [...visible, i].sort((a, b) => a - b) : visible.filter(j => j !== i))} />
                  Rank {c.rank ?? i + 1} <Status value={c.compliance?.status} />
                </label>
              ))}
            </div>
            {!cs.length ? (
              <Empty title="Select a candidate to compare">Use the rank switches above to restore the evidence table.</Empty>
            ) : (
              <div className="table-wrap">
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Engineering measure</th>
                      {cs.map(c => (
                        <th key={c.id} className={candidates[selected]?.id === c.id ? 'col-selected' : ''}>
                          Rank {c.rank} {c.pareto_optimal && <Badge tone="violet">Pareto</Badge>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(([label, get, group]) => (
                      <tr key={label} className={group ? 'group-start' : ''}>
                        <td>
                          {group && <span className="row-group">{group}</span>}
                          {label}
                        </td>
                        {cs.map(c => (
                          <td key={c.id}>{get(c)}</td>
                        ))}
                      </tr>
                    ))}
                    {Object.keys(candidates[0]?.score_breakdown || {}).map(k => (
                      <tr key={k}>
                        <td className="muted">↳ {human(k)}</td>
                        {cs.map(c => (
                          <td key={c.id} className="mono">
                            {fmt(c.score_breakdown?.[k], 4)}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td>Waveform and explanation</td>
                      {cs.map(c => (
                        <td key={c.id}>
                          <button className="button small" onClick={() => inspect(c.id)}>
                            Inspect rank {c.rank} <ArrowRight size={13} aria-hidden />
                          </button>
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            <p className="panel-note">
              Search samples are used while ranking shortlisted settings. The post-ranking challenge uses separate samples and boundary corners with hardware held fixed. Neither percentage is an accuracy score or a probability of laboratory success. Limit margin is the remaining fraction of the allowed half-range; a negative value exceeds a limit.
            </p>
            <p className="panel-note">Pareto flag considers waveform accuracy, component count and stage utilization among returned candidates. {run.search?.search_kind}</p>
          </Panel>
          <div className="section-title">
            <h2>Counted component plans</h2>
            <p>Inventory provenance: {run.inventory_provenance}</p>
          </div>
          <div className="plans-grid">
            {cs.map(c => (
              <Panel title={`Rank ${c.rank}`} eyebrow={`${c.settings.stages} stages · ${fmt(c.settings.charge_kv_stage, 2)} kV / stage`} key={c.id}>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Network and value</th>
                        <th className="num">Per stage</th>
                        <th className="num">Total required</th>
                        <th className="num">Available / stage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {['front', 'tail'].flatMap(k =>
                        c[`${k}_network`].components.map((part: Data, i: number) => (
                          <tr key={`${k}-${i}`}>
                            <td>
                              {human(k)} · {fmt(part.ohm, 2)} Ω
                            </td>
                            <td className="num">{part.count_per_stage}</td>
                            <td className="num">{part.total_required}</td>
                            <td className="num">{part.available_per_stage}</td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </Panel>
            ))}
          </div>
        </>
      )}
    </>
  );
}
