"""Concurrency, paging, and restart budgets for FWA NETWORK refreshes."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest

import maxpane_dashboard.data.fwa_ecosystem_manager as manager_module
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    FWAEcosystemCache,
    GROUP_FLOW_LOGS,
    GROUP_FWAP,
    GROUP_INTEGRITY,
    GROUP_PROJECT_LOGS,
    GROUP_PULLPOOL,
    TIER_API,
    TIER_FAST,
    TIER_INTEGRITY,
    TIER_MEDIUM,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_manager import (
    FWAEcosystemManager,
    FWAPLogPage,
)
from maxpane_dashboard.data.fwa_ecosystem_models import NetworkEventRow, ProjectRow
from maxpane_dashboard.data.fwa_projects.pullpool import (
    LOG_STREAMS,
    LOG_STREAM_BY_KEY,
    LogProgress,
    LogStreamRead,
    PullPoolLogRead,
)
from maxpane_dashboard.data.fwa_tokenomics_client import (
    BuybackEvent,
    TokenomicsLogRead,
)
from tests.data.test_fwa_ecosystem_manager import (
    BLOCK,
    NOW,
    _Closable,
    _fresh_background,
    _manager,
    _project_row,
)


HASH = "0x" + "ab" * 32


class _CoreIntegrity(SimpleNamespace):
    def status_for(self, *roles: str) -> str:
        checks = [self.codehash_matches.get(role) for role in roles]
        checks.extend(
            value
            for role in roles
            for key, value in self.dependency_matches.items()
            if key.startswith(role + ".")
        )
        if any(value is False for value in checks):
            return "mismatch"
        if not checks or any(value is None for value in checks):
            return "unknown"
        return "ok"


class _PullIntegrity(SimpleNamespace):
    def status_for(self, manifest) -> str:
        for surface in self.surfaces:
            if surface.address.lower() == manifest.address.lower():
                return surface.status
        return "unknown"


class _FWAPIntegrity(SimpleNamespace):
    def status_for_version(self, version: str) -> str:
        statuses = [
            surface.status
            for surface in self.surfaces
            if surface.version == version
        ]
        if "mismatch" in statuses:
            return "mismatch"
        if not statuses or "unknown" in statuses:
            return "unknown"
        if "warning" in statuses:
            return "warning"
        return "ok"


def _core_integrity(
    block_number: int,
    *,
    complete: bool,
    mismatch: bool = False,
    mismatch_role: str = "core",
) -> _CoreIntegrity:
    roles = [item.role for item in manager_module.OFFICIAL_DEPLOYMENTS]
    dependency_keys = [
        item.key for item in manager_module.TOKENOMICS_DEPENDENCIES
    ]
    codehashes = {role: True for role in roles}
    dependencies = {key: True for key in dependency_keys}
    if mismatch:
        codehashes[mismatch_role] = False
    if not complete:
        codehashes = {
            "core": codehashes["core"],
            "token": codehashes["token"],
        }
        dependencies = {}
    return _CoreIntegrity(
        observed_at=NOW,
        block_number=block_number,
        codehash_matches=codehashes,
        dependency_matches=dependencies,
    )


def _project_integrity(
    label: str,
    block_number: int,
    *,
    complete: bool,
    mismatch: bool = False,
    mismatch_index: int = 0,
):
    manifests = (
        manager_module.PULLPOOL_MANIFESTS
        if label == "pullpool"
        else manager_module.FWAP_MANIFESTS
    )
    selected = manifests if complete else (manifests[0], manifests[-1])
    surfaces = []
    for index, manifest in enumerate(selected):
        bad = mismatch and index == mismatch_index
        surfaces.append(
            SimpleNamespace(
                version=manifest.version,
                address=manifest.address,
                block_number=block_number,
                codehash_match=not bad,
                dependency_matches=tuple(
                    (getter, True) for getter, _expected in manifest.dependencies
                ),
                status="mismatch" if bad else "ok",
            )
        )
    result_type = _PullIntegrity if label == "pullpool" else _FWAPIntegrity
    return result_type(
        observed_at=NOW,
        block_number=block_number,
        surfaces=tuple(surfaces),
    )


def _unknown_integrity(label: str, block_number: int):
    if label == "core":
        return _CoreIntegrity(
            observed_at=NOW,
            block_number=block_number,
            codehash_matches={},
            dependency_matches={},
        )
    result_type = _PullIntegrity if label == "pullpool" else _FWAPIntegrity
    return result_type(
        observed_at=NOW,
        block_number=block_number,
        surfaces=(),
    )


def _event(
    *,
    address: str,
    block_number: int,
    log_index: int,
    source_kind: str = "chain_log",
    family: str = "test",
) -> dict:
    tx_hash = "0x" + f"{block_number:064x}"
    return NetworkEventRow(
        event_id=f"1:{address.lower()}:{tx_hash}:{log_index}",
        ts=float(block_number),
        tx_hash=tx_hash,
        log_index=log_index,
        origin="test",
        family=family,
        version="v1",
        event_key="test",
        event_label="Test",
        eth_amount=None,
        fwa_amount=None,
        detail="",
        source_kind=source_kind,
        measurement="measured",
        block_number=block_number,
        observed_at=NOW,
        stale=False,
        verified_source=True,
        integrity="ok",
    ).model_dump()


def _complete_flow_fragment(
    payload: dict, *, observed_at: float, block_number: int
) -> dict:
    row = next(
        dict(item)
        for item in payload["network_flow_rows"]
        if item["key"] == "buyback_swap_eth"
    )
    row.update(value=5.0, observed_at=observed_at, stale=False)
    return {
        "network_flow_rows": [row],
        "network_flow_history_complete": True,
        "network_flow_as_of_block": block_number,
        "network_flow_as_of_ts": observed_at,
        "network_flow_stale": False,
        "network_last_buyback_age_s": 10.0,
    }


async def test_medium_cycle_enforces_two_pages_and_5000_blocks_per_page(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, pull, mega, _fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager.block_hash_reader = lambda _block: HASH
    flow_ranges: list[tuple[int, int]] = []
    pull_ranges: list[tuple[int, int]] = []
    mega_ranges: list[tuple[int, int]] = []
    fwap_ranges: list[tuple[int, int]] = []

    async def fetch_flow(_self, from_block, to_block, *, history_complete):
        assert history_complete is False
        flow_ranges.append((from_block, to_block))
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=(),
            burns=(),
        )

    async def fetch_pull(
        _self,
        from_block,
        to_block,
        *,
        history_complete,
        stream_keys,
        **_kwargs,
    ):
        assert history_complete is False
        pull_ranges.append((from_block, to_block))
        key = stream_keys[0]
        stream = LOG_STREAM_BY_KEY[key]
        split = min(from_block + 4_999, to_block)
        pages = [(from_block, split)]
        if split < to_block:
            pages.append((split + 1, to_block))
        progress = tuple(
            LogProgress(
                adapter=key.adapter,
                version=key.version,
                topic_group=key.topic_group,
                from_block=start,
                to_block=end,
                last_block_hash=HASH,
                page_complete=True,
                overlap=64,
            )
            for start, end in pages
        )
        return PullPoolLogRead(
            observed_at=clock(),
            requested_from_block=from_block,
            requested_to_block=to_block,
            available=True,
            history_complete=False,
            history_complete_versions=(),
            failed_streams=(),
            events=(),
            progress=progress,
            streams=(
                LogStreamRead(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    deployment_block=stream.manifest.deployment_block,
                    scan_from_block=from_block,
                    requested_to_block=to_block,
                    complete_through_block=to_block,
                    watermark_hash_match=None,
                    reorged=False,
                ),
            ),
        )

    async def fetch_mega(
        _self,
        version,
        *,
        from_block,
        to_block,
        history_complete,
        integrity,
    ):
        assert history_complete is False
        assert integrity == "unknown"
        mega_ranges.append((from_block, to_block))
        return SimpleNamespace(
            observed_at=clock(),
            version=version,
            available=True,
            page_complete=True,
            last_complete_block_hash=HASH,
            events=(),
        )

    class FwapLogs(_Closable):
        async def fetch_page(
            self, *, address, topics, from_block, to_block
        ):
            assert address and topics
            fwap_ranges.append((from_block, to_block))
            return FWAPLogPage(logs=(), block_hash=HASH)

    logs.fetch_flow_logs = MethodType(fetch_flow, logs)
    pull.fetch_logs = MethodType(fetch_pull, pull)
    mega.fetch_events = MethodType(fetch_mega, mega)
    manager.fwap_logs = FwapLogs()

    await manager._run_medium_cycle()

    assert len(flow_ranges) <= 2
    assert len(pull_ranges) == 1
    assert pull_ranges[0][1] - pull_ranges[0][0] + 1 <= 10_000
    assert len(mega_ranges) <= 2
    assert len(fwap_ranges) <= 2
    for start, end in [*flow_ranges, *mega_ranges, *fwap_ranges]:
        assert end - start + 1 <= 5_000
    await manager.close()


async def test_pullpool_partial_second_page_replaces_only_complete_first_page(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, pull, _mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    stream = LOG_STREAMS[0]
    start = stream.manifest.deployment_block
    first_end = start + 4_999
    second_start = first_end + 1
    requested_end = second_start + 4_999
    assert requested_end <= BLOCK
    old_first = _event(
        address=stream.manifest.address,
        block_number=start + 2,
        log_index=1,
        family="pullpool",
    )
    old_second = _event(
        address=stream.manifest.address,
        block_number=second_start + 2,
        log_index=2,
        family="pullpool",
    )
    replacement = _event(
        address=stream.manifest.address,
        block_number=start + 3,
        log_index=3,
        family="pullpool",
    )
    rejected = _event(
        address=stream.manifest.address,
        block_number=second_start + 3,
        log_index=4,
        family="pullpool",
    )
    manager._merge_events((old_first, old_second))

    async def fetch_pull(
        _self,
        from_block,
        to_block,
        *,
        history_complete,
        stream_keys,
        **_kwargs,
    ):
        assert from_block == start
        assert to_block == requested_end
        assert history_complete is False
        assert stream_keys == (stream.watermark_key,)
        key = stream.watermark_key
        return PullPoolLogRead(
            observed_at=clock(),
            requested_from_block=from_block,
            requested_to_block=to_block,
            available=False,
            history_complete=False,
            history_complete_versions=(),
            failed_streams=("pullpool:v2:lifecycle",),
            events=(),
            progress=(
                LogProgress(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    from_block=start,
                    to_block=first_end,
                    last_block_hash=HASH,
                    page_complete=True,
                    overlap=64,
                ),
                LogProgress(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    from_block=second_start,
                    to_block=requested_end,
                    last_block_hash=None,
                    page_complete=False,
                    overlap=64,
                ),
            ),
            streams=(
                LogStreamRead(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    deployment_block=start,
                    scan_from_block=start,
                    requested_to_block=requested_end,
                    complete_through_block=first_end,
                    watermark_hash_match=None,
                    reorged=False,
                ),
            ),
        )

    pull.fetch_logs = MethodType(fetch_pull, pull)
    monkeypatch.setattr(
        manager_module,
        "normalize_pullpool_events",
        lambda _read, **_kwargs: (replacement, rejected),
    )

    assert await manager._refresh_pullpool_logs(BLOCK) is False
    watermark = manager.cache.get_watermark(stream.watermark_key)
    assert watermark is not None
    assert watermark.block_number == first_end
    assert old_first["event_id"] not in manager._events
    assert replacement["event_id"] in manager._events
    assert old_second["event_id"] in manager._events
    assert rejected["event_id"] not in manager._events
    await manager.close()


async def test_flow_partial_second_page_keeps_progress_but_reports_failure(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, _pull, _mega, _fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager.block_hash_reader = lambda _block: HASH
    deployment_block = manager_module._TOKEN_DEPLOYMENT_BLOCK
    first_end = deployment_block + 4_999
    ranges: list[tuple[int, int]] = []

    async def fetch_flow(_self, from_block, to_block, *, history_complete):
        assert history_complete is False
        ranges.append((from_block, to_block))
        complete = len(ranges) == 1
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=complete,
            burns_available=complete,
            unavailable_reason=None if complete else "logs unavailable",
            buybacks=(),
            burns=(),
        )

    logs.fetch_flow_logs = MethodType(fetch_flow, logs)

    assert await manager._refresh_flow_logs(BLOCK) is False
    assert ranges == [
        (deployment_block, first_end),
        (first_end + 1, first_end + 5_000),
    ]
    watermark = manager.cache.get_watermark(manager_module._FLOW_WATERMARK)
    assert watermark is not None
    assert watermark.block_number == first_end
    assert manager._flow_coverage_end == first_end
    await manager.close()


@pytest.mark.parametrize(
    "incomplete_flag", ("buyback_decode_complete", "burn_decode_complete")
)
async def test_flow_decode_failure_holds_watermark_and_existing_activity(
    incomplete_flag, tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, _pull, _mega, _fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager._pages_per_cycle = 1
    manager.block_hash_reader = lambda _block: HASH
    deployment = manager_module._TOKEN_DEPLOYMENT_BLOCK
    old = _event(
        address=manager_module.FWA_TOKEN,
        block_number=deployment + 1,
        log_index=7,
        family="fwa",
    )
    manager._merge_events((old,))

    async def malformed(_self, from_block, to_block, *, history_complete):
        assert from_block == deployment
        assert history_complete is False
        flags = {
            "buyback_decode_complete": True,
            "burn_decode_complete": True,
        }
        flags[incomplete_flag] = False
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason="malformed log",
            buybacks=(),
            burns=(),
            **flags,
        )

    logs.fetch_flow_logs = MethodType(malformed, logs)

    assert await manager._refresh_flow_logs(BLOCK) is False
    assert manager.cache.get_watermark(manager_module._FLOW_WATERMARK) is None
    assert manager._flow_coverage_end is None
    assert old["event_id"] in manager._events
    await manager.close()


async def test_complete_flow_page_emits_fwa_buyback_activity(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, _pull, _mega, _fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager._pages_per_cycle = 1
    manager.block_hash_reader = lambda _block: HASH
    deployment = manager_module._TOKEN_DEPLOYMENT_BLOCK
    tx_hash = "0x" + "42" * 32
    buyback = BuybackEvent(
        block_number=deployment + 10,
        block_timestamp=int(clock()),
        observed_at=clock(),
        tx_hash=tx_hash,
        bought_log_index=3,
        routed_log_index=None,
        caller="0x" + "24" * 20,
        eth_spent_wei=2 * 10**18,
        amount_bought_wei=5 * 10**18,
        caller_reward_wei=10**17,
        to_depositors_wei=None,
        to_purchasers_wei=None,
        burned_wei=None,
    )

    async def complete(_self, from_block, to_block, *, history_complete):
        assert from_block == deployment
        assert history_complete is False
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=(buyback,),
            burns=(),
            buyback_decode_complete=True,
            burn_decode_complete=True,
        )

    logs.fetch_flow_logs = MethodType(complete, logs)

    assert await manager._refresh_flow_logs(BLOCK) is True
    rows = [row for row in manager._events.values() if row["family"] == "fwa"]
    assert len(rows) == 1
    assert rows[0]["event_key"] == "buyback"
    assert rows[0]["tx_hash"] == tx_hash
    assert rows[0]["eth_amount"] == 2.0
    assert rows[0]["fwa_amount"] == 5.0
    watermark = manager.cache.get_watermark(manager_module._FLOW_WATERMARK)
    assert watermark is not None and watermark.block_hash == HASH
    await manager.close()


async def test_fwair_manager_and_dynamic_child_use_pinned_integrity_and_cursors(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, drops, _pull, _mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    child = "0x" + "d7" * 20

    def drops_state(row_block: int):
        return SimpleNamespace(
            state_block=BLOCK,
            available=True,
            integrity="ok",
            rows=(
                {
                    "launch_address": child,
                    "block_number": row_block,
                    "integrity": "warning",
                },
            ),
        )

    manager._drops_state = drops_state(BLOCK)
    streams = dict(manager._fwair_event_streams(BLOCK))
    assert streams == {
        manager_module.FWAIR_MANAGER: "ok",
        child: "warning",
    }

    manager._drops_state = drops_state(BLOCK - 1)
    assert dict(manager._fwair_event_streams(BLOCK))[child] == "unknown"
    manager._drops_state = drops_state(BLOCK)
    calls: list[tuple[str, str]] = []

    async def fetch_events(
        _self,
        address,
        *,
        from_block,
        to_block,
        history_complete,
        integrity,
    ):
        assert history_complete is False
        calls.append((address, integrity))
        row = _event(
            address=address,
            block_number=from_block + 1,
            log_index=len(calls),
            family="drop",
        )
        row.update(integrity=integrity, verified_source=integrity != "mismatch")
        return SimpleNamespace(
            observed_at=clock(),
            address=address,
            from_block=from_block,
            to_block=to_block,
            available=True,
            page_complete=True,
            decode_failures=0,
            last_complete_block_hash=HASH,
            events=(row,),
        )

    drops.fetch_events = MethodType(fetch_events, drops)

    assert await manager._refresh_fwair_logs(BLOCK) is True
    assert calls == [
        (manager_module.FWAIR_MANAGER, "ok"),
        (child, "warning"),
    ]
    manager_key = WatermarkKey(
        "fwair", manager_module.FWAIR_MANAGER, "events"
    )
    child_key = WatermarkKey("fwair", child, "events")
    manager_mark = manager.cache.get_watermark(manager_key)
    child_mark = manager.cache.get_watermark(child_key)
    assert manager_mark is not None and child_mark is not None
    assert manager_mark == child_mark
    assert manager_key != child_key
    assert {
        row["event_id"].split(":")[1] for row in manager._events.values()
    } == {manager_module.FWAIR_MANAGER, child}
    await manager.close()


@pytest.mark.parametrize(
    ("campaign_block", "expected_integrity"),
    ((BLOCK, "warning"), (BLOCK - 1, "unknown")),
)
async def test_megarip_events_only_receive_same_block_campaign_integrity(
    campaign_block, expected_integrity, tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, _pull, mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager._pages_per_cycle = 1
    manifest = manager_module.MEGARIP_MANIFESTS[0]
    manager._mega_state = SimpleNamespace(
        state_block=BLOCK,
        campaigns=(
            SimpleNamespace(
                version=manifest.version,
                block_number=campaign_block,
                integrity="warning",
            ),
        ),
    )
    received: list[str] = []

    async def fetch_events(
        _self,
        version,
        *,
        from_block,
        to_block,
        history_complete,
        integrity,
    ):
        assert version == manifest.version
        assert history_complete is False
        received.append(integrity)
        return SimpleNamespace(
            observed_at=clock(),
            available=True,
            page_complete=True,
            last_complete_block_hash=HASH,
            events=(),
        )

    mega.fetch_events = MethodType(fetch_events, mega)

    assert await manager._refresh_megarip_logs(BLOCK) is True
    assert received == [expected_integrity]
    await manager.close()


async def test_due_background_tier_is_single_flight_and_removes_done_task(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    clock.advance(61.0)
    manager.cache.mark_fetched(TIER_FAST, clock())
    manager.cache.mark_fetched(TIER_API, clock())
    manager.cache.mark_fetched(TIER_INTEGRITY, clock())
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def gated_medium():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    manager._run_medium_cycle = gated_medium
    await manager.fetch_and_compute()
    await entered.wait()
    await manager.fetch_and_compute()

    assert calls == 1
    task = manager._background_tasks["medium"]
    release.set()
    await task
    await asyncio.sleep(0)
    assert "medium" not in manager._background_tasks
    await manager.close()


async def test_close_cancels_owned_background_without_task_leak(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    clock.advance(61.0)
    manager.cache.mark_fetched(TIER_FAST, clock())
    manager.cache.mark_fetched(TIER_API, clock())
    manager.cache.mark_fetched(TIER_INTEGRITY, clock())
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def hanging_medium():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    manager._run_medium_cycle = hanging_medium
    await manager.fetch_and_compute()
    await entered.wait()

    await manager.close()

    assert cancelled.is_set()
    assert manager._background_tasks == {}
    assert manager._fast_task is None


async def test_per_source_background_timeout_cancels_the_hung_call(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    manager._background_timeout = 0.01
    cancelled = asyncio.Event()

    async def hang(_block):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def ready(_block):
        return True

    manager._refresh_flow_logs = hang
    manager._refresh_pullpool_logs = ready
    manager._refresh_megarip_logs = ready
    manager._refresh_fwap_logs = ready

    await asyncio.wait_for(manager._run_medium_cycle(), timeout=0.2)

    assert cancelled.is_set()
    assert "flow_logs" in manager._failed_groups
    await manager.close()


async def test_latest_cycle_pin_survives_core_failure_and_drives_slow_calls(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    clock.advance(31.0)
    core.head_block = BLOCK + 1
    core.fail = True

    payload = await manager.fetch_and_compute()

    assert manager._current_state_block() == BLOCK + 1
    assert payload["network_state_block"] == BLOCK
    assert payload["network_chain_head"] == BLOCK + 1
    assert manager.cache.get_last_good("core").block_number == BLOCK
    assert manager.cache.get_last_good("pullpool").block_number == BLOCK + 1

    calls: list[tuple[str, int]] = []

    class CoreIntegrity(SimpleNamespace):
        def status_for(self, *_roles):
            return "ok"

    async def core_check(block_number):
        calls.append(("core", block_number))
        return CoreIntegrity(
            observed_at=clock(),
            block_number=block_number,
            codehash_matches={},
            dependency_matches={},
        )

    async def pull_check(block_number):
        calls.append(("pullpool", block_number))
        return SimpleNamespace(block_number=block_number)

    async def fwap_check(block_number):
        calls.append(("fwap", block_number))
        return SimpleNamespace(block_number=block_number)

    core.fetch_official_integrity = core_check
    pull.fetch_integrity = pull_check
    fwap.fetch_integrity = fwap_check
    await manager._run_integrity_cycle()

    assert calls == [
        ("core", BLOCK + 1),
        ("pullpool", BLOCK + 1),
        ("fwap", BLOCK + 1),
    ]
    assert manager._core_integrity is None
    await manager.close()


async def test_project_log_failure_stales_only_that_adapter_and_publishes_peers(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    pull_event = _event(
        address="0x" + "61" * 20,
        block_number=100,
        log_index=1,
        family="pullpool",
    )
    mega_event = _event(
        address="0x" + "62" * 20,
        block_number=101,
        log_index=1,
        family="megarip",
    )
    fwap_event = _event(
        address="0x" + "63" * 20,
        block_number=102,
        log_index=1,
        family="fwap",
    )
    manager._merge_events((pull_event, mega_event, fwap_event))

    async def ready(_block):
        return True

    async def down(_block):
        return False

    manager._refresh_flow_logs = ready
    manager._refresh_fwair_logs = ready
    manager._refresh_pullpool_logs = ready
    manager._refresh_megarip_logs = down
    manager._refresh_fwap_logs = ready
    manager._source_history_caught_up = (
        lambda source, _block: source != "megarip"
    )
    clock.advance(5.0)

    await manager._run_medium_cycle()
    payload = manager.cache.latest_snapshot().payload
    rows = {row["family"]: row for row in payload["network_events"]}

    assert rows["pullpool"]["stale"] is False
    assert rows["fwap"]["stale"] is False
    assert rows["megarip"]["stale"] is True
    assert payload["network_feed_available"] is True
    assert payload["network_feed_unavailable_reason"] == "partial: megarip"
    assert payload["network_feed_as_of_ts"] == clock()
    assert {row["observed_at"] for row in rows.values()} == {NOW}
    assert "project_logs" in payload["network_degraded_sources"]
    await manager.close()


async def test_successful_pages_stay_partial_until_every_stream_is_caught_up(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    event = _event(
        address=manager_module.FWAP_MANIFESTS[0].address,
        block_number=100,
        log_index=1,
        family="fwap",
    )
    manager._merge_events((event,))

    async def ready(_block):
        return True

    manager._refresh_flow_logs = ready
    manager._refresh_fwair_logs = ready
    manager._refresh_pullpool_logs = ready
    manager._refresh_megarip_logs = ready
    manager._refresh_fwap_logs = ready
    manager._source_history_caught_up = (
        lambda source, _block: source != "fwap"
    )
    clock.advance(2.0)

    await manager._run_medium_cycle()
    payload = manager.cache.latest_snapshot().payload

    assert payload["network_feed_unavailable_reason"] == "partial: fwap"
    assert payload["network_events"][0]["stale"] is True
    assert GROUP_PROJECT_LOGS in payload["network_degraded_sources"]
    assert manager.cache.seconds_until_due(TIER_MEDIUM, clock()) > 0.0
    await manager.close()


async def test_total_project_log_outage_keeps_last_good_but_marks_every_event_stale(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    events = (
        _event(
            address="0x" + "71" * 20,
            block_number=100,
            log_index=1,
            family="pullpool",
        ),
        _event(
            address="0x" + "72" * 20,
            block_number=101,
            log_index=1,
            family="megarip",
        ),
        _event(
            address="0x" + "73" * 20,
            block_number=102,
            log_index=1,
            family="fwap",
        ),
    )
    manager._merge_events(events)
    await manager._store_event_fragment(
        clock(),
        state_block=BLOCK,
    )
    previous = manager.cache.get_last_good(GROUP_PROJECT_LOGS)

    async def project_down(_block):
        return False

    manager._refresh_flow_logs = project_down
    manager._refresh_fwair_logs = project_down
    manager._refresh_pullpool_logs = project_down
    manager._refresh_megarip_logs = project_down
    manager._refresh_fwap_logs = project_down
    clock.advance(1.0)

    await manager._run_medium_cycle()
    payload = manager.cache.latest_snapshot().payload

    assert manager.cache.get_last_good(GROUP_PROJECT_LOGS) == previous
    assert payload["network_feed_available"] is True
    assert payload["network_feed_unavailable_reason"] == (
        "partial: drop, fwa, fwap, megarip, pullpool"
    )
    assert all(row["stale"] is True for row in payload["network_events"])
    assert "project_logs" in payload["network_degraded_sources"]
    await manager.close()


async def test_quiet_success_uses_scan_time_without_inventing_event_provenance(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()

    async def ready(_block):
        return True

    manager._refresh_flow_logs = ready
    manager._refresh_pullpool_logs = ready
    manager._refresh_megarip_logs = ready
    manager._refresh_fwap_logs = ready
    clock.advance(7.0)

    await manager._run_medium_cycle()
    entry = manager.cache.get_last_good(GROUP_PROJECT_LOGS)

    assert entry is not None
    assert entry.ts == clock()
    assert entry.payload["network_feed_as_of_ts"] == clock()
    assert entry.payload["network_events"] == []
    await manager.close()


async def test_integrity_race_marks_and_commits_degradation(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    entered = asyncio.Event()
    release = asyncio.Event()
    entered_count = 0

    class Integrity(SimpleNamespace):
        def status_for(self, *_roles):
            return "ok"

    async def check(block_number):
        nonlocal entered_count
        entered_count += 1
        if entered_count == 3:
            entered.set()
        await release.wait()
        return Integrity(
            observed_at=NOW,
            block_number=block_number,
            codehash_matches={},
            dependency_matches={},
        )

    core.fetch_official_integrity = check
    pull.fetch_integrity = check
    fwap.fetch_integrity = check
    task = asyncio.create_task(manager._run_integrity_cycle())
    await entered.wait()
    manager._state_block = BLOCK + 1
    release.set()
    await task

    assert "integrity" in manager.cache.latest_snapshot().payload[
        "network_degraded_sources"
    ]
    assert manager.cache.get_last_good(GROUP_INTEGRITY) is None
    await manager.close()


async def test_medium_cycle_pin_race_does_not_publish_old_results_as_fresh(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    manager._merge_events(
        (
            _event(
                address="0x" + "81" * 20,
                block_number=100,
                log_index=1,
                family="pullpool",
            ),
        )
    )
    await manager._store_event_fragment(clock(), state_block=BLOCK)
    previous = manager.cache.get_last_good(GROUP_PROJECT_LOGS)
    entered = asyncio.Event()
    release = asyncio.Event()
    entered_count = 0

    async def gated(_block):
        nonlocal entered_count
        entered_count += 1
        if entered_count == 4:
            entered.set()
        await release.wait()
        return True

    manager._refresh_flow_logs = gated
    manager._refresh_pullpool_logs = gated
    manager._refresh_megarip_logs = gated
    manager._refresh_fwap_logs = gated
    clock.advance(1.0)
    task = asyncio.create_task(manager._run_medium_cycle())
    await entered.wait()
    manager._state_block = BLOCK + 1
    release.set()
    await task

    assert manager.cache.get_last_good(GROUP_PROJECT_LOGS) == previous
    assert manager.cache.seconds_until_due(TIER_MEDIUM, clock()) == 30.0
    assert {GROUP_FLOW_LOGS, GROUP_PROJECT_LOGS} <= set(
        manager.cache.latest_snapshot().payload["network_degraded_sources"]
    )
    await manager.close()


async def test_flow_fetch_result_after_pin_change_cannot_mutate_history(
    tmp_path, monkeypatch
) -> None:
    manager, clock, *_rest, logs = _manager(tmp_path, monkeypatch)
    await manager.fetch_and_compute()
    manager.block_hash_reader = lambda _block: HASH
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch_flow(_self, from_block, to_block, *, history_complete):
        assert history_complete is False
        entered.set()
        await release.wait()
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=(),
            burns=(),
        )

    logs.fetch_flow_logs = MethodType(fetch_flow, logs)
    task = asyncio.create_task(manager._refresh_flow_logs(BLOCK))
    await entered.wait()
    manager._state_block = BLOCK + 1
    release.set()

    assert await task is False
    assert manager.cache.get_watermark(manager_module._FLOW_WATERMARK) is None
    assert manager.cache.get_last_good(GROUP_FLOW_LOGS) is None
    assert manager._flow_logs is None
    assert manager._flow_buybacks == {}
    assert manager._flow_burns == {}
    await manager.close()


async def test_pullpool_pin_race_never_exposes_live_cache_to_adapter(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, _core, _drops, pull, _mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    stream = LOG_STREAMS[0]
    key = stream.watermark_key
    watermark_block = stream.manifest.deployment_block + 100
    previous = manager.cache.set_watermark(
        key,
        block_number=watermark_block,
        block_hash=HASH,
        overlap=64,
        page_complete=True,
    )
    coverage = SimpleNamespace(
        ranges=(SimpleNamespace(through_block=watermark_block),)
    )
    manager._pull_history = SimpleNamespace(
        coverage_for=lambda requested: coverage if requested == key else None
    )
    manager.block_hash_reader = lambda _block: HASH
    entered = asyncio.Event()
    release = asyncio.Event()
    received_cache = None
    received_watermarks = None

    async def fetch_pull(_self, *_args, cache=None, watermarks=None, **_kwargs):
        nonlocal received_cache, received_watermarks
        received_cache = cache
        received_watermarks = watermarks
        entered.set()
        await release.wait()
        if cache is not None:
            cache.set_watermark(
                key,
                block_number=watermark_block + 1,
                block_hash=HASH,
                overlap=64,
                page_complete=True,
            )
        return None

    pull.fetch_logs = MethodType(fetch_pull, pull)
    task = asyncio.create_task(manager._refresh_pullpool_logs(BLOCK))
    await entered.wait()
    manager._state_block = BLOCK + 1
    release.set()

    assert await task is False
    assert received_cache is None
    assert received_watermarks == {key: previous}
    assert manager.cache.get_watermark(key) == previous
    await manager.close()


async def test_project_log_paths_only_receive_integrity_for_the_same_block(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, pull, _mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    manager._pages_per_cycle = 1
    manager.block_hash_reader = lambda _block: HASH
    old_pull = SimpleNamespace(block_number=BLOCK - 1)
    old_fwap = SimpleNamespace(block_number=BLOCK - 1)
    manager._pull_integrity = old_pull
    manager._fwap_integrity = old_fwap
    seen: dict[str, list[object | None]] = {
        "pull_events": [],
        "pull_rows": [],
        "fwap_events": [],
    }

    async def fetch_pull(
        _self,
        from_block,
        to_block,
        *,
        history_complete,
        stream_keys,
        **_kwargs,
    ):
        assert history_complete is False
        key = stream_keys[0]
        stream = LOG_STREAM_BY_KEY[key]
        return PullPoolLogRead(
            observed_at=clock(),
            requested_from_block=from_block,
            requested_to_block=to_block,
            available=True,
            history_complete=False,
            history_complete_versions=(),
            failed_streams=(),
            events=(),
            progress=(
                LogProgress(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    from_block=from_block,
                    to_block=to_block,
                    last_block_hash=HASH,
                    page_complete=True,
                    overlap=64,
                ),
            ),
            streams=(
                LogStreamRead(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    deployment_block=stream.manifest.deployment_block,
                    scan_from_block=from_block,
                    requested_to_block=to_block,
                    complete_through_block=to_block,
                    watermark_hash_match=None,
                    reorged=False,
                ),
            ),
        )

    def pull_events(_read, *, integrity, stale):
        assert stale is False
        seen["pull_events"].append(integrity)
        return ()

    def pull_rows(state, *, history, integrity):
        assert history is not None
        seen["pull_rows"].append(integrity)
        return state.rows

    def fwap_events(_read, *, integrity, stale):
        assert stale is False
        seen["fwap_events"].append(integrity)
        return ()

    class FwapLogs(_Closable):
        async def fetch_page(self, **_kwargs):
            return FWAPLogPage(logs=(), block_hash=HASH)

    pull.fetch_logs = MethodType(fetch_pull, pull)
    monkeypatch.setattr(manager_module, "normalize_pullpool_events", pull_events)
    monkeypatch.setattr(manager_module, "build_pullpool_rows", pull_rows)
    monkeypatch.setattr(manager_module, "normalize_fwap_events", fwap_events)
    manager.fwap_logs = FwapLogs()

    assert await manager._refresh_pullpool_logs(BLOCK) is True
    assert await manager._refresh_fwap_logs(BLOCK) is True
    assert seen == {
        "pull_events": [None],
        "pull_rows": [None],
        "fwap_events": [None],
    }
    await manager.close()


async def test_restart_ignores_cursor_without_accumulator_and_missing_hash_holds(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, *_rest = _manager(tmp_path, monkeypatch)
    key = WatermarkKey("megarip", "v3", "lifecycle")
    deployment = 100
    manager.cache.set_watermark(
        key,
        block_number=1_000,
        block_hash=HASH,
        overlap=64,
        page_complete=True,
    )

    assert await manager._resume_start(key, deployment, None) == (deployment, False)

    manager.block_hash_reader = lambda _block: None
    assert await manager._resume_start(key, deployment, 1_000) is None
    assert manager.cache.get_watermark(key).block_number == 1_000
    await manager.close()


async def test_cached_event_rows_stay_last_good_but_never_seed_raw_history(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    cached = _event(address="0x" + "44" * 20, block_number=50, log_index=1)
    manager.cache.store_last_good(
        GROUP_PROJECT_LOGS,
        {
            "network_events": [cached],
            "network_feed_available": True,
            "network_feed_unavailable_reason": None,
            "network_feed_as_of_ts": NOW,
        },
        ts=NOW,
        block_number=50,
    )
    await manager.close()

    fresh = FWAEcosystemManager(
        tokenomics_client=core,
        tokenomics_log_client=logs,
        drops_client=drops,
        pullpool_adapter=pull,
        megarip_adapter=mega,
        fwap_adapter=fwap,
        fwap_log_source=None,
        cache=manager.cache,
        clock=lambda: NOW,
        persist_cache=False,
    )

    assert fresh._events == {}
    restored = fresh.cache.get_last_good(GROUP_PROJECT_LOGS).payload[
        "network_events"
    ]
    assert [row["event_id"] for row in restored] == [cached["event_id"]]
    assert restored[0]["stale"] is True
    await fresh.close()


async def test_incompatible_newer_flow_scan_keeps_complete_previous_fragment(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, _drops, _pull, _mega, _fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    payload = await manager.fetch_and_compute()
    previous = manager.cache.store_last_good(
        GROUP_FLOW_LOGS,
        _complete_flow_fragment(
            payload, observed_at=clock(), block_number=BLOCK
        ),
        ts=clock(),
        block_number=BLOCK,
    )
    manager._flow_coverage_end = BLOCK
    manager.cache.set_watermark(
        manager_module._FLOW_WATERMARK,
        block_number=BLOCK,
        block_hash=HASH,
        overlap=64,
        page_complete=True,
    )
    manager.block_hash_reader = lambda _block: HASH
    manager._state_block = BLOCK + 1
    manager._last_chain_head = BLOCK + 1

    async def fetch_flow(_self, from_block, to_block, *, history_complete):
        assert history_complete is False
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=(),
            burns=(),
        )

    logs.fetch_flow_logs = MethodType(fetch_flow, logs)

    assert await manager._refresh_flow_logs(BLOCK + 1) is False
    assert manager.cache.get_last_good(GROUP_FLOW_LOGS) == previous
    await manager.close()


async def test_restart_incomplete_genesis_scan_cannot_replace_complete_flow_cache(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    payload = await manager.fetch_and_compute()
    previous = manager.cache.store_last_good(
        GROUP_FLOW_LOGS,
        _complete_flow_fragment(
            payload, observed_at=clock(), block_number=BLOCK
        ),
        ts=clock(),
        block_number=BLOCK,
    )
    await manager.close()
    clock.advance(31.0)
    fresh = FWAEcosystemManager(
        tokenomics_client=core,
        tokenomics_log_client=logs,
        drops_client=drops,
        pullpool_adapter=pull,
        megarip_adapter=mega,
        fwap_adapter=fwap,
        fwap_log_source=None,
        cache=manager.cache,
        clock=clock,
        persist_cache=False,
    )
    await fresh.fetch_and_compute()
    fresh.block_hash_reader = lambda _block: HASH

    async def fetch_flow(_self, from_block, to_block, *, history_complete):
        assert history_complete is False
        return TokenomicsLogRead(
            observed_at=clock(),
            from_block=from_block,
            to_block=to_block,
            history_complete=False,
            buybacks_available=True,
            burns_available=True,
            unavailable_reason=None,
            buybacks=(),
            burns=(),
        )

    logs.fetch_flow_logs = MethodType(fetch_flow, logs)

    assert await fresh._refresh_flow_logs(BLOCK) is False
    assert fresh.cache.get_last_good(GROUP_FLOW_LOGS) == previous
    assert GROUP_FLOW_LOGS in fresh._failed_groups
    await fresh.close()


async def test_restart_fast_state_preserves_cached_flow_log_rows(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    payload = await manager.fetch_and_compute()
    cached_row = next(
        dict(row)
        for row in payload["network_flow_rows"]
        if row["key"] == "buyback_swap_eth"
    )
    cached_row.update(value=5.0, observed_at=clock(), stale=False)
    manager.cache.store_last_good(
        GROUP_FLOW_LOGS,
        {
            "network_flow_rows": [cached_row],
            "network_flow_history_complete": True,
            "network_flow_as_of_block": BLOCK,
            "network_flow_as_of_ts": clock(),
            "network_flow_stale": False,
            "network_last_buyback_age_s": 10.0,
        },
        ts=clock(),
        block_number=BLOCK,
    )
    await manager.close()
    clock.advance(31.0)

    fresh = FWAEcosystemManager(
        tokenomics_client=core,
        tokenomics_log_client=logs,
        drops_client=drops,
        pullpool_adapter=pull,
        megarip_adapter=mega,
        fwap_adapter=fwap,
        fwap_log_source=None,
        cache=manager.cache,
        clock=clock,
        persist_cache=False,
    )
    refreshed = await fresh.fetch_and_compute()
    row = next(
        item
        for item in refreshed["network_flow_rows"]
        if item["key"] == "buyback_swap_eth"
    )

    assert len(refreshed["network_flow_rows"]) == 19
    assert row["value"] == 5.0
    assert row["stale"] is True
    assert refreshed["network_last_buyback_age_s"] == 41.0
    await fresh.close()


async def test_megarip_unavailable_keeps_adapter_supplied_integrity_rows(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, _core, _drops, _pull, mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    original = mega.fetch_state

    async def unavailable(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.available = False
        return result

    mega.fetch_state = unavailable

    payload = await manager.fetch_and_compute()

    assert any(row["family"] == "megarip" for row in payload["network_project_rows"])
    assert "megarip" not in payload["network_degraded_sources"]
    await manager.close()


async def test_partial_integrity_cycle_does_not_replace_group_last_good(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    previous = manager.cache.store_last_good(
        GROUP_INTEGRITY,
        {"network_integrity_warning_count": 0},
        ts=clock() - 1.0,
        block_number=BLOCK,
    )

    class Integrity(SimpleNamespace):
        def status_for(self, *_roles):
            return "ok"

    async def ok(block_number):
        return Integrity(
            observed_at=clock(),
            block_number=block_number,
            codehash_matches={},
            dependency_matches={},
        )

    async def fail(_block_number):
        raise RuntimeError("integrity down")

    core.fetch_official_integrity = ok
    pull.fetch_integrity = fail
    fwap.fetch_integrity = ok

    await manager._run_integrity_cycle()

    assert manager.cache.get_last_good(GROUP_INTEGRITY) == previous
    assert "integrity" in manager.cache.latest_snapshot().payload[
        "network_degraded_sources"
    ]
    await manager.close()


@pytest.mark.parametrize("target", ("core", "pullpool", "fwap"))
async def test_confirmed_partial_mismatch_latches_until_complete_recovery(
    target, tmp_path, monkeypatch
) -> None:
    manager, clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    bad_pull = manager_module.PULLPOOL_MANIFESTS[0]
    good_pull = manager_module.PULLPOOL_MANIFESTS[-1]
    bad_fwap = manager_module.FWAP_MANIFESTS[0]
    good_fwap = manager_module.FWAP_MANIFESTS[-1]

    def pull_rows(state, *, integrity=None, **_kwargs):
        status = (
            "unknown" if integrity is None else integrity.status_for(bad_pull)
        )
        row = dict(state.rows[0])
        row.update(
            primary_value=None if status == "mismatch" else 1.0,
            source_badge="INTEGRITY" if status == "mismatch" else "DEGRADED",
            integrity=status,
        )
        return (row,)

    def fwap_rows(state, *, integrity=None, **_kwargs):
        status = (
            "unknown"
            if integrity is None
            else integrity.status_for_version(bad_fwap.version)
        )
        row = dict(state.rows[0])
        row.update(
            primary_value=None if status == "mismatch" else 1.0,
            source_badge="INTEGRITY" if status == "mismatch" else "DEGRADED",
            integrity=status,
        )
        return (row,)

    monkeypatch.setattr(manager_module, "build_pullpool_rows", pull_rows)
    monkeypatch.setattr(manager_module, "build_fwap_rows", fwap_rows)
    await manager.fetch_and_compute()
    previous = manager.cache.store_last_good(
        GROUP_INTEGRITY,
        {"network_integrity_warning_count": 0},
        ts=clock() - 1.0,
        block_number=BLOCK,
    )

    reads = {
        "core": (
            _core_integrity(BLOCK, complete=False, mismatch=True)
            if target == "core"
            else _unknown_integrity("core", BLOCK)
        ),
        "pullpool": (
            _project_integrity(
                "pullpool", BLOCK, complete=False, mismatch=True
            )
            if target == "pullpool"
            else _unknown_integrity("pullpool", BLOCK)
        ),
        "fwap": (
            _project_integrity("fwap", BLOCK, complete=False, mismatch=True)
            if target == "fwap"
            else _unknown_integrity("fwap", BLOCK)
        ),
    }

    async def read_core(_block_number):
        return reads["core"]

    async def read_pull(_block_number):
        return reads["pullpool"]

    async def read_fwap(_block_number):
        return reads["fwap"]

    core.fetch_official_integrity = read_core
    pull.fetch_integrity = read_pull
    fwap.fetch_integrity = read_fwap

    await manager._run_integrity_cycle()

    assert GROUP_INTEGRITY in manager._failed_groups
    assert manager.cache.get_last_good(GROUP_INTEGRITY) == previous
    payload = manager.cache.latest_snapshot().payload
    if target == "core":
        assert manager._core_integrity.status_for("core") == "mismatch"
        assert payload["network_active_listings"] is None
    else:
        stored = (
            manager._pull_integrity
            if target == "pullpool"
            else manager._fwap_integrity
        )
        if target == "pullpool":
            assert stored.status_for(bad_pull) == "mismatch"
        else:
            assert stored.status_for_version(bad_fwap.version) == "mismatch"
        row = next(
            item
            for item in payload["network_project_rows"]
            if item["family"] == target
        )
        assert row["primary_value"] is None
        assert row["integrity"] == "mismatch"

    clock.advance(31.0)
    core.head_block = BLOCK + 1
    await manager._run_fast_cycle()

    payload = manager.cache.latest_snapshot().payload
    if target == "core":
        matched = manager._matching_integrity(
            manager._core_integrity, BLOCK + 1
        )
        assert matched.status_for("core") == "mismatch"
        assert matched.status_for("token") == "unknown"
        assert payload["network_active_listings"] is None
    elif target == "pullpool":
        matched = manager._matching_integrity(
            manager._pull_integrity, BLOCK + 1
        )
        assert matched.status_for(bad_pull) == "mismatch"
        assert matched.status_for(good_pull) == "unknown"
    else:
        matched = manager._matching_integrity(
            manager._fwap_integrity, BLOCK + 1
        )
        assert matched.status_for_version(bad_fwap.version) == "mismatch"
        assert matched.status_for_version(good_fwap.version) == "unknown"
    if target != "core":
        row = next(
            item
            for item in payload["network_project_rows"]
            if item["family"] == target
        )
        assert row["primary_value"] is None
        assert row["integrity"] == "mismatch"

    reads = {
        "core": (
            _core_integrity(
                BLOCK + 1,
                complete=False,
                mismatch=True,
                mismatch_role="token",
            )
            if target == "core"
            else _unknown_integrity("core", BLOCK + 1)
        ),
        "pullpool": (
            _project_integrity(
                "pullpool",
                BLOCK + 1,
                complete=False,
                mismatch=True,
                mismatch_index=1,
            )
            if target == "pullpool"
            else _unknown_integrity("pullpool", BLOCK + 1)
        ),
        "fwap": (
            _project_integrity(
                "fwap",
                BLOCK + 1,
                complete=False,
                mismatch=True,
                mismatch_index=1,
            )
            if target == "fwap"
            else _unknown_integrity("fwap", BLOCK + 1)
        ),
    }
    await manager._run_integrity_cycle()

    assert GROUP_INTEGRITY in manager._failed_groups
    assert manager.cache.get_last_good(GROUP_INTEGRITY) == previous
    if target == "core":
        assert manager._core_integrity.status_for("core") == "mismatch"
        assert manager._core_integrity.status_for("token") == "mismatch"
    elif target == "pullpool":
        assert manager._pull_integrity.status_for(bad_pull) == "mismatch"
        assert manager._pull_integrity.status_for(good_pull) == "mismatch"
    else:
        assert (
            manager._fwap_integrity.status_for_version(bad_fwap.version)
            == "mismatch"
        )
        assert (
            manager._fwap_integrity.status_for_version(good_fwap.version)
            == "mismatch"
        )

    reads = {
        "core": _core_integrity(BLOCK + 1, complete=True),
        "pullpool": _project_integrity(
            "pullpool", BLOCK + 1, complete=True
        ),
        "fwap": _project_integrity("fwap", BLOCK + 1, complete=True),
    }
    await manager._run_integrity_cycle()

    assert GROUP_INTEGRITY not in manager._failed_groups
    current = manager.cache.get_last_good(GROUP_INTEGRITY)
    assert current is not None and current.block_number == BLOCK + 1
    payload = manager.cache.latest_snapshot().payload
    if target == "core":
        assert payload["network_active_listings"] == 7
    else:
        row = next(
            item
            for item in payload["network_project_rows"]
            if item["family"] == target
        )
        assert row["primary_value"] == 1.0
        assert row["integrity"] == "ok"
    await manager.close()


@pytest.mark.parametrize("target", ("core", "pullpool", "fwap"))
async def test_integrity_mismatch_immediately_suppresses_cached_event_semantics(
    target, tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    initial = await manager.fetch_and_compute()
    if target == "core":
        address = manager_module.FWA_TOKEN
        family = "fwa"
        source = "fwa"
    elif target == "pullpool":
        address = manager_module.PULLPOOL_MANIFESTS[0].address
        family = "pullpool"
        source = "pullpool"
    else:
        address = manager_module.FWAP_MANIFESTS[0].address
        family = "fwap"
        source = "fwap"
    event = _event(
        address=address,
        block_number=BLOCK - 1,
        log_index=4,
        family=family,
    )
    event.update(
        eth_amount=3.0,
        fwa_amount=7.0,
        detail="previously decoded semantic amount",
    )
    manager._merge_events((event,))
    await manager._store_event_fragment(clock(), state_block=BLOCK)
    if target == "core":
        manager.cache.store_last_good(
            GROUP_FLOW_LOGS,
            _complete_flow_fragment(
                initial, observed_at=clock(), block_number=BLOCK
            ),
            ts=clock(),
            block_number=BLOCK,
        )

    reads = {
        "core": _core_integrity(
            BLOCK,
            complete=True,
            mismatch=target == "core",
            mismatch_role="token",
        ),
        "pullpool": _project_integrity(
            "pullpool",
            BLOCK,
            complete=True,
            mismatch=target == "pullpool",
        ),
        "fwap": _project_integrity(
            "fwap",
            BLOCK,
            complete=True,
            mismatch=target == "fwap",
        ),
    }

    async def read_core(_block_number):
        return reads["core"]

    async def read_pull(_block_number):
        return reads["pullpool"]

    async def read_fwap(_block_number):
        return reads["fwap"]

    core.fetch_official_integrity = read_core
    pull.fetch_integrity = read_pull
    fwap.fetch_integrity = read_fwap

    await manager._run_integrity_cycle()

    live = manager._events[event["event_id"]]
    cached = manager.cache.get_last_good(GROUP_PROJECT_LOGS)
    assert cached is not None
    published = next(
        row
        for row in cached.payload["network_events"]
        if row["event_id"] == event["event_id"]
    )
    for row in (live, published):
        assert row["event_key"] == "integrity_mismatch"
        assert row["event_label"] == "Untrusted contract log"
        assert row["eth_amount"] is None
        assert row["fwa_amount"] is None
        assert row["verified_source"] is False
        assert row["integrity"] == "mismatch"
        assert row["stale"] is True
        assert "semantics suppressed" in row["detail"]
    assert cached.payload["network_feed_unavailable_reason"] == (
        f"partial: {source}"
    )
    assert source in manager._event_integrity_failed
    payload = manager.cache.latest_snapshot().payload
    assert GROUP_PROJECT_LOGS in payload["network_degraded_sources"]
    if target == "core":
        buyback = next(
            row
            for row in payload["network_flow_rows"]
            if row["key"] == "buyback_swap_eth"
        )
        assert buyback["value"] is None
        assert buyback["integrity"] == "mismatch"
        assert payload["network_last_buyback_age_s"] is None
        assert GROUP_FLOW_LOGS in payload["network_degraded_sources"]
        cached_flow = manager.cache.get_last_good(GROUP_FLOW_LOGS)
        assert cached_flow is not None
        cached_buyback = next(
            row
            for row in cached_flow.payload["network_flow_rows"]
            if row["key"] == "buyback_swap_eth"
        )
        assert cached_buyback["value"] is None
        assert cached_buyback["integrity"] == "mismatch"
        assert cached_flow.payload["network_flow_stale"] is True
        assert cached_flow.payload["network_last_buyback_age_s"] is None

        assert manager.cache.save()
        restored_cache = FWAEcosystemCache(
            path=manager.cache.path, clock=clock
        )
        assert restored_cache.load()
        _fresh_background(restored_cache, clock)
        fresh = FWAEcosystemManager(
            tokenomics_client=core,
            tokenomics_log_client=logs,
            drops_client=drops,
            pullpool_adapter=pull,
            megarip_adapter=mega,
            fwap_adapter=fwap,
            fwap_log_source=None,
            cache=restored_cache,
            clock=clock,
            persist_cache=False,
        )
        for restarted in (fresh._visible_snapshot(), await fresh.fetch_and_compute()):
            assert restarted["network_token_supply_fwa"] is None
            assert restarted["network_burned_since_genesis_fwa"] is None
            assert restarted["network_burned_since_genesis_pct"] is None
            restarted_buyback = next(
                row
                for row in restarted["network_flow_rows"]
                if row["key"] == "buyback_swap_eth"
            )
            assert restarted_buyback["value"] is None
            assert restarted_buyback["integrity"] == "mismatch"
            assert restarted_buyback["stale"] is True
            assert restarted["network_last_buyback_age_s"] is None
        await fresh.close()

    if target == "core":
        manager._flow_coverage_end = BLOCK
        manager._flow_logs = SimpleNamespace(marker=True)
    elif target == "pullpool":
        manager._pull_history = SimpleNamespace(marker=True)
    else:
        key = WatermarkKey(
            "fwap",
            manager_module.FWAP_MANIFESTS[0].version,
            manager_module.FWAP_MANIFESTS[0].role,
        )
        manager._project_coverage_end[key] = BLOCK

    reads = {
        "core": _core_integrity(BLOCK, complete=True),
        "pullpool": _project_integrity("pullpool", BLOCK, complete=True),
        "fwap": _project_integrity("fwap", BLOCK, complete=True),
    }
    clock.advance(1.0)
    await manager._run_integrity_cycle()

    recovered = manager.cache.latest_snapshot().payload
    assert source in manager._event_integrity_failed
    assert recovered["network_feed_unavailable_reason"] == f"partial: {source}"
    recovered_event = next(
        row
        for row in recovered["network_events"]
        if row["event_id"] == event["event_id"]
    )
    assert recovered_event["eth_amount"] is None
    assert recovered_event["fwa_amount"] is None
    assert recovered_event["stale"] is True
    if target == "core":
        assert manager._flow_coverage_end is None
        assert manager._flow_logs is None
        assert GROUP_FLOW_LOGS in recovered["network_degraded_sources"]
    elif target == "pullpool":
        assert manager._pull_history is None
    else:
        assert key not in manager._project_coverage_end

    # A second successful integrity poll must not erase an in-progress
    # deployment-to-head rebuild.
    if target == "core":
        manager._flow_coverage_end = BLOCK - 1
    elif target == "pullpool":
        manager._pull_history = SimpleNamespace(marker="partial rebuild")
    else:
        manager._project_coverage_end[key] = BLOCK - 1
    clock.advance(1.0)
    await manager._run_integrity_cycle()
    if target == "core":
        assert manager._flow_coverage_end == BLOCK - 1
    elif target == "pullpool":
        assert manager._pull_history.marker == "partial rebuild"
    else:
        assert manager._project_coverage_end[key] == BLOCK - 1
    await manager.close()


@pytest.mark.parametrize(
    ("source", "group"),
    (("pullpool", GROUP_PULLPOOL), ("fwap", GROUP_FWAP)),
)
async def test_restored_project_mismatch_blocks_fast_semantics_until_recovery(
    source, group, tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    entry = manager.cache.get_last_good(group)
    assert entry is not None
    fragment = deepcopy(entry.payload)
    target = next(
        row for row in fragment["network_project_rows"] if row["family"] == source
    )
    target.update(
        primary_value=None,
        eth_value=None,
        fwa_value=None,
        lifecycle="integrity mismatch",
        detail="runtime/dependency integrity mismatch; metrics suppressed",
        source_badge="INTEGRITY",
        stale=True,
        verified_source=False,
        integrity="mismatch",
    )
    manager.cache.store_last_good(
        group,
        fragment,
        ts=entry.ts,
        block_number=entry.block_number,
    )
    await manager._commit_from_groups()
    assert manager.cache.save()

    restored_cache = FWAEcosystemCache(path=manager.cache.path, clock=clock)
    assert restored_cache.load()
    _fresh_background(restored_cache, clock)
    fresh = FWAEcosystemManager(
        tokenomics_client=core,
        tokenomics_log_client=logs,
        drops_client=drops,
        pullpool_adapter=pull,
        megarip_adapter=mega,
        fwap_adapter=fwap,
        fwap_log_source=None,
        cache=restored_cache,
        clock=clock,
        persist_cache=False,
    )
    for payload in (fresh._visible_snapshot(), await fresh.fetch_and_compute()):
        row = next(
            item
            for item in payload["network_project_rows"]
            if item["family"] == source
        )
        assert row["primary_value"] is None
        assert row["eth_value"] is None
        assert row["fwa_value"] is None
        assert row["integrity"] == "mismatch"
        assert row["stale"] is True
    assert source in fresh._state_integrity_latched

    async def read_core(_block_number):
        return _core_integrity(BLOCK, complete=True)

    async def read_pull(_block_number):
        return _project_integrity("pullpool", BLOCK, complete=True)

    async def read_fwap(_block_number):
        return _project_integrity("fwap", BLOCK, complete=True)

    core.fetch_official_integrity = read_core
    pull.fetch_integrity = read_pull
    fwap.fetch_integrity = read_fwap
    await fresh._run_integrity_cycle()
    await fresh._run_fast_cycle()

    recovered = fresh.cache.latest_snapshot().payload
    recovered_row = next(
        item
        for item in recovered["network_project_rows"]
        if item["family"] == source
    )
    assert source not in fresh._state_integrity_latched
    assert recovered_row["primary_value"] == 1.0
    assert recovered_row["integrity"] == "ok"
    await fresh.close()
    await manager.close()


@pytest.mark.parametrize("target", ("core", "pullpool", "fwap"))
async def test_latched_mismatch_is_not_applied_before_its_evidence_block(
    target, tmp_path, monkeypatch
) -> None:
    manager, *_rest = _manager(tmp_path, monkeypatch)
    if target == "core":
        result = _core_integrity(
            BLOCK, complete=True, mismatch=True, mismatch_role="token"
        )
    else:
        result = _project_integrity(
            target, BLOCK, complete=True, mismatch=True
        )
    latched = manager._merge_integrity_mismatch(None, result)

    assert manager._matching_integrity(result, BLOCK - 1) is None
    assert manager._matching_integrity(latched, BLOCK - 1) is None
    assert manager._matching_integrity(latched, BLOCK) is not None
    await manager.close()


async def test_rollback_before_mismatch_stays_partial_until_trusted_rescan(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    trusted = _event(
        address=manager_module.FWA_TOKEN,
        block_number=BLOCK - 1,
        log_index=7,
        family="fwa",
    )
    trusted.update(
        eth_amount=3.0,
        fwa_amount=9.0,
        detail="canonical pre-mismatch event",
    )
    manager._merge_events((trusted,))
    await manager._store_event_fragment(clock(), state_block=BLOCK)

    async def read_core(_block_number):
        return _core_integrity(
            BLOCK, complete=True, mismatch=True, mismatch_role="token"
        )

    async def read_pull(_block_number):
        return _project_integrity("pullpool", BLOCK, complete=True)

    async def read_fwap(_block_number):
        return _project_integrity("fwap", BLOCK, complete=True)

    core.fetch_official_integrity = read_core
    pull.fetch_integrity = read_pull
    fwap.fetch_integrity = read_fwap
    await manager._run_integrity_cycle()
    assert manager._events[trusted["event_id"]]["eth_amount"] is None

    manager._flow_coverage_end = BLOCK
    core.head_block = BLOCK - 1
    await manager._run_fast_cycle()
    assert manager._flow_coverage_end is None

    async def ready(_block):
        return True

    manager._refresh_flow_logs = ready
    manager._refresh_fwair_logs = ready
    manager._refresh_pullpool_logs = ready
    manager._refresh_megarip_logs = ready
    manager._refresh_fwap_logs = ready
    history_caught_up = manager._source_history_caught_up
    manager._source_history_caught_up = lambda source, state_block: (
        history_caught_up(source, state_block) if source == "fwa" else True
    )

    await manager._run_medium_cycle()
    rolled_back = manager.cache.latest_snapshot().payload
    still_suppressed = next(
        row
        for row in rolled_back["network_events"]
        if row["event_id"] == trusted["event_id"]
    )
    assert manager._flow_coverage_end is None
    assert "fwa" in manager._event_integrity_failed
    assert "fwa" in manager._event_integrity_rebuild
    assert rolled_back["network_feed_unavailable_reason"] == "partial: fwa"
    assert still_suppressed["eth_amount"] is None
    assert still_suppressed["event_key"] == "integrity_mismatch"
    assert still_suppressed["stale"] is True
    assert GROUP_PROJECT_LOGS in rolled_back["network_degraded_sources"]

    # Model the completed deployment-to-rollback rescan.  Only now may the
    # canonical pre-evidence event regain its decoded semantics.
    manager._replace_events(
        (trusted,),
        address=manager_module.FWA_TOKEN,
        from_block=BLOCK - 1,
        to_block=BLOCK - 1,
        reorged=True,
    )
    manager._flow_coverage_end = BLOCK - 1
    clock.advance(1.0)
    await manager._run_medium_cycle()

    rebuilt = manager.cache.latest_snapshot().payload
    restored = next(
        row
        for row in rebuilt["network_events"]
        if row["event_id"] == trusted["event_id"]
    )
    assert "fwa" not in manager._event_integrity_failed
    assert "fwa" not in manager._event_integrity_rebuild
    assert rebuilt["network_feed_unavailable_reason"] is None
    assert restored["eth_amount"] == 3.0
    assert restored["fwa_amount"] == 9.0
    assert restored["event_key"] == "test"
    assert restored["stale"] is False
    assert GROUP_PROJECT_LOGS not in rebuilt["network_degraded_sources"]

    # If the mismatched block becomes canonical again, the retained evidence
    # must immediately re-suppress the event before the next integrity poll.
    core.head_block = BLOCK
    clock.advance(1.0)
    await manager._run_fast_cycle()
    bounced = manager.cache.latest_snapshot().payload
    suppressed_again = next(
        row
        for row in bounced["network_events"]
        if row["event_id"] == trusted["event_id"]
    )
    assert "fwa" in manager._event_integrity_failed
    assert bounced["network_feed_unavailable_reason"] == "partial: fwa"
    assert suppressed_again["eth_amount"] is None
    assert suppressed_again["event_key"] == "integrity_mismatch"
    assert GROUP_PROJECT_LOGS in bounced["network_degraded_sources"]
    await manager.close()


async def test_fail_soft_unknown_integrity_keeps_warning_last_good(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    previous = manager.cache.store_last_good(
        GROUP_INTEGRITY,
        {"network_integrity_warning_count": 3},
        ts=clock() - 1.0,
        block_number=BLOCK,
    )

    class UnknownIntegrity(SimpleNamespace):
        def status_for(self, *_roles):
            return "unknown"

        def status_for_version(self, _version):
            return "unknown"

    async def fail_soft(block_number):
        return UnknownIntegrity(
            observed_at=clock(),
            block_number=block_number,
            codehash_matches={"unknown": None},
            dependency_matches={"unknown": None},
            surfaces=(),
        )

    core.fetch_official_integrity = fail_soft
    pull.fetch_integrity = fail_soft
    fwap.fetch_integrity = fail_soft

    await manager._run_integrity_cycle()

    assert manager.cache.get_last_good(GROUP_INTEGRITY) == previous
    payload = manager.cache.latest_snapshot().payload
    assert payload["network_integrity_warning_count"] == 3
    assert GROUP_INTEGRITY in payload[
        "network_degraded_sources"
    ]
    await manager.close()


async def test_overlap_replaces_orphan_and_event_dedupe_sorts_newest(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, *_rest = _manager(tmp_path, monkeypatch)
    address = "0x" + "55" * 20
    orphan = _event(address=address, block_number=105, log_index=1)
    keep = _event(address=address, block_number=99, log_index=2)
    replacement = _event(address=address, block_number=106, log_index=3)
    lower_precedence = dict(replacement)
    lower_precedence.update(source_kind="project_api", detail="API duplicate")
    manager._merge_events((orphan, keep))

    manager._replace_events(
        (replacement,),
        address=address,
        from_block=100,
        to_block=110,
        reorged=True,
    )
    rows = manager._dedupe_events(
        [*manager._events.values(), lower_precedence, replacement, keep]
    )

    assert [row["block_number"] for row in rows] == [106, 99]
    assert rows[0]["source_kind"] == "chain_log"
    assert orphan["event_id"] not in {row["event_id"] for row in rows}
    await manager.close()


async def test_project_source_precedence_keeps_chain_row_over_api_duplicate(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, *_rest = _manager(tmp_path, monkeypatch)
    chain = _project_row("fwap", observed_at=NOW)
    api = dict(chain)
    api.update(
        source_kind="project_api",
        source_badge="API STALE",
        stale=True,
        detail="API attempted overwrite",
    )
    chain = ProjectRow.model_validate(chain).model_dump()
    api = ProjectRow.model_validate(api).model_dump()

    rows = manager._dedupe_project_rows([api, chain])

    assert len(rows) == 1
    assert rows[0]["source_kind"] == "chain_state"
    assert rows[0]["detail"] == "chain value"
    await manager.close()
