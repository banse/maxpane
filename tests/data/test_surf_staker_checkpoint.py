"""Lifetime staker coverage, persisted cursor and replay-tail regressions."""
from copy import deepcopy
from unittest.mock import AsyncMock

from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_POOL4_STAKERS, TIER_POOL4_STAKERS
from tests.data.test_surf_manager_pool4_market import (
    _market_manager, MarketPool4Client, TRANSFER_LOGS, TRANSFERS_FULL,
    VAULT_ADDR, VAULT_STATE, SHARE_SUPPLY_UNITS,
)


def setup(tmp_path):
    client = MarketPool4Client()
    head = [TRANSFERS_FULL['head_block']]
    logs = deepcopy(TRANSFER_LOGS)
    reads, anchors = [], []
    async def block(**kwargs):
        return head[0]
    async def zero(addr, before, **kwargs):
        anchors.append(before)
        return before < TRANSFERS_FULL['first_log_block']
    async def flow(addr, start, end, **kwargs):
        reads.append((start, end))
        return [row for row in logs if start <= int(row['blockNumber'], 16) <= end]
    client.fetch_block_number = block
    client.fetch_zero_supply = zero
    client.fetch_flow_logs = flow
    manager = _market_manager(tmp_path, pool4_client=client)
    manager.cache.store_last_good(SLOT_POOL4, dict(
        network='MAINNET', vault_addr=VAULT_ADDR, share_price_wei=VAULT_STATE.share_price_wei,
        vault_decimals=VAULT_STATE.decimals), ts=manager._clock())
    return manager, client, head, logs, reads, anchors


async def sweep(manager):
    return await manager._pool_pool4_stakers({TIER_POOL4_STAKERS}, manager._clock())


async def test_old_unmoved_mints_survive_window_age_and_incremental_resume(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    head[0] += 403_200  # old heuristic would silently age out the entire mint history
    first = await sweep(manager)
    assert first['complete'] is True
    assert first['staker_count'] > 20
    assert anchors and reads[0][0] < TRANSFERS_FULL['first_log_block']
    checkpoint = manager.cache.get_last_good(SLOT_POOL4_STAKERS).payload['_history']
    assert sum(checkpoint['balances'].values()) == SHARE_SUPPLY_UNITS
    head[0] += 150
    second = await sweep(manager)
    assert second['stakers'] == first['stakers']
    assert reads[-1] == (checkpoint['block'] + 1, head[0])
    assert len(reads) == 2


async def test_failed_resume_retains_checkpoint_and_last_good_timestamp(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    await sweep(manager)
    old = deepcopy(manager.cache.get_last_good(SLOT_POOL4_STAKERS))
    head[0] += 150
    client.fetch_flow_logs = AsyncMock(return_value=None)
    assert await sweep(manager) is None
    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS) == old


async def test_recent_reorg_replays_from_checkpoint_without_double_applying(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    first = await sweep(manager)
    row = deepcopy(logs[0])
    row.update(blockNumber=hex(head[0] - 1), logIndex='0xff', transactionHash='0x'+'ab'*32,
               data='0x'+hex(10**24)[2:].zfill(64))
    logs.append(row)
    changed = await sweep(manager)
    assert changed['stakers'] != first['stakers']
    logs.pop()  # replacement chain omits that mint in the replay horizon
    reverted = await sweep(manager)
    assert reverted['stakers'] == first['stakers']


async def test_corrupt_or_old_checkpoint_rebuilds_instead_of_trusting_balances(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    first = await sweep(manager)
    for bad in (None, {'block': True}, dict(first['_history'], vault='0x'+'12'*20),
                dict(first['_history'], balances={'bad': 7})):
        manager.cache.store_last_good(SLOT_POOL4_STAKERS, dict(first, _history=bad), ts=1)
        manager._staker_anchor = None  # a fresh process has no in-memory anchor
        before = len(anchors)
        result = await sweep(manager)
        assert len(anchors) > before
        assert result['stakers'] == first['stakers']


async def test_malformed_transfer_cannot_advance_checkpoint(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    logs[0]['data'] = '0xnot-a-word'
    assert await sweep(manager) is None
    assert manager.cache.get_last_good(SLOT_POOL4_STAKERS) is None


async def test_saved_checkpoint_resumes_after_cache_reload(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    first = await sweep(manager)
    manager.cache.save()
    restored = SurfCache(path=manager.cache.path)
    restored.load(now=manager._clock())
    manager.cache = restored
    manager._staker_anchor = None
    head[0] += 150
    second = await sweep(manager)
    assert second['stakers'] == first['stakers']
    assert len(anchors) == 1
    assert reads[-1][0] == first['_history']['block'] + 1


async def test_small_head_rollback_never_retreats_checkpoint(tmp_path):
    manager, client, head, logs, reads, anchors = setup(tmp_path)
    first = await sweep(manager)
    head[0] -= 5
    second = await sweep(manager)
    assert second['_history']['block'] == first['_history']['block']
    third = await sweep(manager)
    assert third['stakers'] == second['stakers']
