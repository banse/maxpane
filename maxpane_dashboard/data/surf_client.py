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
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.evm_abi import (
    decode_address,
    decode_aggregate3_result,
    decode_string,
    decode_uint,
    encode_aggregate3,
    encode_uint,
    strip0x,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)
from maxpane_dashboard.data.surf_models import ChainState, NonceSet

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
        """The fast-tier eth_call round: one aggregate3 over eight views.

        Sub-call order is positional and mirrored in the decode below.
        Every sub-call is ``allowFailure=True``: a single reverted view
        degrades one field to ``None``, never the round.

        The eighth sub-call is Multicall3's own ``getBlockNumber()``, which is
        how ``ChainState.block_number`` gets a producer without a second round
        trip. Reading the height inside the same ``eth_call`` also makes it
        *the* height of this state: fetch it separately and a reorg or a
        rotated endpoint can hand back a block the other seven never saw.
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
    "MAX_CHANNEL_PAGES",
    "MAX_ACTIVITY_PAGES",
    "MAX_NFT_TRANSFER_PAGES",
    "MAX_REGISTRY_LOG_PAGES",
    "PRICE_AGREE_TOLERANCE_PCT",
    "MULTICALL3",
]
