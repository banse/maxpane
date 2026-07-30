"""Tests for the DOTA (Defense of the Agents) REST client.

**Zero network.** Every test drives :class:`DOTAClient` through an
``httpx.MockTransport``; the default transport double raises on any request it
was not scripted for, so a stray ``await`` that reaches the wire fails loudly
instead of dialling a host that no longer resolves.

Context (LOW-10): the DOTA backend host is dead (NXDOMAIN), so the payload
shapes below are derived from what ``dota_client.py`` actually *reads*, not
from live captures.  The point of this file is to pin the client's
graceful-degradation contract — malformed rows are skipped, a broken price
feed yields ``(None, None, None)``, a partial outage still yields a snapshot —
so that removing a guard or reshaping a parse breaks a test.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import dota_client as dc
from maxpane_dashboard.data.dota_client import (
    DOTAClient,
    _calc_win_rate,
    _strip_non_ascii,
)
from maxpane_dashboard.data.dota_models import DOTAGameState


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the retry backoff so failure-path tests are instant."""
    monkeypatch.setattr(dc, "_BACKOFF_SECONDS", (0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted an unscripted request: {request.method} {request.url}"
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that records every URL it was handed."""

    def __init__(self, handler: Callable[[str], httpx.Response]) -> None:
        self.urls: list[str] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.urls.append(str(request.url))
            return handler(str(request.url))

        super().__init__(_wrapped)


def _client_on(handler: Callable[[str], httpx.Response]) -> DOTAClient:
    return DOTAClient(
        http_client=httpx.AsyncClient(transport=RecordingTransport(handler))
    )


def _offline_client() -> DOTAClient:
    """A client that cannot reach anything — proves a test stayed offline."""
    return DOTAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    )


def _json(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _route(
    *,
    game_state: httpx.Response | Callable[[], httpx.Response] | None = None,
    leaderboard: httpx.Response | Callable[[], httpx.Response] | None = None,
    dexscreener: httpx.Response | Callable[[], httpx.Response] | None = None,
) -> Callable[[str], httpx.Response]:
    """Build a URL-dispatching handler; unrouted URLs blow up."""

    def _resolve(
        resp: httpx.Response | Callable[[], httpx.Response] | None, url: str
    ) -> httpx.Response:
        if resp is None:  # pragma: no cover - guard
            raise AssertionError(f"unrouted request: {url}")
        return resp() if callable(resp) else resp

    def handler(url: str) -> httpx.Response:
        if url == dc._GAME_STATE_URL:
            return _resolve(game_state, url)
        if url == dc._LEADERBOARD_URL:
            return _resolve(leaderboard, url)
        if url == dc._DEXSCREENER_URL:
            return _resolve(dexscreener, url)
        raise AssertionError(f"unexpected URL: {url}")  # pragma: no cover

    return handler


def _sequence(*responses: httpx.Response) -> Callable[[], httpx.Response]:
    """Return a callable yielding each response in turn, then repeating the last."""
    box = list(responses)

    def _next() -> httpx.Response:
        return box.pop(0) if len(box) > 1 else box[0]

    return _next


# ---------------------------------------------------------------------------
# Payload fixtures — shapes derived from the parsing code
# ---------------------------------------------------------------------------


def _hero(name: str = "Grommash", faction: str = "orc") -> dict:
    return {
        "name": name,
        "faction": faction,
        "class": "warrior",
        "lane": "mid",
        "hp": 800,
        "maxHp": 1000,
        "alive": True,
        "level": 4,
        "xp": 120,
        "xpToNext": 300,
        "abilities": [{"id": "cleave", "level": 2}],
        "abilityChoices": ["whirlwind", "shout"],
    }


def _game_state_payload(**over: Any) -> dict:
    payload: dict[str, Any] = {
        "tick": 42,
        "agents": {"human": ["alice"], "orc": ["bob"]},
        "lanes": {
            "top": {"human": 5, "orc": 3, "frontline": 40},
            "mid": {"human": 2, "orc": 6, "frontline": -20},
        },
        "towers": [
            {"faction": "human", "lane": "top", "hp": 900, "maxHp": 1500, "alive": True},
            {"faction": "orc", "lane": "top", "hp": 0, "maxHp": 1500, "alive": False},
        ],
        "bases": {
            "human": {"hp": 4000, "maxHp": 5000},
            "orc": {"hp": 5000, "maxHp": 5000},
        },
        "heroes": [_hero(), _hero("Uther", "human")],
        "winner": None,
    }
    payload.update(over)
    return payload


def _dex_pair(
    *,
    price: str = "0.00042",
    change_24h: float = 12.5,
    liquidity: float = 50_000.0,
    market_cap: float = 1_200_000.0,
) -> dict:
    return {
        "priceUsd": price,
        "priceChange": {"h24": change_24h},
        "liquidity": {"usd": liquidity},
        "marketCap": market_cap,
    }


# ===========================================================================
# Pure helpers
# ===========================================================================


def test_strip_non_ascii_removes_emoji_and_keeps_ascii():
    assert _strip_non_ascii("Ka’Zul \U0001f525") == "KaZul "
    assert _strip_non_ascii("plain-name_1") == "plain-name_1"


def test_calc_win_rate_prefers_precomputed_camel_case():
    assert _calc_win_rate({"winRate": 73.5, "games_won": 1, "games_played": 99}) == 73.5


def test_calc_win_rate_accepts_snake_case_alias():
    assert _calc_win_rate({"win_rate": "50"}) == 50.0


def test_calc_win_rate_computes_from_counts_when_absent():
    assert _calc_win_rate({"games_won": 3, "games_played": 4}) == 75.0
    assert _calc_win_rate({"wins": 1, "games": 2}) == 50.0


def test_calc_win_rate_zero_games_returns_zero_not_division_error():
    assert _calc_win_rate({"games_won": 0, "games_played": 0}) == 0.0
    assert _calc_win_rate({}) == 0.0


def test_calc_win_rate_null_precomputed_falls_back_to_counts():
    # ``winRate: null`` must not short-circuit to float(None).
    assert _calc_win_rate({"winRate": None, "games_won": 1, "games_played": 4}) == 25.0


def test_calc_win_rate_raises_on_null_counts():
    # Documents *why* fetch_leaderboard needs its per-entry try/except.
    with pytest.raises(TypeError):
        _calc_win_rate({"games_won": None, "games_played": 10})


# ===========================================================================
# fetch_game_state
# ===========================================================================


async def test_fetch_game_state_happy_path():
    client = _client_on(_route(game_state=_json(_game_state_payload())))
    state = await client.fetch_game_state()

    assert isinstance(state, DOTAGameState)
    assert state.tick == 42
    assert state.winner is None
    assert state.lanes["top"].human == 5
    assert state.lanes["mid"].frontline == -20
    assert state.bases["orc"].max_hp == 5000
    assert [t.alive for t in state.towers] == [True, False]
    assert state.heroes[0].hero_class == "warrior"
    assert state.heroes[0].max_hp == 1000
    assert state.heroes[0].abilities[0].id == "cleave"
    assert state.heroes[0].ability_choices == ["whirlwind", "shout"]
    await client.close()


async def test_fetch_game_state_parses_finished_game():
    client = _client_on(_route(game_state=_json(_game_state_payload(winner="orc"))))
    state = await client.fetch_game_state()
    assert state.winner == "orc"


async def test_fetch_game_state_ignores_extra_fields():
    payload = _game_state_payload(unexpectedNewField={"anything": 1})
    client = _client_on(_route(game_state=_json(payload)))
    state = await client.fetch_game_state()
    assert state.tick == 42


async def test_fetch_game_state_game_arg_does_not_change_url():
    # The ``game`` parameter is accepted but not used in the request URL.
    handler = _route(game_state=_json(_game_state_payload()))
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    await client.fetch_game_state(3)
    assert transport.urls == [dc._GAME_STATE_URL]


async def test_fetch_game_state_missing_required_field_raises():
    payload = _game_state_payload()
    del payload["bases"]
    client = _client_on(_route(game_state=_json(payload)))
    with pytest.raises(ValueError):  # pydantic ValidationError
        await client.fetch_game_state()


async def test_fetch_game_state_null_hp_raises():
    payload = _game_state_payload()
    payload["bases"]["human"]["hp"] = None
    client = _client_on(_route(game_state=_json(payload)))
    with pytest.raises(ValueError):
        await client.fetch_game_state()


async def test_fetch_game_state_empty_payload_raises():
    client = _client_on(_route(game_state=_json({})))
    with pytest.raises(ValueError):
        await client.fetch_game_state()


async def test_fetch_game_state_http_500_raises_after_retries():
    handler = _route(game_state=_json({"error": "boom"}, status=500))
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_game_state()
    assert len(transport.urls) == dc._MAX_RETRIES


async def test_fetch_game_state_transport_error_raises():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nxdomain", request=request)

    client = DOTAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    with pytest.raises(httpx.ConnectError):
        await client.fetch_game_state()


# ===========================================================================
# _get_with_retry
# ===========================================================================


async def test_retry_recovers_after_transient_500():
    handler = _route(
        game_state=_sequence(
            _json({"error": "bad gateway"}, status=502),
            _json(_game_state_payload()),
        )
    )
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    state = await client.fetch_game_state()
    assert state.tick == 42
    assert len(transport.urls) == 2


async def test_retry_treats_429_as_retryable():
    handler = _route(
        leaderboard=_sequence(
            _json({"detail": "rate limited"}, status=429),
            _json([{"name": "alice", "games_won": 1, "games_played": 2}]),
        )
    )
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    entries = await client.fetch_leaderboard()
    assert len(entries) == 1
    assert len(transport.urls) == 2


async def test_retry_exhausts_attempts_on_persistent_connect_error():
    calls: list[str] = []

    def boom(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise httpx.ConnectTimeout("timeout", request=request)

    client = DOTAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    with pytest.raises(httpx.ConnectTimeout):
        await client.fetch_leaderboard()
    assert len(calls) == dc._MAX_RETRIES


async def test_retry_also_retries_a_404():
    # 4xx is not special-cased: raise_for_status raises HTTPStatusError, which
    # is an httpx.HTTPError, so it goes through the same retry loop.
    handler = _route(leaderboard=_json({"detail": "gone"}, status=404))
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_leaderboard()
    assert len(transport.urls) == dc._MAX_RETRIES


# ===========================================================================
# fetch_leaderboard — happy paths and shape tolerance
# ===========================================================================


async def test_fetch_leaderboard_bare_list():
    payload = [
        {
            "rank": 1,
            "name": "alice",
            "games_won": 8,
            "games_played": 10,
            "playerType": "Agent",
        },
        {
            "rank": 2,
            "name": "bob",
            "games_won": 3,
            "games_played": 12,
            "playerType": "Human",
        },
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()

    assert [e.name for e in entries] == ["alice", "bob"]
    assert [e.rank for e in entries] == [1, 2]
    assert entries[0].wins == 8
    assert entries[0].games == 10
    assert entries[0].win_rate == 80.0
    assert entries[0].player_type == "Agent"
    assert entries[1].win_rate == pytest.approx(25.0)


@pytest.mark.parametrize(
    "key", ["leaderboard", "data", "players", "entries", "results"]
)
async def test_fetch_leaderboard_unwraps_known_envelope_keys(key: str):
    payload = {key: [{"name": "alice", "wins": 1, "games": 1}]}
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["alice"]


async def test_fetch_leaderboard_falls_back_to_first_list_value():
    payload = {"meta": {"total": 1}, "somethingNew": [{"name": "alice"}]}
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["alice"]


async def test_fetch_leaderboard_accepts_snake_case_aliases():
    payload = [
        {"player": "carol", "wins": 4, "games": 5, "player_type": "Agent"},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    (entry,) = await client.fetch_leaderboard()
    assert entry.name == "carol"
    assert entry.wins == 4
    assert entry.games == 5
    assert entry.win_rate == 80.0
    assert entry.player_type == "Agent"


async def test_fetch_leaderboard_defaults_rank_name_and_type():
    payload = [{"wins": 1, "games": 2}, {"wins": 0, "games": 1}]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.rank for e in entries] == [1, 2]
    assert [e.name for e in entries] == ["Player 1", "Player 2"]
    assert [e.player_type for e in entries] == ["Human", "Human"]


async def test_fetch_leaderboard_strips_non_ascii_from_names():
    payload = [{"username": "☠ dark‐lord \U0001f480", "wins": 1, "games": 1}]
    client = _client_on(_route(leaderboard=_json(payload)))
    (entry,) = await client.fetch_leaderboard()
    assert entry.name == " darklord "


async def test_fetch_leaderboard_logs_raw_only_on_first_fetch(caplog):
    handler = _route(leaderboard=_json([{"name": "alice", "wins": 1, "games": 1}]))
    client = _client_on(handler)
    assert client._first_leaderboard_fetch is True
    with caplog.at_level("DEBUG", logger=dc.__name__):
        await client.fetch_leaderboard()
    assert client._first_leaderboard_fetch is False
    assert any("raw response" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level("DEBUG", logger=dc.__name__):
        await client.fetch_leaderboard()
    assert not any("raw response" in r.message for r in caplog.records)


# ===========================================================================
# fetch_leaderboard — degradation: bad rows are skipped, not fatal
# ===========================================================================


async def test_fetch_leaderboard_skips_null_games_won_row():
    payload = [
        {"name": "good", "games_won": 2, "games_played": 4},
        {"name": "null-wins", "games_won": None, "games_played": 4},
        {"name": "also-good", "games_won": 1, "games_played": 2},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good", "also-good"]


async def test_fetch_leaderboard_skips_null_games_played_row():
    payload = [
        {"name": "null-games", "games_won": 1, "games_played": None},
        {"name": "good", "wins": 1, "games": 1},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good"]


async def test_fetch_leaderboard_skips_non_numeric_counts():
    payload = [
        {"name": "junk", "wins": "many", "games": "several"},
        {"name": "good", "wins": 2, "games": 3},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good"]


async def test_fetch_leaderboard_skips_non_numeric_win_rate():
    payload = [
        {"name": "junk", "winRate": "n/a", "wins": 1, "games": 1},
        {"name": "good", "winRate": 33.0, "wins": 1, "games": 3},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good"]
    assert entries[0].win_rate == 33.0


async def test_fetch_leaderboard_skips_null_rank_row():
    payload = [
        {"rank": None, "name": "null-rank", "wins": 1, "games": 1},
        {"rank": 2, "name": "good", "wins": 1, "games": 1},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good"]


async def test_fetch_leaderboard_skips_non_dict_items():
    payload = ["a string", 42, None, ["nested"], {"name": "good", "wins": 1, "games": 1}]
    client = _client_on(_route(leaderboard=_json(payload)))
    entries = await client.fetch_leaderboard()
    assert [e.name for e in entries] == ["good"]


async def test_fetch_leaderboard_all_rows_malformed_returns_empty_list():
    payload = [{"games_won": None}, {"wins": "x"}, "nope"]
    client = _client_on(_route(leaderboard=_json(payload)))
    assert await client.fetch_leaderboard() == []


async def test_fetch_leaderboard_row_index_used_for_default_rank_not_position():
    # Skipped rows still consume an index, so defaults follow the raw payload.
    payload = [
        {"games_won": None, "games_played": 1},
        {"name": "second", "wins": 1, "games": 1},
    ]
    client = _client_on(_route(leaderboard=_json(payload)))
    (entry,) = await client.fetch_leaderboard()
    assert entry.rank == 2


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"leaderboard": []},
        {"error": "no data"},
        {"count": 0},
        "unexpected string body",
        123,
    ],
)
async def test_fetch_leaderboard_empty_or_unexpected_shapes_return_empty(payload: Any):
    client = _client_on(_route(leaderboard=_json(payload)))
    assert await client.fetch_leaderboard() == []


async def test_fetch_leaderboard_json_null_body_returns_empty():
    handler = _route(
        leaderboard=httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )
    )
    client = _client_on(handler)
    assert await client.fetch_leaderboard() == []


async def test_fetch_leaderboard_non_json_body_raises():
    # No JSON guard here — the caller (fetch_snapshot) is what absorbs it.
    handler = _route(leaderboard=httpx.Response(200, text="<html>down</html>"))
    client = _client_on(handler)
    with pytest.raises(ValueError):  # json.JSONDecodeError
        await client.fetch_leaderboard()


async def test_fetch_leaderboard_envelope_with_non_list_value_is_ignored():
    payload = {"leaderboard": {"not": "a list"}}
    client = _client_on(_route(leaderboard=_json(payload)))
    assert await client.fetch_leaderboard() == []


# ===========================================================================
# fetch_token_price
# ===========================================================================


async def test_fetch_token_price_happy_path():
    payload = {"pairs": [_dex_pair()]}
    client = _client_on(_route(dexscreener=_json(payload)))
    price, change, mcap = await client.fetch_token_price()
    assert price == pytest.approx(0.00042)
    assert change == pytest.approx(12.5)
    assert mcap == pytest.approx(1_200_000.0)


async def test_fetch_token_price_picks_highest_liquidity_pair():
    payload = {
        "pairs": [
            _dex_pair(price="0.001", liquidity=100.0, market_cap=1.0),
            _dex_pair(price="0.002", liquidity=999_999.0, market_cap=2.0),
            _dex_pair(price="0.003", liquidity=5_000.0, market_cap=3.0),
        ]
    }
    client = _client_on(_route(dexscreener=_json(payload)))
    price, _change, mcap = await client.fetch_token_price()
    assert price == pytest.approx(0.002)
    assert mcap == pytest.approx(2.0)


async def test_fetch_token_price_null_liquidity_does_not_crash_ranking():
    payload = {
        "pairs": [
            {"priceUsd": "1.0", "liquidity": {"usd": None}, "priceChange": {"h24": 1}},
            {"priceUsd": "2.0", "liquidity": {"usd": 10.0}, "priceChange": {"h24": 2}},
        ]
    }
    client = _client_on(_route(dexscreener=_json(payload)))
    price, change, _mcap = await client.fetch_token_price()
    assert price == pytest.approx(2.0)
    assert change == pytest.approx(2.0)


async def test_fetch_token_price_accepts_singular_pair_dict():
    payload = {"pair": _dex_pair(price="0.5")}
    client = _client_on(_route(dexscreener=_json(payload)))
    price, _change, _mcap = await client.fetch_token_price()
    assert price == pytest.approx(0.5)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"pairs": None},
        {"pairs": []},
        {"schemaVersion": "1.0.0", "pairs": None},
    ],
)
async def test_fetch_token_price_no_pairs_returns_all_none(payload: dict):
    client = _client_on(_route(dexscreener=_json(payload)))
    assert await client.fetch_token_price() == (None, None, None)


@pytest.mark.parametrize("bad_price", ["not-a-number", None, "", {"usd": 1}])
async def test_fetch_token_price_non_numeric_price_returns_all_none(bad_price: Any):
    payload = {"pairs": [{"priceUsd": bad_price, "priceChange": {"h24": 1.0}}]}
    client = _client_on(_route(dexscreener=_json(payload)))
    assert await client.fetch_token_price() == (None, None, None)


async def test_fetch_token_price_null_price_change_returns_all_none():
    payload = {"pairs": [{"priceUsd": "1.0", "priceChange": {"h24": None}}]}
    client = _client_on(_route(dexscreener=_json(payload)))
    assert await client.fetch_token_price() == (None, None, None)


async def test_fetch_token_price_unexpected_top_level_shape_returns_all_none():
    # A list body has no ``.get`` — the blanket except must absorb it.
    client = _client_on(_route(dexscreener=_json([_dex_pair()])))
    assert await client.fetch_token_price() == (None, None, None)


async def test_fetch_token_price_non_json_body_returns_all_none():
    handler = _route(
        dexscreener=httpx.Response(200, text="<html>maintenance</html>")
    )
    client = _client_on(handler)
    assert await client.fetch_token_price() == (None, None, None)


async def test_fetch_token_price_http_error_returns_all_none():
    handler = _route(dexscreener=_json({"detail": "oops"}, status=503))
    transport = RecordingTransport(handler)
    client = DOTAClient(http_client=httpx.AsyncClient(transport=transport))
    assert await client.fetch_token_price() == (None, None, None)
    assert len(transport.urls) == dc._MAX_RETRIES


async def test_fetch_token_price_transport_error_returns_all_none():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    client = DOTAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    assert await client.fetch_token_price() == (None, None, None)


async def test_fetch_token_price_missing_fields_currently_yield_zero_not_none():
    """CURRENT BEHAVIOUR, pinned deliberately — see note below.

    ``priceUsd``/``priceChange.h24``/``marketCap`` all default to ``0`` when the
    key is absent, so a pair that simply omits market cap reports ``0.0``
    instead of "unknown".  That conflicts with the codebase rule "a failed read
    is None, never 0"; this test documents the gap so a future fix has to
    update it consciously rather than silently.
    """
    payload = {"pairs": [{"liquidity": {"usd": 10.0}}]}
    client = _client_on(_route(dexscreener=_json(payload)))
    assert await client.fetch_token_price() == (0.0, 0.0, 0.0)


async def test_fetch_token_price_null_market_cap_coerced_to_zero():
    payload = {
        "pairs": [{"priceUsd": "1.5", "priceChange": {"h24": -3.0}, "marketCap": None}]
    }
    client = _client_on(_route(dexscreener=_json(payload)))
    price, change, mcap = await client.fetch_token_price()
    assert price == pytest.approx(1.5)
    assert change == pytest.approx(-3.0)
    # ``or 0`` swallows the null — 0.0, not None (same gap as above).
    assert mcap == 0.0


# ===========================================================================
# fetch_snapshot — partial-failure assembly
# ===========================================================================


async def test_fetch_snapshot_all_sources_healthy():
    handler = _route(
        game_state=_json(_game_state_payload()),
        leaderboard=_json([{"name": "alice", "wins": 1, "games": 2}]),
        dexscreener=_json({"pairs": [_dex_pair()]}),
    )
    client = _client_on(handler)
    snap = await client.fetch_snapshot()

    assert snap.fetched_at > 0
    assert snap.game_state is not None and snap.game_state.tick == 42
    assert [e.name for e in snap.leaderboard] == ["alice"]
    assert snap.token_price_usd == pytest.approx(0.00042)
    assert snap.token_price_change_24h == pytest.approx(12.5)
    assert snap.token_market_cap == pytest.approx(1_200_000.0)


async def test_fetch_snapshot_game_state_failure_leaves_none_and_keeps_rest():
    handler = _route(
        game_state=_json({"detail": "down"}, status=500),
        leaderboard=_json([{"name": "alice", "wins": 1, "games": 2}]),
        dexscreener=_json({"pairs": [_dex_pair()]}),
    )
    client = _client_on(handler)
    snap = await client.fetch_snapshot()

    assert snap.game_state is None
    assert [e.name for e in snap.leaderboard] == ["alice"]
    assert snap.token_price_usd == pytest.approx(0.00042)


async def test_fetch_snapshot_leaderboard_failure_leaves_empty_list():
    handler = _route(
        game_state=_json(_game_state_payload()),
        leaderboard=_json({"detail": "down"}, status=500),
        dexscreener=_json({"pairs": [_dex_pair()]}),
    )
    client = _client_on(handler)
    snap = await client.fetch_snapshot()

    assert snap.game_state is not None
    assert snap.leaderboard == []
    assert snap.token_price_usd is not None


async def test_fetch_snapshot_price_failure_leaves_none_price_fields():
    handler = _route(
        game_state=_json(_game_state_payload()),
        leaderboard=_json([]),
        dexscreener=_json({"pairs": []}),
    )
    client = _client_on(handler)
    snap = await client.fetch_snapshot()

    assert snap.game_state is not None
    assert snap.token_price_usd is None
    assert snap.token_price_change_24h is None
    assert snap.token_market_cap is None


async def test_fetch_snapshot_total_outage_still_returns_snapshot():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nxdomain: host is gone", request=request)

    client = DOTAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    snap = await client.fetch_snapshot()

    assert snap.game_state is None
    assert snap.leaderboard == []
    assert snap.token_price_usd is None
    assert snap.token_price_change_24h is None
    assert snap.token_market_cap is None
    assert snap.fetched_at > 0


async def test_fetch_snapshot_garbage_bodies_degrade_without_raising():
    handler = _route(
        game_state=_json({"tick": "not-an-int"}),
        leaderboard=_json("surprise"),
        dexscreener=_json({"nope": True}),
    )
    client = _client_on(handler)
    snap = await client.fetch_snapshot()

    assert snap.game_state is None
    assert snap.leaderboard == []
    assert snap.token_price_usd is None


# ===========================================================================
# Lifecycle
# ===========================================================================


async def test_close_does_not_close_injected_client():
    http = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    client = DOTAClient(http_client=http)
    await client.close()
    assert http.is_closed is False
    await http.aclose()


async def test_context_manager_closes_owned_client():
    async with _offline_client() as client:
        inner = client._client
        assert client._owns_client is False  # injected in this helper
    assert inner.is_closed is False
    await inner.aclose()


async def test_default_client_is_owned_and_closed():
    client = DOTAClient()
    assert client._owns_client is True
    inner = client._client
    await client.close()
    assert inner.is_closed is True
