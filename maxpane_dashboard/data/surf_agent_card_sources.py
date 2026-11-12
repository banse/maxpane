"""Selected-agent token earnings and job membership, with independent read clocks."""
import asyncio

from maxpane_dashboard.analytics.surf_launch_checks import address, is_production
from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data import surf_agent_earnings as earnings
from maxpane_dashboard.data import surf_agent_work as work
from maxpane_dashboard.data.surf_cache import SLOT_AGENT_EARNINGS, SLOT_AGENT_WORK, SLOT_SWARM_ORACLE_INDEX
from maxpane_dashboard.data.surf_news_hero import _stamp, source
from maxpane_dashboard.data.surf_swarm import coerce_oracle_index, match_requests, seat_work_rows

TTL = 600
WORK_REQUEST_BUDGET, WORK_SECONDS = 24, 8


class _BudgetExhausted(Exception):
    pass


def oracle_absent(seat, index):
    """A complete request history must cover every attempt before proving absence."""
    jobs = {}
    candidates = set(work.oracle_candidates(seat, include_attempts=True))
    for row in seat_work_rows(seat):
        job, stamp = parse_job_id(row['job_id']), row['submitted_ts']
        if job not in candidates:
            continue
        previous = jobs.get(job, stamp)
        jobs[job] = max(previous, stamp) if previous is not None and stamp is not None else None
    _, _, absent = match_requests(index, [dict(job_id=job, submitted_ts=stamp)
                                         for job, stamp in jobs.items()])
    return absent


def coerce_earnings(value, now):
    result = {}
    for owner, point in value.items() if isinstance(value, dict) else []:
        if address(owner) is None or address(owner) != owner or not isinstance(point, dict) or set(point) != {'read_ts', 'rows'}:
            continue
        stamp, rows = _stamp(point['read_ts'], now), earnings.coerce_rows(point['rows'])
        if stamp is not None and now-stamp <= 48*3600 and rows is not None:
            result[owner] = dict(read_ts=stamp, rows=rows)
    return dict(sorted(result.items(), key=lambda item: -item[1]['read_ts'])[:8])


class AgentCardSources:
    def __init__(self, cache, client, swarm, *, clock):
        self.cache, self.client, self.swarm, self.clock = cache, client, swarm, clock
        self.earnings_failed, self.work_failed, self.pending = set(), set(), set()
        self.attempts = {}
        self.work_attempts = {}

    def capture(self, now):
        oracle = coerce_oracle_index(getattr(self.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX), 'payload', None)) or {}
        return dict(earnings=coerce_earnings(getattr(self.cache.get_last_good(SLOT_AGENT_EARNINGS), 'payload', None), now),
                    work=work.coerce_points(getattr(self.cache.get_last_good(SLOT_AGENT_WORK), 'payload', None), now),
                    oracle_chains=oracle.get('chains', {}), oracle_index=oracle,
                    earnings_failed=set(self.earnings_failed), work_failed=set(self.work_failed),
                    pending=set(self.pending))

    async def read(self, seat, now, *, priority_jobs=()):
        # Sources write disjoint cache slots; a slow explorer cannot gate job reads.
        await asyncio.gather(self._earnings(seat, now), self._work(seat, now, priority_jobs=priority_jobs))

    async def _earnings(self, seat, now):
        owner = address(seat.get('owner'))
        if owner is None:
            return
        points = self.capture(now)['earnings']
        point = points.get(owner)
        if point is not None and now-point['read_ts'] < TTL or now-self.attempts.get(owner, 0) < 120:
            return
        self.attempts = {key: stamp for key, stamp in self.attempts.items() if now-stamp < 120}
        self.attempts[owner] = now
        self.pending.add(owner)
        try:
            try:
                rows = earnings.coerce_rows(await self.client.fetch(owner))
            except Exception:
                rows = None
            if rows is None:
                self.earnings_failed.add(owner)
                return
            stamp = float(self.clock())
            points[owner] = dict(read_ts=stamp, rows=rows)
            self.cache.store_last_good(SLOT_AGENT_EARNINGS, coerce_earnings(points, stamp), ts=stamp)
            self.earnings_failed.discard(owner)
        finally:
            self.pending.discard(owner)

    async def _work(self, seat, now, *, priority_jobs=()):
        points = self.capture(now)['work']
        candidates = work.record_candidates(seat)
        accepted = set(work.candidates(seat))
        self.work_attempts = {job: stamp for job, stamp in self.work_attempts.items() if job in candidates}
        self.work_failed.intersection_update(candidates)
        due = work.due(seat, points, now, cap=len(candidates), include_attempts=True)
        priority = set(priority_jobs) & set(candidates)
        # Two attempts give missing history priority, then every candidate gets
        # a turn before another retry round (including stale cached facts).
        due.sort(key=lambda job: (self.work_attempts.get(job, 0) // 2,
                                 job in points and 'shipped' in points[job],
                                 self.work_attempts.get(job, 0),
                                 job not in priority, job not in accepted))
        remaining = WORK_REQUEST_BUDGET
        async def read(method, identity):
            nonlocal remaining
            if remaining <= 0:
                raise _BudgetExhausted
            remaining -= 1
            return await method(identity)
        async def read_job(job):
            self.work_attempts[job] = self.work_attempts.get(job, 0) + 1
            try:
                observed = await read(self.swarm.read_job_detail, job)
                stamp = observed.observed_at if observed is not None else None
                detail = observed.payload if observed is not None else None
                point = work.membership_point(detail, job, stamp)
                if point is not None and point['shipped'] is None:
                    workflow = await read(self.swarm.fetch_workflow, detail['workflow']['id'])
                    identity = work.workflow_contract(detail, workflow, job)
                    contract = (observed if identity == job else await read(self.swarm.read_job_detail, identity)) if identity else None
                    if contract is not None and contract.observed_at is not None:
                        stamp = min(stamp, contract.observed_at)
                        point = work.workflow_point(detail, workflow, contract.payload, job, stamp)
                    else:
                        point = None
            except _BudgetExhausted:
                return  # deferred work is not a failed observation
            except Exception:
                point = None
            if point is None:
                self.work_failed.add(job)
                return
            points[job] = point
            self.work_failed.discard(job)
            self.cache.store_last_good(SLOT_AGENT_WORK, work.coerce_points(points, float(self.clock())), ts=stamp)

        # Count every source call, including workflow/contract followups. Keep
        # completed membership points; next offer rotates past attempted jobs.
        try:
            async with asyncio.timeout(WORK_SECONDS):
                for offset in range(0, len(due), 4):
                    if remaining <= 0:
                        break
                    await asyncio.gather(*(read_job(job) for job in due[offset:offset+min(4, remaining)]))
        except TimeoutError:
            pass


def project(capture, seat, *, now):
    """Join a frozen owner source to the selected seat's complete accepted work."""
    seat = seat if isinstance(seat, dict) else {}
    owner = address(seat.get('owner'))
    point = capture.get('earnings', {}).get(owner)
    earned_source = source(point['read_ts'] if point else None, now=now, ttl=TTL,
                           failed=owner in capture.get('earnings_failed', set()))
    if owner in capture.get('pending', set()):
        earned_source = dict(state='pending', read_ts=None)
    elif owner in capture.get('earnings_failed', set()):
        earned_source['state'] = 'failed'
    earned = earnings.summarize(point['rows'], work.accepted_job_ids(seat), now) if point else {}
    if point is not None:
        earned['wallet_total'] = len({(row['chain_id'], row['token_address']) for row in point['rows']
                                     if is_production(dict(chainId=row['chain_id']))})
    accepted = work.accepted_rows(seat)
    if earned and (accepted is None or any(parse_job_id(row.get('jobId')) is None for row in accepted)):
        earned.update(earned=None, earned_24h=None, worked_on=None, worked_on_24h=None, worked_recent=None)
    points = capture.get('work', {})
    nodes = work.summarize(seat, points, now, oracle_chains=capture.get('oracle_chains'),
                           oracle_absent=oracle_absent(seat, capture.get('oracle_index')))
    jobs = work.record_candidates(seat)
    stamps = [points[job]['read_ts'] for job in jobs if job in points]
    membership = source(min(stamps, default=None), now=now, ttl=TTL,
                        failed=bool(set(jobs) & capture.get('work_failed', set())))
    if (nodes['launches_total'] is None or nodes['research_total'] is None) and membership['state'] == 'ok':
        membership['state'] = 'partial'
    return (dict(_agent_earnings=earned, _agent_nodes=nodes, _agent_accepted=work.job_counts(seat)),
            dict(earnings=earned_source, agent_work=membership))
