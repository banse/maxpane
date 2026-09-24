"""Composited SUBMISSION popup from committed captures; clicks never fetch."""
import pytest
from textual.containers import VerticalScroll

from maxpane_dashboard.screens.submission_detail import SubmissionDetailScreen
from maxpane_dashboard.screens.surf import SurfScreen, MODE_AGENT
from maxpane_dashboard.data import surf_swarm as sw
from tests.data.test_surf_swarm_answers import capture, own, point
from tests.screens.test_oracle_answer import PopupApp, lines, settled, x_button
from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
from tests.widgets.test_surf_swarm_seat_record import oracle_row
from tests.screens.test_surf_screen import _Harness, _FakeManager, _sample_data
from tests.widgets.address_probe import icon_targets, link_targets


def row_for(name='hunt'):
    payload,item=own(name)
    source=next(r for r in sw.seat_work_rows(capture('seat_420'))if r['submission_hash']==item['hash'])
    rows=sw.enrich_work_rows([source],{payload['jobId']:{item['hash']:point(payload,item)}})
    return sw.enrich_job_rows(rows,{payload['jobId']:sw.job_detail_point(capture(name+'_job'),payload['jobId'],now_ts=1000)})[0]


class SubmissionApp(PopupApp):
    def __init__(self,row): super().__init__(row,screen_type=SubmissionDetailScreen)


async def all_visible(pilot):
    scroll=pilot.app.screen.query_one(VerticalScroll)
    result=[]
    for _ in range(100):
        await pilot.pause()
        result.extend(lines(pilot.app))
        if scroll.scroll_y>=scroll.max_scroll_y: return '\n'.join(result)
        scroll.scroll_to(y=min(scroll.scroll_y+max(1,scroll.size.height-1),scroll.max_scroll_y),animate=False)
    raise AssertionError('scroll did not reach the end')


@pytest.mark.parametrize('size',[(80,24),(139,33),(40,12)])
async def test_hunt_submission_content_and_geometry(size):
    async with SubmissionApp(row_for()).run_test(size=size) as pilot:
        await pilot.pause()
        screen=pilot.app.screen;scroll=screen.query_one(VerticalScroll)
        assert scroll.has_focus and scroll.max_scroll_x==0
        footer=screen.query_one('#submission-detail-close')
        assert footer.region.bottom<=size[1]-1
        line=lines(pilot.app)[footer.region.y];x=line.index('PRESS SPACE OR ESC TO CLOSE')
        assert abs(x+len('PRESS SPACE OR ESC TO CLOSE')/2-size[0]/2)<=1
        for widget in screen.query('*'):
            if widget.is_on_screen and widget.region.width:
                assert widget.region.x>=0 and widget.region.right<=size[0]
        text=await all_visible(pilot)
        if size[0]>=80:
            for word in ['blocked · node hunt_b: runtime_error','hunt_b failed 3 runtime_error','Fren Review',
                'failed · local_build_failed','fable 5.1','61 turns','22m 56s','75.0K out','6.2M cached in',
                'published excerpt only','the local build failed','OTHER SEATS ON THIS JOB (7)', '#1', '#1548']:
                assert word in text,word
        assert 'PRESS SPACE OR ESC TO CLOSE' in lines(pilot.app)[footer.region.y]


async def test_bundle_failure_and_unread_job_have_no_other_seats_or_excerpt():
    row=row_for('bundle');row.update(job_read='not_read',job_detail_state=None)
    async with SubmissionApp(row).run_test(size=(139,33)) as pilot:
        text=await all_visible(pilot)
        assert 'bundle upload failed (500)' in text and 'not read yet' in text
        assert 'OTHER SEATS' not in text and 'published excerpt' not in text


async def test_reply_indentation_addresses_and_markup_are_safe():
    address='0x'+'a'*40
    row=row_for();row.update(sub_reply='    ┃ Indented [/x]\n'+address, objective='[/x] '+address,
                            job_blocked_reason='[/x] '+address, sub_others=[])
    async with SubmissionApp(row).run_test(size=(139,33)) as pilot:
        text=await all_visible(pilot)
        assert '    ┃ Indented [/x]' in text
        assert any(target[2]==address for target in icon_targets(pilot.app))
        assert not link_targets(pilot.app)


@pytest.mark.parametrize('key',['space','escape'])
async def test_submission_click_exact_hash_snapshot_and_close_to_agent(key):
    first=row_for(); second=dict(first,submission_hash='f'*64,sub_reply='Second member reply',sub_others=[])
    payload=_sample_data();payload.update(swarm_seat_state='ok',swarm_seat_work_rows=[first,second])
    manager=_FakeManager(payload);screen=SurfScreen(manager,poll_interval=9999)
    async with _Harness(screen).run_test(size=(139,33)) as pilot:
        await settled(pilot,lambda:manager.calls>0 and not screen._refresh_in_flight)
        await pilot.press('a');await pilot.pause()
        for row in (first,second):
            target=None
            for y,strip in enumerate(screen._compositor.render_strips()):
                x=0
                for segment in strip:
                    for char in segment.text:
                        if char=='»' and row['submission_hash'] in screen.get_style_at(x,y).meta.get('@click',''):
                            target=(x,y)
                        x+=1
            assert target
            before=manager.calls
            await pilot.click(offset=target)
            await settled(pilot,lambda:isinstance(pilot.app.screen,SubmissionDetailScreen))
            assert manager.calls==before
            assert pilot.app.screen.row['sub_reply']==row['sub_reply']
            saved=pilot.app.screen.row['sub_reply'];row['sub_reply']='changed later'
            assert pilot.app.screen.row['sub_reply']==saved
            await pilot.press('enter');await pilot.pause()
            assert isinstance(pilot.app.screen,SubmissionDetailScreen)
            await pilot.press(key)
            await settled(pilot,lambda:pilot.app.screen is screen and not screen._refresh_in_flight)
            assert screen._mode==MODE_AGENT


async def test_submission_action_revalidates_identity_read_state_and_stale_rows():
    from maxpane_dashboard.widgets.status_bar import StatusBar
    row = row_for()
    payload = _sample_data()
    payload.update(swarm_seat_state='ok', swarm_seat_work_rows=[row])
    manager = _FakeManager(payload)
    screen = SurfScreen(manager, poll_interval=9999)
    async with _Harness(screen).run_test(size=(139, 33)) as pilot:
        await settled(pilot, lambda: manager.calls > 0 and not screen._refresh_in_flight)
        await pilot.press('a')
        await pilot.pause()
        for job, hash_ in [(row['job_id']+'\n', row['submission_hash']),
                           (row['job_id'], row['submission_hash']+'\n')]:
            await screen.action_open_submission(job, hash_)
            assert pilot.app.screen is screen
        for state in ('not_read', 'unavailable', 'not_served'):
            screen._oracle_answer_rows = [dict(row, answer_state=state)]
            await screen.action_open_submission(row['job_id'], row['submission_hash'])
            assert pilot.app.screen is screen
            assert screen.query_one(StatusBar).message == 'answer no longer listed'
        screen._oracle_answer_rows = []
        await screen.action_open_submission(row['job_id'], row['submission_hash'])
        assert pilot.app.screen is screen
        assert screen.query_one(StatusBar).message == 'answer no longer listed'


async def test_markup_in_metadata_and_other_seat_cap_are_literal():
    row = row_for()
    row.update(node_key='[/x]', role='[/x]', work_status='[/x]', model='[/x]',
               sub_failure_reason='[/x]', sub_failed_checks='[/x]',
               sub_artifacts=[{'name': '[/x]', 'bytes': 3}],
               job_read='unavailable',
               job_nodes=[{'key': '[/x]', 'state': '[/x]', 'attempt': 2, 'failure_reason': '[/x]'}],
               sub_others=[{'node_key': '[/x]', 'token': i, 'outcome': '[/x]',
                            'failure_reason': None, 'line': '[/x]'} for i in range(8)],
               sub_others_total=12)
    async with SubmissionApp(row).run_test(size=(139, 33)) as pilot:
        text = await all_visible(pilot)
        assert 'unavailable' in text
        assert 'checks failed: [/x]' in text and 'artifacts [/x] (3 bytes)' in text
        assert '[/x]  #7  [/x]  [/x]' in text and '+4 more' in text


async def test_cached_large_integer_usage_cannot_crash_popup():
    row = row_for('bundle')
    row['sub_cached_input_tokens'] = 10**309
    async with SubmissionApp(row).run_test(size=(80, 24)) as pilot:
        text = await all_visible(pilot)
        assert 'bundle upload failed (500)' in text and 'cached in' in text
        assert pilot.app.screen.query_one(VerticalScroll).max_scroll_x == 0


@pytest.mark.parametrize('state', ['read', 'unavailable', 'not_read'])
async def test_job_line_exposes_cached_read_time(state):
    from maxpane_dashboard.widgets.fmt import hhmm
    row = row_for()
    assert row['job_read_ts'] == 1000.0
    row['job_read'] = state
    if state == 'not_read':
        row['job_read_ts'] = None
    async with SubmissionApp(row).run_test(size=(139, 33)) as pilot:
        await pilot.pause()
        text = '\n'.join(lines(pilot.app))
        if state == 'not_read':
            assert 'not read yet' in text and 'as of' not in text
        else:
            assert 'as of '+hhmm(1000.0) in text
            expected = 'blocked · node hunt_b: runtime_error' if state == 'read' else 'unavailable'
            assert expected+' · as of '+hhmm(1000.0) in text


async def test_record_and_submission_share_the_token_carry():
    from tests.widgets.test_surf_swarm_seat_record import _record
    row = row_for('bundle')
    row['output_tokens'] = 999700
    assert '1.0M' in '\n'.join(await _record(swarm_seat_work_rows=[row]))
    async with SubmissionApp(row).run_test(size=(139, 33)) as pilot:
        text = await all_visible(pilot)
        assert '1.0M out' in text and '999.7K' not in text


@pytest.mark.parametrize('size',[(80,24),(139,33),(40,12)])
@pytest.mark.parametrize('kind',['answer','submission'])
async def test_top_right_x_closes_either_popup(kind,size):
    app=PopupApp(oracle_row(),OracleAnswerScreen) if kind=='answer' else SubmissionApp(row_for())
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        popup=pilot.app.screen
        await pilot.click(offset=x_button(pilot.app))
        await settled(pilot,lambda:pilot.app.screen is not popup)
