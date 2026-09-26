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


# ---------------------------------------------------------------------------
# Task 1.2 — the ordered rule table and redact()
# ---------------------------------------------------------------------------


def test_redact_none_and_unprintable_objects_are_empty():
    class Boom:
        def __str__(self):
            raise RuntimeError("no")

    assert sr.redact(None) == ""
    assert sr.redact(Boom()) == ""
    assert sr.redact(42) == "42"


def test_sk_ant_precedes_sk():
    # spec §13 order rule: sk-ant- must not be left as sk-[redacted]
    out = sr.redact("key sk-ant-api03-abcd1234 and sk-proj-zzzz9999 end")
    assert out == "key sk-ant-[redacted] and sk-[redacted] end"
    assert sr.RULES[0][1] == "sk-ant-[redacted]" and sr.RULES[1][1] == "sk-[redacted]"


def test_jwt_bearer_github_and_query_rules():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert sr.redact(f"auth {jwt} ok") == "auth [jwt] ok"
    assert sr.redact("Authorization: Bearer abcDEF123456") == "Authorization: Bearer [redacted]"
    assert sr.redact("ghp_" + "A" * 36) == "[github-token]"
    assert sr.redact("gho_" + "b" * 20 + " ghs_" + "c" * 25) == "[github-token] [github-token]"
    assert sr.redact("https://x/y?token=abc&sig=def&page=2") == "https://x/y?token=[redacted]&sig=[redacted]&page=2"
    # a bare header segment is not a JWT for the *rule* (two segments needed) but is for the canary
    assert sr.redact("eyJhbGciOiJIUzI1NiJ9") == "eyJhbGciOiJIUzI1NiJ9"
    assert sr.JWT_RE.search("eyJhbGciOiJIUzI1NiJ9") is not None


def test_hex64_placeholder_unless_the_field_is_allowed():
    # spec §13: <hex64> unless the field is a known hash/public-key field
    assert sr.redact(HEX64) == "<hex64>"
    assert sr.redact(f"tx {HEX64} mined") == "tx <hex64> mined"
    assert sr.redact(HEX64, field="submissionHash") == HEX64
    assert sr.redact(HEX64, field="txHash") == HEX64
    assert sr.redact(HEX64, field="deviceKey") == HEX64
    assert sr.redact(HEX64, field="hash12") == "<hex64>"
    assert sr.redact(HEX64[:-1]) == HEX64[:-1]          # 63 hex is not a key
    assert sr.redact(HEX64 + "0") == HEX64 + "0"        # 65 hex has no word boundary at 64
    assert sr.HEX64_ALLOWED_FIELDS == frozenset({"submissionHash", "txHash", "deviceKey"})


def test_redact_runs_step_0_before_the_rules():
    # a NUL or a bidi control inside a key must not hide it from the sk rule
    assert sr.redact("\x00sk-abcd\x00") == "sk-[redacted]"
    assert sr.redact("sk-\u202eabcd") == "sk-[redacted]"
    assert sr.redact("\x1b[31msk-abcd") == "\u241b[31msk-[redacted]"


# ---------------------------------------------------------------------------
# Task 1.3 — agent sentences and the real masked-key heartbeat
# ---------------------------------------------------------------------------


def test_redact_agent_sentence_collapses_whitespace_and_caps_160():
    # spec §13: whitespace collapse and a 160-char cap on agent sentences (the daemon's own two operations)
    text = "Created\n\n artifacts/answer.json \t\t then  " + "x" * 300
    out = sr.redact_agent_sentence(text)
    assert out.startswith("Created artifacts/answer.json then xxxx")
    assert "  " not in out and "\n" not in out and "\t" not in out
    assert len(out) == sr.AGENT_SENTENCE_CAP == 160
    assert sr.redact_agent_sentence(None) == ""


def test_masked_key_never_reaches_a_strip_or_the_ledger():
    # spec §14 mutation proof 12 (redactor half): the real sk-svcac******** fragment from the 09-25 heartbeat
    lines = _fixture_lines("heartbeat_paused_401.txt")
    assert len(lines) == 91
    masked = [line for line in lines if "sk-svcac" in line]
    assert len(masked) == 30, "the slice carries exactly 30 heartbeats with the masked fragment"
    for line in masked:
        out = sr.redact(line)
        assert "svcac" not in out
        assert "sk-[redacted] — run imd doctor" in out
        beat = HEARTBEAT.fullmatch(out)
        assert beat is not None, out
        assert beat.group("reason") == "unexpected status 401 Unauthorized: Incorrect API key provided: sk-[redacted]"
        assert "svcac" not in sr.redact_agent_sentence(line)
    # the strings the ledger would persist from this incident
    reason = masked[0].split("failed runs: ", 1)[1].split(" — run imd doctor")[0]
    paused_hint = {"until": "23:53", "failedRuns": 3, "reason": sr.redact(reason)}
    assert paused_hint["reason"] == "unexpected status 401 Unauthorized: Incorrect API key provided: sk-[redacted]"
    assert sr.SK_RE.search(json.dumps(paused_hint)) is None
