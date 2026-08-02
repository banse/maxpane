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

import logging

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len as _visible_len

logger = logging.getLogger(__name__)

_DASH = "--"
_EMDASH = "—"
_MAX_ROWS = 60
#: Narrowest the COLLECTION column ever gets -- the width it used to be fixed
#: at, which truncated almost every real name ("Ten Thousand To…",
#: "Art Blocks Expl…", "VeeFriends Seri…").
_NAME_WIDTH = 16

#: Widest it grows to. The longest live collection name is 40 characters
#: ("MAX PAIN AND FRENS OPEN EDITION BY XCOPY"); past this the column starts
#: taking space from numbers that carry the board's meaning, so a handful of
#: outliers still elide.
_NAME_WIDTH_MAX = 34

#: Every other column plus DataTable's one-column pad on each side of all
#: seven. What is left over goes to COLLECTION.
_FIXED_COLUMN_COST = 3 + 5 + 9 + 10 + 8 + 10 + (2 * 7)
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


def _fmt_name(name, address, width: int = _NAME_WIDTH) -> str:
    if name:
        s = str(name).strip()
        if s:
            return s if len(s) <= width else s[: max(width - 1, 1)] + "…"
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
    FWAOddsBoard > #fwa-odds-title {
        text-wrap: nowrap;
        text-overflow: ellipsis;
        text-style: none;
    }
    """

    def compose(self) -> ComposeResult:
        # One title line, not a title plus a meta line. The provenance
        # (collection count, swept block, staleness) is folded into the title
        # instead of sitting under it: it is short, it belongs to the board as
        # a whole, and a second line of muted text above a table reads as
        # clutter -- especially since it clipped at the widths people run.
        yield Static("ODDS BOARD", classes="fwa-odds-title", id="fwa-odds-title")
        yield DataTable(id="fwa-odds-table", classes="fwa-odds-table")

    #: Last payload, replayed on resize so the name column can re-fit.
    _last_payload: dict | None = None

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
        self._last_payload = {
            "collection_odds": collection_odds,
            "odds_available": odds_available,
            "odds_as_of_block": odds_as_of_block,
            "odds_stale": odds_stale,
        }
        table = self.query_one("#fwa-odds-table", DataTable)
        table.clear()

        if odds_available is False:
            # The unavailable state used to live in a meta line under the
            # title. With that line gone it goes *in* the title, which is the
            # only place left that is always visible -- the table below it is
            # a row of dashes and says nothing on its own.
            self._set_title_text(
                "ODDS BOARD · [yellow]odds unavailable — position sweep failed[/]"
            )
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
            self._set_title_text("ODDS BOARD · no collections")
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH, _EMDASH, _EMDASH)
            return

        rows = sorted(rows, key=_sort_key)[:_MAX_ROWS]
        name_width = self._grow_name_column(
            [str(r.get("name") or r.get("address") or "") for r in rows]
        )

        suppressed_note = ""
        for idx, row in enumerate(rows, start=1):
            rank = row.get("rank")
            rank_str = _fmt_int(rank) if rank is not None else str(idx)
            name = safe_markup(
                _fmt_name(row.get("name"), row.get("address"), name_width)
            )
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

        self._set_title(len(rows), odds_as_of_block, odds_stale, suppressed_note)

    # -- helpers ---------------------------------------------------------

    def _grow_name_column(self, names: list[str]) -> int:
        """Widen COLLECTION to fit its content, bounded by the space available.

        The board's seven columns cost 75 rendered columns at their declared
        widths, in a slot that measures ~118 at a 200-column terminal -- so a
        third of the pane sat blank while every collection name was elided to
        16 characters. The numeric columns are all fixed-width by nature (a
        percentage, an ETH amount), so the name is the only one that can take
        the slack, exactly as the settlement table's ``_grow_label`` does.

        Sized to the **longest name actually on the board**, not to the space:
        growing to the full slot would pad a column of 19-character names out
        to 34 and move the numbers away from them for nothing. Bounded below by
        the old fixed width and above by both the free space and
        :data:`_NAME_WIDTH_MAX`.

        Returns the width so the row builder elides to the same number the
        column will really render.
        """
        width = max(self.content_size.width - 2, 0)
        if width <= 0:
            return _NAME_WIDTH
        longest = max((len(n) for n in names), default=0)
        name_width = max(
            _NAME_WIDTH,
            min(longest, width - _FIXED_COLUMN_COST, _NAME_WIDTH_MAX),
        )
        try:
            table = self.query_one("#fwa-odds-table", DataTable)
            for key in table.columns:
                column = table.columns[key]
                if str(column.label).strip() == "COLLECTION":
                    if column.width != name_width:
                        column.width = name_width
                        table.refresh()
                    break
        except Exception as exc:  # noqa: BLE001 -- cosmetic, never fatal
            logger.debug("could not resize the collection column: %s", exc)
        return name_width

    def _set_title_text(self, text: str) -> None:
        """Write the title line, ignoring a not-yet-composed widget."""
        try:
            self.query_one("#fwa-odds-title", Static).update(text)
        except Exception:  # not composed yet
            pass

    def _title_for(
        self, count: int, block, stale, suppressed_note: str, width: int = 0
    ) -> str:
        """The title line for these values inside *width* columns.

        Split out from :meth:`_set_title` so the composition rules can be
        asserted directly, without a harness whose width decides which optional
        parts survive.
        """
        block_str = _fmt_int(block) if block is not None else _DASH
        optional = [f"{count} collections", f"block {block_str}"]
        if suppressed_note:
            note = suppressed_note
            if len(note) > _NOTE_WIDTH:
                note = note[: _NOTE_WIDTH - 1] + "…"
            optional.append(f"* {note}")

        # `[dim]` is deliberately absent: the enclosing Static is already
        # `color: $text-muted` and compounding them gives 3.71:1 under `fwa`
        # and 3.64 under bakery, below WCAG 1.4.3, for no visual gain (WP-19).
        stale_part = "[yellow]STALE — last good sweep[/]" if stale else ""

        while True:
            parts = ["ODDS BOARD"] + optional + ([stale_part] if stale_part else [])
            text = " · ".join(p for p in parts if p)
            if not width or _visible_len(text) <= width or not optional:
                return text
            optional.pop()

    def on_resize(self, _event=None) -> None:
        """Re-render so the name column tracks the new width."""
        if self._last_payload is not None:
            self.update_data(**self._last_payload)

    def _set_title(self, count: int, block, stale, suppressed_note: str) -> None:
        """``ODDS BOARD · 52 collections · block 25,666,513``, width permitting.

        Parts are appended widest-last and dropped from the right when they do
        not fit, so the panel never clips mid-word. Priority is deliberate:
        ``STALE`` outranks everything because a stale board presented as live
        is the one failure this widget must not have, then the block (the
        board's provenance), then the count, then the suppressed-floor
        footnote (whose ``*`` marker is already visible in the FLOOR column).
        """
        self._set_title_text(
            self._title_for(
                count, block, stale, suppressed_note,
                max(self.content_size.width - 2, 0),
            )
        )
