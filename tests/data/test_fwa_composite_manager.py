"""Concurrency contract for the FWA umbrella manager."""

from __future__ import annotations

import asyncio

from maxpane_dashboard.data.fwa_composite_manager import FWACompositeManager
from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    FWA_UMBRELLA_DATA_KEYS,
)
from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS


def _pulls_payload(marker: object = "pulls") -> dict:
    payload = dict.fromkeys(FWA_DATA_KEYS)
    payload[FWA_DATA_KEYS[0]] = marker
    return payload


def _network_payload(marker: object = "network") -> dict:
    payload = dict.fromkeys(FWA_NETWORK_DATA_KEYS)
    payload[FWA_NETWORK_DATA_KEYS[0]] = marker
    return payload


class _Pulls:
    def __init__(self, payload=None, *, error: Exception | None = None) -> None:
        self.payload = _pulls_payload() if payload is None else payload
        self.error = error
        self.calls = 0
        self.close_calls = 0
        self._error_count = 2

    async def fetch_and_compute(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.payload

    async def close(self):
        self.close_calls += 1


class _Network:
    def __init__(self, fetch) -> None:
        self._fetch = fetch
        self.calls = 0
        self.close_calls = 0
        self._error_count = 3

    async def fetch_and_compute(self):
        self.calls += 1
        return await self._fetch()

    async def close(self):
        self.close_calls += 1


async def test_never_finishing_network_cannot_delay_pulls() -> None:
    never = asyncio.Event()

    async def hang():
        await never.wait()
        return _network_payload()

    pulls = _Pulls()
    network = _Network(hang)
    manager = FWACompositeManager(
        pulls_manager=pulls,
        ecosystem_manager=network,
    )

    data = await asyncio.wait_for(manager.fetch_and_compute(), timeout=0.1)

    assert tuple(data) == FWA_UMBRELLA_DATA_KEYS
    assert data[FWA_DATA_KEYS[0]] == "pulls"
    assert all(data[key] is None for key in FWA_NETWORK_DATA_KEYS)
    assert pulls.calls == 1
    await asyncio.sleep(0)
    assert network.calls == 1
    await manager.close()


async def test_repeated_ticks_reuse_one_unfinished_network_task() -> None:
    never = asyncio.Event()

    async def hang():
        await never.wait()
        return _network_payload()

    network = _Network(hang)
    manager = FWACompositeManager(
        pulls_manager=_Pulls(),
        ecosystem_manager=network,
    )

    await manager.fetch_and_compute()
    await asyncio.sleep(0)
    await manager.fetch_and_compute()
    await asyncio.sleep(0)
    await manager.fetch_and_compute()

    assert network.calls == 1
    await manager.close()


async def test_network_that_finishes_before_pulls_is_harvested_atomically() -> None:
    release_pulls = asyncio.Event()

    class GatedPulls(_Pulls):
        async def fetch_and_compute(self):
            self.calls += 1
            await release_pulls.wait()
            return self.payload

    async def ready():
        return _network_payload("ready")

    manager = FWACompositeManager(
        pulls_manager=GatedPulls(),
        ecosystem_manager=_Network(ready),
    )
    refresh = asyncio.create_task(manager.fetch_and_compute())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not refresh.done()

    release_pulls.set()
    data = await refresh

    assert data[FWA_NETWORK_DATA_KEYS[0]] == "ready"
    assert tuple(data) == FWA_UMBRELLA_DATA_KEYS
    await manager.close()


async def test_completed_snapshot_is_reused_while_next_refresh_runs() -> None:
    first_done = asyncio.Event()
    second_never = asyncio.Event()

    async def sequence():
        if network.calls == 1:
            first_done.set()
            return _network_payload("last-good")
        await second_never.wait()
        return _network_payload("new")

    network = _Network(sequence)
    manager = FWACompositeManager(
        pulls_manager=_Pulls(),
        ecosystem_manager=network,
    )

    first = await manager.fetch_and_compute()
    assert first[FWA_NETWORK_DATA_KEYS[0]] is None
    await first_done.wait()
    second = await manager.fetch_and_compute()
    await asyncio.sleep(0)

    assert second[FWA_NETWORK_DATA_KEYS[0]] == "last-good"
    assert network.calls == 2
    await manager.close()


async def test_failed_or_malformed_network_never_replaces_last_good() -> None:
    outcomes = [
        _network_payload("good"),
        {**_network_payload("bad"), "unexpected": 1},
        RuntimeError("rpc down"),
    ]

    async def sequence():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    manager = FWACompositeManager(
        pulls_manager=_Pulls(),
        ecosystem_manager=_Network(sequence),
    )

    assert (await manager.fetch_and_compute())[FWA_NETWORK_DATA_KEYS[0]] is None
    await asyncio.sleep(0)
    assert (await manager.fetch_and_compute())[FWA_NETWORK_DATA_KEYS[0]] == "good"
    await asyncio.sleep(0)
    assert (await manager.fetch_and_compute())[FWA_NETWORK_DATA_KEYS[0]] == "good"
    await asyncio.sleep(0)
    assert (await manager.fetch_and_compute())[FWA_NETWORK_DATA_KEYS[0]] == "good"
    await manager.close()


async def test_pulls_failure_and_unknown_keys_still_return_exact_contract() -> None:
    async def hang():
        await asyncio.Event().wait()

    manager = FWACompositeManager(
        pulls_manager=_Pulls(error=RuntimeError("pulls down")),
        ecosystem_manager=_Network(hang),
    )

    data = await manager.fetch_and_compute()

    assert tuple(data) == FWA_UMBRELLA_DATA_KEYS
    assert all(data[key] is None for key in FWA_DATA_KEYS)
    await manager.close()


async def test_close_cancels_task_and_closes_each_child_once() -> None:
    cancelled = asyncio.Event()

    async def hang():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    pulls = _Pulls()
    network = _Network(hang)
    manager = FWACompositeManager(
        pulls_manager=pulls,
        ecosystem_manager=network,
    )
    await manager.fetch_and_compute()
    await asyncio.sleep(0)

    await manager.close()
    await manager.close()

    assert cancelled.is_set()
    assert pulls.close_calls == 1
    assert network.close_calls == 1
    assert manager._network_task is None
    assert manager._error_count == 5
