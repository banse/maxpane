"""Tests for Ten Thousand Tokens (TTT) signal analytics.

Covers the pure functions in ``maxpane_dashboard.analytics.ttt_signals``:

* decay_tax_pct
* per_nft_share / concentration_multiplier
* count_buybacks_ready
* count_decay_window
* fresh_launch_alert
* buybacks_ready_signal / decay_window_signal / concentration_signal
* claim_math_scenarios
* aggregate_recent_launches

All inputs are constructed directly from ``TTTFactoryState`` / ``TTTLaunchedToken``
/ ``TTTActivityEvent`` Pydantic models -- no mocking framework needed.
"""

from __future__ import annotations

import time

import pytest

from maxpane_dashboard.analytics.ttt_signals import (
    BUYBACK_BOUNTY_FRAC,
    BUYBACK_MAX_DRAW_WEI,
    BUYBACK_READY_THRESHOLD_WEI,
    DECAY_BLOCKS,
    MAX_NFTS,
    aggregate_recent_launches,
    buybacks_ready_signal,
    claim_math_scenarios,
    concentration_multiplier,
    concentration_signal,
    count_buybacks_ready,
    count_decay_window,
    decay_tax_pct,
    decay_window_signal,
    fresh_launch_alert,
    per_nft_share,
)
from maxpane_dashboard.data.ttt_models import (
    TTTActivityEvent,
    TTTFactoryState,
    TTTLaunchedToken,
)

VALID_COLORS = {"green", "yellow", "red", "dim"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(
    token_id: int = 1,
    address: str = "0x0000000000000000000000000000000000000001",
    launch_block: int = 100,
    reservoir_wei: int = 0,
    fees_eth_24h: float = 0.0,
    symbol: str = "TKN",
    **overrides,
) -> TTTLaunchedToken:
    """Build a minimal valid TTTLaunchedToken with sensible defaults."""
    defaults = dict(
        token_id=token_id,
        address=address,
        deployer="0x000000000000000000000000000000000000dead",
        launch_block=launch_block,
        symbol=symbol,
        decimals=18,
        reservoir_wei=reservoir_wei,
        fees_eth_24h=fees_eth_24h,
        fees_eth_lifetime=fees_eth_24h,
    )
    defaults.update(overrides)
    return TTTLaunchedToken(**defaults)


def _make_state(
    unburned: int = 9891,
    burn_count: int | None = None,
    current_block: int = 1_000_000,
    acc_eth_per_share: int = 0,
    total_eth_to_holders_wei: int = 0,
    **overrides,
) -> TTTFactoryState:
    """Build a minimal valid TTTFactoryState with sensible defaults."""
    max_supply = overrides.pop("max_supply", 10_000)
    if burn_count is None:
        burn_count = max_supply - unburned
    defaults = dict(
        max_supply=max_supply,
        burn_count=burn_count,
        total_minted=max_supply,
        unburned=unburned,
        burned_pct=burn_count / max_supply * 100,
        acc_eth_per_share=acc_eth_per_share,
        total_eth_to_holders_wei=total_eth_to_holders_wei,
        current_block=current_block,
    )
    defaults.update(overrides)
    return TTTFactoryState(**defaults)


def _make_event(
    event_type: str = "burn",
    timestamp: int = 0,
    block_number: int = 100,
    tx_hash: str = "0xabc",
    token_symbol: str | None = "TKN",
    token_address: str | None = None,
    actor_address: str | None = None,
    eth_amount_wei: int = 0,
    token_id: int | None = None,
    extra: dict | None = None,
) -> TTTActivityEvent:
    """Build a minimal valid TTTActivityEvent with sensible defaults."""
    return TTTActivityEvent(
        tx_hash=tx_hash,
        block_number=block_number,
        timestamp=timestamp,
        event_type=event_type,
        token_symbol=token_symbol,
        token_address=token_address,
        actor_address=actor_address,
        eth_amount_wei=eth_amount_wei,
        token_id=token_id,
        extra=extra,
    )


def _signal_field(sig, name: str):
    """Return field from a TTTSignal-like object: works for both models and dicts."""
    if isinstance(sig, dict):
        return sig[name]
    return getattr(sig, name)


# ---------------------------------------------------------------------------
# decay_tax_pct
# ---------------------------------------------------------------------------

class TestDecayTaxPct:
    def test_block_0_is_99(self) -> None:
        assert decay_tax_pct(0) == 99

    def test_block_1_is_98(self) -> None:
        assert decay_tax_pct(1) == 98

    def test_block_50_is_49(self) -> None:
        assert decay_tax_pct(50) == 49

    def test_block_97_is_2(self) -> None:
        assert decay_tax_pct(97) == 2

    def test_block_98_is_1(self) -> None:
        assert decay_tax_pct(98) == 1

    def test_block_99_floors_at_1(self) -> None:
        assert decay_tax_pct(99) == 1

    def test_block_10000_still_floor(self) -> None:
        assert decay_tax_pct(10_000) == 1


# ---------------------------------------------------------------------------
# per_nft_share / concentration_multiplier
# ---------------------------------------------------------------------------

class TestPerNftShare:
    def test_full_supply(self) -> None:
        assert per_nft_share(10_000) == pytest.approx(0.30 / 10_000)

    def test_half_supply(self) -> None:
        assert per_nft_share(5_000) == pytest.approx(0.30 / 5_000)

    def test_sole_survivor(self) -> None:
        assert per_nft_share(1) == pytest.approx(0.30)

    def test_zero_unburned_returns_zero(self) -> None:
        assert per_nft_share(0) == 0.0


class TestConcentrationMultiplier:
    def test_full_supply_is_one(self) -> None:
        assert concentration_multiplier(10_000) == pytest.approx(1.0)

    def test_one_tenth_supply_is_ten(self) -> None:
        assert concentration_multiplier(1_000) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# count_buybacks_ready
# ---------------------------------------------------------------------------

class TestCountBuybacksReady:
    def test_empty_list(self) -> None:
        count, bounty = count_buybacks_ready([])
        assert count == 0
        assert bounty == 0

    def test_one_above_threshold(self) -> None:
        # 0.2 Ξ reservoir (above 0.1 Ξ threshold)
        reservoir = 2 * 10**17
        tokens = [
            _make_token(token_id=1, address="0x01", reservoir_wei=reservoir),
            _make_token(token_id=2, address="0x02", reservoir_wei=10**16),  # 0.01 Ξ
            _make_token(token_id=3, address="0x03", reservoir_wei=0),
        ]
        count, bounty = count_buybacks_ready(tokens)
        assert count == 1
        assert bounty == int(BUYBACK_BOUNTY_FRAC * reservoir)

    def test_reservoir_above_one_eth_caps_bounty(self) -> None:
        # 5 Ξ reservoir -- bounty caps at 0.005 * 1 Ξ
        reservoir = 5 * 10**18
        tokens = [_make_token(address="0xbig", reservoir_wei=reservoir)]
        count, bounty = count_buybacks_ready(tokens)
        assert count == 1
        assert bounty == int(BUYBACK_BOUNTY_FRAC * BUYBACK_MAX_DRAW_WEI)


# ---------------------------------------------------------------------------
# count_decay_window
# ---------------------------------------------------------------------------

class TestCountDecayWindow:
    def test_empty_list(self) -> None:
        assert count_decay_window([], current_block=1_000_000) == 0

    def test_boundary_exactly_98_blocks_not_counted_97_counted(self) -> None:
        current_block = 1_000_000
        # Token A: launched exactly 98 blocks ago -- tax has fallen to floor, NOT counted
        token_a = _make_token(
            token_id=1, address="0x0a", launch_block=current_block - DECAY_BLOCKS
        )
        # Token B: launched 97 blocks ago -- still inside decay window, counted
        token_b = _make_token(
            token_id=2, address="0x0b", launch_block=current_block - (DECAY_BLOCKS - 1)
        )
        count = count_decay_window([token_a, token_b], current_block=current_block)
        assert count == 1

    def test_a_zero_head_block_counts_nothing(self) -> None:
        """LOW-5: `fetch_block_number` returns 0 for a failed read, and every
        `0 - launch_block` is hugely negative -- i.e. `< 98`. Without the lower
        bound one dead-RPC cycle reported the entire collection as in-decay."""
        tokens = [
            _make_token(token_id=i, address=f"0x{i:02x}", launch_block=25_000_000 + i)
            for i in range(5)
        ]
        assert count_decay_window(tokens, current_block=0) == 0

    def test_a_launch_block_ahead_of_the_head_is_not_counted(self) -> None:
        """A lagging node can report a head below a launch we already know
        about; a negative age is not a fresh launch."""
        token = _make_token(token_id=1, address="0x0a", launch_block=1_000_050)
        assert count_decay_window([token], current_block=1_000_000) == 0

    def test_age_zero_is_counted(self) -> None:
        """The clamp must not exclude a token launched in the head block."""
        token = _make_token(token_id=1, address="0x0a", launch_block=1_000_000)
        assert count_decay_window([token], current_block=1_000_000) == 1


# ---------------------------------------------------------------------------
# fresh_launch_alert
# ---------------------------------------------------------------------------

class TestFreshLaunchAlert:
    def test_no_burns_returns_none(self) -> None:
        now = time.time()
        events = [
            _make_event(event_type="swap", timestamp=int(now) - 60),
            _make_event(event_type="buyback", timestamp=int(now) - 30),
        ]
        assert fresh_launch_alert(events, current_block=1_000_000, now_ts=now) is None

    def test_burn_3_minutes_ago_returns_signal(self) -> None:
        now = time.time()
        current_block = 1_000_000
        launch_block = current_block - 10  # 10 blocks ago -> tax = 89%
        burn = _make_event(
            event_type="burn",
            timestamp=int(now) - 3 * 60,  # 3 minutes ago
            block_number=launch_block,
            token_symbol="FRESH",
            token_id=42,
        )
        sig = fresh_launch_alert([burn], current_block=current_block, now_ts=now)
        assert sig is not None
        value_str = _signal_field(sig, "value_str")
        assert "3m ago" in value_str
        # decay_tax_pct(10) == 89
        assert "89" in value_str
        assert _signal_field(sig, "color") in VALID_COLORS

    def test_burn_11_minutes_ago_returns_none(self) -> None:
        now = time.time()
        burn = _make_event(
            event_type="burn",
            timestamp=int(now) - 11 * 60,
            block_number=999_900,
            token_symbol="STALE",
            token_id=7,
        )
        assert fresh_launch_alert([burn], current_block=1_000_000, now_ts=now) is None


# ---------------------------------------------------------------------------
# Signal-builder functions
# ---------------------------------------------------------------------------

class TestBuybacksReadySignal:
    def test_shape(self) -> None:
        sig = buybacks_ready_signal([])
        for field in ("label", "value_str", "indicator", "color"):
            assert _signal_field(sig, field) is not None
        assert _signal_field(sig, "color") in VALID_COLORS

    def test_count_zero_is_dim(self) -> None:
        sig = buybacks_ready_signal([])
        assert _signal_field(sig, "color") == "dim"

    def test_count_positive_is_green(self) -> None:
        token = _make_token(reservoir_wei=2 * 10**17)  # 0.2 Ξ, above threshold
        sig = buybacks_ready_signal([token])
        assert _signal_field(sig, "color") == "green"


class TestDecayWindowSignal:
    def test_shape(self) -> None:
        state = _make_state()
        sig = decay_window_signal([], current_block=state.current_block)
        for field in ("label", "value_str", "indicator", "color"):
            assert _signal_field(sig, field) is not None
        assert _signal_field(sig, "color") in VALID_COLORS

    def test_count_zero_is_dim(self) -> None:
        sig = decay_window_signal([], current_block=1_000_000)
        assert _signal_field(sig, "color") == "dim"

    def test_count_positive_is_yellow(self) -> None:
        current_block = 1_000_000
        # Token within decay window (50 blocks ago)
        token = _make_token(launch_block=current_block - 50)
        sig = decay_window_signal([token], current_block=current_block)
        assert _signal_field(sig, "color") == "yellow"

    def test_an_unknown_head_block_is_dim_and_reports_zero(self) -> None:
        """LOW-5: the false yellow "N tokens in decay window" alarm. The
        manager suppresses this signal entirely at `current_block == 0`, but
        the function itself must not fabricate a count either."""
        tokens = [
            _make_token(token_id=i, address=f"0x{i:02x}", launch_block=25_000_000 + i)
            for i in range(340)
        ]
        sig = decay_window_signal(tokens, current_block=0)
        assert _signal_field(sig, "color") == "dim"
        assert "0 tokens" in _signal_field(sig, "value_str")


class TestConcentrationSignal:
    def test_shape(self) -> None:
        state = _make_state(unburned=9891)
        sig = concentration_signal(state, eth_to_holders_24h=0.5)
        for field in ("label", "value_str", "indicator", "color"):
            assert _signal_field(sig, field) is not None
        assert _signal_field(sig, "color") in VALID_COLORS

    def test_includes_unburned_count_and_per_day(self) -> None:
        state = _make_state(unburned=9891)
        sig = concentration_signal(state, eth_to_holders_24h=0.5)
        value_str = _signal_field(sig, "value_str")
        # Should reference the per-NFT slice as "1/9,891"
        assert "1/9,891" in value_str
        # Should mention per-day ETH flow
        assert "Ξ/day" in value_str


# ---------------------------------------------------------------------------
# claim_math_scenarios
# ---------------------------------------------------------------------------

class TestClaimMathScenarios:
    def test_returns_six_rows(self) -> None:
        state = _make_state(unburned=9891)
        rows = claim_math_scenarios(state, eth_to_holders_24h=0.5)
        assert len(rows) == 6

    def test_today_row_uses_state_unburned(self) -> None:
        state = _make_state(unburned=9891)
        rows = claim_math_scenarios(state, eth_to_holders_24h=0.5)
        today = next(r for r in rows if r["scenario"] == "Today")
        assert today["unburned"] == 9891
        assert today["multiplier_vs_today"] == pytest.approx(1.0)

    def test_sole_survivor_row(self) -> None:
        state = _make_state(unburned=9891)
        rows = claim_math_scenarios(state, eth_to_holders_24h=0.5)
        sole = next(r for r in rows if r["scenario"] == "Sole survivor")
        assert sole["unburned"] == 1
        assert sole["share_pct"] == pytest.approx(30.0)

    def test_projections_scale_inversely_with_unburned(self) -> None:
        state = _make_state(unburned=10_000)
        rows = claim_math_scenarios(state, eth_to_holders_24h=1.0)
        # Build lookup by scenario name
        by_scenario = {r["scenario"]: r for r in rows}
        # Halving unburned doubles per-NFT projection
        # 25% burned == 7500 unburned
        # 50% burned == 5000 unburned
        proj_7500 = by_scenario.get(
            "25% burned", by_scenario.get("25%", None)
        )
        proj_5000 = by_scenario.get(
            "50% burned", by_scenario.get("50%", None)
        )
        assert proj_7500 is not None and proj_5000 is not None
        assert proj_7500["unburned"] == 7500
        assert proj_5000["unburned"] == 5000
        # Per-NFT scales inversely with unburned
        assert proj_5000["projected_24h_eth"] == pytest.approx(
            proj_7500["projected_24h_eth"] * (7500 / 5000)
        )


# ---------------------------------------------------------------------------
# aggregate_recent_launches
# ---------------------------------------------------------------------------

class TestAggregateRecentLaunches:
    def test_empty_events(self) -> None:
        assert aggregate_recent_launches([]) == 0

    def test_counts_burns_in_last_24h(self) -> None:
        # `aggregate_recent_launches` anchors the trailing window to the most
        # recent burn timestamp in the list (so the count is stable whether the
        # events are fresh-from-chain or replayed from cache).
        # Anchor at `now`; place 3 burns inside the trailing 24h and 2 well
        # outside (48h before the anchor) so the cutoff (anchor - 86400) is
        # unambiguous.
        now = int(time.time())
        within_window = now - 3600  # 1h before anchor
        outside_window = now - (48 * 3600)  # 48h before anchor (well outside 24h)
        events = [
            _make_event(event_type="burn", timestamp=now, token_id=0),
            _make_event(event_type="burn", timestamp=within_window, token_id=1),
            _make_event(event_type="burn", timestamp=within_window, token_id=2),
            _make_event(event_type="burn", timestamp=outside_window, token_id=4),
            _make_event(event_type="burn", timestamp=outside_window, token_id=5),
        ]
        count = aggregate_recent_launches(events)
        assert count == 3
