"""Retained NFT evidence with bounded background work and cache-only navigation."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import logging
import time

from maxpane_dashboard.analytics.surf_nft import normalize_record, project_snapshot
from maxpane_dashboard.data.surf_nft_cache import SurfNftCache, _stamp
from maxpane_dashboard.data.surf_nft_client import Budget, BudgetExhausted, SurfNftClient
from maxpane_dashboard.data.surf_nft_discovery import SurfNftDiscovery, discovery_candidates
from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector
from maxpane_dashboard.data.surf_nft_rules.catalog import project_catalog
from maxpane_dashboard.data.surf_nft_rules.rules import RULES

log = logging.getLogger(__name__)


class SurfNftManager:
    is_mock = False
    POLL_SECONDS = 30
    CHAIN_TTL = 120
    PROBE_TTL = 600
    FAILURE_BACKOFF = 120

    def __init__(self, *, swarm, client=None, cache=None, cache_path=None,
                 clock=time.time, monotonic=time.monotonic):
        self.swarm = swarm
        self._clock, self._monotonic = clock, monotonic
        self._owns_client = client is None
        self.client = client if client is not None else SurfNftClient(clock=clock, monotonic=monotonic)
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
        self.last_budget = None

    def select(self, identity):
        """Only mark priority. Rows and asynchronous completions keep their own IDs."""
        self._selected = identity if isinstance(identity, str) else None

    def is_loading(self, view=None):
        return bool(not self._closed and self._task is not None
                    and not self._task.done() and not self._task.cancelling())

    def offer_hub(self):
        if self._closed or self.is_loading():
            return
        now = self._clock()
        interval = self.FAILURE_BACKOFF if self._failed else self.POLL_SECONDS
        if self._last_offer is not None and now - self._last_offer < interval:
            return
        self._last_offer = now
        self._task = asyncio.create_task(self._cycle())

    async def fetch_and_compute(self):
        self.offer_hub()
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
                        nft_summary={'observed_at': observation}, nft_selected=None,
                        nft_sources=sources, nft_coverage=coverage, as_of=self._clock())
        return project_snapshot(snapshot, selected_id=self._selected)

    def catalogue_summary(self):
        return self.get_snapshot()['nft_summary']

    def _candidates(self):
        return {**discovery_candidates(self.state.get('discovery') or {}),
                **self.state.get('child_candidates', {})}

    def _due(self, identity):
        if identity in self.state.get('progress', {}):
            return True
        attempted = self._inspection_attempts.get(identity)
        if attempted is not None and self._clock() - attempted < self.FAILURE_BACKOFF:
            return False
        evidence = self.state.get('evidence', {}).get(identity)
        if not evidence:
            return True
        stamp = _stamp(evidence.get('checkedAt'))
        ttl = self.CHAIN_TTL if evidence.get('standard') else self.PROBE_TTL
        return stamp is None or self._clock() - stamp >= ttl

    def _pending(self, candidates):
        """Prioritize retained progress and reviewed identities without trusting them."""
        due = [(key, value) for key, value in candidates.items() if self._due(key)]
        due.sort(key=lambda item: (item[0] != self._selected,
                                  item[0] not in self.state.get('progress', {}),
                                  item[0] not in RULES,
                                  _stamp(self.state.get('evidence', {}).get(item[0], {}).get('checkedAt')) or 0))
        return due

    async def _inspect(self, identity, candidate, budget):
        stages = self.state.setdefault('progress', {})
        if identity not in stages and len(stages) >= SurfNftCache.MAX_STAGES:
            return
        result = await self.inspector.advance(candidate, stages.get(identity), budget=budget)
        self._inspection_attempts[identity] = self._clock()
        if result.complete:
            stages.pop(identity, None)
        elif result.progress:
            stages[identity] = result.progress
        if result.evidence is not None:
            self._retain_evidence(identity, result.evidence)
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

    async def _cycle(self):
        budget = Budget(monotonic=self._monotonic)
        self.last_budget = budget
        self.state['last_attempt'] = self._clock()
        self._failed = False
        try:
            # One discovery page always precedes the selection's reserved slice.
            await self._discover(budget, page_limit=1, detail_limit=0, launch_limit=0)
            candidates = self._candidates()
            pending = self._pending(candidates)
            priority = pending[0][0] if pending else None
            if priority is not None:
                with budget.limit(http=6, rpc=64):
                    await self._inspect(priority, candidates[priority], budget)
            # Keep six physical sends for coherent chain progress after backfill.
            with budget.limit(http=max(0, budget.remaining_http - 6), rpc=0):
                await self._discover(budget, page_limit=3, detail_limit=8, launch_limit=2)
            candidates = self._candidates()
            due = [(key, value) for key, value in self._pending(candidates) if key != priority]
            for identity, candidate in due:
                if not budget.can_admit():
                    break
                await self._inspect(identity, candidate, budget)
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
            self.cache.save(self.state, selected_id=self._selected)

    async def wait_pending(self):
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
        await self.wait_pending()
        self.cache.save(self.state, selected_id=self._selected)
        if self._owns_client:
            await self.client.close()
