"""Pure folds for the POOL4 ``4`` market body.  No I/O, no clock, no Textual.

Imported by the manager, never by a widget.

Three folds live here and they share one property worth stating once: **every
one of them answers ``None`` when it could not compute, and a real zero when
the answer genuinely is zero.**  That distinction is the repo's oldest rule
(``A failed read is None, never 0``) and each fold below has a test named after
its own half of it, because the two halves fail in opposite directions -- a
``None`` rendered as ``0`` claims a fact nobody read, and a ``0`` rendered as
``--`` hides one that was.
"""

from __future__ import annotations

import math

#: ``log(1.0001)``, precomputed.  Uniswap ticks are powers of 1.0001, so a tick
#: difference becomes a price ratio through one ``exp``; taking the log on every
#: call would be the same number rounded slightly differently each time.
_LOG_BASE = math.log(1.0001)


def venue_gap_pct(*, hook_tick: int | None, reference_tick: int | None) -> float | None:
    """How much dearer IMD is on the hook pool than on the hookless one, in %.

    **Derived one way, and this docstring is the authority on which way.** The
    research skill reported this number three ways that did not agree -- +1.5%
    from its ``state`` command, +0.2% from ``share`` twenty-eight blocks later,
    and 145 ticks (~1.45%) implied by ``depth``.  We do not inherit any of them.

    The derivation: price is IMD per ETH and equals ``1.0001 ** tick``, so a
    HIGHER tick means more IMD per ETH, means IMD is CHEAPER there.  IMD's price
    ratio between the two venues is therefore ``1.0001 ** (reference - hook)``,
    and a positive result means a buyer pays more on the hook pool.

    **Both ticks must come from the same block.**  Reading them a block apart is
    how a 1.3% disagreement appears out of nothing in a thin pool -- see
    :meth:`~maxpane_dashboard.data.surf_pool4_client.Pool4Client.fetch_reference_slot0`,
    which batches with the hook read for exactly this reason.

    A tick of ``0`` is a real price (one IMD per ETH), so the missing-tick guard
    tests ``is None`` rather than truthiness.
    """
    if hook_tick is None or reference_tick is None:
        return None
    return (math.exp((reference_tick - hook_tick) * _LOG_BASE) - 1.0) * 100.0


def cheaper_venue(
    *,
    gap_pct: float | None,
    hook_fee_bps: int | None,
    reference_fee_bps: int | None,
) -> str | None:
    """Which venue a buyer should use, or ``None`` when the answer is neither.

    ``None`` is a real answer here and the common one: a gap smaller than the
    two pools' fees summed cannot be arbitraged away, and a reader who moves
    venues to capture it pays more in spread than the gap is worth.  PRD 8.3.

    Both live pools charge 1% (10000 bps), so the bar is a 2% gap, and nothing
    observed has ever cleared it -- +1.46%, +0.2% and -0.01% inside one hour.
    Silence is therefore the *expected* output, not a sign the fold never ran.

    An unreadable fee returns ``None`` rather than defaulting to zero.  A zero
    default would make every threshold trivially clear and name a venue on
    noise -- the ``0 in (None, False, ())`` failure this repo has already
    shipped once.

    The two words it can return are :data:`~maxpane_dashboard.data.surf_models.POOL4_VENUE_WORDS`.
    They are restated here as literals rather than imported: the widget above
    branches on them, and a derivation would make the agreement test compare a
    constant against itself.
    """
    if gap_pct is None or hook_fee_bps is None or reference_fee_bps is None:
        return None
    threshold = (hook_fee_bps + reference_fee_bps) / 10000.0
    if abs(gap_pct) <= threshold:
        return None
    return "reference" if gap_pct > 0 else "here"
