"""Physics audit of the lumped Marx equivalent used for recommendations.

Run: python -m scripts.physics_audit --output artifacts/physics_audit/v1/audit.json

Three evidence levels are kept apart:
  * numerical agreement for the same equations (independent integrator),
  * agreement between different circuit models (workbook equations, alternative
    tail position, hypothetical extra discharge path),
  * agreement with measurements (none available; recorded as such).
Alternative circuits are sensitivity diagnostics only. They are never used for
recommendations, because the CPRI connection details are not supplied.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from backend.app.data.workbook_reference import calculate, predict as workbook_predict
from backend.app.physics.circuit import simulate
from backend.app.physics.compliance import check
from backend.app.physics.waveform_metrics import analyze
from scripts.independent_impulse_reference import solve as independent_solve

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('front_us', 'tail_us', 'crest_kv')
PROFILES = {p['id']: p for p in json.loads((ROOT/'config/generator_profiles.json').read_text(encoding='utf-8'))}

# Representative settings: the CPRI regression cases recorded in OPTIMIZATION_REPORT.md
# and the workbook golden case. Charge values are the recorded recommended charges.
CASES = [
    {'name': 'CPRI Lightning 1425 kV', 'profile': 'cpri_problem_brief_profile', 'impulse_type': 'Lightning',
     'stages': 11, 'charge_kv_stage': 181.90279, 'front_r_stage': 30, 'tail_r_stage': 520,
     'load_c_pf': 650, 'divider_c_pf': 250, 'stray_c_pf': 55, 'base_c_pf': 545, 'l_uh': 12, 'efficiency': .83},
    {'name': 'CPRI Switching 1050 kV', 'profile': 'cpri_problem_brief_profile', 'impulse_type': 'Switching',
     'stages': 11, 'charge_kv_stage': 141.116226, 'front_r_stage': 4165, 'tail_r_stage': 22000,
     'load_c_pf': 650, 'divider_c_pf': 250, 'stray_c_pf': 55, 'base_c_pf': 545, 'l_uh': 12, 'efficiency': .83},
]
# Workbook golden case: the supplied calculator's own recommended settings.
_wb = calculate()
CASES.append({'name': 'Workbook Lightning 1425 kV (calculator settings)', 'profile': 'workbook_reference_profile',
              'impulse_type': 'Lightning', 'stages': _wb['stages'], 'charge_kv_stage': _wb['charge_kv_stage'],
              'front_r_stage': _wb['front_r_stage'], 'tail_r_stage': _wb['tail_r_stage'], 'load_c_pf': 850,
              'divider_c_pf': 500, 'stray_c_pf': 150, 'base_c_pf': 0, 'l_uh': 18.5, 'efficiency': .82})


def total_pf(case):
    return case['load_c_pf'] + case['divider_c_pf'] + case['stray_c_pf'] + case['base_c_pf']


def production(case, **override):
    c = {**case, **override}
    return simulate(c['stages'], c['charge_kv_stage'], c['front_r_stage'], c['tail_r_stage'],
                    PROFILES[c['profile']]['stage_c_uf'], total_pf(c), c['l_uh'], c['efficiency'],
                    c['impulse_type'], True)


def alternative(case, tail_position='generator', extra_shunt_ohm=None):
    """Transient integration of a variant topology (diagnostic only)."""
    n = case['stages']
    cg = PROFILES[case['profile']]['stage_c_uf'] * 1e-6 / n
    cl = total_pf(case) * 1e-12
    rf, rt, inductance = n*case['front_r_stage'], n*case['tail_r_stage'], case['l_uh']*1e-6
    v0 = n * case['charge_kv_stage'] * case['efficiency']
    g_gen = (1/rt if tail_position == 'generator' else 0.) + (1/extra_shunt_ohm if extra_shunt_ohm else 0.)
    g_load = 1/rt if tail_position == 'load' else 0.

    def rhs(t, y):
        vg, current, vl = y
        return [(-current - g_gen*vg)/cg, (vg - rf*current - vl)/inductance, (current - g_load*vl)/cl]

    tau = rt*(cg+cl) + rf*cl
    horizon = 12*tau
    sol = solve_ivp(rhs, (0, horizon), [v0, 0., 0.], method='Radau', rtol=1e-9, atol=1e-12*v0,
                    dense_output=True, max_step=horizon/2000)
    if not sol.success:
        raise ValueError(sol.message)
    fast = max(rf*cl, math.sqrt(inductance*cl))
    t = np.unique(np.r_[np.linspace(0, 40*fast, 4000), np.geomspace(fast*1e-3, horizon, 6000)])
    v = sol.sol(t)[2]
    metrics = analyze(t*1e6, v, case['impulse_type'])
    return {k: float(metrics[k]) for k in KEYS}


def relative(a, b):
    return {k: 100*(a[k]/b[k]-1) for k in KEYS}


def audit_case(case):
    p = PROFILES[case['profile']]
    base = production(case)
    metrics = {k: base[k] for k in KEYS}
    independent = independent_solve({**case, 'stage_c_uf': p['stage_c_uf'], 'total_c_pf': total_pf(case)})
    wb = workbook_predict(case['stages'], case['charge_kv_stage'], case['front_r_stage'], case['tail_r_stage'],
                          case['load_c_pf'], case['divider_c_pf'], case['stray_c_pf'] + case['base_c_pf'],
                          case['l_uh'], case['efficiency'], p['stage_c_uf'])
    load_side = alternative(case, 'load')
    same_by_ode = alternative(case, 'generator')
    rows = {
        'production_lumped_circuit': metrics,
        'independent_integrator_same_equations': {k: independent[k] for k in KEYS},
        'ode_check_same_topology': same_by_ode,
        'workbook_equations_different_model': {k: wb[k] for k in KEYS},
        'tail_resistor_on_load_side_diagnostic': load_side,
    }
    if p.get('charging_r_ohm'):
        # Hypothetical: one column of charging resistors acting as an extra discharge
        # path across the erected capacitance. Connection not supplied; bound only.
        rows['hypothetical_charging_resistor_discharge_path'] = alternative(
            case, 'generator', extra_shunt_ohm=case['stages']*p['charging_r_ohm'])
    differences = {name: relative(values, metrics) for name, values in rows.items() if name != 'production_lumped_circuit'}
    utilization = metrics['crest_kv'] / (case['stages']*case['charge_kv_stage']*case['efficiency'])
    no_extra_loss_charge = case['charge_kv_stage']*case['efficiency']
    without_base = production(case, base_c_pf=0) if case['base_c_pf'] else None
    t30, t90 = base['t30_us'], base['t90_us']
    record = {
        'case': case, 'metrics': rows, 'difference_vs_production_pct': differences,
        'compliance': {name: check(case['impulse_type'], metrics['crest_kv'], values)['nominal_pass'] for name, values in rows.items()},
        'units': {
            'erected_capacitance_nf': p['stage_c_uf']*1e3/case['stages'],
            'load_side_capacitance_pf': total_pf(case),
            'total_front_ohm': case['stages']*case['front_r_stage'],
            'total_tail_ohm': case['stages']*case['tail_r_stage'],
            'erected_charge_kv': case['stages']*case['charge_kv_stage'],
            'stored_energy_kj': case['stages']*.5*p['stage_c_uf']*1e-6*(case['charge_kv_stage']*1e3)**2/1e3,
            'energy_rating_total_kj': p['energy_total_kj'],
            'maximum_energy_ratio': base['diagnostics']['maximum_energy_ratio'],
        },
        'efficiency': {
            'assumed_extra_loss_factor': case['efficiency'],
            'circuit_voltage_utilization': utilization,
            'overall_crest_per_erected_kv': metrics['crest_kv']/(case['stages']*case['charge_kv_stage']),
            'charge_needed_without_extra_loss_kv_stage': no_extra_loss_charge,
            'note': 'The circuit already loses voltage to the Cg/Cl divider and tail discharge. The efficiency input is applied '
                    'on top as an extra, unmodelled loss. If the operator means the workbook overall efficiency, losses are '
                    'counted twice and the recommended charge is too high by 1/efficiency.',
        },
        'definitions': {
            'lightning_front': '1.67 × (t90 − t30) on the rising edge',
            'virtual_origin': 't30 − 0.5 × (t90 − t30)',
            'lightning_tail': 't50 − virtual origin',
            'switching_peak': 'time from true origin (t = 0 in simulation) to crest, challenge convention',
            'switching_tail': 't50 from true origin, challenge convention',
            'rising_30_90_interval_us': t90 - t30,
            'note': 'Standards editions define switching time-to-peak differently; the challenge targets and definitions are kept.',
        },
    }
    if without_base:
        record['base_capacitance_effect_pct'] = relative({k: without_base[k] for k in KEYS}, metrics)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/physics_audit/v1/audit.json')
    args = parser.parse_args()
    result = {'version': 'physics-audit-v1', 'cases': [audit_case(c) for c in CASES],
              'evidence_levels': {
                  'numerical_agreement_same_equations': 'Independent charge/flux Radau integrator and a separate state-space ODE solve.',
                  'agreement_between_circuit_models': 'Workbook equations and topology variants; differences are model-form sensitivity, not error.',
                  'agreement_with_measurements': 'None available. No measured generator waveform with known settings has been supplied.'},
              'omitted_effects': [
                  'Spark-gap resistance, arc inductance and firing jitter (no circuit information supplied).',
                  'Distributed stage-to-ground stray capacitance and stage inductance (values not supplied).',
                  'Charging, potential and grounding resistor paths during the pulse (connections not supplied; bounded above as a hypothetical).',
                  'Divider internal damping and lead geometry beyond the single lumped inductance.'],
              'scope': 'Software and model-form audit. It does not establish physical accuracy of the generator.'}
    out = ROOT/args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for case in result['cases']:
        print(case['case']['name'])
        for name, diff in case['difference_vs_production_pct'].items():
            print(f'  {name:52s}', {k: f'{v:+.4f}%' for k, v in diff.items()})
        print('  utilization', round(case['efficiency']['circuit_voltage_utilization'], 4),
              'overall', round(case['efficiency']['overall_crest_per_erected_kv'], 4))


if __name__ == '__main__':
    main()
