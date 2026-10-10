"use client";
import { useEffect, useState } from "react";
import { Download, FileCheck2, LoaderCircle, RefreshCw } from "lucide-react";
import { api, apiUrl, Data, fmt, post } from "@/lib/api";
import { Badge, Panel } from "./ui";
import TrialDecisionEvidence from "./trial-decision-evidence";

export default function TrialEvaluator({ refreshToken }: { refreshToken?: string }) {
  const [trials, setTrials] = useState<Data[]>([]),
    [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<Data | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function refresh() {
    try {
      setTrials(await api("/api/trials"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    refresh();
  }, [refreshToken]);
  const lab = trials.filter((t) => t.source_type === "measured_lab");
  async function evaluate() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await post("/api/evaluations", { trial_ids: selected }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="4 · Independent evaluation on new measured shots" action={<Badge tone="amber">Measured evidence required</Badge>}
      className="evaluator">
      <p className="panel-note">
        Select at least three new laboratory captures. We compare predictions saved before upload with their measured values, without fitting a
        correction to these shots. Repeated imports and calibration-source waveforms cannot count as new evidence.
      </p>
      <div className="heading-actions">
        <span className="panel-note">
          {lab.length} laboratory uploads · {trials.length - lab.length} synthetic uploads excluded · up to 50 recent uploads
        </span>
        <button className="button small" onClick={refresh}>
          <RefreshCw size={14} /> Refresh captures
        </button>
      </div>
      {error && (
        <div role="alert" className="alert error">
          {error}
        </div>
      )}
      {lab.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Select</th>
                <th>Capture / saved setup</th>
                <th>Measured front / peak</th>
                <th>Measured tail</th>
                <th>Measured crest</th>
                <th>Capture review</th>
              </tr>
            </thead>
            <tbody>
              {lab.map((t) => (
                <tr key={t.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Include laboratory capture ${t.id}`}
                      checked={selected.includes(t.id)}
                      disabled={t.quality?.calibration_allowed === false}
                      onChange={(e) => setSelected(e.target.checked ? [...selected, t.id] : selected.filter((id) => id !== t.id))}
                    />
                  </td>
                  <td>
                    {t.id}
                    <small className="block">
                      Run {t.run_id} · {t.candidate_id}
                    </small>
                  </td>
                  <td>{fmt(t.measured.front_us, 3)} µs</td>
                  <td>{fmt(t.measured.tail_us, 3)} µs</td>
                  <td>{fmt(t.measured.crest_kv, 3)} kV</td>
                  <td>
                    {t.quality?.calibration_allowed === false ? "Review required" : t.quality ? "Basic checks passed" : "Rechecked before scoring"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="panel-note">
          No laboratory captures are available yet. Upload actual analyzer CSVs above and mark their provenance accurately. Synthetic demo results do
          not establish laboratory accuracy.
        </p>
      )}
      <button className="button primary" disabled={busy || selected.length < 3} onClick={evaluate}>
        {busy ? <LoaderCircle className="spin" size={15} /> : <FileCheck2 size={15} />} Score {selected.length} selected new shots
      </button>
      {result && (
        <div className="trial-quality">
          <div className="heading-actions">
            <strong>Saved accuracy review · {result.trial_count} captures</strong>
            <a className="button secondary" href={apiUrl(`/api/evaluations/${result.id}/json`)}>
              <Download size={14} /> Download evidence
            </a>
          </div>
          <p className="panel-note">{result.scope}</p>
          {result.groups.map((group: Data, index: number) => (
            <div className="trial-quality" key={index}>
              <strong>
                {group.context.impulse_type} · {group.sample_count} captures
              </strong>
              <p className="panel-note">
                {group.context.profile_id} · Layout {group.context.layout_id} · {group.context.solver} · {group.context.model_version}
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Physics RMSE</th>
                      <th>Original model RMSE</th>
                      <th>Saved prediction RMSE</th>
                      <th>Saved prediction MAPE</th>
                      <th>Error reduction vs physics</th>
                    </tr>
                  </thead>
                  <tbody>
                    {["Front / peak", "Tail", "Crest"].map((label, i) => (
                      <tr key={label}>
                        <td>
                          {label} · {group.units[i]}
                        </td>
                        <td>{fmt(group.metrics.physics.rmse[i], 4)}</td>
                        <td>{fmt(group.metrics.original_model.rmse[i], 4)}</td>
                        <td>{fmt(group.metrics.recorded_prediction.rmse[i], 4)}</td>
                        <td>{fmt(group.metrics.recorded_prediction.mape_pct[i], 2)}%</td>
                        <td>
                          {group.metrics.recorded_prediction.rmse_reduction_vs_physics_pct[i] === null
                            ? "Undefined: zero baseline error"
                            : `${fmt(group.metrics.recorded_prediction.rmse_reduction_vs_physics_pct[i], 2)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="panel-note">
                Positive reduction means lower error; negative values remain visible. Original model excludes the applied local bias; saved prediction
                includes it when present. {group.sample_note}
              </p>
              <TrialDecisionEvidence group={group} />
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
