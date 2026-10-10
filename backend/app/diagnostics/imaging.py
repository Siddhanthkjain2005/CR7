"""Image validation and recorded geometric transforms (Pillow + numpy only).

The original bytes are never modified. Every transform is an explicit, recorded
step with a 3×3 matrix that maps working-image pixels back to the original
image, so an extracted trace can always be drawn on the photograph it came from.
"""
import io
import math

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 15_000_000
MAX_PIXELS = 40_000_000
MAX_SIDE = 12_000
MIN_SIDE = 64
MAX_WORKING_SIDE = 4000
MAGIC = {'png': (b'\x89PNG\r\n\x1a\n',), 'jpeg': (b'\xff\xd8\xff',), 'webp': (b'RIFF',)}
MEDIA = {'png': 'image/png', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}
# Pillow refuses images above this many pixels before decoding them.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def sniff(content):
    if content[:8] == MAGIC['png'][0]:
        return 'png'
    if content[:3] == MAGIC['jpeg'][0]:
        return 'jpeg'
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'webp'
    return None


def inspect(content):
    """Validate type, size and dimensions from the bytes themselves (never the filename)."""
    if len(content) > MAX_BYTES:
        raise ValueError(f'The image exceeds the {MAX_BYTES // 1_000_000} MB limit.')
    kind = sniff(content)
    if kind is None:
        raise ValueError('Only PNG, JPEG and WebP images are accepted (checked from the file contents).')
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(content)) as image:
            fmt = (image.format or '').lower()
            width, height = image.size
            orientation = image.getexif().get(0x0112, 1) if hasattr(image, 'getexif') else 1
            mode = image.mode
            frames = getattr(image, 'n_frames', 1)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as error:
        raise ValueError(f'The image could not be decoded safely: {error}') from error
    if {'jpeg': 'jpeg', 'png': 'png', 'webp': 'webp'}.get(fmt) != kind:
        raise ValueError('The image contents do not match a single supported format.')
    if frames != 1:
        raise ValueError('Animated or multi-frame images are not accepted; export a single still image.')
    if min(width, height) < MIN_SIDE or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
        raise ValueError(f'Image dimensions {width}×{height} are outside {MIN_SIDE}–{MAX_SIDE} px per side '
                         f'or above {MAX_PIXELS // 1_000_000} megapixels.')
    return {'format': kind, 'media_type': MEDIA[kind], 'width': width, 'height': height, 'mode': mode,
            'exif_orientation': int(orientation) if isinstance(orientation, int) else 1, 'bytes': len(content)}


def oriented(content):
    """RGB array after the camera's recorded EXIF orientation (a recorded step)."""
    with Image.open(io.BytesIO(content)) as image:
        upright = ImageOps.exif_transpose(image).convert('RGB')
        return np.asarray(upright, dtype=np.uint8).copy()


def _perspective_matrix(src, dst):
    """3×3 H with dst→src mapping (Pillow PERSPECTIVE convention: output→input)."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    coeffs = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
    return np.append(coeffs, 1.).reshape(3, 3)


def map_points(matrix, points):
    """Apply a 3×3 homography to (x, y) points."""
    p = np.asarray(points, float).reshape(-1, 2)
    q = np.c_[p, np.ones(len(p))] @ np.asarray(matrix, float).T
    return q[:, :2] / q[:, 2:3]


def apply(rgb, spec):
    """Apply recorded transforms; returns (working RGB array, record).

    spec: {'corners': [[x,y] TL, TR, BR, BL] in oriented-image pixels} for perspective
    correction from the four plot corners, or {'rotate_deg': float, 'crop': [x0, y0, x1, y1]}
    (crop in the rotated frame). The record holds the working→original matrix.
    """
    spec = spec or {}
    h, w = rgb.shape[:2]
    image = Image.fromarray(rgb)
    steps = []
    if spec.get('corners'):
        if spec.get('rotate_deg') or spec.get('crop'):
            raise ValueError('Use either the four plot corners or rotate-and-crop, not both.')
        corners = np.asarray(spec['corners'], float)
        if corners.shape != (4, 2) or not np.isfinite(corners).all():
            raise ValueError('Give four plot corners: top-left, top-right, bottom-right, bottom-left.')
        if (corners < -1).any() or (corners[:, 0] > w + 1).any() or (corners[:, 1] > h + 1).any():
            raise ValueError('Plot corners must lie inside the image.')
        tl, tr, br, bl = corners
        width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
        height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
        cross = (tr - tl)[0] * (bl - tl)[1] - (tr - tl)[1] * (bl - tl)[0]
        if width < 40 or height < 40 or cross <= 0:
            raise ValueError('The four corners must outline the plot area in order (top-left, top-right, bottom-right, bottom-left).')
        scale = min(1., MAX_WORKING_SIDE / max(width, height))
        out_w, out_h = int(round(width * scale)), int(round(height * scale))
        matrix = _perspective_matrix(corners, [(0, 0), (out_w, 0), (out_w, out_h), (0, out_h)])
        coeffs = tuple((matrix / matrix[2, 2]).ravel()[:8])
        image = image.transform((out_w, out_h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC,
                                fillcolor=(255, 255, 255))
        steps.append({'step': 'perspective', 'corners': corners.tolist(), 'output_size': [out_w, out_h]})
    else:
        angle = float(spec.get('rotate_deg') or 0.)
        if not math.isfinite(angle) or abs(angle) > 45:
            raise ValueError('Straightening is limited to ±45°.')
        matrix = np.eye(3)
        if angle:
            t = math.radians(angle)
            c, s = math.cos(t), math.sin(t)
            out_w = int(math.ceil(abs(w * c) + abs(h * s)))
            out_h = int(math.ceil(abs(w * s) + abs(h * c)))
            # Output→input affine for a clockwise rotation of the displayed content.
            a, b, d, e = c, s, -s, c
            cx_in, cy_in, cx_out, cy_out = w / 2, h / 2, out_w / 2, out_h / 2
            cc = cx_in - (a * cx_out + b * cy_out)
            ff = cy_in - (d * cx_out + e * cy_out)
            matrix = np.array([[a, b, cc], [d, e, ff], [0, 0, 1.]])
            image = image.transform((out_w, out_h), Image.Transform.AFFINE, (a, b, cc, d, e, ff),
                                    Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))
            steps.append({'step': 'rotate', 'degrees_clockwise': angle, 'output_size': [out_w, out_h]})
        crop = spec.get('crop')
        if crop:
            x0, y0, x1, y1 = [float(v) for v in crop]
            W, H = image.size
            x0, x1 = sorted((max(0., x0), min(float(W), x1)))
            y0, y1 = sorted((max(0., y0), min(float(H), y1)))
            if x1 - x0 < 40 or y1 - y0 < 40:
                raise ValueError('The crop must keep at least 40×40 pixels.')
            box = (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
            image = image.crop(box)
            matrix = matrix @ np.array([[1, 0, box[0]], [0, 1, box[1]], [0, 0, 1.]])
            steps.append({'step': 'crop', 'box': list(box)})
        if max(image.size) > MAX_WORKING_SIDE:
            factor = MAX_WORKING_SIDE / max(image.size)
            size = (max(1, int(image.size[0] * factor)), max(1, int(image.size[1] * factor)))
            image = image.resize(size, Image.Resampling.LANCZOS)
            matrix = matrix @ np.diag([1 / factor, 1 / factor, 1.])
            steps.append({'step': 'downscale', 'factor': factor})
    work = np.asarray(image.convert('RGB'), dtype=np.uint8).copy()
    return work, {'steps': steps, 'working_size': [work.shape[1], work.shape[0]],
                  'working_to_original': matrix.tolist(),
                  'note': 'Applied to a copy. The original upload is stored unchanged with its checksum.'}


def png(rgb):
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format='PNG', optimize=False)
    return buffer.getvalue()


def gray(rgb):
    return (rgb[..., 0] * .299 + rgb[..., 1] * .587 + rgb[..., 2] * .114).astype(float)


def background_color(rgb):
    """Most common colour (quantized), taken as the plot background."""
    step = max(1, int(np.sqrt(rgb.shape[0] * rgb.shape[1] / 1_000_000)))  # sample at most ~1 Mpx
    sample = rgb[::step, ::step].reshape(-1, 3)
    q = sample // 16
    keys = q[:, 0].astype(np.int32) * 256 + q[:, 1].astype(np.int32) * 16 + q[:, 2]
    mode = np.bincount(keys).argmax()
    return np.median(sample[keys == mode], axis=0)


def deskew(rgb, limit=8., step=.25):
    """Estimate the straightening angle from straight lines (projection-profile method)."""
    from scipy import ndimage
    g = gray(rgb)
    bg = gray(background_color(rgb)[None, None, :].astype(np.uint8))[0, 0]
    mask = (np.abs(g - bg) > 60).astype(float)
    factor = max(1, int(max(mask.shape) / 700))
    mask = mask[::factor, ::factor]
    if mask.sum() < 50:
        return {'degrees_clockwise': 0., 'confidence': 'no straight lines found'}
    best, scores = 0., []
    for angle in np.arange(-limit, limit + 1e-9, step):
        r = ndimage.rotate(mask, -angle, reshape=True, order=0)
        score = float(np.var(r.sum(axis=1)) + np.var(r.sum(axis=0)))
        scores.append((angle, score))
    scores.sort(key=lambda a: -a[1])
    best = scores[0][0]
    zero = next(s for a, s in scores if abs(a) < 1e-9)
    return {'degrees_clockwise': float(best),
            'confidence': 'clear' if scores[0][1] > 1.05 * zero or abs(best) < 1e-9 else 'weak',
            'note': 'Suggestion from the straight lines in the image (axes, grid). Confirm visually before use.'}
