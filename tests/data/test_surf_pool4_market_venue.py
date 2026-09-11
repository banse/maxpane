"""WP2 — the cross-venue price gap, and the read that feeds it.

**Zero network.** The two client tests drive :class:`Pool4Client` through an
``httpx.MockTransport`` seeded from committed captures; the fold tests touch no
I/O at all because the fold is pure.

The fold tests come from the plan verbatim. The two additions are the ones the
plan's own reasoning demands but does not spell out as tests: that both ticks
ride **one** batch (a gap derived from two blocks is the +1.5%/+0.2%
disagreement PRD 8.3 exists to end), and WP8's cross-check that the pinned
reference pool is the one an independent reader calls deepest.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data import surf_pool4_market as mk
from maxpane_dashboard.data.surf_models import POOL4_NETWORKS, POOL4_VENUE_WORDS
from maxpane_dashboard.data.surf_pool4_client import (
    POOL4_REFERENCE_POOL_ID,
    Pool4Client,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "pool4"

SEPOLIA, MAINNET = POOL4_NETWORKS


def load(name: str):
    with open(FIXTURES / f"{name}.json") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The fold — the plan's five tests
# ---------------------------------------------------------------------------


def test_the_gap_is_derived_from_both_ticks_and_is_signed():
    """Hook at 68196, reference at 68341: the reference tick is HIGHER, so IMD
    is cheaper there, so a buyer pays more here -> positive gap."""
    gap = mk.venue_gap_pct(hook_tick=68196, reference_tick=68341)
    assert gap == pytest.approx(1.46, abs=0.02)
    assert mk.venue_gap_pct(hook_tick=68341, reference_tick=68196) == pytest.approx(
        -1.44, abs=0.02
    )


def test_the_gap_is_none_when_either_tick_is_missing():
    assert mk.venue_gap_pct(hook_tick=None, reference_tick=68341) is None
    assert mk.venue_gap_pct(hook_tick=68196, reference_tick=None) is None


def test_no_venue_is_named_when_the_gap_is_below_the_combined_fees():
    """PRD 8.3. Both pools charge 1%, so a gap under 2% is not arbitrageable
    and switching venues over it loses the spread. Silence is the answer."""
    assert mk.cheaper_venue(
        gap_pct=1.46, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None
    assert mk.cheaper_venue(
        gap_pct=0.2, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None


def test_the_reference_is_named_only_once_the_gap_clears_the_fees():
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=10000, reference_fee_bps=10000
    ) == "reference"
    assert mk.cheaper_venue(
        gap_pct=-3.0, hook_fee_bps=10000, reference_fee_bps=10000
    ) == "here"


def test_an_unreadable_fee_is_not_a_free_pass():
    """A missing fee must not be treated as zero -- that would let every gap
    clear a threshold of nothing and name a venue on noise."""
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=None, reference_fee_bps=10000
    ) is None
    assert mk.cheaper_venue(
        gap_pct=3.0, hook_fee_bps=10000, reference_fee_bps=None
    ) is None
    assert mk.cheaper_venue(
        gap_pct=None, hook_fee_bps=10000, reference_fee_bps=10000
    ) is None


def test_the_two_venue_words_are_the_frozen_ones():
    """WP0 froze the vocabulary; a third spelling would reach a widget that
    only knows two and fall through to whichever branch is last."""
    named = {
        mk.cheaper_venue(gap_pct=g, hook_fee_bps=10000, reference_fee_bps=10000)
        for g in (3.0, -3.0)
    }
    assert named == set(POOL4_VENUE_WORDS)


# ---------------------------------------------------------------------------
# The oracle — WP8's reference-pool cross-check (the ladder test is WP8's own)
# ---------------------------------------------------------------------------


def test_our_pinned_reference_pool_is_the_one_the_oracle_calls_deepest():
    """If IMD's deepest pool ever moves, POOL4_REFERENCE_POOL_ID is wrong and
    the venue gap silently compares against a shallow pool. This is the test
    that notices."""
    assert load("oracle_25955365")["reference_pool_id"] == POOL4_REFERENCE_POOL_ID


def test_the_oracle_block_reproduces_a_gap_no_venue_can_be_named_from():
    """The independent reader's own two ticks, one block, both fees 1%.

    PRD 8.3 left three disagreeing figures on the record (+1.5%, +0.2%, ~1.45%).
    Derived one way from one block the gap is a fraction of a percent, an order
    of magnitude under the 2% the two fees cost -- so ``cheaper_venue`` is
    silent, which is the designed answer and not a missing implementation.
    """
    oracle = load("oracle_25955365")
    gap = mk.venue_gap_pct(
        hook_tick=oracle["tick"], reference_tick=oracle["reference_tick"]
    )
    assert abs(gap) < 0.05, gap
    assert mk.cheaper_venue(
        gap_pct=gap,
        hook_fee_bps=oracle["hook_lp_fee_bps"],
        reference_fee_bps=oracle["reference_lp_fee_bps"],
    ) is None


# ---------------------------------------------------------------------------
# The read — one batch, one block
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


class _Recorder(httpx.MockTransport):
    """MockTransport keeping every request payload, to count round trips."""

    def __init__(self, handler) -> None:
        self.payloads: list = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.payloads.append(json.loads(request.content))
            return handler(request)

        super().__init__(_wrapped)


def _extsload_table(pool_id: str, word: str) -> dict[str, str]:
    """``{extsload calldata: storage word}`` for one pool, keyed by calldata.

    Keyed by what the client actually sends, never by position, so the test
    passes only if the client independently derives the same storage slots.
    """
    slot0_call, liquidity_call = P.pool_state_calls(pool_id)
    return {slot0_call.lower(): word, liquidity_call.lower(): _LIQ_WORD}


_LIQ_WORD = "0x" + f"{10**21:064x}"


def _slot0_word(tick: int) -> str:
    """A slot0 storage word carrying *tick*, encoded the way v4 packs it."""
    sqrt_price = 1 << 96
    packed = (sqrt_price & ((1 << 160) - 1)) | ((tick & 0xFFFFFF) << 160)
    packed |= 10000 << 208  # lpFee, the top field
    return "0x" + f"{packed:064x}"


def _pair_handler(*, hook_tick: int, reference_tick: int, block: int, pool_id: str):
    table: dict[str, str] = {}
    table.update(_extsload_table(pool_id, _slot0_word(hook_tick)))
    table.update(
        _extsload_table(POOL4_REFERENCE_POOL_ID, _slot0_word(reference_tick))
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        entries = payload if isinstance(payload, list) else [payload]
        out = []
        for entry in entries:
            rid = entry.get("id")
            if entry.get("method") == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": rid, "result": hex(block)})
                continue
            data = str(entry["params"][0]["data"]).lower()
            out.append({"jsonrpc": "2.0", "id": rid,
                        "result": table.get(data, "0x")})
        body = out if isinstance(payload, list) else out[0]
        return httpx.Response(200, json=body)

    return handler


def _client_on(transport: httpx.BaseTransport) -> Pool4Client:
    return Pool4Client(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
    )


POOL_MANAGER = load("mainnet_pool_slot0")["pool_manager"]
HOOK_POOL_ID = load("mainnet_pool_slot0")["pool_id"]


async def test_both_ticks_come_back_from_one_round_trip():
    """PRD 8.3's whole point. Two ticks read a block apart is how a 1.3%
    disagreement appears out of nothing in a thin pool, so the reference read
    rides the hook's own batch rather than opening a second round."""
    transport = _Recorder(_pair_handler(
        hook_tick=68181, reference_tick=68180, block=25955365,
        pool_id=HOOK_POOL_ID,
    ))
    client = _client_on(transport)
    got = await client.fetch_reference_slot0(
        HOOK_POOL_ID, network=MAINNET, pool_manager=POOL_MANAGER)

    assert len(transport.payloads) == 1, transport.payloads
    assert got["hook"].tick == 68181
    assert got["reference"].tick == 68180
    assert got["block_number"] == 25955365
    assert got["reference"].pool_id == POOL4_REFERENCE_POOL_ID


async def test_the_gap_the_pair_implies_is_the_folds_gap():
    """The read and the fold agree end to end, so neither can drift alone."""
    transport = _Recorder(_pair_handler(
        hook_tick=68196, reference_tick=68341, block=25955365,
        pool_id=HOOK_POOL_ID,
    ))
    got = await _client_on(transport).fetch_reference_slot0(
        HOOK_POOL_ID, network=MAINNET, pool_manager=POOL_MANAGER)
    gap = mk.venue_gap_pct(
        hook_tick=got["hook"].tick, reference_tick=got["reference"].tick)
    assert gap == pytest.approx(1.46, abs=0.02)


async def test_an_unreadable_reference_is_none_and_never_a_zero_tick():
    """Tick 0 is a real price (1 IMD per ETH). A dead read that rendered as 0
    would put the gap at hundreds of percent and name a venue on nothing."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        entries = payload if isinstance(payload, list) else [payload]
        out = []
        hook_table = _extsload_table(HOOK_POOL_ID, _slot0_word(68181))
        for entry in entries:
            rid = entry.get("id")
            if entry.get("method") == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": rid, "result": hex(1)})
                continue
            data = str(entry["params"][0]["data"]).lower()
            out.append({"jsonrpc": "2.0", "id": rid,
                        "result": hook_table.get(data, "0x")})
        return httpx.Response(200, json=out if isinstance(payload, list) else out[0])

    got = await _client_on(httpx.MockTransport(handler)).fetch_reference_slot0(
        HOOK_POOL_ID, network=MAINNET, pool_manager=POOL_MANAGER)
    assert got["hook"].tick == 68181
    assert got["reference"].tick is None
    assert mk.venue_gap_pct(
        hook_tick=got["hook"].tick, reference_tick=got["reference"].tick) is None


async def test_a_malformed_hook_pool_id_never_reaches_the_network():
    client = _client_on(httpx.MockTransport(_no_network))
    assert await client.fetch_reference_slot0(
        "0xdeadbeef", network=MAINNET, pool_manager=POOL_MANAGER) is None


async def test_a_malformed_reference_id_does_not_take_the_hook_read_with_it():
    """A wrong constant must degrade one half, not blind the whole view."""
    transport = _Recorder(_pair_handler(
        hook_tick=68181, reference_tick=68180, block=25955365,
        pool_id=HOOK_POOL_ID,
    ))
    got = await _client_on(transport).fetch_reference_slot0(
        HOOK_POOL_ID, "0xnothex", network=MAINNET, pool_manager=POOL_MANAGER)
    assert got["hook"].tick == 68181
    assert got["reference"] is None
