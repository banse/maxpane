"""Neutral POOL4 values use normal text ink without recoloring labels or signals."""
from textual.app import App

import pytest

from maxpane_dashboard.widgets.surf.pool4u_burn import SurfPool4UBurn
from maxpane_dashboard.widgets.surf.pool4u_signals import SurfPool4USignals
from maxpane_dashboard.themes import THEMES
from tests.widgets.test_surf_pool4_pipeline import pipeline


@pytest.fixture(params=['matrix', 'minimal'])
def theme(request, monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    return request.param


async def painted(widget_type, payload, width=80, *, theme):
    class Harness(App):
        CSS = "Screen { color: $text; }"

        def compose(self):
            yield widget_type()

    app = Harness()
    app.register_theme(THEMES[theme])
    app.theme = theme
    async with app.run_test(size=(width, 20)) as pilot:
        pilot.app.query_one(widget_type).update_data(**payload)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = [(strip.text.rstrip(), [segment.style for segment in strip for _ in segment.text])
                for strip in strips if strip.text.strip()]
        return rows, app.ansi_theme.ansi_colors, app.screen.rich_style.color.get_truecolor()


def styles_at(rows, word):
    matches = [(text, styles) for text, styles in rows if word in text]
    assert len(matches) == 1, (word, [text for text, _ in rows])
    text, styles = matches[0]
    start = text.index(word)
    return styles[start:start + len(word)]


def assert_normal(rows, word, normal):
    for style in styles_at(rows, word):
        assert style.color.get_truecolor() == normal, (word, style)
        assert not style.dim, (word, style)


def assert_gray(rows, word, normal):
    for style in styles_at(rows, word):
        color = style.color.get_truecolor()
        assert all(dim < full for dim, full in zip(color, normal)), (word, style)
        assert max(color) - min(color) < 10, (word, style)


@pytest.mark.asyncio
@pytest.mark.parametrize('width', [80, 35], ids=['full', 'compact'])
async def test_burn_values_use_normal_text_with_gray_labels_and_scope(width, theme):
    rows, _, normal = await painted(SurfPool4UBurn, dict(
        pool4_network='MAINNET', pool4_flow=[{'ts': 1000, 'burned_imd': 2},
                                           {'ts': 4600, 'burned_imd': 4}],
        pool4_total_burned=35135.94, pool4_burned_supply_pct=.84,
        pool4_total_supply=4165864.94, pool4_burn_pipeline=pipeline()), width, theme=theme)
    full = width == 80
    assert [text.strip() for text, _ in rows] == [
        'BURN & SUPPLY' + ('' if full else '  ‹ widen'),
        ('alloc rate   ' + '▁' * 11 + '█  144.0/day over 60m' if full
         else '▁' * 9 + '█ 144.0/day 60m'),
        ('settled      35.1K · 0.84% of ETH supply' if full else '35.1K settled · 0.84% ETH'),
        ('ETH supply   4.2M IMD' if full else 'ETH supply 4.2M'),
        'executor-wide', 'queued       29.95 IMD', 'last bridge  159.56 IMD',
        'Base burned  84.05 IMD',
    ]
    for value in ('144.0/day', '35.1K', '0.84%', '4.2M', '29.95 IMD', '159.56 IMD', '84.05 IMD'):
        assert_normal(rows, value, normal)
    for label in ('BURN & SUPPLY', 'executor-wide', 'queued', 'last bridge', 'Base burned'):
        assert_gray(rows, label, normal)
    if full:
        for label in ('alloc rate', 'settled', 'ETH supply   '):
            assert_gray(rows, label, normal)
    else:
        assert_gray(rows, 'ETH supply', normal)
    assert all(not style.dim and style.color.get_truecolor() == normal
               for style in styles_at(rows, '█'))


@pytest.mark.asyncio
async def test_signals_neutral_values_use_normal_text_and_labels_remain_gray(theme):
    rows, _, normal = await painted(SurfPool4USignals, dict(
        pool4_network='MAINNET', pool4_cap_headroom=10, pool4_venue_gap_pct=0,
        pool4_current_tick=100, pool4_reference_pool_tick=90, pool4_backlog_days=.3), theme=theme)
    assert [text.strip() for text, _ in rows] == [
        'SIGNALS', 'burning      OFF · headroom 10', 'cheaper pool no edge  100/90',
        'backstop     unknown', 'drip backlog 0.3d',
    ]
    for value in ('OFF · headroom 10', 'no edge  100/90', 'unknown', '0.3d'):
        assert_normal(rows, value, normal)
    for label in ('SIGNALS', 'burning', 'cheaper pool', 'backstop', 'backlog'):
        assert_gray(rows, label, normal)


@pytest.mark.asyncio
@pytest.mark.parametrize('backstop', ['deployed', 'none'])
async def test_signals_keep_existing_colored_status_accents(backstop, theme):
    rows, palette, normal = await painted(SurfPool4USignals, dict(
        pool4_network='MAINNET', pool4_cap_headroom=0, pool4_cheaper_venue='reference',
        pool4_venue_gap_pct=3.1, pool4_current_tick=68196, pool4_reference_pool_tick=68180,
        pool4_backstop_state=backstop, pool4_backstop_lower_tick=68280,
        pool4_backstop_eth=24.51, pool4_backlog_days=3.2), theme=theme)
    for value, color in [('ON · headroom 0', 2), ('REFERENCE −3.10%', 6),
                         ('deep · 3.2d · return understates', 3),
                         ('24.51 ETH', 2) if backstop == 'deployed'
                         else ('none deployed', 3)]:
        assert all(style.color.get_truecolor() == palette[color]
                   for style in styles_at(rows, value))
    for label in ('SIGNALS', 'burning', 'cheaper pool', 'backstop', 'backlog'):
        assert_gray(rows, label, normal)
