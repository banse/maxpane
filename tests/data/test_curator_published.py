import json
import pathlib

import httpx
import pytest

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


async def test_an_html_body_is_not_mistaken_for_json():
    # Unknown API paths on this host return the SPA's index with HTTP 200.
    def handler(request):
        return httpx.Response(200, text="<!doctype html>", headers={"content-type": "text/html"})
    assert await pub.fetch_published_version(transport=_transport(handler)) is None


async def test_an_oversized_body_is_refused_before_it_is_parsed(monkeypatch):
    monkeypatch.setattr(pub, "MAX_VERSIONS_BYTES", 8)
    transport = _ok({"/versions": _load("versions.json")})
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
