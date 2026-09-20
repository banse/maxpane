"""Headless Textual tests for the Talismans dashboard widgets.

Each widget is mounted in a tiny ``App`` via ``App.run_test()`` and then
``update_data()`` is exercised three ways:

* (a) no args
* (b) empty/None payload
* (c) a representative full payload from the WP3 data contract

Every call must complete without raising, and where sensible we assert
the DataTable / RichLog ends up with the expected number of rows/lines.
"""

from __future__ import annotations

import time

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, RichLog

from maxpane_dashboard.widgets.talismans import (
    TalismansActivityFeed,
    TalismansHeroMetrics,
    TalismansLeaderboard,
    TalismansMaterialsTable,
    TalismansMatrixTable,
    TalismansSignals,
    TalismansSparkline,
)


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


# -- hero metrics -----------------------------------------------------


@pytest.mark.asyncio
async def test_hero_metrics():
    widget = TalismansHeroMetrics()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(
            live_tokens=None,
            mythic_count=None,
            total_cores=None,
            operations_24h=None,
        )
        widget.update_data(
            live_tokens=1490,
            token_drift=-46,
            mythic_count=12,
            mythic_pct=0.8,
            mythics_ever_forged=15,
            total_cores=1536,
            cores_invariant_intact=True,
            genesis_minted=1536,
            operations_24h=34,
            operations_total=2891,
        )
        # invariant broken path
        widget.update_data(
            live_tokens=1490,
            token_drift=-46,
            mythic_count=12,
            mythic_pct=0.8,
            mythics_ever_forged=15,
            total_cores=1500,
            cores_invariant_intact=False,
            operations_24h=34,
            operations_total=2891,
        )


# -- leaderboard ------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard():
    widget = TalismansLeaderboard()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(top_collectors=[])
        table = widget.query_one(DataTable)
        assert table.row_count == 1  # "No data" row

        collectors = [
            {
                "rank": i,
                "address": f"0x{i:040x}",
                "tokens": 100 - i,
                "cores": 50 - i,
                "mythics": i,
            }
            for i in range(1, 6)
        ]
        widget.update_data(top_collectors=collectors)
        assert table.row_count == 5


# -- sparkline --------------------------------------------------------


@pytest.mark.asyncio
async def test_sparkline():
    widget = TalismansSparkline()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(mythic_history=[], operations_history=[])
        # single point -> still flat / waiting, must not crash
        widget.update_data(
            mythic_history=[[1000, 5]],
            operations_history=[[1000, 1]],
        )
        widget.update_data(
            mythic_history=[[1000 + i * 86400, i] for i in range(10)],
            operations_history=[[1000 + i * 86400, 30 - i] for i in range(10)],
        )


# -- signals ----------------------------------------------------------


@pytest.mark.asyncio
async def test_signals():
    widget = TalismansSignals()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(
            conservation_signal=None,
            cutmerge_signal=None,
            forge_momentum_signal=None,
            mythic_scarcity_signal=None,
        )
        widget.update_data(
            conservation_signal={
                "label": "Conservation",
                "value_str": "cores conserved",
                "indicator": "●",
                "color": "green",
            },
            cutmerge_signal={
                "label": "Cut/Merge",
                "value_str": "net +3 cuts",
                "indicator": "▲",
                "color": "yellow",
            },
            forge_momentum_signal={
                "label": "Forge",
                "value_str": "2 mythics 24h",
                "indicator": "●",
                "color": "green",
            },
            mythic_scarcity_signal={
                "label": "Scarcity",
                "value_str": "0.8% mythic",
                "indicator": "●",
                "color": "red",
            },
        )


# -- activity feed ----------------------------------------------------


@pytest.mark.asyncio
async def test_activity_feed():
    widget = TalismansActivityFeed()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(activity_events=[])
        log = widget.query_one(RichLog)
        assert len(log.lines) == 1  # "No activity yet"

        now = int(time.time())
        events = [
            {
                "tx_hash": "0xaaa",
                "block_number": 100,
                "timestamp": now,
                "op_type": "bond",
                "token_id_a": 12,
                "token_id_b": 34,
                "result_id": 99,
                "operator": "0xabc",
                "essence": "Mythic",
                "tier": "Bonded",
            },
            {
                "timestamp": now,
                "op_type": "cleave",
                "token_id_a": 50,
                "result_id": 51,
            },
            {
                "timestamp": now,
                "op_type": "cut",
                "token_id_a": 7,
                "result_id": 8,
            },
            {
                "timestamp": now,
                "op_type": "merge",
                "token_id_a": 1,
                "token_id_b": 2,
                "result_id": 3,
            },
            # malformed / unknown op type still must not crash
            {"timestamp": now, "op_type": "weird"},
            {"timestamp": None, "op_type": "bond"},
        ]
        widget.update_data(activity_events=events)
        assert len(log.lines) == len(events)


# -- matrix table -----------------------------------------------------


@pytest.mark.asyncio
async def test_matrix_table():
    widget = TalismansMatrixTable()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(essence_tier_matrix={"rows": [], "totals": {}})
        table = widget.query_one(DataTable)
        assert table.row_count == 1  # "No data" row

        matrix = {
            "rows": [
                {
                    "essence": "Lithic",
                    "raw": 500,
                    "cut": 200,
                    "fine": 100,
                    "prime": 50,
                    "bonded": 0,
                    "total": 850,
                },
                {
                    "essence": "Lumic",
                    "raw": 300,
                    "cut": 150,
                    "fine": 80,
                    "prime": 40,
                    "bonded": 0,
                    "total": 570,
                },
                {
                    "essence": "Mythic",
                    "raw": 0,
                    "cut": 0,
                    "fine": 0,
                    "prime": 0,
                    "bonded": 12,
                    "total": 12,
                },
            ],
            "totals": {
                "raw": 800,
                "cut": 350,
                "fine": 180,
                "prime": 90,
                "bonded": 12,
                "total": 1432,
            },
        }
        widget.update_data(essence_tier_matrix=matrix)
        assert table.row_count == 4  # 3 rows + TOTAL


# -- materials table --------------------------------------------------


@pytest.mark.asyncio
async def test_materials_table():
    widget = TalismansMaterialsTable()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(materials_ledger=[])
        table = widget.query_one(DataTable)
        assert table.row_count == 1  # "No data" row

        ledger = [
            {
                "rank": i,
                "material": f"Material {i}",
                "essence": "Lithic",
                "tokens": 100 - i,
                "cores": 50 - i,
            }
            for i in range(1, 7)
        ]
        widget.update_data(materials_ledger=ledger)
        assert table.row_count == 6


# -- composited pins (Branch 7 WP-B) -----------------------------------
#
# The tests above are smoke tests: they drive `update_data` three ways and
# assert a row count. That is enough to catch a crash and nothing else --
# every one of them stayed green through the whole migration, including
# under three deliberate mutations. What a panel *puts on screen* is what
# the migration could have changed, so the pins below assert the
# composited strips (the repo rule: `render_strips()`, never the content
# string), and each one names the mutation it exists to redden.


_PIN_SIZE = (120, 24)


async def _composited(widget, **payload) -> list[str]:
    """The widget's composited lines after one poll."""
    app = _Harness(widget)
    async with app.run_test(size=_PIN_SIZE) as pilot:
        widget.update_data(**payload)
        await pilot.pause()
        return [
            "".join(seg.text for seg in strip).rstrip()
            for strip in app.screen._compositor.render_strips()
        ]


def _line_with(lines: list[str], needle: str) -> str:
    matches = [line for line in lines if needle in line]
    assert len(matches) == 1, f"{needle!r} in {matches!r} of {lines!r}"
    return matches[0]


#: A rising series whose last value the two candidate formatters spell
#: differently: ``fmt_int`` -> ``1,900``, ``sparkline_common.fmt_compact``
#: (``SparklinePanel``'s default) -> ``1.9K``.
_RISING = [[1_000 + i * 86_400, 1_000 + i * 100] for i in range(10)]


@pytest.mark.asyncio
async def test_the_sparkline_value_cell_is_a_grouped_integer_not_a_compact_one():
    """Mutation: drop ``TalismansSparkline.fmt_value`` -> this reddens.

    Both series are counts of whole things in the low thousands, and the
    panel has the room to show them exactly. ``fmt_compact`` would round
    1,900 Mythics to ``1.9K``.
    """
    lines = await _composited(
        TalismansSparkline(),
        mythic_history=_RISING,
        operations_history=_RISING,
    )
    row = _line_with(lines, "MYTHIC COUNT")
    assert row.endswith("1,900"), row
    assert "1.9K" not in row, row


@pytest.mark.asyncio
async def test_the_sparkline_draws_no_trend_arrow():
    """Mutation: set ``SHOW_ARROW = True`` -> this reddens.

    The arrow is the base's default and this panel never drew one; it
    would also arrive with a leading space, i.e. a ragged trailing cell.
    """
    lines = await _composited(
        TalismansSparkline(),
        mythic_history=_RISING,
        operations_history=_RISING,
    )
    row = _line_with(lines, "MYTHIC COUNT")
    assert not any(glyph in row for glyph in ("▲", "▼", "●")), row


@pytest.mark.asyncio
async def test_a_series_too_short_to_draw_keeps_its_label():
    """Mutation: ``MIN_POINTS = 1`` or ``EMPTY_KEEPS_LABEL = False``.

    One sample is drawn by ``build_sparkline_from_points`` as a flat
    baseline, which reads as a run of zeroes that never happened -- so
    this panel says so in words instead, **beside the label**, because
    with two stacked series the reader has to be able to tell which one
    is not ready.
    """
    lines = await _composited(
        TalismansSparkline(),
        mythic_history=[[1_000, 5]],
        operations_history=_RISING,
    )
    row = _line_with(lines, "MYTHIC COUNT")
    assert "waiting for data" in row, row
    # The other series is drawn, so this is not a panel that simply failed.
    assert "1,900" in _line_with(lines, "DAILY OPERATIONS")


@pytest.mark.asyncio
async def test_the_empty_leaderboard_says_no_data_under_the_wallet_column():
    """Mutation: move ``No data`` to another cell of ``EMPTY_ROW``.

    A cell tuple of the wrong shape paints the degraded state under the
    wrong heading -- and ``DataTable.add_row`` pads a short tuple in
    silence, so nothing else would say.
    """
    lines = await _composited(TalismansLeaderboard(), top_collectors=[])
    header = _line_with(lines, "WALLET")
    row = _line_with(lines, "No data")
    assert header.index("WALLET") == row.index("No data"), (header, row)
    # ... and the rank column is a dash, not the word.
    assert row.lstrip().startswith("--"), row


@pytest.mark.asyncio
async def test_the_signals_separator_keeps_forge_momentum_off_the_cutmerge_group():
    """Mutation: delete the bare ``None`` item from ``ROWS`` -> this reddens.

    The separator is a blank ``.panel-line`` *between* two groups of
    rows -- conservation / cut-merge above, forge / scarcity below -- and
    it is not the title's blank row, which is ``PanelBase``'s margin. It
    was unpinned: removing it left the whole named set, the sweep and the
    guard tests green while the panel lost a row of structure.
    """
    def _sig(value_str: str) -> dict:
        return {
            "label": "ignored",      # the rows are label-less
            "value_str": value_str,
            "indicator": "●",
            "color": "green",
        }

    lines = await _composited(
        TalismansSignals(),
        conservation_signal=_sig("cores conserved"),
        cutmerge_signal=_sig("net +3 cuts"),
        forge_momentum_signal=_sig("2 mythics 24h"),
        mythic_scarcity_signal=_sig("0.8% mythic"),
    )
    cutmerge_at = lines.index(_line_with(lines, "net +3 cuts"))
    forge_at = lines.index(_line_with(lines, "2 mythics 24h"))
    assert forge_at == cutmerge_at + 2, lines
    assert lines[cutmerge_at + 1].strip() == "", lines
    # Scarcity follows forge with no gap: one separator, not two.
    scarcity_at = lines.index(_line_with(lines, "0.8% mythic"))
    assert scarcity_at == forge_at + 1, lines
