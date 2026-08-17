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
                # IDENTITY, not membership.  ``0 in (None, False, ())`` is True
                # -- ``0 == False`` in Python -- so the membership form this
                # test used to be written in could not fail on the one value it
                # exists to catch, and a ``block_number: int | None = 0`` was
                # invisible to the whole repo.  ``== ()`` stays an equality
                # because ``0 == ()`` is False and tuple identity is not
                # guaranteed.
                assert (
                    field.default is None
                    or field.default is False
                    or field.default == ()
                ), f"{model.__name__}.{field.name} defaults to {field.default!r}"
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


# --------------------------------------------------------------------------
# WP0.6 — the flat manager contract
# --------------------------------------------------------------------------

from maxpane_dashboard.data.curator_models import (  # noqa: E402
    CURATOR_ACTIVITY_KINDS,
    CURATOR_DEGRADED_GROUPS,
    CURATOR_KEYS,
    CURATOR_ROW_KEYS,
    CURATOR_SERIES_KEYS,
    CURATOR_SIGNAL_STATES,
    PHASES,
    SIGNAL_ROWS,
)

#: PRD §5's key list, restated independently of the module so the two can
#: actually disagree.  Copying ``CURATOR_KEYS`` in here would make this test
#: compare a constant with itself.
EXPECTED_KEYS = {
    # phase machine
    "phase",
    "settled",
    "settled_hour",
    "settled_at_ts",
    "settled_observed_at",
    "lived_desc",
    # clock
    "current_hour",
    "hour_fed_eth",
    "hour_needed_eth",
    "hour_seconds_left",
    "grace_seconds_left",
    "grace_ends_utc",
    # config the widgets render rather than branch on
    "hourly_threshold_eth",
    "first_judged_hour",
    # curve
    "early_multiplier_x",
    "points_per_eth_now",
    "survival_streak_hours",
    "closest_call_margin_eth",
    "closest_call_hour",
    # list
    "contributors_total",
    "deposits_total",
    "volume_routed_eth",
    "top_points",
    # signals
    "last_saved_hour",
    "last_saved_wallet",
    "last_saved_ens",
    "last_saved_age_s",
    "whale_amount_eth",
    "whale_wallet",
    "whale_ens",
    "whale_age_s",
    "clusters_count",
    "flagged_points_share_pct",
    "forced_eth",
    "rescued_total_eth",
    "sig_settled_state",
    "sig_at_risk_state",
    # YOU
    "you_rank",
    "you_points",
    "you_credit_eth",
    "you_required_next_eth",
    "you_marginal_points",
    # The `y` wallet view (PRD §13 A8) — folded from payloads already fetched.
    "you_weight_eth",
    "you_tx_count",
    "you_first_hour",
    "you_joined_utc",
    "you_weight_share_pct",
    "you_ladder_rows",
    "you_next_rank",
    "you_next_rank_needs_eth",
    "you_next_send_passes",
    "you_ens",
    # rows
    "leaderboard_rows",
    "activity_rows",
    "closest_call_rows",
    "cluster_rows",
    "volume_series",
    "contributors_series",
    # The linked-wallet analysis view (`f`), added by the sybil expansion
    # (docs/curator_sybil_PRD.md §7).  All eleven are manager-adapter-produced
    # from the detached B+C sweep's last-good, never emitted by build_signals.
    "operator_rows",
    "segment_rows",
    "clean_list_rows",
    "operators_count",
    "clean_points",
    "clean_contributors",
    "analysis_as_of_hhmm",
    "you_linked_state",
    "you_linked_reasons",
    "you_linked_group_size",
    "you_clean_rank",
    # health
    "degraded",
    "as_of_hhmm",
    "as_of",
}


def test_curator_keys_is_exactly_the_prd_contract() -> None:
    assert set(CURATOR_KEYS) == EXPECTED_KEYS
    assert len(CURATOR_KEYS) == len(set(CURATOR_KEYS))
    assert isinstance(CURATOR_KEYS, tuple)


def test_phases_are_the_three_the_prd_names() -> None:
    assert PHASES == ("grace", "judged", "settled")


def test_no_wei_key_leaks_into_the_flat_dict() -> None:
    """The manager divides exactly once; the dict is the presentation boundary."""
    assert not [k for k in CURATOR_KEYS if k.endswith("_wei")]


def test_row_key_sets_match_the_prd() -> None:
    assert CURATOR_ROW_KEYS["leaderboard_rows"] == (
        "rank",
        "address",
        "points",
        "credit_eth",
        "tx_count",
        "flagged",
        # Verified reverse ENS for `address` (PRD §13 A9).  Rendered inside the
        # address cell's own width, so a name can never widen the table.
        "name",
        # The confidence-graded link marker (sybil PRD §6), appended so every
        # shipped column keeps its position and `flagged` keeps its type.
        "link_conf",
    )
    assert CURATOR_ROW_KEYS["activity_rows"] == (
        "ts",
        "address",
        "amount_eth",
        "credited_eth",
        "new_weight",
        "tx_count",
        "hour",
        "kind",
        "tx_hash",
        "log_index",
        "name",
    )
    assert CURATOR_ROW_KEYS["closest_call_rows"] == (
        "hour",
        "volume_eth",
        "margin_eth",
        "savior",
        "savior_name",
    )
    assert CURATOR_ROW_KEYS["cluster_rows"] == (
        "size",
        "amount_eth",
        "first_block",
        "last_block",
        "points",
        "points_share_pct",
    )
    assert set(CURATOR_ROW_KEYS) <= set(CURATOR_KEYS)


def test_the_two_series_are_named_separately_from_the_row_payloads() -> None:
    """``volume_series`` and ``contributors_series`` are ``[ts, value]`` pairs
    that load through ``data/series_points.coerce_points`` -- not lists of
    dicts.  Giving them a column tuple in ``CURATOR_ROW_KEYS`` would tell a
    widget to index a 2-tuple by name, so they get their own name instead."""
    assert CURATOR_SERIES_KEYS == ("volume_series", "contributors_series")
    assert set(CURATOR_SERIES_KEYS) <= set(CURATOR_KEYS)
    assert set(CURATOR_SERIES_KEYS).isdisjoint(CURATOR_ROW_KEYS)


def test_every_list_payload_has_either_a_row_shape_or_a_series_declaration() -> None:
    """The ten list payloads, all accounted for, none twice.

    Six from PRD §5; the seventh is ``you_ladder_rows``, added with the `y``
    wallet view (PRD §13 A8); the last three are the analysis view's panels
    (sybil PRD §7).

    Enumerated rather than counted.  The count this test used to carry was a
    literal ``7``, and the honest way to grow it is to name the payloads that
    exist — a bumped number says a payload was added, this says *which*, and it
    still fails if one is added without a shape.
    """
    listish = {k for k in CURATOR_KEYS if k.endswith("_rows") or k.endswith("_series")}
    assert listish == set(CURATOR_ROW_KEYS) | set(CURATOR_SERIES_KEYS)
    assert listish == {
        "leaderboard_rows",
        "activity_rows",
        "closest_call_rows",
        "cluster_rows",
        "you_ladder_rows",
        "operator_rows",
        "segment_rows",
        "clean_list_rows",
        "volume_series",
        "contributors_series",
    }


def test_activity_rows_carry_the_dedupe_key() -> None:
    """PRD §4: de-dupe by (tx, log index).  Both must be in the row shape or the
    widget cannot do it, and a re-org replay renders every deposit twice."""
    assert {"tx_hash", "log_index"} <= set(CURATOR_ROW_KEYS["activity_rows"])


def test_no_row_shape_is_wei_denominated() -> None:
    """Rows are rendered directly; the manager already divided."""
    for name, cols in CURATOR_ROW_KEYS.items():
        assert not [c for c in cols if c.endswith("_wei")], name


def test_the_volume_column_is_never_called_tvl_or_locked() -> None:
    """H4: every wei is refunded in-transaction, so volume is gas-priced, not
    capital-priced.  A column named ``tvl`` would be a lie in the schema
    itself, before any copy is written."""
    banned = {"tvl", "locked", "at_risk", "capital", "balance", "deposited_eth"}
    for name, cols in CURATOR_ROW_KEYS.items():
        assert banned.isdisjoint(cols), name
    assert banned.isdisjoint(CURATOR_KEYS)


def test_the_signal_rows_are_the_seven_the_rail_renders() -> None:
    """PRD §4's rail, in order:
    ``SETTLED · HOUR AT RISK · HOUR SAVED · WHALE · FARM · FORCED ETH · YOU``.

    This tuple used to end in ``rescued``, which no spec the widget author reads
    has ever contained -- PRD §4, wp4.md:231 and wp6.md:300 all end in YOU.  An
    eight-label rail built from a seven-label test is a row that never renders.
    """
    assert SIGNAL_ROWS == (
        "settled",
        "at_risk",
        "hour_saved",
        "whale",
        "clusters",
        "forced_eth",
        "you",
    )
    assert len(set(SIGNAL_ROWS)) == len(SIGNAL_ROWS)


def test_the_rail_has_no_rescued_row_but_rescued_is_still_a_key() -> None:
    """``rescued_total_eth`` renders *inside* the FORCED ETH row.

    Forced in, swept out: one anomaly with two numbers.  Spending a row on it
    would make an eighth in a rail that already loses its last row first, and
    ``Rescued`` has never fired -- so the dedicated row would be empty in every
    state anyone can currently observe.
    """
    assert "rescued" not in SIGNAL_ROWS
    assert "rescued_total_eth" in CURATOR_KEYS
    assert "forced_eth" in SIGNAL_ROWS and "forced_eth" in CURATOR_KEYS


def test_the_you_row_is_last_and_has_keys_to_render() -> None:
    """The FWA coverage-badge position.  A rail in a fixed-height column loses
    its last row first, and the last row is the reader's own standing -- so the
    row is both the most personal and the most likely to vanish."""
    assert SIGNAL_ROWS[-1] == "you"
    assert {
        "you_rank",
        "you_points",
        "you_credit_eth",
        "you_required_next_eth",
        "you_marginal_points",
    } <= set(CURATOR_KEYS)


def test_the_hourly_threshold_is_a_key_because_it_cannot_be_derived() -> None:
    """CLAUDE.md hard constraint 4: read it live, never hardcode the documented
    5.00.

    Two widgets render the number -- the hero clock's ``fed X.XX/5.00 ETH`` and
    the volume sparkline's labelled survival bar -- and it is **not** recoverable
    from the two keys beside it.  ``ethNeededThisHour()`` (source.sol:547)
    returns 0 for the whole grace period and again whenever a judged hour is
    already safe, so ``hour_fed_eth + hour_needed_eth`` equals the threshold
    only while an hour is short.  The counter-example is pinned against the
    committed batch round in
    ``test_curator_captures.py::test_the_hourly_threshold_is_not_recoverable_from_the_two_keys_beside_it``
    (734.61 ETH fed, 0 needed, a 5 ETH bar).
    """
    assert "hourly_threshold_eth" in CURATOR_KEYS
    assert {"hour_fed_eth", "hour_needed_eth"} <= set(CURATOR_KEYS)
    assert not [k for k in CURATOR_KEYS if k.endswith("_wei")]


def test_the_first_judged_hour_is_a_key_because_the_widgets_print_it() -> None:
    """``n/a until hour 24`` (HOUR AT RISK during grace) and the closest-calls
    empty state both print the number.  ``gracePeriod // hourDuration`` gives it,
    but neither operand is in the flat dict either -- so with no key the widget
    types the 24, which is the constraint-4 violation the ``once`` tier exists to
    prevent."""
    assert "first_judged_hour" in CURATOR_KEYS
    assert "grace_period" not in CURATOR_KEYS
    assert "hour_duration" not in CURATOR_KEYS


def test_the_activity_kind_vocabulary_is_frozen_not_remembered() -> None:
    """The ``dev``/``ops`` lesson (CLAUDE.md), applied one wave early.

    ``CURATOR_ROW_KEYS`` freezes that a row has a ``kind``; this freezes what
    goes in it.  The widget sizes a fixed-width cell from this tuple in wave 2
    and the producer fills it in wave 3 -- a wave apart, with no shared name,
    a producer emitting ``first_deposit`` cuts the cell mid-word and both suites
    stay green.
    """
    assert CURATOR_ACTIVITY_KINDS == ("deposit", "joined", "saved")
    assert "kind" in CURATOR_ROW_KEYS["activity_rows"]
    assert len(set(CURATOR_ACTIVITY_KINDS)) == len(CURATOR_ACTIVITY_KINDS)
    # What the consumer actually sizes to.  Stated here so a widening of the
    # vocabulary shows up as a column cost, in this file, at review time.
    assert max(len(k) for k in CURATOR_ACTIVITY_KINDS) == 7


def test_the_signal_state_vocabulary_is_frozen_and_excludes_none() -> None:
    """``None`` is the fourth state and it is deliberately NOT in the tuple:
    it means "the analytics layer could not judge", which renders the
    unavailable state, never a quiet ``ok``."""
    assert CURATOR_SIGNAL_STATES == ("ok", "watch", "fired")
    assert None not in CURATOR_SIGNAL_STATES
    assert {"sig_settled_state", "sig_at_risk_state"} <= set(CURATOR_KEYS)


def test_the_degraded_group_vocabulary_is_frozen() -> None:
    """PRD §5: ``degraded`` group names ⊆ {state, logs, wallet}.  The title bar
    renders them verbatim, so an unlisted spelling reaches the user as-is."""
    assert set(CURATOR_DEGRADED_GROUPS) == {"state", "logs", "wallet"}
    assert "degraded" in CURATOR_KEYS


def test_the_two_judgement_rows_have_an_explicit_state_key() -> None:
    """``sig_settled_state`` and ``sig_at_risk_state`` are colours, not numbers.

    Every other rail row is rendered from an observation the manager already
    emits; these two are the ones where the analytics layer has to decide, so
    they need their own keys rather than being re-derived in the widget.
    """
    assert "sig_settled_state" in CURATOR_KEYS
    assert "sig_at_risk_state" in CURATOR_KEYS


def test_the_settlement_evidence_stamp_is_in_the_contract() -> None:
    """H1: under a full outage after settlement was observed, the dashboard
    still renders SETTLED -- the outage degrades the freshness marker, never
    the phase.  ``settled_observed_at`` is what the marker is drawn from, and
    it is distinct from ``settled_at_ts`` (the log's own word) and from
    ``as_of`` (this refresh)."""
    assert {"settled_observed_at", "settled_at_ts", "as_of"} <= set(CURATOR_KEYS)


def test_signal_output_keys_are_a_subset_of_curator_keys() -> None:
    """The only place the two frozen key surfaces are compared.

    Skips until ``analytics/curator_signals.py`` lands; a skip here is the
    intended state, not an outstanding failure.  WP0.8 records the deferred
    bite-proof: rename one entry of ``SIGNAL_OUTPUT_KEYS``, run ``-k subset -v``
    -> FAILS naming the key; restore -> green (**not** skipped).  If it still
    skips, the ``importorskip`` path is wrong and the guard has been dead the
    whole time.
    """
    sig = pytest.importorskip("maxpane_dashboard.analytics.curator_signals")
    missing = sorted(set(sig.SIGNAL_OUTPUT_KEYS) - set(CURATOR_KEYS))
    assert not missing, f"signal keys absent from CURATOR_KEYS: {missing}"


# ==========================================================================
# WP0 (sybil expansion, 2026-08-17) — the analysis surface
# ==========================================================================
#
# The keys the sybil / fan-out build adds.  Written out literally here rather
# than imported from anywhere: this file is the independent restatement, and a
# shared constant would let one edit move both sides at once.


def test_curator_keys_gained_exactly_the_analysis_surface() -> None:
    """The new keys are present, and no shipped key was removed."""
    new = {
        "operator_rows", "segment_rows", "clean_list_rows", "operators_count",
        "clean_points", "clean_contributors", "analysis_as_of_hhmm",
        "you_linked_state", "you_linked_reasons", "you_linked_group_size",
        "you_clean_rank",
    }
    assert new <= set(CURATOR_KEYS)
    assert "clean_list_export_path" not in CURATOR_KEYS   # screen-owned (plan §6.1)
    assert len(CURATOR_KEYS) == len(set(CURATOR_KEYS))    # still no duplicate
    # `flagged_points_share_pct` is REUSED, not re-added (PRD §7, plan §6.2).
    assert "flagged_points_share_pct" in CURATOR_KEYS
    assert "linked_points_share_pct" not in CURATOR_KEYS


def test_the_new_analysis_keys_are_not_in_the_signal_surface() -> None:
    """They are manager-adapter-produced (the ENS-merge precedent), NOT emitted
    by build_signals -- so analytics/curator_signals.py stays exactly as shipped
    and its forbidden-word source scan is never touched.  Guarded with
    importorskip so WP0 is green before the analytics module is read."""
    sig = pytest.importorskip("maxpane_dashboard.analytics.curator_signals")
    analysis = {
        "operator_rows", "segment_rows", "clean_list_rows", "operators_count",
        "clean_points", "clean_contributors", "analysis_as_of_hhmm",
        "you_linked_state", "you_linked_reasons", "you_linked_group_size",
        "you_clean_rank",
    }
    assert analysis.isdisjoint(set(sig.SIGNAL_OUTPUT_KEYS))
    # The module that must not learn the word: it fills `flagged` (the Tier-A
    # bool) and nothing graded.  `link_conf` is the manager's merge.
    assert "link_conf" not in set(sig.SIGNAL_OUTPUT_KEYS)


def test_the_new_row_shapes_are_frozen() -> None:
    assert CURATOR_ROW_KEYS["operator_rows"] == (
        "size", "reasons", "points", "points_share_pct", "sqrt_subsidy_x", "conf")
    assert CURATOR_ROW_KEYS["segment_rows"] == (
        "label", "contributors", "points_share_pct", "detail")
    assert CURATOR_ROW_KEYS["clean_list_rows"] == (
        "clean_rank", "address", "points", "credit_eth", "name")
    assert set(CURATOR_ROW_KEYS) <= set(CURATOR_KEYS)


def test_the_leaderboard_gained_a_confidence_grade_without_dropping_the_bool() -> None:
    """PRD §6: the flag upgrades to graded.  `flagged` (Tier-A bool) STAYS so
    curator_signals.py is untouched; `link_conf` is the additive graded grade."""
    lb = CURATOR_ROW_KEYS["leaderboard_rows"]
    assert "flagged" in lb and "link_conf" in lb
    # Additive means *appended*: every shipped column keeps its position, so a
    # widget that indexes the tuple rather than the dict is not resequenced.
    assert lb[:-1] == (
        "rank", "address", "points", "credit_eth", "tx_count", "flagged", "name"
    )
    assert lb[-1] == "link_conf"


def test_the_analysis_freshness_marker_is_its_own_key() -> None:
    """The B+C sweep is detached and long-TTL, so its last-good is minutes or
    hours older than the fast tier's.  Rendering both behind one `as_of_hhmm`
    would present a stale analysis as live -- CLAUDE.md's "never a stale number
    presented as live".  `analysis_as_of_hhmm` is `str | None`; None is "the
    sweep has not published yet", which the three panels render as their own
    unavailable state, never as "analyzed, nothing linked"."""
    assert "analysis_as_of_hhmm" in CURATOR_KEYS
    assert "as_of_hhmm" in CURATOR_KEYS
    assert "analysis_as_of" not in CURATOR_KEYS  # one marker, not two clocks


def test_the_analysed_zero_is_representable_separately_from_the_failure() -> None:
    """The FARM-row defect, designed out.

    `operators_count == 0` is "analyzed, nothing linked" -- a real answer.
    `operators_count is None` is "could not analyze".  Both must exist as top
    level keys or the widget cannot tell them apart, and it renders confident
    and green through an outage.  `clean_points` / `clean_contributors` carry
    the same distinction for the CLEANED LIST panel, and `you_linked_reasons`
    carries it for the wallet line: `[]` is analyzed-and-clean, and the
    unknown case is `you_linked_state is None`.
    """
    for key in ("operators_count", "clean_points", "clean_contributors",
                "you_linked_group_size", "you_clean_rank"):
        assert key in CURATOR_KEYS
    assert "you_linked_state" in CURATOR_KEYS
    assert "you_linked_reasons" in CURATOR_KEYS


def test_no_new_key_is_wei_denominated_or_named_after_capital() -> None:
    """The two house rules the new surface has to keep: the manager divided
    once at the boundary, and no wei this contract ever saw was capital."""
    new = {
        "operator_rows", "segment_rows", "clean_list_rows", "operators_count",
        "clean_points", "clean_contributors", "analysis_as_of_hhmm",
        "you_linked_state", "you_linked_reasons", "you_linked_group_size",
        "you_clean_rank",
    }
    assert not [k for k in new if k.endswith("_wei")]
    banned = {"tvl", "locked", "at_risk", "capital", "balance", "deposited_eth"}
    assert banned.isdisjoint(new)
    for name in ("operator_rows", "segment_rows", "clean_list_rows"):
        assert not [c for c in CURATOR_ROW_KEYS[name] if c.endswith("_wei")], name
        assert banned.isdisjoint(CURATOR_ROW_KEYS[name]), name


def test_the_analysis_row_shapes_carry_no_accusatory_column_name() -> None:
    """PRD §2/§8: pattern-language only, and the schema is written before any
    copy is.  A column called `sybil_score` would put the word on the screen by
    way of a DataTable header long before a widget author got a say.

    `sqrt_subsidy_x` is the honest name for the 44.6x number: it is what the
    sqrt curve pays for splitting one bankroll across k wallets, a property of
    the curve rather than an accusation about a person.
    """
    banned = {"sybil", "cheat", "fraud", "attack", "abuse", "wash", "farm", "bot"}
    for name in ("operator_rows", "segment_rows", "clean_list_rows"):
        for column in CURATOR_ROW_KEYS[name]:
            assert not (banned & set(column.split("_"))), f"{name}.{column}"
    for key in CURATOR_KEYS:
        assert not (banned & set(key.split("_"))), key


# ==========================================================================
# WP0.5 — the routing table (the screen-dispatch contract)
# ==========================================================================
#
# Which widget renders each new key (implementation plan §3.3).  It lives HERE,
# in the test file, and not in production, for one reason: `screens/curator.py`
# owns `WIDGET_SIGNATURES` and that file is WP4's.  WP0 may not edit it.  But
# WP4 (which wires the dispatch) and WP5 (which writes two of the widgets) are
# in different waves and must not have to talk, so the map they both code
# against is frozen here and both import it.
#
# Values are TUPLES because two keys reach more than one widget:
# `analysis_as_of_hhmm` stamps all three analysis panels (each degrades
# independently, so each prints its own marker), and `you_clean_rank` is read
# by the CLEANED LIST panel *and* by the wallet-standing line, which prints it
# beside the raw rank ("#412 raw, #47 clean").
#
# `leaderboard_rows["link_conf"]` is deliberately absent: it is a row sub-key,
# not a top-level key, so it needs no dispatch entry -- `CuratorLeaderboard`
# already receives `leaderboard_rows`.

#: The three panels WP4 creates for `MODE_ANALYSIS`.
WP4_ANALYSIS_WIDGETS = ("CuratorOperators", "CuratorSegments", "CuratorCleanList")

#: The shipped widgets the analysis keys also reach.  Both exist today.
WP5_EXISTING_WIDGETS = ("CuratorWalletStanding", "CuratorLeaderboard")

ANALYSIS_KEY_ROUTING: dict[str, tuple[str, ...]] = {
    # ---- OPERATORS -------------------------------------------------------
    "operator_rows": ("CuratorOperators",),
    "operators_count": ("CuratorOperators",),
    # Already a shipped key, re-routed rather than re-added (PRD §7).  It
    # currently feeds the FARM rail row from Tier A; WHICH producer wins once
    # the library's stronger number exists is WP3's decision (plan §6.2), and
    # either way the OPERATORS panel is where the analysis view renders it.
    "flagged_points_share_pct": ("CuratorOperators",),
    # ---- SEGMENTS --------------------------------------------------------
    "segment_rows": ("CuratorSegments",),
    # ---- CLEANED LIST ----------------------------------------------------
    "clean_list_rows": ("CuratorCleanList",),
    "clean_points": ("CuratorCleanList",),
    "clean_contributors": ("CuratorCleanList",),
    # ---- two keys, more than one home ------------------------------------
    "analysis_as_of_hhmm": WP4_ANALYSIS_WIDGETS,
    "you_clean_rank": ("CuratorCleanList", "CuratorWalletStanding"),
    # ---- the `y` view's linked line (WP5 renders, WP4 wires) -------------
    "you_linked_state": ("CuratorWalletStanding",),
    "you_linked_reasons": ("CuratorWalletStanding",),
    "you_linked_group_size": ("CuratorWalletStanding",),
}


def test_every_new_key_has_a_home_widget() -> None:
    """Totality: the screen's dispatch test will require CURATOR_KEYS - dispatched
    - META_KEYS == {}.  Each new top-level key must therefore reach a widget.
    analysis_as_of_hhmm reaches all three analysis panels."""
    homed = set(ANALYSIS_KEY_ROUTING)
    new = {k for k in CURATOR_KEYS if k in {
        "operator_rows","segment_rows","clean_list_rows","operators_count",
        "clean_points","clean_contributors","analysis_as_of_hhmm",
        "you_linked_state","you_linked_reasons","you_linked_group_size","you_clean_rank"}}
    assert new <= homed


def test_the_routing_table_only_routes_keys_that_exist() -> None:
    """The other direction.  A key routed here but absent from ``CURATOR_KEYS``
    is a widget WP4 would wire to a payload entry the manager never builds --
    a kwarg that is ``None`` forever and a panel that is dark behind a green
    suite."""
    assert set(ANALYSIS_KEY_ROUTING) <= set(CURATOR_KEYS)


def test_every_route_is_a_tuple_of_widget_class_names() -> None:
    """Tuples, not bare strings, and pinned as such.

    Two of the twelve routes have more than one destination, and a ``str``
    value would iterate as characters -- a bug that reads as a widget called
    ``C``.  Making *every* value a tuple is what stops WP4 writing the
    single-destination case one way and the multi-destination case another.
    """
    for key, widgets in ANALYSIS_KEY_ROUTING.items():
        assert isinstance(widgets, tuple), key
        assert widgets, f"{key} routes nowhere"
        assert len(set(widgets)) == len(widgets), key
        for name in widgets:
            assert isinstance(name, str) and name.startswith("Curator"), (key, name)


def test_the_routed_widgets_are_the_five_the_plan_names() -> None:
    """Three panels WP4 creates plus two shipped widgets WP5 extends -- and no
    sixth, which would be a widget nobody has been told to write."""
    routed = {name for names in ANALYSIS_KEY_ROUTING.values() for name in names}
    assert routed == set(WP4_ANALYSIS_WIDGETS) | {"CuratorWalletStanding"}
    # `CuratorLeaderboard` is in WP5_EXISTING_WIDGETS but not in the routing
    # table on purpose: it renders `link_conf`, which is a sub-key of a row
    # payload it already receives, so it needs no new dispatch entry.
    assert "CuratorLeaderboard" not in routed
    assert "link_conf" not in CURATOR_KEYS
    assert "link_conf" in CURATOR_ROW_KEYS["leaderboard_rows"]


def test_the_two_shipped_widgets_the_table_names_really_exist() -> None:
    """A typo in either name would only surface in WP4's wave, in a file WP0
    cannot see.  They are importable today, so it can surface now."""
    from maxpane_dashboard.widgets.curator import leaderboard, wallet

    for module, name in ((wallet, "CuratorWalletStanding"),
                         (leaderboard, "CuratorLeaderboard")):
        assert hasattr(module, name), name
    assert set(WP5_EXISTING_WIDGETS) == {"CuratorWalletStanding", "CuratorLeaderboard"}


def test_each_analysis_panel_gets_its_own_freshness_marker() -> None:
    """PRD §5: "each degrades independently, each shows `as of HH:MM`".  All
    three therefore route `analysis_as_of_hhmm`; a single shared header would
    make one panel's outage invisible behind another panel's success."""
    assert ANALYSIS_KEY_ROUTING["analysis_as_of_hhmm"] == WP4_ANALYSIS_WIDGETS
    assert len(WP4_ANALYSIS_WIDGETS) == 3
