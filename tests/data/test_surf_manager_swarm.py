"""The swarm's two refresh tiers, the jobs-seen slot and the AGENT seat in SurfManager.

Zero network, structurally: the surf and pool4 clients are the established
doubles from ``test_surf_manager``/``test_surf_manager_pool4`` (the surf
double's transport is a :class:`~tests.data.test_surf_manager.DeadTransport`
that raises on any use), and the swarm client is the fake given below --
the real :class:`~maxpane_dashboard.data.surf_swarm_client.SwarmClient` is
never constructed in this file. The clock is a fake too, so every "N seconds
later" in these tests is exact rather than a race against wall time.

Fix round 1 (controller-mandated, finding 1): the two swarm tiers are spawned
independently, with no gate between them, so both are typically due -- and
both spawned -- on a cold cycle. ``_FakeSwarm``'s methods each carry a real
``await asyncio.sleep(0)`` suspension point so the two spawned tasks
genuinely interleave the way real I/O would, rather than one running to
completion before the other is ever given a turn (an artifact of the
original all-synchronous fake). Tests that need to isolate one tier's own
work assert against that tier's own stored slot or against a call-count
*delta*, never against the shared call log's absolute value or its ordering.

WP4 (swarm v2, plan A3): the fake serves the **2026-09-21 v2 corpus**
(``swarm_capture_v2`` / ``swarm_details_v2``). Every fixture-derived pin
below was re-read off that corpus: ``/health.connectedDaemons`` is 28, the
100-job list holds 98 ``completed`` and 2 ``executing`` (one of which,
``f046299c…``, has a committed detail; the other is a 404), the roster has
16 seats led by token 0, seat 1548 is the corpus feedback pin (17 entries)
and seat 463 works the one executing detail. The corpus stamps are
2026-09-20 -- 43 days *after* ``test_surf_manager.NOW`` -- so the tests
that reason about the seen slot's age run their clock from ``V2_NOW``.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import re
from collections import Counter
from datetime import datetime, timezone

import pytest

from maxpane_dashboard.data import surf_manager as surf_manager_mod
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import (
    SLOT_SWARM, SLOT_SWARM_JOBS_SEEN, SLOT_SWARM_SCORES, SLOT_SWARM_SEAT, TIER_SWARM,
    TIER_SWARM_SCORES, TIER_SWARM_SEAT,
)
from maxpane_dashboard.data.surf_manager import (
    SWARM_JOBS_SEEN_MAX_AGE_S, SWARM_SWEEP_CAP, SurfManager,
)
from maxpane_dashboard.data.surf_models import SURF_KEYS, SWARM_KEYS
from maxpane_dashboard.data.surf_swarm_client import UNKNOWN_SEAT
from tests.data.test_surf_manager import FakeClock, FakeSurfClient, NOW
from tests.data.test_surf_manager_pool4 import FakePool4Client
from tests.surf_swarm_fixtures import (
    swarm_capture_v2, swarm_details_v2, swarm_seat_capture,
)

#: Just after the corpus's newest ``updatedAt`` (``2026-09-20T23:06:10.038Z``).
V2_NOW = 1_789_945_600.0

#: Every stamp the host writes: UTC, ISO-8601, millisecond precision, ``Z``.
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

_SEAT_KEYS = (
    "swarm_seat_rows", "swarm_seat_selected", "swarm_seat_summary",
    "swarm_seat_node_rows", "swarm_seat_feedback_rows", "swarm_seat_as_of_hhmm",
)


def _stamp(ts: float) -> str:
    """A host-shaped stamp for a synthetic job."""
    whole = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return whole.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(round((ts % 1) * 1000)):03d}Z"


def _synthetic_jobs(n: int, *, start_ts: float, step_s: float = 1.0,
                    state: str = "completed") -> list[dict]:
    """``n`` jobs with distinct stamps, oldest first: index 0 is the oldest."""
    return [
        {
            "id": f"synthetic-{i:04d}",
            "state": state,
            "template": "skill:synthetic",
            "createdAt": _stamp(start_ts + i * step_s),
            "updatedAt": _stamp(start_ts + i * step_s + 0.5),
        }
        for i in range(n)
    ]


class _FakeSwarm:
    """Serves the committed v2 corpus and counts what was asked for, per route.

    Each method carries a real ``await asyncio.sleep(0)`` -- fix round 1
    finding 1 -- so two concurrently-spawned tasks against this fake actually
    interleave, matching real I/O, instead of one running to full completion
    before the other is ever scheduled.

    ``fail`` kills ``/health`` (so the live tier never reaches ``/jobs``);
    the per-route ``fail_*`` switches serve ``None`` for that one route only,
    the client's contract for a 404 or a dead host. ``fetch_job`` answers the
    committed detail or ``None`` -- a 404 -- for an id the corpus lacks.

    ``fetch_seat`` (the /seats plan WP2) serves ``seats[token]`` -- by
    default the four committed seat captures -- and ``UNKNOWN_SEAT`` for a
    token it has no entry for; an entry of ``None`` is every host failing.
    ``seat_gate``, when given, holds each seat read in flight until it is
    set, and ``seat_entered`` is set once a read has reached that point, so
    a test awaits observable state rather than a clock.
    """

    def __init__(self, *, jobs=None, health=None, details=None, fail=False,
                 fail_jobs=False, fail_skills=False, fail_launches=False,
                 fail_sites=False, seats=None, seat_gate=None):
        self.calls: Counter = Counter()
        self.detail_calls: list[str] = []
        self.seat_calls: list[int] = []
        self.seats: dict = (
            {t: swarm_seat_capture(f"seat_{t}") for t in (0, 420, 516, 1649)}
            if seats is None else dict(seats)
        )
        self.seat_gate = seat_gate
        self.seat_entered = asyncio.Event()
        self._jobs = swarm_capture_v2("jobs")["jobs"] if jobs is None else jobs
        self._health = swarm_capture_v2("health") if health is None else health
        self._details = swarm_details_v2() if details is None else details
        self._fail = fail
        self._fail_jobs = fail_jobs
        self._fail_skills = fail_skills
        self._fail_launches = fail_launches
        self._fail_sites = fail_sites

    @property
    def health_calls(self) -> int:
        return self.calls["health"]

    @property
    def job_calls(self) -> int:
        return self.calls["jobs"]

    async def fetch_health(self):
        await asyncio.sleep(0)
        self.calls["health"] += 1
        return None if self._fail else dict(self._health)

    async def fetch_version(self):
        await asyncio.sleep(0)
        self.calls["version"] += 1
        return dict(swarm_capture_v2("version"))

    async def fetch_jobs(self):
        await asyncio.sleep(0)
        self.calls["jobs"] += 1
        return None if (self._fail or self._fail_jobs) else list(self._jobs)

    async def fetch_job(self, job_id):
        await asyncio.sleep(0)
        self.calls["job"] += 1
        self.detail_calls.append(job_id)
        detail = self._details.get(job_id)
        return dict(detail) if isinstance(detail, dict) else None

    async def fetch_skills(self):
        await asyncio.sleep(0)
        self.calls["skills"] += 1
        return None if self._fail_skills else list(swarm_capture_v2("skills")["skills"])

    async def fetch_launches(self):
        await asyncio.sleep(0)
        self.calls["launches"] += 1
        return None if self._fail_launches else list(swarm_capture_v2("launches")["launches"])

    async def fetch_sites(self):
        await asyncio.sleep(0)
        self.calls["sites"] += 1
        return None if self._fail_sites else list(swarm_capture_v2("sites")["sites"])

    async def fetch_seat(self, token):
        await asyncio.sleep(0)
        self.calls["seat"] += 1
        self.seat_calls.append(token)
        self.seat_entered.set()
        if self.seat_gate is not None:
            await self.seat_gate.wait()
        if token not in self.seats:
            return dict(UNKNOWN_SEAT)
        answer = self.seats[token]
        return None if answer is None else copy.deepcopy(answer)

    async def close(self):
        return None


def _manager(tmp_path, swarm, **kw) -> SurfManager:
    """:class:`SurfManager` wired to structurally network-dead doubles.

    ``client``/``pool4_client`` default to ``FakeSurfClient()``/
    ``FakePool4Client()`` rather than the constructor's real-network defaults
    -- CLAUDE.md's "no test may touch the network" -- as every other manager
    test file in this package does. The clock defaults to a fixed
    :class:`FakeClock` so "61 seconds later" is exact, never a race.
    """
    kw.setdefault("client", FakeSurfClient())
    kw.setdefault("pool4_client", FakePool4Client())
    kw.setdefault("clock", FakeClock(NOW))
    return SurfManager(cache_path=tmp_path / "surf.json", swarm_client=swarm, **kw)


async def _settle(manager: SurfManager) -> None:
    """Wait for whichever swarm tiers this cycle spawned (the seat read too)."""
    tasks = [t for t in (manager._swarm_task, manager._swarm_scores_task,
                         manager._swarm_seat_task) if t is not None]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _landed(tmp_path, swarm, **kw):
    """A manager whose both tiers have landed once, and the payload after them."""
    manager = _manager(tmp_path, swarm, **kw)
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    return manager, payload


def _seen(manager: SurfManager) -> dict | None:
    entry = manager.cache.get_last_good(SLOT_SWARM_JOBS_SEEN)
    return None if entry is None else entry.payload


def _seat_of(details: dict, token: int) -> set[str]:
    """The corpus jobs whose detail carries a node in seat ``token``."""
    return {
        job_id for job_id, d in details.items()
        if any(
            isinstance(n.get("seat"), dict) and n["seat"].get("tokenId") == str(token)
            for n in d.get("nodes") or []
        )
    }


# ---------------------------------------------------------------------------
# The two tiers: spawn, gate, isolation (ported from the 2026-09-16 corpus)
# ---------------------------------------------------------------------------


async def test_the_first_payload_is_not_behind_the_swarm_read(tmp_path):
    class _Slow(_FakeSwarm):
        async def fetch_health(self):
            await asyncio.sleep(30)
            raise AssertionError("first paint waited for the swarm")

    manager = _manager(tmp_path, _Slow())
    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert set(payload) == set(SURF_KEYS)
    await manager.close()


async def test_the_scores_sweep_runs_even_while_the_live_read_is_still_in_flight(tmp_path):
    """Fix round 1 finding 1: the two tiers run on independent clocks.

    A live read that never completes (``_Slow``, a real ``asyncio.sleep(30)``)
    reproduces "the live tier is due and in flight" on every cycle without
    waiting 60 real seconds: the scores sweep must still be spawned and must
    still be able to finish.
    """
    class _Slow(_FakeSwarm):
        async def fetch_health(self):
            await asyncio.sleep(30)
            raise AssertionError("must not have been reached")

    manager = _manager(tmp_path, _Slow())
    await manager.fetch_and_compute()
    assert manager._swarm_task is not None and not manager._swarm_task.done()
    assert manager._swarm_scores_task is not None, "the scores sweep must not wait on the live read"
    await manager._swarm_scores_task
    assert manager._swarm_scores_task.done()
    await manager.close()


async def test_only_one_swarm_sweep_is_ever_in_flight(tmp_path):
    """Fix round 1 finding 5: the tier is due both times *and* the previous
    task is genuinely still in flight both times, which is what exercises
    the "already running" guard."""
    class _Slow(_FakeSwarm):
        async def fetch_health(self):
            await asyncio.sleep(30)
            raise AssertionError("should have been reused, not restarted")

    manager = _manager(tmp_path, _Slow())
    await manager.fetch_and_compute()
    first = manager._swarm_task
    assert first is not None and not first.done(), "the live read must still be in flight"
    await manager.fetch_and_compute()
    assert manager._swarm_task is first
    await manager.close()


async def test_details_are_fetched_only_for_executing_jobs(tmp_path):
    """Plan §1.5: the live tier reads the detail route for ``executing`` jobs
    only -- not ``blocked`` (the v1 "still moving" rule) and not the 98
    completed ones. ``TIER_SWARM_SCORES`` is marked fetched first so the
    shared call log holds the live tier's work alone."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    assert manager._swarm_scores_task is None, "the scores tier must not have been due"
    await manager._swarm_task
    executing = {j["id"] for j in swarm._jobs if j["state"] == "executing"}
    assert executing, "the corpus must hold an executing job for this to bite"
    assert set(swarm.detail_calls) == executing
    assert swarm.calls["job"] == len(executing)
    assert len(swarm.detail_calls) < len(swarm._jobs)
    await manager.close()


async def test_a_blocked_job_is_not_read_by_the_live_tier(tmp_path):
    """The half of the rule above the corpus cannot show: ``blocked`` was in
    the v1 "still moving" set and is not ``executing``."""
    jobs = [dict(j) for j in swarm_capture_v2("jobs")["jobs"][:6]]
    jobs[0]["state"] = "blocked"
    jobs[1]["state"] = "executing"
    for job in jobs[2:]:
        job["state"] = "completed"
    swarm = _FakeSwarm(jobs=jobs)
    manager = _manager(tmp_path, swarm)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    await manager._swarm_task
    assert swarm.detail_calls == [jobs[1]["id"]]
    await manager.close()


async def test_the_job_list_is_not_re_read_when_no_counter_moved(tmp_path):
    """Fix round 1 finding 1: assert on the *delta* the direct call caused."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await _settle(manager)
    health_before, jobs_before = swarm.health_calls, swarm.job_calls
    manager.cache.mark_failed(TIER_SWARM, now=0.0)  # make it due again
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.health_calls == health_before + 1
    assert swarm.job_calls == jobs_before, "the list was paid for twice with nothing moved"
    await manager.close()


async def test_a_moved_counter_forces_the_list(tmp_path):
    """Fix round 1 finding 1: the delta-based sibling of the test above."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await _settle(manager)
    jobs_before = swarm.job_calls
    swarm._health = dict(swarm._health, acceptedLastDay=swarm._health["acceptedLastDay"] + 1)
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == jobs_before + 1
    await manager.close()


@pytest.mark.parametrize("counter", ["pendingOracle", "pendingSomethingNew"])
async def test_a_pending_counter_the_gate_never_named_still_forces_the_list(tmp_path, counter):
    """Plan §1.1: the gate is an open set -- every ``pending*`` field plus the
    four named ones. ``pendingOracle`` arrived between the 2026-09-16 and
    2026-09-21 captures and the old closed tuple never saw it; the second
    case is a counter the host has not invented yet. Restore the closed
    tuple and both cases redden."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await _settle(manager)
    jobs_before = swarm.job_calls
    swarm._health = dict(swarm._health, **{counter: swarm._health.get(counter, 0) + 1})
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == jobs_before + 1, f"a moved {counter} did not force the list"
    await manager.close()


async def test_a_non_counter_health_field_does_not_force_the_list(tmp_path):
    """The other edge of the open set: ``/health.version`` (and every other
    non-``pending`` field outside the four) moving is not evidence the list
    changed, so it must not pay for the 27.5 KB read."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await _settle(manager)
    jobs_before = swarm.job_calls
    swarm._health = dict(swarm._health, version="moved", status="moved")
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == jobs_before
    await manager.close()


async def test_a_failed_read_leaves_the_counter_gate_armed(tmp_path):
    """Fix round 1 finding 2: ``_swarm_counters`` reflects the last
    *successful* read, so a failed attempt after a counter move leaves the
    next read obliged to try again."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await _settle(manager)

    swarm._health = dict(swarm._health, acceptedLastDay=swarm._health["acceptedLastDay"] + 1)
    swarm._fail_jobs = True
    jobs_before = swarm.job_calls
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == jobs_before + 1, "the moved counter must have forced an attempt"

    swarm._fail_jobs = False
    jobs_before = swarm.job_calls
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 122.0)
    assert swarm.job_calls == jobs_before + 1, "a failed attempt must not have armed the gate shut"
    await manager.close()


# ---------------------------------------------------------------------------
# Zero vs None on the live keys (old and new)
# ---------------------------------------------------------------------------


async def test_a_real_zero_publishes_as_zero_not_none(tmp_path):
    """Fix round 1 finding 3, on the v2 keys since WP7: a successful read
    with nothing executing publishes a real ``[]`` and a THROUGHPUT dict
    whose rollup has no ``executing`` bucket -- never ``None``, which only a
    list that was never read publishes."""
    all_completed = [dict(j, state="completed") for j in swarm_capture_v2("jobs")["jobs"][:5]]
    _, payload = await _landed(tmp_path, _FakeSwarm(jobs=all_completed))
    assert payload["swarm_inflight_rows"] == []
    facts = payload["swarm_throughput"]
    assert facts["window_n"] == 5
    assert facts["states"] == [{"state": "completed", "count": 5}]


async def test_an_unread_list_still_publishes_none(tmp_path):
    """Fix round 1 finding 3's other half: an unread list is still ``None``
    on every list-derived key, and ``/health``'s own keys with it (the slot
    is not written when the list read fails)."""
    manager = _manager(tmp_path, _FakeSwarm(fail=True))
    payload = await manager.fetch_and_compute()
    assert payload["swarm_inflight_rows"] is None
    assert payload["swarm_throughput"] is None
    assert payload["swarm_agents_online"] is None
    await manager.close()


async def test_a_genuinely_empty_read_publishes_zero_not_none(tmp_path):
    """F-C: a *successful* read of an idle swarm (``{"jobs": []}``) publishes
    a real empty list and a dict of honest empties (``window_n == 0``), not
    ``None``; the marker proves the read happened."""
    _, payload = await _landed(tmp_path, _FakeSwarm(jobs=[]))
    assert payload["swarm_as_of_hhmm"] is not None, "the read must have succeeded"
    assert payload["swarm_inflight_rows"] == []
    facts = payload["swarm_throughput"]
    assert facts is not None and facts["window_n"] == 0 and facts["states"] == []
    assert facts["dur_n"] == 0 and facts["dur_median_s"] is None


async def test_a_failed_jobs_read_publishes_none_not_empty(tmp_path):
    """Plan WP4 mutation: serve ``[]`` for a failed ``/jobs`` and this reddens.

    The fold answers ``[]`` for ``None`` and ``[]`` alike; the manager is the
    one place that knows the list was never read, and it must say ``None``
    (CLAUDE.md "a failed read is ``None``"). ``/health`` keeps answering, so
    this is specifically the ``/jobs`` failure path, and because the live
    slot is not written at all on that path the health-derived new keys are
    ``None`` too -- nothing landed, nothing is presented as live.
    """
    manager = _manager(tmp_path, _FakeSwarm(fail_jobs=True))
    await manager.fetch_and_compute()
    await asyncio.gather(*(t for t in (manager._swarm_task, manager._swarm_scores_task) if t),
                         return_exceptions=True)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_inflight_rows"] is None
    assert payload["swarm_queue_total"] is None
    assert payload["swarm_breaker"] is None
    assert payload["swarm_as_of_hhmm"] is None
    await manager.close()


async def test_a_list_with_no_executing_job_publishes_an_empty_inflight_list(tmp_path):
    """The other half: a read list with nothing executing is a real ``[]``."""
    all_completed = [dict(j, state="completed") for j in swarm_capture_v2("jobs")["jobs"][:5]]
    _, payload = await _landed(tmp_path, _FakeSwarm(jobs=all_completed))
    assert payload["swarm_as_of_hhmm"] is not None
    assert payload["swarm_inflight_rows"] == []


async def test_the_live_keys_carry_queue_total_breaker_and_inflight_rows(tmp_path):
    """The three new live keys (plan §1.1/§1.2) off the corpus: the pending
    counters sum to 45 (``pendingFeedback`` alone is non-zero), the breaker
    is ``null`` on the host (= not tripped, a fact), and the two executing
    jobs make two IN FLIGHT rows -- the one with a committed detail carries
    its seat, the 404 one carries ``None`` attribution."""
    health = swarm_capture_v2("health")
    expected_total = sum(v for k, v in health.items() if k.startswith("pending"))
    _, payload = await _landed(tmp_path, _FakeSwarm())
    assert payload["swarm_queue_total"] == expected_total == 45
    assert payload["swarm_breaker"] == {"tripped": False, "detail": None}
    rows = payload["swarm_inflight_rows"]
    assert [r["job_id"][:8] for r in rows] == ["f046299c", "708ea465"]
    assert rows[0]["agent_token"] == 463 and rows[0]["node_state"] == "working"
    assert rows[1]["agent_token"] is None and rows[1]["node_key"] is None


# ---------------------------------------------------------------------------
# The slow sweep: cap, partial success, its keys
# ---------------------------------------------------------------------------


def test_every_corpus_stamp_is_utc_iso_8601_with_milliseconds():
    """The premise of the sweep's newest-first order: ``_swarm_sweep_ids``
    sorts on the ``createdAt`` *string*, which is chronological only while
    every stamp is ``YYYY-MM-DDTHH:MM:SS.mmmZ``. The day the host writes an
    offset or a different precision, this is what says so."""
    jobs = swarm_capture_v2("jobs")["jobs"]
    assert jobs
    for job in jobs:
        assert _STAMP.match(job["createdAt"]), job["createdAt"]
        assert _STAMP.match(job["updatedAt"]), job["updatedAt"]
    assert _STAMP.match(_stamp(V2_NOW + 0.337)), "the synthetic stamps must be host-shaped too"


async def test_the_sweep_reads_at_most_the_cap_newest_first(tmp_path):
    """R-F: ``SWARM_SWEEP_CAP + 3`` jobs with distinct stamps -> exactly
    ``SWARM_SWEEP_CAP`` detail reads, and the three *oldest* are the ones
    not asked for."""
    jobs = _synthetic_jobs(SWARM_SWEEP_CAP + 3, start_ts=V2_NOW - 3600.0)
    # Shuffle the list order so a sort that trusts the host's order fails too.
    jobs = jobs[1::2] + jobs[0::2]
    swarm = _FakeSwarm(jobs=jobs)
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    result = await manager._pool_swarm_scores({TIER_SWARM_SCORES}, V2_NOW)
    assert result["ok"]
    assert len(swarm.detail_calls) == SWARM_SWEEP_CAP
    oldest = {"synthetic-0000", "synthetic-0001", "synthetic-0002"}
    assert oldest.isdisjoint(swarm.detail_calls)
    assert swarm.detail_calls[0] == f"synthetic-{SWARM_SWEEP_CAP + 2:04d}", "newest first"
    await manager.close()


async def test_a_job_past_the_sweep_cap_is_still_served_from_the_seen_slot(tmp_path):
    """R-F's second clause: the seen slot carries what the sweep no longer
    reaches. A job older than the cap, whose seat record entered the slot on
    an earlier tick, stays in the slot after the sweep and its seat is still
    on the roster -- served from the slot, not dropped."""
    old_id = "synthetic-0000"
    jobs = _synthetic_jobs(SWARM_SWEEP_CAP + 3, start_ts=V2_NOW - 3600.0)
    seen_before = {
        old_id: {
            "created_ts": V2_NOW - 3600.0, "updated_ts": V2_NOW - 3599.5,
            "state": "completed", "template": "skill:synthetic",
            "nodes": [{
                "key": "implement", "seat_token": 4242, "seat_agent": "9",
                "role": "implement", "state": "accepted", "verdict_status": "accepted",
                "rejection_code": None, "revisions": 0, "at_ts": V2_NOW - 3599.5,
            }],
        },
    }
    swarm = _FakeSwarm(jobs=jobs)
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    manager.cache.store_last_good(SLOT_SWARM_JOBS_SEEN, seen_before, ts=V2_NOW - 60.0)
    await manager._pool_swarm_scores({TIER_SWARM_SCORES}, V2_NOW)
    assert old_id not in swarm.detail_calls, "the job must be past the cap for this to bite"
    seen = _seen(manager)
    assert seen[old_id]["nodes"] == seen_before[old_id]["nodes"]
    entry = manager.cache.get_last_good(SLOT_SWARM_SCORES)
    keys = manager._swarm_seat_keys(entry.payload, entry, seen, None)
    assert [r["token_id"] for r in keys["swarm_seat_rows"]] == [4242]
    await manager.close()


async def test_a_dead_skills_route_leaves_only_its_keys_none(tmp_path):
    """R-B: partial success is a success. ``/skills`` answers a 404 (``None``
    from the client); the sweep still lands, its marker is set, launches,
    sites and the seat roster are lists, the live keys are live, and only
    the two skill keys are ``None``."""
    _, payload = await _landed(tmp_path, _FakeSwarm(fail_skills=True))
    assert payload["swarm_scores_as_of_hhmm"] is not None, "partial success must still land"
    assert payload["swarm_skill_rows"] is None
    assert payload["swarm_skill_summary"] is None
    assert isinstance(payload["swarm_launch_rows"], list) and payload["swarm_launch_rows"]
    assert isinstance(payload["swarm_site_rows"], list) and payload["swarm_site_rows"]
    assert isinstance(payload["swarm_seat_rows"], list) and payload["swarm_seat_rows"]
    assert payload["swarm_launch_summary"]["by_status"]
    assert payload["swarm_agents_online"] == 28 and payload["swarm_as_of_hhmm"] is not None


async def test_a_dead_launches_route_leaves_only_its_keys_none(tmp_path):
    """R-B's sibling for the route the old tier used to fail the whole sweep on."""
    _, payload = await _landed(tmp_path, _FakeSwarm(fail_launches=True, fail_sites=True))
    assert payload["swarm_scores_as_of_hhmm"] is not None
    assert payload["swarm_launch_rows"] is None and payload["swarm_launch_summary"] is None
    assert payload["swarm_site_rows"] is None
    assert payload["swarm_skill_rows"] and payload["swarm_skill_summary"]["total"] == 30


async def test_the_slow_keys_land_from_the_sweep(tmp_path):
    """The four §1.2 row keys and the two §1.1 summaries off the corpus."""
    _, payload = await _landed(tmp_path, _FakeSwarm())
    assert len(payload["swarm_skill_rows"]) == 30
    assert payload["swarm_skill_summary"]["total"] == 30
    assert len(payload["swarm_launch_rows"]) == 30
    assert sum(r["count"] for r in payload["swarm_launch_summary"]["by_kind"]) == 30
    assert len(payload["swarm_site_rows"]) == 6
    assert payload["swarm_stale"] is False
    # ``swarm_throughput`` is §1.3's dict off the LIVE tier's own list since
    # WP7 (its widget shows ``swarm_as_of_hhmm``); the corpus window is the
    # hundred jobs ``/jobs`` returned, ten of them delivered.
    tp = payload["swarm_throughput"]
    assert tp["window_n"] == 100 and tp["dur_n"] == 10
    assert "accepted_per_day" not in tp


async def test_the_sweep_publishes_whole_rows_even_with_no_live_slot(tmp_path):
    """Fix round 1 finding 4: ``shipped_rows`` comes off the sweep's own
    stored ``jobs``, so a populated sweep slot publishes whole rows whether
    or not the live tier has ever run. ``swarm_throughput`` is **not** this
    fold's since WP7 -- it rides the live slot behind the live marker."""
    jobs = swarm_capture_v2("jobs")["jobs"]
    launches = swarm_capture_v2("launches")["launches"]
    sites = swarm_capture_v2("sites")["sites"]
    manager = _manager(tmp_path, _FakeSwarm())
    scores_entry = manager.cache.store_last_good(
        SLOT_SWARM_SCORES,
        {"jobs": jobs, "details": [], "launches": launches, "sites": sites},
        ts=manager._clock(),
    )
    assert manager.cache.get_last_good(SLOT_SWARM) is None  # the live slot never ran
    keys = manager._swarm_scores_keys(
        scores_entry.payload, scores_entry, None, manager._clock()
    )
    assert keys["swarm_launch_rows"] and keys["swarm_site_rows"], (
        "no launch/site rows with a whole sweep slot"
    )
    assert "swarm_throughput" not in keys
    # WP7 retired the v1 keys this method used to emit off the same slot.
    assert "swarm_shipped_rows" not in keys and "swarm_score_rows" not in keys
    # A slot persisted before WP4 has no ``skills``: its keys are ``None``,
    # never a crash and never an empty list presented as read.
    assert keys["swarm_skill_rows"] is None and keys["swarm_skill_summary"] is None
    await manager.close()


# ---------------------------------------------------------------------------
# The jobs-seen slot
# ---------------------------------------------------------------------------


async def test_one_live_success_seeds_the_seen_slot_with_every_listed_job(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    assert _seen(manager) is None
    await manager.fetch_and_compute()
    await manager._swarm_task
    seen = _seen(manager)
    assert isinstance(seen, dict)
    assert set(seen) == {j["id"] for j in swarm._jobs}
    assert len(seen) == len(swarm._jobs) == 100
    # The executing job whose detail was read carries its node summary, key first.
    executing = next(j["id"] for j in swarm._jobs if j["state"] == "executing" and j["id"] in swarm._details)
    assert list(seen[executing]["nodes"][0])[0] == "key"
    assert seen[executing]["nodes"][0]["seat_token"] == 463
    await manager.close()


async def test_an_unchanged_seen_map_is_not_re_stored(tmp_path, monkeypatch):
    """F7: ``store_last_good`` sets ``_dirty`` and the live slot is stored on
    every tick anyway, so the observable is the *seen slot's* store calls: a
    second tick over the same list must not make one."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    await manager._swarm_task
    stores: list[str] = []
    real = manager.cache.store_last_good

    def _recording(slot, payload, *, ts=None):
        stores.append(slot)
        return real(slot, payload, ts=ts)

    monkeypatch.setattr(manager.cache, "store_last_good", _recording)
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert SLOT_SWARM in stores, "the live slot itself is written every tick"
    assert SLOT_SWARM_JOBS_SEEN not in stores, "an unchanged seen map was re-stored"
    await manager.close()


async def test_a_seen_entry_older_than_48_hours_is_pruned(tmp_path):
    stale_id, fresh_id = "stale-job", "fresh-job"
    prior = {
        stale_id: {"created_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S - 3600.0,
                   "updated_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S - 1.0,
                   "state": "completed", "template": "t", "nodes": []},
        fresh_id: {"created_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S + 60.0,
                   "updated_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S + 60.0,
                   "state": "completed", "template": "t", "nodes": []},
    }
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    manager.cache.store_last_good(SLOT_SWARM_JOBS_SEEN, prior, ts=V2_NOW - 60.0)
    await manager._pool_swarm({TIER_SWARM}, V2_NOW)
    seen = _seen(manager)
    assert stale_id not in seen
    assert fresh_id in seen
    assert len(seen) == 100 + 1
    await manager.close()


async def test_the_seen_slot_holds_the_cap(tmp_path, monkeypatch):
    """Plan WP4 mutation: make the map unbounded and this reddens. The cap is
    read off the module at call time, so the monkeypatch below is what the
    manager sees -- a cap bound as a default argument would not."""
    monkeypatch.setattr(surf_manager_mod, "SWARM_JOBS_SEEN_CAP", 10)
    jobs = _synthetic_jobs(15, start_ts=V2_NOW - 600.0, step_s=10.0)
    swarm = _FakeSwarm(jobs=jobs)
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    await manager._pool_swarm({TIER_SWARM}, V2_NOW)
    seen = _seen(manager)
    assert len(seen) == 10
    assert set(seen) == {f"synthetic-{i:04d}" for i in range(5, 15)}, "the newest must be the ones kept"
    await manager.close()


async def test_a_failed_jobs_read_leaves_the_seen_slot_untouched(tmp_path):
    """Neither tier folds the seen slot on its failure path. The prior entry
    is deliberately *older than the prune age*: a fold that ran on failure
    -- even over an empty read -- would prune it and store the changed map,
    so ``is stored`` (identity, not equality) is what catches it."""
    prior = {"kept": {"created_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S - 3600.0,
                      "updated_ts": V2_NOW - SWARM_JOBS_SEEN_MAX_AGE_S - 3600.0,
                      "state": "completed", "template": "t", "nodes": []}}
    swarm = _FakeSwarm(fail_jobs=True)
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    stored = manager.cache.store_last_good(SLOT_SWARM_JOBS_SEEN, prior, ts=V2_NOW - 60.0)
    result = await manager._pool_swarm({TIER_SWARM}, V2_NOW)
    assert result == {"ok": False, "payload": None}
    assert manager.cache.get_last_good(SLOT_SWARM_JOBS_SEEN) is stored
    result = await manager._pool_swarm_scores({TIER_SWARM_SCORES}, V2_NOW)
    assert result == {"ok": False, "payload": None}
    assert manager.cache.get_last_good(SLOT_SWARM_JOBS_SEEN) is stored
    await manager.close()


async def test_the_slow_sweep_also_folds_the_seen_slot(tmp_path):
    """A1: seat records for jobs the live tier never saw executing enter the
    slot through the sweep's detail read -- the 25 committed details cover
    completed jobs whose nodes the live tier (executing only) never reads."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm, clock=FakeClock(V2_NOW))
    await manager._pool_swarm_scores({TIER_SWARM_SCORES}, V2_NOW)
    seen = _seen(manager)
    assert len(seen) == 100
    with_nodes = {job_id for job_id, e in seen.items() if e["nodes"]}
    assert with_nodes == {k for k in swarm._details if k in seen}
    assert len(with_nodes) == 25
    await manager.close()


async def test_completed_24h_is_none_until_a_day_has_accumulated_then_an_int(tmp_path):
    """R-A through the slot: ``throughput_facts`` off the seen map reads
    ``None`` -- never ``0`` -- while the slot is younger than 24 h, and an
    ``int`` (a real zero counts) once the clock has moved 24 h + 1 s and one
    more tick has folded. The manager's own ``swarm_throughput`` reads this
    slot (``_swarm_keys``, WP7); this proves the slot's own history. The
    clock is injected (``FakeClock``), never slept."""
    clock = FakeClock(V2_NOW)
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm, clock=clock)
    await manager._pool_swarm({TIER_SWARM}, clock())
    jobs = swarm._jobs
    young = sw.throughput_facts(jobs, _seen(manager), now_ts=clock())
    assert young["completed_24h"] is None
    assert young["seen_since_ts"] == min(sw._ts(j["createdAt"]) for j in jobs)

    clock.advance(86_400.0 + 1.0)
    await manager._pool_swarm({TIER_SWARM}, clock())
    aged = sw.throughput_facts(jobs, _seen(manager), now_ts=clock())
    assert isinstance(aged["completed_24h"], int)
    assert aged["completed_24h"] == sum(
        1 for e in _seen(manager).values()
        if e["state"] == "completed" and e["updated_ts"] >= clock() - 86_400.0
    )
    await manager.close()


# ---------------------------------------------------------------------------
# The AGENT seat: the /seats tier (docs/surf_agent_seats_plan.md WP2)
# ---------------------------------------------------------------------------

#: The seat keys the /seats tier feeds -- never another token's values.
_SEAT_READ_KEYS = (
    "swarm_seat_summary", "swarm_seat_work_rows", "swarm_seat_feedback_rows",
    "swarm_seat_as_of_hhmm",
)


async def _seated(tmp_path, swarm, **kw):
    """A manager that has read its selected seat, and the payload after it.

    Cycle 1 spawns the sweep (and, with a saved seat, the seat read); cycle 2
    has a roster, so a most-active seat is chosen and read; cycle 3 serves it.
    Every step awaits the spawned tasks -- observable state, never a sleep.
    """
    manager = _manager(tmp_path, swarm, **kw)
    for _ in range(2):
        await manager.fetch_and_compute()
        await _settle(manager)
    payload = await manager.fetch_and_compute()
    return manager, payload


def _seat_payload_of(token: int) -> dict:
    return swarm_seat_capture(f"seat_{token}")


async def test_the_default_seat_is_the_most_active_and_its_record_is_the_seats_own(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm())
    rows = payload["swarm_seat_rows"]
    assert len(rows) == 16
    assert payload["swarm_seat_selected"] == {
        "token_id": 0, "agent_id": rows[0]["agent_id"], "selected_by": "most_active",
    }
    seat = _seat_payload_of(0)
    assert payload["swarm_seat_state"] == "ok"
    assert payload["swarm_seat_summary"] == sw.seat_summary_from_seat(seat)
    assert payload["swarm_seat_summary"]["reviewed"] == len(seat["reviews"]) == 202
    assert payload["swarm_seat_work_rows"] == sw.seat_work_rows(seat)
    assert payload["swarm_seat_feedback_rows"] == sw.seat_review_rows(seat)
    entry = manager.cache.get_last_good(SLOT_SWARM_SEAT)
    assert payload["swarm_seat_as_of_hhmm"] == entry.as_of_hhmm()
    assert manager.swarm_client.seat_calls == [0], "one seat, the selected one: no fan-out"
    await manager.close()


async def test_the_saved_seat_wins_off_the_roster(tmp_path):
    """D1 (rewrites the ``unseen_token`` test): ``/seats`` answers for any
    paired token, so a saved seat the job window never saw is shown, not
    swapped for the most active. Its ``agent_id`` comes off the payload."""
    assert 420 not in {r["token_id"] for r in sw.seat_rows(swarm_details_v2(), {})}
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420)
    assert payload["swarm_seat_selected"] == {
        "token_id": 420, "agent_id": "50939", "selected_by": "saved",
    }
    summary = payload["swarm_seat_summary"]
    assert (summary["accepted"], summary["attempts"], summary["reviewed"]) == (12, 74, 72)
    assert len(payload["swarm_seat_work_rows"]) == 12
    await manager.close()


async def test_a_saved_seat_given_as_text_parses(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat="420")
    assert payload["swarm_seat_selected"]["token_id"] == 420
    assert payload["swarm_seat_state"] == "ok"
    await manager.close()


async def test_the_retired_seat_env_var_selects_nothing(tmp_path, monkeypatch):
    """``MAXPANE_IMD_SEAT`` is gone (2026-09-21): the saved seat reaches the
    manager only through ``seat=``, so a stale export in a shell profile
    must not quietly pick a seat."""
    monkeypatch.setenv("MAXPANE_IMD_SEAT", "1548")
    manager, payload = await _landed(tmp_path, _FakeSwarm())
    assert payload["swarm_seat_selected"]["selected_by"] == "most_active"
    assert payload["swarm_seat_selected"]["token_id"] == 0
    await manager.close()


async def test_select_seat_moves_the_cursor_and_the_record_follows(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420)
    assert payload["swarm_seat_selected"]["token_id"] == 420
    manager.select_seat(0)
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"] == {
        "token_id": 0, "agent_id": "50906", "selected_by": "cursor",
    }
    assert payload["swarm_seat_summary"] == sw.seat_summary_from_seat(_seat_payload_of(0))
    # The transitional window fold still follows the cursor until WP5.
    assert {r["job_id"] for r in payload["swarm_seat_node_rows"]} <= _seat_of(swarm_details_v2(), 0)
    # A string token parses too -- the DataTable hands the row's text.
    manager.select_seat("1548")
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"]["token_id"] == 1548
    assert payload["swarm_seat_selected"]["selected_by"] == "cursor"
    await manager.close()


async def test_set_seat_replaces_the_saved_seat_and_drops_the_cursor(tmp_path):
    """The seat prompt's seam: the typed seat wins at once -- over a roster
    pick made earlier, which would otherwise keep outranking it."""
    manager, _ = await _seated(tmp_path, _FakeSwarm(), seat=420)
    manager.select_seat(0)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"]["selected_by"] == "cursor"
    manager.set_seat(516)
    assert manager._seat_cursor is None
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"] == {
        "token_id": 516, "agent_id": "50992", "selected_by": "saved",
    }
    assert payload["swarm_seat_summary"]["accepted"] == 4
    await manager.close()


async def test_a_cursor_outside_the_roster_falls_back(tmp_path):
    manager, _ = await _landed(tmp_path, _FakeSwarm(), seat="1548")
    manager.select_seat(999_999)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"]["selected_by"] == "saved"
    assert payload["swarm_seat_selected"]["token_id"] == 1548
    await manager.close()

    manager, _ = await _landed(tmp_path, _FakeSwarm())
    manager.select_seat("not-a-token")
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"]["selected_by"] == "most_active"
    await manager.close()


@pytest.mark.parametrize("method,arg", [("select_seat", 0), ("set_seat", 516)])
async def test_a_seat_switch_marks_the_tier_due_and_awaits_nothing(tmp_path, method, arg):
    """No network await in a message path (CLAUDE.md): a plain function that
    writes attributes and marks the tier due. The read is the next cycle's."""
    manager, _ = await _seated(tmp_path, _FakeSwarm(), seat=420)
    assert not manager.cache.is_due(TIER_SWARM_SEAT, manager._clock())
    switch = getattr(manager, method)
    assert not inspect.iscoroutinefunction(switch)
    calls_before = Counter(manager.swarm_client.calls)
    task_before = manager._swarm_seat_task
    assert switch(arg) is None
    assert manager.swarm_client.calls == calls_before, "the switch made a client call"
    assert manager._swarm_seat_task is task_before, "the switch spawned a read"
    assert manager.cache.is_due(TIER_SWARM_SEAT, manager._clock())
    await manager.close()


async def test_a_switch_while_the_new_seats_read_is_pending_shows_none_of_the_old_seat(tmp_path):
    """A's slot is present and B is selected: every seat key is ``pending`` /
    ``None`` and no value is A's (spec §5, plan §5 "seat switch")."""
    manager, before = await _seated(tmp_path, _FakeSwarm())
    assert before["swarm_seat_selected"]["token_id"] == 0
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT).payload["token"] == 0
    manager.set_seat(420)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"] == {
        "token_id": 420, "agent_id": None, "selected_by": "saved",
    }
    assert payload["swarm_seat_state"] == "pending"
    for key in _SEAT_READ_KEYS:
        assert payload[key] is None, key
        assert before[key] is not None, f"{key}: A had a value to leak"
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_state"] == "ok"
    assert payload["swarm_seat_summary"]["attempts"] == 74
    await manager.close()


async def test_a_selected_seat_with_no_read_finished_is_pending(tmp_path):
    """Cold start with a saved seat: the first payload is ``pending``
    (``Loading…``), never ``None`` (``unavailable``) and never a zero."""
    manager = _manager(tmp_path, _FakeSwarm(), seat=420)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_selected"]["token_id"] == 420
    assert payload["swarm_seat_state"] == "pending"
    for key in _SEAT_READ_KEYS:
        assert payload[key] is None, key
    await manager.close()


async def test_an_unknown_seat_is_a_real_negative(tmp_path):
    """404 ``unknown_seat``: the state, no summary, real-empty rows, and the
    marker of the read that said so (plan §9 L)."""
    manager, payload = await _seated(
        tmp_path, _FakeSwarm(seats={999_999: dict(UNKNOWN_SEAT)}), seat=999_999,
    )
    assert payload["swarm_seat_selected"] == {
        "token_id": 999_999, "agent_id": None, "selected_by": "saved",
    }
    assert payload["swarm_seat_state"] == "unknown_seat"
    assert payload["swarm_seat_summary"] is None
    assert payload["swarm_seat_work_rows"] == []
    assert payload["swarm_seat_feedback_rows"] == []
    assert payload["swarm_seat_as_of_hhmm"] is not None
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT).payload == {
        "token": 999_999, "state": "unknown_seat", "seat": None,
    }
    await manager.close()


async def test_a_failed_read_with_a_last_good_for_the_same_seat_serves_it(tmp_path):
    clock = FakeClock(NOW)
    swarm = _FakeSwarm()
    manager, good = await _seated(tmp_path, swarm, seat=420, clock=clock)
    as_of = good["swarm_seat_as_of_hhmm"]
    assert good["swarm_seat_state"] == "ok" and as_of is not None
    swarm.seats[420] = None                       # every host failed
    clock.advance(121.0)
    await manager.fetch_and_compute()
    await _settle(manager)
    assert swarm.seat_calls == [420, 420], "the second read happened and failed"
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_state"] == "ok"
    for key in _SEAT_READ_KEYS:
        assert payload[key] == good[key], key
    assert payload["swarm_seat_as_of_hhmm"] == as_of
    await manager.close()


async def test_a_failed_read_with_no_last_good_is_none_never_zero(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm(seats={420: None}), seat=420)
    assert manager.swarm_client.seat_calls == [420]
    assert payload["swarm_seat_selected"]["token_id"] == 420
    assert payload["swarm_seat_state"] is None
    for key in _SEAT_READ_KEYS:
        assert payload[key] is None, key
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT) is None
    await manager.close()


async def test_a_failed_read_of_b_under_a_slot_for_a_is_none_not_pending(tmp_path):
    """The failure is remembered per token: B's read failed and B has no
    last-good, so B is ``unavailable`` even though A's slot is present."""
    swarm = _FakeSwarm(seats={516: None})
    manager, _ = await _seated(tmp_path, swarm, seat=420)
    manager.set_seat(516)
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert swarm.seat_calls == [420, 516]
    assert payload["swarm_seat_selected"]["token_id"] == 516
    assert payload["swarm_seat_state"] is None
    for key in _SEAT_READ_KEYS:
        assert payload[key] is None, key
    # Switching to B again is a new read in flight: pending, not unavailable.
    manager.set_seat(516)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_state"] == "pending"
    await manager.close()


async def test_a_400_is_a_failed_read_and_backs_the_tier_off(tmp_path):
    """The client turns ``400 invalid_request`` into ``None``; the manager
    marks the tier failed (120 s) and publishes ``None``."""
    clock = FakeClock(NOW)
    swarm = _FakeSwarm(seats={420: None})
    manager, payload = await _seated(tmp_path, swarm, seat=420, clock=clock)
    assert payload["swarm_seat_state"] is None
    assert not manager.cache.is_due(TIER_SWARM_SEAT, clock() + 60.0)
    assert manager.cache.is_due(TIER_SWARM_SEAT, clock() + 121.0)
    await manager.fetch_and_compute()
    assert swarm.seat_calls == [420], "the backoff held: no retry inside 120 s"
    await manager.close()


async def test_a_payload_for_another_token_is_a_failed_read(tmp_path):
    """A ``tokenId`` mismatch (seat A's record answering for B) is ``None``."""
    swarm = _FakeSwarm(seats={420: _seat_payload_of(516)})
    manager, payload = await _seated(tmp_path, swarm, seat=420)
    assert payload["swarm_seat_state"] is None
    assert payload["swarm_seat_summary"] is None
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT) is None
    await manager.close()


async def test_queued_reviews_carry_no_tx_chain_or_sent_time(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420)
    queued = [r for r in payload["swarm_seat_feedback_rows"] if r["status"] == "queued"]
    assert len(queued) == 1
    assert (queued[0]["tx_hash"], queued[0]["chain_id"], queued[0]["sent_ts"]) == (None, None, None)
    assert payload["swarm_seat_summary"]["review_status"] == {"sent": 66, "submitted": 5, "queued": 1}
    await manager.close()


async def test_one_seat_read_per_cycle_and_a_token_change_cancels_the_old_one(tmp_path):
    gate = asyncio.Event()
    swarm = _FakeSwarm(seat_gate=gate)
    manager = _manager(tmp_path, swarm, seat=420)
    await manager.fetch_and_compute()
    first = manager._swarm_seat_task
    assert first is not None
    await swarm.seat_entered.wait()
    await manager.fetch_and_compute()
    assert manager._swarm_seat_task is first, "a second read stacked behind the first"
    assert swarm.seat_calls == [420]

    manager.set_seat(516)
    await manager.fetch_and_compute()
    assert first.cancelled(), "the old seat's read was not cancelled"
    second = manager._swarm_seat_task
    assert second is not first and second is not None
    gate.set()
    await second
    assert swarm.seat_calls == [420, 516]
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT).payload["token"] == 516
    await manager.close()


async def test_a_seat_other_than_the_slots_is_read_without_waiting_for_the_ttl(tmp_path):
    """The selection moved without a switch (the most active seat changed, or
    a restored slot names another seat): the tier is fresh, but the selected
    seat has no read yet, so it is read now rather than after 120 s."""
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm, seat=420)
    now = manager._clock()
    manager.cache.store_last_good(
        SLOT_SWARM_SEAT, {"token": 516, "state": "ok", "seat": _seat_payload_of(516)}, ts=now,
    )
    manager.cache.mark_fetched(TIER_SWARM_SEAT, now)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_state"] == "pending"
    await _settle(manager)
    assert swarm.seat_calls == [420]
    await manager.close()


async def test_close_cancels_an_in_flight_seat_read(tmp_path):
    swarm = _FakeSwarm(seat_gate=asyncio.Event())
    manager = _manager(tmp_path, swarm, seat=420)
    await manager.fetch_and_compute()
    task = manager._swarm_seat_task
    await swarm.seat_entered.wait()
    await manager.close()
    assert task.cancelled()
    assert manager._swarm_seat_task is None


async def test_a_sweep_that_never_ran_publishes_none_for_every_roster_key(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert manager.cache.get_last_good(SLOT_SWARM_SCORES) is None
    assert payload["swarm_as_of_hhmm"] is not None, "the live tier ran; the sweep did not"
    for key in _SEAT_KEYS + ("swarm_roster_window", "swarm_seat_work_rows", "swarm_seat_state"):
        assert payload[key] is None, key
    assert manager.swarm_client.seat_calls == [], "no seat selected, nothing to read"
    await manager.close()


async def test_a_saved_seat_is_served_with_no_sweep_at_all(tmp_path):
    """The seat tier is independent of the sweep (rewrites the meaning of the
    test above for a saved seat): no roster, but the seat's own record."""
    manager = _manager(tmp_path, _FakeSwarm(), seat=420)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    await _settle(manager)
    payload = await manager.fetch_and_compute()
    assert manager.cache.get_last_good(SLOT_SWARM_SCORES) is None
    assert payload["swarm_seat_rows"] is None
    assert payload["swarm_roster_window"] is None
    assert payload["swarm_seat_selected"] == {
        "token_id": 420, "agent_id": "50939", "selected_by": "saved",
    }
    assert payload["swarm_seat_state"] == "ok"
    assert payload["swarm_seat_summary"]["accepted"] == 12
    await manager.close()


async def test_a_sweep_with_no_seat_publishes_an_empty_roster_and_no_selection(tmp_path):
    seatless = {
        job_id: dict(d, nodes=[dict(n, seat=None) for n in d.get("nodes") or []])
        for job_id, d in swarm_details_v2().items()
    }
    manager, payload = await _landed(tmp_path, _FakeSwarm(details=seatless))
    assert payload["swarm_scores_as_of_hhmm"] is not None, "the sweep ran"
    assert payload["swarm_seat_rows"] == []
    assert payload["swarm_seat_selected"] is None
    for key in _SEAT_READ_KEYS + ("swarm_seat_node_rows", "swarm_seat_state"):
        assert payload[key] is None, key
    await manager.close()


async def test_the_roster_window_is_the_sweeps_job_list(tmp_path):
    manager, payload = await _landed(tmp_path, _FakeSwarm())
    jobs = manager.cache.get_last_good(SLOT_SWARM_SCORES).payload["jobs"]
    assert payload["swarm_roster_window"] == sw.roster_window(jobs)
    assert payload["swarm_roster_window"]["jobs"] == 100
    await manager.close()


async def test_a_hand_edited_seat_slot_is_not_served(tmp_path):
    """A persisted slot is third-party input: a bool token is refused whole,
    so the seat is ``pending`` until its own read lands."""
    path = tmp_path / "surf.json"
    seed = _manager(tmp_path, _FakeSwarm(), seat=420)
    seed.cache.store_last_good(
        SLOT_SWARM_SEAT, {"token": True, "state": "ok", "seat": _seat_payload_of(420)},
        ts=seed._clock(),
    )
    seed.cache.save()
    await seed.close()
    assert path.exists()
    manager = _manager(tmp_path, _FakeSwarm(), seat=420)
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_state"] == "pending"
    for key in _SEAT_READ_KEYS:
        assert payload[key] is None, key
    await manager.close()


# ---------------------------------------------------------------------------
# Contract and degradation
# ---------------------------------------------------------------------------


async def test_a_failed_swarm_read_names_no_degraded_group(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm(fail=True))
    payload = await manager.fetch_and_compute()
    await asyncio.gather(manager._swarm_task, return_exceptions=True)
    payload = await manager.fetch_and_compute()
    assert "swarm" not in payload["degraded"]
    assert all(not g.startswith("swarm") for g in payload["degraded"])
    await manager.close()


async def test_the_payload_is_exactly_the_contract_with_or_without_the_swarm(tmp_path):
    for swarm in (_FakeSwarm(), _FakeSwarm(fail=True)):
        manager = _manager(tmp_path, swarm)
        payload = await manager.fetch_and_compute()
        assert set(payload) == set(SURF_KEYS)
        await _settle(manager)
        payload = await manager.fetch_and_compute()
        assert set(payload) == set(SURF_KEYS)
        await manager.close()


async def test_the_swarm_keys_are_filled_from_the_slot(tmp_path):
    """Re-pinned on the v2 corpus (WP7): 28 connected daemons; two IN FLIGHT
    rows -- both executing jobs, the one with a committed detail carrying its
    node and the one whose detail is a 404 carrying ``None`` node fields (a
    404 drops the detail, never the row or the read); a THROUGHPUT dict over
    the whole hundred-job list."""
    manager, payload = await _landed(tmp_path, _FakeSwarm())
    assert payload["swarm_agents_online"] == swarm_capture_v2("health")["connectedDaemons"] == 28
    rows = payload["swarm_inflight_rows"]
    assert len(rows) == 2
    assert sorted(r["node_key"] is None for r in rows) == [False, True]
    assert payload["swarm_throughput"]["window_n"] == 100
    assert payload["swarm_queue_total"] == 45          # health.json pendingFeedback
    assert payload["swarm_as_of_hhmm"], "no marker published"
    await manager.close()


async def test_the_three_swarm_methods_emit_exactly_the_swarm_block(tmp_path):
    """WP7: ``_swarm_keys`` + ``_swarm_scores_keys`` + ``_swarm_seat_keys``
    publish the ``SWARM_KEYS`` block and nothing else, each key from exactly
    one of them. ``_finalise`` drops a key outside ``SURF_KEYS`` with only a
    log line, so a retired key quietly re-emitted here would never reach the
    payload test above -- this is the test that sees it."""
    manager, _ = await _landed(tmp_path, _FakeSwarm())
    live = manager.cache.get_last_good(SLOT_SWARM)
    scores = manager.cache.get_last_good(SLOT_SWARM_SCORES)
    seen = _seen(manager)
    assert live is not None and scores is not None
    parts = [
        manager._swarm_keys(live.payload, live, manager._clock(), seen),
        manager._swarm_scores_keys(scores.payload, scores, live, manager._clock()),
        manager._swarm_seat_keys(
            scores.payload, scores, seen, manager.cache.get_last_good(SLOT_SWARM_SEAT),
        ),
    ]
    emitted = Counter(k for part in parts for k in part)
    assert set(emitted) == set(SWARM_KEYS), (
        sorted(set(emitted) ^ set(SWARM_KEYS))
    )
    assert all(n == 1 for n in emitted.values()), (
        sorted(k for k, n in emitted.items() if n > 1)
    )
    await manager.close()


async def test_a_manager_built_without_a_swarm_client_owns_a_real_one(tmp_path) -> None:
    """F-D. The default mirrors ``client``'s and ``pool4_client``'s own: a
    manager built with nothing for this argument gets the real, keyless
    ``SwarmClient`` -- which is exactly why every helper in this suite
    injects a double, and why that is asserted here rather than assumed."""
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient

    manager = SurfManager(
        cache_path=str(tmp_path / "surf_cache.json"),
        client=FakeSurfClient(),
        pool4_client=FakePool4Client(),
        clock=FakeClock(NOW),
    )
    assert isinstance(manager.swarm_client, SwarmClient)
    await manager.swarm_client.close()
