"""Settlement outcome mix + crown history for the FWA dashboard.

Two stacked sections in one ``DataTable``:

1. **Outcome mix** -- what purchasers actually do with the NFT they drew::

       accept bid, paid in $FWA   73.92%
       accept bid, paid in ETH    13.84%
       relist                      7.64%
       keep the NFT                4.60%
       force-finalized             0.00%

   ~88% sell straight back and almost nobody keeps the art. That is the most
   revealing statistic in the protocol, so the widget states it in words above
   the table rather than leaving it to be inferred from five percentages. The
   sell-back share is **computed from the rows**, never hardcoded.

2. **Crown history** -- a *per-holder* aggregation (``rank``, ``holder``,
   ``reigns``, ``payout_eth``, ``last_block``, ``last_ts``), not one row per
   event: the ``TopListingSettled`` vacate+set pairs are deduped upstream. One
   wallet currently holds 4 reigns. A summary row carries the totals
   (33 sets, 12 payouts, 91.096 ETH).

Both sections are log-derived, so both share one staleness header
(``as of HH:MM``) and one explicit unavailable state -- mandatory per PRD §9,
not polish.

The five shares sum to 100 only after rounding; the total row renders the
computed sum to two decimals and asserts nothing.

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

_DASH = "--"
_EMDASH = "—"

#: Crown holders rendered; the tail is summarised by the totals row.
_MAX_CROWN_ROWS = 5

#: The explicit degraded text. Tested verbatim.
UNAVAILABLE_TEXT = "logs unavailable"

#: Outcomes that mean "sold straight back", for the headline share.
_SELLBACK_OUTCOMES = ("bid_fwa", "bid_eth")


def _fmt_int(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_pct(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_eth(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.3f}"
    except (TypeError, ValueError):
        return _DASH


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _short_addr(value) -> str:
    if value is None:
        return _DASH
    s = str(value).strip()
    if not s:
        return _DASH
    if len(s) <= 14:
        return s
    return f"{s[:6]}..{s[-4:]}"


def _hhmm(timestamp) -> str:
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??:??"


def _headline(mix_rows: list) -> str:
    """``87.76% sell straight back · 4.60% keep the NFT`` -- computed, not fixed."""
    sellback = 0.0
    kept = None
    seen = False
    for row in mix_rows:
        if not isinstance(row, dict):
            continue
        share = _as_float(row.get("share_pct"))
        if share is None:
            continue
        outcome = str(row.get("outcome") or "").strip().lower()
        if outcome in _SELLBACK_OUTCOMES:
            sellback += share
            seen = True
        elif outcome == "kept":
            kept = share
    if not seen:
        return ""
    text = f"  [bold]{sellback:.2f}%[/] sell straight back"
    if kept is not None:
        text += f" · [dim]{kept:.2f}% keep the NFT[/]"
    return text


class FWASettlementTable(Vertical):
    """Settlement outcome mix stacked above the crown history."""

    DEFAULT_CSS = """
    FWASettlementTable > .fwa-settle-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWASettlementTable > .fwa-settle-note {
        width: 100%;
        padding: 0 1;
    }
    FWASettlementTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "SETTLEMENT & CROWN",
            classes="fwa-settle-title",
            id="fwa-settle-title",
        )
        yield Static("", classes="fwa-settle-note", id="fwa-settle-note")
        yield DataTable(id="fwa-settle-dt", classes="fwa-settle-table")

    def on_mount(self) -> None:
        table = self.query_one("#fwa-settle-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("OUTCOME / HOLDER", width=22)
        table.add_column("COUNT", width=8)
        table.add_column("SHARE", width=8)
        table.add_column("ETH", width=9)
        table.add_row("Loading...", _DASH, _DASH, _DASH)

    # -- helpers -------------------------------------------------------

    def _set_title(self, suffix: str = "") -> None:
        title = self.query_one("#fwa-settle-title", Static)
        title.update(
            f"SETTLEMENT & CROWN  [dim]{suffix}[/]" if suffix else "SETTLEMENT & CROWN"
        )

    def _set_note(self, text: str) -> None:
        self.query_one("#fwa-settle-note", Static).update(text)

    # -- rendering -----------------------------------------------------

    def update_data(
        self,
        settlement_mix=None,
        crown_history=None,
        crown_sets_total=None,
        crown_payouts_total=None,
        crown_paid_eth=None,
        settle_available=None,
        settle_as_of_ts=None,
        **_kwargs,
    ) -> None:
        """Refresh both sections.

        Every kwarg matches ``FWA_WIDGET_SIGNATURES["FWASettlementTable"]``. No
        args, all-``None`` and a full payload all render without raising.
        """
        table = self.query_one("#fwa-settle-dt", DataTable)
        table.clear()

        try:
            mix_rows = list(settlement_mix or [])
        except TypeError:
            mix_rows = []
        try:
            crown_rows = list(crown_history or [])
        except TypeError:
            crown_rows = []

        has_data = bool(mix_rows or crown_rows)
        available = has_data if settle_available is None else bool(settle_available)

        if not available:
            self._set_title("· unavailable")
            self._set_note(f"[red]  ⚠ {UNAVAILABLE_TEXT} — settlement mix paused[/]")
            table.add_row(
                f"[red]⚠ {UNAVAILABLE_TEXT}[/]", _EMDASH, _EMDASH, _EMDASH
            )
            table.add_row("[dim]crown history[/]", _EMDASH, _EMDASH, _EMDASH)
            return

        self._set_title(
            f"· as of {_hhmm(settle_as_of_ts)}" if settle_as_of_ts else ""
        )
        self._set_note(_headline(mix_rows))

        if not has_data:
            table.add_row("[dim]No data[/]", _DASH, _DASH, _DASH)
            return

        self._render_mix(table, mix_rows)
        self._render_crown(
            table, crown_rows, crown_sets_total, crown_payouts_total, crown_paid_eth
        )

    def _render_mix(self, table: DataTable, mix_rows: list) -> None:
        total_count = 0
        total_share = 0.0
        any_share = False

        for row in mix_rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or row.get("outcome") or _DASH)
            count = row.get("count")
            share = _as_float(row.get("share_pct"))
            if isinstance(count, int):
                total_count += count
            if share is not None:
                total_share += share
                any_share = True
            table.add_row(label[:22], _fmt_int(count), _fmt_pct(share), _EMDASH)

        if mix_rows:
            table.add_row(
                "[bold]TOTAL[/]",
                f"[bold]{_fmt_int(total_count)}[/]",
                f"[bold]{_fmt_pct(total_share) if any_share else _DASH}[/]",
                _EMDASH,
            )

    def _render_crown(
        self,
        table: DataTable,
        crown_rows: list,
        sets_total,
        payouts_total,
        paid_eth,
    ) -> None:
        table.add_row("", "", "", "")
        table.add_row("[bold]CROWN HISTORY[/]", "[dim]REIGNS[/]", "", "[dim]PAID[/]")

        if not crown_rows:
            table.add_row("[dim]no reigns recorded[/]", _EMDASH, _EMDASH, _EMDASH)
        for idx, row in enumerate(crown_rows[:_MAX_CROWN_ROWS], start=1):
            if not isinstance(row, dict):
                continue
            rank = row.get("rank", idx)
            holder = _short_addr(row.get("holder"))
            reigns = _fmt_int(row.get("reigns"))
            payout = _fmt_eth(row.get("payout_eth"))
            table.add_row(f"{rank}. {holder}", reigns, _EMDASH, payout)

        if sets_total is not None or payouts_total is not None or paid_eth is not None:
            sets_str = (
                f"{_fmt_int(sets_total)} sets" if sets_total is not None else _EMDASH
            )
            payouts_str = (
                f"{_fmt_int(payouts_total)} paid"
                if payouts_total is not None
                else _EMDASH
            )
            table.add_row(
                "[bold]TOTAL[/]",
                f"[bold]{sets_str}[/]",
                f"[bold]{payouts_str}[/]",
                f"[bold]{_fmt_eth(paid_eth)}[/]",
            )
