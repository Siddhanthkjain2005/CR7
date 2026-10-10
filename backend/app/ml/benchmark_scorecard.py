"""Compare saved evidence only; never run predictions or modify model selection."""
import math

TYPES = ('Lightning', 'Switching')


def compare(tables, model, baseline):
    rows = []
    for impulse in TYPES:
        targets = ('Front time', 'Tail time', 'Crest voltage') if impulse == 'Lightning' else ('Peak time', 'Tail time', 'Crest voltage')
        table = tables.get(impulse, {})
        selected = table.get(model, {}).get('rmse', [])
        reference = table.get(baseline, {}).get('rmse', [])
        for target, name in enumerate(targets):
            current = selected[target] if target < len(selected) else None
            original = reference[target] if target < len(reference) else None
            valid = all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
                        for value in (current, original))
            verdict = 'NOT RECORDED'
            gain = None
            if valid:
                verdict = 'TIE' if math.isclose(current, original, rel_tol=1e-10, abs_tol=1e-12) else 'LOWER ERROR' if current < original else 'HIGHER ERROR'
                gain = 100 * (1 - current / original) if original > 0 else None
            rows.append({'impulse_type': impulse, 'target': name, 'unit': 'kV' if target == 2 else 'µs',
                         'model_rmse': current if valid else None, 'baseline_rmse': original if valid else None,
                         'rmse_reduction_pct': gain, 'verdict': verdict})
    return {'model': model, 'baseline': baseline, 'expected_targets': 6,
            'recorded_targets': sum(row['verdict'] != 'NOT RECORDED' for row in rows),
            'lower_error_targets': sum(row['verdict'] == 'LOWER ERROR' for row in rows),
            'higher_error_targets': sum(row['verdict'] == 'HIGHER ERROR' for row in rows),
            'tied_targets': sum(row['verdict'] == 'TIE' for row in rows), 'targets': rows}


def scorecard(hidden, v2=None):
    result = {'version': 'saved-benchmark-comparison-v1',
              'frozen_v1': {'evidence_type': 'SYNTHETIC FROZEN TEST', 'evaluated_at': hidden.get('evaluated_at'),
                            'comparisons': [compare(hidden.get('metrics', {}), 'Selected hybrid', baseline)
                                            for baseline in ('Physics only', 'Exact workbook kNN')],
                            'scope': 'Saved V1 test only. Exact kNN used all official Train rows; V1 held some Train rows for calibration. Neither is laboratory accuracy or a runtime-gated optimizer score.'},
              'development_v2': None,
              'scope': 'A count of outputs with lower RMSE against a named baseline, not the percentage of correct shots. Test and development evidence remain separate.'}
    if v2 is not None:
        tables = {impulse: data.get('metrics', {}) for impulse, data in v2.get('nested_cv', {}).items()}
        result['development_v2'] = {'evidence_type': 'SYNTHETIC DEVELOPMENT CV',
                                    'comparisons': [compare(tables, 'V2 search', baseline)
                                                    for baseline in ('Matched V1 refit', 'Matched exact kNN')],
                                    'scope': v2.get('evaluation_scope', 'Nested Train CV development; no new final-test or laboratory result.'),
                                    'active_default_changed': False}
    return result
