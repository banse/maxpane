"""Fishing activity feed for Cat Town dashboard."""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.cattown._chain import EXPLORER


_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}

#: display budget for the fisher name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. No pin binds this
#: RichLog line; grown by ICON_COLS as in the recipe (PRD §5).
_FISHER_COLS = 12


def _format_event_time(timestamp: float | int | str) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _catch_to_text(catch: dict) -> Text:
    """Convert a catch dict into a composited ``Text`` line."""
    ts = _format_event_time(catch.get("timestamp", 0))
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


class CTActivityFeed(Vertical):
    """Auto-scrolling fishing activity feed."""

    DEFAULT_CSS = """
    CTActivityFeed > .feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_tx_hashes: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("FISHING ACTIVITY", classes="feed-title")
        yield RichLog(id="ct-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(
        self,
        recent_catches: list[dict] | None = None,
    ) -> None:
        """Rewrite the log with newest catches on top.

        Catches are de-duplicated by ``tx_hash``.
        """
        log = self.query_one("#ct-activity-log", RichLog)

        if not recent_catches:
            if not self._seen_tx_hashes:
                log.write("[dim]  No activity yet[/]")
            return

        # De-duplicate by tx_hash
        new_catches: list[dict] = []
        for catch in recent_catches:
            tx_hash = catch.get("tx_hash", "")
            if tx_hash and tx_hash in self._seen_tx_hashes:
                continue
            if tx_hash:
                self._seen_tx_hashes.add(tx_hash)
            new_catches.append(catch)

        if not new_catches and self._seen_tx_hashes:
            return

        # Clear and rewrite: newest on top
        log.clear()
        log.auto_scroll = False
        for catch in recent_catches:
            log.write(_catch_to_text(catch))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
