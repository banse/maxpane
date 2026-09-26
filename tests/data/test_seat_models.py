"""Tests for ``maxpane_dashboard.data.seat_models`` (PEPEPANE plan WP1).

Fixtures under ``tests/fixtures/seat/status/`` are synthetic v2 documents
(``status_v2_*.json``), one aidude-v1-shaped document and one v2 document that
leaks a 64-hex value.  No network, no clock: ``fold_status_document`` with
``now=None`` uses ``completedAtUtc`` as its reference.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
import re
import time
from pathlib import Path

import pytest

from maxpane_dashboard.data import seat_models as sm

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat" / "status"
REPO = Path(__file__).resolve().parents[2]
HEX64 = "0123456789abcdef" * 4
HOST = {"kind": "systemd", "unit": "imd-worker.service", "container": None, "runtime": "codex", "hostname": "ubuntu"}
STATUS_FIXTURES = (
    "status_v2_healthy.json", "status_v2_tail_dead.json", "status_v2_api_down.json", "status_v2_offline.json",
    "status_v2_local_only_gate.json", "status_v2_gate_unknown.json",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path, value


# ---------------------------------------------------------------------------
# Task 1.6 — constants, Refusal, empty_*, parse_iso, as_of_hhmm, truncate_id
# ---------------------------------------------------------------------------


def test_constants_are_the_contract_values():
    # spec §7 / contract B: schemaVersion 2, producer string, 2 MiB cap, the 14 sources, the 4 last-good API sources
    assert sm.SCHEMA_VERSION == 2
    assert sm.PRODUCER == "pepepane 0.1.0"
    assert sm.MAX_DOCUMENT_BYTES == 2 * 1024 * 1024
    assert sm.SOURCE_NAMES == (
        "tail", "unit", "broker", "seat", "status", "skills", "sessions", "workstat", "hints", "auth",
        "standing", "seatWork", "reasons", "plane",
    )
    assert sm.LAST_GOOD_SOURCES == frozenset({"standing", "seatWork", "reasons", "plane"})
    assert sm.SOURCE_TAGS == {"L": "tail", "H": "broker", "C": "broker", "U": "unit", "S": "sessions",
                              "A": "api", "D": "derived", "K": "configured"}


def test_refusal_is_a_frozen_pair():
    refusal = sm.Refusal("wrong_schema", "schemaVersion=1")
    assert (refusal.code, refusal.detail) == ("wrong_schema", "schemaVersion=1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.code = "x"  # type: ignore[misc]


def test_empty_source_shape_and_trust():
    assert sm.empty_source() == {
        "ok": None, "asOfUtc": None, "ageS": None, "reason": None, "trust": "host",
        "failures": 0, "unavailable": False, "watermark": None, "threadAliveAt": None,
    }
    assert sm.empty_source(trust="container")["trust"] == "container"


def test_empty_document_has_every_block_and_no_zero_leaf():
    # spec §7: every block present, failed read = null never 0
    doc = sm.empty_document(started_at_utc="2026-09-26T03:40:07Z", host=HOST)
    assert set(doc) == {
        "schemaVersion", "producer", "startedAtUtc", "completedAtUtc", "host", "sources", "seat", "daemon", "auth",
        "unit", "current", "queue", "tasks", "today", "cost", "quota", "standing", "plane", "machine", "control",
    }
    assert doc["schemaVersion"] == 2 and doc["producer"] == "pepepane 0.1.0"
    assert doc["startedAtUtc"] == "2026-09-26T03:40:07Z" and doc["completedAtUtc"] is None
    assert doc["host"] == HOST
    assert tuple(doc["sources"]) == sm.SOURCE_NAMES
    for path, leaf in _leaves(doc):
        if path.startswith(("sources.", "host.")) or path in ("schemaVersion", "producer", "startedAtUtc"):
            continue
        assert leaf is None, f"{path} is {leaf!r}, not None"
    assert doc["tasks"]["rows"] == [] and doc["seat"]["skills"]["optOut"] == [] and doc["standing"]["running"] == []
    assert doc["cost"]["series"] == {"outputTokensPerDay": [], "tasksPerDay": [], "acceptedPerDay": []}


def test_parse_iso_reads_z_ms_offset_and_naive_as_utc():
    assert sm.parse_iso("2026-09-26T03:40:07Z") == 1790394007.0
    assert sm.parse_iso("2026-09-26T01:52:44.909Z") == pytest.approx(1790387564.909)
    assert sm.parse_iso("2026-09-26T03:40:07+00:00") == 1790394007.0
    assert sm.parse_iso("2026-09-26T05:40:07+02:00") == 1790394007.0
    assert sm.parse_iso("2026-09-26T03:40:07") == 1790394007.0
    for bad in (None, "", "   ", "yesterday", 1790394007, "2026-09-26 03:11:29.985+00 extra"):
        assert sm.parse_iso(bad) is None


def test_as_of_hhmm_is_local_time_of_the_stamp():
    local = time.localtime(1790394007.0)
    assert sm.as_of_hhmm("2026-09-26T03:40:07Z") == f"{local.tm_hour:02d}:{local.tm_min:02d}"
    assert re.fullmatch(r"\d\d:\d\d", sm.as_of_hhmm("2026-09-26T03:40:07Z"))
    assert sm.as_of_hhmm(None) is None
    assert sm.as_of_hhmm("garbage") is None
    assert sm.as_of_hhmm("1970-01-01T00:00:00Z") is None


def test_truncate_id_keeps_eight_characters():
    # spec §13 / §16 #13: device public key and wallet truncated to 8 chars
    assert sm.truncate_id(HEX64) == "01234567"
    assert sm.truncate_id("72b617d4" + "ab" * 28) == "72b617d4"
    assert sm.truncate_id("0x887b9f1234", 8) == "0x887b9f"
    assert sm.truncate_id("abc") == "abc"
    assert sm.truncate_id(7) == "7"
    assert sm.truncate_id(HEX64, n=12) == "0123456789ab"
    assert sm.truncate_id(None) is None
    assert sm.truncate_id("   ") is None


@pytest.mark.guard
def test_seat_models_imports_are_pure():
    # spec §14 purity rule (2): no Textual, subprocess, socket or httpx under data/seat_models.py
    tree = ast.parse((REPO / "maxpane_dashboard" / "data" / "seat_models.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert modules.isdisjoint({"textual", "rich", "subprocess", "socket", "httpx"}), modules
    froms = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert froms & {m for m in froms if m and m.startswith("maxpane_dashboard")} == {
        "maxpane_dashboard.analytics.seat_redact"
    }


# ---------------------------------------------------------------------------
# Task 1.7 — validate_status_document
# ---------------------------------------------------------------------------


def _minimal_v2() -> dict:
    return {"schemaVersion": 2, "producer": "pepepane 0.1.0", "seat": {"tokenId": 7, "deviceKeyPublic": "72b617d4"}}


def test_validate_accepts_a_clean_v2_document():
    assert sm.validate_status_document(_minimal_v2()) is None
    assert sm.validate_status_document(sm.empty_document(started_at_utc="2026-09-26T03:40:07Z", host=HOST)) is None
    assert sm.validate_status_document(_load("status_v2_healthy.json")) is None


def test_validate_refuses_not_an_object():
    assert sm.validate_status_document([]) == sm.Refusal("not_an_object", "type=list")
    assert sm.validate_status_document("{}") == sm.Refusal("not_an_object", "type=str")
    assert sm.validate_status_document(None) == sm.Refusal("not_an_object", "type=NoneType")


def test_validate_refuses_wrong_schema():
    # spec §7 refusal rules: schemaVersion != 2 -> wrong_schema (aidude v1 is the case that matters)
    refusal = sm.validate_status_document(_load("status_v1_wrong_schema.json"))
    assert refusal == sm.Refusal("wrong_schema", "schemaVersion=1")
    assert sm.validate_status_document({"producer": "x"}) == sm.Refusal("wrong_schema", "schemaVersion=None")
    assert sm.validate_status_document({"schemaVersion": "2"}) == sm.Refusal("wrong_schema", "schemaVersion='2'")
    assert sm.validate_status_document({"schemaVersion": True}) is not None
    # a wrong schema is reported before a secret is looked for
    assert sm.validate_status_document({"schemaVersion": 1, "k": HEX64}).code == "wrong_schema"


def test_validate_refuses_any_hex64():
    # spec §7: in a valid document NO 64-hex value survives -- even under an otherwise-allowed field name
    refusal = sm.validate_status_document(_load("status_v2_with_secret.json"))
    assert refusal == sm.Refusal("with_secret", "canary: hex64 at seat.deviceKeyPublic")
    doc = _minimal_v2()
    doc["tasks"] = {"rows": [{"hash12": HEX64}]}
    assert sm.validate_status_document(doc) == sm.Refusal("with_secret", "canary: hex64 at tasks.rows[0].hash12")
    doc = _minimal_v2()
    doc["submissionHash"] = HEX64
    assert sm.validate_status_document(doc) == sm.Refusal("with_secret", "canary: hex64 at submissionHash")
    doc = _minimal_v2()
    doc["seat"]["deviceKey"] = HEX64
    assert sm.validate_status_document(doc).code == "with_secret"


def test_validate_refuses_secret_key_names_sk_and_jwt():
    doc = _minimal_v2()
    doc["seat"]["devicePrivateKey"] = None
    assert sm.validate_status_document(doc) == sm.Refusal("with_secret", "canary: key_name at seat.devicePrivateKey")
    doc = _minimal_v2()
    doc["daemon"] = {"pausedHint": {"reason": "Incorrect API key provided: sk-svcac********"}}
    assert sm.validate_status_document(doc) == sm.Refusal("with_secret", "canary: sk at daemon.pausedHint.reason")
    doc = _minimal_v2()
    doc["auth"] = {"reasons": ["token eyJhbGciOiJIUzI1NiJ9"]}
    assert sm.validate_status_document(doc) == sm.Refusal("with_secret", "canary: jwt at auth.reasons[0]")


def test_validate_refuses_over_2mib():
    # spec §7: > 2 MiB -> refused; exactly 2 MiB passes
    doc = _minimal_v2()
    assert sm.validate_status_document(doc, raw_bytes=sm.MAX_DOCUMENT_BYTES + 1) == sm.Refusal(
        "too_large", "2,097,153 B > 2 MiB"
    )
    assert sm.validate_status_document(doc, raw_bytes=sm.MAX_DOCUMENT_BYTES) is None
    big = _minimal_v2()
    big["seat"]["eligibility"] = "e" * (sm.MAX_DOCUMENT_BYTES + 10)
    refusal = sm.validate_status_document(big)
    assert refusal is not None and refusal.code == "too_large" and refusal.detail.endswith(" B > 2 MiB")
    # size is checked before the schema: an oversize v1 document is too_large, not wrong_schema
    assert sm.validate_status_document({"schemaVersion": 1}, raw_bytes=sm.MAX_DOCUMENT_BYTES + 1).code == "too_large"


# ---------------------------------------------------------------------------
# Task 1.8 — SEAT_KEYS, SEAT_ROW_KEYS, SEAT_BLOCK_KEYS, SEAT_FIELD_SOURCES, SEAT_WIDGET_SIGNATURES
# ---------------------------------------------------------------------------


def test_seat_keys_are_unique_and_prefixed():
    assert len(sm.SEAT_KEYS) == len(set(sm.SEAT_KEYS))
    status_bar = {"last_updated_seconds_ago", "error_count", "poll_interval"}
    assert status_bar <= set(sm.SEAT_KEYS)
    assert all(key.startswith("seat_") for key in sm.SEAT_KEYS if key not in status_bar)
    assert sm.SEAT_KEYS[-3:] == ("last_updated_seconds_ago", "error_count", "poll_interval")


def test_every_widget_signature_key_is_a_seat_key():
    # contract C.4: every name in every signature is in SEAT_KEYS (the PANELS adapters are keys(*signature))
    assert set(sm.SEAT_WIDGET_SIGNATURES) == {
        "SeatHero", "SeatNow", "SeatLedgerTable", "SeatLog", "SeatConfig", "SeatCost", "SeatMachine",
    }
    keys = set(sm.SEAT_KEYS)
    for widget, signature in sm.SEAT_WIDGET_SIGNATURES.items():
        assert len(signature) == len(set(signature)), f"{widget} repeats a key"
        missing = [name for name in signature if name not in keys]
        assert not missing, f"{widget} names keys outside SEAT_KEYS: {missing}"


def test_every_row_and_block_key_is_a_seat_key():
    keys = set(sm.SEAT_KEYS)
    assert set(sm.SEAT_ROW_KEYS) <= keys
    assert set(sm.SEAT_BLOCK_KEYS) <= keys
    assert set(sm.SEAT_ROW_FIELD_SOURCES) <= set(sm.SEAT_ROW_KEYS)
    for list_key, fields in sm.SEAT_ROW_FIELD_SOURCES.items():
        assert set(fields) <= set(sm.SEAT_ROW_KEYS[list_key])
        assert set(fields.values()) <= set(sm.SOURCE_NAMES)
    for name, columns in sm.SEAT_ROW_KEYS.items():
        assert len(columns) == len(set(columns)), name


def test_field_sources_cover_every_seat_key_exactly():
    # spec §7: sources are mapped per field -- every key has a decision, none is invented
    assert set(sm.SEAT_FIELD_SOURCES) == set(sm.SEAT_KEYS)
    assert set(sm.SEAT_FIELD_SOURCES.values()) <= set(sm.SOURCE_NAMES) | {None}
    assert sm.SEAT_FIELD_SOURCES["seat_unit_memory_current_b"] == "unit"
    assert sm.SEAT_FIELD_SOURCES["seat_daemon_state"] == "tail"
    assert sm.SEAT_FIELD_SOURCES["seat_standing_attempts"] == "seatWork"      # lifetime counters: /seats/<id>?work=
    assert sm.SEAT_FIELD_SOURCES["seat_standing_running"] == "standing"
    # spec §7: tokenId C(status) -> K, agentId A(enrollment.agentId) -> K -- the fallback lives in the value, never gated
    assert sm.SEAT_FIELD_SOURCES["seat_agent_id"] is None and sm.SEAT_FIELD_SOURCES["seat_token_id"] is None
    assert sm.SEAT_FIELD_SOURCES["seat_control_gate"] == "broker"
    assert sm.SEAT_FIELD_SOURCES["poll_interval"] is None
