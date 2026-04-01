"""Expected value calculations for boosts and attacks."""

# (id, name, type, success_rate, cookie_cost, multiplier_bps, duration_seconds)
# multiplier_bps: 10000 = 1.0x (no change), 12500 = 1.25x, 20000 = 2.0x
# For attacks, multiplier_bps represents the penalty (2500 = 25% reduction, 10000 = 100%)
# cookie_cost is in display units
BOOST_CATALOG: list[tuple[int, str, str, float, int, int, int]] = [
    (1, "Ad Campaign", "boost", 0.60, 120, 12500, 14400),
    (2, "Motivational Speech", "boost", 0.40, 80, 12500, 14400),
    (3, "Secret Recipe", "boost", 0.35, 250, 15000, 28800),
    (4, "Chef's Help", "boost", 0.50, 450, 20000, 28800),
    (5, "Recipe Sabotage", "attack", 0.60, 120, 2500, 14400),
    (6, "Fake Partnership", "attack", 0.35, 60, 2500, 14400),
    (7, "Kitchen Fire", "attack", 0.20, 320, 10000, 7200),
    (8, "Supplier Strike", "attack", 0.30, 220, 5000, 14400),
]

_CATALOG_BY_ID: dict[int, tuple[int, str, str, float, int, int, int]] = {
    entry[0]: entry for entry in BOOST_CATALOG
}


def _get_entry(entry_id: int) -> tuple[int, str, str, float, int, int, int]:
    """Look up a catalog entry by ID. Raises KeyError if not found."""
    if entry_id not in _CATALOG_BY_ID:
        raise KeyError(f"Unknown boost/attack ID: {entry_id}")
    return _CATALOG_BY_ID[entry_id]


def calculate_boost_ev(boost_id: int, bakery_production_rate: float) -> float:
    """Calculate expected value of a boost in cookie units.

    EV = success_rate * production_rate * (multiplier - 1) * duration_hours - cookie_cost

    The multiplier is in basis points (10000 = 1.0x, 12500 = 1.25x, 20000 = 2.0x).
    production_rate is in cookies/hour. Returns EV in display-unit cookies.
    """
    entry = _get_entry(boost_id)
    _, _, entry_type, success_rate, cookie_cost, multiplier_bps, duration_seconds = entry

    if entry_type != "boost":
        raise ValueError(f"ID {boost_id} is an attack, not a boost")

    multiplier = multiplier_bps / 10000.0
    duration_hours = duration_seconds / 3600.0

    ev = success_rate * bakery_production_rate * (multiplier - 1.0) * duration_hours - cookie_cost
    return ev


def calculate_attack_ev(attack_id: int, target_production_rate: float) -> float:
    """Calculate gap-closure-per-cookie for an attack.

    gap_closure = success_rate * target_rate * penalty * duration_hours
    Returns gap_closure / cookie_cost (ratio, higher is better).

    The penalty is derived from multiplier_bps (2500 = 0.25, 10000 = 1.0).
    target_production_rate is in cookies/hour.
    """
    entry = _get_entry(attack_id)
    _, _, entry_type, success_rate, cookie_cost, multiplier_bps, duration_seconds = entry

    if entry_type != "attack":
        raise ValueError(f"ID {attack_id} is a boost, not an attack")

    penalty = multiplier_bps / 10000.0
    duration_hours = duration_seconds / 3600.0

    gap_closure = success_rate * target_production_rate * penalty * duration_hours
    if cookie_cost == 0:
        return float("inf") if gap_closure > 0 else 0.0
    return gap_closure / cookie_cost


def rank_boosts(bakery_production_rate: float) -> list[tuple[str, float]]:
    """Return boosts ranked by EV, best first.

    Returns a list of (name, ev) tuples sorted by descending EV.
    """
    results: list[tuple[str, float]] = []
    for entry in BOOST_CATALOG:
        entry_id, name, entry_type, *_ = entry
        if entry_type != "boost":
            continue
        ev = calculate_boost_ev(entry_id, bakery_production_rate)
        results.append((name, ev))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def rank_attacks(target_production_rate: float) -> list[tuple[str, float]]:
    """Return attacks ranked by gap-closure-per-cookie, best first.

    Returns a list of (name, ratio) tuples sorted by descending ratio.
    """
    results: list[tuple[str, float]] = []
    for entry in BOOST_CATALOG:
        entry_id, name, entry_type, *_ = entry
        if entry_type != "attack":
            continue
        ratio = calculate_attack_ev(entry_id, target_production_rate)
        results.append((name, ratio))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
