"""WP-1 — interface freeze tests for the FWA dashboard contract.

These tests exist to stop the contract drifting while seven wave-2 agents code
against it in parallel. They are cheap, offline and structural on purpose.
"""

import pytest
from pydantic import ValidationError

from maxpane_dashboard.data.fwa_models import (
    FWA_DATA_KEYS,
    FWA_ROW_KEYS,
    FWA_SETTLEMENT_OUTCOMES,
    FWA_WIDGET_SIGNATURES,
    INVERSE_WEIGHT_NUMERATOR,
    CollectionOdds,
    ConfigParam,
    Crown,
    DrawEvent,
    FWASignal,
    FWASnapshot,
    PoolTemp,
    Position,
    PullEV,
    SettlementMix,
)

# Live-ish values from docs/fwa_technical_findings.md §4.2 (listings(56508)).
_BACKING_WEI = 221_000_000_000_000_000_000
_WEIGHT = INVERSE_WEIGHT_NUMERATOR // _BACKING_WEI  # 4524886877828054


def _position(**overrides):
    kwargs = dict(
        listing_id=56508,
        collection="0xb7f7f6c52f2e2fdb1963eab30438024864c313f6",
        depositor="0xb873bdcba0e9e40503a562abfeb4cce80cc33119",
        allocatee=None,
        token_id=1234,
        weight=_WEIGHT,
        backing_wei=_BACKING_WEI,
        fee_share=1,
        fee_debt=6_590_500_784_182_843_196,
        slot=4321,
        allocated_at=0,
        status=1,
    )
    kwargs.update(overrides)
    return Position(**kwargs)


def _all_models():
    """One representative instance of each of the ten models."""
    position = _position()
    odds = CollectionOdds(
        address="0xb7f7f6c52f2e2fdb1963eab30438024864c313f6",
        name="CryptoPunks",
        positions=3,
        weight=_WEIGHT * 3,
        weight_share_pct=0.0,
        backing_wei=137_100_000_000_000_000_000,
        floor_eth=None,
        floor_source="missing",
        eth_per_odds_point=None,
        floor_note="",
    )
    ev = PullEV(
        lower_eth=0.0912,
        best_eth=0.1063,
        fee_eth=0.13683,
        rebate_eth=0.0,
        collections_priced=22,
        collections_total=38,
        weight_priced_pct=31.7,
    )
    crown = Crown(
        listing_id=56283,
        depositor="0x019817ad02a31b990433542097be29d97613e8cb",
        pot_wei=60_242_085_156_350_313,
        seize_wei=243_100_000_000_000_000_000,
        threshold_bps=1000,
        share_bps=100,
        vacant=False,
    )
    temp = PoolTemp(
        seconds_since_last_request=41,
        token_share_bps=0,
        hot_gap=60,
        cold_gap=3600,
        forced_share_bps=-1,
        share_estimated=False,
    )
    param = ConfigParam(
        key=15,
        name="TOP_LISTING_SHARE_BPS",
        value=100,
        block_number=25_592_190,
        is_drift=True,
    )
    mix = SettlementMix(
        outcome="bid_fwa",
        label="Accept bid, paid in $FWA",
        count=38_083,
        share_pct=73.92,
    )
    signal = FWASignal(
        label="POOL TEMP",
        value_str="COLD 41m · surcharge → YOU (100%)",
        indicator="●",
        color="green",
    )
    draw = DrawEvent(
        ts=1_785_870_083,
        block_number=25_612_655,
        tx_hash="0x" + "ab" * 32,
        purchaser="0xabcd000000000000000000000000000000001234",
        collection="0xb7f7f6c52f2e2fdb1963eab30438024864c313f6",
        collection_name="Nakamigos",
        token_id=4471,
        outcome="bid_fwa",
        outcome_label="sold back ($FWA)",
        amount_wei=118_000_000_000_000_000,
    )
    snapshot = FWASnapshot(
        fetched_at=1_785_870_083.5,
        block_number=25_612_655,
        positions=(position,),
        collection_odds=(odds,),
        pull_ev=ev,
        crown=crown,
        pool_temp=temp,
        params=(param,),
        settlement_mix=(mix,),
        draw_events=(draw,),
        pool_temp_signal=signal,
        active_positions=3_867,
        core_balance_wei=2_551_000_000_000_000_000_000,
        acquisition_fee_wei=136_829_134_522_020_108,
        total_weight=31_280_618_816_683_353_089_152,
        weighted_backing_total=3_890_999_999_999_999_999_275_601_332_649_457_427_323,
        invariants_ok=True,
        degraded_sources=("logs",),
    )
    return [position, odds, ev, crown, temp, param, mix, signal, draw, snapshot]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_all_ten_models_construct_from_representative_data():
    models = _all_models()
    assert len(models) == 10
    # sanity: the inverse-weight rule holds for the representative position
    assert models[0].weight == INVERSE_WEIGHT_NUMERATOR // models[0].backing_wei


@pytest.mark.parametrize("index", range(10))
def test_models_are_frozen(index):
    model = _all_models()[index]
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, field, None)


def test_models_reject_undeclared_fields():
    # extra="forbid" is what makes the PullEV band structural rather than a habit
    with pytest.raises(ValidationError):
        _position(surprise_field=1)


def test_snapshot_sequences_are_immutable_tuples():
    snapshot = _all_models()[-1]
    assert isinstance(snapshot.positions, tuple)
    assert isinstance(snapshot.collection_odds, tuple)
    assert isinstance(snapshot.degraded_sources, tuple)


# ---------------------------------------------------------------------------
# The band guard (PRD §3, plan risk R13)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("banned", ["point_eth", "value_eth", "ev_eth"])
def test_pull_ev_has_no_single_confident_number_field(banned):
    assert banned not in PullEV.model_fields
    assert not hasattr(_all_models()[2], banned)
    with pytest.raises(ValidationError):
        PullEV(
            lower_eth=0.0,
            best_eth=0.0,
            fee_eth=0.0,
            rebate_eth=0.0,
            collections_priced=0,
            collections_total=0,
            weight_priced_pct=0.0,
            **{banned: 0.1},
        )


def test_pull_ev_coverage_fields_are_required():
    # a value can never render without the badge, because the badge cannot be omitted
    for required in ("lower_eth", "best_eth", "collections_priced",
                     "collections_total", "weight_priced_pct"):
        assert PullEV.model_fields[required].is_required()


# ---------------------------------------------------------------------------
# Typed traps
# ---------------------------------------------------------------------------


def test_position_backing_wei_rejects_a_float():
    with pytest.raises(ValidationError):
        _position(backing_wei=1.5)
    with pytest.raises(ValidationError):
        # whole-valued floats are rejected too — 1e18 already lost the low bits
        _position(backing_wei=2.21e20)
    with pytest.raises(ValidationError):
        _position(weight=float(_WEIGHT))


def test_pool_temp_forced_share_bps_is_signed():
    assert PoolTemp(seconds_since_last_request=0).forced_share_bps == -1
    dynamic = PoolTemp(seconds_since_last_request=12, forced_share_bps=-1)
    overridden = PoolTemp(seconds_since_last_request=12, forced_share_bps=5000)
    assert dynamic.forced_share_bps == -1
    assert overridden.forced_share_bps == 5000


def test_crown_vacant_is_explicit_not_inferred_from_zero():
    vacant = Crown(listing_id=0)
    assert vacant.vacant is True
    assert vacant.depositor is None
    assert vacant.pot_wei == 0


def test_position_unallocated_is_none_not_the_zero_address():
    assert _position().allocatee is None


# ---------------------------------------------------------------------------
# The flat-dict contract
# ---------------------------------------------------------------------------


def test_data_keys_are_unique_valid_identifiers():
    assert len(FWA_DATA_KEYS) == len(set(FWA_DATA_KEYS))
    for key in FWA_DATA_KEYS:
        assert key.isidentifier(), key
        assert key == key.lower(), key


def test_weighted_backing_total_is_not_a_data_key():
    # rule 4: it is neither wei nor ETH and must never be labelled TVL,
    # so it is structurally unavailable to widgets
    assert "weighted_backing_total" not in FWA_DATA_KEYS
    assert "tvl" not in " ".join(FWA_DATA_KEYS)


def test_widget_signatures_cover_exactly_the_seven_prd_widgets():
    assert set(FWA_WIDGET_SIGNATURES) == {
        "FWAHeroMetrics",
        "FWAOddsBoard",
        "FWASparkline",
        "FWASignals",
        "FWAActivityFeed",
        "FWAChaseBoard",
        "FWASettlementTable",
    }


def test_every_widget_kwarg_is_a_data_key():
    for widget, kwargs in FWA_WIDGET_SIGNATURES.items():
        assert len(kwargs) == len(set(kwargs)), widget
        for kwarg in kwargs:
            assert kwarg in FWA_DATA_KEYS, f"{widget}.update_data({kwarg}=...)"


def test_no_data_key_is_dispatched_to_two_widgets():
    seen: dict[str, str] = {}
    for widget, kwargs in FWA_WIDGET_SIGNATURES.items():
        for kwarg in kwargs:
            assert kwarg not in seen, f"{kwarg} claimed by {seen.get(kwarg)} and {widget}"
            seen[kwarg] = widget


def test_every_availability_flag_is_present():
    for flag in (
        "ev_available",
        "price_available",
        "crown_available",
        "odds_available",
        "spark_available",
        "feed_available",
        "chase_available",
        "settle_available",
    ):
        assert flag in FWA_DATA_KEYS
    # and each one reaches the widget that must render the unavailable state
    dispatched = {k for kwargs in FWA_WIDGET_SIGNATURES.values() for k in kwargs}
    assert {
        "ev_available", "price_available", "crown_available", "odds_available",
        "spark_available", "feed_available", "chase_available", "settle_available",
    } <= dispatched


def test_row_key_payloads_are_declared_and_consistent():
    for payload, keys in FWA_ROW_KEYS.items():
        assert payload in FWA_DATA_KEYS, payload
        assert len(keys) == len(set(keys)), payload
        assert all(k.isidentifier() for k in keys), payload
    # settlement rows must match the SettlementMix model field-for-field
    assert set(FWA_ROW_KEYS["settlement_mix"]) == set(SettlementMix.model_fields)


def test_settlement_outcomes_are_the_five_documented_ones():
    assert FWA_SETTLEMENT_OUTCOMES == (
        "bid_fwa", "bid_eth", "relist", "kept", "forced",
    )


def test_module_imports_no_client_cache_analytics_or_textual():
    import inspect

    from maxpane_dashboard.data import fwa_models

    source = inspect.getsource(fwa_models)
    for banned in ("textual", "httpx", "requests", "fwa_client", "fwa_cache",
                   "fwa_logs", "fwa_market", "fwa_manager", "analytics"):
        assert f"import {banned}" not in source
        assert f"from {banned}" not in source
