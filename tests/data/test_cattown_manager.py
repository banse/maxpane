"""``CatTownManager`` never writes a sentinel into a persisted series.

**Zero network.** The manager's client is replaced with a double whose
fetchers are the only source of data and whose raffle read raises on
demand; the cache file is redirected into ``tmp_path``.  Nothing here
constructs an ``httpx`` client, so nothing can reach the wire, and
nothing writes to ``~/.maxpane``.

The claim is the repo's first convention -- **a failed read is ``None``,
never ``0``** -- applied where it costs the most: these two series are
persisted to ``~/.maxpane/cattown_cache.json``, so a zero written during
an outage survives the outage and reads afterwards as a measurement.
The manager used to seed ``raffle_total_tickets = 0`` before a
best-effort fetch and ``leader_weight = 0.0`` before checking whether
the competition had any entries, and appended both verbatim: a dead
raffle endpoint became "nobody bought a ticket", and a competition
nobody had entered yet became "the leader's fish weighs nothing".
"""

from __future__ import annotations

from typing import Any

import pytest

from maxpane_dashboard.data.cattown_manager import CatTownManager
from maxpane_dashboard.data.cattown_models import (
    CatTownSnapshot,
    CompetitionEntry,
    CompetitionState,
    KibbleEconomy,
    StakingState,
)

NOW = 1_700_000_000.0


def _snapshot(entries: list[CompetitionEntry]) -> CatTownSnapshot:
    return CatTownSnapshot(
        fetched_at=NOW,
        kibble=KibbleEconomy(
            price_eth=1e-7,
            total_supply=1_000_000.0,
            circulating=900_000.0,
            burned=100_000.0,
            staked_total=50_000.0,
            price_change_24h=0.0,
        ),
        competition=CompetitionState(
            week_number=7,
            is_active=True,
            total_volume_kibble=10_000.0,
            prize_pool_kibble=1_000.0,
            treasure_pool_kibble=7_000.0,
            staker_revenue_kibble=1_000.0,
            num_participants=len(entries),
            start_time=int(NOW) - 3600,
            end_time=int(NOW) + 3600,
            entries=entries,
        ),
        recent_catches=[],
        staking=StakingState(
            total_staked=50_000.0,
            user_staked=0.0,
            pending_rewards=0.0,
            weekly_revenue=0.0,
        ),
    )


def _entry(weight: float = 4.25) -> CompetitionEntry:
    return CompetitionEntry(
        fisher_address="0x" + "11" * 20,
        fish_weight_kg=weight,
        fish_species="Tuna",
        rarity="rare",
        rank=1,
    )


class _Client:
    """The only source of data, and it never touches a socket."""

    def __init__(
        self,
        snapshot: CatTownSnapshot,
        raffle: int | None = 250,
        raffle_fails: bool = False,
    ) -> None:
        self._snapshot = snapshot
        self._raffle = raffle
        self._raffle_fails = raffle_fails

    async def fetch_snapshot(self) -> CatTownSnapshot:
        return self._snapshot

    async def get_raffle_total_tickets(self) -> int:
        if self._raffle_fails:
            raise RuntimeError("raffle endpoint is down")
        return self._raffle

    async def resolve_basenames(self, addresses: list[str]) -> dict[str, Any]:
        return {}


class _NoNetworkClient:
    """What ``CatTownManager.__init__`` builds instead of a real client.

    The real one constructs an ``httpx.AsyncClient``; this one cannot
    reach a socket even by accident, and every fetcher raises so a test
    that forgot to install its own double fails loudly rather than
    exercising a failure path by accident and passing for the wrong
    reason.
    """

    def __getattr__(self, name: str):
        async def _raise(*_a, **_k):
            raise AssertionError(f"unscripted client call: {name}")

        return _raise


@pytest.fixture()
def manager(tmp_path, monkeypatch: pytest.MonkeyPatch) -> CatTownManager:
    """A manager with no HTTP client and a cache file in ``tmp_path``."""
    monkeypatch.setattr(
        "maxpane_dashboard.data.cattown_manager.CatTownClient", _NoNetworkClient
    )
    monkeypatch.setattr(
        "maxpane_dashboard.data.cattown_manager._CACHE_DIR", tmp_path
    )
    monkeypatch.setattr(
        "maxpane_dashboard.data.cattown_manager._CACHE_FILE",
        tmp_path / "cattown_cache.json",
    )
    return CatTownManager(poll_interval=30)


async def test_a_failed_raffle_read_records_no_ticket_point(manager) -> None:
    """The regression: the series stays empty, it does not gain a zero."""
    manager.client = _Client(_snapshot([]), raffle_fails=True)

    await manager.fetch_and_compute()

    assert manager.cache.get_raffle_tickets_history() == []


async def test_a_competition_with_no_entries_records_no_leader_weight(
    manager,
) -> None:
    """No entries means there is no leader to weigh, not a weightless one."""
    manager.client = _Client(_snapshot([]), raffle_fails=True)

    await manager.fetch_and_compute()

    assert manager.cache.get_leader_weight_history() == []


async def test_a_good_read_records_one_point_in_each_series(manager) -> None:
    """The normal path, so the two cases above are read against a shape
    that is known to work rather than against nothing."""
    manager.client = _Client(_snapshot([_entry(4.25)]), raffle=250)

    await manager.fetch_and_compute()

    assert manager.cache.get_raffle_tickets_history() == [(NOW, 250.0)]
    assert manager.cache.get_leader_weight_history() == [(NOW, 4.25)]
    assert manager.cache.get_prize_pool_history() == [(NOW, 1_000.0)]


async def test_a_real_zero_is_still_recorded(manager) -> None:
    """A round in which the raffle sold nothing is a measurement, and it
    has to stay distinguishable from the outage above."""
    manager.client = _Client(_snapshot([_entry(0.0)]), raffle=0)

    await manager.fetch_and_compute()

    assert manager.cache.get_raffle_tickets_history() == [(NOW, 0.0)]
    assert manager.cache.get_leader_weight_history() == [(NOW, 0.0)]


async def test_the_failed_and_good_cycles_are_distinguishable_in_the_series(
    manager,
) -> None:
    """Two cycles, one dead raffle and one live: the persisted series
    holds exactly one point, at the timestamp of the live cycle."""
    manager.client = _Client(_snapshot([]), raffle_fails=True)
    await manager.fetch_and_compute()
    manager.client = _Client(_snapshot([_entry(4.25)]), raffle=250)
    await manager.fetch_and_compute()

    assert manager.cache.get_raffle_tickets_history() == [(NOW, 250.0)]
    assert manager.cache.get_leader_weight_history() == [(NOW, 4.25)]
    # The prize pool was read on both cycles.
    assert manager.cache.get_prize_pool_history() == [(NOW, 1_000.0), (NOW, 1_000.0)]
