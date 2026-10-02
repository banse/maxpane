"""F-S5: the manager's per-seat REWARDS read and its two contract keys.

The client is a double (``fetch_seat_rewards`` scripted); the seat is the
committed ``seat_420`` capture (owner pawai.eth, IDMD collection, chain 1).
What is pinned: the split per held seat, the since-pairedAt argument, the
per-seat TTL and failure backoff, ``pending`` vs ``None``, and that a stored
total never answers for another owner or pairing.
"""

from __future__ import annotations

import copy

import pytest

from maxpane_dashboard.data import surf_manager as M
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT_REWARDS
from maxpane_dashboard.data.surf_models import SURF_KEYS, SeatRewards
from tests.data.test_surf_manager import FakeClock, FakeSurfClient, NOW
from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager, _seat_payload_of, _seated, _settle

SEAT = _seat_payload_of(420)
SUMMARY = sw.seat_summary_from_seat(SEAT)
RAW = 7692307692307692307 + 3052147239263803680 + 3121794871794871794
PAID = SeatRewards(raw_total=RAW, decimals=18, seats_held=1, transfers=3)


class _RewardsClient(FakeSurfClient):
    def __init__(self, result=PAID, **kw):
        super().__init__(**kw)
        self.result = result
        self.reward_calls: list[tuple] = []

    async def fetch_seat_rewards(self, owner, since_ts):
        self.reward_calls.append((owner, since_ts))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_the_two_keys_are_in_the_contract():
    assert "swarm_seat_rewards" in SURF_KEYS and "swarm_seat_rewards_state" in SURF_KEYS


async def test_seat_420_shows_its_imd_and_usd_at_todays_price(tmp_path):
    client = _RewardsClient()
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=client)
    assert client.reward_calls == [(SUMMARY["owner"], SUMMARY["paired_ts"])], "since pairedAt"
    rewards = payload["swarm_seat_rewards"]
    assert payload["swarm_seat_rewards_state"] == "ok"
    assert rewards["seats"] == 1
    assert rewards["imd"] == pytest.approx(13.8662, abs=1e-4)
    assert rewards["usd"] == pytest.approx(rewards["imd"] * payload["imd_price_usd"])
    await manager.close()


async def test_the_total_is_split_evenly_across_the_wallets_seats(tmp_path):
    client = _RewardsClient(SeatRewards(raw_total=RAW, decimals=18, seats_held=4, transfers=3))
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=client)
    assert payload["swarm_seat_rewards"]["imd"] == pytest.approx(RAW / 1e18 / 4)
    assert payload["swarm_seat_rewards"]["seats"] == 4
    await manager.close()


async def test_a_live_decimals_is_the_divisor(tmp_path):
    client = _RewardsClient(SeatRewards(raw_total=5_000_000, decimals=6, seats_held=1, transfers=1))
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=client)
    assert payload["swarm_seat_rewards"]["imd"] == pytest.approx(5.0)
    await manager.close()


async def test_nothing_received_is_a_real_zero(tmp_path):
    client = _RewardsClient(SeatRewards(raw_total=0, decimals=18, seats_held=1, transfers=0))
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=client)
    assert payload["swarm_seat_rewards"] == {"imd": 0.0, "usd": 0.0, "seats": 1}
    assert payload["swarm_seat_rewards_state"] == "ok"
    await manager.close()


async def test_no_price_keeps_the_imd_and_drops_only_the_usd(tmp_path, monkeypatch):
    client = _RewardsClient()
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=client)
    keys = manager._seat_rewards_keys(payload, None, NOW)
    assert keys["swarm_seat_rewards"]["usd"] is None
    assert keys["swarm_seat_rewards"]["imd"] == pytest.approx(13.8662, abs=1e-4)
    await manager.close()


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1.0, True])
async def test_a_nonsense_price_is_no_price(tmp_path, price):
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=_RewardsClient())
    assert manager._seat_rewards_keys(payload, price, NOW)["swarm_seat_rewards"]["usd"] is None
    await manager.close()


async def test_not_read_yet_is_pending_and_a_failure_is_none(tmp_path):
    manager, payload = await _seated(tmp_path, _FakeSwarm(), seat=420, client=FakeSurfClient())
    assert (payload["swarm_seat_rewards"], payload["swarm_seat_rewards_state"]) == (None, "pending")
    await manager.close()
    for result in (None, RuntimeError("blockscout down")):
        manager, payload = await _seated(tmp_path / str(id(result)), _FakeSwarm(), seat=420,
                                         client=_RewardsClient(result))
        assert (payload["swarm_seat_rewards"], payload["swarm_seat_rewards_state"]) == (None, None)
        await manager.close()


async def test_no_seat_record_means_no_rewards_keys(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm(), client=_RewardsClient())
    payload = await manager.fetch_and_compute()
    assert payload["swarm_seat_rewards"] is None and payload["swarm_seat_rewards_state"] is None
    await manager.close()


async def test_a_fresh_read_is_not_repeated_within_its_ttl(tmp_path):
    clock = FakeClock(NOW)
    client = _RewardsClient()
    manager = _manager(tmp_path, _FakeSwarm(), client=client, clock=clock)
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock.advance(M.SWARM_SEAT_REWARDS_TTL_S - 1))
    assert len(client.reward_calls) == 1
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock.advance(2))
    assert len(client.reward_calls) == 2
    await manager.close()


async def test_a_failure_backs_off_and_keeps_the_last_good(tmp_path):
    clock = FakeClock(NOW)
    client = _RewardsClient()
    manager = _manager(tmp_path, _FakeSwarm(), client=client, clock=clock)
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    stored = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_SEAT_REWARDS).payload)
    client.result = None
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock.advance(M.SWARM_SEAT_REWARDS_TTL_S + 1))
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock.advance(M.SWARM_SEAT_REWARDS_BACKOFF_S - 1))
    assert len(client.reward_calls) == 2, "the backoff holds the retry"
    assert manager.cache.get_last_good(SLOT_SWARM_SEAT_REWARDS).payload == stored
    keys = manager._seat_rewards_keys({"swarm_seat_selected": {"token_id": 420},
                                       "swarm_seat_state": "ok", "swarm_seat_summary": SUMMARY},
                                      1.0, clock())
    assert keys["swarm_seat_rewards_state"] == "ok", "last-good is served through a failure"
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock.advance(2))
    assert len(client.reward_calls) == 3
    await manager.close()


@pytest.mark.parametrize("field, value", [("owner", "0x" + "ab" * 20), ("paired_ts", NOW - 5)])
async def test_a_stored_total_never_answers_for_another_owner_or_pairing(tmp_path, field, value):
    clock = FakeClock(NOW)
    client = _RewardsClient()
    manager = _manager(tmp_path, _FakeSwarm(), client=client, clock=clock)
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    summary = dict(SUMMARY, **{field: value})
    seat_keys = {"swarm_seat_selected": {"token_id": 420}, "swarm_seat_state": "ok",
                 "swarm_seat_summary": summary}
    keys = manager._seat_rewards_keys(seat_keys, 1.0, clock())
    assert keys == {"swarm_seat_rewards": None, "swarm_seat_rewards_state": "pending"}
    # ... and the sold seat is re-read at once, not after the TTL.
    sold = dict(SEAT, owner=summary["owner"]) if field == "owner" else dict(
        SEAT, pairedAt="2026-10-02T00:00:00.000Z")
    await manager._pool_swarm_seat_rewards(sold, 420, clock.advance(1))
    assert len(client.reward_calls) == 2
    await manager.close()


@pytest.mark.parametrize("patch", [{"collection": "0x" + "cd" * 20}, {"chainId": 8453},
                                   {"collection": None}, {"pairedAt": None}, {"owner": None}])
async def test_a_seat_outside_the_idmd_collection_is_not_read(tmp_path, patch):
    client = _RewardsClient()
    manager = _manager(tmp_path, _FakeSwarm(), client=client)
    await manager._pool_swarm_seat_rewards(dict(SEAT, **patch), 420, NOW)
    assert client.reward_calls == []
    keys = manager._seat_rewards_keys({"swarm_seat_selected": {"token_id": 420},
                                       "swarm_seat_state": "ok",
                                       "swarm_seat_summary": sw.seat_summary_from_seat(dict(SEAT, **patch))},
                                      1.0, NOW)
    assert keys == {"swarm_seat_rewards": None, "swarm_seat_rewards_state": None}
    await manager.close()


async def test_the_slot_survives_a_restart_and_drops_bad_points(tmp_path):
    clock = FakeClock(NOW)
    manager = _manager(tmp_path, _FakeSwarm(), client=_RewardsClient(), clock=clock)
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    payload = dict(manager.cache.get_last_good(SLOT_SWARM_SEAT_REWARDS).payload)
    payload["7"] = dict(payload["420"], raw=-1)
    payload["8"] = dict(payload["420"], seats=0)
    payload["9"] = dict(payload["420"], decimals=True)
    payload["10"] = dict(payload["420"], raw=10 ** 400, decimals=0)     # review I1
    manager.cache.store_last_good(SLOT_SWARM_SEAT_REWARDS, payload, ts=clock())
    manager.save_cache()
    await manager.close()
    fresh = _manager(tmp_path, _FakeSwarm(), client=_RewardsClient(), clock=clock)
    assert list(fresh.cache.get_last_good(SLOT_SWARM_SEAT_REWARDS).payload) == ["420"]
    await fresh.close()


def test_the_slot_keeps_the_six_newest_seats():
    point = {"owner": SUMMARY["owner"], "paired_ts": 1.0, "raw": 1, "decimals": 18, "seats": 1,
             "transfers": 1}
    slot = {str(t): dict(point, read_ts=float(t)) for t in range(1, 9)}
    assert list(sw.coerce_rewards_slot(slot, now=NOW)) == ["8", "7", "6", "5", "4", "3"]
    assert sw.coerce_rewards_slot({"1": dict(point, read_ts=NOW + 10_000)}, now=NOW) == {}
    assert sw.coerce_rewards_slot([], now=NOW) is None


async def test_a_hostile_raw_cannot_overflow_the_cycle(tmp_path):
    """Review I1: a raw beyond any real sum is dropped at coercion, never divided."""
    clock = FakeClock(NOW)
    manager = _manager(tmp_path, _FakeSwarm(), client=_RewardsClient(), clock=clock)
    point = {"owner": SUMMARY["owner"].lower(), "paired_ts": SUMMARY["paired_ts"], "raw": 10 ** 400,
             "decimals": 0, "seats": 1, "transfers": 1, "read_ts": clock()}
    manager.cache.store_last_good(SLOT_SWARM_SEAT_REWARDS, {"420": point}, ts=clock())
    seat_keys = {"swarm_seat_selected": {"token_id": 420}, "swarm_seat_state": "ok",
                 "swarm_seat_summary": SUMMARY}
    assert manager._seat_rewards_keys(seat_keys, 1.0, clock())["swarm_seat_rewards"] is None
    await manager.close()


async def test_an_old_total_is_never_shown_as_live(tmp_path):
    """Review I3: REWARDS has no as-of line, so past the max age the total is unread."""
    clock = FakeClock(NOW)
    client = _RewardsClient()
    manager = _manager(tmp_path, _FakeSwarm(), client=client, clock=clock)
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    seat_keys = {"swarm_seat_selected": {"token_id": 420}, "swarm_seat_state": "ok",
                 "swarm_seat_summary": SUMMARY}
    clock.advance(M.SWARM_SEAT_REWARDS_MAX_AGE_S)
    assert manager._seat_rewards_keys(seat_keys, 1.0, clock())["swarm_seat_rewards_state"] == "ok"
    clock.advance(1)
    assert manager._seat_rewards_keys(seat_keys, 1.0, clock()) == {
        "swarm_seat_rewards": None, "swarm_seat_rewards_state": "pending"}
    client.result = None
    await manager._pool_swarm_seat_rewards(SEAT, 420, clock())
    assert manager._seat_rewards_keys(seat_keys, 1.0, clock()) == {
        "swarm_seat_rewards": None, "swarm_seat_rewards_state": None}
    await manager.close()
