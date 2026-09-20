"""Activity feed for Onchain Monsters dashboard.

The log, the dedupe set and the write contract are
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed`'s (Branch 6);
``_event_to_text`` below is this dashboard's ``format_row`` hook, and the
``HH:MM`` cell is ``widgets/fmt.hhmm``.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.ocm._chain import EXPLORER
from maxpane_dashboard.widgets.panels import RichLogFeed

#: Display budget for the actor address in this RichLog line, excluding the
#: icon (``ICON_COLS``). No layout pin covers this hidden dashboard, so this
#: is a grow-in-slack choice matching the recipe's own RichLog example.
_ADDR_COLS = 17


def _event_to_text(event: dict) -> Text:
    """Convert an event dict into a composited Rich ``Text`` line.

    Built directly with :class:`~rich.text.Text`, never a markup string:
    the actor address carries the copy icon (``widgets/address.py``), whose
    click action lives in a ``Style`` that only survives outside markup
    parsing.
    """
    ts = hhmm(event.get("timestamp", 0))
    address = event.get("actor_address", "")
    event_type = event.get("event_type", "")
    token_id = event.get("token_id")
    count = event.get("count", 0)

    line = Text(f"  {ts}  ")
    addr = address_text(address, width=_ADDR_COLS, explorer=EXPLORER)

    if event_type == "mint":
        line.append("MINT     ", style="green")
        line.append_text(addr)
        line.append(f"  Minted Monster #{token_id}")
    elif event_type == "burn":
        line.append("BURN     ", style="red")
        line.append_text(addr)
        line.append(f"  Sacrificed Monster #{token_id}")
    elif event_type == "stake":
        line.append("STAKE    ", style="cyan")
        line.append_text(addr)
        line.append(f"  Staked {count} monster(s)")
    elif event_type == "unstake":
        line.append("UNSTAKE  ", style="yellow")
        line.append_text(addr)
        line.append(f"  Unstaked {count} monster(s)")
    else:
        line.append(f"{str(event_type).upper()}  ", style="dim")
        line.append_text(addr)
        line.append(f"  {event_type}")
    return line


class OCMActivityFeed(RichLogFeed):
    """Auto-scrolling activity feed for Onchain Monsters."""

    TITLE = "ACTIVITY"

    LOG_ID = "ocm-activity-log"

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    OCMActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    #: The ``format_row`` hook. A ``staticmethod``: the row is a function of
    #: the event alone.
    format_row = staticmethod(_event_to_text)

    def update_data(
        self,
        recent_events: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by ``tx_hash`` (``RichLogFeed.dedupe_key``).
        """
        self.render_events(recent_events)
