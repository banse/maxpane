"""Selected-seat presence is independent of admission to the worker list."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surfboard as hub, surfboard_activity as activity, surf_swarm as sw
from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from tests.surf_swarm_fixtures import swarm_capture_v3


def captured(token=650):
    return json.loads(Path('tests/fixtures/surf/work/selected_seat_presence.json').read_text())['standings'][str(token)]


@pytest.fixture
def setup():
    raw = captured(); now = [sw._ts(raw['at'])]
    selected = [650, None, None, None]
    manager = SimpleNamespace(_clock=lambda: now[0], get_hub_seats=lambda: tuple(selected),
        _hub_active=True, _closing=False, _retired_reads=set(),
        swarm_client=SimpleNamespace(fetch_seat_standing=AsyncMock(return_value=raw)))
    return SurfCardReader(manager), raw, now, selected


def project(reader, now, *, workers=None):
    workers = sw.normalize_workers(workers or swarm_capture_v3('workers'))
    return next(c for c in hub.cards({}, {}, now=now,
        agent_seats=[dict(token_id=650, live=sw._seat_live_from_slot(workers,650),
                          api_status='active', presence=reader.presence_snapshot(650))],
        activity=activity.observe(None,workers,now=now)) if c['key']=='agent')


async def test_connected_refusing_seat_is_not_offline(setup):
    reader, raw, now, _ = setup
    await reader._presence(650)
    card = project(reader,now[0])
    assert (card['status'],card['meter_state'],card['secondary']) == ('not_accepting','not_accepting','0 of 1 slots')
    assert 'standing read' in card['detail'] and 'accepting work: no' in card['detail']
    assert raw == captured()


@pytest.mark.parametrize('change,state', [('idle','idle'),('busy','working'),('refusing_busy','working'),('disconnected','offline'),('absent','offline'),('heartbeat','offline')])
async def test_direct_presence_drives_state_without_worker_membership(setup,change,state):
    reader, raw, now, _ = setup
    if change=='idle':raw['presence']['acceptingWork']=True
    if change in ('busy','refusing_busy'):
        raw['standing']['working']=2
        raw['presence']['acceptingWork']=change=='busy'
    if change=='disconnected':raw['presence']={'connected':False}
    # Public standing for offline seats 3/420 returned explicit null on 2026-11-11.
    if change=='absent':raw['presence']=None
    if change=='heartbeat':raw['presence']['stale']=True
    await reader._presence(650)
    card=project(reader,now[0])
    assert card['status']==state
    if change=='refusing_busy':
        assert card['secondary']=='2 working' and 'accepting work: no' in card['detail']
    if state=='offline':assert card['secondary']=='offline'


async def test_missing_worker_row_without_standing_is_unknown(setup):
    reader,_,now,_=setup
    card=project(reader,now[0])
    assert card['status']=='unavailable' and card['meter_state']=='unavailable'
    assert card['secondary']=='— of — slots'


@pytest.mark.parametrize('bad',['failure','identity','boolean','count','capacity','old','future','missing_presence','malformed_presence'])
async def test_bad_read_preserves_observation_and_clock_without_live_bar(setup,bad):
    reader,raw,now,_=setup
    await reader._presence(650)
    before=reader.presence_snapshot(650)
    now[0]+=61
    raw['at']=datetime.fromtimestamp(now[0],timezone.utc).isoformat()
    if bad=='failure':reader.manager.swarm_client.fetch_seat_standing.return_value=None
    if bad=='identity':raw['tokenId']='420'
    if bad=='boolean':raw['presence']['connected']=1
    if bad=='count':raw['standing']['working']=True
    if bad=='capacity':raw['presence']['maxConcurrency']=-1
    if bad=='old':raw['at']=captured()['at']
    if bad=='future':raw['at']=datetime.fromtimestamp(now[0]+10,timezone.utc).isoformat()
    if bad=='missing_presence':raw.pop('presence')
    if bad=='malformed_presence':raw['presence']=[]
    await reader._presence(650)
    after=reader.presence_snapshot(650)
    assert after['read_ts']==before['read_ts'] and after['working']==0
    assert after['state']=='stale'
    card=project(reader,now[0])
    assert card['status']=='stale' and card['secondary']=='0 of 1 slots'
    assert card['meter_kind']=='presence'


async def test_aging_a_good_observation_does_not_prove_offline(setup):
    reader,_,now,_=setup
    await reader._presence(650)
    now[0]+=301
    assert reader.presence_snapshot(650)['state']=='stale'
    assert project(reader,now[0])['status']=='stale'


async def test_retired_request_cannot_publish_after_same_token_is_reassigned(setup):
    reader,raw,now,selected=setup
    entered,release=asyncio.Event(),asyncio.Event()
    async def delayed(token):
        entered.set()
        try: await release.wait()
        except asyncio.CancelledError: await release.wait()
        return raw
    reader.manager.swarm_client.fetch_seat_standing.side_effect=delayed
    task=asyncio.create_task(reader._presence(650)); reader.tasks['presence:650']=task
    await entered.wait()
    selected[:]=[3,None,None,None]; reader.sync_presence()
    selected[:]=[650,None,None,None]; reader.sync_presence()
    release.set(); await task
    assert reader.presence_snapshot(650) is None


async def test_presence_budget_is_unique_and_force_does_not_bypass_retry_delay(setup):
    reader,raw,now,selected=setup
    selected[:]=[650,650,None,None]
    reader.signals.readers=lambda **kw:[]
    for name in ('_seat','_work','_research','_current','_pool','_feed','_market'):
        setattr(reader,name,AsyncMock())
    reader.offer(force=True); await reader.wait_pending()
    client=reader.manager.swarm_client
    assert client.fetch_seat_standing.await_count==1
    now[0]+=59;reader.offer(force=True);await reader.wait_pending()
    assert client.fetch_seat_standing.await_count==1
    now[0]+=1;raw['at']=datetime.fromtimestamp(now[0],timezone.utc).isoformat()
    reader.offer(force=True);await reader.wait_pending()
    assert client.fetch_seat_standing.await_count==2


async def test_public_idle_seats_keep_their_counts_and_snapshot_is_copied(setup):
    reader,_,now,selected=setup
    for token,capacity in ((3,3),(7,4),(420,3)):
        raw=captured(token); now[0]=sw._ts(raw['at']);selected[0]=token
        reader.manager.swarm_client.fetch_seat_standing.return_value=raw
        await reader._presence(token)
        snapshot=reader.presence_snapshot(token)
        assert (snapshot['live_state'],snapshot['working'],snapshot['max_concurrency'])==('idle',0,capacity)
        snapshot['working']=99
        assert reader.presence_snapshot(token)['working']==0


@pytest.mark.parametrize('token', [3, 420])
async def test_explicit_absent_presence_paints_offline_instead_of_zero_capacity(setup, token):
    from tests.widgets.test_surfboard_rack import RackApp, SurfboardCard, card_strips
    reader, _, now, selected = setup
    raw = captured(token)
    raw['presence'] = None  # Observed public offline form; not a missing field.
    now[0] = sw._ts(raw['at']); selected[0] = token
    reader.manager.swarm_client.fetch_seat_standing.return_value = raw
    await reader._presence(token)
    row = next(c for c in hub.cards({}, {}, now=now[0], agent_seats=[dict(
        token_id=token, presence=reader.presence_snapshot(token))]) if c['key']=='agent')
    assert reader.presence_snapshot(token)['max_concurrency'] is None
    async with RackApp().run_test(size=(149,45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-agent', SurfboardCard)
        card.set_data(row)
        await pilot.pause()
        painted = '\n'.join(s.text for s in card_strips(pilot.app, card))
        assert 'offline' in painted and 'OFF' in painted
        assert '0 of 0' not in painted
        assert '▱' in painted and '▰' not in painted


async def test_fresh_positive_worker_can_replace_retained_standing(setup):
    reader,_,now,_=setup
    await reader._presence(650)
    now[0]+=301
    raw=swarm_capture_v3('workers')
    row=deepcopy(raw['workers'][0]);row['seat']['tokenId']='650'
    row.update(working=1,maxConcurrency=3)
    raw.update(workers=[row],count=1)
    card=project(reader,now[0],workers=raw)
    assert (card['status'],card['secondary'])==('working','1 of 3 slots')
    assert 'last observed presence' in card['detail']


async def test_cancelled_presence_read_keeps_old_values_and_marks_source_stale(setup):
    reader,_,now,_=setup
    await reader._presence(650)
    stamp=reader.presence_snapshot(650)['read_ts']
    entered=asyncio.Event()
    async def blocked(token):
        entered.set();await asyncio.Event().wait()
    reader.manager.swarm_client.fetch_seat_standing.side_effect=blocked
    task=asyncio.create_task(reader._presence(650))
    await entered.wait()
    assert reader.presence_snapshot(650)['state']=='ok'
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert reader.presence_snapshot(650)['state']=='stale'
    assert reader.presence_snapshot(650)['read_ts']==stamp
    assert project(reader,now[0])['secondary']=='0 of 1 slots'
