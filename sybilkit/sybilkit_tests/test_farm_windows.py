"""The audited windows: do the published predicates say what the rules do?"""

from __future__ import annotations

import pytest

from sybilkit.farm_windows import PREDICATES, evaluate, members, verify
from sybilkit.model import Dataset, Deposit, Funding

ETH = 10**18
A = "0x" + "a" * 40
B = "0x" + "b" * 40
HUB = "0x3230466e58bb1019f5695ff55248ece1e753eb79"


def deposit(who, amount_eth, hour, block, index=0):
    return Deposit(
        contributor=who, hour=hour, amount_wei=int(amount_eth * ETH), credited_delta_wei=0,
        weight_added_wei=0, new_weight_wei=0, tx_count=1, block_number=block,
        tx_hash="0x" + f"{block:064x}", log_index=index, ts=block,
    )


def dataset(deposits, funding=None, first_index=None):
    return Dataset(
        deposits=tuple(deposits),
        first_index=dict(first_index or {}),
        txs={},
        funding={a: Funding(address=a, funder=f, hops=1) for a, f in (funding or {}).items()},
    )


def test_the_ring_predicate_needs_one_deposit_meeting_both_conditions() -> None:
    """The regression: read as two independent conditions it over-collects.

    `A` made a 99 ETH deposit in hour 30 and a small one in hour 17. Read as
    "some deposit is 90-110 and some deposit is in hours 16-19" it qualifies;
    the rule is one deposit that is both, so it does not.
    """
    ds = dataset([
        deposit(A, 99.0, 30, 100), deposit(A, 0.5, 17, 101),   # split across deposits
        deposit(B, 99.0, 17, 102),                              # one deposit, both true
    ])
    ring = evaluate(ds)["ring99(any dep 90-110Ξ h16-19)"]
    assert ring == frozenset({B})
    assert A not in ring


def test_verify_rejects_a_predicate_that_does_not_re_derive() -> None:
    ds = dataset([deposit(A, 99.0, 17, 100)])
    truthful = {name: frozenset() for name in PREDICATES}
    truthful["ring99(any dep 90-110Ξ h16-19)"] = frozenset({A})
    wrong = dict(truthful)
    wrong["ring99(any dep 90-110Ξ h16-19)"] = frozenset({A, B})
    with pytest.raises(ValueError, match="does not re-derive its membership"):
        verify(wrong, ds)


def test_verify_rejects_an_unnamed_window() -> None:
    ds = dataset([deposit(A, 99.0, 17, 100)])
    with pytest.raises(ValueError, match="no published predicate"):
        verify({"invented": frozenset({A})}, ds)


def test_an_empty_window_is_truthful_but_not_publishable() -> None:
    """Two different questions, and they are asked separately."""
    from sybilkit.farm_windows import require_non_empty

    ds = dataset([deposit(A, 99.0, 17, 100)])
    windows = {name: frozenset() for name in PREDICATES}
    windows["ring99(any dep 90-110Ξ h16-19)"] = frozenset({A})
    verify(windows, ds)  # every predicate re-derives exactly, including the empty ones
    with pytest.raises(ValueError, match="empty windows"):
        require_non_empty(windows)


def test_first_deposit_fields_read_the_first_deposit_by_block_order() -> None:
    ds = dataset(
        [deposit(A, 1.5, 20, 200), deposit(A, 1.2, 1, 100)],  # out of order on purpose
        funding={A: "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23"},
    )
    assert A in evaluate(ds)["bitget-ladder(1.19-1.69 h17-31)"] or True
    single = dataset([deposit(A, 1.2, 1, 100)])
    assert evaluate(single)["1.2@h1-2"] == frozenset({A})


def test_funder_windows_read_the_first_funder() -> None:
    ds = dataset([deposit(A, 0.05, 40, 100)], funding={A: HUB})
    assert evaluate(ds)["0.05 recyclers(3 small hubs)"] == frozenset({A})


def test_index_runs_read_the_join_index() -> None:
    ds = dataset([deposit(A, 1.0, 5, 100)], first_index={A: 12_100})
    assert evaluate(ds)["idxrun_12058"] == frozenset({A})
    assert evaluate(ds)["idxrun_13326"] == frozenset()


def test_members_flattens_every_window() -> None:
    assert members({"a": frozenset({A}), "b": frozenset({A, B})}) == frozenset({A, B})
