"""Headless tests for the semantic FWA value-flow rail."""

from __future__ import annotations

import ast
import inspect

from rich.cells import cell_len
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from maxpane_dashboard.data.fwa_ecosystem_models import FWA_NETWORK_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa import fwa_flow_rail as module
from maxpane_dashboard.widgets.fwa.fwa_flow_rail import FWAFlowRail


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _log_text(widget: FWAFlowRail) -> str:
    log = widget.query_one("#fwa-flow-log", RichLog)
    return "\n".join(strip.text for strip in log.lines)


def _title(widget: FWAFlowRail) -> str:
    visual = widget.query_one("#fwa-flow-title", Static).visual
    return getattr(visual, "plain", str(visual))


def _row(**changes) -> dict:
    row = {
        "key": "buyback_gross_eth",
        "label": "Buyback gross",
        "value": 1.25,
        "unit": "eth",
        "configured_bps": None,
        "state": "executed",
        "direction": "in",
        "detail": "gross before caller reward",
        "tx_hash": "0xabc",
        "source_kind": "chain_log",
        "measurement": "measured",
        "block_number": 25_849_700,
        "observed_at": 1_784_900_000.0,
        "stale": False,
        "verified_source": True,
        "integrity": "ok",
    }
    row.update(changes)
    return row


def test_flow_signature_is_exact_and_keyword_only() -> None:
    signature = inspect.signature(FWAFlowRail.update_data)
    names = tuple(name for name in signature.parameters if name != "self")
    assert names == FWA_NETWORK_WIDGET_SIGNATURES["FWAFlowRail"]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for name, parameter in signature.parameters.items()
        if name != "self"
    )


async def test_flow_blank_payload_is_explicitly_unavailable() -> None:
    widget = FWAFlowRail()
    async with _Harness(widget).run_test(size=(90, 20)):
        widget.update_data(
            **{key: None for key in FWA_NETWORK_WIDGET_SIGNATURES["FWAFlowRail"]}
        )
        text = _log_text(widget)
        assert "value flow unavailable" in text
        assert "no last-good flow snapshot" in text
        assert "history n/a" in widget.query_one("#fwa-flow-note", Static).visual.plain


async def test_flow_renders_observed_execution_and_mutated_bps() -> None:
    widget = FWAFlowRail()
    rows = [
        _row(direction="in", label="ETH inflow"),
        _row(
            key="settlement_payout",
            label="Settlement payout",
            value=8_750,
            unit="bps",
            configured_bps=8_750,
            direction="out",
        ),
        _row(
            key="crown_share",
            label="Crown share",
            value=75,
            unit="bps",
            configured_bps=75,
            direction="branch",
        ),
        _row(
            key="fwa_bought",
            label="FWA bought",
            value=12_345.5,
            unit="fwa",
            direction="state",
        ),
    ]
    async with _Harness(widget).run_test(size=(150, 24)):
        widget.update_data(
            network_flow_rows=rows,
            network_flow_available=True,
            network_flow_history_complete=True,
            network_flow_as_of_block=25_849_738,
            network_flow_as_of_ts=1_784_900_000,
            network_flow_stale=False,
        )
        text = _log_text(widget)
        assert "ETH  >  BUYBACK  >  FWA" in text
        assert "IN  >" in text and "OUT <" in text
        assert "BR +>" in text and "ST  =" in text
        assert "obs 87.50%" in text and "cfg 87.50%" in text
        assert "obs 0.75%" in text and "cfg 0.75%" in text
        assert "history complete" in widget.query_one("#fwa-flow-note", Static).visual.plain


async def test_flow_stale_integrity_and_hostile_text_are_visible() -> None:
    widget = FWAFlowRail()
    rows = [
        _row(
            label="海豚🙂 [red]route[/]",
            detail="[/x] mismatch from 链🙂",
            integrity="mismatch",
            verified_source=False,
            stale=True,
        )
    ]
    async with _Harness(widget).run_test(size=(130, 18)):
        widget.update_data(
            network_flow_rows=rows,
            network_flow_available=False,
            network_flow_history_complete=False,
            network_flow_as_of_block=12,
            network_flow_as_of_ts=1_000,
            network_flow_stale=True,
        )
        text = _log_text(widget)
        note = widget.query_one("#fwa-flow-note", Static).visual.plain
        assert "showing labelled last-good rows" in text
        assert "[red]route[/]" in text
        assert "[/x] mismatch" in text
        assert "! mismatch" in text and "unverified" in text
        assert "STALE" in note and "history partial" in note and "INTEGRITY 1" in note


async def test_flow_narrow_lines_fit_and_announce_shed_fields() -> None:
    widget = FWAFlowRail()
    async with _Harness(widget).run_test(size=(46, 18)):
        widget.update_data(
            network_flow_rows=[_row(detail="a deliberately long detail " * 3)],
            network_flow_available=True,
            network_flow_history_complete=True,
        )
        log = widget.query_one("#fwa-flow-log", RichLog)
        assert "widen" in _title(widget) or "widen" in _log_text(widget)
        assert all(cell_len(strip.text) <= log.content_size.width for strip in log.lines)


def test_flow_widget_imports_no_data_io_or_clock_modules() -> None:
    tree = ast.parse(inspect.getsource(module))
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden = ("maxpane_dashboard.data", "analytics", "httpx", "aiohttp", "time", "datetime")
    assert not any(name.startswith(forbidden) for name in imports)
