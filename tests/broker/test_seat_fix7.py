"""Measured round-7 doctor output: preserve lines, normalize only the summary reason."""
from pathlib import Path

from tests.broker._harness import call, make_broker, transient

DOCTOR = Path(__file__).resolve().parents[1] / "fixtures/seat/cli/2a548252/imd_doctor.txt"


def test_root_doctor_indented_host_summary_reaches_reason(tmp_path):
    output = DOCTOR.read_text()
    broker, *_ = make_broker(tmp_path, script={("systemd-run",): transient(output, rc=1)})
    plan = call(broker, "doctor")["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker._threads[plan["plan_id"]].join(timeout=5)
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False
    assert data["verify_lines"] == output.splitlines()
    assert data["verify_lines"][-1] == "  1 thing to fix: memory"
    assert data["reason"] == "exit 1 · 1 thing to fix: memory"


def test_doctor_summary_is_stripped_before_200_character_cap():
    from imd_dashd.imd_dashd import _transient_reason
    summary = "2 things to fix: " + "x" * 250
    assert _transient_reason("doctor", 1, ["  " + summary + "  "]) == "exit 1 · " + summary[:200]
