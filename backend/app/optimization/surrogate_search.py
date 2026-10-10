"""Surrogate-screened network shortlists (evaluation option, not the default search).

For one stage count, every constructible front x tail pair from the counted stock
is scored with the circuit surrogate, and the best pairs are added to the normal
nearest-value shortlist. The optimizer then circuit-solves every pair, so the
surrogate only decides which constructible settings get a full simulation.
"""
import math

import numpy as np

from ..ml.surrogate import load
from ..physics.compliance import RULES
from .networks import networks, nearest_networks

PAIR_LIMIT = 2_000_000


def selector(top_pairs=6):
    model = load()

    def select(req, profile, n, charge, front_stock, tail_stock, rf_target, rt_target):
        fronts = nearest_networks(front_stock, rf_target, req.max_components_per_network, 5)
        tails = nearest_networks(tail_stock, rt_target, req.max_components_per_network, 5)
        all_fronts = networks(tuple(sorted(front_stock.items())), req.max_components_per_network)
        all_tails = networks(tuple(sorted(tail_stock.items())), req.max_components_per_network)
        if not all_fronts or not all_tails or len(all_fronts)*len(all_tails) > PAIR_LIMIT:
            return fronts, tails
        rf = np.repeat([f['equivalent_ohm'] for f in all_fronts], len(all_tails))
        rt = np.tile([t['equivalent_ohm'] for t in all_tails], len(all_fronts))
        stray = req.stray_c_pf + ((profile['base_c_pf'] or 0) if req.include_base_c else 0)
        total = req.load_c_pf + req.divider_c_pf + stray
        size = len(rf)
        metrics, inside = model.predict(np.full(size, n), np.full(size, charge), rf, rt, np.full(size, profile['stage_c_uf']),
                                        np.full(size, total), np.full(size, req.l_uh), np.full(size, req.efficiency),
                                        np.full(size, req.impulse_type))
        rule = RULES[req.impulse_type]
        # Charge needed for the requested crest at this setting, and its hardware limits.
        needed = charge*req.test_kv/np.maximum(metrics[:, 2], 1e-9)
        stage_energy = .5*profile['stage_c_uf']*1e-6*(needed*1e3)**2/1e3
        feasible = ((needed <= profile['stage_kv']) & (stage_energy <= profile['energy_stage_kj'])
                    & (n*stage_energy <= profile['energy_total_kj']) & inside)
        deviation = (np.abs(metrics[:, 0] - rule['front_target_us'])/((rule['front_max_us'] - rule['front_min_us'])/2)
                     + np.abs(metrics[:, 1] - rule['tail_target_us'])/((rule['tail_max_us'] - rule['tail_min_us'])/2))
        order = np.lexsort((deviation, ~feasible))[:top_pairs]
        chosen_f = {round(all_fronts[i//len(all_tails)]['equivalent_ohm'], 8): all_fronts[i//len(all_tails)] for i in order}
        chosen_t = {round(all_tails[i % len(all_tails)]['equivalent_ohm'], 8): all_tails[i % len(all_tails)] for i in order}
        merged_f = {round(x['equivalent_ohm'], 8): x for x in fronts}; merged_f.update(chosen_f)
        merged_t = {round(x['equivalent_ohm'], 8): x for x in tails}; merged_t.update(chosen_t)
        return list(merged_f.values()), list(merged_t.values())

    return select


def exhaustive_selector(pair_limit=400):
    """Every constructible pair, when small enough to circuit-solve exhaustively."""
    def select(req, profile, n, charge, front_stock, tail_stock, rf_target, rt_target):
        all_fronts = networks(tuple(sorted(front_stock.items())), req.max_components_per_network)
        all_tails = networks(tuple(sorted(tail_stock.items())), req.max_components_per_network)
        if len(all_fronts)*len(all_tails) > pair_limit:
            raise ValueError(f'Exhaustive comparison limited to {pair_limit} pairs per stage count.')
        return all_fronts, all_tails
    return select


def catalogue_size(req, front_stock, tail_stock):
    return (len(networks(tuple(sorted(front_stock.items())), req.max_components_per_network)),
            len(networks(tuple(sorted(tail_stock.items())), req.max_components_per_network)))
