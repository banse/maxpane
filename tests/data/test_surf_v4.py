"""v4 pool state maths.  Pure: no I/O, no network, no addresses."""

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_v4

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/surf/v4/v4_pool_state.json").read_text()
)


def test_decode_slot0_matches_the_live_word() -> None:
    sqrt, tick, fee = surf_v4.decode_slot0(FIXTURE["slot0_word"])
    assert sqrt == FIXTURE["expected"]["sqrt_price_x96"]
    assert tick == FIXTURE["expected"]["tick"]
    assert fee == FIXTURE["expected"]["lp_fee"]


def test_the_live_pool_is_the_one_percent_tier() -> None:
    """1% is what the dev announced; a decoy at 5-98% must not decode to it."""
    _, _, fee = surf_v4.decode_slot0(FIXTURE["slot0_word"])
    assert fee == 10000


def test_decode_liquidity() -> None:
    assert surf_v4.decode_liquidity(FIXTURE["liquidity_word"]) == (
        FIXTURE["expected"]["liquidity"]
    )


def test_slot_pair_is_base_and_base_plus_three() -> None:
    slot0, liq = surf_v4.pool_state_slots(FIXTURE["pool_id"])
    assert int(liq, 16) - int(slot0, 16) == 3
    assert len(slot0) == 66 and slot0.startswith("0x")


def test_negative_tick_decodes_as_signed() -> None:
    """tick is int24; a pool below 1:1 has a negative tick and must not
    decode as ~16.7 million."""
    word = "0x" + ("000000" + "ffffff" + "0" * 40).rjust(64, "0")
    _, tick, _ = surf_v4.decode_slot0(word)
    assert tick == -1


def test_price_eth_per_imd() -> None:
    """currency0 is native ETH, currency1 is IMD, so sqrtPrice**2 is IMD/ETH."""
    price = surf_v4.price_eth_per_imd(FIXTURE["expected"]["sqrt_price_x96"])
    assert price == pytest.approx(0.00044463, rel=1e-4)


def test_price_of_zero_sqrt_is_none_not_zero() -> None:
    """An unread pool is None; 0.0 would render as a free token."""
    assert surf_v4.price_eth_per_imd(0) is None
