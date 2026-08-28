"""Bounded orchestration for the flat FWA NETWORK presentation payload.

The manager is deliberately a controller.  Contract reads and event decoding
remain in their clients/adapters, tokenomics calculations remain in
``analytics.fwa_ecosystem``, and persistence remains in
``fwa_ecosystem_cache``.  This module only pins one block, isolates sources,
applies last-good freshness, schedules bounded background work, and publishes
one complete validated snapshot.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from maxpane_dashboard.analytics.fwa_ecosystem import (
    build_flow_rows,
    burned_since_genesis,
    wei_to_tokens,
)
from maxpane_dashboard.data.fwa_drops_client import FWAIRDropsClient
from maxpane_dashboard.data.fwa_ecosystem_addresses import OFFICIAL_DEPLOYMENTS
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    GROUP_CORE,
    GROUP_DROPS,
    GROUP_FLOW_LOGS,
    GROUP_FWAP,
    GROUP_INTEGRITY,
    GROUP_MEGARIP,
    GROUP_PROJECT_LOGS,
    GROUP_PULLPOOL,
    TIER_API,
    TIER_FAST,
    TIER_INTEGRITY,
    TIER_MEDIUM,
    TIER_TTL_SECONDS,
    FWAEcosystemCache,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
    NetworkEventRow,
    ProjectRow,
    blank_network_payload,
)
from maxpane_dashboard.data.fwa_logs import FWALogClient
from maxpane_dashboard.data.fwa_projects.fwap import (
    EVENT_SPECS as FWAP_EVENT_SPECS,
    FWAP_MANIFESTS,
    FWAPAdapter,
    build_project_rows as build_fwap_rows,
    decode_events as decode_fwap_events,
    normalize_events as normalize_fwap_events,
)
from maxpane_dashboard.data.fwa_projects.megarip import (
    MEGARIP_MANIFESTS,
    MegaRipAdapter,
)
from maxpane_dashboard.data.fwa_projects.pullpool import (
    ALL_MANIFESTS as PULLPOOL_MANIFESTS,
    LOG_STREAMS as PULLPOOL_LOG_STREAMS,
    PullPoolAdapter,
    PullPoolHistory,
    accumulate_history as accumulate_pullpool_history,
    build_project_rows as build_pullpool_rows,
    normalize_events as normalize_pullpool_events,
)
from maxpane_dashboard.data.fwa_tokenomics_client import (
    DEPENDENCIES as TOKENOMICS_DEPENDENCIES,
    FWATokenomicsClient,
    FWATokenomicsLogClient,
    TokenomicsLogRead,
)

logger = logging.getLogger(__name__)

FAST_REQUEST_TIMEOUT = 8.0
API_REQUEST_TIMEOUT = 6.0
BACKGROUND_REQUEST_TIMEOUT = 12.0
LOG_PAGE_BLOCKS = 5_000
LOG_PAGES_PER_CYCLE = 2
REORG_OVERLAP = 64
EVENT_LIMIT = 500

_FLOW_WATERMARK = WatermarkKey("tokenomics", "v1", "flow")
_TOKEN_DEPLOYMENT_BLOCK = next(
    item.deployment_block for item in OFFICIAL_DEPLOYMENTS if item.role == "token"
)
_PROJECT_GROUPS = (GROUP_PULLPOOL, GROUP_MEGARIP, GROUP_FWAP)
_PROJECT_LOG_SOURCES = frozenset(("pullpool", "megarip", "fwap"))
_DIRECT_GROUPS = (GROUP_CORE, GROUP_DROPS, *_PROJECT_GROUPS)
_DEFAULT = object()
_HASH_CHARS = frozenset("0123456789abcdef")


def _finite_now(clock: Callable[[], float]) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("ecosystem clock must return epoch seconds")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("ecosystem clock must return finite epoch seconds")
    return value


def _block(value: Any, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("state block must be an integer")
    if value < (1 if positive else 0):
        raise ValueError("state block is unavailable")
    return value


def _block_hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.lower()
    if (
        len(value) != 66
        or not value.startswith("0x")
        or any(char not in _HASH_CHARS for char in value[2:])
    ):
        return None
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        value = dump()
        if isinstance(value, Mapping):
            return dict(value)
    raise TypeError("presentation row must be a mapping or pydantic model")


def _event_sort_key(row: Mapping[str, Any]) -> tuple[int, int]:
    block_number = row.get("block_number")
    log_index = row.get("log_index")
    return (
        block_number if isinstance(block_number, int) else -1,
        log_index if isinstance(log_index, int) else -1,
    )


def _visible_legacy(row: Mapping[str, Any]) -> bool:
    if row.get("is_current") is True:
        return True
    eth = row.get("eth_value")
    fwa = row.get("fwa_value")
    return bool(
        (isinstance(eth, (int, float)) and not isinstance(eth, bool) and eth > 0)
        or (isinstance(fwa, (int, float)) and not isinstance(fwa, bool) and fwa > 0)
        or row.get("integrity") != "ok"
    )


@dataclass(frozen=True, slots=True)
class FWAPLogPage:
    """One caller-bounded raw FWAP log page.

    The block hash is optional because the manager may obtain it from its
    independently injected hash reader.  A page without a validated hash is
    still decodable but cannot advance a watermark.
    """

    logs: tuple[Mapping[str, Any], ...]
    block_hash: str | None = None
    page_complete: bool = True


class FWAPLogSource:
    """Minimal keyless Pool-B transport for FWAP's pure event decoder."""

    def __init__(
        self,
        *,
        endpoints: Sequence[str] | None = None,
        http_client: Any = None,
        min_call_interval: float = 0.05,
    ) -> None:
        self._endpoints = endpoints
        self._http_client = http_client
        self._min_call_interval = min_call_interval
        self._clients: dict[str, FWALogClient] = {}
        self._closed = False

    def _client(self, address: str) -> FWALogClient:
        client = self._clients.get(address)
        if client is None:
            client = FWALogClient(
                endpoints=self._endpoints,
                http_client=self._http_client,
                core_address=address,
                min_call_interval=self._min_call_interval,
            )
            self._clients[address] = client
        return client

    async def fetch_page(
        self,
        *,
        address: str,
        topics: Sequence[str],
        from_block: int,
        to_block: int,
    ) -> FWAPLogPage:
        raw = await self._client(address).get_logs(
            [list(topics)], from_block, to_block
        )
        return FWAPLogPage(logs=tuple(raw))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.gather(
            *(client.close() for client in self._clients.values()),
            return_exceptions=True,
        )
        self._clients.clear()


class FWAEcosystemManager:
    """Produce and retain the exact ordered 40-key NETWORK payload."""

    def __init__(
        self,
        poll_interval: float = 60.0,
        *,
        tokenomics_client: Any | None = None,
        tokenomics_log_client: Any | None = None,
        drops_client: Any | None = None,
        pullpool_adapter: Any | None = None,
        megarip_adapter: Any | None = None,
        fwap_adapter: Any | None = None,
        fwap_log_source: Any = _DEFAULT,
        block_source: Any | None = None,
        block_hash_reader: Any | None = None,
        cache: FWAEcosystemCache | None = None,
        clock: Callable[[], float] = time.time,
        load_cache: bool = True,
        persist_cache: bool = True,
        gas_price_wei: int | None = None,
        fast_timeout: float = FAST_REQUEST_TIMEOUT,
        api_timeout: float = API_REQUEST_TIMEOUT,
        background_timeout: float = BACKGROUND_REQUEST_TIMEOUT,
        page_blocks: int = LOG_PAGE_BLOCKS,
        pages_per_cycle: int = LOG_PAGES_PER_CYCLE,
        reorg_overlap: int = REORG_OVERLAP,
        event_limit: int = EVENT_LIMIT,
    ) -> None:
        for label, value in (
            ("poll_interval", poll_interval),
            ("fast_timeout", fast_timeout),
            ("api_timeout", api_timeout),
            ("background_timeout", background_timeout),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError(f"{label} must be finite and positive")
        for label, value in (
            ("page_blocks", page_blocks),
            ("pages_per_cycle", pages_per_cycle),
            ("reorg_overlap", reorg_overlap),
            ("event_limit", event_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive int")
        if page_blocks > LOG_PAGE_BLOCKS:
            raise ValueError(f"page_blocks cannot exceed {LOG_PAGE_BLOCKS}")
        if pages_per_cycle > LOG_PAGES_PER_CYCLE:
            raise ValueError(
                f"pages_per_cycle cannot exceed {LOG_PAGES_PER_CYCLE}"
            )
        if reorg_overlap > page_blocks:
            raise ValueError("reorg_overlap cannot exceed page_blocks")
        if gas_price_wei is not None and (
            isinstance(gas_price_wei, bool)
            or not isinstance(gas_price_wei, int)
            or gas_price_wei < 0
        ):
            raise ValueError("gas_price_wei must be a non-negative int or None")

        self.poll_interval = float(poll_interval)
        self._clock = clock
        self._fast_timeout = float(fast_timeout)
        self._api_timeout = float(api_timeout)
        self._background_timeout = float(background_timeout)
        self._page_blocks = page_blocks
        self._pages_per_cycle = pages_per_cycle
        self._reorg_overlap = reorg_overlap
        self._event_limit = event_limit
        self._gas_price_wei = gas_price_wei
        self._persist_cache = bool(persist_cache)

        self.tokenomics_client = tokenomics_client or FWATokenomicsClient(clock=clock)
        self.tokenomics_logs = (
            tokenomics_log_client or FWATokenomicsLogClient(clock=clock)
        )
        self.drops_client = drops_client or FWAIRDropsClient(clock=clock)
        self.pullpool = pullpool_adapter or PullPoolAdapter(
            clock=clock,
            page_size=page_blocks,
            max_pages=pages_per_cycle,
            overlap=reorg_overlap,
        )
        self.megarip = megarip_adapter or MegaRipAdapter(clock=clock)
        self.fwap = fwap_adapter or FWAPAdapter(clock=clock)
        self.fwap_logs = (
            FWAPLogSource() if fwap_log_source is _DEFAULT else fwap_log_source
        )
        self.block_source = block_source or self.tokenomics_client
        self.block_hash_reader = block_hash_reader or self.tokenomics_logs

        cache_was_injected = cache is not None
        self.cache = cache or FWAEcosystemCache(clock=clock)
        if load_cache and not cache_was_injected:
            self.cache.load()

        snapshot = self.cache.latest_snapshot()
        self._error_count = 0
        if snapshot is not None:
            previous = snapshot.payload.get("network_error_count")
            if isinstance(previous, int) and not isinstance(previous, bool):
                self._error_count = previous
        self._last_chain_head: int | None = (
            None
            if snapshot is None
            else snapshot.payload.get("network_chain_head")
        )
        restored_pin = None if snapshot is None else snapshot.payload.get(
            "network_chain_head"
        )
        if not isinstance(restored_pin, int) or isinstance(restored_pin, bool):
            restored_pin = (
                None if snapshot is None else snapshot.payload.get("network_state_block")
            )
        self._state_block: int | None = (
            restored_pin
            if isinstance(restored_pin, int) and not isinstance(restored_pin, bool)
            else None
        )
        self._cycle_pin_valid = self._state_block is not None
        self._failed_groups: set[str] = set()
        self._token_state: Any | None = None
        self._drops_state: Any | None = None
        self._pull_state: Any | None = None
        self._mega_state: Any | None = None
        self._fwap_state: Any | None = None
        self._core_integrity: Any | None = None
        self._pull_integrity: Any | None = None
        self._fwap_integrity: Any | None = None
        self._fwap_api: Any | None = None
        self._fwap_api_chain_block: int | None = None
        self._pull_history: PullPoolHistory | None = None
        self._flow_logs: TokenomicsLogRead | None = None
        self._flow_buybacks: dict[tuple[str, int], Any] = {}
        self._flow_burns: dict[tuple[str, int], Any] = {}
        self._flow_coverage_end: int | None = None
        # Watermarks are not proof that this process has the corresponding
        # accumulator.  Coverage starts empty after every restart, even when
        # the presentation cache restored rows and cursors.
        self._project_coverage_end: dict[WatermarkKey, int] = {}
        restored_flow = self.cache.get_last_good(GROUP_FLOW_LOGS)
        self._has_restored_flow_fragment = restored_flow is not None
        self._events: dict[str, dict[str, Any]] = {}
        restored_events = self.cache.get_last_good(GROUP_PROJECT_LOGS)
        # Persisted presentation rows remain visible through cache last-good,
        # but are not raw history and therefore never seed the mutable event
        # accumulator or inherit fresh provenance after restart.
        self._has_restored_event_fragment = restored_events is not None
        self._restored_events: dict[str, dict[str, Any]] = {}
        if restored_events is not None:
            for raw in restored_events.payload.get("network_events", ()):
                if isinstance(raw, Mapping) and isinstance(raw.get("event_id"), str):
                    row = dict(raw)
                    row["stale"] = True
                    self._restored_events[row["event_id"]] = row
            restored_payload = deepcopy(restored_events.payload)
            restored_payload["network_events"] = list(
                self._restored_events.values()
            )
            self.cache.store_last_good(
                GROUP_PROJECT_LOGS,
                restored_payload,
                ts=restored_events.ts,
                block_number=restored_events.block_number,
            )
        self._project_log_failed: set[str] = set()
        if restored_events is not None:
            self._failed_groups.add(GROUP_PROJECT_LOGS)
        if restored_flow is not None:
            self._failed_groups.add(GROUP_FLOW_LOGS)

        self._pull_stream_cursor = 0
        self._mega_stream_cursor = 0
        self._fwap_stream_cursor = 0
        self._fast_task: asyncio.Task[dict[str, Any]] | None = None
        self._background_tasks: dict[str, asyncio.Task[None]] = {}
        self._commit_lock = asyncio.Lock()
        self._closed = False

    # -- public lifecycle -------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Refresh due fast state, schedule slow work, and return 40 keys."""

        if self._closed:
            return self._visible_snapshot()

        now = _finite_now(self._clock)
        if self.cache.is_due(TIER_FAST, now):
            task = self._fast_task
            if task is None or task.done():
                task = asyncio.create_task(
                    self._run_fast_cycle(), name="fwa-network-fast"
                )
                task.add_done_callback(self._observe_task)
                self._fast_task = task
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- last-good boundary
                logger.debug("FWA fast cycle failed at manager boundary: %s", exc)

        self._harvest_fast()
        self._schedule_due_background()
        return self._visible_snapshot()

    async def close(self) -> None:
        """Cancel all owned work and close every distinct collaborator once."""

        if self._closed:
            return
        self._closed = True
        tasks: list[asyncio.Task[Any]] = []
        if self._fast_task is not None:
            tasks.append(self._fast_task)
            self._fast_task = None
        tasks.extend(self._background_tasks.values())
        self._background_tasks.clear()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[int] = set()
        for client in (
            self.tokenomics_client,
            self.tokenomics_logs,
            self.drops_client,
            self.pullpool,
            self.megarip,
            self.fwap,
            self.fwap_logs,
            self.block_source,
            self.block_hash_reader,
        ):
            if client is None or id(client) in seen:
                continue
            seen.add(id(client))
            close = getattr(client, "close", None)
            if close is None:
                close = getattr(client, "aclose", None)
            if not callable(close):
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 -- close remaining peers
                logger.debug("closing FWA NETWORK client failed: %s", exc)

    # -- fast pinned state ------------------------------------------------

    async def _run_fast_cycle(self) -> dict[str, Any]:
        self._cycle_pin_valid = False
        try:
            state_block = await asyncio.wait_for(
                self._obtain_state_block(), timeout=self._fast_timeout
            )
        except Exception as exc:  # noqa: BLE001 -- exact blank/last-good
            self._record_failure(*_DIRECT_GROUPS, error=exc)
            self.cache.mark_failed(TIER_FAST, _finite_now(self._clock))
            await self._commit_from_groups()
            return self._visible_snapshot()

        self._last_chain_head = state_block
        self._state_block = state_block
        self._cycle_pin_valid = True
        calls = (
            (GROUP_CORE, self._fetch_core(state_block)),
            (GROUP_DROPS, self.drops_client.fetch_drops(block_number=state_block)),
            (GROUP_PULLPOOL, self.pullpool.fetch_state(state_block)),
            (GROUP_MEGARIP, self.megarip.fetch_state(block_number=state_block)),
            (GROUP_FWAP, self.fwap.fetch_state(state_block)),
        )
        results = await asyncio.gather(
            *(
                self._bounded(coro, self._fast_timeout)
                for _group, coro in calls
            ),
            return_exceptions=True,
        )

        any_success = False
        all_success = True
        for (group, _coro), result in zip(calls, results, strict=True):
            if isinstance(result, BaseException):
                self._record_failure(group, error=result)
                all_success = False
                continue
            try:
                self._accept_direct(group, result, state_block)
            except Exception as exc:  # noqa: BLE001 -- adapter boundary
                self._record_failure(group, error=exc)
                all_success = False
            else:
                any_success = True
                self._failed_groups.discard(group)

        now = _finite_now(self._clock)
        if any_success and all_success:
            self.cache.mark_fetched(TIER_FAST, now)
        else:
            self.cache.mark_failed(TIER_FAST, now)
        await self._commit_from_groups()
        return self._visible_snapshot()

    async def _fetch_core(self, state_block: int) -> Any:
        kwargs: dict[str, Any] = {"block_number": state_block}
        if self._gas_price_wei is not None:
            kwargs["gas_price_wei"] = self._gas_price_wei
        return await self.tokenomics_client.fetch_state(**kwargs)

    async def _obtain_state_block(self) -> int:
        source = self.block_source
        if callable(source) and not hasattr(source, "fetch_block_number"):
            result = source()
        else:
            method = getattr(source, "fetch_block_number", None)
            if method is None:
                method = getattr(source, "head_block", None)
            if not callable(method):
                raise TypeError("block_source must expose fetch_block_number()")
            result = method()
        if inspect.isawaitable(result):
            result = await result
        return _block(result, positive=True)

    def _accept_direct(self, group: str, result: Any, state_block: int) -> None:
        if group == GROUP_CORE:
            _block(getattr(result, "state_block", None))
            if result.state_block != state_block:
                raise ValueError("core returned a different state block")
            self._token_state = result
            self._store_core_fragment()
            return
        if group == GROUP_DROPS:
            if getattr(result, "state_block", None) != state_block:
                raise ValueError("drops returned a different state block")
            if getattr(result, "available", None) is not True:
                raise RuntimeError("drops read unavailable")
            self._drops_state = result
            self._store_drops_fragment(result)
            return
        if group == GROUP_PULLPOOL:
            if getattr(result, "block_number", None) != state_block:
                raise ValueError("PullPool returned a different state block")
            integrity = self._matching_integrity(
                self._pull_integrity, state_block
            )
            rows = build_pullpool_rows(
                result,
                history=self._pull_history,
                integrity=integrity,
            )
            self._pull_state = result
            self._store_project_fragment(group, rows, result.observed_at, state_block)
            return
        if group == GROUP_MEGARIP:
            if getattr(result, "state_block", None) != state_block:
                raise ValueError("MegaRip returned a different state block")
            self._mega_state = result
            self._store_project_fragment(
                group, result.rows, result.observed_at, state_block
            )
            return
        if group == GROUP_FWAP:
            if getattr(result, "block_number", None) != state_block:
                raise ValueError("FWAP returned a different state block")
            rows = build_fwap_rows(
                result,
                integrity=self._matching_integrity(
                    self._fwap_integrity, state_block
                ),
                api=self._api_for_state(state_block),
            )
            self._fwap_state = result
            self._store_project_fragment(group, rows, result.observed_at, state_block)
            return
        raise ValueError(f"unknown direct group {group!r}")

    def _store_core_fragment(self) -> None:
        state = self._token_state
        if state is None:
            return
        source_now = float(state.observed_at)
        state_block = state.state_block
        integrity = self._matching_integrity(self._core_integrity, state_block)
        logs = self._flow_logs
        if (
            logs is not None
            and state_block is not None
            and logs.to_block > state_block
        ):
            logs = None
        rows = build_flow_rows(
            state,
            now=source_now,
            logs=logs,
            integrity=integrity,
            state_stale=False,
            logs_stale=False,
        )
        core_status = (
            "unknown"
            if integrity is None
            else integrity.status_for("core")
        )
        token_status = (
            "unknown"
            if integrity is None
            else integrity.status_for("token", "hook")
        )
        burn = burned_since_genesis(state.total_supply_wei)
        supply = wei_to_tokens(state.total_supply_wei)
        if token_status == "mismatch":
            supply = None
            burn_fwa = None
            burn_pct = None
        else:
            burn_fwa = burn.burned_fwa
            burn_pct = burn.burned_pct
        latest = None
        if logs is not None and logs.buybacks:
            latest = max(
                logs.buybacks,
                key=lambda item: (item.block_number, item.bought_log_index),
            )
        latest_age: float | None = None
        if latest is not None and latest.block_timestamp is not None:
            latest_age = max(0.0, source_now - float(latest.block_timestamp))
        fragment = {
            "network_state_block": state.state_block,
            "network_chain_head": state.chain_head,
            "network_state_stale": False,
            "network_active_listings": (
                None if core_status == "mismatch" else state.active_listings
            ),
            "network_pull_quote_eth": (
                None if core_status == "mismatch" else wei_to_tokens(state.quote_total_wei)
            ),
            "network_pending_count": (
                None if core_status == "mismatch" else state.pending_count
            ),
            "network_unsettled_count": (
                None if core_status == "mismatch" else state.unsettled_count
            ),
            "network_crown_pot_eth": (
                None if core_status == "mismatch" else wei_to_tokens(state.crown_pot_wei)
            ),
            "network_token_supply_fwa": supply,
            "network_burned_since_genesis_fwa": burn_fwa,
            "network_burned_since_genesis_pct": burn_pct,
            "network_last_buyback_age_s": latest_age,
            "network_flow_rows": rows,
            "network_flow_available": True,
        }
        self.cache.store_last_good(
            GROUP_CORE,
            fragment,
            ts=source_now,
            block_number=state.state_block,
        )

    @staticmethod
    def _matching_integrity(integrity: Any | None, block_number: int | None) -> Any | None:
        if integrity is None or block_number is None:
            return None
        return integrity if getattr(integrity, "block_number", None) == block_number else None

    @staticmethod
    def _integrity_read_complete(
        label: str, result: Any, block_number: int
    ) -> bool:
        """Accept verified matches or mismatches, never fail-soft unknowns."""

        if result is None or getattr(result, "block_number", None) != block_number:
            return False
        if label == "core":
            codehashes = getattr(result, "codehash_matches", None)
            dependencies = getattr(result, "dependency_matches", None)
            if not isinstance(codehashes, Mapping) or not isinstance(
                dependencies, Mapping
            ):
                return False
            expected_codehashes = {
                deployment.role for deployment in OFFICIAL_DEPLOYMENTS
            }
            expected_dependencies = {
                dependency.key for dependency in TOKENOMICS_DEPENDENCIES
            }
            return bool(
                set(codehashes) == expected_codehashes
                and set(dependencies) == expected_dependencies
                and all(type(value) is bool for value in codehashes.values())
                and all(type(value) is bool for value in dependencies.values())
            )

        manifests = PULLPOOL_MANIFESTS if label == "pullpool" else FWAP_MANIFESTS
        expected = {manifest.address.lower(): manifest for manifest in manifests}
        surfaces = getattr(result, "surfaces", None)
        if (
            not isinstance(surfaces, Sequence)
            or isinstance(surfaces, (str, bytes))
            or len(surfaces) != len(expected)
        ):
            return False
        seen: set[str] = set()
        for surface in surfaces:
            address = str(getattr(surface, "address", "")).lower()
            manifest = expected.get(address)
            if (
                manifest is None
                or address in seen
                or getattr(surface, "block_number", None) != block_number
                or type(getattr(surface, "codehash_match", None)) is not bool
                or getattr(surface, "status", "unknown")
                not in {"ok", "warning", "mismatch"}
            ):
                return False
            pairs = getattr(surface, "dependency_matches", None)
            if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)):
                return False
            actual_dependencies: dict[str, bool] = {}
            for pair in pairs:
                if (
                    not isinstance(pair, Sequence)
                    or isinstance(pair, (str, bytes))
                    or len(pair) != 2
                    or not isinstance(pair[0], str)
                    or type(pair[1]) is not bool
                    or pair[0] in actual_dependencies
                ):
                    return False
                actual_dependencies[pair[0]] = pair[1]
            if set(actual_dependencies) != {
                getter for getter, _expected in manifest.dependencies
            }:
                return False
            seen.add(address)
        return seen == set(expected)

    def _api_for_state(self, block_number: int) -> Any | None:
        if (
            self._fwap_api is None
            or self._fwap_api_chain_block is None
            or self._fwap_api_chain_block > block_number
        ):
            return None
        return self._fwap_api

    def _store_drops_fragment(self, read: Any) -> None:
        rows = [_row_dict(row) for row in read.rows]
        self.cache.store_last_good(
            GROUP_DROPS,
            {
                "network_drop_rows": rows,
                "network_drops_available": True,
                "network_drops_as_of_block": read.state_block,
                "network_drops_stale": False,
                "network_drop_count": int(read.valid_count),
            },
            ts=float(read.observed_at),
            block_number=read.state_block,
        )

    def _store_project_fragment(
        self,
        group: str,
        rows: Sequence[Any],
        observed_at: float,
        block_number: int,
    ) -> None:
        canonical: list[dict[str, Any]] = []
        for raw in rows:
            row = ProjectRow.model_validate(_row_dict(raw)).model_dump()
            if tuple(row) != PROJECT_ROW_KEYS:
                raise ValueError("project row key order drift")
            if _visible_legacy(row):
                canonical.append(row)
        self.cache.store_last_good(
            group,
            {"network_project_rows": canonical},
            ts=float(observed_at),
            block_number=block_number,
        )

    # -- background task orchestration -----------------------------------

    @staticmethod
    def _observe_task(task: asyncio.Task[Any]) -> None:
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    def _harvest_fast(self) -> None:
        task = self._fast_task
        if task is not None and task.done():
            self._fast_task = None

    def _schedule_due_background(self) -> None:
        if self._closed or not self._cycle_pin_valid or self._state_block is None:
            return
        for tier, factory in (
            (TIER_MEDIUM, self._run_medium_cycle),
            (TIER_API, self._run_api_cycle),
            (TIER_INTEGRITY, self._run_integrity_cycle),
        ):
            existing = self._background_tasks.get(tier)
            if existing is not None:
                if not existing.done():
                    continue
                self._background_tasks.pop(tier, None)
            if not self.cache.is_due(tier, _finite_now(self._clock)):
                continue
            task = asyncio.create_task(factory(), name=f"fwa-network-{tier}")
            task.add_done_callback(
                lambda done, tier=tier: self._background_done(tier, done)
            )
            self._background_tasks[tier] = task

    def _background_done(self, tier: str, task: asyncio.Task[None]) -> None:
        self._observe_task(task)
        if self._background_tasks.get(tier) is task:
            self._background_tasks.pop(tier, None)

    async def _run_medium_cycle(self) -> None:
        block_number = self._current_state_block()
        if block_number is None or not self._pin_matches(block_number):
            self.cache.mark_failed(TIER_MEDIUM, _finite_now(self._clock))
            return
        operations = (
            (GROUP_FLOW_LOGS, self._refresh_flow_logs(block_number)),
            ("pullpool", self._refresh_pullpool_logs(block_number)),
            ("megarip", self._refresh_megarip_logs(block_number)),
            ("fwap", self._refresh_fwap_logs(block_number)),
        )
        results = await asyncio.gather(
            *(
                self._bounded(coro, self._background_timeout)
                for _label, coro in operations
            ),
            return_exceptions=True,
        )
        if not self._pin_matches(block_number):
            # A newer fast cycle owns publication.  Old historical results
            # may remain useful only if a source committed them while the pin
            # still matched; this cycle must never label them fresh.
            self._failed_groups.update((GROUP_FLOW_LOGS, GROUP_PROJECT_LOGS))
            self._project_log_failed.update(_PROJECT_LOG_SOURCES)
            self.cache.mark_failed(TIER_MEDIUM, _finite_now(self._clock))
            await self._commit_from_groups()
            return
        project_results: dict[str, bool] = {}
        flow_ok = False
        for (label, _coro), result in zip(operations, results, strict=True):
            ok = result is True
            if isinstance(result, BaseException):
                self._error_count += 1
                logger.debug("%s refresh failed: %s", label, result)
            if label == GROUP_FLOW_LOGS:
                flow_ok = ok
            else:
                project_results[label] = ok
                if ok:
                    self._project_log_failed.discard(label)
                else:
                    self._project_log_failed.add(label)

        if flow_ok:
            self._failed_groups.discard(GROUP_FLOW_LOGS)
        else:
            self._failed_groups.add(GROUP_FLOW_LOGS)
        project_pages_ok = bool(
            project_results and all(project_results.values())
        )
        if project_pages_ok:
            self._failed_groups.discard(GROUP_PROJECT_LOGS)
        else:
            self._failed_groups.add(GROUP_PROJECT_LOGS)

        now = _finite_now(self._clock)
        if flow_ok and project_pages_ok:
            self.cache.mark_fetched(TIER_MEDIUM, now)
        else:
            self.cache.mark_failed(TIER_MEDIUM, now)
        successful_projects = {
            source for source, ok in project_results.items() if ok
        }
        if successful_projects:
            await self._store_event_fragment(
                now,
                state_block=block_number,
                successful_sources=successful_projects,
            )
        await self._commit_from_groups()

    async def _run_api_cycle(self) -> None:
        block_number = self._current_state_block()
        if block_number is None or self._closed:
            self.cache.mark_failed(TIER_API, _finite_now(self._clock))
            return
        try:
            result = await self._bounded(
                self.fwap.fetch_api_snapshot(block_number), self._api_timeout
            )
            if self._current_state_block() != block_number:
                self.cache.mark_failed(TIER_API, _finite_now(self._clock))
                await self._commit_from_groups()
                return
            self._fwap_api = result
            self._fwap_api_chain_block = block_number
            if (
                self._fwap_state is not None
                and self._fwap_state.block_number == block_number
            ):
                rows = build_fwap_rows(
                    self._fwap_state,
                    integrity=self._matching_integrity(
                        self._fwap_integrity, block_number
                    ),
                    api=result,
                )
                self._store_project_fragment(
                    GROUP_FWAP,
                    rows,
                    self._fwap_state.observed_at,
                    self._fwap_state.block_number,
                )
        except Exception as exc:  # noqa: BLE001 -- optional enrichment
            self._error_count += 1
            self.cache.mark_failed(TIER_API, _finite_now(self._clock))
            logger.debug("FWAP API enrichment failed: %s", exc)
        else:
            self.cache.mark_fetched(TIER_API, _finite_now(self._clock))
        await self._commit_from_groups()

    async def _run_integrity_cycle(self) -> None:
        block_number = self._current_state_block()
        if block_number is None or self._closed:
            self.cache.mark_failed(TIER_INTEGRITY, _finite_now(self._clock))
            return
        calls = (
            ("core", self.tokenomics_client.fetch_official_integrity(block_number)),
            ("pullpool", self.pullpool.fetch_integrity(block_number)),
            ("fwap", self.fwap.fetch_integrity(block_number)),
        )
        results = await asyncio.gather(
            *(
                self._bounded(coro, self._background_timeout)
                for _label, coro in calls
            ),
            return_exceptions=True,
        )
        if self._current_state_block() != block_number:
            # A newer fast snapshot won the race.  Never attach integrity
            # proved at the old block to its new state rows.
            self._failed_groups.add(GROUP_INTEGRITY)
            self.cache.mark_failed(TIER_INTEGRITY, _finite_now(self._clock))
            await self._commit_from_groups()
            return
        successes = 0
        for (label, _coro), result in zip(calls, results, strict=True):
            if isinstance(result, BaseException):
                self._error_count += 1
                logger.debug("%s integrity failed: %s", label, result)
                continue
            if not self._integrity_read_complete(label, result, block_number):
                self._error_count += 1
                logger.debug("%s integrity read incomplete", label)
                continue
            successes += 1
            if label == "core":
                if (
                    self._token_state is not None
                    and self._token_state.state_block == block_number
                ):
                    self._core_integrity = result
                    self._store_core_fragment()
            elif label == "pullpool":
                if (
                    self._pull_state is not None
                    and self._pull_state.block_number == block_number
                ):
                    self._pull_integrity = result
                    rows = build_pullpool_rows(
                        self._pull_state,
                        history=self._pull_history,
                        integrity=self._pull_integrity,
                    )
                    self._store_project_fragment(
                        GROUP_PULLPOOL,
                        rows,
                        self._pull_state.observed_at,
                        self._pull_state.block_number,
                    )
            else:
                if (
                    self._fwap_state is not None
                    and self._fwap_state.block_number == block_number
                ):
                    self._fwap_integrity = result
                    rows = build_fwap_rows(
                        self._fwap_state,
                        integrity=self._fwap_integrity,
                        api=self._api_for_state(block_number),
                    )
                    self._store_project_fragment(
                        GROUP_FWAP,
                        rows,
                        self._fwap_state.observed_at,
                        self._fwap_state.block_number,
                    )
        now = _finite_now(self._clock)
        if successes == len(calls):
            self._failed_groups.discard(GROUP_INTEGRITY)
            self.cache.mark_fetched(TIER_INTEGRITY, now)
        else:
            self._failed_groups.add(GROUP_INTEGRITY)
            self.cache.mark_failed(TIER_INTEGRITY, now)
        if successes == len(calls):
            self.cache.store_last_good(
                GROUP_INTEGRITY,
                {"network_integrity_warning_count": self._integrity_warning_count()},
                ts=now,
                block_number=block_number,
            )
        await self._commit_from_groups()

    # -- bounded historical sources --------------------------------------

    async def _refresh_flow_logs(self, state_block: int) -> bool:
        if not self._pin_matches(state_block):
            return False
        resumed = await self._resume_start(
            _FLOW_WATERMARK,
            _TOKEN_DEPLOYMENT_BLOCK,
            self._flow_coverage_end,
            expected_state_block=state_block,
        )
        if resumed is None or not self._pin_matches(state_block):
            return False
        start, reorged = resumed
        buybacks = dict(self._flow_buybacks)
        burns = dict(self._flow_burns)
        coverage_end = self._flow_coverage_end

        def drop_range(from_block: int, to_block: int | None) -> None:
            nonlocal buybacks, burns

            def kept(block_number: int) -> bool:
                if block_number < from_block:
                    return True
                return to_block is not None and block_number > to_block

            buybacks = {
                key: event
                for key, event in buybacks.items()
                if kept(event.block_number)
            }
            burns = {
                key: event
                for key, event in burns.items()
                if kept(event.block_number)
            }

        if reorged:
            drop_range(start, None)
            coverage_end = start - 1
        page_success = False
        page_failed = False
        last_observed: float | None = None
        last_to: int | None = None
        completed_pages: list[tuple[int, str, float]] = []
        for _ in range(self._pages_per_cycle):
            if start > state_block:
                break
            end = min(start + self._page_blocks - 1, state_block)
            read = await self.tokenomics_logs.fetch_flow_logs(
                start, end, history_complete=False
            )
            if not self._pin_matches(state_block):
                return False
            hash_value = await self._read_block_hash(end)
            if not self._pin_matches(state_block):
                return False
            complete = bool(
                read.buybacks_available and read.burns_available and hash_value
            )
            if not complete:
                page_failed = True
                break
            # An overlap is a canonical replacement, not an additive merge.
            drop_range(start, end)
            for event in read.buybacks:
                buybacks[(event.tx_hash, event.bought_log_index)] = event
            for event in read.burns:
                burns[(event.tx_hash, event.log_index)] = event
            page_success = True
            last_observed = float(read.observed_at)
            last_to = end
            coverage_end = end
            completed_pages.append((end, hash_value, last_observed))
            start = end + 1

        if not page_success or not self._pin_matches(state_block):
            return False
        history_complete = bool(
            coverage_end is not None and coverage_end >= state_block
        )
        assert last_observed is not None and last_to is not None
        next_logs = TokenomicsLogRead(
            observed_at=last_observed,
            from_block=_TOKEN_DEPLOYMENT_BLOCK,
            to_block=last_to,
            history_complete=history_complete,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=tuple(
                sorted(
                    buybacks.values(),
                    key=lambda item: (item.block_number, item.bought_log_index),
                )
            ),
            burns=tuple(
                sorted(
                    burns.values(),
                    key=lambda item: (item.block_number, item.log_index),
                )
            ),
        )
        self._flow_buybacks = buybacks
        self._flow_burns = burns
        self._flow_coverage_end = coverage_end
        self._flow_logs = next_logs
        for page_end, page_hash, page_ts in completed_pages:
            self._advance_watermark(
                _FLOW_WATERMARK,
                block_number=page_end,
                block_hash=page_hash,
                ts=page_ts,
                deployment_block=_TOKEN_DEPLOYMENT_BLOCK,
            )

        # A persisted presentation fragment is not the raw accumulator.  Keep
        # it visibly stale and untouched until the rebuilt scan proves full
        # deployment-to-state coverage.
        if self._has_restored_flow_fragment and not history_complete:
            return False
        compatible_core = bool(
            self._token_state is not None
            and self._token_state.state_block is not None
            and last_to <= self._token_state.state_block
        )
        if not compatible_core:
            return False
        self._store_core_fragment()
        core_entry = self.cache.get_last_good(GROUP_CORE)
        if core_entry is None:
            return False
        flow_rows = [
            row
            for row in core_entry.payload.get("network_flow_rows", ())
            if row.get("source_kind") == "chain_log"
        ]
        buyback_age = core_entry.payload.get("network_last_buyback_age_s")
        self.cache.store_last_good(
            GROUP_FLOW_LOGS,
            {
                "network_flow_rows": flow_rows,
                "network_flow_history_complete": history_complete,
                "network_flow_as_of_block": last_to,
                "network_flow_as_of_ts": last_observed,
                "network_flow_stale": not history_complete,
                "network_last_buyback_age_s": buyback_age,
            },
            ts=last_observed,
            block_number=last_to,
        )
        self._has_restored_flow_fragment = False
        return not page_failed

    async def _refresh_pullpool_logs(self, state_block: int) -> bool:
        if not PULLPOOL_LOG_STREAMS:
            return True
        if not self._pin_matches(state_block):
            return False
        stream = PULLPOOL_LOG_STREAMS[
            self._pull_stream_cursor % len(PULLPOOL_LOG_STREAMS)
        ]
        key = stream.watermark_key
        coverage = (
            None
            if self._pull_history is None
            else self._pull_history.coverage_for(key)
        )
        coverage_end = (
            None
            if coverage is None or not coverage.ranges
            else coverage.ranges[-1].through_block
        )
        resumed = await self._resume_start(
            key,
            stream.manifest.deployment_block,
            coverage_end,
            expected_state_block=state_block,
        )
        if resumed is None:
            if self._pin_matches(state_block):
                self._pull_stream_cursor += 1
            return False
        if not self._pin_matches(state_block):
            return False
        start, reorged = resumed
        end = min(start + self._page_blocks * self._pages_per_cycle - 1, state_block)
        if start > state_block:
            self._pull_stream_cursor += 1
            return True
        saved = self.cache.get_watermark(key)
        aligned = saved is None or (
            coverage_end is not None and coverage_end >= saved.block_number
        )
        kwargs: dict[str, Any] = {
            "history_complete": False,
            "stream_keys": (key,),
        }
        if aligned:
            # The adapter may reconcile a supplied cache while awaiting its
            # own hash read.  Pass a frozen cursor mapping so an old cycle can
            # never mutate manager-owned persistence before the pin guard.
            kwargs["watermarks"] = {} if saved is None else {key: saved}
        else:
            kwargs["watermarks"] = {}
        read = await self.pullpool.fetch_logs(start, end, **kwargs)
        if not self._pin_matches(state_block):
            return False
        self._pull_stream_cursor += 1
        all_progress = tuple(getattr(read, "progress", ()))
        progress_rows = all_progress[: self._pages_per_cycle]
        complete_pages: list[Any] = []
        next_page_start = start
        for progress in progress_rows:
            page_hash = _block_hash(progress.last_block_hash)
            valid_bounds = bool(
                progress.watermark_key == key
                and progress.from_block == next_page_start
                and progress.from_block <= progress.to_block <= end
            )
            if not progress.page_complete or page_hash is None or not valid_bounds:
                break
            complete_pages.append(progress)
            next_page_start = progress.to_block + 1

        history_streams = tuple(
            scan.model_copy(update={"reorged": True})
            if reorged and getattr(scan, "watermark_key", None) == key
            else scan
            for scan in read.streams
        )
        history_read = read.model_copy(
            update={
                "progress": tuple(complete_pages),
                "streams": history_streams,
            }
        )
        next_history = accumulate_pullpool_history(
            self._pull_history, history_read, cache=None
        )
        integrity = self._matching_integrity(
            self._pull_integrity, state_block
        )
        rows = normalize_pullpool_events(
            history_read, integrity=integrity, stale=False
        )
        if not self._pin_matches(state_block):
            return False

        self._pull_history = next_history
        for progress in complete_pages:
            page_hash = _block_hash(progress.last_block_hash)
            assert page_hash is not None
            self._advance_watermark(
                progress.watermark_key,
                block_number=progress.to_block,
                block_hash=page_hash,
                ts=float(read.observed_at),
                deployment_block=stream.manifest.deployment_block,
            )
        scan_reorged = any(
            getattr(scan, "watermark_key", None) == key
            and getattr(scan, "reorged", False)
            for scan in history_read.streams
        )
        for index, progress in enumerate(complete_pages):
            page_rows = tuple(
                row
                for row in rows
                if isinstance(row.get("block_number"), int)
                and progress.from_block
                <= row["block_number"]
                <= progress.to_block
            )
            self._replace_events(
                page_rows,
                address=stream.manifest.address,
                from_block=progress.from_block,
                to_block=progress.to_block,
                reorged=bool(scan_reorged and index == 0),
            )
        if (
            self._pull_state is not None
            and self._pull_state.block_number == state_block
        ):
            project_rows = build_pullpool_rows(
                self._pull_state,
                history=self._pull_history,
                integrity=self._matching_integrity(
                    self._pull_integrity, self._pull_state.block_number
                ),
            )
            self._store_project_fragment(
                GROUP_PULLPOOL,
                project_rows,
                self._pull_state.observed_at,
                self._pull_state.block_number,
            )
        matching_scans = tuple(
            scan
            for scan in read.streams
            if getattr(scan, "watermark_key", None) == key
        )
        complete_through = max(
            (
                scan.complete_through_block
                for scan in matching_scans
                if scan.complete_through_block is not None
            ),
            default=None,
        )
        return bool(
            read.available
            and not read.failed_streams
            and progress_rows
            and len(all_progress) == len(progress_rows)
            and len(progress_rows) == len(complete_pages)
            and next_page_start > end
            and complete_through is not None
            and complete_through >= end
        )

    async def _refresh_megarip_logs(self, state_block: int) -> bool:
        if not MEGARIP_MANIFESTS:
            return True
        if not self._pin_matches(state_block):
            return False
        all_ok = True
        for offset in range(self._pages_per_cycle):
            manifest = MEGARIP_MANIFESTS[
                (self._mega_stream_cursor + offset) % len(MEGARIP_MANIFESTS)
            ]
            key = WatermarkKey("megarip", manifest.version, "lifecycle")
            resumed = await self._resume_start(
                key,
                manifest.deployment_block,
                self._project_coverage_end.get(key),
                expected_state_block=state_block,
            )
            if resumed is None or not self._pin_matches(state_block):
                all_ok = False
                continue
            start, reorged = resumed
            end = min(start + self._page_blocks - 1, state_block)
            if start > state_block:
                continue
            read = await self.megarip.fetch_events(
                manifest.version,
                from_block=start,
                to_block=end,
                history_complete=False,
            )
            if not self._pin_matches(state_block):
                return False
            page_hash = _block_hash(read.last_complete_block_hash)
            complete = bool(read.available and read.page_complete and page_hash)
            if complete:
                self._advance_watermark(
                    key,
                    block_number=end,
                    block_hash=page_hash,
                    ts=float(read.observed_at),
                    deployment_block=manifest.deployment_block,
                )
                self._replace_events(
                    read.events,
                    address=manifest.address,
                    from_block=start,
                    to_block=end,
                    reorged=reorged,
                )
                self._project_coverage_end[key] = end
            else:
                all_ok = False
        self._mega_stream_cursor = (
            self._mega_stream_cursor + self._pages_per_cycle
        ) % len(MEGARIP_MANIFESTS)
        return all_ok

    async def _refresh_fwap_logs(self, state_block: int) -> bool:
        if self.fwap_logs is None:
            return False
        if not self._pin_matches(state_block):
            return False
        streams: list[tuple[Any, tuple[str, ...]]] = []
        for manifest in FWAP_MANIFESTS:
            topics = tuple(
                spec.topic0
                for spec in FWAP_EVENT_SPECS
                if spec.manifest.address == manifest.address
            )
            if topics:
                streams.append((manifest, topics))
        if not streams:
            return True
        all_ok = True
        for offset in range(self._pages_per_cycle):
            manifest, topics = streams[
                (self._fwap_stream_cursor + offset) % len(streams)
            ]
            key = WatermarkKey("fwap", manifest.version, manifest.role)
            resumed = await self._resume_start(
                key,
                manifest.deployment_block,
                self._project_coverage_end.get(key),
                expected_state_block=state_block,
            )
            if resumed is None or not self._pin_matches(state_block):
                all_ok = False
                continue
            start, reorged = resumed
            end = min(start + self._page_blocks - 1, state_block)
            if start > state_block:
                continue
            page = await self._fetch_fwap_page(
                manifest.address, topics, start, end
            )
            if not self._pin_matches(state_block):
                return False
            valid = self._validate_fwap_page(
                page.logs, manifest.address, start, end
            )
            hash_value = _block_hash(page.block_hash) or await self._read_block_hash(end)
            if not self._pin_matches(state_block):
                return False
            decoded = (
                None
                if valid is None
                else decode_fwap_events(valid, _finite_now(self._clock))
            )
            decode_complete = bool(
                decoded is not None and len(decoded.events) == len(valid or ())
            )
            complete = bool(
                page.page_complete and decode_complete and hash_value
            )
            if complete:
                observed_at = _finite_now(self._clock)
                assert decoded is not None
                rows = normalize_fwap_events(
                    decoded,
                    integrity=self._matching_integrity(
                        self._fwap_integrity, state_block
                    ),
                    stale=False,
                )
                self._advance_watermark(
                    key,
                    block_number=end,
                    block_hash=hash_value,
                    ts=observed_at,
                    deployment_block=manifest.deployment_block,
                )
                self._replace_events(
                    rows,
                    address=manifest.address,
                    from_block=start,
                    to_block=end,
                    reorged=reorged,
                )
                self._project_coverage_end[key] = end
            else:
                all_ok = False
        self._fwap_stream_cursor = (
            self._fwap_stream_cursor + self._pages_per_cycle
        ) % len(streams)
        return all_ok

    async def _fetch_fwap_page(
        self,
        address: str,
        topics: Sequence[str],
        from_block: int,
        to_block: int,
    ) -> FWAPLogPage:
        method = getattr(self.fwap_logs, "fetch_page", None)
        if method is None:
            method = getattr(self.fwap_logs, "fetch_logs", None)
        if not callable(method):
            raise TypeError("fwap_log_source must expose fetch_page()")
        raw = method(
            address=address,
            topics=topics,
            from_block=from_block,
            to_block=to_block,
        )
        if inspect.isawaitable(raw):
            raw = await raw
        if isinstance(raw, FWAPLogPage):
            return raw
        if isinstance(raw, Mapping):
            logs = raw.get("logs", ())
            return FWAPLogPage(
                logs=tuple(logs) if isinstance(logs, Sequence) else (),
                block_hash=_block_hash(raw.get("block_hash")),
                page_complete=raw.get("page_complete") is not False,
            )
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            return FWAPLogPage(logs=tuple(raw))
        raise TypeError("FWAP log page must be a sequence or FWAPLogPage")

    @staticmethod
    def _validate_fwap_page(
        logs: Sequence[Any], address: str, from_block: int, to_block: int
    ) -> tuple[Mapping[str, Any], ...] | None:
        valid: list[Mapping[str, Any]] = []
        for raw in logs:
            if not isinstance(raw, Mapping):
                return None
            if str(raw.get("address") or "").lower() != address:
                return None
            number = raw.get("blockNumber")
            if isinstance(number, str):
                try:
                    number = int(number, 16)
                except ValueError:
                    return None
            if (
                isinstance(number, bool)
                or not isinstance(number, int)
                or not from_block <= number <= to_block
            ):
                return None
            valid.append(raw)
        return tuple(valid)

    async def _resume_start(
        self,
        key: WatermarkKey,
        deployment_block: int,
        coverage_end: int | None,
        *,
        expected_state_block: int | None = None,
    ) -> tuple[int, bool] | None:
        """Return a canonical start only when cursor and accumulator agree.

        A persisted watermark without the corresponding in-memory accumulator
        is intentionally ignored: the scan restarts at deployment.  Once the
        accumulator covers the watermark, its saved hash must be readable
        before a tail/overlap can resume.
        """

        watermark = self.cache.get_watermark(key)
        if coverage_end is None:
            return deployment_block, False
        if watermark is None or coverage_end < watermark.block_number:
            return max(
                deployment_block,
                coverage_end + 1 - self._reorg_overlap,
            ), False
        live_hash = await self._read_block_hash(watermark.block_number)
        if (
            expected_state_block is not None
            and not self._pin_matches(expected_state_block)
        ):
            return None
        if live_hash is None:
            return None
        reorged = self.cache.reconcile_block_hash(
            key, live_hash, deployment_block=deployment_block
        )
        return (
            self.cache.scan_start(key, deployment_block=deployment_block),
            reorged,
        )

    def _advance_watermark(
        self,
        key: WatermarkKey,
        *,
        block_number: int,
        block_hash: str,
        ts: float,
        deployment_block: int,
    ) -> None:
        """Advance only canonical complete pages; never jump a restored cursor."""

        previous = self.cache.get_watermark(key)
        if previous is not None and block_number < previous.block_number:
            return
        if (
            previous is not None
            and block_number == previous.block_number
            and previous.block_hash != block_hash
        ):
            self.cache.reconcile_block_hash(
                key, block_hash, deployment_block=deployment_block
            )
        self.cache.set_watermark(
            key,
            block_number=block_number,
            block_hash=block_hash,
            overlap=self._reorg_overlap,
            page_complete=True,
            ts=ts,
        )

    def _drop_flow_range(self, from_block: int, to_block: int | None) -> None:
        def kept(block_number: int) -> bool:
            if block_number < from_block:
                return True
            return to_block is not None and block_number > to_block

        self._flow_buybacks = {
            key: event
            for key, event in self._flow_buybacks.items()
            if kept(event.block_number)
        }
        self._flow_burns = {
            key: event
            for key, event in self._flow_burns.items()
            if kept(event.block_number)
        }

    async def _read_block_hash(self, block_number: int) -> str | None:
        reader = self.block_hash_reader
        if reader is None:
            return None
        if callable(reader):
            value = reader(block_number)
        else:
            method = getattr(reader, "fetch_block_hash", None)
            if method is None:
                method = getattr(reader, "block_hash", None)
            if not callable(method):
                return None
            value = method(block_number)
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, Mapping):
            value = value.get("hash")
        return _block_hash(value)

    # -- normalized publication ------------------------------------------

    def _merge_events(self, rows: Sequence[Any]) -> None:
        source_rank = {"market_api": 0, "project_api": 1, "chain_state": 2, "chain_log": 3}
        for raw in rows:
            row = NetworkEventRow.model_validate(_row_dict(raw)).model_dump()
            if tuple(row) != NETWORK_EVENT_ROW_KEYS:
                raise ValueError("event row key order drift")
            event_id = row["event_id"]
            previous = self._events.get(event_id)
            if previous is None:
                self._events[event_id] = row
                continue
            old_rank = source_rank.get(str(previous.get("source_kind")), -1)
            new_rank = source_rank.get(str(row.get("source_kind")), -1)
            if new_rank > old_rank or (
                new_rank == old_rank
                and bool(previous.get("stale"))
                and not bool(row.get("stale"))
            ):
                self._events[event_id] = row
        if len(self._events) > self._event_limit * 2:
            retained = sorted(
                self._events.values(), key=_event_sort_key, reverse=True
            )[: self._event_limit]
            self._events = {row["event_id"]: row for row in retained}

    def _replace_events(
        self,
        rows: Sequence[Any],
        *,
        address: str,
        from_block: int,
        to_block: int,
        reorged: bool,
    ) -> None:
        prefix = f"1:{address.lower()}:"
        retained: dict[str, dict[str, Any]] = {}
        for event_id, row in self._events.items():
            block_number = row.get("block_number")
            in_replacement = bool(
                event_id.lower().startswith(prefix)
                and isinstance(block_number, int)
                and block_number >= from_block
                and (reorged or block_number <= to_block)
            )
            if not in_replacement:
                retained[event_id] = row
        self._events = retained
        self._merge_events(rows)

    async def _store_event_fragment(
        self,
        now: float,
        *,
        state_block: int,
        successful_sources: set[str],
    ) -> None:
        # Fresh peers publish even while another adapter is down.  Restored
        # presentation rows stay visibly stale until full accumulated coverage
        # proves them again; they never seed the canonical event accumulator.
        self._project_log_failed.difference_update(successful_sources)
        combined = deepcopy(self._restored_events)
        for event_id, raw in self._events.items():
            row = dict(raw)
            source = self._event_adapter(row)
            row["stale"] = bool(
                row.get("stale") or source in self._project_log_failed
            )
            combined[event_id] = row
        if self._project_history_caught_up(state_block):
            restored_ids = set(self._restored_events)
            self._restored_events.clear()
            self._has_restored_event_fragment = False
            combined = {
                event_id: row
                for event_id, row in combined.items()
                if event_id not in restored_ids or event_id in self._events
            }
        rows = sorted(combined.values(), key=_event_sort_key, reverse=True)[
            : self._event_limit
        ]
        latest_block = max(
            (
                int(row["block_number"])
                for row in rows
                if isinstance(row.get("block_number"), int)
                and not isinstance(row.get("block_number"), bool)
            ),
            default=None,
        )
        self.cache.store_last_good(
            GROUP_PROJECT_LOGS,
            {
                "network_events": rows,
                "network_feed_available": True,
                "network_feed_unavailable_reason": (
                    None
                    if not self._project_log_failed
                    else "partial: " + ", ".join(sorted(self._project_log_failed))
                ),
                "network_feed_as_of_ts": now,
            },
            ts=now,
            block_number=latest_block,
        )

    @staticmethod
    def _event_adapter(row: Mapping[str, Any]) -> str:
        family = str(row.get("family") or "")
        if family == "megarip":
            return "megarip"
        if family == "fwap":
            return "fwap"
        return "pullpool"

    def _project_history_caught_up(self, state_block: int) -> bool:
        if self._pull_history is None:
            return False
        if any(
            not self._pull_history.covers(stream.watermark_key, state_block)
            for stream in PULLPOOL_LOG_STREAMS
        ):
            return False
        for manifest in MEGARIP_MANIFESTS:
            key = WatermarkKey("megarip", manifest.version, "lifecycle")
            if self._project_coverage_end.get(key, -1) < state_block:
                return False
        for manifest in FWAP_MANIFESTS:
            if not any(
                spec.manifest.address == manifest.address for spec in FWAP_EVENT_SPECS
            ):
                continue
            key = WatermarkKey("fwap", manifest.version, manifest.role)
            if self._project_coverage_end.get(key, -1) < state_block:
                return False
        return True

    async def _commit_from_groups(self) -> None:
        async with self._commit_lock:
            payload = self._assemble_payload(_finite_now(self._clock))
            if payload is None:
                return
            self.cache.commit_snapshot(payload, ts=_finite_now(self._clock))
            if self._persist_cache:
                self.cache.save()

    def _assemble_payload(self, now: float) -> dict[str, Any] | None:
        entries = {
            group: self.cache.get_last_good(group)
            for group in (
                GROUP_CORE,
                GROUP_FLOW_LOGS,
                GROUP_DROPS,
                GROUP_PULLPOOL,
                GROUP_MEGARIP,
                GROUP_FWAP,
                GROUP_PROJECT_LOGS,
                GROUP_INTEGRITY,
            )
        }
        if not any(entries[group] is not None for group in _DIRECT_GROUPS):
            return None

        payload: dict[str, Any] = {
            key: None for key in FWA_NETWORK_DATA_KEYS
        }
        payload.update(
            {
                "network_ready": True,
                "network_chain_head": self._last_chain_head,
                "network_state_stale": True,
                "network_flow_rows": [],
                "network_flow_available": False,
                "network_flow_history_complete": False,
                "network_flow_stale": True,
                "network_drop_rows": [],
                "network_drops_available": False,
                "network_drops_stale": True,
                "network_project_rows": [],
                "network_projects_available": False,
                "network_projects_stale": True,
                "network_events": [],
                "network_feed_available": False,
                "network_feed_unavailable_reason": "project logs unavailable",
                "network_degraded_sources": [],
                "network_integrity_warning_count": None,
                "network_error_count": self._error_count,
            }
        )

        core = entries[GROUP_CORE]
        core_stale = self._entry_stale(GROUP_CORE, core, TIER_FAST, now)
        if core is not None:
            payload.update(deepcopy(core.payload))
            payload["network_state_stale"] = core_stale
            age = payload.get("network_last_buyback_age_s")
            if isinstance(age, float):
                payload["network_last_buyback_age_s"] = age + core.age_seconds(now)
        if self._last_chain_head is not None:
            payload["network_chain_head"] = self._last_chain_head

        flow = entries[GROUP_FLOW_LOGS]
        flow_stale = self._entry_stale(
            GROUP_FLOW_LOGS, flow, TIER_MEDIUM, now
        )
        if flow is not None:
            flow_payload = deepcopy(flow.payload)
            saved_flow_rows = flow_payload.pop("network_flow_rows", [])
            state_rows = {
                row.get("key"): row for row in payload["network_flow_rows"]
            }
            for row in saved_flow_rows:
                state_rows[row.get("key")] = row
            payload["network_flow_rows"] = [
                state_rows[key]
                for key in (
                    row.get("key") for row in payload["network_flow_rows"]
                )
                if key in state_rows
            ]
            payload.update(flow_payload)
            age = payload.get("network_last_buyback_age_s")
            if isinstance(age, float):
                payload["network_last_buyback_age_s"] = age + flow.age_seconds(now)
        if (
            core is not None
            and self._state_block is not None
            and core.block_number != self._state_block
        ):
            flow_stale = True
        payload["network_flow_stale"] = bool(
            core_stale
            or flow_stale
            or payload["network_flow_history_complete"] is not True
        )
        payload["network_flow_rows"] = self._mark_rows_stale(
            payload["network_flow_rows"],
            state_stale=core_stale,
            log_stale=flow_stale,
        )

        drops = entries[GROUP_DROPS]
        drops_stale = self._entry_stale(GROUP_DROPS, drops, TIER_FAST, now)
        if drops is not None:
            payload.update(deepcopy(drops.payload))
            payload["network_drops_stale"] = drops_stale
            payload["network_drop_rows"] = self._set_rows_stale(
                payload["network_drop_rows"], drops_stale
            )

        project_rows: list[dict[str, Any]] = []
        project_blocks: list[int] = []
        project_stale = False
        any_project = False
        for group in _PROJECT_GROUPS:
            entry = entries[group]
            stale = self._entry_stale(group, entry, TIER_FAST, now)
            project_stale = project_stale or stale
            if entry is None:
                continue
            any_project = True
            if entry.block_number is not None:
                project_blocks.append(entry.block_number)
            project_rows.extend(
                self._set_rows_stale(
                    entry.payload.get("network_project_rows", ()), stale
                )
            )
        payload["network_project_rows"] = self._dedupe_project_rows(project_rows)
        payload["network_projects_available"] = any_project
        payload["network_projects_as_of_block"] = (
            min(project_blocks) if project_blocks else None
        )
        payload["network_projects_stale"] = project_stale

        events = entries[GROUP_PROJECT_LOGS]
        event_age_stale = bool(
            events is None
            or events.age_seconds(now) >= TIER_TTL_SECONDS[TIER_MEDIUM]
        )
        if events is not None:
            payload.update(deepcopy(events.payload))
            event_rows: list[dict[str, Any]] = []
            for raw in payload["network_events"]:
                row = _row_dict(raw)
                source_failed = (
                    self._event_adapter(row) in self._project_log_failed
                )
                row["stale"] = bool(
                    row.get("stale") or event_age_stale or source_failed
                )
                event_rows.append(row)
            payload["network_events"] = self._dedupe_events(event_rows)
            if _PROJECT_LOG_SOURCES <= self._project_log_failed:
                payload["network_feed_unavailable_reason"] = (
                    "partial: " + ", ".join(sorted(_PROJECT_LOG_SOURCES))
                )

        self._apply_project_counts(payload)
        integrity = entries[GROUP_INTEGRITY]
        if integrity is not None:
            payload.update(deepcopy(integrity.payload))
        degraded = {
            group
            for group, tier in (
                (GROUP_CORE, TIER_FAST),
                (GROUP_FLOW_LOGS, TIER_MEDIUM),
                (GROUP_DROPS, TIER_FAST),
                (GROUP_PULLPOOL, TIER_FAST),
                (GROUP_MEGARIP, TIER_FAST),
                (GROUP_FWAP, TIER_FAST),
                (GROUP_PROJECT_LOGS, TIER_MEDIUM),
                (GROUP_INTEGRITY, TIER_INTEGRITY),
            )
            if self._entry_stale(group, entries[group], tier, now)
        }
        degraded.update(self._failed_groups)
        payload["network_degraded_sources"] = sorted(degraded)
        successful_times = [
            entry.ts for entry in entries.values() if entry is not None
        ]
        payload["network_last_updated_seconds_ago"] = float(
            max(0.0, now - max(successful_times)) if successful_times else 0.0
        )
        payload["network_error_count"] = self._error_count
        return {key: payload[key] for key in FWA_NETWORK_DATA_KEYS}

    def _entry_stale(self, group: str, entry: Any, tier: str, now: float) -> bool:
        return bool(
            entry is None
            or group in self._failed_groups
            or entry.age_seconds(now) >= TIER_TTL_SECONDS[tier]
        )

    @staticmethod
    def _set_rows_stale(rows: Sequence[Any], stale: bool) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for raw in rows:
            row = _row_dict(raw)
            row["stale"] = bool(stale or row.get("stale"))
            output.append(row)
        return output

    @staticmethod
    def _mark_rows_stale(
        rows: Sequence[Any], *, state_stale: bool, log_stale: bool
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for raw in rows:
            row = _row_dict(raw)
            stale = log_stale if row.get("source_kind") == "chain_log" else state_stale
            row["stale"] = bool(stale or row.get("stale"))
            output.append(row)
        return output

    @staticmethod
    def _dedupe_project_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        rank = {"market_api": 0, "project_api": 1, "chain_log": 2, "chain_state": 3}
        selected: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            if not _visible_legacy(row):
                continue
            identity = (
                row.get("family"),
                row.get("surface"),
                row.get("version"),
                str(row.get("address") or "").lower(),
            )
            old = selected.get(identity)
            if old is None or rank.get(str(row.get("source_kind")), -1) > rank.get(
                str(old.get("source_kind")), -1
            ):
                selected[identity] = row
        family_rank = {
            "pullpool": 0,
            "group_pull": 1,
            "standing_orders": 2,
            "megarip": 3,
            "fwap": 4,
        }
        return sorted(
            selected.values(),
            key=lambda row: (
                family_rank.get(str(row.get("family")), 99),
                0 if row.get("is_current") else 1,
                str(row.get("surface")),
                str(row.get("version")),
            ),
        )

    def _dedupe_events(self, rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        rank = {"market_api": 0, "project_api": 1, "chain_state": 2, "chain_log": 3}
        for row in rows:
            event_id = row.get("event_id")
            if not isinstance(event_id, str):
                continue
            old = selected.get(event_id)
            if old is None or rank.get(str(row.get("source_kind")), -1) > rank.get(
                str(old.get("source_kind")), -1
            ):
                selected[event_id] = row
        return sorted(selected.values(), key=_event_sort_key, reverse=True)[
            : self._event_limit
        ]

    @staticmethod
    def _apply_project_counts(payload: dict[str, Any]) -> None:
        if payload.get("network_projects_available") is not True:
            return
        current = [
            row for row in payload["network_project_rows"] if row.get("is_current") is True
        ]
        payload["network_project_family_count"] = len(
            {row.get("family") for row in current}
        )
        healthy = degraded = unverified = 0
        for row in current:
            if row.get("verified_source") is not True or row.get("source_badge") == "CHAIN-READ":
                unverified += 1
            elif (
                row.get("integrity") != "ok"
                or row.get("source_badge") != "VERIFIED"
                or row.get("stale") is True
            ):
                degraded += 1
            else:
                healthy += 1
        payload["network_project_healthy_count"] = healthy
        payload["network_project_degraded_count"] = degraded
        payload["network_project_unverified_count"] = unverified

    def _integrity_warning_count(self, payload: Mapping[str, Any] | None = None) -> int:
        if payload is None:
            payload = self._assemble_rows_only()
        count = 0
        for row in payload.get("network_flow_rows", ()):
            if not isinstance(row, Mapping) or row.get("key") != "official_integrity":
                continue
            value = row.get("value")
            if isinstance(value, int) and not isinstance(value, bool):
                count += value
            elif row.get("integrity") == "mismatch":
                count += 1
        for key in ("network_drop_rows", "network_project_rows"):
            count += sum(
                isinstance(row, Mapping)
                and row.get("integrity") in {"warning", "mismatch"}
                for row in payload.get(key, ())
            )
        return count

    def _assemble_rows_only(self) -> dict[str, Any]:
        rows: dict[str, Any] = {
            "network_flow_rows": [],
            "network_drop_rows": [],
            "network_project_rows": [],
        }
        core = self.cache.get_last_good(GROUP_CORE)
        drops = self.cache.get_last_good(GROUP_DROPS)
        if core is not None:
            rows["network_flow_rows"] = core.payload.get("network_flow_rows", [])
        if drops is not None:
            rows["network_drop_rows"] = drops.payload.get("network_drop_rows", [])
        for group in _PROJECT_GROUPS:
            entry = self.cache.get_last_good(group)
            if entry is not None:
                rows["network_project_rows"].extend(
                    entry.payload.get("network_project_rows", [])
                )
        return rows

    def _current_state_block(self) -> int | None:
        return self._state_block

    def _pin_matches(self, block_number: int) -> bool:
        return bool(
            not self._closed
            and self._cycle_pin_valid
            and self._current_state_block() == block_number
        )

    def _visible_snapshot(self) -> dict[str, Any]:
        snapshot = self.cache.latest_snapshot()
        if snapshot is None:
            return blank_network_payload()
        payload = deepcopy(snapshot.payload)
        now = _finite_now(self._clock)
        successful_times = [
            entry.ts
            for group in (
                GROUP_CORE,
                GROUP_FLOW_LOGS,
                GROUP_DROPS,
                GROUP_PULLPOOL,
                GROUP_MEGARIP,
                GROUP_FWAP,
                GROUP_PROJECT_LOGS,
                GROUP_INTEGRITY,
            )
            if (entry := self.cache.get_last_good(group)) is not None
        ]
        payload["network_last_updated_seconds_ago"] = float(
            max(0.0, now - max(successful_times))
            if successful_times
            else snapshot.age_seconds(now)
        )
        return {key: payload[key] for key in FWA_NETWORK_DATA_KEYS}

    async def _bounded(self, awaitable: Awaitable[Any], timeout: float) -> Any:
        return await asyncio.wait_for(awaitable, timeout=timeout)

    def _record_failure(self, *groups: str, error: BaseException) -> None:
        self._error_count += 1
        self._failed_groups.update(groups)
        logger.debug("FWA source %s failed: %s", ",".join(groups), error)


__all__ = [
    "API_REQUEST_TIMEOUT",
    "BACKGROUND_REQUEST_TIMEOUT",
    "EVENT_LIMIT",
    "FAST_REQUEST_TIMEOUT",
    "FWAEcosystemManager",
    "FWAPLogPage",
    "FWAPLogSource",
    "LOG_PAGE_BLOCKS",
    "LOG_PAGES_PER_CYCLE",
    "REORG_OVERLAP",
]
