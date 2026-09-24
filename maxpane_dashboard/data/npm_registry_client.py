"""Bounded, keyless npm latest checks for the two supported LLM runtimes."""
from __future__ import annotations

import httpx

from maxpane_dashboard.analytics.surf_swarm_signals import runtime_semver
from maxpane_dashboard.data.rpc_common import OwnedHttpClient

RUNTIME_PACKAGES = {'claude': '@anthropic-ai/claude-code', 'codex': '@openai/codex'}
REGISTRY = 'https://registry.npmjs.org'


def npm_version(value: object) -> str | None:
    """Only the plain registry form, never a CLI banner or unbounded string."""
    if (not isinstance(value, str) or len(value) > 64 or ' ' in value
            or runtime_semver('claude', value) is None):
        return None
    return value


class NpmRegistryClient(OwnedHttpClient):
    def __init__(self, *, http_client: httpx.AsyncClient | None = None):
        self._client = http_client if http_client is not None else httpx.AsyncClient(timeout=5.0)
        self._owns_client = http_client is None

    async def fetch_latest(self, runtime_id: object) -> str | None:
        if not isinstance(runtime_id, str) or runtime_id not in RUNTIME_PACKAGES:
            return None
        try:
            response = await self._client.get(f'{REGISTRY}/{RUNTIME_PACKAGES[runtime_id]}/latest', timeout=5.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        return npm_version(payload.get('version')) if isinstance(payload, dict) else None
