"""Additive fault routes. Saved experiments never become trials or corrections."""
import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from .. import storage
from ..diagnostics.reference import snapshot_from_run
from .models import FaultRequest
from .report import csv_text, report_html
from .simulation import reference_view, simulate_fault

router = APIRouter(prefix='/api', tags=['Generated fault tests'])


def _get(kind, rid):
    try:
        return storage.get(rid, kind)
    except KeyError:
        raise HTTPException(404, f'{kind.replace("_", " ")} not found')


def snapshot(run_id, candidate_id):
    run = _get('run', run_id)
    try:
        snap = snapshot_from_run(run, candidate_id)
        # The legacy diagnostic snapshot intentionally copies only its own
        # inputs. This stricter experimental service also preserves topology.
        snap['inputs'] = {**snap['inputs'], 'connection_mode': run['inputs'].get('connection_mode')}
        snap['sha256'] = hashlib.sha256(json.dumps({k: snap[k] for k in ('run_id', 'candidate_id', 'settings',
            'circuit_inputs', 'efficiency', 'profile', 'effective_parameters', 'inputs')},
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return snap
    except (KeyError, ValueError, TypeError) as error:
        raise HTTPException(422, str(error))


@router.get('/runs/{run_id}/candidates/{candidate_id}/fault-tests/reference')
def get_reference(run_id: str, candidate_id: str):
    """Resolve the healthy circuit and illustrative event defaults without saving a fault."""
    snap = snapshot(run_id, candidate_id)
    try:
        return reference_view(snap)
    except (KeyError, ValueError, TypeError) as error:
        raise HTTPException(422, str(error))


@router.post('/runs/{run_id}/candidates/{candidate_id}/fault-tests')
def create_fault(run_id: str, candidate_id: str, body: FaultRequest):
    """Save one independently labelled hypothetical experiment at unchanged charge."""
    snap = snapshot(run_id, candidate_id)
    try:
        result = simulate_fault(snap, body)
        return storage.put('fault_test', uuid.uuid4().hex[:12], result)
    except (KeyError, ValueError, TypeError) as error:
        raise HTTPException(422, str(error))


@router.get('/fault-tests/{experiment_id}')
def get_fault(experiment_id: str):
    return _get('fault_test', experiment_id)


@router.get('/fault-tests/{experiment_id}/json')
def export_json(experiment_id: str):
    record = _get('fault_test', experiment_id)
    return Response(json.dumps(record, indent=2, allow_nan=False), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="fault-test-{record["id"]}.json"'})


@router.get('/fault-tests/{experiment_id}/csv')
def export_csv(experiment_id: str):
    record = _get('fault_test', experiment_id)
    return Response(csv_text(record), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="fault-test-{record["id"]}.csv"'})


@router.get('/fault-tests/{experiment_id}/report', response_class=HTMLResponse)
def export_report(experiment_id: str):
    return report_html(_get('fault_test', experiment_id))
