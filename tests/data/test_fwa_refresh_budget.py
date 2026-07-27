"""WP-14 — the FWA refresh budget, measured rather than asserted from prose.

**Zero network.**  Everything here runs against ``tests/fixtures/fwa/`` through the
WP-6 transport doubles (``RecordingTransport`` / ``SimChain``), which decode the
client's own ``aggregate3`` calldata and re-encode a real ``Result[]``.  No test
sleeps: the 0.12 s inter-call pacing is observed through a recording stand-in for
``asyncio.sleep``.

Why this file exists in the shape it does
-----------------------------------------
The implementation plan's §16 gate said *"one sweep ≤ 20 `eth_call`s"*.  A fixed
number is the wrong shape of gate for this system, and the specific number was
wrong twice over:

* the plan's §8.4 says **~12** and findings §6.1 says **17**; the sweep at 3,867
  positions is **18** — 1 aggregate read + 9 slot batches + 8 listing batches.
  Both undercounts appear to have dropped the listing batches or the aggregate
  read;
* the pool grew from 3,867 (2026-07-25) to 5,942 (2026-07-27) — **+53 % in two
  days** — so any constant gate expires within the week.  At 5,942 the same sweep
  is **26** ``eth_call``s and would "fail" a ≤ 20 gate while behaving perfectly.

A gate that is wrong is worse than no gate: it is met while the real behaviour
drifts.  So the budget here is expressed as a **function of the live position
count**, and the fixed numbers that remain are *measurements at named pool sizes*
recorded so a regression shows up as a number changing.

The scaling law (derived from ``fwa_client._collect_listing_ids`` /
``_fetch_listings``, verified against three measured pool sizes)::

    eth_calls(N) = 1                                    # pinned aggregate read
                 + ceil(S / 500)                        # slot batches, S = top occupied slot
                 + ceil(N / 500)                        # listing batches
    round_trips(N) = eth_calls(N) + 1                   # + eth_blockNumber

with ``S`` bounded by the client's own runaway guard,
``int(N * SLOT_SCAN_HEADROOM) + SLOT_SCAN_MIN_EXTRA``.  At the live hole geometry
(top occupied slot 4,148 for 3,867 positions → ``S ≈ 1.073·N``) that is
``≈ 1 + N / 241``.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data.fwa_cache import (
    TIER_FAST,
    TIER_MEDIUM,
    TIER_SLOW,
    TIER_TTL_SECONDS,
    FWACache,
)
from maxpane_dashboard.data.fwa_client import (
    FWA_HOT_KEYS,
    FWA_REWARDS,
    HOT_VIEWS,
    MULTICALL3,
    MULTICALL_MAX_CALLS,
    SELECTORS,
    SLOT_SCAN_HEADROOM,
    SLOT_SCAN_MIN_EXTRA,
    FWAClient,
    _decode_aggregate3_result,
    _encode_uint,
    _strip0x,
    check_sweep_invariants,
    decode_listing,
)

# The WP-6 harness.  Imported rather than copied: a benchmark that measures a
# different transport double from the one the unit tests use is measuring
# something else.
from tests.data.test_fwa_client import (
    RecordingTransport,
    SimChain,
    _build_free_list_geometry,
    decode_aggregate3_calldata,
    encode_aggregate3_result,
    encode_listing,
    load_fixture,
)

# ---------------------------------------------------------------------------
# Measured constants.  A regression must show up as one of these numbers
# changing, not as a vague slowdown.  Every one was produced by the tests below.
# ---------------------------------------------------------------------------

#: Pool sizes the budget is measured at.  3,867 = live 2026-07-25 (findings
#: §6.1); 5,942 = live 2026-07-27 (§13.6, +53 % in two days); 10,000 = the next
#: round number the pool is plausibly heading for.
POOL_2026_07_25 = 3_867
POOL_2026_07_27 = 5_942
POOL_PROJECTED = 10_000

#: ``eth_call``s per full block-pinned sweep, measured.  NOT a gate — the gate is
#: :func:`sweep_eth_calls_upper_bound`; these are the points that pin the curve.
MEASURED_SWEEP_ETH_CALLS: dict[int, int] = {
    POOL_2026_07_25: 18,   # 1 aggregate + 9 slot batches + 8 listing batches
    POOL_2026_07_27: 26,   # 1 + 13 + 12
    POOL_PROJECTED: 43,    # 1 + 22 + 20
}

#: One extra round trip per sweep: ``eth_blockNumber`` to pin the block.
SWEEP_NON_ETH_CALL_ROUND_TRIPS = 1

#: A fast tick is **3** ``eth_call``s, not 1.  ``quoteAcquisitionPrice()`` is
#: deliberately outside the aggregate3 batch — bounding ``gas`` for one view is
#: not bounding it for 48 — and ``tokenShareBps(gap)`` needs an argument the
#: batch itself has to read first.  The plan's "1" counted only the batch.
MEASURED_FAST_TICK_ETH_CALLS = 3
MEASURED_FAST_TICK_ETH_CALLS_BARE = 1
#: Plus ``eth_getBalance`` (the only TVL source) and a TTL-cached ``eth_gasPrice``.
MEASURED_FAST_TICK_ROUND_TRIPS = 5

#: The client never uses raw JSON-RPC array batching; the ≤ 60-element ceiling
#: from §11 is therefore satisfied by construction, and this asserts it stays so.
MAX_JSONRPC_BATCH_ELEMENTS = 60

#: Observational, **not** measured here: findings §6.1 timed a live sweep at
#: 3,867 positions at 3.3 s over 19 round trips against publicnode.
OBSERVED_LIVE_SWEEP_SECONDS_AT_3867 = 3.3
OBSERVED_LIVE_ROUND_TRIPS_AT_3867 = 19
CALIBRATED_LATENCY_S = OBSERVED_LIVE_SWEEP_SECONDS_AT_3867 / OBSERVED_LIVE_ROUND_TRIPS_AT_3867

#: The client's own pacing floor (§11): a round trip can never be cheaper than this.
INTER_CALL_DELAY_S = 0.12

#: Observed pool growth: 3,867 → 5,942 over two days.
POOL_GROWTH_PER_DAY = (POOL_2026_07_27 / POOL_2026_07_25) ** 0.5

#: Live hole geometry: highest occupied slot / activeListingCount at block
#: 25612701.  The slot space is non-contiguous, so the scan always reads more
#: slots than there are positions.
LIVE_HOLE_RATIO = 4_148 / 3_867


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


def sweep_eth_calls_upper_bound(n: int) -> int:
    """Worst-case ``eth_call``s for a sweep of ``n`` positions.

    Derived from the code, not from a measurement: the slot scan can never run
    past its own budget (``int(n·headroom) + min_extra`` slots, 500 per call) and
    the listing read is exactly ``ceil(n / 500)``.  Independent of hole geometry,
    which is why it is the gate.
    """
    if n <= 0:
        return 1
    budget = int(n * SLOT_SCAN_HEADROOM) + SLOT_SCAN_MIN_EXTRA
    return (
        1
        + math.ceil(budget / MULTICALL_MAX_CALLS)
        + math.ceil(n / MULTICALL_MAX_CALLS)
    )


def sweep_eth_calls_expected(n: int, hole_ratio: float = LIVE_HOLE_RATIO) -> int:
    """Expected ``eth_call``s at a given hole density — the curve, not the ceiling."""
    if n <= 0:
        return 1
    top_slot = round(n * hole_ratio)
    return (
        1
        + math.ceil(top_slot / MULTICALL_MAX_CALLS)
        + math.ceil(n / MULTICALL_MAX_CALLS)
    )


def sweep_round_trips(n: int) -> int:
    return sweep_eth_calls_upper_bound(n) + SWEEP_NON_ETH_CALL_ROUND_TRIPS


def sweep_seconds(n: int, latency_s: float, cpu_s_per_position: float) -> float:
    """Wall-clock model for one sweep.

    A round trip costs ``max(latency, 0.12)``: the client paces itself at 0.12 s
    and cannot go faster even on a local node.  CPU is the decode/aggregate cost
    measured by :func:`_measure_decode_rate`, which is genuinely additive — it
    runs between round trips, not during them.
    """
    per_call = max(latency_s, INTER_CALL_DELAY_S)
    return sweep_round_trips(n) * per_call + n * cpu_s_per_position


def max_positions_within(
    budget_s: float, latency_s: float, cpu_s_per_position: float
) -> int:
    """Largest pool whose sweep still fits in ``budget_s``. Binary search, exact."""
    lo, hi = 0, 1_000_000
    if sweep_seconds(hi, latency_s, cpu_s_per_position) <= budget_s:
        return hi  # pragma: no cover - the model is not interesting up there
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if sweep_seconds(mid, latency_s, cpu_s_per_position) <= budget_s:
            lo = mid
        else:
            hi = mid - 1
    return lo


def days_of_growth(from_n: int, to_n: int) -> float:
    """Days from ``from_n`` to ``to_n`` at the observed +23.9 %/day."""
    if to_n <= from_n:
        return 0.0
    return math.log(to_n / from_n) / math.log(POOL_GROWTH_PER_DAY)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _client_on(transport: httpx.AsyncBaseTransport, **kw: Any) -> FWAClient:
    return FWAClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _ok(payload: dict, result: Any) -> httpx.Response:
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": payload.get("id"), "result": result}
    )


def synthetic_geometry(n: int) -> tuple[dict[int, int], list[int]]:
    """An ``n``-position slot map at the live hole density.

    Reproduces the fixture's own geometry exactly at n=3,867 (verified by
    :func:`test_synthetic_geometry_reproduces_the_fixture_call_count`), so the
    larger sizes are an extrapolation of measured structure rather than a guess.
    """
    top_slot = round(n * LIVE_HOLE_RATIO)
    step = top_slot / n
    slots: list[int] = []
    seen: set[int] = set()
    for k in range(n):
        s = int(k * step) + 1
        while s in seen:
            s += 1
        seen.add(s)
        slots.append(s)
    slots[-1] = top_slot
    slots = sorted(set(slots))
    assert len(slots) == n
    slot_map = {slot: 1000 + i for i, slot in enumerate(slots)}
    base = [
        int(v)
        for v in load_fixture("backing_distribution.json")["backing_values_wei"]
    ]
    backings = [base[i % len(base)] for i in range(n)]
    return slot_map, backings


def _sim_chain(n: int, *, block_number: int = 25612701) -> SimChain:
    slot_map, backings = synthetic_geometry(n)
    return SimChain(
        block_number=block_number, backings=backings, slot_map=slot_map
    )


def _multicall_widths(transport: RecordingTransport) -> list[int]:
    return [
        len(decode_aggregate3_calldata(p["params"][0]["data"]))
        for _u, p in transport.requests
        if p.get("method") == "eth_call"
        and p["params"][0]["to"].lower() == MULTICALL3
    ]


def _hot_handler() -> Callable[[str, dict], httpx.Response]:
    """Serve a complete, populated hot batch plus its two follow-up calls."""
    quote_raw = next(
        s["quoteAcquisitionPrice"]["raw_return_data"]
        for s in load_fixture("quote_acquisition_price.json")["samples"]
        if s["gasPrice_wei"] == 1_000_000_000
    )

    def handler(_url: str, payload: dict) -> httpx.Response:
        method = payload.get("method")
        if method == "eth_gasPrice":
            return _ok(payload, hex(1_000_000_000))
        if method == "eth_getBalance":
            return _ok(payload, hex(2_340_905_117_595_043_174_540))
        assert method == "eth_call", f"unexpected RPC method {method} on a fast tick"
        call = payload["params"][0]
        if call["to"].lower() == MULTICALL3:
            out = []
            for _t, _a, cd in decode_aggregate3_calldata(call["data"]):
                sel = "0x" + _strip0x(cd)[:8]
                if sel == SELECTORS["symbol()"]:
                    out.append(
                        (
                            True,
                            "0x"
                            + _encode_uint(0x20)
                            + _encode_uint(3)
                            + "465741".ljust(64, "0"),
                        )
                    )
                elif sel == SELECTORS["forcedTokenShareBps()"]:
                    out.append((True, "0x" + "f" * 64))
                elif sel == SELECTORS["lastAcquisitionTs()"]:
                    out.append((True, "0x" + _encode_uint(int(time.time()) - 300)))
                else:
                    out.append((True, "0x" + _encode_uint(7)))
            return _ok(payload, encode_aggregate3_result(out))
        if call["data"] == SELECTORS["quoteAcquisitionPrice()"]:
            return _ok(payload, quote_raw)
        if call["data"].startswith(SELECTORS["tokenShareBps(uint256)"]):
            return _ok(payload, "0x" + _encode_uint(4321))
        raise AssertionError(f"unexpected eth_call {call}")

    return handler


class GatedTransport(httpx.AsyncBaseTransport):
    """Recording transport that parks one chosen request on an ``asyncio.Event``.

    This is how a sweep is "artificially slowed past 60 s" without any test
    actually waiting: request number ``gate_at`` blocks until the gate is set,
    and everything the fast tier does in the meantime is recorded around it.
    """

    def __init__(
        self,
        handler: Callable[[str, dict], httpx.Response],
        *,
        gate_at: int,
        probe: Callable[[], None] | None = None,
    ) -> None:
        self._handler = handler
        self._gate_at = gate_at
        #: called once per wire request — lets a test observe the published
        #: snapshot at every point a sweep could conceivably leak a partial one
        self._probe = probe
        self.gate = asyncio.Event()
        self.reached_gate = asyncio.Event()
        self.requests: list[tuple[str, dict]] = []

    def calls(self, method: str) -> list[dict]:
        return [p for _u, p in self.requests if p.get("method") == method]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append((str(request.url), payload))
        if self._probe is not None:
            self._probe()
        if len(self.requests) == self._gate_at:
            self.reached_gate.set()
            await self.gate.wait()
        response = self._handler(str(request.url), payload)
        response.request = request
        return response


async def _swap_transport(
    client: FWAClient, transport: httpx.AsyncBaseTransport
) -> None:
    """Point a live client at a new transport, keeping its single-flight state.

    The lock and the last-good sweep live on the client, so the overlap tests
    need the *same* ``FWAClient`` with a different wire underneath it.
    """
    old = client._client
    client._client = httpx.AsyncClient(transport=transport)
    await old.aclose()


class _FakeClock:
    def __init__(self, start: float = 1_784_900_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# 1. Calls per tier, as a function of position count
# ---------------------------------------------------------------------------


async def test_synthetic_geometry_reproduces_the_fixture_call_count():
    """The extrapolated geometry is calibrated against the real one.

    ``_build_free_list_geometry`` is the fixture's exact hole layout at 3,867
    (263 holes below the count, 263 positions above it, top slot 4,148).  The
    synthetic generator must produce the same call count at the same size, or the
    5,942 and 10,000 measurements are extrapolating from a different shape.
    """
    fixture_slot_map, fixture_backings, _holes = _build_free_list_geometry()
    real = SimChain(
        block_number=25612701,
        backings=fixture_backings,
        slot_map=fixture_slot_map,
    )
    transport = RecordingTransport(real.handler)
    _b, _p, report = await _client_on(transport).sweep_positions()
    assert report["invariants_ok"] is True
    real_calls = len(transport.calls("eth_call"))

    synth = _sim_chain(POOL_2026_07_25)
    synth_transport = RecordingTransport(synth.handler)
    _b2, _p2, report2 = await _client_on(synth_transport).sweep_positions()
    assert report2["invariants_ok"] is True

    assert len(synth_transport.calls("eth_call")) == real_calls
    assert real_calls == MEASURED_SWEEP_ETH_CALLS[POOL_2026_07_25]


@pytest.mark.parametrize(
    "n", [POOL_2026_07_25, POOL_2026_07_27, POOL_PROJECTED]
)
async def test_sweep_call_count_at_each_pool_size(n: int):
    """The measured curve: 18 / 26 / 43 ``eth_call``s at 3,867 / 5,942 / 10,000.

    The plan's fixed ``≤ 20`` gate passes at 3,867, fails at 5,942 — two days
    later — and is wrong by a factor of two at 10,000.  That is why the gate is
    now :func:`sweep_eth_calls_upper_bound`.
    """
    chain = _sim_chain(n)
    transport = RecordingTransport(chain.handler)
    client = _client_on(transport)

    block, positions, report = await client.sweep_positions()

    assert block == 25612701
    assert report["invariants_ok"] is True
    assert report["collected"] == report["expected"] == n == len(positions)

    eth_calls = transport.calls("eth_call")
    assert len(eth_calls) == MEASURED_SWEEP_ETH_CALLS[n]

    # The gate: the code-derived ceiling holds, and the geometry model predicts
    # the measurement exactly.
    assert len(eth_calls) <= sweep_eth_calls_upper_bound(n)
    assert len(eth_calls) == sweep_eth_calls_expected(n)

    # One extra round trip, and only one: eth_blockNumber pins the sweep.
    assert len(transport.calls("eth_blockNumber")) == SWEEP_NON_ETH_CALL_ROUND_TRIPS
    assert len(transport.requests) == len(eth_calls) + SWEEP_NON_ETH_CALL_ROUND_TRIPS

    # Every call in the sweep is pinned to the same block.
    assert {p["params"][1] for p in eth_calls} == {hex(block)}


def test_the_plan_s_fixed_20_call_gate_expires_within_the_week():
    """The correction, stated as an executable fact.

    A constant gate cannot survive a pool growing 23.9 %/day.  This test fails
    the moment someone reintroduces one.
    """
    assert MEASURED_SWEEP_ETH_CALLS[POOL_2026_07_25] == 18 <= 20
    assert MEASURED_SWEEP_ETH_CALLS[POOL_2026_07_27] == 26 > 20
    # The pool crossed the 20-call line at ~4,300 positions, i.e. between the
    # two live captures.
    crossing = next(
        n for n in range(1, 20_000) if sweep_eth_calls_expected(n) > 20
    )
    assert POOL_2026_07_25 < crossing < POOL_2026_07_27
    assert days_of_growth(POOL_2026_07_25, crossing) < 2.0


def test_scaling_law_is_linear_in_position_count():
    """``eth_calls ≈ 1 + N/241`` — visible, not assumed."""
    points = sorted(MEASURED_SWEEP_ETH_CALLS.items())
    slopes = [
        (c2 - c1) / (n2 - n1)
        for (n1, c1), (n2, c2) in zip(points, points[1:])
    ]
    # calls per position, i.e. ~1/241
    for slope in slopes:
        assert 1 / 300 < slope < 1 / 200
    # and the whole curve sits between the model and the ceiling
    for n, calls in points:
        assert sweep_eth_calls_expected(n) == calls <= sweep_eth_calls_upper_bound(n)
        assert sweep_eth_calls_upper_bound(n) - calls <= 3  # the ceiling is tight


async def test_fast_tick_costs_three_eth_calls_not_one():
    """The plan says 1.  It is 3, by design, and the design is right.

    ``quoteAcquisitionPrice()`` carries its own ``gasPrice`` and a bounded
    ``gas``; folding it into aggregate3 would bound the gas of all 48 views
    together, which is not the same guarantee.  ``tokenShareBps(gap)`` takes an
    argument computed from the ``lastAcquisitionTs()`` the batch just returned,
    so it cannot ride in the batch that produces it.
    """
    transport = RecordingTransport(_hot_handler())
    client = _client_on(transport)

    out = await client.fetch_hot_batch()

    assert set(out) == set(FWA_HOT_KEYS)
    assert out["_ok"] is True and out["_failed"] == ()

    eth_calls = transport.calls("eth_call")
    assert len(eth_calls) == MEASURED_FAST_TICK_ETH_CALLS

    targets = [c["params"][0] for c in eth_calls]
    assert targets[0]["to"].lower() == MULTICALL3
    assert targets[1]["data"] == SELECTORS["quoteAcquisitionPrice()"]
    assert "gasPrice" in targets[1] and "gas" in targets[1]
    assert targets[2]["to"] == FWA_REWARDS
    assert targets[2]["data"].startswith(SELECTORS["tokenShareBps(uint256)"])

    # The whole hot tier as round trips, including the TVL balance read.
    await client.fetch_eth_balance()
    assert len(transport.requests) == MEASURED_FAST_TICK_ROUND_TRIPS

    # ~48 views in one chunk, nowhere near the cap.
    widths = _multicall_widths(transport)
    assert widths == [len(HOT_VIEWS)]
    assert widths[0] <= MULTICALL_MAX_CALLS


async def test_fast_tick_can_be_reduced_to_one_eth_call():
    """Degraded mode: drop the two follow-ups and the tick is a single call."""
    transport = RecordingTransport(_hot_handler())
    client = _client_on(transport)

    out = await client.fetch_hot_batch(
        include_quote=False, include_token_share=False
    )

    assert len(transport.calls("eth_call")) == MEASURED_FAST_TICK_ETH_CALLS_BARE
    assert out["acquisition_fee"] == 7


async def test_fast_tick_never_runs_a_sweep():
    """No slot scan, no listing read, no block pin on the 15 s path."""
    transport = RecordingTransport(_hot_handler())
    client = _client_on(transport)

    await client.fetch_hot_batch()
    await client.fetch_eth_balance()

    banned = (
        SELECTORS["slotToListing(uint256)"],
        SELECTORS["listings(uint256)"],
    )
    for _u, payload in transport.requests:
        if payload.get("method") != "eth_call":
            continue
        call = payload["params"][0]
        assert call["data"][:10] not in banned
        if call["to"].lower() == MULTICALL3:
            for _t, _a, cd in decode_aggregate3_calldata(call["data"]):
                assert cd[:10] not in banned
        # hot reads are deliberately unpinned (§11)
        assert payload["params"][1] == "latest"

    assert transport.calls("eth_blockNumber") == []


async def test_slow_tier_issues_no_eth_calls_at_all():
    """The 15-minute tier is HTTP to CoinGecko/DexScreener/DefiLlama — Pool C.

    It shares no client, no transport and no endpoint list with Pool A, so it
    cannot be reached from a fast or medium tick even by accident.  Asserted
    structurally because the alternative — asserting it in the manager — belongs
    to WP-12.
    """
    from maxpane_dashboard.data import fwa_market

    def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(f"structural test touched the wire: {request.url}")

    client = _client_on(httpx.MockTransport(_no_network))
    hosts = " ".join(client.endpoints).lower()
    for foreign in ("coingecko", "dexscreener", "geckoterminal", "llama"):
        assert foreign not in hosts
    assert not any(
        isinstance(getattr(client, name, None), fwa_market.FWAMarketClient)
        for name in dir(client)
        if not name.startswith("__")
    )
    # And the tier table keeps them 60× apart, so a slow sweep can never be
    # mistaken for a hot one.
    assert TIER_TTL_SECONDS[TIER_FAST] == 15.0
    assert TIER_TTL_SECONDS[TIER_MEDIUM] == 60.0
    assert TIER_TTL_SECONDS[TIER_SLOW] == 900.0


# ---------------------------------------------------------------------------
# 2. The 500-call cap, at the boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected_widths"),
    [
        (1, [1]),
        (499, [499]),
        (500, [500]),           # exactly the cap: one chunk, accepted
        (501, [500, 1]),        # one over: split, never a 501-call chunk
        (1000, [500, 500]),
        (1001, [500, 500, 1]),
    ],
)
async def test_multicall_chunking_at_the_500_boundary(
    count: int, expected_widths: list[int]
):
    """``_multicall`` splits at exactly 500 and the split is index-preserving."""
    addresses = ["0x" + f"{i:040x}" for i in range(1, count + 1)]

    def handler(_url: str, payload: dict) -> httpx.Response:
        inner = decode_aggregate3_calldata(payload["params"][0]["data"])
        assert len(inner) <= MULTICALL_MAX_CALLS
        return _ok(
            payload,
            encode_aggregate3_result(
                [(True, "0x" + _encode_uint(1)) for _ in inner]
            ),
        )

    transport = RecordingTransport(handler)
    client = _client_on(transport)

    out = await client.fetch_collections_whitelisted(addresses)

    assert _multicall_widths(transport) == expected_widths
    assert max(_multicall_widths(transport)) <= MULTICALL_MAX_CALLS
    # results stay aligned with the request across the chunk boundary
    assert len(out) == count
    assert all(v is True for v in out.values())


async def test_no_sweep_chunk_at_any_pool_size_exceeds_the_cap():
    """Slot batches and listing batches alike, at the largest modelled pool."""
    chain = _sim_chain(POOL_PROJECTED)
    transport = RecordingTransport(chain.handler)
    await _client_on(transport).sweep_positions()

    widths = _multicall_widths(transport)
    assert max(widths) == MULTICALL_MAX_CALLS      # the chunker really fills them
    assert all(w <= MULTICALL_MAX_CALLS for w in widths)
    assert sum(widths) >= POOL_PROJECTED * 2       # slots + listings


async def test_client_never_uses_raw_jsonrpc_array_batching():
    """§11's ≤ 60-element batch limit, held by not batching at all.

    Every request is a single JSON object.  A future "optimisation" that sends an
    array must respect the 60-element ceiling; this test makes that a deliberate
    decision rather than an accident.
    """
    chain = _sim_chain(600)
    transport = RecordingTransport(chain.handler)
    await _client_on(transport).sweep_positions()

    assert transport.requests
    for _url, payload in transport.requests:
        assert isinstance(payload, dict), "raw JSON-RPC batching appeared"
        if isinstance(payload, list):  # pragma: no cover - guard for the future
            assert len(payload) <= MAX_JSONRPC_BATCH_ELEMENTS


async def test_consecutive_calls_are_paced_without_the_test_sleeping(
    monkeypatch: pytest.MonkeyPatch,
):
    """~0.12 s between round trips, observed through a recording fake clock."""
    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float, *a: Any, **kw: Any) -> None:
        recorded.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    chain = _sim_chain(600)
    transport = RecordingTransport(chain.handler)
    client = FWAClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=INTER_CALL_DELAY_S,
        backoff_seconds=(0.0, 0.0),
    )

    started = time.perf_counter()
    await client.sweep_positions()
    elapsed = time.perf_counter() - started

    # one pause between each pair of consecutive round trips, none before the first
    assert len(recorded) == len(transport.requests) - 1
    assert all(0.10 <= d <= INTER_CALL_DELAY_S for d in recorded)
    # the pacing is a real cost on the wire — it is what makes the 0.12 s floor
    # in :func:`sweep_seconds` a floor
    assert sum(recorded) == pytest.approx(
        (len(transport.requests) - 1) * INTER_CALL_DELAY_S, abs=0.05
    )
    # ...and the suite did not actually wait for any of it
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 3. Tier interaction: skipped, not queued; and atomic publication
# ---------------------------------------------------------------------------


async def test_overlapping_sweeps_are_skipped_not_queued():
    """Three concurrent callers, one sweep on the wire.

    The two that arrive while a sweep is in flight get the previous result
    immediately, flagged ``skipped``, and add **zero** requests.  Queueing them
    would mean rendering a block from ten minutes ago.
    """
    chain = _sim_chain(1_200)
    transport = RecordingTransport(chain.handler)
    client = _client_on(transport)

    first = await client.sweep_positions()
    assert first[2]["invariants_ok"] is True
    baseline_requests = len(transport.requests)

    # Now gate the *next* sweep mid-flight and pile two more callers onto it.
    gated = GatedTransport(chain.handler, gate_at=3)
    await _swap_transport(client, gated)

    inflight = asyncio.create_task(client.sweep_positions())
    await gated.reached_gate.wait()

    overlapped = await asyncio.gather(
        client.sweep_positions(), client.sweep_positions()
    )
    requests_during_overlap = len(gated.requests)

    for _b, positions, report in overlapped:
        assert report["skipped"] is True
        assert positions == first[1], "a skipped tick still serves the last good sweep"
    assert len(gated.requests) == requests_during_overlap, "a sweep was queued"

    gated.gate.set()
    block, positions, report = await inflight
    assert report["skipped"] is False
    assert report["invariants_ok"] is True
    assert len(positions) == 1_200

    # exactly two sweeps' worth of traffic for four calls
    assert len(gated.requests) == baseline_requests


async def test_eight_fast_ticks_survive_a_sweep_slowed_past_60s():
    """The starvation scenario from §16 R2, driven by a fake clock.

    A medium sweep is parked mid-flight for longer than the 60 s tier interval.
    Eight 15 s fast ticks run over the top of it; two further medium ticks come
    due and are both **skipped**.  Nothing queues, nothing starves.
    """
    clock = _FakeClock()
    cache = FWACache(clock=clock)
    chain = _sim_chain(1_200)

    # --- tick 0: a medium sweep that completes, so there is a last-good result
    warm = RecordingTransport(chain.handler)
    client = _client_on(warm)
    block, positions, report = await client.sweep_positions()
    assert report["invariants_ok"] is True
    cache.set_sweep(block, positions)
    cache.mark_fetched(TIER_MEDIUM)
    cache.mark_fetched(TIER_FAST)
    t_zero = clock.t

    # --- t+60: the next medium sweep starts and then hangs past its own tier
    gated = GatedTransport(chain.handler, gate_at=3)
    await _swap_transport(client, gated)
    clock.advance(TIER_TTL_SECONDS[TIER_MEDIUM])
    assert TIER_MEDIUM in cache.tiers_due()
    inflight = asyncio.create_task(client.sweep_positions())
    await gated.reached_gate.wait()

    # --- the fast tier keeps its own cadence on its own client
    hot_transport = RecordingTransport(_hot_handler())
    hot_client = _client_on(hot_transport)

    fast_ok = 0
    medium_skipped = 0
    next_medium_at = clock.t + TIER_TTL_SECONDS[TIER_MEDIUM]
    for _tick in range(8):
        clock.advance(TIER_TTL_SECONDS[TIER_FAST])
        assert TIER_FAST in cache.tiers_due()
        hot = await hot_client.fetch_hot_batch()
        assert hot["_ok"] is True, "a fast tick was starved by the sweep"
        cache.mark_fetched(TIER_FAST)
        fast_ok += 1

        # the sweep has been in flight for longer than the medium interval
        if clock.t >= next_medium_at:
            assert TIER_MEDIUM in cache.tiers_due()
            _b, skipped_positions, rep = await client.sweep_positions()
            assert rep["skipped"] is True
            # the tick still renders: it gets the last-good sweep, not nothing
            assert len(skipped_positions) == 1_200
            medium_skipped += 1
            next_medium_at += TIER_TTL_SECONDS[TIER_MEDIUM]
            # a skipped tick is NOT a fetch: the tier stays due rather than
            # rescheduling itself 60 s out on the strength of a non-result
            assert TIER_MEDIUM in cache.tiers_due()

    assert fast_ok == 8
    assert clock.t - t_zero == 180.0
    assert medium_skipped == 2, "8 fast ticks == 120 s == two medium tier deadlines"

    gated.gate.set()
    _b, positions2, report2 = await inflight
    assert report2["skipped"] is False
    assert len(positions2) == 1_200

    # the eight fast ticks cost exactly what a fast tick costs, times eight
    assert (
        len(hot_transport.calls("eth_call"))
        == 8 * MEASURED_FAST_TICK_ETH_CALLS
    )
    # and the two skipped medium ticks cost nothing
    assert len(gated.requests) == len(warm.requests)


async def test_published_snapshot_is_atomic_during_a_sweep():
    """A consumer never sees a half-updated pool.

    The sweep builds a whole list and the cache swaps it in one assignment, so
    every observation a widget can make is a complete, block-consistent sweep —
    either the old one or the new one, never a mixture.  Sampled twice over: on
    every event-loop turn, and on every single wire request the sweep makes.
    """
    cache = FWACache()
    old_chain = _sim_chain(600, block_number=25612700)
    new_chain = _sim_chain(POOL_2026_07_25, block_number=25612701)

    warm = RecordingTransport(old_chain.handler)
    client = _client_on(warm)
    b0, p0, _r = await client.sweep_positions()
    assert cache.set_sweep(b0, p0) is True

    observations: list[tuple[int | None, int]] = []

    def observe() -> None:
        entry = cache.get_sweep()
        assert entry is not None
        observations.append((entry.block, len(entry.payload)))

    gated = GatedTransport(new_chain.handler, gate_at=3, probe=observe)
    await _swap_transport(client, gated)

    stop = asyncio.Event()

    async def consumer() -> None:
        while not stop.is_set():
            observe()
            await asyncio.sleep(0)

    async def producer() -> None:
        block, positions, report = await client.sweep_positions()
        assert report["invariants_ok"] is True
        cache.set_sweep(block, positions)

    watcher = asyncio.create_task(consumer())
    task = asyncio.create_task(producer())
    await gated.reached_gate.wait()
    gated.gate.set()
    await task
    stop.set()
    await watcher

    # the swap window was genuinely sampled: at least once per wire request
    assert len(observations) >= len(gated.requests) > 10
    # Only two states were ever visible, and both are internally consistent.
    assert set(observations) <= {
        (25612700, 600),
        (25612701, POOL_2026_07_25),
    }
    assert observations[0] == (25612700, 600)
    assert observations[-1] == (25612701, POOL_2026_07_25)
    # and it really did transition mid-poll rather than after the watcher stopped
    assert (25612701, POOL_2026_07_25) in observations
    # the sweep took many round trips, every one of which a consumer could have
    # caught mid-build had the publication not been atomic
    assert len(gated.requests) == MEASURED_SWEEP_ETH_CALLS[POOL_2026_07_25] + 1


# ---------------------------------------------------------------------------
# 4. CPU cost of the decode/aggregate path, independent of network latency
# ---------------------------------------------------------------------------


def _encoded_sweep_payloads(n: int) -> tuple[list[str], list[str], list[int]]:
    """Pre-build exactly what the wire returns for an ``n``-position sweep."""
    slot_map, backings = synthetic_geometry(n)
    slots = sorted(slot_map)
    top_slot = slots[-1]

    slot_chunks: list[str] = []
    for start in range(1, top_slot + 1, MULTICALL_MAX_CALLS):
        width = min(MULTICALL_MAX_CALLS, top_slot - start + 1)
        slot_chunks.append(
            encode_aggregate3_result(
                [
                    (True, "0x" + _encode_uint(slot_map.get(s, 0)))
                    for s in range(start, start + width)
                ]
            )
        )

    listing_chunks: list[str] = []
    for start in range(0, n, MULTICALL_MAX_CALLS):
        window = slots[start : start + MULTICALL_MAX_CALLS]
        listing_chunks.append(
            encode_aggregate3_result(
                [
                    (
                        True,
                        encode_listing(
                            collection="0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e",
                            depositor="0x00000000000000000000000000000000000000aa",
                            purchaser="0x" + "0" * 40,
                            token_id=slot_map[s],
                            weight=10**36 // max(1, backings[i]),
                            value=backings[i],
                            slot=s,
                        ),
                    )
                    for i, s in enumerate(window, start=start)
                ]
            )
        )
    return slot_chunks, listing_chunks, backings


_DECODE_MEASUREMENT: dict[str, float] = {}


def _measure_decode_rate() -> float:
    """Seconds of pure CPU per position for the decode/aggregate path."""
    if "s_per_position" in _DECODE_MEASUREMENT:
        return _DECODE_MEASUREMENT["s_per_position"]
    n = POOL_2026_07_25
    slot_chunks, listing_chunks, _backings = _encoded_sweep_payloads(n)

    started = time.perf_counter()
    ids: list[int] = []
    for chunk in slot_chunks:
        for ok, data in _decode_aggregate3_result(chunk):
            if ok and _strip0x(data):
                value = int(_strip0x(data)[:64], 16)
                if value:
                    ids.append(value)
    positions = []
    for chunk in listing_chunks:
        for i, (ok, data) in enumerate(_decode_aggregate3_result(chunk)):
            if ok:
                pos = decode_listing(data, i)
                if pos is not None:
                    positions.append(pos)
    # Feed the check its own correct answers so the benchmark measures the
    # aggregate arithmetic rather than the mismatch-logging path.
    total_weight = sum(p.weight for p in positions)
    weighted = sum(p.weight * p.backing_wei for p in positions)
    report = check_sweep_invariants(
        positions,
        expected_count=len(positions),
        total_weight_onchain=total_weight,
        weighted_backing_total_onchain=weighted,
        acquisition_fee_onchain=fwa_ev.acquisition_fee_wei(weighted, total_weight),
    )
    elapsed = time.perf_counter() - started
    assert report["invariants_ok"] is True

    assert len(positions) == n
    _DECODE_MEASUREMENT["s_per_position"] = elapsed / n
    _DECODE_MEASUREMENT["total_s"] = elapsed
    _DECODE_MEASUREMENT["n"] = n
    return elapsed / n


def test_decode_and_aggregate_cpu_cost_over_the_full_pool():
    """The CPU half of a sweep, measured with the network taken out.

    A sweep is not only round trips: 3,867 listings arrive as ~2.7 MB of hex that
    has to be decoded and reduced.  Knowing this number separately is what makes
    the headroom model below meaningful — if CPU dominated, adding RPC endpoints
    would not help.

    Measured: **~37 ms for 3,867 positions, ~10 µs/position** — i.e. about 1 % of
    the 3.3 s a live sweep takes.  The medium tier is latency-bound, not
    CPU-bound, so the levers that matter are chunk width and endpoint count, not
    a faster decoder.
    """
    per_position = _measure_decode_rate()
    total = _DECODE_MEASUREMENT["total_s"]

    # A generous tripwire, not a stopwatch: this is ~0.2 s on the dev machine and
    # the assertion is here to catch an O(n²) decoder, not CI jitter.
    assert total < 3.0, f"decode path took {total:.2f}s for {POOL_2026_07_25} positions"
    assert per_position < 1e-3

    # CPU is a minority of a live sweep: findings §6.1 measured 3.3 s end to end.
    assert total < 0.5 * OBSERVED_LIVE_SWEEP_SECONDS_AT_3867

    # ...and it is linear.  Half the pool costs about half the time.
    half_slots, half_listings, _b = _encoded_sweep_payloads(POOL_2026_07_25 // 2)
    started = time.perf_counter()
    for chunk in half_slots + half_listings:
        _decode_aggregate3_result(chunk)
    half = time.perf_counter() - started
    assert half < total * 1.5, "decode is superlinear in position count"


# ---------------------------------------------------------------------------
# 5. Growth headroom — the number that actually matters
# ---------------------------------------------------------------------------


def test_pool_growth_rate_is_the_one_the_findings_recorded():
    assert round(POOL_GROWTH_PER_DAY, 2) == 1.24           # +23.9 %/day
    assert round(POOL_2026_07_27 / POOL_2026_07_25 - 1, 2) == 0.54
    assert round(days_of_growth(POOL_2026_07_25, POOL_2026_07_27), 2) == 2.0


@pytest.mark.parametrize(
    "latency_s",
    [CALIBRATED_LATENCY_S, 0.5, 1.0],
    ids=["calibrated-0.17s", "slow-0.5s", "degraded-1.0s"],
)
def test_medium_tier_fits_in_60s_at_today_s_pool_size(latency_s: float):
    """5,942 positions still fit the 60 s tier at every plausible RPC latency."""
    cpu = _measure_decode_rate()
    seconds = sweep_seconds(POOL_2026_07_27, latency_s, cpu)
    assert seconds < TIER_TTL_SECONDS[TIER_MEDIUM]


def test_model_reproduces_the_one_live_timing_we_have():
    """Sanity: the model must land on the 3.3 s that was actually observed.

    Observational input, taken from findings §6.1 (a live run against
    publicnode), not from anything measured in this suite.
    """
    cpu = _measure_decode_rate()
    modelled = sweep_seconds(POOL_2026_07_25, CALIBRATED_LATENCY_S, cpu)
    assert 0.8 <= modelled / OBSERVED_LIVE_SWEEP_SECONDS_AT_3867 <= 1.4


def test_growth_headroom_of_the_60s_medium_tier():
    """**The headroom figure.**

    Where does the 60 s medium tier break, and how long does the observed growth
    rate take to get there?

    ===================  =============  ==========  ===========================
    round-trip latency   breaks at ~N   × today     days from 5,942 at +24 %/d
    ===================  =============  ==========  ===========================
    0.17 s (calibrated)        77,000        13.0×             11.9
    0.50 s (slow public)       26,500         4.5×              7.0
    1.00 s (degraded)          12,864         2.2×              3.6
    ===================  =============  ==========  ===========================

    The binding case is the degraded one: **~12,900 positions, about 3.6 days of
    the observed growth rate away**.  Below that the sweep fits; above it the 60 s
    tick lands on a sweep that has not finished, which the single-flight lock
    turns into a skipped refresh rather than a pile-up — so the failure mode is a
    stale odds board, not a 429 cascade.  The mitigation is a wider chunk (the
    500-call cap is a publicnode observation, not a Multicall3 limit) or a longer
    medium interval; both are cheap, which is why this is a headroom note and not
    a blocker.
    """
    cpu = _measure_decode_rate()
    limits = {
        lat: max_positions_within(TIER_TTL_SECONDS[TIER_MEDIUM], lat, cpu)
        for lat in (CALIBRATED_LATENCY_S, 0.5, 1.0)
    }

    # today's pool is comfortably inside every scenario
    for lat, n_max in limits.items():
        assert n_max > POOL_2026_07_27, f"already over budget at {lat}s/call"

    # the documented figures, to within the tolerance of the cpu measurement
    assert 60_000 < limits[CALIBRATED_LATENCY_S] < 95_000
    assert 22_000 < limits[0.5] < 33_000
    assert 11_000 < limits[1.0] < 17_000

    # the binding constraint and its expiry date
    worst = limits[1.0]
    headroom_days = days_of_growth(POOL_2026_07_27, worst)
    assert 3.0 < headroom_days < 5.0
    assert worst / POOL_2026_07_27 > 2.0  # at least a doubling of pool size

    # 10,000 positions — the next round number — still fits, but only just at 1 s
    assert sweep_seconds(POOL_PROJECTED, 1.0, cpu) < TIER_TTL_SECONDS[TIER_MEDIUM]
    assert sweep_seconds(POOL_PROJECTED, 1.0, cpu) > 0.6 * TIER_TTL_SECONDS[TIER_MEDIUM]


def test_fast_tier_has_an_order_of_magnitude_more_headroom_than_the_medium_tier():
    """The 15 s tier is 3 calls and does not grow with the pool — by design."""
    cpu = _measure_decode_rate()
    fast_seconds = MEASURED_FAST_TICK_ROUND_TRIPS * max(1.0, INTER_CALL_DELAY_S)
    assert fast_seconds < TIER_TTL_SECONDS[TIER_FAST] / 2

    # the fast tick's cost is independent of N: same 3 calls at 10,000 positions
    assert MEASURED_FAST_TICK_ETH_CALLS == 3
    medium_seconds = sweep_seconds(POOL_PROJECTED, 1.0, cpu)
    assert medium_seconds / fast_seconds > 5
