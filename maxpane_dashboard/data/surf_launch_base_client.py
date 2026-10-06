"""Keyless Base state batches for production-launch evidence."""
import httpx
from maxpane_dashboard.data.rpc_common import OwnedHttpClient, jsonrpc_payload, ENDPOINT_DEAD_CODES
from maxpane_dashboard.data.rpc_classify import BASE_ENDPOINT_LIMITATION_FRAGMENTS, looks_like_endpoint_limitation
from maxpane_dashboard.analytics.surf_launch_checks import evidence_calls, evidence_results

BASE_LAUNCH_RPCS = ('https://base-rpc.publicnode.com', 'https://mainnet.base.org')
_ENDPOINT_LIMITATION_PATTERNS = BASE_ENDPOINT_LIMITATION_FRAGMENTS

async def read_batch(client, urls, calls, fragments):
    """One attempt per public endpoint; keep independent failed items unknown."""
    if not calls: return []
    payload = [jsonrpc_payload(i + 1, method, params) for i, (method, params) in enumerate(calls)]
    for url in urls:
        try:
            response = await client.post(url, json=payload)
            if response.status_code in ENDPOINT_DEAD_CODES: continue
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, list): continue
            # Limitations belong to the provider; retry the whole batch elsewhere.
            if any(isinstance(item, dict) and item.get('error') and looks_like_endpoint_limitation(item['error'], fragments=fragments, check_codes=False) for item in body): continue
            by_id = {item.get('id'): item.get('result') if not item.get('error') else None for item in body if isinstance(item, dict)}
            return [by_id.get(i + 1) for i in range(len(calls))]
        except (httpx.HTTPError, ValueError, OSError):
            continue
    return None

class SwarmBaseClient(OwnedHttpClient):
    def __init__(self, *, http_client=None, rpcs=BASE_LAUNCH_RPCS):
        self._client = http_client or httpx.AsyncClient(timeout=10, follow_redirects=False)
        self._owns_client = http_client is None
        self._rpcs = tuple(rpcs)

    async def _rpc(self, calls):
        return await read_batch(self._client, self._rpcs, calls, _ENDPOINT_LIMITATION_PATTERNS)

    async def fetch_launch_pool_state(self, calls):
        """Read v4 storage and decimals through the existing state endpoint pool."""
        return await self._rpc(calls) if calls else []

    async def fetch_launch_evidence(self, tx_hashes, addresses):
        keys, calls = evidence_calls(tx_hashes, addresses)
        return evidence_results(keys, await self._rpc(calls))
