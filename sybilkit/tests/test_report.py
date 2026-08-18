"""WP1.6 — ``DetectResult``: wallet verdicts, the flagged set, the threshold.

Everything here is hand-built, because the value object must behave before
``detect`` exists to feed it.  The detect-built identities (``total ==
flagged + clean``, cluster points equal summed member curve points) are pinned
in ``test_cluster.py``, where the producer lives.
"""

from __future__ import annotations


from sybilkit.report import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    Cluster,
    DetectResult,
    Reason,
    WalletVerdict,
)

A1 = "0x" + "11" * 20
A2 = "0x" + "22" * 20
B1 = "0x" + "33" * 20
STRANGER = "0x" + "99" * 20
CLEAN = "0x" + "aa" * 20


def _cluster(cluster_id, members, confidence, points=100, share=0.01) -> Cluster:
    return Cluster(
        cluster_id=cluster_id,
        members=tuple(members),
        reasons=(Reason("amount", "identical 0.45Ξ send ×2", 0.75),),
        confidence=confidence,
        points=points,
        points_share=share,
        span_blocks=10,
        size=len(members),
    )


def _result() -> DetectResult:
    high = _cluster(0, (A1, A2), confidence=0.64, points=9081, share=0.0682)
    low = _cluster(1, (B1,), confidence=0.43, points=139218, share=0.0052)
    res = DetectResult(
        clusters=[high, low],
        total_points=26_585_740,
        flagged_points=9_081,
        clean_points=26_576_659,
    )
    res.analyzed = frozenset({A1, A2, B1, CLEAN})
    return res


def test_wallet_returns_a_verdict_for_a_member() -> None:
    res = _result()
    v = res.wallet(A1)
    assert isinstance(v, WalletVerdict)
    assert v.in_cluster is True
    assert v.cluster_id == 0
    assert v.confidence == 0.64
    assert v.reasons and v.reasons[0].family == "amount"


def test_wallet_returns_none_for_a_stranger_never_a_zero_confidence_verdict() -> None:
    """A stranger is not a wallet scored clean.  ``None`` is the only honest
    answer for an address the analysis never looked at."""
    res = _result()
    assert res.wallet(STRANGER) is None


def test_wallet_separates_analyzed_clean_from_not_analyzed() -> None:
    """The representable negative: an analyzed non-member gets
    ``in_cluster=False`` with empty reasons — a different object from the
    stranger's ``None``, and the two must never collapse (the FARM-row
    defect, one wave early)."""
    res = _result()
    v = res.wallet(CLEAN)
    assert isinstance(v, WalletVerdict)
    assert v.in_cluster is False
    assert v.cluster_id is None
    assert v.reasons == ()
    assert v.confidence == 0.0


def test_a_hand_built_result_defaults_to_knowing_no_population() -> None:
    """Without ``analyzed`` being set by ``detect``, a non-member lookup is
    ``None`` — the safe default is "not analyzed", never a confident clean."""
    res = DetectResult(
        clusters=[_cluster(0, (A1,), 0.9)],
        total_points=100,
        flagged_points=100,
        clean_points=0,
    )
    assert res.wallet(A1) is not None
    assert res.wallet(CLEAN) is None


def test_wallet_lookup_is_case_insensitive() -> None:
    """Members are lowercase by contract; a checksummed query must not turn a
    member into a stranger."""
    res = _result()
    assert res.wallet(A1.upper().replace("0X", "0x")) is not None


def test_flagged_is_exactly_the_members_at_or_above_the_threshold() -> None:
    res = _result()
    assert res.flagged == {A1, A2}  # the 0.43 cluster stays graduated, unflagged
    assert all(a == a.lower() for a in res.flagged)


def test_flagged_respects_a_caller_supplied_threshold() -> None:
    high = _cluster(0, (A1, A2), confidence=0.64)
    low = _cluster(1, (B1,), confidence=0.43)
    res = DetectResult(
        clusters=[high, low],
        total_points=100,
        flagged_points=100,
        clean_points=0,
        confidence_threshold=0.4,
    )
    assert res.flagged == {A1, A2, B1}
    stricter = DetectResult(
        clusters=[high, low],
        total_points=100,
        flagged_points=100,
        clean_points=0,
        confidence_threshold=0.9,
    )
    assert stricter.flagged == set()


def test_the_default_threshold_is_the_frozen_one() -> None:
    res = DetectResult(clusters=[], total_points=0, flagged_points=0, clean_points=0)
    assert res.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD == 0.5


def test_a_member_of_an_unflagged_cluster_still_gets_its_graduated_verdict() -> None:
    """Confidence stays graduated either side of the flagged cut: below the
    threshold the wallet is linked-with-reasons, just not "flagged"."""
    res = _result()
    v = res.wallet(B1)
    assert v is not None
    assert v.in_cluster is True
    assert v.confidence == 0.43
    assert B1 not in res.flagged


# ===========================================================================
# Review R4.3 — the object has to agree with itself on a spelling
# ===========================================================================
#
# `clean_list` was taught (R4.2) to lowercase `res.analyzed` on read, because
# `CleanList.standing` and `CleanList.clean_rank` lowercase every query they
# are given.  `DetectResult` lowercases its queries too — and then tested them
# against the **raw** `analyzed` frozenset and the **raw** `_by_member` index,
# so the same hand-built result answered "clean" from one object and "never
# analyzed" from the other.  Ruling D1-B made that hand-built path first-class
# (there is no dataset fallback any more), so the disagreement is not a corner:
# it is the path a caller with counters and no run is now expected to take.
#
# Every fix below is a **no-op on every path `detect` produces** — the class
# documents `analyzed` and `Cluster.members` as lowercase and `detect` honours
# it — which is what the live-path test at the end of this block pins.


def _checksummed(addr: str) -> str:
    """*addr* with its hex letters uppercased — the EIP-55 spelling shape."""
    return "0x" + addr[2:].upper()


def _mini_dataset(addrs):
    """A tiny ``Dataset`` — one deposit each, so ``clean_list`` can rank them.

    Local rather than shared with ``test_curator.py``: this file's subject is
    the value object, and the dataset is only here because the contradiction
    R4.3 names is a contradiction *between two objects*.
    """
    from sybilkit.model import Dataset

    deposits, firsts = [], []
    for i, addr in enumerate(addrs, start=1):
        deposits.append(
            {
                "contributor": addr,
                "hour": 0,
                "amount_wei": 10**18,
                "credited_delta_wei": 10**18,
                "weight_added_wei": 15 * 10**17,
                "new_weight_wei": 15 * 10**17,
                "tx_count": 1,
                "block_number": 100 + i,
                "log_index": 1,
                "tx_hash": "0x" + f"{i:064x}",
            }
        )
        firsts.append({"contributor": addr, "index": i})
    return Dataset.from_events(deposits, firsts)


def test_wallet_and_standing_agree_on_a_mixed_case_hand_built_result() -> None:
    """**Review R4.3.**  The library contradicted itself, address by address.

    ``clean_list`` lowercases ``res.analyzed`` on read; ``DetectResult.wallet``
    lowercased the *query* and then tested it against the raw frozenset.  So on
    a hand-built result whose ``analyzed`` carries checksummed spellings, the
    very same wallet was ``"clean"`` to :meth:`CleanList.standing` and ``None``
    — never analyzed — to :meth:`DetectResult.wallet`.  Before R4.2 both were
    wrong in the same direction and nothing showed; the disagreement is new.

    The pairing asserted here is the one the two docstrings promise:
    ``standing() == "unknown"`` **iff** ``wallet() is None``.
    """
    from sybilkit.curator import CuratorPreset, clean_list

    addrs = [f"0x{i:040x}" for i in range(1, 13)]
    survivor, removed = addrs[9], addrs[10]  # ...00a and ...00b — real letters
    assert survivor != _checksummed(survivor)

    res = DetectResult([_cluster(1, (removed,), confidence=1.0)], 0, 0, 0)
    res.analyzed = frozenset({_checksummed(survivor), _checksummed(removed)})

    preset = CuratorPreset(points_per_eth=1000, min_deposit_wei=5 * 10**16)
    clean = clean_list(_mini_dataset(addrs), res, preset)

    for addr in addrs:
        looked_at = res.wallet(addr) is not None
        assert (clean.standing(addr) == "unknown") is not looked_at, addr

    # and the two specifics, spelled out
    assert clean.standing(survivor) == "clean"
    verdict = res.wallet(survivor)
    assert verdict is not None and verdict.in_cluster is False
    assert res.wallet(_checksummed(survivor)) is not None
    assert clean.standing(removed) == "removed"
    linked = res.wallet(removed)
    assert linked is not None and linked.in_cluster is True


def test_a_mixed_case_flagged_member_does_not_survive_a_not_in_flagged_filter() -> None:
    """The same shape one attribute over: ``flagged`` returned raw spellings.

    ``flagged`` is documented as "**lowercase** members of every cluster at or
    above the threshold", and every consumer filters with it — the library's
    own ``clean_list``/``bench`` lowercase defensively, but a caller that takes
    the docstring at its word writes ``addr not in res.flagged`` and a
    checksummed cluster member walks straight through the filter it was
    supposed to be removed by.
    """
    addrs = [f"0x{i:040x}" for i in range(10, 13)]  # ...00a/b/c — real letters
    member = addrs[0]
    assert member != _checksummed(member)
    res = DetectResult(
        [_cluster(0, (_checksummed(member),), confidence=0.9)], 100, 100, 0
    )

    assert res.flagged == {member}
    assert all(a == a.lower() for a in res.flagged)
    assert [a for a in addrs if a not in res.flagged] == addrs[1:]


def test_a_checksummed_cluster_member_is_still_a_member_to_wallet() -> None:
    """The third raw read: the ``_by_member`` index was keyed on the spelling.

    ``wallet`` lowercases its query, so a checksummed member was a stranger to
    the result that contains it — the reverse of the ``analyzed`` bug and, on a
    result whose ``analyzed`` was set, a *worse* answer: linked read back as
    the representable clean.  Both spellings of the query must find it.
    """
    member = f"0x{10:040x}"
    res = DetectResult(
        [_cluster(0, (_checksummed(member),), confidence=0.9)], 100, 100, 0
    )
    res.analyzed = frozenset({member})

    for query in (member, _checksummed(member)):
        verdict = res.wallet(query)
        assert verdict is not None, query
        assert verdict.in_cluster is True, query
        assert verdict.cluster_id == 0


def test_the_live_lowercase_path_is_byte_for_byte_what_it_was() -> None:
    """The fix is defence on the hand-built path and nothing else.

    ``detect`` sets ``analyzed`` from lowercase contributors and spells every
    ``Cluster.members`` lowercase, so normalising on write can only be a no-op
    there — asserted against a real run rather than argued, and against the
    hand-built lowercase result the rest of this file uses.
    """
    from sybilkit.cluster import detect

    addrs = [f"0x{i:040x}" for i in range(1, 13)]
    live = detect(_mini_dataset(addrs))
    assert live.analyzed == frozenset(addrs)
    assert isinstance(live.analyzed, frozenset)
    for addr in addrs:
        assert live.wallet(addr) is not None

    res = _result()
    assert res.analyzed == frozenset({A1, A2, B1, CLEAN})
    assert res.flagged == {A1, A2}
    assert res.wallet(STRANGER) is None
    assert res.wallet(CLEAN) == WalletVerdict(False, None, (), 0.0)
