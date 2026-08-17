"""WP1.3 — the ``sequence`` family: consecutive ``FirstDeposit``-index runs.

The research §5.3 pattern: a farm registers its wallets back-to-back, so the
protocol's own 1-based join counter hands them consecutive indices, packed
into a couple of blocks, with (near-)identical amounts.  Measured on the
committed population: 1 975 of the 2 002 single-deposit 0.45 wallets sit
inside such runs.
"""

from __future__ import annotations

from sybilkit import Dataset, DetectConfig
from sybilkit.signals.sequence import sequence_edges

from tests.conftest import connected_sets

CFG = DetectConfig()


def _synthetic(indices_blocks_amounts) -> Dataset:
    rows = []
    firsts = []
    for i, (index, block, amount) in enumerate(indices_blocks_amounts):
        addr = f"0x{i + 1:040x}"
        rows.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": block,
                "tx_hash": "0x" + f"{i + 1:064x}",
                "log_index": i,
            }
        )
        firsts.append({"contributor": addr, "index": index})
    return Dataset.from_events(rows, firsts)


def test_the_consecutive_index_run_over_the_045_farm_is_found(population_ds) -> None:
    """The named WP1.3 case: the 0.45 wave's consecutive join indices."""
    edges = sequence_edges(population_ds, CFG)
    assert edges
    amount_of = {d.contributor: d.amount_wei for d in population_ds.deposits}
    farm_comps = [
        comp
        for comp in connected_sets(edges)
        if sum(1 for a in comp if amount_of.get(a) == 450_000_000_000_000_000) >= 5
    ]
    covered = set().union(*farm_comps) if farm_comps else set()
    farm_covered = sum(
        1 for a in covered if amount_of.get(a) == 450_000_000_000_000_000
    )
    assert farm_covered >= 1900


def test_the_jitter_run_is_found_despite_no_two_equal_amounts(population_ds) -> None:
    """Index run 12 058–12 157: randomized amounts (~0.118Ξ), two blocks —
    near-identical is enough; byte-equality is not required."""
    edges = sequence_edges(population_ds, CFG)
    run_addrs = {
        addr
        for addr, idx in population_ds.first_index.items()
        if 12_058 <= idx <= 12_157
    }
    comps = [c for c in connected_sets(edges) if c & run_addrs]
    biggest = max((c & run_addrs for c in comps), default=set(), key=len)
    assert len(biggest) >= 90


def test_every_edge_is_sequence_family(population_ds) -> None:
    edges = sequence_edges(population_ds, CFG)
    assert edges
    for e in edges[:50]:
        assert e.family == "sequence"
        assert e.reason.family == "sequence"
        assert 0.0 < e.strength <= 1.0


def test_a_run_needs_tight_blocks_not_just_consecutive_indices() -> None:
    """Consecutive indices with hours between them are organic churn, not a
    registration burst: > 2 blocks of spacing breaks the run."""
    amt = 100_000_000_000_000_000
    ds = _synthetic([(i, 1000 + i * 50, amt) for i in range(1, 11)])
    assert sequence_edges(ds, CFG) == []


def test_a_run_needs_near_identical_amounts() -> None:
    """Ten consecutive indices in one block, but every amount is its own
    order of magnitude: a busy block, not a farm."""
    ds = _synthetic([(i, 1000, 10**16 * (2**i)) for i in range(1, 11)])
    assert sequence_edges(ds, CFG) == []


def test_a_short_run_is_below_the_floor() -> None:
    """Three neighbours with matching amounts happen by chance; a run only
    counts from ``min_size``."""
    amt = 100_000_000_000_000_000
    ds = _synthetic([(i, 1000, amt) for i in range(1, 4)])
    assert sequence_edges(ds, CFG) == []
    ds5 = _synthetic([(i, 1000, amt) for i in range(1, 6)])
    assert len(connected_sets(sequence_edges(ds5, CFG))[0]) == 5


def test_no_edges_from_an_empty_dataset() -> None:
    assert (
        sequence_edges(Dataset(deposits=(), first_index={}, txs={}, funding={}), CFG)
        == []
    )
