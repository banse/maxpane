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
