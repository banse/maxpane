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
