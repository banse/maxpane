"""Tests for Cat Town signal generation."""

from maxpane_dashboard.analytics.cattown_signals import (
    generate_condition_signal,
    generate_competition_signal,
    generate_kibble_signal,
    generate_legendary_signal,
    generate_staking_signal,
)

SIGNAL_KEYS = {"label", "value_str", "indicator", "color"}


class TestConditionSignal:
    def test_condition_signal_format(self):
        sig = generate_condition_signal({"time_of_day": "Morning", "season": "Spring", "weather": "Sun"})
        assert sig.keys() == SIGNAL_KEYS
        assert sig["label"] == "Conditions"
        assert "Morning" in sig["value_str"]
        assert "Spring" in sig["value_str"]
        assert sig["color"] == "white"


class TestLegendarySignal:
    def test_legendary_signal_active(self):
        sig = generate_legendary_signal({"time_of_day": "Morning", "season": "Spring", "weather": "Storm"})
        assert sig["color"] == "green"
        assert "ACTIVE" in sig["value_str"]
        assert "Elusive Marlin" in sig["value_str"]

    def test_legendary_signal_inactive(self):
        # Every real season matches a legendary (Spring->Gar, Summer->Musky, etc.)
        # so we test with no season/weather to get inactive
        sig = generate_legendary_signal({"time_of_day": "Morning"})
        assert sig["color"] == "dim"
        assert "None available" in sig["value_str"]


class TestCompetitionSignal:
    def test_competition_signal_live(self):
        sig = generate_competition_signal(is_active=True, seconds_remaining=3600, prize_pool_kibble=50000)
        assert sig["color"] == "yellow"
        assert "LIVE" in sig["value_str"]

    def test_competition_signal_countdown(self):
        sig = generate_competition_signal(is_active=False, seconds_remaining=86400, prize_pool_kibble=0)
        assert sig["color"] == "dim"
        assert "Starts in" in sig["value_str"]
        assert "1d" in sig["value_str"]


class TestStakingSignal:
    def test_staking_signal_high_apy(self):
        sig = generate_staking_signal(apy=25.0, kibble_price_change=2.0)
        assert sig["color"] == "green"
        assert "25.0%" in sig["value_str"]

    def test_staking_signal_medium_apy(self):
        sig = generate_staking_signal(apy=10.0, kibble_price_change=0.0)
        assert sig["color"] == "yellow"

    def test_staking_signal_low_apy(self):
        sig = generate_staking_signal(apy=3.0, kibble_price_change=-1.0)
        assert sig["color"] == "dim"


class TestKibbleSignal:
    def test_kibble_signal_positive(self):
        sig = generate_kibble_signal(price_usd=0.05, change_24h=5.0)
        assert sig["color"] == "green"
        assert "+5.0%" in sig["value_str"]

    def test_kibble_signal_negative(self):
        sig = generate_kibble_signal(price_usd=0.05, change_24h=-3.0)
        assert sig["color"] == "red"
        assert "-3.0%" in sig["value_str"]

    def test_kibble_signal_zero_change(self):
        sig = generate_kibble_signal(price_usd=0.05, change_24h=0.0)
        assert sig["color"] == "white"
