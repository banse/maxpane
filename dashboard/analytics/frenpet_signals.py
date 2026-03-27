"""Per-pet and portfolio strategic signals for FrenPet.

Provides battle efficiency tracking, score velocity, ranking, growth phase
determination, time-of-death monitoring, and tactical recommendations.
All functions are pure: no I/O, no side effects.
"""

import time


def calculate_battle_efficiency(wins: int, losses: int) -> float:
    """Calculate win rate as a percentage.

    Returns a float between 0.0 and 100.0.
    Returns 0.0 if no battles have been fought.
    """
    total = wins + losses
    if total == 0:
        return 0.0
    return (wins / total) * 100.0


def calculate_velocity(score_samples: list[tuple[float, float]]) -> float:
    """Calculate score velocity in points per day from time-series data.

    Uses linear regression over (timestamp_seconds, score) samples.
    Returns 0.0 if fewer than 2 samples or all timestamps are identical.
    """
    if len(score_samples) < 2:
        return 0.0

    n = len(score_samples)
    timestamps = [s[0] for s in score_samples]
    scores = [s[1] for s in score_samples]

    # Convert to days relative to first sample
    t0 = timestamps[0]
    days = [(t - t0) / 86400.0 for t in timestamps]

    if days[-1] == 0.0:
        return 0.0

    # Linear regression: slope = points per day
    sum_x = sum(days)
    sum_y = sum(scores)
    sum_xy = sum(x * y for x, y in zip(days, scores))
    sum_x2 = sum(x * x for x in days)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0.0:
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope


def calculate_rank(my_score: float, all_scores: list[float]) -> dict:
    """Calculate ranking position among all scores.

    Returns a dict with:
        rank: 1-indexed position (1 = highest score).
        total: Total number of scores.
        percentile: Percentage of scores you are above (0-100).
        distance_to_next: Points needed to reach the next higher rank.
            0.0 if already rank 1.
        distance_from_prev: Points the next lower rank needs to catch you.
            0.0 if already last place.
    """
    if not all_scores:
        return {
            "rank": 1,
            "total": 0,
            "percentile": 100.0,
            "distance_to_next": 0.0,
            "distance_from_prev": 0.0,
        }

    sorted_desc = sorted(all_scores, reverse=True)
    total = len(sorted_desc)

    # Find rank (1-indexed, higher score = better rank)
    rank = 1
    for s in sorted_desc:
        if s > my_score:
            rank += 1
        else:
            break

    # Percentile: fraction of scores at or below ours
    below_or_equal = sum(1 for s in all_scores if s <= my_score)
    percentile = (below_or_equal / total) * 100.0

    # Distance to next rank above
    if rank <= 1:
        distance_to_next = 0.0
    else:
        # The score at position rank-2 (0-indexed) in descending order
        next_higher = sorted_desc[rank - 2]
        distance_to_next = next_higher - my_score

    # Distance from the rank below
    if rank >= total:
        distance_from_prev = 0.0
    else:
        # The score at position rank (0-indexed) in descending order
        next_lower = sorted_desc[rank]
        distance_from_prev = my_score - next_lower

    return {
        "rank": rank,
        "total": total,
        "percentile": percentile,
        "distance_to_next": distance_to_next,
        "distance_from_prev": distance_from_prev,
    }


def determine_growth_phase(score: float) -> str:
    """Classify a pet's growth phase based on score.

    Returns one of:
        'Hatchling'    -- score < 100K
        'Growing'      -- 100K <= score < 200K
        'Competitive'  -- 200K <= score < 300K
        'Apex'         -- score >= 300K
    """
    if score < 100_000:
        return "Hatchling"
    elif score < 200_000:
        return "Growing"
    elif score < 300_000:
        return "Competitive"
    return "Apex"


def calculate_tod_status(tod_timestamp: int) -> dict:
    """Calculate time-of-death status from a Unix timestamp.

    Returns a dict with:
        hours_remaining: Hours until the TOD timestamp.
        status: 'safe' (>48h), 'warning' (6-48h), or 'critical' (<6h).
        color: 'green', 'amber', or 'red' corresponding to status.
    """
    now = time.time()
    seconds_remaining = tod_timestamp - now
    hours_remaining = max(seconds_remaining / 3600.0, 0.0)

    if hours_remaining > 48.0:
        status = "safe"
        color = "green"
    elif hours_remaining >= 6.0:
        status = "warning"
        color = "amber"
    else:
        status = "critical"
        color = "red"

    return {
        "hours_remaining": hours_remaining,
        "status": status,
        "color": color,
    }


def generate_pet_recommendation(
    phase: str,
    battle_efficiency: float,
    velocity: float,
    threat_level: str,
    market_conditions: dict,
) -> str:
    """Generate a one-line tactical recommendation.

    Considers growth phase, battle performance, score trajectory,
    threat exposure, and current market conditions to produce
    actionable guidance.
    """
    verdict = market_conditions.get("verdict", "balanced")
    sweet_spot = market_conditions.get("sweet_spot_count", 0)

    # Critical threat override
    if threat_level == "high" and phase != "Apex":
        return "Raise DEF or shield -- high threat exposure for your tier"

    # Phase-specific logic
    if phase == "Hatchling":
        if velocity < 0:
            return "Feed immediately -- score is declining, TOD risk rising"
        if sweet_spot > 10:
            return "Farm weak targets -- plenty of safe battles available"
        return "Focus on feeding and stat growth -- avoid risky battles"

    if phase == "Growing":
        if battle_efficiency < 50.0:
            return "Tighten target selection -- win rate below 50%"
        if verdict == "aggressive" and sweet_spot > 5:
            return "Push battles aggressively -- favorable market conditions"
        return "Balanced battling -- maintain steady growth trajectory"

    if phase == "Competitive":
        if threat_level == "medium":
            return "Consider raising DEF -- moderate threat exposure at your tier"
        if velocity > 0 and battle_efficiency >= 60.0:
            return "Maintain pressure -- strong momentum, keep battling"
        return "Selective battles only -- protect your competitive position"

    # Apex
    if battle_efficiency >= 70.0 and verdict == "aggressive":
        return "Dominate -- high efficiency plus favorable conditions"
    if velocity < 0:
        return "Defensive posture -- score declining, reduce battle frequency"
    return "Hold position -- selective high-value targets only"
