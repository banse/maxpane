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


# ---------------------------------------------------------------------------
# WP1a (docs/surf_agent_seats_plan.md): ``fetch_seat`` reads GET /seats/{token}.
# A 404 whose body is ``unknown_seat`` is an answer (a real negative, never
# paired); any other 404 is a failed read and rotates like every other error.
# ---------------------------------------------------------------------------

from types import MappingProxyType  # noqa: E402

from maxpane_dashboard.data.surf_swarm_client import UNKNOWN_SEAT  # noqa: E402
from tests.surf_swarm_fixtures import swarm_seat_capture  # noqa: E402


def _recording(seen: list[httpx.Request], respond):
    def handler(request):
        seen.append(request)
        return respond(request)
    return handler


async def test_fetch_seat_200_returns_the_seat_dict_from_the_one_path():
    body = swarm_seat_capture("seat_420")
    seen: list[httpx.Request] = []

    async with _client(_recording(seen, lambda r: httpx.Response(200, json=body))) as client:
        seat = await client.fetch_seat(420)

    # The host serves ``tokenId`` as a decimal string ("420"), not an int.
    assert seat == body and seat["tokenId"] == "420"
    assert [r.url.path for r in seen] == ["/seats/420"]
    assert _hosts(seen) == [FIRST_HOST]
    assert seen[0].method == "GET" and seen[0].url.query == b""


async def test_fetch_seat_unknown_seat_404_is_the_normalised_answer_and_does_not_rotate():
    body = swarm_seat_capture("unknown_seat_404")
    assert body["error"] == "unknown_seat", "the committed fixture is the measured 404 body"
    seen: list[httpx.Request] = []

    async with _client(_recording(seen, lambda r: httpx.Response(404, json=body))) as client:
        result = await client.fetch_seat(99999)

    assert result == {"error": "unknown_seat"}
    assert result is not None, "a real negative is distinct from a failed read"
    assert _hosts(seen) == [FIRST_HOST], "unknown_seat is an answer: no second host is asked"


async def test_fetch_seat_unknown_seat_result_is_a_fresh_copy_and_the_constant_is_immutable():
    body = swarm_seat_capture("unknown_seat_404")

    async with _client(lambda r: httpx.Response(404, json=body)) as client:
        first = await client.fetch_seat(7)
        first["error"] = "tampered"
        first["extra"] = 1
        second = await client.fetch_seat(7)

    assert second == {"error": "unknown_seat"}, "a caller's edit never leaks into the next result"
    assert second is not first
    assert isinstance(UNKNOWN_SEAT, MappingProxyType)
    assert dict(UNKNOWN_SEAT) == {"error": "unknown_seat"}
    with pytest.raises(TypeError):
        UNKNOWN_SEAT["error"] = "x"  # type: ignore[index]
    assert second == UNKNOWN_SEAT


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(lambda: httpx.Response(404, text="<html><body>Not Found</body></html>"), id="html-404"),
        pytest.param(lambda: httpx.Response(404, json={"error": "not_found"}), id="other-error-404"),
        pytest.param(lambda: httpx.Response(404, json=["unknown_seat"]), id="list-404"),
        pytest.param(lambda: httpx.Response(404, json={"detail": "no device has paired with that token"}),
                     id="no-error-key-404"),
    ],
)
async def test_fetch_seat_a_removed_route_404_rotates_and_is_none_never_never_paired(response):
    seen: list[httpx.Request] = []

    async with _client(_recording(seen, lambda r: response())) as client:
        assert await client.fetch_seat(420) is None

    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST], "a non-unknown_seat 404 rotates through the pool"


async def test_fetch_seat_a_removed_route_on_host_one_is_answered_by_host_two():
    body = swarm_seat_capture("seat_516")
    seen: list[httpx.Request] = []

    def respond(request):
        if request.url.host == FIRST_HOST:
            return httpx.Response(404, text="Cannot GET /seats/516")
        return httpx.Response(200, json=body)

    async with _client(_recording(seen, respond)) as client:
        assert await client.fetch_seat(516) == body
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_seat_400_invalid_request_rotates_then_is_none():
    body = swarm_seat_capture("invalid_request_400")
    seen: list[httpx.Request] = []

    async with _client(_recording(seen, lambda r: httpx.Response(400, json=body))) as client:
        assert await client.fetch_seat(1) is None
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_seat_400_on_host_one_rotates_to_host_two():
    body = swarm_seat_capture("seat_1649")
    seen: list[httpx.Request] = []

    def respond(request):
        if request.url.host == FIRST_HOST:
            return httpx.Response(400, json=swarm_seat_capture("invalid_request_400"))
        return httpx.Response(200, json=body)

    async with _client(_recording(seen, respond)) as client:
        assert await client.fetch_seat(1649) == body
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


@pytest.mark.parametrize(
    "respond",
    [
        pytest.param(lambda r: httpx.Response(500, json={"error": "internal_error"}), id="500"),
        pytest.param(lambda r: httpx.Response(302, headers={"Location": "https://evil.example/"}), id="302"),
        pytest.param(lambda r: httpx.Response(200, text="<html>maintenance</html>"), id="non-json-200"),
    ],
)
async def test_fetch_seat_other_non_200_or_non_json_rotates_then_is_none(respond):
    seen: list[httpx.Request] = []

    async with _client(_recording(seen, respond)) as client:
        assert await client.fetch_seat(0) is None
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_seat_a_json_200_that_is_not_an_object_is_none():
    """Parsed JSON is a read: like ``fetch_version``, a non-object body is ``None``, not rotated."""
    seen: list[httpx.Request] = []
    body = [swarm_seat_capture("seat_0")]

    async with _client(_recording(seen, lambda r: httpx.Response(200, json=body))) as client:
        assert await client.fetch_seat(0) is None
    assert _hosts(seen) == [FIRST_HOST]


async def test_fetch_seat_transport_error_rotates_then_is_none():
    seen: list[httpx.Request] = []

    def respond(request):
        raise httpx.ConnectError("refused", request=request)

    async with _client(_recording(seen, respond)) as client:
        assert await client.fetch_seat(420) is None
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_seat_unknown_seat_on_host_two_after_host_one_failed_is_the_answer():
    seen: list[httpx.Request] = []

    def respond(request):
        if request.url.host == FIRST_HOST:
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(404, json=swarm_seat_capture("unknown_seat_404"))

    async with _client(_recording(seen, respond)) as client:
        assert await client.fetch_seat(5) == {"error": "unknown_seat"}
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]


async def test_fetch_seat_paces_once_per_request_including_the_unknown_seat_answer():
    delays: list[float] = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    def respond(request):
        if request.url.path == "/seats/420":
            return httpx.Response(200, json=swarm_seat_capture("seat_420"))
        return httpx.Response(404, json=swarm_seat_capture("unknown_seat_404"))

    async with _client(respond, sleep=fake_sleep) as client:
        await client.fetch_seat(420)
        await client.fetch_seat(99999)

    assert len(delays) == 2 and all(d > 0 for d in delays)


async def test_other_getters_still_rotate_on_an_unknown_seat_shaped_404():
    """The 404-answer path is opt-in: ``fetch_job`` keeps treating any 404 as a failed read."""
    seen: list[httpx.Request] = []
    body = swarm_seat_capture("unknown_seat_404")

    async with _client(_recording(seen, lambda r: httpx.Response(404, json=body))) as client:
        assert await client.fetch_job("abc") is None
        assert await client.fetch_health() is None
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST, FIRST_HOST, SECOND_HOST]


@pytest.mark.parametrize(
    "token",
    [True, False, -1, -420, "420", "1?x", "", None, 4.0, 420.5, b"420"],
    ids=repr,
)
async def test_fetch_seat_refuses_a_token_that_is_not_a_non_negative_int_with_zero_requests(token):
    seen: list[httpx.Request] = []

    def handler(request):  # pragma: no cover - must never run
        seen.append(request)
        return httpx.Response(200, json=swarm_seat_capture("seat_1649"))

    async with _client(handler) as client:
        assert await client.fetch_seat(token) is None  # type: ignore[arg-type]
    assert seen == [], f"{token!r} issued a request"


async def test_fetch_seat_zero_is_a_valid_token():
    seen: list[httpx.Request] = []
    body = swarm_seat_capture("seat_0")

    async with _client(_recording(seen, lambda r: httpx.Response(200, json=body))) as client:
        assert await client.fetch_seat(0) == body
    assert [r.url.path for r in seen] == ["/seats/0"]


async def test_fetch_seat_never_reaches_the_network_under_the_raising_transport():
    async with _client(_no_network) as client:
        with pytest.raises(AssertionError):
            await client.fetch_seat(420)


@pytest.mark.parametrize('route', ['workers', 'contributors'])
async def test_board_reads_use_canned_keyless_rotating_paced_transport(route):
    from tests.surf_swarm_fixtures import swarm_capture_v3

    seen, delays = [], []
    payload = swarm_capture_v3(route)

    async def sleep(delay):
        delays.append(delay)

    def handler(request):
        seen.append(request)
        assert request.url.path == f'/{route}'
        assert request.method == 'GET'
        assert not {'authorization', 'cookie', 'x-api-key'} & set(request.headers)
        return httpx.Response(503) if len(seen) == 1 else httpx.Response(200, json=payload)

    async with _client(handler, sleep=sleep) as client:
        assert await getattr(client, f'fetch_{route}')() == payload
    assert _hosts(seen) == [FIRST_HOST, SECOND_HOST]
    assert len(delays) == 1 and delays[0] > 0
    async with _client(_no_network, sleep=sleep) as client:
        with pytest.raises(AssertionError):
            await getattr(client, f'fetch_{route}')()


@pytest.mark.parametrize('route', ['workers', 'contributors'])
@pytest.mark.parametrize('body', [None, [], 'garbage', 0])
async def test_board_fetch_rejects_non_dict_body(route, body):
    async with _client(lambda request: httpx.Response(200, json=body)) as client:
        assert await getattr(client, f'fetch_{route}')() is None


async def test_oracle_query_and_detail_use_exact_urls_with_rotation():
    job = '00000000-0000-4000-8000-000000000001'
    calls = []
    before = '2026-09-23T20:00:00.123Z'
    query = 'limit=200&before=2026-09-23T20%3A00%3A00.123Z'
    def handler(request):
        calls.append(str(request.url))
        assert str(request.url) in (
            f'https://one.test/oracle/requests?{query}', f'https://two.test/oracle/requests?{query}',
            f'https://one.test/oracle/requests/{job}',
        )
        assert request.method == 'GET'
        if request.url.host == 'one.test' and request.url.path == '/oracle/requests':
            return httpx.Response(503)
        return httpx.Response(200, json={'requests': []} if request.url.query else {'id': job})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmClient(http_client=http, hosts=('https://one.test', 'https://two.test'), inter_call_delay=0)
        assert await client.fetch_oracle_requests(limit=200, before=before) == []
        assert await client.fetch_oracle_request(job) == {'id': job}
        assert len(calls) == 3


@pytest.mark.parametrize('limit,before', [(True,None),(0,None),(501,None),('200',None),(200,''),(200,'yesterday'),(200,True),(200,'2026-09-23T20:00:00Z\n')])
async def test_oracle_invalid_parameters_make_no_request(limit,before):
    def handler(request):
        raise AssertionError(f'unexpected request: {request.url}')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client=SwarmClient(http_client=http,inter_call_delay=0)
        assert await client.fetch_oracle_requests(limit=limit,before=before) is None
        assert await client.fetch_oracle_request('../bad') is None


@pytest.mark.parametrize('status,body,expected', [(200,{'requests':[]},[]),(200,{},None),(400,{'error':'invalid_id'},None),(404,{},None)])
async def test_oracle_empty_is_distinct_from_failed_read(status,body,expected):
    job='00000000-0000-4000-8000-000000000001'
    def handler(request):
        assert request.url.path in ('/oracle/requests','/oracle/requests/'+job)
        return httpx.Response(status,json=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client=SwarmClient(http_client=http,inter_call_delay=0)
        assert await client.fetch_oracle_requests(limit=500) == expected
        if status != 200:
            assert await client.fetch_oracle_request(job) is None
