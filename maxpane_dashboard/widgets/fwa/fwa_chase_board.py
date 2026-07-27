"""Chase board for the FWA dashboard -- the richest positions, and their odds.

A ranked ``DataTable`` of the biggest-backed listings::

    | #  | COLLECTION | TOKEN | BACKING | ODDS   | JACKPOT |

This is where the protocol's central absurdity is legible: draw weight is
**inverse** to backing, so the 221 ETH position sits at ``0.000%`` odds for a
``1,378×`` jackpot ratio. Two rendering rules follow from that:

* An odds value below 0.001% renders ``0.000%`` -- three decimals, never a bare
  ``0``, because "0" reads as "excluded from the draw" and that is wrong.
* The jackpot ratio is shown next to the odds, so the trade is on one line.

**The crown and the jackpot may be the same listing.** At block 25612701
``topListingId == 56508``, which is also the max-backing position, so the hero
CROWN tile and this board's top row describe *one* listing. That is a live
coincidence, not a permanent fact -- the crown moves when someone out-backs it.
The board therefore *detects* it: pass the current crown listing id as the
optional ``crown_listing_id`` kwarg and the matching row is marked ``♛`` with a
footer note. Without it, nothing is claimed either way.

``crown_listing_id`` is deliberately outside
``FWA_WIDGET_SIGNATURES["FWAChaseBoard"]``: it is an optional extra with a
``None`` default, so the frozen two-kwarg payload still renders.

Primitives only -- this module imports nothing from ``fwa_models``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

_DASH = "--"

#: Rows rendered, matching the ``tal_materials_table.py`` budget.
_MAX_ROWS = 12

#: Marker for the row that is also the crown position.
CROWN_GLYPH = "♛"


def _fmt_text(value, width: int | None = None) -> str:
    if value is None:
        return _DASH
    s = str(value).strip()
    if not s:
        return _DASH
    if width is not None and len(s) > width:
        return s[: width - 1] + "…"
    return s


def _short_addr(value) -> str:
    if value is None:
        return _DASH
    s = str(value).strip()
    if not s:
        return _DASH
    if len(s) <= 12:
        return s
    return f"{s[:6]}..{s[-4:]}"


def _collection_label(row: dict) -> str:
    name = row.get("collection_name")
    if name and str(name).strip():
        return _fmt_text(name, 12)
    return _short_addr(row.get("collection"))


def _fmt_token(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"#{int(value)}"
    except (TypeError, ValueError):
        s = str(value).strip()
        return f"#{s}" if s else _DASH


def _fmt_eth(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_odds(value) -> str:
    """Three decimals always: ``0.000%`` for the unreachable positions.

    A position with a vanishing share is still *in* the draw. Rendering it as
    ``0`` would say otherwise, so the three decimals are mandatory.
    """
    if value is None:
        return _DASH
    try:
        return f"{float(value):.3f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_jackpot(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.0f}×"
    except (TypeError, ValueError):
        return _DASH


def _same_listing(a, b) -> bool:
    """True when two listing ids are the same, tolerating str/int mixes."""
    if a is None or b is None:
        return False
    try:
        return int(a) == int(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


class FWAChaseBoard(Vertical):
    """Richest positions: backing, near-zero odds, jackpot ratio."""

    DEFAULT_CSS = """
    FWAChaseBoard > .fwa-chase-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWAChaseBoard > .fwa-chase-note {
        width: 100%;
        padding: 0 1;
        color: $text-muted;
    }
    FWAChaseBoard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("CHASE BOARD", classes="fwa-chase-title")
        yield Static(" ", classes="fwa-chase-spacer")
        yield DataTable(id="fwa-chase-dt", classes="fwa-chase-table")
        note = Static("", classes="fwa-chase-note", id="fwa-chase-note")
        note.display = False
        yield note

    def on_mount(self) -> None:
        table = self.query_one("#fwa-chase-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        # Width budget: 45 + 12 cell padding = 57 columns, inside the 2fr slot
        # the bottom row gives this table (and under tal_matrix_table's 66).
        table.add_column("#", width=3)
        table.add_column("COLLECTION", width=12)
        table.add_column("TOKEN", width=9)
        table.add_column("BACKING", width=7)
        table.add_column("ODDS", width=7)
        table.add_column("JACKPOT", width=7)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH, _DASH)

    def _set_note(self, text: str) -> None:
        note = self.query_one("#fwa-chase-note", Static)
        if text:
            note.update(text)
            note.display = True
        else:
            note.update("")
            note.display = False

    def update_data(
        self,
        chase_positions=None,
        chase_available=None,
        crown_listing_id=None,
        **_kwargs,
    ) -> None:
        """Refresh the ranked chase rows.

        ``chase_positions`` / ``chase_available`` are the frozen signature;
        ``crown_listing_id`` is an optional extra used only to mark the row that
        is also the crown position (see the module docstring).
        """
        table = self.query_one("#fwa-chase-dt", DataTable)
        table.clear()

        try:
            rows = list(chase_positions or [])
        except TypeError:
            rows = []

        available = bool(rows) if chase_available is None else bool(chase_available)

        if not available:
            table.add_row(
                _DASH, "[dim]unavailable[/]", _DASH, _DASH, _DASH, _DASH
            )
            self._set_note(
                "[yellow]  ⚠ positions unavailable — no sweep this cycle[/]"
            )
            return

        if not rows:
            table.add_row(_DASH, "[dim]No data[/]", _DASH, _DASH, _DASH, _DASH)
            self._set_note("")
            return

        crown_rank: int | None = None
        crown_id = None

        for idx, row in enumerate(rows[:_MAX_ROWS], start=1):
            if not isinstance(row, dict):
                continue
            rank = row.get("rank", idx)
            collection = _collection_label(row)
            token = _fmt_token(row.get("token_id"))
            backing = _fmt_eth(row.get("backing_eth"))
            odds = _fmt_odds(row.get("odds_pct"))
            jackpot = _fmt_jackpot(row.get("jackpot_ratio"))

            is_crown = _same_listing(row.get("listing_id"), crown_listing_id)
            if is_crown:
                crown_rank = rank if isinstance(rank, int) else idx
                crown_id = row.get("listing_id")

            rank_str = f"{CROWN_GLYPH}{rank}" if is_crown else str(rank)
            if idx == 1:
                rank_str = f"[bold]{rank_str}[/]"
                collection = f"[bold]{collection}[/]"

            table.add_row(rank_str, collection, token, backing, odds, jackpot)

        if crown_rank is not None:
            self._set_note(
                f"  [#d4af37]{CROWN_GLYPH}[/] {crown_id} · crown and chase "
                f"#{crown_rank} are one position"
            )
        else:
            self._set_note("")
