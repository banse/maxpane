"""Cat Town conditions, fish table, and treasure table.

Provides time/season helpers and static catalogs for all 35 fish species
and 33 treasures, plus filter functions for determining what is currently
available based on in-game conditions.
"""

from __future__ import annotations

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Time / Season helpers
# ---------------------------------------------------------------------------


def get_time_of_day(utc_hour: int) -> str:
    """Map a UTC hour (0-23) to a time-of-day label.

    Morning: 6-11, Afternoon: 12-17, Evening: 18-23, Night: 0-5.
    """
    if 6 <= utc_hour <= 11:
        return "Morning"
    if 12 <= utc_hour <= 17:
        return "Afternoon"
    if 18 <= utc_hour <= 23:
        return "Evening"
    return "Night"


def get_season(utc_month: int) -> str:
    """Map a UTC month (1-12) to a season label.

    Spring: 3-5, Summer: 6-8, Autumn: 9-11, Winter: 12, 1, 2.
    """
    if 3 <= utc_month <= 5:
        return "Spring"
    if 6 <= utc_month <= 8:
        return "Summer"
    if 9 <= utc_month <= 11:
        return "Autumn"
    return "Winter"


def get_current_conditions() -> dict:
    """Return current conditions based on UTC time.

    Returns ``{"time_of_day": str, "season": str, "weather": "Unknown"}``.
    """
    now = datetime.now(timezone.utc)
    return {
        "time_of_day": get_time_of_day(now.hour),
        "season": get_season(now.month),
        "weather": "Unknown",
    }


# ---------------------------------------------------------------------------
# Fish table -- all 35 species
# ---------------------------------------------------------------------------
# Each entry: {name, rarity, weight_min, weight_max, condition_type, condition_value}
# condition_type: "any" | "season" | "time_of_day" | "weather"
# condition_value: str | list[str]

FISH_TABLE: list[dict] = [
    # -- Common (12) --
    {"name": "Bluegill", "rarity": "Common", "weight_min": 0.5, "weight_max": 1.2, "condition_type": "any", "condition_value": "Any"},
    {"name": "Pink Salmon", "rarity": "Common", "weight_min": 2.5, "weight_max": 5.0, "condition_type": "any", "condition_value": "Any"},
    {"name": "Amber Tilapia", "rarity": "Common", "weight_min": 2.0, "weight_max": 2.4, "condition_type": "any", "condition_value": "Any"},
    {"name": "Rainbow Trout", "rarity": "Common", "weight_min": 0.5, "weight_max": 2.5, "condition_type": "any", "condition_value": "Any"},
    {"name": "Smallmouth Bass", "rarity": "Common", "weight_min": 1.0, "weight_max": 3.0, "condition_type": "season", "condition_value": "Spring"},
    {"name": "Brook Trout", "rarity": "Common", "weight_min": 0.5, "weight_max": 2.0, "condition_type": "season", "condition_value": "Summer"},
    {"name": "Crappie", "rarity": "Common", "weight_min": 0.5, "weight_max": 1.0, "condition_type": "season", "condition_value": "Autumn"},
    {"name": "Yellow Perch", "rarity": "Common", "weight_min": 0.5, "weight_max": 1.5, "condition_type": "season", "condition_value": "Winter"},
    {"name": "Oddball", "rarity": "Common", "weight_min": 5.0, "weight_max": 10.0, "condition_type": "time_of_day", "condition_value": "Morning"},
    {"name": "Crab", "rarity": "Common", "weight_min": 0.5, "weight_max": 1.0, "condition_type": "time_of_day", "condition_value": "Afternoon"},
    {"name": "Goby", "rarity": "Common", "weight_min": 1.0, "weight_max": 2.0, "condition_type": "time_of_day", "condition_value": "Evening"},
    {"name": "Eel", "rarity": "Common", "weight_min": 0.5, "weight_max": 3.0, "condition_type": "time_of_day", "condition_value": "Night"},
    # -- Uncommon (5) --
    {"name": "Pike", "rarity": "Uncommon", "weight_min": 4.0, "weight_max": 12.0, "condition_type": "any", "condition_value": "Any"},
    {"name": "Tiger Trout", "rarity": "Uncommon", "weight_min": 1.0, "weight_max": 21.0, "condition_type": "time_of_day", "condition_value": "Morning"},
    {"name": "Tambaqui", "rarity": "Uncommon", "weight_min": 6.0, "weight_max": 21.0, "condition_type": "time_of_day", "condition_value": "Afternoon"},
    {"name": "Peacock Bass", "rarity": "Uncommon", "weight_min": 2.5, "weight_max": 22.5, "condition_type": "time_of_day", "condition_value": "Evening"},
    {"name": "Common Carp", "rarity": "Uncommon", "weight_min": 2.0, "weight_max": 21.0, "condition_type": "time_of_day", "condition_value": "Night"},
    # -- Rare (6) --
    {"name": "Catfish", "rarity": "Rare", "weight_min": 18.0, "weight_max": 40.0, "condition_type": "any", "condition_value": "Any"},
    {"name": "Blue Mahseer", "rarity": "Rare", "weight_min": 20.0, "weight_max": 42.0, "condition_type": "time_of_day", "condition_value": "Morning"},
    {"name": "Taimen", "rarity": "Rare", "weight_min": 10.0, "weight_max": 42.5, "condition_type": "time_of_day", "condition_value": "Afternoon"},
    {"name": "Twilight Barbel", "rarity": "Rare", "weight_min": 14.0, "weight_max": 42.0, "condition_type": "time_of_day", "condition_value": "Evening"},
    {"name": "Redtail Catfish", "rarity": "Rare", "weight_min": 13.0, "weight_max": 42.5, "condition_type": "time_of_day", "condition_value": "Night"},
    {"name": "King Snapper", "rarity": "Rare", "weight_min": 25.0, "weight_max": 43.0, "condition_type": "weather", "condition_value": ["Rain", "Storm"]},
    # -- Epic (6) --
    {"name": "Sun-Kissed Catfish", "rarity": "Epic", "weight_min": 30.0, "weight_max": 43.5, "condition_type": "weather", "condition_value": "Sun"},
    {"name": "Amberfin Catfish", "rarity": "Epic", "weight_min": 32.5, "weight_max": 45.0, "condition_type": "weather", "condition_value": ["Sun", "Heatwave"]},
    {"name": "Paddlefish", "rarity": "Epic", "weight_min": 35.0, "weight_max": 43.5, "condition_type": "time_of_day", "condition_value": "Morning"},
    {"name": "Goliath Tigerfish", "rarity": "Epic", "weight_min": 38.0, "weight_max": 43.5, "condition_type": "time_of_day", "condition_value": "Afternoon"},
    {"name": "Arapaima", "rarity": "Epic", "weight_min": 35.0, "weight_max": 43.0, "condition_type": "time_of_day", "condition_value": "Evening"},
    {"name": "Young Bull Shark", "rarity": "Epic", "weight_min": 38.0, "weight_max": 44.0, "condition_type": "time_of_day", "condition_value": "Night"},
    # -- Legendary (6) --
    {"name": "Elusive Marlin", "rarity": "Legendary", "weight_min": 45.0, "weight_max": 50.0, "condition_type": "weather", "condition_value": "Storm"},
    {"name": "Radiant Catfish", "rarity": "Legendary", "weight_min": 35.0, "weight_max": 47.5, "condition_type": "weather", "condition_value": "Heatwave"},
    {"name": "Alligator Gar", "rarity": "Legendary", "weight_min": 42.0, "weight_max": 46.5, "condition_type": "season", "condition_value": "Spring"},
    {"name": "Muskellunge", "rarity": "Legendary", "weight_min": 42.5, "weight_max": 45.5, "condition_type": "season", "condition_value": "Summer"},
    {"name": "Freshwater Stingray", "rarity": "Legendary", "weight_min": 40.0, "weight_max": 47.0, "condition_type": "season", "condition_value": "Autumn"},
    {"name": "Sturgeon", "rarity": "Legendary", "weight_min": 42.0, "weight_max": 46.0, "condition_type": "season", "condition_value": "Winter"},
]

# ---------------------------------------------------------------------------
# Treasure table -- all 33 treasures
# ---------------------------------------------------------------------------

TREASURE_TABLE: list[dict] = [
    # -- Common ($0.10-$0.75) --
    {"name": "Coffee Cup", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    {"name": "Old Boot", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    {"name": "Driftwood", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "weather", "condition_value": ["Wind", "Storm"]},
    {"name": "Metal Rivets", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    {"name": "Soda Can", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    {"name": "Bike Tire", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    {"name": "Soggy Chips", "rarity": "Common", "value_min": 0.10, "value_max": 0.75, "condition_type": "any", "condition_value": "Any"},
    # -- Uncommon ($1.50-$5.00) --
    {"name": "Meteorite Fragment", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Pirate Doubloon", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "weather", "condition_value": ["Wind", "Storm"]},
    {"name": "Pristine Snowflake", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "weather", "condition_value": "Snow"},
    {"name": "Vintage Harmonica", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Solar Pearl", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "weather", "condition_value": ["Sun", "Heatwave"]},
    {"name": "Dubious Tome", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Old Wristwatch", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Ancient Fossil", "rarity": "Uncommon", "value_min": 1.50, "value_max": 5.00, "condition_type": "any", "condition_value": "Any"},
    # -- Rare ($7.50-$30.00) --
    {"name": "Mysterious Locket", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Freshwater Pearl", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Bronze Goblet", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Lovely Duck", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "weather", "condition_value": ["Rain", "Storm"]},
    {"name": "Misty Duck", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "weather", "condition_value": ["Rain", "Storm"]},
    {"name": "Gold Band", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Snow Globe", "rarity": "Rare", "value_min": 7.50, "value_max": 30.00, "condition_type": "weather", "condition_value": "Snow"},
    # -- Epic ($0.10-$100.00) --
    {"name": "Message in a Bottle", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Jade Figurine", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Fancy Duck", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "weather", "condition_value": "Rain"},
    {"name": "Lost Compass", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "weather", "condition_value": "Wind"},
    {"name": "Gilded Sundial", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "weather", "condition_value": "Heatwave"},
    {"name": "Diamond", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "any", "condition_value": "Any"},
    {"name": "Frozen Tusk", "rarity": "Epic", "value_min": 0.10, "value_max": 100.00, "condition_type": "weather", "condition_value": "Snow"},
    # -- Legendary ($250.00 each) --
    {"name": "Dawnbreak Ring", "rarity": "Legendary", "value_min": 250.00, "value_max": 250.00, "condition_type": "time_of_day", "condition_value": "Morning"},
    {"name": "Solar Ring", "rarity": "Legendary", "value_min": 250.00, "value_max": 250.00, "condition_type": "time_of_day", "condition_value": "Afternoon"},
    {"name": "Twilight Ring", "rarity": "Legendary", "value_min": 250.00, "value_max": 250.00, "condition_type": "time_of_day", "condition_value": "Evening"},
    {"name": "Moonlight Ring", "rarity": "Legendary", "value_min": 250.00, "value_max": 250.00, "condition_type": "time_of_day", "condition_value": "Night"},
]

# ---------------------------------------------------------------------------
# Filter functions
# ---------------------------------------------------------------------------


def _matches_condition(entry: dict, conditions: dict) -> bool:
    """Check whether a fish/treasure entry matches the given conditions."""
    ctype = entry["condition_type"]
    cvalue = entry["condition_value"]

    if ctype == "any":
        return True

    current = conditions.get(ctype)
    if current is None:
        return False

    if isinstance(cvalue, list):
        return current in cvalue
    return current == cvalue


def get_available_fish(conditions: dict) -> list[dict]:
    """Return fish available under the given conditions.

    ``conditions`` should be a dict with keys like ``time_of_day``,
    ``season``, ``weather``.  Fish with ``condition_type="any"`` are
    always included.
    """
    return [f for f in FISH_TABLE if _matches_condition(f, conditions)]


def get_available_treasures(conditions: dict) -> list[dict]:
    """Return treasures available under the given conditions."""
    return [t for t in TREASURE_TABLE if _matches_condition(t, conditions)]


def is_legendary_window(conditions: dict) -> bool:
    """Return True if any legendary fish's condition is currently met."""
    legendary = [f for f in FISH_TABLE if f["rarity"] == "Legendary"]
    return any(_matches_condition(f, conditions) for f in legendary)


def get_competition_timing() -> dict:
    """Return competition timing based on UTC weekday.

    The competition runs from Saturday (weekday 5) 00:00 UTC through
    Sunday (weekday 6) 23:59:59 UTC.

    Returns ``{"is_active": bool, "seconds_until_start": int,
    "seconds_until_end": int}``.
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday ... 6=Sunday

    # Calculate start of this week's Saturday 00:00 UTC
    days_until_saturday = (5 - weekday) % 7
    saturday_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if weekday <= 5:
        saturday_start = saturday_start.replace(
            day=now.day + days_until_saturday
        )
    else:
        # It's Sunday -- Saturday was yesterday
        saturday_start = saturday_start.replace(day=now.day - 1)

    # End of Sunday 23:59:59
    sunday_end = saturday_start.replace(
        day=saturday_start.day + 1, hour=23, minute=59, second=59
    )

    is_active = weekday in (5, 6)

    if is_active:
        seconds_until_start = 0
        seconds_until_end = max(0, int((sunday_end - now).total_seconds()))
    else:
        seconds_until_start = max(0, int((saturday_start - now).total_seconds()))
        seconds_until_end = max(0, int((sunday_end - now).total_seconds()))

    return {
        "is_active": is_active,
        "seconds_until_start": seconds_until_start,
        "seconds_until_end": seconds_until_end,
    }
