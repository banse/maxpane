"""Every TTT site that shows an address carries the copy icon.

``ttt_activity_feed`` shows the burn actor's address (previously sliced to
its first 6 hex characters with no icon); ``ttt_fees_table`` and
``ttt_leaderboard`` show the token symbol standing in for its ERC20 contract
address -- the icon copies the address behind the symbol, same as a
name-backed row elsewhere in the app.

``ttt_claims_table`` is a confirmed false positive (recipe step 1): its rows
are pure per-NFT burn-scenario math (``scenario``, ``unburned``,
``share_pct``, ``projected_24h_eth``) with no address, token or wallet field
anywhere in ``analytics.ttt_signals.claim_math_scenarios``. It is left out of
``CASES`` and untouched; see ``task-7-report.md`` for the full read.
"""

from __future__ import annotations

import importlib
import inspect
import time

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["ttt_activity_feed", "ttt_fees_table", "ttt_leaderboard"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, mod.__name__
    return classes[0]


@pytest.mark.parametrize("name", CASES)
async def test_each_ttt_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.ttt.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}, name
        x, y, _ = next(t for t in targets if t[2] == ADDR)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]


#: name -> update_data kwargs carrying ADDR, built from that widget's real
#: update_data keys (ttt_manager.fetch_and_compute's payload shape).
SEEDED: dict[str, dict] = {
    "ttt_activity_feed": {
        "activity_events": [
            {
                "event_type": "burn",
                "timestamp": int(time.time()),
                "token_symbol": "TTT1",
                "actor_address": ADDR,
                "token_id": 42,
            },
        ],
    },
    "ttt_fees_table": {
        "top_fee_engines": [
            {
                "rank": 1,
                "address": ADDR,
                "symbol": "TTT1",
                "fees_24h_eth": 0.5,
                "fees_lifetime_eth": 2.0,
                "fees_per_vol_pct": 1.2,
            },
        ],
    },
    "ttt_leaderboard": {
        "top_tokens_by_volume": [
            {
                "rank": 1,
                "address": ADDR,
                "symbol": "TTT1",
                "price_usd": 0.01,
                "change_h24": 5.0,
                "vol_usd_h24": 1000.0,
                "age_str": "2d",
                "mcap_usd": 5000.0,
            },
        ],
    },
}
