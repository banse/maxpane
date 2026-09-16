"""Task 5 — wiring the swarm's two refresh tiers into SurfManager.

Zero network, structurally: the surf and pool4 clients are the established
doubles from ``test_surf_manager``/``test_surf_manager_pool4`` (the surf
double's transport is a :class:`~tests.data.test_surf_manager.DeadTransport`
that raises on any use), and the swarm client is the fake given below —
the real :class:`~maxpane_dashboard.data.surf_swarm_client.SwarmClient` is
never constructed in this file. The clock is a fake too, so every "N seconds
later" in these tests is exact rather than a race against wall time.

Fix round 1 (controller-mandated, finding 1): the two swarm tiers are spawned
independently, with no gate between them, so both are typically due — and
both spawned — on a cold cycle. ``_FakeSwarm``'s methods each carry a real
``await asyncio.sleep(0)`` suspension point so the two spawned tasks
genuinely interleave the way real I/O would, rather than one running to
completion before the other is ever given a turn (an artifact of the
original all-synchronous fake). Tests that need to isolate one tier's own
work assert against that tier's own stored slot or against a call-count
*delta*, never against the shared call log's absolute value or its ordering.
"""
from __future__ import annotations

import asyncio

import pytest

from maxpane_dashboard.data.surf_cache import (
    SLOT_SWARM, SLOT_SWARM_SCORES, TIER_SWARM, TIER_SWARM_SCORES,
)
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.surf_models import SURF_KEYS
from tests.data.test_surf_manager import FakeClock, FakeSurfClient, NOW
from tests.data.test_surf_manager_pool4 import FakePool4Client
from tests.surf_swarm_fixtures import swarm_capture


class _FakeSwarm:
    """Serves the committed captures and counts what was asked for.

    Each method carries a real ``await asyncio.sleep(0)`` — fix round 1
    finding 1 — so two concurrently-spawned tasks against this fake actually
    interleave, matching real I/O, instead of one running to full completion
    before the other is ever scheduled.
    """

    def __init__(self, *, jobs=None, health=None, fail=False, fail_jobs=False):
        self.health_calls = 0
        self.job_calls = 0
        self.detail_calls: list[str] = []
        self._jobs = swarm_capture("jobs")["jobs"] if jobs is None else jobs
        self._health = swarm_capture("health") if health is None else health
        self._fail = fail
        #: Fails only ``/jobs``, leaving ``/health`` answering normally --
        #: distinct from ``fail`` (fix round 1 finding 2's own test needs a
        #: successful ``/health`` with a moved counter and a failing
        #: ``fetch_jobs``, which ``fail=True`` cannot produce since
        #: ``_pool_swarm`` returns before ever reaching ``fetch_jobs`` when
        #: ``/health`` itself fails).
        self._fail_jobs = fail_jobs

    async def fetch_health(self):
        await asyncio.sleep(0)
        self.health_calls += 1
        return None if self._fail else dict(self._health)

    async def fetch_jobs(self):
        await asyncio.sleep(0)
        self.job_calls += 1
        return None if (self._fail or self._fail_jobs) else list(self._jobs)

    async def fetch_job(self, job_id):
        await asyncio.sleep(0)
        self.detail_calls.append(job_id)
        for name in ("job_executing", "job_blocked", "job_completed"):
            job = swarm_capture(name)
            if job["id"] == job_id:
                return job
        return swarm_capture("job_executing")

    async def fetch_launches(self):
        await asyncio.sleep(0)
        return swarm_capture("launches")["launches"]

    async def fetch_sites(self):
        await asyncio.sleep(0)
        return swarm_capture("sites")["sites"]

    async def close(self):
        return None


def _manager(tmp_path, swarm, **kw) -> SurfManager:
    """:class:`SurfManager` wired to structurally network-dead doubles.

    The brief's own helper passed only ``swarm_client=``, which would leave
    ``client``/``pool4_client`` at their real-network defaults
    (``SurfClient()``/``Pool4Client()``) — exactly what CLAUDE.md's "no test
    may touch the network" and this task's own rules forbid. Every other
    manager test file in this package (``test_surf_manager_pool4.py``,
    ``test_surf_manager_pool4_market.py``) defaults those two to
    ``FakeSurfClient()``/``FakePool4Client()`` for the same reason, so this
    helper does too. The clock defaults to a fixed :class:`FakeClock` rather
    than real ``time.time`` for the same determinism reason those files use
    one — this file's counter-gate tests reason about "61 seconds later" and
    must not depend on how fast the test process actually runs.
    """
    kw.setdefault("client", FakeSurfClient())
    kw.setdefault("pool4_client", FakePool4Client())
    kw.setdefault("clock", FakeClock(NOW))
    return SurfManager(cache_path=tmp_path / "surf.json", swarm_client=swarm, **kw)


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

    An earlier version of ``_spawn_swarm_scores`` also refused to start
    while ``self._swarm_task`` existed and was not yet done. Because the two
    spawns happen back to back with no ``await`` between them, that check
    was deterministically ``False`` whenever both tiers were due together --
    not a race that sometimes went the other way -- so at a poll interval of
    60 s or more (legal: ``__main__.py`` enforces only a minimum of 5, no
    maximum) the live tier was due on every cycle and the scores sweep never
    ran at all. A live read that never completes (``_Slow``, a real
    ``asyncio.sleep(30)``) reproduces "the live tier is due and in flight"
    on every cycle without needing to wait 60 real seconds or advance a
    clock: the scores sweep must still be spawned and must still be able to
    finish.
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
    """Fix round 1 finding 5.

    The original version of this test used a plain ``_FakeSwarm()``, whose
    read completes inside the very first cycle (the fake had no real
    suspension point at the time). With the clock frozen at ``NOW``, that
    left ``TIER_SWARM`` not due on the second call — ``_spawn_swarm``
    returned at the tier check and never reached the "already running"
    guard, so deleting that guard did not redden the test. A live read that
    never completes (``_Slow``, real ``asyncio.sleep(30)``) is due on every
    cycle (``mark_fetched``/``mark_failed`` never run) and never finishes
    (``.done()`` stays ``False``), which is what actually exercises the
    guard: the tier is due both times *and* the previous task is genuinely
    still in flight both times.
    """
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


async def test_details_are_fetched_only_for_unfinished_jobs(tmp_path):
    """Fix round 1 finding 1: keep the scores tier out of the way.

    With the cross-tier gate removed, the scores sweep is typically due (and
    spawned) in the same cold-cache cycle, and it fetches every job's own
    detail through the same shared client — so the raw call log
    (``swarm.detail_calls``) would reflect both tiers' work, not just the
    live tier's, if both ran. This test is specifically about the live
    tier's own "unfinished only" rule, so ``TIER_SWARM_SCORES`` is marked
    already-fetched before the cycle runs, keeping the scores tier from
    spawning at all here. Their genuine independence (both due, both
    spawned, both making progress) is covered separately by the tests that
    exercise it directly (the counter-gate tests below, and
    ``test_only_one_swarm_sweep_is_ever_in_flight``).
    """
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    manager.cache.mark_fetched(TIER_SWARM_SCORES, manager._clock())
    await manager.fetch_and_compute()
    assert manager._swarm_scores_task is None, "the scores tier must not have been due"
    await manager._swarm_task
    unfinished = {j["id"] for j in swarm._jobs if j["state"] not in ("completed", "cancelled")}
    assert set(swarm.detail_calls) == unfinished
    assert len(swarm.detail_calls) < len(swarm._jobs)
    await manager.close()


async def test_the_job_list_is_not_re_read_when_no_counter_moved(tmp_path):
    """Fix round 1 finding 1: assert on the *delta* the direct call caused.

    The first ``fetch_and_compute()`` now typically spawns both tiers, and
    the scores sweep also calls ``fetch_jobs()`` once on its own — so the
    absolute call count after cycle 1 is no longer just the live tier's.
    Capturing the count *after* both tiers have settled, then asserting on
    how much the explicit second read (bypassing ``_cycle``/spawning
    entirely) added, isolates exactly what this test is about: whether that
    one direct read paid for the list again.
    """
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    if manager._swarm_scores_task is not None:
        await manager._swarm_scores_task
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
    await manager._swarm_task
    if manager._swarm_scores_task is not None:
        await manager._swarm_scores_task
    jobs_before = swarm.job_calls
    swarm._health = dict(swarm._health, acceptedLastDay=swarm._health["acceptedLastDay"] + 1)
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == jobs_before + 1
    await manager.close()


async def test_a_failed_read_leaves_the_counter_gate_armed(tmp_path):
    """Fix round 1 finding 2.

    ``self._swarm_counters`` used to be set unconditionally after a
    re-fetch *attempt*, including a failed one — so a counter move followed
    by a failed ``fetch_jobs`` would still "remember" the new counters, and
    the next cycle's unchanged counters would compare equal and skip the
    retry, leaving the list permanently stale behind a gate that believed it
    was current. Moving the assignment inside the successful-fetch branch
    means a failed attempt leaves the gate armed: the next read, even with
    the same counters, must try again because ``_swarm_counters`` still
    reflects the last *successful* read, not the last attempt.
    """
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    if manager._swarm_scores_task is not None:
        await manager._swarm_scores_task

    # ``fail_jobs``, not ``fail``: this scenario needs ``/health`` to keep
    # answering (with a moved counter) while only ``/jobs`` fails.
    # ``_pool_swarm`` returns before ever reaching ``fetch_jobs`` when
    # ``/health`` itself fails, so ``fail=True`` could not exercise this.
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


async def test_a_real_zero_publishes_as_zero_not_none(tmp_path):
    """Fix round 1 finding 3: a successful read with nothing in a state
    publishes ``0``, never ``None`` — only a list that was never read does.
    """
    all_completed = [dict(j, state="completed") for j in swarm_capture("jobs")["jobs"][:5]]
    swarm = _FakeSwarm(jobs=all_completed)
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    payload = await manager.fetch_and_compute()
    assert payload["swarm_jobs_in_flight"] == 0
    assert payload["swarm_jobs_blocked"] == 0
    await manager.close()


async def test_an_unread_list_still_publishes_none(tmp_path):
    """Fix round 1 finding 3's other half: an unread list is still ``None``."""
    manager = _manager(tmp_path, _FakeSwarm(fail=True))
    payload = await manager.fetch_and_compute()
    assert payload["swarm_jobs_in_flight"] is None
    assert payload["swarm_jobs_blocked"] is None
    await manager.close()


async def test_the_sweep_publishes_whole_rows_even_with_no_live_slot(tmp_path):
    """Fix round 1 finding 4.

    ``shipped_rows``/``throughput`` used to be sourced from the *live*
    slot's ``jobs`` at publish time, so an empty or cold live slot would
    silently blank the sweep panel's rows even when the sweep's own read was
    complete and fine. They now come off the sweep's own stored ``jobs``,
    so a populated sweep slot publishes whole rows regardless of whether the
    live tier has ever run.
    """
    jobs = swarm_capture("jobs")["jobs"]
    launches = swarm_capture("launches")["launches"]
    sites = swarm_capture("sites")["sites"]
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
    assert keys["swarm_shipped_rows"], "no shipped rows with a whole sweep slot"
    assert keys["swarm_throughput"]["accepted_per_day"] is not None
    await manager.close()


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
        await manager.close()


async def test_the_swarm_keys_are_filled_from_the_slot(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    await manager.fetch_and_compute()
    await manager._swarm_task
    payload = await manager.fetch_and_compute()
    assert payload["swarm_agents_online"] == swarm_capture("health")["connectedDaemons"]
    assert payload["swarm_field_rows"], "no field rows published"
    assert payload["swarm_queue_rows"], "no queue rows published"
    assert payload["swarm_as_of_hhmm"], "no marker published"
    await manager.close()
