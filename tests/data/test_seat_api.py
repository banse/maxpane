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
