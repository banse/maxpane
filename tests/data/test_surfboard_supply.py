"""Global supply uses the canonical Base token, never a bridged-chain sum."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surfboard as hub
from maxpane_dashboard.data.surf_launch_base_client import SwarmBaseClient
from tests.data.test_surf_manager_surfboard import manager


def capture():
    return json.loads(Path('tests/fixtures/surf/hub/base_supply.json').read_text())


@pytest.mark.parametrize('decimals,expected', [(18, 7095964.257748015), (6, 7095964257748015000.)])
async def test_supply_reads_canonical_token_and_live_decimals(decimals, expected):
    reply = capture()
    reply[1]['result'] = f'0x{decimals:064x}'
    def respond(request):
        batch = json.loads(request.content)
        assert request.url.host == 'base-rpc.publicnode.com'
        assert [call['params'] for call in batch] == [
            [{'to': '0xFF0C532FDB8Cd566Ae169C1CB157ff2Bdc83E105', 'data': selector}, 'latest']
            for selector in ('0x18160ddd', '0x313ce567')]
        assert all(call['method'] == 'eth_call' for call in batch)
        return httpx.Response(200, json=list(reversed(reply)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = SwarmBaseClient(http_client=http)
        assert await client.fetch_imd_global_supply() == {'total_supply': pytest.approx(expected)}


@pytest.mark.parametrize('index,value', [(0, None), (0, '0x'), (0, '0x12'),
    (0, '0x'+'z'*64), (0, '0x'+'0'*64), (1, None), (1, '0x'), (1, '0x'+f'{37:064x}')])
async def test_supply_invalid_getter_is_unknown(index, value):
    reply = capture(); reply[index]['result'] = value
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=reply))) as http:
        assert await SwarmBaseClient(http_client=http).fetch_imd_global_supply() is None


@pytest.mark.parametrize('value', [None, 0, -1, True, '1', float('inf')])
def test_supply_cache_rejects_invalid_denominator(value):
    envelope = hub.source_envelope({'total_supply': 1}, 1000)
    envelope['payload']['total_supply'] = value
    if value != float('inf'):
        envelope['version'] = hub.version(envelope['payload'])
    assert hub.coerce_source(envelope, 'supply', now=1001) is None


async def test_supply_visible_cadence_failure_clock_and_cache(manager):
    m, clock = manager
    reader = m._launch_rpc_clients[8453].fetch_imd_global_supply
    reader.return_value = {'total_supply': 7095964.257748015}
    try:
        await m.fetch_hub_snapshot()
        await asyncio.gather(*m._hub_source_tasks.values())
        reader.assert_not_awaited()
        m.set_hub_active(True)
        m._last_full_payload = dict(pool4_total_burned=33279.3, pool4_network='MAINNET')
        await m.fetch_hub_snapshot()
        await asyncio.gather(*m._hub_source_tasks.values())
        first = m._hub_sources()['supply']
        assert first['state']=='ok' and first['read_ts']==1000
        assert hub.coerce_source(first, 'supply', now=1001) == first
        snapshot = m._project_hub(refresh_legacy=False)
        assert snapshot['pool4_total_burned'] == 33279.3
        assert not any(c['key'] == 'protocol' for c in snapshot['surfboard_cards'])
        clock.now=1599
        await m.fetch_hub_snapshot(); await asyncio.gather(*m._hub_source_tasks.values())
        assert reader.await_count==1
        reader.return_value=None; clock.now=1600
        await m.fetch_hub_snapshot(); await asyncio.gather(*m._hub_source_tasks.values())
        source=m._hub_sources()['supply']
        assert source['state']=='stale' and source['read_ts']==1000 and source['attempt_ts']==1600
        assert source['payload']==first['payload'] and reader.await_count==2
        clock.now=1700
        await m.fetch_hub_snapshot(); await asyncio.gather(*m._hub_source_tasks.values())
        assert reader.await_count==2
        reader.return_value={'total_supply': 7000000}; clock.now=2200
        await m.fetch_hub_snapshot(); await asyncio.gather(*m._hub_source_tasks.values())
        assert m._hub_sources()['supply']['state']=='ok'
        assert m._hub_sources()['supply']['read_ts']==2200
    finally:
        await m.close()


def test_supply_disk_cache_preserves_success_clock_and_validates_payload(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    path = str(tmp_path/'supply.json')
    cache = SurfCache(clock=lambda: 1700)
    good = hub.source_envelope({'total_supply': 7095964.257748015}, 1000)
    stale = hub.source_envelope(None, 1600, prior=good)
    cache.store_last_good(hub.SOURCE_SLOTS['supply'], stale, ts=1600)
    assert cache.newest_as_of() == 1000
    cache.save(path)
    restored = SurfCache(clock=lambda: 1700)
    restored.load(path, slot_coercers={hub.SOURCE_SLOTS['supply']:
        lambda raw: hub.coerce_source(raw, 'supply', now=1700)})
    assert restored.get_last_good(hub.SOURCE_SLOTS['supply']).payload == stale
    # No validator: a persisted denominator must not bypass the source contract.
    unchecked = SurfCache(clock=lambda: 1700)
    unchecked.load(path)
    assert unchecked.get_last_good(hub.SOURCE_SLOTS['supply']) is None
