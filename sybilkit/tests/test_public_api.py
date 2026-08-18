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


def test_dataset_from_events_builds_the_empty_dataset() -> None:
    """WP1 landed the body; the stub assertion this replaces is the only line
    of the freeze that was allowed to change.  Empty in, empty out — with the
    two tier-B/C lookups as real empty dicts, not ``None``."""
    ds = Dataset.from_events([], [])
    assert ds.deposits == ()
    assert ds.first_index == {}
    assert ds.txs == {}
    assert ds.funding == {}


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


#: The **only** part of the distribution allowed a third-party import, and it
#: is allowed exactly one: ``httpx``, lazily, inside the call that needs it.
#: WP0 wrote this exemption's shape into the two tests below before ``sources/``
#: existed ("this test grows an explicit exemption for that subpackage and for
#: nothing else"), and WP2 filled it in.  ``cli.py`` rides along because it
#: reaches the transport only *through* ``sources/`` — it is listed so that a
#: future direct import there is a decision somebody made here, not a drift.
IO_EXEMPT_PACKAGES = ("sources",)
IO_EXEMPT_FILES = ("cli.py",)
IO_ALLOWED_ROOTS = frozenset({"httpx"})


def _module_sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _is_io_exempt(path: Path) -> bool:
    rel = path.relative_to(SRC)
    return rel.parts[0] in IO_EXEMPT_PACKAGES or rel.name in IO_EXEMPT_FILES


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
    happened to write down.  WP2's ``sources/`` imports ``httpx``, so the test
    grew the exemption its own docstring promised — :data:`IO_EXEMPT_PACKAGES`
    plus :data:`IO_ALLOWED_ROOTS`, and nothing else.
    """
    offenders: list[str] = []
    for path in _module_sources():
        exempt = _is_io_exempt(path)
        for root in _imported_roots(path):
            if root in sys.stdlib_module_names or root == "sybilkit":
                continue
            if exempt and root in IO_ALLOWED_ROOTS:
                continue
            offenders.append(f"{path.relative_to(SRC)}: {root}")
    assert not offenders, offenders


def test_no_module_imports_maxpane_textual_or_a_transport() -> None:
    """Named explicitly as well, because these four are the ones that would
    make the distribution stop being standalone rather than merely stop being
    dependency-free.

    ``httpx`` is struck from the banned set for ``sources/`` alone, and for
    nothing else: maxpane, textual, requests and a bare ``socket`` stay banned
    everywhere, including there.
    """
    banned = {"maxpane", "maxpane_dashboard", "textual", "httpx", "requests", "socket"}
    for path in _module_sources():
        allowed = IO_ALLOWED_ROOTS if _is_io_exempt(path) else frozenset()
        clash = (banned - allowed) & _imported_roots(path)
        assert not clash, f"{path.relative_to(SRC)} imports {clash}"


def test_the_io_exemption_covers_exactly_the_sources_subpackage() -> None:
    """The exemption is a hole in two structural gates, so it gets its own
    pin: exactly one package, exactly one file, exactly one allowed root.  A
    later WP that widens any of the three has to widen it *here*, in front of
    this docstring, rather than by adding an import somewhere and watching a
    gate go quiet."""
    assert IO_EXEMPT_PACKAGES == ("sources",)
    assert IO_EXEMPT_FILES == ("cli.py",)
    assert IO_ALLOWED_ROOTS == frozenset({"httpx"})
    exempted = [p.relative_to(SRC) for p in _module_sources() if _is_io_exempt(p)]
    assert all(
        str(p).startswith("sources/") or str(p) == "cli.py" for p in exempted
    ), exempted


def test_the_distribution_ships_py_typed() -> None:
    assert (SRC / "py.typed").is_file()


# ===========================================================================
# WP0.3 — the report / config / detect surface
# ===========================================================================

from sybilkit.cluster import FAMILIES, DetectConfig, detect  # noqa: E402
from sybilkit.curve import curve_points  # noqa: E402
from sybilkit.report import Cluster, DetectResult, Reason, WalletVerdict  # noqa: E402

#: The three report dataclasses, frozen the same way the models are.
REPORT_KWARGS: dict[type, tuple[str, ...]] = {
    Reason: ("family", "human_string", "strength"),
    Cluster: (
        "cluster_id",
        "members",
        "reasons",
        "confidence",
        "points",
        "points_share",
        "span_blocks",
        "size",
    ),
    WalletVerdict: ("in_cluster", "cluster_id", "reasons", "confidence"),
}

REPORTS = tuple(REPORT_KWARGS)


def _reason(family: str = "amount", strength: float = 0.8) -> Reason:
    return Reason(family=family, human_string="identical 0.45 ETH send", strength=strength)


def _cluster(cluster_id: int = 0, points_share: float = 0.0681) -> Cluster:
    return Cluster(
        cluster_id=cluster_id,
        members=("0x" + "11" * 20, "0x" + "22" * 20),
        reasons=(_reason(),),
        confidence=0.9,
        points=1_811_322,
        points_share=points_share,
        span_blocks=254,
        size=1995,
    )


@pytest.mark.parametrize("model", REPORTS)
def test_report_models_are_frozen_slotted_dataclasses(model) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True
    assert "__slots__" in vars(model), f"{model.__name__} is not slotted"


@pytest.mark.parametrize("model", REPORTS)
def test_report_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    assert tuple(f.name for f in dataclasses.fields(model)) == REPORT_KWARGS[model]


@pytest.mark.parametrize("model", REPORTS)
def test_report_models_construct_from_their_documented_kwargs(model) -> None:
    assert model(**{name: None for name in REPORT_KWARGS[model]}) is not None


def test_the_five_signal_families_are_the_authority_and_live_in_cluster() -> None:
    """PRD §3.1: a cluster forms only when ≥ ``min_families`` **distinct**
    families link its members.  One tuple, in one module, or the combiner and
    the reason-writer count different things and the gate silently loosens.

    ``Reason`` deliberately does **not** validate against this tuple at
    construction: ``cluster.py`` imports ``report.py`` (it builds
    :class:`Cluster` objects), so a validating ``Reason`` would need the import
    to run the other way too.  The constraint is pinned here instead.
    """
    assert FAMILIES == ("amount", "sequence", "cadence", "gas", "funding")
    assert len(set(FAMILIES)) == len(FAMILIES)
    for family in FAMILIES:
        assert _reason(family).family == family
    # ...and the module that owns the tuple is the one the combiner lives in.
    assert FAMILIES is sys.modules["sybilkit.cluster"].FAMILIES
    assert not hasattr(sys.modules["sybilkit.report"], "FAMILIES")


def test_a_reason_is_a_pattern_language_string_with_a_graduated_strength() -> None:
    """"Reasons, never verdicts" (PRD §3.1).  ``strength`` is a float in [0, 1]
    so confidence can be multiplicative and graduated; a bool here would make
    every cluster binary, which is the failure mode the whole design avoids."""
    r = _reason(strength=0.55)
    assert _hint(Reason, "strength") == "float"
    assert _hint(Reason, "human_string") == "str"
    assert 0.0 <= r.strength <= 1.0


def test_a_cluster_carries_its_share_its_span_and_its_size() -> None:
    """``span_blocks`` is ``int | None`` — a one-block cluster spans 0, which is
    a real and very incriminating measurement, so the unknown case needs its own
    value."""
    c = _cluster()
    assert _hint(Cluster, "span_blocks") == "int | None"
    assert _hint(Cluster, "points") == "int"
    assert _hint(Cluster, "points_share") == "float"
    assert _hint(Cluster, "members") == "tuple[str, ...]"
    assert _hint(Cluster, "reasons") == "tuple[Reason, ...]"
    assert c.size == 1995 and c.span_blocks == 254


def test_clusters_are_ordered_by_points_share_descending() -> None:
    """PRD §3.3: ``res.clusters`` is sorted by ``points_share`` desc — widest
    operator first, because that is the row the OPERATORS panel leads with."""
    small, big = _cluster(1, 0.0042), _cluster(2, 0.1789)
    res = DetectResult(
        clusters=[big, small],
        total_points=26_585_740,
        flagged_points=11_498_903,
        clean_points=15_086_837,
    )
    assert [c.cluster_id for c in res.clusters] == [2, 1]
    assert res.clusters == sorted(
        [small, big], key=lambda c: c.points_share, reverse=True
    )


def test_detect_result_is_a_value_object_not_a_dataclass() -> None:
    """It has methods (``wallet``) and a derived property (``flagged``), so it
    is a small class rather than a dataclass — the four counters are the whole
    of its state and each is an ``int``, never a ``None``: a detector that ran
    always knows how many points it looked at."""
    assert not dataclasses.is_dataclass(DetectResult)
    res = DetectResult(
        clusters=[_cluster()],
        total_points=26_585_740,
        flagged_points=11_498_903,
        clean_points=15_086_837,
    )
    assert res.total_points == 26_585_740
    assert res.flagged_points + res.clean_points == res.total_points
    assert isinstance(res.clusters, list)


def test_detect_result_wallet_and_flagged_behave_on_the_empty_result() -> None:
    """WP1 landed the bodies; the stub assertions this replaces were the only
    lines allowed to change.  An empty result flags nobody and knows nobody —
    the safe default for a wallet it never analyzed is ``None``, never a
    zero-confidence verdict."""
    res = DetectResult(
        clusters=[], total_points=0, flagged_points=0, clean_points=0
    )
    assert res.wallet("0x" + "11" * 20) is None
    assert res.flagged == set()


def test_the_flagged_threshold_travels_with_the_result() -> None:
    """``res.flagged`` is "confidence >= threshold", so the threshold has to be
    somewhere the result can see it.  It is a keyword-only argument defaulting
    to ``DetectConfig.confidence_threshold``'s default, which is what makes
    ``detect()`` able to hand its config's value straight through and a
    hand-built result behave identically."""
    params = inspect.signature(DetectResult.__init__).parameters
    assert list(params) == [
        "self",
        "clusters",
        "total_points",
        "flagged_points",
        "clean_points",
        "confidence_threshold",
    ]
    assert params["confidence_threshold"].kind is inspect.Parameter.KEYWORD_ONLY
    default = dataclasses.fields(DetectConfig)
    (threshold,) = [f for f in default if f.name == "confidence_threshold"]
    assert params["confidence_threshold"].default == threshold.default


def test_a_wallet_verdict_separates_not_in_a_cluster_from_not_analyzed() -> None:
    """``res.wallet(addr)`` returns ``None`` when the wallet was **not
    analyzed**, and a ``WalletVerdict(in_cluster=False, ...)`` when it was
    analyzed and found clean.  Collapsing the two would let the `y` view print
    a confident "not linked" through an outage — the FARM-row defect,
    one wave early.
    """
    clean = WalletVerdict(in_cluster=False, cluster_id=None, reasons=(), confidence=0.0)
    linked = WalletVerdict(
        in_cluster=True, cluster_id=0, reasons=(_reason(),), confidence=0.91
    )
    assert clean.in_cluster is False and clean.cluster_id is None
    assert linked.cluster_id == 0
    assert _hint(WalletVerdict, "cluster_id") == "int | None"
    assert _hint(WalletVerdict, "in_cluster") == "bool"


def test_detect_config_defaults_are_the_measured_ones() -> None:
    """PRD §3.1/§3.3, and every one of the four is a measured decision:

    ``min_size=5``   — Hop used ≥10 and LayerZero ≥20; 5 is the floor that
                       still keeps one-human-few-wallets out.
    ``min_families=2`` — one family alone never convicts.
    ``near_amount_tol=0.10`` — ±10% catches the jitter-amount batches a
                       byte-identical rule cannot (499 runs / 7 369 wallets at
                       ±10%, against 281 / 3 779 byte-identical).
    ``confidence_threshold=0.5`` — the ``flagged`` cut, graduated either side.

    Amended in WP1 fix round 1 (controller-authorized frozen-surface
    amendments):

    ``points_per_eth=1000`` — ruling R10: the curve rate is an explicit,
    documented config field rather than a slot-invisible ``getattr`` on the
    dataset.  1000 is the rate the committed population was swept at; a
    caller that has read the live rate passes it here, visibly.
    ``protocol_min_amount_wei=None`` — ruling R13: when set, byte-identical
    groups AT the protocol minimum get no amount/split edge from
    identicalness alone (everyone sends the minimum; it identifies nobody).
    """
    cfg = DetectConfig()
    assert cfg.min_size == 5
    assert cfg.min_families == 2
    assert cfg.near_amount_tol == 0.10
    assert cfg.confidence_threshold == 0.5
    assert cfg.points_per_eth == 1000
    assert cfg.protocol_min_amount_wei is None
    assert dataclasses.is_dataclass(DetectConfig)
    assert DetectConfig.__dataclass_params__.frozen is True
    assert tuple(f.name for f in dataclasses.fields(DetectConfig)) == (
        "min_size",
        "min_families",
        "near_amount_tol",
        "confidence_threshold",
        "points_per_eth",
        "protocol_min_amount_wei",
    )


def test_detect_has_the_frozen_signature_and_runs_on_the_empty_dataset() -> None:
    params = inspect.signature(detect).parameters
    assert list(params) == ["ds", "config"]
    assert params["config"].default == DetectConfig()
    # WP1 landed the body; the stub assertion this replaces was the only part
    # of this test allowed to change.
    ds = Dataset(deposits=(), first_index={}, txs={}, funding={})
    res = detect(ds)
    assert res.clusters == []
    assert (res.total_points, res.flagged_points, res.clean_points) == (0, 0, 0)


def test_the_whole_prd_public_surface_imports_from_the_package_root() -> None:
    """PRD §3.3's first line is ``from sybilkit import Dataset, detect,
    DetectConfig`` — so those names must be on the package, not only on the
    submodules a reader would have to go looking for."""
    import sybilkit

    for name in (
        "Dataset",
        "detect",
        "DetectConfig",
        "DetectResult",
        "Deposit",
        "Tx",
        "Funding",
        "Cluster",
        "Reason",
        "WalletVerdict",
    ):
        assert hasattr(sybilkit, name), name
        assert name in sybilkit.__all__, name
    assert set(sybilkit.__all__) == {
        "Dataset",
        "detect",
        "DetectConfig",
        "DetectResult",
        "Deposit",
        "Tx",
        "Funding",
        "Cluster",
        "Reason",
        "WalletVerdict",
    }


def test_the_curve_preset_signature_floors_like_the_contract() -> None:
    """``curve_points(weight_wei, points_per_eth)`` — the contract's own
    ``isqrt(weight_wei) * points_per_eth // 10**9``.

    It lives in its own module rather than in ``curator.py`` (WP2's file)
    because ``Cluster.points`` needs it in **wave 1**: a cluster's points are
    the summed curve points of its members, so WP1 cannot compute a
    ``points_share`` without it.  WP2's ``sybilkit.curator`` re-exports *this*
    one; there is deliberately never a second implementation, because the
    second one is the one nobody mutation-tests.

    Two things are frozen by the signature alone and both are load-bearing:
    ``points_per_eth`` is **read from the chain**, never the documented 1000
    (CLAUDE.md hard constraint 4), and neither argument has a default, so no
    caller can silently inherit one.
    """
    params = inspect.signature(curve_points).parameters
    assert list(params) == ["weight_wei", "points_per_eth"]
    assert all(p.default is inspect.Parameter.empty for p in params.values())
    # WP1 landed the body; the stub assertion this replaces was the only line
    # of this test allowed to change.
    assert curve_points(10**18, 1000) == 1000


# ===========================================================================
# WP8 — the shared folds
#
# The cleanup lane's contract, and it is a *cross-distribution* one: maxpane's
# ``data/curator_clusters.py`` imports ``sybilkit.signals.first_rows`` and
# ``sybilkit.signals.tier_a_components`` by name, so a hoist that makes the
# library compute a fold once may only ever GROW those signatures, and only
# with keyword-only parameters carrying defaults.  These tests pin the growth
# *and* pin that being handed the fold answers exactly what deriving it does —
# a shared fold that changed a number would be a failed cleanup.
# ===========================================================================

from sybilkit.signals import (  # noqa: E402
    first_rows,
    identical_amount_windows,
    single_first_rows,
    tier_a_components,
)
from sybilkit.signals.amounts import amount_edges  # noqa: E402
from sybilkit.signals.cadence import cadence_edges  # noqa: E402
from sybilkit.signals.funding import funding_edges  # noqa: E402
from sybilkit.signals.gas import gas_edges  # noqa: E402
from sybilkit.signals.sequence import sequence_edges  # noqa: E402
from sybilkit.signals.split import split_edges  # noqa: E402

#: ``(callable, the positional parameters that were already frozen)``.  Every
#: parameter after those must be KEYWORD_ONLY with a default — the additive
#: shape the distribution boundary allows.
SHARED_FOLD_SIGNATURES: tuple[tuple[object, tuple[str, ...]], ...] = (
    (single_first_rows, ("ds",)),
    (identical_amount_windows, ("ds", "cfg")),
    (tier_a_components, ("ds", "cfg")),
    (amount_edges, ("ds", "cfg")),
    (split_edges, ("ds", "cfg")),
    (sequence_edges, ("ds", "cfg")),
    (cadence_edges, ("ds", "cfg")),
    (gas_edges, ("ds", "cfg")),
    (funding_edges, ("ds", "cfg")),
)


@pytest.mark.parametrize(
    "fn,frozen", SHARED_FOLD_SIGNATURES, ids=lambda v: getattr(v, "__name__", "")
)
def test_the_shared_fold_parameters_are_additive_and_keyword_only(fn, frozen) -> None:
    """The boundary rule, asserted structurally rather than remembered.

    ``first_rows`` and ``tier_a_components`` are imported *by maxpane*, and
    every other name here is one hop from them; a positional insertion or a
    renamed leading parameter breaks a second distribution that this suite
    cannot see.  So: the leading positional names are exactly what they were,
    and anything the hoist added is keyword-only and defaults to ``None``.
    """
    params = inspect.signature(fn).parameters
    names = list(params)
    assert names[: len(frozen)] == list(frozen), names
    for name in names[len(frozen) :]:
        p = params[name]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, (fn, name, p.kind)
        assert p.default is None, (fn, name, p.default)


def test_first_rows_itself_keeps_the_signature_maxpane_calls_it_with() -> None:
    """The one fold maxpane derives for itself.  It takes a dataset and
    nothing else, and the hoist must not have given it a knob — a defaulted
    parameter here would be a fold the two distributions could disagree on."""
    params = inspect.signature(first_rows).parameters
    assert list(params) == ["ds"]
    assert all(p.default is inspect.Parameter.empty for p in params.values())


def test_the_signals_accept_a_precomputed_first_row_map_and_agree_with_deriving_it() -> None:
    """``detect`` derived every contributor's first deposit seven times over.

    Handing the map in must be indistinguishable from letting each signal walk
    the deposits itself — same edges, same order, same reasons, same strengths
    — for the four tier-A families, for ``gas``, and for the two shared folds
    the amount family is built on.
    """
    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset()
    cfg = DetectConfig()
    firsts = first_rows(ds)
    assert firsts, "the labeled subset has first deposits to share"

    assert single_first_rows(ds, firsts=firsts) == single_first_rows(ds)
    assert tier_a_components(ds, cfg, firsts=firsts) == tier_a_components(ds, cfg)

    for fn in (amount_edges, split_edges, sequence_edges, cadence_edges):
        assert fn(ds, cfg, firsts=firsts) == fn(ds, cfg), fn.__name__
    groups = tier_a_components(ds, cfg, firsts=firsts)
    assert gas_edges(ds, cfg, groups=groups, firsts=firsts) == gas_edges(
        ds, cfg, groups=groups
    )
    # and with no groups handed in either, so the fallback path shares too
    assert gas_edges(ds, cfg, firsts=firsts) == gas_edges(ds, cfg)


def test_detect_walks_the_deposits_for_a_first_row_map_exactly_once() -> None:
    """The hoist itself, and the only way to see it is to count the walks.

    Seven callers used to derive the same map inside one ``detect`` run
    (``amounts`` twice, ``split``, ``sequence``, ``cadence``, ``gas``, and
    ``detect``'s own fold).  Counting is what makes this test bite: an
    agreement test alone stays green with every recomputation still in place.
    """
    import sybilkit.signals as signals_mod

    real = signals_mod.first_rows
    calls = 0

    def counting(ds):
        nonlocal calls
        calls += 1
        return real(ds)

    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset()
    signals_mod.first_rows = counting
    try:
        detect(ds, DetectConfig())
    finally:
        signals_mod.first_rows = real
    assert calls == 1, calls


def test_split_and_amounts_walk_one_windowing_pass() -> None:
    """The second shared fold: the ONE window discipline, run once.

    ``amounts`` and ``split`` are deliberately built on the same windowing pass
    — "neither can weld a crowd the other would have split" — and each used to
    compute it for itself, so the discipline they share was a shared *rule* and
    two separate answers.  ``detect`` runs the pass once and hands the same
    list to both; being handed it answers exactly what deriving it answers.
    """
    import sybilkit.signals as signals_mod
    import sybilkit.signals.amounts as amounts_mod
    import sybilkit.signals.split as split_mod

    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset()
    cfg = DetectConfig()
    windows = identical_amount_windows(ds, cfg, singles=single_first_rows(ds))
    assert windows, "the labeled subset has identical-amount windows to share"

    assert amount_edges(ds, cfg, windows=windows) == amount_edges(ds, cfg)
    assert split_edges(ds, cfg, windows=windows) == split_edges(ds, cfg)

    real = identical_amount_windows
    calls = 0

    def counting(ds_, cfg_, **kw):
        nonlocal calls
        calls += 1
        return real(ds_, cfg_, **kw)

    for mod in (signals_mod, amounts_mod, split_mod):
        mod.identical_amount_windows = counting
    try:
        detect(ds, cfg)
    finally:
        for mod in (signals_mod, amounts_mod, split_mod):
            mod.identical_amount_windows = real
    assert calls == 1, calls


def test_the_two_amount_signals_are_handed_the_very_same_windows() -> None:
    """Identity, not merely equality — the point of the hoist is that there is
    one pass, and a window is a list nobody downstream may mutate."""
    import sybilkit.signals.amounts as amounts_mod
    import sybilkit.signals.split as split_mod

    from tests.conftest import build_labeled_dataset

    ds = build_labeled_dataset()
    seen: list[object] = []

    def record(fn):
        def wrapped(ds_, cfg_, *, windows=None, **kw):
            seen.append(windows)
            return fn(ds_, cfg_, windows=windows, **kw)

        return wrapped

    real_amounts, real_split = amounts_mod.amount_edges, split_mod.split_edges
    amounts_mod.amount_edges = record(real_amounts)
    split_mod.split_edges = record(real_split)
    try:
        detect(ds, DetectConfig())
    finally:
        amounts_mod.amount_edges = real_amounts
        split_mod.split_edges = real_split

    assert len(seen) == 2
    assert seen[0] is not None
    assert seen[0] is seen[1]
    # and the pass survived both signals unmutated
    before = [(amount, list(window)) for amount, window in seen[0]]
    detect(ds, DetectConfig())
    assert [(amount, list(window)) for amount, window in seen[0]] == before


def test_the_preset_and_the_signals_agree_on_first_deposits(monkeypatch) -> None:
    """``curator.first_deposits`` and ``signals.first_rows`` are the same fold.

    They were two implementations of it — a sort-and-``setdefault`` here, a
    min-comparison there — agreeing today because nobody had changed either.
    That is the shape ruling R1 already refused for the curve ("the second copy
    is the one nobody mutation-tests"), and the same argument applies to a fold
    the detector and the preset both key their whole output off.

    Comparing the two to *each other* would be vacuous once one delegates, so
    they are both compared to a third derivation written out here — the plain
    "smallest ``(block_number, log_index)`` per contributor" an auditor would
    write — and the delegation itself is proven separately, by patching the
    name the preset imported and watching the preset's answer move with it.
    """
    import sybilkit.curator as curator_mod

    from tests.conftest import build_labeled_dataset, build_population_dataset

    for ds in (build_labeled_dataset(), build_population_dataset()):
        oracle: dict = {}
        for dep in ds.deposits:
            cur = oracle.get(dep.contributor)
            if cur is None or (dep.block_number, dep.log_index) < (
                cur.block_number,
                cur.log_index,
            ):
                oracle[dep.contributor] = dep
        assert oracle, "the fixture has deposits to fold"
        assert first_rows(ds) == oracle
        assert curator_mod.first_deposits(ds) == oracle

    ds = build_labeled_dataset()
    sentinel: dict = {}
    monkeypatch.setattr(curator_mod, "first_rows", lambda d: sentinel)
    assert curator_mod.first_deposits(ds) is sentinel
