import json

import pytest

from tests.surf_swarm_fixtures import (SWARM_FIXTURES_V2, swarm_capture, swarm_capture_v2,
                                       swarm_details_v2, swarm_manifest_v2)

def test_every_capture_has_the_shape_the_fold_expects():
    health = swarm_capture("health")
    for key in ("connectedDaemons", "activeEnrollments", "workingNow",
                "acceptedLastDay", "identity", "verifierUp"):
        assert key in health, key

    jobs = swarm_capture("jobs")["jobs"]
    assert jobs and all({"id", "state", "template", "objective", "createdAt",
                         "updatedAt"} <= set(j) for j in jobs)

    executing = swarm_capture("job_executing")
    assert executing["state"] == "executing"
    assert executing["nodes"], "the executing capture has no subtasks to render"

    blocked = swarm_capture("job_blocked")
    assert blocked["state"] == "blocked" and blocked["blockedReason"]

    done = swarm_capture("job_completed")
    assert done["reviews"], "the completed capture carries no review to score"
    assert done["reviews"][0]["entries"][0]["value"] is not None

    assert swarm_capture("launches")["launches"]
    assert swarm_capture("sites")["sites"]


def test_a_seat_and_a_chain_id_are_present_to_fold():
    seats = [n.get("seat") for n in swarm_capture("job_executing")["nodes"]]
    assert any(s and s.get("tokenId") for s in seats)
    assert swarm_capture("job_completed")["reviews"][0]["chainId"] == 11155111


# --- the 2026-09-21 v2 corpus from api.imd.fun (plan A3; the two tests above retire in WP7) ---

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


def test_the_old_manifest_detail_ids_were_probed_and_recorded():
    manifest = swarm_manifest_v2()
    old = json.loads((SWARM_FIXTURES_V2.parent / "MANIFEST.json").read_text(encoding="utf-8"))
    old_ids = {e["endpoint"].removeprefix("/jobs/") for e in old.values()
               if e["endpoint"].startswith("/jobs/")}
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
