"""The broker's fixed verb enum, typed argument schemas and wire encoding (spec §11, contract C.11).

One JSON line in ``{"v":1,"verb":"<enum>","args":{...}}``, one JSON line out
``{"ok":bool,"data"|"plan"|"result"|"error":...}``. Sending a WRITE verb is a *plan* request;
``apply`` consumes the plan. Nothing here touches a socket, a process or a file: this module is
pure so that both the root broker and the TUI-side client import the same names.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping

PROTOCOL_VERSION = 1

READ_VERBS = ("ping", "seat", "whoami", "status", "skills", "tools", "sessions", "work-stat", "outbox", "orphans",
              "hints-stat", "auth-mtime", "gate", "verify", "audit-tail")
WRITE_VERBS = ("restart", "drain-restart", "cancel-drain", "stop", "start", "enable-boot", "disable-boot",
               "skills-set", "kill-orphans", "doctor")          # sending one of these = a PLAN request
APPLY_VERB = "apply"
ALL_VERBS = READ_VERBS + WRITE_VERBS + (APPLY_VERB,)
TRANSIENT_VERBS = ("whoami", "status", "skills", "tools", "sessions", "doctor", "skills-set")   # systemd-run children
INPROCESS_WORKER_VERBS = ("seat", "outbox", "work-stat", "hints-stat", "auth-mtime")            # Popen(user=imd-worker)
ROOT_VERBS = ("ping", "orphans", "gate", "verify", "audit-tail", "kill-orphans", "restart", "stop", "start",
              "enable-boot", "disable-boot", "drain-restart", "cancel-drain")
GATED_VERBS = ("restart", "stop", "drain-restart")             # idle gate G at apply (drain: at fire)
INVERSE = {"restart": "stop", "stop": "start", "start": "stop", "enable-boot": "disable-boot", "disable-boot": "enable-boot",
           "drain-restart": "cancel-drain", "cancel-drain": None, "skills-set": "skills-set", "kill-orphans": None, "doctor": None}

#: Used with ``fullmatch`` -- the spec's ``^…$`` made trailing-newline-safe (spec §11 skills row).
SKILL_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
NODE8_RE = re.compile(r"[0-9a-f]{8}", re.ASCII)
PLAN_ID_RE = re.compile(r"[0-9a-f]{16}", re.ASCII)
LOCAL_ONLY_ACK = "local-only"

ERRORS = ("bad_request", "bad_verb", "bad_args", "peer_refused", "busy", "plan_spent", "plan_expired", "unknown_plan",
          "bad_confirm", "gate_blocked", "gate_unknown(outbox)", "gate_unknown(unit)", "local_only_ack_required",
          "force_disabled", "force_node8_mismatch", "bad_skill_id", "skill_not_listed", "doctor_too_soon",
          "drain_not_armed", "drain_already_armed", "projection_refused", "whoami_unavailable",
          "child_posture_unavailable", "timeout", "unreadable", "internal")

#: verb -> {arg name: allowed type(s)}. An arg name not listed -> bad_args; a listed arg of the wrong
#: type -> bad_args. Optional args are listed with ``type(None)`` among their allowed types.
_OPT_STR = (str, type(None))
ARG_SCHEMAS: dict[str, dict[str, type | tuple[type, ...]]] = {
    # plan requests
    "restart": {"offline": bool, "force_node8": _OPT_STR},
    "stop": {"offline": bool, "force_node8": _OPT_STR},
    "drain-restart": {"offline": bool, "force_node8": _OPT_STR},
    "start": {}, "enable-boot": {}, "disable-boot": {}, "cancel-drain": {},
    "skills-set": {"skill_id": str, "on": bool},
    "kill-orphans": {"pids": list},
    "doctor": {},
    # apply
    APPLY_VERB: {"plan_id": str, "confirm": str, "force_node8": _OPT_STR, "local_only_ack": _OPT_STR},
    # reads
    "sessions": {"since": (int, float), "runtime": str},
    "audit-tail": {"n": int},
    "verify": {"plan_id": str},
    "gate": {"offline": bool},
    "ping": {}, "seat": {}, "whoami": {}, "status": {}, "skills": {}, "tools": {}, "work-stat": {}, "outbox": {},
    "orphans": {}, "hints-stat": {}, "auth-mtime": {},
}
#: Args that must be present (everything else in a schema is optional).
REQUIRED_ARGS: dict[str, tuple[str, ...]] = {
    "skills-set": ("skill_id", "on"),
    "kill-orphans": ("pids",),
    APPLY_VERB: ("plan_id", "confirm"),
    "sessions": ("since", "runtime"),
    "audit-tail": ("n",),
    "verify": ("plan_id",),
}

MAX_REQUEST_BYTES = 64 * 1024


def encode_request(verb: str, args: Mapping | None = None) -> bytes:
    """One JSON line plus ``b"\\n"``."""
    return (json.dumps({"v": PROTOCOL_VERSION, "verb": verb, "args": dict(args or {})},
                       separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def decode_request(line: bytes) -> tuple[str, dict]:
    """``(verb, args)`` from one wire line; raises ``ValueError`` (-> ``bad_request``) on any malformed input."""
    if not isinstance(line, (bytes, bytearray)):
        raise ValueError("request is not bytes")
    if len(line) > MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    try:
        obj = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"request is not one JSON object: {exc.__class__.__name__}") from None
    if not isinstance(obj, dict) or obj.get("v") != PROTOCOL_VERSION:
        raise ValueError("request must be an object with v == 1")
    verb = obj.get("verb")
    args = obj.get("args", {})
    if not isinstance(verb, str) or not isinstance(args, dict):
        raise ValueError("verb must be a string and args an object")
    return verb, args


def ok(**payload) -> dict:
    """``{"ok": True, **payload}`` -- the payload key is ``data`` | ``plan`` | ``result``."""
    return {"ok": True, **payload}


def err(code: str, detail: Mapping | None = None) -> dict:
    if code not in ERRORS:
        raise ValueError(f"unknown error code {code!r}")
    return {"ok": False, "error": code, "detail": dict(detail or {})}


def _type_ok(value: object, allowed: type | tuple[type, ...]) -> bool:
    kinds = allowed if isinstance(allowed, tuple) else (allowed,)
    if isinstance(value, bool) and bool not in kinds:
        return False                      # bool is an int subclass; a schema that says int means int
    return isinstance(value, kinds)


def validate_args(verb: str, args: Mapping) -> str | None:
    """The error code for a bad verb/arg set, else ``None``.

    ``skill_id`` is checked only for *type* here; its value is checked by the broker with
    ``SKILL_ID_RE.fullmatch`` so the refusal can be audited without echoing it (spec §11).
    """
    if verb not in ALL_VERBS:
        return "bad_verb"
    schema = ARG_SCHEMAS[verb]
    for name in REQUIRED_ARGS.get(verb, ()):
        if name not in args:
            return "bad_args"
    for name, value in args.items():
        if name not in schema or not _type_ok(value, schema[name]):
            return "bad_args"
    if verb == "kill-orphans":
        pids = args.get("pids", [])
        if not pids or not all(isinstance(p, int) and not isinstance(p, bool) and p > 1 for p in pids):
            return "bad_args"
    return None


__all__ = [
    "PROTOCOL_VERSION", "READ_VERBS", "WRITE_VERBS", "APPLY_VERB", "ALL_VERBS", "TRANSIENT_VERBS",
    "INPROCESS_WORKER_VERBS", "ROOT_VERBS", "GATED_VERBS", "INVERSE", "SKILL_ID_RE", "NODE8_RE", "PLAN_ID_RE",
    "LOCAL_ONLY_ACK", "ERRORS", "ARG_SCHEMAS", "REQUIRED_ARGS", "MAX_REQUEST_BYTES",
    "encode_request", "decode_request", "ok", "err", "validate_args",
]
