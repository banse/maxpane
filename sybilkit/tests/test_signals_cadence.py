"""WP1.3 — the ``cadence`` family: per-block bursts and the metronomic drip.

Measured shapes this family exists for:

* the 0.45 wave lands **exactly 20 or 30 wallets per block** (90 blocks with
  ≥ 5, covering 1 975 wallets) — burst quantization, research §4;
* the 14.0 farm is a **1-per-2-to-4-blocks metronome** for ten hours
  (654 gaps of 2, 228 of 3) — the drip, research §5.4;
* the 2.067 operator drips the same way inside each of its two waves.

And the negative it must respect: organic deposits scatter — a random
walk-in crowd produces no cadence edge.
"""

from __future__ import annotations

from sybilkit import Dataset, DetectConfig
from sybilkit.signals.cadence import cadence_edges

from tests.conftest import connected_sets

CFG = DetectConfig()

AMT_045 = 450_000_000_000_000_000
AMT_14 = 14 * 10**18
AMT_2067 = 2_067_000_000_000_000_000


def _synthetic(rows_spec) -> Dataset:
    rows = []
    for i, (block, amount) in enumerate(rows_spec):
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
    return Dataset.from_events(rows, [])


def _amount_of(ds):
    return {d.contributor: d.amount_wei for d in ds.deposits}


def test_the_045_burst_quantization_is_found(population_ds) -> None:
    edges = cadence_edges(population_ds, CFG)
    amount_of = _amount_of(population_ds)
    burst_045 = {
        a
        for c in connected_sets(edges)
        for a in c
        if amount_of.get(a) == AMT_045
    }
    assert len(burst_045) >= 1900
    assert any(
        "×20" in e.reason.human_string or "×30" in e.reason.human_string
        for e in edges
    )


def test_the_140_metronomic_drip_is_found(population_ds) -> None:
    """No two 14.0 deposits share a block — only the drip rule can see this
    farm's cadence.

    The regularity rule fragments the ten-hour stream into strictly-regular
    sub-runs, so coverage is 527 of 1 003 rather than all of them — and that
    is enough on purpose: cadence hands the *component* its second family,
    and the byte-identical 14.0 amount is what unites the component."""
    edges = cadence_edges(population_ds, CFG)
    amount_of = _amount_of(population_ds)
    drip_14 = {
        a for c in connected_sets(edges) for a in c if amount_of.get(a) == AMT_14
    }
    assert len(drip_14) >= 500
    assert any("drip" in e.reason.human_string for e in edges)


def test_each_2067_wave_drips_on_its_own_slice(population_ds) -> None:
    """WP1.3's corroboration half: the two waves are 1 316 blocks apart, so
    cadence sees two separate drips — uniting them is the amount family's job,
    asserted at combiner level in WP1.5."""
    edges = cadence_edges(population_ds, CFG)
    amount_of = _amount_of(population_ds)
    comps = [
        {a for a in c if amount_of.get(a) == AMT_2067}
        for c in connected_sets(edges)
    ]
    waves = sorted((len(c) for c in comps if len(c) >= 40), reverse=True)
    assert len(waves) >= 2  # measured: 104 (h13) + 46/41 (h18, two sub-runs)


def test_the_labeled_burst_slice_fires_in_sample(labeled_ds, labeled_truth) -> None:
    """idxrun_13326's sample lands 6 wallets in one block with jitter amounts
    inside ±tol — a burst even at sample density."""
    edges = cadence_edges(labeled_ds, CFG)
    members = labeled_truth["members_of"]["idxrun_13326"]
    hit = {a for c in connected_sets(edges) for a in c} & members
    assert len(hit) >= 5


def test_a_random_scatter_produces_no_cadence_edge() -> None:
    """The brief's named negative: organic deposits — distinct amounts,
    irregular spacing — produce nothing."""
    import random

    rng = random.Random(4)
    block = 1000
    spec = []
    for i in range(40):
        block += rng.choice([1, 2, 3, 5, 9, 17, 40])
        spec.append((block, 10**16 * rng.randrange(3, 4000)))
    ds = _synthetic(spec)
    assert cadence_edges(ds, CFG) == []


def test_a_same_block_crowd_with_unrelated_amounts_is_not_a_burst() -> None:
    """A busy block is not a farm: five deposits in one block whose amounts
    share nothing produce no burst."""
    ds = _synthetic([(1000, 10**16 * (3**i)) for i in range(1, 6)])
    assert cadence_edges(ds, CFG) == []


def test_a_drip_needs_regular_gaps_not_just_small_ones() -> None:
    """Same amount, small but wildly irregular gaps: churn, not a metronome."""
    amt = 300_000_000_000_000_000
    blocks = [1000, 1001, 1009, 1010, 1018, 1019, 1027, 1028, 1036, 1037]
    ds = _synthetic([(b, amt) for b in blocks])
    edges = [e for e in cadence_edges(ds, CFG) if "drip" in e.reason.human_string]
    assert edges == []


def test_no_edges_from_an_empty_dataset() -> None:
    assert (
        cadence_edges(Dataset(deposits=(), first_index={}, txs={}, funding={}), CFG)
        == []
    )
