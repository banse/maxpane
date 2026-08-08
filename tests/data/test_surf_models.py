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
    LogWindow,
    MarketSnapshot,
    NftStats,
    NonceSet,
)

ALL_MODELS = (
    NonceSet,
    ChainState,
    ChannelTx,
    DevTx,
    MarketSnapshot,
    LogWindow,
    NftStats,
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
        "block_number",
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
        "sources_agree",
    ),
    LogWindow: (
        "from_block", "to_block", "bridge_mints", "identity_updates",
        "v4_initializes", "seaport_sales",
    ),
    NftStats: (
        "holders", "total_supply", "transfers_total", "dev_holdings",
        "transfers_24h", "written", "floor_eth",
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
