"""Interface freeze for the surf data layer.

These are cheap structural tests whose only job is to stop the contract
drifting while later work packages code against it in parallel.
"""

from __future__ import annotations

import dataclasses

import pytest

from maxpane_dashboard.data.surf_models import (
    ChainState,
    ChannelTx,
    DevTx,
    LaunchpadCoin,
    LaunchpadState,
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
    PoolV4State,
)

ALL_MODELS = (
    NonceSet,
    ChainState,
    ChannelTx,
    DevTx,
    MarketSnapshot,
    LogWindow,
    NftStats,
    PoolV4State,
    LaunchpadCoin,
    LaunchpadState,
)


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_are_frozen_dataclasses(model) -> None:
    assert dataclasses.is_dataclass(model)
    assert model.__dataclass_params__.frozen is True


def test_nonce_set_accepts_partial_failure() -> None:
    """A batched read where one call failed is None for that leg, not 0."""
    ns = NonceSet(announce=14, dev=None, ops=38)
    assert ns.announce == 14
    assert ns.dev is None
    assert ns.ops == 38
    assert ns.block_number is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        ns.dev = 0  # type: ignore[misc]


#: The exact keyword names each producer passes.  This is the interface freeze that
#: matters: a rename anywhere now fails at *collection* in this file, in WP1's client
#: suite and in WP4's manager suite, instead of silently becoming a ``None`` hero.
#: WP1 and WP4 each import CONSTRUCTOR_KWARGS and assert the same thing against the
#: kwargs their own code passes — see WP1.2 and WP4.7.
CONSTRUCTOR_KWARGS: dict[type, tuple[str, ...]] = {
    NonceSet: ("announce", "dev", "ops", "block_number"),
    ChainState: (
        "lp_liquidity", "lp_token0", "lp_token1", "lp_fee",
        "lp_tokens_owed0_wei", "lp_tokens_owed1_wei", "lp_imd_wei",
        "lp_weth_wei", "lp_owner", "identity_allowed", "imd_supply_wei",
        "sqrt_price_x96", "pool_tick", "imd_name", "imd_symbol",
        "block_number", "lp_state", "lp_position_count",
    ),
    ChannelTx: (
        "tx_hash", "ts", "nonce", "from_addr", "to_addr", "value_wei",
        "input_hex", "method",
    ),
    DevTx: (
        "tx_hash", "ts", "wallet_label", "from_addr", "to_addr", "counterparty",
        "counterparty_label", "value_wei", "method", "kind", "created_contract",
    ),
    MarketSnapshot: (
        "imd_price_usd", "imd_price_usd_gecko", "imd_change_24h_pct",
        "imd_vol_24h_usd", "pool_liquidity_usd", "pool_imd", "pool_weth",
        "fp_price_usd", "fdv_usd", "eth_usd", "indexer_name", "indexer_symbol",
        "sources_agree", "legacy_pool_liquidity_usd",
    ),
    LogWindow: (
        "from_block", "to_block", "bridge_mints", "identity_updates",
        "v4_initializes", "seaport_sales",
    ),
    NftStats: (
        "holders", "total_supply", "transfers_total", "dev_holdings",
        "transfers_24h", "written", "floor_eth",
    ),
    PoolV4State: (
        "pool_id", "sqrt_price_x96", "tick", "lp_fee", "liquidity",
        "pool_id_source",
    ),
    LaunchpadCoin: (
        "ticker", "name", "creator", "age_s", "price_eth", "change_1h_pct",
        "swaps_1h", "imd_burned",
    ),
    LaunchpadState: (
        "coin_count", "imd_to_burn_wei", "total_real_imd_wei", "burn_fee_bps",
        "creator_fee_bps", "creator_eth_owed_wei", "executor_balance_wei",
        "min_bridge_wei", "coins", "swap_count", "trader_count",
        "burned_total_wei", "swaps_by_coin",
    ),
}


@pytest.mark.parametrize("model", ALL_MODELS)
def test_field_names_are_exactly_the_frozen_vocabulary(model) -> None:
    """The whole point of WP0.4.

    Three work packages code against these names in parallel.  An earlier draft of
    this plan had ChainState spelled three different ways across WP0/WP1/WP4 — the
    constructor calls would have raised TypeError and the reads would have returned
    None for the entire hero.  This test is what makes that a collection error.
    """
    assert tuple(f.name for f in dataclasses.fields(model)) == CONSTRUCTOR_KWARGS[model]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_model_constructs_from_its_documented_kwargs(model) -> None:
    """Constructing by keyword — the way every producer does — must not TypeError."""
    assert model(**{name: None for name in CONSTRUCTOR_KWARGS[model]}) is not None


def test_chain_state_all_none_is_constructible() -> None:
    """Total outage must produce a well-formed all-None state, never zeros."""
    cs = ChainState(
        lp_liquidity=None,
        lp_token0=None,
        lp_token1=None,
        lp_fee=None,
        lp_tokens_owed0_wei=None,
        lp_tokens_owed1_wei=None,
        lp_imd_wei=None,
        lp_weth_wei=None,
        lp_owner=None,
        identity_allowed=None,
        imd_supply_wei=None,
        sqrt_price_x96=None,
        pool_tick=None,
        imd_name=None,
        imd_symbol=None,
    )
    assert all(getattr(cs, f.name) is None for f in dataclasses.fields(cs))


def test_no_flat_dict_key_masquerades_as_a_model_field() -> None:
    """The reverse of the drift that produced this test.

    ``lp_imd``/``imd_supply``/``gate_open``/``value_eth``/``block`` are *flat-dict*
    keys.  WP4 must map to them from the wei-native model fields, and a getattr for
    the flat name would quietly yield the default forever.
    """
    flat_only = {
        "lp_imd", "lp_weth", "imd_supply", "gate_open", "value_eth", "block",
        "counterparty_known", "identity_writes", "floor",
    }
    for model in ALL_MODELS:
        clash = flat_only & {f.name for f in dataclasses.fields(model)}
        assert not clash, f"{model.__name__} carries flat-dict key(s) {clash}"


def test_no_model_field_defaults_to_zero() -> None:
    """The house rule, stated structurally: a default of 0 is a sentinel that
    would outlive the outage that produced it."""
    for model in ALL_MODELS:
        for field in dataclasses.fields(model):
            if field.default is not dataclasses.MISSING:
                assert field.default in (None, False, ()), (
                    f"{model.__name__}.{field.name} defaults to {field.default!r}"
                )


def test_wei_fields_are_named_wei() -> None:
    """Unit discipline, mirrored from fwa_models: models are wei-native and the
    flat dict is the presentation boundary."""
    for name in ("imd_supply_wei", "lp_imd_wei", "lp_weth_wei",
                 "lp_tokens_owed0_wei", "lp_tokens_owed1_wei"):
        assert name in {f.name for f in dataclasses.fields(ChainState)}
    assert "value_wei" in {f.name for f in dataclasses.fields(ChannelTx)}
    assert "value_wei" in {f.name for f in dataclasses.fields(DevTx)}


def test_nft_floor_is_pinned_to_none() -> None:
    """v1 has no keyless floor source.  The field exists so the widget can
    render the explicit unavailable state; it must not become a number."""
    stats = NftStats(
        holders=667,
        total_supply=2000,
        transfers_total=7411,
        dev_holdings=3,
    )
    assert stats.floor_eth is None
    assert stats.transfers_24h is None   # the rate, not the lifetime counter
    assert stats.written is None         # WP1.8 fills it; the default is the
                                         # degraded state, not "no producer"


def test_nft_lifetime_and_daily_transfers_are_separate_fields() -> None:
    """Blockscout serves a lifetime counter; the PRD asks for a daily rate.

    Holding both on one field is how 7,411 gets rendered as "7,411/day".  The
    derivation is WP1.8's ``_count_transfers_24h()``; when it cannot reach the
    24 h edge inside its page budget it answers ``None`` and the widget renders
    the unavailable state rather than a lower bound.
    """
    names = {f.name for f in dataclasses.fields(NftStats)}
    assert {"transfers_total", "transfers_24h"} <= names


def test_log_window_groups_default_to_empty_not_missing() -> None:
    """``()`` is the only empty a group can carry.

    It means the window was read and nothing happened in it, *or* that this one
    filter failed — the tuple cannot hold ``None``, so the failure travels in
    the manager's ``degraded`` list instead.  A window where *every* group
    failed is a ``None`` returned instead of a ``LogWindow``: the client never
    hands back a half-real window.
    """
    window = LogWindow(from_block=1, to_block=2, bridge_mints=({"ts": 1.0},))
    assert window.bridge_mints == ({"ts": 1.0},)
    assert window.identity_updates == ()
    assert window.v4_initializes == ()
    assert window.seaport_sales == ()


def test_channel_tx_kinds_are_the_four_frozen_strings() -> None:
    """CHANNEL_KINDS is the vocabulary ``classify_channel_tx`` returns — it is
    deliberately *not* a ChannelTx field: the client returns raw rows and the
    pure layer classifies them (PRD §6 rule 4)."""
    from maxpane_dashboard.data.surf_models import CHANNEL_KINDS

    assert CHANNEL_KINDS == ("self", "reply", "action", "fund")
    assert "kind" not in {f.name for f in dataclasses.fields(ChannelTx)}
    assert "text" not in {f.name for f in dataclasses.fields(ChannelTx)}


def test_module_has_no_io_imports() -> None:
    import inspect

    from maxpane_dashboard.data import surf_models

    source = inspect.getsource(surf_models)
    for banned in ("import httpx", "import asyncio", "from textual", "import requests"):
        assert banned not in source


# ---------------------------------------------------------------------------
# the flat-dict contract (docs/surf_PRD.md §5)
# ---------------------------------------------------------------------------

EXPECTED_KEYS = {
    # meta
    "as_of",
    "degraded",
    "eth_usd",
    # feed
    "feed_nonce",
    "feed_last_post_age_s",
    "feed_items",
    # signals — six detectors x (state, detail, age)
    "sig_post_state",
    "sig_post_detail",
    "sig_post_age_s",
    "sig_lp_state",
    "sig_lp_detail",
    "sig_lp_age_s",
    "sig_gate_state",
    "sig_gate_detail",
    "sig_gate_age_s",
    "sig_deploy_state",
    "sig_deploy_detail",
    "sig_deploy_age_s",
    "sig_bridge_state",
    "sig_bridge_detail",
    "sig_bridge_age_s",
    "sig_burn_state",
    "sig_burn_detail",
    "sig_burn_age_s",
    # hero
    "hook_status",
    "lp_liquidity",
    "lp_imd",
    "lp_weth",
    "lp_owner_ok",
    "gate_open",
    "identities_written",
    "imd_supply",
    "imd_burned_cum",
    # market
    "imd_price_usd",
    "imd_change_24h_pct",
    "imd_vol_24h_usd",
    "pool_liquidity_usd",
    "legacy_pool_liquidity_usd",
    "price_source_disagreement_pct",
    "fp_price_usd",
    "parity_pct",
    "supply_series",
    "price_series",
    # nft
    "nft_holders",
    "nft_transfers_24h",
    "nft_dev_holdings",
    "nft_written",
    "nft_last_sales",
    "nft_floor",
    # activity
    "dev_activity",
    # pool (v3 -> v4 migration)
    "pool_venue",
    "pool_fee_bps",
    "pool_liquidity_raw",
    "pool_id_source",
    "decoy_pool_count",
    "lp_state",
    "lp_position_count",
    # burn executor (v1 -> v2)
    "burn_accrued",
    "burn_staged",
    "burn_ready",
    "burn_min_bridge",
    # launchpad (detached sweep)
    "launchpad_coin_count",
    "launchpad_swap_count",
    "launchpad_trader_count",
    "launchpad_burned_total",
    "launchpad_creator_eth_owed",
    "launchpad_coins",
    "launchpad_as_of_hhmm",
    # signals — three new detectors x (state, detail, age)
    "sig_decoy_state",
    "sig_decoy_detail",
    "sig_decoy_age_s",
    "sig_burnready_state",
    "sig_burnready_detail",
    "sig_burnready_age_s",
    "sig_hot_state",
    "sig_hot_detail",
    "sig_hot_age_s",
}


def test_surf_keys_is_exactly_the_prd_contract() -> None:
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    assert set(SURF_KEYS) == EXPECTED_KEYS
    assert len(SURF_KEYS) == len(set(SURF_KEYS)) == 77


def test_every_signal_has_all_three_facets() -> None:
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    for base in (
        "post", "lp", "gate", "deploy", "bridge", "burn",
        "decoy", "burnready", "hot",
    ):
        for suffix in ("state", "detail", "age_s"):
            assert f"sig_{base}_{suffix}" in SURF_KEYS


def test_signal_output_keys_are_a_subset_of_surf_keys() -> None:
    """SIGNAL_OUTPUT_KEYS (the signals module) must all exist in SURF_KEYS.

    Skips until ``analytics/surf_signals.py`` lands; from then on this is the
    only test in the repo that compares the two frozen key surfaces, so a
    rename on either side fails here — instead of surfacing as a widget that
    quietly renders ``None`` for a signal nobody notices is missing.
    """
    surf_signals = pytest.importorskip("maxpane_dashboard.analytics.surf_signals")
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    missing = sorted(set(surf_signals.SIGNAL_OUTPUT_KEYS) - set(SURF_KEYS))
    assert not missing, f"signal keys absent from SURF_KEYS: {missing}"


def test_row_key_sets_match_the_prd() -> None:
    from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS

    assert SURF_ROW_KEYS["feed_items"] == (
        "ts",
        "kind",
        "from_addr",
        "from_label",
        "text",
        "tx_hash",
    )
    assert SURF_ROW_KEYS["nft_last_sales"] == ("ts", "token_id", "eth")
    assert SURF_ROW_KEYS["dev_activity"] == (
        "ts",
        "wallet_label",
        "kind",
        "counterparty",
        "counterparty_known",
        "value_eth",
        "tx_hash",
    )
    assert set(SURF_ROW_KEYS) <= set(
        __import__(
            "maxpane_dashboard.data.surf_models", fromlist=["SURF_KEYS"]
        ).SURF_KEYS
    )


def test_no_wei_key_leaks_into_the_flat_dict() -> None:
    """The dict is the presentation boundary: ETH/float only."""
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    assert not [k for k in SURF_KEYS if k.endswith("_wei")]


# ---------------------------------------------------------------------------
# v4 migration + IMD launchpad — the frozen contract addition (2026-08-23)
# ---------------------------------------------------------------------------

from maxpane_dashboard.data.surf_models import SURF_KEYS, SURF_ROW_KEYS


def test_pool_v4_state_fields() -> None:
    s = PoolV4State(
        pool_id="0xb07d",
        sqrt_price_x96=3757351088368496721754945570926,
        tick=77186,
        lp_fee=10000,
        liquidity=7393092836965392068604,
        pool_id_source="hook",
    )
    assert s.lp_fee == 10000
    assert s.pool_id_source == "hook"


def test_pool_id_source_is_recorded_not_inferred() -> None:
    """The panel must be able to say the id came from the fallback."""
    s = PoolV4State(
        pool_id="0xb07d", sqrt_price_x96=None, tick=None, lp_fee=None,
        liquidity=None, pool_id_source="fallback",
    )
    assert s.pool_id_source == "fallback"


def test_new_payload_keys_exist() -> None:
    for key in (
        "pool_venue", "pool_fee_bps", "pool_liquidity_raw", "pool_id_source",
        "decoy_pool_count", "lp_state", "lp_position_count",
        "burn_accrued", "burn_staged", "burn_ready", "burn_min_bridge",
        "launchpad_coin_count", "launchpad_swap_count",
        "launchpad_trader_count", "launchpad_burned_total",
        "launchpad_creator_eth_owed", "launchpad_coins",
        "launchpad_as_of_hhmm",
        "sig_decoy_state", "sig_decoy_detail", "sig_decoy_age_s",
        "sig_burnready_state", "sig_burnready_detail", "sig_burnready_age_s",
        "sig_hot_state", "sig_hot_detail", "sig_hot_age_s",
    ):
        assert key in SURF_KEYS, key


def test_lp_migration_signal_keys_are_renamed_not_dropped() -> None:
    """LP MIGRATION became LP MOVE; the prefix stays `lp` so the widget's
    _ROW_KEYS alignment is unchanged."""
    assert "sig_lp_state" in SURF_KEYS


def test_launchpad_coin_row_keys() -> None:
    assert SURF_ROW_KEYS["launchpad_coins"] == (
        "ticker", "name", "creator", "creator_known",
        "age_s", "price_eth", "change_1h_pct", "swaps_1h", "imd_burned",
    )
