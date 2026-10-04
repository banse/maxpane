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
        "unit", "current", "currentJobs", "jobs", "records", "nodes", "queue", "tasks", "today", "cost", "quota", "standing", "plane", "machine", "control",
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
        "maxpane_dashboard.analytics.seat_redact",
        "maxpane_dashboard.analytics.seat_signals",
        "maxpane_dashboard.analytics.seat_text",
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
        "SeatJob", "SeatOutputTokens", "SeatSkills", "SeatRecords", "SeatNodes", "SeatGate", "SeatAudit", "SeatControl",
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


# ---------------------------------------------------------------------------
# Task 1.9 — fold_status_document on the healthy fixture
# ---------------------------------------------------------------------------


def test_healthy_fixture_validates_and_folds_to_exactly_seat_keys():
    doc = _load("status_v2_healthy.json")
    assert sm.validate_status_document(doc) is None
    flat = sm.fold_status_document(doc)
    assert tuple(flat) == sm.SEAT_KEYS


def test_fold_maps_the_blocks_to_their_keys():
    flat = sm.fold_status_document(_load("status_v2_healthy.json"))
    assert flat["seat_schema_version"] == 2 and flat["seat_producer"] == "pepepane 0.1.0"
    assert flat["seat_host_kind"] == "systemd" and flat["seat_hostname"] == "ubuntu" and flat["seat_host_container"] is None
    assert flat["seat_offline"] is False
    assert flat["seat_token_id"] == 7 and flat["seat_agent_id"] == 51075
    assert flat["seat_device_key_public"] == "72b617d4" and flat["seat_wallet"] == "0x887b9f"
    assert flat["seat_eligibility"] == "eligible — this machine can receive work"
    assert flat["seat_capacity"] == 1 and flat["seat_offers"] == ["code", "fuzz", "research"]
    assert flat["seat_runtime_id"] == "codex" and flat["seat_runtime_version"] == "codex-cli 0.157.0"
    assert flat["seat_skills_offered"] == 31 and flat["seat_skills_rows"][1] == {"id": "public-rpcs", "on": True, "needs": "network"}
    assert flat["seat_inference"]["premium"] == {"codex": {"model": "gpt-6-astra", "effort": "xhigh"}}
    assert flat["seat_daemon_state"] == "alive" and flat["seat_daemon_idle_beats"] == 9 and flat["seat_daemon_running"] == 0
    assert flat["seat_daemon_fleet_online"] == 406 and flat["seat_daemon_paused_hint"] is None
    assert flat["seat_auth_degraded"] is False and flat["seat_auth_credential_file_mtime_utc"] == "2026-09-25T23:38:43Z"
    assert flat["seat_unit_memory_current_b"] == 115798016 and flat["seat_unit_boot_enabled"] is False
    assert flat["seat_unit_graceful_stop_possible"] is True
    assert flat["seat_current"] is None
    assert flat["seat_queue"] == {"ready": 27, "eligible": 0, "fleetOnline": 396,
                                  "blocked": [{"reason": "at capacity", "nodes": 27}], "asOfUtc": "2026-09-26T03:40:09Z"}
    assert flat["seat_tasks_window"]["source"] == "journald" and flat["seat_tasks_window"]["rows"] == 2
    assert flat["seat_today_tasks"] == 12 and flat["seat_today_accepted"] == 9 and flat["seat_today_divergence"]["ok"] is True
    assert flat["seat_cost_tokens"] == {"input": 2100000, "output": 96000, "cached": 24000000, "cacheWrite": 0}
    assert flat["seat_cost_buckets"][0]["ttftP50Ms"] == 2481 and flat["seat_quota"]["usedPercent"] == 45.0
    assert flat["seat_standing_attempts"] == 288 and flat["seat_standing_accepted"] == 244
    assert flat["seat_standing_counters_inconsistent"] is False and flat["seat_standing_running"] == []
    assert flat["seat_standing_recent_failures"][0]["reason"] == "runtime_error"
    assert flat["seat_plane_awaiting_verdict"] == 7 and flat["seat_plane_connected_daemons"] == 409
    assert flat["seat_machine_work_dirs"] == 288 and flat["seat_machine_outbox_files"] == 0 and flat["seat_machine_orphans"] == []
    assert flat["seat_machine_journal"]["capNote"].startswith("~347 MiB")
    assert flat["seat_control_broker_reachable"] is True and flat["seat_control_gate"]["safe"] is True
    assert flat["seat_control_gate"]["planeMode"] == "plane+local" and flat["seat_control_drain"] is None
    assert flat["seat_control_last_audit"][0]["planId"] == "7f3a9c1e2b4d6081"


def test_fold_normalises_rows_and_blocks_to_their_key_lists():
    flat = sm.fold_status_document(_load("status_v2_healthy.json"))
    for list_key in ("seat_tasks_rows", "seat_skills_rows", "seat_cost_buckets", "seat_standing_recent_failures",
                     "seat_control_last_audit"):
        assert flat[list_key], list_key
        for row in flat[list_key]:
            assert tuple(row) == sm.SEAT_ROW_KEYS[list_key], list_key
    for block_key in ("seat_queue", "seat_control_gate", "seat_quota"):
        assert tuple(flat[block_key]) == sm.SEAT_BLOCK_KEYS[block_key], block_key
    assert flat["seat_tasks_rows"][0]["hash12"] == "c4d9714ffb95" and flat["seat_tasks_rows"][0]["outcome"] == "accepted"
    assert flat["seat_tasks_rows"][1]["failureReason"] == "runtime_error"
    assert flat["seat_last_task"] == {"nodeId8": "0c1f9727", "storedUtc": "2026-09-26T03:24:17.236Z",
                                      "hash12": "c4d9714ffb95", "outcome": "accepted", "verdictLagS": 900,
                                      "acceptedUtc": "2026-09-26T03:23:44.909Z"}
    # a sparse row gains every column as None
    doc = _load("status_v2_healthy.json")
    doc["tasks"]["rows"] = [{"nodeId8": "deadbeef"}, "not a row"]
    rows = sm.fold_status_document(doc)["seat_tasks_rows"]
    assert len(rows) == 1 and rows[0]["nodeId8"] == "deadbeef" and rows[0]["hash12"] is None


def test_fold_truncates_identifiers_and_redacts_every_string():
    # spec §13: device key / wallet to 8 chars at fold time; every third-party string through redact() (step 0 first)
    doc = _load("status_v2_healthy.json")
    doc["seat"]["deviceKeyPublic"] = HEX64
    doc["seat"]["wallet"] = "0x887b9f1234567890abcdef"
    doc["seat"]["eligibility"] = "eligible \x1b]0;evil\x07 sk-svcac********"
    doc["daemon"]["pausedHint"] = {"until": "23:53", "failedRuns": 3, "reason": "401: sk-svcac******** \u202e"}
    doc["tasks"]["rows"][0]["objective"] = "ghp_" + "A" * 36
    doc["standing"]["recentFailures"][0]["reason"] = "Bearer abcdefgh12345678"
    flat = sm.fold_status_document(doc)
    assert flat["seat_device_key_public"] == "01234567" and flat["seat_wallet"] == "0x887b9f"
    assert flat["seat_eligibility"] == "eligible \u241b]0;evil sk-[redacted]"
    assert flat["seat_daemon_paused_hint"] == {"until": "23:53", "failedRuns": 3, "reason": "401: sk-[redacted] "}
    assert flat["seat_tasks_rows"][0]["objective"] == "[github-token]"
    assert flat["seat_standing_recent_failures"][0]["reason"] == "Bearer [redacted]"
    assert "svcac" not in json.dumps(flat)


def test_fold_emits_only_log_lines_newer_than_the_seq_the_widget_saw():
    # contract C.4: seat_log_lines = lines with seq > log_seq; seat_log_seq = the newest emitted
    lines = [
        {"seq": 1, "ts": "2026-09-26T03:40:01.000Z", "kind": "heartbeat", "text": "\u2026", "invocation": "5e0c", "cursor": "s=1"},
        {"seq": 2, "ts": "2026-09-26T03:40:05.000Z", "kind": "phase", "text": "  working: sk-abcd \x07", "invocation": "5e0c", "cursor": "s=2"},
        {"seq": 3, "ts": "2026-09-26T03:40:09.000Z", "kind": "submitted", "text": "submitted implement for 0c1f9727", "invocation": "5e0c"},
    ]
    doc = _load("status_v2_healthy.json")
    flat = sm.fold_status_document(doc, log_lines=lines, log_seq=1)
    assert [line["seq"] for line in flat["seat_log_lines"]] == [2, 3]
    assert flat["seat_log_lines"][0]["text"] == "  working: sk-[redacted] "
    assert tuple(flat["seat_log_lines"][1]) == sm.SEAT_ROW_KEYS["seat_log_lines"] and flat["seat_log_lines"][1]["cursor"] is None
    assert flat["seat_log_seq"] == 3
    empty = sm.fold_status_document(doc, log_lines=(), log_seq=7)
    assert empty["seat_log_lines"] == [] and empty["seat_log_seq"] == 7


def test_fold_is_deterministic_without_a_clock_and_ages_with_one():
    doc = _load("status_v2_healthy.json")
    assert sm.fold_status_document(doc) == sm.fold_status_document(doc)
    assert sm.fold_status_document(doc)["last_updated_seconds_ago"] == 0
    assert sm.fold_status_document(doc, now=1790394012.0 + 42)["last_updated_seconds_ago"] == 42
    assert sm.fold_status_document(doc, now=1790394012.0 - 5)["last_updated_seconds_ago"] == 0
    assert sm.fold_status_document({"schemaVersion": 2}, now=1.0)["last_updated_seconds_ago"] == 999


def test_fold_as_of_hhmm_names_every_source():
    flat = sm.fold_status_document(_load("status_v2_healthy.json"))
    assert tuple(flat["seat_as_of_hhmm"]) == sm.SOURCE_NAMES
    assert all(re.fullmatch(r"\d\d:\d\d", value) for value in flat["seat_as_of_hhmm"].values())
    assert flat["seat_as_of_hhmm"]["tail"] == sm.as_of_hhmm("2026-09-26T03:40:11Z")
    assert tuple(flat["seat_sources"]) == sm.SOURCE_NAMES
    assert tuple(flat["seat_sources"]["tail"]) == tuple(sm.empty_source())


def test_fold_status_bar_keys_are_numbers():
    doc = _load("status_v2_healthy.json")
    flat = sm.fold_status_document(doc)
    assert flat["error_count"] == 0 and flat["poll_interval"] == 5
    doc["pollInterval"] = 10
    assert sm.fold_status_document(doc)["poll_interval"] == 10
    doc["pollInterval"] = True
    assert sm.fold_status_document(doc)["poll_interval"] == 5


def test_fold_completes_the_wp7_keys():
    # contract C.14: WP7 completes seat_hero_state, seat_hero_reasons, seat_daemon_offline, seat_log_footer, seat_ledger_footer
    flat = sm.fold_status_document(_load("status_v2_healthy.json"))
    assert flat["seat_hero_state"] == "green" and flat["seat_hero_reasons"] == []
    assert flat["seat_daemon_offline"] is False
    assert flat["seat_log_footer"] == "tail: journalctl -f · cursor age 4 s · grammar 5bfa8261 ✓"
    assert flat["seat_ledger_footer"].startswith("journald ") and flat["seat_ledger_footer"].endswith("· stored today 11 = plane 11 ✓")
    dead = sm.fold_status_document(_load("status_v2_tail_dead.json"))
    assert dead["seat_hero_state"] == "red" and dead["seat_hero_reasons"][0] == "tail dead 52 s"
    assert dead["seat_daemon_offline"] is None, "no heartbeat facts survive a dead tail"
    assert dead["seat_log_footer"].endswith("· tail: exited rc=1 — retry in 8s")
    assert dead["seat_ledger_footer"] == "ledger unavailable"
    offline = sm.fold_status_document(_load("status_v2_offline.json"))
    assert offline["seat_hero_state"] == "green" and "plane" not in offline["seat_ledger_footer"]
    sparse = sm.fold_status_document({"schemaVersion": 2})
    assert sparse["seat_hero_state"] is None and sparse["seat_daemon_offline"] is None
    assert sparse["seat_log_footer"] == "tail: — · cursor age — · grammar 5bfa8261 (daemon version unknown)"
    assert sparse["seat_ledger_footer"] == "ledger unavailable"
    # spec §6 rule 4 / mutation proof 8: the hero reads source-gated values. A live standing (presenceConnected true,
    # heartbeatAgeMs 4100) adds the plane clause to a stale local heartbeat; an `unavailable` standing adds nothing
    live_plane = _load("status_v2_healthy.json")
    live_plane["daemon"]["heartbeatAgeS"] = 183
    assert sm.fold_status_document(live_plane)["seat_hero_reasons"] == ["heartbeat 183 s old", "plane sees us · local tail stale"]
    stale_plane = _load("status_v2_api_down.json")
    stale_plane["daemon"]["heartbeatAgeS"] = 183
    stale = sm.fold_status_document(stale_plane)
    assert stale["seat_hero_state"] == "amber" and stale["seat_hero_reasons"] == ["heartbeat 183 s old"]
    stale_plane["standing"]["presenceConnected"] = False
    stale_plane["daemon"]["heartbeatAgeS"] = 300
    lost = sm.fold_status_document(stale_plane)
    assert lost["seat_hero_state"] == "amber" and lost["seat_daemon_offline"] is False, "a stale `connected: false` never reds the hero"


def test_fold_never_raises_on_a_sparse_or_empty_document():
    for doc in ({"schemaVersion": 2}, {}, sm.empty_document(started_at_utc="2026-09-26T03:40:07Z", host=HOST)):
        flat = sm.fold_status_document(doc)
        assert tuple(flat) == sm.SEAT_KEYS
        for key, value in flat.items():
            if isinstance(value, (dict, list)) or key in ("seat_offline", "seat_log_seq", "last_updated_seconds_ago",
                                                          "error_count", "poll_interval", "seat_log_footer",
                                                          "seat_ledger_footer", "seat_schema_version", "seat_producer",
                                                          "seat_started_at_utc", "seat_host_kind", "seat_host_unit",
                                                          "seat_host_runtime", "seat_hostname"):
                continue
            assert value is None, f"{key} folded to {value!r} from a sparse document"
    assert sm.fold_status_document("not a dict")["seat_daemon_state"] is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Task 1.9 (continued) — per-field source gating (mutation proof 8)
# ---------------------------------------------------------------------------


def test_not_ok_source_yields_none_even_with_values():
    # spec §14 mutation proof 8: values from a not-ok source fold to None -- per field (stats ok while inspect failed)
    doc = _load("status_v2_healthy.json")
    doc["sources"]["unit"].update({"ok": False, "reason": "inspect timed out 25 s", "failures": 1, "unavailable": True})
    assert doc["unit"]["memoryCurrentB"] == 115798016, "the document still carries the stale value"
    flat = sm.fold_status_document(doc)
    assert flat["seat_unit_memory_current_b"] is None
    assert flat["seat_unit_active_state"] is None
    assert flat["seat_machine_load1"] is None
    # ...while every field fed by a source that IS ok keeps its value
    assert flat["seat_daemon_state"] == "alive"
    assert flat["seat_machine_work_dirs"] == 288
    assert flat["seat_standing_attempts"] == 288
    assert flat["seat_sources"]["unit"]["reason"] == "inspect timed out 25 s"
    assert flat["error_count"] == 1
    # tokenId C(status) -> K (spec §7): a failed `imd status` gates the eligibility, never the saved token id
    doc = _load("status_v2_healthy.json")
    doc["sources"]["status"].update({"ok": False, "reason": "socket timeout 20 s"})
    flat = sm.fold_status_document(doc)
    assert flat["seat_eligibility"] is None and flat["seat_token_id"] == 7  # spec §8 `IDMD #7 (saved)`


def test_last_good_api_sources_keep_values_until_unavailable():
    # spec §6 rule 4 / contract C.4: an API source on ok:false keeps its last-good values until `unavailable`
    doc = _load("status_v2_healthy.json")
    doc["sources"]["standing"].update({"ok": False, "reason": "HTTP 500", "failures": 1, "unavailable": False})
    kept = sm.fold_status_document(doc)
    assert kept["seat_standing_working"] == 0 and kept["seat_queue"]["ready"] == 27 and kept["seat_agent_id"] == 51075
    doc["sources"]["standing"].update({"failures": 3, "unavailable": True})
    gone = sm.fold_status_document(doc)
    assert gone["seat_standing_working"] is None and gone["seat_queue"] is None
    assert gone["seat_agent_id"] == 51075, "the agent id carries its own A -> K fallback and is never gated"  # spec §7
    assert gone["seat_standing_attempts"] == 288, "the lifetime counters come from seatWork, which is still ok"
    # a local source never keeps last-good: ok:false gates at once
    doc = _load("status_v2_healthy.json")
    doc["sources"]["skills"].update({"ok": False, "reason": "imd skills format changed", "unavailable": False})
    assert sm.fold_status_document(doc)["seat_skills_rows"] is None


def test_persisted_row_fields_keep_their_own_facts_during_api_outage():
    # Round 9 §8.1 supersedes base API gating for persisted ledger facts.
    doc = _load("status_v2_healthy.json")
    doc["sources"]["seatWork"].update({"ok": False, "failures": 3, "unavailable": True})
    flat = sm.fold_status_document(doc)
    row = flat["seat_tasks_rows"][0]
    assert row["outcome"] == doc["tasks"]["rows"][0]["outcome"]
    assert row["verdictLagS"] == doc["tasks"]["rows"][0]["verdictLagS"]
    assert row["acceptedAtApi"] == doc["tasks"]["rows"][0]["acceptedAtApi"]
    assert row["nodeId8"] == "0c1f9727" and row["hash12"] == "c4d9714ffb95", "local facts are untouched"
    assert flat["seat_tasks_rows"][1]["failureReason"] == "runtime_error", "reasons is still ok"
    assert flat["seat_last_task"]["outcome"] == doc["tasks"]["rows"][0]["outcome"]
    assert flat["seat_today_accepted"] == doc["today"]["accepted"] and flat["seat_today_tasks"] == 12
    doc["sources"]["reasons"].update({"ok": False, "failures": 3, "unavailable": True})
    assert sm.fold_status_document(doc)["seat_tasks_rows"][1]["failureReason"] == "runtime_error"


# ---------------------------------------------------------------------------
# Task 1.10 — the five degraded status_v2_* fixtures
# ---------------------------------------------------------------------------


def test_offline_fixture_has_no_api_sources_and_flags_offline():
    # spec §7: under --offline the API sources are absent entirely; §8 VERDICTS reads `local only`
    doc = _load("status_v2_offline.json")
    assert not any(name in doc["sources"] for name in ("standing", "seatWork", "reasons", "plane"))
    flat = sm.fold_status_document(doc)
    assert flat["seat_offline"] is True
    assert flat["seat_queue"] is None and flat["seat_standing_attempts"] is None and flat["seat_plane_version"] is None
    assert flat["seat_tasks_rows"][0]["outcome"] == "unknown"
    assert flat["seat_agent_id"] == 51075, "a configured agent id survives --offline (K)"
    assert flat["seat_control_gate"]["planeMode"] == "local-only"
    assert set(flat["seat_sources"]) == set(sm.SOURCE_NAMES) - {"standing", "seatWork", "reasons", "plane"}
    assert flat["seat_as_of_hhmm"]["standing"] is None


def test_tail_dead_fixture_blanks_every_tail_fed_key():
    flat = sm.fold_status_document(_load("status_v2_tail_dead.json"))
    for key, source in sm.SEAT_FIELD_SOURCES.items():
        if source == "tail":
            assert flat[key] is None, key
    assert flat["seat_sources"]["tail"]["reason"] == "tail: exited rc=1 — retry in 8s"
    assert flat["seat_unit_active_state"] == "active" and flat["seat_standing_attempts"] == 288
    assert flat["seat_log_seq"] == 0 and flat["error_count"] == 1


def test_api_down_fixture_blanks_the_api_fed_keys_only():
    flat = sm.fold_status_document(_load("status_v2_api_down.json"))
    for key, source in sm.SEAT_FIELD_SOURCES.items():
        if source in ("standing", "seatWork", "reasons", "plane"):
            assert flat[key] is None, key
    assert flat["seat_offline"] is False, "api down is not --offline"
    assert flat["seat_daemon_state"] == "alive" and flat["seat_today_tasks"] == 12
    assert flat["seat_sources"]["plane"]["reason"].startswith("HTTP 500")
    assert flat["error_count"] == 4


def test_local_only_and_gate_unknown_fixtures_keep_the_gate_block():
    local_only = sm.fold_status_document(_load("status_v2_local_only_gate.json"))
    assert local_only["seat_control_gate"]["planeMode"] == "local-only" and local_only["seat_control_gate"]["safe"] is True
    assert local_only["seat_standing_working"] == 0, "standing is ok:false but not yet unavailable -- last-good kept"
    unknown = sm.fold_status_document(_load("status_v2_gate_unknown.json"))
    assert unknown["seat_control_gate"]["safe"] is False
    assert unknown["seat_control_gate"]["reason"] == "gate unknown: outbox unreadable"
    assert unknown["seat_control_gate"]["outboxFiles"] is None
    assert unknown["seat_machine_outbox_files"] is None and unknown["seat_machine_work_dirs"] is None


@pytest.mark.parametrize("name", STATUS_FIXTURES)
def test_every_status_v2_fixture_validates_and_folds(name):
    doc = _load(name)
    assert sm.validate_status_document(doc) is None, name
    flat = sm.fold_status_document(doc)
    assert tuple(flat) == sm.SEAT_KEYS
    assert "$" not in json.dumps(flat), "no currency anywhere (spec §10)"

# Round 9 contract. Breaks caught: loss of parallel jobs, full RECORDS replies,
# nested API object copying, missing new widget inputs, and oversize output.
def _round9_document():
    doc = _load("status_v2_healthy.json")
    doc["currentJobs"] = [
        {"jobId": "job-old", "startedUtc": "2026-10-03T17:00:00Z", "objective": "short old"},
        {"jobId": "job-new", "startedUtc": "2026-10-03T17:02:00Z", "objective": "short new"},
        {"jobId": "job-mid", "startedUtc": "2026-10-03T17:01:00Z", "objective": "short mid"},
    ]
    doc["jobs"] = [
        {"key": "7/node-new/time", "jobId": "job-new", "objective": "full [question]\nsecond line",
         "reply": "full [reply]\nsecond line", "questionState": "read", "replyState": "read",
         "usage": {"model": "claude", "turns": 6, "tokens": {"output": 10250}},
         "delivery": {"url": "repo/path", "atUtc": "2026-10-03T17:03:00Z"}},
        {"key": "7/node-last/time", "jobId": "job-last", "reply": "last reply"},
    ]
    doc["records"] = {"rows": [{"key": "7/node-new/time", "jobId": "job-new", "nodeKey": "implement",
        "answerPreview": "one sentence.\nsecret second sentence", "reply": "FULL REPLY MUST STAY IN LEDGER",
        "jobState": "completed", "launch": {"requested": True, "kind": "repo"}}],
        "window": {"rows": 400, "asOfUtc": "2026-10-03T17:03:00Z"}}
    doc["nodes"] = {"allRows": [{"nodeKey": "implement", "attempts": 10, "accepted": 8,
                                  "paid": None, "launch": None}], "weekRows": [],
                    "coverage": {"attempts": 12, "covered": 10, "detailsRead": 0,
                                 "asOfUtc": "2026-10-03T17:03:00Z"}}
    doc["seat"].update(autoUpdate=True, runtimeWrapper="wrapper note")
    return doc


def test_round9_fold_keeps_three_running_jobs_newest_first_and_separate_full_text():
    flat = sm.fold_status_document(_round9_document())
    assert [r["jobId"] for r in flat["seat_current_jobs"]] == ["job-new", "job-mid", "job-old"]
    assert flat["seat_jobs"][0]["objective"] == "full [question]\nsecond line"
    assert flat["seat_jobs"][0]["reply"] == "full [reply]\nsecond line"
    assert flat["seat_records_rows"][0]["answerPreview"] == "one sentence."
    assert "reply" not in flat["seat_records_rows"][0]
    assert flat["seat_nodes_all_rows"][0]["accepted"] == 8
    assert flat["seat_nodes_coverage"]["covered"] == 10
    assert flat["seat_auto_update"] is True and flat["seat_runtime_wrapper"] == "wrapper note"


def test_round9_nested_api_objects_are_shaped_field_by_field():
    doc = _round9_document()
    job = doc["jobs"][0]
    job["secret"] = "must disappear"
    job["usage"]["secret"] = "must disappear"
    job["usage"]["tokens"]["privateKey"] = "must disappear"
    job["delivery"]["auth.json"] = "must disappear"
    job["structuralCheck"] = {"status": "passed", "detail": "paths verified", "secret": "must disappear"}
    job["panel"] = {"state": "agreed", "agreed": 3, "secret": "must disappear"}
    doc["records"]["rows"][0]["launch"]["secret"] = "must disappear"
    # A malicious object in a normally scalar slot must not slip through either.
    doc["records"]["rows"][0]["model"] = {"secret": "must disappear"}
    shaped = sm.shape_dashboard_document(doc)
    assert sm.validate_status_document(shaped) is None
    assert shaped["jobs"][0]["usage"]["tokens"]["output"] == 10250
    assert shaped["jobs"][0]["structuralCheck"] == {"status": "passed", "evaluation": None, "detail": "paths verified"}
    assert shaped["records"]["rows"][0]["model"] is None
    assert "must disappear" not in json.dumps(shaped)
    flat = sm.fold_status_document(doc)
    assert "must disappear" not in json.dumps({k: flat[k] for k in (
        "seat_jobs", "seat_records_rows", "seat_nodes_all_rows", "seat_nodes_coverage")} )


def test_round9_written_document_is_valid_and_text_caps_do_not_expand_records():
    doc = _round9_document()
    doc["jobs"][0].update(objective="Q" * 100000, reply="R" * 100000,
                            structuralCheck={"status": "passed", "detail": "Z" * 100000})
    doc["records"]["rows"][0]["answerPreview"] = "Z" * 100000
    shaped = sm.shape_dashboard_document(doc)
    assert sm.validate_status_document(shaped) is None
    assert len(shaped["jobs"][0]["objective"]) == 4096
    assert shaped["jobs"][0]["objective"].endswith("…")
    assert len(shaped["jobs"][0]["structuralCheck"]["detail"]) == 512
    assert len(shaped["records"]["rows"][0]["answerPreview"]) == 160
    assert "reply" not in shaped["records"]["rows"][0]


def test_round9_old_document_still_folds_without_new_blocks():
    flat = sm.fold_status_document(_load("status_v2_healthy.json"))
    assert flat["seat_current_jobs"] == [] and flat["seat_jobs"] == []
    assert flat["seat_records_rows"] == [] and flat["seat_nodes_all_rows"] == []
    assert flat["seat_records_window"] is None and flat["seat_nodes_coverage"] is None
    assert flat["seat_token_id"] == 7 and flat["seat_tasks_rows"][0]["outcome"] == "accepted"


def test_round9_all_six_bodies_have_frozen_signatures():
    needs = {
        "SeatHero": {"seat_nodes_all_rows", "seat_nodes_coverage", "seat_control_restart_required", "seat_config_changed_since_start"},
        "SeatJob": {"seat_current_jobs", "seat_jobs", "seat_sources", "seat_offline"},
        "SeatOutputTokens": {"seat_cost_series", "seat_cost_tokens", "seat_sources"},
        "SeatSkills": {"seat_skills_rows", "seat_skills_needs_network", "seat_control_restart_required"},
        "SeatRecords": {"seat_records_rows", "seat_records_window", "seat_offline"},
        "SeatNodes": {"seat_nodes_all_rows", "seat_nodes_week_rows", "seat_nodes_coverage"},
        "SeatGate": {"seat_control_gate", "seat_control_drain", "seat_sources"},
        "SeatAudit": {"seat_control_last_audit", "seat_control_in_flight"},
        "SeatControl": {"seat_control_gate", "seat_control_in_flight", "seat_unit_boot_enabled", "seat_control_plan", "seat_control_status", "seat_control_last_audit"},
        "SeatConfig": {"seat_token_id", "seat_wallet", "seat_device_key_public", "seat_auto_update", "seat_runtime_wrapper"},
    }
    for widget, keys in needs.items():
        assert keys <= set(sm.SEAT_WIDGET_SIGNATURES.get(widget, ())), widget


def test_round9_worst_document_under_2mib_mutation13():
    doc = _round9_document()
    # Literal worst supported round-9 fixture: three running jobs plus last,
    # 400 local tasks / record previews / node types, 50 skills, 20 audit rows.
    text = "😀" * 4096
    base_job = doc["jobs"][0]
    doc["jobs"] = [dict(base_job, jobId=job_id, objective=text, reply=text,
                        oracleQuestion=text, oracleAnswer=text, oracleNotes=text,
                        structuralCheck={"status": "passed", "detail": text})
                   for job_id in ("job-new", "job-mid", "job-old", "job-last")]
    doc["records"]["rows"] = [dict(doc["records"]["rows"][0], key=f"7/node/{i}", answerPreview=text,
                                  reply=text, oracleQuestion=text, oracleNotes=text) for i in range(400)]
    doc["tasks"]["rows"] = [dict(doc["tasks"]["rows"][0], key=f"7/node/{i}") for i in range(400)]
    doc["seat"]["skills"]["rows"] = [{"id": f"skill-{i}", "on": True, "needs": "network"} for i in range(50)]
    doc["nodes"]["allRows"] = [dict(doc["nodes"]["allRows"][0], nodeKey=f"node-{i}") for i in range(400)]
    doc["control"]["lastAudit"] = [{"seq": i, "verb": "restart", "phase": "verify"} for i in range(20)]
    doc['control'].update(status=text, statusParts=[{'text':text,'colour':'green'} for _ in range(32)],
                          plan={key:text for key in sm.SEAT_BLOCK_KEYS['seat_control_plan']})
    shaped = sm.shape_dashboard_document(doc)
    raw_bytes = len(json.dumps(shaped, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    assert raw_bytes < 2 * 1024 * 1024
    emitted_bytes = len(json.dumps(shaped, ensure_ascii=False, indent=2).encode("utf-8"))
    assert emitted_bytes < 2 * 1024 * 1024
    assert sm.validate_status_document(shaped, raw_bytes=emitted_bytes) is None
    assert sm.validate_status_document(shaped) is None
    assert len(shaped["records"]["rows"]) == 400
    assert len(shaped["jobs"]) == 4
    assert len(shaped["jobs"][0]["reply"]) == 4096


def test_round9_job_text_is_limited_to_running_attempts_and_one_last_job():
    doc = _round9_document()
    doc["jobs"] = [dict(doc["jobs"][0], key=f"attempt-{i}") for i in range(400)] + doc["jobs"][1:]
    shaped = sm.shape_dashboard_document(doc)
    assert len(shaped["jobs"]) <= 4
    assert shaped["jobs"][-1]["jobId"] == "job-last"


def test_round9_additive_config_cost_control_fields_reject_nested_hostile_values():
    doc = _round9_document()
    doc["seat"]["runtimeWrapper"] = {"secret": "must disappear"}
    doc["cost"]["outputTokens"] = {"today": 12, "secret": "must disappear"}
    doc["control"].update(plan={"planId": "abc123", "command": "imd restart", "secret": "must disappear"},
                          status="verifying", mode="verifying")
    shaped = sm.shape_dashboard_document(doc)
    assert sm.validate_status_document(shaped) is None
    assert shaped["seat"]["runtimeWrapper"] is None
    flat = sm.fold_status_document(shaped)
    assert flat["seat_output_tokens"]["today"] == 12
    assert flat["seat_control_plan"]["planId"] == "abc123"
    assert flat["seat_control_status"] == "verifying"


def test_round9_node_launch_counts_remain_numbers_while_job_record_launch_stays_object():
    doc = _round9_document()
    doc["nodes"]["allRows"] = [{"nodeKey": "implement", "launch": 2}, {"nodeKey": "unread", "launch": None}]
    doc["nodes"]["weekRows"] = [{"nodeKey": "implement", "launch": 1}, {"nodeKey": "unread", "launch": None}]
    doc["jobs"][0]["launch"] = {"kind": "repo", "requested": True, "workflowId": "workflow-1"}
    flat = sm.fold_status_document(doc)
    assert [row["launch"] for row in flat["seat_nodes_all_rows"]] == [2, None]
    assert [row["launch"] for row in flat["seat_nodes_week_rows"]] == [1, None]
    assert flat["seat_jobs"][0]["launch"] == {"kind": "repo", "requested": True, "workflowId": "workflow-1"}
    assert flat["seat_records_rows"][0]["launch"] == {"kind": "repo", "requested": True, "workflowId": None}
