"""Rasterize Sworn's bounded, self-contained SVG on the reader side."""
from __future__ import annotations

import base64
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import re
from xml.etree import ElementTree


_TAGS = {'svg', 'rect', 'g', 'polygon', 'path', 'circle', 'defs', 'clipPath'}
_ATTRS = {'viewBox', 'width', 'height', 'style', 'font-family', 'id', 'd', 'points',
          'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'fill', 'fill-opacity', 'stroke',
          'stroke-opacity', 'stroke-width', 'stroke-linejoin', 'stroke-linecap',
          'clip-path', 'transform', 'opacity', 'fill-rule', 'clip-rule'}


def _validate(svg: str) -> None:
    if not isinstance(svg, str) or len(svg) > 250_000:
        raise ValueError('SVG exceeds the artwork budget')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)', svg, re.I):
        raise ValueError('SVG declarations and processing instructions are not allowed')
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise ValueError('Invalid SVG') from exc
    elements = list(root.iter())
    if len(elements) > 4096 or root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('Invalid SVG element budget or root')
    for node in elements:
        if node.tag not in _TAGS and node.tag not in {'{http://www.w3.org/2000/svg}' + t for t in _TAGS}:
            raise ValueError('Unsupported SVG element')
        for key, value in node.attrib.items():
            if key not in _ATTRS:
                raise ValueError('Unsupported SVG attribute')
            if key == 'style' and not re.fullmatch(r'\s*font-family\s*:[\w\s,\-]+;?\s*', value):
                raise ValueError('SVG style may only name its unused font family')
            if re.search(r'url\s*\(', value, re.I) and not re.fullmatch(r'url\(#[\w-]+\)', value):
                raise ValueError('SVG resource references must be local fragments')


@lru_cache(maxsize=8)
def _raster(svg: str):
    import resvg_py
    from PIL import Image

    png = resvg_py.svg_to_bytes(svg_string=svg, width=768, height=768, skip_system_fonts=True)
    with Image.open(BytesIO(png)) as rendered:
        image = Image.alpha_composite(Image.new('RGBA', (768, 768), '#0a0a0a'),
                                     rendered.convert('RGBA')).convert('RGB')
    output = BytesIO()
    image.save(output, format='PNG')
    small = image.resize((128, 128), Image.Resampling.LANCZOS)
    raw = small.tobytes().hex()
    colors = tuple(raw[i:i + 6] for i in range(0, len(raw), 6))
    rows = tuple(colors[y:y + 128] for y in range(0, len(colors), 128))
    return base64.b64encode(output.getvalue()).decode('ascii'), rows


def prepare_art(svg: str) -> dict:
    """Return only serializable, caller-owned data; never perform network reads."""
    _validate(svg)
    png, pixels = _raster(svg)
    return {'png': png, 'pixels': [list(row) for row in pixels],
            'hash': sha256(svg.encode('utf-8')).hexdigest()}
