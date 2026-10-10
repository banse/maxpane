"""Keyless, block-pinned wallet balances over the existing chain state pools.

This client owns no wallet cache. The manager retains last-good reads and guards
wallet generations. Every call refreshes decimals alongside balances, including
for proxies; only a complete valid pair produces a current whole-token quantity.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence

import httpx

from maxpane_dashboard.data.evm_abi import decode_uint256
from maxpane_dashboard.data.rpc_classify import (
    BASE_ENDPOINT_LIMITATION_FRAGMENTS, ETH_ENDPOINT_LIMITATION_FRAGMENTS,
)
from maxpane_dashboard.data.rpc_common import OwnedHttpClient
from maxpane_dashboard.data.surf_client import STATE_RPC_FALLBACKS, STATE_RPC_PRIMARY
from maxpane_dashboard.data.surf_launch_base_client import BASE_LAUNCH_RPCS, read_batch
from maxpane_dashboard.data.surf_launch_rh_client import ROBINHOOD_LAUNCH_RPCS
from maxpane_dashboard.data.surf_pool4 import ERC20_SELECTORS, encode_balance_of

STATE_RPCS = {
    1: (STATE_RPC_PRIMARY, *STATE_RPC_FALLBACKS),
    8453: BASE_LAUNCH_RPCS,
    4663: ROBINHOOD_LAUNCH_RPCS,
}
_ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')
_WORD = re.compile(r'0x[0-9a-fA-F]{64}')
_QUANTITY = re.compile(r'0x[0-9a-fA-F]{1,64}')


def _uint_word(value) -> int | None:
    return decode_uint256(value) if isinstance(value, str) and _WORD.fullmatch(value) else None


def _rpc_quantity(value) -> int | None:
    return int(value, 16) if isinstance(value, str) and _QUANTITY.fullmatch(value) else None


def _record(balance=None, decimals=None, *, block=None, now=None, state='unavailable') -> dict:
    places = _uint_word(decimals)
    if places is not None and places > 255:
        places = None
    raw = _uint_word(balance)
    quantity = raw / 10**places if raw is not None and places is not None else None
    if quantity is not None and not math.isfinite(quantity):
        quantity = None
    known = quantity is not None
    return dict(balance_raw=raw, decimals=places, held_quantity=quantity,
                balance_state='ok' if known else state,
                balance_read_at=now if known else None,
                balance_block=block if known else None)


class PortfolioBalanceClient(OwnedHttpClient):
    """Read at most ``batch_size`` tokens per batch and ``concurrency`` chains.

    Inject an httpx client or transport for offline tests. An injected client
    stays owned by its caller. ``rpcs`` can replace supported-chain state pools;
    each selected endpoint must report the actual intended chain before its
    block or call results are accepted. No unsupported chain is inferred.
    """

    def __init__(self, *, http_client: httpx.AsyncClient | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 rpcs: Mapping[int, Sequence[str]] | None = None,
                 now_fn: Callable[[], float] = time.time,
                 batch_size: int = 20, concurrency: int = 3) -> None:
        if not 1 <= batch_size <= 100 or not 1 <= concurrency <= 3:
            raise ValueError('Batch size must be 1–100 and concurrency 1–3')
        self._client = http_client or httpx.AsyncClient(
            timeout=10, transport=transport, follow_redirects=False,
        )
        self._owns_client = http_client is None
        self._rpcs = {chain: tuple(urls) for chain, urls in (STATE_RPCS if rpcs is None else rpcs).items()
                      if chain in STATE_RPCS}
        self._now = now_fn
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(concurrency)

    async def read_balances(self, wallet: str, tokens: list[dict]) -> dict[str, dict]:
        """Return one honest balance record per token ID, never fabricated zero."""
        results = {token['id']: _record() for token in tokens}
        if not isinstance(wallet, str) or not _ADDRESS.fullmatch(wallet):
            return results
        chains: dict[int, dict[str, list[str]]] = {}
        for token in tokens:
            chain, address = token.get('chain_id'), token.get('token_address')
            if type(chain) is not int or chain not in STATE_RPCS:
                results[token['id']] = _record(state='unsupported')
            elif isinstance(address, str) and _ADDRESS.fullmatch(address):
                chains.setdefault(chain, {}).setdefault(address.lower(), []).append(token['id'])

        async def read_chain(chain, addresses):
            async with self._semaphore:
                records = await self._read_chain(wallet, chain, list(addresses))
            for address, record in records.items():
                for token_id in addresses[address]:
                    results[token_id] = dict(record)

        await asyncio.gather(*(read_chain(chain, addresses) for chain, addresses in chains.items()))
        return results

    async def _read_chain(self, wallet: str, chain: int, pending: list[str]) -> dict:
        records = {}
        fragments = BASE_ENDPOINT_LIMITATION_FRAGMENTS if chain == 8453 else ETH_ENDPOINT_LIMITATION_FRAGMENTS
        for url in self._rpcs.get(chain, ()):
            header = await read_batch(self._client, (url,), [
                ('eth_chainId', []), ('eth_blockNumber', []),
            ], fragments)
            if header is None or _rpc_quantity(header[0]) != chain:
                continue
            block = _rpc_quantity(header[1])
            if block is None:
                continue
            for start in range(0, len(pending), self._batch_size):
                chunk = pending[start:start+self._batch_size]
                calls = [('eth_chainId', [])]
                for address in chunk:
                    calls.extend((
                        ('eth_call', [{'to': address, 'data': encode_balance_of(wallet)}, hex(block)]),
                        ('eth_call', [{'to': address, 'data': ERC20_SELECTORS['decimals']}, hex(block)]),
                    ))
                answer = await read_batch(self._client, (url,), calls, fragments)
                if answer is None or _rpc_quantity(answer[0]) != chain:
                    pending = pending[start:]
                    break
                now = self._now()
                for index, address in enumerate(chunk):
                    records[address] = _record(answer[2*index+1], answer[2*index+2], block=block, now=now)
            else:
                return records
        return records
