"""Keyless reads of the IMD swarm control plane (``docs/imd_swarm_api.md``).

GET only, a two-host pool, no key of any kind.  Every fetch returns ``None``
rather than raising: a failed read is not a zero and not an empty list.

The host serves no filters, no caching validators and no pagination, so the
job list is all-or-nothing; the manager's counter check, not this client,
decides how often it is paid for.  No path ever carries a ``?``: parameters
on ``/jobs`` are ignored upstream and would imply a page that does not exist
(``docs/surf_swarm_v2_implementation_plan.md`` §0 R3/R4).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient

logger = logging.getLogger(__name__)

__all__ = [
    "SWARM_API", "SWARM_API_HOSTS", "SWARM_INTER_CALL_DELAY", "SWARM_REQUEST_TIMEOUT",
    "SwarmClient",
]

#: The swarm's control plane, as a pool.  Measured 2026-09-21 (plan §0 R1):
#: both names serve the same deployment — ``/version`` answered commit
#: ``282e2b19…`` on both on 2026-09-21 and ``1308af71…`` on both the day
#: before — so this is one source with two names, not two sources.
#: ``api.imd.fun`` is the documented name and goes first; the Railway host is
#: the one the explorer's own page source names and the one every fixture
#: before the v2 corpus was captured from.  Neither sends a CORS header, which
#: a TUI never needs.  A failure on one host rotates to the next for that
#: request only; the pool is never shrunk or reordered at runtime — a
#: provider's error is evidence only about the request it read
#: (``rules/data.md``).  The write surface is authenticated; these reads are
#: the public subset.
SWARM_API_HOSTS: tuple[str, ...] = (
    "https://api.imd.fun",
    "https://identitymdcontrol-plane-production.up.railway.app",
)

#: The first host of the pool, kept under its pre-v2 name for importers.
SWARM_API = SWARM_API_HOSTS[0]

SWARM_REQUEST_TIMEOUT = 15.0
#: Measured: 62 sequential detail reads at this spacing drew 62 × 200 with no
#: rate limiting (``docs/imd_swarm_api.md``).  It is politeness, not a limit.
#: Paid once per request, not once per host attempt.
SWARM_INTER_CALL_DELAY = 0.12


class SwarmClient(OwnedHttpClient):
    """Reads ``/health``, ``/jobs``, ``/jobs/{id}``, ``/launches``, ``/sites``,
    ``/skills``, ``/version``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        hosts: Sequence[str] = SWARM_API_HOSTS,
        base_url: str | None = None,
        inter_call_delay: float = SWARM_INTER_CALL_DELAY,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(SWARM_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        # ``base_url`` predates the pool; given, it is a one-host pool so a
        # caller pinning a host is never silently rotated into the default.
        pool: Sequence[str] = (base_url,) if base_url is not None else hosts
        self._hosts: tuple[str, ...] = tuple(host.rstrip("/") for host in pool)
        if not self._hosts:
            raise ValueError("SwarmClient needs at least one host")
        self._delay = float(inter_call_delay)
        self._sleep = sleep or asyncio.sleep
        self._last_call: float = 0.0

    async def _get(self, path: str, *, raw: bool = False) -> Any:
        """One GET, tried once per host in pool order.

        A transport error, a non-200 or a non-JSON body rotates to the next
        host for **this request**; the pool itself never changes.  Every host
        failing is ``None`` — never a partial value.
        """
        if "?" in path:
            raise ValueError(f"the swarm API takes no query parameters: {path!r}")
        await self._sleep(self._delay)
        for attempt, host in enumerate(self._hosts):
            try:
                response = await self._client.get(host + path)
            except (httpx.HTTPError, OSError) as exc:
                logger.debug("swarm GET %s%s failed: %s", host, path, exc)
                continue
            if response.status_code != 200:
                logger.debug("swarm GET %s%s -> %s", host, path, response.status_code)
                continue
            if raw:
                body: Any = response.content
            else:
                try:
                    body = response.json()
                except ValueError as exc:
                    logger.debug("swarm GET %s%s served non-JSON: %s", host, path, exc)
                    continue
            if attempt:
                logger.debug(
                    "swarm GET %s answered by %s after %d host(s) failed", path, host, attempt,
                )
            return body
        logger.debug("swarm GET %s failed on every host", path)
        return None

    async def _dict(self, path: str) -> dict[str, Any] | None:
        body = await self._get(path)
        return body if isinstance(body, dict) else None

    async def fetch_health(self) -> dict[str, Any] | None:
        return await self._dict("/health")

    async def fetch_version(self) -> dict[str, Any] | None:
        return await self._dict("/version")

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

    async def fetch_skills(self) -> list[dict[str, Any]] | None:
        return await self._list("/skills", "skills")

    async def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        return await self._dict(f"/jobs/{job_id}")
