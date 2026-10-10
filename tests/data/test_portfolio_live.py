"""Live wallet lifecycle, exercised only with synthetic injected sources."""
import asyncio
from copy import deepcopy

import httpx
import pytest

from maxpane_dashboard.data.portfolio_demo import demo_snapshot
from maxpane_dashboard.data.portfolio_manager import PortfolioManager

WALLET = '0x' + 'ab' * 20
OTHER = '0x' + 'cd' * 20


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('network used by portfolio test')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)


class Market:
    def __init__(self):
        self.calls, self.closed = [], False
        self.rows = demo_snapshot('sample')['tokens']
        for index, row in enumerate(self.rows):
            row.update(chain_id={'eth': 1, 'base': 8453, 'rh': 4663}[row['chain']],
                       token_address='0x' + f'{index + 1:040x}', launch_uuid=f'launch-{index}')
            row['id'] = f"{row['chain_id']}:{row['token_address']}"
        self.complete = True

    async def fetch_portfolio(self, priority_ids=()):
        self.calls.append(tuple(priority_ids))
        return dict(tokens=deepcopy(self.rows), activity=[], as_of=100,
                    is_mock=False, sources={'catalogue': dict(state='ok' if self.complete else 'partial',
                        as_of=100, complete=self.complete, coverage_complete=self.complete, loaded=4)})

    async def close(self):
        self.closed = True


class Balances:
    def __init__(self):
        self.calls, self.fail, self.closed = [], False, False

    async def read_balances(self, wallet, tokens):
        self.calls.append((wallet, [row['id'] for row in tokens]))
        if self.fail:
            raise RuntimeError('source down')
        return {row['id']: dict(balance_raw=(10 if wallet == WALLET else 20) * 10**6,
            decimals=6, held_quantity=10 if wallet == WALLET else 20,
            balance_state='ok', balance_read_at=100, balance_block=42) for row in tokens}

    async def close(self):
        self.closed = True


class Claims:
    def __init__(self, market):
        self.calls, self.closed = [], False
        self.payload = dict(allocations=[dict(allocation_id='round:wallet',
            chain_id=market.rows[0]['chain_id'], token_address=market.rows[0]['token_address'],
            launch_uuid='launch-0', claimable_quantity=2, claim_state='ready',
            claim_read_state='ok', claim_read_at=100, locked_quantity=0, claimed_quantity=0,
            unlock_at=99, claim_reason=None)], agents=[dict(id='1', online=True)],
            sources={name: dict(state='ok', complete=True, checked=1, total=1, as_of=100)
                     for name in ('claims', 'agents')})

    async def fetch_claims(self, wallet):
        self.calls.append(wallet)
        return deepcopy(self.payload)

    async def close(self):
        self.closed = True


def setup(wallet=WALLET):
    market, balances, clock = Market(), Balances(), [100]
    claims = Claims(market)
    manager = PortfolioManager(market, wallet, balances=balances, claims=claims, clock=lambda: clock[0])
    return manager, market, balances, claims, clock


async def test_first_paint_is_nonblocking_and_live_never_uses_mock_basis():
    manager, market, balances, claims, clock = setup()
    first = await manager.fetch_and_compute()
    assert first['is_mock'] is False and first['wallet'] == WALLET
    assert all(row['held_quantity'] is None for row in first['tokens'])
    assert first['sources']['balances']['complete'] is False
    await manager.wait_pending()
    current = await manager.fetch_and_compute()
    assert all(row['held_quantity'] == 10 for row in current['tokens'])
    assert all(row['held_cost_usd'] is None and row['basis_state'] == 'unavailable' for row in current['tokens'])
    assert current['tokens'][0]['claimable_quantity'] == 2
    assert current['tokens'][1]['claim_state'] == 'none'
    assert current['sources']['balances']['complete'] is True
    assert current['agents'] == [dict(id='1', online=True)]
    assert len(balances.calls) == len(claims.calls) == 1
    await manager.close()
    assert not market.closed and not balances.closed and not claims.closed


async def test_unset_wallet_does_not_start_wallet_or_market_reads():
    manager, market, balances, claims, _ = setup(None)
    snapshot = await manager.fetch_and_compute()
    await manager.wait_pending()
    assert snapshot['tokens'] == snapshot['agents'] == []
    assert not market.calls and not balances.calls and not claims.calls
    await manager.close()


async def test_ready_claim_only_tokens_receive_shared_market_priority():
    manager, market, balances, claims, _ = setup()
    original = balances.read_balances
    async def zeros(wallet, tokens):
        result = await original(wallet, tokens)
        for row in result.values():
            row.update(balance_raw=0, held_quantity=0)
        return result
    balances.read_balances = zeros
    await manager.fetch_and_compute()
    await manager.wait_pending()
    await manager.fetch_and_compute()
    assert market.calls[-1] == (market.rows[0]['id'],)
    await manager.close()


async def test_failed_refresh_retains_stale_quantity_with_original_source_time():
    manager, _, balances, claims, clock = setup()
    await manager.fetch_and_compute()
    await manager.wait_pending()
    balances.fail = True
    clock[0] = 300
    await manager.fetch_and_compute()
    await manager.wait_pending()
    snapshot = await manager.fetch_and_compute()
    assert snapshot['tokens'][0]['held_quantity'] == 10
    assert snapshot['tokens'][0]['balance_state'] == 'stale'
    assert snapshot['sources']['balances']['as_of'] == 100
    assert not snapshot['sources']['balances']['complete']
    await manager.close()


async def test_first_failed_read_is_unknown_and_incomplete_catalogue_never_completes_wallet():
    manager, market, balances, _, _ = setup()
    market.complete = False
    balances.fail = True
    await manager.fetch_and_compute()
    await manager.wait_pending()
    snapshot = await manager.fetch_and_compute()
    assert snapshot['tokens'][0]['held_quantity'] is None
    assert snapshot['tokens'][0]['balance_state'] == 'unavailable'
    assert not snapshot['sources']['balances']['complete']
    await manager.close()


async def test_distinct_claims_are_summed_once_and_locked_allocations_stay_in_detail():
    manager, _, _, claims, _ = setup()
    first = claims.payload['allocations'][0]
    claims.payload['allocations'] += [deepcopy(first), dict(first, allocation_id='round:2', claimable_quantity=3),
        dict(first, allocation_id='round:3', claimable_quantity=0, claim_state='locked', locked_quantity=4)]
    await manager.fetch_and_compute()
    await manager.wait_pending()
    snapshot = await manager.fetch_and_compute()
    row = snapshot['tokens'][0]
    assert row['claimable_quantity'] == 5 and row['locked_quantity'] == 4
    await manager.close()


async def test_balance_batches_make_progress_without_repeating_current_success():
    manager, _, balances, _, _ = setup()
    manager.BALANCE_BATCH = 2
    await manager.fetch_and_compute()
    await manager.wait_pending()
    partial = await manager.fetch_and_compute()
    assert partial['sources']['balances']['checked'] == 2
    assert partial['sources']['balances']['complete'] is False
    await manager.wait_pending()
    current = await manager.fetch_and_compute()
    assert current['sources']['balances']['checked'] == 4
    assert current['sources']['balances']['complete'] is True
    assert len({key for _, ids in balances.calls for key in ids}) == 4
    await manager.close()


async def test_wallet_aba_race_rejects_late_writes_even_when_client_ignores_cancellation():
    manager, _, balances, _, _ = setup()
    entered, release = asyncio.Event(), asyncio.Event()
    original = balances.read_balances
    calls = 0
    async def delayed(wallet, tokens):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            result = await original(wallet, tokens)
            for row in result.values():
                row['held_quantity'] = 999
            return result
        return await original(wallet, tokens)
    balances.read_balances = delayed
    await manager.fetch_and_compute()
    await asyncio.wait_for(entered.wait(), 2)
    manager.set_wallet(OTHER)
    middle = await manager.fetch_and_compute()
    assert all(row['held_quantity'] is None for row in middle['tokens'])
    manager.set_wallet(WALLET)
    await manager.fetch_and_compute()
    # Complete fresh A first, then let the cancelled old A attempt overwrite it.
    await asyncio.wait_for(asyncio.shield(manager._active['balances']), 2)
    release.set()
    await asyncio.wait_for(manager.wait_pending(), 2)
    final = await manager.fetch_and_compute()
    assert final['wallet_generation'] == 3
    assert all(row['held_quantity'] == 10 for row in final['tokens'])
    await manager.close()


async def test_mixed_age_claims_preserve_fresh_allocations_and_their_valuation():
    from maxpane_dashboard.analytics.portfolio import project_snapshot
    manager, market, _, claims, clock = setup()
    old = claims.payload['allocations'][0]
    claims.payload['allocations'].append(dict(old, allocation_id='round:fresh',
        chain_id=market.rows[1]['chain_id'], token_address=market.rows[1]['token_address'],
        launch_uuid='launch-1', claim_read_at=300, claimable_quantity=5))
    claims.payload['sources']['claims'].update(state='partial', complete=False)
    clock[0] = 300
    await manager.fetch_and_compute()
    await manager.wait_pending()
    raw = await manager.fetch_and_compute()
    assert raw['tokens'][0]['claim_read_state'] == 'stale'
    assert raw['tokens'][1]['claim_read_state'] == 'ok'
    projection = project_snapshot(raw)
    assert projection['metrics']['claimable_value'] == .1
    await manager.close()


async def test_verified_claim_only_membership_survives_unread_market_catalogue():
    manager, market, _, _, _ = setup()
    async def unread(priority_ids=()):
        return dict(tokens=None, activity=[], sources={'catalogue': dict(state='pending', complete=False)})
    market.fetch_portfolio = unread
    await manager.fetch_and_compute()
    await manager.wait_pending()
    snapshot = await manager.fetch_and_compute()
    assert snapshot['tokens'] is not None and len(snapshot['tokens']) == 1
    assert snapshot['tokens'][0]['claimable_quantity'] == 2
    assert snapshot['sources']['balances']['complete'] is False
    await manager.close()
