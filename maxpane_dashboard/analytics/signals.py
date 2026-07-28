"""Strategic signals for decision-making."""

# Confirmed season payout split: the prize pool is shared 70/20/10 between
# the #1, #2 and #3 bakeries.  Nobody outside the top three is paid.
PRIZE_SPLIT: tuple[float, float, float] = (0.70, 0.20, 0.10)

# ``calculate_late_join_ev`` is handed a *top-three* probability, not a
# win-the-season probability.  Conditional on landing in the top three we
# treat the three places as equally likely, so the bakery's expected share
# of the pool is the mean of the split (1/3), not the whole pool.
MEAN_TOP3_SHARE: float = sum(PRIZE_SPLIT) / len(PRIZE_SPLIT)


def calculate_late_join_ev(
    prize_pool_eth: float,
    eth_price_usd: float,
    member_count: int,
    buy_in_eth: float,
    win_probability: float,
    season_active: bool = True,
) -> dict:
    """Calculate expected value of joining a season late, per member.

    The payout a *single* new member can expect is not the prize pool.  It
    is the pool times the bakery's share of the 70/20/10 split, divided by
    the number of members that share splits with them.  Multiplying the
    top-three probability by the full pool -- as this function used to --
    overstates the figure by roughly two orders of magnitude for a
    30-member bakery, and the SignalsPanel renders that number verbatim.

    Parameters
    ----------
    member_count:
        Members of the bakery being joined; the bakery's share of the pool
        is split among them.  Values below 1 are treated as 1 (you would
        be the only member).
    win_probability:
        Probability the bakery finishes in the top three.
    season_active:
        ``False`` once the season has ended.  A finished season cannot be
        joined, so the EV is exactly ``-buy_in`` regardless of the pool --
        which matters because a *finalized* season still reports a
        non-zero pool for a while.

    Returns a dict with:
        ev_usd: Expected value in USD (expected payout minus cost).
        breakeven_probability: Top-three probability needed to break even.
        recommendation: A human-readable recommendation string.
    """
    buy_in_usd = buy_in_eth * eth_price_usd
    prize_pool_usd = prize_pool_eth * eth_price_usd
    members = max(int(member_count), 1)

    # What one member collects if the bakery lands in the top three.
    payout_if_top3 = MEAN_TOP3_SHARE * prize_pool_usd / members

    if not season_active:
        return {
            "ev_usd": round(-buy_in_usd, 2),
            "breakeven_probability": 1.0,
            "recommendation": "Season over -- joining is no longer possible",
        }

    expected_payout = win_probability * payout_if_top3
    ev_usd = expected_payout - buy_in_usd

    # Breakeven probability: prob * payout_if_top3 = buy_in_usd
    if payout_if_top3 > 0:
        breakeven_probability = buy_in_usd / payout_if_top3
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
