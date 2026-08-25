"""Two invariants that nothing else in the suite pins.

Both come out of an audit of a real 19 522-wallet population (published at
github.com/banse/clustermap/tree/main/audit), where each gap cost something:

* the **fold** is asserted only through :func:`sybilkit.signals.funding.funding_edges`
  directly — ten calls in ``test_signals_funding.py`` against two ``detect()``
  calls, both of which test the self-funder guard rather than the fold. Merging
  is impossible by construction (the combiner unions on tier-A edges only), but
  mis-*attribution* is not: a funding row spanning two components can hand one
  of them a family it did not earn, and nothing exercised that through the
  combiner.

* **coverage monotonicity** — resolving *more* enrichment must never make a rule
  fire *less*. A rule that measures a share of a group whose size depends on how
  much data you happened to have will silently go quiet as coverage improves.
  That is not hypothetical: in the audited population an exchange fan-out rule
  written as ">= 90 % of a funder's fresh withdrawals share one fee value"
  caught an operator 232/232 at 64 % coverage and 0/239 at 100 %, because the
  denominator grew while the evidence did not.
"""

from __future__ import annotations

import collections

import pytest

from sybilkit import Dataset, DetectConfig, detect
from tests.sybilkit_fixtures import labeled_subset

CFG = DetectConfig()


def _funding_rows() -> list[dict]:
    lab = labeled_subset()
    rows = []
    for entry in lab["members"] + lab["controls"]:
        if entry.get("funding"):
            rows.append({"address": entry["address"], **entry["funding"]})
    return sorted(rows, key=lambda row: row["address"])


def _dataset_with(fraction: float) -> Dataset:
    """The benchmark population with the first *fraction* of funding resolved."""
    lab = labeled_subset()
    deposits: list[dict] = []
    firsts: list[dict] = []
    tx_rows: list[dict] = []
    for entry in lab["members"] + lab["controls"]:
        firsts.append({"contributor": entry["address"], "index": entry["first_index"]})
        for dep in entry["deposits"]:
            deposits.append({"contributor": entry["address"], **dep})
        if entry.get("tx"):
            tx_rows.append(entry["tx"])
    rows = _funding_rows()
    keep = rows[: round(len(rows) * fraction)]
    return Dataset.from_events(deposits, firsts, txs=tx_rows, funding=keep or None)


AMT_A = 3_333_000_000_000_000_000   # two farms, each behaviourally self-contained
AMT_B = 7_777_000_000_000_000_000


def _farm(n, *, amount, block0, prefix):
    rows = []
    for i in range(n):
        addr = "0x" + prefix * 2 + f"{i:036x}"
        rows.append({
            "contributor": addr, "hour": 1, "amount_wei": amount,
            "credited_delta_wei": amount, "weight_added_wei": amount,
            "new_weight_wei": amount, "tx_count": 1, "block_number": block0 + i,
            "tx_hash": "0x" + prefix * 2 + f"{i:060x}", "log_index": i,
        })
    return rows


def _identical_txs(rows, *, fee, gas_limit):
    return [
        {"tx_hash": row["tx_hash"], "nonce": 0, "max_priority_fee_wei": fee,
         "max_fee_wei": fee * 3, "gas_limit": gas_limit, "tx_type": 2}
        for row in rows
    ]


def test_funding_evidence_about_a_stranger_never_counts_toward_a_cluster() -> None:
    """The fold, asserted through ``detect()`` — on the thing that can break.

    The combiner unions on tier-A edges ONLY (``cluster.py``: ``for edge in
    tier_a: uf.union(...)``); ``gas`` and ``funding`` are appended afterwards and
    attributed with ``uf.find(edge.a)``. So a builder inserted into
    ``funding_edges`` cannot merge two components — the architecture prevents
    that a layer above the family, and a test written to catch a merge is
    vacuous.

    What removing the fold *does* break is attribution: a funding row between
    two different components gets its family credited to whichever component the
    first endpoint lives in. The cluster then carries a third family bought with
    evidence about a stranger, which is exactly how a component clears the
    ``>= 2 families`` gate it should have failed.

    Verified by mutation: with the fold removed, the left cluster comes back as
    ['amount', 'funding', 'gas'] and this test fails.
    """
    # Each farm needs two families of its own, or the >=2-family gate discards
    # both and there is no cluster left to inspect — which is how the first cut
    # of this test passed against a library with the fold deliberately removed.
    left = _farm(6, amount=AMT_A, block0=1_000, prefix="aa")
    right = _farm(6, amount=AMT_B, block0=90_000, prefix="bb")
    txs = _identical_txs(left, fee=35_000_000, gas_limit=83_967)
    txs += _identical_txs(right, fee=77_000_000, gas_limit=91_600)
    # The only funding row in the dataset crosses between the two components.
    bridge = [{
        "address": right[0]["contributor"],
        "funder": left[0]["contributor"],
        "hops": 1,
    }]
    ds = Dataset.from_events(left + right, [], txs=txs, funding=bridge)

    left_members = {row["contributor"] for row in left}
    right_members = {row["contributor"] for row in right}
    result = detect(ds, CFG)
    assert len(result.clusters) == 2, (
        "premise broken: both farms must be kept clusters for this test to mean "
        f"anything, got {len(result.clusters)}"
    )
    for cluster in result.clusters:
        families = {reason.family for reason in cluster.reasons}
        assert "funding" not in families, (
            f"cluster {cluster.cluster_id} counts a funding family, but the only "
            "funding row in this dataset is between two different components: "
            "the fold is gone and a cluster is being corroborated by a stranger"
        )
        members = set(cluster.members)
        assert not (members & left_members and members & right_members), (
            f"cluster {cluster.cluster_id} spans both farms: the funding family "
            "welded two behavioural components instead of corroborating one"
        )


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_more_enrichment_never_makes_the_detector_see_less(fraction) -> None:
    """Resolving more funding may add evidence; it must never remove any.

    Guards the failure mode where a rule is expressed as a share of a set whose
    size grows with coverage. Compared against the zero-coverage baseline so a
    regression at any step is attributed to the step that caused it.
    """
    def families(result) -> collections.Counter:
        counts: collections.Counter = collections.Counter()
        for cluster in result.clusters:
            for family in {reason.family for reason in cluster.reasons}:
                counts[family] += 1
        return counts

    baseline = detect(_dataset_with(0.0), CFG)
    result = detect(_dataset_with(fraction), CFG)

    base_counts = families(baseline)
    counts = families(result)
    for family, seen in base_counts.items():
        assert counts[family] >= seen, (
            f"at {fraction:.0%} funding coverage the {family} family holds "
            f"{counts[family]} clusters, down from {seen} with no funding at all"
        )
    assert len(result.flagged) >= len(baseline.flagged), (
        f"at {fraction:.0%} coverage the detector flags {len(result.flagged)} wallets, "
        f"down from {len(baseline.flagged)} with no enrichment at all"
    )
    assert len(result.clusters) >= len(baseline.clusters), (
        f"at {fraction:.0%} coverage the detector keeps {len(result.clusters)} clusters, "
        f"down from {len(baseline.clusters)} with no enrichment"
    )
