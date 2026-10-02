"""``imd_dashd/gate.py`` -- the idle gate G, evaluated fresh at apply (spec §11 steps (a)-(e); proofs 7, 24, 28)."""
from __future__ import annotations

import json

import pytest

from imd_dashd import gate
from imd_dashd.gate import (
    GATE_STANDING_MAX_AGE_S, GateResult, IDLE_BEATS_REQUIRED, IDLE_WINDOW_S, evaluate, idle_beats, newest_lifecycle,
)

NOW = 1_790_000_000.0


def hb(offset_s: float, work: str = "idle", state: str = "alive") -> tuple[float, str]:
    """A daemon heartbeat as the broker reads it from the journal: (epoch, message)."""
    epoch = NOW - offset_s
    stamp = gate.iso_utc(epoch)[:-1] + ".000Z"
    return epoch, f"{stamp} {state} 14h42m · {work} · 77 submitted · fleet 406 online, 417 enrolled"


def line(offset_s: float, text: str) -> tuple[float, str]:
    epoch = NOW - offset_s
    return epoch, f"{gate.iso_utc(epoch)[:-1] + '.000Z'} {text}"


FRESH_PLANE = {"running_count": 0, "at": gate.iso_utc_ms(NOW - 0.4)}
IDLE_9 = [hb(30 * i) for i in range(9, 0, -1)] + [hb(11)]      # ten idle beats, newest 11 s old; 7 inside the 180 s window


def ok_gate(**overrides) -> GateResult:
    kwargs = dict(journal_lines=IDLE_9 + [line(20 * 60 + 17, "submitted implement for 0c1f9727")],
                  standing=FRESH_PLANE, offline=False, outbox_files=0, unit_active=True,
                  graceful_stop_possible=True, now=NOW, lifecycle_read_succeeded=True)
    kwargs.update(overrides)
    # keep the journal in time order whatever the override
    kwargs["journal_lines"] = sorted(kwargs["journal_lines"], key=lambda item: item[0])
    return evaluate(**kwargs)


def test_idle_beats_count_consecutive_idle_within_the_window():
    # spec §11 (a): >= 4 consecutive `· idle ·` heartbeats among heartbeats newer than now - 3 min
    assert IDLE_BEATS_REQUIRED == 4 and IDLE_WINDOW_S == 180
    count, age = idle_beats([hb(150), hb(120), hb(90), hb(60), hb(30)], now=NOW)
    assert (count, age) == (5, 30.0)
    count, _ = idle_beats([hb(120, "1 task running"), hb(90), hb(60), hb(30)], now=NOW)
    assert count == 3                                    # the running beat ends the run
    count, _ = idle_beats([hb(90), hb(60), hb(30, "2 tasks running")], now=NOW)
    assert count == 0                                    # newest beat is running
    count, age = idle_beats([hb(400), hb(350), hb(300), hb(250)], now=NOW)
    assert (count, age) == (0, None)                     # a frozen tail cannot vouch idle (spec §9)
    count, _ = idle_beats([hb(200), hb(170), hb(140)], now=NOW)
    assert count == 2                                    # the 200 s beat is outside the window


def test_newest_lifecycle_is_anchored_and_ignores_prose():
    lines = [
        line(300, "accepted implement 0c1f9727 — src/, test/ (max 60 turns)")[1],
        line(240, "  working: the accepted recipe must cite the oracle answer")[1],   # prose forgery (fill6 §2)
        line(200, "submitted implement for 0c1f9727")[1],
        line(100, "2026-09-26T03:24:17.136Z accepted implement deadbeef — x (max 1 turns)")[1],  # not anchored at col 0
    ]
    assert newest_lifecycle(lines) == (lines[2], False)
    assert newest_lifecycle(lines + [line(50, "accepted question ec996927")[1]]) == (
        line(50, "accepted question ec996927")[1], True)
    assert newest_lifecycle(["2026-09-26T03:24:17.136Z alive 1m · idle · 0 submitted"]) == (None, None)
    assert newest_lifecycle([line(10, "submission stored (c4d9714ffb95) — awaiting verdict")[1]])[1] is False
    assert newest_lifecycle([line(10, "cancelled 16a4df90: superseded")[1]])[1] is False


def test_safe_gate_has_the_spec_preconditions_shape():
    result = ok_gate()
    assert result.safe and result.reason is None and result.unknown is None
    assert result.idle_beats == 7 and result.idle_beats_required == 4 and result.newest_heartbeat_age_s == 11.0
    assert result.plane == {"mode": "plane+local", "running": 0, "as_of": FRESH_PLANE["at"], "standing_age_s": 0.4}
    assert result.lifecycle_open is False and result.last_lifecycle_line.endswith("submitted implement for 0c1f9727")
    assert result.outbox_files == 0 and result.unit_active is True and result.graceful_stop_possible is True
    assert set(result.to_dict()) == {"safe", "reason", "idle_beats", "idle_beats_required", "newest_heartbeat_age_s",
                                     "plane", "last_lifecycle_line", "lifecycle_open", "outbox_files", "unit_active",
                                     "graceful_stop_possible", "unknown"}


def test_restart_plan_refuses_while_running():
    # mutation proof 7 (idle gate 4 -> 0): two idle beats after work are not enough …
    two_idle = [hb(90, "1 task running"), hb(60), hb(30)]
    result = ok_gate(journal_lines=two_idle + [line(20 * 60, "submitted implement for 0c1f9727")])
    assert not result.safe and result.reason == "idle 2/4 beats" and result.idle_beats == 2
    # … and a newest heartbeat that says `1 task running` is refused outright
    running = IDLE_9[:-1] + [hb(11, "1 task running")]
    result = ok_gate(journal_lines=running + [line(20 * 60, "submitted implement for 0c1f9727")])
    assert not result.safe and result.idle_beats == 0 and result.reason.startswith("task running")


def test_gate_requires_empty_outbox():
    # mutation proof 7 (drop outbox == 0): a pending unacked result blocks the restart (spec §11 (d))
    assert ok_gate(outbox_files=1).reason == "outbox 1 file"
    assert ok_gate(outbox_files=3).reason == "outbox 3 files"
    assert ok_gate(outbox_files=1).safe is False


def test_gate_refuses_on_open_accept_line():
    # mutation proof 24: 4 idle beats, a fresh `running: []` 0.4 s old, and an `accepted` line 15 s after the
    # 4th beat with no terminal line -> refused on (c), never trusted from (a)+(b)
    four_idle = [hb(105), hb(75), hb(45), hb(15)]
    open_accept = line(0.5, "accepted implement 0c1f9727 — src/, test/ (max 60 turns)")
    result = ok_gate(journal_lines=four_idle + [line(600, "submitted implement for 3aa1c610"), open_accept])
    assert result.idle_beats == 4 and result.plane["running"] == 0          # (a) and (b) would have passed
    assert result.lifecycle_open is True
    assert not result.safe and result.reason == "task running 0c1f9727 · 0:00"
    # a terminal line after the accept clears (c)
    result = ok_gate(journal_lines=four_idle + [open_accept, line(0.2, "submitted implement for 0c1f9727")])
    assert result.lifecycle_open is False and result.safe


def test_gate_refuses_when_outbox_unreadable():
    # mutation proof 28: an unreadable outbox is `gate unknown`, never "no blocker" (spec §11 (d) fail closed)
    result = ok_gate(outbox_files=None)
    assert not result.safe and result.unknown == "outbox" and result.reason == "gate unknown: outbox unreadable"
    # unknown outranks every other reading, so a typed ack has nothing to override
    result = ok_gate(outbox_files=None, journal_lines=[hb(11, "1 task running")])
    assert result.unknown == "outbox"


def test_gate_refuses_when_unit_state_unknown_or_inactive():
    # spec §11 (e): docker inspect timed out 2 of 3 cycles -> unknown is `gate_unknown(unit)`, never "no blocker"
    result = ok_gate(unit_active=None)
    assert not result.safe and result.unknown == "unit" and result.reason == "gate unknown: unit unreadable"
    assert ok_gate(unit_active=False).reason == "unit inactive"


def test_plane_half_is_local_only_when_offline_failed_or_stale():
    # spec §11 (b): a failed read, `offline: true`, or a read older than GATE_STANDING_MAX_AGE_S -> local-only
    assert GATE_STANDING_MAX_AGE_S == 2.0
    assert ok_gate(offline=True).plane == {"mode": "local-only", "running": None, "as_of": None, "standing_age_s": None}
    assert ok_gate(standing=None).plane["mode"] == "local-only"
    stale = {"running_count": 0, "at": gate.iso_utc_ms(NOW - 25)}
    result = ok_gate(standing=stale)
    assert result.plane["mode"] == "local-only" and result.plane["standing_age_s"] == 25.0
    assert ok_gate(offline=True).safe is True           # local checks pass; the broker demands the typed ack
    assert ok_gate(standing={"running_count": 1, "at": gate.iso_utc_ms(NOW - 0.3)}).reason == "plane reports 1 running"
# ---------------------------------------------------------------- the dropped urllib child (Task 6.5)

import urllib.error  # noqa: E402

from imd_dashd.gate import fetch_standing_running  # noqa: E402


class _Response:
    def __init__(self, body: object, status: int = 200) -> None:
        self._body = json.dumps(body).encode()
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_fetch_standing_running_returns_only_the_count_and_retries_once(monkeypatch):
    # spec §11 (b): "returns only {running_count, at} to root"; retry once on failure
    calls: list[str] = []
    bodies = iter([urllib.error.URLError("boom"), _Response({"standing": {"running": [{"jobId": "j", "objective": "secret prose"}]}})])

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        item = next(bodies)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(gate, "_urlopen", fake_urlopen)
    result = fetch_standing_running("https://api.imd.fun/seats/7/standing", timeout_s=8)
    assert set(result) == {"running_count", "at"} and result["running_count"] == 1
    assert gate.parse_iso(result["at"]) is not None and result["at"][-5] == "."   # millisecond stamp
    assert calls == ["https://api.imd.fun/seats/7/standing"] * 2
    assert "objective" not in json.dumps(result)


def test_fetch_standing_running_raises_after_two_failures_and_on_bad_shape(monkeypatch):
    monkeypatch.setattr(gate, "_urlopen", lambda request, timeout: _Response({"standing": {}}))
    with pytest.raises(ValueError):
        fetch_standing_running("https://api.imd.fun/seats/7/standing")
    monkeypatch.setattr(gate, "_urlopen", lambda request, timeout: _Response({"error": "shm"}, status=500))
    with pytest.raises(urllib.error.HTTPError):
        fetch_standing_running("https://api.imd.fun/seats/7/standing")


def test_main_prints_one_json_line_and_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(gate, "_urlopen", lambda request, timeout: _Response({"standing": {"running": []}}))
    assert gate.main(["--standing", "https://api.imd.fun/seats/7/standing"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and json.loads(out)["running_count"] == 0

    def down(request, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(gate, "_urlopen", down)
    assert gate.main(["--standing", "https://api.imd.fun/seats/7/standing", "--timeout", "1"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "URLError"}
# ---------------------------------------------------------------- the gate as the broker applies it (Task 6.10; spec §11 (b), (d))

from tests.broker._harness import PYTHON, Journal, audit_lines, call, make_broker  # noqa: E402  (broker-level halves of proofs 7 and 28)


def test_local_only_gate_needs_typed_ack(tmp_path):
    # mutation proof 7 (drop the plane half): a plan under --offline (or a failed standing read) is `local-only`
    # and apply needs the typed `local-only` ack; a redeploy wave must not block a 3 a.m. restart (spec §11 (b))
    broker, runner, _journal, _clock, audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": True})["plan"]
    assert plan["preconditions"]["plane"] == {"mode": "local-only", "running": None, "as_of": None, "standing_age_s": None}
    assert runner.argvs(PYTHON, "-I") == []                                      # no standing child under offline
    refused = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert refused["error"] == "local_only_ack_required" and refused["detail"]["ack"] == "local-only"
    assert runner.argvs("systemctl", "restart") == []
    plan = call(broker, "restart", {"offline": True})["plan"]
    applied = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "local_only_ack": "local-only"})
    assert applied["ok"] and applied["result"]["preconditions"]["plane"]["mode"] == "local-only"
    assert len(runner.argvs("systemctl", "restart")) == 1
    # a failed standing read (not offline) is local-only too
    runner.script[(PYTHON, "-I", broker._broker_dir + "/gate.py")] = (1, '{"error":"URLError"}\n')
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert plan["preconditions"]["plane"]["mode"] == "local-only"
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["error"] == "local_only_ack_required"
    assert audit_lines(audit)[-1]["outcome"] == "local_only_ack_required"


def test_gate_unknown_outbox_cannot_be_acked(tmp_path):
    # mutation proof 28, broker half: `ls outbox` fails -> gate_unknown(outbox); no ack, no --force overrides it
    broker, runner, _journal, _clock, audit = make_broker(tmp_path, script={("ls", "-1A"): (2, "")})
    refused = call(broker, "restart", {"offline": True})
    assert refused["error"] == "gate_unknown(outbox)" and refused["detail"]["reason"] == "gate unknown: outbox unreadable"
    assert audit_lines(audit)[-1]["outcome"] == "gate_unknown(outbox)"
    # even a plan made while the outbox was readable is re-read fresh at apply
    runner.script[("ls", "-1A")] = (0, "")
    plan = call(broker, "restart", {"offline": True})["plan"]
    runner.script[("ls", "-1A")] = (2, "")
    late = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "local_only_ack": "local-only"})
    assert late["error"] == "gate_unknown(outbox)" and runner.argvs("systemctl", "restart") == []
    # and a docker-style unit unknown is the same class (spec §11 (e))
    broker2, _r, _j, _c, _a = make_broker(tmp_path / "b", script={("systemctl", "is-active", "imd-worker.service"): (0, "")})
    assert call(broker2, "restart", {"offline": True})["error"] == "gate_unknown(unit)"


def test_failed_lifecycle_read_is_unknown_but_successful_empty_is_idle():
    assert ok_gate(journal_lines=IDLE_9).safe
    missing = ok_gate(journal_lines=IDLE_9, lifecycle_read_succeeded=False)
    assert not missing.safe and missing.unknown == 'lifecycle'
    assert missing.last_lifecycle_line is None and missing.lifecycle_open is None
    aged = line(7 * 86400, 'submitted implement for 0c1f9727')
    assert ok_gate(journal_lines=[aged] + IDLE_9).safe
    opened = ok_gate(journal_lines=[aged] + IDLE_9 + [line(1, 'accepted question deadbeef')])
    assert not opened.safe and opened.lifecycle_open is True


def test_stale_positive_standing_never_allows_an_idle_gate():
    result = ok_gate(standing={"running_count": 2, "at": gate.iso_utc_ms(NOW - 25)})
    assert not result.safe and result.reason == "plane reports 2 running"
    assert result.plane["mode"] == "local-only"
    assert result.plane["running"] == 2


@pytest.mark.parametrize("kind", ["task", "question", "campaign"])
def test_local_executor_failure_closes_lifecycle(kind):
    failed = line(150, f"{kind} failed: executor threw")
    accepted = line(200, "accepted question deadbeef")
    result = ok_gate(journal_lines=[accepted, failed] + IDLE_9)
    assert result.safe and result.lifecycle_open is False
    assert result.last_lifecycle_line == failed[1]


@pytest.mark.parametrize("fixture", ["local_fail_empty.txt", "local_fail_stripped.txt"])
def test_empty_local_failure_fixtures_are_terminal(fixture):
    from pathlib import Path
    rows = (Path(__file__).parents[1] / "fixtures/seat/grammar" / fixture).read_text().splitlines()
    for kind in ("task", "question", "campaign"):
        failed = rows[-1].replace("question failed", kind + " failed")
        assert newest_lifecycle([rows[0], failed]) == (failed, False)
