"""Interface freeze for the curator data layer.

Cheap structural tests whose only job is to stop the contract drifting while
WP2, WP3, WP4 and WP5 code against it in parallel.  Three vocabularies for one
dataclass does not surface as a merge conflict: the producer raises
``TypeError``, the consumer's ``getattr(..., None)`` returns ``None`` forever,
and the dashboard renders a dark hero behind a green suite.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from maxpane_dashboard.data.curator_models import (
    ContributorRow,
    CuratorConfig,
    CuratorState,
    DepositEvent,
    HourBucket,
    LogSweep,
    SettlementRecord,
    WalletState,
)

ADDR = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"

ALL_MODELS = (
    CuratorState,
    CuratorConfig,
    WalletState,
    DepositEvent,
    ContributorRow,
    HourBucket,
    SettlementRecord,
    LogSweep,
)


#: The exact keyword names each producer passes.  This is the interface freeze
#: that matters: a rename anywhere now fails at *collection* in this file, in
#: WP2's client suite and in WP5's manager suite, instead of silently becoming a
#: ``None`` hero.  WP2 and WP5 each import CONSTRUCTOR_KWARGS and assert the
#: same thing against the kwargs their own code passes.
CONSTRUCTOR_KWARGS: dict[type, tuple[str, ...]] = {
    CuratorState: (
        "settled",
        "current_hour",
        "current_hour_total_wei",
        "hour_needed_wei",
        "hour_seconds_left",
        "last_active_hour",
        "last_active_hour_total_wei",
        "early_bps",
        "volume_wei",
        "contributors",
        "tx_count",
        "forced_balance_wei",
        "block_number",
    ),
    CuratorConfig: (
        "launch_time",
        "hourly_threshold_wei",
        "grace_period",
        "hour_duration",
        "min_deposit_wei",
        "min_escalation_wei",
        "credit_cap_wei",
        "first_judged_hour",
        "points_per_eth",
        "deployer",
    ),
    WalletState: (
        "address",
        "points",
        "weight_wei",
        "contributed_wei",
        "tx_count",
        "first_hour",
        "has_joined",
        "required_next_wei",
    ),
    DepositEvent: (
        "contributor",
        "hour",
        "amount_wei",
        "credited_delta_wei",
        "weight_added_wei",
        "new_weight_wei",
        "tx_count",
        "hour_total_wei",
        "early_bps",
        "block_number",
        "tx_hash",
        "log_index",
        "ts",
    ),
    ContributorRow: (
        "address",
        "weight_wei",
        "credit_wei",
        "tx_count",
        "first_hour",
        "first_index",
        "points",
    ),
    HourBucket: ("hour", "volume_wei", "deposits", "judged", "saved_by"),
    SettlementRecord: (
        "settled",
        "block_number",
        "observed_at",
        "settled_hour",
        "settled_at_ts",
        "total_contributors",
        "total_volume_wei",
    ),
    LogSweep: (
        "from_block",
        "to_block",
        "deposits",
        "first_deposits",
        "hour_saved",
        "settled",
        "rescued",
        "launched",
    ),
}


def _all_none_state() -> dict[str, None]:
    return {name: None for name in CONSTRUCTOR_KWARGS[CuratorState]}


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_are_frozen_dataclasses(model) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True


@pytest.mark.parametrize("model", ALL_MODELS)
def test_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    """The whole point of WP0.5.

    Four work packages code against these names in parallel.  This test is what
    turns a rename into a collection error instead of a dark panel.
    """
    assert tuple(f.name for f in dataclasses.fields(model)) == CONSTRUCTOR_KWARGS[model]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_model_constructs_from_its_documented_kwargs(model) -> None:
    """Constructing by keyword — the way every producer does — must not TypeError."""
    assert model(**{name: None for name in CONSTRUCTOR_KWARGS[model]}) is not None


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_are_immutable(model) -> None:
    instance = model(**{name: None for name in CONSTRUCTOR_KWARGS[model]})
    first = CONSTRUCTOR_KWARGS[model][0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, first, 0)


def test_no_model_field_defaults_to_zero() -> None:
    """The house rule, stated structurally: a default of 0 is a sentinel that
    would outlive the outage that produced it."""
    for model in ALL_MODELS:
        for field in dataclasses.fields(model):
            if field.default is not dataclasses.MISSING:
                assert field.default in (None, False, ()), (
                    f"{model.__name__}.{field.name} defaults to {field.default!r}"
                )
            assert field.default_factory is dataclasses.MISSING, (
                f"{model.__name__}.{field.name} has a mutable default factory"
            )


def test_wei_fields_are_named_wei() -> None:
    """Unit discipline: models are wei-native, the flat dict is the
    presentation boundary, and the manager divides exactly once."""
    expected = {
        CuratorState: {
            "current_hour_total_wei",
            "hour_needed_wei",
            "last_active_hour_total_wei",
            "volume_wei",
            "forced_balance_wei",
        },
        CuratorConfig: {
            "hourly_threshold_wei",
            "min_deposit_wei",
            "min_escalation_wei",
            "credit_cap_wei",
        },
        WalletState: {"weight_wei", "contributed_wei", "required_next_wei"},
        DepositEvent: {
            "amount_wei",
            "credited_delta_wei",
            "weight_added_wei",
            "new_weight_wei",
            "hour_total_wei",
        },
        ContributorRow: {"weight_wei", "credit_wei"},
        HourBucket: {"volume_wei"},
        SettlementRecord: {"total_volume_wei"},
    }
    for model, names in expected.items():
        have = {f.name for f in dataclasses.fields(model) if f.name.endswith("_wei")}
        assert have == names, model.__name__


def test_no_eth_denominated_field_reaches_a_model() -> None:
    """The other half of the unit rule: ``*_eth`` belongs to the flat dict.

    ``CuratorConfig.points_per_eth`` is the one exemption and it is not a
    counter-example: ``POINTS_PER_ETH`` is a dimensionless *rate* (1000 points
    per ETH of weight), a chain constant whose name ends in ETH by accident of
    the contract's spelling.  It holds no wei and the manager never divides it.
    """
    allowed = {(CuratorConfig, "points_per_eth")}
    for model in ALL_MODELS:
        for f in dataclasses.fields(model):
            if (model, f.name) in allowed:
                continue
            assert not f.name.endswith("_eth"), (
                f"{model.__name__}.{f.name} is ETH-denominated; models are wei-native"
            )


def test_module_has_no_io_imports() -> None:
    """WP0 ships no I/O at all, and this is the structural proof.

    Asserted against the *import statements*, not a list of spellings someone
    thought of: the module imports the standard library and nothing else, so a
    future ``from .curator_client import ...`` fails here regardless of how it
    is written.
    """
    import re

    module = __import__(
        "maxpane_dashboard.data.curator_models", fromlist=["curator_models"]
    )
    source = inspect.getsource(module)
    imports = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"\s*(from|import)\s", line)
    ]
    assert imports == [
        "from __future__ import annotations",
        "from dataclasses import dataclass",
    ], imports
    for banned in ("httpx", "textual", "requests", "urllib", "socket"):
        assert not re.search(rf"^\s*(from|import)\s+{banned}\b", source, re.MULTILINE)


def test_the_three_legitimate_zeros_are_constructible_and_distinct_from_none() -> None:
    """This contract has zeros that are answers, not failures.

    ``currentHourTotal`` is 0 at every hour boundary; ``ethNeededThisHour`` is 0
    through the whole grace period and again whenever an hour is safe;
    ``creditedDelta`` is 0 for a deposit above the cap.  Each must be storable as
    0 and readable back as 0 -- and each must be storable as None meaning "the
    read failed".  A model that cannot hold both has already lost the
    distinction the whole dashboard is built on.
    """
    zeroed = CuratorState(
        **{**_all_none_state(), "current_hour_total_wei": 0, "hour_needed_wei": 0}
    )
    assert zeroed.current_hour_total_wei == 0
    assert zeroed.hour_needed_wei == 0
    assert CuratorState(**_all_none_state()).current_hour_total_wei is None
    assert CuratorState(**_all_none_state()).hour_needed_wei is None

    # The third zero lives on the event, and it is a real int there: a deposit
    # above the 1000 ETH cap credits nothing but still counts fully toward the
    # hour.  Weight is therefore 0 too, and neither is a failed read.
    capped = DepositEvent(
        contributor=ADDR,
        hour=7,
        amount_wei=1500 * 10**18,
        credited_delta_wei=0,
        weight_added_wei=0,
        new_weight_wei=1000 * 10**18,
        tx_count=2,
        hour_total_wei=1500 * 10**18,
        early_bps=10_000,
        block_number=25_800_000,
        tx_hash="0x" + "ab" * 32,
        log_index=3,
    )
    assert capped.credited_delta_wei == 0
    assert capped.amount_wei > 0


def test_settled_false_is_not_settled_unknown() -> None:
    """``isSettled()`` is a bool.  ``False`` is a live game; ``None`` is a
    failed read, and the phase machine must branch differently on each."""
    alive = CuratorState(**{**_all_none_state(), "settled": False})
    unknown = CuratorState(**_all_none_state())
    assert alive.settled is False
    assert unknown.settled is None
    assert alive.settled is not unknown.settled


def test_first_hour_zero_is_not_the_same_as_never_joined() -> None:
    """The packed-struct off-by-one, made unrepresentable.

    ``firstHourOf()`` returns ``(0, false)`` for a stranger and ``(0, true)``
    for someone who deposited in hour 0.  One field cannot carry both, which is
    why ``has_joined`` exists as a separate bool.
    """
    stranger = WalletState(
        address=ADDR,
        points=None,
        weight_wei=None,
        contributed_wei=None,
        tx_count=None,
        first_hour=0,
        has_joined=False,
        required_next_wei=None,
    )
    founder = dataclasses.replace(stranger, has_joined=True)
    assert stranger.first_hour == founder.first_hour == 0
    assert stranger.has_joined is not founder.has_joined


def test_deposit_event_carries_no_derived_field() -> None:
    """Raw discipline: points, margin and cluster membership are WP3's.

    A ``points`` field here would give the curve two callers and two test
    suites, and the one in the client would be the one nobody mutation-tests.
    """
    names = {f.name for f in dataclasses.fields(DepositEvent)}
    for derived in ("points", "margin_wei", "cluster_id", "is_whale", "rank", "flagged"):
        assert derived not in names


def test_deposit_event_timestamp_is_optional_and_defaults_to_none() -> None:
    """H14: a missing block timestamp renders ``--:--``, never ``00:00``."""
    ev = DepositEvent(
        contributor=ADDR,
        hour=1,
        amount_wei=5 * 10**16,
        credited_delta_wei=5 * 10**16,
        weight_added_wei=99_875_000_000_000_000,
        new_weight_wei=99_875_000_000_000_000,
        tx_count=1,
        hour_total_wei=5 * 10**16,
        early_bps=19_975,
        block_number=25_769_888,
        tx_hash="0x" + "cd" * 32,
        log_index=1,
    )
    assert ev.ts is None


def test_deposit_event_carries_the_dedupe_key() -> None:
    """PRD §4: de-dupe by (tx, log index), or a re-org replay renders every
    deposit twice."""
    names = {f.name for f in dataclasses.fields(DepositEvent)}
    assert {"tx_hash", "log_index"} <= names


def test_contributor_row_points_stay_none_until_the_curve_is_applied() -> None:
    """WP3.6 folds the row; the curve runs afterwards.  A 0 here would render a
    real leaderboard entry as having scored nothing."""
    row = ContributorRow(
        address=ADDR,
        weight_wei=10**18,
        credit_wei=10**18,
        tx_count=1,
        first_hour=0,
        first_index=1,
    )
    assert row.points is None


def test_hour_bucket_separates_judged_from_saved() -> None:
    """H13: the in-progress hour is never judged, and ``saved_by`` is ``None``
    for every hour ``HourSaved`` never fired in -- which so far is all of them."""
    live = HourBucket(hour=2, volume_wei=51 * 10**18, deposits=8, judged=False)
    assert live.judged is False
    assert live.saved_by is None


def test_settlement_record_splits_the_latch_from_the_obituary() -> None:
    """H1: the first three fields come from the ``isSettled()`` *view*
    observation -- the evidence record the manager never re-reads through.  The
    last four are filled from the ``Settled`` log if and when it appears, which
    may be much later or never."""
    latched = SettlementRecord(
        settled=True, block_number=25_900_000, observed_at=1_787_000_400.0
    )
    assert latched.settled is True
    assert latched.settled_hour is None
    assert latched.settled_at_ts is None
    assert latched.total_contributors is None
    assert latched.total_volume_wei is None


def test_log_sweep_groups_default_to_empty_not_missing() -> None:
    sweep = LogSweep(from_block=1, to_block=2, deposits=({"topics": []},))
    assert sweep.first_deposits == () and sweep.settled == ()
    assert sweep.hour_saved == () and sweep.rescued == () and sweep.launched == ()


def test_log_sweep_groups_are_tuples_so_a_none_cannot_hide_in_one() -> None:
    """``()`` means "read, nothing matched" **or** "this one filter failed".

    A frozen tuple cannot hold ``None``, so the per-group failure travels
    out-of-band in the client's ``log_group_failed`` dict and reaches the user
    through the manager's ``degraded`` list.  A sweep where *every* group failed
    returns ``None`` instead of a ``LogSweep``.
    """
    sweep = LogSweep(from_block=1, to_block=2)
    for field in dataclasses.fields(LogSweep):
        if field.name in ("from_block", "to_block"):
            continue
        assert getattr(sweep, field.name) == ()
        assert isinstance(getattr(sweep, field.name), tuple)


def test_no_flat_dict_key_masquerades_as_a_model_field() -> None:
    flat_only = {
        "phase",
        "hour_fed_eth",
        "hour_needed_eth",
        "volume_routed_eth",
        "top_points",
        "forced_eth",
        "you_rank",
        "as_of_hhmm",
        "degraded",
    }
    for model in ALL_MODELS:
        clash = flat_only & {f.name for f in dataclasses.fields(model)}
        assert not clash, f"{model.__name__} carries flat-dict key(s) {clash}"
