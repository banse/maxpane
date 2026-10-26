"""Wallet rendering uses projected facts only; no fetch is triggered by selection."""
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from textual.app import App
from textual.widgets import DataTable, Static

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf_wallet import WalletBody, WIDGET_SIGNATURES


NOW = 1792929600
ADDRESS = "0x1111111111111111111111111111111111111111"
TOKEN = "0x2222222222222222222222222222222222222222"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("wallet widgets must not fetch")
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.delenv("NO_COLOR", raising=False)


def snapshot():
    orders = [dict(id=f"request-{i}", action=action, name=f"Request {i}", timestamp=NOW-i*3600,
                   status="completed", payment_state="settled", outcome="delivered",
                   in_flight=False, follow_up=False,
                   payments=[dict(chain_id=8453, asset=TOKEN, symbol="IMD", decimals=18, amount="2.5",
                                  tx_hash="0x"+str(i+1)*64, log_index=0)])
              for i, action in enumerate(("job.open", "workflow.open", "launch.open", "oracle.request", "schedule.create"))]
    usage = dict(count=7, actors=3, unit="claims", complete=True, first_seen=False,
                 rule="Claimed(address)", evidence=[dict(label="Verified receipt", url="https://basescan.org/tx/" + "0x" + "a"*64)],
                 latest=NOW-10, observed_at=NOW, from_block=10, to_block=100, tracking_since=NOW-86400)
    artifacts = [
        dict(id="site", kind="SITE", name="Portal", chain="BASE", chain_id=8453, linked_id="registry", binding_checked=True,
             order_id="request-1", site_url="https://portal.example.org", project="portal", usage=None),
        dict(id="registry", kind="CONTRACT", name="Registry [/x]", chain="BASE", chain_id=8453, address=ADDRESS,
             order_id="request-1", binding_checked=True, usage=usage),
        dict(id="token", kind="TOKEN", name="Credits", chain="ETH", chain_id=1, address=TOKEN,
             order_id="request-2", binding_checked=True, usage=None),
        dict(id="static", kind="SITE", name="Handbook", chain="--", binding_checked=True, usage=None),
    ]
    return dict(wallet=ADDRESS, orders=orders, artifacts=artifacts, schedules=[], as_of=NOW,
                payment_totals=[dict(chain_id=8453, asset=TOKEN, symbol="IMD", decimals=18, paid="12.5", refunded=None,
                                     paid_complete=True, refund_complete=False, count=5)],
                sources={"orders": dict(state="ok", observed_at=NOW, complete=True)}, coverage=["orders complete"])


class WalletApp(App):
    CSS_PATH = Path(__file__).resolve().parents[2] / "maxpane_dashboard/themes/minimal.tcss"
    CSS = "#wallet-test-header, #wallet-test-footer {height:1;} WalletBody {height:1fr;}"

    def __init__(self, data=None, view_state=None):
        super().__init__()
        self.data = data
        self.view_state = view_state
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield Static("WALLET / SWARM", id="wallet-test-header")
        yield WalletBody(view_state=self.view_state)
        yield Static("Enter artifact · Esc overview", id="wallet-test-footer")

    def on_mount(self):
        self.query_one(WalletBody).update_data(wallet_snapshot=self.data)


def painted(app, widget=None):
    strips = app.screen._compositor.render_strips()
    if widget is None:
        return "\n".join(strip.text for strip in strips)
    region = widget.region
    return "\n".join(strip.crop(region.x, region.right).text for strip in strips[region.y:region.bottom])


def test_signature_agreement():
    from maxpane_dashboard.data.surf_wallet_models import WALLET_WIDGET_SIGNATURES
    assert WIDGET_SIGNATURES == WALLET_WIDGET_SIGNATURES


@pytest.mark.asyncio
async def test_first_read_all_widgets_and_empty_observation():
    async with WalletApp().run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        output = painted(pilot.app)
        for title in ("REQUESTS", "JOBS", "WORKFLOWS", "LAUNCHES", "ORACLES", "SCHEDULES", "REQUEST ACTIVITY", "REQUEST STATUS", "ONCHAIN USE", "PAYMENTS", "CREATED", "SELECTED", "ATTENTION", "RECORD"):
            assert title in output
        cards = list(body.query(NewsHeroCard))
        assert len(cards) == 12
        assert all(not card._display_record.digits for card in cards)
        data = snapshot()
        data.update(orders=[], artifacts=[], payment_totals=[])
        body.update_data(wallet_snapshot=data)
        await pilot.pause()
        assert body.query_one("#hero-wallet-overview-requests", NewsHeroCard)._display_record.digits == "0"
        assert body.query_one("#hero-wallet-detail-paid", NewsHeroCard)._display_record.digits == "0"
        assert "No created artifacts" in painted(pilot.app)


@pytest.mark.asyncio
async def test_overview_detail_live_values_and_segmented_bars():
    async with WalletApp(snapshot()).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        output = painted(pilot.app)
        assert "Registry [/x]" in output
        assert "LINKED ACTIVE" in output and "NO DATA" in output
        assert "▰" in output and "▱" in output
        assert "Refunded" in output and "--" in output
        assert "12.5" in output
        assert "DEMO" not in output
        table = body.query_one("#wallet-overview-assets", DataTable)
        table.focus()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert body.view == "detail" and body.selected_id == "registry"
        output = painted(pilot.app)
        assert "ONCHAIN USE / 24H" in output and "7 claims / 3 addresses" in output
        assert "Claimed(address)" in output
        assert ADDRESS in output and "⧉" in output
        assert "Refunded" in output
        assert body.back() is True
        await pilot.pause()
        assert body.view == "overview" and body.selected_id == "registry"
        assert body.back() is False


@pytest.mark.asyncio
async def test_refresh_retains_identity_without_rebuilding_unchanged_tables():
    data = snapshot()
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        table = body.query_one("#wallet-overview-assets", DataTable)
        table.move_cursor(row=2)
        await pilot.pause()
        assert body.selected_id == "token"
        original_row = next(iter(table.rows.values()))
        body.update_data(wallet_snapshot=deepcopy(data))
        await pilot.pause()
        assert next(iter(table.rows.values())) is original_row
        data["artifacts"].reverse()
        body.update_data(wallet_snapshot=data)
        await pilot.pause()
        assert body.selected_id == "token"
        assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == "token"
        body.show_view("detail")
        await pilot.pause()
        assert body.selected_id == "token"


@pytest.mark.asyncio
async def test_wallet_change_clears_retained_digits_selection_and_links():
    async with WalletApp(snapshot()).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        body.show_view("detail")
        await pilot.pause()
        assert body.source_links
        body.update_data(wallet_snapshot=dict(wallet=TOKEN, orders=None, artifacts=None, as_of=None))
        await pilot.pause()
        assert body.selected_id is None
        assert body.source_links == []
        assert all(not card._display_record.digits for card in body.query(NewsHeroCard))
        assert "Portal" not in painted(pilot.app)


@pytest.mark.asyncio
async def test_address_links_and_unknown_chain_never_guessed():
    data = snapshot()
    data["artifacts"][2].update(chain_id=999, chain="OTHER")
    data["artifacts"][0]["site_url"] = "javascript:alert(1)"
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        table = body.query_one("#wallet-overview-assets", DataTable)
        registry_name = table.get_row("registry")[1]
        assert "⧉" in registry_name.plain
        assert any(span.style.link == f"https://basescan.org/address/{ADDRESS}" for span in registry_name.spans if hasattr(span.style, "link"))
        token_name = table.get_row("token")[1]
        assert "⧉" in token_name.plain
        assert not any(getattr(span.style, "link", None) for span in token_name.spans)
        assert not any(url.startswith("javascript:") for url in body.source_links)


@pytest.mark.asyncio
async def test_narrow_scroll_and_recover_preserves_footer_and_selection():
    async with WalletApp(snapshot()).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        body.show_view("detail")
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = body.query_one("#wallet-viewport")
        assert viewport.max_scroll_x > 0 and viewport.max_scroll_y > 0
        assert "Esc overview" in painted(pilot.app)
        viewport.scroll_end(animate=False)
        await pilot.pause()
        assert viewport.scroll_y > 0
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert body.selected_id == "site"
        assert "SITES" in painted(pilot.app)


@pytest.mark.asyncio
async def test_partial_usage_history_and_same_wallet_retention_remain_truthful():
    data = snapshot()
    data["sources"]["orders"]["truncated"] = True
    data["artifacts"][1]["usage"].update(count=0, actors=0, complete=False)
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        output = painted(pilot.app)
        assert "QUIET" not in output
        assert "·" in painted(pilot.app, body.query_one("#wallet-activity-content"))
        assert body.query_one("#wallet-overview-assets", DataTable).get_row("registry")[-1].plain == "NO DATA"
        body.update_data(wallet_snapshot=dict(wallet=ADDRESS, orders=None, artifacts=None, as_of=None))
        await pilot.pause()
        assert "Registry [/x]" in painted(pilot.app)
        assert body.query_one("#hero-wallet-overview-requests", NewsHeroCard)._display_record.digits == "5"


@pytest.mark.asyncio
async def test_payment_assets_stay_separate_and_are_scroll_reachable():
    data = snapshot()
    data["orders"][0]["payments"] = [dict(chain_id=1, asset=TOKEN, symbol="ALT [/x]", decimals=6, amount="987.25",
                                         tx_hash="0x"+"f"*64, log_index=0)]
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        panel = body.query_one("#wallet-payments")
        scroller = panel.query_one(".wallet-insight-scroll")
        assert scroller.max_scroll_y > 0
        output = painted(pilot.app, panel)
        assert "987.25" in output
        assert "ALT [/x]" in output
        assert "997.25" not in output
        scroller.scroll_end(animate=False)
        await pilot.pause()
        output = painted(pilot.app, panel)
        assert "10.0" in output and "settled" in output


@pytest.mark.asyncio
async def test_compositor_full_frames_and_metadata_at_owner_size():
    async with WalletApp(snapshot()).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        for view in ("overview", "detail"):
            body.show_view(view)
            await pilot.pause()
            viewport = body.query_one("#wallet-viewport")
            assert viewport.max_scroll_x == 0
            for card in body.query_one(f"#wallet-{view}").query(NewsHeroCard):
                lines = painted(pilot.app, card).splitlines()
                assert len(lines) == 9
                assert "╭" in lines[0] and "╮" in lines[0]
                assert "╰" in lines[-1] and "╯" in lines[-1]
            assert "Orders 30D" in painted(pilot.app)
            assert "Coverage:" in painted(pilot.app)
            assert body.query_one(f"#wallet-{view}-assets", DataTable).region.bottom < 44


@pytest.mark.asyncio
async def test_receipt_and_rule_evidence_remain_clickable_in_detail():
    from tests.widgets.address_probe import link_targets
    data = snapshot()
    tx = "0x" + "b" * 64
    data["artifacts"][1]["usage"].update(latest=tx, evidence="https://example.org/verified-rule", through_timestamp=NOW-30)
    data["artifacts"][1]["deployment"] = dict(tx_hash=tx, confirmed=True, block_number=9, linkage="direct creation receipt")
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        body.selected_id = "registry"
        body.show_view("detail")
        await pilot.pause()
        assert "direct creation receipt" in painted(pilot.app)
        assert any(item[4] == tx and item[5] == f"https://basescan.org/tx/{tx}" for item in link_targets(pilot.app))
        assert "https://example.org/verified-rule" in body.source_links


@pytest.mark.asyncio
async def test_partial_payment_is_a_lower_bound_on_both_hero_views():
    data = snapshot()
    data["orders"][0]["payments"] = None
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        requests = body.query_one("#hero-wallet-overview-requests", NewsHeroCard)
        assert "paid >=10.0 IMD" in painted(pilot.app, requests)
        assert ">=10.0" in painted(pilot.app, body.query_one("#wallet-payments"))
        body.show_view("detail")
        await pilot.pause()
        requests = body.query_one("#hero-wallet-detail-requests", NewsHeroCard)
        paid = body.query_one("#hero-wallet-detail-paid", NewsHeroCard)
        assert "paid >=10.0 IMD" in painted(pilot.app, requests)
        assert "at least" in painted(pilot.app, paid)
        assert paid._display_record.digits == "10.0"


@pytest.mark.asyncio
async def test_saved_selection_survives_unread_mount_until_artifacts_are_observed():
    view_state = dict(view="detail", selected_id="token")
    async with WalletApp(view_state=view_state).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        assert body.selected_id == view_state["selected_id"] == "token"
        body.update_data(wallet_snapshot=snapshot())
        await pilot.pause()
        table = body.query_one("#wallet-detail-assets", DataTable)
        assert body.selected_id == "token"
        assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == "token"
        assert "Credits" in painted(pilot.app, body.query_one("#wallet-selected"))
        empty = snapshot()
        empty["artifacts"] = []
        body.update_data(wallet_snapshot=empty)
        await pilot.pause()
        assert body.selected_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("size, scroll_x, scroll_y", [
    ((144, 45), True, True), ((145, 45), False, False), ((146, 45), False, False),
    ((145, 44), True, True), ((146, 44), False, True), ((145, 46), False, False),
])
async def test_layout_boundary_matches_whole_viewport(size, scroll_x, scroll_y):
    async with WalletApp(snapshot()).run_test(size=size) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        for view in ("overview", "detail"):
            body.show_view(view)
            await pilot.pause()
            viewport = body.query_one("#wallet-viewport")
            assert (viewport.max_scroll_x > 0) is scroll_x
            assert (viewport.max_scroll_y > 0) is scroll_y
            output = painted(pilot.app)
            assert "Coverage:" in output and "Usage 24H" in output
            assert "Esc overview" in output
            if not scroll_x and not scroll_y:
                for card in body.query_one(f"#wallet-{view}").query(NewsHeroCard):
                    lines = painted(pilot.app, card).splitlines()
                    assert len(lines) == 9
                    assert "╭" in lines[0] and "╮" in lines[0]
                    assert "╰" in lines[-1] and "╯" in lines[-1]


@pytest.mark.asyncio
async def test_record_object_keeps_copy_icon_without_guessing_payment_chain():
    from rich.cells import cell_len
    from tests.widgets.address_probe import icon_targets, link_targets
    data = snapshot()
    object_address = "0x4444444444444444444444444444444444444444"
    data["orders"][0]["name"] = object_address + " reviewed"
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        table = body.query_one("#wallet-orders", DataTable)
        cell = table.get_row("request-0")[2]
        assert cell_len(cell.plain) <= 20
        assert "⧉" in painted(pilot.app, table)
        assert any(value == object_address for _, _, value in icon_targets(pilot.app))
        assert not any(value == object_address for _, _, _, _, value, _ in link_targets(pilot.app))


@pytest.mark.asyncio
async def test_onchain_title_uses_usage_clock_when_api_snapshot_advances():
    data = snapshot()
    usage_observed_at = NOW - 3600
    data["sources"]["usage"] = dict(state="ok", observed_at=usage_observed_at, complete=True)
    data["artifacts"][1]["usage"]["observed_at"] = usage_observed_at
    async with WalletApp(data).run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(WalletBody)
        await pilot.pause()
        title = body.query_one("#wallet-onchain .panel-title", Static)
        assert "ONCHAIN USE / 24H · 11:00Z" in painted(pilot.app, title)
        data["as_of"] = NOW + 7200
        data["sources"]["usage"]["state"] = "unavailable"
        data["artifacts"][1]["usage_state"] = "unavailable"
        body.update_data(wallet_snapshot=data)
        await pilot.pause()
        assert "ONCHAIN USE / 24H · 11:00Z" in painted(pilot.app, title)
        assert "14:00" not in painted(pilot.app, title)
        data["sources"]["usage"]["observed_at"] = None
        body.update_data(wallet_snapshot=data)
        await pilot.pause()
        assert painted(pilot.app, title).strip() == "ONCHAIN USE / 24H"
