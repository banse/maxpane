"""Tests for Defense of the Agents signal generation."""

from maxpane_dashboard.analytics.dota_signals import (
    compute_faction_balance,
    compute_hero_advantage,
    compute_lane_pressure,
    generate_recommendation,
)

SIGNAL_KEYS = {"label", "value_str", "indicator", "color"}
VALID_COLORS = {"green", "yellow", "red"}


class TestFactionBalance:
    def test_human_dominant(self):
        sig = compute_faction_balance(70, 34)
        assert sig.keys() == SIGNAL_KEYS
        assert sig["color"] == "green"
        assert "Human dominant" in sig["value_str"]
        assert "70 vs 34" in sig["value_str"]

    def test_orc_dominant(self):
        sig = compute_faction_balance(20, 60)
        assert sig["color"] == "red"
        assert "Orc dominant" in sig["value_str"]
        assert "20 vs 60" in sig["value_str"]

    def test_contested(self):
        sig = compute_faction_balance(50, 48)
        assert sig["color"] == "yellow"
        assert "Contested" in sig["value_str"]

    def test_exactly_at_20_percent_threshold(self):
        # 120 vs 100: 120 == 100 * 1.2, NOT greater, so contested
        sig = compute_faction_balance(120, 100)
        assert sig["color"] == "yellow"
        assert "Contested" in sig["value_str"]

    def test_just_above_20_percent_threshold(self):
        # 121 vs 100: 121 > 100 * 1.2
        sig = compute_faction_balance(121, 100)
        assert sig["color"] == "green"
        assert "Human dominant" in sig["value_str"]

    def test_both_zero(self):
        sig = compute_faction_balance(0, 0)
        assert sig["color"] == "yellow"
        assert "Contested" in sig["value_str"]
        assert "0 vs 0" in sig["value_str"]

    def test_one_zero(self):
        sig = compute_faction_balance(10, 0)
        assert sig["color"] == "green"
        assert "Human dominant" in sig["value_str"]

    def test_orc_one_zero(self):
        sig = compute_faction_balance(0, 10)
        assert sig["color"] == "red"
        assert "Orc dominant" in sig["value_str"]

    def test_label(self):
        sig = compute_faction_balance(50, 50)
        assert sig["label"] == "Faction Balance"

    def test_indicator(self):
        sig = compute_faction_balance(50, 50)
        assert sig["indicator"] == "\u25cf"

    def test_color_always_valid(self):
        for h, o in [(100, 10), (10, 100), (50, 50), (0, 0)]:
            sig = compute_faction_balance(h, o)
            assert sig["color"] in VALID_COLORS


class TestLanePressure:
    def test_human_pushing(self):
        sig = compute_lane_pressure(50, 40, 30)
        assert sig.keys() == SIGNAL_KEYS
        assert sig["color"] == "green"
        assert "Human pushing" in sig["value_str"]
        assert "+40 avg" in sig["value_str"]

    def test_orc_pushing(self):
        sig = compute_lane_pressure(-50, -30, -40)
        assert sig["color"] == "red"
        assert "Orc pushing" in sig["value_str"]
        assert "-40 avg" in sig["value_str"]

    def test_stalemate(self):
        sig = compute_lane_pressure(10, -5, 5)
        assert sig["color"] == "yellow"
        assert "Stalemate" in sig["value_str"]

    def test_exactly_at_positive_threshold(self):
        # avg = 20.0, not > 20, so stalemate
        sig = compute_lane_pressure(20, 20, 20)
        assert sig["color"] == "yellow"
        assert "Stalemate" in sig["value_str"]

    def test_just_above_positive_threshold(self):
        # avg = 21.0
        sig = compute_lane_pressure(21, 21, 21)
        assert sig["color"] == "green"
        assert "Human pushing" in sig["value_str"]

    def test_exactly_at_negative_threshold(self):
        # avg = -20.0, not < -20, so stalemate
        sig = compute_lane_pressure(-20, -20, -20)
        assert sig["color"] == "yellow"
        assert "Stalemate" in sig["value_str"]

    def test_just_below_negative_threshold(self):
        # avg = -21.0
        sig = compute_lane_pressure(-21, -21, -21)
        assert sig["color"] == "red"
        assert "Orc pushing" in sig["value_str"]

    def test_all_zero(self):
        sig = compute_lane_pressure(0, 0, 0)
        assert sig["color"] == "yellow"
        assert "Stalemate" in sig["value_str"]
        assert "+0 avg" in sig["value_str"]

    def test_mixed_lanes(self):
        # +100, 0, -100 => avg 0 => stalemate
        sig = compute_lane_pressure(100, 0, -100)
        assert sig["color"] == "yellow"
        assert "Stalemate" in sig["value_str"]

    def test_label(self):
        sig = compute_lane_pressure(0, 0, 0)
        assert sig["label"] == "Lane Pressure"

    def test_color_always_valid(self):
        for t, m, b in [(50, 50, 50), (-50, -50, -50), (0, 0, 0)]:
            sig = compute_lane_pressure(t, m, b)
            assert sig["color"] in VALID_COLORS


class TestHeroAdvantage:
    def test_human_edge(self):
        sig = compute_hero_advantage(6, 4)
        assert sig.keys() == SIGNAL_KEYS
        assert sig["color"] == "green"
        assert "Human edge" in sig["value_str"]
        assert "6 vs 4" in sig["value_str"]

    def test_orc_edge(self):
        sig = compute_hero_advantage(2, 5)
        assert sig["color"] == "red"
        assert "Orc edge" in sig["value_str"]
        assert "2 vs 5" in sig["value_str"]

    def test_even(self):
        sig = compute_hero_advantage(4, 4)
        assert sig["color"] == "yellow"
        assert "Even" in sig["value_str"]

    def test_one_hero_difference_is_even(self):
        sig = compute_hero_advantage(5, 4)
        assert sig["color"] == "yellow"
        assert "Even" in sig["value_str"]

    def test_one_hero_difference_orc_side_is_even(self):
        sig = compute_hero_advantage(3, 4)
        assert sig["color"] == "yellow"
        assert "Even" in sig["value_str"]

    def test_exactly_two_difference(self):
        sig = compute_hero_advantage(5, 3)
        assert sig["color"] == "green"
        assert "Human edge" in sig["value_str"]

    def test_exactly_two_difference_orc(self):
        sig = compute_hero_advantage(3, 5)
        assert sig["color"] == "red"
        assert "Orc edge" in sig["value_str"]

    def test_all_dead(self):
        sig = compute_hero_advantage(0, 0)
        assert sig["color"] == "yellow"
        assert "Even" in sig["value_str"]
        assert "0 vs 0" in sig["value_str"]

    def test_zero_vs_two(self):
        sig = compute_hero_advantage(0, 2)
        assert sig["color"] == "red"
        assert "Orc edge" in sig["value_str"]

    def test_label(self):
        sig = compute_hero_advantage(3, 3)
        assert sig["label"] == "Hero Advantage"

    def test_color_always_valid(self):
        for h, o in [(6, 2), (2, 6), (4, 4), (0, 0)]:
            sig = compute_hero_advantage(h, o)
            assert sig["color"] in VALID_COLORS


class TestGenerateRecommendation:
    def test_game_over_human(self):
        rec = generate_recommendation(50, 30, 40.0, 5, 3, 800, 0, 1000, "Human")
        assert "Human victory" in rec
        assert "game complete" in rec

    def test_game_over_orc(self):
        rec = generate_recommendation(30, 50, -40.0, 3, 5, 0, 800, 1000, "Orc")
        assert "Orc victory" in rec
        assert "game complete" in rec

    def test_game_over_lowercase(self):
        rec = generate_recommendation(50, 30, 40.0, 5, 3, 800, 0, 1000, "human")
        assert "Human victory" in rec

    def test_human_base_critical(self):
        rec = generate_recommendation(50, 60, -10.0, 4, 4, 200, 800, 1000, None)
        assert "Human base at 20%" in rec
        assert "Orc closing in" in rec

    def test_orc_base_critical(self):
        rec = generate_recommendation(60, 50, 10.0, 4, 4, 800, 100, 1000, None)
        assert "Orc base at 10%" in rec
        assert "Human closing in" in rec

    def test_base_exactly_at_30_percent_not_critical(self):
        rec = generate_recommendation(50, 50, 0.0, 4, 4, 300, 300, 1000, None)
        # 30% is not < 30%, so not critical
        assert "base at" not in rec

    def test_base_just_below_30_percent(self):
        rec = generate_recommendation(50, 50, 0.0, 4, 4, 250, 800, 1000, None)
        assert "Human base at 25%" in rec

    def test_all_human_favored(self):
        rec = generate_recommendation(80, 30, 35.0, 6, 3, 800, 600, 1000, None)
        assert "hero advantage" in rec
        assert "human victory likely" in rec

    def test_all_orc_favored(self):
        rec = generate_recommendation(30, 80, -35.0, 3, 6, 600, 800, 1000, None)
        assert "Orc pushing" in rec
        assert "human base threatened" in rec

    def test_mixed_signals(self):
        # Human has units, orc has lane pressure
        rec = generate_recommendation(80, 30, -35.0, 4, 4, 800, 800, 1000, None)
        assert "contested" in rec.lower() or "split" in rec.lower()

    def test_evenly_matched(self):
        rec = generate_recommendation(50, 50, 0.0, 4, 4, 800, 800, 1000, None)
        assert "evenly matched" in rec

    def test_zero_base_max_hp(self):
        # Edge case: base_max_hp is 0, should not divide by zero
        rec = generate_recommendation(50, 50, 0.0, 4, 4, 0, 0, 0, None)
        assert isinstance(rec, str)
        assert len(rec) > 0

    def test_winner_takes_priority_over_base_critical(self):
        # Winner set even though base HP is critical
        rec = generate_recommendation(50, 30, 40.0, 5, 3, 100, 0, 1000, "Human")
        assert "victory" in rec
        assert "base at" not in rec

    def test_returns_string(self):
        rec = generate_recommendation(50, 50, 0.0, 4, 4, 500, 500, 1000, None)
        assert isinstance(rec, str)
