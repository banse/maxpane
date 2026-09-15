"""Every cattown and talismans site that shows an address carries the copy icon.

Names stand in for addresses in three cattown sites (``ct_activity_feed``,
``ct_hero_metrics``, ``ct_leaderboard``): the icon still copies the address
behind the name. ``tal_leaderboard`` shows the address directly.
"""

from __future__ import annotations

import importlib
import inspect
import time

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["cattown.ct_activity_feed", "cattown.ct_hero_metrics", "cattown.ct_leaderboard",
         "talismans.tal_leaderboard"]


class _WidgetApp(CopyRecorder, App):
    """``themes/minimal.tcss`` gives ``CTHeroBox`` its ``width: 1fr``; without
    it the first hero box takes the whole row and the LEADER box never
    reaches the compositor (the ``test_hero_metrics_degradation.py``
    precedent for this exact gap). Scoped to ``CTHeroBox`` so it is inert for
    the other three cases, which carry their own layout CSS.
    """

    CSS = """
    CTHeroBox {
        width: 1fr;
        height: 7;
        padding: 1 2;
        text-align: center;
    }
    """

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
@pytest.mark.parametrize("with_name", [False, True], ids=["address", "named"])
async def test_the_icon_appears_with_or_without_a_display_name(name, with_name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.{name}")
    payload = SEEDED[name](with_name)
    app = _WidgetApp(_widget_class(mod)(), payload)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}, (name, with_name)


async def test_clicking_the_icon_copies_the_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.cattown.ct_leaderboard")
    payload = SEEDED["cattown.ct_leaderboard"](False)
    app = _WidgetApp(_widget_class(mod)(), payload)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        target = next(t for t in icon_targets(app) if t[2] == ADDR)
        await pilot.click(offset=(target[0], target[1]))
        await pilot.pause()
        assert ADDR in app.copied


def _ct_activity_feed(with_name: bool) -> dict:
    catch = {
        "tx_hash": "0xtx1",
        "timestamp": int(time.time()),
        "fisher_address": ADDR,
        "species": "Salmon",
        "weight_kg": 1.2,
        "rarity": "Common",
    }
    if with_name:
        catch["display_name"] = "whiskers"
    return {"recent_catches": [catch]}


def _ct_hero_metrics(with_name: bool) -> dict:
    top_fisher = {"address": ADDR, "weight_kg": 3.4}
    if with_name:
        top_fisher["display_name"] = "whiskers"
    return {"top_fisher": top_fisher}


def _ct_leaderboard(with_name: bool) -> dict:
    entry = {
        "rank": 1,
        "fisher_address": ADDR,
        "fish_species": "Salmon",
        "fish_weight_kg": 2.0,
        "rarity": "Common",
    }
    if with_name:
        entry["display_name"] = "whiskers"
    return {"competition_entries": [entry]}


def _tal_leaderboard(with_name: bool) -> dict:
    # talismans' leaderboard row has no display-name field; both parametrized
    # cases render the same address-only payload.
    return {"top_collectors": [{"rank": 1, "address": ADDR, "tokens": 10, "cores": 5, "mythics": 1}]}


#: name -> callable(with_name) -> update_data kwargs, with ADDR as the address
#: and, when with_name is True, "whiskers" as the display name. Built from
#: each widget's real update_data keys.
SEEDED: dict = {
    "cattown.ct_activity_feed": _ct_activity_feed,
    "cattown.ct_hero_metrics": _ct_hero_metrics,
    "cattown.ct_leaderboard": _ct_leaderboard,
    "talismans.tal_leaderboard": _tal_leaderboard,
}
