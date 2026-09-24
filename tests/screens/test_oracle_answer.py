"""ANSWER popup: composited content, geometry and real app-level click paths."""
import asyncio

import pytest
from rich.cells import cell_len
from textual.app import App
from textual.containers import VerticalScroll

from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard import clipboard
from maxpane_dashboard.screens.surf import SurfScreen, MODE_AGENT
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.widgets.address_probe import icon_targets, link_targets, LinkRecorder
from tests.widgets.test_surf_swarm_seat_record import oracle_row
from tests.screens.test_surf_screen import _FakeManager, _sample_data, _Harness


class PopupApp(CopyAddressMixin, ExplorerLinkMixin, LinkRecorder, App):
    def __init__(self, row):
        super().__init__(); self.row = row
    def on_mount(self):
        self.push_screen(OracleAnswerScreen(self.row))


def lines(app):
    return [''.join(s.text for s in strip) for strip in app.screen._compositor.render_strips()]


async def settled(pilot, predicate):
    for _ in range(100):
        await pilot.pause()
        if predicate(): return
    assert predicate(), 'observable UI state did not settle'


@pytest.mark.parametrize('size', [(80,24),(139,33),(40,12)])
async def test_popup_content_footer_geometry_and_scrolling(size):
    row=oracle_row(oracle_notes='Start of notes.\n\n'+'A paragraph of evidence.\n'*100)
    async with PopupApp(row).run_test(size=size) as pilot:
        await pilot.pause()
        text='\n'.join(lines(pilot.app))
        assert 'PRESS ENTER TO CLOSE' in text and 'ANSWER ·' in text
        if size[0]>=80:
            assert 'QUESTION' in text and 'this seat' in text and 'YES' in text
            assert 'agreed 34 · quorum 35 · panel 49' in text and 'Start of notes.' in text
        footer=pilot.app.screen.query_one('#oracle-answer-close')
        scroll=pilot.app.screen.query_one(VerticalScroll)
        assert scroll.has_focus and scroll.max_scroll_x==0
        assert footer.region.bottom<=size[1]-1
        line=lines(pilot.app)[footer.region.y]
        x=line.index('PRESS ENTER TO CLOSE')
        assert abs(x+(len('PRESS ENTER TO CLOSE')/2)-size[0]/2)<=1
        for widget in pilot.app.screen.query('*'):
            if widget.region.width and widget.is_on_screen:
                assert widget.region.right<=size[0] and widget.region.x>=0
        await pilot.press('pagedown')
        await settled(pilot, lambda: scroll.scroll_y>0)
        assert 'PRESS ENTER TO CLOSE' in '\n'.join(lines(pilot.app))


@pytest.mark.parametrize('chain', [1,56,4663])
async def test_popup_question_notes_and_address_list_use_shared_copy_and_link_helpers(chain, monkeypatch):
    copied=[]
    async def copy(text, **kwargs): copied.append(text); return clipboard.COPIED
    monkeypatch.setattr(clipboard, 'copy_text', copy)
    addresses=['0x'+str(i)*40 for i in (1,2,3)]
    row=oracle_row(panel_answer_type='address[]',oracle_seat_answer=addresses[0],oracle_chain_id=chain,
                   oracle_question='Question '+addresses[1],oracle_notes='Notes '+addresses[2])
    async with PopupApp(row).run_test(size=(139,33)) as pilot:
        await pilot.pause()
        icons=icon_targets(pilot.app)
        assert {t[2] for t in icons}==set(addresses)
        links=[t for t in link_targets(pilot.app) if t[4] in addresses]
        assert bool(links) is (chain==1)
        x,y,address=icons[0]
        await pilot.click(offset=(x,y))
        await settled(pilot, lambda: copied==[address])
        if links:
            x,y,*_=links[0]
            await pilot.click(offset=(x,y))
            assert pilot.app.opened==[links[0][-1]]


@pytest.mark.parametrize('state', ['unavailable','agreed'])
async def test_popup_snapshot_invalid_and_failed_answers(state):
    row=oracle_row(oracle_seat_answer=None,panel_state=state,oracle_notes='Saved notes.')
    app=PopupApp(row)
    async with app.run_test(size=(80,24)) as pilot:
        await pilot.pause(); row['oracle_notes']='Changed after open'
        text='\n'.join(lines(app))
        assert 'Saved notes.' in text and 'Changed after open' not in text
        assert 'this seat   —' in text
        if state=='unavailable': assert 'unavailable' in text


@pytest.mark.parametrize('key', ['enter','escape'])
async def test_record_popup_click_closes_back_to_agent_and_resumes_guarded_refresh(key):
    row=oracle_row()
    payload=_sample_data(); payload.update(swarm_seat_state='ok',swarm_seat_work_rows=[row])
    manager=_FakeManager(payload); screen=SurfScreen(manager, poll_interval=9999)
    async with _Harness(screen).run_test(size=(139,33)) as pilot:
        await settled(pilot,lambda: manager.calls>0 and not screen._refresh_in_flight)
        await pilot.press('a'); await pilot.pause()
        targets=[]
        for y,strip in enumerate(screen._compositor.render_strips()):
            x=0
            for segment in strip:
                for ch in segment.text:
                    if ch=='»': targets.append((x,y,screen.get_style_at(x,y).meta))
                    x+=cell_len(ch)
        assert targets
        x,y,meta=targets[0]; assert 'screen.open_oracle_answer' in meta['@click']
        before=manager.calls
        await pilot.click(offset=(x,y))
        await settled(pilot,lambda:isinstance(pilot.app.screen,OracleAnswerScreen))
        assert manager.calls==before and screen._refresh_timer is None
        await pilot.press(key)
        await settled(pilot,lambda:pilot.app.screen is screen and manager.calls>before and not screen._refresh_in_flight)
        assert screen._mode==MODE_AGENT and screen._refresh_timer is not None


async def test_popup_action_revalidates_and_reports_disappeared_row():
    manager=_FakeManager(_sample_data()); screen=SurfScreen(manager,poll_interval=9999)
    async with _Harness(screen).run_test(size=(139,33)) as pilot:
        await settled(pilot,lambda:manager.calls>0 and not screen._refresh_in_flight)
        row=oracle_row()
        await screen.action_open_oracle_answer(row['job_id'],row['submission_hash']+'\n')
        assert pilot.app.screen is screen
        await screen.action_open_oracle_answer(row['job_id'],row['submission_hash'])
        assert pilot.app.screen is screen
        assert screen.query_one(StatusBar).message=='answer no longer listed'


async def test_resume_real_manager_keeps_fresh_seat_answers_and_oracle_cache(tmp_path):
    from tests.data.test_surf_manager_oracle import Oracle
    from tests.data.test_surf_manager_swarm import _manager
    from tests.data.test_surf_manager_answers import NOW
    from tests.data.test_surf_manager import FakeClock
    from maxpane_dashboard.data.surf_cache import TIERS
    fake=Oracle(status='assessing'); manager=_manager(tmp_path,fake,clock=FakeClock(NOW))
    manager.set_seat(420)
    await manager._pool_swarm_seat(420,NOW)
    for tier in TIERS: manager.cache.mark_fetched(tier,NOW)
    screen=SurfScreen(manager,poll_interval=9999)
    try:
        async with _Harness(screen).run_test(size=(139,33)) as pilot:
            await settled(pilot,lambda:bool(getattr(screen,'_oracle_answer_rows',None)) and not screen._refresh_in_flight)
            row=screen._oracle_answer_rows[0]
            calls=(list(fake.oracle_calls),list(fake.answer_calls),list(fake.seat_calls))
            cycle=manager._cycle_count
            await screen.action_open_oracle_answer(row['job_id'],row['submission_hash'])
            await settled(pilot,lambda:isinstance(pilot.app.screen,OracleAnswerScreen))
            assert manager._cycle_count==cycle
            manager.client.calls.clear()
            await pilot.press('enter')
            await settled(pilot,lambda:pilot.app.screen is screen and manager._cycle_count>cycle and not screen._refresh_in_flight)
            assert (fake.oracle_calls,fake.answer_calls,fake.seat_calls)==calls
            # The fast chain tier intentionally has TTL=0: those reads remain normal.
            assert manager.client.calls == ['fetch_nonces','fetch_chain_state']
    finally: await manager.close()


async def test_popup_preserves_full_uint256_and_lists_every_address():
    row=oracle_row(panel_answer_type='uint256',oracle_seat_answer='9'*78,oracle_notes='Notes.')
    async with PopupApp(row).run_test(size=(139,33)) as pilot:
        await pilot.pause()
        assert '9'*78 in '\n'.join(lines(pilot.app))
    addresses=['0x'+str(i)*40 for i in (1,2,3)]
    row.update(panel_answer_type='address[]',oracle_seat_answer=' '.join(addresses))
    async with PopupApp(row).run_test(size=(80,24)) as pilot:
        await pilot.pause()
        assert {t[2] for t in icon_targets(pilot.app)}==set(addresses)
        assert all(address+' ⧉' in '\n'.join(lines(pilot.app)) for address in addresses)


async def test_popup_failed_member_displays_reason_in_red():
    from rich.color import Color
    row=oracle_row(oracle_member_ok=False,oracle_member_reason='Invalid input',oracle_notes='Details.')
    async with PopupApp(row).run_test(size=(80,24)) as pilot:
        await pilot.pause()
        shown=lines(pilot.app)
        y=next(i for i,line in enumerate(shown) if 'failed · Invalid input' in line)
        x=shown[y].index('failed · Invalid input')
        assert pilot.app.screen.get_style_at(x,y).color.get_truecolor(pilot.app.ansi_theme)==Color.parse('red').get_truecolor(pilot.app.ansi_theme)
