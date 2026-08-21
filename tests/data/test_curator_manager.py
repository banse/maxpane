"""WP5 — ``CuratorManager``: tiers, decoders, readings and the flat contract.

Every test drives a fake client and an injected clock.  No socket is opened and
nothing sleeps: the fakes are plain objects whose coroutines return committed
fixture data or ``None``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time

import pytest

from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data import curator_manager
from maxpane_dashboard.data.curator_cache import (
    NFT_HOLDER_TTL_SECONDS,
    SERIES_INPUT_KEYS,
    SLOT_BLOCKSCOUT,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    CuratorCache,
)
from tests.curator_fixtures import CAPTURE_A, state_from_bundle
from maxpane_dashboard.data import ens
from maxpane_dashboard.data.curator_cache import TIER_FAST
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
from maxpane_dashboard.data.curator_list_filters import (
    FilterDataUnavailable,
    FilterSpec,
    NftCollectionRef,
    PREDEFINED_NFT_COLLECTIONS,
    empty_filter_values,
    parse_filter_values,
    preset_filter,
)
from maxpane_dashboard.data.curator_nft_holders import (
    NftHolderPending,
    NftHolderScan,
    NftHolderUnavailable,
    wallet_universe_fingerprint,
)
from tests.curator_fixtures import capture
from maxpane_dashboard.analytics.curator_signals import LEADERBOARD_LIMIT, build_signals
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CURATOR_KEYS,
    CURATOR_ROW_KEYS,
    ContributorRow,
    CuratorConfig,
    DepositEvent,
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

    async def fetch_ens_names(self, addresses, **_kw):
        return self._answer("fetch_ens_names", tuple(addresses)) or {}

    async def fetch_blockscout_logs(self, max_pages=400):
        return self._answer("fetch_blockscout_logs", max_pages)

    async def close(self):
        self.closed = True
        value = self.answers.get("close")
        if isinstance(value, Exception):
            raise value


class FakeNftClient:
    def __init__(self, answers=(), names=()):
        self.answers = list(answers)
        self.names = list(names)
        self.calls = []
        self.name_calls = []
        self.closed = False

    async def collection_name(self, collection):
        self.name_calls.append(collection.key)
        answer = self.names.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def scan(self, collection, wallets):
        self.calls.append((collection.key, tuple(wallets)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def close(self):
        self.closed = True


def _nft_row(address, points=1):
    return {
        "rank": 1,
        "address": address,
        "points": points,
        "credit_eth": 1.0,
        "tx_count": 1,
        "flagged": False,
        "name": None,
        "weight_eth": 1.0,
        "first_hour": 0,
        "first_index": 1,
        "link_conf": "clean",
    }


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


def test_the_manager_never_names_a_live_hour_view_at_all(tmp_path, clock):
    """H2, structural, and the half the tree lacked.  The cache is grepped for
    these spellings already, but the FOLD PATH lives here: `_refold` builds its
    buckets one attribute access away from the live CuratorState, and a
    mutation that stamps the live hour total onto the folded bucket persists
    the exact 99.5% boundary crash H2 exists to prevent -- with the whole suite
    green, because FAST_TIER_PAYLOAD_KEYS governs the last-good PAYLOAD and not
    what `_refold` may read off a state object."""
    src = inspect.getsource(curator_manager)
    for banned in (
        "current_hour_total",
        "currentHourTotal",
        "last_active_hour",
        "lastActiveHour",
    ):
        assert banned not in src, banned


def test_a_quiet_crossing_cannot_overwrite_a_folded_bucket(tmp_path, clock):
    """The behavioural half.  Replay a healthy cycle, then **the chain's own
    quiet crossing**, and force a refold.  The series must not move: the hour's
    volume is the logs' answer, and a state poll has no vote.

    Re-pointed 2026-08-17 at capture A -- the state this test used to describe
    with two hand-changed words, now the words the chain wrote at 15:58:52 UTC:
    ``currentHour`` 20, ``currentHourTotal`` 0, ``lastActiveHour`` still 19 with
    11,322.19 ETH in it.  Decoded through the client's own ``decode_view``, so
    the bytes travel the production path.
    """
    real = state_from_bundle(CAPTURE_A)
    assert real.current_hour_total_wei == 0
    assert real.last_active_hour < real.current_hour
    assert real.last_active_hour_total_wei > 0

    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    manager = _manager(tmp_path, clock, client=client)
    healthy = asyncio.run(manager.fetch_and_compute())
    assert healthy["volume_series"] and healthy["volume_series"][-1][1] > 0

    client.answers["fetch_state"] = real
    clock.advance(60)
    manager.cache.mark_failed("medium", clock.now, retry_after=0.0)   # force a refold
    crossed = asyncio.run(manager.fetch_and_compute())

    assert crossed["volume_series"] == healthy["volume_series"]
    assert manager.cache.get_series("volume_series") == healthy["volume_series"]


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


def test_the_contributors_curve_gets_a_point_per_hour_not_one_per_cycle(tmp_path, clock):
    """A cumulative total stamped at the newest bucket is a ONE-POINT series,
    and ``CuratorSparklines`` renders "waiting for data..." below two points --
    so the PEOPLE row would stay blank on a fresh install no matter how long
    the game has run.  The persisted curve must be the same curve
    ``build_signals`` computes, hour by hour, not one sample of it."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    stored = manager.cache.get_series("contributors_series")
    computed = build_signals(
        manager._readings(config=CONFIG, logs=_sweep()), now_ts=NOW
    )["contributors_series"]
    assert len(stored) == 2                                  # hours 0 and 1
    assert stored == [[float(ts), float(v)] for ts, v in computed]
    assert [ts for ts, _v in stored] == [A.LAUNCH_TIME, A.LAUNCH_TIME + 3600]
    assert stored[0][1] < stored[1][1]                       # a curve, not a level


def test_a_failed_fold_writes_no_zero_and_keeps_the_previous_table(tmp_path, clock):
    """``safe_call`` turning a raise into ``[]`` used to reach
    ``record_contributor_count(len(rows or []))`` as a literal ``0`` -- the
    sentinel-in-a-persisted-series the house rule forbids, and it survived to
    disk.  A failed fold is not an empty fold: nothing is published, the
    leaderboard keeps standing and the watermark does not move past the range
    that produced it."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    healthy = manager.cache.get_series("contributors_series")
    watermark = manager.cache.last_seen_block()
    assert healthy and len(manager.cache.fold_rows()) == 145

    def boom(*_args, **_kwargs):
        raise RuntimeError("fold on fire")

    original = curator_manager.fold_deposits
    curator_manager.fold_deposits = boom
    try:
        clock.advance(60)
        client.answers["fetch_logs"] = lambda *_: _sweep(
            [], from_block=watermark + 1, to_block=watermark + 50
        )
        asyncio.run(manager._pool_logs({"medium"}, clock.now, CONFIG))
    finally:
        curator_manager.fold_deposits = original

    assert manager.cache.get_series("contributors_series") == healthy
    assert 0.0 not in [v for _ts, v in manager.cache.get_series("contributors_series")]
    assert len(manager.cache.fold_rows()) == 145
    assert manager.cache.last_seen_block() == watermark

    manager.cache.save()
    restored = CuratorCache(path=manager.cache.path, clock=clock)
    restored.load(now=clock.now)
    assert restored.get_series("contributors_series") == healthy


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


def _partial_sweep_client(dead_group: str) -> FakeClient:
    """A sweep whose ``dead_group`` filter died while the others answered.

    The client documents exactly this: ``fetch_logs`` returns a ``LogSweep``
    unless *every* group failed, and ``log_group_failed`` is the only thing
    that tells ``()`` apart from "this filter died".
    """
    import dataclasses as _dc

    partial = _dc.replace(_sweep(), **{dead_group: ()})
    client = FakeClient(
        fetch_logs=lambda *_: partial, fetch_blockscout_logs=lambda *_: []
    )
    client.log_group_failed[dead_group] = True
    return client


def test_a_dead_deposits_filter_reads_as_unavailable_not_as_an_empty_game(tmp_path, clock):
    """A sweep whose ``deposits`` filter died still returns a LogSweep, so
    keying the None/[] distinction off the SWEEP rather than the GROUP reads
    that filter as "read it, found nothing" -- the conflation 1ba8370 fixed one
    level up, reintroduced one level down.  The widgets branch on it: [] renders
    "no deposits yet" over a game with 231 of them."""
    client = _partial_sweep_client("deposits")
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager.fetch_and_compute())

    assert "deposits" not in manager._logs_read_groups()
    assert out["leaderboard_rows"] is None
    assert out["activity_rows"] is None
    assert out["closest_call_rows"] is None
    assert out["cluster_rows"] is None
    assert SOURCE_LOGS in out["degraded"]


def test_a_dead_filter_does_not_advance_the_watermark_past_its_range(tmp_path, clock):
    """store_fold's contract: advancing on a failure skips that block range
    FOREVER, and the leaderboard is then permanently wrong with no symptom.  A
    sweep that read five groups and not the sixth has not covered its range."""
    client = _partial_sweep_client("deposits")
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    assert manager.cache.last_seen_block() is None           # never advanced
    assert manager._sweep_from_block() == A.CREATION_BLOCK   # re-read, not skipped
    assert len(manager.cache.first_deposits()) == 145        # what arrived is kept

    # ...and once the filter recovers, the range is swept again and folded.
    client.log_group_failed["deposits"] = False
    client.answers["fetch_logs"] = lambda *_: _sweep()
    clock.advance(60)
    asyncio.run(manager._pool_logs({"medium"}, clock.now, CONFIG))
    assert [args[0] for name, *args in client.calls if name == "fetch_logs"][-1] == (
        A.CREATION_BLOCK
    )
    assert len(manager.cache.events()) == 231
    assert manager.cache.last_seen_block() == 25_770_500


def test_a_group_with_history_still_serves_it_when_its_filter_dies(tmp_path, clock):
    """The other side of the same rule.  A transient dead filter must not blank
    a fold we already hold -- that is what last-good behind `as of HH:MM` is
    for, and it is the degradation matrix's row 2."""
    client = FakeClient(fetch_logs=lambda *_: _sweep(), fetch_blockscout_logs=lambda *_: [])
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager.fetch_and_compute())

    dead = _partial_sweep_client("deposits")
    manager.client = dead
    clock.advance(60)
    out = asyncio.run(manager.fetch_and_compute())
    assert 0 < len(out["leaderboard_rows"]) <= LEADERBOARD_LIMIT
    assert SOURCE_LOGS in out["degraded"]


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


class _BlockingCrossCheck(FakeClient):
    """A Blockscout read that does not answer until the test lets it.

    Stands in for the real one, which pages the contract's entire log history
    50 rows at a time: 19 500 logs and climbing, measured at 202.6 s.
    """

    def __init__(self, rows, **answers) -> None:
        super().__init__(**answers)
        self.rows = rows
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.crosschecks = 0

    async def fetch_blockscout_logs(self, max_pages=400):
        self.crosschecks += 1
        self.started.set()
        await self.release.wait()
        return self.rows


def _blocking_manager(tmp_path, clock, rows=()):
    client = _BlockingCrossCheck(
        list(rows),
        fetch_logs=lambda *_: _sweep(),
        fetch_state=_state(),
        fetch_config=None,
    )
    return _manager(tmp_path, clock, client=client), client


def test_the_payload_does_not_wait_for_the_cross_check(tmp_path, clock):
    """First paint must not sit behind a read of the whole log history.

    Measured through the real app before this changed: the first payload
    arrived after 201.2 s, of which `fetch_blockscout_logs` was 202.6 of the
    cycle's 203.8; the next cycle took 0.8 s.  Everything a panel renders was
    ready in under a second and the reader watched an empty SIGNALS rail -- the
    doomsday clock -- for three and a half minutes, on every launch, warm cache
    included.

    Nothing in the payload comes from the cross-check: it either agrees with
    the fold or schedules a repair sweep for a later tick.
    """
    manager, client = _blocking_manager(tmp_path, clock)

    async def _run() -> None:
        # If this were awaited, the timeout is what would fire.
        out = await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert set(out) == set(CURATOR_KEYS)
        assert out["leaderboard_rows"], "the fold that drives every panel"

        # ...and it really is running, rather than skipped.
        await asyncio.wait_for(client.started.wait(), timeout=5)
        assert not manager._crosscheck_task.done()

        # A second cycle while it pages does not stack a second one up: the
        # slow tier is still due, because only the call itself marks it.
        await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert client.crosschecks == 1

        client.release.set()
        await asyncio.wait_for(manager._crosscheck_task, timeout=5)
        assert manager.cache.last_good.get(SLOT_BLOCKSCOUT) is not None

    asyncio.run(_run())


def test_a_gap_found_after_the_payload_still_schedules_the_repair(tmp_path, clock):
    """Detached, not dropped: the answer lands late and still does its job."""
    missing = RPC_ROWS[2]
    manager, client = _blocking_manager(tmp_path, clock, rows=[missing])
    manager.client.answers["fetch_logs"] = lambda *_: _sweep(
        [row for row in RPC_ROWS if row is not missing]
    )

    async def _run() -> None:
        await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert len(manager.cache.events()) == 230
        assert manager._repair_from_block is None      # not back yet
        await asyncio.wait_for(client.started.wait(), timeout=5)

        client.release.set()
        await asyncio.wait_for(manager._crosscheck_task, timeout=5)
        assert manager._repair_from_block == 25_769_888
        assert manager._fold_stale is True
        assert SOURCE_LOGS in manager._degraded()
        assert "medium" in manager.cache.tiers_due(NOW)

    asyncio.run(_run())


def test_close_stops_an_in_flight_cross_check_before_the_sockets_go(tmp_path, clock):
    """Quitting mid-sweep is the common case when the sweep takes minutes.

    The task holds the same client, so it is cancelled and awaited before
    ``close()`` touches it -- and the cache is still saved.
    """
    manager, client = _blocking_manager(tmp_path, clock)

    async def _run() -> None:
        await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        await asyncio.wait_for(client.started.wait(), timeout=5)
        task = manager._crosscheck_task

        await asyncio.wait_for(manager.close(), timeout=5)
        assert task.done() and task.cancelled()
        assert manager._crosscheck_task is None
        assert client.closed is True
        assert os.path.exists(manager.cache.path)

    asyncio.run(_run())


def test_a_cross_check_that_raises_costs_no_cycle(tmp_path, clock):
    """A detached task has nobody to raise at, so it must not raise at all --
    an unretrieved exception surfaces at GC time and never as a degraded
    source."""
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(),
        fetch_state=_state(),
        fetch_blockscout_logs=RuntimeError("blockscout gone"),
    )
    manager = _manager(tmp_path, clock, client=client)

    async def _run() -> None:
        out = await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert set(out) == set(CURATOR_KEYS)
        await asyncio.wait_for(manager._crosscheck_task, timeout=5)
        assert manager._crosscheck_task.exception() is None

    asyncio.run(_run())


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


def test_a_legacy_truncated_cache_is_repaired_from_creation_once(tmp_path, clock):
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(),
    )
    manager = _manager(tmp_path, clock, client=client)
    decoded = [decode_deposit(row) for row in RPC_ROWS]
    events = [event for event in decoded if event is not None]
    manager.cache.store_events(events[-100:])
    manager.cache.store_fold([], last_block=25_770_500, now=NOW)
    manager.cache.dropped_events = 131

    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    assert _recorded_from_block(client) == A.CREATION_BLOCK
    assert len(manager.cache.events()) == 231
    assert manager.cache.dropped_events == 0
    assert manager._sweep_from_block() == 25_770_501


def test_a_partial_legacy_repair_keeps_the_marker_and_retries_from_creation(
    tmp_path, clock
):
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    client.log_group_failed["deposits"] = True
    manager = _manager(tmp_path, clock, client=client)
    manager.cache.store_fold([], last_block=25_770_500, now=NOW)
    manager.cache.dropped_events = 5

    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    assert manager.cache.dropped_events == 5
    assert manager._sweep_from_block() == A.CREATION_BLOCK


def test_a_legacy_repair_behind_the_old_watermark_keeps_the_marker(
    tmp_path, clock
):
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(to_block=25_770_499),
    )
    manager = _manager(tmp_path, clock, client=client)
    manager.cache.store_fold([], last_block=25_770_500, now=NOW)
    manager.cache.dropped_events = 5

    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    assert manager.cache.dropped_events == 5
    assert manager._sweep_from_block() == A.CREATION_BLOCK


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


# ---------------------------------------------------------------------------
# WP5.11 — the readings seam
# ---------------------------------------------------------------------------


def test_readings_emits_exactly_the_frozen_reading_keys(tmp_path, clock):
    from maxpane_dashboard.analytics.curator_signals import READING_KEYS

    manager = _manager(tmp_path, clock)
    assert set(manager._readings()) == set(READING_KEYS)
    assert set(manager._readings(state=_state(), config=CONFIG, logs=_sweep())) == set(
        READING_KEYS
    )


def test_the_outage_encoding_is_held_constant(tmp_path, clock):
    """None == the read failed.  [] == the read succeeded and found nothing.
    Collapsing them makes a dead logs pool indistinguishable from a quiet
    chain -- and 'quiet' is the state that kills this contract."""
    manager = _manager(tmp_path, clock)
    dead = manager._readings(logs=None)
    quiet = manager._readings(logs=LogSweep(from_block=1, to_block=2))
    assert dead["deposits"] is None
    assert dead["first_deposits"] is None
    assert dead["hour_saved"] is None
    assert quiet["deposits"] == []
    assert quiet["hour_saved"] == []


def test_a_group_read_once_keeps_reading_empty_rather_than_dead(tmp_path, clock):
    """HourSaved and Rescued have never fired on chain: 'read it, found
    nothing' is the expected answer and must not render as an outage."""
    client = FakeClient(fetch_logs=lambda *_: _sweep())
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    later = manager._readings(logs=None)
    assert later["hour_saved"] == []
    assert len(later["deposits"]) == 231


def test_the_fast_tier_readings_are_live_only_and_never_stale(tmp_path, clock):
    """PRD §11 row 1: a dead state pool means the clock, the phase truth and
    earlyBps render unavailable -- never a stale number wearing a live face."""
    manager = _manager(tmp_path, clock)
    manager.cache.store_last_good(SLOT_STATE, {"current_hour": 4}, ts=NOW)
    read = manager._readings(state=None)
    for key in FAST_TIER_PAYLOAD_KEYS:
        assert read[key] is None, key


def test_config_is_served_from_the_cache_because_immutables_cannot_go_stale(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    read = manager._readings(config=CONFIG)
    assert read["launch_time"] == A.LAUNCH_TIME
    assert read["points_per_eth"] == 1000
    assert read["credit_cap_wei"] == 1000 * 10**18


def test_the_deficit_zero_survives_the_seam(tmp_path, clock):
    """Legitimate zero 1 of 3: ethNeededThisHour() returns 0 through ALL of
    grace and on any already-safe judged hour.  It is the answer, not a hole."""
    manager = _manager(tmp_path, clock)
    read = manager._readings(state=_state(hour_needed_wei=0), config=CONFIG)
    assert read["hour_needed_wei"] == 0
    assert read["hour_needed_wei"] is not None


def test_a_silent_hour_reaches_the_series_as_a_zero_rather_than_a_hole(tmp_path, clock):
    """Legitimate zero 2 of 3, and the most important point on the chart: a
    judged hour that took in nothing IS a zero.  hourly_buckets is dense, so
    the silent hour must be PRESENT at 0.0 -- skipping it would draw the curve
    straight across the crash that killed the game.

    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (WP1.3 capture A, the quiet hour crossing).  The capture covers hours 0
    # and 1 only; the hour-3 row below is a captured row with its indexed hour
    # topic and its de-dupe key changed by hand -- the same two words the chain
    # will change for us when capture A lands.
    """
    deposit = next(
        r for r in RPC_ROWS if r["topics"][0].lower() == A.TOPIC_DEPOSITED.lower()
    )
    later = dict(
        deposit,
        topics=[deposit["topics"][0], deposit["topics"][1], "0x" + f"{3:064x}"],
        blockNumber=hex(25_770_499),
        transactionHash="0x" + "3a" * 32,
        logIndex="0x0",
    )
    client = FakeClient(fetch_logs=lambda *_: _sweep([*RPC_ROWS, later]))
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))

    series = manager.cache.get_series("volume_series")
    assert [ts for ts, _v in series] == [A.LAUNCH_TIME + 3600 * h for h in range(4)]
    assert series[2][1] == 0.0                 # hour 2 took in nothing
    assert len(series) == 4                    # ...and is present, not skipped

    read = manager._readings(config=CONFIG, logs=_sweep())
    assert build_signals(read, now_ts=NOW)["volume_series"][2][1] == 0.0


def test_a_credited_delta_above_the_cap_is_a_measurement_not_a_dropped_row(tmp_path, clock):
    """Legitimate zero 3 of 3.  Above the 1000 ETH credit cap a further deposit
    earns creditedDelta == 0 and therefore weightAdded == 0 -- while still
    counting FULLY toward that hour's survival.  A row that is dropped or
    coerced to None here loses the whale from the activity feed and loses its
    ETH from the hour that had to survive on it."""
    from maxpane_dashboard.data.curator_cache import _event_from_dict, _event_to_dict

    cap = CONFIG["credit_cap_wei"]
    capped = DepositEvent(
        contributor="0x" + "c0" * 20,
        hour=1,
        amount_wei=cap + 500 * 10**18,          # 500 ETH past the cap
        credited_delta_wei=0,                   # ...credits nothing more
        weight_added_wei=0,                     # ...and so weighs nothing more
        new_weight_wei=cap,
        tx_count=2,
        hour_total_wei=cap,
        early_bps=19_491,
        block_number=25_770_499,
        tx_hash="0x" + "cc" * 32,
        log_index=0,
        ts=A.LAUNCH_TIME + 3600.0,
    )
    round_tripped = _event_from_dict(_event_to_dict(capped))
    assert round_tripped == capped
    assert round_tripped.credited_delta_wei == 0
    assert round_tripped.weight_added_wei == 0

    manager = _manager(tmp_path, clock)
    manager.cache.store_events([capped], now=NOW)
    read = manager._readings(config=CONFIG, logs=_sweep([]))
    out = build_signals(read, now_ts=NOW)

    row = next(r for r in out["activity_rows"] if r["tx_hash"] == capped.tx_hash)
    assert row["credited_eth"] == 0.0           # a measurement...
    assert row["credited_eth"] is not None      # ...never an outage
    assert row["amount_eth"] == pytest.approx(1500.0)   # the ETH still routed
    assert out["volume_series"][1][1] == pytest.approx(1500.0)


def test_the_latch_reaches_the_seam_even_when_the_live_read_is_gone(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    manager.cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    read = manager._readings(state=None)
    assert read["settled"] is None                      # the live read is gone
    assert read["settlement_record"].settled is True    # the evidence is not


# ---------------------------------------------------------------------------
# WP5.12 — fetch_and_compute: the flat contract
# ---------------------------------------------------------------------------

#: Every combination of the three source groups answering or dying.
_EVERY_FAILURE_COMBINATION = [
    {"state": s, "logs": lg, "wallet": w}
    for s in (True, False)
    for lg in (True, False)
    for w in (True, False)
]


def _scenario_client(scenario) -> FakeClient:
    return FakeClient(
        fetch_state=_state() if scenario["state"] else None,
        fetch_balance=0 if scenario["state"] else None,
        fetch_config=CuratorConfig(
            launch_time=A.LAUNCH_TIME,
            hourly_threshold_wei=5 * 10**18,
            grace_period=86_400,
            hour_duration=3_600,
            min_deposit_wei=5 * 10**16,
            min_escalation_wei=10**17,
            credit_cap_wei=1000 * 10**18,
            first_judged_hour=24,
            points_per_eth=1000,
            deployer=A.DEPLOYER,
        ) if scenario["state"] else None,
        fetch_logs=(lambda *_: _sweep()) if scenario["logs"] else (lambda *_: None),
        fetch_blockscout_logs=lambda *_: [],
        fetch_wallet=_wallet_state() if scenario["wallet"] else None,
    )


def test_it_returns_exactly_curator_keys_always(tmp_path, clock):
    for index, scenario in enumerate(_EVERY_FAILURE_COMBINATION):
        manager = _manager(
            tmp_path / f"s{index}", clock,
            client=_scenario_client(scenario), wallet=WALLET,
        )
        out = asyncio.run(manager.fetch_and_compute())
        assert set(out) == set(CURATOR_KEYS), scenario


def test_no_exception_escapes_when_every_call_raises(tmp_path, clock):
    client = FakeClient(
        fetch_state=RuntimeError("state pool gone"),
        fetch_balance=RuntimeError("balance gone"),
        fetch_config=RuntimeError("config gone"),
        fetch_logs=RuntimeError("logs pool gone"),
        fetch_blockscout_logs=RuntimeError("blockscout gone"),
        fetch_wallet=RuntimeError("wallet gone"),
    )
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    out = asyncio.run(manager.fetch_and_compute())
    assert set(out) == set(CURATOR_KEYS)
    assert out["degraded"] == sorted(SOURCES)
    assert out["phase"] is None
    assert out["contributors_total"] is None
    assert out["leaderboard_rows"] is None


def test_the_manager_divides_to_eth_exactly_once(tmp_path, clock):
    """Models are wei-native; the dict is the presentation boundary.  Two
    divisions is how a number becomes 1e-18 of itself, silently.

    ``build_signals`` owns that division and the cache's series writer owns the
    only other one, so this module's own count is ZERO -- and a division
    appearing here is exactly the second one.
    """
    _EXPECTED_DIVISION_SITES = 0
    src = inspect.getsource(curator_manager)
    assert src.count("/ _WEI") + src.count("/ 10**18") == _EXPECTED_DIVISION_SITES
    assert "_eth(" not in src


def test_an_analytics_failure_is_never_published_as_a_healthy_picture(tmp_path, clock):
    """`_safe_call` absorbs a raise from build_signals and the blank contract
    goes out -- but `degraded` is recomputed from SOURCE health, and the sources
    are fine.  Untouched, the title bar asserts three live sources over a
    payload nothing produced: 49 None values with a fresh `as of HH:MM`.  The
    outermost handler already does the right thing; safe_call intercepts before
    it can be reached."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("analytics on fire")

    client = _scenario_client({"state": True, "logs": True, "wallet": True})
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    original = curator_manager.build_signals
    curator_manager.build_signals = boom
    try:
        out = asyncio.run(manager.fetch_and_compute())
    finally:
        curator_manager.build_signals = original

    assert set(out) == set(CURATOR_KEYS)
    assert out["phase"] is None                      # nothing was produced
    assert out["degraded"] == sorted(SOURCES)        # ...and the banner says so
    assert set(out["degraded"]) <= set(SOURCES)

    # ...and it clears itself once the analytics are back, rather than latching.
    clock.advance(60)
    healthy = asyncio.run(manager.fetch_and_compute())
    assert healthy["phase"] == "grace"
    assert healthy["degraded"] == []


def test_a_key_the_manager_invents_is_dropped_and_logged(tmp_path, clock, caplog):
    """_finalise returns exactly CURATOR_KEYS -- the surf pattern."""
    manager = _manager(tmp_path, clock)
    with caplog.at_level("ERROR"):
        out = manager._finalise({"phase": "grace", "hour_fed_eth": 1.5, "invented": 9})
    assert set(out) == set(CURATOR_KEYS)
    assert out["phase"] == "grace"
    assert "invented" in caplog.text


def test_the_blank_payload_distinguishes_dead_sources_from_empty_ones(tmp_path, clock):
    """A None list means 'source dead'; [] means 'genuinely nothing'.  On a
    blank payload the ROW keys stay None (we did not look) while the SERIES
    keys are [] (an empty history is a fact about this install, not about the
    network)."""
    manager = _manager(tmp_path, clock)
    blank = manager._blank_payload()
    for key in ("leaderboard_rows", "activity_rows", "closest_call_rows", "cluster_rows"):
        assert blank[key] is None
    for key in ("volume_series", "contributors_series"):
        assert blank[key] == []
    assert blank["degraded"] == []


def test_a_healthy_cycle_publishes_the_chain_values_it_read(tmp_path, clock):
    manager = _manager(
        tmp_path, clock, client=_scenario_client({"state": True, "logs": True, "wallet": True}),
        wallet=WALLET,
    )
    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == []
    assert out["phase"] == "grace"
    assert out["current_hour"] == 4
    assert out["contributors_total"] == 143            # the contract's own counter
    assert out["hourly_threshold_eth"] == 5.0          # read live, never hardcoded
    assert out["first_judged_hour"] == 24
    assert out["early_multiplier_x"] == pytest.approx(1.9491)
    assert 0 < len(out["leaderboard_rows"]) <= LEADERBOARD_LIMIT
    assert out["volume_series"][0][0] == A.LAUNCH_TIME
    assert out["as_of_hhmm"] is not None
    assert out["you_required_next_eth"] == pytest.approx(4.1)


def test_the_fast_tier_is_spaced_by_its_own_ttl_not_by_the_poll_interval(tmp_path, clock):
    """TIER_TTL_SECONDS['fast'] is 15 s (PRD §5) and `--poll-interval` accepts
    5, so an ungated fast half triples the declared request budget against
    keyless public endpoints -- and the 15 s failure backoff never applies to a
    rate-limited host at all.  Ten cycles inside one TTL window are one round of
    requests, and the readings in between are the ones that round returned."""
    from maxpane_dashboard.data.curator_cache import TIER_TTL_SECONDS

    client = _scenario_client({"state": True, "logs": True, "wallet": True})
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    first = asyncio.run(manager.fetch_and_compute())
    for _ in range(9):
        clock.advance(1)
        out = asyncio.run(manager.fetch_and_compute())
        # ...and the picture does not flicker to `unavailable` in between.
        assert out["current_hour"] == first["current_hour"]
        assert out["phase"] == first["phase"]
        assert out["you_required_next_eth"] == first["you_required_next_eth"]

    names = [name for name, *_ in client.calls]
    assert names.count("fetch_state") == 1
    assert names.count("fetch_balance") == 1
    assert names.count("fetch_wallet") == 1

    clock.advance(TIER_TTL_SECONDS["fast"])
    asyncio.run(manager.fetch_and_compute())
    names = [name for name, *_ in client.calls]
    assert names.count("fetch_state") == 2
    assert names.count("fetch_wallet") == 2


def test_a_skipped_fast_tick_never_re_serves_a_reading_from_across_an_outage(tmp_path, clock):
    """The retained round is not a last-good store.  It is cleared by a failed
    attempt, so the tier sitting out its 15 s BACKOFF renders unavailable rather
    than a number from before the outage wearing a live face (PRD §11 row 1)."""
    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    manager = _manager(tmp_path, clock, client=client)
    healthy = asyncio.run(manager.fetch_and_compute())
    assert healthy["current_hour"] == 4

    client.answers["fetch_state"] = None
    client.answers["fetch_balance"] = None
    clock.advance(15)
    dead = asyncio.run(manager.fetch_and_compute())
    assert dead["current_hour"] is None
    assert SOURCE_STATE in dead["degraded"]

    clock.advance(1)                                   # inside the backoff
    still = asyncio.run(manager.fetch_and_compute())
    assert still["current_hour"] is None
    assert SOURCE_STATE in still["degraded"]


def test_a_nonzero_balance_never_reaches_a_volume_field(tmp_path, clock):
    """H5.  1.5 ETH of forced ETH is an anomaly -- somebody selfdestructed into
    a contract that refunds every wei in-tx -- and it belongs to exactly one
    key.  volume is ROUTED, and the hour total is folded from logs."""
    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    client.answers["fetch_balance"] = 1_500_000_000_000_000_000
    manager = _manager(tmp_path, clock, client=client)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["forced_eth"] == 1.5
    assert out["volume_routed_eth"] == 8401.0          # stats(), not the balance
    assert out["hour_fed_eth"] != 1.5
    for key in ("volume_routed_eth", "hour_fed_eth", "top_points", "contributors_total"):
        assert out[key] != 1.5, key


def test_the_series_survive_a_restart_and_reach_the_payload(tmp_path, clock):
    path = tmp_path / "curator_cache.json"
    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    first = CuratorManager(
        client=client, cache=CuratorCache(path=str(path), clock=clock), clock=clock
    )
    out = asyncio.run(first.fetch_and_compute())
    series = out["volume_series"]
    assert series
    asyncio.run(first.close())

    dead = FakeClient(fetch_state=None, fetch_balance=None, fetch_config=None,
                      fetch_logs=lambda *_: None, fetch_blockscout_logs=lambda *_: None)
    second = CuratorManager(
        client=dead, cache=CuratorCache(path=str(path), clock=clock), clock=clock
    )
    again = asyncio.run(second.fetch_and_compute())
    assert again["volume_series"] == series
    assert again["degraded"] == [SOURCE_LOGS, SOURCE_STATE]


def test_a_blockscout_row_newer_than_the_sweep_is_not_a_gap(tmp_path, clock):
    """The two sources are read minutes apart on different transports and
    Blockscout is often ahead.  Only a row INSIDE the range we claim to have
    folded is evidence that we missed something -- otherwise every cross-check
    would condemn the fold for being one block younger."""
    newer = dict(RPC_ROWS[2], blockNumber=hex(25_999_999),
                 transactionHash="0x" + "ee" * 32, logIndex="0x1")
    client = FakeClient(
        fetch_logs=lambda *_: _sweep(to_block=25_770_500),
        fetch_blockscout_logs=lambda *_: [newer],
    )
    manager = _manager(tmp_path, clock, client=client)
    asyncio.run(manager._pool_logs({"medium"}, NOW, CONFIG))
    out = asyncio.run(manager._pool_crosscheck({"slow"}, NOW, _state(), CONFIG))
    assert out["gap_block"] is None
    assert manager._fold_stale is False


# ---------------------------------------------------------------------------
# set_wallet() — the runtime switch behind the screen's `w` key
# ---------------------------------------------------------------------------

OTHER_WALLET = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"


def test_set_wallet_moves_the_address_and_says_so(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    assert manager.wallet is None

    assert manager.set_wallet(WALLET) is True
    assert manager.wallet == WALLET


def test_set_wallet_normalises_empty_to_none_and_treats_it_as_no_change(tmp_path, clock):
    """`""` and `None` both mean *no wallet*, so neither is a switch away from
    the other -- a refetch and a dropped last-good would both be waste."""
    manager = _manager(tmp_path, clock)
    assert manager.set_wallet("") is False
    assert manager.wallet is None

    manager.set_wallet(WALLET)
    assert manager.set_wallet("") is True
    assert manager.wallet is None


def test_re_typing_the_same_address_is_a_no_op(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    manager.set_wallet(WALLET)
    manager.cache.store_last_good(SLOT_WALLET, {"address": WALLET})
    manager.cache.mark_fetched(TIER_FAST)

    assert manager.set_wallet(WALLET) is False

    # Nothing was thrown away for a keypress that changed nothing.
    assert manager.cache.get_last_good(SLOT_WALLET) is not None
    assert manager.cache.is_fresh(TIER_FAST) is True


def test_switching_wallets_cannot_leave_the_previous_wallets_row_on_screen(tmp_path, clock):
    """The bug this exists to prevent: `_fast_wallet` is re-served for the rest
    of the fast tier's TTL, so without clearing it the old wallet's rank, credit
    and `next >=` render for up to 15 s under the *new* address."""
    manager = _manager(tmp_path, clock, wallet=WALLET)
    manager._fast_wallet = _wallet_state(address=WALLET, points=30_035)

    manager.set_wallet(OTHER_WALLET)

    assert manager._fast_wallet is None


def test_switching_wallets_drops_the_previous_wallets_last_good(tmp_path, clock):
    """Its payload is literally `{"address": <the old one>}`.  Served behind an
    `as of HH:MM` marker it would say "stale" while the number says "yours"."""
    manager = _manager(tmp_path, clock, wallet=WALLET)
    manager.cache.store_last_good(SLOT_WALLET, {"address": WALLET})

    manager.set_wallet(OTHER_WALLET)

    assert manager.cache.get_last_good(SLOT_WALLET) is None


def test_a_switched_wallet_reads_degraded_until_something_is_read_about_it(tmp_path, clock):
    """Not "healthy and empty" -- that would render rank -- for an address
    nobody has asked about yet.  Dropping the old last-good is what produces
    this, and it is why `set_wallet` does not bother clearing the old address's
    entry in `_failed_groups`: `_degraded` already degrades a group with no
    last-good, so the two are indistinguishable here."""
    client = FakeClient(fetch_wallet=lambda address: _wallet_state(address=address))
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    manager.cache.store_last_good(SLOT_WALLET, {"address": WALLET})
    manager._note(SOURCE_WALLET, ok=True)
    assert SOURCE_WALLET not in manager._degraded()

    manager.set_wallet(OTHER_WALLET)
    assert SOURCE_WALLET in manager._degraded()

    asyncio.run(manager._pool_wallet(NOW))
    assert SOURCE_WALLET not in manager._degraded()


def test_switching_wallets_expires_the_fast_tier_so_the_next_cycle_refetches(tmp_path, clock):
    """Without this the keypress looks like it worked and the row stays dark:
    a tier with 12 of its 15 seconds left is "fresh", so nothing is fetched."""
    manager = _manager(tmp_path, clock, wallet=WALLET)
    manager.cache.mark_fetched(TIER_FAST)
    assert manager.cache.is_fresh(TIER_FAST) is True

    manager.set_wallet(OTHER_WALLET)

    assert manager.cache.is_due(TIER_FAST) is True


def test_the_new_wallet_is_the_one_the_next_cycle_actually_reads(tmp_path, clock):
    """End to end through the real pool: the six YOU views are called with the
    address the reader just set, not the one the manager was constructed with."""
    client = FakeClient(fetch_wallet=lambda address: _wallet_state(address=address))
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)

    manager.set_wallet(OTHER_WALLET)
    state = asyncio.run(manager._pool_wallet(NOW))

    assert ("fetch_wallet", OTHER_WALLET) in client.calls
    assert ("fetch_wallet", WALLET) not in client.calls
    assert state.address == OTHER_WALLET


def test_clearing_the_wallet_makes_the_next_cycle_read_nothing(tmp_path, clock):
    client = FakeClient(fetch_wallet=_wallet_state())
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)

    assert manager.set_wallet(None) is True
    assert asyncio.run(manager._pool_wallet(NOW)) is None
    assert client.calls == []
    assert SOURCE_WALLET not in manager._degraded()


# ---------------------------------------------------------------------------
# Reverse ENS labelling (PRD §13 A9)
# ---------------------------------------------------------------------------


def _payload_with_addresses(manager) -> dict:
    return {
        "leaderboard_rows": [{"address": WALLET, "name": None}],
        "activity_rows": [{"address": OTHER_WALLET, "name": None}],
        "closest_call_rows": [{"savior": WALLET, "savior_name": None}],
        "whale_wallet": OTHER_WALLET,
        "last_saved_wallet": WALLET,
    }


def test_only_the_addresses_on_screen_are_resolved(tmp_path, clock):
    """The contributor table is thousands of wallets for ten visible rows."""
    manager = _manager(tmp_path, clock, wallet=WALLET)
    payload = _payload_with_addresses(manager)
    payload["leaderboard_rows"].append({"address": "0x" + "11" * 20, "name": None})

    wanted = manager._rendered_addresses(payload)

    assert set(a.lower() for a in wanted) == {
        WALLET.lower(), OTHER_WALLET.lower(), "0x" + "11" * 20,
    }


def test_a_resolved_name_reaches_every_place_that_address_renders(tmp_path, clock):
    client = FakeClient(fetch_ens_names=lambda addrs: {WALLET.lower(): "surfsurf.eth"})
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    payload = _payload_with_addresses(manager)

    asyncio.run(manager._label_with_ens(payload, NOW))

    assert payload["leaderboard_rows"][0]["name"] == "surfsurf.eth"
    assert payload["closest_call_rows"][0]["savior_name"] == "surfsurf.eth"
    assert payload["last_saved_ens"] == "surfsurf.eth"
    assert payload["you_ens"] == "surfsurf.eth"
    # ...and an address with no name is left alone rather than mislabelled.
    assert payload["activity_rows"][0]["name"] is None
    assert payload.get("whale_ens") is None


def test_a_failed_resolution_leaves_every_row_exactly_as_it_was(tmp_path, clock):
    """Names are decoration: the failure costs the label, never the row."""
    client = FakeClient(fetch_ens_names=RuntimeError("all endpoints down"))
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)
    payload = _payload_with_addresses(manager)

    asyncio.run(manager._label_with_ens(payload, NOW))

    assert payload["leaderboard_rows"][0]["name"] is None
    assert payload["you_ens"] is None if "you_ens" in payload else True


def test_an_address_with_no_name_is_asked_once_not_every_tick(tmp_path, clock):
    """Most wallets have no reverse record.  Without the miss half, every one of
    them is re-queried forever, because "absent from the map" and "never asked"
    look identical."""
    asked: list[list[str]] = []

    def resolve(addrs):
        asked.append(list(addrs))
        return {}

    client = FakeClient(fetch_ens_names=resolve)
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)

    asyncio.run(manager._label_with_ens(_payload_with_addresses(manager), NOW))
    asyncio.run(manager._label_with_ens(_payload_with_addresses(manager), NOW + 30))

    assert len(asked) == 1, "a known miss was asked again"


def test_a_known_miss_expires_so_a_new_registration_is_picked_up(tmp_path, clock):
    asked: list[list[str]] = []

    def resolve(addrs):
        asked.append(list(addrs))
        return {}

    client = FakeClient(fetch_ens_names=resolve)
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)

    asyncio.run(manager._label_with_ens(_payload_with_addresses(manager), NOW))
    later = NOW + ens.MISS_TTL_SECONDS + 1
    asyncio.run(manager._label_with_ens(_payload_with_addresses(manager), later))

    assert len(asked) == 2


def test_a_fresh_name_is_not_re_resolved(tmp_path, clock):
    asked: list[list[str]] = []

    def resolve(addrs):
        asked.append(list(addrs))
        return {a.lower(): "surfsurf.eth" for a in addrs}

    client = FakeClient(fetch_ens_names=resolve)
    manager = _manager(tmp_path, clock, client=client, wallet=WALLET)

    asyncio.run(manager._label_with_ens(_payload_with_addresses(manager), NOW))
    payload = _payload_with_addresses(manager)
    asyncio.run(manager._label_with_ens(payload, NOW + 60))

    assert len(asked) == 1
    # ...and the cached name still labels the second payload.
    assert payload["leaderboard_rows"][0]["name"] == "surfsurf.eth"


# ---------------------------------------------------------------------------
# WP3.3 — the detached Tier-B+C analysis sweep (_spawn_crosscheck's pattern)
# ---------------------------------------------------------------------------


from maxpane_dashboard.data import curator_clusters  # noqa: E402
from maxpane_dashboard.data.curator_cache import (  # noqa: E402
    SLOT_CLUSTERS,
    TIER_ANALYSIS,
)
from tests.data.test_curator_clusters import (  # noqa: E402
    AnalysisRoutes,
    FARM_MEMBERS,
    CONTROLS as FARM_CONTROLS,
    STRANGER as FARM_STRANGER,
    farm_analysis,
    farm_events,
    farm_first_deposits,
    no_sleep,
)

#: The once-tier payload the sweep reads, as `_pool_config` now stores it:
#: the readings' keys plus the minimum the preset refuses to run without.
ANALYSIS_CONFIG = {**CONFIG, "min_deposit_wei": 5 * 10**16}


def _analysis_manager(tmp_path, clock, *, routes=None, wallet=None):
    """A manager whose fold is the farm: cache pre-seeded, empty log sweeps.

    The state double's counters agree with the nine seeded events — the
    cross-check compares the fold against ``stats()``, and a double whose
    counter says 222 over a nine-event fold is a fixture accusing itself.
    """
    client = _scenario_client(
        {"state": True, "logs": True, "wallet": bool(wallet)}
    )
    client.answers["fetch_state"] = _state(tx_count=9, contributors=9)
    client.answers["fetch_logs"] = lambda *_: _sweep([], to_block=25_770_500)
    manager = _manager(
        tmp_path,
        clock,
        client=client,
        wallet=wallet,
        analysis_transport=routes.transport if routes is not None else None,
        analysis_sleep=no_sleep,
    )
    manager.cache.store_events(farm_events(), now=NOW)
    manager.cache.store_first_deposits(farm_first_deposits())
    return manager


def test_the_config_slot_carries_the_minimum_and_the_readings_do_not(tmp_path, clock):
    """R13's live read travels through the config slot to the sweep — and only
    there: READING_KEYS is frozen and build_signals never sees the key."""
    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    manager = _manager(tmp_path, clock, client=client)
    payload = asyncio.run(manager._pool_config({"once"}, NOW))
    assert payload["min_deposit_wei"] == 5 * 10**16
    readings = manager._readings(config=payload)
    assert "min_deposit_wei" not in readings


def test_spawn_analysis_starts_one_task_and_never_stacks_a_second(tmp_path, clock):
    routes = AnalysisRoutes(blocking=True)
    manager = _analysis_manager(tmp_path, clock, routes=routes)

    async def _run():
        task = manager._spawn_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG)
        assert task is not None
        await asyncio.wait_for(routes.started.wait(), timeout=5)
        again = manager._spawn_analysis(
            {TIER_ANALYSIS}, NOW + 1, ANALYSIS_CONFIG
        )
        assert again is task, "one in flight, never two"
        routes.release.set()
        await asyncio.wait_for(task, timeout=5)
        assert manager.cache.analysis_last_good() is not None

    asyncio.run(_run())


def test_the_analysis_tier_gates_the_sweep(tmp_path, clock):
    manager = _analysis_manager(tmp_path, clock)

    async def _run():
        assert (
            manager._spawn_analysis({"fast", "medium"}, NOW, ANALYSIS_CONFIG)
            is None
        )
        assert manager._analysis_task is None

    asyncio.run(_run())


def test_the_sweep_publishes_into_the_slot_with_the_spawn_time_stamp(tmp_path, clock):
    """The payload built before the sweep lands is the supported not-yet-run
    state; the slot's stamp is the SPAWN time, never the completion time."""
    routes = AnalysisRoutes()
    manager = _analysis_manager(tmp_path, clock, routes=routes)

    async def _run():
        out = await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert out["operator_rows"] is None            # not-yet-run this cycle
        assert out["analysis_as_of_hhmm"] is None
        assert manager._analysis_task is not None
        await asyncio.wait_for(manager._analysis_task, timeout=5)

        entry = manager.cache.analysis_last_good()
        assert entry is not None
        assert entry.ts == NOW                          # spawn-time stamp
        payload = entry.payload
        assert payload["operators_count"] == 1          # funding linked the farm
        assert payload["groups"][0]["size"] == len(FARM_MEMBERS)
        # The cursor rides in the slot: coverage extends across sweeps.
        assert set(payload["enrichment"]["funding"]) >= set(FARM_MEMBERS)
        assert payload["enrichment"]["txs"]
        assert routes.gets and routes.posts, (
            "the sweep drives sybilkit.sources through the injected transport"
        )

    asyncio.run(_run())


def test_the_sweep_borrows_the_real_clients_own_session_in_production(tmp_path, clock):
    """The **production** half of ``_analysis_session`` — the branch every
    other sweep test skips.

    Those tests inject an ``analysis_transport``, so ``_analysis_session``
    returns the injected branch and the borrowed-``_client`` path is exercised
    only by the live smoke.  Here ``analysis_transport`` is ``None`` (so the
    injected branch is *not* taken) and the manager's client is a **real**
    :class:`CuratorClient` whose own ``httpx`` session is MockTransport-backed:
    the sweep must borrow that session, fetch through it, and publish into
    ``SLOT_CLUSTERS`` — with no socket, because the transport is a mock.

    The borrowed attribute is asserted by name (``_client``): a future
    ``CuratorClient`` refactor that renames it would silently drop the sweep to
    tier A, and this reddens instead.
    """
    import httpx
    from maxpane_dashboard.data.curator_client import CuratorClient

    routes = AnalysisRoutes()
    http = httpx.AsyncClient(transport=routes.transport)
    client = CuratorClient(http_client=http)

    # The seam this test exists to pin: production borrows the real client's
    # own `_client`.  If the attribute is renamed, this fails here rather than
    # letting the sweep quietly run tier A only.
    assert getattr(client, "_client", None) is http

    manager = _manager(
        tmp_path,
        clock,
        client=client,
        analysis_transport=None,           # force the production branch
        analysis_sleep=no_sleep,
    )
    assert manager._analysis_session() == (http, None)

    manager.cache.store_events(farm_events(), now=NOW)
    manager.cache.store_first_deposits(farm_first_deposits())

    async def _run():
        try:
            return await asyncio.wait_for(
                manager._pool_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG),
                timeout=5,
            )
        finally:
            await http.aclose()

    out = asyncio.run(_run())
    assert out["swept"] is True

    # Fetched through the borrowed session: the mock transport recorded both
    # wire shapes, which only the production `_client` path could have driven.
    assert routes.posts and routes.gets, (
        "the sweep drove sybilkit.sources through the real client's own _client"
    )
    # ...and published into SLOT_CLUSTERS, funding-linked exactly as the
    # injected-branch sibling asserts.
    entry = manager.cache.get_last_good(SLOT_CLUSTERS)
    assert entry is not None
    assert entry.payload["operators_count"] == 1
    assert set(entry.payload["enrichment"]["funding"]) >= set(FARM_MEMBERS)


def test_the_first_payload_is_not_behind_the_analysis_read(tmp_path, clock):
    """The mandated first-paint guard: a funding pass is minutes long, and
    awaiting it in-cycle is exactly the 201-second blank SIGNALS rail the
    cross-check already taught this manager about.  Awaiting the sweep inside
    `_cycle` makes the five-second timeout here fire."""
    routes = AnalysisRoutes(blocking=True)
    manager = _analysis_manager(tmp_path, clock, routes=routes)

    async def _run():
        out = await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert set(out) == set(CURATOR_KEYS)
        assert out["leaderboard_rows"], "the fold that drives every panel"

        await asyncio.wait_for(routes.started.wait(), timeout=5)
        task = manager._analysis_task
        assert not task.done()

        # A second cycle while it fetches does not stack a second sweep.
        clock.advance(1)
        await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert manager._analysis_task is task

        routes.release.set()
        await asyncio.wait_for(task, timeout=5)
        assert manager.cache.analysis_last_good() is not None

    asyncio.run(_run())


def test_close_cancels_both_detached_tasks_and_saves(tmp_path, clock):
    """Quitting mid-sweep is the common case when a sweep takes minutes: both
    detached reads hold the client, so both are cancelled and awaited before
    the sockets go, and the cache is still saved."""
    routes = AnalysisRoutes(blocking=True)
    scenario = _scenario_client({"state": True, "logs": True, "wallet": False})
    client = _BlockingCrossCheck(
        [],
        fetch_logs=lambda *_: _sweep([], to_block=25_770_500),
        fetch_state=_state(),
        fetch_config=scenario.answers["fetch_config"],
    )
    manager = _manager(
        tmp_path,
        clock,
        client=client,
        analysis_transport=routes.transport,
        analysis_sleep=no_sleep,
    )
    manager.cache.store_events(farm_events(), now=NOW)
    manager.cache.store_first_deposits(farm_first_deposits())

    async def _run():
        await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        await asyncio.wait_for(routes.started.wait(), timeout=5)
        await asyncio.wait_for(client.started.wait(), timeout=5)
        a_task, c_task = manager._analysis_task, manager._crosscheck_task
        assert not a_task.done() and not c_task.done()

        await asyncio.wait_for(manager.close(), timeout=5)
        assert a_task.done() and a_task.cancelled()
        assert c_task.done() and c_task.cancelled()
        assert manager._analysis_task is None
        assert manager._crosscheck_task is None
        assert client.closed is True
        assert os.path.exists(manager.cache.path)

    asyncio.run(_run())


def test_a_sweep_with_nothing_to_analyze_backs_off_instead_of_spinning(tmp_path, clock):
    """No events (or no live-read config) is 'cannot run yet', not a failed
    sweep: the tier is spaced so the offer is not re-made every cycle, and no
    degradation banner lights for it."""
    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    client.answers["fetch_logs"] = lambda *_: _sweep([], to_block=25_770_500)
    manager = _manager(tmp_path, clock, client=client)  # cache empty: no events

    async def _run():
        task = manager._spawn_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(_run())
    assert manager.cache.analysis_last_good() is None
    assert manager._analysis_failed is False
    from maxpane_dashboard.data.curator_cache import TIER_FAILURE_BACKOFF_SECONDS

    assert TIER_ANALYSIS not in manager.cache.tiers_due(NOW + 1)
    assert TIER_ANALYSIS in manager.cache.tiers_due(
        NOW + TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS] + 1
    )


def test_without_a_session_the_sweep_publishes_tier_a_only_and_fetches_nothing(
    tmp_path, clock
):
    """A client double with no HTTP session and no injected transport means the
    sweep may not fetch — it still publishes the tier-A answer, whose losses
    are honest (the two-family gate simply finds less)."""
    manager = _analysis_manager(tmp_path, clock)      # no routes

    async def _run():
        task = manager._spawn_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(_run())
    payload = manager.cache.analysis_last_good().payload
    assert payload["operators_count"] == 0            # amount alone never convicts
    assert payload["enrichment"]["funding"] == {}
    assert payload["enrichment"]["txs"] == {}


# ---------------------------------------------------------------------------
# WP3.4 — the merge into the flat dict (and the keys-FILLED criterion)
# ---------------------------------------------------------------------------


def _store_farm_slot(manager, *, ts=NOW, wallet=None, **overrides):
    payload = curator_clusters.slot_payload(farm_analysis(wallet=wallet))
    payload.update(overrides)
    manager.cache.store_analysis(payload, ts=ts)
    return payload


def _legacy_clean_slot(count=1_200):
    addresses = ["0x" + f"{rank:040x}" for rank in range(1, count + 1)]
    rows = [
        ContributorRow(
            address=address,
            weight_wei=rank,
            credit_wei=rank * 10**18,
            tx_count=1,
            first_hour=0,
            first_index=rank,
            points=10_000 - rank,
        )
        for rank, address in enumerate(addresses, start=1)
    ]
    slot = {
        "operator_rows": [],
        "segment_rows": [],
        "clean_list_rows": [
            {
                "clean_rank": rank,
                "address": address,
                "points": 10_000 - rank,
                "credit_eth": float(rank),
                "name": None,
            }
            for rank, address in enumerate(addresses[:20], start=1)
        ],
        "operators_count": 0,
        "clean_points": sum(10_000 - rank for rank in range(1, count + 1)),
        "clean_contributors": count,
        "points_total": sum(10_000 - rank for rank in range(1, count + 1)),
        "flagged_points_share_pct": 0.0,
        "groups": [],
        "clean_ranks": {
            address.lower(): rank
            for rank, address in enumerate(addresses, start=1)
        },
    }
    return slot, rows


def test_a_legacy_twenty_row_clean_list_expands_from_the_cached_fold(
    tmp_path, clock
):
    """A pre-100 cache must not pin the list at its old rendered-row cap."""
    manager = _manager(tmp_path, clock)
    stored, rows = _legacy_clean_slot()
    old_ts = NOW - 3_600
    manager.cache.store_fold(rows, last_block=None, now=NOW)
    manager.cache.store_analysis(stored, ts=old_ts)

    payload = {"leaderboard_rows": []}
    manager._merge_analysis(payload)

    assert len(payload["clean_list_rows"]) == 1_000
    assert [row["clean_rank"] for row in payload["clean_list_rows"]] == list(
        range(1, 1_001)
    )
    assert payload["clean_list_rows"][-1] == {
        "clean_rank": 1_000,
        "address": "0x" + f"{1_000:040x}",
        "points": 9_000,
        "credit_eth": 1_000.0,
        "name": None,
        "weight_eth": 0.000000000000001,
        "tx_count": 1,
        "first_hour": 0,
        "first_index": 1_000,
    }
    migrated = manager.cache.analysis_last_good()
    assert migrated.ts == old_ts
    assert len(migrated.payload["clean_list_rows"]) == 1_000
    assert len(stored["clean_list_rows"]) == 20, "the old payload was mutated"


def test_an_incomplete_fold_does_not_replace_a_legacy_clean_list(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    stored, rows = _legacy_clean_slot()
    manager.cache.store_fold(rows[:50], last_block=None, now=NOW)
    manager.cache.store_analysis(stored, ts=NOW)

    payload = {"leaderboard_rows": []}
    manager._merge_analysis(payload)

    assert len(payload["clean_list_rows"]) == 20
    assert len(manager.cache.analysis_last_good().payload["clean_list_rows"]) == 20


def test_full_list_exports_ignore_display_caps_without_growing_the_analysis_slot(
    tmp_path, clock
):
    manager = _manager(tmp_path, clock)
    stored, rows = _legacy_clean_slot(count=1_200)
    manager.cache.store_fold(rows, last_block=None, now=NOW)
    manager.cache.store_first_deposits(
        [
            {"contributor": row.address, "index": index, "ts": NOW}
            for index, row in enumerate(rows, start=1)
        ]
    )
    manager.cache.store_last_good(SLOT_LOGS, {}, ts=NOW)
    manager.cache.store_analysis(stored, ts=NOW)

    raw = manager.full_list_rows(cleaned=False)
    clean = manager.full_list_rows(cleaned=True)

    assert len(raw) == 1_200
    assert len(clean) == 1_200
    assert raw[-1]["rank"] == 1_200
    assert clean[-1]["clean_rank"] == 1_200
    assert raw[-1]["first_index"] == 1_200
    assert clean[-1]["first_index"] == 1_200
    assert set(raw[-1]) == set(CURATOR_ROW_KEYS["leaderboard_rows"])
    assert set(clean[-1]) == set(CURATOR_ROW_KEYS["clean_list_rows"])
    assert len(manager.cache.analysis_last_good().payload["clean_list_rows"]) == 20


def test_the_configured_wallet_gets_a_complete_list_row_beyond_the_display_cap(
    tmp_path, clock
):
    stored, rows = _legacy_clean_slot(count=1_200)
    wallet = rows[-1].address
    manager = _manager(tmp_path, clock, wallet=wallet)
    manager.cache.store_fold(rows, last_block=None, now=NOW)
    manager.cache.store_analysis(stored, ts=NOW)
    payload = {
        "leaderboard_rows": [],
        "you_rank": 1_200,
        "you_points": rows[-1].points,
        "you_credit_eth": 1_200.0,
        "you_weight_eth": rows[-1].weight_wei / 10**18,
        "you_tx_count": 1,
        "you_first_hour": 0,
    }

    manager._merge_analysis(payload)

    assert payload["you_list_row"] == {
        "rank": 1_200,
        "clean_rank": 1_200,
        "address": wallet,
        "points": rows[-1].points,
        "credit_eth": 1_200.0,
        "weight_eth": rows[-1].weight_wei / 10**18,
        "tx_count": 1,
        "first_hour": 0,
        "first_index": 1_200,
        "name": None,
        "link_conf": "clean",
    }


def test_full_list_exports_keep_unavailable_and_empty_distinct(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    assert manager.full_list_rows(cleaned=False) is None
    assert manager.full_list_rows(cleaned=True) is None

    manager.cache.store_last_good(SLOT_LOGS, {}, ts=NOW)
    empty_slot, empty_fold = _legacy_clean_slot(count=0)
    manager.cache.store_fold(empty_fold, last_block=None, now=NOW)
    manager.cache.store_analysis(empty_slot, ts=NOW)

    assert manager.full_list_rows(cleaned=False) == []
    assert manager.full_list_rows(cleaned=True) == []


def test_an_incomplete_fold_cannot_masquerade_as_a_full_clean_export(
    tmp_path, clock
):
    manager = _manager(tmp_path, clock)
    stored, rows = _legacy_clean_slot(count=1_200)
    manager.cache.store_fold(rows[:-1], last_block=None, now=NOW)
    manager.cache.store_analysis(stored, ts=NOW)

    assert manager.full_list_rows(cleaned=True) is None


def test_an_incomplete_fold_cannot_masquerade_as_a_full_raw_export(
    tmp_path, clock
):
    manager = _manager(tmp_path, clock)
    _stored, rows = _legacy_clean_slot(count=3)
    manager.cache.store_fold(rows[:2], last_block=None, now=NOW)
    manager.cache.store_first_deposits(
        [
            {"contributor": row.address, "index": index, "ts": NOW}
            for index, row in enumerate(rows, start=1)
        ]
    )
    manager.cache.store_last_good(SLOT_LOGS, {}, ts=NOW)

    assert manager.full_list_rows(cleaned=False) is None


def test_with_no_analysis_last_good_every_analysis_key_is_none_never_empty(
    tmp_path, clock
):
    """The dead-vs-empty pin, and the WP3.4 bite's designated victim: a
    not-yet-run analysis must be None — an [] here is an empty table asserting
    nobody is linked, drawn from a read that never happened."""
    manager = _analysis_manager(tmp_path, clock, wallet=WALLET)
    out = asyncio.run(manager.fetch_and_compute())
    for key in ("operator_rows", "segment_rows", "clean_list_rows"):
        assert out[key] is None, key
    for key in (
        "operators_count",
        "clean_points",
        "clean_contributors",
        "points_total",
        "analysis_as_of_hhmm",
        "you_linked_state",
        "you_linked_reasons",
        "you_linked_group_size",
        "you_clean_rank",
    ):
        assert out[key] is None, key
    # R9: link_conf is seeded None on every leaderboard row — present, never
    # missing, never a confident empty.
    for row in out["leaderboard_rows"]:
        assert "link_conf" in row and row["link_conf"] is None


def test_with_an_analysis_last_good_every_one_of_the_twelve_keys_is_filled(
    tmp_path, clock
):
    """The missing-red hazard, closed head-on (controller ruling 3): the
    totality test stayed green while all twelve keys were None, so this one
    asserts the FILLING — rows populated, counts real ints, the marker a real
    HH:MM — for both reader states."""
    import re

    # --- a linked reader ---------------------------------------------------
    manager = _analysis_manager(tmp_path / "linked", clock, wallet=FARM_MEMBERS[0])
    _store_farm_slot(manager)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["operator_rows"] and isinstance(out["operator_rows"], list)
    assert out["operator_rows"][0]["size"] == len(FARM_MEMBERS)
    assert out["segment_rows"] and out["segment_rows"][0]["label"]
    assert out["clean_list_rows"] and out["clean_list_rows"][0]["clean_rank"] == 1
    for key, expected in (
        ("operators_count", 1),
        ("clean_points", None),
        ("clean_contributors", 3),
        ("points_total", None),
    ):
        value = out[key]
        assert isinstance(value, int) and not isinstance(value, bool), key
        if expected is not None:
            assert value == expected, key
    assert out["points_total"] > out["clean_points"] > 0
    assert re.fullmatch(r"\d{2}:\d{2}", out["analysis_as_of_hhmm"])
    assert out["you_linked_state"] == "linked"
    assert out["you_linked_reasons"], "pattern-language evidence, not empty"
    assert out["you_linked_group_size"] == len(FARM_MEMBERS)
    assert out["you_clean_rank"] is None          # removed from the list: real

    # --- a clean reader ----------------------------------------------------
    manager2 = _analysis_manager(tmp_path / "clean", clock, wallet=FARM_CONTROLS[0])
    _store_farm_slot(manager2)
    out2 = asyncio.run(manager2.fetch_and_compute())
    assert out2["you_linked_state"] == "clean"
    assert out2["you_linked_reasons"] == []       # analyzed, not linked
    assert out2["you_linked_group_size"] is None
    assert isinstance(out2["you_clean_rank"], int)


def test_the_farm_share_prefers_the_analysis_value_when_it_has_run(
    tmp_path, clock
):
    """Override-with-fallback (plan §6 risk 2, pre-ruled): the analysis
    last-good's share wins when present; Tier A's build_signals value stands
    otherwise — so FARM and OPERATORS tell one story once the sweep has run."""
    manager = _analysis_manager(tmp_path, clock)
    before = asyncio.run(manager.fetch_and_compute())
    tier_a_share = before["flagged_points_share_pct"]
    assert tier_a_share != 43.25                  # guard: the override is visible

    _store_farm_slot(manager, flagged_points_share_pct=43.25)
    clock.advance(1)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["flagged_points_share_pct"] == 43.25

    # ...and an analysis that carries no share leaves Tier A's value standing.
    _store_farm_slot(manager, flagged_points_share_pct=None, ts=NOW + 2)
    clock.advance(1)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["flagged_points_share_pct"] == tier_a_share


def test_link_conf_is_graded_from_the_slot_and_flagged_stays_tier_a(
    tmp_path, clock
):
    manager = _analysis_manager(tmp_path, clock)
    _store_farm_slot(manager)
    out = asyncio.run(manager.fetch_and_compute())
    by_addr = {row["address"].lower(): row for row in out["leaderboard_rows"]}
    member = by_addr[FARM_MEMBERS[0]]
    control = by_addr[FARM_CONTROLS[0]]
    assert member["link_conf"] == "high"
    assert control["link_conf"] == "clean"
    assert isinstance(member["flagged"], bool)    # Tier A's bool, untouched


def test_a_resolved_name_reaches_the_clean_list_rows(tmp_path, clock):
    """`name` on a clean-list row is the leaderboard's identity cell exactly:
    filled by the manager's ENS merge, never by the adapter."""
    manager = _analysis_manager(tmp_path, clock)
    named = FARM_CONTROLS[0]
    manager.client.answers["fetch_ens_names"] = lambda addrs: (
        {named: "his-dudeness.eth"} if named in {a.lower() for a in addrs} else {}
    )
    _store_farm_slot(manager)
    out = asyncio.run(manager.fetch_and_compute())
    row = next(
        r for r in out["clean_list_rows"] if r["address"].lower() == named
    )
    assert row["name"] == "his-dudeness.eth"


def test_the_merge_never_mutates_the_persisted_slot_payload(tmp_path, clock):
    """The merge copies rows out of the slot: the ENS fill writes names onto
    the PAYLOAD's rows, and a name written into the cached slot would be
    persisted past every name TTL."""
    manager = _analysis_manager(tmp_path, clock)
    named = FARM_CONTROLS[0]
    manager.client.answers["fetch_ens_names"] = lambda addrs: {
        named: "his-dudeness.eth"
    }
    stored = _store_farm_slot(manager)
    asyncio.run(manager.fetch_and_compute())
    for row in stored["clean_list_rows"]:
        assert row["name"] is None
    slot_rows = manager.cache.analysis_last_good().payload["clean_list_rows"]
    for row in slot_rows:
        assert row["name"] is None


# ---------------------------------------------------------------------------
# WP3.6 — the reader's linkage and clean rank across a wallet switch
# ---------------------------------------------------------------------------


def test_set_wallet_recomputes_linkage_from_the_held_analysis_without_a_new_sweep(
    tmp_path, clock
):
    """The sweep is about-the-population, not about-one-wallet: a runtime
    switch re-answers the four linkage keys from the already-held last-good,
    and forces no fresh B+C read."""
    manager = _analysis_manager(tmp_path, clock, wallet=FARM_MEMBERS[0])
    _store_farm_slot(manager)
    manager.cache.mark_fetched(TIER_ANALYSIS, NOW)     # no sweep is due

    first = asyncio.run(manager.fetch_and_compute())
    assert first["you_linked_state"] == "linked"
    assert first["you_clean_rank"] is None

    assert manager.set_wallet(FARM_CONTROLS[0]) is True
    out = asyncio.run(manager.fetch_and_compute())
    assert out["you_linked_state"] == "clean"
    assert out["you_linked_reasons"] == []
    assert isinstance(out["you_clean_rank"], int)
    assert out["analysis_as_of_hhmm"] == first["analysis_as_of_hhmm"]
    assert manager._analysis_task is None, "a wallet switch spawned a sweep"

    # ...and a wallet the sweep never saw is unknown, never a confident clean.
    manager.set_wallet(FARM_STRANGER)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["you_linked_state"] is None
    assert out["you_clean_rank"] is None


def test_clearing_the_wallet_clears_the_linkage_but_not_the_population_keys(
    tmp_path, clock
):
    manager = _analysis_manager(tmp_path, clock, wallet=FARM_MEMBERS[0])
    _store_farm_slot(manager)
    manager.cache.mark_fetched(TIER_ANALYSIS, NOW)
    assert asyncio.run(manager.fetch_and_compute())["you_linked_state"] == "linked"

    manager.set_wallet(None)
    out = asyncio.run(manager.fetch_and_compute())
    for key in (
        "you_linked_state",
        "you_linked_reasons",
        "you_linked_group_size",
        "you_clean_rank",
    ):
        assert out[key] is None, key
    assert out["operator_rows"], "the population analysis is not the reader's"
    assert SOURCE_WALLET not in out["degraded"]


# ---------------------------------------------------------------------------
# Fix round 1 — the analyzed-none state end to end, absence, outage backoff
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

from tests.data.test_curator_clusters import (  # noqa: E402
    MINIMUM as FARM_MINIMUM,
    RATE as FARM_RATE,
)


def _store_analyzed_none_slot(manager, *, ts=NOW):
    """A REAL analyzed-none publish: the analysis ran over the farm with no
    second family, so the amount component exists and no cluster does."""
    result = curator_clusters.build_analysis(
        farm_events(),
        farm_first_deposits(),
        points_per_eth=FARM_RATE,
        min_deposit_wei=FARM_MINIMUM,
    )
    payload = curator_clusters.slot_payload(result)
    manager.cache.store_analysis(payload, ts=ts)
    return payload


def test_an_analyzed_none_slot_reaches_the_flat_dict_as_real_zeros(tmp_path, clock):
    """Fix round 1, I1 — the fourth payload state, pinned THROUGH
    fetch_and_compute.  The regression class this exists for is the
    ``slot.get(key) or None`` collapse: a real zero laundered into 'could not
    analyze' by a truthiness test at the merge."""
    import re

    manager = _analysis_manager(tmp_path, clock, wallet=FARM_MEMBERS[0])
    stored = _store_analyzed_none_slot(manager)
    assert stored["operators_count"] == 0             # guard: really none-found

    out = asyncio.run(manager.fetch_and_compute())
    assert out["operator_rows"] == []                  # analyzed, nothing linked
    assert out["operators_count"] == 0
    assert isinstance(out["operators_count"], int)
    assert out["segment_rows"], "the population bands exist without operators"
    # Retargeted for ruling D4.  The aggregate band is `linked groups` now,
    # and this assertion had to move with it or it would have been VACUOUS:
    # after the rename no row can carry "largest operators" whatever the
    # analysis found, so the old spelling could no longer distinguish an
    # analyzed-none slot from one that published an aggregate off nothing.
    assert all(
        row["label"] != "linked groups" for row in out["segment_rows"]
    )
    assert out["clean_points"] == out["points_total"] > 0
    assert out["clean_contributors"] == len(FARM_MEMBERS) + len(FARM_CONTROLS)
    assert out["flagged_points_share_pct"] == 0.0      # the ruled override
    assert re.fullmatch(r"\d{2}:\d{2}", out["analysis_as_of_hhmm"])
    # The configured wallet was analyzed and cleared:
    assert out["you_linked_state"] == "clean"
    assert out["you_linked_reasons"] == []
    assert out["you_linked_group_size"] is None
    assert isinstance(out["you_clean_rank"], int)
    # ...and every leaderboard row grades clean, never a confident blank.
    for row in out["leaderboard_rows"]:
        assert row["link_conf"] in ("clean", None)


def test_a_missing_sybilkit_is_analysis_unavailable_never_a_crash(
    tmp_path, clock, monkeypatch
):
    """The ruled guarded import: with the library absent the twelve keys stay
    in their not-yet-run state, the merge and the R9 seeding keep working,
    no banner lights for mere absence, and the tier is spaced rather than
    re-offered every cycle."""
    manager = _analysis_manager(tmp_path, clock, wallet=WALLET)
    monkeypatch.setattr(curator_clusters, "SYBILKIT_AVAILABLE", False)

    async def _run():
        out = await asyncio.wait_for(manager.fetch_and_compute(), timeout=5)
        assert set(out) == set(CURATOR_KEYS)
        for key in (
            "operator_rows",
            "segment_rows",
            "clean_list_rows",
            "operators_count",
            "clean_points",
            "clean_contributors",
            "points_total",
            "analysis_as_of_hhmm",
            "you_linked_state",
            "you_linked_reasons",
            "you_linked_group_size",
            "you_clean_rank",
        ):
            assert out[key] is None, key
        assert out["degraded"] == []                   # absence is not an outage
        for row in out["leaderboard_rows"]:
            assert "link_conf" in row and row["link_conf"] is None
        task = manager._analysis_task
        if task is not None:
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(_run())
    assert manager._analysis_failed is False
    assert TIER_ANALYSIS not in manager.cache.tiers_due(NOW + 1)


def test_a_held_analysis_still_serves_when_sybilkit_is_gone(
    tmp_path, clock, monkeypatch
):
    """The merge reads a persisted payload, not the library: a last-good built
    while sybilkit existed keeps rendering after it is gone."""
    manager = _analysis_manager(tmp_path, clock, wallet=FARM_MEMBERS[0])
    _store_farm_slot(manager)
    monkeypatch.setattr(curator_clusters, "SYBILKIT_AVAILABLE", False)

    out = asyncio.run(manager.fetch_and_compute())
    assert out["operators_count"] == 1
    assert out["operator_rows"]
    assert out["you_linked_state"] == "linked"
    assert out["degraded"] == []


def test_a_sweep_whose_every_source_died_retries_on_the_backoff(tmp_path, clock):
    """Fix round 1, M2 — tx AND funding both unreachable: the tier-A result
    still publishes (data-wise honest), but the tier retries on the FAILURE
    backoff instead of waiting out the full ~30-minute TTL."""

    async def dead(_request):
        raise httpx.ConnectError("network unreachable")

    client = _scenario_client({"state": True, "logs": True, "wallet": False})
    client.answers["fetch_state"] = _state(tx_count=9, contributors=9)
    client.answers["fetch_logs"] = lambda *_: _sweep([], to_block=25_770_500)
    manager = _manager(
        tmp_path,
        clock,
        client=client,
        analysis_transport=httpx.MockTransport(dead),
        analysis_sleep=no_sleep,
    )
    manager.cache.store_events(farm_events(), now=NOW)
    manager.cache.store_first_deposits(farm_first_deposits())

    async def _run():
        task = manager._spawn_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(_run())
    entry = manager.cache.analysis_last_good()
    assert entry is not None                            # the tier-A publish
    assert entry.payload["operators_count"] == 0
    assert manager._analysis_failed is False            # it published; no banner
    from maxpane_dashboard.data.curator_cache import TIER_FAILURE_BACKOFF_SECONDS

    assert TIER_ANALYSIS not in manager.cache.tiers_due(NOW + 1)
    assert TIER_ANALYSIS in manager.cache.tiers_due(
        NOW + TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS] + 1
    )


def test_a_failed_sweeps_backoff_counts_from_completion_not_spawn(
    tmp_path, clock, monkeypatch
):
    """Fix round 1, M4 — a sweep that took 200 s to die must not have those
    200 s deducted from its retry spacing.  Freshness stamps stay spawn-time;
    only the retry clock moves."""

    def slow_boom(*_args, **_kwargs):
        clock.advance(200)                              # the sweep's own duration
        raise RuntimeError("died late")

    manager = _analysis_manager(tmp_path, clock)
    monkeypatch.setattr(curator_clusters, "build_analysis", slow_boom)

    async def _run():
        task = manager._spawn_analysis({TIER_ANALYSIS}, NOW, ANALYSIS_CONFIG)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(_run())
    from maxpane_dashboard.data.curator_cache import TIER_FAILURE_BACKOFF_SECONDS

    backoff = TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS]
    # Spawn-time stamping would make the tier due at NOW + 300 already:
    assert TIER_ANALYSIS not in manager.cache.tiers_due(NOW + backoff + 1)
    assert TIER_ANALYSIS not in manager.cache.tiers_due(NOW + 200 + backoff - 1)
    assert TIER_ANALYSIS in manager.cache.tiers_due(NOW + 200 + backoff + 1)


def _deposit(address: str, amount_wei: int, index: int) -> DepositEvent:
    return DepositEvent(
        contributor=address,
        hour=0,
        amount_wei=amount_wei,
        credited_delta_wei=amount_wei,
        weight_added_wei=amount_wei,
        new_weight_wei=amount_wei,
        tx_count=1,
        hour_total_wei=amount_wei,
        early_bps=10_000,
        block_number=index,
        tx_hash=f"0x{index:064x}",
        log_index=0,
        ts=NOW,
    )


def test_filtered_rows_use_a_valid_complete_export_and_cached_evidence(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    slot, fold = _legacy_clean_slot(count=3)
    addresses = [row.address for row in fold]
    slot["groups"] = [{
        "size": 2,
        "conf": "high",
        "families": ["amount", "funding"],
        "reasons": ["matching send amounts", "shared funder chain"],
        "members": addresses[:2],
    }]
    manager.cache.store_fold(fold, last_block=None, now=NOW)
    manager.cache.store_first_deposits([
        {"contributor": address, "index": index, "ts": NOW}
        for index, address in enumerate(addresses, start=1)
    ])
    manager.cache.store_events([
        _deposit(addresses[0], 1 * 10**18, 1),
        _deposit(addresses[1], 25 * 10**18, 2),
        _deposit(addresses[2], 25 * 10**18 - 1, 3),
    ])
    manager.cache.store_last_good(SLOT_LOGS, {}, ts=NOW)
    manager.cache.store_analysis(slot, ts=NOW)

    exported = manager.full_list_rows(cleaned=False)
    (tmp_path / "curator_raw_list.json").write_text(json.dumps(exported))
    spec = parse_filter_values({
        **empty_filter_values(),
        "families": frozenset({"funding"}),
        "whale": True,
    })
    result = manager.filtered_list_rows(
        tmp_path,
        expected_count=3,
        live_rows=exported[:1],
        you_row=None,
        spec=spec,
    )

    assert result.complete is True
    assert result.source_reason is None
    assert [row["address"] for row in result.rows] == [addresses[1]]
    assert manager.client.calls == []


def test_whale_filter_does_not_sum_sub_threshold_individual_deposits(
    tmp_path, clock
):
    manager = _manager(tmp_path, clock)
    _slot, fold = _legacy_clean_slot(count=1)
    address = fold[0].address
    manager.cache.store_fold(fold, last_block=None, now=NOW)
    manager.cache.store_first_deposits(
        [{"contributor": address, "index": 1, "ts": NOW}]
    )
    manager.cache.store_events(
        [
            _deposit(address, 13 * 10**18, 1),
            _deposit(address, 12 * 10**18, 2),
        ]
    )

    result = manager.filtered_list_rows(
        tmp_path,
        expected_count=1,
        live_rows=[{"rank": 1, "address": address}],
        you_row=None,
        spec=preset_filter("3"),
    )

    assert result.rows == []
    assert manager.client.calls == []


def test_filtered_rows_fall_back_to_the_live_slice_when_export_is_short(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    live = [{
        "rank": 1, "address": "0x" + "01" * 20, "points": 1,
        "credit_eth": 1.0, "tx_count": 1, "flagged": False, "name": None,
        "weight_eth": 1.0, "first_hour": 0, "first_index": 1,
        "link_conf": "clean",
    }]
    (tmp_path / "curator_raw_list.json").write_text(json.dumps(live))
    result = manager.filtered_list_rows(
        tmp_path,
        expected_count=2,
        live_rows=live,
        you_row=None,
        spec=preset_filter("2"),
    )
    assert result.rows == live
    assert result.complete is False
    assert result.source_reason == "count_mismatch"


def test_family_and_whale_filters_refuse_missing_evidence(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    row = {"rank": 1, "address": "0x" + "01" * 20, "first_index": 1, "first_hour": 0}
    values = empty_filter_values()
    values["families"] = frozenset({"amount"})
    with pytest.raises(FilterDataUnavailable, match="linked analysis unavailable"):
        manager.filtered_list_rows(tmp_path, expected_count=1, live_rows=[row], you_row=None, spec=parse_filter_values(values))

    with pytest.raises(FilterDataUnavailable, match="deposit history unavailable"):
        manager.filtered_list_rows(tmp_path, expected_count=1, live_rows=[row], you_row=None, spec=preset_filter("3"))


@pytest.mark.asyncio
async def test_collection_name_is_resolved_once_per_manager_session(tmp_path, clock):
    collection = NftCollectionRef(
        "ethereum", "0x" + "a" * 40, "ETH 0xaaaa…aaaa"
    )
    nft = FakeNftClient(names=("Reader Pass",))
    manager = _manager(tmp_path, clock, nft_client_factory=lambda: nft)
    assert await manager.resolve_nft_collection_name(collection) == "Reader Pass"
    assert await manager.resolve_nft_collection_name(collection) == "Reader Pass"
    assert nft.name_calls == [collection.key]
    await manager.close()


@pytest.mark.asyncio
async def test_no_name_uses_and_caches_the_short_address_label(tmp_path, clock):
    collection = NftCollectionRef(
        "base", "0x" + "b" * 40, "BASE 0xbbbb…bbbb"
    )
    nft = FakeNftClient(names=(None,))
    manager = _manager(tmp_path, clock, nft_client_factory=lambda: nft)
    expected = "BASE 0xbbbb…bbbb"
    assert await manager.resolve_nft_collection_name(collection) == expected
    assert await manager.resolve_nft_collection_name(collection) == expected
    assert nft.name_calls == [collection.key]
    await manager.close()


@pytest.mark.asyncio
async def test_unavailable_collection_name_is_not_cached(tmp_path, clock):
    collection = NftCollectionRef(
        "ethereum", "0x" + "c" * 40, "ETH 0xcccc…cccc"
    )
    nft = FakeNftClient(names=(
        NftHolderUnavailable("ethereum NFT holder RPC unavailable"),
        "Retry Pass",
    ))
    manager = _manager(tmp_path, clock, nft_client_factory=lambda: nft)
    with pytest.raises(NftHolderUnavailable):
        await manager.resolve_nft_collection_name(collection)
    assert await manager.resolve_nft_collection_name(collection) == "Retry Pass"
    assert nft.name_calls == [collection.key, collection.key]
    await manager.close()


@pytest.mark.asyncio
async def test_nft_filter_queues_once_without_blocking_or_opening_early(
    tmp_path, clock
):
    made = []
    gate = asyncio.Event()

    class BlockingNft(FakeNftClient):
        async def scan(self, collection, wallets):
            self.calls.append((collection.key, tuple(wallets)))
            await gate.wait()
            return NftHolderScan(
                collection, frozenset(), len(tuple(wallets)), 0, 1
            )

    def factory():
        client = BlockingNft()
        made.append(client)
        return client

    manager = _manager(
        tmp_path, clock, nft_client_factory=factory
    )
    assert made == []
    row = _nft_row("0x" + "1" * 40)
    spec = parse_filter_values({
        **empty_filter_values(),
        "nft_collections": (PREDEFINED_NFT_COLLECTIONS[0],),
    })
    with pytest.raises(NftHolderPending, match="loading"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    with pytest.raises(NftHolderPending, match="loading"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await asyncio.sleep(0)
    assert len(made) == 1 and len(made[0].calls) == 1
    gate.set()
    await manager._nft_task
    await manager.close()


@pytest.mark.asyncio
async def test_nft_scan_deduplicates_the_display_row_wallet_universe(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    holder = "0x" + "a" * 40
    nft = FakeNftClient([
        NftHolderScan(collection, frozenset({holder}), 1, 0, 1)
    ])
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: nft
    )
    rows = [_nft_row(holder), _nft_row(holder.upper())]
    spec = FilterSpec(nft_collections=(collection,))

    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=2, live_rows=rows,
            you_row=None, spec=spec
        )
    await manager._nft_task

    assert nft.calls == [(collection.key, (holder,))]
    hit = manager.cache.nft_holders(
        collection.key, wallet_universe_fingerprint([holder])
    )
    assert hit is not None
    assert hit.holders == frozenset({holder})
    await manager.close()


@pytest.mark.asyncio
async def test_fresh_and_stale_holder_sets_filter_without_false_empty(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    refreshed = NftHolderScan(
        collection, frozenset({"0x" + "1" * 40}), 2, 0, 2
    )
    nft = FakeNftClient([refreshed])
    made = []

    def factory():
        made.append(nft)
        return nft

    manager = _manager(
        tmp_path, clock,
        nft_client_factory=factory,
    )
    holder = "0x" + "1" * 40
    other = "0x" + "2" * 40
    rows = [_nft_row(holder), _nft_row(other)]
    fingerprint = wallet_universe_fingerprint(
        row["address"] for row in rows
    )
    manager.cache.store_nft_holders(
        collection.key,
        wallet_fingerprint=fingerprint,
        holders=(holder,), checked=2, failed=0,
        block_number=1, ts=clock(),
    )
    spec = FilterSpec(nft_collections=(collection,))
    fresh = manager.filtered_list_rows(
        tmp_path, expected_count=2, live_rows=rows,
        you_row=None, spec=spec
    )
    assert fresh.rows == [rows[0]]
    assert fresh.holder_receipt is None
    assert made == []

    clock.advance(NFT_HOLDER_TTL_SECONDS + 1)
    stale = manager.filtered_list_rows(
        tmp_path, expected_count=2, live_rows=rows,
        you_row=None, spec=spec
    )
    assert stale.rows == [rows[0]]
    assert stale.holder_receipt == (
        "NFT holders as of "
        + time.strftime("%H:%M", time.localtime(NOW))
    )
    assert manager._nft_task is not None
    await manager._nft_task
    await manager.close()


@pytest.mark.asyncio
async def test_complete_scan_publishes_and_incomplete_scan_preserves_last_good(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[0]
    holder = "0x" + "1" * 40
    complete = NftHolderScan(
        collection, frozenset({holder}), 1, 0, 12
    )
    incomplete = NftHolderScan(
        collection, frozenset(), 0, 0, 13
    )
    nft = FakeNftClient([complete, incomplete])
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: nft
    )
    row = _nft_row(holder)
    spec = FilterSpec(nft_collections=(collection,))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await manager._nft_task
    hit = manager.filtered_list_rows(
        tmp_path, expected_count=1, live_rows=[row],
        you_row=None, spec=spec
    )
    assert hit.rows == [row]

    clock.advance(NFT_HOLDER_TTL_SECONDS + 1)
    manager.filtered_list_rows(
        tmp_path, expected_count=1, live_rows=[row],
        you_row=None, spec=spec
    )
    await manager._nft_task
    assert manager.cache.nft_holders(
        collection.key, wallet_universe_fingerprint([holder])
    ).holders == frozenset({holder})
    await manager.close()
    assert nft.closed is True


@pytest.mark.asyncio
async def test_total_failure_backs_off_without_second_request(
    tmp_path, clock
):
    collection = PREDEFINED_NFT_COLLECTIONS[1]
    failed = FakeNftClient([
        NftHolderUnavailable("RPC unavailable")
    ])
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: failed
    )
    row = _nft_row("0x" + "1" * 40)
    spec = FilterSpec(nft_collections=(collection,))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await manager._nft_task
    with pytest.raises(NftHolderUnavailable, match="unavailable"):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    assert len(failed.calls) == 1
    await manager.close()


@pytest.mark.asyncio
async def test_close_cancels_and_awaits_active_nft_scan(tmp_path, clock):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingNft(FakeNftClient):
        async def scan(self, collection, wallets):
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    nft = BlockingNft()
    manager = _manager(
        tmp_path, clock, nft_client_factory=lambda: nft
    )
    row = _nft_row("0x" + "1" * 40)
    spec = FilterSpec(nft_collections=(PREDEFINED_NFT_COLLECTIONS[0],))
    with pytest.raises(NftHolderPending):
        manager.filtered_list_rows(
            tmp_path, expected_count=1, live_rows=[row],
            you_row=None, spec=spec
        )
    await started.wait()
    await manager.close()
    assert cancelled.is_set()
    assert nft.closed is True
