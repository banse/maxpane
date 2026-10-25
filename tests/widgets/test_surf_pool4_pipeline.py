"""Composited POOL4 stages keep hook allocation distinct from Base proof."""
from copy import deepcopy

import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.pool4u_burn import SurfPool4UBurn
from maxpane_dashboard.widgets.surf.pool4_split import SurfPool4Split
from tests.widgets.surf_compositing import composite_lines


def pipeline(state="ok"):
    payload = {
        "identity": {"network": "MAINNET"},
        "queue": {"state": "ok", "read_ts": 1792796400, "block": 26266580,
                  "amount_wei": 2994623, "decimals": 5},
        "bridge": {"state": "ok", "read_ts": 1792796460, "from_block": 26216000,
                   "to_block": 26266580, "complete": True,
                   "event": {"amount_wei": 159563587, "decimals": 6,
                             "timestamp": 1792790000, "block": 26257982}},
        "base_burn": {"state": "ok", "read_ts": 1792796520,
                      "from_block": 37000000, "to_block": 37302400, "complete": True,
                      "event": {"amount_wei": 8405, "decimals": 2,
                                "timestamp": 1792790100, "block": 37302000}},
    }
    if state == "wide":
        payload["queue"].update(amount_wei=2**256 - 1, decimals=0)
    for key in ("bridge", "base_burn"):
        if state == "empty":
            payload[key]["event"] = None
        elif state == "partial":
            payload[key].update(state="partial", complete=False)
        elif state == "wide":
            payload[key]["event"].update(amount_wei=2**256 - 1, decimals=0)
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize("widget", [SurfPool4UBurn, SurfPool4Split])
async def test_pipeline_stages_keep_their_amounts_and_scope(widget):
    rows = await composite_lines(widget, (72, 40), pool4_network="MAINNET",
                                 pool4_total_burned=35135.94,
                                 pool4_burn_pipeline=pipeline())
    output = "\n".join(rows)
    for label, value in (("queued", "29.95 IMD"), ("last bridge", "159.56 IMD"),
                         ("Base burned", "84.05 IMD")):
        assert any(label in row and value in row for row in rows), output
    assert "executor-wide" in output
    assert "settled" in output
    assert "burned 35" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("widget", [SurfPool4UBurn, SurfPool4Split])
async def test_zero_empty_and_unknown_pipeline_values_are_distinct(widget):
    data = pipeline()
    data["queue"]["amount_wei"] = 0
    data["bridge"]["event"] = None
    data["base_burn"] = None
    rows = await composite_lines(widget, (60, 40), pool4_network="MAINNET",
                                 pool4_burn_pipeline=data)
    assert any("queued" in row and "0.00 IMD" in row for row in rows)
    assert any("last bridge" in row and "none in window" in row for row in rows)
    assert any("Base burned" in row and "—" in row for row in rows)


@pytest.mark.asyncio
async def test_partial_event_does_not_claim_to_be_latest_and_sources_have_own_clocks():
    data = deepcopy(pipeline())
    data["bridge"].update(complete=False, state="partial")

    class Harness(App):
        def compose(self):
            yield SurfPool4UBurn()

    async with Harness().run_test(size=(60, 20)) as pilot:
        widget = pilot.app.query_one(SurfPool4UBurn)
        widget.update_data(pool4_burn_pipeline=data)
        await pilot.pause()
        output = "\n".join(strip.text for strip in pilot.app.screen._compositor.render_strips())
        assert "bridge seen" in output and "last bridge" not in output
        detail = str(widget.tooltip)
        assert all(clock in detail for clock in ("23:00", "23:01", "23:02")), detail
        assert "26216000" in detail and "26266580" in detail
        assert "incomplete" in detail
        assert "successful Base receipt" in detail
        assert "multiple sources" in detail


@pytest.mark.asyncio
async def test_hook_share_names_ethereum_supply():
    output = "\n".join(await composite_lines(
        SurfPool4UBurn, (60, 20), pool4_total_burned=35135.94,
        pool4_burned_supply_pct=.84, pool4_total_supply=4165864.94))
    assert "settled" in output and "0.84% of ETH supply" in output
    assert "ETH supply" in output


@pytest.mark.asyncio
@pytest.mark.parametrize("amount, decimals, expected", [(1, 18, "<0.01 IMD"), (True, 18, "—"), (1, None, "—")])
async def test_queue_never_rounds_positive_dust_or_unread_decimals_into_zero(amount, decimals, expected):
    data = pipeline()
    data["queue"].update(amount_wei=amount, decimals=decimals)
    rows = await composite_lines(SurfPool4UBurn, (60, 20), pool4_burn_pipeline=data)
    assert any("queued" in row and expected in row for row in rows)
