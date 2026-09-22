"""SEAT details measured from composited output, including owner metadata."""
import copy
import inspect
import re
from pathlib import Path
import pytest
from textual.app import App
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_summary_from_seat
from maxpane_dashboard.widgets.fmt import hhmm, mmdd
from maxpane_dashboard.widgets.surf.swarm_seat_verdicts import SurfSwarmSeatVerdicts, ROW_IDS, PANEL_MAX_WIDTH
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.surf_compositing import composite_lines
from tests.widgets.address_probe import LinkRecorder, icon_targets, link_targets

SEAT = swarm_seat_capture("seat_420")
SUMMARY = seat_summary_from_seat(SEAT)
SELECTED = {"token_id":420, "agent_id":SUMMARY["agent_id"], "selected_by":"saved"}
SIZE=(PANEL_MAX_WIDTH,16)
async def _record(**kwargs):
    data=dict(swarm_seat_summary=SUMMARY,swarm_seat_selected=SELECTED,swarm_seat_state="ok",swarm_seat_as_of_hhmm="04:06")
    data.update(kwargs)
    return "\n".join(await composite_lines(SurfSwarmSeatVerdicts,SIZE,css_path=CSS_PATH,**data))

def test_signature():
    params=inspect.signature(SurfSwarmSeatVerdicts.update_data).parameters
    assert tuple(k for k,p in params.items() if k!="self" and p.kind!=p.VAR_KEYWORD)==SWARM_WIDGET_SIGNATURES["SurfSwarmSeatVerdicts"]

async def test_lifetime_details_and_identity_are_visible():
    text=await _record()
    for word in ("IDMD #420",f"agent {SUMMARY['agent_id']}","owner", "online ●", "runtime", "daemon", "device", "attempts", "won", "of attempts", "reviewed", "feedback", "submitted", "queued", "score", "by role"):
        assert word in text, (word,text)
    assert f"{mmdd(SUMMARY['paired_ts'])} {hhmm(SUMMARY['paired_ts'])}" in text
    assert f"{SUMMARY['win_rate']*100:.1f} %" in text
    assert "SEAT · as of 04:06" in text and "SEAT RECORD" not in text

async def test_four_digit_feedback_counts_are_whole():
    summary=dict(SUMMARY,review_status={"sent":80_001,"submitted":9_999,"queued":9_999})
    text=await _record(swarm_seat_summary=summary)
    assert "80,001 sent" in text and "9,999 submitted" in text and "9,999 queued" in text
    for line in text.splitlines():
        if any(word in line for word in ("feedback", "queued")):
            assert "…" not in line

async def test_null_daemon_empty_runtime_and_zero_attempts_are_real_negatives():
    seat=copy.deepcopy(swarm_seat_capture("seat_0"))
    seat.update(attempts=0,accepted=0,reviews=[],work=[])
    text=await _record(swarm_seat_summary=seat_summary_from_seat(seat))
    assert "not reported" in text and "runtime none" in text and "no attempts" in text
    assert "no scores yet" in text

async def test_missing_fields_are_unavailable_and_not_zero():
    text=await _record(swarm_seat_summary=dict(SUMMARY,daemon=None,devices=None,runtime=None,attempts=None,win_rate=None))
    assert "daemon unavailable" in text and "runtime unavailable" in text
    assert "0 attempts" not in text

async def test_long_roles_are_counted_and_hostile_text_is_sanitized():
    roles=[{"role":"[/x]implement","count":99999}]+[{"role":f"role{i}","count":9} for i in range(8)]
    text=await _record(swarm_seat_summary=dict(SUMMARY, roles=roles,runtime="[/x]PWNED "+"x"*80,daemon="[$success]daemon"))
    assert "PWNED" in text and "…" in text and "[/x]" not in text and "[$success]" not in text
    assert "role0 9 · +7 more" in text

@pytest.mark.parametrize("state,word",[("pending","Loading..."),("unknown_seat","#420 never paired"),(None,"unavailable"),("bad","unavailable")])
async def test_states_hide_stale_values(state,word):
    text=await _record(swarm_seat_state=state)
    assert word in text and "⧉" not in text and "submitted" not in text

async def test_no_args_rewrites_every_line():
    text="\n".join(await composite_lines(SurfSwarmSeatVerdicts,SIZE,css_path=CSS_PATH))
    assert text.count("unavailable")==len(ROW_IDS) and "Loading" not in text

class Linked(LinkRecorder,App):
    CSS_PATH=CSS_PATH
    def compose(self):
        yield SurfSwarmSeatVerdicts()

async def test_owner_retains_copy_icon_and_mainnet_explorer():
    async with Linked().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmSeatVerdicts).update_data(swarm_seat_summary=SUMMARY,swarm_seat_selected=SELECTED,swarm_seat_state="ok")
        await pilot.pause()
        icons=icon_targets(pilot.app)
        links=link_targets(pilot.app)
    assert [a for _,_,a in icons]==[SUMMARY["owner"]]
    assert {(x[2],x[3],x[4]) for x in links}=={("etherscan","address",SUMMARY["owner"])}

@pytest.mark.guard
def test_panel_fit_width_agrees_with_stylesheet():
    block=re.search(r"^SurfSwarmSeatVerdicts \{(.*?)\}",Path(CSS_PATH).read_text(),re.S|re.M)
    assert int(re.search(r"max-width:\s*(\d+)",block.group(1)).group(1))==PANEL_MAX_WIDTH


async def test_duplicate_review_entries_explanation_is_whole_and_only_shown_for_a_gap():
    summary = seat_summary_from_seat(swarm_seat_capture("seat_420_duplicated_reviews"))
    text = await _record(swarm_seat_summary=summary)
    assert "reviewed 197 submissions · 351 entries served" in text
    assert "entries served" not in await _record()


async def test_five_digit_review_entries_explanation_remains_whole():
    text = await _record(swarm_seat_summary=dict(SUMMARY, reviewed=55_555, review_entries=99_999))
    assert "reviewed 55,555 submissions · 99,999 entries served" in text


async def test_attempts_rate_shares_the_attempts_line_and_reviewed_stays_separate():
    summary = seat_summary_from_seat(swarm_seat_capture("seat_420_duplicated_reviews"))
    text = await _record(swarm_seat_summary=summary)
    assert "attempts 201 · won 190 (94.5 % of attempts)" in text
    reviewed = [line.strip() for line in text.splitlines() if "reviewed" in line]
    assert reviewed == ["reviewed 197 submissions · 351 entries served"]


async def test_missing_attempts_and_wins_remain_whole_without_redundant_rate():
    text = await _record(swarm_seat_summary=dict(SUMMARY, attempts=None, accepted=None, win_rate=None))
    assert "attempts unavailable · won unavailable" in text
    assert "…" not in next(line for line in text.splitlines() if "attempts" in line)
