"""Tests for Cat Town conditions, fish table, and treasure table."""

from __future__ import annotations

from unittest.mock import patch
from datetime import datetime, timezone

import pytest

from maxpane_dashboard.analytics.cattown_conditions import (
    FISH_TABLE,
    TREASURE_TABLE,
    get_available_fish,
    get_available_treasures,
    get_competition_timing,
    get_season,
    get_time_of_day,
    is_legendary_window,
)


# ---------------------------------------------------------------------------
# Time-of-day tests (boundary values)
# ---------------------------------------------------------------------------


class TestTimeOfDay:
    def test_time_of_day_morning(self) -> None:
        assert get_time_of_day(6) == "Morning"
        assert get_time_of_day(11) == "Morning"

    def test_time_of_day_afternoon(self) -> None:
        assert get_time_of_day(12) == "Afternoon"
        assert get_time_of_day(17) == "Afternoon"

    def test_time_of_day_evening(self) -> None:
        assert get_time_of_day(18) == "Evening"
        assert get_time_of_day(23) == "Evening"

    def test_time_of_day_night(self) -> None:
        assert get_time_of_day(0) == "Night"
        assert get_time_of_day(5) == "Night"


# ---------------------------------------------------------------------------
# Season tests (boundary months)
# ---------------------------------------------------------------------------


class TestSeason:
    def test_season_spring(self) -> None:
        assert get_season(3) == "Spring"
        assert get_season(5) == "Spring"

    def test_season_summer(self) -> None:
        assert get_season(6) == "Summer"
        assert get_season(8) == "Summer"

    def test_season_autumn(self) -> None:
        assert get_season(9) == "Autumn"
        assert get_season(11) == "Autumn"

    def test_season_winter(self) -> None:
        assert get_season(12) == "Winter"
        assert get_season(1) == "Winter"
        assert get_season(2) == "Winter"


# ---------------------------------------------------------------------------
# Table count tests
# ---------------------------------------------------------------------------


class TestTables:
    def test_fish_table_has_35_entries(self) -> None:
        assert len(FISH_TABLE) == 35

    def test_treasure_table_has_33_entries(self) -> None:
        assert len(TREASURE_TABLE) == 33


# ---------------------------------------------------------------------------
# Fish filter tests
# ---------------------------------------------------------------------------


class TestFishFilter:
    def test_fish_filter_any_always_included(self) -> None:
        """Bluegill (condition_type=any) appears regardless of conditions."""
        conditions = {"time_of_day": "Evening", "season": "Winter", "weather": "Storm"}
        available = get_available_fish(conditions)
        names = [f["name"] for f in available]
        assert "Bluegill" in names

    def test_fish_filter_specific_time(self) -> None:
        """Oddball appears only when time_of_day=Morning."""
        morning = get_available_fish({"time_of_day": "Morning"})
        evening = get_available_fish({"time_of_day": "Evening"})
        morning_names = [f["name"] for f in morning]
        evening_names = [f["name"] for f in evening]
        assert "Oddball" in morning_names
        assert "Oddball" not in evening_names

    def test_fish_filter_specific_season(self) -> None:
        """Smallmouth Bass appears only in Spring."""
        spring = get_available_fish({"season": "Spring"})
        summer = get_available_fish({"season": "Summer"})
        spring_names = [f["name"] for f in spring]
        summer_names = [f["name"] for f in summer]
        assert "Smallmouth Bass" in spring_names
        assert "Smallmouth Bass" not in summer_names


# ---------------------------------------------------------------------------
# Legendary window tests
# ---------------------------------------------------------------------------


class TestLegendaryWindow:
    def test_legendary_window_storm(self) -> None:
        """Storm enables Elusive Marlin (legendary)."""
        assert is_legendary_window({"weather": "Storm"}) is True

    def test_legendary_window_no_match(self) -> None:
        """Sun + Morning does not enable any legendary fish."""
        assert is_legendary_window({"weather": "Sun", "time_of_day": "Morning"}) is False


# ---------------------------------------------------------------------------
# Competition timing tests
# ---------------------------------------------------------------------------


class TestCompetitionTiming:
    def test_competition_timing_saturday(self) -> None:
        """Competition is active on Saturday."""
        # Saturday 2026-03-28 12:00 UTC
        saturday_noon = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
        with patch("maxpane_dashboard.analytics.cattown_conditions.datetime") as mock_dt:
            mock_dt.now.return_value = saturday_noon
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_competition_timing()
        assert result["is_active"] is True
        assert result["seconds_until_start"] == 0

    def test_competition_timing_wednesday(self) -> None:
        """Competition is not active on Wednesday."""
        # Wednesday 2026-03-25 12:00 UTC
        wednesday_noon = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        with patch("maxpane_dashboard.analytics.cattown_conditions.datetime") as mock_dt:
            mock_dt.now.return_value = wednesday_noon
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_competition_timing()
        assert result["is_active"] is False
        assert result["seconds_until_start"] > 0
