"""``data/seat_tail.py`` -- the tail sources and the follower thread (spec §5.1, §9, §4.3).

No test here spawns ``journalctl`` or ``docker``: every source runs behind an injected
``popen``/``run`` that serves fixture bytes over a real pipe (so ``select`` is exercised),
or is a ``ListLineSource``. ``HOME`` is a temp dir; the tail state lives on ``tmp_path``.
"""

from __future__ import annotations

import ast
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.data import seat_tail
from maxpane_dashboard.data.seat_tail import (
    TailThread,

    DockerLogsSource,
    docker_factory,

    JournaldSource,
    journald_factory,

    backfill_is_stale,
    detect_gap,

    TailState,

    ALIVE_STAMP_S,
    BACKOFF_MAX_S,
    BACKOFF_MIN_S,
    DAEMON_STAMP_RE,
    DEDUP_KEYS_MAX,
    DOCKER_BACKFILL_TIMEOUT_S,
    DOCKER_FIRST_RUN_SINCE,
    DOCKER_TAIL_LINES,
    GAP_TOLERANCE_S,
    JOURNAL_FIRST_RUN_SINCE,
    KIND_DOCKER,
    KIND_JOURNALD,
    KIND_LIST,
    ListLineSource,
    RawLine,
    STALE_BACKFILL_REASON,
    TAIL_FILE,
    daemon_stamp,
    journal_since_arg,
    realtime_us_to_iso,
    split_docker_prefix,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat" / "grammar"

HB1 = "2026-09-26T03:40:07.120Z alive 14h42m · idle · 77 submitted · fleet 406 online, 417 enrolled"
HB2 = "2026-09-26T03:40:37.121Z alive 14h43m · idle · 77 submitted · fleet 406 online, 417 enrolled"
ACC = "2026-09-26T03:40:52.400Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)"
NPM = "npm warn deprecated inflight@1.0.6: This module is not supported"


# =============================================================================
# Task 3.1 -- constants, RawLine, ListLineSource, helpers
# =============================================================================


def test_constants_match_the_contract():
    # contract §B data/seat_tail.py; spec §5.1, §9
    assert JOURNAL_FIRST_RUN_SINCE == "-14d"
    assert GAP_TOLERANCE_S == 60
    assert DOCKER_TAIL_LINES == 200
    assert DOCKER_BACKFILL_TIMEOUT_S == 25
    assert (BACKOFF_MIN_S, BACKOFF_MAX_S) == (1, 30)
    assert ALIVE_STAMP_S == 1.0
    assert TAIL_FILE == "seat_tail.json"
    assert (KIND_JOURNALD, KIND_DOCKER, KIND_LIST) == ("journald", "docker-log", "list")
    assert STALE_BACKFILL_REASON == "backfill stale segment, discarded"
    assert DOCKER_FIRST_RUN_SINCE == "336h"
    assert DEDUP_KEYS_MAX == 2000


def test_rawline_defaults_are_trusted_and_bare():
    raw = RawLine("x")
    assert (raw.cursor, raw.invocation, raw.realtime_us, raw.trusted) == (None, None, None, True)
    with pytest.raises(Exception):
        raw.text = "y"  # frozen


def test_list_source_replays_strings_and_rawlines_in_order_and_reports_exit():
    # spec §4.4: the fixture host replays a captured log through the same start_tail() path
    src = ListLineSource([HB1, RawLine(ACC, cursor="c1")], exit_code=3)
    assert src.kind == KIND_LIST
    src.open()
    assert src.exit_code() is None                 # still "running"
    got = [item for item in src.lines() if item is not None]
    assert [r.text for r in got] == [HB1, ACC]
    assert got[1].cursor == "c1" and got[0].trusted is True
    assert src.exit_code() == 3
    assert src.backfill() is None


def test_list_source_backfill_is_marked_untrusted():
    # spec §5.1 Mac transport: the --since body is untrusted until the discard rule clears it
    src = ListLineSource([HB2], backfill=[HB1, RawLine(ACC)])
    body = src.backfill()
    assert body is not None and [r.text for r in body] == [HB1, ACC]
    assert all(r.trusted is False for r in body)


def test_list_source_delay_yields_idle_ticks_without_real_sleep(monkeypatch):
    # spec §9: the thread must be able to stamp aliveAt every second even when no line arrives,
    # so a waiting source yields None ticks in ALIVE_STAMP_S slices
    slept: list[float] = []
    monkeypatch.setattr(seat_tail.time, "sleep", slept.append)
    src = ListLineSource([HB1], delay_s=2.5)
    src.open()
    items = list(src.lines())
    assert items[-1].text == HB1
    assert items[:-1] == [None, None, None]
    assert slept == [1.0, 1.0, 0.5]


def test_list_source_time_scale_waits_the_stamps_spacing(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(seat_tail.time, "sleep", slept.append)
    src = ListLineSource([HB1, HB2], time_scale=30.0)     # 30.001 s apart -> ~1.0 s
    src.open()
    items = list(src.lines())
    assert [i.text for i in items if i is not None] == [HB1, HB2]
    assert len(slept) >= 1 and abs(sum(slept) - 30.001 / 30.0) < 1e-6


def test_split_docker_prefix_strips_exactly_one_rfc3339nano_token():
    # header Review Focus #2 / spec §5.1: --timestamps puts Docker's stamp in front of the daemon's
    stamp, rest = split_docker_prefix("2026-09-26T03:40:07.123456789Z " + HB1)
    assert stamp == "2026-09-26T03:40:07.123456789Z" and rest == HB1
    # Go's RFC3339Nano trims trailing zeros: fewer digits, and none at all, are the same prefix
    assert split_docker_prefix("2026-09-26T03:40:07.5Z " + NPM) == ("2026-09-26T03:40:07.5Z", NPM)
    assert split_docker_prefix("2026-09-26T03:40:07Z " + NPM) == ("2026-09-26T03:40:07Z", NPM)
    # exactly one token is split off, whatever its digit count -- so the daemon's own stamp survives on
    # --timestamps output, and the function is applied ONLY to --timestamps output (a bare daemon line
    # would lose its stamp: that is the caller's contract, pinned here so nobody "fixes" it by guessing)
    assert daemon_stamp(rest) == "2026-09-26T03:40:07.120Z"
    assert split_docker_prefix(HB1) == ("2026-09-26T03:40:07.120Z", HB1[25:])
    assert split_docker_prefix(NPM) == (None, NPM)


def test_daemon_stamp_reads_only_the_daemon_shape():
    assert daemon_stamp(HB1) == "2026-09-26T03:40:07.120Z"
    assert daemon_stamp(NPM) is None
    assert daemon_stamp("2026-09-26T03:40:07.123456789Z " + HB1) is None   # Docker's shape is not the daemon's
    assert DAEMON_STAMP_RE.pattern.startswith("^")


def test_realtime_us_to_iso_matches_the_daemon_stamp_shape():
    # spec §5.1 VPS transport: the first __REALTIME_TIMESTAMP is compared with lastTsUtc
    assert realtime_us_to_iso(1790394007120000) == "2026-09-26T03:40:07.120Z"
    assert realtime_us_to_iso(1790394007120999) == "2026-09-26T03:40:07.120Z"   # floors to ms


def test_journal_since_arg_is_the_systemd_time_form():
    # spec §5.1: the fallback attach is --since <lastTsUtc>; journalctl takes "YYYY-MM-DD HH:MM:SS UTC"
    assert journal_since_arg("2026-09-24T04:12:00.000Z") == "2026-09-24 04:12:00 UTC"
    assert journal_since_arg("2026-09-24T04:12:00.999Z") == "2026-09-24 04:12:00 UTC"  # floored second
    assert journal_since_arg(None) == JOURNAL_FIRST_RUN_SINCE
    assert journal_since_arg("garbage") == JOURNAL_FIRST_RUN_SINCE

# =============================================================================
# Task 3.2 -- TailState
# =============================================================================


def test_tail_state_roundtrip_is_atomic_and_0600(tmp_path):
    # spec §9 Watermarks: ~/.maxpane/seat_tail.json {"kind","cursor","lastTsUtc","invocation"}
    path = tmp_path / ".maxpane" / TAIL_FILE
    state = TailState(kind=KIND_JOURNALD, cursor="s=1;i=2", last_ts_utc="2026-09-26T03:40:07.120Z",
                      invocation="a1b2", watermark_ts=None)
    state.save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (tmp_path / ".maxpane" / (TAIL_FILE + ".tmp")).exists()
    payload = json.loads(path.read_text())
    assert payload == {"version": 1, "kind": "journald", "cursor": "s=1;i=2",
                       "lastTsUtc": "2026-09-26T03:40:07.120Z", "invocation": "a1b2", "watermarkTs": None}
    assert TailState.load(path) == state


def test_tail_state_missing_corrupt_or_foreign_version_yields_defaults(tmp_path):
    assert TailState.load(tmp_path / "nope.json") == TailState()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert TailState.load(bad) == TailState()
    bad.write_text(json.dumps([1, 2]))
    assert TailState.load(bad) == TailState()
    bad.write_text(json.dumps({"version": 2, "cursor": "x"}))
    assert TailState.load(bad).cursor is None
    # a hand-edited value of the wrong type is third-party input, not a crash
    bad.write_text(json.dumps({"version": 1, "cursor": 17, "lastTsUtc": ["a"]}))
    assert TailState.load(bad) == TailState()


def test_tail_state_save_failure_is_logged_not_raised(tmp_path, caplog):
    target = tmp_path / "file-not-dir"
    target.write_text("")
    TailState(kind="x").save(target / TAIL_FILE)      # parent is a file -> OSError inside
    assert "failed to save tail state" in caplog.text

# =============================================================================
# Task 3.3 -- detect_gap / backfill_is_stale
# =============================================================================


def test_detect_gap_is_from_data_not_exit_code():
    # spec §5.1 VPS transport: a first entry newer than lastTsUtc + 60 s is a gap even with exit 0
    last = "2026-09-24T04:12:00.000Z"
    assert detect_gap(first_realtime_utc="2026-09-26T03:40:07.120Z", last_ts_utc=last, exit_code=0) == \
        "gap 2026-09-24T04:12:00.000Z→2026-09-26T03:40:07.120Z"
    # exactly +60 s is NOT a gap ("newer than lastTsUtc + 60 s")
    assert detect_gap(first_realtime_utc="2026-09-24T04:13:00.000Z", last_ts_utc=last, exit_code=0) is None
    assert detect_gap(first_realtime_utc="2026-09-24T04:13:00.001Z", last_ts_utc=last, exit_code=0) is not None
    # an entry older than lastTs (the --since fallback re-reads from lastTs) is not a gap
    assert detect_gap(first_realtime_utc="2026-09-24T04:11:30.000Z", last_ts_utc=last, exit_code=0) is None


def test_detect_gap_on_non_zero_exit_and_on_nothing_to_compare():
    assert detect_gap(first_realtime_utc=None, last_ts_utc="2026-09-24T04:12:00.000Z", exit_code=1) == \
        "gap 2026-09-24T04:12:00.000Z→?"
    assert detect_gap(first_realtime_utc=None, last_ts_utc="2026-09-24T04:12:00.000Z", exit_code=0) is None
    assert detect_gap(first_realtime_utc="2026-09-26T03:40:07.120Z", last_ts_utc=None, exit_code=1) is None  # first run


def test_backfill_is_stale_rule():
    # spec §5.1 Mac transport: compared with the persisted watermark AND the follower's first line
    wm, first = "2026-09-20T12:59:40.000Z", "2026-09-20T13:05:12.001Z"
    assert backfill_is_stale(newest_backfill_ts=None, watermark_ts=wm, follower_first_ts=first) is True
    assert backfill_is_stale(newest_backfill_ts="2026-09-20T10:04:41.220Z", watermark_ts=wm, follower_first_ts=first) is True
    assert backfill_is_stale(newest_backfill_ts="2026-09-20T13:00:00.000Z", watermark_ts=wm, follower_first_ts=first) is True   # > 60 s before the follower
    assert backfill_is_stale(newest_backfill_ts="2026-09-20T13:04:30.000Z", watermark_ts=wm, follower_first_ts=first) is False
    assert backfill_is_stale(newest_backfill_ts="2026-09-20T13:06:00.000Z", watermark_ts=None, follower_first_ts=None) is False
    assert backfill_is_stale(newest_backfill_ts="2026-09-20T13:04:30.000Z", watermark_ts=None, follower_first_ts=first) is False


# --- a Popen recorder that serves bytes over a real pipe ---------------------------------


class _Proc:
    def __init__(self, body: bytes, rc: int) -> None:
        read_fd, write_fd = os.pipe()
        os.write(write_fd, body)
        os.close(write_fd)                      # EOF once the body is consumed
        self.stdout = os.fdopen(read_fd, "rb", buffering=0)
        self._rc = rc
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout=None) -> int:
        self.returncode = self._rc
        return self._rc

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = self._rc

    def kill(self) -> None:
        self.killed = True
        self.returncode = self._rc


class ScriptedPopen:
    """``popen`` seam: records every argv, serves one scripted body per call."""

    def __init__(self, bodies: list[bytes], rcs: list[int] | None = None) -> None:
        self.bodies = list(bodies)
        self.rcs = list(rcs or [0] * len(bodies))
        self.calls: list[tuple[list[str], dict]] = []
        self.procs: list[_Proc] = []

    def __call__(self, argv, **kw) -> _Proc:
        self.calls.append((list(argv), dict(kw)))
        index = min(len(self.calls) - 1, len(self.bodies) - 1)
        proc = _Proc(self.bodies[index], self.rcs[index])
        self.procs.append(proc)
        return proc


class ScriptedRun:
    """``run`` seam: records argv + kwargs, returns a ``CompletedProcess`` or raises."""

    def __init__(self, stdout: bytes = b"", rc: int = 0, raise_exc: BaseException | None = None) -> None:
        self.stdout, self.rc, self.raise_exc = stdout, rc, raise_exc
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kw) -> subprocess.CompletedProcess:
        self.calls.append((list(argv), dict(kw)))
        if self.raise_exc is not None:
            raise self.raise_exc
        return subprocess.CompletedProcess(list(argv), self.rc, stdout=self.stdout, stderr=b"")


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# =============================================================================
# Task 3.4 -- JournaldSource
# =============================================================================


def test_journald_argv_forms_are_the_two_documented_ones():
    # spec §5.1 VPS transport: -o json -f --after-cursor=<cursor>; first run --since -14d
    assert JournaldSource().argv() == ["journalctl", "-u", "imd-worker.service", "-o", "json", "-f", "--since", "-14d"]
    assert JournaldSource("imd-worker.service", cursor="s=1;i=2").argv()[-2:] == ["--after-cursor", "s=1;i=2"]
    assert JournaldSource(since="2026-09-24 04:12:00 UTC").argv()[-2:] == ["--since", "2026-09-24 04:12:00 UTC"]
    src = JournaldSource(cursor="s=1;i=2", since="2026-09-24 04:12:00 UTC")
    assert "--since" not in src.argv()             # a cursor wins over since


def test_journald_source_parses_o_json_records_from_the_fixture():
    # fixture grammar/journal_json_records.jsonl: the -o json shape with __CURSOR, __REALTIME_TIMESTAMP,
    # _SYSTEMD_INVOCATION_ID and MESSAGE carrying the daemon's own stamp (vps §2)
    popen = ScriptedPopen([_fixture_bytes("journal_json_records.jsonl")])
    src = JournaldSource("imd-worker.service", cursor="s=00000000000000000000000000000001;i=1ef", popen=popen)
    src.open()
    argv, kw = popen.calls[0]
    assert argv == ["journalctl", "-u", "imd-worker.service", "-o", "json", "-f",
                    "--after-cursor", "s=00000000000000000000000000000001;i=1ef"]
    assert kw["stdout"] is subprocess.PIPE and "shell" not in kw
    got = [r for r in src.lines() if r is not None]
    assert len(got) == 9
    unit_event, runtimes, heartbeat = got[0], got[1], got[2]
    assert unit_event.text == "Started imd-worker.service - IdentityMD worker daemon."
    assert unit_event.invocation is None                       # systemd's own line: no _SYSTEMD_INVOCATION_ID
    assert unit_event.cursor.startswith("s=") and unit_event.realtime_us == 1790393995000000
    assert runtimes.text.endswith("runtimes: codex (using codex, as asked)")
    assert heartbeat.invocation == "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert realtime_us_to_iso(heartbeat.realtime_us) == "2026-09-26T03:40:07.120Z" == daemon_stamp(heartbeat.text)
    assert all(r.trusted for r in got)
    assert src.exit_code() == 0


def test_journald_source_tolerates_binary_message_and_garbage_lines():
    body = b"\n".join([
        b"not json at all",
        json.dumps({"__CURSOR": "s=1", "__REALTIME_TIMESTAMP": "1790394007120000",
                    "MESSAGE": list("2026-09-26T03:40:07.120Z alive 1m".encode())}).encode(),
        json.dumps(["a", "list"]).encode(),
        json.dumps({"__CURSOR": "s=2", "__REALTIME_TIMESTAMP": "not-a-number", "MESSAGE": None}).encode(),
    ]) + b"\n"
    src = JournaldSource(popen=ScriptedPopen([body]))
    src.open()
    got = [r for r in src.lines() if r is not None]
    assert [r.text for r in got] == ["2026-09-26T03:40:07.120Z alive 1m", ""]
    assert got[1].realtime_us is None and got[1].cursor == "s=2"


def test_journald_close_terminates_then_kills_within_stop_timeout():
    class _Hang(_Proc):
        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("journalctl", timeout)
            self.returncode = 137
            return 137

    class _HangPopen(ScriptedPopen):
        def __call__(self, argv, **kw):
            self.calls.append((list(argv), dict(kw)))
            proc = _Hang(b"", 137)
            self.procs.append(proc)
            return proc

    popen = _HangPopen([b""])
    src = JournaldSource(popen=popen, stop_timeout_s=0.01)
    src.open()
    src.close()
    proc = popen.procs[0]
    assert proc.terminated and proc.killed
    src.close()                                  # idempotent


def test_journald_factory_picks_cursor_then_since_fallback_then_first_run():
    popen = ScriptedPopen([b""])
    make = journald_factory("imd-worker.service", popen=popen)
    assert make(TailState(cursor="s=9;i=a")).argv()[-2:] == ["--after-cursor", "s=9;i=a"]
    assert make(TailState(cursor=None, last_ts_utc="2026-09-24T04:12:00.000Z")).argv()[-2:] == \
        ["--since", "2026-09-24 04:12:00 UTC"]
    assert make(TailState()).argv()[-2:] == ["--since", "-14d"]

# =============================================================================
# Task 3.5 -- DockerLogsSource
# =============================================================================


def test_docker_follower_argv_is_only_the_trusted_form():
    # spec §5.1 Mac transport / §9 Docker equivalent: `-f --tail 200 --timestamps` is the ONLY trusted read;
    # `--since` is never the follower. Mutation: --tail != 200, or a --since follower -> this reddens.
    popen = ScriptedPopen([b""])
    src = DockerLogsSource("imd-worker", watermark_ts="2026-09-26T03:40:07.120Z", popen=popen)
    assert src.follower_argv() == ["docker", "logs", "-f", "--tail", "200", "--timestamps", "imd-worker"]
    src.open()
    argv, kw = popen.calls[0]
    assert argv == ["docker", "logs", "-f", "--tail", str(DOCKER_TAIL_LINES), "--timestamps", "imd-worker"]
    assert "--since" not in argv and argv.count("--tail") == 1 and argv[argv.index("--tail") + 1] == "200"
    assert "shell" not in kw
    assert src.kind == KIND_DOCKER


def test_docker_follower_strips_the_timestamps_prefix_and_keeps_unstamped_lines():
    body = ("2026-09-26T03:40:07.123456789Z " + HB1 + "\n" + "2026-09-26T03:40:09.5Z " + NPM + "\n").encode()
    src = DockerLogsSource(popen=ScriptedPopen([body]))
    src.open()
    got = [r for r in src.lines() if r is not None]
    assert [r.text for r in got] == [HB1, NPM]
    assert all(r.trusted and r.cursor is None for r in got)


def test_docker_backfill_runs_since_watermark_with_timeout_and_is_untrusted():
    # spec §5.1 Mac transport: one-shot `docker logs --since <watermark> --timestamps`, 25 s timeout, untrusted
    run = ScriptedRun(stdout=_fixture_bytes("docker_stale_segment.log"))
    src = DockerLogsSource("imd-worker", watermark_ts="2026-09-20T12:59:40.000Z", run=run)
    body = src.backfill()
    argv, kw = run.calls[0]
    assert argv == ["docker", "logs", "--since", "2026-09-20T12:59:40.000Z", "--timestamps", "imd-worker"]
    assert kw["timeout"] == DOCKER_BACKFILL_TIMEOUT_S == 25 and "shell" not in kw
    assert body is not None and len(body) == 6
    assert body[0].text.startswith("2026-09-20T09:58:12.301Z alive") and all(not r.trusted for r in body)
    assert max(daemon_stamp(r.text) for r in body) == "2026-09-20T10:04:41.220Z"


def test_docker_backfill_first_run_uses_the_14_day_window_and_failures_yield_none():
    assert DockerLogsSource().backfill_argv() == ["docker", "logs", "--since", DOCKER_FIRST_RUN_SINCE, "--timestamps", "imd-worker"]
    timeout = ScriptedRun(raise_exc=subprocess.TimeoutExpired("docker", 25))
    assert DockerLogsSource(run=timeout).backfill() is None
    missing = ScriptedRun(raise_exc=FileNotFoundError("docker"))
    assert DockerLogsSource(run=missing).backfill() is None
    failed = ScriptedRun(stdout=b"Error response from daemon: No such container\n", rc=1)
    assert DockerLogsSource(run=failed).backfill() is None


def test_docker_factory_passes_the_persisted_watermark_to_the_backfill():
    run = ScriptedRun(stdout=b"")
    make = docker_factory("imd-worker", popen=ScriptedPopen([b""]), run=run)
    src = make(TailState(kind=KIND_DOCKER, watermark_ts="2026-09-26T03:40:07.120Z"))
    src.backfill()
    assert run.calls[0][0][3] == "2026-09-26T03:40:07.120Z"


# --- a classify seam that needs no WP2 --------------------------------------------------


@dataclass(frozen=True)
class _StubLine:
    """The shape of ``seat_log_grammar.LogLine`` (contract C.5) as this module relies on it."""

    ts: str
    invocation: str | None
    text: str
    kind: str
    cursor: str | None
    seq: int


def _stub_classify(line: str, *, invocation=None, cursor=None, seq=0) -> _StubLine:
    stamp = daemon_stamp(line) or ""
    if not stamp:
        kind = "unknown"
    elif " alive " in line or " disconnected " in line:
        kind = "heartbeat"
    elif " accepted " in line:
        kind = "accepted_code"
    else:
        kind = "other"
    return _StubLine(stamp, invocation, line, kind, cursor, seq)


class _Clock:
    def __init__(self, start: float = 1_790_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _drain(q: "queue.Queue") -> list:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out




def _thread(source_factory, *, state=None, state_path=None, clock=None, redact_fn=None, classify=_stub_classify):
    q: "queue.Queue" = queue.Queue()
    thread = TailThread(
        source_factory, q,
        state=state or TailState(),
        state_path=state_path,
        now=clock or _Clock(),
        redact=redact_fn or (lambda s: s),
        classify=classify,
    )
    return thread, q


# =============================================================================
# Task 3.6 -- TailThread core: redact -> classify -> queue, watermark, aliveAt, persistence
# =============================================================================


def test_thread_classifies_raw_then_redacts_before_queue_with_monotonic_seq():
    # Fix3: raw classification must preserve lifecycle events; only redacted LogLine reaches the queue.
    hostile = "2026-09-25T23:41:22.577Z alive 11h55m · idle · 13 submitted · paused until 23:53 after 3 failed runs: unexpected status 401 Unauthorized: sk-svcac******** \x1b]52;c;AAAA\x07 — run imd doctor"
    seen: list[str] = []

    def classify(text, *, invocation=None, cursor=None, seq=0):
        seen.append(text)
        return _stub_classify(text, invocation=invocation, cursor=cursor, seq=seq)

    thread, q = _thread(lambda st: ListLineSource([HB1, hostile, RawLine(ACC, cursor="c9", invocation="inv1")]),
                        redact_fn=redact, classify=classify)
    thread.run_once()
    lines = _drain(q)
    assert [l.seq for l in lines] == [1, 2, 3]
    assert seen[1] == hostile
    assert "sk-svcac" not in lines[1].text and "sk-[redacted]" in lines[1].text
    assert "\x1b" not in lines[1].text and "\x07" not in lines[1].text and "\u241b" in lines[1].text
    assert lines[2].cursor == "c9" and lines[2].invocation == "inv1"
    assert thread.state.cursor == "c9" and thread.state.invocation == "inv1"


def test_unstamped_line_never_moves_the_watermark():
    # header Review Focus #2 / spec §5.1 Mac transport: the watermark is the daemon's newest ISO stamp,
    # never Docker's -t stamp and never "last line seen"
    state = TailState(kind=KIND_DOCKER, last_ts_utc="2026-09-26T03:40:07.120Z", watermark_ts="2026-09-26T03:40:07.120Z")
    src = ListLineSource([HB2, NPM, HB1])          # newer, unstamped, then an OLDER re-delivered line
    src.kind = KIND_DOCKER
    thread, q = _thread(lambda st: src, state=state)
    thread.run_once()
    lines = _drain(q)
    assert [l.kind for l in lines] == ["heartbeat", "unknown", "heartbeat"]
    assert lines[1].ts == "" and lines[1].text == NPM
    assert state.last_ts_utc == "2026-09-26T03:40:37.121Z" == state.watermark_ts


def test_journald_cursor_moves_on_unstamped_unit_events_but_last_ts_does_not():
    state = TailState(kind=KIND_JOURNALD)
    src = ListLineSource([
        RawLine(HB1, cursor="c1", invocation="i1", realtime_us=1790394007120000),
        RawLine("Stopping imd-worker.service - IdentityMD worker daemon...", cursor="c2", invocation=None,
                realtime_us=1790394010000000),
    ])
    src.kind = KIND_JOURNALD
    thread, _ = _thread(lambda st: src, state=state)
    thread.run_once()
    assert state.cursor == "c2" and state.invocation == "i1" and state.last_ts_utc == "2026-09-26T03:40:07.120Z"
    assert state.watermark_ts is None and state.kind == KIND_JOURNALD


def test_thread_stamps_alive_at_without_lines():
    # spec §9 Follower: the thread stamps aliveAt every second even when no lines arrive
    clock = _Clock(1000.0)

    class _Ticks:
        kind = KIND_LIST

        def open(self): pass
        def close(self): pass
        def exit_code(self): return 0
        def backfill(self): return None

        def lines(self):
            for _ in range(3):
                clock.advance(ALIVE_STAMP_S)
                yield None

    thread, q = _thread(lambda st: _Ticks(), clock=clock)
    assert thread.alive_at is None
    thread.run_once()
    assert thread.alive_at == 1003.0 and q.empty()


def test_state_is_persisted_only_after_the_queue_is_drained_and_on_stop(tmp_path):
    # spec §9 Watermarks: persisted after each drained batch (the manager drains on the poll tick)
    path = tmp_path / TAIL_FILE
    clock = _Clock()

    class _Src:
        kind = KIND_LIST

        def open(self): pass
        def close(self): pass
        def exit_code(self): return None
        def backfill(self): return None

        def lines(self):
            yield RawLine(HB1, cursor="c1")
            yield None                                  # tick with a full queue -> no save
            saved_early.append(path.exists())
            while thread_ref[0]._queue.qsize():          # let the "manager" drain
                thread_ref[0]._queue.get_nowait()
            yield None                                  # tick with an empty queue -> save
            saved_after_drain.append(TailState.load(path).cursor)
            yield RawLine(HB2, cursor="c2")

    saved_early: list[bool] = []
    saved_after_drain: list[str | None] = []
    thread_ref: list[TailThread] = []
    thread, q = _thread(lambda st: _Src(), state_path=path, clock=clock)
    thread_ref.append(thread)
    thread.run_once()
    assert saved_early == [False] and saved_after_drain == ["c1"]
    assert TailState.load(path).cursor == "c2"           # exit persists regardless


def test_start_and_stop_run_the_source_on_a_daemon_thread(tmp_path):
    thread, q = _thread(lambda st: ListLineSource([HB1, HB2, ACC]), state_path=tmp_path / TAIL_FILE)
    thread.start()
    got = [q.get(timeout=5).text for _ in range(3)]
    thread.stop(timeout_s=5)
    assert got == [HB1, HB2, ACC]
    assert thread._thread is not None and not thread._thread.is_alive() and thread._thread.daemon
    assert thread.alive_at is not None
    assert TailState.load(tmp_path / TAIL_FILE).last_ts_utc == "2026-09-26T03:40:52.400Z"


def test_a_classify_that_raises_drops_the_line_and_keeps_the_follower():
    def classify(text, *, invocation=None, cursor=None, seq=0):
        if text == HB2:
            raise ValueError("hostile")
        return _stub_classify(text, invocation=invocation, cursor=cursor, seq=seq)

    thread, q = _thread(lambda st: ListLineSource([HB1, HB2, ACC]), classify=classify)
    thread.run_once()
    assert [l.text for l in _drain(q)] == [HB1, ACC]

# =============================================================================
# Task 3.7 -- docker behaviour in the thread: dedup, backfill discard (#31), prefix before classify
# =============================================================================


def _stale_body() -> list[str]:
    return [split_docker_prefix(line)[1] for line in _fixture_bytes("docker_stale_segment.log").decode().splitlines() if line]


FOLLOWER_0920 = [
    "2026-09-20T13:05:12.001Z alive 6h19m · idle · 5 submitted · fleet 62 online, 71 enrolled",
    "2026-09-20T13:05:42.002Z alive 6h20m · idle · 5 submitted · fleet 62 online, 71 enrolled",
]


def test_stale_backfill_is_discarded_not_a_gap():
    # spec §5.1 Mac transport (mutation proof #31): a --since backfill whose newest stamp is older than the
    # watermark is discarded whole -> sources.tail.reason = "backfill stale segment, discarded"; it is NOT a
    # gap footer and never resurrects old rows. Fixture docker_stale_segment.log is 3 h older than the follower.
    state = TailState(kind=KIND_DOCKER, last_ts_utc="2026-09-20T12:59:40.000Z", watermark_ts="2026-09-20T12:59:40.000Z")
    reason_while_following: list[str | None] = []

    class _Follower(ListLineSource):
        kind = KIND_DOCKER

        def lines(self):
            yield from super().lines()
            reason_while_following.append(holder[0].reason)   # what sources.tail.reason says while the follower runs

    holder: list[TailThread] = []
    src = _Follower(FOLLOWER_0920, backfill=_stale_body())
    thread, q = _thread(lambda st: src, state=state)
    holder.append(thread)
    thread.run_once()
    texts = [l.text for l in _drain(q)]
    assert texts == FOLLOWER_0920                     # not one 09:58–10:04 line reached the queue
    assert reason_while_following == [STALE_BACKFILL_REASON]
    assert thread.backfill_note == STALE_BACKFILL_REASON and thread.backfill_at == 1_790_000_000.0
    assert thread.gap_note is None
    assert state.watermark_ts == "2026-09-20T13:05:42.002Z" == state.last_ts_utc


def test_stale_backfill_through_docker_source_end_to_end():
    # the same rule with the real DockerLogsSource: the follower body (trusted) and the --since body (fixture)
    follower = "".join(f"2026-09-20T13:05:{12 + 30 * i:02d}.00{i + 1}00000Z {line}\n" for i, line in enumerate(FOLLOWER_0920)).encode()
    popen = ScriptedPopen([follower])
    run = ScriptedRun(stdout=_fixture_bytes("docker_stale_segment.log"))
    state = TailState(kind=KIND_DOCKER, last_ts_utc="2026-09-20T12:59:40.000Z", watermark_ts="2026-09-20T12:59:40.000Z")
    thread, q = _thread(docker_factory("imd-worker", popen=popen, run=run), state=state)
    thread.run_once()
    assert [l.text for l in _drain(q)] == FOLLOWER_0920
    assert thread.backfill_note == STALE_BACKFILL_REASON and thread.gap_note is None
    assert run.calls[0][0][:4] == ["docker", "logs", "--since", "2026-09-20T12:59:40.000Z"]
    assert popen.calls[0][0] == ["docker", "logs", "-f", "--tail", "200", "--timestamps", "imd-worker"]


def test_fresh_backfill_is_ingested_before_the_follower_lines():
    # the positive half of the discard rule: a body reaching up to the follower's window is history, in order
    body = ["2026-09-20T13:00:12.000Z alive 6h14m · idle · 5 submitted · fleet 62 online, 71 enrolled",
            "2026-09-20T13:04:42.000Z alive 6h18m · idle · 5 submitted · fleet 62 online, 71 enrolled"]
    state = TailState(kind=KIND_DOCKER, last_ts_utc="2026-09-20T12:59:40.000Z", watermark_ts="2026-09-20T12:59:40.000Z")
    src = ListLineSource(FOLLOWER_0920, backfill=body)
    src.kind = KIND_DOCKER
    thread, q = _thread(lambda st: src, state=state)
    thread.run_once()
    assert [l.text for l in _drain(q)] == body + FOLLOWER_0920
    assert thread.backfill_note is None and thread.gap_note is None
    assert thread.backfill_at == 1_790_000_000.0


def test_backfill_with_no_stamped_follower_line_is_judged_at_exit():
    state = TailState(kind=KIND_DOCKER, watermark_ts="2026-09-20T12:59:40.000Z", last_ts_utc="2026-09-20T12:59:40.000Z")
    src = ListLineSource([NPM], backfill=_stale_body())
    src.kind = KIND_DOCKER
    thread, q = _thread(lambda st: src, state=state)
    thread.run_once()
    assert [l.text for l in _drain(q)] == [NPM]
    assert thread.backfill_note == STALE_BACKFILL_REASON


def test_docker_timestamp_prefix_is_stripped_before_classify():
    # header Review Focus #2: a line with Docker's RFC3339Nano prefix but no daemon stamp classifies unknown,
    # goes to LOG only and never moves the watermark; the prefix never reaches classify()
    body = ("2026-09-26T03:40:07.123456789Z " + HB1 + "\n"
            "2026-09-26T03:40:08.000000001Z " + NPM + "\n"
            "2026-09-26T03:40:37.121999999Z " + HB2 + "\n").encode()
    seen: list[str] = []

    def classify(text, *, invocation=None, cursor=None, seq=0):
        seen.append(text)
        return _stub_classify(text, invocation=invocation, cursor=cursor, seq=seq)

    state = TailState(kind=KIND_DOCKER)
    thread, q = _thread(docker_factory("imd-worker", popen=ScriptedPopen([body]), run=ScriptedRun(stdout=b"")),
                        state=state, classify=classify)
    thread.run_once()
    assert seen == [HB1, NPM, HB2]
    assert not any(re.match(r"^\d{4}-\d\d-\d\dT[\d:.]+Z \d{4}-", t) for t in seen)
    lines = _drain(q)
    assert [l.kind for l in lines] == ["heartbeat", "unknown", "heartbeat"]
    assert state.watermark_ts == "2026-09-26T03:40:37.121Z"


def test_docker_reattach_dedups_redelivered_tail_lines_by_ts_and_text():
    # spec §5.1 Mac transport: dedup by (ts, text); `-f --tail 200` re-delivers the same 200 lines at every re-attach
    state = TailState(kind=KIND_DOCKER)
    first = ListLineSource([HB1, HB2], exit_code=1)
    second = ListLineSource([HB1, HB2, ACC], exit_code=1)
    first.kind = second.kind = KIND_DOCKER
    sources = iter([first, second])
    thread, q = _thread(lambda st: next(sources), state=state)
    thread.run_once()
    thread.run_once()
    assert [l.text for l in _drain(q)] == [HB1, HB2, ACC]
    assert thread.restarts == 2 and thread.reason == "tail: exited rc=1 — retry in 1s"


def test_dedup_set_is_bounded():
    state = TailState(kind=KIND_DOCKER)
    lines = [f"2026-09-26T{h:02d}:{m:02d}:{s:02d}.000Z alive 1m · idle · 0 submitted"
             for h in range(1, 3) for m in range(60) for s in range(0, 60, 3)]   # 2,400 distinct stamps
    src = ListLineSource(lines)
    src.kind = KIND_DOCKER
    thread, q = _thread(lambda st: src, state=state)
    thread.run_once()
    assert q.qsize() == 2400 and len(thread._seen) == DEDUP_KEYS_MAX

# =============================================================================
# Task 3.8 -- journald gap detection and the --since fallback
# =============================================================================


def test_vacuumed_cursor_is_detected_from_data_not_exit_code():
    # spec §5.1 VPS transport / §9 Watermarks: journalctl may seek to the closest surviving entry with exit 0
    # after a vacuum, so the FIRST record's __REALTIME_TIMESTAMP is compared with lastTsUtc; more than 60 s newer
    # -> gap note + the next attach is --since <lastTsUtc>. Fixture journal_vacuumed_cursor.jsonl starts 2 d later.
    popen = ScriptedPopen([_fixture_bytes("journal_vacuumed_cursor.jsonl"), _fixture_bytes("journal_json_records.jsonl")], rcs=[0, 0])
    state = TailState(kind=KIND_JOURNALD, cursor="s=00000000000000000000000000000001;i=7d0", last_ts_utc="2026-09-24T04:12:00.000Z",
                      invocation="a1b2c3d4e5f60718293a4b5c6d7e8f90")
    thread, q = _thread(journald_factory("imd-worker.service", popen=popen), state=state)
    thread.run_once()
    assert popen.calls[0][0][-2:] == ["--after-cursor", "s=00000000000000000000000000000001;i=7d0"]
    assert thread.gap_note == "gap 2026-09-24T04:12:00.000Z→2026-09-26T03:40:07.120Z"
    assert thread.reason == thread.gap_note
    assert q.empty()                                   # nothing from the mis-seeked attach was ingested
    assert state.cursor is None and state.last_ts_utc == "2026-09-24T04:12:00.000Z"
    assert thread.backoff_s == BACKOFF_MIN_S and thread.restarts == 1
    thread.run_once()
    argv = popen.calls[1][0]
    assert argv[-2:] == ["--since", "2026-09-24 04:12:00 UTC"] and "--after-cursor" not in argv
    assert q.qsize() == 9                             # the fallback attach delivers
    assert state.cursor is not None and state.last_ts_utc == "2026-09-26T03:41:37.123Z"
    assert thread.gap_note == "gap 2026-09-24T04:12:00.000Z→2026-09-26T03:40:07.120Z"   # the footer keeps the note


def test_after_cursor_attach_within_tolerance_is_not_a_gap():
    popen = ScriptedPopen([_fixture_bytes("journal_json_records.jsonl")])
    state = TailState(kind=KIND_JOURNALD, cursor="s=00000000000000000000000000000001;i=1ef", last_ts_utc="2026-09-26T03:39:30.000Z")
    thread, q = _thread(journald_factory(popen=popen), state=state)
    thread.run_once()
    assert thread.gap_note is None and q.qsize() == 9
    assert state.cursor.startswith("s=00000000000000000000000000000001;i=1f8;")   # the newest record's __CURSOR
    assert state.invocation == "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert thread.reason == "tail: exited rc=0 — retry in 1s"


def test_non_zero_exit_before_any_record_with_a_cursor_falls_back_to_since():
    # spec §5.1 VPS transport: "... or a non-zero exit, triggers the fallback --since <lastTsUtc>"
    popen = ScriptedPopen([b"Failed to seek to cursor: No such file or directory\n", b""], rcs=[1, 0])
    state = TailState(kind=KIND_JOURNALD, cursor="s=dead", last_ts_utc="2026-09-24T04:12:00.000Z")
    thread, _ = _thread(journald_factory(popen=popen), state=state)
    thread.run_once()
    assert thread.gap_note == "gap 2026-09-24T04:12:00.000Z→?"
    assert thread.reason == "tail: exited rc=1 — retry in 1s"
    assert state.cursor is None
    thread.run_once()
    assert popen.calls[1][0][-2:] == ["--since", "2026-09-24 04:12:00 UTC"]


def test_non_zero_exit_after_records_keeps_the_advanced_cursor():
    # a journald restart mid-stream is not a vacuum: the cursor moved with the records, re-attach after it
    popen = ScriptedPopen([_fixture_bytes("journal_json_records.jsonl")], rcs=[1])
    state = TailState(kind=KIND_JOURNALD, cursor="s=00000000000000000000000000000001;i=1ef", last_ts_utc="2026-09-26T03:39:30.000Z")
    thread, _ = _thread(journald_factory(popen=popen), state=state)
    thread.run_once()
    assert thread.gap_note is None and state.cursor is not None and state.cursor != "s=00000000000000000000000000000001;i=1ef"


def test_open_failure_is_a_reason_not_a_crash():
    def broken(argv, **kw):
        raise FileNotFoundError("journalctl")

    thread, _ = _thread(journald_factory(popen=broken))
    thread.run_once()
    assert thread.reason == "tail: open failed (journalctl) — retry in 1s"
    assert thread.restarts == 1

# =============================================================================
# Task 3.9 -- exit / backoff / reason; purity; opt-in host test
# =============================================================================


def test_dead_thread_reports_reason_and_backoff_ceiling_30s():
    # spec §9 Follower / §18 "tail thread dies silently": on exit the thread restarts with backoff 1->30 s
    # and reports `tail: exited rc=N — retry in Ns` through sources.tail.reason
    thread, _ = _thread(lambda st: ListLineSource([], exit_code=1))
    reasons = []
    for _ in range(7):
        thread.run_once()
        reasons.append(thread.reason)
    assert reasons == [f"tail: exited rc=1 — retry in {n}s" for n in (1, 2, 4, 8, 16, 30, 30)]
    assert thread.backoff_s == BACKOFF_MAX_S == 30 and thread.restarts == 7


def test_a_healthy_run_resets_the_backoff_and_clears_the_reason():
    calls = 0

    def factory(st):
        nonlocal calls
        calls += 1
        return ListLineSource([] if calls < 4 else [HB1], exit_code=1)

    thread, q = _thread(factory)
    for _ in range(3):
        thread.run_once()
    assert thread.backoff_s == 4
    thread.run_once()
    assert q.qsize() == 1 and thread.backoff_s == BACKOFF_MIN_S
    assert thread.reason == "tail: exited rc=1 — retry in 1s"        # set at exit, after the line cleared it


def test_loop_survives_a_factory_exception(tmp_path):
    def factory(st):
        raise RuntimeError("boom")

    thread, _ = _thread(factory)
    thread._stop.clear()
    calls = {"n": 0}

    def wait_once(seconds):
        calls["n"] += 1
        if calls["n"] >= 2:
            thread._stop.set()

    thread._wait = wait_once
    thread._loop()
    assert thread.reason.startswith("tail: crashed: boom — retry in") and thread.restarts == 2


def test_every_subprocess_call_has_a_timeout_or_stop_timeout_and_a_list_argv():
    # spec §14 Rules (3): data/seat_tail.py is one of two seat modules allowed subprocess; every run has
    # timeout=, every Popen owner documents stop_timeout_s, argv is a list, never shell=True
    source = Path(seat_tail.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_calls, popen_calls = [], []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        init = next((f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"), None)
        has_stop_timeout = init is not None and any(a.arg == "stop_timeout_s" for a in init.args.kwonlyargs + init.args.args)
        for node in ast.walk(cls):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            assert not any(k.arg == "shell" for k in node.keywords), ast.dump(node)
            if name in {"run", "_run"}:
                run_calls.append(node)
                assert any(k.arg == "timeout" for k in node.keywords), f"{cls.name}: {name} without timeout="
            if name in {"Popen", "_popen", "popen"}:
                popen_calls.append(node)
                assert has_stop_timeout, f"{cls.name} spawns without a stop_timeout_s"
            if name in {"run", "_run", "Popen", "_popen", "popen"}:
                first = node.args[0]
                assert isinstance(first, ast.List) or (isinstance(first, ast.Name) and first.id == "argv"), ast.dump(first)
    assert len(run_calls) == 1 and len(popen_calls) == 2
    assert "shell=True" not in source


def test_seat_tail_imports_no_textual_httpx_or_widgets():
    # spec §14 Rules (2)/(3): no Textual import under data/; the tail talks to nothing but the queue
    tree = ast.parse(Path(seat_tail.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:                              # module level only; TailThread.__init__ resolves WP2 lazily
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not any(n.startswith(("textual", "httpx", "rich", "maxpane_dashboard.widgets", "maxpane_dashboard.screens")) for n in names), names
    assert "maxpane_dashboard.data.seat_log_grammar" not in names   # resolved lazily in TailThread.__init__


@pytest.mark.host
def test_host_journald_source_follows_the_real_unit_for_two_seconds():
    """Opt-in only (`-m host`): the real journalctl, two seconds, no assertion on content."""
    if shutil.which("journalctl") is None:
        pytest.skip("no journalctl on this host")
    src = JournaldSource("imd-worker.service", since="-1h", stop_timeout_s=2.0)
    src.open()
    stop = threading.Timer(2.0, src.close)
    stop.start()
    try:
        count = sum(1 for item in src.lines() if item is not None)
    finally:
        stop.cancel()
    assert count >= 0


def test_unicode_backfill_preserves_one_lifecycle_record():
    payload = (FIXTURES.parent / "logs" / "unicode-lifecycle-mac.log").read_bytes()
    source = DockerLogsSource("imd-worker", watermark_ts="2026-09-26T00:00:00.000Z", run=lambda *a, **kw: subprocess.CompletedProcess([], 0, payload, b""))
    rows = source.backfill()
    assert len(rows) == 1 and "fix\u2028the parser" in rows[0].text


@pytest.mark.parametrize("objective", ["\u200b", "\u202e", "\x07", "sk-syntheticSecret1234\u202e"])
def test_raw_tail_classification_reaches_ledger_without_raw_fields(tmp_path, objective):
    from maxpane_dashboard.data.seat_log_grammar import classify, KIND_ACCEPTED_CODE
    from maxpane_dashboard.data.seat_ledger import SeatLedger
    raw = f"2026-09-26T01:52:50.000Z accepted implement 0c1f9727 — {objective} (max 40 turns)"
    thread, q = _thread(lambda st: ListLineSource([raw]), redact_fn=redact, classify=classify)
    thread.run_once()
    lines = _drain(q)
    assert len(lines) == 1 and lines[0].kind == KIND_ACCEPTED_CODE
    assert lines[0].text == redact(raw) and lines[0].fields["paths"] == redact(objective)
    ledger = SeatLedger(tmp_path / "ledger.sqlite", seat=7, now=lambda: 1790387570.0)
    ledger.ingest(lines)
    assert len(ledger.rows()) == 1
    import sqlite3
    with sqlite3.connect(tmp_path / "ledger.sqlite") as conn:
        dump = "\n".join(conn.iterdump())
    assert "syntheticSecret" not in dump and "\u200b" not in dump and "\u202e" not in dump and "\x07" not in dump
    ledger.close()
