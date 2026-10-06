"""Keyless Robinhood state batches for production-launch evidence."""
import httpx
from maxpane_dashboard.data.rpc_common import OwnedHttpClient
from maxpane_dashboard.data.rpc_classify import ETH_ENDPOINT_LIMITATION_FRAGMENTS
from maxpane_dashboard.data.surf_launch_base_client import read_batch
from maxpane_dashboard.analytics.surf_launch_checks import evidence_calls, evidence_results

ROBINHOOD_LAUNCH_RPCS = ('https://rpc.mainnet.chain.robinhood.com', 'https://robinhood-rpc.publicnode.com')
_ENDPOINT_LIMITATION_PATTERNS = ETH_ENDPOINT_LIMITATION_FRAGMENTS

class SwarmRobinhoodClient(OwnedHttpClient):
    def __init__(self, *, http_client=None, rpcs=ROBINHOOD_LAUNCH_RPCS):
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
