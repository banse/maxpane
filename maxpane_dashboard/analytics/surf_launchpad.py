"""Launchpad ranking and thresholds.

Pure functions.  No I/O, no Textual, and no direct wall-clock read of any
kind -- every entry point takes ``now_ts`` instead.

The HOT COIN threshold is **relative to the day's own distribution**.  At
~1,170 swaps/day across ~146 coins a fixed "any swap" threshold lights the row
permanently, which is the trap ``signals.py`` documents for ``‹ widen``: a
marker that is always on means nothing.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

#: A coin is hot at this multiple of the day's median swap count...
HOT_MULTIPLE = 3
#: ...but never below this floor, so a quiet day (median 1) cannot promote a
#: coin on 3 swaps.
HOT_FLOOR = 5
#: Below this many active coins there is no meaningful median at all.
HOT_MIN_ACTIVE = 5
#: How old a swap distribution may be before HOT COIN refuses to read it.
#:
#: The distribution is a **windowed** statistic -- "how many swaps each coin
#: took in the last 24h" -- so it decays in a way its siblings on this rail do
#: not.  ``burn_ready`` ("``previewBridge()`` would send something") is a
#: reading of the pipeline's state right now, not a window over a period; "40 swaps this day", read a week
#: later, describes a day that has entirely passed and says nothing at all
#: about now.  Serving it from the launchpad tier's never-expiring last-good
#: slot is what let HOT COIN report ``ICE · 40 swaps`` off a day-old cache
#: through a total outage (final-fix-wave C1) -- the "never a stale number
#: presented as live" rule, on the one reading here that cannot survive being
#: replayed.
#:
#: The bound is the **window's own length**, not a tier interval: once the
#: reading is older than the day it measured, zero of that day overlaps now.
#: ``surf_client.LAUNCHPAD_DAY_BLOCKS`` * ``_LAUNCHPAD_BLOCK_SECONDS`` is that
#: day, and ``test_the_hot_coin_staleness_bound_is_the_window_it_measures``
#: pins the two together so a re-cut window cannot silently outgrow this.
#:
#: This was an hour (``3600.0``) until a live measurement (2026-08-23) found
#: 1 swap in an hour across 146 coins: every coin tied at 0, the ranking fell
#: through to ``-age_s``, and the panel showed the 20 oldest never-traded
#: coins at an identical initial curve price. The same day held 46 swaps
#: across 10 active coins, so the window widened to match what the chain
#: actually produces.
HOT_MAX_AGE_S = 86400.0


def hot_coin_threshold(swaps_by_coin: Mapping[str, int]) -> int | None:
    """Swap count a coin must reach today to be HOT, or ``None``.

    ``None`` means "the day is too thin to judge" and must render OK, not a
    fire: an empty day is not evidence of a hot coin.
    """
    active = [n for n in swaps_by_coin.values() if n > 0]
    if len(active) < HOT_MIN_ACTIVE:
        return None
    return max(HOT_FLOOR, int(statistics.median(active)) * HOT_MULTIPLE)


def mcap_eth(price_eth: float | None, coin_supply_wei: int | None) -> float | None:
    """Fully-diluted market cap in ETH, or ``None``.

    Both inputs can genuinely be unknown -- the price round is a separate
    ``aggregate3`` that can fail on its own, and a cursor written before the
    supply was persisted has no supply -- and an unknown input makes an
    unknown market cap, never ``0.0``. A supply of exactly zero is treated
    the same way: it is not a market cap of zero, it is a coin whose supply
    we cannot believe.

    Measured 2026-08-25: all 146 launchpad coins report ``coinSupply`` ==
    1e9 and their token's live ``totalSupply()`` agrees. The supply is still
    read per coin from that coin's own ``Launched`` event rather than
    assumed -- a uniform value found by sampling is not a contract guarantee.
    """
    if price_eth is None or not coin_supply_wei:
        return None
    try:
        return float(price_eth) * (int(coin_supply_wei) / 1e18)
    except (TypeError, ValueError):
        return None


def rank_coins(
    launches: Sequence[Mapping[str, Any]],
    day_swaps: Sequence[Mapping[str, Any]],
    swaps_all: Mapping[str, int],
    now_ts: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Rank launched coins by 24h swap count, most active first.

    Ranking happens **from logs alone** -- no per-coin RPC call.  One
    ``getLogs`` over ``CurveSwap`` yields counts for every coin, so cost is
    flat whether the launchpad holds 146 coins or 1,460.  Curve state is read
    only for the rows this function returns.

    ``ticker`` and ``name`` are carried through raw: they are attacker-chosen
    and are escaped at render, not here.

    Swaps are attributed by ``pool_id`` -- the coin's identity -- and never by
    ticker (final fix wave, I1).  ``launch(string,string)`` is permissionless
    and unpriced beyond gas, so two coins can share a ticker; counting by it
    handed the impostor and the real coin one merged total, which each then
    rendered as its own swap count and ranked on. Each returned row carries
    its ``pool_id`` for the same reason: it is what the caller prices against.

    Ranking sorts on ``(-swaps_24h, -swaps_all, -age_s)``: the 24h count is
    the primary signal, but a quiet 24h ties every coin at 0 exactly the way
    a quiet hour used to (1 swap across 146 coins, measured 2026-08-23), and
    without a second key the sort fell through straight to ``-age_s`` --
    surfacing the oldest never-traded coins, not the most active ones.
    ``swaps_all`` -- the cumulative count from the client's cursor, not
    windowed -- is the tiebreak: a coin that traded heavily once and has
    since gone quiet still outranks one that has never traded at all.

    ``swaps_all`` is ``{pool_id: cumulative count}`` from the client's
    cursor, not a list of raw swap rows like ``day_swaps`` -- it is already a
    per-coin total, so it is looked up directly rather than counted here.
    """
    day_counts: dict[str, int] = {}
    for swap in day_swaps:
        pool_id = swap.get("pool_id")
        if pool_id:
            day_counts[pool_id] = day_counts.get(pool_id, 0) + 1

    rows: list[dict[str, Any]] = []
    for launch in launches:
        pool_id = launch.get("pool_id")
        ticker = launch.get("ticker")
        ts = launch.get("ts")
        rows.append(
            {
                "pool_id": pool_id,
                "ticker": ticker,
                "name": launch.get("name"),
                "creator": launch.get("creator"),
                "creator_known": bool(launch.get("creator_known")),
                "age_s": (now_ts - ts) if isinstance(ts, (int, float)) else None,
                "price_eth": launch.get("price_eth"),
                # No swaps today is not a flat day: None, never 0.0.
                "change_24h_pct": launch.get("change_24h_pct"),
                "swaps_24h": day_counts.get(pool_id, 0),
                # A real, representable zero: the coin exists and has never
                # traded, which is a fact worth ranking on, not a failed read.
                "swaps_all": swaps_all.get(pool_id, 0),
                "imd_burned": launch.get("imd_burned"),
                # Carried, not used: `mcap_eth` needs it and the price it
                # multiplies is not read until the client's price round.
                "coin_supply_wei": launch.get("coin_supply_wei"),
            }
        )
    rows.sort(
        key=lambda r: (-r["swaps_24h"], -r["swaps_all"], -(r["age_s"] or 0.0))
    )
    return rows[:limit]
