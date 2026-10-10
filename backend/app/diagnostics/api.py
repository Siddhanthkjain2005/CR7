"""Waveform Diagnostics API (additive; mounted under /api/diagnostics).

Records are versioned and append-only:
  diagnostic               session header revisions  (<session>.<revision>)
  diagnostic_reference     reference snapshot (+ as-fired settings and their prediction)
  diagnostic_upload        declared origin, original file checksum and metadata
  diagnostic_digitization  transforms, axis calibration, samples, edits, uncertainty, quality
  diagnostic_comparison    alignment, metrics, residuals
  diagnostic_investigation hypotheses, fits, identifiability, verdict and findings
Downstream records name the records they were computed from, so a changed input
marks them stale instead of silently mixing versions.
"""
import base64
import hashlib
import html
import io
import json
import math
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .. import storage
from ..trial_provenance import validate_csv_provenance
from . import VERSION, imaging, digitize, jobs
from .compare import compare as run_compare
from .findings import findings as make_findings, hypothetical_parameters
from .inverse import investigate as run_investigation, Cancelled
from .reference import snapshot_from_run, as_fired as record_as_fired, FIRED_KEYS
from .report import report_html

router = APIRouter(prefix='/api/diagnostics', tags=['Waveform Diagnostics'])
ORIGINS = {'physical_experiment': 'Physical experiment (declared)', 'software_simulation': 'Software simulation (declared)',
           'demonstration': 'Demonstration (declared)', 'unknown': 'Unknown origin'}
CSV_LIMIT = 5_000_000


def root():
    from .. import main
    return main.ROOT


def now():
    return datetime.now(timezone.utc).isoformat()


def finite(value):
    """Non-finite numbers (an unbounded uncertainty, a singular matrix) are stored as null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    if isinstance(value, np.ndarray):
        return [finite(v) for v in value.tolist()]
    return value


def fail(error, status=422):
    raise HTTPException(status, str(error))


def get_record(kind, rid):
    try:
        return storage.get(rid, kind)
    except KeyError:
        raise HTTPException(404, f'{kind.replace("_", " ")} not found')


def revisions(sid):
    if not sid or not all(c.isalnum() for c in sid):
        raise HTTPException(404, 'Diagnostic session not found')
    history = storage.list_prefix('diagnostic', sid + '.')
    if not history:
        raise HTTPException(404, 'Diagnostic session not found')
    return history


def advance(sid, note, **changes):
    history = revisions(sid)
    latest = history[-1]
    header = {k: v for k, v in latest.items() if k not in ('id', 'created_at')}
    header.update(changes, revision=len(history) + 1, note=note)
    return storage.put('diagnostic', f'{sid}.{len(history) + 1:04d}', header)


def current(header, kind, key):
    rid = header.get(key)
    return storage.get(rid, kind) if rid else None


def staleness(header, reference, source, comparison, investigation):
    stale = {}
    if comparison:
        why = []
        if comparison.get('reference_id') != header.get('reference_id'):
            why.append('the reference or as-fired settings changed')
        if comparison.get('source_id') != (header.get('digitization_id')):
            why.append('the uploaded waveform or its digitization changed')
        if why:
            stale['comparison'] = 'Out of date: ' + ' and '.join(why) + '. Compare again.'
    if investigation:
        if investigation.get('comparison_id') != header.get('comparison_id') or 'comparison' in stale:
            stale['investigation'] = 'Out of date: the comparison it was computed from has changed. Investigate again.'
    return stale


def session_view(sid):
    history = revisions(sid)
    header = history[-1]
    reference = current(header, 'diagnostic_reference', 'reference_id')
    upload = current(header, 'diagnostic_upload', 'upload_id')
    source = current(header, 'diagnostic_digitization', 'digitization_id')
    comparison = current(header, 'diagnostic_comparison', 'comparison_id')
    investigation = current(header, 'diagnostic_investigation', 'investigation_id')
    stale = staleness(header, reference, source, comparison, investigation)
    step = ('reference' if not reference else 'upload' if not upload else 'calibrate' if not source
            else 'compare' if not comparison or 'comparison' in stale else 'investigate' if not investigation or 'investigation' in stale
            else 'findings')
    return {'session': header, 'reference': reference, 'upload': upload, 'digitization': source, 'comparison': comparison,
            'investigation': investigation, 'stale': stale, 'next_step': step,
            'history': [{'revision': h['revision'], 'created_at': h['created_at'], 'note': h.get('note')} for h in history],
            'version': VERSION}


# ------------------------------------------------------------------ sessions

class CreateSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(default='', max_length=128)
    title: str = Field(default='', max_length=120)


@router.post('')
def create_session(body: CreateSession):
    """Start from a saved run and candidate (a new reference comes from the existing optimizer first)."""
    run = get_record('run', body.run_id)
    try:
        snap = snapshot_from_run(run, body.candidate_id)
    except (KeyError, ValueError) as error:
        fail(error)
    reference = storage.put('diagnostic_reference', uuid.uuid4().hex[:12], {**snap, 'as_fired': None, 'revision_note': 'Created from saved run'})
    sid = uuid.uuid4().hex[:12]
    title = body.title.strip() or f"{snap['impulse_type']} {snap['test_kv']:g} kV · {snap['profile_label']}"
    storage.put('diagnostic', f'{sid}.0001', {'session_id': sid, 'revision': 1, 'title': title, 'reference_id': reference['id'],
                                             'upload_id': None, 'digitization_id': None, 'comparison_id': None,
                                             'investigation_id': None, 'note': 'Reference chosen from saved run', 'version': VERSION})
    return session_view(sid)


@router.get('')
def list_sessions(limit: int = 50):
    latest = {}
    for record in storage.list_records('diagnostic', None):
        sid = record['session_id']
        if sid not in latest or record['revision'] > latest[sid]['revision']:
            latest[sid] = record
    rows = sorted(latest.values(), key=lambda r: r['created_at'], reverse=True)[:max(1, min(limit, 200))]
    return [{'session_id': r['session_id'], 'title': r['title'], 'updated_at': r['created_at'], 'revision': r['revision'],
             'note': r.get('note'), 'demo': bool(r.get('demo'))} for r in rows]


@router.get('/{sid}')
def get_session(sid: str):
    return session_view(sid)


class AsFired(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    values: dict[str, float] = Field(default_factory=dict)
    uncertain: list[str] = Field(default_factory=list, max_length=12)
    note: str = Field(default='', max_length=500)


@router.post('/{sid}/as-fired')
def set_as_fired(sid: str, body: AsFired):
    """Record the settings actually fired; the circuit is re-solved for them (new reference revision)."""
    header = revisions(sid)[-1]
    reference = get_record('diagnostic_reference', header['reference_id'])
    snap = {k: v for k, v in reference.items() if k not in ('id', 'created_at', 'as_fired', 'revision_note')}
    try:
        fired = record_as_fired(snap, body.values, body.uncertain) if body.values or body.uncertain else None
    except (KeyError, ValueError) as error:
        fail(error)
    if fired:
        fired['note_from_operator'] = body.note.strip() or None
    new = storage.put('diagnostic_reference', uuid.uuid4().hex[:12], {**snap, 'as_fired': fired, 'parent_reference_id': reference['id'],
                      'revision_note': 'As-fired settings recorded' if fired else 'As-fired settings cleared'})
    advance(sid, 'As-fired settings recorded' if fired else 'As-fired settings cleared', reference_id=new['id'])
    return session_view(sid)


# ------------------------------------------------------------------ upload

def _store_bytes(sid, content, extension):
    digest = hashlib.sha256(content).hexdigest()
    folder = root() / 'artifacts' / 'diagnostics' / sid
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{digest}.{extension}'          # never the uploaded filename
    if not path.exists():
        path.write_bytes(content)
    return digest, str(path.relative_to(root()))


def _read_original(upload):
    path = (root() / upload['stored_path']).resolve()
    if not path.is_relative_to(root().resolve()) or not path.is_file():
        raise HTTPException(409, 'The original upload is missing from storage.')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != upload['sha256']:
        raise HTTPException(409, 'The stored upload no longer matches its checksum; it was changed outside the application.')
    return content


@router.post('/{sid}/upload')
async def upload(sid: str, file: UploadFile = File(...), origin: str = Form('unknown'), captured_at: str | None = Form(None),
                 instrument: str | None = Form(None), session_label: str | None = Form(None), shot_label: str | None = Form(None),
                 notes: str | None = Form(None), time_column: str = Form('time_us'), voltage_column: str = Form('voltage_kv'),
                 time_unit: str = Form('us'), voltage_unit: str = Form('kV'), voltage_side: str = Form('high_voltage'),
                 divider_ratio: float = Form(1.), divider_ratio_source: str | None = Form(None), baseline_kv: float = Form(0.),
                 onset_us: float = Form(0.), expected_polarity: str = Form('unknown')):
    header = revisions(sid)[-1]
    if origin not in ORIGINS:
        fail('Declare the origin: physical experiment, software simulation, demonstration or unknown.')
    if expected_polarity not in ('positive', 'negative', 'unknown'):
        fail('Expected polarity must be positive, negative or unknown.')
    if captured_at:
        try:
            datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
        except ValueError:
            fail('Capture time must be an ISO 8601 timestamp or omitted.')
    content = await file.read(imaging.MAX_BYTES + 1)
    if not content:
        fail('The file is empty.')
    kind = imaging.sniff(content)
    meta = {'origin': origin, 'origin_label': ORIGINS[origin], 'captured_at': captured_at, 'instrument': instrument,
            'session_label': session_label, 'shot_label': shot_label, 'notes': notes,
            'original_filename': (file.filename or '')[:200], 'declared_content_type': file.content_type,
            'expected_polarity': expected_polarity,
            'origin_scope': 'The origin is the uploader\'s declaration. A photo or file does not verify laboratory provenance.'}
    if kind:
        try:
            info = imaging.inspect(content)
        except ValueError as error:
            fail(error)
        digest, path = _store_bytes(sid, content, {'png': 'png', 'jpeg': 'jpg', 'webp': 'webp'}[kind])
        record = {**meta, 'source': 'image', 'image': info, 'sha256': digest, 'stored_path': path, 'bytes': len(content),
                  'evidence_class': 'image_digitized', 'label': 'Digitized from image — approximate',
                  'admission': 'Image-derived samples are lower-quality evidence. They never enter calibration, parameter '
                               'fitting or laboratory-accuracy workflows.'}
        saved = storage.put('diagnostic_upload', uuid.uuid4().hex[:12], record)
        advance(sid, 'Image uploaded', upload_id=saved['id'], digitization_id=None)
        return session_view(sid)
    if len(content) > CSV_LIMIT:
        fail('CSV exceeds the 5 MB upload limit.', 413)
    try:
        text = content.decode('utf-8-sig')
    except UnicodeError:
        fail('Upload a PNG, JPEG or WebP image, or a UTF-8 CSV with time and voltage columns.')
    reference = get_record('diagnostic_reference', header['reference_id'])
    try:
        provenance = validate_csv_provenance(text, reference['run_id'], reference['candidate_id'], time_unit, voltage_unit)
        frame = pd.read_csv(io.StringIO(text), comment='#')
        t = frame[time_column].to_numpy(float) * digitize.TIME_UNITS[time_unit]
        axes = {'time_unit': time_unit, 'voltage_unit': voltage_unit, 'voltage_side': voltage_side,
                'divider_ratio': divider_ratio, 'divider_ratio_source': divider_ratio_source}
        _validate_voltage_side(axes)
        scale = digitize.VOLT_UNITS[voltage_unit] * (divider_ratio if voltage_side == 'instrument' else 1.)
        v = frame[voltage_column].to_numpy(float) * scale
        if len(t) < 10 or len(t) != len(v) or not np.isfinite(t).all() or not np.isfinite(v).all() or not (np.diff(t) > 0).all():
            raise ValueError('The CSV needs at least 10 finite samples with strictly increasing time.')
        if len(t) > 2_000_000:
            raise ValueError('The CSV has more than 2 million samples.')
    except (KeyError, ValueError, TypeError, pd.errors.ParserError) as error:
        fail(f'CSV validation failed: {error}')
    digest, path = _store_bytes(sid, content, 'csv')
    record = {**meta, 'source': 'csv', 'sha256': digest, 'stored_path': path, 'bytes': len(content), 'provenance': provenance,
              'evidence_class': 'csv_declared_' + origin, 'label': 'Uploaded samples (' + ORIGINS[origin].lower() + ')',
              'admission': 'Diagnostics do not create corrections. To use a measured shot for calibration or evaluation, '
                           'import it on Compare measurement, where the shared admission checks apply.'}
    saved = storage.put('diagnostic_upload', uuid.uuid4().hex[:12], record)
    impulse = reference['impulse_type']
    an = digitize.analyse_samples(t, v, impulse, baseline_kv, onset_us, expected_polarity, check_flat_crest=True)
    samples = {'time_us': t.tolist(), 'voltage_kv': v.tolist(), 'sigma_t_us': None, 'sigma_v_kv': None,
               'kind': ['observed'] * len(t)}
    quality = {'version': digitize.VERSION, 'flags': an['issues'], 'notes': an['notes'],
               'metric_availability': {k: bool(x) for k, x in an['available'].items()},
               'quantitative_comparison_allowed': (an['metrics'] or an.get('partial')) is not None
                                                 and not any(i['code'] in ('polarity_mismatch', 'crest_unresolved', 'too_few_samples', 'clipping') for i in an['issues']),
               'evidence_class': record['evidence_class'], 'label': record['label'],
               'scope': 'Samples are the uploaded values after the stated unit and divider conversion; nothing is resampled or smoothed.'}
    digit = storage.put('diagnostic_digitization', uuid.uuid4().hex[:12], {
        'source': 'csv', 'upload_id': saved['id'], 'upload_sha256': digest, 'samples': samples,
        'processing': {'time_column': time_column, 'voltage_column': voltage_column, 'time_unit': time_unit, 'voltage_unit': voltage_unit,
                       'voltage_side': voltage_side, 'divider_ratio_applied': divider_ratio if voltage_side == 'instrument' else 1.,
                       'divider_ratio_source': divider_ratio_source},
        'baseline_kv': baseline_kv, 'onset_us': onset_us, 'expected_polarity': expected_polarity,
        'analysis': {k: an.get(k) for k in ('metrics', 'partial', 'available', 'issues', 'notes', 'detected_polarity')},
        'quality': quality})
    advance(sid, 'CSV uploaded', upload_id=saved['id'], digitization_id=digit['id'])
    return session_view(sid)


def _validate_voltage_side(axes):
    side = axes.get('voltage_side'); ratio = float(axes.get('divider_ratio') or 1)
    if side not in ('high_voltage', 'instrument'):
        raise ValueError('Say whether the values are the high voltage or the instrument (divider output) signal.')
    if not (math.isfinite(ratio) and ratio > 0):
        raise ValueError('The divider ratio must be a positive number.')
    if side == 'high_voltage' and ratio != 1:
        raise ValueError('The values already are high voltage. Applying a divider ratio as well would count the divider '
                         'twice; set the ratio to 1 or choose "instrument signal".')
    if side == 'instrument' and ratio != 1 and not str(axes.get('divider_ratio_source') or '').strip():
        raise ValueError('Give the source of the divider ratio (for example the divider certificate).')


@router.get('/{sid}/image/original')
def original_image(sid: str):
    header = revisions(sid)[-1]
    up = current(header, 'diagnostic_upload', 'upload_id')
    if not up or up['source'] != 'image':
        raise HTTPException(404, 'This session has no uploaded image.')
    return Response(_read_original(up), media_type=up['image']['media_type'], headers={'Cache-Control': 'no-store'})


class Transforms(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    corners: list[list[float]] | None = None
    rotate_deg: float = 0.
    crop: list[float] | None = None


def _working(sid, transforms):
    header = revisions(sid)[-1]
    up = current(header, 'diagnostic_upload', 'upload_id')
    if not up or up['source'] != 'image':
        raise HTTPException(409, 'Upload an image first.')
    rgb = imaging.oriented(_read_original(up))
    try:
        work, record = imaging.apply(rgb, transforms.model_dump(exclude_none=True) if transforms else {})
    except ValueError as error:
        fail(error)
    if up['image'].get('exif_orientation', 1) != 1:
        record['steps'].insert(0, {'step': 'exif_orientation', 'value': up['image']['exif_orientation']})
    return up, rgb, work, record


def _preview(work, limit=1600):
    from PIL import Image
    scale = min(1., limit / max(work.shape[:2]))
    image = Image.fromarray(work)
    if scale < 1:
        image = image.resize((max(1, int(work.shape[1] * scale)), max(1, int(work.shape[0] * scale))), Image.Resampling.LANCZOS)
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode(), scale


@router.post('/{sid}/image/preview')
def image_preview(sid: str, body: Transforms):
    """Working image after the recorded transforms, plus suggestions the user must confirm."""
    up, _, work, record = _working(sid, body)
    data, scale = _preview(work)
    return {'png_base64': data, 'preview_scale': scale, 'transform': record,
            'suggestions': suggestions(work), 'original_size': [up['image']['width'], up['image']['height']]}


def suggestions(work):
    """Deskew angle, plot frame, gridlines and candidate trace colours. Suggestions only."""
    g = imaging.gray(work)
    bg = imaging.background_color(work)
    dark = np.abs(g - imaging.gray(bg[None, None, :].astype(np.uint8))[0, 0]) > 60
    h, w = dark.shape
    rows = dark.sum(axis=1); cols = dark.sum(axis=0)
    long_rows = [int(i) for i in np.flatnonzero(rows > .5 * w)]
    long_cols = [int(i) for i in np.flatnonzero(cols > .5 * h)]
    frame = None
    if len(long_rows) >= 2 and len(long_cols) >= 2:
        frame = [long_cols[0], long_rows[0], long_cols[-1], long_rows[-1]]
    def grid_positions(profile, size):
        idx = np.flatnonzero(profile > .35 * size)
        groups = np.split(idx, np.flatnonzero(np.diff(idx) > 2) + 1) if len(idx) else []
        return [float(gp.mean()) for gp in groups if len(gp)]
    gx, gy = grid_positions(cols, h), grid_positions(rows, w)
    spacing = lambda p: np.diff(p) if len(p) > 2 else np.array([])
    log_hint = False
    sx = spacing(gx)
    if len(sx) >= 4 and sx.std() / max(sx.mean(), 1e-9) > .25:
        log_hint = True
    # Candidate colours: saturated pixels clustered coarsely.
    flat = work.reshape(-1, 3).astype(int)
    sat = flat.max(axis=1) - flat.min(axis=1)
    coloured = flat[sat > 60]
    palette = []
    if len(coloured):
        keys, counts = np.unique(coloured // 48, axis=0, return_counts=True)
        for k in np.argsort(-counts)[:5]:
            if counts[k] > 50:
                palette.append({'rgb': (keys[k] * 48 + 24).tolist(), 'pixels': int(counts[k])})
    return {'deskew': imaging.deskew(work), 'plot_frame_px': frame, 'gridlines_x_px': gx[:40], 'gridlines_y_px': gy[:40],
            'possibly_logarithmic_time_axis': log_hint, 'trace_colours': palette, 'ocr': ocr_ticks(work),
            'note': 'Suggestions only. Confirm the plot area, anchors, units and axis type yourself before extraction.'}


def ocr_ticks(work):
    """Optional tick-label reading with a local Tesseract binary. Never required, never trusted without confirmation."""
    binary = shutil.which('tesseract')
    if not binary:
        return {'available': False, 'message': 'Local OCR (Tesseract) is not installed. Enter axis values manually.'}
    try:
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = f'{folder}/plot.png'
            Image.fromarray(work).save(path)
            out = subprocess.run([binary, path, 'stdout', '--psm', '11', 'tsv'], capture_output=True, text=True, timeout=20)
        words = []
        for line in out.stdout.splitlines()[1:]:
            parts = line.split('\t')
            if len(parts) == 12 and parts[11].strip():
                text = parts[11].strip().replace('−', '-')
                try:
                    value = float(text)
                except ValueError:
                    continue
                x, y, w_, h_ = (int(parts[i]) for i in (6, 7, 8, 9))
                words.append({'value': value, 'text': text, 'box_px': [x, y, x + w_, y + h_], 'confidence': float(parts[10])})
        return {'available': True, 'numbers': words[:60],
                'message': 'Numbers read locally from the image. They are suggestions; confirm each anchor value.'}
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return {'available': False, 'message': f'Local OCR failed: {error}. Enter axis values manually.'}


class Digitize(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    transforms: Transforms = Field(default_factory=Transforms)
    plot_box: list[float] | None = None
    seed: list[float] = Field(min_length=2, max_length=2)
    tolerance: float = Field(default=28., ge=5, le=80)
    edits: dict = Field(default_factory=dict)
    axes: dict
    baseline_kv: float = 0.
    onset_us: float = 0.
    expected_polarity: str = 'unknown'


@router.post('/{sid}/digitize')
def digitize_image(sid: str, body: Digitize):
    """Extract the selected curve with the confirmed calibration; keeps transforms, edits and quality."""
    header = revisions(sid)[-1]
    reference = get_record('diagnostic_reference', header['reference_id'])
    up, _, work, transform = _working(sid, body.transforms)
    edits = {'erase': [list(map(float, z)) for z in body.edits.get('erase', [])][:200],
             'add': [list(map(float, p)) for p in body.edits.get('add', [])][:2000]}
    if body.expected_polarity not in ('positive', 'negative', 'unknown'):
        fail('Expected polarity must be positive, negative or unknown.')
    try:
        cal = digitize.calibration(body.axes)
        ex = digitize.extract(work, body.seed, plot_box=body.plot_box, tolerance=body.tolerance, edits=edits)
        phys = digitize.physical_samples(cal, ex)
    except (KeyError, TypeError, ValueError) as error:
        fail(error)
    impulse = reference['impulse_type']
    an = digitize.analyse_samples(phys['time_us'], phys['voltage_kv'], impulse, body.baseline_kv, body.onset_us,
                                  body.expected_polarity, sample_sigma_kv=float(np.median(phys['sigma_v_kv'])),
                                  us_per_px=cal['us_per_px'], thickness_px=ex['thickness_px'])
    box = ex['plot_box']
    quality = digitize.quality(cal, ex, phys, an, impulse, int(box[2] - box[0]))
    matrix = np.array(transform['working_to_original'])
    original_xy = imaging.map_points(matrix, np.c_[phys['pixel_x'], phys['pixel_y']]).tolist()
    record = {'source': 'image', 'upload_id': up['id'], 'upload_sha256': up['sha256'], 'transform': transform,
              'plot_box': box, 'seed': body.seed, 'tolerance': body.tolerance, 'edits': edits, 'axes': body.axes,
              'calibration': {k: cal[k] for k in ('us_per_px', 'kv_per_px', 'time_direction', 'voltage_direction',
                                                  'voltage_scale_applied', 'voltage_side', 'mode', 'anchor_uncertainty_px',
                                                  'x_anchors', 'y_anchors')},
              'extraction': {k: ex[k] for k in ('colour_rgb', 'thickness_px', 'columns', 'column_coverage', 'gaps_px',
                                                'removed_by_edit', 'manual_points', 'flags', 'notes', 'steep_columns', 'max_jump_px')},
              'samples': {k: phys[k] for k in ('time_us', 'voltage_kv', 'sigma_t_us', 'sigma_v_kv', 'independent_sigma_t_us',
                                               'independent_sigma_v_kv', 'kind')},
              'overlay': {'working_px': np.c_[phys['pixel_x'], phys['pixel_y']].tolist(), 'original_px': original_xy},
              'baseline_kv': body.baseline_kv, 'onset_us': body.onset_us, 'expected_polarity': body.expected_polarity,
              'analysis': {k: an.get(k) for k in ('metrics', 'partial', 'available', 'issues', 'notes', 'detected_polarity', 'rise_30_90_px')},
              'quality': quality, 'label': 'Digitized from image — approximate', 'evidence_class': 'image_digitized'}
    saved = storage.put('diagnostic_digitization', uuid.uuid4().hex[:12], finite(record))
    advance(sid, 'Trace digitized', digitization_id=saved['id'])
    return session_view(sid)


# ------------------------------------------------------------------ compare

class CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    alignment: dict = Field(default_factory=lambda: {'basis': 'none', 'time_shift_us': 0.})
    excluded_ranges_us: list[list[float]] = Field(default_factory=list, max_length=20)


def prediction_for(reference):
    if reference.get('as_fired'):
        return reference['as_fired']['prediction'], 'as_fired'
    return reference['prediction'], 'recommended'


@router.post('/{sid}/compare')
def compare_waveforms(sid: str, body: CompareRequest):
    header = revisions(sid)[-1]
    reference = get_record('diagnostic_reference', header['reference_id']) if header.get('reference_id') else None
    source = current(header, 'diagnostic_digitization', 'digitization_id')
    if not reference or not source:
        fail('Choose a reference and upload (and digitize) a waveform first.', 409)
    prediction, basis = prediction_for(reference)
    samples = source['samples']
    t = np.asarray(samples['time_us']); v = np.asarray(samples['voltage_kv'])
    crest = prediction['metrics']['crest_kv']
    pre = (v - source['baseline_kv'])[t < source['onset_us']]
    noise = float(1.4826 * np.median(np.abs(np.diff(pre) - np.median(np.diff(pre)))) / math.sqrt(2)) if len(pre) > 20 else 0.
    tolerance = max(noise, .01 * crest)
    for pair in body.excluded_ranges_us:
        if len(pair) != 2:
            fail('Each excluded range needs a start and an end time.')
    try:
        result = run_compare(reference, prediction['waveform'], samples, impulse_type=reference['impulse_type'],
                             baseline_kv=source['baseline_kv'], onset_us=source['onset_us'],
                             expected_polarity=source.get('expected_polarity'), alignment=body.alignment,
                             excluded_ranges=body.excluded_ranges_us,
                             quantitative_allowed=source['quality']['quantitative_comparison_allowed'],
                             sample_sigma=tolerance if samples.get('sigma_v_kv') is None else None,
                             pixel=({'us_per_px': source['calibration']['us_per_px'], 'thickness_px': source['extraction']['thickness_px']}
                                    if source['source'] == 'image' else None))
    except (KeyError, ValueError) as error:
        fail(error)
    result.update(reference_id=reference['id'], source_id=source['id'], prediction_basis=basis,
                  prediction_label=prediction['label'], uncertainty_basis=(
                      'Pixel uncertainty from the digitization.' if source['source'] == 'image' else
                      f'Comparison tolerance of {tolerance:.4g} kV: the larger of the pre-onset noise and 1% of the predicted '
                      'crest. It is a stated tolerance, not a measured instrument uncertainty.'),
                  diagnosis_limited=None if reference.get('as_fired') else
                  'The settings actually fired were not recorded. The comparison uses the recommended settings; hardware diagnosis is limited.',
                  evidence_label=source.get('label') or source['quality'].get('label'))
    saved = storage.put('diagnostic_comparison', uuid.uuid4().hex[:12], finite(result))
    advance(sid, 'Compared with the circuit prediction', comparison_id=saved['id'])
    return session_view(sid)


# ------------------------------------------------------------------ investigate

@router.post('/{sid}/investigate')
def start_investigation(sid: str):
    header = revisions(sid)[-1]
    view = session_view(sid)
    comparison = view['comparison']
    if not comparison or 'comparison' in view['stale']:
        fail('Compare the waveform with the current reference first.', 409)
    if not comparison.get('quantitative_allowed'):
        reasons = [p['message'] for p in comparison.get('plausibility') or []]
        if comparison.get('polarity_issue'):
            reasons.append(comparison['polarity_issue']['message'])
        blocking = set(view['digitization']['quality'].get('blocking_reasons') or [])
        reasons += [f['message'] for f in (view['digitization']['quality'].get('flags') or [])
                    if f['code'] in blocking | {'clipping', 'multiple_same_colour_curves', 'crest_unresolved', 'too_few_samples'}]
        fail('Quantitative diagnosis is disabled for this waveform: ' + (' '.join(reasons[:3]) or
             'the recording does not support a quantitative comparison.'), 409)
    reference = view['reference']
    prediction, basis = prediction_for(reference)
    fired = reference.get('as_fired')
    base = prediction['circuit_args']
    observed = comparison['observed']
    predicted = {**comparison['predicted_metrics'], 'time_us': prediction['waveform']['time_us'],
                 'voltage_kv': prediction['waveform']['voltage_kv']}

    def work(progress, cancel):
        result = run_investigation(base, observed, predicted, reference['impulse_type'],
                                   uncertain=(fired or {}).get('uncertain_fields', []), as_fired_recorded=bool(fired),
                                   profile=reference['profile'], progress=progress, cancel=cancel)
        if cancel.is_set():
            return None
        result['findings'] = make_findings(result, base, comparison, reference)
        review = [i['message'] for i in comparison['observed_analysis']['issues']
                  if i['code'] in ('disconnected_rising_limb', 'two_stage_rise', 'dip_after_90_percent')]
        flagged = [r['label'] for r in comparison['metrics'] if r['status'] == 'Requires review']
        if review or flagged:
            result['verdict']['requires_review'] = (
                'Requires review: ' + (', '.join(flagged) + ' ' if flagged else '') +
                'carry review flags on the recording itself (for example a precursor or recrossing, which can lie before '
                'the entered onset and outside the fitted window). The verdict above describes the compared impulse only.')
            result['verdict']['review_flags'] = review
        # Fitted explanatory curves, labelled separately (only after diagnosis).
        from .inverse import model_curve
        grid = np.asarray(prediction['waveform']['time_us'])
        curves = []
        for h in result['hypotheses']:
            if h.get('status') in ('Possible cause', 'Several explanations fit', 'Consistent with this waveform') and h['id'] != 'baseline':
                params = {k: x for k, x in h['parameters'].items() if k != 'stages'}
                try:
                    curves.append({'hypothesis_id': h['id'], 'label': f"Fitted explanation — {h['title']} (hypothetical)",
                                   'time_us': grid.tolist(), 'voltage_kv': model_curve(base, params, grid, h.get('stages')).tolist()})
                except ValueError:
                    continue
        result['fitted_curves'] = curves[:4]
        result.update(comparison_id=comparison['id'], reference_id=reference['id'], prediction_basis=basis,
                      circuit_args=base, diagnosis_limited=comparison.get('diagnosis_limited'))
        saved = storage.put('diagnostic_investigation', uuid.uuid4().hex[:12], finite(result))
        advance(sid, 'Possible causes investigated', investigation_id=saved['id'])
        return saved['id']
    try:
        job_id = jobs.start('investigation', work, label=header['title'])
    except ValueError as error:
        fail(error, 429)
    return {'job_id': job_id, 'session_id': sid}


@router.get('/jobs/{job_id}')
def job_status(job_id: str):
    try:
        return jobs.view(job_id)
    except KeyError:
        raise HTTPException(404, 'Job not found (jobs are kept in memory until the server restarts).')


@router.post('/jobs/{job_id}/cancel')
def job_cancel(job_id: str):
    try:
        return jobs.cancel(job_id)
    except KeyError:
        raise HTTPException(404, 'Job not found')


# ------------------------------------------------------------------ explore and export

class Explore(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hypothesis_id: str = Field(min_length=1, max_length=64)


@router.post('/{sid}/explore')
def explore(sid: str, body: Explore):
    """Run the existing optimizer as if one explanation were confirmed (hypothetical, explicitly requested)."""
    from ..optimization.engine import optimize
    from ..schemas import OptimizeRequest
    from ..physics.circuit import VERSION as CIRCUIT_VERSION
    view = session_view(sid)
    inv = view['investigation']
    if not inv or 'investigation' in view['stale']:
        fail('Investigate possible causes first.', 409)
    hyp = next((h for h in inv['hypotheses'] if h['id'] == body.hypothesis_id), None)
    if hyp is None or hyp.get('mismatch') is None:
        fail('Unknown or untested explanation.')
    params, reason = hypothetical_parameters(hyp, inv['circuit_args'])
    if params is None:
        fail(reason)
    reference = view['reference']
    run = get_record('run', reference['run_id'])
    inputs = {k: v for k, v in run['inputs'].items() if k not in ('calibration_id', 'parameter_calibration_id')}
    inputs.update(solver='circuit', model_mode='physics', require_model_agreement=False)
    profile = {k: v for k, v in run['profile'].items() if k != 'effective_parameters'}
    record = {'id': f'diagnostic:{inv["id"]}:{hyp["id"]}', 'parameters': params, 'source_type': 'diagnostic_hypothesis',
              'fit': {'shots': 0, 'residual_pct': [], 'hypothesis': hyp['title']},
              'scope': {'generator_profile': profile, 'impulse_type': inputs['impulse_type'], 'layout_id': inputs['layout_id'],
                        'include_base_c': inputs.get('include_base_c'), 'physics_version': CIRCUIT_VERSION}}
    try:
        req = OptimizeRequest.model_validate(inputs)
        result = optimize(req, None, parameter_calibration=record)
    except ValueError as error:
        fail(error)
    run_id = uuid.uuid4().hex[:12]
    result['run_id'] = run_id
    result['diagnostic_exploration'] = {
        'session_id': sid, 'investigation_id': inv['id'], 'hypothesis_id': hyp['id'], 'hypothesis_title': hyp['title'],
        'effective_parameters': params, 'hypothetical': True,
        'label': f"Hypothetical: recommendation if \"{hyp['title']}\" is confirmed",
        'note': 'A fitted continuous resistance or capacitance is an effective value, not a part to install. The optimizer '
                'still chooses constructible networks from the counted stock and applies every rating. Nothing is applied '
                'to other runs; this is not a correction.'}
    saved = storage.put('run', run_id, result)
    return {'run_id': saved['id'], 'exploration': saved['diagnostic_exploration'],
            'candidates': [{k: c.get(k) for k in ('id', 'rank', 'settings', 'hybrid', 'compliance')} for c in saved['candidates'][:3]]}


@router.get('/{sid}/export.json')
def export_json(sid: str):
    view = session_view(sid)
    body = json.dumps(view, indent=2, allow_nan=False)
    return Response(body, media_type='application/json', headers={'Content-Disposition': f'attachment; filename="waveform_diagnostic_{sid}.json"'})


@router.get('/{sid}/report', response_class=HTMLResponse)
def export_report(sid: str):
    view = session_view(sid)
    return HTMLResponse(report_html(view), headers={'Content-Disposition': f'inline; filename="waveform_diagnostic_{sid}.html"'})


# ------------------------------------------------------------------ labelled demonstration

@router.post('/demo')
def demo_session():
    """A clearly labelled generated demonstration: a rendered image of a shot whose front network is 18 % low."""
    from .demo import create_demo
    try:
        sid = create_demo()
    except ValueError as error:
        fail(error)
    return session_view(sid)
