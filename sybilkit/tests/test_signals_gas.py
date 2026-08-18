"""WP1.4 — the ``gas`` family: fee/limit uniformity classes over ``ds.txs``.

The uniformity is the signal, never the value (research §5.2): 0.035 gwei is
a common honest default, 0.1 gwei shared by a whole wave is an operator.  So
gas never *groups* the population — it corroborates a component the tier-A
families already built, by asking whether that component collapses to one
fingerprint while the population stays diverse.

The None discipline (controller ruling 3): 18 of the 220 sampled txs are
legacy type-0 with **no** priority fee.  A ``None`` never joins a uniformity
class — folding it would invent a 28th class or a fake uniformity — so an
axis with any ``None`` is *unjudgeable*, and the distinct-control-priority-fee
count is 27 **excluding** ``None``.
"""

from __future__ import annotations

from sybilkit import Dataset, DetectConfig
from sybilkit.signals.gas import gas_edges

CFG = DetectConfig()


def _tx_of(ds, addr):
    dep = min(
        (d for d in ds.deposits if d.contributor == addr),
        key=lambda d: (d.block_number, d.log_index),
    )
    return ds.txs.get(dep.tx_hash)


def test_the_fixture_facts_the_family_is_built_on(labeled_ds, labeled_truth) -> None:
    """The measured collapse: the 0.45 and 10.0 farms are one priority fee +
    one gas limit each, while the 60 controls spread over 27 priority fees
    (excluding the two legacy Nones) and 15 gas limits."""
    for cl in ("amt_0.45_h3", "amt_10.0_h5"):
        txs = [_tx_of(labeled_ds, a) for a in labeled_truth["members_of"][cl]]
        assert len({t.max_priority_fee_wei for t in txs}) == 1
        assert len({t.gas_limit for t in txs}) == 1
    control_txs = [_tx_of(labeled_ds, a) for a in labeled_truth["controls"]]
    pfs = {t.max_priority_fee_wei for t in control_txs if t.max_priority_fee_wei is not None}
    assert len(pfs) == 27  # EXCLUDING None -- ruling 3's exact number
    assert sum(1 for t in control_txs if t.max_priority_fee_wei is None) == 2
    assert len({t.gas_limit for t in control_txs}) == 15


def test_gas_corroborates_the_uniform_farms(labeled_ds, labeled_truth) -> None:
    edges = gas_edges(labeled_ds, CFG)
    assert edges
    touched = {e.a for e in edges} | {e.b for e in edges}
    for cl in ("amt_0.45_h3", "amt_10.0_h5"):
        assert labeled_truth["members_of"][cl] <= touched
    for e in edges:
        assert e.family == "gas"
        assert 0.0 < e.strength <= 1.0


def test_gas_never_merges_two_farms_that_share_a_fingerprint(
    labeled_ds, labeled_truth
) -> None:
    """0.45 and 10.0 share (0.1 gwei, 91 600) exactly.  Gas corroborates each
    component internally; no edge may cross them, or the shared honest-ish
    default would weld unrelated groups."""
    edges = gas_edges(labeled_ds, CFG)
    m045 = labeled_truth["members_of"]["amt_0.45_h3"]
    m100 = labeled_truth["members_of"]["amt_10.0_h5"]
    for e in edges:
        assert not (e.a in m045 and e.b in m100)
        assert not (e.a in m100 and e.b in m045)


def test_a_two_priority_fee_farm_still_corroborates_on_its_gas_limit(
    labeled_ds, labeled_truth
) -> None:
    """The 14.0 drip runs two priority fees (one of them the fingerprint-odd
    11 500 001 wei) over a single 150 000 gas limit: a collapsed limit with a
    ≤2-value fee is still machine uniformity, at reduced strength."""
    edges = gas_edges(labeled_ds, CFG)
    m14 = labeled_truth["members_of"]["amt_14.0_h4"]
    touching = [e for e in edges if e.a in m14 or e.b in m14]
    assert touching
    assert all(e.strength < 0.85 for e in touching)


def test_an_all_legacy_component_is_unjudgeable_not_uniform(
    labeled_ds, labeled_truth
) -> None:
    """The 0.1 farm is pure type-0: priority fee and max fee are ``None``
    across the board, leaving one judgeable axis — not enough.  This is the
    None-fold trap: treating the Nones as a shared value would fire gas here
    and convict the farm-shaped control sitting in the same window."""
    edges = gas_edges(labeled_ds, CFG)
    m01 = labeled_truth["members_of"]["amt_0.1_h17"]
    for e in edges:
        assert e.a not in m01 and e.b not in m01


def test_a_mixed_none_axis_is_unjudgeable() -> None:
    """Five wallets share a gas limit; three carry a priority fee of X and two
    are legacy ``None``.  The fee axis must not read as 'one class of X'."""
    amt = 3_000_000_000_000_000_000  # odd → one amount component
    rows, txs = [], []
    for i in range(5):
        addr = f"0x{i + 1:040x}"
        tx_hash = "0x" + f"{i + 1:064x}"
        rows.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amt + 1,  # odd amount, byte-identical
                "credited_delta_wei": amt,
                "weight_added_wei": amt,
                "new_weight_wei": amt,
                "tx_count": 1,
                "block_number": 1000 + i * 100,
                "tx_hash": tx_hash,
                "log_index": i,
            }
        )
        legacy = i >= 3
        txs.append(
            {
                "tx_hash": tx_hash,
                "nonce": 0,
                "max_priority_fee_wei": None if legacy else 100_000_000,
                "max_fee_wei": None if legacy else 150_000_000 + i,
                "gas_limit": 91_600,
                "tx_type": 0 if legacy else 2,
            }
        )
    ds = Dataset.from_events(rows, [], txs=txs)
    assert gas_edges(ds, CFG) == []


def test_empty_txs_means_no_edges_tier_a_only(labeled_truth) -> None:
    """The normal first-cycle state: tier A only, gas silent — an honest loss
    of recall under the ≥2-family gate, never a fake fingerprint."""
    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset(txs=False)
    assert ds.txs == {}
    assert gas_edges(ds, CFG) == []


# ---- review finding #2: one transaction is one fingerprint ----------------
#
# The uniformity test asks whether a component's members *agree*.  Members
# whose first deposits ride the SAME transaction cannot disagree — they carry
# one fee tuple by construction — so counting them per member hands the test
# N copies of one measurement and every axis collapses for free.

AMT_ODD = 3_333_000_000_000_000_001  # odd → one byte-identical amount component


def _wave(n, tx_of, *, block_of=None):
    """*n* single-deposit wallets on one odd amount, whose first deposits ride
    the transactions ``tx_of(i)`` names — one uniform fee tuple per distinct
    transaction, so uniformity is guaranteed and only the *count* is at issue.
    """
    block_of = block_of or (lambda i: 1000 + i)
    rows, txs, seen = [], [], set()
    for i in range(n):
        tx_hash = tx_of(i)
        rows.append(
            {
                "contributor": "0x" + "aa" * 4 + f"{i:032x}",
                "hour": 1,
                "amount_wei": AMT_ODD,
                "credited_delta_wei": AMT_ODD,
                "weight_added_wei": AMT_ODD,
                "new_weight_wei": AMT_ODD,
                "tx_count": 1,
                "block_number": block_of(i),
                "tx_hash": tx_hash,
                "log_index": i,
            }
        )
        if tx_hash not in seen:
            seen.add(tx_hash)
            txs.append(
                {
                    "tx_hash": tx_hash,
                    "nonce": 0,
                    "max_priority_fee_wei": 100_000_000,
                    "max_fee_wei": 150_000_000,
                    "gas_limit": 91_600,
                    "tx_type": 2,
                }
            )
    return Dataset.from_events(rows, [], txs=txs)


def _hash(i):
    return "0x" + "bb" * 4 + f"{i:056x}"


def test_a_group_whose_first_deposits_share_one_transaction_yields_no_gas_edge() -> None:
    """Six wallets credited by one router call: one transaction, therefore one
    fee tuple, therefore no agreement to measure.  It used to read as six
    agreeing fingerprints and fire at the two-axis strength."""
    ds = _wave(6, lambda i: _hash(0), block_of=lambda i: 1000)
    assert gas_edges(ds, CFG) == []


def test_the_uniformity_count_is_distinct_transactions_not_members() -> None:
    """Six members, five transactions (two members share one).  The group is
    fully covered and still fires — but the number the reason carries is the
    five measurements, not the six wallets."""
    ds = _wave(6, lambda i: _hash(min(i, 4)))
    edges = gas_edges(ds, CFG)
    assert edges
    assert {e.strength for e in edges} == {0.85}
    assert all("×5" in e.reason.human_string for e in edges)
    assert not any("×6" in e.reason.human_string for e in edges)


def test_a_router_batched_wave_cannot_reach_the_two_axis_strength() -> None:
    """Ten wallets across two batch transactions.  Coverage is perfect and
    every axis collapses, but two measurements are below ``min_size`` and a
    fee fingerprint of two transactions is not evidence about ten wallets."""
    ds = _wave(10, lambda i: _hash(i // 5), block_of=lambda i: 1000 + i // 5)
    assert gas_edges(ds, CFG) == []


def test_a_group_with_enough_distinct_transactions_still_fires() -> None:
    """The over-correction guard: deduping by transaction must not silence the
    ordinary case, where every member sent its own."""
    ds = _wave(6, _hash)
    edges = gas_edges(ds, CFG)
    assert edges
    assert {e.strength for e in edges} == {0.85}
    assert all("×6" in e.reason.human_string for e in edges)
