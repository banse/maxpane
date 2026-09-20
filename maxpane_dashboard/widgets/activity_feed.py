"""Scrolling activity feed showing recent game events.

On ``widgets/panels.py`` since Branch 8 WP-B: a
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed` in stream mode,
keyed on the copy's four fields (timestamp, launcher, type, description).
The event formatting below is unchanged from the copy: it is built as a
``rich.text.Text`` because the launcher carries the copy icon
(``widgets/address.py``), whose click action lives in a ``Style`` that only
survives outside markup parsing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.panels import RichLogFeed

if TYPE_CHECKING:
    from maxpane_dashboard.data.models import ActivityEvent


#: Rendered in place of a line whose event could not be formatted at all.
_MALFORMED_LINE = "  [dim]??:??[/]  [yellow]unreadable event[/]"
#: Display budget for the launcher address in this RichLog line, excluding
#: the icon (``ICON_COLS``). No layout pin covers this hidden dashboard, so
#: this is a grow-in-slack choice matching the recipe's own RichLog example.
_WHO_COLS = 17


def _who_text(launcher: object, *, width: int) -> Text:
    """The launcher's address, iconed, or "the bakery" for a random event.

    No launcher -- ``None`` for a game-generated random event, or an empty
    string -- renders as "the bakery" rather than an address, so one such
    event cannot blank the whole feed. A non-string launcher is coerced rather than handed to
    :func:`~maxpane_dashboard.widgets.address.is_address`, which would
    simply reject it and render it as inert text anyway.
    """
    if not launcher:
        return Text("the bakery", style="dim")
    if not isinstance(launcher, str):
        launcher = str(launcher)
    # No ``explorer=``: Bakery runs on Abstract (``data/client.py`` reads
    # ``agent.json``; ``tests/data/test_client.py`` pins ``chainId`` 2741,
    # explorer ``abscan.org``), which ``widgets/explorer.py`` does not allowlist.
    # An unknown chain gets no link, never a guessed one (rules/widgets.md).
    return address_text(launcher, width=width, style="dim")


def _event_to_text(event: ActivityEvent) -> Text:
    """Convert an ActivityEvent into a composited Rich ``Text`` line.

    Never raises.  Fields are read defensively -- a payload change or a
    partially-validated model can leave any of them missing or ``None`` --
    and an event that still cannot be formatted degrades to a single
    explicit "unreadable event" line so the rest of the feed survives.

    Built directly with :class:`~rich.text.Text` rather than a markup
    string: the launcher carries the copy icon (``widgets/address.py``),
    whose click action lives in a ``Style`` that only survives outside
    markup parsing. Every other field is inserted as literal text through
    ``Text.append`` -- which never parses ``"["`` as a tag -- so it needs
    no ``safe_markup`` escaping; escaping it here would print the escape
    backslashes literally instead of hiding them.
    """
    try:
        return _format_event(event)
    except Exception:
        return Text.from_markup(_MALFORMED_LINE)


def _format_event(event: ActivityEvent) -> Text:
    """Format one event; :func:`_event_to_text` is the safe wrapper."""
    # An entry with no type, no title and no description carries nothing a
    # reader could act on. Rendering it as a timestamped blank line would
    # pass for a real event; say it is unreadable instead.
    if not any(
        getattr(event, field, None)
        for field in ("type", "title", "description")
    ):
        return Text.from_markup(_MALFORMED_LINE)

    # ``fmt.hhmm``: ``None``, non-numeric text and out-of-range values render
    # ``??:??`` rather than raising (MEDI-37), and so does a non-positive
    # stamp -- the API's epoch seconds are never zero.
    ts = hhmm(getattr(event, "timestamp", None))
    who = _who_text(getattr(event, "launcher", None), width=_WHO_COLS)

    title = str(getattr(event, "title", None) or "")
    description = str(getattr(event, "description", None) or "")
    event_type = getattr(event, "type", None)

    line = Text()
    line.append(f"  {ts}  ", style="dim")

    if event_type == "simple":
        # Join/leave — title has the action, description is empty
        line.append_text(who)
        line.append(f" {title}", style="cyan")
    elif event_type == "rug":
        # Attack/boost — combine title (boost name) + description + linked bakery
        target = str(getattr(event, "linked_bakery_name", None) or "")
        if getattr(event, "success", None):
            desc = f"{title}: {description} {target}"
            line.append(f"{desc}  ")
            line.append("✓", style="green")
        else:
            if getattr(event, "is_outgoing", None):
                desc = f"{title}: Failed on {target}"
            else:
                desc = f"{title}: {description} {target}"
            line.append(f"{desc}  ")
            line.append("✗", style="red")
    else:
        line.append_text(who)
        line.append(f" {title or description}")
    return line


class ActivityFeed(RichLogFeed):
    """Auto-scrolling activity feed with recent game events."""

    TITLE = "ACTIVITY"
    LOG_ID = "activity-log"

    # Geometry only: the title's colour and blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    ActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def dedupe_key(self, event) -> str:
        """The copy's key: ``timestamp:launcher:type:description``."""
        return (
            f"{getattr(event, 'timestamp', None)}:"
            f"{getattr(event, 'launcher', None)}:"
            f"{getattr(event, 'type', None)}:"
            f"{getattr(event, 'description', None)}"
        )

    def format_row(self, event) -> Text:
        return _event_to_text(event)

    def update_data(self, events: list[ActivityEvent] | None) -> None:
        """Rewrite the log with newest events on top.

        The contract is :meth:`RichLogFeed.render_events`' stream mode:
        ``None``/empty shows "No activity yet" only while nothing has ever
        been shown, an event that cannot be formatted shows "unreadable
        event" on its own line and the surrounding events still render, and
        nothing here may raise (MEDI-37).
        """
        self.render_events(events)
