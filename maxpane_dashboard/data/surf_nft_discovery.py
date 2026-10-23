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
    JOB_ID, NFT_WORDS, NON_BUILD_TEMPLATES, deployment_candidates, job_references, related_records, record_index, timestamp,
)

SEARCHES = ('NFT', '721', '1155', 'non-fungible', 'generative', 'mint', 'collection')
SOURCES = ('launches', 'jobs', 'workflows', 'publications', *(f'search:{q}' for q in SEARCHES), 'sites', 'capabilities')
MAX_FACTS = 2000
MAX_FACT_BYTES = 32 * 1024
HEAD_TTL = 300.
RECONCILE_TTL = 600.
UPDATE_OVERLAP = 300.
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
                            'head_ids': [], 'refresh_ids': [], 'refresh_cursor': None,
                            'last_attempt': None, 'retry_at': 0., 'head_retry_at': 0., 'count': 0,
                            'reconcile_at': None, 'reconciling': False, 'updated_at': None,
                            'scan_max': None, 'scan_started': None, 'scan_valid': True,
                            'delta_since': None, 'delta_cursor': None, 'delta_max': None, 'delta_started': None,
                            'provider_total': None, 'warnings': [], 'recent_ids': []}
                    for source in SOURCES},
        'raw': {'launches': [], 'launchDetails': {}, 'jobDetails': {}, 'workflows': [],
                'publications': [], 'sites': {'sites': []}, 'coverage': {}, 'finishedAt': None},
        'pending_launches': {}, 'pending_jobs': {}, 'queue_turns': {},
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
                   'createdAt', 'updatedAt', 'project', 'delivery', 'result', 'nodes', 'launch', 'site', 'workflow'),
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
    for key in ('project', 'delivery', 'result', 'launch', 'site', 'attestation', 'workflow'):
        if key in out and not isinstance(out[key], dict):
            out[key] = {}
    for key in ('nodes', 'jobs', 'artifacts', 'versions', 'contracts', 'sites'):
        if key in out:
            out[key] = [v for v in out[key] if isinstance(v, dict)] if isinstance(out[key], list) else []
    for parent, key in (('project', 'versions'), ('attestation', 'contracts')):
        if parent in out and key in out[parent]:
            items = out[parent][key]
            out[parent][key] = [v for v in items if isinstance(v, dict)] if isinstance(items, list) else []
    if 'project' in out:
        # A project embeds every previous objective again. Keep the graph/source
        # fields consumed by this reader, not repeated bodies that reject the job.
        project = out['project']
        out['project'] = {k: project[k] for k in ('id', 'head', 'running') if k in project}
        if 'versions' in project:
            out['project']['versions'] = [{k: v[k] for k in ('jobId', 'workflowId', 'baseCommit', 'repoUrl', 'commit') if k in v}
                                          for v in project['versions']]
    if 'workflow' in out:
        out['workflow'] = {k: out['workflow'][k] for k in ('id', 'objective') if k in out['workflow']}
        if parse_job_id(out['workflow'].get('id')) is None:
            out['workflow'] = {}
        elif not isinstance(out['workflow'].get('objective'), str):
            out['workflow']['objective'] = ''
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
        for key in ('head_at', 'last_attempt', 'retry_at', 'head_retry_at', 'reconcile_at', 'updated_at', 'scan_max', 'scan_started'):
            if _number(source.get(key)):
                defaults[key] = source[key]
        defaults['reconciling'] = source.get('reconciling') is True
        defaults['scan_valid'] = (source.get('scan_valid', True) is True
                                  and (source.get('tail_cursor') is None or _number(source.get('scan_started'))))
        if (name in ('jobs', 'workflows') and isinstance(source.get('delta_since'), str)
                and valid_page_cursor(name, source['delta_since'])
                and valid_page_cursor(name, source.get('delta_cursor'))):
            defaults['delta_since'] = source['delta_since']
            defaults['delta_cursor'] = source.get('delta_cursor')
            for key in ('delta_max', 'delta_started'):
                if _number(source.get(key)):
                    defaults[key] = source[key]
        elif source.get('delta_since') is not None or source.get('delta_cursor') is not None:
            defaults['head_retry_at'] = 0.  # Corrupt optional progress cannot strand good facts.
        defaults['tail_cursor'] = source.get('tail_cursor') if type(source.get('tail_cursor')) in (str, int) else None
        if valid_page_cursor('jobs' if name.startswith('search:') else name, source.get('refresh_cursor')):
            defaults['refresh_cursor'] = source.get('refresh_cursor')
        else:
            state['truncated'] = True
        for key in ('head_ids', 'refresh_ids'):
            defaults[key] = [v for v in source.get(key, [])[:100] if isinstance(v, str) and len(v) <= 200] if isinstance(source.get(key), list) else []
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
    turns = value.get('queue_turns')
    if isinstance(turns, dict):
        state['queue_turns'] = {key: turns[key] % 4 for key in ('launches', 'jobs')
                                if type(turns.get(key)) is int and turns[key] >= 0}
    # Upgrade older cursors without rereading the entire already retained launch history.
    launch_source = state['sources']['launches']
    if not launch_source['head_ids'] and launch_source['refresh_cursor'] is None:
        launches = sorted(state['raw']['launches'],
                          key=lambda row: row.get('launchNumber') if type(row.get('launchNumber')) is int else 0,
                          reverse=True)
        launch_source['head_ids'] = [row['id'] for row in launches[:100]]
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
        for key in ('head_at', 'last_attempt', 'reconcile_at', 'updated_at', 'delta_max', 'delta_started', 'scan_max', 'scan_started'):
            if source[key] is not None and not 0 <= source[key] <= now:
                source[key] = None
                if key.startswith('scan_'):
                    source['scan_valid'] = False
                source['terminal'] = False
                _warn(source, 'invalid_observation_clock')
        if source['reconcile_at'] is None:
            source['reconcile_at'] = now
        if timestamp(source['delta_since']) is not None and timestamp(source['delta_since']) > now:
            source.update(delta_since=None, delta_cursor=None, delta_max=None, delta_started=None)
            _warn(source, 'invalid_update_clock')
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


def priority_references(raw):
    """Scheduling hints from explicit source links; never deployment proof."""
    jobs, launches = {}, {}
    def add(target, identity, stamp):
        if parse_job_id(identity):
            target[identity] = max(target.get(identity, 0), stamp)
    for workflow in raw.get('workflows', []):
        if NFT_WORDS.search(workflow.get('objective') or ''):
            for key in ('contractsJobId', 'frontendJobId'):
                add(jobs, workflow.get(key), timestamp(workflow.get('updatedAt')) or 0)
    for publication in raw.get('publications', []):
        if NFT_WORDS.search(publication.get('title') or ''):
            stamp = timestamp(publication.get('updatedAt')) or 0
            for version in publication.get('versions', []):
                add(jobs, version.get('jobId'), stamp)
            for contract in publication.get('contracts', []):
                add(launches, contract.get('id'), stamp)
    for job in raw.get('jobDetails', {}).values():
        if any(NFT_WORDS.search(text or '') for text in
               (job.get('objective'), (job.get('workflow') or {}).get('objective'))):
            add(jobs, job.get('id'), timestamp(job.get('updatedAt')) or 0)
    for job in raw.get('jobDetails', {}).values():
        if job.get('id') in jobs:
            add(launches, (job.get('launch') or {}).get('id'), jobs[job['id']])
    for launch in [*raw.get('launches', []), *raw.get('launchDetails', {}).values()]:
        for job in launch.get('jobs', []):
            if job.get('id') in jobs:
                add(launches, launch.get('id'), jobs[job['id']])
    return jobs, launches


def discovery_candidates(state):
    """Project accepted explicit deployment facts without fetching or clock reads."""
    raw = state.get('raw', {}) if isinstance(state, dict) else {}
    found = deployment_candidates(raw)
    references = job_references(raw.get('jobDetails', {}))
    priority_jobs, priority_launches = priority_references(raw)
    index = record_index(raw, references)
    for identity, candidate in found.items():
        jobs, sites, repos = related_records(raw, candidate['jobIds'], candidate['address'],
                                           candidate['launchIds'], references=references, index=index)
        candidate['jobIds'] = [j['id'] for j in jobs]
        candidate['nft_intent'] = (any(v in priority_launches for v in candidate['launchIds'])
                                   or any(v in priority_jobs for v in candidate['jobIds']))
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

    @staticmethod
    def _queue_order(state, family, priority):
        """Three priority admissions, one FIFO admission; survives cache reload."""
        turns = state.setdefault('queue_turns', {})
        turn = turns.get(family, 0)
        turns[family] = (turn + 1) % 4
        return priority if turn != 3 else lambda _item: 0

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
                previous = raw['launchDetails'].get(row['id'])
                if (previous and isinstance(row.get('updatedAt'), str)
                        and (not isinstance(previous.get('updatedAt'), str)
                             or row['updatedAt'] > previous['updatedAt'])):
                    # A rich but older detail must not shadow fresh deployment artifacts.
                    raw['launchDetails'].pop(row['id'])
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

    def _accept_page(self, source, page, *, head, refreshing=False):
        # An observed head never resets a cursor already traversing history.
        first = source['head_at'] is None
        if not head and not refreshing and page.rows and all(r['id'] in source['recent_ids'] for r in page.rows):
            _warn(source, 'repeated_page')
            return False
        if page.provider_total is not None:
            if source['provider_total'] is not None and page.provider_total != source['provider_total']:
                _warn(source, 'provider_total_changed')
            source['provider_total'] = page.provider_total
        if page.warning:
            _warn(source, page.warning)
        if not refreshing and (not head or first):
            source['count'] += len([r for r in page.rows if r['id'] not in source['recent_ids']])
            source['tail_cursor'] = page.next_cursor
            source['terminal'] = page.terminal
            if page.terminal and page.provider_total is not None and source['count'] < page.provider_total:
                _warn(source, 'publication_count_gap')
            source['recent_ids'] = (source['recent_ids'] + [r['id'] for r in page.rows])[-200:]
        if head:
            source['head_at'] = page.observed_at
        if head or refreshing:
            ids = [r['id'] for r in page.rows]
            if head:
                source['refresh_ids'] = ids
            overlap = bool(set(ids) & set(source['head_ids']))
            if not first and not overlap and not page.terminal:
                source['refresh_cursor'] = page.next_cursor
            else:
                source['refresh_cursor'] = None
                source['head_ids'] = source['refresh_ids']
                source['refresh_ids'] = []
        return True

    @staticmethod
    def _scan_page(source, page, now):
        """Only a clean, complete scan certifies an update baseline."""
        if source['scan_started'] is None:
            source['scan_started'] = now
        stamps = [timestamp(row.get('updatedAt')) for row in page.rows]
        if page.warning or any(stamp is None or stamp > now for stamp in stamps):
            source['scan_valid'] = False
        elif stamps:
            source['scan_max'] = max([source['scan_max'] or 0, *stamps])
        if page.terminal and source['scan_valid'] and not source['warnings'] and source['scan_max'] is not None:
            source['updated_at'] = max(source['updated_at'] or 0,
                                      min(source['scan_max'], source['scan_started']))

    @staticmethod
    def _checkpoint(state, checkpoint):
        if checkpoint is not None:
            # Do not certify coverage until all admitted work has finished.
            state['raw']['coverage'] = {**state['raw'].get('coverage', {}), 'complete': False}
            checkpoint(state)

    async def advance(self, state=None, *, budget, page_limit=4, detail_limit=8, launch_limit=4, checkpoint=None):
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
            if (name not in ('sites', 'capabilities') and not source['reconciling'] and source['terminal']
                    and (source['delta_since'] is None or source['head_retry_at'] > 0)
                    and now - source['reconcile_at'] >= RECONCILE_TTL):
                # Revisit older records even on sources without an update API.
                # Retain accepted facts; only a validated terminal page certifies this scan.
                source.update(reconciling=True, reconcile_at=now, terminal=False,
                              tail_cursor=None, count=0, recent_ids=[], refresh_cursor=None,
                              scan_started=now, scan_max=None, scan_valid=True,
                              delta_since=None, delta_cursor=None, delta_max=None, delta_started=None)
            if (name in ('jobs', 'workflows') and not source['reconciling'] and source['updated_at'] is not None
                    and source['delta_since'] is None and now - (source['head_at'] or 0) >= HEAD_TTL):
                source['delta_since'] = datetime.fromtimestamp(max(0, source['updated_at'] - UPDATE_OVERLAP),
                    timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                source['delta_max'] = source['updated_at']
                source['delta_started'] = now
            delta = source['delta_since'] is not None
            refreshing = source['refresh_cursor'] is not None
            head = not delta and not refreshing and (source['head_at'] is None or now - source['head_at'] >= HEAD_TTL)
            # A reconciliation's first page doubles as its head observation. Later
            # head reads have their own retry lane and never rewind history.
            if source['reconciling'] and source['tail_cursor'] is None:
                head = False
            retry_key = 'head_retry_at' if delta or head or refreshing else 'retry_at'
            if source[retry_key] > now:
                continue
            history_page = not delta and not refreshing and (not head or source['head_at'] is None)
            first_history = history_page and source['tail_cursor'] is None
            if not delta and not head and not refreshing and source['terminal']:
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
                    self._checkpoint(state, checkpoint)
                    continue
                page = await self.client.page('jobs' if name.startswith('search:') else name,
                                              cursor=source['delta_cursor'] if delta else None if head else source['refresh_cursor'] if refreshing else source['tail_cursor'],
                                              query=name.partition(':')[2] if name.startswith('search:') else None,
                                              budget=budget, **({'since': source['delta_since']} if delta else {}))
                if delta:
                    stamps = [timestamp(row.get('updatedAt')) for row in page.rows]
                    if (page.warning or any(stamp is None or stamp > self.clock() or stamp < timestamp(source['delta_since']) for stamp in stamps)
                            or not page.terminal and page.next_cursor == source['delta_cursor']):
                        raise SourceUnavailable('uncertified update page')
                    source['delta_max'] = max([source['delta_max'] or 0, *stamps])
                    source['delta_cursor'] = page.next_cursor
                    if page.terminal:
                        source.update(updated_at=min(source['delta_max'], source['delta_started'] or now),
                                      head_at=page.observed_at, delta_since=None, delta_cursor=None,
                                      delta_max=None, delta_started=None)
                    accepted = True
                else:
                    accepted = self._accept_page(source, page, head=head, refreshing=refreshing)
                    if accepted and history_page:
                        self._scan_page(source, page, now)
                        if first_history:
                            source['head_at'] = page.observed_at
                        if source['reconciling'] and page.terminal:
                            source['reconciling'] = False
                if accepted:
                    source[retry_key] = 0.
                    self._ingest(state, name, page.rows, page.observed_at)
                    state['observed_at'] = page.observed_at
                    self._checkpoint(state, checkpoint)
                else:
                    source[retry_key] = self.clock() + RETRY_TTL
            except BudgetExhausted:
                state['rotation'] = index
                break
            except (SourceUnavailable, ValueError):
                source[retry_key] = self.clock() + RETRY_TTL
                # Failed refresh never destroys previously observed tail completeness.
        priority_jobs, priority_launches = priority_references(state['raw'])
        launch_numbers = {row['id']: row.get('launchNumber') for row in state['raw']['launches']}
        launches = [(identity, p) for identity, p in state['pending_launches'].items()
                    if p['retry_at'] <= self.clock()]
        launch_priority = lambda item: (item[0] not in priority_launches,
            item[0] in state['raw']['launchDetails'], -priority_launches.get(item[0], 0),
            -(launch_numbers[item[0]] if type(launch_numbers.get(item[0])) is int else 0))
        for _ in range(min(launch_limit, 4, len(launches))):
            if not budget.can_admit():
                break
            item = min(launches, key=self._queue_order(state, 'launches', launch_priority))
            launches.remove(item)
            identity, pending = item
            state['pending_launches'][identity] = state['pending_launches'].pop(identity)
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
                self._checkpoint(state, checkpoint)
            else:
                state['truncated'] = True
                pending['retry_at'] = self.clock() + RETRY_TTL
        admitted = 0
        # Newly discovered project continuations can use the remaining admitted slots.
        tried = set()
        while admitted < min(detail_limit, 8):
            if not self.client.can_read_shared_job():
                break
            pending_jobs = [(identity, p) for identity, p in state['pending_jobs'].items()
                            if identity not in tried and p['retry_at'] <= self.clock()]
            if not pending_jobs:
                break
            try:
                budget.reserve_shared_job()
            except BudgetExhausted:
                break
            priority = self._queue_order(state, 'jobs', lambda item:
                (item[0] not in priority_jobs, -priority_jobs.get(item[0], 0)))
            identity, pending = min(pending_jobs, key=priority)
            state['pending_jobs'][identity] = state['pending_jobs'].pop(identity)
            tried.add(identity)
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
            self._queue(state, fact.get('launch', {}).get('id'), launch=True)
            for version in fact.get('project', {}).get('versions', []):
                self._queue(state, version.get('jobId'))
            for linked in JOB_ID.findall(fact.get('objective') or ''):
                self._queue(state, linked)
            self._checkpoint(state, checkpoint)
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
        coverage = {'complete': (all(v['terminal'] and v['refresh_cursor'] is None and v['delta_since'] is None and not v['warnings'] for k, v in state['sources'].items()
                                     if k not in ('sites', 'capabilities'))
                                 and not state['pending_launches'] and not state['pending_jobs'] and not state['truncated']),
                    'truncated': state['truncated'], 'observed': state['observed_at'] is not None,
                    'sources': deepcopy(state['sources']),
                    'pending_launches': len(state['pending_launches']), 'pending_jobs': len(state['pending_jobs'])}
        state['raw']['coverage'] = deepcopy(coverage)
        if state['observed_at'] is not None:
            state['raw']['finishedAt'] = datetime.fromtimestamp(state['observed_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
        return DiscoveryResult(state, discovery_candidates(state), state['raw']['jobDetails'], coverage)
