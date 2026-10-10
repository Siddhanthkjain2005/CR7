"""Versioned equipment references, separate from generator capability."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def catalog():
    data = json.loads((ROOT / 'config/test_objects.json').read_text(encoding='utf-8'))
    ids = set()
    for obj in data['objects']:
        if obj['id'] in ids:
            raise ValueError('Duplicate test object ID')
        ids.add(obj['id'])
        if obj['status'] not in ('unknown', 'source_verified', 'operator_provided'):
            raise ValueError('Unknown test object reference status')
        value = obj['recommended_test_level_kv']
        if value is not None and (value <= 0 or not obj['source'] or obj['status'] == 'unknown'):
            raise ValueError('A test level needs a positive value, source and explicit status')
    return data


def validate_request(req, profile, data=None):
    data = catalog() if data is None else data
    if not profile['enabled']:
        raise ValueError('Profile is incomplete. Verified capacitance, energy and inventory are required.')
    if not profile['voltage_min_kv'] <= req.test_kv <= profile['voltage_max_kv']:
        raise ValueError('Requested test voltage is outside selected generator profile capability.')
    # The workbook crest is exactly erected charge times efficiency. A passive
    # RLC load can overshoot that initial voltage, so circuit feasibility must
    # be decided from its solved charge and the actual voltage/energy limits.
    stages = min(profile['max_stages'], req.stage_max or profile['max_stages'])
    if req.solver == 'reference' and req.test_kv > stages * profile['stage_kv'] * req.efficiency:
        raise ValueError('Requested test voltage exceeds available stages and charging capability at the entered efficiency.')
    obj = None
    if req.test_object_id:
        obj = next((o for o in data['objects'] if o['id'] == req.test_object_id), None)
        if obj is None:
            raise ValueError('Unknown test object reference ID.')
        if obj['impulse_type'] != req.impulse_type:
            raise ValueError('Test object reference impulse type does not match the request.')
    level = obj['recommended_test_level_kv'] if obj else None
    source = obj['source'] if obj else None
    status = obj['status'] if obj else 'unknown'
    if req.equipment_reference_kv is not None:
        level, source, status = req.equipment_reference_kv, req.equipment_reference_source, 'operator_provided'
    mismatch = level is not None and abs(req.test_kv / level - 1) > data['mismatch_fraction']
    message = (f'Requested {req.test_kv:g} kV differs from recorded reference {level:g} kV. Source: {source}. Confirm the entered level is intentional.'
               if mismatch else 'Requested level matches the recorded reference within the application review threshold.'
               if level is not None else 'Equipment test-level reference unavailable. The entered target voltage is used.')
    return {'catalog_version': data['version'], 'test_object_id': req.test_object_id,
            'status': status, 'reference_kv': level, 'source': source,
            'source_version': obj.get('source_version') if obj and status != 'operator_provided' else None,
            'mismatch': mismatch, 'confirmation_required': mismatch and not req.confirm_reference_mismatch,
            'confirmed': bool(mismatch and req.confirm_reference_mismatch), 'message': message}
