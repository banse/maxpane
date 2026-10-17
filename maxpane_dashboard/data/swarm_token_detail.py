"""Bounded, cancellable launch enrichment for one immutable token selection.

Market reads stay owned by the overview manager. This reader owns only its
launch/job/workflow/site task; successful section clocks survive failed reads.
"""
import asyncio
from copy import deepcopy
import time

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import ZERO, address
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_NODE_KEYS
from maxpane_dashboard.data.surf_swarm import launch_rows, parse_seat_token, site_rows
from maxpane_dashboard.data.swarm_token_detail_models import SOURCE_NAMES


def _text(value):
    return value if isinstance(value, str) and value else None


def _stale_token(token):
    for name in ('market', 'history', 'trades', 'liquidity'):
        if token.get(name + '_read_at') is not None:
            token[name + '_state'] = 'stale'
    return token


class SwarmTokenDetailManager:
    """One selected launch, never a mutable table cursor or first-row fallback."""

    TTL, REQUEST_TIMEOUT = 300, 20
    MAX_JOBS, MAX_NODES, MAX_SITES, CONCURRENCY = 12, 128, 2000, 3
    MAX_ARTIFACTS = 128

    def __init__(self, tokens_manager, token, *, client=None, clock=time.time):
        self.overview = tokens_manager
        self.is_mock = bool(getattr(tokens_manager, 'is_mock', False))
        self.client = client if client is not None else getattr(tokens_manager, 'client', None)
        self._clock = clock
        self._token = deepcopy(token)
        self._identity = (token.get('id'), token.get('chain_id'), address(token.get('token_address')))
        self._launch_id = parse_job_id(token.get('launch_uuid'))
        self._enabled = bool(not self.is_mock and self.client and self._launch_id
                             and type(self._identity[1]) is int and self._identity[2] not in (None, ZERO))
        self._launch = self._contributors = self._artifacts = None
        self._sources = {name: dict(state='pending' if self._enabled else 'unavailable', read_ts=None, partial=False)
                         for name in SOURCE_NAMES}
        if self._identity[2] not in (None, ZERO) and type(self._identity[1]) is int:
            self._artifacts = [self._artifact('token', token.get('name') or token.get('symbol'),
                                              self._identity[2])]
        self._task = None
        self._attempt = None
        self._closed = False
        self._active_view, self._retired = 'token', set()
        self._view_epoch = 0
        self._semaphore = asyncio.Semaphore(self.CONCURRENCY)

    def _artifact(self, kind, name, contract=None, *, site=None):
        return dict(kind=kind, name=name, address=contract, chain_id=self._identity[1],
                    site_label=site.get('label') if site else None,
                    site_ens_name=site.get('ens_name') if site else None)

    def _fail(self, name):
        self._sources[name]['state'] = ('stale' if self._sources[name]['read_ts'] is not None
                                        else 'unavailable')

    def _publish(self, name, value, state='ok'):
        setattr(self, '_' + name, value)
        self._sources[name] = dict(state=state, read_ts=self._clock(), partial=state == 'partial')

    async def _read(self, method, identity=None):
        epoch = self._view_epoch
        result = None
        try:
            async with self._semaphore:
                async with asyncio.timeout(self.REQUEST_TIMEOUT):
                    operation = getattr(self.client, method)
                    result = await operation(identity) if identity is not None else await operation()
        except Exception:
            pass
        if epoch != self._view_epoch or self._active_view is None or self._closed:
            raise asyncio.CancelledError('retired token detail read')
        return result

    def _decode_launch(self, raw):
        if (not isinstance(raw, dict) or raw.get('id') != self._launch_id
                or type(raw.get('chainId')) is not int or raw['chainId'] != self._identity[1]
                or not isinstance(raw.get('artifacts'), list)
                or not any(isinstance(a, dict) and a.get('role') == 'token'
                           and address(a.get('address')) == self._identity[2] for a in raw['artifacts'])
                or not _text(raw.get('status'))):
            return None
        row = launch_rows([dict(raw, artifacts=[])])[0]
        jobs = raw.get('jobs')
        objective = next((_text(job.get('objective')) for job in jobs
                          if isinstance(job, dict) and _text(job.get('objective'))), None) if isinstance(jobs, list) else None
        launch = dict(id=self._launch_id, number=row['launch_number'], chain_id=row['chain_id'],
                      status=row['status'], verdict=self._token.get('verdict'), objective=objective,
                      recorded_ts=row['created_ts'], repo_url=row['repo_url'],
                      site_label=None, site_ens_name=None)
        artifacts, seen = [], set()
        malformed = len(raw['artifacts']) > self.MAX_ARTIFACTS
        for item in raw['artifacts'][:self.MAX_ARTIFACTS]:
            contract = address(item.get('address')) if isinstance(item, dict) else None
            if contract in (None, ZERO):
                malformed = True
                continue
            if contract not in seen:
                seen.add(contract)
                artifacts.append(self._artifact('token' if item.get('role') == 'token' else 'contract',
                                                 _text(item.get('name')) or _text(item.get('role')), contract))
        return launch, artifacts, malformed

    def _decode_job(self, raw, identity, stage):
        if (not isinstance(raw, dict) or raw.get('id') != identity or not _text(raw.get('state'))
                or not isinstance(raw.get('nodes'), list) or len(raw['nodes']) > self.MAX_NODES):
            return None
        rows, seen, partial = [], set(), False
        for node in raw['nodes']:
            if not isinstance(node, dict) or not _text(node.get('key')) or not _text(node.get('state')):
                partial = True
                continue
            if node['state'] != 'accepted' or node['key'] in SWARM_ORACLE_NODE_KEYS:
                continue
            seat = node.get('seat')
            seat = parse_seat_token(seat.get('tokenId')) if isinstance(seat, dict) else None
            if seat is None:
                partial = True
                continue
            role = _text(node.get('role')) or 'unknown'
            role = 'build' if role == 'implement' else role
            key = seat, role, identity
            if key not in seen:
                seen.add(key)
                rows.append(dict(seat=seat, role=role, job_id=identity, state='accepted', stage=stage))
        return rows, partial

    async def _job(self, identity):
        raw = await self._read('fetch_job', identity)
        decoded = self._decode_job(raw, identity, 'contracts')
        if decoded is None:
            return None, set(), True
        rows, partial = decoded
        proven = {identity}
        workflow = raw.get('workflow')
        if 'workflow' not in raw:
            return rows, proven, True
        if workflow is None:
            return rows, proven, partial
        workflow_id = parse_job_id(workflow.get('id')) if isinstance(workflow, dict) else None
        linked = await self._read('fetch_workflow', workflow_id) if workflow_id else None
        if (not isinstance(linked, dict) or linked.get('id') != workflow_id
                or not isinstance(linked.get('contracts'), dict) or linked['contracts'].get('id') != identity
                or not isinstance(linked.get('launch'), dict) or linked['launch'].get('id') != self._launch_id
                or 'frontend' not in linked):
            return rows, proven, True
        frontend = linked['frontend']
        if frontend is None:
            return rows, proven, partial
        frontend_id = parse_job_id(frontend.get('id')) if isinstance(frontend, dict) else None
        if frontend_id is None:
            return rows, proven, True
        detail = await self._read('fetch_job', frontend_id)
        decoded = self._decode_job(detail, frontend_id, 'frontend')
        if decoded is None:
            return rows, proven, True
        frontend_workflow = detail.get('workflow')
        if not isinstance(frontend_workflow, dict) or frontend_workflow.get('id') != workflow_id:
            return rows, proven, True
        proven.add(frontend_id)
        return rows + decoded[0], proven, partial or decoded[1]

    async def _refresh(self):
        raw = await self._read('fetch_launch_jobs', self._launch_id)
        decoded = self._decode_launch(raw)
        if decoded is None:
            for name in SOURCE_NAMES:
                self._fail(name)
            return
        launch, artifacts, artifacts_partial = decoded
        self._publish('launch', launch)
        jobs = raw.get('jobs')
        ids = list(dict.fromkeys(parse_job_id(job.get('id')) for job in jobs
                                 if isinstance(job, dict))) if isinstance(jobs, list) else []
        partial = (not isinstance(jobs, list) or len(ids) != len(jobs)
                   or None in ids or len(ids) > self.MAX_JOBS)
        ids = [identity for identity in ids if identity is not None][:self.MAX_JOBS]
        results = await asyncio.gather(*(self._job(identity) for identity in ids),
                                       self._read('fetch_sites'))
        sites = results.pop()
        contributors, proven, known = {}, set(), False
        for rows, job_ids, incomplete in results:
            partial |= incomplete
            proven.update(job_ids)
            if rows is not None:
                known = True
                for row in rows:
                    contributors[row['seat'], row['role'], row['job_id']] = row
        if known or not partial:
            self._publish('contributors', list(contributors.values()), 'partial' if partial else 'ok')
        else:
            self._fail('contributors')
        if not isinstance(sites, list) or any(not isinstance(site, dict) for site in sites):
            if self._sources['artifacts']['read_ts'] is not None:
                self._fail('artifacts')
                return
            sites = []
            artifacts_partial = True
        artifacts_partial |= len(sites) > self.MAX_SITES or partial
        for site in site_rows(sites[:self.MAX_SITES]):
            if (site['job_id'] not in proven or site['superseded_by']
                    or site['status'] not in ('named', 'published', 'live')
                    or not site['ens_name']):
                continue
            if not any(item['site_ens_name'] == site['ens_name'] for item in artifacts):
                artifacts.append(self._artifact('site', site['label'] or site['ens_name'], site=site))
                if launch['site_ens_name'] is None:
                    launch.update(site_label=site['label'], site_ens_name=site['ens_name'])
        self._publish('artifacts', artifacts, 'partial' if artifacts_partial else 'ok')

    def is_loading(self, view: str | None = None) -> bool:
        """Combine this reader with only its selected token's borrowed reads."""
        if self._closed or self._active_view is None:
            return False
        if self._task is not None and not self._task.done() and not self._task.cancelling():
            return True
        loading = getattr(self.overview, 'is_loading', None)
        return bool(loading(token_id=self._identity[0])) if loading is not None else False

    def _accept_token(self, token):
        if (isinstance(token, dict) and (token.get('id'), token.get('chain_id'),
                address(token.get('token_address'))) == self._identity
                and token.get('launch_uuid') == self._launch_id):
            self._token = deepcopy(token)
        else:
            _stale_token(self._token)

    async def fetch_and_compute(self):
        await self.drain_reads()
        now = self._clock()
        epoch = self._view_epoch
        if not self._closed and self._active_view is not None:
            refresh = getattr(self.overview, 'fetch_selected_token', None)
            if refresh and not self.is_mock:
                try:
                    token = await refresh(self._identity[0], launch_uuid=self._launch_id)
                except Exception:
                    token = None
                if epoch != self._view_epoch or self._active_view is None or self._closed:
                    raise asyncio.CancelledError('retired token market read')
                self._accept_token(token)
            if (self._enabled and (self._task is None or self._task.done())
                    and (self._attempt is None or now - self._attempt >= self.TTL)):
                self._attempt = now
                self._task = asyncio.create_task(self._refresh())
        return self.get_snapshot()

    def get_snapshot(self):
        """Refresh completed borrowed values and project without scheduling I/O."""
        getter = getattr(self.overview, 'get_selected_token', None)
        if getter is not None and not self.is_mock and not self._closed:
            self._accept_token(getter(self._identity[0], launch_uuid=self._launch_id))
        now = self._clock()
        sources = deepcopy(self._sources)
        for source in sources.values():
            if source['read_ts'] is not None and not 0 <= now - source['read_ts'] < self.TTL:
                source['state'] = 'stale'
        return deepcopy(dict(token=self._token, launch=self._launch, contributors=self._contributors,
                             artifacts=self._artifacts, sources=sources, as_of=now, is_mock=self.is_mock))

    async def wait_pending(self):
        """Observable completion without a sleep or ownership of overview work."""
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    def set_active_view(self, view):
        """Suspend this launch and its borrowed market reads, retaining results."""
        if view == self._active_view:
            return
        self._active_view = view
        self._view_epoch += 1
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._retired.add(self._task)
        if view is not None:
            self._attempt = None
        setter = getattr(self.overview, 'set_active_view', None)
        if setter is not None:
            setter('token:' + self._identity[0] if view is not None else None)

    async def drain_reads(self):
        tasks = tuple(self._retired)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._retired.difference_update(tasks)
        drain = getattr(self.overview, 'drain_reads', None)
        if drain is not None:
            await drain()

    async def close(self):
        self._closed = True
        self.set_active_view(None)
        await self.drain_reads()
        await self.wait_pending()
