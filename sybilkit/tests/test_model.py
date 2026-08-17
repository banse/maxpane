"""WP1.1 — ``Dataset.from_events``, the one coercing constructor.

Pure coercion: lowercase every address, integerise every wei word, de-dupe on
``(tx_hash, log_index)``, and *drop* a malformed row rather than zero it — the
``_usable_deposits`` discipline from ``curator_signals``.  No I/O anywhere.
"""

from __future__ import annotations

import pytest

from sybilkit.model import Dataset, Deposit, Funding, Tx

ADDR = "0x047F606FD5B2BAA5F5C6C4AB8958E45CB6B054B7"  # deliberately checksummed
ADDR_LC = ADDR.lower()
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


def test_the_committed_population_round_trips() -> None:
    """The full fixture builds: 22 319 deposits, 15 576 contributors, and the
    wei words survive exactly (no float anywhere near them)."""
    from tests.sybilkit_fixtures import load

    ds = Dataset.from_events(load("deposits.json.gz"), load("first_deposits.json.gz"))
    assert len(ds.deposits) == 22_319
    assert len(ds.first_index) == 15_576
    assert min(ds.first_index.values()) == 1
    assert any(d.amount_wei == 2_067_000_000_000_000_000 for d in ds.deposits)
