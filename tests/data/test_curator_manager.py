"""WP5 — ``CuratorManager``: tiers, decoders, readings and the flat contract.

Every test drives a fake client and an injected clock.  No socket is opened and
nothing sleeps: the fakes are plain objects whose coroutines return committed
fixture data or ``None``.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data import curator_manager
from maxpane_dashboard.data.curator_cache import (
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    CuratorCache,
)
from maxpane_dashboard.data.curator_manager import (
    GROUP_SLOT,
    SOURCES,
    SOURCE_LOGS,
    SOURCE_STATE,
    SOURCE_WALLET,
    CuratorManager,
)
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CuratorState,
)

NOW = 1_786_968_000.0


class Clock:
    def __init__(self, start: float = NOW) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


class FakeClient:
    """A client double: every coroutine answers from what the test set.

    It carries the six degradation attributes the real client exposes, so the
    manager reads them exactly as it would in production.
    """

    def __init__(self, **answers) -> None:
        self.answers = answers
        self.calls: list[tuple] = []
        self.closed = False
        self.state_failed = False
        self.config_failed = False
        self.logs_failed = False
        self.wallet_failed = False
        self.blockscout_truncated = False
        self.log_group_failed = {
            g: False
            for g in (
                "deposits",
                "first_deposits",
                "hour_saved",
                "settled",
                "rescued",
                "launched",
            )
        }

    def _answer(self, name, *args):
        self.calls.append((name, *args))
        value = self.answers.get(name)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(*args)
        return value

    async def fetch_state(self):
        return self._answer("fetch_state")

    async def fetch_config(self):
        return self._answer("fetch_config")

    async def fetch_balance(self):
        return self._answer("fetch_balance")

    async def fetch_wallet(self, address):
        return self._answer("fetch_wallet", address)

    async def fetch_logs(self, from_block, to_block="latest"):
        return self._answer("fetch_logs", from_block, to_block)

    async def fetch_block_timestamps(self, block_numbers):
        return self._answer("fetch_block_timestamps", tuple(block_numbers)) or {}

    async def fetch_blockscout_logs(self, max_pages=400):
        return self._answer("fetch_blockscout_logs", max_pages)

    async def close(self):
        self.closed = True
        value = self.answers.get("close")
        if isinstance(value, Exception):
            raise value


def _manager(tmp_path, clock, client=None, **kwargs) -> CuratorManager:
    return CuratorManager(
        client=client if client is not None else FakeClient(),
        cache=CuratorCache(path=str(tmp_path / "curator_cache.json"), clock=clock),
        clock=clock,
        **kwargs,
    )


@pytest.fixture()
def clock() -> Clock:
    return Clock()


# ---------------------------------------------------------------------------
# WP5.7 — the skeleton, the sources and the degradation surface
# ---------------------------------------------------------------------------


def test_sources_are_the_frozen_degraded_vocabulary():
    """The title bar renders these verbatim, so an invented fourth name
    ("rpc", "config") reaches the user as-is."""
    assert SOURCES == CURATOR_DEGRADED_GROUPS
    assert set(GROUP_SLOT) == set(SOURCES)


def test_degraded_is_a_sorted_list_drawn_only_from_sources(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    degraded = manager._degraded()
    assert degraded == sorted(degraded)
    assert set(degraded) <= set(SOURCES)


def test_a_group_that_never_produced_a_payload_is_degraded(tmp_path, clock):
    manager = _manager(tmp_path, clock, wallet="0x" + "ab" * 20)
    assert manager._degraded() == sorted(SOURCES)

    manager.cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)
    manager.cache.store_last_good(SLOT_LOGS, {"deposits": 3}, ts=NOW)
    manager.cache.store_last_good(SLOT_WALLET, {"points": 1}, ts=NOW)
    assert manager._degraded() == []


def test_with_no_wallet_configured_the_wallet_group_is_never_degraded(tmp_path, clock):
    """Nothing was attempted and nothing is wrong: every you_* key is None
    because there is nobody to ask about, not because a source died."""
    manager = _manager(tmp_path, clock)
    manager.cache.store_last_good(SLOT_STATE, {"a": 1}, ts=NOW)
    manager.cache.store_last_good(SLOT_LOGS, {"b": 2}, ts=NOW)
    assert manager._degraded() == []

    manager.client.wallet_failed = True
    assert manager._degraded() == []


def test_a_failed_group_stays_degraded_until_it_succeeds_again(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    manager.cache.store_last_good(SLOT_STATE, {"a": 1}, ts=NOW)
    manager.cache.store_last_good(SLOT_LOGS, {"b": 2}, ts=NOW)

    manager._note(SOURCE_LOGS, False)
    assert manager._degraded() == [SOURCE_LOGS]
    clock.advance(600)                     # its tier is backed off, not healthy
    assert manager._degraded() == [SOURCE_LOGS]
    manager._note(SOURCE_LOGS, True)
    assert manager._degraded() == []


def test_noting_an_unknown_group_raises_rather_than_reaching_the_title_bar(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    with pytest.raises(ValueError):
        manager._note("rpc", False)


def test_the_client_flags_fold_into_the_three_groups(tmp_path, clock):
    manager = _manager(tmp_path, clock, wallet="0x" + "ab" * 20)
    for slot in (SLOT_STATE, SLOT_LOGS, SLOT_WALLET):
        manager.cache.store_last_good(slot, {"x": 1}, ts=NOW)
    assert manager._degraded() == []

    manager.client.config_failed = True
    assert manager._degraded() == [SOURCE_STATE]
    manager.client.config_failed = False

    manager.client.log_group_failed["settled"] = True
    assert manager._degraded() == [SOURCE_LOGS]
    manager.client.log_group_failed["settled"] = False

    manager.client.blockscout_truncated = True
    assert manager._degraded() == [SOURCE_LOGS]
    manager.client.blockscout_truncated = False

    manager.client.wallet_failed = True
    assert manager._degraded() == [SOURCE_WALLET]


def test_a_client_double_without_the_flags_does_not_crash_the_manager(tmp_path, clock):
    class Bare:
        async def close(self):
            pass

    manager = _manager(tmp_path, clock, client=Bare())
    assert manager._degraded() == [SOURCE_LOGS, SOURCE_STATE]


def test_guard_swallows_a_raise_and_notes_nothing_itself(tmp_path, clock):
    manager = _manager(tmp_path, clock, client=FakeClient(fetch_state=RuntimeError("boom")))

    async def go():
        return await manager._guard(manager.client.fetch_state, "fetch_state")

    assert asyncio.run(go()) is None


def test_close_closes_the_client_then_saves_the_cache(tmp_path, clock):
    order: list[str] = []
    client = FakeClient()

    manager = _manager(tmp_path, clock, client=client)
    real_close, real_save = client.close, manager.cache.save

    async def close_client():
        order.append("client")
        await real_close()

    def save_cache(*args, **kwargs):
        order.append("cache")
        return real_save(*args, **kwargs)

    client.close = close_client
    manager.cache.save = save_cache
    asyncio.run(manager.close())

    assert order == ["client", "cache"]
    assert client.closed is True


def test_close_still_saves_when_the_client_close_raises(tmp_path, clock):
    client = FakeClient(close=RuntimeError("socket on fire"))
    manager = _manager(tmp_path, clock, client=client)
    manager.cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)

    asyncio.run(manager.close())            # must not raise

    restored = CuratorCache(path=manager.cache.path, clock=clock)
    restored.load(now=NOW)
    assert restored.get_last_good(SLOT_STATE).payload == {"settled": False}


def test_the_wallet_comes_from_the_constructor_never_the_environment(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("MAXPANE_WALLET", "0x" + "ff" * 20)
    manager = _manager(tmp_path, clock)
    assert manager.wallet is None
    src = inspect.getsource(curator_manager)
    assert "os.environ" not in src and "getenv" not in src
