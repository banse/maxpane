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
SIZE=(PANEL_MAX_WIDTH,24)
async def _record(**kwargs):
    data=dict(swarm_seat_summary=SUMMARY,swarm_seat_selected=SELECTED,swarm_seat_state="ok",swarm_seat_as_of_hhmm="04:06")
    data.update(kwargs)
    return "\n".join(await composite_lines(SurfSwarmSeatVerdicts,SIZE,css_path=CSS_PATH,**data))

def test_signature():
    params=inspect.signature(SurfSwarmSeatVerdicts.update_data).parameters
    assert tuple(k for k,p in params.items() if k!="self" and p.kind!=p.VAR_KEYWORD)==SWARM_WIDGET_SIGNATURES["SurfSwarmSeatVerdicts"]

async def test_lifetime_details_and_identity_are_visible():
    text=await _record()
    for word in ("IDMD #420",f"agent {SUMMARY['agent_id']}","owner", "paired", "runtime", "daemon", "device", "attempts", "accepted", "of attempts", "reviewed", "feedback", "submitted", "queued", "score", "by role"):
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
    assert "role0 9 · role1 9 · +6 more" in text

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
    assert "attempts 201 · accepted 190 (94.5 % of attempts)" in text
    reviewed = [line.strip() for line in text.splitlines() if "reviewed" in line]
    assert reviewed == ["reviewed 197 submissions · 351 entries served"]


async def test_missing_attempts_and_wins_remain_whole_without_redundant_rate():
    text = await _record(swarm_seat_summary=dict(SUMMARY, attempts=None, accepted=None, win_rate=None))
    assert "attempts unavailable · accepted unavailable" in text
    assert "…" not in next(line for line in text.splitlines() if "attempts" in line)


async def test_five_digit_attempts_and_acceptance_rate_are_whole():
    text = await _record(swarm_seat_summary=dict(SUMMARY, attempts=99_999, accepted=9_999, win_rate=9_999/99_999))
    assert "attempts 99,999 · accepted 9,999 (10.0 % of attempts)" in text
    assert " won " not in text

CONTRIB=dict(listed=True,attempts=207,accepted=189,rejected=2,pending=16,turns=2189,
             wall_clock_s=29160,rank=4,ranked_of=101)
LIVE=dict(live=True,skills=30,profiles=['none','foundry'],platform='linux x64')

@pytest.mark.parametrize('state',['ok','pending',None])
async def test_contributors_never_borrow_seats_numbers_and_survive_seats_loss(state):
    text=await _record(swarm_seat_state=state,swarm_seat_contrib=CONTRIB,
                       swarm_board_as_of_hhmm='03:01',swarm_seat_live=LIVE,swarm_workers_as_of_hhmm='05:07')
    assert 'contributors 207 att · 189 acc · 2 rej · 16 pend' in text
    assert '2189 turns · 8.1 h · rank #4 of 101 · as of 03:01' in text
    assert 'skills' not in text and 'profiles' not in text
    assert 'workers as of 05:07' not in text
    if state!='ok':assert 'attempts 201' not in text and '⧉' not in text

@pytest.mark.parametrize('contrib,word',[(None,'unavailable'),({'listed':False},'not listed')])
async def test_contributor_absence_is_not_unavailability(contrib,word):
    text=await _record(swarm_seat_contrib=contrib)
    assert 'contributors '+word in text
    assert ('not listed' in text)==(word=='not listed')
    assert f"attempts {SUMMARY['attempts']}" in text

async def test_worker_metadata_has_no_seat_rendering_path():
    text=await _record(swarm_seat_live=dict(LIVE,profiles=['[/x]foundry'],platform='[$success]linux x64'))
    assert 'profiles' not in text and 'linux' not in text
    assert '[/x]' not in text and '[$success]' not in text
    missing=await _record(swarm_seat_summary=dict(SUMMARY,skills=777,profiles=['POISON'],platform='POISON'))
    assert 'workers' not in missing and 'POISON' not in missing and '777' not in missing


async def test_long_worker_metadata_stays_off_seat_while_contributor_facts_remain_whole():
    text=await _record(swarm_seat_live=dict(LIVE,profiles=["x"*64],platform="y"*64),
                       swarm_workers_as_of_hhmm="05:07",swarm_seat_contrib=CONTRIB,swarm_board_as_of_hhmm="03:01")
    assert "skills" not in text and "profiles" not in text
    assert "workers as of 05:07" not in text
    assert "contributors 207 att · 189 acc · 2 rej · 16 pend" in text


async def test_fix_wave_identity_and_pairing_share_one_composited_line():
    text = await _record()
    line = next(line.strip() for line in text.splitlines() if "IDMD #420" in line)
    assert line == f"IDMD #420 · agent {SUMMARY['agent_id']} · paired {mmdd(SUMMARY['paired_ts'])} {hhmm(SUMMARY['paired_ts'])}"
    assert "surf-swarm-verdicts-paired" not in ROW_IDS
    assert "online" not in text and "offline" not in text


async def test_fix_wave_feedback_statuses_share_one_composited_line():
    summary = dict(SUMMARY, review_status={"sent":80_001,"submitted":9_999,"queued":9_998})
    text = await _record(swarm_seat_summary=summary)
    line = next(line.strip() for line in text.splitlines() if "feedback" in line)
    assert line == "feedback 80,001 sent · 9,999 submitted · 9,998 queued"
    assert "surf-swarm-verdicts-queued" not in ROW_IDS
    assert sum("queued" in line for line in text.splitlines()) == 1


async def test_fix_wave_worker_metadata_is_absent_from_seat():
    text = await _record(swarm_seat_live=LIVE, swarm_workers_as_of_hhmm="05:07")
    assert "skills" not in text and "profiles" not in text and "linux" not in text
    assert "workers as of" not in text and "05:07" not in text


@pytest.mark.parametrize("width,one_line", [(63,False),(120,True)])
async def test_fix_wave_contributors_use_one_line_only_when_all_facts_fit(width,one_line):
    async with Linked().run_test(size=(width,24)) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatVerdicts)
        widget.styles.max_width = width
        widget.update_data(swarm_seat_summary=SUMMARY,swarm_seat_selected=SELECTED,swarm_seat_state="ok",
                           swarm_seat_contrib=CONTRIB,swarm_board_as_of_hhmm="03:01")
        await pilot.pause()
        rows = ["".join(segment.text for segment in strip).strip() for strip in pilot.app.screen._compositor.render_strips()]
        first = next(line for line in rows if "contributors 207" in line)
        tail = "2189 turns · 8.1 h · rank #4 of 101 · as of 03:01"
        if one_line:
            assert first == "contributors 207 att · 189 acc · 2 rej · 16 pend · " + tail
            assert not widget.query_one("#surf-swarm-verdicts-contributor-time").display
        else:
            assert first == "contributors 207 att · 189 acc · 2 rej · 16 pend"
            assert tail in rows
            assert widget.query_one("#surf-swarm-verdicts-contributor-time").display


@pytest.mark.parametrize('defect', ['selected-malformed', 'other-malformed'])
@pytest.mark.parametrize('stress', [False, True], ids=['v3', 'five-digit'])
async def test_i1_malformed_contributor_evidence_reaches_agent_composite_at_pin(tmp_path, defect, stress):
    from tests.data.test_surf_manager_swarm import _FakeSwarm, _landed
    from tests.screens.test_surf_swarm_layout import _v3_agent_payload
    from tests.screens.test_surf_screen import _surf_app, _region_text

    swarm = _FakeSwarm()
    if stress:
        selected = next(row for row in swarm.contributors['contributors'] if row['tokenId'] == '420')
        selected.update(attempts=99999, accepted=55555, rejected=11111, pending=33333, turns=99999, wallClockMs='99999000')
    victim = next(row for row in swarm.contributors['contributors']
                  if (row['tokenId'] == '420') == (defect == 'selected-malformed'))
    victim['turns'] = None
    manager, keys = await _landed(tmp_path, swarm, seat=420)
    try:
        payload = _v3_agent_payload()
        for key in ('swarm_board_summary', 'swarm_board_rows', 'swarm_seat_contrib',
                    'swarm_board_as_of_hhmm', 'swarm_seat_live', 'swarm_workers_as_of_hhmm'):
            payload[key] = keys[key]
        async with _surf_app(payload).run_test(size=(138, 32)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.press('a')
            await pilot.pause()
            panel = pilot.app.screen.query_one(SurfSwarmSeatVerdicts)
            text = _region_text(pilot.app, panel)
            if defect == 'selected-malformed':
                assert 'contributors unavailable' in text
                assert 'not listed' not in text
            else:
                assert keys['swarm_seat_contrib']['rank'] is None
                assert keys['swarm_seat_contrib']['ranked_of'] == len({row['tokenId'] for row in swarm.contributors['contributors']})
                expected = 'contributors 99999 att · 55555 acc · 11111 rej · 33333 pend' if stress else 'contributors 207 att · 189 acc · 2 rej · 16 pend'
                assert expected in text
                rank_line = next(line for line in text.splitlines() if 'rank' in line)
                assert 'as of ' + keys['swarm_board_as_of_hhmm'] in rank_line
                assert 'rank unavailable' in rank_line and '…' not in rank_line
    finally:
        await manager.close()
