"use client";
import { ArrowUpRight } from "lucide-react";
import { apiUrl, Data, fmt } from "@/lib/api";
import { Badge, Panel } from "./ui";

function CrestStudy({ study, version, description }: { study: Data; version: string; description: string }) {
  return (
    <Panel
      title={`Switching crest · ${version.toUpperCase()} focused study`}
      eyebrow="Repeated nested development comparison"
      action={<Badge tone="amber">{study.promotion_eligible ? "Independent check needed" : "Gate not met · serving unchanged"}</Badge>}
    >
      <p className="panel-note">{description} Each of three fold arrangements reserves its own held rows.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repeated development comparison</th>
              <th>RMSE (kV)</th>
              <th>95th percentile error (kV)</th>
              <th>Worst error (kV)</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(study.combined_repeated_development_metrics || {}).map(([name, m]: [string, any]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{fmt(m.rmse_kv, 5)}</td>
                <td>{fmt(m.p95_absolute_error_kv, 5)}</td>
                <td>{fmt(m.worst_absolute_error_kv, 5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="panel-note">
        The search beat both baselines in {study.folds_beating_both_baselines} / 15 folds. The fixed gate requires at least 2% lower error against
        both baselines in every fold arrangement. {study.decision}
      </p>
      <p className="panel-note">{study.scope}</p>
      <a className="button text-button" href={apiUrl(`/api/documents/accuracy_${version}_results`)} target="_blank" rel="noreferrer">
        Read the {version.toUpperCase()} crest study <ArrowUpRight size={14} />
      </a>
    </Panel>
  );
}

export default function BenchmarkComparison({ data }: { data: Data }) {
  const saved = data.benchmark_scorecard;
  if (!saved) return null;
  const frozen = saved.frozen_v1?.comparisons || [];
  const physics = frozen.find((c: Data) => c.baseline === "Physics only");
  const knn = frozen.find((c: Data) => c.baseline === "Exact workbook kNN");
  const development = saved.development_v2?.comparisons?.find((c: Data) => c.baseline === "Matched exact kNN");
  const numerical = data.independent_circuit_verification;
  return (
    <>
      <Panel
        title="Which baseline do the six outputs beat?"
        eyebrow="Saved results from different evaluations; counts are not additive"
        action={<Badge>Lower RMSE counts</Badge>}
      >
        <div className="facts">
          <div>
            <span>V1 · frozen test vs physics</span>
            <strong>{physics?.lower_error_targets ?? "—"} / 6</strong>
            <small>Outputs with lower error</small>
          </div>
          <div>
            <span>V1 · frozen test vs workbook kNN</span>
            <strong>{knn?.lower_error_targets ?? "—"} / 6</strong>
            <small>Switching crest remains higher</small>
          </div>
          <div>
            <span>V2 · development CV vs workbook kNN</span>
            <strong>{development?.lower_error_targets ?? "—"} / 6</strong>
            <small>Experimental · separate from the test</small>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Frozen V1 output</th>
                <th>V1 RMSE</th>
                <th>Workbook kNN RMSE</th>
                <th>Compared with workbook</th>
              </tr>
            </thead>
            <tbody>
              {knn?.targets?.map((row: Data) => (
                <tr key={`${row.impulse_type}-${row.target}`}>
                  <td>
                    {row.impulse_type} · {row.target}
                  </td>
                  <td>
                    {fmt(row.model_rmse, 5)} {row.unit}
                  </td>
                  <td>
                    {fmt(row.baseline_rmse, 5)} {row.unit}
                  </td>
                  <td className={row.verdict === "LOWER ERROR" ? "positive" : row.verdict === "HIGHER ERROR" ? "negative" : "muted"}>
                    {row.verdict === "NOT RECORDED"
                      ? "Not recorded"
                      : row.verdict === "TIE"
                        ? "Equal error"
                        : `${fmt(Math.abs(row.rmse_reduction_pct), 2)}% ${row.verdict === "LOWER ERROR" ? "lower" : "higher"} error`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-note">
          These counts compare error across six outputs; they are not percentages of correct shots. V2’s 6 / 6 result uses development folds and does
          not change V1’s saved test result. {saved.frozen_v1?.scope}
        </p>
      </Panel>
      {numerical && (
        <Panel
          title="CPRI circuit · independent numerical verification"
          eyebrow="Generated simulation of the same assumed topology; not ML accuracy or laboratory validation"
          action={
            <Badge tone="cyan">
              {numerical.passing_channels} / {numerical.expected_channels} numerical checks
            </Badge>
          }
        >
          <p className="panel-note">
            A separate charge/flux integrator generated {numerical.requested_cases} cases using Radau, BDF and tighter-tolerance refinement. All{" "}
            {numerical.reference_accepted_cases} references passed convergence and passive-energy checks. Forty fixed evaluation cases per impulse
            type compare the app’s modal solver with those references.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Numerical channel</th>
                  <th>Available / requested</th>
                  <th>95th percentile difference</th>
                  <th>Worst difference</th>
                  <th>Fixed agreement gate</th>
                </tr>
              </thead>
              <tbody>
                {numerical.channels.map((row: Data) => (
                  <tr key={`${row.impulse_type}-${row.metric}`}>
                    <td>
                      {row.impulse_type} ·{" "}
                      {row.metric === "front_us"
                        ? row.impulse_type === "Lightning"
                          ? "Front time"
                          : "Time to peak"
                        : row.metric === "tail_us"
                          ? "Tail time"
                          : "Crest voltage"}
                    </td>
                    <td>
                      {row.accepted_prediction_cases} / {row.requested_evaluation_cases}
                    </td>
                    <td>{row.p95_relative_error_pct == null ? "Unavailable" : `${Number(row.p95_relative_error_pct).toExponential(2)}%`}</td>
                    <td>{row.worst_relative_error_pct == null ? "Unavailable" : `${Number(row.worst_relative_error_pct).toExponential(2)}%`}</td>
                    <td>{row.numerical_agreement_pass ? "Met" : "Not met"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="panel-note">
            {numerical.scope} No model weights changed. Unknown hardware topology, parasitics and inventory remain explicit assumptions.
          </p>
          <a className="button text-button" href={apiUrl("/api/documents/independent_simulation_results")} target="_blank" rel="noreferrer">
            Read the numerical verification <ArrowUpRight size={14} />
          </a>
        </Panel>
      )}
      {data.experiment_v6 && (
        <CrestStudy
          study={data.experiment_v6}
          version="v6"
          description="The study compares smooth relative corrections, voltage-weighted fits and local residual averaging against both V2 and exact workbook kNN."
        />
      )}
      {data.experiment_v7 && (
        <CrestStudy
          study={data.experiment_v7}
          version="v7"
          description="The follow-up compares regularized spline envelopes, quantile centers and Bayesian fits against the same baselines and a fixed compact spline control. Observed extremes are not proven noise bounds."
        />
      )}
    </>
  );
}
