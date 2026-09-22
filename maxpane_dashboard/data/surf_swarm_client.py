"""Keyless reads of the IMD swarm control plane (``docs/imd_swarm_api.md``).

GET only, a two-host pool, no key of any kind.  Every fetch returns ``None``
rather than raising: a failed read is not a zero and not an empty list.

The host serves no filters, no caching validators and no pagination, so the
job list is all-or-nothing; the manager's counter check, not this client,
decides how often it is paid for.  No path ever carries a ``?``: parameters
on ``/jobs`` are ignored upstream and would imply a page that does not exist
(``docs/surf_swarm_v2_implementation_plan.md`` §0 R3/R4); ``_get`` raises on
one. The detail getter interpolating caller text into a path,
:meth:`SwarmClient.fetch_job`, refuses an id that is not a plain path segment
and returns ``None`` -- so the contract above holds at every public getter.
:meth:`SwarmClient.fetch_seat` formats an ``int`` (``{token:d}``) and refuses
anything else before any request. ``submissions`` validates a canonical UUID
before interpolating a job id; any 404 is confined to that job.

The seat getter distinguishes a real negative from a failed read:
``fetch_seat`` returns a fresh copy of :data:`UNKNOWN_SEAT` for the host's
``404 {"error": "unknown_seat"}`` -- a seat never paired, a real negative
(``docs/surf_agent_seats_spec.md`` §2, §5). ``submissions`` similarly returns
:data:`SUBMISSIONS_NOT_FOUND` for HTTP 404; transport/parse failures remain None.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient

logger = logging.getLogger(__name__)


#: Characters that would turn a job id into a second path segment, a query
#: or a fragment.  Whitespace is refused beside them.
_NOT_A_SEGMENT = frozenset("?/#")


def _is_path_segment(value: object) -> bool:
    """``True`` for a non-empty ``str`` that is exactly one path segment."""
    if not isinstance(value, str) or not value:
        return False
    return not any(ch in _NOT_A_SEGMENT or ch.isspace() for ch in value)

def parse_job_id(value: object) -> str | None:
    """A canonical UUID path component, shared with answer cache validation."""
    if not isinstance(value, str):
        return None
    try:
        return value if str(UUID(value)) == value else None
    except ValueError:
        return None


__all__ = [
    "SWARM_API", "SWARM_API_HOSTS", "SWARM_INTER_CALL_DELAY", "SWARM_REQUEST_TIMEOUT",
    "SwarmClient", "UNKNOWN_SEAT",
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

#: ``fetch_seat``'s normalised answer for a token no device has paired with:
#: the host's ``404 {"error": "unknown_seat", "detail": ...}``, reduced to its
#: error code.  Distinct from ``None`` (a failed read).  Read-only by
#: construction -- a ``MappingProxyType``, so no caller can alter the module's
#: copy -- and ``fetch_seat`` returns a fresh ``dict`` each time, so a caller
#: may alter its own result.  Compare with ``==`` (a proxy equals its dict).
UNKNOWN_SEAT: MappingProxyType[str, str] = MappingProxyType({"error": "unknown_seat"})

#: Explicit job-local HTTP 404; None remains transient transport/parse failure.
SUBMISSIONS_NOT_FOUND = MappingProxyType({"error": "submissions_not_found"})


@dataclass(frozen=True)
class _Answered404:
    """A 404 whose body the caller's predicate accepted as an answer."""

    body: Any


def _is_unknown_seat(body: object) -> bool:
    return isinstance(body, dict) and body.get("error") == UNKNOWN_SEAT["error"]


class SwarmClient(OwnedHttpClient):
    """Reads ``/health``, ``/jobs``, ``/jobs/{id}``, ``/launches``,
    ``/seats/{token}``, ``/sites``, ``/skills``, ``/version``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        hosts: Sequence[str] = SWARM_API_HOSTS,
        base_url: str | None = None,
        inter_call_delay: float = SWARM_INTER_CALL_DELAY,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        # ``follow_redirects=False`` (WP7): a redirect is a host this client
        # did not choose. The pool is an allowlist of two names that are one
        # deployment; a 3xx off either is answered by rotation to the other
        # pool entry for that request, never by following the ``Location``
        # to wherever it points.
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(SWARM_REQUEST_TIMEOUT),
            follow_redirects=False,
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

    async def _get(
        self,
        path: str,
        *,
        raw: bool = False,
        answers_404: Callable[[Any], bool] | None = None,
    ) -> Any:
        """One GET, tried once per host in pool order.

        A transport error, a non-200 or a non-JSON body rotates to the next
        host for **this request**; the pool itself never changes.  Every host
        failing is ``None`` — never a partial value.

        ``answers_404`` (opt-in, JSON reads only): a 404 whose JSON body the
        predicate accepts is an *answer*, returned as ``_Answered404(body)``
        with no further host asked.  Any other 404 -- a removed route, an HTML
        page -- rotates like every other non-200.
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
            if response.status_code == 404 and answers_404 is not None and not raw:
                try:
                    answer = response.json()
                except ValueError:
                    answer = None
                if answers_404(answer):
                    return _Answered404(answer)
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

    async def fetch_workers(self) -> dict[str, Any] | None:
        """Live device envelope through the shared host pool and pacing."""
        return await self._dict("/workers")

    async def fetch_contributors(self) -> dict[str, Any] | None:
        """Per-device lifetime counters, including served envelope totals."""
        return await self._dict("/contributors")

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
        """One job's detail, or ``None`` -- also for an id that is no path segment.

        The id is interpolated into the path.  One carrying ``?``, ``/``,
        ``#`` or whitespace, an empty one or a non-string would build a
        request this API does not serve (``_get`` raises on ``?``), and the
        getter contract is ``None``, never a raise -- so it is refused here,
        before any request (WP2 review, 2026-09-21).
        """
        if not _is_path_segment(job_id):
            logger.debug("swarm fetch_job refused an id that is no path segment: %r", job_id)
            return None
        return await self._dict(f"/jobs/{job_id}")

    async def submissions(self, job_id: str) -> dict[str, Any] | None:
        """One job's submissions, explicit 404 sentinel, or transient-failure None."""
        job = parse_job_id(job_id)
        if job is None:
            return None
        body = await self._get(f"/jobs/{job}/submissions", answers_404=lambda body: True)
        if isinstance(body, _Answered404):
            return dict(SUBMISSIONS_NOT_FOUND)
        return body if isinstance(body, dict) else None

    async def fetch_seat(self, token: int) -> dict[str, Any] | None:
        """``GET /seats/{token}``: the seat's dict, a fresh copy of
        :data:`UNKNOWN_SEAT`, or ``None``.

        ``UNKNOWN_SEAT`` is the host's ``404 unknown_seat`` -- a token never
        paired, an answer: no other host is asked.  Any other 404 is a failed
        read and rotates, so a removed route never reads as "never paired".
        A token that is not an ``int``, is a ``bool`` or is negative is
        refused before any request; the path is formatted from the ``int``
        (``{token:d}``), so caller text never reaches it.
        """
        if isinstance(token, bool) or not isinstance(token, int) or token < 0:
            logger.debug("swarm fetch_seat refused a token that is no non-negative int: %r", token)
            return None
        body = await self._get(f"/seats/{token:d}", answers_404=_is_unknown_seat)
        if isinstance(body, _Answered404):
            return dict(UNKNOWN_SEAT)
        return body if isinstance(body, dict) else None
