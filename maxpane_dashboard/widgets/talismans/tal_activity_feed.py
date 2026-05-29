"""Activity feed for the Talismans dashboard.

Renders the most recent operations (newest-first) in a ``RichLog``.  Four
operation types are formatted with a per-type color tag:

* ``"bond"``   -> violet BOND  (forges a Mythic from two inputs).
* ``"cleave"`` -> cyan   CLEAVE.
* ``"cut"``    -> amber  CUT.
* ``"merge"``  -> green  MERGE.

Every formatter is exception-safe: missing or malformed fields collapse
to dashes rather than crashing the RichLog write.

Copied from ``ttt_activity_feed.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

_DASH = "--"

_OP_COLORS = {
    "bond": "#8a6fd6",
    "cleave": "cyan",
    "cut": "#f59e0b",
    "merge": "green",
}


# -- helpers -----------------------------------------------------------


def _format_event_time(timestamp) -> str:
    """``HH:MM`` from unix seconds; falls back to ``??:??``."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError):
        return "??:??"


def _safe_get(event: dict, key: str, default=None):
    if not isinstance(event, dict):
        return default
    return event.get(key, default)


def _id_str(value) -> str:
    if value is None:
        return _DASH
    try:
        return str(int(value))
    except (TypeError, ValueError):
        s = str(value).strip()
        return s if s else _DASH


# -- per-type formatters ----------------------------------------------


def _fmt_bond(event: dict, ts: str) -> str:
    a = _id_str(_safe_get(event, "token_id_a"))
    b = _id_str(_safe_get(event, "token_id_b"))
    result = _id_str(_safe_get(event, "result_id"))
    color = _OP_COLORS["bond"]
    return (
        f"{ts} [{color}]BOND  [/] #{a} + #{b} → #{result} · Mythic"
    )


def _fmt_cleave(event: dict, ts: str) -> str:
    a = _id_str(_safe_get(event, "token_id_a"))
    result = _id_str(_safe_get(event, "result_id"))
    color = _OP_COLORS["cleave"]
    return f"{ts} [{color}]CLEAVE[/] #{a} → #{result}"


def _fmt_cut(event: dict, ts: str) -> str:
    a = _id_str(_safe_get(event, "token_id_a"))
    result = _id_str(_safe_get(event, "result_id"))
    color = _OP_COLORS["cut"]
    return f"{ts} [{color}]CUT   [/] #{a} → #{result}"


def _fmt_merge(event: dict, ts: str) -> str:
    a = _id_str(_safe_get(event, "token_id_a"))
    b = _id_str(_safe_get(event, "token_id_b"))
    result = _id_str(_safe_get(event, "result_id"))
    color = _OP_COLORS["merge"]
    return f"{ts} [{color}]MERGE [/] #{a} + #{b} → #{result}"


def _event_to_markup(event: dict) -> str | None:
    """Format one activity event; ``None`` to skip malformed input."""
    if not isinstance(event, dict):
        return None
    ts = _format_event_time(event.get("timestamp"))
    op_type = (event.get("op_type") or "").lower()

    try:
        if op_type == "bond":
            return _fmt_bond(event, ts)
        if op_type == "cleave":
            return _fmt_cleave(event, ts)
        if op_type == "cut":
            return _fmt_cut(event, ts)
        if op_type == "merge":
            return _fmt_merge(event, ts)
    except Exception:
        # Never let a single malformed event take down the whole panel.
        return None
    # Unknown type -- render a generic dim row rather than skipping.
    return f"{ts} [dim]{op_type.upper():<6}[/] [dim]--[/]"


# -- widget ------------------------------------------------------------


class TalismansActivityFeed(Vertical):
    """Auto-scrolling activity feed for Talismans operations."""

    DEFAULT_CSS = """
    TalismansActivityFeed > .tal-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="tal-feed-title")
        yield Static(" ", classes="tal-feed-spacer")
        yield RichLog(
            id="tal-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(
        self,
        activity_events=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with the supplied events (newest-first).

        The widget rewrites the log on every refresh -- simpler than
        incremental diffing and fast enough for the row cap.
        """
        log = self.query_one("#tal-activity-log", RichLog)
        events = activity_events or []
        log.clear()

        if not events:
            log.write("[dim]  No activity yet[/]")
            return

        try:
            iterator = list(events)[:25]
        except TypeError:
            log.write("[dim]  No activity yet[/]")
            return

        log.auto_scroll = False
        for event in iterator:
            line = _event_to_markup(event)
            if line is not None:
                log.write(line)

        self.call_after_refresh(log.scroll_home, animate=False)
