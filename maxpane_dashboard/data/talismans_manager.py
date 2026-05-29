"""Orchestrator for the Talismans NFT dashboard (WP3b).

Single coordination point between :class:`TalismansClient` (RPC fetch),
:class:`TalismansCache` (persistent state), and the signal analytics in
:mod:`maxpane_dashboard.analytics.talismans_signals`. Exposes one public
coroutine, ``fetch_and_compute()``, which returns the flat dict consumed by the
widget layer.

Cycle behaviour (each refresh):

1. Pull collection flags + block number in parallel.
2. Incremental operation-log scan (Bonded / Cleaved / Cut / Merged) since
   ``cache.last_seen_block["ops"]``; register output ids and apply each op.
3. Batch-read every known token's live state via Multicall3; rebuild the live
   token registry.
4. Compute the core-conservation baseline (once) and the live aggregates.
5. Sample hourly distribution buckets.
6. Run signal analytics and assemble the flat dict.
7. Persist the cache.

Mirrors the patterns in :mod:`maxpane_dashboard.data.ttt_manager`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.talismans_signals import (
    conservation_signal,
    count_operations,
    cutmerge_signal,
    essence_tier_matrix,
    forge_momentum_signal,
    materials_ledger,
    mythic_count,
    mythic_scarcity_pct,
    mythic_scarcity_signal,
    top_collectors,
    total_cores,
)
from maxpane_dashboard.data.talismans_cache import TalismansCache
from maxpane_dashboard.data.talismans_client import (
    _DEFAULT_LOG_LOOKBACK_BLOCKS,
    TalismansClient,
)
from maxpane_dashboard.data.talismans_materials import essence_of, tier_name
from maxpane_dashboard.data.talismans_models import TalismanActivityEvent, TalismanToken

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "talismans_cache.json"

_GENESIS_MAX_ID = 1536


def _safe_call(fn: Any, *args: Any, default: Any = None) -> Any:
    """Call *fn* with *args*, returning *default* on exception."""
    try:
        return fn(*args)
    except Exception as exc:
        logger.debug("Analytics call %s failed: %s", getattr(fn, "__name__", fn), exc)
        return default


def _block_timestamp(block_number: int, current_block: int, now_ts: float) -> int:
    """Approximate the unix timestamp of a block.

    No per-block RPC reads -- anchor on the current block at the current
    wall-clock time and extrapolate backwards at ~12 seconds per block (L1).
    """
    if current_block <= 0 or block_number <= 0:
        return int(now_ts)
    return max(0, int(now_ts) - (current_block - block_number) * 12)


class TalismansManager:
    """Pulls Talismans data, updates cache, computes analytics, returns flat dict."""

    def __init__(self, poll_interval: int = 30) -> None:
        self.client = TalismansClient()
        self.cache = TalismansCache()
        self.poll_interval = poll_interval
        self._cycle_count = 0
        self._error_count = 0
        self._last_fetch_ts: float = 0.0

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache.load_from_file(str(_CACHE_FILE))
        self.cache.seed_genesis_ids()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one full refresh cycle and return the flat dashboard dict."""
        now_ts = time.time()
        self._last_fetch_ts = now_ts

        # -- 1) Block number + collection flags in parallel --------------
        block_task = asyncio.create_task(self.client.fetch_block_number())
        flags_task = asyncio.create_task(self.client.fetch_collection_flags())
        try:
            current_block = await block_task
        except Exception as exc:
            logger.debug("block number fetch failed: %s", exc)
            current_block = 0
        try:
            flags = await flags_task
        except Exception as exc:
            self._error_count += 1
            logger.warning("collection flags fetch failed: %s", exc)
            flags = {
                "total_supply": len(self.cache.tokens),
                "genesis_minted": _GENESIS_MAX_ID,
                "bond_cleave_enabled": False,
                "cut_merge_enabled": False,
            }

        # -- 2) Incremental operation-log scan ---------------------------
        await self._scan_operations(current_block, now_ts)

        # -- 3) Live token state -----------------------------------------
        await self._refresh_token_states(current_block, now_ts)

        # -- 4) Aggregates + conservation baseline -----------------------
        live_token_list = list(self.cache.tokens.values())
        tcores = total_cores(live_token_list)
        live = flags["total_supply"]  # authoritative live count
        # Enumeration is complete when our per-token set matches the contract's
        # authoritative supply. Only lock in the conservation baseline (and only
        # assert the invariant) from a complete scan — a partial scan would
        # otherwise poison the baseline with a too-low total.
        enumeration_complete = live > 0 and len(live_token_list) == live
        if enumeration_complete:
            self.cache.set_invariant_baseline_if_unset(tcores)

        mcount = mythic_count(live_token_list)

        # -- 5) Sample hourly distribution -------------------------------
        self.cache.sample_distribution(now_ts, mcount, live)

        # -- 6) Analytics + assemble dict --------------------------------
        operations_24h = count_operations(
            list(self.cache.activity_log), now_ts=int(now_ts)
        )

        baseline = self.cache.cores_invariant_baseline
        conservation = _safe_call(
            conservation_signal, tcores, baseline, enumeration_complete
        )
        cutmerge = _safe_call(cutmerge_signal, flags["cut_merge_enabled"])
        forge = _safe_call(
            forge_momentum_signal,
            [(ts, v) for ts, v in self.cache.tokencount_hourly],
        )
        scarcity = _safe_call(mythic_scarcity_signal, mcount, live)

        def _dump(sig: Any) -> dict | None:
            if sig is None:
                return None
            try:
                return sig.model_dump()
            except Exception:
                return None

        result = {
            "live_tokens": flags["total_supply"],
            "genesis_minted": flags["genesis_minted"],
            "token_drift": flags["total_supply"] - flags["genesis_minted"],
            "mythic_count": mcount,
            "mythic_pct": _safe_call(
                mythic_scarcity_pct, mcount, flags["total_supply"], default=0.0
            ),
            "mythics_ever_forged": self.cache.mythics_ever_forged,
            "total_cores": tcores,
            "cores_invariant_intact": (
                enumeration_complete
                and baseline > 0
                and tcores == baseline
            ),
            "operations_24h": operations_24h,
            "operations_total": self.cache.operations_total,
            "top_collectors": _safe_call(
                top_collectors, live_token_list, 10, default=[]
            ),
            "mythic_history": [[ts, v] for ts, v in self.cache.mythic_hourly],
            "operations_history": [[ts, v] for ts, v in self.cache.ops_hourly],
            "conservation_signal": _dump(conservation),
            "cutmerge_signal": _dump(cutmerge),
            "forge_momentum_signal": _dump(forge),
            "mythic_scarcity_signal": _dump(scarcity),
            "activity_events": [
                e.model_dump() for e in self.cache.get_activity_for_display(25)
            ],
            "essence_tier_matrix": _safe_call(
                essence_tier_matrix, live_token_list,
                default={"rows": [], "totals": {}},
            ),
            "materials_ledger": _safe_call(
                materials_ledger, live_token_list, 32, default=[]
            ),
            "current_block": current_block,
            "last_updated_seconds_ago": 0,
            "error_count": self._error_count,
            "poll_interval": self.poll_interval,
            "active_view": "matrix",  # default; the screen owns view toggling (WP5)
            "bond_cleave_enabled": flags["bond_cleave_enabled"],
            "cut_merge_enabled": flags["cut_merge_enabled"],
        }

        self.save_cache()
        self._cycle_count += 1
        return result

    def save_cache(self) -> None:
        self.cache.save_to_file(str(_CACHE_FILE))

    async def close(self) -> None:
        self.save_cache()
        await self.client.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _scan_operations(self, current_block: int, now_ts: float) -> None:
        """Incrementally fetch + apply Bonded / Cleaved / Cut / Merged ops."""
        if current_block <= 0:
            return
        last = self.cache.last_seen_block.get("ops")
        if last:
            from_block = last + 1
        else:
            from_block = max(0, current_block - _DEFAULT_LOG_LOOKBACK_BLOCKS)
        from_block = max(0, from_block)

        try:
            ops = await self.client.fetch_operation_logs(from_block, current_block)
        except Exception as exc:
            self._error_count += 1
            logger.debug("operation log scan failed: %s", exc)
            return

        for op in ops:
            self.cache.register_result_ids(op)
            try:
                event = TalismanActivityEvent(
                    tx_hash=op.get("tx_hash", "0x"),
                    block_number=int(op.get("block_number", 0)),
                    timestamp=_block_timestamp(
                        int(op.get("block_number", 0)), current_block, now_ts
                    ),
                    op_type=op.get("op_type", ""),
                    token_id_a=op.get("token_id_a"),
                    token_id_b=op.get("token_id_b"),
                    result_id=op.get("result_id"),
                    operator=op.get("operator"),
                )
            except Exception as exc:
                logger.debug("could not build activity event: %s", exc)
                continue
            self.cache.apply_operation(event)

        self.cache.last_seen_block["ops"] = current_block

    async def _refresh_token_states(
        self, current_block: int, now_ts: float
    ) -> None:
        """Batch-read live state for every known id; rebuild the registry."""
        try:
            states = await self.client.fetch_token_states(
                sorted(self.cache.known_ids)
            )
        except Exception as exc:
            self._error_count += 1
            logger.debug("token-state fetch failed: %s", exc)
            return

        tokens: dict[int, TalismanToken] = {}
        for tid, st in states.items():
            material_id = int(st.get("material_id", 0))
            core_count = int(st.get("core_count", 0))
            owner = str(st.get("owner", "")).lower()
            try:
                tokens[int(tid)] = TalismanToken(
                    token_id=int(tid),
                    owner=owner,
                    core_count=core_count,
                    material_id=material_id,
                    essence=essence_of(material_id),
                    form=int(st.get("form", 0)),
                    seed=int(st.get("seed", 0)),
                    tier=tier_name(core_count),
                    is_genesis=int(tid) <= _GENESIS_MAX_ID,
                )
            except Exception as exc:
                logger.debug("could not build token %s: %s", tid, exc)
        self.cache.set_token_states(tokens)


__all__ = ["TalismansManager"]
