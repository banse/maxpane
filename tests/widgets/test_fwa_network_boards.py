"""Responsive and safety tests for the NETWORK DataTables."""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.data.fwa_ecosystem_models import FWA_NETWORK_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa.fwa_ecosystem_registry import (
    FWAEcosystemRegistry,
)
from maxpane_dashboard.widgets.fwa.fwair_drop_board import FWAIRDropBoard


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _headers(table: DataTable) -> list[str]:
    return [str(column.label) for column in table.columns.values()]


def _rows(table: DataTable) -> list[list[str]]:
    return [
        [str(cell) for cell in table.get_row_at(index)]
        for index in range(table.row_count)
    ]


def _static_plain(widget, selector: str) -> str:
    visual = widget.query_one(selector, Static).visual
    return getattr(visual, "plain", str(visual))


def _drop_row(**changes) -> dict:
    row = {
        "launch_id": 2,
        "launch_address": "0x" + "12" * 20,
        "collection_address": "0x" + "34" * 20,
        "collection_name": "海豚🙂 [red]Drop[/]",
        "phase": "supporting",
        "support_open": True,
        "token_count": 10_000,
        "supported_count": 350,
        "supporter_count": 72,
        "launched_count": 120,
        "terminal_count": 15,
        "backing_eth": 18.125,
        "total_backing_eth": 22.5,
        "artist_credit_eth": 1.25,
        "supporter_principal_eth": 17.0,
        "supporter_reserve_fwa": 9_876.5,
        "source_kind": "chain_state",
        "measurement": "measured",
        "block_number": 25_849_738,
        "observed_at": 1_784_900_000.0,
        "stale": False,
        "verified_source": True,
        "integrity": "ok",
    }
    row.update(changes)
    return row


def _project_row(**changes) -> dict:
    row = {
        "family": "pullpool",
        "surface": "pool",
        "version": "v2",
        "address": "0x" + "56" * 20,
        "is_current": True,
        "is_legacy_liability": False,
        "lifecycle": "open",
        "primary_label": "active rounds",
        "primary_value": 12,
        "primary_unit": "rounds",
        "eth_label": "owed",
        "eth_value": 2.5,
        "fwa_label": "claim",
        "fwa_value": 12_345.0,
        "detail": "[/x] hostile detail 海🙂",
        "source_badge": "VERIFIED",
        "source_kind": "chain_state",
        "measurement": "derived",
        "block_number": 25_849_738,
        "observed_at": 1_784_900_000.0,
        "stale": False,
        "verified_source": True,
        "integrity": "ok",
    }
    row.update(changes)
    return row


def test_board_signatures_are_exact_and_keyword_only() -> None:
    for name, widget in (
        ("FWAIRDropBoard", FWAIRDropBoard),
        ("FWAEcosystemRegistry", FWAEcosystemRegistry),
    ):
        signature = inspect.signature(widget.update_data)
        params = tuple(key for key in signature.parameters if key != "self")
        assert params == FWA_NETWORK_WIDGET_SIGNATURES[name]
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for key, parameter in signature.parameters.items()
            if key != "self"
        )


async def test_drop_board_full_preserves_launch_dimensions_and_literal_names() -> None:
    widget = FWAIRDropBoard()
    async with _Harness(widget).run_test(size=(180, 22)):
        widget.update_data(
            network_drop_rows=[_drop_row()],
            network_drops_available=True,
            network_drops_as_of_block=25_849_738,
            network_drops_stale=False,
        )
        table = widget.query_one("#fwair-drop-table", DataTable)
        headers = _headers(table)
        assert headers == [
            "ID",
            "DROP",
            "PHASE",
            "OPEN",
            "TOKENS",
            "SUPPORTED",
            "SUPPORTERS",
            "LAUNCHED",
            "TERMINAL",
            "BACKING",
            "TOTAL ETH",
            "ARTIST ETH",
            "PRINC ETH",
            "RES FWA",
        ]
        joined = " ".join(_rows(table)[0])
        assert "海豚🙂 [red]Drop[/]" in joined
        assert "supporting" in joined
        assert "18.125" in joined and "22.500" in joined
        assert "1.250" in joined and "17.000" in joined and "9,876.5" in joined
        assert "120" in joined and "15" in joined
        assert "widen" not in _static_plain(widget, "#fwair-title")


async def test_drop_board_narrow_keeps_required_dimensions_and_announces_shed() -> None:
    widget = FWAIRDropBoard()
    async with _Harness(widget).run_test(size=(55, 20)):
        widget.update_data(
            network_drop_rows=[_drop_row(collection_name="🙂" * 30)],
            network_drops_available=True,
            network_drops_as_of_block=12,
            network_drops_stale=True,
        )
        table = widget.query_one("#fwair-drop-table", DataTable)
        headers = _headers(table)
        assert headers == ["ID", "PHASE", "FUND ETH", "TERM/LAUNCH"]
        assert "widen" in _static_plain(widget, "#fwair-title")
        row = _rows(table)[0]
        assert "2" in row[0] and "supporting" in row[1]
        assert "22.500" in row[2] and "15/120" in row[3]
        assert "stale" in _static_plain(widget, "#fwair-note")
async def test_drop_board_blank_and_last_good_states_are_distinct() -> None:
    widget = FWAIRDropBoard()
    async with _Harness(widget).run_test(size=(90, 20)):
        widget.update_data(
            **{
                key: None
                for key in FWA_NETWORK_WIDGET_SIGNATURES["FWAIRDropBoard"]
            }
        )
        assert "drop data unavailable" in " ".join(_rows(widget.query_one(DataTable))[0])
        widget.update_data(
            network_drop_rows=[_drop_row()],
            network_drops_available=False,
            network_drops_as_of_block=10,
            network_drops_stale=True,
        )
        assert "last good" in _static_plain(widget, "#fwair-note")
        assert len(_rows(widget.query_one(DataTable))) == 1


async def test_registry_preserves_labels_units_source_and_legacy_indentation() -> None:
    widget = FWAEcosystemRegistry()
    project_rows = [
        _project_row(),
        _project_row(
            version="v1",
            is_current=False,
            is_legacy_liability=True,
            lifecycle="refunding",
            source_badge="INTEGRITY",
            integrity="mismatch",
        ),
        _project_row(
            family="megarip",
            surface="campaign",
            version="v1",
            is_current=False,
            is_legacy_liability=False,
            source_badge="CHAIN-READ",
        ),
    ]
    async with _Harness(widget).run_test(size=(180, 24)):
        widget.update_data(
            network_project_rows=project_rows,
            network_projects_available=True,
            network_projects_as_of_block=25_849_738,
            network_projects_stale=False,
        )
        table = widget.query_one("#fwa-registry-table", DataTable)
        rows = _rows(table)
        assert not rows[0][0].startswith("↳")
        assert rows[1][0].startswith("↳")
        assert not rows[2][0].startswith("↳")
        joined = "\n".join(" ".join(row) for row in rows)
        assert "active rounds 12 rounds" in joined
        assert "owed 2.500 ETH" in joined
        assert "claim 12,345.000 FWA" in joined
        assert "VERIFIED" in joined and "INTEGRITY" in joined
        assert "[/x] hostile detail 海🙂" in joined


async def test_registry_narrow_keeps_all_metric_units_and_widen_marker() -> None:
    widget = FWAEcosystemRegistry()
    async with _Harness(widget).run_test(size=(70, 20)):
        widget.update_data(
            network_project_rows=[_project_row()],
            network_projects_available=True,
            network_projects_as_of_block=10,
            network_projects_stale=False,
        )
        table = widget.query_one("#fwa-registry-table", DataTable)
        assert _headers(table) == ["PROJECT", "PRIMARY", "ETH", "FWA"]
        row = _rows(table)[0]
        assert row[1].endswith("rounds")
        assert row[2].endswith("ETH")
        assert row[3].endswith("FWA")
        assert "widen" in _static_plain(widget, "#fwa-registry-title")


async def test_registry_blank_is_unavailable_not_an_empty_table() -> None:
    widget = FWAEcosystemRegistry()
    async with _Harness(widget).run_test(size=(100, 18)):
        widget.update_data(
            **{
                key: None
                for key in FWA_NETWORK_WIDGET_SIGNATURES["FWAEcosystemRegistry"]
            }
        )
        table = widget.query_one("#fwa-registry-table", DataTable)
        assert "project data unavailable" in " ".join(_rows(table)[0])
        assert "unavailable" in _static_plain(widget, "#fwa-registry-note")
