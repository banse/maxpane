"""Tests for ``maxpane_dashboard.data.curator_client`` — THE LIST's fetch layer.

**Zero network.** Every test drives the client through an ``httpx.MockTransport``.
Two offline doubles, and they are not interchangeable (the distinction is
``tests/data/test_surf_client.py``'s and it is load-bearing here too):

* ``_raising_client`` raises ``AssertionError`` on any request, so it proves a
  code path performed **no I/O at all**.  ``MockTransport`` does not wrap a
  handler exception, and ``AssertionError`` is neither an ``httpx.HTTPError``
  nor a ``ValueError``, so it sails through every ``except`` in the client and
  out of the fetcher.  Use it only where nothing may be fetched.
* ``_offline_client`` raises ``httpx.ConnectError`` — a transport failure the
  client already classifies — so it models a **total outage** and every
  ``fetch_*`` degrades to ``None``/``{}`` through its normal retry-and-rotate
  path.

Real payloads come from WP0's committed captures through
``tests.curator_fixtures.capture()``: ``batch.json`` + ``results.json`` for the
view round, ``tenderly_logs.json`` for the log sweep, ``bs_page_*.json`` for the
Blockscout cross-check.  They are read **in place** rather than copied into
``tests/fixtures/curator/client/`` — a byte-for-byte copy of 1.1 MB of JSON is a
second source of truth that can drift from the first, and the captures are
declared read-only.  ``tests/fixtures/curator/client/`` therefore holds only
payloads that do not exist on chain yet: the synthetic ``Settled`` /
``HourSaved`` / ``Rescued`` rows.

Every expected value below was decoded out of those bytes, never typed from
memory.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data import curator_client
from maxpane_dashboard.data.curator_client import CuratorClient

from tests.curator_fixtures import capture

CLIENT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "curator" / "client"

#: The host of the state pool's primary, for tests that assert rotation.
STATE_PRIMARY_HOST = "ethereum-rpc.publicnode.com"


def client_fixture(name: str) -> Any:
    with open(CLIENT_FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted a request it must not make: {request.method} {request.url}"
    )


def _client(handler: Callable[[httpx.Request], httpx.Response], **kw: Any) -> CuratorClient:
    """A client whose every request is answered by *handler*."""
    return CuratorClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _raising_client(**kw: Any) -> CuratorClient:
    """Proves a code path issues **no request at all**."""
    return _client(_no_network, **kw)


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(
        f"test attempted real network access: {request.method} {request.url}",
        request=request,
    )


def _offline_client(**kw: Any) -> CuratorClient:
    """Every endpoint down, at the socket — the total-outage double."""
    return _client(_offline, **kw)


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, method, payload, headers)``."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[tuple[str, str, Any, httpx.Headers]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload: Any = None
            if request.content:
                try:
                    payload = json.loads(request.content)
                except ValueError:
                    payload = None
            self.requests.append(
                (str(request.url), request.method, payload, request.headers)
            )
            return handler(request)

        super().__init__(_wrapped)


def _recording_client(
    handler: Callable[[httpx.Request], httpx.Response], **kw: Any
) -> tuple[CuratorClient, RecordingTransport]:
    transport = RecordingTransport(handler)
    client = CuratorClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )
    return client, transport


def _rpc_ok(result: Any) -> Callable[[httpx.Request], httpx.Response]:
    """A handler that answers any single call with *result*."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                         "result": result})

    return handler


# ===========================================================================
# WP2.1 — endpoint pools, the User-Agent, and the keyless guarantee
# ===========================================================================


def test_the_client_sends_a_real_user_agent() -> None:
    """publicnode 403s python-urllib's default UA and accepted the identical
    batch from curl (captures/README.md).  Every request must carry a real one.

    Asserted on the *transport's* view of the request, not on the constructor,
    because httpx merges client-level and request-level headers and only the
    merged value is what the endpoint sees.  ``surf_client`` sets only
    ``Accept`` on the client it builds, and an injected client (which is what
    every test here uses, and what a caller may pass in production) carries
    whatever headers its owner set — so the header has to go on the *request*.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1"})

    client = _client(handler)
    asyncio.run(client._rpc_state("eth_blockNumber", []))
    assert seen and seen[0]
    low = seen[0].lower()
    assert "maxpane" in low
    for default in ("python-urllib", "urllib", "python-httpx", "python-requests"):
        assert default not in low, f"{seen[0]!r} is a library default UA"


def test_publicnode_is_absent_from_the_logs_pool() -> None:
    """It refuses archive eth_getLogs (CLAUDE.md hazard table).  A pool that
    contains it burns a round trip and a retry on every sweep."""
    assert all("publicnode" not in u for u in CuratorClient().log_endpoints)


def test_publicnode_is_the_state_pool_primary() -> None:
    """The other half of the same rule: it is the strongest keyless batcher and
    the whole fast tier is one batch array."""
    assert "publicnode" in CuratorClient().state_endpoints[0]


def test_banned_hosts_are_refused_at_construction() -> None:
    for url in ("https://eth.llamarpc.com", "https://rpc.ankr.com/eth",
                "https://cloudflare-eth.com", "https://api.reservoir.tools",
                "https://eth-mainnet.g.alchemy.com/v2/x",
                "https://mainnet.infura.io/v3/x",
                "https://api.etherscan.io/api"):
        with pytest.raises(ValueError):
            CuratorClient(state_rpc=url)
        with pytest.raises(ValueError):
            CuratorClient(log_rpcs=[url])


def test_the_default_pools_are_themselves_unbanned() -> None:
    """A banned-host list that rejects our own defaults would make the
    zero-argument constructor raise — the shape of that bug is a typo in the
    frozenset, and it is invisible until someone builds a default client."""
    client = CuratorClient()
    assert client.state_endpoints and client.log_endpoints


def test_no_module_level_string_looks_like_a_key() -> None:
    src = inspect.getsource(curator_client)
    for banned in ("api_key", "apikey", "x-api-key", "Authorization",
                   "private_key", "keystore", "eth_sendRawTransaction",
                   "eth_sendTransaction", "eth_sign"):
        assert banned not in src, banned


# ===========================================================================
# WP2.2 — the batched state RPC
# ===========================================================================


def _batch_handler(
    result_for: Callable[[dict], Any],
    *,
    shuffle: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer a batch array entry-by-entry, optionally out of order."""

    def handler(request: httpx.Request) -> httpx.Response:
        payloads = json.loads(request.content)
        out = []
        for entry in payloads:
            value = result_for(entry)
            if isinstance(value, dict) and "error" in value:
                out.append({"jsonrpc": "2.0", "id": entry["id"], **value})
            else:
                out.append({"jsonrpc": "2.0", "id": entry["id"], "result": value})
        if shuffle:
            out.reverse()
        return httpx.Response(200, json=out)

    return handler


def test_a_batch_reply_is_mapped_by_id_not_by_position() -> None:
    """A provider is free to answer a batch array in any order — JSON-RPC says
    so explicitly.  Position-mapping a reversed reply silently transposes every
    field, and every one of these views is a same-width uint256, so no type
    check anywhere downstream can catch it."""
    calls = [("eth_call", [{"to": A.CURATOR, "data": sel}, "latest"])
             for sel in ("0xaa", "0xbb", "0xcc")]
    marker = {"0xaa": "0x01", "0xbb": "0x02", "0xcc": "0x03"}
    handler = _batch_handler(
        lambda e: marker[e["params"][0]["data"]], shuffle=True
    )
    results = asyncio.run(_client(handler)._rpc_state_batch(calls))
    assert results == ["0x01", "0x02", "0x03"]


def test_one_errored_batch_entry_stays_none_and_the_rest_survive() -> None:
    """The partial-success case is the NORMAL case, not an edge one.  The
    errored slot stays ``None``: a ``0`` there is indistinguishable from a real
    reading, and this contract has three legitimate zeros."""
    calls = [("eth_call", [{"to": A.CURATOR, "data": sel}, "latest"])
             for sel in ("0xaa", "0xbb", "0xcc")]

    def result_for(entry: dict) -> Any:
        if entry["params"][0]["data"] == "0xbb":
            return {"error": {"code": -32000, "message": "execution reverted"}}
        return "0x2a"

    results = asyncio.run(_client(_batch_handler(result_for))._rpc_state_batch(calls))
    assert results == ["0x2a", None, "0x2a"]


def test_a_non_list_reply_rotates_to_the_next_endpoint() -> None:
    """An endpoint that answers a batch array with a scalar is not speaking the
    protocol.  Rotating is cheaper than parsing whatever it did send."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if len(seen) == 1:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
                                             "result": "0x1"})
        payloads = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": p["id"], "result": "0x7"} for p in payloads
        ])

    results = asyncio.run(
        _client(handler)._rpc_state_batch([("eth_blockNumber", [])])
    )
    assert results == ["0x7"]
    assert len(set(seen)) == 2  # it really did move to another host


def test_a_dead_status_rotates_without_burning_the_retry_ladder() -> None:
    """401/403/451/52x mean "this host", not "try again in a moment".  Retrying
    them is how a keyless endpoint that quietly started requiring a key bricks a
    whole dashboard for a session."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == STATE_PRIMARY_HOST:
            return httpx.Response(403, text="forbidden")
        payloads = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": p["id"], "result": "0x7"} for p in payloads
        ])

    results = asyncio.run(
        _client(handler)._rpc_state_batch([("eth_blockNumber", [])])
    )
    assert results == ["0x7"]
    assert seen.count(STATE_PRIMARY_HOST) == 1, "a dead host was retried"


def test_a_malformed_batch_request_short_circuits_the_whole_chain() -> None:
    """Our bug, not theirs: it fails identically on every endpoint, so rotating
    triples the request count and hides the mistake."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32600, "message": "invalid request"},
        })

    with pytest.raises(RuntimeError):
        asyncio.run(_client(handler)._rpc_state_batch([("eth_blockNumber", [])]))
    assert len(seen) == 1


def test_a_total_batch_outage_returns_none_not_a_list_of_zeros() -> None:
    assert asyncio.run(
        _offline_client()._rpc_state_batch([("eth_blockNumber", [])])
    ) is None
