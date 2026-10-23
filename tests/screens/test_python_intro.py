"""Composited native intro frames and real Textual key routing; no network."""
from dataclasses import replace
from pathlib import Path
import re

import pytest
from rich.cells import cell_len

from maxpane_dashboard.intro.settings import IntroConfig
from maxpane_dashboard.intro.view import IntroApp, COMPACT, RAIN_CHARS, TAGLINE_EN
from maxpane_dashboard.screens.splash import LOGO, TAGLINE, NOTICE


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('intro must stay offline')
    monkeypatch.setattr('httpx.Client.send', fail)
    monkeypatch.setattr('httpx.AsyncClient.send', fail)


def make_app(**changes):
    clock = [0.0]
    return IntroApp(replace(IntroConfig(), **changes), clock=lambda: clock[0], seed=42), clock


async def rows(app, pilot):
    app.tick()
    await pilot.pause()
    return [s.text for s in app.screen._compositor.render_strips()]


@pytest.mark.asyncio
async def test_actual_keys_and_complete_rendered_sequence():
    app, clock = make_app(skip_key='none', tagline='english', rain_duration_ms=100)
    async with app.run_test(size=(149, 45)) as pilot:
        clock[0] = 1.5
        assert 'Wake up, Anon...' in '\n'.join(await rows(app, pilot))
        clock[0] = app.sequence.typewriter_duration
        assert '> Do you want to enter the Ether?' in '\n'.join(await rows(app, pilot))
        await pilot.press('g', 'm', 'enter')
        assert "gm anon. Let's go." in '\n'.join(await rows(app, pilot))
        clock[0] += 1
        await rows(app, pilot)
        clock[0] += .1
        assert any(row.strip() for row in await rows(app, pilot))
        clock[0] += 4.01
        rendered = await rows(app, pilot)
        assert LOGO.splitlines()[0] in rendered[19]
        assert TAGLINE_EN in rendered[27]
        assert 'press any key' not in '\n'.join(rendered)
        await pilot.press('enter')
        assert app.sequence.result is None
        clock[0] += 3
        rendered = await rows(app, pilot)
        assert 'press any key' in rendered[30] and NOTICE in rendered[43]
        await pilot.press('x')
    assert app.return_value == 'dashboard'


@pytest.mark.asyncio
async def test_actual_no_edit_retry_and_interrupt():
    app, clock = make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        app.sequence.enter('prompt')
        await pilot.press('n', 'x', 'backspace', 'g', 'm', 'i', 'enter')
        assert 'Not with that attitude' in '\n'.join(await rows(app, pilot))
        clock[0] += 1
        await rows(app, pilot)
        await pilot.press('n', 'enter')
        assert 'Maybe next time, anon.' in '\n'.join(await rows(app, pilot))
        await pilot.press('ctrl+c')
    assert app.return_value == 'interrupt'


@pytest.mark.asyncio
async def test_wide_prompt_tail_max_marker_and_resize_preserve_state():
    app, _ = make_app()
    async with app.run_test(size=(80, 24)) as pilot:
        app.sequence.enter('prompt')
        for char in '界' * 60 + 'tail':
            app.sequence.key(char, char)
        line = next(r for r in await rows(app, pilot) if '[max]' in r)
        assert '…' in line and 'tail' in line and cell_len(line) == 80
        await pilot.resize_terminal(32, 8)
        line = next(r for r in await rows(app, pilot) if '[max]' in r)
        assert 'tail' in line and cell_len(line) == 32
        assert len(app.sequence.buffer) == 64 and app.sequence.stage == 'prompt'


@pytest.mark.parametrize('size', [(149, 45), (100, 30), (99, 30), (80, 24), (79, 24), (25, 10), (1, 1)])
@pytest.mark.asyncio
async def test_logo_and_rain_fit_all_sizes_and_keep_logo_position(size):
    app, clock = make_app()
    async with app.run_test(size=size) as pilot:
        app.sequence.enter('rain')
        clock[0] = 7.49
        reveal = await rows(app, pilot)
        clock[0] = 7.5
        settled = await rows(app, pilot)
        expected = LOGO if size[0] >= 100 and size[1] >= 30 else (
            COMPACT if size[0] >= 80 and size[1] >= 24 else 'M A X P A N E')
        top = max(0, (size[1] - len(expected.splitlines())) // 2)
        for y, line in enumerate(expected.splitlines(), top):
            clipped = line[:size[0]]
            assert clipped in settled[y] and clipped in reveal[y]
        assert len(settled) == size[1]
        assert all(cell_len(row) == size[0] for row in settled)
        await pilot.resize_terminal(149, 45)
        assert LOGO.splitlines()[0] in (await rows(app, pilot))[19]
        assert app.sequence.stage == 'logo'


@pytest.mark.asyncio
async def test_custom_colors_are_in_composited_logo_and_background():
    app, _ = make_app(color_scheme='custom', colors={'logo': '#123456', 'background': '#102030'})
    async with app.run_test(size=(149, 45)) as pilot:
        app.sequence.enter('logo')
        await rows(app, pilot)
        segments = [seg for strip in app.screen._compositor.render_strips() for seg in strip]
        logo = next(seg for seg in segments if '█' in seg.text)
        assert logo.style.color.get_truecolor() == (18, 52, 86)
        assert logo.style.bgcolor.get_truecolor() == (16, 32, 48)


@pytest.mark.asyncio
async def test_idle_frame_does_not_emit_an_ansi_style_for_every_blank_cell():
    app, _ = make_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await rows(app, pilot)
        segments = [seg for strip in app.screen._compositor.render_strips() for seg in strip]
        assert sum(len(seg.text) for seg in segments) == 149 * 45
        assert len(segments) < 150  # roughly one run per row, not 6,705 resets


@pytest.mark.asyncio
async def test_rust_cursor_frozen_prompt_and_custom_rain_palette():
    app, clock = make_app(color_scheme='custom', colors={'rain_dim': '#ff0000', 'rain_bright': '#ff0000'})
    async with app.run_test(size=(149, 45)) as pilot:
        clock[0] = .1
        assert 'Wa▌' in '\n'.join(await rows(app, pilot))
        app.sequence.enter('prompt')
        app.sequence.buffer = 'x' * 64
        await pilot.press('enter')
        assert '[max]' not in '\n'.join(await rows(app, pilot))
        app.sequence.enter('rain')
        clock[0] += 3
        await rows(app, pilot)
        segments = [seg for strip in app.screen._compositor.render_strips() for seg in strip if seg.text.strip()]
        assert len(segments) > 10
        assert all(seg.style.color.get_truecolor() == (255, 0, 0) for seg in segments)


@pytest.mark.guard
def test_assets_agree_with_rust_source():
    root = Path(__file__).resolve().parents[2] / 'maxpane/src/intro'
    source = (root / 'logo.rs').read_text()
    for name, value in [('LOGO_FULL', LOGO), ('LOGO_COMPACT', COMPACT),
                        ('TAGLINE_JP', TAGLINE), ('TAGLINE_EN', TAGLINE_EN), ('NOTICE_TEXT', NOTICE)]:
        literal = re.search(r'const ' + name + r': &str = "(.*?)";', source, re.S).group(1)
        assert literal.removeprefix('\\\n') == value
    charset = (root / 'charset.rs').read_text().split('pub const RAIN_CHARS_SINGLE_WIDTH:')[1].split('];')[0]
    assert ''.join(re.findall(r"'(.)'", charset)) == RAIN_CHARS
