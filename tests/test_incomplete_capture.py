"""Independent measured step responses are unsuitable impulse captures."""
from copy import deepcopy
import hashlib
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from backend.app.physics.waveform_metrics import analyze, waveform_from_metrics
from backend.app.trial_quality import assess_waveform

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/external/metrology/zenodo_6340016/dataset_2022_08_03.xlsx'


@pytest.mark.parametrize('sheet', [1, 2, 3])
def test_trusted_measured_steps_do_not_enter_impulse_calibration(sheet):
    # Source workbook values are seconds and volts of a divider step response.
    # This conversion is not a generator-voltage calibration or impulse label.
    assert hashlib.md5(SOURCE.read_bytes()).hexdigest() == '62b08bf71bd6af952b5c7b8c16a68fde'
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(SOURCE) as archive:
        tree = ET.fromstring(archive.read(f'xl/worksheets/sheet{sheet}.xml'))
    pairs = []
    for row in tree.findall('s:sheetData/s:row', ns):
        cells = row.findall('s:c', ns)
        if len(cells) >= 2:
            values = [c.find('s:v', ns) for c in cells[:2]]
            if all(v is not None for v in values):
                pairs.append([float(v.text) for v in values])
    pairs = np.asarray(pairs)
    assert len(pairs) == 22000
    times, voltage = pairs[:, 0]*1e6, pairs[:, 1]*1e-3
    measured = analyze(times, voltage)
    original = deepcopy(measured)
    quality = assess_waveform(times, voltage, measured)
    assert not quality['calibration_allowed'] and not quality['evaluation_allowed']
    assert 'incomplete_falling_limb' in {item['code'] for item in quality['issues']}
    assert quality['metrics']['post_half_value_span_us'] < .02
    assert measured == original


@pytest.mark.parametrize('impulse,front,tail', [('Lightning', 1.2, 50.), ('Switching', 250., 2500.)])
@pytest.mark.parametrize('polarity,baseline,shift', [(1, 0., 0.), (-1, 7., 500.)])
def test_truncated_half_value_requires_review_but_extended_capture_passes(impulse, front, tail, polarity, baseline, shift):
    wave = waveform_from_metrics(front, tail, 1000., impulse, points=20000)
    times = np.asarray(wave['time_us']) + shift
    voltage = baseline + polarity*np.asarray(wave['voltage_kv'])
    measured = analyze(times, voltage, impulse, baseline_kv=baseline, time_origin_us=shift)
    assert assess_waveform(times, voltage, measured, impulse_type=impulse)['calibration_allowed']
    cutoff = np.searchsorted(times, measured['t50_us']) + 2
    short_t, short_v = times[:cutoff], voltage[:cutoff]
    short = analyze(short_t, short_v, impulse, baseline_kv=baseline, time_origin_us=shift)
    quality = assess_waveform(short_t, short_v, short, impulse_type=impulse)
    assert 'incomplete_falling_limb' in {i['code'] for i in quality['issues']}
    assert not quality['calibration_allowed']
    assert short['crest_kv'] == measured['crest_kv']


def test_many_post_crossing_samples_with_insufficient_duration_still_require_review():
    # High row count must not turn an end-of-window transition into a usable tail.
    times = np.r_[np.linspace(0, 20, 300), np.linspace(20.001, 20.02, 300)]
    voltage = np.where(times <= 1, 1000*times,
                       np.where(times <= 20, 1000 - (times-1)*500/19,
                                500 - (times-20)*100))
    measured = analyze(times, voltage)
    quality = assess_waveform(times, voltage, measured)
    assert quality['metrics']['post_half_value_intervals'] > 200
    assert 'incomplete_falling_limb' in {i['code'] for i in quality['issues']}
