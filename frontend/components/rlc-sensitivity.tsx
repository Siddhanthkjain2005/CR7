"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Download, Play, SlidersHorizontal } from "lucide-react";
import { Data, fmt, post, apiUrl } from "@/lib/api";
import { Badge, Panel } from "./ui";
import EngineeringChart from "./engineering-chart";

const parameters = [
  ["front_r_stage", "R · Front resistance / stage"],
  ["tail_r_stage", "R · Tail resistance / stage"],
  ["load_c_pf", "C · Test-object capacitance"],
  ["divider_c_pf", "C · Divider capacitance"],
  ["stray_c_pf", "C · Stray capacitance"],
  ["l_uh", "L · Connection inductance"],
];

export default function RlcSensitivity({ run, candidate }: { run: Data; candidate: Data }) {
  const [parameter, setParameter] = useState("load_c_pf"),
    [change, setChange] = useState("10");
  const [modelId, setModelId] = useState(run.inputs.solver),
    [front, setFront] = useState(false);
  const [result, setResult] = useState<Data | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const requestNumber = useRef(0);
  useEffect(() => {
    requestNumber.current++;
    setResult(null);
    setError("");
    setBusy(false);
    setModelId(run.inputs.solver);
  }, [run.id, candidate.id, run.inputs.solver]);
  const changePct = Number(change);
  const valid = change !== "" && Number.isFinite(changePct) && changePct >= -30 && changePct <= 30;
  const reviewed =
    valid &&
    result?.run_id === run.id &&
    result?.candidate_id === candidate.id &&
    result?.parameter.key === parameter &&
    result?.parameter.requested_change_pct === changePct
      ? result
      : null;
  const model = reviewed?.models.find((m: Data) => m.id === modelId);
  const preview = async () => {
    if (!valid) return;
    const ticket = ++requestNumber.current;
    setBusy(true);
    setError("");
    try {
      const r = await post(`/api/runs/${run.id}/candidates/${candidate.id}/sensitivity`, { parameter, change_pct: changePct });
      if (ticket === requestNumber.current) setResult(r);
    } catch (e) {
      if (ticket === requestNumber.current) {
        setResult(null);
        setError((e as Error).message);
      }
    } finally {
      if (ticket === requestNumber.current) setBusy(false);
    }
  };
  return (
    <Panel
      id="rlc-sensitivity"
      title="Explore R, L and C"
      eyebrow="One declared parameter at a time, −30% to +30%; stages, charge and efficiency stay fixed"
      className="sensitivity-panel"
      action={<Badge tone="cyan">Raw physics comparison</Badge>}
    >
      <p className="panel-note">
        Vary one value around saved run {run.id}, rank {candidate.rank}. Active stages, charging voltage and efficiency stay fixed. This view explains
        the models; it does not change the recommendation.
      </p>
      <div className="sensitivity-layout">
        <form
          className="sensitivity-controls"
          onSubmit={(e) => {
            e.preventDefault();
            void preview();
          }}
        >
          <label className="field">
            <span>Parameter to vary</span>
            <select value={parameter} onChange={(e) => setParameter(e.target.value)}>
              {parameters.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Change from saved value (%)</span>
            <input required type="number" min={-30} max={30} step="any" value={change} onChange={(e) => setChange(e.target.value)} />
          </label>
          <input
            aria-label="Parameter percentage slider"
            type="range"
            min={-30}
            max={30}
            step={1}
            value={valid ? changePct : 0}
            onChange={(e) => setChange(e.target.value)}
          />
          <div className="sensitivity-shortcuts">
            {[-10, 0, 10].map((value) => (
              <button type="button" key={value} onClick={() => setChange(String(value))}>
                {value === 0 ? "Reset" : `${value > 0 ? "+" : ""}${value}%`}
              </button>
            ))}
          </div>
          <button className="button primary full" disabled={busy || !valid} type="submit">
            <Play size={14} />
            {busy ? "Computing preview…" : "Preview one change"}
          </button>
          <dl>
            <div>
              <dt>Fixed active stages</dt>
              <dd>{candidate.settings.stages}</dd>
            </div>
            <div>
              <dt>Fixed charge / stage</dt>
              <dd>{fmt(candidate.settings.charge_kv_stage, 2)} kV</dd>
            </div>
            <div>
              <dt>Fixed efficiency</dt>
              <dd>{fmt(run.inputs.efficiency, 3)}</dd>
            </div>
          </dl>
          <p className="muted">No ML residual or trial correction is applied. Both curves use raw physics.</p>
        </form>
        <div className="sensitivity-output">
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
          {!reviewed ? (
            <div className="sensitivity-empty">
              <SlidersHorizontal size={28} />
              <h3>See which part of the impulse moves</h3>
              <p>
                Choose R, L or C and preview its effect on front / peak time, tail and crest. Compare the workbook equations with the lumped circuit
                at the same values.
              </p>
            </div>
          ) : (
            <>
              <div className="sensitivity-summary">
                <div>
                  <span>{reviewed.parameter.label}</span>
                  <strong>
                    {fmt(reviewed.parameter.baseline_value, 3)} <ArrowRight size={14} /> {fmt(reviewed.parameter.variant_value, 3)}{" "}
                    <small>{reviewed.parameter.unit}</small>
                  </strong>
                </div>
                <a className="button small" href={apiUrl(`/api/sensitivity/${reviewed.id}/json`)}>
                  <Download size={14} /> Preview audit JSON
                </a>
              </div>
              {reviewed.resistor_plan_requires_new_search && (
                <div className="alert compact">
                  Hypothetical resistance: this value has no counted stock construction. A new optimization is required to obtain a component plan.
                </div>
              )}
              {!reviewed.parameter.value_changed && (
                <div className="alert compact">
                  The chosen value is unchanged.{reviewed.parameter.baseline_value === 0 ? " A percentage change leaves a zero input at zero." : ""}
                </div>
              )}
              <div className="sensitivity-toolbar">
                <div className="segmented">
                  {reviewed.models.map((m: Data) => (
                    <button
                      key={m.id}
                      type="button"
                      aria-pressed={m.id === modelId}
                      className={m.id === modelId ? "active" : ""}
                      onClick={() => setModelId(m.id)}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <div className="segmented">
                  <button type="button" className={!front ? "active" : ""} onClick={() => setFront(false)}>
                    Full wave
                  </button>
                  <button type="button" className={front ? "active" : ""} onClick={() => setFront(true)}>
                    Front / peak detail
                  </button>
                </div>
              </div>
              {model?.available ? (
                <>
                  {model.baseline.waveform && model.variant.waveform ? (
                    <EngineeringChart
                      waveform={model.variant.waveform}
                      physics={model.baseline.waveform}
                      physicsLabel="Baseline raw physics"
                      predictionLabel="What-if raw physics"
                      height={260}
                      front={front}
                      timeMaxUs={Math.max(model.baseline.metrics.tail_us, model.variant.metrics.tail_us) * 5}
                      frontMaxUs={
                        Math.max(model.baseline.metrics.front_us, model.variant.metrics.front_us) * (run.inputs.impulse_type === "Lightning" ? 6 : 3)
                      }
                    />
                  ) : (
                    <p className="panel-note">
                      A curve is unavailable: {model.baseline.plot_error || model.variant.plot_error}. Valid formula metrics are retained below.
                    </p>
                  )}
                  <p className="sensitivity-caption">
                    {model.id === "reference"
                      ? "Curves reconstruct the workbook’s three metrics; they are not independent waveform predictions."
                      : "Curves are simulated by the lumped RLC circuit; distributed effects and spark-gap dynamics are omitted."}{" "}
                    {model.physics_version}.
                  </p>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Baseline raw physics</th>
                          <th>What-if raw physics</th>
                          <th>Change</th>
                          <th>Allowed range</th>
                          <th>What-if waveform</th>
                        </tr>
                      </thead>
                      <tbody>
                        {model.changes.map((row: Data, i: number) => {
                          const limit = model.variant.waveform_limits.rows[i];
                          return (
                            <tr key={row.metric}>
                              <td>{limit.name}</td>
                              <td>
                                {fmt(row.baseline, 3)} {row.unit}
                              </td>
                              <td>
                                {fmt(row.variant, 3)} {row.unit}
                              </td>
                              <td>
                                {row.delta_pct > 0 ? "+" : ""}
                                {fmt(row.delta_pct, 2)}%
                              </td>
                              <td>
                                {fmt(limit.lower, 2)}–{fmt(limit.upper, 2)} {row.unit}
                              </td>
                              <td>
                                <Badge tone={limit.pass ? "green" : "red"}>{limit.pass ? "Inside limits" : "Outside limits"}</Badge>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="alert error">
                  {model?.label} could not compute this comparison: {model?.error || "Model unavailable"}. No pass is inferred.
                </div>
              )}
              <p className="sensitivity-caption">
                Saved uncertainty status: <strong>{reviewed.saved_uncertainty_status}</strong>, unchanged. Waveform limits here contain no uncertainty
                envelope or laboratory approval. Effects are local to these inputs; interactions and a universal monotonic law are not established.
              </p>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}
