"""Copy icons on every 0x address the base widgets render.

PRD: ``docs/address_copy_PRD.md``. Task 5 brief:
``.superpowers/sdd/2026-09-14-address-copy-icons/task-5-brief.md``.

Base's ten candidate modules split several ways -- see
``task-5-report.md`` for the full reasoning, summarised here:

- ``graduated``, ``launch_feed``, ``top_movers``, ``trending_table``: each
  shows a token's *symbol* as a stand-in for its contract address (PRD §3.2,
  "a name standing in for an address"). Tested generically below via
  ``MODULES``/``SEEDED``.
- ``fee_claims``: shows a transaction hash (``short_hex``, no icon) and a
  fee-claim *symbol*; its payload has no address field anywhere. Confirmed
  false positive for the icon -- dedicated no-icon tests below instead.
- ``fee_leaderboard``: ``entry["token"]`` is the same kind of symbol string
  as ``fee_claims``'s, with no address field in its payload shape either.
  Confirmed false positive, left unmodified; no test needed (nothing changed
  to protect).
- ``overview.py`` (top-level module) and ``overview/_legacy_overview.py``
  are byte-identical duplicates, and ``widgets.base.overview`` as an import
  path resolves to the *package* (``overview/__init__.py``), which shadows
  the standalone ``overview.py`` module completely: it is unreachable by
  ``import maxpane_dashboard.widgets.base.overview`` (a pre-existing defect,
  reported in task-5-report.md, not fixed here). Both files are converted in
  lockstep; each gets its own dedicated test that reaches it directly --
  ``_legacy_overview`` by its real import path, the shadowed ``overview.py``
  by loading it off disk.
- ``overview/bt_leaderboard.py`` and ``overview/bt_overview_leaderboard.py``
  both define an unrelated, identically-named class ``BTOverviewLeaderboard``.
  ``bt_overview_leaderboard.py`` is the one actually wired to the live base
  screen (``screens/base_terminal.py``); ``bt_leaderboard.py`` is reachable
  only from ``tests/widgets/test_markup_safety.py``'s hostile-name test.
  Both get a dedicated test below.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
#: 40 hex chars -- deliberately address-shaped, to prove fee_claims's guard:
#: even a hex value this length gets no icon, because ``short_hex`` never
#: attaches one regardless of the value's shape (it returns ``str``, never a
#: ``Text`` carrying an ``@click`` meta). A realistic 64-hex tx hash would
#: also pass this test, but vacuously -- it fails ``is_address`` on length
#: alone, so it would pass even through a wrongly-wired ``address_text``.
#: This value is the one that actually exercises the guard.
TX_HASH_ADDRESS_SHAPED = "0x" + "cd" * 20
#: A realistic transaction hash length (32 bytes), for the companion test.
TX_HASH_REALISTIC = "0x" + "ab" * 32


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, f"{mod.__name__} defines no widget with update_data"
    return classes[0]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget = widget
        self._payload = payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _base_token(address: str, *, symbol: str = "TOK"):
    from maxpane_dashboard.data.base_models import BaseToken

    return BaseToken(
        address=address,
        name="Token",
        symbol=symbol,
        price_usd=1.23,
        price_change_5m=1.0,
        price_change_1h=2.0,
        price_change_24h=3.0,
        volume_24h=100_000.0,
        market_cap=1_000_000.0,
        fdv=1_000_000.0,
        liquidity=50_000.0,
        pair_address=None,
        dex="aerodrome",
        created_at=1_700_000_000,
    )


def _token_launch(address: str, *, symbol: str = "NEW"):
    from maxpane_dashboard.data.base_models import TokenLaunch

    return TokenLaunch(
        address=address,
        name="Launch",
        symbol=symbol,
        deployer="clanker",
        created_at=1_700_000_000,
        age_seconds=120,
        initial_liquidity=None,
        current_price=1.0,
        price_change_5m=1.0,
        market_cap=1000.0,
        volume_24h=1000.0,
        buy_count=1,
        sell_count=1,
        graduated=False,
    )


def _trending_pool(token_address: str, *, symbol: str = "POOL"):
    from maxpane_dashboard.data.base_models import TrendingPool

    return TrendingPool(
        pool_address="0x" + "11" * 20,
        token_name="Pool Token",
        token_symbol=symbol,
        token_address=token_address,
        price_usd=1.0,
        volume_24h=1000.0,
        price_change_24h=1.0,
    )


def _overview_payload(address: str) -> dict:
    token = _base_token(address, symbol="OVR")
    launch = _token_launch(address, symbol="OVL")
    pool = _trending_pool(address, symbol="POOL")
    return {
        "trending_tokens": [token],
        "launch_stats": {},
        "last_updated_seconds_ago": 1,
        "price_histories": {},
        "volume_leaders": [token],
        "launches": [launch],
        "top_gainers": [token],
        "top_losers": [],
        "trending_pools": [pool],
    }


# ---------------------------------------------------------------------------
# The four widgets confirmed "in scope" per the brief: a token contract
# address behind the symbol label.
# ---------------------------------------------------------------------------

MODULES = ["graduated", "launch_feed", "top_movers", "trending_table"]

SEEDED: dict[str, dict] = {
    "graduated": {
        "graduated": [
            {"symbol": "GRAD", "address": ADDR, "price_usd": 1.0, "price_change_5m": 5.0},
        ],
    },
    "launch_feed": {
        "launches": [
            {
                "timestamp": 1_700_000_000, "symbol": "NEW", "address": ADDR,
                "deployer": "clanker", "price_usd": 1.0, "price_change_5m": 5.0,
                "volume": 1000.0,
            },
        ],
    },
    "top_movers": {"gainers": [_base_token(ADDR, symbol="GAIN")], "losers": []},
    "trending_table": {"tokens": [_base_token(ADDR, symbol="TREND")]},
}


@pytest.mark.parametrize("name", MODULES)
async def test_each_base_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.base.{name}")
    widget_cls = _widget_class(mod)
    payload = SEEDED[name]
    app = _WidgetApp(widget_cls(), payload)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert (ADDR in {t[2] for t in icon_targets(app)}), name


# ---------------------------------------------------------------------------
# fee_claims: transaction hash only. short_hex, never an icon.
# ---------------------------------------------------------------------------


async def test_fee_claims_address_shaped_hash_gets_no_icon():
    from maxpane_dashboard.widgets.base.fee_claims import FeeClaims

    app = _WidgetApp(
        FeeClaims(),
        {"claims": [
            {"timestamp": 1_700_000_000, "token": "PIE", "amount_eth": 0.5,
             "tx_hash": TX_HASH_ADDRESS_SHAPED},
        ]},
    )
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert icon_targets(app) == []


async def test_fee_claims_realistic_hash_length_also_gets_no_icon():
    from maxpane_dashboard.widgets.base.fee_claims import FeeClaims

    app = _WidgetApp(
        FeeClaims(),
        {"claims": [
            {"timestamp": 1_700_000_000, "token": "PIE", "amount_eth": 0.5,
             "tx_hash": TX_HASH_REALISTIC},
        ]},
    )
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert icon_targets(app) == []


# ---------------------------------------------------------------------------
# overview.py (shadowed top-level module) and overview/_legacy_overview.py
# (its reachable duplicate): both converted, each reached directly.
# ---------------------------------------------------------------------------


def _load_shadowed_overview_module():
    """Load the standalone, unreachable ``widgets/base/overview.py``.

    ``import maxpane_dashboard.widgets.base.overview`` resolves to the
    *package* ``overview/__init__.py`` (Python prefers the package over the
    sibling module of the same name), so the plain module can never be
    reached that way. Loaded directly off disk so its conversion is still
    exercised; see task-5-report.md for the defect writeup.
    """
    base_dir = Path(importlib.import_module("maxpane_dashboard.widgets.base").__file__).parent
    spec = importlib.util.spec_from_file_location(
        "maxpane_dashboard.widgets.base._shadowed_overview", base_dir / "overview.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_shadowed_top_level_overview_module_puts_an_icon_on_its_addresses():
    module = _load_shadowed_overview_module()
    widget_cls = _widget_class(module)
    app = _WidgetApp(widget_cls(), {"data": _overview_payload(ADDR)})
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}


async def test_legacy_overview_panel_puts_an_icon_on_its_addresses():
    from maxpane_dashboard.widgets.base.overview._legacy_overview import OverviewPanel

    app = _WidgetApp(OverviewPanel(), {"data": _overview_payload(ADDR)})
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}


# ---------------------------------------------------------------------------
# The two same-named BTOverviewLeaderboard classes.
# ---------------------------------------------------------------------------


async def test_bt_overview_leaderboard_the_live_widget_puts_an_icon_on_the_token():
    from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import (
        BTOverviewLeaderboard,
    )

    app = _WidgetApp(
        BTOverviewLeaderboard(), {"trending_tokens": [_base_token(ADDR, symbol="LIVE")]},
    )
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}


async def test_bt_leaderboard_dead_duplicate_puts_an_icon_on_the_token():
    from maxpane_dashboard.widgets.base.overview.bt_leaderboard import BTOverviewLeaderboard

    app = _WidgetApp(BTOverviewLeaderboard(), {"tokens": [_base_token(ADDR, symbol="DUP")]})
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}
