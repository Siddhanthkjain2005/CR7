"""Render known waveforms into plot images (for the labelled demonstration and tests).

Every rendered image carries a visible "generated" label and returns the exact
pixel positions of its axis values, so digitizing it back can be checked.
"""
import io

import numpy as np


def render_plot(curves, *, time_range, voltage_range, size=(1200, 800), dpi=100, grid=True, label='GENERATED DEMONSTRATION — not a laboratory record',
                time_label='Time (µs)', voltage_label='Voltage (kV)', ticks=None, style='plot', annotate=None):
    """curves: list of dicts {t, v, color, width}. Returns (png bytes, truth).

    truth['to_pixel'] gives a function's coefficients (linear) mapping axis values to
    image pixels; truth['plot_box'] is the axes rectangle in pixels.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    w, h = size
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
    face = '#101418' if style == 'scope' else 'white'
    fig.patch.set_facecolor(face)
    ax = fig.add_axes([.1, .12, .85, .78])
    ax.set_facecolor(face)
    for c in curves:
        ax.plot(c['t'], c['v'], color=c.get('color', '#1f5fbf'), linewidth=c.get('width', 1.6), solid_capstyle='butt')
    ax.set_xlim(*time_range); ax.set_ylim(*voltage_range)
    fg = '#c8d0d8' if style == 'scope' else '#222222'
    if grid:
        ax.grid(True, color='#3a4450' if style == 'scope' else '#d0d0d0', linewidth=.8)
    if ticks:
        ax.set_xticks(ticks.get('x', ax.get_xticks())); ax.set_yticks(ticks.get('y', ax.get_yticks()))
        ax.set_xlim(*time_range); ax.set_ylim(*voltage_range)
    ax.set_xlabel(time_label, color=fg); ax.set_ylabel(voltage_label, color=fg)
    ax.tick_params(colors=fg)
    for spine in ax.spines.values():
        spine.set_color(fg)
    if label:
        fig.text(.5, .955, label, ha='center', va='center', color='#b02020', fontsize=11, weight='bold')
    if annotate:
        ax.text(*annotate['xy'], annotate['text'], color=annotate.get('color', fg), fontsize=10)
    fig.canvas.draw()
    # Display coordinates have their origin at the bottom-left; images at the top-left.
    to_display = ax.transData
    (x0, y0), (x1, y1) = to_display.transform([(time_range[0], voltage_range[0]), (time_range[1], voltage_range[1])])
    height = fig.canvas.get_width_height()[1]
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=dpi, facecolor=face)
    plt.close(fig)
    truth = {'plot_box': [float(x0), float(height - y1), float(x1), float(height - y0)],
             'x': (float(x0), float(time_range[0]), float(x1), float(time_range[1])),
             'y': (float(height - y0), float(voltage_range[0]), float(height - y1), float(voltage_range[1])),
             'size': [w, h]}
    return buffer.getvalue(), truth


def pixel_of(truth, t, v):
    x0, t0, x1, t1 = truth['x']; y0, v0, y1, v1 = truth['y']
    return x0 + (t - t0) * (x1 - x0) / (t1 - t0), y0 + (v - v0) * (y1 - y0) / (v1 - v0)


def warp(png_bytes, corners_out, *, quality=None, scale=1.):
    """Simulate a photo: perspective-distort the image so its corners land at corners_out.

    Returns (bytes, forward 3×3 matrix original→warped).
    """
    from PIL import Image
    from .imaging import _perspective_matrix
    image = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    w, h = image.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    out_w = int(max(c[0] for c in corners_out) + 20); out_h = int(max(c[1] for c in corners_out) + 20)
    inverse = _perspective_matrix(src, corners_out)   # warped → original
    coeffs = tuple((inverse / inverse[2, 2]).ravel()[:8])
    warped = image.transform((out_w, out_h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC, fillcolor=(235, 232, 226))
    if scale != 1:
        warped = warped.resize((max(64, int(out_w * scale)), max(64, int(out_h * scale))), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if quality:
        warped.save(buffer, format='JPEG', quality=quality)
    else:
        warped.save(buffer, format='PNG')
    forward = np.linalg.inv(inverse)
    if scale != 1:
        forward = np.diag([scale, scale, 1.]) @ forward
    return buffer.getvalue(), forward
