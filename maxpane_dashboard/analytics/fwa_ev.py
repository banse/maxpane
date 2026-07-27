"""Pure EV and pricing math for the Fake World Assets (FWA) dashboard.

FWA sells one draw from a pool of NFT positions.  Selection weight is
**inversely** proportional to the ETH backing a position carries
(``weight = 1e36 / backing``), so the price the protocol charges tracks the
*harmonic* mean of all backings, not the arithmetic mean.  The purchaser then
chooses, **after** seeing the draw, between selling the NFT back for
``85% x backing`` (a pre-funded standing bid) and keeping it at whatever the
collection floor happens to be.  That post-draw choice is a real option, and it
is why the pull EV is an expectation over ``max(sell_back, floor)`` rather than
over either leg alone.

Keyless floor prices reach 26 of the 38 collections holding live positions, but
those 26 carry only about a fifth of the draw weight: roughly **79.6% of pool
weight has no keyless floor** (findings §13.14).  The flagship number is
therefore returned as a **band**, never a point — see :func:`pull_ev_band`.
Both figures are live measurements, not constants; nothing here hardcodes
either, and the coverage counters are computed from whatever the floor sweep
actually returned.

Everything here is pure: stdlib only, no I/O, no network, no models, no
Textual.  Wei-valued functions return ``int`` and use integer floor division
exactly where the contract does.

Sources:
    docs/fwa_game_mechanics.md  §5 (weights), §6 (pricing), §7 (standing bid),
                                §9 (fees), §11 (crown), §14.2 (purchaser)
    docs/fwa_technical_findings.md §4.1 (view functions), §6 (enumeration)
    docs/fwa_PRD.md             §3 (the EV band), §4 (surcharge ramp),
                                §7 (correctness rules 1-5, 11)

Pattern: ``maxpane_dashboard/analytics/ev.py``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

#: ``INVERSE_WEIGHT_NUMERATOR`` in ``src/FWA.sol``.  Sized far above any
#: realistic backing so ``1e36 // backing`` never floors to zero.
INVERSE_WEIGHT_NUMERATOR: int = 10**36

#: ``BPS()`` — the protocol's basis-point denominator.
BPS: int = 10_000

WEI_PER_ETH: int = 10**18

#: ``surchargeBps`` — 1000 bps (10%).  Live-read where possible (rule 6).
DEFAULT_SURCHARGE_BPS: int = 1_000

#: ``settlementDiscountBps()`` returns **8500**, and that is the purchaser
#: *payout* rate (85%), NOT a 15% discount.  Naming trap; do not invert it
#: (PRD rule 3, mechanics §7).
DEFAULT_PURCHASER_PAYOUT_BPS: int = 8_500

#: ``topThresholdBps`` — a challenger needs 1.10x the incumbent's backing.
DEFAULT_TOP_THRESHOLD_BPS: int = 1_000

#: Surcharge ramp endpoints (PRD §4).  Fallback labels only — see
#: :func:`surcharge_ramp_share`.
HOT_GAP_SECONDS: int = 60
COLD_GAP_SECONDS: int = 3_600


# ---------------------------------------------------------------------------
# 1-3. Weights  (PRD rule 1, rule 4)
# ---------------------------------------------------------------------------


def inverse_weight(backing_wei: int) -> int:
    """Selection weight of a single position: ``1e36 // backing_wei``.

    Integer floor division, exactly as ``src/FWA.sol`` does it.  Verified
    against all 3,867 live positions with zero mismatches, e.g. the largest
    position (221 ETH) has weight ``4524886877828054``.

    Weight is **inverse** to backing: pair an NFT with more ETH and it is drawn
    less often.  Any proportional-weighting assumption is wrong (PRD rule 1).

    Raises:
        ValueError: if ``backing_wei <= 0``.  ``minBacking`` is 0.01 ETH, so a
            non-positive backing means the caller decoded something wrong.
    """
    if backing_wei <= 0:
        raise ValueError(f"backing must be positive wei, got {backing_wei!r}")
    return INVERSE_WEIGHT_NUMERATOR // backing_wei


def total_weight(backings: Iterable[int]) -> int:
    """``Sum(1e36 // backing_i)`` — the denominator of every selection probability.

    Must equal ``totalWeight()`` read at the *same pinned block*; a mismatch
    means the slot sweep missed positions (PRD rule 11, findings §6.2).
    """
    return sum(inverse_weight(b) for b in backings)


def weighted_backing_total(backings: Iterable[int]) -> int:
    """``Sum(weight_i * backing_i)`` — the numerator of the pool price.

    .. warning::

       This quantity is **neither wei nor ETH**, and it is **not TVL**.  Because
       ``weight_i * backing_i`` is approximately ``1e36`` for every position,
       the sum is approximately ``activeListingCount * 1e36``.  Its leading
       digits therefore look like a count of ETH — the live value
       ``3.891e39`` against 3,891 active listings — which makes rendering it as
       "3,891 ETH TVL" a tempting and completely wrong thing to do
       (PRD rule 4, findings §6.4 TRAP 3).

       It may **never** be rendered as TVL, as a wei amount, or as an ETH
       amount.  It exists only as the numerator of :func:`expected_value_wei`.
       For value held use ``eth_getBalance(FWA core)`` or the enumerated
       ``Sum(backing_i)``.
    """
    return sum(inverse_weight(b) * b for b in backings)


# ---------------------------------------------------------------------------
# 4-5. The two floor divisions  (PRD rule 2)
# ---------------------------------------------------------------------------


def expected_value_wei(weighted_total: int, total_weight: int) -> int:
    """``weightedBackingTotal / totalWeight`` — the **first** floor division.

    This is the pool's expected value per draw, and because weights are inverse
    to backing it is the harmonic mean of all backings.  Returns 0 when
    ``total_weight == 0``, matching ``if (totalWeight == 0) return 0;``.

    Keep this separate from :func:`acquisition_fee_wei`.  The two divisions are
    sequential in the contract and collapsing them into a single expression
    changes the result by up to a wei (see that function's docstring).
    """
    if total_weight <= 0:
        return 0
    return weighted_total // total_weight


def acquisition_fee_wei(
    weighted_total: int,
    total_weight: int,
    surcharge_bps: int = DEFAULT_SURCHARGE_BPS,
) -> int:
    """``acquisitionFee()`` — ``ev * (BPS + surchargeBps) / BPS``.

    This is the **second** of two sequential floor divisions::

        ev  = weightedBackingTotal / totalWeight      # floor division #1
        fee = ev * (10000 + surchargeBps) / 10000     # floor division #2

    The algebraically equivalent one-step form
    ``weightedBackingTotal * 11000 / (totalWeight * 10000)`` is **not**
    equivalent in integer arithmetic.  At block 25612701 it returns
    ``136260883651302692`` while the contract returns ``136260883651302691``.
    At block 25612655 the two forms happen to agree, which is precisely why a
    single sample cannot catch the collapse.

    Returns 0 when ``total_weight == 0`` (PRD rule 2).

    ``surchargeBps`` has no getter; 1000 bps is the live value, passed in so it
    stays a parameter rather than a hardcoded constant (PRD rule 6).
    """
    ev = expected_value_wei(weighted_total, total_weight)
    if ev == 0:
        return 0
    return ev * (BPS + surcharge_bps) // BPS


def surcharge_wei(fee_wei: int, surcharge_bps: int = DEFAULT_SURCHARGE_BPS) -> int:
    """The surcharge component embedded in an acquisition fee, in wei.

    ``fee = ev * (BPS + surchargeBps) / BPS``, so the surcharge slice is
    ``fee * surchargeBps / (BPS + surchargeBps)`` — about 1/11th of the fee at
    the live 1000 bps.  This is the pot that the hot/cold ramp splits between
    depositors and the purchaser's $FWA allowance (PRD §4).
    """
    if fee_wei <= 0 or surcharge_bps <= 0:
        return 0
    return fee_wei * surcharge_bps // (BPS + surcharge_bps)


# ---------------------------------------------------------------------------
# 6. Means and the gap  (mechanics §5, §6, §14.2)
# ---------------------------------------------------------------------------


def harmonic_mean_wei(backings: Sequence[int]) -> int:
    """``n / Sum(1 / backing_i)``, in wei — what the acquisition price tracks.

    Computed as ``n * 1e36 // totalWeight`` so it uses the same integer
    arithmetic as the contract.  At the pinned block 25612701 this returns
    ``123873530592093356`` (0.1239 ETH), identical to
    :func:`expected_value_wei` on that block's aggregates.

    Dominated by the cheapest positions, which is the whole point: the
    lightly-backed positions are the ones you almost always receive.
    """
    if not backings:
        return 0
    tw = total_weight(backings)
    if tw <= 0:
        return 0
    return len(backings) * INVERSE_WEIGHT_NUMERATOR // tw


def arithmetic_mean_wei(backings: Sequence[int]) -> int:
    """``Sum(backing_i) // n`` — the average ETH actually sitting in the pool.

    Never the price.  Contrast it with :func:`harmonic_mean_wei`; the distance
    between them is the option value in the tail.
    """
    if not backings:
        return 0
    return sum(backings) // len(backings)


def hm_am_gap(backings: Sequence[int]) -> float:
    """``arithmetic_mean / harmonic_mean`` — the protocol in one number.

    Live pool: roughly 4.0x.  The pool holds about four times more ETH per
    position than the price implies, because the price is set by the dust and
    the ETH is held by the chase items you almost never draw.

    Returns 0.0 for an empty pool.
    """
    hm = harmonic_mean_wei(backings)
    if hm <= 0:
        return 0.0
    return arithmetic_mean_wei(backings) / hm


# ---------------------------------------------------------------------------
# 7. Selection odds  (mechanics §5)
# ---------------------------------------------------------------------------


def selection_probability(backing_wei: int, total_weight: int) -> float:
    """``P(select i) = weight_i / totalWeight``.

    Returns 0.0 when ``total_weight <= 0``.
    """
    if total_weight <= 0:
        return 0.0
    return inverse_weight(backing_wei) / total_weight


def expected_draws_until(backing_wei: int, total_weight: int) -> float:
    """Expected number of acquisitions before this position is drawn.

    ``totalWeight / weight_i``.  For the 221 ETH position against the live
    totalWeight that is roughly 6.9 million draws.
    """
    weight = inverse_weight(backing_wei)
    if weight <= 0:
        return float("inf")
    return total_weight / weight


def collection_weight_shares(
    positions: Sequence[tuple[int, str]],
    total_weight: int | None = None,
) -> dict[str, float]:
    """Share of selection weight held by each collection, in percent.

    Args:
        positions: ``(backing_wei, collection)`` pairs.
        total_weight: denominator to measure against.  Defaults to the summed
            weight of ``positions``; pass the pool-wide ``totalWeight()`` to
            measure a subset against the whole pool.

    Returned percentages are ordered largest first.  Expect genuinely tiny
    numbers: CryptoPunks 721 holds 137.10 ETH across 3 positions and 0.000% of
    the weight.  That asymmetry *is* the protocol.
    """
    by_collection: dict[str, int] = {}
    summed = 0
    for backing_wei, collection in positions:
        weight = inverse_weight(backing_wei)
        by_collection[collection] = by_collection.get(collection, 0) + weight
        summed += weight

    denominator = summed if total_weight is None else total_weight
    if denominator <= 0:
        return {name: 0.0 for name in by_collection}

    shares = {name: weight / denominator * 100.0 for name, weight in by_collection.items()}
    return dict(sorted(shares.items(), key=lambda kv: kv[1], reverse=True))


# ---------------------------------------------------------------------------
# 8. The flagship: the pull EV band  (PRD §3, rules 3 and 4)
# ---------------------------------------------------------------------------


def sellback_payout_wei(
    backing_wei: int,
    payout_bps: int = DEFAULT_PURCHASER_PAYOUT_BPS,
) -> int:
    """What the purchaser receives for accepting the depositor's standing bid.

    ``backing * settlementDiscountBps / BPS``.  **8500 bps means the purchaser
    receives 85%**, not that they lose 85% and not that they receive 15%.  The
    onchain getter is named ``settlementDiscountBps()`` and returns the payout
    rate; the 15% retained slice is the complement (mechanics §7, PRD rule 3).
    """
    return backing_wei * payout_bps // BPS


def pull_ev_band(
    positions: Sequence[tuple[int, str]],
    floors_eth: Mapping[str, float],
    acquisition_fee_wei: int,
    purchaser_payout_bps: int = DEFAULT_PURCHASER_PAYOUT_BPS,
    rebate_share: float = 0.0,
    surcharge_bps: int = DEFAULT_SURCHARGE_BPS,
) -> dict:
    """Expected value of one pull, as a **band**::

        EV = Sum p_i * max(0.85 * backing_i, floor_i) - acquisitionFee
             + rebateShare * surcharge

    The purchaser chooses *after* the draw, so each position is worth the
    better of its two exits.  Keyless floors reach 26 of 38 live collections
    but only ~20% of the draw weight — the two largest weight buckets are
    unpriced — so a single number here would be a lie dressed as precision.
    Two bounds are returned instead:

    * ``lower_eth`` — a position in an **unpriced** collection contributes
      **zero**.  Strictly pessimistic: it counts only value that can actually
      be verified right now, so it cannot mislead someone into a pull.
    * ``best_eth`` — an unknown floor is **excluded from the max()** rather
      than zeroed, so the position keeps its guaranteed ``0.85 x backing``
      sell-back leg and simply forgoes the keep option.

    With full floor coverage the two collapse onto each other; with none,
    ``best_eth`` degrades to the sell-back-only expectation and ``lower_eth``
    to ``-acquisitionFee``.  The width of the band *is* the uncertainty.

    **Invariant: ``lower_eth <= best_eth``**, enforced here rather than only in
    the tests.

    There is deliberately **no** ``ev`` / ``point`` / ``value`` field.  This
    number tells someone whether to spend ETH; it does not get to pretend it is
    confident (PRD §3, plan risk R13).

    Args:
        positions: ``(backing_wei, collection)`` pairs for every live position.
        floors_eth: collection -> floor price in ETH.  Missing keys mean
            "unpriced"; Art Blocks style multi-collection contracts should be
            omitted rather than given a misleading contract-level floor.
        acquisition_fee_wei: the **live** fee from ``acquisitionFee()`` or
            ``quoteAcquisitionPrice()`` — never recomputed here.
        purchaser_payout_bps: 8500 = the purchaser receives 85% (rule 3).
        rebate_share: fraction of the surcharge routed back to the purchaser as
            a $FWA allowance, from the live ``tokenShareBps`` (PRD §4).
        surcharge_bps: used only to size the surcharge inside the fee.

    Returns:
        ``lower_eth``, ``best_eth``, ``sellback_only_eth``,
        ``acquisition_fee_eth``, ``rebate_eth``, ``collections_priced``,
        ``collections_total``, ``weight_priced_pct``, ``positions``.
    """
    fee_eth = acquisition_fee_wei / WEI_PER_ETH
    rebate_eth = surcharge_wei(acquisition_fee_wei, surcharge_bps) * rebate_share / WEI_PER_ETH

    pool_collections: set[str] = set()
    priced_collections: set[str] = set()
    weight_sum = 0
    weight_priced = 0

    lower_gross = 0.0
    best_gross = 0.0
    sellback_gross = 0.0

    weighted: list[tuple[int, float, float, float]] = []
    for backing_wei, collection in positions:
        weight = inverse_weight(backing_wei)
        weight_sum += weight
        pool_collections.add(collection)

        sellback_eth = sellback_payout_wei(backing_wei, purchaser_payout_bps) / WEI_PER_ETH
        floor = floors_eth.get(collection)

        if floor is None:
            # unknown floor: zeroed for the lower bound, excluded from the
            # max() for the best estimate (so the sell-back leg survives)
            lower_value = 0.0
            best_value = sellback_eth
        else:
            priced_collections.add(collection)
            weight_priced += weight
            lower_value = max(sellback_eth, float(floor))
            best_value = lower_value

        weighted.append((weight, lower_value, best_value, sellback_eth))

    if weight_sum > 0:
        for weight, lower_value, best_value, sellback_eth in weighted:
            probability = weight / weight_sum
            lower_gross += probability * lower_value
            best_gross += probability * best_value
            sellback_gross += probability * sellback_eth

    lower_eth = lower_gross - fee_eth + rebate_eth
    best_eth = best_gross - fee_eth + rebate_eth

    # Structural invariant: every lower_value is <= its best_value by
    # construction, so this can only fire on a real regression.  Raise rather
    # than `assert` so it survives `python -O`.
    if lower_eth > best_eth + 1e-12:
        raise AssertionError(
            f"pull_ev_band invariant violated: lower_eth {lower_eth!r} > best_eth {best_eth!r}"
        )
    lower_eth = min(lower_eth, best_eth)  # float dust only

    weight_priced_pct = (weight_priced / weight_sum * 100.0) if weight_sum > 0 else 0.0

    return {
        "lower_eth": lower_eth,
        "best_eth": best_eth,
        "sellback_only_eth": sellback_gross - fee_eth + rebate_eth,
        "acquisition_fee_eth": fee_eth,
        "rebate_eth": rebate_eth,
        "collections_priced": len(priced_collections),
        "collections_total": len(pool_collections),
        "weight_priced_pct": weight_priced_pct,
        "positions": len(weighted),
    }


# ---------------------------------------------------------------------------
# 9-11. Jackpot, crown, surcharge ramp
# ---------------------------------------------------------------------------


def jackpot_ratio(
    max_backing_wei: int,
    fee_wei: int,
    payout_bps: int = DEFAULT_PURCHASER_PAYOUT_BPS,
) -> float:
    """Best-case payout multiple: ``max_backing * 0.85 / acquisitionFee``.

    At the live 221 ETH maximum backing and a 0.1363 ETH fee this is about
    1,378x.  Always render it next to :func:`jackpot_probability` — the two
    numbers are meaningless apart.  Returns 0.0 if the fee is non-positive.
    """
    if fee_wei <= 0:
        return 0.0
    return sellback_payout_wei(max_backing_wei, payout_bps) / fee_wei


def jackpot_probability(max_backing_wei: int, total_weight: int) -> float:
    """Probability of drawing the largest position: about 1.45e-7 live.

    The other half of :func:`jackpot_ratio`.  A 1,378x payout at 1.45e-7 is an
    expected contribution of roughly 0.0002x — the jackpot is a story, not an
    edge.
    """
    return selection_probability(max_backing_wei, total_weight)


def crown_seize_wei(
    incumbent_backing_wei: int,
    threshold_bps: int = DEFAULT_TOP_THRESHOLD_BPS,
) -> int:
    """Minimum backing needed to take the crown from the incumbent.

    From ``_beatsTop``::

        value * BPS >= listings[topListingId].value * (BPS + topThresholdBps)

    At the live ``topThresholdBps = 1000`` that is 1.10x the incumbent's
    backing.  The crown is a challenge against the current holder, not a ranked
    leaderboard: the contract never backfills the largest deposit, so a
    slightly larger position can still fall short (mechanics §11).
    """
    return incumbent_backing_wei * (BPS + threshold_bps) // BPS


def surcharge_ramp_share(
    gap_seconds: float,
    hot_gap: int = HOT_GAP_SECONDS,
    cold_gap: int = COLD_GAP_SECONDS,
) -> float:
    """Fraction of the surcharge routed to the *purchaser* on a cold pool.

    0.0 at or below ``hot_gap`` (the whole surcharge goes to depositors), 1.0
    at or above ``cold_gap`` (the whole surcharge becomes the purchaser's $FWA
    buy allowance), linear in between.

    .. warning::

       **Fallback label only.**  The linearity of ``tokenShareBps(uint256)``
       between the two endpoints is **unconfirmed** — only the endpoints were
       verified (PRD §4 implementation note, PRD §13 open questions).  Always
       read the live ``tokenShareBps`` value from the chain and let it win;
       use this ramp only to label a pool as hot / warming / cold when the live
       value is unavailable.  Never price a pull off this function.
    """
    if cold_gap <= hot_gap:
        return 1.0 if gap_seconds >= cold_gap else 0.0
    if gap_seconds <= hot_gap:
        return 0.0
    if gap_seconds >= cold_gap:
        return 1.0
    return (gap_seconds - hot_gap) / (cold_gap - hot_gap)


# ---------------------------------------------------------------------------
# 12-13. Revenue split, fee split, round trip
# ---------------------------------------------------------------------------


def take_rate(revenue: float, fees: float) -> float:
    """``revenue / fees`` — the protocol's whole economic posture in one number.

    Live: 8.8%.  About 91% of fees flow to depositors rather than the team.
    Returns 0.0 when ``fees <= 0``.
    """
    if fees <= 0:
        return 0.0
    return revenue / fees


def per_position_credit(distributable: int, active_count: int) -> int:
    """Fee credit per active position — an **equal** split (PRD rule 5).

    ``feeShare`` is 1 for every position regardless of backing, and
    ``feeShareTotal() == activeListingCount()`` is a free onchain invariant.
    Backing buys *duration* in the pool, not a larger share of the fees.

    Floor division, matching the contract's ceiled-``feeDebt`` accounting which
    keeps ``credited <= collected``.  Returns 0 when there are no positions.
    """
    if active_count <= 0:
        return 0
    return distributable // active_count


def settlement_shares(counts: Mapping[str, int]) -> list[dict]:
    """Settlement outcome mix as percentage shares, largest first.

    Live all-time: accept-bid-as-$FWA 73.92%, accept-bid-in-ETH 13.84%,
    relist 7.64%, keep 4.60%, force-finalized 0.00% over 51,522 settlements.
    Roughly 88% of purchasers sell the NFT straight back, and only 4.6% keep
    the JPEG — which is the market's own estimate of how often the keep option
    is worth exercising.

    Returns:
        A list of ``{"outcome": str, "count": int, "share_pct": float}``.
        Shares sum to 100.0 (or all 0.0 when every count is zero).
    """
    total = sum(counts.values())
    rows = [
        {
            "outcome": outcome,
            "count": count,
            "share_pct": (count / total * 100.0) if total > 0 else 0.0,
        }
        for outcome, count in counts.items()
    ]
    rows.sort(key=lambda row: (-row["count"], row["outcome"]))
    return rows


def round_trip_return(
    drawn_backing_wei: int,
    fee_wei: int,
    payout_bps: int = DEFAULT_PURCHASER_PAYOUT_BPS,
) -> float:
    """``0.85 * drawn_backing / acquisitionFee`` — buy, then immediately sell back.

    At the harmonic mean itself this is ``0.85 / 1.10 = 0.773``: a structural
    **-23%**.  Flipping is negative-EV by construction.  A purchaser only comes
    out ahead by drawing above-mean positions, by exercising the keep option,
    or by valuing the $FWA rewards.

    Returns 0.0 if the fee is non-positive.
    """
    if fee_wei <= 0:
        return 0.0
    return sellback_payout_wei(drawn_backing_wei, payout_bps) / fee_wei
