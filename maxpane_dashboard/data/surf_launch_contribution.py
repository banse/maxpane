"""Bounded launch/job joins, publishing only complete production contribution ranks."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from itertools import islice

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import is_production
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_CONTRIBUTION
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_NODE_KEYS
from maxpane_dashboard.data.surf_swarm import parse_seat_token

BATCH_SIZE, BACKOFF, TERMINAL_TTL, ACTIVE_TTL = 6, 120, 1800, 60
MAX_LAUNCHES, MAX_FACTS, MAX_JOBS, MAX_NODES = 10000, 100000, 128, 512
TERMINAL = {'completed', 'cancelled', 'blocked', 'failed', 'abandoned'}
logger = logging.getLogger(__name__)


def _stamp(value, now):
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and 0 <= value <= now)
    except OverflowError:
        return False


def _iso(value):
    try:
        return (isinstance(value, str) and value.endswith('Z')
                and datetime.fromisoformat(value).tzinfo is not None)
    except ValueError:
        return False


def _ids(value, limit=MAX_JOBS):
    return (isinstance(value, list) and len(value) <= limit
            and all(parse_job_id(item) is not None for item in value)
            and len(set(value)) == len(value))


def _version(row):
    return [row['chainId'], row['status'], row['updatedAt']]


def _valid_version(value):
    return (isinstance(value, list) and len(value) == 3
            and is_production(dict(chainId=value[0], status=value[1]))
            and value[1] == 'live' and _iso(value[2]))


def _valid_roles(roles, seats):
    if not isinstance(roles, dict) or set(roles) != {'build', 'review', 'unknown'}:
        return False
    for values in roles.values():
        if (not isinstance(values, list) or len(values) > MAX_NODES
                or any(type(value) is not int or value not in seats for value in values)
                or values != sorted(set(values))):
            return False
    known = set(roles['build']) | set(roles['review'])
    return known.isdisjoint(roles['unknown']) and known | set(roles['unknown']) == set(seats)


def _valid_fact(kind, value, now):
    if not isinstance(value, dict) or not _stamp(value.get('read_ts'), now):
        return False
    if kind == 'launches':
        return (set(value) == {'read_ts', 'version', 'jobs'}
                and _valid_version(value['version']) and _ids(value['jobs']))
    if type(value.get('terminal')) is not bool:
        return False
    if kind == 'jobs':
        seats = value.get('seats')
        keys = {'read_ts', 'terminal', 'seats', 'workflow'}
        return (set(value) in (keys, keys | {'roles'})
                and isinstance(seats, list) and len(seats) <= MAX_NODES
                and all(type(seat) is int and parse_seat_token(seat) is not None for seat in seats)
                and seats == sorted(set(seats))
                and (value['workflow'] is None or parse_job_id(value['workflow']) is not None)
                and ('roles' not in value or _valid_roles(value['roles'], seats)))
    return (set(value) == {'read_ts', 'terminal', 'contracts', 'frontend', 'launch'}
            and all(parse_job_id(value.get(key)) is not None for key in ('contracts', 'launch'))
            and (value.get('frontend') is None or parse_job_id(value['frontend']) is not None))


def _snapshot(value, now):
    if (not isinstance(value, dict) or set(value) not in ({'rows', 'read_ts'}, {'rows', 'read_ts', 'jobs'})
            or not _stamp(value['read_ts'], now) or not isinstance(value['rows'], list)
            or len(value['rows']) > MAX_FACTS):
        return None
    rows, seen = [], set()
    keys = {'rank', 'token_id', 'jobs', 'launches'}
    for rank, row in enumerate(value['rows'], 1):
        if (not isinstance(row, dict) or set(row) not in (keys, keys | {'build_jobs', 'review_jobs'})
                or any(type(row[key]) is not int for key in keys)
                or row['rank'] != rank or row['token_id'] < 0
                or row['token_id'] in seen or not 0 < row['jobs'] <= MAX_FACTS
                or not 0 < row['launches'] <= MAX_LAUNCHES):
            return None
        build, review = row.get('build_jobs'), row.get('review_jobs')
        if not (build is None and review is None or
                type(build) is int and type(review) is int
                and 0 <= build <= row['jobs'] and 0 <= review <= row['jobs']
                and build + review >= row['jobs']):
            return None
        seen.add(row['token_id'])
        rows.append(dict(row, build_jobs=build, review_jobs=review))
    if rows != sorted(rows, key=lambda row: (-row['jobs'], row['token_id'])):
        return None
    jobs = value.get('jobs')
    if jobs is not None and (type(jobs) is not int
            or not max((row['jobs'] for row in rows), default=0) <= jobs <= min(MAX_FACTS, sum(row['jobs'] for row in rows))):
        return None
    return dict(rows=rows, read_ts=value['read_ts'], jobs=jobs)


class LaunchContributionReader:
    """Single-flight batches; source failures never turn missing contributors into zero."""

    def __init__(self, client, cache, *, clock=time.time):
        self.client, self.cache, self.clock = client, cache, clock
        self._sleep = asyncio.sleep
        self.task = None
        self._target, self._complete, self._catalogue_ts = {}, False, None
        self._offered, self._catalogue_failed = False, False
        self._catalogue_pending = False
        self._retry_at, self._failed = 0, False
        self._facts = {kind: {} for kind in ('launches', 'jobs', 'workflows')}
        entry = cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION)
        payload = entry.payload if entry is not None and isinstance(entry.payload, dict) else {}
        now = self.clock()
        for kind, target in self._facts.items():
            values = payload.get(kind)
            if isinstance(values, dict):
                limit = MAX_LAUNCHES if kind == 'launches' else MAX_FACTS
                for identity, value in islice(values.items(), limit):
                    if parse_job_id(identity) and _valid_fact(kind, value, now):
                        target[identity] = {key: list(v) if isinstance(v, list) else v
                                            for key, v in value.items()}
        self._last = _snapshot(payload.get('snapshot'), now)

    def offer(self, catalogue, *, complete, failed=False, read_ts=None):
        """Offer a validated catalogue without awaiting network work in the caller."""
        now = self.clock()
        self._offered = True
        self._catalogue_pending = False
        if (_stamp(now, now) and complete is False and failed is False and read_ts is None
                and (catalogue is None or isinstance(catalogue, list))):
            self._catalogue_pending, self._catalogue_failed = True, False
            return
        if (not _stamp(now, now) or type(complete) is not bool or type(failed) is not bool
                or failed or not isinstance(catalogue, list) or len(catalogue) > MAX_LAUNCHES
                or not _stamp(read_ts, now)):
            self._catalogue_failed = True
            return
        target, seen = {}, set()
        for row in catalogue:
            if (not isinstance(row, dict) or parse_job_id(row.get('id')) is None
                    or row['id'] in seen or type(row.get('chainId')) is not int
                    or not isinstance(row.get('status'), str) or not _iso(row.get('updatedAt'))):
                self._catalogue_failed = True
                return
            seen.add(row['id'])
            if is_production(row) and row['status'] == 'live':
                target[row['id']] = {key: row[key] for key in ('id', 'chainId', 'status', 'updatedAt')}
        self._target, self._complete, self._catalogue_ts = target, complete, read_ts
        self._catalogue_failed = False
        if complete:
            self._prune()
        if self.task is not None and not self.task.done():
            return
        self.task = None
        if self._publish(now):
            self._failed = False
            return
        if now < self._retry_at:
            return
        if any(self._jobs_for(row, now) is None for row in target.values()):
            self._failed = False
            self.task = asyncio.create_task(self._run())

    def _fresh(self, kind, identity, now):
        fact = self._facts[kind].get(identity)
        if kind == 'jobs' and fact is not None and 'roles' not in fact:
            return None  # retain the old ranking while bounded batches backfill roles
        ttl = TERMINAL_TTL if kind == 'launches' or fact and fact['terminal'] else ACTIVE_TTL
        return fact if fact and 0 <= now - fact['read_ts'] < ttl else None

    def _jobs_for(self, row, now):
        launch = self._fresh('launches', row['id'], now)
        if launch is None or launch['version'] != _version(row):
            return None
        jobs = set(launch['jobs'])
        for identity in launch['jobs']:
            job = self._fresh('jobs', identity, now)
            if job is None:
                return None
            if job['workflow'] is not None:
                workflow = self._fresh('workflows', job['workflow'], now)
                if (workflow is None or workflow['contracts'] != identity
                        or workflow['launch'] != row['id']):
                    return None
                if workflow['frontend'] is not None:
                    jobs.add(workflow['frontend'])
        return jobs if all(self._fresh('jobs', job, now) for job in jobs) else None

    async def _get(self, kind, identity, decoder):
        method = {'launches': 'fetch_launch_jobs', 'jobs': 'fetch_job', 'workflows': 'fetch_workflow'}[kind]
        for attempt in range(3):
            raw = await getattr(self.client, method)(identity)
            if raw is not None and raw != {'error': 'busy'}:
                break
            if attempt < 2:
                await self._sleep(5 * 3 ** attempt)
        if not isinstance(raw, dict) or raw.get('id') != identity:
            raise ValueError('source identity or response unavailable')
        fact = decoder(raw)
        fact['read_ts'] = self.clock()
        if not _valid_fact(kind, fact, fact['read_ts']):
            raise ValueError('invalid contribution evidence')
        limit = MAX_LAUNCHES if kind == 'launches' else MAX_FACTS
        if identity not in self._facts[kind] and len(self._facts[kind]) >= limit:
            raise ValueError('contribution fact limit reached')
        self._facts[kind][identity] = fact
        return fact

    @staticmethod
    def _launch(raw, row):
        if (type(raw.get('chainId')) is not int or raw.get('chainId') != row['chainId']
                or raw.get('status') != 'live' or raw.get('updatedAt') != row['updatedAt']
                or not isinstance(raw.get('jobs'), list)
                or any(not isinstance(job, dict) for job in raw['jobs'])):
            raise ValueError('launch identity/version changed')
        return dict(version=_version(row), jobs=[job.get('id') for job in raw['jobs']])

    @staticmethod
    def _job(raw):
        nodes, state, workflow = raw.get('nodes'), raw.get('state'), raw.get('workflow')
        if (not isinstance(nodes, list) or len(nodes) > MAX_NODES
                or not isinstance(state, str) or not state or 'workflow' not in raw
                or workflow is not None and (not isinstance(workflow, dict)
                    or parse_job_id(workflow.get('id')) is None)):
            raise ValueError('job evidence missing')
        seats, seen = set(), set()
        roles = {key: set() for key in ('build', 'review', 'unknown')}
        for node in nodes:
            if (not isinstance(node, dict) or not isinstance(node.get('key'), str)
                    or not node['key'] or node['key'] in seen
                    or not isinstance(node.get('state'), str) or not node['state']):
                raise ValueError('node identity/state missing')
            seen.add(node['key'])
            if node['state'] == 'accepted' and node['key'] not in SWARM_ORACLE_NODE_KEYS:
                seat = node.get('seat')
                token = parse_seat_token(seat.get('tokenId')) if isinstance(seat, dict) else None
                if token is None:
                    raise ValueError('accepted seat missing')
                seats.add(token)
                role = node.get('role')
                group = ('build' if role in ('implement', 'integrate', 'test', 'tests')
                         else 'review' if role == 'review' else 'unknown')
                roles[group].add(token)
        for key in ('build', 'review'):
            roles[key].difference_update(roles['unknown'])
        return dict(seats=sorted(seats), workflow=workflow['id'] if workflow else None,
                    terminal=state in TERMINAL, roles={key: sorted(values) for key, values in roles.items()})

    @staticmethod
    def _workflow(raw):
        contracts, frontend, launch = (raw.get(key) for key in ('contracts', 'frontend', 'launch'))
        if (not isinstance(contracts, dict) or not isinstance(launch, dict)
                or launch.get('status') != 'live' or 'frontend' not in raw
                or frontend is not None and (not isinstance(frontend, dict)
                    or parse_job_id(frontend.get('id')) is None)
                or not isinstance(raw.get('status'), str) or not raw['status']):
            raise ValueError('workflow links missing')
        return dict(contracts=contracts.get('id'), frontend=frontend.get('id') if frontend else None,
                    launch=launch.get('id'), terminal=raw['status'] in TERMINAL)

    async def _read_launch(self, row):
        now = self.clock()
        launch = self._fresh('launches', row['id'], now)
        if launch is None or launch['version'] != _version(row):
            launch = await self._get('launches', row['id'], lambda raw: self._launch(raw, row))
        for identity in launch['jobs']:
            job = self._fresh('jobs', identity, self.clock())
            if job is None:
                job = await self._get('jobs', identity, self._job)
            if job['workflow'] is None:
                continue
            workflow = self._fresh('workflows', job['workflow'], self.clock())
            if workflow is None:
                workflow = await self._get('workflows', job['workflow'], self._workflow)
            if workflow['contracts'] != identity or workflow['launch'] != row['id']:
                # Do not cache an association mismatch until its TTL expires.
                self._facts['workflows'].pop(job['workflow'], None)
                raise ValueError('workflow is not associated with this launch')
            frontend = workflow['frontend']
            if frontend is not None and self._fresh('jobs', frontend, self.clock()) is None:
                await self._get('jobs', frontend, self._job)

    async def _run(self):
        row = None
        try:
            due = [row for row in self._target.values() if self._jobs_for(row, self.clock()) is None]
            for row in due[:BATCH_SIZE]:
                if self._catalogue_failed or self._target.get(row['id']) != row:
                    break
                await self._read_launch(row)
            self._failed = False
            self._publish(self.clock())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failed = True
            self._retry_at = self.clock() + BACKOFF
            logger.warning('launch contribution read failed for %s: %s', row['id'] if row else None, exc)
        finally:
            self._store()

    def _publish(self, now):
        if not self._complete or self._catalogue_failed or self._catalogue_pending:
            return False
        jobs_by_seat, launches_by_seat, clocks = {}, {}, [self._catalogue_ts]
        role_jobs = {'build': {}, 'review': {}}
        unknown = set()
        for identity, row in self._target.items():
            jobs = self._jobs_for(row, now)
            if jobs is None:
                return False
            clocks.append(self._facts['launches'][identity]['read_ts'])
            for job_id in jobs:
                fact = self._facts['jobs'][job_id]
                clocks.append(fact['read_ts'])
                if fact['workflow'] in self._facts['workflows']:
                    clocks.append(self._facts['workflows'][fact['workflow']]['read_ts'])
                for seat in fact['seats']:
                    jobs_by_seat.setdefault(seat, set()).add(job_id)
                    launches_by_seat.setdefault(seat, set()).add(identity)
                unknown.update(fact['roles']['unknown'])
                for role, by_seat in role_jobs.items():
                    for seat in fact['roles'][role]:
                        by_seat.setdefault(seat, set()).add(job_id)
        seats = sorted(jobs_by_seat, key=lambda seat: (-len(jobs_by_seat[seat]), seat))
        result = dict(rows=[dict(rank=rank, token_id=seat, jobs=len(jobs_by_seat[seat]),
                                 launches=len(launches_by_seat[seat]),
                                 **{f'{role}_jobs': None if seat in unknown else len(by_seat.get(seat, ()))
                                    for role, by_seat in role_jobs.items()})
                            for rank, seat in enumerate(seats, 1)], read_ts=min(clocks),
                      jobs=len({job for jobs in jobs_by_seat.values() for job in jobs}))
        if result != self._last:
            self._last = result
            self._store()
        return True

    def _prune(self):
        launches = self._facts['launches']
        self._facts['launches'] = {key: fact for key, fact in launches.items() if key in self._target}
        jobs = {job for fact in self._facts['launches'].values() for job in fact['jobs']}
        workflows = {self._facts['jobs'][job]['workflow'] for job in jobs if job in self._facts['jobs']}
        self._facts['workflows'] = {key: fact for key, fact in self._facts['workflows'].items() if key in workflows}
        jobs.update(fact['frontend'] for fact in self._facts['workflows'].values() if fact['frontend'])
        self._facts['jobs'] = {key: fact for key, fact in self._facts['jobs'].items() if key in jobs}

    def _store(self):
        # Facts are compact immutable records; copy maps once per batch, not per source read.
        payload = {kind: dict(facts) for kind, facts in self._facts.items()}
        payload['snapshot'] = self._last
        now = self.clock()
        if _stamp(now, now):
            self.cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=now)

    def project(self):
        now = self.clock()
        loaded = sum(self._jobs_for(row, now) is not None for row in self._target.values())
        total = len(self._target) if self._offered and not self._catalogue_failed and not self._catalogue_pending else None
        retained = self._last is not None
        running = self.task is not None and not self.task.done()
        if self._failed or self._catalogue_failed:
            state = 'stale' if retained else 'failed'
            detail = 'load failed; retaining last complete ranking' if retained else 'load failed'
        elif self._catalogue_pending:
            state, detail = 'pending', 'loading launch catalogue'
        elif not self._offered:
            state, detail = 'pending', 'refreshing launch catalogue' if retained else 'loading launch catalogue'
        elif running or loaded < len(self._target):
            state, detail = 'pending', f'loading · {loaded}/{total} launches'
        elif not self._complete:
            state, detail = 'pending', f'loading launch catalogue · {loaded} launches read'
        else:
            state, detail = 'ok', f'{total} live production launches · all history'
        return dict(state=state, rows=[dict(row) for row in self._last['rows']] if retained else None,
                    read_ts=self._last['read_ts'] if retained else None,
                    jobs=self._last['jobs'] if retained else None,
                    loaded=loaded, total=total, detail=detail)

    def cancel(self):
        if self.task is not None and not self.task.done():
            self.task.cancel()

    async def close(self):
        self.cancel()
        if self.task is not None:
            try:
                await self.task
            except asyncio.CancelledError:
                pass
