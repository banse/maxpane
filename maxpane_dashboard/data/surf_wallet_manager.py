"""Nonblocking wallet reads and an observed, payer-attributed artifact catalogue."""
import asyncio
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_wallet import payment_totals, timestamp
from maxpane_dashboard.data.surf_wallet_client import SurfWalletClient, wallet_address
from maxpane_dashboard.data.surf_wallet_models import empty_snapshot, WALLET_SNAPSHOT_FIELDS

_LOG = logging.getLogger(__name__)
_ACTIONS = {'job.open', 'job.continue', 'workflow.open', 'launch.open',
            'oracle.request', 'oracle.group', 'schedule.create', 'schedule.topup'}
_CHAINS = {1: 'ETH', 8453: 'BASE', 4663: 'RH'}
_HASH = re.compile(r'(?:0x)?[0-9a-fA-F]{64}')
_WORKING = {'pending', 'queued', 'planning', 'executing', 'running', 'working', 'building', 'deploying'}
_ATTENTION = {'blocked', 'failed', 'cancelled', 'canceled', 'refused', 'paused', 'exhausted'}


def _text(value, limit=180):
    return ''.join(c for c in value if c.isprintable())[:limit] if isinstance(value, str) else ''


def _hash(value):
    return ('0x' + value.removeprefix('0x')).lower() if isinstance(value, str) and _HASH.fullmatch(value) else None


def _fields(value, *, strings='', numbers='', integers='', flags=''):
    """Validate present scalar fields; None is an explicit unknown observation."""
    if not isinstance(value, dict):
        return False
    for names, check in (
        (strings, lambda v: isinstance(v, str)),
        (numbers, lambda v: type(v) in (int, float) and timestamp(v) is not None),
        (integers, lambda v: type(v) is int and v >= 0),
        (flags, lambda v: type(v) is bool),
    ):
        try:
            valid = all(value.get(key) is None or check(value[key]) for key in names.split())
        except OverflowError:
            return False
        if not valid:
            return False
    return True


def _evidence(value):
    if value is None or isinstance(value, str):
        return True
    if isinstance(value, list):
        return all(_evidence(entry) for entry in value)
    return _fields(value, strings='label url tx_hash detail linkage', integers='block_number', numbers='observed_at')


def _decimal(value):
    return isinstance(value, str) and len(value) <= 350 and re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)', value) is not None


def _payment(value, *, total=False):
    if not _fields(value, strings='asset symbol tx_hash', integers='chain_id decimals log_index count',
                   numbers='observed_at', flags='paid_complete refund_complete'):
        return False
    if value.get('chain_id') not in _CHAINS or wallet_address(value.get('asset')) is None or type(value.get('decimals')) is not int or not 0 <= value['decimals'] <= 255:
        return False
    if total:
        return all(value.get(key) is None or _decimal(value[key]) for key in ('paid', 'refunded'))
    return _decimal(value.get('amount')) and _hash(value.get('tx_hash')) is not None


def _usage(value):
    return value is None or (_fields(value, strings='unit rule latest',
        integers='count actors from_block to_block', numbers='observed_at tracking_since through_timestamp',
        flags='complete first_seen') and _evidence(value.get('evidence')))


def _same_runtime(previous, current):
    if not previous or previous.get('id') != current.get('id') or previous.get('chain_id') != current.get('chain_id'):
        return False
    if wallet_address(previous.get('address')) != wallet_address(current.get('address')):
        return False
    old, new = previous.get('deployment') or {}, current.get('deployment') or {}
    old_hash = _hash(old.get('runtime_hash')) or _hash(old.get('expected_runtime_hash'))
    new_hash = _hash(new.get('runtime_hash')) or _hash(new.get('expected_runtime_hash'))
    return old.get('confirmed') is True and new.get('confirmed') is True and old_hash is not None and old_hash == new_hash


def _record(raw, wallet):
    identity = parse_job_id(raw.get('orderId'))
    created, paid = timestamp(raw.get('createdAt')), timestamp(raw.get('paidAt'))
    if identity is None or raw.get('action') not in _ACTIONS or (created is None and paid is None):
        return None
    result = raw.get('result') if isinstance(raw.get('result'), dict) else {}
    expected = {'job.open': 'job', 'job.continue': 'job', 'launch.open': 'job',
                'workflow.open': 'workflow', 'oracle.request': 'oracle', 'oracle.group': 'oracle',
                'schedule.create': 'schedule', 'schedule.topup': 'schedule'}[raw['action']]
    refused = result.get('kind') == 'refused'
    if result.get('kind') != expected:
        result = {}
    payment = raw.get('payment') if isinstance(raw.get('payment'), dict) else {}
    payment_state = {'confirmed': 'settled', 'failed': 'failed', 'rejected': 'failed'}.get(payment.get('status'), 'pending')
    status = _text(raw.get('status'), 60) or 'unknown'
    outcome = 'refused' if refused else status
    row = dict(id=identity, payer=wallet, action=raw['action'], name=raw['action'],
               timestamp=paid if paid is not None else created, created_at=created, paid_at=paid,
               payment_state=payment_state, status=status, outcome=outcome,
               in_flight=False, follow_up=outcome == 'refused' or payment_state == 'failed',
               tx_hash=_hash(payment.get('transactionHash')), payments=None,
               evidence=[f'https://api.imd.fun/requests/paid-by/{wallet}'])
    row.update({key: parse_job_id(result.get(source)) for key, source in (
        ('job_id', 'jobId'), ('workflow_id', 'workflowId'), ('launch_id', 'launchId'),
        ('oracle_id', 'requestId'), ('schedule_id', 'scheduleId'))})
    return row


def _artifact(kind, identity, order):
    return dict(id=identity, kind=kind, name='', chain=None, chain_id=None, address=None,
                order_id=order['id'], project=None, linked_id=None, binding_checked=False,
                usage=None, version=None, site_url=None, job_id=order.get('job_id'),
                launch_id=order.get('launch_id'), deployment=None, evidence=[])


def _site(job, order):
    site = job.get('site')
    if not isinstance(site, dict):
        return None
    url = site.get('url')
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        return None
    if parsed is None or parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return None
    project = job.get('project') if isinstance(job.get('project'), dict) else {}
    project_id = parse_job_id(project.get('id')) or parse_job_id(job.get('id'))
    if project_id is None:
        return None
    value = _artifact('SITE', f'site:{project_id}', order)
    versions = project.get('versions') if isinstance(project.get('versions'), list) else []
    version = next((i + 1 for i, v in enumerate(versions) if isinstance(v, dict) and v.get('jobId') == job.get('id')), None)
    value.update(name=_text(site.get('name') or site.get('label') or job.get('objective')) or project_id[:8],
                 project=project_id, site_url=url[:2000], version=version, job_id=job.get('id'),
                 evidence=[f"https://api.imd.fun/jobs/{job['id']}"], updated_at=timestamp(job.get('updatedAt')))
    return value


def _contracts(launch, order):
    chain = launch.get('chainId')
    if type(chain) is not int or chain not in _CHAINS:
        return []
    attestation = launch.get('attestation') if isinstance(launch.get('attestation'), dict) else {}
    published_contracts = attestation.get('contracts')
    code = {c.get('name'): c for c in published_contracts if isinstance(c, dict)} if isinstance(published_contracts, list) else {}
    values = []
    for raw in launch.get('artifacts') or []:
        if not isinstance(raw, dict) or not (address := wallet_address(raw.get('address'))):
            continue
        value = _artifact('TOKEN' if raw.get('role') == 'token' else 'CONTRACT', f'{chain}:{address}', order)
        published = code.get(raw.get('name'), {})
        value.update(name=_text(raw.get('name')) or address[:10], chain=_CHAINS[chain], chain_id=chain,
                     address=address, launch_id=launch.get('id'),
                     deployment=dict(tx_hash=_hash(raw.get('txHash')), confirmed=False,
                         block_number=raw.get('blockNumber') if type(raw.get('blockNumber')) is int else None,
                         creation_code_hash=_hash(raw.get('creationCodeHash')),
                         expected_runtime_hash=_hash(published.get('deployedCodeHash')),
                         source_commit=_text(attestation.get('sourceCommit'), 80) or None),
                     evidence=[f"https://api.imd.fun/launches/{launch['id']}", f"https://api.imd.fun/jobs/{order.get('job_id')}"])
        values.append(value)
    return values


class SurfWalletManager:
    """Owns only tasks and public projections, never the borrowed transports."""
    def __init__(self, *, swarm, evidence=None, wallet='', clock=time.time, cache_path=None):
        self.client, self.evidence, self.clock = SurfWalletClient(swarm), evidence, clock
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self._snapshots, self._due, self._details = {}, {}, {}
        self._hydrated = {}
        self._wallet, self._view, self._generation = '', 'wallet', 0
        self._task, self._retired, self._closed = None, set(), False
        self._load()
        self.set_wallet(wallet)

    def set_wallet(self, address):
        wallet = wallet_address(address) if address else ''
        if wallet is None or wallet == self._wallet:
            return False
        self._cancel()
        self._wallet = wallet
        return True

    def set_active_view(self, view):
        if view != self._view:
            self._cancel()
            self._view = view

    def _cancel(self):
        self._generation += 1
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._retired.add(self._task)
        self._task = None

    async def drain_reads(self):
        if self._retired:
            await asyncio.gather(*self._retired, return_exceptions=True)
            self._retired.clear()

    def is_loading(self, view=None):
        return view in (None, 'wallet') and self._task is not None and not self._task.done() and not self._task.cancelling()

    def get_snapshot(self):
        return {'wallet_snapshot': deepcopy(self._snapshots.get(self._wallet, empty_snapshot(self._wallet)))}

    async def fetch_and_compute(self):
        if not self._closed and self._view == 'wallet' and self._wallet and not self.is_loading() and self.clock() >= self._due.get(self._wallet, 0):
            self._task = asyncio.create_task(self._read(self._wallet, self._generation))
        return self.get_snapshot()

    async def wait_pending(self):
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)

    async def close(self):
        self._closed = True
        self._cancel()
        await self.drain_reads()

    def _publish(self, wallet, generation, snapshot):
        if wallet != self._wallet or generation != self._generation or self._closed:
            return False
        self._snapshots[wallet] = deepcopy(snapshot)
        return True

    async def _read(self, wallet, generation):
        now = self.clock()
        snapshot = deepcopy(self._snapshots.get(wallet, empty_snapshot(wallet)))
        try:
            raw, schedule_result = await asyncio.gather(self.client.orders(wallet), self.client.schedules(wallet))
            if generation != self._generation:
                return
            schedules, schedule_complete = schedule_result
            old = snapshot['sources'].get('orders', {})
            if raw is None:
                snapshot['sources']['orders'] = dict(old, state='unavailable', detail='Public payer orders unavailable; retained observations')
                self._due[wallet] = now + 60
                self._publish(wallet, generation, snapshot)
                return
            orders = {r['id']: r for source in raw if (r := _record(source, wallet)) is not None}
            malformed = sum(row.get('action') in _ACTIONS and _record(row, wallet) is None for row in raw)
            if malformed:
                snapshot['sources']['orders'] = dict(old, state='unavailable', detail='Malformed payer orders; retained observations')
                self._due[wallet] = now + 60
                self._publish(wallet, generation, snapshot)
                return
            old_orders = {r['id']: r for r in snapshot['orders'] or []}
            for identity, row in orders.items():
                prior = old_orders.get(identity, {})
                if row['tx_hash'] and row['tx_hash'] == prior.get('tx_hash'):
                    row['payments'] = deepcopy(prior.get('payments'))
                    for key in ('evidence_state', 'evidence_observed_at'):
                        if key in prior:
                            row[key] = prior[key]
                if row['job_id'] == prior.get('job_id') and row['status'] == prior.get('status'):
                    for key in ('name', 'outcome', 'in_flight', 'follow_up', 'launch_id'):
                        if key in prior:
                            row[key] = prior[key]
            snapshot['orders'], snapshot['as_of'] = list(orders.values()), now
            snapshot['sources']['orders'] = dict(state='ok', observed_at=now, complete=len(raw) < 100,
                truncated=len(raw) == 100, detail='Latest 100 payer requests; not lifetime history')
            snapshot['coverage'] = ['Orders: latest 100 public payer requests; admission attempts outside this feed are unknown',
                                    'Artifacts: all observed; not a complete lifetime catalogue',
                                    'Usage: onchain only; site traffic and trading excluded', 'Refunds: unavailable without explicit receipt evidence']
            if schedules is not None:
                snapshot['schedules'] = [dict(id=s['id'], name=_text(s.get('label')), status=_text(s.get('status')),
                    owner=wallet, action=_text(s.get('action')), next_run_at=timestamp(s.get('nextRunAt')),
                    runs=s.get('runs') if isinstance(s.get('runs'), dict) else None) for s in schedules]
                snapshot['sources']['schedules'] = dict(state='ok' if schedule_complete else 'partial',
                    observed_at=now, complete=schedule_complete, detail='Owned schedules; runs are not requests')
            else:
                snapshot['sources']['schedules'] = dict(snapshot['sources'].get('schedules', {}), state='unavailable', complete=False)
            if not self._publish(wallet, generation, snapshot):
                return
            candidates, complete, details_at = await self._hydrate(snapshot['orders'], now)
            if generation != self._generation:
                return
            previous = {a['id']: a for a in snapshot['artifacts'] or []}
            # Known deployments are re-enriched even after their order leaves the latest-100 feed.
            combined = {**previous, **{a['id']: a for a in candidates}}
            if self.evidence is not None:
                snapshot['orders'], enriched, coverage = await self.evidence.enrich(snapshot['orders'], list(combined.values()), now=now)
                snapshot['coverage'].extend(coverage)
            else:
                enriched = [a for a in combined.values() if a['kind'] == 'SITE']
                snapshot['coverage'].append('Deployment, payment and usage chain evidence unavailable')
            for row in snapshot['orders']:
                prior = old_orders.get(row['id'], {})
                if row.get('payments') is None and row.get('tx_hash') == prior.get('tx_hash'):
                    row['payments'] = deepcopy(prior.get('payments'))
                    if row['payments'] and prior.get('evidence_observed_at') is not None:
                        row['evidence_observed_at'] = prior['evidence_observed_at']
            for value in enriched:
                if value.get('evidence_invalidated') is True:
                    prior = previous.get(value['id'])
                    if prior:
                        previous[value['id']] = dict(prior, usage=None, evidence_invalidated=True,
                            usage_state='invalidated',
                            evidence_state='invalidated', evidence_observed_at=value.get('evidence_observed_at'),
                            current_runtime_hash=(value.get('deployment') or {}).get('current_runtime_hash'))
                    continue
                if value.get('kind') == 'SITE' or (value.get('deployment') or {}).get('confirmed') is True:
                    prior = previous.get(value['id'])
                    if value.get('usage_state') in ('unsupported', 'invalidated'):
                        value['usage'] = None
                    elif (value.get('usage') is None and value.get('usage_state') in (None, 'unavailable')
                            and _same_runtime(prior, value) and isinstance(prior.get('usage'), dict)):
                        value['usage'] = deepcopy(prior['usage'])
                        value['usage_state'] = 'unavailable'
                    if value['kind'] != 'SITE' or not prior or (value.get('version') or 0) >= (prior.get('version') or 0):
                        previous[value['id']] = value
            snapshot['artifacts'] = list(previous.values())
            snapshot['payment_totals'] = payment_totals(snapshot['orders'])
            proven = [r for r in snapshot['orders'] if r['payment_state'] == 'settled']
            proven.extend(a for a in snapshot['artifacts'] if a['kind'] != 'SITE')
            clocks = [stamp for value in proven if (stamp := timestamp(value.get('evidence_observed_at'))) is not None]
            chain_complete = all(value.get('evidence_state') == 'ok' and (timestamp(value.get('evidence_observed_at')) or 0) >= now for value in proven) and not any(
                a['kind'] != 'SITE' and a['id'] not in previous for a in candidates)
            snapshot['sources']['chain'] = dict(state='ok' if chain_complete and clocks else 'partial' if clocks else 'unavailable',
                observed_at=min(clocks) if clocks else None, complete=chain_complete and bool(clocks),
                detail='Receipt and deployment evidence; usage requires a separate reviewed rule')
            usage_artifacts = [a for a in snapshot['artifacts'] if a['kind'] != 'SITE']
            usage = [(a.get('usage') or {}) for a in usage_artifacts]
            usage_clocks = [stamp for value in usage if (stamp := timestamp(value.get('observed_at'))) is not None]
            usage_complete = bool(usage) and all(artifact.get('usage_state') in (None, 'ok')
                and value.get('complete') is True and (timestamp(value.get('observed_at')) or 0) >= now
                for artifact, value in zip(usage_artifacts, usage))
            snapshot['sources']['usage'] = dict(state='ok' if usage_complete else 'partial' if usage_clocks else 'unavailable',
                observed_at=min(usage_clocks) if usage_clocks else None, complete=usage_complete,
                detail='Reviewed onchain usage rules; unsupported artifacts remain unknown')
            snapshot['sources']['details'] = dict(state='ok' if complete else 'partial', observed_at=details_at,
                complete=complete, detail='Explicit result IDs only; up to 48 detail reads per cycle')
            snapshot['coverage'].append('Details: complete for observed orders' if complete else 'Details: partial; unresolved results remain unknown')
            self._due[wallet] = self.clock() + (30 if complete and schedule_complete else 60)
            if self._publish(wallet, generation, snapshot):
                self._save()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOG.exception('Wallet public read failed')
            self._due[wallet] = self.clock() + 60
            snapshot['sources']['details'] = dict(snapshot['sources'].get('details', {}), state='unavailable', complete=False)
            self._publish(wallet, generation, snapshot)

    async def _hydrate(self, orders, now):
        budget, complete, candidates, observations = 48, True, {}, []
        pending, exhausted = {}, False

        async def detail(kind, identity):
            nonlocal budget, complete, exhausted
            if identity is None:
                return None
            key = (kind, identity)
            if key in pending:
                return await pending[key]
            cached = self._details.get(key)
            if cached and now < cached[0]:
                complete &= cached[3]
                if cached[2] is not None:
                    observations.append(cached[2])
                return deepcopy(cached[1])
            if budget <= 0:
                complete = False
                exhausted = True
                return deepcopy(cached[1]) if cached else None
            budget -= 1
            async def read():
                nonlocal complete
                value = await self.client.detail(kind, identity)
                if value is None:
                    complete = False
                    observed_at = cached[2] if cached else None
                    value = deepcopy(cached[1]) if cached else None
                    self._details[key] = (now + 60, value, observed_at, False)
                else:
                    observed_at = now
                    self._details[key] = (now + 30, value, now, True)
                if observed_at is not None:
                    observations.append(observed_at)
                return value
            pending[key] = asyncio.create_task(read())
            return await pending[key]

        async def job_assets(job, row):
            if not job:
                return
            site = _site(job, row)
            if site:
                prior = candidates.get(site['id'])
                if prior is None or (site.get('version') or 0) >= (prior.get('version') or 0):
                    candidates[site['id']] = site
            launch = job.get('launch') if isinstance(job.get('launch'), dict) else {}
            identity = parse_job_id(launch.get('id'))
            if identity:
                row['launch_id'] = identity
                value = await detail('launch', identity)
                if value:
                    candidates.update((a['id'], a) for a in _contracts(value, row))
                    if row['action'] == 'launch.open':
                        row['outcome'] = _text(value.get('status'), 60) or 'unknown'

        async def hydrate(row):
            job = await detail('job', row['job_id'])
            if job:
                row['name'] = _text(job.get('objective')) or row['name']
                if row['action'] in ('job.open', 'job.continue', 'launch.open'):
                    row['outcome'] = _text(job.get('state'), 60) or 'unknown'
                await job_assets(job, row)
            for kind, field in (('workflow', 'workflow_id'), ('oracle', 'oracle_id'), ('schedule', 'schedule_id')):
                value = await detail(kind, row[field])
                if not value:
                    continue
                row['name'] = _text(value.get('label') or value.get('objective') or value.get('question')) or row['name']
                row['outcome'] = _text(value.get('status') or value.get('state'), 60) or 'unknown'
                if kind == 'workflow':
                    for child in ('contractsJobId', 'frontendJobId'):
                        await job_assets(await detail('job', parse_job_id(value.get(child))), row)
            row['in_flight'] = row['outcome'] in _WORKING
            row['follow_up'] = row['outcome'] in _ATTENTION or row['payment_state'] == 'failed'

        def last_observed(row):
            return self._hydrated.get((row['payer'], row['id']), 0)

        try:
            # Finish dependent reads before admitting another root. A partially
            # traversed order keeps priority for the next bounded pass.
            for index, row in enumerate(sorted(orders, key=last_observed)):
                exhausted = False
                await hydrate(row)
                if not exhausted:
                    self._hydrated[(row['payer'], row['id'])] = now
                if budget <= 0 and index < len(orders) - 1:
                    complete = False
                    break
        finally:
            for task in pending.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending.values(), return_exceptions=True)
        return list(candidates.values()), complete, min(observations) if observations else now if not orders else None

    def _load(self):
        if self.cache_path is None:
            return
        try:
            if self.cache_path.stat().st_size > 5_000_000:
                return
            payload = json.loads(self.cache_path.read_text())
            for wallet, snapshot in payload.items():
                if wallet_address(wallet) != wallet or not self._valid(snapshot, wallet):
                    continue
                self._snapshots[wallet] = snapshot
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            pass

    @staticmethod
    def _valid(snapshot, wallet):
        if not isinstance(snapshot, dict) or set(snapshot) != set(WALLET_SNAPSHOT_FIELDS) or snapshot.get('wallet') != wallet:
            return False
        for field in ('orders', 'artifacts', 'schedules'):
            rows = snapshot[field]
            if rows is not None and (not isinstance(rows, list) or len(rows) > 5000 or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows)):
                return False
            if rows is not None and len({row['id'] for row in rows}) != len(rows):
                return False
        for row in snapshot['orders'] or []:
            if (not _fields(row, strings='action name payment_state status outcome job_id workflow_id launch_id oracle_id schedule_id tx_hash evidence_state',
                            numbers='timestamp created_at paid_at evidence_observed_at', flags='in_flight follow_up')
                    or row.get('payer') != wallet or parse_job_id(row.get('id')) is None or row.get('action') not in _ACTIONS
                    or timestamp(row.get('timestamp')) is None or not _evidence(row.get('evidence'))):
                return False
            payments = row.get('payments')
            if payments is not None and (not isinstance(payments, list) or any(not _payment(p) for p in payments)):
                return False
        for artifact in snapshot['artifacts'] or []:
            if (not _fields(artifact, strings='kind name chain address order_id project linked_id site_url job_id launch_id evidence_state current_runtime_hash usage_state',
                            integers='chain_id version', numbers='updated_at evidence_observed_at', flags='binding_checked evidence_invalidated')
                    or artifact.get('kind') not in ('SITE', 'CONTRACT', 'TOKEN') or not _usage(artifact.get('usage'))
                    or not _evidence(artifact.get('evidence'))):
                return False
            if (artifact.get('usage_state') not in (None, 'ok', 'unavailable', 'unsupported', 'invalidated')
                    or artifact.get('usage_state') in ('unsupported', 'invalidated') and artifact.get('usage') is not None):
                return False
            deployment = artifact.get('deployment')
            if deployment is not None and not _fields(deployment,
                strings='tx_hash creation_code_hash expected_runtime_hash runtime_hash current_runtime_hash source_commit linkage detail',
                integers='block_number', numbers='observed_at', flags='confirmed'):
                return False
            if artifact['kind'] != 'SITE' and (wallet_address(artifact.get('address')) is None
                    or artifact.get('chain_id') not in _CHAINS or not deployment or deployment.get('confirmed') is not True
                    or artifact['id'] != f"{artifact['chain_id']}:{artifact['address'].lower()}"):
                return False
        for schedule in snapshot['schedules'] or []:
            if (not _fields(schedule, strings='name status action', numbers='next_run_at')
                    or schedule.get('owner') != wallet or parse_job_id(schedule['id']) is None
                    or schedule.get('runs') is not None and not _fields(schedule['runs'], integers='total remaining')):
                return False
        totals = snapshot['payment_totals']
        if totals is not None and (not isinstance(totals, list) or any(not _payment(p, total=True) for p in totals)):
            return False
        if (not isinstance(snapshot['sources'], dict) or any(not _fields(source, strings='state detail',
                numbers='observed_at', flags='complete truncated') for source in snapshot['sources'].values())
                or not isinstance(snapshot['coverage'], list) or any(not isinstance(item, str) for item in snapshot['coverage'])
                or not _fields(snapshot, numbers='as_of')):
            return False
        try:
            json.dumps(snapshot, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            return False
        return True

    def _save(self):
        if self.cache_path is None:
            return
        try:
            payload = {w: s for w, s in self._snapshots.items() if self._valid(s, w)}
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(payload, allow_nan=False))
            temporary.replace(self.cache_path)
        except (OSError, ValueError, TypeError):
            _LOG.debug('Wallet public cache could not be saved')
