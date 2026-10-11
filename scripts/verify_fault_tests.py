"""Predeclared generated fault-scenario numerical verification.

The SI-unit reference below builds Kirchhoff equations independently. It does
not import the production matrices, modes, state propagator or metric helpers.
Run with ``python -m scripts.verify_fault_tests`` after implementation lands.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "artifacts/fault_tests/v1/protocol.json"


def si_equivalent(configuration: dict, *, active_stages: int | None = None,
                  source_fraction: float = 1.) -> dict:
    """Construct the declared series-Marx equivalent from original inputs."""
    n = configuration["stages"] if active_stages is None else active_stages
    if n == 0:
        return {"zero": True}
    return {"zero": False, "cg": configuration["stage_c_uf"] * 1e-6 / n,
            "cl": configuration["total_c_pf"] * 1e-12,
            "rf": configuration["front_r_stage"] * n,
            "rt": configuration["tail_r_stage"] * n,
            "l": configuration["l_uh"] * 1e-6,
            "initial_v": n * configuration["charge_kv_stage"] * 1000
                         * configuration["efficiency"] * source_fraction}


def independent_matrix(eq: dict, r_shunt: float | None = None,
                       l_shunt: float = 0.) -> tuple[np.ndarray, list[str]]:
    """Independent SI nodal state order Vg,Vl,(Iseries),(Ishunt)."""
    names = ["generator_v", "load_v"]
    if eq["l"] > 0:
        names.append("series_a")
    if r_shunt is not None and l_shunt > 0:
        names.append("shunt_a")
    index = {name: k for k, name in enumerate(names)}
    a = np.zeros((len(names), len(names)), dtype=float)
    vg, vl = index["generator_v"], index["load_v"]
    a[vg, vg] -= 1 / (eq["cg"] * eq["rt"])
    if eq["l"] > 0:
        i = index["series_a"]
        a[vg, i] -= 1 / eq["cg"]
        a[vl, i] += 1 / eq["cl"]
        a[i, vg] += 1 / eq["l"]
        a[i, vl] -= 1 / eq["l"]
        a[i, i] -= eq["rf"] / eq["l"]
    else:
        # Substitute the algebraic front-branch current into the two KCLs.
        a[vg, vg] -= 1 / (eq["rf"] * eq["cg"])
        a[vg, vl] += 1 / (eq["rf"] * eq["cg"])
        a[vl, vg] += 1 / (eq["rf"] * eq["cl"])
        a[vl, vl] -= 1 / (eq["rf"] * eq["cl"])
    if r_shunt is not None:
        if l_shunt > 0:
            i = index["shunt_a"]
            a[vl, i] -= 1 / eq["cl"]
            a[i, vl] += 1 / l_shunt
            a[i, i] -= r_shunt / l_shunt
        else:
            a[vl, vl] -= 1 / (r_shunt * eq["cl"])
    return a, names


def _integrate(a: np.ndarray, initial: np.ndarray, start: float, end: float,
               times: np.ndarray, method: str) -> np.ndarray:
    if end == start:
        return np.repeat(initial[:, None], len(times), axis=1)
    # Constant Jacobian supplied separately from the production solution.
    sol = solve_ivp(lambda _t, y: a @ y, (start, end), initial,
                    method=method, jac=a, rtol=1e-10,
                    atol=np.full(len(initial), 1e-8), dense_output=True,
                    max_step=(end - start) / 1000)
    if not sol.success:
        raise AssertionError(f"Independent {method} integration failed: {sol.message}")
    return np.asarray(sol.sol(times))


def independent_response(configuration: dict, time_us: list[float] | np.ndarray,
                         *, method: str = "Radau", chop_time_us: float | None = None,
                         shunt_r_ohm: float | None = None, shunt_l_uh: float = 0.,
                         active_stages: int | None = None,
                         source_fraction: float = 1.) -> dict:
    times = np.asarray(time_us, dtype=float) * 1e-6
    eq = si_equivalent(configuration, active_stages=active_stages,
                       source_fraction=source_fraction)
    if eq["zero"] or eq["initial_v"] == 0:
        return {"voltage_kv": np.zeros(len(times)), "energy_j": np.zeros(len(times)),
                "states": {}, "event_before": {}, "event_after": {}}
    a, names = independent_matrix(eq)
    initial = np.zeros(len(names)); initial[0] = eq["initial_v"]
    if chop_time_us is None:
        states = _integrate(a, initial, 0., float(times[-1]), times, method)
        state_map = dict(zip(names, states))
        before = after = {}
    else:
        event_t = chop_time_us * 1e-6
        prior_times = times[times <= event_t]
        before_states = _integrate(a, initial, 0., event_t,
                                  np.r_[prior_times, event_t], method)
        event_values = before_states[:, -1]
        after_a, after_names = independent_matrix(eq, shunt_r_ohm, shunt_l_uh * 1e-6)
        after_initial = np.zeros(len(after_names))
        after_initial[:len(names)] = event_values
        later_times = times[times > event_t]
        later = _integrate(after_a, after_initial, event_t, float(times[-1]),
                           later_times, method)
        state_map = {}
        for i, name in enumerate(after_names):
            prior = before_states[i, :-1] if i < len(names) else np.zeros(len(prior_times))
            state_map[name] = np.r_[prior, later[i]]
        before = dict(zip(names, map(float, event_values)))
        after = dict(zip(after_names, map(float, after_initial)))
    vg, vl = state_map["generator_v"], state_map["load_v"]
    energy = .5 * eq["cg"] * vg ** 2 + .5 * eq["cl"] * vl ** 2
    if "series_a" in state_map:
        energy += .5 * eq["l"] * state_map["series_a"] ** 2
    if "shunt_a" in state_map:
        energy += .5 * shunt_l_uh * 1e-6 * state_map["shunt_a"] ** 2
    return {"voltage_kv": vl / 1000, "energy_j": energy, "states": state_map,
            "event_before": before, "event_after": after}


def rc_shunt_exponential(configuration: dict, times_us: list[float],
                         chop_time_us: float, shunt_r_ohm: float) -> np.ndarray:
    """2x2 independent analytic RC event solution; no numerical integration."""
    eq = si_equivalent({**configuration, "l_uh": 0.})
    a, _ = independent_matrix(eq)
    b, _ = independent_matrix(eq, shunt_r_ohm, 0.)
    z = np.array([eq["initial_v"], 0.])
    tc = chop_time_us * 1e-6
    handover = expm(a * tc) @ z
    values = []
    for t_us in times_us:
        t = t_us * 1e-6
        y = expm(a * t) @ z if t <= tc else expm(b * (t-tc)) @ handover
        values.append(float(y[1] / 1000))
    return np.array(values)


def _crossing(times: np.ndarray, values: np.ndarray, level: float,
              start: int = 0, rising: bool = True) -> float | None:
    for i in range(start, len(times)-1):
        va, vb = values[i:i+2]
        hit = va <= level <= vb if rising else va >= level >= vb
        if hit:
            return float(times[i] if vb == va else
                         times[i] + (times[i+1]-times[i])*(level-va)/(vb-va))
    return None


def published_sample_metrics(time_us: list[float], voltage_kv: list[float]) -> dict:
    """Independent positive-LI sample measurements; no application import."""
    t, v = np.array(time_us), np.array(voltage_kv)
    peak = int(np.argmax(v)); crest = float(v[peak])
    if crest <= 0:
        return {"crest_kv": 0., "peak_time_us": None, "front_us": None, "tail_us": None}
    t30 = _crossing(t[:peak+1], v[:peak+1], .3*crest)
    t90 = _crossing(t[:peak+1], v[:peak+1], .9*crest)
    t50 = _crossing(t, v, .5*crest, peak, False)
    virtual = t30-.5*(t90-t30) if t30 is not None and t90 is not None else None
    return {"crest_kv": crest, "peak_time_us": float(t[peak]),
            "front_us": 1.67*(t90-t30) if t30 is not None and t90 is not None else None,
            "tail_us": t50-virtual if t50 is not None and virtual is not None else None,
            "t30_us": t30, "t90_us": t90, "t50_us": t50,
            "virtual_origin_us": virtual}


def snapshot_for_configuration(configuration: dict, case_id: str = "generated_verification") -> dict:
    """Generated fixture snapshot: no optimizer/database/evidence mutation."""
    c = configuration
    is_cpri = c["stage_c_uf"] == .125 and c["stages"] in (11, 12)
    is_workbook = c["stage_c_uf"] == 3.
    snapshot = {
        "run_id": case_id, "candidate_id": "fixed_saved_settings", "rank": 1,
        "impulse_type": "Lightning", "test_kv": 1425.,
        "profile_label": "CPRI fixture" if is_cpri else "Workbook fixture" if is_workbook else "Hypothetical custom fixture",
        "inputs": {"connection_mode": "series_marx_equivalent", "include_base_c": False,
                   "solver": "circuit", "impulse_type": "Lightning"},
        "settings": {key: c[key] for key in ("stages", "charge_kv_stage", "front_r_stage", "tail_r_stage")},
        "circuit_inputs": {"load_c_pf": c["total_c_pf"], "divider_c_pf": 0.,
                           "stray_c_pf": 0., "l_uh": c["l_uh"]},
        "efficiency": c["efficiency"], "effective_parameters": None,
        "profile": {"id": "cpri_problem_brief_profile" if is_cpri else "workbook_reference_profile" if is_workbook else "custom_fixture",
                    "stage_c_uf": c["stage_c_uf"], "base_c_pf": 0.,
                    "min_stages": 1, "max_stages": 12 if is_cpri else 15 if is_workbook else c["stages"],
                    "stage_kv": 200., "energy_total_kj": None},
        "saved_prediction": {"solver": "circuit", "metrics": None},
        "solver_note": None, "open_questions": [], "topology": "Declared series Marx equivalent",
    }
    snapshot["sha256"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return snapshot


def production_case(case: dict) -> dict:
    """Only the public simulation entry point and request classes imported."""
    from backend.app.fault_tests.simulation import simulate_fault
    from backend.app.fault_tests.models import ChoppedImpulse, StageFailure
    from backend.app.physics.circuit import simulate
    snapshot = snapshot_for_configuration(case["configuration"], case["id"])
    if case["kind"] == "chop":
        # Mode validation belongs to public contract. Fixed times are never moved.
        healthy = simulate(**case["configuration"])
        mode = "front" if case["chop_time_us"] < healthy["peak_time_us"] else "tail"
        request = ChoppedImpulse(test_type="chopped_impulse", chop_mode=mode,
                                 chop_time_us=case["chop_time_us"], shunt_r_ohm=case["shunt_r_ohm"],
                                 shunt_l_uh=case["shunt_l_uh"], title=case["id"])
    else:
        request = StageFailure(test_type="stage_failure",
                               failure_mode="uncharged_conducting" if case["mode"] == "uncharged" else "bypassed",
                               stage_indices=case["failed_stages"], remaining_charge_fraction=0., title=case["id"])
    return simulate_fault(snapshot, request)


def score_case(case: dict, result: dict) -> tuple[dict, dict]:
    """Score predeclared gates; never modify a scenario or acceptance limit."""
    healthy = result["healthy"]; fault = result["fault"]
    t = np.array(fault["waveform"]["time_us"])
    v = np.array(fault["waveform"]["voltage_kv"])
    vh = np.array(healthy["waveform"]["voltage_kv"])
    scale = max(vh)
    c = case["configuration"]
    kwargs = {}
    if case["kind"] == "chop":
        kwargs = {key: case[key] for key in ("chop_time_us", "shunt_r_ohm", "shunt_l_uh")}
    elif case["mode"] == "uncharged":
        kwargs["source_fraction"] = (c["stages"]-len(case["failed_stages"]))/c["stages"]
    else:
        kwargs["active_stages"] = c["stages"]-len(case["failed_stages"])
    errors = {}; energy_growth = {}; independent = {}
    arrays = {"time_us": t, "healthy_voltage_kv": vh, "fault_voltage_kv": v}
    for method in ("Radau", "BDF"):
        ref = independent_response(c, t, method=method, **kwargs)
        href = independent_response(c, t, method=method)
        errors[method] = {"fault": float(np.max(np.abs(v-ref["voltage_kv"]))/scale),
                          "healthy": float(np.max(np.abs(vh-href["voltage_kv"]))/scale)}
        initial = float(ref["energy_j"][0])
        energy_growth[method] = float(max(0., np.diff(ref["energy_j"]).max())/initial) if initial else 0.
        arrays[f"{method.lower()}_fault_voltage_kv"] = ref["voltage_kv"]
        arrays[f"{method.lower()}_energy_j"] = ref["energy_j"]
        independent[method] = ref
    gates = {"G1_independent_voltage": all(max(x.values()) <= 1e-5 for x in errors.values())}
    details = {"voltage_error_normalized_by_healthy_crest": errors,
               "independent_energy_maximum_increase_ratio": energy_growth}
    if case["kind"] == "chop":
        mask = t <= case["chop_time_us"]
        pre_gap = float(np.max(np.abs(v[mask]-vh[mask]))/scale)
        gates["G2_pre_chop_match"] = pre_gap <= 1e-8
        event = result["event"]
        before, after = event["pre_state"], event["post_state"]
        continuity = {key: abs(after[key]-before[key])/max(1.,abs(before[key]))
                      for key in ("generator_voltage_kv", "load_voltage_kv", "series_current_a")}
        shunt_ok = (after["shunt_current_a"] == 0. if case["shunt_l_uh"] > 0 else
                    abs(after["shunt_current_a"]-after["load_voltage_kv"]*1000/case["shunt_r_ohm"]) < 1e-8)
        gates["G3_continuity_and_passivity"] = (max(continuity.values()) <= 1e-10 and shunt_ok
              and max(energy_growth.values()) <= 1e-8
              and result["checks"]["post_event_maximum_energy_increase_ratio"] <= 1e-8)
        details.update(pre_chop_normalized_gap=pre_gap, relative_event_state_jump=continuity,
                       shunt_initial_current_correct=shunt_ok)
    else:
        gates["G3_continuity_and_passivity"] = max(energy_growth.values()) <= 1e-8
    # Independently re-extract all available geometric metrics from exactly
    # the exported curve. This is not ordinary full-impulse acceptance.
    metrics = published_sample_metrics(t.tolist(), v.tolist())
    metric_errors = {}
    for key, expected in metrics.items():
        got = fault["metrics"].get(key)
        if expected is None or got is None:
            metric_errors[key] = 0. if expected is None and got is None else None
        else:
            metric_errors[key] = abs(expected-got)/max(1., abs(expected))
    gates["G4_metrics_export_consistency"] = all(x is not None and x <= 1e-8 for x in metric_errors.values())
    details["exported_metric_relative_error"] = metric_errors
    if case["kind"] == "stage_failure":
        n, k = c["stages"], len(case["failed_stages"])
        ratio = (n-k)/n
        eq_args = result["event"]["fault_circuit_args"]
        if case["mode"] == "uncharged":
            proportionality = float(np.max(np.abs(v-vh*ratio))/scale)
            args_ok = all(eq_args[key] == c[key] for key in ("stages","stage_c_uf","total_c_pf","front_r_stage","tail_r_stage","l_uh"))
            charge_ok = abs(eq_args["charge_kv_stage"]-c["charge_kv_stage"]*ratio) <= 1e-9
            gates["G5_stage_fault_semantics"] = proportionality <= 1e-8 and args_ok and charge_ok
            details["proportionality_error_normalized"] = proportionality
        else:
            gates["G5_stage_fault_semantics"] = eq_args["stages"] == n-k and eq_args["charge_kv_stage"] == c["charge_kv_stage"]
        input_single = .5*c["stage_c_uf"]*1e-6*(c["charge_kv_stage"]*1000)**2/1000
        expected_input = (n-k)*input_single
        expected_terminal = (.5*c["stage_c_uf"]*1e-6/n*((n-k)*c["charge_kv_stage"]*1000*c["efficiency"])**2/1000
                             if case["mode"] == "uncharged" else expected_input*c["efficiency"]**2)
        input_match = abs(result["energy"]["fault_input_kj"]-expected_input) <= 1e-8
        terminal_match = abs(result["energy"]["fault_terminal_equivalent_kj"]-expected_terminal) <= 1e-8
        gates["G5_stage_fault_semantics"] &= input_match and terminal_match
        details.update(input_stage_energy_expected_kj=expected_input, terminal_equivalent_energy_expected_kj=expected_terminal,
                       energy_metadata_matches=input_match and terminal_match)
    if c["l_uh"] in (0., 1e-10) and case["kind"] == "chop" and case["shunt_l_uh"] == 0.:
        analytic = rc_shunt_exponential(c, t.tolist(), case["chop_time_us"], case["shunt_r_ohm"])
        rc_error = float(np.max(np.abs(v-analytic))/scale)
        gates["G6_RC_analytic_limit"] = rc_error <= 1e-7
        details["rc_analytic_normalized_error"] = rc_error
    gates["G7_input_and_provenance"] = (result["source_type"] == "generated_hypothetical_fault"
        and result["hardware_control"] is False and result["laboratory_validation"] == "Not established"
        and result["compliance_assessment"] == "Not performed for fault waveforms"
        and result["checks"]["original_charge_held_fixed"] is True
        and result["checks"]["output_renormalized"] is False)
    json.dumps(result, allow_nan=False)
    row = {"id": case["id"], "kind": case["kind"], "configuration": c,
           "actual_chop_classification": result["event"].get("classification"),
           "healthy_metrics": healthy["metrics"], "fault_metrics": fault["metrics"],
           "energy": result["energy"], "event": result["event"], "production_checks": result["checks"],
           "gates": gates, "all_applicable_gates_pass": all(gates.values()), "details": details}
    return row, arrays


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/fault_tests/v1/results.json")
    parser.add_argument("--execution-id", default="initial_execution")
    args = parser.parse_args()
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    clarification = json.loads((PROTOCOL.parent/"pre_scoring_contract_clarification.json").read_text())
    rejection_ids = set(clarification["contract_clarifications"][0]["case_ids"])
    rows = []
    execution_dir = PROTOCOL.parent / args.execution_id
    execution_dir.mkdir(exist_ok=True)
    for case in protocol["cases"]:
        try:
            result = production_case(case)
            if case["id"] in rejection_ids:
                row = {"id":case["id"], "expected_rejection":True, "all_applicable_gates_pass":False,
                       "error":"Unsupported all-bypassed scenario incorrectly returned a result."}
            else:
                row, arrays = score_case(case, result)
                np.savez_compressed(execution_dir/f"{case['id']}.npz", **arrays)
        except Exception as exc:
            row = {"id":case["id"], "expected_rejection":case["id"] in rejection_ids,
                   "all_applicable_gates_pass":case["id"] in rejection_ids and isinstance(exc, ValueError),
                   "error_type":type(exc).__name__, "error":str(exc)}
        rows.append(row)
        print(case["id"], "PASS" if row["all_applicable_gates_pass"] else "FAIL", flush=True)
    gate_summary = {}
    for gate in protocol["gates"]:
        scores = [row["gates"][gate] for row in rows if gate in row.get("gates",{})]
        gate_summary[gate] = {"pass":all(scores) if scores else None,"scored_cases":len(scores),
                              "passing_cases":sum(scores)}
    sources = [ROOT/"backend/app/fault_tests/simulation.py", ROOT/"scripts/verify_fault_tests.py"]
    output = {"execution_id":args.execution_id, "protocol_sha256":hashlib.sha256(protocol_bytes).hexdigest(),
              "scope":protocol["scope"], "clarification":clarification,
              "source_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "methods":["Radau","BDF","analytic 2x2 RC exponential"], "cases":rows,
              "numeric_case_count":sum(not row.get("expected_rejection",False) for row in rows),
              "expected_rejection_case_count":sum(row.get("expected_rejection",False) for row in rows),
              "all_cases_pass":all(row["all_applicable_gates_pass"] for row in rows),
              "gate_summary":gate_summary, "input_rejection_regressions":"See tests/test_fault_tests_independent.py pytest record; G7 case scores here cover provenance only.",
              "not_established":["Real CPRI accuracy","actual gap or physical stage-failure waveform prediction","IEC compliance","physical safety"]}
    destination = ROOT/args.output
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite prior execution: {destination}")
    destination.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print("Saved", destination, "all cases pass:", output["all_cases_pass"], flush=True)


if __name__ == "__main__":
    main()
