"""Live-draw activity feed for the FWA dashboard.

One line per draw, newest first::

    14:32  0xABCD..1234  drew Nakamigos #4471   → sold back ($FWA) 0.118 ETH

The feed is fed from event logs, which the design calls out as its single point
of failure: when the log pool is down there is nothing to show. That case is a
first-class rendered state, not an accident (PRD §9):

* **Available** -- lines render live, no staleness header.
* **Unavailable, with last-good content** -- an explicit
  ``logs unavailable — activity paused`` line, the persisted lines below it, and
  an ``as of HH:MM`` header so nothing stale is ever presented as live.
* **Unavailable, with nothing persisted** -- the paused line plus the reason.

The feed is therefore never blank, never a traceback, and never silently stale.

The settlement choice is colour-coded *and* spelled out in words, so the outcome
survives greyscale (PRD §11).

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

_DASH = "--"

#: Max lines rendered per refresh, matching ``tal_activity_feed.py``.
_MAX_ROWS = 25

#: The explicit degraded line. Tested verbatim.
UNAVAILABLE_LINE = "logs unavailable — activity paused"

#: Colour per settlement outcome. Always paired with the words below.
_OUTCOME_COLORS = {
    "bid_fwa": "green",
    "bid_eth": "cyan",
    "relist": "#f59e0b",
    "kept": "#8a6fd6",
    "forced": "red",
}

#: Fallback wording when the payload omits ``outcome_label``.
_OUTCOME_LABELS = {
    "bid_fwa": "sold back ($FWA)",
    "bid_eth": "sold back (ETH)",
    "relist": "relisted",
    "kept": "kept the NFT",
    "forced": "force-finalized",
}


# -- helpers -----------------------------------------------------------


def _hhmm(timestamp) -> str:
    """``HH:MM`` from unix seconds; falls back to ``??:??``."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??:??"


def _short_addr(value) -> str:
    """``0xABCD..1234`` from a full address; ``--`` when unusable."""
    if value is None:
        return _DASH
    s = str(value).strip()
    if not s:
        return _DASH
    if len(s) <= 12:
        return s
    return f"{s[:6]}..{s[-4:]}"


def _collection_label(event: dict) -> str:
    """Display name when we have one, else a shortened address."""
    name = event.get("collection_name")
    if name:
        s = str(name).strip()
        if s:
            return s[:16]
    return _short_addr(event.get("collection"))


def _token_label(value) -> str:
    if value is None:
        return ""
    try:
        return f" #{int(value)}"
    except (TypeError, ValueError):
        s = str(value).strip()
        return f" #{s}" if s else ""


def _amount_label(value) -> str:
    """``0.118 ETH``; empty string when there is no meaningful amount."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    return f" {amount:.3f} ETH"


def _event_to_markup(event) -> str | None:
    """Format one draw event; ``None`` to skip malformed input."""
    if not isinstance(event, dict):
        return None
    try:
        ts = _hhmm(event.get("ts"))
        wallet = _short_addr(event.get("purchaser"))
        what = f"{_collection_label(event)}{_token_label(event.get('token_id'))}"
        outcome = str(event.get("outcome") or "").strip().lower()
        label = str(event.get("outcome_label") or "").strip()
        if not label:
            label = _OUTCOME_LABELS.get(outcome, outcome or "unknown outcome")
        color = _OUTCOME_COLORS.get(outcome, "dim")
        amount = _amount_label(event.get("amount_eth"))
        return (
            f"{ts}  {wallet:<14}  drew {what:<20}"
            f"  [{color}]→ {label}[/]{amount}"
        )
    except Exception:
        # A single malformed event must never take down the panel.
        return None


class FWAActivityFeed(Vertical):
    """Auto-scrolling feed of live draws and their settlement choices."""

    DEFAULT_CSS = """
    FWAActivityFeed > .fwa-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWAActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Last-good content, persisted so a dead log pool degrades to
        # "stale but labelled" instead of "blank".
        self._last_lines: list[str] = []
        self._last_good_ts: float | None = None

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="fwa-feed-title", id="fwa-feed-title")
        yield Static(" ", classes="fwa-feed-spacer")
        yield RichLog(
            id="fwa-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    # -- rendering -----------------------------------------------------

    def _set_title(self, suffix: str = "") -> None:
        title = self.query_one("#fwa-feed-title", Static)
        title.update(f"ACTIVITY  [dim]{suffix}[/]" if suffix else "ACTIVITY")

    def update_data(
        self,
        draw_events=None,
        feed_available=None,
        feed_unavailable_reason=None,
        feed_as_of_ts=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log from the supplied draws (newest first).

        Every kwarg matches ``FWA_WIDGET_SIGNATURES["FWAActivityFeed"]``.
        ``feed_available=None`` means "unstated": the feed is treated as live
        when it has events, so a bare ``update_data(draw_events=[...])`` behaves
        like the other dashboards.
        """
        log = self.query_one("#fwa-activity-log", RichLog)
        log.clear()
        log.auto_scroll = False

        try:
            events = list(draw_events or [])
        except TypeError:
            events = []

        available = bool(events) if feed_available is None else bool(feed_available)

        if available:
            lines = [
                line
                for line in (_event_to_markup(event) for event in events[:_MAX_ROWS])
                if line is not None
            ]
            # Live content replaces the persisted copy -- including the empty
            # case, so an emptied window is never backfilled with old draws.
            self._last_lines = lines
            self._last_good_ts = (
                feed_as_of_ts if feed_as_of_ts is not None else time.time()
            )
            self._set_title()
            if not lines:
                log.write("[dim]  No draws in this window[/]")
                return
            for line in lines:
                log.write(line)
            self.call_after_refresh(log.scroll_home, animate=False)
            return

        # -- unavailable ------------------------------------------------
        as_of = feed_as_of_ts if feed_as_of_ts is not None else self._last_good_ts
        if self._last_lines and as_of is not None:
            self._set_title(f"· as of {_hhmm(as_of)}")
        else:
            self._set_title("· unavailable")

        log.write(f"[red]⚠ {UNAVAILABLE_LINE}[/]")
        reason = str(feed_unavailable_reason or "").strip()
        if reason:
            log.write(f"[dim]  {reason}[/]")

        if self._last_lines:
            log.write(f"[dim]  last good content, as of {_hhmm(as_of)}:[/]")
            for line in self._last_lines:
                log.write(line)
        else:
            log.write("[dim]  no draws recorded yet[/]")
        self.call_after_refresh(log.scroll_home, animate=False)
