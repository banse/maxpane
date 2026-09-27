"""Tests for ``maxpane_dashboard.analytics.seat_signals`` (PEPEPANE plan WP7).

Pure functions, injected clocks.  Pinned epochs (UTC):
  T0      = 1790394012.0  2026-09-26T03:40:12Z  (the healthy fixture's completedAtUtc)
  HB      = 1790394008.226  2026-09-26T03:40:08.226Z  (its newest heartbeat)
  START   = 1790336741.0  2026-09-25T11:45:41Z  (ActiveEnterTimestamp on #7)
  PAUSE_SEEN = 1790380552.0  2026-09-25T23:55:52Z  (the lingering `paused until 23:53` line, fill1 §5)
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import seat_signals as ss

REPO = Path(__file__).resolve().parents[2]
T0 = 1790394012.0
HB = 1790394008.226
START = 1790336741.0
PAUSE_SEEN = 1790380552.0


# ---------------------------------------------------------------------------
# Task 7.1 — constants and stamp helpers
# ---------------------------------------------------------------------------


def test_constants_are_the_contract_values():
    # contract §B analytics/seat_signals.py; spec §8 hero, §9 staleness constants, §6 rule 4, §5.2 grace
    assert ss.HEARTBEAT_STALE_S == 90 and ss.HEARTBEAT_DEAD_S == 300 and ss.TAIL_DEAD_S == 45
    assert ss.DISCONNECTED_BEATS_RED == 2 and ss.IDLE_WINDOW_S == 180
    assert ss.API_UNAVAILABLE_FAILURES == 3 and ss.API_UNAVAILABLE_S == 600
    assert ss.CONFIG_REWRITE_GRACE_S == 60 and ss.PLANE_PRESENCE_WINDOW_MS == 60000
    assert ss.AUTH_FAST_FAIL_S == 40 and ss.AUTH_CREDENTIAL_REFRESH_S == 3600
    assert ss.AGENT_SENTENCE_CAP == 160 and ss.ID_TRUNCATE_CHARS == 8
    assert ss.SOURCE_LIVE_S == 15 and ss.PAUSED_HINT_MAX_AGE_S == 330
    assert ss.VPS_GRACEFUL_STOP_TIMEOUT_S == 30 and ss.MAC_GRACEFUL_STOP_TIMEOUT_S == 45
    assert ss.DOCKER_DEFAULT_STOP_TIMEOUT_S == 10


def test_parse_iso_reads_z_ms_nanoseconds_offset_and_naive_as_utc():
    assert ss.parse_iso("2026-09-26T03:40:12Z") == T0
    assert ss.parse_iso("2026-09-26T03:40:08.226Z") == pytest.approx(HB)
    # Docker State.StartedAt is RFC3339 with NINE fractional digits (spec §5.5 Mac anchor)
    assert ss.parse_iso("2026-09-21T19:57:03.123456789Z") == pytest.approx(1790020623.123456)
    assert ss.parse_iso("2026-09-26T05:40:12+02:00") == T0
    assert ss.parse_iso("2026-09-26T03:40:12") == T0
    for bad in (None, "", "   ", "yesterday", 1790394012, True, "2026-09-26 03:11:29.985+00 extra"):
        assert ss.parse_iso(bad) is None


def test_parse_pg_timestamp_equals_seat_api_private():
    # WP5 deviation 1: the public copy must equal seat_api._parse_pg_timestamp on every input
    from maxpane_dashboard.data.seat_api import _parse_pg_timestamp

    cases = ("2026-09-26 03:11:29.985+00", "2026-09-26T03:11:29.985Z", "2026-09-26 03:11:29+02",
             "2026-09-26 03:11:29.5+05:30", "2026-09-26 03:11:29-0330", "2026-09-26T03:11:29.985", None, "", 7,
             "2026-13-01 00:00:00+00", "garbage", "2026-09-26 03:11:29.985+00 extra")
    for text in cases:
        assert ss.parse_pg_timestamp(text) == _parse_pg_timestamp(text), text
    assert ss.parse_pg_timestamp("2026-09-26 03:11:29.985+00") == pytest.approx(1790392289.985)


def test_iso_z_round_trips_and_day_utc_is_the_utc_date():
    assert ss.iso_z(T0) == "2026-09-26T03:40:12Z"
    assert ss.iso_z(HB, millis=True) == "2026-09-26T03:40:08.226Z"
    assert ss.parse_iso(ss.iso_z(START)) == START
    assert ss.day_utc(T0) == "2026-09-26"
    assert ss.day_utc(1790380799.0) == "2026-09-25" and ss.day_utc(1790380800.0) == "2026-09-26"


def test_as_of_hhmm_is_local_time_and_none_when_unusable():
    local = time.localtime(T0)
    assert ss.as_of_hhmm("2026-09-26T03:40:12Z") == f"{local.tm_hour:02d}:{local.tm_min:02d}"
    assert re.fullmatch(r"\d\d:\d\d", ss.as_of_hhmm("2026-09-26T03:40:12Z"))
    assert ss.as_of_hhmm(None) is None and ss.as_of_hhmm("garbage") is None
    assert ss.as_of_hhmm("1970-01-01T00:00:00Z") is None


def test_short_build_is_the_hash_after_the_plus():
    assert ss.short_build("0.1.0+5bfa8261") == "5bfa8261"
    assert ss.short_build("0.1.0+5bfa82612889abcdef") == "5bfa8261"
    assert ss.short_build("0.2.0") == "0.2.0"
    assert ss.short_build(None) is None and ss.short_build("") is None and ss.short_build(7) is None


def test_staleness_thresholds_are_inclusive_at_the_low_side():
    # spec §9: fresh below stale_s, stale from stale_s, dead from dead_s; unknown without a stamp
    assert ss.staleness("2026-09-26T03:40:08Z", now=T0, stale_s=90, dead_s=300) == "fresh"
    assert ss.staleness(ss.iso_z(T0 - 90), now=T0, stale_s=90, dead_s=300) == "stale"
    assert ss.staleness(ss.iso_z(T0 - 299), now=T0, stale_s=90, dead_s=300) == "stale"
    assert ss.staleness(ss.iso_z(T0 - 300), now=T0, stale_s=90, dead_s=300) == "dead"
    assert ss.staleness(None, now=T0, stale_s=90, dead_s=300) == "unknown"
    assert ss.staleness("nope", now=T0, stale_s=90, dead_s=300) == "unknown"
    assert ss.staleness(ss.iso_z(T0 + 30), now=T0, stale_s=90, dead_s=300) == "fresh", "a future stamp is not stale"


def test_verdict_lag_rounds_and_refuses_the_impossible():
    # spec §6: acceptedAt is Postgres text, storedUtc ISO ms; the healthy fixture's row 0 is 900 s
    assert ss.verdict_lag_s(stored_utc="2026-09-26T03:24:17.236Z", accepted_at_api="2026-09-26T03:39:17Z") == 900
    assert ss.verdict_lag_s(stored_utc="2026-09-26T03:10:20.985Z", accepted_at_api="2026-09-26 03:11:29.985+00") == 69
    assert ss.verdict_lag_s(stored_utc=None, accepted_at_api="2026-09-26T03:39:17Z") is None
    assert ss.verdict_lag_s(stored_utc="2026-09-26T03:24:17.236Z", accepted_at_api=None) is None
    assert ss.verdict_lag_s(stored_utc="2026-09-26T03:39:17Z", accepted_at_api="2026-09-26T03:24:17Z") is None, "a verdict before the store is skew, not a lag"


@pytest.mark.guard
def test_seat_signals_imports_are_pure():
    # spec §14 purity rule (2): no Textual/rich, subprocess, socket, httpx; only seat_redact from the package
    tree = ast.parse((REPO / "maxpane_dashboard" / "analytics" / "seat_signals.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    froms: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
            froms.add(node.module or "")
    assert modules.isdisjoint({"textual", "rich", "subprocess", "socket", "httpx"}), modules
    assert {m for m in froms if m.startswith("maxpane_dashboard")} <= {"maxpane_dashboard.analytics.seat_redact"}


# ---------------------------------------------------------------------------
# Task 7.2 — offline (two beats), tail liveness, lingering pause, counters
# ---------------------------------------------------------------------------


def test_offline_needs_two_beats():
    # spec §6 rule 3 / §14 mutation proof 15: one `disconnected` beat is a redeploy wave, not an offline seat
    assert ss.offline_state(consecutive_disconnected_beats=1, presence_connected=True, heartbeat_age_s=4) is False
    assert ss.offline_state(consecutive_disconnected_beats=1, presence_connected=None, heartbeat_age_s=31) is False
    assert ss.offline_state(consecutive_disconnected_beats=2, presence_connected=True, heartbeat_age_s=4) is True
    assert ss.offline_state(consecutive_disconnected_beats=5, presence_connected=None, heartbeat_age_s=None) is True
    assert ss.offline_state(consecutive_disconnected_beats=0, presence_connected=True, heartbeat_age_s=4) is False


def test_offline_from_the_plane_needs_a_stale_heartbeat_too():
    # spec §9: HEARTBEAT_DEAD_S (300) red `offline` only together with presence.connected == false; a 91-299 s heartbeat is amber, not red
    assert ss.offline_state(consecutive_disconnected_beats=0, presence_connected=False, heartbeat_age_s=300) is True
    assert ss.offline_state(consecutive_disconnected_beats=0, presence_connected=False, heartbeat_age_s=299) is False
    assert ss.offline_state(consecutive_disconnected_beats=0, presence_connected=False, heartbeat_age_s=91) is False
    assert ss.offline_state(consecutive_disconnected_beats=0, presence_connected=False, heartbeat_age_s=None) is False
    assert ss.offline_state(consecutive_disconnected_beats=None, presence_connected=None, heartbeat_age_s=None) is None
    assert ss.offline_state(consecutive_disconnected_beats=None, presence_connected=True, heartbeat_age_s=4) is False


def test_tail_state_is_dead_after_45s_without_a_stamp():
    # spec §9: TAIL_DEAD_S = 45 without a thread aliveAt -> sources.tail.ok = false
    assert ss.tail_state(alive_at=T0 - 1, now=T0) == (True, None)
    assert ss.tail_state(alive_at=T0 - 45, now=T0) == (True, None)
    ok, reason = ss.tail_state(alive_at=T0 - 46, now=T0)
    assert ok is False and reason == "tail dead 46 s — restarting"
    assert ss.tail_state(alive_at=None, now=T0) == (False, "tail thread not running")


def test_pausedhint_active_only_while_until_is_ahead_and_the_hint_is_fresh():
    # fill1 §5: `23:55:52 … 1 task running · paused until 23:53` lingers after the pause (the suffix is 5 min stale)
    hint = {"until": "23:53", "failedRuns": 3, "reason": "unexpected status 401 Unauthorized", "seenUtc": "2026-09-25T23:55:52.000Z"}
    assert ss.pausedhint_active(hint, now=PAUSE_SEEN + 8) is False            # 23:56:00 > 23:53
    fresh = dict(hint, seenUtc="2026-09-25T23:41:22.577Z")
    assert ss.pausedhint_active(fresh, now=1790379700.0) is True              # 23:41:40 < 23:53
    assert ss.pausedhint_active(fresh, now=1790379700.0 + ss.PAUSED_HINT_MAX_AGE_S + 1) is False, "a hint older than 5.5 min is not evidence"
    # midnight wrap: seen 23:58, until 00:10 -> next day
    wrap = dict(hint, until="00:10", seenUtc="2026-09-25T23:58:00Z")
    assert ss.pausedhint_active(wrap, now=1790380800.0 - 60) is True          # 23:59
    assert ss.pausedhint_active(wrap, now=1790380800.0 + 660) is False        # 00:11
    assert ss.pausedhint_active(None, now=T0) is False
    assert ss.pausedhint_active({"until": "nope"}, now=T0) is False
    assert ss.pausedhint_active({"until": "23:53"}, now=PAUSE_SEEN - 600) is True, "without seenUtc the hint is dated now"


def test_counters_consistent_checks_the_identity_and_never_repairs_it():
    # spec §6: attempts == accepted + rejected + failed + pending (417/417 seats); 244+5+11+28 = 288
    assert ss.counters_consistent({"attempts": 288, "accepted": 244, "rejected": 5, "failed": 11, "pending": 28}) is True
    assert ss.counters_consistent({"attempts": 290, "accepted": 244, "rejected": 5, "failed": 11, "pending": 28}) is False
    assert ss.counters_consistent({"attempts": 288, "accepted": 244, "rejected": 5, "failed": 11}) is None
    assert ss.counters_consistent({"attempts": "288", "accepted": 244, "rejected": 5, "failed": 11, "pending": 28}) is None
    assert ss.counters_consistent(None) is None and ss.counters_consistent({}) is None


def test_pausedhint_active_equals_seat_auth_rule():
    # WP4 open question 7: seat_auth.pause_hint_active (the auth reason) restates this rule (the hero amber); one rule, bound here
    from maxpane_dashboard.analytics import seat_auth

    assert ss.PAUSED_HINT_MAX_AGE_S == seat_auth.PAUSED_HINT_MAX_AGE_S
    seen = "2026-09-25T23:36:37.000Z"
    base = ss.parse_iso(seen)
    for hint in ({"until": "23:53", "seenUtc": seen}, {"until": "00:10", "seenUtc": seen}, {"until": "23:30", "seenUtc": seen},
                 {"until": "23:53"}, {"until": "25:00", "seenUtc": seen}, None, {"until": 5}):
        for dt in (0, 60, 329, 331, 1200, 3600):
            assert ss.pausedhint_active(hint, now=base + dt) == seat_auth.pause_hint_active(hint, now=base + dt), (hint, dt)
