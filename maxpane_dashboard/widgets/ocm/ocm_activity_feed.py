"""Activity feed for Onchain Monsters dashboard."""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.address import address_text

#: Display budget for the actor address in this RichLog line, excluding the
#: icon (``ICON_COLS``). No layout pin covers this hidden dashboard, so this
#: is a grow-in-slack choice matching the recipe's own RichLog example.
_ADDR_COLS = 17


def _format_event_time(timestamp: float | int | str) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _event_to_text(event: dict) -> Text:
    """Convert an event dict into a composited Rich ``Text`` line.

    Built directly with :class:`~rich.text.Text`, never a markup string:
    the actor address carries the copy icon (``widgets/address.py``), whose
    click action lives in a ``Style`` that only survives outside markup
    parsing.
    """
    ts = _format_event_time(event.get("timestamp", 0))
    address = event.get("actor_address", "")
    event_type = event.get("event_type", "")
    token_id = event.get("token_id")
    count = event.get("count", 0)

    line = Text(f"  {ts}  ")
    addr = address_text(address, width=_ADDR_COLS)

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


class OCMActivityFeed(Vertical):
    """Auto-scrolling activity feed for Onchain Monsters."""

    DEFAULT_CSS = """
    OCMActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OCMActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_tx_hashes: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="feed-title")
        yield RichLog(id="ocm-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(
        self,
        recent_events: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with newest events on top.

        Events are de-duplicated by ``tx_hash``.
        """
        log = self.query_one("#ocm-activity-log", RichLog)

        if not recent_events:
            if not self._seen_tx_hashes:
                log.write("[dim]  No activity yet[/]")
            return

        # De-duplicate by tx_hash
        new_events: list[dict] = []
        for event in recent_events:
            tx_hash = event.get("tx_hash", "")
            if tx_hash and tx_hash in self._seen_tx_hashes:
                continue
            if tx_hash:
                self._seen_tx_hashes.add(tx_hash)
            new_events.append(event)

        if not new_events and self._seen_tx_hashes:
            return

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        for event in recent_events:
            log.write(_event_to_text(event))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
