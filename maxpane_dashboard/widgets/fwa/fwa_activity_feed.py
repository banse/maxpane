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

Width behaviour
---------------

The feed's 3fr slot is 81 rendered columns at a 200-column terminal and 56 at
140, while the full line needs 79. Rather than let the outcome label clip to
something unreadable like ``→ a``, the line sheds whole fields as the width
drops (see :func:`_tier_for`) and the title says which ones went. The outcome
label itself is *never* cut mid-word: it falls back to a shorter wording that
still names the outcome.

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

#: Abbreviations used when the line is too narrow for the full wording. Each
#: still says what happened -- unlike a truncated ``→ a``.
_OUTCOME_SHORT = {
    "bid_fwa": "sold ($FWA)",
    "bid_eth": "sold (ETH)",
    "relist": "relisted",
    "kept": "kept NFT",
    "forced": "forced",
}

#: Rendered columns each line layout needs (see :func:`_tier_for`), measured
#: from the format strings in :func:`_event_to_markup` rather than rounded.
FULL_WIDTH = 77
COMPACT_WIDTH = 55
MINIMAL_WIDTH = 34

#: Columns each layout spends on everything *except* the outcome label; the
#: label gets the remainder of the real width (see :func:`_event_to_markup`).
_FIXED_FULL = 60      # time + wallet + "drew " + what(20) + arrow + " x ETH"
_FIXED_COMPACT = 41   # time + wallet + what(16) + arrow
_FIXED_MINIMAL = 23   # time + wallet + arrow

#: Fallbacks when the width is not known yet, and the floor below which the
#: label is abbreviated rather than squeezed further.
_LABEL_BUDGET_FULL = 17
_LABEL_BUDGET_MIN = 10

#: Room the ``Collection #token`` field gets in each layout.
_WHAT_BUDGET_FULL = 20
_WHAT_BUDGET_COMPACT = 16

#: Marker appended to the title when the layout had to shed a field.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for amounts",
    "minimal": "‹ widen: collections + ETH",
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


def _tier_for(width: int) -> str:
    """Widest line layout that fits ``width`` rendered columns.

    Thresholds are the measured widths of the three line layouts below, not
    round numbers:

    ===========  =====  =====================================================
    Tier         Needs  Line
    ===========  =====  =====================================================
    ``full``     79     ``HH:MM  wallet  drew Collection #id   → label  ETH``
    ``compact``  52     ``HH:MM  wallet  Collection #id  → label``
    ``minimal``  34     ``HH:MM  wallet  → label``
    ===========  =====  =====================================================

    The real slots are 81 columns at a 200-column terminal and 56 at 140, so
    the feed runs ``full`` on a wide terminal and ``compact`` on a narrow one.
    ``width <= 0`` means "not laid out yet" and optimistically picks ``full``.
    """
    if width <= 0 or width >= FULL_WIDTH:
        return "full"
    if width >= COMPACT_WIDTH:
        return "compact"
    return "minimal"


def _what_for(event: dict, budget: int) -> str:
    """``Collection #token`` inside ``budget`` columns.

    The *name* is squeezed before the token id is: ``Art B… #78000123`` keeps
    both fields recognisable, whereas the naive ``[:budget]`` cut produced
    ``Art Blocks #7`` -- a token id that is not the token id.
    """
    name = _collection_label(event)
    token = _token_label(event.get("token_id"))
    if len(name) + len(token) <= budget:
        return f"{name}{token}"
    room = budget - len(token)
    if room >= 4:
        return f"{name[:room - 1]}…{token}"
    return f"{name}{token}"[: budget - 1] + "…"


def _label_for(event: dict, outcome: str, budget: int) -> str:
    """The settlement choice in words, abbreviated rather than truncated.

    A clipped ``→ a`` is worse than no column at all, so when the payload's
    ``outcome_label`` does not fit the line's budget we fall back to the short
    form for that outcome instead of cutting the string.
    """
    label = str(event.get("outcome_label") or "").strip()
    if not label:
        label = _OUTCOME_LABELS.get(outcome, outcome or "unknown outcome")
    if len(label) <= budget:
        return label
    short = _OUTCOME_SHORT.get(outcome)
    if short and len(short) <= budget:
        return short
    # No known abbreviation: keep whole words, never a half word.
    words = label.split()
    out = words[0] if words else label
    return out[:budget] if len(out) > budget else out


def _event_to_markup(event, tier: str = "full", width: int = 0) -> str | None:
    """Format one draw event at ``tier``; ``None`` to skip malformed input.

    ``width`` is the real number of columns available. The outcome label gets
    whatever the fixed fields leave over, so a wide terminal shows the
    payload's own wording and a narrow one falls back to the short form -- the
    budget is measured, never a fixed guess.
    """
    if not isinstance(event, dict):
        return None
    try:
        ts = _hhmm(event.get("ts"))
        wallet = _short_addr(event.get("purchaser"))
        outcome = str(event.get("outcome") or "").strip().lower()
        color = _OUTCOME_COLORS.get(outcome, "dim")

        if tier == "minimal":
            budget = max(width - _FIXED_MINIMAL, _LABEL_BUDGET_MIN) if width else 14
            label = _label_for(event, outcome, budget)
            return f"{ts}  {wallet:<12}  [{color}]→ {label}[/]"

        if tier == "compact":
            what = _what_for(event, _WHAT_BUDGET_COMPACT)
            budget = max(width - _FIXED_COMPACT, _LABEL_BUDGET_MIN) if width else 14
            label = _label_for(event, outcome, budget)
            return (
                f"{ts}  {wallet:<12}  {what:<{_WHAT_BUDGET_COMPACT}}"
                f"  [{color}]→ {label}[/]"
            )

        what = _what_for(event, _WHAT_BUDGET_FULL)
        budget = (
            max(width - _FIXED_FULL, _LABEL_BUDGET_MIN) if width else _LABEL_BUDGET_FULL
        )
        label = _label_for(event, outcome, budget)
        amount = _amount_label(event.get("amount_eth"))
        return (
            f"{ts}  {wallet:<12}  drew {what:<20}"
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
        # "stale but labelled" instead of "blank". The raw events are kept
        # rather than formatted lines, so a resize re-lays them out.
        self._last_events: list[dict] = []
        self._last_good_ts: float | None = None
        self._payload: dict = {}

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

    def _set_title(self, suffix: str = "", hint: str = "") -> None:
        """``ACTIVITY  · as of 14:32  ‹ widen for amounts``, width permitting.

        The staleness stamp is never dropped -- stale content presented as live
        is the one outcome this widget may not produce, and the stamp is what
        prevents it. The widen marker yields if they cannot both fit; it is
        only ever set in the narrow layouts, where the stamp is the shorter and
        more urgent of the two.
        """
        title = self.query_one("#fwa-feed-title", Static)
        base = "ACTIVITY"
        width = max(self.content_size.width - 2, 0)

        text = base
        used = len(base)
        if suffix:
            text += f"  [dim]{suffix}[/]"
            used += 2 + len(suffix)
        if hint and (not width or used + 2 + len(hint) <= width):
            text += f"  [yellow]{hint}[/]"
        title.update(text)

    def _log_width(self, log: RichLog) -> int:
        """Rendered columns available to one line (``padding: 0 1`` removed)."""
        width = log.content_size.width
        if width <= 0:
            width = max(self.content_size.width - 2, 0)
        return width

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
        try:
            events = list(draw_events or [])
        except TypeError:
            events = []

        available = bool(events) if feed_available is None else bool(feed_available)

        if available:
            # Live content replaces the persisted copy -- including the empty
            # case, so an emptied window is never backfilled with old draws.
            self._last_events = [e for e in events[:_MAX_ROWS] if isinstance(e, dict)]
            self._last_good_ts = (
                feed_as_of_ts if feed_as_of_ts is not None else time.time()
            )

        self._payload = {
            "available": available,
            "reason": feed_unavailable_reason,
            "as_of": feed_as_of_ts,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the feed out: the line layout depends on the width."""
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        try:
            log = self.query_one("#fwa-activity-log", RichLog)
        except Exception:  # not composed yet
            return

        available = bool(self._payload.get("available"))
        reason = str(self._payload.get("reason") or "").strip()
        as_of_arg = self._payload.get("as_of")

        width = self._log_width(log)
        tier = _tier_for(width)
        hint = WIDEN_HINTS.get(tier, "")
        lines = [
            line
            for line in (
                _event_to_markup(event, tier, width) for event in self._last_events
            )
            if line is not None
        ]

        log.clear()
        log.auto_scroll = False

        if available:
            self._set_title("", hint if lines else "")
            if not lines:
                log.write("[dim]  No draws in this window[/]")
                return
            for line in lines:
                log.write(line)
            self.call_after_refresh(log.scroll_home, animate=False)
            return

        # -- unavailable ------------------------------------------------
        as_of = as_of_arg if as_of_arg is not None else self._last_good_ts
        if lines and as_of is not None:
            self._set_title(f"· as of {_hhmm(as_of)}", hint)
        else:
            self._set_title("· unavailable")

        log.write(f"[red]⚠ {UNAVAILABLE_LINE}[/]")
        if reason:
            log.write(f"[dim]  {reason}[/]")

        if lines:
            log.write(f"[dim]  last good content, as of {_hhmm(as_of)}:[/]")
            for line in lines:
                log.write(line)
        else:
            log.write("[dim]  no draws recorded yet[/]")
        self.call_after_refresh(log.scroll_home, animate=False)
