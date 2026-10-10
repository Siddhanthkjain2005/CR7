"""Fit a few effective generator parameters from calibration shots (grey-box).

The lumped circuit keeps its topology. Three effective parameters absorb what
the model cannot know in advance about the real machine:

  * loss_scale   multiplies the assumed extra loss factor (crest level),
  * extra_load_pf adds load-side capacitance (unmodelled stray/base, sets front),
  * tail_scale   multiplies the total tail resistance (extra discharge paths).

They are fitted by bounded least squares to the measured crest, front/peak and
tail of one or more calibration shots at their as-fired settings, with a weak
prior toward "no change". Unlike a per-setting metric offset, the fitted
parameters are used at any other setting of the same generator, so a
reduced-voltage calibration shot informs the full-voltage recommendation.
"""
import numpy as np
from scipy.optimize import least_squares

from .circuit import simulate

VERSION = 'effective-parameter-calibration-v1'
KEYS = ('front_us', 'tail_us', 'crest_kv')
NAMES = ('loss_scale', 'extra_load_pf', 'tail_scale')
NEUTRAL = {'loss_scale': 1.0, 'extra_load_pf': 0.0, 'tail_scale': 1.0}
PRIOR_WEIGHT = 0.02  # weak pull toward the uncalibrated model; keeps the fit identifiable


def bounds_for(load_pf):
    return ([0.6, -0.4*load_pf, 0.5], [1.25, 1.5*load_pf, 1.6])


def predict(shot, params):
    """Circuit metrics for one shot description with effective parameters applied."""
    p = {**NEUTRAL, **(params or {})}
    total = shot['total_c_pf'] + p['extra_load_pf']
    if total <= 0:
        raise ValueError('Effective load capacitance must stay positive.')
    eff = shot['efficiency']*p['loss_scale']
    return simulate(shot['stages'], shot['charge_kv_stage'], shot['front_r_stage'], shot['tail_r_stage']*p['tail_scale'],
                    shot['stage_c_uf'], total, shot['l_uh'], eff, shot['impulse_type'], False)


def fit(shots):
    """shots: dicts with circuit inputs (as fired) and 'measured' metrics."""
    if not shots:
        raise ValueError('At least one calibration shot is required.')
    load = float(np.mean([s['total_c_pf'] for s in shots]))
    lower, upper = bounds_for(load)
    scale = np.array([1.0, load, 1.0])

    def residuals(x):
        params = dict(zip(NAMES, x*scale))
        out = []
        for s in shots:
            try:
                m = predict(s, params)
            except ValueError:
                return np.full(3*len(shots) + 3, 10.0)
            out += [m[k]/s['measured'][k] - 1 for k in KEYS]
        prior = PRIOR_WEIGHT*(x - np.array([1.0, 0.0, 1.0]))
        return np.r_[out, prior]

    x0 = np.array([1.0, 0.0, 1.0])
    result = least_squares(residuals, x0, bounds=(np.array(lower)/scale, np.array(upper)/scale), x_scale='jac',
                           xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=400)
    params = dict(zip(NAMES, (result.x*scale).tolist()))
    fitted = [predict(s, params) for s in shots]
    residual_pct = [{k: 100*(f[k]/s['measured'][k] - 1) for k in KEYS} for f, s in zip(fitted, shots)]
    at_bound = [name for name, v, lo, hi in zip(NAMES, result.x*scale, lower, upper) if abs(v - lo) < 1e-6*max(1, abs(lo)) or abs(v - hi) < 1e-6*max(1, abs(hi))]
    jac = result.jac[:3*len(shots)]
    condition = float(np.linalg.cond(jac)) if jac.size else None
    return {'version': VERSION, 'parameters': params, 'shots': len(shots), 'residual_pct': residual_pct,
            'parameters_at_bound': at_bound, 'jacobian_condition': condition,
            'converged': bool(result.success)}
