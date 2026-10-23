"""Selection, cache provenance and cancellation without network or graphics."""
import asyncio
import copy
import json

import pytest

from maxpane_dashboard.data.sworn_client import decode_metadata
from maxpane_dashboard.data.sworn_manager import SwornManager
from maxpane_dashboard.data.sworn_models import SWORN_KEYS
from maxpane_dashboard.data.evm_abi import decode_string
from tests.data.test_sworn_client import FIXTURE, CLAIMANT, HOLDER


class Client:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.entered = asyncio.Event()
        self.gate = None
    async def fetch(self, value):
        self.calls.append(value)
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError('offline')
        token_id = int(value) if value and not value.startswith('0x') else 10
        uri = decode_string(FIXTURE['calls']['tokenURI(uint256)']['result'], max_len=1_000_000)
        metadata, svg = decode_metadata(uri, CLAIMANT)
        return {'supply': 42, 'block': 123456, 'card': {'token_id': token_id, 'claimant': CLAIMANT, 'holder': HOLDER,
                'minted_at_block': 123, 'metadata': metadata, 'svg': svg}, 'error': None}
    async def close(self):
        pass


def make(tmp_path, *, client=None, now=None, prepare=None):
    manager = SwornManager(client=client or Client(), cache_path=tmp_path/'sworn.json',
        now=now or (lambda: 1000.0), prepare=prepare or (lambda svg: {'hash': 'test', 'png': '', 'pixels': []}))
    manager.set_active_view('SWORN')
    return manager


async def test_contract_selected_first_and_cached_switch(tmp_path):
    prepared = []
    manager = make(tmp_path, prepare=lambda svg: prepared.append(svg) or {'hash': 'test'})
    manager.select('1')
    first = await manager.fetch_and_compute()
    assert set(first) == set(SWORN_KEYS)
    assert first['sworn_selected']['token_id'] == 1
    assert [r['token_id'] for r in first['sworn_rows']] == [2, 1]
    assert first['sworn_rows'][0]['families'] is None
    assert first['sworn_rows'][1]['families'] == 0
    manager.select('2')
    assert manager.get_snapshot()['sworn_selected'] is None
    await manager.fetch_and_compute()
    manager.select('1')
    assert manager.get_snapshot()['sworn_selected']['token_id'] == 1
    assert manager.client.calls == ['1', '2']
    assert len(prepared) == 1


async def test_poll_updates_holder_but_same_art_rasterizes_once(tmp_path):
    prepared = []
    manager = make(tmp_path, prepare=lambda svg: prepared.append(svg) or {'hash': 'test'})
    manager.select('1')
    await manager.fetch_and_compute()
    await manager.fetch_and_compute()
    assert manager.client.calls == ['1', '1']
    assert len(prepared) == 1


async def test_failure_retains_original_timestamp_and_cold_failure_is_none(tmp_path):
    clock = [1000.0]
    manager = make(tmp_path, now=lambda: clock[0])
    manager.select('1')
    await manager.fetch_and_compute()
    clock[0] = 2000.0
    manager.client.fail = True
    result = await manager.fetch_and_compute()
    assert result['sworn_supply'] == 42
    assert result['sworn_observed_at'] == 1000.0
    assert result['sworn_selected']['observed_at'] == 1000.0
    assert result['sworn_error'] is None
    assert manager._error_count == 1
    manager.select('3')
    result = await manager.fetch_and_compute()
    assert result['sworn_selected'] is None


async def test_late_old_selection_and_cancel_do_not_publish(tmp_path):
    client = Client()
    client.gate = asyncio.Event()
    manager = make(tmp_path, client=client)
    manager.select('1')
    task = asyncio.create_task(manager.fetch_and_compute())
    await client.entered.wait()
    manager.select('2')
    client.gate.set()
    await task
    assert manager.get_snapshot()['sworn_selected'] is None
    assert manager.get_snapshot()['sworn_selection'] == '2'
    assert manager.get_snapshot()['sworn_supply'] is None
    assert manager.cache.cards == {}
    client.gate.clear()
    client.entered.clear()
    task = asyncio.create_task(manager.fetch_and_compute())
    await client.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert manager.get_snapshot()['sworn_selected'] is None


async def test_persisted_cache_restores_art_and_rejects_other_deployment(tmp_path):
    manager = make(tmp_path)
    manager.select('1')
    await manager.fetch_and_compute()
    await manager.close()
    restored = make(tmp_path)
    restored.select('1')
    assert restored.get_snapshot()['sworn_selected']['holder'] == HOLDER
    assert restored.get_snapshot()['sworn_selected']['observed_at'] == 1000.0
    raw = json.loads((tmp_path/'sworn.json').read_text())
    raw['binding']['registry'] = HOLDER
    (tmp_path/'sworn.json').write_text(json.dumps(raw))
    other = make(tmp_path)
    other.select('1')
    assert other.get_snapshot()['sworn_supply'] is None
    assert other.get_snapshot()['sworn_selected'] is None


async def test_hidden_view_and_invalid_lookup_start_no_reads(tmp_path):
    manager = make(tmp_path)
    manager.set_active_view(None)
    await manager.fetch_and_compute()
    assert not manager.client.calls
    manager.set_active_view('SWORN')
    manager.select('not a wallet')
    assert manager.get_snapshot()['sworn_error']
    await manager.fetch_and_compute()
    assert not manager.client.calls


async def test_overlapping_refreshes_never_queue_another_read(tmp_path):
    client = Client()
    client.gate = asyncio.Event()
    manager = make(tmp_path, client=client)
    first = asyncio.create_task(manager.fetch_and_compute())
    await client.entered.wait()
    await manager.fetch_and_compute()
    assert client.calls == [None]
    client.gate.set()
    await first


async def test_malformed_cache_and_huge_invalid_input_do_not_crash(tmp_path):
    (tmp_path/'sworn.json').write_text('{not json')
    manager = make(tmp_path)
    assert manager.get_snapshot()['sworn_supply'] is None
    manager.select('1')
    await manager.fetch_and_compute()
    manager.select('9'*5000)
    assert manager.get_snapshot()['sworn_selected'] is None
    assert manager.get_snapshot()['sworn_error']
    await manager.fetch_and_compute()
    assert manager.client.calls == ['1']


async def test_proven_missing_claimant_clears_prior_cached_card(tmp_path):
    manager = make(tmp_path)
    manager.select('1')
    await manager.fetch_and_compute()
    manager.select(CLAIMANT)
    assert manager.get_snapshot()['sworn_selected']
    async def now_absent(selection):
        return {'supply':42, 'block':123457, 'card':None, 'error':'No minted card for this claimant'}
    manager.client.fetch = now_absent
    result = await manager.fetch_and_compute()
    assert result['sworn_selected'] is None
    assert result['sworn_error'] == 'No minted card for this claimant'


@pytest.mark.parametrize('field,entry', [('attributes', None), ('oracle', None)])
async def test_corrupt_cached_metadata_member_is_skipped(tmp_path, field, entry):
    manager = make(tmp_path)
    manager.select('1')
    await manager.fetch_and_compute()
    raw = json.loads((tmp_path/'sworn.json').read_text())
    raw['cards'][0]['metadata'][field].append(entry)
    (tmp_path/'sworn.json').write_text(json.dumps(raw))
    restored = make(tmp_path)
    restored.select('1')
    assert restored.get_snapshot()['sworn_selected'] is None
    assert restored.get_snapshot()['sworn_supply'] == 42
