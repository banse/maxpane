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

import pytest

from maxpane_dashboard.data import curator_clusters as cc
from maxpane_dashboard.data.curator_models import DepositEvent

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


# ---------------------------------------------------------------------------
# T4 — the analysis itself, built from published membership
# ---------------------------------------------------------------------------
#
# ``build_analysis_from_published`` is ``build_analysis`` forked from its
# ``res = detect(...)`` line: the clusters come off the wire, everything
# downstream of them is still the library's own pure ``segments()`` and
# ``clean_list()`` run over the LOCAL dataset.  So the tests below need a
# local half, and it has to agree with the published half wei-for-wei —
# ``_fixture_events`` builds one deposit per exported row carrying that row's
# own ``weight_eth``, ``credit_eth``, ``first_hour``, ``first_index`` and
# ``tx_count``, and
# ``test_the_local_fixture_reproduces_every_published_rows_own_measurements``
# is the guard that says so.  Without it the headline test could compare two
# sets that were never equal and still look green.

#: The two live chain reads, as the fixtures measured them.  Standing in for
#: ``POINTS_PER_ETH()`` and ``minDeposit()``, exactly as ``RATE``/``MINIMUM``
#: do in ``test_curator_clusters.py`` — never a default inside the adapter.
RATE = 1000
MINIMUM = 50_000_000_000_000_000

_WEI = 10**18


def _preset():
    return cc.build_preset(RATE, MINIMUM)


def _row_wei(eth):
    """An ETH reading from a published row, back in wei.

    The publisher rounds to the decimals it prints; that rounding is the only
    loss in the round trip and it does not move a single ``points`` value —
    see the fixture guard test.
    """
    return int(round(eth * _WEI))


def _fixture_events(rows=None):
    """One local deposit per exported row, carrying that row's own words.

    The published export is the *other* half of this seam: it says what the
    publisher measured for each wallet.  A local ``Dataset`` that disagreed
    with it would make every downstream comparison meaningless while still
    producing numbers, so each deposit is built to reproduce its row —
    ``new_weight_wei`` from ``weight_eth`` (the high-water mark
    ``final_weights`` reads), ``credited_delta_wei`` from ``credit_eth``,
    ``hour`` from ``first_hour``, ``tx_count`` verbatim — and the join index
    doubles as the block number so chain order is join order.

    ``weight_added_wei == credited_delta_wei * early_bps // 10_000`` is
    ``DepositEvent``'s own documented identity, so ``early_bps`` is derived
    from the two readings rather than remembered.
    """
    rows = _load("export_trimmed.json")["rows"] if rows is None else rows
    events = []
    for row in rows:
        weight = _row_wei(row["weight_eth"])
        credited = _row_wei(row["credit_eth"])
        early_bps = weight * 10_000 // credited if credited else 10_000
        events.append(
            DepositEvent(
                contributor=row["address"],
                hour=row["first_hour"],
                amount_wei=credited,
                credited_delta_wei=credited,
                weight_added_wei=credited * early_bps // 10_000,
                new_weight_wei=weight,
                tx_count=row["tx_count"],
                hour_total_wei=credited,
                early_bps=early_bps,
                block_number=1_000_000 + row["first_index"],
                tx_hash="0x" + f"{row['first_index']:064x}",
                log_index=0,
                ts=None,
            )
        )
    return events


def _fixture_firsts(rows=None):
    """The ``FirstDeposit`` fold: the protocol's own 1-based join index."""
    rows = _load("export_trimmed.json")["rows"] if rows is None else rows
    return [
        {"contributor": row["address"], "index": row["first_index"]}
        for row in rows
    ]


def _build(ov=None, ex=None, **kwargs):
    ov = _load("overview_trimmed.json") if ov is None else ov
    ex = _load("export_trimmed.json") if ex is None else ex
    payload = {
        "clusters": ov["clusters"],
        "rows": ex["rows"],
        "totals": ov["totals"],
        "config": _preset(),
    }
    payload.update(kwargs)
    return cc.build_analysis_from_published(
        _fixture_events(), _fixture_firsts(), **payload
    )


def _cluster_id_of(group, ex):
    """The published cluster id a rebuilt group's members all belong to.

    ``groups`` rows carry no cluster id (``build_analysis`` never had one to
    carry), so the members are the join.  Asserting the id is *single* is
    half the test: a group holding members of two published clusters would
    mean the reconstruction lost the membership it exists to preserve.
    """
    by_address = {row["address"].lower(): row for row in ex["rows"]}
    ids = {by_address[member]["cluster_id"] for member in group["members"]}
    assert len(ids) == 1, f"group spans published clusters {sorted(ids)}"
    return ids.pop()


def test_the_local_fixture_reproduces_every_published_rows_own_measurements():
    """The local half of the seam agrees with the published half, per wallet.

    Built over an empty cluster list on purpose: with nothing flagged every
    one of the 82 exported wallets survives into ``clean_list_rows``, so this
    compares the *whole* fixture against the *whole* export rather than the
    40 rows the real payload happens to leave clean.
    """
    ex = _load("export_trimmed.json")
    result = _build(
        clusters=[], rows=[], totals={"points": 0, "linked_points": 0}
    )
    mine = {row["address"]: row for row in result.clean_list_rows}
    assert len(mine) == len(ex["rows"])
    for row in ex["rows"]:
        got = mine[row["address"].lower()]
        assert got["points"] == row["points"], row["address"]
        assert got["first_hour"] == row["first_hour"], row["address"]
        assert got["first_index"] == row["first_index"], row["address"]
        assert got["tx_count"] == row["tx_count"], row["address"]
        assert got["weight_eth"] == pytest.approx(row["weight_eth"])


def test_the_rebuilt_clean_list_is_the_published_clean_list_exactly():
    """Not the same count -- the same addresses."""
    ex = _load("export_trimmed.json")
    result = _build()
    published_clean = {
        r["address"].lower() for r in ex["rows"] if r["status"] == "clean"
    }
    assert set(result.clean_ranks) == published_clean
    assert result.clean_contributors == len(published_clean)


def test_the_analyzed_population_is_the_local_fold_not_the_publishers():
    """``res.analyzed`` is this caller's job, and dropping it fails silently.

    ``detect_result_from_published`` leaves ``analyzed`` at ``DetectResult``'s
    ``frozenset()`` default by design (T3), and ``clean_list`` takes its
    survivors from ``analyzed`` and nothing else.  Left unset, every
    non-member reads "not analyzed" rather than "analyzed and clean", the
    clean list comes back **empty**, and every other counter still looks
    plausible.
    """
    ex = _load("export_trimmed.json")
    result = _build()
    assert result.result.analyzed == {
        row["address"].lower() for row in ex["rows"]
    }
    clean = next(r["address"].lower() for r in ex["rows"] if r["status"] == "clean")
    linked = next(
        r["address"].lower() for r in ex["rows"] if r["cluster_id"] is not None
    )
    assert result.clean.standing(clean) == "clean"
    assert result.clean.standing(linked) == "removed"


def test_every_group_carries_its_own_review_members_and_no_others():
    ex = _load("export_trimmed.json")
    result = _build()
    assert result.groups
    for group in result.groups:
        cluster_id = _cluster_id_of(group, ex)
        expected = {
            row["address"].lower(): row["member_families"]
            for row in ex["rows"]
            if row["cluster_id"] == cluster_id and row["status"] == "review"
        }
        assert group["review_members"] == expected


def test_a_group_with_no_review_member_carries_an_empty_mapping_not_none():
    """``{}`` reads "we looked and there were none"; ``None`` reads "unknown"."""
    ex = _load("export_trimmed.json")
    result = _build()
    without = [
        group
        for group in result.groups
        if not any(
            row["status"] == "review"
            and row["cluster_id"] == _cluster_id_of(group, ex)
            for row in ex["rows"]
        )
    ]
    assert without, "the fixture must hold a group with no review member"
    for group in without:
        assert group["review_members"] == {}
    assert all(g["review_members"] is not None for g in result.groups)


def test_the_review_segment_row_counts_the_review_wallets_and_their_share():
    """Both numbers folded from the payload — neither is written into code."""
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    result = _build(ov, ex)
    row = next(r for r in result.segment_rows if r["label"] == "under review")
    reviewed = [
        r
        for r in ex["rows"]
        if r["status"] == "review" and isinstance(r["cluster_id"], int)
    ]
    assert reviewed
    assert row["contributors"] == len(reviewed)
    assert row["points_share_pct"] == pytest.approx(
        sum(r["points"] for r in reviewed) / ov["totals"]["points"] * 100
    )


def test_the_review_row_follows_the_operators_band():
    result = _build()
    assert result.segment_rows[0]["label"] == "linked groups"
    assert result.segment_rows[1]["label"] == "under review"


def test_the_review_row_leads_when_the_payload_names_no_operator_band():
    """The insert position is computed, never a remembered ``1``.

    With no clusters there is no ``operators`` band, so ``ordered`` starts
    with a cohort — and a hardcoded ``1`` would drop the review row *between*
    the early and late cohorts, which is the one place it means nothing.
    """
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    result = _build(ov, ex, clusters=[])
    assert result.operator_rows == []
    assert result.segment_rows[0]["label"] == "under review"
    assert result.segment_rows[1]["label"].startswith("early cohort")


def test_no_review_row_is_appended_when_the_payload_reviews_nobody():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    rows = [r for r in ex["rows"] if r["status"] != "review"]
    result = _build(ov, ex, rows=rows)
    assert not any(r["label"] == "under review" for r in result.segment_rows)


def test_a_review_flagged_group_says_so_in_its_reasons_and_not_in_its_band():
    """Group review is a sentence in the reasons; the band stays the band.

    Measured on the live service: the ``review_flag`` groups hold **zero**
    review members and every group that holds them is unflagged.  A group row
    banding itself as "under review" while every one of its members reads
    linked would be a contradiction the publisher never made.
    """
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    result = _build(ov, ex)
    flagged_ids = {c["id"] for c in ov["clusters"] if c["review_flag"]}
    quiet_ids = {c["id"] for c in ov["clusters"] if not c["review_flag"]}
    assert flagged_ids and quiet_ids
    bands = {c["id"]: c["band"] for c in ov["clusters"]}
    seen = set()
    for group in result.groups:
        cluster_id = _cluster_id_of(group, ex)
        seen.add(cluster_id)
        assert group["conf"] == bands[cluster_id]
        assert group["conf"] in ("high", "low")
        assert ("under review" in group["reasons"]) is (cluster_id in flagged_ids)
    assert seen == flagged_ids | quiet_ids


def test_the_group_band_is_the_publishers_word_not_our_own_grading():
    """``conf`` comes from ``published_band``, which is the whole point of it.

    The two agree on every one of the 160 live clusters, so the trimmed
    payload alone cannot tell them apart -- which is exactly how a
    ``_grade_families`` left in place would ship green.  This contradicts one
    cluster on purpose: cluster 3 carries a ``funding`` reason, so our own
    grading calls it ``high`` while the payload here says ``low``.
    """
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    contradicted = json.loads(json.dumps(ov))
    contradicted["clusters"][0]["band"] = "low"
    assert cc._grade_families(
        r["family"] for r in contradicted["clusters"][0]["reasons"]
    ) == "high"
    result = _build(contradicted, ex)
    assert result.groups[0]["conf"] == "low"
    assert result.operator_rows[0]["conf"] == "low"


def test_a_forbidden_word_in_a_published_reason_never_reaches_the_row():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    poisoned = json.loads(json.dumps(ov))
    poisoned["clusters"][0]["reasons"][0]["text"] = (
        "wash-trading sybil ring · obvious fraud"
    )
    result = _build(poisoned, ex)
    rendered = [s for row in result.operator_rows for s in row["reasons"]]
    rendered += [s for group in result.groups for s in group["reasons"]]
    rendered += [row["label"] for row in result.segment_rows]
    rendered += [row["detail"] for row in result.segment_rows]
    assert rendered
    assert not any(
        word in text.lower() for text in rendered for word in cc.FORBIDDEN_WORDS
    )
    # Replaced by its family's own phrase, not dropped: the reason count is
    # unchanged against the same build over the untouched payload.
    clean = _build(ov, ex)
    assert [len(g["reasons"]) for g in result.groups] == [
        len(g["reasons"]) for g in clean.groups
    ]
    assert "shared funder chain" in result.groups[0]["reasons"]


def test_sqrt_subsidy_x_is_filled_for_every_operator_row():
    result = _build()
    assert result.operator_rows
    assert all(row["sqrt_subsidy_x"] is not None for row in result.operator_rows)


def test_operator_rows_lead_with_the_widest_share():
    ov = _load("overview_trimmed.json")
    result = _build(ov)
    shares = [row["points_share_pct"] for row in result.operator_rows]
    assert shares == sorted(shares, reverse=True)
    assert shares[0] == pytest.approx(
        max(c["points_share"] for c in ov["clusters"]) * 100
    )


def test_two_calls_over_one_payload_return_equal_results():   # purity
    first, second = _build(), _build()
    assert first.operator_rows == second.operator_rows
    assert first.segment_rows == second.segment_rows
    assert first.clean_list_rows == second.clean_list_rows
    assert first.groups == second.groups
    assert first.clean_ranks == second.clean_ranks
    assert (
        first.operators_count,
        first.clean_points,
        first.clean_contributors,
        first.points_total,
        first.flagged_points_share_pct,
    ) == (
        second.operators_count,
        second.clean_points,
        second.clean_contributors,
        second.points_total,
        second.flagged_points_share_pct,
    )


def test_the_analysis_keys_still_fill_from_a_published_build():
    """The published build is the same ``AnalysisResult`` the manager reads."""
    result = _build()
    keys = cc.analysis_keys(result)
    assert set(keys) == set(cc.CURATOR_ANALYSIS_KEYS)
