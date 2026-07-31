"""The transport atoms every client agrees on -- and nothing more (MEDI-17).

MEDI-17 proposed extracting "the hardened ttt/talismans ``_rpc``" into one
module and routing all five RPC clients through it. Three weeks of live
hardening later that is the wrong fix, and the reason is worth writing down
so the next reviewer does not re-propose it.

The five ``_rpc`` bodies are not five copies of one thing. They implement
**five different, individually tested error policies**, each of which encodes
a fact about a specific chain or a specific provider:

===============  ==========================================================
client           what its ``_rpc`` uniquely knows
===============  ==========================================================
``talismans``    Classifies every failure into a *kind* and raises a typed
                 ``TalismansRpcError``. Its ``eth_getLogs`` pager reads
                 ``.kind`` and ``.suggested_to`` to shrink its window, so
                 the classification is load-bearing data, not logging. It
                 also classifies the JSON-RPC ``error`` body **before**
                 ``raise_for_status``, because drpc's shrinkable range cap
                 arrives wearing an HTTP 400 and status-first handling
                 demoted the one recoverable error in the set to an opaque
                 transport failure.
``ttt``          Boolean ``_looks_like_endpoint_limitation`` over a
                 20-fragment table, plus a ``_MALFORMED_REQUEST_CODES``
                 escape hatch that *does* short-circuit the chain. Two
                 endpoint pools (state vs logs) because publicnode batches
                 ``eth_call`` beautifully and 403s on archive
                 ``eth_getLogs``.
``fwa``          No classification at all: **any** ``error`` body rotates.
                 Correct for a state-only client with no log scans, where
                 the cheapest recovery from anything is the next endpoint.
                 Also rejects a batch response to a single call -- a
                 Multicall3-specific failure mode.
``cattown``      Deliberately raises on a non-limitation error instead of
                 rotating: a reverted ``eth_call`` is the *contract's*
                 answer, not the endpoint's fault, and rotating on it would
                 triple the request count for no gain. Its retry ladder
                 lives in a separate ``_post_with_retry`` returning a
                 ``Response``, because ``get_recent_catches`` needs the
                 response object.
``ocm``          Single endpoint, no rotation, a flat pre-call sleep rather
                 than monotonic pacing. Ethereum mainnet + one env-var
                 override.
===============  ==========================================================

A shared ``_rpc`` covering that table would be a five-way policy switch --
more code than the five bodies, with every client's behaviour reachable from
every other client's bug. Worse, unifying them *is* a behaviour change, and
each of those behaviours is pinned by tests that were written when the
behaviour was a live outage.

What the five genuinely do agree on is below: the JSON-RPC envelope, the set
of HTTP statuses that mean "this host, not this request", the monotonic
pacing arithmetic, and the "I own my httpx client" lifecycle. Those are
shared here. The policy stays where the knowledge is.

``OwnedHttpClient`` reaches slightly wider than JSON-RPC -- all eight
``*_client.py`` modules had the same three lifecycle methods, including the
pure-HTTP ones (``base``, ``dota``, ``frenpet``) -- so it lives here rather
than in a ninth module of its own.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Self

import httpx

#: HTTP statuses that mean "*this endpoint* is broken, gone, or blocking us",
#: as opposed to "try again in a moment". Rotate to the next endpoint instead
#: of burning the retry ladder on a host that will not answer.
#:
#: The 52x block is Cloudflare's: those are ``>= 500`` but emphatically not
#: transient, which is why they must be tested for *before* the generic 5xx
#: retry branch. 401/402/403/451 are the shapes a keyless endpoint takes when
#: it quietly starts requiring a key or geo-blocks the caller -- the exact
#: failure that used to brick a whole dashboard for a session.
#:
#: Byte-identical in ``talismans_client``, ``fwa_client``, ``cattown_client``
#: and (as a function-local set) ``ttt_client`` before MEDI-17.
ENDPOINT_DEAD_CODES: frozenset[int] = frozenset(
    {401, 402, 403, 451, 521, 522, 523, 524, 525, 526}
)


def jsonrpc_payload(request_id: int, method: str, params: list) -> dict[str, Any]:
    """Build one JSON-RPC 2.0 request envelope.

    The one part of the transport that is protocol, not policy -- and so the
    one part that was identical in all five RPC clients.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


async def pace(last_call_at: float, min_interval: float) -> float:
    """Sleep until *min_interval* has passed since *last_call_at*.

    Returns the new "last call" timestamp, which the caller stores::

        self._last_rpc_at = await pace(self._last_rpc_at, _INTER_CALL_DELAY)

    Monotonic and self-correcting: a call that was already slow pays no extra
    delay, so pacing costs nothing on a healthy endpoint and only bites on a
    burst. Unpaced bursts are what earn the 429s from keyless hosts.

    A ``min_interval`` of zero (or a first-ever call, ``last_call_at == 0``)
    never sleeps but still advances the clock -- matching what the four
    hand-rolled copies did.
    """
    if min_interval > 0 and last_call_at > 0:
        elapsed = time.monotonic() - last_call_at
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
    return time.monotonic()


class OwnedHttpClient:
    """Lifecycle for a client that may or may not own its ``httpx`` client.

    Mixed into all eight ``*_client.py`` classes, each of which set the same
    two attributes in ``__init__`` and then repeated the same three methods::

        self._client = http_client or httpx.AsyncClient(...)
        self._owns_client = http_client is None

    An injected client belongs to the caller (the tests inject one built on a
    mock transport, so no socket is ever opened) and must **not** be closed
    here; one we built ourselves must be.
    """

    #: Annotations only -- the mixin creates no attributes. Subclasses assign
    #: both in ``__init__``.
    _client: httpx.AsyncClient
    _owns_client: bool

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


__all__ = [
    "ENDPOINT_DEAD_CODES",
    "OwnedHttpClient",
    "jsonrpc_payload",
    "pace",
]
