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
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_record import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    JOB_COLS,
    ANSWER_MIN_COLS,
    TIGHT_WIDTH,
    SurfSwarmSeatRecord,
)
from tests.surf_swarm_fixtures import swarm_seat_capture
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
    assert NEWEST["node_key"] in row and NEWEST["role"] in row and NEWEST["job_state"] in row
    assert "not read" in row and NEWEST["objective"] not in row
    text = "\n".join(lines)
    assert "RECORD" in text and f"as of {AS_OF}" in text
    header = _row_with(lines, "answer").split()
    assert header == ["when", "job", "node", "role", "state", "launch", "sub", "model", "took", "answer"]


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


async def test_one_below_full_sheds_role_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    row = [dict(NEWEST, answer_state="read", answer="fits")]
    full_lines = await _record((FULL_WIDTH + gutter, 12), swarm_seat_work_rows=row)
    compact_lines = await _record((FULL_WIDTH + gutter - 1, 12), swarm_seat_work_rows=row)
    full_header = _row_with(full_lines, "when").split()
    compact_header = _row_with(compact_lines, "when").split()
    assert "role" in full_header and "‹" not in "\n".join(full_lines)
    assert "role" not in compact_header and "‹" in "\n".join(compact_lines)
    assert "answer" in compact_header, "compact keeps the answer"


async def test_one_below_compact_sheds_the_answer():
    gutter = SwarmTableBase.GUTTER_COLS
    lines = await _record((COMPACT_WIDTH + gutter - 1, 12), swarm_seat_work_rows=[NEWEST])
    header = _row_with(lines, "when").split()
    assert "answer" not in header and "‹" in "\n".join(lines)
    assert NEWEST["node_key"] in "\n".join(lines)

async def test_dates_survive_midnight_and_launch_submission_are_plain():
    from maxpane_dashboard.widgets.fmt import mmdd
    rows = [dict(NEWEST, job_id=f"day{i}abcd", accepted_ts=1_758_456_000+i*86400,
                 launch="evm_project" if i else None, submission_hash="ab"*32) for i in range(2)]
    text = "\n".join(await _record(size=(180,12), swarm_seat_work_rows=rows))
    assert mmdd(rows[0]["accepted_ts"]) != mmdd(rows[1]["accepted_ts"])
    for row in rows:
        assert f"{mmdd(row['accepted_ts'])} {hhmm(row['accepted_ts'])}" in text
    assert "evm_project" in text and "abababab" in text and "—" in text
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
    assert header==['when','job','node','role','state','launch','sub','model','took','answer']
    line=_row_with(lines,_job(row))
    assert word in line and 'OBJECTIVE MUST NOT PAINT' not in '\n'.join(lines)
    if state in ('read','no_reply'):
        assert 'claude-sonnet-5' in line and '7m' in line
    else:
        assert 'claude-sonnet-5' not in line and '7m' not in line and line.count('—')==2


@pytest.mark.parametrize('seconds,expected',[(420,'7m'),(3840,'1h 04m'),(0,'<1m'),(0.1,'<1m'),(59.99,'<1m'),(60,'1m'),(None,'—')])
async def test_polish_duration_and_missing_model(seconds,expected):
    row=dict(NEWEST,answer_state='read',answer='Done.',model=None,took_s=seconds,launch='evm_project')
    line=_row_with(await _record((200,12),swarm_seat_work_rows=[row]),_job(row))
    assert re.search(r'(?<!\S)' + re.escape(expected) + r'(?!\S)', line), line
    assert line.count('—')==(2 if seconds is None else 1)


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
    assert 'claude-sonnet-5' in text and '<1m' in text and '…' in text and '‹' in text
    assert '[x]' not in text and '/Users/' not in text and '/home/' not in text and '/root/' not in text
