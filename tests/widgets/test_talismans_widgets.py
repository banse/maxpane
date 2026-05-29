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
