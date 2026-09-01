"""Eligibility policies: what a consumer excludes, given what the rules linked."""

from __future__ import annotations

import pytest

from sybilkit.eligibility import (
    DEFAULT_POLICY_ID,
    POLICIES,
    POLICIES_BY_ID,
    AuditedWindows,
    evaluate,
    wallet_standing,
)


def wallet(address="0xaa", status="flagged", families=(), cluster_id=0):
    return {
        "address": address,
        "status": status,
        "member_families": list(families),
        "cluster_id": cluster_id,
    }


WINDOWS = AuditedWindows(frozenset({"0xfarm"}), (), {})


@pytest.mark.parametrize("status", ["clean", "review"])
def test_a_policy_never_excludes_a_wallet_the_rules_did_not_flag(status: str) -> None:
    """Policies narrow what being flagged costs. They never widen the net."""
    row = wallet(address="0xfarm", status=status, families=("amount", "cadence", "funding"))
    for policy in POLICIES:
        assert policy.excludes(row, 5, WINDOWS.members) is False


def test_each_policy_reads_the_evidence_it_names() -> None:
    two = wallet(families=("amount", "cadence"))
    three = wallet(families=("amount", "cadence", "funding"))
    audited = wallet(address="0xfarm", families=("amount", "cadence"))

    assert POLICIES_BY_ID["E0"].excludes(two, 1, WINDOWS.members) is True
    assert POLICIES_BY_ID["E3"].excludes(two, 3, WINDOWS.members) is False
    assert POLICIES_BY_ID["E3"].excludes(three, 1, WINDOWS.members) is True
    assert POLICIES_BY_ID["E3"].excludes(audited, 1, WINDOWS.members) is True
    assert POLICIES_BY_ID["E9"].excludes(two, 3, WINDOWS.members) is True
    assert POLICIES_BY_ID["E9"].excludes(two, 2, WINDOWS.members) is False


def test_only_the_current_standard_is_not_a_proposal() -> None:
    assert DEFAULT_POLICY_ID == "E0"
    assert POLICIES_BY_ID["E0"].proposal is False
    assert [p.id for p in POLICIES if p.proposal] == ["E3", "E9"]


def test_a_missing_window_artifact_disables_only_the_policy_that_needs_it() -> None:
    clusters = [{"id": 0, "families": ["amount", "cadence", "funding"]}]
    summaries = {row["id"]: row for row in evaluate([wallet()], clusters, AuditedWindows.empty())}
    assert summaries["E3"]["available"] is False
    assert summaries["E0"]["available"] is True
    assert summaries["E9"]["available"] is True
    assert [row["id"] for row in wallet_standing(wallet(), clusters[0], AuditedWindows.empty())] == [
        "E0",
        "E9",
    ]


def test_a_missing_artifact_is_not_an_error(tmp_path) -> None:
    assert AuditedWindows.load(tmp_path / "absent.json.gz").available is False


def test_evaluate_separates_status_from_eligibility() -> None:
    """A flagged wallet may be eligible; that is the whole point of the layer."""
    rows = [
        wallet(address="0xa", families=("amount", "cadence")),
        wallet(address="0xb", families=("amount", "cadence", "funding")),
        wallet(address="0xc", status="clean"),
    ]
    clusters = [{"id": 0, "families": ["amount", "cadence"]}]
    summaries = {row["id"]: row for row in evaluate(rows, clusters, WINDOWS)}
    assert summaries["E0"]["excluded"] == 2
    assert summaries["E3"]["excluded"] == 1
    assert summaries["E3"]["eligible_by_analysis_status"] == {"flagged": 1, "clean": 1}


def test_points_share_is_reported_only_when_points_are_given() -> None:
    rows = [wallet(address="0xa", families=("a", "b", "c")), wallet(address="0xb", status="clean")]
    clusters = [{"id": 0, "families": ["a", "b", "c"]}]
    without = {row["id"]: row for row in evaluate(rows, clusters, WINDOWS)}
    assert "excluded_points_share" not in without["E3"]
    with_points = {
        row["id"]: row
        for row in evaluate(rows, clusters, WINDOWS, points={"0xa": 300, "0xb": 100})
    }
    assert with_points["E3"]["excluded_points_share"] == 0.75
