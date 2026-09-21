"""Tests for the swarm v2 folds in ``maxpane_dashboard.data.surf_swarm`` (plan WP3).

Every payload is the committed 2026-09-21 corpus from ``api.imd.fun``
(``tests/fixtures/surf/swarm/v2/``, plan A3) or one of its three hand-made
shapes; hand-built lists cover the states the fourteen-minute live window
did not contain (cancelled, blocked, an unparseable seat). No network, no
wall clock: every ``now_ts`` is a literal.

Every literal pinned below was read off the JSON by hand and says which
field it came from, so the test cannot have been derived from the fold.
"""

from __future__ import annotations

import datetime

import pytest

from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS
from tests.surf_swarm_fixtures import (
    swarm_capture_v2,
    swarm_details_v2,
    swarm_manifest_v2,
)


def _iso(stamp: str) -> float:
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


#: A minute after MANIFEST ``captured_at`` (2026-09-21T00:08:51Z).
NOW = _iso("2026-09-21T00:09:00Z")
_DAY = 86_400
_TWO_DAYS = 2 * _DAY

# The two executing jobs of the capture (``jobs.json`` ``state == "executing"``).
EXECUTING_WITH_DETAIL = "f046299c-d94e-4760-9e3c-c1e2d3a1a3b2"   # createdAt 21:41:27.617Z
EXECUTING_NO_DETAIL = "708ea465-4171-4835-b193-69f01ac1a185"     # createdAt 21:41:09.309Z
OLD_COMPLETED = "7018907b-7466-4326-a602-e322913db496"            # 2026-09-16, reviews populated


@pytest.fixture(scope="module")
def health():
    return swarm_capture_v2("health")


@pytest.fixture(scope="module")
def jobs():
    return swarm_capture_v2("jobs")["jobs"]


@pytest.fixture(scope="module")
def skills():
    return swarm_capture_v2("skills")["skills"]


@pytest.fixture(scope="module")
def launches():
    return swarm_capture_v2("launches")["launches"]


@pytest.fixture(scope="module")
def sites():
    return swarm_capture_v2("sites")["sites"]


@pytest.fixture(scope="module")
def details():
    return swarm_details_v2()


@pytest.fixture(scope="module")
def manifest():
    return swarm_manifest_v2()


def _rows_match(rows, key):
    shape = SURF_ROW_KEYS[key]
    assert rows, f"no rows to check against {key}"
    for row in rows:
        assert tuple(row) == shape, (key, tuple(row))


# ---------------------------------------------------------------------------
# row shapes -- every row of every fold is exactly its SURF_ROW_KEYS tuple
# ---------------------------------------------------------------------------


def test_every_v2_row_carries_exactly_its_contract_fields_in_order(
    jobs, details, skills, launches, sites,
):
    seen = fold.merge_seen({}, jobs, details, now_ts=NOW, cap=5000, max_age_s=_TWO_DAYS)
    _rows_match(fold.inflight_rows(jobs, details, now_ts=NOW), "swarm_inflight_rows")
    _rows_match(fold.skill_rows(skills), "swarm_skill_rows")
    _rows_match(fold.launch_rows(launches), "swarm_launch_rows")
    _rows_match(fold.site_rows(sites), "swarm_site_rows")
    seat_rows = fold.seat_rows(details, seen)
    _rows_match(seat_rows, "swarm_seat_rows")
    # The /seats row folds (work, reviews) are shape-checked in test_surf_swarm_seats.py.


# ---------------------------------------------------------------------------
# queue_total / breaker
# ---------------------------------------------------------------------------


def test_queue_total_is_the_hand_sum_of_the_eight_pending_counters(health):
    # health.json: pendingVerification 0, pendingAttestation 0,
    # pendingDeployment 0, pendingDelivery 0, pendingFeedback 45,
    # pendingOracle 0, pendingFuzz 0, pendingSites 0  ->  45.
    assert sum(1 for k in health if k.startswith("pending")) == 8
    assert fold.queue_total(health) == 45


def test_queue_total_skips_non_int_counters_and_bools():
    health = {"pendingA": 3, "pendingB": "7", "pendingC": None, "pendingD": True,
              "pendingE": 2.5, "connectedDaemons": 99}
    assert fold.queue_total(health) == 3


def test_queue_total_is_none_when_nothing_could_be_summed():
    assert fold.queue_total(None) is None
    assert fold.queue_total([]) is None
    assert fold.queue_total({"connectedDaemons": 3}) is None
    # pending keys present but none an int: nothing was read -> None, not 0.
    assert fold.queue_total({"pendingA": None, "pendingB": "x"}) is None


def test_queue_total_reports_a_real_zero():
    assert fold.queue_total({"pendingA": 0, "pendingB": 0}) == 0


def test_breaker_three_way(health):
    # health.json: "deployBreaker": null  -> present and not tripped.
    assert health["deployBreaker"] is None
    assert fold.breaker(health) == {"tripped": False, "detail": None}
    # A string is the breaker's reason.
    assert fold.breaker({"deployBreaker": "too many failed deploys"}) == {
        "tripped": True, "detail": "too many failed deploys",
    }
    # Could not look: the key is absent, or health is not a mapping.
    assert fold.breaker({"status": "ok"}) is None
    assert fold.breaker(None) is None
    assert fold.breaker("ok") is None


def test_breaker_mapping_detail_prefers_reason_then_detail_then_first_str():
    assert fold.breaker({"deployBreaker": {"reason": "r", "detail": "d"}})["detail"] == "r"
    assert fold.breaker({"deployBreaker": {"detail": "d", "since": "s"}})["detail"] == "d"
    assert fold.breaker({"deployBreaker": {"n": 3, "since": "s"}})["detail"] == "s"
    assert fold.breaker({"deployBreaker": {"n": 3}}) == {"tripped": True, "detail": None}
    assert fold.breaker({"deployBreaker": True}) == {"tripped": True, "detail": None}
    assert fold.breaker({"deployBreaker": 7}) == {"tripped": True, "detail": None}


# ---------------------------------------------------------------------------
# inflight_rows
# ---------------------------------------------------------------------------


def test_inflight_rows_are_the_executing_jobs_newest_first_with_and_without_detail(
    jobs, details, manifest,
):
    rows = fold.inflight_rows(jobs, details, now_ts=NOW)
    assert [r["job_id"] for r in rows] == [EXECUTING_WITH_DETAIL, EXECUTING_NO_DETAIL]
    assert EXECUTING_NO_DETAIL not in details

    with_detail, no_detail = rows
    assert manifest["criteria"]["node_working"]["job_ids"][0] == EXECUTING_WITH_DETAIL
    # details/f046299c….json nodes[0]: key oracle_assess, role implement,
    # state working, seat {tokenId "463", agentId "50972"}, revisions 0.
    assert with_detail["node_key"] == "oracle_assess"
    assert with_detail["node_role"] == "implement"
    assert with_detail["node_state"] == "working"
    assert with_detail["agent_token"] == 463
    assert isinstance(with_detail["agent_token"], int)
    assert with_detail["agent_id"] == "50972"
    assert with_detail["revisions"] == 0
    assert with_detail["template"] == "skill:oracle-assess"
    assert with_detail["created_ts"] == _iso("2026-09-20T21:41:27.617Z")
    assert with_detail["age_s"] == NOW - _iso("2026-09-20T21:41:27.617Z")
    assert isinstance(with_detail["objective"], str)

    assert no_detail["created_ts"] == _iso("2026-09-20T21:41:09.309Z")
    assert no_detail["age_s"] == NOW - no_detail["created_ts"]
    for field in ("node_key", "node_role", "node_state", "agent_token", "agent_id", "revisions"):
        assert no_detail[field] is None, field


def test_inflight_rows_without_any_details_leave_every_node_field_none(jobs):
    for details in (None, {}):
        rows = fold.inflight_rows(jobs, details, now_ts=NOW)
        assert len(rows) == 2
        for row in rows:
            assert row["node_key"] is None and row["agent_token"] is None


def test_inflight_active_node_is_working_else_newest_non_accepted_else_none():
    job = {"id": "j", "state": "executing", "template": "t", "objective": "o",
           "createdAt": "2026-09-20T21:00:00Z"}
    nodes = [
        {"key": "a", "role": "implement", "state": "accepted", "revisions": 0,
         "updatedAt": "2026-09-20T21:30:00Z", "seat": {"tokenId": "1", "agentId": "a1"}},
        {"key": "b", "role": "review", "state": "waiting", "revisions": 1,
         "updatedAt": "2026-09-20T21:10:00Z", "seat": {"tokenId": "2", "agentId": "a2"}},
        {"key": "c", "role": "integrate", "state": "failed", "revisions": 2,
         "updatedAt": "2026-09-20T21:20:00Z", "seat": {"tokenId": "3", "agentId": "a3"}},
    ]
    # No node working: the newest updatedAt among the non-accepted wins (c).
    row = fold.inflight_rows([job], {"j": {"id": "j", "nodes": nodes}}, now_ts=NOW)[0]
    assert (row["node_key"], row["node_state"], row["agent_token"]) == ("c", "failed", 3)
    # A working node wins regardless of its age.
    working = dict(nodes[1], state="working")
    row = fold.inflight_rows([job], {"j": {"id": "j", "nodes": [nodes[0], working, nodes[2]]}},
                             now_ts=NOW)[0]
    assert (row["node_key"], row["node_state"]) == ("b", "working")
    # Every node accepted: no active node.
    all_done = [dict(n, state="accepted") for n in nodes]
    row = fold.inflight_rows([job], {"j": {"id": "j", "nodes": all_done}}, now_ts=NOW)[0]
    assert row["node_key"] is None and row["agent_token"] is None


def test_inflight_agent_token_is_none_when_it_does_not_parse_and_agent_id_stays_str():
    job = {"id": "j", "state": "executing", "createdAt": "2026-09-20T21:00:00Z"}
    detail = {"id": "j", "nodes": [{"key": "a", "state": "working",
                                    "seat": {"tokenId": "not-a-number", "agentId": "50972"}}]}
    row = fold.inflight_rows([job], {"j": detail}, now_ts=NOW)[0]
    assert row["agent_token"] is None
    assert row["agent_id"] == "50972"
    # A null seat, as the old completed jobs carry (details/7018907b….json).
    detail = {"id": "j", "nodes": [{"key": "a", "state": "working", "seat": None}]}
    row = fold.inflight_rows([job], {"j": detail}, now_ts=NOW)[0]
    assert row["agent_token"] is None and row["agent_id"] is None
    assert row["node_key"] == "a"


def test_inflight_rows_skip_malformed_jobs_without_raising():
    malformed = swarm_capture_v2("jobs_malformed")["jobs"]
    assert any(not isinstance(j, dict) for j in malformed)
    # The one real job is completed, so the in-flight set is a real empty.
    assert fold.inflight_rows(malformed, None, now_ts=NOW) == []
    executing = dict(malformed[0], state="executing")
    rows = fold.inflight_rows([executing, *malformed[1:]], None, now_ts=NOW)
    assert [r["job_id"] for r in rows] == [executing["id"]]


def test_every_rows_fold_returns_an_empty_list_for_none_and_for_empty():
    """The manager tells ``None`` from ``[]`` by whether the read happened."""
    assert fold.inflight_rows(None, None, now_ts=NOW) == []
    assert fold.inflight_rows([], None, now_ts=NOW) == []
    assert fold.skill_rows(None) == [] and fold.skill_rows([]) == []
    assert fold.launch_rows(None) == [] and fold.launch_rows([]) == []
    assert fold.site_rows(None) == [] and fold.site_rows([]) == []
    assert fold.seat_rows(None, None) == [] and fold.seat_rows({}, {}) == []


# ---------------------------------------------------------------------------
# skill_rows / launch_rows / site_rows
# ---------------------------------------------------------------------------


def test_skill_rows_cover_the_catalogue_sorted_by_role_then_id(skills):
    rows = fold.skill_rows(skills)
    assert len(rows) == 30  # skills.json carries 30 entries
    assert [(r["role"], r["skill_id"]) for r in rows] == sorted(
        (r["role"], r["skill_id"]) for r in rows
    )
    # skills.json[0]: adversarial-review v2, role review, kind code,
    # judge verifier-rerun, tier 1, checks "foundry", requires [].
    row = next(r for r in rows if r["skill_id"] == "adversarial-review")
    assert row == {"skill_id": "adversarial-review", "version": 2, "role": "review",
                   "kind": "code", "tier": 1, "judge": "verifier-rerun",
                   "checks": "foundry", "requires": []}
    for r in rows:
        assert isinstance(r["requires"], list)
        assert all(isinstance(x, str) for x in r["requires"])
        assert r["checks"] is None or isinstance(r["checks"], str)


def test_skill_rows_on_the_null_tier_shape_leave_tier_and_judge_none():
    rows = fold.skill_rows(swarm_capture_v2("skills_null_tier")["skills"])
    assert len(rows) == 7
    assert all(r["tier"] is None and r["judge"] is None for r in rows)
    assert rows[0]["skill_id"]  # something real came through


def test_skill_rows_coerce_requires_and_checks_and_skip_garbage():
    rows = fold.skill_rows([
        {"id": "b", "role": "x", "requires": "not-a-list", "checks": 7},
        {"id": "a", "role": "x", "requires": ["ok", 3, None], "checks": None},
        "garbage", None,
    ])
    assert [r["skill_id"] for r in rows] == ["a", "b"]
    assert rows[1]["requires"] == [] and rows[1]["checks"] is None
    assert rows[0]["requires"] == ["ok"]


def test_launch_rows_newest_first_with_five_field_artifacts(launches):
    rows = fold.launch_rows(launches)
    assert len(rows) == 30  # launches.json count 30
    stamps = [r["created_ts"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)
    # launches.json[0]: launchNumber 62, kind evm_project, status live,
    # chainId 11155111, artifactCount 3, three artifacts.
    row = next(r for r in rows if r["launch_number"] == 62)
    assert row["kind"] == "evm_project" and row["status"] == "live"
    assert row["chain_id"] == 11155111
    assert row["repo_url"] == (
        "https://github.com/Identity-md/launch-62-build-independently-review-streaming"
    )
    assert row["commit"] == "192743350ad9bd9b1b0be3f2522147fe142672f0"
    assert row["parked_reason"] is None
    assert row["artifact_count"] == 3 and len(row["artifacts"]) == 3
    assert row["artifacts"][0] == {
        "role": "distributor", "name": "MerkleDistributor",
        "address": "0x81472e20aa40be45be87c3d12a74fddb35892b90",
        "tx_hash": "0x1fc477e5910ad5a286cd1d0152d47abcd3488067afaeddb4c6967f6287b37d04",
        "block_number": 11746995,
    }
    for r in rows:
        for art in r["artifacts"]:
            assert tuple(art) == ("role", "name", "address", "tx_hash", "block_number")
    assert sum(len(r["artifacts"]) for r in rows) == 55  # plan R5: 55 addresses


def test_launch_rows_fall_back_to_len_artifacts_and_skip_garbage_artifacts():
    rows = fold.launch_rows([
        {"launchNumber": 1, "artifacts": [{"role": "token"}, "junk", None]},
        {"launchNumber": 2, "artifactCount": 9, "artifacts": []},
        "junk",
    ])
    by_n = {r["launch_number"]: r for r in rows}
    assert by_n[1]["artifact_count"] == 1 and len(by_n[1]["artifacts"]) == 1
    assert by_n[2]["artifact_count"] == 9
    assert by_n[1]["artifacts"][0]["address"] is None


def test_site_rows_newest_updated_first(sites):
    rows = fold.site_rows(sites)
    assert len(rows) == 6  # sites.json count 6
    stamps = [s["updatedAt"] for s in sites]
    newest = max(sites, key=lambda s: s["updatedAt"])
    assert rows[0]["label"] == newest["label"]
    # sites.json[0]: label roll, ensName roll.site.identitymd.eth, bytes 2445908,
    # status named, blockNumber 26021387, failure null, supersededBy null.
    roll = next(r for r in rows if r["label"] == "roll")
    assert roll == {
        "label": "roll", "ens_name": "roll.site.identitymd.eth",
        "cid": "bafybeig4xxfxbhkxsmautrga6yjuqcv76bctmkhj3f7ad2mqfeambtlp6q",
        "bytes": 2445908, "status": "named",
        "tx_hash": "0x9d46eec7e6f2cad4ef760022b3edda30cbd85761530934fc3926c40902a25986",
        "block_number": 26021387, "job_id": "115a2caa-323b-411a-bc39-e69977e85e34",
        "superseded_by": None, "failure": None,
    }
    assert len(stamps) == len(rows)


# ---------------------------------------------------------------------------
# throughput_facts (§1.3)
# ---------------------------------------------------------------------------


def test_throughput_facts_is_none_when_jobs_were_never_read():
    assert fold.throughput_facts(None, {}, now_ts=NOW) is None


def test_throughput_facts_on_an_empty_read_is_a_dict_of_honest_empties():
    out = fold.throughput_facts([], {}, now_ts=NOW)
    assert out == {
        "window_start_ts": None, "window_end_ts": None, "window_n": 0,
        "states": [],
        "dur_median_s": None, "dur_p90_s": None, "dur_max_s": None,
        "dur_n": 0,
        "cancel_reasons": [],
        "completed_24h": None, "seen_since_ts": None,
    }


def test_throughput_facts_on_the_capture(jobs):
    out = fold.throughput_facts(jobs, {}, now_ts=NOW)
    # jobs.json: 100 jobs, createdAt min 21:39:46.236Z / max 21:53:17.337Z,
    # 98 completed + 2 executing, no cancelled job.
    assert out["window_n"] == 100
    assert out["window_start_ts"] == _iso("2026-09-20T21:39:46.236Z")
    assert out["window_end_ts"] == _iso("2026-09-20T21:53:17.337Z")
    assert out["states"] == [{"state": "completed", "count": 98},
                             {"state": "executing", "count": 2}]
    assert out["cancel_reasons"] == []
    # Completed jobs carrying ``delivery.deliveredAt`` are the sample; the
    # count is pinned to the corpus itself (counted off jobs.json, not off
    # the fold), and it is enough for the three percentiles.
    delivered = [
        j for j in jobs
        if j.get("state") == "completed" and isinstance(j.get("delivery"), dict)
        and j["delivery"].get("deliveredAt")
    ]
    assert len(delivered) == 10, len(delivered)
    assert out["dur_n"] == 10
    assert out["dur_median_s"] is not None
    assert out["dur_median_s"] <= out["dur_p90_s"] <= out["dur_max_s"]
    assert out["dur_max_s"] > 0
    # No seen history handed in: accumulating, never 0.
    assert out["completed_24h"] is None and out["seen_since_ts"] is None


def test_throughput_facts_keeps_an_unknown_state_in_the_rollup():
    unknown = swarm_capture_v2("jobs_unknown_state")["jobs"]
    out = fold.throughput_facts(unknown, {}, now_ts=NOW)
    assert out["states"] == [{"state": "quarantined", "count": 2}]


def test_throughput_facts_counts_cancel_reasons_verbatim():
    jobs = [
        {"id": "1", "state": "cancelled", "blockedReason": "budget", "createdAt": "2026-09-20T21:00:00Z"},
        {"id": "2", "state": "cancelled", "blockedReason": "budget", "createdAt": "2026-09-20T21:01:00Z"},
        {"id": "3", "state": "cancelled", "blockedReason": "[red]timeout[/red]",
         "createdAt": "2026-09-20T21:02:00Z"},
        {"id": "4", "state": "cancelled", "blockedReason": None, "createdAt": "2026-09-20T21:03:00Z"},
        {"id": "5", "state": "blocked", "blockedReason": "budget", "createdAt": "2026-09-20T21:04:00Z"},
    ]
    out = fold.throughput_facts(jobs, {}, now_ts=NOW)
    assert out["cancel_reasons"] == [{"reason": "budget", "count": 2},
                                     {"reason": "[red]timeout[/red]", "count": 1}]
    assert out["states"] == [{"state": "cancelled", "count": 4}, {"state": "blocked", "count": 1}]
    assert out["dur_median_s"] is None  # nothing completed


def test_throughput_facts_skips_malformed_jobs_without_raising():
    malformed = swarm_capture_v2("jobs_malformed")["jobs"]
    out = fold.throughput_facts(malformed, {}, now_ts=NOW)
    # Two mappings were returned (one real job, one with state 7); the list
    # in the middle is not a job.
    assert out["window_n"] == 2
    assert out["states"] == [{"state": "completed", "count": 1}]


def test_throughput_facts_completed_24h_comes_from_the_seen_map():
    since = NOW - 2 * _DAY
    seen = {
        "old": {"created_ts": since, "updated_ts": since + 60, "state": "completed",
                "template": None, "nodes": []},
        "new": {"created_ts": NOW - 3600, "updated_ts": NOW - 1800, "state": "completed",
                "template": None, "nodes": []},
    }
    out = fold.throughput_facts([], seen, now_ts=NOW)
    assert out["completed_24h"] == 1 and out["seen_since_ts"] == since


# ---------------------------------------------------------------------------
# the seen slot: seen_entry / merge_seen / seen_since_ts
# ---------------------------------------------------------------------------

_SEEN_NODE_FIELDS = ("key", "seat_token", "seat_agent", "role", "state", "verdict_status",
                     "rejection_code", "revisions", "at_ts")


def test_seen_entry_shape_from_a_detail_and_without_one(jobs, details):
    job = next(j for j in jobs if j["id"] == EXECUTING_WITH_DETAIL)
    entry = fold.seen_entry(job, details[EXECUTING_WITH_DETAIL])
    assert tuple(entry) == ("created_ts", "updated_ts", "state", "template", "nodes")
    assert entry["state"] == "executing" and entry["template"] == "skill:oracle-assess"
    # jobs.json (the list) says updatedAt 22:15:58.655Z for this job; the
    # detail file says 21:41:27.617Z. The slot stores the list's stamp.
    assert entry["created_ts"] == _iso("2026-09-20T21:41:27.617Z")
    assert entry["updated_ts"] == _iso("2026-09-20T22:15:58.655Z")
    # details/f046299c….json nodes[0]: seat 463/50972, implement, working,
    # verdict.status accepted, rejectionCode null, revisions 0,
    # updatedAt 2026-09-20T22:15:58.655Z.
    assert entry["nodes"] == [{
        "key": "oracle_assess",
        "seat_token": 463, "seat_agent": "50972", "role": "implement",
        "state": "working", "verdict_status": "accepted", "rejection_code": None,
        "revisions": 0, "at_ts": _iso("2026-09-20T22:15:58.655Z"),
    }]
    assert tuple(entry["nodes"][0]) == _SEEN_NODE_FIELDS
    no_detail = fold.seen_entry(job, None)
    assert no_detail["nodes"] == [] and no_detail["state"] == "executing"


def test_seen_entry_keeps_a_node_whose_seat_is_null_with_none_seat_fields(details):
    entry = fold.seen_entry({"id": OLD_COMPLETED, "state": "completed"}, details[OLD_COMPLETED])
    assert len(entry["nodes"]) == 1
    assert entry["nodes"][0]["seat_token"] is None and entry["nodes"][0]["seat_agent"] is None
    assert entry["nodes"][0]["verdict_status"] == "accepted"


def _job(job_id, created, updated, state="completed"):
    return {"id": job_id, "state": state, "template": "t",
            "createdAt": f"2026-09-20T{created}Z", "updatedAt": f"2026-09-20T{updated}Z"}


def test_merge_seen_returns_a_new_dict_keyed_by_job_id(jobs, details):
    seen: dict = {}
    out = fold.merge_seen(seen, jobs, details, now_ts=NOW, cap=5000, max_age_s=_TWO_DAYS)
    assert out is not seen and seen == {}
    assert set(out) == {j["id"] for j in jobs}
    assert len(out[EXECUTING_WITH_DETAIL]["nodes"]) == 1
    assert out[EXECUTING_NO_DETAIL]["nodes"] == []
    again = fold.merge_seen(out, jobs, details, now_ts=NOW, cap=5000, max_age_s=_TWO_DAYS)
    assert again is not out and again == out


def test_merge_seen_newer_updated_ts_wins_older_does_not_overwrite():
    older = _job("j", "21:00:00", "21:10:00", state="executing")
    newer = _job("j", "21:00:00", "21:20:00", state="completed")
    first = fold.merge_seen({}, [older], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    second = fold.merge_seen(first, [newer], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert second["j"]["state"] == "completed"
    assert second["j"]["updated_ts"] == _iso("2026-09-20T21:20:00Z")
    stale = fold.merge_seen(second, [older], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert stale["j"]["state"] == "completed"  # the older read did not win


def test_merge_seen_keeps_node_summaries_when_a_later_read_has_no_detail():
    job = _job("j", "21:00:00", "21:10:00", state="executing")
    detail = {"id": "j", "nodes": [{"key": "a", "role": "implement", "state": "working",
                                    "seat": {"tokenId": "5", "agentId": "x"}}]}
    with_nodes = fold.merge_seen({}, [job], {"j": detail}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert len(with_nodes["j"]["nodes"]) == 1
    same_stamp = fold.merge_seen(with_nodes, [job], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert len(same_stamp["j"]["nodes"]) == 1


def test_merge_seen_drops_entries_older_than_max_age():
    fresh = _job("fresh", "23:00:00", "23:30:00")
    old = {"id": "old", "state": "completed", "template": "t",
           "createdAt": "2026-09-01T00:00:00Z", "updatedAt": "2026-09-01T01:00:00Z"}
    out = fold.merge_seen({}, [fresh, old], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert set(out) == {"fresh"}
    # An existing entry ages out too.
    seen = {"stale": {"created_ts": NOW - 10 * _DAY, "updated_ts": NOW - 9 * _DAY,
                      "state": "completed", "template": "t", "nodes": []}}
    out = fold.merge_seen(seen, [fresh], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert set(out) == {"fresh"}


def test_merge_seen_keeps_the_newest_cap_entries_by_updated_ts():
    jobs = [_job(f"j{i}", "21:00:00", f"21:0{i}:00") for i in range(6)]
    out = fold.merge_seen({}, jobs, {}, now_ts=NOW, cap=3, max_age_s=_TWO_DAYS)
    assert set(out) == {"j3", "j4", "j5"}


def test_merge_seen_treats_a_non_mapping_seen_and_garbage_entries_as_absent():
    job = _job("j", "21:00:00", "21:10:00")
    for seen in (None, [], "x", 3):
        out = fold.merge_seen(seen, [job], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
        assert set(out) == {"j"}
    poisoned = {"bad": "not a mapping", "worse": None, "nostamps": {"state": "completed"}}
    out = fold.merge_seen(poisoned, [job], {}, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    assert set(out) == {"j"}


def test_merge_seen_skips_malformed_jobs():
    malformed = swarm_capture_v2("jobs_malformed")["jobs"]
    out = fold.merge_seen({}, malformed, None, now_ts=NOW, cap=10, max_age_s=_TWO_DAYS)
    # The list in the middle is not a job; {"id": "x", "state": 7} carries no
    # timestamp at all, so it can neither be aged nor ranked and is not stored.
    assert set(out) == {malformed[0]["id"]}


def test_seen_since_ts_is_the_oldest_created_ts():
    seen = {"a": {"created_ts": 30.0}, "b": {"created_ts": 10.0}, "c": {"created_ts": None}}
    assert fold.seen_since_ts(seen) == 10.0
    assert fold.seen_since_ts({}) is None
    assert fold.seen_since_ts(None) is None


# ---------------------------------------------------------------------------
# AGENT body roster fold (A1): seat_rows. The window-based seat choice, node
# rows and feedback rows retired in the AGENT-seats WP5 (docs/surf_agent_seats_plan.md §3).
# ---------------------------------------------------------------------------

# Read off the 28 detail files by hand: every distinct nodes[].seat.tokenId
# that parses to an int. 7018907b, 4ba29896 and 9c6543f5 carry seat null.
_CORPUS_TOKENS = {0, 1, 2, 12, 47, 354, 463, 579, 617, 1120, 1242, 1299, 1548,
                  1599, 1606, 1731}


def test_seat_rows_one_per_parseable_seat_sorted_by_nodes(details):
    rows = fold.seat_rows(details, {})
    assert {r["token_id"] for r in rows} == _CORPUS_TOKENS
    assert len(rows) == 16
    assert all(isinstance(r["token_id"], int) for r in rows)
    counts = [r["nodes"] for r in rows]
    assert counts == sorted(counts, reverse=True)
    # Seat 0 is on eight nodes in eight jobs (1c47e615, 416e1862, 4ac228e8,
    # 79513878, 92b87fce, 9dbfeb65, e645958e, ef0b2b66), the most active.
    assert rows[0]["token_id"] == 0 and rows[0]["nodes"] == 8 and rows[0]["jobs"] == 8


def test_seat_rows_the_seat_in_several_jobs_from_the_manifest(details, manifest):
    crit = manifest["criteria"]["seat_in_several_jobs"]
    assert crit["met"] is True
    rows = {r["token_id"]: r for r in fold.seat_rows(details, {})}
    # Seat 1548 (agentId "50971") sits on 7 nodes across 6 of the criterion's
    # jobs: 1a5b1255, 71cd53fa, 9dbfeb65 (two nodes), ad7bebb8, b6bc671c,
    # f278d3f2. Every one of its 17 review entries carries value 1.
    row = rows[1548]
    assert row["jobs"] >= 2
    assert row["jobs"] == 6 and row["nodes"] == 7
    assert row["agent_id"] == "50971"
    assert row["roles"] == sorted(row["roles"]) and "implement" in row["roles"]
    assert row["accepted"] == 7 and row["rejected"] == 0
    assert row["revisions"] == 0
    assert row["scored"] == 17 and row["mean_score"] == 1.0
    assert row["working_now"] is False
    assert row["last_active_ts"] is not None
    # Seat 463 is the one node in state working (details/f046299c….json).
    assert rows[463]["working_now"] is True
    assert rows[463]["scored"] == 3  # agentId 50972: 1a5b1255, 4859f19e, 71cd53fa


def test_seat_rows_skip_nodes_whose_seat_is_absent_or_unparseable():
    details = {
        "j1": {"id": "j1", "nodes": [
            {"key": "a", "role": "implement", "state": "accepted",
             "seat": {"tokenId": "7", "agentId": "x"}},
            {"key": "b", "role": "review", "state": "accepted", "seat": None},
            {"key": "c", "role": "review", "state": "accepted",
             "seat": {"tokenId": "seven", "agentId": "y"}},
            {"key": "d", "role": "review", "state": "accepted", "seat": {"agentId": "z"}},
            "garbage",
        ]},
        "j2": None,
        "j3": "garbage",
    }
    rows = fold.seat_rows(details, {})
    assert [r["token_id"] for r in rows] == [7]
    assert rows[0]["nodes"] == 1


def test_seat_rows_fold_in_seen_nodes_for_jobs_no_detail_covers(details):
    since = NOW - 3600
    seen = {
        # a job outside the detail sweep, seat 1548 on it
        "seen-only": {"created_ts": since, "updated_ts": since + 60, "state": "completed",
                      "template": "t", "nodes": [
                          {"seat_token": 1548, "seat_agent": "50971", "role": "integrate",
                           "state": "accepted", "verdict_status": "accepted",
                           "rejection_code": None, "revisions": 3, "at_ts": since + 60}]},
        # a job the detail sweep covers: its seen nodes must not double count
        "ad7bebb8-fd1a-4268-b831-1c253a85ae4c": {
            "created_ts": since, "updated_ts": since, "state": "completed", "template": "t",
            "nodes": [{"seat_token": 1548, "seat_agent": "50971", "role": "implement",
                       "state": "accepted", "verdict_status": "accepted",
                       "rejection_code": None, "revisions": 0, "at_ts": since}]},
        # a brand-new seat known only from the seen slot
        "seen-new": {"created_ts": since, "updated_ts": since, "state": "completed",
                     "template": "t", "nodes": [
                         {"seat_token": 4242, "seat_agent": "77", "role": "review",
                          "state": "working", "verdict_status": None,
                          "rejection_code": None, "revisions": None, "at_ts": None}]},
    }
    rows = {r["token_id"]: r for r in fold.seat_rows(details, seen)}
    assert rows[1548]["jobs"] == 7 and rows[1548]["nodes"] == 8
    assert rows[1548]["revisions"] == 3
    assert "integrate" in rows[1548]["roles"]
    assert rows[4242]["nodes"] == 1 and rows[4242]["working_now"] is True
    assert rows[4242]["agent_id"] == "77" and rows[4242]["last_active_ts"] is None
    assert len(rows) == 17


# ---------------------------------------------------------------------------
# the pre-v2 folds that survived WP7 (health_facts, network_of), ported off
# the retired 2026-09-16 captures onto the corpus
# ---------------------------------------------------------------------------


def test_health_facts_reads_the_counters_and_never_invents_a_zero(health):
    facts = fold.health_facts(health)
    # health.json: connectedDaemons 28, activeEnrollments 36, workingNow 1,
    # acceptedLastDay 1189, the three *Up flags true.
    assert facts["agents_online"] == 28 == health["connectedDaemons"]
    assert facts["agents_enrolled"] == 36 == health["activeEnrollments"]
    assert facts["working_now"] == 1
    assert facts["accepted_today"] == 1189
    assert facts["services_up"] == {"verifier": True, "publisher": True, "deployer": True}
    assert facts["network"] == "MAINNET"          # identity.chainId 1
    blank = fold.health_facts(None)
    assert blank["agents_online"] is None and blank["accepted_today"] is None
    assert blank["services_up"] is None and blank["network"] is None


def test_health_facts_with_partial_payload_returns_none_for_missing_services():
    """Unread service keys are None, never False. Only explicit false is False."""
    partial = {"connectedDaemons": 2, "verifierUp": True, "deployerUp": False}
    facts = fold.health_facts(partial)
    assert facts["services_up"] == {"verifier": True, "publisher": None, "deployer": False}
    assert facts["agents_online"] == 2 and facts["working_now"] is None


def test_network_of_is_an_allowlist():
    assert fold.network_of(11155111) == "SEPOLIA"
    assert fold.network_of(1) == "MAINNET"
    assert fold.network_of(999) is None
    assert fold.network_of(None) is None
    assert fold.network_of("mainnet") is None
