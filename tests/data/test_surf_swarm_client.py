import httpx
import pytest

from maxpane_dashboard.data.surf_swarm_client import SWARM_API, SwarmClient
from tests.surf_swarm_fixtures import swarm_capture_v2, swarm_details_v2

#: The one executing job of the v2 corpus that has a detail (nodes) on file.
_EXECUTING_DETAIL = "f046299c-d94e-4760-9e3c-c1e2d3a1a3b2"


def _client(handler, **kw) -> SwarmClient:
    return SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


def _no_network(request):  # pragma: no cover - must never run
    raise AssertionError(f"a test reached the network: {request.url}")


async def test_every_read_is_a_keyless_get_against_the_pools_first_host():
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

    # Construction-level assertion: the client built by the module must not carry auth headers
    client = SwarmClient()
    assert "Authorization" not in client._client.headers
    assert "X-Api-Key" not in client._client.headers
    assert client._client.headers.get("Accept") == "application/json"
    await client.close()


async def test_the_owned_client_never_follows_a_redirect_off_the_pool():
    """WP7: the client the module builds for itself has redirects OFF -- a
    ``Location`` header names a host nobody allowlisted. Read off the
    constructed ``httpx.AsyncClient``, not off a mocked transport (a
    ``MockTransport`` never redirects, so a transport-level test could not
    fail); and a 3xx from the first host is answered by rotating to the
    second pool entry, not by following it anywhere."""
    owned = SwarmClient()
    assert owned._client.follow_redirects is False
    await owned.close()

    seen: list[str] = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == httpx.URL(SWARM_API).host:
            return httpx.Response(302, headers={"Location": "https://evil.example/health"})
        return httpx.Response(200, json={"status": "ok"})

    async with _client(handler) as client:
        assert await client.fetch_health() == {"status": "ok"}
    assert "evil.example" not in seen
    assert seen[0] == httpx.URL(SWARM_API).host and len(seen) == 2


async def test_jobs_and_launches_and_sites_unwrap_their_envelopes():
    def handler(request):
        name = {"/jobs": "jobs", "/launches": "launches", "/sites": "sites"}[request.url.path]
        return httpx.Response(200, json=swarm_capture_v2(name))

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
        return httpx.Response(200, json=swarm_details_v2()[_EXECUTING_DETAIL])

    async with _client(handler) as client:
        job = await client.fetch_job("4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6")

    assert job["nodes"], "the detail must carry its subtasks"


async def test_a_404_on_one_job_is_none_not_a_raise():
    async with _client(lambda request: httpx.Response(404, json={"error": "gone"})) as client:
        assert await client.fetch_job("missing") is None


async def test_a_500_is_none_and_never_a_zero():
    async with _client(lambda request: httpx.Response(500, json={"error": "internal_error", "detail": "Failed query"})) as client:
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


# ---------------------------------------------------------------------------
# v2 (plan §0 R1, WP2): the host is a two-entry pool.  A failure rotates to the
# next host for *that request only*; no host is ever dropped or reordered.
# ---------------------------------------------------------------------------

from maxpane_dashboard.data.surf_swarm_client import SWARM_API_HOSTS  # noqa: E402
from tests.surf_swarm_fixtures import swarm_capture_v2  # noqa: E402

FIRST_HOST, SECOND_HOST = (httpx.URL(h).host for h in SWARM_API_HOSTS[:2])


def _hosts(seen: list[httpx.Request]) -> list[str]:
    return [request.url.host for request in seen]


async def test_a_503_on_the_first_host_rotates_to_the_second_for_that_request_only():
    seen: list[httpx.Request] = []
    body = swarm_capture_v2("health")

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(200, json=body)

    async with _client(handler) as client:
        first = await client.fetch_health()
        second = await client.fetch_health()

    assert first == body, "the second host's 200 body is the answer"
    assert second == body
    # Rotation is per request: the second request starts at the first host again.
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST, FIRST_HOST]
    assert {request.url.path for request in seen} == {"/health"}, "the same path is asked of every host"


async def test_a_non_json_200_on_the_first_host_rotates_the_same_way():
    seen: list[httpx.Request] = []
    body = swarm_capture_v2("jobs")

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(200, text="<html>maintenance</html>")
        return httpx.Response(200, json=body)

    async with _client(handler) as client:
        jobs = await client.fetch_jobs()
        again = await client.fetch_jobs()

    assert jobs == body["jobs"]
    assert again == body["jobs"]
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST, FIRST_HOST]


async def test_both_hosts_failing_is_none_after_exactly_two_requests():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(502, text="bad gateway")

    async with _client(handler) as client:
        assert await client.fetch_launches() is None

    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST], "every host once, no third attempt"


async def test_a_connect_error_on_host_one_rotates_and_on_both_is_none():
    seen: list[httpx.Request] = []
    body = swarm_capture_v2("sites")

    def flaky_first(request):
        seen.append(request)
        if request.url.host == FIRST_HOST:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=body)

    async with _client(flaky_first) as client:
        assert await client.fetch_sites() == body["sites"]
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]

    seen.clear()

    def dead_everywhere(request):
        seen.append(request)
        raise httpx.ConnectError("refused", request=request)

    async with _client(dead_everywhere) as client:
        assert await client.fetch_sites() is None
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_skills_unwraps_its_envelope_and_a_missing_key_is_none_not_empty():
    body = swarm_capture_v2("skills")

    async with _client(lambda request: httpx.Response(200, json=body)) as client:
        skills = await client.fetch_skills()
    assert skills == body["skills"]
    assert isinstance(skills, list) and skills[0]["id"], "the v2 corpus carries skill ids"

    async with _client(lambda request: httpx.Response(200, json={"count": 3})) as client:
        assert await client.fetch_skills() is None

    async with _client(lambda request: httpx.Response(200, json={"skills": {"not": "a list"}})) as client:
        assert await client.fetch_skills() is None


async def test_fetch_version_returns_the_dict_and_a_list_body_is_none():
    body = swarm_capture_v2("version")

    async with _client(lambda request: httpx.Response(200, json=body)) as client:
        version = await client.fetch_version()
    assert version == body
    assert isinstance(version["commit"], str) and len(version["commit"]) == 40

    async with _client(lambda request: httpx.Response(200, json=[body])) as client:
        assert await client.fetch_version() is None


async def test_the_skills_and_version_paths_are_the_documented_ones():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"skills": []})

    async with _client(handler) as client:
        await client.fetch_skills()
        await client.fetch_version()

    assert [request.url.path for request in seen] == ["/skills", "/version"]


async def test_the_jobs_request_carries_no_query_and_no_key_shaped_header():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=swarm_capture_v2("jobs"))

    async with _client(handler) as client:
        await client.fetch_jobs()

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/jobs"
    assert request.url.query == b"", "no filter, no page: the upstream ignores parameters (R3/R4)"
    assert "?" not in str(request.url)
    lowered = {k.lower() for k in request.headers}
    assert not lowered & {"authorization", "x-api-key", "api-key", "x-token", "cookie"}
    # Nothing beyond the transport's own plumbing and Accept: no header may
    # carry a key-shaped value.  (The Accept header itself is set on the
    # client the module builds, asserted construction-level above.)
    assert lowered <= {"host", "accept", "accept-encoding", "connection", "user-agent"}, lowered


async def test_a_path_with_a_query_string_is_refused_before_any_request():
    seen: list[httpx.Request] = []

    def handler(request):  # pragma: no cover - must never run
        seen.append(request)
        return httpx.Response(200, json={})

    async with _client(handler) as client:
        with pytest.raises(ValueError):
            await client._get("/jobs?limit=50")

    assert seen == []


@pytest.mark.parametrize("job_id", ["abc?limit=1", "a/b", "x#y", "", "with space", 42, None])
async def test_fetch_job_refuses_an_id_that_is_no_path_segment_and_returns_none(job_id):
    """WP2 review: the public getter keeps the None contract ``_get``'s raise breaks."""
    async with _client(_no_network) as client:
        assert await client.fetch_job(job_id) is None


async def test_fetch_job_with_a_plain_id_still_asks_the_host():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=swarm_details_v2()[_EXECUTING_DETAIL])

    async with _client(handler) as client:
        assert await client.fetch_job("1c47e615-c14e-4eac-bec5-6b0229c18e78") is not None
    assert [r.url.path for r in seen] == ["/jobs/1c47e615-c14e-4eac-bec5-6b0229c18e78"]


async def test_pacing_is_once_per_request_even_when_the_request_rotated():
    delays: list[float] = []
    seen: list[httpx.Request] = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    def handler(request):
        seen.append(request)
        if request.url.host == FIRST_HOST:
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(200, json=swarm_capture_v2("health"))

    async with _client(handler, sleep=fake_sleep) as client:
        await client.fetch_health()
        await client.fetch_health()

    assert len(seen) == 4, "two requests, each rotated once"
    assert len(delays) == 2, "one pacing sleep per request, not per host attempt"
    assert all(d > 0 for d in delays)


def test_the_host_pool_is_at_least_two_https_urls_none_on_the_dead_list():
    assert isinstance(SWARM_API_HOSTS, tuple)
    assert len(SWARM_API_HOSTS) >= 2
    assert len(set(SWARM_API_HOSTS)) == len(SWARM_API_HOSTS), "no duplicate host"
    dead = ("llamarpc", "ankr", "cloudflare-eth", "reservoir", "omniatech", "blockpi", "merkle", "flashbots")
    for host in SWARM_API_HOSTS:
        assert host.startswith("https://"), host
        assert not host.endswith("/"), host
        assert "?" not in host and "key" not in host.lower(), host
        for fragment in dead:
            assert fragment not in host, f"{host} is on CLAUDE.md's dead list ({fragment})"
    assert SWARM_API == SWARM_API_HOSTS[0], "the old name survives as the first host"


async def test_a_deprecated_base_url_becomes_a_one_host_pool():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(503, text="down")

    client = SwarmClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="https://example.invalid/",
    )
    async with client:
        assert await client.fetch_health() is None

    assert _hosts(seen) == ["example.invalid"], "one host, asked once, no rotation into the default pool"
