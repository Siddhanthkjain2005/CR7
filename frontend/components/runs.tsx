'use client';
import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowDownToLine, ArrowRight, FileText, History, RefreshCw} from 'lucide-react';
import {api, apiUrl, Data, fmt, human, shortId, stamp} from '@/lib/api';
import {Badge, Empty, Notice, PageHeading, Panel, Skeleton, Status} from './ui';
import {useWorkspace} from './workspace';
import {AgreementEvidence, NominalEvidence, VerificationEvidence} from './run-evidence';

export function Runs() {
  const {loadRun, busy, error, run} = useWorkspace();
  const router = useRouter();
  const [records, setRecords] = useState<Data[]>([]),
    [failure, setFailure] = useState(''),
    [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(''),
    [impulse, setImpulse] = useState('all'),
    [evidenceFilter, setEvidenceFilter] = useState('all');
  async function refresh() {
    setLoading(true);
    try {
      setRecords(await api('/api/runs'));
      setFailure('');
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  const filtered = records.filter(r => {
    const v = r.evidence?.verification;
    const matchesEvidence =
      evidenceFilter === 'all' ||
      (evidenceFilter === 'checked-pass' && v?.all_checks_pass === true) ||
      (evidenceFilter === 'checked-fail' && v?.all_checks_pass === false) ||
      (evidenceFilter === 'unrecorded' && !v);
    const text = [r.id, r.profile, r.inputs?.impulse_type, r.inputs?.test_kv, r.model_version, r.status].join(' ').toLowerCase();
    return text.includes(query.trim().toLowerCase()) && (impulse === 'all' || r.inputs?.impulse_type === impulse) && matchesEvidence;
  });
  const challenged = records.filter(r => r.evidence?.verification);
  const inspect = async (id: string) => {
    await loadRun(id);
    router.push('/');
  };
  return (
    <>
      <PageHeading
        tag="Engineering"
        title="Run history"
        description="Every saved recommendation with its model checks and uncertainty status. Restoring a run never reruns or changes it."
        action={
          <button className="button small" onClick={refresh} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} aria-hidden /> Refresh
          </button>
        }
      />
      {(failure || error) && (
        <Notice tone="red" role="alert" title="Saved runs could not be read">
          {failure || error}
        </Notice>
      )}
      <div className="counts">
        <div className="count">
          <span>Loaded runs</span>
          <strong>{records.length}</strong>
          <small>Up to the 100 most recent saved runs</small>
        </div>
        <div className="count">
          <span>All post-ranking checks pass</span>
          <strong>
            {challenged.filter(r => r.evidence.verification.all_checks_pass).length}
            <small> / {challenged.length} checked</small>
          </strong>
          <small>Finite simulations · not measured accuracy</small>
        </div>
        <div className="count">
          <span>Challenge not recorded</span>
          <strong>{records.length - challenged.length}</strong>
          <small>Earlier runs keep their original evidence</small>
        </div>
      </div>
      <div className="history-filters">
        <label className="field">
          <span>Find a saved run</span>
          <input type="search" placeholder="Run ID, profile, model or voltage" value={query} onChange={e => setQuery(e.target.value)} />
        </label>
        <label className="field">
          <span>Impulse type</span>
          <select value={impulse} onChange={e => setImpulse(e.target.value)}>
            <option value="all">All impulse types</option>
            <option>Lightning</option>
            <option>Switching</option>
          </select>
        </label>
        <label className="field">
          <span>Post-ranking challenge</span>
          <select value={evidenceFilter} onChange={e => setEvidenceFilter(e.target.value)}>
            <option value="all">All evidence</option>
            <option value="checked-pass">All checks pass</option>
            <option value="checked-fail">Limits exceeded</option>
            <option value="unrecorded">Not recorded</option>
          </select>
        </label>
      </div>
      <Panel title="Saved engineering runs" action={<Badge>{filtered.length} of {records.length} loaded</Badge>}>
        {loading && !records.length ? (
          <Skeleton lines={5} />
        ) : !records.length ? (
          <Empty title="No saved runs yet" icon={<History size={26} />}>
            Complete an optimization to create a reproducible audit record.
          </Empty>
        ) : !filtered.length ? (
          <Empty title="No runs match these filters">Change the search or evidence filter to see more loaded runs.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="run-table">
              <thead>
                <tr>
                  <th>Run and saved time</th>
                  <th>Test and source</th>
                  <th>Primary nominal</th>
                  <th>Model agreement</th>
                  <th>Post-ranking challenge</th>
                  <th>Uncertainty envelope</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => {
                  const ev = r.evidence || {};
                  const current = run?.id === r.id;
                  return (
                    <tr key={r.id} className={current ? 'highlight-row' : ''}>
                      <td>
                        <code>{r.id}</code> {current && <Badge tone="cyan">Loaded</Badge>}
                        <small className="block">{stamp(r.created_at)}</small>
                        <small className="block">{r.model_version || 'Model version not recorded'}</small>
                      </td>
                      <td>
                        <strong>
                          {r.inputs?.impulse_type} · {fmt(r.inputs?.test_kv, 0)} kV
                        </strong>
                        <small className="block">{r.profile}</small>
                        <small className="block">{(r.inputs?.solver || 'reference') === 'reference' ? 'Reference model' : 'Equivalent circuit'}</small>
                      </td>
                      <td>
                        <NominalEvidence value={ev.primary_nominal_pass} />
                      </td>
                      <td>
                        <AgreementEvidence agreement={ev.agreement} solver={r.inputs?.solver || 'reference'} />
                      </td>
                      <td>
                        <VerificationEvidence verification={ev.verification} />
                        {ev.verification && (
                          <small className="block">
                            Limit margin: {typeof ev.verification.minimum_margin_fraction === 'number' ? `${fmt(ev.verification.minimum_margin_fraction * 100, 1)}%` : 'Not recorded'}
                            {typeof ev.verification.unique_scenarios === 'number' && ` · ${ev.verification.unique_scenarios} distinct`}
                          </small>
                        )}
                      </td>
                      <td>
                        <Status value={r.status} />
                        <small className="block">ML: {ev.ml_support ? human(ev.ml_support) : 'Not recorded'}</small>
                        {ev.calibration_source && <small className="block">{ev.lab_calibrated ? 'Scoped laboratory correction' : 'Synthetic calibration'} · not validation</small>}
                      </td>
                      <td>
                        <div className="table-actions">
                          <button className="button small" disabled={busy} onClick={() => inspect(r.id)} aria-label={`Restore run ${shortId(r.id)} in the optimizer`}>
                            Restore <ArrowRight size={13} aria-hidden />
                          </button>
                          <a className="icon-button" aria-label={`Open report for run ${r.id}`} title="Engineering report" href={apiUrl(`/api/runs/${r.id}/report`)} target="_blank" rel="noreferrer">
                            <FileText size={15} />
                          </a>
                          <a className="icon-button" aria-label={`Download JSON for run ${r.id}`} title="Audit JSON" href={apiUrl(`/api/runs/${r.id}/json`)}>
                            <ArrowDownToLine size={15} />
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="panel-note">
          Passing nominal or sampled checks does not establish laboratory accuracy. MARGINAL can remain when the uncertainty envelope exceeds a limit. “Not recorded” means the saved run has no such evidence; refreshing this list does not rerun it. Limit margin is the remaining fraction of the allowed half-range.
        </p>
      </Panel>
    </>
  );
}
