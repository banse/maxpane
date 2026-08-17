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


# ===========================================================================
# WP2.3 — the logs pool, message-text classification, bounded shrinking
# ===========================================================================


def _log_error_handler(
    err_for_host: dict[str, dict], rows: list[dict] | None = None,
    status_for_host: dict[str, int] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Per-host canned JSON-RPC errors; any other host answers *rows*."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        host = request.url.host
        if host in err_for_host:
            return httpx.Response(
                (status_for_host or {}).get(host, 200),
                json={"jsonrpc": "2.0", "id": payload["id"],
                      "error": err_for_host[host]},
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                         "result": rows if rows is not None else []})

    return handler


def test_a_routing_message_fails_over_even_though_its_code_is_reused() -> None:
    """drpc's real failure: "Can't route your request..." arrives with a code
    other providers spend on a malformed request.  Classifying on the CODE
    sends a healthy query to the bin; classifying on the TEXT fails over."""
    seen: list[str] = []
    rows = [{"topics": [A.TOPIC_DEPOSITED], "data": "0x"}]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        payload = json.loads(request.content)
        if len(seen) == 1:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32602,
                          "message": "Can't route your request. Try again later."},
            })
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                         "result": rows})

    out = asyncio.run(_client(handler)._rpc_logs("eth_getLogs", [{}]))
    assert out == rows
    assert len(set(seen)) == 2, "it never left the endpoint that could not route"


def test_a_genuinely_malformed_request_short_circuits_the_chain() -> None:
    """Same code, different text.  Rotating on our own bug triples the request
    count and hides it."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        payload = json.loads(request.content)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload["id"],
            "error": {"code": -32602, "message": "invalid argument 0"},
        })

    with pytest.raises(RuntimeError):
        asyncio.run(_client(handler)._rpc_logs("eth_getLogs", [{}]))
    assert len(seen) == 1, "a malformed request was tried on a second endpoint"


def test_a_range_error_is_classified_before_raise_for_status() -> None:
    """drpc wraps its shrinkable range cap in an HTTP 400.  Status-first
    handling demotes the one recoverable error in the set to an opaque
    transport failure, and the sweep then fails instead of shrinking."""
    err = {"code": -32602, "message": "block range is too large, limited to 1000"}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(400, json={"jsonrpc": "2.0", "id": payload["id"],
                                         "error": err})

    with pytest.raises(curator_client._LogRangeError):
        asyncio.run(_client(handler)._rpc_logs("eth_getLogs", [{}]))


def test_a_suggested_range_is_never_followed() -> None:
    """One provider decrements a single block per round trip and livelocks
    anything that obeys it.  The window halves instead, boundedly."""
    windows: list[tuple[int, int]] = []
    suggested = (0x189378E, 0x189378F)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        windows.append((int(flt["fromBlock"], 16), int(flt["toBlock"], 16)))
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload["id"],
            "error": {
                "code": -32005,
                "message": (
                    "block range is too large; try a suggested range of "
                    f"{suggested[0]}-{suggested[1]}"
                ),
            },
        })

    client = _client(handler)
    out = asyncio.run(client._get_logs_shrinking(
        {"address": A.CURATOR}, 0, 100_000, group="deposits"
    ))
    assert out is None, "an unshrinkable sweep must fail honestly, never guess"

    spans = [b - a for a, b in windows]
    assert spans == sorted(spans, reverse=True)
    assert spans[1] <= spans[0] // 2 + 1
    assert len(windows) <= curator_client._LOG_MAX_SHRINKS + 1
    assert suggested not in windows, "the provider's suggested range was adopted"


def test_a_paged_sweep_covers_every_block_and_never_drops_the_bottom() -> None:
    """The shrink must not walk the window's LEFT edge forward.

    ``surf_client`` shrinks by raising ``fromBlock`` — correct for a recent
    window, catastrophic for a backfill, where the blocks it walks past are the
    contract's whole early history and nothing ever asks for them again.
    """
    windows: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        windows.append((int(flt["fromBlock"], 16), int(flt["toBlock"], 16)))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                         "result": []})

    client = _client(handler, log_page_blocks=100)
    asyncio.run(client._get_logs_shrinking(
        {"address": A.CURATOR}, 1_000, 1_249, group="deposits"
    ))
    assert windows[0][0] == 1_000
    assert windows[-1][1] == 1_249
    covered: set[int] = set()
    for lo, hi in windows:
        covered |= set(range(lo, hi + 1))
    assert covered == set(range(1_000, 1_250))


def test_a_shrunk_sweep_still_starts_where_it_was_asked_to() -> None:
    """Same rule, on the shrinking path: the retry re-issues the SAME cursor
    with a narrower span, it does not skip ahead."""
    windows: list[tuple[int, int]] = []
    state = {"errors_left": 2}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        flt = payload["params"][0]
        windows.append((int(flt["fromBlock"], 16), int(flt["toBlock"], 16)))
        if state["errors_left"] > 0:
            state["errors_left"] -= 1
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32005, "message": "block range is too large"},
            })
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                         "result": []})

    client = _client(handler, log_page_blocks=1_000)
    out = asyncio.run(client._get_logs_shrinking(
        {"address": A.CURATOR}, 5_000, 5_400, group="deposits"
    ))
    assert out == []
    assert [w[0] for w in windows[:3]] == [5_000, 5_000, 5_000]


# ===========================================================================
# WP2.4 — the fast view round and the immutable config
# ===========================================================================

#: The 2026-08-16 21:12 UTC round, keyed by selector.  Built from the committed
#: request/response arrays BY ``id`` — never by position: ``isSettled()`` and
#: ``ethNeededThisHour()`` both answered ``0x0`` in this round, so positional
#: reasoning over ``results.json`` cannot tell those two apart.
def _captured_round() -> dict[str, str]:
    blob = client_fixture("state_batch.json")
    by_id = {r["id"]: r for r in blob["responses"]}
    return {
        req["params"][0]["data"]: by_id[req["id"]]["result"]
        for req in blob["requests"]
    }


CAPTURED_ROUND = _captured_round()

#: A plausible head for the captured round.  Any int; the state's own height is
#: what is under test, not its value.
CAPTURED_HEAD = 25770231


def _view_handler(
    answers: dict[str, str],
    *,
    errors: frozenset[str] = frozenset(),
    head: int | None = CAPTURED_HEAD,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer an ``eth_call`` batch by SELECTOR, and ``eth_blockNumber``."""

    def one(entry: dict) -> dict:
        if entry["method"] == "eth_blockNumber":
            if head is None:
                return {"jsonrpc": "2.0", "id": entry["id"],
                        "error": {"code": -32000, "message": "no head"}}
            return {"jsonrpc": "2.0", "id": entry["id"], "result": hex(head)}
        data = entry["params"][0]["data"]
        selector = data[:10]
        if selector in errors:
            return {"jsonrpc": "2.0", "id": entry["id"],
                    "error": {"code": -32000, "message": "execution reverted"}}
        if data not in answers and selector not in answers:
            return {"jsonrpc": "2.0", "id": entry["id"],
                    "error": {"code": -32000, "message": f"unknown {data}"}}
        return {"jsonrpc": "2.0", "id": entry["id"],
                "result": answers.get(data, answers.get(selector))}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if isinstance(payload, list):
            return httpx.Response(200, json=[one(e) for e in payload])
        return httpx.Response(200, json=one(payload))

    return handler


def _state(**kw: Any) -> Any:
    return asyncio.run(_client(_view_handler(CAPTURED_ROUND, **kw)).fetch_state())


def test_fetch_state_decodes_the_captured_round() -> None:
    """Every field, against the real 2026-08-16 21:12 UTC payload."""
    st = _state()
    assert st.settled is False              # a bool, not 0
    assert st.current_hour == 1
    assert st.current_hour_total_wei == 0x27D2C90DCE228AE5B0
    assert st.hour_needed_wei == 0          # grace: a real 0, not a failed read
    assert st.hour_seconds_left == 2796
    assert st.last_active_hour == 1
    assert st.last_active_hour_total_wei == st.current_hour_total_wei
    assert st.early_bps == 19_491           # 1.9491x, NOT ~1.99x
    assert (st.volume_wei, st.contributors, st.tx_count) == (
        0x560119983627C22D4F, 143, 222,
    )
    assert st.block_number == CAPTURED_HEAD


def test_the_balance_is_never_folded_into_the_state_round() -> None:
    """H5: every wei of a deposit is refunded in-transaction, so this balance is
    ALWAYS forced ETH and never a deposit.  ``fetch_state`` leaves it ``None``
    and ``fetch_balance`` is its own read, so nothing can reach a volume, a TVL
    or a hero total by accident."""
    assert _state().forced_balance_wei is None


def test_is_settled_decodes_to_a_bool_not_an_int() -> None:
    """``settled is False`` and ``settled is None`` must be different things.
    An int ``0`` here would make ``if not settled`` true for a failed read too,
    and the phase machine would render a live game as unknown-or-running with
    no way to tell which."""
    assert _state().settled is False
    assert _state(errors=frozenset({A.SEL_IS_SETTLED})).settled is None


def test_a_real_zero_survives_and_a_failed_read_does_not_become_one() -> None:
    """The two zeros of the fast tier, side by side.  ``ethNeededThisHour()``
    answers a genuine 0 all through grace; the same field after a failed entry
    must be ``None``, or HOUR AT RISK reads a dead endpoint as a safe hour."""
    assert _state().hour_needed_wei == 0
    assert _state(errors=frozenset({A.SEL_ETH_NEEDED_THIS_HOUR})).hour_needed_wei \
        is None


def test_the_multi_word_views_are_decoded_to_their_full_width() -> None:
    """``lastActiveHour()`` is 2 words and ``stats()`` is 3.  Decoding word 0
    only would silently drop the hour total and both counters — and the hour
    total is half of the boundary hazard."""
    st = _state()
    assert st.last_active_hour_total_wei == 0x27D2C90DCE228AE5B0
    assert st.contributors == 143 and st.tx_count == 222
    # ... and the decoder itself agrees with the frozen width table.
    for name, _sel in A.FAST_VIEW_SELECTORS:
        raw = CAPTURED_ROUND[_sel]
        assert len(curator_client.decode_view(name, raw)) == \
            A.VIEW_RETURN_WORDS[name], name


def test_a_short_return_decodes_to_none_rather_than_to_zeros() -> None:
    """A reverted ``eth_call`` comes back as ``0x``.  Decoding that as a word of
    zeros manufactures a reading out of a failure — and for ``stats()`` it would
    manufacture three."""
    assert curator_client.decode_view("SEL_STATS", "0x") is None
    one_word = "0x" + "00" * 32
    assert curator_client.decode_view("SEL_STATS", one_word) is None
    assert curator_client.decode_view("SEL_CURRENT_HOUR", one_word) == (0,)


def test_the_batch_is_sent_in_the_frozen_order() -> None:
    """WP0.4 left the ORDER unpinned on purpose; this is where it is pinned.

    The expectation below is **hand-typed, not derived from
    ``FAST_VIEW_SELECTORS``**.  Deriving it would compare a constant against
    itself and the test could never fail again: the client builds its batch FROM
    that tuple, so both sides would move together.  Redundancy plus an agreement
    test is the house pattern (CLAUDE.md, on ``_GAME_CYCLE``).

    One correction to what wp2.md expected of this test.  It says a reorder
    should also make ``test_fetch_state_decodes_the_captured_round`` fail "with
    two fields transposed".  It does not, and that was verified by swapping
    ``SEL_CURRENT_HOUR`` and ``SEL_EARLY_MULTIPLIER_BPS`` in memory and re-running
    both: only this test went red.  The reason is that ``_decode_round`` keys its
    output by selector NAME while indexing the reply by position, and the reply
    was already re-aligned by ``id``, so a name and its result travel together
    and a reorder is self-consistent end to end.  That is the safer arrangement
    and it stays — which is precisely why this test has to exist and has to be
    hand-typed: with the decode immune, an accidental reorder would otherwise be
    invisible everywhere, including in the correspondence between these
    selectors and ``captures/batch.json``'s 21-call round.
    """
    expected_names = [
        "SEL_IS_SETTLED", "SEL_CURRENT_HOUR", "SEL_CURRENT_HOUR_TOTAL",
        "SEL_ETH_NEEDED_THIS_HOUR", "SEL_TIME_LEFT_IN_HOUR",
        "SEL_LAST_ACTIVE_HOUR", "SEL_EARLY_MULTIPLIER_BPS", "SEL_STATS",
    ]
    expected_selectors = [
        "0x3270bb5b", "0x020e185d", "0x78f251f3", "0xa4586257",
        "0x7a7d6632", "0xa8a036f1", "0xd8631b3d", "0xd80528ae",
    ]
    expected_words = [1, 1, 1, 1, 1, 2, 1, 3]

    assert [n for n, _s in A.FAST_VIEW_SELECTORS] == expected_names
    assert [s for _n, s in A.FAST_VIEW_SELECTORS] == expected_selectors
    assert [A.VIEW_RETURN_WORDS[n] for n in expected_names] == expected_words

    client, transport = _recording_client(_view_handler(CAPTURED_ROUND))
    asyncio.run(client.fetch_state())
    sent = [p for _u, _m, p, _h in transport.requests if isinstance(p, list)][0]
    assert [c["params"][0]["data"] for c in sent[:-1]] == expected_selectors
    assert sent[-1]["method"] == "eth_blockNumber"
    assert all(c["params"][0]["to"] == A.CURATOR for c in sent[:-1])


def test_the_whole_fast_tier_is_one_round_trip() -> None:
    """Eight views plus the height in ONE batch array.  A height fetched
    separately can describe a different block from the state it labels."""
    client, transport = _recording_client(_view_handler(CAPTURED_ROUND))
    asyncio.run(client.fetch_state())
    assert len(transport.requests) == 1


def test_one_failed_entry_degrades_one_field() -> None:
    st = _state(errors=frozenset({A.SEL_EARLY_MULTIPLIER_BPS}))
    assert st.early_bps is None
    assert st.current_hour == 1          # everything else survived
    assert st.contributors == 143


def test_a_partial_state_round_still_reports_itself_degraded() -> None:
    """Three views answered and one did not is the NORMAL failure here, and the
    reader is entitled to see it marked — a hole with no marker is a stale
    number presented as live."""
    client = _client(_view_handler(
        CAPTURED_ROUND, errors=frozenset({A.SEL_STATS})))
    st = asyncio.run(client.fetch_state())
    assert st is not None and st.volume_wei is None
    assert client.state_failed is True


def test_a_clean_state_round_clears_the_degradation_flag() -> None:
    client = _client(_view_handler(CAPTURED_ROUND))
    client.state_failed = True           # left over from a previous cycle
    asyncio.run(client.fetch_state())
    assert client.state_failed is False


def test_a_failed_height_does_not_fail_the_state() -> None:
    """The height labels the reading; losing the label does not lose the
    reading, and a ``0`` height would read as genesis."""
    st = _state(head=None)
    assert st.block_number is None and st.current_hour == 1


def test_a_dead_pool_returns_none_not_a_zeroed_state() -> None:
    client = _offline_client()
    assert asyncio.run(client.fetch_state()) is None
    assert client.state_failed is True


def test_fetch_config_decodes_the_ten_once_tier_views() -> None:
    """Read LIVE off the chain, never from the pins in ``curator_addresses``.
    Docs drift; chains do not."""
    cfg = asyncio.run(_client(_view_handler(CAPTURED_ROUND)).fetch_config())
    assert cfg.launch_time == 1_786_910_327
    assert cfg.hourly_threshold_wei == 5 * 10**18
    assert cfg.grace_period == 86_400
    assert cfg.hour_duration == 3_600
    assert cfg.min_deposit_wei == 5 * 10**16
    assert cfg.min_escalation_wei == 10**17
    assert cfg.credit_cap_wei == 1_000 * 10**18
    assert cfg.first_judged_hour == 24
    assert cfg.points_per_eth == 1_000
    assert cfg.deployer == A.DEPLOYER.lower()


def test_the_deployer_is_decoded_as_an_address_not_as_a_number() -> None:
    """The one non-uint in the ``once`` tier.  ``decode_uint`` would render it
    as a 154-digit integer and the allowlist lookup would never match."""
    cfg = asyncio.run(_client(_view_handler(CAPTURED_ROUND)).fetch_config())
    assert isinstance(cfg.deployer, str)
    assert cfg.deployer.startswith("0x") and len(cfg.deployer) == 42


def test_the_config_batch_is_sent_in_the_frozen_order() -> None:
    """Same reasoning as the fast tier, and the same hand-typed expectation."""
    expected = [
        "0x790ca413", "0x9d99a86d", "0xa06db7dc", "0xda25efd9", "0x41b3d185",
        "0x2c379609", "0x1ea0466e", "0x2a9c657f", "0xc99a340f", "0xd5f39488",
    ]
    assert [s for _n, s in A.ONCE_VIEW_SELECTORS] == expected
    client, transport = _recording_client(_view_handler(CAPTURED_ROUND))
    asyncio.run(client.fetch_config())
    sent = [p for _u, _m, p, _h in transport.requests if isinstance(p, list)][0]
    assert [c["params"][0]["data"] for c in sent] == expected


def test_one_failed_config_entry_degrades_one_field() -> None:
    client = _client(_view_handler(
        CAPTURED_ROUND, errors=frozenset({A.SEL_CREDIT_CAP})))
    cfg = asyncio.run(client.fetch_config())
    assert cfg.credit_cap_wei is None
    assert cfg.hourly_threshold_wei == 5 * 10**18
    assert client.config_failed is True


def test_a_dead_pool_returns_no_config_rather_than_a_default_one() -> None:
    client = _offline_client()
    assert asyncio.run(client.fetch_config()) is None
    assert client.config_failed is True


def test_no_documented_config_value_is_hardcoded_in_the_client() -> None:
    """CLAUDE.md rule 4: read values live, never hardcode a documented one.

    The eight immutables are ``immutable`` and ``POINTS_PER_ETH`` is a
    ``constant``, so a fallback would look harmless for as long as it happened
    to be right — which, on this repo's record, is until it isn't (a documented
    5% fee that is 1% on chain; a "4.0x" ratio that measured 3.885, 3.49 and
    2.956 on three consecutive days).
    """
    src = inspect.getsource(curator_client)
    literals = {int(tok.replace("_", ""))
                for tok in re.findall(r"\b\d[\d_]*\b", src)}
    for banned in (86_400, 3_600, 5_000_000_000_000_000_000,
                   1_000_000_000_000_000_000_000, 1_000, 19_491):
        assert banned not in literals, f"{banned} is a chain value, read it live"


# ===========================================================================
# WP2.5 — the per-wallet view batch
# ===========================================================================

#: ``pointsOf``/``weightOf`` for leaderboard #1, read off the chain at
#: 2026-08-16 22:51:43 UTC and committed in
#: ``captures/live/20260816T225143Z_curve-probe.json``.  Real values, not
#: invented ones: the points are the contract's own answer for that weight.
LEADER_1 = "0x381fe486d87c7f2633c777f1b5be3105a2a51744"
LEADER_1_POINTS = 0x7553                    # 30_035
LEADER_1_WEIGHT = 0x30E7413171FFE0A000

#: The remaining four wallet views were never captured for any address (the
#: research round holds only parameterless calls plus these two).  These four
#: words are hand-built to exercise the decode, not to assert a chain fact — no
#: assertion below treats them as one.
_W_CONTRIBUTED = 462_200_000_000_000_000_000
_W_TX_COUNT = 2
_W_REQUIRED_NEXT = 462_300_000_000_000_000_000


def _words(*values: int) -> str:
    return "0x" + "".join(f"{v:064x}" for v in values)


def _wallet_answers(**override: str) -> dict[str, str]:
    answers = {
        A.SEL_POINTS_OF: _words(LEADER_1_POINTS),
        A.SEL_WEIGHT_OF: _words(LEADER_1_WEIGHT),
        A.SEL_CONTRIBUTED_BY: _words(_W_CONTRIBUTED),
        A.SEL_TX_COUNT_OF: _words(_W_TX_COUNT),
        A.SEL_REQUIRED_NEXT: _words(_W_REQUIRED_NEXT),
        A.SEL_FIRST_HOUR_OF: _words(0, 1),
    }
    answers.update(override)
    return answers


def _wallet_returning(override: dict[str, str] | None = None,
                      errors: frozenset[str] = frozenset()) -> Any:
    handler = _view_handler(_wallet_answers(**(override or {})), errors=errors)
    return asyncio.run(_client(handler).fetch_wallet(LEADER_1))


def test_fetch_wallet_decodes_the_six_argument_taking_views() -> None:
    ws = _wallet_returning()
    assert ws.address == LEADER_1
    assert ws.points == LEADER_1_POINTS
    assert ws.weight_wei == LEADER_1_WEIGHT
    assert ws.contributed_wei == _W_CONTRIBUTED
    assert ws.tx_count == _W_TX_COUNT
    assert ws.required_next_wei == _W_REQUIRED_NEXT


def test_first_hour_of_un_shifts_and_reports_joined_separately() -> None:
    """H6.  ``firstHourOf`` returns ``(0, false)`` for a stranger and
    ``(0, true)`` for an hour-0 founder.  The client must never collapse them,
    and must never read the raw ``contributors()`` struct field, which carries
    the ``+1``."""
    stranger = _wallet_returning({A.SEL_FIRST_HOUR_OF: _words(0, 0)})
    founder = _wallet_returning({A.SEL_FIRST_HOUR_OF: _words(0, 1)})
    assert (stranger.first_hour, stranger.has_joined) == (0, False)
    assert (founder.first_hour, founder.has_joined) == (0, True)
    # ...and the bit is a bool, so a failed read stays distinguishable from both.
    assert stranger.has_joined is False
    assert _wallet_returning(errors=frozenset({A.SEL_FIRST_HOUR_OF})).has_joined \
        is None


def test_the_client_never_calls_the_raw_contributors_getter() -> None:
    """It packs ``firstHour + 1`` so that 0 can mean "never deposited".  Reading
    it un-shifted renders every hour-0 founder as an hour-1 depositor, and every
    stranger as a founder."""
    assert "SEL_CONTRIBUTORS" not in inspect.getsource(curator_client)


def test_required_next_is_the_wei_the_wallet_must_send() -> None:
    """Quoted so nobody burns gas on ``MustEscalate``.  A ``None`` renders the
    unavailable state; a ``0`` would read as "send anything"."""
    assert _wallet_returning().required_next_wei == _W_REQUIRED_NEXT
    assert _wallet_returning(
        errors=frozenset({A.SEL_REQUIRED_NEXT})).required_next_wei is None


def test_an_address_argument_is_left_padded_without_an_inner_0x() -> None:
    """The Multicall3 lesson applies to plain ``eth_call`` data too: an inner
    ``0x`` makes the node reject the payload."""
    client, transport = _recording_client(_view_handler(_wallet_answers()))
    asyncio.run(client.fetch_wallet(LEADER_1))
    sent = [p for _u, _m, p, _h in transport.requests if isinstance(p, list)][0]
    by_selector = {c["params"][0]["data"][:10]: c["params"][0]["data"] for c in sent}
    data = by_selector[A.SEL_POINTS_OF]
    assert data.count("0x") == 1 and len(data) == 10 + 64
    assert data.endswith(LEADER_1[2:].lower())


def test_the_wallet_batch_is_sent_in_the_frozen_order() -> None:
    """Hand-typed, for the reason spelled out on the fast tier's twin."""
    expected = ["0xcf6a4403", "0xdd4bc101", "0x64a8e570",
                "0x662d7299", "0xa5f88754", "0xc5148173"]
    assert [s for _n, s in A.WALLET_VIEW_SELECTORS] == expected
    client, transport = _recording_client(_view_handler(_wallet_answers()))
    asyncio.run(client.fetch_wallet(LEADER_1))
    sent = [p for _u, _m, p, _h in transport.requests if isinstance(p, list)][0]
    assert [c["params"][0]["data"][:10] for c in sent] == expected
    assert len(transport.requests) == 1, "six views, one round trip"


def test_one_failed_wallet_entry_degrades_one_field() -> None:
    client = _client(_view_handler(_wallet_answers(),
                                   errors=frozenset({A.SEL_WEIGHT_OF})))
    ws = asyncio.run(client.fetch_wallet(LEADER_1))
    assert ws.weight_wei is None and ws.points == LEADER_1_POINTS
    assert client.wallet_failed is True


def test_a_dead_pool_returns_no_wallet_rather_than_an_empty_one() -> None:
    client = _offline_client()
    assert asyncio.run(client.fetch_wallet(LEADER_1)) is None
    assert client.wallet_failed is True


def test_an_unusable_address_costs_no_request_at_all() -> None:
    """``--wallet`` is user input and ``MAXPANE_WALLET`` is environment input.
    Neither is validated upstream, and a batch of six calls against ``"me"``
    spends a round trip to be told what a length check knows for free.

    ``_raising_client`` is the double here precisely because it proves the
    absence of I/O rather than tolerating it.
    """
    for bad in ("", "   ", "me", "0x", "0xnothex" + "0" * 32,
                "0x381fe486d87c7f2633c777f1b5be3105a2a517"):
        client = _raising_client()
        assert asyncio.run(client.fetch_wallet(bad)) is None
        assert client.wallet_failed is True


# ===========================================================================
# WP2.6 — the contract balance, which is never a balance
# ===========================================================================


def test_a_zero_balance_is_the_expected_reading_not_a_failure() -> None:
    """H5.  Every wei of a deposit is refunded inside the same transaction, so
    between transactions this balance is **exactly zero** — and every live
    bundle captured so far reads ``0x0``.  A ``None`` here would mark the normal
    state as unavailable and light an anomaly row that has nothing behind it."""
    assert asyncio.run(_client(_rpc_ok("0x0")).fetch_balance()) == 0


def test_the_captured_bundles_agree_that_the_balance_is_zero() -> None:
    """Provenance for the paragraph above, read out of WP1's bundles rather
    than asserted from memory.  Skipped, never failed, when no bundle carries
    the field — ``captures/live/`` grows while this suite is being written."""
    from tests.curator_fixtures import live_bundles

    seen = []
    for path in live_bundles():
        body = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(body, dict) and "balance" in body:
            seen.append(body["balance"])
    if not seen:
        pytest.skip("no live bundle carries a balance yet")
    assert all(_hex(v) == 0 for v in seen if v is not None), seen


def _hex(value: Any) -> int | None:
    return None if not isinstance(value, str) else int(value, 16)


def test_a_nonzero_balance_decodes_to_forced_wei() -> None:
    """Anything nonzero got here by ``selfdestruct`` or by a builder naming the
    contract as fee recipient.  It is an anomaly to surface, not income."""
    assert asyncio.run(
        _client(_rpc_ok("0x16345785d8a0000")).fetch_balance()
    ) == 10**17


def test_a_dead_pool_gives_no_balance_rather_than_zero() -> None:
    """The one place the distinction bites hardest: ``0`` is the *expected*
    reading, so an outage coerced to ``0`` is indistinguishable from health."""
    assert asyncio.run(_offline_client().fetch_balance()) is None


def test_the_balance_is_never_folded_into_a_volume() -> None:
    """Structural, not stylistic: the balance leaves this module as its own
    ``int`` return, and no client method fills ``CuratorState``'s volume — or
    even its own ``forced_balance_wei`` — from it.  Nothing downstream can add
    forced ETH to a routed total by reading a state object."""
    client = _client(_view_handler(CAPTURED_ROUND))
    st = asyncio.run(client.fetch_state())
    assert st.forced_balance_wei is None
    assert st.volume_wei == 0x560119983627C22D4F  # stats(), untouched
    body = inspect.getsource(curator_client.CuratorClient.fetch_balance).replace(
        curator_client.CuratorClient.fetch_balance.__doc__ or "", ""
    )
    assert "CuratorState" not in body, "the balance leaked into a state object"


def test_the_balance_read_goes_to_the_state_pool() -> None:
    """``eth_getBalance`` is state, and the pools do not cross."""
    client, transport = _recording_client(_rpc_ok("0x0"))
    asyncio.run(client.fetch_balance())
    url, _m, payload, _h = transport.requests[0]
    assert STATE_PRIMARY_HOST in url
    assert payload["method"] == "eth_getBalance"
    assert payload["params"] == [A.CURATOR, "latest"]


# ===========================================================================
# WP2.7 — the six event groups out of one address sweep
# ===========================================================================

#: The 377 rows tenderly served for the whole history on 2026-08-16, read in
#: place out of WP0's capture (the file is the full JSON-RPC envelope; the rows
#: live under ``result``).
FULL_SWEEP_ROWS = capture("tenderly_logs.json")["result"]

#: A head comfortably above the last captured log, so one page covers the lot.
SWEEP_HEAD = 25_770_400


def _logs_handler(
    rows: list[dict],
    *,
    fail_topics: frozenset[str] = frozenset(),
    fail_combined: bool = False,
    head: int | None = SWEEP_HEAD,
) -> Callable[[httpx.Request], httpx.Response]:
    """Serve *rows* for an address sweep, filtered when a topic0 is asked for.

    ``fail_combined`` makes the topic0-OR sweep fail so the per-topic fallback
    is what answers; ``fail_topics`` fails individual per-topic filters.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        rid = payload["id"]
        if payload["method"] == "eth_blockNumber":
            if head is None:
                return httpx.Response(200, json={
                    "jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32000, "message": "no head"}})
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": rid,
                                             "result": hex(head)})
        topics = (payload["params"][0].get("topics") or [[]])[0]
        wanted = topics if isinstance(topics, list) else [topics]
        if (len(wanted) > 1 and fail_combined) or (
            len(wanted) == 1 and wanted[0] in fail_topics
        ):
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32000, "message": "filter unavailable"}})
        keep = {t.lower() for t in wanted}
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": rid,
            "result": [r for r in rows if r["topics"][0].lower() in keep]})

    return handler


def test_the_full_history_sweep_groups_every_event() -> None:
    """The counts are the capture's own, re-derived here rather than quoted:
    wave 1 found the plan's 226 was wrong (it is 231), so the arithmetic is
    written out where a re-capture would move it."""
    client = _client(_logs_handler(FULL_SWEEP_ROWS))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert len(FULL_SWEEP_ROWS) == 377
    assert len(sweep.deposits) == 231
    assert len(sweep.first_deposits) == 145
    assert len(sweep.launched) == 1
    assert 1 + 231 + 145 == 377
    assert sweep.hour_saved == () and sweep.settled == () and sweep.rescued == ()
    # ...and () for a group that never fired is NOT the same as a failed filter:
    assert not any(client.log_group_failed.values())
    assert client.logs_failed is False
    assert (sweep.from_block, sweep.to_block) == (A.CREATION_BLOCK, SWEEP_HEAD)


def test_one_address_scoped_sweep_answers_all_six_groups() -> None:
    """The research proved a single address-scoped filter with a topic0 OR array
    returns all 377 rows in one call.  Six per-topic filters would be six round
    trips on every refresh for the same bytes."""
    client, transport = _recording_client(_logs_handler(FULL_SWEEP_ROWS))
    asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    get_logs = [p for _u, _m, p, _h in transport.requests
                if isinstance(p, dict) and p["method"] == "eth_getLogs"]
    assert len(get_logs) == 1
    flt = get_logs[0]["params"][0]
    assert flt["address"] == A.CURATOR
    assert sorted(t.lower() for t in flt["topics"][0]) == sorted(
        t.lower() for t in (A.TOPIC_LAUNCHED, A.TOPIC_DEPOSITED,
                            A.TOPIC_FIRST_DEPOSIT, A.TOPIC_HOUR_SAVED,
                            A.TOPIC_SETTLED, A.TOPIC_RESCUED)
    )


def test_the_sweep_goes_to_the_logs_pool_and_never_to_publicnode() -> None:
    client, transport = _recording_client(_logs_handler(FULL_SWEEP_ROWS))
    asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert transport.requests
    assert all(STATE_PRIMARY_HOST not in url for url, *_rest in transport.requests)


def test_a_raw_row_survives_grouping_untouched() -> None:
    """The decoders are WP3/WP5's; this client normalises nothing away.

    ``logIndex`` in particular: PRD §4 de-dupes activity rows by (tx, log
    index), and a client that dropped it would make that impossible while every
    test stayed green.  ``blockTimestamp`` likewise — wave 1 proved every
    captured row carries one, and discarding it costs a round trip to re-fetch
    what we were already handed.
    """
    sweep = asyncio.run(_client(_logs_handler(FULL_SWEEP_ROWS))
                        .fetch_logs(A.CREATION_BLOCK))
    row = sweep.deposits[0]
    assert {"topics", "data", "blockNumber", "transactionHash", "logIndex",
            "blockTimestamp"} <= set(row)
    assert len(row["topics"]) == 3          # topic0 + contributor + hour
    assert row in FULL_SWEEP_ROWS           # identity, not a rebuilt copy


def test_the_deposit_hour_comes_from_the_indexed_topic() -> None:
    """H2's foundation: the hour is ``topics[2]``, so the hourly series needs no
    timestamp and no state read.  A client that only exposed ``data`` would push
    the fold back onto ``currentHourTotal()``, which zeroes at every boundary."""
    sweep = asyncio.run(_client(_logs_handler(FULL_SWEEP_ROWS))
                        .fetch_logs(A.CREATION_BLOCK))
    hours = {int(r["topics"][2], 16) for r in sweep.deposits}
    assert hours and min(hours) >= 0
    assert hours == {0, 1}, "the 2026-08-16 capture spans hours 0 and 1 only"


def test_a_group_that_never_fired_reads_as_empty_and_not_failed() -> None:
    """HourSaved, Settled and Rescued have never fired.  Their rows must render
    an explicit never-fired state, which needs ``()`` **and** a ``False`` in the
    failure dict — either alone is ambiguous."""
    client = _client(_logs_handler(FULL_SWEEP_ROWS))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    for group in ("hour_saved", "settled", "rescued"):
        assert getattr(sweep, group) == ()
        assert client.log_group_failed[group] is False


def test_the_endgame_rows_group_correctly_when_they_finally_fire() -> None:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # HourSaved / Settled / Rescued have never fired on chain; capture C's
    # window is 2026-08-17 20:58:47 UTC at the earliest and it is one-shot.
    # Only the ABI's indexed-ness is asserted here, never a value.
    rows = client_fixture("logs_settled_row.json")["rows"]
    client = _client(_logs_handler(rows))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert len(sweep.settled) == 1
    assert len(sweep.hour_saved) == 1
    assert len(sweep.rescued) == 1
    assert sweep.deposits == () and sweep.launched == ()
    assert not any(client.log_group_failed.values())


def test_an_empty_sweep_is_a_reading_not_a_failure() -> None:
    rows = client_fixture("logs_empty.json")["rows"]
    client = _client(_logs_handler(rows))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert sweep is not None
    assert all(getattr(sweep, g) == () for g in curator_client.LOG_GROUPS)
    assert not any(client.log_group_failed.values())
    assert client.logs_failed is False


def test_one_failed_group_is_reported_out_of_band_not_as_an_empty_tuple() -> None:
    """A frozen tuple cannot hold ``None``, so ``()`` is ambiguous on its own.
    The dict is what resolves it — and without it a dead ``Settled`` filter
    would read as "the game is alive"."""
    client = _client(_logs_handler(
        FULL_SWEEP_ROWS, fail_combined=True,
        fail_topics=frozenset({A.TOPIC_SETTLED}),
    ))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert sweep.settled == ()
    assert client.log_group_failed["settled"] is True
    assert len(sweep.deposits) == 231           # the healthy groups still landed
    assert client.log_group_failed["deposits"] is False
    assert client.logs_failed is False          # partial, not total


def test_the_combined_sweep_falls_back_to_per_topic_filters() -> None:
    """One filter is the cheap path, not the only one.  An endpoint that refuses
    a topic0 OR array must not cost the whole sweep."""
    client, transport = _recording_client(
        _logs_handler(FULL_SWEEP_ROWS, fail_combined=True))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert len(sweep.deposits) == 231 and len(sweep.first_deposits) == 145
    assert not any(client.log_group_failed.values())
    get_logs = [p for _u, _m, p, _h in transport.requests
                if isinstance(p, dict) and p["method"] == "eth_getLogs"]
    filters = [p["params"][0]["topics"][0] for p in get_logs]
    # The OR array is tried first (once per endpoint — it rotates before it
    # gives up), then exactly one scalar filter per event.
    assert isinstance(filters[0], list)
    scalars = [t for t in filters if isinstance(t, str)]
    assert sorted(scalars) == sorted(
        t.lower() for t in (A.TOPIC_LAUNCHED, A.TOPIC_DEPOSITED,
                            A.TOPIC_FIRST_DEPOSIT, A.TOPIC_HOUR_SAVED,
                            A.TOPIC_SETTLED, A.TOPIC_RESCUED)
    )


def test_every_group_failing_returns_none_not_a_hollow_sweep() -> None:
    client = _offline_client()
    assert asyncio.run(client.fetch_logs(A.CREATION_BLOCK)) is None
    assert client.logs_failed is True
    assert all(client.log_group_failed.values())


def test_a_dead_head_read_fails_every_group_rather_than_none_of_them() -> None:
    """No filter was even attempted, so every group is exactly as unread as the
    head itself.  Leaving them ``False`` would report a sweep that never
    happened as clean."""
    client = _client(_logs_handler(FULL_SWEEP_ROWS, head=None))
    assert asyncio.run(client.fetch_logs(A.CREATION_BLOCK)) is None
    assert all(client.log_group_failed.values())


def test_an_explicit_to_block_costs_no_head_read() -> None:
    """The incremental tier already knows where it stopped."""
    client, transport = _recording_client(_logs_handler(FULL_SWEEP_ROWS))
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK, SWEEP_HEAD))
    assert sweep.to_block == SWEEP_HEAD
    assert not any(p["method"] == "eth_blockNumber"
                   for _u, _m, p, _h in transport.requests if isinstance(p, dict))


def test_the_failure_dict_is_reset_at_the_start_of_every_call() -> None:
    """"True right now", never "true once, ever".  A flag left standing from a
    previous cycle degrades a healthy dashboard until restart."""
    client = _client(_logs_handler(FULL_SWEEP_ROWS))
    client.log_group_failed = {g: True for g in curator_client.LOG_GROUPS}
    client.logs_failed = True
    asyncio.run(client.fetch_logs(A.CREATION_BLOCK))
    assert not any(client.log_group_failed.values())
    assert client.logs_failed is False


def test_a_row_repeated_across_pages_is_counted_once() -> None:
    """Pages are half-open by construction, but a retried page or an endpoint
    that overlaps its own window would otherwise double every deposit in the
    leaderboard.  (tx hash, log index) is the same key PRD §4 de-dupes on."""
    client = _client(_logs_handler(FULL_SWEEP_ROWS), log_page_blocks=100)
    sweep = asyncio.run(client.fetch_logs(A.CREATION_BLOCK, A.CREATION_BLOCK + 999))
    assert len(sweep.deposits) == 231
