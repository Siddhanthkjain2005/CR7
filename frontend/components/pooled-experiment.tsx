import { ArrowUpRight, FlaskConical } from "lucide-react";
import { apiUrl, Data, fmt } from "@/lib/api";
import { Badge, Panel } from "./ui";

export default function PooledExperiment({ experiment }: { experiment: Data }) {
  return (
    <Panel title="Accuracy search · shared patterns" eyebrow="Train development study" action={<Badge tone="amber">V4 · no promotion</Badge>}>
      <div className="experiment-method-note">
        <FlaskConical size={17} />
        <div>
          <p>
            Tested {experiment.candidate_count} ways to share relative corrections between Lightning and Switching. Both impulse types’ held-out
            examples stayed outside each shared model’s training. No pooled candidate met the inner selection gate; the V2 comparator was retained for
            all six outputs.
          </p>
          <p>
            <strong>{fmt(experiment.macro_improvement_pct, 2)}% additional error reduction.</strong> The default V1 and optional V2 remain unchanged.
          </p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Impulse / output</th>
              <th>V2 refit RMSE</th>
              <th>V4 search RMSE</th>
              <th>Unit</th>
            </tr>
          </thead>
          <tbody>
            {["Lightning", "Switching"].flatMap((type) => {
              const metrics = experiment.nested_cv?.[type]?.metrics;
              return [type === "Lightning" ? "Front time" : "Peak time", "Tail time", "Crest voltage"].map((label, j) => (
                <tr key={`${type}-${j}`}>
                  <td>
                    {type} · {label}
                  </td>
                  <td>{fmt(metrics?.["Historical V2 refit"]?.rmse?.[j], 5)}</td>
                  <td>{fmt(metrics?.["V4 pooling search"]?.rmse?.[j], 5)}</td>
                  <td>{j === 2 ? "kV" : "µs"}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
      <p className="panel-note">
        {experiment.scope} Calibration, Validation and Hidden Test outcomes were not evaluated. This result does not establish an irreducible error
        floor.
      </p>
      <div className="heading-actions">
        <a className="button small" href={apiUrl("/api/documents/accuracy_v4_results")} target="_blank" rel="noreferrer">
          Read method and result <ArrowUpRight size={13} />
        </a>
        <a className="button text-button small" href={apiUrl(`/api/models/${experiment.version}/metrics`)} target="_blank" rel="noreferrer">
          Open saved evidence <ArrowUpRight size={13} />
        </a>
      </div>
    </Panel>
  );
}
