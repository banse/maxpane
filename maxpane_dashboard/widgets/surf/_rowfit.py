"""Shared row-fit machinery for surf's ``RichLog(wrap=False)`` panels.

``RichLog`` composed ``wrap=False`` narrows any line wider than its usable
width **at write time, with no ``…``, no marker and nothing in the title**
(``.claude/skills/terminal-layout/SKILL.md``).  A row that goes into one of
these panels therefore has to be *fitted* before it is written, and the
fitting is the same three-part job in every one of them:

* :data:`GAP` -- how far apart two cells sit, and what an *absent* cell
  takes with it;
* :func:`row_cols` -- what a row made of exactly these cells costs;
* :func:`tier_for` -- the widest whole-cell layout that fits;
* :func:`budget` -- the order of sacrifice inside one tier, when the row
  still does not fit after the tier has shed what it can.

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
    "budget",
    "clip",
    "pad",
    "row_cols",
    "tier_for",
]

#: Columns between two adjacent cells.  Two, in every surf row panel, and
#: pinned as a design decision rather than a derived quantity by
#: ``test_activity_spends_no_columns_between_the_wallet_and_the_kind``.
GAP = 2


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
    ``_fmt.long_addr`` made of an arbitrary ``counterparty`` -- and measured
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
