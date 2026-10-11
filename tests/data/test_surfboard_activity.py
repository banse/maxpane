"""Observed activity transitions, with committed workers and an injected clock."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surfboard_activity as activity
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SURFBOARD_ACTIVITY, SLOTS, SurfCache
from tests.surf_swarm_fixtures import swarm_capture_v3


NOW = 1_791_670_000.0
TOKEN = 420


def workers(*counts, token=TOKEN):
    """Change only counters and identity in a committed worker response."""
    raw = swarm_capture_v3("workers")
    source = raw["workers"][0]
    raw["workers"] = []
    for index, count in enumerate(counts):
        row = deepcopy(source)
        row["seat"]["tokenId"] = str(token)
        row["working"] = count
        row["deviceKey"] = f"device-{index}"
        raw["workers"].append(row)
    raw["count"] = len(counts)
    return sw.normalize_workers(raw)


def stopped():
    busy = activity.observe(None, workers(1), now=NOW - 120)
    return activity.observe(busy, workers(0), now=NOW)


def test_busy_is_full_and_stop_is_the_observation_time_not_heartbeat():
    payload = activity.observe(None, workers(1), now=NOW)
    assert activity.project(payload, TOKEN, now=NOW) == {
        "state": "busy", "remaining": 86400.0, "as_of": NOW, "stopped_ts": None,
    }
    payload = activity.observe(payload, workers(0), now=NOW + 120)
    assert activity.project(payload, TOKEN, now=NOW + 120) == {
        "state": "idle", "remaining": 86400.0, "as_of": NOW + 120,
        "stopped_ts": NOW + 120,
    }


@pytest.mark.parametrize("elapsed, remaining", [(0, 86400), (43200, 43200), (86400, 0), (90000, 0)])
def test_confirmed_idle_decays_linearly_without_resetting_on_reads(elapsed, remaining):
    payload = activity.observe(stopped(), workers(0), now=NOW + elapsed)
    assert activity.project(payload, TOKEN, now=NOW + elapsed) == {
        "state": "idle", "remaining": remaining, "as_of": NOW + elapsed,
        "stopped_ts": NOW,
    }


def test_resuming_work_resets_to_full_then_a_new_stop_starts_a_new_window():
    payload = activity.observe(stopped(), workers(2), now=NOW + 600)
    assert activity.project(payload, TOKEN, now=NOW + 600)["remaining"] == 86400
    assert activity.project(payload, TOKEN, now=NOW + 600)["stopped_ts"] is None
    payload = activity.observe(payload, workers(0), now=NOW + 720)
    assert activity.project(payload, TOKEN, now=NOW + 720)["stopped_ts"] == NOW + 720


@pytest.mark.parametrize("read", [workers(0), workers()])
def test_initial_idle_or_absence_has_no_invented_stop(read):
    payload = activity.observe(None, read, now=NOW)
    assert activity.project(payload, TOKEN, now=NOW) == {
        "state": "idle", "remaining": None, "as_of": NOW, "stopped_ts": None,
    }


def test_known_busy_disappearing_from_complete_read_starts_stop():
    payload = activity.observe(None, workers(1), now=NOW - 120)
    payload = activity.observe(payload, workers(), now=NOW)
    assert activity.project(payload, TOKEN, now=NOW)["stopped_ts"] == NOW
    payload = activity.observe(payload, workers(), now=NOW + 120)
    assert activity.project(payload, TOKEN, now=NOW + 120)["stopped_ts"] == NOW


def test_incomplete_list_cannot_confirm_absence():
    payload = activity.observe(None, workers(1), now=NOW)
    partial = workers()
    partial["count"] = 1
    payload = activity.observe(payload, partial, now=NOW + 120)
    assert activity.project(payload, TOKEN, now=NOW + 120)["state"] == "unavailable"
    assert activity.project(payload, TOKEN, now=NOW + 120)["stopped_ts"] is None


@pytest.mark.parametrize("counts, expected", [((None, 2), "busy"), ((None, 0), "unavailable"), ((0, 0), "idle"), ((True,), "unavailable")])
def test_any_positive_device_proves_busy_but_unknown_counts_never_prove_idle(counts, expected):
    payload = activity.observe(None, workers(*counts), now=NOW)
    assert activity.project(payload, TOKEN, now=NOW)["state"] == expected


def test_pause_without_a_known_zero_is_not_idle():
    read = workers(None)
    read["workers"][0].update(paused_until_ts=NOW + 600, failures=3, pause_known=True)
    payload = activity.observe(None, read, now=NOW)
    assert activity.project(payload, TOKEN, now=NOW)["state"] == "unavailable"


@pytest.mark.parametrize("read", [None, workers(None)])
def test_failure_or_unknown_count_preserves_existing_stop_without_showing_remaining(read):
    payload = activity.observe(stopped(), read, now=NOW + 120)
    shown = activity.project(payload, TOKEN, now=NOW + 120)
    assert shown["state"] in ("stale", "unavailable")
    assert shown["remaining"] is None
    assert shown["stopped_ts"] == NOW
    payload = activity.observe(payload, workers(0), now=NOW + 240)
    assert activity.project(payload, TOKEN, now=NOW + 240)["remaining"] == 86160


@pytest.mark.parametrize("read", [None, workers(None)])
def test_failure_or_unknown_does_not_consume_the_prior_busy_transition(read):
    payload = activity.observe(None, workers(1), now=NOW)
    payload = activity.observe(payload, read, now=NOW + 120)
    payload = activity.observe(payload, workers(0), now=NOW + 240)
    assert activity.project(payload, TOKEN, now=NOW + 240)["stopped_ts"] == NOW + 240


def test_projection_never_advances_read_clocks_and_expires_after_300_seconds():
    payload = stopped()
    original = deepcopy(payload)
    assert activity.project(payload, TOKEN, now=NOW + 300)["remaining"] == 86100
    shown = activity.project(payload, TOKEN, now=NOW + 301)
    assert shown == {"state": "stale", "remaining": None, "as_of": NOW, "stopped_ts": NOW}
    assert payload == original


def test_identical_successful_reads_advance_freshness_while_failed_attempts_do_not():
    read = workers(1)
    payload = activity.observe(None, read, now=NOW)
    payload = activity.observe(payload, read, now=NOW + 240)
    assert payload["read_ts"] == payload["attempt_ts"] == NOW + 240
    assert activity.project(payload, TOKEN, now=NOW + 500)["state"] == "busy"
    payload = activity.observe(payload, None, now=NOW + 501)
    assert payload["read_ts"] == NOW + 240
    assert payload["attempt_ts"] == NOW + 501
    assert activity.project(payload, TOKEN, now=NOW + 501)["state"] == "stale"


def test_no_successful_read_has_explicit_unavailable_state():
    payload = activity.observe(None, None, now=NOW)
    assert activity.project(payload, TOKEN, now=NOW) == {
        "state": "unavailable", "remaining": None, "as_of": None, "stopped_ts": None,
    }


@pytest.mark.parametrize("field, value", [("read_ts", NOW + 1), ("attempt_ts", True), ("attempt_ts", float("nan")), ("attempt_ts", -1), ("ok", "yes")])
def test_corrupt_source_metadata_is_refused(field, value):
    payload = stopped()
    payload[field] = value
    assert activity.coerce(payload, now=NOW) is None


@pytest.mark.parametrize("edit", [{"stopped_ts": NOW + 1}, {"stopped_ts": True}, {"state": "maybe"}, {"known": 1}, {"seen_ts": float("inf")}])
def test_corrupt_points_are_dropped_without_turning_them_into_confirmed_absence(edit):
    payload = stopped()
    payload["seats"][str(TOKEN)].update(edit)
    clean = activity.coerce(payload, now=NOW)
    assert clean is not None
    assert str(TOKEN) not in clean["seats"]
    assert activity.project(clean, TOKEN, now=NOW)["state"] == "unavailable"


@pytest.mark.parametrize("token", [True, -1, 2 ** 256, "420", None])
def test_projection_rejects_invalid_token_identity(token):
    assert activity.project(stopped(), token, now=NOW)["state"] == "unavailable"


@pytest.mark.parametrize("key", ["0420", "-1", "True", "9" * 1000])
def test_persisted_noncanonical_or_oversize_ids_are_discarded(key):
    payload = stopped()
    payload["seats"][key] = payload["seats"].pop(str(TOKEN))
    assert activity.coerce(payload, now=NOW)["seats"] == {}


def test_history_is_bounded_without_inventing_absence_for_an_evicted_token():
    payload = stopped()
    point = payload["seats"][str(TOKEN)]
    payload["seats"] = {str(i): deepcopy(point) for i in range(4100)}
    clean = activity.coerce(payload, now=NOW)
    assert len(clean["seats"]) == 4096
    evicted = next(i for i in range(4100) if str(i) not in clean["seats"])
    assert activity.project(clean, evicted, now=NOW)["state"] == "unavailable"


def test_activity_cache_roundtrips_and_requires_its_coercer(tmp_path):
    assert SLOT_SURFBOARD_ACTIVITY == "surfboard_activity" and SLOT_SURFBOARD_ACTIVITY in SLOTS
    path = tmp_path / "surf.json"
    cache = SurfCache(path=path, clock=lambda: NOW + 120)
    cache.store_last_good(SLOT_SURFBOARD_ACTIVITY, stopped(), ts=NOW)
    cache.save()
    missing = SurfCache(path=path, clock=lambda: NOW + 120)
    missing.load()
    assert missing.get_last_good(SLOT_SURFBOARD_ACTIVITY) is None
    restored = SurfCache(path=path, clock=lambda: NOW + 120)
    restored.load(slot_coercers={SLOT_SURFBOARD_ACTIVITY: lambda p: activity.coerce(p, now=NOW + 120)})
    entry = restored.get_last_good(SLOT_SURFBOARD_ACTIVITY)
    assert entry is not None and entry.payload == stopped()
    payload = activity.observe(entry.payload, workers(0, token=516), now=NOW + 120)
    assert activity.project(payload, TOKEN, now=NOW + 120)["remaining"] == 86280
    assert activity.project(payload, 516, now=NOW + 120)["remaining"] is None


def test_failed_activity_attempt_never_advances_overall_success_clock(tmp_path):
    cache = SurfCache(path=tmp_path / "surf.json", clock=lambda: NOW + 120)
    cache.store_last_good("chain", {"ok": True}, ts=NOW)
    failed = activity.observe(stopped(), None, now=NOW + 120)
    cache.store_last_good(SLOT_SURFBOARD_ACTIVITY, failed, ts=NOW + 120)
    assert cache.newest_as_of() == NOW
