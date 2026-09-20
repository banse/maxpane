"""``DOTAManager.fetch_and_compute`` tells a failed read from a real zero.

**Zero network.** The manager's client and cache are replaced with doubles;
the doubles' fetchers are the only source of data, and the game-state one
raises on demand. Nothing here constructs an ``httpx`` client, so nothing
can reach the wire.

One claim, and it is the convention this repo states first: **a failed read
is ``None``, never ``0``** -- and never ``[]``, which is the same mistake in
a list's clothing. ``fetch_and_compute`` used to serve ``heroes=[]`` when
the game-state fetch failed, and the roster panel (a snapshot: it re-paints
the whole state every poll) cannot tell that from "the game has no heroes".
Under the feed contract both left the previous poll's HP and ALIVE/DEAD
rows on screen under an ``updated 0s ago`` marker (Branch 7 WP-A review C1).
"""

from __future__ import annotations

from typing import Any

import pytest

from maxpane_dashboard.data.dota_manager import DOTAManager
from maxpane_dashboard.data.dota_models import (
    DOTABase,
    DOTAGameState,
    DOTAHero,
    DOTALane,
)


def _hero(name: str = "Axe") -> DOTAHero:
    return DOTAHero(
        name=name, faction="orc", **{"class": "tank"}, lane="top",
        hp=500, maxHp=600, alive=True, level=4, xp=10, xpToNext=20,
        abilities=[],
    )


def _state(heroes: list[DOTAHero]) -> DOTAGameState:
    lane = DOTALane(human=1, orc=1, frontline=0.0)
    base = DOTABase(hp=1_000, maxHp=1_000)
    return DOTAGameState(
        tick=1,
        agents={},
        lanes={"top": lane, "mid": lane, "bot": lane},
        towers=[],
        bases={"human": base, "orc": base},
        heroes=heroes,
        winner=None,
    )


class _Client:
    """The only source of data, and it never touches a socket."""

    def __init__(self, state: DOTAGameState | None, fail: bool = False) -> None:
        self._state = state
        self._fail = fail

    async def fetch_game_state(self) -> DOTAGameState:
        if self._fail:
            raise RuntimeError("game state read failed")
        return self._state

    async def fetch_token_price(self) -> tuple[None, None, None]:
        return (None, None, None)

    async def fetch_leaderboard(self) -> list[Any]:
        return []


class _NoNetworkClient:
    """What ``DOTAManager.__init__`` builds instead of a real client.

    The real one constructs an ``httpx.AsyncClient``; this one cannot reach
    a socket even by accident, and every fetcher raises so a test that
    forgot to install its own double fails loudly rather than exercising
    the failure path by accident and passing for the wrong reason.
    """

    def __getattr__(self, name: str):
        async def _raise(*_a, **_k):
            raise AssertionError(f"unscripted client call: {name}")
        return _raise


@pytest.fixture()
def manager(tmp_path, monkeypatch: pytest.MonkeyPatch) -> DOTAManager:
    """A manager with no HTTP client and a cache file in ``tmp_path``."""
    monkeypatch.setattr(
        "maxpane_dashboard.data.dota_manager.DOTAClient", _NoNetworkClient
    )
    monkeypatch.setattr(
        "maxpane_dashboard.data.dota_manager._CACHE_DIR", tmp_path
    )
    monkeypatch.setattr(
        "maxpane_dashboard.data.dota_manager._CACHE_FILE",
        tmp_path / "dota_cache.json",
    )
    return DOTAManager(poll_interval=30)


async def test_a_failed_game_state_read_serves_heroes_none(manager) -> None:
    """The regression. ``None`` is "could not look"."""
    manager.client = _Client(None, fail=True)

    data = await manager.fetch_and_compute()

    assert data["heroes"] is None, data["heroes"]
    assert manager._error_count == 1


async def test_a_successful_read_with_no_heroes_serves_an_empty_list(
    manager,
) -> None:
    """The real negative, and it must stay representable as itself: the
    game state was read, and there are no heroes in it. A panel shows
    ``No heroes yet`` for this and ``unavailable`` for the case above."""
    manager.client = _Client(_state([]))

    data = await manager.fetch_and_compute()

    assert data["heroes"] == [], data["heroes"]
    assert manager._error_count == 0


async def test_a_successful_read_serves_the_roster(manager) -> None:
    """The normal path, so the two cases above are read against a shape
    that is known to work rather than against nothing."""
    manager.client = _Client(_state([_hero("Axe"), _hero("Sven")]))

    data = await manager.fetch_and_compute()

    assert [h["name"] for h in data["heroes"]] == ["Axe", "Sven"]
    assert data["heroes"][0]["hp"] == 500
    assert data["heroes"][0]["alive"] is True
