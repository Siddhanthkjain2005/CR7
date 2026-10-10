"use client";
import { Data, fmt } from "@/lib/api";
import { Badge, Panel } from "./ui";

export default function SettingsVerification({ candidate }: { candidate: Data }) {
  const v = candidate.verification;
  if (!v) return null;
  const w = v.worst_case;
  return (
    <Panel
      title="Fixed-setting challenge"
      eyebrow="Extra simulated scenarios run after ranking, with the hardware held fixed"
      action={<Badge tone={v.all_checks_pass ? "green" : "red"}>{v.all_checks_pass ? "All sampled checks pass" : "Limit exceeded"}</Badge>}
    >
      <p className="panel-note">
        These extra checks run after the settings are ranked. They do not influence which setup wins the search.{" "}
        {v.models_checked.length === 2 ? "Both the reference prediction and independent circuit must pass." : "The circuit prediction must pass."}
      </p>
      <div className="verification-cards">
        <div>
          <span>New parasitic samples</span>
          <strong>
            {v.fresh_samples.passed}
            <small> / {v.fresh_samples.total}</small>
          </strong>
          <p>Separate sampling seed</p>
        </div>
        <div>
          <span>Boundary corners</span>
          <strong>
            {v.boundary_corners.passed}
            <small> / {v.boundary_corners.total}</small>
          </strong>
          <p>All combinations at ±{v.uncertainty_pct}%</p>
        </div>
        <div>
          <span>Smallest limit margin</span>
          <strong className={w.minimum_margin_fraction >= 0 ? "positive" : "negative"}>
            {fmt(w.minimum_margin_fraction * 100, 1)}
            <small>%</small>
          </strong>
          <p>Fraction of the allowed half-range</p>
        </div>
      </div>
      <div className="verification-worst">
        <div>
          <Badge tone={w.all_models_pass ? "cyan" : "red"}>Most limiting scenario</Badge>
          <h3>
            {w.limiting_metric} · {w.limiting_model}
          </h3>
          <p>
            <strong>
              {fmt(w.predicted, 3)} {w.unit}
            </strong>{" "}
            · allowed {fmt(w.allowed_lower, 3)}–{fmt(w.allowed_upper, 3)} {w.unit}
          </p>
        </div>
        <dl>
          {[
            ["load_c_pf", "Object C", "pF"],
            ["divider_c_pf", "Divider C", "pF"],
            ["stray_c_pf", "Stray C", "pF"],
            ["l_uh", "Inductance", "µH"],
          ].map(([k, label, unit]) => (
            <div key={k}>
              <dt>{label}</dt>
              <dd>
                {fmt(w.inputs[k], 2)} {unit}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="panel-note">
        {v.unique_scenarios} distinct scenarios. {v.scope} The uncertainty-envelope status remains <strong>{candidate.compliance.status}</strong>.
      </p>
    </Panel>
  );
}
