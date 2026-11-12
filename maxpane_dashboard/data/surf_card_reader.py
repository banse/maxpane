"""Small Boardroom-only reads; never populate a hidden dashboard's detail tier."""
import asyncio
import logging
from collections import Counter
from copy import deepcopy

from maxpane_dashboard.analytics import surf_pool4_depth
from maxpane_dashboard.analytics.surf_work import workflow_is_open, job_family as _job_family
from maxpane_dashboard.analytics.surfboard import count
from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data import surf_work as work
from maxpane_dashboard.data import surf_oracles as oracle
from maxpane_dashboard.data import surf_swarm as swarm
from maxpane_dashboard.data import surfboard_activity as activity
from maxpane_dashboard.data.surf_card_signals import SurfCardSignals
from maxpane_dashboard.data.surf_cache import (
    SLOT_CHANNEL, SLOT_ETH_USD, SLOT_MARKET, SLOT_POOL4, TIER_MEDIUM,
    SLOT_SWARM_SEAT, SLOT_SURFBOARD_ACTIVITY,
    TIER_TTL_SECONDS, TIER_FAILURE_BACKOFF_SECONDS,
)

log = logging.getLogger(__name__)


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _presence_point(raw, token, now):
    if not isinstance(raw, dict) or swarm._served_token(raw.get('tokenId')) != token:
        return None
    stamp = swarm._ts(raw.get('at'))
    presence, standing = raw.get('presence'), raw.get('standing')
    if stamp is None or not 0 <= now - stamp <= 60 or not isinstance(standing, dict):
        return None
    # A valid standing reply explicitly uses null when no device is connected.
    # An omitted/malformed field or failed request still means unknown.
    if 'presence' in raw and presence is None:
        presence = {'connected': False}
    if not isinstance(presence, dict) or type(presence.get('connected')) is not bool:
        return None
    accepting = presence.get('acceptingWork')
    working, capacity = count(standing.get('working')), count(presence.get('maxConcurrency'))
    if not presence['connected']:
        state = 'offline'
    else:
        if type(presence.get('stale')) is not bool:
            return None
        if presence['stale']:
            state = 'offline'
        elif type(accepting) is not bool or working is None or capacity is None:
            return None
        else:
            state = 'working' if working else 'idle' if accepting else 'not_accepting'
    return dict(token_id=token, read_ts=stamp, live_state=state, working=working,
                max_concurrency=capacity, accepting_work=accepting if type(accepting) is bool else None)


class SurfCardReader:
    def __init__(self, manager):
        self.manager = manager
        self.tasks = {}
        self.attempts = {}
        self.workflows = None
        self.completed_workflows = None
        self.workflows_ts = None
        self._workflow_before = None
        self._workflow_states = {}
        self._workflow_started = None
        self.current_jobs = {}
        self.current_ts = None
        self.current_failed = False
        self.current_complete = False
        self.current_expected = None
        self._current_before = None
        self.research_rows = None
        self.research_ts = None
        self.research_failed = False
        self.research_agents = None
        self.research_agents_ts = None
        self._research_agent_requests = None
        self._research_agents_next = 0
        self._research_standings = {}
        self._busy_assignments = None
        self._presence_epochs = {}
        self._presence_points = {}
        self._presence_failed = set()
        self.pool = {}
        self.pool_ts = None
        self.pool_failed = False
        self.medium_due = {}
        self.discovery = None
        self.signals = SurfCardSignals(self)

    def offer(self, *, force=False):
        now = self.manager._clock()
        self.sync_presence()
        seats = {f'seat:{token}': token for token in self.manager.get_hub_seats() if token is not None}
        presence = {f'presence:{token}': token for token in self._presence_epochs}
        for name in list(self.tasks):
            if name.startswith('seat:') and name not in seats:
                task = self.tasks.pop(name)
                if not task.done():
                    task.cancel()
                    self.manager._retired_reads.add(task)
        self.attempts = {name: stamp for name, stamp in self.attempts.items()
                         if not name.startswith(('seat:', 'presence:')) or name in seats or name in presence or now - stamp < 60}
        reads = self.signals.readers(force=force)
        reads += [('work', self._work), ('research', self._research), ('current', self._current), ('pool4', self._pool),
                 ('feed', self._feed), ('market', self._market)]
        reads += [(name, lambda token=token: self._seat(token)) for name, token in seats.items()]
        reads += [(name, lambda token=token: self._presence(token)) for name, token in presence.items()]
        for name, read in reads:
            task = self.tasks.get(name)
            if task is not None and not task.done():
                continue
            if name in presence and now - self.attempts.get(name, -1e20) < 60:
                continue
            if not force and now - self.attempts.get(name, -1e20) < 30:
                continue
            self.attempts[name] = now
            self.tasks[name] = asyncio.create_task(self._guard(read, name))

    async def _guard(self, read, name):
        try:
            async with asyncio.timeout(30 if name == 'research' else 12):
                await read()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if name == 'pool4':
                self.pool_failed = True
            elif name == 'current':
                self.current_failed = True
            elif name == 'research':
                self.research_failed = True
            log.debug('Boardroom %s retained last observation: %s', name, exc)

    async def wait_pending(self):
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    def sync_presence(self):
        """Retire identities synchronously, including requests which ignore cancellation."""
        selected = {token for token in self.manager.get_hub_seats() if token is not None}
        for token in self._presence_epochs.keys() - selected:
            self._presence_epochs.pop(token)
            self._presence_points.pop(token, None)
            self._presence_failed.discard(token)
            task = self.tasks.pop(f'presence:{token}', None)
            if task is not None and not task.done():
                task.cancel()
                self.manager._retired_reads.add(task)
        for token in selected:
            self._presence_epochs.setdefault(token, object())

    async def _presence(self, token):
        self.sync_presence()
        epoch = self._presence_epochs.get(token)
        if epoch is None:
            return
        point = None
        try:
            raw = await self.manager.swarm_client.fetch_seat_standing(token)
            point = _presence_point(raw, token, self.manager._clock())
        finally:
            if (self._presence_epochs.get(token) is epoch and self.manager._hub_active
                    and not self.manager._closing):
                prior = self._presence_points.get(token)
                if point is not None and (prior is None or point['read_ts'] >= prior['read_ts']):
                    self._presence_points[token] = point
                    self._presence_failed.discard(token)
                else:
                    self._presence_failed.add(token)

    def presence_snapshot(self, token):
        point = self._presence_points.get(token)
        if point is None or token not in self.manager.get_hub_seats():
            return None
        fresh = token not in self._presence_failed and 0 <= self.manager._clock() - point['read_ts'] <= 120
        return dict(deepcopy(point), state='ok' if fresh else 'stale')

    async def _seat(self, token):
        """Only assigned identity/status and work timestamps; no AGENT fan-out."""
        manager = self.manager
        raw = await manager.swarm_client.fetch_seat(token)
        state = swarm.seat_state(raw, token)
        if (state is None or manager._closing or not manager._hub_active
                or token not in manager.get_hub_seats()):
            return
        now = float(manager._clock())
        prior = manager.cache.get_last_good(SLOT_SWARM_SEAT)
        slot = swarm.coerce_seat_slot(getattr(prior, 'payload', None), now=now) or {'seats': {}}
        seats = slot['seats']
        point = dict(state=state, seat=raw if state == 'ok' else None)
        previous = seats.get(str(token))
        if previous is None or any(previous[key] != value for key, value in point.items()):
            seats[str(token)] = dict(point, read_ts=now)
        elif next(iter(seats)) != str(token):
            seats[str(token)] = dict(previous, seen_ts=now)
        slot = swarm.coerce_seat_slot(slot, now=now)
        if prior is None or prior.payload != slot:
            manager.cache.store_last_good(SLOT_SWARM_SEAT, slot, ts=now)
        observed = manager.cache.get_last_good(SLOT_SURFBOARD_ACTIVITY)
        seeded = activity.with_records(getattr(observed, 'payload', None), slot, now=now)
        if seeded is not None and seeded != observed.payload:
            manager.cache.store_last_good(SLOT_SURFBOARD_ACTIVITY, seeded, ts=observed.ts)

    async def _work(self):
        """Count complete workflow lists, resuming bounded scans between polls."""
        rows, complete, stamp = await self.manager._refresh_workflow_catalogue(self.manager._clock())
        if complete:
            states = [workflow_is_open(row.get('status')) for row in rows]
            if None not in states:
                self.workflows = sum(states)
                self.completed_workflows = sum(row.get('status') in ('completed', 'superseded') for row in rows)
                self.workflows_ts = stamp

    async def _research(self):
        """An independent active-request read; a full page cannot prove a total."""
        started = self.manager._clock()
        raw = await self.manager.swarm_client.fetch_oracle_requests(limit=500, status='assessing')
        if not isinstance(raw, list) or len(raw) >= 500:
            self.research_failed = True
            return
        rows = [oracle._row(row, self.manager._clock()) for row in raw]
        if (any(row is None or row['status'] != 'assessing' for row in rows)
                or len({row['id'] for row in rows}) != len(rows)):
            self.research_failed = True
            return
        self.research_rows, self.research_ts = rows, started
        self.research_failed = False
        identities = {(row['id'], row['job_id']) for row in rows}
        if identities != self._research_agent_requests:
            self.research_agents, self.research_agents_ts = None, None
            self._research_standings.clear()
            self._busy_assignments = None
        self._research_agent_requests = identities
        if not rows:
            self.research_agents, self.research_agents_ts = 0, started
            if not self.current_jobs:
                return
        if started < self._research_agents_next:
            return
        self.research_agents = None
        try:
            result = await self._research_agents(rows)
            if result is not None:
                self.research_agents, self.research_agents_ts = result
        finally:
            # Standing is rate-limited. Space complete attempts, including failures.
            self._research_agents_next = self.manager._clock() + 60

    async def _research_agents(self, requests):
        """Resume bounded standing reads; count only with coverage of every busy seat."""
        self._busy_assignments = None
        jobs = {row['job_id'] for row in requests}
        client = self.manager.swarm_client
        if (None in jobs or not callable(getattr(client, 'fetch_seat_standing', None))
                or not callable(getattr(client, 'fetch_overview', None))):
            return None

        def roster(raw):
            if not isinstance(raw, dict): return None
            seats, health, stamp = raw.get('seats'), raw.get('health'), raw.get('at')
            if (not isinstance(seats, dict) or len(seats) > 10000
                    or not isinstance(health, dict) or health.get('reachable') is not True
                    or type(stamp) not in (int, float)
                    or not 0 <= self.manager._clock() - stamp / 1000 <= 30):
                return None
            busy, seen = set(), set()
            for key, row in seats.items():
                token = swarm._served_token(key)
                if (token is None or token in seen or not isinstance(row, dict)
                        or swarm._served_token(row.get('tokenId')) != token
                        or type(row.get('working')) is not bool):
                    return None
                seen.add(token)
                if row['working']: busy.add(token)
            return busy

        # The full /swarm seat map includes assignments that /workers omits.
        # health.workingNow describes a different population; it is not a roster total.
        before = roster(await client.fetch_overview())
        if before is None: return None
        now = self.manager._clock()
        cached = self._research_standings
        for token in list(cached):
            if token not in before or not 0 <= now - cached[token][1] <= 300:
                cached.pop(token)
        # Missing seats first, then the oldest observations. Larger rosters resume
        # next poll rather than returning a permanently unavailable count.
        selected = sorted(before, key=lambda token: (cached.get(token, (None, -1e20))[1], token))[:32]
        gate = asyncio.Semaphore(4)
        async def read(token):
            async with gate:
                return await client.fetch_seat_standing(token)
        details = await asyncio.gather(*(read(token) for token in selected))
        for token, raw in zip(selected, details):
            cached.pop(token, None)
            if not isinstance(raw, dict) or swarm._served_token(raw.get('tokenId')) != token: continue
            stamp = swarm._ts(raw.get('at'))
            standing = raw.get('standing')
            if (stamp is None or not 0 <= self.manager._clock() - stamp <= 60
                    or not isinstance(standing, dict)): continue
            running = standing.get('running')
            if not isinstance(running, list) or count(standing.get('working')) != len(running): continue
            identities = {parse_job_id(row.get('jobId')) if isinstance(row, dict) else None for row in running}
            if None not in identities:
                cached[token] = (identities, stamp)
        # New busy seats must also have an observation before we can publish a total.
        after = roster(await client.fetch_overview())
        if after is None or not after.issubset(cached): return None
        observed = min((cached[token][1] for token in after), default=self.manager._clock())
        if not 0 <= self.manager._clock() - observed <= 300: return None
        self._busy_assignments = ({token: cached[token][0].copy() for token in after}, observed)
        return sum(bool(cached[token][0] & jobs) for token in after), observed

    def _research_snapshot(self):
        fresh = (self.research_ts is not None and not self.research_failed
                 and 0 <= self.manager._clock() - self.research_ts <= 60)
        rows = self.research_rows if fresh else None
        chains = {row['chain_id'] for row in rows or []}
        stamp = self.research_ts
        if self.research_agents is not None and self.research_agents_ts is not None:
            stamp = min(stamp, self.research_agents_ts)
        return dict(state='ok' if rows is not None else 'unavailable',
                    count=len(rows) if rows is not None else None,
                    chains=len(chains) if rows is not None and None not in chains else None,
                    read_ts=stamp)

    async def _current(self):
        """Recent jobs, one resumable older page, and at most 24 fresh details."""
        client = self.manager.swarm_client
        fence = client._monotonic()
        raw = await client.fetch_jobs(limit=100)
        if not isinstance(raw, list):
            self.current_failed = True
            return
        rows = {}
        complete = len(raw) <= 100
        for item in raw[:100]:
            row = work._job(item, self.manager._clock())
            if row is None:
                complete = False
            elif row['id'] in rows and rows[row['id']] != row:
                complete = False
            else:
                rows[row['id']] = row
        research_ids = ([row['job_id'] for row in self.research_rows if row['job_id']]
                        if self._research_snapshot()['state'] == 'ok' else [])
        def active_ids():
            return list(dict.fromkeys(
                [key for key in self.current_jobs if key not in rows] + research_ids
                + [key for key, row in rows.items() if row['state'] == 'executing']))
        # A job can remain executing long after it falls out of recent history.
        # Candidates may already be terminal. Only verified executing coverage
        # can suppress the next bounded history read.
        next_before = self._current_before
        if (len(raw) == 100 and self.current_expected is not None and self.current_expected > 0
                and (not self.current_complete or len(self.current_jobs) != self.current_expected)):
            before = self._current_before or raw[-1].get('createdAt')
            boundary = swarm._ts(before)
            tail = await client.fetch_jobs(limit=500, before=before) if boundary is not None else None
            decoded = [work._job(item, self.manager._clock()) for item in tail[:500]] if isinstance(tail, list) else []
            valid = (isinstance(tail, list) and len(tail) <= 500 and all(
                row is not None and row['created_ts'] is not None and row['created_ts'] < boundary
                for row in decoded))
            valid = valid and len({row['id'] for row in decoded}) == len(decoded)
            if valid:
                valid = all(left['created_ts'] >= right['created_ts'] for left, right in zip(decoded, decoded[1:]))
            if valid:
                for row in decoded:
                    if row['id'] in rows and rows[row['id']] != row:
                        complete = False
                    rows[row['id']] = row
                next_before = tail[-1]['createdAt'] if len(tail) == 500 else None
            else:
                complete = False
        identities = active_ids()
        complete &= len(identities) <= 24
        reads = await asyncio.gather(*(client.read_job_detail(key, fresh_after=fence)
                                      for key in identities[:24]))
        # An unread older active ID must remain eligible for the next bounded retry.
        jobs = {key: value for key, value in self.current_jobs.items() if key in identities[:24]}
        stamps = []
        for identity, read in zip(identities, reads):
            row = work._job(read.payload, self.manager._clock(), detail=True)
            if (row is None or row['id'] != identity or read.observed_at is None
                    or read.started_mono < fence or row['nodes'] is None):
                complete = False
                continue
            stamps.append(read.observed_at)
            if row['state'] == 'executing':
                jobs[identity] = dict(template=row['template'], family=_job_family(read.payload),
                    created_ts=row['created_ts'],
                    nodes=[dict(key=node['key'], state=node['state']) for node in row['nodes']])
            else:
                jobs.pop(identity, None)
        if complete:
            self._current_before = next_before
        self.current_jobs = jobs
        self.current_ts = min(stamps, default=self.manager._clock())
        self.current_complete = complete
        self.current_failed = False

    def current_work(self, source):
        """A global count match is required before calling a bounded sample complete."""
        now = self.manager._clock()
        overview = (source.get('payload') or {}).get('overview') or {}
        expected = count((overview.get('job_states') or {}).get('executing'))
        self.current_expected = expected
        source_ts = source.get('read_ts')
        fresh = (self.current_ts is not None and 0 <= now - self.current_ts <= 60
                 and type(source_ts) in (int, float) and 0 <= now - source_ts <= 60
                 and abs(self.current_ts - source_ts) <= 30
                 and source.get('state') == 'ok' and not self.current_failed)
        complete = fresh and self.current_complete and expected == len(self.current_jobs)
        facts = dict(state='ok' if complete else 'partial' if fresh else 'stale' if self.current_ts else 'unavailable',
                     read_ts=self.current_ts, node_counts=None, oracle_agents=None, waiting_jobs=None,
                     completed_workflows=self.completed_workflows, workflows_read_ts=self.workflows_ts,
                     research=self._research_snapshot(),
                     jobs_loaded=len(self.current_jobs), jobs_expected=expected,
                     reason='Current node coverage incomplete')
        facts['job_groups'] = self._job_groups(complete, facts['state'])
        if complete:
            nodes = [node for job in self.current_jobs.values() for node in job['nodes']
                     if node['state'] == 'working']
            facts['node_counts'] = dict(Counter(node['key'].replace('-', '_').split('_', 1)[0]
                                               for node in nodes))
            facts['waiting_jobs'] = sum(not any(node['state'] == 'working' for node in job['nodes'])
                                        for job in self.current_jobs.values())
            oracle = any(job['template'] is None or 'oracle' in job['template'].lower()
                         or any('oracle' in node['key'].lower() for node in job['nodes'])
                         for job in self.current_jobs.values())
            facts.update(oracle_agents=None if oracle else 0,
                         reason='API does not expose a complete live panel' if oracle else 'Complete current jobs; no oracle running')
        if facts['research']['state'] == 'ok':
            agents_fresh = self.research_agents_ts is not None and 0 <= now - self.research_agents_ts <= 300
            facts['oracle_agents'] = self.research_agents if agents_fresh else None
            facts['reason'] += ('; Research agents: distinct assigned seats, complete busy-seat coverage at the observation time'
                                if facts['oracle_agents'] is not None else '; Research worker standing coverage incomplete')
        return facts

    def _job_groups(self, complete, state):
        """Partition only a certified active set; assignments use the same busy roster."""
        complete = complete and all(job.get('family') is not None for job in self.current_jobs.values())
        assignments = self._busy_assignments
        if assignments is not None and not 0 <= self.manager._clock() - assignments[1] <= 300:
            assignments = None
        groups = {}
        for family in ('launch', 'research'):
            identities = {key for key, job in self.current_jobs.items() if job.get('family') == family}
            observed = assignments is not None and all(
                self.current_jobs[key].get('created_ts') is not None
                and self.current_jobs[key]['created_ts'] <= assignments[1] for key in identities)
            agents = (sum(bool(running & identities) for running in assignments[0].values())
                      if complete and observed else None)
            groups[family] = dict(count=len(identities) if complete else None,
                agents=0 if complete and not identities else agents,
                state='ok' if complete else 'partial' if state == 'ok' else state,
                read_ts=self.current_ts, agents_read_ts=assignments[1] if assignments else None)
        return groups

    def work_snapshot(self, source):
        launch = self.current_work(source)['job_groups']['launch']
        result = work.project(None, now=self.manager._clock())
        result['summary'].update(jobs=launch['count'], seats=launch['agents'], workflows=self.workflows)
        result.update(state=launch['state'], read_ts=launch['read_ts'],
                      partial=launch['state'] != 'ok', details_loaded=None, details_expected=None)
        return result

    async def _medium(self, slot, read, *, force=False):
        """Per-source clocks: card reads cannot satisfy a hidden detail tier."""
        now = self.manager._clock()
        entry = self.manager.cache.get_last_good(slot)
        ttl = TIER_TTL_SECONDS[TIER_MEDIUM]
        if not force and entry is not None and 0 <= now - entry.ts < ttl:
            return
        if not force and now < self.medium_due.get(slot, -1e20):
            return
        # Set before awaiting, so cancellation/timeout also respects backoff.
        self.medium_due[slot] = now + TIER_FAILURE_BACKOFF_SECONDS[TIER_MEDIUM]
        result = await read()
        if result is not None:
            self.medium_due[slot] = self.manager._clock() + ttl

    async def _feed(self):
        await self.signals.wait_chain()
        nonce = self.signals.nonce()
        cached = self.manager.cache.get_last_good(SLOT_CHANNEL)
        moved = nonce is not None and nonce != (getattr(cached, 'payload', None) or {}).get('nonce')
        async def read():
            try:
                result = await self.manager._pool_channel({TIER_MEDIUM}, self.manager._clock(), nonce)
            except BaseException:
                self.signals.failed.add('feed')
                raise
            (self.signals.failed.discard if result is not None else self.signals.failed.add)('feed')
            return result
        await self._medium(SLOT_CHANNEL, read, force=moved and 'feed' not in self.signals.failed)

    def signal_snapshot(self, data, *, now):
        return self.signals.snapshot(data, now=now)

    def signal_source(self, *, now):
        return self.signals.source(now=now)

    async def _market(self):
        from maxpane_dashboard.data.surf_cache import TIER_MEDIUM, SLOT_LAUNCHPAD
        manager = self.manager
        launch = getattr(manager.cache.get_last_good(SLOT_LAUNCHPAD), 'payload', None) or {}
        await asyncio.gather(
            self._medium(SLOT_MARKET, lambda: manager._pool_market(
                {TIER_MEDIUM}, manager._clock(), launch.get('pool_id'))),
            self._medium(SLOT_ETH_USD, lambda: manager._pool_eth_usd(
                {TIER_MEDIUM}, manager._clock())))

    async def _pool(self):
        from maxpane_dashboard.data.surf_manager import (
            IMD_TOKEN, POOL4_ADOPTED, POOL4_NETWORK_MAINNET,
            POOL4_NETWORK_SEPOLIA, POOL4_SEPOLIA_HOOK, POOL4_SEPOLIA_TOKEN,
        )
        manager = self.manager
        prior = getattr(manager.cache.get_last_good(SLOT_POOL4), 'payload', None) or {}
        channel = getattr(manager.cache.get_last_good(SLOT_CHANNEL), 'payload', None) or {}
        items = channel.get('items')
        now = manager._clock()
        if (self.discovery is None or self.discovery[0] != items
                or not 0 <= now - self.discovery[1] < TIER_TTL_SECONDS[TIER_MEDIUM]):
            discovery, _source = await manager._pool4_discovery(items, prior)
            # Cache only an established adoption; unknown never becomes a fact.
            self.discovery = ((deepcopy(items), now, discovery)
                              if _field(discovery, 'state') == POOL4_ADOPTED else None)
        else:
            discovery = self.discovery[2]
        adopted = _field(discovery, 'state') == POOL4_ADOPTED and _field(discovery, 'hook_addr')
        network = POOL4_NETWORK_MAINNET if adopted else POOL4_NETWORK_SEPOLIA
        hook_addr = _field(discovery, 'hook_addr') if adopted else POOL4_SEPOLIA_HOOK
        token = IMD_TOKEN if adopted else POOL4_SEPOLIA_TOKEN
        client = manager.pool4_client
        quote = await client.fetch_card_quote(hook_addr, network=network, token_addr=token)
        share, tick = _field(quote, 'share_price_wei'), _field(quote, 'tick')
        self.pool_failed = type(share) is not int or type(tick) is not int
        if type(share) is not int and type(tick) is not int:
            return
        identity = (network, hook_addr)
        if self.pool.get('identity') != identity:
            self.pool = {'identity': identity}
        if type(share) is int:
            self.pool['pool4_share_price'] = share / 1e18
            self.pool['share_ts'] = manager._clock()
        if type(tick) is int:
            self.pool['tick'] = tick
            self.pool['tick_ts'] = manager._clock()
        self.pool['pool4_network'] = network
        self.pool_ts = min(self.pool[key] for key in ('share_ts', 'tick_ts') if key in self.pool)

    def pool_snapshot(self):
        data = {key: value for key, value in self.pool.items() if key.startswith('pool4_')}
        quote = getattr(self.manager.cache.get_last_good(SLOT_ETH_USD), 'payload', None) or {}
        tick, eth_usd = self.pool.get('tick'), quote.get('eth_usd')
        if type(tick) is int and type(eth_usd) in (int, float) and eth_usd > 0:
            ratio = surf_pool4_depth.sqrt_ratio(tick) ** 2
            if ratio > 0:
                data['pool4_price_usd'] = eth_usd / ratio
        return data
