import { Data, fmt } from "@/lib/api";

const LABELS: Record<string, string> = { physics: "Physics", original_model: "Original model", recorded_prediction: "Saved prediction" };
function rateText(rate: Data) {
  return rate?.pct == null ? "Not estimable · no eligible cases" : `${rate.numerator} / ${rate.denominator} · ${fmt(rate.pct, 1)}%`;
}

export default function TrialDecisionEvidence({ group }: { group: Data }) {
  const decisions = group.decisions;
  if (!decisions) return <p className="panel-note">This earlier review has no saved decision-error counts.</p>;
  const saved = decisions.models.recorded_prediction,
    envelope = decisions.saved_envelope;
  const worst = group.metrics.recorded_prediction.worst_case;
  return (
    <div className="trial-quality">
      <strong>Did a predicted PASS survive the measured shot?</strong>
      <p className="panel-note">
        A false PASS means the predicted waveform is within all limits while the extracted measured waveform is outside at least one. A false FAIL is
        the reverse. These counts use the rules saved with each prediction: {group.context.rules_id} · {group.context.rules_version}.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Prediction</th>
              <th>True PASS</th>
              <th>False PASS</th>
              <th>False FAIL</th>
              <th>True FAIL</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(decisions.models).map(([name, d]: [string, any]) => (
              <tr key={name}>
                <td>{LABELS[name] || name}</td>
                <td>{d.true_pass}</td>
                <td className={d.false_pass ? "negative" : ""}>{d.false_pass}</td>
                <td>{d.false_fail}</td>
                <td>{d.true_fail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="panel-note">
        Saved prediction · false PASS among measured failures: <strong>{rateText(saved.false_pass_among_measured_failures)}</strong>. Measured failure
        among predicted passes: <strong>{rateText(saved.measured_fail_among_predicted_passes)}</strong>. False FAIL among measured passes:{" "}
        <strong>{rateText(saved.false_fail_among_measured_passes)}</strong>.
      </p>
      {!saved.both_measured_outcomes_present && (
        <p className="alert compact">
          This group does not contain both measured PASS and FAIL outcomes. It cannot establish performance on the missing outcome class.
        </p>
      )}
      {worst && (
        <p className="panel-note">
          Largest saved-prediction error: <strong>{fmt(worst.normalized_error_tolerance, 3)} × tolerance half-width</strong> ·{" "}
          {worst.metric === "crest_kv" ? "crest" : worst.metric === "tail_us" ? "tail" : "front / peak"} · capture {worst.trial_id}. This identifies
          the worst observed miss, not a limit on future error.
        </p>
      )}
      {envelope && (
        <p className="panel-note">
          Saved prediction envelopes: {envelope.state_counts.contained} contained, {envelope.state_counts.overlaps} overlapping,{" "}
          {envelope.state_counts.outside} outside and {envelope.state_counts.unavailable} unavailable. Measured failures among contained envelopes:{" "}
          {rateText(envelope.measured_fail_among_contained_envelopes)}. Envelope containment is separate from nominal decisions and hardware approval.
        </p>
      )}
    </div>
  );
}
