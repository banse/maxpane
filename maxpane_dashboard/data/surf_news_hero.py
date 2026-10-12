"""Pure news-card projections of existing source snapshots; no reads or writes."""
from __future__ import annotations

import math

from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.data.series_points import coerce_points
from maxpane_dashboard.data.surf_v4 import price_eth_per_imd


# Only failures of a known detector's inputs can stale its summary. NFT counters,
# market prices and pool4, for example, cannot make a channel detector unhealthy.
_SIGNAL_SOURCES = {
    "post": ("chain", "channel"), "thread": ("channel",),
    "lp": ("chain", "logs"), "gate": ("chain", "logs"),
    "deploy": ("channel", "activity"), "bridge": ("logs",),
    "burn": ("chain", "activity"), "decoy": ("pad",),
    "burnready": ("pad",), "hot": ("pad",), "swarm": ("swarm",),
}


def _stamp(value: object, now: float) -> float | None:
    value = number(value)
    return float(value) if value is not None and 0 < value <= now else None


def source(read_ts: object, *, now: float, ttl: float, failed: bool = False) -> dict:
    stamp = _stamp(read_ts, now)
    return {"read_ts": stamp, "state": "unavailable" if stamp is None else
            "stale" if failed or now - stamp > ttl else "ok"}


def _metadata(sources: dict, name: str, now: float) -> dict:
    raw = sources.get(name)
    raw = raw if isinstance(raw, dict) else {}
    stamp = _stamp(raw.get("read_ts"), now)
    state = raw.get("state")
    return {"read_ts": stamp, "state": state if stamp is not None and
            state in ("ok", "stale") else "unavailable"}


def _post(items: object, kind: str, metadata: dict, now: float) -> dict:
    result = dict(metadata, text=None, age_s=None)
    if not isinstance(items, list) or metadata["state"] == "unavailable":
        return dict(result, state="unavailable")
    candidates = [(stamp, str(row.get("tx_hash") or ""), row["text"])
                  for row in items if isinstance(row, dict) and row.get("kind") == kind
                  and isinstance(row.get("text"), str) and row["text"].strip()
                  and (stamp := _stamp(row.get("ts"), now)) is not None]
    if candidates:
        stamp, _, text = max(candidates)
        result.update(text=text, age_s=now - stamp)
    return result


def _activity(raw: object, metadata: dict, now: float, wallet_count: int) -> dict:
    result = dict(metadata, rows=None, wallet_count=wallet_count)
    if not isinstance(raw, list) or metadata["state"] == "unavailable":
        return dict(result, state="unavailable")
    rows = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        stamp = _stamp(row.get("ts"), now)
        label, kind = row.get("wallet_label"), row.get("kind")
        if stamp is not None and label in ("dev", "ops") and isinstance(kind, str) and kind.strip():
            rows.append(dict(age_s=now - stamp, wallet_label=label, kind=kind))
    rows.sort(key=lambda row: row["age_s"])
    result["rows"] = rows[:3]
    return result


def project(*, data: dict, channel: object, activity: object, market: object,
            launchpad: object, boards: object, sources: dict, now: float,
            signal_read_ts: float | None, poll_interval: float, wallet_count: int) -> dict:
    """Use each captured value with its own source version and successful clock.

    `channel` is the full cached page, not the 25-row display feed. The price
    uses the same onchain-first selection as the native market panel; both
    inputs' clocks matter when converting its ETH price into USD.
    """
    channel, activity, market, launchpad, boards = (
        value if isinstance(value, dict) else {}
        for value in (channel, activity, market, launchpad, boards)
    )
    meta = {name: _metadata(sources, name, now) for name in
            ("channel", "activity", "market", "pad", "nft")}
    known = {name: data.get(f"sig_{name}_state") for name in SIGNAL_NAMES
             if data.get(f"sig_{name}_state") in ("ok", "watch", "fired")}
    signal_source = source(signal_read_ts, now=now, ttl=poll_interval)
    if not known:
        signal_source["state"] = "unavailable"
    elif signal_source["state"] == "ok" and any(
        _metadata(sources, dependency, now)["state"] != "ok"
        for name in known for dependency in _SIGNAL_SOURCES[name]
    ):
        signal_source["state"] = "stale"
    signals = dict(signal_source, fired=sum(state == "fired" for state in known.values()),
                   watch=sum(state == "watch" for state in known.values()),
                   quiet=sum(state == "ok" for state in known.values()), known=len(known), total=len(SIGNAL_NAMES))

    price_meta = dict(meta["market"])
    price = number(market.get("imd_price_usd"))
    sqrt_price, eth_usd = count(launchpad.get("sqrt_price_x96")), number(market.get("eth_usd"))
    # sqrtPriceX96 is uint160. Bound it before floating-point pool arithmetic.
    if sqrt_price is not None and 0 < sqrt_price < 2**160 and eth_usd is not None:
        chain_price = number(price_eth_per_imd(sqrt_price) * eth_usd)
        if chain_price is not None and meta["pad"]["state"] != "unavailable":
            price = chain_price
            stamps = [meta[name]["read_ts"] for name in ("market", "pad")]
            price_meta["read_ts"] = min(stamps) if all(stamp is not None for stamp in stamps) else None
            if meta["pad"]["state"] == "stale" and price_meta["state"] == "ok":
                price_meta["state"] = "stale"
    if price is None or price_meta["state"] == "unavailable":
        price, price_meta["state"] = None, "unavailable"
    change = market.get("imd_change_24h_pct")
    try:
        change = change if type(change) in (int, float) and math.isfinite(change) else None
    except OverflowError:
        change = None
    points, _ = coerce_points(data.get("price_series"), now=now)
    market_card = dict(price_meta, price_usd=price, change_24h_pct=change,
                       points=[point[1] for point in sorted(points)])
    nft = dict(meta["nft"], holders=count(boards.get("nft_holders")),
               written=count(boards.get("nft_written")), moves_24h=number(boards.get("nft_transfers_24h")))
    if nft["state"] == "unavailable" or all(nft[field] is None for field in ("holders", "written", "moves_24h")):
        nft.update(state="unavailable", holders=None, written=None, moves_24h=None)
    return {
        "announcement": _post(channel.get("items"), "self", meta["channel"], now),
        "reply": _post(channel.get("items"), "reply", meta["channel"], now),
        "signals": signals,
        "activity": _activity(activity.get("rows"), meta["activity"], now, wallet_count),
        "market": market_card,
        "boards": nft,
    }
