"""npm latest reads use captured responses and an injected, socket-free transport."""
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.npm_registry_client import NpmRegistryClient, RUNTIME_PACKAGES

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'surf' / 'npm'


@pytest.mark.parametrize('runtime', ['claude', 'codex'])
async def test_latest_reads_only_allowlisted_package_version(runtime):
    payload = json.loads((FIXTURES / f'{runtime}_latest.json').read_text())
    calls = []
    def respond(request):
        calls.append(str(request.url))
        assert str(request.url) == f'https://registry.npmjs.org/{RUNTIME_PACKAGES[runtime]}/latest'
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = NpmRegistryClient(http_client=http)
        assert await client.fetch_latest(runtime) == payload['version']
        await client.close()
        assert not http.is_closed
    assert len(calls) == 1


@pytest.mark.parametrize('status,body', [(404, '{}'), (500, '{}'), (200, '<html>oops'), (200, '[]')])
async def test_bad_registry_response_is_unknown_without_retry(status, body):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert await NpmRegistryClient(http_client=http).fetch_latest('claude') is None
    assert len(calls) == 1


@pytest.mark.parametrize('version', [None, True, 4, '[/x]', '1.2', 'v1.2.3', '1.2.3\n',
    '1.2.3 (Claude Code)', 'codex-cli 1.2.3', '9' * 65, '1.2.3-alpha.01'])
async def test_hostile_registry_version_is_unknown(version):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'version':version}))) as http:
        assert await NpmRegistryClient(http_client=http).fetch_latest('claude') is None


async def test_unknown_runtime_cannot_form_a_registry_request():
    def dead(request):
        raise AssertionError('No request is permitted')
    async with httpx.AsyncClient(transport=httpx.MockTransport(dead)) as http:
        client = NpmRegistryClient(http_client=http)
        for runtime in (None, 'unknown', '../secret', 'claude?x=1', []):
            assert await client.fetch_latest(runtime) is None


async def test_timeout_is_unknown_without_retry():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('offline')
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        assert await NpmRegistryClient(http_client=http).fetch_latest('codex') is None
    assert len(calls) == 1
