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
    decode_deposit,
    decode_first_deposit,
    decode_hour_saved,
    decode_launched,
    decode_rescued_total,
    decode_settled,
    GROUP_SLOT,
    SOURCES,
    SOURCE_LOGS,
    SOURCE_STATE,
    SOURCE_WALLET,
    CuratorManager,
)
from tests.curator_fixtures import capture
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CuratorConfig,
    CuratorState,
    LogSweep,
    WalletState,
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


# ---------------------------------------------------------------------------
# The decoder — the gap the wave-2 gate found unassigned, and WP5 owns it
# ---------------------------------------------------------------------------

RPC_ROWS = capture("tenderly_logs.json")["result"]
BS_ROWS = capture("bs_page_0.json")["items"]


def test_the_captured_sweep_decodes_to_the_231_deposited_rows():
    events = [e for e in (decode_deposit(row) for row in RPC_ROWS) if e is not None]
    assert len(events) == 231
    first = events[0]
    assert first.contributor == A.ANNOUNCE.lower()
    assert first.hour == 0
    assert first.amount_wei == 50_000_000_000_000_000
    assert first.early_bps == 19_975
    assert first.tx_count == 1


def test_the_weight_identity_holds_wei_exact_for_every_captured_row():
    """H8: weightAdded == creditedDelta * earlyBps // 10_000, floored.  Wei is an
    integer -- pytest.approx on one of these is a review failure."""
    for event in (decode_deposit(row) for row in RPC_ROWS):
        if event is None:
            continue
        assert event.weight_added_wei == event.credited_delta_wei * event.early_bps // 10_000


def test_the_hour_comes_off_the_indexed_topic_not_a_timestamp():
    """Hour bucketing needs no timestamp at all, which is what makes the fold
    immune to the boundary the state views trip over."""
    hours = {e.hour for e in (decode_deposit(r) for r in RPC_ROWS) if e is not None}
    # The 2026-08-16 sweep was taken at 21:04-21:14 UTC, i.e. 65-76 minutes
    # after launch: hours 0 and 1 exist and no later hour does yet.
    assert hours == {0, 1}


def test_every_decoded_event_carries_the_stamp_it_was_handed():
    """H14 struck through: the rows DO carry blockTimestamp, so re-fetching it
    would pay a round trip for nothing."""
    events = [e for e in (decode_deposit(r) for r in RPC_ROWS) if e is not None]
    assert all(e.ts is not None and e.ts > 1_786_000_000 for e in events)


def test_first_deposit_indices_are_one_based_and_max_at_the_contributor_count():
    rows = [decode_first_deposit(r) for r in RPC_ROWS]
    rows = [r for r in rows if r is not None]
    assert len(rows) == 145
    assert min(r["index"] for r in rows) == 1
    assert max(r["index"] for r in rows) == 145        # == totalContributors


def test_the_launched_row_decodes_to_the_pinned_immutables():
    launched = [decode_launched(r) for r in RPC_ROWS]
    launched = [r for r in launched if r is not None]
    assert len(launched) == 1
    assert launched[0] == {
        "launch_time": A.LAUNCH_TIME,
        "hourly_threshold_wei": 5 * 10**18,
        "grace_period": 86_400,
        "hour_duration": 3_600,
        "min_deposit_wei": 5 * 10**16,
        "min_escalation_wei": 10**17,
        "credit_cap_wei": 1000 * 10**18,
    }


def test_the_blockscout_dialect_decodes_to_the_same_event(tmp_path):
    """The cross-check is only a cross-check if both dialects land on the same
    model: block_number/transaction_hash/index/ISO timestamp vs the RPC's hex."""
    by_key = {
        (e.tx_hash.lower(), e.log_index): e
        for e in (decode_deposit(r) for r in RPC_ROWS)
        if e is not None
    }
    matched = 0
    for row in BS_ROWS:
        event = decode_deposit(row)
        if event is None:
            continue
        twin = by_key.get((event.tx_hash.lower(), event.log_index))
        if twin is None:
            continue
        matched += 1
        assert event == twin
    assert matched >= 25


def test_a_short_or_malformed_payload_decodes_to_none_never_to_zeros():
    """A truncated log and a reverted call both look like something int(x, 16)
    would turn into a 0 -- and a 0 here is a deposit that never happened."""
    good = dict(RPC_ROWS[2])
    assert decode_deposit(good) is not None

    short = dict(good, data="0x" + "00" * 32)             # one word, seven needed
    assert decode_deposit(short) is None
    assert decode_deposit(dict(good, data="0x")) is None
    assert decode_deposit(dict(good, data=None)) is None
    assert decode_deposit(dict(good, topics=[good["topics"][0]])) is None
    assert decode_deposit(dict(good, transactionHash=None)) is None
    assert decode_deposit(dict(good, logIndex=None)) is None
    assert decode_deposit(dict(good, blockNumber="not-hex")) is None
    assert decode_deposit("junk") is None
    assert decode_deposit(None) is None


def test_a_row_of_another_event_is_not_decoded_as_a_deposit():
    """Topic0 is checked, so the six filters cannot contaminate each other."""
    first_deposit_row = next(
        r for r in RPC_ROWS if r["topics"][0].lower() == A.TOPIC_FIRST_DEPOSIT.lower()
    )
    assert decode_deposit(first_deposit_row) is None
    assert decode_hour_saved(first_deposit_row) is None
    assert decode_settled(first_deposit_row) is None
    assert decode_launched(first_deposit_row) is None


def test_a_row_with_no_stamp_decodes_with_ts_none(tmp_path):
    """Renders '--:--'.  A 0 would render 1970-01-01, which looks like data."""
    stampless = {k: v for k, v in RPC_ROWS[2].items() if k != "blockTimestamp"}
    event = decode_deposit(stampless)
    assert event is not None and event.ts is None


def test_rescued_distinguishes_never_fired_from_never_read():
    """0 is a real answer -- Rescued has never fired -- and None is an outage."""
    assert decode_rescued_total(RPC_ROWS) == 0
    assert decode_rescued_total(()) == 0
    assert decode_rescued_total(None) is None


def test_the_settled_and_hour_saved_decoders_read_their_synthetic_rows():
    """# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    (WP1.3 capture C).  Neither event has ever fired on chain, so these rows
    are hand-built from the vendored ABI; the shape is the ABI's, not a guess.
    """
    settled_row = {
        "topics": [A.TOPIC_SETTLED, "0x" + f"{24:064x}"],
        "data": "0x" + f"{1_787_000_400:064x}" + f"{300:064x}" + f"{9 * 10**21:064x}",
        "blockNumber": "0x18937a0",
        "transactionHash": "0x" + "ab" * 32,
        "logIndex": "0x1",
        "blockTimestamp": hex(1_787_000_400),
    }
    assert decode_settled(settled_row) == {
        "hour": 24,
        "ts": 1_787_000_400,
        "total_contributors": 300,
        "total_volume_wei": 9 * 10**21,
    }
    assert decode_settled(dict(settled_row, data="0x")) is None

    saved_row = {
        "topics": [
            A.TOPIC_HOUR_SAVED,
            "0x" + "0" * 24 + "cd" * 20,
            "0x" + f"{30:064x}",
        ],
        "data": "0x" + f"{5 * 10**18:064x}",
        "blockNumber": "0x18937a1",
        "transactionHash": "0x" + "cd" * 32,
        "logIndex": "0x2",
        "blockTimestamp": hex(1_787_004_000),
    }
    assert decode_hour_saved(saved_row) == {
        "hour": 30,
        "wallet": "0x" + "cd" * 20,
        "ts": float(1_787_004_000),
    }


# ---------------------------------------------------------------------------
# WP5.9 — backfill, incremental sweep and gap repair
# ---------------------------------------------------------------------------

CONFIG = {
    "launch_time": A.LAUNCH_TIME,
    "grace_period": 86_400,
    "hour_duration": 3_600,
    "hourly_threshold_wei": 5 * 10**18,
    "first_judged_hour": 24,
    "points_per_eth": 1000,
    "credit_cap_wei": 1000 * 10**18,
}


def _sweep(rows=None, *, from_block=A.CREATION_BLOCK, to_block=25_770_500) -> LogSweep:
    rows = RPC_ROWS if rows is None else rows
    groups = {"deposits": [], "first_deposits": [], "hour_saved": [],
              "settled": [], "rescued": [], "launched": []}
    topic_group = {
        A.TOPIC_DEPOSITED.lower(): "deposits",
        A.TOPIC_FIRST_DEPOSIT.lower(): "first_deposits",
        A.TOPIC_HOUR_SAVED.lower(): "hour_saved",
        A.TOPIC_SETTLED.lower(): "settled",
        A.TOPIC_RESCUED.lower(): "rescued",
        A.TOPIC_LAUNCHED.lower(): "launched",
    }
    for row in rows:
        group = topic_group.get(row["topics"][0].lower())
        if group:
            groups[group].append(row)
    return LogSweep(
        from_block=from_block,
        to_block=to_block,
        **{name: tuple(items) for name, items in groups.items()},
    )


def _recorded_from_block(client) -> int:
    return next(args[0] for name, *args in client.calls if name == "fetch_logs")


def test_a_first_run_backfills_from_the_creation_block(tmp_path, clock):
    """Validated as one sweep in the research; 377 logs from 25 769 870."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    assert _recorded_from_block(client) == A.CREATION_BLOCK
    assert len(manager.cache.events()) == 231
    assert len(manager.cache.first_deposits()) == 145


def test_a_later_run_starts_at_the_watermark_plus_one(tmp_path, clock):
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    assert manager.cache.last_seen_block() == 25_770_500

    clock.advance(60)
    client.answers["fetch_logs"] = lambda *_: _sweep([], from_block=25_770_501,
                                                     to_block=25_770_600)
    asyncio.run(manager._pool_logs({"medium"}, clock.now, CONFIG))
    assert _recorded_from_block(client) == A.CREATION_BLOCK
    assert [args[0] for name, *args in client.calls if name == "fetch_logs"][-1] == 25_770_501


def test_a_failed_sweep_does_not_advance_the_watermark(tmp_path, clock):
    """Otherwise the missed range is missed forever and the leaderboard is
    permanently wrong with no symptom."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    before = manager.cache.last_seen_block()

    client.answers["fetch_logs"] = lambda *_: None
    clock.advance(60)
    out = asyncio.run(manager._pool_logs({"medium"}, clock.now, CONFIG))
    assert out["ok"] is False
    assert manager.cache.last_seen_block() == before
    assert SOURCE_LOGS in manager._degraded()

    # ...and the next attempt re-reads the range that failed, not the one after.
    client.answers["fetch_logs"] = lambda *_: _sweep([], from_block=before + 1,
                                                     to_block=before + 50)
    clock.advance(60)
    asyncio.run(manager._pool_logs({"medium"}, clock.now, CONFIG))
    assert [args[0] for name, *args in client.calls if name == "fetch_logs"][-1] == before + 1


def test_a_sweep_the_medium_tier_is_not_due_for_is_not_made(tmp_path, clock):
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager._pool_logs({"fast"}, NOW, CONFIG))
    assert out == {"ok": None, "swept": False}
    assert client.calls == []


def test_the_fold_and_the_series_come_out_of_the_sweep(tmp_path, clock):
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    rows = manager.cache.fold_rows()
    assert len(rows) == 145                     # == totalContributors
    assert rows[0].points is not None
    series = manager.cache.get_series("volume_series")
    assert [ts for ts, _v in series] == [A.LAUNCH_TIME, A.LAUNCH_TIME + 3600]
    assert series[0][1] > 0
    assert manager.cache.get_series("contributors_series")[-1][1] == 145


def test_the_series_is_untouched_when_the_launch_anchor_is_unknown(tmp_path, clock):
    """Without launchTime a bucket has no wall clock; the series waits for the
    `once` tier rather than inventing a timeline."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, None))
    assert manager.cache.get_series("volume_series") == []
    assert len(manager.cache.events()) == 231   # the history still folded in


def test_one_failed_log_group_degrades_only_its_own_keys(tmp_path, clock):
    """LogSweep's () is ambiguous; log_group_failed resolves it.  A dead
    ``settled`` filter must not make the leaderboard look empty, and an empty
    ``hour_saved`` must not read as a failure."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    client.log_group_failed["rescued"] = True
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    assert len(manager.cache.events()) == 231           # deposits unaffected
    assert manager.cache.hour_saved() == []             # read, never fired
    assert manager.cache.rescued_total_wei() is None    # NOT read -> not 0
    assert SOURCE_LOGS in manager._degraded()
    assert "rescued" not in manager._logs_read_groups()
    assert "hour_saved" in manager._logs_read_groups()


def test_a_settled_log_fills_the_obituary_without_creating_the_latch(tmp_path, clock):
    """# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    (WP1.3 capture C).  Settled has never fired on chain."""
    settled_row = {
        "topics": [A.TOPIC_SETTLED, "0x" + f"{24:064x}"],
        "data": "0x" + f"{1_787_000_400:064x}" + f"{300:064x}" + f"{9 * 10**21:064x}",
        "blockNumber": "0x18937a0",
        "transactionHash": "0x" + "ab" * 32,
        "logIndex": "0x1",
        "blockTimestamp": hex(1_787_000_400),
    }
    client = FakeClient(fetch_logs=lambda *_: _sweep([*RPC_ROWS, settled_row]))
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    assert manager.cache.settlement_record() is None

    manager.cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    record = manager.cache.settlement_record()
    assert record.settled_hour == 24 and record.total_contributors == 300


def test_the_slow_tier_repairs_a_gap_the_fold_missed(tmp_path, clock):
    """PRD §5: cross-check against an independent source; a mismatch triggers a
    re-sweep of the suspect range rather than a silent wrong number.  Driven
    with a fold that is deliberately short by one event."""
    short = [row for row in RPC_ROWS if row is not RPC_ROWS[2]]
    missing = RPC_ROWS[2]
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(short),
        fetch_blockscout_logs=lambda *_: [missing],
    )
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    assert len(manager.cache.events()) == 230

    out = asyncio.run(manager._pool_crosscheck({"slow"}, NOW, _state(), CONFIG))
    assert out["gap_block"] == 25_769_888
    assert manager._repair_from_block == 25_769_888
    assert manager._fold_stale is True
    assert SOURCE_LOGS in manager._degraded()
    assert "medium" in manager.cache.tiers_due(NOW)      # the repair is brought forward

    client.answers["fetch_logs"] = lambda *_: _sweep()
    asyncio.run(manager._pool_logs({"medium"}, NOW + 1, CONFIG))
    assert _recorded_from_block(client) == A.CREATION_BLOCK
    assert [args[0] for name, *args in client.calls if name == "fetch_logs"][-1] == 25_769_888
    assert len(manager.cache.events()) == 231
    assert manager._repair_from_block is None
    assert manager._fold_stale is False


def test_a_stats_mismatch_marks_the_fold_stale_rather_than_publishing(tmp_path, clock):
    """The contract's own deposit counter against the folded history -- but
    only when the fold covers the block the counter was read at, because the
    two are read seconds apart on different endpoint pools."""
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(to_block=25_770_500),
        fetch_blockscout_logs=lambda *_: [],
    )
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    # Fold younger than the counter's block: not comparable, nothing claimed.
    ahead = _state(tx_count=9_999, block_number=25_999_999)
    out = asyncio.run(manager._pool_crosscheck({"slow"}, NOW, ahead, CONFIG))
    assert out["gap_block"] is None
    assert manager._fold_stale is False

    # Fold covers the block: 231 folded against a claimed 400 is a real gap.
    covered = _state(tx_count=400, block_number=25_770_400)
    out = asyncio.run(manager._pool_crosscheck({"slow"}, NOW, covered, CONFIG))
    assert out["gap_block"] == A.CREATION_BLOCK
    assert manager._fold_stale is True
    assert SOURCE_LOGS in manager._degraded()


def test_a_dead_cross_check_does_not_condemn_the_fold(tmp_path, clock):
    """Blockscout being down is not the logs pool being down: the fold still
    stands on the RPC sweep, and claiming a gap we cannot see would be worse
    than saying nothing."""
    client = FakeClient(fetch_logs=lambda *_: _sweep(), fetch_blockscout_logs=lambda *_: None)
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    out = asyncio.run(manager._pool_crosscheck({"slow"}, NOW, _state(), CONFIG))
    assert out["ok"] is False
    assert manager._fold_stale is False
    assert manager._repair_from_block is None
    assert manager._degraded() == [SOURCE_STATE]        # state never ran here


def test_a_sweep_row_that_does_not_decode_is_dropped_not_zeroed(tmp_path, clock):
    broken = dict(RPC_ROWS[2], data="0x00")
    client = FakeClient(fetch_logs=lambda *_: _sweep([*RPC_ROWS, broken]))
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    assert len(manager.cache.events()) == 231
    assert all(e.amount_wei > 0 for e in manager.cache.events())


# ---------------------------------------------------------------------------
# WP5.10 — the YOU tier
# ---------------------------------------------------------------------------

WALLET = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"


def _wallet_state(**overrides) -> WalletState:
    fields = dict(
        address=WALLET,
        points=1000,
        weight_wei=10**18,
        contributed_wei=10**18,
        tx_count=4,
        first_hour=0,
        has_joined=True,
        required_next_wei=4_100_000_000_000_000_000,
    )
    fields.update(overrides)
    return WalletState(**fields)


def test_with_no_wallet_configured_zero_wallet_calls_are_made(tmp_path, clock):
    client = FakeClient(fetch_wallet=_wallet_state())
    manager = _manager(tmp_path, clock)
    manager.client = client
    assert asyncio.run(manager._pool_wallet(NOW)) is None
    assert client.calls == []
    assert manager._degraded() == [SOURCE_LOGS, SOURCE_STATE]      # never 'wallet'


def test_with_a_wallet_set_the_six_views_run_on_the_fast_tier(tmp_path, clock):
    client = FakeClient(fetch_wallet=_wallet_state())
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    state = asyncio.run(manager._pool_wallet(NOW))
    assert client.calls == [("fetch_wallet", WALLET)]
    assert state.points == 1000
    assert manager.cache.get_last_good(SLOT_WALLET).payload == {"address": WALLET}
    assert SOURCE_WALLET not in manager._degraded()


def test_an_invalid_address_is_rejected_before_any_request(tmp_path, clock):
    """Sending garbage to a public node to be told what we could have checked
    locally is both rude and slow."""
    for bad in ("not-an-address", "0x1234", "0x" + "zz" * 20, 42, ""):
        client = FakeClient(fetch_wallet=_wallet_state())
        manager = _manager(tmp_path, clock, client=client, wallet=bad)
        assert asyncio.run(manager._pool_wallet(NOW)) is None
        assert client.calls == []
        if bad:
            assert SOURCE_WALLET in manager._degraded()


def test_a_stranger_is_a_successful_read_not_a_failure(tmp_path, clock):
    """The contract answers minDeposit for a wallet that has never deposited,
    which is exactly the number that wallet needs."""
    stranger = _wallet_state(
        points=0, weight_wei=0, contributed_wei=0, tx_count=0,
        first_hour=0, has_joined=False, required_next_wei=5 * 10**16,
    )
    client = FakeClient(fetch_wallet=stranger)
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    state = asyncio.run(manager._pool_wallet(NOW))
    assert state.has_joined is False
    assert state.required_next_wei == 5 * 10**16
    assert SOURCE_WALLET not in manager._degraded()


def test_a_failed_wallet_read_degrades_only_the_wallet(tmp_path, clock):
    client = FakeClient(fetch_wallet=None)
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    manager.cache.store_last_good(SLOT_STATE, {"a": 1}, ts=NOW)
    manager.cache.store_last_good(SLOT_LOGS, {"b": 2}, ts=NOW)
    assert asyncio.run(manager._pool_wallet(NOW)) is None
    assert manager._degraded() == [SOURCE_WALLET]


def test_a_partial_wallet_read_is_a_failure_not_a_half_truth(tmp_path, clock):
    """The client sets wallet_failed for a partial batch too: three of six
    views answering is not a YOU row anyone should read as live."""
    client = FakeClient(fetch_wallet=_wallet_state(points=None, weight_wei=None))
    client.wallet_failed = True
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    asyncio.run(manager._pool_wallet(NOW))
    assert SOURCE_WALLET in manager._degraded()
