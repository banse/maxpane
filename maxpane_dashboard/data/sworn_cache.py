"""Atomic, deployment-bound last-good cards; no raster data is persisted."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile

from .sworn_client import BINDING, MAX_SVG, address, validate_metadata

MAX_CARDS = 32
DEFAULT_CACHE_PATH = Path.home() / '.maxpane' / 'sworn_cache.json'


class SwornCache:
    def __init__(self, path, *, now):
        self.path, self.cards = Path(path), {}
        self.supply = self.block = self.observed_at = None
        try:
            if self.path.stat().st_size > 16_000_000:
                return
            raw = json.loads(self.path.read_text())
            if raw.get('binding') != BINDING:
                return
            stamp = raw.get('observed_at')
            if not self._stamp(stamp, now):
                return
            if type(raw.get('supply')) is not int or not 0 <= raw['supply'] < 2**256 or type(raw.get('block')) is not int:
                return
            self.supply, self.block, self.observed_at = raw['supply'], raw['block'], stamp
            for card in raw.get('cards', [])[-MAX_CARDS:]:
                try:
                    if type(card.get('token_id')) is not int or not 0 < card['token_id'] <= self.supply:
                        continue
                    if not all(address(card.get(k)) for k in ('claimant', 'holder')) or not self._stamp(card.get('observed_at'), now):
                        continue
                    if any(type(card.get(k)) is not int or card[k] < 0 for k in ('minted_at_block', 'block')):
                        continue
                    if not isinstance(card.get('svg'), str) or len(card['svg'].encode()) > MAX_SVG:
                        continue
                    validate_metadata(card['metadata'], card['claimant'])
                    self.put(card)
                except (KeyError, ValueError, TypeError, AttributeError):
                    continue
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @staticmethod
    def _stamp(value, now):
        return type(value) in (float, int) and math.isfinite(value) and now - 7*86400 <= value <= now + 60

    def put(self, card):
        key = card['token_id']
        self.cards.pop(key, None)
        self.cards[key] = card
        while len(self.cards) > MAX_CARDS:
            self.cards.pop(next(iter(self.cards)))

    def save(self):
        if self.observed_at is None:
            return
        name = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', dir=self.path.parent, delete=False) as stream:
                name = stream.name
                json.dump({'binding': BINDING, 'supply': self.supply, 'block': self.block,
                           'observed_at': self.observed_at, 'cards': list(self.cards.values())}, stream)
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
