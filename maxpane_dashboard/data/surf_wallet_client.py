"""Validated public wallet reads through the shared, keyless Swarm transport."""
import re

from maxpane_dashboard.analytics.surf_ids import parse_job_id


def wallet_address(value):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', value) and int(value[2:], 16) else None


class SurfWalletClient:
    def __init__(self, swarm):
        self.swarm = swarm
        self._schedule_passes = {}

    async def orders(self, wallet):
        wallet = wallet_address(wallet)
        if wallet is None:
            return None
        payload = await self.swarm._get(f'/requests/paid-by/{wallet}')
        if not isinstance(payload, dict) or wallet_address(payload.get('payer')) != wallet:
            return None
        rows = payload.get('orders')
        if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(r, dict) for r in rows):
            return None
        return rows

    async def schedules(self, wallet):
        """At most four 100-row pages; failure is distinct from an empty result."""
        wallet = wallet_address(wallet)
        if wallet is None:
            return None, False
        state = self._schedule_passes.setdefault(wallet, {'rows': {}, 'before': None})
        rows, before = state['rows'], state['before']
        for _ in range(4):
            params = dict(owner=wallet, limit='100')
            if before:
                params['before'] = before
            payload = await self.swarm._get('/schedules', params=params)
            batch = payload.get('schedules') if isinstance(payload, dict) else None
            if not isinstance(batch, list) or len(batch) > 100 or any(not isinstance(r, dict) or wallet_address(r.get('owner')) != wallet or parse_job_id(r.get('id')) is None for r in batch):
                return (list(rows.values()) if rows else None), False
            rows.update((r['id'], r) for r in batch)
            if len(batch) < 100:
                self._schedule_passes.pop(wallet, None)
                return list(rows.values()), True
            cursor = batch[-1].get('createdAt')
            if not isinstance(cursor, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+Z', cursor) or before and cursor >= before:
                break
            before = cursor
            state['before'] = before
        return list(rows.values()), False

    async def detail(self, kind, identity):
        if parse_job_id(identity) is None:
            return None
        methods = {'job': 'fetch_job', 'workflow': 'fetch_workflow', 'launch': 'fetch_launch', 'oracle': 'fetch_oracle_detail'}
        if kind in methods:
            payload = await getattr(self.swarm, methods[kind])(identity)
        elif kind in ('schedule', 'site'):
            payload = await self.swarm._get(f'/{kind}s/{identity}')
        else:
            return None
        return payload if isinstance(payload, dict) and payload.get('id', identity) == identity else None
