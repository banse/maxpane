"""Heterogeneous activity feed for the TTT dashboard.

Renders the last 25 events from ``cache.activity_log``, descending by
block.  Five event types are formatted with a per-type color tag:

* ``"burn"``    -> yellow BURN, with token symbol, actor (first 6 hex
  chars) and ``tokenId``.
* ``"swap"``    -> green BUY (positive ETH) or red SELL (negative ETH),
  with current buy-tax %.
* ``"fee"``     -> green FEE, with the 30% holder-pool share.
* ``"buyback"`` -> magenta BBACK, with bounty paid.  (The plan task
  refers to this as ``"bought"`` but the cache emits ``"buyback"``;
  both keys are accepted here.)
* ``"sale"``    -> cyan SALE, with the secondary-market price.

Every formatter is exception-safe: missing or malformed fields collapse
to dashes rather than crashing the RichLog write.  See WP3 schema in
``ttt_models.py::TTTActivityEvent`` for the dict shape.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

_WEI = 10**18
_DASH = "--"


# -- helpers -----------------------------------------------------------


def _format_ts(timestamp) -> str:
    """``HH:MM`` from unix seconds; falls back to ``??:??``."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError):
        return "??:??"


def _short_actor(actor) -> str:
    """First 6 hex chars after ``0x``; falls back to dash."""
    if not actor:
        return _DASH
    s = str(actor)
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    return s[:6] if s else _DASH


def _sym(symbol) -> str:
    if symbol is None:
        return _DASH
    s = str(symbol).strip()
    return s if s else _DASH


def _wei_to_eth(wei) -> float | None:
    try:
        return float(int(wei)) / _WEI
    except (TypeError, ValueError):
        return None


def _safe_get(event: dict, key: str, default=None):
    if not isinstance(event, dict):
        return default
    return event.get(key, default)


# -- per-type formatters ----------------------------------------------


def _fmt_burn(event: dict, ts: str, sym: str) -> str:
    actor = _short_actor(_safe_get(event, "actor_address"))
    token_id = _safe_get(event, "token_id")
    token_id_str = str(token_id) if token_id is not None else _DASH
    return (
        f"{ts}  [yellow]BURN [/]  {sym:>6}  by {actor:.6}…   "
        f"tokenId {token_id_str}"
    )


def _fmt_swap(event: dict, ts: str, sym: str) -> str:
    eth_amount = _wei_to_eth(_safe_get(event, "eth_amount_wei", 0))
    extra = _safe_get(event, "extra") or {}
    tax_pct = extra.get("tax_pct") if isinstance(extra, dict) else None

    if eth_amount is None:
        eth_str = _DASH
        dir_color = "white"
    else:
        dir_color = "green" if eth_amount >= 0 else "red"
        eth_str = f"{eth_amount:+7.4f}"

    if tax_pct is None:
        tax_str = _DASH
    else:
        try:
            tax_str = f"{float(tax_pct):.0f}"
        except (TypeError, ValueError):
            tax_str = _DASH

    return (
        f"{ts}  [{dir_color}]SWAP [/]  {sym:>6}  "
        f"{eth_str} Ξ  tax {tax_str}%"
    )


def _fmt_fee(event: dict, ts: str, sym: str) -> str:
    eth_amount = _wei_to_eth(_safe_get(event, "eth_amount_wei", 0))
    if eth_amount is None:
        eth_str = _DASH
    else:
        eth_str = f"{eth_amount:.4f}"
    return f"{ts}  [green]FEE  [/]  {sym:>6}  {eth_str} Ξ → holders"


def _fmt_buyback(event: dict, ts: str, sym: str) -> str:
    extra = _safe_get(event, "extra") or {}
    bounty_wei = extra.get("bounty_wei") if isinstance(extra, dict) else None
    if bounty_wei is None:
        # fall back to eth_amount_wei when bounty_wei isn't populated
        bounty = _wei_to_eth(_safe_get(event, "eth_amount_wei", 0))
    else:
        bounty = _wei_to_eth(bounty_wei)
    if bounty is None:
        bounty_str = _DASH
    else:
        bounty_str = f"{bounty:.5f}"
    return (
        f"{ts}  [magenta]BBACK[/]  {sym:>6}  "
        f"{bounty_str} Ξ bounty paid"
    )


def _fmt_sale(event: dict, ts: str) -> str:
    token_id = _safe_get(event, "token_id")
    token_id_str = str(token_id) if token_id is not None else _DASH
    extra = _safe_get(event, "extra") or {}
    price_eth = extra.get("price_eth") if isinstance(extra, dict) else None
    if price_eth is None:
        # fallback to eth_amount_wei
        price = _wei_to_eth(_safe_get(event, "eth_amount_wei", 0))
    else:
        try:
            price = float(price_eth)
        except (TypeError, ValueError):
            price = None
    if price is None:
        price_str = _DASH
    else:
        price_str = f"{price:.4f}"
    return (
        f"{ts}  [cyan]SALE [/]  TTT     "
        f"#{token_id_str}  {price_str} Ξ"
    )


def _event_to_markup(event: dict) -> str | None:
    """Format one activity event; ``None`` to skip unknown types."""
    if not isinstance(event, dict):
        return None
    ts = _format_ts(event.get("timestamp"))
    sym = _sym(event.get("token_symbol"))
    etype = (event.get("event_type") or "").lower()

    try:
        if etype == "burn":
            return _fmt_burn(event, ts, sym)
        if etype == "swap":
            return _fmt_swap(event, ts, sym)
        if etype == "fee":
            return _fmt_fee(event, ts, sym)
        if etype in ("buyback", "bought", "bback"):
            return _fmt_buyback(event, ts, sym)
        if etype == "sale":
            return _fmt_sale(event, ts)
    except Exception:
        # Never let a single malformed event take down the whole panel.
        return None
    # Unknown type -- render a generic dim row rather than skipping
    return f"{ts}  [dim]{etype.upper():>5}[/]  {sym:>6}  [dim]--[/]"


# -- widget ------------------------------------------------------------


class TTTActivityFeed(Vertical):
    """Auto-scrolling activity feed for TTT (last 25 events)."""

    DEFAULT_CSS = """
    TTTActivityFeed > .ttt-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("ACTIVITY", classes="ttt-feed-title")
        yield RichLog(
            id="ttt-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(
        self,
        activity_events=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with the supplied events (descending order).

        Newest events appear at the top.  The widget rewrites the log on
        every refresh -- simpler than incremental diffing and fast
        enough for the 25-row cap.
        """
        log = self.query_one("#ttt-activity-log", RichLog)
        events = activity_events or []
        log.clear()

        if not events:
            log.write("[dim]  No activity yet[/]")
            return

        try:
            iterator = list(events)[:25]
        except TypeError:
            log.write("[dim]  No activity yet[/]")
            return

        log.auto_scroll = False
        for event in iterator:
            line = _event_to_markup(event)
            if line is not None:
                log.write(line)

        self.call_after_refresh(log.scroll_home, animate=False)
