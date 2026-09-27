"""Children of the broker (spec §4.1a child env, §4.1b transient units).

Two kinds. **Transient units** (``systemd-run``) for anything that executes ``imd`` or parses
hostile-size files: the child gets the worker unit's own posture (the property list below, plus the
``IPAddressDeny`` copied from the worker unit at broker start), its own cgroup and OOM domain, and
``RuntimeMaxSec`` so systemd kills the *whole* cgroup on a hang; the broker's ``subprocess.run``
timeout is the belt (``RuntimeMaxSec + 15``) and fires ``systemctl kill --signal=KILL`` on the unit.
**In-process children** (``Popen(user=imd-worker, group=imd-worker, extra_groups=[])``) for the
stdlib-only reads inside the 0700 worker home: the projection, ``ls outbox``, the standing child.

Both kinds get EXACTLY ``CHILD_ENV`` and ``cwd=/tmp`` (spec §4.1a; the recorder test asserts equality).
"""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]

CHILD_ENV = {"HOME": "/home/imd-worker",
             "PATH": "/opt/imd-worker/bin:/opt/imd-worker/node/bin:/usr/local/bin:/usr/bin:/bin",
             "NO_COLOR": "1", "LANG": "C.UTF-8"}                 # EXACTLY these four (spec §4.1a)
CHILD_CWD = "/tmp"
WORKER_USER = "imd-worker"
WORKER_GROUP = "imd-worker"
WORKER_UNIT = "imd-worker.service"
UNIT_PREFIX = "imd-dash-"
CHILD_MEMORY_MAX = "512M"
CHILD_TASKS_MAX = 64
SUBPROCESS_BELT_S = 15
RUNTIME_MAX_S = {"whoami": 20, "status": 30, "skills": 30, "tools": 20, "sessions": 60, "doctor": 120, "skills-set": 30}
TRANSIENT_PROPERTIES: tuple[str, ...] = (      # in this order, each rendered as "-p", value (spec §4.1b + contract BindReadOnlyPaths)
    "NoNewPrivileges=yes", "UMask=0077", "PrivateTmp=yes", "ProtectSystem=strict", "ProtectHome=tmpfs",
    "BindPaths=/home/imd-worker", "TemporaryFileSystem=/opt:ro", "BindReadOnlyPaths=/opt/imd-worker",
    "BindReadOnlyPaths=/opt/imd-dash/broker",
    "InaccessiblePaths=/run/dbus", "InaccessiblePaths=/run/systemd/private", "InaccessiblePaths=/run/imd-dash",
    "InaccessiblePaths=/home/imd-dash", "InaccessiblePaths=/var/log/imd-dash",
)


def unit_name(verb: str, seq: int) -> str:
    return f"{UNIT_PREFIX}{verb}-{seq}"


def transient_argv(verb: str, seq: int, argv: Sequence[str], *, ip_address_deny: str, runtime_max_s: int,
                   memory_max: str = CHILD_MEMORY_MAX, tasks_max: int = CHILD_TASKS_MAX) -> list[str]:
    out = ["systemd-run", f"--uid={WORKER_USER}", f"--gid={WORKER_GROUP}", "--wait", "--collect", "--pipe", "--quiet",
           f"--unit={unit_name(verb, seq)}", f"--working-directory={CHILD_CWD}"]
    for key in ("HOME", "PATH", "NO_COLOR", "LANG"):
        out.append(f"--setenv={key}={CHILD_ENV[key]}")
    for prop in TRANSIENT_PROPERTIES:
        out += ["-p", prop]
    out += ["-p", f"IPAddressDeny={ip_address_deny}", "-p", f"MemoryMax={memory_max}", "-p", f"TasksMax={tasks_max}",
            "-p", f"RuntimeMaxSec={runtime_max_s}", "--", *argv]
    return out


@dataclass(frozen=True)
class ChildResult:
    rc: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    unit: str | None
    elapsed_s: float


def _bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8", "replace")
    return b""


def run_transient(verb: str, seq: int, argv: Sequence[str], *, run: Runner, ip_address_deny: str,
                  stdin: bytes | None = None) -> ChildResult:
    """One transient unit; belt = ``RUNTIME_MAX_S[verb] + SUBPROCESS_BELT_S``, then ``systemctl kill --signal=KILL``."""
    unit = unit_name(verb, seq)
    runtime_max = RUNTIME_MAX_S[verb]
    full = transient_argv(verb, seq, argv, ip_address_deny=ip_address_deny, runtime_max_s=runtime_max)
    started = time.monotonic()
    try:
        completed = run(full, input=stdin, capture_output=True, timeout=runtime_max + SUBPROCESS_BELT_S)
    except subprocess.TimeoutExpired as exc:
        try:
            run(["systemctl", "kill", "--signal=KILL", unit + ".service"], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return ChildResult(rc=None, stdout=_bytes(exc.stdout), stderr=_bytes(exc.stderr), timed_out=True, unit=unit,
                           elapsed_s=time.monotonic() - started)
    return ChildResult(rc=completed.returncode, stdout=_bytes(completed.stdout), stderr=_bytes(completed.stderr),
                       timed_out=False, unit=unit, elapsed_s=time.monotonic() - started)


def run_inprocess(argv: Sequence[str], *, run: Runner, timeout_s: float, stdin: bytes | None = None) -> ChildResult:
    """A stdlib child dropped to ``imd-worker`` with the verbatim env and cwd (spec §4.1a, §12.1 NoNewPrivileges note)."""
    started = time.monotonic()
    try:
        completed = run(list(argv), input=stdin, user=WORKER_USER, group=WORKER_GROUP, extra_groups=[], env=dict(CHILD_ENV),
                        cwd=CHILD_CWD, timeout=timeout_s, capture_output=True)
    except subprocess.TimeoutExpired as exc:
        return ChildResult(rc=None, stdout=_bytes(exc.stdout), stderr=_bytes(exc.stderr), timed_out=True, unit=None,
                           elapsed_s=time.monotonic() - started)
    return ChildResult(rc=completed.returncode, stdout=_bytes(completed.stdout), stderr=_bytes(completed.stderr),
                       timed_out=False, unit=None, elapsed_s=time.monotonic() - started)


def read_ip_address_deny(*, run: Runner) -> str | None:
    """``systemctl show imd-worker.service -p IPAddressDeny --value``; ``None`` on any failure or an empty value.

    ``None`` makes the broker refuse every TRANSIENT verb with ``child_posture_unavailable`` rather than
    run a runtime child unfenced (spec §4.1b).
    """
    try:
        completed = run(["systemctl", "show", WORKER_UNIT, "-p", "IPAddressDeny", "--value"], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    value = _bytes(completed.stdout).decode("utf-8", "replace").strip()
    return value or None


__all__ = ["CHILD_CWD", "CHILD_ENV", "CHILD_MEMORY_MAX", "CHILD_TASKS_MAX", "ChildResult", "RUNTIME_MAX_S", "Runner",
           "SUBPROCESS_BELT_S", "TRANSIENT_PROPERTIES", "UNIT_PREFIX", "WORKER_GROUP", "WORKER_UNIT", "WORKER_USER",
           "read_ip_address_deny", "run_inprocess", "run_transient", "transient_argv", "unit_name"]
