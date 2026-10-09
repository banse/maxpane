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
    from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
    from tests.data.test_swarm_tokens_live import Pages, Market
    m._swarm_tokens_manager = SwarmTokensManager(m, client=Pages(), market=Market(), clock=lambda: clock.now)
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


async def test_announce_card_counts_full_channel_snapshot_not_visible_feed(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_CHANNEL
    m,clock=manager
    rows=[dict(kind=('self','reply','answer')[i%3],ts=999,tx_hash=f'0x{i:064x}') for i in range(40)]
    m._last_full_payload=dict(feed_items=rows[:25])
    m.cache.store_last_good(SLOT_CHANNEL,dict(items=rows),ts=999)
    try:
        for refresh in (False,True):
            data=m._project_hub(refresh_legacy=refresh)
            assert data['surfboard_cards'][0]['secondary']=='40 new posts'
        m.cache.store_last_good(SLOT_CHANNEL,dict(items=[rows[0]]),ts=1000)
        assert m._project_hub()['surfboard_cards'][0]['secondary']=='1 new post'
        clock.now=999+86400
        assert m._project_hub()['surfboard_cards'][0]['secondary']=='0 new posts'
    finally:
        await m.close()

async def test_source_failure_retains_clock_and_backoff(manager):
    m,clock=manager;m.set_hub_active(True)
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    clock.now+=31;m.swarm_client.fetch_overview.return_value=None
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
    clock.now+=30
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    after=(await m.fetch_hub_snapshot())['surfboard_sources']['overview']
    assert after['read_ts']==1030 and before['read_ts']==1000
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
    clock.now+=30
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_overview.await_count==1
    m.set_hub_active(True)
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_steps_hourly.await_count==1
    assert m.swarm_client.fetch_overview.await_count==2
    await m.close()

async def test_visible_hub_waits_thirty_seconds_and_keeps_the_source_fresh(manager):
    m,clock=manager;await ready(m)
    for elapsed in (15,29):
        clock.now=1000+elapsed
        result=await m.fetch_hub_snapshot()
        await asyncio.gather(*m._hub_source_tasks.values())
        assert m.swarm_client.fetch_overview.await_count==1
        assert result['surfboard_sources']['overview']['state']=='ok'
    clock.now=1030
    await m.fetch_hub_snapshot();await asyncio.gather(*m._hub_source_tasks.values())
    assert m.swarm_client.fetch_overview.await_count==2
    assert m._hub_sources()['overview']['read_ts']==1030
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


async def test_footer_sources_are_independent_and_use_injected_clock(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_MARKET
    from maxpane_dashboard.data.surf_manager import SOURCE_MARKET
    m, clock = manager
    raw = capture('overview'); raw.update(capture('footer_counts'))
    m.swarm_client.fetch_overview.return_value = raw
    m.cache.store_last_good(SLOT_MARKET, {'market_cap_usd': 2_345_678, 'fdv_usd': 9_876_543}, ts=995)
    await ready(m)
    footer = m._project_hub()['surfboard_footer']
    assert footer == {
        'market_value_usd': 2_345_678, 'market_basis': 'market_cap', 'market_state': 'ok', 'market_read_ts': 995,
        'inference_tokens': 189121393249, 'overview_state': 'ok', 'overview_read_ts': 1000,
        'provider_ts': raw['at'] / 1000, 'as_of': 1000,
    }
    clock.now = 1016
    m.swarm_client.fetch_overview.return_value = None
    await m._read_hub_source('overview', m._hub_sources()['overview'])
    failed = m._project_hub()['surfboard_footer']
    assert failed == dict(footer, overview_state='stale', as_of=1016)
    m._failed_groups.add(SOURCE_MARKET)
    assert m._project_hub()['surfboard_footer'] == dict(failed, market_state='stale')
    m._failed_groups.clear()
    clock.now = 1086
    assert m._project_hub()['surfboard_footer'] == dict(failed, market_state='stale', as_of=1086)
    await m.close()


@pytest.mark.parametrize('cap,fdv,value,basis', [
    (0, 200, 0, 'market_cap'), (None, 200, 200, 'fdv'), (True, 200, 200, 'fdv'),
    (-1, 0, 0, 'fdv'), (float('inf'), 200, 200, 'fdv'), (float('nan'), 200, 200, 'fdv'),
    (None, True, None, None), (None, -1, None, None), (None, float('inf'), None, None),
    (None, None, None, None),
])
async def test_footer_validates_restored_market_values_and_labels_fdv(manager, cap, fdv, value, basis):
    from maxpane_dashboard.data.surf_cache import SLOT_MARKET
    m, clock = manager
    m.cache.store_last_good(SLOT_MARKET, {'market_cap_usd': cap, 'fdv_usd': fdv}, ts=990)
    footer = m._project_hub()['surfboard_footer']
    assert footer['market_value_usd'] == value and footer['market_basis'] == basis
    assert footer['market_read_ts'] == 990 and footer['market_state'] == 'ok'
    assert footer['inference_tokens'] is None and footer['overview_state'] == 'unavailable'
    assert footer['overview_read_ts'] is None and footer['provider_ts'] is None
    await m.close()


async def test_footer_cold_cache_uses_unknowns_and_no_fake_zero(manager):
    m, clock = manager
    assert m._project_hub()['surfboard_footer'] == {
        'market_value_usd': None, 'market_basis': None, 'market_state': 'unavailable', 'market_read_ts': None,
        'inference_tokens': None, 'overview_state': 'unavailable', 'overview_read_ts': None,
        'provider_ts': None, 'as_of': 1000,
    }
    await m.close()


def test_market_payload_carries_verified_cap_and_fdv_without_requiring_new_field():
    from tests.data.test_surf_manager import _market
    snap = _market(market_cap_usd=456.0, fdv_usd=789.0)
    assert SurfManager._market_payload(snap)['market_cap_usd'] == 456.0
    assert SurfManager._market_payload(snap)['fdv_usd'] == 789.0
    assert SurfManager._market_payload(_market())['market_cap_usd'] is None


async def test_old_overview_snapshot_survives_failed_read_until_tokens_arrive(manager):
    from maxpane_dashboard.data import surfboard as hub
    m, clock = manager
    old = hub.normalize_overview(capture('overview'))
    old['overview'].pop('inference_tokens')
    m.cache.store_last_good(hub.SOURCE_SLOTS['overview'], hub.source_envelope(old, 999), ts=999)
    footer = m._project_hub()['surfboard_footer']
    assert footer['inference_tokens'] is None and footer['overview_state'] == 'ok'
    assert footer['overview_read_ts'] == 999
    m.swarm_client.fetch_overview.return_value = None
    await m._read_hub_source('overview', m._hub_sources()['overview'])
    failed = m._project_hub()
    assert failed['surfboard_overview'] == dict(old['overview'], inference_tokens=None)
    assert failed['surfboard_events'] == old['events']
    assert failed['surfboard_footer'] == dict(footer, overview_state='stale')
    m.swarm_client.fetch_overview.return_value = capture('overview')
    clock.now += 30
    await m._read_hub_source('overview', m._hub_sources()['overview'])
    assert m._project_hub()['surfboard_footer']['inference_tokens'] == 188932748311
    assert m._project_hub()['surfboard_footer']['overview_read_ts'] == 1030
    await m.close()


async def test_tokens_card_shares_retained_catalogue_and_ages_news_without_full_read(manager):
    m, clock = manager
    m._last_full_payload = dict(as_of=1000, swarm_launch_fired=[dict(ts=1000., number=1210)])
    m._offer_full = lambda now: None
    try:
        first = await m.fetch_hub_snapshot()
        assert next(c for c in first['surfboard_cards'] if c['key']=='swarm-tokens')['primary'] == 'unavailable'
        adapter = m.swarm_tokens_manager()
        await adapter.wait_pending()
        second = await m.fetch_hub_snapshot()
        card = next(c for c in second['surfboard_cards'] if c['key']=='swarm-tokens')
        assert (card['primary'], card['secondary'], card['status']) == ('3', '1 new', 'active')
        assert adapter is m.swarm_tokens_manager()
        assert set(adapter._tasks) == {'catalogue'}
        clock.now = 4600
        card = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert (card['primary'], card['secondary'], card['status']) == ('3', '0 new', 'idle')
        assert 'catalogue stale' in card['detail']
    finally:
        await m.close()
    assert adapter._closed
