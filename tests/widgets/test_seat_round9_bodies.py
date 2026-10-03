"""Complete round-9 content through the compositor (WP5)."""
import copy

import pytest
from textual.widgets import DataTable

from maxpane_dashboard.widgets.seat import SeatJob, SeatOutputTokens, SeatLedgerTable, SeatRecords, SeatNodes, SeatConfig, SeatSkills
from maxpane_dashboard.widgets.seat.machine import SeatMachine
from tests.widgets.test_seat_config_machine import _payload, _machine
from tests.widgets.test_seat_hero import composite_lines
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens.test_seat_round9_navigation import strips

JOB = 'b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70'
ADDR = '0x1234567890123456789012345678901234567890'


async def test_machine_transcripts_label_once_and_journal_explicit_reason():
    data = _payload('SeatMachine', seat_machine_transcript_retention={'kind':'claude-projects','deleteDays':30}, seat_machine_journal=None)
    data['seat_sources']['unit'].update(ok=True, reason='journal permission denied')
    rows = await _machine(**data)
    line = next(r for r in rows if '30-day window' in r)
    assert line.count('transcripts') == 1
    assert any('journal permission denied' in r for r in rows)


@pytest.mark.parametrize('days,reason,word', [(0,'unavailable','no token data yet (sessions: unavailable)'),(1,None,'1 day so far')])
async def test_output_tokens_explains_short_series(days, reason, word):
    series = {'outputTokensPerDay': [['2026-10-03', 123]] if days else []}
    rows = await composite_lines(SeatOutputTokens,(100,12),seat_cost_series=series,
                                seat_output_tokens=dict(today=123 if days else None,sevenDays=123 if days else None,
                                                        averagePerDay=123 if days else None,days=days,reason=reason))
    assert word in '\n'.join(rows)


async def test_output_tokens_has_all_three_figures_below_series():
    rows = await composite_lines(SeatOutputTokens,(100,12),
        seat_cost_series={'outputTokensPerDay':[['2026-10-02',100],['2026-10-03',300]]},
        seat_output_tokens=dict(today=300,sevenDays=400,averagePerDay=200,days=2,reason=None))
    text = '\n'.join(rows)
    assert 'today 300' in text and '7 d 400' in text and 'avg 200' in text


async def test_ledger_footer_keeps_today_duration_and_divergence():
    data=_payload('SeatLedgerTable',seat_today_p50_s=28,seat_today_longest_s=252,
                  seat_today_divergence={'localStored':11,'planeRowsSubmittedToday':11,'matches':True})
    rows=await composite_lines(SeatLedgerTable,(160,24),**data)
    text='\n'.join(rows)
    assert 'today p50 28 s' in text and 'longest 4m12s' in text
    assert '11' in text and 'plane' in text


async def test_job_plain_api_text_outcome_structural_check_and_usage():
    row=dict(key='j',jobId=JOB,nodeId8='d09e7e5b',nodeKey='research_report',role='implement',
             storedUtc='2026-10-03T23:45:00Z',objective='Question [red]literal[/]\nsecond line',questionState='read',questionAsOfUtc='2026-10-03T17:08:00Z',
             reply='Result [link=https://evil.invalid]literal[/]\nhttps://third.invalid',replyState='read',
             outcome='rejected',structuralCheck={'status':'accepted','evaluation':'structural','detail':'paths and tree verified'},
             usage={'model':'claude-fable-5-1','turns':6,'tokens':{'output':10250},'wallS':55})
    text='\n'.join(await composite_lines(SeatJob,(110,35),seat_jobs=[row]))
    assert 'JOB · last · stored' in text and 'QUESTION (api' in text
    assert 'Question [red]literal[/]' in text and 'second line' in text
    assert 'Result [link=https://evil.invalid]literal[/]' in text and 'https://third.invalid' in text
    assert 'rejected' in text and 'check: structural — paths and tree verified' in text
    assert 'claude-fable-5-1' in text and '6 turns' in text and 'out 10,250' in text and '55 s' in text


@pytest.mark.parametrize('state,reason,offline,want', [('not read',None,False,'reply not read yet'),('busy','busy',False,'reply unavailable (api: busy)'),('unavailable','503 ×2',False,'reply unavailable (api: 503 ×2)'),('text expired',None,False,'text expired'),('not read',None,True,'unavailable (offline)')])
async def test_job_unread_result_explains_its_state(state,reason,offline,want):
    text='\n'.join(await composite_lines(SeatJob,(100,24),seat_jobs=[dict(key='j',jobId=JOB,replyState=state,replyReason=reason)],seat_offline=offline))
    assert want in text


async def test_job_working_text_and_offline_cache_are_visible():
    current=dict(key='j',jobId=JOB,nodeId8='12345678',phase='working',elapsedS=42,lastMessage='last sentence')
    data=dict(current,objective='standing objective',questionState='not read',replyState='not read')
    text='\n'.join(await composite_lines(SeatJob,(100,24),seat_current_jobs=[current],seat_jobs=[data],seat_offline=True))
    assert 'JOB · working' in text and 'standing objective' in text and '(cached)' in text
    assert 'QUESTION (cached)' in text
    assert 'in progress · working' in text and '42 s' in text and 'last sentence' in text


async def test_records_pin_columns_literal_answer_and_window_controls():
    flat=_seat_payload()
    flat['seat_records_rows']=[dict(key=f'r-{i}',jobId=JOB,nodeKey='oracle_assess',workStatus='pending',
        answerPreview='[red]answer[/] first.',answerState='read', panel={'state':'agreed','agreed':7,'quorum':5},
        model='gpt-6-luna',durationS=55,tokens={'output':1500}) for i in range(62)]
    async with _seat_app(flat).run_test(size=(132,40)) as pilot:
        await pilot.pause(); await pilot.press('4'); await pilot.pause()
        panel=pilot.app.screen.query_one(SeatRecords)
        assert {'when','job','node','state','panel','answer'} <= set(panel._keys)
        text='\n'.join(strips(pilot.app.screen))
        assert '[red]answer[/]' in text and '✓ 7/5' in text
        assert 'all · not completed' in text and '+22 older' in text and 'more' in text
        await pilot.press('m'); await pilot.pause()
        assert panel.query_one(DataTable).row_count==60
        assert '+2 older' in '\n'.join(strips(pilot.app.screen))


async def test_nodes_unknown_payer_is_dim_dot_and_footer_defines_coverage():
    flat=_seat_payload()
    flat['seat_nodes_all_rows']=[dict(nodeKey='research_report',role='implement',attempts=3,accepted=2,rejected=0,failed=0,pending=1,
        acceptedPercent=200/3,durationP50S=28,outputTokensP50=1234,paid=None,launch=None,detailsRead=0,lastSubmittedUtc='2026-10-03T17:00:00Z'),
        dict(nodeKey='(plane unread)',role=None,attempts=1,accepted=0,rejected=0,failed=0,pending=1,paid=0,launch=0,detailsRead=1)]
    flat['seat_nodes_coverage']=dict(covered=4,attempts=7,detailsRead=1)
    async with _seat_app(flat).run_test(size=(180,40)) as pilot:
        await pilot.pause(); await pilot.press('5'); await pilot.pause()
        panel=pilot.app.screen.query_one(SeatNodes)
        assert {'paid','launch','acc_pct','pending','duration','output'} <= set(panel._keys)
        text='\n'.join(strips(pilot.app.screen))
        assert '66.7' in text and '(plane unread)' in text
        assert 'covers 4 of 7 attempts' in text and 'job details read 1 of 4' in text
        assert 'accepted ÷ attempts' in text and 'api paidBy' in text
        table=panel.query_one(DataTable)
        table.move_cursor(row=1); await pilot.pause()
        y=table.region.y+table.header_height
        x=table.region.x+sum(w+2 for k,_,w in panel._installed if list(panel._keys).index(k)<list(panel._keys).index('paid'))+1
        assert strips(pilot.app.screen)[y][x]=='·'
        # Textual resolves Rich dim into the final terminal colour.
        known_x=table.region.x+sum(w+2 for k,_,w in panel._installed if list(panel._keys).index(k)<list(panel._keys).index('n'))+1
        assert pilot.app.screen.get_style_at(x,y).color != pilot.app.screen.get_style_at(known_x,y).color


async def test_config_every_setting_and_skills_counts_tools_restart():
    flat=_seat_payload()
    flat['seat_skills_rows']=[dict(id=f'skill-{i}',on=i<30,needs='network' if i<9 else '') for i in range(50)]
    flat.update(seat_skills_offered=50,seat_skills_on=30,seat_skills_needs_network=9,seat_control_restart_required=True)
    async with _seat_app(flat).run_test(size=(180,45)) as pilot:
        await pilot.pause(); await pilot.press('3'); await pilot.pause()
        config=pilot.app.screen.query_one(SeatConfig)
        names={row['setting'] for row in config._seat_rows}
        assert {'server','seat','wallet','device key','runtime','capacity','offers','inference economy','inference standard','inference premium',
                'premium advertised','wrapper','tools','hints','boot','auto-update','daemon','config file'} <= names
        text='\n'.join(strips(pilot.app.screen))
        assert '50 offered' in text and '30 on' in text and '9 need network' in text
        assert 'restart required' in text and '6 CONTROL' in text and 'shown state applies after restart' in text
        assert pilot.app.screen.query_one(SeatSkills).query_one(DataTable).row_count==50


async def test_skills_counts_and_record_node_window_words_are_in_panel_titles():
    flat = _seat_payload()
    flat.update(seat_skills_offered=50, seat_skills_on=30, seat_skills_needs_network=9)
    async with _seat_app(flat).run_test(size=(180,45)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await pilot.press('3'); await pilot.pause()
        skills = screen.query_one(SeatSkills)
        y = skills.query_one('.panel-title').region.y
        assert '50 offered' in strips(screen)[y] and '9 need network' in strips(screen)[y]
        for key, cls, words in [('4', SeatRecords, 'all · not completed'), ('5', SeatNodes, 'all · 7 d')]:
            await pilot.press(key); await pilot.pause()
            panel = screen.query_one(cls)
            y = panel.query_one('.panel-title').region.y
            assert words in strips(screen)[y]
            x = strips(screen)[y].index('all')
            assert screen.get_style_at(x,y).meta.get('@click')


async def test_job_keeps_every_running_job_when_only_one_full_detail_is_cached():
    flat = _seat_payload()
    flat['seat_current_jobs'] = [dict(jobId='new-job',nodeId8='11111111',objective='standing newest',phase='working'),
                                 dict(jobId='old-job',nodeId8='22222222',objective='standing older',phase='working')]
    flat['seat_jobs'] = [dict(jobId='old-job',nodeId8='22222222',objective='full older',questionState='read')]
    async with _seat_app(flat).run_test(size=(180,45)) as pilot:
        await pilot.pause()
        panel = pilot.app.screen.query_one(SeatJob)
        assert panel.selected_row()['jobId'] == 'new-job'
        assert 'standing newest' in '\n'.join(strips(pilot.app.screen))
        assert '1 of 2' in '\n'.join(strips(pilot.app.screen))
        await pilot.press('n'); await pilot.pause()
        assert panel.selected_row()['jobId'] == 'old-job'
        assert 'full older' in '\n'.join(strips(pilot.app.screen))


async def test_oracle_bool_answer_and_consensus_use_shared_yes_no_words():
    rows = await composite_lines(SeatJob, (110,30), seat_jobs=[dict(jobId=JOB,oracleRequestId='oracle-id',
            oracleQuestion='Question',oracleAnswer='false',replyState='read',
            panel=dict(state='agreed',agreed=7,quorum=5,size=9,answerType='bool',answerBool=True))])
    text = '\n'.join(rows)
    assert 'NO' in text and 'agreed 7 · quorum 5 · panel 9 · YES' in text


@pytest.mark.parametrize('outcome,extra,want', [
    ('accepted', {'verdictLagS':1020}, 'accepted (+17m)'),
    ('failed', {'failureReason':'runtime_error'}, 'failed runtime_error'),
])
async def test_job_verdict_keeps_ledger_lag_and_failure_reason(outcome, extra, want):
    row = dict(jobId=JOB, outcome=outcome, **extra)
    text = '\n'.join(await composite_lines(SeatJob, (110,30), seat_jobs=[row]))
    assert want in text


@pytest.mark.parametrize('state,want', [('not read','not read'), ('busy','busy'), ('unavailable','unavailable')])
async def test_records_unread_answer_is_explicit_and_uses_its_status_colour(state, want):
    flat = _seat_payload()
    flat['seat_records_rows'] = [dict(key='reference', jobId=JOB, answerPreview='reference'),
                                 dict(key='unread', jobId=JOB, answerState=state)]
    async with _seat_app(flat).run_test(size=(180,40)) as pilot:
        await pilot.pause(); await pilot.press('4'); await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one(SeatRecords).query_one(DataTable)
        y = table.region.y + table.header_height + 1
        line = strips(screen)[y]
        assert want in line
        color = screen.get_style_at(line.index(want), y).color
        if state in ('busy', 'unavailable'):
            assert color.get_truecolor(pilot.app.ansi_theme) == pilot.app.ansi_theme.ansi_colors[3]
        else:
            assert color != screen.get_style_at(line.index(JOB[:8]), y).color


async def test_job_usage_falls_back_to_submission_wall_clock():
    text = '\n'.join(await composite_lines(SeatJob, (110,30), seat_jobs=[dict(jobId=JOB,
        usage={'model':'api-model','turns':4,'tokens':{'output':900},'wallMs':55000,'wallS':None})]))
    assert 'api-model · 4 turns · out 900 · took 55 s' in text
