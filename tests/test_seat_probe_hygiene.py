"""Synthetic-only checks for report output that owners later commit."""
from __future__ import annotations

import io
import json
import re
import sys
import contextlib
import subprocess
from pathlib import Path

import pytest

from maxpane_dashboard.analytics.seat_redact import BIDI_FORMAT_RE, CONTROL_RE, G2_RULES, strip_controls
from tests import test_seat_fixture_manifest as fixture_guard

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "deploy/vps/probe_seat_host.sh"


def _check_probe_doc(text: str) -> list[str]:
    from imd_dashd.probe_hygiene import public_ip_matches
    problems = []
    # Decode escapes as JSON would (including surrogate pairs), without flagging
    # ordinary Unicode punctuation such as the lifecycle em dash.
    escape = re.compile(r"\\u[dD][89aAbB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}|\\x[0-9a-fA-F]{2}")
    for match in escape.finditer(text):
        value = match.group()
        if value.startswith(("\\x", "\\U")):
            decoded = chr(int(value[2:], 16))
        else:
            decoded = json.loads('"' + value + '"')
        if CONTROL_RE.search(decoded) or BIDI_FORMAT_RE.search(decoded):
            problems.append("escaped control or format character")
    def check_string(value, field=None):
        if public_ip_matches(value):
            problems.append("global IP")
        if field not in fixture_guard.HEX_FIELDS and re.search(r"[0-9a-fA-F]{32,}", value):
            problems.append("hex32")
        if any(pattern.search(strip_controls(value)) for pattern, _ in G2_RULES):
            problems.append("G2 credential")
    def walk(value, field=None):
        if isinstance(value, dict):
            for key, child in value.items():
                check_string(key)
                walk(child, key)
        elif isinstance(value, list):
            for child in value:
                walk(child, field)
        elif isinstance(value, str):
            check_string(value, field)
    for line in text.split("\n"):
        try:
            walk(json.loads(line, parse_int=str, parse_float=str))
        except (ValueError, TypeError):
            check_string(line)
    return problems


@pytest.mark.parametrize("text, expected", [
    ("IPAddressDeny=8.8.8.8/32 1.1.1.1/32 172.16.0.0/12 100.64.0.0/10 fc00::/7 fe80::/10", "IPAddressDeny=[public-ip]/32 [public-ip]/32 172.16.0.0/12 100.64.0.0/10 fc00::/7 fe80::/10"),
    ("ip=[2606:4700:4700::1111] net=2001:4860::/32", "ip=[[public-ip]] net=[public-ip]/32"),
    ("2026-09-28T10:20:30.000Z aa:bb:cc:dd:ee:ff 192.0.2.10/32 ::1 127.0.0.1", "2026-09-28T10:20:30.000Z aa:bb:cc:dd:ee:ff 192.0.2.10/32 ::1 127.0.0.1"),
])
def test_shared_ip_detector_masks_only_global_addresses(text, expected):
    from imd_dashd.probe_hygiene import redact_public_ips, public_ip_matches
    assert redact_public_ips(text) == expected
    assert bool(public_ip_matches(text)) == (text != expected)
    assert redact_public_ips(expected) == expected


@pytest.mark.parametrize("message, kind", [
    ("github_pat_" + "aZ_7" * 8, "G2"),
    ("x-api-key: syntheticvalue", "G2"),
    ("8.8.8.8", "global IP"),
    ("person@example.org", "email"),
    ("sk-" + "\u2060" + "ant-synthetic", "control"),
])
def test_fixture_guard_decodes_message_byte_arrays(tmp_path, message, kind):
    data = json.dumps({"MESSAGE": list(message.encode())}).encode()
    (tmp_path / "row.jsonl").write_bytes(data)
    manifest = {"entries": {"row.jsonl": fixture_guard._entry(data)}}
    problems = fixture_guard._scan_content(tmp_path, manifest)
    assert any(kind in problem for problem in problems), problems


@pytest.mark.parametrize("value", [[256], [-1], [True], ["no"], [255]])
def test_fixture_guard_refuses_invalid_message_arrays(tmp_path, value):
    data = json.dumps({"MESSAGE": value}).encode()
    (tmp_path / "row.jsonl").write_bytes(data)
    manifest = {"entries": {"row.jsonl": fixture_guard._entry(data)}}
    assert any("MESSAGE byte array" in problem for problem in fixture_guard._scan_content(tmp_path, manifest))


def test_committed_probe_doc_contains_no_unscrubbed_report_values():
    assert _check_probe_doc((REPO / "docs/seat_install_probe.md").read_text()) == []


@pytest.mark.parametrize("text, kind", [
    ("endpoint 8.8.8.8/32", "global IP"),
    ("cursor=" + "a" * 32, "hex32"),
    ('{"MESSAGE": "sk-\\u2060ant-synthetic"}', "escaped control"),
    ('{"MESSAGE": "x\\udb40\\udc41y"}', "escaped control"),
    ('{"MESSAGE": "x\\u001by"}', "escaped control"),
    ("Authorization: Basic dXNlcjpwYXNz", "G2"),
    ("github_pat_" + "AZ_9" * 8, "G2"),
])
def test_probe_doc_guard_bites_on_synthetic_bad_content(text, kind):
    assert any(kind in problem for problem in _check_probe_doc(text))


def test_probe_doc_guard_allows_public_hash_fields_and_unicode_punctuation():
    text = json.dumps({"txHash": "f" * 64, "MESSAGE": "accepted — paths"})
    assert _check_probe_doc(text) == []


def _run_python_section(name, raw, monkeypatch):
    text = PROBE.read_text()
    body = text.split('# BEGIN ' + name + '\n', 1)[1].split('# END ' + name, 1)[0]
    output = io.StringIO()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(raw))
    with contextlib.redirect_stdout(output):
        exec(compile(body, '<synthetic probe section>', 'exec'), {})
    return output.getvalue()


@pytest.mark.parametrize('as_bytes', [False, True])
def test_p04_redacts_full_message_before_eighty_column_head(monkeypatch, as_bytes):
    credential = 'github_pat_' + 'Synthetic_7' * 4
    message = 'x' * 74 + credential
    value = list(message.encode()) if as_bytes else message
    output = _run_python_section('CURSOR_PROBE', json.dumps({'MESSAGE': value, '__REALTIME_TIMESTAMP': '1'}), monkeypatch)
    assert output == '1 ' + ('x' * 74 + '[github-token]')[:80] + '\n'
    assert 'github' not in output


@pytest.mark.parametrize('char', ['\u200b', '\u2060'])
def test_p05_redacts_unicode_split_credentials_before_json_encoding(monkeypatch, capsys, char):
    body = PROBE.read_text().split('# BEGIN LIFECYCLE_PROBE\n', 1)[1].split('# END LIFECYCLE_PROBE', 1)[0]
    value = 'sk-' + char + 'ant-syntheticSample'
    record = json.dumps({'MESSAGE': value})
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, record, ''))
    exec(compile(body, '<synthetic p05>', 'exec'), {})
    output = capsys.readouterr().out
    assert 'syntheticSample' not in output
    assert 'sk-ant-[redacted]' in output
    assert '\\u200b' not in output and '\\u2060' not in output


def test_scrub_mode_is_unprivileged_and_covers_all_output_hygiene(tmp_path):
    # Synthetic installed-layout copy: no host probe functions are called.
    source = PROBE.read_text().replace('/usr/bin/python3', sys.executable)
    source = source.replace('/opt/imd-dash/broker', str(REPO))
    script = tmp_path / 'deploy/vps/probe_seat_host.sh'
    script.parent.mkdir(parents=True)
    script.write_text(source)
    forbidden = tmp_path / 'bin'
    forbidden.mkdir()
    for name in ('id', 'journalctl', 'systemctl', 'runuser', 'hostname'):
        (forbidden / name).write_text('#!/bin/sh\necho HOST_COMMAND_FORBIDDEN >&2\nexit 98\n')
        (forbidden / name).chmod(0o755)
    import os
    env = dict(os.environ, PATH=str(forbidden) + ':' + os.environ['PATH'])
    payload = ('IPAddressDeny=8.8.8.8/32 100.64.0.0/10 fc00::/7 fe80::/10\n'
               '2026-09-28T10:20:30.000Z aa:bb:cc:dd:ee:ff\n'
               'cursor=' + 'a' * 32 + '\nCookie: synthetic=session\nprice=\x24\n')
    result = subprocess.run(['bash', str(script), '--scrub'], input=payload, text=True,
                            capture_output=True, timeout=5, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ''
    assert '[public-ip]/32 100.64.0.0/10 fc00::/7 fe80::/10' in result.stdout
    assert '2026-09-28T10:20:30.000Z aa:bb:cc:dd:ee:ff' in result.stdout
    assert 'cursor=<hex>' in result.stdout and 'Cookie: [redacted]' in result.stdout
    assert '\x24' not in result.stdout


def test_p09_scrubs_before_truncation_and_p20_owner_commands_use_scrub():
    text = PROBE.read_text()
    assert 'scrub < "$out.err" | head -c 600 | code_block' in text
    p20 = text.split('p20() {', 1)[1].split('\n}', 1)[0]
    for line in p20.splitlines():
        if 'tail -n 6' in line or 'journalctl -u ' in line:
            assert '| bash $HERE/probe_seat_host.sh --scrub' in line


@pytest.mark.parametrize('address', ['8.8.8.8', '2606:4700:4700::1111'])
def test_shared_ip_detector_handles_label_colon(address):
    from imd_dashd.probe_hygiene import redact_public_ips
    assert redact_public_ips('peer:' + address) == 'peer:[public-ip]'


def test_probe_doc_guard_scans_numeric_json_values():
    assert 'hex32' in _check_probe_doc('{"value": 12345678901234567890123456789012}')


@pytest.mark.parametrize("address, suffix", [
    ("2606:4700:4700::1111", "."),
    ("2606:4700:4700::1111", "..."),
    ("2606:4700:4700::1111", "/128."),
    ("::ffff:8.8.8.8", "."),
    ("::ffff:8.8.8.8", "..."),
])
def test_sentence_final_global_ipv6_is_scrubbed(address, suffix):
    from imd_dashd.probe_hygiene import redact_public_ips
    assert redact_public_ips("peer " + address + suffix) == "peer [public-ip]" + suffix

@pytest.mark.parametrize("address", ["2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_sentence_final_global_ipv6_is_rejected_by_both_guards(tmp_path, address):
    text = "peer " + address + "."
    data = json.dumps({"MESSAGE": text}).encode()
    (tmp_path / "row.jsonl").write_bytes(data)
    manifest = {"entries": {"row.jsonl": fixture_guard._entry(data)}}
    fixture_problems = fixture_guard._scan_content(tmp_path, manifest)
    doc_problems = _check_probe_doc(text)
    assert (any("global IP" in problem for problem in fixture_problems), "global IP" in doc_problems) == (True, True), (fixture_problems, doc_problems)
