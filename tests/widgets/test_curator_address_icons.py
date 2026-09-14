"""Copy icons on every 0x address the curator widgets render (Task 3).

PRD: ``docs/address_copy_PRD.md``. Task 3 brief:
``.superpowers/sdd/2026-09-14-address-copy-icons/task-3-brief.md``.

Widget-level tests (each widget constructed directly and driven through
``update_data``), matching the precedent Tasks 5-8 already established
rather than the dispatch template's full-screen sketch -- see
``task-3-report.md`` for why: curator's own screen test module names two
classes ending in "Harness", the default (dashboard) body needs an ``h``
keypress to even reach three of these five widgets (the screen opens on
Raw Lists), and two of the four bodies the template's own sketch exercises
(wallet, analysis) hold nothing this task converts. None of that machinery
is needed here: every widget below takes its payload straight through
``update_data``, exactly like Tasks 5/7's own address-icon tests.

Five sites confirmed (recipe step 1), all named in the brief:

- ``activity.py``: the deposit feed's identity cell (``short_label`` over
  ``address``/``name``).
- ``closest_calls.py``: the SAVIOR cell (``short_label`` over
  ``savior``/``savior_name``).
- ``leaderboard.py``: the WALLET cell (``short_label`` over
  ``address``/``name``).
- ``list_hero.py``: the wallet card's address line (the full, unshortened
  address, PRD's "address stays visible even when ENS exists").
- ``signals.py``: HOUR SAVED's and WHALE's identity part -- the only two of
  the rail's seven rows that ever carry a wallet.

Curator's other widgets that also render addresses --
``wallet.py``/``cleaned_list.py``/``operators.py``/``segments.py``/
``clusters.py``/``lists.py`` -- are out of Task 3's scope (not named in the
brief's file list) and untouched here; ``widgets/curator/list_filter.py:201``
is a dict key, not a display, and is explicitly left alone.
"""

from __future__ import annotations

import importlib
import inspect

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["activity", "closest_calls", "leaderboard", "list_hero", "signals"]


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
    assert classes, f"{mod.__name__} defines no widget with update_data"
    return classes[0]


#: name -> update_data kwargs carrying ADDR, built from each widget's real
#: row shape (``CURATOR_ROW_KEYS`` / each module's own ``update_data``
#: signature, read off the source rather than guessed).
SEEDED: dict[str, dict] = {
    "activity": dict(activity_rows=[{
        "kind": "deposit", "ts": 1_700_000_000, "address": ADDR, "name": None,
        "amount_eth": 3.6, "credited_eth": 2.8, "new_weight": 7.03,
        "tx_count": 1, "tx_hash": "0x" + "ab" * 32, "log_index": 1,
    }]),
    "closest_calls": dict(closest_call_rows=[{
        "hour": 1, "volume_eth": 5.0, "margin_eth": 0.5,
        "savior": ADDR, "savior_name": None,
    }]),
    "leaderboard": dict(leaderboard_rows=[{
        "rank": 1, "address": ADDR, "name": None, "points": 100,
        "credit_eth": 1.0, "tx_count": 1, "link_conf": None, "flagged": None,
    }]),
    "list_hero": dict(
        you_address=ADDR, you_ens=None, list_view="raw",
        you_rank=1, contributors_total=10,
        you_points=10, you_credit_eth=1.0,
    ),
    "signals": dict(
        whale_wallet=ADDR, whale_ens=None, whale_amount_eth=1.0, whale_age_s=60,
    ),
}


@pytest.mark.parametrize("name", CASES)
async def test_each_curator_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.curator.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}, (name, targets)


@pytest.mark.parametrize("name", CASES)
async def test_clicking_the_icon_copies_exactly_that_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.curator.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        target = next(t for t in icon_targets(app) if t[2] == ADDR)
        await pilot.click(offset=(target[0], target[1]))
        await pilot.pause()
        assert app.copied == [ADDR], name


async def test_leaderboard_lower_cases_a_checksummed_address():
    """Two sources spell one wallet two ways (``eth_call`` checksums it, a
    log topic decodes lowercase); the icon must copy one spelling so "this
    row is you" (a case-insensitive compare) is never contradicted by what
    the clipboard actually holds."""
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.leaderboard")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(leaderboard_rows=[{
        "rank": 1, "address": checksummed, "name": None, "points": 100,
        "credit_eth": 1.0, "tx_count": 1, "link_conf": None, "flagged": None,
    }]))
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert targets, "no copy icon on the leaderboard"
        addresses = {t[2] for t in targets}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_list_hero_wallet_card_shows_the_verified_ens_name_and_still_copies_the_address():
    """PRD §13 A9 / the record-list hero contract: the icon goes on the
    address, and a verified ENS name still stands in as the shown text."""
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.list_hero")
    app = _WidgetApp(_widget_class(mod)(), dict(
        you_address=ADDR, you_ens="reader.eth", list_view="raw",
        you_rank=1, contributors_total=10, you_points=10, you_credit_eth=1.0,
    ))
    async with app.run_test(size=(150, 12)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}
        strips = app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "reader.eth" in text
