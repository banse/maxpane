"""Shared row-fit machinery for ``RichLog(wrap=False)`` panels, the widen-hint
vocabulary and the width-tier :class:`Ladder` -- ``widgets/rowfit.py``, one
module for every dashboard (built for surf; ``docs/refactor_programme_2026_09.md``
Branches 2 and 3).

``RichLog`` composed ``wrap=False`` narrows any line wider than its usable
width **at write time, with no ``…``, no marker and nothing in the title**
(``.claude/skills/terminal-layout/SKILL.md``).  A row that goes into one of
these panels therefore has to be *fitted* before it is written, and the
fitting is the same three-part job in every one of them:

* :data:`GAP` -- how far apart two cells sit, and what an *absent* cell
  takes with it;
* :func:`row_cols` -- what a row made of exactly these cells costs;
* :func:`tier_for` -- the widest whole-cell layout that fits, and
  :class:`Ladder`, the same selector bound to one panel's own thresholds;
* :func:`budget` -- the order of sacrifice inside one tier, when the row
  still does not fit after the tier has shed what it can;
* :data:`WIDEN_HINT` / :data:`SHORT_HINT` / :data:`GLYPH_HINT` -- the one
  spelling of "columns were dropped here", and :func:`title_with_hint` /
  :func:`has_marker`, the title fitter and the ``as of`` predicate the swarm
  panels share.

This module exists because that ladder was written twice already
(``activity.py`` 2026-08-07, ``launchpad_activity.py`` 2026-08-23) and a
third panel was about to copy it.  CLAUDE.md's *Reuse before you build* names
the cost precisely, and it is not typing: "three copies of one helper means a
fix reaches one of them".  The fix in question is the one this module also
carries -- :func:`clip`, :func:`pad` and every measurement here are on
:func:`rich.cells.cell_len`, never ``len()``.

**What deliberately stays in the calling module.** Every per-panel column
constant -- ``_KIND_COLS``, ``_WALLET_COLS``, ``ADDR_COLS``, ``FULL_WIDTH``,
``WIDEN_HINTS`` and friends.  Those are *measurements of one panel's own
format strings*, each with its own ``#:`` block recording what it was
measured against and which producer vocabulary a test pins it to; hoisting
them here would put one number in front of two panels that do not render the
same row.  Only the machinery is shared.

Primitives only: no ``data/``, no ``analytics/``, no Textual, no clock.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from rich.cells import cell_len

__all__ = [
    "GAP",
    "GLYPH_HINT",
    "Ladder",
    "SHORT_HINT",
    "WIDEN_HINT",
    "budget",
    "clip",
    "has_marker",
    "pad",
    "row_cols",
    "tier_for",
    "title_with_hint",
]

#: Columns between two adjacent cells.  Two, in every surf row panel, and
#: pinned as a design decision rather than a derived quantity by
#: ``test_activity_spends_no_columns_between_the_wallet_and_the_kind``.
GAP = 2

#: What a panel appends to its own title when it had to shed a column, cut a
#: head, truncate a message or clip a row -- the **repo-wide spelling**, one
#: literal for every dashboard (curator, fwa, surf; sixteen module-level copies
#: until Branch 3 of ``docs/refactor_programme_2026_09.md``). Never nothing:
#: "columns were dropped here" is the contract, and going silent is not an
#: option this codebase allows. Appended, never substituted for the title. Do
#: not redefine it to mean anything narrower; ``test_the_widen_vocabulary_
#: means_one_thing_across_the_repo`` binds every spelling to this one.
#:
#: Where it lands is each panel's own decision and is documented there: the
#: heroes raise it in a box's *bottom border* (five content lines inside a
#: height-7 frame leave no sixth line to spare), the ``RichLog`` panels append
#: it to the title, the curator table panels and SIGNALS append it when a row
#: lost every part of its value.
WIDEN_HINT = "‹ widen"

#: The **fallback** marker for a title bar too narrow to carry a panel's own
#: descriptive hint (its ``WIDEN_HINTS[tier]``, e.g. ``‹ widen: time, kind,
#: ETH`` -- those dicts stay per module: they are content, not a constant). It
#: names nothing, which is a real loss -- but the contract above still holds.
#: An alias of :data:`WIDEN_HINT`, deliberately not a second literal, so there
#: is one string to change and no spelling can drift. Reachable in the narrow
#: rails: at 80 terminal columns surf's activity panel is 30 wide against the
#: 38 its minimal hint needs; surf's NFT panel also uses it when the row that
#: overflows is the 31-column floor line, which has no field to shed.
SHORT_HINT = WIDEN_HINT

#: One tier below :data:`WIDEN_HINT`: the bare marker glyph, for a panel too
#: narrow to say it in words. It exists because a pool4 title carries the
#: network word as well as the panel name, so ``THE RATCHET · SEPOLIA
#: ‹ widen`` genuinely does not fit a narrow rail where a bare
#: ``LAUNCHPAD ACTIVITY  ‹ widen`` would. :func:`title_with_hint` tries the
#: two in that order.
#:
#: **Deliberately not called ``SHORT_HINT``.** That name means ``"‹ widen"``
#: everywhere; reusing it for a narrower thing on the same view would make one
#: name stand for two spellings, which is the same class of defect as the
#: network word ``_pool4`` exists to unify.
GLYPH_HINT = "‹"


def clip(value: str, width: int) -> str:
    """Truncate ``value`` to ``width`` **terminal cells**, marking a cut ``…``.

    Measured on :func:`rich.cells.cell_len`, never ``len()``: *a sized cell is
    not a fitted one*.  Tickers, ENS names and counterparty labels are all
    third-party strings, and eight CJK characters are sixteen columns -- a
    ``len()``-sized cell is then eight columns wider than the budget it was
    checked against, and the overflow comes off the end of the line
    unannounced.

    A wide glyph straddling the cut is dropped rather than half-drawn, so the
    result can come back one cell *under* ``width``; :func:`pad` squares it
    up.  Must run **before** ``safe_markup`` -- escaping first and truncating
    after can cut a ``\\[`` escape pair in half.
    """
    if width <= 0:
        return ""
    if cell_len(value) <= width:
        return value
    if width == 1:
        return "…"
    out: list[str] = []
    used = 0
    for char in value:
        size = cell_len(char)
        if used + size > width - 1:
            break
        out.append(char)
        used += size
    return "".join(out) + "…"


def pad(value: str, width: int) -> str:
    """Left-align ``value`` in ``width`` **cells**.

    ``f"{value:<{width}}"`` pads to a *character* count, so it under-pads a
    wide-glyph cell -- the mirror image of :func:`clip`'s bug, which is why
    both live here rather than in a format string.  Pad raw, escape after:
    padding an escaped string misaligns it.
    """
    return value + " " * max(width - cell_len(value), 0)


def row_cols(cells: Iterable[int], trailing: int = 0, gap: int = GAP) -> int:
    """Rendered width of a row made of exactly ``cells``, plus ``trailing``.

    **A cell of zero width is absent, and an absent cell takes its ``gap``
    with it.**  That is the arithmetic both callers got wrong before this
    function existed: they charged the row for every gap unconditionally and
    never re-measured the result, so dropping a cell neither freed the gap it
    had been charged for nor proved the row now fitted.  ``activity.py``'s
    ``FLOOR_WIDTH`` records what that cost on screen -- a 24-column row in a
    23-column log, narrowed by ``RichLog`` to ``0xF308``, which is the one
    address collision that panel exists to prevent.

    ``trailing`` is the amount cell, which carries its own leading gap inside
    its own string (both panels format it ``f"  {…}"``), so it is *added*
    rather than joined.  A row with no cells at all costs exactly
    ``trailing``: the ``gap * (len(present) - 1)`` term would otherwise
    subtract a gap that was never charged.
    """
    present = [cols for cols in cells if cols]
    if not present:
        return trailing
    return sum(present) + gap * (len(present) - 1) + trailing


def tier_for(width: int, ladder: Sequence[tuple[str, int]]) -> str:
    """Widest layout in ``ladder`` that fits ``width`` rendered columns.

    ``ladder`` is ``((name, columns_needed), …)`` **widest first**; the last
    entry is the fallback and its threshold is not consulted.  A tier's
    requirement may be a constant (``activity.FULL_WIDTH``) or measured per
    batch (``launchpad_activity`` re-derives ``full`` from the widest amount
    in the batch, because a swap has no upper bound) -- this function does not
    care which, and that is the point of taking the ladder as data.

    ``width <= 0`` means "not laid out yet" and optimistically picks the
    widest layout; each panel's ``on_resize`` re-lays it out once it has a
    size.
    """
    if width <= 0:
        return ladder[0][0]
    for name, needed in ladder:
        if width >= needed:
            return name
    return ladder[-1][0]


class Ladder:
    """A panel's own width tiers, widest first, bound to :func:`tier_for`.

    ``Ladder(("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("minimal", 0))``
    replaces the ``def _tier_for(width) -> str`` that eight modules each wrote
    as an ``if``-chain (or a :func:`tier_for` call) over their own ``*_WIDTH``
    constants (Branch 3 of ``docs/refactor_programme_2026_09.md``); the module
    keeps its name with ``_tier_for = _LADDER.tier_for``, so its tests and
    docstrings still read. (``surf/activity._tier_for`` stays a function: a
    screen test pins the measured-width note in its docstring.)
    The semantics are exactly :func:`tier_for`'s: ``width <= 0`` picks the
    first step, otherwise the first step whose threshold the width reaches,
    otherwise the last step -- whose threshold is therefore never consulted
    (a panel with a documented ``MINIMAL_WIDTH`` that is also its floor may
    quote it there or write ``0``; the tier chosen is the same either way).

    Thresholds are the calling module's measurements and stay there: a
    ladder holds the *names and numbers one panel measured*, never a shared
    number two panels do not both render.
    """

    __slots__ = ("steps",)

    def __init__(self, *steps: tuple[str, int]) -> None:
        if not steps:
            raise ValueError("a Ladder needs at least one step")
        self.steps: tuple[tuple[str, int], ...] = tuple(steps)

    def tier_for(self, width: int) -> str:
        """Widest step that fits ``width`` rendered columns (:func:`tier_for`)."""
        return tier_for(width, self.steps)

    def __repr__(self) -> str:
        return f"Ladder{self.steps!r}"


def has_marker(as_of: object) -> bool:
    """True when *as_of* is a real ``as of`` clock, not merely non-``None``.

    An unavailable gate that checks ``as_of is None`` alone treats an empty
    string as "this slot has been read" and lets rows or an empty-state line
    render, while the title -- which has always checked truthiness, not
    identity, to decide whether to print a clock at all -- shows no ``as of``
    marker: a body claiming to have read the source under a title that shows
    no time it read it at (surf's swarm FIELD, fix round 2). Every call site
    that asks the question goes through this one predicate, so the title and
    the body cannot disagree again. Hoisted from the four identical swarm
    copies in Branch 3.
    """
    return isinstance(as_of, str) and bool(as_of)


def title_with_hint(base: str, widen: bool, room: int) -> str:
    """Append the longest widen marker that fits *base* within *room* columns.

    :data:`WIDEN_HINT` first, then the bare :data:`GLYPH_HINT`, each two
    columns after the title; neither when *widen* is false, and *base*
    untouched when not even the glyph fits. ``room <= 0`` means "not laid
    out yet" and appends the full marker. For a title that also carries a
    network word use ``_pool4.title_text`` / ``market_panel_title``, which
    bind the same two markers to that shape; this is the fitter for a title
    that deliberately carries none (the swarm panels, whose chain word is per
    row). Hoisted from the four identical swarm copies in Branch 3.
    ``curator/_table.title_with_hint`` is a different contract (it returns
    ``(title, fitted)``) and is not this function. The width argument is
    ``room``, not ``budget``, so it cannot shadow :func:`budget` in this module.
    """
    if not widen:
        return base
    for candidate in (WIDEN_HINT, GLYPH_HINT):
        if not room or cell_len(base) + 2 + cell_len(candidate) <= room:
            return f"{base}  {candidate}"
    return base


def budget(
    width: int,
    who: str,
    known: bool,
    needed: Callable[[int, int, bool], int],
    wallet_cols: int,
    keep_stamp: bool,
    min_label_cols: int,
) -> tuple[bool, int, str]:
    """Fit one row to ``width``; returns ``(keep_stamp, wallet_cols, who)``.

    ``needed(who_cols, wallet_cols, keep_stamp) -> int`` is the caller's own
    row arithmetic (its :func:`row_cols` call).  It is passed in rather than
    closed over because the two later steps *change* ``wallet_cols`` and
    ``keep_stamp``, and a closure that silently re-read them was the shape
    that made this logic hard to follow where it used to live.

    Order of sacrifice, after the tier has already dropped whole columns:

    1. a **known** label is cut with a visible ``…`` (down to
       ``min_label_cols``) -- it is descriptive text;
    2. the **wallet** cell goes, whole.  It is three columns wide against a
       two-member vocabulary, so there is nothing in it to shrink: cut to two
       it renders ``de`` / ``op`` with no ``…``, which is a silent cut one
       cell to the left;
    3. the **date** goes, whole;
    4. the **unknown-counterparty window** is never touched at all -- the
       caller withholds the row instead (``activity.FLOOR_WIDTH``).

    ``wallet_cols`` / ``keep_stamp`` are the *starting* plan, so a caller can
    fit every row of a batch to one shared layout.  Passing a cell already
    dropped can only ever leave this function more room, never less, so a
    batch plan is a fixed point of it.

    Every measurement is :func:`rich.cells.cell_len`. ``who`` is a
    third-party string -- a ``KNOWN_LABELS`` label, or whatever
    ``widgets/address.address_text`` made of an arbitrary ``counterparty``,
    copy icon included -- and measured
    with ``len()`` a nine-character, eighteen-column label was declared to
    fit in nine. The cut was worse than the overflow: ``who[: room - 1] +
    "…"`` took ``room - 1`` *characters* for a budget of ``room``
    **columns**, so the ellipsis said "cut" while the result still painted
    past the width it had just been cut to, and ``RichLog`` then took the
    difference off the end with nothing to say so.

    ``width <= 0`` (not laid out yet) leaves everything at its natural size.
    """
    if width <= 0:
        return keep_stamp, wallet_cols, who

    over = needed(cell_len(who), wallet_cols, keep_stamp) - width
    if over > 0 and known and cell_len(who) > min_label_cols:
        room = max(cell_len(who) - over, min_label_cols)
        who = clip(who, room)
    if needed(cell_len(who), wallet_cols, keep_stamp) > width:
        wallet_cols = 0
    if needed(cell_len(who), wallet_cols, keep_stamp) > width:
        keep_stamp = False
    return keep_stamp, wallet_cols, who
