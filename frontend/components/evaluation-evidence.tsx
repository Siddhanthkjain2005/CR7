'use client';
import {useEffect, useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {api, apiUrl, Data, fmt} from '@/lib/api';
import {Badge, KindTag, Notice, Panel, PassFail, Skeleton} from './ui';

const PROFILE_NAMES: Record<string, string> = {
  cpri_problem_brief_profile: 'CPRI',
  workbook_reference_profile: 'Workbook',
  custom_generator: 'Custom',
};

function groupLabel(key: string) {
  const [profile, impulse, engine] = key.split(' | ');
  return `${PROFILE_NAMES[profile] || profile} · ${impulse} · ${engine === 'circuit' ? 'circuit' : 'workbook equations'}`;
}

function stat(s: Data | null | undefined, digits = 3) {
  if (!s) return '—';
  const floor = 10 ** -digits;
  const one = (v: number) => (Math.abs(v) < floor ? `<${fmt(floor, digits)}` : fmt(v, digits));
  if (Math.abs(s.worst) < floor) return `all <${fmt(floor, digits)}`;
  return `${one(s.median)} / ${one(s.p95)} / ${one(s.worst)}`;
}

/**
 * What the saved evaluation pack, surrogate study and physics audit demonstrate.
 * Reads recorded artifacts only; nothing is re-run in the browser.
 */
export default function EvaluationEvidence() {
  const [pack, setPack] = useState<Data | null>(null);
  const [surrogate, setSurrogate] = useState<Data | null>(null);
  const [audit, setAudit] = useState<Data | null>(null);
  const [study, setStudy] = useState<Data | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  useEffect(() => {
    const gone = (name: string) => () => setMissing(m => [...m, name]);
    api('/api/evaluation-pack').then(setPack).catch(gone('evaluation pack'));
    api('/api/verification/surrogate').then(setSurrogate).catch(gone('surrogate study'));
    api('/api/verification/physics-audit').then(setAudit).catch(gone('physics audit'));
    api('/api/verification/parameter-calibration-study').then(setStudy).catch(gone('parameter calibration study'));
  }, []);
  if (!pack && !surrogate && !audit && !missing.length) {
    return (
      <Panel>
        <Skeleton lines={5} />
      </Panel>
    );
  }
  const s = surrogate?.summary;
  return (
    <section className="evaluation" aria-labelledby="evaluation-title">
      <div className="section-title">
        <h2 id="evaluation-title">What is demonstrated</h2>
        <a className="button small" href={apiUrl('/api/documents/accuracy_report')} target="_blank" rel="noreferrer">
          Accuracy report <ArrowUpRight size={14} aria-hidden />
        </a>
      </div>
      <div className="evidence-levels">
        <div>
          <KindTag kind="simulation">Numerical agreement</KindTag>
          <p>The production circuit solver against an independent integrator of the same equations.</p>
        </div>
        <div>
          <KindTag kind="assumption">Different circuit models</KindTag>
          <p>Workbook equations and alternative topologies. Differences measure model-form uncertainty.</p>
        </div>
        <div>
          <KindTag kind="measured">Measured</KindTag>
          <p>None yet. No real generator capture with known settings has been supplied.</p>
        </div>
      </div>
      {missing.length > 0 && <Notice tone="neutral">Not recorded yet: {missing.join(', ')}.</Notice>}

      {pack && (
        <Panel
          title="Evaluation pack · unknown judge inputs"
          eyebrow={`${pack.cases} reproducible requests · ${pack.outcomes.recommendations} recommendations · ${pack.outcomes.rejections} correct rejections expected`}
          action={<Badge tone={pack.outcomes.expected_outcome_matched === pack.cases ? 'green' : 'amber'}>{pack.outcomes.expected_outcome_matched}/{pack.cases} expected outcomes</Badge>}
        >
          <p className="panel-note">
            Each recommended setting (top three per request) is re-simulated with the independent integrator. Errors are displayed value versus that re-simulation:
            median / 95th percentile / worst absolute percentage. A false pass means the app showed a pass that the re-simulation fails.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Profile · impulse · engine</th>
                  <th className="num">Requests</th>
                  <th className="num">Crest error %</th>
                  <th className="num">Front / peak error %</th>
                  <th className="num">Tail error %</th>
                  <th className="num">Waveform NRMSE %</th>
                  <th className="num">False passes</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(pack.simulation_agreement_by_profile as Data).map(([key, g]: [string, Data]) => (
                  <tr key={key}>
                    <td>{groupLabel(key)}</td>
                    <td className="num">{g.cases}</td>
                    <td className="num">{stat(g.crest_error_pct, 4)}</td>
                    <td className="num">{stat(g.front_or_peak_error_pct, 4)}</td>
                    <td className="num">{stat(g.tail_error_pct, 4)}</td>
                    <td className="num">{stat(g.waveform_nrmse_pct, 3)}</td>
                    <td className="num">
                      {g.false_passes} of {g.candidates_checked}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="facts">
            <div>
              <span>Bounded versus exhaustive search</span>
              <strong>
                {pack.recommendation_quality.top1_agreement}/{pack.recommendation_quality.exhaustive_comparisons} same top setting
              </strong>
              <small>Requests whose full constructible network catalogue could be circuit-solved</small>
            </div>
            <div>
              <span>Workbook calculator baseline</span>
              <strong>
                {pack.baseline_workbook_calculator.circuit_nominal_passes}/{pack.baseline_workbook_calculator.cases_simulated} pass in the circuit
              </strong>
              <small>Its unconstrained settings, stock not checked, simulated with the circuit</small>
            </div>
            {pack.surrogate_expanded_search && (
              <div>
                <span>Surrogate-screened search</span>
                <strong>
                  {pack.surrogate_expanded_search.strictly_better} better · {pack.surrogate_expanded_search.equal_or_better}/{pack.surrogate_expanded_search.cases} equal or better
                </strong>
                <small>{pack.surrogate_expanded_search.promoted ? 'Met its promotion rule' : 'Did not meet its promotion rule; default search unchanged'}</small>
              </div>
            )}
          </div>
          <p className="panel-note">{pack.measured_performance}</p>
        </Panel>
      )}

      {study && (
        <Panel
          title="Calibrating the generator from one reduced-voltage shot"
          eyebrow="Simulated model-mismatch study · not laboratory evidence"
          action={<PassFail pass={study.gates.all_pass} passText="All declared gates passed" failText="Declared gates not met" />}
        >
          <p className="panel-note">
            A stand-in “true” generator differs from the declared model (loss, stray capacitance, a charging-resistor discharge path, part of the tail at the load, spark-gap
            resistance and extra inductance). One shot at half charge fits three circuit parameters, which then predict other settings and voltages.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Impulse · method</th>
                  <th className="num">Shots</th>
                  <th className="num">Crest median / worst %</th>
                  <th className="num">Front median / worst %</th>
                  <th className="num">Tail median / worst %</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(study.summary as Data).flatMap(([impulse, m]: [string, Data]) =>
                  (['uncalibrated', 'metric_offset', 'fitted_parameters'] as const).map(method => (
                    <tr key={impulse + method}>
                      <td>
                        {impulse} · {method === 'uncalibrated' ? 'declared model' : method === 'metric_offset' ? 'one-shot offset' : 'fitted parameters'}
                      </td>
                      <td className="num">{m.validation_shots}</td>
                      {(['crest_kv', 'front_us', 'tail_us'] as const).map(k => (
                        <td className="num" key={k}>
                          {fmt(m[method][k].median_abs_pct, 3)} / {fmt(m[method][k].worst_abs_pct, 2)}
                        </td>
                      ))}
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
          <p className="panel-note">
            Recommendations that pass on the stand-in generator: {study.gates.recommendation_truth_passes.uncalibrated} of {study.gates.recommendation_truth_passes.cases} with the declared model,{' '}
            {study.gates.recommendation_truth_passes.fitted_parameters} of {study.gates.recommendation_truth_passes.cases} after fitting. The one-shot offset cannot transfer to other settings or
            voltages, so it equals the declared model here. Real calibration shots are needed to confirm this on the machine.
          </p>
        </Panel>
      )}

      {s && (
        <Panel
          title="Machine learning: circuit surrogate"
          eyebrow={`${fmt(surrogate?.dataset?.rows, 0)} simulated rows · grouped split · test frozen before model selection`}
          action={<PassFail pass={s.screening_use_allowed} passText="Accuracy gate passed" failText="Accuracy gate failed" />}
        >
          <p className="panel-note">
            A small neural network trained on simulated outcomes reproduces the circuit solver about {fmt(s.runtime_ms_per_setting?.speedup, 0)}× faster. It is a surrogate of the
            solver: it cannot be more physically accurate than the circuit, and it never produces a displayed prediction. It is used only to screen settings, which are then re-simulated.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Frozen test (inside validated range)</th>
                  <th className="num">Rows</th>
                  <th className="num">Front / peak p95 %</th>
                  <th className="num">Tail p95 %</th>
                  <th className="num">Crest p95 %</th>
                  <th className="num">Worst %</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.test_errors_vs_circuit as Data).map(([impulse, e]: [string, Data]) => (
                  <tr key={impulse}>
                    <td>{impulse}</td>
                    <td className="num">{e.front_us.n}</td>
                    <td className="num">{fmt(e.front_us.p95_pct, 3)}</td>
                    <td className="num">{fmt(e.tail_us.p95_pct, 3)}</td>
                    <td className="num">{fmt(e.crest_kv.p95_pct, 3)}</td>
                    <td className="num">{fmt(Math.max(e.front_us.worst_pct, e.tail_us.worst_pct, e.crest_kv.worst_pct), 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="panel-note">
            Timing decision disagreement with the circuit: {fmt(s.test_timing_decisions?.timing_decision_disagreement_pct, 2)}% of {s.test_timing_decisions?.rows} rows; false passes{' '}
            {s.test_timing_decisions?.false_pass_rows} of {s.test_timing_decisions?.circuit_fail_rows} circuit fails. Outside the validated range the surrogate is switched off and the circuit is used.
          </p>
        </Panel>
      )}

      {audit && (
        <Panel title="Physics audit · model-form sensitivity" eyebrow="Change in each metric if a different circuit model were right" action={<KindTag kind="assumption">Diagnostic</KindTag>}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th className="num">Independent integrator</th>
                  <th className="num">Workbook equations</th>
                  <th className="num">Tail resistor at load</th>
                  <th className="num">Charging-resistor path</th>
                </tr>
              </thead>
              <tbody>
                {audit.cases.map((c: Data) => {
                  const d = c.difference_vs_production_pct;
                  const cell = (row: Data | undefined) =>
                    row ? `${fmt(row.front_us, 1)} / ${fmt(row.tail_us, 1)} / ${fmt(row.crest_kv, 1)}` : '—';
                  return (
                    <tr key={c.case.name}>
                      <td>{c.case.name}</td>
                      <td className="num">{fmt(Math.max(...Object.values(d.independent_integrator_same_equations as Data).map(v => Math.abs(v as number))), 6)}</td>
                      <td className="num">{cell(d.workbook_equations_different_model)}</td>
                      <td className="num">{cell(d.tail_resistor_on_load_side_diagnostic)}</td>
                      <td className="num">{cell(d.hypothetical_charging_resistor_discharge_path)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="panel-note">
            Percent change in front / tail / crest relative to the production circuit; the first column is the largest absolute difference. Alternative circuits are not used for
            recommendations because the CPRI connection details are not supplied; measured shots are needed to resolve them.{' '}
            <a href={apiUrl('/api/documents/physics_audit')} target="_blank" rel="noreferrer">
              Read the physics audit
            </a>
            .
          </p>
        </Panel>
      )}
    </section>
  );
}
