"use client";
import { SourceBadge } from "./evidence-pages";
import { Data, fmt } from "@/lib/api";
import { Badge } from "./ui";

export default function TrialQuality({ trial }: { trial: Data }) {
  const q = trial.quality,
    lineage = trial.calibration_lineage;
  return (
    <div className="trial-quality">
      <SourceBadge trial={trial} />
      <div className="heading-actions">
        <strong>Waveform identity</strong>
        <Badge tone={trial.provenance?.setup_identity === "matched_export" ? "cyan" : "neutral"}>
          {trial.provenance?.setup_identity === "matched_export" ? "Export matches setup" : "Operator-selected setup"}
        </Badge>
      </div>
      <p className="panel-note">
        {trial.provenance?.setup_identity === "matched_export"
          ? "The CSV’s recorded run, candidate and units match this upload."
          : "Confirm that the uploaded shot used this run’s selected hardware and units."}
      </p>
      <div className="heading-actions">
        <strong>Waveform capture review</strong>
        <Badge tone={!q ? "amber" : q.calibration_allowed ? "cyan" : "red"}>
          {!q ? "Not recorded" : q.calibration_allowed ? "Basic checks passed" : "Review capture"}
        </Badge>
      </div>
      {q ? (
        <>
          <p className="panel-note">
            {q.metrics.sample_count} samples · {q.metrics.rising_intervals_30_90} intervals across the 30–90% rise (minimum{" "}
            {q.metrics.minimum_rising_intervals}).
          </p>
          {q.metrics.peak_neighbor_span_us != null && (
            <p className="panel-note">
              Acquired crest-neighbor span: {fmt(q.metrics.peak_neighbor_span_us, 4)} µs (review limit{" "}
              {fmt(q.metrics.maximum_peak_neighbor_span_us, 4)} µs). Falling half-value bracket: {fmt(q.metrics.half_value_bracket_span_us, 4)} µs
              (review limit {fmt(q.metrics.maximum_half_value_bracket_span_us, 4)} µs).
            </p>
          )}
          {q.evaluation_allowed === false && (
            <p className="alert compact">
              Extracted values are provisional. A nominal value inside the limits cannot count as accepted measurement evidence until capture
              resolution is reviewed.
            </p>
          )}
          {q.evaluation_allowed == null && (
            <p className="panel-note">
              This earlier capture review predates the crest and tail resolution checks. The stored waveform is rechecked before calibration or
              scoring.
            </p>
          )}
          {!!q.issues.length && (
            <ul className="notes-list">
              {q.issues.map((issue: Data) => (
                <li key={issue.code}>{issue.message}</li>
              ))}
            </ul>
          )}
          <p className="panel-note">{q.scope}</p>
        </>
      ) : (
        <p className="panel-note">
          This older upload has no saved capture review. Its stored waveform will be checked before creating a new calibration.
        </p>
      )}
      {lineage?.parent_calibration_id && (
        <>
          <div className="heading-actions">
            <strong>Repeated-shot correction</strong>
            <Badge>Parent {lineage.parent_calibration_id}</Badge>
          </div>
          <p className="panel-note">
            The new residual is added to the correction already applied. The total below is relative to the original model.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Previous correction</th>
                  <th>New residual</th>
                  <th>Total correction</th>
                </tr>
              </thead>
              <tbody>
                {["Front / peak µs", "Tail µs", "Crest kV"].map((label, i) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>{fmt(lineage.prior_applied_bias[i], 4)}</td>
                    <td>{fmt(trial.bias[i], 4)}</td>
                    <td>{fmt(trial.calibration_bias[i], 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
