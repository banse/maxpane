"""``imd_dashd/verbs.py`` -- the fixed enum and typed args every other broker module trusts (spec §11)."""
from __future__ import annotations

import json

import pytest

from imd_dashd import verbs
from imd_dashd.verbs import (
    ALL_VERBS, APPLY_VERB, ARG_SCHEMAS, ERRORS, GATED_VERBS, INPROCESS_WORKER_VERBS, INVERSE, LOCAL_ONLY_ACK,
    PLAN_ID_RE, READ_VERBS, ROOT_VERBS, SKILL_ID_RE, TRANSIENT_VERBS, WRITE_VERBS,
    decode_request, encode_request, err, ok, validate_args,
)


def test_enum_is_exactly_the_spec_verb_table():
    # spec §11 verb table + read verbs; §11 "Excluded entirely": no unlink/pair/site/tools-key/update/tier/capacity
    assert WRITE_VERBS == ("restart", "drain-restart", "cancel-drain", "stop", "start", "enable-boot", "disable-boot",
                           "skills-set", "kill-orphans", "doctor")
    assert READ_VERBS == ("ping", "seat", "whoami", "status", "skills", "tools", "sessions", "work-stat", "outbox",
                          "orphans", "hints-stat", "auth-mtime", "gate", "verify", "audit-tail")
    for excluded in ("unlink", "pair", "site", "update", "tier", "capacity", "tools-key", "prune", "hints-put"):
        assert excluded not in ALL_VERBS
    assert len(ALL_VERBS) == len(set(ALL_VERBS)) == 26
    assert set(TRANSIENT_VERBS) | set(INPROCESS_WORKER_VERBS) | set(ROOT_VERBS) == set(READ_VERBS) | set(WRITE_VERBS)
    assert set(TRANSIENT_VERBS).isdisjoint(INPROCESS_WORKER_VERBS)
    assert set(GATED_VERBS) == {"restart", "stop", "drain-restart"}
    assert set(INVERSE) == set(WRITE_VERBS)
    assert INVERSE["restart"] == "stop" and INVERSE["enable-boot"] == "disable-boot" and INVERSE["doctor"] is None
    assert len(ERRORS) == len(set(ERRORS))
    assert set(ARG_SCHEMAS) == set(ALL_VERBS)


@pytest.mark.parametrize("good", ["oracle-assess", "a", "build.ponder_indexer-2", "x" * 64])
def test_skill_id_regex_accepts_the_spec_shape(good):
    assert SKILL_ID_RE.fullmatch(good)


@pytest.mark.parametrize("bad", ["oracle assess", "a;rm", "-leading", "Upper", "x" * 65, "", "a\n", "ä"])
def test_skill_id_regex_refuses_shell_and_unicode(bad):
    # spec §11: skill_id must match ^[a-z0-9][a-z0-9._-]{0,63}$ before it may enter argv or the audit
    assert SKILL_ID_RE.fullmatch(bad) is None


def test_wire_round_trip_is_one_json_line():
    line = encode_request("restart", {"offline": False})
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert json.loads(line) == {"v": 1, "verb": "restart", "args": {"offline": False}}
    assert decode_request(line) == ("restart", {"offline": False})
    assert decode_request(encode_request("ping")) == ("ping", {})


@pytest.mark.parametrize("raw", [b"", b"not json\n", b"[1,2]\n", b'{"v":2,"verb":"ping","args":{}}\n',
                                 b'{"v":1,"verb":7,"args":{}}\n', b'{"v":1,"verb":"ping","args":[]}\n',
                                 b"\xff\xfe\n", b'{"v":1,"verb":"ping","args":{}}' + b" " * (64 * 1024)])
def test_decode_refuses_every_malformed_line(raw):
    with pytest.raises(ValueError):
        decode_request(raw)


def test_ok_and_err_shapes():
    assert ok(data={"pid": 1}) == {"ok": True, "data": {"pid": 1}}
    assert err("busy", {"verb": "restart", "plan_id": "7f3a9c1e2b4d6081", "since": "t"}) == {
        "ok": False, "error": "busy", "detail": {"verb": "restart", "plan_id": "7f3a9c1e2b4d6081", "since": "t"}}
    assert err("timeout") == {"ok": False, "error": "timeout", "detail": {}}
    with pytest.raises(ValueError):
        err("not_a_code")


@pytest.mark.parametrize("verb,args,expected", [
    ("restart", {"offline": False}, None),
    ("restart", {"offline": True, "force_node8": "0c1f9727"}, None),
    ("restart", {"offline": "no"}, "bad_args"),
    ("restart", {"unknown": 1}, "bad_args"),
    ("restart", {"offline": 1}, "bad_args"),                     # bool means bool, not int
    ("skills-set", {"skill_id": "oracle-assess", "on": False}, None),
    ("skills-set", {"skill_id": "oracle-assess"}, "bad_args"),  # `on` required
    ("skills-set", {"skill_id": 5, "on": True}, "bad_args"),
    ("kill-orphans", {"pids": [64861, 64876]}, None),
    ("kill-orphans", {"pids": []}, "bad_args"),
    ("kill-orphans", {"pids": [1]}, "bad_args"),                # never pid 1 / 0 / negative
    ("kill-orphans", {"pids": ["64861"]}, "bad_args"),
    (APPLY_VERB, {"plan_id": "7f3a9c1e2b4d6081", "confirm": "7f3a"}, None),
    (APPLY_VERB, {"plan_id": "7f3a9c1e2b4d6081", "confirm": "7f3a", "local_only_ack": LOCAL_ONLY_ACK}, None),
    (APPLY_VERB, {"plan_id": "7f3a9c1e2b4d6081"}, "bad_args"),
    ("sessions", {"since": 1790000000.5, "runtime": "codex"}, None),
    ("sessions", {"since": "yesterday", "runtime": "codex"}, "bad_args"),
    ("audit-tail", {"n": 5}, None),
    ("audit-tail", {"n": True}, "bad_args"),
    ("audit-tail", {}, "bad_args"),
    ("verify", {"plan_id": "7f3a9c1e2b4d6081"}, None),
    ("gate", {"offline": True}, None),
    ("ping", {}, None),
    ("ping", {"x": 1}, "bad_args"),
    ("tier-set", {}, "bad_verb"),                               # spec §11: tier/capacity/update are not verbs
    ("update", {}, "bad_verb"),
])
def test_validate_args_is_the_type_gate(verb, args, expected):
    assert validate_args(verb, args) == expected


def test_plan_id_regex_is_sixteen_hex():
    assert PLAN_ID_RE.fullmatch("7f3a9c1e2b4d6081")
    assert PLAN_ID_RE.fullmatch("7f3a9c1e2b4d608") is None
    assert PLAN_ID_RE.fullmatch("7F3A9C1E2B4D6081") is None


def test_module_is_pure_stdlib():
    # spec §4.1 trust boundary (3): root code is stdlib only and imports nothing from maxpane_dashboard
    import inspect
    source = inspect.getsource(verbs)
    assert "maxpane" not in source
    assert "import subprocess" not in source and "import socket" not in source
