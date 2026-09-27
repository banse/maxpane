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
