import httpx
import pytest

from maxpane_dashboard.data.surf_swarm_client import SWARM_API, SwarmClient
from tests.surf_swarm_fixtures import swarm_capture


def _client(handler, **kw) -> SwarmClient:
    return SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


def _no_network(request):  # pragma: no cover - must never run
    raise AssertionError(f"a test reached the network: {request.url}")


async def test_every_read_is_a_keyless_get_against_the_one_host():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async with _client(handler) as client:
        await client.fetch_health()

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == f"{SWARM_API}/health"
    lowered = {k.lower() for k in request.headers}
    assert not lowered & {"authorization", "x-api-key", "cookie", "token"}


async def test_jobs_and_launches_and_sites_unwrap_their_envelopes():
    def handler(request):
        name = {"/jobs": "jobs", "/launches": "launches", "/sites": "sites"}[request.url.path]
        return httpx.Response(200, json=swarm_capture(name))

    async with _client(handler) as client:
        jobs = await client.fetch_jobs()
        launches = await client.fetch_launches()
        sites = await client.fetch_sites()

    assert isinstance(jobs, list) and jobs[0]["id"]
    assert isinstance(launches, list) and launches[0]["artifacts"]
    assert isinstance(sites, list) and sites[0]["cid"]


async def test_a_job_detail_is_returned_whole():
    def handler(request):
        assert request.url.path.startswith("/jobs/")
        return httpx.Response(200, json=swarm_capture("job_executing"))

    async with _client(handler) as client:
        job = await client.fetch_job("4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6")

    assert job["nodes"], "the detail must carry its subtasks"


async def test_a_404_on_one_job_is_none_not_a_raise():
    async with _client(lambda request: httpx.Response(404, json={"error": "gone"})) as client:
        assert await client.fetch_job("missing") is None


async def test_a_500_is_none_and_never_a_zero():
    async with _client(lambda request: httpx.Response(500, text="boom")) as client:
        assert await client.fetch_jobs() is None
        assert await client.fetch_health() is None


async def test_a_timeout_is_none():
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    async with _client(handler) as client:
        assert await client.fetch_health() is None


async def test_malformed_json_is_none():
    async with _client(lambda request: httpx.Response(200, text="not json")) as client:
        assert await client.fetch_jobs() is None


async def test_an_envelope_without_its_list_is_none_not_an_empty_list():
    async with _client(lambda request: httpx.Response(200, json={"count": 0})) as client:
        assert await client.fetch_jobs() is None


async def test_the_client_paces_its_calls():
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    def handler(request):
        return httpx.Response(200, json={"count": 0, "jobs": []})

    client = _client(handler, sleep=fake_sleep)
    async with client:
        await client.fetch_jobs()
        await client.fetch_jobs()

    assert delays and all(d > 0 for d in delays)


async def test_a_test_client_never_reaches_the_network():
    async with _client(_no_network) as client:
        with pytest.raises(AssertionError):
            await client._get("/health", raw=True)
