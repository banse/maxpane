"""The AGENT body's hero: SEAT · ACCEPTED JOBS · WORK · REWARDS · RANK · STATUS.

Composited assertions only. The summaries are **folded** from the committed
``/seats`` captures (``tests/fixtures/surf/swarm/seats/``) by
``data/surf_swarm.seat_summary_from_seat`` -- the manager's own fold -- and
every expected number is read back off that fold or the fixture, never
hand-typed. The per-class contract is imposed against
``SWARM_WIDGET_SIGNATURES`` (flipped in WP5).

**Composited under the real stylesheet, at the real pins.** The hero states no
geometry of its own (``rules/widgets.md``: ``HeroBoxBase`` leaves every
dimension to ``minimal.tcss``), so the harness loads
``maxpane_dashboard.app.CSS_PATH`` and renders at the AGENT body's own column
pin and at the app-wide ``FULL_LAYOUT_COLUMNS``: six boxes with ~16 content
cells each at the former.
"""

from __future__ import annotations

import copy
import inspect

import pytest
from textual.app import App

from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_summary_from_seat
from maxpane_dashboard.screens.surf import SURF_AGENT_FULL_LAYOUT_COLUMNS
from maxpane_dashboard.widgets.fmt import hhmm, mmdd
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf.swarm_agent_hero import (
    BOX_IDS,
    NO_SEAT_LINE,
    ONLINE_LINE,
    WORKING_GLYPH,
    WORKING_LINE,
    SurfSwarmAgentHero,
    SurfSwarmAgentHeroBox,
)
from tests.surf_swarm_fixtures import swarm_agent_sources, swarm_capture_v5, swarm_seat_capture
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmAgentHero"]

SEAT_420 = swarm_seat_capture("seat_420")
SEAT_0 = swarm_seat_capture("seat_0")
SUMMARY = seat_summary_from_seat(SEAT_420)
CONTRIB = swarm_agent_sources(420)["swarm_seat_contrib"]
SELECTED = {"token_id": int(SEAT_420["tokenId"]), "agent_id": str(SEAT_420["agentId"]),
            "selected_by": "saved"}
AS_OF = "04:06"
#: F-S5: seat 420's three disperse payments (13.8662 IMD, the committed
#: Blockscout capture) at a fixed price -- the owner's example, $105.84.
REWARD_IMD = (7692307692307692307 + 3052147239263803680 + 3121794871794871794) / 1e18
REWARDS = {"imd": REWARD_IMD, "usd": REWARD_IMD * 7.633, "seats": 1}
#: The AGENT body's own column pin; every ``_box_text`` renders here by default.
SIZE = (SURF_AGENT_FULL_LAYOUT_COLUMNS, 9)
#: The two widths the hero has to be whole at: its body's pin and the app's.
PINS = (SURF_AGENT_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS)
#: The seats-gated boxes; RANK reads ``/contributors`` and is not gated.
STAT_BOXES = ("accepted", "rewards")


_DROP = object()


def _folded(**changes) -> dict:
    """#420's capture with top-level fields replaced, then folded."""
    payload = copy.deepcopy(SEAT_420)
    for key, value in changes.items():
        if value is _DROP:
            payload.pop(key, None)
        else:
            payload[key] = value
    return seat_summary_from_seat(payload)


class _Themed(App):
    """The real stylesheet: ``SurfSwarmAgentHeroBox``'s geometry lives there."""

    CSS_PATH = CSS_PATH

    def compose(self):
        yield SurfSwarmAgentHero()


def _merged(kwargs) -> dict:
    return {"swarm_seat_selected": SELECTED, "swarm_seat_summary": SUMMARY,
            "swarm_seat_state": "ok", "swarm_seat_as_of_hhmm": AS_OF,
            "swarm_seat_live": {"live":True,"live_state":"idle","working":0,"max_concurrency":2},
            "swarm_seat_contrib": CONTRIB,
            "swarm_seat_rewards": REWARDS, "swarm_seat_rewards_state": "ok",
            "swarm_workers_as_of_hhmm":"05:07", **kwargs}


async def _hero(size=SIZE, **kwargs):
    return "\n".join(await composite_lines(SurfSwarmAgentHero, size, css_path=CSS_PATH,
                                           **_merged(kwargs)))


async def _box_text(box_id, size=SIZE, **kwargs):
    """The composited text of one box's own region (the boxes share rows)."""
    async with _Themed().run_test(size=size) as pilot:
        hero = pilot.app.query_one(SurfSwarmAgentHero)
        hero.update_data(**_merged(kwargs))
        await pilot.pause()
        box = pilot.app.query_one(f"#{box_id}")
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        region = box.region
        sliced = [
            rows[y][region.x: region.x + region.width]
            for y in range(max(region.y, 0), min(region.y + region.height, len(rows)))
        ]
        return "\n".join(row.rstrip() for row in sliced)


async def _boxes(size=SIZE, **kwargs) -> dict[str, str]:
    return {key: await _box_text(BOX_IDS[key], size=size, **kwargs) for key in BOX_IDS}


def _lines(box: str) -> list[str]:
    """A box's non-blank content lines, border and padding stripped."""
    out = []
    for row in box.split("\n"):
        inner = row.strip().strip("│┌┐└┘─").strip()
        if inner:
            out.append(inner)
    return out


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_target_signature_in_order():
    sig = inspect.signature(SurfSwarmAgentHero.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SIGNATURE
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_without_raising():
    """Nothing selected and no state: SEAT says so, the five stat boxes are
    ``unavailable`` (the state is ``None``), and no ``Loading...`` seed survives."""
    bare = "\n".join(await composite_lines(SurfSwarmAgentHero, SIZE, css_path=CSS_PATH))
    # Six: the three stat boxes, RANK (no contributors read), STATUS's
    # worker word and its accepted line.
    assert bare.count("unavailable") == 6 and "Loading" not in bare
    assert NO_SEAT_LINE in bare
    none = "\n".join(await composite_lines(SurfSwarmAgentHero, SIZE, css_path=CSS_PATH,
                                           **{k: None for k in SIGNATURE}))
    assert none == bare


def test_the_box_class_is_its_own_type_selector_and_the_six_boxes_are_named():
    assert SurfSwarmAgentHero.BOX_CLASS is SurfSwarmAgentHeroBox
    assert len(BOX_IDS) == 6 == len(SurfSwarmAgentHero.BOXES)
    labels = [label for _id, label in SurfSwarmAgentHero.BOXES]
    # F-S6 (owner, 2026-10-02): ACCEPTED JOBS and WORK traded places.
    assert labels == ["SEAT", "ACCEPTED JOBS", "WORK", "REWARDS", "RANK", "STATUS"]
    assert [box_id for box_id, _label in SurfSwarmAgentHero.BOXES] == [
        BOX_IDS[key] for key in ("seat", "accepted", "work", "rewards", "rank", "status")]


async def test_the_hero_row_is_seven_lines_under_the_stylesheet():
    """SEAT's three lines under the label and its blank row need a 7-tall box."""
    async with _Themed().run_test(size=SIZE) as pilot:
        hero = pilot.app.query_one(SurfSwarmAgentHero)
        hero.update_data(**_merged({}))
        await pilot.pause()
        assert hero.region.height == 7
        assert all(box.region.height == 7 for box in pilot.app.query(SurfSwarmAgentHeroBox))


# -- the #420 record, folded ---------------------------------------------------------


@pytest.mark.parametrize("width", PINS)
async def test_the_defect_seat_renders_its_lifetime_record_whole_at_both_pins(width):
    boxes = await _boxes(size=(width, 9))
    assert f"IDMD #{SELECTED['token_id']}" in boxes["seat"]
    assert f"agent {SELECTED['agent_id']}" in boxes["seat"] and "saved" not in boxes["seat"]
    assert f"{SUMMARY['accepted']} of {SUMMARY['attempts']}" in boxes["accepted"]
    # F-S5: the owner's example, line 1 IMD, line 2 blank, line 3 USD.
    assert _inner_rows(boxes["rewards"]) == ["REWARDS", "", "13.87 IMD", "", "$105.84"]
    assert f"{SUMMARY['win_rate']*100:.1f} %" in boxes["accepted"]
    assert "of attempts" not in boxes["accepted"]
    assert f"#{CONTRIB['rank']} of {CONTRIB['ranked_of']}" in boxes["rank"]
    assert "turns" not in boxes["work"]
    assert f"{CONTRIB['wall_clock_s'] / 3600:.1f} h" in boxes["work"]
    assert f"{ONLINE_LINE} · {WORKING_GLYPH} 0 of 2" in boxes["status"]
    assert f"accepted {mmdd(SUMMARY['last_won_ts'])} {hhmm(SUMMARY['last_won_ts'])}" in boxes["status"]
    assert "as of" not in "\n".join(boxes.values())
    for key, text in boxes.items():
        assert "…" not in text and "unavailable" not in text, (width, key, text)


@pytest.mark.parametrize("width", PINS)
async def test_the_largest_seat_fits_whole_and_reads_offline(width):
    summary = seat_summary_from_seat(SEAT_0)
    selected = {"token_id": 0, "agent_id": str(SEAT_0["agentId"]), "selected_by": "most_active"}
    boxes = await _boxes(size=(width, 9), swarm_seat_selected=selected,
                         swarm_seat_summary=summary, swarm_seat_live={"live":False,"live_state":"offline"})
    assert "13.87 IMD" in boxes["rewards"]
    assert "offline" in boxes["status"] and "online" not in boxes["status"]
    assert "most active" in boxes["seat"]
    for key, text in boxes.items():
        assert "…" not in text, (width, key, text)


async def test_no_marker_means_no_as_of_line():
    accepted = await _box_text(BOX_IDS["accepted"], swarm_seat_as_of_hhmm="")
    assert "as of" not in accepted and f"{SUMMARY['accepted']} of" in accepted


# -- the seat state ------------------------------------------------------------------


async def test_pending_says_loading_in_the_stat_boxes_and_still_names_the_seat():
    """A switch in flight: the reader must see *which* seat is loading, and no
    number of the seat that was shown before (A's summary under B's name)."""
    other = {"token_id": 12345, "agent_id": "50906", "selected_by": "saved"}
    boxes = await _boxes(swarm_seat_selected=other, swarm_seat_state="pending",
                         swarm_seat_as_of_hhmm=None)
    assert "IDMD #12345" in boxes["seat"] and "agent 50906" in boxes["seat"]
    assert "IDMD #12345" in boxes["seat"] and "Loading" not in boxes["seat"]
    for key in STAT_BOXES:
        assert "Loading..." in boxes[key], (key, boxes[key])
    # SUMMARY (seat #420's numbers) was passed in and must not reach a pixel.
    whole = "\n".join(boxes.values())
    assert f"{SUMMARY['accepted']} of" not in whole and "IMD" not in whole


async def test_a_failed_read_is_unavailable_never_zero_and_still_names_the_seat():
    boxes = await _boxes(swarm_seat_state=None, swarm_seat_summary=None,
                         swarm_seat_as_of_hhmm=None)
    assert f"IDMD #{SELECTED['token_id']}" in boxes["seat"]
    assert "unavailable" not in boxes["seat"]
    for key in STAT_BOXES:
        body = [line.strip("│ ") for line in boxes[key].splitlines()]
        assert "unavailable" in body, (key, boxes[key])
        assert "0" not in body and "0 of 0" not in boxes[key], (key, boxes[key])


async def test_a_malformed_state_is_unavailable():
    boxes = await _boxes(swarm_seat_state="garbage")
    for key in STAT_BOXES:
        assert "unavailable" in boxes[key], key


@pytest.mark.parametrize("width", PINS)
async def test_a_seat_that_never_paired_says_so_and_counts_nothing(width):
    """``unknown_seat`` is a real negative, not a failure: the stat boxes show a
    dim em dash, never ``unavailable``, and SEAT says ``never paired``."""
    boxes = await _boxes(size=(width, 9), swarm_seat_state="unknown_seat",
                         swarm_seat_summary=None,
                         swarm_seat_selected={"token_id": 12345, "agent_id": None,
                                              "selected_by": "saved"})
    assert "IDMD #12345" in boxes["seat"] and NEVER_PAIRED_WORDS in boxes["seat"]
    assert "…" not in boxes["seat"], (width, boxes["seat"])
    for key in STAT_BOXES:
        body = [line.strip("│ ") for line in boxes[key].splitlines()]
        assert "—" in body and "unavailable" not in boxes[key], (key, boxes[key])


async def test_no_selection_says_so_rather_than_naming_a_seat():
    seat = await _box_text(BOX_IDS["seat"], swarm_seat_selected=None, swarm_seat_state=None,
                           swarm_seat_summary=None, swarm_seat_as_of_hhmm=None)
    assert NO_SEAT_LINE in seat and "IDMD" not in seat


#: A lifetime record years on: every counter at its realistic ceiling. The
#: totals have no ceiling of their own (seat #0 already has 202 reviews), so
#: the box's width is bounded by its *lines*, never by the seat's age.
FIVE_DIGIT = dict(SUMMARY, reviewed=99_999, scored=99_999, accepted=9_999, attempts=99_999,
                  collaborators=9_999,
                  review_status={"sent": 98_001, "submitted": 999, "queued": 999})


@pytest.mark.parametrize("width", PINS)
async def test_a_five_digit_record_fits_every_box_at_both_pins(width):
    """The fix-round finding: a two-value line was cut at the AGENT pin, where
    the hero has no ``‹``. REWARDS' widest amount below the compact form,
    ``99,999.99 IMD`` over ``$99,999.99``, fits whole, and so does ACCEPTED's
    ``9,999 of 99,999``."""
    boxes = await _boxes(size=(width, 9), swarm_seat_summary=FIVE_DIGIT,
                         swarm_seat_rewards={"imd": 99_999.99, "usd": 99_999.99, "seats": 1})
    assert _lines(boxes["rewards"])[-2:] == ["99,999.99 IMD", "$99,999.99"], boxes["rewards"]
    assert "9,999 of 99,999" in boxes["accepted"]
    assert "of attempts" not in boxes["accepted"]
    for key, text in boxes.items():
        assert "…" not in text, (width, key, text)


# -- zeros, missing fields and malformed payloads --------------------------------------


async def test_a_zero_record_renders_zeros_not_unavailable():
    zero = _folded(attempts=0, accepted=0, work=[], reviews=[], collaborators=[])
    boxes = await _boxes(swarm_seat_summary=zero)
    assert "0 of 0" in boxes["accepted"]
    assert "no attempts" in boxes["accepted"]
    for key in STAT_BOXES:
        assert "unavailable" not in boxes[key], (key, boxes[key])


async def test_a_field_the_source_did_not_carry_is_unavailable_in_its_own_box_only():
    """``attempts`` missing from the payload folds to ``None``: ACCEPTED says
    ``unavailable`` -- never ``12 of 0`` -- and the other boxes keep their numbers."""
    missing = _folded(attempts=_DROP)
    assert missing["attempts"] is None and missing["accepted"] == SUMMARY["accepted"]
    boxes = await _boxes(swarm_seat_summary=missing)
    assert "unavailable" in boxes["accepted"]
    assert " of 0" not in boxes["accepted"] and " of " not in boxes["accepted"]
    assert "13.87 IMD" in _lines(boxes["rewards"])
    assert f"{WORKING_GLYPH} 0 of 2" in boxes["status"]


# -- REWARDS (F-S5) ---------------------------------------------------------------


@pytest.mark.parametrize("rewards, state, expected", [
    (None, "pending", ["REWARDS", "Loading..."]),
    (None, None, ["REWARDS", "unavailable"]),
    (REWARDS, None, ["REWARDS", "unavailable"]),     # a value with no ok state is not shown
    ("garbage", "ok", ["REWARDS", "unavailable"]),
    ({"imd": None, "usd": 1.0, "seats": 1}, "ok", ["REWARDS", "unavailable"]),
    ({"imd": float("nan"), "usd": 1.0, "seats": 1}, "ok", ["REWARDS", "unavailable"]),
    ({"imd": -1.0, "usd": 1.0, "seats": 1}, "ok", ["REWARDS", "unavailable"]),
    ({"imd": 0.0, "usd": 0.0, "seats": 1}, "ok", ["REWARDS", "0.00 IMD", "$0.00"]),
    ({"imd": 13.8662, "usd": None, "seats": 1}, "ok", ["REWARDS", "13.87 IMD", "unavailable"]),
    ({"imd": 0.001, "usd": 0.004, "seats": 1}, "ok", ["REWARDS", "<0.01 IMD", "<$0.01"]),
])
async def test_rewards_says_which_kind_of_missing(rewards, state, expected):
    text = await _box_text(BOX_IDS["rewards"], swarm_seat_rewards=rewards,
                           swarm_seat_rewards_state=state)
    assert _lines(text) == expected, text


@pytest.mark.parametrize("seat_state, word", [("pending", "Loading..."), ("busy", "busy · retrying"),
                                              (None, "unavailable"), ("unknown_seat", "—")])
async def test_the_seat_state_gates_rewards_before_its_own_state(seat_state, word):
    text = await _box_text(BOX_IDS["rewards"], swarm_seat_state=seat_state)
    assert _lines(text) == ["REWARDS", word] and "IMD" not in text


@pytest.mark.parametrize("value, shown", [
    (13.8662, "13.87"), (99_999.994, "99,999.99"), (99_999.996, "100.0K"),
    (999_949.0, "999.9K"), (999_950.0, "1.0M"), (1_234_567.0, "1.2M"),
    (999_950_000_000.0, "1.0e+12"), (0.0, "0.00"), (0.004, "<0.01"),
])
async def test_reward_amounts_shorten_honestly(value, shown):
    text = await _box_text(BOX_IDS["rewards"],
                           swarm_seat_rewards={"imd": value, "usd": value, "seats": 1})
    assert _lines(text)[1] == f"{shown} IMD"
    assert _lines(text)[2] == (f"<${shown[1:]}" if shown.startswith("<") else f"${shown}")


async def test_malformed_payloads_land_on_unavailable_not_a_crash():
    whole = await _hero(swarm_seat_summary="garbage")
    assert "unavailable" in whole
    seat = await _box_text(BOX_IDS["seat"], swarm_seat_selected=["not", "a", "dict"])
    assert "unavailable" in seat
    typed = dict(SUMMARY, accepted="lots", online="yes")
    boxes = await _boxes(swarm_seat_summary=typed,swarm_seat_live={"live":"yes"})
    assert "unavailable" in boxes["accepted"] and "unavailable" in boxes["status"]
    assert f"#{CONTRIB['rank']} of" in boxes["rank"]


# -- RANK ------------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["pending", None, "unknown_seat"])
async def test_rank_follows_the_contributors_read_not_the_seat(state):
    rank = await _box_text(BOX_IDS["rank"], swarm_seat_state=state, swarm_seat_summary=None)
    assert f"#{CONTRIB['rank']} of {CONTRIB['ranked_of']}" in rank


@pytest.mark.parametrize("contrib,expected", [({**CONTRIB, "listed": False}, "not listed"),
                                               (None, "unavailable")])
async def test_rank_says_not_listed_apart_from_a_failed_read(contrib, expected):
    rank = await _box_text(BOX_IDS["rank"], swarm_seat_contrib=contrib)
    assert expected in rank and "#" not in rank


# -- SEAT ------------------------------------------------------------------------------


@pytest.mark.parametrize("width", PINS)
async def test_a_saved_seat_says_nothing_and_the_busiest_says_most_active(width):
    """Owner, 2026-09-22: ``saved`` is the normal case and SEAT drops the word."""
    saved = await _box_text(BOX_IDS["seat"], size=(width, 9),
                            swarm_seat_selected=dict(SELECTED, selected_by="saved"))
    assert "saved" not in saved and "--" not in saved and "IDMD #" in saved
    most = await _box_text(BOX_IDS["seat"], size=(width, 9),
                           swarm_seat_selected=dict(SELECTED, selected_by="most_active"))
    assert "most active" in most and "…" not in most


async def test_a_hostile_agent_id_renders_literally():
    text = await _box_text(BOX_IDS["seat"], swarm_seat_selected=dict(SELECTED, agent_id="[/x]"))
    assert "agent [/x]" in text


async def test_a_theme_token_in_an_agent_id_does_not_raise():
    text = await _box_text(BOX_IDS["seat"], swarm_seat_selected=dict(SELECTED, agent_id="[$success]"))
    assert "agent [$success]" in text

async def test_status_names_only_the_last_won_date_not_feedback_time():
    from maxpane_dashboard.widgets.fmt import mmdd
    summary = dict(SUMMARY, last_won_ts=1_758_456_000, last_sent_ts=1_758_628_800)
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=summary)
    assert f"accepted {mmdd(summary['last_won_ts'])} {hhmm(summary['last_won_ts'])}" in text
    assert "last" not in text


async def test_status_says_worked_when_the_newest_attempt_is_newer_than_the_newest_accept():
    """Owner 2026-09-22 on the live v5 capture: the newest attempt (22:07) is not accepted."""
    summary = seat_summary_from_seat(swarm_capture_v5("seat_420"))
    won, worked = summary["last_won_ts"], summary["last_worked_ts"]
    assert worked > won
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=summary)
    assert f"worked {mmdd(worked)} {hhmm(worked)}" in text and "accepted" not in text


@pytest.mark.parametrize("worked_delta", [0, -60, None])
async def test_status_keeps_accepted_when_it_is_the_newest(worked_delta):
    won = SUMMARY["last_won_ts"]
    worked = None if worked_delta is None else won + worked_delta
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=dict(SUMMARY, last_worked_ts=worked))
    assert f"accepted {mmdd(won)} {hhmm(won)}" in text and "worked" not in text


async def test_status_says_worked_for_a_seat_with_no_accepted_work():
    worked = SUMMARY["last_won_ts"]
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=dict(
        SUMMARY, accepted=0, last_won_ts=None, last_worked_ts=worked))
    assert f"worked {mmdd(worked)}" in text and "none accepted" not in text


@pytest.mark.parametrize("accepted,expected", [(0, "none accepted yet"), (3, "accepted unavailable"), (None, "accepted unavailable")])
async def test_status_distinguishes_no_wins_from_missing_win_timestamp(accepted, expected):
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=dict(SUMMARY, accepted=accepted, last_won_ts=None))
    assert expected in text and "??" not in text


async def test_acceptance_words_replace_retired_win_words_in_composited_output():
    boxes = await _boxes()
    text = "\n".join(boxes.values())
    assert "WORK" in text and "ACCEPTED" in text and "ACCEPT RATE" not in text
    assert "WIN RATE" not in text and "won " not in text and "wins" not in text

LIVE = dict(live=True, live_state='working', working=3, max_concurrency=8, paused_until_ts=1_758_456_000,
            failures=7, skills=30, profiles=['foundry'], platform='linux x64')

@pytest.mark.parametrize('state',['pending',None])
async def test_worker_status_survives_bad_seats_without_stale_accepted_date(state):
    text=await _box_text(BOX_IDS['status'],size=(180,9),swarm_seat_state=state,
                        swarm_seat_live=LIVE,swarm_workers_as_of_hhmm='05:07')
    assert f'{WORKING_GLYPH} 3 of 8' in text and 'until' in text and '×7' in text
    assert '05:07' not in text
    assert 'accepted unavailable' in text and mmdd(SUMMARY['last_won_ts']) not in text
    assert len(_lines(text)) == 4  # one title, exactly three body lines

@pytest.mark.parametrize('live,expected',[(None,'unavailable'),({'live':False,'live_state':'offline'},'offline')])
async def test_worker_status_distinguishes_offline_from_unavailable(live,expected):
    text=await _box_text(BOX_IDS['status'],size=(180,9),swarm_seat_live=live)
    assert expected in _lines(text)
    assert ('offline' in text)==(expected=='offline')
    assert f"accepted {mmdd(SUMMARY['last_won_ts'])}" in text

async def test_seats_clock_leaves_the_hero_for_record():
    # Owner 2026-09-22: the STATUS title lost "workers as of HH:MM".
    boxes=await _boxes(size=(180,9),swarm_seat_live=LIVE,swarm_workers_as_of_hhmm='05:07')
    assert 'as of' not in '\n'.join(boxes.values())
    assert _lines(boxes['status'])[0] == 'STATUS'
    assert '05:07' not in boxes['status'] and '04:06' not in boxes['status']


@pytest.mark.parametrize('live_state,word,color',[
    ('working',WORKING_LINE,2),('idle',ONLINE_LINE,2),('offline','offline',1),
    ('paused','paused',1),(None,'unavailable',3),
])
async def test_polish_worker_status_words_and_composited_colors(live_state,word,color):
    live=dict(live=live_state!='offline',live_state=live_state,working=2 if live_state=='working' else 0,
              max_concurrency=8,paused_until_ts=1758456000 if live_state=='paused' else None,failures=7)
    async with _Themed().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmAgentHero).update_data(**_merged(dict(swarm_seat_live=live)))
        await pilot.pause()
        box=pilot.app.query_one('#'+BOX_IDS['status']);region=box.region
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y=next(y for y in range(region.y,region.bottom) if word in lines[y][region.x:region.right])
        x=lines[y].index(word,region.x)
        style=pilot.app.screen.get_style_at(x,y)
        assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
        if live_state in ('idle','working'):
            # Owner 2026-09-22: only "● online" is green; the counts after it are not.
            # F-S4 (owner, 2026-10-02): "● working" takes the same shape.
            count_x=lines[y].index(WORKING_GLYPH,region.x)
            assert pilot.app.screen.get_style_at(count_x,y).color!=style.color
        content='\n'.join(line[region.x:region.right] for line in lines[region.y:region.bottom])
        assert 'as of' not in content and 'accepted '+mmdd(SUMMARY['last_won_ts']) in content
        if live_state in ('idle','paused',None):assert f'{WORKING_GLYPH} 0 of 8' in content
        if live_state=='working':assert f'{WORKING_LINE} · {WORKING_GLYPH} 2 of 8' in content
        else:assert 'working' not in content
        if live_state=='paused':assert 'until '+hhmm(1758456000) in content and '×7' in content
        assert '…' not in content


async def test_polish_unknown_pause_fold_reaches_unavailable_not_idle():
    from maxpane_dashboard.data import surf_swarm as fold
    from tests.surf_swarm_fixtures import swarm_capture_v4
    row=swarm_capture_v4('workers')['workers'][0]
    row.update(working=0,paused=None)
    token=int(row['seat']['tokenId'])
    idle=fold.seat_live(dict(count=1,workers=[row]),token)
    row.pop('paused')
    unknown=fold.seat_live(dict(count=1,workers=[row]),token)
    assert idle['live_state']=='idle' and unknown['live_state'] is None
    for live,expected in ((idle,ONLINE_LINE),(unknown,'unavailable')):
        text=await _box_text(BOX_IDS['status'],swarm_seat_live=live)
        assert _lines(text)[1].startswith(expected),text
        assert ('online' in text)==(expected==ONLINE_LINE) and 'idle' not in text
        assert f'{WORKING_GLYPH} 0 of ' in text


async def test_polish_accepted_rewards_and_rate_have_composited_emphasis():
    async with _Themed().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmAgentHero).update_data(**_merged({}))
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        for box_key,word,color in (('accepted',str(SUMMARY['accepted']),2),('accepted',str(SUMMARY['attempts']),None),
                                   ('rewards','13.87',None),('rewards','105.84',None),('accepted',f"{SUMMARY['win_rate']*100:.1f}",None)):
            region=pilot.app.query_one('#'+BOX_IDS[box_key]).region
            y=next(y for y in range(region.y,region.bottom) if word in lines[y][region.x:region.right])
            style=pilot.app.screen.get_style_at(lines[y].index(word,region.x),y)
            assert style.bold,(box_key,word,style)
            if color is not None:assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]


@pytest.mark.parametrize('delta,word,color', [(2,'▲2',2),(-3,'▼3',1),(None,None,None),(0,None,None)])
async def test_rank_move_has_composited_direction_and_color(delta, word, color):
    async with _Themed().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmAgentHero).update_data(**_merged({'swarm_seat_rank_delta':delta}))
        await pilot.pause()
        region = pilot.app.query_one('#'+BOX_IDS['rank']).region
        rows = [''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        text = '\n'.join(row[region.x:region.right] for row in rows[region.y:region.bottom])
        assert 'turns' not in text and ' h' not in text
        if word:
            y = next(y for y in range(region.y,region.bottom) if word in rows[y][region.x:region.right])
            style = pilot.app.screen.get_style_at(rows[y].index(word,region.x),y)
            assert style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[color]
        else:
            assert '▲' not in text and '▼' not in text


@pytest.mark.parametrize('tokens,expected', [(1_700_000,'1.7M tokens'),(0,'0 tokens'),
    (None,'-- tokens'),('[/x]','-- tokens'),(True,'-- tokens'),(-1,'-- tokens'),
    (10**30,'1.0e+30 tokens'),(10**1000,'-- tokens')])
async def test_work_output_tokens_are_bounded_and_honest(tokens, expected):
    text = await _box_text(BOX_IDS['work'], swarm_seat_contrib={**CONTRIB, 'output_tokens':tokens})
    assert _lines(text) == ['WORK', f"{CONTRIB['wall_clock_s']/3600:.1f} h", expected]


@pytest.mark.parametrize('contrib,word', [(None,'unavailable'),({'listed':False},'not listed')])
async def test_work_uses_contributor_availability(contrib,word):
    text = await _box_text(BOX_IDS['work'], swarm_seat_contrib=contrib)
    assert _lines(text) == ['WORK', word]


async def test_unranked_never_shows_a_stale_delta():
    text = await _box_text(BOX_IDS['rank'], swarm_seat_contrib={**CONTRIB, 'rank':None}, swarm_seat_rank_delta=2)
    assert _lines(text) == ['RANK', 'unranked']


async def test_committed_420_capture_reaches_work_accepted_and_rank():
    from tests.surf_swarm_fixtures import swarm_capture_v3
    summary = seat_summary_from_seat(swarm_capture_v3('seat_420_with_contributors'))
    boxes = await _boxes(swarm_seat_summary=summary)
    assert _lines(boxes['work']) == ['WORK', '8.1 h', '1.2M tokens']
    assert _lines(boxes['accepted']) == ['ACCEPTED JOBS', '190 of 204', '93.1 %']
    assert _lines(boxes['rank']) == ['RANK', '#6 of 99']


@pytest.mark.parametrize('width', PINS)
async def test_owner_hero_example_is_an_explicit_synthetic_layout_case(width):
    boxes = await _boxes(size=(width,9),
                         swarm_seat_summary={**SUMMARY, 'accepted':242, 'attempts':280, 'win_rate':242/280},
                         swarm_seat_contrib={**CONTRIB, 'turns':3063, 'wall_clock_s':11.9*3600,
                                             'output_tokens':1_700_000, 'rank':8, 'ranked_of':306})
    assert _lines(boxes['work']) == ['WORK', '11.9 h', '1.7M tokens']
    assert _lines(boxes['accepted']) == ['ACCEPTED JOBS', '242 of 280', '86.4 %']
    assert _lines(boxes['rank']) == ['RANK', '#8 of 306']
    assert 'as of' not in '\n'.join(boxes.values())


def _inner_rows(box: str) -> list[str]:
    """A box's rows between its borders, blank rows kept."""
    rows = [row.strip().strip("│┌┐└┘─").strip() for row in box.split("\n")]
    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()
    return rows


async def test_two_line_boxes_have_a_blank_row_between_their_lines_like_status():
    """Owner, 2026-09-25: label, blank, line 1, blank, line 2 -- STATUS's rhythm.
    SEAT's blank line 2 carries only a rare selection word (most active, never paired)."""
    boxes = await _boxes(swarm_seat_rank_delta=2,
                         swarm_seat_selected=dict(SELECTED, selected_by="saved"))
    for key in ("seat", "work", "accepted", "rewards", "rank"):
        rows = _inner_rows(boxes[key])
        assert len(rows) == 5 and rows[1] == "" and rows[3] == "", (key, rows)
        assert all(rows[i] for i in (0, 2, 4)), (key, rows)


async def test_seat_selection_word_takes_the_blank_line_above_the_agent():
    most = _inner_rows(await _box_text(BOX_IDS["seat"],
                       swarm_seat_selected=dict(SELECTED, selected_by="most_active")))
    assert most[2:] == ["IDMD #420", "most active", "agent 50939"], most


@pytest.mark.parametrize('working,cap,expected', [
    # live #420, 2026-09-26: oracle jobs exceed maxConcurrency. F-S4: the word
    # leads, so the over-capacity count drops its own "working" (never twice).
    (9, 1, '● working · ⚙ 9'),
    (1, 1, '● working · ⚙ 1 of 1'), (2, 4, '● working · ⚙ 2 of 4'),
])
async def test_status_drops_capacity_when_working_exceeds_it(working, cap, expected):
    text = await _box_text(BOX_IDS['status'], swarm_seat_live={
        'live': True, 'live_state': 'working', 'working': working, 'max_concurrency': cap})
    assert _lines(text)[1] == expected


@pytest.mark.parametrize('working,cap,expected,word', [
    (1, 3, '● working · ⚙ 1 of 3', True),
    # The sweep's worst case: 30 cells against STATUS's 24 at the pin. The word
    # goes and the counts stay whole in green -- never "⚙ 99,999 of…".
    (99_999, 99_999, '⚙ 99,999 of 99,999', False),
])
async def test_status_working_word_yields_to_whole_counts_at_the_pin(working, cap, expected, word):
    async with _Themed().run_test(size=(SURF_AGENT_FULL_LAYOUT_COLUMNS, 9)) as pilot:
        pilot.app.query_one(SurfSwarmAgentHero).update_data(**_merged(dict(swarm_seat_live={
            'live': True, 'live_state': 'working', 'working': working, 'max_concurrency': cap})))
        await pilot.pause()
        await pilot.pause()
        region = pilot.app.query_one('#' + BOX_IDS['status']).region
        lines = [''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        content = [line[region.x:region.right].strip(' │') for line in lines[region.y:region.bottom]]
        assert expected in content, content
        assert (WORKING_LINE in '\n'.join(content)) is word
        assert not any('…' in line for line in content), content
