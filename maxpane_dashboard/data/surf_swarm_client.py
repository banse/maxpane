"""Keyless reads of the IMD swarm control plane (``docs/imd_swarm_api.md``).

GET only, a two-host pool, no key of any kind.  Every fetch returns ``None``
rather than raising: a failed read is not a zero and not an empty list.

The /jobs route accepts validated ``limit`` (1..500), exclusive ISO ``before``,
updated-since ``since`` and text ``q`` (up to 200 characters) through HTTP query parameters. Its returned
count is a page count, never a network total. The default read is a bounded
recent page. Paths never contain queries. Overview, records and hourly getters
preserve their envelopes for validation by the data projection layer.

The seat getter distinguishes a real negative from a failed read:
``fetch_seat`` returns a fresh copy of :data:`UNKNOWN_SEAT` for the host's
``404 {"error": "unknown_seat"}`` -- a seat never paired, a real negative
(``docs/surf_agent_seats_spec.md`` §2, §5). ``submissions`` similarly returns
:data:`SUBMISSIONS_NOT_FOUND` for HTTP 404; transport/parse failures remain None.
"""
from __future__ import annotations

import asyncio
import logging
import json
import math
import time
from collections import OrderedDict
from copy import deepcopy
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from maxpane_dashboard.analytics.surf_ids import parse_job_id

import httpx
from maxpane_dashboard.data.surf_transport import SurfTransport

from maxpane_dashboard.data.rpc_common import OwnedHttpClient
from maxpane_dashboard.data.surf_models import SWARM_WORKFLOW_PAGE_SIZE, SWARM_WORKFLOW_MAX_PAGES

logger = logging.getLogger(__name__)


#: Characters that would turn a job id into a second path segment, a query
#: or a fragment.  Whitespace is refused beside them.
_NOT_A_SEGMENT = frozenset("?/#")


def _workflow_cursor(value: object) -> datetime | None:
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", value) is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_path_segment(value: object) -> bool:
    """``True`` for a non-empty ``str`` that is exactly one path segment."""
    if not isinstance(value, str) or not value:
        return False
    return not any(ch in _NOT_A_SEGMENT or ch.isspace() for ch in value)



__all__ = [
    "SWARM_API", "SWARM_API_HOSTS", "SWARM_INTER_CALL_DELAY", "SWARM_REQUEST_TIMEOUT",
    "SwarmClient", "JobDetailRead", "UNKNOWN_SEAT", "SEAT_BUSY",
]

#: The swarm's control plane, as a pool. Rechecked 2026-10-23: the former
#: identitymdcontrol-plane-production Railway deployment returns HTTP 404.
#: The replacement named by the developer (aidude/docs/imd-api-changelog.md)
#: and api.imd.fun both returned /version commit 0a3c69e93b0f112cdf60b2bbfdd98e81bcecfb3c.
#: This is one source with two names. The documented name stays first.
#: A failure on one host rotates to the next for that
#: request only; the pool is never shrunk or reordered at runtime — a
#: provider's error is evidence only about the request it read
#: (``rules/data.md``).  The write surface is authenticated; these reads are
#: the public subset.
SWARM_API_HOSTS: tuple[str, ...] = (
    "https://api.imd.fun",
    "https://api-imd.up.railway.app",
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

#: Every host reported temporary load shedding, distinct from a failed read:
#: ``fetch_seat`` and (F-S3) ``fetch_job`` return a fresh copy.
SEAT_BUSY: MappingProxyType[str, str] = MappingProxyType({"error": "busy"})

#: Explicit job-local HTTP 404; None remains transient transport/parse failure.
SUBMISSIONS_NOT_FOUND = MappingProxyType({"error": "submissions_not_found"})


_DETAIL_API_VERSION = "jobs-v1"
_DETAIL_MAX_ENTRIES = 400
_DETAIL_MAX_BYTES = 16 * 1024 * 1024
_DETAIL_MAX_ENTRY_BYTES = 512 * 1024
_TERMINAL_JOBS = frozenset(("completed", "failed", "cancelled"))


@dataclass(frozen=True)
class JobDetailRead:
    """A consumer-owned payload and the original HTTP observation."""

    payload: dict | None
    observed_at: float | None
    started_mono: float
    revision: str | None
    from_cache: bool


@dataclass
class _DetailMemo:
    read: JobDetailRead
    expires: float
    epoch: int
    size: int
    last_good: JobDetailRead | None


@dataclass
class _DetailFlight:
    task: asyncio.Task
    waiters: int = 0


def _detail_metadata(body: dict) -> dict[str, str]:
    metadata = {}
    revision = body.get("updatedAt")
    if isinstance(revision, str) and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z", revision):
        try:
            datetime.fromisoformat(revision)
            metadata["updatedAt"] = revision
        except ValueError:
            pass
    state = body.get("state", body.get("status"))
    if isinstance(state, str) and state and state.strip() == state:
        metadata["state"] = state
    return metadata


@dataclass(frozen=True)
class _Answered404:
    """A 404 whose body the caller's predicate accepted as an answer."""

    body: Any


def _is_unknown_seat(body: object) -> bool:
    return isinstance(body, dict) and body.get("error") == UNKNOWN_SEAT["error"]


class SwarmClient(OwnedHttpClient):
    """Reads ``/health``, ``/jobs``, ``/jobs/{id}``, ``/launches``,
    ``/seats/{token}``, ``/sites``, ``/skills``, ``/version``, ``/workflows``,
    ``/oracle/requests``, ``/oracle/requests/{uuid}``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        hosts: Sequence[str] = SWARM_API_HOSTS,
        base_url: str | None = None,
        inter_call_delay: float = SWARM_INTER_CALL_DELAY,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        transport: SurfTransport | None = None,
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
        self._transport = transport or SurfTransport(delay=self._delay)
        self._sleep = sleep or asyncio.sleep
        self._last_call: float = 0.0
        self._clock, self._monotonic = clock, monotonic
        self._detail_memo: OrderedDict[str, _DetailMemo] = OrderedDict()
        self._detail_flights: dict[str, _DetailFlight] = {}
        self._detail_tasks: set[asyncio.Task] = set()  # Includes retiring scopes until done.
        self._detail_epochs: dict[str, int] = {}
        self._detail_hints: dict[str, dict[str, str]] = {}
        self._detail_slots = asyncio.Semaphore(8)
        self._detail_scope = self._current_detail_scope()
        self._detail_closed = False

    async def _get(
        self,
        path: str,
        *,
        raw: bool = False,
        params: Mapping[str, str] | None = None,
        answers_404: Callable[[Any], bool] | None = None,
        seat_busy: bool = False,
        _on_start: Callable[[], None] | None = None,
    ) -> Any:
        """One GET, tried once per host in pool order.

        A transport error, a non-200 or a non-JSON body rotates to the next
        host for **this request**; the pool itself never changes.  Every host
        failing is ``None`` — never a partial value.

        ``answers_404`` (opt-in, JSON reads only): a 404 whose JSON body the
        predicate accepts is an *answer*, returned as ``_Answered404(body)``
        with no further host asked.  Any other 404 -- a removed route, an HTML
        page -- rotates like every other non-200.

        ``seat_busy`` opts seat and job-detail reads into a distinct result
        only when every host returns HTTP 503 with the exact JSON error
        ``busy``.
        """
        if "?" in path:
            raise ValueError(f"the swarm API takes no query parameters: {path!r}")
        await self._sleep(self._delay)
        if _on_start is not None:
            _on_start()
        busy_hosts = 0
        for attempt, host in enumerate(self._hosts):
            try:
                await self._transport.acquire(host + path)
                response = await self._client.get(host + path, params=params)
                self._transport.observe(host + path, response)
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
            if seat_busy and response.status_code == 503:
                try:
                    error = response.json()
                except ValueError:
                    error = None
                if isinstance(error, dict) and error.get("error") == "busy":
                    busy_hosts += 1
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
        return SEAT_BUSY if busy_hosts == len(self._hosts) else None

    async def _dict(self, path: str) -> dict[str, Any] | None:
        body = await self._get(path)
        return body if isinstance(body, dict) else None

    async def fetch_oracle_requests(self, *, limit: int, before: str | None = None) -> list[dict] | None:
        """Oracle pagination alone accepts query parameters; [] is a real empty."""
        if type(limit) is not int or not 1 <= limit <= 500:
            return None
        if before is not None and (not isinstance(before, str) or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z", before) is None):
            return None
        params = {"limit": str(limit)}
        if before is not None:
            params["before"] = before
        body = await self._get("/oracle/requests", params=params)
        rows = body.get("requests") if isinstance(body, dict) else None
        return rows if isinstance(rows, list) else None

    async def fetch_oracle_detail(self, request_id: str) -> dict | None:
        """Full members for the selected ORACLES request, through the shared pool."""
        if parse_job_id(request_id) is None:
            return None
        return await self._dict("/oracle/requests/" + request_id)

    async def fetch_oracle_request(self, request_id: str, submission_hash: str) -> dict | None:
        """A removed route or unknown request is an unavailable read, never absence."""
        if (parse_job_id(request_id) is None or not isinstance(submission_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", submission_hash) is None):
            return None
        body = await self._get("/oracle/requests/" + request_id, params={"members": submission_hash})
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

    async def _list(
        self, path: str, key: str, *, params: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]] | None:
        body = await self._get(path, params=params)
        if not isinstance(body, dict):
            return None
        rows = body.get(key)
        # A missing list is an unread list.  ``[]`` from the host is a real
        # empty and passes through.
        return rows if isinstance(rows, list) else None

    async def fetch_overview(self) -> dict[str, Any] | None:
        return await self._dict("/swarm")

    async def fetch_seat_records(self) -> dict[str, Any] | None:
        return await self._dict("/seats/records")

    async def fetch_steps_hourly(self) -> dict[str, Any] | None:
        return await self._dict("/steps/hourly")

    async def fetch_jobs(self, *, limit: int = 100, before: str | None = None,
                         q: str | None = None, since: str | None = None) -> list[dict[str, Any]] | None:
        """One bounded page: ``before`` pages creation; ``since`` filters updates."""
        if type(limit) is not int or not 1 <= limit <= 500:
            return None
        for cursor in (before, since):
            if cursor is None:
                continue
            if not isinstance(cursor, str) or re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z", cursor) is None:
                return None
            try:
                datetime.fromisoformat(cursor)
            except ValueError:
                return None
        if q is not None and (not isinstance(q, str) or len(q) > 200):
            return None
        params = {"limit": str(limit)}
        if before is not None:
            params["before"] = before
        if q is not None:
            params["q"] = q
        if since is not None:
            params["since"] = since
        rows = await self._list("/jobs", "jobs", params=params)
        for row in rows or ():
            if not isinstance(row, dict):
                continue
            job = row.get("id")
            if not isinstance(job, str) or job not in self._detail_epochs:
                continue
            metadata = _detail_metadata(row)
            previous = self._detail_hints.setdefault(job, {})
            if any(previous.get(key) != value for key, value in metadata.items()):
                self._detail_epochs[job] += 1
            previous.update(metadata)
        return rows

    async def fetch_launches(self) -> list[dict[str, Any]] | None:
        return await self._list("/launches", "launches", params={"limit": "100"})

    async def fetch_launch(self, launch_id: str) -> dict[str, Any] | None:
        if parse_job_id(launch_id) is None:
            return None
        return await self._dict(f"/launches/{launch_id}")

    async def fetch_launch_jobs(self, launch_id: str) -> dict[str, Any] | None:
        """Launch/job links without large reward allocations and claims."""
        if parse_job_id(launch_id) is None:
            return None
        body = await self._get(f"/launches/{launch_id}", params={"light": "1"})
        return body if isinstance(body, dict) else None

    async def fetch_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """Authoritative contract/frontend job relationship for one workflow."""
        if parse_job_id(workflow_id) is None:
            return None
        return await self._dict(f"/workflows/{workflow_id}")

    async def fetch_launch_policies(self) -> list[dict[str, Any]] | None:
        return await self._list("/launch/policies", "policies")

    async def fetch_sites(self) -> list[dict[str, Any]] | None:
        return await self._list("/sites", "sites")

    async def fetch_skills(self) -> list[dict[str, Any]] | None:
        return await self._list("/skills", "skills")

    async def fetch_workflows(self, *, limit: int = SWARM_WORKFLOW_PAGE_SIZE,
                              before: str | None = None, since: str | None = None) -> list[dict[str, Any]] | None:
        """``GET /workflows`` -- the newest ``limit`` workflows, newest ``createdAt`` first.

        ``limit`` must be a strict ``int`` (not a ``bool``) in 1..100, else ``None``
        before any request; it travels in ``params=``, never in the path. A body
        whose ``workflows`` is not a list is a failed read; ``[]`` is a real empty
        page. ``count`` is the page size, never a total, and is not read.
        ``since`` filters updatedAt independently of the createdAt ``before`` cursor.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            logger.debug("swarm fetch_workflows refused a limit outside 1..100: %r", limit)
            return None
        if any(cursor is not None and _workflow_cursor(cursor) is None for cursor in (before, since)):
            return None
        params = {"limit": str(limit)}
        if before is not None:
            params["before"] = before
        if since is not None:
            params["since"] = since
        return await self._list("/workflows", "workflows", params=params)

    async def fetch_workflow_history(self) -> tuple[list[dict] | None, bool]:
        """Bounded, newest-first backfill and whether the end was reached.

        A later failure retains the pages already read. `_get` pays the configured
        inter-call delay on every page. Only a short/empty page proves completion.
        """
        rows, seen = [], set()
        before = None
        for _ in range(SWARM_WORKFLOW_MAX_PAGES):
            page = await self.fetch_workflows(limit=SWARM_WORKFLOW_PAGE_SIZE, before=before)
            if page is None:
                if before is not None:
                    logger.warning("partial workflow history: later page failed")
                return (rows if before is not None else None), False
            cursor = page[-1].get("createdAt") if page and isinstance(page[-1], dict) else None
            stamp = _workflow_cursor(cursor)
            if before is not None and page and (stamp is None or stamp >= _workflow_cursor(before)):
                logger.warning("partial workflow history: cursor did not advance")
                return rows, False
            for row in page:
                if not isinstance(row, dict):
                    continue
                identity = row.get("id")
                if isinstance(identity, str):
                    if identity in seen:
                        continue
                    seen.add(identity)
                rows.append(row)
            if len(page) < SWARM_WORKFLOW_PAGE_SIZE:
                return rows, True
            if stamp is None:
                logger.warning("partial workflow history: invalid cursor")
                return rows, False
            before = cursor
        return rows, False

    def _current_detail_scope(self) -> tuple:
        return tuple(sorted(str(httpx.URL(host)).rstrip("/") for host in self._hosts)), _DETAIL_API_VERSION

    def _forget_detail(self, job: str) -> None:
        if job not in self._detail_memo and job not in self._detail_flights:
            self._detail_epochs.pop(job, None)
            self._detail_hints.pop(job, None)

    def _finish_detail(self, job: str, flight: _DetailFlight) -> None:
        self._detail_tasks.discard(flight.task)
        if flight.task.done() and not flight.task.cancelled():
            flight.task.exception()  # Retrieve errors even if its final waiter was cancelled.
        if flight.waiters == 0 and self._detail_flights.get(job) is flight:
            self._detail_flights.pop(job)
            self._forget_detail(job)

    async def _check_detail_scope(self) -> None:
        scope = self._current_detail_scope()
        if scope == self._detail_scope:
            return
        self._detail_scope = scope
        tasks = [flight.task for flight in self._detail_flights.values()]
        for task in tasks:
            task.cancel()
        self._detail_flights.clear()
        self._detail_memo.clear()
        self._detail_epochs.clear()
        self._detail_hints.clear()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _remember_detail(self, job: str, read: JobDetailRead, epoch: int) -> None:
        old = self._detail_memo.get(job)
        good = read if read.observed_at is not None else old.last_good if old else None
        size = len(json.dumps(read.payload, ensure_ascii=False, separators=(",", ":")).encode())
        if good is not None and good is not read:
            size += len(json.dumps(good.payload, ensure_ascii=False, separators=(",", ":")).encode())
        if size > _DETAIL_MAX_ENTRY_BYTES:
            self._detail_memo.pop(job, None)
            return
        ttl = (600 if _detail_metadata(read.payload or {}).get("state") in _TERMINAL_JOBS else 30
               ) if read.observed_at is not None else 15
        self._detail_memo[job] = _DetailMemo(read, self._monotonic() + ttl, epoch, size, good)
        self._detail_memo.move_to_end(job)
        total = sum(entry.size for entry in self._detail_memo.values())
        while len(self._detail_memo) > _DETAIL_MAX_ENTRIES or total > _DETAIL_MAX_BYTES:
            removed, entry = self._detail_memo.popitem(last=False)
            total -= entry.size
            self._forget_detail(removed)

    async def _load_job_detail(self, job: str) -> tuple[JobDetailRead, int, tuple]:
        async with self._detail_slots:
            started, epoch = self._monotonic(), self._detail_epochs[job]
            scope = self._detail_scope

            def begin():
                nonlocal started, epoch
                started, epoch = self._monotonic(), self._detail_epochs[job]

            body = await self._get("/jobs/" + job, seat_busy=True, _on_start=begin)
            observed = self._clock()
            if body is SEAT_BUSY:
                payload = dict(SEAT_BUSY)
            elif (isinstance(body, dict) and body.get("error") is None
                  and body.get("id") == job):
                payload = body
            else:
                payload = None
            good = payload is not None and payload.get("error") != "busy"
            read = JobDetailRead(payload, observed if good else None, started,
                                 _detail_metadata(payload or {}).get("updatedAt") if good else None, False)
            if (not self._detail_closed and scope == self._detail_scope
                    and epoch == self._detail_epochs.get(job)):
                if good:
                    self._detail_hints.setdefault(job, {}).update(_detail_metadata(payload))
                self._remember_detail(job, read, epoch)
            return read, epoch, scope

    def known_job_revision(self, job_id: str) -> str | None:
        """Last validated server revision in this scope; never fetch or register."""
        if (self._detail_closed or not _is_path_segment(job_id)
                or self._current_detail_scope() != self._detail_scope):
            return None
        return self._detail_hints.get(job_id, {}).get('updatedAt')

    async def read_job_detail(self, job_id: str, *, fresh_after: float | None = None) -> JobDetailRead:
        """Share bounded detail reads; freshness constrains the real HTTP start."""
        if (not _is_path_segment(job_id) or self._detail_closed or
                (fresh_after is not None and (isinstance(fresh_after, bool) or
                 not isinstance(fresh_after, (int, float)) or not math.isfinite(fresh_after)))):
            return JobDetailRead(None, None, self._monotonic(), None, False)
        await self._check_detail_scope()
        while not self._detail_closed:
            epoch = self._detail_epochs.setdefault(job_id, 0)
            memo = self._detail_memo.get(job_id)
            if (memo is not None and memo.epoch == epoch and self._monotonic() < memo.expires
                    and (fresh_after is None or memo.read.started_mono >= fresh_after)):
                self._detail_memo.move_to_end(job_id)
                read = memo.read
                return JobDetailRead(deepcopy(read.payload), read.observed_at,
                                     read.started_mono, read.revision, True)
            flight = self._detail_flights.get(job_id)
            if flight is not None and flight.task.cancelling():
                try:
                    await asyncio.shield(flight.task)
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                if self._detail_flights.get(job_id) is flight:
                    self._detail_flights.pop(job_id)
                continue
            if flight is not None and flight.task.done():
                self._detail_flights.pop(job_id)
                flight = None
            if flight is None:
                flight = _DetailFlight(asyncio.create_task(self._load_job_detail(job_id)))
                self._detail_flights[job_id] = flight
                self._detail_tasks.add(flight.task)
                flight.task.add_done_callback(
                    lambda _, flight=flight: self._finish_detail(job_id, flight))
            flight.waiters += 1
            try:
                read, result_epoch, result_scope = await asyncio.shield(flight.task)
                current = (result_epoch == self._detail_epochs.get(job_id)
                           and result_scope == self._detail_scope)
            finally:
                flight.waiters -= 1
                if flight.waiters == 0:
                    if not flight.task.done():
                        flight.task.cancel()
                    elif self._detail_flights.get(job_id) is flight:
                        self._detail_flights.pop(job_id)
                        self._forget_detail(job_id)
            if current and (fresh_after is None or read.started_mono >= fresh_after):
                return JobDetailRead(deepcopy(read.payload), read.observed_at,
                                     read.started_mono, read.revision, False)
        return JobDetailRead(None, None, self._monotonic(), None, False)

    async def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        """Compatibility adapter; every consumer owns its whole payload copy."""
        return (await self.read_job_detail(job_id)).payload

    async def close(self) -> None:
        """Drain all detail tasks before closing our owned HTTP client."""
        self._detail_closed = True
        tasks = list(self._detail_tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._detail_flights.clear()
        self._detail_memo.clear()
        self._detail_epochs.clear()
        self._detail_hints.clear()
        await super().close()

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
        :data:`UNKNOWN_SEAT` or :data:`SEAT_BUSY`, or ``None``.

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
        body = await self._get(f"/seats/{token:d}", answers_404=_is_unknown_seat, seat_busy=True)
        if isinstance(body, _Answered404):
            return dict(UNKNOWN_SEAT)
        if body is SEAT_BUSY:
            return dict(SEAT_BUSY)
        return body if isinstance(body, dict) and body.get("error") != "busy" else None
