"""WP1.5 — ``detect``: union-find, the ≥2-family gate, graduated confidence.

The named tests from the work-package brief appear verbatim; around them sit
the detect-level identities (the wei-exact fold, cluster points as summed
member curve points) and the whole-population smoke (controller ruling 4).
"""

from __future__ import annotations

from collections import Counter

from sybilkit import Dataset, DetectConfig, detect
from sybilkit.curve import curve_points
from sybilkit.labels import CEX_HOT_WALLETS

from tests.conftest import build_labeled_dataset, build_population_dataset
from tests.sybilkit_fixtures import labeled_subset

# ---------------------------------------------------------------------------
# helpers the brief's verbatim tests call
# ---------------------------------------------------------------------------

_LAB = labeled_subset()
_MIN_CROWD = {
    m["address"].lower()
    for m in _LAB["members"]
    if m["cluster"] in ("amt_0.05_h7", "amt_0.05_h15", "amt_0.05_h17")
}


def _labeled() -> Dataset:
    return build_labeled_dataset()


def _control_addresses() -> set[str]:
    return {c["address"].lower() for c in _LAB["controls"]}


def _amount_only_fixture() -> Dataset:
    """The 0.05 minimum crowd, tier A only: identical round amounts and
    nothing else — no txs, no funding, and at sample density no sequence or
    cadence can fire."""
    deposits = []
    firsts = []
    for m in _LAB["members"]:
        if m["address"].lower() not in _MIN_CROWD:
            continue
        firsts.append({"contributor": m["address"], "index": m["first_index"]})
        for dep in m["deposits"]:
            deposits.append({"contributor": m["address"], **dep})
    return Dataset.from_events(deposits, firsts)


from functools import lru_cache


@lru_cache(maxsize=1)
def _shape_amounts() -> dict[str, int]:
    """First-deposit amount per contributor, off the full population — which
    contains every labeled address, so one map serves both datasets."""
    out: dict[str, int] = {}
    for dep in build_population_dataset().deposits:  # chain-ordered
        out.setdefault(dep.contributor, dep.amount_wei)
    return out


def _shape(c) -> str:
    """A cluster's dominant first-deposit amount as a short ETH string."""
    amounts = Counter(_shape_amounts()[m] for m in c.members)
    wei = amounts.most_common(1)[0][0]
    whole, frac = divmod(wei, 10**18)
    text = f"{whole}.{frac:018d}".rstrip("0")
    return text + "0" if text.endswith(".") else text


# ---------------------------------------------------------------------------
# the brief's named tests, verbatim
# ---------------------------------------------------------------------------


def test_one_family_never_convicts():
    """PRD §3.1.  A component joined only by identical amounts -- with no
    sequence, cadence, gas or funding corroboration -- is below min_families and
    is not a cluster."""
    ds = _amount_only_fixture()   # the 0.05 minimum crowd
    assert detect(ds, DetectConfig(min_families=2)).clusters == []


def test_min_size_keeps_one_human_few_wallets_out():
    assert all(c.size >= 5 for c in detect(_labeled(), DetectConfig()).clusters)


def test_the_16_audited_operators_are_each_found():
    res = detect(_labeled(), DetectConfig())
    found = {_shape(c) for c in res.clusters}
    for shape in ("0.45", "14.0", "10.0", "1.2", "2.067"):
        assert shape in found


def test_no_control_is_flagged():
    res = detect(_labeled(), DetectConfig())
    assert res.flagged.isdisjoint(_control_addresses())


def test_confidence_is_graduated_not_binary():
    res = detect(_labeled(), DetectConfig())
    confs = sorted({round(c.confidence, 2) for c in res.clusters})
    assert len(confs) >= 2 and all(0.0 <= c <= 1.0 for c in confs)


def test_freshness_discounts_never_convicts():
    """A fresh-nonce-only signal cannot lift a one-family component to a
    cluster (research §5: 55% of controls are nonce-0).

    The 0.05 crowd *with* its transaction fingerprints: most of those wallets
    are nonce-0, their fee fingerprints are diverse (no gas family), and
    freshness must stay a discount on confidence — never an edge, never a
    family, never a conviction."""
    deposits, firsts, txs = [], [], []
    for m in _LAB["members"]:
        if m["address"].lower() not in _MIN_CROWD:
            continue
        firsts.append({"contributor": m["address"], "index": m["first_index"]})
        for dep in m["deposits"]:
            deposits.append({"contributor": m["address"], **dep})
        txs.append(m["tx"])
    ds = Dataset.from_events(deposits, firsts, txs=txs)
    assert detect(ds, DetectConfig()).clusters == []


# ---------------------------------------------------------------------------
# freshness discounts (the positive half), and the gate under config
# ---------------------------------------------------------------------------


def _two_family_farm(*, fresh: bool) -> Dataset:
    amount = 3_333_000_000_000_000_001  # odd, byte-identical
    deposits, txs = [], []
    for i in range(6):
        addr = f"0x{i + 1:040x}"
        tx_hash = "0x" + f"{i + 1:064x}"
        deposits.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": 1000 + i * 100,
                "tx_hash": tx_hash,
                "log_index": i,
            }
        )
        txs.append(
            {
                "tx_hash": tx_hash,
                "nonce": 0 if fresh else 40 + i,
                "max_priority_fee_wei": 100_000_000,
                "max_fee_wei": 150_000_000,
                "gas_limit": 91_600,
                "tx_type": 2,
            }
        )
    return Dataset.from_events(deposits, [], txs=txs)


def test_confidence_is_noisy_or_so_corroboration_accumulates_upward() -> None:
    """Review I2 / ruling R11: confidence = 1 − Π(1 − strength_f) over the
    distinct families' best strengths.  A per-family product would *lower*
    confidence with every extra family — gaining evidence must never cost
    conviction.  The two-family farm here carries amount 0.9 (odd exact) and
    gas 0.85: noisy-OR says 0.985; adding a funding chain (0.95) must raise
    it, not sink it."""
    two = detect(_two_family_farm(fresh=True), DetectConfig())
    assert len(two.clusters) == 1
    assert round(two.clusters[0].confidence, 9) == round(1 - 0.1 * 0.15, 9)

    # the same farm with a peel chain on top: strictly more confident
    amount = 3_333_000_000_000_000_001
    deposits, txs, funding = [], [], []
    addrs = [f"0x{i + 1:040x}" for i in range(6)]
    for i, addr in enumerate(addrs):
        tx_hash = "0x" + f"{i + 1:064x}"
        deposits.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": 1000 + i * 100,
                "tx_hash": tx_hash,
                "log_index": i,
            }
        )
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
        if i:
            funding.append({"address": addr, "funder": addrs[i - 1], "hops": 1})
    three = detect(
        Dataset.from_events(deposits, [], txs=txs, funding=funding), DetectConfig()
    )
    assert len(three.clusters) == 1
    assert three.clusters[0].confidence > two.clusters[0].confidence
    assert three.clusters[0].confidence <= 1.0


def test_freshness_is_a_discount_on_confidence() -> None:
    """Same two-family farm, one all-fresh and one all-aged: the aged copy is
    still a cluster (the gate never moves) at strictly lower confidence."""
    fresh = detect(_two_family_farm(fresh=True), DetectConfig())
    aged = detect(_two_family_farm(fresh=False), DetectConfig())
    assert len(fresh.clusters) == len(aged.clusters) == 1
    assert aged.clusters[0].confidence < fresh.clusters[0].confidence
    assert aged.clusters[0].members == fresh.clusters[0].members


def test_a_shared_cex_funder_cannot_be_the_second_family() -> None:
    """WP1.7's end-to-end half: a one-family amount group whose members all
    share a Binance hot-wallet funder must not become a cluster."""
    amount = 3_333_000_000_000_000_001
    deposits, funding = [], []
    binance = next(iter(CEX_HOT_WALLETS))
    for i in range(6):
        addr = f"0x{i + 1:040x}"
        deposits.append(
            {
                "contributor": addr,
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": 1000 + i * 100,
                "tx_hash": "0x" + f"{i + 1:064x}",
                "log_index": i,
            }
        )
        funding.append({"address": addr, "funder": binance, "hops": 1})
    ds = Dataset.from_events(deposits, [], funding=funding)
    assert detect(ds, DetectConfig()).clusters == []


def test_a_single_block_coincidence_is_one_family_and_no_cluster() -> None:
    """Review I3 / ruling R12: one block with ≥ min_size chained-near
    single-deposit wallets, tier A only.  Before the fix, amounts-near and
    cadence-burst both fired on that identical configuration and the block
    convicted itself; now the coincidence is a single amount family and the
    gate holds."""
    base = 100_000_000_000_000_000
    deposits = []
    for i in range(6):
        amount = base + i * base // 100  # chained-near jitter, no two equal
        deposits.append(
            {
                "contributor": f"0x{i + 1:040x}",
                "hour": 1,
                "amount_wei": amount,
                "credited_delta_wei": amount,
                "weight_added_wei": amount,
                "new_weight_wei": amount,
                "tx_count": 1,
                "block_number": 1000,  # ONE block
                "tx_hash": "0x" + f"{i + 1:064x}",
                "log_index": i,
            }
        )
    ds = Dataset.from_events(deposits, [])
    assert detect(ds, DetectConfig()).clusters == []


def test_points_per_eth_travels_through_the_config() -> None:
    """Review I5 / ruling R10: the curve rate is an explicit DetectConfig
    field — no dataset attribute, no stringly getattr.  Doubling the rate
    doubles every wei-exact fold (before the floor), and shares stay put."""
    ds = _two_family_farm(fresh=True)
    at_1000 = detect(ds, DetectConfig())
    at_2000 = detect(ds, DetectConfig(points_per_eth=2000))
    assert at_1000.total_points > 0
    assert at_2000.total_points == sum(
        curve_points(w, 2000)
        for w in {d.contributor: d.new_weight_wei for d in ds.deposits}.values()
    )
    assert at_2000.clusters[0].points > at_1000.clusters[0].points
    assert at_2000.clusters[0].points_share == at_1000.clusters[0].points_share
    # and the dataset carries no rate for anything to read
    assert not hasattr(ds, "points_per_eth")


def test_the_gate_reads_its_thresholds_from_the_config() -> None:
    ds = _labeled()
    default = detect(ds, DetectConfig())
    loose = detect(ds, DetectConfig(min_families=1))
    strict = detect(ds, DetectConfig(min_size=25))
    assert len(loose.clusters) > len(default.clusters)
    assert all(c.size >= 25 for c in strict.clusters)


# ---------------------------------------------------------------------------
# detect-level identities
# ---------------------------------------------------------------------------


def test_total_points_is_the_wei_exact_fold_and_the_counters_balance() -> None:
    ds = _labeled()
    res = detect(ds, DetectConfig())
    last_weight: dict[str, int] = {}
    for dep in ds.deposits:  # chain-ordered: the last write is the final weight
        last_weight[dep.contributor] = dep.new_weight_wei
    expected = sum(curve_points(w, 1000) for w in last_weight.values())
    assert res.total_points == expected
    assert res.flagged_points + res.clean_points == res.total_points


def test_cluster_points_are_the_summed_member_curve_points() -> None:
    """The WP1.6 summation identity, pinned where the summation lives; its
    mutation bite drops a member from the sum."""
    ds = _labeled()
    res = detect(ds, DetectConfig())
    last_weight: dict[str, int] = {}
    for dep in ds.deposits:
        last_weight[dep.contributor] = dep.new_weight_wei
    assert res.clusters
    for c in res.clusters:
        assert c.points == sum(curve_points(last_weight[m], 1000) for m in c.members)
        assert c.points_share == c.points / res.total_points
        assert c.size == len(c.members)
        assert all(m == m.lower() for m in c.members)


def test_flagged_points_are_the_flagged_clusters_points() -> None:
    res = detect(_labeled(), DetectConfig())
    expected = sum(
        c.points for c in res.clusters if c.confidence >= res.confidence_threshold
    )
    assert res.flagged_points == expected


def test_span_blocks_is_the_first_deposit_block_span() -> None:
    ds = _labeled()
    res = detect(ds, DetectConfig())
    first_block: dict[str, int] = {}
    for dep in ds.deposits:
        first_block.setdefault(dep.contributor, dep.block_number)
    for c in res.clusters:
        blocks = [first_block[m] for m in c.members]
        assert c.span_blocks == max(blocks) - min(blocks)


def test_wallet_answers_all_three_ways_from_a_real_run() -> None:
    ds = _labeled()
    res = detect(ds, DetectConfig())
    member = next(iter(res.flagged))
    verdict = res.wallet(member)
    assert verdict.in_cluster is True and verdict.reasons
    control = next(iter(_control_addresses()))
    clean = res.wallet(control)
    assert clean is not None and clean.in_cluster is False  # analyzed, not linked
    assert res.wallet("0x" + "77" * 20) is None  # never analyzed


def test_two_runs_over_one_dataset_return_equal_results() -> None:
    ds = _labeled()
    a, b = detect(ds, DetectConfig()), detect(ds, DetectConfig())
    assert a.clusters == b.clusters
    assert (a.total_points, a.flagged_points, a.clean_points) == (
        b.total_points,
        b.flagged_points,
        b.clean_points,
    )


def test_reasons_are_pattern_language_never_verdicts() -> None:
    res = detect(_labeled(), DetectConfig())
    families = set()
    for c in res.clusters:
        assert len({r.family for r in c.reasons}) >= 2
        families |= {r.family for r in c.reasons}
        for r in c.reasons:
            lowered = r.human_string.lower()
            for verdict_word in ("sybil", "fraud", "cheat", "guilty"):
                assert verdict_word not in lowered
    assert "amount" in families


def test_an_unknown_edge_family_is_a_programming_error_not_a_second_family() -> None:
    """Review I1: the gate counts distinct families, so a misspelt family
    from a future signal ('amounts ', 'sequnce') must never silently count
    as corroboration.  An unknown family is a programming error and detect
    raises on it rather than convicting with it."""
    import pytest

    from sybilkit.cluster import Edge
    from sybilkit.report import Reason
    import sybilkit.signals.amounts as amounts_mod

    ds = _two_family_farm(fresh=True)
    real = amounts_mod.amount_edges

    def poisoned(ds_, cfg_):
        edges = real(ds_, cfg_)
        bad = Reason("amounts ", "misspelt family", 0.9)
        return edges + [
            Edge(edges[0].a, edges[0].b, "amounts ", 0.9, bad),
            Edge(edges[0].a, edges[0].b, "sequnce", 0.9, bad),
        ]

    amounts_mod.amount_edges = poisoned
    try:
        with pytest.raises(ValueError, match="amounts "):
            detect(ds, DetectConfig())
    finally:
        amounts_mod.amount_edges = real
    # restored: the same dataset detects normally again
    assert len(detect(ds, DetectConfig()).clusters) == 1


def test_an_empty_dataset_detects_nothing_and_says_so() -> None:
    res = detect(Dataset(deposits=(), first_index={}, txs={}, funding={}))
    assert res.clusters == []
    assert (res.total_points, res.flagged_points, res.clean_points) == (0, 0, 0)


def test_the_protocol_minimum_crowd_is_not_flagged_wholesale_on_tier_a() -> None:
    """Review I4 / ruling R13: with the protocol minimum declared, the
    1,468-wallet 0.05 crowd stops being one welded amount component.
    Measured: 272 of them still flag — via consecutive-index runs and
    repeated byte-identical bursts, i.e. genuinely farm-shaped sub-groups —
    which is the point: the minimum alone convicts nobody, behaviour still
    can."""
    ds = build_population_dataset()
    minimum = 50_000_000_000_000_000
    counts: dict[str, list] = {}
    for d in ds.deposits:
        counts.setdefault(d.contributor, []).append(d)
    crowd = {
        c for c, rows in counts.items()
        if len(rows) == 1 and rows[0].amount_wei == minimum
    }
    assert len(crowd) == 1468
    res = detect(ds, DetectConfig(protocol_min_amount_wei=minimum))
    flagged_minimum = res.flagged & crowd
    assert len(flagged_minimum) <= 400  # measured 272; wholesale would be 1468
    # and without the declaration the crowd still welds -- the knob is load-bearing
    wholesale = detect(ds, DetectConfig())
    assert len(wholesale.flagged & crowd) == 1468


# ---------------------------------------------------------------------------
# the whole-population smoke (controller ruling 4): tier A only, one pass
# ---------------------------------------------------------------------------


def test_the_whole_population_tier_a_smoke() -> None:
    ds = build_population_dataset()
    res = detect(ds, DetectConfig())

    # the wei-exact fold over all 15 576 contributors
    assert res.total_points == 26_585_740
    assert res.flagged_points + res.clean_points == res.total_points

    # the flagged share lands in a sane band; tier A alone overshoots the
    # research's 43.25% all-tier conservative floor because the big real
    # farms (14.0/10.0/0.45) alone carry ~39% and the round-amount crowds
    # add the rest.  Measured after fix round 1: 0.5609 under this default
    # config, 0.5479 with protocol_min_amount_wei set (recorded in the WP1
    # report; band-asserted here, not over-pinned).
    share = res.flagged_points / res.total_points
    assert 0.30 <= share <= 0.70

    # the three named operators are found
    found = {_shape(c) for c in res.clusters}
    for shape in ("0.45", "14.0", "10.0"):
        assert shape in found

    # and the wave sizes are the audited magnitudes, not fragments
    sizes = {_shape(c): c.size for c in res.clusters}
    assert sizes["0.45"] >= 1900
    assert sizes["14.0"] >= 950
    assert sizes["10.0"] >= 700
