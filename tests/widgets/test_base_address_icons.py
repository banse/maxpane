"""Copy icons on every 0x address the base widgets render.

PRD: ``docs/address_copy_PRD.md`` (the 2026-09-14 address-copy-icons build,
task 5; its briefs were archived with the rest of ``.superpowers/``,
``HANDOVER.md`` §1.2).

After the dead-base-code refactor (``docs/refactor_programme_2026_09.md``
Branch 1), the only base widget left with a live import path is
``overview/bt_overview_leaderboard.py`` -- the leaderboard actually wired to
``screens/base_terminal.py``. The eight other candidate modules covered here
previously (``graduated``, ``launch_feed``, ``top_movers``, ``trending_table``,
``fee_claims``, the shadowed top-level ``overview.py``,
``overview/_legacy_overview.py`` and ``overview/bt_leaderboard.py``) were
unreachable dead code and were deleted along with their tests in that
refactor.
"""

from __future__ import annotations

from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4
#: A second, distinct address -- used wherever a test must prove a click
#: copies *that row's own* address rather than a neighbour's.
ADDR2 = "0x" + "fedcba9876" * 4


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


# ---------------------------------------------------------------------------
# bt_overview_leaderboard.py: the one live widget in this package.
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


async def test_bt_overview_leaderboard_clicking_the_icon_copies_that_rows_address():
    """The one live widget in this package: prove the click actually fires.

    ``icon_targets`` only proves an icon carries the right ``@click`` meta at
    a composited coordinate; it never dispatches a real click. Two rows with
    two different addresses so a click that copied the wrong (neighbour's)
    row's address would fail this -- not just "no icon", a *specific* wrong
    icon.
    """
    from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import (
        BTOverviewLeaderboard,
    )

    app = _WidgetApp(
        BTOverviewLeaderboard(),
        {"trending_tokens": [
            _base_token(ADDR, symbol="LIVE1"),
            _base_token(ADDR2, symbol="LIVE2"),
        ]},
    )
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        target = next(t for t in icon_targets(app) if t[2] == ADDR2)
        await pilot.click(offset=(target[0], target[1]))
        await pilot.pause()
        assert app.copied == [ADDR2]
