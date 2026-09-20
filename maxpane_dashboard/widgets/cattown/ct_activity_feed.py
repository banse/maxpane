"""Fishing activity feed for Cat Town dashboard.

The log, the dedupe set and the write contract are
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed`'s (Branch 7, WP-A);
``_catch_to_text`` below is this dashboard's ``format_row`` hook, and the
``HH:MM`` cell is ``widgets/fmt.hhmm``. The copy it replaces printed a
**clock time for an epoch-zero stamp** -- ``01:00`` on 1970-01-01, an
unread timestamp looking exactly like data -- and raised ``TypeError`` on a
``None`` one; ``hhmm`` renders ``??:??`` for both, which is what every
other feed in the app already showed.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.cattown._chain import EXPLORER
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.panels import RichLogFeed

#: display budget for the fisher name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. No pin binds this
#: RichLog line; grown by ICON_COLS as in the recipe (PRD §5).
_FISHER_COLS = 12


def _catch_to_text(catch: dict) -> Text:
    """Convert a catch dict into a composited ``Text`` line.

    Built directly with :class:`~rich.text.Text`, never a markup string:
    the fisher's cell carries the copy icon (``widgets/address.py``), whose
    click action lives in a ``Style`` that only survives outside markup
    parsing.
    """
    ts = hhmm(catch.get("timestamp", 0))
    display_name = catch.get("display_name", "")
    fisher = address_text(
        catch.get("fisher_address", ""),
        label=display_name or None,
        width=_FISHER_COLS,
        style="dim",
        explorer=EXPLORER,
    )
    species = str(catch.get("species", "Unknown") or "Unknown")
    weight = catch.get("weight_kg", 0.0)
    event_type = catch.get("rarity", "fish")

    line = Text()
    line.append(f"  {ts}  ", style="dim")
    line.append_text(fisher)
    line.append("  ")
    if event_type == "treasure":
        line.append(f"Found {species}", style="yellow")
    else:
        # Fish: show weight in kg
        line.append(f"Caught {species} ({weight:.1f}kg)", style="cyan")
    return line


class CTActivityFeed(RichLogFeed):
    """Auto-scrolling fishing activity feed."""

    TITLE = "FISHING ACTIVITY"

    LOG_ID = "ct-activity-log"

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    CTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    #: The ``format_row`` hook. A ``staticmethod``: the row is a function of
    #: the catch alone.
    format_row = staticmethod(_catch_to_text)

    def update_data(
        self,
        recent_catches: list[dict] | None = None,
    ) -> None:
        """Rewrite the log with newest catches on top.

        Catches are de-duplicated by ``tx_hash`` (``RichLogFeed.dedupe_key``).
        """
        self.render_events(recent_catches)
