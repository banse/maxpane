"""Portfolio's preview is deterministic, synthetic and wallet scoped."""

import json

import pytest

from maxpane_dashboard.data import portfolio_models as models
from maxpane_dashboard.data.portfolio_demo import (
    MOCK_NOW, SAMPLE_WALLET, DemoPortfolioManager, demo_snapshot,
)


def test_sample_contract_and_unconfigured_wallet():
    sample = demo_snapshot(SAMPLE_WALLET)
    assert tuple(sample) == models.SNAPSHOT_KEYS
    assert sample['wallet'] == 'sample'
    assert sample['is_mock'] is True and sample['as_of'] == MOCK_NOW
    assert [row['symbol'] for row in sample['tokens']] == ['TIDE', 'KITE', 'FOAM', 'MESH']
    assert all(tuple(row) == models.TOKEN_KEYS for row in sample['tokens'])
    assert all(row['id'] == f"{row['chain']}:{row['launch_id']}" for row in sample['tokens'])
    assert all(tuple(row) == models.ACTIVITY_KEYS for row in sample['activity'])
    assert '0x' not in json.dumps(sample)
    assert sample['agents'] == [
        {'id': '420', 'online': True}, {'id': '77', 'online': True},
        {'id': '1548', 'online': False},
    ]
    empty = demo_snapshot()
    assert empty['wallet'] is None
    assert empty['tokens'] == empty['activity'] == empty['agents'] == []


@pytest.mark.asyncio
async def test_managers_are_detached_offline_and_wallet_changes_do_not_persist(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError('Portfolio demo attempted network access')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setenv('HOME', str(tmp_path))
    empty, sample = DemoPortfolioManager(), DemoPortfolioManager(SAMPLE_WALLET)
    assert empty.is_mock is sample.is_mock is True
    assert empty.wallet is None and sample.wallet == SAMPLE_WALLET
    assert (await empty.fetch_and_compute())['tokens'] == []
    snapshot = await sample.fetch_and_compute()
    snapshot['tokens'][0]['sparkline'][0] = -99
    snapshot['activity'].clear()
    snapshot['agents'][0]['online'] = False
    assert await sample.fetch_and_compute() == demo_snapshot(SAMPLE_WALLET)
    assert empty.set_wallet('  another-wallet  ') is True
    assert empty.wallet == 'another-wallet'
    assert empty.set_wallet('another-wallet') is False
    assert (await empty.fetch_and_compute())['wallet'] == 'another-wallet'
    assert sample.wallet == SAMPLE_WALLET
    assert empty.set_wallet(None) is True
    assert (await empty.fetch_and_compute())['tokens'] == []
    assert await empty.close() is None
    assert await sample.close() is None
    assert list(tmp_path.iterdir()) == []
