"""Fourth-round regressions against scripted local sources, never a live worker."""
import json
import subprocess

import pytest

from imd_dashd import imd_dashd as root
from imd_dashd import gate
from tests.broker._harness import call, make_broker, msg
from tests.data.test_seat_broker_client import _local
from maxpane_dashboard.data.seat_broker_client import BrokerError
from maxpane_dashboard.data import seat_log_grammar as grammar
from maxpane_dashboard.data.seat_ledger import SeatLedger


ACCEPTS = [
    ("accepted review deadbeef —  (max 60 turns)", "accepted_code", "review", "code", 60),
    ("accepted implement deadbeef — src/", "accepted_code_head", "implement", "code", None),
    ("accepted tests deadbeef —", "accepted_code_head", "tests", "code", None),
    ("accepted review deadbeef — ", "accepted_code_head", "review", "code", None),
    ("accepted campaign deadbeef — harness", "accepted_fuzz_head", "campaign", "fuzz", None),
    ("accepted campaign deadbeef —", "accepted_fuzz_head", "campaign", "fuzz", None),
]


def apply(broker, plan, **extra):
    return call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], **extra})


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_all_accept_forms_open_the_ledger(tmp_path, body, kind, role, task_kind, turns):
    line = grammar.classify(msg(1790000000, body)[1])
    assert line.kind == kind
    if turns is not None:
        assert line.fields["paths"] == "" and line.fields["max_turns"] == str(turns)
    ledger = SeatLedger(tmp_path / "ledger.sqlite", seat=7, now=lambda: 1790000005)
    try:
        result = ledger.ingest([line])
        assert result.opened == 1
        row = ledger.open_row()
        assert row["nodeId8"] == "deadbeef" and row["role"] == role and row["kind"] == task_kind
        assert ledger.rows()[0]["maxTurns"] == turns
    finally:
        ledger.close()


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_root_accept_forms_block_and_matching_force_works(tmp_path, body, kind, role, task_kind, turns):
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    plan = call(broker, "restart")["plan"]
    journal.add(msg(clock() - 5, body))
    answer = apply(broker, plan)
    assert answer["error"] == "gate_blocked"
    assert answer["detail"]["reason"] == "task running deadbeef · 0:05"
    assert answer["detail"]["preconditions"]["lifecycle_open"] is True
    assert not runner.argvs("systemctl", "restart")
    forced = call(broker, "restart", {"force_node8": "deadbeef"})["plan"]
    assert apply(broker, forced, force_node8="deadbeef")["ok"]
    assert runner.argvs("systemctl", "restart")


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_mac_accept_forms_block_apply(tmp_path, body, kind, role, task_kind, turns):
    broker, runner, lines, clock = _local(tmp_path)
    plan = broker.plan("restart")
    lines.append(msg(clock() - 5, body))
    with pytest.raises(BrokerError) as caught:
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    assert caught.value.code == "gate_blocked"
    assert caught.value.detail["reason"] == "task running deadbeef · 0:05"
    assert caught.value.detail["preconditions"]["lifecycle_open"] is True
    assert not runner.argvs("docker", "restart")


@pytest.mark.parametrize("body", [
    "accepted review deadbeef — src (max 60 turns) trailing",
    "accepted campaign deadbeef — harness (20 runs) trailing",
])
def test_completed_tail_with_trailing_prose_never_becomes_a_head(body):
    text = msg(1790000000, body)[1]
    assert grammar.classify(text).kind == grammar.KIND_UNKNOWN
    assert gate.newest_lifecycle([text]) == (None, None)


@pytest.mark.parametrize("byte_count,all_fields,expect_null", [(4087, False, False), (4088, False, True), (4100, True, False)])
def test_journal_fake_filters_full_message_before_systemd_size_limit(byte_count, all_fields, expect_null):
    from tests.broker._harness import Journal, NOW
    prefix = msg(NOW, "task failed: ")[1]
    # The boundary is UTF-8 bytes, not characters.
    text = prefix + "é" * ((byte_count - len(prefix.encode())) // 2)
    text += "x" * (byte_count - len(text.encode()))
    journal = Journal([(NOW, text)])
    argv = ["journalctl", "--grep", "task failed: .+", "--lines", "1"] + (["--all"] if all_fields else [])
    result = journal(argv, {})
    assert result.returncode == 0
    message = json.loads(result.stdout)["MESSAGE"]
    assert (message is None) is expect_null
    if not expect_null:
        assert message == text


@pytest.mark.parametrize("cursor", [None, "s=deadbeef;i=0"])
def test_follower_preserves_long_terminal_and_closes_ledger(tmp_path, cursor):
    from tests.broker._harness import Journal, NOW
    from tests.data.test_seat_tail import _Proc
    from maxpane_dashboard.data.seat_tail import JournaldSource
    accepted = msg(NOW - 10, "accepted implement deadbeef — src (max 60 turns)")
    terminal = msg(NOW - 1, "task failed: " + "z" * 4100)
    journal = Journal([accepted, terminal])
    def popen(argv, **kw):
        done = journal(argv, kw)
        return _Proc(done.stdout, done.returncode)
    source = JournaldSource(cursor=cursor, since="-600s", popen=popen)
    ledger = SeatLedger(tmp_path / "ledger.sqlite", seat=7, now=lambda: NOW)
    try:
        ledger.ingest([grammar.classify(accepted[1], cursor=Journal.cursor(0), invocation="inv0001")])
        source.open()
        parsed = [grammar.classify(raw.text, cursor=raw.cursor, invocation=raw.invocation)
                  for raw in source.lines() if raw is not None]
        ledger.ingest(parsed)
        assert ledger.open_row() is None
        assert ledger.state.last_lifecycle.kind == "local_fail"
        assert ledger.state.last_lifecycle.fields["msg"] == "z" * 4100
        # The same journal without --all demonstrates the actual loss, independent of argv assertions.
        argv = [arg for arg in source.argv() if arg != "--all"]
        hidden = journal(argv, {})
        decoded = [JournaldSource._parse_record(line) for line in hidden.stdout.decode().split("\n") if line]
        assert decoded[-1].text == ""
    finally:
        source.close()
        ledger.close()
