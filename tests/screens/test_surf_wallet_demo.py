"""Wallet A/B prototype: offline semantics, navigation and composited layout."""
from collections import Counter
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from rich.color import Color
from textual.widgets import DataTable

from scripts.surf_wallet_demo import (
    SurfWalletDemo, export_demo, hero_records, mock_snapshot, usage_signal, usage_text,
)
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    def refuse(*args, **kwargs):
        raise AssertionError("wallet demo must not use network, user state or external actions")

    async def refuse_async(*args, **kwargs):
        refuse()

    for target in ("httpx.Client.send", "socket.create_connection", "webbrowser.open",
                   "maxpane_dashboard.config._read_config", "maxpane_dashboard.config._write_config",
                   "maxpane_dashboard.data.surf_cache.SurfCache.load",
                   "maxpane_dashboard.data.surf_cache.SurfCache.save"):
        monkeypatch.setattr(target, refuse)
    monkeypatch.setattr("httpx.AsyncClient.send", refuse_async)
    monkeypatch.setattr("maxpane_dashboard.clipboard.copy_text", refuse_async)


def test_complete_demo_fixture_counts_and_money_are_consistent():
    snapshot = mock_snapshot()
    orders, assets = snapshot["orders"], snapshot["artifacts"]
    assert len(orders) == len({r["id"] for r in orders}) == 84
    assert Counter(r["action"] for r in orders) == {
        "job.open": 32, "job.continue": 10, "workflow.open": 12,
        "launch.open": 8, "oracle.request": 16, "schedule.create": 2, "schedule.topup": 4,
    }
    assert sum(r["payment_state"] == "settled" for r in orders) == 78
    assert sum(r["paid_imd"] for r in orders) == Decimal("62.5")
    assert sum(r["refund_imd"] for r in orders) == Decimal("1.0")
    assert sum(r["in_flight"] for r in orders) == 5
    assert sum(r["follow_up"] for r in orders) == 4
    assert sum(r["action"] == "workflow.open" and r["outcome"] == "shipped" for r in orders) == 10
    assert sum(r["action"] == "launch.open" and r["outcome"] == "deployed" for r in orders) == 6
    assert sum(r["action"] == "oracle.request" and r["outcome"] == "attested" for r in orders) == 14
    assert Counter(a["kind"] for a in assets) == {"SITE": 10, "CONTRACT": 14, "TOKEN": 4}
    assert len({a["id"] for a in assets}) == 28
    assert len({(a["chain"], a["id"]) for a in assets if a["kind"] != "SITE"}) == 18
    assert all(a["order_id"] in {r["id"] for r in orders} for a in assets)
    by_id = {a["id"]: a for a in assets}
    assert sum(a["linked_id"] is not None for a in assets if a["kind"] == "SITE") == 8
    assert all(a["linked_id"] in by_id for a in assets if a["kind"] == "SITE" and a["linked_id"])
    assert sum(bool(a["usage"]) for a in assets if a["kind"] != "SITE") == 6
    assert sum(bool(a["usage"] and a["usage"]["complete"]) for a in assets if a["kind"] != "SITE") == 4
    counts = {r.title: r.digits for r in hero_records(snapshot, "overview")}
    assert counts == dict(REQUESTS="84", JOBS="42", WORKFLOWS="12", LAUNCHES="8",
                         ORACLES="16", SCHEDULES="6", SITES="10", CONTRACTS="18",
                         TOKENS="4", **{"IN FLIGHT": "5", "PAID": "62.5", "ATTENTION": "4"})


def test_usage_distinguishes_unknown_zero_partial_and_linked_evidence():
    by_id = {a["id"]: a for a in mock_snapshot()["artifacts"]}
    for identity, expected in {
        "site-atlas": "LINKED ACTIVE", "site-harbor": "LINKED QUIET",
        "contract-registry": "ACTIVE", "contract-vault": "QUIET",
        "token-credits": "FIRST SEEN", "token-access": "NO DATA",
        "site-static": "NO ONCHAIN LINK", "site-unresolved": "NO DATA",
    }.items():
        assert usage_signal(by_id[identity], by_id) == expected
    assert "27 registrations" in usage_text(by_id["site-atlas"], by_id)
    assert "0 deposits" in usage_text(by_id["contract-vault"], by_id)
    assert usage_text(by_id["token-access"], by_id) == "--"
    partial = dict(by_id["contract-vault"], usage=dict(by_id["contract-vault"]["usage"], complete=False))
    assert usage_signal(partial, by_id) == "NO DATA"
    assert usage_text(partial, by_id) == "--"
    positive = dict(partial, usage=dict(partial["usage"], count=2, actors=1))
    assert usage_signal(positive, by_id) == "ACTIVE"
    assert usage_text(positive, by_id).startswith(">=2 deposits")


async def test_overview_rack_and_tables_fit_owner_terminal():
    async with SurfWalletDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query("#overview NewsHeroCard"))
        assert len(cards) == 12 and {c.region.height for c in cards} == {9}
        assert cards[6].region.y == cards[0].region.bottom + 1
        assert [c.region.x for c in cards[:6]] == [c.region.x for c in cards[6:]]
        assert max(c.region.width for c in cards) - min(c.region.width for c in cards) <= 1
        for c in cards:
            output = painted(app, c)
            assert c.data.title in output and c.data.heading in output
            assert c.data.subtitle in output and c.data.footer in output
            assert all(corner in output for corner in "┌┐└┘")
        segments = [segment for strip in app.screen._compositor.render_strips() for segment in strip]
        edge = next(segment for segment in segments if "┌" in segment.text)
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        table = app.query_one("#overview-assets", DataTable)
        assert table.row_count == 28
        assert app.query_one("#orders", DataTable).row_count == 84
        output = painted(app)
        for text in ("DEMO DATA", "Orders 30D", "Assets ALL KNOWN", "Usage 24H",
                     "CREATED", "RECORD", "LINKED ACTIVE", "FIRST SEEN", "NO DATA", "1.0 IMD"):
            assert text in output
        for forbidden in ("SEATS", "WORKERS", "EFFORT", "ACCEPTED", "VISITORS", "P/L"):
            assert forbidden not in output
        assert app.query_one("#overview-selected").region.bottom <= app.query_one("#demo-footer").region.y
        viewport = app.query_one("#viewport")
        assert not viewport.max_scroll_x and not viewport.max_scroll_y


@pytest.mark.parametrize("identity, expected", [
    ("site-atlas", "LINKED ACTIVE"), ("contract-vault", "QUIET"),
    ("token-credits", "FIRST SEEN"), ("token-access", "NO DATA"),
    ("site-static", "NO ONCHAIN LINK"),
])
async def test_artifact_detail_and_escape_keep_exact_identity(identity, expected):
    async with SurfWalletDemo(selected_id=identity).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        app = pilot.app
        assert app.view == "detail" and app.selected_id == identity
        cards = list(app.query("#detail NewsHeroCard"))
        assert len(cards) == 6 and {c.region.height for c in cards} == {9}
        assert len({c.region.y for c in cards}) == 1
        assert max(c.region.width for c in cards) - min(c.region.width for c in cards) <= 1
        assert all(l.region.right < r.region.x for l, r in zip(cards, cards[1:]))
        for card in cards:
            output = painted(app, card)
            assert all(s in output for s in (card.data.title, card.data.heading, card.data.subtitle, card.data.footer))
            assert all(edge in output for edge in "┌┐└┘")
        detail = painted(app, app.query_one("#artifact-detail"))
        assert expected in detail and app.by_id[identity]["name"] in detail
        if identity == "site-atlas":
            assert "frontend origin not proven" in detail
        if identity == "token-access":
            assert "--" in detail and "0 redemptions" not in detail
        if identity == "token-credits":
            assert "Tracking since" in detail and "first-ever" in detail
        assert not app.query_one("#viewport").max_scroll_y
        await pilot.press("escape")
        await pilot.pause()
        assert app.view == "overview" and app.selected_id == identity
        table = app.query_one("#overview-assets", DataTable)
        assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == identity


async def test_detail_selection_changes_and_returns_without_index_reset():
    async with SurfWalletDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.press("enter", "down", "down")
        await pilot.pause()
        app = pilot.app
        assert app.selected_id == "contract-registry"
        assert "Atlas Registry" in painted(app, app.query_one("#artifact-detail"))
        await pilot.press("escape")
        await pilot.pause()
        assert app.selected_id == "contract-registry"
        assert app.query_one("#overview-assets", DataTable).cursor_row == 2
        await pilot.press("tab")
        assert app.focused is app.query_one("#orders")


async def test_narrow_scroll_and_restore_reach_both_modes():
    async with SurfWalletDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for view in ("overview", "detail"):
            if view == "detail":
                await pilot.press("enter")
            await pilot.resize_terminal(100, 30)
            await pilot.pause()
            vp = pilot.app.query_one("#viewport")
            assert vp.max_scroll_x > 0 and vp.max_scroll_y > 0
            vp.scroll_to(x=vp.max_scroll_x, y=0, animate=False)
            await pilot.pause()
            assert "ATTENTION" in painted(pilot.app)
            vp.scroll_to(x=0, y=vp.max_scroll_y, animate=False)
            await pilot.pause()
            assert "RECORD" in painted(pilot.app) if view == "overview" else "REQUESTS" in painted(pilot.app)
            await pilot.resize_terminal(149, 45)
            await pilot.pause()
            assert not vp.max_scroll_x and not vp.max_scroll_y
            assert "DEMO DATA" in painted(pilot.app)
        assert pilot.app.view == "detail"


async def test_exports_both_views_and_unknown_selection_is_rejected(tmp_path):
    for view in ("overview", "detail"):
        output = tmp_path / f"wallet-{view}.svg"
        await export_demo(output, (149, 45), view, "token-access")
        svg = output.read_text()
        visible = "".join(ElementTree.fromstring(svg).itertext()).replace("\u00a0", " ")
        assert "<svg" in svg and "DEMO DATA" in visible and "Signal" in visible
    with pytest.raises(ValueError, match="artifact"):
        SurfWalletDemo(selected_id="missing")
    with pytest.raises(ValueError, match="view"):
        SurfWalletDemo(view="unknown")
