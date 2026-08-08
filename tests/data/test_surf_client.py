"""Tests for maxpane_dashboard.data.surf_client.

**Zero network.** Every test drives the client through an ``httpx.MockTransport``.
There are TWO offline doubles and they are not interchangeable:

* ``_raising_client`` raises ``AssertionError`` on any request, so it proves a
  code path performed **no I/O at all**. It may only be used where nothing is
  fetched — ``MockTransport`` does not wrap handler exceptions, so that
  ``AssertionError`` propagates verbatim through httpx and is caught by none of
  the client's ``except (httpx.HTTPError, ValueError)`` / ``except RuntimeError``
  handlers.
* ``_offline_client`` raises ``httpx.ConnectError`` — a real transport failure
  the client already classifies — so it models a **total outage** and every
  ``fetch_*`` degrades to ``None`` through its normal retry/rotation path. Every
  ``*_outage_returns_none`` test uses this one.

``RecordingTransport`` captures every request so pool separation is asserted
structurally, not assumed. Fixtures are committed slices of real payloads
captured 2026-08-08 (see ``tests/fixtures/surf/client/``); expected values below
were derived by decoding those files, never typed from memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import surf_client
from maxpane_dashboard.data.surf_client import SurfClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "client"


def load_fixture(name: str) -> Any:
    with open(FIXTURES / name) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles (mirrors tests/data/test_fwa_client.py)
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _raising_client(**kw: Any) -> SurfClient:
    """A client that must not be asked for anything — proves zero I/O.

    Use ONLY where the code path under test issues no request. An
    ``AssertionError`` raised inside a ``MockTransport`` handler is re-raised
    verbatim by httpx (verified against the installed 0.28.1: the transport does
    not wrap handler exceptions), and ``AssertionError`` is not an
    ``httpx.HTTPError``, a ``ValueError`` or a ``RuntimeError`` — so it sails
    straight through every ``except`` clause in ``SurfClient`` and out of the
    fetcher. For "the whole internet is down, return None", use
    ``_offline_client`` below.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _offline(request: httpx.Request) -> httpx.Response:
    """Fail at the socket, the way a real outage does."""
    raise httpx.ConnectError(
        f"test attempted real network access: {request.method} {request.url}",
        request=request,
    )


def _offline_client(**kw: Any) -> SurfClient:
    """A client whose every request fails at the transport layer.

    ``httpx.ConnectError`` IS an ``httpx.HTTPError``, so ``_rpc_state``,
    ``_rpc_state_batch``, ``_rpc_logs`` and ``_get_json`` all classify it,
    exhaust their retries, rotate through every endpoint and give up — which is
    exactly the total-outage path each ``fetch_*`` must degrade to ``None``
    through. This is the double for every ``*_outage_returns_none`` test.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_offline)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, method, payload_or_None)``."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[tuple[str, str, Any]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                try:
                    payload = json.loads(request.content)
                except ValueError:
                    payload = None
            self.requests.append((str(request.url), request.method, payload))
            return handler(request)

        super().__init__(_wrapped)

    def urls(self) -> list[str]:
        return [u for (u, _m, _p) in self.requests]


def _client_on(transport: httpx.MockTransport, **kw: Any) -> SurfClient:
    return SurfClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _rpc_ok(payload: dict, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}


# ---------------------------------------------------------------------------
# WP1.1 — configuration and classification
# ---------------------------------------------------------------------------


def test_state_and_log_pools_are_disjoint_roles():
    client = _raising_client()
    assert client.state_endpoints[0] == "https://ethereum-rpc.publicnode.com"
    # publicnode refuses archive eth_getLogs (CLAUDE.md dead-endpoint table):
    # it must never appear in the logs pool.
    assert all("publicnode" not in u for u in client.log_endpoints)
    assert "https://gateway.tenderly.co/public/mainnet" in client.log_endpoints
    assert "https://eth.drpc.org" in client.log_endpoints


@pytest.mark.parametrize(
    "url",
    [
        "https://eth.llamarpc.com",       # HTTP 521, origin down
        "https://rpc.ankr.com/eth",       # now keyed
        "https://cloudflare-eth.com",     # -32046 on every call
        "https://api.reservoir.tools",    # sunset
        "https://mainnet.infura.io/v3/x", # keyed
    ],
)
def test_banned_host_rejected_at_construction(url):
    with pytest.raises(ValueError):
        SurfClient(state_rpc=url, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))
    with pytest.raises(ValueError):
        SurfClient(log_rpcs=[url], http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        # 1rpc ships its 50-block log cap under -32602 — the *malformed* code.
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "query exceeds max block range"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, True),
        ({"code": -32046, "message": "Cannot fulfill request"}, True),
        # A genuinely malformed request must NOT rotate — it fails the same way
        # on every endpoint and would burn the whole pool.
        ({"code": -32602, "message": "invalid argument 0: json: cannot unmarshal"}, False),
        ({"code": -32601, "message": "the method does not exist"}, False),
        # A non-dict error is unclassifiable: err toward rotation.
        ("boom", True),
    ],
)
def test_endpoint_limitation_classification_is_message_first(err, expected):
    assert surf_client._looks_like_endpoint_limitation(err) is expected


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "block range is too large, try 25700000-25700001"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, False),
        ({"code": -32602, "message": "invalid argument"}, False),
    ],
)
def test_range_limitation_is_a_narrower_class(err, expected):
    assert surf_client._is_range_limitation(err) is expected


@pytest.mark.asyncio
async def test_rpc_state_rotates_on_dead_status_and_error_body():
    """publicnode answers HTTP 403 → rotate; tenderly answers an error body →
    rotate; the third endpoint answers — the caller sees its result."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        payload = json.loads(request.content)
        if "publicnode" in url:
            return httpx.Response(403, json={})
        if "tenderly" in url:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32000, "message": "capacity exceeded, upgrade plan"},
            })
        return httpx.Response(200, json=_rpc_ok(payload, "0x92e"))

    async with _client_on(RecordingTransport(handler)) as client:
        result = await client._rpc_state("eth_getTransactionCount",
                                         ["0x" + "11" * 20, "latest"])
    assert result == "0x92e"
    assert len({u.split("/")[2] for u in seen}) == 3  # three distinct hosts tried


@pytest.mark.asyncio
async def test_rpc_state_gives_up_after_all_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, json={})

    async with _client_on(RecordingTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            await client._rpc_state("eth_blockNumber", [])


@pytest.mark.asyncio
async def test_close_does_not_close_injected_client():
    http = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    client = SurfClient(http_client=http)
    await client.close()
    assert not http.is_closed  # injected clients belong to the caller
    await http.aclose()
