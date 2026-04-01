"""FrenPet battle calculations -- win probability, rewards, risk ratios.

All formulas verified against on-chain Attack events (2026-03-22).
All functions are pure: no I/O, no side effects.
"""

SCORE_DECIMALS = 10**12  # Raw on-chain scores have 12 decimal places


def calculate_win_probability(my_atk: int, target_def: int) -> float:
    """Calculate win probability: my_atk / (my_atk + target_def).

    Returns a float between 0.0 and 1.0.
    Returns 0.0 if both values are zero or negative.
    """
    total = my_atk + target_def
    if total <= 0:
        return 0.0
    return my_atk / total


def calculate_loss(my_score: float) -> float:
    """Loss is always 0.5% of own score.

    Returns the point value lost on a battle defeat.
    """
    return my_score * 0.005


def calculate_reward(
    my_score: float,
    target_score: float,
    win_prob: float,
    target_hibernated: bool = False,
) -> float:
    """Calculate potential reward based on odds.

    Two regimes depending on whether we are attacking a weaker or stronger pet:

    If win_prob >= 0.5 (attacking weaker):
        attacker_base = my_loss (no /10 penalty)
        raw_reward = attacker_base * 1.7
        cap = target_score * 0.005 * (2 if hibernated else 1)
        reward = min(raw_reward, cap)

    If win_prob < 0.5 (attacking stronger):
        attacker_base = my_loss / 10
        odds_pct = win_prob * 100
        raw_reward = attacker_base * (1 + (50 - odds_pct) + 0.7)
        cap = target_score * 0.005 * (2 if hibernated else 1) / 10
        reward = min(raw_reward, cap)
    """
    my_loss = calculate_loss(my_score)
    odds_pct = win_prob * 100
    hib_mult = 2 if target_hibernated else 1

    if odds_pct >= 50:
        # Attacking weaker: no /10 free-player penalty
        attacker_base = my_loss
        raw_reward = attacker_base * 1.7
        cap = target_score * 0.005 * hib_mult
    else:
        # Attacking stronger: /10 free-player penalty
        attacker_base = my_loss / 10 if my_loss > 0 else 0
        raw_reward = attacker_base * (1 + (50 - odds_pct) + 0.7)
        cap = target_score * 0.005 * hib_mult / 10

    return min(raw_reward, cap)


def calculate_reward_risk_ratio(
    my_score: float,
    my_atk: int,
    target_score: float,
    target_def: int,
    target_hibernated: bool = False,
) -> float:
    """Calculate reward-risk ratio for a battle.

    ratio = (could_win * win_prob) / (could_lose * lose_prob)

    Returns the ratio. Values > 1.0 indicate positive expected value.
    Returns inf if could_lose or lose_prob is zero with positive upside.
    Returns 0.0 if there is no upside.
    """
    win_prob = calculate_win_probability(my_atk, target_def)
    lose_prob = 1.0 - win_prob
    could_win = calculate_reward(my_score, target_score, win_prob, target_hibernated)
    could_lose = calculate_loss(my_score)

    if could_lose <= 0 or lose_prob <= 0:
        return float("inf") if could_win > 0 else 0.0

    return (could_win * win_prob) / (could_lose * lose_prob)


def evaluate_target(
    my_score: float,
    my_atk: int,
    my_def: int,
    target_score: float,
    target_atk: int,
    target_def: int,
    target_hibernated: bool = False,
) -> dict:
    """Full target evaluation combining all battle calculations.

    Returns a dict with:
        win_prob: Probability of winning (0-1).
        could_win: Points gained on victory.
        could_lose: Points lost on defeat.
        ratio: Reward-risk ratio.
        ev: Expected value (could_win * win_prob - could_lose * lose_prob).
        recommendation: 'strong', 'moderate', 'weak', or 'avoid'.
    """
    win_prob = calculate_win_probability(my_atk, target_def)
    lose_prob = 1.0 - win_prob
    could_win = calculate_reward(my_score, target_score, win_prob, target_hibernated)
    could_lose = calculate_loss(my_score)
    ratio = calculate_reward_risk_ratio(
        my_score, my_atk, target_score, target_def, target_hibernated
    )
    ev = (could_win * win_prob) - (could_lose * lose_prob)

    # Classify recommendation based on ratio and win probability
    if ratio >= 2.0 and win_prob >= 0.55:
        recommendation = "strong"
    elif ratio >= 1.2 and win_prob >= 0.45:
        recommendation = "moderate"
    elif ratio >= 0.8:
        recommendation = "weak"
    else:
        recommendation = "avoid"

    return {
        "win_prob": win_prob,
        "could_win": could_win,
        "could_lose": could_lose,
        "ratio": ratio,
        "ev": ev,
        "recommendation": recommendation,
    }
