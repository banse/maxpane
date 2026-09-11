"""POOL4 depth ladder -- what the hook's own liquidity bids as IMD falls.

PURE. Stdlib only: no I/O, no clock, no Textual, no ``data/``. PRD 6.5, 7.5.

**What this is and is not.** These are quotes from the position as it stands
*right now*. A ``rebalance()`` closes the backstop band and redeploys it from
just above spot, so every number here can move the moment a keeper acts. It is
never a floor, never a guarantee and never protection -- see PRD 8.2 and the
forbidden-word test in ``tests/widgets/test_surf_pool4u_depth.py``.

**Orientation.** ETH is currency0 and price is IMD per ETH, so **tick up means
IMD is cheaper**: a reader selling IMD pushes the tick up, the pool pays out
ETH (currency0) and absorbs IMD (currency1).

Constant-liquidity math over a tick range::

    amount0 (ETH)  = L * (sqrtB - sqrtA) / (sqrtA * sqrtB)
    amount1 (IMD)  = L * (sqrtB - sqrtA)
    sqrt(price@t)  = 1.0001 ** (t / 2)

Validated against an independent implementation -- the ``pool4hook-research``
skill, captured at block 25955365 in
``tests/fixtures/surf/pool4/oracle_25955365.json`` and cross-checked by
``tests/data/test_surf_pool4_oracle.py``.
"""

from __future__ import annotations

import math

#: v4's max usable tick. The backstop band runs from its lower tick to here,
#: which is what makes its ETH single-sided.
MAX_TICK = 887272

#: log(1.0001), hoisted: this is the hot constant in every conversion.
_LOG_BASE = math.log(1.0001)

#: The ladder's rungs, as percentage falls in IMD's price. Five rows, chosen
#: to fit the panel: -1 is "a normal candle", -50 is "a bad day". The skill's
#: own ladder runs to -90, which is past the point a reader learns anything.
DEPTH_MOVES: tuple[int, ...] = (1, 5, 10, 20, 50)


def sqrt_ratio(tick: float) -> float:
    """sqrt(price) at ``tick``, where price is IMD per ETH."""
    return 1.0001 ** (tick / 2.0)


def eth_between(liquidity: float, tick_lo: int, tick_hi: int) -> float:
    """Whole ETH a position of ``liquidity`` pays as the tick rises lo -> hi.

    Returns 0.0 -- not a negative, not None -- when the range does not open,
    because "the price did not get there" is a representable zero.
    """
    if tick_hi <= tick_lo:
        return 0.0
    a, b = sqrt_ratio(tick_lo), sqrt_ratio(tick_hi)
    return liquidity * (b - a) / (a * b) / 1e18


def tick_for_price_drop(tick_now: int, drop_pct: float) -> int:
    """The tick IMD's price reaches after falling ``drop_pct`` percent.

    A fall in IMD's price is a *rise* in IMD-per-ETH, hence a rise in tick.
    """
    if drop_pct <= 0.0 or drop_pct >= 100.0:
        return tick_now
    ratio = 1.0 / (1.0 - drop_pct / 100.0)
    return tick_now + int(round(math.log(ratio) / _LOG_BASE))


def depth_rows(
    *,
    tick: int | None,
    position_liquidity: float | None,
    band_lower_tick: int | None,
    band_liquidity: float | None,
) -> list[dict] | None:
    """The cumulative ladder, or ``None`` if the position could not be read.

    Keyword-only on ``_pool4_cap_headroom``'s precedent: two tick arguments
    and two liquidity arguments sitting side by side is exactly the signature
    where a positional swap is silent, so make it a ``TypeError``.

    ``None`` for the whole ladder, never a ladder of zeros: a zero ladder
    renders as "this pool bids nothing", which is a confident wrong answer to
    a question we could not answer at all.

    No band deployed is *not* that case: the full-range position still bids,
    so the ladder is real and ``band_used_pct`` is a true 0.0.
    """
    if tick is None or position_liquidity is None:
        return None

    has_band = band_lower_tick is not None and band_liquidity is not None
    band_total = (
        eth_between(band_liquidity, band_lower_tick, MAX_TICK) if has_band else 0.0
    )

    rows: list[dict] = []
    for move in DEPTH_MOVES:
        target = tick_for_price_drop(tick, float(move))
        full = eth_between(position_liquidity, tick, target)
        band = 0.0
        if has_band and target > band_lower_tick:
            band = eth_between(band_liquidity, max(tick, band_lower_tick), target)
        used = (band / band_total * 100.0) if band_total > 0.0 else 0.0
        rows.append(
            {
                "move_pct": move,
                "eth_paid": full + band,
                "band_used_pct": min(used, 100.0),
            }
        )
    return rows
