"""Hygiene and fact pins for ``sybilkit``'s own committed fixtures.

The mirror of the maxpane side's ``tests/data/test_curator_sybil_data.py``, cut
down to what this distribution can prove on its own: it has no access to
``docs/curator_sybil_data/`` (that lives in the other repo), so it asserts the
fixtures' internal consistency and the facts the benchmark gate will stand on.

Nothing here opens a socket, and nothing here writes — the two gzipped
population archives are decompressed in memory, never onto disk.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from tests.sybilkit_fixtures import FIXTURES, POPULATION, labeled_subset, load, slices


def test_the_reader_returns_a_sorted_list_of_the_committed_fixtures() -> None:
    names = [p.name for p in slices()]
    assert names == sorted(names)
    assert set(names) == {"labeled_subset.json", *POPULATION}


def test_no_fixture_carries_an_api_key() -> None:
    """Keyless by hard constraint, asserted over the bytes rather than intent."""
    for path in slices():
        if path.suffix == ".gz":
            continue
        text = path.read_text("utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"


def test_the_population_stays_gzipped() -> None:
    """``deposits.json`` unpacks to ~12 MB.  An uncompressed copy beside the
    archive is an untracked file the next ``git status`` reads as a change
    nobody made, and it is what happens the first time a test writes one out
    instead of streaming it."""
    loose = [p.name for p in FIXTURES.iterdir() if p.name.endswith(".json")]
    assert loose == ["labeled_subset.json"]
    for name in POPULATION:
        assert (FIXTURES / name).is_file()


def test_the_full_population_is_the_whole_sweep_not_a_sample() -> None:
    """WP2's segment tests assert population statistics; a precision floor
    measured on a convenient subset is a floor that passes for the wrong
    reason."""
    deposits = load("deposits.json.gz")
    first = load("first_deposits.json.gz")
    assert len(deposits) == 22_319
    assert len(first) == 15_576
    # The join index is 1-based and contiguous, exactly like the source event.
    indices = sorted(f["index"] for f in first)
    assert indices == list(range(1, len(first) + 1))
    assert len({d["contributor"].lower() for d in deposits}) == len(first)


def test_the_deposit_rows_satisfy_the_contract_s_own_weight_identity() -> None:
    """``weight_added = credited_delta * early_bps // 10_000``, floored, on all
    22 319 rows.  If the archive were ever re-cut with a lossy transform, this
    is what would catch it -- and it is the identity WP1's curve tests lean on.
    """
    for d in load("deposits.json.gz"):
        assert d["weight_added_wei"] == (
            d["credited_delta_wei"] * d["early_bps"] // 10_000
        )


def test_the_labeled_subset_is_the_sixteen_operators_and_the_sixty_controls() -> None:
    subset = labeled_subset()
    assert subset["meta"]["n_clusters"] == 16
    assert subset["meta"]["n_members"] == 160
    assert subset["meta"]["n_controls"] == 60
    assert len(subset["clusters"]) == 16
    labels = Counter(m["cluster"] for m in subset["members"])
    assert set(labels.values()) == {10}
    assert {c["cluster"] for c in subset["clusters"]} == set(labels)
    # Cluster labels are preserved, which is the whole point of a *labeled*
    # subset: without them the gate can measure recall but not precision.
    assert all(m["cluster"] for m in subset["members"])
    assert all(c["cluster"] is None for c in subset["controls"])


def test_the_subset_carries_everything_a_dataset_needs() -> None:
    """Self-contained, so the gate runs offline with no second file.

    Deposit rows (amount, block, hour, tx hash, log index), the 1-based join
    index, the tier-B fingerprint and the tier-C funder -- the four inputs
    ``Dataset.from_events`` takes, for all 220 addresses.
    """
    subset = labeled_subset()
    everyone = subset["members"] + subset["controls"]
    assert len(everyone) == 220
    for row in everyone:
        assert row["address"] == row["address"].lower()
        assert row["first_index"] >= 1
        assert row["deposits"]
        assert set(row["tx"]) == {
            "tx_hash", "nonce", "max_priority_fee_wei", "max_fee_wei",
            "gas_limit", "tx_type",
        }
        for d in row["deposits"]:
            assert isinstance(d["amount_wei"], int) and d["amount_wei"] > 0
            assert isinstance(d["block_number"], int)
            assert d["tx_hash"].startswith("0x")


def test_the_funding_signal_the_gate_will_stand_on() -> None:
    """10/10 on a fully-resolved farm sample, 0/47 across the controls.

    The strongest measured discriminator on this population, and the reason
    tier C is worth a bounded background sweep at all.  A run of the combiner
    that loses the funding family loses this, and the benchmark gate is where
    that shows up.
    """
    subset = labeled_subset()
    farm = [
        m
        for m in subset["members"]
        if m["cluster"] == "amt_0.45_h3" and (m["funding"] or {}).get("funder")
    ]
    assert len(farm) == 10
    assert all(m["funding"]["funder_in_cluster"] is True for m in farm)

    controls = [c for c in subset["controls"] if (c["funding"] or {}).get("funder")]
    assert len(controls) == 47
    assert not [c for c in controls if c["funding"]["funder_in_cluster"]]


def test_an_unresolved_funder_is_null_and_never_false() -> None:
    """Tri-state, and the library's whole ``None``-is-not-``0`` rule starts
    here: ``funder_in_cluster is None`` means the bounded lookup found no
    funder, which is not the same claim as "the funder was outside the
    cluster"."""
    subset = labeled_subset()
    everyone = subset["members"] + subset["controls"]
    unresolved = [r for r in everyone if r["funding"] and r["funding"]["funder"] is None]
    assert unresolved
    assert all(r["funding"]["funder_in_cluster"] is None for r in unresolved)
    resolved = [r for r in everyone if r["funding"] and r["funding"]["funder"]]
    assert len(resolved) == 177
    assert all(isinstance(r["funding"]["funder_in_cluster"], bool) for r in resolved)


def test_the_gas_uniformity_the_benchmark_expects() -> None:
    """Each audited operator's sampled transactions collapse to one gas limit;
    the 0.45 and 10.0 groups collapse to the *same* priority fee and gas limit,
    which is what makes them one operator rather than two."""
    subset = labeled_subset()
    by_cluster: dict[str, list[dict]] = {}
    for m in subset["members"]:
        by_cluster.setdefault(m["cluster"], []).append(m["tx"])

    def spread(cid: str) -> tuple[int, int]:
        sample = by_cluster[cid]
        fees = {
            t["max_priority_fee_wei"]
            for t in sample
            if t["max_priority_fee_wei"] is not None
        }
        return len(fees), len({t["gas_limit"] for t in sample})

    assert spread("amt_0.45_h3") == (1, 1)
    assert spread("amt_10.0_h5") == (1, 1)
    shared = {
        (t["max_priority_fee_wei"], t["gas_limit"])
        for cid in ("amt_0.45_h3", "amt_10.0_h5")
        for t in by_cluster[cid]
    }
    assert shared == {(100_000_000, 91_600)}


def test_the_worst_operator_is_the_one_the_widths_are_cut_for() -> None:
    """1 995 wallets, 6.81% of all points, a 44.6x sqrt subsidy -- carried in
    this distribution's copy too, so a WP1 or WP2 test never has to reach into
    the maxpane repo for the number."""
    clusters = {c["cluster"]: c for c in labeled_subset()["clusters"]}
    top = clusters["amt_0.45_h3"]
    assert top["wallets"] == 1995
    assert round(top["share_pct"], 2) == 6.81
    assert round(top["sqrt_subsidy_x"], 1) == 44.6
    assert top["points"] == 1_811_322
    assert sum(c["wallets"] for c in clusters.values()) == 6303


def test_nothing_in_the_fixtures_reads_as_an_accusation() -> None:
    """PRD §2: the library is the artifact named "sybil"; its *data* still
    speaks in pattern-language, because these strings are the ones a consumer
    renders."""
    blob = json.dumps(labeled_subset(), ensure_ascii=False).lower()
    for word in ("cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in blob, word


def test_the_reader_raises_rather_than_returning_none_for_a_missing_fixture() -> None:
    """A reader that swallowed a missing file would turn a moved fixture into a
    test that quietly measures nothing."""
    with pytest.raises(FileNotFoundError):
        load("no_such_fixture.json")
