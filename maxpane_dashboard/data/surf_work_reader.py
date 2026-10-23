"""Detached current-work discovery and bounded, direct active-project reads."""
import asyncio
import logging

from maxpane_dashboard.data import surf_work as work
from maxpane_dashboard.data.surf_cache import SLOT_SURF_WORK, TIER_SURF_WORK

logger = logging.getLogger(__name__)


class WorkReader:
    def __init__(self, client, cache, *, clock):
        self.client, self.cache, self.clock = client, cache, clock
        self.task = None
        self._workflow_before = None
        self._workflow_rows = {}
        self._workflow_started = None

    def offer(self):
        if self.task is not None and not self.task.done():
            if self.task.cancelling():
                self.task = asyncio.create_task(self._read_after_cancel(self.task))
            return self.task
        if not self.cache.is_due(TIER_SURF_WORK, self.clock()):
            return None
        self.task = asyncio.create_task(self._read())
        return self.task

    async def _read_after_cancel(self, prior):
        # Screen suspend may cancel just before the view is reopened.
        await asyncio.gather(prior, return_exceptions=True)
        await self._read()

    def cancel(self):
        if self.task is not None and not self.task.done():
            self.task.cancel()

    async def close(self):
        self.cancel()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)

    def project(self):
        entry = self.cache.get_last_good(SLOT_SURF_WORK)
        return work.project(getattr(entry, 'payload', None), now=self.clock(),
                            failed=self.cache.last_failure_ts(TIER_SURF_WORK) is not None)

    async def _fetch(self, method, *args, **kwargs):
        try:
            result = await getattr(self.client, method)(*args, **kwargs)
            raw = result.payload if method == 'read_job_detail' else result
        except Exception:
            return None
        if isinstance(raw, dict) and raw.get('error') == 'busy':
            raise ValueError('swarm busy')
        return result

    async def _workflow_catalogue(self, started):
        if self._workflow_before is None:
            self._workflow_rows = {}
            self._workflow_started = started
        for _ in range(work.WORKFLOW_PAGES_PER_READ):
            kwargs = {'before': self._workflow_before} if self._workflow_before else {}
            page = await self._fetch('fetch_workflows', limit=work.PAGE_LIMIT, **kwargs)
            if not isinstance(page, list):
                if not self._workflow_rows: raise ValueError('workflows unavailable')
                break
            decoded, _ = work._page(page, work._workflow, self.clock())
            if page and not decoded and not self._workflow_rows:
                raise ValueError('nonempty workflow page has no valid rows')
            valid = {row['id'] for row in decoded}
            duplicate = any(identity in self._workflow_rows for identity in valid)
            if duplicate:
                self._workflow_before = None
                break
            self._workflow_rows.update((raw['id'], raw) for raw in page
                                       if isinstance(raw, dict) and raw.get('id') in valid)
            if len(decoded) != len(page):
                self._workflow_before = None
                break
            if len(page) < work.PAGE_LIMIT:
                self._workflow_before = None
                return list(self._workflow_rows.values()), True, self._workflow_started
            cursor = page[-1].get('createdAt')
            stamp = work._stamp(work._ts(cursor), self.clock())
            if (not isinstance(cursor, str) or not cursor.endswith('Z') or stamp is None
                    or self._workflow_before is not None and stamp >= work._ts(self._workflow_before)
                    or len(self._workflow_rows) >= work.WORKFLOW_LIMIT):
                self._workflow_before = None
                break
            self._workflow_before = cursor
        return list(self._workflow_rows.values()), False, self._workflow_started

    async def _collect(self, started):
        jobs = await self._fetch('fetch_jobs', limit=work.PAGE_LIMIT)
        if not isinstance(jobs, list): raise ValueError('jobs unavailable')
        workflows, workflow_complete, workflow_started = await self._workflow_catalogue(started)
        rows, _ = work._page(jobs, work._job, self.clock())
        flows, _ = work._page(workflows, work._workflow, self.clock(), work.WORKFLOW_LIMIT)
        if (jobs and not rows) or (workflows and not flows):
            raise ValueError('nonempty work page has no valid rows')
        partial = len(rows) != len(jobs) or len(flows) != len(workflows) or not workflow_complete
        discovery_ok = len(rows) == len(jobs)
        first_page = [raw for raw in jobs[:work.PAGE_LIMIT] if isinstance(raw, dict) and raw.get('id') in {r['id'] for r in rows}]
        cutoff = started - work.HISTORY_SECONDS
        jobs = [raw for raw in first_page if raw['state'] not in work.TERMINAL or
                (work._stamp(work._ts(raw.get('createdAt')), self.clock()) or started) >= cutoff]
        overview = await self._fetch('fetch_overview')
        counts = overview.get('counts') if isinstance(overview, dict) else None
        states = counts.get('jobStates') if isinstance(counts, dict) else None
        hint = work.integer(states.get('executing')) if isinstance(states, dict) else None
        total = work.integer(counts.get('jobs')) if isinstance(counts, dict) else None
        state_counts = {state: work.integer(value) for state, value in states.items()} if isinstance(states, dict) else {}
        open_hint = None
        if (total is not None and state_counts and all(isinstance(state, str) and state and value is not None
                for state, value in state_counts.items()) and sum(state_counts.values()) == total):
            open_hint = sum(value for state, value in state_counts.items() if state not in work.TERMINAL)
        discovery_mono = self.client._monotonic()
        details, detail_bounds, detail_times, expected = {}, {}, {}, set()
        required_reads = 0

        async def read_job(identity, *, required=True, fresh_after=None):
            nonlocal required_reads, partial
            expected.add(identity)
            if identity in details and (fresh_after is None or
                    detail_bounds.get(identity) is not None and detail_bounds[identity] >= fresh_after):
                return details[identity]
            if required and required_reads >= work.CONTEXT_DETAIL_LIMIT:
                partial = True
                if identity in details: details[identity] = None
                return None
            if required: required_reads += 1
            read = await self._fetch('read_job_detail', identity, fresh_after=fresh_after)
            raw = read.payload if read is not None else None
            row = work._job(raw, self.clock(), detail=True)
            details[identity] = raw if row is not None and row['id'] == identity else None
            detail_bounds[identity] = fresh_after
            detail_times[identity] = work._stamp(read.observed_at, self.clock()) if read is not None else None
            if details[identity] is None: partial = True
            return details[identity]

        entry = self.cache.get_last_good(SLOT_SURF_WORK)
        previous = work.coerce_snapshot(getattr(entry, 'payload', None), now=self.clock())
        prior_ids = [j['id'] for j in previous['jobs'] if j['state'] == 'executing' and
                     j['id'] in previous['current_job_ids']] if previous else []
        observed = {j['id'] for j in rows if j['state'] == 'executing'}
        open_ids = {j['id'] for j in rows if j['state'] not in work.TERMINAL}
        stored_ids = {j['id'] for j in jobs}
        page, seen, before = first_page, {j['id'] for j in rows}, None
        reached_end = len(page) < work.PAGE_LIMIT
        history_complete = reached_end or any(j['created_ts'] is not None and j['created_ts'] < cutoff for j in rows)
        for identity in dict.fromkeys([j['id'] for j in rows if j['state'] == 'executing'] + prior_ids):
            raw = await read_job(identity, fresh_after=discovery_mono)
            if raw is None:
                discovery_ok = False
            elif raw['state'] == 'executing':
                observed.add(identity)
                if identity not in stored_ids: jobs.append(raw); stored_ids.add(identity)
            else:
                observed.discard(identity)
            if raw is not None:
                if raw['state'] in work.TERMINAL:
                    open_ids.discard(identity)
                else:
                    open_ids.add(identity)
                    if identity not in stored_ids: jobs.append(raw); stored_ids.add(identity)

        for _ in range(max(0, work.SCAN_PAGES - 1)):
            if (history_complete and hint is not None and len(observed) == hint
                    and (reached_end or open_hint is not None and len(open_ids) == open_hint)): break
            limit = work.PAGE_LIMIT if before is None else work.SCAN_PAGE_LIMIT
            if len(page) < limit: break
            cursor = page[-1].get('createdAt') if isinstance(page[-1], dict) else None
            stamp = work._stamp(work._ts(cursor), self.clock())
            if not isinstance(cursor, str) or not cursor.endswith('Z') or stamp is None or (before is not None and stamp >= work._ts(before)):
                discovery_ok = False; break
            before = cursor
            page = await self._fetch('fetch_jobs', limit=work.SCAN_PAGE_LIMIT, before=before)
            if not isinstance(page, list): discovery_ok = False; break
            page_mono = self.client._monotonic()
            decoded, _ = work._page(page, work._job, self.clock(), work.SCAN_PAGE_LIMIT)
            if len(decoded) != len(page) or any(j['id'] in seen for j in decoded):
                discovery_ok = False; break
            seen.update(j['id'] for j in decoded)
            open_ids.update(j['id'] for j in decoded if j['state'] not in work.TERMINAL)
            reached_end = len(page) < work.SCAN_PAGE_LIMIT
            history_complete |= reached_end or any(j['created_ts'] is not None and j['created_ts'] < cutoff for j in decoded)
            for row in decoded:
                if row['state'] in work.TERMINAL and (row['created_ts'] or started) < cutoff: continue
                if row['id'] not in stored_ids:
                    if len(jobs) >= work.HISTORY_JOB_LIMIT + work.CONTEXT_DETAIL_LIMIT:
                        discovery_ok = False; continue
                    raw = next(j for j in page if j['id'] == row['id'])
                    jobs.append(raw); stored_ids.add(row['id'])
                if row['state'] != 'executing': continue
                observed.add(row['id'])
                detail = await read_job(row['id'], fresh_after=page_mono)
                if detail is None: discovery_ok = False
                elif detail['state'] != 'executing': observed.discard(row['id'])
                if detail is not None and detail['state'] in work.TERMINAL: open_ids.discard(row['id'])
        open_complete = reached_end or open_hint is not None and len(open_ids) == open_hint
        complete = discovery_ok and hint is not None and len(observed) == hint and open_complete
        partial |= not history_complete or not open_complete
        if previous and (not history_complete or not open_complete):
            raise ValueError('job history or open population incomplete; retaining previous snapshot')
        projects, metadata, anchors, owners = {}, {}, {}, {}
        active = {identity: raw for identity, raw in details.items() if raw and raw['state'] == 'executing'}
        for identity, raw in active.items():
            context = work.project_context(raw)
            if raw.get('project') is not None and context is None: partial = True
            if context is not None:
                project, versions = context
                pid = project['id']
                merged = list(dict.fromkeys(projects.get(pid, {}).get('job_ids', []) + project['job_ids']))
                if (len(merged) > work.VERSION_LIMIT or len(set(owners) | set(merged)) > work.CONTEXT_JOB_LIMIT - 2 * work.WORKFLOW_DETAIL_LIMIT
                        or any(i in owners and owners[i] != pid for i in merged)):
                    partial = True; continue
                if pid in projects:
                    project['job_ids'] = merged
                    project['active_job_ids'] = list(dict.fromkeys(projects[pid]['active_job_ids'] + [identity]))
                    project['workflow_ids'] = list(dict.fromkeys(projects[pid]['workflow_ids'] + project['workflow_ids']))
                projects[pid] = project
                for version in versions:
                    job_id = version['jobId']; owners[job_id] = pid
                    metadata[job_id] = dict(version, id=job_id)
                    if version.get('workflowId'): anchors.setdefault(version['workflowId'], set()).add(job_id)
            linked = raw.get('workflow')
            if linked is not None:
                flow_id = work.parse_job_id(linked.get('id')) if isinstance(linked, dict) else None
                if flow_id is None: partial = True
                else:
                    anchors.setdefault(flow_id, set()).add(identity)
                    if identity in owners and flow_id not in projects[owners[identity]]['workflow_ids']:
                        projects[owners[identity]]['workflow_ids'].append(flow_id)
        workflow_rows = {raw['id']: raw for raw in workflows[:work.WORKFLOW_LIMIT]
                         if isinstance(raw, dict) and raw.get('id') in {f['id'] for f in flows}}
        peer_flows = {}
        for index, (identity, members) in enumerate(anchors.items()):
            if index >= work.WORKFLOW_DETAIL_LIMIT: partial = True; break
            raw = await self._fetch('fetch_workflow', identity)
            normalized = work.workflow_context(raw, identity, members, now=self.clock())
            if normalized is None:
                partial = True
                workflow_rows.pop(identity, None)
                continue
            linked = [normalized.get(k) for k in ('contractsJobId', 'frontendJobId') if normalized.get(k)]
            pids = {owners[i] for i in members if i in owners}
            if len(pids) > 1 or any(i in owners and owners[i] not in pids for i in linked):
                partial = True; workflow_rows.pop(identity, None); continue
            workflow_rows[identity] = normalized
            for job_id in linked:
                peer_flows[job_id] = identity
                if pids:
                    pid = next(iter(pids)); project = projects[pid]
                    if job_id not in project['job_ids']:
                        if len(owners) >= work.CONTEXT_JOB_LIMIT: partial = True; continue
                        project['job_ids'].append(job_id); owners[job_id] = pid
                expected.add(job_id)
        for identity in list(dict.fromkeys(list(owners) + list(peer_flows))):
            raw = await read_job(identity)
            if raw is None: continue
            project, workflow = raw.get('project'), raw.get('workflow')
            foreign_project = identity in owners and project is not None and (work.project_context(raw, active_only=False) is None
                                                                             or project.get('id') != owners[identity])
            foreign_flow = identity in peer_flows and (not isinstance(workflow, dict) or workflow.get('id') != peer_flows[identity])
            if foreign_project or foreign_flow or raw.get('parentJobId') == identity:
                if identity not in active: details[identity] = None
                partial = True
                # A rejected active member cannot authorize a persisted project.
                for pid in list(projects):
                    if identity in projects[pid]['active_job_ids']:
                        del projects[pid]
                if identity in active: complete = False
        current_rows, _ = work._page(jobs, work._job, self.clock(), work.HISTORY_JOB_LIMIT + work.CONTEXT_DETAIL_LIMIT)
        enrichment_rows = [row for row in current_rows if row['state'] == 'executing' or (row['created_ts'] or started) >= cutoff]
        optional = [i for i in work.detail_ids(enrichment_rows, flows) if i not in details and i not in expected]
        expected.update(optional)
        versions = {row['id']: [row['state'], row['updated_ts']] for row in current_rows}
        prior_jobs = {row['id']: row for row in previous['jobs']} if previous else {}
        retained = {identity: point for identity, point in (previous or {}).get('optional_details', {}).items()
                    if identity in optional and point['version'] == versions.get(identity)
                    and started - point['read_ts'] < work.HISTORY_SECONDS}
        cursor = (previous or {}).get('optional_cursor')
        offset = optional.index(cursor) + 1 if cursor in optional else 0
        ordered = optional[offset:] + optional[:offset]
        due = [identity for identity in ordered if identity not in retained
               or started - retained[identity]['read_ts'] >= work.OPTIONAL_DETAIL_TTL]
        for identity in due[:work.DETAIL_LIMIT]:
            raw = await read_job(identity, required=False)
            row = work._job(raw, self.clock(), detail=True)
            if (row is not None and row['nodes'] is not None and identity in versions
                    and detail_times[identity] is not None):
                retained[identity] = dict(version=versions[identity], read_ts=detail_times[identity])
            elif identity in retained:
                # A failed refresh cannot retimestamp or erase same-version evidence.
                details.pop(identity, None)
            cursor = identity
        retained = dict(sorted(retained.items(), key=lambda item: item[1]['read_ts'], reverse=True)[:work.OPTIONAL_CACHE_LIMIT])
        prior_details = {identity: prior_jobs[identity] for identity in retained
                         if identity not in details and identity in prior_jobs}
        observed = [point['read_ts'] for point in retained.values()]
        result = work.snapshot(jobs, list(workflow_rows.values()), details, read_ts=min(started, workflow_started, *observed), now=self.clock(),
                             projects=list(projects.values()), metadata=metadata, expected_ids=expected,
                             active_scan_complete=complete, coverage_partial=partial,
                             workflow_scan_complete=workflow_complete,
                             retained_details=prior_details,
                             context_job_ids=list(dict.fromkeys(list(owners) + list(peer_flows))),
                             context_workflow_ids=list(anchors))
        result.update(optional_details=retained, optional_cursor=cursor)
        if not workflow_complete and previous:
            retained = {row['id']: row for row in result['workflows']}
            for row in previous['workflows']:
                retained.setdefault(row['id'], row)
            result['workflows'] = list(retained.values())[:work.WORKFLOW_LIMIT + work.WORKFLOW_DETAIL_LIMIT]
            retained_ids = {row['id'] for row in result['workflows']}
            result['current_workflow_ids'] = list(dict.fromkeys(result['current_workflow_ids'] +
                [identity for identity in previous['current_workflow_ids'] if identity in retained_ids and identity not in result['context_workflow_ids']]))
            result['read_ts'] = min(result['read_ts'], previous['read_ts'])
        return result

    async def _read(self):
        started = self.clock()
        try:
            snapshot = await self._collect(started)
            if work.coerce_snapshot(snapshot, now=self.clock()) is None:
                raise ValueError('invalid assembled work snapshot')
            self.cache.store_last_good(SLOT_SURF_WORK, snapshot, ts=started)
            self.cache.mark_fetched(TIER_SURF_WORK, self.clock())
            self.cache.save()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug('WIP read unavailable: %s', exc)
            self.cache.mark_failed(TIER_SURF_WORK, self.clock())
