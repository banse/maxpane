"""Fishing activity feed for Cat Town dashboard."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}


def _format_event_time(timestamp: float | int | str) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    try:
        ts = int(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xABCD..1234 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _catch_to_markup(catch: dict) -> str:
    """Convert a catch dict into a Rich-markup formatted line."""
    ts = _format_event_time(catch.get("timestamp", 0))
    display_name = catch.get("display_name", "")
    fisher = display_name if display_name else _short_addr(catch.get("fisher_address", ""))
    species = catch.get("species", "Unknown")
    weight = catch.get("weight_kg", 0.0)
    event_type = catch.get("rarity", "fish")

    if event_type == "treasure":
        return (
            f"  [dim]{ts}[/]  "
            f"[dim]{fisher}[/]  "
            f"[yellow]Found {species}[/]"
        )
    else:
        # Fish: show weight in kg
        return (
            f"  [dim]{ts}[/]  "
            f"[dim]{fisher}[/]  "
            f"[cyan]Caught {species} ({weight:.1f}kg)[/]"
        )


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
            log.write(_catch_to_markup(catch))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
