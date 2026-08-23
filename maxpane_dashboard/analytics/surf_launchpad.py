"""Launchpad ranking, thresholds and flow aggregates.

Pure functions.  No I/O, no Textual, and no direct wall-clock read of any
kind -- every entry point takes ``now_ts`` instead.

The HOT COIN threshold is **relative to the hour's own distribution**.  At
~1,170 swaps/day across ~146 coins a fixed "any swap" threshold lights the row
permanently, which is the trap ``signals.py`` documents for ``‹ widen``: a
marker that is always on means nothing.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

#: A coin is hot at this multiple of the hour's median swap count...
HOT_MULTIPLE = 3
#: ...but never below this floor, so a quiet hour (median 1) cannot promote a
#: coin on 3 swaps.
HOT_FLOOR = 5
#: Below this many active coins there is no meaningful median at all.
HOT_MIN_ACTIVE = 5


def hot_coin_threshold(swaps_by_coin: Mapping[str, int]) -> int | None:
    """Swap count a coin must reach this hour to be HOT, or ``None``.

    ``None`` means "the hour is too thin to judge" and must render OK, not a
    fire: an empty hour is not evidence of a hot coin.
    """
    active = [n for n in swaps_by_coin.values() if n > 0]
    if len(active) < HOT_MIN_ACTIVE:
        return None
    return max(HOT_FLOOR, int(statistics.median(active)) * HOT_MULTIPLE)


def curve_flow(swaps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate swap rows into the CURVE FLOW panel's numbers."""
    buys = sum(1 for s in swaps if s.get("is_buy"))
    total = len(swaps)
    traders = {s.get("trader") for s in swaps if s.get("trader")}
    return {
        "swap_count": total,
        "trader_count": len(traders),
        "buy_pct": (100.0 * buys / total) if total else None,
        "sell_pct": (100.0 * (total - buys) / total) if total else None,
    }


def rank_coins(
    launches: Sequence[Mapping[str, Any]],
    swaps: Sequence[Mapping[str, Any]],
    now_ts: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Rank launched coins by recent swap count, most active first.

    Ranking happens **from logs alone** -- no per-coin RPC call.  One
    ``getLogs`` over ``CurveSwap`` yields counts for every coin, so cost is
    flat whether the launchpad holds 146 coins or 1,460.  Curve state is read
    only for the rows this function returns.

    ``ticker`` and ``name`` are carried through raw: they are attacker-chosen
    and are escaped at render, not here.
    """
    counts: dict[str, int] = {}
    for swap in swaps:
        coin = swap.get("coin")
        if coin:
            counts[coin] = counts.get(coin, 0) + 1

    rows: list[dict[str, Any]] = []
    for launch in launches:
        ticker = launch.get("ticker")
        ts = launch.get("ts")
        rows.append(
            {
                "ticker": ticker,
                "name": launch.get("name"),
                "creator": launch.get("creator"),
                "creator_known": bool(launch.get("creator_known")),
                "age_s": (now_ts - ts) if isinstance(ts, (int, float)) else None,
                "price_eth": launch.get("price_eth"),
                # No swaps this hour is not a flat hour: None, never 0.0.
                "change_1h_pct": launch.get("change_1h_pct"),
                "swaps_1h": counts.get(ticker, 0),
                "imd_burned": launch.get("imd_burned"),
            }
        )
    rows.sort(key=lambda r: (-r["swaps_1h"], -(r["age_s"] or 0.0)))
    return rows[:limit]
