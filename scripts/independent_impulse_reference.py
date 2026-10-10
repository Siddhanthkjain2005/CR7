"""Independent generated charge/flux reference; never imports serving physics.

This integrates the same disclosed lumped topology with different numerical
methods. It verifies software, not the physical generator or laboratory accuracy.
"""
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

METRICS = ('front_us', 'tail_us', 'crest_kv')


def solve(case, method='Radau', rtol=1e-9, atol=1e-12, waveform=False):
    n = case['stages']
    cg = case['stage_c_uf'] * 1e-6 / n
    cl = case['total_c_pf'] * 1e-12
    rf = n * case['front_r_stage']
    rt = n * case['tail_r_stage']
    inductance = case['l_uh'] * 1e-6
    v0 = n * case['charge_kv_stage'] * case['efficiency']
    if min(cg, cl, rf, rt, v0) <= 0 or inductance < 0:
        raise ValueError('Positive finite passive components required.')
    if not np.isfinite([cg, cl, rf, rt, inductance, v0]).all():
        raise ValueError('Finite component values required.')
    scale = rf * cl
    horizon = 12 * rt * (cg + cl) / scale
    # States are qg/(Cg*V0), ql/(Cl*V0), phi/(Rf*Cl*V0).
    # Normalized time t/(Rf*Cl) makes numerical tolerances unit independent.
    if inductance > 0:
        beta = rf * rf * cl / inductance
        jac = np.array([[-rf*cl/(rt*cg), 0, -cl/cg*beta],
                        [0, 0, beta], [1, -1, -beta]])
        initial = [1., 0., 0.]
        def peak_event(t, y):
            return y[2]
    else:
        jac = np.array([[-rf*cl/(rt*cg)-cl/cg, cl/cg], [1, -1]])
        initial = [1., 0.]
        def peak_event(t, y):
            return y[0] - y[1]
    peak_event.direction = -1
    solution = solve_ivp(lambda t, y: jac @ y, (0, horizon), initial,
                         method=method, jac=jac, rtol=rtol, atol=atol,
                         dense_output=True, events=peak_event,
                         max_step=horizon/256)
    if not solution.success:
        raise ValueError('Transient integration failed: ' + solution.message)
    peaks = solution.t_events[0]
    peaks = peaks[(peaks > 0) & (peaks < horizon)]
    if not len(peaks):
        raise ValueError('No interior reference crest.')
    peak_time = float(peaks[np.argmax(solution.sol(peaks)[1])])
    crest = float(solution.sol(peak_time)[1])
    if not np.isfinite(crest) or crest <= 0:
        raise ValueError('Unresolved reference crest.')
    def crossing(fraction, rising):
        nodes = np.unique(np.r_[solution.t, peak_time])
        nodes = nodes[nodes <= peak_time] if rising else nodes[nodes >= peak_time]
        heights = solution.sol(nodes)[1] - fraction * crest
        matches = ((heights[:-1] <= 0) & (heights[1:] >= 0) if rising
                   else (heights[:-1] >= 0) & (heights[1:] <= 0))
        candidates = np.flatnonzero(matches)
        if not len(candidates):
            raise ValueError('Unresolved reference threshold crossing.')
        i = int(candidates[0])
        return brentq(lambda t: solution.sol(t)[1] - fraction*crest,
                      nodes[i], nodes[i+1], xtol=1e-12, rtol=1e-13)
    t30, t90, t50 = crossing(.3, True), crossing(.9, True), crossing(.5, False)
    virtual = t30 - .5*(t90-t30)
    lightning = case['impulse_type'] == 'Lightning'
    if case['impulse_type'] not in ('Lightning', 'Switching'):
        raise ValueError('Unknown reference impulse type.')
    front = 1.67*(t90-t30) if lightning else peak_time
    tail = t50-virtual if lightning else t50
    states = solution.sol(solution.t)
    energy = states[0]**2 + cl/cg * states[1]**2
    if inductance > 0:
        energy += rf*rf*cl*cl/(inductance*cg) * states[2]**2
    increase = float(max(0., np.max(np.diff(energy))))
    result = {'front_us': float(front*scale*1e6),
              'tail_us': float(tail*scale*1e6), 'crest_kv': float(crest*v0),
              'peak_time_us': float(peak_time*scale*1e6),
              't30_us': float(t30*scale*1e6), 't90_us': float(t90*scale*1e6),
              't50_us': float(t50*scale*1e6),
              'virtual_origin_us': float(virtual*scale*1e6),
              'maximum_energy_ratio': float(np.max(energy)),
              'maximum_energy_increase_ratio': increase,
              'solver': method, 'rtol': rtol, 'atol': atol,
              'accepted_steps': len(solution.t), 'local_crests': len(peaks),
              'source_type': 'independent_generated_simulation'}
    if waveform:
        plot_times = np.unique(np.r_[np.linspace(0, peak_time*3, 300),
                                    np.linspace(peak_time, horizon, 300),
                                    peak_time, t30, t90, t50])
        result['waveform'] = {'time_us': (plot_times*scale*1e6).tolist(),
                              'voltage_kv': (solution.sol(plot_times)[1]*v0).tolist(),
                              'source_type': 'independent_generated_simulation'}
    return result
