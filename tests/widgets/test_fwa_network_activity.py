"""Headless tests for the ecosystem-wide NETWORK activity feed."""

from __future__ import annotations

import ast
import inspect

from rich.cells import cell_len
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from maxpane_dashboard.data.fwa_ecosystem_models import FWA_NETWORK_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa import fwa_network_activity as module
from maxpane_dashboard.widgets.fwa.fwa_network_activity import (
    LAST_GOOD_LINE,
    QUIET_LINE,
    UNAVAILABLE_LINE,
    FWANetworkActivity,
)


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _event(**changes) -> dict:
    event = {
        "event_id": "0xabc:4",
        "ts": 1_784_899_880,
        "tx_hash": "0x" + "ab" * 32,
        "log_index": 4,
        "origin": "PullPool",
        "family": "pullpool",
        "version": "v2",
        "event_key": "ticket_bought",
        "event_label": "Ticket bought",
        "eth_amount": 0.125,
        "fwa_amount": 1_234.5,
        "detail": "round 17",
        "source_kind": "chain_log",
        "measurement": "measured",
        "block_number": 25_849_700,
        "observed_at": 1_784_900_000.0,
        "stale": False,
        "verified_source": True,
        "integrity": "ok",
    }
    event.update(changes)
    return event


def _log(widget: FWANetworkActivity) -> RichLog:
    return widget.query_one("#fwa-network-activity-log", RichLog)


def _log_text(widget: FWANetworkActivity) -> str:
    return "\n".join(strip.text for strip in _log(widget).lines)


def _title(widget: FWANetworkActivity) -> str:
    visual = widget.query_one("#fwa-network-feed-title", Static).visual
    return getattr(visual, "plain", str(visual))


def test_network_activity_signature_is_exact_and_keyword_only() -> None:
    signature = inspect.signature(FWANetworkActivity.update_data)
    names = tuple(name for name in signature.parameters if name != "self")
    assert names == FWA_NETWORK_WIDGET_SIGNATURES["FWANetworkActivity"]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for name, parameter in signature.parameters.items()
        if name != "self"
    )


async def test_network_activity_full_retains_source_version_amounts_and_dedupes() -> None:
    widget = FWANetworkActivity()
    events = [
        _event(),
        _event(event_label="duplicate must disappear"),
        _event(
            event_id="0xdef:9",
            origin="FWAIR",
            family="fwair",
            version="launch-2",
            event_label="Collection supported",
            eth_amount=4.5,
            fwa_amount=None,
        ),
    ]
    async with _Harness(widget).run_test(size=(150, 18)):
        widget.update_data(
            network_events=events,
            network_feed_available=True,
            network_feed_unavailable_reason=None,
            network_feed_as_of_ts=1_784_900_000,
        )
        text = _log_text(widget)
        assert "PullPool/v2" in text
        assert "FWAIR/launch-2" in text
        assert "0.1250 ETH" in text and "1,234.50 FWA" in text
        assert "duplicate must disappear" not in text
        assert text.count("Ticket bought") == 1
        assert _log(widget).wrap is False


async def test_network_activity_distinguishes_quiet_unavailable_and_last_good() -> None:
    widget = FWANetworkActivity()
    async with _Harness(widget).run_test(size=(100, 18)):
        widget.update_data(
            network_events=[],
            network_feed_available=True,
            network_feed_unavailable_reason=None,
            network_feed_as_of_ts=1_784_900_000,
        )
        assert QUIET_LINE in _log_text(widget)

        widget.update_data(
            network_events=None,
            network_feed_available=False,
            network_feed_unavailable_reason="RPC page timed out",
            network_feed_as_of_ts=None,
        )
        text = _log_text(widget)
        assert UNAVAILABLE_LINE in text
        assert "RPC page timed out" in text
        assert "no last-good activity" in text

        widget.update_data(
            network_events=[_event()],
            network_feed_available=True,
            network_feed_unavailable_reason=None,
            network_feed_as_of_ts=1_784_900_000,
        )
        widget.update_data(
            network_events=None,
            network_feed_available=False,
            network_feed_unavailable_reason="logs down",
            network_feed_as_of_ts=None,
        )
        text = _log_text(widget)
        assert UNAVAILABLE_LINE in text and LAST_GOOD_LINE in text
        assert "as of t1,784,900,000" in text
        assert "Ticket bought" in text


async def test_network_activity_accepts_cache_rows_on_a_fresh_unavailable_widget() -> None:
    widget = FWANetworkActivity()
    async with _Harness(widget).run_test(size=(100, 18)):
        widget.update_data(
            network_events=[_event()],
            network_feed_available=False,
            network_feed_unavailable_reason="live logs unavailable",
            network_feed_as_of_ts=1_784_900_000,
        )
        text = _log_text(widget)
        assert LAST_GOOD_LINE in text and "Ticket bought" in text


async def test_network_activity_hostile_wide_text_is_literal_fitted_and_announced() -> None:
    widget = FWANetworkActivity()
    hostile = _event(
        origin="[/x]海🙂",
        family="[red]项目[/]",
        version="版本🙂",
        event_label="[bold]中奖🙂海豚[/]" * 4,
        detail="[/x]" * 20,
        eth_amount=10**80,
        fwa_amount=10**90,
    )
    async with _Harness(widget).run_test(size=(52, 16)):
        widget.update_data(
            network_events=[hostile],
            network_feed_available=True,
            network_feed_unavailable_reason=None,
            network_feed_as_of_ts=1_784_900_000,
        )
        log = _log(widget)
        text = _log_text(widget)
        assert "[/x]" in text or "[red]" in text
        assert "widen" in _title(widget) or "widen" in text
        assert all(cell_len(strip.text) <= log.content_size.width for strip in log.lines)


async def test_network_activity_blank_payload_is_safe() -> None:
    widget = FWANetworkActivity()
    async with _Harness(widget).run_test(size=(80, 16)):
        widget.update_data(
            **{
                key: None
                for key in FWA_NETWORK_WIDGET_SIGNATURES["FWANetworkActivity"]
            }
        )
        assert UNAVAILABLE_LINE in _log_text(widget)


def test_network_activity_imports_no_data_io_or_clock_modules() -> None:
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
