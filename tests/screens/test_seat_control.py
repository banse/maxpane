"""The CONTROL modal (spec §8 CONTROL, §11 TUI side; contract §C.16; header Review Focus #5).

Every broker call goes through ``FakeBroker`` (WP6) and is recorded in ``broker.calls``; the
assertions are on **which** verbs were called with **which** args, and on the composited text.

Mutation proofs: ``test_control_modal_never_replans_on_its_own`` -- make the verify tick call
``plan`` again when ``verified`` is ``False`` -> red; ``test_force_typed_twice_and_disabled_without_graceful_stop``
-- skip the second node8 check at apply, or plan a forced restart when ``gracefulStopPossible`` is
False -> red; ``test_local_only_gate_needs_the_typed_ack`` -- accept the four characters when the plane
half is local-only -> red; ``test_doctor_output_has_its_dollar_figure_stripped`` -- paint ``verify_lines``
raw -> red.
"""

from __future__ import annotations

import copy
import asyncio
import threading
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Input

from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.data.seat_broker_client import BrokerError, FakeBroker
from maxpane_dashboard.data.seat_models import fold_status_document
from maxpane_dashboard.screens.seat_control import (
    AUDIT_LINES,
    CONFIRM_CHARS,
    LOCAL_ONLY_ACK,
    STATIC_LINES,
    VERB_KEYS,
    SeatControlScreen,
    verb_lines,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
DOC = json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8"))
PLAN_ID = "7f3a9c1e2b4d6081"
SIZE = (120, 40)

PLAN = {"ok": True, "plan": {
    "plan_id": PLAN_ID, "verb": "restart", "argv": ["systemctl", "restart", "imd-worker.service"],
    "expires_at": "2026-09-26T03:41:12Z", "single_use": True,
    "preconditions": {"idle_beats": 9, "idle_beats_required": 4, "newest_heartbeat_age_s": 11,
                      "plane": {"mode": "plane+local", "running": 0, "as_of": "2026-09-26T03:40:09Z", "standing_age_s": 0.4},
                      "last_lifecycle_line": "2026-09-26T03:24:17.136Z submitted implement for 0c1f9727", "lifecycle_open": False,
                      "outbox_files": 0, "unit_active": True, "graceful_stop_possible": True},
    "warning": "a task assigned in the ~1–5 s between the gate's fresh reads and systemctl may be reported as a failed run; "
               "3 consecutive failed runs pause the seat 15 min (never measured: 16/16 historical restarts were idle)",
    "inverse": {"verb": "stop", "args": {}},
    "verify": {"verified_when": ["shutting down", "runtimes:"], "within_s": 30, "connected_when": "admitted (session", "reported_separately": True},
    "restart_required_after": False}}
APPLIED = {"ok": True, "result": {"outcome": "applied", "exit_code": 0, "cursor_before": "s=1;i=2", "audit_seq": 1287, "preconditions": PLAN["plan"]["preconditions"]}}
AUDIT = {"ok": True, "data": {"lines": [
    {"ts": "2026-09-25T11:45:41Z", "seq": 1280, "peer_uid": 1001, "verb": "restart", "phase": "plan", "plan_id": "1111aaaa2222bbbb", "outcome": "planned"},
    {"ts": "2026-09-25T11:45:43Z", "seq": 1281, "peer_uid": 1001, "verb": "restart", "phase": "apply", "plan_id": "1111aaaa2222bbbb", "outcome": "applied"},
]}}
PING = {"ok": True, "data": {"pid": 1, "version": "imd-dashd 0.1.0", "uptime_s": 3.0, "drain_armed": False, "in_flight": None, "posture_ok": True}}


def _verify_sequence(*results):
    """A verify responder that walks through *results* (each ``verified``/``connected``/``reason``) then repeats the last."""
    calls = []

    def respond(args):
        index = min(len(calls), len(results) - 1)
        calls.append(args)
        verified, connected, reason = results[index]
        return {"ok": True, "data": {"verified": verified, "connected": connected, "elapsed_s": 4.1 * (index + 1), "reason": reason,
                                     "verify_lines": ["03:40:31.101Z shutting down", "03:40:31.402Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)"] if verified else [],
                                     "cursor_after": "s=2;i=3", "audit_seq": 1288}}

    return respond


def _broker(**overrides) -> FakeBroker:
    responses = {"restart": PLAN, "stop": PLAN, "start": PLAN, "drain-restart": PLAN, "cancel-drain": PLAN, "enable-boot": PLAN, "disable-boot": PLAN,
                 "skills-set": PLAN, "kill-orphans": PLAN, "doctor": PLAN, "apply": APPLIED, "verify": _verify_sequence((None, None, None), (True, "pending (reconnecting since 03:40:31)", None), (True, True, None)),
                 "audit-tail": AUDIT, "ping": PING}
    responses.update(overrides)
    return FakeBroker(responses)


class _Manager:
    def __init__(self, doc: dict, broker: FakeBroker) -> None:
        self._doc = doc
        self.broker = broker
        self._error_count = 0
        #: ``SeatManager.plan_open`` (WP7): the standing tier polls every 15 s while a plan is open.
        self.plan_open = False
        #: every ``SeatManager.set_restart_required(flag)`` call the modal made
        self.restart_required_calls: list[bool] = []

    def set_restart_required(self, flag: bool) -> None:
        self.restart_required_calls.append(flag)

    def document(self) -> dict:
        return copy.deepcopy(self._doc)

    async def fetch_and_compute(self) -> dict:
        return fold_status_document(self.document())

    async def close(self) -> None:
        pass


class _A(App):
    from maxpane_dashboard.screens.seat import SeatScreen
    CSS = SeatScreen.DEFAULT_CSS
    def __init__(self, manager, flat=None, on_payload=None) -> None:
        super().__init__()
        self._manager, self._flat, self._on_payload = manager, flat, on_payload

    def on_mount(self) -> None:
        self.push_screen(SeatControlScreen(self._manager, flat=self._flat, poll_s=0.01, now=lambda: 1_790_000_000.0,
                                           on_payload=self._on_payload))


def _doc(**control) -> dict:
    doc = copy.deepcopy(DOC)
    doc["control"].update(control)
    return doc


def _screen_text(pilot) -> str:
    return "\n".join("".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips())


async def _painted(pilot) -> None:
    """Wait for pending workers and an actual render callback, with bounded failure."""
    await asyncio.wait_for(pilot.app.workers.wait_for_complete(), 3)
    painted = asyncio.Event()
    pilot.app.screen.call_after_refresh(painted.set)
    pilot.app.screen.refresh()
    await asyncio.wait_for(painted.wait(), 3)


async def _type(pilot, text: str) -> None:
    pilot.app.screen.query_one(Input).value = text
    await pilot.press("enter")
    await _painted(pilot)
    await _painted(pilot)


def _calls(broker: FakeBroker, verb: str) -> list[dict]:
    return [args for v, args in broker.calls if v == verb]


# -- the verb list and the static lines ----------------------------------------------------


def test_verb_keys_and_static_lines_are_the_contract_s():
    assert VERB_KEYS == {"r": "restart", "d": "drain-restart", "s": "stop", "S": "start", "b": "enable-boot", "k": "skills-set",
                         "o": "kill-orphans", "D": "doctor", "x": "cancel-drain"}
    assert STATIC_LINES[0].startswith("tiers: shown above (CONFIG)") and "runbook §2.1" in STATIC_LINES[0]
    assert STATIC_LINES[1] == "capacity: 1 by decision — drop-in + drained restart — runbook §4c"
    assert STATIC_LINES[2] == "update: {installed} → {available} — runbook §2.1 (drained restart)"
    assert CONFIRM_CHARS == 4 and AUDIT_LINES == 5 and LOCAL_ONLY_ACK == "local-only"


def test_verb_lines_carry_the_live_gate_words():
    flat = fold_status_document(DOC)
    lines = [t.plain for t in verb_lines(flat)]
    # ``_clock`` renders local time (``as_of_hhmm``): build the stamp the same way, never a hardcoded UTC clock.
    stamp = as_of_hhmm("2026-09-26T03:24:17.136Z")
    assert lines[0].startswith(f"[r] restart — safe now (idle 9 beats · plane running: none · last line submitted {stamp} · outbox 0)")
    assert "[d] drain-restart — waits for 4 idle beats, then restarts (armed: no)" in lines
    assert "[b] enable at boot — disabled" in lines
    assert "[k] skill on/off — restart required" in lines
    assert "[o] kill orphans — 0 candidates" in lines
    assert any(l.startswith("[D] doctor — spends one runtime turn") for l in lines)
    blocked = fold_status_document(_doc(gate={**DOC["control"]["gate"], "safe": False, "reason": "task running 0c1f9727 · 0:42", "lifecycleOpen": True}))
    blocked["seat_unit_graceful_stop_possible"] = False
    assert [t.plain for t in verb_lines(blocked)][0] == "[r] restart — BLOCKED: task running 0c1f9727 · 0:42 · force disabled (no init)"
    busy = fold_status_document(_doc(inFlight={"verb": "restart", "planId": PLAN_ID, "sinceUtc": "2026-09-26T03:40:30Z"}))
    assert [t.plain for t in verb_lines(busy)][0] == "[r] restart — BUSY: plan 7f3a in flight"
    unreachable = fold_status_document(_doc(brokerReachable=False))
    assert all("broker unreachable — read-only" in t.plain for t in verb_lines(unreachable))


async def test_the_modal_shows_verbs_static_lines_and_the_audit_footer():
    broker = _broker()
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        text = _screen_text(pilot)
        assert "CONTROL" in text and "[r] restart — safe now" in text
        assert "tiers: shown above (CONFIG)" in text and "capacity: 1 by decision" in text
        assert "update: 0.1.0+5bfa8261 → none — runbook §2.1 (drained restart)" in text
        assert "1281" in text or "apply" in text, "the audit footer shows the last lines"
        assert _calls(broker, "audit-tail") == [{"n": AUDIT_LINES}]


# -- plan -> typed confirm -> apply -> verify -----------------------------------------------


async def test_restart_plans_confirms_applies_and_polls_verify_until_a_verdict():
    broker = _broker()
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        await _painted(pilot)
        await _painted(pilot)
        assert _calls(broker, "restart") == [{"offline": False}]
        text = _screen_text(pilot)
        assert f"plan {PLAN_ID[:4]}" in text and "systemctl restart imd-worker.service" in text
        assert "idle_beats 9" in text and "standing_age_s 0.4" in text and "last_lifecycle_line" in text and "inverse: stop" in text
        # the modal's ~112-cell content width wraps the warning between "failed" and "run"; this fragment stays on one line
        assert "may be reported as a" in text
        assert pilot.app.screen.mode == "planned"
        await _type(pilot, "zzzz")
        assert _calls(broker, "apply") == [], "a wrong confirm never reaches the broker"
        assert f"type {PLAN_ID[:4]}" in _screen_text(pilot)
        await _type(pilot, PLAN_ID[:4])
        assert _calls(broker, "apply") == [{"plan_id": PLAN_ID, "confirm": PLAN_ID[:4]}]
        for _ in range(30):
            await _painted(pilot)
            if pilot.app.screen.mode == "done":
                break
        assert pilot.app.screen.mode == "done"
        text = _screen_text(pilot)
        assert "verified ✓" in text and "connected: pending (reconnecting since 03:40:31)" in text or "connected: yes" in text
        assert len(_calls(broker, "verify")) >= 2 and len(_calls(broker, "audit-tail")) >= 2
        assert _calls(broker, "restart") == [{"offline": False}], "one plan, ever"


async def test_control_modal_never_replans_on_its_own():
    # header Review Focus #5: verify never sees `shutting down` -> verified False with a reason; no automatic re-plan, no re-apply
    broker = _broker(verify=_verify_sequence((None, None, None), (False, None, "no shutting down within 30 s")))
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        await _painted(pilot)
        await _type(pilot, PLAN_ID[:4])
        for _ in range(40):
            await _painted(pilot)
        text = _screen_text(pilot)
        assert "verify: not seen — check LOG" in text and "no shutting down within 30 s" in text
        assert _calls(broker, "restart") == [{"offline": False}]
        assert len(_calls(broker, "apply")) == 1
        assert pilot.app.screen.mode == "done"


async def test_a_broker_error_is_shown_and_never_retried():
    def refuse(args):
        raise BrokerError("busy", {"verb": "restart", "plan_id": PLAN_ID, "since": "2026-09-26T03:40:30Z"})

    broker = _broker(restart=refuse)
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        for _ in range(20):
            await _painted(pilot)
        assert "error: busy" in _screen_text(pilot) and pilot.app.screen.mode == "idle"
        assert len(_calls(broker, "restart")) == 1


# -- force: typed twice, disabled without a graceful stop -------------------------------------


async def test_force_typed_twice_and_disabled_without_graceful_stop():
    running = _doc(gate={**DOC["control"]["gate"], "safe": False, "reason": "task running 0c1f9727 · 0:42", "lifecycleOpen": True})
    running["current"] = {"nodeId8": "0c1f9727", "jobId": None, "role": "implement", "kind": "code", "phase": "working", "startedUtc": "2026-09-26T03:39:30Z",
                          "elapsedS": 42, "maxTurns": 60, "model": "gpt-6-luna", "tierDerived": "economy/standard", "lastMessage": None,
                          "lastMessageUtc": None, "planeSince": None, "objective": None, "nodeKey": "oracle_assess"}
    broker = _broker()
    async with _A(_Manager(running, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        await _painted(pilot)
        assert _calls(broker, "restart") == [], "a blocked gate plans nothing until the running node8 is typed"
        assert "type the running node8" in _screen_text(pilot) and pilot.app.screen.mode == "force"
        await _type(pilot, "deadbeef")
        assert _calls(broker, "restart") == []
        await _type(pilot, "0c1f9727")
        assert _calls(broker, "restart") == [{"offline": False, "force_node8": "0c1f9727"}]
        await _type(pilot, PLAN_ID[:4])
        assert _calls(broker, "apply") == [], "a forced plan is applied by typing the node8 a second time, never the plan id"
        await _type(pilot, "0c1f9727")
        assert _calls(broker, "apply") == [{"plan_id": PLAN_ID, "confirm": PLAN_ID[:4], "force_node8": "0c1f9727"}]
    ungraceful = copy.deepcopy(running)
    ungraceful["unit"]["gracefulStopPossible"] = False
    ungraceful["unit"]["stopTimeoutS"] = 10
    broker = _broker()
    async with _A(_Manager(ungraceful, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        await _painted(pilot)
        assert "force disabled" in _screen_text(pilot) and pilot.app.screen.mode == "idle"
        await _type(pilot, "0c1f9727")
        assert _calls(broker, "restart") == []


async def test_local_only_gate_needs_the_typed_ack():
    local = copy.deepcopy(PLAN)
    local["plan"]["preconditions"]["plane"] = {"mode": "local-only", "running": None, "as_of": None, "standing_age_s": None}
    broker = _broker(restart=local)
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("r")
        await _painted(pilot)
        await _type(pilot, PLAN_ID[:4])
        assert _calls(broker, "apply") == [] and f"type {LOCAL_ONLY_ACK}" in _screen_text(pilot)
        await _type(pilot, LOCAL_ONLY_ACK)
        assert _calls(broker, "apply") == [{"plan_id": PLAN_ID, "confirm": PLAN_ID[:4], "local_only_ack": LOCAL_ONLY_ACK}]


# -- the other verbs -----------------------------------------------------------------------------


async def test_skills_set_takes_a_typed_id_gated_by_the_regex():
    broker = _broker()
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("k")
        await _painted(pilot)
        assert pilot.app.screen.mode == "skill" and "type <skill-id> on|off" in _screen_text(pilot)
        await _type(pilot, "bad id; rm -rf / off")
        assert _calls(broker, "skills-set") == [] and "invalid skill id" in _screen_text(pilot)
        await _type(pilot, "oracle-assess off")
        assert _calls(broker, "skills-set") == [{"skill_id": "oracle-assess", "on": False}]
        assert pilot.app.screen.mode == "planned"


async def test_boot_flips_between_enable_and_disable_and_orphans_carry_their_pids():
    doc = copy.deepcopy(DOC)
    doc["unit"]["bootEnabled"] = True
    doc["machine"]["orphans"] = [{"pid": 64861, "pgid": 64861, "uid": 1000, "cgroup": "user-0.slice/session-147.scope", "ageS": 127000, "rssB": 130000000,
                                  "cmd": "codex exec", "pgidMembers": [{"pid": 64855, "uid": 0, "cgroup": "user-0.slice/session-147.scope", "cmd": "runuser"}]}]
    broker = _broker()
    async with _A(_Manager(doc, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        assert "[b] disable at boot — enabled" in _screen_text(pilot)
        assert "[o] kill orphans — 1 candidate (1 pgid member shown)" in _screen_text(pilot)
        await pilot.press("b")
        await _painted(pilot)
        assert _calls(broker, "disable-boot") == [{}]
        await pilot.press("escape")
        await _painted(pilot)
    broker = _broker()
    async with _A(_Manager(doc, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("o")
        await _painted(pilot)
        assert _calls(broker, "kill-orphans") == [{"pids": [64861]}]


async def test_unreachable_broker_greys_every_verb_and_ignores_keys():
    broker = FakeBroker({"audit-tail": AUDIT}, reachable=False)
    async with _A(_Manager(_doc(brokerReachable=False), broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        assert "broker unreachable — read-only" in _screen_text(pilot)
        await pilot.press("r")
        await _painted(pilot)
        assert _calls(broker, "restart") == []


async def test_skills_set_apply_marks_restart_required_and_offers_drain():
    # spec §11 skills set: R -- sets restartRequired; CONTROL offers drain-restart as step 2; spec §8 hero amber
    skills_plan = copy.deepcopy(PLAN)
    skills_plan["plan"].update(verb="skills-set", argv=["imd", "skills", "set", "oracle-assess", "off"], restart_required_after=True)
    started = {"ok": True, "result": {"outcome": "started", "exit_code": None, "cursor_before": None, "audit_seq": 1291, "preconditions": {}}}
    broker = _broker(**{"skills-set": skills_plan, "apply": started})
    manager = _Manager(DOC, broker)
    async with _A(manager).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("k")
        await _painted(pilot)
        await _type(pilot, "oracle-assess off")
        assert pilot.app.screen.mode == "planned"
        await _type(pilot, PLAN_ID[:4])
        for _ in range(30):
            await _painted(pilot)
            if manager.restart_required_calls:
                break
        assert manager.restart_required_calls == [True]
        # The note is the last line of ``#seat-control-status``, under the verified line and both verify_lines; at
        # 120x40 the 10-row skills-set plan block pushes it one row below the scroll area's fold (content 28 rows in a
        # 27-row viewport), so the modal's own status text is read -- the claim is that the note is offered, not where
        # the viewport happens to sit.
        assert "press [d] to drain-restart" in pilot.app.screen._status.plain


async def test_open_plan_sets_manager_plan_open_and_close_clears_it():
    # spec §6 standing row cadence: 15 s while a control plan is open (WP7 TIER_STANDING_PLAN_OPEN_S reads plan_open)
    manager = _Manager(DOC, _broker())
    async with _A(manager).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        assert manager.plan_open is False
        await pilot.press("r")
        for _ in range(10):
            await _painted(pilot)
            if pilot.app.screen.mode == "planned":
                break
        assert manager.plan_open is True
        await pilot.press("escape")
        await _painted(pilot)
        assert manager.plan_open is False


class _CyclingManager(_Manager):
    """Records ``plan_open`` at every ``fetch_and_compute`` and serves whatever document it holds now."""

    def __init__(self, doc: dict, broker: FakeBroker) -> None:
        super().__init__(doc, broker)
        self.cycles: list[bool] = []

    async def fetch_and_compute(self) -> dict:
        self.cycles.append(self.plan_open)
        return fold_status_document(self.document())


async def test_the_modal_runs_the_manager_cycle_so_gate_words_and_plan_open_are_live():
    # spec §8 CONTROL "verb list with live gate words" + spec §6 "15 s while a control plan is open": textual suspends the
    # PEPEPANE screen under a pushed modal (DashboardScreen.on_screen_suspend stops its refresh timer), so the modal's own tick
    # runs fetch_and_compute -- the gate changes between ticks, a cycle runs with plan_open True, and every flat is handed on
    manager = _CyclingManager(DOC, _broker())
    payloads: list[dict] = []
    async with _A(manager, on_payload=payloads.append).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        assert "[r] restart — safe now" in _screen_text(pilot)
        manager._doc = _doc(gate={**DOC["control"]["gate"], "safe": False, "reason": "task running 0c1f9727 · 0:42", "lifecycleOpen": True})
        for _ in range(30):
            await _painted(pilot)
            if "BLOCKED: task running 0c1f9727" in _screen_text(pilot):
                break
        assert "[r] restart — BLOCKED: task running 0c1f9727 · 0:42" in _screen_text(pilot), "gate words froze at open"
        assert manager.cycles and payloads, "no manager cycle ran while the modal was open"
        assert payloads[-1]["seat_control_gate"]["safe"] is False, "the flat reaches the PEPEPANE screen's panels too"
        manager._doc = copy.deepcopy(DOC)
        for _ in range(30):
            await _painted(pilot)
            if "[r] restart — safe now" in _screen_text(pilot):
                break
        await pilot.press("r")
        for _ in range(30):
            await _painted(pilot)
            if pilot.app.screen.mode == "planned" and manager.cycles[-1] is True:
                break
        assert manager.plan_open is True and manager.cycles[-1] is True, "a cycle ran with plan_open set (the 15 s cadence is scheduled)"


async def test_verb_keys_are_not_swallowed_by_the_confirm_field():
    # the Input is focused only while a prompt is open (force, skill, planned); idle, a verb key reaches action_verb
    broker = _broker()
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        assert not isinstance(pilot.app.focused, Input)
        await pilot.press("r")
        for _ in range(10):
            await _painted(pilot)
            if pilot.app.screen.mode == "planned":
                break
        assert _calls(broker, "restart") == [{"offline": False}]
        assert pilot.app.screen.query_one(Input).value == ""
        assert isinstance(pilot.app.focused, Input), "a planned verb opens the confirm field"


async def test_doctor_output_has_its_dollar_figure_stripped():
    def doctor_verify(args):
        return {"ok": True, "data": {"verified": True, "connected": None, "elapsed_s": 6.2, "reason": None, "audit_seq": 1290, "cursor_after": None,
                                     "verify_lines": ["runtime auth ok · smoke run 4.1 s · est. $0.070 (list price, not billed)", "memory 3.8 GiB < 8 GiB required by foundry"]}}

    broker = _broker(verify=doctor_verify, apply={"ok": True, "result": {"outcome": "started", "exit_code": None, "cursor_before": None, "audit_seq": 1289, "preconditions": {}}})
    async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
        await _painted(pilot)
        await pilot.press("D")
        await _painted(pilot)
        await _type(pilot, PLAN_ID[:4])
        for _ in range(30):
            await _painted(pilot)
            if pilot.app.screen.mode == "done":
                break
        text = _screen_text(pilot)
        assert "runtime auth ok" in text and "$" not in text


async def test_combined_force_and_local_only_require_both_typed_acknowledgements():
    doc = _doc(gate={**DOC["control"]["gate"], "safe": False,
                     "reason": "task running 0c1f9727", "lifecycleOpen": True})
    plan = copy.deepcopy(PLAN)
    plan["plan"]["preconditions"]["plane"]["mode"] = "local-only"
    broker = _broker(restart=plan)
    async with _A(_Manager(doc, broker)).run_test(size=SIZE) as pilot:
        await pilot.press("r")
        await _type(pilot, "0c1f9727")
        await _type(pilot, "local-only")
        assert not _calls(broker, "apply"), "the node8 must be typed again first"
        await _type(pilot, "0c1f9727")
        assert not _calls(broker, "apply"), "the local-only acknowledgement remains required"
        await _type(pilot, "local-only")
        assert _calls(broker, "apply") == [{"plan_id": PLAN_ID, "confirm": PLAN_ID[:4],
                                            "force_node8": "0c1f9727", "local_only_ack": "local-only"}]


@pytest.mark.parametrize("held_verb", ["apply", "verify"])
async def test_broker_apply_does_not_block_escape_or_issue_a_second_write(held_verb):
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def held_apply(_args):
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        return APPLIED if held_verb == "apply" else _verify_sequence((True, True, None))({})

    broker = _broker(**{held_verb: held_apply})
    try:
        async with _A(_Manager(DOC, broker)).run_test(size=SIZE) as pilot:
            await pilot.press("r")
            control = pilot.app.screen
            field = control.query_one(Input)
            field.value = PLAN_ID[:4]
            field.post_message(Input.Submitted(field, field.value))
            await asyncio.wait_for(entered.wait(), 1)
            try:
                field.value = PLAN_ID[:4]
                control.post_message(Input.Submitted(field, field.value))
                processed = asyncio.Event()
                control.call_later(processed.set)
                await asyncio.wait_for(processed.wait(), 1)
                assert len(_calls(broker, "apply")) == 1
                await asyncio.wait_for(pilot.press("escape"), 1)
                assert not isinstance(pilot.app.screen, SeatControlScreen)
                assert len(_calls(broker, "apply")) == 1
            finally:
                release.set()
    finally:
        release.set()
