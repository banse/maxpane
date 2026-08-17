"""WP1.2 — the optimal-split ``≈ W/k`` weight signature.

An operator splitting a pot across *k* equal deposits leaves a machine-scale
signature: *k* byte-identical amounts whose implied pot no human splits by
hand.  ``split_edges`` corroborates such groups — and it stays inside the
``amount`` family on purpose: a split is *evidence about* an amount group, so
it may raise the family's strength but can never be the second family the
cluster gate needs.
"""

from __future__ import annotations

from sybilkit import Dataset, DetectConfig
from sybilkit.signals.split import split_edges

from tests.conftest import component_containing

CFG = DetectConfig()


def test_the_045_farms_equal_split_fires_on_the_population(
    population_ds,
) -> None:
    """1 995 × 0.45 ETH is an 897.75 ETH pot — the research's worked example
    of the optimal-split signature."""
    edges = split_edges(population_ds, CFG)
    assert edges
    with_045 = [
        e for e in edges if "0.45" in e.reason.human_string
    ]
    assert with_045
    comp = component_containing(with_045, with_045[0].a)
    assert len(comp) > 1900


def test_split_edges_stay_in_the_amount_family(population_ds) -> None:
    """Never a second family: the ≥2-family gate must not be reachable by
    amount evidence wearing two hats."""
    edges = split_edges(population_ds, CFG)
    assert edges
    assert {e.family for e in edges} == {"amount"}


def test_a_human_scale_pot_does_not_fire() -> None:
    """Five friends sending 0.45 each is a 2.25 ETH pot, not a split farm."""
    amt = 450_000_000_000_000_000
    rows = [
        {
            "contributor": f"0x{i:040x}",
            "hour": 1,
            "amount_wei": amt,
            "credited_delta_wei": amt,
            "weight_added_wei": amt,
            "new_weight_wei": amt,
            "tx_count": 1,
            "block_number": 100 + i,
            "tx_hash": "0x" + f"{i:064x}",
            "log_index": 1,
        }
        for i in range(5)
    ]
    ds = Dataset.from_events(rows, [])
    assert split_edges(ds, CFG) == []


def test_the_reason_names_the_split_shape(population_ds) -> None:
    edges = split_edges(population_ds, CFG)
    assert any("W/k" in e.reason.human_string for e in edges)


def test_no_edges_from_an_empty_dataset() -> None:
    assert split_edges(Dataset(deposits=(), first_index={}, txs={}, funding={}), CFG) == []
