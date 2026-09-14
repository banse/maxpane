"""Activity feed template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and a scrolling RichLog.
De-duplicates events by a composite key.  Newest events appear on top.

**The blank row under the title is not optional.**  Every panel title in
this repo is followed by one blank row (``margin: 0 0 1 0`` on the title's
own class), so a panel is separated from whatever sits above it.  Keep that
rule when you copy this file.  On 2026-09-12 a survey found 36 panel titles
across the app missing it and **all six of these templates** missing it too,
which is how it spread: a defect in a copy-source is a defect in every
dashboard not yet written.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_battle_activity.py
  - maxpane_dashboard/widgets/cattown/ct_activity_feed.py

Keep the defensive shape when you copy this (MEDI-37): ``update_data``
calls ``log.clear()`` before it writes, so anything that raises between
those two points leaves the panel blank on every refresh for as long as
the bad event stays in the feed window.  Every field is API-sourced, so
every field is escaped and every formatting step degrades instead of
raising.

Every displayed 0x address -- and every name that stands in for one -- goes
through ``widgets/address.py`` and carries the copy icon. That is a repo rule,
not a style: tests/test_address_rule.py fails on a private address formatter
and tests/screens/test_address_icons_everywhere.py fails on an address that
reaches the screen without its icon. Copy this, keep the import.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static
from maxpane_dashboard.widgets.address import address_text


#: Rendered in place of a line whose event could not be formatted at all.
_MALFORMED_LINE = "  [dim]??:??[/]  [yellow]unreadable event[/]"
#: Rendered when the feed has nothing to show.
_EMPTY_LINE = "[dim]  No activity yet[/]"
#: Display budget for the address, excluding the icon (``ICON_COLS``).
#: Matches the two real activity-feed conversions this template was copied
#: alongside (``widgets/ocm/ocm_activity_feed.py``, ``widgets/activity_feed.py``).
WHO_COLS = 17


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


def _event_to_text(event: dict) -> Text:
    """Convert an event dict into a composited Rich ``Text`` line.

    Adapt the dict keys and formatting to your game's event schema, but
    keep the wrapper: an event that cannot be formatted degrades to one
    explicit line so the rest of the feed still renders.

    Built directly with :class:`~rich.text.Text`, never a markup string:
    the address carries the copy icon (``widgets/address.py``), whose click
    action lives in a ``Style`` that only survives outside markup parsing.
    Every other field is inserted as literal text through ``Text.append`` --
    which never parses ``"["`` as a tag -- so ``safe_markup`` is neither
    needed nor safe to use here: escaping it would print the escape
    backslashes literally instead of hiding them.
    """
    try:
        return _format_event(event)
    except Exception:
        return Text.from_markup(_MALFORMED_LINE)


def _format_event(event: dict) -> Text:
    """Format one event; :func:`_event_to_text` is the safe wrapper."""
    if not isinstance(event, dict):
        return Text.from_markup(_MALFORMED_LINE)
    # An entry with no action and no detail carries nothing a reader could
    # act on; a timestamped blank line would pass for a real event.
    if not any(event.get(field) for field in ("action", "detail", "display_name")):
        return Text.from_markup(_MALFORMED_LINE)
    ts = _format_event_time(event.get("timestamp", 0))
    # A display name stands in for the address when one is set; the icon
    # still copies the address either way. A missing/non-string address
    # renders the "--" placeholder instead of raising.
    who = address_text(
        event.get("address"),
        label=event.get("display_name") or None,
        width=WHO_COLS,
        style="dim",
    )
    action = str(event.get("action", ""))
    detail = str(event.get("detail", ""))
    success = event.get("success", True)

    line = Text()
    line.append(f"  {ts}  ", style="dim")
    line.append_text(who)
    line.append("  ")
    line.append(action, style="cyan")
    line.append(f" {detail}  ")
    line.append("\u2713" if success else "\u2717", style="green" if success else "red")
    return line


class GameActivityFeed(Vertical):
    """Auto-scrolling activity feed with recent game events.

    Rename this class (and the CSS selectors) for your game, e.g.
    ``class CTActivityFeed(Vertical):``.
    """

    DEFAULT_CSS = """
    /* `margin: 0 0 1 0` IS THE BLANK ROW UNDER THE TITLE and it is
       mandatory -- see the module docstring. Do not drop it when you adapt
       the selector name. */
    GameActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
        margin: 0 0 1 0;
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
                log.write(_event_to_text(event))
                written += 1
            except Exception:
                # A single unwritable line must not truncate the feed.
                continue

        if written == 0:
            log.write(_EMPTY_LINE)

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
