"""Signal generators for Onchain Monsters dashboard.

Pure functions that return signal dicts with keys:
    label, value_str, indicator, color
"""


def generate_staking_signal(staking_ratio: float) -> dict:
    """Staking health based on percentage of supply staked."""
    pct = staking_ratio * 100 if staking_ratio <= 1.0 else staking_ratio
    if pct > 40:
        color = "green"
        status = "healthy"
    elif pct >= 20:
        color = "yellow"
        status = "moderate"
    else:
        color = "red"
        status = "low"
    return {
        "label": "Staking Rate",
        "value_str": f"{pct:.0f}% staked",
        "indicator": "\u25cf",
        "color": color,
    }


def generate_mint_velocity_signal(mints_per_day: float) -> dict:
    """Mint activity level based on daily mint rate."""
    if mints_per_day > 5:
        color = "green"
        status = "active"
    elif mints_per_day >= 1:
        color = "yellow"
        status = "steady"
    else:
        color = "dim"
        status = "quiet"
    return {
        "label": "Mint Velocity",
        "value_str": f"~{mints_per_day:.0f}/day",
        "indicator": "\u25cf",
        "color": color,
    }


def generate_burn_rate_signal(burns_per_week: float) -> dict:
    """Burn pressure based on weekly burn count."""
    if burns_per_week > 5:
        color = "red"
        status = "high"
    elif burns_per_week >= 1:
        color = "yellow"
        status = "moderate"
    else:
        color = "dim"
        status = "rare"
    return {
        "label": "Burn Rate",
        "value_str": f"~{burns_per_week:.0f}/week",
        "indicator": "\u25cf",
        "color": color,
    }


def generate_recommendation(
    staking_ratio: float,
    mints_per_day: float,
    burns_per_week: float,
    supply_trend_up: bool,
) -> str:
    """Generate a one-line strategic recommendation."""
    pct = staking_ratio * 100 if staking_ratio <= 1.0 else staking_ratio

    if pct < 20:
        return "Low staking activity -- holders may be disengaged"

    if burns_per_week > mints_per_day * 7:
        return "Supply contracting -- more burns than mints"

    if mints_per_day > 5 and supply_trend_up:
        return "Mint velocity rising -- growing interest"

    if pct > 40 and mints_per_day >= 1:
        return "Healthy staking ratio, steady mints"

    return "Collection stable -- monitoring trends"


def compute_mint_velocity(supply_history: list[tuple[float, float]]) -> float:
    """Compute mints per day from (timestamp, supply) pairs.

    Timestamps are unix seconds. Returns 0.0 if fewer than 2 data points.
    """
    if len(supply_history) < 2:
        return 0.0
    supply_history = sorted(supply_history, key=lambda p: p[0])
    t0, s0 = supply_history[0]
    t1, s1 = supply_history[-1]
    elapsed_days = (t1 - t0) / 86400
    if elapsed_days <= 0:
        return 0.0
    delta = s1 - s0
    return max(delta / elapsed_days, 0.0)


def compute_burn_rate(burn_counts: list[tuple[float, int]]) -> float:
    """Compute burns per week from (timestamp, cumulative_burned) pairs.

    Timestamps are unix seconds. Returns 0.0 if fewer than 2 data points.
    """
    if len(burn_counts) < 2:
        return 0.0
    burn_counts = sorted(burn_counts, key=lambda p: p[0])
    t0, b0 = burn_counts[0]
    t1, b1 = burn_counts[-1]
    elapsed_weeks = (t1 - t0) / 604800
    if elapsed_weeks <= 0:
        return 0.0
    delta = b1 - b0
    return max(delta / elapsed_weeks, 0.0)
