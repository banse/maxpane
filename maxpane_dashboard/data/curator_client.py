"""Keyless, read-only fetch layer for the curator dashboard — THE LIST.

Subject: ``WhitelistCurator`` at :data:`curator_addresses.CURATOR` on Ethereum
mainnet.  Nothing here signs, sends, or encodes a state-changing call;
``deposit()``, ``settle()`` and ``rescue()`` are read *about*, never called.  No
source needs a key of any kind, and none may be added.

TWO ENDPOINT POOLS, NEVER CROSSED
    ``ethereum-rpc.publicnode.com`` serves **state** — it is the strongest
    keyless batcher there is, and the whole fast tier is one JSON-RPC batch
    array of plain ``eth_call``s — but it **refuses archive ``eth_getLogs``**.
    Logs therefore go to ``gateway.tenderly.co/public/mainnet`` with
    ``eth.drpc.org`` behind it, and publicnode is deliberately absent from that
    list (``test_publicnode_is_absent_from_the_logs_pool``).  A banned-host
    frozenset rejects the dead and the newly-keyed at construction.

A REAL ``User-Agent``, ON EVERY REQUEST
    publicnode answers ``403`` to python-urllib's default UA and answered the
    byte-identical batch from ``curl`` (``captures/README.md``).  The header is
    set per *request*, not only on the client this module builds: a caller may
    inject an ``httpx.AsyncClient`` of their own (every test does), and a
    constructor-level header would be absent from exactly those requests.

MESSAGE TEXT, NOT CODE
    Providers reuse ``-32602`` and ``-32005`` for unrelated meanings — drpc's
    "Can't route your request" arrives wearing a code other providers spend on
    a malformed request.  Classification is on the message; a real malformed
    request short-circuits the whole chain, because it fails identically
    everywhere and rotating on our own bug triples the request count and hides
    it.  A provider's *suggested* retry range is **never** adopted: one of them
    decrements a single block per round trip and livelocks a verbatim follower.
    The window halves instead, boundedly.

A FAILED READ IS ``None``, NEVER ``0`` — AND THIS CONTRACT HAS THREE REAL ZEROS
    Every field degrades independently: a batch where three views answered and
    one errored returns the three, with that one field ``None``.  The three
    zeros that are *answers*, not failures, and must survive untouched:

    * ``currentHourTotal()`` is ``0`` at every hour boundary, for as long as it
      takes the next deposit to land.
    * ``ethNeededThisHour()`` is ``0`` through the whole grace period and again
      whenever a judged hour is already safe.
    * ``creditedDelta`` is ``0`` for a deposit above the credit cap — which
      still counts *fully* toward that hour's survival.

    The mirror of the rule applies to the log sweep: ``()`` is ambiguous on a
    frozen tuple, so a per-group failure travels out-of-band in
    :attr:`CuratorClient.log_group_failed`, and a sweep where *every* group
    failed returns ``None`` rather than a hollow :class:`LogSweep`.

THE BALANCE IS NOT A BALANCE
    Every wei of a deposit is refunded inside the same transaction, so
    ``eth_getBalance`` on this contract is **always forced ETH** — selfdestruct
    or a builder naming it as fee recipient — and never a deposit.  It is
    returned by :meth:`CuratorClient.fetch_balance` on its own, so nothing can
    mistake it for a volume, a TVL or a hero total.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data.evm_abi import (
    decode_address,
    decode_uint,
    encode_address,
    strip0x,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
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

#: Logs pool.  publicnode is deliberately absent: it refuses archive
#: ``eth_getLogs``, so including it would spend a round trip and a retry on
#: every sweep before rotating to an endpoint that can answer.
LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",  # hard 10k-block page cap; our page sits under it
]

BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"

#: Hosts that are dead, newly keyed, or useless — refused at construction so a
#: mistake is a ``ValueError`` at wiring time rather than a dashboard that
#: quietly renders unavailable for a session.
_BANNED_RPC_HOSTS = frozenset(
    {
        "eth.llamarpc.com",     # HTTP 521, origin down
        "rpc.ankr.com",         # now requires a key
        "cloudflare-eth.com",   # -32046 on Ethereum
        "api.reservoir.tools",  # sunset, DNS gone
    }
)

#: The same rule for whole domains: every subdomain of these is keyed, and a
#: keyed endpoint in a keyless app is a bug, not a fallback.
_BANNED_HOST_SUFFIXES = ("alchemy.com", "infura.io", "etherscan.io")

#: publicnode 403s a library-default UA.  Sent on **every** request.
USER_AGENT = "maxpane-dashboard/curator (keyless read-only onchain viewer)"

_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": USER_AGENT,
}

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
#: publicnode 429s under unpaced bursts; measured in ``fwa_client``.
_INTER_CALL_DELAY = 0.12

#: One ``eth_getLogs`` page.  Under drpc's hard 10k cap, and the whole curator
#: history is a few hundred blocks today — this exists so the backfill still
#: terminates honestly if the game runs for weeks.
LOG_PAGE_BLOCKS = 9000
_LOG_MIN_WINDOW = 300
_LOG_MAX_SHRINKS = 3

#: The rendered activity window, not the whole history: block timestamps are a
#: **fallback** (every captured log row already carries ``blockTimestamp``), so
#: this batch must stay small enough to be free when it is needed at all.
MAX_TIMESTAMP_BLOCKS = 40

#: Blockscout log pages to follow in one cross-check.  Eight covered the whole
#: history at capture (376 rows over 8 pages).
MAX_BLOCKSCOUT_PAGES = 8

#: ``LogSweep``'s group fields, and the keys of :attr:`log_group_failed`.
LOG_GROUPS: tuple[str, ...] = (
    "deposits",
    "first_deposits",
    "hour_saved",
    "settled",
    "rescued",
    "launched",
)

#: topic0 -> the ``LogSweep`` field a row belongs in.  Lowercase keys: an
#: endpoint may serve either case and the dashboard must not care.
_TOPIC_TO_GROUP: dict[str, str] = {
    A.TOPIC_DEPOSITED.lower(): "deposits",
    A.TOPIC_FIRST_DEPOSIT.lower(): "first_deposits",
    A.TOPIC_HOUR_SAVED.lower(): "hour_saved",
    A.TOPIC_SETTLED.lower(): "settled",
    A.TOPIC_RESCUED.lower(): "rescued",
    A.TOPIC_LAUNCHED.lower(): "launched",
}

_GROUP_TO_TOPIC: dict[str, str] = {g: t for t, g in _TOPIC_TO_GROUP.items()}


# ---------------------------------------------------------------------------
# Error classification — message text first
# ---------------------------------------------------------------------------

#: "This endpoint can't", as opposed to "this request is bad".  Mirrored from
#: ``surf_client`` / ``ttt_client`` and extended with drpc's routing failure:
#: that message arrives with ``-32602``, which other providers spend on a
#: genuinely malformed request, so a code-first classifier bins a healthy query.
_ENDPOINT_LIMITATION_PATTERNS = (
    "limited to", "block range", "range is too large", "ranges over",
    "exceeds", "too large", "too many", "archive", "unauthorized",
    "authenticate", "free plan", "upgrade", "not supported", "unsupported",
    "capacity", "rate limit", "timeout", "try again", "cannot fulfill",
    # drpc, observed live: "Can't route your request. Try again later."
    "can't route", "cannot route", "route your request",
)

#: The shrinkable class only: "your block range is too wide".
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
    """True only for the shrinkable "block range is too wide" class."""
    if not isinstance(err, dict):
        return False
    message = str(err.get("message") or "").lower()
    return any(frag in message for frag in _RANGE_LIMITATION_PATTERNS)


class _LogRangeError(RuntimeError):
    """``eth_getLogs`` failed because the requested window is too wide."""


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def _hex_to_int(value: Any) -> int | None:
    """A ``0x``-prefixed quantity, or ``None`` — **never** ``0`` on failure."""
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def decode_view(sel_name: str, raw: Any) -> tuple[Any, ...] | None:
    """Decode one view's return data into its declared words, or ``None``.

    Driven by :data:`curator_addresses.VIEW_RETURN_TYPES`, which is the
    machine-readable decode instruction for all 28 selectors.  Three of them are
    not one word — ``stats()`` is three, ``lastActiveHour()`` and
    ``firstHourOf()`` are two — and a scalar decode of any of those is a silent
    bug: reading only word 0 of ``firstHourOf()`` throws away ``hasJoined``,
    which is the single bit that separates "deposited in the launch hour" from
    "never deposited at all".

    ``None`` for a missing, non-string or **short** payload.  Short matters: a
    reverted ``eth_call`` comes back as ``0x``, and decoding that as zeros would
    manufacture a plausible reading out of a failure.
    """
    types = A.VIEW_RETURN_TYPES.get(sel_name)
    if types is None:  # pragma: no cover — WP0 pins all 28
        logger.error("decode_view: %s has no declared return type", sel_name)
        return None
    if not isinstance(raw, str):
        return None
    body = strip0x(raw.strip())
    if len(body) < 64 * len(types):
        return None
    out: list[Any] = []
    for idx, sol_type in enumerate(types):
        if sol_type == "bool":
            # False and None are different answers; only this branch may
            # produce False.
            out.append(decode_uint(body, idx) != 0)
        elif sol_type == "address":
            out.append(decode_address(body, idx))
        elif sol_type.startswith("uint"):
            # Every uintN arrives left-padded in one word; the width matters
            # only to whoever reasons about overflow.
            out.append(decode_uint(body, idx))
        else:  # pragma: no cover — WP0 asserts only these three spellings
            logger.error("decode_view: %s declares unknown type %r",
                         sel_name, sol_type)
            return None
    return tuple(out)


def _is_address(value: Any) -> bool:
    """A ``0x``-prefixed 20-byte hex address, and nothing else."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) != 42 or not text.startswith("0x"):
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


class CuratorClient(OwnedHttpClient):
    """Async, keyless, read-only client for every curator data source."""

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
        log_page_blocks: int = LOG_PAGE_BLOCKS,
    ) -> None:
        self._state_rpcs = [state_rpc, *(state_fallbacks or STATE_RPC_FALLBACKS)]
        self._log_rpcs = list(log_rpcs or LOG_RPCS)
        for url in (*self._state_rpcs, *self._log_rpcs):
            host = (urlparse(url).hostname or "").lower()
            if host in _BANNED_RPC_HOSTS or host.endswith(_BANNED_HOST_SUFFIXES):
                raise ValueError(
                    f"{url} is a banned RPC host (dead, keyed or useless) — "
                    "see curator_client._BANNED_RPC_HOSTS"
                )
        self._blockscout = blockscout_base.rstrip("/")
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers=dict(_REQUEST_HEADERS),
        )
        self._owns_client = http_client is None
        self._inter_call_delay = inter_call_delay
        self._backoff_seconds = backoff_seconds
        self._now_fn = now_fn
        self._log_page_blocks = log_page_blocks
        self._request_id = 0
        self._last_rpc_at: float = 0.0

        # -- The degradation surface ------------------------------------
        # Six flags, every one of them "true RIGHT NOW" and never "true once,
        # ever": each is reset at the START of the call it describes, so a
        # recovered endpoint clears it without anybody having to remember to.
        # The manager folds them into the frozen ``degraded`` vocabulary
        # (``state`` / ``logs`` / ``wallet``); this module renders nothing.

        #: ``fetch_state()`` failed in whole (returned ``None``) or in part (a
        #: batch entry errored, so one field is ``None`` while the rest are
        #: real).  Partial counts: a missing ``earlyMultiplierBps`` is a hole
        #: the reader is entitled to see marked.
        self.state_failed: bool = False
        #: ``fetch_config()``, same contract.  Separate from ``state_failed``
        #: because the ``once`` tier is read on a different schedule; the
        #: manager folds it into the ``state`` group.
        self.config_failed: bool = False
        #: ``fetch_logs()`` could not read a single group.
        self.logs_failed: bool = False
        #: ``fetch_wallet()`` failed in whole or in part.
        self.wallet_failed: bool = False
        #: ``fetch_blockscout_logs()`` hit its page bound while the server was
        #: still handing back a cursor — more rows existed than we fetched.
        self.blockscout_truncated: bool = False
        #: Per-group failure for the most recent ``fetch_logs()``, keyed by the
        #: exact :class:`LogSweep` field each group feeds.  This is the
        #: out-of-band channel the model's own docstring calls for: a frozen
        #: tuple cannot hold ``None``, so ``()`` means "read, nothing matched"
        #: **or** "this filter failed", and only this dict tells them apart.
        #: Without it a dead ``Settled`` filter reads as "the game is alive".
        self.log_group_failed: dict[str, bool] = {g: False for g in LOG_GROUPS}

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
        """One paced POST, with the real UA merged onto whatever client we hold.

        The headers go here rather than only on the client built in
        ``__init__`` because an injected client carries its owner's headers,
        and publicnode's 403 does not care whose client it was.
        """
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)
        return await self._client.post(
            url, json=payload, headers=dict(_REQUEST_HEADERS)
        )

    async def _rpc_state(self, method: str, params: list) -> Any:
        """One JSON-RPC call on the STATE pool, retry + rotation.

        This pool issues only plain getters, so the cheapest recovery from any
        *endpoint* problem is the next endpoint.  A malformed-request error is
        OUR bug: it fails identically everywhere, so it short-circuits.
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
                        break  # rotate; do not retry a dead host
                    resp.raise_for_status()
                    body = resp.json()
                    if isinstance(body, dict) and body.get("error"):
                        err = body["error"]
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"{url}: {err}")
                            break  # rotate
                        raise RuntimeError(f"malformed request: {err}")
                    return body.get("result") if isinstance(body, dict) else None
                except (httpx.HTTPError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(self._backoff_seconds[attempt])
        raise RuntimeError(f"all state endpoints failed: {last_err}")


__all__ = [
    "CuratorClient",
    "STATE_RPC_PRIMARY",
    "STATE_RPC_FALLBACKS",
    "LOG_RPCS",
    "BLOCKSCOUT_BASE",
    "USER_AGENT",
    "LOG_PAGE_BLOCKS",
    "LOG_GROUPS",
    "MAX_TIMESTAMP_BLOCKS",
    "MAX_BLOCKSCOUT_PAGES",
    "decode_view",
]
