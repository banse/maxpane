"""Async client for RugPull Bakery tRPC API and agent.json.

Uses httpx for non-blocking HTTP with manual exponential backoff retries.
All public methods return parsed Pydantic models and never raise on
transient network failures -- they log warnings and re-raise only after
exhausting retries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from maxpane_dashboard.data.models import (
    ActivityEvent,
    AgentConfig,
    BakeryDetail,
    BakeryMember,
    BakerySummary,
    PaginatedBakeries,
    PaginatedMembers,
    Season,
    unwrap_trpc,
)
from maxpane_dashboard.data.price import PriceClient
from maxpane_dashboard.data.snapshot import GameSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 10.0


class GameDataClient:
    """Fetches game data from rugpullbakery.com APIs.

    Parameters
    ----------
    base_url:
        Root URL of the game site (no trailing slash).
    price_client:
        Optional ``PriceClient`` instance. One is created automatically
        if not supplied.
    """

    def __init__(
        self,
        base_url: str = "https://www.rugpullbakery.com",
        *,
        price_client: PriceClient | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._trpc_base = f"{self._base_url}/api/trpc"
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._price_client = price_client or PriceClient()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and price client."""
        await self._price_client.close()
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> GameDataClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_with_retry(self, url: str) -> httpx.Response:
        """Issue a GET request with exponential-backoff retries.

        Retries on ``httpx`` transport errors and 5xx status codes.
        Raises the final exception if all retries are exhausted.
        """
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(url)
                if resp.status_code >= 500:
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
                    logger.warning(
                        "Request to %s failed (attempt %d/%d): %s  -- retrying in %.1fs",
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Request to %s failed after %d attempts: %s",
                        url,
                        _MAX_RETRIES,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]

    def _trpc_url(self, procedure: str, input_data: dict[str, Any] | None = None) -> str:
        """Build the full tRPC GET URL for a procedure.

        tRPC expects ``?input=<url-encoded JSON>`` where the JSON has the
        shape ``{"json": <payload>}``.
        """
        url = f"{self._trpc_base}/{procedure}"
        if input_data is not None:
            encoded = quote(json.dumps({"json": input_data}), safe="")
            url = f"{url}?input={encoded}"
        return url

    async def _trpc_get(
        self,
        procedure: str,
        input_data: dict[str, Any] | None = None,
    ) -> Any:
        """Fetch a tRPC procedure and unwrap the result envelope."""
        url = self._trpc_url(procedure, input_data)
        resp = await self._get_with_retry(url)
        return unwrap_trpc(resp.json())

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_agent_config(self) -> AgentConfig:
        """Fetch ``/agent.json`` and parse into an ``AgentConfig`` model."""
        url = f"{self._base_url}/agent.json"
        resp = await self._get_with_retry(url)
        return AgentConfig.from_api(resp.json())

    async def get_active_season(self) -> Season:
        """Fetch the current active season.

        The endpoint returns a list; we pick the first active one.
        """
        seasons_raw: list[dict[str, Any]] = await self._trpc_get(
            "leaderboard.getActiveSeason",
        )
        for s in seasons_raw:
            season = Season.from_api(s)
            if season.is_active:
                return season
        # Fallback: return the first season if none marked active
        return Season.from_api(seasons_raw[0])

    async def get_top_bakeries(self, *, max_pages: int = 5) -> list[BakerySummary]:
        """Fetch the full leaderboard, paginating up to *max_pages* pages.

        Returns a flat list of ``BakerySummary`` sorted by cookie count
        (server-side ordering).
        """
        all_bakeries: list[BakerySummary] = []
        cursor: dict[str, Any] | None = None

        for _ in range(max_pages):
            input_data: dict[str, Any] = {}
            if cursor is not None:
                input_data["cursor"] = cursor

            raw = await self._trpc_get("leaderboard.getTopBakeries", input_data)
            page = PaginatedBakeries.from_api(raw)
            all_bakeries.extend(page.items)

            if page.next_cursor is None:
                break
            # The API expects txCount without decimal places
            tx_count = page.next_cursor.tx_count
            if "." in tx_count:
                tx_count = tx_count.split(".")[0]
            cursor = {
                "txCount": tx_count,
                "id": page.next_cursor.id,
            }

        return all_bakeries

    async def get_bakery_by_id(self, bakery_id: int) -> BakeryDetail:
        """Fetch details for a single bakery."""
        raw = await self._trpc_get(
            "leaderboard.getBakeryById",
            {"bakeryId": bakery_id},
        )
        return BakeryDetail.from_api(raw)

    async def get_bakery_members(
        self,
        bakery_id: int,
        season_id: int,
        *,
        max_pages: int = 3,
    ) -> list[BakeryMember]:
        """Fetch bakery members with pagination."""
        all_members: list[BakeryMember] = []
        cursor: dict[str, Any] | None = None

        for _ in range(max_pages):
            input_data: dict[str, Any] = {
                "bakeryId": bakery_id,
                "seasonId": season_id,
            }
            if cursor is not None:
                input_data["cursor"] = cursor

            raw = await self._trpc_get("leaderboard.getBakeryMembers", input_data)
            page = PaginatedMembers.from_api(raw)
            all_members.extend(page.items)

            if page.next_cursor is None:
                break
            cursor = {
                "txCount": page.next_cursor.tx_count,
                "address": page.next_cursor.address,
            }

        return all_members

    async def get_activity_feed(
        self,
        bakery_id: int,
        season_id: int,
    ) -> list[ActivityEvent]:
        """Fetch activity feed for a single bakery."""
        raw: list[dict[str, Any]] = await self._trpc_get(
            "leaderboard.getActivityFeed",
            {"bakeryId": bakery_id, "seasonId": season_id},
        )
        return [ActivityEvent.from_api(e) for e in raw]

    async def get_activity_feed_global(
        self,
        season_id: int,
        *,
        top_n: int = 10,
    ) -> list[ActivityEvent]:
        """Fetch activity across the top *top_n* bakeries.

        There is no dedicated global feed endpoint, so we fan out to the
        top bakeries and merge results by timestamp (descending).
        """
        bakeries = await self.get_top_bakeries()
        target_ids = [b.id for b in bakeries[:top_n]]

        tasks = [
            self.get_activity_feed(bid, season_id) for bid in target_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[ActivityEvent] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Failed to fetch activity for a bakery: %s", result)
                continue
            merged.extend(result)

        # Sort by timestamp descending (most recent first)
        merged.sort(key=lambda e: int(e.timestamp), reverse=True)
        return merged

    # ------------------------------------------------------------------
    # Unified snapshot
    # ------------------------------------------------------------------

    async def fetch_all(self) -> GameSnapshot:
        """Fetch everything concurrently and return a unified snapshot.

        Individual sub-fetches that fail are logged and replaced with
        safe defaults so the dashboard always gets *something*.
        """
        (
            agent_config_result,
            season_result,
            bakeries_result,
            eth_price_result,
        ) = await asyncio.gather(
            self.get_agent_config(),
            self.get_active_season(),
            self.get_top_bakeries(),
            self._price_client.get_eth_usd(),
            return_exceptions=True,
        )

        # --- Unpack with fallbacks ---
        if isinstance(agent_config_result, BaseException):
            logger.error("Failed to fetch agent config: %s", agent_config_result)
            raise agent_config_result  # Cannot proceed without config

        agent_config: AgentConfig = agent_config_result

        if isinstance(season_result, BaseException):
            logger.error("Failed to fetch active season: %s", season_result)
            raise season_result  # Cannot proceed without season

        season: Season = season_result

        bakeries: list[BakerySummary] = []
        if isinstance(bakeries_result, BaseException):
            logger.warning("Failed to fetch bakeries: %s", bakeries_result)
        else:
            bakeries = bakeries_result

        eth_price: float = 0.0
        if isinstance(eth_price_result, BaseException):
            logger.warning("Failed to fetch ETH price: %s", eth_price_result)
        else:
            eth_price = eth_price_result

        # Fetch global activity using the season we just obtained
        try:
            activity = await self.get_activity_feed_global(season.id, top_n=5)
        except Exception as exc:
            logger.warning("Failed to fetch global activity feed: %s", exc)
            activity = []

        return GameSnapshot(
            season=season,
            bakeries=bakeries,
            activity=activity,
            agent_config=agent_config,
            eth_price_usd=eth_price,
            fetched_at=time.time(),
        )
