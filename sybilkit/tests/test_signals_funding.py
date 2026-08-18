"""WP1.4 — the ``funding`` family: the first-funder graph, folded.

The single strongest measured discriminator (research §5.1) is **funder ∈
same cluster** — the peel chain, 10/10 on fully-resolved farm samples against
0/47 controls.  What it is explicitly *not* is "funder is any contributor":
35 of the 47 resolved controls were funded by their own main wallet, which is
a contributor, and which is normal.  The fold — an edge only when funder and
funded already share a behavioural component — is what separates the two, and
it is the mandated mutation bite of this work package.

Ruling 2: the fold is only checkable against FULL cluster membership, which
the sampled 220-address dataset cannot carry (a sampled member's funder is
usually an unsampled member).  So the ground truth is pinned straight off the
fixture's precomputed full-membership join, and the *signal* is exercised on
synthetic peel chains plus the four in-sample funder pairs.
"""

from __future__ import annotations

from sybilkit import Dataset, DetectConfig
from sybilkit.labels import CEX_HOT_WALLETS
from sybilkit.signals.funding import funding_edges

CFG = DetectConfig()

AMT_ODD = 3_333_000_000_000_000_000  # odd: byte-identical across windows


def _farm_rows(n, *, amount=AMT_ODD, block0=1000, prefix="aa"):
    rows = []
    for i in range(n):
        addr = "0x" + prefix * 2 + f"{i:036x}"
        rows.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": block0 + i,
                "tx_hash": "0x" + prefix * 2 + f"{i:060x}",
                "log_index": i,
            }
        )
    return rows


def _addrs(rows):
    return [r["contributor"] for r in rows]


def test_the_fixture_ground_truth_eleven_operators_and_no_control(
    labeled_truth,
) -> None:
    """Ruling 2 verbatim: 11 of the 16 operators have all ten sampled funders
    resolved and every one is 10/10 funder-in-cluster; the three groups below
    their resolved total are 0.05-minimum groups that are genuinely mixed —
    NOT signal failure; controls are 0/47."""
    raw = labeled_truth["raw"]
    full_ten, below = [], []
    for cl, members in labeled_truth["members_of"].items():
        entries = [m for m in raw["members"] if m["address"].lower() in members]
        resolved = [m for m in entries if m["funding"]["funder"] is not None]
        in_cluster = [m for m in resolved if m["funding"]["funder_in_cluster"]]
        if len(resolved) == 10 and len(in_cluster) == 10:
            full_ten.append(cl)
        elif len(in_cluster) < len(resolved):
            below.append(cl)
    assert len(full_ten) == 11
    assert set(below) <= {"amt_0.05_h7", "amt_0.05_h15", "amt_0.05_h17"}
    controls = [c for c in raw["controls"] if c["funding"]["funder"] is not None]
    assert len(controls) == 47
    assert sum(1 for c in controls if c["funding"]["funder_in_cluster"]) == 0


def test_a_peel_chain_inside_a_component_is_the_strongest_evidence() -> None:
    """Six wallets, byte-identical odd amount (one behavioural component),
    each funded by the previous — the serial chain fires."""
    rows = _farm_rows(6)
    addrs = _addrs(rows)
    funding = [
        {"address": addrs[i], "funder": addrs[i - 1], "hops": 1}
        for i in range(1, 6)
    ]
    ds = Dataset.from_events(rows, [], funding=funding)
    edges = funding_edges(ds, CFG)
    assert len(edges) == 5
    assert {e.family for e in edges} == {"funding"}
    assert all(e.strength >= 0.9 for e in edges)
    assert any("chain" in e.reason.human_string for e in edges)


def test_a_main_wallet_funder_outside_the_component_is_not_evidence() -> None:
    """The 35/47 false-positive shape, and the mandated bite's victim: each
    'control' is funded by its own main wallet — a contributor, but one that
    shares no behavioural component with it.  Zero edges; a version that
    fires on *any* contributor funder reddens here."""
    farm = _farm_rows(6, prefix="aa")  # an unrelated real farm component
    controls = []
    mains = []
    for i in range(5):
        c = _farm_rows(1, amount=10**17 * (7 + 2 * i) + 1, block0=5000 + 40 * i, prefix="cc")[0]
        m = _farm_rows(1, amount=10**16 * (3 + 5 * i), block0=2000 + 40 * i, prefix="dd")[0]
        c["contributor"] = "0x" + "cc" * 4 + f"{i:032x}"
        m["contributor"] = "0x" + "dd" * 4 + f"{i:032x}"
        c["tx_hash"] = "0x" + "cc" * 4 + f"{i:056x}"
        m["tx_hash"] = "0x" + "dd" * 4 + f"{i:056x}"
        controls.append(c)
        mains.append(m)
    funding = [
        {"address": c["contributor"], "funder": m["contributor"], "hops": 1}
        for c, m in zip(controls, mains)
    ]
    ds = Dataset.from_events(farm + controls + mains, [], funding=funding)
    assert funding_edges(ds, CFG) == []


def test_a_shared_cex_hot_wallet_never_fabricates_funding_evidence() -> None:
    """The research §7 false-positive class: a one-family amount group whose
    members were all first-funded from the same Binance hot wallet.  Without
    the exclusion the shared funder becomes family #2 and the gate falls."""
    rows = _farm_rows(6)
    binance = next(iter(CEX_HOT_WALLETS))
    funding = [
        {"address": r["contributor"], "funder": binance, "hops": 1} for r in rows
    ]
    ds = Dataset.from_events(rows, [], funding=funding)
    assert funding_edges(ds, CFG) == []


def test_a_shared_non_infra_funder_inside_a_component_corroborates() -> None:
    """The disperse-style hub *inside* one behavioural component is real
    evidence — weaker than the chain, but present."""
    rows = _farm_rows(6)
    hub = "0x" + "ee" * 20
    funding = [
        {"address": r["contributor"], "funder": hub, "hops": 1} for r in rows
    ]
    ds = Dataset.from_events(rows, [], funding=funding)
    edges = funding_edges(ds, CFG)
    assert edges
    assert all(e.strength < 0.9 for e in edges)
    assert any("shared" in e.reason.human_string for e in edges)


def test_a_none_funder_produces_no_edge_never_a_false_one() -> None:
    """Tier C not run (or bounded out) is ``None`` — and ``None`` is a failed
    read, not a shared funder."""
    rows = _farm_rows(6)
    funding = [
        {"address": r["contributor"], "funder": None, "hops": None} for r in rows
    ]
    ds = Dataset.from_events(rows, [], funding=funding)
    assert funding_edges(ds, CFG) == []


def test_the_four_in_sample_funder_pairs_stay_inside_their_own_labels(
    labeled_ds, labeled_truth
) -> None:
    """Four sampled members are funded by another sampled address.  Every
    resulting edge must stay inside one operator's own membership — never a
    control, never across labels."""
    edges = funding_edges(labeled_ds, CFG)
    assert edges  # the sampled peel-chain fragments fire
    cluster_of = labeled_truth["cluster_of"]
    for e in edges:
        assert e.a not in labeled_truth["controls"]
        assert e.b not in labeled_truth["controls"]
        assert cluster_of.get(e.a) == cluster_of.get(e.b) is not None


def test_empty_funding_means_no_edges_tier_a_only() -> None:
    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset(funding=False)
    assert ds.funding == {}
    assert funding_edges(ds, CFG) == []


# ---- review finding #1: the self-referential funding row -------------------
#
# A persisted slot payload is third-party input (the adapter's own translation
# boundary says so), so ``{'address': A, 'funder': A}`` is a row this family
# has to survive.  The union of A with A is a no-op, but the *family* it books
# is not: a one-family component that gains ``funding`` clears the >=2-family
# gate and convicts at noisy-OR ~0.995 on evidence that is one edited line.


def test_a_self_funding_row_never_creates_the_funding_family() -> None:
    """A wallet is not its own first funder; a row saying so is edited, not
    measured.  It must produce no edge at all — an ``Edge(A, A, "funding")``
    unions nothing but books the family, which is the whole defect."""
    rows = _farm_rows(6)
    addrs = _addrs(rows)
    funding = [{"address": addrs[0], "funder": addrs[0], "hops": 1}]
    ds = Dataset.from_events(rows, [], funding=funding)
    assert funding_edges(ds, CFG) == []


def test_a_self_funding_row_never_joins_a_shared_funder_hub() -> None:
    """The hub fold counts the funded addresses inside one component, so a
    self row inflates the hub by one and hands the reason a count that is one
    wallet too many.  The hub here is two real members, not three."""
    rows = _farm_rows(6)
    addrs = _addrs(rows)
    hub = addrs[0]
    funding = [
        {"address": hub, "funder": hub, "hops": 1},  # the hand-edited row
        {"address": addrs[1], "funder": hub, "hops": 1},
        {"address": addrs[2], "funder": hub, "hops": 1},
    ]
    ds = Dataset.from_events(rows, [], funding=funding)
    edges = funding_edges(ds, CFG)
    assert all(e.a != e.b for e in edges)
    shared = [e for e in edges if "shared" in e.reason.human_string]
    assert shared
    assert all("×2" in e.reason.human_string for e in shared)
    assert {e.a for e in shared} | {e.b for e in shared} == {addrs[1], addrs[2]}


def test_a_hand_edited_self_funding_row_cannot_lift_a_one_family_component() -> None:
    """End to end through ``detect``: six wallets on one byte-identical odd
    amount are a one-family component and must never convict.  One edited
    ``funder == address`` row used to book a second family and produce a
    cluster at ~0.995 confidence."""
    from sybilkit import detect

    rows = _farm_rows(6)
    addrs = _addrs(rows)
    plain = detect(Dataset.from_events(rows, []), CFG)
    assert plain.clusters == []  # one family: amount, and one never convicts
    funding = [{"address": addrs[0], "funder": addrs[0], "hops": 1}]
    ds = Dataset.from_events(rows, [], funding=funding)
    assert detect(ds, CFG).clusters == []


def test_the_self_funder_guard_does_not_depend_on_the_funders_casing() -> None:
    """A hand-built ``Funding`` reaches the family without passing the mapping
    coercers, so the guard compares lowercased on both sides rather than
    trusting the producer to have normalised.  Built as a ``Dataset`` directly
    so this states the family's own contract, not the model's."""
    from sybilkit import Dataset as DS
    from sybilkit.model import Funding

    rows = _farm_rows(6)
    addrs = _addrs(rows)
    hub = addrs[0]
    shouty = "0x" + hub[2:].upper()
    ds = Dataset.from_events(rows, [])
    funding = {
        a: Funding(address=a, funder=shouty, hops=1) for a in addrs[:3]
    }
    ds = DS(
        deposits=ds.deposits,
        first_index=ds.first_index,
        txs=ds.txs,
        funding=funding,
    )
    edges = funding_edges(ds, CFG)
    assert all(e.a != e.b for e in edges)
    shared = [e for e in edges if "shared" in e.reason.human_string]
    assert shared
    assert all("×2" in e.reason.human_string for e in shared)
    assert {e.a for e in shared} | {e.b for e in shared} == {addrs[1], addrs[2]}
