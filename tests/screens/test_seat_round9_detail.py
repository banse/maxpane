"""Public cache texts are literal and address-aware; local transcript bodies stay absent."""
import pytest

from maxpane_dashboard.widgets.explorer import BASE, url_for
from tests.screens.test_seat_task_detail import _A, _row
from tests.widgets.address_probe import link_targets
from tests.screens.test_seat_round9_navigation import strips

ADDRESS='0x1234567890123456789012345678901234567890'


@pytest.mark.parametrize('oracle',[False,True])
async def test_cached_api_question_reply_notes_are_literal_with_copy_only_or_chain_link(oracle):
    row=_row(objective='Question [red]literal[/]\nline two '+ADDRESS,reply='Reply [link=https://evil.invalid]literal[/]\nhttps://third.invalid '+ADDRESS,
             questionState='read',replyState='read',questionAsOfUtc='2026-10-03T17:08:00Z',replyAsOfUtc='2026-10-03T17:10:00Z',
             paid=True,template='shape:dag',launch={'kind':'repo','requested':True,'workflowId':'workflow-123'},workflowId='workflow-123',
             delivery={'url':'https://github.com/example/repo','atUtc':'2026-10-03T17:11:00Z'},
             prompt='PRIVATE PROMPT',summary='LOCAL SUMMARY',toolOutput='PRIVATE TOOL OUTPUT',lastMessage='PRIVATE LAST MESSAGE')
    if oracle:
        row.update(oracleRequestId='oracle-123',oracleQuestion=row['objective'],oracleAnswer=row['reply'],
                   oracleNotes='Notes [red]literal[/] '+ADDRESS,panel={'state':'agreed','agreed':7,'quorum':5,'size':9,'chainId':8453})
    async with _A(row).run_test(size=(120,60)) as pilot:
        await pilot.pause()
        text='\n'.join(strips(pilot.app.screen))
        assert 'QUESTION' in text and 'RESULT' in text
        assert 'Question [red]literal[/]' in text and 'line two '+ADDRESS+' ⧉' in text
        assert 'Reply [link=https://evil.invalid]literal[/]' in text
        assert 'https://third.invalid '+ADDRESS+' ⧉' in text
        assert 'paid: yes (api paidBy)' in text and 'shape:dag' in text and 'workflow-123' in text
        assert 'delivered' in text and 'example/repo' in text
        assert all(word not in text for word in ('PRIVATE PROMPT','LOCAL SUMMARY','PRIVATE TOOL OUTPUT','PRIVATE LAST MESSAGE'))
        urls={target[5] for target in link_targets(pilot.app)}
        assert 'https://evil.invalid' not in urls and 'https://third.invalid' not in urls
        assert (url_for(BASE,'address',ADDRESS) in urls)==oracle
        if oracle: assert 'Notes [red]literal[/]' in text and 'agreed 7 · quorum 5 · panel 9' in text


@pytest.mark.parametrize('paid,word',[(True,'yes (api paidBy)'),(False,'no payer'),(None,'not known')])
async def test_detail_paid_three_states_never_exposes_payer(paid,word):
    async with _A(_row(paid=paid,paidBy=ADDRESS)).run_test(size=(120,60)) as pilot:
        await pilot.pause(); text='\n'.join(strips(pilot.app.screen))
        assert 'paid: '+word in text and ADDRESS not in text


async def test_plane_only_record_has_no_fabricated_local_section():
    async with _A(dict(jobId='b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70',source={'row':'api'},reply='cached reply',replyState='read')).run_test(size=(120,30)) as pilot:
        await pilot.pause(); text='\n'.join(strips(pilot.app.screen))
        assert 'LOCAL' not in text and 'PLANE' in text and 'cached reply' in text


async def test_enter_on_standing_only_job_does_not_invent_local_ledger_facts():
    from maxpane_dashboard.screens.seat_task_detail import SeatTaskDetail
    from tests.address_sweep.builders import _seat_app, _seat_payload

    flat = _seat_payload()
    standing = dict(key=None, jobId='b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70',
                    nodeId8='12345678', nodeKey='research_report', role='implement',
                    objective='Standing-only question', phase='working')
    flat['seat_current_jobs'] = [standing]
    flat['seat_jobs'] = [standing]
    flat['seat_tasks_rows'] = []
    async with _seat_app(flat).run_test(size=(170,55)) as pilot:
        await pilot.pause()
        await pilot.press('enter')
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatTaskDetail)
        text = '\n'.join(strips(pilot.app.screen))
        assert 'PLANE' in text and 'Standing-only question' in text
        assert 'LOCAL' not in text
        assert all(word not in text for word in ('api errors: none', 'flags: none', '(not reached)'))
