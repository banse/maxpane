import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from maxpane_dashboard.data.surf_manager import SurfManager
from tests.data.test_surfboard import capture

class Client:
    async def close(self):pass

@pytest.fixture
def manager(tmp_path):
    clock=SimpleNamespace(now=1000.)
    swarm=Client()
    swarm.fetch_overview=AsyncMock(return_value=capture('overview'))
    swarm.fetch_seat_records=AsyncMock(return_value=capture('records'))
    swarm.fetch_steps_hourly=AsyncMock(return_value=capture('hourly'))
    m=SurfManager(clock=lambda:clock.now,cache_path=str(tmp_path/'cache.json'),client=Client(),pool4_client=Client(),swarm_client=swarm,npm_client=Client(),seat=420)
    m._cycle=AsyncMock(return_value=m._blank_payload())
    return m,clock

async def test_shared_full_fetch_cancellation_isolated_and_interval_coalesced(manager):
    m,clock=manager; gate=asyncio.Event()
    async def blocked():
        await gate.wait();return m._blank_payload()
    m._cycle.side_effect=blocked
    a=asyncio.create_task(m.fetch_and_compute());b=asyncio.create_task(m.fetch_and_compute())
    await asyncio.sleep(0);await asyncio.sleep(0)
    a.cancel()
    with pytest.raises(asyncio.CancelledError):await a
    gate.set();await b
    await m.fetch_and_compute()
    assert m._cycle.await_count==1
    await m.close()

async def test_hub_sources_progress_while_full_startup_blocked(manager):
    m,clock=manager; gate=asyncio.Event()
    async def blocked():await gate.wait();return m._blank_payload()
    m._cycle.side_effect=blocked;m.set_hub_active(True)
    first=await m.fetch_hub_snapshot()
    assert first['surfboard_overview'] is None
    await asyncio.gather(*m._hub_source_tasks.values())
    second=await m.fetch_hub_snapshot()
    assert second['surfboard_overview']['agents_online']==864
    assert second['swarm_seat_outcome']['accepted']==3253
    assert m._cycle.await_count==1
    assert m.swarm_client.fetch_overview.await_count==1
    await m.close()

async def test_source_failure_retains_clock_and_backoff(manager):
    m,clock=manager;m.set_hub_active(True)
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    clock.now+=16;m.swarm_client.fetch_overview.return_value=None
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    result=await m.fetch_hub_snapshot()
    assert result['surfboard_sources']['overview']['read_ts']==1000
    assert result['surfboard_sources']['overview']['state']=='stale'
    assert m.swarm_client.fetch_overview.await_count==2
    await m.close()

async def ready(m):
    m.set_hub_active(True)
    await m.fetch_hub_snapshot()
    await asyncio.gather(*m._hub_source_tasks.values())

async def test_source_success_refreshes_read_clock_but_keeps_content_version(manager):
    m,clock=manager;await ready(m)
    before=(await m.fetch_hub_snapshot())['surfboard_sources']['overview']
    clock.now+=15
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    after=(await m.fetch_hub_snapshot())['surfboard_sources']['overview']
    assert after['read_ts']==1015 and before['read_ts']==1000
    assert after['version']==before['version']
    await m.close()

async def test_records_invalid_snapshot_retains_whole_old_version(manager):
    m,clock=manager;await ready(m)
    before=await m.fetch_hub_snapshot()
    m.swarm_client.fetch_seat_records.return_value=capture('bad_partition');clock.now+=120
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    after=await m.fetch_hub_snapshot()
    assert after['swarm_seat_outcome']==before['swarm_seat_outcome']
    assert after['swarm_outcomes_source']['state']=='stale'
    assert after['swarm_outcomes_source']['read_ts']==1000
    await m.close()

async def test_hourly_only_eligible_in_hub_and_overview_uses_background_cadence(manager):
    m,clock=manager
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_steps_hourly.await_count==0
    clock.now+=15
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_overview.await_count==1
    m.set_hub_active(True)
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_steps_hourly.await_count==1
    assert m.swarm_client.fetch_overview.await_count==2
    await m.close()

async def test_commands_canonical_outcome_and_read_only_navigation(manager):
    m,_=manager;await ready(m)
    result=await m.execute_hub_command('seat #420')
    assert '3,253 / 3,392' in result['lines'][0]
    selected=m._seat_saved
    result=await m.execute_hub_command('open #1836')
    assert result['intent']=='open_seat' and result['token_id']==1836 and m._seat_saved==selected
    result=await m.execute_hub_command('open dc4e3a')
    assert result['url']=='https://explorer.imd.fun/jobs/dc4e3a21-8e12-44c3-9a6d-ae180f5c8c60'
    assert (await m.execute_hub_command('open https://evil.invalid'))['intent'] is None
    assert (await m.execute_hub_command('clear'))['clear']
    assert len((await m.execute_hub_command('grep captured'))['lines'])<=20
    await m.close()

async def test_old_rank_basis_is_discarded_without_clearing_other_history(manager):
    m,_=manager
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT_RANK
    m.cache.store_last_good(SLOT_SWARM_SEAT_RANK,{'420':{'rank':999,'prev':1000}},ts=1000)
    await ready(m)
    data=await m.fetch_hub_snapshot()
    assert data['swarm_seat_rank_delta'] is None
    assert m.cache.get_last_good(SLOT_SWARM_SEAT_RANK).payload['basis']=='seat-records-v1'
    assert m._seat_saved==420
    await m.close()

async def test_close_twice_and_fetch_after_close_do_not_restart_work(manager):
    m,_=manager;m.client.close=AsyncMock()
    await ready(m);await m.close();await m.close()
    await m.fetch_hub_snapshot();await m.fetch_and_compute()
    assert m.client.close.await_count==1
    assert all(t.done() for t in m._hub_source_tasks.values())

async def test_identity_lookup_preserves_canonical_counts_and_is_bounded(manager):
    from tests.data.test_surf_manager_swarm import _seat_payload_of
    m,_=manager;await ready(m)
    seat=_seat_payload_of(420)
    seat['attempts']=9999;seat['accepted']=0
    m.swarm_client.fetch_seat=AsyncMock(return_value=seat)
    first=await m.execute_hub_command('seat 420')
    assert '3,253 / 3,392' in first['lines'][0]
    assert first['lines'][-1].startswith('Owner ')
    await m.execute_hub_command('seat 420')
    assert m.swarm_client.fetch_seat.await_count==1
    assert (await m.fetch_hub_snapshot())['swarm_seat_outcome']['attempts']==3392
    await m.close()

async def test_lookup_busy_reply_and_close_cancel_only_owned_task(manager):
    m,_=manager;await ready(m)
    entered=asyncio.Event();gate=asyncio.Event()
    async def lookup(name):
        entered.set();await gate.wait()
    m.client.fetch_ens_address=lookup
    command=asyncio.create_task(m.execute_hub_command('find surf.eth'))
    await entered.wait()
    assert 'already running' in (await m.execute_hub_command('find second.eth'))['lines'][0]
    await m.close()
    with pytest.raises(asyncio.CancelledError):await command
    assert m._hub_lookup_task.cancelled()

async def test_status_reports_each_service_up_down_or_unavailable(manager):
    m,_=manager
    m.swarm_client.fetch_overview.return_value['health'].update(verifierUp=False,publisherUp=True,deployerUp=None)
    await ready(m)
    lines='\n'.join((await m.execute_hub_command('status'))['lines'])
    assert 'verifier down' in lines and 'publisher up' in lines and 'deployer unavailable' in lines
    await m.close()

async def test_cards_use_legacy_source_failure_and_success_clocks(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD,SLOT_POOL4,SLOT_CHANNEL,SLOT_MARKET,TIER_LAUNCHPAD,TIER_POOL4
    m,clock=manager
    m._last_full_payload=m._blank_payload()
    m._last_full_payload.update(pool4_price_usd=2.,pool4_vault_assets=20,pool4_total_supply=100,launchpad_coin_count=1,launchpad_new_24h=0)
    for slot in (SLOT_POOL4,SLOT_CHANNEL,SLOT_MARKET):m.cache.store_last_good(slot,{},ts=900)
    lp={'coin_count':1,'launch_count':1,'new_24h':0,'cursor':{'last_block':1,'launches':{'a':{}}},'swaps_by_coin':{'a':1}}
    m.cache.store_last_good(SLOT_LAUNCHPAD,lp,ts=900)
    m.cache.mark_fetched(TIER_POOL4,910);m.cache.mark_fetched(TIER_LAUNCHPAD,910)
    m.cache.mark_failed(TIER_POOL4,950);m.cache.mark_failed(TIER_LAUNCHPAD,950)
    cards={c['key']:c for c in m._project_hub(refresh_legacy=False)['surfboard_cards']}
    assert cards['launchpad']['status']=='stale'
    assert cards['pool4']['status']=='stale'
    assert 'pool4 stale · read '+__import__('maxpane_dashboard.data.surfboard',fromlist=['hhmm']).hhmm(910) in cards['pool4']['detail']
    assert 'market' in cards['pool4']['detail'] and 'read' in cards['pool4']['detail']
    await m.close()

async def test_legacy_source_success_clears_failure_without_retimestamping_content(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD,TIER_LAUNCHPAD
    from maxpane_dashboard.data import surfboard as hub
    m,clock=manager
    m.cache.store_last_good(SLOT_LAUNCHPAD,{'coin_count':1},ts=800)
    m.cache.mark_fetched(TIER_LAUNCHPAD,850)
    m.cache.mark_failed(TIER_LAUNCHPAD,900)
    first=m._hub_card_sources({})['launchpad']
    assert first=={'state':'stale','read_ts':850}
    m.cache.mark_fetched(TIER_LAUNCHPAD,950)
    assert m._hub_card_sources({})['launchpad']=={'state':'ok','read_ts':950}
    assert m.cache.get_last_good(SLOT_LAUNCHPAD).ts==800
    clock.now=1551
    assert m._hub_card_sources({})['launchpad']['state']=='stale'
    await m.close()
