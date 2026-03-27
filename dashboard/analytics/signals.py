"""Strategic signals for decision-making."""


def calculate_late_join_ev(
    prize_pool_eth: float,
    eth_price_usd: float,
    member_count: int,
    buy_in_eth: float,
    win_probability: float,
) -> dict:
    """Calculate expected value of joining a season late.

    Returns a dict with:
        ev_usd: Expected value in USD (expected payout minus cost).
        breakeven_probability: The win probability needed to break even.
        recommendation: A human-readable recommendation string.
    """
    buy_in_usd = buy_in_eth * eth_price_usd
    prize_pool_usd = prize_pool_eth * eth_price_usd

    # EV = win_probability * prize_share - buy_in cost
    # Assume winner-take-all for simplicity; if you win, you get the full pool
    expected_payout = win_probability * prize_pool_usd
    ev_usd = expected_payout - buy_in_usd

    # Breakeven probability: prob * prize_pool_usd = buy_in_usd
    if prize_pool_usd > 0:
        breakeven_probability = buy_in_usd / prize_pool_usd
    else:
        breakeven_probability = 1.0

    if ev_usd > 0:
        recommendation = "Positive EV -- consider joining"
    elif breakeven_probability > 0.5:
        recommendation = "Negative EV -- buy-in too high relative to pool"
    else:
        recommendation = "Negative EV -- win probability too low"

    return {
        "ev_usd": round(ev_usd, 2),
        "breakeven_probability": round(breakeven_probability, 4),
        "recommendation": recommendation,
    }


def calculate_gap_analysis(
    leader_cookies: float,
    leader_rate: float,
    your_cookies: float,
    your_rate: float,
    hours_remaining: float,
) -> dict:
    """Analyze the gap between your bakery and the leader.

    Returns a dict with:
        current_gap: Current cookie deficit (positive means you are behind).
        gap_rate: Rate at which the gap is changing per hour.
            Negative means you are closing the gap.
        projected_final_gap: Projected gap at end of remaining time.
        catchable: Whether you can close the gap before time runs out.
    """
    current_gap = leader_cookies - your_cookies
    gap_rate = leader_rate - your_rate  # positive = gap widening
    projected_final_gap = current_gap + gap_rate * hours_remaining
    catchable = projected_final_gap <= 0

    return {
        "current_gap": round(current_gap, 2),
        "gap_rate": round(gap_rate, 2),
        "projected_final_gap": round(projected_final_gap, 2),
        "catchable": catchable,
    }


def calculate_leader_dominance(
    leader_cookies: float,
    second_place_cookies: float,
) -> float:
    """Calculate how dominant the leader is relative to second place.

    Returns ratio (e.g., 3.1 means leader has 3.1x the cookies of #2).
    Returns float('inf') if second place has 0 cookies.
    """
    if second_place_cookies <= 0:
        return float("inf") if leader_cookies > 0 else 1.0
    return round(leader_cookies / second_place_cookies, 2)


def generate_recommendation(
    dominance: float,
    hours_remaining: float,
    your_rank: int,
    gap_analysis: dict,
) -> str:
    """Generate a one-line strategic recommendation.

    Considers leader dominance, time pressure, current rank, and gap trajectory.
    """
    catchable = gap_analysis.get("catchable", False)
    gap_rate = gap_analysis.get("gap_rate", 0.0)

    if your_rank == 1:
        if dominance >= 3.0:
            return "Hold steady -- commanding lead, maintain production"
        elif dominance >= 1.5:
            return "Stay aggressive -- lead is solid but not insurmountable"
        else:
            return "Boost now -- lead is narrow, protect your position"

    # Not in first place
    if not catchable:
        if hours_remaining < 2.0:
            return "Concede -- gap insurmountable with time remaining"
        if dominance >= 5.0:
            return "Join #1 -- gap insurmountable"
        return "Attack leader -- only path to closing the gap"

    # Gap is catchable
    if gap_rate < 0:
        # Closing the gap
        if hours_remaining < 4.0:
            return "Boost now -- closing gap but running out of time"
        return "Stay the course -- gap is closing naturally"
    else:
        # Gap widening but still mathematically catchable
        if hours_remaining < 4.0:
            return "All-in boost + attack -- last chance to close gap"
        return "Attack leader and boost -- need to reverse gap trend"
