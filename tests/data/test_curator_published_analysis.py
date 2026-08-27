"""T3 — reconstructing ``sybilkit`` objects from published cluster membership.

THE LIST's linked-wallet analysis is switching from a locally-computed sweep
to a published, immutable dataset.  This is the hinge: turn the published
cluster metadata (``overview_trimmed.json``'s ``clusters``) and per-wallet
membership (``export_trimmed.json``'s ``rows``) into real ``sybilkit.Cluster``
/ ``sybilkit.DetectResult`` objects, so the library's own pure ``segments()``
and ``clean_list()`` can run over them unchanged.

The trimmed fixtures are a matched pair verified against the live service
(T1): cluster ids agree between the overview and the export, and each
cluster's declared ``size`` equals its kept-member count.  ``export_hostile.json``
is one cluster (``cluster_id: 1`` on every clustered row) with one defect per
row, used to prove a malformed row costs the ROW, never the sweep.
"""

from __future__ import annotations

import json
import pathlib

from maxpane_dashboard.data import curator_clusters as cc

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures/curator/published"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _hostile_cluster():
    """The one-cluster overview matching every clustered row in
    ``export_hostile.json``, all of which carry ``cluster_id: 1``.

    Its lone reason spells a forbidden word (``FORBIDDEN_WORDS`` in
    ``curator_clusters.py``) so ``clusters_from_published`` is proven to
    route every reason through ``pattern_language`` on the way in, not just
    the ones this dashboard already knows are polite.
    """
    return {
        "id": 1,
        "size": 3,
        "confidence": 0.9,
        "band": "high",
        "points": 250,
        "points_share": 0.01,
        "span_blocks": 12,
        "families": ["amount"],
        "reasons": [
            {
                "family": "amount",
                "strength": 0.9,
                "text": "flagged as a wash-trading sybil ring",
            }
        ],
    }


def test_the_reconstructed_clusters_match_the_overviews_own_sizes():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    clusters = cc.clusters_from_published(ov["clusters"], ex["rows"])
    by_id = {c.cluster_id: c for c in clusters}
    for declared in ov["clusters"]:
        assert len(by_id[declared["id"]].members) == declared["size"]


def test_members_are_lowercased_on_both_sides():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    rows = [dict(r, address=r["address"].upper()) for r in ex["rows"]]
    clusters = cc.clusters_from_published(ov["clusters"], rows)
    assert all(m == m.lower() for c in clusters for m in c.members)


def test_a_row_whose_address_is_malformed_is_dropped_not_rendered():
    # export_hostile.json's own malformed-address row ("nothex") carries
    # cluster_id: null, so it is already excluded by the cluster_id guard --
    # asserting against it alone would prove nothing about the address guard
    # specifically (Task 2's lesson: isolate the guard under test, don't let
    # an earlier guard silently take the credit). This adds one more row,
    # otherwise valid, that only the address guard can reject.
    ov = {"clusters": [_hostile_cluster()]}
    rows = _load("export_hostile.json")["rows"] + [
        {
            "cluster_id": 1,
            "address": "0xNOTHEXNOTHEXNOTHEXNOTHEXNOTHEXNOTHEXNOTH",
            "status": "flagged",
        }
    ]
    clusters = cc.clusters_from_published(ov["clusters"], rows)
    joined = [m for c in clusters for m in c.members]
    assert not any("nothex" in m for m in joined)


def test_a_hostile_reason_is_translated_through_pattern_language():
    # The endpoint is third-party: a reason string that spells a forbidden
    # word must never survive into a built Cluster's reasons.
    ov = {"clusters": [_hostile_cluster()]}
    rows = _load("export_hostile.json")["rows"]
    clusters = cc.clusters_from_published(ov["clusters"], rows)
    cluster = next(c for c in clusters if c.cluster_id == 1)
    human_strings = [r.human_string for r in cluster.reasons]
    assert human_strings == ["matching send amounts"]
    assert not any(
        word in s.lower() for s in human_strings for word in cc.FORBIDDEN_WORDS
    )


def test_a_malformed_cluster_entry_is_skipped_not_crashed():
    ov_clusters = [_hostile_cluster(), {"id": None, "size": 1}, "not-a-mapping"]
    rows = _load("export_hostile.json")["rows"]
    clusters = cc.clusters_from_published(ov_clusters, rows)
    assert [c.cluster_id for c in clusters] == [1]


def test_the_band_is_the_publishers_word_when_it_is_one_we_know():
    assert (
        cc.published_band({"band": "low", "families": ["amount", "cadence", "gas"]})
        == "low"
    )


def test_an_unknown_band_word_falls_back_to_our_own_family_grading():
    # The endpoint is third-party: "critical" must never reach a screen.
    assert cc.published_band({"band": "critical", "families": ["amount", "funding"]}) == "high"
    assert cc.published_band({"band": None, "families": ["amount", "cadence"]}) == "low"


def test_review_members_are_indexed_by_cluster_with_their_own_families():
    ex = _load("export_hostile.json")
    got = cc.review_members_of(ex["rows"])
    assert got[1] == {"0x5555555555555555555555555555555555555555": ["amount"]}


def test_a_hand_built_result_answers_membership_like_a_detected_one():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    res = cc.detect_result_from_published(ov["clusters"], ex["rows"], ov["totals"])
    # detect_result_from_published leaves `analyzed` at DetectResult's own
    # frozenset() default -- by design, a later caller (the manager, wiring
    # this to the LOCAL fold) sets it from the population *this build*
    # actually folded, not the publisher's. Without setting it here, any
    # non-member reads as "never analyzed" (None), not the representable
    # False, so this test sets it the same way that later caller will, using
    # the export's own rows as the folded population.
    res.analyzed = {r["address"] for r in ex["rows"]}
    member = next(r["address"] for r in ex["rows"] if r["cluster_id"] is not None)
    assert res.wallet(member).in_cluster is True
    clean = next(r["address"] for r in ex["rows"] if r["status"] == "clean")
    assert res.wallet(clean).in_cluster is False


def test_a_boolean_is_not_read_as_a_number():
    # json.loads turns `true` into a Python bool, which IS an int.
    assert cc.published_band({"band": "low", "families": []}) == "low"
    clusters = cc.clusters_from_published(
        [
            {
                "id": 1,
                "points": True,
                "confidence": 0.9,
                "points_share": 0.1,
                "span_blocks": None,
                "families": [],
                "reasons": [],
                "band": "low",
            }
        ],
        [],
    )
    assert clusters[0].points == 0


def test_a_non_finite_confidence_is_refused():
    clusters = cc.clusters_from_published(
        [
            {
                "id": 1,
                "points": 1,
                "confidence": float("inf"),
                "points_share": 0.1,
                "span_blocks": None,
                "families": [],
                "reasons": [],
                "band": "low",
            }
        ],
        [],
    )
    assert clusters[0].confidence == 0.0


def test_clusters_are_ordered_widest_share_first():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    res = cc.detect_result_from_published(ov["clusters"], ex["rows"], ov["totals"])
    shares = [c.points_share for c in res.clusters]
    assert shares == sorted(shares, reverse=True)
