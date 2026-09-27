"""Broker clients and host readers for PEPEPANE (spec §4.1, §4.2, §5.3, §5.5, §11; contract C.12).

This is one of the two seat modules allowed ``subprocess``/``socket`` (the other is
``data/seat_tail.py``): every ``subprocess.run`` carries ``timeout=`` and a list argv, every socket
call a timeout. Three brokers share ``BrokerProtocol``:

* ``UnixSocketBroker`` -- the VPS: one JSON line to ``/run/imd-dash/broker.sock``; root's ``imd-dashd``
  does the work. ``trust() == "host"``.
* ``LocalDockerBroker`` -- the Mac: the same enum, plan -> apply -> verify, single-use plan ids, one
  write in flight and an audit file, in-process over fixed ``docker`` argv. Every ``docker exec`` that
  runs ``imd``, ``python3`` or ``node`` is wrapped INSIDE the container with coreutils ``timeout`` (spec
  §4.2), each host-side call has ``timeout=25`` and a 5-minute breaker. ``trust() == "container"``:
  the ``imd`` binary lives on a task-writable volume, so nothing it prints feeds a gate.
* ``FakeBroker`` -- tests and ``--host fixture``: scripted or fixture-file responses; records ``calls``.

The host readers (``SystemdUnitReader``, ``DockerUnitReader``, ``FixtureUnitReader``) are the TUI's own
unprivileged reads (``systemctl show``, cgroup files, ``docker inspect``/``stats``); the text parsers
turn ``imd status|skills|tools|whoami`` output into fields, ``None`` on anything they do not recognise.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from maxpane_dashboard.analytics.seat_redact import redact, redact_agent_sentence
from maxpane_dashboard.data.seat_models import SEAT_ROW_KEYS

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]
Clock = Callable[[], float]
Json = Any

CLIENT_TIMEOUT_S = 20.0            #: every read verb, plan, apply and verify on the TUI side (spec §11)
PING_TIMEOUT_S = 1.0
DOCKER_TIMEOUT_S = 25.0
DOCKER_BREAKER_S = 300.0
MAC_STOP_TIMEOUT_S = 30
MAC_CONTAINER = "imd-worker"
SOCKET_PATH = "/run/imd-dash/broker.sock"
AUDIT_FILE_MAC = "seat_audit.jsonl"
#: Client-side copies of the broker enum (the TUI needs them on the VPS, where ``imd_dashd`` is not
#: installed); ``tests/data/test_seat_broker_client.py::test_client_enum_equals_the_broker_enum`` binds them.
PROTOCOL_VERSION = 1
READ_VERBS = ("ping", "seat", "whoami", "status", "skills", "tools", "sessions", "work-stat", "outbox", "orphans",
              "hints-stat", "auth-mtime", "gate", "verify", "audit-tail")
WRITE_VERBS = ("restart", "drain-restart", "cancel-drain", "stop", "start", "enable-boot", "disable-boot",
               "skills-set", "kill-orphans", "doctor")
APPLY_VERB = "apply"
GATED_VERBS = ("restart", "stop", "drain-restart")
TRANSIENT_VERBS = ("whoami", "status", "skills", "tools", "sessions", "doctor", "skills-set")
SKILL_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
LOCAL_ONLY_ACK = "local-only"
#: In-container ``timeout -s TERM -k <grace> <secs>`` per exec kind (spec §4.2, §5.3, §11)
class BrokerError(Exception):
    def __init__(self, code: str, detail: Mapping | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail or {})


@dataclass(frozen=True)
class Plan:
    plan_id: str
    verb: str
    argv: list[str]
    expires_at: str
    single_use: bool
    preconditions: dict
    warning: str
    inverse: dict | None
    verify: dict
    restart_required_after: bool
    raw: dict

    @classmethod
    def from_wire(cls, plan: Mapping) -> "Plan":
        return cls(plan_id=str(plan.get("plan_id")), verb=str(plan.get("verb")), argv=list(plan.get("argv") or []),
                   expires_at=str(plan.get("expires_at")), single_use=bool(plan.get("single_use", True)),
                   preconditions=dict(plan.get("preconditions") or {}), warning=str(plan.get("warning") or ""),
                   inverse=plan.get("inverse"), verify=dict(plan.get("verify") or {}),
                   restart_required_after=bool(plan.get("restart_required_after", False)), raw=dict(plan))


@dataclass(frozen=True)
class ApplyResult:
    outcome: str
    exit_code: int | None
    cursor_before: str | None
    audit_seq: int | None
    preconditions: dict
    raw: dict

    @classmethod
    def from_wire(cls, result: Mapping) -> "ApplyResult":
        return cls(outcome=str(result.get("outcome")), exit_code=result.get("exit_code"), cursor_before=result.get("cursor_before"),
                   audit_seq=result.get("audit_seq"), preconditions=dict(result.get("preconditions") or {}), raw=dict(result))


@dataclass(frozen=True)
class VerifyResult:
    verified: bool | None
    connected: bool | str | None
    verify_lines: list[str]
    cursor_after: str | None
    elapsed_s: float | None
    audit_seq: int | None
    reason: str | None
    raw: dict

    @classmethod
    def from_wire(cls, data: Mapping) -> "VerifyResult":
        return cls(verified=data.get("verified"), connected=data.get("connected"), verify_lines=[str(x) for x in data.get("verify_lines") or []],
                   cursor_after=data.get("cursor_after"), elapsed_s=data.get("elapsed_s"), audit_seq=data.get("audit_seq"),
                   reason=data.get("reason"), raw=dict(data))


class BrokerProtocol(Protocol):
    kind: str
    offline: bool

    def call(self, verb: str, args: Mapping | None = None, *, timeout_s: float = CLIENT_TIMEOUT_S) -> dict: ...
    def read(self, verb: str, args: Mapping | None = None) -> Json: ...
    def plan(self, verb: str, args: Mapping | None = None) -> Plan: ...
    def apply(self, plan_id: str, confirm: str, *, force_node8: str | None = None, local_only_ack: str | None = None) -> ApplyResult: ...
    def verify(self, plan_id: str) -> VerifyResult: ...
    def reachable(self) -> bool: ...
    def trust(self) -> str: ...


class _CallMixin:
    """``read``/``plan``/``apply``/``verify``/``reachable`` on top of a ``call()`` that returns the wire dict."""

    offline: bool = False

    def call(self, verb: str, args: Mapping | None = None, *, timeout_s: float = CLIENT_TIMEOUT_S) -> dict:  # pragma: no cover
        raise NotImplementedError

    def read(self, verb: str, args: Mapping | None = None) -> Json:
        return self.call(verb, args)["data"]

    def plan(self, verb: str, args: Mapping | None = None) -> Plan:
        args = dict(args or {})
        if verb in GATED_VERBS:
            args["offline"] = bool(self.offline)          # every plan request carries the TUI's --offline (spec §11 (b))
        return Plan.from_wire(self.call(verb, args)["plan"])

    def apply(self, plan_id: str, confirm: str, *, force_node8: str | None = None, local_only_ack: str | None = None) -> ApplyResult:
        args: dict = {"plan_id": plan_id, "confirm": confirm}
        if force_node8 is not None:
            args["force_node8"] = force_node8
        if local_only_ack is not None:
            args["local_only_ack"] = local_only_ack
        return ApplyResult.from_wire(self.call(APPLY_VERB, args)["result"])

    def verify(self, plan_id: str) -> VerifyResult:
        return VerifyResult.from_wire(self.call("verify", {"plan_id": plan_id})["data"])

    def reachable(self) -> bool:
        try:
            return bool(self.call("ping", {}, timeout_s=PING_TIMEOUT_S).get("ok"))
        except BrokerError:
            return False


def _check_wire(response: object) -> dict:
    if not isinstance(response, dict) or "ok" not in response:
        raise BrokerError("bad_response", {"reason": "not a broker response object"})
    if response.get("ok") is not True:
        raise BrokerError(str(response.get("error") or "internal"), response.get("detail") or {})
    return response


# ---------------------------------------------------------------- VPS: the unix socket


def _default_connect(path: str, timeout_s: float) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    sock.connect(path)
    return sock


class UnixSocketBroker(_CallMixin):
    kind = "unix"

    def __init__(self, path: str = SOCKET_PATH, *, offline: bool = False,
                 connect: Callable[[str, float], socket.socket] | None = None) -> None:
        self.path = path
        self.offline = offline
        self._connect = connect or _default_connect

    def trust(self) -> str:
        return "host"

    def call(self, verb: str, args: Mapping | None = None, *, timeout_s: float = CLIENT_TIMEOUT_S) -> dict:
        line = (json.dumps({"v": PROTOCOL_VERSION, "verb": verb, "args": dict(args or {})}, separators=(",", ":")) + "\n").encode()
        try:
            sock = self._connect(self.path, timeout_s)
        except OSError as exc:
            raise BrokerError("unreachable", {"path": self.path, "reason": exc.__class__.__name__}) from None
        try:
            sock.settimeout(timeout_s)
            sock.sendall(line)
            chunks = bytearray()
            while b"\n" not in chunks and len(chunks) < 4 * 1024 * 1024:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks += chunk
        except OSError as exc:
            raise BrokerError("transport", {"reason": exc.__class__.__name__, "verb": verb}) from None
        finally:
            try:
                sock.close()
            except OSError:
                pass
        try:
            response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
        except ValueError:
            raise BrokerError("bad_response", {"reason": "not one JSON line", "verb": verb}) from None
        return _check_wire(response)


# ---------------------------------------------------------------- tests / --host fixture


class FakeBroker(_CallMixin):
    kind = "fake"

    def __init__(self, responses: Mapping[str, Json | Callable[[dict], dict]] | None = None, *, fixture_dir: Path | None = None,
                 offline: bool = False, reachable: bool = True, trust: str = "host") -> None:
        self.responses = dict(responses or {})
        self.fixture_dir = Path(fixture_dir) if fixture_dir else None
        self.offline = offline
        self._reachable = reachable
        self._trust = trust
        self.calls: list[tuple[str, dict]] = []

    def trust(self) -> str:
        return self._trust

    @staticmethod
    def _as_wire(verb: str, value: object) -> object:
        """A dict carrying ``ok`` is a whole wire response; for a read verb any other value is its ``data``.

        Both fixture styles stay valid: ``{"ok": true, "plan": {...}}`` (plan/apply/verify scripts) and a bare
        read payload such as ``{"files": 0}`` (the dev-mode ``broker/<verb>.json`` files). A write verb's value
        must be a whole response, so a bare dict there is ``bad_response``, never a silent plan.
        """
        if isinstance(value, dict) and "ok" in value:
            return value
        if verb in READ_VERBS:
            return {"ok": True, "data": value}
        return value

    def call(self, verb: str, args: Mapping | None = None, *, timeout_s: float = CLIENT_TIMEOUT_S) -> dict:
        args = dict(args or {})
        self.calls.append((verb, args))
        if not self._reachable:
            raise BrokerError("unreachable", {"verb": verb})
        if verb in self.responses:
            answer = self.responses[verb]
            response = self._as_wire(verb, answer(args) if callable(answer) else answer)
        elif self.fixture_dir is not None and (self.fixture_dir / "broker" / f"{verb}.json").exists():
            response = self._as_wire(verb, json.loads((self.fixture_dir / "broker" / f"{verb}.json").read_text(encoding="utf-8")))
        elif verb == "ping":
            response = {"ok": True, "data": {"pid": 0, "version": "fake", "uptime_s": 0.0, "drain_armed": False, "in_flight": None,
                                             "posture_ok": True}}
        else:
            raise BrokerError("no_fixture", {"verb": verb})
        return _check_wire(response)


# ---------------------------------------------------------------- Mac: the in-process docker broker


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _text(value: object) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ("" if value is None else str(value))


# ---------------------------------------------------------------- host readers


class UnitReader(Protocol):
    def read_unit(self) -> dict | None: ...
    def read_host(self) -> dict | None: ...


SYSTEMCTL_PROPS = ("ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestamp,ExecMainStartTimestamp,UnitFileState,Restart,"
                   "RestartUSec,MemoryMax,CPUQuotaPerSecUSec,TasksMax,TasksCurrent,KillMode,TimeoutStopUSec,ExecStart")


def _host_facts(home: str) -> dict:
    facts: dict = {"hostname": os.uname().nodename, "load1": None, "memAvailMiB": None, "diskFreeGiB": None, "journal": None}
    try:
        facts["load1"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    try:
        with open("/proc/meminfo", "rb") as fh:
            for raw in fh:
                if raw.startswith(b"MemAvailable:"):
                    facts["memAvailMiB"] = int(raw.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        vfs = os.statvfs(home)
        facts["diskFreeGiB"] = round(vfs.f_bavail * vfs.f_frsize / 1024 ** 3, 1)
    except OSError:
        pass
    return facts


class SystemdUnitReader:
    def __init__(self, unit: str = "imd-worker.service", *, run: Runner = subprocess.run,
                 cgroup_root: Path = Path("/sys/fs/cgroup/system.slice"), proc: Path = Path("/proc"), home: str = "/home") -> None:
        self.unit = unit
        self._run = run
        self._cgroup_root = Path(cgroup_root)
        self._proc = Path(proc)
        self._home = home

    def read_unit(self) -> dict | None:
        try:
            done = self._run(["systemctl", "show", self.unit, "--timestamp=utc", "-p", SYSTEMCTL_PROPS], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if done.returncode != 0:
            return None
        unit = parse_systemctl_show(_text(done.stdout))
        unit.update(parse_cgroup(self._cgroup_root / self.unit))
        return unit

    def read_host(self) -> dict | None:
        return _host_facts(self._home)


class DockerUnitReader:
    def __init__(self, container: str = MAC_CONTAINER, *, run: Runner = subprocess.run, timeout_s: float = DOCKER_TIMEOUT_S,
                 breaker_s: float = DOCKER_BREAKER_S, now: Clock = time.time) -> None:
        self.container = container
        self._run = run
        self._timeout_s = timeout_s
        self._breaker_s = breaker_s
        self._now = now
        self.breaker_until: dict[str, float] = {}

    def _call(self, name: str, argv: list[str]) -> tuple[subprocess.CompletedProcess | None, str | None]:
        """``(completed, None)`` on rc 0, else ``(None, reason)``; a timeout opens the breaker for ``breaker_s``."""
        now = self._now()
        if self.breaker_until.get(name, 0.0) > now:
            return None, f"{name} skipped: breaker open until {_iso(self.breaker_until[name])}"
        try:
            done = self._run(argv, capture_output=True, timeout=self._timeout_s)
        except subprocess.TimeoutExpired:
            self.breaker_until[name] = now + self._breaker_s          # 5-min breaker per verb after any timeout (spec §4.2)
            return None, f"{name} timed out {self._timeout_s:g} s"
        except OSError as exc:
            return None, f"{name} failed: {exc.__class__.__name__}"
        if done.returncode != 0:
            return None, f"{name} exited rc={done.returncode}"
        return done, None

    def read_unit(self) -> dict | None:
        """``docker inspect`` and ``docker stats`` fail independently: a missing half is ``None``, never 0 (fill4 §5).

        A partial block carries ``"reason"`` naming the failed half, so the manager marks the unit source
        failed while keeping the values it did get (WP7 deviation 6, spec §14 mutation proof 8).
        """
        inspect, inspect_reason = self._call("inspect", ["docker", "inspect", self.container])
        stats, stats_reason = self._call("stats", ["docker", "stats", "--no-stream", "--format", "{{json .}}", self.container])
        if inspect is None and stats is None:
            return None
        unit: dict = {}
        reasons = [r for r in (inspect_reason, stats_reason) if r]
        if inspect is not None:
            try:
                unit.update(parse_docker_inspect(json.loads(_text(inspect.stdout))))
            except ValueError:
                reasons.append("inspect output is not JSON")
        if stats is not None:
            text = _text(stats.stdout).strip()
            unit.update(parse_docker_stats(text.splitlines()[-1] if text else ""))
        if not unit:
            return None
        if reasons:
            unit["reason"] = "; ".join(reasons)
        return unit

    def read_host(self) -> dict | None:
        return _host_facts(str(Path.home()))


class FixtureUnitReader:
    def __init__(self, case_dir: Path) -> None:
        self.case_dir = Path(case_dir)

    def read_unit(self) -> dict | None:
        unit_dir = self.case_dir / "unit"
        if (unit_dir / "systemctl_show.txt").exists():
            unit = parse_systemctl_show((unit_dir / "systemctl_show.txt").read_text(encoding="utf-8"))
            if (unit_dir / "cgroup").is_dir():
                unit.update(parse_cgroup(unit_dir / "cgroup"))
            return unit
        if (unit_dir / "docker_inspect.json").exists():
            unit = parse_docker_inspect(json.loads((unit_dir / "docker_inspect.json").read_text(encoding="utf-8")))
            if (unit_dir / "docker_stats.txt").exists():
                unit.update(parse_docker_stats((unit_dir / "docker_stats.txt").read_text(encoding="utf-8").strip().splitlines()[-1]))
            return unit
        return None

    def read_host(self) -> dict | None:
        path = self.case_dir / "unit" / "host.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"hostname": "fixture", "load1": None, "memAvailMiB": None, "diskFreeGiB": None, "journal": None}

# ---------------------------------------------------------------- parsers


_USEC_UNITS = (("ms", 0.001), ("us", 0.000001), ("min", 60.0), ("s", 1.0), ("h", 3600.0), ("d", 86400.0), ("w", 604800.0))


def _usec_to_s(value: str | None) -> float | None:
    if not value or value == "infinity":
        return None
    total = 0.0
    for part in value.split():
        for suffix, factor in _USEC_UNITS:
            if part.endswith(suffix) and part[:-len(suffix)].replace(".", "", 1).isdigit():
                total += float(part[:-len(suffix)]) * factor
                break
        else:
            return None
    return total


def _int_or_none(value: object) -> int | None:
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isdigit() else None


_SYSTEMD_STAMP_RE = re.compile(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) UTC")


def _systemd_stamp(value: str | None) -> str | None:
    """``Thu 2026-09-25 11:45:41 UTC`` -> ``2026-09-25T11:45:41Z`` (``--timestamp=utc``); ``None`` otherwise."""
    match = _SYSTEMD_STAMP_RE.search(value or "")
    return f"{match.group(1)}T{match.group(2)}Z" if match else None


def parse_systemctl_show(text: str) -> dict:
    """``key=value`` lines -> the §7 unit block; USec fields to seconds; ``infinity`` -> ``None``; never 0 for a missing field."""
    props = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    stop_s = _usec_to_s(props.get("TimeoutStopUSec"))
    kill_mode = props.get("KillMode") or None
    quota_s = _usec_to_s(props.get("CPUQuotaPerSecUSec"))
    memory_max = props.get("MemoryMax")
    return {
        "activeState": props.get("ActiveState") or None,
        "subState": props.get("SubState") or None,
        "mainPid": _int_or_none(props.get("MainPID")) or None,
        "sinceUtc": _systemd_stamp(props.get("ActiveEnterTimestamp")),
        "execMainStartUtc": _systemd_stamp(props.get("ExecMainStartTimestamp")),
        "restarts": _int_or_none(props.get("NRestarts")),
        "bootEnabled": None if props.get("UnitFileState") is None else props.get("UnitFileState") == "enabled",
        "unitFileState": props.get("UnitFileState") or None,
        "restartPolicy": (f"{props['Restart']}/{props.get('RestartUSec', '?')}" if props.get("Restart") else None),
        "killMode": kill_mode,
        "stopTimeoutS": stop_s,
        "gracefulStopPossible": None if kill_mode is None or stop_s is None else (kill_mode == "control-group" and stop_s >= 30),
        "memoryMaxB": None if memory_max in (None, "", "infinity") else _int_or_none(memory_max),
        "cpuQuota": None if quota_s is None else f"{int(round(quota_s * 100))}%",
        "tasksMax": _int_or_none(props.get("TasksMax")),
        "tasksCurrent": _int_or_none(props.get("TasksCurrent")),
        "execStart": props.get("ExecStart") or None,
    }


def parse_docker_inspect(body: Json) -> dict:
    """``docker inspect`` (a one-element list or the element) -> the docker unit facts; ``StopTimeout null`` = engine default 10 s."""
    doc = body[0] if isinstance(body, list) and body else body
    if not isinstance(doc, dict):
        return {}
    state = doc.get("State") or {}
    host = doc.get("HostConfig") or {}
    config = doc.get("Config") or {}
    stop_timeout = host.get("StopTimeout")
    stop_s = 10 if stop_timeout is None else stop_timeout
    init = bool(host.get("Init")) if host.get("Init") is not None else False
    started = str(state.get("StartedAt") or "")
    started_utc = started[:19] + "Z" if len(started) >= 19 and started[10] == "T" else None
    nano = host.get("NanoCpus") or 0
    return {
        "running": state.get("Running") if isinstance(state.get("Running"), bool) else None,
        "status": state.get("Status") or None,
        "startedAt": started_utc,
        "oomKilled": state.get("OOMKilled") if isinstance(state.get("OOMKilled"), bool) else None,
        "restartCount": doc.get("RestartCount") if isinstance(doc.get("RestartCount"), int) else None,
        "restartPolicy": (host.get("RestartPolicy") or {}).get("Name") or None,
        "stopTimeoutS": stop_s,
        "stopTimeoutConfigured": stop_timeout is not None,
        "init": init,
        "gracefulStopPossible": (stop_s >= 45) or init,
        "memoryMaxB": host.get("Memory") or None,
        "cpuQuota": f"{nano / 1e9:g} cpus" if nano else None,
        "logConfig": {"type": (host.get("LogConfig") or {}).get("Type"), "config": (host.get("LogConfig") or {}).get("Config") or {}},
        "image": config.get("Image") or None,
        # the §7 unit block keys (contract §C.12 read_unit; WP1 empty_document["unit"]), beside the docker-shaped ones
        "activeState": "active" if state.get("Running") is True else (state.get("Status") or None),
        "subState": state.get("Status") or None,
        "mainPid": state.get("Pid") or None,
        "sinceUtc": started_utc,
        "restarts": doc.get("RestartCount") if isinstance(doc.get("RestartCount"), int) else None,
        "bootEnabled": ((host.get("RestartPolicy") or {}).get("Name") in ("always", "unless-stopped")) if host.get("RestartPolicy") else None,
    }


_SIZE_UNITS = {"B": 1, "kB": 1000, "KB": 1000, "KiB": 1024, "MB": 1000 ** 2, "MiB": 1024 ** 2, "GB": 1000 ** 3, "GiB": 1024 ** 3}
_SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([A-Za-z]+)\s*$")


def _size_to_bytes(text: str) -> int | None:
    match = _SIZE_RE.match(text or "")
    if not match or match.group(2) not in _SIZE_UNITS:
        return None
    return int(float(match.group(1)) * _SIZE_UNITS[match.group(2)])


def parse_docker_stats(line: str) -> dict:
    """One ``docker stats --no-stream --format '{{json .}}'`` line -> memory/cpu/pids; ``None`` for anything unparsable."""
    try:
        row = json.loads(line) if line else {}
    except ValueError:
        row = {}
    mem = str(row.get("MemUsage") or "").split("/")[0]
    cpu = str(row.get("CPUPerc") or "").rstrip("%")
    try:
        cpu_pct: float | None = float(cpu) if cpu else None
    except ValueError:
        cpu_pct = None
    return {"memoryCurrentB": _size_to_bytes(mem) if mem else None, "cpuPct": cpu_pct, "pids": _int_or_none(row.get("PIDs"))}


def parse_cgroup(root: Path) -> dict:
    """``memory.current/peak/max`` and ``cpu.max`` under *root* -> ints / ``"100%"``; ``max`` -> ``None``."""
    out: dict = {"memoryCurrentB": None, "memoryPeakB": None, "memoryMaxB": None, "cpuQuota": None}
    for key, name in (("memoryCurrentB", "memory.current"), ("memoryPeakB", "memory.peak"), ("memoryMaxB", "memory.max")):
        try:
            text = (Path(root) / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        out[key] = None if text == "max" else _int_or_none(text)
    try:
        quota, period = (Path(root) / "cpu.max").read_text(encoding="utf-8").split()
        if quota != "max" and period.isdigit() and int(period) > 0:
            out["cpuQuota"] = f"{int(round(int(quota) / int(period) * 100))}%"
    except (OSError, ValueError):
        pass
    return out


_STATUS_FIELDS = {"config", "server", "device", "token", "capacity"}
_RUNTIME_ROW_RE = re.compile(r"^(?P<mark>[→✓✗])\s+(?P<id>\S+)\s*(?P<rest>.*)$")


def parse_imd_status(lines: Sequence[str], *, daemon_version: str | None = None) -> dict:
    """``imd status`` text (lifted from aidude ``_worker_page.py:395-424``) -> fields; per-field ``None`` + ``parseError`` on drift."""
    fields: dict[str, str] = {}
    runtimes: list[dict] = []
    offers: list[str] | None = None
    eligibility: str | None = None
    tasks_run_on: str | None = None
    for raw in lines:
        line = str(raw).strip()
        if not line:
            continue
        row = _RUNTIME_ROW_RE.match(line)
        if row:
            runtimes.append({"mark": row.group("mark"), "id": row.group("id"), "detail": row.group("rest").strip() or None,
                             "chosen": row.group("mark") == "→", "available": row.group("mark") in "→✓"})
            continue
        if line.startswith("offers:"):
            offers = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
            continue
        if line.startswith("tasks run on:"):
            tasks_run_on = line.split(":", 1)[1].strip() or None
            continue
        if line.startswith("server") and "active" in line and ":" in line:
            eligibility = line.split(":", 1)[1].strip() or None
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in _STATUS_FIELDS:
            fields.setdefault(parts[0], parts[1].strip())
    chosen = next((r for r in runtimes if r["chosen"]), None)
    runtime = None
    if chosen:
        detail = (chosen["detail"] or "").split()
        runtime = {"id": chosen["id"], "version": " ".join(detail) or None}
    capacity_text = fields.get("capacity", "")
    capacity = _int_or_none(capacity_text.split()[0]) if capacity_text else None
    parsed_anything = bool(fields or runtimes or offers or eligibility)
    return {
        "configPath": fields.get("config"), "server": fields.get("server"),
        "deviceKey": fields.get("device") if fields.get("device") and re.fullmatch(r"[0-9a-f]{64}", fields["device"]) else None,
        "tokenId": _int_or_none(fields.get("token")), "capacity": capacity, "runtimes": runtimes, "runtime": runtime,
        "tasksRunOn": tasks_run_on, "offers": offers, "eligibility": eligibility,
        "parseError": None if parsed_anything else f"imd status format changed in {daemon_version or 'unknown build'}",
    }


_SKILLS_HEADER_RE = re.compile(r"^(?P<offered>\d+) skills? offered, (?P<on>\d+) on here\.?$")
_SKILL_ROW_RE = re.compile(r"^(?P<state>on|off)\s+(?P<id>\S+)(?:\s+—\s+needs\s+(?P<needs>.+))?$")


def parse_imd_skills(lines: Sequence[str]) -> dict:
    """``imd skills`` text -> ``{"offered","on","rows":[{"id","on","needs"}],"needsNetwork"}``."""
    offered: int | None = None
    on: int | None = None
    rows: list[dict] = []
    for raw in lines:
        line = str(raw).strip()
        header = _SKILLS_HEADER_RE.match(line)
        if header:
            offered, on = int(header.group("offered")), int(header.group("on"))
            continue
        row = _SKILL_ROW_RE.match(line)
        if row:
            needs = (row.group("needs") or "").strip() or None
            rows.append({"id": row.group("id"), "on": row.group("state") == "on", "needs": needs})
    return {"offered": offered, "on": on, "rows": rows, "needsNetwork": sum(1 for r in rows if r["needs"] == "network")}


_TOOLS_NONE_RE = re.compile(r"^no tools configured\b")
_TOOL_ROW_RE = re.compile(r"^(?:ready|not ready)\s+(?P<id>[a-z0-9][a-z0-9._-]*)\b")


def parse_imd_tools(lines: Sequence[str]) -> list[str]:
    ids: list[str] = []
    for raw in lines:
        line = str(raw).strip()
        if not line or _TOOLS_NONE_RE.match(line):
            continue
        row = _TOOL_ROW_RE.match(line)
        if row:
            ids.append(row.group("id"))
    return ids


def parse_whoami(lines: Sequence[str]) -> str | None:
    for raw in lines:
        line = str(raw).strip()
        if re.fullmatch(r"[0-9a-f]{64}", line):
            return line
    return None


_PS_HEADER_RE = re.compile(r"^\s*PID\s+PPID\s+PGID\s+ELAPSED\s+RSS\s+COMMAND\s*$")


def parse_docker_ps(text: str, *, min_age_s: float = 3600.0, worker_uid: int = 1000) -> list[dict]:
    """``ps -o pid,ppid,pgid,etimes,rss,args -u imd`` inside the container -> orphan candidates (spec §5.5 Mac).

    A candidate is older than an hour and NOT a descendant of PID 1 (the daemon); ``docker exec``'d
    processes have ppid 0. Rows carry ``SEAT_ROW_KEYS["seat_machine_orphans"]`` exactly; ``trust`` is
    the caller's (``container``).
    """
    procs: list[dict] = []
    for raw in text.splitlines():
        if not raw.strip() or _PS_HEADER_RE.match(raw):
            continue
        parts = raw.split(None, 5)
        if len(parts) < 6 or not all(p.lstrip("-").isdigit() for p in parts[:5]):
            continue
        pid, ppid, pgid, etimes, rss = (int(p) for p in parts[:5])
        procs.append({"pid": pid, "ppid": ppid, "pgid": pgid, "age_s": etimes, "rss_b": rss * 1024, "uid": worker_uid,
                      "cmd": redact_agent_sentence(parts[5])[:80], "cgroup": "container"})
    by_pid = {p["pid"]: p for p in procs}

    def under_daemon(proc: dict) -> bool:
        seen = set()
        current = proc
        while current["pid"] not in seen:
            seen.add(current["pid"])
            if current["pid"] == 1:
                return True
            current = by_pid.get(current["ppid"])
            if current is None:
                return False
        return False

    keys = SEAT_ROW_KEYS["seat_machine_orphans"]
    out: list[dict] = []
    for proc in procs:
        if proc["age_s"] <= min_age_s or under_daemon(proc) or proc["cmd"].startswith("ps "):
            continue
        members = [{"pid": m["pid"], "uid": m["uid"], "cgroup": m["cgroup"], "cmd": m["cmd"]} for m in procs
                   if m["pgid"] == proc["pgid"] and m["pid"] != proc["pid"]]
        row = {"pid": proc["pid"], "pgid": proc["pgid"], "uid": proc["uid"], "cgroup": proc["cgroup"], "ageS": proc["age_s"],
               "rssB": proc["rss_b"], "cmd": proc["cmd"], "pgidMembers": members}
        out.append({k: row.get(k) for k in keys})
    return out
