"""Signal generators for Defense of the Agents dashboard.

Pure functions that return signal dicts with keys:
    label, value_str, indicator, color
"""

from __future__ import annotations


def compute_faction_balance(human_units: int, orc_units: int) -> dict:
    """Faction balance based on total unit counts.

    Green 'Human dominant' if human exceeds orc by >20%.
    Red 'Orc dominant' if orc exceeds human by >20%.
    Yellow 'Contested' otherwise.
    """
    total = human_units + orc_units
    if total == 0:
        return {
            "label": "Faction Balance",
            "value_str": "Contested (0 vs 0)",
            "indicator": "\u25cf",
            "color": "yellow",
        }

    # Check if one side exceeds the other by more than 20%
    if human_units > orc_units * 1.2:
        color = "green"
        status = "Human dominant"
    elif orc_units > human_units * 1.2:
        color = "red"
        status = "Orc dominant"
    else:
        color = "yellow"
        status = "Contested"

    return {
        "label": "Faction Balance",
        "value_str": f"{status} ({human_units} vs {orc_units})",
        "indicator": "\u25cf",
        "color": color,
    }


def compute_lane_pressure(top_fl: int, mid_fl: int, bot_fl: int) -> dict:
    """Lane pressure based on average frontline position across 3 lanes.

    Frontline values range from -100 (deep orc territory) to +100 (deep human push).
    Green 'Human pushing' if avg > +20.
    Red 'Orc pushing' if avg < -20.
    Yellow 'Stalemate' otherwise.
    """
    avg = (top_fl + mid_fl + bot_fl) / 3.0

    if avg > 20:
        color = "green"
        status = "Human pushing"
    elif avg < -20:
        color = "red"
        status = "Orc pushing"
    else:
        color = "yellow"
        status = "Stalemate"

    return {
        "label": "Lane Pressure",
        "value_str": f"{status} ({avg:+.0f} avg)",
        "indicator": "\u25cf",
        "color": color,
    }


def compute_hero_advantage(human_alive: int, orc_alive: int) -> dict:
    """Hero advantage based on alive hero counts per faction.

    Green 'Human edge' if human has 2+ more alive.
    Red 'Orc edge' if orc has 2+ more alive.
    Yellow 'Even' otherwise.
    """
    diff = human_alive - orc_alive

    if diff >= 2:
        color = "green"
        status = "Human edge"
    elif diff <= -2:
        color = "red"
        status = "Orc edge"
    else:
        color = "yellow"
        status = "Even"

    return {
        "label": "Hero Advantage",
        "value_str": f"{status} ({human_alive} vs {orc_alive})",
        "indicator": "\u25cf",
        "color": color,
    }


def generate_recommendation(
    human_units: int,
    orc_units: int,
    avg_frontline: float,
    human_alive: int,
    orc_alive: int,
    human_base_hp: int,
    orc_base_hp: int,
    base_max_hp: int,
    winner: str | None,
) -> str:
    """Generate a one-line strategic recommendation based on game state."""
    # Game over
    if winner:
        faction = winner.capitalize() if winner[0].islower() else winner
        return f"{faction} victory \u2014 game complete"

    # Base critical (<30% HP)
    human_base_pct = (human_base_hp / base_max_hp * 100) if base_max_hp > 0 else 100
    orc_base_pct = (orc_base_hp / base_max_hp * 100) if base_max_hp > 0 else 100

    if human_base_pct < 30:
        return f"Human base at {human_base_pct:.0f}% \u2014 Orc closing in for the win"
    if orc_base_pct < 30:
        return f"Orc base at {orc_base_pct:.0f}% \u2014 Human closing in for the win"

    # Determine faction leanings
    human_units_favored = human_units > orc_units * 1.2 if (human_units + orc_units) > 0 else False
    orc_units_favored = orc_units > human_units * 1.2 if (human_units + orc_units) > 0 else False
    human_lane_favored = avg_frontline > 20
    orc_lane_favored = avg_frontline < -20
    human_hero_favored = (human_alive - orc_alive) >= 2
    orc_hero_favored = (orc_alive - human_alive) >= 2

    # All human-favored
    if human_hero_favored and human_lane_favored:
        return (
            f"{human_alive}v{orc_alive} hero advantage with "
            f"+{avg_frontline:.0f} avg frontline \u2014 human victory likely"
        )

    # All orc-favored
    if orc_hero_favored and orc_lane_favored:
        return "Orc pushing 3 lanes with hero majority \u2014 human base threatened"

    # Mixed signals
    any_human = human_units_favored or human_lane_favored or human_hero_favored
    any_orc = orc_units_favored or orc_lane_favored or orc_hero_favored
    if any_human and any_orc:
        return "Lane pressure split \u2014 contested battlefront"

    # Single-side advantage but not all
    if any_human or any_orc:
        return "Lane pressure split \u2014 contested battlefront"

    return "Game in progress \u2014 factions evenly matched"
