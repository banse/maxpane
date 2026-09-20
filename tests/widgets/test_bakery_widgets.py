"""Composited pins for the six top-level bakery widgets (Branch 8 WP-B).

Every assertion here is on **composited output** (``render_strips()``),
never on a content string, and every test names the mutation it exists to
redden. The six widgets -- ``hero_metrics``, ``leaderboard``,
``cookie_chart``, ``signals_panel``, ``activity_feed``, ``ev_table`` -- were
the original 2025 copies every later dashboard was seeded from; the three
degradation files beside this one (``test_hero_metrics_degradation.py``,
``test_activity_feed_degradation.py``, ``test_ev_table_catalog_source.py``)
pin *behaviour under bad input* and are unchanged. This file pins the
*geometry and the constants* the move onto ``widgets/panels.py`` introduces
(column widths, the 30-cell bar, the 20/12/10 signal cells, the label and
row caps) so that a mutation to any of them reddens something.

The one non-composited assertion is the leaderboard's fifth column width:
the last column's width moves nothing to its right, so it is read off the
``DataTable`` directly, beside the composited pin of the other four.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.models import ActivityEvent, BakerySummary
from maxpane_dashboard.widgets.activity_feed import ActivityFeed
from maxpane_dashboard.widgets.cookie_chart import CookieChart
from maxpane_dashboard.widgets.ev_table import EVTable
from maxpane_dashboard.widgets.hero_metrics import HeroMetrics
from maxpane_dashboard.widgets.leaderboard import Leaderboard
from maxpane_dashboard.widgets.signals_panel import SignalsPanel
from maxpane_dashboard.widgets.sparkline_common import SPARK_CHARS

from tests.widgets.surf_compositing import composite_lines

REPO = Path(__file__).resolve().parents[2]
STYLESHEET = REPO / "maxpane_dashboard" / "themes" / "minimal.tcss"

#: What the compositor reports for a ``[yellow]``/``[green]``/``[red]`` span in
#: a ``Static`` under the app stylesheet (measured; Textual resolves the
#: markup names itself, so Rich's own ``Style.parse`` triplets do not apply).
YELLOW = (255, 255, 0)
GREEN = (0, 128, 0)
RED = (255, 0, 0)
#: A ``RichLog`` row's ``Text`` styles go through the app's ANSI theme
#: instead, so the same two names land on different triplets there.
FEED_GREEN = (152, 224, 36)
FEED_RED = (244, 0, 95)


class _Harness(App):
    """Mount a single widget under the app stylesheet so polls can be replayed."""

    CSS_PATH = CSS_PATH

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


_PIN_SIZE = (120, 30)


def _strips(app) -> list[str]:
    return [
        "".join(seg.text for seg in strip).rstrip()
        for strip in app.screen._compositor.render_strips()
    ]


async def _composited(cls, **payload) -> list[str]:
    """The widget's own rows after one poll, under ``minimal.tcss``."""
    return await composite_lines(
        cls, _PIN_SIZE, css_path=CSS_PATH, region_only=True, **payload
    )


def _line_with(lines: list[str], needle: str) -> str:
    matches = [line for line in lines if needle in line]
    assert len(matches) == 1, f"{needle!r} in {matches!r} of {lines!r}"
    return matches[0]


def _colour_of(app, needle: str) -> tuple[int, int, int] | None:
    """The truecolor of the first segment whose text carries *needle*."""
    for strip in app.screen._compositor.render_strips():
        for seg in strip:
            if needle in seg.text and seg.style is not None and seg.style.color:
                return seg.style.color.get_truecolor()
    return None


def _bold_of(app, needle: str) -> bool | None:
    for strip in app.screen._compositor.render_strips():
        for seg in strip:
            if needle in seg.text and seg.style is not None:
                return bool(seg.style.bold)
    return None


def _bakery(i: int, name: str, tx_count: str) -> BakerySummary:
    return BakerySummary(
        id=i, name=name, creator="0x" + "11" * 20, leader="0x" + "22" * 20,
        top_cook=None, member_count=3, active_cook_count=2, season_id=3,
        created_at="0", tx_count=tx_count, raw_tx_count=tx_count, buffs=0,
        debuffs=0, active_buffs=(), active_debuffs=(),
    )


def _event(**overrides) -> ActivityEvent:
    fields = dict(
        type="simple",
        title="joined the bakery",
        description="",
        launcher="0x" + "1" * 40,
        timestamp="1700000000",
        boost_type_name=None,
        boost_multiplier_bps=None,
        success=None,
        is_outgoing=None,
        linked_bakery_name=None,
    )
    fields.update(overrides)
    return ActivityEvent.model_construct(**fields)


#: The full hero argument set, all present and well-formed.
_HERO = dict(
    prize_pool_eth=12.5,
    prize_pool_usd=41_000.0,
    hours_remaining=71.5,
    season_id=4,
    season_active=True,
    leader_name="Crumb Cartel",
    leader_cookies=139_300.0,
    leader_rate=5_800.0,
)

_HERO_SIZE = (220, 24)


class _HeroHarness(App):
    """Mount ``HeroMetrics`` without the stylesheet's box border.

    ``minimal.tcss`` gives ``HeroBox`` ``height: 7`` **and** a border, which
    leaves three inner rows: label, blank, value -- the sub-line (USD, season,
    name and rate) is clipped in production and would be invisible to every
    pin below. The same geometry minus the border is what
    ``test_hero_metrics_degradation.py`` mounts, and it shows all four rows.
    """

    CSS = """
    HeroBox {
        width: 1fr;
        height: 7;
        padding: 1 2;
        text-align: center;
    }
    """

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


# -- HeroMetrics --------------------------------------------------------------


@pytest.mark.asyncio
async def test_hero_boxes_paint_label_blank_row_then_the_two_value_lines():
    """Mutation: any of the three ``BOXES`` labels, the ``.2f ETH`` or the
    ``$,.0f`` format, ``format_cookies``/``format_rate`` in the LEADER body
    -> this reddens. The layout is label, blank, value, sub-line, as the
    copy wrote it.
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**_HERO)
        await pilot.pause()
        lines = _strips(widget.app)
    labels = _line_with(lines, "PRIZE POOL")
    assert "SEASON COUNTDOWN" in labels and "LEADER" in labels
    values = _line_with(lines, "12.50 ETH")
    assert "2d 23h 30m" in values and "139.3K cookies" in values
    sub = _line_with(lines, "$41,000")
    assert "Crumb Cartel  +5,800/hr" in sub
    assert lines.index(values) == lines.index(labels) + 2
    assert lines.index(sub) == lines.index(values) + 1


@pytest.mark.asyncio
async def test_countdown_bar_is_twelve_cells_and_the_percent_is_elapsed():
    """Mutation: the ``12`` cell count, the 720-hour season, ``1 -`` in the
    elapsed fraction -> this reddens. 71.5 h left of 720 is 90 % elapsed:
    ten full blocks, two light ones.
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**_HERO)
        await pilot.pause()
        bar = _line_with(_strips(widget.app), "%")
    assert "█" * 10 + "░" * 2 + " 90%" in bar
    assert "█" * 11 not in bar


@pytest.mark.asyncio
async def test_an_ended_season_relabels_the_box_and_says_so_in_yellow():
    """Mutation: the ``not season_active`` branch, or computing the label
    inside the guard so a failed read paints ``SEASON COUNTDOWN`` -> this
    reddens. The box label *is* the season number when it has ended.
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**{**_HERO, "season_active": False})
        await pilot.pause()
        lines = _strips(widget.app)
        assert not [line for line in lines if "SEASON COUNTDOWN" in line]
        assert "SEASON 4" in _line_with(lines, "PRIZE POOL")
        assert _colour_of(widget.app, "Season Ended") == YELLOW
        assert _bold_of(widget.app, "Season Ended") is True


@pytest.mark.asyncio
async def test_a_failed_hours_read_keeps_the_season_under_unavailable():
    """Mutation: the ``hours is None`` branch -> this reddens. ``unavailable``
    is yellow (``panels.UNAVAILABLE``), the season sub-line is kept, and the
    bar is not drawn.
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**{**_HERO, "hours_remaining": None})
        await pilot.pause()
        lines = _strips(widget.app)
        assert "unavailable" in _line_with(lines, "12.50 ETH")
        assert "SEASON 4" in _line_with(lines, "$41,000")
        assert not [line for line in lines if "%" in line]
        assert _colour_of(widget.app, "unavailable") == YELLOW


@pytest.mark.asyncio
async def test_a_failed_prize_read_is_unavailable_over_the_usd_line():
    """Mutation: the ``eth is not None`` body switch -> this reddens.
    ``unavailable`` sits where the ETH figure would, the USD line stays.
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**{**_HERO, "prize_pool_eth": "n/a"})
        await pilot.pause()
        lines = _strips(widget.app)
        row = _line_with(lines, "2d 23h 30m")
        assert row.index("unavailable") < row.index("2d 23h 30m")
        assert "$41,000" in lines[lines.index(row) + 1]


@pytest.mark.asyncio
async def test_a_hostile_leader_name_and_a_missing_rate_still_render():
    """Mutation: ``safe_markup`` on the name, or ``--/hr`` for a ``None`` rate
    -> this reddens (the name would land on the box's ``unavailable``
    fallback instead of reaching the screen as text).
    """
    widget = HeroMetrics()
    async with _HeroHarness(widget).run_test(size=_HERO_SIZE) as pilot:
        widget.update_data(**{**_HERO, "leader_name": "[/x] Bakers", "leader_rate": None})
        await pilot.pause()
        sub = _line_with(_strips(widget.app), "$41,000")
        assert "[/x] Bakers  --/hr" in sub


# -- Leaderboard --------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_header_cells_sit_at_the_five_column_widths():
    """Mutation: any of ``COLUMNS``' five widths (4/24/10/12/8) -> this
    reddens. A ``DataTable`` pads each cell by one on either side, so a
    header label starts at ``2 + sum(width + 2)`` of the columns before it;
    the fifth width moves nothing to its right and is read off the table.
    """
    rows = await _composited(
        Leaderboard, bakeries=[_bakery(1, "Rug Co", "1000000")],
        production_rates={}, prize_pool_usd=0.0,
    )
    header = rows[2]
    assert header.index("#") == 2, repr(header)
    assert header.index("Bakery") == 8, repr(header)
    assert header.index("Cookies") == 34, repr(header)
    assert header.index("Δ/hr") == 46, repr(header)
    assert header.index("Gap") == 60, repr(header)

    widget = Leaderboard()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        await pilot.pause()
        table = widget.query_one("#leaderboard-table", DataTable)
        assert [c.width for c in table.columns.values()] == [4, 24, 10, 12, 8]


@pytest.mark.asyncio
async def test_leaderboard_rows_are_cookies_rate_and_gap_to_the_leader():
    """Mutation: the ``10_000`` cookie scale, ``format_gap`` against the
    *leader's* cookies (rather than the row's own), or the rate lookup by
    name -> this reddens.
    """
    rows = await _composited(
        Leaderboard,
        bakeries=[_bakery(1, "Rug Co", "1000000"), _bakery(2, "Dough Inc", "500000")],
        production_rates={"Rug Co": 5.0, "Dough Inc": 2.0},
        prize_pool_usd=0.0,
    )
    leader = _line_with(rows, "Rug Co")
    second = _line_with(rows, "Dough Inc")
    assert leader.split() == ["1", "Rug", "Co", "100", "+5/hr", "—"]
    assert second.split() == ["2", "Dough", "Inc", "50", "+2/hr", "-50"]


@pytest.mark.asyncio
async def test_the_leader_row_is_bold_with_a_green_rate_and_the_second_is_not():
    """Mutation: ``index == 0`` in ``build_row`` (the copy's ``idx == 1``),
    or the ``[green]`` around the leader's rate -> this reddens.

    The bold is read composited. The green is read off the cell: row 0 is
    the table's cursor row and ``minimal.tcss`` paints the cursor with
    ``color: $text``, which covers the span's colour on screen -- in
    production too -- so the compositor cannot see it there.
    """
    widget = Leaderboard()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(
            [_bakery(1, "Rug Co", "1000000"), _bakery(2, "Dough Inc", "500000")],
            {"Rug Co": 5.0, "Dough Inc": 2.0},
            0.0,
        )
        await pilot.pause()
        await pilot.pause()
        assert _bold_of(widget.app, "Rug Co") is True
        assert _bold_of(widget.app, "Dough Inc") is False
        table = widget.query_one("#leaderboard-table", DataTable)
        assert str(table.get_row_at(0)[3]) == "[green]+5/hr[/]"
        assert str(table.get_row_at(1)[3]) == "+2/hr"


@pytest.mark.asyncio
async def test_an_empty_board_paints_the_no_data_row_once():
    """Mutation: ``EMPTY_ROW`` -> this reddens. ``[]`` is a real answer --
    the board was read and nobody is on it.
    """
    rows = await _composited(
        Leaderboard, bakeries=[], production_rates={}, prize_pool_usd=0.0
    )
    assert rows[3].split() == ["--", "No", "data", "--", "--", "--"], rows[3]
    assert not rows[4].strip(), rows[4]


@pytest.mark.asyncio
async def test_a_failed_bakeries_read_paints_unavailable_not_no_data():
    """``None`` is "could not look" (follow-up #35): one yellow row, no
    ``No data`` above or below it. Mutation: ``UNAVAILABLE_ROW`` -> reddens."""
    rows = await _composited(
        Leaderboard, bakeries=None, production_rates={}, prize_pool_usd=0.0
    )
    assert rows[3].split() == ["--", "unavailable", "--", "--", "--"], rows[3]
    assert not rows[4].strip(), rows[4]
    assert not any("No data" in row for row in rows), rows


@pytest.mark.asyncio
async def test_the_board_is_capped_at_ten_rows():
    """Mutation: ``ROW_CAP`` -> this reddens."""
    widget = Leaderboard()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(
            [_bakery(i, f"Bakery {i:02d}", str(1_000_000 - i)) for i in range(1, 13)],
            {},
            0.0,
        )
        await pilot.pause()
        table = widget.query_one("#leaderboard-table", DataTable)
        assert table.row_count == 10


@pytest.mark.asyncio
async def test_a_hostile_name_reaches_the_board_as_text_in_the_bold_row():
    """Mutation: ``safe_markup`` on the name -> this reddens (the row is
    skipped by the base's guard and the board shows one row fewer).
    """
    rows = await _composited(
        Leaderboard,
        bakeries=[_bakery(1, "[/x] Bakers", "1000000"), _bakery(2, "Plain", "10000")],
        production_rates={}, prize_pool_usd=0.0,
    )
    assert "[/x] Bakers" in _line_with(rows, "Bakers")
    assert "Plain" in rows[rows.index(_line_with(rows, "Bakers")) + 1]


# -- CookieChart --------------------------------------------------------------

_SERIES_UP = [(1_700_000_000.0 + i * 60, float(i)) for i in range(1, 6)]
_SERIES_DOWN = [(1_700_000_000.0 + i * 60, float(6 - i)) for i in range(1, 6)]


@pytest.mark.asyncio
async def test_cookie_chart_draws_a_thirty_cell_bar_after_an_eight_cell_label():
    """Mutation: ``SPARK_WIDTH`` (30, the copy's ``_SPARK_WIDTH``),
    ``LABEL_WIDTH`` (8) -> this reddens. The label starts at column 4 (the
    panel's ``padding: 0 1``, the line's, and the row's two leading spaces),
    the bar two cells after the eight-cell label, the value two cells after
    the bar, the arrow one cell after the value.
    """
    rows = await _composited(
        CookieChart,
        histories={"Rug Co": _SERIES_UP, "Dough Inc": _SERIES_DOWN, "Flat": [(1.0, 3.0)]},
    )
    first = rows[2]
    assert first.index("Rug Co") == 4, repr(first)
    bar = first[14:44]
    assert len(bar) == 30 and set(bar) <= set(SPARK_CHARS), repr(first)
    assert first[44:].startswith("  5 ▲"), repr(first)
    second = rows[3]
    assert second[4:12] == "Dough In", repr(second)
    assert second[44:].startswith("  1 ▼"), repr(second)
    # One point: a flat baseline, its value and a steady dot, as the copy drew.
    third = rows[4]
    assert third[14:44] == SPARK_CHARS[0] * 30 and third[44:].startswith("  3 ●")


@pytest.mark.asyncio
async def test_cookie_chart_escapes_the_name_after_clipping_it():
    """Mutation: escaping before the clip -> this reddens. ``"[/x]bake"`` is
    eight characters and must reach the screen whole; escaping first turns
    it into ``\\[/x]bake`` (nine), and the clip then cuts the trailing
    ``e``.
    """
    rows = await _composited(CookieChart, histories={"[/x]bake": _SERIES_UP})
    assert rows[2][4:12] == "[/x]bake", repr(rows[2])


@pytest.mark.asyncio
async def test_cookie_chart_says_unavailable_when_the_histories_are_not_a_dict():
    """Mutation: the ``isinstance(histories, dict)`` guard -> this reddens
    (``None.items()`` raises out of ``update_data`` and the app dies). A
    failed read paints ``unavailable`` on the first line, in yellow, and
    blanks the other two; it is distinct from ``{}``, below.
    """
    widget = CookieChart()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(histories=None)
        await pilot.pause()
        assert widget.app._exception is None
        lines = _strips(widget.app)
        assert lines[2].strip() == "unavailable", lines[:5]
        assert not lines[3].strip() and not lines[4].strip()
        assert _colour_of(widget.app, "unavailable") == YELLOW


@pytest.mark.asyncio
async def test_cookie_chart_paints_three_blank_lines_for_no_bakeries():
    """Mutation: writing the ``None`` state for ``{}`` too -> this reddens.
    An empty dict is a read that found nobody, not a read that failed.
    """
    rows = await _composited(CookieChart, histories={})
    assert not any(line.strip() for line in rows[2:5]), rows


@pytest.mark.asyncio
async def test_cookie_chart_blanks_a_named_bakery_with_no_points():
    """Mutation: a flat baseline for an empty series (the copy drew
    ``▁ × 30 … 0 ●``, a run of zeroes that never happened) -> this reddens.
    """
    rows = await _composited(CookieChart, histories={"Rug Co": [], "Dough Inc": _SERIES_UP})
    assert not rows[2].strip(), rows[2]
    assert "Dough In" in rows[3]


# -- SignalsPanel -------------------------------------------------------------

_SIGNALS = dict(
    late_join_ev={"ev_usd": 1234.5},
    gap_analysis={"gap_rate": -2.0},
    dominance=3.5,
    recommendation="Join now",
)


@pytest.mark.asyncio
async def test_signal_rows_have_the_20_12_10_cells_of_the_trailing_shape():
    """Mutation: a ``ROWS`` label, the ``${:,.2f}`` EV format, the ``.1f``
    dominance format, or the ``positive``/``warning`` words -> this reddens.
    ``fmt_signal_trailing``'s defaults: label padded to 20, value
    right-aligned in 12, two cells, the dot, one cell, the word. The label
    sits at column 4: the panel's ``padding: 0 1``, the line's, and the two
    leading spaces of the row shape.
    """
    rows = await _composited(SignalsPanel, **_SIGNALS)
    ev = rows[2]
    assert ev[4:24] == "Late-Join EV        ", repr(ev)
    assert ev[24:36] == "   $1,234.50", repr(ev)
    assert ev[36:] == "  ● positive", repr(ev)
    gap = rows[3]
    assert gap[4:24] == "Gap Trend           " and gap[24:36] == "     closing"
    assert gap[36:] == "  ● closing", repr(gap)
    dom = rows[4]
    assert dom[4:24] == "Leader Dominance    " and dom[24:36] == "        3.5x"
    assert dom[36:] == "  ● warning", repr(dom)


@pytest.mark.asyncio
async def test_signal_dots_carry_the_copys_colours():
    """Mutation: ``_ev_color`` (positive -> green), ``_gap_trend_label``
    (closing -> green), ``_dominance_color`` (>= 3 -> yellow) -> this
    reddens.
    """
    widget = SignalsPanel()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(**_SIGNALS)
        await pilot.pause()
        assert _colour_of(widget.app, "● positive") == GREEN
        assert _colour_of(widget.app, "● closing") == GREEN
        assert _colour_of(widget.app, "● warning") == YELLOW
        widget.update_data(
            late_join_ev={"ev_usd": -1.0}, gap_analysis={"gap_rate": 1.0},
            dominance=float("inf"), recommendation="Wait",
        )
        await pilot.pause()
        assert _colour_of(widget.app, "● negative") == RED
        assert _colour_of(widget.app, "● widening") == RED
        assert "∞x" in _line_with(_strips(widget.app), "Leader Dominance")


@pytest.mark.asyncio
async def test_a_signal_the_manager_could_not_compute_says_unavailable():
    """Mutation: ``None`` passed through to ``.get`` (the copy raised into
    the screen's ``except`` and left ``Loading...`` up) -> this reddens.
    Each row degrades on its own: the two good rows still render.
    """
    widget = SignalsPanel()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(
            late_join_ev=None, gap_analysis={"gap_rate": 0.0}, dominance=None,
            recommendation="Hold",
        )
        await pilot.pause()
        lines = _strips(widget.app)
        ev = _line_with(lines, "Late-Join EV")
        assert ev[24:36] == " unavailable", repr(ev)
        assert ev[36:] == "  ●", repr(ev)
        assert "stable" in _line_with(lines, "Gap Trend")
        assert "unavailable" in _line_with(lines, "Leader Dominance")
        assert not [line for line in lines if "Loading" in line]
        assert _colour_of(widget.app, "unavailable") == YELLOW


@pytest.mark.asyncio
async def test_the_recommendation_is_centred_and_escaped():
    """Mutation: dropping ``safe_markup`` on the recommendation -> this
    reddens (``[/x]`` raises inside the guard and the line lands on
    ``unavailable``). The line is centred by ``.panel-rec``.
    """
    rows = await _composited(SignalsPanel, **{**_SIGNALS, "recommendation": "[/x] Join"})
    rec = _line_with(rows, "Recommendation")
    assert "→ Recommendation: [/x] Join" in rec
    assert rec.index("→") > 20, repr(rec)
    assert not rows[5].strip(), rows


@pytest.mark.asyncio
async def test_a_missing_recommendation_is_unavailable_not_blank():
    """Mutation: writing ``""`` for ``None`` -> this reddens. A blank line
    would pass for "nothing to recommend"; the manager always produces a
    string, so ``None`` is a read that failed.
    """
    rows = await _composited(SignalsPanel, **{**_SIGNALS, "recommendation": None})
    assert "→ Recommendation: unavailable" in _line_with(rows, "Recommendation")


# -- ActivityFeed -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_feed_paints_time_iconed_launcher_and_the_title():
    """Mutation: ``fmt.hhmm`` for the timestamp, the 17-cell launcher, or the
    ``simple`` branch's ``title`` -> this reddens. Epoch ``0`` is ``??:??``
    -- ``hhmm`` treats a non-positive stamp as unknown -- so the pin does not
    depend on the machine's timezone.
    """
    rows = await _composited(ActivityFeed, events=[_event(timestamp="0")])
    line = rows[2].strip()
    assert line.startswith("??:??  0x1111"), repr(line)
    assert "⧉ joined the bakery" in line, repr(line)


@pytest.mark.asyncio
async def test_a_rug_event_names_the_target_and_its_outcome():
    """Mutation: the ``rug`` branch -- ``title: description target`` and the
    green tick / red cross -> this reddens.
    """
    hit = _event(
        type="rug", title="Recipe Sabotage", description="hit", success=True,
        is_outgoing=True, linked_bakery_name="Dough Inc", timestamp="0",
    )
    miss = _event(
        type="rug", title="Supplier Strike", description="x", success=False,
        is_outgoing=True, linked_bakery_name="Dough Inc", timestamp="0",
    )
    widget = ActivityFeed()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data([hit, miss])
        await pilot.pause()
        lines = _strips(widget.app)
        assert "Recipe Sabotage: hit Dough Inc  ✓" in _line_with(lines, "Sabotage")
        assert "Supplier Strike: Failed on Dough Inc  ✗" in _line_with(lines, "Strike")
        assert _colour_of(widget.app, "✓") == FEED_GREEN
        assert _colour_of(widget.app, "✗") == FEED_RED


@pytest.mark.asyncio
async def test_the_dedupe_key_is_time_launcher_type_and_description():
    """Mutation: adding ``title`` to ``dedupe_key`` -> this reddens. The copy
    keyed on those four fields, so a second poll whose only change is a
    title is "nothing new" and leaves the log alone.
    """
    widget = ActivityFeed()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data([_event(timestamp="0", title="joined the bakery")])
        await pilot.pause()
        widget.update_data([_event(timestamp="0", title="left the bakery")])
        await pilot.pause()
        lines = _strips(widget.app)
        assert "joined the bakery" in _line_with(lines, "0x1111")
        assert not [line for line in lines if "left the bakery" in line]
        widget.update_data([_event(timestamp="0", description="new")])
        await pilot.pause()
        assert "0x1111" in _line_with(_strips(widget.app), "0x1111")


@pytest.mark.asyncio
async def test_a_launcher_less_event_is_the_bakerys_own():
    """Mutation: ``_who_text``'s empty-launcher branch -> this reddens."""
    rows = await _composited(ActivityFeed, events=[_event(launcher=None, timestamp="0")])
    assert rows[2].strip().startswith("??:??  the bakery joined the bakery"), repr(rows[2])


# -- EVTable ------------------------------------------------------------------

_BOOSTS = [("Ad Campaign", 2711.5), ("Cleanup Crew Extended", -6000.0)]
_ATTACKS = [("Recipe Sabotage", 1.25), ("Supplier Strike", 0.0)]


@pytest.mark.asyncio
async def test_ev_table_header_and_rows_sit_at_the_14_10_14_8_cells():
    """Mutation: the header format, the 14-cell name clip (``_truncate``),
    the 10-cell EV and 8-cell ratio right-alignments, the star on row 0 ->
    this reddens.
    """
    rows = await _composited(EVTable, boost_rankings=_BOOSTS, attack_rankings=_ATTACKS)
    assert rows[2] == "    Boosts                 EV    Attacks             Gap", repr(rows[2])
    assert not rows[3].strip()
    first = rows[4]
    assert first[2:4] == "★ ", repr(first)
    assert first[4:18] == "Ad Campaign   ", repr(first)
    assert first[19:29] == "    +2,712", repr(first)
    assert first[31:33] == "★ " and first[33:47] == "Recipe Sabota.", repr(first)
    assert first[48:56] == "    1.2x", repr(first)
    second = rows[5]
    assert second[4:18] == "Cleanup Crew .", repr(second)
    assert second[19:29] == "    -6,000", repr(second)
    assert second[33:47] == "Supplier Stri." and second[48:56] == "    0.0x", repr(second)


@pytest.mark.asyncio
async def test_ev_table_colours_positive_green_negative_red_and_zero_dim():
    """Mutation: ``[green]``/``[red]`` on the EV, ``[dim]`` on a zero ratio
    -> this reddens.
    """
    widget = EVTable()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(_BOOSTS, _ATTACKS)
        await pilot.pause()
        assert _colour_of(widget.app, "+2,712") == GREEN
        assert _colour_of(widget.app, "-6,000") == RED
        assert _colour_of(widget.app, "1.2x") == GREEN
        assert _colour_of(widget.app, "0.0x") != GREEN


@pytest.mark.asyncio
async def test_a_third_row_with_nothing_ranked_is_blank_not_stale():
    """Mutation: dropping the ``i < len(...)`` padding branches -> this
    reddens. Two boosts and one attack leave row 2 empty and row 1's attack
    side empty; a shorter list must not raise past the earlier rows.
    """
    rows = await _composited(EVTable, boost_rankings=_BOOSTS, attack_rankings=_ATTACKS[:1])
    assert rows[5].rstrip() == "    Cleanup Crew .     -6,000", repr(rows[5])
    assert not rows[6].strip(), rows[6]


@pytest.mark.asyncio
async def test_rankings_the_manager_could_not_produce_say_unavailable_thrice():
    """Mutation: ``boost_rankings or []`` (three blank rows) -> this reddens.
    The manager always returns a list, so ``None`` is a failed read and each
    of the three rows says so; ``Loading...`` is gone.
    """
    widget = EVTable()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(None, None)
        await pilot.pause()
        lines = _strips(widget.app)
        assert [line.strip() for line in lines[4:7]] == ["unavailable"] * 3, lines
        assert not [line for line in lines if "Loading" in line]
        assert _colour_of(widget.app, "unavailable") == YELLOW


@pytest.mark.asyncio
async def test_the_stale_catalog_marker_is_yellow_on_the_title_row():
    """Mutation: the title write for a non-live ``catalog_source`` -> this
    reddens; the colour pin is new here (the catalog-source file pins the
    words).
    """
    widget = EVTable()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(_BOOSTS, _ATTACKS, "fallback")
        await pilot.pause()
        lines = _strips(widget.app)
        assert lines[0].strip().startswith("BEST PLAYS  ⚠ STALE CATALOG"), lines[0]
        assert _colour_of(widget.app, "STALE") == YELLOW
        assert not lines[1].strip()


# -- the stylesheet -----------------------------------------------------------


@pytest.mark.guard
def test_the_stylesheet_carries_no_bakery_title_block():
    """Mutation: paste any of the five deleted title blocks back into
    ``minimal.tcss`` -> this reddens. The title's colour and its blank row
    are ``PanelBase``'s now; a stylesheet block restating them would win on
    specificity and make the base's rule unfalsifiable for bakery.
    """
    text = STYLESHEET.read_text(encoding="utf-8")
    for selector in (
        "Leaderboard > Static",
        "CookieChart > .chart-title",
        "SignalsPanel > .signals-title",
        "ActivityFeed > .feed-title",
        "EVTable > .ev-title",
    ):
        assert selector not in text, selector
