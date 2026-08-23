"""Keyless multi-source client for the surf dashboard (surfsurf.eth tracker).

Four source groups, all keyless (PRD docs/surf_PRD.md §5):

=================  =========================================================
state RPC          eth_call getters + the three nonces. publicnode primary —
                   the strongest keyless batcher, but it REFUSES archive
                   ``eth_getLogs``, which is why the pools are separate.
logs RPC           recent-window ``eth_getLogs`` only (bridge mints,
                   IdentityHashUpdated, v4 Initialize, Seaport OrderFulfilled).
Blockscout REST    v2 GETs only: channel bodies, dev tx pages, token counters.
                   v1 ``eth_call`` is broken (HTTP 400) — never used.
market REST        GeckoTerminal + DexScreener, cross-checked. GeckoTerminal
                   serves a STALE token name ("Vibe Coins") — display names
                   come from DexScreener/onchain, never from GeckoTerminal.
=================  =========================================================

Failure semantics (CLAUDE.md, non-negotiable): a failed read is ``None``,
never ``0``. Every public ``fetch_*`` returns its model with per-field
``None`` for individually failed reads, and ``None`` overall only when every
source for that method failed. No public method ever raises into the refresh
loop.

RPC errors are classified on MESSAGE TEXT, not code: providers reuse -32602
and -32005 for unrelated meanings, and one provider's "suggested retry range"
decrements one block per round trip and livelocks anything that follows it
verbatim. This client never follows a suggested range; it halves its own
window (bounded).
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Callable, NamedTuple
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.analytics import surf_launchpad
from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data import surf_v4
from maxpane_dashboard.data.evm_abi import (
    decode_address,
    decode_aggregate3_result,
    decode_string,
    decode_uint,
    encode_aggregate3,
    encode_uint,
    pad_left,
    strip0x,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)
from maxpane_dashboard.data.surf_models import (
    ChainState,
    ChannelTx,
    DevTx,
    LaunchpadCoin,
    LaunchpadState,
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
    PoolV4State,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoints — two pools, structurally separate (CLAUDE.md hazard table)
# ---------------------------------------------------------------------------

STATE_RPC_PRIMARY = "https://ethereum-rpc.publicnode.com"
STATE_RPC_FALLBACKS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://rpc.mevblocker.io",
]
#: Logs pool. publicnode is deliberately absent: it 403s archive eth_getLogs.
LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",  # hard 10k-block page cap; fine at our window
]

_BANNED_RPC_HOSTS = frozenset(
    {
        "eth.llamarpc.com",       # HTTP 521, origin down
        "rpc.ankr.com",           # now requires an API key
        "eth-mainnet.g.alchemy.com",
        "mainnet.infura.io",
        "api.opensea.io",
        "api.reservoir.tools",    # sunset, DNS gone
        "cloudflare-eth.com",     # -32603 / -32046 on every call
    }
)

BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"
DEXSCREENER_TOKENS_API = "https://api.dexscreener.com/latest/dex/tokens"
GECKO_TOKEN_API = (
    "https://api.geckoterminal.com/api/v2/networks/eth/tokens/{address}"
)
#: ETH/USD, keyless. The URL is copied verbatim from
#: ``maxpane_dashboard/data/price.py::_COINGECKO_URL``, which is module-private
#: there — this is a copied *string*, not a copied client. WP1.7 explains why
#: ``PriceClient`` itself must not be instantiated here (it builds its own
#: ``httpx.AsyncClient`` and would bypass the injected transport) and why its
#: ``0.0``-on-failure sentinel must not be copied with it.
COINGECKO_ETH_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=ethereum&vs_currencies=usd"
)

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
_INTER_CALL_DELAY = 0.12  # publicnode 429s under bursts; measured in fwa_client

#: Recent-window size for eth_getLogs (~8 h at 12 s blocks). Constructor-
#: injectable; halved (never "suggested-range"-followed) on range errors.
LOG_WINDOW_BLOCKS = 2400
_LOG_MIN_WINDOW = 300
_LOG_MAX_SHRINKS = 3

#: There is deliberately no ``LAUNCHPAD_LOG_WINDOW_BLOCKS`` here any more, and
#: no ``LAUNCHPAD_HOUR_BLOCKS`` either. The first was a 33,000-block window
#: measured back from the *chain head*; the launch history it was trying to
#: read is fixed at its *start*, so the window walked off the far end of that
#: history one block per block. Measured 2026-08-23: 146 launches existed, the
#: earliest 33,702 blocks back, and the window saw 66 of them -- including
#: neither of the two busiest pools on the launchpad, which therefore had no
#: ticker, no name and no creator and could not reach the table at any sort
#: order. A history that only grows is swept from its first block through a
#: cursor (``A.LAUNCHPAD_FIRST_BLOCK`` + ``LaunchpadState.cursor``), never
#: through a rolling window. The hour constant went with it: see
#: ``LAUNCHPAD_DAY_BLOCKS`` below for the window that replaced it.
#: Curve state (spot price) is read only for the rows actually rendered --
#: never per the full coin population (WP5 design idea 1). This bounds the
#: follow-up multicall's size regardless of ``coinCount``.
LAUNCHPAD_RENDER_LIMIT = 20
#: Real-chain seconds per block, used only to turn a raw log row's
#: ``blockNumber`` into an approximate epoch timestamp for ``age_s`` --
#: ``eth_getLogs`` rows carry no timestamp of their own on every endpoint.
#: Matches the ~12 s/block assumption ``LOG_WINDOW_BLOCKS`` already documents.
_LAUNCHPAD_BLOCK_SECONDS = 12.0
#: 24 hours at ``_LAUNCHPAD_BLOCK_SECONDS``/block -- the window ``rank_coins``
#: now treats as "the day" for ``swaps_24h`` and HOT COIN, replacing the
#: single hour that had 1 CurveSwap across 146 coins on a live measurement
#: (2026-08-23) and left every coin tied at 0. Derived, not the literal
#: ``7_200``, so a block-time change moves this and
#: ``surf_launchpad.HOT_MAX_AGE_S`` together --
#: ``test_the_hot_coin_staleness_bound_is_the_window_it_measures`` pins the
#: two against each other for exactly that reason.
LAUNCHPAD_DAY_BLOCKS = int(86_400 / _LAUNCHPAD_BLOCK_SECONDS)   # 7_200
#: Search floor for the decoy-pool sweep: ``Initialize`` logs on the v4
#: PoolManager filtered to ``currency1 == IMD`` exist from this block on
#: (2026-08-23 research sweep).
V4_INITIALIZE_SEARCH_FROM_BLOCK = 25_000_000

MAX_CHANNEL_PAGES = 3   # 21 txs fit one page today; growth must not break us
MAX_ACTIVITY_PAGES = 2  # per wallet
#: ~38 IDMD transfers/day at 50 rows/page: four pages is ~5x headroom, and
#: hitting the bound means "unknown", never a partial count (WP1.8).
MAX_NFT_TRANSFER_PAGES = 4
#: Identity writes are 1 of 2000 today; the same bound-means-unknown rule.
MAX_REGISTRY_LOG_PAGES = 4

_DAY_SECONDS = 86400.0

PRICE_AGREE_TOLERANCE_PCT = 5.0

#: Canonical Multicall3 deployment — identical address on every EVM chain.
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

#: ``getBlockNumber()`` on Multicall3 itself — recomputed during planning with
#: this repo's keccak, not remembered.  Module-private and defined HERE because
#: WP0's frozen selector surface has no entry for it and WP1 may not edit
#: ``surf_addresses`` (open issue 14 offers WP0 the one-line promotion).
_SEL_GET_BLOCK_NUMBER = "0x42cbb15c"

#: ERC-721 ``balanceOf(address)`` — client-local, like the selector above:
#: WP0's frozen surface has no entry for it (open issue 7), so it is defined
#: HERE rather than added to ``surf_addresses``.
_SEL_BALANCE_OF = "0x70a08231"

#: Seaport 1.6 — lowercase because every log-filter address this module
#: builds is compared/stored lowercase (module docstring / CLAUDE.md rule).
#: ``surf_addresses.SEAPORT`` is the checksummed, display-facing twin; this
#: is the client-local one actually used to build ``eth_getLogs`` filters.
_SEAPORT = "0x0000000000000068f116a894984e2db1123eb395"
#: A ``bytes32`` topic of all zeros — matches ``Transfer``'s ``from`` when the
#: sender is the mint address, i.e. this IS the mint filter's "from == 0x0".
_ZERO_TOPIC = "0x" + "0" * 64

_POSITIONS_RETURN_WORDS = 12
_SLOT0_RETURN_WORDS = 7


def _decode_int24(word: int) -> int:
    """Two's-complement for the int24 tick returned as a full word."""
    return word - (1 << 256) if word >= 1 << 255 else word


def _decode_positions(raw_hex: str) -> dict | None:
    """positions(uint256) flat 12-word tuple; short return = revert = None."""
    raw = strip0x(raw_hex or "")
    if len(raw) < _POSITIONS_RETURN_WORDS * 64:
        return None
    return {
        "token0": decode_address(raw, 2),
        "token1": decode_address(raw, 3),
        "fee": decode_uint(raw, 4),
        "tick_lower": _decode_int24(decode_uint(raw, 5)),
        "tick_upper": _decode_int24(decode_uint(raw, 6)),
        "liquidity": decode_uint(raw, 7),
        "tokens_owed0": decode_uint(raw, 10),
        "tokens_owed1": decode_uint(raw, 11),
    }


def _lp_state(
    positions_result: tuple[bool, str] | None,
    owner_result: tuple[bool, str] | None,
) -> str | None:
    """Classify the v3 LP position from its raw ``aggregate3`` sub-calls.

    Three outcomes, and the middle one is the point. ``aggregate3`` with
    ``allowFailure=True`` returns ``success=False`` for a revert — which is an
    *answer*: the position does not exist. That is not a failed read, so it
    must not collapse into the same ``None`` a transport outage produces
    (CLAUDE.md: "a row whose real negative has no representable value ...
    renders None identically for 'we looked and there was nothing' and 'we
    could not look'"). Verified live 2026-08-17: ``positions(1167726)`` now
    reverts ``Invalid token ID`` and ``ownerOf(1167726)`` reverts
    ``ERC721: owner query for nonexistent token`` — the ops wallet withdrew
    and burned the position.

    ``positions_result``/``owner_result`` are the raw ``(success, returnData)``
    tuples ``decode_aggregate3_result`` hands back, or ``None`` when no
    sub-call answered at all (there is no such entry to read). Only that
    double-``None`` case is unknown; a revert with either leg present is
    evidence.
    """
    if positions_result is None and owner_result is None:
        return None
    reverted = positions_result is not None and not positions_result[0]
    if reverted:
        return "gone"
    if positions_result is not None and positions_result[0]:
        return "live"
    return None


def _decode_slot0(raw_hex: str) -> dict | None:
    raw = strip0x(raw_hex or "")
    if len(raw) < _SLOT0_RETURN_WORDS * 64:
        return None
    return {
        "sqrt_price_x96": decode_uint(raw, 0),
        "tick": _decode_int24(decode_uint(raw, 1)),
    }


_Q96 = 1 << 96
_MAX_TICK = 887272


def _sqrt_ratio_at_tick(tick: int) -> int:
    """``sqrt(1.0001**tick) * 2**96`` — the range edge in Q64.96.

    Deliberately NOT Uniswap's 256-bit bit-shift ladder: that exists so a
    *contract* can be exact in integer arithmetic, and porting it is a
    well-known source of transcription bugs. A float pow is accurate to about
    1e-12 relative, which is roughly a millionth of the last digit this
    dashboard ever prints (four decimals of a 388,421-token side). Read-only,
    display-only, and the exactness that matters — ``liquidity`` and
    ``sqrtPriceX96`` — comes off the chain untouched.
    """
    tick = max(-_MAX_TICK, min(_MAX_TICK, int(tick)))
    return int(math.exp(tick * math.log(1.0001) / 2) * _Q96)


def _position_amounts_wei(
    liquidity: int | None,
    sqrt_price_x96: int | None,
    tick_lower: int | None,
    tick_upper: int | None,
) -> tuple[int | None, int | None]:
    """``(amount0_wei, amount1_wei)`` currently held by an v3 position.

    Any missing input yields ``(None, None)``: an amount derived from a failed
    price read is indistinguishable from a real one on screen, and this pair
    feeds the LP MIGRATION hero row.

    The general formula — the full-range shortcut ``L/√P`` / ``L·√P`` is only
    its limit case, and the LP is expected to be re-added concentrated:

        √P clamped into [√a, √b]
        amount0 = L · 2**96 · (√b − √P) / (√P · √b)
        amount1 = L · (√P − √a) / 2**96

    An in-range side that genuinely holds nothing is ``0``; that is a value,
    not a failure (a position parked entirely below spot is 100 % token1).
    """
    if None in (liquidity, sqrt_price_x96, tick_lower, tick_upper):
        return None, None
    if sqrt_price_x96 <= 0 or tick_lower >= tick_upper:
        return None, None
    sa = _sqrt_ratio_at_tick(tick_lower)
    sb = _sqrt_ratio_at_tick(tick_upper)
    sp = max(sa, min(sb, sqrt_price_x96))
    amount0 = (liquidity * _Q96 * (sb - sp)) // (sp * sb) if sp * sb else 0
    amount1 = (liquidity * (sp - sa)) // _Q96
    return amount0, amount1


# ---------------------------------------------------------------------------
# Launchpad log decoding.  ``ticker`` and ``name`` are carried through
# RAW here -- ``launch(string,string)`` is permissionless, so both are
# attacker-chosen strings, and escaping happens at render (Task 11), never
# here. Every helper returns ``None`` on a short/malformed row rather than
# guessing; a dropped row is simply absent from the ranked list, never a
# zero-filled placeholder in it.
# ---------------------------------------------------------------------------


def _decode_launched_data(data_hex: str) -> tuple[str, str, int, int] | None:
    """``(string name, string ticker, uint256 coinSupply, uint256
    initialPriceWad)`` -- the non-indexed tail of ``Launched``.

    Hand-rolled rather than a shared multi-field ABI decoder (there is no
    second caller in this codebase that needs one -- see ``evm_abi``'s own
    docstring on what does and does not belong there). Each dynamic field is
    re-wrapped with a synthetic leading offset word so ``evm_abi.decode_string``
    -- built for a single top-level dynamic value -- can decode it in place.
    """
    raw = strip0x(data_hex or "")
    if len(raw) < 4 * 64:
        return None
    try:
        name_off = decode_uint(raw, 0) * 2   # bytes -> hex chars
        ticker_off = decode_uint(raw, 1) * 2
        coin_supply = decode_uint(raw, 2)
        initial_price_wad = decode_uint(raw, 3)
    except ValueError:
        return None
    name = decode_string("0x" + pad_left("20", 64) + raw[name_off:])
    ticker = decode_string("0x" + pad_left("20", 64) + raw[ticker_off:])
    if name is None or ticker is None:
        return None
    return name, ticker, coin_supply, initial_price_wad


def _decode_launched_log(row: dict) -> dict | None:
    """One raw ``Launched`` row -> its fields, or ``None`` if malformed.

    Topic layout: ``[topic0, poolId, coin, creator]`` -- three indexed
    fields, matching the vendored ``Launched(bytes32,address,address,string,
    string,uint256,uint256)`` preimage's first three types.
    """
    topics = row.get("topics") or []
    if len(topics) < 4:
        return None
    decoded = _decode_launched_data(row.get("data") or "0x")
    if decoded is None:
        return None
    name, ticker, coin_supply_wei, initial_price_wad = decoded
    try:
        block = int(row.get("blockNumber"), 16)
    except (TypeError, ValueError):
        return None
    return {
        "pool_id": str(topics[1]).lower(),
        "coin": decode_address(topics[2]),
        "creator": decode_address(topics[3]),
        "name": name,
        "ticker": ticker,
        "coin_supply_wei": coin_supply_wei,
        "initial_price_wad": initial_price_wad,
        "block": block,
    }


def _decode_curve_swap_log(row: dict) -> dict | None:
    """One raw ``CurveSwap`` row -> its fields, or ``None`` if malformed.

    Fix round 1 (2026-08-24): the layout below is the REAL verified
    ``LaunchpadHook`` ABI (fetched from Blockscout), not the guess the
    Task 5 brief's frozen preimage alone could support -- topic0 hashing
    only pins the *type* list, never field names or which types are
    indexed. ``event CurveSwap(bytes32 indexed poolId, address indexed
    trader, address indexed router, bool buy, uint256 ethAmount, uint256
    imdAmount, uint256 coinAmount, uint256 creatorFeeEth, uint256
    burnFeeImd)``.

    There is **no coin-address field anywhere in this event** -- the
    original guess read ``topics[2]`` as a coin address and ``topics[3]``
    as trader; both were wrong (``topics[2]`` is trader, ``topics[3]`` is
    router, and no slot names the coin at all). A swap is attributed to a
    launched coin exclusively by joining ``poolId`` against the
    ``Launched`` sweep -- see ``_launchpad_logs``, which already did that
    join correctly (on ``pool_id``, never on this now-removed field), so
    this fix changes what the fields mean, not how they get used.
    ``router`` is decoded but nothing currently consumes it.
    """
    topics = row.get("topics") or []
    if len(topics) < 4:
        return None
    raw = strip0x(row.get("data") or "0x")
    if len(raw) < 6 * 64:
        return None
    try:
        block = int(row.get("blockNumber"), 16)
    except (TypeError, ValueError):
        return None
    return {
        "pool_id": str(topics[1]).lower(),
        "trader": decode_address(topics[2]),
        "router": decode_address(topics[3]),
        "is_buy": decode_uint(raw, 0) != 0,
        "eth_amount_wei": decode_uint(raw, 1),
        "imd_amount_wei": decode_uint(raw, 2),
        "coin_amount_wei": decode_uint(raw, 3),
        "creator_fee_eth_wei": decode_uint(raw, 4),
        "burn_fee_imd_wei": decode_uint(raw, 5),
        "block": block,
    }


def _decode_imd_burned_amount(row: dict) -> int | None:
    """``ImdBurned(uint256 amount)`` -- one hook-wide aggregate per event,
    never per coin: the burn pipeline batches whatever has accrued."""
    raw = strip0x(row.get("data") or "0x")
    if len(raw) < 64:
        return None
    return decode_uint(raw, 0)


class _LaunchpadSweep(NamedTuple):
    """Everything ``fetch_launchpad`` needs out of one pass over the logs.

    A ``NamedTuple`` rather than the bare 6-tuple this used to return: the
    cursor rewrite took it to eleven fields, and eleven positional unpackings
    at the call site is exactly how a pair of same-typed neighbours
    (``launch_count``/``new_24h``, ``swap_count``/``trader_count``) gets
    silently transposed.

    ``launches`` is the **merged** population -- the cursor's history plus
    whatever this pass added -- not the rows this pass decoded, so it is what
    ``launch_count``/``creator_count`` are taken over. ``day_swaps`` is the
    opposite: a windowed slice, only the rows inside
    ``LAUNCHPAD_DAY_BLOCKS`` of the head, which is why it is re-read every
    pass instead of accumulated (see ``_launchpad_logs``).

    Every aggregate is ``None`` on a failed sweep and never ``0``; the
    dict-shaped ones (``swaps_all``, ``swaps_by_coin``, ``coin_tickers``)
    keep the same split, with ``{}`` reserved for "swept, and quiet".
    """

    launches: list[dict]
    day_swaps: list[dict]
    swaps_all: dict[str, int]
    swap_count: int | None
    trader_count: int | None
    burned_total_wei: int | None
    swaps_by_coin: dict[str, int] | None
    coin_tickers: dict[str, str] | None
    launch_count: int | None
    new_24h: int | None
    creator_count: int | None
    cursor: dict | None


#: Length cap for the two attacker-chosen strings the launchpad cursor
#: PERSISTS. ``LaunchpadFactory.launch(string,string)`` is permissionless and
#: unpriced beyond gas, so a name is whatever somebody paid calldata for --
#: and this task is what turned those strings from transient decode output
#: into cache-file content that is re-read and rewritten every tick. Without
#: a cap, one launch with a megabyte name grows ``~/.maxpane/surf_cache.json``
#: by a megabyte forever. 64 is deliberately generous against the widest cell
#: that ever shows one (``widgets/surf/launchpad._NAME_COLS`` = 18): the cap
#: is a bound on the FILE, not a display decision, and truncating to the
#: column width here would throw away a name the layout might one day widen.
_LAUNCHPAD_TEXT_MAX = 64


def _launchpad_text(value: Any) -> str:
    """One attacker-chosen launchpad string, bounded, for persistence.

    Applied on both sides of the cache file -- on the way in from a decoded
    ``Launched`` and on the way back out of a cursor -- because a hand-edited
    payload can carry a string no chain event ever produced. Escaping is
    still the render layer's job and deliberately does NOT happen here.
    """
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    return value[:_LAUNCHPAD_TEXT_MAX]


def _failed_launchpad_sweep(resume: dict | None) -> _LaunchpadSweep:
    """The all-unknown sweep, carrying *resume* back out untouched.

    The cursor is the one field a failure must **return, not reset**:
    ``swaps_all``, the trader set and the burn totals inside it are persisted
    accumulators, and CLAUDE.md's "a failed read is ``None``, never ``0``"
    bites hardest on those -- a zero written into an accumulator outlives the
    outage that produced it, and no later sweep can tell it was ever wrong.
    So nothing merges, nothing advances, nothing zeroes: the very object we
    were handed goes back, and every aggregate reads unknown.

    The one thing it will not hand back is a *non-dict*.
    ``LaunchpadState.cursor`` is declared ``dict | None``, and the manager
    reads ``payload["cursor"]["last_block"]`` off it; passing a string or an
    int straight through would honour "untouched" by breaking the field's own
    type, and the crash would land one layer away from the cache file that
    caused it. Something unusable is ``None`` -- "no cursor", which is the
    same thing the cold sweep already means.
    """
    return _LaunchpadSweep(
        launches=[], day_swaps=[], swaps_all={}, swap_count=None,
        trader_count=None, burned_total_wei=None, swaps_by_coin=None,
        coin_tickers=None, launch_count=None, new_24h=None,
        creator_count=None,
        cursor=resume if isinstance(resume, dict) else None,
    )


def _coerce_launchpad_resume(resume: Any) -> dict | None:
    """A persisted launchpad cursor -> its normalised form, or ``None``.

    ``None`` means "sweep cold, from :data:`surf_addresses.LAUNCHPAD_FIRST_BLOCK`",
    which is always a *safe* degradation: a cold sweep rebuilds every
    accumulator from chain, so the worst a rejected cursor costs is one
    wide sweep.  That is why anything structurally unusable is rejected whole
    rather than patched -- half-trusting a cursor is how a corrupt
    ``last_block`` would skip real history forever.

    The cache file is third-party input (curator's
    ``pattern_language()`` makes the same point about strings read back out of
    a persisted payload: a hand-edited cache is not our own data), so every
    field is coerced per entry rather than trusted wholesale, and an
    individually broken launch row is dropped instead of taking the cursor
    with it.  ``traders`` comes back as a ``set`` for the union that follows;
    it is re-serialised sorted, because a JSON cursor has to round-trip.
    """
    if not isinstance(resume, dict):
        return None
    last_block = resume.get("last_block")
    if isinstance(last_block, bool) or not isinstance(last_block, int):
        return None
    if last_block < 0:
        return None

    launches: dict[str, dict] = {}
    raw_launches = resume.get("launches")
    if isinstance(raw_launches, dict):
        for pool_id, rec in raw_launches.items():
            if not isinstance(pool_id, str) or not isinstance(rec, dict):
                continue
            block = rec.get("block")
            if isinstance(block, bool) or not isinstance(block, int):
                continue
            launches[pool_id.lower()] = {
                "ticker": _launchpad_text(rec.get("ticker")),
                "name": _launchpad_text(rec.get("name")),
                "creator": _launchpad_text(rec.get("creator")),
                "block": block,
            }

    def counter(key: str) -> dict[str, int]:
        raw = resume.get(key)
        out: dict[str, int] = {}
        if isinstance(raw, dict):
            for pool_id, count in raw.items():
                if not isinstance(pool_id, str):
                    continue
                if isinstance(count, bool) or not isinstance(count, int):
                    continue
                if count < 0:
                    continue
                out[pool_id.lower()] = count
        return out

    burned_total = resume.get("burned_total_wei")
    if isinstance(burned_total, bool) or not isinstance(burned_total, int):
        burned_total = 0
    burned_total = max(burned_total, 0)

    # `resume.get("traders") or ()` was not enough: a hand-edited `5` is
    # truthy and not iterable (TypeError straight out of a `fetch_*` that
    # promises it always returns a state), and a hand-edited `"abc"` iterates
    # as three one-character "addresses". Only a real sequence is a trader
    # list; anything else is no traders at all.
    raw_traders = resume.get("traders")
    traders = (
        {
            addr.lower()[:_LAUNCHPAD_TEXT_MAX]
            for addr in raw_traders
            if isinstance(addr, str) and addr
        }
        if isinstance(raw_traders, (list, tuple, set, frozenset))
        else set()
    )

    return {
        "last_block": last_block,
        "launches": launches,
        "swaps_all": counter("swaps_all"),
        "burn_by_coin": counter("burn_by_coin"),
        "burned_total_wei": burned_total,
        "traders": traders,
    }


# ---------------------------------------------------------------------------
# Blockscout REST row parsing helpers
# ---------------------------------------------------------------------------


def _parse_iso_ts(ts: str | None) -> float | None:
    """Blockscout ISO-8601 ('2026-08-07T04:27:11.000000Z') -> epoch seconds."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _lenient_int(value: Any) -> int | None:
    """A Blockscout scalar that may be ``int``, ``str``, missing or ``null``.

    ``None`` for anything unreadable — **never** ``0``. The field this exists
    for is ``ChannelTx.nonce``, where ``0`` is a real value (the channel's
    genesis "soon" post), so ``int(row.get("nonce") or 0)`` would make every
    unreadable row impersonate it. ``bool`` is rejected for the same reason
    WP2's ``_as_int`` rejects it: ``True`` is never a nonce, and reading it as
    ``1`` turns a broken payload into a plausible number.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 10)
        except ValueError:
            return None
    return None


#: The closed label vocabulary for the activity column (PRD §4).
DEV_TX_KINDS = frozenset(
    {"deploy", "lp", "burn", "bridge", "fwa claim", "transfer", "other"}
)

_DEV_WALLET_LABELS: dict[str, str] = {
    A.DEV_WALLET.lower(): "dev",
    A.OPS_WALLET.lower(): "ops",
}

#: Inbound value at or below this is poisoning bait, not a payment.  Not used
#: by the filter — sender keying already removes every inbound row — and kept
#: as the documented PRD §4 threshold for whoever later surfaces inbound rows
#: deliberately.  See rule 2 in task WP1.6.
_DUST_WEI = 10**9


def _label_for(addr: str | None) -> str | None:
    """Allowlist lookup.  No fallback, no fuzzy match, no prefix match."""
    if not addr:
        return None
    return A.KNOWN_LABELS.get(addr.lower())


# ---------------------------------------------------------------------------
# Error classification — message text first (mirrors ttt_client; policy is
# deliberately NOT shared via rpc_common, see that module's docstring)
# ---------------------------------------------------------------------------

_ENDPOINT_LIMITATION_PATTERNS = (
    "limited to", "block range", "range is too large", "ranges over",
    "exceeds", "too large", "too many", "archive", "api key", "unauthorized",
    "authenticate", "free plan", "upgrade", "not supported", "unsupported",
    "capacity", "rate limit", "timeout", "try again", "cannot fulfill",
)

_RANGE_LIMITATION_PATTERNS = (
    "limited to", "block range", "range is too large", "ranges over",
)

_MALFORMED_REQUEST_CODES = {-32600, -32601, -32602, -32604, -32700}


def _looks_like_endpoint_limitation(err: Any) -> bool:
    """True if *err* reads as "this endpoint can't", not "this request is bad"."""
    if not isinstance(err, dict):
        return True
    message = str(err.get("message") or "").lower()
    if any(frag in message for frag in _ENDPOINT_LIMITATION_PATTERNS):
        return True
    return err.get("code") not in _MALFORMED_REQUEST_CODES


def _is_range_limitation(err: Any) -> bool:
    """True only for "your block range is too wide" — the shrinkable class."""
    if not isinstance(err, dict):
        return False
    message = str(err.get("message") or "").lower()
    return any(frag in message for frag in _RANGE_LIMITATION_PATTERNS)


class _LogRangeError(RuntimeError):
    """eth_getLogs failed because the requested window is too wide."""


def _addr_topic(addr: str) -> str:
    """Left-pad a 20-byte address into a 32-byte ``eth_getLogs`` topic word."""
    return "0x" + pad_left(strip0x(addr).lower(), 64)


class SurfClient(OwnedHttpClient):
    """Async, keyless, read-only client for every surf data source."""

    def __init__(
        self,
        state_rpc: str = STATE_RPC_PRIMARY,
        state_fallbacks: list[str] | None = None,
        log_rpcs: list[str] | None = None,
        blockscout_base: str = BLOCKSCOUT_BASE,
        *,
        http_client: httpx.AsyncClient | None = None,
        inter_call_delay: float = _INTER_CALL_DELAY,
        backoff_seconds: tuple[float, ...] = _BACKOFF_SECONDS,
        now_fn: Callable[[], float] = time.time,
        log_window_blocks: int = LOG_WINDOW_BLOCKS,
    ) -> None:
        self._state_rpcs = [state_rpc, *(state_fallbacks or STATE_RPC_FALLBACKS)]
        self._log_rpcs = list(log_rpcs or LOG_RPCS)
        for url in (*self._state_rpcs, *self._log_rpcs):
            host = (urlparse(url).hostname or "").lower()
            if host in _BANNED_RPC_HOSTS:
                raise ValueError(
                    f"{url} is a banned RPC host (dead, keyed or useless) — "
                    "see surf_client._BANNED_RPC_HOSTS"
                )
        self._blockscout = blockscout_base.rstrip("/")
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._inter_call_delay = inter_call_delay
        self._backoff_seconds = backoff_seconds
        self._now_fn = now_fn
        self._log_window_blocks = log_window_blocks
        self._request_id = 0
        self._last_rpc_at: float = 0.0
        #: True only when the most recent ``fetch_channel_txs()`` hit
        #: ``MAX_CHANNEL_PAGES`` while Blockscout was still reporting a
        #: ``next_page_params`` cursor — i.e. more rows existed than that
        #: sweep was willing to fetch. Reset to ``False`` at the START of
        #: every call (never left stale from a previous cycle) so a caller
        #: can trust it as "true right now", not "true once, ever". WP4
        #: reads this to render a degraded/partial-feed flag; this client
        #: does not render anything itself.
        self.channel_truncated: bool = False
        #: Same contract as ``channel_truncated``, for ``fetch_dev_activity()``:
        #: True when EITHER the dev-wallet or the ops-wallet page fetch hit
        #: ``MAX_ACTIVITY_PAGES`` while Blockscout still had a
        #: ``next_page_params`` cursor. Reset to ``False`` at the START of
        #: every call. A single bool, not per-wallet, because the frozen
        #: ``SURF_KEYS``/``degraded`` surface tracks source GROUPS
        #: ("dev_activity"), not individual wallets — the extra bit would be
        #: dead weight downstream. The dropped detail (which wallet) still
        #: reaches the log line in ``fetch_dev_activity``. This flag matters
        #: more than the channel's: a truncated activity page can drop a
        #: ``created_contract`` row off the end, which is the sole signal the
        #: NEW DEPLOY detector watches for — silent truncation there means the
        #: dashboard reports "nothing deployed" when something did.
        self.activity_truncated: bool = False
        #: Per-group failure flags for the most recent ``fetch_recent_logs()``
        #: call, keyed by the exact ``LogWindow`` field name each result feeds
        #: (``bridge_mints`` / ``identity_updates`` / ``v4_initializes`` /
        #: ``seaport_sales``). Reset to all ``False`` at the START of every
        #: call, same contract as ``channel_truncated`` / ``activity_truncated``
        #: above. A ``dict`` rather than a fifth bool because the four groups
        #: feed four independent detectors (BRIDGE STAGE / GATE OPEN /
        #: V4 LAUNCH / NFT sales) and the manager must be able to degrade only
        #: the one that actually failed — collapsing them into one flag would
        #: make a dead Seaport filter mark a healthy bridge-mint filter
        #: degraded too. This is the out-of-band channel ``LogWindow``'s own
        #: docstring calls for: its four tuple fields cannot hold ``None``, so
        #: ``()`` is ambiguous between "read succeeded, nothing matched" and
        #: "read failed" on its own — this dict is what resolves that
        #: ambiguity for whoever reads the ``LogWindow`` this call returns.
        #: ``v4_initializes`` is flagged failed if EITHER the currency0 or the
        #: currency1 query failed, even when the other one returned rows: a
        #: real v4 Initialize on the failed side is invisible either way, and
        #: reporting the group as healthy because the *other* query happened
        #: to succeed would hide exactly that gap.
        self.log_group_failed: dict[str, bool] = {
            "bridge_mints": False,
            "identity_updates": False,
            "v4_initializes": False,
            "seaport_sales": False,
        }

    # Lifecycle (close / __aenter__ / __aexit__) comes from OwnedHttpClient.

    @property
    def state_endpoints(self) -> list[str]:
        return list(self._state_rpcs)

    @property
    def log_endpoints(self) -> list[str]:
        return list(self._log_rpcs)

    # ------------------------------------------------------------------
    # RPC plumbing
    # ------------------------------------------------------------------

    async def _post_rpc(self, url: str, payload: Any) -> httpx.Response:
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)
        return await self._client.post(url, json=payload)

    async def _rpc_state(self, method: str, params: list) -> Any:
        """One JSON-RPC call on the state pool, retry + rotation.

        Rotation policy mirrors ``fwa_client``: this pool issues only plain
        getters, so the cheapest recovery from any *endpoint* problem is the
        next endpoint. A malformed-request error, however, is OUR bug: it
        fails identically everywhere, so it short-circuits the chain.
        """
        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self._state_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payload)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break  # rotate, do not retry a dead host
                    resp.raise_for_status()
                    body = resp.json()
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break  # rotate
                        raise RuntimeError(f"malformed request: {err}")
                    return body.get("result")
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all state endpoints failed: {last_err}")

    async def _rpc_state_batch(
        self, calls: list[tuple[str, list]]
    ) -> list[Any] | None:
        """One JSON-RPC *batch array* POST on the state pool.

        Returns per-entry results aligned with *calls*; an entry that came
        back as an error is ``None`` (NEVER 0). Returns ``None`` only when
        every endpoint failed to serve the batch at all.
        """
        payloads = []
        for method, params in calls:
            self._request_id += 1
            payloads.append(jsonrpc_payload(self._request_id, method, params))
        id_to_idx = {p["id"]: i for i, p in enumerate(payloads)}
        last_err: BaseException | None = None
        for url in self._state_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payloads)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break
                    resp.raise_for_status()
                    body = resp.json()
                    if not isinstance(body, list):
                        # An endpoint that answers a batch with a scalar is
                        # not speaking the protocol; rotate.
                        last_err = RuntimeError(f"{url}: non-batch reply")
                        break
                    results: list[Any] = [None] * len(payloads)
                    for entry in body:
                        idx = id_to_idx.get(entry.get("id"))
                        if idx is None:
                            continue
                        if entry.get("error"):
                            logger.warning(
                                "batch entry %s failed: %s",
                                calls[idx][0], entry["error"],
                            )
                            continue  # stays None — never 0
                        results[idx] = entry.get("result")
                    return results
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        logger.warning("state batch failed on every endpoint: %s", last_err)
        return None

    async def _rpc_logs(self, method: str, params: list) -> Any:
        """One JSON-RPC call on the LOGS pool.

        Raises ``_LogRangeError`` when the message says the window is too
        wide (the caller halves its own window — a provider's "suggested
        range" is NEVER followed: one of them decrements a block per round
        trip and livelocks verbatim followers). Other endpoint limitations
        rotate; malformed requests raise.
        """
        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self._log_rpcs:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._post_rpc(url, payload)
                    if resp.status_code in ENDPOINT_DEAD_CODES:
                        last_err = RuntimeError(f"{url} -> {resp.status_code}")
                        break
                    # drpc wraps its shrinkable range cap in an HTTP 400 —
                    # classify the JSON error body BEFORE raise_for_status
                    # (talismans_client learned this live).
                    body: Any = None
                    try:
                        body = resp.json()
                    except ValueError:
                        pass
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _is_range_limitation(err):
                            raise _LogRangeError(str(err))
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break
                        raise RuntimeError(f"malformed request: {err}")
                    resp.raise_for_status()
                    return body.get("result") if isinstance(body, dict) else None
                except _LogRangeError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all log endpoints failed: {last_err}")

    # ------------------------------------------------------------------
    # REST plumbing (Blockscout v2 / DexScreener / GeckoTerminal)
    # ------------------------------------------------------------------

    async def _get_json(self, url: str, params: dict | None = None) -> Any:
        """GET with retries. Returns parsed JSON, or ``None`` on any failure."""
        for attempt in range(_MAX_RETRIES):
            try:
                self._last_rpc_at = await pace(
                    self._last_rpc_at, self._inter_call_delay
                )
                resp = await self._client.get(url, params=params)
                if resp.status_code in ENDPOINT_DEAD_CODES:
                    logger.warning("GET %s -> %s", url, resp.status_code)
                    return None
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(self._backoff_seconds[attempt])
                else:
                    logger.warning("GET %s failed: %s", url, exc)
        return None

    # ------------------------------------------------------------------
    # Public API — fast tier
    # ------------------------------------------------------------------

    async def fetch_nonces(self) -> NonceSet | None:
        """The three account nonces **and the height they were read at**, one
        batched POST (PRD §3 signals 1/2/4).

        The announce channel emits NO logs — this poll IS the new-post
        detector. A failed leg is ``None``: turning it into 0 would read as
        "fresh EOA" and un-fire / re-fire every nonce-derived signal, and a
        ``block_number`` of 0 would read as genesis.

        ``eth_blockNumber`` is the fourth entry of the same batch array, not a
        second round trip: a height fetched separately can describe a different
        block from the counts, which is worse than no height at all for a
        detector that diffs nonces between refreshes. It is also why the fast
        tier is still ONE request.
        """
        addrs = [A.ANNOUNCE, A.DEV_WALLET, A.OPS_WALLET]
        try:
            results = await self._rpc_state_batch(
                [("eth_getTransactionCount", [a, "latest"]) for a in addrs]
                + [("eth_blockNumber", [])]
            )
        except RuntimeError as exc:  # malformed-request short-circuit
            logger.warning("fetch_nonces: %s", exc)
            return None
        if results is None:
            return None

        def to_int(hex_or_none: Any) -> int | None:
            if not isinstance(hex_or_none, str):
                return None
            try:
                return int(hex_or_none, 16)
            except ValueError:
                return None

        return NonceSet(
            announce=to_int(results[0]),
            dev=to_int(results[1]),
            ops=to_int(results[2]),
            block_number=to_int(results[3]),
        )

    async def fetch_chain_state(self) -> ChainState | None:
        """The fast-tier eth_call round: one aggregate3 over nine views.

        Sub-call order is positional and mirrored in the decode below.
        Every sub-call is ``allowFailure=True``: a single reverted view
        degrades one field to ``None``, never the round — except the first
        two, where a revert is decoded as ``ChainState.lp_state == "gone"``
        rather than ``None``: see ``_lp_state``.

        The eighth sub-call is Multicall3's own ``getBlockNumber()``, which is
        how ``ChainState.block_number`` gets a producer without a second round
        trip. Reading the height inside the same ``eth_call`` also makes it
        *the* height of this state: fetch it separately and a reorg or a
        rotated endpoint can hand back a block the other seven never saw.

        The ninth sub-call is the v4 side of the 2026-08-17 migration:
        ``PositionManager.balanceOf(OPS_WALLET)`` — how many v4 position NFTs
        the ops wallet now holds. Verified live: exactly 1.
        """
        calls = [
            (A.NFPM, A.SEL_POSITIONS + encode_uint(A.LP_POSITION_ID)),
            (A.NFPM, A.SEL_OWNER_OF + encode_uint(A.LP_POSITION_ID)),
            (A.IDENTITY_REGISTRY, A.SEL_IDENTITY_ALLOWED),
            (A.IMD_TOKEN, A.SEL_TOTAL_SUPPLY),
            (A.POOL_V3, A.SEL_SLOT0),
            (A.IMD_TOKEN, A.SEL_NAME),
            (A.IMD_TOKEN, A.SEL_SYMBOL),
            (MULTICALL3, _SEL_GET_BLOCK_NUMBER),
            (
                A.POSITION_MANAGER_V4,
                A.SEL_BALANCE_OF + pad_left(strip0x(A.OPS_WALLET).lower(), 64),
            ),
        ]
        # NOTE the tuple order evm_abi.encode_aggregate3 actually takes:
        # (target, callData, allowFailure) -- NOT (target, allow, data).
        data = encode_aggregate3(
            [(target, calldata, True) for target, calldata in calls]
        )
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": data}, "latest"]
            )
        except RuntimeError as exc:
            logger.warning("fetch_chain_state: %s", exc)
            return None
        results = decode_aggregate3_result(raw or "0x")
        if len(results) != len(calls):
            logger.warning("fetch_chain_state: short aggregate3 reply")
            return None

        def ok(i: int) -> str | None:
            success, ret = results[i]
            return ret if success and strip0x(ret) else None

        pos = _decode_positions(ok(0)) if ok(0) else None
        owner_raw = ok(1)
        gate_raw = ok(2)
        supply_raw = ok(3)
        slot0 = _decode_slot0(ok(4)) if ok(4) else None
        name_raw, sym_raw = ok(5), ok(6)
        block_raw = ok(7)
        balance_raw = ok(8)

        # `ok()` collapses success/failure into `ret or None`, which is
        # exactly the conflation this field exists to undo: `results[0]` is
        # the raw `(success, returnData)` pair, so a revert (success=False)
        # is still visible as evidence, not indistinguishable from silence.
        lp_state = _lp_state(results[0], results[1])

        # The two LP side amounts (PRD §5 `lp_imd` / `lp_weth`).  Mapped by
        # ADDRESS: this pool orders WETH as token0, but trusting the index
        # instead of the address is how a dashboard prints 142 IMD and 388k
        # WETH the first time a pool is deployed the other way round.
        amount0, amount1 = _position_amounts_wei(
            pos["liquidity"] if pos else None,
            slot0["sqrt_price_x96"] if slot0 else None,
            pos["tick_lower"] if pos else None,
            pos["tick_upper"] if pos else None,
        )
        weth_wei = imd_wei = None
        if pos and (pos["token0"] or "").lower() == A.WETH.lower():
            weth_wei, imd_wei = amount0, amount1
        elif pos and (pos["token1"] or "").lower() == A.WETH.lower():
            imd_wei, weth_wei = amount0, amount1
        else:
            logger.warning(
                "fetch_chain_state: position %s is not a WETH pair (%s/%s) — "
                "LP sides unavailable",
                A.LP_POSITION_ID,
                pos and pos["token0"], pos and pos["token1"],
            )

        # Keyword names are WP0.4's CONSTRUCTOR_KWARGS[ChainState], verbatim.
        return ChainState(
            lp_imd_wei=imd_wei,
            lp_weth_wei=weth_wei,
            lp_liquidity=pos["liquidity"] if pos else None,
            lp_token0=pos["token0"] if pos else None,
            lp_token1=pos["token1"] if pos else None,
            lp_fee=pos["fee"] if pos else None,
            lp_tokens_owed0_wei=pos["tokens_owed0"] if pos else None,
            lp_tokens_owed1_wei=pos["tokens_owed1"] if pos else None,
            lp_owner=decode_address(owner_raw) if owner_raw else None,
            identity_allowed=(
                None if gate_raw is None else decode_uint(gate_raw, 0) != 0
            ),
            imd_supply_wei=(
                None if supply_raw is None else decode_uint(supply_raw, 0)
            ),
            sqrt_price_x96=slot0["sqrt_price_x96"] if slot0 else None,
            pool_tick=slot0["tick"] if slot0 else None,
            imd_name=decode_string(name_raw) if name_raw else None,
            imd_symbol=decode_string(sym_raw) if sym_raw else None,
            block_number=(
                None if block_raw is None else decode_uint(block_raw, 0)
            ),
            lp_state=lp_state,
            lp_position_count=(
                None if balance_raw is None else decode_uint(balance_raw, 0)
            ),
        )

    async def fetch_pool_v4(self) -> PoolV4State:
        """Read the live IMD/ETH v4 pool via two sequential ``aggregate3`` rounds.

        v4 has no ``slot0()`` getter, and the *id* of the live pool is not a
        constant either: 38 ETH/IMD v4 pools exist on mainnet and 37 are
        decoys at other fee tiers, so which one is real is a question with a
        wrong answer. Round 1 reads ``LaunchpadHook.imdEthPoolId()`` — the
        dev's own on-chain declaration of his pool. Round 2 needs that id
        first, because it computes the pool's storage slot from it, which is
        why this cannot be folded into one multicall: the two rounds are
        necessarily sequential, not a batching opportunity missed.

        A failed hook read falls back to the vendored
        ``A.POOL_V4_ID_FALLBACK`` constant, and ``pool_id_source`` records
        which one was actually used ("hook" or "fallback") so a failed hook
        read can never silently masquerade as a confirmed pool. Every
        sub-call keeps ``allowFailure=True``, so a reverted view degrades one
        field to ``None`` rather than the round — and unlike the other
        ``fetch_*`` methods, this one always returns a ``PoolV4State``: the
        pool is real, so there is no "does not exist" case, only "we could
        not read it right now".
        """
        pool_id: str | None = None
        hook_call = encode_aggregate3(
            [(A.LAUNCHPAD_HOOK, A.SEL_IMD_ETH_POOL_ID, True)]
        )
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": hook_call}, "latest"]
            )
            hook_results = decode_aggregate3_result(raw or "0x")
            if hook_results:
                success, ret = hook_results[0]
                ret_hex = strip0x(ret)
                if success and len(ret_hex) >= 64:
                    pool_id = "0x" + ret_hex[:64]
        except RuntimeError as exc:
            logger.warning("fetch_pool_v4: hook read failed: %s", exc)

        if pool_id is not None:
            pool_id_source = "hook"
        else:
            pool_id = A.POOL_V4_ID_FALLBACK
            pool_id_source = "fallback"

        slot0_key, liquidity_key = surf_v4.pool_state_slots(
            pool_id, A.V4_POOLS_MAPPING_SLOT
        )
        state_call = encode_aggregate3(
            [
                (A.POOL_MANAGER_V4, A.SEL_EXTSLOAD + strip0x(slot0_key), True),
                (A.POOL_MANAGER_V4, A.SEL_EXTSLOAD + strip0x(liquidity_key), True),
            ]
        )
        sqrt_price_x96: int | None = None
        tick: int | None = None
        lp_fee: int | None = None
        liquidity: int | None = None
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": state_call}, "latest"]
            )
            state_results = decode_aggregate3_result(raw or "0x")
            if len(state_results) == 2:
                def ok(i: int) -> str | None:
                    success, ret = state_results[i]
                    return ret if success and strip0x(ret) else None

                slot0_word = ok(0)
                liquidity_word = ok(1)
                if slot0_word is not None:
                    sqrt_price_x96, tick, lp_fee = surf_v4.decode_slot0(slot0_word)
                if liquidity_word is not None:
                    liquidity = surf_v4.decode_liquidity(liquidity_word)
        except RuntimeError as exc:
            logger.warning("fetch_pool_v4: extsload read failed: %s", exc)

        return PoolV4State(
            pool_id=pool_id,
            sqrt_price_x96=sqrt_price_x96,
            tick=tick,
            lp_fee=lp_fee,
            liquidity=liquidity,
            pool_id_source=pool_id_source,
        )

    # ------------------------------------------------------------------
    # State + logs RPC — the launchpad tier
    # ------------------------------------------------------------------

    async def fetch_launchpad(self, resume: dict | None = None) -> LaunchpadState:
        """The launchpad tier: one getter multicall, three log sweeps, then
        ``rank_coins`` off the swap logs alone.

        *resume* is the previous sweep's persisted cursor (``LaunchpadState.
        cursor``, cached in ``SLOT_LAUNCHPAD``), or ``None`` for a cold sweep
        from ``A.LAUNCHPAD_FIRST_BLOCK``. The returned state carries the
        cursor to persist and hand back next time. Passing ``None`` forever
        is correct, just wasteful: every sweep then re-reads the whole
        history and arrives at the same numbers.

        Cost is flat in ``coinCount``: ranking never issues a per-coin call
        (design idea 1 — see the analytics module docstring). Curve state —
        the live ``spotPriceEthPerCoin`` — is read only for the rows this
        method actually returns, in one more bounded ``aggregate3`` batch,
        never for the full coin population.

        State calls go to publicnode; every ``eth_getLogs`` goes to
        tenderly/drpc — the standing split (publicnode refuses archive
        ``eth_getLogs``).

        Always returns a ``LaunchpadState``, never ``None``: the launchpad is
        real, so a total outage is an honestly all-``None`` state, the same
        contract ``fetch_pool_v4`` keeps. ``imd_to_burn_wei`` and
        ``executor_balance_wei`` carry a representable zero; every other
        getter is ``None`` on failure, never ``0``.

        ``swaps_by_coin`` (fix round 2) rides the same ``CurveSwap`` sweep
        ``coins``/``swap_count``/``trader_count`` already read — the full
        per-coin distribution, not the ``LAUNCHPAD_RENDER_LIMIT``-capped one
        ``coins`` carries. See ``LaunchpadState``'s own docstring for why the
        two must stay separate: one is what the panel draws, the other is
        what HOT COIN's median is taken over.

        **The cursor carries more than ``last_block``/``launches``/
        ``swaps_all``**, and the extra keys are not bookkeeping -- they are
        the only thing keeping four *lifetime* figures lifetime once the
        sweep stopped re-reading all of history every tick.
        ``swap_count`` falls out of ``swaps_all`` for free, but
        ``trader_count`` (distinct traders, ``traders``),
        ``burned_total_wei`` (the ``ImdBurned`` running total) and each
        coin's ``imd_burned`` (``burn_by_coin``) have no additive shortcut
        from a 10-minute delta: a cardinality cannot be deduplicated after
        the fact, and a total cannot be recovered from its newest addend. So
        they are accumulated in the cursor, and a sweep that dropped them
        would keep rendering the same four labels over numbers that had
        quietly become "since the last tick". Every one of them is read back
        through ``_coerce_launchpad_resume``, because a cache file is
        third-party input.
        """
        getters = [
            (A.LAUNCHPAD_HOOK, A.SEL_IMD_TO_BURN),
            (A.LAUNCHPAD_HOOK, A.SEL_TOTAL_REAL_IMD),
            (A.LAUNCHPAD_HOOK, A.SEL_BURN_FEE_BPS),
            (A.LAUNCHPAD_HOOK, A.SEL_CREATOR_FEE_BPS),
            (A.LAUNCHPAD_HOOK, A.SEL_TOTAL_CREATOR_ETH_OWED),
            (A.LAUNCHPAD_FACTORY, A.SEL_COIN_COUNT),
            (A.BURN_EXECUTOR_V2, A.SEL_TOKEN_BALANCE),
            (A.BURN_EXECUTOR_V2, A.SEL_MIN_BRIDGE_AMOUNT),
        ]
        (
            imd_to_burn_wei, total_real_imd_wei, burn_fee_bps, creator_fee_bps,
            creator_eth_owed_wei, coin_count, executor_balance_wei, min_bridge_wei,
        ) = await self._launchpad_getters(getters)

        sweep = await self._launchpad_logs(resume)

        rows = surf_launchpad.rank_coins(
            sweep.launches, sweep.day_swaps, sweep.swaps_all,
            now_ts=self._now_fn(), limit=LAUNCHPAD_RENDER_LIMIT,
        )
        rows = await self._price_rendered_rows(rows)

        coins = tuple(
            LaunchpadCoin(
                ticker=row["ticker"],
                name=row["name"],
                creator=row["creator"],
                age_s=row["age_s"],
                price_eth=row["price_eth"],
                change_24h_pct=row["change_24h_pct"],
                swaps_24h=row["swaps_24h"],
                swaps_all=row["swaps_all"],
                imd_burned=row["imd_burned"],
            )
            for row in rows
        )

        # The two population reads, compared -- deliberately here and not
        # reconciled into one number. `coinCount()` is what the factory says
        # it minted; `launch_count` is what the log sweep actually found. They
        # agree on a healthy full sweep, and every way of NOT agreeing is
        # worth saying out loud: a cursor mid-catch-up (fine, transient), a
        # provider that truncated a page (was silent until this task paged the
        # reads), or a first block that is too late (permanent, and invisible
        # in the panel, which would just show fewer coins). This is the check
        # that would have caught the 33,000-block window reporting 66 of 146
        # as if it were the whole launchpad.
        if (
            coin_count is not None
            and sweep.launch_count is not None
            and sweep.launch_count != coin_count
        ):
            logger.warning(
                "launchpad population mismatch: the sweep found %d Launched "
                "event(s) but coinCount() says %d -- the sweep is %s the "
                "factory (cursor at %s)",
                sweep.launch_count, coin_count,
                "behind" if sweep.launch_count < coin_count else "ahead of",
                None if sweep.cursor is None else sweep.cursor.get("last_block"),
            )

        return LaunchpadState(
            coin_count=coin_count,
            imd_to_burn_wei=imd_to_burn_wei,
            total_real_imd_wei=total_real_imd_wei,
            burn_fee_bps=burn_fee_bps,
            creator_fee_bps=creator_fee_bps,
            creator_eth_owed_wei=creator_eth_owed_wei,
            executor_balance_wei=executor_balance_wei,
            min_bridge_wei=min_bridge_wei,
            coins=coins,
            swap_count=sweep.swap_count,
            trader_count=sweep.trader_count,
            burned_total_wei=sweep.burned_total_wei,
            swaps_by_coin=sweep.swaps_by_coin,
            coin_tickers=sweep.coin_tickers,
            launch_count=sweep.launch_count,
            new_24h=sweep.new_24h,
            creator_count=sweep.creator_count,
            cursor=sweep.cursor,
        )

    async def _launchpad_getters(
        self, getters: list[tuple[str, str]]
    ) -> tuple[int | None, ...]:
        """One ``aggregate3`` over the hook / factory / executor getters.

        Each leg is individually ``None`` on failure, never ``0`` — except
        that a genuine on-chain ``0`` (``imdToBurn``, ``tokenBalance``,
        ``minBridgeAmount``) decodes to the real integer ``0``, exactly the
        representable-zero contract ``LaunchpadState`` documents.
        """
        data = encode_aggregate3([(target, sel, True) for target, sel in getters])
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": data}, "latest"]
            )
        except RuntimeError as exc:
            logger.warning("fetch_launchpad getters: %s", exc)
            return (None,) * len(getters)
        results = decode_aggregate3_result(raw or "0x")
        if len(results) != len(getters):
            logger.warning("fetch_launchpad getters: short aggregate3 reply")
            return (None,) * len(getters)

        def ok(i: int) -> str | None:
            success, ret = results[i]
            return ret if success and strip0x(ret) else None

        return tuple(
            decode_uint(ok(i), 0) if ok(i) is not None else None
            for i in range(len(getters))
        )

    async def _launchpad_logs(self, resume: dict | None) -> _LaunchpadSweep:
        """Sweep ``Launched`` / ``CurveSwap`` / ``ImdBurned`` on the LOGS pool
        from the launchpad's first block, resuming through *resume*.

        **Why a cursor and not a window.** The launch history only ever grows
        and its start never moves, so any window measured back from the chain
        head walks off the far end of it one block per block. The 33,000-block
        window this replaced was already 702 blocks short on the day it was
        measured (2026-08-23: 146 launches, the earliest 33,702 blocks back)
        and it showed 66 of them -- with the launchpad's two busiest pools
        among the 80 it could not see, so they had no ticker, no name and no
        creator and could not reach the table at any sort order. An
        append-only log deserves an append-only read.

        **Cost.** A cold sweep (``resume is None``) covers everything from
        ``A.LAUNCHPAD_FIRST_BLOCK`` to the head -- ~34k blocks today, once.
        After that ``Launched`` and ``ImdBurned`` resume from
        ``last_block + 1``, so at the 600 s launchpad tier they are a few
        hundred blocks each. ``CurveSwap`` is the exception and never starts
        later than ``head - LAUNCHPAD_DAY_BLOCKS``: it feeds *windowed*
        statistics (``swaps_24h``, ``swaps_by_coin``, ``change_24h_pct``)
        which cannot be accumulated forward the way a lifetime total can --
        yesterday's swap has to *leave* the day. Re-reading a fixed 7,200
        blocks beats persisting a day of raw swap rows in the cache file and
        then having to trust them back: a re-read is self-healing, a
        persisted buffer is one more third-party structure to validate per
        point. The two ranges do not double count -- the accumulators only
        ever consume rows at or above ``from_block``, the day slice only ever
        rows at or above the day floor.

        **Resume is strictly greater than.** ``from_block = last_block + 1``.
        The boundary block was fully swept last time, so re-including it
        would add its swaps to ``swaps_all`` a second time -- and an
        off-by-one into a *persisted counter* corrupts it permanently and
        invisibly, because no later sweep can tell an inflated total from a
        real one.

        **A partial sweep is an outage.** If any of the three sweeps returns
        ``None``, nothing merges, nothing advances and nothing zeroes: the
        untouched *resume* goes back out as the cursor and every aggregate
        reads ``None``. There is no honest way to advance ``last_block`` past
        blocks whose ``CurveSwap`` rows were never read -- doing so would
        drop them from ``swaps_all`` forever while presenting the total as
        complete. Serving last-good behind an ``as of`` marker is the
        manager's job (``SLOT_LAUNCHPAD``), not this method's.

        ``launches`` is the merged population -- the cursor's history plus
        this pass -- keyed by ``pool_id``, so a re-seen ``Launched`` (a reorg
        replay, or a boundary block swept twice) overwrites its row rather
        than duplicating it. ``launch_count`` is its size, ``creator_count``
        the distinct ``creator`` over it, and ``new_24h`` the subset launched
        within ``LAUNCHPAD_DAY_BLOCKS`` of the head -- all three over the
        *full* history, never the ``LAUNCHPAD_RENDER_LIMIT``-capped slice
        ``coins`` carries.

        ``swaps_by_coin`` is the **full** per-coin day distribution -- every
        coin with a swap today, not the render-capped slice -- because
        ``surf_launchpad.hot_coin_threshold`` takes a *median* over it and a
        median of only the busiest 20 runs several times too high. It is
        keyed by ``pool_id``, the coin's identity, and never by ticker
        (``launch(string,string)`` is permissionless, so two coins can share
        one); ``coin_tickers`` is the companion ``{pool_id: ticker}`` map that
        exists only so a row can be *labelled*, carrying the ticker raw
        because escaping belongs to the render layer.
        """
        prior = _coerce_launchpad_resume(resume)
        try:
            head_hex = await self._rpc_logs("eth_blockNumber", [])
            head = int(head_hex, 16)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.warning("fetch_launchpad logs head: %s", exc)
            return _failed_launchpad_sweep(resume)

        from_block = (
            A.LAUNCHPAD_FIRST_BLOCK if prior is None else prior["last_block"] + 1
        )
        day_from = max(A.LAUNCHPAD_FIRST_BLOCK, head - LAUNCHPAD_DAY_BLOCKS)
        # The swap sweep has to cover both the unread tail AND the whole day;
        # clamped to the head so a cursor that is somehow ahead of the chain
        # (a lagging endpoint, a reorg) asks for a degenerate range instead of
        # a negative one.
        swap_from = min(min(from_block, day_from), head)

        # `_get_logs_paged`, never `_get_logs_shrinking`: the shrinking
        # reader answers a wide ask by discarding the OLDEST blocks and
        # returning the remainder as a success, and the oldest blocks are
        # precisely the launches this sweep exists to recover.
        launched_rows = await self._get_logs_paged(
            {"address": A.LAUNCHPAD_FACTORY, "topics": [A.TOPIC_LAUNCHED]},
            min(from_block, head), head, group="launchpad_launched",
        )
        swap_rows = await self._get_logs_paged(
            {"address": A.LAUNCHPAD_HOOK, "topics": [A.TOPIC_CURVE_SWAP]},
            swap_from, head, group="launchpad_curve_swap",
        )
        burned_rows = await self._get_logs_paged(
            {"address": A.LAUNCHPAD_HOOK, "topics": [A.TOPIC_IMD_BURNED]},
            min(from_block, head), head, group="launchpad_imd_burned",
        )
        if launched_rows is None or swap_rows is None or burned_rows is None:
            return _failed_launchpad_sweep(resume)

        # ---- merge: the cursor's history, then this pass on top -----------
        merged: dict[str, dict] = dict(prior["launches"]) if prior else {}
        for row in launched_rows or ():
            parsed = _decode_launched_log(row)
            if parsed is None or parsed["block"] < from_block:
                continue
            merged[parsed["pool_id"]] = {
                # Bounded before it is ever persisted: `launch(string,string)`
                # is permissionless, and the cursor is a file we rewrite every
                # tick.
                "ticker": _launchpad_text(parsed["ticker"]),
                "name": _launchpad_text(parsed["name"]),
                "creator": _launchpad_text(parsed["creator"]),
                "block": parsed["block"],
            }

        swaps_all: dict[str, int] = dict(prior["swaps_all"]) if prior else {}
        burn_by_coin: dict[str, int] = dict(prior["burn_by_coin"]) if prior else {}
        traders: set[str] = set(prior["traders"]) if prior else set()
        burned_total_wei: int = prior["burned_total_wei"] if prior else 0

        day_swaps: list[dict] = []
        day_priced: dict[str, list[dict]] = {}
        swaps_by_coin: dict[str, int] = {}
        for row in swap_rows:
            parsed = _decode_curve_swap_log(row)
            if parsed is None:
                continue
            pool_id = parsed["pool_id"]
            block = parsed["block"]
            # Lifetime accumulators: only the never-before-read tail. Rows
            # below `from_block` are here for the day window alone and were
            # already counted by the sweep that first read them.
            if block >= from_block:
                swaps_all[pool_id] = swaps_all.get(pool_id, 0) + 1
                if parsed["trader"]:
                    traders.add(parsed["trader"].lower())
                if pool_id in merged:
                    burn_by_coin[pool_id] = (
                        burn_by_coin.get(pool_id, 0) + parsed["burn_fee_imd_wei"]
                    )
            if block >= day_from:
                day_swaps.append({
                    "pool_id": pool_id,
                    "trader": parsed["trader"],
                    "is_buy": parsed["is_buy"],
                })
                if pool_id in merged:
                    swaps_by_coin[pool_id] = swaps_by_coin.get(pool_id, 0) + 1
                    day_priced.setdefault(pool_id, []).append(parsed)

        for row in burned_rows:
            try:
                block = int(row.get("blockNumber"), 16)
            except (TypeError, ValueError):
                continue
            if block < from_block:
                continue
            amount = _decode_imd_burned_amount(row)
            if amount is not None:
                burned_total_wei += amount

        # ---- derive the payload -------------------------------------------
        now_ts = self._now_fn()
        # change_24h_pct comes from log data alone -- no RPC call, unlike
        # price_eth. CurveSwap carries no price field, so a swap's effective
        # price is ethAmount/coinAmount and the day's move is first vs last.
        # None -- never 0.0 -- when fewer than two in-window swaps carry a
        # usable (non-zero coinAmount) price: "no measurable move" is not the
        # claim "a flat day", and collapsing the two would rank a coin with
        # one swap as unchanged rather than unmeasured.
        change_by_pool: dict[str, float] = {}
        for pool_id, entries in day_priced.items():
            entries.sort(key=lambda p: p["block"])
            priced = [p for p in entries if p["coin_amount_wei"] > 0]
            if len(priced) < 2:
                continue
            first = priced[0]["eth_amount_wei"] / priced[0]["coin_amount_wei"]
            last = priced[-1]["eth_amount_wei"] / priced[-1]["coin_amount_wei"]
            if first:
                change_by_pool[pool_id] = (last / first - 1.0) * 100.0

        launches = [
            {
                "pool_id": pool_id,
                "ticker": rec["ticker"],
                "name": rec["name"],
                "creator": rec["creator"],
                "creator_known": _label_for(rec["creator"]) is not None,
                "ts": now_ts - (head - rec["block"]) * _LAUNCHPAD_BLOCK_SECONDS,
                "price_eth": None,     # filled in for rendered rows only
                "change_24h_pct": change_by_pool.get(pool_id),
                # A representable zero: a coin that has launched and never
                # traded really has burned nothing.
                "imd_burned": burn_by_coin.get(pool_id, 0) / 1e18,
            }
            for pool_id, rec in sorted(
                merged.items(), key=lambda kv: (kv[1]["block"], kv[0])
            )
        ]

        cursor = {
            # Never backwards: `swaps_all` and the trader set are
            # accumulators, and a cursor that retreated would re-count the
            # blocks it gave back.
            "last_block": head if prior is None else max(head, prior["last_block"]),
            "launches": {
                pool_id: dict(rec) for pool_id, rec in merged.items()
            },
            "swaps_all": swaps_all,
            "burn_by_coin": burn_by_coin,
            "burned_total_wei": burned_total_wei,
            # A sorted list, not a set: this round-trips through JSON. It is
            # the one part of the cursor that grows with *traders* rather than
            # with coins (673 addresses on 2026-08-23, ~30 KB), and it is
            # here because distinct-trader cardinality is the one lifetime
            # aggregate with no additive shortcut -- a count cannot be
            # deduplicated after the fact.
            "traders": sorted(traders),
        }

        return _LaunchpadSweep(
            launches=launches,
            day_swaps=day_swaps,
            swaps_all=swaps_all,
            swap_count=sum(swaps_all.values()),
            trader_count=len(traders),
            burned_total_wei=burned_total_wei,
            swaps_by_coin=swaps_by_coin,
            coin_tickers={
                pool_id: rec["ticker"] for pool_id, rec in merged.items()
            },
            launch_count=len(merged),
            new_24h=sum(1 for rec in merged.values() if rec["block"] >= day_from),
            creator_count=len({rec["creator"] for rec in merged.values()}),
            cursor=cursor,
        )

    async def _price_rendered_rows(self, rows: list[dict]) -> list[dict]:
        """Read live ``spotPriceEthPerCoin`` for exactly the rows
        ``rank_coins`` returned — never the full coin population.

        A missing/failed leg leaves that row's ``price_eth`` at whatever
        ``rank_coins`` already gave it (``None``), never a guessed value.

        The pool comes off the **row's own** ``pool_id`` (final fix wave, I1).
        It used to be looked up through a ``{ticker: pool_id}`` map built from
        the launches, which silently collapsed two coins sharing a ticker —
        so the impostor's pool could be quoted and rendered as the real coin's
        price. ``launch(string,string)`` is permissionless, so that is a
        thing anyone can arrange for the price of gas.
        """
        if not rows:
            return rows
        calls: list[tuple[str, str]] = []
        order: list[int] = []
        for i, row in enumerate(rows):
            pool_id = row.get("pool_id")
            if not pool_id:
                continue
            calls.append(
                (A.LAUNCHPAD_HOOK, A.SEL_SPOT_PRICE_ETH_PER_COIN + strip0x(pool_id))
            )
            order.append(i)
        if not calls:
            return rows
        data = encode_aggregate3([(t, cd, True) for t, cd in calls])
        try:
            raw = await self._rpc_state(
                "eth_call", [{"to": MULTICALL3, "data": data}, "latest"]
            )
        except RuntimeError as exc:
            logger.warning("fetch_launchpad price round: %s", exc)
            return rows
        results = decode_aggregate3_result(raw or "0x")
        if len(results) != len(calls):
            logger.warning("fetch_launchpad price round: short aggregate3 reply")
            return rows
        priced = list(rows)
        for idx, (success, ret) in zip(order, results):
            if success and strip0x(ret):
                priced[idx] = {**priced[idx], "price_eth": decode_uint(ret, 0) / 1e18}
        return priced

    async def fetch_decoy_pool_count(
        self, real_pool_id: str | None
    ) -> tuple[int | None, dict | None]:
        """How many OTHER ETH/IMD v4 pools exist, and the newest one's row.

        One ``getLogs`` on ``TOPIC_V4_INITIALIZE`` filtered to
        ``currency1 == IMD`` — LOGS POOL ONLY — minus *real_pool_id*. 37 of
        38 such pools are third-party decoys (some squatting within one pip
        of the real 1% fee tier), so the count is itself a signal worth
        rendering, and "the newest" surfaces the most recent squat rather
        than a fixed historical one.

        Returns ``(None, None)`` on total outage — the read failed, we do not
        know. An empty, successfully-read sweep (no decoys at all) is the
        representable ``(0, None)``: we looked, and there were none.
        """
        try:
            head_hex = await self._rpc_logs("eth_blockNumber", [])
            head = int(head_hex, 16)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.warning("fetch_decoy_pool_count head: %s", exc)
            return None, None
        rows = await self._get_logs_shrinking(
            {
                "address": A.POOL_MANAGER_V4,
                "topics": [A.TOPIC_V4_INITIALIZE, None, None,
                           _addr_topic(A.IMD_TOKEN)],
            },
            V4_INITIALIZE_SEARCH_FROM_BLOCK, head, group="v4_decoy_pools",
        )
        if rows is None:
            return None, None

        real = (real_pool_id or "").lower()
        decoys = [
            row for row in rows
            if len(row.get("topics") or []) > 1
            and str(row["topics"][1]).lower() != real
        ]
        if not decoys:
            return 0, None

        newest_row = max(decoys, key=lambda r: int(r.get("blockNumber") or "0x0", 16))
        topics = newest_row.get("topics") or []
        data = strip0x(newest_row.get("data") or "0x")
        newest = {
            "pool_id": str(topics[1]).lower() if len(topics) > 1 else None,
            "currency0": decode_address(topics[2]) if len(topics) > 2 else None,
            "currency1": decode_address(topics[3]) if len(topics) > 3 else None,
            "fee": decode_uint(data, 0) if len(data) >= 64 else None,
            "tick_spacing": (
                _decode_int24(decode_uint(data, 1)) if len(data) >= 128 else None
            ),
            "hooks": decode_address(data, 2) if len(data) >= 192 else None,
            "sqrt_price_x96": decode_uint(data, 3) if len(data) >= 256 else None,
            "tick": (
                _decode_int24(decode_uint(data, 4)) if len(data) >= 320 else None
            ),
            "block_number": int(newest_row.get("blockNumber") or "0x0", 16),
        }
        return len(decoys), newest

    # ------------------------------------------------------------------
    # Blockscout REST — announcement channel
    # ------------------------------------------------------------------

    async def _blockscout_tx_pages(
        self, address: str, max_pages: int
    ) -> tuple[list[dict] | None, bool]:
        """All tx rows for *address*, following next_page_params, bounded.

        Returns ``(rows, truncated)``. ``rows`` keeps the existing "partial
        beats nothing, ``None`` only when nothing was read" contract.
        ``truncated`` is True ONLY when the ``max_pages`` bound was exhausted
        while the server was still handing back a ``next_page_params``
        cursor — i.e. more rows existed than this sweep was willing to fetch.
        Returning the partial rows silently (no flag, no log line) is the bug
        this return value exists to close: a caller cannot tell "that is
        everything" from "we stopped asking" without it, and the manager
        package needs exactly that distinction to render a degraded-feed
        flag.
        """
        url = f"{self._blockscout}/addresses/{address}/transactions"
        rows: list[dict] = []
        params: dict | None = None
        for _page in range(max_pages):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return rows or None, False  # partial > nothing; None only if empty
            rows.extend(body["items"])
            nxt = body.get("next_page_params")
            if not nxt:
                return rows, False
            params = nxt  # the server cursor, verbatim, as query params
        # The loop ran out of page budget while the last page still handed
        # back a cursor: there was more to fetch and we chose not to.
        logger.warning(
            "_blockscout_tx_pages: hit the %d-page bound for %s with more "
            "pages still available; returning %d partial rows",
            max_pages, address, len(rows),
        )
        return rows, True

    @staticmethod
    def _parse_channel_tx(row: dict) -> ChannelTx | None:
        ts = _parse_iso_ts(row.get("timestamp"))
        tx_hash = row.get("hash")
        from_addr = ((row.get("from") or {}).get("hash") or "").lower()
        # `or None`, exactly as _parse_dev_tx does it: WP0.4 types this field
        # `str | None`, and a contract creation has no `to`.  "" would be a
        # third state nobody declared — falsy like None, but a str, so a
        # downstream `to_addr is None` check stops matching in silence.
        to_addr = ((row.get("to") or {}).get("hash") or "").lower() or None
        if ts is None or not tx_hash or not from_addr:
            return None  # a malformed row is dropped, never zero-filled
        try:
            value_wei = int(row.get("value") or "0")
        except (TypeError, ValueError):
            return None
        return ChannelTx(
            ts=ts,
            # NOT `int(... or 0)`: nonce 0 is the channel's genesis "soon" post,
            # so a missing nonce coerced to 0 impersonates a real tx.
            nonce=_lenient_int(row.get("nonce")),
            from_addr=from_addr,
            to_addr=to_addr,
            value_wei=value_wei,
            input_hex=row.get("raw_input") or "0x",
            tx_hash=tx_hash,
            method=row.get("method"),
        )

    async def fetch_channel_txs(self) -> list[ChannelTx] | None:
        """Every tx touching the announce channel, newest first, RAW.

        No decoding, no classification here: the channel is permissionless
        and attacker-writable; interpretation is pure-function work in
        analytics/surf_signals.py where it is table-tested (PRD §6 rule 4).

        Sets ``self.channel_truncated`` — reset to ``False`` before the
        fetch, then to whatever ``_blockscout_tx_pages`` reports — so a
        caller can tell a bounded partial read apart from a genuinely
        complete one. It is never left stale from a previous refresh.
        """
        self.channel_truncated = False
        rows, truncated = await self._blockscout_tx_pages(
            A.ANNOUNCE, MAX_CHANNEL_PAGES
        )
        self.channel_truncated = truncated
        if rows is None:
            return None
        parsed = [self._parse_channel_tx(r) for r in rows]
        return [p for p in parsed if p is not None]

    # ------------------------------------------------------------------
    # Blockscout REST — dev-wallet activity feed
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_dev_kind(row: dict, to_addr: str | None,
                           created: str | None) -> str:
        """Map one tx onto the closed PRD §4 vocabulary.

        Keyed on the *destination address* wherever possible, because the
        address is what the dashboard trusts (CLAUDE.md: trust the address,
        never the name).  `method` only ever narrows a decision the address
        has already made.

        **The burn pipeline moved and this map did not** (final fix wave, I2).
        Measured on chain today: `burnAccruedImd()` goes to the LAUNCHPAD HOOK
        and `bridgeToBaseBurnReceiver()` now goes to `BURN_EXECUTOR_V2`, so
        both classified as `other` while only the *retired* V1 executor
        classified as `burn`. That silently disabled BURN's WATCH precursor,
        which `surf_manager._readings` builds from `kind == "burn"` rows: the
        whole burn pipeline could run with the rail saying nothing until the
        supply drop landed. Spec §6.4 and §9 both required otherwise. V1 stays
        for history -- its transactions are still on the pages we read -- so
        this is three burn destinations, not a replacement.
        """
        if created:
            return "deploy"
        if to_addr == A.NFPM.lower():
            return "lp"
        if to_addr == A.LAUNCHPAD_HOOK.lower():
            # burnAccruedImd(): the hook holds the accrued IMD and is where
            # the (permissionless) burn is kicked off. Read-only dashboard --
            # we render that it happened, we never offer to call it.
            return "burn"
        if to_addr in (A.BURN_EXECUTOR_V2.lower(), A.BURN_EXECUTOR_V1.lower()):
            # bridgeToBaseBurnReceiver(): it bridges in order to burn, and the
            # burn is what signal 6 and the supply sparkline care about. V2 is
            # the live executor; V1 is the superseded one whose history is
            # still on the dev wallets' pages.
            return "burn"
        if to_addr == A.RELAY_DEPOSITORY.lower():
            return "bridge"
        if to_addr == A.FWA_SPLITTER.lower() and row.get("method") == "claim":
            return "fwa claim"
        if row.get("method") is None and (row.get("raw_input") or "0x") == "0x":
            return "transfer"
        return "other"

    @classmethod
    def _parse_dev_tx(cls, row: dict, wallet_addr: str) -> DevTx | None:
        """Build one DevTx, or None if this row is not this wallet's own tx.

        The sender check is the address-poisoning defense (PRD §6.5) and it
        lives HERE, at construction, so that no later stage can be handed a
        row that should not exist.  A 1-gwei transfer from a lookalike address
        returns None and never becomes a widget row.
        """
        from_addr = ((row.get("from") or {}).get("hash") or "").lower()
        if from_addr != wallet_addr:
            return None                      # ← the whole poisoning defense

        ts = _parse_iso_ts(row.get("timestamp"))
        tx_hash = row.get("hash")
        if ts is None or not tx_hash:
            return None
        try:
            value_wei = int(row.get("value") or "0")
        except (TypeError, ValueError):
            return None

        to_addr = ((row.get("to") or {}).get("hash") or "").lower() or None
        created = row.get("created_contract") or None
        if isinstance(created, dict):
            created = (created.get("hash") or "").lower() or None
        elif isinstance(created, str):
            created = created.lower() or None

        counterparty = to_addr or created or ""
        return DevTx(
            tx_hash=tx_hash,
            ts=ts,
            wallet_label=_DEV_WALLET_LABELS[wallet_addr],
            from_addr=from_addr,
            to_addr=to_addr,
            counterparty=counterparty,
            counterparty_label=_label_for(counterparty),
            value_wei=value_wei,
            method=row.get("method"),
            kind=cls._classify_dev_kind(row, to_addr, created),
            created_contract=created,
        )

    async def fetch_dev_activity(self) -> list[DevTx] | None:
        """Recent txs of both dev wallets, merged newest-first, filtered and
        labelled.

        Inbound rows — including the six live address-poisoning dust transfers
        sitting in these two wallets' histories today — are dropped here, at
        the only place that still knows *whose page* a row came from.

        Sets ``self.activity_truncated`` — reset to ``False`` before the
        fetch, then ``True`` if EITHER wallet's page fetch hit
        ``MAX_ACTIVITY_PAGES`` while a cursor remained. A truncated page can
        drop a ``created_contract`` row off its end, and that row is the only
        signal the NEW DEPLOY detector watches for — silent truncation here
        would render as "nothing deployed" instead of "unknown".
        """
        self.activity_truncated = False
        (dev_rows, dev_truncated), (ops_rows, ops_truncated) = await asyncio.gather(
            self._blockscout_tx_pages(A.DEV_WALLET, MAX_ACTIVITY_PAGES),
            self._blockscout_tx_pages(A.OPS_WALLET, MAX_ACTIVITY_PAGES),
        )
        if dev_rows is None and ops_rows is None:
            return None
        self.activity_truncated = dev_truncated or ops_truncated
        if self.activity_truncated:
            which = ", ".join(
                label for label, trunc in
                (("dev", dev_truncated), ("ops", ops_truncated)) if trunc
            )
            logger.warning(
                "fetch_dev_activity: hit the %d-page bound for the %s "
                "wallet(s) with more pages still available",
                MAX_ACTIVITY_PAGES, which,
            )
        out: list[DevTx] = []
        for rows, wallet_addr in (
            (dev_rows, A.DEV_WALLET.lower()),
            (ops_rows, A.OPS_WALLET.lower()),
        ):
            for row in rows or []:
                parsed = self._parse_dev_tx(row, wallet_addr)
                if parsed is not None:
                    out.append(parsed)
        out.sort(key=lambda r: r.ts, reverse=True)
        return out

    # ------------------------------------------------------------------
    # Market REST — GeckoTerminal + DexScreener, cross-checked
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_imd_pair(body: Any, real_pool_id: str | None) -> dict | None:
        """The live v4 pair, matched by pool id -- never by liquidity size.

        Fix round 10a. 38 ETH/IMD v4 pools exist on mainnet and 37 are
        third-party decoys at other fee tiers (some squatting within one pip
        of the real 1% tier), and DexScreener returns them in the *same*
        response as the real pair -- "pick the deepest pair" (the old
        fallback this method used to have) is not merely imprecise, it is
        exploitable: anyone can fund a decoy past the real pool's liquidity
        and take over this panel. It already had: the drained v3 pair's
        ~$2,195 rendered while the live v4 pool held ~$805,927 -- a ~370x
        under-report of the dashboard's own subject.

        ``real_pool_id`` is the dev's own on-chain declaration
        (``LaunchpadHook.imdEthPoolId()``, via ``fetch_pool_v4()``) of which
        pool is his. DexScreener represents a v4 pool's ``pairAddress`` as
        that same bytes32 pool id -- v4 has no per-pool contract address the
        way v2/v3 do -- so matching the two directly is an exact identity
        check, not a heuristic.

        ``None`` -- never a guess -- when ``real_pool_id`` is not yet known
        (the launchpad sweep has not landed this process) or when no pair in
        the response matches it. Both are "cannot verify", and this repo's
        rule for "cannot verify" is ``None``, not "pick the closest-looking
        one".
        """
        if not real_pool_id:
            return None
        target = str(real_pool_id).lower()
        for p in (body or {}).get("pairs") or []:
            if str(p.get("pairAddress", "")).lower() == target:
                return p
        return None

    @staticmethod
    def _f(value: Any) -> float | None:
        """Lenient float parse: None/absent/garbage stays None, never 0."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def fetch_market(self, real_pool_id: str | None = None) -> MarketSnapshot | None:
        """IMD + FP market data, DexScreener primary, GeckoTerminal check.

        GeckoTerminal serves a STALE token name for IMD ("Vibe Coins") — its
        numbers are welcome, its strings are not (PRD §6 rule 3).

        ``real_pool_id`` (fix round 10a) is the live v4 pool id the caller
        already holds from a prior ``fetch_pool_v4()`` read (the manager
        threads it through from the launchpad slot) -- it costs no extra
        request here, it is only how ``_pick_imd_pair`` tells the real pair
        from a decoy. ``None`` when the caller does not have it yet (a cold
        cache before the launchpad sweep first lands): the v4 pair is then
        honestly unmatched rather than guessed, and every field this method
        would otherwise derive from it falls back through the existing
        Gecko path below, exactly as it already does on a total DexScreener
        outage.
        """
        dex_body, gecko_body, fp_body, eth_body = await asyncio.gather(
            self._get_json(f"{DEXSCREENER_TOKENS_API}/{A.IMD_TOKEN}"),
            self._get_json(GECKO_TOKEN_API.format(address=A.IMD_TOKEN.lower()),
                           params={"include": "top_pools"}),
            self._get_json(f"{DEXSCREENER_TOKENS_API}/{A.FP_TOKEN_BASE}"),
            self._get_json(COINGECKO_ETH_URL),
        )
        eth_usd = self._f(((eth_body or {}).get("ethereum") or {}).get("usd"))

        pair = self._pick_imd_pair(dex_body, real_pool_id)
        gecko_price = None
        gecko_pool = None
        if isinstance(gecko_body, dict):
            attrs = ((gecko_body.get("data") or {}).get("attributes") or {})
            gecko_price = self._f(attrs.get("price_usd"))
            included = gecko_body.get("included") or []
            gecko_pool = (included[0].get("attributes") or {}) if included else None
        if pair is None and gecko_price is None:
            return None  # both IMD sources dead — no snapshot, no zeros

        price_dex = self._f((pair or {}).get("priceUsd"))
        price = price_dex if price_dex is not None else gecko_price
        agree: bool | None = None
        if price_dex is not None and gecko_price is not None:
            mid = (price_dex + gecko_price) / 2
            agree = (
                abs(price_dex - gecko_price) / mid * 100
                <= PRICE_AGREE_TOLERANCE_PCT
                if mid > 0 else False
            )

        fp_pair = None
        if isinstance(fp_body, dict):
            fp_pair = max(
                fp_body.get("pairs") or [],
                key=lambda p: ((p.get("liquidity") or {}).get("usd") or 0.0),
                default=None,
            )

        liq = (pair or {}).get("liquidity") or {}
        change = (pair or {}).get("priceChange") or {}
        vol = (pair or {}).get("volume") or {}
        return MarketSnapshot(
            imd_price_usd=price,
            imd_price_usd_gecko=gecko_price,
            imd_change_24h_pct=(
                self._f(change.get("h24"))
                if pair is not None
                else self._f((gecko_pool or {}).get(
                    "price_change_percentage", {}).get("h24"))
            ),
            imd_vol_24h_usd=(
                self._f(vol.get("h24"))
                if pair is not None
                else self._f(((gecko_pool or {}).get("volume_usd") or {}).get("h24"))
            ),
            pool_liquidity_usd=(
                self._f(liq.get("usd"))
                if pair is not None
                else self._f((gecko_pool or {}).get("reserve_in_usd"))
            ),
            pool_imd=self._f(liq.get("base")),
            pool_weth=self._f(liq.get("quote")),
            fp_price_usd=self._f((fp_pair or {}).get("priceUsd")),
            fdv_usd=self._f((pair or {}).get("fdv")),
            # 0.0 would be a sentinel, and an ETH price of zero is not a number
            # anyone should see rendered as one.
            eth_usd=(eth_usd if (eth_usd or 0) > 0 else None),
            indexer_name=((pair or {}).get("baseToken") or {}).get("name"),
            indexer_symbol=((pair or {}).get("baseToken") or {}).get("symbol"),
            sources_agree=agree,
        )

    # ------------------------------------------------------------------
    # Blockscout REST + state RPC — IDMD collection stats
    # ------------------------------------------------------------------

    async def _count_transfers_24h(self) -> float | None:
        """IDMD transfers in the last 24 h — a RATE, never the lifetime count.

        Rows arrive newest-first, so the first row older than the cutoff ends
        the count: everything after it is outside the window. Two endings are
        complete answers — that older row, or a page the server did not
        continue. Running out of page budget while still inside the window is
        NOT: that answer is a lower bound, and a lower bound rendered as
        "transfers/day" is a wrong number, so it degrades to ``None``.
        """
        cutoff = self._now_fn() - _DAY_SECONDS
        url = f"{self._blockscout}/tokens/{A.IDMD_NFT}/transfers"
        params: dict | None = None
        count = 0
        for _page in range(MAX_NFT_TRANSFER_PAGES):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return None
            for row in body["items"]:
                ts = _parse_iso_ts(row.get("timestamp"))
                if ts is None:
                    continue          # undated row: skip it, never count it
                if ts < cutoff:
                    return float(count)          # crossed the window edge
                count += 1
            nxt = body.get("next_page_params")
            if not nxt:
                return float(count)              # no older rows exist
            params = nxt
        logger.warning(
            "transfers_24h: %s pages did not reach the 24 h edge — reporting "
            "unavailable rather than a lower bound", MAX_NFT_TRANSFER_PAGES,
        )
        return None

    async def _count_identities_written(self) -> int | None:
        """Distinct IDMD ids that ever received an identity hash (x of 2000).

        LIFETIME, not windowed. The only write today happened 2026-05-14,
        months before any ``eth_getLogs`` window this client opens, so a
        window count would render a confident 0/2000. Blockscout's address-log
        view is the keyless lifetime source; the registry exposes no
        written-hash getter.

        Counted over DISTINCT ``topics[1]``: ``IdentityHashUpdated`` fires
        again when a holder replaces their hash, and that is one identity
        written, not two. Topic0 is filtered explicitly — the registry emits
        other events, and "every log this contract ever emitted" is a
        different, larger number.
        """
        url = f"{self._blockscout}/addresses/{A.IDENTITY_REGISTRY}/logs"
        params: dict | None = None
        ids: set[str] = set()
        for _page in range(MAX_REGISTRY_LOG_PAGES):
            body = await self._get_json(url, params=params)
            if not isinstance(body, dict) or "items" not in body:
                return None
            for row in body["items"]:
                topics = row.get("topics") or []
                if not topics or str(topics[0] or "").lower() != \
                        A.TOPIC_IDENTITY_HASH_UPDATED.lower():
                    continue
                if len(topics) > 1 and topics[1]:
                    ids.add(str(topics[1]).lower())
            if not body.get("next_page_params"):
                return len(ids)       # 0 is a real answer: nobody has written
            params = body["next_page_params"]
        logger.warning("identities written: page bound hit, count truncated")
        return None                   # a lower bound is not a count

    async def fetch_nft_stats(self) -> NftStats | None:
        """IDMD collection stats. Floor is deliberately absent: no keyless
        source (OpenSea keyed/Cloudflare-gated) — the manager renders the
        explicit unavailable state, never a faked number.
        """
        token_body, counters_body, transfers_24h, written = await asyncio.gather(
            self._get_json(f"{self._blockscout}/tokens/{A.IDMD_NFT}"),
            self._get_json(f"{self._blockscout}/tokens/{A.IDMD_NFT}/counters"),
            self._count_transfers_24h(),
            self._count_identities_written(),
        )
        dev_holdings: int | None = None
        try:
            calldata = _SEL_BALANCE_OF + pad_left(strip0x(A.DEV_WALLET).lower(), 64)
            raw = await self._rpc_state(
                "eth_call", [{"to": A.IDMD_NFT, "data": calldata}, "latest"]
            )
            if raw and strip0x(raw):
                dev_holdings = decode_uint(raw, 0)
        except RuntimeError as exc:
            logger.warning("fetch_nft_stats balanceOf: %s", exc)

        def to_int(v: Any) -> int | None:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        holders = to_int((token_body or {}).get("holders_count"))
        supply = to_int((token_body or {}).get("total_supply"))
        transfers = to_int((counters_body or {}).get("transfers_count"))
        if all(v is None for v in (holders, supply, transfers, dev_holdings,
                                   transfers_24h, written)):
            return None
        return NftStats(
            holders=holders,
            total_supply=supply,
            transfers_total=transfers,     # lifetime, 7,411
            transfers_24h=transfers_24h,   # the rate — a different number
            dev_holdings=dev_holdings,
            written=written,               # feeds BOTH hero and NFT panel
            # floor_eth stays at its pinned None: no keyless source exists.
        )

    # ------------------------------------------------------------------
    # State RPC — transaction provenance (the v4-launch corroboration)
    # ------------------------------------------------------------------

    async def fetch_tx_senders(self, tx_hashes: Sequence[str]) -> dict[str, str]:
        """``{tx_hash: signer}``, both lowercased, for the hashes we could read.

        Uniswap v4 ``initialize()`` is permissionless: an ``Initialize`` log
        naming IMD with a non-zero hook costs a stranger one transaction's gas,
        and the event payload says nothing about who sent it. The signature on
        the enclosing transaction is the one part of that a stranger cannot
        forge, so this read is what lets the manager tell the dev's launch from
        an impostor's. Nothing here decides what the answer *means*.

        A hash we could not read is **absent from the result** — never mapped to
        ``""``, to the zero address, or to any other placeholder. "We do not
        know who sent it" and "a stranger sent it" are opposite conclusions for
        the caller, and collapsing them turns an RPC outage into a confident
        verdict about the single event this dashboard exists to catch.

        One batched POST on the state pool for the whole (de-duplicated) list,
        and **no request at all** for an empty one: the everyday answer is zero
        hooked pools, and the everyday cost must be zero.
        """
        wanted: list[str] = []
        for raw in tx_hashes or ():
            tx = str(raw or "").strip().lower()
            if tx and tx not in wanted:
                wanted.append(tx)
        if not wanted:
            return {}
        try:
            results = await self._rpc_state_batch(
                [("eth_getTransactionByHash", [tx]) for tx in wanted]
            )
        except RuntimeError as exc:      # malformed-request short-circuit
            logger.warning("fetch_tx_senders: %s", exc)
            return {}
        if results is None:
            return {}
        out: dict[str, str] = {}
        for tx, result in zip(wanted, results):
            if not isinstance(result, dict):
                continue                  # a failed entry stays absent, never ""
            sender = str(result.get("from") or "").strip().lower()
            if sender.startswith("0x") and len(sender) == 42:
                out[tx] = sender
        return out

    # ------------------------------------------------------------------
    # Logs RPC — the recent-window sweep for signals 2/3/5 + NFT sales
    # ------------------------------------------------------------------

    async def _get_logs_shrinking(
        self, base_filter: dict, from_block: int, to_block: int, *, group: str
    ) -> list[dict] | None:
        """eth_getLogs with bounded window-halving on range errors.

        A provider's suggested range is NEVER adopted: one of them decrements
        a single block per round trip, which livelocks a verbatim follower.
        Halving our own window converges in <= _LOG_MAX_SHRINKS steps or
        fails honestly.

        **It shrinks toward the HEAD, and a shrunk read returns as a
        success.** ``toBlock`` stays pinned while ``fromBlock`` walks
        forward, so a range-capped endpoint yields the newest slice of the
        ask and the older blocks are silently dropped -- the caller cannot
        tell that from a complete answer. That is deliberate and harmless
        for the recent-window callers this exists for, which only ever want
        the newest ``LOG_WINDOW_BLOCKS`` and treat a short window as a
        smaller *recent*. It is **wrong for any caller reading history**:
        the blocks it discards are the oldest ones, which is exactly what
        such a caller is there for. Use ``_get_logs_paged`` instead -- it
        tiles the range and fails rather than skipping.

        *group* is a label only — one of the ``LogWindow`` field names — used
        solely so a warning can say WHICH filter died. It does not affect the
        request; the caller still owns turning a ``None`` return into
        ``self.log_group_failed[group] = True``.
        """
        window = to_block - from_block
        for _shrink in range(_LOG_MAX_SHRINKS + 1):
            flt = dict(base_filter)
            flt["fromBlock"] = hex(to_block - window)
            flt["toBlock"] = hex(to_block)
            try:
                result = await self._rpc_logs("eth_getLogs", [flt])
                return result if isinstance(result, list) else None
            except _LogRangeError:
                window = max(window // 2, _LOG_MIN_WINDOW)
                if window == _LOG_MIN_WINDOW and _shrink >= 1:
                    break
            except RuntimeError as exc:
                logger.warning("getLogs failed for %s: %s", group, exc)
                return None
        # Every attempt either range-errored or hit the shrink floor without
        # a shrink left to spend: honest failure, never a livelock.
        logger.warning(
            "getLogs shrink exhausted for %s: still range-limited at a "
            "%d-block window after %d attempt(s)",
            group, window, _LOG_MAX_SHRINKS + 1,
        )
        return None

    async def _get_logs_paged(
        self, base_filter: dict, from_block: int, to_block: int, *, group: str
    ) -> list[dict] | None:
        """eth_getLogs over an arbitrarily wide range, in complete pages.

        The reader for anything that sweeps *history*.
        ``_get_logs_shrinking`` cannot do this job: it answers a too-wide ask
        by pulling ``fromBlock`` toward the head and returning the short
        result as a success, so a range-capped endpoint hands back the newest
        slice and drops the oldest blocks with no trace. For the launchpad
        that is not a degraded read, it is a *silent* one -- and the cursor
        then advances past the blocks that were never read, which turns a
        transient provider limit into permanent data loss. Measured on the
        committed 146-launch fixture with a 10,000-block cap: the shrinking
        reader returned 2 launches and 45 swaps as a clean success.

        So the range is tiled into ``LOG_WINDOW_BLOCKS``-sized pages (2,400 --
        this client's working window everywhere else) and **any page that
        cannot be read fails the whole call**, ``None``. A range error halves
        the page size and retries *the same start*: the cursor never moves
        over a block whose logs were not seen. Bounded by ``_LOG_MAX_SHRINKS``
        halvings and the ``_LOG_MIN_WINDOW`` floor, then honest failure --
        never a livelock, and never a suggested range followed verbatim.

        Cost is one request per 2,400 blocks: ~15 per event type for today's
        ~34k-block cold sweep, 3 for the 7,200-block day re-read. An empty
        page is data; ``[]`` overall means "swept, and nothing happened".
        """
        if from_block > to_block:
            return []
        rows: list[dict] = []
        page = LOG_WINDOW_BLOCKS
        shrinks = 0
        start = from_block
        while start <= to_block:
            end = min(start + page - 1, to_block)
            flt = dict(base_filter)
            flt["fromBlock"] = hex(start)
            flt["toBlock"] = hex(end)
            try:
                result = await self._rpc_logs("eth_getLogs", [flt])
            except _LogRangeError as exc:
                if page <= _LOG_MIN_WINDOW or shrinks >= _LOG_MAX_SHRINKS:
                    logger.warning(
                        "getLogs paged: %s still range-limited at a %d-block "
                        "page after %d halving(s) -- failing rather than "
                        "skipping blocks %d..%d: %s",
                        group, page, shrinks, start, end, exc,
                    )
                    return None
                page = max(page // 2, _LOG_MIN_WINDOW)
                shrinks += 1
                continue          # the SAME start -- never skip forward
            except RuntimeError as exc:
                logger.warning("getLogs paged failed for %s: %s", group, exc)
                return None
            if not isinstance(result, list):
                logger.warning("getLogs paged: %s returned a non-list", group)
                return None
            rows.extend(result)
            start = end + 1
        return rows

    async def fetch_recent_logs(self) -> LogWindow | None:
        """The recent-window log sweep for signals 2/3/5 and NFT sales.

        LOGS POOL ONLY. Four filter groups; an *empty* group is data (nothing
        happened); a *failed* group is ``None``; a dead head-read is a dead
        window. Raw log dicts pass through — decoding is downstream.

        Sets ``self.log_group_failed`` — reset to all ``False`` at the START
        of every call, then per-group ``True`` for whichever of the four
        ``LogWindow`` fields could not be read. ``LogWindow`` itself cannot
        carry that distinction (its tuple fields default to ``()``, and ``()``
        is a legitimate "nothing happened" answer), so this dict is the
        out-of-band channel the model's own docstring calls for.
        """
        self.log_group_failed = {
            "bridge_mints": False,
            "identity_updates": False,
            "v4_initializes": False,
            "seaport_sales": False,
        }
        try:
            head_hex = await self._rpc_logs("eth_blockNumber", [])
            head = int(head_hex, 16)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.warning("fetch_recent_logs head: %s", exc)
            # No filter was even attempted: every group is exactly as
            # unread as the head itself, so every group is failed too.
            self.log_group_failed = {k: True for k in self.log_group_failed}
            return None
        from_block = head - self._log_window_blocks

        bridge = await self._get_logs_shrinking(
            {
                "address": A.IMD_TOKEN,
                "topics": [
                    A.TOPIC_TRANSFER,
                    _ZERO_TOPIC,
                    [_addr_topic(A.DEV_WALLET), _addr_topic(A.OPS_WALLET)],
                ],
            },
            from_block, head, group="bridge_mints",
        )
        self.log_group_failed["bridge_mints"] = bridge is None
        identity = await self._get_logs_shrinking(
            {"address": A.IDENTITY_REGISTRY,
             "topics": [A.TOPIC_IDENTITY_HASH_UPDATED]},
            from_block, head, group="identity_updates",
        )
        self.log_group_failed["identity_updates"] = identity is None
        # v4 Initialize: IMD may be currency0 (topic2) or currency1 (topic3).
        init0 = await self._get_logs_shrinking(
            {"address": A.POOL_MANAGER_V4,
             "topics": [A.TOPIC_V4_INITIALIZE, None, _addr_topic(A.IMD_TOKEN)]},
            from_block, head, group="v4_initializes[currency0]",
        )
        init1 = await self._get_logs_shrinking(
            {"address": A.POOL_MANAGER_V4,
             "topics": [A.TOPIC_V4_INITIALIZE, None, None,
                        _addr_topic(A.IMD_TOKEN)]},
            from_block, head, group="v4_initializes[currency1]",
        )
        v4_inits: list[dict] | None
        if init0 is None and init1 is None:
            v4_inits = None
        else:
            v4_inits = [*(init0 or []), *(init1 or [])]
        # Failed if EITHER side failed: a row missing from the failed side is
        # invisible even when the other side's query came back clean.
        self.log_group_failed["v4_initializes"] = init0 is None or init1 is None
        seaport_raw = await self._get_logs_shrinking(
            {"address": _SEAPORT,
             "topics": [A.TOPIC_SEAPORT_ORDER_FULFILLED]},
            from_block, head, group="seaport_sales",
        )
        self.log_group_failed["seaport_sales"] = seaport_raw is None
        seaport: list[dict] | None = None
        if seaport_raw is not None:
            # Cheap pre-filter: keep only fulfillments whose payload mentions
            # the IDMD contract. Exact consideration decoding is downstream.
            idmd_word = strip0x(A.IDMD_NFT).lower()
            seaport = [
                log for log in seaport_raw
                if idmd_word in str(log.get("data", "")).lower()
            ]

        if bridge is None and identity is None and v4_inits is None \
                and seaport is None:
            return None
        # Raw rows, verbatim from the endpoint.  WP4 decodes them; this module
        # must not normalise, prune or re-key them.
        return LogWindow(
            from_block=from_block,
            to_block=head,
            bridge_mints=tuple(bridge or ()),
            identity_updates=tuple(identity or ()),
            v4_initializes=tuple(v4_inits or ()),
            seaport_sales=tuple(seaport or ()),
        )


__all__ = [
    "SurfClient",
    "STATE_RPC_PRIMARY",
    "STATE_RPC_FALLBACKS",
    "LOG_RPCS",
    "BLOCKSCOUT_BASE",
    "DEXSCREENER_TOKENS_API",
    "GECKO_TOKEN_API",
    "COINGECKO_ETH_URL",
    "LOG_WINDOW_BLOCKS",
    "LAUNCHPAD_DAY_BLOCKS",
    "LAUNCHPAD_RENDER_LIMIT",
    "V4_INITIALIZE_SEARCH_FROM_BLOCK",
    "MAX_CHANNEL_PAGES",
    "MAX_ACTIVITY_PAGES",
    "MAX_NFT_TRANSFER_PAGES",
    "MAX_REGISTRY_LOG_PAGES",
    "PRICE_AGREE_TOLERANCE_PCT",
    "MULTICALL3",
]
