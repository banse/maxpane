"""Interface freeze for ``sybilkit``'s public API (PRD §3.3, plan §3.1).

WP0 writes no behaviour.  What it writes is the *vocabulary* — the dataclass
field tuples, the function signatures, the config defaults and the family names
— because four work packages code against them in parallel and never speak:
WP1 fills the bodies, WP2 builds the preset/CLI/bench on top, WP3 consumes the
result from inside maxpane.  A field named wrong here is discovered a wave
later, at the cost of the wave.

Everything below therefore asserts *shape*, and every stub is expected to raise
``NotImplementedError("WP1")`` when called.  The day a body lands, the
``NotImplementedError`` assertions are the ones that change; nothing else here
may have to.

No test in this file (or this suite) opens a socket.  The structural proof is
:func:`test_the_package_imports_only_the_standard_library`, which reads the
import statements rather than a list of spellings someone thought of.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

from sybilkit.model import Dataset, Deposit, Funding, Tx

SRC = Path(__file__).resolve().parents[1] / "src" / "sybilkit"

ADDR = "0x047f606fd5b2baa5f5c6c4ab8958e45cb6b054b7"
FUNDER = "0x332f73dd1e40dd9581444dbdc0bb6547fadbf954"
TX = "0x" + "ab" * 32


# ===========================================================================
# WP0.2 — the wei-native model vocabulary
# ===========================================================================

#: The exact keyword names each producer passes, in declaration order.  This is
#: the freeze that matters: a rename anywhere fails at *collection* here rather
#: than silently becoming a ``None`` in someone else's cluster.
#:
#: Mirrors ``tests/data/test_curator_models.py::CONSTRUCTOR_KWARGS`` on the
#: maxpane side, deliberately — the two distributions keep the same house rule.
CONSTRUCTOR_KWARGS: dict[type, tuple[str, ...]] = {
    Deposit: (
        "contributor",
        "hour",
        "amount_wei",
        "credited_delta_wei",
        "weight_added_wei",
        "new_weight_wei",
        "tx_count",
        "block_number",
        "tx_hash",
        "log_index",
        "ts",
    ),
    Tx: (
        "tx_hash",
        "nonce",
        "max_priority_fee_wei",
        "max_fee_wei",
        "gas_limit",
        "tx_type",
    ),
    Funding: ("address", "funder", "hops"),
    Dataset: ("deposits", "first_index", "txs", "funding"),
}

MODELS = tuple(CONSTRUCTOR_KWARGS)


@pytest.mark.parametrize("model", MODELS)
def test_models_are_frozen_slotted_dataclasses(model) -> None:
    """``frozen=True, slots=True`` on all four.

    Frozen because a detector that mutated its input would make two runs over
    one ``Dataset`` disagree; slotted because the population is 22 319 deposits
    and a per-instance ``__dict__`` is the difference between analysing it and
    swapping.
    """
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True
    assert "__slots__" in vars(model), f"{model.__name__} is not slotted"


@pytest.mark.parametrize("model", MODELS)
def test_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    assert tuple(f.name for f in dataclasses.fields(model)) == CONSTRUCTOR_KWARGS[model]


@pytest.mark.parametrize("model", MODELS)
def test_every_model_constructs_from_its_documented_kwargs(model) -> None:
    """Constructing by keyword — the way every producer does — must not TypeError."""
    assert model(**{name: None for name in CONSTRUCTOR_KWARGS[model]}) is not None


@pytest.mark.parametrize("model", MODELS)
def test_models_are_immutable(model) -> None:
    instance = model(**{name: None for name in CONSTRUCTOR_KWARGS[model]})
    first = CONSTRUCTOR_KWARGS[model][0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, first, 0)


def _hint(model, name: str) -> str:
    """The annotation as written, normalised for whitespace.

    Read off ``dataclasses.fields`` rather than evaluated: these modules run
    under ``from __future__ import annotations``, and the *string* is what a
    reviewer sees and what a rename has to change.
    """
    (field,) = [f for f in dataclasses.fields(model) if f.name == name]
    return " ".join(str(field.type).split())


def test_every_wei_field_is_an_int_or_an_optional_int() -> None:
    """Wei-native: amounts are exact integers, never floats.

    ``float`` cannot hold 1 363 396 200 000 000 000 000 wei without rounding,
    and the curve floors an integer square root — a float anywhere upstream of
    it moves the last digits of every score.

    The *distribution* of wei fields is pinned too, not just their type: only
    :class:`Deposit` (four amounts off the event) and :class:`Tx` (two fee
    fields) carry any.  :class:`Funding` and :class:`Dataset` deliberately hold
    none — a wei field appearing on either would mean an amount had been
    derived somewhere it should not have been.
    """
    by_model = {
        model: tuple(
            f.name for f in dataclasses.fields(model) if f.name.endswith("_wei")
        )
        for model in MODELS
    }
    assert by_model == {
        Deposit: (
            "amount_wei",
            "credited_delta_wei",
            "weight_added_wei",
            "new_weight_wei",
        ),
        Tx: ("max_priority_fee_wei", "max_fee_wei"),
        Funding: (),
        Dataset: (),
    }
    for model, names in by_model.items():
        for name in names:
            assert _hint(model, name) in ("int", "int | None"), (model.__name__, name)


def test_a_failed_read_is_none_and_the_optional_fields_say_so() -> None:
    """CLAUDE.md's rule, carried into the library.

    ``Deposit`` comes off a log, so every word is present or the row does not
    exist — its wei fields are plain ``int``.  ``Tx`` is the tier-B fingerprint
    and every field of it can fail independently (a legacy type-0 tx has no
    ``maxPriorityFeePerGas`` at all), so all five are ``int | None``.
    ``Funding.funder`` is ``str | None`` and the ``None`` means "we could not
    resolve a funder" — never "this address has no funder", which is not a
    thing an EOA that has ever transacted can be.
    """
    for name in ("amount_wei", "credited_delta_wei", "weight_added_wei"):
        assert _hint(Deposit, name) == "int"
    for name in ("nonce", "max_priority_fee_wei", "max_fee_wei", "gas_limit", "tx_type"):
        assert _hint(Tx, name) == "int | None"
    assert _hint(Funding, "funder") == "str | None"
    assert _hint(Funding, "hops") == "int | None"
    assert _hint(Deposit, "ts") == "float | None"


def test_deposit_carries_the_dedupe_key_and_no_derived_field() -> None:
    """``(tx_hash, log_index)`` de-dupes a re-org replay; ``points``,
    ``cluster_id`` and friends are the analysis's, not the model's."""
    names = {f.name for f in dataclasses.fields(Deposit)}
    assert {"tx_hash", "log_index"} <= names
    for derived in ("points", "cluster_id", "flagged", "confidence", "rank", "is_sybil"):
        assert derived not in names


def test_no_model_field_is_eth_denominated() -> None:
    """The units boundary: the library is wei-native end to end.  ETH appears
    exactly once in the whole distribution — as ``points_per_eth``, the
    contract's own dimensionless rate — and never on a model."""
    for model in MODELS:
        for field in dataclasses.fields(model):
            assert not field.name.endswith("_eth"), f"{model.__name__}.{field.name}"


def test_dataset_from_events_is_a_classmethod_with_the_frozen_signature() -> None:
    """The one constructor WP1 fills.  ``txs``/``funding`` are keyword-only and
    default to ``None`` because tier A runs with neither — a caller that has
    only logs must not have to pass two empty dicts to say so."""
    assert isinstance(inspect.getattr_static(Dataset, "from_events"), classmethod)
    params = inspect.signature(Dataset.from_events).parameters
    assert list(params) == ["deposits", "first_deposits", "txs", "funding"]
    assert params["txs"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["funding"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["txs"].default is None
    assert params["funding"].default is None


def test_dataset_from_events_is_a_stub_until_wp1() -> None:
    with pytest.raises(NotImplementedError, match="WP1"):
        Dataset.from_events([], [])


def test_a_dataset_holds_the_four_lookups_the_signals_need() -> None:
    """Constructed directly (WP1 fills the coercing classmethod), so the field
    types are pinned before any body exists."""
    dep = Deposit(
        contributor=ADDR,
        hour=3,
        amount_wei=450_000_000_000_000_000,
        credited_delta_wei=450_000_000_000_000_000,
        weight_added_wei=628_875_000_000_000_000,
        new_weight_wei=628_875_000_000_000_000,
        tx_count=1,
        block_number=25_771_150,
        tx_hash=TX,
        log_index=12,
    )
    ds = Dataset(
        deposits=(dep,),
        first_index={ADDR: 3012},
        txs={TX: Tx(TX, 0, 100_000_000, 141_167_541, 91_600, 2)},
        funding={ADDR: Funding(ADDR, FUNDER, 1)},
    )
    assert ds.deposits[0].amount_wei == 450_000_000_000_000_000
    assert ds.first_index[ADDR] == 3012
    assert ds.txs[TX].gas_limit == 91_600
    assert ds.funding[ADDR].funder == FUNDER
    assert dep.ts is None


def test_the_first_index_is_the_one_based_first_deposit_index() -> None:
    """1-based, exactly like the contract's ``FirstDeposit`` topic: a 0 would be
    a wallet that never deposited, and the sequence detector runs on runs of
    *consecutive* indices, so an off-by-one shifts every run it finds."""
    assert "index" in inspect.getdoc(Dataset)
    ds = Dataset(deposits=(), first_index={ADDR: 1}, txs={}, funding={})
    assert min(ds.first_index.values()) == 1


# ===========================================================================
# WP0.2 — structural: stdlib only, no I/O, no maxpane
# ===========================================================================


def _module_sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names a file imports, read off the AST.

    Not a substring scan: ``from .model import Deposit`` and
    ``import httpx as h`` are both handled, and a spelling nobody thought of
    cannot slip through.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import — inside the package
                roots.add("sybilkit")
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_the_package_imports_only_the_standard_library() -> None:
    """PRD §3.5: the core is importable with **zero** third-party packages.

    Asserted against ``sys.stdlib_module_names`` rather than a banned list, so
    a future ``import numpy`` fails here too — not just the four names anyone
    happened to write down.  WP2's ``sources/`` will import ``httpx``; when it
    does, this test grows an explicit exemption for that subpackage and for
    nothing else.
    """
    offenders: list[str] = []
    for path in _module_sources():
        for root in _imported_roots(path):
            if root in sys.stdlib_module_names or root == "sybilkit":
                continue
            offenders.append(f"{path.relative_to(SRC)}: {root}")
    assert not offenders, offenders


def test_no_module_imports_maxpane_textual_or_a_transport() -> None:
    """Named explicitly as well, because these four are the ones that would
    make the distribution stop being standalone rather than merely stop being
    dependency-free."""
    banned = {"maxpane", "maxpane_dashboard", "textual", "httpx", "requests", "socket"}
    for path in _module_sources():
        clash = banned & _imported_roots(path)
        assert not clash, f"{path.relative_to(SRC)} imports {clash}"


def test_the_distribution_ships_py_typed() -> None:
    assert (SRC / "py.typed").is_file()
