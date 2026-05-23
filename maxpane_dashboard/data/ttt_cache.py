"""Persistent state for the Ten Thousand Tokens (TTT) dashboard.

Tracks:

* The 10,000 per-NFT ERC20 token contracts (address + metadata).
* A 24h-window fee history per token (FeeSplitter.Deposited holderShare).
* Hourly burn-count + floor-price buckets, 168 hours (7 days) deep, for the
  sparkline widget.
* A ring buffer of the most recent 200 activity events for the activity feed.
* Per-event-type incremental scan watermarks (last seen block per topic).
* Rolling 24h counters for launches and ETH-to-holders flow.

Persistence: serialised to ``~/.maxpane/ttt_cache.json`` (fail-soft on missing
/ corrupt file). Follows the patterns in :mod:`maxpane_dashboard.data.ocm_cache`
for save/load and in :mod:`maxpane_dashboard.data.base_cache` for hourly bucket
aggregation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque

from maxpane_dashboard.data.ttt_models import (
    TTTActivityEvent,
    TTTLaunchedToken,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache sizing
# ---------------------------------------------------------------------------

_HOURLY_HISTORY_HOURS = 168          # 7 days
_ACTIVITY_RING_BUFFER = 200
_FEE_BUCKET_RETENTION_SEC = 25 * 3600  # keep 24h+1h of fee history
_HOURLY_RETENTION_SEC = (_HOURLY_HISTORY_HOURS + 1) * 3600

_WEI = 10**18


def _hour_bucket(ts: float) -> float:
    """Floor a timestamp to the start of its hour."""
    return float(int(ts // 3600) * 3600)


class TTTCache:
    """In-memory state for one TTT dashboard process.

    All collections are designed for single-threaded asyncio access -- no
    locking. Mutations are intentionally cheap so the refresh cycle can
    iterate hundreds of events without overhead.
    """

    def __init__(self) -> None:
        # Discovered per-NFT ERC20 tokens. Keyed by lower-case address.
        self.tokens: dict[str, TTTLaunchedToken] = {}

        # Per-token fee buckets: list of (ts_hour, holder_share_wei).
        # Aggregated by hour so 24h windows are cheap to compute.
        self.fees_by_token: dict[str, list[list[float]]] = {}

        # Sparkline buckets, 7d deep.
        self.burns_hourly: deque[tuple[float, int]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )
        self.floor_hourly: deque[tuple[float, float]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )
        # Total volume across all tokens (USD), hourly bucketed, 7d deep.
        self.volume_hourly: deque[tuple[float, float]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )

        # Activity ring buffer, newest events first.
        self.activity_log: deque[TTTActivityEvent] = deque(
            maxlen=_ACTIVITY_RING_BUFFER
        )

        # Incremental scan watermarks, keyed by event topic name.
        self.last_seen_block: dict[str, int] = {}

        # Rolling 24h counters (recomputed each cycle from buckets, but kept
        # here so the manager doesn't have to scan every time).
        self.launches_24h: int = 0
        self.eth_to_holders_24h_wei: int = 0

    # ------------------------------------------------------------------
    # Token registry
    # ------------------------------------------------------------------

    def register_token(
        self,
        *,
        token_id: int,
        address: str,
        deployer: str,
        launch_block: int,
        symbol: str | None = None,
        decimals: int = 18,
    ) -> None:
        """Add a token to the registry if not already present.

        Existing entries are preserved -- use :meth:`update_token_metadata`
        to fill in symbol/decimals later.
        """
        addr = address.lower()
        if addr in self.tokens:
            return
        self.tokens[addr] = TTTLaunchedToken(
            token_id=token_id,
            address=addr,
            deployer=deployer.lower(),
            launch_block=launch_block,
            symbol=symbol,
            decimals=decimals,
        )

    def update_token_metadata(
        self, address: str, symbol: str, decimals: int
    ) -> None:
        """Patch a token's symbol/decimals (immutable models -> model_copy)."""
        addr = address.lower()
        existing = self.tokens.get(addr)
        if existing is None:
            return
        self.tokens[addr] = existing.model_copy(
            update={"symbol": symbol, "decimals": decimals}
        )

    def update_token_market(
        self,
        address: str,
        *,
        price_usd: float | None,
        change_h24: float | None,
        volume_h24: float | None,
        mcap: float | None,
    ) -> None:
        """Patch a token's market data fields (price, change, volume, mcap)."""
        addr = address.lower()
        existing = self.tokens.get(addr)
        if existing is None:
            return
        self.tokens[addr] = existing.model_copy(
            update={
                "price_usd": price_usd,
                "price_change_h24": change_h24,
                "volume_usd_h24": volume_h24,
                "market_cap_usd": mcap,
            }
        )

    def update_token_reservoir(self, address: str, reservoir_wei: int) -> None:
        addr = address.lower()
        existing = self.tokens.get(addr)
        if existing is None:
            return
        self.tokens[addr] = existing.model_copy(
            update={"reservoir_wei": int(reservoir_wei)}
        )

    def update_token_fees(
        self, address: str, fees_24h_eth: float, fees_lifetime_eth: float
    ) -> None:
        addr = address.lower()
        existing = self.tokens.get(addr)
        if existing is None:
            return
        self.tokens[addr] = existing.model_copy(
            update={
                "fees_eth_24h": fees_24h_eth,
                "fees_eth_lifetime": fees_lifetime_eth,
            }
        )

    # ------------------------------------------------------------------
    # Activity log + per-event-type applicators
    # ------------------------------------------------------------------

    def apply_launch(
        self,
        *,
        token_id: int,
        address: str,
        launcher: str,
        block_number: int,
        timestamp: int,
        tx_hash: str,
        symbol: str | None = None,
    ) -> None:
        """Record a burn-and-launch event (factory.Launched).

        Registers the token (no-op if already known) and appends a ``burn``
        activity event for the feed.
        """
        self.register_token(
            token_id=token_id,
            address=address,
            deployer=launcher,
            launch_block=block_number,
            symbol=symbol,
        )
        self.activity_log.appendleft(
            TTTActivityEvent(
                tx_hash=tx_hash,
                block_number=block_number,
                timestamp=timestamp,
                event_type="burn",
                token_symbol=symbol,
                token_address=address.lower(),
                actor_address=launcher.lower(),
                eth_amount_wei=0,
                token_id=token_id,
                extra=None,
            )
        )

    def apply_deposit(
        self,
        *,
        token: str,
        sender: str,
        holder_share_wei: int,
        total_wei: int,
        block_number: int,
        timestamp: int,
        tx_hash: str,
    ) -> None:
        """Bucket a FeeSplitter.Deposited event into per-token hourly fees.

        The 30%-bucket is taken DIRECTLY from ``holder_share_wei`` -- no
        recomputation; the event already emits pre-split shares inline.
        """
        addr = token.lower()
        bucket = _hour_bucket(timestamp)
        token_buckets = self.fees_by_token.setdefault(addr, [])
        # Aggregate by hour: if last bucket is the same hour, add to it
        if token_buckets and token_buckets[-1][0] == bucket:
            token_buckets[-1][1] += int(holder_share_wei)
        else:
            token_buckets.append([bucket, int(holder_share_wei)])

        sym = (self.tokens.get(addr) or TTTLaunchedToken(
            token_id=0, address=addr, deployer="0x" + "0" * 40,
            launch_block=0, symbol=None, decimals=18,
        )).symbol

        self.activity_log.appendleft(
            TTTActivityEvent(
                tx_hash=tx_hash,
                block_number=block_number,
                timestamp=timestamp,
                event_type="fee",
                token_symbol=sym,
                token_address=addr,
                actor_address=sender.lower(),
                eth_amount_wei=int(total_wei),
                token_id=(self.tokens.get(addr).token_id if addr in self.tokens else None),
                extra={"holder_share_wei": int(holder_share_wei)},
            )
        )

    def apply_buyback(
        self,
        *,
        token: str,
        caller: str,
        eth_spent_wei: int,
        caller_reward_wei: int,
        block_number: int,
        timestamp: int,
        tx_hash: str,
    ) -> None:
        """Append a TTT.Bought event to the activity feed."""
        addr = token.lower()
        sym = self.tokens.get(addr).symbol if addr in self.tokens else None
        tid = self.tokens.get(addr).token_id if addr in self.tokens else None
        self.activity_log.appendleft(
            TTTActivityEvent(
                tx_hash=tx_hash,
                block_number=block_number,
                timestamp=timestamp,
                event_type="buyback",
                token_symbol=sym,
                token_address=addr,
                actor_address=caller.lower(),
                eth_amount_wei=int(eth_spent_wei),
                token_id=tid,
                extra={"bounty_wei": int(caller_reward_wei)},
            )
        )

    def sample_burns_and_floor(
        self, now_ts: float, cum_burns: int, floor_eth: float | None
    ) -> None:
        """Append the current burn count + floor to the hourly deques.

        Dedupes by bucket: if the most-recent bucket is already at the
        current hour, we overwrite it instead of appending a duplicate.
        """
        bucket = _hour_bucket(now_ts)
        # Burns
        if self.burns_hourly and self.burns_hourly[-1][0] == bucket:
            self.burns_hourly[-1] = (bucket, int(cum_burns))
        else:
            self.burns_hourly.append((bucket, int(cum_burns)))
        # Floor (only if we got one)
        if floor_eth is not None and floor_eth > 0:
            if self.floor_hourly and self.floor_hourly[-1][0] == bucket:
                self.floor_hourly[-1] = (bucket, float(floor_eth))
            else:
                self.floor_hourly.append((bucket, float(floor_eth)))

    def sample_volume(self, now_ts: float, total_volume_usd: float) -> None:
        """Append the current total volume (USD) to the hourly deque.

        Mirrors the ``sample_burns_and_floor`` dedupe pattern: if the most-
        recent bucket is already at the current hour, overwrite it instead
        of appending a duplicate.
        """
        bucket = _hour_bucket(now_ts)
        try:
            val = float(total_volume_usd)
        except (TypeError, ValueError):
            return
        if self.volume_hourly and self.volume_hourly[-1][0] == bucket:
            self.volume_hourly[-1] = (bucket, val)
        else:
            self.volume_hourly.append((bucket, val))

    # ------------------------------------------------------------------
    # Activity log read helpers
    # ------------------------------------------------------------------

    def get_activity_for_display(
        self, limit: int = 25
    ) -> list[TTTActivityEvent]:
        """Return the most recent ``limit`` activity events sorted by block desc.

        Multi-day event scans land in the activity_log in scan order, not
        chronological order. We sort by ``block_number`` descending at read
        time so the display always shows the freshest blocks first. The
        ``activity_log`` insertion path is intentionally left alone.

        Ties on block_number (multiple events in the same block) are broken
        by ``timestamp`` desc as a stable secondary key.
        """
        events = list(self.activity_log)
        events.sort(
            key=lambda e: (int(e.block_number or 0), int(e.timestamp or 0)),
            reverse=True,
        )
        if limit is None or limit < 0:
            return events
        return events[:limit]

    # ------------------------------------------------------------------
    # Pruning and aggregation
    # ------------------------------------------------------------------

    def prune_old(self, now_ts: float) -> None:
        """Drop fee buckets older than 24h+1h."""
        cutoff = now_ts - _FEE_BUCKET_RETENTION_SEC
        for addr, buckets in list(self.fees_by_token.items()):
            kept = [b for b in buckets if b[0] >= cutoff]
            if kept:
                self.fees_by_token[addr] = kept
            else:
                # Don't drop the token entry itself -- just clear its buckets
                self.fees_by_token[addr] = []

    def recompute_rolling_counters(self, now_ts: float) -> None:
        """Recompute ``launches_24h`` and ``eth_to_holders_24h_wei`` from the buffers.

        Counts ``burn`` activity events in the last 24h, and sums every
        token's holder-share fee buckets in the same window.
        """
        cutoff = now_ts - 86400
        self.launches_24h = sum(
            1
            for e in self.activity_log
            if e.event_type == "burn" and e.timestamp >= cutoff
        )
        total = 0
        for buckets in self.fees_by_token.values():
            for ts_hour, wei in buckets:
                if ts_hour >= cutoff:
                    total += int(wei)
        self.eth_to_holders_24h_wei = total

    def per_token_fees(self, address: str, now_ts: float) -> tuple[float, float]:
        """Return ``(fees_eth_24h, fees_eth_lifetime)`` for one token.

        ``lifetime`` here is "everything we've seen since the cache started" --
        the absolute lifetime requires a one-time chain scan from genesis,
        which we do NOT do per cycle.
        """
        buckets = self.fees_by_token.get(address.lower(), [])
        if not buckets:
            return (0.0, 0.0)
        cutoff = now_ts - 86400
        sum_24h = sum(int(w) for (ts, w) in buckets if ts >= cutoff)
        sum_total = sum(int(w) for (_, w) in buckets)
        return (sum_24h / _WEI, sum_total / _WEI)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist cache to disk via atomic temp-then-rename."""
        payload = {
            "saved_at": time.time(),
            "tokens": {addr: t.model_dump() for addr, t in self.tokens.items()},
            "fees_by_token": {
                addr: [[float(ts), int(w)] for (ts, w) in buckets]
                for addr, buckets in self.fees_by_token.items()
            },
            "burns_hourly": [[float(ts), int(v)] for (ts, v) in self.burns_hourly],
            "floor_hourly": [[float(ts), float(v)] for (ts, v) in self.floor_hourly],
            "volume_hourly": [[float(ts), float(v)] for (ts, v) in self.volume_hourly],
            "activity_log": [e.model_dump() for e in self.activity_log],
            "last_seen_block": dict(self.last_seen_block),
            "launches_24h": int(self.launches_24h),
            "eth_to_holders_24h_wei": int(self.eth_to_holders_24h_wei),
        }
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, path)
            logger.info(
                "TTT cache saved to %s (%d tokens, %d activity)",
                path,
                len(self.tokens),
                len(self.activity_log),
            )
        except OSError as exc:
            logger.warning("Failed to save TTT cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load_from_file(self, path: str) -> None:
        """Load saved state from disk. Silent no-op on missing / corrupt file."""
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No TTT cache to load (%s): %s", path, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("TTT cache %s has unexpected shape, skipping", path)
            return

        # Tokens
        try:
            for addr, data in (payload.get("tokens") or {}).items():
                try:
                    self.tokens[addr.lower()] = TTTLaunchedToken.model_validate(data)
                except Exception as exc:
                    logger.debug("Skipping bad token %s: %s", addr, exc)
        except Exception as exc:
            logger.warning("tokens block bad: %s", exc)

        # Fees
        try:
            self.fees_by_token = {}
            for addr, buckets in (payload.get("fees_by_token") or {}).items():
                self.fees_by_token[addr.lower()] = [
                    [float(b[0]), int(b[1])]
                    for b in buckets
                    if isinstance(b, (list, tuple)) and len(b) >= 2
                ]
        except Exception as exc:
            logger.warning("fees_by_token block bad: %s", exc)

        # Hourly
        try:
            self.burns_hourly.clear()
            for pt in payload.get("burns_hourly") or []:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    self.burns_hourly.append((float(pt[0]), int(pt[1])))
            self.floor_hourly.clear()
            for pt in payload.get("floor_hourly") or []:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    self.floor_hourly.append((float(pt[0]), float(pt[1])))
            self.volume_hourly.clear()
            for pt in payload.get("volume_hourly") or []:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        self.volume_hourly.append((float(pt[0]), float(pt[1])))
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:
            logger.warning("hourly history bad: %s", exc)

        # Activity
        try:
            self.activity_log.clear()
            for evt in payload.get("activity_log") or []:
                try:
                    self.activity_log.append(TTTActivityEvent.model_validate(evt))
                except Exception as exc:
                    logger.debug("Skipping bad activity event: %s", exc)
        except Exception as exc:
            logger.warning("activity_log block bad: %s", exc)

        # Watermarks + counters
        try:
            for k, v in (payload.get("last_seen_block") or {}).items():
                self.last_seen_block[str(k)] = int(v)
        except Exception:
            pass
        self.launches_24h = int(payload.get("launches_24h") or 0)
        self.eth_to_holders_24h_wei = int(payload.get("eth_to_holders_24h_wei") or 0)

        logger.info(
            "Loaded TTT cache from %s: %d tokens, %d activity, %d hourly points",
            path,
            len(self.tokens),
            len(self.activity_log),
            len(self.burns_hourly),
        )


__all__ = ["TTTCache"]
