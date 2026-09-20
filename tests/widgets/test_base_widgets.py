"""Composited pins for the six Base Terminal (``BT*``) widgets (Branch 8 WP-A).

Every assertion here is on **composited output** (``render_strips()``),
never on a content string, and every test names the mutation it exists to
redden. The six widgets under ``widgets/base/overview/`` had **no**
composited widget test before this branch (``test_base_address_icons.py``
covers the icon, ``tests/screens/test_base_terminal_screen.py`` the
status bar); each constant the migration onto ``widgets/panels.py``
introduces is pinned here so that a mutation to it reddens something.

The one non-composited assertion is the leaderboard's sixth column width:
the last column's width moves nothing to its right, so it is read off the
``DataTable`` directly, beside the composited pin of the other five.
"""

from __future__ import annotations

from rich.highlighter import ReprHighlighter
from rich.text import Text
import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets.base.overview import (
    BTActivityFeed,
    BTBestPlays,
    BTOverviewHero,
    BTOverviewLeaderboard,
    BTSignals,
    BTSparklines,
)
from maxpane_dashboard.widgets.sparkline_common import SPARK_CHARS

from tests.widgets.surf_compositing import composite_lines


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


def _token(i: int, **overrides) -> dict:
    tok = {
        "symbol": f"TK{i:02d}",
        "address": "0x" + f"{i:02x}" * 20,
        "price_usd": 1.5,
        "price_change_24h": 3.0,
        "volume_24h": 90_000.0,
        "market_cap": 2_000_000.0,
    }
    tok.update(overrides)
    return tok


# -- BTOverviewLeaderboard --------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_header_cells_sit_at_the_six_column_widths():
    """Mutation: any of ``COLUMNS``' six widths (4/14/14/10/12/12) -> this
    reddens. A ``DataTable`` pads each cell by one on either side, so a
    header label starts at ``2 + sum(width + 2)`` of the columns before it;
    the sixth width moves nothing to its right and is read off the table.
    """
    rows = await _composited(BTOverviewLeaderboard, trending_tokens=[_token(1)])
    header = rows[2]
    assert header.index("#") == 2, repr(header)
    assert header.index("Token") == 8, repr(header)
    assert header.index("Price") == 24, repr(header)
    assert header.index("24h %") == 40, repr(header)
    assert header.index("Volume") == 52, repr(header)
    assert header.index("Mcap") == 66, repr(header)

    widget = BTOverviewLeaderboard()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        await pilot.pause()
        table = widget.query_one("#bto-lb-table", DataTable)
        assert [c.width for c in table.columns.values()] == [4, 14, 14, 10, 12, 12]


@pytest.mark.asyncio
async def test_leaderboard_draws_fifteen_rows_and_not_the_sixteenth():
    """Mutation: ``ROW_CAP = 15`` -> ``10`` or ``None`` -> this reddens."""
    rows = await _composited(
        BTOverviewLeaderboard, trending_tokens=[_token(i) for i in range(1, 21)]
    )
    assert _line_with(rows, "TK15").startswith("  15 "), rows
    assert not any("TK16" in line for line in rows), rows
    assert not any(line.startswith("  16 ") for line in rows), rows


@pytest.mark.asyncio
async def test_leaderboard_empty_row_puts_no_data_in_the_token_cell():
    """Mutation: move ``No data`` to another cell of ``EMPTY_ROW`` -> this
    reddens. The second cell starts at column 8 (``#`` is 4 wide, padded)."""
    rows = await _composited(BTOverviewLeaderboard, trending_tokens=[])
    line = _line_with(rows, "No data")
    assert line.index("--") == 2, repr(line)
    assert line.index("No data") == 8, repr(line)


@pytest.mark.asyncio
async def test_leaderboard_bolds_the_top_three_symbols_only():
    """Mutation: ``is_top = idx <= 3`` -> ``idx == 1`` -> this reddens.
    Read off the compositor's styles, not the cell string."""
    widget = BTOverviewLeaderboard()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data([_token(i) for i in range(1, 6)])
        await pilot.pause()
        bold: dict[str, bool] = {}
        for strip in pilot.app.screen._compositor.render_strips():
            for seg in strip:
                if seg.text.strip().startswith("TK") and seg.style is not None:
                    bold[seg.text.strip()] = bool(seg.style.bold)
    assert bold == {"TK01": True, "TK02": True, "TK03": True,
                    "TK04": False, "TK05": False}, bold


# -- BTSparklines --------------------------------------------------------------

_SERIES = [(1_700_000_000.0 + i * 3_600, 1_000_000.0 + i * 50_000) for i in range(6)]
_SMALL = [(1_700_000_000.0, 900.0), (1_700_003_600.0, 950.0)]


@pytest.mark.asyncio
async def test_sparkline_labels_are_padded_to_ten_cells():
    """Mutation: ``LABEL_WIDTH = 10`` -> ``8`` (the base default) -> this
    reddens. Two before the label are the row's, one before those is
    ``.panel-line``'s padding and one more is the ``BTSparklines`` block's
    own ``padding: 0 1`` in ``minimal.tcss`` (the label sits at column 4, as
    the SIGNALS labels do); the bar starts at ``4 + 10 + 2 = 16``."""
    rows = await _composited(
        BTSparklines, volume_history=_SERIES, trade_count_history=_SERIES
    )
    for label in ("Volume", "Trades"):
        line = _line_with(rows, label)
        bar_at = next(i for i, ch in enumerate(line) if ch in SPARK_CHARS)
        assert bar_at == 16, (label, repr(line))


@pytest.mark.asyncio
async def test_sparkline_is_twenty_blocks_wide_not_the_shared_twenty_two():
    """Mutation: ``SPARK_WIDTH = 20`` deleted (base default 22) -> this
    reddens. The copy drew a 20-cell bar and the panel is sized for it."""
    rows = await _composited(BTSparklines, volume_history=_SERIES)
    line = _line_with(rows, "Volume")
    assert sum(ch in SPARK_CHARS for ch in line) == 20, repr(line)


@pytest.mark.asyncio
async def test_sparkline_draws_the_trend_arrow():
    """Mutation: ``SHOW_ARROW = False`` -> this reddens."""
    rows = await _composited(BTSparklines, volume_history=_SERIES)
    line = _line_with(rows, "Volume")
    assert line.endswith("▲"), repr(line)


@pytest.mark.asyncio
async def test_an_empty_series_says_waiting_beside_its_label():
    """Mutation: ``EMPTY_TEXT`` -> ``""`` or ``EMPTY_KEEPS_LABEL = False`` ->
    this reddens. All three lines say so when nothing has been recorded."""
    rows = await _composited(BTSparklines)
    for label in ("Volume", "ETH", "Trades"):
        line = _line_with(rows, label)
        assert line.startswith(f"    {label:<10}  waiting for data..."), repr(line)


@pytest.mark.asyncio
async def test_sparkline_values_keep_the_dollar_prefix_and_per_hour_suffix():
    """Mutation: drop the ``fmt_value`` override (``fmt_compact``) -> this
    reddens: ``$1.2M`` becomes ``1.2M``, ``950/h`` becomes ``950.0/h``,
    ``$950`` becomes ``950.0``."""
    rows = await _composited(
        BTSparklines, volume_history=_SERIES, eth_price_history=_SMALL,
        trade_count_history=_SMALL,
    )
    assert "$1.2M" in _line_with(rows, "Volume"), rows
    assert "$950" in _line_with(rows, "ETH"), rows
    assert "950/h" in _line_with(rows, "Trades"), rows
    assert not any("950.0" in line for line in rows), rows


# -- BTSignals ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_rows_are_label_value_then_trailing_dot():
    """Mutation: swap ``fmt_signal_trailing`` for the base's ``fmt_signal``
    (dot first) or change ``label_width``/``value_width`` -> this reddens.
    Label at column 4 (the ``BTSignals`` block's ``padding: 0 1`` in
    ``minimal.tcss``, the ``.panel-line`` padding, then the row's two), the
    value right-aligned to end at ``4 + 20 + 12 = 36``, the dot two cells
    after."""
    rows = await _composited(
        BTSignals, buy_sell_signal="Bullish", volume_signal="Rising",
        whale_signal=None,
    )
    buy = _line_with(rows, "Buy/Sell")
    assert buy.index("Buy/Sell") == 4, repr(buy)
    assert buy.index("Bullish") + len("Bullish") == 36, repr(buy)
    assert buy.index("●") == 38, repr(buy)
    assert buy.rstrip().endswith("●"), repr(buy)
    whale = _line_with(rows, "Whale Activity")
    assert whale.index("...") + 3 == 36, repr(whale)
    # Row order: Buy/Sell, Volume, Whale Activity, consecutive.
    order = [rows.index(_line_with(rows, n)) for n in ("Buy/Sell", "Volume", "Whale Activity")]
    assert order == [order[0], order[0] + 1, order[0] + 2], order


@pytest.mark.asyncio
async def test_recommendation_is_blank_when_empty_and_one_row_under_the_rows():
    """Mutation: write the recommendation line unconditionally, or add a
    bare ``None`` to ``ROWS`` beside the base's own pre-recommendation blank
    (two blanks) -> this reddens."""
    empty = await _composited(BTSignals, buy_sell_signal="Bullish")
    assert not any("Recommendation" in line for line in empty), empty
    whale_at = empty.index(_line_with(empty, "Whale Activity"))
    assert all(not line.strip() for line in empty[whale_at + 1:]), empty

    full = await _composited(
        BTSignals, buy_sell_signal="Bullish", recommendation="Accumulate",
    )
    whale_at = full.index(_line_with(full, "Whale Activity"))
    rec = _line_with(full, "→ Recommendation: Accumulate")
    assert full.index(rec) == whale_at + 2, full
    assert not full[whale_at + 1].strip(), full


# -- BTActivityFeed -------------------------------------------------------------

_TRADE = {
    "symbol": "DEGEN", "volume_24h": 1_200_000.0, "buys_24h": 60,
    "sells_24h": 40, "price_change_24h": 12.0, "liquidity": 500_000.0,
}


@pytest.mark.asyncio
async def test_feed_paints_the_placeholder_once_across_empty_polls():
    """Mutation: drop the ``clear()`` before the placeholder, or write it
    on every empty poll (the copy's ``_has_data`` shape) -> this reddens.
    The pre-migration capture showed ``No activity yet`` twice after the
    two refreshes a mount performs."""
    widget = BTActivityFeed()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(whale_trades=[])
        await pilot.pause()
        widget.update_data(whale_trades=None)
        await pilot.pause()
        lines = _strips(pilot.app)
    assert sum("No activity yet" in line for line in lines) == 1, lines


@pytest.mark.asyncio
async def test_feed_keeps_its_rows_on_an_empty_poll():
    """Mutation: ``SNAPSHOT = True`` -> this reddens (a snapshot re-paints
    and an empty poll would blank the ranking). Stream mode is the copy's
    own behaviour: a transient empty poll leaves the rows alone."""
    widget = BTActivityFeed()
    async with _Harness(widget).run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(whale_trades=[_TRADE])
        await pilot.pause()
        widget.update_data(whale_trades=[])
        await pilot.pause()
        lines = _strips(pilot.app)
    assert any("DEGEN" in line for line in lines), lines
    assert not any("No activity yet" in line for line in lines), lines


@pytest.mark.asyncio
async def test_feed_writes_its_column_header_above_the_first_row():
    """Mutation: ``HEADER_LINE = None`` -> this reddens. The header is a
    row of its own -- title, blank, header, then the ranking."""
    rows = await _composited(BTActivityFeed, whale_trades=[_TRADE])
    assert rows[0].strip() == "ACTIVITY", rows
    assert not rows[1].strip(), rows
    assert "Token" in rows[2] and "Buys/Sells" in rows[2], rows
    assert "DEGEN" in rows[3] and "$1.2M" in rows[3], rows
    assert rows[3].index("DEGEN") == rows[2].index("Token"), rows


def test_feed_rows_carry_the_repr_highlight_the_copy_had():
    """Mutation: return ``Text.from_markup(...)`` without the highlighter ->
    this reddens. ``RichLog`` highlights *strings* it is handed and not
    ``Text``; the copy wrote strings, so the migrated ``Text`` row applies
    the same ``ReprHighlighter`` itself or the numbers lose their colour."""
    from maxpane_dashboard.widgets.base.overview.bt_activity_feed import (
        _token_to_markup,
    )

    row = BTActivityFeed().format_row(_TRADE)
    assert isinstance(row, Text)
    reference = ReprHighlighter()(Text.from_markup(_token_to_markup(_TRADE)))
    assert row.plain == reference.plain
    assert row.spans == reference.spans, row.spans
    assert any(str(s.style).startswith("repr.") for s in row.spans), row.spans


# -- BTBestPlays ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_best_plays_keeps_one_gap_row_between_header_and_rows():
    """Mutation: yield a second spacer under the header, or drop the one
    that is there -> this reddens. Title, blank, header, blank, first row."""
    rows = await _composited(
        BTBestPlays, gainers=[("ALPHA", "+12.0%")], losers=[("BETA", "-3.0%")],
    )
    assert rows[0].strip() == "BEST PLAYS", rows
    assert not rows[1].strip(), rows
    assert "Top Gainers" in rows[2] and "Top Losers" in rows[2], rows
    assert not rows[3].strip(), rows
    assert rows[4].lstrip().startswith("* ALPHA"), repr(rows[4])
    assert "+12.0%" in rows[4] and "* BETA" in rows[4] and "-3.0%" in rows[4], rows


# -- BTOverviewHero ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_hero_says_no_data_for_a_missing_gainer_and_dots_for_none():
    """Mutation: render the ``None`` gainer as ``unavailable`` (the base's
    fallback) -> this reddens. ``No data`` is the copy's own text for a
    real negative -- no token moved -- not for a build that failed."""
    rows = await _composited(
        BTOverviewHero, eth_price=None, eth_change_24h=None, total_volume=None,
        top_gainer_name=None, top_gainer_pct=None,
    )
    assert any("No data" in line for line in rows), rows
    assert not any("unavailable" in line for line in rows), rows
    dots = _line_with(rows, "...")
    assert dots.count("...") == 3, repr(dots)


@pytest.mark.asyncio
async def test_hero_formats_the_four_values_as_the_copy_did():
    """Mutation: any of the four box bodies -> this reddens."""
    rows = await _composited(
        BTOverviewHero, eth_price=3000.0, eth_change_24h=1.5,
        total_volume=1_234_567.0, top_gainer_name="DEGEN", top_gainer_pct=12.0,
    )
    values = _line_with(rows, "$3,000.00")
    assert "+1.50%" in values and "$1.2M" in values and "DEGEN" in values, values
