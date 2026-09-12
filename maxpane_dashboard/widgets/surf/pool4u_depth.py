"""IF IMD FALLS: what the hook's own liquidity bids as IMD's price falls.

The EV-table slot on the `4` body. Five rungs -- a fall in IMD's price, the ETH
the hook's position would pay out to get there, and how much of the backstop
band that consumes.

**A quote, never a promise, and the title says so in its own words.** These are
what the position bids *as it stands now*. A ``rebalance()`` closes the backstop
band and redeploys it from just above spot, so every number on this panel can
move the moment a keeper acts -- and the band that is under a reader at 14:02
may be somewhere else at 14:03 with nothing on screen having gone red. PRD §8.2
therefore forbids four words here outright: *guaranteed*, *protected*, *safe*,
and *floor* in the protective sense. THE RATCHET, one panel over on the ``p``
body, carries the same rule under the name ``observed``-not-``guaranteed``, and
both are pinned by a forbidden-word test against **composited** output rather
than against this file's source: a source grep passes while a reader sees
something else, which is the known-fake shape in this repo's taxonomy.

The ladder is computed here, and why that is not a layering mistake
------------------------------------------------------------------
``analytics/surf_pool4_depth.depth_rows`` is a pure stdlib function and this
panel calls it directly on five frozen payload keys -- ``pool4_current_tick``,
``pool4_position_liquidity``, ``pool4_backstop_lower_tick``,
``pool4_backstop_liquidity`` and ``pool4_backstop_state``.

The plan specified a ``pool4_depth_rows`` payload key instead. **There is no
such key**: WP0 froze the contract without it, and
``test_surf_widget_contract.py::test_update_data_kwargs_are_frozen_contract_keys``
refuses any ``update_data`` kwarg that is not in ``SURF_KEYS``, so the key could
not be introduced from this side. That is the same gap carry-over C1 found under
``pool4_backstop_distance_pct``, and it has the same cure: the conversion lives
once, in the analytics module that already owns every other tick conversion on
this view, and the widget imports it. CLAUDE.md permits exactly this -- *widgets
may import pure ``analytics/``; they may not import ``data/``* -- and the
allowance is proved rather than asserted:
``test_surf_widget_contract._PURE_ANALYTICS_ALLOWED`` names the module and
``test_the_allowed_analytics_modules_are_themselves_pure`` AST-walks its own
imports, and every ``maxpane_dashboard.analytics.*`` reachable from there, to a
fixed point.

``depth_rows`` returning ``None`` is a whole-panel unavailable state and is
**never** a ladder of zeros: a zero ladder paints "this pool bids nothing",
which is a confident wrong answer to a question we could not answer at all. No
band deployed is *not* that case -- the full-range position still bids, so the
ladder is real and ``band used`` is a true ``0.0%``.

``band used`` has THREE states, and the third one is why this panel was
re-opened (PRD 6.5, AMENDED 2026-09-11)
---------------------------------------------------------------------------
The panel exists to answer *how much is bidding under me*, so ``band used``
carries the whole weight of that question -- and until 2026-09-11 it answered
``0.0%`` both when there was no band and when nobody could read one. Measured
through the real ``SurfScreen`` at (143, 60): with ``pool4_backstop_liquidity``
set to ``0`` and then to ``None``, this column was **byte-identical**. That is
CLAUDE.md's curator-rail defect one layer out -- ``band used 0.0%`` through an
outage tells a reader, with confidence, that the backstop is not helping them,
when the truth is that nobody looked.

``pool4_backstop_state`` is the fifth ladder input for exactly that reason, and
the unread state paints :data:`UNREAD_BAND` -- the **word** ``unknown``, not a
dash. A dash is this panel's "unreadable number" glyph and already means
something in the ``ETH paid`` column beside it; a reader scanning a column of
percentages reads ``--`` as a small one far more readily than as an absent one.
A word with no digits in it cannot be misread as a quantity at all.

A fixed width, since 2026-09-12
-------------------------------
This is the one panel on the ``4`` body whose column is a **constant** rather
than a share of the terminal: :data:`PANEL_COLUMNS`. The owner asked for it
narrower off the live screen ("half of its space is empty") and for the
columns to go to STAKERS beside it, and a ``fr`` seam cannot deliver that --
a ratio hands this panel a proportion, so it grows straight back on a wide
terminal. A fixed column hands every extra column to the leaderboard at every
width. The number itself is the caption's, not the table's; see
:data:`PANEL_COLUMNS` for why that is a floor and what it would take to move
it.

Shape, shared primitives and the ``$`` trap
-------------------------------------------
A ``DataTable`` under its own title and over a caption, on
``widgets/surf/pool4u_stakers.py``'s shape: fixed column widths measured in
terminal cells, ``_rowfit.clip``/``pad`` (both on :func:`rich.cells.cell_len`,
never ``len()``) and columns *removed* rather than blanked on the narrow tier,
because writing empty cells into a fixed-width column frees nothing.

Title, network word and widen marker come from ``widgets/surf/_pool4.py`` --
imported, never restated. Two packages once wrote ``network_word`` twice with
different behaviour on unknown input, and one body painted ``THE SPLIT · —``
beside ``THE RATCHET · BASE``.

``DataTable`` defers ``Text.from_markup`` into its idle handler, so every cell
is escaped before it goes in; the caption reaches ``Static`` as a pre-built
``rich.text.Text`` parsed inside ``_pool4.parse_line``'s own ``try``. Styles are
Rich colour names only: Rich cannot resolve Textual's ``$``-prefixed theme
variables, and such a token parses cleanly then raises ``MissingStyle`` at
render time, inside ``Static.update``, outside this module's ``try``.

Purity: stdlib, ``rich``, ``textual``, this package's primitives and the one
allowlisted analytics module. No ``data/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.surf_pool4_depth import depth_rows
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float
from maxpane_dashboard.widgets.surf._pool4 import (
    TITLE_CLASS,
    join_lines,
    parse_line,
    market_title_text,
)
from maxpane_dashboard.widgets.surf._rowfit import clip, pad

__all__ = [
    "CAPTION",
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "HEADERS",
    "PANEL_COLUMNS",
    "TABLE_ID",
    "TITLE",
    "UNAVAILABLE_LINE",
    "UNREAD_BAND",
    "SurfPool4UDepth",
    "ladder_cells",
]

#: Panel title. The network word is appended by ``_pool4.market_title_text``
#: -- on every network except ``MAINNET``, which this body leaves unsaid -- and a hint
#: after that, both appended and never substituted, so ``"IF IMD FALLS" in
#: text`` holds at every width and in every state.
#:
#: A conditional, not a claim: it names the scenario the rows are quotes for.
#: ``DOWNSIDE PROTECTION`` was the obvious alternative and is the exact word
#: PRD §8.2 forbids.
TITLE = "IF IMD FALLS"

#: The line under the table, and the reason the panel is honest. It carries the
#: word ``now`` because *when* the quote is from is the whole of §8.2: a
#: rebalance relocates the band, so a ladder with no tense on it reads as a
#: standing commitment. ``as it stands`` rather than ``currently`` so the
#: sentence names the **position** as the thing that may change, not the price.
CAPTION = "quoted from the position as it stands now"

#: How many terminal columns this panel is given on the ``4`` body, and the
#: **only** panel on that body whose width is a constant rather than a share.
#:
#: Restated here, not imported -- the number lives in CSS, in
#: ``SurfScreen.DEFAULT_CSS`` and in ``themes/minimal.tcss``, and a stylesheet
#: cannot read Python. ``test_the_ladder_column_is_exactly_the_width_of_its_own
#: _caption`` reads all three back off composited output and asserts they agree,
#: so a seam edit in either CSS copy reddens rather than silently re-widening
#: the panel the owner asked to shrink.
#:
#: WHAT IT IS MADE OF, and it is not the table. :data:`FULL_WIDTH` is 27 cells;
#: :data:`CAPTION` is **41**, and the caption is the widest thing this panel
#: paints. Add the two columns of the panel's own ``padding: 0 1`` and the two
#: the caption's ``Static`` takes for its own and the answer is 45, measured in
#: situ rather than added up.
#:
#: **AND IT IS A FLOOR, NOT A PREFERENCE.** Below 45 this panel's caption is cut
#: by CSS with an ellipsis and **no ``‹`` marker**: the widen tier is decided
#: from :data:`FULL_WIDTH`, the table's width, so between 31 and 44 columns the
#: sentence that says these numbers are a quote rather than a promise goes
#: quietly missing while the title claims everything fits. That is the standing
#: "a panel that can bind must be able to mark" rule failing, and it is why the
#: request to make this panel "quite less" wide stops at 45 rather than at the
#: table's 29. Shortening :data:`CAPTION` would move this number; PRD §8.2 owns
#: that sentence, so it was measured (29 cells or fewer would hold
#: ``screens/surf.SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` at 105) and not spent.
PANEL_COLUMNS = 45

#: Nothing could be read -- ``depth_rows`` returned ``None`` because the tick or
#: the position's liquidity was unavailable. A rendered sentence, never an empty
#: table: an empty table under a live title bar is what a hook bidding nothing
#: looks like.
UNAVAILABLE_LINE = "ladder unavailable"

#: ``band used`` when the band itself was not read -- ``pool4_backstop_state``
#: is ``None``, or it says ``deployed`` and the band's numbers are missing.
#:
#: A word rather than a dash, and the difference is the point of WP11. ``--`` is
#: what ``_fmt_eth`` already paints for an unreadable ETH leg one column over,
#: so re-using it here would make "the band is unknown" and "this number is
#: small/unavailable" the same mark in two adjacent columns. ``unknown``
#: contains no digit and no percent sign, so it cannot be read as ``0.0%`` by a
#: reader skimming the column -- which is the exact misreading this panel
#: shipped with. Seven cells, inside :data:`_USED_COLS`.
UNREAD_BAND = "unknown"

TABLE_ID = "surf-pool4u-depth-table"
_TITLE_ID = "surf-pool4u-depth-title"
_CAPTION_ID = "surf-pool4u-depth-caption"

#: Column headers, in render order. ``band used`` and not ``band left``: the
#: consumed share grows as the fall deepens, and a reader tracking "how much is
#: gone" reads a rising number the same way on every row.
HEADERS: tuple[str, ...] = ("fall", "ETH paid", "band used")

#: Column budgets in **terminal cells**, measured against the widest value each
#: column can hold rather than against today's data:
#:
#: * fall -- ``-50%`` is four, and the header ``fall`` is four;
#: * ETH paid -- ``9,999.99`` is eight, which covers a pool far deeper than
#:   this one and the header besides;
#: * band used -- ``100.0%`` is six, and ``band used`` is nine.
_MOVE_COLS = 4
_ETH_COLS = 8
_USED_COLS = 9

#: What ``DataTable`` spends on each column *beyond* the width asked for: one
#: cell of padding either side. ``_rowfit.row_cols`` is deliberately not used
#: for the two pins below -- it charges a gap *between* present cells, which is
#: a ``RichLog`` row's arithmetic, while a ``DataTable`` pads every column
#: including the last. The two formulas differ by a gap and a trailing pad, and
#: borrowing the wrong one puts the widen marker a column or two off the width
#: it is marking. ``SurfPool4UStakers`` records the same decision.
_CELL_PADDING = 2

#: Widest full-tier row.
FULL_WIDTH = sum(
    cols + _CELL_PADDING for cols in (_MOVE_COLS, _ETH_COLS, _USED_COLS)
)

#: One tier down: the ``band used`` **column** goes -- removed, not blanked.
#:
#: It is the right cell to lose on this panel even though the band is what makes
#: the hook interesting, because it is the only column that is a *share of*
#: something rather than a quantity: ``ETH paid`` already rises with the band's
#: contribution, so losing the share costs resolution and not a fact. Dropping
#: ``ETH paid`` instead would leave a table of percentages of a number no longer
#: on screen.
COMPACT_WIDTH = sum(cols + _CELL_PADDING for cols in (_MOVE_COLS, _ETH_COLS))


def _fmt_eth(value) -> str:
    """ETH at two decimals, grouped; ``--`` on an unreadable rung.

    Never ``0.00`` for an unread value. A zero here is a real answer -- the
    price did not reach that rung's range -- and the dash has to stay available
    to mean something else.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.2f}"


def ladder_cells(row: object) -> tuple[str, str, str] | None:
    """Decompose one ladder rung into its three raw cells; ``None`` drops it.

    ``band_used_pct`` of ``None`` becomes :data:`UNREAD_BAND` and never the
    dash: an unread band is a *different* statement from an unreadable number,
    and this is the only cell on the panel that can make it.

    A single malformed rung must never take the panel down, so every failure
    here is a dropped row rather than an exception. The rows come from this
    repo's own pure function rather than from a chain read, so a malformed one
    is a bug and not hostile input -- but the panel degrades identically either
    way, and that is cheaper than being right about which it was.
    """
    if not isinstance(row, dict):
        return None
    try:
        move = as_float(row.get("move_pct"))
        move_text = f"-{int(move)}%" if move is not None else DASH
        used = as_float(row.get("band_used_pct"))
        used_text = f"{used:.1f}%" if used is not None else UNREAD_BAND
        return move_text, _fmt_eth(row.get("eth_paid")), used_text
    except Exception:
        return None


class SurfPool4UDepth(Vertical):
    """IF IMD FALLS: the hook's bid ladder, quoted from the position now."""

    DEFAULT_CSS = """
    SurfPool4UDepth > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfPool4UDepth > DataTable {
        height: 1fr;
        min-height: 4;
    }
    SurfPool4UDepth > .pool4u-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1`` eats a column each side of the
    #: child's content box, so a fit decision compares against
    #: ``self.size.width`` minus two, never ``self.size.width``. The same
    #: number, for the same reason, as ``SurfPool4UStakers``'s.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._widen = False
        self._tier = "full"
        #: Which tier's columns are currently *on* the table. Tracked apart
        #: from ``_tier`` so the header is rebuilt exactly when the tier moves
        #: and never on an ordinary repaint -- ``clear(columns=True)`` every
        #: poll would flush the header row and the reader's scroll with it.
        self._columns_tier: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID,
                     classes=TITLE_CLASS)
        yield DataTable(id=TABLE_ID)
        yield Static(Text(""), id=_CAPTION_ID)

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
            table.add_column(HEADERS[0], width=_MOVE_COLS, key="move")
            table.add_column(HEADERS[1], width=_ETH_COLS, key="eth")
            if tier == "full":
                table.add_column(HEADERS[2], width=_USED_COLS, key="used")
        except Exception:  # pragma: no cover - defensive
            return
        self._columns_tier = tier

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_current_tick=None,
        pool4_position_liquidity=None,
        pool4_backstop_lower_tick=None,
        pool4_backstop_liquidity=None,
        pool4_backstop_state=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        The five inputs are the ladder's arguments, not its output -- see the
        module docstring for why there is no ``pool4_depth_rows`` key to take
        instead, and for why ``pool4_backstop_state`` is one of them rather
        than something this panel infers from the other four. Every kwarg carries its full ``pool4_`` contract prefix and is
        a member of ``SURF_KEYS``.

        ``**_kwargs`` is mandatory: the screen splats the whole payload, so a
        key added tomorrow must be ignored rather than raise.

        **``pool4_as_of_hhmm`` is accepted and not rendered** (2026-09-12).
        The ``4`` MARKET body prints one ``as of`` marker, on the screen's own
        title row, and no panel repeats it -- see ``_pool4``'s *One clock on
        the `4` body* section for the whole of that decision, and for the one
        panel it does not settle.
        The kwarg stays in the signature because every pool4 panel spells
        every contract key in full (``test_no_pool4_widget_needs_a_kwarg_
        alias``), and dropping it would leave the screen's splat handing it to
        ``**_kwargs`` with nothing recording why.
        """
        self._payload = {
            "tick": pool4_current_tick,
            "position_liquidity": pool4_position_liquidity,
            "band_lower_tick": pool4_backstop_lower_tick,
            "band_liquidity": pool4_backstop_liquidity,
            "band_state": pool4_backstop_state,
            "network": pool4_network,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def rows(self) -> list[dict] | None:
        """The ladder for the current payload, or ``None`` when unreadable.

        ``depth_rows`` is keyword-only by design: two tick arguments and two
        liquidity arguments side by side is exactly the signature where a
        positional swap is silent, so it is a ``TypeError`` instead.
        """
        payload = self._payload
        if not payload:
            return None
        try:
            return depth_rows(
                tick=payload.get("tick"),
                position_liquidity=payload.get("position_liquidity"),
                band_lower_tick=payload.get("band_lower_tick"),
                band_liquidity=payload.get("band_liquidity"),
                band_state=payload.get("band_state"),
            )
        except Exception:
            return None

    def _render_view(self) -> None:
        budget = self._text_budget()
        self._widen = bool(budget) and budget < FULL_WIDTH
        self._tier = "compact" if self._widen else "full"
        rows = self.rows()
        self._render_title()
        self._render_rows(rows)
        self._render_caption(rows)

    def _render_title(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
        except Exception:  # not composed yet
            return
        # ``market_title_text``, not ``title_text``: this is the ``4`` body,
        # and it is the one that leaves ``MAINNET`` unsaid. The ``p`` body's
        # five panels go on printing it -- see ``_pool4.QUIET_NETWORK`` for
        # why silence is available for exactly one network and nothing else.
        title.update(
            Text(
                market_title_text(
                    TITLE,
                    self._payload.get("network"),
                    self._widen,
                    self._text_budget(),
                ),
                style="dim",
            )
        )

    def _render_rows(self, rows) -> None:
        try:
            table = self.query_one(f"#{TABLE_ID}", DataTable)
        except Exception:  # not composed yet
            return
        self._install_columns(table, self._tier)
        try:
            table.clear()
        except Exception:  # pragma: no cover - columns not added yet
            return
        if not isinstance(rows, list):
            return
        for row in rows:
            cells = ladder_cells(row)
            if cells is None:
                continue
            move, eth, used = cells
            # Escape AFTER fitting: ``clip`` measures cells and an escaped
            # ``\\[`` is two characters for one cell, so escaping first
            # misaligns every column and can cut an escape pair in half.
            values = [
                safe_markup(pad(clip(move, _MOVE_COLS), _MOVE_COLS)),
                safe_markup(pad(clip(eth, _ETH_COLS), _ETH_COLS)),
            ]
            if self._tier == "full":
                values.append(safe_markup(pad(clip(used, _USED_COLS), _USED_COLS)))
            try:
                table.add_row(*values)
            except Exception:
                continue

    def _render_caption(self, rows) -> None:
        try:
            caption = self.query_one(f"#{_CAPTION_ID}", Static)
        except Exception:  # not composed yet
            return

        markup: list[str] = []
        if not self._payload.get("seen") or rows is None:
            markup.append(f"[yellow]⚠ {safe_markup(UNAVAILABLE_LINE)}[/]")
        else:
            markup.append(f"[dim]{safe_markup(CAPTION)}[/]")

        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            caption.update(join_lines(lines))
        except Exception:  # pragma: no cover - parse already guarded
            pass
