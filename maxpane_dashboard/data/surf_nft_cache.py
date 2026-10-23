"""Small atomic evidence cache; saving never renews source observations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import time

from maxpane_dashboard.analytics.surf_launch_checks import address

log = logging.getLogger(__name__)
_CLOCK_FIELDS = frozenset(('observed_at', '_observed_at', 'checkedAt', 'started_at', 'read_at',
                           'head_at', 'attempt_at', 'readTimestamp'))


def _stamp(value):
    if type(value) in (int, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
        except (ValueError, OverflowError, OSError):
            pass
    return None


def _valid_json(value, now, depth=0):
    if depth > 40:
        return False
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_valid_json(v, now, depth + 1) for v in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not _valid_json(item, now, depth + 1):
                return False
            if key in _CLOCK_FIELDS and item is not None:
                stamp = _stamp(item)
                if stamp is None or not 0 <= stamp <= now:
                    return False
        return True
    return False


def _identity(key, value=None):
    if not isinstance(key, str) or ':' not in key:
        return False
    chain, contract = key.split(':', 1)
    if chain not in ('1', '4663') or address(contract) != contract:
        return False
    if value is not None:
        raw_chain = value.get('chainId', value.get('chain_id'))
        raw_address = value.get('address', value.get('contract'))
        return type(raw_chain) is int and str(raw_chain) == chain and address(raw_address) == contract
    return True


class SurfNftCache:
    """No I/O on construction; unknown records remain distinct from empty ones."""

    MAX_BYTES = 16 * 1024 * 1024
    MAX_RECORDS = 1000
    MAX_FACTS = 2000
    MAX_STAGES = 32
    MAX_STAGE_BYTES = 256 * 1024

    def __init__(self, *, path=None, clock=time.time):
        self.path = Path(path) if path is not None else Path.home() / '.maxpane' / 'surf_nft_cache.json'
        self.clock = clock

    @staticmethod
    def empty():
        return {'discovery': {}, 'evidence': {}, 'progress': {}, 'child_candidates': {}, 'records': None,
                'cache_partial': False, 'last_attempt': None, 'probe_turn': 0}

    def _coerce(self, raw, *, selected_id=None):
        out = self.empty()
        if not isinstance(raw, dict):
            return out
        now = self.clock()
        partial = raw.get('cache_partial') is True
        turn = raw.get('probe_turn')
        if type(turn) is int and turn >= 0:
            out['probe_turn'] = turn % 4
        discovery = raw.get('discovery', {})
        if isinstance(discovery, dict):
            from maxpane_dashboard.data.surf_nft_discovery import validate_discovery_state
            out['discovery'] = validate_discovery_state(discovery, now=now) if discovery else {}
            facts = out['discovery'].get('raw', {})
            remaining = self.MAX_FACTS
            if isinstance(facts, dict):
                for family in ('launches', 'launchDetails', 'jobDetails', 'workflows', 'publications'):
                    entries = facts.get(family)
                    if isinstance(entries, (dict, list)):
                        if len(entries) > remaining:
                            partial = True
                            if isinstance(entries, dict):
                                facts[family] = dict(list(entries.items())[-remaining:]) if remaining else {}
                            else:
                                facts[family] = entries[-remaining:] if remaining else []
                        remaining = max(0, remaining - len(facts[family]))
        elif discovery:
            partial = True
        for family, limit in (('evidence', self.MAX_RECORDS), ('progress', self.MAX_STAGES)):
            entries = raw.get(family, {})
            if not isinstance(entries, dict):
                partial = True
                continue
            # Preserve selected work, then the newest observations; stable tie order.
            def priority(pair):
                key, value = pair
                stamp = _stamp(value.get('checkedAt', value.get('started_at'))) if isinstance(value, dict) else None
                return key != selected_id, -(stamp or 0)
            for key, value in sorted(entries.items(), key=priority):
                if (not isinstance(value, dict) or not _identity(key, value if family == 'evidence' else None)
                        or not _valid_json(value, now)
                        or len(out[family]) >= limit
                        or family == 'progress' and len(json.dumps(value).encode()) > self.MAX_STAGE_BYTES):
                    partial = True
                    continue
                out[family][key] = deepcopy(value)
        children = raw.get('child_candidates', {})
        if isinstance(children, dict):
            for key, candidate in children.items():
                if (not isinstance(candidate, dict) or not _identity(key, candidate)
                        or not _valid_json(candidate, now) or len(out['child_candidates']) >= self.MAX_RECORDS):
                    partial = True
                    continue
                out['child_candidates'][key] = deepcopy(candidate)
        records = raw.get('records')
        if isinstance(records, list):
            # The normalizer is the same boundary used on live scanner records.
            from maxpane_dashboard.analytics.surf_nft import normalize_record
            out['records'] = []
            seen = set()
            ordered = sorted(records, key=lambda row: not isinstance(row, dict) or row.get('id') != selected_id)
            for record in ordered:
                normalized = normalize_record(record) if isinstance(record, dict) and _valid_json(record, now) else None
                if normalized is None or normalized['id'] in seen or len(out['records']) >= self.MAX_RECORDS:
                    partial = True
                    continue
                seen.add(normalized['id'])
                out['records'].append(normalized)
        elif records is not None:
            partial = True
        attempt = _stamp(raw.get('last_attempt'))
        out['last_attempt'] = attempt if attempt is not None and 0 <= attempt <= now else None
        out['cache_partial'] = partial
        return self._fit_bytes(out, now, selected_id)

    def _fit_bytes(self, state, now, selected_id):
        """Evict oldest supplementary facts first, retaining selected/staged work."""
        def encoded(value):
            return json.dumps(value, allow_nan=False, separators=(',', ':')).encode()
        def size():
            return len(encoded(dict(state, version=1, saved_at=now)))
        remaining = size()
        if remaining <= self.MAX_BYTES:
            return state
        state['cache_partial'] = True
        discovery = state['discovery']
        discovery['truncated'] = True
        raw = discovery.get('raw', {})
        raw.setdefault('coverage', {})['complete'] = False
        remaining = size()
        removable = []
        def collect(container, rank):
            pairs = container.items() if isinstance(container, dict) else enumerate(container)
            for key, value in pairs:
                identity = value.get('id', key) if isinstance(value, dict) else key
                stamp = next((_stamp(value.get(field)) for field in
                    ('_observed_at', 'checkedAt', 'started_at', 'last_meaningful_at')
                    if isinstance(value, dict) and _stamp(value.get(field)) is not None), 0)
                removable.append((identity == selected_id, rank, stamp, container, key, value))
        for rank, family in enumerate(('publications', 'workflows', 'sites', 'launches',
                                       'jobDetails', 'launchDetails')):
            container = raw.get(family, {})
            collect(container.get('sites', []) if family == 'sites' else container, rank)
        for rank, family in enumerate(('pending_jobs', 'pending_launches'), 6):
            collect(discovery.get(family, {}), rank)
        for rank, family in enumerate(('child_candidates', 'evidence', 'records', 'progress'), 8):
            collect(state.get(family) or {}, rank)
        for _, _, _, container, key, value in sorted(removable, key=lambda row: row[:3]):
            if remaining <= self.MAX_BYTES:
                break
            # Ignore removed separators: the estimate remains conservatively high.
            remaining -= len(encoded(value))
            if isinstance(container, dict):
                remaining -= len(encoded(key)) + 1
                del container[key]
            else:
                container.remove(value)
        return state

    def load(self):
        try:
            if self.path.stat().st_size > self.MAX_BYTES:
                return self.empty()
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict) or raw.get('version') != 1:
                return self.empty()
            return self._coerce(raw)
        except (OSError, ValueError, TypeError, RecursionError):
            return self.empty()

    def prepare(self, state, *, selected_id=None):
        """Apply the same bounds to retained memory and persisted evidence."""
        return self._coerce(state, selected_id=selected_id)

    def save(self, state, *, selected_id=None):
        try:
            return self._write(self.prepare(state, selected_id=selected_id))
        except (ValueError, TypeError, RecursionError) as exc:
            log.debug('NFT cache validation failed: %s', exc)
            return False

    def prepare_and_save(self, state, *, selected_id=None):
        """Validate once, persist that exact bounded snapshot, and retain it."""
        clean = self.prepare(state, selected_id=selected_id)
        self._write(clean)
        return clean

    def _write(self, clean):
        temporary = None
        try:
            payload = json.dumps(dict(clean, version=1, saved_at=self.clock()), allow_nan=False,
                                 separators=(',', ':')).encode()
            if len(payload) > self.MAX_BYTES:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.surf-nft-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            log.debug('NFT cache write failed: %s', exc)
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
