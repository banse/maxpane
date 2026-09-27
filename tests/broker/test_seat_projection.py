"""``imd_dashd/projection.py`` -- the only reader of config.json (spec §5.2 (i)-(iv), §13 canary; proofs 18, 29, unknown-key)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from imd_dashd import projection
from imd_dashd.projection import ALLOWLIST, CONFIG_KEYS, EXIT_REFUSED_PATH, EXIT_UNKNOWN_KEYS, project, tool_ids

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat" / "broker"
PUBLIC = "72b617d4a1c3e5f70918273645b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e"
PRIVATE = "9f8e7d6c5b4a39281706f5e4d3c2b1a0f9e8d7c6b5a4938271605f4e3d2c1b0a"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_key_tables_are_the_spec_lists():
    # spec §5.2: config.json keys are exactly these 8; the allowlist is these 7 (+ tool ids)
    assert CONFIG_KEYS == ("server", "deviceKey", "devicePrivateKey", "maxConcurrency", "wallet", "tokenId", "skillsOptOut", "inference")
    assert ALLOWLIST == ("server", "deviceKey", "wallet", "tokenId", "maxConcurrency", "skillsOptOut", "inference")
    assert "devicePrivateKey" not in ALLOWLIST


def test_project_emits_the_allowlist_and_tool_ids_only():
    out = project(_load("projection_ok.json"), {"tools": {"browser": {"command": "/usr/bin/x", "env": ["SECRET_TOKEN"]}}})
    assert set(out) == set(ALLOWLIST) | {"tools"}
    assert out["deviceKey"] == PUBLIC and out["tokenId"] == 7 and out["tools"] == ["browser"]
    assert PRIVATE not in json.dumps(out)
    assert "SECRET_TOKEN" not in json.dumps(out)                      # spec §5.2: ids only, never tools.env / commands
    assert project(_load("projection_ok.json"), None)["tools"] == []


def test_tool_ids_accepts_both_shapes_and_refuses_junk():
    assert tool_ids({"tools": [{"id": "b", "command": "/x"}, {"id": "a"}, {"command": "no-id"}]}) == ["a", "b"]
    assert tool_ids({"tools": {"z": {}, "y": {}}}) == ["y", "z"]
    assert tool_ids({"tools": "browser"}) == [] and tool_ids(None) == [] and tool_ids({}) == []


def test_projection_refuses_unknown_key():
    # spec §5.2 (ii) / §13 (5): exactly the 8 known keys, else fail closed (formats changed between builds)
    with pytest.raises(KeyError, match="unknown_keys"):
        project(_load("projection_extra_key.json"), None)                # 9 keys (agentId added)
    seven = {k: v for k, v in _load("projection_ok.json").items() if k != "inference"}
    with pytest.raises(KeyError, match="unknown_keys"):
        project(seven, None)                                              # 8 keys expected, 7 present
    renamed = dict(_load("projection_ok.json"))
    renamed["devicePublicKey"] = renamed.pop("deviceKey")
    with pytest.raises(KeyError, match="unknown_keys"):
        project(renamed, None)


def test_main_exit_codes_and_one_json_line(tmp_path, capsys):
    config = tmp_path / "config.json"
    shutil.copy(FIXTURES / "projection_ok.json", config)
    tools = tmp_path / "tools.json"
    tools.write_text(json.dumps({"tools": {"browser": {"command": "/usr/bin/x"}}}))
    assert projection.main(["--config", str(config), "--tools", str(tools)]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    payload = json.loads(out)
    assert set(payload) == set(ALLOWLIST) | {"tools", "configMtimeUtc"}
    assert payload["tools"] == ["browser"] and PRIVATE not in out
    # tools.json missing is fine (spec §5.3: `no tools configured`); config.json missing is not
    assert projection.main(["--config", str(config), "--tools", str(tmp_path / "none.json")]) == 0
    assert json.loads(capsys.readouterr().out)["tools"] == []
    assert projection.main(["--config", str(tmp_path / "missing.json"), "--tools", str(tools)]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "unreadable"}
    shutil.copy(FIXTURES / "projection_extra_key.json", config)
    assert projection.main(["--config", str(config), "--tools", str(tools)]) == EXIT_UNKNOWN_KEYS == 3
    assert json.loads(capsys.readouterr().out) == {"error": "unknown_keys"}


def test_main_never_opens_a_backup_copy(tmp_path, capsys):
    # spec §5.2 (iv): never reads config.json.bak-* (two operator backups exist on #7)
    backup = tmp_path / "config.json.bak-20260925"
    shutil.copy(FIXTURES / "projection_ok.json", backup)
    assert projection.main(["--config", str(backup), "--tools", str(tmp_path / "tools.json")]) == EXIT_REFUSED_PATH == 4
    assert json.loads(capsys.readouterr().out) == {"error": "refused_path"}
    assert projection.BACKUP_RE.search("/home/imd-worker/.identitymd/config.json") is None
    assert projection.BACKUP_RE.search("/home/imd-worker/.identitymd/config.json.bak-1") is not None
# ---------------------------------------------------------------- the canary the broker runs on the projection (spec §13)

import os  # noqa: E402

from imd_dashd import imd_dashd as broker_mod  # noqa: E402
from tests.broker._harness import PYTHON, audit_lines, call, make_broker, projection_child  # noqa: E402

PROJECTION_CHILD = (PYTHON, "-I", os.path.join(broker_mod.BROKER_DIR, "projection.py"))


def test_projection_canary_refuses_and_audits(tmp_path):
    # mutation proof 18: a projection that carries devicePrivateKey is refused (canary: key_name) and audited without the value
    broker, _runner, _journal, _clock, audit = make_broker(
        tmp_path, script={PROJECTION_CHILD: lambda argv, kw: projection_child(_load("projection_leaky.json"))})
    assert call(broker, "seat") == {"ok": False, "error": "projection_refused", "detail": {"canary": "key_name"}}
    last = audit_lines(audit)[-1]
    assert last["phase"] == "canary" and last["outcome"] == "canary: key_name" and last["verb"] == "seat"
    text = (tmp_path / "audit.jsonl").read_text()
    assert PRIVATE not in text and PUBLIC not in text
    # an sk- value anywhere in the payload is refused too
    payload = project(_load("projection_ok.json"), None)
    payload["server"] = "https://api.imd.fun?key=sk-svcac1234abcd"
    broker._run.script[PROJECTION_CHILD] = lambda argv, kw: projection_child(payload)
    assert call(broker, "seat")["detail"] == {"canary": "sk"}


def test_projection_canary_refuses_swapped_key(tmp_path):
    # mutation proof 29: public/private swapped -- same byte shape, so only the whoami match catches it
    broker, _runner, _journal, _clock, audit = make_broker(
        tmp_path, script={PROJECTION_CHILD: lambda argv, kw: projection_child(_load("projection_swapped_key.json"))})
    assert call(broker, "seat") == {"ok": False, "error": "projection_refused", "detail": {"canary": "devicekey_mismatch"}}
    assert audit_lines(audit)[-1]["outcome"] == "canary: devicekey_mismatch"
    assert PRIVATE not in (tmp_path / "audit.jsonl").read_text()
    # a second 64-hex value under any other key is refused as hex64 even when deviceKey matches
    payload = project(_load("projection_ok.json"), None)
    payload["wallet"] = PRIVATE
    broker._run.script[PROJECTION_CHILD] = lambda argv, kw: projection_child(payload)
    assert call(broker, "seat")["detail"] == {"canary": "hex64"}


def test_projection_unknown_keys_exit_3_is_a_canary_refusal(tmp_path):
    broker, _runner, _journal, _clock, audit = make_broker(
        tmp_path, script={PROJECTION_CHILD: lambda argv, kw: projection_child({"error": "unknown_keys"}, rc=3)})
    assert call(broker, "seat")["detail"] == {"canary": "unknown_keys"}
    assert audit_lines(audit)[-1]["outcome"] == "canary: unknown_keys"
