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
    FWA_NETWORK_DATA_KEYS,
    ProjectRow,
    blank_network_payload,
)
from maxpane_dashboard.data.fwa_tokenomics_client import TokenomicsState
from tests.fwa_ecosystem_fixtures import FixedClock


NOW = 1_800_000_000.0
BLOCK = 25_900_000


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
            rows=(),
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
