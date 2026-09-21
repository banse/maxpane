import json

import pytest

from tests.surf_swarm_fixtures import (SWARM_FIXTURES_SEATS, SWARM_FIXTURES_V2, swarm_capture_v2,
                                       swarm_details_v2, swarm_manifest_v2, swarm_seat_capture)

# --- the 2026-09-21 v2 corpus from api.imd.fun (plan A3) ---

_LIST_CAPTURES = ("health", "version", "jobs", "skills", "launches", "sites")
_HAND_SHAPES = ("jobs_malformed", "jobs_unknown_state", "skills_null_tier")
_SECRET_KEYS = {"privateKey", "secret", "apiKey", "token"}


def _every_v2_json():
    for path in sorted(SWARM_FIXTURES_V2.rglob("*.json")):
        with open(path, encoding="utf-8") as fh:
            yield path, json.load(fh)


def test_v2_health_carries_every_field_the_hero_reads():
    health = swarm_capture_v2("health")
    for key in ("connectedDaemons", "activeEnrollments", "workingNow", "acceptedLastDay",
                "identity", "verifierUp", "publisherUp", "deployerUp"):
        assert key in health, key
    assert any(k.startswith("pending") for k in health), "no pending* counter to sum"
    assert "deployBreaker" in health  # the value may be null: null is "not tripped"
    # `swarm_network` reads `identity.chainId`, not the identity envelope.
    assert isinstance(health["identity"], dict) and "chainId" in health["identity"]


def test_v2_jobs_carry_the_list_fields_the_fold_reads():
    jobs = swarm_capture_v2("jobs")["jobs"]
    assert len(jobs) >= 25
    for job in jobs:
        assert {"id", "state", "template", "objective", "createdAt", "updatedAt"} <= set(job), job["id"]


def test_v2_skills_carry_the_capability_fields():
    skills = swarm_capture_v2("skills")["skills"]
    assert skills
    for skill in skills:
        assert {"id", "version", "role", "kind", "tier", "judge", "requires", "checks"} <= set(skill), skill


def test_v2_launches_carry_the_launch_fields_and_typed_artifacts():
    launches = swarm_capture_v2("launches")["launches"]
    assert launches
    for launch in launches:
        assert {"launchNumber", "kind", "status", "chainId", "sourceRepoUrl", "artifacts",
                "sourceCommit", "parkedReason", "createdAt", "updatedAt"} <= set(launch), launch
        for artifact in launch["artifacts"]:
            assert {"role", "name", "address", "txHash", "blockNumber"} <= set(artifact), artifact
    assert any(launch["artifacts"] for launch in launches), "no artifact address to link"


def test_v2_sites_carry_the_site_fields():
    sites = swarm_capture_v2("sites")["sites"]
    assert sites
    for site in sites:
        assert {"label", "ensName", "cid", "bytes", "status", "txHash", "blockNumber", "jobId",
                "supersededBy", "failure"} <= set(site), site


def test_v2_version_commit_is_what_the_manifest_records():
    version = swarm_capture_v2("version")
    manifest = swarm_manifest_v2()
    assert isinstance(version.get("commit"), str) and len(version["commit"]) == 40
    assert manifest["version"] == version["commit"]
    assert manifest["host"] == "https://api.imd.fun"


def test_r2_attribution_lives_on_the_detail_route_only():
    for job in swarm_capture_v2("jobs")["jobs"]:
        assert not any(k.startswith(("agent", "seat")) for k in job), sorted(job)
    token_ids = [n["seat"]["tokenId"] for job in swarm_details_v2().values()
                 for n in job["nodes"] if isinstance(n.get("seat"), dict)]
    assert any(token_ids), "no detail node carries seat.tokenId"


def test_v2_details_corpus_is_at_least_twenty_five_well_formed_jobs():
    details = swarm_details_v2()
    assert len(details) >= 25
    for stem, job in details.items():
        assert job["id"] == stem
        assert {"reviews", "nodes"} <= set(job), stem
        assert job["nodes"], stem
        for node in job["nodes"]:
            assert {"role", "state", "seat"} <= set(node), (stem, node.get("key"))


#: Every node field `swarm_inflight_rows`, `swarm_seat_rows` and
#: `swarm_seat_node_rows` read (plan §1.2, A1), and every verdict sub-field
#: `swarm_seat_summary`'s rejection and failed-check counts read. A key may be
#: null; it may not be absent -- absence is what a silent API change looks
#: like, and WP3's folds would render it as "not read" rather than fail.
_NODE_FIELDS = frozenset({
    "key", "role", "state", "seat", "attempt", "revisions", "failureReason",
    "dispatchNote", "dispatchNoteAt", "updatedAt", "verdict",
})
_VERDICT_FIELDS = frozenset({
    "status", "profile", "evaluation", "rejectionCode", "detail",
    "failedChecks", "verifierVersion", "at",
})
#: Every review field `swarm_seat_feedback_rows` reads.
_REVIEW_FIELDS = frozenset({"status", "chainId", "txHash", "blockNumber", "sentAt", "entries"})
_ENTRY_FIELDS = frozenset({"agentId", "value", "nodeKey"})


def test_every_detail_node_and_review_carries_every_field_the_agent_body_reads():
    """WP1 review, Important: the corpus must prove the *detail* shape too.

    Counted so the walk cannot pass by looping zero times; the counts are
    lower bounds, not pins, because a recapture legitimately changes them.
    """
    nodes = verdicts = reviews = entries = 0
    for stem, job in swarm_details_v2().items():
        for node in job["nodes"]:
            missing = _NODE_FIELDS - set(node)
            assert not missing, (stem, node.get("key"), sorted(missing))
            nodes += 1
            verdict = node["verdict"]
            if verdict is not None:
                assert isinstance(verdict, dict), (stem, node.get("key"))
                missing = _VERDICT_FIELDS - set(verdict)
                assert not missing, (stem, node.get("key"), sorted(missing))
                verdicts += 1
        for review in job["reviews"]:
            missing = _REVIEW_FIELDS - set(review)
            assert not missing, (stem, sorted(missing))
            reviews += 1
            for entry in review["entries"]:
                missing = _ENTRY_FIELDS - set(entry)
                assert not missing, (stem, sorted(missing))
                entries += 1
    assert nodes >= 25 and verdicts >= 1 and reviews >= 1 and entries >= 1, (
        nodes, verdicts, reviews, entries
    )


def test_swarm_details_v2_returns_one_entry_per_file():
    files = sorted(p.stem for p in (SWARM_FIXTURES_V2 / "details").glob("*.json"))
    assert list(swarm_details_v2()) == files and len(files) == len(set(files))


def test_manifest_details_bind_to_the_files_on_disk():
    manifest = swarm_manifest_v2()
    on_disk = {p.stem: p.stat().st_size for p in (SWARM_FIXTURES_V2 / "details").glob("*.json")}
    assert set(manifest["details"]) == set(on_disk)
    for job_id, entry in manifest["details"].items():
        assert entry["bytes"] == on_disk[job_id], job_id
        assert entry["endpoint"] == f"/jobs/{job_id}"
    for name in _LIST_CAPTURES:
        assert manifest["files"][name]["bytes"] == (SWARM_FIXTURES_V2 / f"{name}.json").stat().st_size
        assert manifest["files"][name]["endpoint"] == f"/{name}"


def _recomputed_criteria(details):
    """Amendment A1's four criteria, derived here from the detail files, not the manifest."""
    working, failed, reviewed = [], [], []
    seat_jobs: dict[str, set[str]] = {}
    for job_id, job in details.items():
        nodes = job["nodes"]
        if any(n["state"] == "working" for n in nodes):
            working.append(job_id)
        if any(n.get("failureReason") is not None for n in nodes):
            failed.append(job_id)
        if any(r.get("entries") for r in job["reviews"]):
            reviewed.append(job_id)
        for n in nodes:
            seat = n.get("seat")
            if isinstance(seat, dict) and seat.get("tokenId") is not None:
                seat_jobs.setdefault(str(seat["tokenId"]), set()).add(job_id)
    shared: set[str] = set()
    for jobs in seat_jobs.values():
        if len(jobs) >= 2:
            shared |= jobs
    return {
        "node_working": {"met": bool(working), "job_ids": sorted(working)},
        "failure_reason": {"met": bool(failed), "job_ids": sorted(failed)},
        "review_entries": {"met": bool(reviewed), "job_ids": sorted(reviewed)},
        "seat_in_several_jobs": {"met": bool(shared), "job_ids": sorted(shared)},
    }


def test_manifest_criteria_equal_a_recomputation_from_the_details():
    assert swarm_manifest_v2()["criteria"] == _recomputed_criteria(swarm_details_v2())


@pytest.mark.parametrize("criterion", ("node_working", "failure_reason", "review_entries",
                                       "seat_in_several_jobs"))
def test_every_a1_criterion_is_met_by_the_corpus(criterion):
    # All four were met live on 2026-09-21. A recapture that unmeets one reddens here; the
    # brief then wants this case under xfail(strict=True) naming the criterion, not deleted.
    block = swarm_manifest_v2()["criteria"][criterion]
    assert block["met"] is True and block["job_ids"], criterion


#: The three ``/jobs/{id}`` captures of the retired 2026-09-16 v1 manifest
#: (``job_blocked``, ``job_completed``, ``job_executing``), hand-typed from
#: it before WP7 deleted the file, so the v2 manifest's record of having
#: probed them stays checkable against something other than itself.
_V1_MANIFEST_DETAIL_IDS = frozenset({
    "9c6543f5-e642-4df8-9d5b-d7e7ab947f96",   # job_blocked
    "7018907b-7466-4326-a602-e322913db496",   # job_completed
    "4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6",   # job_executing
})


def test_the_old_manifest_detail_ids_were_probed_and_recorded():
    manifest = swarm_manifest_v2()
    old_ids = set(_V1_MANIFEST_DETAIL_IDS)
    assert set(manifest["details_search"]["old_manifest_ids_probed"]) == old_ids
    present = set(manifest["details_search"]["old_manifest_ids_present"])
    assert present <= old_ids and present == old_ids & set(manifest["details"])
    assert set(manifest["probed_absent"]) == old_ids - present


def test_hand_shape_jobs_malformed_has_a_non_dict_and_a_non_str_state():
    jobs = swarm_capture_v2("jobs_malformed")["jobs"]
    assert any(not isinstance(j, dict) for j in jobs)
    assert any(isinstance(j, dict) and not isinstance(j.get("state"), str) for j in jobs)
    assert any(isinstance(j, dict) and isinstance(j.get("state"), str) for j in jobs)


def test_hand_shape_jobs_unknown_state_uses_a_state_no_capture_has_seen():
    unknown = {j["state"] for j in swarm_capture_v2("jobs_unknown_state")["jobs"]}
    seen = {j["state"] for j in swarm_capture_v2("jobs")["jobs"]}
    seen |= {job["state"] for job in swarm_details_v2().values()}
    seen |= {n["state"] for job in swarm_details_v2().values() for n in job["nodes"]}
    assert unknown and not unknown & seen, unknown & seen


def test_hand_shape_skills_null_tier_has_only_null_judge_and_tier():
    skills = swarm_capture_v2("skills_null_tier")["skills"]
    assert skills
    assert all(s["judge"] is None and s["tier"] is None for s in skills)


def test_manifest_names_every_hand_shape_with_a_sentence():
    hand_made = swarm_manifest_v2()["hand_made"]
    assert set(hand_made) == set(_HAND_SHAPES)
    for name in _HAND_SHAPES:
        assert (SWARM_FIXTURES_V2 / f"{name}.json").exists()
        assert hand_made[name].startswith("Hand-made")
    assert set(_HAND_SHAPES).isdisjoint(swarm_manifest_v2()["files"])


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}/{k}", k
            yield from _walk_keys(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def test_a_keyless_public_api_serves_no_secret_shaped_key_anywhere():
    offenders = [(path.name, where) for path, body in _every_v2_json()
                 for where, key in _walk_keys(body) if key in _SECRET_KEYS]
    assert offenders == []
    for name in ("health", "version"):
        assert _SECRET_KEYS.isdisjoint(swarm_capture_v2(name)), name


# --- the 2026-09-21 /seats/{tokenId} captures (docs/surf_agent_seats_plan.md WP0) ---

#: The eight committed captures, hand-typed from the plan's WP0 table so the
#: manifest cannot agree with itself by losing a file.
_SEAT_CAPTURES = (
    "seat_420", "seat_0", "seat_1649", "seat_516", "unknown_seat_404",
    "invalid_request_400", "jobs_window_100", "job_80c853bd_winner_only",
)


def test_seats_manifest_names_exactly_the_files_on_disk_and_each_parses():
    manifest = swarm_seat_capture("MANIFEST")
    on_disk = {p.stem for p in SWARM_FIXTURES_SEATS.glob("*.json")} - {"MANIFEST"}
    assert set(manifest["files"]) == on_disk == set(_SEAT_CAPTURES)
    assert manifest["host"] == "https://api.imd.fun"
    for name, entry in manifest["files"].items():
        body = swarm_seat_capture(name)
        assert isinstance(body, dict), name
        assert entry["bytes"] == (SWARM_FIXTURES_SEATS / f"{name}.json").stat().st_size, name
        assert entry["route"].startswith("/"), name
        assert entry["http_status"] in (200, 400, 404), name
        assert entry["selected_because"], name
        for field in ("captured_at", "version"):  # a value or an honest "not recorded"
            assert isinstance(entry[field], str) and entry[field], (name, field)


def test_seat_420_carries_the_defect_numbers():
    """The explorer's numbers for #420 (spec §1): 74 / 12 / 72, split 66 / 5 / 1."""
    seat = swarm_seat_capture("seat_420")
    assert seat["tokenId"] == "420"  # served as a decimal string
    assert (seat["attempts"], seat["accepted"], len(seat["reviews"])) == (74, 12, 72)
    assert len(seat["work"]) == seat["accepted"]
    statuses = [r["status"] for r in seat["reviews"]]
    assert (statuses.count("sent"), statuses.count("submitted"), statuses.count("queued")) == (66, 5, 1)
    assert len(statuses) == 72  # no fourth status hides in the total
    (queued,) = [r for r in seat["reviews"] if r["status"] == "queued"]
    assert queued["txHash"] is None and queued["chainId"] is None and queued["sentAt"] is None
    for review in seat["reviews"]:
        if review["status"] == "submitted":
            assert review["txHash"] and review["sentAt"] is None
        if review["status"] == "sent":
            assert review["txHash"] and review["sentAt"]


def test_every_seat_capture_carries_every_field_the_spec_names():
    top = {"tokenId", "agentId", "chainId", "collection", "adapter", "status", "ownership",
           "owner", "pairedAt", "online", "daemonVersion", "runtimes", "devices", "attempts",
           "accepted", "work", "reviews", "collaborators"}
    work = {"jobId", "objective", "jobState", "launch", "nodeKey", "role", "submissionHash",
            "acceptedAt"}
    review = {"jobId", "nodeKey", "role", "value", "policy", "verdict", "submissionHash",
              "status", "txHash", "chainId", "sentAt"}
    rows = 0
    for name in ("seat_420", "seat_0", "seat_1649", "seat_516"):
        seat = swarm_seat_capture(name)
        assert not top - set(seat), (name, sorted(top - set(seat)))
        assert seat["chainId"] == 1, name
        for row in seat["work"]:
            assert not work - set(row), (name, sorted(work - set(row)))
            rows += 1
        for row in seat["reviews"]:
            assert not review - set(row), (name, sorted(review - set(row)))
            assert row["status"] in ("sent", "submitted", "queued"), (name, row["status"])
            assert "blockNumber" not in row, name
            rows += 1
    assert rows > 0


def test_the_other_three_seats_pin_what_the_plan_selected_them_for():
    zero = swarm_seat_capture("seat_0")
    assert zero["online"] is False and zero["runtimes"] == [] and len(zero["reviews"]) == 202
    assert swarm_seat_capture("seat_1649")["runtimes"] == [{"id": "codex", "version": "codex-cli 0.149.0"}]
    small = swarm_seat_capture("seat_516")
    assert (small["attempts"], small["accepted"]) == (10, 4)
    assert [r["status"] for r in small["reviews"]].count("submitted") == 1


def test_the_error_bodies_are_the_two_documented_errors():
    assert swarm_seat_capture("unknown_seat_404")["error"] == "unknown_seat"
    assert swarm_seat_capture("invalid_request_400")["error"] == "invalid_request"
    files = swarm_seat_capture("MANIFEST")["files"]
    assert files["unknown_seat_404"]["http_status"] == 404
    assert files["invalid_request_400"]["http_status"] == 400


def test_jobs_window_is_a_page_of_one_hundred_not_every_job():
    window = swarm_seat_capture("jobs_window_100")
    assert window["count"] == 100 == len(window["jobs"])


def test_the_competitive_detail_lists_only_the_winner():
    job = swarm_seat_capture("job_80c853bd_winner_only")
    assert job["id"].startswith("80c853bd")
    assert len(job["nodes"]) == 1
    winner = job["nodes"][0]["seat"]["tokenId"]
    scored = {e["agentId"] for r in job["reviews"] for e in r["entries"]}
    assert len(scored) > 1, "the review scores more seats than the node list names"
    assert winner == "47"


def test_the_seat_captures_serve_no_secret_shaped_key():
    offenders = [(name, where) for name in _SEAT_CAPTURES
                 for where, key in _walk_keys(swarm_seat_capture(name)) if key in _SECRET_KEYS]
    assert offenders == []
