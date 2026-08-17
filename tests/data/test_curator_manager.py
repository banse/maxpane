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
    SERIES_INPUT_KEYS,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    CuratorCache,
)
from maxpane_dashboard.data.curator_manager import (
    FAST_TIER_PAYLOAD_KEYS,
    GROUP_SLOT,
    SOURCES,
    SOURCE_LOGS,
    SOURCE_STATE,
    SOURCE_WALLET,
    CuratorManager,
)
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CuratorConfig,
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


# ---------------------------------------------------------------------------
# WP5.8 — the fast tier: state, the latch and the forced-ETH anomaly
# ---------------------------------------------------------------------------


def _state(**overrides) -> CuratorState:
    """A healthy grace-phase round, calibrated to the 2026-08-16 captures."""
    fields = dict(
        settled=False,
        current_hour=4,
        current_hour_total_wei=51_480_000_000_000_000_000,
        hour_needed_wei=0,                    # 0 during grace is REAL
        hour_seconds_left=3_412,
        last_active_hour=4,
        last_active_hour_total_wei=51_480_000_000_000_000_000,
        early_bps=19_491,
        volume_wei=8_401_000_000_000_000_000_000,
        contributors=143,
        tx_count=222,
        forced_balance_wei=None,              # always fetch_balance()'s
        block_number=25_770_500,
    )
    fields.update(overrides)
    return CuratorState(**fields)


def test_one_state_and_one_balance_call_per_fast_tick(tmp_path, clock):
    client = FakeClient(fetch_state=_state(), fetch_balance=0)
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_state(NOW))
    assert [name for name, *_ in client.calls] == ["fetch_state", "fetch_balance"]


def test_the_balance_is_folded_onto_the_state_and_nowhere_else(tmp_path, clock):
    """H5: a non-zero balance is forced ETH -- somebody selfdestructed into the
    contract.  It must never become a deposit, a volume or an hour total."""
    client = FakeClient(fetch_state=_state(), fetch_balance=1_500_000_000_000_000_000)
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager._pool_state(NOW))
    state = out["state"]
    assert state.forced_balance_wei == 1_500_000_000_000_000_000
    assert state.volume_wei == 8_401_000_000_000_000_000_000
    assert state.current_hour_total_wei == 51_480_000_000_000_000_000


def test_a_zero_balance_is_the_healthy_answer_and_is_not_a_failure(tmp_path, clock):
    client = FakeClient(fetch_state=_state(), fetch_balance=0)
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager._pool_state(NOW))
    assert out["ok"] is True
    assert out["state"].forced_balance_wei == 0
    assert manager._degraded() == [SOURCE_LOGS]        # logs never ran, state is fine


def test_the_fast_tier_payload_cannot_reach_the_series(tmp_path, clock):
    """The other half of H2's guarantee, from the manager's side: the keys the
    fast tier produces and the keys the series writer consumes are disjoint
    sets, asserted rather than reasoned about."""
    assert not (set(FAST_TIER_PAYLOAD_KEYS) & set(SERIES_INPUT_KEYS))
    for banned in ("current_hour_total_wei", "last_active_hour", "last_active_hour_total_wei"):
        assert banned not in FAST_TIER_PAYLOAD_KEYS


def test_the_fast_tier_writes_no_series_point_however_often_it_runs(tmp_path, clock):
    """The behavioural half.  Fifty fast ticks across an hour boundary, with
    the live hour total collapsing to 0 -- and the series stays empty, because
    only a folded sweep may write one."""
    states = [_state(), _state(current_hour=5, current_hour_total_wei=0, last_active_hour=4)]
    client = FakeClient(fetch_state=lambda: states[min(1, len(client.calls) // 10)],
                        fetch_balance=0)
    manager = _manager(tmp_path, clock, client=client)
    for _ in range(50):
        asyncio.run(manager._pool_state(clock.now))
        clock.advance(15)
    assert manager.cache.get_series("volume_series") == []
    assert manager.cache.get_series("contributors_series") == []


def test_settled_feeds_the_latch_and_the_latch_only(tmp_path, clock):
    client = FakeClient(fetch_state=_state(settled=True), fetch_balance=0)
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_state(NOW))
    record = manager.cache.settlement_record()
    assert record.settled is True
    assert record.block_number == 25_770_500
    assert record.observed_at == NOW


def test_a_failed_state_read_notes_state_and_leaves_the_last_good_standing(tmp_path, clock):
    client = FakeClient(fetch_state=_state(), fetch_balance=0)
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_state(NOW))
    assert manager.cache.get_last_good(SLOT_STATE).payload["contributors"] == 143

    client.answers["fetch_state"] = None
    clock.advance(15)
    out = asyncio.run(manager._pool_state(clock.now))
    assert out["ok"] is False
    assert SOURCE_STATE in manager._degraded()
    assert manager.cache.get_last_good(SLOT_STATE).payload["contributors"] == 143
    assert manager.cache.as_of_ts(SLOT_STATE) == NOW          # freshness froze
    assert manager.cache.last_fetch_ts("fast") == NOW         # a failure is not a fetch


def test_a_failed_balance_read_never_becomes_a_zero(tmp_path, clock):
    """'RPC down' and 'the contract holds nothing' are different facts and the
    forced-ETH row says different things about each."""
    client = FakeClient(fetch_state=_state(), fetch_balance=None)
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager._pool_state(NOW))
    assert out["state"].forced_balance_wei is None
    assert out["ok"] is False


def test_the_once_tier_is_read_live_and_then_never_again(tmp_path, clock):
    config = CuratorConfig(
        launch_time=1_786_910_327,
        hourly_threshold_wei=5 * 10**18,
        grace_period=86_400,
        hour_duration=3_600,
        min_deposit_wei=5 * 10**16,
        min_escalation_wei=10**17,
        credit_cap_wei=1000 * 10**18,
        first_judged_hour=24,
        points_per_eth=1000,
        deployer=A.DEPLOYER,
    )
    client = FakeClient(fetch_config=config)
    manager = _manager(tmp_path, clock, client=client)

    payload = asyncio.run(manager._pool_config({"once"}, NOW))
    assert payload["hourly_threshold_wei"] == 5 * 10**18
    assert payload["points_per_eth"] == 1000

    clock.advance(365 * 24 * 3600)
    again = asyncio.run(manager._pool_config(set(manager.cache.tiers_due()), clock.now))
    assert again == payload
    assert [name for name, *_ in client.calls] == ["fetch_config"]


def test_a_failed_once_tier_degrades_state_and_comes_due_again(tmp_path, clock):
    client = FakeClient(fetch_config=None)
    manager = _manager(tmp_path, clock, client=client)
    assert asyncio.run(manager._pool_config({"once"}, NOW)) is None
    assert SOURCE_STATE in manager._degraded()
    clock.advance(3600)
    assert "once" in manager.cache.tiers_due()
