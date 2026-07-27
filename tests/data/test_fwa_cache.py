"""Tests for the FWA tiered cache and persistence layer (WP-9).

Everything runs offline against a fake clock and ``tmp_path``: no network, no
sleeping, no dependence on wall-clock time.
"""

from __future__ import annotations

import json
import math
import time

import pytest

from maxpane_dashboard.data.fwa_cache import (
    DEFAULT_CACHE_PATH,
    SERIES_ACQUISITION_FEE_ETH,
    SERIES_ACTIVE_POSITIONS,
    SERIES_CROWN_POT_ETH,
    SERIES_FWA_PRICE_USD,
    SLOT_LOGS,
    SLOT_STARTUP,
    SLOT_SWEEP,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    TIER_TAIL,
    TIERS,
    FWACache,
    LastGood,
)
from maxpane_dashboard.data.fwa_models import Position


class FakeClock:
    """Monotonic-by-hand clock so TTL tests never sleep."""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += float(seconds)
        return self.t


def _pos(listing_id: int, backing_wei: int = 10**17) -> Position:
    return Position(
        listing_id=listing_id,
        collection="0x" + "c" * 40,
        depositor="0x" + "d" * 40,
        token_id=listing_id,
        weight=10**36 // backing_wei,
        backing_wei=backing_wei,
        slot=listing_id,
        status=1,
    )


# ---------------------------------------------------------------------------
# Tier TTLs
# ---------------------------------------------------------------------------


def test_ttl_per_tier():
    """fast expires at 15 s, medium at 60 s, tail at 30 s, slow at 900 s."""
    clock = FakeClock()
    c = FWACache(clock=clock)

    # Nothing has ever been fetched: every tier is due.
    assert set(c.tiers_due()) == set(TIERS)

    for tier in (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_TAIL):
        c.mark_fetched(tier)
    assert c.tiers_due() == (TIER_ONCE,)

    clock.advance(14.9)
    assert c.is_fresh(TIER_FAST)
    clock.advance(0.2)                       # t = 15.1 s
    assert not c.is_fresh(TIER_FAST)
    assert c.is_fresh(TIER_MEDIUM)
    assert c.is_fresh(TIER_TAIL)
    assert c.is_fresh(TIER_SLOW)

    clock.advance(15.0)                      # t = 30.1 s
    assert not c.is_fresh(TIER_TAIL)
    assert c.is_fresh(TIER_MEDIUM)

    clock.advance(30.0)                      # t = 60.1 s
    assert not c.is_fresh(TIER_MEDIUM)
    assert c.is_fresh(TIER_SLOW)

    clock.advance(840.0)                     # t = 900.1 s
    assert not c.is_fresh(TIER_SLOW)
    assert set(c.tiers_due()) == set(TIERS)


def test_once_tier_never_expires_after_a_fetch():
    clock = FakeClock()
    c = FWACache(clock=clock)
    assert c.is_due(TIER_ONCE)
    c.mark_fetched(TIER_ONCE)
    clock.advance(365 * 86400)
    assert c.is_fresh(TIER_ONCE)
    assert c.seconds_until_due(TIER_ONCE) == math.inf


def test_is_due_is_the_inverse_of_is_fresh():
    clock = FakeClock()
    c = FWACache(clock=clock)
    c.mark_fetched(TIER_FAST)
    assert c.is_fresh(TIER_FAST) is True
    assert c.is_due(TIER_FAST) is False
    clock.advance(20)
    assert c.is_due(TIER_FAST) is True
    assert c.seconds_until_due(TIER_FAST) == 0.0


def test_unknown_tier_raises():
    c = FWACache(clock=FakeClock())
    for call in (
        lambda: c.is_fresh("hourly"),
        lambda: c.mark_fetched("hourly"),
        lambda: c.mark_failed("hourly"),
        lambda: c.expire_tier("hourly"),
        lambda: c.seconds_until_due("hourly"),
    ):
        with pytest.raises(ValueError):
            call()


def test_failed_fetch_leaves_tier_due_after_a_spaced_retry():
    """A failure never counts as a fetch, but it does not hammer the host either."""
    clock = FakeClock()
    c = FWACache(clock=clock)
    c.mark_failed(TIER_SLOW)                 # default backoff 120 s
    assert c.last_fetch_ts(TIER_SLOW) is None
    assert c.is_fresh(TIER_SLOW)             # backing off, not fetched
    clock.advance(119)
    assert c.is_fresh(TIER_SLOW)
    clock.advance(2)
    assert c.is_due(TIER_SLOW)


def test_explicit_now_overrides_the_clock():
    c = FWACache(clock=FakeClock(0.0))
    c.mark_fetched(TIER_FAST, now=500.0)
    assert c.is_fresh(TIER_FAST, now=510.0)
    assert not c.is_fresh(TIER_FAST, now=520.0)


# ---------------------------------------------------------------------------
# Last-good snapshots
# ---------------------------------------------------------------------------


def test_last_good_survives_a_failed_fetch():
    """Pool B down => the feed still has its last-good payload, marked as of HH:MM."""
    clock = FakeClock()
    c = FWACache(clock=clock)
    c.set_log_aggregates({"draw_events": [{"tx_hash": "0xabc"}]}, block=25_612_655)
    c.mark_fetched(TIER_TAIL)

    clock.advance(3600)
    c.mark_failed(TIER_TAIL)                 # both log endpoints down

    entry = c.get_log_aggregates()
    assert entry is not None
    assert entry.payload["draw_events"] == [{"tx_hash": "0xabc"}]
    assert entry.age_seconds(clock.t) == 3600
    assert c.as_of_ts(SLOT_LOGS) == entry.ts
    assert entry.as_of_hhmm() == time.strftime("%H:%M", time.localtime(entry.ts))


def test_last_good_carries_timestamp_and_block():
    clock = FakeClock(1_700_000_000.0)
    c = FWACache(clock=clock)

    c.set_hot_batch({"acquisitionFee": 124_700_000_000_000_000}, block=25_612_655)
    hot = c.get_hot_batch()
    assert hot.ts == 1_700_000_000.0
    assert hot.block == 25_612_655

    assert c.set_sweep(25_612_655, [_pos(1), _pos(2)]) is True
    sweep = c.get_sweep()
    assert sweep.ts == 1_700_000_000.0
    assert sweep.block == 25_612_655

    c.set_log_aggregates({"settlement_mix": []})
    assert c.get_log_aggregates().ts == 1_700_000_000.0

    c.set_floor("0x" + "A" * 40, 0.42, source="coingecko")
    assert c.get_floor("0x" + "a" * 40).ts == 1_700_000_000.0

    # Every last-good entry is stamped; nothing can be stored undated.
    assert all(e.ts > 0 for e in c.last_good.values())
    assert all(e.ts > 0 for e in c.floors.values())


def test_age_of_and_as_of_ts_are_none_without_a_payload():
    c = FWACache(clock=FakeClock())
    assert c.age_of(SLOT_LOGS) is None
    assert c.as_of_ts(SLOT_LOGS) is None
    assert c.get_sweep() is None
    assert c.sweep_block is None
    assert c.sweep_stale is True             # no sweep is not a fresh sweep


def test_floors_age_independently_per_collection():
    clock = FakeClock()
    c = FWACache(clock=clock)
    a = "0x" + "1" * 40
    b = "0x" + "2" * 40
    c.set_floor(a, 12.5)
    clock.advance(300)
    c.set_floor(b, None, source="suppressed", note="multi-collection contract")

    assert c.floor_age_seconds(a) == 300
    assert c.floor_age_seconds(b) == 0
    assert c.get_floor(b).payload["floor_eth"] is None
    assert c.get_floor(b).payload["source"] == "suppressed"
    assert set(c.floors_snapshot()) == {a, b}
    assert c.floor_age_seconds("0x" + "9" * 40) is None


# ---------------------------------------------------------------------------
# Sweep: block pinning and invalidation
# ---------------------------------------------------------------------------


def test_invalidate_sweep_marks_stale():
    clock = FakeClock()
    c = FWACache(clock=clock)
    c.set_sweep(100, [_pos(1)])
    c.mark_fetched(TIER_MEDIUM)
    assert c.sweep_stale is False
    assert c.is_fresh(TIER_MEDIUM)

    assert c.invalidate_sweep("BackingUpdated at block 101") is True

    sweep = c.get_sweep()
    assert sweep.stale is True
    assert sweep.stale_reason == "BackingUpdated at block 101"
    assert sweep.block == 100                # still carries its pinned block
    assert sweep.payload == (_pos(1),)       # payload kept: stale beats blank
    assert c.is_due(TIER_MEDIUM)             # and a refetch is due immediately
    assert c.sweep_invalidations == 1


def test_backing_updated_after_the_swept_block_invalidates():
    c = FWACache(clock=FakeClock())
    c.set_sweep(25_612_655, [_pos(1)])
    c.mark_fetched(TIER_MEDIUM)

    assert c.note_backing_updated(25_612_700) is True
    assert c.sweep_stale is True
    assert c.is_due(TIER_MEDIUM)


def test_backing_updated_at_or_before_the_swept_block_is_ignored():
    """WP-7's full-history backfill must not invalidate an up-to-date sweep."""
    c = FWACache(clock=FakeClock())
    c.set_sweep(25_612_655, [_pos(1)])
    c.mark_fetched(TIER_MEDIUM)

    assert c.note_backing_updated(25_600_000) is False   # ancient, already reflected
    assert c.note_backing_updated(25_612_655) is False   # same block, reflected
    assert c.sweep_stale is False
    assert c.is_fresh(TIER_MEDIUM)
    assert c.sweep_invalidations == 0


def test_invariant_mismatch_stores_but_flags_stale():
    c = FWACache(clock=FakeClock())
    assert c.set_sweep(100, [_pos(1)], invariants_ok=False) is True
    sweep = c.get_sweep()
    assert sweep.payload == (_pos(1),)
    assert sweep.stale is True
    assert sweep.stale_reason == "invariant mismatch"

    c.set_sweep(101, [_pos(1)])              # a clean sweep clears the flag
    assert c.sweep_stale is False
    assert c.note_invariant_mismatch("totalWeight off by 255e36") is True
    assert "totalWeight" in c.get_sweep().stale_reason


def test_unpinned_sweep_is_refused():
    c = FWACache(clock=FakeClock())
    assert c.set_sweep(0, [_pos(1)]) is False
    assert c.get_sweep() is None


def test_sweep_from_an_older_block_is_refused():
    """Sweeps are whole block-pinned snapshots; the board never walks backwards."""
    c = FWACache(clock=FakeClock())
    c.set_sweep(200, [_pos(1), _pos(2)])
    assert c.set_sweep(199, [_pos(3)]) is False

    sweep = c.get_sweep()
    assert sweep.block == 200
    assert sweep.payload == (_pos(1), _pos(2))   # untouched, not merged


def test_new_sweep_replaces_wholesale_never_merges():
    c = FWACache(clock=FakeClock())
    c.set_sweep(200, [_pos(1), _pos(2), _pos(3)])
    c.set_sweep(201, [_pos(9)])

    sweep = c.get_sweep()
    assert sweep.block == 201
    assert sweep.payload == (_pos(9),)           # not 4 positions from 2 blocks

    # There is no per-position API to merge with in the first place.
    for banned in ("add_position", "update_position", "merge_positions", "set_position"):
        assert not hasattr(c, banned)


def test_sweep_size_is_not_capped():
    """+53% pool growth in two days: nothing here may assume a position count."""
    c = FWACache(clock=FakeClock())
    big = [_pos(i, backing_wei=10**16 + i) for i in range(1, 6001)]
    assert c.set_sweep(300, big) is True
    assert len(c.get_sweep().payload) == 6000


# ---------------------------------------------------------------------------
# Hourly series
# ---------------------------------------------------------------------------


def test_hourly_buckets_capped_at_168():
    c = FWACache(clock=FakeClock())
    start = 1_700_000_000.0
    for i in range(400):
        ts = start + i * 3600
        c.sample_series(
            ts,
            fwa_price_usd=0.031 + i,
            acquisition_fee_eth=0.1247,
            active_positions=3867 + i,
            crown_pot_eth=1.5,
        )
    for name in (
        SERIES_FWA_PRICE_USD,
        SERIES_ACQUISITION_FEE_ETH,
        SERIES_ACTIVE_POSITIONS,
        SERIES_CROWN_POT_ETH,
    ):
        assert len(c.get_series(name)) == 168

    prices = c.get_series(SERIES_FWA_PRICE_USD)
    assert prices[-1][1] == pytest.approx(0.031 + 399)      # newest kept
    assert prices[0][1] == pytest.approx(0.031 + 232)       # oldest evicted


def test_hourly_bucket_overwrites_within_the_same_hour():
    c = FWACache(clock=FakeClock())
    base = 1_700_000_000.0
    hour = float(int(base // 3600) * 3600)
    c.sample_series(base, fwa_price_usd=0.030)
    c.sample_series(base + 60, fwa_price_usd=0.031)
    c.sample_series(base + 120, fwa_price_usd=0.032)
    assert c.get_series(SERIES_FWA_PRICE_USD) == [[hour, 0.032]]


def test_none_samples_never_punch_a_zero_into_a_series():
    c = FWACache(clock=FakeClock())
    ts = 1_700_000_000.0
    c.sample_series(ts, fwa_price_usd=0.031)
    c.sample_series(ts + 3600, fwa_price_usd=None, crown_pot_eth=2.0)
    assert len(c.get_series(SERIES_FWA_PRICE_USD)) == 1
    assert c.get_series(SERIES_CROWN_POT_ETH)[-1][1] == 2.0
    assert c.get_series(SERIES_ACTIVE_POSITIONS) == []


def test_non_finite_and_unparsable_samples_are_dropped():
    c = FWACache(clock=FakeClock())
    ts = 1_700_000_000.0
    c.sample_series(ts, fwa_price_usd=float("nan"))
    c.sample_series(ts, crown_pot_eth=float("inf"))
    assert c.get_series(SERIES_FWA_PRICE_USD) == []
    assert c.get_series(SERIES_CROWN_POT_ETH) == []
    assert c.get_series("not_a_series") == []


# ---------------------------------------------------------------------------
# Log tail watermarks
# ---------------------------------------------------------------------------


def test_last_seen_block_is_monotonic():
    c = FWACache(clock=FakeClock())
    c.update_last_seen_block("BackingUpdated", 100)
    c.update_last_seen_block("BackingUpdated", 90)     # a rewind is ignored
    c.update_last_seen_block("TopListingSet", 250)
    c.update_last_seen_block("TopListingSet", "junk")  # type: ignore[arg-type]
    assert c.get_last_seen_block("BackingUpdated") == 100
    assert c.get_last_seen_block("TopListingSet") == 250
    assert c.get_last_seen_block("NeverSeen") == 0
    assert c.get_last_seen_block("NeverSeen", default=25_000_000) == 25_000_000


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "fwa_cache.json")
    clock = FakeClock(1_700_000_000.0)
    c = FWACache(clock=clock)

    c.set_hot_batch({"acquisitionFee": 124_700_000_000_000_000}, block=25_612_655)
    c.set_log_aggregates(
        {"crown_history": [{"holder": "0xabc", "reigns": 4}]}, block=25_612_600
    )
    c.set_market({"price_usd": 0.031, "fdv_usd": 31_144_901})
    c.set_startup({"collections": 51})
    c.set_floor("0x" + "A" * 40, 12.5, source="coingecko")
    c.set_floor("0x" + "B" * 40, None, source="suppressed", note="Art Blocks")
    c.sample_series(
        clock.t,
        fwa_price_usd=0.031,
        acquisition_fee_eth=0.1247,
        active_positions=5942,
        crown_pot_eth=1.5,
    )
    c.update_last_seen_block("AcquisitionRequested", 25_612_655)
    c.set_sweep(25_612_655, [_pos(1), _pos(2)])
    c.mark_fetched(TIER_ONCE)
    c.save_to_file(path)

    back = FWACache(clock=FakeClock(1_700_009_999.0))
    back.load_from_file(path)

    assert back.get_hot_batch().payload["acquisitionFee"] == 124_700_000_000_000_000
    assert back.get_hot_batch().block == 25_612_655
    assert back.get_log_aggregates().payload["crown_history"][0]["reigns"] == 4
    assert back.get_log_aggregates().ts == 1_700_000_000.0
    assert back.get_market().payload["price_usd"] == 0.031
    assert back.get_startup().payload["collections"] == 51
    assert back.get_floor("0x" + "a" * 40).payload["floor_eth"] == 12.5
    assert back.get_floor("0x" + "b" * 40).payload["note"] == "Art Blocks"
    assert back.get_series(SERIES_ACTIVE_POSITIONS)[-1][1] == 5942
    assert back.get_last_seen_block("AcquisitionRequested") == 25_612_655


def test_last_good_persistence_survives_a_restart_with_its_own_timestamp(tmp_path):
    """The Pool B degradation story: last-good log data outlives the process."""
    path = str(tmp_path / "fwa_cache.json")
    c = FWACache(clock=FakeClock(1_700_000_000.0))
    c.set_log_aggregates({"draw_events": [{"tx_hash": "0xdead"}]})
    c.save_to_file(path)

    restarted = FWACache(clock=FakeClock(1_700_003_600.0))
    restarted.load_from_file(path)

    entry = restarted.get_log_aggregates()
    assert entry.payload["draw_events"] == [{"tx_hash": "0xdead"}]
    assert entry.ts == 1_700_000_000.0                       # its own timestamp
    assert entry.age_seconds(1_700_003_600.0) == 3600        # honestly an hour old
    assert restarted.as_of_ts(SLOT_LOGS) == 1_700_000_000.0


def test_restored_sweep_keeps_provenance_but_no_positions_and_is_stale(tmp_path):
    path = str(tmp_path / "fwa_cache.json")
    c = FWACache(clock=FakeClock(1_700_000_000.0))
    c.set_sweep(25_612_655, [_pos(i) for i in range(1, 51)])
    c.save_to_file(path)

    # Positions are deliberately not written to disk (unbounded with pool growth,
    # and a cross-process block-pinned list is exactly what rule 11 forbids).
    raw = json.loads((tmp_path / "fwa_cache.json").read_text())
    assert SLOT_SWEEP not in raw["last_good"]
    assert raw["sweep_provenance"]["positions"] == 50
    assert raw["sweep_provenance"]["block"] == 25_612_655

    back = FWACache(clock=FakeClock())
    back.load_from_file(path)
    assert back.sweep_block == 25_612_655
    assert back.get_sweep().payload == ()
    assert back.sweep_stale is True
    assert "not persisted" in back.get_sweep().stale_reason


def test_only_the_once_tier_mark_survives_a_restart(tmp_path):
    path = str(tmp_path / "fwa_cache.json")
    clock = FakeClock(1_700_000_000.0)
    c = FWACache(clock=clock)
    for tier in TIERS:
        c.mark_fetched(tier)
    c.set_startup({"collections": 51})
    c.save_to_file(path)

    back = FWACache(clock=FakeClock(1_700_000_001.0))
    back.load_from_file(path)
    assert back.get_last_good(SLOT_STARTUP).payload["collections"] == 51
    assert back.is_fresh(TIER_ONCE)                     # no repeat 58 s backfill
    assert set(back.tiers_due()) == {
        TIER_FAST,
        TIER_MEDIUM,
        TIER_SLOW,
        TIER_TAIL,
    }


def test_once_tier_mark_is_ignored_without_its_payload(tmp_path):
    """A mark without a payload would silently skip the startup work forever."""
    path = tmp_path / "fwa_cache.json"
    path.write_text(
        json.dumps({"version": 1, "once_fetched_at": 1_700_000_000.0})
    )
    c = FWACache(clock=FakeClock())
    c.load_from_file(str(path))
    assert c.is_due(TIER_ONCE)


def test_corrupt_file_loads_empty_not_raise(tmp_path):
    path = tmp_path / "fwa_cache.json"
    path.write_text("{not json at all")
    c = FWACache(clock=FakeClock())
    c.load_from_file(str(path))               # must not raise
    assert c.last_good == {}
    assert c.floors == {}
    assert set(c.tiers_due()) == set(TIERS)


def test_non_dict_and_partly_bad_payloads_load_fail_soft(tmp_path):
    c = FWACache(clock=FakeClock())

    list_file = tmp_path / "list.json"
    list_file.write_text("[1, 2, 3]")
    c.load_from_file(str(list_file))
    assert c.last_good == {}

    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps(
            {
                "version": 1,
                "last_good": {
                    "log_aggregates": {"payload": {"ok": True}, "ts": 5.0},
                    "hot_batch": "not-a-dict",
                    "bogus_slot": {"payload": {}, "ts": 1.0},
                },
                "floors": {"0xAAA": "nope"},
                "series": {"fwa_price_usd": [[1.0, 2.0], "bad", [3.0]]},
                "last_seen_block": {"ConfigSet": "x", "NFTAllocated": 42},
                "sweep_provenance": "not-a-dict",
                "sweep_invalidations": "many",
            }
        )
    )
    c.load_from_file(str(mixed))
    assert c.get_log_aggregates().payload == {"ok": True}
    assert c.get_hot_batch() is None
    assert c.get_last_good("bogus_slot") is None
    assert c.floors == {}
    assert c.get_series(SERIES_FWA_PRICE_USD) == [[1.0, 2.0]]
    assert c.get_last_seen_block("NFTAllocated") == 42
    assert c.get_last_seen_block("ConfigSet") == 0
    assert c.get_sweep() is None
    assert c.sweep_invalidations == 0


def test_missing_file_loads_empty_not_raise(tmp_path):
    c = FWACache(clock=FakeClock())
    c.load_from_file(str(tmp_path / "nope" / "fwa_cache.json"))
    assert c.last_good == {}


def test_save_creates_parent_directory_and_is_atomic(tmp_path):
    path = tmp_path / "nested" / "dir" / "fwa_cache.json"
    c = FWACache(clock=FakeClock())
    c.set_market({"price_usd": 0.031})
    c.save_to_file(str(path))
    assert path.exists()
    assert not (tmp_path / "nested" / "dir" / "fwa_cache.json.tmp").exists()
    assert json.loads(path.read_text())["version"] == 1


def test_save_to_unwritable_path_does_not_raise(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    c = FWACache(clock=FakeClock())
    c.set_market({"price_usd": 0.031})
    c.save_to_file(str(blocker / "sub" / "fwa_cache.json"))   # must not raise


def test_non_serialisable_payload_is_dropped_not_fabricated(tmp_path):
    path = str(tmp_path / "fwa_cache.json")
    c = FWACache(clock=FakeClock())
    c.set_market({"price_usd": 0.031, "session": object()})
    c.save_to_file(path)

    back = FWACache(clock=FakeClock())
    back.load_from_file(path)
    payload = back.get_market().payload
    assert payload["price_usd"] == 0.031
    assert payload["session"] is None


def test_pydantic_payloads_are_dumped_on_save(tmp_path):
    path = str(tmp_path / "fwa_cache.json")
    c = FWACache(clock=FakeClock())
    c.set_log_aggregates({"positions_seen": [_pos(7)]})
    c.save_to_file(path)

    back = FWACache(clock=FakeClock())
    back.load_from_file(path)
    row = back.get_log_aggregates().payload["positions_seen"][0]
    assert row["listing_id"] == 7
    assert row["backing_wei"] == 10**17


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def test_module_imports_nothing_but_stdlib_and_fwa_models():
    """Acceptance criterion: only fwa_models; no client, no analytics, no network."""
    from pathlib import Path as _Path

    import maxpane_dashboard.data.fwa_cache as mod

    src = _Path(mod.__file__).read_text()
    project_imports = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import maxpane", "from maxpane"))
    ]
    assert project_imports == [
        "from maxpane_dashboard.data.fwa_models import Position"
    ]
    for banned in (
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "fwa_client",
        "fwa_logs",
        "fwa_market",
        "fwa_signals",
        "textual",
    ):
        assert f"import {banned}" not in src


def test_default_cache_path_is_the_maxpane_convention():
    assert DEFAULT_CACHE_PATH.endswith("/.maxpane/fwa_cache.json")


def test_last_good_dataclass_is_frozen():
    entry = LastGood(payload={"a": 1}, ts=1.0, block=2)
    with pytest.raises(Exception):
        entry.ts = 2.0                        # type: ignore[misc]
    assert entry.age_seconds(0.5) == 0.0      # never negative
