"""Regression tests for HIGH-7: hostile third-party names must not crash the app.

Textual's ``DataTable.add_row`` stores cell values verbatim and defers
``Text.from_markup`` to ``_on_idle -> _update_dimensions ->
default_cell_formatter``. A test that merely calls ``update_data()`` and
asserts "no exception" therefore passes *while the bug is still present* --
the ``MarkupError`` fires later, inside the message pump, where the screen's
``try/except`` cannot see it and the whole app dies.

Every test here consequently mounts the real widget in a real ``App`` and
pumps at least one idle cycle via ``pilot.pause()`` so the deferred formatter
actually runs. ``test_harness_detects_unescaped_markup`` is the control: it
proves this harness really does surface the crash, so the tests below are
meaningful rather than vacuous.
"""

from __future__ import annotations

import pytest
from rich.errors import MarkupError
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from maxpane_dashboard.data.models import ActivityEvent, BakerySummary
from maxpane_dashboard.templates.leaderboard_template import GameLeaderboard
from maxpane_dashboard.widgets.leaderboard import Leaderboard
from maxpane_dashboard.widgets.markup_safety import safe_markup

# Names a griefer can set on a public leaderboard. Each is malformed Rich
# markup in a different way; every one of them raises MarkupError if it
# reaches Text.from_markup unescaped.
HOSTILE_NAMES = [
    "[/x] Bakers",  # closing tag matching no open tag (the reported case)
    "[/]",  # bare close with nothing open
    "[/bold] Crew",  # close of a tag that was never opened
    "[bold] Unclosed",  # valid-but-unclosed: no error, but leaks styling
    "[not a tag] Guild",  # bracketed text that is not a real tag
    "[#00ff00 on]",  # malformed style definition
]


class _Harness(App):
    """Mount a single widget so ``update_data`` can be driven headlessly."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _bakery(idx: int, name: str) -> BakerySummary:
    return BakerySummary(
        id=idx,
        name=name,
        creator="0x" + "1" * 40,
        leader="0x" + "2" * 40,
        top_cook=None,
        member_count=3,
        active_cook_count=2,
        season_id=1,
        created_at="1700000000",
        tx_count=str(10_000_000 - idx),
        raw_tx_count=str(10_000_000 - idx),
        buffs=0,
        debuffs=0,
        active_buffs=(),
        active_debuffs=(),
    )


# -- control: prove the harness can see the crash ----------------------


@pytest.mark.parametrize("hostile", ["[/x] Bakers", "[/]", "[/bold] Crew"])
async def test_harness_detects_unescaped_markup(hostile: str) -> None:
    """An unescaped hostile value must still blow up through this harness.

    This is what makes the rest of the file trustworthy. If Textual ever
    stops deferring markup parsing to idle, this test fails and tells us the
    other tests here have quietly become vacuous.
    """

    class _Raw(App):
        def compose(self) -> ComposeResult:
            yield DataTable(id="t")

        def on_mount(self) -> None:
            table = self.query_one("#t", DataTable)
            table.add_column("Name")
            table.add_row(hostile)  # deliberately unescaped

    with pytest.raises(MarkupError):
        async with _Raw().run_test() as pilot:
            await pilot.pause()


# -- the fix: Leaderboard (widgets/leaderboard.py) ---------------------


async def test_leaderboard_survives_hostile_leader_name() -> None:
    """The reported crash: hostile name in the bold-highlighted leader row."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([_bakery(1, "[/x] Bakers")], {}, 1000.0)
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == 1
        # Rendered literally, not swallowed as a markup tag.
        rendered = table.get_row_at(0)[1]
        assert "[/x] Bakers" in str(rendered)


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_leaderboard_survives_hostile_names_every_row(hostile: str) -> None:
    """Hostile names crash in the leader row *and* in the plain rows."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        # Same hostile name in row 1 (markup-wrapped) and row 2 (raw).
        widget.update_data(
            [_bakery(1, hostile), _bakery(2, hostile)],
            {},
            1000.0,
        )
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == 2


async def test_leaderboard_survives_repeated_refreshes() -> None:
    """The real failure recurs on every refresh, so re-render repeatedly."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        for _ in range(3):
            widget.update_data(
                [_bakery(i, name) for i, name in enumerate(HOSTILE_NAMES, start=1)],
                {},
                1000.0,
            )
            await pilot.pause()
            await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == len(HOSTILE_NAMES)


async def test_leaderboard_keeps_leader_bold_styling() -> None:
    """Escaping must not destroy the intended bold markup on the leader row."""
    widget = Leaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([_bakery(1, "Normal Name")], {}, 1000.0)
        await pilot.pause()

        table = widget.query_one("#leaderboard-table", DataTable)
        assert str(table.get_row_at(0)[1]) == "[bold]Normal Name[/]"


# -- the template new dashboards are copied from ----------------------


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_template_leaderboard_survives_hostile_entries(hostile: str) -> None:
    """templates/leaderboard_template.py must not teach the bug to new code."""
    widget = GameLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"name": hostile, "score": 1234, "detail": hostile, "status": hostile},
                {"name": hostile, "score": 12, "detail": hostile, "status": hostile},
            ]
        )
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#game-leaderboard-table", DataTable)
        assert table.row_count == 2


async def test_template_leaderboard_survives_hostile_address_fallback() -> None:
    """The name falls back to the address, which is API-sourced too."""
    widget = GameLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data([{"name": "", "address": "[/x]", "score": 1}])
        await pilot.pause()
        await pilot.pause()

        table = widget.query_one("#game-leaderboard-table", DataTable)
        assert table.row_count == 1


# -- the helper itself -------------------------------------------------


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
def test_safe_markup_output_parses_as_markup(hostile: str) -> None:
    """Escaped output must round-trip through from_markup to the original."""
    from rich.text import Text

    assert Text.from_markup(safe_markup(hostile)).plain == hostile


def test_safe_markup_handles_none_and_non_strings() -> None:
    assert safe_markup(None) == ""
    assert safe_markup(42) == "42"
    assert safe_markup("plain") == "plain"


# -- the rest of the fleet ---------------------------------------------
#
# The same crash exists wherever another party's text reaches a DataTable or
# a markup string: token symbols (anyone can deploy an ERC-20 called "[/x]"),
# NFT collection names, pet names, player handles. These drive each widget
# through a real mount + idle cycle with hostile values in every row, so the
# non-leader ("bare cell") branches are exercised too -- those are just as
# fatal as the bold ones, because DataTable markup-parses any cell containing
# a "[".


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_dota_leaderboard_survives_hostile_handles(hostile: str) -> None:
    from maxpane_dashboard.widgets.dota.dota_leaderboard import DOTALeaderboard

    widget = DOTALeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"rank": r, "name": hostile, "wins": 1, "games": 2,
                 "win_rate": 50.0, "player_type": hostile}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#dota-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_ttt_leaderboard_survives_hostile_symbols(hostile: str) -> None:
    """Anyone can deploy a token whose symbol is malformed markup."""
    from maxpane_dashboard.widgets.ttt.ttt_leaderboard import TTTLeaderboard

    widget = TTTLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            top_tokens_by_volume=[
                {"rank": r, "symbol": hostile, "price_usd": 1.0,
                 "change_h24": 1.0, "vol_usd_h24": 1.0, "age_str": "1d",
                 "mcap_usd": 1.0}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#ttt-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_cattown_leaderboard_survives_hostile_basenames(hostile: str) -> None:
    from maxpane_dashboard.widgets.cattown.ct_leaderboard import CTLeaderboard

    widget = CTLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"rank": r, "display_name": hostile, "fish_species": hostile,
                 "fish_weight_kg": 1.0, "rarity": "Common"}
                for r in (1, 2, 3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#ct-leaderboard-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_base_leaderboard_survives_hostile_symbols(hostile: str) -> None:
    from maxpane_dashboard.widgets.base.overview.bt_leaderboard import (
        BTOverviewLeaderboard,
    )

    widget = BTOverviewLeaderboard()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                {"symbol": hostile, "price_usd": 1.0, "price_change_24h": 1.0,
                 "volume_24h": 100.0, "liquidity_usd": 100.0}
                for _ in range(3)
            ]
        )
        await pilot.pause()
        await pilot.pause()
        assert widget.query_one("#bto-lb-table", DataTable).row_count == 3


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
async def test_bakery_activity_feed_survives_hostile_event_text(hostile: str) -> None:
    """RichLog(markup=True) defers rendering to on_resize -- same crash class."""
    from maxpane_dashboard.widgets.activity_feed import ActivityFeed

    widget = ActivityFeed()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            [
                ActivityEvent(
                    type="rug",
                    title=hostile,
                    description=hostile,
                    launcher="0x" + "1" * 40,
                    timestamp="1700000000",
                    boost_type_name=None,
                    boost_multiplier_bps=None,
                    boost_duration=None,
                    is_shield=None,
                    is_outgoing=True,
                    success=True,
                    linked_bakery_id=None,
                    linked_bakery_name=hostile,
                )
            ]
        )
        await pilot.pause()
        await pilot.pause()


async def test_cookie_chart_survives_hostile_bakery_names() -> None:
    from maxpane_dashboard.widgets.cookie_chart import CookieChart

    widget = CookieChart()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data({name: [(0, 1.0), (1, 2.0)] for name in HOSTILE_NAMES})
        await pilot.pause()
        await pilot.pause()


async def test_hero_metrics_survives_hostile_leader_name() -> None:
    from maxpane_dashboard.widgets.hero_metrics import HeroMetrics

    widget = HeroMetrics()
    async with _Harness(widget).run_test() as pilot:
        widget.update_data(
            prize_pool_eth=1.0,
            prize_pool_usd=1000.0,
            hours_remaining=48.0,
            season_id=1,
            season_active=True,
            leader_name="[/x] Bakers",
            leader_cookies=1000.0,
            leader_rate=1.0,
        )
        await pilot.pause()
        await pilot.pause()
