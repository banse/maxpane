"""Tier A: the ``eth_getLogs`` sweep, chunked and failed over.

One address-scoped filter with a topic0 ``OR`` array, walked in
:attr:`~sybilkit.sources.SourceConfig.log_chunk_blocks`-block pages over the
logs pool (``gateway.tenderly.co`` primary, ``eth.drpc.org`` behind it).

Two things about the paging that look like details and are not:

* **A provider's suggested range is never adopted.**  One of them decrements a
  single block per round trip and livelocks anything that follows it verbatim.
  The window halves, boundedly; when that is exhausted the head of the pool is
  dropped and the same cursor is retried against the next endpoint, because a
  *throttle* message carrying ``limited to`` classifies as a range cap and
  shrinking against a throttled endpoint forever is how a healthy second
  endpoint ends a sweep having received zero requests.
* **Shrinking narrows the window's right edge and re-issues the same cursor.**
  Raising ``fromBlock`` instead is correct for a rolling recent window and
  catastrophic for a backfill: the blocks it walks past are the contract's
  whole early history, and nothing ever asks for them again.
* **A sweep that read some chunks and then lost the pool is a partial, not a
  ``None``.**  ``DepositSweep.to_block`` names the extent actually covered and
  is the cursor a later sweep resumes from; discarding everything already
  fetched left the caller with no cursor at all.  Zero chunks read is still
  ``None`` — that one is an outage.

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

    ``to_block`` is the range the sweep **covered**, which on a partial pass is
    short of the chain head it asked for: the walk is contiguous from
    ``from_block``, so that one number is both the honest extent and the cursor
    a later sweep resumes from.
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


def _replay_rank(d: Deposit) -> tuple[int, int, int, int, int, int, int, str, bool, float]:
    """The tie-break for two rows sharing one ``(tx_hash, log_index)``.

    That collision is a **reorg replay** — or two sweeps merged across one — and
    the canonical row is the one at the higher block, so ``block_number`` is the
    rule.  Every later term exists for one purpose only: to make the answer
    **total**, so that it never depends on which row the producer handed over
    first.  Total means every field of the row takes part, ``contributor`` and
    ``ts`` included: a rank that stopped at the numeric words still ordered two
    rows differing only in those two by input order, which is the one thing
    ``Dataset.from_events`` promises not to do.  ``ts`` is optional and ``None``
    does not order, so it enters as a present-flag followed by a value.

    The same rule, term for term, lives in the other module: ``model.py`` and
    ``sources/logs.py`` dedupe the same rows on the same key, and a rule that
    differed between them would make the ``Dataset`` a sweep builds disagree
    with one built from its rows.  Frozen in the review-fix plan under decision
    D3 (option B); the two copies are pinned behaviourally by
    ``test_the_log_sweep_and_from_events_agree_on_a_conflicting_duplicate``.
    """
    return (
        d.block_number,
        d.new_weight_wei,
        d.amount_wei,
        d.credited_delta_wei,
        d.weight_added_wei,
        d.tx_count,
        d.hour,
        d.contributor,
        d.ts is not None,
        d.ts if d.ts is not None else 0.0,
    )


#: Clean chunks in a row before the window widens again.  A history that is
#: dense in one place and empty everywhere else used to pay the narrow window
#: for the whole rest of the walk — 16× the requests per chunk, forever, off
#: one dense region.
#:
#: Recovery is **symmetric**: when the span climbs all the way back to
#: ``log_chunk_blocks`` the per-endpoint shrink budget comes back with it.  It
#: used to reset only where the pool head is dropped, so a second dense region
#: after a full recovery skipped shrinking and spent an **endpoint** instead —
#: the expensive answer, on a pool two deep.  Full width is the conservative
#: place to do it: the walk can only get there by reading real chunks, so the
#: reset cannot feed the livelock the halving rule exists to prevent.
SPAN_RECOVER_AFTER = 4


async def _page(
    session: _Session,
    contract: str,
    from_block: int,
    to_block: int,
) -> tuple[list[dict], int | None]:
    """Every matching row over ``[from_block, to_block]``, and how far it got.

    Returns ``(rows, covered_to_block)``.  ``covered_to_block is None`` means
    **no chunk was read at all** — the outage case, and the only one the caller
    turns into ``None``.  Anything else is honest partial coverage: the walk is
    contiguous from ``from_block``, so one block number states its whole extent
    and is also the cursor a later sweep resumes from.

    Three failure shapes, three different answers:

    * ``RangeTooWide`` — halve **our own** span (never the provider's suggested
      one; one of them decrements a single block per round trip and a verbatim
      follower never converges), at most ``max_shrinks`` times.  When shrinking
      is exhausted the problem may not be the window at all: a *throttle*
      message carrying ``limited to`` classifies as a range cap, and shrinking
      against a throttled endpoint forever is how a healthy second endpoint
      ends a sweep having received zero requests.  So the head of the pool is
      dropped and the **same cursor** is retried against what is left.
    * ``MalformedRequest`` — our own bug, identical everywhere; stop.
    * ``AllEndpointsFailed`` / an unreadable result — stop, keeping what was
      already read.
    """
    cfg = session.config
    pool = list(cfg.log_rpcs)
    full_span = max(int(cfg.log_chunk_blocks), 1)
    span = full_span
    cursor = from_block
    shrinks = 0
    clean = 0
    rows: list[dict] = []
    covered: int | None = None
    while cursor <= to_block:
        end = min(cursor + span - 1, to_block)
        flt = {
            "address": contract,
            "fromBlock": hex(cursor),
            "toBlock": hex(end),
            "topics": [[DEPOSITED_TOPIC, FIRST_DEPOSIT_TOPIC]],
        }
        try:
            result = await rpc_call(session, tuple(pool), "eth_getLogs", [flt])
        except RangeTooWide:
            # THE LIVELOCK RULE.  The provider's own suggested range is not
            # even parsed: one of them decrements a single block per round trip
            # and a verbatim follower never converges.  Halve OUR span, at most
            # `max_shrinks` times.
            clean = 0
            if shrinks < cfg.max_shrinks and span > cfg.min_log_window:
                shrinks += 1
                span = max(span // 2, cfg.min_log_window)
                continue  # same cursor, narrower window
            # Shrinking is exhausted against THIS endpoint.  It may never have
            # been a range problem: rotate rather than fail with the rest of
            # the pool unasked.  The span is carried over rather than reset —
            # the recovery below widens it again off clean chunks, and a reset
            # here would make the requested spans climb mid-walk, which is the
            # one shape the livelock bite forbids.
            pool.pop(0)
            if not pool:
                return rows, covered
            shrinks = 0
            continue  # same cursor, next endpoint
        except (MalformedRequest, AllEndpointsFailed):
            return rows, covered
        if not isinstance(result, list):
            return rows, covered
        rows.extend(r for r in result if isinstance(r, dict))
        covered = end
        cursor = end + 1
        clean += 1
        if clean >= SPAN_RECOVER_AFTER and span < full_span:
            span = min(span * 2, full_span)
            clean = 0
            if span == full_span:
                # The shrink budget recovers with the span, and only at full
                # width.  Resetting it earlier would let one stubborn region
                # shrink forever; not resetting it at all made a *second* dense
                # region cost an endpoint rather than a shrink, which on a
                # two-deep pool is the whole pool for a history that is merely
                # lumpy.  Full width is reachable only by reading real chunks,
                # so this cannot livelock.
                shrinks = 0
    return rows, covered


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
    or **no chunk at all** could be: ``[]`` here would read as "this contract
    has no history", which is the one conclusion an outage must never reach.

    **A sweep that read some chunks and then lost the pool comes back as a
    partial**, with ``to_block`` naming the extent it actually covered.  This
    relaxes the older "``None``, never a partial" contract deliberately —
    ``docs/curator_sybil_review_fixes_plan.md`` §WP4.2(iii), ruled as
    recommended — because the alternative was discarding every chunk already
    fetched and offering the caller no resume cursor.  ``to_block`` is already
    the field that states coverage and already the cursor a later sweep starts
    from, so a partial states its own extent rather than lying by omission.
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
        rows, covered = await _page(s, contract, from_block, head)
    if covered is None:
        return None  # not one chunk was read: an outage, never an empty history

    deposits: dict[tuple[str, int], Deposit] = {}
    firsts: dict[str, dict] = {}
    for row in rows:
        if str(row.get("address", contract)).lower() != contract:
            continue  # the filter is address-scoped; anything else is not ours
        topic0 = str((row.get("topics") or [""])[0]).lower()
        if topic0 == DEPOSITED_TOPIC:
            dep = decode_deposit(row)
            if dep is not None:
                # Settled by content, not by arrival: `setdefault` kept the
                # orphaned row on an old-then-new ordering, so a shuffled
                # producer and an ordered one built different sweeps.
                key = (dep.tx_hash, dep.log_index)
                prev = deposits.get(key)
                if prev is None or _replay_rank(dep) > _replay_rank(prev):
                    deposits[key] = dep
        elif topic0 == FIRST_DEPOSIT_TOPIC:
            first = decode_first_deposit(row)
            if first is not None:
                firsts.setdefault(first["contributor"], first)
    ordered = tuple(sorted(deposits.values(), key=lambda d: (d.block_number, d.log_index)))
    first_rows = tuple(sorted(firsts.values(), key=lambda f: f["index"]))
    return DepositSweep(
        from_block=from_block,
        to_block=covered,
        deposits=ordered,
        first_deposits=first_rows,
    )


__all__ = [
    "DEPOSITED_SIGNATURE",
    "DEPOSITED_TOPIC",
    "DEPOSIT_DATA_WORDS",
    "FIRST_DEPOSIT_SIGNATURE",
    "FIRST_DEPOSIT_TOPIC",
    "SPAN_RECOVER_AFTER",
    "DepositSweep",
    "decode_deposit",
    "decode_first_deposit",
    "fetch_deposits",
]
