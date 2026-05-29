"""Tests for the Talismans dashboard cache (WP3b)."""

from __future__ import annotations

import time

from maxpane_dashboard.data.talismans_cache import TalismansCache
from maxpane_dashboard.data.talismans_models import (
    TalismanActivityEvent,
    TalismanToken,
)


def _tok(token_id: int, **kw) -> TalismanToken:
    base = dict(
        token_id=token_id,
        owner="0x" + "a" * 40,
        core_count=1,
        material_id=16,
        essence="Lithic",
        form=0,
        seed=0,
        tier="Raw",
        is_genesis=token_id <= 1536,
    )
    base.update(kw)
    return TalismanToken(**base)


def _ev(op_type="bond", token_id_a=1, tx_hash="0xabc", block_number=100, **kw):
    base = dict(
        tx_hash=tx_hash,
        block_number=block_number,
        timestamp=kw.pop("timestamp", 1000),
        op_type=op_type,
        token_id_a=token_id_a,
        token_id_b=kw.pop("token_id_b", 2),
        result_id=kw.pop("result_id", 3),
        operator="0x" + "b" * 40,
    )
    base.update(kw)
    return TalismanActivityEvent(**base)


def test_seed_genesis_ids():
    c = TalismansCache()
    c.seed_genesis_ids()
    assert len(c.known_ids) == 1536
    assert 1 in c.known_ids
    assert 1536 in c.known_ids
    assert 0 not in c.known_ids
    assert 1537 not in c.known_ids


def test_register_result_ids():
    c = TalismansCache()
    c.register_result_ids({"result_id": 5000, "result_id_b": 5001})
    assert 5000 in c.known_ids
    assert 5001 in c.known_ids
    # None result_id_b is not added
    c.register_result_ids({"result_id": 6000, "result_id_b": None})
    assert 6000 in c.known_ids
    # missing result_id_b key
    c.register_result_ids({"result_id": 7000})
    assert 7000 in c.known_ids


def test_apply_operation_dedupe():
    c = TalismansCache()
    ev = _ev(op_type="cut", tx_hash="0xdead", token_id_a=10)
    c.apply_operation(ev)
    c.apply_operation(ev)  # same dedupe key -> ignored
    assert c.operations_total == 1
    assert len(c.activity_log) == 1


def test_apply_operation_bond_increments_mythics():
    c = TalismansCache()
    c.apply_operation(_ev(op_type="bond", tx_hash="0x1", token_id_a=1))
    c.apply_operation(_ev(op_type="bond", tx_hash="0x2", token_id_a=4))
    c.apply_operation(_ev(op_type="cut", tx_hash="0x3", token_id_a=9))
    assert c.mythics_ever_forged == 2
    assert c.operations_total == 3


def test_apply_operation_ops_hourly_bucket():
    c = TalismansCache()
    base = 100000.0
    c.apply_operation(_ev(tx_hash="0xa", token_id_a=1, timestamp=int(base)))
    c.apply_operation(_ev(tx_hash="0xb", token_id_a=2, timestamp=int(base + 10)))
    # same hour -> single bucket, count 2
    assert len(c.ops_hourly) == 1
    assert c.ops_hourly[-1][1] == 2


def test_activity_sort_by_block_desc():
    c = TalismansCache()
    c.apply_operation(_ev(tx_hash="0x1", token_id_a=1, block_number=50))
    c.apply_operation(_ev(tx_hash="0x2", token_id_a=2, block_number=200))
    c.apply_operation(_ev(tx_hash="0x3", token_id_a=3, block_number=100))
    disp = c.get_activity_for_display(limit=25)
    assert [e.block_number for e in disp] == [200, 100, 50]


def test_sample_distribution_overwrites_same_hour():
    c = TalismansCache()
    now = 200000.0
    c.sample_distribution(now, mythic_count=5, token_count=100)
    c.sample_distribution(now + 30, mythic_count=6, token_count=101)
    assert len(c.mythic_hourly) == 1
    assert len(c.tokencount_hourly) == 1
    assert c.mythic_hourly[-1][1] == 6
    assert c.tokencount_hourly[-1][1] == 101


def test_invariant_baseline_sets_once():
    c = TalismansCache()
    c.set_invariant_baseline_if_unset(0)
    assert c.cores_invariant_baseline == 0  # 0 input not set
    c.set_invariant_baseline_if_unset(500)
    assert c.cores_invariant_baseline == 500
    c.set_invariant_baseline_if_unset(999)  # already set -> no change
    assert c.cores_invariant_baseline == 500


def test_set_token_states_replaces():
    c = TalismansCache()
    c.set_token_states({1: _tok(1)})
    assert set(c.tokens.keys()) == {1}
    c.set_token_states({2: _tok(2), 3: _tok(3)})
    assert set(c.tokens.keys()) == {2, 3}


def test_save_load_round_trip(tmp_path):
    c = TalismansCache()
    c.seed_genesis_ids()
    c.set_token_states({1: _tok(1, essence="Mythic", material_id=32, tier="Raw")})
    c.apply_operation(_ev(tx_hash="0x1", token_id_a=1, block_number=50, op_type="cut"))
    c.apply_operation(_ev(tx_hash="0x2", token_id_a=2, block_number=200, op_type="bond"))
    c.sample_distribution(123456.0, mythic_count=1, token_count=3)
    c.set_invariant_baseline_if_unset(42)
    c.last_seen_block["ops"] = 999
    path = tmp_path / "talismans_cache.json"
    c.save_to_file(str(path))

    c2 = TalismansCache()
    c2.load_from_file(str(path))
    assert c2.tokens[1].essence == "Mythic"
    assert 1 in c2.known_ids and 1536 in c2.known_ids
    assert c2.operations_total == 2
    assert c2.mythics_ever_forged == 1
    assert c2.cores_invariant_baseline == 42
    assert c2.last_seen_block["ops"] == 999
    # activity order preserved (newest first by appendleft)
    disp = c2.get_activity_for_display(25)
    assert [e.block_number for e in disp] == [200, 50]
    # dedupe set restored -> re-applying same tx is a no-op
    c2.apply_operation(_ev(tx_hash="0x1", token_id_a=1, block_number=50, op_type="cut"))
    assert c2.operations_total == 2


def test_load_missing_file_is_noop(tmp_path):
    c = TalismansCache()
    c.load_from_file(str(tmp_path / "does_not_exist.json"))
    assert c.tokens == {}
    assert c.operations_total == 0
