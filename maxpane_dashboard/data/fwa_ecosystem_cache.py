"""Persistence and refresh clocks for the FWA NETWORK dashboard.

The cache is deliberately smaller than the existing PULLS cache.  It owns four
refresh clocks, independently dated last-good presentation fragments, one
complete NETWORK presentation snapshot, and log scan watermarks.  It performs
no network I/O and accepts an injected clock.

Two boundaries are structural:

* :meth:`FWAEcosystemCache.commit_snapshot` accepts exactly the frozen 40-key
  NETWORK contract.  A partial manager result can therefore never replace the
  visible snapshot.
* :meth:`FWAEcosystemCache.set_watermark` requires an explicit successful-page
  flag.  Failed or partial pages cannot move a log cursor past unread blocks.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from maxpane_dashboard.data.fwa_ecosystem_models import (
    DropRow,
    FlowRow,
    FWA_NETWORK_DATA_KEYS,
    NetworkEventRow,
    ProjectRow,
)
from maxpane_dashboard.data.series_points import CLOCK_SKEW_TOLERANCE_SECONDS

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(Path.home() / ".maxpane" / "fwa_ecosystem_cache.json")

# A version mismatch is intentionally all-or-nothing.  NETWORK has no older
# persisted format that this implementation can interpret safely.
CACHE_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Refresh tiers -- implementation plan section 7
# ---------------------------------------------------------------------------

TIER_FAST = "fast"
TIER_MEDIUM = "medium"
TIER_API = "api"
TIER_INTEGRITY = "integrity"

TIERS: tuple[str, ...] = (
    TIER_FAST,
    TIER_MEDIUM,
    TIER_API,
    TIER_INTEGRITY,
)

TIER_TTL_SECONDS: dict[str, float] = {
    TIER_FAST: 30.0,
    TIER_MEDIUM: 60.0,
    TIER_API: 120.0,
    TIER_INTEGRITY: 600.0,
}

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 30.0,
    TIER_API: 60.0,
    TIER_INTEGRITY: 120.0,
}


# ---------------------------------------------------------------------------
# Independently failing source groups
# ---------------------------------------------------------------------------

GROUP_CORE = "core"
GROUP_FLOW_LOGS = "flow_logs"
GROUP_DROPS = "drops"
GROUP_PULLPOOL = "pullpool"
GROUP_MEGARIP = "megarip"
GROUP_FWAP = "fwap"
GROUP_PROJECT_LOGS = "project_logs"
GROUP_INTEGRITY = "integrity"
GROUP_MARKET = "market"

GROUPS: tuple[str, ...] = (
    GROUP_CORE,
    GROUP_FLOW_LOGS,
    GROUP_DROPS,
    GROUP_PULLPOOL,
    GROUP_MEGARIP,
    GROUP_FWAP,
    GROUP_PROJECT_LOGS,
    GROUP_INTEGRITY,
    GROUP_MARKET,
)


# Stable ids from the presentation contract.  The cache validates rather than
# invents them while restoring an on-disk snapshot.
DEGRADED_SOURCE_IDS: tuple[str, ...] = GROUPS


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LastGood:
    """One successful source-group fragment with its original provenance."""

    payload: dict[str, Any]
    ts: float
    block_number: int | None = None
    source_fingerprint: str | None = None

    def age_seconds(self, now: float) -> float:
        return max(0.0, float(now) - self.ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": copy.deepcopy(self.payload),
            "ts": self.ts,
            "block_number": self.block_number,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    """One validated, complete NETWORK payload committed in one assignment."""

    payload: dict[str, Any]
    ts: float

    def age_seconds(self, now: float) -> float:
        return max(0.0, float(now) - self.ts)

    def to_dict(self) -> dict[str, Any]:
        return {"payload": copy.deepcopy(self.payload), "ts": self.ts}


_NAMESPACE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_BLOCK_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
MAX_REORG_OVERLAP = 5_000


@dataclass(frozen=True, slots=True, order=True)
class WatermarkKey:
    """Collision-free identity for one adapter/version/topic log stream."""

    adapter: str
    version: str
    topic_group: str

    def __post_init__(self) -> None:
        for label, value in (
            ("adapter", self.adapter),
            ("version", self.version),
            ("topic_group", self.topic_group),
        ):
            if not isinstance(value, str) or not _NAMESPACE_PART.fullmatch(value):
                raise ValueError(f"invalid watermark {label} {value!r}")


@dataclass(frozen=True, slots=True)
class Watermark:
    """Last fully scanned block for one namespaced log stream."""

    block_number: int
    block_hash: str
    overlap: int
    updated_at: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.block_number, bool)
            or not isinstance(self.block_number, int)
            or self.block_number < 0
        ):
            raise ValueError("watermark block_number must be a non-negative int")
        if not _BLOCK_HASH.fullmatch(self.block_hash):
            raise ValueError("watermark block_hash must be a 32-byte hex hash")
        if (
            isinstance(self.overlap, bool)
            or not isinstance(self.overlap, int)
            or self.overlap < 1
            or self.overlap > MAX_REORG_OVERLAP
        ):
            raise ValueError(
                f"watermark overlap must be in 1..{MAX_REORG_OVERLAP}"
            )
        if not _usable_timestamp(self.updated_at):
            raise ValueError("watermark updated_at must be a finite timestamp")

    def to_dict(self, key: WatermarkKey) -> dict[str, Any]:
        return {
            "adapter": key.adapter,
            "version": key.version,
            "topic_group": key.topic_group,
            "block_number": self.block_number,
            "block_hash": self.block_hash,
            "overlap": self.overlap,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Frozen presentation validation
# ---------------------------------------------------------------------------

_ROW_MODELS: dict[str, type[BaseModel]] = {
    "network_flow_rows": FlowRow,
    "network_drop_rows": DropRow,
    "network_project_rows": ProjectRow,
    "network_events": NetworkEventRow,
}

_BOOL_KEYS = {
    "network_ready",
    "network_state_stale",
    "network_flow_available",
    "network_flow_history_complete",
    "network_flow_stale",
    "network_drops_available",
    "network_drops_stale",
    "network_projects_available",
    "network_projects_stale",
    "network_feed_available",
}

_INT_KEYS = {
    "network_state_block",
    "network_chain_head",
    "network_active_listings",
    "network_pending_count",
    "network_unsettled_count",
    "network_drop_count",
    "network_project_family_count",
    "network_project_healthy_count",
    "network_project_degraded_count",
    "network_project_unverified_count",
    "network_flow_as_of_block",
    "network_drops_as_of_block",
    "network_projects_as_of_block",
    "network_integrity_warning_count",
    "network_error_count",
}

_FLOAT_KEYS = {
    "network_pull_quote_eth",
    "network_crown_pot_eth",
    "network_token_supply_fwa",
    "network_burned_since_genesis_fwa",
    "network_burned_since_genesis_pct",
    "network_last_buyback_age_s",
    "network_flow_as_of_ts",
    "network_feed_as_of_ts",
    "network_last_updated_seconds_ago",
}

_STRING_KEYS = {"network_feed_unavailable_reason"}


def _usable_timestamp(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _validate_timestamp(value: Any, *, now: float, label: str) -> float:
    if not _usable_timestamp(value):
        raise ValueError(f"{label} must be a finite timestamp")
    ts = float(value)
    if ts > now + CLOCK_SKEW_TOLERANCE_SECONDS:
        raise ValueError(f"{label} is implausibly future-dated")
    return ts


def _non_negative_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative int or None")
    return value


def _non_negative_float(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, float):
        raise ValueError(f"{key} must be a float or None")
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{key} must be finite and non-negative")
    return value


def _validate_fragment(payload: Any, *, exact: bool) -> dict[str, Any]:
    """Validate and detach one presentation fragment or complete snapshot."""

    if not isinstance(payload, Mapping):
        raise ValueError("NETWORK cache payload must be a mapping")
    keys = tuple(payload)
    allowed = set(FWA_NETWORK_DATA_KEYS)
    unknown = set(keys) - allowed
    if unknown:
        labels = sorted(repr(key) for key in unknown)
        raise ValueError(f"unknown NETWORK cache keys: {labels!r}")
    if exact and set(keys) != allowed:
        missing = [key for key in FWA_NETWORK_DATA_KEYS if key not in payload]
        extra = [key for key in keys if key not in allowed]
        raise ValueError(
            f"complete NETWORK snapshot has wrong keys; missing={missing!r}, "
            f"extra={extra!r}"
        )

    canonical: dict[str, Any] = {}
    for key in FWA_NETWORK_DATA_KEYS if exact else keys:
        value = payload[key]
        if key in _ROW_MODELS:
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{key} must be a row list")
            rows: list[dict[str, Any]] = []
            for index, row in enumerate(value):
                try:
                    model = _ROW_MODELS[key].model_validate(row)
                except (ValidationError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid {key}[{index}]: {exc}") from exc
                rows.append(model.model_dump())
            canonical[key] = rows
        elif key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a bool")
            canonical[key] = value
        elif key in _INT_KEYS:
            canonical[key] = _non_negative_int(value, key)
        elif key in _FLOAT_KEYS:
            canonical[key] = _non_negative_float(value, key)
        elif key in _STRING_KEYS:
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be a string or None")
            canonical[key] = value
        elif key == "network_degraded_sources":
            if not isinstance(value, list) or not all(
                isinstance(source, str) for source in value
            ):
                raise ValueError("network_degraded_sources must be a string list")
            if value != sorted(set(value)):
                raise ValueError("network_degraded_sources must be sorted and unique")
            unknown_sources = set(value) - set(DEGRADED_SOURCE_IDS)
            if unknown_sources:
                raise ValueError(
                    f"unknown degraded source ids: {sorted(unknown_sources)!r}"
                )
            canonical[key] = list(value)
        else:  # pragma: no cover - contract test catches a newly unhandled key
            raise ValueError(f"no cache validator for NETWORK key {key!r}")

    if exact and canonical["network_ready"] is not True:
        raise ValueError("a committed NETWORK snapshot must set network_ready=True")
    return canonical


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class FWAEcosystemCache:
    """Tier clocks and schema-versioned NETWORK persistence.

    Access is single-threaded asyncio-style, matching the dashboard managers.
    Returned payloads are copies so callers cannot mutate a committed snapshot
    in place and bypass the exact-contract validator.
    """

    def __init__(
        self,
        path: str = DEFAULT_CACHE_PATH,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = str(path)
        self._clock = clock
        self._tier_last_fetch: dict[str, float] = {}
        self._tier_next_due: dict[str, float] = {}
        self._last_good: dict[str, LastGood] = {}
        self._snapshot: NetworkSnapshot | None = None
        self._watermarks: dict[WatermarkKey, Watermark] = {}
        # A hash mismatch forces this start until a complete replacement page
        # commits.  Persisting the marker prevents a restart reopening the gap.
        self._reorg_starts: dict[WatermarkKey, int] = {}

    def _now(self, now: float | None = None) -> float:
        value = self._clock() if now is None else now
        if not _usable_timestamp(value):
            raise ValueError("cache clock must return a finite timestamp")
        return float(value)

    # -- tiers ---------------------------------------------------------------

    @staticmethod
    def _check_tier(tier: str) -> str:
        if tier not in TIER_TTL_SECONDS:
            raise ValueError(f"unknown NETWORK refresh tier {tier!r}")
        return tier

    def is_fresh(self, tier: str, now: float | None = None) -> bool:
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        return due_at is not None and self._now(now) < due_at

    def is_due(self, tier: str, now: float | None = None) -> bool:
        return not self.is_fresh(tier, now)

    def tiers_due(self, now: float | None = None) -> tuple[str, ...]:
        ts = self._now(now)
        return tuple(tier for tier in TIERS if not self.is_fresh(tier, ts))

    def mark_fetched(self, tier: str, now: float | None = None) -> None:
        self._check_tier(tier)
        ts = self._now(now)
        self._tier_last_fetch[tier] = ts
        self._tier_next_due[tier] = ts + TIER_TTL_SECONDS[tier]

    def mark_failed(
        self,
        tier: str,
        now: float | None = None,
        retry_after: float | None = None,
    ) -> None:
        self._check_tier(tier)
        backoff = (
            TIER_FAILURE_BACKOFF_SECONDS[tier]
            if retry_after is None
            else float(retry_after)
        )
        if not math.isfinite(backoff) or backoff < 0.0:
            raise ValueError("retry_after must be finite and non-negative")
        self._tier_next_due[tier] = self._now(now) + backoff

    def seconds_until_due(self, tier: str, now: float | None = None) -> float:
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return 0.0
        return max(0.0, due_at - self._now(now))

    def last_fetch_ts(self, tier: str) -> float | None:
        self._check_tier(tier)
        return self._tier_last_fetch.get(tier)

    # -- independently dated last-good groups -------------------------------

    @staticmethod
    def _check_group(group: str) -> str:
        if group not in GROUPS:
            raise ValueError(f"unknown NETWORK source group {group!r}")
        return group

    def store_last_good(
        self,
        group: str,
        payload: Mapping[str, Any] | None,
        *,
        ts: float | None = None,
        block_number: int | None = None,
        source_fingerprint: str | None = None,
    ) -> LastGood:
        """Store a successful group fragment without losing its source time.

        ``None`` is an outage and is refused.  Empty row lists and numeric zero
        remain valid facts; the fragment validator preserves that distinction.
        """

        self._check_group(group)
        if payload is None:
            raise ValueError("an unavailable read cannot replace last-good data")
        block = _non_negative_int(block_number, "block_number")
        if source_fingerprint is not None:
            if not isinstance(source_fingerprint, str) or not _BLOCK_HASH.fullmatch(
                source_fingerprint
            ):
                raise ValueError("source_fingerprint must be a 32-byte hex hash")
            source_fingerprint = source_fingerprint.lower()
        canonical = _validate_fragment(payload, exact=False)
        entry = LastGood(
            payload=canonical,
            ts=self._now(ts),
            block_number=block,
            source_fingerprint=source_fingerprint,
        )
        self._last_good[group] = entry
        return self._copy_last_good(entry)

    @staticmethod
    def _copy_last_good(entry: LastGood) -> LastGood:
        return replace(entry, payload=copy.deepcopy(entry.payload))

    def get_last_good(self, group: str) -> LastGood | None:
        self._check_group(group)
        entry = self._last_good.get(group)
        return None if entry is None else self._copy_last_good(entry)

    def age_of(self, group: str, now: float | None = None) -> float | None:
        entry = self.get_last_good(group)
        return None if entry is None else entry.age_seconds(self._now(now))

    # -- complete visible snapshot ------------------------------------------

    def commit_snapshot(
        self,
        payload: Mapping[str, Any],
        *,
        ts: float | None = None,
    ) -> NetworkSnapshot:
        """Atomically replace the in-memory snapshot after complete validation."""

        canonical = _validate_fragment(payload, exact=True)
        candidate = NetworkSnapshot(payload=canonical, ts=self._now(ts))
        self._snapshot = candidate
        return self._copy_snapshot(candidate)

    @staticmethod
    def _copy_snapshot(snapshot: NetworkSnapshot) -> NetworkSnapshot:
        return replace(snapshot, payload=copy.deepcopy(snapshot.payload))

    def latest_snapshot(self) -> NetworkSnapshot | None:
        snapshot = self._snapshot
        return None if snapshot is None else self._copy_snapshot(snapshot)

    # -- namespaced log watermarks ------------------------------------------

    def get_watermark(self, key: WatermarkKey) -> Watermark | None:
        return self._watermarks.get(key)

    def set_watermark(
        self,
        key: WatermarkKey,
        *,
        block_number: int,
        block_hash: str,
        overlap: int,
        page_complete: bool,
        ts: float | None = None,
    ) -> Watermark | None:
        """Advance ``key`` only after a fully successful log page.

        A caller must pass ``page_complete`` explicitly.  ``False`` is a
        no-op that returns the previous watermark, making the failure path
        unable to skip a block range accidentally.
        """

        if not isinstance(key, WatermarkKey):
            raise TypeError("key must be a WatermarkKey")
        if not isinstance(page_complete, bool):
            raise TypeError("page_complete must be a bool")
        if not page_complete:
            return self.get_watermark(key)

        if not isinstance(block_hash, str):
            raise ValueError("watermark block_hash must be a 32-byte hex hash")
        candidate = Watermark(
            block_number=block_number,
            block_hash=block_hash.lower(),
            overlap=overlap,
            updated_at=self._now(ts),
        )
        previous = self._watermarks.get(key)
        reorg_pending = key in self._reorg_starts
        if previous is not None and not reorg_pending:
            if candidate.block_number < previous.block_number:
                raise ValueError("watermark cannot move backwards without a reorg")
            if (
                candidate.block_number == previous.block_number
                and candidate.block_hash != previous.block_hash
            ):
                raise ValueError("same-block hash change must be reconciled as a reorg")
        self._watermarks[key] = candidate
        self._reorg_starts.pop(key, None)
        return candidate

    def scan_start(self, key: WatermarkKey, *, deployment_block: int) -> int:
        """First block for the next page, including the configured overlap."""

        deployment = _non_negative_int(deployment_block, "deployment_block")
        assert deployment is not None
        forced = self._reorg_starts.get(key)
        if forced is not None:
            return max(deployment, forced)
        watermark = self._watermarks.get(key)
        if watermark is None:
            return deployment
        return max(
            deployment,
            watermark.block_number + 1 - watermark.overlap,
        )

    def reconcile_block_hash(
        self,
        key: WatermarkKey,
        live_block_hash: str,
        *,
        deployment_block: int,
    ) -> bool:
        """Mark an overlap rewind when the saved watermark block was reorged.

        Returns ``True`` only on a mismatch.  The forced start survives a
        restart and is cleared only by :meth:`set_watermark` for a complete
        replacement page.
        """

        if not isinstance(live_block_hash, str) or not _BLOCK_HASH.fullmatch(
            live_block_hash
        ):
            raise ValueError("live_block_hash must be a 32-byte hex hash")
        watermark = self._watermarks.get(key)
        if watermark is None:
            return False
        if watermark.block_hash == live_block_hash.lower():
            return False
        deployment = _non_negative_int(deployment_block, "deployment_block")
        assert deployment is not None
        self._reorg_starts[key] = max(
            deployment,
            watermark.block_number + 1 - watermark.overlap,
        )
        return True

    # -- persistence ---------------------------------------------------------

    def _persistence_payload(self) -> dict[str, Any]:
        watermarks = [
            watermark.to_dict(key)
            for key, watermark in sorted(self._watermarks.items())
        ]
        reorg_starts = [
            {
                "adapter": key.adapter,
                "version": key.version,
                "topic_group": key.topic_group,
                "start_block": start,
            }
            for key, start in sorted(self._reorg_starts.items())
        ]
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "saved_at": self._now(),
            "snapshot": None if self._snapshot is None else self._snapshot.to_dict(),
            "last_good": {
                group: entry.to_dict()
                for group, entry in sorted(self._last_good.items())
            },
            "watermarks": watermarks,
            "reorg_starts": reorg_starts,
        }

    def save(self, path: str | None = None) -> bool:
        """Atomically persist via a same-directory temporary file and replace."""

        target = str(path or self.path)
        tmp = target + ".tmp"
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(
                    self._persistence_payload(),
                    handle,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save FWA ecosystem cache %s: %s", target, exc)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    def load(self, path: str | None = None, *, now: float | None = None) -> bool:
        """Load one schema, isolating malformed last-good and watermark slots."""

        target = str(path or self.path)
        try:
            with open(target, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.info("No FWA ecosystem cache to load (%s): %s", target, exc)
            return False
        if not isinstance(raw, Mapping):
            logger.warning("FWA ecosystem cache %s is not an object", target)
            return False
        version = raw.get("schema_version")
        if type(version) is not int or version != CACHE_SCHEMA_VERSION:
            logger.warning(
                "FWA ecosystem cache %s has unsupported schema %r",
                target,
                version,
            )
            return False

        reference = self._now(now)
        loaded_snapshot = self._load_snapshot(raw.get("snapshot"), reference)
        loaded_last_good = self._load_last_good(raw.get("last_good"), reference)
        loaded_watermarks = self._load_watermarks(raw.get("watermarks"), reference)
        loaded_reorgs = self._load_reorg_starts(
            raw.get("reorg_starts"), loaded_watermarks
        )

        # One assignment per complete section: callers cannot observe a file
        # half applied even if one slot was malformed.
        self._snapshot = loaded_snapshot
        self._last_good = loaded_last_good
        self._watermarks = loaded_watermarks
        self._reorg_starts = loaded_reorgs
        return True

    @staticmethod
    def _load_snapshot(raw: Any, now: float) -> NetworkSnapshot | None:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            return None
        try:
            ts = _validate_timestamp(raw.get("ts"), now=now, label="snapshot ts")
            payload = _validate_fragment(raw.get("payload"), exact=True)
            return NetworkSnapshot(payload=payload, ts=ts)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _load_last_good(raw: Any, now: float) -> dict[str, LastGood]:
        loaded: dict[str, LastGood] = {}
        if not isinstance(raw, Mapping):
            return loaded
        for group, entry in raw.items():
            if group not in GROUPS or not isinstance(entry, Mapping):
                continue
            try:
                ts = _validate_timestamp(
                    entry.get("ts"), now=now, label=f"{group} last-good ts"
                )
                block = _non_negative_int(entry.get("block_number"), "block_number")
                fingerprint = entry.get("source_fingerprint")
                if fingerprint is not None:
                    if not isinstance(fingerprint, str) or not _BLOCK_HASH.fullmatch(
                        fingerprint
                    ):
                        raise ValueError("invalid source fingerprint")
                    fingerprint = fingerprint.lower()
                payload = _validate_fragment(entry.get("payload"), exact=False)
                loaded[group] = LastGood(
                    payload=payload,
                    ts=ts,
                    block_number=block,
                    source_fingerprint=fingerprint,
                )
            except (TypeError, ValueError):
                continue
        return loaded

    @staticmethod
    def _load_watermarks(raw: Any, now: float) -> dict[WatermarkKey, Watermark]:
        loaded: dict[WatermarkKey, Watermark] = {}
        if not isinstance(raw, list):
            return loaded
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            try:
                key = WatermarkKey(
                    adapter=entry.get("adapter"),
                    version=entry.get("version"),
                    topic_group=entry.get("topic_group"),
                )
                watermark = Watermark(
                    block_number=entry.get("block_number"),
                    block_hash=str(entry.get("block_hash", "")).lower(),
                    overlap=entry.get("overlap"),
                    updated_at=_validate_timestamp(
                        entry.get("updated_at"),
                        now=now,
                        label="watermark updated_at",
                    ),
                )
                loaded[key] = watermark
            except (TypeError, ValueError):
                continue
        return loaded

    @staticmethod
    def _load_reorg_starts(
        raw: Any,
        watermarks: Mapping[WatermarkKey, Watermark],
    ) -> dict[WatermarkKey, int]:
        loaded: dict[WatermarkKey, int] = {}
        if not isinstance(raw, list):
            return loaded
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            try:
                key = WatermarkKey(
                    adapter=entry.get("adapter"),
                    version=entry.get("version"),
                    topic_group=entry.get("topic_group"),
                )
                start = _non_negative_int(entry.get("start_block"), "start_block")
                watermark = watermarks.get(key)
                if start is None or watermark is None or start > watermark.block_number:
                    continue
                loaded[key] = start
            except (TypeError, ValueError):
                continue
        return loaded


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "DEFAULT_CACHE_PATH",
    "DEGRADED_SOURCE_IDS",
    "FWAEcosystemCache",
    "GROUPS",
    "GROUP_CORE",
    "GROUP_DROPS",
    "GROUP_FLOW_LOGS",
    "GROUP_FWAP",
    "GROUP_INTEGRITY",
    "GROUP_MARKET",
    "GROUP_MEGARIP",
    "GROUP_PROJECT_LOGS",
    "GROUP_PULLPOOL",
    "LastGood",
    "MAX_REORG_OVERLAP",
    "NetworkSnapshot",
    "TIERS",
    "TIER_API",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_INTEGRITY",
    "TIER_MEDIUM",
    "TIER_TTL_SECONDS",
    "Watermark",
    "WatermarkKey",
]
