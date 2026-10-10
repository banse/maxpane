"""Wallet reward proofs reconciled against block-pinned, read-only contract views.

The verified factory's MerkleDistributor source and a matching live capture are
vendored under tests/fixtures/portfolio/claims; only its view ABI is shipped.
The explorer lists earned launch IDs; that list alone never proves readiness.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import re
import time

import httpx

from maxpane_dashboard.data.keccak import keccak256
from maxpane_dashboard.data.portfolio_balance_client import STATE_RPCS
from maxpane_dashboard.data.rpc_classify import (
    BASE_ENDPOINT_LIMITATION_FRAGMENTS, ETH_ENDPOINT_LIMITATION_FRAGMENTS,
)
from maxpane_dashboard.data.surf_launch_base_client import read_batch
from maxpane_dashboard.data.surf_pool4 import selector, ERC20_SELECTORS, encode_balance_of
from maxpane_dashboard.data.surf_swarm_client import SwarmClient, parse_job_id

EXPLORER_HOST = 'https://explorer.imd.fun'
_ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')
_WORD = re.compile(r'0x[0-9a-fA-F]{64}')
_UINT = re.compile(r'(0|[1-9][0-9]{0,77})')
# All signatures and return layouts come from the vendored verified source.
_VIEWS = {name: selector(signature) for name, signature in {
    'token': 'token()', 'round_count': 'roundCount()', 'round': 'roundOf(uint256)',
    'claimed': 'claimed(uint256,address)', 'swept': 'swept(uint256)',
    'reserved': 'reserved()',
}.items()}


def _address(value):
    return value.lower() if isinstance(value, str) and _ADDRESS.fullmatch(value) else None


def _word(value):
    return int(value, 16) if isinstance(value, str) and _WORD.fullmatch(value) else None


def _quantity(value):
    if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{1,64}', value):
        return int(value, 16)
    return None


def _source(state='unavailable', as_of=None, complete=False, **kwargs):
    return dict(state=state, as_of=as_of, complete=complete, **kwargs)


def _proof(claim, wallet):
    """OpenZeppelin StandardMerkleTree: double-hashed leaf, sorted hash pairs."""
    if not isinstance(claim, dict):
        return None
    amount, root, proof = claim.get('amount'), claim.get('root'), claim.get('proof')
    if (not isinstance(amount, str) or not _UINT.fullmatch(amount)
            or int(amount) >= 2**256 or not isinstance(root, str) or not _WORD.fullmatch(root)
            or not isinstance(proof, list) or len(proof) > 64
            or any(not isinstance(p, str) or not _WORD.fullmatch(p) for p in proof)):
        return None
    leaf = keccak256(keccak256(bytes.fromhex(wallet[2:].zfill(64) + format(int(amount), '064x'))))
    for sibling in proof:
        other = bytes.fromhex(sibling[2:])
        leaf = keccak256(min(leaf, other) + max(leaf, other))
    return (int(amount), root.lower()) if leaf.hex() == root[2:].lower() else None


def _earned(body):
    if (not isinstance(body, dict) or not isinstance(body.get('claimable'), list)
            or not isinstance(body.get('unlocks'), list)
            or any(body.get(k) not in (None, False) for k in ('next', 'nextCursor', 'hasMore'))):
        return None
    ids = list(body['claimable'])
    for item in body['unlocks']:
        if not isinstance(item, dict) or not isinstance(item.get('at'), str):
            return None
        try:
            if datetime.fromisoformat(item['at'].replace('Z', '+00:00')).tzinfo is None:
                return None
        except ValueError:
            return None
        ids.append(item.get('id'))
    if len(ids) > 10000 or any(parse_job_id(value) is None for value in ids):
        return None
    return list(dict.fromkeys(ids))


def _agents(body, wallet):
    if (not isinstance(body, dict) or _address(body.get('wallet')) != wallet
            or not isinstance(body.get('tokens'), list)):
        return None
    result = {}
    for token in body['tokens']:
        if not isinstance(token, dict) or not str(token.get('tokenId', '')).isdigit():
            return None
        device = token.get('device')
        if device is None:
            continue  # an owned, unpaired NFT is not a connected worker
        if not isinstance(device, dict):
            return None
        agent_id = token.get('agentId')
        identity = str(agent_id) if agent_id is not None else 'seat:' + str(token['tokenId'])
        row = dict(id=identity, token_id=str(token['tokenId']),
                   online=device.get('online') if type(device.get('online')) is bool else None,
                   agent_id=str(agent_id) if agent_id is not None else None)
        if identity in result and result[identity] != row:
            return None
        result[identity] = row
    return list(result.values())


class PortfolioClaimsClient(SwarmClient):
    """At most 12 launches per refresh, with wallet-partitioned progress.

    Every launch uses two public HTTP reads and bounded state batches. Round
    enumeration is capped at eight; larger histories remain unavailable.
    A wallet's current seats never decide its historical reward entitlement.
    """

    def __init__(self, *, clock=time.time, transport=None, http_client=None,
                 rpcs=None, max_launches=12, max_rounds=8, **kwargs):
        if not 1 <= max_launches <= 24 or not 1 <= max_rounds <= 32:
            raise ValueError('Claim read budgets outside supported bounds')
        client = http_client or httpx.AsyncClient(timeout=10, transport=transport, follow_redirects=False)
        super().__init__(http_client=client, **kwargs)
        self._owns_client = http_client is None
        self._explorer = SwarmClient(http_client=client, hosts=(EXPLORER_HOST,),
                                     inter_call_delay=kwargs.get('inter_call_delay', .12))
        self._clock, self._rpcs = clock, STATE_RPCS if rpcs is None else rpcs
        self._budget, self._round_budget = max_launches, max_rounds
        self._wallets = {}
        self._locks = {}

    async def fetch_claims(self, wallet):
        wallet = _address(wallet)
        if wallet is None:
            return dict(allocations=None, agents=None,
                        sources=dict(claims=_source(), agents=_source()))
        async with self._locks.setdefault(wallet, asyncio.Lock()):
            return await self._fetch(wallet)

    async def _fetch(self, wallet):
        state = self._wallets.setdefault(wallet, dict(records={}, pending=[], agents=None,
                                                       agent_at=None, enumeration_at=None))
        # Independent tasks: a slow/dead earned source must not erase presence.
        agents_task = asyncio.create_task(self._get('/pair/wallet/' + wallet))
        try:
            if not state['pending']:
                body = await self._explorer._get('/api/earned', params={'wallet': wallet})
                ids = _earned(body)
                if ids is None:
                    for row in state['records'].values():
                        row['claim_read_state'] = 'stale' if row['claim_read_at'] is not None else 'unavailable'
                    return self._result(state, await agents_task, wallet, failed=True)
                state['enumeration_at'] = self._clock()
                # Recheck known rewards even after the ready list drops a claimed leaf.
                state['pending'] = list(dict.fromkeys(ids + list(state['records'])))
            batch = state['pending'][:self._budget]
            # Four concurrent launches is a fixed bound, shared by HTTP and RPC work.
            semaphore = asyncio.Semaphore(4)
            async def fetch(launch):
                async with semaphore:
                    row = await self._allocation(wallet, launch)
                previous = state['records'].get(launch)
                if row['claim_read_state'] in ('unavailable', 'unsupported') and previous and previous['claim_read_at'] is not None:
                    row = {**previous, 'claim_read_state': 'stale', 'claim_reason': row['claim_reason']}
                return launch, row
            for launch, row in await asyncio.gather(*(fetch(launch) for launch in batch)):
                state['records'][launch] = row
            state['pending'] = state['pending'][len(batch):]
            return self._result(state, await agents_task, wallet)
        finally:
            if not agents_task.done():
                agents_task.cancel()
                await asyncio.gather(agents_task, return_exceptions=True)

    def _result(self, state, agents_body, wallet, *, failed=False):
        agents = _agents(agents_body, wallet)
        if agents is not None:
            state['agents'], state['agent_at'] = agents, self._clock()
        agent_state = 'ok' if agents is not None else 'stale' if state['agents'] is not None else 'unavailable'
        rows = {}
        for value in state['records'].values():
            row = deepcopy(value)
            if row['claim_read_at'] is not None and self._clock() - row['claim_read_at'] > 120:
                row['claim_read_state'] = 'stale'
            key = row['allocation_id']
            if key in rows:
                previous = rows[key]
                if any(previous.get(k) != row.get(k) for k in ('token_address', 'claim_raw', 'claim_state')):
                    previous.update(claim_read_state='unavailable', claimable_quantity=None,
                                    claim_reason='Conflicting allocation identities')
                previous['launch_uuids'].append(row['launch_uuid'])
            else:
                rows[key] = row
        values = list(rows.values())
        complete = not failed and not state['pending'] and all(r['claim_read_state'] == 'ok' for r in values)
        claim_state = 'ok' if complete else 'partial'
        if failed:
            claim_state = 'stale' if state['records'] else 'unavailable'
        timestamps = [r['claim_read_at'] for r in values if r['claim_read_at'] is not None]
        as_of = min(timestamps) if timestamps else state['enumeration_at']
        return dict(allocations=values if state['enumeration_at'] is not None else None,
                    agents=deepcopy(state['agents']), sources=dict(
                        claims=_source(claim_state, as_of, complete,
                                       checked=len(state['records']), total=len(state['records']) + len([x for x in state['pending'] if x not in state['records']]),
                                       reason='Claim source unavailable' if failed else 'Verifying earned allocations' if not complete else None),
                        agents=_source(agent_state, state['agent_at'], agent_state == 'ok')))

    async def _allocation(self, wallet, launch):
        row = dict(chain_id=None, token_address=None, launch_uuid=launch, launch_uuids=[launch],
                   allocation_id=launch + ':' + wallet, claimable_quantity=None,
                   locked_quantity=None, claimed_quantity=None, claim_state='unavailable',
                   claim_read_state='unavailable', claim_read_at=None, unlock_at=None,
                   claim_reason='Allocation identity or proof unavailable', claim_raw=None)
        record, answer = await asyncio.gather(
            self.fetch_launch(launch), self._explorer._get('/api/claim', params={'launch': launch, 'wallet': wallet}))
        if (not isinstance(record, dict) or record.get('id') != launch
                or type(record.get('chainId')) is not int or not isinstance(record.get('artifacts'), list)):
            return row
        identities = {}
        for artifact in record['artifacts']:
            if isinstance(artifact, dict) and artifact.get('role') in ('token', 'distributor'):
                address = _address(artifact.get('address'))
                if address is None or artifact['role'] in identities and identities[artifact['role']] != address:
                    return row
                identities[artifact['role']] = address
        if set(identities) != {'token', 'distributor'}:
            return row
        chain, token, distributor = record['chainId'], identities['token'], identities['distributor']
        row.update(chain_id=chain, token_address=token, distributor=distributor,
                   launch_number=record.get('launchNumber'))
        if not isinstance(answer, dict) or 'claim' not in answer:
            return row
        if answer['claim'] is None:
            return {**row, 'claim_state': 'none', 'claim_read_state': 'ok', 'claim_read_at': self._clock(),
                    'claimable_quantity': 0, 'locked_quantity': 0, 'claimed_quantity': 0,
                    'claim_reason': 'Wallet has no allocation'}
        proven = _proof(answer['claim'], wallet)
        if proven is None:
            return row
        amount, root = proven
        row['claim_raw'] = amount
        if chain not in STATE_RPCS or not self._rpcs.get(chain):
            return {**row, 'claim_read_state': 'unsupported', 'claim_reason': 'Claim chain unsupported'}
        evidence = await self._chain_state(chain, token, distributor, wallet, root)
        if evidence is None:
            return {**row, 'claim_reason': 'Claim contract state unavailable or identity mismatch'}
        decimals, block, stamp, round_id, unlocked, claimed, swept, funded, spent, reserved, balance = evidence
        try:
            unlock_at = datetime.fromtimestamp(unlocked, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            return {**row, 'claim_reason': 'Reward unlock time is out of range'}
        quantity = amount / 10**decimals
        row.update(allocation_id=f'{chain}:{distributor}:{round_id}:{wallet}', decimals=decimals,
                   claim_block=block, claim_block_time=stamp, claim_read_at=self._clock(),
                   unlock_at=unlock_at,
                   locked_quantity=0, claimed_quantity=0, claimable_quantity=0, claim_read_state='ok')
        if claimed:
            row.update(claim_state='claimed', claimed_quantity=quantity, claim_reason='Already claimed')
        elif swept:
            row.update(claim_state='none', claim_reason='Reward round closed')
        elif amount > funded - spent or balance < reserved:
            row.update(claim_state='unavailable', claim_read_state='unavailable', claimable_quantity=None,
                       claim_read_at=None, claim_reason='Reward funding unavailable')
        elif stamp < unlocked:
            row.update(claim_state='locked', locked_quantity=quantity, claim_reason='Reward is locked')
        else:
            row.update(claim_state='ready', claimable_quantity=quantity, claim_reason=None)
        return row

    async def _chain_state(self, chain, token, distributor, wallet, root):
        fragments = BASE_ENDPOINT_LIMITATION_FRAGMENTS if chain == 8453 else ETH_ENDPOINT_LIMITATION_FRAGMENTS
        for url in self._rpcs[chain]:
            head = await read_batch(self._client, (url,), [('eth_chainId', []), ('eth_getBlockByNumber', ['latest', False])], fragments)
            if head is None or _quantity(head[0]) != chain or not isinstance(head[1], dict):
                continue
            block, stamp = _quantity(head[1].get('number')), _quantity(head[1].get('timestamp'))
            if block is None or stamp is None:
                continue
            async def views(specs):
                calls = [('eth_chainId', [])] + [('eth_call', [{'to': address, 'data': data}, hex(block)]) for address, data in specs]
                results = await read_batch(self._client, (url,), calls, fragments)
                return results[1:] if results is not None and _quantity(results[0]) == chain else None
            base = await views([(distributor, _VIEWS['token']), (distributor, _VIEWS['round_count']),
                                (token, ERC20_SELECTORS['decimals']), (distributor, _VIEWS['reserved']),
                                (token, encode_balance_of(distributor))])
            if base is None:
                continue
            address, count, decimals, reserved, balance = [_word(v) for v in base]
            if (address != int(token, 16) or count is None or not 1 <= count <= self._round_budget
                    or decimals is None or decimals > 255 or reserved is None or balance is None):
                continue
            specs = []
            for index in range(count):
                arg = format(index, '064x')
                specs.extend([(distributor, _VIEWS['round'] + arg),
                              (distributor, _VIEWS['claimed'] + arg + wallet[2:].zfill(64)),
                              (distributor, _VIEWS['swept'] + arg)])
            rounds = await views(specs)
            if rounds is None:
                continue
            matched = []
            for index in range(count):
                record, claimed, swept = rounds[index*3:index*3+3]
                if not isinstance(record, str) or not re.fullmatch(r'0x[0-9a-fA-F]{256}', record):
                    break
                if record[:66].lower() != root:
                    continue
                funded, spent, unlocked = [int(record[i:i+64], 16) for i in (66, 130, 194)]
                claimed, swept = _word(claimed), _word(swept)
                if claimed not in (0, 1) or swept not in (0, 1) or spent > funded or unlocked >= 2**64:
                    break
                matched.append((decimals, block, stamp, index, unlocked, claimed, swept, funded, spent, reserved, balance))
            else:
                if len(matched) == 1:
                    return matched[0]
        return None
