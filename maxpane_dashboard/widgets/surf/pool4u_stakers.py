"""The `4` body's leaderboard slot: STAKERS -- who holds the sIMD vault.

**The ranking is not the point; concentration is** (PRD §6.1). Whether three
wallets can walk out of this vault is a risk a reader acts on, and the footer
is where this panel says so. The rows are the evidence for the footer, not the
other way round.

Its own clock, deliberately
---------------------------
The four keys behind this panel come from ``TIER_POOL4_STAKERS`` -- a full sIMD
``Transfer`` history fold on curator's ``TIER_ANALYSIS`` precedent, far too
expensive for the 600 s pool4 sweep. So the panel carries
``pool4_stakers_as_of_hhmm``, **its own, slower marker**, and never the body's
``pool4_as_of_hhmm``: a panel whose numbers can be half an hour old sitting
under a clock that says seconds is a stale number presented as live, which is
the failure CLAUDE.md's "as of" rule exists to prevent. It takes
``pool4_as_of_hhmm`` too, because the pool4 contract requires every panel on
this body to (``test_no_pool4_widget_needs_a_kwarg_alias``), and renders the
staker one.

``top 3 = --`` is a real state
------------------------------
``pool4_staker_top3_pct`` is ``None`` on an **incomplete** fold, and the footer
renders the dash rather than computing a fallback from the rows it happens to
have. Ranking a subset understates concentration -- the one direction that
makes a risk look smaller than it is -- and this is ``clean_routed_eth``'s
guard verbatim (PRD §7.4).

Addresses
---------
Chain-sourced, therefore escaped, and shortened with ``_fmt.long_addr`` rather
than the leaderboard template's ``_short_addr``. That is a deliberate departure
from the template and the reason is in ``_fmt``: live spoofs of surf's own fee
recipients exist today which collide with the real addresses on first-6/last-4
-- exactly what ``0xABCD..1234`` shows -- and do not collide on ``long_addr``'s
window. A panel whose whole subject is *which* wallets hold the vault is the
last place to use the colliding form.

Purity
------
Stdlib, ``rich``, ``textual`` and this package's own primitives. No ``data/``,
no ``analytics/``, no clock, no I/O. Rich colour names only -- Rich cannot
resolve Textual's ``$`` theme tokens and raises at render time, outside this
module's ``try``.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_compact, long_addr
from maxpane_dashboard.widgets.surf._pool4 import (
    join_lines,
    parse_line,
    strip_tags,
    title_text,
)
from maxpane_dashboard.widgets.surf._rowfit import clip, pad

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "MAX_ROWS",
    "TABLE_ID",
    "TITLE",
    "TOP_N",
    "UNAVAILABLE_LINE",
    "SurfPool4UStakers",
    "footer_line",
    "staker_cells",
]

TITLE = "STAKERS"

#: Nothing was read at all -- ``pool4_stakers is None``.
UNAVAILABLE_LINE = "stakers unavailable"

#: The fold ran and found no holders. A **different** sentence from
#: :data:`UNAVAILABLE_LINE`, and the distinction is the curator rail bug: an
#: empty vault is a real, representable answer and must not be paintable by an
#: outage.
EMPTY_LINE = "no depositors"

#: How many rows the table draws. The producer caps its own list at 20
#: (``staker_rows(limit=20)``); this is the renderer's own guard so a longer
#: list cannot push the footer off a short panel.
MAX_ROWS = 20

#: The concentration question the footer answers. Three, because three wallets
#: acting together is the smallest group a reader treats as one actor.
TOP_N = 3

TABLE_ID = "surf-pool4u-stakers-table"
_FOOTER_ID = "surf-pool4u-stakers-footer"
_TITLE_ID = "surf-pool4u-stakers-title"

#: Column budgets, in **terminal cells**, measured against the widest value
#: each column can hold rather than against today's data:
#:
#: * rank -- ``MAX_ROWS`` is two digits, so three cells covers ``20`` and the
#:   ``#`` header both;
#: * address -- ``_fmt.long_addr``'s form exactly: ``0x`` + 8 hex + ``…`` +
#:   6 hex;
#: * IMD -- ``fmt_compact`` tops out at ``999.9B`` (six) and a grouped integer
#:   below 1000 at ``999`` (three), so ten cells leaves room for the header and
#:   for a magnitude this vault has not reached;
#: * share -- ``100.0%`` is six.
_RANK_COLS = 3
_ADDR_COLS = 17
_IMD_COLS = 10
_PCT_COLS = 6

#: What ``DataTable`` spends on each column *beyond* the width asked for: one
#: cell of padding either side. Measured rather than assumed -- the two pins
#: below are compared against composited output by
#: ``test_the_stakers_width_pins_are_what_the_table_actually_paints``, which
#: uses ``==`` and therefore reddens whether a pin is set too low or too high.
#:
#: This is why ``_rowfit.row_cols`` is **not** used for these two numbers even
#: though ``clip``/``pad`` from that module fit every cell: ``row_cols``
#: charges ``GAP`` *between* present cells, which is a ``RichLog`` row's
#: arithmetic. A ``DataTable`` pads every column including the last, so the two
#: formulas differ by a gap and a trailing pad, and borrowing the wrong one
#: would put a marker a column or two off the width it is marking.
_CELL_PADDING = 2

#: Widest full-tier row.
FULL_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_RANK_COLS, _ADDR_COLS, _IMD_COLS, _PCT_COLS)
)

#: One tier down: the share **column** goes -- removed, not blanked. Writing
#: empty cells into a fixed-width column frees nothing, so a "compact" tier
#: that did that would light the widen marker and still overflow by exactly
#: the width it claimed to have shed.
#:
#: The share is the right cell to lose *on this panel specifically* even though
#: concentration is the panel's subject, because the footer states
#: concentration for the whole vault in one line and survives every tier. The
#: per-row share is the restatement; the address and the amount are not
#: restated anywhere.
COMPACT_WIDTH = sum(
    cols + _CELL_PADDING for cols in (_RANK_COLS, _ADDR_COLS, _IMD_COLS)
)


def _fmt_imd_cell(value) -> str:
    """A staker's IMD holding, fitted to :data:`_IMD_COLS`.

    ``fmt_compact`` above 1000 (``184.2K``), grouped integers below it, and
    ``--`` on an unread amount -- never ``0``, which would rank a wallet as
    holding nothing when we simply could not convert its shares.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) >= 1000:
        return fmt_compact(v)
    return f"{v:,.0f}"


def staker_cells(row: object) -> tuple[str, str, str, str] | None:
    """Decompose one staker row into its four raw cells; ``None`` drops it.

    A single malformed row must never take the panel down, so every failure
    here is a dropped row rather than an exception.

    **Two spellings of the address are accepted and that is a reported defect,
    not a convenience.** ``surf_models.POOL4_STAKERS_KEYS`` documents the row
    shape as ``rank/addr/imd/pct`` while the plan's own producer
    (``surf_pool4_market.staker_rows``) emits ``address``; unlike
    ``pool4_flow`` and ``pool4_hatches``, ``pool4_stakers`` has no
    ``SURF_ROW_KEYS`` entry to settle it. Reading one spelling would paint a
    column of dashes if the other landed. Filed for WP0/WP4 to resolve; when
    it is, drop the fallback.
    """
    if not isinstance(row, dict):
        return None
    try:
        rank = row.get("rank")
        rank_text = f"{int(rank)}" if rank is not None else DASH
        addr = row.get("address")
        if addr is None:
            addr = row.get("addr")
        pct = as_float(row.get("pct"))
        pct_text = f"{pct:.1f}%" if pct is not None else DASH
        return rank_text, long_addr(addr), _fmt_imd_cell(row.get("imd")), pct_text
    except Exception:
        return None


def footer_line(count, top_pct) -> str:
    """``66 addresses · top 3 = 32% of vault`` -- plain text, already fitted.

    ``top_pct is None`` renders ``top 3 = --`` and never a number computed
    from the visible rows: the fold was incomplete, and a subset's share is a
    smaller number than the truth (PRD §7.4).

    ``count is None`` drops the addresses clause rather than printing
    ``-- addresses``: the concentration half is the half a reader acts on and
    it should not be pushed along by a dash.
    """
    parts: list[str] = []
    n = as_float(count)
    if n is not None:
        parts.append(f"{int(n):,} addresses")
    pct = as_float(top_pct)
    shown = f"{pct:.0f}%" if pct is not None else DASH
    parts.append(f"top {TOP_N} = {shown} of vault")
    return " · ".join(parts)


class SurfPool4UStakers(Vertical):
    """STAKERS: rank, address, IMD, share of vault, over a concentration line."""

    DEFAULT_CSS = """
    SurfPool4UStakers > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfPool4UStakers > DataTable {
        height: 1fr;
        min-height: 4;
    }
    """

    #: ``> Static``'s own ``padding: 0 1`` eats a column each side of the
    #: child's content box, so a fit decision compares against
    #: ``self.size.width`` minus two, never ``self.size.width``.
    #: ``SurfPool4Hatches._TITLE_PADDING_COLS`` records the same mistake being
    #: made and fixed one panel over.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._widen = False
        self._tier = "full"
        #: Which tier's columns are currently *on* the table. Tracked apart
        #: from ``_tier`` so the columns are rebuilt exactly when the tier
        #: moves and never on an ordinary repaint -- ``clear(columns=True)``
        #: on every poll would flush the header row and the reader's scroll
        #: position with it.
        self._columns_tier: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID)
        yield DataTable(id=TABLE_ID)
        yield Static(Text(""), id=_FOOTER_ID)

    def on_mount(self) -> None:
        try:
            table = self.query_one(f"#{TABLE_ID}", DataTable)
        except Exception:  # pragma: no cover - not composed
            return
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._install_columns(table, self._tier)

    def _install_columns(self, table: DataTable, tier: str) -> None:
        """(Re)build the header for *tier*; a no-op when it is already there."""
        if self._columns_tier == tier:
            return
        try:
            table.clear(columns=True)
            table.add_column("#", width=_RANK_COLS, key="rank")
            table.add_column("address", width=_ADDR_COLS, key="address")
            table.add_column("IMD", width=_IMD_COLS, key="imd")
            if tier == "full":
                table.add_column("share", width=_PCT_COLS, key="pct")
        except Exception:  # pragma: no cover - defensive
            return
        self._columns_tier = tier

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_stakers=None,
        pool4_staker_count=None,
        pool4_staker_top3_pct=None,
        pool4_stakers_as_of_hhmm=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        ``pool4_as_of_hhmm`` is accepted and **not rendered** -- see the module
        docstring. It is in the signature because every pool4 panel spells that
        key in full, and the contract test that pins it is what stops a second
        body eliding it to ``as_of_hhmm`` and making one kwarg name answer for
        two different contract keys.
        """
        self._payload = {
            "rows": pool4_stakers,
            "count": pool4_staker_count,
            "top3_pct": pool4_staker_top3_pct,
            "as_of": pool4_stakers_as_of_hhmm,
            "network": pool4_network,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _render_view(self) -> None:
        budget = self._text_budget()
        self._widen = bool(budget) and budget < FULL_WIDTH
        self._tier = "compact" if self._widen else "full"
        self._render_title()
        self._render_rows()
        self._render_footer()

    def _render_title(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
        except Exception:  # not composed yet
            return
        title.update(
            Text(
                title_text(
                    TITLE,
                    self._payload.get("network"),
                    self._widen,
                    self._text_budget(),
                ),
                style="dim",
            )
        )

    def _render_rows(self) -> None:
        try:
            table = self.query_one(f"#{TABLE_ID}", DataTable)
        except Exception:  # not composed yet
            return
        self._install_columns(table, self._tier)
        try:
            table.clear()
        except Exception:  # pragma: no cover - columns not added yet
            return

        rows = self._payload.get("rows")
        if not isinstance(rows, list):
            return
        for row in rows[:MAX_ROWS]:
            cells = staker_cells(row)
            if cells is None:
                continue
            rank, addr, imd, pct = cells
            # Escape AFTER fitting: ``clip`` measures cells and an escaped
            # ``\\[`` is two characters and one cell, so escaping first
            # misaligns every column and can cut an escape pair in half.
            # DataTable defers ``Text.from_markup`` into its idle handler, so
            # an unescaped ``[/x]`` in a chain-sourced address crashes the app
            # from inside the message pump.
            values = [
                safe_markup(pad(clip(rank, _RANK_COLS), _RANK_COLS)),
                safe_markup(clip(addr, _ADDR_COLS)),
                safe_markup(pad(clip(imd, _IMD_COLS), _IMD_COLS)),
            ]
            if self._tier == "full":
                values.append(safe_markup(clip(pct, _PCT_COLS)))
            try:
                table.add_row(*values)
            except Exception:
                continue

    def _render_footer(self) -> None:
        try:
            footer = self.query_one(f"#{_FOOTER_ID}", Static)
        except Exception:  # not composed yet
            return

        payload = self._payload
        rows = payload.get("rows")
        markup: list[str] = []
        if not payload.get("seen") or rows is None:
            markup.append(f"[yellow]⚠ {safe_markup(UNAVAILABLE_LINE)}[/]")
        elif not rows:
            markup.append(f"[dim]{safe_markup(EMPTY_LINE)}[/]")
        else:
            markup.append(
                f"[dim]{safe_markup(footer_line(payload.get('count'), payload.get('top3_pct')))}[/]"
            )

        as_of = strip_tags(payload.get("as_of"))
        if as_of:
            markup.append(f"[dim]as of {safe_markup(as_of)}[/]")

        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            footer.update(join_lines(lines))
        except Exception:  # pragma: no cover - parse already guarded
            pass
