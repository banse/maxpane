"""WP1.6 — ``DetectResult``: wallet verdicts, the flagged set, the threshold.

Everything here is hand-built, because the value object must behave before
``detect`` exists to feed it.  The detect-built identities (``total ==
flagged + clean``, cluster points equal summed member curve points) are pinned
in ``test_cluster.py``, where the producer lives.
"""

from __future__ import annotations

import pytest

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
