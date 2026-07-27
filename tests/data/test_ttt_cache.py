"""Tests for :class:`TTTCache` — idempotency, persistence, migration.

**Zero network** (this module never constructs a client).

The centrepiece is the CRIT-1 regression: before the fix the ``apply_*``
methods were pure accumulators, so a re-scanned block range double-counted.
The review reproduced it as "applying one event twice yields
``eth_to_holders_24h_wei == 2e18`` for a 1e18 deposit" — that exact scenario
is :func:`test_applying_the_same_deposit_twice_counts_it_once`.
"""

from __future__ import annotations

import json
import time

import pytest

from maxpane_dashboard.data.ttt_cache import (
    _ACTIVITY_RING_BUFFER,
    _CACHE_SCHEMA_VERSION,
    _SEEN_EVENT_PERSIST,
    _SEEN_EVENT_RING,
    TTTCache,
    _event_key,
    _hour_bucket,
)

WEI = 10**18
TOKEN_A = "0x" + "aa" * 20
TOKEN_B = "0x" + "bb" * 20
ACTOR = "0x" + "c0" * 20
NOW = 1_800_000_000.0


def deposit(cache: TTTCache, **kw):
    args = dict(
        token=TOKEN_A,
        sender=ACTOR,
        holder_share_wei=WEI,
        total_wei=3 * WEI,
        block_number=23_000_000,
        timestamp=int(NOW),
        tx_hash="0x" + "11" * 32,
        log_index=4,
    )
    args.update(kw)
    cache.apply_deposit(**args)


def launch(cache: TTTCache, **kw):
    args = dict(
        token_id=42,
        address=TOKEN_A,
        launcher=ACTOR,
        block_number=23_000_000,
        timestamp=int(NOW),
        tx_hash="0x" + "22" * 32,
        log_index=1,
    )
    args.update(kw)
    cache.apply_launch(**args)


def buyback(cache: TTTCache, **kw):
    args = dict(
        token=TOKEN_A,
        caller=ACTOR,
        eth_spent_wei=WEI // 2,
        caller_reward_wei=WEI // 100,
        block_number=23_000_000,
        timestamp=int(NOW),
        tx_hash="0x" + "33" * 32,
        log_index=2,
    )
    args.update(kw)
    cache.apply_buyback(**args)


# ===========================================================================
# 1. CRIT-1: idempotent applicators
# ===========================================================================


def test_applying_the_same_deposit_twice_counts_it_once():
    """The exact figure from the review: 1e18 deposited must never read 2e18."""
    cache = TTTCache()
    deposit(cache, holder_share_wei=WEI)
    deposit(cache, holder_share_wei=WEI)  # same log, re-delivered by a rescan
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == WEI
    assert cache.per_token_fees(TOKEN_A, NOW) == (1.0, 1.0)
    assert len(cache.activity_log) == 1


def test_a_deposit_replayed_a_hundred_times_still_reads_once():
    """A full hour of 30s polls over the same window (CRIT-1's ~120x)."""
    cache = TTTCache()
    for _ in range(120):
        deposit(cache, holder_share_wei=WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == WEI
    assert len(cache.activity_log) == 1


def test_distinct_deposits_still_accumulate():
    """Idempotency must not become deafness — different logs still add up."""
    cache = TTTCache()
    deposit(cache, tx_hash="0x" + "a1" * 32, holder_share_wei=WEI)
    deposit(cache, tx_hash="0x" + "a2" * 32, holder_share_wei=2 * WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == 3 * WEI
    assert len(cache.activity_log) == 2


def test_two_deposits_in_one_tx_are_kept_apart_by_log_index():
    """A multi-hop swap can emit two Deposited for one token in one tx."""
    cache = TTTCache()
    deposit(cache, log_index=4, holder_share_wei=WEI)
    deposit(cache, log_index=9, holder_share_wei=WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == 2 * WEI


def test_the_same_tx_hitting_two_tokens_is_not_deduped():
    cache = TTTCache()
    deposit(cache, token=TOKEN_A, log_index=None, holder_share_wei=WEI)
    deposit(cache, token=TOKEN_B, log_index=None, holder_share_wei=WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == 2 * WEI
    assert set(cache.fees_by_token) == {TOKEN_A.lower(), TOKEN_B.lower()}


def test_replayed_launch_registers_one_token_and_one_activity_row():
    cache = TTTCache()
    launch(cache)
    launch(cache)
    cache.recompute_rolling_counters(NOW)
    assert len(cache.tokens) == 1
    assert len(cache.activity_log) == 1
    assert cache.launches_24h == 1


def test_replayed_buyback_appends_one_row():
    cache = TTTCache()
    buyback(cache)
    buyback(cache)
    assert len(cache.activity_log) == 1
    assert cache.activity_log[0].extra == {"bounty_wei": WEI // 100}


def test_event_types_do_not_collide_on_a_shared_tx_hash():
    """One tx can burn an NFT and deposit fees; both must survive."""
    cache = TTTCache()
    tx = "0x" + "ab" * 32
    launch(cache, tx_hash=tx, log_index=None)
    deposit(cache, tx_hash=tx, log_index=None)
    buyback(cache, tx_hash=tx, log_index=None)
    assert {e.event_type for e in cache.activity_log} == {"burn", "fee", "buyback"}


def test_same_tx_in_two_blocks_is_treated_as_two_events():
    """Block number is part of the identity (a reorg-replayed tx)."""
    cache = TTTCache()
    deposit(cache, block_number=23_000_000, holder_share_wei=WEI)
    deposit(cache, block_number=23_000_001, holder_share_wei=WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == 2 * WEI


def test_mark_event_seen_reports_first_sighting_only():
    cache = TTTCache()
    assert cache.mark_event_seen("k") is True
    assert cache.mark_event_seen("k") is False


def test_seen_ring_is_bounded_and_evicts_oldest_first():
    cache = TTTCache()
    for i in range(_SEEN_EVENT_RING + 10):
        cache.mark_event_seen(f"key-{i}")
    assert len(cache._seen_events) == _SEEN_EVENT_RING
    assert len(cache._seen_order) == _SEEN_EVENT_RING
    assert "key-0" not in cache._seen_events          # evicted
    assert f"key-{_SEEN_EVENT_RING + 9}" in cache._seen_events


def test_event_key_is_case_insensitive_and_shape_stable():
    a = _event_key(
        tx_hash="0xAB", event_type="fee", token=TOKEN_A.upper(),
        block_number=7, log_index=1,
    )
    b = _event_key(
        tx_hash="0xab", event_type="fee", token=TOKEN_A.lower(),
        block_number=7, log_index=1,
    )
    assert a == b
    # A missing log index is its own identity, distinct from index 0.
    assert _event_key(
        tx_hash="0x1", event_type="fee", token=None, block_number=1
    ) != _event_key(
        tx_hash="0x1", event_type="fee", token=None, block_number=1, log_index=0
    )


# ===========================================================================
# 2. Bucketing, pruning, rolling counters
# ===========================================================================


def test_deposits_in_the_same_hour_share_one_bucket():
    cache = TTTCache()
    hour = int(NOW // 3600) * 3600
    deposit(cache, timestamp=hour + 60, tx_hash="0x" + "01" * 32, holder_share_wei=WEI)
    deposit(cache, timestamp=hour + 120, tx_hash="0x" + "02" * 32, holder_share_wei=WEI)
    assert cache.fees_by_token[TOKEN_A.lower()] == [[float(hour), 2 * WEI]]


def test_deposits_in_different_hours_get_their_own_buckets():
    cache = TTTCache()
    hour = int(NOW // 3600) * 3600
    deposit(cache, timestamp=hour + 60, tx_hash="0x" + "01" * 32)
    deposit(cache, timestamp=hour + 3700, tx_hash="0x" + "02" * 32)
    assert len(cache.fees_by_token[TOKEN_A.lower()]) == 2


def test_prune_old_drops_buckets_past_25h_but_keeps_the_token_entry():
    cache = TTTCache()
    deposit(cache, timestamp=int(NOW - 30 * 3600), tx_hash="0x" + "01" * 32)
    deposit(cache, timestamp=int(NOW - 3600), tx_hash="0x" + "02" * 32)
    cache.prune_old(NOW)
    assert TOKEN_A.lower() in cache.fees_by_token
    assert len(cache.fees_by_token[TOKEN_A.lower()]) == 1


def test_per_token_fees_splits_24h_from_lifetime():
    cache = TTTCache()
    deposit(cache, timestamp=int(NOW - 26 * 3600), tx_hash="0x" + "01" * 32,
            holder_share_wei=5 * WEI)
    deposit(cache, timestamp=int(NOW - 3600), tx_hash="0x" + "02" * 32,
            holder_share_wei=2 * WEI)
    fees_24h, lifetime = cache.per_token_fees(TOKEN_A, NOW)
    assert (fees_24h, lifetime) == (2.0, 7.0)
    assert cache.per_token_fees("0x" + "ff" * 20, NOW) == (0.0, 0.0)


def test_rolling_counters_respect_the_24h_cutoff():
    cache = TTTCache()
    launch(cache, timestamp=int(NOW - 25 * 3600), tx_hash="0x" + "01" * 32)
    launch(cache, timestamp=int(NOW - 3600), tx_hash="0x" + "02" * 32,
           address=TOKEN_B, token_id=43)
    deposit(cache, timestamp=int(NOW - 25 * 3600), tx_hash="0x" + "03" * 32,
            holder_share_wei=9 * WEI)
    deposit(cache, timestamp=int(NOW - 3600), tx_hash="0x" + "04" * 32,
            holder_share_wei=WEI)
    cache.recompute_rolling_counters(NOW)
    assert cache.launches_24h == 1
    assert cache.eth_to_holders_24h_wei == WEI


def test_sample_burns_and_floor_overwrites_within_one_hour():
    cache = TTTCache()
    cache.sample_burns_and_floor(NOW, 100, 0.05)
    cache.sample_burns_and_floor(NOW + 60, 101, 0.06)
    assert list(cache.burns_hourly) == [(_hour_bucket(NOW), 101)]
    assert list(cache.floor_hourly) == [(_hour_bucket(NOW), 0.06)]
    # A new hour appends.
    cache.sample_burns_and_floor(NOW + 3700, 102, 0.07)
    assert len(cache.burns_hourly) == 2


def test_sample_burns_and_floor_ignores_a_missing_or_zero_floor():
    cache = TTTCache()
    cache.sample_burns_and_floor(NOW, 100, None)
    cache.sample_burns_and_floor(NOW, 100, 0.0)
    assert list(cache.floor_hourly) == []
    assert len(cache.burns_hourly) == 1


def test_sample_volume_overwrites_and_rejects_non_numeric():
    cache = TTTCache()
    cache.sample_volume(NOW, 1000.0)
    cache.sample_volume(NOW + 60, 2000.0)
    cache.sample_volume(NOW + 120, "not a number")  # type: ignore[arg-type]
    assert list(cache.volume_hourly) == [(_hour_bucket(NOW), 2000.0)]


def test_activity_ring_buffer_is_bounded():
    cache = TTTCache()
    for i in range(_ACTIVITY_RING_BUFFER + 25):
        deposit(cache, tx_hash="0x" + f"{i:064x}")
    assert len(cache.activity_log) == _ACTIVITY_RING_BUFFER


def test_get_activity_for_display_sorts_by_block_desc_regardless_of_scan_order():
    cache = TTTCache()
    for block in (23_000_005, 23_000_001, 23_000_009):
        deposit(cache, block_number=block, tx_hash="0x" + f"{block:064x}")
    shown = cache.get_activity_for_display(limit=2)
    assert [e.block_number for e in shown] == [23_000_009, 23_000_005]
    assert len(cache.get_activity_for_display(limit=-1)) == 3


def test_deposit_for_an_unknown_token_still_buckets_without_a_symbol():
    cache = TTTCache()
    deposit(cache, token=TOKEN_B)
    row = cache.activity_log[0]
    assert row.token_symbol is None and row.token_id is None
    assert TOKEN_B.lower() in cache.fees_by_token


def test_deposit_after_launch_carries_the_symbol_and_token_id():
    cache = TTTCache()
    launch(cache, token_id=42)
    cache.update_token_metadata(TOKEN_A, "AAA", 18)
    deposit(cache)
    row = cache.activity_log[0]
    assert (row.token_symbol, row.token_id) == ("AAA", 42)


# ===========================================================================
# 3. Token registry patches
# ===========================================================================


def test_register_token_is_insert_if_absent():
    cache = TTTCache()
    cache.register_token(
        token_id=1, address=TOKEN_A.upper(), deployer=ACTOR, launch_block=10
    )
    cache.register_token(
        token_id=999, address=TOKEN_A, deployer=ACTOR, launch_block=99
    )
    assert list(cache.tokens) == [TOKEN_A.lower()]
    assert cache.tokens[TOKEN_A.lower()].token_id == 1


def test_update_helpers_are_no_ops_for_unknown_addresses():
    cache = TTTCache()
    cache.update_token_metadata(TOKEN_A, "X", 18)
    cache.update_token_reservoir(TOKEN_A, 5)
    cache.update_token_fees(TOKEN_A, 1.0, 2.0)
    cache.update_token_market(
        TOKEN_A, price_usd=1.0, change_h24=1.0, volume_h24=1.0, mcap=1.0
    )
    assert cache.tokens == {}


def test_update_helpers_patch_a_frozen_model_in_place():
    cache = TTTCache()
    launch(cache)
    cache.update_token_metadata(TOKEN_A, "AAA", 6)
    cache.update_token_reservoir(TOKEN_A, 7 * WEI)
    cache.update_token_fees(TOKEN_A, 1.5, 9.5)
    cache.update_token_market(
        TOKEN_A, price_usd=0.5, change_h24=-3.0, volume_h24=100.0, mcap=900.0
    )
    t = cache.tokens[TOKEN_A.lower()]
    assert (t.symbol, t.decimals, t.reservoir_wei) == ("AAA", 6, 7 * WEI)
    assert (t.fees_eth_24h, t.fees_eth_lifetime) == (1.5, 9.5)
    assert (t.price_usd, t.price_change_h24, t.market_cap_usd) == (0.5, -3.0, 900.0)


# ===========================================================================
# 4. Persistence round-trip
# ===========================================================================


def _populate(cache: TTTCache) -> None:
    launch(cache)
    cache.update_token_metadata(TOKEN_A, "AAA", 18)
    cache.update_token_reservoir(TOKEN_A, 3 * WEI)
    deposit(cache, tx_hash="0x" + "d1" * 32, holder_share_wei=2 * WEI)
    buyback(cache)
    cache.sample_burns_and_floor(NOW, 1234, 0.05)
    cache.sample_volume(NOW, 9999.0)
    cache.last_seen_block["Deposited"] = 23_000_100
    cache.recompute_rolling_counters(NOW)


def test_save_load_roundtrip_preserves_every_field(tmp_path):
    path = str(tmp_path / "ttt_cache.json")
    src = TTTCache()
    _populate(src)
    src.save_to_file(path)

    dst = TTTCache()
    dst.load_from_file(path)

    assert dst.tokens == src.tokens
    assert dst.fees_by_token == src.fees_by_token
    assert list(dst.burns_hourly) == list(src.burns_hourly)
    assert list(dst.floor_hourly) == list(src.floor_hourly)
    assert list(dst.volume_hourly) == list(src.volume_hourly)
    assert [e.model_dump() for e in dst.activity_log] == [
        e.model_dump() for e in src.activity_log
    ]
    assert dst.last_seen_block == {"Deposited": 23_000_100}
    assert dst.launches_24h == src.launches_24h
    assert dst.eth_to_holders_24h_wei == src.eth_to_holders_24h_wei


def test_save_writes_the_current_schema_version(tmp_path):
    path = str(tmp_path / "ttt_cache.json")
    cache = TTTCache()
    _populate(cache)
    cache.save_to_file(path)
    with open(path) as fh:
        assert json.load(fh)["schema_version"] == _CACHE_SCHEMA_VERSION


def test_reloading_does_not_re_apply_events_across_a_restart(tmp_path):
    """The reorg margin re-delivers events after a restart; they must be known."""
    path = str(tmp_path / "ttt_cache.json")
    src = TTTCache()
    deposit(src, holder_share_wei=WEI)
    src.recompute_rolling_counters(NOW)
    src.save_to_file(path)

    dst = TTTCache()
    dst.load_from_file(path)
    deposit(dst, holder_share_wei=WEI)  # same log, re-scanned after restart
    dst.recompute_rolling_counters(NOW)
    assert dst.eth_to_holders_24h_wei == WEI
    assert len(dst.activity_log) == 1


def test_only_the_tail_of_the_seen_ring_is_persisted(tmp_path):
    path = str(tmp_path / "ttt_cache.json")
    cache = TTTCache()
    for i in range(_SEEN_EVENT_PERSIST + 500):
        cache.mark_event_seen(f"key-{i}")
    cache.save_to_file(path)
    with open(path) as fh:
        keys = json.load(fh)["seen_events"]
    assert len(keys) == _SEEN_EVENT_PERSIST
    assert keys[-1] == f"key-{_SEEN_EVENT_PERSIST + 499}"


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "ttt_cache.json"
    cache = TTTCache()
    _populate(cache)
    cache.save_to_file(str(path))
    assert path.exists()
    assert not (tmp_path / "ttt_cache.json.tmp").exists()


def test_save_to_an_unwritable_path_is_logged_not_raised(tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    cache = TTTCache()
    _populate(cache)
    cache.save_to_file(str(blocker / "sub" / "cache.json"))  # must not raise


# ===========================================================================
# 5. Corrupt / hostile files
# ===========================================================================


def test_load_missing_file_is_a_silent_no_op(tmp_path):
    cache = TTTCache()
    cache.load_from_file(str(tmp_path / "nope.json"))
    assert cache.tokens == {} and cache.last_seen_block == {}


@pytest.mark.parametrize(
    "content", ["", "{not json", "[]", "null", '"a string"', "12"]
)
def test_load_garbage_file_does_not_raise_and_leaves_the_cache_empty(
    tmp_path, content
):
    path = tmp_path / "ttt_cache.json"
    path.write_text(content)
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.tokens == {}
    assert cache.eth_to_holders_24h_wei == 0


def test_load_a_truncated_file_written_mid_save(tmp_path):
    path = tmp_path / "ttt_cache.json"
    good = TTTCache()
    _populate(good)
    good.save_to_file(str(path))
    blob = path.read_text()
    path.write_text(blob[: len(blob) // 2])
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.tokens == {}


def test_load_keeps_the_good_rows_of_a_partially_bad_payload(tmp_path):
    path = tmp_path / "ttt_cache.json"
    good = TTTCache()
    _populate(good)
    good.save_to_file(str(path))
    payload = json.loads(path.read_text())
    payload["tokens"]["0xdeadbeef"] = {"nonsense": True}
    payload["activity_log"].append({"broken": True})
    payload["fees_by_token"]["0xzz"] = [["bad"], [1.0, 2]]
    payload["burns_hourly"].append(["only-one-element"])
    path.write_text(json.dumps(payload))

    cache = TTTCache()
    cache.load_from_file(str(path))
    assert TOKEN_A.lower() in cache.tokens
    assert "0xdeadbeef" not in cache.tokens
    assert all(hasattr(e, "event_type") for e in cache.activity_log)
    assert len(cache.activity_log) == len(good.activity_log)


def test_load_survives_wrong_types_in_scalar_fields(tmp_path):
    path = tmp_path / "ttt_cache.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "last_seen_block": {"Deposited": "not-a-number"},
                "launches_24h": None,
                "eth_to_holders_24h_wei": None,
                "seen_events": [1, 2, "ok"],
            }
        )
    )
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.launches_24h == 0
    assert cache.eth_to_holders_24h_wei == 0
    assert cache.mark_event_seen("ok") is False   # the one valid key survived


# ===========================================================================
# 6. Schema migration — the already-corrupted user caches
# ===========================================================================


def _legacy_payload() -> dict:
    """A v1 file as written by a build carrying CRIT-1: inflated accumulators."""
    hour = float(int(NOW // 3600) * 3600)
    return {
        "saved_at": NOW,
        "tokens": {
            TOKEN_A.lower(): {
                "token_id": 42,
                "address": TOKEN_A.lower(),
                "deployer": ACTOR,
                "launch_block": 23_000_000,
                "symbol": "AAA",
                "decimals": 18,
                "reservoir_wei": 3 * WEI,
            }
        },
        # 120x the truth, exactly the observed inflation after one hour
        "fees_by_token": {TOKEN_A.lower(): [[hour, 120 * WEI]]},
        "burns_hourly": [[hour, 1234]],
        "floor_hourly": [[hour, 0.05]],
        "volume_hourly": [[hour, 9999.0]],
        "activity_log": [
            {
                "tx_hash": "0x" + "11" * 32,
                "block_number": 23_000_000,
                "timestamp": int(NOW),
                "event_type": "fee",
                "token_symbol": "AAA",
                "token_address": TOKEN_A.lower(),
                "actor_address": ACTOR,
                "eth_amount_wei": 3 * WEI,
                "token_id": 42,
                "extra": None,
            }
        ] * 120,
        "last_seen_block": {"Deposited": 23_000_100, "Launched": 23_000_100},
        "launches_24h": 120,
        "eth_to_holders_24h_wei": 120 * WEI,
    }


def test_legacy_cache_has_its_inflated_accumulators_discarded(tmp_path):
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(_legacy_payload()))
    cache = TTTCache()
    cache.load_from_file(str(path))

    # Everything that accumulated is gone rather than silently carried over.
    assert cache.fees_by_token == {}
    assert list(cache.activity_log) == []
    assert cache.eth_to_holders_24h_wei == 0
    assert cache.launches_24h == 0
    assert cache.last_seen_block == {}


def test_legacy_cache_keeps_the_state_that_never_accumulated(tmp_path):
    """Token registry and sparklines are written by overwrite/insert paths."""
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(_legacy_payload()))
    cache = TTTCache()
    cache.load_from_file(str(path))

    assert cache.tokens[TOKEN_A.lower()].symbol == "AAA"
    assert cache.tokens[TOKEN_A.lower()].reservoir_wei == 3 * WEI
    assert len(cache.burns_hourly) == 1
    assert len(cache.floor_hourly) == 1
    assert len(cache.volume_hourly) == 1


def test_a_file_with_no_version_word_is_treated_as_legacy(tmp_path):
    payload = _legacy_payload()
    payload.pop("schema_version", None)
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(payload))
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.eth_to_holders_24h_wei == 0


@pytest.mark.parametrize("version", ["1", None, "garbage", 0])
def test_unparseable_version_words_fall_back_to_legacy_handling(tmp_path, version):
    payload = _legacy_payload()
    payload["schema_version"] = version
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(payload))
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.fees_by_token == {}
    assert cache.tokens                      # registry still kept


def test_a_current_version_file_is_loaded_untouched(tmp_path):
    payload = _legacy_payload()
    payload["schema_version"] = _CACHE_SCHEMA_VERSION
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(payload))
    cache = TTTCache()
    cache.load_from_file(str(path))
    assert cache.eth_to_holders_24h_wei == 120 * WEI
    assert cache.last_seen_block == {"Deposited": 23_000_100, "Launched": 23_000_100}


def test_migration_then_save_upgrades_the_file_on_disk(tmp_path):
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(_legacy_payload()))
    cache = TTTCache()
    cache.load_from_file(str(path))
    cache.save_to_file(str(path))

    reloaded = TTTCache()
    reloaded.load_from_file(str(path))
    assert json.loads(path.read_text())["schema_version"] == _CACHE_SCHEMA_VERSION
    # Second load is a no-op migration: the fees stay empty, not re-dropped.
    assert reloaded.tokens[TOKEN_A.lower()].symbol == "AAA"


def test_migration_logs_a_warning_naming_the_file(tmp_path, caplog):
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(_legacy_payload()))
    with caplog.at_level("WARNING"):
        TTTCache().load_from_file(str(path))
    messages = [r.getMessage() for r in caplog.records]
    assert any("schema v1" in m and str(path) in m for m in messages)


def test_a_rebuilt_cache_reports_the_true_number_after_migration(tmp_path):
    """End state: the inflated 120 ETH is replaced by the real 1 ETH."""
    path = tmp_path / "ttt_cache.json"
    path.write_text(json.dumps(_legacy_payload()))
    cache = TTTCache()
    cache.load_from_file(str(path))
    deposit(cache, holder_share_wei=WEI)   # what the rescan actually finds
    deposit(cache, holder_share_wei=WEI)   # ...re-delivered by the next poll
    cache.recompute_rolling_counters(NOW)
    assert cache.eth_to_holders_24h_wei == WEI


def test_a_replayed_launch_can_re_register_a_token_lost_from_the_registry():
    """Registry and seen-ring can disagree after a partial load; heal, don't skip."""
    cache = TTTCache()
    launch(cache)
    cache.tokens.clear()          # e.g. the tokens block failed validation
    launch(cache)                 # same log, re-delivered by the next scan
    assert TOKEN_A.lower() in cache.tokens
    assert len(cache.activity_log) == 1     # still no duplicate feed row
