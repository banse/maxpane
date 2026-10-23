"""Offline rendering, geometry and lifecycle of the standalone house spike."""
import httpx
import pytest
from textual.widgets import Static

from scripts.seat_house_demo import HouseDemo, halfblock_strips, release_image, select_graphics
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal


async def until(pilot, predicate):
    for _ in range(30):
        await pilot.pause()
        if predicate():
            return
    assert predicate(), 'layout did not settle'


def test_solid_pixels_use_only_backgrounds_without_font_glyph_edges():
    from scripts.seat_house_demo import solid_strips
    rgb = ((0, 0, 0), (255, 255, 255), (100, 0, 0))
    rows = solid_strips([bytearray([1, 2]), bytearray([2, 1])], 6, 3, rgb=rgb)
    assert len(rows) == 3 and all(row.cell_length == 6 for row in rows)
    assert all(part.text.strip() == '' for row in rows for part in row)
    first = list(rows[0])
    assert first[1].text == '  ' and first[1].style.bgcolor.get_truecolor() == rgb[1]
    assert first[2].text == '  ' and first[2].style.bgcolor.get_truecolor() == rgb[2]
    assert solid_strips([bytearray([1])], 1, 1, rgb=rgb)[0].cell_length == 1


@pytest.mark.asyncio
async def test_default_is_a_native_closeup_with_solid_composited_pixels():
    from scripts.seat_house_demo import RGB
    app = HouseDemo(clock=lambda: 0)
    async with app.run_test(size=(149, 45)) as pilot:
        def painted_at_final_size():
            region = app.query_one('#house-layer').region
            rows = app.query_one('#house-pixels').rows
            return (region.size == (99, 31) and region == app.query_one(SurfboardTerminal).region
                    and len(rows) == 31 and all(row.cell_length == 99 for row in rows))
        await until(pilot, painted_at_final_size)
        assert app.closeup and app.pixel_mode == 'cells'
        layer = app.query_one('#house-layer').region
        strips = app.screen._compositor.render_strips()
        painted = [strips[y].crop(layer.x, layer.right) for y in range(layer.y, layer.bottom)]
        assert all(part.text.strip() == '' for row in painted for part in row)
        colors = {part.style.bgcolor.get_truecolor() for row in painted for part in row if part.style.bgcolor}
        assert len(colors) >= 5 and colors <= set(RGB) | {(29, 29, 29)}
        await pilot.press('z')
        assert not app.closeup


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('The house demo must never fetch data')
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)


def test_halfblocks_preserve_both_pixel_colors_and_fill_region():
    rows = halfblock_strips([bytearray([1, 2]), bytearray([3, 4])], 4, 2,
                           rgb=((0, 0, 0), (255, 255, 255), (100, 0, 0),
                                (0, 100, 0), (0, 0, 100)))
    assert len(rows) == 2
    assert all(row.cell_length == 4 for row in rows)
    pixels = [part for row in rows for part in row if '▀' in part.text]
    assert pixels[0].style.color.get_truecolor() == (255, 255, 255)
    assert pixels[0].style.bgcolor.get_truecolor() == (0, 100, 0)
    assert pixels[1].style.color.get_truecolor() == (100, 0, 0)
    assert pixels[1].style.bgcolor.get_truecolor() == (0, 0, 100)


def test_graphics_probe_only_on_explicit_tty_request():
    calls = []
    def loader():
        calls.append(True)
        raise ImportError('optional package missing')
    assert select_graphics('halfblock', tty=True, loader=loader)[0] is None
    assert select_graphics('tgp', tty=False, loader=loader)[0] is None
    assert calls == []
    backend, note = select_graphics('tgp', tty=True, loader=loader)
    assert backend is None and 'solid-pixel' in note
    assert calls == [True]


@pytest.mark.parametrize('size', [(1, 1), (80, 24), (320, 101)])
@pytest.mark.asyncio
async def test_fullscreen_fits_tiny_and_native_sized_terminals(size):
    app = HouseDemo(clock=lambda: 0, fullscreen=True, pixel_mode='halfblock', closeup=False)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        visible = app.screen._compositor.render_strips()
        assert len(visible) == size[1]
        assert all(row.cell_length == size[0] for row in visible)
        if size == (320, 101):
            assert app.query_one('#house-layer').size == (320, 100)
            assert 'native 320×200' in visible[-1].text


def test_image_cleanup_targets_and_frees_only_owned_id():
    class Renderable:
        terminal_image_id = 713
    renderable, sent = Renderable(), []
    release_image(renderable, lambda **kw: sent.append(kw))
    release_image(renderable, lambda **kw: sent.append(kw))
    assert sent == [dict(a='d', d='I', i=713, q=2)]
    assert renderable.terminal_image_id is None


@pytest.mark.asyncio
async def test_panel_fullscreen_resize_pause_and_reveal():
    clock = [0.0]
    app = HouseDemo(clock=lambda: clock[0], pixel_mode='halfblock', closeup=False)
    async with app.run_test(size=(149, 45)) as pilot:
        layer = app.query_one('#house-layer')
        terminal = app.query_one(SurfboardTerminal)
        # Rack track sizing and scrollbar removal each schedule a later layout.
        await until(pilot, lambda: layer.region == terminal.region)
        assert layer.region == terminal.region
        assert layer.region.size == (99, 31)
        visible = app.screen._compositor.render_strips()
        assert any('▀' in row.text for row in visible)
        assert 'SAMPLE' in visible[0].text
        assert all('commands' not in row.text for row in visible)
        clock[0] = 1.0
        app.tick()
        assert app.elapsed == 1.0
        await pilot.press('space')
        clock[0] = 5.0
        app.tick()
        assert app.elapsed == 1.0
        await pilot.press('f')
        await pilot.pause()
        assert layer.region == (0, 0, 149, 44)
        assert 'DEMO' in app.screen._compositor.render_strips()[-1].text
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert layer.region == (0, 0, 100, 29)
        await pilot.press('f', 'enter')
        await pilot.pause()
        assert not layer.display
        assert all('▀' not in row.text for row in app.screen._compositor.render_strips())
        await pilot.press('enter', 'r', 'z')
        await pilot.pause()
        assert layer.display and app.elapsed == 0 and app.closeup


@pytest.mark.asyncio
async def test_graphics_cleared_when_hidden_and_at_exit():
    class FakeImage(Static):
        image = None
    from scripts.seat_house_demo import Graphics
    backend = Graphics(FakeImage, lambda frame, width, height: ('pixels', width, height))
    app = HouseDemo(graphics=backend)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        widget = app.query_one('#house-image')
        assert widget.image is not None
        await pilot.press('enter')
        assert widget.image is None
        await pilot.press('enter')
        await pilot.pause()
        assert widget.image is not None
    assert widget.image is None


@pytest.mark.asyncio
async def test_installed_graphics_palette_placement_and_owned_cleanup(monkeypatch):
    """Optional backend contract; fake terminal response/sender, never a real probe."""
    import sys
    if sys.version_info < (3, 12):
        pytest.skip('Optional textual-image requires Python 3.12+')
    pytest.importorskip('PIL')
    pytest.importorskip('textual_image')
    from textual_image import _terminal
    monkeypatch.setattr(_terminal.probe_terminal, '_result',
                        _terminal.TerminalCapabilities(_terminal.CellSize(10, 20), False, True), raising=False)
    from textual_image.renderable import tgp
    sent = []
    monkeypatch.setattr(tgp, '_send_tgp_message', lambda **kw: sent.append(kw))
    from scripts.seat_house_demo import load_graphics, base_house, RGB
    backend = load_graphics()
    canvas = backend.make_image(base_house(), 99, 31)
    assert canvas.size == (990, 620)
    data = canvas.convert('RGB').tobytes()
    assert set(zip(data[::3], data[1::3], data[2::3])) <= set(RGB) | {(29, 29, 29)}
    app = HouseDemo(graphics=backend, clock=lambda: 0, closeup=False)
    async with app.run_test(size=(149, 45)) as pilot:
        await until(pilot, lambda: any(cmd.get('U') == 1 and cmd['c'] == 99 for cmd in sent))
        app.screen._compositor.render_strips()
        assert any(cmd.get('U') == 1 and cmd['c'] == 99 for cmd in sent)
        await pilot.press('f')
        await pilot.resize_terminal(10, 5)
        await until(pilot, lambda: app.query_one('#house-pixels').display)
        assert app.query_one('#house-pixels').display
        await pilot.resize_terminal(149, 45)
        await until(pilot, lambda: app.image_widget.image is not None)
        assert app.image_widget.image is not None
        await pilot.press('enter')
        await pilot.pause()
    uploaded = {cmd['i'] for cmd in sent if 'payload' in cmd}
    deleted = {cmd['i'] for cmd in sent if cmd.get('a') == 'd' and cmd.get('d') == 'I'}
    assert uploaded and deleted == uploaded
