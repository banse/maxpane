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

from maxpane_dashboard.analytics.seat_redact import redact, redact_agent_sentence, redact_tree
from maxpane_dashboard.data.seat_models import SEAT_ROW_KEYS

try:  # the Mac runs an editable checkout where the top-level stdlib package imports; the VPS wheel has no imd_dashd
    from imd_dashd import audit as _audit_mod
    from imd_dashd import drain as _drain_mod
    from imd_dashd import gate as _gate_mod
    from imd_dashd import verbs as _verbs_mod
    from imd_dashd import imd_dashd as _broker_mod
    IMD_DASHD_AVAILABLE = True
except ImportError:                                   # pragma: no cover - exercised only on a wheel install
    _audit_mod = _drain_mod = _gate_mod = _verbs_mod = _broker_mod = None
    IMD_DASHD_AVAILABLE = False

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
LOCAL_BROKER_VERSION = "pepepane local-docker broker 0.1.0"

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
NOT_ON_DOCKER = ("enable-boot", "disable-boot")     # `unless-stopped` already covers boot (spec §11 verb table)

#: In-container ``timeout -s TERM -k <grace> <secs>`` per exec kind (spec §4.2, §5.3, §11)
CONTAINER_TIMEOUTS = {"status": (5, 25), "skills": (5, 25), "whoami": (5, 25), "tools": (5, 25), "seat": (5, 20),
                      "sessions": (5, 20), "doctor": (10, 120), "skills-set": (10, 25)}
LOCAL_TICK_S = 5.0                                   #: LocalDockerBroker.call() runs tick() when this long has passed

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
            sock.sendall(line)  # newline frames the request; never half-close (broker EOF means abandoned)
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
                                             "posture_ok": True, "drop_ok": True}}
        else:
            raise BrokerError("no_fixture", {"verb": verb})
        return _check_wire(response)


# ---------------------------------------------------------------- Mac: the in-process docker broker


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _text(value: object) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ("" if value is None else str(value))


def broker_script(name: str) -> bytes:
    """The bytes of ``imd_dashd/<name>.py`` to pipe into the container's ``python3 -`` (projection, summariser)."""
    if not IMD_DASHD_AVAILABLE:
        raise BrokerError("unavailable", {"reason": "imd_dashd package not importable"})
    path = Path(_verbs_mod.__file__).with_name(f"{name}.py")
    try:
        return path.read_bytes()
    except OSError:
        raise BrokerError("unavailable", {"reason": f"{name}.py missing"}) from None


class LocalDockerBroker(_CallMixin):
    """The Mac parity broker (spec §4.2, §12.2): shape, not privilege, is the mitigation."""

    kind = "docker"

    def __init__(self, container: str = MAC_CONTAINER, *, run: Runner = subprocess.run, audit_path: Path | None = None,
                 now: Clock = time.time, offline: bool = False, tail_lines: Callable[[], Sequence[tuple[float, str]]] | None = None,
                 breaker_s: float = DOCKER_BREAKER_S, timeout_s: float = DOCKER_TIMEOUT_S, seat: int | None = None,
                 standing_url: str = "https://api.imd.fun/seats/{seat}/standing") -> None:
        if not IMD_DASHD_AVAILABLE:
            raise BrokerError("unavailable", {"reason": "LocalDockerBroker needs the imd_dashd package (editable checkout)"})
        self.container = container
        self._run = run
        self._now = now
        self.offline = offline
        self._injected_tail = tail_lines
        self._tail_lines = tail_lines or self._docker_tail      # WP8 injects none: read the trusted `docker logs --tail 200`
        self._breaker_s = breaker_s
        self._timeout_s = timeout_s
        self._seat = seat
        self._standing_url = standing_url
        path = Path(audit_path) if audit_path else Path.home() / ".maxpane" / AUDIT_FILE_MAC
        self._audit = _audit_mod.Audit(path, now=now, mode=0o600)
        self._plans = _broker_mod.PlanStore(now=now)
        self._watches: dict[str, Any] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._in_flight: dict | None = None
        self._breaker_until: dict[str, float] = {}
        self._drain = _drain_mod.Drain(now=now)
        self._started = now()
        self._last_doctor: float | None = None
        self._whoami_key: str | None = None
        self._skills_listing: set[str] | None = None
        self._pending_kills: list[tuple[float, str, int]] = []
        self._kill_snapshots: dict[tuple[str, int], dict] = {}
        self._drain_watermark = self._started               #: the newest heartbeat epoch the drain has consumed
        self._drain_fired: set[str] = set()                 #: drain-fired restarts still awaiting their verify line
        self._last_tick = self._started
        self._tick_lock = threading.Lock()
        self._read_counts: dict[str, int] = {}
        self._reads_flushed_at = self._started

    def trust(self) -> str:
        return "container"

    # -- docker plumbing --------------------------------------------------------------------------

    def _docker(self, family: str, argv: Sequence[str], *, stdin: bytes | None = None,
                timeout_s: float | None = None) -> subprocess.CompletedProcess:
        """One docker call behind the per-verb breaker (spec §12.2). ``stdin`` feeds a script; otherwise stdin is
        ``DEVNULL``, so ``docker exec -i`` never attaches the TUI's own terminal. ``timeout_s`` is the host-side belt
        (25 s by default; above the in-container limit for a wrapped exec -- deviation 15)."""
        now = self._now()
        until = self._breaker_until.get(family)
        if until is not None and now < until:
            raise BrokerError("timeout", {"breaker_until": _iso(until), "family": family})
        io: dict = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
        try:
            return self._run(list(argv), capture_output=True, timeout=timeout_s or self._timeout_s, **io)
        except subprocess.TimeoutExpired:
            self._breaker_until[family] = now + self._breaker_s
            detail = {"family": family, "breaker_until": _iso(now + self._breaker_s)}
            # Only this caught runner timeout proves that the signal command actually ran.
            # A pre-open breaker or a process-snapshot timeout leaves signal state untouched.
            if family == "kill-orphans" and list(argv[4:6]) == ["kill", "-TERM"]:
                detail.update(reason="orphan signal command timed out", outcome="timeout")
            raise BrokerError("timeout", detail) from None
        except OSError as exc:
            raise BrokerError("unreachable", {"reason": exc.__class__.__name__}) from None

    def _exec_argv(self, inner: Sequence[str], *, kind: str | None) -> list[str]:
        """``docker exec -i <c> [timeout -s TERM -k <g> <s>] <inner>`` -- the in-container timeout for imd/python3/node."""
        argv = ["docker", "exec", "-i", self.container]
        if kind is not None:
            grace, secs = CONTAINER_TIMEOUTS[kind]
            argv += ["timeout", "-s", "TERM", "-k", str(grace), str(secs)]
        return argv + list(inner)

    def _exec(self, inner: Sequence[str], *, kind: str | None, family: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
        # host-side belt: 25 s for a bare coreutils exec, grace + secs + 5 above a wrapped exec's in-container limit (deviation 15)
        belt = None if kind is None else sum(CONTAINER_TIMEOUTS[kind]) + 5
        return self._docker(family, self._exec_argv(inner, kind=kind), stdin=stdin, timeout_s=belt)

    def _inspect(self) -> dict | None:
        try:
            done = self._docker("inspect", ["docker", "inspect", self.container])
        except BrokerError:
            return None
        if done.returncode != 0:
            return None
        try:
            return parse_docker_inspect(json.loads(_text(done.stdout)))
        except ValueError:
            return None

    def _outbox_files(self) -> int | None:
        try:
            done = self._exec(["ls", "-1A", "/home/imd/.identitymd/outbox"], kind=None, family="outbox")
        except BrokerError:
            return None
        if done.returncode != 0:
            return None
        return len([ln for ln in _text(done.stdout).splitlines() if ln.strip()])

    def _standing(self) -> dict | None:
        if self.offline:
            return None
        if self._seat is None:                        # built without seat=: take tokenId from the canary-checked projection
            try:
                token = self._seat_projection().get("tokenId")
            except BrokerError:
                token = None
            if isinstance(token, int) and not isinstance(token, bool) and token > 0:
                self._seat = token
        if self._seat is None:
            return None
        try:
            return _gate_mod.fetch_standing_running(self._standing_url.format(seat=self._seat))
        except (OSError, ValueError):
            return None

    def _gate(self):
        standing = self._standing()
        standing_checked_at = self._now()
        outbox = self._outbox_files()
        inspect = self._inspect()
        unit_active = None if inspect is None else inspect.get("running")
        graceful = None if inspect is None else inspect.get("gracefulStopPossible")
        if self._injected_tail is not None:
            lines, lifecycle_ok = list(self._injected_tail()), True
        else:
            lines, lifecycle_ok = self._docker_tail_read()
        if _gate_mod.newest_lifecycle([text for _, text in lines])[0] is None:
            history, history_ok = self._docker_tail_read(_limit=10000)
            # Empty/older segments cannot corroborate a nonempty live window.
            current = not lines or bool(history and history[-1][0] >= max(epoch for epoch, _ in lines))
            lifecycle_ok = lifecycle_ok and history_ok and current
            if lifecycle_ok:
                lines = sorted(set(history + lines))
        return _gate_mod.evaluate(journal_lines=lines, standing=standing, offline=self.offline,
                                  outbox_files=outbox, unit_active=unit_active, graceful_stop_possible=graceful,
                                  now=self._now(), lifecycle_read_succeeded=lifecycle_ok, standing_checked_at=standing_checked_at)

    def _docker_tail(self, *, _limit: int = 200) -> list[tuple[float, str]]:
        return self._docker_tail_read(_limit=_limit)[0]

    def _docker_tail_read(self, *, _limit: int = 200) -> tuple[list[tuple[float, str]], bool]:
        """Trusted Docker logs, preserving read success independently of an empty result."""
        try:
            done = self._docker("logs", ["docker", "logs", "--tail", str(_limit), "--timestamps", self.container])
        except BrokerError:
            return [], False
        if done.returncode != 0:
            return [], False
        out: list[tuple[float, str]] = []
        for raw in (_text(done.stdout) + "\n" + _text(done.stderr)).split("\n"):
            raw = raw.rstrip("\r")
            text = raw.split(" ", 1)[1] if " " in raw else raw
            epoch = _gate_mod.parse_iso(text[:24])
            if epoch is not None:
                out.append((epoch, text))
        return sorted(out), True

    def _log(self, **fields) -> int:
        try:
            return self._audit.append(**fields)
        except (OSError, TypeError, ValueError):
            return -1

    # -- dispatch ----------------------------------------------------------------------------------

    def call(self, verb: str, args: Mapping | None = None, *, timeout_s: float = CLIENT_TIMEOUT_S) -> dict:
        if verb != "ping" and self._now() - self._last_tick >= LOCAL_TICK_S:
            try:
                self.tick()                        # the in-process drain and SIGKILL follow-ups advance with the client's calls
            except BrokerError:
                pass
        args = dict(args or {})
        code = _verbs_mod.validate_args(verb, args)
        if code is not None:
            self._log(peer_uid=os.getuid(), verb=verb if verb in _verbs_mod.ALL_VERBS else None, phase="refused", outcome=code,
                      args={"names": sorted(args)})
            raise BrokerError(code, {"verb": verb})
        if verb in READ_VERBS:
            self._read_counts[verb] = self._read_counts.get(verb, 0) + 1          # audited as counts only (spec §11)
            return _check_wire(_verbs_mod.ok(data=self._read(verb, args)))
        if verb == APPLY_VERB:
            return _check_wire(self._apply(args))
        return _check_wire(self._plan(verb, args))

    # -- reads --------------------------------------------------------------------------------------

    def _lines(self, done: subprocess.CompletedProcess) -> list[str]:
        return [redact(ln) for ln in _text(done.stdout).splitlines() if ln.strip()]

    def _read(self, verb: str, args: dict) -> Json:
        if verb == "ping":
            return {"pid": os.getpid(), "version": LOCAL_BROKER_VERSION, "uptime_s": round(self._now() - self._started, 1),
                    "drain_armed": self._drain.armed is not None, "in_flight": None if self._in_flight is None else dict(self._in_flight),
                    "posture_ok": True, "drop_ok": True, "drain": None if self._drain.armed is None else self._drain.armed.to_dict()}
        if verb == "audit-tail":
            return {"lines": self._audit.tail(max(1, min(int(args["n"]), 200)))}
        if verb == "gate":
            gate = self._gate()
            return {**gate.to_dict(), "last_lifecycle_line": redact(gate.last_lifecycle_line) if gate.last_lifecycle_line is not None else None}
        if verb == "verify":
            return self._verify(str(args["plan_id"]))
        if verb in ("status", "skills", "tools"):
            done = self._exec(["imd", verb], kind=verb, family=verb)
            lines = self._lines(done)
            if verb == "skills":
                self._skills_listing = {ln.split()[1] for ln in lines if ln.split()[:1] in (["on"], ["off"]) and len(ln.split()) > 1}
            return {"lines": lines, "rc": done.returncode, "unit": None}
        if verb == "whoami":
            done = self._exec(["imd", "whoami"], kind="whoami", family="whoami")
            key = parse_whoami([redact(ln, "deviceKey") for ln in _text(done.stdout).splitlines()])
            if key is None:
                raise BrokerError("whoami_unavailable", {"rc": done.returncode})
            self._whoami_key = key
            return {"deviceKey": key}
        if verb == "seat":
            return self._seat_projection()
        if verb == "sessions":
            script = broker_script("summarise_claude")
            done = self._exec(["python3", "-", "--root", "/home/imd/.claude/projects", "--since", repr(float(args["since"]))],
                              kind="sessions", family="sessions", stdin=script)
            try:
                body = json.loads(_text(done.stdout))
            except ValueError:
                raise BrokerError("unreadable", {"what": "summariser output", "rc": done.returncode}) from None
            return redact_tree(body)
        if verb == "outbox":
            count = self._outbox_files()
            if count is None:
                raise BrokerError("unreadable", {"what": "outbox"})
            return {"files": count}
        if verb == "work-stat":
            listing = self._exec(["find", "/home/imd/.identitymd/work", "-mindepth", "1", "-maxdepth", "4", "-printf", "%y\t%T@\t%P\n"],
                                 kind=None, family="work-stat")
            if listing.returncode != 0:
                raise BrokerError("unreadable", {"what": "work"})
            usage = self._exec(["du", "-sb", "/home/imd/.identitymd/work"], kind=None, family="work-stat")
            total = None
            try:
                total = int(_text(usage.stdout).split()[0]) if usage.returncode == 0 else None
            except (IndexError, ValueError):
                total = None
            return _broker_mod.parse_work_listing(_text(listing.stdout), total_bytes=total)
        if verb in ("hints-stat", "auth-mtime"):
            path = "/home/imd/CLAUDE.md" if verb == "hints-stat" else "/home/imd/.claude/.credentials.json"
            done = self._exec(["stat", "-c", "%s %Y", path], kind=None, family=verb)
            if done.returncode != 0:
                raise BrokerError("unreadable", {"what": verb})
            size, mtime = _text(done.stdout).split()
            data = {"path": path, "mtimeUtc": _iso(int(mtime))}
            if verb == "hints-stat":
                digest = self._exec(["sha256sum", path], kind=None, family=verb)
                parts = _text(digest.stdout).split()
                data.update({"bytes": int(size), "sha8": parts[0][:8] if digest.returncode == 0 and parts else None})
            return data
        if verb == "orphans":
            done = self._exec(["ps", "-o", "pid,ppid,pgid,etimes,rss,args", "-u", "imd"], kind=None, family="orphans")
            return {"candidates": parse_docker_ps(_text(done.stdout))}
        raise BrokerError("bad_verb", {"verb": verb})

    def _seat_projection(self) -> dict:
        if self._whoami_key is None:
            self._read("whoami", {})
        done = self._exec(["python3", "-", "--config", "/home/imd/.identitymd/config.json", "--tools", "/home/imd/.identitymd/tools.json"],
                          kind="seat", family="seat", stdin=broker_script("projection"))
        try:
            payload = json.loads(_text(done.stdout))
        except ValueError:
            payload = None
        if done.returncode == 3 or (isinstance(payload, dict) and payload.get("error") == "unknown_keys"):
            return self._canary("unknown_keys")
        if done.returncode != 0 or not isinstance(payload, dict):
            raise BrokerError("unreadable", {"what": "config projection", "rc": done.returncode})
        from maxpane_dashboard.analytics.seat_redact import find_secret
        kind = find_secret(payload, allowed_hex64_paths=frozenset({"deviceKey"}))
        if kind is not None:
            return self._canary(kind)
        if payload.get("deviceKey") != self._whoami_key:
            return self._canary("devicekey_mismatch")
        return payload

    def _canary(self, kind: str) -> dict:
        self._log(peer_uid=os.getuid(), verb="seat", phase="canary", outcome=f"canary: {kind}")
        raise BrokerError("projection_refused", {"canary": kind})

    # -- plan / apply / verify ----------------------------------------------------------------------

    def _armed_drain_refusal(self, verb: str, plan_id: str | None = None) -> dict | None:
        if verb in ("restart", "stop") and self._drain.armed is not None:
            self._log(peer_uid=os.getuid(), verb=verb, phase="refused", plan_id=plan_id, outcome="drain_already_armed")
            return _verbs_mod.err("drain_already_armed", {"hint": "cancel-drain before a manual restart or stop"})
        return None

    def _plan(self, verb: str, args: dict) -> dict:
        refusal = self._armed_drain_refusal(verb)
        if refusal is not None:
            return refusal
        if self._in_flight is not None:
            self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="busy", args={"names": sorted(args)})
            return _verbs_mod.err("busy", dict(self._in_flight))
        if verb in NOT_ON_DOCKER:
            self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="bad_verb")
            return _verbs_mod.err("bad_verb", {"verb": verb, "reason": "docker restart policy unless-stopped covers boot"})
        preconditions: dict = {}
        inverse: dict | None = None
        verify = {"verified_when": [], "within_s": _broker_mod.VERIFY_WITHIN_S, "connected_when": None, "reported_separately": True}
        restart_required_after = False
        warning = _broker_mod.WARNING
        argv: list[str]
        if verb in GATED_VERBS:
            gate = self._gate()
            preconditions = _broker_mod._preconditions(gate)
            if args.get("force_node8"):
                # spec §4.2 / §16 #8: --force is ALWAYS disabled on the Mac in v1, even after the recreate (follow-up item 13)
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="force_disabled", preconditions=preconditions)
                return _verbs_mod.err("force_disabled", {"graceful_stop_possible": gate.graceful_stop_possible,
                                                         "reason": "recreate the container with --stop-timeout 45 --init first"})
            if verb != "drain-restart":                # spec §11: drain-restart = plain confirm to arm; G runs at fire time
                if gate.unknown is not None:
                    self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome=f"gate_unknown({gate.unknown})", preconditions=preconditions)
                    return _verbs_mod.err(f"gate_unknown({gate.unknown})", {"reason": gate.reason, "preconditions": preconditions})
                if not gate.safe:
                    self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="gate_blocked", preconditions=preconditions)
                    return _verbs_mod.err("gate_blocked", {"reason": gate.reason, "preconditions": preconditions})
            elif self._drain.armed is not None:
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="drain_already_armed")
                return _verbs_mod.err("drain_already_armed", {**self._drain.armed.to_dict(), "hint": "cancel-drain before arming another drain"})
            if verb == "stop":
                argv = ["docker", "stop", "-t", str(MAC_STOP_TIMEOUT_S), self.container]
                verify = {"verified_when": ["shutting down", "container not running"], "within_s": _broker_mod.VERIFY_WITHIN_S,
                          "connected_when": None, "reported_separately": True}
                inverse = {"verb": "start", "args": {}}
            else:
                argv = ["docker", "restart", "-t", str(MAC_STOP_TIMEOUT_S), self.container]
                verify = {"verified_when": ["shutting down", "runtimes:"], "within_s": _broker_mod.VERIFY_WITHIN_S,
                          "connected_when": "admitted (session", "reported_separately": True}
                inverse = {"verb": "stop" if verb == "restart" else "cancel-drain", "args": {}}
                if verb == "drain-restart":
                    warning = "in-process drain: dies with the TUI (spec §11); " + _broker_mod.WARNING
        elif verb == "start":
            argv = ["docker", "start", self.container]
            inspect = self._inspect()
            preconditions = {"unit_active": None if inspect is None else inspect.get("running")}
            verify = {"verified_when": ["runtimes:"], "within_s": _broker_mod.VERIFY_WITHIN_S, "connected_when": "admitted (session",
                      "reported_separately": True}
            inverse = {"verb": "stop", "args": {}}
            warning = "starts the container; it accepts work as soon as it is admitted"
        elif verb == "cancel-drain":
            if self._drain.armed is None:
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="drain_not_armed")
                return _verbs_mod.err("drain_not_armed")
            argv = []
            preconditions = {"drain": self._drain.armed.to_dict()}
            warning = "clears the armed drain; nothing is restarted"
        elif verb == "skills-set":
            skill_id = args["skill_id"]
            if not SKILL_ID_RE.fullmatch(skill_id):
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="bad_skill_id", args={"skill_id": "<refused>", "on": bool(args["on"])})
                return _verbs_mod.err("bad_skill_id")
            if self._skills_listing is None:
                try:
                    self._read("skills", {})
                except BrokerError:
                    pass
            if self._skills_listing is not None and skill_id not in self._skills_listing:
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="skill_not_listed", args={"skill_id": skill_id})
                return _verbs_mod.err("skill_not_listed", {"skill_id": skill_id})
            argv = self._exec_argv(["imd", "skills", "add" if args["on"] else "remove", skill_id], kind="skills-set")
            preconditions = {"skill_id": skill_id, "on": bool(args["on"]), "listed": self._skills_listing is not None, "trust": "container"}
            verify = {"verified_when": ["imd skills re-listed"], "within_s": 25, "connected_when": None, "reported_separately": True}
            inverse = {"verb": "skills-set", "args": {"skill_id": skill_id, "on": not args["on"]}}
            restart_required_after = True
            warning = "skillsOptOut is read once at daemon start: the change applies after a (drained) restart"
        elif verb == "doctor":
            now = self._now()
            if self._last_doctor is not None and now - self._last_doctor < _broker_mod.DOCTOR_MIN_INTERVAL_S:
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="doctor_too_soon")
                return _verbs_mod.err("doctor_too_soon", {"next_allowed_at": _iso(self._last_doctor + _broker_mod.DOCTOR_MIN_INTERVAL_S)})
            argv = self._exec_argv(["imd", "doctor"], kind="doctor")
            preconditions = {"last_doctor_utc": None if self._last_doctor is None else _iso(self._last_doctor), "runtime_max_s": 120}
            verify = {"verified_when": ["exit 0"], "within_s": 120, "connected_when": None, "reported_separately": True}
            warning = "spends one runtime turn and quota; leaves a work/doctor-* transcript; the kill happens inside the container"
        elif verb == "kill-orphans":
            candidates = {c["pid"]: c for c in self._read("orphans", {})["candidates"]}
            pids = [int(p) for p in args["pids"]]
            if any(p not in candidates for p in pids):
                self._log(peer_uid=os.getuid(), verb=verb, phase="refused", outcome="bad_args", args={"pids": pids})
                return _verbs_mod.err("bad_args", {"reason": "every pid must be a current orphan candidate", "pids": pids})
            rows = [candidates[p] for p in pids]
            procs = self._process_snapshot()
            kill_snapshot = {p["pid"]: _broker_mod._proc_identity(p) for p in procs}
            if not all(self._kill_identity_safe(procs, "pid", pid, kill_snapshot) for pid in pids):
                return _verbs_mod.err("bad_args", {"reason": "orphan identity unavailable"})
            mode = {str(pgid): ("group" if self._kill_identity_safe(procs, "pgid", pgid, kill_snapshot) else "individual")
                    for pgid in sorted({r["pgid"] for r in rows})}
            argv = self._exec_argv(["kill", "-TERM"], kind=None)
            preconditions = {"candidates": rows, "kill_mode_by_pgid": mode, "min_age_s": _broker_mod.ORPHAN_MIN_AGE_S,
                             "sigkill_after_s": _broker_mod.KILL_GRACE_S, "trust": "container"}
            verify = {"verified_when": ["pids gone"], "within_s": _broker_mod.KILL_GRACE_S, "connected_when": None, "reported_separately": True}
            warning = "kills inside the container with SIGTERM (SIGKILL after 10 s); the ps listing is container-reported"
        else:
            self._log(peer_uid=os.getuid(), verb=None, phase="refused", outcome="bad_verb")
            return _verbs_mod.err("bad_verb", {"verb": verb})
        plan = self._plans.create(verb, args, argv, preconditions, inverse, verify, force_node8=None)
        if verb == "kill-orphans":
            plan.kill_snapshot = kill_snapshot
        seq = self._log(peer_uid=os.getuid(), verb=verb, phase="plan", plan_id=plan.plan_id, args={k: v for k, v in args.items()},
                        preconditions=preconditions, outcome="planned")
        return _verbs_mod.ok(plan={"plan_id": plan.plan_id, "verb": verb, "argv": argv, "expires_at": _iso(plan.expires), "single_use": True,
                                   "preconditions": preconditions, "warning": warning, "inverse": inverse, "verify": verify,
                                   "restart_required_after": restart_required_after, "audit_seq": seq})

    def _apply(self, args: dict) -> dict:
        plan_id = str(args["plan_id"])
        audit_id = plan_id if _verbs_mod.PLAN_ID_RE.fullmatch(plan_id) else None     # never echo a malformed id
        if not self._lock.acquire(blocking=False):
            self._log(peer_uid=os.getuid(), verb="apply", phase="refused", plan_id=audit_id, outcome="busy")
            return _verbs_mod.err("busy", dict(self._in_flight or {}))
        release = True
        plan = None
        try:
            now = self._now()
            try:
                plan = self._plans.consume(plan_id, now)
                self._watches[plan_id] = _broker_mod.VerifyWatch(plan_id=plan_id, verb=plan.verb, kind="none", cursor_before=None, started=now)
            except _broker_mod.PlanError as exc:
                self._log(peer_uid=os.getuid(), verb="apply", phase="refused", plan_id=audit_id, outcome=exc.code)
                return _verbs_mod.err(exc.code, exc.detail)
            if args["confirm"] != plan_id[:4]:
                self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan_id, outcome="bad_confirm")
                return _verbs_mod.err("bad_confirm")
            self._in_flight = {"verb": plan.verb, "plan_id": plan_id, "since": _iso(now)}
            refusal = self._armed_drain_refusal(plan.verb, plan_id)
            if refusal is not None:
                return refusal
            if plan.verb in GATED_VERBS:
                if plan.verb == "drain-restart":
                    if self._drain.armed is not None:
                        self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan_id, outcome="drain_already_armed")
                        return _verbs_mod.err("drain_already_armed", {**self._drain.armed.to_dict(), "hint": "cancel-drain before arming another drain"})
                    self._drain_watermark = now                           # tick() counts only heartbeats after the arm
                    event = self._drain.arm(plan_id)
                    # verified at once, like the root broker (WP8's CONTROL polls verify after every apply, contract §C.16)
                    self._watches[plan_id] = _broker_mod.VerifyWatch(
                        plan_id=plan_id, verb=plan.verb, kind="none", cursor_before=None, started=now, verified=True,
                        lines=[_broker_mod._drain_verify_line(self._drain.armed.to_dict(), plan.preconditions.get("idle_beats_required"))])
                    seq = self._log(peer_uid=os.getuid(), verb=plan.verb, phase=event, plan_id=plan_id, preconditions=plan.preconditions, outcome="armed")
                    return _verbs_mod.ok(result={"outcome": "armed", "exit_code": None, "cursor_before": None, "audit_seq": seq,
                                                 "preconditions": plan.preconditions, "drain": self._drain.armed.to_dict()})
                gate = self._gate()                                             # FRESH at apply (spec §11)
                preconditions = _broker_mod._preconditions(gate)
                if gate.unknown is not None:
                    self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan_id, outcome=f"gate_unknown({gate.unknown})",
                              preconditions=preconditions)
                    return _verbs_mod.err(f"gate_unknown({gate.unknown})", {"reason": gate.reason, "preconditions": preconditions})
                if not gate.safe:
                    self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan_id, outcome="gate_blocked", preconditions=preconditions)
                    return _verbs_mod.err("gate_blocked", {"reason": gate.reason, "preconditions": preconditions})
                if gate.plane["mode"] == "local-only" and args.get("local_only_ack") != LOCAL_ONLY_ACK:
                    self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan_id, outcome="local_only_ack_required",
                              preconditions=preconditions)
                    return _verbs_mod.err("local_only_ack_required", {"plane": gate.plane, "ack": LOCAL_ONLY_ACK})
                return self._exec_docker_write(plan, preconditions)
            if plan.verb == "start":
                return self._exec_docker_write(plan, plan.preconditions)
            if plan.verb == "cancel-drain":
                event = self._drain.cancel()
                self._watches[plan_id] = _broker_mod.VerifyWatch(plan_id=plan_id, verb=plan.verb, kind="none", cursor_before=None,
                                                                 started=now, verified=True, lines=["drain cleared · nothing restarted"])
                seq = self._log(peer_uid=os.getuid(), verb=plan.verb, phase=event, plan_id=plan_id, outcome="cancelled")
                return _verbs_mod.ok(result={"outcome": "cancelled", "exit_code": 0, "cursor_before": None, "audit_seq": seq,
                                             "preconditions": plan.preconditions})
            if (plan.verb == "doctor" and self._last_doctor is not None
                    and now - self._last_doctor < _broker_mod.DOCTOR_MIN_INTERVAL_S):
                self._log(peer_uid=os.getuid(), verb="doctor", phase="refused", plan_id=plan_id, outcome="doctor_too_soon")
                return _verbs_mod.err("doctor_too_soon")
            if plan.verb in ("skills-set", "doctor"):
                result = self._apply_transient(plan)
                release = not result.get("ok", False)  # transfer cleanup only after successful thread start
                return result
            if plan.verb == "kill-orphans":
                return self._apply_kill(plan)
            return _verbs_mod.err("internal", {"reason": "unhandled verb"})
        except Exception as exc:
            code = exc.code if isinstance(exc, BrokerError) else "internal"
            detail = exc.detail if isinstance(exc, BrokerError) else {"reason": type(exc).__name__}
            self._log(peer_uid=os.getuid(), verb=plan.verb if plan is not None else "apply", phase="refused", plan_id=audit_id,
                      outcome=f"internal: {type(exc).__name__}" if code == "internal" else code)
            watch = self._watches.get(plan_id)
            if watch is not None:
                watch.kind, watch.done, watch.verified = "none", True, False
                watch.reason = code + ": " + json.dumps(detail, sort_keys=True)
            return _verbs_mod.err(code, detail)
        finally:
            watch = self._watches.get(plan_id)
            if release and watch is not None and watch.kind == "none" and watch.verified is None:
                watch.done, watch.verified, watch.reason = True, False, "apply refused; plan spent"
            if release:
                self._in_flight = None
                self._lock.release()

    def _exec_docker_write(self, plan, preconditions: dict) -> dict:
        started = self._now()
        try:
            done = self._docker(plan.argv[1], plan.argv)
            exit_code: int | None = done.returncode
        except BrokerError as exc:
            exit_code = None if exc.code == "timeout" else -1
        kind = {"restart": "restart", "drain-restart": "restart", "stop": "stop", "start": "start"}[plan.verb]
        watch = _broker_mod.VerifyWatch(plan_id=plan.plan_id, verb=plan.verb, kind=kind, cursor_before=None, started=started)
        self._watches[plan.plan_id] = watch
        outcome = "applied" if exit_code == 0 else ("timeout" if exit_code is None else f"exit {exit_code}")
        seq = self._log(peer_uid=os.getuid(), verb=plan.verb, phase="apply", plan_id=plan.plan_id, preconditions=preconditions, outcome=outcome)
        if exit_code != 0:
            return _verbs_mod.err("timeout" if exit_code is None else "internal", {"outcome": outcome, "exit_code": exit_code, "audit_seq": seq})
        return _verbs_mod.ok(result={"outcome": "applied", "exit_code": 0, "cursor_before": None, "audit_seq": seq, "preconditions": preconditions})

    def _apply_transient(self, plan) -> dict:
        watch = _broker_mod.VerifyWatch(plan_id=plan.plan_id, verb=plan.verb, kind="transient", cursor_before=None, started=self._now())
        self._watches[plan.plan_id] = watch
        previous_doctor = self._last_doctor
        if plan.verb == "doctor":
            self._last_doctor = self._now()

        def worker() -> None:
            try:
                done = self._docker(plan.verb, plan.argv, timeout_s=sum(CONTAINER_TIMEOUTS[plan.verb]) + 5)
                watch.lines = [_broker_mod._CURRENCY_FIGURE_RE.sub("", redact(ln)) for ln in _text(done.stdout).splitlines() if ln.strip()]
                watch.rc = done.returncode
                watch.verified = done.returncode == 0
                watch.reason = _broker_mod._transient_reason(plan.verb, done.returncode, watch.lines)
                if plan.verb == "skills-set" and watch.verified:
                    self._skills_listing = None
                    listing = self._read("skills", {})           # spec §11 skills row: verify by re-listing (container-reported)
                    rows = [ln.split() for ln in listing.get("lines", [])]
                    row = next((r for r in rows if len(r) > 1 and r[0] in ("on", "off") and r[1] == plan.args["skill_id"]), None)
                    watch.verified = row is not None and (row[0] == "on") is bool(plan.args["on"])
                    if not watch.verified:
                        watch.reason = "re-listing disagrees"
            except BrokerError as exc:
                watch.verified, watch.reason = False, exc.code
            finally:
                watch.done = True
                self._log(peer_uid=os.getuid(), verb=plan.verb, phase="verify", plan_id=plan.plan_id, outcome="finished", verified=watch.verified)
                self._in_flight = None
                self._lock.release()

        seq = self._log(peer_uid=os.getuid(), verb=plan.verb, phase="apply", plan_id=plan.plan_id, preconditions=plan.preconditions, outcome="started")
        try:
            thread = threading.Thread(target=worker, name=f"seat-docker-{plan.verb}", daemon=True)
            self._threads[plan.plan_id] = thread
            thread.start()
        except Exception:  # constructor/start failure: no worker owns cleanup yet
            self._threads.pop(plan.plan_id, None)
            self._last_doctor = previous_doctor  # no child ran: preserve the preceding cooldown
            watch.done, watch.verified, watch.reason = True, False, "thread start failed"
            self._log(peer_uid=os.getuid(), verb=plan.verb, phase="verify", plan_id=plan.plan_id,
                      outcome="thread start failed", verified=False)
            return _verbs_mod.err("internal", {"reason": "thread start failed"})
        return _verbs_mod.ok(result={"outcome": "started", "exit_code": None, "cursor_before": None, "audit_seq": seq,
                                     "preconditions": plan.preconditions, "unit": None})

    def _process_snapshot(self) -> list[dict]:
        done = self._exec(["python3", "-", "--proc-snapshot"], kind="sessions", family="kill-orphans",
                          stdin=broker_script("process_snapshot"))
        try:
            rows = json.loads(_text(done.stdout))
            keys = {"pid", "ppid", "pgid", "uid", "cgroup", "start_ticks", "age_s"}
            valid = isinstance(rows, list) and all(
                isinstance(r, dict) and set(r) == keys
                and all(isinstance(r[k], int) and not isinstance(r[k], bool) and r[k] >= 0
                        for k in ("pid", "ppid", "pgid", "uid", "start_ticks"))
                and isinstance(r["cgroup"], str) and bool(r["cgroup"])
                and isinstance(r["age_s"], (int, float)) and not isinstance(r["age_s"], bool)
                for r in rows)
            valid = valid and len({r["pid"] for r in rows}) == len(rows)
        except (ValueError, TypeError):
            valid = False
        if done.returncode != 0 or not valid:
            self._log(verb="kill-orphans", phase="refused", outcome="process snapshot unavailable")
            raise BrokerError("unreadable", {"what": "process snapshot"})
        return rows

    @staticmethod
    def _orphan_identity_safe(row: dict, rows: list[dict], snapshot: dict) -> bool:
        if (row["uid"] != 1000 or row["age_s"] <= _broker_mod.ORPHAN_MIN_AGE_S
                or snapshot.get(row["pid"]) != _broker_mod._proc_identity(row)):
            return False
        by_pid = {r["pid"]: r for r in rows}
        seen = set()
        current = row
        while current["pid"] not in seen:
            seen.add(current["pid"])
            if current["pid"] == 1:
                return False
            if current["ppid"] == 0:
                return True
            current = by_pid.get(current["ppid"])
            if current is None:
                return False
        return False

    def _kill_identity_safe(self, rows: list[dict], kind: str, ident: int, snapshot: dict) -> bool:
        members = [r for r in rows if r["pgid" if kind == "pgid" else "pid"] == ident]
        return bool(members) and all(self._orphan_identity_safe(r, rows, snapshot) for r in members)

    def _apply_kill(self, plan) -> dict:
        now = self._now()
        killed: list[dict] = []
        skipped: list[dict] = []
        try:
            for pgid_text, mode in plan.preconditions["kill_mode_by_pgid"].items():
                members = [r for r in plan.preconditions["candidates"] if str(r["pgid"]) == pgid_text]
                pgid = int(pgid_text)
                rows = self._process_snapshot()
                if (mode == "group" and self._kill_identity_safe(rows, "pgid", pgid, plan.kill_snapshot)
                        and all(self._kill_identity_safe(rows, "pid", m["pid"], plan.kill_snapshot) for m in members)):
                    done = self._exec(["kill", "-TERM", "--", f"-{pgid}"], kind=None, family="kill-orphans")
                    if done.returncode != 0:
                        raise BrokerError("unreadable", {"what": "kill failed"})
                    self._pending_kills.append((now + _broker_mod.KILL_GRACE_S, "pgid", pgid))
                    self._kill_snapshots[("pgid", pgid)] = dict(plan.kill_snapshot)
                    killed.append({"mode": "group", "pgid": pgid, "pids": [m["pid"] for m in members]})
                else:
                    for row in members:
                        rows = self._process_snapshot()
                        if not self._kill_identity_safe(rows, "pid", row["pid"], plan.kill_snapshot):
                            skipped.append({"pid": row["pid"], "reason": "changed since plan"})
                            continue
                        done = self._exec(["kill", "-TERM", str(row["pid"])], kind=None, family="kill-orphans")
                        if done.returncode != 0:
                            raise BrokerError("unreadable", {"what": "kill failed"})
                        self._pending_kills.append((now + _broker_mod.KILL_GRACE_S, "pid", row["pid"]))
                        self._kill_snapshots[("pid", row["pid"])] = dict(plan.kill_snapshot)
                        killed.append({"mode": "individual", "pid": row["pid"]})
        except Exception as exc:
            code = exc.code if isinstance(exc, BrokerError) else "internal"
            detail = exc.detail if isinstance(exc, BrokerError) else {"reason": type(exc).__name__}
            return self._finish_kill(plan, now, killed, skipped, _verbs_mod.err(code, detail))
        return self._finish_kill(plan, now, killed, skipped)

    def _finish_kill(self, plan, now: float, killed: list[dict], skipped: list[dict], refusal: dict | None = None) -> dict:
        """Keep exactly the completed signals auditable and verifiable after a later refusal."""
        if refusal is not None:
            accounted = {pid for item in killed for pid in (item["pids"] if item["mode"] == "group" else [item["pid"]])}
            accounted.update(item["pid"] for item in skipped)
            skipped.extend({"pid": row["pid"], "reason": refusal["error"]}
                           for row in plan.preconditions["candidates"] if row["pid"] not in accounted)
        if refusal is not None and not killed:
            self._log(peer_uid=os.getuid(), verb=plan.verb, phase="refused", plan_id=plan.plan_id,
                      outcome=refusal["error"], args={"killed": [], "skipped": skipped})
            return _verbs_mod.err(refusal["error"], {**refusal.get("detail", {}), "plan_spent": True,
                                                  "partial": False, "killed": [], "skipped": skipped})
        # the plan's verify ("pids gone"): tick() decides it over the ps listing once every SIGKILL follow-up has run
        targets = [("pgid", k["pgid"]) if k["mode"] == "group" else ("pid", k["pid"]) for k in killed]
        self._watches[plan.plan_id] = _broker_mod.VerifyWatch(plan_id=plan.plan_id, verb="kill-orphans", kind="kill", cursor_before=None,
                                                              started=now, targets=targets, verified=None if targets else True)
        seq = self._log(peer_uid=os.getuid(), verb="kill-orphans", phase="apply", plan_id=plan.plan_id,
                        preconditions={"pids": [r["pid"] for r in plan.preconditions["candidates"]]}, outcome="partial" if refusal is not None else ("applied" if killed else "nothing to kill"),
                        args={"killed": killed})
        if refusal is not None:
            return _verbs_mod.err(refusal["error"], {**refusal.get("detail", {}), "plan_spent": True, "partial": True,
                                                  "killed": killed, "skipped": skipped, "audit_seq": seq})
        return _verbs_mod.ok(result={"outcome": "applied", "exit_code": 0, "cursor_before": None, "audit_seq": seq,
                                     "preconditions": plan.preconditions, "killed": killed, "skipped": skipped})

    def _verify(self, plan_id: str) -> dict:
        watch = self._watches.get(plan_id)
        if watch is None:
            raise BrokerError("unknown_plan", {"plan_id": plan_id})
        now = self._now()
        if watch.kind == "transient":
            return {"verified": watch.verified if watch.done else None, "connected": None, "verify_lines": list(watch.lines) if watch.done else [],
                    "cursor_after": None, "elapsed_s": round(now - watch.started, 1), "audit_seq": None, "reason": watch.reason if watch.done else None}
        if watch.kind in ("none", "kill"):          # decided at apply (drain arm, cancel-drain) or by tick() (kill-orphans)
            return watch.to_dict(now, None)
        lines = [(e, t) for e, t in self._tail_lines() if e >= watch.started - 1]
        unit_active = None
        if watch.kind == "stop":
            inspect = self._inspect()
            unit_active = None if inspect is None else inspect.get("running")
        previously = (watch.verified, watch.connected)
        watch.update(lines, now, unit_active=unit_active)
        seq = None
        if (watch.verified, watch.connected) != previously:          # one verify line per change, like the root broker
            seq = self._log(peer_uid=os.getuid(), verb=watch.verb, phase="verify", plan_id=plan_id,
                            outcome="verified" if watch.verified else ("pending" if watch.verified is None else "not verified"),
                            verified=watch.verified, connected=watch.connected)
        return watch.to_dict(now, seq)

    # -- housekeeping: the in-process drain (spec §11 drain-restart, Mac column) ---------------------

    def _flush_read_counts(self, now: float) -> None:
        """Read verbs are audited as counts only (spec §11; deviation 16): one ``reads`` line per READ_COUNT_FLUSH_S."""
        if not self._read_counts or now - self._reads_flushed_at < _broker_mod.READ_COUNT_FLUSH_S:
            return
        self._log(peer_uid=os.getuid(), verb=None, phase="reads", outcome="counts", args={"counts": dict(self._read_counts)})
        self._read_counts = {}
        self._reads_flushed_at = now

    def tick(self, now: float | None = None) -> list[str]:
        """Plan purge, the hourly read-count line, the verify line of a drain-fired restart, drain heartbeats from the tail
        (``drain_rearmed`` / ``drain_fire`` through the same fresh gate, then ``docker restart -t 30`` / ``drain_expired``)
        and the ``kill-orphans`` SIGKILL after ``KILL_GRACE_S``. In-process: it runs only while the TUI does (spec §11).
        Returns the audit events it wrote."""
        if not self._tick_lock.acquire(blocking=False):
            return []
        try:
            now = self._now() if now is None else now
            events: list[str] = []
            self._flush_read_counts(now)
            self._plans.purge(now)
            for fired in list(self._drain_fired):
                try:
                    data = self._verify(fired)
                except BrokerError:
                    data = {}
                if data.get("verified") is not None or fired not in self._watches:
                    self._drain_fired.discard(fired)
            if self._drain.armed is not None:
                event = self._drain.tick(now)
                if event:
                    events.append(event)
                    self._log(peer_uid=os.getuid(), verb="drain-restart", phase=event, outcome="expired")
                else:
                    for epoch, text in list(self._tail_lines()):
                        match = _gate_mod.HEARTBEAT_RE.match(text)
                        if not match or epoch <= self._drain_watermark:
                            continue
                        self._drain_watermark = epoch
                        armed_before = self._drain.armed
                        event = self._drain.on_heartbeat("idle" if match.group("work") == "idle" else "running", epoch)
                        if event:
                            events.append(event)
                            if event == _drain_mod.EVENT_FIRE:
                                self._fire_drain(events, armed_before)
                            else:
                                self._log(peer_uid=os.getuid(), verb="drain-restart", phase=event,
                                          plan_id=None if self._drain.armed is None else self._drain.armed.plan_id, outcome=event)
                        if self._drain.armed is None:
                            break
            still: list[tuple[float, str, int]] = []
            sigkilled: set[tuple[str, int]] = set()
            for deadline, kind, ident in self._pending_kills:
                if now < deadline:
                    still.append((deadline, kind, ident))
                    continue
                snapshot = self._kill_snapshots.pop((kind, ident), {})
                try:
                    rows = self._process_snapshot()
                except BrokerError:
                    rows = []
                safe = self._kill_identity_safe(rows, kind, ident, snapshot)
                if not safe:
                    self._log(verb="kill-orphans", phase="refused", outcome="identity unavailable or changed before SIGKILL")
                if safe:
                    argv = ["kill", "-KILL", "--", f"-{ident}"] if kind == "pgid" else ["kill", "-KILL", str(ident)]
                    try:
                        self._exec(argv, kind=None, family="kill-orphans")
                    except BrokerError:
                        pass
                    events.append("sigkill")
                    sigkilled.add((kind, ident))
            self._pending_kills = still
            self._resolve_kill_watches(now, sigkilled)             # the kill-orphans verify, as the root broker decides it
            self._last_tick = now
            return events
        finally:
            self._tick_lock.release()

    def _resolve_kill_watches(self, now: float, sigkilled: set[tuple[str, int]]) -> None:
        """The root broker's ``kill-orphans`` verdict (``_decide_kill_watch``) over the container's ``ps`` listing: decided
        once no SIGKILL follow-up is queued for the watch and none went out on this tick; an unreadable listing is a
        ``false`` naming why, never a silent pass. One ``verify`` audit line per decision."""
        queued = {(kind, ident) for _deadline, kind, ident in self._pending_kills}
        ready = [w for w in self._watches.values() if w.kind == "kill" and w.verified is None
                 and not any(t in queued or t in sigkilled for t in w.targets)]
        if not ready:
            return
        try:
            rows = self._process_snapshot()
        except BrokerError as exc:
            for watch in ready:
                watch.verified, watch.reason = False, f"ps listing unavailable ({exc.code})"
            rows = None
        for watch in ready:
            if rows is not None:
                _broker_mod._decide_kill_watch(watch, pids={r["pid"] for r in rows}, pgids={r["pgid"] for r in rows})
            self._log(peer_uid=os.getuid(), verb=watch.verb, phase="verify", plan_id=watch.plan_id,
                      outcome="verified" if watch.verified else "not verified", verified=watch.verified)

    def _fire_drain(self, events: list[str], armed_before) -> None:
        """``drain_fire``: the same fresh gate (a)-(e) as apply, then ``docker restart -t 30``; otherwise the SAME drain
        waits on (``Drain.restore``: plan id and ``DRAIN_MAX_S`` deadline unchanged)."""
        if not self._lock.acquire(blocking=False):
            self._drain.restore(armed_before)                    # a write is in flight: keep waiting
            return
        try:
            gate = self._gate()
            preconditions = _broker_mod._preconditions(gate)
            if gate.unknown is not None or not gate.safe or (gate.plane["mode"] == "local-only" and not self.offline):
                self._drain.restore(armed_before)
                self._log(peer_uid=os.getuid(), verb="drain-restart", phase="drain_rearmed", plan_id=armed_before.plan_id,
                          preconditions=preconditions, outcome=gate.reason or f"plane {gate.plane['mode']}")
                events.append("drain_rearmed")
                return
            plan = self._plans.create("drain-restart", {"offline": self.offline},
                                      ["docker", "restart", "-t", str(MAC_STOP_TIMEOUT_S), self.container], preconditions, None, {})
            plan.spent = True                                    # synthetic: never appliable by id
            self._in_flight = {"verb": "drain-restart", "plan_id": plan.plan_id, "since": _iso(self._now())}
            self._log(peer_uid=os.getuid(), verb="drain-restart", phase="drain_fire", plan_id=plan.plan_id,
                      preconditions=preconditions, outcome="firing")
            self._exec_docker_write(plan, preconditions)
            self._drain_fired.add(plan.plan_id)
        finally:
            self._in_flight = None
            self._lock.release()

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

        A partial block carries ``"reason"`` naming the failed half, so the manager lands the unit source
        per field with the reason (WP7 deviation 6, spec §14 mutation proof 8).
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
__all__ = [
    "APPLY_VERB", "AUDIT_FILE_MAC", "ApplyResult", "BrokerError", "BrokerProtocol", "CLIENT_TIMEOUT_S", "CONTAINER_TIMEOUTS",
    "DOCKER_BREAKER_S", "DOCKER_TIMEOUT_S", "DockerUnitReader", "FakeBroker", "FixtureUnitReader", "GATED_VERBS",
    "IMD_DASHD_AVAILABLE", "LOCAL_ONLY_ACK", "LOCAL_TICK_S", "LocalDockerBroker", "MAC_CONTAINER", "MAC_STOP_TIMEOUT_S", "NOT_ON_DOCKER",
    "PROTOCOL_VERSION", "Plan", "READ_VERBS", "SKILL_ID_RE", "SOCKET_PATH", "SYSTEMCTL_PROPS", "SystemdUnitReader",
    "TRANSIENT_VERBS", "UnitReader", "UnixSocketBroker", "VerifyResult", "WRITE_VERBS", "broker_script", "parse_cgroup",
    "parse_docker_inspect", "parse_docker_ps", "parse_docker_stats", "parse_imd_skills", "parse_imd_status", "parse_imd_tools",
    "parse_systemctl_show", "parse_whoami",
]
