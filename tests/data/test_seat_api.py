"""SeatApiClient and its pure helpers — spec §6 API fallback contract.

Every read goes through ``httpx.MockTransport``: no socket, no real ``~/.maxpane``, no file outside
``tests/fixtures/seat/api/``.  Tests reference the module as ``seat_api.<name>`` so a name a later
task has not written yet fails only its own test (``AttributeError``), never the collection.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.analytics import seat_redact
from maxpane_dashboard.data import seat_api
from maxpane_dashboard.data.surf_swarm_client import SWARM_API_HOSTS

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "seat" / "api"
FIRST_HOST, SECOND_HOST = (httpx.URL(h).host for h in SWARM_API_HOSTS[:2])
NOW = 1790394007.0          # 2026-09-26T03:40:07Z — the spec §7 example stamp
JOB = "b1fb1439-7e2a-4d61-9f3b-2c8e5a1d0b47"
HEX = "2ddc5fd34b37812dc93fdb997ab16a5241b9cccdc7757b1c82670b5a3ee25ae8"   # sha256(b"b1fb1439-attempt-1")


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _no_sleep(_seconds: float) -> None:
    return None


def _client(handler, **kw):
    kw.setdefault("now", lambda: NOW)
    kw.setdefault("sleep", _no_sleep)
    return seat_api.SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


def _no_network(request):  # pragma: no cover - must never run
    raise AssertionError(f"a test reached the network: {request.url}")


# ---------------------------------------------------------------------------
# Task 5.1 — constants, ApiResult, tolerant JSON
# ---------------------------------------------------------------------------

def test_control_characters_inside_json_strings_parse_with_strict_false():
    """Spec §6 (tolerant JSON: raw control characters occur inside strings — fill1 FACTS) + §13 step 0."""
    body = b'{"objective": "line\x07 one\x1b]0;evil\x07\ttab", "n": 1}'
    with pytest.raises(ValueError):
        json.loads(body.decode("utf-8"))            # strict json rejects the raw tab: strict=False is load-bearing
    data = seat_api.parse_json_tolerant(body)
    assert data == {"objective": "line one\u241b]0;evil\ttab", "n": 1}   # BEL gone, ESC a glyph, tab kept
    assert "\x07" not in data["objective"] and "\x1b" not in data["objective"]
    assert seat_api.parse_json_tolerant('{"a": "b"}') == {"a": "b"}
    assert seat_api.parse_json_tolerant(b"\xef\xbb\xbf[1]") == [1]       # a UTF-8 BOM is not JSON to json.loads
    with pytest.raises(ValueError):
        seat_api.parse_json_tolerant(b"<html>gateway</html>")
    with pytest.raises(TypeError):
        seat_api.parse_json_tolerant(None)


def test_constants_match_the_contract():
    """Contract §B 'data/seat_api.py' + spec §6 routes table."""
    assert seat_api.API_TIMEOUT_S == 20.0 and seat_api.API_RETRY_ONCE is True
    assert seat_api.SEAT_WORK_ROWS == 60 and seat_api.SEAT_WORK_BACKFILL_ROWS == 1000
    assert seat_api.MAX_REASONS_PER_CYCLE == 2
    assert seat_api.API_HOSTS is SWARM_API_HOSTS and seat_api.API_HOSTS[0] == "https://api.imd.fun"
    assert seat_api.REQUEST_HEADERS == {"Accept": "application/json", "Accept-Encoding": "gzip"}
    contract_reasons = {"runtime_error", "internal_error", "path_violation", "local_build_failed", "clone_failed",
                        "timeout", "cancelled", "schema_invalid"}
    assert contract_reasons <= set(seat_api.FAILURE_REASONS)
    assert {"budget_exhausted", "lease_expired", "runtime_unavailable"} <= set(seat_api.FAILURE_REASONS)  # wire enum, fill1 §4
    assert seat_api.FAILURE_CLASSES == ("infrastructure", "machine", "unclear")
    result = seat_api.ApiResult(ok=False, data=None, status=None, as_of_utc=None, reason="timeout", elapsed_s=0.0, route="/health")
    with pytest.raises(AttributeError):      # frozen dataclass
        result.ok = True                      # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 5.2 — summaries dropped, reasons as enum words
# ---------------------------------------------------------------------------

def test_drop_summaries_removes_every_summary_key_and_copies():
    """Spec §6 traps: recentFailures[].summary and submissions[].summary are raw runtime error text
    (a masked provider key sat in one on 09-25) and are dropped before parsing completes; nothing
    else changes and the input is not mutated."""
    src = {
        "standing": {"recentFailures": [{"reason": "runtime_error", "summary": "401 Unauthorized … sk-svcac********", "jobId": JOB}]},
        "submissions": [{"summary": "wrote outside the task's allowed paths: err.log", "hash": HEX}],
        "nested": [[{"summary": "deep"}]],
        "count": 2,
    }
    frozen = json.dumps(src, sort_keys=True)
    out = seat_api.drop_summaries(src)
    assert out == {
        "standing": {"recentFailures": [{"reason": "runtime_error", "jobId": JOB}]},
        "submissions": [{"hash": HEX}],
        "nested": [[{}]],
        "count": 2,
    }
    assert json.dumps(src, sort_keys=True) == frozen          # a copy, not an in-place edit
    assert '"summary"' not in json.dumps(out)
    assert seat_api.drop_summaries("summary") == "summary" and seat_api.drop_summaries(None) is None


def test_reason_word_is_the_enum_word_or_other():
    """Spec §6 rule 5: failure reasons are shown as the enum word, never a free-text summary."""
    assert seat_api.reason_word("runtime_error") == "runtime_error"
    assert seat_api.reason_word("budget_exhausted") == "budget_exhausted"        # wire enum member (fill1 §4)
    assert seat_api.reason_word("401 Unauthorized: Incorrect API key provided") == "other"
    assert seat_api.reason_word("RUNTIME_ERROR") == "other" and seat_api.reason_word(7) == "other"
    assert seat_api.reason_word(None) is None
    assert seat_api.failure_class_word("machine") == "machine"
    assert seat_api.failure_class_word("weird") == "other" and seat_api.failure_class_word(None) is None


# ---------------------------------------------------------------------------
# Task 5.3 — the API fixture bodies
# ---------------------------------------------------------------------------

API_FIXTURES = (
    "seat7_standing.json", "workers_standing_q0.json", "seat7_work20.json", "seat7_work20_inconsistent.json",
    "seat7_500.json", "job_b1fb1439_submissions.json", "health.json", "services.json", "workers_row.json",
)


def _device_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "deviceKey":
                yield item
            yield from _device_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _device_keys(item)


@pytest.mark.guard
def test_api_fixtures_are_summary_free_redacted_and_registered():
    """Spec §14 fixtures (API bodies: deviceKey scrubbed, summaries removed, control characters stripped)
    + contract §D MANIFEST rules (every file registered with matching sha256/bytes)."""
    entries = json.loads((FIXTURES.parent / "MANIFEST.json").read_text(encoding="utf-8"))["entries"]
    for name in API_FIXTURES:
        raw = (FIXTURES / name).read_bytes()
        text = raw.decode("utf-8")
        assert not seat_redact.CONTROL_RE.search(text), name
        assert not seat_redact.SK_RE.search(text), name
        body = json.loads(text)
        assert '"summary"' not in json.dumps(body), name
        assert all(isinstance(k, str) and k.startswith("scrubbed-") for k in _device_keys(body)), name
        assert seat_redact.find_secret(body, allowed_hex64_fields=frozenset({"submissionHash", "hash", "txHash"})) is None, name
        entry = entries[f"api/{name}"]
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest() and entry["bytes"] == len(raw), name
        assert {"origin", "captured_at", "redactions", "synthetic"} <= set(entry), name
    work = _fixture("seat7_work20.json")
    assert len(work["work"]) == 20 and (work["attempts"], work["accepted"], work["rejected"], work["failed"], work["pending"]) == (288, 244, 5, 11, 28)
    assert _fixture("seat7_work20_inconsistent.json")["attempts"] == 290
    assert _fixture("workers_standing_q0.json")["queue"] is None
    assert _fixture("seat7_500.json")["error"] == "internal_error"


# ---------------------------------------------------------------------------
# Task 5.4 — Postgres timestamps, work rows, the counters identity
# ---------------------------------------------------------------------------

def test_postgres_timestamp_and_verdict_lag():
    """Spec §6 seats row: `acceptedAt` is Postgres text `2026-09-26 03:11:29.985+00`, `submittedAt` ISO `Z`;
    mutation proof 21.  The measured 69 s pending->accepted flip (fill5 §3: submitted 03:10:20, accepted 03:11:29)."""
    p = seat_api._parse_pg_timestamp
    assert p("2026-09-26 03:11:29.985+00") == p("2026-09-26T03:11:29.985Z") == 1790392289.985
    assert p("2026-09-26 05:11:29.985+02") == p("2026-09-26 05:11:29.985+02:00") == p("2026-09-26 05:11:29.985+0200") == 1790392289.985
    assert p("2026-09-26 03:11:29+00") == 1790392289.0 and p("2026-09-26T03:11:29Z") == 1790392289.0
    assert p("not a stamp") is None and p(None) is None and p(1790392289) is None and p("2026-13-01 00:00:00+00") is None
    row = seat_api.normalise_work_row({
        "jobId": "e7a1c2d3-4b5f-4a6e-9c8d-0f1e2d3c4b5a", "objective": "Assess the rebalance", "jobState": "completed",
        "nodeKey": "oracle_assess", "role": "implement", "status": "accepted", "submissionHash": HEX,
        "submittedAt": "2026-09-26T03:10:20.985Z", "acceptedAt": "2026-09-26 03:11:29.985+00", "launch": None,
    })
    assert row["acceptedAt"] == "2026-09-26T03:11:29.985Z" and row["submittedAt"] == "2026-09-26T03:10:20.985Z"
    assert p(row["acceptedAt"]) - p(row["submittedAt"]) == 69.0          # the verdict lag WP7 renders as `+1 m 9 s`
    assert row["submissionHash"] == HEX and row["status"] == "accepted" and tuple(row) == seat_api.WORK_ROW_KEYS
    # an unparseable stamp is None -- never the raw text, never 0; a null hash never joins; odd status words are "unknown"
    assert seat_api.normalise_work_row({"acceptedAt": "yesterday", "status": "Weird", "submissionHash": None})["acceptedAt"] is None
    assert seat_api.normalise_work_row({"status": "Weird"})["status"] == "unknown"
    assert seat_api.normalise_work_row({"status": "ACCEPTED", "submissionHash": 42})["submissionHash"] is None
    assert seat_api.normalise_work_row({})["status"] is None and seat_api.normalise_work_row("junk")["jobId"] is None


def test_inconsistent_counters_are_flagged():
    """Spec §6 seats row + §7 standing block, mutation proof 36: attempts == accepted+rejected+failed+pending
    (417/417 seats, fill5 §3).  A violating body is flagged and never 'repaired' into the sum."""
    good, bad = _fixture("seat7_work20.json"), _fixture("seat7_work20_inconsistent.json")
    assert seat_api.validate_counters(good) is True
    assert seat_api.seat_counters(good) == {"attempts": 288, "accepted": 244, "rejected": 5, "failed": 11, "pending": 28,
                                            "countersInconsistent": False}
    assert seat_api.validate_counters(bad) is False
    flagged = seat_api.seat_counters(bad)
    assert flagged["countersInconsistent"] is True
    assert flagged["attempts"] == 290 and flagged["accepted"] + flagged["rejected"] + flagged["failed"] + flagged["pending"] == 288
    # a missing, string or bool counter can never validate; nothing to check -> None, not False-as-a-verdict
    assert seat_api.validate_counters({**good, "failed": "11"}) is False
    assert seat_api.validate_counters({**good, "failed": True}) is False
    assert seat_api.validate_counters({k: v for k, v in good.items() if k != "pending"}) is False
    assert seat_api.seat_counters({})["countersInconsistent"] is None and seat_api.seat_counters({})["attempts"] is None


def test_work_rows_normalise_to_exact_keys_and_iso_stamps():
    """Every fixture row leaves with exactly WORK_ROW_KEYS and ISO-Z millisecond stamps (or None)."""
    import re
    iso_ms = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
    rows = [seat_api.normalise_work_row(r) for r in _fixture("seat7_work20.json")["work"]]
    assert len(rows) == 20 and all(tuple(r) == seat_api.WORK_ROW_KEYS for r in rows)
    assert all(iso_ms.match(r["submittedAt"]) for r in rows)
    assert all(r["acceptedAt"] is None or iso_ms.match(r["acceptedAt"]) for r in rows)
    assert all(r["status"] in seat_api.WORK_STATUSES for r in rows)
    assert all(r["acceptedAt"] is None for r in rows if r["status"] == "pending")   # pending rows carry no acceptedAt
    assert all(r["acceptedAt"] is not None for r in rows if r["status"] == "accepted")   # an accepted row always has its verdict stamp
    assert any(r["status"] == "accepted" for r in rows)


# ---------------------------------------------------------------------------
# Task 5.5 — the standing block
# ---------------------------------------------------------------------------

def test_normalise_standing_exact_shape_from_an_inline_body():
    """Spec §7 standing block minus counters + queue block; presence/enrollment lifted (contract C.10)."""
    body = {
        "at": "2026-09-26T03:24:55.812Z", "devices": 1,
        "enrollment": {"status": "active", "tokenId": 7, "agentId": 51075},
        "presence": {"connected": True, "acceptingWork": True, "heartbeatAgeMs": 4410, "stale": False,
                     "daemonVersion": "0.1.0+5bfa8261", "maxConcurrency": 1,
                     "runtimes": [{"id": "codex", "version": "codex-cli 0.157.0", "premiumModel": {"model": "gpt-6-astra", "effort": "xhigh"}}]},
        "standing": {"working": 1,
                     "running": [{"jobId": "9c3d2f7a-5b1e-4c0d-8a2f-6e7b1c9d0a3f", "objective": "o", "nodeKey": "oracle_assess",
                                  "role": "implement", "since": "2026-09-26T03:24:53.214Z", "extra": "ignored"}],
                     "consecutiveFailures": 0, "pausedUntil": None, "lastFailedAt": "2026-09-25T23:38:45.117Z",
                     "breaker": {"failures": 3, "cooldownMs": 900000},
                     "recentFailures": [{"at": "a", "reason": "runtime_error", "jobId": JOB, "nodeKey": "oracle_assess"},
                                        {"at": "b", "reason": "brand_new_reason", "jobId": JOB, "nodeKey": "k"}]},
        "queue": {"ready": 27, "fleetOnline": 396, "eligible": 0, "blocked": [{"reason": "at capacity", "nodes": 27}]},
        "server": {"version": "0.1.0+aa634633", "presenceWindowMs": 60000},
    }
    block = seat_api.normalise_standing(body)
    assert tuple(block) == seat_api.STANDING_KEYS
    assert block["working"] == 1 and block["consecutiveFailures"] == 0 and block["pausedUntil"] is None
    assert block["running"] == [{"jobId": "9c3d2f7a-5b1e-4c0d-8a2f-6e7b1c9d0a3f", "objective": "o", "nodeKey": "oracle_assess",
                                 "role": "implement", "since": "2026-09-26T03:24:53.214Z"}]
    assert block["breaker"] == {"failures": 3, "cooldownMs": 900000}
    assert block["recentFailures"] == [{"at": "a", "reason": "runtime_error", "nodeKey": "oracle_assess", "jobId": JOB},
                                       {"at": "b", "reason": "other", "nodeKey": "k", "jobId": JOB}]
    assert block["presenceConnected"] is True and block["heartbeatAgeMs"] == 4410 and block["presenceStale"] is False
    assert block["daemonVersion"] == "0.1.0+5bfa8261" and block["maxConcurrency"] == 1
    assert block["premiumAdvertised"] == {"model": "gpt-6-astra", "effort": "xhigh"}
    assert block["agentId"] == 51075 and block["enrollmentStatus"] == "active" and block["devices"] == 1
    assert block["queue"] == {"ready": 27, "eligible": 0, "fleetOnline": 396,
                              "blocked": [{"reason": "at capacity", "nodes": 27}], "asOfUtc": "2026-09-26T03:24:55.812Z"}
    assert block["asOfUtc"] == "2026-09-26T03:24:55.812Z"
    empty = seat_api.normalise_standing({})
    assert tuple(empty) == seat_api.STANDING_KEYS and empty["working"] is None and empty["running"] == [] and empty["queue"] is None


def test_normalise_standing_reads_the_seats_form_only():
    """Spec §6 never-used: `?queue=0` returns `queue: null` and `/workers.working` is a heartbeat echo --
    the normaliser yields None for both rather than inventing a queue line or a 'working now'."""
    seats = seat_api.normalise_standing(_fixture("seat7_standing.json"))
    assert isinstance(seats["working"], int) and tuple(seats["queue"]) == seat_api.QUEUE_KEYS
    assert all(isinstance(seats["queue"][k], int) for k in ("ready", "eligible", "fleetOnline"))
    assert all(set(b) == {"reason", "nodes"} for b in seats["queue"]["blocked"])
    q0 = seat_api.normalise_standing(_fixture("workers_standing_q0.json"))
    assert q0["queue"] is None and isinstance(q0["working"], int)       # same standing, no queue
    row = seat_api.normalise_standing(_fixture("workers_row.json"))
    assert row["working"] is None and row["queue"] is None and row["running"] == []   # top-level `working` is never read
    # the workers form spells fleet size `online`; the seats form `fleetOnline` -- only the latter is read
    assert seat_api.normalise_standing({"queue": {"ready": 1, "online": 398}})["queue"]["fleetOnline"] is None


# ---------------------------------------------------------------------------
# Task 5.6 — the client core: pool, retry once, gzip, redaction, last-good
# ---------------------------------------------------------------------------

async def test_every_read_is_a_keyless_gzip_get_with_the_20s_timeout():
    """Spec §6: keyless GET, Accept-Encoding: gzip, 20 s timeout -- on the injected client too."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_fixture("health.json"))

    async with _client(handler) as client:
        result = await client.health()
    assert result.ok and result.status == 200 and result.route == "/health"
    assert result.as_of_utc == "2026-09-26T03:40:07Z" and result.reason is None and result.elapsed_s >= 0.0
    request = seen[0]
    assert request.method == "GET" and str(request.url) == f"{SWARM_API_HOSTS[0]}/health"
    assert request.headers["accept-encoding"] == "gzip" and request.headers["accept"] == "application/json"
    assert not {k.lower() for k in request.headers} & {"authorization", "x-api-key", "cookie", "token"}
    assert request.extensions["timeout"] == {"connect": 20.0, "read": 20.0, "write": 20.0, "pool": 20.0}


async def test_the_owned_client_has_gzip_20s_and_no_redirects():
    """Construction-level: the client the module builds for itself (never used by a test for a request)."""
    owned = seat_api.SeatApiClient()
    try:
        assert owned._client.timeout == httpx.Timeout(20.0)
        assert owned._client.follow_redirects is False
        assert owned._client.headers["accept-encoding"] == "gzip" and owned._client.headers["accept"] == "application/json"
        assert "authorization" not in owned._client.headers
        assert owned._owns_client is True
    finally:
        await owned.close()
    with pytest.raises(ValueError):
        seat_api.SeatApiClient(hosts=())


async def test_a_gzip_body_is_decoded_and_parsed():
    def handler(request):
        return httpx.Response(200, content=gzip.compress(json.dumps(_fixture("services.json")).encode("utf-8")),
                              headers={"content-encoding": "gzip"})

    async with _client(handler) as client:
        result = await client.services()
    assert result.ok and result.data["verifier"]["claims"] == 1568791
    assert isinstance(result.data["verifier"]["claims"], int)          # ints survive the redaction pipeline


async def test_retry_once_on_5xx_rotates_to_the_second_host_then_gives_up():
    """Spec §6: retry once on 5xx; the pool is api.imd.fun -> Railway."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(500, json=_fixture("seat7_500.json"))

    async with _client(handler) as client:
        result = await client.health()
    assert [r.url.host for r in seen] == [FIRST_HOST, SECOND_HOST]
    assert result.ok is False and result.status == 500 and result.data is None and result.as_of_utc is None
    assert result.reason == "500 ×2 (retrying)"


async def test_timeout_and_transport_errors_retry_once_then_give_up():
    seen = []

    def timeout_then_ok(request):
        seen.append(request)
        if len(seen) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"status": "ok"})

    async with _client(timeout_then_ok) as client:
        result = await client.health()
    assert result.ok and len(seen) == 2

    def always_timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    async with _client(always_timeout) as client:
        result = await client.health()
    assert result.ok is False and result.status is None and result.reason == "timeout ×2 (retrying)"

    calls = []

    def refused_then_502(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(502, text="bad gateway")

    async with _client(refused_then_502) as client:
        result = await client.services()
    assert result.reason == "transport ×1 · 502 ×1 (retrying)" and result.status == 502


async def test_4xx_bad_json_and_oversize_bodies_are_answers_not_retries():
    """A 4xx, a non-JSON 200 or an oversize body says something about the request; no second host is asked."""
    seen = []

    def not_found(request):
        seen.append(request)
        return httpx.Response(404, json={"error": "unknown"})

    async with _client(not_found) as client:
        result = await client.health()
    assert result.ok is False and result.status == 404 and result.reason == "404" and len(seen) == 1

    async with _client(lambda request: httpx.Response(200, text="<html>gateway</html>")) as client:
        result = await client.health()
    assert result.ok is False and result.status == 200 and result.reason == "bad json" and result.data is None

    async with _client(lambda request: httpx.Response(200, content=b"x" * (seat_api.MAX_BODY_BYTES + 1))) as client:
        result = await client.health()
    assert result.ok is False and result.reason == "body too large" and result.data is None


async def test_health_and_services_are_redacted_and_remembered_as_last_good():
    """Spec §6 rule 4: last-good kept behind its own asOfUtc -- the client remembers the newest ok result per route."""
    mode = {"fail": False}

    def handler(request):
        if mode["fail"]:
            return httpx.Response(503, text="unavailable")
        body = _fixture("health.json") if request.url.path == "/health" else _fixture("services.json")
        return httpx.Response(200, json=body)

    async with _client(handler) as client:
        health = await client.health()
        services = await client.services()
        assert health.data["connectedDaemons"] == 409 and health.data["awaitingVerdict"] == 7
        assert services.data["verifier"]["up"] is True
        mode["fail"] = True
        again = await client.health()
        assert again.ok is False and again.reason == "503 ×2 (retrying)"
        assert client.last_good("/health") is health and client.last_good("/services") is services
        assert client.last_good("/nowhere") is None
    async with _client(_no_network) as fresh:
        assert fresh.last_good("/health") is None


# ---------------------------------------------------------------------------
# Task 5.7 — standing / seat_work / backfill
# ---------------------------------------------------------------------------

async def test_working_now_and_queue_come_from_seat_standing_only():
    """Spec §6 never-used + mutation proof 9: 'working now' and the queue line come from
    GET /seats/<id>/standing with NO query string; /workers is never requested; ?queue=0 (which
    returns queue: null -- workers_standing_q0.json) is never sent; a /workers row's `working` is never read."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_fixture("seat7_standing.json"))

    async with _client(handler) as client:
        result = await client.standing(7)
    assert result.ok and [str(r.url) for r in seen] == [f"{SWARM_API_HOSTS[0]}/seats/7/standing"]
    assert seen[0].url.query == b""
    block = seat_api.normalise_standing(result.data)
    assert isinstance(block["working"], int) and tuple(block["queue"]) == seat_api.QUEUE_KEYS
    assert isinstance(block["queue"]["ready"], int) and isinstance(block["queue"]["eligible"], int)
    assert block["queue"]["asOfUtc"] == result.data["at"]
    # why the query string matters: the ?queue=0 form has no queue at all
    assert seat_api.normalise_standing(_fixture("workers_standing_q0.json"))["queue"] is None
    # and a /workers row (top-level `working`, a heartbeat echo behind a 30 s cache) never feeds `working`
    assert seat_api.normalise_standing(_fixture("workers_row.json"))["working"] is None
    # the client has no method that could reach /workers at all
    assert not [name for name in dir(seat_api.SeatApiClient) if "worker" in name.lower()]


async def test_no_query_string_reaches_standing():
    """Spec §6 standing row: `?queue=0` returns `queue: null` -- never use it if the queue line is wanted."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_fixture("seat7_standing.json"))

    async with _client(handler) as client:
        await client.standing(7)
        await client.standing(420)
    assert [r.url.raw_path for r in seen] == [b"/seats/7/standing", b"/seats/420/standing"]
    assert all(b"?" not in r.url.raw_path and b"queue" not in r.url.raw_path for r in seen)


async def test_api_500_is_unavailable_not_zero():
    """Spec §6 seats row (HTTP 500 on 16/60 reads: retry once, keep last-good, render `verdicts as of HH:MM`,
    never 0) + mutation proof 22."""
    seen = []
    mode = {"fail": False}

    def handler(request):
        seen.append(request)
        if mode["fail"]:
            return httpx.Response(500, json=_fixture("seat7_500.json"))
        return httpx.Response(200, json=_fixture("seat7_work20.json"))

    async with _client(handler) as client:
        good = await client.seat_work(7)
        assert good.ok and good.data["attempts"] == 288 and good.as_of_utc == "2026-09-26T03:40:07Z"
        assert good.route == "/seats/7?work=60&reviews=0"
        mode["fail"] = True
        bad = await client.seat_work(7)
    assert bad.ok is False and bad.status == 500 and bad.data is None and bad.as_of_utc is None
    assert bad.reason == "500 ×2 (retrying)"
    assert [r.url.host for r in seen[1:]] == [FIRST_HOST, SECOND_HOST]      # exactly one retry, on the other host
    kept = client.last_good(bad.route)
    assert kept is good and kept.data["attempts"] == 288                     # last-good survives the 500
    assert not isinstance(bad.data, int)                                     # never a zero


async def test_seat_work_sends_work_and_reviews_and_validates_them():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_fixture("seat7_work20.json"))

    async with _client(handler) as client:
        default = await client.seat_work(7)
        twenty = await client.seat_work(7, work=20)
        assert default.ok and twenty.ok
        for bad_value in (-1, 1001, True, "20", 2.5):
            refused = await client.seat_work(7, work=bad_value)   # type: ignore[arg-type]
            assert refused.ok is False and refused.reason == "bad params" and refused.route == "/seats/7"
        refused = await client.seat_work(7, reviews=5000)
        assert refused.reason == "bad params"
    assert [r.url.query for r in seen] == [b"work=60&reviews=0", b"work=20&reviews=0"]
    assert seat_api.validate_counters(default.data) is True                  # the redaction pipeline keeps ints


async def test_backfill_asks_for_1000_rows_and_zero_reviews():
    """Spec §5.6 / §16 #15: one-time history seed from /seats/<id>?work=1000&reviews=0."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_fixture("seat7_work20.json"))

    async with _client(handler) as client:
        result = await client.backfill(420)
    assert result.ok and result.route == "/seats/420?work=1000&reviews=0"
    assert str(seen[0].url) == f"{SWARM_API_HOSTS[0]}/seats/420?work=1000&reviews=0"


async def test_seat_is_validated_before_any_request():
    """As SwarmClient.fetch_seat: an int formatted with {seat:d}; a bool, a negative, a non-digit string or a float never builds a path."""
    async with _client(_no_network) as client:
        for bad in (-1, True, "7x", 7.0, None):
            standing = await client.standing(bad)      # type: ignore[arg-type]
            work = await client.seat_work(bad)         # type: ignore[arg-type]
            assert standing.ok is False and standing.reason == "bad seat" and standing.route == "/seats/?/standing"
            assert work.ok is False and work.reason == "bad seat" and work.route == "/seats/?"
            assert standing.status is None and standing.data is None


# ---------------------------------------------------------------------------
# Task 5.8 — /jobs/<uuid>/submissions
# ---------------------------------------------------------------------------

async def test_job_submissions_refuses_a_non_uuid_job_id():
    """Spec §6 (`/jobs/<jobId>/submissions` keyed by jobId) + the surf client's rule that caller text never
    reaches a path: anything but a canonical lowercase UUID is refused before any request and never echoed."""
    async with _client(_no_network) as client:
        for bad in ("b1fb1439", "../health", "B1FB1439-7E2A-4D61-9F3B-2C8E5A1D0B47", "", None, 7,
                    "b1fb1439-7e2a-4d61-9f3b-2c8e5a1d0b47?queue=0", "b1fb1439-7e2a-4d61-9f3b-2c8e5a1d0b47/x"):
            result = await client.job_submissions(bad)   # type: ignore[arg-type]
            assert result.ok is False and result.reason == "bad job id" and result.data is None and result.status is None
            assert result.route == "/jobs/?/submissions"


async def test_summaries_are_dropped_before_any_string_is_kept():
    """Spec §6 traps + §13: recentFailures[].summary and submissions[].summary are raw runtime error text
    (a masked provider key sat in one on 09-25); they are dropped before redaction, persistence or render --
    the sentinel appears nowhere in either result, and neither does the key."""
    sentinel = "SUMMARY-SENTINEL-4f2a"
    standing = _fixture("workers_standing_q0.json")        # the form that carries summary in the wild
    for entry in standing["standing"]["recentFailures"]:
        entry["summary"] = f"{sentinel} 401 Unauthorized: Incorrect API key provided: sk-svcac********"
    subs = _fixture("job_b1fb1439_submissions.json")
    for item in subs["submissions"]:
        item["summary"] = f"{sentinel} wrote outside the task's allowed paths: err.log"

    def handler(request):
        return httpx.Response(200, json=standing if request.url.path.endswith("/standing") else subs)

    async with _client(handler) as client:
        r1 = await client.standing(7)
        r2 = await client.job_submissions(JOB)
    for result in (r1, r2):
        assert result.ok
        dumped = json.dumps(result.data)
        assert sentinel not in dumped and '"summary"' not in dumped and "sk-svcac" not in dumped
    assert all("summary" not in f for f in seat_api.normalise_standing(r1.data)["recentFailures"])


async def test_submission_hash_survives_redaction_and_device_keys_do_not():
    """The 64-hex `hash` is the ledger's join key and must survive the redactor (as `submissionHash`, an allowed
    field); a 64-hex deviceKey must not (8 chars, spec §13 identifiers)."""
    body = {"jobId": JOB, "count": 1, "submissions": [{
        "hash": HEX, "nodeKey": "oracle_assess", "role": "implement", "attempt": 1,
        "deviceKey": "7" * 64, "seat": {"tokenId": 7, "agentId": 51075}, "outcome": "failed", "accepted": False,
        "failureReason": "runtime_error", "failureClass": "machine",
        "usage": {"model": None, "runtime": "codex", "turns": 0, "inputTokens": 0, "outputTokens": 0, "cachedInputTokens": 0, "wallClockMs": 33704},
        "createdAt": "2026-09-25T23:37:56.035Z", "repoUrl": "https://x", "summary": "gone",
    }], "repoUrl": "https://github.com/example/oracle-panel", "baseCommit": "deadbeef"}

    async with _client(lambda request: httpx.Response(200, json=body)) as client:
        result = await client.job_submissions(JOB)
    item = result.data["submissions"][0]
    assert tuple(item) == seat_api.SUBMISSION_KEYS
    assert item["submissionHash"] == HEX and item["hash12"] == HEX[:12]
    assert item["deviceKey8"] == "7" * 8 and "7" * 64 not in json.dumps(result.data)
    assert item["seatTokenId"] == 7 and item["seatAgentId"] == 51075 and item["attempt"] == 1
    assert item["outcome"] == "failed" and item["failureReason"] == "runtime_error" and item["failureClass"] == "machine"
    assert item["usage"] == {"turns": 0, "inputTokens": 0, "outputTokens": 0, "cachedInputTokens": 0, "wallClockMs": 33704,
                             "model": None, "runtime": "codex"}
    assert set(result.data) == {"jobId", "count", "submissions"} and "repoUrl" not in json.dumps(result.data)
    assert seat_api.normalise_submission({"hash": "not-hex", "seat": 7})["submissionHash"] is None
    assert seat_api.normalise_submission({"hash": "not-hex", "seat": 7})["seatTokenId"] == 7   # an int `seat` is tolerated


async def test_submissions_are_filtered_to_the_seat():
    """Spec §6 submissions row: filter submissions[] to our seat; reasons are enum words only."""
    async with _client(lambda request: httpx.Response(200, json=_fixture("job_b1fb1439_submissions.json"))) as client:
        result = await client.job_submissions(JOB)
    mine = seat_api.submissions_for_seat(result.data, 7)
    assert mine and all(s["seatTokenId"] == 7 for s in mine)
    assert len(mine) < len(result.data["submissions"])                         # another seat's attempt is excluded
    assert all(tuple(s) == seat_api.SUBMISSION_KEYS for s in mine)
    assert all(s["failureReason"] in seat_api.FAILURE_REASONS + (seat_api.REASON_OTHER, None) for s in mine)
    assert all(s["failureClass"] in seat_api.FAILURE_CLASSES + (seat_api.REASON_OTHER, None) for s in mine)
    assert seat_api.submissions_for_seat(result.data, 999999) == [] and seat_api.submissions_for_seat(None, 7) == []


async def test_a_404_on_submissions_is_an_answer_not_a_retry():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(404, json={"error": "not_found"})

    async with _client(handler) as client:
        result = await client.job_submissions(JOB)
    assert result.ok is False and result.status == 404 and result.reason == "404" and len(seen) == 1
    assert str(seen[0].url) == f"{SWARM_API_HOSTS[0]}/jobs/{JOB}/submissions"


# ---------------------------------------------------------------------------
# Task 5.9 — plane block + hygiene
# ---------------------------------------------------------------------------

def test_normalise_plane_from_services_and_health():
    """Spec §7 plane block from /services + /health (spec §6 last row); undocumented fields labelled, None never 0."""
    plane = seat_api.normalise_plane(_fixture("services.json"), _fixture("health.json"), as_of_utc="2026-09-26T03:40:07Z")
    assert tuple(plane) == seat_api.PLANE_KEYS
    assert plane["version"] == "0.1.0+aa634633" and plane["verifierUp"] is True
    assert plane["verifierLastSeenUtc"] == "2026-09-26T03:32:58.104Z" and plane["verifierClaims"] == 1568791
    assert plane["awaitingVerdict"] == 7 and plane["connectedDaemons"] == 409 and plane["activeEnrollments"] == 417
    assert plane["computedAt"] == "2026-09-26T03:40:05.344Z" and plane["asOfUtc"] == "2026-09-26T03:40:07Z"
    nothing = seat_api.normalise_plane(None, None)
    assert tuple(nothing) == seat_api.PLANE_KEYS and all(v is None for v in nothing.values())
    # the list-shaped /services variant is read the same way; verifierUp falls back to the service row when /health is absent
    listed = {"services": [{"name": "verifier", "up": False, "lastSeenAt": "2026-09-26T03:00:00.000Z", "claims": 5}]}
    assert seat_api.normalise_plane(listed, None)["verifierUp"] is False
    assert seat_api.normalise_plane(listed, None)["verifierClaims"] == 5


async def test_every_string_in_a_result_passes_the_redactor():
    """Spec §6 (every string hostile: control strip + redact) + §13: a body carrying an OSC 52 clipboard write, the
    masked 09-25 key fragment and a 64-hex under a non-allowed field leaves the client harmless; ints and the
    allowed `submissionHash` survive."""
    hostile = {
        "attempts": 1, "accepted": 1, "rejected": 0, "failed": 0, "pending": 0,
        "work": [{"jobId": "j", "status": "accepted", "submissionHash": HEX,
                  "objective": "run \x1b]52;c;AAAA\x07 with sk-svcac******** and " + HEX + " \u202eevil",
                  "acceptedAt": "2026-09-26 03:11:29.985+00", "submittedAt": "2026-09-26T03:10:20.985Z", "launch": None}],
    }
    async with _client(lambda request: httpx.Response(200, json=hostile)) as client:
        result = await client.seat_work(7, work=1)
    objective = result.data["work"][0]["objective"]
    assert "\x1b" not in objective and "\x07" not in objective and "\u202e" not in objective
    assert "\u241b" in objective and "sk-[redacted]" in objective and "<hex64>" in objective and "sk-svcac" not in objective
    assert result.data["work"][0]["submissionHash"] == HEX                   # allowed field, kept whole
    assert result.data["attempts"] == 1 and isinstance(result.data["attempts"], int)
    assert seat_api.normalise_work_row(result.data["work"][0])["acceptedAt"] == "2026-09-26T03:11:29.985Z"


@pytest.mark.guard
def test_seat_api_is_pure_of_textual_subprocess_and_socket():
    """Spec §14 purity: data/seat_tail.py and data/seat_broker_client.py are the ONLY seat modules allowed
    subprocess/socket; seat_api imports httpx and nothing from textual."""
    tree = ast.parse((REPO / "maxpane_dashboard" / "data" / "seat_api.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"textual", "subprocess", "socket", "rich"}
    assert "httpx" in imported and "maxpane_dashboard" in imported
    assert not any(isinstance(n, ast.Attribute) and n.attr in {"run", "Popen"} and isinstance(n.value, ast.Name)
                   and n.value.id == "subprocess" for n in ast.walk(tree))


def test_public_names_match_the_contract():
    """Contract C.10 names + this WP's additive names are exported; nothing private leaks through __all__."""
    public = set(seat_api.__all__)
    assert {"ApiResult", "SeatApiClient", "parse_json_tolerant", "drop_summaries", "validate_counters",
            "normalise_work_row", "normalise_standing", "reason_word", "API_TIMEOUT_S", "SEAT_WORK_ROWS",
            "SEAT_WORK_BACKFILL_ROWS", "MAX_REASONS_PER_CYCLE", "FAILURE_REASONS", "FAILURE_CLASSES", "API_HOSTS"} <= public
    assert {"seat_counters", "failure_class_word", "normalise_submission", "submissions_for_seat", "normalise_plane"} <= public
    assert not [name for name in public if name.startswith("_")]
    assert all(hasattr(seat_api, name) for name in public)
    for name in ("standing", "seat_work", "job_submissions", "services", "health", "backfill", "last_good", "_get"):
        assert callable(getattr(seat_api.SeatApiClient, name))


# ---------------------------------------------------------------------------
# Task 5.10 — the owner-run captures keep the measured shapes
# ---------------------------------------------------------------------------

CAPTURED = FIXTURES / "captured"


def _captured(name: str):
    path = CAPTURED / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@pytest.mark.guard
def test_captured_bodies_keep_the_measured_shapes():
    """Spec §6 rule 6 + §14 fixtures: the redacted live captures under api/captured/ (WP5 Task 5.10, owner-run)
    are clean, registered as captured, and still carry every shape the synthetic bodies model.  Shape only, never
    a value: the synthetic api/*.json stay the inputs of every value-pinned test.  A red line here is plane drift
    and goes to aidude docs/imd-api-changelog.md §3 as a dated entry."""
    import re

    if not CAPTURED.is_dir():
        pytest.skip("no owner-run capture yet (WP5 Task 5.10)")
    entries = json.loads((FIXTURES.parent / "MANIFEST.json").read_text(encoding="utf-8"))["entries"]
    names = sorted(p.name for p in CAPTURED.glob("*.json"))
    assert {"health.json", "seat7_standing.json", "seat7_work20.json", "services.json", "workers_row.json"} <= set(names)
    for name in names:
        raw = (CAPTURED / name).read_bytes()
        text = raw.decode("utf-8")
        body = json.loads(text)
        assert not seat_redact.CONTROL_RE.search(text) and not seat_redact.SK_RE.search(text), name
        assert '"summary"' not in json.dumps(body), name
        assert all(isinstance(k, str) and k.startswith("scrubbed-") for k in _device_keys(body)), name
        assert seat_redact.find_secret(body, allowed_hex64_fields=frozenset({"submissionHash", "hash", "txHash"})) is None, name
        entry = entries[f"api/captured/{name}"]
        assert entry["synthetic"] is False and entry["sha256"] == hashlib.sha256(raw).hexdigest(), name
    iso_ms = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
    work = _captured("seat7_work20.json")
    assert seat_api.validate_counters(work) is True
    rows = [seat_api.normalise_work_row(r) for r in work["work"]]
    assert rows and all(tuple(r) == seat_api.WORK_ROW_KEYS for r in rows)
    assert all(r[k] is None or iso_ms.match(r[k]) for r in rows for k in ("submittedAt", "acceptedAt"))
    block = seat_api.normalise_standing(_captured("seat7_standing.json"))
    assert tuple(block) == seat_api.STANDING_KEYS and tuple(block["queue"]) == seat_api.QUEUE_KEYS
    assert all(isinstance(block["queue"][k], int) for k in ("ready", "eligible", "fleetOnline"))
    q0 = _captured("workers_standing_q0.json")
    if q0 is not None:                      # captured only when the owner could read seat 7's public device key
        assert seat_api.normalise_standing(q0)["queue"] is None
    subs = _captured("job_b1fb1439_submissions.json")
    if subs is not None:                    # captured only when the captured work20 held a failed row
        items = seat_api._prepare_submissions(subs)["submissions"]
        assert all(tuple(s) == seat_api.SUBMISSION_KEYS for s in items)
    plane = seat_api.normalise_plane(_captured("services.json"), _captured("health.json"))
    assert tuple(plane) == seat_api.PLANE_KEYS and isinstance(plane["version"], str)
