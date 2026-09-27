"""NOW and LOG (spec §8 NOW, §8 LOG; contract §C.15).

NOW is five ``.panel-line`` Statics: the task, the plane's view of it, the agent's
own sentence, the queue line and the auth line. LOG is a ``RichLogFeed`` that is
**append-only by seq**: a poll never clears what an earlier poll wrote (spec §9,
contract decision on ``render_events``).

Mutation proofs (spec §14): ``test_control_codes_never_reach_a_strip`` (proof 23) --
drop the redactor's control-character step, or paint the sentence without
``redact_agent_sentence`` -> red; ``test_masked_key_never_reaches_a_strip`` (proof 12,
strip half for NOW and LOG) -- paint a reason or a log line without ``redact`` -> red;
``test_seat_log_is_append_only_across_polls`` -- replace ``SeatLog.render_events`` with
the base's clear-and-repaint -> red.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import RichLog

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES, fold_status_document
from maxpane_dashboard.widgets.seat.now import QUIET_NETWORK, SeatNow
from tests.widgets.test_seat_hero import composite_lines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
NOW_SIGNATURE = SEAT_WIDGET_SIGNATURES["SeatNow"]
SIZE = (120, 9)
WIDE = (200, 9)

#: A ``working:`` line carrying OSC 52 / OSC 0 escapes and U+202E (spec §13, synthetic fixture).
CONTROL_LINES = [line for line in (FIXTURES / "grammar" / "control_chars.txt").read_text(encoding="utf-8").splitlines()
                 if "working:" in line]
#: The real masked fragment the 09-25 heartbeat carried (spec §13; fixture kept on purpose).
MASKED_LINE = next(line for line in (FIXTURES / "grammar" / "heartbeat_paused_401.txt").read_text(encoding="utf-8").splitlines()
                   if "sk-svcac" in line)
FORBIDDEN = {chr(c) for c in range(0x20) if c not in (0x09, 0x0A)} | {"\x7f", "‮", "‭", "⁦"}


def _healthy(**overrides) -> dict:
    flat = fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))
    payload = {key: copy.deepcopy(flat[key]) for key in NOW_SIGNATURE}
    payload.update(overrides)
    return payload


def _source(payload: dict, name: str, **fields) -> dict:
    payload["seat_sources"] = copy.deepcopy(payload["seat_sources"])
    payload["seat_sources"][name].update(fields)
    return payload


async def _now(size=SIZE, **payload) -> list[str]:
    return await composite_lines(SeatNow, size, css_path=CSS_PATH, region_only=True, **payload)


def _line(rows: list[str], index: int) -> str:
    """Content line *index* (0 = task line): row 0 is the title, row 1 the blank row."""
    return rows[2 + index].strip()


CURRENT = {"nodeId8": "0c1f9727", "jobId": "b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70", "role": "implement", "kind": "code",
           "phase": "working", "startedUtc": "2026-09-26T03:23:44.909Z", "elapsedS": 42, "maxTurns": 60, "model": "gpt-6-luna",
           "tierDerived": "economy/standard", "lastMessage": "Created artifacts/answer.json", "lastMessageUtc": "2026-09-26T03:24:10Z",
           "planeSince": "2026-09-26T03:23:41Z", "objective": "Assess the oracle answer for job b1fb1439", "nodeKey": "oracle_assess"}
RUNNING = [{"jobId": "b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70", "objective": "Assess the oracle answer for job b1fb1439",
            "nodeKey": "oracle_assess", "role": "implement", "since": "2026-09-26T03:23:41Z"}]


# -- shape ---------------------------------------------------------------------------------


def test_now_has_five_named_lines():
    assert SeatNow.LINE_IDS == ("seat-now-task", "seat-now-plane", "seat-now-sentence", "seat-now-queue", "seat-now-auth")
    assert SeatNow.TITLE == "NOW"


async def test_no_args_and_all_none_render_without_raising():
    # ``composite_lines`` always calls ``update_data(**kwargs)``, so the no-argument call is the all-None call:
    # both paint the idle wording, never the Loading placeholder.
    rows = await _now()
    assert rows[0].strip().startswith("NOW") and "Loading" not in "\n".join(rows)
    rows = await _now(**{k: None for k in NOW_SIGNATURE})
    assert rows[0].strip().startswith("NOW") and "Loading" not in "\n".join(rows)


# -- the four states of the task line -----------------------------------------------------


async def test_idle_names_the_last_task_its_hash_and_its_verdict_lag():
    rows = await _now(WIDE, **_healthy())
    task = _line(rows, 0)
    assert task.startswith("idle since ") and "last 0c1f9727 stored c4d9714ffb95 → accepted (+15m)" in task, task
    assert _line(rows, 3) == "queue: 27 ready · 0 eligible · blocked: at capacity 27"
    assert _line(rows, 4) == "" and _line(rows, 2) == ""


async def test_working_reads_the_task_the_plane_and_the_sentence():
    rows = await _now(WIDE, **_healthy(seat_current=CURRENT, seat_daemon_work="1 task running", seat_standing_running=RUNNING))
    assert _line(rows, 0) == "0c1f9727 · implement · working · 42 s of max 60 turns · on gpt-6-luna (~economy/standard)"
    assert _line(rows, 1).startswith('oracle_assess · "Assess the oracle answer for job b1fb1439" · api ')
    assert _line(rows, 2) == "» Created artifacts/answer.json"


async def test_a_plane_assignment_without_the_daemon_line_yet_says_so():
    rows = await _now(WIDE, **_healthy(seat_standing_running=RUNNING))
    assert _line(rows, 0) == "plane assigned oracle_assess — waiting for the daemon line"
    assert _line(rows, 1).startswith('oracle_assess · "Assess the oracle answer')


async def test_a_dead_tail_reads_unavailable_with_the_reason():
    rows = await _now(WIDE, **_source(_healthy(), "tail", ok=False, reason="exited rc=1 — retry in 4s"))
    assert _line(rows, 0) == "unavailable (tail: exited rc=1 — retry in 4s)"


# -- the queue line ------------------------------------------------------------------------


async def test_an_empty_queue_says_the_network_is_quiet_not_this_machine():
    queue = {"ready": 0, "eligible": 0, "fleetOnline": 396, "blocked": [], "asOfUtc": "2026-09-26T03:40:09Z"}
    rows = await _now(WIDE, **_healthy(seat_queue=queue))
    assert _line(rows, 3) == f"queue: nothing waiting · 396 online — {QUIET_NETWORK}"
    assert QUIET_NETWORK == "the network is quiet, not this machine"


async def test_the_queue_line_is_unavailable_from_the_api_and_absent_offline():
    down = _source(_healthy(seat_queue=None), "standing", ok=False, reason="HTTP 500", failures=3, unavailable=True)
    rows = await _now(WIDE, **down)
    assert _line(rows, 3) == "queue: unavailable (api)"
    offline = await _now(WIDE, **_healthy(seat_queue=None, seat_offline=True))
    assert "queue:" not in "\n".join(offline)


# -- the auth line -------------------------------------------------------------------------


async def test_the_auth_line_names_the_reasons_and_the_refreshed_credential_file():
    rows = await _now(WIDE, **_healthy(seat_auth_degraded=True, seat_auth_reasons=["paused after 3 failed runs", "api_error 401"],
                                     seat_auth_credential_file_mtime_utc="2026-09-25T23:38:43Z"))
    auth = _line(rows, 4)
    assert auth.startswith("⚠ runtime auth degraded — paused after 3 failed runs · api_error 401; credential file refreshed ")
    assert auth.endswith("(not read)")


# -- the sentence is fitted, never CSS-cut, and never carries a control byte -----------------


async def test_the_sentence_is_fitted_with_a_visible_ellipsis_and_no_marker():
    long = dict(CURRENT, lastMessage="x" * 400)
    rows = await _now((80, 9), **_healthy(seat_current=long, seat_standing_running=RUNNING))
    assert _line(rows, 2).endswith("…") and len(_line(rows, 2)) <= 78
    assert "‹" not in rows[0], "an agent's prose is capped by the daemon; its length is not a layout defect"


async def test_control_codes_never_reach_a_strip():
    # spec §14 mutation proof 23 (NOW half): the OSC 52 / OSC 0 / U+202E sample through NOW's sentence
    assert CONTROL_LINES, "the WP1 fixture has a working: line"
    # WP1's fixture has two ``working:`` lines: OSC 52 / OSC 0 (ESC bytes) and a U+202E/U+202C bidi forgery (no ESC).
    # Step 0 glyphs ESC but deletes bidi formats without a trace, so the glyph is asserted only where an ESC was.
    assert any("\x1b" in raw for raw in CONTROL_LINES), "the ESC half of proof 23 must not become vacuous"
    for raw in CONTROL_LINES:
        rows = await _now(WIDE, **_healthy(seat_current=dict(CURRENT, lastMessage=raw), seat_standing_running=RUNNING))
        text = "\n".join(rows)
        assert not (set(text) & FORBIDDEN), [hex(ord(c)) for c in text if c in FORBIDDEN]
        if "\x1b" in raw:
            assert "␛" in _line(rows, 2), "an attempted escape stays visible as a glyph"


async def test_masked_key_never_reaches_a_strip():
    # spec §14 mutation proof 12 (strip half, NOW): a reason carrying the masked fragment is redacted by the widget.
    # The slice starts at the 401 reason so ``sk-svcac`` (offset 199 of the 232-char line) is in the input;
    # ``strip_tags`` deletes the ``[redacted]`` placeholder, so the painted remnant is ``provided: sk-``.
    reason = MASKED_LINE[MASKED_LINE.index("unexpected status"):]
    assert "sk-svcac" in reason, "the input must carry the key or the proof is vacuous"
    rows = await _now(WIDE, **_healthy(seat_auth_degraded=True, seat_auth_reasons=[reason]))
    text = "\n".join(rows)
    assert "sk-svcac" not in text and "provided: sk-" in text


async def test_hostile_markup_in_third_party_text_renders_literally():
    rows = await _now(WIDE, **_healthy(seat_current=dict(CURRENT, objective="[/x][bold]evil[/] plan"), seat_standing_running=RUNNING))
    assert "[bold]" not in "\n".join(rows) and "evil" in _line(rows, 1)
