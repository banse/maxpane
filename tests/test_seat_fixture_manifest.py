"""Every file under ``tests/fixtures/seat/`` is accounted for and clean (spec §14 "Fixtures"; contract §D).

``MANIFEST.json`` is one manifest for the whole tree: ``{"version": 1, "root":
"tests/fixtures/seat", "entries": {<relpath>: {origin, captured_at, sha256, bytes,
redactions, synthetic, daemon_version, notes[, allow]}}}``. WP0 commits it with an
empty ``entries``; every WP that adds a fixture adds the entry. Two guards:

* ``test_every_fixture_has_a_matching_manifest_entry`` -- sha256 and byte size match,
  no file without an entry, no entry without a file, every entry well-formed;
* ``test_no_fixture_contains_control_chars_or_sk`` -- no committed text carries a
  C0/C1/DEL control character, a bidi/format control, an ``sk-`` key, JWT, secret
  field name or unexpected long hex. Declared per-entry exceptions are: ``"control_chars"`` for a
  fixture that is ``synthetic: true`` (``grammar/control_chars.txt`` *is* the
  injection sample, spec §13 proof 23) and ``"sk"`` for the server-masked fragment
  (``sk-svcac********``) a heartbeat carried (contract §D notes) -- an unmasked key
  never passes, allowed or not. ``"synthetic_refusal"`` permits only exact sample
  values and paths in the designated canary fixtures; JWTs remain forbidden.
  Public hash/key fields, exact CLI device lines, Docker identity fields and the
  oversize transcript's exact filler have narrow context checks below.

The checkers are pure functions over a root and a manifest dict, so the two
``tmp_path`` tests below prove they can fail while the committed tree is still empty
(mutation: make ``_check_tree`` return ``[]`` -> both ``tmp_path`` tests redden).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from maxpane_dashboard.analytics.seat_redact import HEX64_RE, JWT_RE, SECRET_KEY_RE

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO / "tests" / "fixtures" / "seat"
MANIFEST = FIXTURE_ROOT / "MANIFEST.json"

#: Contract §C.3 (the redactor's step-0 and canary regexes, restated here because WP0 has no
#: dependency; ``tests/analytics/test_seat_redact.py`` asserts the redactor's copies equal these).
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
BIDI_FORMAT_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
SK_RE = re.compile(r"sk-[A-Za-z0-9*_-]{4,}")
#: A server-masked fragment: a short prefix then four or more ``*``. The only ``sk-`` shape a
#: fixture may keep, and only when its entry says ``"allow": ["sk"]``.
MASKED_SK_RE = re.compile(r"sk-[A-Za-z0-9_-]{0,12}\*{4,}")

REQUIRED_KEYS = frozenset({
    "origin", "captured_at", "sha256", "bytes", "redactions", "synthetic", "daemon_version", "notes",
})
OPTIONAL_KEYS = frozenset({"allow"})
REDACTIONS = frozenset({
    "control_chars", "sk", "jwt", "hex64>=32", "deviceKey", "recentFailures.summary",
    "submissions.summary", "prompts", "tool_io", "base_instructions", "credential_org",
})
ALLOW = frozenset({"control_chars", "sk", "synthetic_refusal"})
HEX_FIELDS = frozenset({"submissionHash", "hash", "txHash", "deviceKey"})
# Exact deliberate sample values and paths, never a whole-file secret exemption.
SYNTHETIC_PRIVATE = "9f8e7d6c5b4a39281706f5e4d3c2b1a0f9e8d7c6b5a4938271605f4e3d2c1b0a"
REFUSAL_VALUES = {
    "broker/projection_ok.json": {"devicePrivateKey": SYNTHETIC_PRIVATE},
    "broker/projection_leaky.json": {"devicePrivateKey": SYNTHETIC_PRIVATE},
    "broker/projection_extra_key.json": {"devicePrivateKey": SYNTHETIC_PRIVATE},
    "broker/projection_swapped_key.json": {"deviceKey": SYNTHETIC_PRIVATE},
    "broker/projection_nested_device_key.json": {
        "devicePrivateKey": SYNTHETIC_PRIVATE, "inference.deviceKey": "ab" * 32,
    },
    "status/status_v2_with_secret.json": {"seat.deviceKeyPublic": "0123456789abcdef" * 4},
}
CLI_DEVICE_FILES = frozenset({
    "cli/5bfa8261/imd_status_seat7.txt", "cli/5bfa8261/imd_status_seat420.txt",
    "cli/5bfa8261/imd_doctor.txt",
})
PLAIN_SECRET_NAME_RE = re.compile(r"privateKey|devicePrivateKey|mnemonic|secret", re.IGNORECASE)
CAPTURED_AT_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
#: Compressed fixtures (``sessions/rollout_task.jsonl.zst``) are pinned by sha256/bytes only;
#: their text is scanned by the summariser tests where ``compression.zstd`` imports.
BINARY_SUFFIXES = frozenset({".zst"})


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != "MANIFEST.json")


def _check_entry(relpath: str, entry: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(entry, dict):
        return [f"{relpath}: entry is not an object"]
    keys = set(entry)
    if missing := REQUIRED_KEYS - keys:
        problems.append(f"{relpath}: missing keys {sorted(missing)}")
    if extra := keys - REQUIRED_KEYS - OPTIONAL_KEYS:
        problems.append(f"{relpath}: unknown keys {sorted(extra)}")
    if not isinstance(entry.get("origin"), str) or not entry.get("origin"):
        problems.append(f"{relpath}: origin must be a non-empty string")
    if not isinstance(entry.get("captured_at"), str) or not CAPTURED_AT_RE.fullmatch(entry["captured_at"]):
        problems.append(f"{relpath}: captured_at must be YYYY-MM-DDTHH:MM:SSZ")
    if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
        problems.append(f"{relpath}: sha256 must be 64 lower-case hex")
    if not isinstance(entry.get("bytes"), int) or isinstance(entry.get("bytes"), bool) or entry["bytes"] < 0:
        problems.append(f"{relpath}: bytes must be a non-negative int")
    redactions = entry.get("redactions")
    if not isinstance(redactions, list) or not set(redactions) <= REDACTIONS:
        problems.append(f"{relpath}: redactions must be a list drawn from {sorted(REDACTIONS)}")
    if not isinstance(entry.get("synthetic"), bool):
        problems.append(f"{relpath}: synthetic must be a bool")
    if entry.get("daemon_version") is not None and not isinstance(entry["daemon_version"], str):
        problems.append(f"{relpath}: daemon_version must be a string or null")
    if not isinstance(entry.get("notes"), str):
        problems.append(f"{relpath}: notes must be a string")
    allow = entry.get("allow", [])
    if not isinstance(allow, list) or not set(allow) <= ALLOW:
        problems.append(f"{relpath}: allow must be a list drawn from {sorted(ALLOW)}")
    elif "control_chars" in allow and entry.get("synthetic") is not True:
        problems.append(f"{relpath}: only a synthetic fixture may carry control characters")
    if isinstance(allow, list) and "synthetic_refusal" in allow:
        if entry.get("synthetic") is not True or relpath not in REFUSAL_VALUES:
            problems.append(f"{relpath}: synthetic_refusal requires a designated synthetic refusal fixture")
    return problems


def _check_tree(root: Path, manifest: dict) -> list[str]:
    """Every problem in *root* against *manifest*: shape, dangling entries, unlisted files, digests."""
    problems: list[str] = []
    if manifest.get("version") != 1:
        problems.append("manifest version must be 1")
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        return problems + ["manifest entries must be an object"]
    on_disk = {p.relative_to(root).as_posix(): p for p in _files(root)}
    for relpath in sorted(set(entries) - set(on_disk)):
        problems.append(f"{relpath}: listed in MANIFEST.json but not on disk")
    for relpath in sorted(set(on_disk) - set(entries)):
        problems.append(f"{relpath}: on disk but not in MANIFEST.json")
    for relpath in sorted(set(entries) & set(on_disk)):
        entry = entries[relpath]
        problems += _check_entry(relpath, entry)
        if isinstance(entry, dict):
            data = on_disk[relpath].read_bytes()
            if entry.get("bytes") != len(data):
                problems.append(f"{relpath}: bytes {entry.get('bytes')} != {len(data)} on disk")
            if entry.get("sha256") != hashlib.sha256(data).hexdigest():
                problems.append(f"{relpath}: sha256 does not match the committed bytes")
    return problems


def _scan_content(root: Path, manifest: dict) -> list[str]:
    """Scan decoded JSON/JSONL and plain text, with narrowly scoped fixture exceptions."""
    problems: list[str] = []
    entries = manifest.get("entries", {}) if isinstance(manifest.get("entries"), dict) else {}
    for file in _files(root):
        relpath = file.relative_to(root).as_posix()
        if file.suffix in BINARY_SUFFIXES:
            continue
        try:
            text = file.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{relpath}: not UTF-8 (a text fixture) and not a known binary suffix")
            continue
        entry = entries.get(relpath) if isinstance(entries.get(relpath), dict) else {}
        allow = set(entry.get("allow", [])) if isinstance(entry.get("allow", []), list) else set()
        controls_ok = "control_chars" in allow and entry.get("synthetic") is True
        refusal_values = (REFUSAL_VALUES.get(relpath, {})
                          if "synthetic_refusal" in allow and entry.get("synthetic") is True else {})

        def problem(kind: str, path: str) -> None:
            problems.append(f"{relpath}: contains {kind} at {path or '<root>'}")

        # JSON decoding discards formatting whitespace; retain the raw-byte guard
        # as well as checking decoded strings for escaped controls.
        if not controls_ok and (CONTROL_RE.search(text) or BIDI_FORMAT_RE.search(text)):
            problem("a control or bidi/format character", "raw text")

        def scan_string(value: str, path: str, *, field: str | None = None,
                        hex_ok: bool = False, plain: bool = False) -> None:
            if not controls_ok and (CONTROL_RE.search(value) or BIDI_FORMAT_RE.search(value)):
                problem("a control or bidi/format character", path)
            for match in SK_RE.finditer(value):
                if "sk" not in allow or not MASKED_SK_RE.fullmatch(match.group(0)):
                    problem("an sk- key", path)
            if JWT_RE.search(value):
                problem("a JWT", path)
            if plain and PLAIN_SECRET_NAME_RE.search(value):
                problem("a secret key name", path)
            if field not in HEX_FIELDS and not hex_ok and HEX64_RE.search(value):
                problem("hex64", path)

        def walk(value: object, path: str = "", field: str | None = None) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else key
                    if SECRET_KEY_RE.search(key) and not (child_path in refusal_values and
                                                          refusal_values[child_path] == child):
                        problem("a secret key name", child_path)
                    scan_string(key, child_path + " (key)")
                    walk(child, child_path, key)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
            elif isinstance(value, str):
                hex_ok = refusal_values.get(path) == value
                if relpath == "cli/docker_inspect.json":
                    hex_ok |= (path == "[0].Id" and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                               or path == "[0].Image" and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None)
                if relpath == "sessions/rollout_oversize_line.jsonl" and path == "payload.item.text":
                    hex_ok |= value == "A" * (2 * 1024 * 1024)
                scan_string(value, path, field=field, hex_ok=hex_ok)

        def object_pairs(pairs: list[tuple[str, object]]) -> dict:
            value = {}
            for key, child in pairs:
                if key in value:
                    problem("a duplicate JSON key", key)
                value[key] = child
            return value

        try:
            walk(json.loads(text, object_pairs_hook=object_pairs, parse_int=str, parse_float=str))
        except json.JSONDecodeError:
            # Journald captures and transcripts may contain one JSON object per line.
            for index, line in enumerate(text.split("\n")):
                try:
                    walk(json.loads(line, object_pairs_hook=object_pairs, parse_int=str, parse_float=str))
                except json.JSONDecodeError:
                    hex_ok = (relpath in CLI_DEVICE_FILES and
                              re.fullmatch(r"device[ \t]+[0-9a-f]{64}", line) is not None)
                    if relpath == "cli/5bfa8261/imd_whoami.txt":
                        hex_ok = re.fullmatch(r"[0-9a-f]{64}", line) is not None
                    scan_string(line, f"line {index + 1}", hex_ok=hex_ok, plain=True)
    return problems


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# -- the committed tree -------------------------------------------------------


@pytest.mark.guard
def test_manifest_has_the_contract_shape():
    manifest = _manifest()
    assert manifest["version"] == 1
    assert manifest["root"] == "tests/fixtures/seat"
    assert isinstance(manifest["entries"], dict)
    assert set(manifest) == {"version", "root", "entries"}


@pytest.mark.guard
def test_every_fixture_has_a_matching_manifest_entry():
    """Spec §14 Fixtures / contract §D: sha256 and bytes match for every file; nothing unlisted."""
    assert _check_tree(FIXTURE_ROOT, _manifest()) == []


@pytest.mark.guard
def test_no_fixture_contains_control_chars_or_sk():
    """Spec §13 / §14: fixtures are committed only after redaction (control strip included)."""
    assert _scan_content(FIXTURE_ROOT, _manifest()) == []


# -- the checkers can fail (proved on tmp_path while the tree is empty) -------


def _entry(data: bytes, **overrides) -> dict:
    entry = {
        "origin": "synthetic, this test",
        "captured_at": "2026-09-26T08:00:00Z",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "redactions": ["control_chars", "sk"],
        "synthetic": True,
        "daemon_version": None,
        "notes": "",
    }
    entry.update(overrides)
    return entry


def test_the_tree_checker_catches_missing_entries_wrong_digests_and_wrong_sizes(tmp_path):
    good = b"heartbeat: idle\n"
    (tmp_path / "grammar").mkdir()
    (tmp_path / "grammar" / "good.txt").write_bytes(good)
    (tmp_path / "grammar" / "unlisted.txt").write_bytes(good)
    (tmp_path / "grammar" / "wrong_sha.txt").write_bytes(good)
    (tmp_path / "grammar" / "wrong_size.txt").write_bytes(good)
    manifest = {"version": 1, "root": "x", "entries": {
        "grammar/good.txt": _entry(good),
        "grammar/wrong_sha.txt": _entry(good, sha256="0" * 64),
        "grammar/wrong_size.txt": _entry(good, bytes=len(good) + 1),
        "grammar/dangling.txt": _entry(good),
        "grammar/bad_shape.txt": {"origin": "x"},
    }}
    problems = _check_tree(tmp_path, manifest)
    assert any(p.startswith("grammar/unlisted.txt: on disk but not") for p in problems)
    assert any(p.startswith("grammar/wrong_sha.txt: sha256 does not match") for p in problems)
    assert any(p.startswith("grammar/wrong_size.txt: bytes") for p in problems)
    assert any(p.startswith("grammar/dangling.txt: listed in MANIFEST.json but not on disk") for p in problems)
    assert any(p.startswith("grammar/bad_shape.txt: listed in MANIFEST.json but not on disk") for p in problems)
    assert not any(p.startswith("grammar/good.txt") for p in problems)
    # A clean pair passes: the checker is not simply always red.
    assert _check_tree(tmp_path, {"version": 1, "root": "x", "entries": {
        k: _entry(good) for k in ("grammar/good.txt", "grammar/unlisted.txt", "grammar/wrong_sha.txt", "grammar/wrong_size.txt")
    }}) == []


def test_the_entry_checker_refuses_bad_vocabulary_and_controls_in_a_captured_file():
    data = b"x"
    assert _check_entry("a", _entry(data, redactions=["ansi"])) != []
    assert _check_entry("a", _entry(data, allow=["all_secrets"])) != []
    assert _check_entry("a", _entry(data, allow=["synthetic_refusal"])) != []
    assert _check_entry("broker/projection_leaky.json", _entry(data, allow=["synthetic_refusal"], synthetic=False)) != []
    assert _check_entry("broker/projection_leaky.json", _entry(data, allow=["synthetic_refusal"])) == []
    assert _check_entry("a", _entry(data, captured_at="2026-09-26 08:00")) != []
    assert _check_entry("a", _entry(data, synthetic="yes")) != []
    assert _check_entry("a", _entry(data, extra="key")) != []
    # ``allow: control_chars`` is for hand-written samples only (spec §14: "synthetic, labelled").
    assert _check_entry("a", _entry(data, allow=["control_chars"], synthetic=False)) != []
    assert _check_entry("a", _entry(data, allow=["control_chars"], synthetic=True)) == []
    assert _check_entry("a", _entry(data)) == []


def test_the_content_scan_catches_controls_bidi_and_keys_and_honours_the_declared_exceptions(tmp_path):
    files = {
        "esc.txt": "working: \x1b]52;c;AAAA\x07 done\n",
        "bidi.txt": "working: \u202eevil\n",
        "key.txt": "auth failed for sk-abcd1234efgh\n",
        "masked_allowed.txt": "401 for sk-svcac******** (masked by the server)\n",
        "unmasked_allowed.txt": "401 for sk-svcac1234abcd\n",
        "controls_synthetic.txt": "working: \x1b]0;x\x07 \u202e\n",
        "controls_captured.txt": "working: \x1b]0;x\x07\n",
        "clean.txt": "heartbeat: idle · fleet 406 online\n",
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    entries = {name: _entry(text.encode("utf-8")) for name, text in files.items()}
    entries["masked_allowed.txt"]["allow"] = ["sk"]
    entries["unmasked_allowed.txt"]["allow"] = ["sk"]
    entries["controls_synthetic.txt"]["allow"] = ["control_chars"]
    entries["controls_captured.txt"].update(allow=["control_chars"], synthetic=False)
    problems = _scan_content(tmp_path, {"version": 1, "root": "x", "entries": entries})
    flagged = {p.split(":")[0] for p in problems}
    assert flagged == {"esc.txt", "bidi.txt", "key.txt", "unmasked_allowed.txt", "controls_captured.txt"}
    # The captured file with controls is also refused by the entry checker (belt and braces).
    assert _check_entry("controls_captured.txt", entries["controls_captured.txt"]) != []


@pytest.mark.parametrize("payload, category", [
    ({"unexpected": "ab" * 32}, "hex64"),
    ({"unexpected": "0x" + "AB" * 64}, "hex64"),
    ({"unexpected": "z" + "ab" * 32 + "z"}, "hex64"),
    ({"unexpected": "eyJ" + "a" * 12 + "." + "b" * 12}, "JWT"),
    ({"devicePrivateKey": "[removed]"}, "secret key name"),
    ({"devicePrivateKey": None}, "secret key name"),
    ({"nested": [{"Mnemonic": "[removed]"}]}, "secret key name"),
])
def test_content_scan_refuses_unlisted_secret_values_and_keys(tmp_path, payload, category):
    data = json.dumps(payload).encode()
    (tmp_path / "unlisted.json").write_bytes(data)
    assert any(category in p for p in _scan_content(tmp_path, {"entries": {}}))


@pytest.mark.parametrize("payload, category", [
    ({"deviceKey": "eyJ" + "a" * 12}, "JWT"),
    ({"hash": "eyJ" + "a" * 12}, "JWT"),
    ({"devicePrivateKey": "eyJ" + "a" * 12}, "JWT"),
    ({"devicePrivateKey": "cd" * 32}, "hex64"),
    ({"unexpected": "ab" * 32}, "hex64"),
    ({"nested": {"devicePrivateKey": "[removed]"}}, "secret key name"),
])
def test_refusal_allowance_does_not_hide_unrelated_or_new_secrets(tmp_path, payload, category):
    (tmp_path / "broker").mkdir()
    name = "broker/projection_leaky.json"
    data = json.dumps(payload).encode()
    (tmp_path / name).write_bytes(data)
    manifest = {"entries": {name: _entry(data, allow=["synthetic_refusal"])}}
    assert any(category in p for p in _scan_content(tmp_path, manifest))


def test_json_escapes_cannot_hide_jwt_or_secret_key_names(tmp_path):
    # Raw scanning cannot see these; the decoded JSON values/keys must also be checked.
    data = b'{"devicePrivate\\u004bey":"removed","note":"\\u0065yJaaaaaaaaaaaa"}'
    (tmp_path / "escaped.json").write_bytes(data)
    problems = _scan_content(tmp_path, {"entries": {}})
    assert any("secret key name" in p for p in problems)
    assert any("JWT" in p for p in problems)


def test_fixture_hex_exceptions_are_context_limited(tmp_path):
    files = {
        "public.json": {"hash": "ab" * 32, "submissionHash": "cd" * 32,
                        "txHash": "ef" * 32, "deviceKey": "01" * 32,
                        "wallet": "0x" + "a" * 40, "INVOCATION_ID": "b" * 32},
        "cli/docker_inspect.json": [{"Id": "a" * 64, "Image": "sha256:" + "b" * 64,
                                     "Config": {"Id": "c" * 64}}],
    }
    for name, payload in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    cli = tmp_path / "cli/5bfa8261/imd_status_seat7.txt"
    cli.parent.mkdir(parents=True)
    cli.write_text("device    " + "a" * 64 + "\nnote " + "b" * 64 + "\n")
    (tmp_path / "other.txt").write_text("device " + "a" * 64 + "\n")
    problems = _scan_content(tmp_path, {"entries": {}})
    assert len(problems) == 3
    assert any("cli/docker_inspect.json" in p and "Config.Id" in p for p in problems)
    assert any("imd_status_seat7.txt" in p and "hex64" in p for p in problems)
    assert any("other.txt" in p and "hex64" in p for p in problems)
    assert not any("public.json" in p for p in problems)


def test_duplicate_json_keys_cannot_hide_a_secret(tmp_path):
    data = '{"unexpected":"' + "ab" * 32 + '","unexpected":"safe"}'
    (tmp_path / "duplicate.json").write_text(data)
    assert _scan_content(tmp_path, {"entries": {}})


def test_plain_numeric_hex_is_not_lost_to_json_number_decoding(tmp_path):
    (tmp_path / "numeric.txt").write_text("1" * 64)
    assert any("hex64" in p for p in _scan_content(tmp_path, {"entries": {}}))


def test_json_whitespace_keeps_the_original_raw_control_guard(tmp_path):
    (tmp_path / "control.json").write_bytes(b'{"ok":\r1}')
    assert any("control" in p for p in _scan_content(tmp_path, {"entries": {}}))
