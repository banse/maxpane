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
        doc = redact_tree(doc)
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
        new_lines = [self._line_dict(line) for line in self._ring if line.seq > self._emitted_seq]
        flat = models.fold_status_document(doc, now=float(self._clock()), log_lines=new_lines, log_seq=self._emitted_seq)
        self._emitted_seq = int(flat.get("seat_log_seq") or self._emitted_seq)
        return flat

    def _drain_step(self, now: float) -> None:
        self.drain()


    def _inline_step(self, now: float) -> None:
        """Task 7.8 fills this in (systemd/fixture unit + host reads)."""

    def _spawn_tiers(self, now: float) -> None:
        """Tasks 7.8–7.10 fill this in (docker unit, broker tiers, api tiers)."""

    # ------------------------------------------------------------------ tier bookkeeping

    def _ttl(self, tier: str) -> float:
        if tier == "standing" and self.plan_open:
            return float(TIER_STANDING_PLAN_OPEN_S)
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
            except Exception as exc:                 # noqa: BLE001 -- nobody awaits this task
                self._error_count += 1
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
        doc["daemon"] = self._daemon_block(now)
        doc["current"] = self._current_block(now)
        doc["tasks"] = self._tasks_block(now)
        doc["today"] = self._today_block(now, doc["tasks"]["rows"])
        st = self._state
        doc["seat"].update({
            "daemonVersion": st.daemon_version,
            "releaseAvailable": st.release_available,
            "buildMismatch": bool(st.build_mismatch) if st.daemon_version is not None else None,
        })
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
                "gapNote": self._thread.gap_note if self._thread is not None else None,
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
        today["divergence"] = None                   # Task 7.10 fills it from the seatwork tier
        return today














__all__ = [
    "BACKFILL_MAX_S", "BACKFILL_QUIET_S", "CONTAINER_TRUST_SOURCES", "COST_WINDOW_DAYS", "DOCKER_BREAKER_S", "DOCKER_HOST",
    "DOCKER_TIMEOUT_S", "EVENT_BUMP_SEATWORK_S", "EVENT_BUMP_SESSIONS_S", "EVENT_BUMP_STANDING_S", "EVENT_BUMP_WORKSTAT_S",
    "FIXTURE_HOST", "HOST_KINDS", "LEDGER_ROWS_ON_SCREEN", "LOG_RING", "OFFLINE_REMOVES", "SERIES_DAYS", "SYSTEMD_HOST",
    "SeatManager", "TIERS", "TIER_BROKER_STATUS_S", "TIER_PLANE_S", "TIER_REASONS_S", "TIER_RETRY_S", "TIER_SEATWORK_S",
    "TIER_SEATWORK_SETTLED_S", "TIER_SESSIONS_S", "TIER_SOURCES", "TIER_STANDING_PLAN_OPEN_S", "TIER_STANDING_S", "TIER_TTL_S",
    "TIER_UNIT_S", "TIER_WORKSTAT_S",
]
