"""WP2.3 — the keyless failover fetchers.

**Zero network.**  Every test drives a fetcher through an
``httpx.MockTransport``; nothing here opens a socket, and
``test_no_test_in_this_file_builds_a_client_without_a_transport`` is the
structural proof (an AST scan, mirroring
``tests/data/test_curator_client.py``) rather than a promise.

What the doubles are for, in one line each:

``_handler``
    Answers whatever the test wants and records what it was asked.

``_offline``
    Raises ``httpx.ConnectError`` on every request — the total-outage double.
    Not ``AssertionError``: ``MockTransport`` does not wrap a handler
    exception, and an ``AssertionError`` is caught by none of the fetchers'
    ``except`` clauses, so it would propagate instead of exercising the
    degrade-to-``None`` contract.

``_never``
    Raises ``AssertionError`` — for the paths that must issue **no request at
    all**, where propagation is exactly the behaviour we want.
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

httpx = pytest.importorskip(
    "httpx",
    reason="sybilkit[sources] is an extra; the core suite runs without it",
)

from sybilkit import Deposit, Funding, Tx  # noqa: E402
from sybilkit import sources  # noqa: E402
from sybilkit.sources import SourceConfig, blockscout, logs, txs  # noqa: E402

CONTRACT = "0x8fF23e0Bd8b6f8f1cDb54B0dFC0c1F30d5fFCbd8"
THIS_FILE = Path(__file__).resolve()

#: A config with every delay at zero — the *pacing* is asserted separately, by
#: injecting a recording ``sleep``; making every other test wait for it would
#: buy nothing but seconds.
FAST = SourceConfig(inter_call_delay=0.0, backoff_seconds=(0.0, 0.0),
                    blockscout_min_interval=0.0)


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


class Recorder:
    """Records ``(method, url, payload, headers)`` for every request."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler
        self.calls: list[tuple[str, httpx.URL, Any, httpx.Headers]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload: Any = None
        if request.content:
            try:
                payload = json.loads(request.content)
            except ValueError:
                payload = None
        self.calls.append((request.method, request.url, payload, request.headers))
        return self._handler(request)

    @property
    def payloads(self) -> list[Any]:
        return [c[2] for c in self.calls]

    @property
    def urls(self) -> list[str]:
        return [str(c[1]) for c in self.calls]


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _offline(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"no sockets here: {request.url}", request=request)


def _never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(f"a request that must not happen: {request.url}")


def _rpc_result(result: Any) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


def _rpc_error(code: int, message: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, json={"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": message}}
    )


def _sleeper() -> tuple[Callable[[float], Any], list[float]]:
    """An awaitable ``sleep`` double that records instead of waiting."""
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    return sleep, waits


# ---------------------------------------------------------------------------
# Log-row builders
# ---------------------------------------------------------------------------


def _word(value: int) -> str:
    return f"{value:064x}"


def _addr_topic(addr: str) -> str:
    return "0x" + "0" * 24 + addr.lower().removeprefix("0x")


def deposited_row(
    addr: str, *, hour: int, amount: int, block: int, log_index: int,
    weight: int | None = None, tx_hash: str | None = None, ts: int | None = None,
) -> dict:
    weight = amount if weight is None else weight
    data = "".join(
        _word(v)
        for v in (amount, amount, weight, weight, 1, amount, 10_000)
    )
    row = {
        "address": CONTRACT.lower(),
        "topics": [logs.DEPOSITED_TOPIC, _addr_topic(addr), hex(hour)],
        "data": "0x" + data,
        "blockNumber": hex(block),
        "logIndex": hex(log_index),
        "transactionHash": tx_hash or ("0x" + f"{block:04x}{log_index:04x}".rjust(64, "a")),
    }
    if ts is not None:
        row["blockTimestamp"] = hex(ts)
    return row


def first_deposit_row(addr: str, *, index: int, block: int, log_index: int, ts: int = 0) -> dict:
    return {
        "address": CONTRACT.lower(),
        "topics": [logs.FIRST_DEPOSIT_TOPIC, _addr_topic(addr), hex(index)],
        "data": "0x" + _word(ts),
        "blockNumber": hex(block),
        "logIndex": hex(log_index),
        "transactionHash": "0x" + f"{block:04x}{log_index:04x}".rjust(64, "b"),
    }


ALICE = "0x1111111111111111111111111111111111111111"
BOB = "0x2222222222222222222222222222222222222222"


# ===========================================================================
# keccak — the ABI identifiers are COMPUTED, never pasted
# ===========================================================================


def test_keccak_reproduces_the_empty_string_digest() -> None:
    """The canonical Keccak-256 test vector.  If this is wrong, every topic and
    every selector below is wrong in a way that looks plausible."""
    assert sources.keccak256_hex(b"") == (
        "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    )


def test_the_view_selectors_are_derived_not_remembered() -> None:
    """Two independent derivations agreeing.

    The right-hand side is what maxpane vendored for this deployment, where it
    is checked against ``captures/source.sol`` *and* against the ABI; the
    left-hand side is this package computing the same thing from the signature
    with its own keccak.  That is why the CLI can honour rulings R10/R13 by
    **reading** ``POINTS_PER_ETH`` and ``minDeposit`` off the chain instead of
    carrying someone's memory of 1000 and 0.05.
    """
    assert sources.selector("minDeposit()") == "0x41b3d185"
    assert sources.selector("POINTS_PER_ETH()") == "0xc99a340f"


def test_the_event_topics_are_derived_not_remembered() -> None:
    assert logs.DEPOSITED_TOPIC == (
        "0xb83850979ca63333b482bfe84d4d7cf15f9cc15c139b1e48bc44eb5446669cb3"
    )
    assert logs.FIRST_DEPOSIT_TOPIC == (
        "0xe5a1ae9630942d7510b794ac6b487f13176cf55b27415ad75303dd3109242918"
    )
    assert sources.event_topic(logs.DEPOSITED_SIGNATURE) == logs.DEPOSITED_TOPIC


# ===========================================================================
# Keyless: the banned-host frozenset rejects at construction
# ===========================================================================


@pytest.mark.parametrize(
    "url",
    [
        "https://eth.llamarpc.com",           # HTTP 521, origin down
        "https://rpc.ankr.com/eth",           # now requires a key
        "https://cloudflare-eth.com",         # -32046 on Ethereum
        "https://api.reservoir.tools/x",      # sunset, DNS gone
        "https://eth-mainnet.g.alchemy.com/v2/KEY",
        "https://mainnet.infura.io/v3/KEY",
        "https://api.etherscan.io/api",
    ],
)
def test_a_dead_or_keyed_host_is_refused_at_construction(url: str) -> None:
    """The ``curator_client`` precedent: a mistake is a ``ValueError`` at
    wiring time, not a session that quietly renders unavailable.  A keyed
    endpoint in a keyless tool is a bug, never a fallback."""
    with pytest.raises(ValueError):
        SourceConfig(log_rpcs=(url,))
    with pytest.raises(ValueError):
        SourceConfig(state_rpcs=(url,))
    with pytest.raises(ValueError):
        SourceConfig(blockscout_base=url)


def test_the_default_endpoints_are_the_three_verified_keyless_ones() -> None:
    cfg = SourceConfig()
    assert cfg.log_rpcs[0] == "https://gateway.tenderly.co/public/mainnet"
    assert "https://eth.drpc.org" in cfg.log_rpcs
    assert cfg.state_rpcs[0] == "https://ethereum-rpc.publicnode.com"
    # publicnode refuses archive eth_getLogs; including it in the log pool
    # spends a round trip and a retry before rotating to one that can answer.
    assert not any("publicnode" in u for u in cfg.log_rpcs)
    assert cfg.blockscout_base.startswith("https://eth.blockscout.com/api/v2")


# ===========================================================================
# logs.fetch_deposits — chunking, failover, the livelock
# ===========================================================================


def test_a_first_sweep_pulls_the_whole_history_in_eight_hundred_block_chunks() -> None:
    rows = [
        deposited_row(ALICE, hour=0, amount=45 * 10**16, block=1_000, log_index=1,
                      ts=1_700_000_000),
        first_deposit_row(ALICE, index=1, block=1_000, log_index=0, ts=1_700_000_000),
        deposited_row(BOB, hour=1, amount=45 * 10**16, block=2_500, log_index=3),
        first_deposit_row(BOB, index=2, block=2_500, log_index=2),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(2_599))
        flt = body["params"][0]
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        return _rpc_result([r for r in rows if lo <= int(r["blockNumber"], 16) <= hi])

    rec = Recorder(handler)
    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 1_000, client=_client(rec), config=FAST)
    )
    assert sweep is not None
    spans = [
        (int(p["params"][0]["fromBlock"], 16), int(p["params"][0]["toBlock"], 16))
        for p in rec.payloads
        if p["method"] == "eth_getLogs"
    ]
    assert spans == [(1_000, 1_799), (1_800, 2_599)]
    assert [d.contributor for d in sweep.deposits] == [ALICE.lower(), BOB.lower()]
    assert sweep.deposits[0].amount_wei == 45 * 10**16
    assert sweep.deposits[0].hour == 0
    assert sweep.deposits[0].ts == 1_700_000_000.0
    assert sweep.from_block == 1_000 and sweep.to_block == 2_599
    assert [r["index"] for r in sweep.first_deposits] == [1, 2]


def test_the_sweep_builds_a_dataset_the_core_can_detect_on() -> None:
    rows = [
        deposited_row(ALICE, hour=0, amount=10**17, block=10, log_index=1),
        first_deposit_row(ALICE, index=1, block=10, log_index=0),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(10))
        return _rpc_result(rows)

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None
    ds = sweep.dataset()
    assert isinstance(sweep.deposits[0], Deposit)
    assert ds.first_index == {ALICE.lower(): 1}
    assert len(ds.deposits) == 1 and ds.txs == {} and ds.funding == {}


def test_a_chunk_failure_fails_over_to_the_next_endpoint_on_message_text() -> None:
    """drpc's routing failure arrives wearing ``-32602``, which other providers
    spend on a genuinely malformed request.  Classification is on the
    **message**, so the healthy query rotates instead of being binned."""
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        body = json.loads(request.content)
        if request.url.host == "gateway.tenderly.co":
            return _rpc_error(-32602, "Can't route your request. Try again later.")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        return _rpc_result([])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None
    assert "gateway.tenderly.co" in served and "eth.drpc.org" in served


def test_a_malformed_request_short_circuits_instead_of_rotating() -> None:
    """OUR bug fails identically everywhere, so rotating on it triples the
    request count and hides it.  The sweep degrades to ``None`` after the first
    endpoint rather than walking the pool."""
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        return _rpc_error(-32602, "invalid argument 0: hex string without 0x prefix")

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None
    assert served.count("eth.drpc.org") == 0


def test_a_two_hundred_html_body_rotates_to_the_next_endpoint() -> None:
    """**Review #3, the reproduced case.**  A 200 whose body is not JSON-RPC is
    not an answer.

    An endpoint behind a proxy that has fallen over answers ``200 text/html``.
    ``resp.json()`` raised, ``body`` became ``None``, and the final line handed
    that ``None`` straight back **without rotating** — so a healthy second
    endpoint was never asked.  ``rpc_batch`` already rotated on the same input
    (``not isinstance(body, list)``), and that asymmetry is the proof the intent
    was rotation all along.
    """
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        if request.url.host == "gateway.tenderly.co":
            return httpx.Response(200, text="<html><body>502 Bad Gateway</body></html>")
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        return _rpc_result([])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert "eth.drpc.org" in served, served
    assert sweep is not None
    assert sweep.to_block == 100


def test_a_two_hundred_bare_array_body_is_not_a_completed_sweep() -> None:
    """The same defect's quieter half, and the dangerous one.

    A single JSON-RPC answer is an **object** by spec, even when its ``result``
    is a list.  A bare ``[]`` came back verbatim, ``_page`` accepted it as a
    page of zero logs, and ``fetch_deposits`` completed an *empty* sweep —
    "this contract has no history", during an outage.  That is the one
    conclusion an outage must never reach.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        return httpx.Response(200, json=[])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None


def test_an_unreadable_body_from_every_endpoint_degrades_to_none_not_an_empty_history() -> None:
    """And when nobody can be read, the pool is walked first and the answer is
    ``None`` — never a sweep of zero deposits."""
    rec = Recorder(lambda r: httpx.Response(200, text="upstream connect error"))
    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(rec), config=FAST)
    )
    assert sweep is None
    hosts = {u.split("/")[2] for u in rec.urls}
    assert len(hosts) > 1, rec.urls  # it really did rotate


def test_a_providers_suggested_retry_range_is_never_adopted() -> None:
    """**The mandated livelock bite.**

    One real provider answers a too-wide window with a *suggested* range that
    decrements by a single block per round trip.  A client that follows the
    suggestion verbatim never converges: it asks for 800, is told 799, asks for
    799, is told 798, forever.  We halve **our own** span instead, at most
    ``max_shrinks`` times, then fail honestly.

    Asserted three ways, because only all three together exclude the livelock:
    the requested spans strictly halve; the suggestion is never echoed back;
    and the total number of round trips is bounded.
    """
    suggested = {"value": 799}
    spans: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(5_000))
        flt = body["params"][0]
        span = int(flt["toBlock"], 16) - int(flt["fromBlock"], 16) + 1
        spans.append(span)
        suggested["value"] -= 1
        return _rpc_error(
            -32602,
            "query returned more than 10000 results, "
            f"retry with a range of {suggested['value']} blocks",
        )

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None
    assert len(spans) <= 16, spans          # bounded: no livelock
    assert spans[0] == FAST.log_chunk_blocks
    halving = [s for s in spans if s != spans[0]]
    assert halving, "the window never shrank at all"
    assert all(b <= a for a, b in zip(spans, spans[1:]))
    # never the provider's number, at any point
    assert not any(797 <= s <= 799 for s in spans), spans


def test_shrinking_narrows_the_right_edge_and_keeps_the_cursor() -> None:
    """``surf_client`` shrinks by raising ``fromBlock``, which is correct for a
    rolling recent window and catastrophic for a backfill: the blocks it walks
    past are this contract's whole early history and nothing ever asks for them
    again."""
    seen: list[tuple[int, int]] = []
    state = {"refused": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(1_599))
        flt = body["params"][0]
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        seen.append((lo, hi))
        if state["refused"] < 1:
            state["refused"] += 1
            return _rpc_error(-32005, "query returned more than 10000 results")
        return _rpc_result([])

    asyncio.run(logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST))
    assert seen[0] == (0, 799)
    assert seen[1][0] == 0, seen  # same cursor, narrower window
    assert seen[1][1] < 799


def test_a_throttle_message_that_looks_like_a_range_cap_still_rotates_the_pool() -> None:
    """**Review #11(i), the reproduced case.**  Shrinking is not a substitute
    for rotating.

    "You are limited to 100 requests per second" is a *throttle*, but it
    contains ``limited to`` and is therefore classified ``RangeTooWide``.  The
    walk then halved its window 800 → 50 against the **same** endpoint and gave
    up, with the healthy second endpoint receiving nothing at all.  Shrink
    exhaustion now drops the head of the pool and carries on from the same
    cursor.
    """
    served: list[str] = []
    row = deposited_row(ALICE, hour=0, amount=10**17, block=7, log_index=1)

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        if request.url.host == "gateway.tenderly.co":
            return _rpc_error(-32005, "You are limited to 100 requests per second")
        flt = body["params"][0]
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        return _rpc_result([row] if lo <= 7 <= hi else [])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None, "the throttled endpoint took the whole sweep down"
    assert [d.contributor for d in sweep.deposits] == [ALICE.lower()]
    assert "eth.drpc.org" in served, served


def test_the_second_endpoint_receives_a_request_before_the_sweep_fails() -> None:
    """The minimum statement of the same defect: when the sweep does fail, it
    fails having asked **everybody**.  Before the fix the second endpoint's
    request count was zero."""
    getlogs: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(5_000))
        getlogs.append(request.url.host or "")
        return _rpc_error(-32005, "query returned more than 10000 results")

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None
    assert getlogs.count("eth.drpc.org") >= 1, getlogs


def test_a_narrowed_span_recovers_after_a_run_of_clean_chunks() -> None:
    """**Review #11(ii).**  One dense region used to narrow the window for the
    whole rest of the walk — 16× the requests for every later chunk, on a
    history that is dense in one place and empty everywhere else.  After
    ``SPAN_RECOVER_AFTER`` clean chunks the span doubles back toward
    ``log_chunk_blocks``."""
    spans: list[int] = []
    state = {"refused": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(6_000))
        flt = body["params"][0]
        lo, hi = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        spans.append(hi - lo + 1)
        if state["refused"] < 1:
            state["refused"] += 1
            return _rpc_error(-32005, "query returned more than 10000 results")
        return _rpc_result([])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None
    assert logs.SPAN_RECOVER_AFTER == 4
    assert spans[:6] == [800, 400, 400, 400, 400, 800], spans


def test_a_sweep_that_read_some_chunks_returns_how_far_it_got_not_none() -> None:
    """**Review #11(iii).**  One more failure after the shrink budget used to
    discard every chunk already fetched, with no resume cursor at all.

    ``DepositSweep.to_block`` is already the field that tells the truth about
    coverage *and* is already the resume cursor, so a partial sweep is honest
    rather than a lie of omission.  This deliberately relaxes the documented
    "``None``, never a partial" contract — see
    ``docs/curator_sybil_review_fixes_plan.md`` §WP4.2(iii), ruled as
    recommended.
    """
    row = deposited_row(ALICE, hour=0, amount=10**17, block=7, log_index=1)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(2_000))
        flt = body["params"][0]
        if int(flt["fromBlock"], 16) == 0:
            return _rpc_result([row])
        raise httpx.ConnectError("the endpoint went away", request=request)

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None
    assert sweep.from_block == 0
    assert sweep.to_block == 799, "the sweep must state the extent it covered"
    assert [d.contributor for d in sweep.deposits] == [ALICE.lower()]


def test_a_sweep_that_read_nothing_is_still_none() -> None:
    """The other half of the contract, unchanged: zero chunks read is an
    outage, and an outage is ``None`` — never a sweep of zero deposits over a
    range we never covered."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(2_000))
        raise httpx.ConnectError("the endpoint went away", request=request)

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None


def test_a_total_outage_degrades_to_none_never_to_an_empty_sweep() -> None:
    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(_offline), config=FAST)
    )
    assert sweep is None


def test_every_log_request_carries_a_real_user_agent() -> None:
    rec = Recorder(lambda r: _rpc_result([] if b"getLogs" in r.content else hex(50)))
    asyncio.run(logs.fetch_deposits(CONTRACT, 0, client=_client(rec), config=FAST))
    assert rec.calls
    for _method, _url, _payload, headers in rec.calls:
        assert headers["user-agent"] == FAST.user_agent
        assert "python-httpx" not in headers["user-agent"]


def test_a_row_from_another_address_or_topic_never_reaches_the_dataset() -> None:
    """The filter is address-scoped, so anything else did not come from this
    contract however it got into the reply."""
    stranger = deposited_row(BOB, hour=0, amount=10**17, block=5, log_index=9)
    stranger["address"] = "0x" + "de" * 20
    other_event = deposited_row(BOB, hour=0, amount=10**17, block=6, log_index=9)
    other_event["topics"] = ["0x" + "cd" * 32, *other_event["topics"][1:]]
    rows = [
        deposited_row(ALICE, hour=0, amount=10**17, block=4, log_index=1),
        stranger,
        other_event,
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(10))
        return _rpc_result(rows)

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None
    assert [d.contributor for d in sweep.deposits] == [ALICE.lower()]


def test_duplicate_rows_are_deduped_on_tx_hash_and_log_index() -> None:
    row = deposited_row(ALICE, hour=0, amount=10**17, block=4, log_index=1)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(10))
        return _rpc_result([row, dict(row)])

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is not None and len(sweep.deposits) == 1


# ===========================================================================
# txs.fetch_tx_fingerprints — batching and the User-Agent
# ===========================================================================


def _tx_reply(tx_hash: str, *, nonce: int = 0, tx_type: int = 2) -> dict:
    body = {
        "hash": tx_hash,
        "nonce": hex(nonce),
        "gas": hex(91_600),
        "type": hex(tx_type),
    }
    if tx_type == 2:
        body["maxPriorityFeePerGas"] = hex(100_000_000)
        body["maxFeePerGas"] = hex(171_362_544)
    return body


def test_tx_fingerprints_are_batched_and_decoded() -> None:
    hashes = ["0x" + f"{i:064x}" for i in range(95)]

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        assert isinstance(batch, list), "fingerprints must be batched, not serial"
        return httpx.Response(
            200,
            json=[
                {"jsonrpc": "2.0", "id": call["id"],
                 "result": _tx_reply(call["params"][0], nonce=i)}
                for i, call in enumerate(batch)
            ],
        )

    rec = Recorder(handler)
    got = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(rec), config=FAST)
    )
    assert got is not None and len(got.fingerprints) == 95
    assert got.pending == ()
    sizes = [len(p) for p in rec.payloads]
    assert sizes == [40, 40, 15], sizes  # publicnode throttles ~40-call batches
    one = got.fingerprints[hashes[0]]
    assert isinstance(one, Tx)
    assert (one.gas_limit, one.tx_type, one.max_priority_fee_wei) == (
        91_600, 2, 100_000_000,
    )


def test_a_legacy_transaction_keeps_its_missing_fee_fields_as_none() -> None:
    """A type-0 transaction has no ``maxPriorityFeePerGas`` **at all**, so the
    field is ``None`` because it does not exist — never a shared zero, which a
    uniformity detector would read as a collapsed axis."""
    tx_hash = "0x" + "11" * 32

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        return httpx.Response(
            200,
            json=[{"jsonrpc": "2.0", "id": batch[0]["id"],
                   "result": _tx_reply(tx_hash, tx_type=0)}],
        )

    got = asyncio.run(
        txs.fetch_tx_fingerprints([tx_hash], client=_client(handler), config=FAST)
    )
    assert got is not None
    assert got.fingerprints[tx_hash].max_priority_fee_wei is None
    assert got.fingerprints[tx_hash].max_fee_wei is None
    assert got.fingerprints[tx_hash].gas_limit == 91_600


def test_publicnode_403s_a_library_default_user_agent_and_we_never_send_one() -> None:
    """Measured live (``captures/README.md``): publicnode answers ``403`` to
    python-urllib's default UA and answered the byte-identical batch from
    ``curl``.  The header goes on every **request**, not only on a client we
    happened to build — a caller may inject their own, and every test here
    does."""
    def handler(request: httpx.Request) -> httpx.Response:
        ua = request.headers.get("user-agent", "")
        if "python-httpx" in ua or "urllib" in ua or not ua:
            return httpx.Response(403, text="Forbidden")
        batch = json.loads(request.content)
        return httpx.Response(
            200,
            json=[{"jsonrpc": "2.0", "id": c["id"],
                   "result": _tx_reply(c["params"][0])} for c in batch],
        )

    tx_hash = "0x" + "22" * 32
    got = asyncio.run(
        txs.fetch_tx_fingerprints([tx_hash], client=_client(handler), config=FAST)
    )
    assert got is not None and tx_hash in got.fingerprints

    # The control: the same transport really does 403 a default UA, so the
    # assertion above is about our header and not about a lenient double.
    async def bare() -> int:
        async with _client(handler) as client:
            resp = await client.post("https://ethereum-rpc.publicnode.com", json=[])
            return resp.status_code

    assert asyncio.run(bare()) == 403


def test_a_batch_endpoint_error_rotates_on_message_text() -> None:
    """**Review I1, the reproduced case.**  drpc answers every entry of a batch
    with "Can't route your request" under ``-32602`` — a code other providers
    spend on genuinely malformed input.

    The batch path used to skip errored entries silently, so a live endpoint
    that had refused the *whole* call produced an empty result set and no
    rotation at all.  Classification is on the message, exactly as in
    ``rpc_call``, and the whole batch rotates to the next endpoint.
    """
    served: list[str] = []
    tx_hash = "0x" + "44" * 32

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        batch = json.loads(request.content)
        if request.url.host == "ethereum-rpc.publicnode.com":
            return httpx.Response(200, json=[
                {"jsonrpc": "2.0", "id": c["id"],
                 "error": {"code": -32602,
                           "message": "Can't route your request. Try again later."}}
                for c in batch
            ])
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": _tx_reply(c["params"][0])}
            for c in batch
        ])

    got = asyncio.run(
        txs.fetch_tx_fingerprints([tx_hash], client=_client(handler), config=FAST)
    )
    assert got is not None
    assert tx_hash in got.fingerprints, "the routing error was not classified"
    assert "ethereum-rpc.publicnode.com" in served
    assert "gateway.tenderly.co" in served, served


def test_a_malformed_batch_short_circuits_instead_of_rotating() -> None:
    """OUR bug fails identically everywhere, so rotating on it triples the
    request count and hides it.  The batch stops at the first endpoint and the
    fetcher degrades to ``None`` — the same answer ``fetch_deposits`` gives."""
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        batch = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"],
             "error": {"code": -32602,
                       "message": "invalid argument 0: hex string of odd length"}}
            for c in batch
        ])

    got = asyncio.run(
        txs.fetch_tx_fingerprints(["0x" + "55" * 32], client=_client(handler), config=FAST)
    )
    assert got is None
    assert served.count("gateway.tenderly.co") == 0, served


def _malformed_batch(request: httpx.Request) -> httpx.Response:
    batch = json.loads(request.content)
    return httpx.Response(200, json=[
        {"jsonrpc": "2.0", "id": c["id"],
         "error": {"code": -32602,
                   "message": "invalid argument 0: hex string of odd length"}}
        for c in batch
    ])


def _two_per_batch() -> SourceConfig:
    return SourceConfig(inter_call_delay=0.0, backoff_seconds=(0.0, 0.0),
                        blockscout_min_interval=0.0, tx_batch_size=2)


def test_a_malformed_hash_in_a_later_batch_keeps_the_fingerprints_already_read() -> None:
    """**Review #10, the reproduced case.**  ``None`` means *no batch was
    read*.

    One bad hash string — in a hand-edited cursor, say — arrives as a
    ``-32602`` on the batch that carries it, and the whole call returned
    ``None``: every fingerprint the earlier batches had already read was thrown
    away, and the caller was told the endpoint never answered at all.  The
    short circuit is right (our own bug fails identically everywhere) but it
    must keep what it read and name what it did not.
    """
    hashes = ["0x" + f"{i:064x}" for i in range(6)]
    bad = hashes[2]
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        batch = json.loads(request.content)
        if any(c["params"][0] == bad for c in batch):
            return _malformed_batch(request)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": _tx_reply(c["params"][0])}
            for c in batch
        ])

    got = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(handler), config=_two_per_batch())
    )
    assert got is not None, "a read batch was discarded by a later bad one"
    assert set(got.fingerprints) == set(hashes[:2])
    assert served.count("gateway.tenderly.co") == 0, served  # still no rotation


def test_a_malformed_hash_in_the_first_batch_is_still_none() -> None:
    """The other half, unchanged: nothing was read, so ``None`` keeps its
    exact documented meaning."""
    hashes = ["0x" + f"{i:064x}" for i in range(6)]
    got = asyncio.run(
        txs.fetch_tx_fingerprints(
            hashes, client=_client(_malformed_batch), config=_two_per_batch()
        )
    )
    assert got is None


def test_the_pending_cursor_after_a_malformed_batch_names_every_unread_hash() -> None:
    """And the cursor is usable: everything from the bad batch onward is
    pending, so feeding ``pending`` back finishes the sweep."""
    hashes = ["0x" + f"{i:064x}" for i in range(6)]
    bad = hashes[2]

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        if any(c["params"][0] == bad for c in batch):
            return _malformed_batch(request)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": _tx_reply(c["params"][0])}
            for c in batch
        ])

    first = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(handler), config=_two_per_batch())
    )
    assert first is not None
    assert first.pending == tuple(hashes[2:]), first.pending

    def healthy(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": _tx_reply(c["params"][0])}
            for c in batch
        ])

    second = asyncio.run(
        txs.fetch_tx_fingerprints(
            first.pending, client=_client(healthy), config=_two_per_batch()
        )
    )
    assert second is not None
    assert set(second.fingerprints) == set(hashes[2:])
    assert second.pending == ()


@pytest.mark.parametrize(
    "message",
    [
        "invalid params",
        "Invalid params: invalid length 63, expected a 0x-prefixed hex string",
        "parse error",
        "unknown block",
        "json: cannot unmarshal hex string of odd length into Go value",
    ],
)
def test_a_genuine_invalid_params_message_short_circuits_without_rotating(
    message: str,
) -> None:
    """The classification that makes the short circuit safe is the **message**.

    ``is_endpoint_limitation`` used to end on ``err["code"] not in
    MALFORMED_REQUEST_CODES`` — classification by code, which this repo forbids
    because providers reuse ``-32602`` and ``-32005`` for unrelated meanings.
    Short-circuiting now needs the message to agree, and these are the real
    spellings of a request that is genuinely ours to fix.
    """
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        body = json.loads(request.content)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(hex(100))
        return _rpc_error(-32602, message)

    sweep = asyncio.run(
        logs.fetch_deposits(CONTRACT, 0, client=_client(handler), config=FAST)
    )
    assert sweep is None
    assert served.count("eth.drpc.org") == 0, served


def test_an_error_object_with_no_message_falls_back_to_the_code_and_says_so() -> None:
    """The one documented use of a code in this module, and the reason it is
    documented: there is no text to classify.

    An unfamiliar *message* is an endpoint problem, not our bug — rotating on
    somebody's unrecognised wording costs a round trip, while short-circuiting
    the whole pool on it hides a working endpoint.
    """
    assert sources.is_endpoint_limitation({"code": -32602}) is False
    assert sources.is_endpoint_limitation({"code": -32000}) is True
    assert sources.is_endpoint_limitation({"code": -32602, "message": ""}) is False
    assert sources.is_endpoint_limitation(
        {"code": -32602, "message": "a wording nobody has vendored yet"}
    ) is True
    doc = " ".join((sources.is_endpoint_limitation.__doc__ or "").split()).lower()
    assert "no message" in doc, doc


def test_a_partial_batch_failure_names_the_hashes_it_could_not_read() -> None:
    """A partial read handed back as a bare dict is indistinguishable from a
    complete one, and a uniformity detector reading a half-covered component
    sees a collapsed axis that is really a coverage hole.  So the sweep says
    which hashes it is missing."""
    hashes = ["0x" + f"{i:064x}" for i in range(3)]
    dead = hashes[2]

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        if any(c["params"][0] == dead for c in batch):
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": _tx_reply(c["params"][0])}
            for c in batch
        ])

    cfg = SourceConfig(inter_call_delay=0.0, backoff_seconds=(0.0, 0.0),
                       blockscout_min_interval=0.0, tx_batch_size=2)
    got = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(handler), config=cfg)
    )
    assert got is not None
    assert set(got.fingerprints) == set(hashes[:2])
    assert got.pending == (dead,)

    # A hash the node answered for with no body is "ask again", never "this
    # transaction has no fingerprint".
    def empty(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": None} for c in batch
        ])

    none_body = asyncio.run(
        txs.fetch_tx_fingerprints(hashes[:1], client=_client(empty), config=FAST)
    )
    assert none_body is not None
    assert none_body.fingerprints == {}
    assert none_body.pending == (hashes[0],)


def test_a_batch_answered_out_of_order_is_realigned_by_id() -> None:
    """**Review I5.**  A provider is allowed to answer a batch in any order,
    and one that does hands every fingerprint to the wrong transaction — a
    defect that looks exactly like a detector calibration problem.

    The transport below answers **reversed** and gives each transaction a
    distinct nonce, so a positional decoder maps them backwards and this test
    is the only thing that would say so.
    """
    hashes = ["0x" + f"{i:064x}" for i in range(5)]
    nonce_of = {h: i * 7 for i, h in enumerate(hashes)}

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        replies = [
            {"jsonrpc": "2.0", "id": c["id"],
             "result": _tx_reply(c["params"][0], nonce=nonce_of[c["params"][0]])}
            for c in batch
        ]
        replies.reverse()
        return httpx.Response(200, json=replies)

    got = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(handler), config=FAST)
    )
    assert got is not None
    assert {h: got.fingerprints[h].nonce for h in hashes} == nonce_of


def test_a_dead_batch_falls_over_and_then_degrades_to_none() -> None:
    """drpc answers HTTP 500 to a batched ``getTransactionByHash``; the pool
    rotates on it, and when nothing answers the result is ``None`` — never an
    empty dict, which a caller would read as "these transactions have no
    fingerprints"."""
    served: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.host or "")
        return httpx.Response(500, text="internal error")

    got = asyncio.run(
        txs.fetch_tx_fingerprints(["0x" + "33" * 32], client=_client(handler), config=FAST)
    )
    assert got is None
    assert len(set(served)) > 1, served  # it really did rotate


def test_no_hashes_is_an_empty_answer_and_no_request_at_all() -> None:
    got = asyncio.run(txs.fetch_tx_fingerprints([], client=_client(_never), config=FAST))
    assert got is not None
    assert got.fingerprints == {} and got.pending == ()


# ===========================================================================
# blockscout.fetch_funding — keyset pagination, throttling, resumability
# ===========================================================================


def _page(items: list[dict], nxt: dict | None) -> httpx.Response:
    return httpx.Response(200, json={"items": items, "next_page_params": nxt})


def _incoming(from_addr: str, to_addr: str, block: int) -> dict:
    return {
        "from": {"hash": from_addr},
        "to": {"hash": to_addr},
        "block_number": block,
        "hash": "0x" + f"{block:064x}",
    }


FUNDER = "0x3333333333333333333333333333333333333333"


def test_funding_paginates_by_keyset_and_takes_the_oldest_incoming_transfer() -> None:
    """Blockscout serves newest-first with a keyset cursor, so the **first**
    funder is on the last page — the cursor is followed verbatim, as query
    params, exactly as the server handed it back."""
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("block_number") == "10":
            return _page([_incoming(FUNDER, ALICE, 10)], None)
        return _page(
            [_incoming(BOB, ALICE, 900)],
            {"block_number": "10", "index": "1"},
        )

    rec = Recorder(handler)
    sleep, waits = _sleeper()
    sweep = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(rec), config=FAST, sleep=sleep
        )
    )
    assert sweep is not None
    entry = sweep.funding[ALICE.lower()]
    assert isinstance(entry, Funding)
    assert entry.funder == FUNDER.lower()
    assert entry.hops == 1
    assert len(rec.calls) == 2
    assert "block_number=10" in rec.urls[1]


def test_funding_throttles_between_requests() -> None:
    """~3 req/s measured clean against Blockscout with zero 429s.  Asserted
    against an injected ``sleep`` so the suite proves the pacing without
    spending the seconds."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _page([_incoming(FUNDER, ALICE, 5)], None)

    sleep, waits = _sleeper()
    cfg = SourceConfig(blockscout_min_interval=1 / 3, backoff_seconds=(0.0, 0.0))
    asyncio.run(
        blockscout.fetch_funding(
            [ALICE, BOB], client=_client(handler), config=cfg, sleep=sleep
        )
    )
    assert waits, "no pacing at all"
    # Equality, not a ceiling: an upper bound is satisfied by a pacer that
    # sleeps zero, which is exactly the regression (a dropped `delay=`) the
    # test exists to catch.
    assert all(w == pytest.approx(cfg.blockscout_min_interval) for w in waits), waits
    assert len(waits) == 2  # one paced request per address


def test_funding_is_resumable_from_the_pending_cursor() -> None:
    """WP3 sweeps candidate-cluster members only — bounded hundreds, over many
    cycles.  So a call takes the subset it wants, reports what it could not
    reach in ``pending``, and a later call extends coverage without re-reading
    what is already ``known``."""
    def handler(request: httpx.Request) -> httpx.Response:
        who = str(request.url).rsplit("/addresses/", 1)[1].split("/")[0].lower()
        return _page([_incoming(FUNDER, who, 7)], None)

    rec = Recorder(handler)
    first = asyncio.run(
        blockscout.fetch_funding(
            [ALICE, BOB], client=_client(rec), config=FAST, budget=1
        )
    )
    assert first is not None
    assert set(first.funding) == {ALICE.lower()}
    assert first.pending == (BOB.lower(),)
    assert first.truncated is True

    calls_before = len(rec.calls)
    second = asyncio.run(
        blockscout.fetch_funding(
            first.pending, client=_client(rec), config=FAST, known=first.funding
        )
    )
    assert second is not None
    assert set(second.funding) == {ALICE.lower(), BOB.lower()}
    assert second.pending == ()
    assert second.truncated is False
    # exactly one new address was read: the known one was never re-fetched
    assert len(rec.calls) - calls_before == 1


def test_a_known_address_is_never_re_read() -> None:
    known = {ALICE.lower(): Funding(address=ALICE.lower(), funder=FUNDER.lower(), hops=1)}
    sweep = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(_never), config=FAST, known=known
        )
    )
    assert sweep is not None
    assert sweep.funding == known
    assert sweep.pending == ()


def test_an_address_whose_history_outran_the_page_budget_gets_no_row_at_all() -> None:
    """**Review C1.**  A bounded-out address is pending and is NOT resolved.

    The row it used to get — ``Funding(funder=None)`` — is the trap: the
    documented resume recipe passes ``funding`` back as ``known``, and ``known``
    is skipped, so the very address the cursor was supposed to return to would
    be skipped forever.  A pending address therefore has **no** row, and
    ``pending_reasons`` says why it is pending.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return _page([_incoming(BOB, ALICE, 900)], {"block_number": "800"})

    sweep = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(handler), config=FAST, max_pages=2
        )
    )
    assert sweep is not None
    assert ALICE.lower() not in sweep.funding
    assert sweep.pending == (ALICE.lower(),)
    assert sweep.pending_reasons == {ALICE.lower(): blockscout.PENDING_PAGES}
    assert sweep.page_bounded == (ALICE.lower(),)
    # `truncated` stays budget-only, so a page-bounded pass is visible through
    # its own vocabulary rather than by overloading somebody else's flag.
    assert sweep.truncated is False


def test_a_page_bounded_address_is_actually_re_read_on_the_next_pass() -> None:
    """**Review C1, the reproduced case.**  The documented resume recipe,
    driven end to end.

    Pass 1 runs with a page budget too small for this address's history and
    reports it pending.  Pass 2 feeds ``pending`` back as *addresses* with
    ``funding`` as ``known`` — exactly the recipe in the WP3 hand-off — and it
    must **issue a request**.  Before the fix it issued zero: pass 1 had written
    a ``funder=None`` row, ``known`` skipped it, ``pending`` came back empty and
    the address was silently dropped from the analysis forever.
    """
    state = {"patient": False}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("block_number") == "800":
            return _page([_incoming(FUNDER, ALICE, 7)], None)
        return _page([_incoming(BOB, ALICE, 900)], {"block_number": "800"})

    rec = Recorder(handler)
    first = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(rec), config=FAST, max_pages=1
        )
    )
    assert first is not None
    assert first.pending == (ALICE.lower(),)
    assert first.funding == {}

    before = len(rec.calls)
    second = asyncio.run(
        blockscout.fetch_funding(
            first.pending, client=_client(rec), config=FAST,
            known=first.funding, max_pages=5,
        )
    )
    assert len(rec.calls) - before > 0, "pass 2 issued no request — the cursor is dead"
    assert second is not None
    assert second.pending == ()
    assert second.funding[ALICE.lower()].funder == FUNDER.lower()


def test_a_transient_failure_is_never_frozen_into_a_resolved_row() -> None:
    """**Review C1, the second reproduced case.**  "The corruption outlives the
    outage" — the repo's own words, and the reason a sentinel is never written
    into a stored series.

    One 503 on pass 1 used to write ``Funding(funder=None)`` permanently: the
    next pass skipped it as ``known`` and the wallet was recorded as having no
    funder, forever, on the strength of one bad minute.  WP3 persists this dict
    into a cache slot, so "forever" would have outlived the process too.
    """
    state = {"down": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["down"]:
            return httpx.Response(503, text="Service Unavailable")
        return _page([_incoming(FUNDER, ALICE, 7)], None)

    first = asyncio.run(
        blockscout.fetch_funding([ALICE], client=_client(handler), config=FAST)
    )
    # Everything attempted failed, so this pass is an outage, not a result.
    assert first is None

    # …and a pass that *partly* answered must still not freeze the failure.
    state["down"] = True

    def mixed(request: httpx.Request) -> httpx.Response:
        who = str(request.url).rsplit("/addresses/", 1)[1].split("/")[0].lower()
        if who == ALICE.lower() and state["down"]:
            return httpx.Response(503, text="Service Unavailable")
        return _page([_incoming(FUNDER, who, 7)], None)

    partial = asyncio.run(
        blockscout.fetch_funding([ALICE, BOB], client=_client(mixed), config=FAST)
    )
    assert partial is not None
    assert ALICE.lower() not in partial.funding      # NOT frozen as funder=None
    assert partial.pending == (ALICE.lower(),)
    assert partial.pending_reasons[ALICE.lower()] == blockscout.PENDING_UNREADABLE
    assert partial.unreadable == (ALICE.lower(),)
    assert partial.funding[BOB.lower()].funder == FUNDER.lower()

    state["down"] = False
    healed = asyncio.run(
        blockscout.fetch_funding(
            partial.pending, client=_client(mixed), config=FAST,
            known=partial.funding,
        )
    )
    assert healed is not None
    assert healed.funding[ALICE.lower()].funder == FUNDER.lower()
    assert healed.pending == ()


def test_a_page_whose_items_are_null_is_unreadable_not_a_finished_walk() -> None:
    """**Review #5a, the reproduced case.**  ``{"items": null}`` from a 200.

    The guard was ``"items" not in body``, so a null items list passed it: the
    walk was treated as **complete**, and an address whose history we never
    actually read got a resolved ``Funding(funder=None)`` row.  A resolved row
    means "we walked the whole history and found no incoming transfer"; that is
    a measurement, and this was an outage wearing it.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        who = str(request.url).rsplit("/addresses/", 1)[1].split("/")[0].lower()
        if who == ALICE.lower():
            return httpx.Response(200, json={"items": None, "next_page_params": None})
        return _page([_incoming(FUNDER, who, 7)], None)

    sweep = asyncio.run(
        blockscout.fetch_funding([ALICE, BOB], client=_client(handler), config=FAST)
    )
    assert sweep is not None
    assert ALICE.lower() not in sweep.funding
    assert sweep.pending == (ALICE.lower(),)
    assert sweep.pending_reasons[ALICE.lower()] == blockscout.PENDING_UNREADABLE
    assert sweep.unreadable == (ALICE.lower(),)


def test_a_null_items_page_never_freezes_a_none_funder_into_a_resolved_row() -> None:
    """And the consequence the row would have had: the documented resume recipe
    passes ``funding`` back as ``known``, so a frozen ``funder=None`` is
    permanent — in maxpane's persisted slot, permanent past the process."""
    state = {"null": True}

    def handler(request: httpx.Request) -> httpx.Response:
        who = str(request.url).rsplit("/addresses/", 1)[1].split("/")[0].lower()
        if who == ALICE.lower() and state["null"]:
            return httpx.Response(200, json={"items": None, "next_page_params": None})
        return _page([_incoming(FUNDER, who, 7)], None)

    first = asyncio.run(
        blockscout.fetch_funding([ALICE, BOB], client=_client(handler), config=FAST)
    )
    assert first is not None
    assert ALICE.lower() not in first.funding

    state["null"] = False
    healed = asyncio.run(
        blockscout.fetch_funding(
            first.pending, client=_client(handler), config=FAST, known=first.funding
        )
    )
    assert healed is not None
    assert healed.funding[ALICE.lower()].funder == FUNDER.lower()
    assert healed.pending == ()


def test_the_funding_docstrings_agree_that_a_pending_address_gets_no_row() -> None:
    """**Review #5c.**  The *module* docstring still taught the behaviour the
    class docstring and the code had already reversed: "emitted with a ``None``
    funder **and** stays in ``pending``".  Both are true statements about two
    different designs, and only one of them is this one.

    Doc-agreement is a test here for the same reason it is on the segment key
    vocabulary: a docstring that teaches the old contract is how the old
    contract gets re-implemented.
    """
    module_doc = " ".join((blockscout.__doc__ or "").split()).lower()
    class_doc = " ".join((blockscout.FundingSweep.__doc__ or "").split()).lower()
    assert "a pending address has no row" in class_doc
    assert "no row at all" in module_doc
    assert "emitted with a ``none`` funder **and** stays in ``pending``" not in module_doc


def test_a_failure_mid_history_is_unreadable_not_page_bounded() -> None:
    """**Fix round 2, M1.**  Two different problems with opposite fixes.

    "Reached ``max_pages`` with a cursor still open" is solved by raising
    ``max_pages``.  "A request died on page 2" is not — doing that just spends
    more requests on an endpoint that is failing.  Round 1 classified both as
    ``"pages"`` because the loop only tracked whether *any* page had parsed, so
    the hand-off's own advice pointed at exactly the wrong action here.

    Page 1 answers with a cursor; page 2 503s; the budget is nine pages, so the
    bound was nowhere near reached.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("block_number") == "500":
            return httpx.Response(503, text="Service Unavailable")
        return _page([_incoming(BOB, ALICE, 900)], {"block_number": "500"})

    sweep = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(handler), config=FAST, max_pages=9
        )
    )
    assert sweep is not None
    assert sweep.pending == (ALICE.lower(),)
    assert sweep.pending_reasons[ALICE.lower()] == blockscout.PENDING_UNREADABLE
    assert sweep.page_bounded == ()          # NOT a bound problem
    assert sweep.unreadable == (ALICE.lower(),)
    assert ALICE.lower() not in sweep.funding


def test_a_clean_fall_through_the_page_bound_is_page_bounded() -> None:
    """The other half of the same distinction: every page we asked for
    answered, there are simply more of them than we were willing to walk."""
    def handler(request: httpx.Request) -> httpx.Response:
        # An endless history: always another cursor, never an error.
        return _page([_incoming(BOB, ALICE, 900)], {"block_number": "500"})

    sweep = asyncio.run(
        blockscout.fetch_funding(
            [ALICE], client=_client(handler), config=FAST, max_pages=3
        )
    )
    assert sweep is not None
    assert sweep.pending_reasons[ALICE.lower()] == blockscout.PENDING_PAGES
    assert sweep.page_bounded == (ALICE.lower(),)
    assert sweep.unreadable == ()


def test_a_tx_sweep_that_resolved_nothing_is_still_a_sweep() -> None:
    """**Fix round 2, the Important.**  ``TxSweep`` has no truthiness.

    It carried a ``__len__`` for one round, which made a successful pass that
    resolved nothing — the documented "node answered, no usable body, ask
    again" case — *falsy*.  Every ``if sweep:`` caller then read a healthy pass
    as an outage.  ``bool()`` on it must stay the plain object default.
    """
    hashes = ["0x" + f"{i:064x}" for i in range(2)]

    def null_bodies(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        return httpx.Response(200, json=[
            {"jsonrpc": "2.0", "id": c["id"], "result": None} for c in batch
        ])

    got = asyncio.run(
        txs.fetch_tx_fingerprints(hashes, client=_client(null_bodies), config=FAST)
    )
    assert got is not None
    assert got.fingerprints == {}
    assert set(got.pending) == set(hashes)
    assert bool(got) is True, "an empty-but-successful sweep must not be falsy"
    assert not hasattr(txs.TxSweep, "__len__")


def test_a_total_outage_is_none_even_when_the_budget_deferred_addresses() -> None:
    """**Review C2, the reproduced case.**  Deferral does not soften an outage.

    ``budget=2`` over five addresses with every request dying used to return a
    ``FundingSweep`` carrying two ``funder=None`` rows and ``truncated=True`` —
    a total outage wearing the costume of a budget cap.  Zero endpoints
    answered; that is ``None``, and the number of addresses we had not got to
    yet has nothing to do with it.
    """
    addresses = ["0x" + f"{i:040x}" for i in range(5)]
    sweep = asyncio.run(
        blockscout.fetch_funding(
            addresses, client=_client(_offline), config=FAST, budget=2
        )
    )
    assert sweep is None


def test_a_funding_outage_degrades_to_none_never_to_an_empty_map() -> None:
    sweep = asyncio.run(
        blockscout.fetch_funding([ALICE], client=_client(_offline), config=FAST)
    )
    assert sweep is None


def test_every_blockscout_request_carries_a_real_user_agent() -> None:
    """Blockscout stalls python-urllib and answers httpx/curl in under a
    second; a real UA is not a courtesy here, it is the difference between an
    answer and a hang."""
    rec = Recorder(lambda r: _page([_incoming(FUNDER, ALICE, 5)], None))
    asyncio.run(blockscout.fetch_funding([ALICE], client=_client(rec), config=FAST))
    assert rec.calls
    for _m, _u, _p, headers in rec.calls:
        assert headers["user-agent"] == FAST.user_agent


# ===========================================================================
# httpx is an EXTRA: lazily imported, clearly missing
# ===========================================================================


def test_a_missing_httpx_names_the_extra_rather_than_stack_tracing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)
    with pytest.raises(sources.MissingDependency) as excinfo:
        sources.require_httpx()
    assert "sybilkit[sources]" in str(excinfo.value)


def test_no_sources_module_imports_httpx_at_module_scope() -> None:
    """``import sybilkit.sources`` must work on the pure install; only a real
    fetch needs the transport.  Read off the AST, so an aliased import cannot
    slip past a spelling nobody thought of."""
    src = Path(sources.__file__).resolve().parent
    for path in sorted(src.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module scope only
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert "httpx" not in names, f"{path.name} imports httpx at module scope"


# ===========================================================================
# The structural no-network gate
# ===========================================================================


def test_no_test_in_this_file_builds_a_client_without_a_transport() -> None:
    """Structural, not incidental: a test added later that builds a bare
    ``httpx.AsyncClient()`` bypasses every mock in this file and would be
    caught only in CI — or not at all, because it would *pass* against a live
    endpoint."""
    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    built = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name not in ("AsyncClient", "Client"):
            continue
        built += 1
        assert any(kw.arg == "transport" for kw in node.keywords), ast.dump(node)
    assert built >= 1, "the scan found nothing to check"


def test_no_source_module_builds_a_client_of_its_own_by_default() -> None:
    """Every fetcher takes ``client=`` or ``transport=``; the one place a real
    ``AsyncClient`` is constructed is the shared opener, so injecting a
    transport in a test really does cover every request."""
    src = Path(sources.__file__).resolve().parent
    total = 0
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "MockTransport" not in text
        total += text.count("AsyncClient(")
    assert total == 1, "exactly one construction site, in sources/__init__.py"


def test_no_test_file_in_the_suite_builds_a_client_without_a_transport() -> None:
    """WP2.7's whole-suite gate, not just this file's.

    ``test_no_test_in_this_file_builds_a_client_without_a_transport`` covers
    the fetch tests; this one walks **every** module under ``tests/``, so a
    future test file that reaches for a transport-less client is caught the day
    it is written rather than the day CI runs offline.  It discovers the files
    by walking the directory, so a file nobody thought to add here is covered
    anyway.
    """
    root = THIS_FILE.parent
    scanned = 0
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scanned += 1
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name not in ("AsyncClient", "Client"):
                continue
            assert any(kw.arg == "transport" for kw in node.keywords), (
                f"{path.name}: {ast.dump(node)}"
            )
    assert scanned >= 12, "the walk found almost nothing — it proved nothing"
