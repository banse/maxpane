"""Grammar tests for ``data/seat_log_grammar.py`` (spec §5.1, Appendix B; contract C.5)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from maxpane_dashboard.analytics.seat_redact import CONTROL_RE, SK_RE
from maxpane_dashboard.data import seat_log_grammar as g

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seat" / "grammar"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines()


def _kinds(name: str) -> list[str]:
    return [g.classify(line).kind for line in _lines(name)]


class TestModuleShape:
    def test_thirty_one_stamped_patterns_in_match_order(self) -> None:
        """Contract C.5: 31 (kind, pattern) pairs; MODEL_LINE and MODEL_REFUSE before PHASE; RATE_LIMITED last."""
        kinds = [kind for kind, _ in g.PATTERNS]
        assert len(kinds) == 31 and len(set(kinds)) == 31
        assert kinds.index(g.KIND_MODEL_LINE) < kinds.index(g.KIND_PHASE)
        assert kinds.index(g.KIND_MODEL_REFUSE) < kinds.index(g.KIND_PHASE)
        assert kinds[-1] == g.KIND_RATE_LIMITED

    def test_every_pattern_is_ascii_and_anchored_at_the_stamp(self) -> None:
        """Appendix B: compile with re.ASCII; every body starts with TS (the ``^(?P<ts>…) `` anchor) and ends with $."""
        for _, pattern in g.PATTERNS:
            assert pattern.flags & re.ASCII
            assert pattern.pattern.startswith(g.TS)
            assert pattern.pattern.endswith("$")

    def test_kind_sets(self) -> None:
        assert g.ACCEPTED_KINDS == {"accepted_code", "accepted_research", "accepted_fuzz"}
        assert g.TERMINAL_KINDS == {"submitted", "answered", "fuzz_outcome", "stored", "cancelled"}
        assert g.CONNECTION_KINDS == {"connected", "admitted", "server_closed", "reconnecting", "ws_response", "ws_socket"}
        assert g.HIGHLIGHT_KINDS == {"rate_limited", "build_skew", "release_avail", "local_fail", "resending", "cancelled"}
        assert g.GRAMMAR_VERSION == "0.1.0+5bfa8261"
        assert g.is_accept("accepted_fuzz") and g.is_terminal("stored") and not g.is_terminal("phase")


class TestClassifyEachKind:
    def test_heartbeat_with_fleet(self) -> None:
        line = g.classify("2026-09-26T02:28:25.226Z alive 14h42m · idle · 77 submitted · fleet 406 online, 417 enrolled")
        assert line.kind == g.KIND_HEARTBEAT and line.ts == "2026-09-26T02:28:25.226Z"
        f = line.fields
        assert (f["state"], f["uptime"], f["work"], f["submitted"], f["online"], f["enrolled"]) == (
            "alive", "14h42m", "idle", "77", "406", "417")
        assert f["running"] is None and f["until"] is None

    def test_heartbeat_without_fleet_clause(self) -> None:
        """Spec §5.1: the fleet clause is absent when the 5 s GET /health failed (427+ lines)."""
        line = g.classify("2026-09-25T15:13:19.512Z disconnected 3h27m · idle · 0 submitted")
        assert line.kind == g.KIND_HEARTBEAT
        assert line.fields["state"] == "disconnected" and line.fields["online"] is None

    def test_heartbeat_running_and_paused_suffix_is_redacted_before_matching(self) -> None:
        raw = ("2026-09-25T23:55:52.556Z alive 12h10m · 1 task running · 16 submitted · fleet 403 online, 412 enrolled"
               " · paused until 23:53 after 3 failed runs: unexpected status 401 Unauthorized: Incorrect API key provided:"
               " sk-svcac******** — run imd doctor")
        line = g.classify(raw)
        assert line.kind == g.KIND_HEARTBEAT
        assert line.fields["running"] == "1" and line.fields["until"] == "23:53" and line.fields["failed"] == "3"
        assert "sk-svcac" not in line.text and "sk-[redacted]" in line.fields["reason"]

    def test_heartbeat_unregistered_suffix(self) -> None:
        line = g.classify("2026-09-26T02:28:25.226Z alive 1m · idle · 0 submitted · token not registered as an agent — run imd doctor")
        assert line.kind == g.KIND_HEARTBEAT and line.fields["unregistered"]

    def test_accept_lines(self) -> None:
        code = g.classify("2026-09-26T01:52:44.909Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)")
        assert code.kind == g.KIND_ACCEPTED_CODE
        assert (code.fields["role"], code.fields["node8"], code.fields["paths"], code.fields["max_turns"]) == (
            "implement", "0c1f9727", "artifacts/answer.json", "60")
        tests = g.classify("2026-09-24T03:50:34.996Z accepted tests e78e1517 — test/fren-review/hunt_d, review/hunt_d.md (max 60 turns)")
        assert tests.kind == g.KIND_ACCEPTED_CODE and tests.fields["role"] == "tests"
        research = g.classify("2026-09-25T18:08:55.020Z accepted question ec996927")
        assert research.kind == g.KIND_ACCEPTED_RESEARCH and research.fields["node8"] == "ec996927"
        fuzz = g.classify("2026-09-24T04:24:01.000Z accepted campaign cb1949ef — test/Harness.t.sol (256 runs)")
        assert fuzz.kind == g.KIND_ACCEPTED_FUZZ and fuzz.fields["runs"] == "256"

    def test_phase_and_model_lines(self) -> None:
        phase = g.classify("2026-09-22T05:14:45.887Z   repairing: fixing failed checks within this assignment")
        assert phase.kind == g.KIND_PHASE and phase.fields["phase"] == "repairing"
        model = g.classify("2026-09-26T01:52:45.400Z   working: running codex on gpt-6-luna")
        assert model.kind == g.KIND_MODEL_LINE and (model.fields["rt"], model.fields["model"]) == ("codex", "gpt-6-luna")
        over = g.classify("2026-09-26T01:52:45.400Z   working: " + "x" * 161)
        assert over.kind == g.KIND_UNKNOWN  # the daemon slices prose at 160 (bundle §3.1); longer is not a daemon line
        bare = g.classify("2026-09-26T01:52:45.400Z   working: running claude")
        assert bare.kind == g.KIND_MODEL_LINE and bare.fields["model"] is None
        refuse = g.classify("2026-09-26T01:52:45.400Z   working: codex refused model gpt-6-astra; running on its default model instead")
        assert refuse.kind == g.KIND_MODEL_REFUSE and refuse.fields["model"] == "gpt-6-astra"

    def test_terminal_lines(self) -> None:
        assert g.classify("2026-09-26T01:53:17.136Z submitted implement for 0c1f9727").fields["node8"] == "0c1f9727"
        assert g.classify("2026-09-25T18:09:56.031Z answered ec996927 with 2 citation(s)").fields["citations"] == "2"
        stored = g.classify("2026-09-26T02:28:23.225Z submission stored (c4d9714ffb95) — awaiting verdict")
        assert stored.kind == g.KIND_STORED and stored.fields["hash12"] == "c4d9714ffb95"
        cancel = g.classify("2026-09-26T02:48:18.153Z cancelled 16a4df90: superseded")
        assert cancel.kind == g.KIND_CANCELLED and (cancel.fields["lease8"], cancel.fields["reason"]) == ("16a4df90", "superseded")
        for text in ("counterexample for invariant_totalSupply", "campaign could not run: the harness did not build",
                     "exhausted 256 runs, nothing found"):
            assert g.classify(f"2026-09-24T04:26:00.000Z {text}").kind == g.KIND_FUZZ_OUTCOME

    def test_error_resend_and_rate_limit_lines(self) -> None:
        err = g.classify("2026-09-26T02:48:19.226Z server error (unknown_lease): lease_closed: lease is expired")
        assert err.kind == g.KIND_SERVER_ERROR and err.fields["code"] == "unknown_lease"
        assert g.classify("2026-09-22T17:21:24.081Z re-sending 1 unacknowledged result(s)").fields["n"] == "1"
        fail = g.classify("2026-09-26T00:00:00.000Z question failed: boom")
        assert fail.kind == g.KIND_LOCAL_FAIL and fail.fields["what"] == "question"
        rate = g.classify("2026-09-26T00:00:00.000Z codex remains rate limited; releasing task after runtime shutdown; pausing new work for five minutes")
        assert rate.kind == g.KIND_RATE_LIMITED

    def test_connection_lines(self) -> None:
        assert g.classify("2026-09-25T11:45:41.663Z connected to api.imd.fun").fields["host"] == "api.imd.fun"
        assert g.classify("2026-09-25T11:45:41.968Z admitted (session 29904530)").fields["session8"] == "29904530"
        closed = g.classify("2026-09-25T15:13:12.445Z server closed: server_shutdown — control plane restarting")
        assert closed.kind == g.KIND_SERVER_CLOSED and closed.fields["reason"] == "server_shutdown"
        assert g.classify("2026-09-24T22:21:56.620Z reconnecting in 3.8s").fields["seconds"] == "3.8"
        assert g.classify("2026-09-24T22:21:56.620Z Unexpected server response: 502").fields["code"] == "502"
        for msg in ("socket hang up", "Client network socket disconnected before secure TLS connection was established"):
            assert g.classify(f"2026-09-21T20:38:40.992Z {msg}").kind == g.KIND_WS_SOCKET

    def test_startup_and_update_lines(self) -> None:
        rt = g.classify("2026-09-25T11:45:41.489Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)")
        assert rt.kind == g.KIND_RUNTIMES and rt.fields["list"] == "codex codex-cli 0.157.0" and rt.fields["rt"] == "codex"
        assert g.classify("2026-09-25T11:45:41.501Z execution profiles: none, foundry").kind == g.KIND_PROFILES
        assert g.classify("2026-09-25T11:45:41.501Z tools advertised: a, b").fields["tools"] == "a, b"
        assert g.classify("2026-09-25T11:45:41.804Z release 0.1.0+5bfa8261, the latest").fields["version"] == "0.1.0+5bfa8261"
        avail = g.classify("2026-09-23T19:56:32.045Z 0.1.0+79f4f4d5 installed; 0.1.0+61d04d62 is available; when idle, stop the worker and run `imd update`, or start with --auto-update so it happens by itself")
        assert avail.kind == g.KIND_RELEASE_AVAIL and (avail.fields["installed"], avail.fields["available"]) == ("0.1.0+79f4f4d5", "0.1.0+61d04d62")
        skew = g.classify("2026-09-23T19:56:32.045Z control plane runs build 0.1.0+aa634633; this checkout is 0.1.0+5bfa8261 — update when idle")
        assert skew.kind == g.KIND_BUILD_SKEW and (skew.fields["plane"], skew.fields["local"]) == ("0.1.0+aa634633", "0.1.0+5bfa8261")
        assert g.classify("2026-09-23T19:56:32.045Z build mismatch: control plane 0.1.0+aa634633").kind == g.KIND_BUILD_SKEW
        assert g.classify("2026-09-25T11:45:41.217Z shutting down").kind == g.KIND_SHUTTING_DOWN
        upd = g.classify("2026-09-24T04:12:40.000Z updated 0.1.0+61d04d62 → 0.1.0+aa8ff6ee (downloaded, verified, installed)")
        assert upd.kind == g.KIND_UPDATED and upd.fields["to"] == "0.1.0+aa8ff6ee"
        assert g.classify("2026-09-22T11:56:18.000Z paired to token 7").fields["token"] == "7"

    def test_unknown_lines(self) -> None:
        """Spec §5.1: anything that matches no pattern is unknown (LOG only); a stamped unknown keeps its stamp."""
        unknown = g.classify("2026-09-21T20:38:54.151Z getaddrinfo EAI_AGAIN api.imd.fun")
        assert unknown.kind == g.KIND_UNKNOWN and unknown.ts == "2026-09-21T20:38:54.151Z" and unknown.fields == {}
        assert g.classify("npm warn deprecated something").kind == g.KIND_UNKNOWN
        assert g.classify("npm warn deprecated something").ts == ""

    def test_log_line_carries_transport_fields(self) -> None:
        line = g.classify("2026-09-25T11:45:41.217Z shutting down", invocation="abc", cursor="s=1;i=2", seq=7)
        assert (line.invocation, line.cursor, line.seq) == ("abc", "s=1;i=2", 7)
        with pytest.raises(Exception):
            line.kind = "x"  # type: ignore[misc]  # frozen

    def test_model_line_matches_before_phase(self) -> None:
        """Contract C.5 order rule: ``  working: running codex on gpt-6-luna`` satisfies PHASE too; order decides."""
        line = g.classify("2026-09-26T01:52:45.400Z   working: running codex on gpt-6-luna")
        assert line.kind == g.KIND_MODEL_LINE
        assert g.PHASE.fullmatch(line.text) is not None  # the ambiguity is real, the order resolves it

    def test_control_characters_are_stripped_before_matching(self) -> None:
        """Spec §13 step 0 / Appendix B: an OSC-52 payload inside working: prose still classifies as phase."""
        raw = "2026-09-26T01:52:50.000Z   working: done \x1b]52;c;AAAA\x07\x1b]0;x\x07 ‮ reversed"
        line = g.classify(raw)
        assert line.kind == g.KIND_PHASE
        assert "\x07" not in line.text and "‮" not in line.text and "␛" in line.text


# ---------------------------------------------------------------------------------------- Task 2.2
class TestUnitEventsAndHelpers:
    def test_unit_events(self) -> None:
        """Spec §5.1: systemd's own lines lack the daemon stamp and classify as unit events (both measured forms)."""
        for line in _lines("unit_events.txt"):
            classified = g.classify(line)
            assert classified.kind == g.KIND_UNIT_EVENT and classified.ts == "", line
        assert g.classify("imd-worker.service: Scheduled restart job, restart counter is at 1.").fields["event"] == "Scheduled restart"
        assert g.classify("Started imd-worker.service - IMD worker (Codex, seat #7).").fields["event"] == "Started"
        assert g.classify("Started something else entirely").kind == g.KIND_UNIT_EVENT  # the regex is deliberately loose
        assert g.classify("2026-09-25T11:45:41.217Z Started imd-worker.service").kind == g.KIND_UNKNOWN  # a stamped line is the daemon's

    def test_parse_ts(self) -> None:
        assert g.parse_ts("2026-09-25T11:45:41.489Z") == 1790336741.489
        assert g.parse_ts("") is None and g.parse_ts("2026-09-25 11:45") is None

    def test_strip_docker_prefix(self) -> None:
        """Docker's RFC3339Nano prefix goes; the daemon's stamp stays; a journald line is untouched."""
        docker = "2026-09-21T19:57:26.361783469Z 2026-09-21T19:57:26.361Z runtimes: claude 2.1.278 (Claude Code) (using claude, as asked)"
        assert g.strip_docker_prefix(docker) == "2026-09-21T19:57:26.361Z runtimes: claude 2.1.278 (Claude Code) (using claude, as asked)"
        assert g.strip_docker_prefix("2026-09-21T20:38:54.151911678Z npm warn something") == "npm warn something"
        assert g.strip_docker_prefix("2026-09-21T20:38:54.15Z npm warn something") == "npm warn something"  # Go trims zeros
        journald = "2026-09-25T11:45:41.217Z shutting down"
        assert g.strip_docker_prefix(journald) == journald
        assert g.strip_docker_prefix("Started imd-worker.service - IMD worker (Codex, seat #7).") == "Started imd-worker.service - IMD worker (Codex, seat #7)."


# ---------------------------------------------------------------------------------------- Task 2.3
def test_prose_never_forges_an_accept() -> None:
    """Mutation proof 2 (spec §14): every pattern is anchored at the stamp and matched with fullmatch.

    The real journal line 4876 ("… the accepted recipe must cite …") and four labelled forgeries
    (a quoted accept template inside working: prose, a quoted stored line, an unstamped accept and
    a stamped accept with trailing text) must never become an accept or a stored event.
    """
    kinds = _kinds("prose_forgery.txt")
    assert kinds == ["model_line", "heartbeat", "phase", "heartbeat", "heartbeat", "phase", "phase", "unknown", "unknown"]
    assert not any(k in g.ACCEPTED_KINDS or k == g.KIND_STORED for k in kinds)


# ---------------------------------------------------------------------------------------- Task 2.4
class TestJournalSlices:
    def test_restart_boundary_slice(self) -> None:
        kinds = _kinds("restart_boundary.txt")
        assert kinds[:7] == ["heartbeat", "unit_event", "shutting_down", "unit_event", "unit_event", "unit_event", "unit_event"]
        assert kinds[7:] == ["runtimes", "profiles", "connected", "release_ok", "admitted", "heartbeat", "heartbeat"]

    def test_heartbeat_no_fleet_slice(self) -> None:
        lines = [g.classify(l) for l in _lines("heartbeat_no_fleet.txt")]
        no_fleet = [l for l in lines if l.kind == g.KIND_HEARTBEAT and l.fields["online"] is None]
        assert len(no_fleet) == 1 and no_fleet[0].fields["state"] == "disconnected"

    def test_research_slice(self) -> None:
        research = _kinds("research_question.txt")
        assert research.count("accepted_research") == 1 and research.count("answered") == 1 and research.count("stored") == 1

    def test_lingering_pause_slice(self) -> None:
        linger = [g.classify(l) for l in _lines("heartbeat_lingering_pause.txt")]
        paused_while_running = [l for l in linger if l.kind == g.KIND_HEARTBEAT and l.fields["until"] and l.fields["running"]]
        assert len(paused_while_running) == 2 and all(l.fields["until"] == "23:53" for l in paused_while_running)
        assert "unknown" not in [l.kind for l in linger]
        assert SK_RE.search("\n".join(_lines("heartbeat_lingering_pause.txt"))) is None  # redacted before commit


# ---------------------------------------------------------------------------------------- Task 2.5
class TestEdgeSlices:
    def test_cancel_slice(self) -> None:
        cancel = _kinds("cancel_lease_closed.txt")
        assert cancel.count("cancelled") == 1 and cancel.count("server_error") == 1 and "unknown" not in cancel

    def test_repair_resend_fastfail_double_slices(self) -> None:
        repair = _kinds("repair_once.txt")
        assert repair.count("accepted_code") == 3 and repair.count("submitted") == 3 and repair.count("stored") == 3
        assert sum(1 for l in _lines("repair_once.txt") if g.classify(l).fields.get("phase") == "repairing") == 3
        resend = _kinds("resend.txt")
        assert resend.count("resending") == 2 and resend.count("stored") == 2
        fast = _kinds("fast_fail_no_working.txt")
        assert fast.count("accepted_code") == 6 and fast.count("model_line") == 0
        double = _kinds("double_accept.txt")
        assert double.count("accepted_code") == 6 and "unknown" not in double

    def test_redeploy_wave_slice(self) -> None:
        wave = [g.classify(l) for l in _lines("redeploy_wave.txt")]
        disconnected = [l for l in wave if l.kind == g.KIND_HEARTBEAT and l.fields["state"] == "disconnected"]
        assert len(disconnected) == 5 and any(l.fields["online"] == "6" for l in disconnected)
        assert sum(1 for l in wave if l.kind == g.KIND_ADMITTED) == 2

    def test_open_accept_after_idle_slice(self) -> None:
        kinds = _kinds("open_accept_after_idle.txt")
        assert kinds == ["heartbeat"] * 4 + ["accepted_code", "phase", "model_line"]


# ---------------------------------------------------------------------------------------- Task 2.12
@pytest.mark.parametrize("name, docker", [("journal7d.txt", False), ("docker420.log", True)])
def test_corpus_is_covered_by_the_grammar(name: str, docker: bool) -> None:
    """Spec §14 grammar corpus: the redacted VPS journal and Mac docker log classify with (almost) no unknowns.

    Both corpora are the scratchpad captures of 2026-09-26 (13,734 / 15,882 lines). Every accept has a
    terminal line, stored trails submitted by at most one, and no committed byte matches SK_RE / CONTROL_RE.
    """
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"{name} not captured yet (Task 2.12, owner-run)")
    raw = path.read_text(encoding="utf-8")
    assert SK_RE.search(raw) is None and CONTROL_RE.search(raw.replace("\n", "")) is None
    counts: dict[str, int] = {}
    unknown: list[str] = []
    for line in raw.splitlines():
        text = g.strip_docker_prefix(line) if docker else line
        kind = g.classify(text).kind
        counts[kind] = counts.get(kind, 0) + 1
        if kind == g.KIND_UNKNOWN:
            unknown.append(text)
    accepts = counts.get("accepted_code", 0) + counts.get("accepted_research", 0) + counts.get("accepted_fuzz", 0)
    closes = counts.get("submitted", 0) + counts.get("answered", 0) + counts.get("fuzz_outcome", 0)
    assert accepts == closes and accepts > 250
    assert 0 <= closes - counts.get("stored", 0) <= 1
    assert counts["heartbeat"] > 0.6 * sum(counts.values())
    assert all("getaddrinfo EAI_AGAIN" in u for u in unknown), unknown[:5]
    assert len(unknown) <= 1
    if name == "journal7d.txt":
        assert counts["unit_event"] == 41 and counts["accepted_research"] == 1 and counts["answered"] == 1
    else:
        assert counts["resending"] == 2 and counts["ws_socket"] == 8
