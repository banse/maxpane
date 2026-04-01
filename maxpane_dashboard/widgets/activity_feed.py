"""Scrolling activity feed showing recent game events."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.data.models import ActivityEvent


def _format_event_time(timestamp_str: str) -> str:
    """Convert a unix timestamp string to HH:MM display format."""
    try:
        ts = int(timestamp_str)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xabcd...ef12 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _event_to_markup(event: ActivityEvent) -> str:
    """Convert an ActivityEvent into a Rich-markup formatted line."""
    ts = _format_event_time(event.timestamp)
    who = _short_addr(event.launcher)

    if event.type == "simple":
        # Join/leave — title has the action, description is empty
        return f"  [dim]{ts}[/]  [cyan]{who} {event.title}[/]"
    elif event.type == "rug":
        # Attack/boost — combine title (boost name) + description + linked bakery
        target = event.linked_bakery_name or ""
        if event.success:
            if event.is_outgoing:
                desc = f"{event.title}: {event.description} {target}"
            else:
                desc = f"{event.title}: {event.description} {target}"
            return f"  [dim]{ts}[/]  {desc}  [green]\u2713[/]"
        else:
            if event.is_outgoing:
                desc = f"{event.title}: Failed on {target}"
            else:
                desc = f"{event.title}: {event.description} {target}"
            return f"  [dim]{ts}[/]  {desc}  [red]\u2717[/]"
    else:
        return f"  [dim]{ts}[/]  {who} {event.title or event.description}"


class ActivityFeed(Vertical):
    """Auto-scrolling activity feed with recent game events."""

    DEFAULT_CSS = """
    ActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    ActivityFeed > RichLog {
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
        yield RichLog(id="activity-log", wrap=True, highlight=True, markup=True)

    def update_data(self, events: list[ActivityEvent]) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by a key composed of
        ``(timestamp, launcher, type, description)``.
        """
        log = self.query_one("#activity-log", RichLog)

        if not events:
            if not self._seen_keys:
                log.write("[dim]  No activity yet[/]")
            return

        # Track all events, newest first (events arrive newest-first)
        new_keys = set()
        for event in events:
            key = f"{event.timestamp}:{event.launcher}:{event.type}:{event.description}"
            new_keys.add(key)
            self._seen_keys.add(key)

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        for event in events:
            log.write(_event_to_markup(event))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
