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
Chain-sourced, and **not shortened at all** since 2026-09-12 wherever the
panel has the room: all 42 characters, followed since 2026-09-14 by the copy
icon (``widgets/address.address_text``). At
``SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` the address gives the icon its two
cells and shows 40 -- ``0x`` + 31 + ``…`` + 6 -- so the icon moved no pin; the
whole value is one click away either way. The trade is recorded beside that
constant. The cell is a ``Text`` and is never parsed, so there is nothing to
escape.

(The history below names ``_fmt.full_addr`` and ``_fmt.long_addr``; both were
removed on 2026-09-14 when every surf address moved to ``widgets/address.py``.)

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
The 17-cell anti-poisoning window this panel left behind was not narrowed for
its other two users: HATCHES' address block on the ``p`` body and the dashboard
body's activity feed still show it, now through ``widgets/address.short_address``
at ``_fmt.ANTI_POISONING_COLS`` with a copy icon beside it. (HATCHES' lever grid
gave up two cells of that window to its icon; see
``screens/surf.SURF_POOL4_FULL_LAYOUT_COLUMNS``.)

Purity
------
Stdlib, ``rich``, ``textual`` and this package's own primitives. No ``data/``,
no ``analytics/``, no clock, no I/O. Rich colour names only -- Rich cannot
resolve Textual's ``$`` theme tokens and raises at render time, outside this
module's ``try``.
"""

from __future__ import annotations

import math

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.address import ICON_COLS, address_text
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_compact,
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

#: How many rows the table draws: **every staker, up to 999** (2026-09-15).
#:
#: It was 20, matching the producer's ``POOL4_STAKERS_LIMIT``, until the
#: owner asked for all 353 addresses. The table sits on a ``1fr`` height
#: inside the panel and scrolls inside itself, so more rows never push the
#: footer off. That was this guard's original reason, and it no longer needs
#: a small number to hold. 999 is the largest rank :data:`_RANK_COLS` can
#: paint whole; a four-digit rank would be cut, and a cut rank is a wrong
#: rank. Restated from ``data/surf_manager.POOL4_STAKERS_LIMIT`` because a
#: widget may not import ``data/``;
#: ``test_the_row_cap_is_the_producers_own_and_fits_the_rank_column`` pins the
#: two together.
MAX_ROWS = 999

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
#: * rank -- three cells covers the ``#`` header and every rank up to
#:   ``999``, which is why :data:`MAX_ROWS` is 999 and not higher;
#: * address -- the **whole** address: ``0x`` + 40 hex is 42 cells. It was 17
#:   (the anti-poisoning window) until 2026-09-12; the twenty-five columns
#:   that move is the single largest thing in this panel's width and the
#:   reason ``screens/surf.SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` moved with it.
#:   **Plus the copy icon since 2026-09-14** (``docs/address_copy_PRD.md``
#:   §5), and the icon is the one thing on this panel with two widths: the
#:   whole address *and* its icon when the panel has the room
#:   (:data:`WHOLE_WIDTH`), and at the pin the address windowed to
#:   :data:`_ADDR_SHORT_COLS` so the icon costs the body nothing -- 40 cells,
#:   ``0x`` + 31 + ``…`` + 6, recorded beside the pin it protects;
#: * IMD -- **eight** since 2026-09-15, was ten. ``fmt_compact`` tops out at
#:   ``999.9B`` (six), ``1200.0B`` past a trillion (seven), and the small-stake
#:   forms at ``0.00042`` / ``<0.0001`` (seven): see :func:`_fmt_imd_cell`;
#: * share -- **eight** since 2026-09-15, was six: ``100.0%`` is six, and the
#:   small-share forms ``0.00012%`` / ``<0.0001%`` are eight (:func:`_fmt_share_cell`).
#:
#: **The two columns traded cells, and the row did not grow.** The owner read
#: ``8``/``0``/``0.0%`` down the bottom of the 353-row table (172 of the live
#: vault's 350 holders printed ``0.0%``) and asked for the real values. Two
#: significant digits on a small share need eight cells where the column had
#: six, and at ``SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`` this table has zero cells
#: to spare beside its scrollbar. The IMD column had three: ten cells for a
#: widest value of seven. So IMD gave two to share. ``FULL_WIDTH`` and
#: ``WHOLE_WIDTH`` are unchanged (69, 71), ``COMPACT_WIDTH`` is 59 (was 61),
#: and no pin moved. Measured in situ on the live 350-row payload and a
#: synthetic worst case (the report of 2026-09-15).
_RANK_COLS = 3
_ADDR_COLS = 42
_ADDR_SHORT_COLS = _ADDR_COLS - ICON_COLS                           # 40
_IMD_COLS = 8
_PCT_COLS = 8

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

#: The row with the **whole** address and its copy icon, share included --
#: the ``whole`` tier. Below it the address is windowed to
#: :data:`_ADDR_SHORT_COLS` and nothing is announced: the whole value is one
#: click away, and a window is an honest short form rather than a shed
#: column (``docs/address_copy_PRD.md`` §5).
WHOLE_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_RANK_COLS, _ADDR_COLS + ICON_COLS, _IMD_COLS, _PCT_COLS)
)                                                                    # 71

#: Widest full-tier row: the share column present, the address windowed to
#: :data:`_ADDR_SHORT_COLS` beside its icon. Unchanged at 69 by the icon --
#: the window gave the icon its two cells.
FULL_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_RANK_COLS, _ADDR_SHORT_COLS + ICON_COLS, _IMD_COLS, _PCT_COLS)
)                                                                    # 69

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
    cols + _CELL_PADDING
    for cols in (_RANK_COLS, _ADDR_SHORT_COLS + ICON_COLS, _IMD_COLS)
)                                                                    # 59


def _shown_addr_cols(tier: str) -> int:
    """Cells of address shown at *tier*, excluding the icon: whole or 40."""
    return _ADDR_COLS if tier == "whole" else _ADDR_SHORT_COLS


#: The smallest step a small stake or share is printed to. Below it the cell
#: says so (:data:`_BELOW_STEP`) instead of rounding a real holding to zero.
_SMALL_STEP = 0.0001
_BELOW_STEP = "<0.0001"


def _two_significant(v: float) -> str:
    """``0 < v < 1`` at two significant digits, or :data:`_BELOW_STEP`.

    ``0.37``, ``0.042``, ``0.0042``, ``0.00042``: as many decimals as it takes
    to show two significant digits, and never fewer than two. Below
    :data:`_SMALL_STEP` it is the floor marker, never a rounded-down zero.
    """
    if v < _SMALL_STEP:
        return _BELOW_STEP
    return f"{v:.{max(2, 1 - math.floor(math.log10(v)))}f}"


def _fmt_imd_cell(value) -> str:
    """A staker's IMD holding, fitted to :data:`_IMD_COLS`, with its real digits.

    ``115.4K`` above 1000 (``fmt_compact``), a grouped integer from 10
    (``780``), two decimals from 1 (``8.42``), two significant digits below 1
    (``0.37``, ``0.0042``), ``<0.0001`` below the step, ``0`` for a true zero,
    and ``--`` for an unread amount.

    Until 2026-09-15 everything below 1000 was a whole number, so the owner's
    screen read ``8``, ``1`` and then ``0`` for four live holders who hold
    something: 0.24, 0.030 and two dust balances. The producer already
    publishes the unrounded float, so the fix is here. Widest form: seven
    cells, measured.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if v == 0:
        return "0"
    sign, m = ("-", -v) if v < 0 else ("", v)
    if m >= 1000:
        return fmt_compact(v)
    if m >= 10:
        return f"{v:,.0f}"
    if m >= 1:
        return f"{v:.2f}"
    return sign + _two_significant(m)


def _fmt_share_cell(value) -> str:
    """A staker's share of the whole vault, fitted to :data:`_PCT_COLS`.

    ``7.7%`` from 1%, two significant digits below it (``0.55%``, ``0.012%``,
    ``0.00053%``), ``<0.0001%`` below the step, ``0%`` for a true zero, and
    ``--`` unread. It was ``.1f`` everywhere, which painted 172 of the live
    vault's 350 holders as ``0.0%``. Widest form: eight cells, measured.
    """
    pct = as_float(value)
    if pct is None:
        return DASH
    if pct == 0:
        return "0%"
    if abs(pct) >= 1:
        return f"{pct:.1f}%"
    return ("-" if pct < 0 else "") + _two_significant(abs(pct)) + "%"


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
        address = str(addr).strip() if addr else ""
        pct_text = _fmt_share_cell(row.get("pct"))
        # The address whole and raw -- ``--`` for a missing one, never a blank
        # cell. How much of it is shown, and its copy icon, is decided at
        # render time against the width (see ``_render_rows``).
        return rank_text, address or DASH, _fmt_imd_cell(row.get("imd")), pct_text
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


def footer_line(count, top_pct, stale: bool = False, shown=None) -> str:
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

    ``shown`` is the number of rows the table actually draws, passed only when
    the population exceeds :data:`MAX_ROWS` (fix round 1, item 4). The
    addresses clause then reads ``showing 999 of 1,200 addresses``, so a
    capped table says so on the line it already has rather than on a new one.
    The widest footer this makes, ``showing 999 of 999,999 addresses · top 3 =
    100% of vault · stale``, is 64 cells against the footer's 69 at the ``4``
    body's width pin.
    """
    parts: list[str] = []
    n = as_float(count)
    if n is not None:
        m = as_float(shown)
        if m is not None and int(m) < int(n):
            parts.append(f"showing {int(m):,} of {int(n):,} addresses")
        else:
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
    #:
    #: **The same two columns are what the table's vertical scrollbar
    #: costs, and the tiers fit beside it with none to spare** (measured
    #: 2026-09-15, fix round 1). The ``DataTable`` has no padding, so it gets
    #: the whole content width, and with every staker loaded it always
    #: scrolls and paints a two-cell scrollbar. That leaves exactly
    #: ``FULL_WIDTH`` / ``WHOLE_WIDTH`` at each tier's first width (119 and
    #: 121 on the ``4`` body), so ``share`` is never hidden, at 35, 50 and 60
    #: rows. A wider scrollbar, or a tier budget that stopped subtracting
    #: these two, would hide the share column behind a horizontal scroll with
    #: no marker. ``test_the_market_body_is_whole_from_its_pinned_width``
    #: reads ``max_scroll_x`` on the ``every-staker`` payload to catch it.
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
        #: What the table currently holds, as ``(tier, rows as plain text)``.
        #: A repaint with the same key is skipped, because
        #: ``DataTable.clear()`` resets ``scroll_y`` to 0. With every staker
        #: in the table (2026-09-15) a reader scrolls to see most of them,
        #: and a 30 s poll that re-sent identical rows would snap them back to
        #: the top each time.
        self._rows_key: tuple | None = None

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
            self._rows_key = None
            table.add_column("#", width=_RANK_COLS, key="rank")
            table.add_column(
                "address", width=_shown_addr_cols(tier) + ICON_COLS, key="address"
            )
            table.add_column("IMD", width=_IMD_COLS, key="imd")
            if tier in ("whole", "full"):
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
        if self._widen:
            self._tier = "compact"
        elif budget and budget < WHOLE_WIDTH:
            # The pin: the address windowed so its icon costs no column.
            # Not a shed field, so no marker -- the icon copies it whole.
            self._tier = "full"
        else:
            self._tier = "whole"
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
        # four panels go on printing it -- see ``_pool4.QUIET_NETWORK`` for
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
        # The reader's place, saved before anything below can clear the table:
        # a tier change rebuilds the columns and a changed payload clears the
        # rows, and ``DataTable.clear()`` resets both to the top. Restored,
        # clamped to the new row count, by :meth:`_restore_place`.
        saved_y = table.scroll_y
        saved_row = table.cursor_row
        self._install_columns(table, self._tier)

        rows = self._payload.get("rows")
        batch: list[list] = []
        if isinstance(rows, list):
            for row in rows[:MAX_ROWS]:
                cells = staker_cells(row)
                if cells is None:
                    continue
                rank, addr, imd, pct = cells
                # Escape AFTER fitting: ``clip`` measures cells and an escaped
                # ``\\[`` is two characters and one cell, so escaping first
                # misaligns every column and can cut an escape pair in half.
                # DataTable defers ``Text.from_markup`` into its idle handler,
                # so an unescaped ``[/x]`` in a chain-sourced address crashes
                # the app from inside the message pump.
                values = [
                    safe_markup(pad(clip(rank, _RANK_COLS), _RANK_COLS)),
                    # A ``Text`` cell, never markup: it carries the copy
                    # icon's action (``widgets/address.address_text``), and
                    # ``DataTable`` renders a ``Text`` as it is, so a
                    # chain-sourced ``[/x]`` never reaches a parser from this
                    # column.
                    address_text(addr, width=_shown_addr_cols(self._tier)),
                    safe_markup(pad(clip(imd, _IMD_COLS), _IMD_COLS)),
                ]
                if self._tier in ("whole", "full"):
                    values.append(safe_markup(clip(pct, _PCT_COLS)))
                batch.append(values)

        # Unchanged rows at an unchanged tier: leave the table, and the
        # reader's scroll position in it, alone (see ``_rows_key``).
        key = (self._tier, tuple(tuple(str(v) for v in values) for values in batch))
        if key == self._rows_key:
            return
        try:
            table.clear()
        except Exception:  # pragma: no cover - columns not added yet
            return
        self._rows_key = None
        for values in batch:
            try:
                table.add_row(*values)
            except Exception:
                continue
        self._rows_key = key
        self._restore_place(table, saved_y, saved_row)

    @staticmethod
    def _restore_place(table: DataTable, scroll_y: float, cursor_row: int) -> None:
        """Put the reader back where they were before a repaint (fix round 1).

        The identical-rows skip in :meth:`_render_rows` keeps the place only
        while nothing changes. A new fold reprices every row every 1800 s, and
        a resize across the whole/full threshold rebuilds the columns; both
        clear the table. The cursor row is restored without scrolling to it.
        The scroll offset is restored after the next refresh, once the table
        knows its new height, and clamped to it so a shorter list lands on its
        last page rather than past its end.
        """
        if table.row_count:
            try:
                table.move_cursor(
                    row=min(max(cursor_row, 0), table.row_count - 1), scroll=False
                )
            except Exception:  # pragma: no cover - defensive
                pass
        if scroll_y <= 0:
            return

        def restore() -> None:
            try:
                table.scroll_to(
                    y=min(scroll_y, table.max_scroll_y), animate=False
                )
            except Exception:  # pragma: no cover - defensive
                pass

        table.call_after_refresh(restore)

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
            # Only a population past the table's own cap is ever cut short:
            # the producer publishes every holder up to the same number.
            population = as_float(payload.get("count"))
            shown = None
            if population is not None and population > MAX_ROWS:
                shown = min(len(rows) if isinstance(rows, list) else 0, MAX_ROWS)
            text = footer_line(
                payload.get("count"),
                payload.get("top3_pct"),
                stale=fold_is_stale(payload.get("as_of"),
                                    payload.get("body_as_of")),
                shown=shown,
            )
            markup.append(f"[dim]{safe_markup(text)}[/]")

        lines = [t for t in (parse_line(m) for m in markup) if t is not None]
        try:
            footer.update(join_lines(lines))
        except Exception:  # pragma: no cover - parse already guarded
            pass
