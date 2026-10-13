"""Detached, bounded read-only WIP polling through the existing swarm client."""
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

    async def _read(self):
        started = self.clock()
        try:
            jobs = await self.client.fetch_jobs(limit=work.PAGE_LIMIT)
            if not isinstance(jobs, list):
                raise ValueError('jobs unavailable')
            workflows = await self.client.fetch_workflows(limit=work.PAGE_LIMIT)
            if not isinstance(workflows, list):
                raise ValueError('workflows unavailable')
            rows, flows, _ = work.decode_pages(jobs, workflows, now=self.clock())
            if (jobs and not rows) or (workflows and not flows):
                raise ValueError('nonempty work page has no valid rows')
            details = {}
            for identity in work.detail_ids(rows, flows)[:work.DETAIL_LIMIT]:
                try:
                    raw = await self.client.fetch_job(identity)
                except Exception:
                    raw = None
                if isinstance(raw, dict) and raw.get('error') == 'busy':
                    raise ValueError('swarm busy')
                details[identity] = raw
            now = self.clock()
            snapshot = work.snapshot(jobs, workflows, details, read_ts=started, now=now)
            self.cache.store_last_good(SLOT_SURF_WORK, snapshot, ts=started)
            self.cache.mark_fetched(TIER_SURF_WORK, now)
            self.cache.save()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug('WIP read unavailable: %s', exc)
            self.cache.mark_failed(TIER_SURF_WORK, self.clock())
