"""Shared builders over the committed fixtures.

Everything here is offline: the bytes come from ``tests/fixtures/`` through
``tests.sybilkit_fixtures``, and a :class:`sybilkit.Dataset` is built through
the public ``Dataset.from_events`` — the same door every real producer uses,
so the suite exercises the coercion path instead of bypassing it.

Ground truth (cluster labels, ``funder_in_cluster``) stays **test-side**: the
model deliberately has no field for it, so the helpers below carry it in plain
dicts next to the dataset.
"""

from __future__ import annotations

import pytest

from sybilkit import Dataset
from tests.sybilkit_fixtures import labeled_subset, load


def build_labeled_dataset(*, txs: bool = True, funding: bool = True) -> Dataset:
    """The 220-address benchmark subset as a Dataset.

    ``txs=False`` / ``funding=False`` drop a tier, which is how the tier-A-only
    first-cycle state is exercised against the same population.
    """
    lab = labeled_subset()
    rows = lab["members"] + lab["controls"]
    deposits = []
    firsts = []
    tx_rows = []
    funding_rows = []
    for entry in rows:
        addr = entry["address"]
        firsts.append({"contributor": addr, "index": entry["first_index"]})
        for dep in entry["deposits"]:
            deposits.append({"contributor": addr, **dep})
        if txs and entry.get("tx"):
            tx_rows.append(entry["tx"])
        if funding and entry.get("funding"):
            funding_rows.append({"address": addr, **entry["funding"]})
    return Dataset.from_events(
        deposits,
        firsts,
        txs=tx_rows if txs else None,
        funding=funding_rows if funding else None,
    )


def build_population_dataset() -> Dataset:
    """The full 22 319-deposit population, tier A only (empty txs/funding)."""
    return Dataset.from_events(load("deposits.json.gz"), load("first_deposits.json.gz"))


@pytest.fixture(scope="session")
def labeled_ds() -> Dataset:
    return build_labeled_dataset()


@pytest.fixture(scope="session")
def labeled_truth() -> dict:
    """Label maps: ``cluster_of`` (member addr -> operator id), ``controls``
    (set of control addrs), ``members_of`` (operator id -> set of addrs)."""
    lab = labeled_subset()
    cluster_of = {m["address"].lower(): m["cluster"] for m in lab["members"]}
    members_of: dict[str, set[str]] = {}
    for addr, cl in cluster_of.items():
        members_of.setdefault(cl, set()).add(addr)
    return {
        "cluster_of": cluster_of,
        "controls": {c["address"].lower() for c in lab["controls"]},
        "members_of": members_of,
        "raw": lab,
    }


@pytest.fixture(scope="session")
def population_ds() -> Dataset:
    return build_population_dataset()


def connected_sets(edges) -> list[set[str]]:
    """Union-find over a list of Edge objects — the test-side view of "joined",
    kept deliberately separate from the combiner's own implementation."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        ra, rb = find(e.a), find(e.b)
        if ra != rb:
            parent[rb] = ra
    comps: dict[str, set[str]] = {}
    for node in parent:
        comps.setdefault(find(node), set()).add(node)
    return list(comps.values())


def component_containing(edges, addr: str) -> set[str]:
    for comp in connected_sets(edges):
        if addr in comp:
            return comp
    return set()
