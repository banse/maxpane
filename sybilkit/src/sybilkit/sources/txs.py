"""Tier B: transaction fingerprints, batched.

``eth_getTransactionByHash`` over the state pool.  Two measured facts shape
this module and neither is optional:

* ``ethereum-rpc.publicnode.com`` is the strongest keyless batcher there is and
  it **403s a library-default User-Agent**.  The header goes on every request.
* It throttles batch arrays much above ~40 calls, and ``eth.drpc.org`` answers
  a batched ``getTransactionByHash`` with a flat HTTP 500 — so the pool rotates
  on status as well as on message.

The fingerprint is the *uniformity across a group*, never the values: a farm
collapses to one priority fee and one gas limit, while 60 control wallets
showed 27 distinct priority fees and 15 gas limits.  Which is why a missing
field must stay :data:`None` — a legacy type-0 transaction has no
``maxPriorityFeePerGas`` **at all**, and a detector that read the absence as a
shared zero would see a collapsed axis that does not exist.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable

from ..model import Tx
from . import (
    DEFAULT_CONFIG,
    AllEndpointsFailed,
    MalformedRequest,
    SourceConfig,
    _Session,
    chunks,
    hex_to_int,
    rpc_batch,
)


def decode_tx(payload: Any) -> Tx | None:
    """One ``eth_getTransactionByHash`` result → :class:`Tx`, or ``None``.

    Every field is read independently and a missing one stays ``None``: they
    fail independently on the wire and they mean different things absent.
    """
    if not isinstance(payload, dict):
        return None
    tx_hash = payload.get("hash")
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
        return None
    return Tx(
        tx_hash=tx_hash.lower(),
        nonce=hex_to_int(payload.get("nonce")),
        max_priority_fee_wei=hex_to_int(payload.get("maxPriorityFeePerGas")),
        max_fee_wei=hex_to_int(payload.get("maxFeePerGas")),
        gas_limit=hex_to_int(payload.get("gas")),
        tx_type=hex_to_int(payload.get("type")),
    )


async def fetch_tx_fingerprints(
    tx_hashes: Iterable[str],
    *,
    config: SourceConfig = DEFAULT_CONFIG,
    client: Any = None,
    transport: Any = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> dict[str, Tx] | None:
    """Fingerprints for *tx_hashes*, keyed by **lowercase** hash.

    Bounded and incremental by construction: the caller passes exactly the
    hashes it wants, so a sweep can be resumed simply by passing the ones it
    does not have yet.  De-duplicates its input — the same transaction can back
    several wallets' first deposits only in a malformed dataset, but asking
    twice costs a round trip either way.

    ``None`` when a whole batch could not be read from any endpoint — never a
    partial dict, which a caller would fold as "these wallets have no
    fingerprints" and a uniformity detector would then read as coverage it does
    not have.  ``{}`` for an empty input is a real answer and costs no request.
    """
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in tx_hashes:
        if not isinstance(raw, str):
            continue
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        wanted.append(key)
    if not wanted:
        return {}

    out: dict[str, Tx] = {}
    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        for batch in chunks(wanted, config.tx_batch_size):
            calls = [("eth_getTransactionByHash", [h]) for h in batch]
            try:
                results = await rpc_batch(s, config.state_rpcs, calls)
            except (AllEndpointsFailed, MalformedRequest):
                return None
            for tx_hash, payload in zip(batch, results):
                decoded = decode_tx(payload)
                if decoded is not None:
                    out[tx_hash] = decoded
    return out


__all__ = ["decode_tx", "fetch_tx_fingerprints"]
