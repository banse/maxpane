"""CONFIG & SKILLS and MACHINE (spec §8; contract §C.15). Composited assertions only.

Both are ``SignalsPanelBase`` panels whose values are sentences; every sentence is a
tuple of honest forms (deviation 6) so a half-width panel shows the same fact shorter,
and a title ``‹ widen`` lights only when even the shortest form had to be cut.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from textual.widgets import DataTable

from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES, fold_status_document
from maxpane_dashboard.widgets.fmt import mmdd
from maxpane_dashboard.widgets.seat.config import SeatConfig, pick_form
from maxpane_dashboard.widgets.seat import SeatSkills
from maxpane_dashboard.widgets.seat.machine import SeatMachine
from tests.widgets.test_seat_hero import composite_lines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
WIDE = (200, 32)
HALF = (71, 32)


def _flat() -> dict:
    return fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))


def _payload(cls_name: str, **overrides) -> dict:
    flat = _flat()
    payload = {key: copy.deepcopy(flat[key]) for key in SEAT_WIDGET_SIGNATURES[cls_name]}
    payload.update(overrides)
    return payload


def _source(payload: dict, name: str, **fields) -> dict:
    payload["seat_sources"] = copy.deepcopy(payload["seat_sources"])
    payload["seat_sources"][name].update(fields)
    return payload


def _rows(rows: list[str], label: str) -> str:
    line = next(line for line in rows if f" {label} " in line or line.strip().startswith(label)).strip()
    # CONFIG now has a separate change column; existing value assertions retain their subject.
    for change in ("fixed", "start flag", "runbook", "derived", "never", "space", "—"):
        if line.endswith("  " + change):
            line = line[:-len(change)].rstrip()
            break
    return line


async def _config(size=WIDE, **payload):
    return await composite_lines(SeatConfig, size, css_path=CSS_PATH, region_only=True, **payload)


async def _machine(size=WIDE, **payload):
    return await composite_lines(SeatMachine, size, css_path=CSS_PATH, region_only=True, **payload)


def test_pick_form_prefers_the_longest_that_fits_and_flags_only_a_cut():
    forms = ("economy codex gpt-6-luna/medium · standard same", "eco luna 6/medium · std same", "luna 6/med")
    assert pick_form(forms, 0) == (forms[0], False)
    assert pick_form(forms, 30) == (forms[1], False)
    text, cut = pick_form(forms, 6)
    assert cut is True and text.endswith("…") and len(text) <= 6


# -- CONFIG & SKILLS ----------------------------------------------------------------------


def test_config_and_skills_are_independent_cursor_tables():
    assert SeatConfig.TABLE_ID == "seat-config-table"
    assert SeatSkills.TABLE_ID == "seat-skills-table"
    assert SeatSkills.ROW_CAP is None
    assert SeatConfig.CURSOR_TYPE == SeatSkills.CURSOR_TYPE == "row"


async def test_config_healthy_values_at_a_wide_terminal():
    rows = await _config(**_payload("SeatConfig"))
    assert rows[0].strip().startswith("CONFIG · as of ")
    assert _rows(rows, "server").endswith("api.imd.fun")
    assert _rows(rows, "capacity").endswith("1 concurrent")
    assert _rows(rows, "offers").endswith("code · fuzz · research")
    assert _rows(rows, "runtime").endswith("codex-cli 0.157.0")
    assert _rows(rows, "daemon").endswith("0.1.0+5bfa8261 · up to date")
    assert _rows(rows, "premium advertised").endswith("gpt-6-astra/xhigh advertised (api)")
    assert _rows(rows, "inference economy").endswith("codex gpt-6-luna/medium")
    assert _rows(rows, "inference standard").endswith("gpt-6-luna/medium")
    assert _rows(rows, "inference premium").endswith("gpt-6-astra/xhigh")
    assert _rows(rows, "hints").endswith("~/.codex/AGENTS.md · 1.8 KB · sha 3f2a9c1e · 09-24")
    assert _rows(rows, "config").endswith("unchanged since start")
    # spec §8 group 1: the #7 codex wrapper note (systemd + codex only; no hardcoded model name, safety §2)
    assert _rows(rows, "wrapper").endswith(
        "/opt/imd-worker/bin/codex sets its own model/effort; the daemon's -m wins (effort precedence: source-proven only)")
    skills = await composite_lines(SeatSkills, (100, 32), css_path=CSS_PATH, region_only=True, **_payload("SeatSkills"))
    text = "\n".join(skills)
    assert "oracle-assess" in text and "public-rpcs" in text and "network" in text and "tool:forge" in text
    assert "tools: none configured" in text


async def test_config_release_available_changed_config_and_runtime_default():
    rows = await _config(**_payload("SeatConfig", seat_release_available="0.1.0+5c1d2e3f", seat_config_changed_since_start=True,
                                    seat_inference=None, seat_tools=["etherscan"]))
    assert _rows(rows, "daemon").endswith("0.1.0+5bfa8261 → 0.1.0+5c1d2e3f · update: see runbook §2.1 — drained restart")
    assert _rows(rows, "config").endswith("changed after start → restart required")
    assert _rows(rows, "inference").endswith("runtime default")
    skills = await composite_lines(SeatSkills, (100, 20), css_path=CSS_PATH, region_only=True, **_payload("SeatSkills", seat_tools=["etherscan"]))
    assert "tools: etherscan" in "\n".join(skills)


async def test_config_group_titles_carry_container_on_the_mac():
    rows = await _config(**_payload("SeatConfig", seat_host_kind="docker"))
    assert rows[0].strip().startswith("CONFIG (container)")
    skills = await composite_lines(SeatSkills, (100, 20), css_path=CSS_PATH, region_only=True, **_payload("SeatSkills", seat_host_kind="docker"))
    assert "SKILLS (container)" in "\n".join(skills)
    assert not any(" wrapper " in line for line in rows), "the codex wrapper note is #7's (systemd), never the Mac's"


async def test_skills_table_keeps_all_rows_without_the_old_cap():
    skills = [{"id": f"skill-{i:02d}", "on": i % 3 != 0, "needs": "network" if i % 4 == 0 else None} for i in range(31)]
    rows = await composite_lines(SeatSkills, (200, 40), css_path=CSS_PATH, region_only=True, **_payload("SeatSkills", seat_skills_rows=skills, seat_skills_offered=31, seat_skills_on=21))
    text = "\n".join(rows)
    assert sum(1 for line in rows if "skill-" in line) == 31
    assert "+19 more" not in text and " off " in text and " on " in text


async def test_config_degrades_per_source():
    broker = await _config(**_source(_payload("SeatConfig"), "broker", ok=False, reason="socket timeout 20 s"))
    for label in ("server", "capacity", "inference", "hints"):
        assert _rows(broker, label).endswith("unavailable (broker: socket timeout 20 s)"), label
    status = await _config(**_source(_payload("SeatConfig"), "status", ok=False, reason="imd status format changed in 0.1.0+5c1d2e3f"))
    assert _rows(status, "capacity").endswith("unavailable (imd status format changed in 0.1.0+5c1d2e3f)")
    assert _rows(status, "server").endswith("api.imd.fun"), "the seat projection is a different source"
    canary = await _config(**_source(_payload("SeatConfig", seat_inference=None), "seat", ok=False, reason="projection_refused (canary: devicekey_mismatch)"))
    assert _rows(canary, "inference").endswith("config projection unavailable — broker refused payload (canary)")


@pytest.mark.parametrize('tools,projection_ok,expected', [
    (None, True, 'unavailable'),
    ([], True, 'none configured'),
    (['etherscan'], True, 'etherscan'),
    (None, False, 'unavailable (projection read failed)'),
    ([], False, 'unavailable (projection read failed)'),
])
async def test_config_tools_distinguishes_missing_empty_and_failed_projection(tools, projection_ok, expected):
    payload = _source(_payload('SeatConfig', seat_tools=tools), 'seat',
                      ok=projection_ok, reason=None if projection_ok else 'projection read failed')
    payload = _source(payload, 'broker', ok=True, reason=None)
    rows = await _config(**payload)
    line = _rows(rows, 'tools')
    assert expected in line
    if tools is None or not projection_ok:
        assert 'none configured' not in line


async def test_config_half_width_shows_short_forms_without_wrapping_and_marks_only_a_cut():
    rows = await _config(HALF, **_payload("SeatConfig"))
    assert "‹" not in rows[0], "the CONFIG table now fits its shortest forms at half width"
    content = [line for line in rows[2:] if line.strip()]
    assert any("inference" in line for line in content)
    assert all(len(line) <= HALF[0] for line in rows)
    # A 40-cell panel cannot fit its shortest value forms, so its title advertises the cut.
    tiny = await _config((40, 32), **_payload("SeatConfig"))
    assert "‹" in tiny[0]


async def test_config_redacts_and_never_parses_third_party_text():
    rows = await _config(**_payload("SeatConfig", seat_skills_rows=[{"id": "sk-svcac******** [/x][bold]", "on": True, "needs": None}],
                                    seat_server="https://api.imd.fun/?token=sk-svcac********"))
    text = "\n".join(rows)
    # The server row shows only the host; ``strip_tags`` deletes the ``[redacted]`` placeholder, so the
    # redacted skills id paints as ``sk-``.
    assert "sk-svcac" not in text and "[bold]" not in text
    skills = await composite_lines(SeatSkills, (100, 20), css_path=CSS_PATH, region_only=True, **_payload("SeatSkills", seat_skills_rows=[{"id": "sk-svcac******** [/x][bold]", "on": True, "needs": None}]))
    assert "sk-" in "\n".join(skills) and "sk-svcac" not in "\n".join(skills)


# -- MACHINE -------------------------------------------------------------------------------


def test_machine_rows_are_the_contract_s():
    assert SeatMachine.ROWS == (("seat-mach-memory", "memory"), ("seat-mach-cpu", "cpu"), ("seat-mach-stop", "stop"), None,
                                ("seat-mach-host", "host"), ("seat-mach-work", "work/"), ("seat-mach-journal", "journal"),
                                ("seat-mach-transcripts", "transcripts"), ("seat-mach-orphans", "orphans"), None, ("seat-mach-plane", "plane"))
    assert SeatMachine.TITLE == "MACHINE" and SeatMachine.LABEL_WIDTH == 10


async def test_machine_healthy_values_at_a_wide_terminal():
    rows = await _machine(**_payload("SeatMachine"))
    assert rows[0].strip().startswith("MACHINE · as of ")
    assert _rows(rows, "memory").endswith("110 MiB · peak 180 MiB · max 3 G")
    assert _rows(rows, "cpu").endswith("quota 100% · tasks 11")
    assert _rows(rows, "stop").endswith("timeout 30 s · kill control-group → graceful stop possible")
    assert _rows(rows, "host").endswith("load 0.02 · mem avail 2.9 G · disk free 109 G")
    assert _rows(rows, "work/").endswith("288 dirs · 58 MB · 7 abnormal-lease dirs · outbox 0")
    # ``mmdd`` and ``as_of_hhmm`` both render local time: build the stamp with the same helpers.
    stamp = f"{mmdd(parse_iso('2026-09-22T12:00:00Z'))} {as_of_hhmm('2026-09-22T12:00:00Z')}"
    assert _rows(rows, "journal").endswith(f"{stamp} → now · cap ~347 MiB resolved at boot; 4 GiB after a journald restart")
    assert _rows(rows, "transcripts").endswith("rollouts plain 7 d then .zst (readable ✓)")
    assert _rows(rows, "orphans").endswith("none")
    assert _rows(rows, "plane").endswith("verifier up · last seen 03:32 · awaiting verdict 7 (undocumented) · 409 daemons (heartbeat: 406 online, 417 enrolled)") \
        or "awaiting verdict 7 (undocumented)" in _rows(rows, "plane")


async def test_machine_mac_wordings_orphans_and_zstd():
    orphan = {"pid": 64861, "pgid": 64861, "uid": 1000, "cgroup": "user-0.slice/session-147.scope", "ageS": 127000, "rssB": 130000000,
              "cmd": "codex exec --json … | tail -2", "pgidMembers": [{"pid": 64855, "uid": 0, "cgroup": "user-0.slice/session-147.scope", "cmd": "runuser"},
                                                                       {"pid": 64856, "uid": 0, "cgroup": "user-0.slice/session-147.scope", "cmd": "sh -c"}]}
    rows = await _machine(**_payload("SeatMachine", seat_host_kind="docker", seat_unit_graceful_stop_possible=False, seat_unit_stop_timeout_s=10,
                                     seat_unit_kill_mode=None,
                                     seat_machine_journal={"driver": "json-file", "rotation": "none", "bytes": 2524877, "diesWith": "docker rm"},
                                     seat_machine_transcript_retention={"kind": "claude-transcripts", "deleteDays": 30},
                                     seat_machine_orphans=[orphan]))
    assert _rows(rows, "stop").endswith("stop-timeout 10 s · no init → mid-task stop is ungraceful")
    assert _rows(rows, "journal").endswith("json-file 2.5 MB · no rotation · dies with docker rm")
    assert _rows(rows, "transcripts").endswith("transcripts 30-day window")
    assert _rows(rows, "orphans").endswith("1 (codex exec, 1 d 11 h, 130 MB, pgid shared with 2 root pids) → kill-orphans")
    zstd = await _machine(**_payload("SeatMachine", seat_machine_transcript_retention={"kind": "codex-rollouts", "plainDays": 7, "deleteDays": None, "zstdReadable": False}))
    assert _rows(zstd, "transcripts").endswith("rollouts > 7 d unreadable (compression.zstd missing)")


async def test_machine_degrades_per_group():
    unit = await _machine(**_source(_payload("SeatMachine"), "unit", ok=False, reason="inspect timed out 25 s"))
    assert _rows(unit, "memory").endswith("unavailable (unit: inspect timed out 25 s)")
    assert _rows(unit, "work/").endswith("288 dirs · 58 MB · 7 abnormal-lease dirs · outbox 0"), "workstat is another source"
    plane = await _machine(**_source(_payload("SeatMachine"), "plane", ok=False, reason="HTTP 500", failures=3, unavailable=True))
    assert _rows(plane, "plane").endswith("plane: unavailable (HTTP 500)")
    work = await _machine(**_source(_payload("SeatMachine"), "workstat", ok=False, reason="broker: timeout"))
    assert _rows(work, "work/").endswith("unavailable (workstat: broker: timeout)")
    assert _rows(work, "orphans").endswith("unavailable (workstat: broker: timeout)")


async def test_machine_half_width_never_wraps_and_marks_only_a_cut():
    rows = await _machine(HALF, **_payload("SeatMachine"))
    assert all(len(line) <= HALF[0] for line in rows) and "‹" not in rows[0]
    assert len([line for line in rows if line.strip()]) == 1 + 9, "title + nine value rows; separators are blank"


async def test_machine_no_args_renders_without_raising():
    rows = await _machine(**{k: None for k in SEAT_WIDGET_SIGNATURES["SeatMachine"]})
    assert rows[0].strip() == "MACHINE" and "unavailable" in "\n".join(rows)
