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

    def offer(self):
        if self.task is not None and not self.task.done():
            return self.task
        if not self.cache.is_due(TIER_SURF_WORK, self.clock()):
            return None
        self.task = asyncio.create_task(self._read())
        return self.task

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
            raw = await getattr(self.client, method)(*args, **kwargs)
        except Exception:
            return None
        if isinstance(raw, dict) and raw.get('error') == 'busy':
            raise ValueError('swarm busy')
        return raw

    async def _collect(self, started):
        jobs = await self._fetch('fetch_jobs', limit=work.PAGE_LIMIT)
        if not isinstance(jobs, list): raise ValueError('jobs unavailable')
        workflows = await self._fetch('fetch_workflows', limit=work.PAGE_LIMIT)
        if not isinstance(workflows, list): raise ValueError('workflows unavailable')
        rows, flows, _ = work.decode_pages(jobs, workflows, now=self.clock())
        if (jobs and not rows) or (workflows and not flows):
            raise ValueError('nonempty work page has no valid rows')
        partial = len(rows) != len(jobs) or len(flows) != len(workflows) or len(workflows) >= work.PAGE_LIMIT
        discovery_ok = len(rows) == len(jobs)
        jobs = [raw for raw in jobs[:work.PAGE_LIMIT] if isinstance(raw, dict) and raw.get('id') in {r['id'] for r in rows}]
        overview = await self._fetch('fetch_overview')
        counts = overview.get('counts') if isinstance(overview, dict) else None
        states = counts.get('jobStates') if isinstance(counts, dict) else None
        hint = work.integer(states.get('executing')) if isinstance(states, dict) else None
        details, expected = {}, set()
        required_reads = 0

        async def read_job(identity, *, required=True):
            nonlocal required_reads, partial
            expected.add(identity)
            if identity in details: return details[identity]
            if required and required_reads >= work.CONTEXT_DETAIL_LIMIT:
                partial = True
                return None
            if required: required_reads += 1
            raw = await self._fetch('fetch_job', identity)
            row = work._job(raw, self.clock(), detail=True)
            details[identity] = raw if row is not None and row['id'] == identity else None
            if details[identity] is None: partial = True
            return details[identity]

        entry = self.cache.get_last_good(SLOT_SURF_WORK)
        previous = work.coerce_snapshot(getattr(entry, 'payload', None), now=self.clock())
        prior_ids = [j['id'] for j in previous['jobs'] if j['state'] == 'executing' and
                     j['id'] in previous['current_job_ids']] if previous else []
        observed = {j['id'] for j in rows if j['state'] == 'executing'}
        stored_ids = {j['id'] for j in rows}
        page, seen, before = list(jobs), set(stored_ids), None
        for identity in dict.fromkeys([j['id'] for j in rows if j['state'] == 'executing'] + prior_ids):
            raw = await read_job(identity)
            if raw is None:
                discovery_ok = False
            elif raw['state'] == 'executing':
                observed.add(identity)
                if identity not in stored_ids: jobs.append(raw); stored_ids.add(identity)
            else:
                observed.discard(identity)

        for _ in range(max(0, work.SCAN_PAGES - 1)):
            if hint is not None and len(observed) >= hint: break
            limit = work.PAGE_LIMIT if before is None else work.SCAN_PAGE_LIMIT
            if len(page) < limit: break
            cursor = page[-1].get('createdAt') if isinstance(page[-1], dict) else None
            stamp = work._stamp(work._ts(cursor), self.clock())
            if not isinstance(cursor, str) or not cursor.endswith('Z') or stamp is None or (before is not None and stamp >= work._ts(before)):
                discovery_ok = False; break
            before = cursor
            page = await self._fetch('fetch_jobs', limit=work.SCAN_PAGE_LIMIT, before=before)
            if not isinstance(page, list): discovery_ok = False; break
            decoded, _ = work._page(page, work._job, self.clock(), work.SCAN_PAGE_LIMIT)
            if len(decoded) != len(page) or any(j['id'] in seen for j in decoded):
                discovery_ok = False; break
            seen.update(j['id'] for j in decoded)
            for row in decoded:
                if row['state'] != 'executing': continue
                observed.add(row['id'])
                if row['id'] not in stored_ids:
                    if len(jobs) >= work.PAGE_LIMIT + work.CONTEXT_DETAIL_LIMIT:
                        discovery_ok = False; continue
                    raw = next(j for j in page if j['id'] == row['id'])
                    jobs.append(raw); stored_ids.add(row['id'])
                detail = await read_job(row['id'])
                if detail is None: discovery_ok = False
                elif detail['state'] != 'executing': observed.discard(row['id'])
        complete = discovery_ok and hint is not None and len(observed) == hint
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
        workflow_rows = {raw['id']: raw for raw in workflows[:work.PAGE_LIMIT]
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
        optional = [i for i in work.detail_ids(rows, flows) if i not in details and i not in expected]
        expected.update(optional)
        for identity in optional[:work.DETAIL_LIMIT]: await read_job(identity, required=False)
        return work.snapshot(jobs, list(workflow_rows.values()), details, read_ts=started, now=self.clock(),
                             projects=list(projects.values()), metadata=metadata, expected_ids=expected,
                             active_scan_complete=complete, coverage_partial=partial,
                             context_job_ids=list(dict.fromkeys(list(owners) + list(peer_flows))),
                             context_workflow_ids=list(anchors))

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
