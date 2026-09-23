import json

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import (
    SLOTS, SLOT_SWARM, SLOT_SWARM_JOBS_SEEN, SLOT_SWARM_SCORES, SLOT_SWARM_SEAT, TIERS,
    TIER_FAILURE_BACKOFF_SECONDS, TIER_SWARM, TIER_SWARM_SCORES, TIER_SWARM_SEAT,
    TIER_TTL_SECONDS, SurfCache,
)
from tests.surf_swarm_fixtures import swarm_seat_capture


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
    assert len(SLOTS) == 17


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


# ---------------------------------------------------------------------------
# The seat tier (docs/surf_agent_seats_plan.md WP2)
# ---------------------------------------------------------------------------


def test_the_seat_tier_and_slot_are_registered_with_their_literals():
    """Hand-typed, never derived: 120 s both ways (plan WP2, §9 N)."""
    assert TIER_SWARM_SEAT == "swarm_seat" and TIER_SWARM_SEAT in TIERS
    assert TIER_TTL_SECONDS[TIER_SWARM_SEAT] == 120.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_SWARM_SEAT] == 120.0
    assert SLOT_SWARM_SEAT == "swarm_seat" and SLOT_SWARM_SEAT in SLOTS


def test_mark_due_makes_the_tier_due_and_keeps_the_last_good(tmp_path):
    from tests.data.test_surf_cache import FakeClock

    clock = FakeClock()
    cache = SurfCache(path=tmp_path / "surf.json", clock=clock)
    slot = {"token": 420, "state": "ok", "seat": swarm_seat_capture("seat_420")}
    cache.store_last_good(SLOT_SWARM_SEAT, slot, ts=clock.t)
    cache.mark_fetched(TIER_SWARM_SEAT, now=clock.t)
    assert TIER_SWARM_SEAT not in cache.tiers_due(clock.t + 1.0)

    cache.mark_due(TIER_SWARM_SEAT)
    assert TIER_SWARM_SEAT in cache.tiers_due(clock.t + 1.0)
    entry = cache.get_last_good(SLOT_SWARM_SEAT)
    assert entry is not None and entry.payload == slot and entry.ts == clock.t
    # No other tier moved.
    cache.mark_fetched(TIER_SWARM, now=clock.t)
    cache.mark_due(TIER_SWARM_SEAT)
    assert TIER_SWARM not in cache.tiers_due(clock.t + 1.0)


def test_mark_due_overrides_a_failure_backoff(tmp_path):
    from tests.data.test_surf_cache import FakeClock

    clock = FakeClock()
    cache = SurfCache(path=tmp_path / "surf.json", clock=clock)
    cache.mark_failed(TIER_SWARM_SEAT, now=clock.t)
    assert not cache.is_due(TIER_SWARM_SEAT, now=clock.t + 60.0)
    cache.mark_due(TIER_SWARM_SEAT)
    assert cache.is_due(TIER_SWARM_SEAT, now=clock.t + 60.0)


def test_mark_due_refuses_an_unknown_tier(tmp_path):
    cache = SurfCache(path=tmp_path / "surf.json")
    with pytest.raises(ValueError):
        cache.mark_due("not-a-tier")


@pytest.mark.parametrize("slot", [
    {"token": 420, "state": "ok", "seat": swarm_seat_capture("seat_420")},
    {"token": 999_999, "state": "unknown_seat", "seat": None},
])
def test_a_seat_slot_round_trips_through_save_and_load(tmp_path, slot):
    from tests.data.test_surf_cache import FakeClock

    clock = FakeClock()
    path = tmp_path / "surf.json"
    cache = SurfCache(path=path, clock=clock)
    cache.store_last_good(SLOT_SWARM_SEAT, slot, ts=clock.t - 60.0)
    cache.save()

    fresh = SurfCache(path=path, clock=clock)
    fresh.load()
    entry = fresh.get_last_good(SLOT_SWARM_SEAT)
    assert entry is not None and entry.ts == clock.t - 60.0
    assert entry.payload == slot
    assert sw.coerce_seat_slot(entry.payload) == slot


@pytest.mark.parametrize("edit", [
    {"token": True},                       # a bool is not a token
    {"token": "420"},                      # nor is a string
    {"state": "pending"},                  # never stored: not a finished read
    {"state": "maybe"},                    # an unknown state
    {"seat": None},                        # "ok" with no seat
    {"seat": [1, 2]},                      # a list where the seat goes
    {"token": 516},                        # another token's seat under this token
])
def test_a_hand_edited_seat_slot_loads_but_is_refused_per_field(tmp_path, edit):
    """The cache restores the slot generically; the manager's reader
    (``coerce_seat_slot``) refuses it whole. A hand-edited cache file is
    third-party input (rules/data.md)."""
    from tests.data.test_surf_cache import FakeClock

    clock = FakeClock()
    path = tmp_path / "surf.json"
    good = {"token": 420, "state": "ok", "seat": swarm_seat_capture("seat_420")}
    cache = SurfCache(path=path, clock=clock)
    cache.store_last_good(SLOT_SWARM_SEAT, good, ts=clock.t - 60.0)
    cache.save()
    on_disk = json.loads(path.read_text())
    on_disk["last_good"][SLOT_SWARM_SEAT]["payload"].update(edit)
    path.write_text(json.dumps(on_disk))

    fresh = SurfCache(path=path, clock=clock)
    fresh.load()
    entry = fresh.get_last_good(SLOT_SWARM_SEAT)
    assert entry is not None, "the cache keeps the slot; the reader judges it"
    assert sw.coerce_seat_slot(entry.payload) is None


# BOARD normalized slots are validated on load by injected pure coercers.


def _board_coercers():
    return {"swarm_workers": sw.coerce_workers_slot, "swarm_contributors": sw.coerce_contributors_slot}


def test_board_tier_and_two_slots_have_frozen_names_and_cadence():
    from maxpane_dashboard.data import surf_cache as mod

    assert mod.TIER_SWARM_BOARD == "swarm_board"
    assert mod.TIER_SWARM_BOARD in TIERS
    assert TIER_TTL_SECONDS[mod.TIER_SWARM_BOARD] == 120.0
    assert TIER_FAILURE_BACKOFF_SECONDS[mod.TIER_SWARM_BOARD] == 120.0
    assert mod.SLOT_SWARM_WORKERS == "swarm_workers" and mod.SLOT_SWARM_WORKERS in SLOTS
    assert mod.SLOT_SWARM_CONTRIBUTORS == "swarm_contributors" and mod.SLOT_SWARM_CONTRIBUTORS in SLOTS


@pytest.mark.parametrize("source", ["workers", "contributors"])
def test_board_slots_roundtrip_with_configured_coercers(tmp_path, source):
    from tests.data.test_surf_cache import FakeClock
    from tests.surf_swarm_fixtures import swarm_capture_v3

    clock = FakeClock(); path = tmp_path / "surf.json"
    slot = f"swarm_{source}"
    payload = getattr(sw, f"normalize_{source}")(swarm_capture_v3(source))
    cache = SurfCache(path=path, clock=clock)
    cache.store_last_good(slot, payload, ts=clock.t - 60); cache.save()
    fresh = SurfCache(path=path, clock=clock)
    fresh.load(slot_coercers=_board_coercers())
    entry = fresh.get_last_good(slot)
    assert entry.payload == payload and entry.ts == clock.t - 60


@pytest.mark.parametrize("source", ["workers", "contributors"])
def test_board_unconfigured_load_refuses_the_slot_instead_of_trusting_it(tmp_path, source):
    from tests.data.test_surf_cache import FakeClock
    from tests.surf_swarm_fixtures import swarm_capture_v3

    clock = FakeClock(); path = tmp_path / "surf.json"
    slot = f"swarm_{source}"
    cache = SurfCache(path=path, clock=clock)
    cache.store_last_good(slot, getattr(sw, f"normalize_{source}")(swarm_capture_v3(source)), ts=clock.t)
    cache.store_last_good(SLOT_SWARM, {"health": "unrelated"}, ts=clock.t)
    cache.save()
    fresh = SurfCache(path=path, clock=clock); fresh.load()
    assert fresh.get_last_good(slot) is None
    assert fresh.get_last_good(SLOT_SWARM).payload == {"health": "unrelated"}


@pytest.mark.parametrize("source", ["workers", "contributors"])
@pytest.mark.parametrize("field,value", [("token_id", True), ("device_key", 123)])
def test_board_hand_edited_slot_is_refused_at_load(tmp_path, source, field, value):
    from tests.data.test_surf_cache import FakeClock
    from tests.surf_swarm_fixtures import swarm_capture_v3

    clock = FakeClock(); path = tmp_path / "surf.json"
    cache = SurfCache(path=path, clock=clock)
    for name in ("workers", "contributors"):
        payload = getattr(sw, f"normalize_{name}")(swarm_capture_v3(name))
        cache.store_last_good(f"swarm_{name}", payload, ts=clock.t)
    cache.save()
    raw = json.loads(path.read_text())
    raw["last_good"][f"swarm_{source}"]["payload"][source][0][field] = value
    path.write_text(json.dumps(raw))
    fresh = SurfCache(path=path, clock=clock); fresh.load(slot_coercers=_board_coercers())
    assert fresh.get_last_good(f"swarm_{source}") is None
    good = "contributors" if source == "workers" else "workers"
    assert fresh.get_last_good(f"swarm_{good}") is not None


@pytest.mark.parametrize('source', ['contributors', 'workers'])
def test_i1_cache_refuses_old_source_slots_missing_identity_metadata(tmp_path, source):
    from tests.data.test_surf_cache import FakeClock
    from tests.surf_swarm_fixtures import swarm_capture_v3

    clock = FakeClock()
    payload = getattr(sw, f'normalize_{source}')(swarm_capture_v3(source))
    payload.pop('malformed_tokens')
    cache = SurfCache(path=tmp_path / 'surf.json', clock=clock)
    cache.store_last_good(f'swarm_{source}', payload, ts=clock.t)
    cache.save()
    fresh = SurfCache(path=cache.path, clock=clock)
    fresh.load(slot_coercers=_board_coercers())
    assert fresh.get_last_good(f'swarm_{source}') is None


def test_polish_answers_slot_is_registered_and_refuses_unvalidated_load(tmp_path):
    from maxpane_dashboard.data import surf_cache as mod
    assert mod.SLOT_SWARM_ANSWERS == "swarm_answers"
    assert SLOTS.count(mod.SLOT_SWARM_ANSWERS) == 1
    path = tmp_path / "answers.json"
    cache = SurfCache()
    cache.store_last_good(mod.SLOT_SWARM_ANSWERS, {"unvalidated": {}}, ts=1000.0)
    cache.save(str(path))
    fresh = SurfCache()
    fresh.load(str(path), now=1000.0)
    assert fresh.get_last_good(mod.SLOT_SWARM_ANSWERS) is None
