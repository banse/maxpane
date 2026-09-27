"""SeatManager -- one refresh cycle of the PEPEPANE dashboard (spec §4.3, §9, §7).

    tail thread (daemon=True, owned here, started ONLY by seat_cli.py when not --once) -> queue.Queue
    RefreshGuard tick -> fetch_and_compute():
        1. drain(): queue -> ledger.ingest -> ring -> detector state (event bumps)
        2. inline reads: systemd/fixture unit + host (docker: the `unit` tier, 30 s)
        3. detached tiers (asyncio.ensure_future, one in flight per tier, last-good behind its own asOfUtc):
           broker_status 600 s · workstat 300 s (+ gate/ping/audit-tail) · sessions 120 s · standing 60 s ·
           seatwork 120/300 s · reasons 300 s (<= 2 jobs) · plane 300 s   [--offline removes the last four]
        4. build the v2 document -> redact -> validate -> fold -> the flat SEAT_KEYS dict

``fetch_and_compute()`` never raises and never starts the tail.  ``BrokerProtocol.read`` is a blocking
socket call, so every broker tier runs it through ``asyncio.to_thread``.  No Textual import, no
``post_message``, no ``subprocess``/``socket`` here (spec §14 purity rule 3): the seams are
``data/seat_tail.py`` and ``data/seat_broker_client.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import platform
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import httpx

from maxpane_dashboard.analytics import seat_auth, seat_cost, seat_signals as sig, seat_tiers
from maxpane_dashboard.analytics.seat_redact import redact, redact_agent_sentence, redact_tree
from maxpane_dashboard.data import seat_api, seat_models as models
from maxpane_dashboard.data.safe_call import safe_call as _safe_call   # the shared guard (tests/data/test_safe_call.py)
from maxpane_dashboard.data.seat_broker_client import (
    BrokerError, BrokerProtocol, FakeBroker, FixtureUnitReader, UnitReader,
    parse_imd_skills, parse_imd_status, parse_imd_tools, parse_whoami,
)
from maxpane_dashboard.data.seat_ledger import LEDGER_FILE, IngestResult, LedgerState, SeatLedger
from maxpane_dashboard.data.seat_log_grammar import GRAMMAR_VERSION, LogLine, classify, parse_ts
from maxpane_dashboard.data.seat_tail import (
    ALIVE_STAMP_S, KIND_LIST, STALE_BACKFILL_REASON, TAIL_FILE, LineSource, ListLineSource, TailState, TailThread,
)

logger = logging.getLogger(__name__)
_monotonic = time.monotonic

Clock = Callable[[], float]

# -- tier cadences (spec §4.3; contract §B) ------------------------------------
TIER_UNIT_S = 30                #: Mac docker inspect/stats
TIER_BROKER_STATUS_S = 600      #: seat, status, skills, tools, hints-stat, auth-mtime; whoami once per session
TIER_WORKSTAT_S = 300           #: work-stat, outbox, orphans (+ ping, gate preview, audit-tail -- deviation 8)
TIER_SESSIONS_S = 120           #: +EVENT_BUMP_SESSIONS_S after each `submitted`
TIER_STANDING_S = 60            #: +EVENT_BUMP_STANDING_S after each `submitted`; 15 s while a control plan is open
TIER_STANDING_PLAN_OPEN_S = 15
TIER_SEATWORK_S = 120           #: +EVENT_BUMP_SEATWORK_S after each `stored`
TIER_SEATWORK_SETTLED_S = 300   #: once every open row has a verdict
TIER_REASONS_S = 300            #: <= MAX_REASONS_PER_CYCLE jobs per cycle
TIER_PLANE_S = 300              #: /services + /health
EVENT_BUMP_SESSIONS_S = 20
EVENT_BUMP_STANDING_S = 30
EVENT_BUMP_SEATWORK_S = 60
EVENT_BUMP_WORKSTAT_S = 5       #: (invented) gate preview + outbox after every lifecycle line (deviation 8)
TIER_RETRY_S = 60               #: (invented) a failed tier is offered again after min(TTL, 60 s), never at once
DOCKER_TIMEOUT_S = 25           #: every docker subprocess.run(timeout=25) (§4.2, §5.5, §12.2) -- consumed by seat_broker_client
DOCKER_BREAKER_S = 300          #: 5-min breaker per verb after any timeout (§4.2)
LEDGER_ROWS_ON_SCREEN = 60      #: tasks.window.rows in the v2 document (§7)
COST_WINDOW_DAYS = 7
SERIES_DAYS = 14
FLEET_CLAUSE_STALE_S = 300      #: spec §6: /health fills daemon.fleetOnline/fleetEnrolled once the heartbeat clause is > 5 min old
BACKFILL_QUIET_S = 2.0          #: (invented) --once: the backfill is complete when no line arrived for 2 s ...
BACKFILL_MAX_S = 25.0           #: ... or after 25 s (the docker backfill timeout, contract §B)
FIXTURE_HOST = "fixture"
SYSTEMD_HOST = "systemd"
DOCKER_HOST = "docker"
HOST_KINDS = (SYSTEMD_HOST, DOCKER_HOST, FIXTURE_HOST)

TIERS = ("unit", "broker_status", "workstat", "sessions", "standing", "seatwork", "reasons", "plane")
TIER_TTL_S = {"unit": 30, "broker_status": 600, "workstat": 300, "sessions": 120, "standing": 60,
              "seatwork": 120, "reasons": 300, "plane": 300}
OFFLINE_REMOVES = ("standing", "seatwork", "reasons", "plane")
#: tier -> the ``sources`` entries it feeds (each entry keeps its own ok/asOf/failures).
TIER_SOURCES: dict[str, tuple[str, ...]] = {
    "unit": ("unit",),
    "broker_status": ("seat", "status", "skills", "hints", "auth"),
    "workstat": ("workstat", "broker"),
    "sessions": ("sessions",),
    "standing": ("standing",),
    "seatwork": ("seatWork",),
    "reasons": ("reasons",),
    "plane": ("plane",),
}
#: The Mac's CLI-fed sources are container-reported text (spec §4.2).
CONTAINER_TRUST_SOURCES = frozenset({"seat", "status", "skills", "sessions"})
LOG_RING = 400                  #: lines kept for the LOG panel (SeatLog.MAX_LINES)

_EMPTY_INGEST = IngestResult(lines=0, opened=0, closed=0, stored=0, restarts=0, unknown=0, events=())


class _QuietSource:
    """A LineSource that emits only idle ticks (``None`` every :data:`ALIVE_STAMP_S`) until closed.

    Handed to the tail thread after a one-shot list source has been replayed, so the thread's
    backoff loop does not replay the same fixture every few seconds (the fixture host, Task 7.12).
    The ticks are the LineSource contract (WP3 deviation 1): ``TailThread`` stamps ``aliveAt`` only
    when ``lines()`` yields, so a silently blocking source would read ``tail dead`` after 45 s.
    ``TailThread.stop()`` calls :meth:`close`, which ends the loop within one tick.
    """

    kind = KIND_LIST

    def __init__(self) -> None:
        self._closed = threading.Event()

    def open(self) -> None:
        self._closed.clear()

    def lines(self):
        while not self._closed.wait(ALIVE_STAMP_S):
            yield None

    def exit_code(self) -> int | None:
        return 0

    def close(self) -> None:
        self._closed.set()

    def backfill(self):
        return None


class _ReplaySource:
    """Replay a one-shot source, then hold the attach open with idle ticks until closed.

    WP3's ``TailThread`` sets ``reason = "tail: exited rc=0 — retry in 1s"`` when a source ends and clears it
    only when a *later* source delivers a line, which a :class:`_QuietSource` never does -- so a replayed
    list that simply ran out would read ``tail exited`` (hero red) for good.  A clean end (``exit_code() ==
    0``) therefore keeps yielding ``None`` ticks until :meth:`close`; any other exit is passed through, so a
    dying fixture (``tail_dead/``) still dies.
    """

    kind = KIND_LIST

    def __init__(self, inner: LineSource) -> None:
        self._inner = inner
        self._closed = threading.Event()
        self.kind = getattr(inner, "kind", KIND_LIST)

    def open(self) -> None:
        self._closed.clear()
        self._inner.open()

    def lines(self):
        for raw in self._inner.lines():
            if self._closed.is_set():
                return
            yield raw
        if self._inner.exit_code() != 0:
            return
        while not self._closed.wait(ALIVE_STAMP_S):
            yield None

    def exit_code(self) -> int | None:
        return self._inner.exit_code()

    def close(self) -> None:
        self._closed.set()
        self._inner.close()

    def backfill(self):
        return self._inner.backfill()


def _single_source_factory(source: LineSource) -> Callable[[TailState], LineSource]:
    """Serve *source* once (wrapped in a :class:`_ReplaySource`) and a :class:`_QuietSource` afterwards."""
    served = {"done": False}

    def factory(state: TailState) -> LineSource:
        if not served["done"]:
            served["done"] = True
            return _ReplaySource(source)
        return _QuietSource()

    return factory


class _BoundedSource:
    """Synchronous --once source with total and quiet deadlines on idle ticks.

    Source operations already carry their transport timeouts. The total deadline
    also covers the Docker backfill and any journald cursor fallback attempt.
    """

    def __init__(self, inner: LineSource, deadline: float) -> None:
        self._inner = inner
        self.kind = inner.kind
        self._deadline = deadline
        self._closed = False

    def open(self) -> None:
        self._inner.open()

    def lines(self):
        last_line = _monotonic()
        for raw in self._inner.lines():
            now = _monotonic()
            if now >= self._deadline:
                return
            if raw is None:
                if now - last_line >= BACKFILL_QUIET_S:
                    return
            else:
                last_line = now
            yield raw

    def backfill(self):
        return self._inner.backfill()

    def exit_code(self):
        return self._inner.exit_code()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._inner.close()


class _TierFailure(Exception):
    """A tier read that answered `not ok` -- lands nothing, counts one failure, retries after min(TTL, 60 s)."""


class SeatManager:
    """Owner of the tail queue, the ledger, the tiers and the last document (contract §C.13)."""

    def __init__(
        self,
        *,
        tail: LineSource | Callable[[TailState], LineSource] | None = None,
        broker: BrokerProtocol | None = None,
        api: seat_api.SeatApiClient | None = None,
        ledger: SeatLedger | None = None,
        ledger_path: str | Path | None = None,
        unit_reader: UnitReader | None = None,
        now: Clock | None = None,
        host: str = SYSTEMD_HOST,
        unit: str = "imd-worker.service",
        container: str | None = None,
        runtime: str | None = None,
        seat: int | None = None,
        agent: int | None = None,
        offline: bool = False,
        poll_interval: int = 5,
        maxpane_dir: Path | None = None,
        producer: str = models.PRODUCER,
        hostname: str | None = None,
    ) -> None:
        if host not in HOST_KINDS:
            raise ValueError(f"host must be one of {HOST_KINDS}, not {host!r}")
        self._clock: Clock = now or time.time
        self._host = host
        self._unit = unit
        self._container = container
        self._runtime = runtime
        self._seat = seat
        self._agent = agent
        self._offline = bool(offline)
        self._poll_interval = int(poll_interval)
        self._producer = producer
        self._hostname = hostname or platform.node() or None
        self._maxpane_dir = Path(maxpane_dir) if maxpane_dir is not None else Path.home() / ".maxpane"
        self._maxpane_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        self._last_good: dict[str, tuple[Any, float]] = {}   # before the ledger: its tier_lookup reads the `seat` projection
        self._ledger = ledger if ledger is not None else SeatLedger(
            Path(ledger_path) if ledger_path is not None else self._maxpane_dir / LEDGER_FILE, seat=seat, now=self._clock,
            tier_lookup=self._tier_lookup,           # WP2 deviation 2: tier_derived exists only through this injection (spec §5.4, §10)
        )
        self._owns_ledger = ledger is None
        self._broker: BrokerProtocol = broker if broker is not None else FakeBroker(reachable=False)
        if self._offline:
            try:
                self._broker.offline = True          # every plan request carries offline: true (spec §4.3, §11 (b))
            except Exception:                        # noqa: BLE001 -- a read-only broker stub
                pass
        self._api: seat_api.SeatApiClient | None = None if self._offline else (api if api is not None else seat_api.SeatApiClient(now=self._clock))
        self._owns_api = api is None and not self._offline
        self._unit_reader = unit_reader

        if tail is None:
            self._tail_factory: Callable[[TailState], LineSource] | None = None
        elif callable(tail) and not hasattr(tail, "lines"):
            self._tail_factory = tail
        else:
            self._tail_factory = _single_source_factory(tail)  # type: ignore[arg-type]
        self._queue: "queue.Queue[LogLine]" = queue.Queue()
        self._thread: TailThread | None = None
        self._tail_state = TailState.load(self._maxpane_dir / TAIL_FILE)
        self._backfill_lines = 0
        self._backfill_done = False
        self._backfill_gap_note: str | None = None
        self._backfill_discarded_utc: str | None = None   # sticky WP3 backfill_note/backfill_at (deviation 11; Task 7.7)

        self._ring: deque[LogLine] = deque(maxlen=LOG_RING)
        self._seq = 0
        self._emitted_seq = 0
        self._last_drain_at: float | None = None
        self._last_events: tuple[str, ...] = ()

        self._due_at: dict[str, float] = {tier: 0.0 for tier in TIERS}
        self._in_flight: dict[str, asyncio.Task] = {}
        self._failures: dict[str, int] = {name: 0 for name in models.SOURCE_NAMES}
        self._reason: dict[str, str | None] = {name: None for name in models.SOURCE_NAMES}
        self._attempted: set[str] = set()
        self._whoami_key: str | None = None
        self._seatwork_settled = False
        self._error_count = 0
        self.plan_open = False
        self._restart_required = False
        self._refusal: models.Refusal | None = None
        self._document: dict = models.empty_document(
            producer=self._producer, started_at_utc=sig.iso_z(self._clock()), host=self._host_block(),
        )

    # ------------------------------------------------------------------ public surface

    @property
    def broker(self) -> BrokerProtocol:
        """The CONTROL modal reaches the broker through the manager only."""
        return self._broker

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def tail_thread(self) -> TailThread | None:
        return self._thread

    def set_restart_required(self, flag: bool) -> None:
        """Set by the CONTROL modal after a `skills-set` apply (restart required, spec §11)."""
        self._restart_required = bool(flag)

    def start_tail(self) -> bool:
        """Start the follower thread.  Called ONLY by seat_cli.py when not --once (and by the fixture host)."""
        if self._thread is not None:
            return True
        if self._tail_factory is None:
            logger.info("seat: no tail source configured; the tail thread is not started")
            return False
        self._thread = TailThread(self._tail_factory, self._queue, state=self._tail_state,
                                  state_path=self._maxpane_dir / TAIL_FILE, now=self._clock)
        self._thread.start()
        return True

    def pending_lines(self) -> int:
        return self._queue.qsize()

    def due(self, tier: str, now: float) -> bool:
        return float(now) >= self._due_at[tier]

    def bump(self, tier: str, seconds: float) -> None:
        """Offer *tier* again in *seconds* -- never later than it already was (event-driven re-reads)."""
        target = float(self._clock()) + float(seconds)
        self._due_at[tier] = min(self._due_at[tier], target)

    def document(self) -> dict:
        """The last v2 document (redacted; validated -- a refused document is replaced, see _cycle)."""
        return self._document

    async def fetch_and_compute(self) -> dict:
        """One cycle: drain -> inline reads -> tiers -> document -> fold.  NEVER raises; NEVER starts the tail."""
        try:
            return await self._cycle()
        except Exception as exc:                     # noqa: BLE001 -- the outermost guard
            self._error_count += 1
            logger.exception("PEPEPANE refresh cycle failed outright: %s", exc)
            try:
                return models.fold_status_document(self._document, now=float(self._clock()))
            except Exception:                        # noqa: BLE001
                return models.fold_status_document({"schemaVersion": 2}, now=float(self._clock()))

    async def settle(self) -> None:
        """Await every in-flight tier task (tests and --once)."""
        tasks = [task for task in self._in_flight.values() if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        """Stop the tail thread, cancel in-flight tiers, close the ledger and the api client we own."""
        thread, self._thread = self._thread, None
        if thread is not None:
            try:
                thread.stop(timeout_s=5.0)
            except Exception as exc:                 # noqa: BLE001
                logger.debug("seat: tail thread stop failed: %s", exc)
        for tier, task in list(self._in_flight.items()):
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._in_flight.clear()
        if self._owns_ledger:
            try:
                self._ledger.close()
            except Exception as exc:                 # noqa: BLE001
                logger.debug("seat: ledger close failed: %s", exc)
        if self._api is not None and self._owns_api:
            try:
                await self._api.close()
            except Exception as exc:                 # noqa: BLE001
                logger.debug("seat: api close failed: %s", exc)

    # ------------------------------------------------------------------ the cycle

    async def _cycle(self) -> dict:
        now = float(self._clock())
        started_at = sig.iso_z(now)
        self._drain_step(now)
        self._inline_step(now)
        self._spawn_tiers(now)
        doc = self._build_document(now, started_at)
        doc = self._no_currency(redact_tree(doc))
        doc["completedAtUtc"] = sig.iso_z(float(self._clock()))   # after every source has been folded in (mutation proof 13)
        refusal = models.validate_status_document(doc)
        if refusal is not None:
            self._error_count += 1
            self._refusal = refusal
            logger.warning("PEPEPANE status document refused (%s: %s); publishing an empty document", refusal.code, refusal.detail)
            doc = models.empty_document(producer=self._producer, started_at_utc=started_at, host=self._host_block())
            for name in doc["sources"]:                # not read (ok None), with the reason: the hero stays None, nothing is asserted from a refused read
                doc["sources"][name].update({"ok": None, "reason": f"document refused ({refusal.code})", "unavailable": True})
            doc["completedAtUtc"] = sig.iso_z(float(self._clock()))
        else:
            self._refusal = None
        doc["pollInterval"] = self._poll_interval
        self._document = doc
        # the LOG panel is a panel too: no `$` reaches it either (header Global Constraints, spec §10)
        new_lines = [self._no_currency(self._line_dict(line)) for line in self._ring if line.seq > self._emitted_seq]
        flat = models.fold_status_document(doc, now=float(self._clock()), log_lines=new_lines, log_seq=self._emitted_seq)
        self._emitted_seq = int(flat.get("seat_log_seq") or self._emitted_seq)
        return flat


    def _drain_step(self, now: float) -> None:
        self.drain()


    def _inline_step(self, now: float) -> None:
        """Systemd and the fixture host read the unit inline (ms); docker rides the 30 s `unit` tier."""
        if self._unit_reader is None or self._host == DOCKER_HOST:
            return
        self._read_unit_host(now)


    def _spawn_tiers(self, now: float) -> None:
        if self._host == DOCKER_HOST and self._unit_reader is not None:
            self._spawn("unit", lambda: asyncio.to_thread(self._read_unit_host, float(self._clock())), now)
        self._spawn("broker_status", self._tier_broker_status, now)
        self._spawn("workstat", self._tier_workstat, now)
        self._spawn("sessions", self._tier_sessions, now)
        if self._offline or self._api is None or self._seat is None:
            return                                   # --offline removes STANDING, SEATWORK, REASONS, PLANE (spec §4.3)
        self._spawn("standing", self._tier_standing, now)
        self._spawn("seatwork", self._tier_seatwork, now)
        self._spawn("reasons", self._tier_reasons, now)
        self._spawn("plane", self._tier_plane, now)




    # ------------------------------------------------------------------ tier bookkeeping

    def _ttl(self, tier: str) -> float:
        if tier == "standing" and self.plan_open:
            return float(TIER_STANDING_PLAN_OPEN_S)
        if tier == "seatwork" and self._seatwork_settled:
            return float(TIER_SEATWORK_SETTLED_S)
        return float(TIER_TTL_S[tier])


    def _mark_read(self, tier: str, now: float, *, ok: bool = True) -> None:
        """A completed tier read: the next offer is TTL away (min(TTL, TIER_RETRY_S) after a failure)."""
        delay = self._ttl(tier) if ok else min(self._ttl(tier), float(TIER_RETRY_S))
        self._due_at[tier] = float(now) + delay

    def _spawn(self, tier: str, factory: Callable[[], Any], now: float) -> None:
        """Detached tier task: one in flight per tier; nobody awaits it, so its exceptions are caught here."""
        running = self._in_flight.get(tier)
        if running is not None and not running.done():
            return
        if not self.due(tier, now):
            return

        async def run() -> None:
            try:
                await factory()
                self._mark_read(tier, float(self._clock()), ok=True)
            except asyncio.CancelledError:
                raise
            except _TierFailure as exc:
                for name in TIER_SOURCES[tier]:
                    self._fail(name, str(exc), float(self._clock()))
                self._mark_read(tier, float(self._clock()), ok=False)
                logger.debug("PEPEPANE tier %s not ok: %s", tier, exc)
            except Exception as exc:                 # noqa: BLE001 -- nobody awaits this task
                for name in TIER_SOURCES[tier]:
                    self._fail(name, f"{type(exc).__name__}: {redact(str(exc))[:120]}", float(self._clock()))
                self._mark_read(tier, float(self._clock()), ok=False)
                logger.warning("PEPEPANE tier %s failed: %s", tier, exc)

        self._in_flight[tier] = asyncio.ensure_future(run())


    def _land(self, source: str, payload: Any, ts: float) -> None:
        """A good read of *source*: last-good replaced, failures reset."""
        self._attempted.add(source)
        self._last_good[source] = (payload, float(ts))
        self._failures[source] = 0
        self._reason[source] = None

    def _fail(self, source: str, reason: str, now: float) -> None:
        """A failed read: last-good kept, failures counted, reason recorded (spec §6 rule 4)."""
        self._attempted.add(source)
        self._failures[source] += 1
        self._reason[source] = redact(reason)
        self._error_count += 1

    def _payload(self, source: str) -> Any:
        entry = self._last_good.get(source)
        return None if entry is None else entry[0]

    def _tier_lookup(self, runtime: str | None, model: str | None, effort: str | None, at: str | float | None, *,
                     seat: int | None = None) -> str | None:
        """The ledger's ``tier_lookup`` (WP2 ``TierLookup``): the dated table, superseded by the landed ``seat``
        projection's ``inference`` block going forward (spec §10; owner decision §16 #5)."""
        projection = self._payload("seat") if hasattr(self, "_last_good") else None
        inference = projection.get("inference") if isinstance(projection, Mapping) else None
        # an analytics call inside ledger.ingest(): a raise costs one tier_derived (None), never the drain
        return _safe_call(seat_tiers.tier_for, runtime, model, effort, at, seat=seat,
                          inference=dict(inference) if isinstance(inference, Mapping) else None, default=None)

    def _source_entry(self, name: str, now: float) -> dict:
        """One ``sources.<name>`` block from the tier state (spec §7 sources; §6 rule 4 unavailable)."""
        trust = "container" if (name in CONTAINER_TRUST_SOURCES and self._broker.trust() == "container") else "host"
        entry = models.empty_source(trust=trust)
        good = self._last_good.get(name)
        failures = self._failures[name]
        if name not in self._attempted:
            return entry
        ts = good[1] if good is not None else None
        entry["asOfUtc"] = sig.iso_z(ts) if ts is not None else None
        entry["ageS"] = int(max(0.0, now - ts)) if ts is not None else None
        entry["failures"] = failures
        entry["reason"] = self._reason[name]
        if failures == 0:
            entry["ok"] = True
            entry["unavailable"] = False
            return entry
        entry["ok"] = False
        if name in models.LAST_GOOD_SOURCES:
            entry["unavailable"] = (
                failures >= sig.API_UNAVAILABLE_FAILURES or ts is None or (now - ts) > sig.API_UNAVAILABLE_S
            )
        else:
            entry["unavailable"] = True
        return entry

    # ------------------------------------------------------------------ document blocks (empty here; later tasks fill them)

    def _host_block(self) -> dict:
        return {"kind": self._host, "unit": self._unit if self._host != DOCKER_HOST else None,
                "container": self._container, "runtime": self._runtime, "hostname": self._hostname}

    def _build_document(self, now: float, started_at: str) -> dict:
        doc = models.empty_document(producer=self._producer, started_at_utc=started_at, host=self._host_block())
        doc["sources"] = {name: self._source_entry(name, now) for name in models.SOURCE_NAMES}
        doc["sources"]["tail"] = self._tail_source(now)
        doc["seat"] = self._seat_block()
        doc["host"]["runtime"] = self._runtime
        doc["daemon"] = self._daemon_block(now)
        doc["current"] = self._current_block(now)
        doc["tasks"] = self._tasks_block(now)
        doc["today"] = self._today_block(now, doc["tasks"]["rows"])
        doc["auth"] = self._auth_block(now, doc["tasks"]["rows"])
        doc["unit"] = self._unit_block()
        doc["cost"] = self._cost_block(now)
        doc["quota"] = self._quota_block()
        doc["machine"] = self._machine_block()
        doc["control"] = self._control_block()
        doc["standing"] = self._standing_block()
        doc["queue"] = self._queue_block()
        doc["plane"] = self._plane_block(now)
        doc["daemon"].update(self._fleet_counts(now))
        changed = self._config_changed(doc["unit"])
        doc["seat"]["configChangedSinceStart"] = changed
        doc["control"]["restartRequired"] = True if (changed is True or self._restart_required) else (False if changed is False else None)
        if self._offline:
            for name in ("standing", "seatWork", "reasons", "plane"):
                doc["sources"].pop(name, None)     # absent entirely under --offline (spec §7)
        return doc



    def _tail_source(self, now: float) -> dict:
        """``sources.tail`` (spec §7): thread liveness, watermark, backfill notes."""
        entry = models.empty_source()
        entry["watermark"] = self._tail_state.cursor or self._tail_state.last_ts_utc
        as_of = self._last_drain_at
        thread = self._thread
        if thread is not None:
            alive_at = thread.alive_at
            ok, reason = sig.tail_state(alive_at=alive_at, now=now)
            thread_reason = thread.reason
            if ok and isinstance(thread_reason, str) and thread_reason.startswith("tail: exited"):
                ok, reason = False, thread_reason
            elif reason is None and thread_reason:
                reason = thread_reason                # a gap note or the stale-backfill discard: informational
            entry.update({
                "ok": ok, "reason": redact(reason) if reason else None, "unavailable": not ok,
                "threadAliveAt": sig.iso_z(alive_at) if alive_at is not None else None,
            })
        elif self._backfill_done:
            ok = self._backfill_lines > 0
            entry.update({"ok": ok, "reason": None if ok else "backfill returned no lines", "unavailable": not ok})
        else:
            entry.update({"ok": None, "reason": "tail thread not running"})   # never started = not read yet, not dead
            return entry
        if as_of is not None:
            entry["asOfUtc"] = sig.iso_z(as_of)
            entry["ageS"] = int(max(0.0, now - as_of))
        return entry


    def _line_dict(self, line: LogLine) -> dict:
        return {"seq": line.seq, "ts": line.ts, "kind": line.kind, "text": line.text,
                "invocation": line.invocation, "cursor": line.cursor}

    def drain(self) -> IngestResult:
        """Empty the queue into the ledger, the ring and the detector state.  Pure ingest, no I/O but sqlite."""
        lines: list[LogLine] = []
        while True:
            try:
                lines.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return self._ingest(lines)

    def feed_lines(self, lines: Iterable[str | LogLine]) -> IngestResult:
        """(invented) The test/fixture seam: classify raw lines and ingest them exactly as drain() would."""
        prepared: list[LogLine] = []
        for item in lines:
            if isinstance(item, LogLine):
                prepared.append(item)
            elif isinstance(item, str):
                prepared.append(classify(item))
        return self._ingest(prepared)

    def _ingest(self, lines: Sequence[LogLine]) -> IngestResult:
        now = float(self._clock())
        self._last_drain_at = now
        if not lines:
            self._last_events = ()
            try:
                self._ledger.ingest(())              # no line: the ledger still recounts beats against the clock (spec §9)
            except Exception as exc:                 # noqa: BLE001 -- the tail must not die with the ledger
                self._error_count += 1
                logger.warning("PEPEPANE ledger recount failed: %s", exc)
            return _EMPTY_INGEST
        stamped: list[LogLine] = []
        for line in lines:
            self._seq += 1
            stamped.append(dataclasses.replace(line, seq=self._seq))
        self._ring.extend(stamped)
        try:
            result = self._ledger.ingest(stamped)
        except Exception as exc:                     # noqa: BLE001 -- the tail must not die with the ledger
            self._error_count += 1
            logger.warning("PEPEPANE ledger ingest failed for %d lines: %s", len(stamped), exc)
            result = _EMPTY_INGEST
        self._apply_bumps(result.events)
        self._last_events = tuple(result.events)
        return result

    def _apply_bumps(self, events: Sequence[str]) -> None:
        """Event-driven re-reads (spec §4.3): the API and the summariser lag the daemon by a known amount."""
        for event in events:
            if event == "submitted":
                self.bump("sessions", EVENT_BUMP_SESSIONS_S)
                self.bump("standing", EVENT_BUMP_STANDING_S)
                self.bump("workstat", EVENT_BUMP_WORKSTAT_S)
            elif event == "stored":
                self.bump("seatwork", EVENT_BUMP_SEATWORK_S)
                self.bump("workstat", EVENT_BUMP_WORKSTAT_S)
            elif event == "accepted":
                self.bump("workstat", EVENT_BUMP_WORKSTAT_S)
            elif event == "restart":
                self._restart_required = False       # the restart boundary (contract C.6) ends a skills-set's `restart required`

    @property
    def _state(self) -> LedgerState:
        return self._ledger.state

    def _tail_kind(self) -> str | None:
        """``tasks.window.source``: the persisted tail kind when known, else the configured host's transport."""
        kind = self._tail_state.kind
        if kind == KIND_LIST:
            return "fixture"
        if kind:
            return kind
        return {SYSTEMD_HOST: "journald", DOCKER_HOST: "docker-log", FIXTURE_HOST: "fixture"}[self._host]

    def _newest_ts(self) -> str | None:
        for line in reversed(self._ring):
            if line.ts:
                return line.ts
        return self._tail_state.last_ts_utc

    def _backfill_discarded(self) -> str | None:
        """``tasks.window.backfillDiscardedUtc`` (deviation 11): WP3's sticky stale-segment discard, remembered past the thread."""
        thread = self._thread
        if thread is not None and getattr(thread, "backfill_note", None) == STALE_BACKFILL_REASON:
            at = getattr(thread, "backfill_at", None)
            if isinstance(at, (int, float)) and not isinstance(at, bool):
                self._backfill_discarded_utc = sig.iso_z(float(at))
        return self._backfill_discarded_utc

    def _daemon_block(self, now: float) -> dict:
        st = self._state
        hb = st.last_heartbeat
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["daemon"]
        if hb is not None:
            fields = dict(hb.fields)
            idle = fields.get("work") == "idle"
            running = fields.get("running")
            hb_epoch = parse_ts(hb.ts)
            block.update({
                "state": fields.get("state"),
                "uptime": fields.get("uptime"),
                "work": "idle" if idle else "running",
                "running": 0 if idle else (int(running) if isinstance(running, str) and running.isdigit() else None),
                "lastHeartbeatUtc": hb.ts or None,
                "heartbeatAgeS": int(max(0.0, now - hb_epoch)) if hb_epoch is not None else None,
            })
        hint = st.paused_hint
        block.update({
            "submittedSinceStart": st.submitted_since_start,
            "idleBeats": st.idle_beats if hb is not None else None,
            "fleetOnline": st.fleet_online,
            "fleetEnrolled": st.fleet_enrolled,
            "pausedHint": None if not isinstance(hint, Mapping) else {
                "until": hint.get("until"), "failedRuns": hint.get("failedRuns"),
                "reason": redact_agent_sentence(hint.get("reason")) if hint.get("reason") else None,
                "seenUtc": hint.get("seenUtc"),
            },
            "invocationId": st.invocation,
            "lastAdmittedUtc": st.last_admitted_utc,
            "disconnects24h": st.disconnects_24h if hb is not None else None,
            "reconnects24h": st.reconnects_24h if hb is not None else None,
            "consecutiveDisconnectedBeats": st.consecutive_disconnected if hb is not None else None,
        })
        return block

    def _current_block(self, now: float) -> dict | None:
        current = self._state.current
        if not isinstance(current, Mapping):
            return None
        block = {key: current.get(key) for key in models.SEAT_BLOCK_KEYS["seat_current"]}
        started = sig.parse_iso(block.get("startedUtc"))
        block["elapsedS"] = int(max(0.0, now - started)) if started is not None else None
        if block.get("lastMessage"):
            block["lastMessage"] = redact_agent_sentence(block["lastMessage"])
        standing = self._payload("standing")
        running = standing.get("running") if isinstance(standing, Mapping) else None
        if isinstance(running, list) and running and isinstance(running[0], Mapping):
            first = running[0]
            block["planeSince"] = first.get("since")
            block["objective"] = block.get("objective") or first.get("objective")
            block["nodeKey"] = block.get("nodeKey") or first.get("nodeKey")
            if block.get("jobId") is None:
                block["jobId"] = first.get("jobId")
        return block


    def _tasks_block(self, now: float) -> dict:
        rows = self._ledger.rows(limit=LEDGER_ROWS_ON_SCREEN)
        for row in rows:
            if row.get("outcome") is None:
                row["outcome"] = "unknown"   # spec §7: no verdict attached (not stored, API unavailable, or --offline)
        counts = self._ledger.counts()
        return {
            "window": {
                "fromUtc": counts.get("sinceUtc"),
                "toUtc": self._newest_ts(),
                "source": self._tail_kind(),
                "rows": len(rows),
                "gapNote": self._thread.gap_note if self._thread is not None else self._backfill_gap_note,
                "ledgerSinceUtc": self._ledger.meta_get("ledger_since_utc"),
                "backfillDiscardedUtc": self._backfill_discarded(),
            },
            "rows": rows,
        }

    def _today_block(self, now: float, rows: Sequence[Mapping]) -> dict:
        day = sig.day_utc(now)
        try:
            today = dict(self._ledger.today(day))
        except Exception as exc:                     # noqa: BLE001 -- the pure rollup over the window is the fallback
            logger.debug("PEPEPANE ledger.today failed (%s); rolling up the window", exc)
            today = sig.rollup_today(rows, day_utc=day)
        today.setdefault("dayUtc", day)
        seatwork = self._payload("seatWork")
        plane_today = seatwork.get("planeRowsSubmittedToday") if isinstance(seatwork, Mapping) else None
        today["divergence"] = sig.divergence(local_stored_today=today.get("stored"), plane_rows_submitted_today=plane_today)
        return today


    def _read_unit_host(self, now: float) -> None:
        """One unit + host read, landed per field (deviation 6; spec §7, fill4 §5).

        A partial read (a ``reason`` key, or one of the two reads missing) lands what answered with ``ok: True``
        and the reason; the failed half is absent from the new payload, so it reads ``None`` -- never the previous
        read's value.  ``ok: False`` (a counted failure) only when neither read answered.
        """
        assert self._unit_reader is not None
        unit: dict | None
        host: dict | None
        try:
            unit = self._unit_reader.read_unit()
        except Exception as exc:                     # noqa: BLE001
            logger.debug("PEPEPANE unit read failed: %s", exc)
            unit = None
        try:
            host = self._unit_reader.read_host()
        except Exception as exc:                     # noqa: BLE001
            logger.debug("PEPEPANE host read failed: %s", exc)
            host = None
        ts = float(self._clock())
        if not isinstance(unit, Mapping) and not isinstance(host, Mapping):
            self._fail("unit", "unit and host reads failed", ts)
            return
        unit_map = dict(unit) if isinstance(unit, Mapping) else {}
        reason = unit_map.pop("reason", None)
        if not isinstance(unit, Mapping):
            reason = reason or "unit read failed"
        elif not isinstance(host, Mapping):
            reason = reason or "host read failed"
        self._land("unit", {"unit": unit_map, "host": dict(host) if isinstance(host, Mapping) else {}}, ts)
        if reason:
            self._reason["unit"] = redact(str(reason))   # per field: ok stays True, the reason names the half that failed

    def _unit_block(self) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["unit"]
        payload = self._payload("unit")
        unit = payload.get("unit") if isinstance(payload, Mapping) else None
        if not isinstance(unit, Mapping):
            return block
        for key in block:
            if key in unit:
                block[key] = unit[key]
        if block.get("gracefulStopPossible") is None:
            if self._host == DOCKER_HOST:
                block["gracefulStopPossible"] = sig.graceful_stop_possible(
                    kill_mode=None, stop_timeout_s=None,
                    docker_stop_timeout_s=unit.get("stopTimeoutS"), docker_init=bool(unit.get("init", False)),
                )
            else:
                block["gracefulStopPossible"] = sig.graceful_stop_possible(
                    kill_mode=unit.get("killMode"), stop_timeout_s=unit.get("stopTimeoutS"),
                )
        return block

    def _machine_block(self) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["machine"]
        payload = self._payload("unit")
        host = payload.get("host") if isinstance(payload, Mapping) else None
        if isinstance(host, Mapping):
            for key in ("load1", "memAvailMiB", "diskFreeGiB", "journal"):
                block[key] = host.get(key)
        runtime = self._runtime
        if runtime == "codex":
            sessions = self._payload("sessions")
            zstd = sessions.get("zstdReadable") if isinstance(sessions, Mapping) else None
            block["transcriptRetention"] = {"kind": "codex-rollouts", "plainDays": 7, "deleteDays": None, "zstdReadable": zstd}
        elif runtime == "claude":
            block["transcriptRetention"] = {"kind": "claude-transcripts", "deleteDays": 30}
        work = self._payload("workstat")
        if isinstance(work, Mapping):
            stat = work.get("workStat") if isinstance(work.get("workStat"), Mapping) else {}
            outbox = work.get("outbox") if isinstance(work.get("outbox"), Mapping) else {}
            orphans = work.get("orphans") if isinstance(work.get("orphans"), Mapping) else {}
            block["workDirs"] = stat.get("count")
            block["workBytes"] = stat.get("bytes")
            block["abnormalLeaseDirs"] = stat.get("abnormal")
            block["outboxFiles"] = outbox.get("files")
            candidates = orphans.get("candidates")
            block["orphans"] = [dict(c) for c in candidates if isinstance(c, Mapping)] if isinstance(candidates, list) else []
        return block


    def _config_changed(self, unit_block: Mapping) -> bool | None:
        projection = self._payload("seat")
        mtime = projection.get("configMtimeUtc") if isinstance(projection, Mapping) else None
        return sig.config_changed_since_start(mtime_utc=mtime, anchor_utc=unit_block.get("sinceUtc"))

    async def _broker_read(self, verb: str, args: Mapping | None = None) -> Any:
        """One read verb; the socket call blocks (20 s client timeout), so it runs in a worker thread."""
        return await asyncio.to_thread(self._broker.read, verb, dict(args) if args else None)

    @staticmethod
    def _broker_reason(exc: BaseException) -> str:
        code = getattr(exc, "code", None)
        detail = getattr(exc, "detail", None)
        if code == "projection_refused":
            kind = detail.get("canary") if isinstance(detail, Mapping) else None
            return f"config projection unavailable — broker refused payload (canary{': ' + str(kind) if kind else ''})"
        if code == "unreadable":
            what = detail.get("what") if isinstance(detail, Mapping) else None
            return f"{what or 'read'} unreadable"
        if code:
            return f"broker: {code}"
        return f"{type(exc).__name__}: {redact(str(exc))[:120]}"

    async def _read_into(self, source: str, verb: str, args: Mapping | None, shape: Callable[[Any], Any]) -> Any:
        """Read *verb* and land its shaped payload on *source*; a failure lands nothing and counts once."""
        try:
            data = await self._broker_read(verb, args)
            payload = shape(data)
        except Exception as exc:                     # noqa: BLE001 -- per-source degradation
            self._fail(source, self._broker_reason(exc), float(self._clock()))
            logger.debug("PEPEPANE broker %s failed: %s", verb, exc)
            return None
        self._land(source, payload, float(self._clock()))
        return payload

    async def _tier_broker_status(self) -> None:
        if self._whoami_key is None:
            try:
                data = await self._broker_read("whoami")
                key = data.get("deviceKey") if isinstance(data, Mapping) else None
                if not key and isinstance(data, Mapping) and isinstance(data.get("lines"), list):
                    key = parse_whoami(data["lines"])
                self._whoami_key = key if isinstance(key, str) and key else None
            except Exception as exc:                 # noqa: BLE001 -- whoami is a convenience; the projection carries the key too
                logger.debug("PEPEPANE whoami failed: %s", exc)

        def shape_seat(data: Any) -> dict:
            return dict(data) if isinstance(data, Mapping) else {}

        def shape_lines(parser: Callable[[Sequence[str]], Any]) -> Callable[[Any], dict]:
            def shape(data: Any) -> dict:
                lines = data.get("lines") if isinstance(data, Mapping) else None
                lines = [str(line) for line in lines] if isinstance(lines, list) else []
                return {"parsed": parser(lines), "rc": data.get("rc") if isinstance(data, Mapping) else None}
            return shape

        seat_payload = await self._read_into("seat", "seat", None, shape_seat)
        await self._read_into("status", "status", None, shape_lines(parse_imd_status))
        await self._read_into("skills", "skills", None, shape_lines(parse_imd_skills))
        if seat_payload is not None and not seat_payload.get("tools"):
            try:
                tools_data = await self._broker_read("tools")
                lines = tools_data.get("lines") if isinstance(tools_data, Mapping) else None
                seat_payload["toolsListing"] = parse_imd_tools([str(l) for l in lines]) if isinstance(lines, list) else []
            except Exception as exc:                 # noqa: BLE001 -- tools is a detail of the seat source
                logger.debug("PEPEPANE tools failed: %s", exc)
        await self._read_into("hints", "hints-stat", None, lambda d: dict(d) if isinstance(d, Mapping) else {})
        await self._read_into("auth", "auth-mtime", None, lambda d: dict(d) if isinstance(d, Mapping) else {})

    async def _tier_workstat(self) -> None:
        now = float(self._clock())
        try:
            reachable = await asyncio.to_thread(self._broker.reachable)
        except Exception as exc:                     # noqa: BLE001
            logger.debug("PEPEPANE ping failed: %s", exc)
            reachable = False
        if not reachable:
            self._fail("broker", "broker unreachable", now)
            self._fail("workstat", "broker unreachable", now)
            return
        control: dict[str, Any] = {"reachable": True, "ping": None, "gate": None, "audit": []}
        problems: list[str] = []
        for verb, args, key in (("ping", None, "ping"), ("gate", {"offline": self._offline}, "gate"), ("audit-tail", {"n": 5}, "audit")):
            try:
                data = await self._broker_read(verb, args)
                control[key] = data.get("lines") if key == "audit" and isinstance(data, Mapping) else data
            except Exception as exc:                 # noqa: BLE001
                problems.append(f"{verb}: {self._broker_reason(exc)}")
        self._land("broker", control, float(self._clock()))
        if problems:
            self._fail("broker", "; ".join(problems), float(self._clock()))

        work: dict[str, Any] = {"workStat": None, "outbox": None, "orphans": None}
        problems = []
        for verb, key in (("work-stat", "workStat"), ("outbox", "outbox"), ("orphans", "orphans")):
            try:
                work[key] = await self._broker_read(verb)
            except Exception as exc:                 # noqa: BLE001
                problems.append(f"{verb}: {self._broker_reason(exc)}")
        stat = work.get("workStat")
        newest = stat.get("newest") if isinstance(stat, Mapping) else None
        if isinstance(newest, list):                 # work_dir_abnormal / node_id / job_id on the matching rows (WP2 deviation 12, spec §5.2)
            try:
                self._ledger.attach_work_dirs([dict(e) for e in newest if isinstance(e, Mapping)])
            except Exception as exc:                 # noqa: BLE001 -- a detail of the ledger; the read itself landed
                logger.debug("PEPEPANE attach_work_dirs failed: %s", exc)
        self._land("workstat", work, float(self._clock()))
        if problems:
            self._fail("workstat", "; ".join(problems), float(self._clock()))

    async def _tier_sessions(self) -> None:
        since = self._ledger.meta_get("sessions_watermark_mtime")
        since_f = float(since) if isinstance(since, (int, float)) and not isinstance(since, bool) else 0.0
        # a guess until `_seat_block` reads the runtime from `imd status` (the first cycle and every --once run); the Mac broker
        # answers with Claude transcripts whatever it is asked, so WP2's attach_sessions takes each stored session's own
        # `runtime` for turnsDefinition and the tier re-derivation -- this argument is only the fallback (spec §10)
        runtime = self._runtime or "codex"
        data = await self._broker_read("sessions", {"since": since_f, "runtime": runtime})
        if not isinstance(data, Mapping):
            raise ValueError("sessions: not an object")
        sessions = [s for s in (data.get("sessions") or []) if isinstance(s, Mapping)]
        if sessions:
            self._ledger.attach_sessions([dict(s) for s in sessions], runtime=runtime)
        if self._runtime is not None:                # the retention sweep is a claude rule: never run it on the guess
            self._ledger.mark_expired_transcripts(runtime=self._runtime, now_utc=sig.iso_z(float(self._clock())))   # WP2 deviation 12
        watermark = data.get("watermarkMtime")
        if isinstance(watermark, (int, float)) and not isinstance(watermark, bool) and float(watermark) > since_f:
            self._ledger.meta_set("sessions_watermark_mtime", float(watermark))
        newest = max(sessions, key=lambda s: float(s.get("mtime") or 0.0)) if sessions else None
        quotas = [s["quota"] for s in sessions if isinstance(s.get("quota"), Mapping) and s["quota"].get("sampledAtUtc")]
        newest_quota = max(quotas, key=lambda q: sig.parse_iso(q.get("sampledAtUtc")) or 0.0) if quotas else None
        previous = self._payload("sessions")
        if newest_quota is None and isinstance(previous, Mapping):
            newest_quota = previous.get("newestQuota")      # the quota is refreshed only while a task runs (spec §10)
        if newest is None and isinstance(previous, Mapping):
            newest = previous.get("newestSession")
        # the summariser is incremental, so an oversize file is reported once: keep the running total (spec §8 COST footer)
        skipped = data.get("skipped") if isinstance(data.get("skipped"), Mapping) else {}
        fresh = skipped.get("oversize")
        total = self._ledger.meta_get("sessions_skipped_oversize")
        total = total if isinstance(total, int) and not isinstance(total, bool) else None
        if isinstance(fresh, int) and not isinstance(fresh, bool):
            total = (total or 0) + max(0, fresh)
            self._ledger.meta_set("sessions_skipped_oversize", total)
        self._land("sessions", {
            "skipped": {"oversize": total},
            "watermarkMtime": watermark,
            "zstdReadable": data.get("zstdReadable"),
            "reason": data.get("reason"),
            "newestSession": dict(newest) if isinstance(newest, Mapping) else None,
            "newestQuota": dict(newest_quota) if isinstance(newest_quota, Mapping) else None,
        }, float(self._clock()))
        self._rollup_series()

    def _rollup_series(self) -> None:
        """Upsert the COST series window into WP2's ``days`` table (deviation 12; spec §5.6, §8 COST ``output tokens/day · 14 d``).

        Only days the ledger covers are rolled up: a day before the first row is unknown, never a 0.
        """
        try:
            now = float(self._clock())
            since = str(self._ledger.counts().get("sinceUtc") or "")[:10]
            if not since:
                return
            for back in range(SERIES_DAYS):
                day = sig.day_utc(now - back * 86400)
                if day >= since:
                    self._ledger.rollup_day(day, now_utc=sig.iso_z(now))
        except Exception as exc:                     # noqa: BLE001 -- the series is a detail; the tier's own read already landed
            self._error_count += 1
            logger.warning("PEPEPANE days rollup failed: %s", exc)

    @staticmethod
    def _first_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(ch if ch.isdigit() else " " for ch in value).split()
            return int(digits[0]) if digits else None
        return None

    @staticmethod
    def _as_list(value: object) -> list:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return []

    def _seat_block(self) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["seat"]
        status = self._payload("status")
        parsed = status.get("parsed") if isinstance(status, Mapping) and isinstance(status.get("parsed"), Mapping) else {}
        proj = self._payload("seat") if isinstance(self._payload("seat"), Mapping) else {}
        skills = self._payload("skills")
        skills_parsed = skills.get("parsed") if isinstance(skills, Mapping) and isinstance(skills.get("parsed"), Mapping) else {}
        standing = self._payload("standing") if isinstance(self._payload("standing"), Mapping) else {}
        hints = self._payload("hints")
        runtime_id, runtime_version = None, None
        for row in self._as_list(parsed.get("runtimes")):
            if row.startswith("→"):
                parts = row.lstrip("→").strip().split(None, 1)
                runtime_id = parts[0] if parts else None
                runtime_version = parts[1] if len(parts) > 1 else None
        if isinstance(parsed.get("runtime"), Mapping):
            runtime_id = parsed["runtime"].get("id") or runtime_id
            runtime_version = parsed["runtime"].get("version") or runtime_version
        if self._runtime is None and runtime_id in ("codex", "claude"):
            self._runtime = runtime_id
        block.update({
            "tokenId": self._first_int(parsed.get("tokenId")) or self._first_int(proj.get("tokenId")) or self._seat,   # WP6 parse_imd_status key
            "agentId": standing.get("agentId") if standing.get("agentId") is not None else self._agent,
            "deviceKeyPublic": models.truncate_id(self._whoami_key or proj.get("deviceKey"), sig.ID_TRUNCATE_CHARS),
            "wallet": models.truncate_id(proj.get("wallet"), sig.ID_TRUNCATE_CHARS),
            "server": proj.get("server") or parsed.get("server") or None,
            "eligibility": parsed.get("eligibility") or None,
            "capacity": self._first_int(parsed.get("capacity")) or self._first_int(proj.get("maxConcurrency")),
            "offers": self._as_list(parsed.get("offers")),
            "daemonVersion": self._state.daemon_version,
            "runtime": {"id": runtime_id or self._runtime, "version": runtime_version},
            "releaseAvailable": self._state.release_available,
            "buildMismatch": bool(self._state.build_mismatch) if self._state.daemon_version is not None else None,
            "skills": {
                "offered": self._first_int(skills_parsed.get("offered")),
                "on": self._first_int(skills_parsed.get("on")),
                "optOut": list(proj.get("skillsOptOut") or []),
                "needsNetwork": self._first_int(skills_parsed.get("needsNetwork")),
                "rows": [dict(r) for r in (skills_parsed.get("rows") or []) if isinstance(r, Mapping)],
            },
            "tools": list(proj.get("tools") or proj.get("toolsListing") or []),
            "inference": dict(proj["inference"]) if isinstance(proj.get("inference"), Mapping) else None,
            "premiumAdvertised": dict(standing["premiumAdvertised"]) if isinstance(standing.get("premiumAdvertised"), Mapping) else None,
            "hints": dict(hints) if isinstance(hints, Mapping) and hints else None,
        })
        return block

    def _auth_block(self, now: float, rows: Sequence[Mapping]) -> dict:
        sessions = self._payload("sessions") if isinstance(self._payload("sessions"), Mapping) else {}
        newest = sessions.get("newestSession")
        auth_payload = self._payload("auth") if isinstance(self._payload("auth"), Mapping) else {}
        state = seat_auth.auth_state(
            paused_hint=self._state.paused_hint,
            newest_transcript=newest if self._runtime == "claude" else None,
            newest_rollout=newest if self._runtime == "codex" else None,
            recent_rows=list(rows[:10]),
            credential_mtime_utc=auth_payload.get("mtimeUtc"),
            now=now,
        )
        return {
            "degraded": state.get("degraded"),
            "reasons": [redact(r) for r in (state.get("reasons") or [])],
            "sinceUtc": state.get("sinceUtc"),
            "credentialFileMtimeUtc": auth_payload.get("mtimeUtc"),
        }

    def _cost_block(self, now: float) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["cost"]
        sessions = self._payload("sessions")
        if not isinstance(sessions, Mapping):
            return block
        rows = self._ledger.rows(limit=10000)
        # doctor/manual/unknown runs never become rows: WP2 keeps them unattached, summarise counts them as excluded (spec §10)
        excluded = self._ledger.unattached_sessions(since_utc=sig.iso_z(now - COST_WINDOW_DAYS * 86400))
        summary = seat_cost.summarise(rows, window_days=COST_WINDOW_DAYS, now=now, sessions=excluded)
        for key in ("windowDays", "tasks", "excluded", "turns", "tokens", "buckets", "sideModel"):
            if key in summary:
                block[key] = summary[key]
        block["series"] = seat_cost.series_from_days(self._ledger.days(SERIES_DAYS), n=SERIES_DAYS)
        depth = dict(summary.get("depth") or {})
        depth.setdefault("ledgerFromUtc", self._ledger.counts().get("sinceUtc"))
        depth.setdefault("sessionsFromUtc", self._ledger.meta_get("ledger_since_utc"))
        depth["expiredRows"] = sum(1 for r in rows if isinstance(r, Mapping) and r.get("tokensReason") == "transcript expired")
        depth["skipped"] = dict(sessions.get("skipped") or {"oversize": None})
        block["depth"] = {k: depth.get(k) for k in ("ledgerFromUtc", "sessionsFromUtc", "expiredRows", "skipped")}
        return block

    def _quota_block(self) -> dict:
        sessions = self._payload("sessions") if isinstance(self._payload("sessions"), Mapping) else {}
        return seat_cost.quota_block(sessions.get("newestQuota"), runtime=self._runtime or "codex")

    def _control_block(self) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["control"]
        control = self._payload("broker")
        if "broker" in self._attempted:
            block["brokerReachable"] = bool(control.get("reachable")) if isinstance(control, Mapping) else False
        if not isinstance(control, Mapping):
            return block
        gate = control.get("gate")
        if isinstance(gate, Mapping):
            plane = gate.get("plane") if isinstance(gate.get("plane"), Mapping) else {}
            block["gate"] = {
                "idleBeats": gate.get("idle_beats"), "idleBeatsRequired": gate.get("idle_beats_required"),
                "planeRunning": plane.get("running"), "planeAsOfUtc": plane.get("as_of"), "planeMode": plane.get("mode"),
                "lastLifecycleLine": gate.get("last_lifecycle_line"), "lifecycleOpen": gate.get("lifecycle_open"),
                "outboxFiles": gate.get("outbox_files"), "unitActive": gate.get("unit_active"),
                "safe": gate.get("safe"), "reason": gate.get("reason"),
            }
        ping = control.get("ping") if isinstance(control.get("ping"), Mapping) else {}
        flight = ping.get("in_flight")
        if isinstance(flight, Mapping):
            block["inFlight"] = {"verb": flight.get("verb"), "planId": flight.get("plan_id"), "sinceUtc": flight.get("since")}
        drain = ping.get("drain")
        if isinstance(drain, Mapping):
            block["drain"] = {k: drain.get(k) for k in models.SEAT_BLOCK_KEYS["seat_control_drain"]}
        elif ping.get("drain_armed") is True:
            block["drain"] = {k: None for k in models.SEAT_BLOCK_KEYS["seat_control_drain"]}
        audit = control.get("audit")
        if isinstance(audit, list):
            block["lastAudit"] = [
                {"ts": a.get("ts"), "seq": a.get("seq"), "verb": a.get("verb"), "phase": a.get("phase"), "planId": a.get("plan_id"),
                 "outcome": a.get("outcome"), "verified": a.get("verified"), "connected": a.get("connected")}
                for a in audit if isinstance(a, Mapping)
            ]
        return block

    async def _tier_standing(self) -> None:
        assert self._api is not None and self._seat is not None
        result = await self._api.standing(self._seat)
        if not result.ok:
            raise _TierFailure(result.reason or "standing failed")
        block = seat_api.normalise_standing(result.data if isinstance(result.data, Mapping) else {})
        for failure in block.get("recentFailures") or []:
            job = failure.get("jobId") if isinstance(failure, Mapping) else None
            reason = failure.get("reason") if isinstance(failure, Mapping) else None
            if job and reason:
                try:
                    self._ledger.attach_reason(str(job), reason=str(reason), failure_class=None, source="standing", at=failure.get("at"))
                except Exception as exc:             # noqa: BLE001
                    logger.debug("PEPEPANE attach_reason(standing) failed: %s", exc)
        self._land("standing", block, float(self._clock()))

    async def _tier_seatwork(self) -> None:
        assert self._api is not None and self._seat is not None
        result = await self._api.seat_work(self._seat)
        if not result.ok:
            raise _TierFailure(result.reason or "seat work failed")
        body = result.data if isinstance(result.data, Mapping) else {}
        counters = {key: body.get(key) for key in ("attempts", "accepted", "rejected", "failed", "pending")}
        consistent = sig.counters_consistent(counters)
        counters["countersInconsistent"] = None if consistent is None else (not consistent)
        rows = [seat_api.normalise_work_row(r) for r in (body.get("work") or []) if isinstance(r, Mapping)]
        now = float(self._clock())
        self._ledger.attach_work(rows, as_of_utc=sig.iso_z(now))
        today = sig.day_utc(now)
        submitted = [sig.parse_iso(r.get("submittedAt")) for r in rows]
        submitted = [s for s in submitted if s is not None]
        plane_today = sum(1 for s in submitted if sig.day_utc(s) == today)
        complete = len(rows) < seat_api.SEAT_WORK_ROWS or (bool(submitted) and sig.day_utc(min(submitted)) < today)
        self._land("seatWork", {"counters": counters, "planeRowsSubmittedToday": plane_today if complete else None,
                                "rows": len(rows), "daemonVersion": body.get("daemonVersion")}, now)
        open_rows = [r for r in self._ledger.rows(limit=LEDGER_ROWS_ON_SCREEN)
                     if r.get("storedUtc") and r.get("outcome") in (None, "unknown", "pending")]
        self._seatwork_settled = not open_rows
        self._rollup_series()                        # verdicts moved: the days table's accepted/failed counts follow (Task 7.9)

    async def _tier_reasons(self) -> None:
        assert self._api is not None and self._seat is not None
        now = float(self._clock())
        cutoff = sig.iso_z(now - 24 * 3600)
        rows = self._ledger.failed_rows_needing_reason(older_than_utc=cutoff, limit=seat_api.MAX_REASONS_PER_CYCLE)
        fetched: list[str] = []
        problems: list[str] = []
        for row in rows[: seat_api.MAX_REASONS_PER_CYCLE]:
            job = row.get("jobId")
            if not isinstance(job, str) or not job:
                continue
            result = await self._api.job_submissions(job)
            fetched.append(job)
            if not result.ok:
                problems.append(f"{job[:8]}: {result.reason}")
                continue
            data = result.data if isinstance(result.data, Mapping) else {}
            mine = [s for s in (data.get("submissions") or []) if isinstance(s, Mapping) and s.get("seatTokenId") == self._seat]
            match = next((s for s in mine if s.get("hash12") == row.get("hash12")), None)
            if match is None:
                failed = [s for s in mine if s.get("outcome") == "failed"]
                match = max(failed, key=lambda s: sig.parse_iso(s.get("createdAt")) or 0.0) if failed else None
            if match is None:
                continue
            reason = seat_api.reason_word(match.get("failureReason")) or "other"
            self._ledger.attach_reason(job, reason=reason, failure_class=match.get("failureClass"), source="submissions",
                                       at=match.get("createdAt"))
        if problems and len(problems) == len(fetched):
            raise _TierFailure("; ".join(problems))
        self._land("reasons", {"fetched": fetched, "problems": problems}, float(self._clock()))

    async def _tier_plane(self) -> None:
        assert self._api is not None
        services = await self._api.services()
        health = await self._api.health()
        if not services.ok and not health.ok:
            raise _TierFailure(f"services: {services.reason}; health: {health.reason}")
        # WP5's normaliser (hoisted, never re-declared): it reads both `/services` shapes, dict-keyed and {"services": [{"name": …}]}
        block = seat_api.normalise_plane(services.data if services.ok else None, health.data if health.ok else None)
        self._land("plane", block, float(self._clock()))

    def _standing_block(self) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["standing"]
        seatwork = self._payload("seatWork")
        counters = seatwork.get("counters") if isinstance(seatwork, Mapping) and isinstance(seatwork.get("counters"), Mapping) else {}
        for key in ("attempts", "accepted", "rejected", "failed", "pending", "countersInconsistent"):
            block[key] = counters.get(key)
        standing = self._payload("standing")
        if isinstance(standing, Mapping):
            for key in ("working", "running", "consecutiveFailures", "pausedUntil", "breaker", "recentFailures",
                        "presenceConnected", "heartbeatAgeMs", "asOfUtc"):
                if key in standing:
                    block[key] = standing[key]
        return block

    def _queue_block(self) -> dict | None:
        standing = self._payload("standing")
        queue_block = standing.get("queue") if isinstance(standing, Mapping) else None
        if not isinstance(queue_block, Mapping):
            return None
        return {key: queue_block.get(key) for key in models.SEAT_BLOCK_KEYS["seat_queue"]}

    def _plane_block(self, now: float) -> dict:
        block = models.empty_document(producer=self._producer, started_at_utc="", host=self._host_block())["plane"]
        entry = self._last_good.get("plane")
        if entry is None:
            return block
        payload, ts = entry
        if isinstance(payload, Mapping):
            block.update({k: payload.get(k) for k in ("version", "verifierUp", "verifierLastSeenUtc", "awaitingVerdict", "connectedDaemons")})
        block["asOfUtc"] = sig.iso_z(ts)
        return block

    def _fleet_counts(self, now: float) -> dict:
        """``daemon.fleetOnline/fleetEnrolled``: the heartbeat clause while it is at most :data:`FLEET_CLAUSE_STALE_S` old,
        else ``/health`` while the plane source is ok, else ``None`` -- never an old clause as if current (spec §6)."""
        st = self._state
        seen = parse_ts(st.fleet_seen_utc) if isinstance(st.fleet_seen_utc, str) and st.fleet_seen_utc else None
        if seen is not None and now - seen <= FLEET_CLAUSE_STALE_S:
            return {"fleetOnline": st.fleet_online, "fleetEnrolled": st.fleet_enrolled}
        plane = self._payload("plane")
        if not self._offline and isinstance(plane, Mapping) and self._failures.get("plane", 0) == 0:
            return {"fleetOnline": plane.get("connectedDaemons"), "fleetEnrolled": plane.get("activeEnrollments")}
        return {"fleetOnline": None, "fleetEnrolled": None}

    @classmethod
    def _no_currency(cls, value: Any) -> Any:
        """Remove every ``$`` from every string leaf (spec §10: tokens, never dollars -- no exception, no flag)."""
        if isinstance(value, str):
            return value.replace("$", "")
        if isinstance(value, dict):
            return {cls._no_currency(k) if isinstance(k, str) else k: cls._no_currency(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._no_currency(v) for v in value]
        if isinstance(value, tuple):
            return [cls._no_currency(v) for v in value]
        return value









































    async def backfill(self, *, api: bool = False) -> dict:
        """Consume a bounded local source synchronously; never start a tail thread.

        TailThread.run_once supplies the existing classifier, Docker stale-segment
        checks and journal cursor fallback. API history retains local ledger rows.
        """
        summary: dict[str, Any] = {"lines": 0, "apiRows": 0, "apiError": None}
        if self._tail_factory is not None and self._thread is None and not self._backfill_done:
            deadline = _monotonic() + BACKFILL_MAX_S
            opened: list[_BoundedSource] = []

            def factory(state: TailState) -> LineSource:
                source = _BoundedSource(self._tail_factory(state), deadline)
                opened.append(source)
                return source

            consumer = TailThread(factory, self._queue, state=self._tail_state,
                                  state_path=self._maxpane_dir / TAIL_FILE, now=self._clock)
            try:
                cursor = self._tail_state.cursor
                consumer.run_once()
                if (cursor is not None and self._tail_state.cursor is None
                        and consumer.gap_note and _monotonic() < deadline):
                    consumer.run_once()
            except Exception as exc:
                self._error_count += 1
                logger.warning("PEPEPANE synchronous backfill failed: %s", redact(str(exc)))
            finally:
                for source in opened:
                    source.close()
                self._backfill_gap_note = consumer.gap_note
                if consumer.backfill_note == STALE_BACKFILL_REASON and consumer.backfill_at is not None:
                    self._backfill_discarded_utc = sig.iso_z(consumer.backfill_at)
                result = self.drain()
                self._backfill_lines = result.lines
                summary["lines"] = result.lines
                consumer.persist(force=True)
                self._backfill_done = True
        if api:
            if self._offline or self._api is None:
                summary["apiError"] = "offline"
            elif self._seat is None:
                summary["apiError"] = "no seat configured"
            else:
                try:
                    result = await self._api.backfill(self._seat)
                except Exception as exc:             # noqa: BLE001
                    result = None
                    summary["apiError"] = f"{type(exc).__name__}"
                if result is not None and result.ok:
                    body = result.data if isinstance(result.data, Mapping) else {}
                    rows = [seat_api.normalise_work_row(r) for r in (body.get("work") or []) if isinstance(r, Mapping)]
                    summary["apiRows"] = int(self._ledger.seed_api_rows(rows, seat=self._seat))
                    self._ledger.meta_set("api_backfill_done_utc", sig.iso_z(float(self._clock())))
                elif result is not None:
                    summary["apiError"] = result.reason or "api backfill failed"
        return summary


__all__ = [
    "BACKFILL_MAX_S", "BACKFILL_QUIET_S", "CONTAINER_TRUST_SOURCES", "COST_WINDOW_DAYS", "DOCKER_BREAKER_S", "DOCKER_HOST",
    "DOCKER_TIMEOUT_S", "EVENT_BUMP_SEATWORK_S", "EVENT_BUMP_SESSIONS_S", "EVENT_BUMP_STANDING_S", "EVENT_BUMP_WORKSTAT_S",
    "FLEET_CLAUSE_STALE_S", "FIXTURE_HOST", "HOST_KINDS", "LEDGER_ROWS_ON_SCREEN", "LOG_RING", "OFFLINE_REMOVES", "SERIES_DAYS", "SYSTEMD_HOST",
    "SeatManager", "TIERS", "TIER_BROKER_STATUS_S", "TIER_PLANE_S", "TIER_REASONS_S", "TIER_RETRY_S", "TIER_SEATWORK_S",
    "TIER_SEATWORK_SETTLED_S", "TIER_SESSIONS_S", "TIER_SOURCES", "TIER_STANDING_PLAN_OPEN_S", "TIER_STANDING_S", "TIER_TTL_S",
    "TIER_UNIT_S", "TIER_WORKSTAT_S",
]


# ---------------------------------------------------------------------------
# the fixture host (spec §4.4): --host fixture --fixture tests/fixtures/seat/<case>/
# ---------------------------------------------------------------------------


def load_case(case_dir: str | Path) -> dict:
    """Read ``case.json``; a case may ``inherit`` a sibling's ``broker/``, ``api/`` and ``unit/`` dirs (deviation 9)."""
    case_path = Path(case_dir)
    case = json.loads((case_path / "case.json").read_text(encoding="utf-8"))
    inherit = case.get("inherit")
    base = case_path.parent / str(inherit) if isinstance(inherit, str) and inherit else None

    def pick(sub: str) -> Path | None:
        own = case_path / sub
        if own.is_dir():
            return own
        if base is not None and (base / sub).is_dir():
            return base / sub
        return None

    api_mode = str(case.get("api", "fixtures"))
    host = str(case.get("host", SYSTEMD_HOST))
    if host not in HOST_KINDS:
        raise ValueError(f"case.json host must be one of {HOST_KINDS}, not {host!r}")
    return {
        "dir": case_path,
        "seat": int(case.get("seat", 7)),
        "agent": int(case["agent"]) if isinstance(case.get("agent"), int) and not isinstance(case.get("agent"), bool) else None,
        "runtime": str(case.get("runtime", "codex")),
        "host": host,
        "time_scale": case.get("time_scale"),
        "now_utc": case.get("nowUtc"),
        "tail_exit_code": int(case.get("tail_exit_code", 0)),
        "api_mode": api_mode,
        "log": case_path / "log.txt",
        "broker_dir": pick("broker"),
        "api_dir": None if api_mode == "down" else pick("api"),
        "unit_dir": pick("unit"),
        "hostname": str(case.get("hostname", "fixture")),
    }


def fixture_api_handler(api_dir: Path | None, *, seat: int) -> Callable[[httpx.Request], httpx.Response]:
    """An ``httpx.MockTransport`` handler serving the case's api bodies; ``api_dir=None`` answers 500 to everything (api down)."""
    headers = {"content-type": "application/json"}

    def handler(request: httpx.Request) -> httpx.Response:
        if api_dir is None:
            return httpx.Response(500, json={"error": "internal_error", "detail": "fixture case: api down"})
        path = request.url.path
        name: str | None = None
        if path == f"/seats/{seat}/standing":
            name = "standing.json"
        elif path == f"/seats/{seat}":
            name = "seat_work.json"
        elif path.startswith("/jobs/") and path.endswith("/submissions"):
            name = f"job_{path.split('/')[2][:8]}_submissions.json"
        elif path == "/health":
            name = "health.json"
        elif path == "/services":
            name = "services.json"
        if name is None or not (api_dir / name).is_file():
            return httpx.Response(404, json={"error": "not_found"})
        return httpx.Response(200, content=(api_dir / name).read_bytes(), headers=headers)

    return handler


def build_fixture_manager(case_dir: str | Path, *, now: Clock | None = None, offline: bool = False, seat: int | None = None,
                          agent: int | None = None, poll_interval: int = 5) -> SeatManager:
    """The dev-mode manager: a replayed log, FakeBroker payloads, fixture api bodies, a fixture unit reader; touches no host.

    The clock is *now*, else the case's fixed ``nowUtc`` (deterministic screenshots), else the wall clock.
    The ledger and tail state live in a fresh temporary directory, never in ``~/.maxpane``.  ``offline``, ``seat``,
    ``agent`` and ``poll_interval`` are pepepane's own flags (WP8 deviation 10): ``--offline`` builds no api client at
    all, ``seat``/``agent`` override the case's values.
    """
    import tempfile

    case = load_case(case_dir)
    if now is not None:
        clock: Clock = now
    else:
        fixed = sig.parse_iso(case["now_utc"])
        clock = (lambda: fixed) if fixed is not None else time.time      # type: ignore[assignment]
    lines = case["log"].read_text(encoding="utf-8").splitlines() if case["log"].is_file() else []
    exit_code = case["tail_exit_code"]
    seat_id = seat if seat is not None else case["seat"]
    served = {"first": True}

    def factory(state: TailState) -> LineSource:
        if served["first"]:
            served["first"] = False
            source = ListLineSource(lines, exit_code=exit_code, time_scale=case["time_scale"])
            # a clean replay holds the attach open (never `tail: exited rc=0` for good); tail_dead/ keeps its dying source
            return _ReplaySource(source) if exit_code == 0 else source
        if exit_code:
            return ListLineSource([], exit_code=exit_code)       # a follower that keeps dying (tail_dead/)
        return _QuietSource()

    if case["broker_dir"] is None:
        broker: BrokerProtocol = FakeBroker(reachable=False)
    else:
        responses = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(case["broker_dir"].glob("*.json"))}
        broker = FakeBroker(responses=responses)
    api = None if offline else seat_api.SeatApiClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(fixture_api_handler(case["api_dir"], seat=seat_id))),
        now=clock,
    )
    unit_reader = FixtureUnitReader(case["unit_dir"].parent) if case["unit_dir"] is not None else None
    scratch = Path(tempfile.mkdtemp(prefix="pepepane-fixture-"))
    manager = SeatManager(
        tail=factory, broker=broker, api=api, unit_reader=unit_reader, now=clock,
        host=case["host"], unit="imd-worker.service", container="imd-worker" if case["host"] == DOCKER_HOST else None,
        runtime=case["runtime"], seat=seat_id, agent=agent if agent is not None else case["agent"], offline=offline,
        poll_interval=poll_interval, maxpane_dir=scratch, hostname=case["hostname"],
    )
    manager._tail_state.kind = KIND_LIST        # tasks.window.source / footers read `fixture`, not the host's transport
    return manager


__all__ += ["build_fixture_manager", "fixture_api_handler", "load_case"]
