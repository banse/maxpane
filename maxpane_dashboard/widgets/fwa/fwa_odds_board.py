"""Odds board for the Fake World Assets (FWA) dashboard.

The leaderboard slot: every collection holding live positions, ranked by
its share of the **draw weight**.

This table exists to make one thing legible at a glance -- draw weight is
*inverse* to backing (``weight = 1e36 // backing``), so the cheapest
collections own the draw and the expensive ones are effectively
unreachable.  TTT sits near 49% of the odds while CryptoPunks hold ~137
ETH of backing for **0.000%**.  The ``ETH/ODDS`` (ETH per odds point) column is where that
inversion becomes a number rather than a claim.

Rendering rules:

* An **unpriced** collection is marked unpriced -- ``—`` when no keyless
  floor exists, ``n/a*`` when the floor is suppressed (one contract
  hosting many collections has no single meaningful floor).  A missing
  floor is never rendered as ``0``.
* ``weight_share_pct`` is rounded to 6 dp upstream and the 38 values sum
  to ``100.000001``; this widget never totals the column or asserts an
  exact 100 (PRD §5).
* ``odds_available is False`` renders an explicit unavailable row, and
  ``odds_stale`` is labelled *stale* rather than silently shown as live
  (PRD §9, §7 rule 11).

Format helpers are local to this file so the widget has no dependency on
game-specific analytics modules, and every one of them tolerates
``None``.  Copied from ``talismans/tal_leaderboard.py`` and adapted to
``FWA_WIDGET_SIGNATURES["FWAOddsBoard"]`` /
``FWA_ROW_KEYS["collection_odds"]``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.markup_safety import safe_markup

_DASH = "--"
_EMDASH = "—"
_MAX_ROWS = 60
_NAME_WIDTH = 16
_NOTE_WIDTH = 44


# -- format helpers ----------------------------------------------------


def _as_float(value):
    """Coerce to ``float`` or return ``None`` -- never raise."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_pct(value) -> str:
    """Three decimals -- ``0.000%`` for the unreachable collections."""
    v = _as_float(value)
    if v is None:
        return _DASH
    return f"{v:.3f}%"


def _fmt_eth(value, places: int = 2) -> str:
    v = _as_float(value)
    if v is None:
        return _EMDASH
    return f"{v:,.{places}f}"


def _fmt_ratio(value) -> str:
    """ETH per odds point -- spans many orders of magnitude."""
    v = _as_float(value)
    if v is None:
        return _EMDASH
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:,.1f}M"
    if a >= 1_000:
        return f"{v:,.0f}"
    if a >= 1:
        return f"{v:,.2f}"
    return f"{v:.3f}"


def _fmt_name(name, address) -> str:
    if name:
        s = str(name).strip()
        if s:
            return s if len(s) <= _NAME_WIDTH else s[: _NAME_WIDTH - 1] + "…"
    if address:
        s = str(address).strip()
        if len(s) > 11:
            return f"{s[:6]}..{s[-4:]}"
        if s:
            return s
    return _DASH


def _floor_cell(row: dict) -> str:
    """Floor price, or an explicit mark of *why* there isn't one."""
    source = str(row.get("floor_source") or "missing").lower()
    floor = _as_float(row.get("floor_eth"))
    if source == "suppressed":
        return "n/a*"
    if floor is None:
        return _EMDASH
    if source == "cached":
        return f"{floor:,.3f}~"
    return f"{floor:,.3f}"


def _sort_key(row: dict):
    share = _as_float(row.get("weight_share_pct"))
    return -(share if share is not None else -1.0)


# -- widget ------------------------------------------------------------


class FWAOddsBoard(Vertical):
    """DataTable of live collections ranked by share of the draw weight."""

    DEFAULT_CSS = """
    FWAOddsBoard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWAOddsBoard > DataTable {
        height: 1fr;
    }
    /* The meta line is a single row by contract: if the block/stale/
       suppression text is wider than the pane it is ellipsised, never
       wrapped -- a second row would push the table down. */
    FWAOddsBoard > #fwa-odds-meta {
        text-wrap: nowrap;
        text-overflow: ellipsis;
        text-style: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("ODDS BOARD", classes="fwa-odds-title")
        yield Static(" ", classes="fwa-odds-meta", id="fwa-odds-meta")
        yield DataTable(id="fwa-odds-table", classes="fwa-odds-table")

    def on_mount(self) -> None:
        table = self.query_one("#fwa-odds-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=3)
        table.add_column("COLLECTION", width=_NAME_WIDTH)
        table.add_column("POS", width=5)
        table.add_column("% WEIGHT", width=9)
        table.add_column("ETH BACKED", width=10)
        table.add_column("FLOOR", width=8)
        table.add_column("ETH/ODDS", width=10)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH, _DASH, _DASH)

    # -- update ---------------------------------------------------------

    def update_data(
        self,
        collection_odds=None,
        odds_available=None,
        odds_as_of_block=None,
        odds_stale=None,
        **_kwargs,
    ) -> None:
        """Refresh the board from ``FWA_ROW_KEYS["collection_odds"]`` rows."""
        table = self.query_one("#fwa-odds-table", DataTable)
        meta = self.query_one("#fwa-odds-meta", Static)
        table.clear()

        if odds_available is False:
            meta.update("[yellow]odds unavailable — position sweep failed[/]")
            table.add_row(
                _DASH,
                "unavailable",
                _DASH,
                _DASH,
                _DASH,
                _EMDASH,
                _EMDASH,
            )
            return

        rows = [r for r in (collection_odds or []) if isinstance(r, dict)]
        if not rows:
            meta.update("no collections")
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH, _EMDASH, _EMDASH)
            return

        rows = sorted(rows, key=_sort_key)[:_MAX_ROWS]

        suppressed_note = ""
        for idx, row in enumerate(rows, start=1):
            rank = row.get("rank")
            rank_str = _fmt_int(rank) if rank is not None else str(idx)
            name = safe_markup(_fmt_name(row.get("name"), row.get("address")))
            positions = _fmt_int(row.get("positions"))
            share = _fmt_pct(row.get("weight_share_pct"))
            backed = _fmt_eth(row.get("eth_backed"))
            floor = _floor_cell(row)
            per_point = _fmt_ratio(row.get("eth_per_odds_point"))

            if floor == "n/a*" and not suppressed_note:
                note = str(row.get("floor_note") or "").strip()
                suppressed_note = safe_markup(note) or "floor suppressed — not meaningful"

            if idx == 1:
                rank_str = f"[bold]{rank_str}[/]"
                name = f"[bold]{name}[/]"
                positions = f"[bold]{positions}[/]"
                share = f"[bold]{share}[/]"
                backed = f"[bold]{backed}[/]"
                floor = f"[bold]{floor}[/]"
                per_point = f"[bold]{per_point}[/]"

            table.add_row(rank_str, name, positions, share, backed, floor, per_point)

        meta.update(self._meta_line(len(rows), odds_as_of_block, odds_stale, suppressed_note))

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _meta_line(count: int, block, stale, suppressed_note: str) -> str:
        block_str = _fmt_int(block) if block is not None else _DASH
        # The enclosing Static is already `color: $text-muted`; a `[dim]`
        # on top of it compounds to 3.71:1 under `fwa` and 3.64 under
        # bakery, below WCAG 1.4.3, for no visual gain (WP-19).
        parts = [f"{count} collections · block {block_str}"]
        if stale:
            parts.append("[yellow]STALE — last good sweep[/]")
        if suppressed_note:
            note = suppressed_note
            if len(note) > _NOTE_WIDTH:
                note = note[: _NOTE_WIDTH - 1] + "…"
            parts.append(f"* {note}")
        return " · ".join(parts)
