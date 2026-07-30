"""Signal generators for Onchain Monsters dashboard.

Pure functions that return signal dicts with keys:
    label, value_str, indicator, color
"""


def generate_staking_signal(staking_pct: float) -> dict:
    """Staking health based on percentage of supply staked.

    ``staking_pct`` is a **percentage**, not a fraction: the caller contract is
    ``OCMStakingStats.staking_ratio``, which ``ocm_client`` already computes as
    ``total_staked / net_supply * 100``. There used to be a unit-guessing
    heuristic here (``* 100`` whenever the value was ``<= 1.0``) which inverted
    exactly the readings that matter most -- a genuine 0.8% staked collection
    rendered as a green "80% staked / healthy" and suppressed the low-staking
    warning, and exactly 1.0% rendered as "100% staked" (LOW-4).
    """
    pct = staking_pct
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
    staking_pct: float,
    mints_per_day: float,
    burns_per_week: float,
    supply_trend_up: bool,
) -> str:
    """Generate a one-line strategic recommendation.

    ``staking_pct`` is a percentage (see :func:`generate_staking_signal`).
    """
    pct = staking_pct

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


def compute_burn_rate(
    burn_counts: list[tuple[float, float]],
    min_elapsed_seconds: float = 0.0,
) -> float:
    """Compute burns per week from (timestamp, cumulative_burned) pairs.

    ``burn_counts`` MUST be a cumulative-burn series -- for Onchain
    Monsters that is ``balanceOf(0xdead)`` over time
    (``OCMCache.get_burn_history()``).  It must NOT be the total-supply
    series: OCM burns are transfers to ``0xdead`` and never reduce
    ``totalSupply``, so a supply series measures *mints* and would report
    mint activity as burn pressure.

    Timestamps are unix seconds. Returns 0.0 if fewer than 2 data points.

    ``min_elapsed_seconds`` floors the observation window used for the
    extrapolation.  Passing the full retention window (7 days) makes the
    result "burns seen in the trailing week", which under-reports while
    history is still filling instead of extrapolating one burn observed
    over two hours into a false ~84/week alarm.
    """
    if len(burn_counts) < 2:
        return 0.0
    burn_counts = sorted(burn_counts, key=lambda p: p[0])
    t0, b0 = burn_counts[0]
    t1, b1 = burn_counts[-1]
    elapsed = t1 - t0
    if elapsed <= 0:
        return 0.0
    elapsed_weeks = max(elapsed, min_elapsed_seconds) / 604800
    delta = b1 - b0
    return max(delta / elapsed_weeks, 0.0)
