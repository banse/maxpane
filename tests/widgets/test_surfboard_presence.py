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
        assert 'NOT ACCEPTING' in painted and '0 of 1' in painted
        assert 'OFF' not in painted and 'active' not in painted
        caption=next(s for s in strips()[-1] if 'NOT ACCEPTING' in s.text)
        # Textual's border caption promotes ANSI yellow to its bright counterpart.
        assert caption.style.color.get_truecolor()==Color.parse('bright_yellow').get_truecolor()
        original=[s.text for s in strips()]
        reader.manager.swarm_client.fetch_seat_standing.return_value=None
        await reader._presence(650)
        row.update(project(reader,now[0]))
        await app.hub._do_refresh();await pilot.pause()
        assert [s.text for s in strips()]==original
        assert card.data['status']=='stale'
        assert not any(c in strips()[-1].text for c in '▰▱')
        raw['standing']['working']=1
        reader.manager.swarm_client.fetch_seat_standing.return_value=raw
        await reader._presence(650)
        row.update(project(reader,now[0]));await app.hub._do_refresh();await pilot.pause()
        assert '1 of 1' in '\n'.join(s.text for s in strips())
        assert 'BUSY' in strips()[-1].text and '▰' in strips()[-1].text
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
