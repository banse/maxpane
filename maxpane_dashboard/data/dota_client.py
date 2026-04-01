"""Async HTTP client for Defense of the Agents game data.

Fetches game state, leaderboard, and DOTA token price via REST APIs.
Uses httpx.AsyncClient with exponential-backoff retries, matching the
pattern established by the OCM client.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from maxpane_dashboard.data.dota_models import (
    DOTAGameState,
    DOTALeaderboardEntry,
    DOTASnapshot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
_REQUEST_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

_GAME_STATE_URL = "https://www.defenseoftheagents.com/api/game/state"
_LEADERBOARD_URL = "https://www.defenseoftheagents.com/api/leaderboard"
_TOKEN_ADDRESS = "0x5f09821cbb61e09d2a83124ae0b56aaa3ae85b07"
_DEXSCREENER_URL = (
    f"https://api.dexscreener.com/latest/dex/tokens/{_TOKEN_ADDRESS}"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")


def _strip_non_ascii(s: str) -> str:
    """Remove non-ASCII characters from a string."""
    return _NON_ASCII_RE.sub("", s)


def _calc_win_rate(item: dict) -> float:
    """Calculate win rate from API response fields."""
    # Try pre-computed field first
    wr = item.get("winRate", item.get("win_rate"))
    if wr is not None:
        return float(wr)
    # Compute from games_won / games_played
    won = int(item.get("games_won", item.get("wins", 0)))
    played = int(item.get("games_played", item.get("games", 0)))
    return (won / played * 100.0) if played > 0 else 0.0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class DOTAClient:
    """Fetches Defense of the Agents data from REST APIs.

    Parameters
    ----------
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  If not provided
        one is created internally and closed on ``close()``.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._first_leaderboard_fetch = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> DOTAClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: retry helper
    # ------------------------------------------------------------------

    async def _get_with_retry(self, url: str) -> httpx.Response:
        """GET with exponential-backoff retries on transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(url)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_SECONDS[attempt]
                    logger.debug(
                        "GET %s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.debug(
                        "GET %s failed after %d attempts: %s",
                        url,
                        _MAX_RETRIES,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Public API: fetch_game_state
    # ------------------------------------------------------------------

    async def fetch_game_state(self, game: int = 1) -> DOTAGameState:
        """Fetch the current game state for the given game number.

        Parameters
        ----------
        game:
            Game instance number (default 1).

        Returns
        -------
        DOTAGameState
            Parsed game state with tick, lanes, heroes, towers, bases.
        """
        url = f"{_GAME_STATE_URL}?game={game}"
        resp = await self._get_with_retry(url)
        data = resp.json()
        return DOTAGameState(**data)

    # ------------------------------------------------------------------
    # Public API: fetch_leaderboard
    # ------------------------------------------------------------------

    async def fetch_leaderboard(self) -> list[DOTALeaderboardEntry]:
        """Fetch the player leaderboard.

        Response format is not fully documented -- we parse permissively
        and log the raw response at DEBUG level on first fetch.

        Returns
        -------
        list[DOTALeaderboardEntry]
            Parsed leaderboard entries, sorted by rank.
        """
        resp = await self._get_with_retry(_LEADERBOARD_URL)
        raw = resp.json()

        if self._first_leaderboard_fetch:
            logger.debug("DOTA leaderboard raw response: %s", raw)
            self._first_leaderboard_fetch = False

        entries: list[DOTALeaderboardEntry] = []

        # Try to parse as a list of dicts (most likely format)
        items: list[Any] = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            # Could be wrapped in a key like "leaderboard", "data", "players"
            for key in ("leaderboard", "data", "players", "entries", "results"):
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break
            if not items:
                # Last resort: try values if single list value
                for v in raw.values():
                    if isinstance(v, list):
                        items = v
                        break

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                entry = DOTALeaderboardEntry(
                    rank=item.get("rank", idx + 1),
                    name=_strip_non_ascii(str(item.get("name", item.get("player", item.get("username", f"Player {idx + 1}"))))),
                    wins=int(item.get("games_won", item.get("wins", 0))),
                    games=int(item.get("games_played", item.get("games", 0))),
                    win_rate=_calc_win_rate(item),
                    player_type=str(item.get("playerType", item.get("player_type", item.get("type", "Human")))),
                )
                entries.append(entry)
            except (ValueError, TypeError) as exc:
                logger.debug("Skipping malformed leaderboard entry %d: %s", idx, exc)

        return entries

    # ------------------------------------------------------------------
    # Public API: fetch_token_price
    # ------------------------------------------------------------------

    async def fetch_token_price(self) -> tuple[float | None, float | None, float | None]:
        """Fetch DOTA token price and market cap from DexScreener.

        Returns
        -------
        tuple[float | None, float | None, float | None]
            ``(price_usd, price_change_24h, market_cap)`` or ``(None, None, None)`` on failure.
        """
        try:
            resp = await self._get_with_retry(_DEXSCREENER_URL)
            data = resp.json()

            pairs = data.get("pairs") or data.get("pair")
            if not pairs:
                logger.debug("DexScreener returned no pairs for DOTA token")
                return (None, None, None)

            if isinstance(pairs, dict):
                pairs = [pairs]

            if not isinstance(pairs, list) or len(pairs) == 0:
                return (None, None, None)

            # Pick the pair with highest liquidity
            best_pair = pairs[0]
            if len(pairs) > 1:
                best_pair = max(
                    pairs,
                    key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                )

            price_usd = float(best_pair.get("priceUsd", 0))
            price_change = best_pair.get("priceChange", {})
            price_change_24h = float(price_change.get("h24", 0))
            market_cap = float(best_pair.get("marketCap", 0) or 0)

            return (price_usd, price_change_24h, market_cap)

        except Exception as exc:
            logger.debug("Failed to fetch DOTA token price: %s", exc)
            return (None, None, None)

    # ------------------------------------------------------------------
    # Public API: fetch_snapshot
    # ------------------------------------------------------------------

    async def fetch_snapshot(self, game: int = 1) -> DOTASnapshot:
        """Fetch all DOTA data and assemble into a DOTASnapshot.

        Each sub-fetch is wrapped in try/except so partial data is
        returned rather than a total failure.

        Parameters
        ----------
        game:
            Game instance number (default 1).
        """
        now = time.time()

        # Game state
        game_state: DOTAGameState | None = None
        try:
            game_state = await self.fetch_game_state(game)
        except Exception as exc:
            logger.warning("Failed to fetch DOTA game state: %s", exc)

        # Leaderboard
        leaderboard: list[DOTALeaderboardEntry] = []
        try:
            leaderboard = await self.fetch_leaderboard()
        except Exception as exc:
            logger.warning("Failed to fetch DOTA leaderboard: %s", exc)

        # Token price + market cap
        token_price_usd, token_price_change_24h, token_market_cap = await self.fetch_token_price()

        return DOTASnapshot(
            fetched_at=now,
            game_state=game_state,
            leaderboard=leaderboard,
            token_price_usd=token_price_usd,
            token_price_change_24h=token_price_change_24h,
            token_market_cap=token_market_cap,
        )
