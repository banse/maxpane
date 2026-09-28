"""``imd_dashd/child_unit.py`` -- transient units and in-process children, byte-for-byte (spec §4.1a, §4.1b)."""
from __future__ import annotations

import subprocess

from imd_dashd.child_unit import (
    CHILD_CWD, CHILD_ENV, RUNTIME_MAX_S, SUBPROCESS_BELT_S, TRANSIENT_PROPERTIES, ChildResult, read_ip_address_deny,
    run_inprocess, run_transient, transient_argv, unit_name,
)
from tests.broker._recorder import RecordingRunner, timeout_for

IP_DENY = "169.254.0.0/16 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 fc00::/7 fe80::/10 192.0.2.10 192.0.2.11"


def test_transient_argv_env_is_exactly_the_four_keys():
    # spec §4.1a: HOME, PATH, NO_COLOR, LANG "and nothing else"; cwd /tmp
    assert CHILD_ENV == {"HOME": "/home/imd-worker",
                         "PATH": "/opt/imd-worker/bin:/opt/imd-worker/node/bin:/usr/local/bin:/usr/bin:/bin",
                         "NO_COLOR": "1", "LANG": "C.UTF-8"}
    assert CHILD_CWD == "/tmp"
    argv = transient_argv("status", 17, ["imd", "status"], ip_address_deny=IP_DENY, runtime_max_s=30)
    setenvs = [a for a in argv if a.startswith("--setenv=")]
    assert setenvs == ["--setenv=HOME=/home/imd-worker",
                       "--setenv=PATH=/opt/imd-worker/bin:/opt/imd-worker/node/bin:/usr/local/bin:/usr/bin:/bin",
                       "--setenv=NO_COLOR=1", "--setenv=LANG=C.UTF-8"]
    assert "--working-directory=/tmp" in argv
    # the in-process child gets the same dict object-for-object
    runner = RecordingRunner()
    run_inprocess(["ls", "-1A", "/home/imd-worker/.identitymd/outbox"], run=runner, timeout_s=5)
    (_, kw), = runner.calls
    assert kw["env"] == CHILD_ENV and set(kw["env"]) == {"HOME", "PATH", "NO_COLOR", "LANG"}
    assert kw["cwd"] == "/tmp" and kw["timeout"] == 5
    assert kw["user"] == "imd-worker" and kw["group"] == "imd-worker" and kw["extra_groups"] == []


def test_transient_properties_in_order():
    # spec §4.1b property list, in order, plus the contract's BindReadOnlyPaths=/opt/imd-dash/broker (C.11)
    assert TRANSIENT_PROPERTIES == (
        "NoNewPrivileges=yes", "UMask=0077", "PrivateTmp=yes", "ProtectSystem=strict", "ProtectHome=tmpfs",
        "BindPaths=/home/imd-worker", "TemporaryFileSystem=/opt:ro", "BindReadOnlyPaths=/opt/imd-worker",
        "BindReadOnlyPaths=/opt/imd-dash/broker",
        "InaccessiblePaths=/run/dbus", "InaccessiblePaths=/run/systemd/private", "InaccessiblePaths=/run/imd-dash",
        "InaccessiblePaths=/home/imd-dash", "InaccessiblePaths=/var/log/imd-dash",
    )
    argv = transient_argv("doctor", 3, ["imd", "doctor"], ip_address_deny=IP_DENY, runtime_max_s=120)
    expected = ["systemd-run", "--uid=imd-worker", "--gid=imd-worker", "--wait", "--collect", "--pipe", "--quiet",
                "--unit=imd-dash-doctor-3", "--working-directory=/tmp",
                "--setenv=HOME=/home/imd-worker",
                "--setenv=PATH=/opt/imd-worker/bin:/opt/imd-worker/node/bin:/usr/local/bin:/usr/bin:/bin",
                "--setenv=NO_COLOR=1", "--setenv=LANG=C.UTF-8"]
    for prop in TRANSIENT_PROPERTIES:
        expected += ["-p", prop]
    expected += ["-p", f"IPAddressDeny={IP_DENY}", "-p", "MemoryMax=512M", "-p", "TasksMax=64", "-p", "RuntimeMaxSec=120",
                 "--", "imd", "doctor"]
    assert argv == expected                                   # byte-for-byte
    assert unit_name("skills-set", 9) == "imd-dash-skills-set-9"


def test_runtime_max_per_verb_matches_the_spec():
    # spec §5.3 / §11: whoami 20, status 30, skills 30, tools 20, sessions 60, doctor 120 (90 s smoke + ~30 s checks), skills-set 30
    assert RUNTIME_MAX_S == {"whoami": 20, "status": 30, "skills": 30, "tools": 20, "sessions": 60, "doctor": 120, "skills-set": 30}
    assert SUBPROCESS_BELT_S == 15


def test_run_transient_uses_the_belt_and_kills_the_unit_on_timeout():
    # spec §4.1b: subprocess.run(timeout=RuntimeMaxSec + 15) is the belt; on timeout `systemctl kill --signal=KILL <unit>`
    runner = RecordingRunner({("systemd-run",): timeout_for(["systemd-run"], 135)})
    result = run_transient("doctor", 4, ["imd", "doctor"], run=runner, ip_address_deny=IP_DENY)
    assert isinstance(result, ChildResult) and result.timed_out and result.rc is None
    assert result.unit == "imd-dash-doctor-4" and result.stdout == b"partial"
    first, second = runner.calls
    assert first[1]["timeout"] == 120 + 15 and first[1]["capture_output"] is True
    assert second[0] == ["systemctl", "kill", "--signal=KILL", "imd-dash-doctor-4.service"] and second[1]["timeout"] == 5


def test_run_transient_returns_output_and_rc():
    runner = RecordingRunner({("systemd-run",): subprocess.CompletedProcess([], 0, b"72b617d4" + b"0" * 56 + b"\n", b"")})
    result = run_transient("whoami", 1, ["imd", "whoami"], run=runner, ip_address_deny=IP_DENY, stdin=None)
    assert result.rc == 0 and result.stdout.startswith(b"72b617d4") and not result.timed_out
    assert runner.calls[0][1]["timeout"] == 20 + 15
    assert runner.calls[0][0][-2:] == ["imd", "whoami"]


def test_run_inprocess_timeout_is_reported_not_raised():
    runner = RecordingRunner({("ls",): timeout_for(["ls"], 5)})
    result = run_inprocess(["ls", "-1A", "/home/imd-worker/.identitymd/outbox"], run=runner, timeout_s=5)
    assert result.timed_out and result.rc is None and result.unit is None


def test_read_ip_address_deny_copies_the_worker_unit_value_or_none():
    # spec §4.1b: read at broker start; a failed read -> None -> child_posture_unavailable for runtime verbs
    runner = RecordingRunner({("systemctl", "show"): (0, IP_DENY + "\n")})
    assert read_ip_address_deny(run=runner) == IP_DENY
    assert runner.calls[0][0] == ["systemctl", "show", "imd-worker.service", "-p", "IPAddressDeny", "--value"]
    assert runner.calls[0][1]["timeout"] == 5
    assert read_ip_address_deny(run=RecordingRunner({("systemctl", "show"): (1, "")})) is None
    assert read_ip_address_deny(run=RecordingRunner({("systemctl", "show"): (0, "\n")})) is None
    assert read_ip_address_deny(run=RecordingRunner({("systemctl", "show"): timeout_for(["systemctl"], 5)})) is None
    assert read_ip_address_deny(run=RecordingRunner({("systemctl", "show"): FileNotFoundError("systemctl")})) is None
