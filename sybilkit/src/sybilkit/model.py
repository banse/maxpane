"""The wei-native input vocabulary.  Four dataclasses and one constructor.

Frozen in WP0; :meth:`Dataset.from_events` is filled in WP1.  Nothing in this
module imports anything but the standard library, and nothing in it knows that
maxpane exists — a caller hands us rows from whatever source it likes (a log
sweep, a Blockscout page, a CSV, a fixture) and we describe them.

Unit discipline
    **Everything is wei, and wei are ``int``.**  ``float`` cannot hold
    1 363 396 200 000 000 000 000 wei without rounding, and the points curve
    floors an integer square root, so a float anywhere upstream moves the last
    digits of every score.  There is no ``*_eth`` field in this package.

Outage discipline
    **A failed read is ``None``, never ``0``.**  :class:`Deposit` comes off a
    log, so its words are all present or the row does not exist — its wei
    fields are plain ``int``.  :class:`Tx` is the tier-B fingerprint and every
    field of it fails independently (a legacy type-0 transaction carries no
    ``maxPriorityFeePerGas`` at all), so all five are optional.
    :class:`Funding` is tier C, where ``funder is None`` means *we could not
    resolve one*, never *this address has none* — an EOA that has transacted
    always had a first funder; we may simply not have found it.

Raw discipline
    **Nothing derived lives here.**  No ``points``, no ``cluster_id``, no
    ``flagged``.  Those are ``cluster.py``'s and ``report.py``'s, which is what
    gives the curve exactly one implementation and one test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class _Malformed(Exception):
    """A row whose words cannot be read.  Raised internally, never escapes:
    ``from_events`` drops the row (the ``_usable_deposits`` discipline) —
    dropped, not zeroed, because a zero would be a *value* and outlive the
    defect that produced it."""


def _get(row: Any, name: str, *alts: str) -> Any:
    """A field off a mapping or an object, ``None`` when absent."""
    names = (name, *alts)
    if isinstance(row, Mapping):
        for n in names:
            if n in row:
                return row[n]
        return None
    for n in names:
        value = getattr(row, n, None)
        if value is not None:
            return value
    return None


def _wei(value: Any) -> int:
    """A wei word as an exact non-negative ``int``.  Accepts ``int``, a decimal
    string and a ``0x`` hex string — the three spellings real producers hand
    out.  A float is malformed on purpose: it already lost the low digits
    upstream.  A **negative** is malformed too: no event word can be negative,
    and one that slipped through would reach ``math.isqrt`` and crash the
    analysis instead of being dropped at the door."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _Malformed(repr(value))
    if isinstance(value, int):
        word = value
    else:
        text = value.strip()
        try:
            word = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            raise _Malformed(repr(value)) from None
    if word < 0:
        raise _Malformed(repr(value))
    return word


def _opt_wei(value: Any) -> int | None:
    """An *optional* word: ``None`` stays ``None`` (a failed read is ``None``,
    never ``0``)."""
    return None if value is None else _wei(value)


def _ts(value: Any) -> float | None:
    """A block's wall clock as a ``float``, or ``None`` — **never a raise**.

    ``ts`` is the one field whose absence degrades a *label* and not a signal:
    cadence detection runs off ``block_number``, which is always present, which
    is exactly why :class:`Deposit` lets ``ts`` be ``None``.  A *malformed*
    ``ts`` therefore has to degrade the same way an absent one does.  Reading it
    inside the row's own ``try`` did the opposite — an ISO-8601 string, which is
    what Blockscout and every CSV export hand out, raised ``ValueError`` and the
    blanket ``except`` dropped the whole deposit, so a fully valid population
    with ISO timestamps built an empty ``Dataset``.

    Only ``ts`` gets this treatment.  Every other word is a signal, and a signal
    that cannot be read still drops its row rather than being softened to
    ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _addr(value: Any) -> str:
    """A lowercase ``0x`` address.  The whole library keys membership on the
    lowercase spelling; a checksummed one from one producer and a lowercase one
    from another would silently split every cluster in half.

    Strip and lowercase **before** the prefix check, exactly as :func:`_wei`
    already does.  Checking the raw string made ``0X…`` malformed in an address
    while the identical spelling was a perfectly good wei word — one rule per
    field is one rule too many, and the row was dropped for a capital letter.
    """
    if not isinstance(value, str):
        raise _Malformed(repr(value))
    text = value.strip().lower()
    if not text.startswith("0x") or len(text) != 42:
        raise _Malformed(repr(value))
    return text


def _tx_hash(value: Any) -> str:
    """A lowercase ``0x`` transaction hash, on :func:`_addr`'s spelling rule:
    strip and lowercase first, *then* look for the prefix.  No length check —
    the hash is a de-dupe key here, not a decoded word."""
    if not isinstance(value, str):
        raise _Malformed(repr(value))
    text = value.strip().lower()
    if not text.startswith("0x"):
        raise _Malformed(repr(value))
    return text


@dataclass(frozen=True, slots=True)
class Deposit:
    """One deposit event, decoded.  Wei-native, raw words only.

    ``contributor`` is a **lowercase** ``0x`` address: the whole library keys
    sets, dicts and cluster membership on it, and a checksummed spelling in one
    producer and a lowercase one in another silently splits every cluster in
    half.  ``hour`` is the source event's own indexed hour bucket, so no
    timestamp is needed to bucket a deposit.

    ``credited_delta_wei`` may legitimately be ``0`` (a deposit above the
    protocol's credit cap) and ``weight_added_wei`` with it.  Both are real
    measurements, neither is a failed read, and nothing may divide by either.

    ``ts`` is the block's wall clock and is ``None`` when the producer had no
    timestamp to give, **or gave one we cannot read** — an ISO-8601 string, say,
    which is what Blockscout and every CSV export hand out.  Cadence detection
    works off ``block_number``, which is always present, precisely so that a
    missing ``ts`` degrades a label rather than a signal; an unreadable one
    degrades identically instead of taking the whole deposit down with it.
    """

    contributor: str
    hour: int
    amount_wei: int
    credited_delta_wei: int
    weight_added_wei: int
    new_weight_wei: int
    tx_count: int
    block_number: int
    tx_hash: str
    log_index: int
    ts: float | None = None


def _replay_rank(d: Deposit) -> tuple[int, ...]:
    """The tie-break for two rows sharing one ``(tx_hash, log_index)``.

    That collision is a **reorg replay** — or two sweeps merged across one — and
    the canonical row is the one at the higher block, so ``block_number`` is the
    rule.  The rest of the tuple exists for one purpose only: to make the answer
    total, so that it never depends on which row the producer handed over first.
    ``ts`` is deliberately absent — it is optional, and ``None`` does not order.

    This function is **byte-identical to the copy in ``sources/logs.py``** and
    must stay that way: the two modules dedupe the same rows on the same key,
    and a rule that differed between them would make a sweep's own ``Dataset``
    disagree with one built from its rows.  Frozen in the review-fix plan under
    decision D3 (option B).
    """
    return (
        d.block_number,
        d.new_weight_wei,
        d.amount_wei,
        d.credited_delta_wei,
        d.weight_added_wei,
        d.tx_count,
        d.hour,
    )


@dataclass(frozen=True, slots=True)
class Tx:
    """A tier-B transaction fingerprint.  Every field independently failable.

    The *uniformity* of these values across a group is the signal, never the
    values themselves: a farm collapses to one priority fee and one gas limit,
    while 60 control wallets showed 27 distinct priority fees and 15 gas
    limits.  0.035 gwei is a common honest default; 0.1 gwei shared by 3 085
    wallets is an operator.

    ``tx_type`` is the EIP-2718 envelope type (0 legacy, 2 EIP-1559).  A legacy
    transaction has no ``max_priority_fee_wei`` and no ``max_fee_wei`` at all —
    those are ``None`` because the field does not exist, which is why a
    detector must count *distinct non-None* values rather than treat a missing
    one as a shared zero.
    """

    tx_hash: str
    nonce: int | None
    max_priority_fee_wei: int | None
    max_fee_wei: int | None
    gas_limit: int | None
    tx_type: int | None


@dataclass(frozen=True, slots=True)
class Funding:
    """Tier C: the first address that funded *address*.

    The strongest measured discriminator on this population is not a *shared*
    funder (a hub) but a funder that is itself a member of the same behavioural
    cluster (a chain): 10/10 on fully-resolved farm samples against 0/47 on
    controls.  35 of those 47 controls *were* funded by a contributor — people
    funding from their own main wallet — which is normal and explicitly not the
    signal.

    ``funder is None`` means the lookup failed or was bounded out, never that
    the address has no funder.  ``hops`` is the peel depth at which the funder
    was found (1 = direct), and is ``None`` for the same reason.
    """

    address: str
    funder: str | None
    hops: int | None


@dataclass(frozen=True, slots=True)
class Dataset:
    """Everything the detectors read, already keyed for lookup.

    ``deposits`` is the full population in whatever order the caller supplied;
    detectors sort it themselves, per signal, because the sort a cadence
    detector wants (block, log index) is not the one an amount detector wants.

    ``first_index`` is the **1-based** join index by lowercase address —
    the protocol's own ``FirstDeposit`` counter.  1-based matters: a ``0``
    would be a wallet that never deposited, and the sequence detector runs on
    runs of *consecutive* indices, so an off-by-one shifts every run it finds.

    ``txs`` and ``funding`` may be empty dicts.  Empty is not a failure and not
    a lie: it means this dataset is tier A only, and the combiner will simply
    never emit a ``gas`` or ``funding`` edge — which, under the ≥2-family gate,
    is a real and honest loss of recall rather than a silent one.

    All four fields are **required**.  A ``default_factory=dict`` would be a
    mutable default on a frozen model and, worse, would let a producer that
    forgot to pass its tier-B payload look exactly like a producer that
    correctly reported having none.
    """

    deposits: tuple[Deposit, ...]
    first_index: dict[str, int]
    txs: dict[str, Tx]
    funding: dict[str, Funding]

    @classmethod
    def from_events(
        cls,
        deposits,
        first_deposits,
        *,
        txs=None,
        funding=None,
    ) -> "Dataset":
        """Build a :class:`Dataset` from raw event rows.  Pure; no I/O.

        *deposits* and *first_deposits* are sequences of mappings or of objects
        with the matching attributes — whatever a caller's own decoder produced.
        The classmethod lowercases every address, coerces every amount to a wei
        ``int`` (a decimal string, a ``0x`` hex string and an ``int`` all being
        things real producers hand out), and folds ``first_deposits`` into
        ``first_index``.

        *txs* and *funding* are keyword-only and default to ``None`` because
        tier A runs with neither: a caller that has only logs must not have to
        pass two empty dicts to say so.  A **pre-built** :class:`Tx` or
        :class:`Funding` takes exactly the same road as a mapping and is re-read
        through the same coercers rather than trusted — a decoder that produced
        a checksummed ``funder`` or a float fee is precisely the producer this
        door exists to normalise, and one that already produced clean values
        loses nothing by being asked twice.

        Malformed rows are **dropped, not zeroed** — with exactly one exception,
        ``ts``, which degrades to ``None`` (see :func:`_ts`) because it is a
        label and not a signal.  Deposits are de-duped on
        ``(tx_hash, log_index)`` and sorted into chain order
        ``(block_number, log_index)``, so a shuffled producer and an ordered
        one build the same dataset.

        Two rows can share that key and still differ — a reorg replay, or two
        sweeps merged across one.  They are settled by :func:`_replay_rank`, not
        by arrival: the higher ``block_number`` wins, and the remaining words
        break a tie so the result is total.  First-wins made the sentence above
        untrue, which is what decision D3 of the review-fix plan is about.
        """
        parsed: dict[tuple[str, int], Deposit] = {}
        for row in deposits:
            try:
                dep = Deposit(
                    contributor=_addr(_get(row, "contributor")),
                    hour=_wei(_get(row, "hour")),
                    amount_wei=_wei(_get(row, "amount_wei")),
                    credited_delta_wei=_wei(_get(row, "credited_delta_wei")),
                    weight_added_wei=_wei(_get(row, "weight_added_wei")),
                    new_weight_wei=_wei(_get(row, "new_weight_wei")),
                    tx_count=_wei(_get(row, "tx_count")),
                    block_number=_wei(_get(row, "block_number", "block")),
                    tx_hash=_tx_hash(_get(row, "tx_hash")),
                    log_index=_wei(_get(row, "log_index")),
                    ts=_ts(_get(row, "ts")),  # degrades to None, never drops the row
                )
            except (_Malformed, TypeError, ValueError):
                continue  # dropped, not zeroed
            key = (dep.tx_hash, dep.log_index)
            prev = parsed.get(key)
            if prev is None or _replay_rank(dep) > _replay_rank(prev):
                parsed[key] = dep
        ordered = tuple(
            sorted(parsed.values(), key=lambda d: (d.block_number, d.log_index))
        )

        first_index: dict[str, int] = {}
        for row in first_deposits:
            try:
                addr = _addr(_get(row, "contributor", "address"))
                index = _wei(_get(row, "index", "first_index"))
            except (_Malformed, TypeError, ValueError):
                continue
            if index >= 1:  # 1-based: a 0 is a wallet that never deposited
                first_index.setdefault(addr, index)

        parsed_txs: dict[str, Tx] = {}
        if txs is not None:
            rows: Iterable[Any] = txs.values() if isinstance(txs, Mapping) else txs
            for row in rows:
                # A pre-built ``Tx`` takes the same road as a mapping: ``_get``
                # reads an attribute as happily as a key, and a fast path here
                # skipped every coercer (a float fee walked into the gas axes).
                try:
                    tx = Tx(
                        tx_hash=_tx_hash(_get(row, "tx_hash")),
                        nonce=_opt_wei(_get(row, "nonce")),
                        max_priority_fee_wei=_opt_wei(_get(row, "max_priority_fee_wei")),
                        max_fee_wei=_opt_wei(_get(row, "max_fee_wei")),
                        gas_limit=_opt_wei(_get(row, "gas_limit")),
                        tx_type=_opt_wei(_get(row, "tx_type")),
                    )
                except (_Malformed, TypeError, ValueError):
                    continue
                parsed_txs.setdefault(tx.tx_hash, tx)

        parsed_funding: dict[str, Funding] = {}
        if funding is not None:
            rows = funding.values() if isinstance(funding, Mapping) else funding
            for row in rows:
                # Likewise: a pre-built ``Funding`` is re-coerced, because the
                # fast path let a checksummed ``funder`` through un-normalised
                # and every component map in the library is keyed lowercase.
                try:
                    funder = _get(row, "funder")
                    entry = Funding(
                        address=_addr(_get(row, "address", "contributor")),
                        funder=None if funder is None else _addr(funder),
                        hops=_opt_wei(_get(row, "hops")),
                    )
                except (_Malformed, TypeError, ValueError):
                    continue
                parsed_funding.setdefault(entry.address, entry)

        return cls(
            deposits=ordered,
            first_index=first_index,
            txs=parsed_txs,
            funding=parsed_funding,
        )


__all__ = ["Deposit", "Tx", "Funding", "Dataset"]
