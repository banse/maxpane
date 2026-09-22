"""The AGENT body's hero: SEAT · ACCEPTED · REVIEWED · SCORE · COLLAB · STATUS.

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
    WORKING_GLYPH,
    SurfSwarmAgentHero,
    SurfSwarmAgentHeroBox,
)
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmAgentHero"]

SEAT_420 = swarm_seat_capture("seat_420")
SEAT_0 = swarm_seat_capture("seat_0")
SUMMARY = seat_summary_from_seat(SEAT_420)
SELECTED = {"token_id": int(SEAT_420["tokenId"]), "agent_id": str(SEAT_420["agentId"]),
            "selected_by": "saved"}
AS_OF = "04:06"
#: The AGENT body's own column pin; every ``_box_text`` renders here by default.
SIZE = (SURF_AGENT_FULL_LAYOUT_COLUMNS, 9)
#: The two widths the hero has to be whole at: its body's pin and the app's.
PINS = (SURF_AGENT_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS)
STAT_BOXES = ("accepted", "reviewed", "win_rate", "collab")


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
    # Six: the five stat boxes and STATUS's accepted line. STATUS's title
    # no longer names a workers clock (owner 2026-09-22), so no seventh.
    assert bare.count("unavailable") == 6 and "Loading" not in bare
    assert NO_SEAT_LINE in bare
    none = "\n".join(await composite_lines(SurfSwarmAgentHero, SIZE, css_path=CSS_PATH,
                                           **{k: None for k in SIGNATURE}))
    assert none == bare


def test_the_box_class_is_its_own_type_selector_and_the_six_boxes_are_named():
    assert SurfSwarmAgentHero.BOX_CLASS is SurfSwarmAgentHeroBox
    assert len(BOX_IDS) == 6 == len(SurfSwarmAgentHero.BOXES)
    labels = [label for _id, label in SurfSwarmAgentHero.BOXES]
    assert labels == ["SEAT", "ACCEPTED", "ACCEPT RATE", "REVIEWED", "COLLAB", "STATUS"]


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
    status = SUMMARY["review_status"]
    pending = status["submitted"] + status["queued"]
    assert f"IDMD #{SELECTED['token_id']}" in boxes["seat"]
    assert f"agent {SELECTED['agent_id']}" in boxes["seat"] and "saved" in boxes["seat"]
    assert f"{SUMMARY['accepted']} of {SUMMARY['attempts']}" in boxes["accepted"]
    # Q-M: pending is a subset of the reviews, never added on top -- and on
    # a line of its own under the total (see the five-digit test below).
    assert _lines(boxes["reviewed"])[-2:] == [str(SUMMARY["reviewed"]), f"{pending} pending"]
    assert f"+{pending}" not in boxes["reviewed"]
    assert f"{SUMMARY['win_rate']*100:.1f} %" in boxes["win_rate"]
    assert "of attempts" in boxes["win_rate"]
    assert f"{SUMMARY['collaborators']} seats" in boxes["collab"]
    assert f"{WORKING_GLYPH} 0 of 2" in boxes["status"]
    assert f"accepted {mmdd(SUMMARY['last_won_ts'])} {hhmm(SUMMARY['last_won_ts'])}" in boxes["status"]
    assert f"as of {AS_OF}" in boxes["accepted"]
    for key, text in boxes.items():
        assert "…" not in text and "unavailable" not in text, (width, key, text)


@pytest.mark.parametrize("width", PINS)
async def test_the_largest_seat_fits_whole_and_reads_offline(width):
    summary = seat_summary_from_seat(SEAT_0)
    selected = {"token_id": 0, "agent_id": str(SEAT_0["agentId"]), "selected_by": "most_active"}
    boxes = await _boxes(size=(width, 9), swarm_seat_selected=selected,
                         swarm_seat_summary=summary, swarm_seat_live={"live":False,"live_state":"offline"})
    status = summary["review_status"]
    assert _lines(boxes["reviewed"])[-2:] == [
        str(summary["reviewed"]), f"{status['submitted'] + status['queued']} pending"]
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
    assert "saved" in boxes["seat"] and "Loading" not in boxes["seat"]
    for key in STAT_BOXES:
        assert "Loading..." in boxes[key], (key, boxes[key])
    # SUMMARY (seat #420's numbers) was passed in and must not reach a pixel.
    whole = "\n".join(boxes.values())
    assert f"{SUMMARY['accepted']} of" not in whole and "pending" not in whole


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
    """The fix-round finding: ``1,202 · 13 pending`` on one line was cut to
    ``pend…`` at the AGENT pin, where the hero has no ``‹``. REVIEWED paints
    the total over the pending count, so ``99,999`` / ``1,998 pending`` fit
    whole, and so do ACCEPTED's ``9,999 of 99,999`` and SCORE's count."""
    boxes = await _boxes(size=(width, 9), swarm_seat_summary=FIVE_DIGIT)
    assert _lines(boxes["reviewed"])[-2:] == ["99,999", "1,998 pending"], boxes["reviewed"]
    assert "9,999 of 99,999" in boxes["accepted"]
    assert "of attempts" in boxes["win_rate"]
    assert "9,999 seats" in boxes["collab"]
    for key, text in boxes.items():
        assert "…" not in text, (width, key, text)


# -- zeros, missing fields and malformed payloads --------------------------------------


async def test_a_zero_record_renders_zeros_not_unavailable():
    zero = _folded(attempts=0, accepted=0, work=[], reviews=[], collaborators=[])
    boxes = await _boxes(swarm_seat_summary=zero)
    assert "0 of 0" in boxes["accepted"]
    assert _lines(boxes["reviewed"])[-2:] == ["0", "0 pending"]
    assert "no attempts" in boxes["win_rate"]
    assert "0 seats" in boxes["collab"]
    for key in ("accepted", "reviewed", "win_rate", "collab"):
        assert "unavailable" not in boxes[key], (key, boxes[key])


async def test_a_field_the_source_did_not_carry_is_unavailable_in_its_own_box_only():
    """``attempts`` missing from the payload folds to ``None``: ACCEPTED says
    ``unavailable`` -- never ``12 of 0`` -- and the other boxes keep their numbers."""
    missing = _folded(attempts=_DROP)
    assert missing["attempts"] is None and missing["accepted"] == SUMMARY["accepted"]
    boxes = await _boxes(swarm_seat_summary=missing)
    assert "unavailable" in boxes["accepted"]
    assert " of 0" not in boxes["accepted"] and " of " not in boxes["accepted"]
    assert str(SUMMARY["reviewed"]) in _lines(boxes["reviewed"])
    assert f"{WORKING_GLYPH} 0 of 2" in boxes["status"]


async def test_a_missing_status_split_shows_dashes_for_pending_not_zero():
    split_less = dict(SUMMARY, review_status=None)
    text = await _box_text(BOX_IDS["reviewed"], swarm_seat_summary=split_less)
    assert _lines(text)[-2:] == [str(SUMMARY["reviewed"]), "-- pending"]
    assert "0 pending" not in text


async def test_malformed_payloads_land_on_unavailable_not_a_crash():
    whole = await _hero(swarm_seat_summary="garbage")
    assert "unavailable" in whole
    seat = await _box_text(BOX_IDS["seat"], swarm_seat_selected=["not", "a", "dict"])
    assert "unavailable" in seat
    typed = dict(SUMMARY, accepted="lots", online="yes")
    boxes = await _boxes(swarm_seat_summary=typed,swarm_seat_live={"live":"yes"})
    assert "unavailable" in boxes["accepted"] and "unavailable" in boxes["status"]
    assert f"{SUMMARY['collaborators']} seats" in boxes["collab"]


# -- SEAT ------------------------------------------------------------------------------


@pytest.mark.parametrize("width", PINS)
async def test_the_three_selected_by_phrasings(width):
    saved = await _box_text(BOX_IDS["seat"], size=(width, 9),
                            swarm_seat_selected=dict(SELECTED, selected_by="saved"))
    assert "saved" in saved and "…" not in saved
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


@pytest.mark.parametrize("accepted,expected", [(0, "none accepted yet"), (3, "accepted unavailable"), (None, "accepted unavailable")])
async def test_status_distinguishes_no_wins_from_missing_win_timestamp(accepted, expected):
    text = await _box_text(BOX_IDS["status"], swarm_seat_summary=dict(SUMMARY, accepted=accepted, last_won_ts=None))
    assert expected in text and "??" not in text


async def test_acceptance_words_replace_retired_win_words_in_composited_output():
    boxes = await _boxes()
    text = "\n".join(boxes.values())
    assert "ACCEPT RATE" in text
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

async def test_seats_clock_stays_with_accepted_and_status_names_no_clock():
    # Owner 2026-09-22: the STATUS title lost "workers as of HH:MM".
    boxes=await _boxes(size=(180,9),swarm_seat_live=LIVE,swarm_workers_as_of_hhmm='05:07')
    assert 'as of 04:06' in boxes['accepted']
    assert _lines(boxes['status'])[0] == 'STATUS'
    assert '05:07' not in boxes['status'] and '04:06' not in boxes['status']


@pytest.mark.parametrize('live_state,word,color',[
    ('working',WORKING_GLYPH,2),('idle','idle',None),('offline','offline',1),
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
        if color is not None:assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
        else:
            plain_y=next(y for y in range(region.y,region.bottom) if 'accepted ' in lines[y][region.x:region.right])
            plain_x=lines[plain_y].index('accepted ',region.x)
            assert style.color!=pilot.app.screen.get_style_at(plain_x,plain_y).color
        content='\n'.join(line[region.x:region.right] for line in lines[region.y:region.bottom])
        assert 'as of' not in content and 'accepted '+mmdd(SUMMARY['last_won_ts']) in content
        if live_state in ('idle','paused',None):assert f'{WORKING_GLYPH} 0 of 8' in content
        assert 'working' not in content
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
    for live,expected in ((idle,'idle'),(unknown,'unavailable')):
        text=await _box_text(BOX_IDS['status'],swarm_seat_live=live)
        assert _lines(text)[1].startswith(expected),text
        assert ('idle' in text)==(expected=='idle')
        assert f'{WORKING_GLYPH} 0 of ' in text


async def test_polish_accepted_reviewed_and_rate_have_composited_emphasis():
    async with _Themed().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmAgentHero).update_data(**_merged({}))
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        for box_key,word,color in (('accepted',str(SUMMARY['accepted']),2),('accepted',str(SUMMARY['attempts']),None),
                                   ('reviewed',str(SUMMARY['reviewed']),None),('win_rate',f"{SUMMARY['win_rate']*100:.1f}",None)):
            region=pilot.app.query_one('#'+BOX_IDS[box_key]).region
            y=next(y for y in range(region.y,region.bottom) if word in lines[y][region.x:region.right])
            style=pilot.app.screen.get_style_at(lines[y].index(word,region.x),y)
            assert style.bold,(box_key,word,style)
            if color is not None:assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
