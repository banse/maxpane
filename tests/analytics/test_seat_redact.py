"""Tests for ``maxpane_dashboard.analytics.seat_redact`` (PEPEPANE plan WP1).

Pure string work: no network, no clock.  Two fixtures feed it --
``grammar/control_chars.txt`` (synthetic; the input half of mutation proof 23)
and ``grammar/heartbeat_paused_401.txt`` (the real 2026-09-25 journal slice
whose heartbeat suffix carries the server-masked ``sk-svcac********``
fragment; mutation proof 12).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import seat_redact as sr

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
REPO = Path(__file__).resolve().parents[2]

#: Appendix B, verbatim: the redactor runs before matching, so a stripped line
#: must still match its pattern.  Inlined here because WP2's grammar module
#: does not exist yet.
TS = r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z) "
PHASE = re.compile(
    TS + r"  (?P<phase>preparing|working|checking|bundling|uploading|repairing): (?P<msg>.{0,160})$", re.ASCII
)
HEARTBEAT = re.compile(
    TS + r"(?P<state>alive|disconnected) (?P<uptime>\d+m|\d+h\d+m|\d+d\d+h) · "
    r"(?P<work>idle|(?P<running>\d+) tasks? running) · (?P<submitted>\d+) submitted"
    r"(?: · fleet (?P<online>\d+) online, (?P<enrolled>\d+) enrolled)?"
    r"(?: · (?:paused until (?P<until>\d\d:\d\d) after (?P<failed>\d+) failed runs?(?:: (?P<reason>.*?))? — run imd doctor"
    r"|(?P<unregistered>token not registered as an agent — run imd doctor)))?$",
    re.ASCII,
)
HEX64 = "0123456789abcdef" * 4


def _fixture_lines(name: str) -> list[str]:
    raw = (FIXTURES / "grammar" / name).read_bytes().decode("utf-8")
    return [line for line in raw.split("\n") if line]


# ---------------------------------------------------------------------------
# Task 1.1 — step 0: control characters
# ---------------------------------------------------------------------------


def test_strip_controls_glyphs_esc_and_removes_the_rest():
    # spec §13 step 0: ESC -> \u241b (visible), other C0 (not \t \n), DEL, C1, bidi removed
    assert sr.strip_controls("a\x1b]52;c;AAAA\x07b") == "a\u241b]52;c;AAAAb"
    assert sr.strip_controls("x\x00y\x7fz\x9bw") == "xyzw"
    assert sr.strip_controls("\u202eevil\u202c ok\u200b") == "evil ok"
    assert sr.strip_controls("tab\tkept\nnewline kept") == "tab\tkept\nnewline kept"
    assert sr.ESC_GLYPH == "\u241b"


def test_strip_controls_removes_osc_and_bidi_and_glyphs_esc():
    # spec §14 mutation proof 23, input half: the control_chars.txt fixture through step 0
    raw = (FIXTURES / "grammar" / "control_chars.txt").read_bytes()
    assert b"\x1b]52;c;AAAA\x07" in raw, "the fixture must carry the raw OSC 52 sequence"
    assert "\u202e".encode("utf-8") in raw, "the fixture must carry U+202E"
    lines = _fixture_lines("control_chars.txt")
    assert len(lines) == 4
    stripped = [sr.strip_controls(line) for line in lines]
    for line in stripped:
        assert not any(ord(c) < 0x20 and c != "\t" for c in line), line
        assert not any(0x7F <= ord(c) <= 0x9F for c in line), line
        assert sr.BIDI_FORMAT_RE.search(line) is None, line
    assert stripped[0] == "2026-09-26T03:24:05.101Z   working: Created artifacts/answer.json \u241b]52;c;AAAA\u241b]0;x done"
    # the injected bytes never change the line's kind: still a PHASE line, still a heartbeat
    assert PHASE.fullmatch(stripped[0]).group("phase") == "working"
    assert PHASE.fullmatch(stripped[1]).group("phase") == "working"
    beat = HEARTBEAT.fullmatch(stripped[2])
    assert beat is not None and beat.group("running") == "1" and beat.group("online") == "406"
    assert "\t" in stripped[3] and "\x08" not in stripped[3]


@pytest.mark.guard
def test_manifest_guard_patterns_match_the_redactor():
    # WP0's tests/test_seat_fixture_manifest.py restates the step-0 and canary regexes; they must not drift
    from tests import test_seat_fixture_manifest as guard

    assert sr.CONTROL_RE.pattern == guard.CONTROL_RE.pattern
    assert sr.BIDI_FORMAT_RE.pattern == guard.BIDI_FORMAT_RE.pattern
    # the redactor's SK_RE adds only the lookahead that spares its own `sk-ant-[redacted]` placeholder
    assert sr.SK_RE.pattern == guard.SK_RE.pattern.replace("sk-", r"sk-(?!ant-\[redacted\])", 1)
    for text in ("sk-svcac********", "sk-ant-api03-abcd", "sk-proj-zzzz9999"):
        assert sr.SK_RE.search(text) and guard.SK_RE.search(text), text
    assert sr.SK_RE.search("sk-[redacted]") is None and guard.SK_RE.search("sk-[redacted]") is None
