from maxpane_dashboard.data.surf_cache import (
    SLOTS, SLOT_SWARM, SLOT_SWARM_SCORES, TIERS, TIER_FAILURE_BACKOFF_SECONDS,
    TIER_SWARM, TIER_SWARM_SCORES, TIER_TTL_SECONDS, SurfCache,
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
