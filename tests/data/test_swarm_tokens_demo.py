"""The preview owns only deterministic, isolated mock data."""

import json

import pytest

from maxpane_dashboard.data.swarm_tokens_demo import (
    MOCK_NOW, DemoSwarmTokensManager, demo_snapshot,
)
from maxpane_dashboard.data import swarm_tokens_models as models


def test_demo_contract_has_realistic_missing_and_zero_states():
    snapshot = demo_snapshot()
    assert tuple(snapshot) == models.SNAPSHOT_KEYS
    assert snapshot['is_mock'] is True and snapshot['as_of'] == MOCK_NOW
    rows = snapshot['tokens']
    assert len(rows) == 24
    assert len({row['id'] for row in rows}) == len(rows)
    assert {row['chain'] for row in rows} == {'eth', 'base', 'rh'}
    assert {row['lp_state'] for row in rows} == {
        'two-sided', 'one-token', 'one-quote', 'withdrawn', 'unknown',
    }
    assert all(tuple(row) == models.TOKEN_KEYS for row in rows)
    assert all(row['id'] == f"{row['chain']}:{row['launch_id']}" for row in rows)
    assert all(row['status'] == 'live' for row in rows)
    assert sum(0 <= MOCK_NOW-row['launched_at'] < 86400 for row in rows) == 3
    by_symbol = {row['symbol']: row for row in rows}
    assert by_symbol['CLAUS']['volume_24h'] == 0
    assert by_symbol['ORB']['volume_24h'] is None
    assert by_symbol['CLAUS']['paired_amount'] == 0
    assert by_symbol['ORB']['paired_amount'] is None
    assert by_symbol['VOID']['lp_state'] == 'withdrawn'
    assert all(row['sparkline'] is None or len(row['sparkline']) == 24 for row in rows)
    assert by_symbol['CLAUS']['sparkline'] is None
    assert all(tuple(row) == models.ACTIVITY_KEYS for row in snapshot['activity'])
    assert all(row['token_id'] in {token['id'] for token in rows} for row in snapshot['activity'])
    assert all(row['ts'] <= MOCK_NOW for row in snapshot['activity'])
    assert {'BUY', 'SELL', 'LAUNCH', 'LP ADD', 'LP READ'} == {row['kind'] for row in snapshot['activity']}
    assert '0x' not in json.dumps(snapshot)


@pytest.mark.asyncio
async def test_manager_and_snapshot_return_independent_deterministic_data(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError('Demo manager attempted network access')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setenv('HOME', str(tmp_path))
    manager = DemoSwarmTokensManager()
    original = demo_snapshot()
    first = await manager.fetch_and_compute()
    assert first == original
    first['tokens'][0]['sparkline'][0] = -99
    first['activity'].clear()
    assert await manager.fetch_and_compute() == original
    assert demo_snapshot() == original
    assert manager._error_count == 0
    assert await manager.close() is None
    assert list(tmp_path.iterdir()) == []
