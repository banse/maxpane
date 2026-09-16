"""Task 5 — wiring the swarm's two refresh tiers into SurfManager.

Zero network, structurally: the surf and pool4 clients are the established
doubles from ``test_surf_manager``/``test_surf_manager_pool4`` (the surf
double's transport is a :class:`~tests.data.test_surf_manager.DeadTransport`
that raises on any use), and the swarm client is the fake given below —
the real :class:`~maxpane_dashboard.data.surf_swarm_client.SwarmClient` is
never constructed in this file. The clock is a fake too, so every "N seconds
later" in these tests is exact rather than a race against wall time.
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
    """Serves the committed captures and counts what was asked for."""

    def __init__(self, *, jobs=None, health=None, fail=False):
        self.health_calls = 0
        self.job_calls = 0
        self.detail_calls: list[str] = []
        self._jobs = swarm_capture("jobs")["jobs"] if jobs is None else jobs
        self._health = swarm_capture("health") if health is None else health
        self._fail = fail

    async def fetch_health(self):
        self.health_calls += 1
        return None if self._fail else dict(self._health)

    async def fetch_jobs(self):
        self.job_calls += 1
        return None if self._fail else list(self._jobs)

    async def fetch_job(self, job_id):
        self.detail_calls.append(job_id)
        for name in ("job_executing", "job_blocked", "job_completed"):
            job = swarm_capture(name)
            if job["id"] == job_id:
                return job
        return swarm_capture("job_executing")

    async def fetch_launches(self):
        return swarm_capture("launches")["launches"]

    async def fetch_sites(self):
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


async def test_only_one_swarm_sweep_is_ever_in_flight(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    await manager.fetch_and_compute()
    first = manager._swarm_task
    await manager.fetch_and_compute()
    assert manager._swarm_task is first
    await manager.close()


async def test_details_are_fetched_only_for_unfinished_jobs(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    unfinished = {j["id"] for j in swarm._jobs if j["state"] not in ("completed", "cancelled")}
    assert set(swarm.detail_calls) == unfinished
    assert len(swarm.detail_calls) < len(swarm._jobs)
    await manager.close()


async def test_the_job_list_is_not_re_read_when_no_counter_moved(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    manager.cache.mark_failed(TIER_SWARM, now=0.0)  # make it due again
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.health_calls == 2
    assert swarm.job_calls == 1, "the list was paid for twice with nothing moved"
    await manager.close()


async def test_a_moved_counter_forces_the_list(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    swarm._health = dict(swarm._health, acceptedLastDay=swarm._health["acceptedLastDay"] + 1)
    await manager._pool_swarm({TIER_SWARM}, manager._clock() + 61.0)
    assert swarm.job_calls == 2
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
