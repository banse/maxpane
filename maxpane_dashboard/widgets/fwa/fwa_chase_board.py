"""Chase board for the FWA dashboard -- the richest positions, and their odds.

A ranked ``DataTable`` of the biggest-backed listings::

    | #  | COLLECTION | TOKEN | BACKING | ODDS   | JACKPOT |

This is where the protocol's central absurdity is legible: draw weight is
**inverse** to backing, so the 221 ETH position sits at ``0.000%`` odds for a
``1,378×`` jackpot ratio. Two rendering rules follow from that:

* An odds value below 0.001% renders ``0.000%`` -- three decimals, never a bare
  ``0``, because "0" reads as "excluded from the draw" and that is wrong.
* The jackpot ratio is shown next to the odds, so the trade is on one line.

Width behaviour
---------------

The 2fr slot is 55 rendered columns at a 200-column terminal but only 38 at
140, and the two columns a clipped table loses first are ``ODDS`` and
``JACKPOT`` -- the two that carry the board's entire meaning. A table that
quietly drops them still *looks* complete, which is worse than being narrow.

So the column set is a function of the width (:data:`_TIERS`), ``ODDS`` and
``JACKPOT`` are the last to be dropped, and the title always names what went:
``CHASE BOARD  ‹ widen: TOKEN/BACKING``. The marker lives in the title
rather than in a footer row, so it costs no data column and cannot itself be
scrolled out of view.

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
from maxpane_dashboard.widgets.markup_safety import safe_markup

from .fwa_hero_metrics import CROWN_GOLD

_DASH = "--"

#: Rows rendered, matching the ``tal_materials_table.py`` budget.
_MAX_ROWS = 12

#: Marker for the row that is also the crown position.
CROWN_GLYPH = "♛"

#: The crown colour, imported rather than restated. This module used to
#: carry its own ``#d4af37`` while the hero tile used ``#f0c040`` -- one
#: semantic with two values that were free to drift apart. Both passed
#: contrast; only one is the colour the ``fwa`` theme declares (WP-19).
_GOLD = CROWN_GOLD


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


def _collection_label(row: dict, width: int = 12) -> str:
    name = row.get("collection_name")
    if name and str(name).strip():
        return safe_markup(_fmt_text(name, width))
    return _short_addr(row.get("collection"))


def _fmt_token(value) -> str:
    """Bare id -- the column header already says ``TOKEN``.

    Dropping the ``#`` buys one column, which is what lets an Art Blocks id
    (``78000123``) fit the 8-wide cell instead of clipping.
    """
    if value is None:
        return _DASH
    try:
        return f"{int(value)}"
    except (TypeError, ValueError):
        s = str(value).strip()
        return s if s else _DASH


def _fmt_eth(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return _DASH


def _fmt_odds(value) -> str:
    """Enough decimals to tell the chase positions apart.

    Three decimals rendered *every* chase row as ``0.000%``: this board ranks
    the richest-backed positions, backing sets an **inverse** draw weight, so
    by construction these are the least likely positions in the pool. The live
    range is roughly 0.000009% (a 300 ETH Punk) to 0.0005% -- entirely below
    what three decimals can show, which left the column dead.

    Precision therefore tracks magnitude, always inside the 9-column cell:
    three decimals at or above 1%, four above 0.001%, six below. A position
    with a vanishing share is still *in* the draw, so it never renders as a
    bare ``0``.
    """
    if value is None:
        return _DASH
    try:
        pct = float(value)
        if pct >= 1:
            return f"{pct:.3f}%"
        if pct >= 0.001:
            return f"{pct:.4f}%"
        text = f"{pct:.6f}%"
        if pct > 0 and text.strip("0.%") == "":
            # Rounded away. Six decimals would print `0.000000%`, which is the
            # same dead column three decimals gave and, worse, reads as "cannot
            # be drawn" -- every listed position is in the draw. Decided on the
            # *formatted* value rather than a numeric threshold, because the
            # boundary is wherever the formatter rounds, not wherever we guess
            # it does (5e-7 rounds to zero here, banker's rounding).
            return "<0.000001%"
        return text
    except (TypeError, ValueError):
        return _DASH


def _fmt_jackpot(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):,.0f}×"
    except (TypeError, ValueError):
        return _DASH


#: Column layouts, widest first. Each entry is ``(key, header, width)``; the
#: rendered cost of a layout is ``sum(width) + 2 per column`` (DataTable pads
#: every cell by one column on each side). Measured, not guessed:
#:
#: =========  ====  ==========================================
#: Tier       Cost  Columns
#: =========  ====  ==========================================
#: full        54   # COLLECTION TOKEN BACKING ODDS JACKPOT
#: compact     44   # COLLECTION BACKING ODDS JACKPOT
#: minimal     34   # COLLECTION ODDS JACKPOT
#: tiny        23   # COLLECTION ODDS
#: =========  ====  ==========================================
#:
#: The real slot is 55 columns at a 200-column terminal and 38 at 140, so the
#: board runs ``full`` when wide and ``minimal`` when narrow. ``ODDS`` and
#: ``JACKPOT`` are the last to go because they are the board's entire point;
#: ``TOKEN`` goes first.
_TIERS: tuple[tuple[str, int, tuple[tuple[str, str, int], ...]], ...] = (
    (
        "full",
        58,
        (
            ("rank", "#", 3),
            ("collection", "COLLECTION", 11),
            ("token", "TOKEN", 8),
            ("backing", "BACKING", 7),
            ("odds", "ODDS", 10),
            ("jackpot", "JACKPOT", 7),
        ),
    ),
    (
        "compact",
        48,
        (
            ("rank", "#", 3),
            ("collection", "COLLECTION", 11),
            ("backing", "BACKING", 7),
            ("odds", "ODDS", 10),
            ("jackpot", "JACKPOT", 7),
        ),
    ),
    (
        "minimal",
        38,
        (
            ("rank", "#", 3),
            ("collection", "COLLECTION", 10),
            ("odds", "ODDS", 10),
            ("jackpot", "JACKPOT", 7),
        ),
    ),
    (
        "tiny",
        27,
        (
            ("rank", "#", 3),
            ("collection", "COLLECTION", 8),
            ("odds", "ODDS", 10),
        ),
    ),
)

#: What the header says when a layout has dropped columns. A dropped column
#: must never be silently absent -- that is the defect this table encodes.
_TIER_HINTS = {
    "full": "",
    "compact": "‹ widen: TOKEN",
    "minimal": "‹ widen: TOKEN/BACKING",
    "tiny": "‹ widen: 3 cols hidden",
}


def _tier_for(width: int) -> tuple[str, tuple[tuple[str, str, int], ...], str]:
    """``(name, columns, hint)`` -- the widest layout that fits ``width``.

    ``width <= 0`` means "not laid out yet" and optimistically picks ``full``.
    """
    for name, cost, columns in _TIERS:
        if width <= 0 or width >= cost:
            return name, columns, _TIER_HINTS[name]
    name, _cost, columns = _TIERS[-1]
    return name, columns, _TIER_HINTS[name]


def _grow_collection(columns: tuple, width: int, cap: int = 18) -> tuple:
    """Spend leftover columns on ``COLLECTION`` -- the cell that ellipsises.

    A tier is the widest layout that *fits*, so there is normally slack between
    its cost and the real width. Giving it to the name column is what keeps
    ``CryptoPunks`` from rendering as ``CryptoPun…`` at 38 columns.
    """
    if width <= 0:
        return columns
    spare = width - (sum(w for _k, _h, w in columns) + 2 * len(columns))
    if spare <= 0:
        return columns
    return tuple(
        (key, header, min(w + spare, cap) if key == "collection" else w)
        for key, header, w in columns
    )


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._tier: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static("CHASE BOARD", classes="fwa-chase-title", id="fwa-chase-title")
        yield Static(" ", classes="fwa-chase-spacer")
        yield DataTable(id="fwa-chase-dt", classes="fwa-chase-table")
        note = Static("", classes="fwa-chase-note", id="fwa-chase-note")
        note.display = False
        yield note

    def on_mount(self) -> None:
        table = self.query_one("#fwa-chase-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*self._cells({"collection": "Loading..."}, columns))

    def on_resize(self, _event=None) -> None:
        """Re-render: the column set is a function of the width."""
        self._render_view()

    # -- layout --------------------------------------------------------

    def _table_width(self, table: DataTable) -> int:
        width = table.content_size.width
        if width <= 0:
            width = self.content_size.width
        return width

    def _apply_columns(self, table: DataTable) -> tuple:
        """Install the column set for the current width; return it."""
        table_width = self._table_width(table)
        _name, columns, hint = _tier_for(table_width)
        columns = _grow_collection(columns, table_width)
        if columns != self._tier:
            table.clear(columns=True)
            for _key, header, width in columns:
                table.add_column(header, width=width)
            self._tier = columns
        else:
            table.clear()
        self._set_title(hint)
        return columns

    def _set_title(self, hint: str) -> None:
        """``CHASE BOARD  ‹ widen: TOKEN/BACKING`` -- inside the width we have.

        If the pair does not fit, the *panel name* shortens, never the marker:
        a user who cannot see the marker cannot know the table is incomplete,
        which is the whole defect this guards against.
        """
        title = self.query_one("#fwa-chase-title", Static)
        if not hint:
            title.update("CHASE BOARD")
            return
        width = max(self.content_size.width - 2, 0)
        base = "CHASE BOARD"
        if width and len(base) + 2 + len(hint) > width:
            base = "CHASE"
        title.update(f"{base}  [yellow]{hint}[/]")

    @staticmethod
    def _cells(values: dict, columns: tuple) -> list:
        """Project ``values`` onto the active columns, defaulting to ``--``."""
        return [values.get(key, _DASH) for key, _header, _width in columns]

    def _set_note(self, text: str) -> None:
        note = self.query_one("#fwa-chase-note", Static)
        if text:
            note.update(text)
            note.display = True
        else:
            note.update("")
            note.display = False

    # -- rendering -----------------------------------------------------

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
        try:
            rows = [r for r in list(chase_positions or []) if isinstance(r, dict)]
        except TypeError:
            rows = []
        self._payload = {
            "rows": rows,
            "available": (
                bool(rows) if chase_available is None else bool(chase_available)
            ),
            "crown_listing_id": crown_listing_id,
        }
        self._render_view()

    def _render_view(self) -> None:
        try:
            table = self.query_one("#fwa-chase-dt", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        name_width = next(
            (w for key, _h, w in columns if key == "collection"), 11
        )

        rows = self._payload["rows"]
        crown_listing_id = self._payload["crown_listing_id"]

        if not self._payload["available"]:
            table.add_row(*self._cells({"collection": "[dim]unavailable[/]"}, columns))
            self._set_note(
                "[yellow]  ⚠ positions unavailable — no sweep this cycle[/]"
            )
            return

        if not rows:
            table.add_row(*self._cells({"collection": "[dim]No data[/]"}, columns))
            self._set_note("")
            return

        crown_rank: int | None = None
        crown_id = None

        for idx, row in enumerate(rows[:_MAX_ROWS], start=1):
            rank = row.get("rank", idx)
            collection = _collection_label(row, name_width)

            is_crown = _same_listing(row.get("listing_id"), crown_listing_id)
            if is_crown:
                crown_rank = rank if isinstance(rank, int) else idx
                crown_id = row.get("listing_id")

            rank_str = f"{CROWN_GLYPH}{rank}" if is_crown else str(rank)
            if idx == 1:
                rank_str = f"[bold]{rank_str}[/]"
                collection = f"[bold]{collection}[/]"

            table.add_row(
                *self._cells(
                    {
                        "rank": rank_str,
                        "collection": collection,
                        "token": _fmt_token(row.get("token_id")),
                        "backing": _fmt_eth(row.get("backing_eth")),
                        "odds": _fmt_odds(row.get("odds_pct")),
                        "jackpot": _fmt_jackpot(row.get("jackpot_ratio")),
                    },
                    columns,
                )
            )

        if crown_rank is not None:
            note = (
                f"  [{_GOLD}]{CROWN_GLYPH}[/] {crown_id} · crown and chase "
                f"#{crown_rank}"
            )
            # The full sentence only when the slot can hold it on one line.
            if self.content_size.width >= 49 or self.content_size.width <= 0:
                note += " are one position"
            self._set_note(note)
        else:
            self._set_note("")
