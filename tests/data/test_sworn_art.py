"""Reader-side Sworn artwork keeps the SVG's geometry and never resolves resources."""
import base64
import io
from pathlib import Path

import httpx
import pytest
from PIL import Image

from maxpane_dashboard.data.sworn_art import prepare_art


SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
<rect width="1000" height="1000" fill="#0a0a0a"/>
<defs><clipPath id="half"><rect width="500" height="1000"/></clipPath></defs>
<g clip-path="url(#half)"><rect width="1000" height="1000" fill="#00cc33"/></g>
<g transform="translate(750,500)"><circle r="100" fill="#ffffff"/></g>
</svg>'''


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('art rasterization must not fetch resources')
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)


def test_svg_raster_and_fallback_preserve_clipping_transform_and_color():
    art = prepare_art(SVG)
    image = Image.open(io.BytesIO(base64.b64decode(art['png'])))
    assert image.size == (768, 768)
    assert image.getpixel((100, 300))[:3] == (0, 204, 51)
    assert image.getpixel((650, 100))[:3] == (10, 10, 10)
    assert image.getpixel((576, 384))[:3] == (255, 255, 255)
    assert len(art['hash']) == 64
    pixels = art['pixels']
    assert len(pixels) == 128 and all(len(row) == 128 for row in pixels)
    assert pixels[40][20] == '00cc33'
    assert pixels[10][100] == '0a0a0a'
    assert pixels[64][96] == 'ffffff'


@pytest.mark.parametrize('svg', [
    '<!DOCTYPE svg [<!ENTITY file SYSTEM "file:///etc/passwd">]>' + SVG,
    SVG.replace('<defs>', '<image href="https://example.com/a.png"/><defs>'),
    SVG.replace('url(#half)', 'url(file:///tmp/art.svg#half)'),
    SVG.replace('<defs>', '<style>@import "https://example.com/a.css";</style><defs>'),
    SVG.replace('<defs>', '<script>alert(1)</script><defs>'),
    '<svg>' + ' ' * 250001 + '</svg>',
    '<svg><broken>',
])
def test_external_resources_and_invalid_svg_are_rejected_before_rasterization(svg, monkeypatch):
    import resvg_py
    def forbidden(**kwargs):
        raise AssertionError('invalid SVG reached rasterization')
    monkeypatch.setattr(resvg_py, 'svg_to_bytes', forbidden)
    with pytest.raises(ValueError):
        prepare_art(svg)


def test_repeated_svg_reuses_raster_but_result_pixels_are_not_mutably_shared(monkeypatch):
    import resvg_py
    original = resvg_py.svg_to_bytes
    calls = []
    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(resvg_py, 'svg_to_bytes', counted)
    svg = SVG.replace('#00cc33', '#8ff0a4')
    first = prepare_art(svg)
    first['pixels'][0][0] = 'deadbe'
    second = prepare_art(svg)
    assert len(calls) == 1
    assert second['pixels'][0][0] != 'deadbe'
    assert first['hash'] == second['hash']


def test_official_illustrative_full_house_retains_active_tiers_and_palette():
    # This site illustration exercises every tier; it is not minted-token evidence.
    svg = (Path(__file__).parents[1] / 'fixtures/sworn_full_house_demo.svg').read_text()
    art = prepare_art(svg)
    image = Image.open(io.BytesIO(base64.b64decode(art['png'])))
    palette = {color for _, color in image.getcolors(maxcolors=768 * 768)}
    assert {(0, 255, 65), (0, 204, 51), (143, 240, 164),
            (219, 254, 230), (255, 255, 255)} <= palette
    assert image.getpixel((0, 0)) == (10, 10, 10)
    assert sum(color != '0a0a0a' for row in art['pixels'] for color in row) > 4000
