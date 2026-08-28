"""Offline tests for the FWA NETWORK cache and log watermarks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import maxpane_dashboard.data.fwa_ecosystem_cache as cache_module
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    CACHE_SCHEMA_VERSION,
    FWAEcosystemCache,
    GROUP_CORE,
    GROUP_DROPS,
    GROUP_FLOW_LOGS,
    GROUP_PULLPOOL,
    TIERS,
    TIER_API,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_FAST,
    TIER_INTEGRITY,
    TIER_MEDIUM,
    TIER_TTL_SECONDS,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    blank_network_payload,
)
from tests.fwa_ecosystem_fixtures import (
    FixedClock,
    load_fwa_ecosystem_fixture,
)


NOW = 1_800_000_000.0
HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32


def _snapshot(**changes: object) -> dict[str, object | None]:
    payload = blank_network_payload()
    payload.update(
        {
            "network_ready": True,
            "network_state_stale": False,
            "network_flow_rows": [],
            "network_flow_available": True,
            "network_flow_history_complete": True,
            "network_flow_stale": False,
            "network_drop_rows": [],
            "network_drops_available": True,
            "network_drops_stale": False,
            "network_project_rows": [],
            "network_projects_available": True,
            "network_projects_stale": False,
            "network_events": [],
            "network_feed_available": True,
            "network_degraded_sources": [],
        }
    )
    payload.update(changes)
    return payload


def _cache(tmp_path: Path, clock: FixedClock | None = None) -> FWAEcosystemCache:
    return FWAEcosystemCache(
        path=str(tmp_path / "fwa_ecosystem_cache.json"),
        clock=clock or FixedClock(NOW),
    )


def _write_fixture(tmp_path: Path, name: str) -> Path:
    path = tmp_path / "fwa_ecosystem_cache.json"
    path.write_text(
        json.dumps(load_fwa_ecosystem_fixture(f"cache/{name}")),
        encoding="utf-8",
    )
    return path


def test_refresh_tiers_match_the_approved_ttls_and_backoffs() -> None:
    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_API, TIER_INTEGRITY)
    assert TIER_TTL_SECONDS == {
        TIER_FAST: 30.0,
        TIER_MEDIUM: 60.0,
        TIER_API: 120.0,
        TIER_INTEGRITY: 600.0,
    }
    assert TIER_FAILURE_BACKOFF_SECONDS == {
        TIER_FAST: 15.0,
        TIER_MEDIUM: 30.0,
        TIER_API: 60.0,
        TIER_INTEGRITY: 120.0,
    }


def test_injected_clock_drives_success_ttl_and_failure_backoff(tmp_path: Path) -> None:
    clock = FixedClock(NOW)
    cache = _cache(tmp_path, clock)
    assert cache.tiers_due() == TIERS

    cache.mark_fetched(TIER_FAST)
    assert cache.last_fetch_ts(TIER_FAST) == NOW
    assert cache.seconds_until_due(TIER_FAST) == 30.0
    clock.advance(29.0)
    assert not cache.is_due(TIER_FAST)
    clock.advance(1.0)
    assert cache.is_due(TIER_FAST)

    cache.mark_failed(TIER_FAST)
    assert cache.last_fetch_ts(TIER_FAST) == NOW
    assert cache.seconds_until_due(TIER_FAST) == 15.0
    clock.advance(15.0)
    assert cache.is_due(TIER_FAST)


def test_failure_does_not_replace_or_redate_last_good(tmp_path: Path) -> None:
    clock = FixedClock(NOW)
    cache = _cache(tmp_path, clock)
    stored = cache.store_last_good(
        GROUP_CORE,
        {"network_active_listings": 0},
        ts=NOW - 50.0,
        block_number=25_849_738,
    )
    clock.advance(100.0)
    cache.mark_failed(TIER_FAST)

    current = cache.get_last_good(GROUP_CORE)
    assert current == stored
    assert current is not None
    assert current.ts == NOW - 50.0
    assert current.payload["network_active_listings"] == 0


def test_unavailable_read_cannot_overwrite_real_zero(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.store_last_good(GROUP_CORE, {"network_pending_count": 0})

    with pytest.raises(ValueError, match="unavailable"):
        cache.store_last_good(GROUP_CORE, None)

    assert cache.get_last_good(GROUP_CORE).payload == {"network_pending_count": 0}


def test_last_good_fragments_validate_rows_and_are_detached(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    fragment: dict[str, object] = {"network_flow_rows": []}
    stored = cache.store_last_good(GROUP_FLOW_LOGS, fragment)
    fragment["network_flow_rows"] = [None]
    stored.payload["network_flow_rows"].append({"caller": "mutation"})

    assert cache.get_last_good(GROUP_FLOW_LOGS).payload == {
        "network_flow_rows": []
    }
    with pytest.raises(ValueError, match=r"network_flow_rows\[0\]"):
        cache.store_last_good(GROUP_FLOW_LOGS, fragment)


def test_complete_snapshot_requires_exact_frozen_keys(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    partial = _snapshot()
    partial.pop("network_error_count")
    with pytest.raises(ValueError, match="wrong keys"):
        cache.commit_snapshot(partial)

    extra = _snapshot(surprise=1)
    with pytest.raises(ValueError, match="unknown NETWORK cache keys"):
        cache.commit_snapshot(extra)
    assert cache.latest_snapshot() is None


def test_complete_snapshot_must_be_ready_and_preserve_none_vs_zero(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    with pytest.raises(ValueError, match="network_ready=True"):
        cache.commit_snapshot(_snapshot(network_ready=False))

    committed = cache.commit_snapshot(
        _snapshot(network_active_listings=0, network_pull_quote_eth=None)
    )
    assert tuple(committed.payload) == FWA_NETWORK_DATA_KEYS
    assert committed.payload["network_active_listings"] == 0
    assert committed.payload["network_pull_quote_eth"] is None


def test_invalid_candidate_never_replaces_visible_snapshot(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.commit_snapshot(_snapshot(network_active_listings=7))
    bad = _snapshot(network_drop_rows=[None])

    with pytest.raises(ValueError, match=r"network_drop_rows\[0\]"):
        cache.commit_snapshot(bad)

    assert cache.latest_snapshot().payload["network_active_listings"] == 7


def test_committed_and_returned_snapshots_cannot_mutate_cache_in_place(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    payload = _snapshot(network_degraded_sources=["core"])
    committed = cache.commit_snapshot(payload)
    payload["network_degraded_sources"].append("drops")
    committed.payload["network_degraded_sources"].append("market")
    cache.latest_snapshot().payload["network_degraded_sources"].append("fwap")

    assert cache.latest_snapshot().payload["network_degraded_sources"] == ["core"]


def test_snapshot_rejects_wrong_scalar_types_and_non_finite_values(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    with pytest.raises(ValueError, match="network_active_listings"):
        cache.commit_snapshot(_snapshot(network_active_listings=False))
    with pytest.raises(ValueError, match="network_pull_quote_eth"):
        cache.commit_snapshot(_snapshot(network_pull_quote_eth=1))
    with pytest.raises(ValueError, match="finite"):
        cache.commit_snapshot(_snapshot(network_pull_quote_eth=float("nan")))


def test_snapshot_rejects_unstable_or_unknown_degraded_sources(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    with pytest.raises(ValueError, match="sorted and unique"):
        cache.commit_snapshot(
            _snapshot(network_degraded_sources=["drops", "core"])
        )
    with pytest.raises(ValueError, match="unknown degraded"):
        cache.commit_snapshot(_snapshot(network_degraded_sources=["unknown"]))


def test_watermarks_are_namespaced_and_advance_only_for_complete_pages(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    pullpool = WatermarkKey("pullpool", "v2", "rounds")
    megarip = WatermarkKey("megarip", "v2", "rounds")

    assert cache.set_watermark(
        pullpool,
        block_number=100,
        block_hash=HASH_A,
        overlap=12,
        page_complete=False,
    ) is None
    cache.set_watermark(
        pullpool,
        block_number=100,
        block_hash=HASH_A,
        overlap=12,
        page_complete=True,
    )
    cache.set_watermark(
        megarip,
        block_number=80,
        block_hash=HASH_B,
        overlap=5,
        page_complete=True,
    )

    assert cache.get_watermark(pullpool).block_number == 100
    assert cache.get_watermark(megarip).block_number == 80
    assert cache.scan_start(pullpool, deployment_block=40) == 89
    assert cache.scan_start(megarip, deployment_block=40) == 76


def test_incomplete_page_cannot_move_an_existing_watermark(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    key = WatermarkKey("fwap", "v2", "trades")
    original = cache.set_watermark(
        key,
        block_number=1_000,
        block_hash=HASH_A,
        overlap=64,
        page_complete=True,
    )
    returned = cache.set_watermark(
        key,
        block_number=2_000,
        block_hash=HASH_B,
        overlap=64,
        page_complete=False,
    )
    assert returned == original
    assert cache.get_watermark(key) == original


def test_hash_mismatch_forces_overlap_rewind_until_complete_replacement(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    key = WatermarkKey("pullpool", "v2", "tickets")
    cache.set_watermark(
        key,
        block_number=100,
        block_hash=HASH_A,
        overlap=12,
        page_complete=True,
    )

    assert not cache.reconcile_block_hash(
        key, HASH_A, deployment_block=50
    )
    assert cache.reconcile_block_hash(key, HASH_B, deployment_block=50)
    assert cache.scan_start(key, deployment_block=50) == 89

    # A reorg is the one path allowed to replace the cursor with an earlier
    # fully scanned page.
    cache.set_watermark(
        key,
        block_number=95,
        block_hash=HASH_B,
        overlap=12,
        page_complete=True,
    )
    assert cache.get_watermark(key).block_number == 95
    assert cache.scan_start(key, deployment_block=50) == 84
    with pytest.raises(ValueError, match="backwards"):
        cache.set_watermark(
            key,
            block_number=94,
            block_hash=HASH_B,
            overlap=12,
            page_complete=True,
        )


def test_round_trip_restores_snapshot_groups_watermark_and_original_times(
    tmp_path: Path,
) -> None:
    clock = FixedClock(NOW)
    cache = _cache(tmp_path, clock)
    cache.commit_snapshot(_snapshot(network_active_listings=11), ts=NOW - 20.0)
    cache.store_last_good(
        GROUP_CORE,
        {"network_active_listings": 11},
        ts=NOW - 40.0,
        block_number=1_234,
    )
    key = WatermarkKey("pullpool", "v2", "tickets")
    cache.set_watermark(
        key,
        block_number=1_234,
        block_hash=HASH_A,
        overlap=20,
        page_complete=True,
        ts=NOW - 30.0,
    )
    cache.reconcile_block_hash(key, HASH_B, deployment_block=1_000)
    assert cache.save()

    restored = _cache(tmp_path, clock)
    assert restored.load()
    assert restored.latest_snapshot().ts == NOW - 20.0
    assert restored.latest_snapshot().payload["network_active_listings"] == 11
    entry = restored.get_last_good(GROUP_CORE)
    assert entry.ts == NOW - 40.0
    assert entry.block_number == 1_234
    assert restored.get_watermark(key).updated_at == NOW - 30.0
    assert restored.scan_start(key, deployment_block=1_000) == 1_215
    # Refresh clocks are deliberately process-local: restart must offer work.
    assert restored.tiers_due() == TIERS


def test_loader_discards_only_the_malformed_slot_and_watermark(
    tmp_path: Path,
) -> None:
    path = _write_fixture(tmp_path, "mixed_corrupt_cache.json")
    cache = FWAEcosystemCache(path=str(path), clock=FixedClock(NOW))

    assert cache.load()
    assert cache.get_last_good(GROUP_CORE).payload == {
        "network_active_listings": 0
    }
    assert cache.get_last_good(GROUP_DROPS) is None
    assert cache.get_last_good(GROUP_PULLPOOL).payload == {
        "network_project_rows": []
    }
    good = WatermarkKey("pullpool", "v2", "tickets")
    bad = WatermarkKey("megarip", "v3", "rounds")
    assert cache.get_watermark(good).block_number == 1234
    assert cache.get_watermark(bad) is None


def test_old_schema_and_corrupt_json_load_nothing(tmp_path: Path) -> None:
    old = _write_fixture(tmp_path, "old_schema.json")
    cache = FWAEcosystemCache(path=str(old), clock=FixedClock(NOW))
    assert not cache.load()
    assert cache.latest_snapshot() is None
    assert cache.get_last_good(GROUP_CORE) is None

    old.write_text("{not json", encoding="utf-8")
    assert not cache.load()


def test_save_uses_same_directory_temp_then_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "nested" / "fwa_ecosystem_cache.json"
    cache = FWAEcosystemCache(path=str(path), clock=FixedClock(NOW))
    cache.commit_snapshot(_snapshot())
    real_replace = cache_module.os.replace
    calls: list[tuple[str, str]] = []

    def checked_replace(source: str, target: str) -> None:
        calls.append((source, target))
        assert source == str(path) + ".tmp"
        assert target == str(path)
        with open(source, encoding="utf-8") as handle:
            assert json.load(handle)["schema_version"] == CACHE_SCHEMA_VERSION
        real_replace(source, target)

    monkeypatch.setattr(cache_module.os, "replace", checked_replace)
    assert cache.save()
    assert calls == [(str(path) + ".tmp", str(path))]
    assert path.exists()
    assert not Path(str(path) + ".tmp").exists()


def test_failed_atomic_replace_preserves_previous_file_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "fwa_ecosystem_cache.json"
    path.write_text('{"sentinel":true}', encoding="utf-8")
    cache = FWAEcosystemCache(path=str(path), clock=FixedClock(NOW))
    cache.commit_snapshot(_snapshot())

    def fail_replace(_source: str, _target: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(cache_module.os, "replace", fail_replace)
    assert not cache.save()
    assert json.loads(path.read_text(encoding="utf-8")) == {"sentinel": True}
    assert not Path(str(path) + ".tmp").exists()


def test_future_dated_snapshot_and_last_good_are_dropped_independently(
    tmp_path: Path,
) -> None:
    raw = load_fwa_ecosystem_fixture("cache/mixed_corrupt_cache.json")
    raw["snapshot"] = {"ts": NOW + 1_000.0, "payload": _snapshot()}
    raw["last_good"][GROUP_CORE]["ts"] = NOW + 1_000.0
    path = tmp_path / "fwa_ecosystem_cache.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    cache = FWAEcosystemCache(path=str(path), clock=FixedClock(NOW))
    assert cache.load()
    assert cache.latest_snapshot() is None
    assert cache.get_last_good(GROUP_CORE) is None
    assert cache.get_last_good(GROUP_PULLPOOL) is not None

