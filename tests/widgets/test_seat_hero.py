"""PEPEPANE hero: SEAT · LIVE · TODAY · VERDICTS · GATE · UNIT (spec §8 HERO; contract §C.15).

Composited assertions only. The healthy payload is the WP1 fixture folded by the
manager's own ``fold_status_document`` (a test may import ``data``), narrowed to the
hero's signature. Every expected word is the spec's own degraded wording.

Mutation proofs (spec §14): ``test_hero_red_beats_amber_beats_green`` -- swap the
severity order in ``hero.worst`` -> red; ``test_pending_is_never_green`` -- paint
``pend`` in green -> red; ``test_verdicts_read_counters_inconsistent_never_the_sum``
(proof 36, wording half) -- render ``life 244 of 290`` when the block says
``countersInconsistent`` -> red; ``test_third_party_text_is_redacted_in_the_hero``
(proof 12, strip half) -- drop the widget's ``redact()`` -> red.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES, fold_status_document
from maxpane_dashboard.widgets.seat.hero import BOX_IDS, SEVERITY, SeatHero, SeatHeroBox, fit_forms, worst
from maxpane_dashboard.screens.seat import SeatScreen


async def composite_lines(widget_cls, size, css_path=None, region_only=False, **payload):
    class HeroApp(App):
        CSS_PATH = css_path
        CSS = SeatScreen.DEFAULT_CSS

        def compose(self):
            yield widget_cls()

    async with HeroApp().run_test(size=size) as pilot:
        widget = pilot.app.query_one(widget_cls)
        widget.update_data(**payload)
        await pilot.pause()
        rows = ["".join(segment.text for segment in strip)
                for strip in pilot.app.screen._compositor.render_strips()]
        if region_only:
            region = widget.region
            rows = [row[region.x:region.right] for row in rows[region.y:region.bottom]]
        return [row.rstrip() for row in rows]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
SIGNATURE = SEAT_WIDGET_SIGNATURES["SeatHero"]
#: Six boxes of ~17 content cells: the width every short form was designed for (spec §8, deviation 6).
PIN = (143, 7)
#: Six boxes of 68 content cells (measured with ``SeatScreen.DEFAULT_CSS``: 1fr, margin 0 1, border, padding 0 1,
#: row padding 0 1 0 0). The longest full form asserted below is the 66-cell daemon line with ``[↑ …] (container)``;
#: at 300 columns a box holds only 44–45 cells and ``fit_forms`` would paint a shorter form.
WIDE = (440, 7)


def _healthy(**overrides) -> dict:
    flat = fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))
    payload = {key: copy.deepcopy(flat[key]) for key in SIGNATURE}
    payload.update(overrides)
    return payload


def _source(payload: dict, name: str, **fields) -> dict:
    payload["seat_sources"] = copy.deepcopy(payload["seat_sources"])
    payload["seat_sources"][name].update(fields)
    return payload


async def _boxes(size=PIN, **payload) -> dict[str, list[str]]:
    """Each box's non-blank value lines (border cells stripped), keyed like ``BOX_IDS``.

    ``HeroRow.render_box`` writes ``[dim]{label}[/]\\n\\n`` + body into the box, so the first two inner rows are
    the label and the blank under it: they are skipped (``lines[2:]``) and index 0 is the first value line.
    """
    class _A(App):
        CSS_PATH = CSS_PATH
        CSS = SeatScreen.DEFAULT_CSS

        def compose(self):
            yield SeatHero()

    async with _A().run_test(size=size) as pilot:
        hero = pilot.app.query_one(SeatHero)
        hero.update_data(**payload)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        out: dict[str, list[str]] = {}
        for key, box_id in BOX_IDS.items():
            region = pilot.app.query_one(f"#{box_id}").region
            lines = [rows[y][region.x + 1: region.x + region.width - 1].strip()
                     for y in range(region.y + 1, region.y + region.height - 1)]
            out[key] = [line for line in lines[2:] if line]  # lines[0] = label, lines[1] = the blank row
            out[key + "-border"] = rows[region.y + region.height - 1][region.x: region.x + region.width]
        out["-colour"] = hero.hero_colour()
        return out


async def _style_at(word: str, size=PIN, **payload):
    """The compositor's style on the first cell of *word*, plus the app's ansi theme."""
    class _A(App):
        CSS_PATH = CSS_PATH
        CSS = SeatScreen.DEFAULT_CSS

        def compose(self):
            yield SeatHero()

    async with _A().run_test(size=size) as pilot:
        pilot.app.query_one(SeatHero).update_data(**payload)
        await pilot.pause()
        rows = ["".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y = next(i for i, row in enumerate(rows) if word in row)
        x = rows[y].index(word)
        style = pilot.app.screen.get_style_at(x, y)
        return style.color.get_truecolor() if style.color else None, pilot.app.ansi_theme.ansi_colors


# -- shape ---------------------------------------------------------------------------------


def test_the_six_boxes_are_named_in_order_and_the_box_class_is_its_own_selector():
    assert SeatHero.BOXES == (("seat-hero-seat", "SEAT"), ("seat-hero-live", "LIVE"), ("seat-hero-config", "CONFIG & SKILLS"),
                              ("seat-hero-records", "RECORDS"), ("seat-hero-nodes", "NODES"), ("seat-hero-control", "CONTROL"))
    assert SeatHero.BOX_CLASS is SeatHeroBox and SeatHeroBox.__name__ == "SeatHeroBox"
    assert tuple(BOX_IDS.values()) == tuple(box_id for box_id, _label in SeatHero.BOXES)
    assert SEVERITY == ("green", "amber", "red")


def test_worst_orders_red_over_amber_over_green_and_ignores_junk():
    assert worst("green", "amber") == "amber" and worst("amber", "red", "green") == "red"
    assert worst(None, "bogus") is None and worst("green", None) == "green"


def test_fit_forms_picks_the_first_form_that_fits_and_marks_only_a_cut():
    from rich.text import Text
    forms = (Text("twelve tasks · eleven stored"), Text("12 tasks · 11 stored"), Text("12 · 11"))
    assert fit_forms(forms, 0) == (forms[0], False)
    assert fit_forms(forms, 20)[0].plain == "12 tasks · 11 stored" and fit_forms(forms, 20)[1] is False
    text, cut = fit_forms(forms, 5)
    assert cut is True and text.plain.endswith("…") and text.cell_len <= 5


async def test_no_args_and_all_none_render_unavailable_without_raising():
    rows = await composite_lines(SeatHero, PIN, css_path=CSS_PATH, region_only=True)
    text = "\n".join(rows)
    assert "unavailable" in text and "Loading" not in text
    rows = await composite_lines(SeatHero, PIN, css_path=CSS_PATH, region_only=True, **{k: None for k in SIGNATURE})
    assert "unavailable" in "\n".join(rows)


async def test_the_hero_row_is_seven_lines_with_the_screen_css():
    rows = await composite_lines(SeatHero, PIN, css_path=CSS_PATH, region_only=True, **_healthy())
    assert len(rows) == 7, rows


# -- the healthy fixture, whole at the pin -----------------------------------------------


async def test_healthy_fixture_fills_every_box_whole_at_the_pin_width():
    boxes = await _boxes(**_healthy())
    for key in BOX_IDS:
        assert boxes[key], key
        assert "…" not in "\n".join(boxes[key]) and "‹" not in boxes[key + "-border"], (key, boxes[key])
    assert boxes["seat"][0].startswith("IDMD #7")
    assert boxes["live"][0].startswith("● alive"), boxes["live"]
    assert "12" in boxes["seat"][2] and "11 stored" in boxes["seat"][2]
    assert "9" in boxes["records"][0] and "pend 1" in boxes["records"][0] or "1p" in boxes["records"][0]
    assert "safe to restart" in boxes["control"][0]
    assert boxes["seat"][1].startswith("active")
    assert boxes["-colour"] == "green"


async def test_the_wide_terminal_shows_the_spec_wordings():
    boxes = await _boxes(WIDE, **_healthy())
    assert boxes["seat"] == ["IDMD #7 · agent 51075 · eligible", "active · 110 MiB / 3 G · boot ⚠", "today 12 tasks · 11 stored"]
    assert boxes["config"] == ["codex-cli 0.157.0 · daemon 0.1.0+5bfa8261", "skills 31/31 · capacity 1", "unchanged since start"]
    assert boxes["live"][0] == "● alive 14h42m · idle · hb 4 s"
    # The healthy fixture's newest audit entry is a verified restart, so LIVE line 3 takes the audit branch;
    # the fleet line is the fallback when no restart/start audit entry exists.
    assert boxes["live"][2].startswith("↻ restarted ") and boxes["live"][2].endswith("· connected"), boxes["live"]
    no_audit = await _boxes(WIDE, **_healthy(seat_control_last_audit=[]))
    assert no_audit["live"][2] == "fleet 406 online · 417 enrolled"
    assert boxes["records"][0] == "today acc 9 · rej 0 · fail 1 · pend 1"
    assert boxes["records"][1] == "life 244 of 288 · lag p50 15m"
    assert boxes["records"][2].startswith("api · as of ")
    assert boxes["control"][0] == "safe to restart" and boxes["control"][1].startswith("idle 9 beats · plane []")
    # ``_clock`` renders local time (``as_of_hhmm`` -> ``time.localtime``): build the expectation the same way.
    assert boxes["control"][2] == f"last line submitted {as_of_hhmm('2026-09-26T03:24:17.136Z')} · outbox 0"


async def test_a_release_available_marks_the_daemon_line_and_the_container_suffix_appears_on_the_mac():
    boxes = await _boxes(WIDE, **_healthy(seat_release_available="0.1.0+5c1d2e3f", seat_host_kind="docker"))
    assert boxes["config"][0] == "codex-cli 0.157.0 · daemon 0.1.0+5bfa8261 [↑ 5c1d2e3f] (container)"
    narrow = await _boxes(**_healthy(seat_release_available="0.1.0+5c1d2e3f"))
    assert "↑" in narrow["config"][0], narrow["config"]


# -- colour: red beats amber beats green ----------------------------------------------------


async def test_hero_red_beats_amber_beats_green():
    # spec §8 HERO precedence red > amber > green; the fold's word never paints a green LIVE over a red fact
    both = _healthy(seat_hero_state="green", seat_daemon_heartbeat_age_s=95, seat_daemon_consecutive_disconnected_beats=2)
    boxes = await _boxes(**both)
    assert boxes["-colour"] == "red" and boxes["live"][0].startswith("○ disconnected"), boxes["live"]
    amber = await _boxes(**_healthy(seat_hero_state="green", seat_daemon_heartbeat_age_s=95))
    assert amber["-colour"] == "amber" and amber["live"][0].startswith("◐ h"), amber["live"]
    green = await _boxes(**_healthy())
    assert green["-colour"] == "green"
    fold_red = await _boxes(**_healthy(seat_hero_state="red"))
    assert fold_red["-colour"] == "red", "the fold's red is never downgraded by healthy local facts"


async def test_pending_is_never_green():
    # spec §6 rule 2 / §8: pending is yellow, never green, whether one or none
    # WIDE: at the pin VERDICTS paints its short form ``9a · 0r · 1f · 1p`` and the words are on no row.
    colour, ansi = await _style_at("pend 1", WIDE, **_healthy())
    assert colour == ansi[3] and colour != ansi[2], colour
    colour, ansi = await _style_at("pend 0", WIDE, **_healthy(seat_today_pending=0))
    assert colour != ansi[2], colour
    colour, ansi = await _style_at("acc 9", WIDE, **_healthy())
    assert colour == ansi[2]


async def test_verdicts_read_counters_inconsistent_never_the_sum():
    # spec §14 mutation proof 36, wording half: 244+5+11+28 != 290 renders the flag, never the numbers
    payload = _healthy(seat_standing_attempts=290, seat_standing_counters_inconsistent=True)
    boxes = await _boxes(WIDE, **payload)
    assert "counters inconsistent (api)" in boxes["records"][1]
    assert "290" not in "\n".join(boxes["records"]) and "244 of" not in "\n".join(boxes["records"])
    narrow = await _boxes(**payload)
    assert "inconsistent (api)" in narrow["records"][1] and "290" not in "\n".join(narrow["records"])
    colour, ansi = await _style_at("inconsistent (api)", WIDE, **payload)
    assert colour == ansi[3]


# -- degraded wordings (spec §8 table) --------------------------------------------------------


async def test_seat_box_degrades_to_saved_token_and_the_broker_reason():
    payload = _source(_healthy(), "status", ok=False, reason="socket timeout 20 s")
    boxes = await _boxes(WIDE, **payload)
    assert boxes["seat"][0] == "IDMD #7 (saved) — imd status unavailable"
    assert boxes["seat"][1] == "broker: socket timeout 20 s"
    narrow = await _boxes(**payload)
    assert narrow["seat"][0].startswith("IDMD #7 (saved)") and "unavailable" in "\n".join(narrow["seat"])


async def test_live_and_today_degrade_when_the_tail_is_dead():
    payload = _source(_healthy(seat_hero_state="red"), "tail", ok=False, reason="no aliveAt for 47 s", asOfUtc="2026-09-26T03:39:20Z")
    boxes = await _boxes(WIDE, **payload)
    assert boxes["live"][0].startswith("tail died ") and boxes["live"][0].endswith("— restarting")
    assert boxes["seat"][2] == "ledger unavailable — tail: no aliveAt for 47 s"
    assert boxes["-colour"] == "red"


async def test_live_reads_unit_inactive_and_offline_needs_the_fold_or_two_beats():
    inactive = await _boxes(WIDE, **_healthy(seat_unit_active_state="inactive"))
    assert inactive["live"][0].startswith("○ unit inactive since ")
    one_beat = await _boxes(WIDE, **_healthy(seat_daemon_state="disconnected", seat_daemon_consecutive_disconnected_beats=1))
    assert one_beat["-colour"] == "green" and "reconnecting" not in one_beat["live"][0], one_beat["live"]
    two = await _boxes(WIDE, **_healthy(seat_daemon_consecutive_disconnected_beats=2))
    assert two["live"][0] == "○ disconnected 2 beats · reconnecting" and two["-colour"] == "red"


async def test_live_third_line_precedence_paused_then_auth_then_restart_then_fleet():
    paused = await _boxes(WIDE, **_healthy(seat_hero_state="amber", seat_standing_paused_until="2026-09-26T23:53:00Z",
                                          seat_daemon_paused_hint={"until": "23:53", "failedRuns": 3, "reason": "x"},
                                          seat_auth_degraded=True, seat_auth_since_utc="2026-09-26T23:36:00Z"))
    assert paused["live"][2].startswith("⏸ paused until ") and "3 failed runs (api)" in paused["live"][2]
    assert paused["-colour"] == "amber"
    lingering = await _boxes(WIDE, **_healthy(seat_daemon_paused_hint={"until": "23:53", "failedRuns": 3, "reason": "x"}))
    assert lingering["live"][2].startswith("paused earlier until 23:53") and lingering["-colour"] == "green"
    auth = await _boxes(WIDE, **_healthy(seat_hero_state="amber", seat_auth_degraded=True, seat_auth_since_utc="2026-09-26T23:36:00Z"))
    assert auth["live"][2].startswith("⚠ runtime auth degraded since ")
    restarted = await _boxes(WIDE, **_healthy(seat_control_last_audit=[
        {"ts": "2026-09-26T03:40:31Z", "seq": 1288, "verb": "restart", "phase": "verify", "planId": "7f3a9c1e2b4d6081",
         "outcome": "applied", "verified": True, "connected": "pending (reconnecting since 03:40:31)"}]))
    assert restarted["live"][2].startswith("↻ restarted ") and "reconnecting since" in restarted["live"][2]
    connected = await _boxes(WIDE, **_healthy(seat_control_last_audit=[
        {"ts": "2026-09-26T03:40:31Z", "seq": 1288, "verb": "restart", "phase": "verify", "planId": "7f3a9c1e2b4d6081",
         "outcome": "applied", "verified": True, "connected": True}]))
    assert connected["live"][2].endswith("· connected")


async def test_today_reads_no_tasks_yet_with_the_last_node():
    boxes = await _boxes(WIDE, **_healthy(seat_today_tasks=0, seat_today_stored=0, seat_today_not_stored=0))
    assert boxes["seat"][2] == "no tasks yet today"
    assert "no tasks yet today" in boxes["seat"][2]


async def test_verdicts_degrade_to_values_kept_amber_then_unavailable_then_local_only():
    kept = _source(_healthy(), "seatWork", ok=False, reason="500 ×2 (retrying)", failures=2)
    boxes = await _boxes(WIDE, **kept)
    assert boxes["records"][0].startswith("today acc 9"), "values kept while retrying"
    assert boxes["records"][2].startswith("⚠ 500 ×2 (retrying) · last ")
    gone = _source(_healthy(seat_today_accepted=None, seat_today_rejected=None, seat_today_failed=None, seat_today_pending=None,
                            seat_standing_attempts=None, seat_standing_accepted=None, seat_today_verdict_lag_p50_s=None),
                   "seatWork", ok=False, reason="HTTP 500", failures=3, unavailable=True)
    boxes = await _boxes(WIDE, **gone)
    assert boxes["records"][0] == "verdicts unavailable" and boxes["records"][1] == "HTTP 500"
    offline = await _boxes(WIDE, **_healthy(seat_offline=True, seat_agent_id=None))
    assert offline["records"][1] == "local only (stored ≠ accepted)"
    assert offline["seat"][0] == "IDMD #7 · agent — · eligible"


async def test_gate_reads_broker_unreachable_in_flight_drain_and_unknown():
    unreachable = await _boxes(WIDE, **_healthy(seat_control_broker_reachable=False, seat_control_gate=None))
    assert unreachable["control"][0] == "broker unreachable — read-only"
    narrow = await _boxes(**_healthy(seat_control_broker_reachable=False, seat_control_gate=None))
    assert narrow["control"][0] in ("broker unreachable", "read-only")
    flight = await _boxes(WIDE, **_healthy(seat_control_in_flight={"verb": "restart", "planId": "7f3a9c1e2b4d6081", "sinceUtc": "2026-09-26T03:40:30Z"}))
    assert flight["control"][0] == "restart in flight (plan 7f3a) · verifying"
    drain = await _boxes(WIDE, **_healthy(seat_control_drain={"armedAtUtc": "2026-09-26T14:02:00Z", "idleBeats": 2, "rearmed": 1, "expiresAtUtc": "2026-09-26T18:02:00Z"}))
    assert drain["control"][0].startswith("drain armed ") and drain["control"][0].endswith("· 2/4 idle beats")
    gate = copy.deepcopy(_healthy()["seat_control_gate"])
    gate.update(safe=False, reason="gate unknown: outbox unreadable", outboxFiles=None)
    unknown = await _boxes(WIDE, **_healthy(seat_control_gate=gate))
    assert unknown["control"][0] == "gate unknown: outbox unreadable"
    running = copy.deepcopy(_healthy()["seat_control_gate"])
    running.update(safe=False, reason="task running 0c1f9727 · 0:42", lifecycleOpen=True)
    blocked = await _boxes(WIDE, **_healthy(seat_control_gate=running))
    assert blocked["control"][0] == "task running 0c1f9727 · 0:42"


async def test_unit_degrades_amber_without_touching_the_hero_colour():
    payload = _source(_healthy(seat_host_kind="docker", seat_unit_boot_enabled=None, seat_unit_graceful_stop_possible=False,
                               seat_unit_stop_timeout_s=10, seat_unit_kill_mode=None),
                      "unit", ok=False, reason="inspect timed out 25 s", asOfUtc="2026-09-26T03:07:00Z")
    boxes = await _boxes(WIDE, **payload)
    assert boxes["seat"][1].startswith("docker unavailable — inspect timed out 25 s")
    assert boxes["-colour"] == "green", "the tail owns liveness (spec §8 UNIT)"
    mac = await _boxes(WIDE, **_healthy(seat_host_kind="docker", seat_unit_boot_enabled=None, seat_unit_graceful_stop_possible=False,
                                        seat_unit_stop_timeout_s=10, seat_unit_kill_mode=None))
    assert mac["seat"][1].startswith("active · 110 MiB")
    # The stop and restart-policy facts moved to MACHINE/CONFIG; their tests cover both states.


async def test_a_partial_docker_read_says_unavailable_amber_while_ok_stays_true():
    # WP7 deviation 6 / spec §7 per-field sources: ``inspect`` timed out while ``stats`` answered -> ``ok`` True plus a
    # reason, the inspect half None. The box names the failure amber and keeps the stats half; the hero stays green.
    payload = _source(_healthy(seat_host_kind="docker", seat_unit_active_state=None, seat_unit_stop_timeout_s=None),
                      "unit", ok=True, reason="inspect timed out 25 s")
    boxes = await _boxes(WIDE, **payload)
    assert boxes["seat"][1].startswith("docker unavailable — inspect timed out 25 s"), boxes["seat"]
    assert "110 MiB" in boxes["seat"][1], "the stats half that answered is still served"
    assert "restart: unless-stopped" not in boxes["seat"], "the inspect half is not claimed"
    assert boxes["-colour"] == "green", "the tail owns liveness (spec §8 UNIT)"
    colour, ansi = await _style_at("docker unavailable", WIDE, **payload)
    assert colour == ansi[3], "amber in the cell"
    # a failed host read leaves every unit field present: UNIT is whole (MACHINE shows the host half)
    host_only = _source(_healthy(), "unit", ok=True, reason="host read failed")
    whole = await _boxes(WIDE, **host_only)
    assert whole["seat"][1].startswith("active · 110 MiB"), whole["seat"]


# -- honest shortening and marking (deviation 6) ----------------------------------------------


async def test_a_narrow_row_shortens_honestly_and_only_a_cut_marks_widen():
    boxes = await _boxes(**_healthy())
    assert all("‹" not in boxes[key + "-border"] for key in BOX_IDS), "at the design width nothing is cut"
    tiny = await _boxes((60, 7), **_healthy())
    cut = [key for key in BOX_IDS if "…" in "\n".join(tiny[key])]
    assert cut, "six boxes in 60 columns must cut something"
    for key in cut:
        assert "‹" in tiny[key + "-border"], (key, tiny[key + "-border"])


async def test_third_party_text_is_redacted_in_the_hero():
    # spec §14 mutation proof 12, strip half (hero): the widget itself redacts, not only the fold.
    # The runtime version is painted verbatim (an ``eligible…`` string collapses to the bare word), and
    # ``strip_tags`` deletes the ``[redacted]`` placeholder, so the painted remnant is ``sk-``.
    boxes = await _boxes(WIDE, **_healthy(seat_runtime_version="codex-cli sk-svcac******** 0.157.0"))
    joined = "\n".join(boxes["config"])
    assert "sk-svcac" not in joined and "codex-cli sk-" in joined, joined
    evil = await _boxes(WIDE, **_healthy(seat_eligibility="[/x][bold]evil"))
    assert "[bold]" not in "\n".join(evil["seat"])


@pytest.mark.parametrize("running,words", [(1, "⚙ 1 task running"), (3, "⚙ 3 tasks running")])
async def test_unattributed_running_text_is_amber_but_label_stays_plain(running, words):
    payload = _healthy(seat_daemon_running=running, seat_current=None, seat_hero_state="green")
    boxes = await _boxes(WIDE, **payload)
    assert boxes["live"][0] == words
    assert boxes["-colour"] == "green"
    color, ansi = await _style_at(words, WIDE, **payload)
    assert color == ansi[3]


@pytest.mark.parametrize("fields,prefix,color", [
    ({"seat_daemon_offline": True}, "○ disconnected", "red"),
    ({"seat_daemon_heartbeat_age_s": 95}, "◐ heartbeat", "amber"),
    ({"seat_unit_active_state": "inactive"}, "○ unit inactive", "red"),
])
async def test_unattributed_work_keeps_liveness_warning_precedence(fields, prefix, color):
    boxes = await _boxes(WIDE, **_healthy(seat_daemon_running=3, seat_current=None, **fields))
    assert boxes["live"][0].startswith(prefix)
    assert boxes["-colour"] == color


async def test_dead_tail_overrides_unattributed_work():
    payload = _source(_healthy(seat_daemon_running=3, seat_current=None), "tail", ok=False)
    boxes = await _boxes(WIDE, **payload)
    assert boxes["live"][0].startswith("tail died") and boxes["-colour"] == "red"


async def test_claude_short_form_uses_version_number_not_code_suffix():
    boxes = await _boxes(PIN, **_healthy(seat_runtime_id='claude', seat_runtime_version='2.1.286 (Claude Code)'))
    assert 'claude 2.1.286' in boxes['config'][0]
    assert 'Code)' not in boxes['config'][0]


@pytest.mark.parametrize('card,fields,source,expected', [
    ('SEAT', {'seat_unit_boot_enabled': False}, None, 3),
    ('SEAT', {'seat_unit_active_state': 'inactive'}, None, 1),
    ('LIVE', {'seat_hero_state': 'amber'}, None, 3),
    ('LIVE', {'seat_hero_state': 'red'}, None, 1),
    ('CONFIG & SKILLS', {'seat_control_restart_required': True}, None, 3),
    ('CONFIG & SKILLS', {'seat_config_changed_since_start': True}, None, 3),
    ('CONFIG & SKILLS', {}, ('seat', {'ok': False, 'reason': 'projection_refused (canary)'}), 1),
    ('CONTROL', {'seat_control_drain': {'armedAtUtc': '2026-10-03T17:00:00Z'}}, None, 3),
    ('CONTROL', {'seat_control_in_flight': {'verb': 'restart'}}, None, 3),
    ('CONTROL', {'seat_control_broker_reachable': False, 'seat_control_gate': None}, None, 3),
    ('CONTROL', {'seat_control_gate': None}, None, 1),
])
async def test_only_named_card_states_colour_the_label(card, fields, source, expected):
    payload = _healthy(**fields)
    if source:
        payload = _source(payload, source[0], **source[1])
    colour, ansi = await _style_at(card + ' ⚠', WIDE, **payload)
    assert colour == ansi[expected]


async def test_running_and_api_unreachable_leave_live_and_records_labels_plain():
    payload = _source(_healthy(seat_daemon_running=3, seat_current=None), 'standing', ok=False, reason='busy')
    payload = _source(payload, 'seatWork', ok=False, reason='busy', unavailable=True)
    rows = await composite_lines(SeatHero, WIDE, css_path=CSS_PATH, region_only=True, **payload)
    assert 'LIVE ⚠' not in '\n'.join(rows)
    assert 'RECORDS ⚠' not in '\n'.join(rows)


@pytest.mark.parametrize('today,lifetime,first,second', [
    ((9,0,1,1),(244,288),'today acc 9 · rej 0 · fail 1 · pend 1','life 244 of 288'),
    ((9,0,1,1),(None,None),'today acc 9 · rej 0 · fail 1 · pend 1','life unavailable'),
    ((None,7,0,0),(None,None),'today acc -- · rej 7 · fail 0 · pend 0','life unavailable'),
    ((None,None,None,None),(244,288),'today unavailable','life 244 of 288'),
])
async def test_records_hero_keeps_cached_counts_when_api_is_busy(today,lifetime,first,second):
    payload = _healthy(**dict(zip(('seat_today_accepted','seat_today_rejected','seat_today_failed','seat_today_pending'),today)),
                       seat_standing_accepted=lifetime[0],seat_standing_attempts=lifetime[1])
    payload = _source(payload,'seatWork',ok=False,unavailable=True,reason='busy',failures=4)
    payload = _source(payload,'standing',ok=False,unavailable=True,reason='busy',failures=4)
    boxes = await _boxes(WIDE,**payload)
    assert boxes['records'][0] == first
    assert boxes['records'][1].startswith(second)
    assert 'busy' in boxes['records'][2] and 'last' in boxes['records'][2]


async def test_records_hero_reports_standing_busy_without_hiding_cached_facts():
    payload = _source(_healthy(),'standing',ok=False,unavailable=True,reason='busy',failures=4)
    boxes = await _boxes(WIDE,**payload)
    assert 'acc 9' in boxes['records'][0]
    assert 'life 244 of 288' in boxes['records'][1]
    assert 'standing' in boxes['records'][2] and 'busy' in boxes['records'][2]
@pytest.mark.parametrize('width', [131, 132, 134])
async def test_complete_stress_hero_keeps_all_counts_and_known_node_at_ceiling(width):
    from tests.screens.test_seat_layout import worst_payload, _seat_app, _region_text
    async with _seat_app(worst_payload()).run_test(size=(width, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        records = _region_text(pilot.app, screen.query_one('#seat-hero-records'))
        nodes = _region_text(pilot.app, screen.query_one('#seat-hero-nodes'))
        assert '888a 77r 66f 55p' in records
        assert 'BUILD · 25 %' in nodes
        assert 'paid400 launch400' in nodes
        assert '…' not in records + nodes and '‹ widen' not in records + nodes


async def test_unknown_node_names_keep_their_original_text_and_honest_widen():
    from tests.screens.test_seat_layout import worst_payload, _seat_app, _region_text
    flat = worst_payload()
    flat['seat_nodes_all_rows'][0]['nodeKey'] = 'unmapped_node_identifier'
    for width in (131, 400):
        async with _seat_app(flat).run_test(size=(width, 50)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            nodes = _region_text(pilot.app, pilot.app.screen.query_one('#seat-hero-nodes'))
            if width == 131:
                assert 'unmapped_node' in nodes and '‹ widen' in nodes
            else:
                assert 'unmapped_node_identifier · 25 %' in nodes and '‹ widen' not in nodes
