'use client';
import {useEffect, useMemo, useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowRight, Download, GitCompareArrows, LoaderCircle} from 'lucide-react';
import {api, apiUrl, Data, fmt, post, shortId, signed} from '@/lib/api';
import {Badge, Notice, Panel, Status} from './ui';
import {useWorkspace} from './workspace';
import GeneratorView from './generator/generator-view';
import {modelFromTransition, ohmText} from '@/lib/generator-model';

export default function SetupTransitionPlanner({run}: {run: Data}) {
  const {setSelected} = useWorkspace();
  const router = useRouter();
  const [history, setHistory] = useState<Data[]>([]),
    [baselineId, setBaselineId] = useState(''),
    [candidateId, setCandidateId] = useState('');
  const [baseline, setBaseline] = useState<Data | null>(null),
    [result, setResult] = useState<Data | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setResult(null);
    api('/api/runs')
      .then(rows => {
        if (active) setHistory(rows);
      })
      .catch(e => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [run.id]);
  useEffect(() => {
    let active = true;
    setBaseline(null);
    setCandidateId('');
    setResult(null);
    if (baselineId)
      api(`/api/runs/${baselineId}`)
        .then(r => {
          if (active) {
            setBaseline(r);
            setCandidateId(r.candidates[0]?.id || '');
          }
        })
        .catch(e => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [baselineId]);
  const compatible = history.filter(r => r.inputs.profile_id === run.inputs.profile_id && r.inputs.layout_id === run.inputs.layout_id);
  // Discard stale planning responses when the selection or run changes.
  const reviewed = result?.target.run_id === run.id && result?.baseline.run_id === baselineId && result?.baseline.candidate_id === candidateId ? result : null;
  const closest = reviewed?.options.find((o: Data) => o.candidate_id === reviewed.closest_nominal_candidate_id);
  const displayed = reviewed?.options.find((o: Data) => o.candidate_id === shown) || closest || reviewed?.options?.[0];
  const model = useMemo(() => (reviewed && displayed ? modelFromTransition(reviewed, displayed, run) : null), [reviewed, displayed, run]);
  async function compare() {
    setBusy(true);
    setError('');
    setResult(null);
    setShown(null);
    const request = {baseline_run_id: baselineId, baseline_candidate_id: candidateId};
    try {
      setResult(await post(`/api/runs/${run.id}/setup-transitions`, request));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Plan changes from a saved setup" eyebrow="Saved plans do not authenticate the equipment actually installed; confirm before changing hardware." action={<Badge tone="amber">Confirm installed hardware</Badge>}>
      <p className="panel-note">Choose the saved plan that represents your current setup. Compare resistor, active-stage and charging changes with this run’s alternatives. This is a planning aid.</p>
      <div className="planner-form">
        <label className="field">
          <span>Baseline saved run</span>
          <select
            value={baselineId}
            onChange={e => {
              setBaselineId(e.target.value);
              setError('');
            }}
          >
            <option value="">Choose a matching generator and layout</option>
            {compatible.map(r => (
              <option key={r.id} value={r.id}>
                {r.id} · {r.inputs.impulse_type} · {fmt(r.inputs.test_kv, 0)} kV
              </option>
            ))}
          </select>
          <small>{compatible.length} saved runs share this profile and layout.</small>
        </label>
        <label className="field">
          <span>Baseline candidate</span>
          <select
            value={candidateId}
            disabled={!baseline}
            onChange={e => {
              setCandidateId(e.target.value);
              setResult(null);
            }}
          >
            {!baseline && <option value="">Select a saved run first</option>}
            {baseline?.candidates.map((c: Data) => (
              <option key={c.id} value={c.id}>
                Rank {c.rank} · {c.settings.stages} stages · Rf {fmt(c.settings.front_r_stage, 2)} Ω · Rt {fmt(c.settings.tail_r_stage, 2)} Ω
              </option>
            ))}
          </select>
        </label>
        <button className="button primary" disabled={busy || !baseline || !candidateId} onClick={compare}>
          {busy ? <LoaderCircle className="spin" size={15} aria-hidden /> : <GitCompareArrows size={15} aria-hidden />} Compare setup changes
        </button>
      </div>
      {error && (
        <Notice tone="red" role="alert">
          {error}
        </Notice>
      )}
      {reviewed && (
        <div className="transition">
          <div className="transition-head">
            <strong>
              {reviewed.eligible_count} nominally passing options · original ranking retained
            </strong>
            <div className="heading-actions">
              <a className="button small" href={apiUrl(`/api/setup-transitions/${reviewed.id}/report`)} target="_blank" rel="noreferrer">
                <Download size={14} aria-hidden /> Printable change plan
              </a>
              <a className="button small ghost" href={apiUrl(`/api/setup-transitions/${reviewed.id}/json`)}>
                Audit JSON
              </a>
            </div>
          </div>
          <p className="panel-note">Preference: {reviewed.priority.join(' → ')}.</p>
          <Notice tone="neutral">{reviewed.review}</Notice>
          {displayed && model && (
            <div className="transition-visual">
              <div className="transition-scene">
                <GeneratorView model={model} view="overview" height={440} caption={`Saved baseline ${shortId(reviewed.baseline.run_id)} → rank ${displayed.original_rank} of run ${shortId(run.id)}`} />
              </div>
              <div className="transition-facts">
                <div className="transition-stages">
                  <div>
                    <span>Before</span>
                    <strong>{model.transition?.baselineStages}</strong>
                  </div>
                  <ArrowRight size={18} aria-hidden />
                  <div>
                    <span>After</span>
                    <strong>{model.transition?.targetStages}</strong>
                  </div>
                  <small>
                    +{model.transition?.added} newly active · −{model.transition?.deactivated} deactivated · charge {signed(displayed.charge_delta_kv_stage, 3)} kV/stage
                  </small>
                </div>
                {(['front', 'tail'] as const).map(role => {
                  const deltas = role === 'front' ? model.transition!.front : model.transition!.tail;
                  return (
                    <div className="transition-net" key={role}>
                      <strong>
                        {role === 'front' ? 'Front' : 'Tail'}: {model.transition!.baselineTopology[role]} → {model.transition!.targetTopology[role]}
                      </strong>
                      <ul>
                        {deltas.map(d => (
                          <li key={d.ohm}>
                            <span>{ohmText(d.ohm)}</span>
                            <span>
                              {d.before} → {d.after} per stage
                            </span>
                            <span className="delta-tags">
                              {d.retained > 0 && <Badge>{d.retained} kept</Badge>}
                              {d.added > 0 && <Badge tone="green">+{d.added} add</Badge>}
                              {d.removed > 0 && <Badge tone="red">−{d.removed} remove</Badge>}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
                <label className="field">
                  <span>Show option</span>
                  <select value={displayed.candidate_id} onChange={e => setShown(e.target.value)}>
                    {reviewed.options.map((o: Data) => (
                      <option key={o.candidate_id} value={o.candidate_id}>
                        Rank {o.original_rank}
                        {o.candidate_id === reviewed.closest_nominal_candidate_id ? ' · closest nominal' : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="field-help">Per-stage counts for shared stages come from the saved plans. Newly active and deactivated stage parts describe plans, not installation instructions.</p>
              </div>
            </div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Original rank</th>
                  <th>Nominal model / stock / rating checks</th>
                  <th className="num">Changed front/tail plans</th>
                  <th className="num">Stages added / deactivated</th>
                  <th className="num">Shared-stage part changes</th>
                  <th className="num">Charge Δ kV/stage</th>
                  <th>Separate challenge</th>
                  <th>Uncertainty</th>
                </tr>
              </thead>
              <tbody>
                {reviewed.options.map((o: Data) => (
                  <tr className={o.candidate_id === reviewed.closest_nominal_candidate_id ? 'highlight-row' : ''} key={o.candidate_id}>
                    <td>
                      <button className="link-button" onClick={() => setShown(o.candidate_id)} aria-pressed={displayed?.candidate_id === o.candidate_id}>
                        Rank {o.original_rank}
                      </button>{' '}
                      {o.candidate_id === reviewed.closest_nominal_candidate_id && <Badge tone="cyan">Closest nominal</Badge>}
                    </td>
                    <td>
                      {o.nominal_review.eligible_nominal ? 'Pass' : 'Review required'}
                      {o.nominal_review.reasons.map((reason: string) => (
                        <small className="block negative" key={reason}>
                          {reason}
                        </small>
                      ))}
                    </td>
                    <td className="num">{o.changed_network_families} / 2</td>
                    <td className="num">
                      {o.active_stages_added} / {o.active_stages_deactivated}
                    </td>
                    <td className="num">{o.shared_stage_part_changes}</td>
                    <td className="num">{signed(o.charge_delta_kv_stage, 3)}</td>
                    <td>{o.verification ? `${o.verification.passed}/${o.verification.total}` : 'Not recorded'}</td>
                    <td>
                      <Status value={o.uncertainty_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {closest && (
            <>
              <p className="panel-note">Closest nominal option: original rank {closest.original_rank}. Charge change {fmt(closest.charge_delta_pct, 2)}%. Model and challenge checks remain simulations.</p>
              <div className="bottom-grid">
                {Object.entries(closest.networks).map(([name, value]) => {
                  const network = value as Data;
                  return (
                    <div key={name} className="transition-detail">
                      <strong>
                        {name === 'front' ? 'Front' : 'Tail'}: {network.baseline_topology} → {network.target_topology}
                      </strong>
                      <p className="panel-note">{network.shared_stage_banks_to_review} shared-stage connection plans need review. Newly active and deactivated stage parts are shown separately in the printable plan.</p>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Value</th>
                              <th className="num">Before /stage</th>
                              <th className="num">After /stage</th>
                              <th className="num">Retained shared</th>
                              <th className="num">Added shared</th>
                              <th className="num">Removed shared</th>
                            </tr>
                          </thead>
                          <tbody>
                            {network.parts.map((part: Data) => (
                              <tr key={part.ohm}>
                                <td>{fmt(part.ohm, 2)} Ω</td>
                                <td className="num">{part.baseline_per_stage}</td>
                                <td className="num">{part.target_per_stage}</td>
                                <td className="num">{part.retained_on_shared_stages}</td>
                                <td className="num">{part.added_on_shared_stages}</td>
                                <td className="num">{part.removed_from_shared_stages}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                className="button text-button"
                onClick={() => {
                  setSelected(run.candidates.findIndex((c: Data) => c.id === closest.candidate_id));
                  router.push('/');
                }}
              >
                Inspect closest nominal option <ArrowRight size={14} aria-hidden />
              </button>
            </>
          )}
          <p className="panel-note">{reviewed.scope}</p>
        </div>
      )}
    </Panel>
  );
}
