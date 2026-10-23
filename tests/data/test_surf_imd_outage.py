"""Outage boundaries: independent chain labels and existing host-pool reads."""
import json
import socket
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.surf_nft_client import Budget, SurfNftClient
from maxpane_dashboard.data.surf_swarm_client import SWARM_API_HOSTS, SwarmClient
from tests.data.test_surf_manager_pool4_market import _market_manager

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf'


@pytest.mark.parametrize('network', ['MAINNET', 'SEPOLIA', None, 'BASE'])
def test_staker_network_is_projected_from_its_own_slot(tmp_path, network):
    manager = _market_manager(tmp_path)
    slot = dict(network=network, stakers=[{'address': '0x' + 'a' * 40}], staker_count=1)
    result = manager._pool4_stakers_keys(slot, None)
    assert result['pool4_stakers_network'] == (network if network in ('MAINNET', 'SEPOLIA') else None)


class ImdDNSOutage:
    """All custom-domain names fail; only recorded Railway responses exist."""
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        assert request.method == 'GET'
        assert not {'authorization', 'x-api-key', 'cookie'} & set(request.headers)
        if request.url.host == 'imd.fun' or request.url.host.endswith('.imd.fun'):
            raise httpx.ConnectError('Name or service not known', request=request) from socket.gaierror(socket.EAI_NONAME, 'NXDOMAIN')
        assert str(request.url).startswith(SWARM_API_HOSTS[1] + '/')
        return httpx.Response(200, json=self.routes[request.url.path])


async def test_nft_plane_reads_rotate_on_dns_failure():
    public = json.loads((FIXTURES / 'nft/discovery/public.json').read_text())
    transport = ImdDNSOutage({'/jobs': public['jobs']})
    async with SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                             inter_call_delay=0, clock=lambda: 100., monotonic=lambda: 1.) as client:
        page = await client.page('jobs', budget=Budget(monotonic=lambda: 1.))
    assert page.rows == public['jobs']['jobs']
    assert [r.url.host for r in transport.requests] == [httpx.URL(h).host for h in SWARM_API_HOSTS]


async def test_swarm_plane_reads_rotate_on_dns_failure():
    from tests.surf_swarm_fixtures import swarm_capture_v2
    capture = swarm_capture_v2('health')
    transport = ImdDNSOutage({'/health': capture})
    async with SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                           inter_call_delay=0) as client:
        result = await client.fetch_health()
    assert result == capture
    assert [r.url.host for r in transport.requests] == [httpx.URL(h).host for h in SWARM_API_HOSTS]


async def test_docs_dns_failure_cannot_adopt_a_cached_docs_hook(tmp_path):
    from maxpane_dashboard.data.surf_pool4_client import Pool4Client, DOCS_URL
    from tests.data.test_surf_manager_pool4 import (
        FakePool4Client, MAINNET_HOOK, _manager,
    )

    transport = ImdDNSOutage({})
    async with Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                           inter_call_delay=0) as reader:
        client = FakePool4Client()
        client.fetch_docs_page = reader.fetch_docs_page
        manager = _manager(tmp_path, pool4_client=client)
        verdict, source = await manager._pool4_discovery([], {
            'network': 'MAINNET', 'hook_addr': MAINNET_HOOK,
            'discovery_state': 'adopted', 'discovery_source': 'docs',
        })
    assert source is None
    assert verdict.state != 'adopted'
    assert verdict.detail.startswith('docs unreachable — ')
    assert client.verified == []
    assert transport.requests
    assert {str(r.url) for r in transport.requests} == {DOCS_URL}


async def test_discovery_gets_full_history_not_the_display_window(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, _self_post, MAINNET_HOOK, POOL4_NOW
    manager = _manager(tmp_path)
    manager.client._returns['fetch_channel_txs'] = None
    rows = [_self_post('gm') for _ in range(30)]
    rows.append(_self_post('pool4: ' + MAINNET_HOOK))
    manager.cache.store_last_good('channel', {'items': rows}, ts=POOL4_NOW - 10)
    seen = []
    monkeypatch.setattr(manager, '_spawn_pool4', lambda tiers, now, items: seen.append(items))
    await manager.fetch_and_compute()
    assert seen == [rows]
    await manager.close()


@pytest.mark.parametrize('transaction', [None, 'different announcement'])
async def test_cached_channel_cannot_supply_current_provenance(tmp_path, transaction):
    from tests.data.test_surf_manager_pool4 import (
        FakePool4Client, MAINNET_HOOK, REAL_TX, _manager, _adopts,
        _self_post, _self_post_tx,
    )
    tx = _self_post_tx(REAL_TX, transaction) if transaction else None
    client = FakePool4Client(fetch_transaction=tx, fetch_candidate_answers=_adopts)
    manager = _manager(tmp_path, pool4_client=client)
    verdict, source = await manager._pool4_discovery(
        [_self_post('pool4: ' + MAINNET_HOOK, tx_hash=REAL_TX)], {},
    )
    assert source is None
    assert verdict.state != 'adopted'
    assert client.verified == []
