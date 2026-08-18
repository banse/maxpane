"""Tier A: the ``eth_getLogs`` sweep, chunked and failed over.

One address-scoped filter with a topic0 ``OR`` array, walked in
:attr:`~sybilkit.sources.SourceConfig.log_chunk_blocks`-block pages over the
logs pool (``gateway.tenderly.co`` primary, ``eth.drpc.org`` behind it).

Two things about the paging that look like details and are not:

* **A provider's suggested range is never adopted.**  One of them decrements a
  single block per round trip and livelocks anything that follows it verbatim.
  The window halves, boundedly, and then the sweep fails honestly.
* **Shrinking narrows the window's right edge and re-issues the same cursor.**
  Raising ``fromBlock`` instead is correct for a rolling recent window and
  catastrophic for a backfill: the blocks it walks past are the contract's
  whole early history, and nothing ever asks for them again.

The two event signatures are **vendored ABI**, and their ``topic0``s are
**computed** from them by this package's own keccak at import.  A signature is
an interface definition — the same class of thing as a function name — while
``POINTS_PER_ETH`` and ``minDeposit`` are chain *state* and are read live
(``sources.fetch_uint_view``).  A hash pasted in as a literal could be checked
by nothing; a computed one is checked by
``tests/test_sources.py::test_the_event_topics_are_derived_not_remembered``
against the deployment's own independently vendored values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..model import Dataset, Deposit
from . import (
    DEFAULT_CONFIG,
    AllEndpointsFailed,
    MalformedRequest,
    RangeTooWide,
    SourceConfig,
    _Session,
    addr_from_topic,
    data_words,
    event_topic,
    hex_to_int,
    rpc_call,
)

#: ``Deposited(address contributor, uint256 hour, …)`` — nine words, the first
#: two indexed, so the hour comes off topic 2 and no timestamp is needed to
#: bucket a deposit.
DEPOSITED_SIGNATURE = (
    "Deposited(address,uint256,uint256,uint256,uint256,uint256,"
    "uint256,uint256,uint256)"
)
#: ``FirstDeposit(address contributor, uint256 index, uint256 ts)`` — ``index``
#: is the second indexed topic and is **1-based**.
FIRST_DEPOSIT_SIGNATURE = "FirstDeposit(address,uint256,uint256)"

DEPOSITED_TOPIC = event_topic(DEPOSITED_SIGNATURE)
FIRST_DEPOSIT_TOPIC = event_topic(FIRST_DEPOSIT_SIGNATURE)

#: ``Deposited``'s seven non-indexed data words, in order.
DEPOSIT_DATA_WORDS: tuple[str, ...] = (
    "amount_wei",
    "credited_delta_wei",
    "weight_added_wei",
    "new_weight_wei",
    "tx_count",
    "hour_total_wei",
    "early_bps",
)


@dataclass(frozen=True, slots=True)
class DepositSweep:
    """One log sweep's decoded rows, plus the range they describe.

    ``from_block``/``to_block`` are the sweep's own provenance and are what the
    CLI stamps into its output header — a *measured* range rather than a wall
    clock, so re-running the export over the same archive produces the same
    file.
    """

    from_block: int
    to_block: int
    deposits: tuple[Deposit, ...]
    first_deposits: tuple[dict, ...]

    def dataset(self, *, txs: Any = None, funding: Any = None) -> Dataset:
        """The sweep as a :class:`~sybilkit.model.Dataset`, through the public
        door — ``Dataset.from_events`` — so the coercion path is exercised
        rather than bypassed."""
        return Dataset.from_events(
            self.deposits, self.first_deposits, txs=txs, funding=funding
        )


def decode_deposit(row: Any) -> Deposit | None:
    """One ``Deposited`` log row → :class:`Deposit`, or ``None`` if unusable.

    ``None`` and not a zeroed row: a deposit whose de-dupe key is missing would
    otherwise render twice after a reorg replay, and a zeroed amount is a
    *value* that outlives the defect that produced it.
    """
    if not isinstance(row, dict):
        return None
    topics = row.get("topics") or []
    if len(topics) < 3 or str(topics[0]).lower() != DEPOSITED_TOPIC:
        return None
    words = data_words(row)
    if len(words) < len(DEPOSIT_DATA_WORDS):
        return None
    contributor = addr_from_topic(topics[1])
    hour = hex_to_int(topics[2])
    block = hex_to_int(row.get("blockNumber"))
    log_index = hex_to_int(row.get("logIndex"))
    tx_hash = row.get("transactionHash")
    if contributor is None or hour is None or block is None or log_index is None:
        return None
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
        return None
    values = {}
    for name, word in zip(DEPOSIT_DATA_WORDS, words):
        parsed = hex_to_int("0x" + word)
        if parsed is None:
            return None
        values[name] = parsed
    ts = hex_to_int(row.get("blockTimestamp"))
    return Deposit(
        contributor=contributor,
        hour=hour,
        amount_wei=values["amount_wei"],
        credited_delta_wei=values["credited_delta_wei"],
        weight_added_wei=values["weight_added_wei"],
        new_weight_wei=values["new_weight_wei"],
        tx_count=values["tx_count"],
        block_number=block,
        tx_hash=tx_hash.lower(),
        log_index=log_index,
        ts=None if ts is None else float(ts),
    )


def decode_first_deposit(row: Any) -> dict | None:
    """One ``FirstDeposit`` row → ``{"contributor", "index", "ts"}``.

    ``index`` is 1-based; a ``0`` would be a wallet that never deposited, and
    the sequence detector runs on runs of *consecutive* indices, so an
    off-by-one shifts every run it finds.
    """
    if not isinstance(row, dict):
        return None
    topics = row.get("topics") or []
    if len(topics) < 3 or str(topics[0]).lower() != FIRST_DEPOSIT_TOPIC:
        return None
    contributor = addr_from_topic(topics[1])
    index = hex_to_int(topics[2])
    if contributor is None or index is None or index < 1:
        return None
    words = data_words(row)
    stamped = hex_to_int("0x" + words[0]) if words else None
    if not stamped:
        stamped = hex_to_int(row.get("blockTimestamp"))
    return {
        "contributor": contributor,
        "index": index,
        "ts": None if not stamped else float(stamped),
    }


async def _page(
    session: _Session,
    contract: str,
    from_block: int,
    to_block: int,
) -> list[dict] | None:
    """Every matching row over ``[from_block, to_block]``, or ``None``.

    ``None`` on any failure: a partial backfill silently presented as a
    complete one is a leaderboard missing contributors.
    """
    cfg = session.config
    span = max(int(cfg.log_chunk_blocks), 1)
    cursor = from_block
    shrinks = 0
    rows: list[dict] = []
    while cursor <= to_block:
        end = min(cursor + span - 1, to_block)
        flt = {
            "address": contract,
            "fromBlock": hex(cursor),
            "toBlock": hex(end),
            "topics": [[DEPOSITED_TOPIC, FIRST_DEPOSIT_TOPIC]],
        }
        try:
            result = await rpc_call(session, cfg.log_rpcs, "eth_getLogs", [flt])
        except RangeTooWide:
            # THE LIVELOCK RULE.  The provider's own suggested range is not
            # even parsed: one of them decrements a single block per round trip
            # and a verbatim follower never converges.  Halve OUR span, at most
            # `max_shrinks` times, then fail honestly.
            if shrinks >= cfg.max_shrinks or span <= cfg.min_log_window:
                return None
            shrinks += 1
            span = max(span // 2, cfg.min_log_window)
            continue  # same cursor, narrower window
        except (MalformedRequest, AllEndpointsFailed):
            return None
        if not isinstance(result, list):
            return None
        rows.extend(r for r in result if isinstance(r, dict))
        cursor = end + 1
    return rows


async def fetch_deposits(
    contract: str,
    from_block: int,
    *,
    to_block: int | None = None,
    config: SourceConfig = DEFAULT_CONFIG,
    client: Any = None,
    transport: Any = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> DepositSweep | None:
    """The whole ``Deposited`` + ``FirstDeposit`` history, decoded.

    *to_block* defaults to the pool's own ``eth_blockNumber``, read in the same
    call chain so the sweep's stated range is one it actually asked for.

    Returns ``None`` — never an empty sweep — when the head could not be read
    or a page failed: ``[]`` here would read as "this contract has no history",
    which is the one conclusion an outage must never reach.
    """
    contract = contract.lower()
    async with _Session(config, client=client, transport=transport, sleep=sleep) as s:
        head = to_block
        if head is None:
            try:
                head = hex_to_int(await rpc_call(s, config.log_rpcs, "eth_blockNumber", []))
            except (AllEndpointsFailed, MalformedRequest, RangeTooWide):
                head = None
            if head is None:
                return None
        if head < from_block:
            return DepositSweep(from_block, head, (), ())
        rows = await _page(s, contract, from_block, head)
    if rows is None:
        return None

    deposits: dict[tuple[str, int], Deposit] = {}
    firsts: dict[str, dict] = {}
    for row in rows:
        if str(row.get("address", contract)).lower() != contract:
            continue  # the filter is address-scoped; anything else is not ours
        topic0 = str((row.get("topics") or [""])[0]).lower()
        if topic0 == DEPOSITED_TOPIC:
            dep = decode_deposit(row)
            if dep is not None:
                deposits.setdefault((dep.tx_hash, dep.log_index), dep)
        elif topic0 == FIRST_DEPOSIT_TOPIC:
            first = decode_first_deposit(row)
            if first is not None:
                firsts.setdefault(first["contributor"], first)
    ordered = tuple(sorted(deposits.values(), key=lambda d: (d.block_number, d.log_index)))
    first_rows = tuple(sorted(firsts.values(), key=lambda f: f["index"]))
    return DepositSweep(
        from_block=from_block, to_block=head, deposits=ordered, first_deposits=first_rows
    )


__all__ = [
    "DEPOSITED_SIGNATURE",
    "DEPOSITED_TOPIC",
    "DEPOSIT_DATA_WORDS",
    "FIRST_DEPOSIT_SIGNATURE",
    "FIRST_DEPOSIT_TOPIC",
    "DepositSweep",
    "decode_deposit",
    "decode_first_deposit",
    "fetch_deposits",
]
