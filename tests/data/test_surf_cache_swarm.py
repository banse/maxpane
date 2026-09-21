from maxpane_dashboard.data.surf_cache import (
    SLOTS, SLOT_SWARM, SLOT_SWARM_JOBS_SEEN, SLOT_SWARM_SCORES, TIERS,
    TIER_FAILURE_BACKOFF_SECONDS, TIER_SWARM, TIER_SWARM_SCORES, TIER_TTL_SECONDS,
    SurfCache,
)


def test_the_swarm_has_two_tiers_with_their_own_ttls():
    assert TIER_SWARM in TIERS and TIER_SWARM_SCORES in TIERS
    assert TIER_TTL_SECONDS[TIER_SWARM] == 60.0
    assert TIER_TTL_SECONDS[TIER_SWARM_SCORES] == 1800.0
    # The live tier backs off to LONGER than its healthy cadence: a failing
    # third-party host must be polled less often, not at the same rate.
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_SWARM] == 120.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_SWARM] > TIER_TTL_SECONDS[TIER_SWARM]
    # The sweep tier retries SOONER than its half-hour cadence, so a transient
    # failure does not leave the scores stale for thirty minutes.
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_SWARM_SCORES] == 300.0
    assert (
        TIER_FAILURE_BACKOFF_SECONDS[TIER_SWARM_SCORES]
        < TIER_TTL_SECONDS[TIER_SWARM_SCORES]
    )


def test_every_tier_has_both_a_ttl_and_a_backoff():
    assert set(TIER_TTL_SECONDS) == set(TIERS)
    assert set(TIER_FAILURE_BACKOFF_SECONDS) == set(TIERS)


def test_both_swarm_slots_are_registered_so_they_restore():
    assert SLOT_SWARM in SLOTS and SLOT_SWARM_SCORES in SLOTS


def test_a_failed_swarm_tier_keeps_its_slot_and_only_spaces_the_retry(tmp_path):
    from tests.data.test_surf_cache import FakeClock

    cache = SurfCache(path=tmp_path / "surf.json", clock=FakeClock())
    cache.store_last_good(SLOT_SWARM, {"agents_online": 2}, ts=1000.0)
    cache.mark_failed(TIER_SWARM, now=1000.0)
    assert cache.get_last_good(SLOT_SWARM).payload == {"agents_online": 2}
    assert not cache.is_due(TIER_SWARM, now=1000.0 + 60.0)
    assert cache.is_due(TIER_SWARM, now=1000.0 + 121.0)


def test_the_jobs_seen_slot_is_registered_so_it_restores():
    """Plan §1.5: a twelfth slot, not a degraded group; the accumulated
    ``job_id -> entry`` map both swarm tiers append to."""
    assert SLOT_SWARM_JOBS_SEEN == "swarm_jobs_seen"
    assert SLOT_SWARM_JOBS_SEEN in SLOTS
    assert len(SLOTS) == 12


def test_a_seen_map_round_trips_through_save_and_load(tmp_path):
    """The slot is persisted generically: store a seen map, ``save()``, load
    into a fresh cache and get the same map back with its ``ts``. Per-point
    validation of what comes back is the fold's ``_load_entry`` job on read
    (``surf_swarm.merge_seen``), not the cache's."""
    from tests.data.test_surf_cache import FakeClock

    clock = FakeClock()
    seen = {
        "f046299c-d94e-4760-9e3c-c1e2d3a1a3b2": {
            "created_ts": 1789940487.617, "updated_ts": 1789942558.655,
            "state": "executing", "template": "skill:oracle-assess",
            "nodes": [{"key": "oracle_assess", "seat_token": 463, "seat_agent": "50972",
                       "role": "implement", "state": "working", "verdict_status": "accepted",
                       "rejection_code": None, "revisions": 0, "at_ts": 1789942558.655}],
        },
        "79513878-beb1-4c0c-8720-5b68fb670557": {
            "created_ts": 1789940386.236, "updated_ts": 1789944426.003,
            "state": "completed", "template": "shape:chain", "nodes": [],
        },
    }
    path = tmp_path / "surf.json"
    cache = SurfCache(path=path, clock=clock)
    cache.store_last_good(SLOT_SWARM_JOBS_SEEN, seen, ts=clock.t - 60.0)
    cache.save()

    fresh = SurfCache(path=path, clock=clock)
    fresh.load()
    entry = fresh.get_last_good(SLOT_SWARM_JOBS_SEEN)
    assert entry is not None
    assert entry.payload == seen
    assert entry.ts == clock.t - 60.0
