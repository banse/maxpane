"""WP1.1 — ``Dataset.from_events``, the one coercing constructor.

Pure coercion: lowercase every address, integerise every wei word, de-dupe on
``(tx_hash, log_index)``, and *drop* a malformed row rather than zero it — the
``_usable_deposits`` discipline from ``curator_signals``.  No I/O anywhere.
"""

from __future__ import annotations

from sybilkit.model import Dataset, Deposit, Funding, Tx

ADDR = "0x047F606FD5B2BAA5F5C6C4AB8958E45CB6B054B7"  # deliberately checksummed
ADDR_LC = ADDR.lower()
ADDR_0X = "0X" + ADDR[2:]  # the other prefix spelling: ``_wei`` already takes it
FUNDER = "0x332F73DD1E40DD9581444DBDC0BB6547FADBF954"
TX1 = "0x" + "ab" * 32
TX2 = "0x" + "cd" * 32


def _dep_row(**over) -> dict:
    row = {
        "contributor": ADDR,
        "hour": 3,
        "amount_wei": 450_000_000_000_000_000,
        "credited_delta_wei": 450_000_000_000_000_000,
        "weight_added_wei": 821_025_000_000_000_000,
        "new_weight_wei": 821_025_000_000_000_000,
        "tx_count": 1,
        "block_number": 25_771_131,
        "tx_hash": TX1,
        "log_index": 67,
    }
    row.update(over)
    return row


def _first_row(**over) -> dict:
    row = {"contributor": ADDR, "index": 2767}
    row.update(over)
    return row


def test_builds_a_dataset_from_raw_dicts() -> None:
    ds = Dataset.from_events([_dep_row()], [_first_row()])
    assert isinstance(ds, Dataset)
    assert len(ds.deposits) == 1
    dep = ds.deposits[0]
    assert isinstance(dep, Deposit)
    assert dep.amount_wei == 450_000_000_000_000_000
    assert dep.block_number == 25_771_131
    assert ds.first_index == {ADDR_LC: 2767}


def test_builds_a_dataset_from_deposit_objects() -> None:
    dep = Deposit(
        contributor=ADDR,  # still checksummed: from_events normalises
        hour=3,
        amount_wei=450_000_000_000_000_000,
        credited_delta_wei=450_000_000_000_000_000,
        weight_added_wei=821_025_000_000_000_000,
        new_weight_wei=821_025_000_000_000_000,
        tx_count=1,
        block_number=25_771_131,
        tx_hash=TX1,
        log_index=67,
    )
    ds = Dataset.from_events([dep], [_first_row()])
    assert ds.deposits[0].amount_wei == 450_000_000_000_000_000
    assert ds.deposits[0].contributor == ADDR_LC


def test_addresses_are_normalised_lowercase() -> None:
    """The bite WP1.1 mandates: a checksummed producer and a lowercase one must
    land on the same key, or every cluster silently splits in half."""
    ds = Dataset.from_events(
        [_dep_row(contributor=ADDR)],
        [_first_row(contributor=ADDR)],
        txs={TX1.upper().replace("0X", "0x"): {"tx_hash": TX1, "nonce": 0}},
        funding={ADDR: {"address": ADDR, "funder": FUNDER, "hops": 1}},
    )
    assert ds.deposits[0].contributor == ADDR_LC
    assert list(ds.first_index) == [ADDR_LC]
    assert list(ds.txs) == [TX1.lower()]
    assert list(ds.funding) == [ADDR_LC]
    assert ds.funding[ADDR_LC].address == ADDR_LC
    assert ds.funding[ADDR_LC].funder == FUNDER.lower()


def test_wei_words_coerce_from_hex_and_decimal_strings() -> None:
    """Real producers hand out all three spellings; every one lands as ``int``."""
    ds = Dataset.from_events(
        [
            _dep_row(
                amount_wei="450000000000000000",
                credited_delta_wei="0x63eb89da4ed00000",
                new_weight_wei=821_025_000_000_000_000,
            )
        ],
        [_first_row(index="2767")],
    )
    dep = ds.deposits[0]
    assert dep.amount_wei == 450_000_000_000_000_000
    assert dep.credited_delta_wei == 0x63EB89DA4ED00000
    assert isinstance(dep.amount_wei, int)
    assert isinstance(dep.credited_delta_wei, int)
    assert ds.first_index[ADDR_LC] == 2767
    assert isinstance(ds.first_index[ADDR_LC], int)


def test_deposits_are_deduped_on_tx_hash_and_log_index() -> None:
    """A re-org replay hands the same event twice; it must count once."""
    ds = Dataset.from_events([_dep_row(), _dep_row()], [_first_row()])
    assert len(ds.deposits) == 1
    # ...but the same tx at a different log index is a second, real event.
    ds2 = Dataset.from_events(
        [_dep_row(), _dep_row(log_index=68)], [_first_row()]
    )
    assert len(ds2.deposits) == 2


def test_first_index_is_one_based_and_keyed_lowercase() -> None:
    ds = Dataset.from_events([], [_first_row(index=1)])
    assert ds.first_index == {ADDR_LC: 1}
    # an index of 0 would be a wallet that never deposited: malformed, dropped
    ds0 = Dataset.from_events([], [_first_row(index=0)])
    assert ds0.first_index == {}


def test_txs_and_funding_default_to_empty_dicts() -> None:
    """Tier A only: a caller with nothing but logs passes neither."""
    ds = Dataset.from_events([_dep_row()], [_first_row()])
    assert ds.txs == {}
    assert ds.funding == {}


def test_a_malformed_deposit_is_dropped_not_zeroed() -> None:
    """The ``_usable_deposits`` discipline: a row whose words cannot be read is
    not in the dataset, and it is never a row of zeros."""
    rows = [
        _dep_row(),
        _dep_row(amount_wei=None, tx_hash=TX2),           # missing word
        _dep_row(amount_wei="not-a-number", tx_hash=TX2),  # unreadable word
        {"contributor": ADDR},                             # missing everything
    ]
    ds = Dataset.from_events(rows, [_first_row()])
    assert len(ds.deposits) == 1
    assert all(d.amount_wei > 0 for d in ds.deposits)


def test_a_negative_wei_word_is_malformed_and_the_row_is_dropped() -> None:
    """Hostile input: a negative amount would survive to ``math.isqrt`` and
    crash ``detect`` with a ValueError deep in the curve.  Negative wei is a
    word that cannot have come off the contract — the row is dropped, not
    zeroed, in both the int and string spellings."""
    rows = [
        _dep_row(),
        _dep_row(amount_wei=-1, tx_hash=TX2),
        _dep_row(new_weight_wei="-450000000000000000", tx_hash=TX2, log_index=99),
    ]
    ds = Dataset.from_events(rows, [_first_row()])
    assert len(ds.deposits) == 1
    # ...and the tier-B/C words hold the same line
    ds2 = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        txs={TX1: {"tx_hash": TX1, "nonce": -3, "gas_limit": 91_600}},
        funding={ADDR: {"address": ADDR, "funder": FUNDER, "hops": -1}},
    )
    assert ds2.txs == {}
    assert ds2.funding == {}


def test_a_hostile_dataset_never_reaches_the_curve_with_a_negative() -> None:
    """End to end: negative rows dropped at the door means ``detect`` runs."""
    from sybilkit import detect

    rows = [_dep_row(amount_wei=-(10**18), new_weight_wei=-(10**18), tx_hash=TX2)]
    res = detect(Dataset.from_events(rows, [_first_row()]))
    assert res.clusters == []
    assert res.total_points == 0


def test_no_sort_dependence_on_input_order() -> None:
    """Chain order is ``(block_number, log_index)`` and the constructor imposes
    it, so a shuffled producer and an ordered one build the same dataset."""
    rows = [
        _dep_row(block_number=25_771_200, log_index=3, tx_hash=TX2),
        _dep_row(block_number=25_771_131, log_index=67, tx_hash=TX1),
        _dep_row(block_number=25_771_200, log_index=1, tx_hash="0x" + "ef" * 32),
    ]
    a = Dataset.from_events(rows, [_first_row()])
    b = Dataset.from_events(list(reversed(rows)), [_first_row()])
    assert a.deposits == b.deposits
    assert [(d.block_number, d.log_index) for d in a.deposits] == [
        (25_771_131, 67),
        (25_771_200, 1),
        (25_771_200, 3),
    ]


def test_tx_rows_keep_none_for_fields_that_do_not_exist() -> None:
    """A legacy type-0 transaction has no priority fee and no max fee; the
    ``None`` must survive coercion rather than becoming a zero."""
    ds = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        txs={TX1: {"tx_hash": TX1, "nonce": 4, "gas_limit": "91600", "tx_type": 0}},
    )
    tx = ds.txs[TX1.lower()]
    assert isinstance(tx, Tx)
    assert tx.max_priority_fee_wei is None
    assert tx.max_fee_wei is None
    assert tx.gas_limit == 91_600
    assert tx.tx_type == 0


def test_funding_none_funder_survives_as_none() -> None:
    """``funder is None`` is "we could not resolve one" — never dropped into a
    fake funder and never an empty string."""
    ds = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        funding={ADDR: {"address": ADDR, "funder": None, "hops": None}},
    )
    f = ds.funding[ADDR_LC]
    assert isinstance(f, Funding)
    assert f.funder is None
    assert f.hops is None


def test_the_population_fixture_spelling_block_is_accepted() -> None:
    """The committed population rows spell the block ``block``, the labeled
    subset spells it ``block_number``; both are real producers."""
    row = _dep_row()
    row["block"] = row.pop("block_number")
    ds = Dataset.from_events([row], [_first_row()])
    assert ds.deposits[0].block_number == 25_771_131


def test_an_iso_string_timestamp_degrades_the_label_and_keeps_the_deposit() -> None:
    """Review finding #8.  ``ts`` is the one field whose absence degrades a
    *label* and not a signal — cadence detection runs off ``block_number``,
    which is always present — so a *malformed* ``ts`` must degrade exactly the
    way an absent one does: to ``None``, with the deposit kept.  Reading it
    inside the row's own ``try`` made an ISO-8601 string (what Blockscout and
    every CSV export hand out) drop the whole deposit."""
    ds = Dataset.from_events(
        [_dep_row(ts="2026-08-17T19:58:47.000000Z")], [_first_row()]
    )
    assert len(ds.deposits) == 1
    dep = ds.deposits[0]
    assert dep.ts is None
    assert dep.amount_wei == 450_000_000_000_000_000
    assert dep.block_number == 25_771_131
    # ...and a readable timestamp still lands as a float, in both spellings
    ds2 = Dataset.from_events(
        [_dep_row(ts=1_755_460_727), _dep_row(ts="1755460728", tx_hash=TX2)],
        [_first_row()],
    )
    assert [d.ts for d in ds2.deposits] == [1_755_460_727.0, 1_755_460_728.0]
    assert all(isinstance(d.ts, float) for d in ds2.deposits)


def test_a_whole_population_with_iso_timestamps_still_builds_a_dataset() -> None:
    """The review's reproduction, committed.  A fully valid population whose
    producer spells ``ts`` ISO-8601 used to build an *empty* ``Dataset``, and
    every downstream count read zero — the worst shape of failure this repo
    knows, because nothing raises and nothing is marked degraded."""
    from tests.sybilkit_fixtures import load

    rows = load("deposits.json.gz")
    for row in rows:
        row["ts"] = "2026-08-17T19:58:47Z"
    ds = Dataset.from_events(rows, load("first_deposits.json.gz"))
    assert len(ds.deposits) == 22_319
    assert len(ds.first_index) == 15_576
    assert all(d.ts is None for d in ds.deposits)


def test_a_malformed_amount_still_drops_the_row() -> None:
    """The complement of #8: only ``ts`` degrades.  A word that *is* a signal is
    still dropped — never zeroed — however it is spelled, and a row carrying an
    unreadable ``ts`` alongside an unreadable amount is dropped for the amount."""
    rows = [
        _dep_row(),
        _dep_row(amount_wei="not-a-number", tx_hash=TX2, ts="2026-08-17T19:58:47Z"),
        _dep_row(new_weight_wei=None, tx_hash=TX2, log_index=99),
    ]
    ds = Dataset.from_events(rows, [_first_row()])
    assert len(ds.deposits) == 1
    assert ds.deposits[0].tx_hash == TX1.lower()


def test_a_checksummed_funder_on_a_prebuilt_row_is_lowercased_like_a_mapping_row() -> None:
    """Review finding #9.  ``isinstance(row, Funding)`` short-circuited straight
    into the dict, so a checksummed ``funder`` survived un-normalised.  Every
    component map in the library is keyed lowercase, so an un-normalised funder
    silently kills the 0.95 peel-chain edge and splits ``by_funder`` hubs — the
    strongest measured discriminator on this population, lost to spelling."""
    prebuilt = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        funding=[Funding(address=ADDR, funder=FUNDER, hops=1)],
    )
    mapped = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        funding=[{"address": ADDR, "funder": FUNDER, "hops": 1}],
    )
    assert list(prebuilt.funding) == [ADDR_LC]
    assert prebuilt.funding[ADDR_LC].address == ADDR_LC
    assert prebuilt.funding[ADDR_LC].funder == FUNDER.lower()
    assert prebuilt.funding == mapped.funding


def test_a_prebuilt_tx_with_a_float_fee_is_dropped_not_admitted() -> None:
    """A float already lost its low digits upstream, which is exactly why
    ``_wei`` refuses one.  The prebuilt fast path skipped ``_opt_wei``
    altogether, so a float priority fee walked into the gas axes and the
    distinct-value count they feed."""
    ds = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        txs=[Tx(TX1, 4, 1.0e8, 141_167_541, 91_600, 2)],
    )
    assert ds.txs == {}
    # ...and a negative one is refused on the same path, for the same reason
    neg = Dataset.from_events(
        [_dep_row()], [_first_row()], txs=[Tx(TX1, -3, 100_000_000, None, 91_600, 2)]
    )
    assert neg.txs == {}
    # ...while the well-formed row is admitted, hash normalised
    ok = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        txs=[Tx("0x" + "AB" * 32, 4, 100_000_000, 141_167_541, 91_600, 2)],
    )
    assert list(ok.txs) == [TX1]
    assert ok.txs[TX1].max_priority_fee_wei == 100_000_000


def test_an_uppercase_0x_address_is_accepted_exactly_like_a_lowercase_one() -> None:
    """``_wei`` lowercases before it looks for the ``0x`` prefix, so ``0X…`` is a
    valid *amount*; ``_addr`` checked the prefix on the raw string, so the very
    same spelling was malformed in an *address* and took the row with it.  One
    spelling rule, every field — and leading whitespace is stripped in all of
    them, not just the wei words."""
    ds = Dataset.from_events(
        [_dep_row(contributor=ADDR_0X, amount_wei="0X63EB89DA4ED00000")],
        [_first_row(contributor=ADDR_0X)],
        funding=[{"address": ADDR_0X, "funder": " " + FUNDER + "\n", "hops": 1}],
    )
    assert len(ds.deposits) == 1
    assert ds.deposits[0].contributor == ADDR_LC
    assert ds.deposits[0].amount_wei == 0x63EB89DA4ED00000
    assert ds.first_index == {ADDR_LC: 2767}
    assert ds.funding[ADDR_LC].funder == FUNDER.lower()
    # ...and the tx-hash words hold the same rule
    ds2 = Dataset.from_events([_dep_row(tx_hash="0X" + "AB" * 32)], [_first_row()])
    assert ds2.deposits[0].tx_hash == TX1


def test_the_prebuilt_and_mapping_paths_build_equal_datasets() -> None:
    """The whole of #9 in one assertion.  The same rows, handed over as
    dataclasses and as mappings, must describe the same dataset — a producer
    that decoded its own rows (maxpane's detached sweep hands over real ``Tx``
    and ``Funding`` objects) otherwise got a *different* dataset from one that
    passed the raw dicts."""
    dep = Deposit(
        contributor=ADDR,
        hour=3,
        amount_wei=450_000_000_000_000_000,
        credited_delta_wei=450_000_000_000_000_000,
        weight_added_wei=821_025_000_000_000_000,
        new_weight_wei=821_025_000_000_000_000,
        tx_count=1,
        block_number=25_771_131,
        tx_hash=TX1,
        log_index=67,
    )
    prebuilt = Dataset.from_events(
        [dep],
        [_first_row()],
        txs={TX1: Tx(TX1, 4, 100_000_000, 141_167_541, 91_600, 2)},
        funding={ADDR: Funding(ADDR, FUNDER, 1)},
    )
    mapped = Dataset.from_events(
        [_dep_row()],
        [_first_row()],
        txs={
            TX1: {
                "tx_hash": TX1,
                "nonce": 4,
                "max_priority_fee_wei": 100_000_000,
                "max_fee_wei": 141_167_541,
                "gas_limit": 91_600,
                "tx_type": 2,
            }
        },
        funding={ADDR: {"address": ADDR, "funder": FUNDER, "hops": 1}},
    )
    assert prebuilt == mapped


def test_a_shuffled_producer_and_an_ordered_one_build_the_same_dataset() -> None:
    """Review finding #7a, ruling D3-B.  Two rows sharing a
    ``(tx_hash, log_index)`` but differing in content — what a reorg replay, or
    two sweeps merged across one, produces — were deduped **first-wins on input
    order**.  A shuffled producer and an ordered one therefore built *different*
    datasets, which ``from_events``' own docstring flatly denies."""
    old = _dep_row(block_number=25_771_131, amount_wei=450_000_000_000_000_000)
    new = _dep_row(block_number=25_771_140, amount_wei=470_000_000_000_000_000)
    a = Dataset.from_events([old, new], [_first_row()])
    b = Dataset.from_events([new, old], [_first_row()])
    assert len(a.deposits) == 1
    assert a == b


def test_a_reorg_replay_keeps_the_row_at_the_higher_block() -> None:
    """The canonical row is the later inclusion, whichever order it arrives in.
    Where the blocks tie, the remaining words settle it — they exist only so
    that the answer is never the input order's."""
    orphan = _dep_row(block_number=25_771_131, new_weight_wei=821_025_000_000_000_000)
    canon = _dep_row(block_number=25_771_140, new_weight_wei=900_000_000_000_000_000)
    for rows in ([orphan, canon], [canon, orphan]):
        ds = Dataset.from_events(rows, [_first_row()])
        assert len(ds.deposits) == 1
        assert ds.deposits[0].block_number == 25_771_140
        assert ds.deposits[0].new_weight_wei == 900_000_000_000_000_000
    twin_low = _dep_row(new_weight_wei=821_025_000_000_000_000)
    twin_high = _dep_row(new_weight_wei=900_000_000_000_000_000)
    first = Dataset.from_events([twin_low, twin_high], [_first_row()])
    second = Dataset.from_events([twin_high, twin_low], [_first_row()])
    assert first == second
    assert first.deposits[0].new_weight_wei == 900_000_000_000_000_000


def test_the_higher_block_wins_even_when_the_other_row_scores_higher() -> None:
    """The *field order* of :func:`_replay_rank`, not merely its terms.

    Every other replay test above hands the higher block the higher
    ``new_weight_wei`` as well, so ``block_number`` never has to outrank
    anything: an auditor swapped the first two terms of the tuple and all
    twenty-five tests in this file stayed green.  Here the two words disagree —
    the later inclusion carries the *lower* weight, which is what a reorg that
    dropped an earlier deposit by the same contributor leaves behind — and
    ``block_number`` is still the rule, in both arrival orders.
    """
    later_but_lighter = _dep_row(
        block_number=25_771_140, new_weight_wei=821_025_000_000_000_000
    )
    earlier_but_heavier = _dep_row(
        block_number=25_771_131, new_weight_wei=900_000_000_000_000_000
    )
    for rows in (
        [later_but_lighter, earlier_but_heavier],
        [earlier_but_heavier, later_but_lighter],
    ):
        ds = Dataset.from_events(rows, [_first_row()])
        assert len(ds.deposits) == 1
        assert ds.deposits[0].block_number == 25_771_140
        assert ds.deposits[0].new_weight_wei == 821_025_000_000_000_000


def test_two_byte_identical_duplicates_still_collapse_to_one_row() -> None:
    """The ordinary case is untouched: one page fetched twice, or a replay of
    the same bytes, still counts once — and the same transaction at a different
    log index is still a second, real event."""
    ds = Dataset.from_events([_dep_row(), _dep_row(), _dep_row()], [_first_row()])
    assert len(ds.deposits) == 1
    ds2 = Dataset.from_events([_dep_row(), _dep_row(log_index=68)], [_first_row()])
    assert len(ds2.deposits) == 2


def test_the_committed_population_round_trips() -> None:
    """The full fixture builds: 22 319 deposits, 15 576 contributors, and the
    wei words survive exactly (no float anywhere near them)."""
    from tests.sybilkit_fixtures import load

    ds = Dataset.from_events(load("deposits.json.gz"), load("first_deposits.json.gz"))
    assert len(ds.deposits) == 22_319
    assert len(ds.first_index) == 15_576
    assert min(ds.first_index.values()) == 1
    assert any(d.amount_wei == 2_067_000_000_000_000_000 for d in ds.deposits)
