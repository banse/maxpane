"""Tests for ``maxpane_dashboard.data.seat_manager`` (PEPEPANE plan WP7).

No test touches api.imd.fun, the real journal, a socket path, a real ``~/.maxpane``, Docker or ssh:
the manager gets a ``FakeBroker`` (WP6), a ``SeatApiClient`` on ``httpx.MockTransport`` (WP5), a
``SeatLedger`` on ``tmp_path`` (WP2), a stub ``UnitReader`` and ``ListLineSource`` lines (WP3).  The
tail *thread* is started only where a test says so.  Clocks are injected; the pinned epochs are those
of ``tests/analytics/test_seat_signals.py`` (T0 = 2026-09-26T03:40:12Z = 1790394012.0).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import seat_manager as sm_mod
from maxpane_dashboard.data import seat_models as models
from maxpane_dashboard.data.seat_broker_client import BrokerError, FakeBroker
from maxpane_dashboard.data.seat_ledger import SeatLedger
from maxpane_dashboard.data.seat_tail import ListLineSource, TailState

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "seat"
T0 = 1790394012.0


class Clock:
    """An injected clock: fixed until ``advance``; ``ticking=True`` adds one second per read (proof 13)."""

    def __init__(self, start: float = T0, *, ticking: bool = False) -> None:
        self.now = start
        self.ticking = ticking
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        if self.ticking:
            self.now += 1.0
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SourceSpy:
    """A ``tail`` factory that records every call and returns an empty ListLineSource."""

    def __init__(self) -> None:
        self.calls: list[TailState] = []
        self.lock = threading.Lock()

    def __call__(self, state: TailState):
        with self.lock:
            self.calls.append(state)
        return ListLineSource([])


class RaisingBroker:
    """A BrokerProtocol whose every entry point raises -- the manager must degrade, never propagate."""

    kind = "fake"
    offline = False

    def call(self, verb, args=None, *, timeout_s=20.0):
        raise RuntimeError(f"broker exploded on {verb}")

    def read(self, verb, args=None):
        raise RuntimeError(f"broker exploded on {verb}")

    def plan(self, verb, args=None):
        raise RuntimeError("plan")

    def apply(self, plan_id, confirm, *, force_node8=None, local_only_ack=None):
        raise RuntimeError("apply")

    def verify(self, plan_id):
        raise RuntimeError("verify")

    def reachable(self):
        raise RuntimeError("ping")

    def trust(self):
        return "host"


class RaisingUnitReader:
    def read_unit(self):
        raise OSError("systemctl exploded")

    def read_host(self):
        raise OSError("statvfs exploded")


def _api(handler):
    from maxpane_dashboard.data.seat_api import SeatApiClient

    return SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _no_network(request):
    raise AssertionError(f"a test reached the network: {request.url}")


def _exploding(request):
    raise httpx.ConnectError("boom", request=request)


def _manager(tmp_path, **over):
    kw = dict(tail=None, broker=FakeBroker(reachable=False), api=_api(_no_network), ledger_path=tmp_path / "ledger.sqlite",
              unit_reader=None, now=Clock(), host="systemd", seat=7, agent=51075, maxpane_dir=tmp_path)
    kw.update(over)
    return sm_mod.SeatManager(**kw)


# ---------------------------------------------------------------------------
# Task 7.6 — constants, construction, tier bookkeeping, never raises / never starts the tail
# ---------------------------------------------------------------------------


def test_tier_constants_are_the_contract_values():
    # contract §B data/seat_manager.py; spec §4.3 cadences
    assert sm_mod.TIERS == ("unit", "broker_status", "workstat", "sessions", "standing", "seatwork", "reasons", "plane")
    assert sm_mod.TIER_TTL_S == {"unit": 30, "broker_status": 600, "workstat": 300, "sessions": 120, "standing": 60,
                                 "seatwork": 120, "reasons": 300, "plane": 300}
    assert sm_mod.OFFLINE_REMOVES == ("standing", "seatwork", "reasons", "plane")
    assert (sm_mod.TIER_UNIT_S, sm_mod.TIER_BROKER_STATUS_S, sm_mod.TIER_WORKSTAT_S, sm_mod.TIER_SESSIONS_S) == (30, 600, 300, 120)
    assert (sm_mod.TIER_STANDING_S, sm_mod.TIER_STANDING_PLAN_OPEN_S, sm_mod.TIER_SEATWORK_S, sm_mod.TIER_SEATWORK_SETTLED_S) == (60, 15, 120, 300)
    assert (sm_mod.TIER_REASONS_S, sm_mod.TIER_PLANE_S) == (300, 300)
    assert (sm_mod.EVENT_BUMP_SESSIONS_S, sm_mod.EVENT_BUMP_STANDING_S, sm_mod.EVENT_BUMP_SEATWORK_S, sm_mod.EVENT_BUMP_WORKSTAT_S) == (20, 30, 60, 5)
    assert (sm_mod.DOCKER_TIMEOUT_S, sm_mod.DOCKER_BREAKER_S, sm_mod.LEDGER_ROWS_ON_SCREEN, sm_mod.COST_WINDOW_DAYS, sm_mod.SERIES_DAYS) == (25, 300, 60, 7, 14)
    assert (sm_mod.FIXTURE_HOST, sm_mod.SYSTEMD_HOST, sm_mod.DOCKER_HOST) == ("fixture", "systemd", "docker")
    assert sm_mod.HOST_KINDS == ("systemd", "docker", "fixture")
    assert sm_mod.TIER_RETRY_S == 60 and sm_mod.BACKFILL_QUIET_S == 2.0 and sm_mod.BACKFILL_MAX_S == 25.0
    assert set(sum(sm_mod.TIER_SOURCES.values(), ())) == set(models.SOURCE_NAMES) - {"tail"}


def test_construction_defaults(tmp_path):
    # contract §C.13: broker None -> FakeBroker(reachable=False); offline -> api ignored; ledger from maxpane_dir; tail None -> start_tail() False
    m = sm_mod.SeatManager(maxpane_dir=tmp_path, now=Clock(), offline=True, api=_api(_no_network))
    assert isinstance(m.broker, FakeBroker) and m.broker.reachable() is False and m.broker.offline is True
    assert m._api is None, "--offline ignores the api entirely"
    assert (tmp_path / "seat_ledger.sqlite").exists()
    assert m.start_tail() is False and m.tail_thread is None
    assert m.error_count == 0 and m._error_count == 0
    assert m.plan_open is False
    with pytest.raises(ValueError):
        sm_mod.SeatManager(maxpane_dir=tmp_path, host="kubernetes")


def test_due_and_bump_bookkeeping(tmp_path):
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    for tier in sm_mod.TIERS:
        assert m.due(tier, clock.now) is True, "every tier is due on the first tick"
    m._mark_read("standing", clock.now)
    assert m.due("standing", clock.now) is False
    assert m.due("standing", clock.now + 59) is False and m.due("standing", clock.now + 60) is True
    m.bump("standing", 30)
    assert m.due("standing", clock.now + 29) is False and m.due("standing", clock.now + 30) is True
    m.bump("standing", 45)
    assert m.due("standing", clock.now + 30) is True, "a bump never pushes a due time later"
    m.plan_open = True
    m._mark_read("standing", clock.now)
    assert m.due("standing", clock.now + 15) is True, "15 s while a control plan is open"
    with pytest.raises(KeyError):
        m.due("nope", clock.now)


async def test_fetch_and_compute_never_raises_and_never_starts_the_tail(tmp_path):
    # spec §4.3 / §15 decision: fetch_and_compute() never raises and never starts the thread; seat_cli calls start_tail()
    spy = SourceSpy()
    m = _manager(tmp_path, tail=spy, broker=RaisingBroker(), api=_api(_exploding), unit_reader=RaisingUnitReader())
    for _ in range(3):
        flat = await m.fetch_and_compute()
        await m.settle()
        assert tuple(flat) == models.SEAT_KEYS
    assert spy.calls == [], "fetch_and_compute() must not start the tail"
    assert m.tail_thread is None
    assert m.start_tail() is True
    deadline = time.monotonic() + 3.0
    while not spy.calls and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert len(spy.calls) >= 1 and isinstance(spy.calls[0], TailState)
    assert m.start_tail() is True, "a second call is a no-op"
    await m.close()
    assert m.tail_thread is None


async def test_first_document_is_the_empty_document_with_meta(tmp_path):
    clock = Clock()
    m = _manager(tmp_path, now=clock, hostname="ubuntu")
    flat = await m.fetch_and_compute()
    doc = m.document()
    assert doc["schemaVersion"] == 2 and doc["producer"] == "pepepane 0.1.0" and doc["pollInterval"] == 5
    assert doc["host"] == {"kind": "systemd", "unit": "imd-worker.service", "container": None, "runtime": None, "hostname": "ubuntu"}
    assert doc["startedAtUtc"] == "2026-09-26T03:40:12Z" and doc["completedAtUtc"] == "2026-09-26T03:40:12Z"
    assert tuple(doc["sources"]) == models.SOURCE_NAMES
    assert doc["sources"]["tail"]["ok"] is None and doc["sources"]["tail"]["reason"] == "tail thread not running", "never started = not read yet, not dead"
    assert doc["sources"]["standing"]["ok"] is None, "no tier has landed yet"
    assert models.validate_status_document(doc) is None
    assert flat["seat_host_kind"] == "systemd" and flat["seat_offline"] is False and flat["poll_interval"] == 5
    assert flat["seat_hero_state"] is None, "no evidence yet"
    assert "$" not in json.dumps(doc)
    await m.close()


async def test_owned_ledger_derives_tiers_and_the_ledger_mirrors_agree(tmp_path):
    # WP2 deviation 2 / WP4: SeatLedger derives tier_derived ONLY through the injected tier_lookup, and WP7 wires it (spec §5.4, §10);
    # spec §10: the broker projection's `inference` block replaces the dated memory-note rows going forward
    from maxpane_dashboard.analytics import seat_signals, seat_tiers
    from maxpane_dashboard.data import seat_api, seat_ledger
    from maxpane_dashboard.data.seat_log_grammar import classify

    m = _manager(tmp_path)                                  # seat 7, owned ledger
    assert m._ledger._tier_lookup == m._tier_lookup, "the owned ledger derives tiers through the manager"
    assert seat_ledger.IDLE_WINDOW_S == seat_signals.IDLE_WINDOW_S and seat_ledger.REASONS_PER_CYCLE == seat_api.MAX_REASONS_PER_CYCLE
    m._ledger.ingest([classify("2026-09-26T03:23:44.909Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)"),
                      classify("2026-09-26T03:23:49.300Z   working: running codex on gpt-6-luna")])
    expected = seat_tiers.tier_for("codex", "gpt-6-luna", None, "2026-09-26T03:23:49.300Z", seat=7)
    assert expected == "economy/standard" and m._ledger.open_row()["tierDerived"] == expected, "mutation proof 19's pair on #7"
    assert m._tier_lookup("codex", "gpt-6-terra", "low", "2026-09-26T03:23:49.300Z", seat=7) is None, "no projection yet: the dated rows"
    m._land("seat", {"inference": {"economy": {"codex": {"model": "gpt-6-terra", "effort": "low"}}}}, T0)
    assert m._tier_lookup("codex", "gpt-6-terra", "low", "2026-09-26T03:23:49.300Z", seat=7) == "economy", "the projection wins"
    await m.close()


def test_quiet_and_replay_sources_tick_until_closed():
    # WP3 deviation 1: LineSource.lines() yields a None idle tick at least every ALIVE_STAMP_S and TailThread stamps aliveAt only
    # on a yield -- a source that blocks silently would read `tail dead` after TAIL_DEAD_S (spec §9)
    quiet = sm_mod._QuietSource()
    quiet.open()
    ticks = quiet.lines()
    assert next(ticks) is None
    quiet.close()
    assert list(ticks) == []
    # a one-shot list that ends rc 0 holds the attach open (never `tail: exited rc=0` for good); a dying one still dies
    replay = sm_mod._ReplaySource(ListLineSource(["2026-09-26T03:40:08.226Z alive 14h42m · idle · 77 submitted"]))
    replay.open()
    it = replay.lines()
    assert next(it).text.startswith("2026-09-26T03:40:08.226Z alive")
    assert next(it) is None, "idle ticks after the clean end"
    replay.close()
    assert list(it) == []
    dying = sm_mod._ReplaySource(ListLineSource([], exit_code=1))
    dying.open()
    assert list(dying.lines()) == [] and dying.exit_code() == 1


# ---------------------------------------------------------------------------
# Task 7.7 — drain, event bumps, tail/daemon/current/tasks/today blocks
# ---------------------------------------------------------------------------

LIFECYCLE = [
    "2026-09-26T03:23:44.909Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)",
    "2026-09-26T03:23:46.100Z   preparing: cloning the base repository",
    "2026-09-26T03:23:49.300Z   working: running codex on gpt-6-luna",
    "2026-09-26T03:24:10.781Z   working: Created artifacts/answer.json",
    "2026-09-26T03:24:15.002Z   checking: formatting",
    "2026-09-26T03:24:16.500Z   bundling: checking source bundle size before upload",
    "2026-09-26T03:24:16.900Z   uploading: uploading 358 bytes",
    "2026-09-26T03:24:17.136Z submitted implement for 0c1f9727",
    "2026-09-26T03:24:17.236Z submission stored (c4d9714ffb95) — awaiting verdict",
]
HEARTBEATS = [
    "2026-09-26T03:39:38.226Z alive 14h41m · idle · 77 submitted · fleet 406 online, 417 enrolled",
    "2026-09-26T03:40:08.226Z alive 14h42m · idle · 77 submitted · fleet 406 online, 417 enrolled",
]
STARTUP = [
    "2026-09-25T11:45:41.402Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)",
    "2026-09-25T11:45:41.403Z execution profiles: none, foundry",
    "2026-09-25T11:45:41.410Z release 0.1.0+5bfa8261, the latest",
    "2026-09-25T11:45:42.100Z connected to api.imd.fun",
    "2026-09-25T11:45:43.200Z admitted (session 1a2b3c4d)",
]


async def test_event_bumps_after_submitted_and_stored(tmp_path):
    # spec §4.3: TIER_SESSIONS +20 s and TIER_STANDING +30 s after each `submitted`; TIER_SEATWORK +60 s after each `stored`
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    for tier in sm_mod.TIERS:
        m._mark_read(tier, clock.now)                      # nothing due for a while
    result = m.feed_lines(LIFECYCLE[:8])                    # ... up to `submitted`
    assert "submitted" in result.events and "stored" not in result.events
    assert m.due("sessions", clock.now + 20) and not m.due("sessions", clock.now + 19)
    assert m.due("standing", clock.now + 30) and not m.due("standing", clock.now + 29)
    assert not m.due("seatwork", clock.now + 60), "no `stored` yet"
    assert m.due("workstat", clock.now + 5), "the gate preview follows every lifecycle line (deviation 8)"
    result = m.feed_lines(LIFECYCLE[8:])
    assert result.events == ("stored",) or "stored" in result.events
    assert m.due("seatwork", clock.now + 60) and not m.due("seatwork", clock.now + 59)
    assert not m.due("plane", clock.now + 60), "plane is not event-driven"
    await m.close()


async def test_drain_takes_the_queue_and_replaying_is_idempotent(tmp_path):
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    from maxpane_dashboard.data.seat_log_grammar import classify
    for text in STARTUP + LIFECYCLE + HEARTBEATS:
        m._queue.put(classify(text, invocation="5e0c1a2b", cursor="s=1"))
    assert m.pending_lines() == len(STARTUP + LIFECYCLE + HEARTBEATS)
    first = m.drain()
    assert m.pending_lines() == 0 and first.lines == len(STARTUP + LIFECYCLE + HEARTBEATS)
    rows_after_first = m._ledger.counts()["rows"]
    m.feed_lines(LIFECYCLE)                                 # the same nine lines again
    assert m._ledger.counts()["rows"] == rows_after_first, "ledger rows are idempotent upserts (spec §9)"
    assert [line.seq for line in m._ring][:3] == [1, 2, 3], "the ring re-sequences monotonically across drains"
    await m.close()


async def test_daemon_current_tasks_and_today_blocks(tmp_path):
    # spec §7 daemon/current/tasks/today blocks from the ledger state; every stamp is the daemon's, every age from the clock
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    m.feed_lines(STARTUP + LIFECYCLE[:4])                   # open row, agent running
    await m.fetch_and_compute()
    doc = m.document()
    cur = doc["current"]
    assert cur["nodeId8"] == "0c1f9727" and cur["role"] == "implement" and cur["kind"] == "code" and cur["phase"] == "working"
    assert cur["startedUtc"] == "2026-09-26T03:23:44.909Z" and cur["maxTurns"] == 60 and cur["model"] == "gpt-6-luna"
    assert cur["tierDerived"] == "economy/standard", "spec §8 NOW `codex on gpt-6-luna (~economy/standard)`: the injected tier lookup (Task 7.6)"
    assert cur["elapsedS"] == 987 and cur["lastMessage"] == "Created artifacts/answer.json"   # 03:40:12 - 03:23:44.909
    assert tuple(cur) == models.SEAT_BLOCK_KEYS["seat_current"]
    assert doc["daemon"]["state"] is None and doc["daemon"]["idleBeats"] in (0, None), "no heartbeat yet"
    assert doc["daemon"]["invocationId"] is None or isinstance(doc["daemon"]["invocationId"], str)
    assert doc["daemon"]["lastAdmittedUtc"] == "2026-09-25T11:45:43.200Z"
    assert doc["seat"]["daemonVersion"] == "0.1.0+5bfa8261"

    m.feed_lines(LIFECYCLE[4:] + HEARTBEATS)
    await m.fetch_and_compute()
    doc = m.document()
    assert doc["current"] is None
    daemon = doc["daemon"]
    assert daemon["state"] == "alive" and daemon["uptime"] == "14h42m" and daemon["work"] == "idle" and daemon["running"] == 0
    assert daemon["submittedSinceStart"] == 77 and daemon["lastHeartbeatUtc"] == "2026-09-26T03:40:08.226Z"
    assert daemon["heartbeatAgeS"] == 3 and daemon["idleBeats"] == 2
    assert daemon["fleetOnline"] == 406 and daemon["fleetEnrolled"] == 417 and daemon["pausedHint"] is None
    assert daemon["consecutiveDisconnectedBeats"] == 0
    rows = doc["tasks"]["rows"]
    assert len(rows) == 1 and rows[0]["nodeId8"] == "0c1f9727" and rows[0]["hash12"] == "c4d9714ffb95"
    assert rows[0]["storedUtc"] == "2026-09-26T03:24:17.236Z" and rows[0]["agentRan"] is True
    assert rows[0]["outcome"] == "unknown", "spec §7: no verdict attached -> the producer writes 'unknown', never None"
    assert rows[0]["tierDerived"] == "economy/standard", "spec §8 LEDGER `model~tier`"
    assert tuple(rows[0]) == models.SEAT_ROW_KEYS["seat_tasks_rows"]
    window = doc["tasks"]["window"]
    assert window["rows"] == 1 and window["toUtc"] == "2026-09-26T03:40:08.226Z" and window["source"] == "journald"  # the configured host's transport
    today = doc["today"]
    assert today["dayUtc"] == "2026-09-26" and today["tasks"] == 1 and today["stored"] == 1 and today["notStored"] == 0
    assert today["p50S"] == 32 and today["divergence"] is None, "no plane rows yet"
    tail = doc["sources"]["tail"]
    assert tail["ok"] is None and tail["reason"] == "tail thread not running", "fed lines are not a running follower"
    assert doc["sources"]["tail"]["watermark"] is None or isinstance(doc["sources"]["tail"]["watermark"], str)
    await m.close()


class _StubThread:
    """What the manager reads from a TailThread: alive_at, reason, gap_note, backfill_note, backfill_at, stop()."""

    def __init__(self, alive_at, reason=None, gap_note=None, backfill_note=None, backfill_at=None):
        self.alive_at, self.reason, self.gap_note = alive_at, reason, gap_note
        self.backfill_note, self.backfill_at = backfill_note, backfill_at

    def stop(self, timeout_s=5.0):
        pass


async def test_tail_source_follows_the_thread(tmp_path):
    # spec §9: lines reach the ledger only through drain(); the source is ok while the thread stamps aliveAt
    clock = Clock()
    m = _manager(tmp_path, now=clock, tail=ListLineSource(HEARTBEATS))
    assert m.start_tail() is True
    deadline = time.monotonic() + 3.0
    while m.pending_lines() < 2 and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    await m.fetch_and_compute()
    doc = m.document()
    tail = doc["sources"]["tail"]
    assert tail["ok"] is True and tail["reason"] is None and tail["asOfUtc"] == "2026-09-26T03:40:12Z"
    assert tail["threadAliveAt"] is not None and doc["daemon"]["state"] == "alive"
    await m.close()


async def test_tail_dead_after_45s_gates_the_daemon_and_reds_the_hero(tmp_path):
    # spec §9: TAIL_DEAD_S = 45 without aliveAt -> sources.tail.ok false, hero red; the document keeps the stale values, the fold gates them (proof 8)
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    m.feed_lines(HEARTBEATS)
    m._thread = _StubThread(alive_at=T0)                    # a follower that stamped at T0 and then went silent
    await m.fetch_and_compute()
    assert m.document()["sources"]["tail"]["ok"] is True
    clock.advance(46)
    flat = await m.fetch_and_compute()
    tail = m.document()["sources"]["tail"]
    assert tail["ok"] is False and tail["reason"] == "tail dead 46 s — restarting" and tail["threadAliveAt"] == "2026-09-26T03:40:12Z"
    assert m.document()["daemon"]["state"] == "alive", "the document keeps the stale value"
    assert flat["seat_daemon_state"] is None and flat["seat_hero_state"] == "red" and flat["seat_hero_reasons"][0] == "tail dead 46 s"
    m._thread = _StubThread(alive_at=T0 + 46, reason="tail: exited rc=1 — retry in 8s")
    flat = await m.fetch_and_compute()
    assert m.document()["sources"]["tail"]["reason"] == "tail: exited rc=1 — retry in 8s" and flat["seat_hero_reasons"] == ["tail exited"]
    # spec §8 LEDGER footer `backfill 03:07 discarded (stale segment)`: WP3's sticky backfill_note outlives the exit reason and the thread
    m._thread = _StubThread(alive_at=T0 + 46, reason="tail: exited rc=1 — retry in 8s",
                            backfill_note="backfill stale segment, discarded", backfill_at=T0 - 60)
    await m.fetch_and_compute()
    assert m.document()["tasks"]["window"]["backfillDiscardedUtc"] == "2026-09-26T03:39:12Z"
    m._thread = None
    await m.fetch_and_compute()
    assert m.document()["tasks"]["window"]["backfillDiscardedUtc"] == "2026-09-26T03:39:12Z", "remembered after the thread is gone (--once)"
    await m.close()


async def test_frozen_tail_stops_vouching_idle(tmp_path):
    # spec §9: the idle-beat counter counts only heartbeats newer than now - 3 min, so a frozen tail cannot vouch "idle";
    # the ledger recounts against the clock on every tick, lines or not (WP2 _recount_beats)
    clock = Clock()
    m = _manager(tmp_path, now=clock)
    m.feed_lines(["2026-09-26T03:38:38.226Z alive 14h40m · idle · 77 submitted · fleet 406 online, 417 enrolled",
                  "2026-09-26T03:39:08.226Z alive 14h41m · idle · 77 submitted · fleet 406 online, 417 enrolled"] + HEARTBEATS)
    await m.fetch_and_compute()
    assert m.document()["daemon"]["idleBeats"] == 4
    clock.advance(200)                                      # no new line: the newest beat is now 204 s old
    await m.fetch_and_compute()
    assert m.document()["daemon"]["idleBeats"] == 0, "a frozen tail cannot vouch idle"
    await m.close()


async def test_restart_boundary_clears_restart_required(tmp_path):
    # spec §8 hero amber `restart required` / §7 control.restartRequired: set by the CONTROL modal after a skills-set apply,
    # cleared by the next restart boundary -- a `runtimes:` banner or an invocation change (contract C.6) -- never left on for good
    m = _manager(tmp_path, now=Clock())
    m.feed_lines(STARTUP)
    m.set_restart_required(True)
    result = m.feed_lines(LIFECYCLE[:3])
    assert "restart" not in result.events and m._restart_required is True, "an ordinary task is no restart"
    result = m.feed_lines(["2026-09-26T03:40:09.000Z shutting down",
                           "2026-09-26T03:40:10.402Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)"])
    assert "restart" in result.events and m._restart_required is False
    await m.close()


# ---------------------------------------------------------------------------
# Task 7.8 — unit/host reads, unit + machine blocks, configChangedSinceStart
# ---------------------------------------------------------------------------

import copy

UNIT_OK = {
    "activeState": "active", "subState": "running", "mainPid": 98508, "sinceUtc": "2026-09-25T11:45:41Z", "restarts": 0,
    "bootEnabled": False, "restartPolicy": "always/30s", "killMode": "control-group", "stopTimeoutS": 30,
    "memoryCurrentB": 115798016, "memoryPeakB": 188592128, "memoryMaxB": 3221225472, "cpuQuota": "100%", "tasksCurrent": 11,
}
HOST_OK = {"load1": 0.02, "memAvailMiB": 2964, "diskFreeGiB": 109.0, "hostname": "ubuntu",
           "journal": {"firstUtc": "2026-09-22T12:00:00Z", "lastUtc": "2026-09-26T03:40:11Z",
                       "capNote": "~347 MiB resolved at boot; 4 GiB after a journald restart"}}


class StubUnitReader:
    def __init__(self, unit, host):
        self.unit, self.host, self.calls = unit, host, 0

    def read_unit(self):
        self.calls += 1
        return copy.deepcopy(self.unit)

    def read_host(self):
        return copy.deepcopy(self.host)


async def test_systemd_unit_is_read_inline_every_tick(tmp_path):
    # spec §4.3 step 2: VPS systemctl show · cgroup · loadavg · statvfs inline (<= ms); gracefulStopPossible derived (§5.5)
    clock = Clock()
    reader = StubUnitReader(UNIT_OK, HOST_OK)
    m = _manager(tmp_path, now=clock, unit_reader=reader, runtime="codex")
    for _ in range(3):
        await m.fetch_and_compute()
    assert reader.calls == 3, "inline, every tick, never tiered on systemd"
    doc = m.document()
    assert doc["sources"]["unit"]["ok"] is True and doc["sources"]["unit"]["asOfUtc"] == "2026-09-26T03:40:12Z"
    unit = doc["unit"]
    assert unit["activeState"] == "active" and unit["memoryCurrentB"] == 115798016 and unit["stopTimeoutS"] == 30
    assert unit["gracefulStopPossible"] is True and unit["sinceUtc"] == "2026-09-25T11:45:41Z"
    assert set(unit) == set(models.empty_document(started_at_utc="x", host={})["unit"])
    machine = doc["machine"]
    assert machine["load1"] == 0.02 and machine["memAvailMiB"] == 2964 and machine["diskFreeGiB"] == 109.0
    assert machine["journal"]["capNote"].startswith("~347 MiB")
    assert machine["transcriptRetention"] == {"kind": "codex-rollouts", "plainDays": 7, "deleteDays": None, "zstdReadable": None}
    assert doc["seat"]["configChangedSinceStart"] is None, "no config mtime read yet (Task 7.9)"
    await m.close()


async def test_docker_unit_is_a_30s_tier_and_claude_retention(tmp_path):
    clock = Clock()
    docker_unit = dict(UNIT_OK, killMode=None, stopTimeoutS=10, init=False, sinceUtc="2026-09-21T19:57:03.123456789Z")
    reader = StubUnitReader(docker_unit, {"load1": 1.5, "memAvailMiB": 900, "diskFreeGiB": 40.0, "hostname": "mac", "journal": None})
    # hostname passed explicitly: host.hostname is the constructor's value (or platform.node()), never the host read's
    m = _manager(tmp_path, now=clock, unit_reader=reader, host="docker", container="imd-worker", runtime="claude", hostname="mac")
    await m.fetch_and_compute()
    await m.settle()
    await m.fetch_and_compute()
    await m.settle()
    assert reader.calls == 1, "docker inspect/stats ride TIER_UNIT (30 s), never inline (spec §4.3)"
    clock.advance(30)
    await m.fetch_and_compute()
    await m.settle()
    assert reader.calls == 2
    doc = m.document()
    assert doc["host"] == {"kind": "docker", "unit": None, "container": "imd-worker", "runtime": "claude", "hostname": "mac"}
    assert doc["unit"]["gracefulStopPossible"] is False, "StopTimeout 10, no init (fill1 §3)"
    assert doc["machine"]["transcriptRetention"] == {"kind": "claude-transcripts", "deleteDays": 30}
    await m.close()


async def test_docker_stats_ok_while_inspect_failed_is_per_field(tmp_path):
    # spec §7 `sources` mapped per field (fill4 §5: docker inspect and stats fail independently) / §14 mutation proof 8, manager half:
    # the half that answered is served, the failed half is None (never a stale or zero value), the host read is never gated on an
    # inspect failure, the reason rides sources.unit, and the hero is not red (the tail owns liveness)
    clock = Clock()
    partial = {"memoryCurrentB": 115798016, "activeState": None, "subState": None, "reason": "inspect timed out 25 s"}
    reader = StubUnitReader(partial, {"load1": 0.5, "memAvailMiB": 1200, "diskFreeGiB": 40.0, "hostname": "mac", "journal": None})
    m = _manager(tmp_path, now=clock, unit_reader=reader, host="docker", container="imd-worker", runtime="claude")
    await m.fetch_and_compute()
    await m.settle()
    flat = await m.fetch_and_compute()
    doc = m.document()
    src = doc["sources"]["unit"]
    assert src["ok"] is True and src["reason"] == "inspect timed out 25 s" and src["failures"] == 0
    assert src["asOfUtc"] == "2026-09-26T03:40:12Z"
    assert flat["seat_unit_memory_current_b"] == 115798016, "stats answered: served"
    assert flat["seat_unit_active_state"] is None and doc["unit"]["stopTimeoutS"] is None, "inspect failed: None, never 0"
    assert flat["seat_machine_load1"] == 0.5, "the host read answered: never gated on an inspect failure"
    assert flat["seat_sources"]["unit"]["reason"] == "inspect timed out 25 s", "WP8's UNIT box renders the reason amber"
    assert flat["seat_hero_state"] != "red", "an inspect timeout turns UNIT amber, never the hero (spec §9)"
    # the next read answers inspect only: the previous memory figure is gone, never served as live
    reader.unit = {"activeState": "running", "subState": "running", "stopTimeoutS": 10, "init": False, "reason": "stats timed out 25 s"}
    clock.advance(30)
    await m.fetch_and_compute()
    await m.settle()
    flat = await m.fetch_and_compute()
    assert flat["seat_unit_active_state"] == "running" and flat["seat_unit_memory_current_b"] is None
    assert m.document()["sources"]["unit"]["reason"] == "stats timed out 25 s"
    # a total failure: both reads None
    m2 = _manager(tmp_path / "b", now=clock, unit_reader=StubUnitReader(None, None), host="systemd")
    await m2.fetch_and_compute()
    src = m2.document()["sources"]["unit"]
    assert src["ok"] is False and src["reason"] == "unit and host reads failed" and src["asOfUtc"] is None
    await m.close()
    await m2.close()


async def test_a_raising_unit_reader_is_a_counted_failure(tmp_path):
    # spec §4.3: fetch_and_compute never raises -- a unit reader that explodes is one counted, reasoned failure of sources.unit
    m = _manager(tmp_path, unit_reader=RaisingUnitReader())
    flat = await m.fetch_and_compute()
    assert tuple(flat) == models.SEAT_KEYS and m.error_count >= 1
    src = m.document()["sources"]["unit"]
    assert src["ok"] is False and src["reason"] == "unit and host reads failed" and src["failures"] == 1
    await m.close()


async def test_config_changed_since_start_uses_the_unit_anchor(tmp_path):
    # spec §5.2: mtime > ActiveEnterTimestamp + 60 s; the projection's configMtimeUtc arrives with the `seat` source
    clock = Clock()
    m = _manager(tmp_path, now=clock, unit_reader=StubUnitReader(UNIT_OK, HOST_OK))
    m._land("seat", {"configMtimeUtc": "2026-09-25T11:45:00Z"}, clock.now)
    await m.fetch_and_compute()
    assert m.document()["seat"]["configChangedSinceStart"] is False
    m._land("seat", {"configMtimeUtc": "2026-09-25T14:00:00Z"}, clock.now)
    await m.fetch_and_compute()
    assert m.document()["seat"]["configChangedSinceStart"] is True
    assert m.document()["control"]["restartRequired"] is True, "a changed config needs a restart (spec §8 CONFIG)"
    # the CONTROL modal's skills-set flag (spec §11) is cleared by the next restart boundary (Task 7.7), not by a TUI restart
    m._land("seat", {"configMtimeUtc": "2026-09-25T11:45:00Z"}, clock.now)
    m.set_restart_required(True)
    await m.fetch_and_compute()
    assert m.document()["control"]["restartRequired"] is True
    m.feed_lines(["2026-09-26T03:40:10.402Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)"])
    await m.fetch_and_compute()
    assert m.document()["control"]["restartRequired"] is False
    await m.close()


# ---------------------------------------------------------------------------
# Task 7.9 — broker tiers: broker_status, workstat, sessions
# ---------------------------------------------------------------------------

DEVICE_KEY = "72b617d4" + "00" * 28        # synthetic 64-hex public key; only its first 8 chars ever enter the document
JOB = "b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70"
NODE = "0c1f9727-4c1e-4b8a-9f0d-2a6e7b3c5d11"
STATUS_LINES = [
    "config /home/imd-worker/.identitymd/config.json",
    "server https://api.imd.fun",
    "device scrubbed-7",
    "token 7",
    "capacity 1 concurrent task(s)",
    "✗ claude not found",
    "→ codex codex-cli 0.157.0",
    "tasks run on: codex",
    "offers: code, fuzz, research",
    "server active: eligible — this machine can receive work",
]
SKILLS_LINES = ["31 skills offered, 31 on here.", "on oracle-assess", "on public-rpcs — needs network", "on foundry-fuzz — needs tool:forge"]
SESSIONS_JSON = {
    "sessions": [{
        "path": "/home/imd-worker/.codex/sessions/2026/09/26/rollout-2026-09-26T03-23-49-abc.jsonl", "runtime": "codex",
        "cwd": f"/home/imd-worker/.identitymd/work/{JOB}/{NODE}", "slug": None, "kind": "task", "jobId": JOB, "nodeId": NODE,
        "startedUtc": "2026-09-26T03:23:49.400Z", "endedUtc": "2026-09-26T03:24:11.800Z", "mtime": 1790393051.8, "bytes": 200000,
        "model": "gpt-6-luna", "effort": "medium", "turns": 3, "turnsDefinition": "agent_messages",
        "tokens": {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0}, "sideModel": None, "ttftMs": 1807, "wallMs": 22400,
        "turn1Context": 24000, "maxTurnsReached": False, "maxTurns": 60, "apiErrors": [], "lastAgentMessageEmpty": False,
        "tokenCountInfoMissing": False, "taskCompleteErrorPresent": False,
        "quota": {"usedPercent": 45.0, "windowMinutes": 10080, "resetsAtUtc": "2026-09-28T21:50:11Z", "planType": "pro", "sampledAtUtc": "2026-09-26T03:24:15Z"},
        "skippedOversize": 0, "error": None,
    }],
    "skipped": {"oversize": 0}, "watermarkMtime": 1790393051.8, "zstdReadable": True, "reason": None,
}
RESPONSES = {
    "ping": {"pid": 4242, "version": "imd-dashd 0.1.0", "uptime_s": 12.5, "drain_armed": False, "in_flight": None, "posture_ok": True},
    "whoami": {"deviceKey": DEVICE_KEY},
    "seat": {"server": "https://api.imd.fun", "deviceKey": DEVICE_KEY, "wallet": "0x887b9f1234567890abcdef1234567890abcdef12", "tokenId": 7,
             "maxConcurrency": 1, "skillsOptOut": [], "inference": {"economy": {"codex": {"model": "gpt-6-luna", "effort": "medium"}},
             "standard": {"codex": {"model": "gpt-6-luna", "effort": "medium"}}, "premium": {"codex": {"model": "gpt-6-astra", "effort": "xhigh"}}},
             "tools": [], "configMtimeUtc": "2026-09-25T11:45:00Z"},
    "status": {"lines": STATUS_LINES, "rc": 0, "unit": "imd-dash-status-1"},
    "skills": {"lines": SKILLS_LINES, "rc": 0, "unit": "imd-dash-skills-2"},
    "tools": {"lines": ["no tools configured (/home/imd-worker/.identitymd/tools.json)"], "rc": 0, "unit": "imd-dash-tools-3"},
    "hints-stat": {"path": "~/.codex/AGENTS.md", "bytes": 1791, "sha8": "3f2a9c1e", "mtimeUtc": "2026-09-24T18:02:11Z"},
    "auth-mtime": {"path": "~/.codex/auth.json", "mtimeUtc": "2026-09-25T23:38:43Z"},
    "sessions": SESSIONS_JSON,
    "work-stat": {"count": 288, "bytes": 58314752, "abnormal": 7, "newest": [{"jobId": JOB, "nodeId": NODE, "mtimeUtc": "2026-09-26T03:23:45Z", "abnormal": False}]},
    "outbox": {"files": 0},
    "orphans": {"candidates": []},
    "gate": {"safe": True, "reason": None, "idle_beats": 9, "idle_beats_required": 4, "newest_heartbeat_age_s": 11.0,
             "plane": {"mode": "plane+local", "running": 0, "as_of": "2026-09-26T03:40:09Z", "standing_age_s": 0.4},
             "last_lifecycle_line": "2026-09-26T03:24:17.136Z submitted implement for 0c1f9727", "lifecycle_open": False,
             "outbox_files": 0, "unit_active": True, "graceful_stop_possible": True, "unknown": None},
    "audit-tail": {"lines": [{"ts": "2026-09-25T11:45:41Z", "seq": 1287, "peer_uid": 1001, "verb": "restart", "phase": "verify",
                              "plan_id": "7f3a9c1e2b4d6081", "args": {}, "preconditions": {}, "outcome": "applied", "verified": True,
                              "connected": True, "cursor_before": "s=1", "cursor_after": "s=2"}]},
}


def _calls(broker, verb):
    return [args for v, args in broker.calls if v == verb]


async def _two_cycles(m):
    await m.fetch_and_compute()
    await m.settle()
    return await m.fetch_and_compute()


async def test_broker_status_tier_feeds_seat_status_skills_hints_auth(tmp_path):
    # spec §4.3 TIER_BROKER_STATUS 600 s (seat, status, skills, tools, hints-stat, auth-mtime; whoami once); §7 seat block
    clock = Clock()
    broker = FakeBroker(responses=RESPONSES)
    m = _manager(tmp_path, now=clock, broker=broker, runtime="codex")
    flat = await _two_cycles(m)
    doc = m.document()
    for name in ("seat", "status", "skills", "hints", "auth"):
        assert doc["sources"][name]["ok"] is True and doc["sources"][name]["asOfUtc"] == "2026-09-26T03:40:12Z", name
    seat = doc["seat"]
    assert seat["tokenId"] == 7 and seat["deviceKeyPublic"] == "72b617d4" and seat["wallet"] == "0x887b9f"
    assert seat["server"] == "https://api.imd.fun" and seat["eligibility"] == "eligible — this machine can receive work"
    assert seat["capacity"] == 1 and seat["offers"] == ["code", "fuzz", "research"]
    assert seat["runtime"] == {"id": "codex", "version": "codex-cli 0.157.0"}
    assert seat["skills"]["offered"] == 31 and seat["skills"]["on"] == 31 and seat["skills"]["optOut"] == []
    assert seat["skills"]["rows"][1] == {"id": "public-rpcs", "on": True, "needs": "network"}
    assert seat["tools"] == [] and seat["inference"]["premium"] == {"codex": {"model": "gpt-6-astra", "effort": "xhigh"}}
    assert seat["hints"] == {"path": "~/.codex/AGENTS.md", "bytes": 1791, "sha8": "3f2a9c1e", "mtimeUtc": "2026-09-24T18:02:11Z"}
    assert doc["auth"]["credentialFileMtimeUtc"] == "2026-09-25T23:38:43Z"
    assert DEVICE_KEY not in json.dumps(doc), "the 64-hex key never enters the document (spec §13)"
    assert models.validate_status_document(doc) is None
    assert flat["seat_device_key_public"] == "72b617d4" and flat["seat_skills_rows"][2]["needs"] == "tool:forge"
    assert len(_calls(broker, "whoami")) == 1 and len(_calls(broker, "status")) == 1
    clock.advance(600)
    await _two_cycles(m)
    assert len(_calls(broker, "status")) == 2 and len(_calls(broker, "whoami")) == 1, "whoami once per session (spec §5.3)"
    await m.close()


async def test_broker_status_failures_are_per_source_and_container_trust(tmp_path):
    # spec §7 sources per field; §4.2 Mac CLI values carry trust: container; a canary refusal names itself
    clock = Clock()

    def refused(args):
        raise BrokerError("projection_refused", {"canary": "devicekey_mismatch"})

    responses = dict(RESPONSES, seat=refused)
    broker = FakeBroker(responses=responses, trust="container")
    m = _manager(tmp_path, now=clock, broker=broker, host="docker", container="imd-worker", runtime="claude",
                 unit_reader=StubUnitReader(UNIT_OK, HOST_OK), seat=None)     # no configured seat: tokenId must come from `imd status`
    await _two_cycles(m)
    doc = m.document()
    assert doc["sources"]["seat"]["ok"] is False and "canary" in doc["sources"]["seat"]["reason"]
    assert doc["sources"]["status"]["ok"] is True and doc["sources"]["status"]["trust"] == "container"
    assert doc["sources"]["skills"]["trust"] == "container" and doc["sources"]["unit"]["trust"] == "host"
    assert doc["seat"]["tokenId"] == 7, "status still answers"
    assert doc["seat"]["inference"] is None and doc["seat"]["wallet"] is None, "no projection, no config values"
    await m.close()


async def test_workstat_tier_feeds_machine_and_control(tmp_path):
    # spec §4.3 TIER_WORKSTAT 300 s (work-stat, outbox, orphans) + deviation 8 (ping, gate preview, audit-tail); §7 machine/control
    clock = Clock()
    broker = FakeBroker(responses=RESPONSES)
    m = _manager(tmp_path, now=clock, broker=broker)
    flat = await _two_cycles(m)
    doc = m.document()
    assert doc["sources"]["workstat"]["ok"] is True and doc["sources"]["broker"]["ok"] is True
    machine = doc["machine"]
    assert (machine["workDirs"], machine["workBytes"], machine["abnormalLeaseDirs"], machine["outboxFiles"], machine["orphans"]) == (288, 58314752, 7, 0, [])
    control = doc["control"]
    assert control["brokerReachable"] is True and control["drain"] is None and control["inFlight"] is None
    assert tuple(control["gate"]) == models.SEAT_BLOCK_KEYS["seat_control_gate"]
    assert control["gate"]["idleBeats"] == 9 and control["gate"]["planeMode"] == "plane+local" and control["gate"]["planeRunning"] == 0
    assert control["gate"]["planeAsOfUtc"] == "2026-09-26T03:40:09Z" and control["gate"]["safe"] is True and control["gate"]["outboxFiles"] == 0
    assert control["lastAudit"] == [{"ts": "2026-09-25T11:45:41Z", "seq": 1287, "verb": "restart", "phase": "verify",
                                     "planId": "7f3a9c1e2b4d6081", "outcome": "applied", "verified": True, "connected": True}]
    assert _calls(broker, "gate") == [{"offline": False}] and _calls(broker, "audit-tail") == [{"n": 5}]
    assert flat["seat_control_gate"]["safe"] is True and flat["seat_machine_work_dirs"] == 288
    # an unreachable broker: the broker source fails with a reason, nothing else is attempted
    down = FakeBroker(reachable=False)
    m2 = _manager(tmp_path / "b", now=clock, broker=down)
    await _two_cycles(m2)
    src = m2.document()["sources"]["broker"]
    assert src["ok"] is False and src["reason"] == "broker unreachable" and m2.document()["control"]["brokerReachable"] is False
    assert _calls(down, "gate") == []
    await m.close()
    await m2.close()


async def test_outbox_unreadable_is_none_never_zero(tmp_path):
    # spec §11 (d): an unreadable outbox is unknown -- None in the document, never 0
    clock = Clock()

    def unreadable(args):
        raise BrokerError("unreadable", {"what": "outbox"})

    broker = FakeBroker(responses=dict(RESPONSES, outbox=unreadable))
    m = _manager(tmp_path, now=clock, broker=broker)
    await _two_cycles(m)
    doc = m.document()
    assert doc["machine"]["outboxFiles"] is None and doc["machine"]["workDirs"] == 288
    assert doc["sources"]["workstat"]["ok"] is False and "outbox" in doc["sources"]["workstat"]["reason"]
    await m.close()


async def test_sessions_tier_attaches_sessions_and_fills_cost_quota_auth(tmp_path):
    # spec §4.3 TIER_SESSIONS 120 s; §5.4 watermark = newest mtime handed to `sessions --since`; §7 cost/quota/auth blocks; §10 no currency
    clock = Clock()
    # one flag-less `imd doctor` run in the same answer: stored by WP2 with task_key NULL, never a ledger row (spec §10)
    doctor = dict(SESSIONS_JSON["sessions"][0], path="/home/imd-worker/.codex/sessions/2026/09/26/rollout-2026-09-26T02-40-12-doc.jsonl",
                  cwd="/home/imd-worker", kind="doctor", jobId=None, nodeId=None, startedUtc="2026-09-26T02:40:12.000Z",
                  endedUtc="2026-09-26T02:40:30.000Z", mtime=T0 - 3570, quota=None)
    broker = FakeBroker(responses=dict(RESPONSES, sessions=dict(SESSIONS_JSON, sessions=SESSIONS_JSON["sessions"] + [doctor])))
    m = _manager(tmp_path, now=clock, broker=broker, runtime="codex")
    m.feed_lines(STARTUP + LIFECYCLE + HEARTBEATS)
    flat = await _two_cycles(m)
    doc = m.document()
    assert doc["sources"]["sessions"]["ok"] is True
    assert _calls(broker, "sessions")[0] == {"since": 0.0, "runtime": "codex"}
    assert m._ledger.meta_get("sessions_watermark_mtime") == 1790393051.8
    row = doc["tasks"]["rows"][0]
    assert row["tokens"] == {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0} and row["turns"] == 3
    assert row["tierDerived"] == "economy/standard", "spec §10: gpt-6-luna/medium on #7 after 09-23 19:56 (re-derived with the effort)"
    cost = doc["cost"]
    assert cost["windowDays"] == 7 and cost["tasks"] == 1 and cost["tokens"]["output"] == 812
    assert cost["excluded"] == {"doctor": 1, "manual": 0}, "spec §10: doctor runs are excluded AND counted (mutation proof 14's other half)"
    assert cost["buckets"][0]["model"] == "gpt-6-luna" and tuple(cost["buckets"][0]) == models.SEAT_ROW_KEYS["seat_cost_buckets"]
    assert cost["depth"]["skipped"] == {"oversize": 0} and cost["depth"]["ledgerFromUtc"] is not None
    assert set(cost["series"]) == {"outputTokensPerDay", "tasksPerDay", "acceptedPerDay"}
    # spec §5.6 / §8 COST sparkline: rolled up into the sqlite days table; only days the ledger covers (09-26), never a padded 0
    assert cost["series"]["tasksPerDay"] == [["2026-09-26", 1]] and cost["series"]["outputTokensPerDay"] == [["2026-09-26", 812]]
    assert doc["quota"] == {"provider": "codex", "window": "weekly", "usedPercent": 45.0, "resetsAtUtc": "2026-09-28T21:50:11Z",
                            "sampledAtUtc": "2026-09-26T03:24:15Z", "planType": "pro", "reason": None}
    assert doc["auth"]["degraded"] is False and doc["auth"]["reasons"] == []
    assert doc["machine"]["transcriptRetention"]["zstdReadable"] is True
    assert "$" not in json.dumps(doc)
    clock.advance(120)
    await _two_cycles(m)
    assert _calls(broker, "sessions")[1] == {"since": 1790393051.8, "runtime": "codex"}, "the watermark moves"
    assert flat["seat_cost_tasks"] == 1
    assert m.document()["cost"]["excluded"] == {"doctor": 1, "manual": 0}, "the same doctor session read twice counts once"
    await m.close()


async def test_oversize_skips_accumulate_across_incremental_calls(tmp_path):
    # spec §5.4 hostile size (`sessions.skipped.oversize`) / §8 COST footer `N oversize skipped`: the summariser is incremental
    # (--since), so each skipped file is reported once; the running total lives in ledger meta instead of resetting every 120 s
    clock = Clock()
    answers = iter([1, 0])

    def sessions(args):
        return dict(SESSIONS_JSON, skipped={"oversize": next(answers, 0)})

    m = _manager(tmp_path, now=clock, broker=FakeBroker(responses=dict(RESPONSES, sessions=sessions)), runtime="codex")
    await _two_cycles(m)
    assert m.document()["cost"]["depth"]["skipped"] == {"oversize": 1}
    clock.advance(120)
    await _two_cycles(m)
    assert m.document()["cost"]["depth"]["skipped"] == {"oversize": 1}, "the second call reported 0; the footer keeps 1"
    assert m._ledger.meta_get("sessions_skipped_oversize") == 1
    await m.close()


# ---------------------------------------------------------------------------
# Task 7.10 — api tiers: standing, seatwork, reasons, plane; unavailable; offline
# ---------------------------------------------------------------------------

API_FIX = FIXTURES / "api"


async def _no_sleep(seconds: float) -> None:
    return None


def _api_nosleep(handler):
    from maxpane_dashboard.data.seat_api import SeatApiClient

    return SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), sleep=_no_sleep)


class FixtureApi:
    """Serves the WP5 api fixtures by path; ``mode`` flips every answer to a 500; records every request."""

    def __init__(self, seat=7):
        self.seat, self.mode, self.requests = seat, "ok", []
        self.bodies = {
            f"/seats/{seat}/standing": "seat7_standing.json", f"/seats/{seat}": "seat7_work20.json",
            "/health": "health.json", "/services": "services.json",
        }

    def __call__(self, request):
        self.requests.append(request)
        if self.mode == "500":
            return httpx.Response(500, json={"error": "internal_error", "detail": "No space left on device"})
        path = request.url.path
        if path.startswith("/jobs/") and path.endswith("/submissions"):
            return httpx.Response(200, content=(API_FIX / "job_b1fb1439_submissions.json").read_bytes(),
                                  headers={"content-type": "application/json"})
        name = self.bodies.get(path)
        if name is None:
            return httpx.Response(404, json={"error": "not_found"})
        return httpx.Response(200, content=(API_FIX / name).read_bytes(), headers={"content-type": "application/json"})

    def paths(self, prefix):
        # path + query ("/seats/7?work=60&reviews=0"): httpx's url.path never carries the query string
        urls = [str(r.url).split("https://api.imd.fun", 1)[-1] for r in self.requests]
        return [u for u in urls if u.startswith(prefix)]


async def test_api_tiers_feed_standing_seatwork_and_plane(tmp_path):
    # spec §6 route table; §7 standing/queue/plane blocks; §4.3 cadences; standing is never read with ?queue=0 (proof 9 lives in WP5)
    clock = Clock()
    api = FixtureApi()
    m = _manager(tmp_path, now=clock, api=_api_nosleep(api))
    m.feed_lines(STARTUP + LIFECYCLE + HEARTBEATS)
    flat = await _two_cycles(m)
    doc = m.document()
    for name in ("standing", "seatWork", "reasons", "plane"):
        assert doc["sources"][name]["ok"] is True and doc["sources"][name]["asOfUtc"] == "2026-09-26T03:40:12Z", name
    assert api.paths("/seats/7/standing") == ["/seats/7/standing"], "no query string, ever (spec §6)"
    assert api.paths("/seats/7?") == ["/seats/7?work=60&reviews=0"]
    st = doc["standing"]
    assert (st["attempts"], st["accepted"], st["rejected"], st["failed"], st["pending"]) == (288, 244, 5, 11, 28) and st["countersInconsistent"] is False
    assert st["working"] == 1 and st["running"][0]["nodeKey"] == "oracle_assess" and st["presenceConnected"] is True
    assert st["breaker"] == {"failures": 3, "cooldownMs": 900000} and st["recentFailures"][0]["reason"] == "runtime_error"
    assert st["asOfUtc"] == "2026-09-26T03:24:55.812Z", "the plane's own `at`, never our fold time"
    assert doc["queue"] == {"ready": 27, "eligible": 0, "fleetOnline": 396, "blocked": [{"reason": "at capacity", "nodes": 27}], "asOfUtc": "2026-09-26T03:24:55.812Z"}
    assert doc["seat"]["agentId"] == 51075 and doc["seat"]["premiumAdvertised"] == {"model": "gpt-6-astra", "effort": "xhigh"}
    plane = doc["plane"]
    assert plane["version"] == "0.1.0+aa634633" and plane["verifierUp"] is True and plane["awaitingVerdict"] == 7 and plane["connectedDaemons"] == 409
    assert plane["verifierLastSeenUtc"] == "2026-09-26T03:32:58.104Z" and plane["asOfUtc"] == "2026-09-26T03:40:12Z"
    assert doc["today"]["divergence"] == {"localStored": 1, "planeRowsSubmittedToday": 19, "ok": False}, "1 stored locally today vs 19 plane rows: drift is reported, never hidden"
    assert doc["current"] is None
    assert flat["seat_standing_working"] == 1 and flat["seat_queue"]["ready"] == 27 and flat["seat_plane_awaiting_verdict"] == 7
    assert flat["seat_agent_id"] == 51075
    await m.close()


async def test_seatwork_backs_off_to_300s_once_every_open_row_has_a_verdict(tmp_path):
    # spec §4.3: TIER_SEATWORK 120 s; 300 s once all open rows have verdicts
    clock = Clock()
    api = FixtureApi()
    m = _manager(tmp_path, now=clock, api=_api_nosleep(api))
    await _two_cycles(m)                                    # no rows at all -> nothing open -> settled
    assert m.due("seatwork", clock.now + 120) is False and m.due("seatwork", clock.now + 300) is True
    # one stored row whose hash is not in the fixture (seat7_work20.json row 0 IS c4d9714ffb95…, status accepted -- WP5 ANCHOR_HASH)
    m.feed_lines([line.replace("c4d9714ffb95", "0123456789ab") for line in STARTUP + LIFECYCLE])
    clock.advance(300)
    await _two_cycles(m)
    assert m.due("seatwork", clock.now + 120) is True, "an open row without a verdict: back to 120 s"
    await m.close()


async def test_offline_removes_api_tiers_and_marks_every_plan_offline(tmp_path):
    # spec §1 #1, §4.3, §4.4, §11 (b): --offline reads nothing from the api and makes every broker plan `local-only`
    clock = Clock()
    gate = dict(RESPONSES["gate"], plane={"mode": "local-only", "running": None, "as_of": None, "standing_age_s": None})
    broker = FakeBroker(responses=dict(RESPONSES, gate=gate))
    m = _manager(tmp_path, now=clock, api=_api(_no_network), broker=broker, offline=True)
    m.feed_lines(STARTUP + LIFECYCLE + HEARTBEATS)
    flat = await _two_cycles(m)
    doc = m.document()
    assert m._api is None and m.broker.offline is True
    assert not any(name in doc["sources"] for name in ("standing", "seatWork", "reasons", "plane"))
    assert _calls(broker, "gate") == [{"offline": True}], "every plan/gate request carries offline: true"
    assert doc["standing"]["attempts"] is None and doc["queue"] is None and doc["plane"]["version"] is None
    assert doc["tasks"]["rows"][0]["outcome"] in (None, "unknown") and doc["today"]["divergence"] is None
    assert doc["seat"]["agentId"] == 51075, "the configured PEPEPANE_AGENT survives --offline (spec §8 SEAT)"
    assert flat["seat_offline"] is True and flat["seat_control_gate"]["planeMode"] == "local-only"
    assert flat["seat_daemon_state"] == "alive" and flat["seat_tasks_rows"][0]["outcome"] == "unknown"
    assert not any(src["unavailable"] for src in doc["sources"].values()), "absent, not unavailable"
    await m.close()


async def test_api_unavailable_after_3_failures_or_10_min_keeps_local_panels(tmp_path):
    # spec §6 rule 4: last-good behind its own asOfUtc; `unavailable` after 3 consecutive failures or 10 min without a good read;
    # total API failure leaves every local panel intact
    clock = Clock()
    api = FixtureApi()
    m = _manager(tmp_path, now=clock, api=_api_nosleep(api), unit_reader=StubUnitReader(UNIT_OK, HOST_OK))   # the unit gives the hero evidence
    m.feed_lines(STARTUP + LIFECYCLE + HEARTBEATS)
    await _two_cycles(m)
    assert m.document()["sources"]["standing"]["ok"] is True
    api.mode = "500"
    for failure in (1, 2):
        clock.advance(60)
        flat = await _two_cycles(m)
        src = m.document()["sources"]["standing"]
        assert src["ok"] is False and src["failures"] == failure and src["unavailable"] is False, failure
        assert src["asOfUtc"] == "2026-09-26T03:40:12Z" and src["reason"].startswith("500")
        assert m.document()["standing"]["working"] == 1 and flat["seat_standing_working"] == 1, "last-good stays until unavailable"
    clock.advance(60)
    flat = await _two_cycles(m)
    src = m.document()["sources"]["standing"]
    assert src["failures"] == 3 and src["unavailable"] is True
    assert flat["seat_standing_working"] is None and flat["seat_queue"] is None
    assert flat["seat_daemon_state"] == "alive" and flat["seat_tasks_rows"][0]["hash12"] == "c4d9714ffb95", "local panels intact"
    # a dead plane is not a dead seat: the hero leads with the local heartbeat's own age (T0+180 s vs 03:40:08.226) -- amber, never red offline
    # the `unavailable` standing's last-good presenceConnected/heartbeatAgeMs never feeds the hero (no `plane sees us · local tail stale`)
    assert flat["seat_hero_state"] == "amber" and flat["seat_hero_reasons"] == ["heartbeat 183 s old"]
    # the 10-minute rule: one good read, one failure a minute later (kept), then nothing good for 10 min
    clock2 = Clock()
    api2 = FixtureApi()
    m2 = _manager(tmp_path / "b", now=clock2, api=_api_nosleep(api2))
    await _two_cycles(m2)
    api2.mode = "500"
    clock2.advance(61)
    await _two_cycles(m2)
    assert m2.document()["sources"]["standing"]["unavailable"] is False and m2.document()["sources"]["standing"]["failures"] == 1
    clock2.advance(540)                                    # 601 s since the good read
    await _two_cycles(m2)
    src = m2.document()["sources"]["standing"]
    assert src["failures"] == 2 and src["unavailable"] is True and src["ageS"] == 601
    await m.close()
    await m2.close()


def _failed_history(hour, node8, hash12):
    return [
        f"2026-09-24T{hour:02d}:00:00.000Z accepted implement {node8} — artifacts/answer.json (max 60 turns)",
        f"2026-09-24T{hour:02d}:00:03.000Z   working: running codex on gpt-6-luna",
        f"2026-09-24T{hour:02d}:00:30.000Z submitted implement for {node8}",
        f"2026-09-24T{hour:02d}:00:30.100Z submission stored ({hash12}) — awaiting verdict",
    ]


async def test_reasons_tier_fetches_at_most_two_jobs_per_cycle(tmp_path):
    # spec §6: /jobs/<jobId>/submissions only for failed rows older than the 24 h standing window, <= 2 jobs per cycle, each job once
    clock = Clock()
    jobs = [f"aaaaaaa{i}-0000-4000-8000-000000000000" for i in (1, 2, 3)]
    nodes = ["11111111", "22222222", "33333333"]
    hashes = ["a" * 12, "b" * 12, "c" * 12]

    def handler(request):
        path = request.url.path
        if path == "/seats/7":
            api_fix.requests.append(request)
            work = [{"jobId": jobs[i], "objective": f"job {i}", "jobState": "completed", "nodeKey": "oracle_assess", "role": "implement",
                     "status": "failed", "submissionHash": hashes[i] + "0" * 52, "submittedAt": f"2026-09-24T0{i + 1}:00:30.100Z",
                     "acceptedAt": None, "launch": None} for i in range(3)]
            return httpx.Response(200, json={"tokenId": 7, "agentId": 51075, "attempts": 3, "accepted": 0, "rejected": 0, "failed": 3, "pending": 0,
                                             "work": work, "online": True, "devices": 1, "daemonVersion": "0.1.0+5bfa8261", "runtimes": []})
        return api_fix(request)

    api_fix = FixtureApi()
    m = _manager(tmp_path, now=clock, api=_api_nosleep(handler))
    for i in range(3):
        m.feed_lines(_failed_history(i + 1, nodes[i], hashes[i]))
    # httpx.MockTransport answers without yielding to the event loop (httpx 0.28.1), so the seatwork tier -- spawned before reasons --
    # has attached the three failed rows when the reasons tier's first step runs: two jobs already in the first cycle
    await _two_cycles(m)
    assert [r["outcome"] for r in m.document()["tasks"]["rows"]] == ["failed", "failed", "failed"]
    assert len(api_fix.paths("/jobs/")) == 2, "at most two jobs per cycle"
    reasons = [r["failureReason"] for r in m.document()["tasks"]["rows"]]
    assert reasons.count("runtime_error") == 2 and reasons.count(None) == 1
    assert m.document()["sources"]["reasons"]["ok"] is True
    clock.advance(300)
    await _two_cycles(m)
    assert len(api_fix.paths("/jobs/")) == 3, "the third job on the next cycle; each job fetched once"
    assert [r["failureReason"] for r in m.document()["tasks"]["rows"]] == ["runtime_error"] * 3
    assert [r["source"]["reason"] for r in m.document()["tasks"]["rows"]] == ["submissions"] * 3
    assert '"summary"' not in json.dumps(m.document()), "summaries never persist or render (spec §6)"
    await m.close()


async def test_fleet_falls_back_to_health_after_five_minutes_without_the_clause(tmp_path):
    # spec §6 `/services` + `/health` row: fleet online/enrolled come from the heartbeat clause first; /health fills the gap once the
    # clause has been missing for > 5 min (427+ clause-less lines measured) -- an old clause is never shown as current
    assert sm_mod.FLEET_CLAUSE_STALE_S == 300
    clock = Clock()
    beats = [
        "2026-09-26T03:33:32.000Z alive 14h35m · idle · 77 submitted · fleet 406 online, 417 enrolled",   # T0 - 400 s
        "2026-09-26T03:39:38.226Z alive 14h41m · idle · 77 submitted",
        "2026-09-26T03:40:08.226Z alive 14h42m · idle · 77 submitted",
    ]
    m = _manager(tmp_path, now=clock, api=_api_nosleep(FixtureApi()))
    m.feed_lines(beats)
    await _two_cycles(m)
    daemon = m.document()["daemon"]
    assert (daemon["fleetOnline"], daemon["fleetEnrolled"]) == (409, 417), "the 400-s-old clause gives way to /health"
    m2 = _manager(tmp_path / "b", now=clock, api=_api(_no_network), offline=True)
    m2.feed_lines(beats)
    await _two_cycles(m2)
    assert (m2.document()["daemon"]["fleetOnline"], m2.document()["daemon"]["fleetEnrolled"]) == (None, None), "never the stale clause"
    await m.close()
    await m2.close()
