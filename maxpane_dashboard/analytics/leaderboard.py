"""Leaderboard analytics and formatting."""


def calculate_prize_per_member(prize_pool_usd: float, member_count: int) -> float:
    """Calculate prize pool divided evenly among members.

    Returns 0.0 if member_count is 0.
    """
    if member_count <= 0:
        return 0.0
    return prize_pool_usd / member_count


def format_gap(cookies: float, leader_cookies: float) -> str:
    """Format the gap between a bakery and the leader.

    Returns a dash for the leader (when cookies == leader_cookies).
    Otherwise returns a formatted negative gap like '-94.6K' or '-1.2M'.
    """
    if cookies >= leader_cookies:
        return "\u2014"

    gap = cookies - leader_cookies  # negative value
    return _format_signed_number(gap)


def format_cookies(cookies: float) -> str:
    """Format cookie count for display.

    Examples: 139300 -> '139.3K', 1500 -> '1.5K', 800 -> '800',
              1500000 -> '1.5M', 0 -> '0'.
    """
    if cookies < 0:
        return "-" + format_cookies(abs(cookies))

    if cookies < 1000:
        # Show as integer for values under 1K
        return f"{int(round(cookies))}"
    elif cookies < 1_000_000:
        value = cookies / 1000.0
        if value >= 100:
            # 139.3K -- one decimal for >=100K
            return f"{value:.1f}K"
        elif value >= 10:
            # 12.5K -- one decimal for >=10K
            return f"{value:.1f}K"
        else:
            # 1.5K -- one decimal for >=1K
            return f"{value:.1f}K"
    else:
        value = cookies / 1_000_000.0
        return f"{value:.1f}M"


def _format_signed_number(value: float) -> str:
    """Format a signed number with K/M suffix."""
    abs_value = abs(value)
    sign = "-" if value < 0 else "+"

    if abs_value < 1000:
        return f"{sign}{int(round(abs_value))}"
    elif abs_value < 1_000_000:
        formatted = abs_value / 1000.0
        return f"{sign}{formatted:.1f}K"
    else:
        formatted = abs_value / 1_000_000.0
        return f"{sign}{formatted:.1f}M"
