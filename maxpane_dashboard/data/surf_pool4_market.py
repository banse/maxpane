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


# ---------------------------------------------------------------------------
# The realised trailing return — WP3
# ---------------------------------------------------------------------------

#: Seconds in a year, for annualising a window.  365 days, not 365.25: the
#: protocol's own docs annualise on 365 and a panel that disagrees with the
#: protocol's stake page by 0.07% invites a bug report that is not a bug.
_YEAR_SECONDS = 365 * 24 * 3600


def trailing_return_pct(
    *,
    dripped_imd: float | None,
    window_seconds: float | None,
    vault_assets: float | None,
) -> float | None:
    """Realised staking return over a window, annualised.  PRD 8.1.

    **This is not ``pool4_implied_apr_pct``.**  That key is the dripper's rate
    annualised -- a *ceiling* on how fast rewards can reach the vault, which
    the vault panel deliberately refuses to call APR.  This is what actually
    arrived: the dripper's delivery events summed over the window, annualised
    against TVL.  The protocol's own docs say the rate "is only a cap on how
    fast that reaches the vault", so the two numbers answer different
    questions and a window under the cap must produce the smaller one.

    **It is lumpy by construction** -- zero through a quiet stretch, spiking
    after a sell-off, because trims only happen when sells exceed headroom.
    That is why the caller renders it with its window in the label
    (``4.0% trailing 7d``) and never as a bare rate.

    ``window_seconds`` is the *measured* span of the window, read off the two
    boundary blocks.  Passing a nominal seven days for a window that fell short
    of one annualises a smaller number as though it had spanned longer, which
    overstates the return in the flattering direction.

    Zero is a real answer and returns ``0.0``.  ``None`` is reserved for "we
    could not compute it": an unread drip total, an unread or empty vault, or
    a zero-length window.  The two are separate branches on purpose and have a
    test each, because a quiet week rendered as ``--`` hides a fact that was
    read, and a dead read rendered as ``0.0%`` claims one that was not.
    """
    if dripped_imd is None or vault_assets is None or window_seconds is None:
        return None
    if vault_assets <= 0.0 or window_seconds <= 0.0:
        return None
    return (dripped_imd / vault_assets) * (_YEAR_SECONDS / window_seconds) * 100.0


# ---------------------------------------------------------------------------
# The staker sweep and the concentration it answers — WP4
# ---------------------------------------------------------------------------

#: ERC-20 mints arrive from here and burns go here.  It is not a holder.
ZERO_ADDRESS = "0x" + "00" * 20


class ShareBalances(dict):
    """Folded sIMD balances, carrying whether the sweep actually finished.

    A plain dict would let an incomplete fold be ranked as though it were the
    whole vault, which understates concentration -- the direction that makes a
    risk look smaller than it is.  The flag rides with the data, so a caller
    cannot hold the balances and forget the caveat: they are one object.
    """

    complete: bool = False


def fold_share_transfers(logs, *, complete: bool) -> ShareBalances:
    """Fold sIMD ``Transfer`` logs into per-holder balances.

    Mints arrive from the zero address and burns go to it; both are ordinary
    transfers in ERC-20 and neither is a holder.  A holder whose balance
    reaches zero is dropped rather than kept, so nothing ranks an address that
    holds nothing.

    *logs* are ``{"from", "to", "value"}`` rows **in chain order**.  Order is
    the caller's responsibility and it matters: a debit applied before its
    credit takes an intermediate balance negative, and the drop-at-zero rule
    would then delete a holder who never left.
    """
    out = ShareBalances()
    out.complete = complete
    for log in logs:
        frm, to, value = log["from"], log["to"], int(log["value"])
        if frm != ZERO_ADDRESS:
            out[frm] = out.get(frm, 0) - value
            if out[frm] <= 0:
                out.pop(frm, None)
        if to != ZERO_ADDRESS:
            out[to] = out.get(to, 0) + value
    return out


def staker_rows(balances, *, share_price: float | None, limit: int = 20):
    """Ranked rows in IMD, or ``None`` if shares cannot be converted.

    ``share_price`` is IMD **per balance unit** -- the unit *balances* are
    folded in, not per whole share -- and it is a LIVE read: the vault is a
    Solady ERC-4626 reporting ``decimals()`` of 24, so one whole share is
    ``1e24`` units and a caller holding raw log amounts must divide the
    whole-share price by ``10 ** decimals()`` before passing it here.  Getting
    that wrong does not raise: it scales every row by 1e24 and renders as a
    plausible, enormous number.  CLAUDE.md's decimals rule, and
    ``test_the_share_price_the_rows_take_is_per_balance_unit_not_per_whole_share``
    pins it against the vault's own ``totalAssets()``.

    ``limit`` caps the **rows**, never the denominator.  ``pct`` is a share of
    the whole vault, so a capped leaderboard does not add to 100% -- and must
    not be made to, because the gap between the page and the vault is the
    dispersion the panel exists to show.
    """
    if share_price is None or not balances:
        return None
    total = sum(balances.values())
    if total <= 0:
        return None
    ranked = sorted(balances.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {
            "rank": i + 1,
            "address": addr,
            "imd": shares * share_price,
            "pct": shares / total * 100.0,
        }
        for i, (addr, shares) in enumerate(ranked)
    ]


def top_n_pct(rows, n: int = 3, *, complete: bool) -> float | None:
    """Share of the vault the top ``n`` hold, or ``None`` on a partial fold.

    ``complete`` is not advisory.  Concentration computed from part of the
    holder set is smaller than the truth, so a partial sweep would report a
    reassuring number for a vault nobody measured -- ``clean_routed_eth``'s
    guard, and the reason the flag travels on :class:`ShareBalances` rather
    than beside it.
    """
    if not complete or not rows:
        return None
    return sum(r["pct"] for r in rows[:n])
