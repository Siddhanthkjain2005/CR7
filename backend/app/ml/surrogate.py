"""Portable circuit surrogate: dimensionless physics groups -> waveform metrics.

The surrogate reproduces the lumped circuit solver (it is trained on its
simulated outcomes). It is a screening tool only: every setting it shortlists
is re-simulated with the circuit before being shown or recommended.
Weights are stored as plain arrays (npz) so inference needs only numpy and
does not depend on the scikit-learn version used for training.
"""
from functools import lru_cache
from pathlib import Path
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT/'artifacts/models/circuit_surrogate_v1'
L_FLOOR = 1e-12  # dimensionless inductive ratio used when L = 0


def features(stages, front_r_stage, tail_r_stage, stage_c_uf, total_c_pf, l_uh, impulse_type):
    n = np.asarray(stages, float)
    cg = np.asarray(stage_c_uf, float)*1e-6/n
    cl = np.asarray(total_c_pf, float)*1e-12
    rf = np.asarray(front_r_stage, float)*n
    rt = np.asarray(tail_r_stage, float)*n
    cs = cg*cl/(cg+cl)
    ratio = np.maximum(np.asarray(l_uh, float)*1e-6/(rf*rf*cs), L_FLOOR)
    switching = (np.asarray(impulse_type) == 'Switching').astype(float)
    x = np.column_stack([np.log(cg/cl), np.log(rt/rf), np.log(ratio), switching])
    scales = {'front_tau_us': rf*cl*1e6, 'tail_tau_us': rt*(cg+cl)*1e6}
    return x, scales


def targets(front_us, tail_us, crest_kv, stages, charge_kv_stage, efficiency, scales):
    erected = np.asarray(stages, float)*np.asarray(charge_kv_stage, float)*np.asarray(efficiency, float)
    return np.column_stack([np.log(np.asarray(front_us)/scales['front_tau_us']),
                            np.log(np.asarray(tail_us)/scales['tail_tau_us']),
                            np.asarray(crest_kv)/erected])


def untransform(y, stages, charge_kv_stage, efficiency, scales):
    erected = np.asarray(stages, float)*np.asarray(charge_kv_stage, float)*np.asarray(efficiency, float)
    return np.column_stack([np.exp(y[:, 0])*scales['front_tau_us'], np.exp(y[:, 1])*scales['tail_tau_us'], y[:, 2]*erected])


class Surrogate:
    def __init__(self, arrays, meta):
        self.meta = meta
        self.x_mean, self.x_std = arrays['x_mean'], arrays['x_std']
        self.y_mean, self.y_std = arrays['y_mean'], arrays['y_std']
        self.weights = [arrays[f'w{i}'] for i in range(meta['layers'])]
        self.biases = [arrays[f'b{i}'] for i in range(meta['layers'])]
        self.domain = {k: np.asarray(v) for k, v in meta['feature_domain'].items()}

    def raw(self, x):
        h = (x - self.x_mean)/self.x_std
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            h = h @ w + b
            if i < len(self.weights) - 1:
                h = np.tanh(h)
        return h*self.y_std + self.y_mean

    def inside_domain(self, x):
        """Validated support: inside the training feature box (per impulse type)."""
        lower, upper = self.domain['lower'], self.domain['upper']
        return np.all((x[:, :3] >= lower) & (x[:, :3] <= upper), axis=1)

    def predict(self, stages, charge_kv_stage, front_r_stage, tail_r_stage, stage_c_uf, total_c_pf, l_uh,
                efficiency, impulse_type):
        x, scales = features(stages, front_r_stage, tail_r_stage, stage_c_uf, total_c_pf, l_uh, impulse_type)
        metrics = untransform(self.raw(x), stages, charge_kv_stage, efficiency, scales)
        return metrics, self.inside_domain(x)


@lru_cache
def load(path=None):
    folder = Path(path) if path else ARTIFACT
    meta = json.loads((folder/'model.json').read_text(encoding='utf-8'))
    with np.load(folder/'weights.npz') as data:
        arrays = {k: data[k] for k in data.files}
    return Surrogate(arrays, meta)
