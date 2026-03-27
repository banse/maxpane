"""Population-level analytics for the FrenPet ecosystem.

Provides distribution analysis, market condition assessment, and threat
evaluation across the entire pet population. All functions are pure.
"""

from dashboard.analytics.frenpet_battle import calculate_win_probability


def calculate_score_distribution(pets: list) -> dict[str, int]:
    """Bucket pets into score tiers.

    Each pet is expected to be a dict with at least a 'score' key.

    Returns a dict mapping tier labels to counts:
        '0-10K', '10-50K', '50-100K', '100-200K', '200-500K', '500K+'
    """
    buckets: dict[str, int] = {
        "0-10K": 0,
        "10-50K": 0,
        "50-100K": 0,
        "100-200K": 0,
        "200-500K": 0,
        "500K+": 0,
    }

    for pet in pets:
        score = pet.get("score", 0)
        if score < 10_000:
            buckets["0-10K"] += 1
        elif score < 50_000:
            buckets["10-50K"] += 1
        elif score < 100_000:
            buckets["50-100K"] += 1
        elif score < 200_000:
            buckets["100-200K"] += 1
        elif score < 500_000:
            buckets["200-500K"] += 1
        else:
            buckets["500K+"] += 1

    return buckets


def calculate_population_stats(pets: list) -> dict:
    """Calculate aggregate statistics for the pet population.

    Each pet is expected to be a dict with 'score', 'atk', 'def', and
    optionally 'hibernated' keys.

    Returns a dict with:
        total: Total number of pets.
        active: Count of non-hibernated pets.
        hibernated: Count of hibernated pets.
        avg_score: Mean score across all pets.
        median_score: Median score across all pets.
        avg_atk: Mean attack stat.
        avg_def: Mean defense stat.
        total_score: Sum of all scores.
    """
    if not pets:
        return {
            "total": 0,
            "active": 0,
            "hibernated": 0,
            "avg_score": 0.0,
            "median_score": 0.0,
            "avg_atk": 0.0,
            "avg_def": 0.0,
            "total_score": 0.0,
        }

    scores = [p.get("score", 0) for p in pets]
    atks = [p.get("atk", 0) for p in pets]
    defs = [p.get("def", 0) for p in pets]
    hibernated_count = sum(1 for p in pets if p.get("hibernated", False))

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n % 2 == 1:
        median = sorted_scores[n // 2]
    else:
        median = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2.0

    total_score = sum(scores)

    return {
        "total": n,
        "active": n - hibernated_count,
        "hibernated": hibernated_count,
        "avg_score": total_score / n,
        "median_score": median,
        "avg_atk": sum(atks) / n,
        "avg_def": sum(defs) / n,
        "total_score": total_score,
    }


def calculate_market_conditions(
    pets: list,
    my_atk: int,
    my_def: int,
) -> dict:
    """Assess current market conditions for battle target selection.

    Each pet is expected to be a dict with 'score', 'atk', 'def', and
    optionally 'shielded', 'in_cooldown', and 'hibernated' keys.

    Returns a dict with:
        available_targets: Count of pets not shielded and not in cooldown.
        sweet_spot_count: Count of targets with 60-80% win probability.
        avg_opponent_def: Average defense among available targets.
        hibernation_rate: Fraction of population that is hibernated (0-1).
        shield_rate: Fraction of population that is shielded (0-1).
        target_density: 'high' (>20 sweet spot), 'medium' (5-20), or 'low' (<5).
        verdict: 'aggressive', 'balanced', or 'conservative'.
    """
    if not pets:
        return {
            "available_targets": 0,
            "sweet_spot_count": 0,
            "avg_opponent_def": 0.0,
            "hibernation_rate": 0.0,
            "shield_rate": 0.0,
            "target_density": "low",
            "verdict": "conservative",
        }

    total = len(pets)
    shielded_count = sum(1 for p in pets if p.get("shielded", False))
    hibernated_count = sum(1 for p in pets if p.get("hibernated", False))

    available = [
        p for p in pets
        if not p.get("shielded", False) and not p.get("in_cooldown", False)
    ]
    available_count = len(available)

    sweet_spot_count = 0
    def_values: list[int] = []
    for p in available:
        target_def = p.get("def", 0)
        def_values.append(target_def)
        wp = calculate_win_probability(my_atk, target_def)
        if 0.60 <= wp <= 0.80:
            sweet_spot_count += 1

    avg_opponent_def = sum(def_values) / len(def_values) if def_values else 0.0
    hibernation_rate = hibernated_count / total
    shield_rate = shielded_count / total

    if sweet_spot_count > 20:
        target_density = "high"
    elif sweet_spot_count >= 5:
        target_density = "medium"
    else:
        target_density = "low"

    # Verdict based on density and hibernation
    if target_density == "high" and hibernation_rate < 0.3:
        verdict = "aggressive"
    elif target_density == "low" or hibernation_rate > 0.6:
        verdict = "conservative"
    else:
        verdict = "balanced"

    return {
        "available_targets": available_count,
        "sweet_spot_count": sweet_spot_count,
        "avg_opponent_def": avg_opponent_def,
        "hibernation_rate": hibernation_rate,
        "shield_rate": shield_rate,
        "target_density": target_density,
        "verdict": verdict,
    }


def calculate_threat_level(
    pets: list,
    my_score: float,
    my_def: int,
) -> dict:
    """Assess how many pets could profitably attack you.

    A threat is any pet whose ATK gives it > 50% win probability against
    your DEF stat.

    Returns a dict with:
        threat_count: Number of threatening pets.
        threat_level: 'low' (<5), 'medium' (5-15), or 'high' (>15).
    """
    threat_count = 0
    for p in pets:
        pet_atk = p.get("atk", 0)
        wp = calculate_win_probability(pet_atk, my_def)
        if wp > 0.5:
            threat_count += 1

    if threat_count > 15:
        threat_level = "high"
    elif threat_count >= 5:
        threat_level = "medium"
    else:
        threat_level = "low"

    return {
        "threat_count": threat_count,
        "threat_level": threat_level,
    }
