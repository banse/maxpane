"""Retained NFT evidence with bounded background work and cache-only navigation."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import logging
import time

from maxpane_dashboard.analytics.surf_nft import normalize_record, project_snapshot
from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data.surf_nft_cache import SurfNftCache, _stamp
from maxpane_dashboard.data.surf_nft_client import Budget, BudgetExhausted, SurfNftClient
from maxpane_dashboard.data.surf_nft_discovery import SurfNftDiscovery, discovery_candidates
from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector, inspection_revision
from maxpane_dashboard.data.surf_nft_rules.catalog import NFT_WORDS, project_catalog
from maxpane_dashboard.data.surf_nft_rules.children import FACTORIES
from maxpane_dashboard.data.surf_nft_rules.references import SEASONS
from maxpane_dashboard.data.surf_nft_rules.rules import RULES
from maxpane_dashboard.data.surf_nft_readme import repository_reference
from maxpane_dashboard.data.surf_transport import read_cycle

log = logging.getLogger(__name__)
_DISCOVERY_PARENTS = {f"{item['chainId']}:{item['factory']}" for item in FACTORIES} | {f"4663:{SEASONS['hook']}"}


class SurfNftManager:
    is_mock = False
    POLL_SECONDS = 30
    CHAIN_TTL = 120
    PROBE_TTL = 600
    FAILURE_BACKOFF = 120
    README_TTL = 600
    README_CACHE_SIZE = 32
    README_DEADLINE = 6

    def __init__(self, *, swarm, client=None, cache=None, cache_path=None,
                 clock=time.time, monotonic=time.monotonic, transport=None):
        self.swarm = swarm
        self._clock, self._monotonic = clock, monotonic
        self._owns_client = client is None
        self.client = client if client is not None else SurfNftClient(clock=clock, monotonic=monotonic, transport=transport)
        self.cache = cache if cache is not None else SurfNftCache(path=cache_path, clock=clock)
        self.state = self.cache.load()
        self.discovery = SurfNftDiscovery(client=self.client, swarm=swarm, clock=clock, monotonic=monotonic)
        self.inspector = SurfNftInspector(self.client, clock=clock)
        self._task = None
        self._closed = False
        self._selected = None
        self._last_offer = None
        self._failed = False
        self._error_count = 0
        self._inspection_attempts = {}
        self._inspection_deferred = {}
        self._inspection_focus = {}
        self.last_budget = None
        self._active_view = 'legacy'
        self._retired = set()
        self._readme_task = None
        self._readme_generation = 0
        self._readme_key = None
        self._readme_base = None
        self._readme_cache = OrderedDict()

    def _retire_readme(self):
        self._readme_generation += 1
        if self._readme_task is not None and not self._readme_task.done():
            self._readme_task.cancel()
            self._retired.add(self._readme_task)
        self._readme_task = None

    def set_active_view(self, view):
        if view == self._active_view:
            return
        self._active_view = view
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._retired.add(self._task)
        self._task = None
        self._last_offer = None
        self._retire_readme()
        self._offer_readme()

    async def drain_reads(self):
        if self._retired:
            retired = tuple(self._retired)
            await asyncio.gather(*retired, return_exceptions=True)
            self._retired.difference_update(retired)

    def select(self, identity):
        """Select cached identity and offer its own README read in the NFT view."""
        self._selected = identity if isinstance(identity, str) else None
        self._offer_readme()

    def get_readme(self):
        """Small passive projection; polling this never starts a source read."""
        if self._readme_base is None:
            return None
        result = dict(self._readme_base)
        cached = self._readme_cache.get(self._readme_key)
        if cached is not None:
            result.update(cached['record'])
        if self._readme_task is not None and not self._readme_task.done():
            result['state'] = 'pending'
        return result

    def _offer_readme(self):
        identity, key = self._selected, None
        base = (dict(identity=identity, repository_url=None, readme_url=None, revision=None,
                     text=None, observed_at=None, state='pending') if identity else None)
        row = next((row for row in self.state.get('records') or [] if row['id'] == identity), None)
        if row is not None:
            repositories = row.get('repositories') or []
            if not repositories:
                base['state'] = 'missing'
            else:
                base['state'] = 'unavailable'
                for repository in repositories:
                    try:
                        key = repository_reference(repository)
                    except (ValueError, TypeError, KeyError):
                        continue
                    base.update(repository_url=key[0], revision=key[1], state='pending')
                    break
        previous_identity = (self._readme_base or {}).get('identity')
        if identity != previous_identity or key != self._readme_key:
            self._retire_readme()
        self._readme_key, self._readme_base = key, base
        if self._closed or self._active_view != 'NFT EXPLORER' or key is None:
            return
        if self._readme_task is not None and not self._readme_task.done():
            return
        cached = self._readme_cache.get(key)
        if cached is not None:
            self._readme_cache.move_to_end(key)
            if self._clock() < cached['retry_at']:
                return
        self._readme_task = asyncio.create_task(self._read_selected(identity, key, self._readme_generation))

    async def _read_selected(self, identity, key, generation):
        # A fast selection change cancels and drains the old transport before
        # admitting its replacement. Ordinary catalogue work has its own budget.
        await self.drain_reads()
        budget = Budget(http_limit=1, rpc_limit=0, deadline_seconds=self.README_DEADLINE,
                        monotonic=self._monotonic)
        try:
            result = await self.client.readme(*key, budget=budget)
            record = dict(result.payload, observed_at=result.observed_at)
            ttl = self.README_TTL
        except asyncio.CancelledError:
            raise
        except Exception:
            previous = self._readme_cache.get(key, {}).get('record') or {}
            record = dict(repository_url=key[0], revision=key[1], readme_url=None,
                          text=None, observed_at=None)
            record.update(previous, state='unavailable')
            ttl = self.FAILURE_BACKOFF
        if (self._closed or self._active_view != 'NFT EXPLORER' or self._selected != identity
                or self._readme_key != key or self._readme_generation != generation):
            return
        self._readme_cache[key] = dict(record=record, retry_at=self._clock() + ttl)
        self._readme_cache.move_to_end(key)
        while len(self._readme_cache) > self.README_CACHE_SIZE:
            self._readme_cache.popitem(last=False)

    def is_loading(self, view=None):
        return bool(not self._closed and any(task is not None and not task.done() and not task.cancelling()
                                            for task in (self._task, self._readme_task)))

    def offer_hub(self):
        self._offer(proof_only=True)

    def _offer(self, *, proof_only=False):
        if (self._closed or self._active_view is None or self._retired
                or self._task is not None and not self._task.done()):
            return
        now = self._clock()
        interval = self.FAILURE_BACKOFF if self._failed else self.POLL_SECONDS
        if self._last_offer is not None and now - self._last_offer < interval:
            return
        self._last_offer = now
        self._task = asyncio.create_task(self._cycle(proof_only=True) if proof_only else self._cycle())

    async def fetch_and_compute(self):
        await self.drain_reads()
        self._offer_readme()
        self._offer()
        return self.get_snapshot()

    def _source(self, identity, observed_at, *, block=None, state='partial', coverage=None):
        return dict(identity=identity, observed_at=observed_at, provider_ts=None,
                    block_number=block, block_hash=None, block_timestamp=None,
                    state=state, coverage=deepcopy(coverage or {}))

    def get_snapshot(self):
        records = self.state.get('records')
        discovery = self.state.get('discovery') or {}
        raw = discovery.get('raw') or {}
        coverage = deepcopy(raw.get('coverage') or {})
        coverage.setdefault('sources', {})
        coverage.setdefault('warnings', [])
        if self.state.get('cache_partial'):
            coverage['complete'] = False
            coverage['warnings'].append('Retained evidence is bounded; historical coverage is partial.')
        observation = discovery.get('observed_at')
        source_states = discovery.get('sources') or {}
        deployments_observed = (source_states.get('launches') or {}).get('head_at') is not None
        builds_observed = any((source_states.get(name) or {}).get('head_at') is not None
                              for name in ('jobs', 'search:NFT'))
        deployed = None if records is None else [r for r in records if r['category'] == 'launched']
        builds = None if records is None else [r for r in records if r['category'] == 'in_the_making']
        if not deployments_observed and not deployed:
            deployed = None
        if not builds_observed and not builds:
            builds = None
        sources = {'discovery': self._source('swarm', observation, coverage=coverage,
                    state='ok' if coverage.get('complete') else 'partial' if observation is not None else 'pending')}
        snapshot = dict(nft_rows=deployed, nft_build_rows=builds,
                        nft_summary={'observed_at': observation}, nft_selected=None, nft_readme=self.get_readme(),
                        nft_sources=sources, nft_coverage=coverage, as_of=self._clock())
        projected = project_snapshot(snapshot, selected_id=self._selected)
        # The screen owns list projection; retained identities must remain searchable.
        projected.update(nft_rows=deepcopy(deployed), nft_build_rows=deepcopy(builds))
        return projected

    def catalogue_summary(self):
        return self.get_snapshot()['nft_summary']

    def _candidates(self):
        return {**discovery_candidates(self.state.get('discovery') or {}),
                **self.state.get('child_candidates', {})}

    def _uninspected_child(self, identity):
        return (identity in self.state.get('child_candidates', {}) and
                not self.state.get('evidence', {}).get(identity, {}).get('detectionStatus'))

    def _due(self, identity):
        if self._clock() < self._inspection_deferred.get(identity, 0):
            return False
        if identity in self.state.get('progress', {}):
            return True
        attempted = self._inspection_attempts.get(identity)
        if attempted is not None and self._clock() - attempted < self.FAILURE_BACKOFF:
            return False
        evidence = self.state.get('evidence', {}).get(identity)
        if not evidence or evidence.get('proofOnly') or self._uninspected_child(identity):
            return True
        stamp = _stamp(evidence.get('checkedAt'))
        ttl = self.CHAIN_TTL if evidence.get('standard') or identity in _DISCOVERY_PARENTS else self.PROBE_TTL
        return stamp is None or self._clock() - stamp >= ttl

    @staticmethod
    def _discovery_priority(candidate):
        """Reported NFT intent orders reads; only chain proof admits a row."""
        launch = candidate.get('launch') or {}
        notes = ((launch.get('attestation') or {}).get('manifest') or {}).get('notes')
        texts = [notes, (candidate.get('artifact') or {}).get('name')]
        texts.extend(job.get('objective') for job in launch.get('jobs') or [])
        relevant = candidate.get('nft_intent') is True or any(
            isinstance(text, str) and NFT_WORDS.search(text) for text in texts)
        number = launch.get('launchNumber')
        return not relevant, -(number if type(number) is int else 0)

    def _proof_current(self, identity, candidate):
        evidence = self.state.get('evidence', {}).get(identity, {})
        return (identity not in _DISCOVERY_PARENTS
                and evidence.get('deploymentConfirmed') is True
                and evidence.get('codePresent') is True and evidence.get('codeHash')
                and 'deployer' in (evidence.get('deployment') or {})
                and evidence.get('standard') in ('ERC-721', 'ERC-1155', 'ERC-721 + ERC-1155')
                and evidence.get('_proof_revision') == self._proof_revision(candidate, evidence))

    @staticmethod
    def _proof_revision(candidate, evidence):
        return inspection_revision(candidate) + ':' + str(evidence.get('codeHash'))

    def _proof_changed(self, identity, candidate):
        evidence = self.state.get('evidence', {}).get(identity, {})
        return (evidence.get('_proof_revision') is not None
                and (evidence['_proof_revision'] != self._proof_revision(candidate, evidence)
                     or 'deployer' not in (evidence.get('deployment') or {})))

    def _pending(self, candidates, *, proof_only=False):
        """Prove reviewed candidates before enriching already observed collections."""
        due = [(key, value) for key, value in candidates.items()
               if (self._due(key) or proof_only and self._proof_changed(key, value))
               and not (proof_only and self._proof_current(key, value))]
        due.sort(key=lambda item: (item[0] != self._selected,
                                  item[0] not in RULES,
                                  item[0] in self.state.get('evidence', {}),
                                  item[0] not in self.state.get('progress', {}),
                                  _stamp(self.state.get('evidence', {}).get(item[0], {}).get('checkedAt')) or 0,
                                  self._discovery_priority(item[1])))
        return due

    def _focus(self, candidates, *, probe=False):
        """Finish one pinned inspection before admitting another in this lane."""
        now = self._clock()
        current, started = self._inspection_focus.get(probe, (None, now))
        if current is not None and now - started >= 600:
            if current in self.state.get('progress', {}):
                self._inspection_deferred[current] = now + self.FAILURE_BACKOFF
            current = None
        evidence = self.state.get('evidence', {})
        stages = self.state.get('progress', {})
        known = {key for key, fact in evidence.items() if fact.get('standard')}
        # Reviewed factories are not necessarily NFTs themselves. Their full
        # interpreter verifies the runtime/registry and discovers proven children.
        known.update(_DISCOVERY_PARENTS)
        known.update(self.state.get('child_candidates', {}))
        known.update(row['id'] for row in self.state.get('records') or [] if row['category'] == 'launched')
        due = [key for key in candidates if (key not in known) == probe and self._due(key)
               and (key in stages or len(stages) < SurfNftCache.MAX_STAGES)]
        if probe and self._selected in self._inspection_attempts:
            # Selection already owns a slice; its partial stage cannot take the
            # independent discovery lane away from unselected candidates.
            due = [key for key in due if key != self._selected] or due
        if current in due:
            return current
        if probe and due:
            # Resume admitted proof across restarts. Every fourth new admission
            # uses oldest launch order so newer traffic cannot starve the tail.
            staged = [key for key in due if 0 <= now - stages.get(key, {}).get('started_at', 0) <= 600]
            if staged:
                identity = min(staged, key=lambda key: stages[key]['started_at'])
            else:
                turn = self.state.get('probe_turn', 0)
                self.state['probe_turn'] = (turn + 1) % 4
                def probe_rank(key):
                    number = (candidates[key].get('launch') or {}).get('launchNumber')
                    number = number if type(number) is int else 0
                    priority = (number,) if turn == 3 else self._discovery_priority(candidates[key])
                    return key in evidence, priority, self._inspection_attempts.get(key, 0), key
                identity = min(due, key=probe_rank)
            self._inspection_focus[probe] = identity, now
            return identity
        # Unknown details beat periodic refreshes; attempts break ties so a
        # reviewed or recently selected collection cannot monopolize admission.
        due.sort(key=lambda key: (not (key in _DISCOVERY_PARENTS or self._uninspected_child(key) or
                                      evidence.get(key, {}).get('proofOnly', key not in evidence)),
                                 self._inspection_attempts.get(key, 0), key != self._selected,
                                 key not in _DISCOVERY_PARENTS, key not in RULES,
                                 self._discovery_priority(candidates[key]),
                                 _stamp(evidence.get(key, {}).get('checkedAt')) or 0))
        identity = due[0] if due else None
        self._inspection_focus[probe] = identity, now
        return identity

    async def _slice(self, identity, candidate, budget, *, http, rpc, seconds=None, proof_only=False):
        before = self.state.get('progress', {}).get(identity, {}).get('completed_operations', 0)
        sent = budget.http_attempts
        with budget.limit(http=http, rpc=rpc, seconds=seconds):
            await self._inspect(identity, candidate, budget, proof_only=proof_only)
        stage = self.state.get('progress', {}).get(identity)
        if stage and (stage.get('restart_reason') or
                      budget.http_attempts > sent and stage.get('completed_operations', 0) == before):
            self._inspection_deferred[identity] = self._clock() + self.FAILURE_BACKOFF

    async def _inspect(self, identity, candidate, budget, *, proof_only=False):
        stages = self.state.setdefault('progress', {})
        if identity not in stages and len(stages) >= SurfNftCache.MAX_STAGES:
            return
        provisional = stages.get(identity, {}).get('provisional') or {}
        staged_hash = provisional.get('codeHash')
        retained_hash = self.state.get('evidence', {}).get(identity, {}).get('codeHash')
        changed_proof = (provisional.get('_proof_revision') is not None
                         and provisional['_proof_revision'] != self._proof_revision(candidate, provisional))
        if changed_proof or staged_hash and retained_hash and staged_hash != retained_hash:
            stages.pop(identity, None)
        options = dict(proof_only=True) if proof_only else {}
        result = await self.inspector.advance(candidate, stages.get(identity), budget=budget, **options)
        self._inspection_attempts[identity] = self._clock()
        if result.complete:
            stages.pop(identity, None)
        elif result.progress:
            stages[identity] = result.progress
        if result.evidence is not None:
            if result.evidence.get('deploymentConfirmed') is True and result.evidence.get('codePresent') is True:
                result.evidence['_proof_revision'] = self._proof_revision(candidate, result.evidence)
            self._retain_evidence(identity, result.evidence)
            retained = self.state.get('evidence', {}).get(identity, {})
            if (result.evidence.get('_proof_revision') and retained.get('codeHash') == result.evidence.get('codeHash')
                    and retained.get('deploymentConfirmed') is True):
                # A refreshed identity proof need not replace older detail facts
                # or claim those facts were observed at its newer block/time.
                retained['_proof_revision'] = result.evidence['_proof_revision']
                if 'deployer' in (result.evidence.get('deployment') or {}):
                    retained.setdefault('deployment', {})['deployer'] = result.evidence['deployment']['deployer']
        for child in result.children:
            key = child['key']
            self.state.setdefault('child_candidates', {})[key] = child['candidate']
            if child.get('evidence') is not None:
                self._retain_evidence(key, child['evidence'])

    def _retain_evidence(self, identity, evidence):
        previous = self.state.get('evidence', {}).get(identity)
        if previous is None:
            record = next((row for row in self.state.get('records') or [] if row['id'] == identity), None)
            if record is not None:
                previous = dict(chainId=record['chain_id'], address=record['contract'], codeHash=record['code_hash'])
        negative = (evidence.get('detectionStatus') in ('unsupported', 'not-nft') or any(
            evidence.get(field) is False for field in ('codePresent', 'receiptSuccess', 'receiptAddressMatches')))
        same_identity = previous and all(evidence.get(field) == previous.get(field) for field in ('chainId', 'address'))
        same_runtime = same_identity and evidence.get('codeHash') and evidence.get('codeHash') == previous.get('codeHash')
        changed_runtime = (same_identity and evidence.get('codePresent') is True
                           and evidence.get('codeHash') and previous.get('codeHash') and not same_runtime)
        # A new runtime invalidates old rules even if another proof read failed.
        # Deferred child candidates, conversely, cannot replace completed proof.
        unresolved = (evidence.get('deploymentConfirmed') is not True or
                      evidence.get('standard') not in ('ERC-721', 'ERC-1155', 'ERC-721 + ERC-1155'))
        provisional = evidence.get('proofOnly') and same_runtime and not previous.get('proofOnly')
        if previous is not None and not negative and not changed_runtime and (unresolved or provisional):
            return
        self.state.setdefault('evidence', {})[identity] = evidence

    async def _discover(self, budget, **limits):
        result = await self.discovery.advance(self.state.get('discovery'), budget=budget, **limits)
        self.state['discovery'] = result.state
        self.state['discovery'].setdefault('raw', {})['coverage'] = result.coverage
        return result

    def _publish(self):
        discovery = self.state.get('discovery') or {}
        if discovery.get('observed_at') is None:
            return
        raw = deepcopy(discovery.get('raw') or {})
        raw.setdefault('coverage', {'complete': False})
        candidates = self._candidates()
        catalog = project_catalog(raw, candidates, self.state.get('evidence', {}),
                                  now_iso=datetime.fromtimestamp(self._clock(), timezone.utc).isoformat())
        records = []
        for record in catalog['collections']:
            identity = record.get('id')
            launch = candidates.get(identity, {}).get('launch') or {}
            request_jobs = sorted({job['id'].lower() for job in launch.get('jobs') or []
                                   if isinstance(job, dict) and parse_job_id(job.get('id'))})
            if request_jobs:
                record.setdefault('deployment', {})['request_job_ids'] = request_jobs
            provenance = candidates.get(identity, {}).get('provenance') or {}
            sources = {'discovery': self._source(identity, provenance.get('observed_at'), coverage=raw['coverage'])}
            for job in record.get('jobs', []):
                fact = raw.get('jobDetails', {}).get(job.get('id'), {})
                job_key = 'job:' + str(job.get('id'))
                sources[job_key] = self._source(job_key, fact.get('_observed_at'))
            evidence = self.state.get('evidence', {}).get(record.get('id'), {})
            chain_source = self._source(record.get('id'), _stamp(evidence.get('checkedAt')),
                                        block=evidence.get('readBlock'))
            chain_source['block_timestamp'] = _stamp(evidence.get('readTimestamp'))
            sources['chain'] = chain_source
            normalized = normalize_record(record, sources=sources)
            if normalized is not None:
                records.append(normalized)
        # Incomplete discovery must not erase previously proven deployments.
        if catalog.get('coverage', {}).get('complete') is not True:
            present = {r['id'] for r in records}
            records.extend(r for r in self.state.get('records') or []
                           if r['category'] == 'launched' and r['id'] not in present
                           and r['id'] not in self.state.get('evidence', {}))
        self.state['records'] = records
        self.state['discovery']['raw']['coverage'] = catalog['coverage']
        self._offer_readme()

    @read_cycle
    async def _cycle(self, *, proof_only=False):
        budget = (Budget(http_limit=12, rpc_limit=96, deadline_seconds=8, monotonic=self._monotonic)
                  if proof_only else Budget(monotonic=self._monotonic))
        self.last_budget = budget
        self.state['last_attempt'] = self._clock()
        self._failed = False
        try:
            # One discovery page always precedes the selection's reserved slice.
            try:
                with budget.limit(http=4 if proof_only else 2, rpc=0, seconds=2):
                    await self._discover(budget, page_limit=1, detail_limit=1 if proof_only else 0, launch_limit=1)
            except BudgetExhausted:
                pass  # A slow discovery page must leave time for retained rows.
            candidates = self._candidates()
            if proof_only:
                # New proofs have a reserved lane even while old rule-backed
                # collections need refreshed metadata. Card budgets stay fixed.
                probe = self._focus(candidates, probe=True)
                if probe is not None:
                    await self._slice(probe, candidates[probe], budget, http=6, rpc=64, proof_only=True)
                    if self._proof_current(probe, candidates[probe]):
                        self.state['progress'].pop(probe, None)
                # Keep discovery/proof separate from mint/getter/source history.
                # Recent proofs need no detail work to render collection counts.
                for identity, candidate in self._pending(candidates, proof_only=True):
                    if identity == probe:
                        continue
                    evidence = self.state.get('evidence', {}).get(identity, {})
                    checked = _stamp(evidence.get('checkedAt'))
                    changed = self._proof_changed(identity, candidate)
                    if not changed and checked is not None and self._clock() - checked < self.CHAIN_TTL:
                        continue
                    await self._inspect(identity, candidate, budget, proof_only=identity not in _DISCOVERY_PARENTS)
                    if self._proof_current(identity, candidate):
                        self.state['progress'].pop(identity, None)
                    if not budget.can_admit():
                        break
                if probe in self.state.get('progress', {}) and budget.can_admit():
                    await self._inspect(probe, candidates[probe], budget, proof_only=True)
                    if self._proof_current(probe, candidates[probe]):
                        self.state['progress'].pop(probe, None)
                return
            priority = self._selected if self._selected in candidates and self._due(self._selected) else None
            if priority is not None:
                await self._slice(priority, candidates[priority], budget, http=8, rpc=64, seconds=3)
            probe = self._focus(candidates, probe=True)
            if probe is not None and probe != priority and budget.can_admit():
                await self._slice(probe, candidates[probe], budget,
                                  http=3 if priority is not None else 6, rpc=32,
                                  seconds=3, proof_only=True)
            # A fresh proof is visible before its name/getters are loaded. Give
            # the oldest verified newcomer a small slice without replacing a
            # pinned factory/collection focus; background work keeps its turn.
            newcomers = [key for key, fact in self.state.get('evidence', {}).items()
                         if key in candidates and key != priority and key not in _DISCOVERY_PARENTS
                         and fact.get('proofOnly') and fact.get('deploymentConfirmed') is True
                         and fact.get('codePresent') is True and fact.get('standard') and self._due(key)]
            if newcomers and budget.remaining_http > 5 and budget.remaining_seconds > 2:
                identity = min(newcomers, key=lambda key:
                    (_stamp(self.state['evidence'][key].get('checkedAt')) or 0, key))
                await self._slice(identity, candidates[identity], budget,
                    http=min(3, budget.remaining_http - 5), rpc=64,
                    seconds=min(3, budget.remaining_seconds - 2))
            # Finish an admitted collection within its ten-minute pinned context.
            # A small separate proof lane keeps new discoveries moving. When no
            # collection needs enrichment, lend its budget to that proof lane.
            while budget.remaining_http > 4 and budget.remaining_seconds > 2:
                identity = self._focus(candidates)
                probing = identity is None
                identity = self._focus(candidates, probe=True) if probing else identity
                if identity is None:
                    break
                await self._slice(identity, candidates[identity], budget,
                                  http=budget.remaining_http - 4, rpc=192,
                                  seconds=budget.remaining_seconds - 2, proof_only=probing)
                if identity in self.state.get('progress', {}):
                    break
            # Pages and launch details used to spend every reserved send before
            # a shared job could reserve its two-host allowance. Give it a turn.
            await self._discover(budget, page_limit=0, detail_limit=1, launch_limit=0)
            await self._discover(budget, page_limit=3, detail_limit=7, launch_limit=2)
        except BudgetExhausted:
            pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failed = True
            self._error_count += 1
            log.debug('NFT batch retained previous observations: %s', exc)
        finally:
            try:
                self._publish()
            except Exception as exc:
                self._failed = True
                self._error_count += 1
                log.warning('NFT projection retained last good catalog: %s', exc)
            prepare = getattr(self.cache, 'prepare', None)
            if prepare is not None:
                self.state = prepare(self.state, selected_id=self._selected)
            keep = set(self.state.get('evidence', {})) | set(self.state.get('progress', {}))
            self._inspection_attempts = {key: stamp for key, stamp in self._inspection_attempts.items() if key in keep}
            self._inspection_deferred = {key: stamp for key, stamp in self._inspection_deferred.items()
                                        if key in keep and stamp > self._clock()}
            self.cache.save(self.state, selected_id=self._selected)

    async def wait_pending(self):
        while pending := [task for task in (self._task, self._readme_task)
                          if task is not None and not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        self._retire_readme()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        await self.drain_reads()
        await self.wait_pending()
        self.cache.save(self.state, selected_id=self._selected)
        if self._owns_client:
            await self.client.close()
