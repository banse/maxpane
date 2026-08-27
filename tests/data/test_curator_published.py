import json
import pathlib

import httpx

from maxpane_dashboard.data import curator_published as pub

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures/curator/published"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _transport(handler):
    return httpx.MockTransport(handler)


def _ok(payloads):
    def handler(request):
        for fragment, body in payloads.items():
            if fragment in str(request.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"detail": "no"})
    return _transport(handler)


class _ExplodingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise AssertionError(f"a test opened the network: {request.url}")


class _CountingExplodingTransport(httpx.AsyncBaseTransport):
    """Raises like a dead network, and records that it was asked to.

    The count is the load-bearing half.  Asserting only `is None` passes on a
    machine with no network even if the module ignored this transport entirely
    and tried the real endpoint -- the failure would be swallowed the same way.
    """
    def __init__(self):
        self.calls = 0

    async def handle_async_request(self, request):
        self.calls += 1
        raise httpx.ConnectError("no network in tests")


async def test_with_no_client_and_no_transport_nothing_is_fetched():
    assert await pub.fetch_published_version() is None


async def test_the_version_is_the_one_the_service_calls_published():
    transport = _ok({"/versions": _load("versions.json")})
    version = await pub.fetch_published_version(transport=transport)
    assert version.version_id == _load("versions.json")["published_version"]
    assert version.content_hash
    assert version.status_counts["clean"] > 0


async def test_a_versions_body_with_no_matching_entry_is_none():
    body = dict(_load("versions.json"))
    body["published_version"] = "no-such-version"
    assert await pub.fetch_published_version(transport=_ok({"/versions": body})) is None


async def test_a_top_level_json_array_is_not_mistaken_for_a_versions_body():
    """A top-level JSON array is valid JSON, arrives with the right content
    type, and sits under every size cap -- nothing already in place stops it.
    Without a container-type guard, `body.get("published_version")` crashes
    with `AttributeError: 'list' object has no attribute 'get'` instead of
    degrading to None."""
    assert await pub.fetch_published_version(transport=_ok({"/versions": []})) is None


async def test_a_top_level_json_string_is_not_mistaken_for_a_versions_body():
    """Same failure mode as the array case, a different top-level JSON type."""
    assert await pub.fetch_published_version(transport=_ok({"/versions": "a string"})) is None


async def test_a_non_dict_element_in_versions_does_not_crash_the_walk():
    """A non-dict element inside `versions[]` must not crash the match search.

    `next()` stops at the first element satisfying the condition, so a bad
    element placed AFTER a real match would never be evaluated by the walk and
    this test would prove nothing.  Placing it first, with a
    `published_version` that matches no real entry, guarantees the walk visits
    it and keeps going -- degrading to None (no match found), never an
    `AttributeError: 'str' object has no attribute 'get'`.
    """
    body = dict(_load("versions.json"))
    body["published_version"] = "no-such-version"
    body["versions"] = ["not-a-dict", *body["versions"]]
    assert await pub.fetch_published_version(transport=_ok({"/versions": body})) is None


async def test_a_failed_overview_returns_none_rather_than_half_an_analysis():
    def handler(request):
        if "/overview" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=_load("export_trimmed.json"))
    version = pub.PublishedVersion(
        version_id="v", content_hash="h", detector_version="0.2.0",
        rule_set="v2h", rules_sha256="deadbeef", snapshot_block=1,
        cluster_count=1, status_counts={"clean": 1},
    )
    got = await pub.fetch_published_analysis(version, transport=_transport(handler))
    assert got is None


async def test_the_real_payload_served_as_html_is_still_refused():
    """The one body that isolates the content-type check.

    Every earlier guard passes by construction -- this IS the live `/versions`
    payload -- so nothing but the content type can reject it.  A spoof that is
    merely malformed proves only that the shape guard works, which is a
    different check that already has its own test.

    The host this reads answers unknown API paths with the SPA's index at HTTP
    200, so "200 and it parses" is not evidence of a payload.
    """
    body = json.dumps(_load("versions.json")).encode()

    def handler(request):
        return httpx.Response(
            200, content=body, headers={"content-type": "text/html; charset=utf-8"}
        )

    assert await pub.fetch_published_version(transport=_transport(handler)) is None


async def test_an_oversized_body_is_never_handed_to_the_parser(monkeypatch):
    """The cap exists to keep a hostile body OUT of the parser, and the return
    value cannot tell you whether it got there -- None either way.  So make the
    parse itself fatal: correct code never reaches it.

    The fixture is loaded (through json.loads) before the patch is applied --
    ``pub.json`` is the real, process-wide ``json`` module, so patching its
    ``loads`` after this point would also blow up this test's own fixture
    loading, not just the code under test.
    """
    versions_body = _load("versions.json")
    monkeypatch.setattr(pub, "MAX_VERSIONS_BYTES", 8)

    def explode(*args, **kwargs):
        raise AssertionError("an oversized body reached the parser")

    monkeypatch.setattr(pub.json, "loads", explode)
    transport = _ok({"/versions": versions_body})
    assert await pub.fetch_published_version(transport=transport) is None


async def test_the_analysis_carries_every_cluster_and_row():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    transport = _ok({"/overview": ov, "/list/export": ex})
    version = await pub.fetch_published_version(
        transport=_ok({"/versions": _load("versions.json")})
    )
    got = await pub.fetch_published_analysis(version, transport=transport)
    assert len(got.clusters) == len(ov["clusters"])
    assert len(got.rows) == len(ex["rows"])
    assert got.totals["population"] == ov["totals"]["population"]


async def test_the_version_travels_in_every_request_query():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "/overview" in str(request.url):
            return httpx.Response(200, json=_load("overview_trimmed.json"))
        return httpx.Response(200, json=_load("export_trimmed.json"))

    version = pub.PublishedVersion(
        version_id="2026-08-25-sybilkit-0.2.0", content_hash="h",
        detector_version="0.2.0", rule_set="v2h", rules_sha256="d",
        snapshot_block=1, cluster_count=1, status_counts={},
    )
    await pub.fetch_published_analysis(version, transport=_transport(handler))
    assert seen and all("2026-08-25-sybilkit-0.2.0" in url for url in seen)


async def test_nothing_in_this_module_opens_a_socket():
    exploding = _ExplodingTransport()
    assert await pub.fetch_published_version(transport=exploding) is None


async def test_every_request_goes_through_the_injected_transport():
    """Stronger than `is None`: `_get_json` swallows every exception into
    None, so a module that ignored `transport` entirely and (on a network-less
    test machine) failed to reach the real endpoint would ALSO return None --
    passing this test for the wrong reason on exactly the machines it runs on.
    Asserting the injected transport was actually invoked is the only way to
    make this environment-independent."""
    transport = _CountingExplodingTransport()
    assert await pub.fetch_published_version(transport=transport) is None
    assert transport.calls == 1, "the module did not use the injected transport"
