"""Signal generators for Cat Town Fishing dashboard."""

from maxpane_dashboard.analytics.cattown_conditions import (
    get_available_fish,
    is_legendary_window,
)


def _format_countdown(seconds: int) -> str:
    """Format seconds into human-readable countdown."""
    if seconds <= 0:
        return "now"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def generate_condition_signal(conditions: dict) -> dict:
    """Current time-of-day + season. Always white (informational)."""
    tod = conditions.get("time_of_day", "Unknown")
    season = conditions.get("season", "Unknown")
    return {
        "label": "Conditions",
        "value_str": f"{tod} \u00b7 {season}",
        "indicator": "\u25cf",
        "color": "white",
    }


def generate_legendary_signal(conditions: dict) -> dict:
    """Green if any legendary fish available under current conditions, dim otherwise."""
    if is_legendary_window(conditions):
        available = get_available_fish(conditions)
        legendaries = [f["name"] for f in available if f["rarity"] == "Legendary"]
        names = ", ".join(legendaries[:2])
        return {
            "label": "Legendary",
            "value_str": f"ACTIVE: {names}",
            "indicator": "\u25cf",
            "color": "green",
        }
    return {
        "label": "Legendary",
        "value_str": "None available",
        "indicator": "\u25cb",
        "color": "dim",
    }


def generate_cutoff_signal(
    entries: list[dict],
    is_active: bool,
) -> dict:
    """Top 10 cutoff weight -- the fish you need to beat to place."""
    if not is_active or not entries:
        return {
            "label": "Top 10 Cutoff",
            "value_str": "No competition",
            "indicator": "\u25cb",
            "color": "dim",
        }

    if len(entries) < 10:
        return {
            "label": "Top 10 Cutoff",
            "value_str": f"< 10 fishers ({len(entries)} active)",
            "indicator": "\u25cf",
            "color": "green",
        }

    cutoff = entries[9].get("fish_weight_kg", 0)
    return {
        "label": "Top 10 Cutoff",
        "value_str": f"{cutoff:.1f}kg to place",
        "indicator": "\u25cf",
        "color": "yellow",
    }


def generate_recommendation(
    conditions: dict,
    entries: list[dict],
    is_active: bool,
    seconds_remaining: int,
    end_time: int = 0,
) -> str:
    """Generate a one-line tactical recommendation."""
    has_legendary = is_legendary_window(conditions)
    countdown = _format_countdown(seconds_remaining)
    num_fishers = len(entries)

    if not is_active:
        if end_time > 0 and seconds_remaining <= 0:
            return "No active competition \u2014 stack reputation for next weekend"
        return f"Competition starts in {countdown} \u2014 stack reputation"

    # Competition is active
    hours_left = seconds_remaining / 3600

    if has_legendary and hours_left > 6:
        available = get_available_fish(conditions)
        legendaries = [f["name"] for f in available if f["rarity"] == "Legendary"]
        fish = legendaries[0] if legendaries else "legendary"
        return f"Legendary window! Target {fish} for leaderboard"

    if num_fishers < 10:
        return f"Only {num_fishers} fishers \u2014 any epic+ fish could place"

    if hours_left < 2:
        cutoff = entries[9].get("fish_weight_kg", 0) if len(entries) >= 10 else 0
        return f"Final {countdown} \u2014 need >{cutoff:.0f}kg to crack top 10"

    if hours_left < 8:
        return f"{countdown} left \u2014 focus on epic+ fish in ideal conditions"

    top_weight = entries[0].get("fish_weight_kg", 0) if entries else 0
    return f"Leader at {top_weight:.1f}kg \u2014 fish during legendary windows"


# Keep these for backward compatibility with existing signal tests
def generate_competition_signal(
    is_active: bool, seconds_remaining: int, prize_pool_kibble: float
) -> dict:
    """LIVE (yellow) when active, countdown (dim) otherwise."""
    if is_active:
        if prize_pool_kibble >= 1_000_000:
            pool_str = f"{prize_pool_kibble / 1_000_000:.1f}M"
        elif prize_pool_kibble >= 1_000:
            pool_str = f"{prize_pool_kibble / 1_000:.1f}K"
        else:
            pool_str = f"{prize_pool_kibble:,.0f}"
        return {
            "label": "Competition",
            "value_str": f"LIVE \u00b7 {pool_str} KIBBLE",
            "indicator": "\u25cf",
            "color": "yellow",
        }
    countdown = _format_countdown(seconds_remaining)
    return {
        "label": "Competition",
        "value_str": f"Starts in {countdown}",
        "indicator": "\u25cb",
        "color": "dim",
    }


def generate_staking_signal(apy: float, kibble_price_change: float) -> dict:
    """APY with color thresholds: green > 20%, yellow 5-20%, dim < 5%."""
    if apy > 20:
        color = "green"
    elif apy >= 5:
        color = "yellow"
    else:
        color = "dim"
    return {
        "label": "Staking APY",
        "value_str": f"{apy:.1f}% APY",
        "indicator": "\u25cf",
        "color": color,
    }


def generate_kibble_signal(price_usd: float, change_24h: float) -> dict:
    """Price with green/red delta based on 24h change."""
    if change_24h > 0:
        color = "green"
    elif change_24h < 0:
        color = "red"
    else:
        color = "white"
    return {
        "label": "KIBBLE",
        "value_str": f"{price_usd:.8f} ETH ({change_24h:+.1f}%)",
        "indicator": "\u25cf",
        "color": color,
    }
