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
