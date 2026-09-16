from tests.surf_swarm_fixtures import swarm_capture

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
