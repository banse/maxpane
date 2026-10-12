"""Production protocol overview geometry, including its native evidence panels."""
import pytest

from maxpane_dashboard.data.surf_models import POOL4_KEYS
from maxpane_dashboard.data.surf_protocol_hero import project
from maxpane_dashboard.screens.surf import (
    POOL4_LEFT_ID, POOL4_RAIL_ID, SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_ROWS, TALLER_HINT,
)
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.rowfit import cell_len
from maxpane_dashboard.widgets.surf.protocol_hero import SurfProtocolHero
from tests.screens._sweeps import boundary_set
from tests.screens.test_surf_pool4_screen import (
    MEASURED_POOL4_COLUMNS, MEASURED_POOL4_ROWS, _POOL4_HEIGHT_PAYLOADS,
    _clipped_pool4_lines, _pool4_app, _pool4_marked, _pool4_payload,
)
from tests.screens.test_surf_screen import _mainnet_pool4_payload, _region_text, _screen_text


def _protocol_payload(kind):
    data = _pool4_payload() if kind == "direct" else _mainnet_pool4_payload()
    if kind == "partial":
        data["pool4_distributor_nodes_bps"] = None
    elif kind == "unavailable":
        data.update({key: None for key in POOL4_KEYS})
    elif kind == "signed-large":
        data["pool4_tokens_in_pool"] = data["pool4_inventory_cap"] + 1_234_567.89
        data["pool4_cap_headroom"] = data["pool4_inventory_cap"] - data["pool4_tokens_in_pool"]
        data["pool4_total_rewarded"] = 123_456_789.12
    data["surf_protocol_hero"] = project(
        data=data, sources={"pool4": dict(state="stale" if kind == "stale" else "ok", read_ts=990)}, now=1000)
    return data


def _lost_card_text(app, card):
    """Unfitted record facts checked against the actual compositor, not render()."""
    text = _region_text(app, card)
    record = card.data
    footer = card.border_subtitle
    footer = footer.plain if hasattr(footer, "plain") else strip_tags(footer)
    expected = [record.title, record.heading, footer, *record.rows]
    if record.subtitle:
        expected.append(record.subtitle)
    lost = [part for part in expected if part and part not in text]
    for label, value in record.stats:
        if not any(label in line and value in line for line in text.splitlines()):
            lost.append((label, value))
    return lost


@pytest.mark.parametrize("kind", ["direct", "mainnet", "partial", "stale", "unavailable", "signed-large"])
@pytest.mark.parametrize("width", boundary_set(SURF_POOL4_FULL_LAYOUT_COLUMNS, 100, 170))
async def test_protocol_view_is_whole_at_width_and_advertises_each_lost_card(width, kind):
    async with _pool4_app(_protocol_payload(kind)).run_test(size=(width, 60)) as pilot:
        app = pilot.app
        await app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        hero = app.screen.query_one(SurfProtocolHero)
        cards = list(hero.children)
        assert len(cards) == 6 and {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        assert cards[-1].region.right <= width
        for card in cards:
            lost = _lost_card_text(app, card)
            marked = "‹" in _region_text(app, card)
            if lost:
                assert marked, (kind, width, card.data.key, lost)
            if width >= SURF_POOL4_FULL_LAYOUT_COLUMNS:
                assert not lost and not marked, (kind, width, card.data.key, lost)
        if width >= SURF_POOL4_FULL_LAYOUT_COLUMNS:
            assert not _pool4_marked(app, app.screen)
            assert not _clipped_pool4_lines(app, app.screen)


async def test_protocol_width_pin_is_bound_by_the_direct_route_row():
    """A pin one column too low OR high fails against painted route text."""
    async with _pool4_app(_protocol_payload("direct")).run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS - 1, 60)
    ) as pilot:
        app = pilot.app
        await app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        card = app.screen.query_one(SurfProtocolHero).query_one("#hero-split")
        assert "direct to stakers" not in _region_text(app, card)
        assert "‹" in _region_text(app, card)
        assert not _pool4_marked(app, app.screen), "the native body has its own 99-column boundary"
        await pilot.resize_terminal(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)
        await pilot.pause()
        assert "direct to stakers" in _region_text(app, card)
        assert "‹" not in _region_text(app, card)
        assert card.content_size.width - 2 == cell_len("direct to stakers")
        assert SURF_POOL4_FULL_LAYOUT_COLUMNS == MEASURED_POOL4_COLUMNS


async def test_protocol_height_boundary_is_tight_and_resize_restores_all_content():
    payload = _POOL4_HEIGHT_PAYLOADS["mainnet-capped"]()
    async with _pool4_app(payload).run_test(size=(149, 45)) as pilot:
        app = pilot.app
        await app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        rail = app.screen.query_one(f"#{POOL4_RAIL_ID}")
        left = app.screen.query_one(f"#{POOL4_LEFT_ID}")
        assert rail.show_vertical_scrollbar and TALLER_HINT in _screen_text(app)
        rail.scroll_end(animate=False)
        await pilot.pause()
        assert rail.scroll_y > 0 and "sIMD VAULT" in _region_text(app, rail)
        for rows in (SURF_POOL4_FULL_LAYOUT_ROWS - 1, SURF_POOL4_FULL_LAYOUT_ROWS):
            await pilot.resize_terminal(SURF_POOL4_FULL_LAYOUT_COLUMNS, rows)
            await pilot.pause()
            await pilot.pause()
            scrolling = left.show_vertical_scrollbar or rail.show_vertical_scrollbar
            assert scrolling is (rows < SURF_POOL4_FULL_LAYOUT_ROWS)
            assert (TALLER_HINT in _screen_text(app)) is scrolling
        assert max(left.virtual_size.height, rail.virtual_size.height) == 34
        assert app.size.height - rail.region.height == 13
        assert SURF_POOL4_FULL_LAYOUT_ROWS == MEASURED_POOL4_ROWS
        assert rail.scroll_y == 0
        assert all(not _lost_card_text(app, card) for card in app.screen.query_one(SurfProtocolHero).children)
        assert not _clipped_pool4_lines(app, app.screen)


async def test_extreme_signed_values_mark_instead_of_hiding_their_sign():
    data = _mainnet_pool4_payload(pool4_cap_headroom=-123_456_789_012_345.)
    async with _pool4_app(data).run_test(size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        app = pilot.app
        await app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        card = app.screen.query_one(SurfProtocolHero).query_one("#hero-inventory")
        text = _region_text(app, card)
        assert "-1.235e+14" in text and "‹" in text
        await pilot.resize_terminal(170, 60)
        await pilot.pause()
        assert not _lost_card_text(app, card) and "‹" not in _region_text(app, card)
