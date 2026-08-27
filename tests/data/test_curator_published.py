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


#: The version the committed ``versions.json`` names as published, and a
#: :class:`PublishedVersion` that agrees with the two bulk fixtures.  Read from
#: the fixture rather than re-typed: a hand-typed hash beside a refreshed
#: capture would make every cross-check test pass for the wrong reason.
PUBLISHED_ID = _load("versions.json")["published_version"]


def _fixture_version():
    entry = next(
        e for e in _load("versions.json")["versions"] if e["id"] == PUBLISHED_ID
    )
    return pub.PublishedVersion(
        version_id=PUBLISHED_ID,
        content_hash=entry["content_hash"],
        detector_version=entry.get("detector_version"),
        rule_set=entry.get("rule_set"),
        rules_sha256=entry.get("rules_sha256"),
        snapshot_block=entry.get("snapshot_block"),
        cluster_count=entry.get("cluster_count"),
        status_counts=entry.get("status_counts") or {},
    )


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


async def test_a_non_dict_overview_body_is_not_mistaken_for_an_analysis():
    """The guard lives in the shared helper, so this asserts at the CALL SITE.

    Both fetchers funnel through `_get_json` today; a later inline parse or a
    shape check reordered ahead of that delegation would bypass it, and only a
    test that enters through this function would notice.
    """
    version = pub.PublishedVersion(
        version_id="v", content_hash="h", detector_version="0.2.0",
        rule_set="v2h", rules_sha256="deadbeef", snapshot_block=1,
        cluster_count=1, status_counts={"clean": 1},
    )
    transport = _ok({"/overview": [], "/list/export": _load("export_trimmed.json")})
    got = await pub.fetch_published_analysis(version, transport=transport)
    assert got is None


async def test_a_non_dict_export_body_is_not_mistaken_for_an_analysis():
    """Same call-site guard, the other bulk read.  A non-dict `/list/export`
    body must not reach `export.get("rows")` -- the overview here is a real,
    valid body, so only the export side can be at fault."""
    version = pub.PublishedVersion(
        version_id="v", content_hash="h", detector_version="0.2.0",
        rule_set="v2h", rules_sha256="deadbeef", snapshot_block=1,
        cluster_count=1, status_counts={"clean": 1},
    )
    transport = _ok({"/overview": _load("overview_trimmed.json"), "/list/export": []})
    got = await pub.fetch_published_analysis(version, transport=transport)
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
    """...and the export names the population it wants rather than taking four
    server-side defaults.

    PRD §3.3 specifies `/list/export?q=&link=all&evidence=all&preset=none`, and
    `scripts/capture_published_analysis.py` -- which produced these fixtures --
    sends exactly that.  Production sent `version` alone until 2026-08-27 and
    depended on defaults it never asked for and never read back.  The live
    default happens to be `link=all`; the site's own CLEAN view is
    `link=unlinked`, and that subset renders as a CONFIDENT clean list, not a
    degraded one.  `MockTransport` ignores the query string, so nothing but
    reading the URL can see this.
    """
    seen = []

    def handler(request):
        seen.append(request.url)
        if "/overview" in str(request.url):
            return httpx.Response(200, json=_load("overview_trimmed.json"))
        return httpx.Response(200, json=_load("export_trimmed.json"))

    await pub.fetch_published_analysis(_fixture_version(), transport=_transport(handler))
    assert seen and all(PUBLISHED_ID in str(url) for url in seen)
    export_url = next(url for url in seen if "/list/export" in str(url))
    assert dict(export_url.params) == {
        "q": "", "link": "all", "evidence": "all", "preset": "none",
        "version": PUBLISHED_ID,
    }


async def test_an_export_filtered_to_something_else_is_refused():
    """The four parameters are only half the fix: the answer says what it
    actually applied, and that echo is the only way to tell a full population
    from a subset.  `link: "unlinked"` over these same fixture rows renders 82
    of 82 wallets with an empty flag cell -- the confident clean -- beside a
    panel reporting 7 linked groups.  Nothing degrades and nothing marks stale,
    so refusing the payload is the only representable answer.
    """
    export = _load("export_trimmed.json")
    export["filters"] = {**export["filters"], "link": "unlinked"}
    transport = _ok({"/overview": _load("overview_trimmed.json"), "/list/export": export})
    assert await pub.fetch_published_analysis(_fixture_version(), transport=transport) is None


async def test_an_export_echoing_the_asked_for_filters_is_accepted():
    """Guard on the test above: the refusal must key off the ECHO, not off the
    presence of a `filters` block.  The unmodified fixture carries the very
    echo the request asks for, so it has to survive."""
    transport = _ok({
        "/overview": _load("overview_trimmed.json"),
        "/list/export": _load("export_trimmed.json"),
    })
    got = await pub.fetch_published_analysis(_fixture_version(), transport=transport)
    assert got is not None and got.rows


@pytest.mark.parametrize("route,field", [
    ("/overview", "version"), ("/list/export", "analysis_version"),
])
async def test_a_bulk_body_naming_another_content_hash_is_refused(route, field):
    """Both bulk responses self-identify, and until 2026-08-27 neither was
    compared against the `/versions` entry that named them.

    A republish landing between the version check and either bulk read -- or a
    CDN serving one stale half -- stores version V's provenance over another
    analysis's rows, in an archive directory named for V.  Recomputing the
    publisher's digest is out of reach; agreement across three independently
    served responses is not.
    """
    bodies = {
        "/overview": _load("overview_trimmed.json"),
        "/list/export": _load("export_trimmed.json"),
    }
    bodies[route][field] = {**bodies[route][field], "content_hash": "0" * 64}
    got = await pub.fetch_published_analysis(_fixture_version(), transport=_ok(bodies))
    assert got is None


async def test_a_transport_failure_degrades_to_none():
    """An arbitrary exception raised inside a transport (here a bare
    AssertionError, not an httpx error) is still caught by `_get_json`'s broad
    except-and-degrade -- NOT a socket-avoidance guarantee: that one is
    `test_every_request_goes_through_the_injected_transport`, below."""
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


# ---------------------------------------------------------------------------
# version_label -- zero coverage at ship time (T2 fix round 2, deferred to
# T8, which is the task that actually renders the label).  Pure formatting,
# no transport needed.
# ---------------------------------------------------------------------------


def _version(**over) -> pub.PublishedVersion:
    fields = {
        "version_id": "2026-08-25-sybilkit-0.2.0",
        "content_hash": "h",
        "detector_version": "0.2.0",
        "rule_set": "v2h",
        "rules_sha256": "d",
        "snapshot_block": 1,
        "cluster_count": 1,
        "status_counts": {},
    }
    fields.update(over)
    return pub.PublishedVersion(**fields)


def test_version_label_is_none_for_a_missing_version():
    """The caller with no version yet (T8's own manager stamp) hands this
    `None` directly rather than special-casing it first."""
    assert pub.version_label(None) is None


def test_version_label_is_the_detector_and_the_date_stamp():
    """The shape every panel renders: ``"sybilkit 0.2.0 · 2026-08-25"`` --
    the date is the version id's own prefix, split off `-sybilkit-`."""
    assert pub.version_label(_version()) == "sybilkit 0.2.0 · 2026-08-25"


def test_version_label_drops_the_sybilkit_half_with_no_detector_version():
    """`detector_version` missing (an older or partial payload) costs only
    its own half of the label -- the date stamp still renders alone."""
    version = _version(detector_version=None)
    assert pub.version_label(version) == "2026-08-25"


def test_version_label_uses_the_whole_id_with_no_sybilkit_marker():
    """A `version_id` that never contains `-sybilkit-` splits to itself
    whole, rather than silently losing the date half."""
    version = _version(version_id="v1", detector_version="0.2.0")
    assert pub.version_label(version) == "sybilkit 0.2.0 · v1"


def test_version_label_is_none_when_both_halves_are_missing():
    """Neither half is fabricated: a version with no id and no detector
    string renders nothing rather than a lone middle dot."""
    version = _version(version_id="", detector_version=None)
    assert pub.version_label(version) is None
