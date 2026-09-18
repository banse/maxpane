"""WP1.2 — the amount family: byte-identical and near-identical (±tol) groups.

Calibration facts these tests lean on, all measured on the committed fixtures:

* every sampled operator wallet is **single-deposit**; the controls that touch
  farm amounts (0.45, 1.2, ...) are almost all multi-deposit ladder wallets;
* the two byte-identical 2.067 waves sit ~2 000 blocks apart (hours 13 and
  18–19) and only the *odd* amount links them;
* the one single-deposit 1.2 control (``0xac6a82b7``) deposited in hour 8,
  six hours after the farm's h1–h2 wave;
* the randomized ``idxrun_13326`` batch (0.0997–0.1027 ETH) has no two equal
  amounts and lands inside two adjacent blocks.
"""

from __future__ import annotations


from sybilkit import DetectConfig
from sybilkit.signals.amounts import amount_edges

from tests.conftest import component_containing

CFG = DetectConfig()

LADDER_CONTROL = "0x9aea9425"  # 12-deposit human ladder incl. 0.05 and 0.45
SINGLE_12_CONTROL_H8 = "0xac6a82b7"  # single 1.2 deposit, hour 8
MIN_CONTROL_H1 = "0x52461063"  # single 0.05 deposit, hour 1


def _full(prefix: str, ds) -> str:
    (addr,) = [c for c in {d.contributor for d in ds.deposits} if c.startswith(prefix)]
    return addr


def test_every_edge_is_amount_family_with_a_graduated_strength(labeled_ds) -> None:
    edges = amount_edges(labeled_ds, CFG)
    assert edges
    for e in edges:
        assert e.family == "amount"
        assert e.reason.family == "amount"
        assert 0.0 < e.strength <= 1.0


def test_the_045_operator_is_joined_byte_identical(labeled_ds, labeled_truth) -> None:
    edges = amount_edges(labeled_ds, CFG)
    members = labeled_truth["members_of"]["amt_0.45_h3"]
    comp = component_containing(edges, next(iter(members)))
    assert members <= comp


def test_the_randomized_batch_is_joined_at_near_amount_tol(
    labeled_ds, labeled_truth
) -> None:
    """The 0.0997–0.1027 jitter batch: no two amounts byte-equal, so only the
    ±10% near rule can join it — and it does, inside its two-block burst."""
    edges = amount_edges(labeled_ds, CFG)
    members = labeled_truth["members_of"]["idxrun_13326"]
    biggest = max(
        (component_containing(edges, m) & members for m in members), key=len
    )
    assert len(biggest) >= 5
    # ...and a byte-identical-only view misses it entirely
    exact_only = [e for e in edges if "near" not in e.reason.human_string]
    for m in members:
        assert component_containing(exact_only, m) & members <= {m}


def test_a_byte_identical_rule_groups_on_integer_wei_never_a_float() -> None:
    """Two deposits one wei apart are different amounts.  A float ETH compare
    would call 2.067 ETH and 2.067 ETH ± 1 wei equal; the integer rule must
    not."""
    from sybilkit import Dataset

    amt = 2_067_000_000_000_000_000
    rows = [
        {
            "contributor": f"0x{i:040x}",
            "hour": 1,
            "amount_wei": amt + (1 if i == 2 else 0),
            "credited_delta_wei": amt,
            "weight_added_wei": amt,
            "new_weight_wei": amt,
            "tx_count": 1,
            "block_number": 100 + i * 500,  # far apart: the near rule is out
            "tx_hash": "0x" + f"{i:064x}",
            "log_index": 1,
        }
        for i in range(3)
    ]
    ds = Dataset.from_events(rows, [])
    edges = amount_edges(ds, CFG)
    linked = component_containing(edges, f"0x{0:040x}")
    assert f"0x{1:040x}" in linked  # byte-identical, joined across blocks (odd)
    assert f"0x{2:040x}" not in linked  # one wei off, blocks apart: not joined


def test_the_005_minimum_crowd_is_one_family_never_a_cluster_on_its_own(
    labeled_ds, labeled_truth
) -> None:
    """Amount alone is NOISY for a round/minimum value (research §5).  The
    signal may group the 0.05 crowd — that is what the ≥2-family gate is for —
    but every edge it emits is the one ``amount`` family, so the crowd can
    never convict on this signal alone."""
    edges = amount_edges(labeled_ds, CFG)
    crowd = {
        a
        for a, cl in labeled_truth["cluster_of"].items()
        if cl in ("amt_0.05_h7", "amt_0.05_h15", "amt_0.05_h17")
    }
    crowd_edges = [e for e in edges if e.a in crowd or e.b in crowd]
    assert {e.family for e in crowd_edges} == {"amount"}


def test_multi_deposit_ladder_wallets_are_outside_every_amount_group(
    labeled_ds, labeled_truth
) -> None:
    """A human laddering 0.05→1.15 touches farm amounts on the way; the
    single-deposit rule keeps every such wallet out of the groups."""
    edges = amount_edges(labeled_ds, CFG)
    ladder = _full(LADDER_CONTROL, labeled_ds)
    assert all(ladder not in (e.a, e.b) for e in edges)


def test_a_round_amount_does_not_reach_across_the_wave_window(
    labeled_ds, labeled_truth
) -> None:
    """The single-deposit 1.2 control deposited in hour 8; the farm's wave is
    hours 1–2.  A round amount groups only inside its contiguous-hour window,
    so the control shares no component with the farm."""
    edges = amount_edges(labeled_ds, CFG)
    farm = labeled_truth["members_of"]["amt_1.2_h1"]
    control = _full(SINGLE_12_CONTROL_H8, labeled_ds)
    comp = component_containing(edges, next(iter(farm)))
    assert farm <= comp
    assert control not in comp
    # same shape for the 0.05 control in hour 1 against the h15+ operators
    h1_control = _full(MIN_CONTROL_H1, labeled_ds)
    for m in labeled_truth["members_of"]["amt_0.05_h15"]:
        assert h1_control not in component_containing(edges, m)


def test_an_odd_amount_reaches_across_windows(labeled_ds, labeled_truth) -> None:
    """The identical odd 2.067 links the operator's two window-separated waves
    — the research §3 signature a wave-scoped rule would miss."""
    edges = amount_edges(labeled_ds, CFG)
    both = (
        labeled_truth["members_of"]["amt_2.067_h18"]
        | labeled_truth["members_of"]["amt_2.067_h13"]
    )
    comp = component_containing(edges, next(iter(both)))
    assert both <= comp


def test_the_protocol_minimum_identicalness_is_not_amount_evidence(
    labeled_ds, labeled_truth
) -> None:
    """Ruling R13: with ``protocol_min_amount_wei`` set, byte-identical 0.05
    groups emit no amount edge from identicalness alone — while every other
    amount keeps its groups, and near-identical jitter is untouched."""
    from sybilkit import DetectConfig

    with_min = DetectConfig(protocol_min_amount_wei=50_000_000_000_000_000)
    edges = amount_edges(labeled_ds, with_min)
    crowd = {
        a
        for a, cl in labeled_truth["cluster_of"].items()
        if cl in ("amt_0.05_h7", "amt_0.05_h15", "amt_0.05_h17")
    }
    exact = [e for e in edges if "near" not in e.reason.human_string]
    for e in exact:
        assert e.a not in crowd and e.b not in crowd
    # the 0.45 farm still groups, and the jitter batch still joins via near
    farm = labeled_truth["members_of"]["amt_0.45_h3"]
    assert farm <= component_containing(edges, next(iter(farm)))
    jitter = labeled_truth["members_of"]["idxrun_13326"]
    assert max(len(component_containing(edges, m) & jitter) for m in jitter) >= 5


def test_no_edges_from_an_empty_dataset() -> None:
    from sybilkit import Dataset

    assert amount_edges(Dataset(deposits=(), first_index={}, txs={}, funding={}), CFG) == []


# ---- review finding #13: the near pass at the exempt minimum ---------------
#
# Ruling R13b already says identicalness at the protocol minimum identifies
# nobody, and ``identical_amount_windows`` enforces it.  The near pass then
# re-admitted an arbitrary member of the very same crowd: it sorts each block's
# rows by ``(amount, address)`` and compares adjacent pairs, skipping equal
# amounts — so a run of byte-equal minimum rows sitting beside a near
# neighbour hands exactly one of them an edge, and *which* one is decided by
# lowercase address order.  D5 rules A: exempt rows leave the near pass too.

EXEMPT = 50_000_000_000_000_000  # 0.05 ETH — the protocol minimum
WITH_MIN = DetectConfig(protocol_min_amount_wei=EXEMPT)


def _row(addr, amount, *, block, log_index):
    return {
        "contributor": addr,
        "hour": 1,
        "amount_wei": amount,
        "credited_delta_wei": amount,
        "weight_added_wei": amount,
        "new_weight_wei": amount,
        "tx_count": 1,
        "block_number": block,
        "tx_hash": "0x" + f"{block:032x}{log_index:032x}",
        "log_index": log_index,
    }


def _minimum_crowd_ds(addr_of):
    """Three byte-equal minimum wallets and one near neighbour above them, all
    in one block.  *addr_of* names the crowd member playing each role, so the
    same measured population can be relabelled without changing one wei."""
    from sybilkit import Dataset

    rows = [_row(addr_of(role), EXEMPT, block=900, log_index=role) for role in range(3)]
    rows.append(_row("0x" + "ee" * 20, EXEMPT + 2_000_000_000_000_000, block=900, log_index=9))
    return Dataset.from_events(rows, [])


def _crowd_addr(role, order):
    return "0x" + "cc" * 4 + f"{order[role]:032x}"


def test_a_near_edge_at_the_exempt_minimum_is_never_emitted() -> None:
    """The minimum crowd contributes no amount edge from either rule.  A
    0.052 wallet in the same block used to pull exactly one of them in."""
    ds = _minimum_crowd_ds(lambda role: _crowd_addr(role, (1, 2, 3)))
    assert amount_edges(ds, WITH_MIN) == []


def test_which_of_two_byte_equal_minimum_wallets_links_is_not_decided_by_address_order() -> None:
    """Two datasets identical in every measured value — same amounts, same
    block, same log indices — with the crowd's addresses permuted between
    them.  Nothing a detector may read has changed, so the set of *roles* the
    edges touch must not change either.  Under the defect the lexically
    largest address was linked, so relabelling moved the conviction from role
    2 to role 0."""
    first = (1, 2, 3)
    second = (3, 1, 2)  # role 0 now carries the largest address
    touched = []
    for order in (first, second):
        role_of = {_crowd_addr(role, order): role for role in range(3)}
        edges = amount_edges(_minimum_crowd_ds(lambda role: _crowd_addr(role, order)), WITH_MIN)
        touched.append({role_of[a] for e in edges for a in (e.a, e.b) if a in role_of})
    assert touched[0] == touched[1]


# ---- R1.3: D5-A is scoped to the minimum, and that is documented ----------
#
# The exemption fixes the arbitrariness only where R13b already said the value
# identifies nobody.  Above the minimum a byte-equal run still hands its near
# edge to a lexically chosen member — and that is harmless, because the
# byte-identical rule has already welded the run into one component, so the
# near edge merges the same two components whichever member carries it.  This
# test states the harmlessness rather than asserting the arbitrariness away,
# and it is the pin the ``amount_edges`` docstring names.

RUN_AMOUNT = 2_067_000_000_000_000_001  # odd, and well above EXEMPT
NEIGHBOUR = "0x" + "ee" * 20


def _byte_equal_run_ds(order):
    """Three byte-equal non-exempt rows and one near neighbour above them, all
    in one block.  *order* permutes only the run's addresses; not one wei, block
    or log index moves with it."""
    from sybilkit import Dataset

    rows = [
        _row(_crowd_addr(role, order), RUN_AMOUNT, block=900, log_index=role)
        for role in range(3)
    ]
    rows.append(
        _row(NEIGHBOUR, RUN_AMOUNT + RUN_AMOUNT // 20, block=900, log_index=9)
    )
    return Dataset.from_events(rows, [])


def test_which_member_of_a_byte_equal_run_carries_the_near_edge_changes_nothing() -> None:
    """The near pass sorts by ``(amount, address)`` and skips equal amounts, so
    the run's highest-addressed member is the one that reaches the neighbour
    above it — an arbitrary choice that relabelling moves.  What must not move
    is the **membership** it decides, and it does not: the byte-identical rule
    already welded the run, so both spellings produce one component over the
    same four roles.  Every count, share and reason a caller sees is computed
    from that membership; only the endpoints of an ``Edge`` object move."""
    carriers, partitions = [], []
    for order in ((1, 2, 3), (3, 1, 2)):  # role 2 then role 0 holds the largest
        role_of = {_crowd_addr(role, order): role for role in range(3)}
        role_of[NEIGHBOUR] = 3
        edges = amount_edges(_byte_equal_run_ds(order), WITH_MIN)
        near = [e for e in edges if "near-identical" in e.reason.human_string]
        assert len(near) == 1
        carriers.append(
            {role_of[a] for a in (near[0].a, near[0].b) if a != NEIGHBOUR}
        )
        partitions.append(
            {
                frozenset(
                    role_of[m] for m in (component_containing(edges, a) or {a})
                )
                for a in role_of
            }
        )
    # the lexical winner really does move -- the phenomenon the docstring names
    assert carriers[0] != carriers[1]
    assert carriers == [{2}, {0}]
    # ...and the membership it decides does not
    assert partitions[0] == partitions[1] == {frozenset({0, 1, 2, 3})}


def test_a_near_edge_above_the_exempt_minimum_still_fires() -> None:
    """The over-correction guard: the exemption is about the minimum, not
    about the near rule.  Two in-band amounts that are both above it still
    join inside their block."""
    from sybilkit import Dataset

    rows = [
        _row("0x" + "aa" * 4 + f"{1:032x}", EXEMPT + 2_000_000_000_000_000, block=900, log_index=1),
        _row("0x" + "aa" * 4 + f"{2:032x}", EXEMPT + 5_000_000_000_000_000, block=900, log_index=2),
    ]
    edges = amount_edges(Dataset.from_events(rows, []), WITH_MIN)
    assert len(edges) == 1
    assert "near-identical" in edges[0].reason.human_string
