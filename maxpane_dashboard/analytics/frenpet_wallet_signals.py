"""Wallet-level strategic signals for FrenPet.

Computes pool share, APR, win rates, FP earning classification,
and pet-level analytics. All functions are pure: no I/O, no side effects.
"""


def compute_pool_share(user_shares: int, total_shares: int) -> float:
    """Return pool share as percentage (0.0-100.0).

    Returns 0.0 if total_shares is 0.
    """
    if total_shares == 0:
        return 0.0
    return (user_shares / total_shares) * 100.0


def compute_apr(
    total_eth_wei: int,
    user_shares: int,
    fp_price_eth: float,
    days_elapsed: float,
) -> float:
    """Annualized return estimate based on ETH earned and FP staked.

    Returns 0.0 if insufficient data (zero days, zero shares, or zero price).
    """
    if days_elapsed <= 0 or user_shares <= 0 or fp_price_eth <= 0:
        return 0.0

    eth_earned = total_eth_wei / 1e18
    cost_basis_eth = user_shares * fp_price_eth
    if cost_basis_eth <= 0:
        return 0.0

    daily_return = eth_earned / cost_basis_eth / days_elapsed
    return daily_return * 365.0 * 100.0


def compute_win_rate(wins: int, losses: int) -> float:
    """Combined win rate as percentage (0.0-100.0).

    Returns 0.0 if no battles have been fought.
    """
    total = wins + losses
    if total == 0:
        return 0.0
    return (wins / total) * 100.0


def classify_fp_rate(total_fp_per_second: int) -> tuple[str, str]:
    """Classify FP earning rate.

    Returns (status_label, color):
        ('earning', 'green') if actively earning,
        ('idle', 'dim') if not earning.
    """
    if total_fp_per_second > 0:
        return ("earning", "green")
    return ("idle", "dim")


def classify_win_rate(rate: float) -> tuple[str, str]:
    """Classify win rate into performance tiers.

    Returns (status_label, color):
        ('strong', 'green') if >= 60%,
        ('balanced', 'yellow') if 40-60%,
        ('weak', 'red') if < 40%.
    """
    if rate >= 60.0:
        return ("strong", "green")
    if rate >= 40.0:
        return ("balanced", "yellow")
    return ("weak", "red")


def classify_pool_share(pct: float) -> tuple[str, str]:
    """Classify pool share into size tiers.

    Returns (status_label, color):
        ('large', 'green') if >= 1.0%,
        ('medium', 'yellow') if >= 0.1%,
        ('small', 'dim') otherwise.
    """
    if pct >= 1.0:
        return ("large", "green")
    if pct >= 0.1:
        return ("medium", "yellow")
    return ("small", "dim")


def generate_wallet_recommendation(
    pool_share_pct: float,
    win_rate: float,
    fp_per_second: int,
    total_eth_wei: int,
) -> str:
    """One-line recommendation string based on wallet signals.

    Considers pool share, battle performance, earning rate,
    and accumulated ETH to produce actionable guidance.
    """
    if fp_per_second == 0 and total_eth_wei == 0:
        return "Inactive wallet -- stake FP and start battling to earn ETH"

    if fp_per_second == 0:
        return "FP earning stopped -- check pet status and feed if needed"

    if win_rate < 40.0:
        return "Low win rate -- review battle targets and pet stats"

    if pool_share_pct >= 1.0 and win_rate >= 60.0:
        return "Strong position -- maintain current strategy"

    if pool_share_pct < 0.1:
        return "Small pool share -- consider staking more FP to increase rewards"

    return "Balanced portfolio -- look for opportunities to boost win rate"


def find_top_earner(pets: list) -> dict | None:
    """Find the pet with the highest score.

    Returns a dict with name, score, wins, losses, win_rate.
    Returns None if the pet list is empty.
    """
    if not pets:
        return None

    best = max(pets, key=lambda p: p.get("score", 0))
    wins = best.get("wins", 0)
    losses = best.get("losses", 0)
    total = wins + losses
    win_rate = (wins / total * 100.0) if total > 0 else 0.0

    return {
        "name": best.get("name", "Unknown"),
        "score": best.get("score", 0),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
    }


def find_most_efficient(pets: list, min_battles: int = 10) -> dict | None:
    """Find the pet with the best win rate among those with enough battles.

    Only considers pets with at least min_battles total battles.
    Returns a dict with name, score, wins, losses, win_rate.
    Returns None if no pets meet the minimum battles threshold.
    """
    qualified = [
        p for p in pets
        if (p.get("wins", 0) + p.get("losses", 0)) >= min_battles
    ]
    if not qualified:
        return None

    def _win_rate(p: dict) -> float:
        wins = p.get("wins", 0)
        total = wins + p.get("losses", 0)
        return wins / total if total > 0 else 0.0

    best = max(qualified, key=_win_rate)
    wins = best.get("wins", 0)
    losses = best.get("losses", 0)
    total = wins + losses
    win_rate = (wins / total * 100.0) if total > 0 else 0.0

    return {
        "name": best.get("name", "Unknown"),
        "score": best.get("score", 0),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
    }
