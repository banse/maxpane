"""In-situ rack geometry, using the production screen and app stylesheet."""
from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard.screens.surfboard import (
    SurfboardScreen, SURFBOARD_FULL_LAYOUT_COLUMNS, SURFBOARD_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.surfboard_fixtures import HubPayloadManager, STAMP, hub_payload
from tests.screens._sweeps import boundary_set


class HubHarness(App):
    CSS_PATH = Path(__file__).resolve().parents[2] / "maxpane_dashboard/themes/minimal.tcss"

    def __init__(self, payload):
        super().__init__()
        self.hub = SurfboardScreen(HubPayloadManager(payload), name="surfboard")

    def on_mount(self):
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = "matrix"
        self.push_screen(self.hub)


@pytest.mark.parametrize("state", ("ok", "stale"))
async def test_projected_pool4_value_period_ratio_and_source_clocks_fit_owner_size(state):
    from maxpane_dashboard.data import surfboard as projection

    # Public live values retain their real precision; only the return is supplied
    # to cover the successful path missing from that live API response.
    raw = dict(pool4_vault_assets=1795886.4737732294, pool4_total_supply=4143519.145292,
               pool4_network="MAINNET", pool4_as_of_hhmm="01:04",
               pool4_price_usd=7.878357502256693, pool4_trailing_return_pct=1.4)
    families = {name: dict(state=state, read_ts=STAMP)
                for name in ("pool4", "market")}
    payload = hub_payload()
    card = next(c for c in projection.cards(raw, {}, now=STAMP, family_sources=families)
                if c["key"] == "pool4")
    payload["surfboard_cards"] = [card if c["key"] == "pool4" else c
                                  for c in payload["surfboard_cards"]]
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app.hub.query_one(SurfboardRack).focus_card("pool4")
        await pilot.pause()
        lines = [strip.text for strip in app.hub._compositor.render_strips()]
        detail = lines[-2]
        assert f"market {state} · read {projection.hhmm(STAMP)}" in detail
        assert f"pool4 {state} · read {projection.hhmm(STAMP)}" in detail
        assert "1,795,886.4737732294 / 4,143,519.145292" in detail
        assert "1.40% / 7d" in "\n".join(lines)
        assert "‹ widen" not in str(app.hub.query_one("#surfboard-card-pool4").border_title)


async def test_focused_detail_marks_overflow_until_the_whole_line_fits():
    payload = hub_payload()
    payload["surfboard_cards"][0]["detail"] = "Full meter detail " + "1234567890 " * 18
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "detail ‹ widen" in app.hub._compositor.render_strips()[0].text
        await pilot.resize_terminal(240, 45)
        await pilot.pause()
        assert "detail ‹ widen" not in app.hub._compositor.render_strips()[0].text
        assert payload["surfboard_cards"][0]["detail"].strip() in app.hub._compositor.render_strips()[-2].text


async def _render(payload, size):
    app = HubHarness(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        screen = app.hub
        viewport = screen.query_one("#surfboard-viewport")
        rack = screen.query_one(SurfboardRack)
        terminal = screen.query_one(SurfboardTerminal)
        cards = list(rack.query(SurfboardCard))
        strips = screen._compositor.render_strips()
        lines = ["".join(segment.text for segment in strip) for strip in strips]
        text = "\n".join(lines)
        card_regions = {card.key: card.region for card in cards}
        card_text = {card.key: "\n".join(
            strip.crop(card.region.x, card.region.right).text
            for strip in strips[max(0, card.region.y):card.region.bottom]) for card in cards}
        clipped = []
        for card in cards:
            if "‹ widen" in str(card.border_title):
                clipped.append(card.key)
        bar = screen.query_one(StatusBar)
        right = bar.query_one("#status-right")
        return dict(text=text, size=size, cards=card_regions, card_text=card_text,
                    terminal=terminal.region, rack=rack.region,
                    horizontal=viewport.show_horizontal_scrollbar,
                    vertical=viewport.show_vertical_scrollbar,
                    clipped=clipped, status_whole=right.region.right <= size[0],
                    heights={card.key: card.region.height for card in cards},
                    widths={card.key: card.region.width for card in cards})


@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
async def test_owner_size_preserves_all_twelve_slots_and_three_row_terminal(kind):
    r = await _render(hub_payload(kind), (149, 45))
    assert not r["horizontal"] and not r["vertical"] and not r["clipped"], r
    assert r["status_whole"], r
    assert len(r["cards"]) == 12
    assert len({region.y for region in r["cards"].values()}) == 4
    assert len({r["cards"][key].y for key in ("announce", "swarm", "agent", "board", "launchpad", "pool4")}) == 1
    assert r["terminal"].y == r["cards"]["protocol"].y == r["cards"]["swarm-tokens"].y
    assert r["terminal"].bottom == r["cards"]["bay-11"].bottom == r["cards"]["bay-12"].bottom
    assert r["cards"]["protocol"].right < r["terminal"].x < r["terminal"].right < r["cards"]["swarm-tokens"].x
    for title in ("ANNOUNCE", "SWARM", "AGENT", "BOARD", "LAUNCHPAD", "POOL4", "PROTOCOL",
                  "SWARM TOKENS", "PORTFOLIO", "EARNINGS", "BAY 11", "BAY 12"):
        assert title in r["text"], (title, r["text"])


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
@pytest.mark.parametrize("width", boundary_set(SURFBOARD_FULL_LAYOUT_COLUMNS, 110, 160, 139))
async def test_width_boundary_reserves_six_columns_even_with_vertical_scrolling(kind, width):
    r = await _render(hub_payload(kind), (width, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    assert r["horizontal"] == (width < SURFBOARD_FULL_LAYOUT_COLUMNS), r
    assert ("‹ widen" in r["text"].splitlines()[0]) == r["horizontal"], r
    assert len({region.y for region in r["cards"].values()}) == 4
    if width >= SURFBOARD_FULL_LAYOUT_COLUMNS:
        assert not r["clipped"] and r["status_whole"], r


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
@pytest.mark.parametrize("height", boundary_set(SURFBOARD_FULL_LAYOUT_ROWS, 25, 55))
async def test_height_boundary_keeps_card_content_or_advertises_scroll(kind, height):
    payload = hub_payload(kind)
    r = await _render(payload, (SURFBOARD_FULL_LAYOUT_COLUMNS, height))
    assert r["vertical"] == (height < SURFBOARD_FULL_LAYOUT_ROWS), r
    assert ("‹ taller" in r["text"].splitlines()[0]) == r["vertical"], r
    assert not r["horizontal"] and not r["clipped"] and r["status_whole"], r
    assert all(value >= 7 for value in r["heights"].values()), r
    if height >= SURFBOARD_FULL_LAYOUT_ROWS:
        for card in payload["surfboard_cards"][:7]:
            assert card["primary"] in r["card_text"][card["key"]], (card, r)
            assert card["secondary"] in r["card_text"][card["key"]], (card, r)


async def test_width_pin_is_the_measured_scroll_transition():
    below = await _render(hub_payload(), (SURFBOARD_FULL_LAYOUT_COLUMNS - 1, 35))
    at = await _render(hub_payload(), (SURFBOARD_FULL_LAYOUT_COLUMNS, 35))
    assert below["horizontal"] and not at["horizontal"], (below, at)
    assert "‹ widen" in below["text"].splitlines()[0]
    assert "‹ widen" not in at["text"].splitlines()[0]


async def test_height_pin_is_the_measured_scroll_transition():
    below = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    at = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS))
    assert below["vertical"] and not at["vertical"], (below, at)
    assert "‹ taller" in below["text"].splitlines()[0]
    assert "‹ taller" not in at["text"].splitlines()[0]
