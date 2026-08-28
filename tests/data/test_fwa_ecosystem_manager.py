"""Offline controller tests for the FWA NETWORK ecosystem manager."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import maxpane_dashboard.data.fwa_ecosystem_manager as manager_module
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    FWAEcosystemCache,
    GROUP_CORE,
    GROUP_DROPS,
    GROUP_FWAP,
    GROUP_MEGARIP,
    GROUP_PULLPOOL,
    TIER_API,
    TIER_FAST,
    TIER_INTEGRITY,
    TIER_MEDIUM,
)
from maxpane_dashboard.data.fwa_ecosystem_manager import FWAEcosystemManager
from maxpane_dashboard.data.fwa_ecosystem_models import (
    DropRow,
    FWA_NETWORK_DATA_KEYS,
    NetworkEventRow,
    ProjectRow,
    blank_network_payload,
)
from maxpane_dashboard.data.fwa_tokenomics_client import TokenomicsState
from tests.fwa_ecosystem_fixtures import FixedClock


NOW = 1_800_000_000.0
BLOCK = 25_900_000
DROP_FINGERPRINT = "0x" + "ab" * 32


def _project_row(
    family: str,
    *,
    observed_at: float,
    block_number: int = BLOCK,
    version: str = "v2",
) -> dict:
    units = {
        "pullpool": "rounds",
        "megarip": "recovery_pct",
        "fwap": "nav_eth",
    }
    return ProjectRow(
        family=family,
        surface=family,
        version=version,
        address="0x" + {"pullpool": "11", "megarip": "22", "fwap": "33"}[family] * 20,
        is_current=True,
        is_legacy_liability=False,
        lifecycle="live",
        primary_label="primary",
        primary_value=1.0,
        primary_unit=units[family],
        eth_label="ETH",
        eth_value=1.0,
        fwa_label="FWA",
        fwa_value=2.0,
        detail="chain value",
        source_badge="VERIFIED",
        source_kind="chain_state",
        measurement="measured",
        block_number=block_number,
        observed_at=observed_at,
        stale=False,
        verified_source=True,
        integrity="ok",
    ).model_dump()


def _drop_row(
    launch_id: int,
    *,
    observed_at: float,
    block_number: int = BLOCK,
) -> DropRow:
    return DropRow(
        launch_id=launch_id,
        launch_address="0x" + f"{launch_id:040x}",
        collection_address="0x" + f"{launch_id + 100:040x}",
        collection_name=f"Launch {launch_id}",
        phase="supporting",
        support_open=True,
        token_count=10,
        supported_count=4,
        supporter_count=3,
        launched_count=0,
        terminal_count=0,
        backing_eth=1.0,
        total_backing_eth=1.0,
        artist_credit_eth=0.0,
        supporter_principal_eth=1.0,
        supporter_reserve_fwa=2.0,
        source_kind="chain_state",
        measurement="measured",
        block_number=block_number,
        observed_at=observed_at,
        stale=False,
        verified_source=True,
        integrity="ok",
    )


class _Closable:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


class _Core(_Closable):
    def __init__(self, clock: FixedClock) -> None:
        super().__init__()
        self.clock = clock
        self.head_calls = 0
        self.head_block = BLOCK
        self.blocks: list[int] = []
        self.fail = False

    async def fetch_block_number(self) -> int:
        self.head_calls += 1
        return self.head_block

    async def fetch_state(self, *, block_number: int, **_kwargs):
        self.blocks.append(block_number)
        if self.fail:
            raise RuntimeError("core down")
        return TokenomicsState(
            observed_at=self.clock(),
            state_block=block_number,
            chain_head=block_number,
            active_listings=7,
            pending_count=2,
            unsettled_count=3,
            quote_total_wei=10**18,
            crown_pot_wei=2 * 10**18,
            total_supply_wei=900_000_000 * 10**18,
        )

    async def fetch_official_integrity(self, block_number: int):
        raise AssertionError(f"unexpected integrity call at {block_number}")


class _Drops(_Closable):
    def __init__(self, clock: FixedClock) -> None:
        super().__init__()
        self.clock = clock
        self.blocks: list[int] = []
        self.event_calls: list[tuple[str, int, int, str]] = []
        self.fail = False

    async def fetch_drops(self, *, block_number: int):
        self.blocks.append(block_number)
        if self.fail:
            raise RuntimeError("drops down")
        return SimpleNamespace(
            observed_at=self.clock(),
            state_block=block_number,
            available=True,
            integrity="ok",
            rows=(),
            holes=(),
            issues=(),
            valid_count=0,
        )

    async def fetch_events(
        self,
        address: str,
        *,
        from_block: int,
        to_block: int,
        history_complete: bool,
        integrity: str,
    ):
        assert history_complete is False
        self.event_calls.append((address, from_block, to_block, integrity))
        return SimpleNamespace(
            observed_at=self.clock(),
            address=address,
            from_block=from_block,
            to_block=to_block,
            available=True,
            page_complete=True,
            last_complete_block_hash="0x" + "ab" * 32,
            events=(),
            decode_failures=0,
        )


class _Project(_Closable):
    def __init__(self, family: str, clock: FixedClock) -> None:
        super().__init__()
        self.family = family
        self.clock = clock
        self.blocks: list[int] = []
        self.fail = False

    async def fetch_state(self, block_number: int | None = None, **kwargs):
        if block_number is None:
            block_number = kwargs["block_number"]
        self.blocks.append(block_number)
        if self.fail:
            raise RuntimeError(f"{self.family} down")
        row = _project_row(
            self.family, observed_at=self.clock(), block_number=block_number
        )
        if self.family == "megarip":
            return SimpleNamespace(
                observed_at=self.clock(),
                state_block=block_number,
                available=True,
                rows=(row,),
            )
        return SimpleNamespace(
            observed_at=self.clock(),
            block_number=block_number,
            rows=(row,),
        )

    async def fetch_integrity(self, block_number: int):
        raise AssertionError(f"unexpected integrity call at {block_number}")

    async def fetch_api_snapshot(self, block_number: int):
        raise AssertionError(f"unexpected API call at {block_number}")


class _NeverUsedLogs(_Closable):
    async def fetch_flow_logs(self, *_args, **_kwargs):
        raise AssertionError("background tier was marked fresh")


def _fresh_background(cache: FWAEcosystemCache, clock: FixedClock) -> None:
    for tier in (TIER_MEDIUM, TIER_API, TIER_INTEGRITY):
        cache.mark_fetched(tier, clock())


def _manager(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    clock: FixedClock | None = None,
):
    clock = clock or FixedClock(NOW)
    cache = FWAEcosystemCache(
        path=str(tmp_path / "network-cache.json"), clock=clock
    )
    _fresh_background(cache, clock)
    core = _Core(clock)
    drops = _Drops(clock)
    pull = _Project("pullpool", clock)
    mega = _Project("megarip", clock)
    fwap = _Project("fwap", clock)
    logs = _NeverUsedLogs()
    monkeypatch.setattr(
        manager_module,
        "build_pullpool_rows",
        lambda state, **_kwargs: state.rows,
    )
    monkeypatch.setattr(
        manager_module,
        "build_fwap_rows",
        lambda state, **_kwargs: state.rows,
    )
    manager = FWAEcosystemManager(
        tokenomics_client=core,
        tokenomics_log_client=logs,
        drops_client=drops,
        pullpool_adapter=pull,
        megarip_adapter=mega,
        fwap_adapter=fwap,
        fwap_log_source=None,
        cache=cache,
        clock=clock,
        persist_cache=False,
    )
    return manager, clock, core, drops, pull, mega, fwap, logs


async def test_exact_keys_one_head_and_every_direct_read_uses_same_block(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, drops, pull, mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )

    payload = await manager.fetch_and_compute()

    assert tuple(payload) == FWA_NETWORK_DATA_KEYS
    assert len(payload) == 40
    assert payload["network_ready"] is True
    assert payload["network_state_block"] == BLOCK
    assert core.head_calls == 1
    assert core.blocks == [BLOCK]
    assert drops.blocks == [BLOCK]
    assert pull.blocks == [BLOCK]
    assert mega.blocks == [BLOCK]
    assert fwap.blocks == [BLOCK]
    assert payload["network_project_family_count"] == 3
    assert payload["network_project_healthy_count"] == 3
    await manager.close()


@pytest.mark.parametrize(
    ("target_name", "group"),
    (
        ("core", GROUP_CORE),
        ("drops", GROUP_DROPS),
        ("pull", GROUP_PULLPOOL),
        ("mega", GROUP_MEGARIP),
        ("fwap", GROUP_FWAP),
    ),
)
async def test_each_failed_adapter_only_stales_its_own_last_good(
    tmp_path, monkeypatch, target_name, group
) -> None:
    manager, clock, core, drops, pull, mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    first = await manager.fetch_and_compute()
    baseline_degraded = set(first["network_degraded_sources"])
    first_entry = manager.cache.get_last_good(group)
    assert first_entry is not None

    clock.advance(31.0)
    target = {
        "core": core,
        "drops": drops,
        "pull": pull,
        "mega": mega,
        "fwap": fwap,
    }[target_name]
    target.fail = True
    second = await manager.fetch_and_compute()

    assert tuple(second) == FWA_NETWORK_DATA_KEYS
    assert manager.cache.seconds_until_due(TIER_FAST, clock()) == 15.0
    assert set(second["network_degraded_sources"]) - baseline_degraded == {group}
    assert manager.cache.get_last_good(group).ts == first_entry.ts
    rows = {row["family"]: row for row in second["network_project_rows"]}
    expected_family = {
        "pull": "pullpool",
        "mega": "megarip",
        "fwap": "fwap",
    }.get(target_name)
    for family, row in rows.items():
        assert row["stale"] is (family == expected_family)
    assert second["network_state_stale"] is (target_name == "core")
    assert second["network_drops_stale"] is (target_name == "drops")
    assert second["network_project_degraded_count"] == int(
        expected_family is not None
    )
    assert second["network_project_healthy_count"] == (
        2 if expected_family is not None else 3
    )
    await manager.close()


async def test_no_success_and_no_cache_returns_exact_untyped_blank(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, drops, pull, mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    for source in (core, drops, pull, mega, fwap):
        source.fail = True

    payload = await manager.fetch_and_compute()

    assert payload == blank_network_payload()
    assert tuple(payload) == FWA_NETWORK_DATA_KEYS
    assert all(value is None for value in payload.values())
    assert manager.cache.latest_snapshot() is None
    await manager.close()


async def test_core_only_first_snapshot_keeps_unavailable_project_counts_unknown(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, _core, drops, pull, mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    for source in (drops, pull, mega, fwap):
        source.fail = True

    payload = await manager.fetch_and_compute()

    assert payload["network_projects_available"] is False
    assert payload["network_project_rows"] == []
    assert payload["network_project_family_count"] is None
    assert payload["network_project_healthy_count"] is None
    assert payload["network_project_degraded_count"] is None
    assert payload["network_project_unverified_count"] is None
    assert payload["network_integrity_warning_count"] is None
    await manager.close()


async def test_drop_hole_keeps_valid_rows_but_marks_snapshot_partial(
    tmp_path, monkeypatch
) -> None:
    manager, clock, _core, drops, _pull, _mega, _fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    row = DropRow(
        launch_id=1,
        launch_address="0x" + "12" * 20,
        collection_address="0x" + "34" * 20,
        collection_name="Observed launch",
        phase="supporting",
        support_open=True,
        token_count=10,
        supported_count=4,
        supporter_count=3,
        launched_count=0,
        terminal_count=0,
        backing_eth=1.0,
        total_backing_eth=1.0,
        artist_credit_eth=0.0,
        supporter_principal_eth=1.0,
        supporter_reserve_fwa=2.0,
        source_kind="chain_state",
        measurement="measured",
        block_number=BLOCK,
        observed_at=clock(),
        stale=False,
        verified_source=True,
        integrity="ok",
    )
    older = row.model_copy(
        update={
            "launch_id": 3,
            "launch_address": "0x" + "56" * 20,
            "collection_name": "Earlier cached launch",
            "block_number": BLOCK - 5,
            "observed_at": clock() - 5.0,
            "stale": True,
        }
    )

    async def partial_drops(*, block_number: int):
        return SimpleNamespace(
            observed_at=clock(),
            state_block=block_number,
            available=True,
            integrity="ok",
            rows=(row, older),
            holes=(2,),
            issues=("launch_2_address_unavailable",),
            valid_count=2,
        )

    drops.fetch_drops = partial_drops

    payload = await manager.fetch_and_compute()

    assert payload["network_drop_count"] == 2
    assert payload["network_drops_available"] is True
    assert payload["network_drops_stale"] is True
    assert payload["network_drops_as_of_block"] == BLOCK - 5
    assert all(row["stale"] is True for row in payload["network_drop_rows"])
    assert manager.cache.get_last_good(GROUP_DROPS).block_number == BLOCK - 5
    assert GROUP_DROPS in payload["network_degraded_sources"]
    await manager.close()


async def test_matching_drop_fingerprint_merges_restart_page_but_reset_does_not(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    first = _drop_row(1, observed_at=clock(), block_number=BLOCK - 1)
    second = _drop_row(2, observed_at=clock(), block_number=BLOCK - 1)
    manager.cache.store_last_good(
        GROUP_DROPS,
        {
            "network_drop_rows": [first.model_dump(), second.model_dump()],
            "network_drops_available": True,
            "network_drops_as_of_block": BLOCK - 1,
            "network_drops_stale": True,
            "network_drop_count": 2,
        },
        ts=clock(),
        block_number=BLOCK - 1,
        source_fingerprint=DROP_FINGERPRINT,
    )
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
    newest = _drop_row(17, observed_at=clock(), block_number=BLOCK)
    page = SimpleNamespace(
        observed_at=clock(),
        state_block=BLOCK,
        next_launch_id=18,
        available=True,
        integrity="warning",
        rows=(newest,),
        holes=(),
        issues=("launch_enumeration_partial",),
        registry_fingerprint=DROP_FINGERPRINT,
        enumeration_reset=False,
    )

    fresh._store_drops_fragment(page)
    merged = fresh.cache.get_last_good(GROUP_DROPS)
    assert merged is not None
    assert [row["launch_id"] for row in merged.payload["network_drop_rows"]] == [
        1,
        2,
        17,
    ]
    assert [row["stale"] for row in merged.payload["network_drop_rows"]] == [
        True,
        True,
        False,
    ]
    assert merged.payload["network_drops_as_of_block"] == BLOCK - 1
    assert merged.payload["network_drop_count"] == 3
    assert merged.source_fingerprint == DROP_FINGERPRINT

    fresh._store_drops_fragment(
        SimpleNamespace(**{**vars(page), "enumeration_reset": True})
    )
    reset = fresh.cache.get_last_good(GROUP_DROPS)
    assert reset is not None
    assert [row["launch_id"] for row in reset.payload["network_drop_rows"]] == [17]
    await fresh.close()
    await manager.close()


async def test_authoritative_drop_mismatch_neutralizes_cache_and_restart(
    tmp_path, monkeypatch
) -> None:
    manager, clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    current = SimpleNamespace(
        observed_at=clock(),
        state_block=BLOCK,
        next_launch_id=2,
        available=True,
        integrity="ok",
        rows=(_drop_row(1, observed_at=clock()),),
        holes=(),
        issues=(),
        registry_fingerprint=DROP_FINGERPRINT,
        enumeration_reset=False,
    )

    async def fetch_drops(*, block_number: int):
        assert block_number == BLOCK
        return current

    drops.fetch_drops = fetch_drops
    initial = await manager.fetch_and_compute()
    assert initial["network_drop_rows"][0]["backing_eth"] == 1.0
    event = NetworkEventRow(
        event_id=(
            f"1:{current.rows[0].launch_address}:"
            f"{'0x' + '12' * 32}:1"
        ),
        ts=clock(),
        tx_hash="0x" + "12" * 32,
        log_index=1,
        origin="FWAIR Drop",
        family="drop",
        version=None,
        event_key="supported",
        event_label="Position supported",
        eth_amount=1.0,
        fwa_amount=2.0,
        detail="trusted before mismatch",
        source_kind="chain_log",
        measurement="measured",
        block_number=BLOCK - 1,
        observed_at=clock(),
        stale=False,
        verified_source=True,
        integrity="ok",
    ).model_dump()
    manager._merge_events((event,))
    await manager._store_event_fragment(clock(), state_block=BLOCK)

    current = SimpleNamespace(
        observed_at=clock(),
        state_block=BLOCK,
        next_launch_id=None,
        available=False,
        integrity="unknown",
        rows=(),
        holes=(),
        issues=("manager_state_unavailable",),
        registry_fingerprint=None,
        enumeration_reset=False,
    )
    transient = await manager._run_fast_cycle()
    assert transient["network_drop_rows"][0]["backing_eth"] == 1.0
    assert transient["network_drop_rows"][0]["integrity"] == "ok"
    assert transient["network_drop_rows"][0]["stale"] is True

    current = SimpleNamespace(
        observed_at=clock(),
        state_block=BLOCK,
        next_launch_id=None,
        available=False,
        integrity="mismatch",
        rows=(),
        holes=(),
        issues=("manager_codehash_mismatch",),
        registry_fingerprint=None,
        enumeration_reset=True,
    )
    mismatched = await manager._run_fast_cycle()

    for payload in (mismatched, manager.cache.latest_snapshot().payload):
        row = payload["network_drop_rows"][0]
        assert row["launch_address"] == _drop_row(1, observed_at=clock()).launch_address
        assert row["backing_eth"] is None
        assert row["supporter_reserve_fwa"] is None
        assert row["phase"] == "unknown"
        assert row["verified_source"] is False
        assert row["integrity"] == "mismatch"
        assert row["stale"] is True
        assert payload["network_drop_count"] is None
        assert GROUP_DROPS in payload["network_degraded_sources"]
        suppressed = next(
            item
            for item in payload["network_events"]
            if item["event_id"] == event["event_id"]
        )
        assert suppressed["eth_amount"] is None
        assert suppressed["fwa_amount"] is None
        assert suppressed["event_key"] == "integrity_mismatch"
        assert suppressed["verified_source"] is False
        assert suppressed["integrity"] == "mismatch"

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
        row = payload["network_drop_rows"][0]
        assert row["backing_eth"] is None
        assert row["supporter_reserve_fwa"] is None
        assert row["integrity"] == "mismatch"
        assert row["stale"] is True
    await fresh.close()
    await manager.close()


@pytest.mark.parametrize("failure_mask", range(32))
async def test_every_direct_adapter_failure_combination_keeps_exact_contract(
    tmp_path, monkeypatch, failure_mask
) -> None:
    manager, _clock, core, drops, pull, mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    sources = (core, drops, pull, mega, fwap)
    for index, source in enumerate(sources):
        source.fail = bool(failure_mask & (1 << index))

    payload = await manager.fetch_and_compute()

    assert tuple(payload) == FWA_NETWORK_DATA_KEYS
    assert len(payload) == 40
    if failure_mask == 31:
        assert payload == blank_network_payload()
    else:
        assert payload["network_ready"] is True
        assert tuple(manager.cache.latest_snapshot().payload) == FWA_NETWORK_DATA_KEYS
    await manager.close()


async def test_api_and_all_integrity_calls_receive_the_snapshot_state_block(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, _drops, pull, _mega, fwap, _logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()
    integrity_calls: list[tuple[str, int]] = []
    api_calls: list[int] = []

    class CoreIntegrity(SimpleNamespace):
        def status_for(self, *_roles):
            return "ok"

    async def core_integrity(block_number):
        integrity_calls.append(("core", block_number))
        return CoreIntegrity(
            observed_at=NOW,
            block_number=block_number,
            codehash_matches={},
            dependency_matches={},
        )

    async def pull_integrity(block_number):
        integrity_calls.append(("pullpool", block_number))
        return SimpleNamespace(block_number=block_number)

    async def fwap_integrity(block_number):
        integrity_calls.append(("fwap", block_number))
        return SimpleNamespace(block_number=block_number)

    async def fwap_api(block_number):
        api_calls.append(block_number)
        return SimpleNamespace(reason="disabled")

    core.fetch_official_integrity = core_integrity
    pull.fetch_integrity = pull_integrity
    fwap.fetch_integrity = fwap_integrity
    fwap.fetch_api_snapshot = fwap_api

    await manager._run_api_cycle()
    await manager._run_integrity_cycle()

    assert api_calls == [BLOCK]
    assert integrity_calls == [
        ("core", BLOCK),
        ("pullpool", BLOCK),
        ("fwap", BLOCK),
    ]
    assert tuple(manager.cache.latest_snapshot().payload) == FWA_NETWORK_DATA_KEYS
    await manager.close()


async def test_close_closes_each_distinct_injected_client_once(
    tmp_path, monkeypatch
) -> None:
    manager, _clock, core, drops, pull, mega, fwap, logs = _manager(
        tmp_path, monkeypatch
    )
    await manager.fetch_and_compute()

    await manager.close()
    await manager.close()

    assert [
        core.close_calls,
        logs.close_calls,
        drops.close_calls,
        pull.close_calls,
        mega.close_calls,
        fwap.close_calls,
    ] == [1, 1, 1, 1, 1, 1]
