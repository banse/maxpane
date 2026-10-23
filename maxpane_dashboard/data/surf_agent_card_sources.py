"""Selected-agent token earnings and job membership, with independent read clocks."""
import asyncio

from maxpane_dashboard.analytics.surf_launch_checks import address
from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data import surf_agent_earnings as earnings
from maxpane_dashboard.data import surf_agent_work as work
from maxpane_dashboard.data.surf_cache import SLOT_AGENT_EARNINGS, SLOT_AGENT_WORK, SLOT_SWARM_ORACLE_INDEX
from maxpane_dashboard.data.surf_news_hero import _stamp, source
from maxpane_dashboard.data.surf_swarm import coerce_oracle_index

TTL = 600


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
                    oracle_chains=oracle.get('chains', {}),
                    earnings_failed=set(self.earnings_failed), work_failed=set(self.work_failed),
                    pending=set(self.pending))

    async def read(self, seat, now):
        # Sources write disjoint cache slots; a slow explorer cannot gate job reads.
        await asyncio.gather(self._earnings(seat, now), self._work(seat, now))

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

    async def _work(self, seat, now):
        points = self.capture(now)['work']
        candidates = work.record_candidates(seat)
        accepted = set(work.candidates(seat))
        self.work_attempts = {job: stamp for job, stamp in self.work_attempts.items() if job in candidates}
        due = work.due(seat, points, now, cap=len(candidates), include_attempts=True)
        due.sort(key=lambda job: (job not in accepted, job in points, self.work_attempts.get(job, 0)))
        async def read_job(job):
            self.work_attempts[job] = now
            try:
                read = await self.swarm.read_job_detail(job)
                stamp = read.observed_at if read is not None else None
                detail = read.payload if read is not None else None
                point = work.membership_point(detail, job, stamp)
                if point is not None and point['shipped'] is None:
                    workflow = await self.swarm.fetch_workflow(detail['workflow']['id'])
                    identity = work.workflow_contract(detail, workflow, job)
                    contract = (read if identity == job else await self.swarm.read_job_detail(identity)) if identity else None
                    if contract is not None and contract.observed_at is not None:
                        stamp = min(stamp, contract.observed_at)
                        point = work.workflow_point(detail, workflow, contract.payload, job, stamp)
                    else:
                        point = None
            except Exception:
                point = None
            if point is None:
                self.work_failed.add(job)
                return
            points[job] = point
            self.work_failed.discard(job)
            self.cache.store_last_good(SLOT_AGENT_WORK, work.coerce_points(points, float(self.clock())), ts=stamp)

        # Finish typical seat histories on the first read without an unbounded burst.
        batch = due[:64]
        for offset in range(0, len(batch), 4):
            await asyncio.gather(*(read_job(job) for job in batch[offset:offset+4]))


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
    accepted = work.accepted_rows(seat)
    if earned and (accepted is None or any(parse_job_id(row.get('jobId')) is None for row in accepted)):
        earned.update(earned=None, earned_24h=None, worked_on=None, worked_on_24h=None, worked_recent=None)
    points = capture.get('work', {})
    nodes = work.summarize(seat, points, now, oracle_chains=capture.get('oracle_chains'))
    jobs = work.record_candidates(seat)
    stamps = [points[job]['read_ts'] for job in jobs if job in points]
    membership = source(min(stamps, default=None), now=now, ttl=TTL,
                        failed=bool(set(jobs) & capture.get('work_failed', set())))
    if (nodes['launches_total'] is None or nodes['oracle_total'] is None) and membership['state'] == 'ok':
        membership['state'] = 'partial'
    return (dict(_agent_earnings=earned, _agent_nodes=nodes),
            dict(earnings=earned_source, agent_work=membership))
