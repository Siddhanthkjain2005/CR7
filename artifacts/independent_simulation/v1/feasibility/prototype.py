"""Independent charge/flux integration feasibility check; generated, not measured.

No production imports. This is a numerical-verification prototype, not ML labels.
"""
import json
import time
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

def metrics(n, charge, rfstage, rtstage, clpf, luh, impulse, method, tolerance):
    cg = .125e-6 / n
    cl = clpf * 1e-12
    rf = rfstage * n
    rt = rtstage * n
    inductance = luh * 1e-6
    v0 = n * charge * .83  # kV; normalization is linear.
    scale = rf * cl
    horizon = 12 * rt * (cg + cl) / scale
    # qg/(Cg*V0), ql/(Cl*V0), phi/(Rf*Cl*V0).
    # Flux is L*I. Inductor-free branch is solved algebraically only at L=0.
    if inductance:
        beta = rf * rf * cl / inductance
        jac = np.array([[-rf*cl/(rt*cg), 0, -cl/cg*beta],
                        [0, 0, beta], [1, -1, -beta]])
        initial = [1., 0., 0.]
        def crest_event(t, y):
            return y[2]
    else:
        jac = np.array([[-rf*cl/(rt*cg)-cl/cg, cl/cg], [1, -1]])
        initial = [1., 0.]
        def crest_event(t, y):
            return y[0] - y[1]
    crest_event.direction = -1
    start = time.perf_counter()
    result = solve_ivp(lambda t,y: jac @ y, [0,horizon], initial,
                       method=method, jac=jac, rtol=tolerance,
                       atol=tolerance*.01, dense_output=True,
                       events=crest_event, max_step=horizon/256)
    if not result.success:
        raise ValueError(result.message)
    peaks = result.t_events[0]
    peaks = peaks[(peaks > 0) & (peaks < horizon)]
    if not len(peaks):
        raise ValueError('No interior crest')
    peak = float(peaks[np.argmax(result.sol(peaks)[1])])
    crest = float(result.sol(peak)[1])
    def crossing(fraction, rising):
        # Inspect all accepted steps; choose first relevant directed crossing.
        nodes = np.unique(np.r_[result.t, peak])
        nodes = nodes[nodes <= peak] if rising else nodes[nodes >= peak]
        heights = result.sol(nodes)[1] - fraction * crest
        candidates = np.flatnonzero((heights[:-1] <= 0) & (heights[1:] >= 0)) if rising else np.flatnonzero((heights[:-1] >= 0) & (heights[1:] <= 0))
        if not len(candidates):
            raise ValueError('Missing crossing')
        i = candidates[0]
        return brentq(lambda x: result.sol(x)[1]-fraction*crest,
                      nodes[i], nodes[i+1], xtol=1e-12, rtol=1e-13)
    t30, t90, t50 = crossing(.3,True), crossing(.9,True), crossing(.5,False)
    origin = t30 - .5*(t90-t30)
    front = 1.67*(t90-t30) if impulse == 'Lightning' else peak
    tail = t50-origin if impulse == 'Lightning' else t50
    return {'front_us':front*scale*1e6, 'tail_us':tail*scale*1e6,
            'crest_kv':crest*v0, 'seconds':time.perf_counter()-start,
            'steps':len(result.t), 'nfev':result.nfev,
            'local_maxima':len(peaks), 'source':'independent_generated_simulation'}

CASES = [
    ['Lightning', 2, 80., 30., 520., 800., 0.],
    ['Lightning', 11, 180., 30., 520., 1500., 12.],
    ['Lightning', 12, 180., 465., 520., 4000., 30.],
    ['Switching', 2, 80., 3700., 22000., 800., 0.],
    ['Switching', 11, 180., 3700., 22000., 1500., 12.],
    ['Switching', 12, 180., 465., 22000., 4000., 30.],
]
ROOT = Path('/tmp/impulsetwin-independent-sim')
if __name__ == '__main__':
    # The fixed feasibility cases and tolerances are written before solving.
    (ROOT/'prototype_protocol.json').write_text(json.dumps({
        'source':'independent_generated_simulation', 'fit_anything':False,
        'scope':'solver feasibility only, not a fresh physical holdout',
        'cases':CASES, 'solvers':[['Radau',1e-9],['BDF',1e-10]],
        'no_production_imports':True},indent=2))
    rows=[]
    for impulse,n,charge,rf,rt,cl,l in CASES:
        row={'case':[impulse,n,charge,rf,rt,cl,l]}
        try:
            first=metrics(n,charge,rf,rt,cl,l,impulse,'Radau',1e-9)
            second=metrics(n,charge,rf,rt,cl,l,impulse,'BDF',1e-10)
            row.update(radau=first,bdf=second,
                relative_difference={key:abs(first[key]-second[key])/abs(first[key]) for key in ['front_us','tail_us','crest_kv']})
        except Exception as error:
            row['failure']=str(error)
        rows.append(row)
    (ROOT/'prototype_results.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows,indent=2))
