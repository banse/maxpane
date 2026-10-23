"""Detached list and selected-detail reads; changing selection never crosses identities."""
import asyncio
import logging

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data import surf_oracles as oracle
from maxpane_dashboard.data.surf_cache import SLOT_SURF_ORACLES, TIER_SURF_ORACLES

logger = logging.getLogger(__name__)


class OraclesReader:
    def __init__(self, client, cache, *, clock):
        self.client, self.cache, self.clock = client, cache, clock
        self.task = None
        self.selected_id = None
        self._failed = {}
        self._details_active = True
        self._reading_detail = False
        self._detail_task = None

    def _snapshot(self):
        entry = self.cache.get_last_good(SLOT_SURF_ORACLES)
        return oracle.coerce_snapshot(getattr(entry, 'payload', None), now=self.clock()) or oracle.empty_snapshot()

    def select(self, identity):
        identity = parse_job_id(identity)
        if identity == self.selected_id:
            return
        self.selected_id = identity
        if self._detail_task is not None and not self._detail_task.done():
            self._detail_task.cancel()
        snapshot = self._snapshot()
        entry = snapshot['details'].get(identity)
        if entry is not None:
            snapshot['details'][identity] = dict(entry, access_ts=self.clock())
            self._store(snapshot)

    def _row(self, snapshot):
        return next((row for row in snapshot['rows'] or [] if row['id'] == self.selected_id), None)

    def _entry(self, snapshot):
        return snapshot['details'].get(self.selected_id)

    def _detail_due(self, snapshot):
        row = self._row(snapshot)
        if row is None or row['job_id'] is None:
            return False
        failed = self._failed.get(self.selected_id)
        if failed is not None and self.clock() - failed < 120:
            return False
        entry = self._entry(snapshot)
        return (entry is None or entry['version'] != oracle.version(row)
                or self.clock() - entry['read_ts'] >= oracle.MAX_AGE
                or entry['row']['status'] not in oracle.TERMINAL
                and self.clock() - entry['read_ts'] >= oracle.DETAIL_TTL)

    def set_details_active(self, active):
        """Keep shared list polling while stopping hidden selected-detail work."""
        was_active = self._details_active
        self._details_active = bool(active)
        if was_active and not self._details_active and self._reading_detail:
            self.cancel()

    def offer(self, *, include_detail=True):
        self.set_details_active(include_detail)
        if self.task is not None and not self.task.done():
            if self.task.cancelling():
                self.task = asyncio.create_task(self._read_after_cancel(self.task))
            return self.task
        snapshot = self._snapshot()
        if not self.cache.is_due(TIER_SURF_ORACLES, self.clock()) and not (
                self._details_active and self._detail_due(snapshot)):
            return None
        self.task = asyncio.create_task(self._read())
        return self.task

    async def _read_after_cancel(self, prior):
        # Screen suspend may cancel just before the next screen resumes.
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
        snapshot, now = self._snapshot(), self.clock()
        row, entry = self._row(snapshot), self._entry(snapshot)
        failed = self._failed.get(self.selected_id) is not None
        state = 'unavailable' if snapshot['rows'] is None else (
            'stale' if self.cache.last_failure_ts(TIER_SURF_ORACLES) is not None
            or now - snapshot['read_ts'] > 120 else 'ok')
        if entry is None:
            detail_state = 'loading' if row is not None and row['job_id'] is not None and not failed else 'unavailable'
        else:
            stale = (failed or row is None or entry['version'] != oracle.version(row)
                     or now - entry['read_ts'] >= oracle.MAX_AGE
                     or entry['row']['status'] not in oracle.TERMINAL
                     and now - entry['read_ts'] >= oracle.DETAIL_TTL)
            partial = entry['truncated'] or row is not None and entry['row']['status'] != row['status']
            detail_state = 'stale' if stale else 'partial' if partial else 'ok'
        return dict(state=state, partial=snapshot['partial'], read_ts=snapshot['read_ts'], now_ts=now,
                    rows=snapshot['rows'], selected_id=self.selected_id,
                    detail=oracle.project_detail(entry) if entry else None, detail_state=detail_state,
                    detail_read_ts=entry['read_ts'] if entry else None)

    def _store(self, snapshot):
        clean = oracle.coerce_snapshot(snapshot, now=self.clock())
        self.cache.store_last_good(SLOT_SURF_ORACLES, clean, ts=self.clock())
        self.cache.save()

    async def _read(self):
        if self.cache.is_due(TIER_SURF_ORACLES, self.clock()):
            started = self.clock()
            try:
                raw = await self.client.fetch_oracle_requests(limit=oracle.PAGE_LIMIT)
                rows, partial = oracle.decode_page(raw, now=self.clock())
                snapshot = self._snapshot()
                snapshot.update(rows=rows, partial=partial, read_ts=started)
                self._store(snapshot)
                self.cache.mark_fetched(TIER_SURF_ORACLES, started)
                if self.selected_id is None and rows:
                    self.select(rows[0]['id'])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug('Oracle list unavailable: %s', exc)
                self.cache.mark_failed(TIER_SURF_ORACLES, self.clock())
        # One current selection at a time. A late result may cache its own identity;
        # the loop then drains the latest selection without waiting for a UI poll.
        while self._details_active and self._detail_due(snapshot := self._snapshot()):
            row, started = self._row(snapshot), self.clock()
            identity = row['id']
            try:
                self._reading_detail = True
                self._detail_task = asyncio.create_task(self.client.fetch_oracle_detail(identity))
                raw = await self._detail_task
                entry = oracle.decode_detail(raw, row, read_ts=started, now=self.clock())
                if entry is None:
                    raise ValueError('invalid oracle detail')
                snapshot = self._snapshot()
                snapshot['details'][identity] = entry
                self._store(snapshot)
                self._failed.pop(identity, None)
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling() or not self._details_active:
                    raise
                # Only the superseded detail was cancelled. Its list is still
                # valid and the parent can immediately drain the new selection.
                continue
            except Exception as exc:
                logger.debug('Oracle detail unavailable: %s', exc)
                self._failed[identity] = self.clock()
                self._failed = dict(sorted(self._failed.items(), key=lambda item: item[1], reverse=True)[:100])
            finally:
                self._reading_detail = False
                self._detail_task = None
            if identity == self.selected_id:
                break
