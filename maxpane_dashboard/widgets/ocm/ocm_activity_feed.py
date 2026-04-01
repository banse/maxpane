"""Activity feed for Onchain Monsters dashboard."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


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


def _event_to_markup(event: dict) -> str:
    """Convert an event dict into a Rich-markup formatted line."""
    ts = _format_event_time(event.get("timestamp", 0))
    addr = _short_addr(event.get("actor_address", ""))
    event_type = event.get("event_type", "")
    token_id = event.get("token_id")
    count = event.get("count", 0)

    if event_type == "mint":
        return f"  {ts}  [green]MINT[/]     {addr}  Minted Monster #{token_id}"
    elif event_type == "burn":
        return f"  {ts}  [red]BURN[/]     {addr}  Sacrificed Monster #{token_id}"
    elif event_type == "stake":
        return f"  {ts}  [cyan]STAKE[/]    {addr}  Staked {count} monster(s)"
    elif event_type == "unstake":
        return f"  {ts}  [yellow]UNSTAKE[/]  {addr}  Unstaked {count} monster(s)"
    else:
        return f"  {ts}  [dim]{event_type.upper()}[/]  {addr}  {event_type}"


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
            log.write(_event_to_markup(event))

        # Scroll to top after render
        self.call_after_refresh(log.scroll_home, animate=False)
