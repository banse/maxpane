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


# ---------------------------------------------------------------------------
# Task 7.3 — config-changed grace, graceful stop, divergence, today rollup
# ---------------------------------------------------------------------------


def test_start_time_rewrite_is_not_a_change():
    # spec §5.2 / §14 mutation proof 16: the daemon rewrites config.json at every start (both seats pass
    # --concurrency), so an mtime inside anchor + 60 s is the start itself, not an operator edit.
    # systemd anchor: ActiveEnterTimestamp 2026-09-25 11:45:41 UTC vs mtime `Sep 25 11:45` (minute resolution, vps §1)
    anchor = "2026-09-25T11:45:41Z"
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T11:45:00Z", anchor_utc=anchor) is False
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T11:45:41Z", anchor_utc=anchor) is False
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T11:46:41Z", anchor_utc=anchor) is False   # exactly +60 s
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T11:46:42Z", anchor_utc=anchor) is True    # +61 s
    # Docker anchor: State.StartedAt with nanoseconds (spec §5.5 Mac)
    started = "2026-09-21T19:57:03.123456789Z"
    assert ss.config_changed_since_start(mtime_utc="2026-09-21T19:57:03Z", anchor_utc=started) is False
    assert ss.config_changed_since_start(mtime_utc="2026-09-21T19:58:03Z", anchor_utc=started) is False   # +59.88 s
    assert ss.config_changed_since_start(mtime_utc="2026-09-21T19:58:04Z", anchor_utc=started) is True
    # an edit long after the start; an mtime before the start (restored backup) is not a change either
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T14:00:00Z", anchor_utc=anchor) is True
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T09:00:00Z", anchor_utc=anchor) is False
    assert ss.config_changed_since_start(mtime_utc=None, anchor_utc=anchor) is None
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T14:00:00Z", anchor_utc=None) is None
    assert ss.config_changed_since_start(mtime_utc="garbage", anchor_utc=anchor) is None
    assert ss.config_changed_since_start(mtime_utc="2026-09-25T11:45:50Z", anchor_utc=anchor, grace_s=0) is True


def test_graceful_stop_possible_on_both_hosts():
    # spec §5.5: systemd KillMode=control-group and TimeoutStopSec >= 30 -> true on #7;
    # docker StopTimeout >= 45 or Init -> false today (StopTimeout null = 10, no init)
    assert ss.graceful_stop_possible(kill_mode="control-group", stop_timeout_s=30) is True
    assert ss.graceful_stop_possible(kill_mode="control-group", stop_timeout_s=29) is False
    assert ss.graceful_stop_possible(kill_mode="mixed", stop_timeout_s=90) is False
    assert ss.graceful_stop_possible(kill_mode="control-group", stop_timeout_s=None) is None
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=30) is None
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=None, docker_stop_timeout_s=None, docker_init=False) is False
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=None, docker_stop_timeout_s=10, docker_init=False) is False
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=None, docker_stop_timeout_s=45, docker_init=False) is True
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=None, docker_stop_timeout_s=10, docker_init=True) is True
    assert ss.graceful_stop_possible(kill_mode=None, stop_timeout_s=None) is None


def test_divergence_compares_local_stored_with_plane_rows():
    # spec §7 today.divergence / §8 LEDGER footer: the grammar-drift detector
    assert ss.divergence(local_stored_today=11, plane_rows_submitted_today=11) == {"localStored": 11, "planeRowsSubmittedToday": 11, "ok": True}
    assert ss.divergence(local_stored_today=57, plane_rows_submitted_today=55) == {"localStored": 57, "planeRowsSubmittedToday": 55, "ok": False}
    assert ss.divergence(local_stored_today=None, plane_rows_submitted_today=11) is None
    assert ss.divergence(local_stored_today=11, plane_rows_submitted_today=None) is None


def _row(node8, accepted, *, stored=True, duration=30.0, outcome=None, lag=None, outcome_as_of=None):
    return {
        "nodeId8": node8, "acceptedUtc": accepted, "storedUtc": accepted if stored else None,
        "durationS": duration, "outcome": outcome, "verdictLagS": lag, "outcomeAsOfUtc": outcome_as_of,
    }


def test_rollup_today_counts_only_the_day_and_never_sums_axes():
    # spec §7 today block; spec §2 "three outcome axes, never summed": tasks/stored are local, verdicts are api
    rows = [
        _row("aaaaaaaa", "2026-09-26T03:23:44.909Z", duration=32.2, outcome="accepted", lag=900, outcome_as_of="2026-09-26T03:40:10Z"),
        _row("bbbbbbbb", "2026-09-26T02:10:00.000Z", duration=252.0, outcome="pending", outcome_as_of="2026-09-26T03:40:10Z"),
        _row("cccccccc", "2026-09-26T01:00:00.000Z", duration=28.0, outcome="failed", outcome_as_of="2026-09-26T03:30:00Z"),
        _row("dddddddd", "2026-09-26T00:30:00.000Z", stored=False, duration=0.4, outcome="unknown"),
        _row("eeeeeeee", "2026-09-25T23:36:03.545Z", duration=34.1, outcome="failed", outcome_as_of="2026-09-26T03:40:10Z"),   # yesterday
        {"nodeId8": "ffffffff", "acceptedUtc": None},                                                                          # unusable
        "not a row",
    ]
    today = ss.rollup_today(rows, day_utc="2026-09-26")
    assert tuple(today) == ("dayUtc", "tasks", "stored", "notStored", "p50S", "longestS", "accepted", "rejected",
                            "failed", "pending", "verdictLagP50S", "verdictsAsOfUtc")
    assert today["dayUtc"] == "2026-09-26" and today["tasks"] == 4 and today["stored"] == 3 and today["notStored"] == 1
    assert today["p50S"] == 30 and today["longestS"] == 252
    assert (today["accepted"], today["rejected"], today["failed"], today["pending"]) == (1, 0, 1, 1)
    assert today["verdictLagP50S"] == 900 and today["verdictsAsOfUtc"] == "2026-09-26T03:40:10Z"
    empty = ss.rollup_today([], day_utc="2026-09-26")
    assert empty["tasks"] == 0 and empty["stored"] == 0 and empty["p50S"] is None and empty["longestS"] is None
    assert empty["accepted"] is None and empty["verdictLagP50S"] is None and empty["verdictsAsOfUtc"] is None
    # a day with rows but no verdict yet: counts are 0 (rows exist, none judged), never None
    unjudged = ss.rollup_today([_row("aaaaaaaa", "2026-09-26T03:23:44.909Z", outcome="unknown")], day_utc="2026-09-26")
    assert (unjudged["accepted"], unjudged["rejected"], unjudged["failed"], unjudged["pending"]) == (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Task 7.4 — hero precedence, source words, gate preview
# ---------------------------------------------------------------------------


def _flat(**over):
    base = {
        "seat_daemon_state": "alive", "seat_daemon_heartbeat_age_s": 4, "seat_daemon_consecutive_disconnected_beats": 0,
        "seat_daemon_paused_hint": None, "seat_standing_paused_until": None, "seat_standing_presence_connected": True,
        "seat_standing_heartbeat_age_ms": 4100, "seat_auth_degraded": False, "seat_control_restart_required": False,
        "seat_unit_active_state": "active", "seat_host_kind": "systemd",
        "seat_sources": {
            "tail": {"ok": True, "asOfUtc": "2026-09-26T03:40:11Z", "reason": None, "threadAliveAt": "2026-09-26T03:40:11Z"},
            "unit": {"ok": True, "asOfUtc": "2026-09-26T03:40:11Z", "reason": None},
        },
    }
    base.update(over)
    return base


def test_hero_is_green_on_the_healthy_flat_dict_and_red_beats_amber():
    # spec §8 HERO: precedence red > amber > green
    assert ss.hero_state(_flat(), now=T0) == ("green", [])
    state, reasons = ss.hero_state(_flat(seat_daemon_consecutive_disconnected_beats=2, seat_auth_degraded=True), now=T0)
    assert state == "red" and reasons[0] == "disconnected 2 beats" and "runtime auth degraded" in reasons
    assert ss.hero_state(_flat(seat_daemon_consecutive_disconnected_beats=1), now=T0) == ("green", [])
    assert ss.hero_state(_flat(seat_unit_active_state="inactive"), now=T0)[0] == "red"
    assert "unit inactive" in ss.hero_state(_flat(seat_unit_active_state="failed"), now=T0)[1]
    assert ss.hero_state(_flat(seat_host_kind="docker", seat_unit_active_state="exited"), now=T0) == ("red", ["container not running"])
    assert ss.hero_state(_flat(seat_unit_active_state=None), now=T0) == ("green", []), "an unknown unit is UNIT amber, never hero red (spec §9 docker equivalent)"


def test_hero_red_on_a_dead_or_exited_tail():
    # spec §9: TAIL_DEAD_S = 45 without aliveAt -> hero red; an exited follower is red while it backs off
    dead = _flat(seat_sources={"tail": {"ok": False, "asOfUtc": "2026-09-26T03:39:20Z", "reason": "tail: exited rc=1 — retry in 8s",
                                         "threadAliveAt": "2026-09-26T03:39:20Z"}, "unit": {"ok": True, "asOfUtc": "2026-09-26T03:40:11Z"}})
    state, reasons = ss.hero_state(dead, now=T0)
    assert state == "red" and reasons[0] == "tail dead 52 s"
    exited = _flat(seat_sources={"tail": {"ok": False, "asOfUtc": "2026-09-26T03:40:11Z", "reason": "tail: exited rc=1 — retry in 2s",
                                           "threadAliveAt": "2026-09-26T03:40:11Z"}, "unit": {"ok": True}})
    assert ss.hero_state(exited, now=T0) == ("red", ["tail exited"])
    never = _flat(seat_sources={"tail": {"ok": False, "asOfUtc": None, "reason": "tail thread not running", "threadAliveAt": None},
                                 "unit": {"ok": True}})
    assert ss.hero_state(never, now=T0)[0] == "green", "a tail that never started is not a dead tail (--once)"


def test_hero_amber_reasons():
    # spec §8: amber if heartbeatAgeS > 90, pausedUntil in the future, auth degraded, restartRequired
    assert ss.hero_state(_flat(seat_daemon_heartbeat_age_s=91, seat_standing_presence_connected=None), now=T0) == ("amber", ["heartbeat 91 s old"])
    assert ss.hero_state(_flat(seat_daemon_heartbeat_age_s=90), now=T0) == ("green", [])
    # spec §9: stale heartbeat but the plane sees us within its 60 s window -> a tail problem, still amber, named
    assert ss.hero_state(_flat(seat_daemon_heartbeat_age_s=120, seat_standing_presence_connected=True, seat_standing_heartbeat_age_ms=4100), now=T0) == (
        "amber", ["heartbeat 120 s old", "plane sees us · local tail stale"])
    assert ss.hero_state(_flat(seat_standing_paused_until="2026-09-26T03:53:00Z"), now=T0) == ("amber", [f"paused until {ss.as_of_hhmm('2026-09-26T03:53:00Z')}"])  # local HH:MM, like every as-of
    assert ss.hero_state(_flat(seat_standing_paused_until="2026-09-26T03:30:00Z"), now=T0) == ("green", []), "a past pausedUntil is history"
    assert ss.hero_state(_flat(seat_auth_degraded=True), now=T0) == ("amber", ["runtime auth degraded"])
    assert ss.hero_state(_flat(seat_control_restart_required=True), now=T0) == ("amber", ["restart required"])
    # spec §6 rule 3 second clause / §9 HEARTBEAT_DEAD_S: presence.connected false with a dead (>= 300 s) heartbeat is red offline;
    # the same plane word with a merely stale heartbeat stays amber
    assert ss.hero_state(_flat(seat_daemon_heartbeat_age_s=300, seat_standing_presence_connected=False), now=T0)[0] == "red"
    assert ss.hero_state(_flat(seat_daemon_heartbeat_age_s=120, seat_standing_presence_connected=False), now=T0) == ("amber", ["heartbeat 120 s old"])


def test_lingering_pause_suffix_does_not_amber_after_until():
    # header Review Focus 3 / fill1 §5: `23:55:52 1 task running · paused until 23:53` -- the suffix alone never ambers once `until` passed
    hint = {"until": "23:53", "failedRuns": 3, "reason": "unexpected status 401 Unauthorized", "seenUtc": "2026-09-25T23:55:52.000Z"}
    flat = _flat(seat_daemon_paused_hint=hint, seat_standing_paused_until=None)
    assert ss.hero_state(flat, now=PAUSE_SEEN + 8) == ("green", [])
    active = _flat(seat_daemon_paused_hint=dict(hint, seenUtc="2026-09-25T23:41:22.577Z"), seat_standing_paused_until=None)
    assert ss.hero_state(active, now=1790379700.0) == ("amber", ["paused until 23:53"])
    # standing.pausedUntil is the truth when both exist
    both = _flat(seat_daemon_paused_hint=hint, seat_standing_paused_until="2026-09-25T23:53:00Z")
    assert ss.hero_state(both, now=PAUSE_SEEN + 8) == ("green", [])


def test_hero_reads_the_v2_document_too_and_is_none_without_evidence():
    # contract deviation 2: None when neither the tail nor the unit source has ever answered
    import json
    from pathlib import Path
    doc = json.loads((REPO / "tests" / "fixtures" / "seat" / "status" / "status_v2_healthy.json").read_text(encoding="utf-8"))
    assert ss.hero_state(doc, now=T0) == ("green", [])
    dead = json.loads((REPO / "tests" / "fixtures" / "seat" / "status" / "status_v2_tail_dead.json").read_text(encoding="utf-8"))
    assert ss.hero_state(dead, now=T0)[0] == "red"
    assert ss.hero_state({}, now=T0) == (None, [])
    assert ss.hero_state({"schemaVersion": 2, "sources": {"tail": {"ok": None}, "unit": {"ok": None}}}, now=T0) == (None, [])


def test_source_word():
    # spec §8 degraded wording inputs: live | as of HH:MM | unavailable (reason) | local only
    live = {"ok": True, "asOfUtc": ss.iso_z(T0 - 4), "reason": None, "unavailable": False}
    assert ss.source_word(live, now=T0) == "live"
    old = {"ok": True, "asOfUtc": ss.iso_z(T0 - 302), "reason": None, "unavailable": False}
    assert ss.source_word(old, now=T0) == f"as of {ss.as_of_hhmm(ss.iso_z(T0 - 302))}"
    last_good = {"ok": False, "asOfUtc": ss.iso_z(T0 - 92), "reason": "timeout 20 s", "unavailable": False}
    assert ss.source_word(last_good, now=T0) == f"as of {ss.as_of_hhmm(ss.iso_z(T0 - 92))}"
    gone = {"ok": False, "asOfUtc": ss.iso_z(T0 - 700), "reason": "HTTP 500 ×3", "unavailable": True}
    assert ss.source_word(gone, now=T0) == "unavailable (HTTP 500 ×3)"
    assert ss.source_word({"ok": False, "asOfUtc": None, "reason": None, "unavailable": True}, now=T0) == "unavailable (no reason given)"
    assert ss.source_word({"ok": None, "asOfUtc": None, "reason": None, "unavailable": False}, now=T0) == "unavailable (not read yet)"
    assert ss.source_word({"ok": None, "asOfUtc": None, "reason": "document refused (with_secret)", "unavailable": True}, now=T0) == "unavailable (document refused (with_secret))"
    assert ss.source_word(None, now=T0) == "local only"


def test_gate_preview_words_and_colours():
    # spec §8 GATE box
    gate = {"idleBeats": 9, "idleBeatsRequired": 4, "planeRunning": 0, "planeAsOfUtc": "2026-09-26T03:40:09Z", "planeMode": "plane+local",
            "lastLifecycleLine": "2026-09-26T03:24:17.136Z submitted implement for 0c1f9727", "lifecycleOpen": False,
            "outboxFiles": 0, "unitActive": True, "safe": True, "reason": None}
    assert ss.gate_preview(gate, broker_reachable=True) == ("safe to restart", "green")
    assert ss.gate_preview(dict(gate, safe=False, reason="task running 0c1f9727 · 0:42"), broker_reachable=True) == ("task running 0c1f9727 · 0:42", "red")
    assert ss.gate_preview(dict(gate, safe=False, reason="idle 2/4 beats"), broker_reachable=True) == ("idle 2/4 beats", "amber")
    assert ss.gate_preview(dict(gate, planeMode="local-only"), broker_reachable=True) == ("plane unreachable · local-only gate", "amber")
    assert ss.gate_preview(dict(gate, safe=False, outboxFiles=None, reason="gate unknown: outbox unreadable"), broker_reachable=True) == ("gate unknown: outbox unreadable", "red")
    assert ss.gate_preview(gate, broker_reachable=False) == ("broker unreachable — read-only", "amber")
    assert ss.gate_preview(None, broker_reachable=True) == ("gate unknown", "amber")
    assert ss.gate_preview(gate, broker_reachable=None) == ("broker unreachable — read-only", "amber")
    drain = {"armedAtUtc": "2026-09-26T03:02:00Z", "idleBeats": 2, "rearmed": 1, "expiresAtUtc": "2026-09-26T07:02:00Z"}
    assert ss.gate_preview(gate, broker_reachable=True, drain=drain) == (f"drain armed {ss.as_of_hhmm('2026-09-26T03:02:00Z')} · 2/4 idle beats", "amber")
    flight = {"verb": "restart", "planId": "7f3a9c1e2b4d6081", "sinceUtc": "2026-09-26T03:40:30Z"}
    assert ss.gate_preview(gate, broker_reachable=True, in_flight=flight) == ("restart in flight (plan 7f3a) · verifying", "amber")
