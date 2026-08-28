"""In-situ screen and layout contracts for FWA NETWORK."""

from __future__ import annotations

from rich.cells import cell_len
from textual.widgets import DataTable, RichLog

from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    FWA_NETWORK_WIDGET_SIGNATURES,
    blank_network_payload,
)
from maxpane_dashboard.screens.fwa import (
    FWA_NETWORK_FULL_LAYOUT_COLUMNS,
    FWA_NETWORK_FULL_LAYOUT_ROWS,
    FWAScreen,
)
from maxpane_dashboard.widgets.fwa import (
    FWAActivityFeed,
    FWAEcosystemRegistry,
    FWAFlowRail,
    FWAHeroMetrics,
    FWAIRDropBoard,
    FWANetworkActivity,
    FWANetworkHero,
)
from maxpane_dashboard.widgets.fwa.fwa_ecosystem_registry import (
    REGISTRY_TABLE_TIERS,
)
from maxpane_dashboard.widgets.fwa.fwair_drop_board import DROP_TABLE_TIERS
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.screens.test_fwa_screen import (
    _FakeManager,
    _ThemedHarness,
    _frozen_payload,
    _screen_text,
)


def _network_payload(**overrides) -> dict:
    payload = _frozen_payload()
    payload.update(blank_network_payload())
    payload.update(
        {
            "network_ready": True,
            "network_state_block": 25_849_738,
            "network_chain_head": 25_849_740,
            "network_state_stale": False,
            "network_active_listings": 6_185,
            "network_pull_quote_eth": 0.0723,
            "network_pending_count": 3,
            "network_unsettled_count": 3,
            "network_crown_pot_eth": 3.622,
            "network_token_supply_fwa": 986_380_000.0,
            "network_burned_since_genesis_fwa": 13_620_000.0,
            "network_burned_since_genesis_pct": 1.362,
            "network_last_buyback_age_s": 12.0,
            "network_drop_count": 2,
            "network_project_family_count": 3,
            "network_project_healthy_count": 3,
            "network_project_degraded_count": 0,
            "network_project_unverified_count": 1,
            "network_flow_rows": [],
            "network_flow_available": True,
            "network_flow_history_complete": True,
            "network_flow_as_of_block": 25_849_738,
            "network_flow_as_of_ts": 1_784_900_000.0,
            "network_flow_stale": False,
            "network_drop_rows": [],
            "network_drops_available": True,
            "network_drops_as_of_block": 25_849_738,
            "network_drops_stale": False,
            "network_project_rows": [],
            "network_projects_available": True,
            "network_projects_as_of_block": 25_849_738,
            "network_projects_stale": False,
            "network_events": [],
            "network_feed_available": True,
            "network_feed_unavailable_reason": None,
            "network_feed_as_of_ts": 1_784_900_000.0,
            "network_degraded_sources": [],
            "network_integrity_warning_count": 0,
            "network_last_updated_seconds_ago": 7.0,
            "network_error_count": 0,
        }
    )
    payload.update(overrides)
    return payload


async def test_pulls_is_default_and_mode_switches_never_fetch() -> None:
    manager = _FakeManager(_network_payload())
    screen = FWAScreen(manager, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        calls = manager.calls

        assert screen._mode == "pulls"
        assert screen._pulls_view == "odds"
        assert screen.query_one(FWAHeroMetrics).display is True
        assert screen.query_one(FWANetworkHero).display is False

        await pilot.press("e")
        await pilot.pause()
        assert manager.calls == calls
        assert screen._mode == "network"
        assert screen.query_one(FWAHeroMetrics).display is False
        assert screen.query_one(FWANetworkHero).display is True
        assert "FWA NETWORK" in _screen_text(app)

        await pilot.press("c")
        await pilot.pause()
        assert manager.calls == calls
        assert screen._mode == "network"
        assert screen._pulls_view == "odds"

        await pilot.press("e")
        await pilot.press("c")
        await pilot.press("e")
        await pilot.press("escape")
        await pilot.pause()
        assert manager.calls == calls
        assert screen._mode == "pulls"
        assert screen._pulls_view == "activity"
        assert screen.query_one(FWAActivityFeed).display is True


async def test_existing_pulls_sections_remain_direct_children_in_order() -> None:
    screen = FWAScreen(_FakeManager(_network_payload()), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        pulls_sections = [
            screen.query_one(FWAHeroMetrics),
            screen.query_one("#middle-row"),
            screen.query_one("#separator"),
            screen.query_one("#bottom-row"),
        ]
        assert all(section.parent is screen for section in pulls_sections)
        child_positions = [list(screen.children).index(section) for section in pulls_sections]
        assert child_positions == sorted(child_positions)


async def test_status_bar_uses_only_the_existing_active_view_surface() -> None:
    screen = FWAScreen(_FakeManager(_network_payload()), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        bar = screen.query_one(StatusBar)
        assert bar._active_view == "pulls/odds · e network"
        assert bar._key_hints == ""
        assert "updated 2s ago" in _screen_text(app)

        await pilot.press("e")
        await pilot.pause()
        assert bar._active_view == "network · e pulls"
        assert bar._key_hints == ""
        assert "updated 7s ago" in _screen_text(app)


async def test_blank_network_never_claims_a_fresh_zero_age() -> None:
    payload = _frozen_payload()
    payload.update(blank_network_payload())
    screen = FWAScreen(_FakeManager(payload), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert "CHAIN N/A" in _screen_text(app)
        assert "updated 999s ago" in _screen_text(app)


async def test_network_is_composed_once_and_fully_populated_while_hidden() -> None:
    manager = _FakeManager(_network_payload())
    screen = FWAScreen(manager, name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        identities = {
            cls: id(screen.query_one(cls))
            for cls in (
                FWANetworkHero,
                FWAFlowRail,
                FWAIRDropBoard,
                FWAEcosystemRegistry,
                FWANetworkActivity,
            )
        }
        hero = screen.query_one(FWANetworkHero)
        assert "6,185 listings" in hero.query_one("#fwa-network-platform").visual.plain

        await pilot.press("e")
        await pilot.press("e")
        await pilot.pause()
        assert identities == {cls: id(screen.query_one(cls)) for cls in identities}


async def test_screen_dispatches_every_network_key_to_widget_or_chrome() -> None:
    manager = _FakeManager(_network_payload())
    screen = FWAScreen(manager, name="fwa")
    app = _ThemedHarness(screen)
    classes = {
        "FWANetworkHero": FWANetworkHero,
        "FWAFlowRail": FWAFlowRail,
        "FWAIRDropBoard": FWAIRDropBoard,
        "FWAEcosystemRegistry": FWAEcosystemRegistry,
        "FWANetworkActivity": FWANetworkActivity,
    }
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        calls: dict[str, list[dict]] = {name: [] for name in classes}
        for name, widget_class in classes.items():
            widget = screen.query_one(widget_class)
            original = widget.update_data

            def recorder(*, _name=name, _original=original, **kwargs):
                calls[_name].append(kwargs)
                return _original(**kwargs)

            widget.update_data = recorder

        await screen._do_refresh()
        await pilot.pause()

        dispatched: set[str] = set()
        for name, signature in FWA_NETWORK_WIDGET_SIGNATURES.items():
            assert calls[name]
            assert tuple(calls[name][-1]) == signature
            dispatched.update(signature)

        chrome = {
            "network_chain_head",
            "network_degraded_sources",
            "network_integrity_warning_count",
            "network_last_updated_seconds_ago",
            "network_error_count",
        }
        assert set(FWA_NETWORK_DATA_KEYS) == dispatched | chrome


def _smallest_table_tiers_fit(screen: FWAScreen) -> bool:
    registry = screen.query_one(FWAEcosystemRegistry).query_one(DataTable)
    drops = screen.query_one(FWAIRDropBoard).query_one(DataTable)
    return (
        registry.content_size.width >= REGISTRY_TABLE_TIERS[-1][1]
        and drops.content_size.width >= DROP_TABLE_TIERS[-1][1]
    )


def test_network_does_not_raise_the_application_width_pin() -> None:
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert FULL_LAYOUT_COLUMNS == 143
    assert FWA_NETWORK_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS


async def test_measured_width_pin_is_the_first_complete_fallback_seam() -> None:
    screen = FWAScreen(_FakeManager(_network_payload()), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(
        size=(FWA_NETWORK_FULL_LAYOUT_COLUMNS - 1, FWA_NETWORK_FULL_LAYOUT_ROWS)
    ) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert not _smallest_table_tiers_fit(screen)

        await pilot.resize_terminal(
            FWA_NETWORK_FULL_LAYOUT_COLUMNS,
            FWA_NETWORK_FULL_LAYOUT_ROWS,
        )
        await pilot.pause()
        assert _smallest_table_tiers_fit(screen)

        await pilot.resize_terminal(
            FWA_NETWORK_FULL_LAYOUT_COLUMNS + 1,
            FWA_NETWORK_FULL_LAYOUT_ROWS,
        )
        await pilot.pause()
        assert _smallest_table_tiers_fit(screen)


async def test_measured_height_pin_scrolls_below_and_clears_at_boundary() -> None:
    screen = FWAScreen(_FakeManager(_network_payload()), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(
        size=(143, FWA_NETWORK_FULL_LAYOUT_ROWS - 1)
    ) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        main = screen.query_one("#fwa-network-main")
        assert main.max_scroll_y > 0
        assert "taller" in screen.query_one("#title-bar").visual.plain

        await pilot.resize_terminal(143, FWA_NETWORK_FULL_LAYOUT_ROWS)
        await pilot.pause()
        assert main.max_scroll_y == 0
        assert screen.query_one("#fwa-network-rail").max_scroll_y == 0
        assert "taller" not in screen.query_one("#title-bar").visual.plain


async def test_real_143_column_layout_has_3_to_2_seam_and_fitted_logs() -> None:
    screen = FWAScreen(_FakeManager(_network_payload()), name="fwa")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, 48)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        main = screen.query_one("#fwa-network-main")
        rail = screen.query_one("#fwa-network-rail")
        assert abs(main.size.width / rail.size.width - 1.5) < 0.05
        assert str(main.styles.scrollbar_gutter) == "stable"
        assert str(rail.styles.scrollbar_gutter) == "stable"

        for selector in ("#fwa-flow-log", "#fwa-network-activity-log"):
            log = screen.query_one(selector, RichLog)
            assert log.wrap is False
            assert all(cell_len(strip.text) <= log.content_size.width for strip in log.lines)

        text = _screen_text(app)
        assert "FWA VALUE FLOW" in text
        assert "VERIFIED INTEGRATIONS" in text
        assert "FWAIR DROPS" in text
        assert "NETWORK ACTIVITY" in text
        assert "ODDS BOARD" not in text
