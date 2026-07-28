"""Activity feed template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and a scrolling RichLog.
De-duplicates events by a composite key.  Newest events appear on top.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_battle_activity.py
  - maxpane_dashboard/widgets/cattown/ct_activity_feed.py

Keep the defensive shape when you copy this (MEDI-37): ``update_data``
calls ``log.clear()`` before it writes, so anything that raises between
those two points leaves the panel blank on every refresh for as long as
the bad event stays in the feed window.  Every field is API-sourced, so
every field is escaped and every formatting step degrades instead of
raising.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static
from maxpane_dashboard.widgets.markup_safety import safe_markup


#: Rendered in place of a line whose event could not be formatted at all.
_MALFORMED_LINE = "  [dim]??:??[/]  [yellow]unreadable event[/]"
#: Rendered when the feed has nothing to show.
_EMPTY_LINE = "[dim]  No activity yet[/]"


def _format_event_time(timestamp: float | int | str) -> str:
    """Convert a unix timestamp to HH:MM display format.

    ``None``, non-numeric text and out-of-range values render ``"??:??"``.
    """
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError, TypeError, OverflowError):
        return "??:??"


def _short_addr(address: str | None) -> str:
    """Shorten a wallet address to 0xABCD..1234 format.

    A missing or non-string address renders empty instead of raising
    ``TypeError`` on ``len()``.
    """
    if not address:
        return ""
    if not isinstance(address, str):
        address = str(address)
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _event_to_markup(event: dict) -> str:
    """Convert an event dict into a Rich-markup formatted line.

    Adapt the dict keys and formatting to your game's event schema, but
    keep the wrapper: an event that cannot be formatted degrades to one
    explicit line so the rest of the feed still renders.
    """
    try:
        return _format_event(event)
    except Exception:
        return _MALFORMED_LINE


def _format_event(event: dict) -> str:
    """Format one event; :func:`_event_to_markup` is the safe wrapper."""
    if not isinstance(event, dict):
        return _MALFORMED_LINE
    # An entry with no action and no detail carries nothing a reader could
    # act on; a timestamped blank line would pass for a real event.
    if not any(event.get(field) for field in ("action", "detail", "display_name")):
        return _MALFORMED_LINE
    ts = _format_event_time(event.get("timestamp", 0))
    who = safe_markup(event.get("display_name", "") or _short_addr(event.get("address", "")))
    action = safe_markup(event.get("action", ""))
    detail = safe_markup(event.get("detail", ""))
    success = event.get("success", True)

    result_icon = "[green]\u2713[/]" if success else "[red]\u2717[/]"
    return f"  [dim]{ts}[/]  [dim]{who}[/]  [cyan]{action}[/] {detail}  {result_icon}"


class GameActivityFeed(Vertical):
    """Auto-scrolling activity feed with recent game events.

    Rename this class (and the CSS selectors) for your game, e.g.
    ``class CTActivityFeed(Vertical):``.
    """

    DEFAULT_CSS = """
    GameActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="feed-title")
        yield RichLog(id="game-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(self, events: list[dict] | None = None) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by a key built from event fields.
        Missing or malformed input renders an explicit state rather than
        raising: nothing may escape this method after ``log.clear()``.
        """
        log = self.query_one("#game-activity-log", RichLog)

        if not events:
            # Only claim "no activity" while nothing has ever been shown --
            # a transient empty poll must not wipe a populated feed.
            if not self._seen_keys:
                # clear() first: without it every empty poll appends another
                # copy of the placeholder, once per refresh interval.
                log.clear()
                log.write(_EMPTY_LINE)
            return

        # De-duplicate
        for event in events:
            try:
                key = (
                    f"{event.get('timestamp', '')}:"
                    f"{event.get('address', '')}:"
                    f"{event.get('action', '')}"
                )
            except Exception:
                continue
            self._seen_keys.add(key)

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        written = 0
        for event in events:
            try:
                log.write(_event_to_markup(event))
                written += 1
            except Exception:
                # A single unwritable line must not truncate the feed.
                continue

        if written == 0:
            log.write(_EMPTY_LINE)

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
