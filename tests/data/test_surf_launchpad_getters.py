"""Cheap entry refreshes reuse the exact launchpad getter batch, without history."""
import copy
import json

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.surf_client import MULTICALL3
from tests.data.test_surf_client import (
    RecordingTransport, _client_on, _launchpad_fixture_handler, _load_launchpad,
    _rpc_ok, _word, decode_aggregate3_calldata, encode_aggregate3_result,
)


GETTERS = (
    ('imd_to_burn_wei', A.LAUNCHPAD_HOOK, A.SEL_IMD_TO_BURN),
    ('total_real_imd_wei', A.LAUNCHPAD_HOOK, A.SEL_TOTAL_REAL_IMD),
    ('burn_fee_bps', A.LAUNCHPAD_HOOK, A.SEL_BURN_FEE_BPS),
    ('creator_fee_bps', A.LAUNCHPAD_HOOK, A.SEL_CREATOR_FEE_BPS),
    ('creator_eth_owed_wei', A.LAUNCHPAD_HOOK, A.SEL_TOTAL_CREATOR_ETH_OWED),
    ('coin_count', A.LAUNCHPAD_FACTORY, A.SEL_COIN_COUNT),
    ('executor_balance_wei', A.BURN_EXECUTOR_V2, A.SEL_TOKEN_BALANCE),
    ('min_bridge_wei', A.BURN_EXECUTOR_V2, A.SEL_MIN_BRIDGE_AMOUNT),
    ('bridge_amount_wei', A.BURN_EXECUTOR_V2, A.SEL_PREVIEW_BRIDGE),
)


def getter_transport(reads, *, block='latest'):
    def handler(request):
        payload = json.loads(request.content)
        assert payload['method'] == 'eth_call', 'getter-only refresh performed history I/O'
        assert payload['params'][1] == block
        assert payload['params'][0]['to'].lower() == MULTICALL3.lower()
        calls = decode_aggregate3_calldata(payload['params'][0]['data'])
        assert calls == [(address.lower(), True, selector.lower())
                         for _, address, selector in GETTERS]
        results = []
        for field, _, _ in GETTERS:
            value = reads.get(field)
            raw = _word(value) if value is not None else '0x'
            if field == 'bridge_amount_wei' and value is not None:
                # previewBridge returns three words; only amountToSend is the amount.
                raw += _word(456)[2:] + _word(789)[2:]
            results.append((value is not None, raw))
        return httpx.Response(200, json=_rpc_ok(payload, encode_aggregate3_result(results)))

    return RecordingTransport(handler)


@pytest.mark.parametrize('block', ['latest', '0x189fa7b'])
async def test_getters_read_one_batch_without_touching_history_or_pending_head(block):
    expected = dict(_load_launchpad('launchpad_reads.json'), bridge_amount_wei=123)
    transport = getter_transport(expected, block=block)
    async with _client_on(transport) as client:
        pending = (A.LAUNCHPAD_FIRST_BLOCK, 25_800_000)
        client._launchpad_pending = pending
        client._launchpad_finalized = {'last_block': 25_799_988}
        client._launchpad_candidate = {'last_block': 25_799_990}
        client._launchpad_published_head = 25_799_999
        client._launchpad_rebuild = True
        before = copy.deepcopy((client._launchpad_pending, client._launchpad_finalized,
                                client._launchpad_candidate, client._launchpad_published_head,
                                client._launchpad_rebuild))
        result = await client.fetch_launchpad_getters(**({} if block == 'latest' else {'block': block}))
        assert result == expected
        assert (client._launchpad_pending, client._launchpad_finalized,
                client._launchpad_candidate, client._launchpad_published_head,
                client._launchpad_rebuild) == before
    assert len(transport.requests) == 1


async def test_getter_failure_is_distinct_from_zero_and_does_not_discard_other_legs():
    expected = dict(_load_launchpad('launchpad_reads.json'), coin_count=None,
                    imd_to_burn_wei=0, bridge_amount_wei=0)
    transport = getter_transport(expected)
    async with _client_on(transport) as client:
        result = await client.fetch_launchpad_getters()
    assert result == expected
    assert result['coin_count'] is None
    assert result['min_bridge_wei'] == result['imd_to_burn_wei'] == result['bridge_amount_wei'] == 0
    assert len(transport.requests) == 1


async def test_getter_transport_outage_preserves_unknown_shape_without_history_reads():
    def offline(request):
        payload = json.loads(request.content)
        assert payload['method'] == 'eth_call'
        raise httpx.ConnectError('injected state outage', request=request)

    transport = RecordingTransport(offline)
    async with _client_on(transport) as client:
        result = await client.fetch_launchpad_getters()
    assert result is None
    assert transport.requests


async def test_full_launchpad_uses_same_getters_at_history_target_block():
    reads = _load_launchpad('launchpad_reads.json')
    logs = _load_launchpad('launchpad_logs.json')
    reads['coin_count'] = len(logs['launched'])
    transport = RecordingTransport(_launchpad_fixture_handler(reads, logs, {}))
    calls = []
    async with _client_on(transport, now_fn=lambda: 2_000_000_000.) as client:
        original = client.fetch_launchpad_getters

        async def observe(*, block='latest'):
            assert client._launchpad_pending is not None
            assert block == hex(client._launchpad_pending[1])
            calls.append(block)
            return await original(block=block)

        client.fetch_launchpad_getters = observe
        state = await client.fetch_launchpad()
    assert calls == [hex(logs['head_block'])]
    assert all(getattr(state, field) == value for field, value in reads.items())
    assert state.bridge_amount_wei is None  # absent in the historical capture
    assert state.launch_count == reads['coin_count']
    assert state.cursor['last_block'] == logs['head_block']
