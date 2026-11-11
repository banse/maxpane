"""Observe presence labels on the real Boardroom screen."""
import pytest
from rich.color import Color

from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.data.test_surfboard_presence import setup, project
from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import hub_payload


@pytest.mark.parametrize('size', [(143,37),(149,45)])
async def test_refusing_card_and_retained_state_survive_screen_refresh(setup,size,monkeypatch):
    monkeypatch.delenv('NO_COLOR',raising=False)
    reader,raw,now,_=setup
    await reader._presence(650)
    row=project(reader,now[0])
    payload=hub_payload()
    payload['surfboard_cards']=[row if c['key']=='agent' else c for c in payload['surfboard_cards']]
    app=HubHarness(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        card=app.hub.query_one('#surfboard-card-agent',SurfboardCard)
        def strips():
            return [s.crop(card.region.x,card.region.right) for s in app.hub._compositor.render_strips()[card.region.y:card.region.bottom]]
        painted='\n'.join(s.text for s in strips())
        assert 'NOT ACCEPTING' in painted and '0 of 1' not in painted
        assert 'OFF' not in painted and 'active' not in painted
        box_bottom=next(s for s in strips() if '└' in s.text)
        caption=next(s for s in box_bottom if 'NOT ACCEPTING' in s.text)
        orange=Color.parse('#ff9f43').get_truecolor()
        assert caption.style.color.get_truecolor()==orange
        assert next(s for s in strips()[0] if '╭' in s.text).style.color.get_truecolor()!=orange
        assert next(s for row in strips() for s in row if '┌' in s.text).style.color.get_truecolor()==orange
        top=next(i for i,row in enumerate(strips()) if '┌' in row.text)
        left,right=strips()[top].text.index('┌'),strips()[top].text.index('┐')
        digit=next(s for row in strips()[top+1:top+4] for s in row.crop(left+1,right) if s.text.strip())
        active=app.hub.query_one('#surfboard-card-board',SurfboardCard)
        active_rows=[s.crop(active.region.x,active.region.right) for s in
                     app.hub._compositor.render_strips()[active.region.y:active.region.bottom]]
        active_top=next(i for i,s in enumerate(active_rows) if '┌' in s.text)
        active_digit=next(s for row in active_rows[active_top+1:active_top+4]
                          for s in row.crop(left+1,right) if s.text.strip())
        assert digit.style.color.get_truecolor()==active_digit.style.color.get_truecolor()
        work=app.hub.query_one('#surfboard-card-work',SurfboardCard)
        work_footer=app.hub._compositor.render_strips()[work.region.bottom-1].crop(work.region.x,work.region.right)
        gray=next(s for s in work_footer if 'workflows' in s.text).style.color.get_truecolor()
        assert strips()[-1].text.count('▱')==card.region.width-9 and '▰' not in strips()[-1].text
        assert next(s for s in strips()[-1] if 'NA' in s.text).style.color.get_truecolor()==gray
        bar=next(s for s in strips()[-1] if '▱' in s.text)
        assert bar.style.color.get_truecolor()==gray
        card.focus();await pilot.pause()
        for width in (size[0]+12,size[0]):
            await pilot.resize_terminal(width,size[1]);await pilot.pause()
            assert strips()[-1].text.count('▱')==card.region.width-9
            assert next(s for s in strips()[0] if '╭' in s.text).style.color.get_truecolor()!=orange
        original=[s.text for s in strips()]
        reader.manager.swarm_client.fetch_seat_standing.return_value=None
        await reader._presence(650)
        row.update(project(reader,now[0]))
        await app.hub._do_refresh();await pilot.pause()
        assert [s.text for s in strips()]==original
        assert card.data['status']=='stale'
        assert 'NA' in strips()[-1].text and '▱' in strips()[-1].text
        raw['standing']['working']=1
        reader.manager.swarm_client.fetch_seat_standing.return_value=raw
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        assert '1 of 1' in '\n'.join(s.text for s in strips())
        assert 'BUSY' in strips()[-1].text and '▰' in strips()[-1].text
        assert 'NOT ACCEPTING' not in '\n'.join(s.text for s in strips())
        assert next(s for s in strips()[0] if '╭' in s.text).style.color.get_truecolor()!=orange
        assert 'accepting work: no' in str(card.tooltip)
        raw['standing']['working']=0;raw['presence']['acceptingWork']=True
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        assert '0 of 1' in '\n'.join(s.text for s in strips())
        assert 'IDLE' in strips()[-1].text and 'BUSY' not in strips()[-1].text
        assert not any(c in strips()[-1].text for c in '▰▱')
        raw['standing']['working']=1;raw['presence']['acceptingWork']=False
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        reader.manager.swarm_client.fetch_seat_standing.return_value=None
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        assert 'BUSY' in strips()[-1].text and '▰' not in strips()[-1].text
        assert '1 of 1' in '\n'.join(s.text for s in strips())
        reader.manager.swarm_client.fetch_seat_standing.return_value=raw
        raw['presence']={'connected':False}
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        assert 'offline' in '\n'.join(s.text for s in strips()) and 'OFF' in strips()[-1].text
        row.update(token_id=None,primary='',secondary='type in',status='empty',meter_state='empty')
        await app.hub._do_refresh();await pilot.pause()
        assert 'NOT ACCEPTING' not in '\n'.join(s.text for s in strips())
        assert 'NA' not in strips()[-1].text
        assert next(s for s in strips()[0] if '╭' in s.text).style.color.get_truecolor()!=orange
