"""Scrolling activity feed showing recent game events."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.data.models import ActivityEvent
from maxpane_dashboard.widgets.markup_safety import safe_markup


#: Rendered in place of a line whose event could not be formatted at all.
_MALFORMED_LINE = "  [dim]??:??[/]  [yellow]unreadable event[/]"
#: Rendered when the feed has nothing to show.
_EMPTY_LINE = "[dim]  No activity yet[/]"


def _format_event_time(timestamp_str: str) -> str:
    """Convert a unix timestamp string to HH:MM display format.

    ``None``, non-numeric text and out-of-range values render ``"??:??"``
    rather than raising: this runs on API-sourced data, and a raise here
    propagates out of ``update_data`` after ``log.clear()`` has already
    run, leaving the panel blank (MEDI-37).
    """
    try:
        ts = int(timestamp_str)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError, TypeError, OverflowError):
        return "??:??"


def _short_addr(address: str | None) -> str:
    """Shorten a wallet address to 0xabcd...ef12 format.

    ``None`` -- a game-generated random event with no launcher -- renders
    as "the bakery" rather than raising, so one such event cannot blank
    the whole feed.  A non-string launcher is coerced rather than handed
    to ``len()``.
    """
    if not address:
        return "the bakery"
    if not isinstance(address, str):
        address = str(address)
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _event_to_markup(event: ActivityEvent) -> str:
    """Convert an ActivityEvent into a Rich-markup formatted line.

    Never raises.  Fields are read defensively -- a payload change or a
    partially-validated model can leave any of them missing or ``None`` --
    and an event that still cannot be formatted degrades to a single
    explicit "unreadable event" line so the rest of the feed survives.
    """
    try:
        return _format_event(event)
    except Exception:
        return _MALFORMED_LINE


def _format_event(event: ActivityEvent) -> str:
    """Format one event; :func:`_event_to_markup` is the safe wrapper."""
    # An entry with no type, no title and no description carries nothing a
    # reader could act on. Rendering it as a timestamped blank line would
    # pass for a real event; say it is unreadable instead.
    if not any(
        getattr(event, field, None)
        for field in ("type", "title", "description")
    ):
        return _MALFORMED_LINE

    ts = _format_event_time(getattr(event, "timestamp", None))
    who = safe_markup(_short_addr(getattr(event, "launcher", None)))

    # title / description / linked_bakery_name are all API-sourced and can
    # contain player-chosen bakery names. RichLog(markup=True) defers
    # Text.from_markup to on_resize, so unescaped markup here crashes the app
    # from inside the message pump, not at the write() call site.
    title = safe_markup(getattr(event, "title", None))
    description = safe_markup(getattr(event, "description", None))
    event_type = getattr(event, "type", None)

    if event_type == "simple":
        # Join/leave — title has the action, description is empty
        return f"  [dim]{ts}[/]  [cyan]{who} {title}[/]"
    elif event_type == "rug":
        # Attack/boost — combine title (boost name) + description + linked bakery
        target = safe_markup(getattr(event, "linked_bakery_name", None) or "")
        if getattr(event, "success", None):
            if getattr(event, "is_outgoing", None):
                desc = f"{title}: {description} {target}"
            else:
                desc = f"{title}: {description} {target}"
            return f"  [dim]{ts}[/]  {desc}  [green]\u2713[/]"
        else:
            if getattr(event, "is_outgoing", None):
                desc = f"{title}: Failed on {target}"
            else:
                desc = f"{title}: {description} {target}"
            return f"  [dim]{ts}[/]  {desc}  [red]\u2717[/]"
    else:
        return f"  [dim]{ts}[/]  {who} {title or description}"


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

    def update_data(self, events: list[ActivityEvent] | None) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by a key composed of
        ``(timestamp, launcher, type, description)``.

        Missing or malformed input renders an explicit state instead of
        raising (MEDI-37).  ``None``/empty shows "No activity yet"; an
        event that cannot be formatted shows "unreadable event" on its own
        line and the surrounding events still render.  Nothing here may
        raise: ``log.clear()`` has already run by the time the events are
        written, so an exception escaping this method leaves the panel
        blank until the offending event ages out of the feed window.
        """
        log = self.query_one("#activity-log", RichLog)

        if not events:
            # Only claim "no activity" while nothing has ever been shown --
            # a transient empty poll must not wipe a populated feed.
            if not self._seen_keys:
                # clear() first: without it every empty poll appends another
                # copy of the placeholder, once per refresh interval.
                log.clear()
                log.write(_EMPTY_LINE)
            return

        # Track all events, newest first (events arrive newest-first)
        new_keys = set()
        for event in events:
            try:
                key = (
                    f"{getattr(event, 'timestamp', None)}:"
                    f"{getattr(event, 'launcher', None)}:"
                    f"{getattr(event, 'type', None)}:"
                    f"{getattr(event, 'description', None)}"
                )
            except Exception:
                continue
            new_keys.add(key)
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
