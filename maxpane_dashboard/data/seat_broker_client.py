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


# ---------------------------------------------------------------- parsers


