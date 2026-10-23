"""Bounded public NFT transport; every physical send uses the same cycle budget."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
import re
import time
from urllib.parse import urlsplit

import httpx

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data.rpc_common import OwnedHttpClient, jsonrpc_payload
from maxpane_dashboard.data.surf_swarm_client import SWARM_API_HOSTS
from maxpane_dashboard.data.surf_nft_readme import decode_readme, repository_reference
from maxpane_dashboard.data.surf_transport import HostCoordinator, SurfTransport


class BudgetExhausted(RuntimeError):
    """The caller must preserve its cursor and continue in another cycle."""


class SourceUnavailable(RuntimeError):
    """A failed read, distinct from an observed empty result."""


@dataclass
class Budget:
    http_limit: int = 24
    rpc_limit: int = 256
    deadline_seconds: float = 15.
    monotonic: Callable[[], float] = time.monotonic
    http_attempts: int = 0
    reserved_http: int = 0
    rpc_calls: int = 0
    started: float = field(init=False)

    def __post_init__(self):
        if (type(self.http_limit) is not int or self.http_limit < 0
                or type(self.rpc_limit) is not int or self.rpc_limit < 0
                or not math.isfinite(self.deadline_seconds) or self.deadline_seconds <= 0):
            raise ValueError('invalid NFT budget')
        self.started = self.monotonic()

    @property
    def remaining_seconds(self) -> float:
        return max(0., self.deadline_seconds - (self.monotonic() - self.started))

    @property
    def remaining_http(self) -> int:
        return max(0, self.http_limit - self.http_attempts - self.reserved_http)

    def can_admit(self, *, http=1, rpc=0) -> bool:
        return (http >= 0 and rpc >= 0 and self.remaining_seconds > 0
                and self.http_attempts + self.reserved_http + http <= self.http_limit
                and self.rpc_calls + rpc <= self.rpc_limit)

    def consume(self, *, http=0, rpc=0) -> None:
        if not self.can_admit(http=http, rpc=rpc):
            raise BudgetExhausted('NFT cycle quota or deadline reached')
        self.http_attempts += http
        self.rpc_calls += rpc

    def reserve_shared_job(self) -> None:
        if not self.can_admit(http=2):
            raise BudgetExhausted('no two-host job reservation available')
        self.reserved_http += 2

    def refund_shared_job(self) -> None:
        self.reserved_http = max(0, self.reserved_http - 2)

    @contextmanager
    def limit(self, *, http, rpc, seconds=None):
        """Temporary work slice, retaining the one cycle's actual counters."""
        if type(http) is not int or type(rpc) is not int or min(http, rpc) < 0:
            raise ValueError('invalid budget slice')
        if seconds is not None and (not math.isfinite(seconds) or seconds <= 0):
            raise ValueError('invalid time slice')
        original = self.http_limit, self.rpc_limit, self.deadline_seconds
        self.http_limit = min(self.http_limit, self.http_attempts + self.reserved_http + http)
        self.rpc_limit = min(self.rpc_limit, self.rpc_calls + rpc)
        if seconds is not None:
            self.deadline_seconds = min(self.deadline_seconds, self.monotonic() - self.started + seconds)
        try:
            yield self
        finally:
            self.http_limit, self.rpc_limit, self.deadline_seconds = original


@dataclass(frozen=True)
class Page:
    rows: list[dict]
    next_cursor: str | int | None
    terminal: bool
    observed_at: float
    provider_total: int | None = None
    warning: str | None = None


@dataclass(frozen=True)
class SourceRead:
    payload: dict
    observed_at: float


_RPC_METHODS = frozenset({'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber',
                         'eth_getCode', 'eth_call', 'eth_getTransactionReceipt',
                         'eth_getTransactionByHash', 'eth_getLogs', 'eth_getStorageAt'})
_STATE_URLS = {
    1: ('https://ethereum-rpc.publicnode.com', 'https://gateway.tenderly.co/public/mainnet'),
    4663: ('https://rpc.mainnet.chain.robinhood.com', 'https://robinhood-rpc.publicnode.com'),
}
_LOG_URLS = {
    1: ('https://gateway.tenderly.co/public/mainnet', 'https://rpc.mevblocker.io'),
    4663: _STATE_URLS[4663],
}
_EXPLORERS = {1: 'eth.blockscout.com', 4663: 'robinhoodchain.blockscout.com'}
_ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', value):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def valid_page_cursor(source, cursor):
    """One cursor contract for requests and independently restored source progress."""
    if cursor is None:
        return True
    if source in ('launches', 'publications'):
        return type(cursor) is int and cursor > 0
    return source in ('jobs', 'workflows') and _timestamp(cursor) is not None


def _source_url(reference) -> str:
    if isinstance(reference, dict):
        if reference.get('kind') == 'blockscout':
            chain, address, resource = (reference.get(k) for k in ('chain_id', 'address', 'resource'))
            if (type(chain) is not int or chain not in _EXPLORERS
                    or not isinstance(address, str) or not _ADDRESS.fullmatch(address)
                    or resource not in ('smart-contracts', 'tokens', 'addresses')):
                raise ValueError('invalid explorer reference')
            reference = f'https://{_EXPLORERS[chain]}/api/v2/{resource}/{address}'
        elif reference.get('kind') == 'github':
            repo, commit, path = (reference.get(k) for k in ('repo', 'commit', 'path'))
            if not isinstance(repo, str) or not repo.startswith('https://github.com/'):
                raise ValueError('invalid pinned repository')
            reference = f'https://raw.githubusercontent.com/{repo[19:]}/{commit}/{path}'
    if not isinstance(reference, str):
        raise ValueError('source reference must be a pinned URL')
    p = urlsplit(reference)
    if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
            or p.query or p.fragment or '%' in p.path or '\\' in p.path
            or any(part in ('..', '.') for part in p.path.split('/'))):
        raise ValueError('invalid public source URL')
    if p.hostname == 'raw.githubusercontent.com':
        if re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[0-9a-fA-F]{40}/[A-Za-z0-9_./-]+\.(?:sol|json)', p.path):
            return reference
    if p.hostname in _EXPLORERS.values():
        if re.fullmatch(r'/api/v2/(?:smart-contracts|tokens|addresses)/0x[0-9a-fA-F]{40}', p.path):
            return reference
    raise ValueError('source URL is not an allowlisted pinned read')


class SurfNftClient(OwnedHttpClient):
    def __init__(self, *, http_client=None, clock=time.time, monotonic=time.monotonic,
                 inter_call_delay=.12, sleep=asyncio.sleep, max_response_bytes=5_000_000,
                 transport=None):
        self._client = http_client or httpx.AsyncClient(follow_redirects=False)
        self._owns_client = http_client is None
        self.clock, self.monotonic = clock, monotonic
        custom_clock = clock is not time.time or monotonic is not time.monotonic or sleep is not asyncio.sleep
        self._transport = transport or SurfTransport(delay=inter_call_delay, coordinator=(
            HostCoordinator(clock=clock, monotonic=monotonic, sleep=sleep) if custom_clock else None))
        self._max_bytes = max_response_bytes
        self._global = asyncio.Semaphore(4)
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self.events: list[dict] = []
        self._request_id = 0
        self._verified_chains: dict[str, tuple[int, float]] = {}

    @property
    def cooldown(self):
        return self._transport.coordinator.cooldown

    def can_read_shared_job(self):
        """Borrowed memo reads must not start through an owned host cooldown."""
        return all(self.cooldown.get(urlsplit(url).hostname, 0) <= self.monotonic()
                   for url in SWARM_API_HOSTS)

    async def _request(self, method, url, *, budget, params=None, payload=None, text=False,
                       missing_ok=False, timeout_seconds=None):
        host = urlsplit(url).hostname
        if self.cooldown.get(host, 0) > self.monotonic():
            raise SourceUnavailable('host cooldown')
        if not budget.can_admit():
            raise BudgetExhausted('request not admitted')
        slots = self._hosts.setdefault(host, asyncio.Semaphore(2))
        remaining = budget.remaining_seconds
        source_limited = timeout_seconds is not None and timeout_seconds < remaining
        deadline = min(remaining, timeout_seconds) if source_limited else remaining
        try:
            async with asyncio.timeout(deadline):
                async with self._global, slots:
                    await self._transport.acquire(url)
                    budget.consume(http=1)
                    event = {'host': host, 'method': method, 'started': self.monotonic(), 'status': None}
                    self.events.append(event)
                    del self.events[:-256]
                    async with self._client.stream(method, url, params=params, json=payload,
                                                   timeout=min(15., budget.remaining_seconds),
                                                   follow_redirects=False) as response:
                        event['status'] = response.status_code
                        self._transport.observe(url, response)
                        if missing_ok and response.status_code == 404:
                            return None
                        if response.status_code != 200:
                            raise SourceUnavailable(f'HTTP {response.status_code}')
                        content = bytearray()
                        async for part in response.aiter_bytes():
                            content.extend(part)
                            if len(content) > self._max_bytes:
                                raise SourceUnavailable('response size bound exceeded')
                        event['finished'] = self.monotonic()
                        try:
                            return content.decode('utf-8') if text else json.loads(content)
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise SourceUnavailable('malformed public response') from exc
        except TimeoutError as exc:
            # Optional enrichment must not exhaust every inspection slice and
            # replay forever. Retain its failure so pinned RPC reads can advance.
            if source_limited and budget.remaining_seconds > 0:
                raise SourceUnavailable('optional public source timed out') from exc
            raise BudgetExhausted('cycle deadline reached') from exc
        except (httpx.HTTPError, OSError) as exc:
            raise SourceUnavailable('transport failed') from exc

    async def _get(self, path, *, budget, params=None):
        for host in SWARM_API_HOSTS:
            try:
                return await self._request('GET', host + path, params=params, budget=budget)
            except SourceUnavailable:
                continue
        raise SourceUnavailable('public API did not answer')

    async def page(self, source, *, cursor=None, query=None, since=None, budget):
        if source not in ('launches', 'jobs', 'workflows', 'publications', 'sites'):
            raise ValueError('unknown discovery source')
        if query is not None and (source != 'jobs' or not isinstance(query, str) or len(query) > 200):
            raise ValueError('invalid search query')
        if not valid_page_cursor(source, cursor):
            raise ValueError('invalid discovery cursor')
        if since is not None and (source not in ('jobs', 'workflows') or _timestamp(since) is None):
            raise ValueError('invalid update filter')
        if source == 'publications':
            params = {'page': str(cursor or 1), 'pageSize': '100'}
        else:
            params = {'limit': '100'}
            if cursor is not None:
                params['before'] = str(cursor)
            if query is not None:
                params['q'] = query
            if since is not None:
                params['since'] = since
        body = await self._get('/' + source, budget=budget, params=params)
        rows = body.get('items' if source == 'publications' else source) if isinstance(body, dict) else None
        if (not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(r, dict) for r in rows)
                or any(not isinstance(r.get('id'), str) or not r['id'] for r in rows)
                or len({r['id'] for r in rows}) != len(rows)):
            raise SourceUnavailable('malformed discovery page')
        warning = None
        if since is not None and any(_timestamp(row.get('updatedAt')) is None or
                                     _timestamp(row['updatedAt']) < _timestamp(since) for row in rows):
            raise SourceUnavailable('update filter was not honored')
        if source == 'publications':
            total, pages = body.get('count'), body.get('totalPages')
            if type(total) is not int or total < 0 or type(pages) is not int or pages < 0:
                raise SourceUnavailable('malformed publication totals')
            terminal = (cursor or 1) >= pages
            if not rows and not terminal:
                raise SourceUnavailable('empty nonterminal publication page')
            next_cursor = (cursor or 1) + 1
        elif source == 'sites':
            total, next_cursor, terminal = None, None, True  # Supplementary only.
        else:
            field = 'launchNumber' if source == 'launches' else 'createdAt'
            previous = cursor
            for row in rows:
                value = row.get(field)
                valid = type(value) is int and value > 0 if source == 'launches' else _timestamp(value) is not None
                if not valid or parse_job_id(row['id']) is None:
                    raise SourceUnavailable('invalid row identity/cursor')
                if previous is not None:
                    current_key = value if source == 'launches' else _timestamp(value)
                    previous_key = previous if source == 'launches' else _timestamp(previous)
                    if current_key > previous_key or ((previous == cursor or source == 'launches') and current_key >= previous_key):
                        raise SourceUnavailable('exclusive cursor did not progress')
                previous = value
            total, next_cursor, terminal = None, previous, len(rows) < 100
            if len(rows) == 100 and source != 'launches' and sum(r[field] == previous for r in rows) > 1:
                warning = 'timestamp_boundary_tie'
        return Page(rows, next_cursor, terminal, self.clock(), total, warning)

    async def detail(self, kind, identity, *, budget):
        if kind == 'capabilities' and identity is None:
            path = '/requests/capabilities'
        elif kind in ('launches', 'workflows') and parse_job_id(identity) is not None:
            path = f'/{kind}/{identity}'
        else:
            raise ValueError('invalid public detail reference')
        body = await self._get(path, budget=budget)
        if not isinstance(body, dict) or (kind != 'capabilities' and body.get('id') != identity):
            raise SourceUnavailable('invalid detail identity')
        return SourceRead(body, self.clock())

    async def rpc(self, chain_id, method, params, *, budget):
        if method == 'eth_blockNumber':
            async def read():
                return (await self.rpc_batch(chain_id, [(method, params)], budget=budget))[0]
            return await self._transport.head(chain_id, read)
        return (await self.rpc_batch(chain_id, [(method, params)], budget=budget))[0]

    async def rpc_batch(self, chain_id, calls, *, budget, return_exceptions=False):
        if type(chain_id) is not int or chain_id not in _STATE_URLS:
            raise ValueError('unsupported NFT chain')
        if (not isinstance(calls, (list, tuple)) or not 1 <= len(calls) <= 32
                or any(not isinstance(c, (tuple, list)) or len(c) != 2 or c[0] not in _RPC_METHODS
                       or not isinstance(c[1], list) for c in calls)):
            raise ValueError('invalid read-only RPC operations')
        if chain_id == 4663 and len(calls) > 1:
            values = []
            for method, params in calls:
                try:
                    values.append(await self.rpc(chain_id, method, params, budget=budget))
                except SourceUnavailable as error:
                    if not return_exceptions:
                        raise
                    values.append(error)
            return values
        budget.consume(rpc=len(calls))
        payload = []
        for method, params in calls:
            self._request_id += 1
            payload.append(jsonrpc_payload(self._request_id, method, params))
        urls = (_LOG_URLS if any(m == 'eth_getLogs' for m, _ in calls) else _STATE_URLS)[chain_id]
        failures = []
        for url in urls:
            try:
                includes_chain = any(method == 'eth_chainId' for method, _ in calls)
                verified_chain, verified_at = self._verified_chains.get(url, (None, -math.inf))
                if not includes_chain and (verified_chain != chain_id or self.monotonic() - verified_at >= 120.):
                    budget.consume(rpc=1)
                    self._request_id += 1
                    check_id = self._request_id
                    check = await self._request('POST', url, payload=jsonrpc_payload(check_id, 'eth_chainId', []), budget=budget)
                    if (not isinstance(check, dict) or check.get('jsonrpc') != '2.0'
                            or type(check.get('id')) is not int or check['id'] != check_id
                            or check.get('result') != hex(chain_id) or 'error' in check):
                        raise SourceUnavailable('endpoint chain identity mismatch')
                    self._verified_chains[url] = (chain_id, self.monotonic())
                for method, params in calls:
                    if method == 'eth_getLogs' and params and isinstance(params[0], dict):
                        target = params[0].get('toBlock')
                        if isinstance(target, str) and re.fullmatch(r'0x[0-9a-fA-F]+', target):
                            async def header(request):
                                budget.consume(rpc=1)
                                return await self._request('POST', url, payload=request, budget=budget)
                            if not await self._transport.prove_block(
                                    self._client, url, int(target, 16), loader=header):
                                raise SourceUnavailable('endpoint does not serve target block')
                body = await self._request('POST', url, payload=payload[0] if len(payload) == 1 else payload, budget=budget)
                responses = [body] if len(payload) == 1 else body
                if not isinstance(responses, list) or len(responses) != len(payload):
                    raise SourceUnavailable('invalid RPC envelope')
                by_id = {}
                for row in responses:
                    if (not isinstance(row, dict) or type(row.get('id')) is not int
                            or row['id'] in by_id or row.get('jsonrpc') != '2.0'
                            or row['id'] not in {request['id'] for request in payload}):
                        raise SourceUnavailable('RPC read failed')
                    if 'error' in row:
                        error = row['error']
                        message = error.get('message') if isinstance(error, dict) else None
                        if not isinstance(message, str):
                            message = 'RPC read failed'
                        error = SourceUnavailable(re.sub(r'[\x00-\x20\x7f]+', ' ', message)[:200])
                        if not return_exceptions:
                            raise error
                        by_id[row['id']] = error
                    elif 'result' not in row:
                        raise SourceUnavailable('RPC read failed')
                    else:
                        by_id[row['id']] = row['result']
                if set(by_id) != {r['id'] for r in payload}:
                    raise SourceUnavailable('RPC response identity mismatch')
                for request in payload:
                    if request['method'] == 'eth_chainId':
                        if by_id[request['id']] != hex(chain_id):
                            self._verified_chains.pop(url, None)
                            raise SourceUnavailable('endpoint chain identity mismatch')
                        self._verified_chains[url] = (chain_id, self.monotonic())
                return [by_id[r['id']] for r in payload]
            except SourceUnavailable as error:
                failures.append(str(error)[:200])
                continue
        raise SourceUnavailable('RPC providers did not answer: ' + '; '.join(failures))

    async def source_json(self, reference, *, budget):
        return await self._request('GET', _source_url(reference), budget=budget, timeout_seconds=2.)

    async def source_text(self, reference, *, budget):
        return await self._request('GET', _source_url(reference), budget=budget, text=True, timeout_seconds=2.)

    async def readme(self, repository_url, revision, *, budget):
        repository_url, revision = repository_reference(dict(url=repository_url, commit=revision))
        path = repository_url.removeprefix('https://github.com/')
        body = await self._request('GET', f'https://api.github.com/repos/{path}/contents/README.md',
                                   params={'ref': revision} if revision else None,
                                   budget=budget, missing_ok=True)
        if body is None:
            payload = dict(repository_url=repository_url, revision=revision, readme_url=None,
                           text=None, state='missing')
        else:
            try:
                payload = decode_readme(body, repository_url, revision)
            except ValueError as exc:
                raise SourceUnavailable('invalid README response') from exc
        return SourceRead(payload, self.clock())
