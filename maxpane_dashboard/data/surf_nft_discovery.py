"""Incremental public Swarm discovery with separate head and history progress.

The persisted raw envelope is scanner-compatible but contains only bounded facts,
not a second full-job cache. Network ownership stays with the two injected clients.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import time

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data.surf_nft_client import BudgetExhausted, SourceUnavailable, valid_page_cursor
from maxpane_dashboard.data.surf_nft_rules.catalog import (
    JOB_ID, NFT_WORDS, NON_BUILD_TEMPLATES, deployment_candidates, related_records,
)

SEARCHES = ('NFT', '721', '1155', 'non-fungible', 'generative', 'mint', 'collection')
SOURCES = ('launches', 'jobs', 'workflows', 'publications', *(f'search:{q}' for q in SEARCHES), 'sites', 'capabilities')
MAX_FACTS = 2000
MAX_FACT_BYTES = 32 * 1024
HEAD_TTL = 300.
DETAIL_TTL = 600.
RETRY_TTL = 120.


@dataclass(frozen=True)
class DiscoveryResult:
    state: dict
    candidates: dict
    job_facts: dict
    coverage: dict


def empty_discovery_state():
    return {
        'version': 1, 'rotation': 0, 'observed_at': None, 'truncated': False,
        'sources': {source: {'head_at': None, 'tail_cursor': None, 'terminal': False,
                            'last_attempt': None, 'retry_at': 0., 'count': 0,
                            'provider_total': None, 'warnings': [], 'recent_ids': []}
                    for source in SOURCES},
        'raw': {'launches': [], 'launchDetails': {}, 'jobDetails': {}, 'workflows': [],
                'publications': [], 'sites': {'sites': []}, 'coverage': {}, 'finishedAt': None},
        'pending_launches': {}, 'pending_jobs': {},
    }


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _clean(value, depth=0):
    """Bound structured evidence; caller records every lossy extraction."""
    if depth > 8:
        return None
    if isinstance(value, str):
        return value[:16384]
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list):
        return [_clean(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {key: _clean(item, depth + 1) for key, item in list(value.items())[:100]
                if isinstance(key, str) and len(key) < 100}
    return None


_FIELDS = {
    'launches': ('id', 'launchNumber', 'chainId', 'status', 'artifacts', 'jobs', 'sourceRepoUrl',
                 'sourceCommit', 'attestation', 'createdAt', 'updatedAt', 'deployedAt', 'title'),
    'jobDetails': ('id', 'objective', 'title', 'state', 'status', 'template', 'chainId',
                   'createdAt', 'updatedAt', 'project', 'delivery', 'result', 'nodes', 'launch', 'site'),
    'workflows': ('id', 'objective', 'status', 'state', 'contractsJobId', 'frontendJobId',
                  'createdAt', 'updatedAt', 'projectId', 'chainId'),
    'publications': ('id', 'title', 'versions', 'contracts', 'sites', 'createdAt', 'updatedAt', 'code'),
    'sites': ('id', 'url', 'jobId', 'status', 'supersededBy', 'takenDownAt', 'takenDownReason',
              'createdAt', 'updatedAt', 'cid', 'name'),
}


def _compact(row, kind, observed_at=None, revision=None):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or len(row['id']) > 200:
        return None
    kind = 'launches' if kind == 'launchDetails' else kind
    fields = _FIELDS[kind]
    selected = {k: row[k] for k in fields if k in row}
    if kind == 'publications' and 'code' in selected:
        selected['code'] = bool(selected['code'])  # Presence is the only discovery fact.
    out = _clean(selected)
    # Wrong-shaped nested evidence is rejected before entering shared interpreters.
    for key in ('project', 'delivery', 'result', 'launch', 'site', 'attestation'):
        if key in out and not isinstance(out[key], dict):
            out[key] = {}
    for key in ('nodes', 'jobs', 'artifacts', 'versions', 'contracts', 'sites'):
        if key in out:
            out[key] = [v for v in out[key] if isinstance(v, dict)] if isinstance(out[key], list) else []
    for parent, key in (('project', 'versions'), ('attestation', 'contracts')):
        if parent in out and key in out[parent]:
            items = out[parent][key]
            out[parent][key] = [v for v in items if isinstance(v, dict)] if isinstance(items, list) else []
    if 'id' in out.get('project', {}) and not isinstance(out['project']['id'], str):
        out['project'].pop('id')
    if 'manifest' in out.get('attestation', {}):
        manifest = out['attestation']['manifest']
        if not isinstance(manifest, dict):
            out['attestation']['manifest'] = {}
        elif 'notes' in manifest and not isinstance(manifest['notes'], str):
            manifest['notes'] = ''
    for key in ('objective', 'title', 'state', 'status', 'template'):
        if key in out and not isinstance(out[key], str):
            out[key] = ''
    if 'chainId' in out and type(out['chainId']) is not int:
        out['chainId'] = None
    if 'chainId' in out.get('launch', {}) and type(out['launch']['chainId']) is not int:
        out['launch']['chainId'] = None
    for key in ('contractsJobId', 'frontendJobId'):
        if key in out and parse_job_id(out[key]) is None:
            out[key] = None
    versions = out.get('versions', []) + out.get('project', {}).get('versions', [])
    for version in versions:
        if 'jobId' in version and parse_job_id(version['jobId']) is None:
            version.pop('jobId')
        for key in ('baseCommit', 'repoUrl', 'commit'):
            if key in version and not isinstance(version[key], str):
                version[key] = None
        if 'site' in version and not isinstance(version['site'], dict):
            version['site'] = {}
    for contract in out.get('contracts', []):
        if 'id' in contract and parse_job_id(contract['id']) is None:
            contract.pop('id')
    sites = out.get('sites', []) + [out.get('site', {})] + [v.get('site', {}) for v in versions]
    if kind == 'sites':
        sites.append(out)
    for site in sites:
        for key in ('id', 'url', 'status', 'updatedAt', 'jobId'):
            if key in site and not isinstance(site[key], str):
                site[key] = None
    if 'delivery' in out.get('result', {}) and not isinstance(out['result']['delivery'], dict):
        out['result']['delivery'] = {}
    if kind == 'launches' and 'jobs' in out:
        out['jobs'] = [j for j in out.get('jobs', []) if parse_job_id(j.get('id'))]
    if out != selected or row.get('_truncated'):
        out['_truncated'] = True
    observed = observed_at if observed_at is not None else row.get('_observed_at')
    out['_observed_at'] = observed if _number(observed) else None
    source_revision = revision if revision is not None else row.get('_revision')
    out['_revision'] = source_revision if isinstance(source_revision, str) else None
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_FACT_BYTES:
        # Do not publish a partial objective as complete semantic evidence.
        return None
    return out


def _upsert(rows, row):
    for index, old in enumerate(rows):
        if old['id'] == row['id']:
            rows[index] = row
            return
    rows.append(row)


def _bound(state):
    raw = state['raw']
    remaining = MAX_FACTS
    # Favor deployed identities and full linked facts over supplementary publications.
    for key in ('launchDetails', 'jobDetails', 'launches', 'workflows', 'publications', 'sites'):
        values = raw[key]['sites'] if key == 'sites' else raw[key]
        is_map = isinstance(values, dict)
        rows = sorted(list(values.values()) if is_map else values,
                      key=lambda row: row.get('_observed_at') or 0., reverse=True)
        keep = rows[:remaining]
        if len(keep) != len(rows):
            state['truncated'] = True
        remaining -= len(keep)
        if key == 'sites':
            raw[key] = {'sites': keep}
        else:
            raw[key] = {v['id']: v for v in keep} if is_map else keep
    for queue in ('pending_launches', 'pending_jobs'):
        if len(state[queue]) > MAX_FACTS:
            state[queue] = dict(list(state[queue].items())[:MAX_FACTS])
            state['truncated'] = True


def _restore(value):
    state = empty_discovery_state()
    if not isinstance(value, dict) or value.get('version') != 1:
        return state
    state['truncated'] = value.get('truncated') is True
    state['rotation'] = value.get('rotation', 0) % len(SOURCES) if type(value.get('rotation')) is int else 0
    state['observed_at'] = value.get('observed_at') if _number(value.get('observed_at')) else None
    for name, defaults in state['sources'].items():
        source = value.get('sources', {}).get(name, {}) if isinstance(value.get('sources'), dict) else {}
        if not isinstance(source, dict):
            continue
        if not valid_page_cursor('jobs' if name.startswith('search:') else name, source.get('tail_cursor')):
            state['truncated'] = True
            continue  # Restart just this source, retaining all other facts/cursors.
        for key in ('head_at', 'last_attempt', 'retry_at'):
            if _number(source.get(key)):
                defaults[key] = source[key]
        defaults['tail_cursor'] = source.get('tail_cursor') if type(source.get('tail_cursor')) in (str, int) else None
        defaults['terminal'] = source.get('terminal') is True
        for key in ('count', 'provider_total'):
            if type(source.get(key)) is int and source[key] >= 0:
                defaults[key] = source[key]
        defaults['warnings'] = [s[:100] for s in source.get('warnings', [])[:16] if isinstance(s, str)] if isinstance(source.get('warnings'), list) else []
        defaults['recent_ids'] = [s[:200] for s in source.get('recent_ids', [])[-200:] if isinstance(s, str)] if isinstance(source.get('recent_ids'), list) else []
    raw = value.get('raw', {})
    if isinstance(raw, dict):
        for kind in ('launches', 'launchDetails', 'jobDetails', 'workflows', 'publications', 'sites'):
            rows = raw.get(kind, [])
            if kind == 'sites':
                rows = rows.get('sites', []) if isinstance(rows, dict) else []
            elif kind in ('launchDetails', 'jobDetails'):
                rows = list(rows.values()) if isinstance(rows, dict) else []
            if not isinstance(rows, list):
                continue
            for row in rows[:MAX_FACTS + 1]:
                compact = _compact(row, kind)
                if compact is None:
                    state['truncated'] = True
                    continue
                if compact.get('_truncated'):
                    state['truncated'] = True
                target = state['raw'][kind]
                if kind in ('launchDetails', 'jobDetails'):
                    target[compact['id']] = compact
                elif kind == 'sites':
                    _upsert(target['sites'], compact)
                else:
                    _upsert(target, compact)
            if len(rows) > MAX_FACTS:
                state['truncated'] = True
    for key in ('pending_launches', 'pending_jobs'):
        values = value.get(key, {})
        if isinstance(values, dict):
            for identity, pending in list(values.items())[:MAX_FACTS]:
                if parse_job_id(identity) and isinstance(pending, dict):
                    state[key][identity] = {'retry_at': pending.get('retry_at') if _number(pending.get('retry_at')) else 0.,
                                            'revision': pending.get('revision') if isinstance(pending.get('revision'), str) else None}
    _bound(state)
    return state


def validate_discovery_state(value, now):
    """Keep unrelated valid facts when one persisted observation is corrupt."""
    state = _restore(value)
    if not _number(now):
        raise ValueError('finite validation clock required')
    if state['observed_at'] is not None and not 0 <= state['observed_at'] <= now:
        state['observed_at'] = None
        state['truncated'] = True
    for source in state['sources'].values():
        for key in ('head_at', 'last_attempt'):
            if source[key] is not None and not 0 <= source[key] <= now:
                source[key] = None
                source['terminal'] = False
                _warn(source, 'invalid_observation_clock')
    raw = state['raw']
    for family in ('launches', 'launchDetails', 'jobDetails', 'workflows', 'publications', 'sites'):
        values = raw[family]['sites'] if family == 'sites' else raw[family]
        rows = list(values.values()) if isinstance(values, dict) else values
        valid = [r for r in rows if r['_observed_at'] is None or 0 <= r['_observed_at'] <= now]
        if len(valid) != len(rows):
            state['truncated'] = True
        if family == 'sites':
            raw[family] = {'sites': valid}
        elif isinstance(values, dict):
            raw[family] = {r['id']: r for r in valid}
        else:
            raw[family] = valid
    # Projection metadata is retained, with incomplete coverage after sanitation.
    previous_raw = value.get('raw', {}) if isinstance(value, dict) else {}
    if isinstance(previous_raw, dict) and isinstance(previous_raw.get('coverage'), dict):
        raw['coverage'] = _clean(previous_raw['coverage'])
    if state['truncated']:
        raw['coverage']['complete'] = False
        raw['coverage']['truncated'] = True
    if state['observed_at'] is not None:
        raw['finishedAt'] = datetime.fromtimestamp(state['observed_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
    return state


def discovery_candidates(state):
    """Project accepted explicit deployment facts without fetching or clock reads."""
    raw = state.get('raw', {}) if isinstance(state, dict) else {}
    found = deployment_candidates(raw)
    for identity, candidate in found.items():
        jobs, sites, repos = related_records(raw, candidate['jobIds'], candidate['address'], candidate['launchIds'])
        candidate['jobIds'] = [j['id'] for j in jobs]
        candidate.update(id=identity, chain_id=candidate['chainId'], contract=candidate['address'],
                         tx_hash=candidate['artifact'].get('txHash'), block_number=candidate['artifact'].get('blockNumber'),
                         provenance={'launch_ids': list(candidate['launchIds']), 'job_ids': list(candidate['jobIds']),
                                     'observed_at': candidate['launch'].get('_observed_at')}, sites=sites, repositories=repos)
    return found


def _warn(source, message):
    if message not in source['warnings']:
        source['warnings'] = (source['warnings'] + [message])[-16:]


class SurfNftDiscovery:
    def __init__(self, *, client, swarm, clock=time.time, monotonic=time.monotonic):
        self.client, self.swarm = client, swarm
        self.clock, self.monotonic = clock, monotonic

    def _queue(self, state, identity, *, launch=False, revision=None):
        if parse_job_id(identity) is None:
            return
        facts = state['raw']['launchDetails' if launch else 'jobDetails']
        known = facts.get(identity)
        if known and (revision is None or revision == known.get('_revision')):
            if _number(known.get('_observed_at')) and self.clock() - known['_observed_at'] < DETAIL_TTL:
                return
        queue = state['pending_launches' if launch else 'pending_jobs']
        queue.setdefault(identity, {'retry_at': 0., 'revision': revision})
        if isinstance(revision, str):
            queue[identity]['revision'] = revision

    def _ingest(self, state, source, rows, observed_at):
        raw = state['raw']
        if source == 'launches':
            for row in rows:
                if type(row.get('chainId')) is not int or row['chainId'] not in (1, 4663):
                    continue
                fact = _compact(row, 'launches', observed_at, row.get('updatedAt'))
                if fact is None:
                    state['truncated'] = True
                    continue
                _upsert(raw['launches'], fact)
                self._queue(state, row['id'], launch=True, revision=row.get('updatedAt'))
        elif source == 'jobs' or source.startswith('search:'):
            query = source.partition(':')[2]
            for row in rows:
                template = row.get('template')
                if template is not None and not isinstance(template, str):
                    state['truncated'] = True
                    continue
                text = row.get('objective') or ''
                relevant = isinstance(text, str) and NFT_WORDS.search(text)
                if source.startswith('search:') and query not in ('mint', 'collection'):
                    relevant = True  # Search server reads full text, previews can omit match.
                if template not in NON_BUILD_TEMPLATES and relevant:
                    self._queue(state, row['id'], revision=row.get('updatedAt'))
        elif source in ('workflows', 'publications', 'sites'):
            for row in rows:
                fact = _compact(row, source, observed_at, row.get('updatedAt'))
                if fact is None:
                    state['truncated'] = True
                    continue
                _upsert(raw[source]['sites'] if source == 'sites' else raw[source], fact)
                if source == 'workflows' and NFT_WORDS.search(fact.get('objective') or ''):
                    for key in ('contractsJobId', 'frontendJobId'):
                        self._queue(state, fact.get(key))
                if source == 'publications' and NFT_WORDS.search(fact.get('title') or ''):
                    if fact.get('code') or fact.get('contracts') or fact.get('sites'):
                        for version in fact.get('versions', []):
                            self._queue(state, version.get('jobId'))
        if any(isinstance(row, dict) and row.get('_truncated') for rows in (raw['launches'], raw['workflows'], raw['publications'], raw['sites']['sites']) for row in rows):
            state['truncated'] = True

    def _accept_page(self, source, page, *, head):
        # An observed head never resets a cursor already traversing history.
        first = source['head_at'] is None
        if not head and page.rows and all(r['id'] in source['recent_ids'] for r in page.rows):
            _warn(source, 'repeated_page')
            return False
        if page.provider_total is not None:
            if source['provider_total'] is not None and page.provider_total != source['provider_total']:
                _warn(source, 'provider_total_changed')
            source['provider_total'] = page.provider_total
        if page.warning:
            _warn(source, page.warning)
        if not head or first:
            source['count'] += len([r for r in page.rows if r['id'] not in source['recent_ids']])
            source['tail_cursor'] = page.next_cursor
            source['terminal'] = page.terminal
            if page.terminal and page.provider_total is not None and source['count'] < page.provider_total:
                _warn(source, 'publication_count_gap')
            source['recent_ids'] = (source['recent_ids'] + [r['id'] for r in page.rows])[-200:]
        if head:
            source['head_at'] = page.observed_at
        return True

    async def advance(self, state=None, *, budget, page_limit=4, detail_limit=8, launch_limit=4):
        if any(type(v) is not int or v < 0 for v in (page_limit, detail_limit, launch_limit)):
            raise ValueError('invalid discovery work limit')
        state = validate_discovery_state(state, self.clock())
        pages = 0
        checked = 0
        while pages < min(page_limit, 4) and checked < len(SOURCES):
            index = state['rotation']
            name = SOURCES[index]
            state['rotation'] = (index + 1) % len(SOURCES)
            checked += 1
            source = state['sources'][name]
            now = self.clock()
            if source['retry_at'] > now:
                continue
            head = source['head_at'] is None or now - source['head_at'] >= HEAD_TTL
            if not head and source['terminal']:
                continue
            if not budget.can_admit():
                state['rotation'] = index
                break
            pages += 1
            source['last_attempt'] = now
            try:
                if name == 'capabilities':
                    read = await self.client.detail('capabilities', None, budget=budget)
                    source.update(head_at=read.observed_at, terminal=True)
                    state['observed_at'] = read.observed_at
                    continue
                page = await self.client.page('jobs' if name.startswith('search:') else name,
                                              cursor=None if head else source['tail_cursor'],
                                              query=name.partition(':')[2] if name.startswith('search:') else None,
                                              budget=budget)
                if self._accept_page(source, page, head=head):
                    self._ingest(state, name, page.rows, page.observed_at)
                    state['observed_at'] = page.observed_at
                else:
                    source['retry_at'] = self.clock() + RETRY_TTL
            except BudgetExhausted:
                state['rotation'] = index
                break
            except (SourceUnavailable, ValueError):
                source['retry_at'] = self.clock() + RETRY_TTL
                # Failed refresh never destroys previously observed tail completeness.
        launches = [(identity, p) for identity, p in state['pending_launches'].items()
                    if p['retry_at'] <= self.clock()][:min(launch_limit, 4)]
        for identity, pending in launches:
            try:
                read = await self.client.detail('launches', identity, budget=budget)
            except BudgetExhausted:
                break
            except (SourceUnavailable, ValueError):
                pending['retry_at'] = self.clock() + RETRY_TTL
                continue
            fact = _compact(read.payload, 'launchDetails', read.observed_at, read.payload.get('updatedAt'))
            if fact is not None and type(fact.get('chainId')) is int and fact['chainId'] in (1, 4663):
                state['raw']['launchDetails'][identity] = fact
                for job in fact.get('jobs', []):
                    self._queue(state, job.get('id'), revision=job.get('updatedAt'))
                state['pending_launches'].pop(identity)
            else:
                state['truncated'] = True
                pending['retry_at'] = self.clock() + RETRY_TTL
        admitted = 0
        # Newly discovered project continuations can use the remaining admitted slots.
        tried = set()
        while admitted < min(detail_limit, 8):
            if not self.client.can_read_shared_job():
                break
            next_job = next(((identity, p) for identity, p in state['pending_jobs'].items()
                             if identity not in tried and p['retry_at'] <= self.clock()), None)
            if next_job is None:
                break
            identity, pending = next_job
            tried.add(identity)
            try:
                budget.reserve_shared_job()
            except BudgetExhausted:
                break
            admitted += 1
            try:
                # Existing shared memo owns flight cancellation; do not shield this waiter.
                async with asyncio.timeout(budget.remaining_seconds):
                    revision = pending.get('revision')
                    known_revision = self.swarm.known_job_revision(identity)
                    fresh_after = self.monotonic() if revision and known_revision and revision != known_revision else None
                    read = await self.swarm.read_job_detail(identity, fresh_after=fresh_after)
            except TimeoutError:
                break
            if read.from_cache:
                budget.refund_shared_job()
            if not isinstance(read.payload, dict) or read.payload.get('id') != identity or not _number(read.observed_at):
                pending['retry_at'] = self.clock() + RETRY_TTL
                continue
            fact = _compact(read.payload, 'jobDetails', read.observed_at, read.revision)
            if fact is None:
                state['truncated'] = True
                pending['retry_at'] = self.clock() + RETRY_TTL
                continue
            if fact.get('_truncated'):
                state['truncated'] = True
            state['raw']['jobDetails'][identity] = fact
            state['pending_jobs'].pop(identity)
            for version in fact.get('project', {}).get('versions', []):
                self._queue(state, version.get('jobId'))
            for linked in JOB_ID.findall(fact.get('objective') or ''):
                self._queue(state, linked)
        # Workflow/publication links discovered earlier also join newly loaded jobs.
        linked_jobs = set(state['raw']['jobDetails'])
        for workflow in state['raw']['workflows']:
            linked = {workflow.get('contractsJobId'), workflow.get('frontendJobId')} - {None}
            if linked & linked_jobs:
                for identity in linked:
                    self._queue(state, identity)
        for publication in state['raw']['publications']:
            linked = {v.get('jobId') for v in publication.get('versions', [])} - {None}
            if linked & linked_jobs or any(c.get('id') in state['raw']['launchDetails'] for c in publication.get('contracts', [])):
                for identity in linked:
                    self._queue(state, identity)
        _bound(state)
        coverage = {'complete': (all(v['terminal'] and not v['warnings'] for k, v in state['sources'].items()
                                     if k not in ('sites', 'capabilities'))
                                 and not state['pending_launches'] and not state['pending_jobs'] and not state['truncated']),
                    'truncated': state['truncated'], 'observed': state['observed_at'] is not None,
                    'sources': deepcopy(state['sources']),
                    'pending_launches': len(state['pending_launches']), 'pending_jobs': len(state['pending_jobs'])}
        state['raw']['coverage'] = deepcopy(coverage)
        if state['observed_at'] is not None:
            state['raw']['finishedAt'] = datetime.fromtimestamp(state['observed_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
        return DiscoveryResult(state, discovery_candidates(state), state['raw']['jobDetails'], coverage)
