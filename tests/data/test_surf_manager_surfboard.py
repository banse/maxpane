import asyncio
import json
from pathlib import Path
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
    swarm.fetch_jobs=AsyncMock(return_value=None)
    swarm.fetch_oracle_requests=AsyncMock(return_value=None)
    swarm.fetch_oracle_detail=AsyncMock(return_value=None)
    m=SurfManager(clock=lambda:clock.now,cache_path=str(tmp_path/'cache.json'),client=Client(),pool4_client=Client(),swarm_client=swarm,npm_client=Client(),seat=420)
    base=Client(); base.fetch_imd_global_supply=AsyncMock(return_value=None)
    m._launch_rpc_clients[8453]=base
    from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
    from tests.data.test_swarm_tokens_live import Pages, Market
    m._swarm_tokens_manager = SwarmTokensManager(m, client=Pages(), market=Market(), clock=lambda: clock.now)
    m._cycle=AsyncMock(return_value=m._blank_payload())
    return m,clock


async def test_hub_work_card_shares_completed_snapshot_with_dashboard(manager):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock.now = raw['read_ts']
    entered, release = asyncio.Event(), asyncio.Event()
    async def jobs(*, limit):
        entered.set()
        await release.wait()
        return raw['jobs']
    m.swarm_client.fetch_jobs = AsyncMock(side_effect=jobs)
    m.swarm_client.fetch_workflows = AsyncMock(return_value=raw['workflows'])
    m.swarm_client.fetch_job = AsyncMock(side_effect=lambda identity: next(
        (d for d in raw['details'] if d['id']==identity), None))
    m.set_hub_active(True)
    try:
        first = await m.fetch_hub_snapshot()
        row = next(c for c in first['surfboard_cards'] if c['key']=='work')
        assert row['status']=='loading' and row['primary']=='—'
        await asyncio.wait_for(entered.wait(), 1)
        task = m._work_reader.task
        await m.fetch_hub_snapshot()
        assert m._work_reader.task is task
        release.set()
        await task
        second = await m.fetch_hub_snapshot()
        row = next(c for c in second['surfboard_cards'] if c['key']=='work')
        assert row['primary']=='2'
        assert row['work_summary']==second['surf_work']['summary']
        assert row['meter_state']==second['surf_work']['state']=='ok'
        m.set_work_active(True)
        m.set_hub_active(False)
        dashboard = await m.fetch_and_compute()
        assert dashboard['surf_work']==second['surf_work']
        assert m._work_reader.task is task
        m.swarm_client.fetch_jobs.assert_awaited_once_with(limit=100)
        m.swarm_client.fetch_workflows.assert_awaited_once_with(limit=100)
    finally:
        await m.close()


@pytest.mark.parametrize('first', ['hub', 'work'])
async def test_work_reader_cancels_only_after_both_consumers_leave(manager, first):
    m, _ = manager
    entered = asyncio.Event()
    async def jobs(*, limit):
        entered.set()
        await asyncio.Event().wait()
    m.swarm_client.fetch_jobs = AsyncMock(side_effect=jobs)
    other = 'work' if first=='hub' else 'hub'
    getattr(m, f'set_{first}_active')(True)
    try:
        await (m.fetch_hub_snapshot() if first=='hub' else m.fetch_and_compute())
        await asyncio.wait_for(entered.wait(), 1)
        task = m._work_reader.task
        getattr(m, f'set_{other}_active')(True)
        getattr(m, f'set_{first}_active')(False)
        assert not task.cancelling()
        getattr(m, f'set_{other}_active')(False)
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
    finally:
        await m.close()


@pytest.mark.parametrize('first', ['hub', 'work'])
@pytest.mark.parametrize('destination', ['hub', 'work'])
async def test_work_reentry_restarts_cancelled_refresh_and_replaces_cached_data(manager, first, destination):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock.now = raw['read_ts']
    entered = asyncio.Event()
    calls = 0
    async def jobs(*, limit):
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            await asyncio.Event().wait()
        return raw['jobs']
    m.swarm_client.fetch_jobs = AsyncMock(side_effect=jobs)
    m.swarm_client.fetch_workflows = AsyncMock(return_value=raw['workflows'])
    m.swarm_client.fetch_job = AsyncMock(side_effect=lambda identity: next(
        (d for d in raw['details'] if d['id'] == identity), None))
    fetch = m.fetch_hub_snapshot if first == 'hub' else m.fetch_and_compute
    getattr(m, f'set_{first}_active')(True)
    try:
        await fetch()
        await m._work_reader.task
        assert m._work_reader.project()['summary']['jobs'] == 2
        clock.now += 60
        await fetch()
        await asyncio.wait_for(entered.wait(), 1)
        previous = m._work_reader.task
        raw['jobs'][0]['state'] = raw['details'][0]['state'] = 'completed'
        # Suspend can cancel the old fetch immediately before resume offers one.
        getattr(m, f'set_{first}_active')(False)
        getattr(m, f'set_{destination}_active')(True)
        await (m.fetch_hub_snapshot() if destination == 'hub' else m.fetch_and_compute())
        replacement = m._work_reader.task
        assert replacement is not previous
        assert not replacement.cancelling()
        assert m._work_reader.project()['summary']['jobs'] == 2
        await asyncio.wait_for(replacement, 1)
        assert previous.cancelled()
        data = m.get_hub_snapshot()
        assert data['surf_work']['summary']['jobs'] == 1
        assert data['surf_work']['read_ts'] == clock.now
        assert next(c for c in data['surfboard_cards'] if c['key'] == 'work')['primary'] == '1'
        assert calls == 3
    finally:
        await m.close()


async def test_inactive_or_closing_hub_does_not_offer_work(manager):
    m, _ = manager
    try:
        await m.fetch_hub_snapshot()
        assert m._work_reader.task is None
        m.set_hub_active(True)
        m._closing = True
        await m.fetch_hub_snapshot()
        assert m._work_reader.task is None
        m.swarm_client.fetch_jobs.assert_not_awaited()
    finally:
        m._closing = False
        await m.close()


async def test_hub_oracles_share_list_native_detail_and_retained_failure_clock(manager):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/oracles/captured.json').read_text())
    clock.now = raw['read_ts']
    entered, release = asyncio.Event(), asyncio.Event()
    async def requests(*, limit):
        entered.set(); await release.wait()
        return raw['requests']
    m.swarm_client.fetch_oracle_requests = AsyncMock(side_effect=requests)
    m.swarm_client.fetch_oracle_detail = AsyncMock(side_effect=lambda key: raw['details'].get(key))
    m.set_hub_active(True)
    try:
        first = await m.fetch_hub_snapshot()
        assert next(c for c in first['surfboard_cards'] if c['key'] == 'oracles')['primary'] == '—'
        await asyncio.wait_for(entered.wait(), 1)
        task = m._oracles_reader.task
        await m.fetch_hub_snapshot()
        assert m._oracles_reader.task is task
        release.set(); await task
        m.swarm_client.fetch_oracle_detail.assert_not_awaited()
        second = await m.fetch_hub_snapshot()
        card = next(c for c in second['surfboard_cards'] if c['key'] == 'oracles')
        assert card['denominator'] == len(second['surf_oracles']['rows']) == 100
        assert card['primary'] == str(sum(r['status'] == 'assessing' for r in second['surf_oracles']['rows']))
        assert card['secondary'] == 'in progress' and card['meter_state'] == 'partial'
        m.set_oracles_active(True); m.set_hub_active(False)
        m._offer_full = lambda _: pytest.fail('unrelated collection in oracle mode')
        native = await m.fetch_and_compute()
        assert native['surf_oracles']['rows'] == second['surf_oracles']['rows']
        await m._oracles_reader.task
        m.swarm_client.fetch_oracle_requests.assert_awaited_once_with(limit=100)
        m.swarm_client.fetch_oracle_detail.assert_awaited_once()
        clock.now += 60
        raw['requests'] = None
        await m.fetch_and_compute(); await m._oracles_reader.task
        stale = m._project_hub()
        retained = next(c for c in stale['surfboard_cards'] if c['key'] == 'oracles')
        assert stale['surf_oracles']['read_ts'] == raw['read_ts']
        assert retained['primary'] == card['primary']
        assert retained['meter_state'] == retained['status'] == 'stale'
        assert retained['secondary'] == 'in progress'
        clock.now += 119
        await m.fetch_and_compute()
        assert m.swarm_client.fetch_oracle_requests.await_count == 2
    finally:
        await m.close()


@pytest.mark.parametrize('first', ['hub', 'oracles'])
async def test_oracle_list_cancels_only_after_both_consumers_leave(manager, first):
    m, _ = manager
    entered = asyncio.Event()
    async def requests(*, limit):
        entered.set(); await asyncio.Event().wait()
    m.swarm_client.fetch_oracle_requests = AsyncMock(side_effect=requests)
    other = 'oracles' if first == 'hub' else 'hub'
    getattr(m, f'set_{first}_active')(True)
    try:
        await (m.fetch_hub_snapshot() if first == 'hub' else m.fetch_and_compute())
        await asyncio.wait_for(entered.wait(), 1)
        task = m._oracles_reader.task
        getattr(m, f'set_{other}_active')(True)
        getattr(m, f'set_{first}_active')(False)
        assert not task.cancelling()
        getattr(m, f'set_{other}_active')(False)
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
    finally:
        await m.close()


@pytest.mark.parametrize('first', ['hub', 'oracles'])
async def test_oracle_route_restarts_cancelling_list_without_waiting_for_poll(manager, first):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/oracles/captured.json').read_text())
    clock.now = raw['read_ts']
    entered = asyncio.Event()
    calls = 0
    async def requests(*, limit):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set(); await asyncio.Event().wait()
        return raw['requests']
    m.swarm_client.fetch_oracle_requests = AsyncMock(side_effect=requests)
    m.swarm_client.fetch_oracle_detail = AsyncMock(side_effect=lambda key: raw['details'].get(key))
    other = 'oracles' if first == 'hub' else 'hub'
    getattr(m, f'set_{first}_active')(True)
    try:
        await (m.fetch_hub_snapshot() if first == 'hub' else m.fetch_and_compute())
        await asyncio.wait_for(entered.wait(), 1)
        previous = m._oracles_reader.task
        # Screen suspend precedes the destination screen's resume event.
        getattr(m, f'set_{first}_active')(False)
        getattr(m, f'set_{other}_active')(True)
        await (m.fetch_hub_snapshot() if other == 'hub' else m.fetch_and_compute())
        replacement = m._oracles_reader.task
        assert replacement is not previous
        await asyncio.wait_for(replacement, 1)
        assert previous.cancelled()
        assert m.get_oracles_snapshot()['rows']
        assert calls == 2
        assert m.swarm_client.fetch_oracle_detail.await_count == (other == 'oracles')
    finally:
        await m.close()

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
            assert data['surfboard_cards'][0]['secondary']=='26 new replies'
        m.cache.store_last_good(SLOT_CHANNEL,dict(items=[rows[0]]),ts=1000)
        assert m._project_hub()['surfboard_cards'][0]['secondary']=='0 new replies'
        clock.now=999+86400
        assert m._project_hub()['surfboard_cards'][0]['secondary']=='0 new replies'
    finally:
        await m.close()


async def test_news_hero_projects_full_cached_channel_and_independent_source_clocks(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_CHANNEL, SLOT_ACTIVITY, SLOT_NFT, SLOT_MARKET, SLOT_LAUNCHPAD
    m, clock = manager
    rows = [dict(kind="reply", ts=999-i, text=f"reply {i}", tx_hash=f"0x{i:064x}") for i in range(30)]
    rows.append(dict(kind="self", ts=800, text="official announcement", tx_hash="0x" + "f"*64))
    m._last_full_payload = dict(feed_items=rows[:25], imd_price_usd=123)
    m.cache.store_last_good(SLOT_CHANNEL, dict(items=rows), ts=980)
    m.cache.store_last_good(SLOT_ACTIVITY, dict(rows=[]), ts=800)
    m.cache.store_last_good(SLOT_NFT, dict(nft_holders=12, nft_written=1, nft_transfers_24h=0), ts=800)
    m.cache.store_last_good(SLOT_MARKET, dict(imd_price_usd=9, eth_usd=2000), ts=990)
    m.cache.store_last_good(SLOT_LAUNCHPAD, dict(sqrt_price_x96=2**96), ts=300)
    try:
        for refresh in (False, True):
            result = m._project_hub(refresh_legacy=refresh)["surf_news_hero"]
            assert result["announcement"] == dict(state="ok", read_ts=980, text="official announcement", age_s=200)
            assert result["reply"]["text"] == "reply 0"
            assert result["activity"]["rows"] == []
            assert result["activity"]["wallet_count"] == 2
            assert result["boards"]["read_ts"] == 800
            assert result["boards"]["moves_24h"] == 0
            assert result["market"]["state"] == "stale"
            assert result["market"]["price_usd"] == 2000
            assert result["market"]["read_ts"] == 300
        m._failed_groups.add("channel")
        result = m._project_hub()["surf_news_hero"]
        assert result["announcement"]["state"] == result["reply"]["state"] == "stale"
        assert result["announcement"]["read_ts"] == 980
        assert result["boards"]["state"] == "ok"
        clock.now = 1250
        assert m._project_hub()["surf_news_hero"]["boards"]["state"] == "stale"
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_news_hero_failed_and_truncated_reads_retain_last_good(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_CHANNEL, SLOT_ACTIVITY, SLOT_NFT
    m, _ = manager
    m.cache.store_last_good(SLOT_CHANNEL, dict(items=[]), ts=999)
    m.cache.store_last_good(SLOT_ACTIVITY, dict(rows=[]), ts=999)
    m.cache.store_last_good(SLOT_NFT, dict(nft_holders=0, nft_written=0, nft_transfers_24h=0), ts=999)
    m.client.channel_truncated = m.client.activity_truncated = True
    try:
        result = m._project_hub()["surf_news_hero"]
        assert result["announcement"]["state"] == result["reply"]["state"] == "stale"
        assert result["activity"]["state"] == "stale"
        assert result["boards"]["state"] == "ok"
        assert result["boards"]["holders"] == 0
        assert result["market"]["state"] == "unavailable"
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
    assert 'launchpad' not in cards and cards['oracles']['status']=='unavailable'
    assert cards['pool4']['status']=='stale'
    assert 'pool4 · read '+__import__('maxpane_dashboard.data.surfboard',fromlist=['hhmm']).hhmm(910) in cards['pool4']['detail']
    assert 'stale' not in cards['pool4']['detail']
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


async def test_pool4_card_compares_confirmed_reads_and_ignores_repaints(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_MARKET, TIER_POOL4
    from maxpane_dashboard.data.surf_manager import SOURCE_MARKET
    m, clock = manager
    pool = dict(network='MAINNET', current_tick=0, hook_addr='0x' + '1' * 40)
    m.cache.store_last_good(SLOT_POOL4, pool, ts=990)
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=8, imd_change_24h_pct=-90), ts=990)

    def card():
        return next(row for row in m._project_hub()['surfboard_cards'] if row['key'] == 'pool4')

    assert (card()['primary'], card()['status']) == ('8.00', 'idle')
    for price, state in ((9, 'active'), (7, 'falling'), (7, 'idle'), (8, 'active')):
        clock.now += 10
        m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=price), ts=clock.now)
        assert card()['status'] == state
        assert card()['status'] == state  # Same source version is not a new price read.

    # A confirmed equal pool read changes no value but clears the old upward color.
    clock.now += 10
    m.cache.mark_fetched(TIER_POOL4, clock.now)
    assert card()['status'] == 'idle'
    clock.now += 10
    m.cache.store_last_good(SLOT_POOL4, dict(pool, current_tick=100), ts=clock.now)
    assert card()['status'] == 'falling'
    m.cache.mark_failed(TIER_POOL4, clock.now + 1)
    assert card()['status'] == 'stale'
    clock.now += 10
    m.cache.mark_fetched(TIER_POOL4, clock.now)
    assert card()['status'] == 'idle'

    # A retained/failed source and an invalid quote cannot replace the last good price.
    m._failed_groups.add(SOURCE_MARKET)
    clock.now += 10
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=4), ts=clock.now)
    assert card()['status'] == 'stale'
    m._failed_groups.clear()
    clock.now += 10
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=None), ts=clock.now)
    assert card()['status'] == 'unavailable'
    clock.now += 10
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=6), ts=clock.now)
    assert card()['status'] == 'falling'  # Compare with 8, not the failed 4.
    clock.now += 91
    assert card()['status'] == 'stale'
    await m.close()


@pytest.mark.parametrize('identity', [dict(network='SEPOLIA'), dict(hook_addr='0x' + '2' * 40)])
async def test_pool4_card_does_not_compare_different_pool_identities(manager, identity):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_MARKET
    m, clock = manager
    pool = dict(network='MAINNET', current_tick=0, hook_addr='0x' + '1' * 40)
    m.cache.store_last_good(SLOT_POOL4, pool, ts=990)
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=8), ts=990)
    m._project_hub()
    clock.now += 10
    m.cache.store_last_good(SLOT_POOL4, dict(pool, **identity), ts=clock.now)
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=9), ts=clock.now)
    row = next(row for row in m._project_hub()['surfboard_cards'] if row['key'] == 'pool4')
    assert row['status'] == 'idle'
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


async def test_tokens_card_shares_retained_catalogue_and_counts_24h_without_full_read(manager):
    m, clock = manager
    m._last_full_payload = dict(as_of=1000, swarm_launch_fired=[dict(ts=1000., number=1210)])
    m._offer_full = lambda now: None
    for raw in m.swarm_tokens_manager().client.data:
        raw['createdAt'] = '1970-01-01T00:15:00Z'
    try:
        first = await m.fetch_hub_snapshot()
        assert next(c for c in first['surfboard_cards'] if c['key']=='swarm-tokens')['primary'] == 'unavailable'
        adapter = m.swarm_tokens_manager()
        await adapter.wait_pending()
        from maxpane_dashboard.data.surf_swarm import launch_rows
        from tests.data.test_swarm_tokens_live import rows
        cached = launch_rows(adapter.client.data)
        cached[0].update(ticker='SFPT', token_address=next(
            a['address'] for a in cached[0]['artifacts'] if a['role'] == 'token'),
            liquidity=dict(state='info', read_ts=1000, token_amount=100, paired_amount=1, paired_symbol='ETH'))
        m._swarm_launch_keys = lambda: dict(swarm_launch_rows=cached)
        second = await m.fetch_hub_snapshot()
        card = next(c for c in second['surfboard_cards'] if c['key']=='swarm-tokens')
        assert (card['primary'], card['secondary'], card['status']) == ('3', '3 new', 'active')
        assert adapter is m.swarm_tokens_manager()
        assert set(adapter._tasks) == {'catalogue', 'markets'}
        await adapter.wait_pending()
        assert next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key']=='swarm-tokens')['status'] == 'active'
        for i, token in enumerate(adapter._tokens(m.swarm_tokens_source(), clock.now, include_inactive=True)):
            adapter._market[token['id']] = (dict(state='ok', market_pool='pool',
                _expected_pool=token['launch_pool'], volume_24h=1000-i*10, price_usd=1), clock.now)
            adapter._failed['markets'].discard(token['id'])
        card = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert card['title'] == 'TOKENS'
        assert len(card['token_ranking']['rows']) == 3
        assert card['token_ranking']['rows'][0]['symbol'] == 'SFPT'
        assert card['token_ranking']['rows'][0]['volume_usd'] == 1000
        assert card['token_ranking']['newest']['age_s'] == 100
        assert card['points'] is None
        clock.now = 4600
        card = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert (card['primary'], card['secondary'], card['status']) == ('3', '3 new', 'active')
        assert 'catalogue read' in card['detail'] and 'stale' not in card['detail']
        assert card['token_ranking']['state'] == 'stale'
        assert all(row['price_direction'] is None for row in card['token_ranking']['rows'])
        clock.now = 900 + 86400
        expired = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert expired['secondary'] == '0 new' and expired['status'] == 'idle'
    finally:
        await m.close()
    assert adapter._closed


@pytest.mark.parametrize('empty', [False, True])
async def test_hub_background_reads_preserve_loaded_cards_and_terminal(manager, empty):
    from copy import deepcopy
    from tests.surfboard_fixtures import hub_payload

    m, _ = manager
    data = hub_payload()
    data.update(pool4_total_burned=0 if empty else 33000)
    if empty:
        data['surfboard_overview'] = dict(agents_online=0, working_now=0)
        data['surfboard_events'] = []
        data['surfboard_footer'].update(market_value_usd=0, inference_tokens=0)
        for card in data['surfboard_cards']:
            key = card['key']
            if key == 'announce':
                card.update(primary='—', secondary='0 new replies')
            elif key == 'swarm':
                card.update(primary='0 online', secondary='0 working', points=[0]*8)
            elif key == 'board':
                card.update(primary='unavailable', fleet_summary=dict(online=0, runtime_known=0, state='ok', read_ts=1000))
            elif key == 'pool4':
                card.update(primary='0.00', share_price=0)
            elif key == 'oracles':
                card.update(primary='0', numerator=0, denominator=0)
            elif key == 'work':
                card.update(primary='0', secondary='0 workflows',
                            work_summary=dict.fromkeys(card['work_summary'], 0))
            elif key == 'swarm-tokens':
                card.update(primary='0', secondary='0 new', token_ranking=dict(rows=[], total=0))
    baseline = deepcopy(data)
    release = asyncio.Event()
    task = asyncio.create_task(release.wait())
    m._full_task = m._pool4_task = m._swarm_board_task = task
    m._work_reader.task = m._oracles_reader.task = task
    m._hub_source_tasks = dict.fromkeys(('overview', 'hourly', 'records', 'supply'), task)
    m._swarm_tokens_manager._tasks = dict.fromkeys(('catalogue', 'markets', 'volume'), task)
    try:
        m._hub_loading_state(data)
        assert data == baseline
        release.set()
        await task
        m._hub_loading_state(data)
        assert data == baseline
    finally:
        await m.close()


async def test_worker_reads_observe_activity_even_unchanged_or_failed(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_SURFBOARD_ACTIVITY, SLOT_SWARM_WORKERS, TIER_SWARM_BOARD
    from tests.surf_swarm_fixtures import swarm_capture_v3
    m, clock = manager
    raw = swarm_capture_v3('workers')
    raw['workers'] = raw['workers'][:1]
    raw['workers'][0]['seat']['tokenId'] = '420'
    raw['workers'][0]['working'] = 1
    raw['count'] = 1
    m.swarm_client.fetch_contributors = AsyncMock(return_value=None)
    m.swarm_client.fetch_workers = AsyncMock(return_value=raw)
    try:
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        assert m._project_hub()['surfboard_cards'][2]['meter_state'] == 'busy'
        clock.now += 120
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        assert m.cache.get_last_good(SLOT_SURFBOARD_ACTIVITY).payload['read_ts'] == clock.now
        assert m.cache.get_last_good(SLOT_SWARM_WORKERS).ts == 1000
        raw['workers'][0]['working'] = 0
        clock.now += 120
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        stopped = clock.now
        clock.now += 43200
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        row = m._project_hub()['surfboard_cards'][2]
        assert row['meter_state'] == 'idle' and row['numerator'] == 43200
        assert m.cache.get_last_good(SLOT_SURFBOARD_ACTIVITY).payload['seats']['420']['stopped_ts'] == stopped
        m.swarm_client.fetch_workers.return_value = None
        clock.now += 120
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        row = m._project_hub()['surfboard_cards'][2]
        assert row['meter_state'] == 'stale' and row['numerator'] is None
    finally:
        await m.close()


async def test_worker_read_recovers_each_seats_cached_work_after_restart(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT, SLOT_SURFBOARD_ACTIVITY, TIER_SWARM_BOARD
    from tests.data.test_surfboard_activity import NOW, seat_records
    from tests.surf_swarm_fixtures import swarm_capture_v3
    m, clock = manager
    clock.now = NOW
    m.set_hub_seats((3, 7, 420, 650))
    raw = swarm_capture_v3('workers')
    source = raw['workers'][0]
    raw['workers'] = [dict(source, seat=dict(source['seat'], tokenId=str(token)), working=0)
                      for token in (3, 7, 420, 650)]
    raw['count'] = 4
    records = {'seats': {}}
    for token, hours in ((3, 2), (7, 25), (420, 4), (650, 48)):
        records['seats'].update(seat_records(token=token, worked=NOW-hours*3600)['seats'])
    m.cache.store_last_good(SLOT_SWARM_SEAT, records, ts=NOW)
    m.swarm_client.fetch_contributors = AsyncMock(return_value=None)
    m.swarm_client.fetch_workers = AsyncMock(return_value=raw)
    try:
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        cards = {c['key']: c for c in m._project_hub()['surfboard_cards']}
        for key, remaining, kind in (('agent', 22*3600, 'activity'),
            ('agent-2', 47*3600, 'activity-cooldown'), ('agent-3', 20*3600, 'activity'),
            ('agent-4', 24*3600, 'activity-cooldown')):
            row = cards[key]
            assert (row['meter_state'], row['numerator'], row['meter_kind']) == ('idle', remaining, kind)
        assert m.cache.get_last_good(SLOT_SURFBOARD_ACTIVITY).payload['seats']['420']['stopped_ts'] == NOW-14400
    finally:
        await m.close()


async def test_hub_ranking_projection_preserves_reader_pool_identity(manager):
    from tests.data.test_swarm_tokens_live import rows
    from maxpane_dashboard.data.surf_swarm import launch_rows
    m, clock = manager
    clock.now = launch_rows(rows())[0]['created_ts'] + 1
    adapter = m.swarm_tokens_manager()
    adapter._catalogue = rows()
    adapter._complete, adapter._cat_as_of = True, clock.now
    launch = launch_rows(rows())[0]
    launch['token_address'] = next(a['address'] for a in launch['artifacts'] if a['role']=='token')
    pool = '0x'+'a'*64
    m._swarm_launch_keys = lambda: dict(swarm_launch_rows=[launch])
    facts = {'launches':{launch['launch_id']:dict(pool_initialize={'pool_id':pool},
        detail_version=[launch['status'], rows()[0].get('updatedAt')], row=rows()[0])}}
    original_slot = m._launch_slot
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS
    m._launch_slot = lambda slot, fallback: facts if slot==SLOT_SWARM_LAUNCH_FACTS else original_slot(slot,fallback)
    source = m.swarm_tokens_source()
    token = next(t for t in adapter._tokens(source, clock.now) if t['launch_uuid']==launch['launch_id'])
    adapter._market[token['id']] = (dict(state='ok', market_pool=pool, _expected_pool=pool, volume_24h=12500, price_usd=2), clock.now)
    try:
        expected = adapter.catalogue_summary(source)['ranking']
        assert expected['rows'][0]['volume_usd'] == 12500
        row = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert row['token_ranking'] == expected
        assert row['points'] is None and row['meter_kind'] == 'sparkline'
        facts['launches'][launch['launch_id']]['pool_initialize']['pool_id'] = '0x'+'b'*64
        changed = next(c for c in m._project_hub()['surfboard_cards'] if c['key']=='swarm-tokens')
        assert not changed['token_ranking']['rows']
        assert changed['token_ranking']['state'] == 'unavailable'
    finally:
        await m.close()


async def test_terminal_commands_keep_read_times_but_omit_stale_labels(manager):
    m, clock = manager
    await ready(m)
    clock.now += 1000
    try:
        assert m._hub_sources()['records']['state'] == 'stale'
        for command in ('status', 'seat #420'):
            lines = '\n'.join((await m.execute_hub_command(command))['lines'])
            assert 'stale' not in lines
            assert 'read ' in lines
        assert m._hub_sources()['records']['state'] == 'stale'
    finally:
        await m.close()


async def test_hub_snapshot_offers_bounded_volume_reads_without_awaiting_them(manager):
    from unittest.mock import Mock
    m, _ = manager
    adapter = m.swarm_tokens_manager()
    adapter.offer_hub_volume = Mock()
    adapter.offer_hub_markets = Mock()
    try:
        await m.fetch_hub_snapshot()
        adapter.offer_hub_volume.assert_called_once_with()
        adapter.offer_hub_markets.assert_not_called()
        m._closing = True
        await m.fetch_hub_snapshot()
        adapter.offer_hub_volume.assert_called_once_with()
    finally:
        m._closing = False
        await m.close()


@pytest.mark.parametrize('source,expected', [
    ('overview', {'swarm'}), ('hourly', {'swarm'}),
    ('records', {'agent'}), ('supply', {'protocol'}),
    ('work', {'work'}), ('oracles', {'oracles'}),
    ('workers', {'board', 'agent'}), ('pool4', {'pool4', 'protocol'}),
    ('catalogue', {'swarm-tokens'}), ('markets', {'swarm-tokens'}),
    ('volume', {'swarm-tokens'}), ('history', set()),
    ('full', {'announce', 'pool4', 'protocol'}),
])
@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancel'])
async def test_hub_loading_tracks_only_relevant_unfinished_reads(manager, source, expected, outcome):
    m, _ = manager
    m.set_hub_seats([420, None, None, None])
    baseline = m._project_hub()
    release = asyncio.Event()
    async def read():
        await release.wait()
        if outcome == 'failure':
            raise ValueError('read failed')
    task = asyncio.create_task(read())
    if source in ('overview', 'hourly', 'records', 'supply'):
        m._hub_source_tasks[source] = task
    elif source in ('work', 'oracles'):
        getattr(m, f'_{source}_reader').task = task
    elif source in ('catalogue', 'markets', 'volume', 'history'):
        m._swarm_tokens_manager._tasks[source] = task
    else:
        setattr(m, {'workers': '_swarm_board_task', 'pool4': '_pool4_task', 'full': '_full_task'}[source], task)
    try:
        loading = m.get_hub_snapshot()
        assert {c['key'] for c in loading['surfboard_cards'] if c['status'] == 'loading'} == expected
        assert [c['primary'] for c in loading['surfboard_cards']] == [c['primary'] for c in baseline['surfboard_cards']]
        assert (loading['surfboard_sources']['overview']['state'] == 'loading') == (source == 'overview')
        assert (loading['surfboard_footer']['market_state'] == 'loading') == (source == 'full')
        assert m._hub_sources() == baseline['surfboard_sources']  # transient display only
        if outcome == 'cancel':
            task.cancel()
        else:
            release.set()
        await asyncio.gather(task, return_exceptions=True)
        finished = m.get_hub_snapshot()
        assert finished['surfboard_cards'] == baseline['surfboard_cards']
        assert finished['surfboard_sources'] == baseline['surfboard_sources']
        assert finished['surfboard_footer'] == baseline['surfboard_footer']
    finally:
        await m.close()


async def test_fleet_card_uses_captured_workers_and_independent_contributor_clock(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_WORKERS, SLOT_SWARM_CONTRIBUTORS
    from maxpane_dashboard.data.surf_swarm import normalize_contributors
    from tests.surf_swarm_fixtures import swarm_capture_v3
    from tests.data.test_surfboard import fleet_workers
    m, clock = manager
    workers = fleet_workers()
    m.cache.store_last_good(SLOT_SWARM_WORKERS, workers, ts=900)
    worker_entry = m.cache.get_last_good(SLOT_SWARM_WORKERS)
    m._swarm_board_observations[SLOT_SWARM_WORKERS] = dict(entry=worker_entry, read_ts=990, failed=False)
    m.cache.store_last_good(SLOT_SWARM_CONTRIBUTORS,
                           normalize_contributors(swarm_capture_v3('contributors')), ts=800)
    original = m._swarm_board_keys
    def replace_cache_after_capture(*args, **kwargs):
        data = original(*args, **kwargs)
        m.cache.store_last_good(SLOT_SWARM_WORKERS, dict(workers=[], count=0, malformed_tokens=[]), ts=1000)
        return data
    m._swarm_board_keys = replace_cache_after_capture
    try:
        data = m.get_hub_snapshot()
        card = next(card for card in data['surfboard_cards'] if card['key'] == 'board')
        assert card['fleet_summary']['codex_percent'] == pytest.approx(100/3)
        assert card['fleet_summary']['online'] == 3
        assert card['fleet_summary']['state'] == 'ok'
        assert card['fleet_summary']['read_ts'] == 990
        assert data['surf_leaderboard_hero']['workers']['read_ts'] == 990
        assert card['numerator'] == data['swarm_board_summary']['wall_clock_ms']
        assert card['numerator'] > 0
        assert f'contributors read {m.cache.get_last_good(SLOT_SWARM_CONTRIBUTORS).as_of_hhmm()}' in card['detail']
        m._swarm_board_keys = original
        card = next(card for card in m.get_hub_snapshot()['surfboard_cards'] if card['key'] == 'board')
        assert card['fleet_summary']['online'] == 0
    finally:
        await m.close()
