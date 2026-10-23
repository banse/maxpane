"""Reader-owned selected-card acquisition with cache-first local projection."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import logging
import time

from .sworn_cache import DEFAULT_CACHE_PATH, SwornCache
from .sworn_client import SwornClient, address
from .sworn_models import empty_payload

logger = logging.getLogger(__name__)


class SwornManager:
    def __init__(self, poll_interval=30, *, client=None, cache_path=DEFAULT_CACHE_PATH, now=time.time, prepare=None):
        if prepare is None:
            from .sworn_art import prepare_art
            prepare = prepare_art
        self.client = client or SwornClient()
        self.cache = SwornCache(cache_path, now=now())
        self._now, self._prepare = now, prepare
        self._selection = self._active = self._error = None
        self._generation, self._busy = 0, False
        self._error_count = 0
        self._art = OrderedDict()

    def set_active_view(self, view):
        if self._active != view:
            self._generation += 1
            self._active = view

    def select(self, value):
        value = str(value).strip().lower() if value is not None else None
        value = value or None
        if value != self._selection:
            self._generation += 1
        self._selection, self._error = value, None
        if not self._valid_selection():
            self._error = 'Enter a token ID or original claimant address'

    def _valid_selection(self):
        value = self._selection
        return value is None or address(value) or (value.isascii() and value.isdecimal() and len(value) <= 78 and 0 < int(value) < 2**256)

    def _selected(self):
        if not self._valid_selection():
            return None
        if address(self._selection):
            return next((c for c in self.cache.cards.values() if c['claimant'].lower() == self._selection), None)
        token_id = int(self._selection) if self._selection else self.cache.supply
        return self.cache.cards.get(token_id)

    def get_snapshot(self):
        payload = empty_payload()
        card, supply = self._selected(), self.cache.supply
        if card:
            digest = hashlib.sha256(card['svg'].encode()).hexdigest()
            if digest not in self._art:
                try:
                    self._art[digest] = self._prepare(card['svg'])
                except (ValueError, RuntimeError, ImportError):
                    self._art[digest] = None
            self._art.move_to_end(digest)
            while len(self._art) > 8:
                self._art.popitem(last=False)
            payload['sworn_selected'] = {k: v for k, v in card.items() if k != 'svg'} | {'art': self._art[digest]}
        if supply:
            selected = card['token_id'] if card else int(self._selection) if self._valid_selection() and self._selection and self._selection.isdecimal() else supply
            start = supply - ((supply - min(supply, selected)) // 20) * 20
            for token_id in range(start, max(0, start-20), -1):
                known = self.cache.cards.get(token_id)
                families = len({i//100 for i in known['metadata']['traits'] if 100 <= i < 1400}) if known else None
                payload['sworn_rows'].append({'token_id': token_id, 'families': families})
        payload.update(sworn_supply=supply, sworn_selection=self._selection, sworn_error=self._error,
                       sworn_block=self.cache.block, sworn_observed_at=self.cache.observed_at)
        return payload

    async def fetch_and_compute(self):
        if self._active is None or self._busy or not self._valid_selection():
            return self.get_snapshot()
        generation, selection = self._generation, self._selection
        self._busy = True
        try:
            async with asyncio.timeout(24):
                result = await self.client.fetch(selection)
            if generation != self._generation:
                return self.get_snapshot()
            stamp = self._now()
            self._error_count = 0
            self.cache.supply, self.cache.block, self.cache.observed_at = result['supply'], result['block'], stamp
            self._error = result.get('error')
            for token_id in list(self.cache.cards):
                if token_id > result['supply']:
                    self.cache.cards.pop(token_id)
            if result['card'] is not None:
                self.cache.put(result['card'] | {'block': result['block'], 'observed_at': stamp})
            elif (previous := self._selected()) is not None:
                self.cache.cards.pop(previous['token_id'], None)
            try:
                self.cache.save()
            except OSError:
                logger.warning('Sworn cache could not be saved')
        except asyncio.CancelledError:
            raise
        except Exception:
            if generation == self._generation:
                self._error, self._error_count = None, self._error_count + 1
            logger.warning('Sworn read did not complete', exc_info=True)
        finally:
            self._busy = False
        return self.get_snapshot()

    async def close(self):
        await self.client.close()
