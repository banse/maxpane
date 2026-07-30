"""Tests for the Onchain Monsters signal generators and rate maths.

The burn-rate tests are the regression net for HIGH-3: the signal used to
be fed the totalSupply series, which for OCM only ever grows -- with
mints -- because burns are transfers to 0xdead and never reduce supply.
A single mint in the ~2h window rendered "~84/week" with a red "high"
pressure indicator while real burns were never counted at all.
"""

from __future__ import annotations

from maxpane_dashboard.analytics.ocm_signals import (
    compute_burn_rate,
    compute_mint_velocity,
    generate_burn_rate_signal,
    generate_mint_velocity_signal,
    generate_recommendation,
    generate_staking_signal,
)

_WEEK = 604800.0
_HOUR = 3600.0


# ---------------------------------------------------------------------------
# Staking signal
# ---------------------------------------------------------------------------


def test_staking_signal_healthy():
    sig = generate_staking_signal(55.0)
    assert sig["color"] == "green"
    assert sig["value_str"] == "55% staked"


def test_staking_signal_moderate_and_low():
    assert generate_staking_signal(25.0)["color"] == "yellow"
    assert generate_staking_signal(5.0)["color"] == "red"


def test_staking_signal_treats_input_as_percentage():
    """LOW-4: no unit guessing -- the input is always already a percentage.

    ``ocm_client`` computes ``staking_ratio = total_staked / net_supply * 100``,
    so a sub-1% reading is a real, alarming sub-1% -- it must not be rescaled
    into a healthy-looking double-digit number.
    """
    assert generate_staking_signal(50.0)["value_str"] == "50% staked"
    # 80 of 10,000 staked -> 0.8%, previously displayed as "80% staked" green.
    sig = generate_staking_signal(0.8)
    assert sig["value_str"] == "1% staked"  # 0.8 rounded by the :.0f format
    assert sig["color"] == "red"
    # Exactly 1.0% was the worst case: it rendered as "100% staked".
    sig = generate_staking_signal(1.0)
    assert sig["value_str"] == "1% staked"
    assert sig["color"] == "red"
    # Zero staked must stay red, not become a 0% green edge case.
    assert generate_staking_signal(0.0)["color"] == "red"


def test_recommendation_flags_sub_one_percent_staking():
    """LOW-4: the low-staking warning must not be suppressed below 1%."""
    assert "disengaged" in generate_recommendation(0.8, 10.0, 0.0, True)
    assert "disengaged" in generate_recommendation(1.0, 10.0, 0.0, True)
    assert "disengaged" in generate_recommendation(0.0, 10.0, 0.0, True)


# ---------------------------------------------------------------------------
# Mint velocity
# ---------------------------------------------------------------------------


def test_mint_velocity_needs_two_points():
    assert compute_mint_velocity([]) == 0.0
    assert compute_mint_velocity([(0.0, 100.0)]) == 0.0


def test_mint_velocity_counts_supply_growth_per_day():
    start = 1_700_000_000.0
    history = [(start, 1000.0), (start + 86400, 1010.0)]
    assert compute_mint_velocity(history) == 10.0


def test_mint_velocity_ignores_point_order():
    start = 1_700_000_000.0
    history = [(start + 86400, 1010.0), (start, 1000.0)]
    assert compute_mint_velocity(history) == 10.0


def test_mint_velocity_never_negative():
    start = 1_700_000_000.0
    assert compute_mint_velocity([(start, 1000.0), (start + 86400, 990.0)]) == 0.0


def test_mint_velocity_zero_elapsed():
    assert compute_mint_velocity([(1.0, 100.0), (1.0, 200.0)]) == 0.0


def test_mint_velocity_signal_thresholds():
    assert generate_mint_velocity_signal(10.0)["color"] == "green"
    assert generate_mint_velocity_signal(2.0)["color"] == "yellow"
    assert generate_mint_velocity_signal(0.0)["color"] == "dim"


# ---------------------------------------------------------------------------
# Burn rate -- HIGH-3 regression
# ---------------------------------------------------------------------------


def test_burn_rate_is_zero_for_a_mint_only_window():
    """The exact shape of the HIGH-3 bug.

    A ~2h totalSupply series in which one mint happened.  Fed to the burn
    rate this used to produce ~84/week and a red "high" indicator.  A
    cumulative-burn series over the same window has no burns in it, so the
    only correct answer is 0.
    """
    start = 1_700_000_000.0
    # What the buggy code passed: totalSupply, which grows by 1 on a mint.
    supply_window = [(start + i * 60.0, 4000.0 + (1 if i >= 60 else 0)) for i in range(120)]
    # What the fixed code passes: balanceOf(0xdead) over the same window.
    burn_window = [(ts, 12.0) for ts, _ in supply_window]

    # Demonstrate the inversion the old wiring produced ...
    assert compute_burn_rate(supply_window) > 80.0
    assert generate_burn_rate_signal(compute_burn_rate(supply_window))["color"] == "red"

    # ... and that the burn series reports the truth: no burns happened.
    rate = compute_burn_rate(burn_window, min_elapsed_seconds=7 * 86400)
    assert rate == 0.0
    signal = generate_burn_rate_signal(rate)
    assert signal["value_str"] == "~0/week"
    assert signal["color"] == "dim"


def test_burn_rate_counts_real_burns():
    """Real burns must actually move the signal."""
    start = 1_700_000_000.0
    burn_window = [
        (start, 10.0),
        (start + 2 * 86400, 12.0),
        (start + 7 * 86400, 17.0),
    ]
    # 7 burns observed over exactly one week.
    assert compute_burn_rate(burn_window, min_elapsed_seconds=7 * 86400) == 7.0
    assert generate_burn_rate_signal(7.0)["color"] == "red"


def test_burn_rate_is_unaffected_by_mints():
    """Mints and burns move independently; only burns reach the signal."""
    start = 1_700_000_000.0
    # Supply triples while burns hold steady.
    burn_window = [(start, 5.0), (start + 7 * 86400, 5.0)]
    assert compute_burn_rate(burn_window, min_elapsed_seconds=7 * 86400) == 0.0


def test_burn_rate_needs_two_points():
    assert compute_burn_rate([]) == 0.0
    assert compute_burn_rate([(1.0, 3.0)]) == 0.0


def test_burn_rate_zero_or_negative_elapsed():
    assert compute_burn_rate([(1.0, 3.0), (1.0, 9.0)]) == 0.0


def test_burn_rate_never_negative():
    start = 1_700_000_000.0
    # Should not happen (the burn balance is monotonic) but a stale RPC read
    # must not produce a negative rate.
    assert compute_burn_rate([(start, 10.0), (start + _WEEK, 4.0)]) == 0.0


def test_burn_rate_min_window_floors_extrapolation():
    """A short observation window must not be blown up into a false alarm."""
    start = 1_700_000_000.0
    two_hours = [(start, 12.0), (start + 2 * _HOUR, 13.0)]

    # Raw extrapolation of one burn seen over 2h is an absurd ~84/week ...
    assert compute_burn_rate(two_hours) > 80.0
    # ... but flooring the window at a week reports it as what it is: 1 burn.
    assert compute_burn_rate(two_hours, min_elapsed_seconds=7 * 86400) == 1.0


def test_burn_rate_min_window_does_not_dampen_a_full_window():
    start = 1_700_000_000.0
    two_weeks = [(start, 0.0), (start + 2 * _WEEK, 20.0)]
    assert compute_burn_rate(two_weeks, min_elapsed_seconds=7 * 86400) == 10.0


def test_burn_rate_signal_thresholds():
    assert generate_burn_rate_signal(10.0)["color"] == "red"
    assert generate_burn_rate_signal(3.0)["color"] == "yellow"
    assert generate_burn_rate_signal(0.0)["color"] == "dim"
    assert generate_burn_rate_signal(2.4)["value_str"] == "~2/week"


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def test_recommendation_low_staking_wins():
    assert "disengaged" in generate_recommendation(10.0, 10.0, 0.0, True)


def test_recommendation_contracting_supply():
    assert "contracting" in generate_recommendation(50.0, 1.0, 20.0, False)


def test_recommendation_growing_interest():
    assert "rising" in generate_recommendation(50.0, 10.0, 0.0, True)


def test_recommendation_healthy_default():
    assert "Healthy" in generate_recommendation(50.0, 2.0, 0.0, False)


def test_recommendation_stable_fallback():
    assert "stable" in generate_recommendation(30.0, 0.0, 0.0, False)


def test_recommendation_does_not_claim_contraction_without_burns():
    """With zero burns the collection can never read as contracting."""
    for mints in (0.0, 1.0, 50.0):
        assert "contracting" not in generate_recommendation(50.0, mints, 0.0, True)
