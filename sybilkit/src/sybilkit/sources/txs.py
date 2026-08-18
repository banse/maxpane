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

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class TxSweep:
    """What one fingerprint pass read, and which hashes it could not.

    The same shape as :class:`~sybilkit.sources.blockscout.FundingSweep`, and
    for the same reason: a **partial** read handed back as a bare dict is
    indistinguishable from a complete one, and a uniformity detector reading a
    half-covered component sees a collapsed axis that is really a coverage
    hole.  WP1's ``gas_edges`` guards this with a ≥ 90 % coverage rule, but the
    guard can only work if the caller knows what it is missing.

    ``pending`` **is** the cursor: feed it back as *tx_hashes* on a later call.
    A hash lands there when its batch could not be read from any endpoint, or
    when the node answered without a usable transaction body (a reorg, or a
    hash that never landed) — both are "ask again", never "this transaction
    has no fingerprint".
    """

    fingerprints: dict[str, Tx]
    pending: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.fingerprints)


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
) -> TxSweep | None:
    """Fingerprints for *tx_hashes*, keyed by **lowercase** hash.

    Bounded and incremental by construction: the caller passes exactly the
    hashes it wants, so a sweep can be resumed simply by passing
    :attr:`TxSweep.pending` back.  De-duplicates its input — the same
    transaction can back several wallets' first deposits only in a malformed
    dataset, but asking twice costs a round trip either way.

    Three answers, never collapsed:

    * ``None`` — **no** batch was read from any endpoint.  A total outage, and
      it is not an empty dict, which a caller would fold as "these wallets have
      no fingerprints".
    * a :class:`TxSweep` with a non-empty ``pending`` — a partial read, and the
      caller can *see* which hashes are missing rather than inferring coverage
      from a dict's length.
    * a :class:`TxSweep` with an empty ``pending`` — complete.  An empty input
      gives an empty complete sweep and costs no request.

    A **malformed request short-circuits** the whole call — no rotation, no
    further batches, ``None``.  It is our own bug, it fails identically
    everywhere, and rotating on it triples the request count and hides it.
    (``fetch_deposits`` degrades the same way for the same reason; a fetcher
    that raised here would make "never crash the caller" untrue for a class of
    failure the caller cannot do anything about.)  An endpoint problem rotates
    inside ``rpc_batch``, which classifies on the message text.
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
        return TxSweep(fingerprints={}, pending=())

    out: dict[str, Tx] = {}
    pending: list[str] = []
    batches = chunks(wanted, config.tx_batch_size)
    read = 0
    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        for batch in batches:
            calls = [("eth_getTransactionByHash", [h]) for h in batch]
            try:
                results = await rpc_batch(s, config.state_rpcs, calls)
            except MalformedRequest:
                return None  # our own bug: stop, do not rotate, do not retry
            except AllEndpointsFailed:
                pending.extend(batch)
                continue
            read += 1
            for tx_hash, payload in zip(batch, results):
                decoded = decode_tx(payload)
                if decoded is None:
                    # No usable body: ask again later, never "no fingerprint".
                    pending.append(tx_hash)
                else:
                    out[tx_hash] = decoded
    if read == 0:
        return None
    return TxSweep(fingerprints=out, pending=tuple(pending))


__all__ = ["TxSweep", "decode_tx", "fetch_tx_fingerprints"]
