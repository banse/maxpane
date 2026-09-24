"""RECORD -- the selected seat's accepted work, lifetime, newest first (plan WP4).

Composited assertions only. Rows are **folded** from the committed ``/seats``
captures by ``data/surf_swarm.seat_work_rows`` (the manager's own fold), and
every expected value is read off that fold, never hand-typed. The per-class
contract is imposed against ``SWARM_WIDGET_SIGNATURES`` (flipped in WP5, which
also removed the two transitional parameters).
"""

from __future__ import annotations

import inspect
import re

from rich.color import Color
from textual.app import App

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_work_rows
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets import explorer as X
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS, NODE_TITLES
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_record import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    JOB_COLS,
    NODE_COLS,
    ANSWER_MIN_COLS,
    TIGHT_WIDTH,
    SurfSwarmSeatRecord,
)
from tests.surf_swarm_fixtures import swarm_capture_v5, swarm_seat_capture
from tests.widgets.address_probe import link_targets
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]

ROWS_420 = seat_work_rows(swarm_seat_capture("seat_420"))
ROWS_0 = seat_work_rows(swarm_seat_capture("seat_0"))
NEWEST = ROWS_420[0]
AS_OF = "04:06"
#: Wide enough for every column at ``full`` plus room for the answer; tall
#: enough for #420's twelve rows, the header, the title and a footer.
SIZE = (180, 20)


def _job(row) -> str:
    return row["job_id"][:JOB_COLS]


def _node(row) -> str:
    """The short word RECORD's node column shows for a known key."""
    return NODE_TITLES[row["node_key"]].lower()


def test_the_folded_rows_carry_exactly_the_frozen_shape():
    assert ROWS_420 and ROWS_0
    for row in ROWS_420 + ROWS_0:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_work_rows"]


async def _record(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_work_rows", ROWS_420)
    kwargs.setdefault("swarm_seat_state", "ok")
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatRecord, size, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_signature():
    sig = inspect.signature(SurfSwarmSeatRecord.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SIGNATURE
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_a_splatted_key_outside_the_signature_is_never_painted():
    """The screen splats the whole payload; ``swarm_network`` left RECORD's
    signature in the WP5 flip and must not reach the panel through ``**_kwargs``."""
    plain = await _record()
    noisy = await _record(swarm_network="SEPOLIA")
    assert plain == noisy


# -- the four seat states stay distinct ----------------------------------------------


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatRecord, SIZE))
    assert "unavailable" in bare and "Loading" not in bare and EMPTY_LINE not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatRecord, SIZE, **{k: None for k in SIGNATURE},
    ))
    assert "unavailable" in none and EMPTY_LINE not in none


async def test_a_failed_read_is_unavailable_and_never_the_real_empty_sentence():
    """State ``None`` (read failed, no last-good) -- even beside ``[]`` rows."""
    for rows in (None, [], ROWS_420):
        text = "\n".join(await _record(swarm_seat_work_rows=rows, swarm_seat_state=None))
        assert "unavailable" in text, rows
        assert EMPTY_LINE not in text and _job(NEWEST) not in text


async def test_ok_with_empty_rows_is_the_real_empty_sentence():
    text = "\n".join(await _record(swarm_seat_work_rows=[]))
    assert EMPTY_LINE in text and "unavailable" not in text


async def test_ok_with_unread_rows_is_unavailable():
    text = "\n".join(await _record(swarm_seat_work_rows=None))
    assert "unavailable" in text and EMPTY_LINE not in text


async def test_unknown_seat_says_never_paired_not_the_empty_sentence():
    text = "\n".join(await _record(swarm_seat_work_rows=[], swarm_seat_state="unknown_seat"))
    assert NEVER_PAIRED_WORDS in text
    assert EMPTY_LINE not in text and "unavailable" not in text


async def test_pending_says_loading_and_paints_no_row():
    text = "\n".join(await _record(swarm_seat_state="pending"))
    assert "Loading" in text
    assert _job(NEWEST) not in text and "unavailable" not in text and EMPTY_LINE not in text


async def test_a_malformed_state_is_unavailable():
    text = "\n".join(await _record(swarm_seat_state="bogus"))
    assert "unavailable" in text and _job(NEWEST) not in text


# -- rows ---------------------------------------------------------------------------


async def test_the_defect_seat_shows_its_twelve_accepted_jobs_newest_first():
    lines = await _record()
    ys = [next(i for i, l in enumerate(lines) if _job(row) in l) for row in ROWS_420]
    assert len(ys) == len(ROWS_420) == swarm_seat_capture("seat_420")["accepted"]
    assert ys == sorted(ys), "the fold's order (newest first) is kept, never re-sorted"
    assert "older" not in "\n".join(lines), "twelve rows are under the cap"


async def test_a_work_row_renders_every_column():
    lines = await _record()
    row = _row_with(lines, _job(NEWEST))
    assert hhmm(NEWEST["accepted_ts"]) in row
    assert NEWEST["job_id"][JOB_COLS:JOB_COLS + 4] not in row
    cells = row.split()
    assert cells[3] == _node(NEWEST) and NEWEST["node_key"] not in row
    assert NEWEST["job_state"] in row
    assert "not read" in row and NEWEST["objective"] not in row
    text = "\n".join(lines)
    assert "RECORD" in text and f"as of {AS_OF}" in text
    header = _row_with(lines, "answer").split()
    assert header == ["when", "job", "node", "state", "model", "took", "panel", "tok", "answer"]


async def test_the_title_has_no_blank_row_under_it():
    """Owner, 2026-09-22: RECORD alone drops ``PanelBase``'s blank row."""
    lines = await _record()
    y = next(i for i, line in enumerate(lines) if "RECORD" in line)
    assert lines[y + 1].split()[:3] == ["when", "job", "node"], lines[y:y + 2]


async def test_every_known_node_key_shows_its_card_word_and_an_unknown_one_is_fitted():
    rows = [dict(NEWEST, job_id=f"{i:08x}", node_key=key)
            for i, key in enumerate([*NODE_TITLES, "integrate_everything"])]
    lines = await _record(swarm_seat_work_rows=rows)
    for row in rows[:-1]:
        assert _row_with(lines, _job(row)).split()[3] == NODE_TITLES[row["node_key"]].lower()
    unknown = _row_with(lines, _job(rows[-1])).split()[3]
    assert unknown == "integ…" and len(unknown) == NODE_COLS


async def _record_links(rows):
    from textual.app import App as _App

    class _A(_App):
        def compose(self):
            yield SurfSwarmSeatRecord()

    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=rows, swarm_seat_state="ok",
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        painted = ["".join(s.text for s in strip)
                   for strip in pilot.app.screen._compositor.render_strips()]
        return painted, link_targets(pilot.app)


async def test_a_job_id_links_its_imd_explorer_page_on_every_shown_cell():
    painted, links = await _record_links([NEWEST])
    y = next(i for i, line in enumerate(painted) if _job(NEWEST) in line)
    x = painted[y].index(_job(NEWEST))
    cells = [t for t in links if t[1] == y]
    assert [t[0] for t in cells] == list(range(x, x + JOB_COLS)), "the whole shown id, no more"
    url = f"https://explorer.imd.fun/jobs/{NEWEST['job_id']}"
    assert {t[2:] for t in cells} == {("imd", "job", NEWEST["job_id"], url)}
    assert X.is_job_id(NEWEST["job_id"])


async def test_a_job_id_that_is_not_a_canonical_uuid_is_shown_but_never_linked():
    rows = [dict(NEWEST, job_id=bad) for bad in
            ("day1abcd-not-a-uuid", NEWEST["job_id"].upper(), "../../x" + NEWEST["job_id"][7:])]
    painted, links = await _record_links(rows)
    assert links == []
    assert any("day1abc…" in line for line in painted)


async def test_a_failed_attempt_writes_its_read_answer_in_red():
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatRecord()

    rows = [dict(NEWEST, job_id="0000aaaa", work_status="failed", answer_state="read",
                 answer="wrote outside the task"),
            dict(NEWEST, job_id="0000bbbb", work_status="rejected", answer_state="read",
                 answer="check passes with ok"),
            dict(NEWEST, job_id="0000cccc", work_status="failed", answer_state="not_read"),
            dict(NEWEST, job_id="0000dddd", work_status="failed", answer_state="garbled")]
    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=rows, swarm_seat_state="ok",
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        painted = ["".join(s.text for s in strip)
                   for strip in pilot.app.screen._compositor.render_strips()]
        theme = pilot.app.ansi_theme
        red = Color.parse("red").get_truecolor(theme)

        def colour(word):
            y = next(i for i, line in enumerate(painted) if word in line)
            return pilot.app.screen.get_style_at(painted[y].index(word), y).color.get_truecolor(theme)

        assert colour("wrote outside") == red
        assert colour("not read") != red, "F65: an unread word keeps its own style"
        assert colour("unavailable") == Color.parse("yellow").get_truecolor(theme), \
            "F65: a could-not-read answer stays yellow on a failed row"
        assert colour("check passes") != red, "only failed, never rejected"



async def test_the_answer_is_clipped_with_an_ellipsis_and_the_title_says_widen():
    long = dict(NEWEST, answer_state="read", answer="answer "*100)
    lines = await _record(swarm_seat_work_rows=[long])
    row = _row_with(lines, _job(NEWEST))
    assert long["answer"] not in row and row.rstrip().endswith("…")
    assert "‹" in "\n".join(lines)
    short = [dict(NEWEST, answer_state="read", answer="built a hook")]
    text = "\n".join(await _record(swarm_seat_work_rows=short))
    assert "built a hook" in text and "‹" not in text, "an answer that fits raises no hint"


async def test_the_state_word_is_coloured_on_the_raw_word():
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatRecord()

    rows = [NEWEST, dict(ROWS_420[1], job_state="failed")]
    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=rows, swarm_seat_state="ok",
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        painted = ["".join(seg.text for seg in strip) for strip in strips]
        y_c = next(i for i, r in enumerate(painted) if _job(rows[0]) in r)
        y_f = next(i for i, r in enumerate(painted) if _job(rows[1]) in r)
        x_c = painted[y_c].index("completed")
        x_f = painted[y_f].index("failed")
        theme = pilot.app.ansi_theme
        done = pilot.app.screen.get_style_at(x_c, y_c).color.get_truecolor(theme)
        failed = pilot.app.screen.get_style_at(x_f, y_f).color.get_truecolor(theme)
        assert done == Color.parse("green").get_truecolor(theme)
        assert failed == Color.parse("red").get_truecolor(theme)


async def test_a_hostile_answer_and_node_key_render_literally_and_never_raise():
    hostile = dict(NEWEST, answer_state="read", answer="[/x]PWNED answer", node_key="[/y]NODE",
                   role="[$error]", job_state="[bold]")
    lines = await _record(swarm_seat_work_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED answer" in text and "NODE" in text
    assert "[" not in text and "]" not in text


async def test_a_malformed_row_field_dashes_and_a_non_dict_row_is_skipped():
    bad = dict(NEWEST, accepted_ts="yesterday", node_key=None, objective=None, job_id=7)
    lines = await _record(swarm_seat_work_rows=[bad, "garbage", ROWS_420[1]])
    row = _row_with(lines, "??:??")
    assert row.count("--") >= 2
    assert _job(ROWS_420[1]) in "\n".join(lines)


async def test_rows_past_the_cap_are_counted_as_older():
    """#0 has 26 accepted jobs; a cap-breaking list is the fold repeated."""
    rows = (ROWS_0 * 2)[: SurfSwarmSeatRecord.ROW_CAP + 5]
    lines = await _record((130, 60), swarm_seat_work_rows=rows)
    painted = [l for l in lines if "completed" in l]
    assert len(painted) == SurfSwarmSeatRecord.ROW_CAP == 40
    assert "+5 older" in "\n".join(lines)
    exact = await _record((130, 60), swarm_seat_work_rows=rows[: SurfSwarmSeatRecord.ROW_CAP])
    assert "older" not in "\n".join(exact)


# -- tiers (provisional; WP6 measures) ------------------------------------------------


def test_the_tier_thresholds_descend():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert ANSWER_MIN_COLS > 0


async def test_one_below_full_sheds_tok_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    row = [dict(NEWEST, answer_state="read", answer="fits")]
    full_lines = await _record((FULL_WIDTH + gutter, 12), swarm_seat_work_rows=row)
    compact_lines = await _record((FULL_WIDTH + gutter - 1, 12), swarm_seat_work_rows=row)
    full_header = _row_with(full_lines, "when").split()
    compact_header = _row_with(compact_lines, "when").split()
    assert "tok" in full_header and "‹" not in "\n".join(full_lines)
    assert "tok" not in compact_header and "‹" in "\n".join(compact_lines)
    assert "answer" in compact_header, "compact keeps the answer"


async def test_one_below_compact_sheds_the_answer():
    gutter = SwarmTableBase.GUTTER_COLS
    lines = await _record((COMPACT_WIDTH + gutter - 1, 12), swarm_seat_work_rows=[NEWEST])
    header = _row_with(lines, "when").split()
    assert "answer" not in header and "‹" in "\n".join(lines)
    assert _row_with(lines, _job(NEWEST)).split()[3] == _node(NEWEST)

async def test_dates_survive_midnight_and_launch_submission_are_not_columns():
    from maxpane_dashboard.widgets.fmt import mmdd
    rows = [dict(NEWEST, job_id=f"day{i}abcd", accepted_ts=1_758_456_000+i*86400,
                 launch="evm_project" if i else None, submission_hash="ab"*32) for i in range(2)]
    text = "\n".join(await _record(size=(180,12), swarm_seat_work_rows=rows))
    assert mmdd(rows[0]["accepted_ts"]) != mmdd(rows[1]["accepted_ts"])
    for row in rows:
        assert f"{mmdd(row['accepted_ts'])} {hhmm(row['accepted_ts'])}" in text
    # Owner, 2026-09-22: launch and sub were hidden so the answer gets the room.
    assert "launch" not in text and "sub" not in text.split()
    assert "evm_project" not in text and "abababab" not in text
    assert "⧉" not in text


import pytest


@pytest.mark.parametrize('state,word',[
    ('read','Built the artifact.'),('not_read','not read'),('unavailable','unavailable'),
    ('not_served','not served'),('no_reply','no reply'),
])
async def test_polish_answer_states_and_same_read_usage(state,word):
    row=dict(NEWEST, answer_state=state,answer='Built the artifact.',model='claude-sonnet-5',took_s=420,
             objective='OBJECTIVE MUST NOT PAINT',launch='evm_project')
    lines=await _record((200,12),swarm_seat_work_rows=[row])
    header=_row_with(lines,'when').split()
    assert header==['when','job','node','state','model','took','panel','tok','answer']
    line=_row_with(lines,_job(row))
    assert word in line and 'OBJECTIVE MUST NOT PAINT' not in '\n'.join(lines)
    if state in ('read','no_reply'):
        assert 'sonnet 5' in line and '7m' in line
    else:
        assert 'sonnet 5' not in line and '7m' not in line and line.count('—')==3


@pytest.mark.parametrize('seconds,expected',[(420,'7m'),(3840,'1h 04m'),(0,'<1m'),(0.1,'<1m'),(59.99,'<1m'),(60,'1m'),(None,'—')])
async def test_polish_duration_and_missing_model(seconds,expected):
    row=dict(NEWEST,answer_state='read',answer='Done.',model=None,took_s=seconds,launch='evm_project')
    line=_row_with(await _record((200,12),swarm_seat_work_rows=[row]),_job(row))
    assert re.search(r'(?<!\S)' + re.escape(expected) + r'(?!\S)', line), line
    assert line.count('—')==(3 if seconds is None else 2)


async def test_polish_answer_sanitization_and_actual_clipping_drive_widen():
    row=dict(NEWEST,answer_state='read',answer='[/x]'*100+'界'*250,model='[$success]model',took_s=3840)
    text='\n'.join(await _record((200,12),swarm_seat_work_rows=[row]))
    assert '界' in text and '…' in text and '‹' in text and '[/x]' not in text
    row['answer']='[/x]'*100+'fits …'
    text='\n'.join(await _record((200,12),swarm_seat_work_rows=[row]))
    assert 'fits …' in text and '‹' not in text and '[$success]' not in text


async def test_polish_answer_unavailable_yellow_and_other_states_dim_in_composite():
    class _A(App):
        def compose(self):yield SurfSwarmSeatRecord()
    rows=[dict(NEWEST,job_id=f'{i:08x}',answer_state=state,answer=None,model=None,took_s=None)
          for i,state in enumerate(('not_read','unavailable','not_served','no_reply'))]
    async with _A().run_test(size=(200,12)) as pilot:
        widget=pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=rows,swarm_seat_state='ok')
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        colors=[]
        for word in ('not read','unavailable','not served','no reply'):
            y=next(i for i,line in enumerate(lines) if word in line)
            style=pilot.app.screen.get_style_at(lines[y].index(word),y)
            colors.append(style.color)
            if word=='unavailable':
                assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[3]
            else:
                # Zebra backgrounds alter the resolved dim RGB per row. Compare
                # against the plain job cell on that same composited row.
                job=rows[('not read','unavailable','not served','no reply').index(word)]['job_id']
                assert style.color!=pilot.app.screen.get_style_at(lines[y].index(job),y).color


async def test_polish_committed_hostile_submission_reaches_record_safely():
    from tests.surf_swarm_fixtures import swarm_capture_v4
    from maxpane_dashboard.data.surf_swarm import submission_answer,enrich_work_rows
    payload=swarm_capture_v4('submissions_hostile')
    item=next(item for item in payload['submissions'] if int(item['seat']['tokenId'])==420)
    point=submission_answer(payload,payload['jobId'],item['hash'],420)
    rows=enrich_work_rows([dict(NEWEST,job_id=payload['jobId'],submission_hash=item['hash'])],
                         {payload['jobId']:{item['hash']:dict(point,read_ts=1000.,terminal=True)}})
    text='\n'.join(await _record((200,12),swarm_seat_work_rows=rows))
    assert 'Created answer.json in report.md and result.txt' in text
    assert 'sonnet 5' in text and '<1m' in text and '…' in text and '‹' in text
    assert '[x]' not in text and '/Users/' not in text and '/home/' not in text and '/root/' not in text


async def test_every_attempt_dates_from_its_submission_on_the_v5_capture():
    """Since 2026-09-22 ``work[]`` also lists pending, rejected and failed
    attempts, which carry no ``acceptedAt``: RECORD dated them ``??-?? ??:??``.
    ``submittedAt`` is served on every entry, so ``when`` reads it first."""
    from maxpane_dashboard.widgets.fmt import mmdd
    seat = swarm_capture_v5("seat_420")
    rows = seat_work_rows(seat)
    assert {w.get("status") for w in seat["work"]} >= {"accepted", "pending"}
    assert all(row["submitted_ts"] is not None for row in rows)
    unaccepted = [r for r in rows if r["accepted_ts"] is None]
    assert unaccepted, "the capture must carry an attempt with no acceptedAt"
    shown = [unaccepted[0], *rows[:3]]
    text = "\n".join(await _record(size=(200, 14), swarm_seat_work_rows=shown))
    assert "??" not in text
    for row in shown:
        assert f"{mmdd(row['submitted_ts'])} {hhmm(row['submitted_ts'])}" in text


async def test_an_unaccepted_attempt_shows_its_own_status_not_the_jobs():
    """Reviewer I1, 2026-09-22: a failed attempt on a completed job rendered
    a green ``completed``. The state cell shows the attempt's status unless
    it was accepted; colours are read off composited cells."""
    seat = swarm_capture_v5("seat_420")
    rows = seat_work_rows(seat)
    picks = {}
    for row in rows:
        if row["job_state"] == "completed":
            picks.setdefault(row["work_status"], row)
    assert {"accepted", "failed", "rejected", "pending"} <= set(picks), set(picks)
    record = SurfSwarmSeatRecord()
    cells = {status: str(record.build_cells(row)["state"]) for status, row in picks.items()}
    assert cells["accepted"] == "[green]completed[/]"
    assert cells["failed"] == "[red]failed[/]"
    assert cells["rejected"] == "[red]rejected[/]"
    assert cells["pending"] == "[yellow]pending[/]"
    old = dict(picks["failed"], work_status=None)
    assert str(record.build_cells(old)["state"]) == "[green]completed[/]"


@pytest.mark.parametrize('raw,expected', [
    ('claude-sonnet-5','sonnet 5'),('claude-opus-5','opus 5'),
    ('claude-opus-5-5','opus 5.5'),('claude-fable-5-1','fable 5.1'),
    ('gpt-6-astra','astra 6'),('gpt-6-sol','sol 6'),('gpt-6-luna','luna 6'),
    ('gpt-5.6-luna','luna 5.6'),('gpt-5.6-terra','terra 5.6'),('gpt-5.6-sol','sol 5.6'),
    ('gpt-5.5','gpt-5.5'),('[/x]',None),(None,None),('',None),
    ('x'*200,'x'*200),('claude-opus-5-5\n','opus 5.5'),
    ('claude-opus-5-5-extra','claude-opus-5-5-extra'),
])
def test_short_model_exact_cleaned_patterns(raw,expected):
    from maxpane_dashboard.widgets.surf._fmt import short_model
    assert short_model(raw)==expected


@pytest.mark.parametrize('state,word,color,dim', [
    ('agreed','✓ 35/36','green',False),('outvoted','✗ 35/36','red',False),
    ('no_quorum_in','✓ no-q','green',True),('no_quorum_out','✗ no-q','red',True),
    ('assessing','… of 112','yellow',False),('blocked','blocked',None,True),
    ('off_panel','–',None,True),('not_oracle','–',None,True),
    ('not_read','not read',None,True),('unavailable','unavail','yellow',False),
])
async def test_panel_states_and_styles_reach_compositor(state,word,color,dim):
    class Harness(App):
        def compose(self): yield SurfSwarmSeatRecord()
    row=dict(NEWEST,answer_state='read',answer='Done.',panel_state=state,
             panel_agreed=35,panel_quorum=36,panel_size=112)
    async with Harness().run_test(size=(220,12)) as pilot:
        pilot.app.query_one(SurfSwarmSeatRecord).update_data(swarm_seat_work_rows=[row],swarm_seat_state='ok')
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y=next(i for i,line in enumerate(lines) if _job(row) in line)
        x=lines[y].index(word)
        style=pilot.app.screen.get_style_at(x,y)
        from textual.filter import dim_color
        if color:
            expected=Color.from_triplet(Color.parse(color).get_truecolor(pilot.app.ansi_theme))
        else:
            # The plain node cell supplies the same row's foreground/background.
            expected=pilot.app.screen.get_style_at(lines[y].index(_node(row)),y).color
        if dim:
            expected=dim_color(style.bgcolor,expected)
        assert style.color.get_truecolor(pilot.app.ansi_theme)==expected.get_truecolor(pilot.app.ansi_theme)


@pytest.mark.parametrize('state,field', [('agreed','panel_agreed'),('outvoted','panel_agreed')])
async def test_missing_panel_counts_are_unavailable(state,field):
    row=dict(NEWEST,panel_state=state,panel_agreed=35,panel_quorum=36,panel_size=112)
    row[field]=None
    text='\n'.join(await _record(swarm_seat_work_rows=[row]))
    assert 'unavail' in _row_with(text.splitlines(),_job(row))
    assert 'None' not in text and '?/?' not in text


@pytest.mark.parametrize('value,expected',[(None,'—'),(0,'0'),(1534,'1.5K'),(22000,'22.0K'),(True,'—')])
async def test_output_tokens_in_composited_tok_column(value,expected):
    row=dict(NEWEST,answer_state='read',answer='Done.',output_tokens=value)
    lines=await _record((220,12),swarm_seat_work_rows=[row])
    header=_row_with(lines,'when');line=_row_with(lines,_job(row))
    assert line[header.index('tok'):header.index('answer')].strip()==expected


@pytest.mark.parametrize('state',['outvoted','no_quorum_out'])
@pytest.mark.parametrize('answer_state',['read','not_read'])
async def test_red_rows_prefix_exact_wei_even_before_answer_read(state,answer_state):
    row=dict(NEWEST,panel_state=state,panel_agreed=35,panel_quorum=36,panel_figure='457162630000000001',
             panel_answer_type='uint256',answer_state=answer_state,answer='Done.')
    text='\n'.join(await _record((220,12),swarm_seat_work_rows=[row]))
    assert 'panel 457162630000000001 · '+('Done.' if answer_state=='read' else 'not read') in text


@pytest.mark.parametrize('answer,word',[(True,'YES'),(False,'NO'),(None,'unavail')])
async def test_bool_prefix_uses_explicit_answer(answer,word):
    row=dict(NEWEST,panel_state='outvoted',panel_agreed=35,panel_quorum=36,panel_figure='263154',
             panel_answer_type='bool',panel_answer_bool=answer,answer_state='read',answer='Done.')
    text='\n'.join(await _record((220,12),swarm_seat_work_rows=[row]))
    assert f'panel {word} · Done.' in text and '263154' not in text


async def test_assessing_without_size_and_hostile_strings_are_cleaned():
    row=dict(NEWEST,panel_state='assessing',panel_quorum=3,panel_size=None,
             model='[/x]gpt-6-astra',answer_state='read',answer='Done.')
    text='\n'.join(await _record((220,12),swarm_seat_work_rows=[row]))
    assert '…' in text and 'astra 6' in text and '[/x]' not in text
    row.update(panel_state='outvoted',panel_agreed=1,panel_quorum=2,panel_figure='[/x]42',panel_answer_type='uint256')
    text='\n'.join(await _record((220,12),swarm_seat_work_rows=[row]))
    assert 'panel 42 · Done.' in text and '[/x]' not in text


async def test_panel_survives_all_tiers_and_role_is_absent():
    gutter=SwarmTableBase.GUTTER_COLS
    row=dict(NEWEST,panel_state='agreed',panel_agreed=105,panel_quorum=112)
    for width,expected in [(FULL_WIDTH,('when','job','node','state','model','took','panel','tok','answer')),
                           (COMPACT_WIDTH,('when','job','node','state','model','took','panel','answer')),
                           (TIGHT_WIDTH,('when','job','node','state','panel'))]:
        lines=await _record((width+gutter,12),swarm_seat_work_rows=[row])
        assert tuple(_row_with(lines,'when').split())==expected
        assert '✓ 105/112' in '\n'.join(lines)


async def test_red_prefix_alone_pushes_answer_past_width_and_lights_widen():
    row=dict(NEWEST,answer_state='read',answer='fits',panel_state='agreed',
             panel_agreed=35,panel_quorum=36,panel_figure='457162630000000001',panel_answer_type='uint256')
    size=(FULL_WIDTH+SwarmTableBase.GUTTER_COLS,12)
    before='\n'.join(await _record(size,swarm_seat_work_rows=[row]))
    assert '‹' not in before
    row['panel_state']='outvoted'
    after='\n'.join(await _record(size,swarm_seat_work_rows=[row]))
    assert 'panel 4571' in after and '…' in after and '‹' in after


@pytest.mark.parametrize('tokens,shown', [
    (0, '0'), (1, '1'), (812, '812'), (999, '999'), (1000, '1.0K'),
    (1534, '1.5K'), (22000, '22.0K'), (999499, '999.5K'),
    (999500, '1.0M'), (999999, '1.0M'), (1234567, '1.2M'),
])
async def test_token_counts_fit_six_cells_without_decimal_integers_or_unit_overflow(tokens, shown):
    from rich.cells import cell_len
    row = dict(NEWEST, answer_state='read', answer='Done.', output_tokens=tokens)
    lines = await _record((220, 12), swarm_seat_work_rows=[row])
    header = _row_with(lines, 'when')
    line = _row_with(lines, _job(row))
    rendered = line[header.index('tok'):header.index('answer')].strip()
    assert rendered == shown
    assert cell_len(rendered) <= 6


def oracle_row(**overrides):
    return dict(dict(NEWEST, answer_state='read', answer='Closing message.', panel_state='agreed',
                     panel_agreed=34, panel_quorum=35, panel_size=49, panel_answer_type='bool',
                     oracle_member_ok=True, oracle_seat_answer='true', oracle_question='Is it true?',
                     oracle_member_reason=None, oracle_notes='The evidence. ' * 100, oracle_chain_id=1), **overrides)


@pytest.mark.parametrize('value,notes,cut', [('true','Long notes. '*100,True),('false','Short.',False),('9'*78,'',True)])
async def test_joined_answer_value_and_popup_action_reach_compositor(value, notes, cut):
    row = oracle_row(oracle_seat_answer=value, oracle_notes=notes,
                     panel_answer_type='uint256' if value[0]=='9' else 'bool')
    class Harness(App):
        def compose(self): yield SurfSwarmSeatRecord()
    async with Harness().run_test(size=(140,12)) as pilot:
        widget=pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=[row],swarm_seat_state='ok')
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y=next(i for i,line in enumerate(lines) if _job(row) in line)
        line=lines[y]
        assert 'Closing message.' not in line and not widget._clipped
        assert ('»' in line) is cut
        if cut:
            x=line.index('»')
            assert line[x-2:x]=='… '
            assert pilot.app.screen.get_style_at(x,y).meta['@click']==f"screen.open_oracle_answer('{row['job_id']}','{row['submission_hash']}')"
            assert '@click' not in pilot.app.screen.get_style_at(x-1,y).meta
        else:
            assert 'NO · Short.' in line


@pytest.mark.parametrize('bad', ['bad', "');x('", 'a'*64+'\n'])
async def test_joined_hostile_identity_never_draws_popup_button(bad):
    row=oracle_row(submission_hash=bad)
    lines=await _record((140,12),swarm_seat_work_rows=[row])
    assert '»' not in '\n'.join(lines)


@pytest.mark.parametrize('chain', [1,56,4663])
async def test_joined_visible_addresses_are_whole_linked_for_known_chain_only(chain):
    from tests.widgets.address_probe import icon_targets, link_targets
    address='0x'+'1'*40
    row=oracle_row(oracle_chain_id=chain,oracle_notes=address+' then '+('long '*100))
    class Harness(App):
        def compose(self): yield SurfSwarmSeatRecord()
    async with Harness().run_test(size=(220,12)) as pilot:
        pilot.app.query_one(SurfSwarmSeatRecord).update_data(swarm_seat_work_rows=[row],swarm_seat_state='ok')
        await pilot.pause()
        assert any(target[2]==address for target in icon_targets(pilot.app))
        links=[target for target in link_targets(pilot.app) if target[4]==address]
        assert bool(links) is (chain==1)
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        assert address+' ⧉' in '\n'.join(lines)
    tight='\n'.join(await _record((110,12),swarm_seat_work_rows=[row]))
    assert '0x' not in tight and '… »' in tight


async def test_joined_failed_member_is_red_and_keeps_popup_action():
    row=oracle_row(oracle_member_ok=False,oracle_member_reason='Invalid input. '*40,work_status='failed')
    class Harness(App):
        def compose(self): yield SurfSwarmSeatRecord()
    async with Harness().run_test(size=(140,12)) as pilot:
        pilot.app.query_one(SurfSwarmSeatRecord).update_data(swarm_seat_work_rows=[row],swarm_seat_state='ok')
        await pilot.pause()
        lines=[''.join(s.text for s in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y=next(i for i,l in enumerate(lines) if 'failed · Invalid' in l)
        x=lines[y].index('failed · Invalid')
        assert pilot.app.screen.get_style_at(x,y).color.get_truecolor(pilot.app.ansi_theme)==Color.parse('red').get_truecolor(pilot.app.ansi_theme)
        assert 'open_oracle_answer' in pilot.app.screen.get_style_at(lines[y].index('»'),y).meta['@click']
