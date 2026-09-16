"""Keyless reads of the IMD swarm control plane (``docs/imd_swarm_api.md``).

GET only, one host, no key of any kind.  Every fetch returns ``None`` rather
than raising: a failed read is not a zero and not an empty list.

The host serves no filters, no caching validators and no pagination, so the
job list is all-or-nothing; the manager's counter check, not this client,
decides how often it is paid for.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient

logger = logging.getLogger(__name__)

__all__ = [
    "SWARM_API", "SWARM_INTER_CALL_DELAY", "SWARM_REQUEST_TIMEOUT", "SwarmClient",
]

#: The swarm's control plane.  Named in the explorer's own page source; its
#: write surface is authenticated, these reads are the public subset.
SWARM_API = "https://identitymdcontrol-plane-production.up.railway.app"

SWARM_REQUEST_TIMEOUT = 15.0
#: Measured: 62 sequential detail reads at this spacing drew 62 × 200 with no
#: rate limiting (``docs/imd_swarm_api.md``).  It is politeness, not a limit.
SWARM_INTER_CALL_DELAY = 0.12


class SwarmClient(OwnedHttpClient):
    """Reads ``/health``, ``/jobs``, ``/jobs/{id}``, ``/launches``, ``/sites``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = SWARM_API,
        inter_call_delay: float = SWARM_INTER_CALL_DELAY,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(SWARM_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._base = base_url.rstrip("/")
        self._delay = float(inter_call_delay)
        self._sleep = sleep or asyncio.sleep
        self._last_call: float = 0.0

    async def _get(self, path: str, *, raw: bool = False) -> Any:
        """One GET.  ``None`` on any failure — never a partial value."""
        await self._sleep(self._delay)
        try:
            response = await self._client.get(self._base + path)
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("swarm GET %s failed: %s", path, exc)
            return None
        if response.status_code != 200:
            logger.debug("swarm GET %s -> %s", path, response.status_code)
            return None
        if raw:
            return response.content
        try:
            return response.json()
        except ValueError as exc:
            logger.debug("swarm GET %s served non-JSON: %s", path, exc)
            return None

    async def fetch_health(self) -> dict[str, Any] | None:
        body = await self._get("/health")
        return body if isinstance(body, dict) else None

    async def _list(self, path: str, key: str) -> list[dict[str, Any]] | None:
        body = await self._get(path)
        if not isinstance(body, dict):
            return None
        rows = body.get(key)
        # A missing list is an unread list.  ``[]`` from the host is a real
        # empty and passes through.
        return rows if isinstance(rows, list) else None

    async def fetch_jobs(self) -> list[dict[str, Any]] | None:
        return await self._list("/jobs", "jobs")

    async def fetch_launches(self) -> list[dict[str, Any]] | None:
        return await self._list("/launches", "launches")

    async def fetch_sites(self) -> list[dict[str, Any]] | None:
        return await self._list("/sites", "sites")

    async def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        body = await self._get(f"/jobs/{job_id}")
        return body if isinstance(body, dict) else None
