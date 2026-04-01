"""Cat Town economy analytics -- pure math functions, no I/O."""


def calculate_burn_rate(burn_amounts: list[float], span_hours: float) -> float:
    """Total KIBBLE burned / span_hours.

    Returns 0.0 if span_hours <= 0 or the list is empty.
    """
    if span_hours <= 0 or not burn_amounts:
        return 0.0
    return sum(burn_amounts) / span_hours


def calculate_fishing_volume(catch_count: int, span_hours: float) -> float:
    """Casts per hour.

    Returns 0.0 if span_hours <= 0.
    """
    if span_hours <= 0:
        return 0.0
    return catch_count / span_hours


def calculate_prize_pool_growth(
    snapshots: list[tuple[float, float]], hours: float
) -> float:
    """KIBBLE added per hour based on (timestamp, amount) pairs.

    Uses first and last snapshot to compute the rate.
    Returns 0.0 if fewer than 2 snapshots or hours <= 0.
    """
    if len(snapshots) < 2 or hours <= 0:
        return 0.0
    snapshots_sorted = sorted(snapshots, key=lambda s: s[0])
    amount_delta = snapshots_sorted[-1][1] - snapshots_sorted[0][1]
    return amount_delta / hours


def calculate_staking_apy(total_staked: float, weekly_revenue: float) -> float:
    """Annualized staking yield as a percentage.

    Formula: (weekly_revenue / total_staked) * 52 * 100.
    Returns 0.0 if total_staked <= 0.
    """
    if total_staked <= 0:
        return 0.0
    return (weekly_revenue / total_staked) * 52 * 100


def calculate_kibble_burn_pct(burned: float, total_supply: float) -> float:
    """Percentage of total supply that has been burned.

    Formula: (burned / total_supply) * 100.
    Returns 0.0 if total_supply <= 0.
    """
    if total_supply <= 0:
        return 0.0
    return (burned / total_supply) * 100


def calculate_identification_ev(kibble_price_usd: float) -> dict:
    """Calculate the revenue split for a cat identification action.

    Based on a $0.25 cost and the 70/10/10/7.5/2.5 revenue split:
      - 70% -> treasure pool
      - 10% -> stakers
      - 10% -> leaderboard
      - 7.5% -> treasury
      - 2.5% -> burn

    Returns a dict with each share in USD.
    """
    cost_usd = 0.25
    return {
        "cost_usd": cost_usd,
        "treasure_pool_share": cost_usd * 0.70,
        "staker_share": cost_usd * 0.10,
        "leaderboard_share": cost_usd * 0.10,
        "treasury_share": cost_usd * 0.075,
        "burn_share": cost_usd * 0.025,
    }


def format_kibble(amount: float) -> str:
    """Human-readable KIBBLE formatting.

    >= 1M  -> '1.2M'
    >= 1K  -> '450.0K'
    else   -> '1,234'
    """
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return f"{amount:,.0f}"
