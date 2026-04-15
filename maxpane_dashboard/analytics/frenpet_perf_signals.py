"""Performance-level strategic signals for FrenPet.

Computes aggregate win rates, velocity classification, weakest-pet
identification, and performance recommendations.
All functions are pure: no I/O, no side effects.
"""


def compute_avg_win_rate(pets: list) -> float:
    """Combined win rate across all pets as percentage (0.0-100.0).

    Sums wins and battles across every pet, then divides.
    Returns 0.0 if there are no battles.
    """
    total_wins = sum(p.win_qty for p in pets)
    total_battles = sum(p.win_qty + p.loss_qty for p in pets)
    if total_battles == 0:
        return 0.0
    return (total_wins / total_battles) * 100.0


def compute_total_velocity(pet_velocities: dict[int, float]) -> float:
    """Sum of per-pet velocities (pts/hr).

    Returns 0.0 if the dict is empty.
    """
    return sum(pet_velocities.values())


def classify_velocity(velocity: float) -> tuple[str, str]:
    """Classify combined score velocity.

    Returns (status_label, color):
        ('growing', 'green')   if velocity > 0,
        ('stalled', 'dim')     if velocity == 0,
        ('declining', 'red')   if velocity < 0.
    """
    if velocity > 0:
        return ("growing", "green")
    if velocity < 0:
        return ("declining", "red")
    return ("stalled", "dim")


def classify_avg_win_rate(rate: float) -> tuple[str, str]:
    """Classify average win rate into performance tiers.

    Returns (status_label, color):
        ('strong', 'green')    if >= 60%,
        ('balanced', 'yellow') if 40-60%,
        ('weak', 'red')        if < 40%.
    """
    if rate >= 60.0:
        return ("strong", "green")
    if rate >= 40.0:
        return ("balanced", "yellow")
    return ("weak", "red")


def find_weakest_pet(pets: list, min_battles: int = 10) -> dict | None:
    """Find the pet with the lowest win rate among those with enough battles.

    Only considers pets with at least *min_battles* total battles.
    Returns a dict with ``name`` and ``win_rate``, or ``None`` if no pets
    meet the minimum battles threshold.
    """
    qualified = [
        p for p in pets if (p.win_qty + p.loss_qty) >= min_battles
    ]
    if not qualified:
        return None

    def _win_rate(p) -> float:
        total = p.win_qty + p.loss_qty
        return (p.win_qty / total) if total > 0 else 0.0

    weakest = min(qualified, key=_win_rate)
    total = weakest.win_qty + weakest.loss_qty
    win_rate = (weakest.win_qty / total * 100.0) if total > 0 else 0.0

    return {
        "name": weakest.name,
        "win_rate": round(win_rate, 1),
    }


def classify_weakest(win_rate: float) -> tuple[str, str]:
    """Classify weakest-pet win rate.

    Returns (status_label, color):
        ('strong', 'green')     if >= 70%,
        ('ok', 'yellow')        if 60-70%,
        ('needs work', 'red')   if < 60%.
    """
    if win_rate >= 70.0:
        return ("strong", "green")
    if win_rate >= 60.0:
        return ("ok", "yellow")
    return ("needs work", "red")


def generate_perf_recommendation(
    avg_win_rate: float,
    total_velocity: float,
    weakest: dict | None,
) -> str:
    """One-line recommendation based on performance signals.

    Considers win rate, velocity trend, and weakest pet to produce
    actionable guidance.
    """
    if avg_win_rate == 0.0 and total_velocity == 0.0:
        return "No battle data -- start battling to generate performance signals"

    if total_velocity < 0:
        return "Score declining -- review battle targets and consider resting weak pets"

    if weakest is not None and weakest["win_rate"] < 50.0:
        return f"{weakest['name']} dragging avg down -- retrain or rest this pet"

    if avg_win_rate < 40.0:
        return "Low overall win rate -- reassess matchups across all pets"

    if avg_win_rate >= 70.0 and total_velocity > 0:
        return "Excellent performance -- maintain current strategy"

    if avg_win_rate >= 60.0:
        return "Strong win rate -- look for velocity improvements"

    return "Balanced performance -- focus on improving weakest pets"


def color_velocity(velocity: float) -> str:
    """Return a color string for per-pet velocity display.

    'green'  if >= 200,
    'cyan'   if >= 100,
    'yellow' if >= 50,
    'dim'    if < 50.
    """
    if velocity >= 200:
        return "green"
    if velocity >= 100:
        return "cyan"
    if velocity >= 50:
        return "yellow"
    return "dim"
