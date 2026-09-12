"""The `4` body's leaderboard slot: STAKERS -- who holds the sIMD vault.

**The ranking is not the point; concentration is** (PRD §6.1). Whether three
wallets can walk out of this vault is a risk a reader acts on, and the footer
is where this panel says so. The rows are the evidence for the footer, not the
other way round.

Its own clock, and what became of it (2026-09-12)
-------------------------------------------------
The rows behind this panel come from ``TIER_POOL4_STAKERS`` -- a full sIMD
``Transfer`` history fold on curator's ``TIER_ANALYSIS`` precedent, far too
expensive for the 600 s pool4 sweep. So the panel carried
``pool4_stakers_as_of_hhmm``, **its own, slower marker**, and never the body's
``pool4_as_of_hhmm``: a panel whose numbers can be half an hour old sitting
under a clock that says seconds is a stale number presented as live, which is
the failure CLAUDE.md's "as of" rule exists to prevent.

**The marker is gone; the property it protected is not.** The owner read the
live screen and asked for every per-panel ``as of`` on the ``4`` body removed
-- see ``_pool4``'s *One clock on the `4` body* for the request and for why it
cost the other four panels nothing. It could not cost this one nothing: the
same live cache had this fold at 13:52 against a title bar reading 15:33, so
deleting the marker alone would have left hour-old rows under a clock that
says *now*, which is exactly the sentence above.

What replaced it is **conditional and rides a line that already exists**: the
concentration footer gains the word ``stale`` when the two markers are further
apart than healthy operation can put them, and says nothing when they are not
(:data:`STALE_WORD`, :data:`STALE_AFTER_S`, :func:`fold_is_stale`). Both
markers are therefore still taken -- one is subtracted from the other -- and
neither is printed. The PRD's §7.2 decision to give this panel its own clock
is amended rather than reversed: the *slower tier* is still the reason this
panel is special, and the word is what says so on screen.

Three reasons to be empty, three sentences
------------------------------------------
The sweep is **detached**, so tick 1's payload is always built before the first
fold can land and an empty panel is the ordinary state of a healthy launch.
``pool4_stakers`` is ``None`` for that, for a sweep in flight, and for a sweep
that failed -- and this panel painted ``⚠ stakers unavailable`` for all three
until 2026-09-12. ``pool4_stakers_state`` is what tells them apart, and the
rule here is ``⚠`` **iff** ``failed``: see :func:`no_rows_line`.

``top 3 = --`` is a real state
------------------------------
``pool4_staker_top3_pct`` is ``None`` on an **incomplete** fold, and the footer
renders the dash rather than computing a fallback from the rows it happens to
have. Ranking a subset understates concentration -- the one direction that
makes a risk look smaller than it is -- and this is ``clean_routed_eth``'s
guard verbatim (PRD §7.4).

Addresses
---------
Chain-sourced, therefore escaped, and **not shortened at all** since
2026-09-12: ``_fmt.full_addr`` renders all 42 characters into a 42-cell column.

It went through two shorteners before that. The leaderboard template's
``_short_addr`` (``0xABCD..1234``) was rejected first, because live spoofs of
surf's own fee recipients collide with the real addresses on first-6/last-4;
``_fmt.long_addr``'s wider window (``0xf53c0a4E…8e3364``) survived that attack
and was what this panel shipped with. The owner read the live screen and asked
for the whole address, and the argument for it is the same one that rejected
``_short_addr`` taken one step further: a panel whose entire subject is *which*
wallets hold the vault is the last place to make a reader reconstruct an
address, and the last place to leave a window an attacker gets to aim at.

**It is paid for in columns and the number is on the record.** The address
column went 17 -> 42, :data:`FULL_WIDTH` went 44 -> 69, what this panel
needs on screen went 48 -> 73, and
``screens/surf.SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` went 105 -> 119
(the body paid fourteen of the twenty-five; IF IMD FALLS gave seven back
and the top row was already carrying the rest). Nothing
else on the body was shortened to absorb it -- see that constant's block for
what the bottom row's seam spends and what it got back from IF IMD FALLS.
``long_addr`` itself is untouched and its other two callers (HATCHES on the
``p`` body, the dashboard body's activity feed) render exactly as before.

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
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_compact,
    full_addr,
)
from maxpane_dashboard.widgets.surf._pool4 import (
    TITLE_CLASS,
    join_lines,
    parse_line,
    strip_tags,
    market_title_text,
)
from maxpane_dashboard.widgets.surf._rowfit import clip, pad

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "MAX_ROWS",
    "PENDING_LINE",
    "STALE_AFTER_S",
    "STALE_WORD",
    "STAKER_STATES",
    "SWEEPING_LINE",
    "TABLE_ID",
    "TITLE",
    "TOP_N",
    "UNAVAILABLE_LINE",
    "SurfPool4UStakers",
    "fold_is_stale",
    "footer_line",
    "no_rows_line",
    "staker_cells",
]

TITLE = "STAKERS"

#: ``data/surf_models.POOL4_STAKERS_STATES`` **restated**, not imported: a
#: widget may not import ``data/`` (it imports ``httpx`` two hops on), and
#: ``_pool4.POOL4_NETWORKS`` records the same restatement one panel over.
#: ``tests/widgets/test_surf_pool4u_left.py`` imports both and asserts they
#: agree in both directions, so a fourth word reddens the suite instead of
#: falling through this module's ``else`` and looking like ``pending``.
STAKER_STATES: tuple[str, ...] = ("pending", "sweeping", "failed")
_PENDING, _SWEEPING, _FAILED = STAKER_STATES

#: An attempt was made and it FAILED. The only line on this panel that wears
#: the warning, and the only state that has ever deserved it.
UNAVAILABLE_LINE = "stakers unavailable"

#: A fold is in flight right now. Neutral, dim, no ``⚠`` -- the sweep is a
#: multi-minute ``Transfer`` walk and this is what a reader sees for most of a
#: cold start.
SWEEPING_LINE = "sweeping the vault …"

#: Nothing has been swept yet and nothing is in flight -- usually because the
#: pool4 sweep has not named a vault for this one to walk. Also the line an
#: ``unknown`` state falls to, because the rule on this panel is ``⚠`` **iff**
#: ``failed``: an absent word is not evidence of a fault.
PENDING_LINE = "stakers not swept yet"

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

#: The word the footer gains when this panel's fold has fallen further behind
#: the body's own clock than healthy operation can put it -- and **nothing at
#: all** when it has not.
#:
#: A word rather than a timestamp, on purpose. Until 2026-09-12 this panel
#: printed ``as of 13:52`` under its rows; the owner read the live screen and
#: asked for every per-panel ``as of`` on this body gone. The other four went
#: and cost nothing (see ``_pool4``'s *One clock on the `4` body*), but this
#: one was the one marker on the body that was **not** saying what the title
#: row already said: measured off the live cache, the body's clock read 15:29
#: against a 15:33 title bar and this panel's read **13:52**. Dropping it with
#: no replacement would put hour-old rows under a title row that reads *now*,
#: which is the failure CLAUDE.md's ``as of`` rule exists to prevent.
#:
#: So it is :data:`_pool4.QUIET_NETWORK`'s shape rather than a marker's: a word
#: that prints only when there is something to say. In the ordinary case it is
#: silent and the footer reads exactly as it did before, which is what the
#: request asked for; it spends **no row** either way, because it rides the
#: concentration line this panel was already painting.
STALE_WORD = "stale"

#: How far behind ``pool4_as_of_hhmm`` this panel's own marker has to fall
#: before :data:`STALE_WORD` prints, in seconds.
#:
#: DERIVED, NOT FELT. The quantity is the **difference between two markers**,
#: so each one contributes its own tier's worth of ordinary lag:
#:
#: * this panel's rows ride ``surf_cache.TIER_POOL4_STAKERS`` (**1800 s**), so
#:   in perfect health the fold is anything from brand new to a full tier old
#:   before the next one is even due;
#: * the marker it is compared against rides ``TIER_POOL4`` (**600 s**), and
#:   the worst case for this subtraction is that clock having *just* advanced
#:   while the staker fold sits at its own age.
#:
#: 1800 + 600 = **2400 s**, and that is the largest gap healthy operation can
#: produce. Anything past it means the staker tier came due and did not land --
#: a missed cycle, not a slow one. The threshold is therefore not a taste
#: judgement and cannot be tuned by feel: if either TTL moves, this number is
#: wrong by exactly the amount that one moved, and
#: ``test_the_stale_threshold_is_the_two_tiers_it_is_derived_from`` reddens.
#:
#: Deliberately **not** the bare 1800: a fold that is 1800 s old is a fold the
#: tier has only just made due, which is the most ordinary state this panel
#: has. Firing there would print the word most of the time and it would stop
#: meaning anything -- which is the same reason ``⚠`` on this panel is
#: reserved for ``failed`` and is not the default.
#:
#: The live case that motivated it sat at **5,820 s** (13:52 against 15:29),
#: two and a half times past this line.
STALE_AFTER_S = 2400.0

#: HH:MM and nothing else. Both markers are formatted by the manager, but a
#: *persisted* payload is third-party input too, so the parse is total.
_HHMM_LEN = 5

#: Half a day, in minutes -- the point past which a positive modular
#: difference is better read as "this panel's marker is AHEAD of the body's"
#: than as "it is twenty-three hours behind". Both markers are wall-clock
#: HH:MM with no date, so midnight has to be crossed by arithmetic.
_HALF_DAY_MIN = 12 * 60

TABLE_ID = "surf-pool4u-stakers-table"
_FOOTER_ID = "surf-pool4u-stakers-footer"
_TITLE_ID = "surf-pool4u-stakers-title"

#: Column budgets, in **terminal cells**, measured against the widest value
#: each column can hold rather than against today's data:
#:
#: * rank -- ``MAX_ROWS`` is two digits, so three cells covers ``20`` and the
#:   ``#`` header both;
#: * address -- the **whole** address: ``0x`` + 40 hex is 42 cells, and
#:   ``_fmt.full_addr`` never returns more than the chain can hold. It was 17
#:   (``long_addr``'s window) until 2026-09-12; the twenty-five columns that
#:   move is the single largest thing in this panel's width and the reason
#:   ``screens/surf.SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` moved with it;
#: * IMD -- ``fmt_compact`` tops out at ``999.9B`` (six) and a grouped integer
#:   below 1000 at ``999`` (three), so ten cells leaves room for the header and
#:   for a magnitude this vault has not reached;
#: * share -- ``100.0%`` is six.
_RANK_COLS = 3
_ADDR_COLS = 42
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

    **``address``, one spelling.** The shape was specified two ways while this
    panel was being written -- ``POOL4_STAKERS_KEYS``'s comment said
    ``rank/addr/imd/pct`` and the producer (``surf_pool4_market.staker_rows``)
    emitted ``address`` -- and this function carried an ``addr`` fallback so
    that whichever landed, the column could not go blank. It was filed as
    carry-over C2 rather than chosen.

    ``SURF_ROW_KEYS["pool4_stakers"]`` now declares ``address`` and the
    producer agrees, so the fallback is dead code and is gone. Keeping it would
    be worse than dead: a row arriving with ``addr`` is now a *producer bug*,
    and a renderer that quietly accepts it hides the bug behind a correct-
    looking column -- which is how a shape divergence survives to the next
    reader instead of reddening in CI.
    """
    if not isinstance(row, dict):
        return None
    try:
        rank = row.get("rank")
        rank_text = f"{int(rank)}" if rank is not None else DASH
        addr = row.get("address")
        pct = as_float(row.get("pct"))
        pct_text = f"{pct:.1f}%" if pct is not None else DASH
        return rank_text, full_addr(addr), _fmt_imd_cell(row.get("imd")), pct_text
    except Exception:
        return None


def no_rows_line(state) -> tuple[str, str]:
    """``(text, rich style)`` for an empty panel, from ``pool4_stakers_state``.

    **The warning is earned, not the default.** ``pool4_stakers`` is ``None``
    for three different reasons and they used to render as one: the fold is
    detached so first paint cannot sit behind it (PRD 7.2), which makes an
    empty panel the *ordinary* state of tick 1 -- and a transient failure backs
    the tier off 300 s, so the panel stayed on that same warning for five
    minutes afterwards. A reader acts differently on each, and the curator rail
    bug is exactly this: one render for several different facts.

    Only ``failed`` gets ``⚠`` and the yellow. Every other value -- including
    an unrecognised word, and ``None`` from a payload that predates the key --
    falls to the dim pending line, because an absent state is not evidence of
    a fault and this panel must never invent one.
    """
    if state == _FAILED:
        return f"⚠ {UNAVAILABLE_LINE}", "yellow"
    if state == _SWEEPING:
        return SWEEPING_LINE, "dim"
    return PENDING_LINE, "dim"


def _hhmm_minutes(value) -> int | None:
    """``"14:32"`` -> 872 minutes past midnight; ``None`` for anything else.

    Total by construction: a hand-edited cache file reaches this panel the
    same way a fetched one does, and a marker that cannot be parsed must make
    the comparison silent rather than raise inside a render.
    """
    text = strip_tags(value)
    if len(text) != _HHMM_LEN or text[2] != ":":
        return None
    try:
        hours = int(text[:2])
        minutes = int(text[3:])
    except ValueError:
        return None
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        return None
    return hours * 60 + minutes


def fold_is_stale(stakers_hhmm, body_hhmm) -> bool:
    """Is the staker fold further behind the body's clock than :data:`STALE_AFTER_S`?

    **Two payload strings, no clock.** The comparison is between the two
    markers the screen already hands this panel, so nothing here calls
    ``time.time()`` and the answer is reproducible from a payload alone --
    CLAUDE.md's inject-the-clock rule, satisfied by not needing one.

    ``False`` whenever the question cannot be answered: either marker missing
    or malformed, or this panel's marker running *ahead* of the body's (which
    is ordinary -- the staker sweep can land between two pool4 sweeps).
    Silence is the safe default, because a word printed on a comparison
    nobody could make is a warning about the renderer rather than the data.
    """
    mine = _hhmm_minutes(stakers_hhmm)
    theirs = _hhmm_minutes(body_hhmm)
    if mine is None or theirs is None:
        return False
    behind = (theirs - mine) % (24 * 60)
    if behind > _HALF_DAY_MIN:
        # Ahead of the body's clock, not most of a day behind it.
        return False
    return behind * 60 > STALE_AFTER_S


def footer_line(count, top_pct, stale: bool = False) -> str:
    """``66 addresses · top 3 = 32% of vault`` -- plain text, already fitted.

    ``top_pct is None`` renders ``top 3 = --`` and never a number computed
    from the visible rows: the fold was incomplete, and a subset's share is a
    smaller number than the truth (PRD §7.4).

    ``count is None`` drops the addresses clause rather than printing
    ``-- addresses``: the concentration half is the half a reader acts on and
    it should not be pushed along by a dash.

    ``stale`` appends :data:`STALE_WORD` -- see that constant, and
    :func:`fold_is_stale` for when it is true. It is **six cells plus the
    separator**, and that is the whole reason it is a word and not the age:
    the widest footer this panel can paint (``999,999 addresses · top 3 =
    100% of vault``) is 41 cells, and ``· stale`` takes it to 49.

    **The budget that sentence is measured against was wrong by two and is
    corrected here** (2026-09-12). It read "the column is 50 at
    ``SURF_POOL4_USER_FULL_LAYOUT_COLUMNS``", which was this panel's *outer*
    width of 52 less its own ``padding: 0 1``. Textual's ``size`` is already
    the content size, so the footer ``Static``'s own ``padding: 0 1`` comes
    off as well: the real budget at a 52-column panel was **48**, and the
    49-cell worst case above was clipped to ``· sta…`` by CSS with no marker
    to say so. It is visible in the ``wide-stakers`` fixture at the old pin.

    The full address moved the panel to 73 columns and the budget to 69, so
    the worst case now clears it by twenty and the defect is gone with the
    layout rather than with a shortened value. ``· stale 1h37m`` is still not
    on the table: the reason it is a word and not an age is that an age is a
    per-panel clock, which this body does not have (see :data:`STALE_WORD`).
    """
    parts: list[str] = []
    n = as_float(count)
    if n is not None:
        parts.append(f"{int(n):,} addresses")
    pct = as_float(top_pct)
    shown = f"{pct:.0f}%" if pct is not None else DASH
    parts.append(f"top {TOP_N} = {shown} of vault")
    if stale:
        parts.append(STALE_WORD)
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
    SurfPool4UStakers > .pool4u-title {
        margin: 0 0 1 0;
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
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID,
                     classes=TITLE_CLASS)
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
        pool4_stakers_state=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        **Neither marker is rendered as a marker** (2026-09-12). The ``4``
        body prints one ``as of``, on the screen's own title row. The two are
        kept because this panel is the one place on the body where they
        *disagree* by more than a rounding: subtracting them is what
        :func:`fold_is_stale` does, and the word it decides is the whole of
        what is left of this panel's own clock. See :data:`STALE_AFTER_S`.

        Both are spelled in full for the contract's reason as well -- every
        pool4 panel does (``test_no_pool4_widget_needs_a_kwarg_alias``), and
        that is what stops a second body eliding one to ``as_of_hhmm`` and
        making one kwarg name answer for two different contract keys.
        """
        self._payload = {
            "rows": pool4_stakers,
            "count": pool4_staker_count,
            "top3_pct": pool4_staker_top3_pct,
            "as_of": pool4_stakers_as_of_hhmm,
            "body_as_of": pool4_as_of_hhmm,
            "state": pool4_stakers_state,
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
            # ``not seen`` shares the empty branch rather than the failed one:
            # a panel the screen has not dispatched to yet knows of no fault,
            # and its ``state`` is ``None``, which :func:`no_rows_line` reads
            # as pending. The alarm has one trigger and this is not it.
            text, style = no_rows_line(payload.get("state"))
            markup.append(f"[{style}]{safe_markup(text)}[/]")
        elif not rows:
            markup.append(f"[dim]{safe_markup(EMPTY_LINE)}[/]")
        else:
            # The staleness word rides THIS line and never one of its own, so
            # a fold that has missed a cycle costs the layout nothing. It is
            # attached only to the real footer: the three empty branches above
            # are already saying something louder about the fold than "old".
            text = footer_line(
                payload.get("count"),
                payload.get("top3_pct"),
                stale=fold_is_stale(payload.get("as_of"),
                                    payload.get("body_as_of")),
            )
            markup.append(f"[dim]{safe_markup(text)}[/]")

        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            footer.update(join_lines(lines))
        except Exception:  # pragma: no cover - parse already guarded
            pass
