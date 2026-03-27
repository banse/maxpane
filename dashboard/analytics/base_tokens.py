"""Base chain token analytics -- movers, volume, momentum."""

from __future__ import annotations

import math


def get_top_movers(
    tokens: list,
    key: str = "price_change_24h",
    limit: int = 5,
) -> tuple[list, list]:
    """Return (gainers, losers) sorted by absolute price change.

    Each list has up to ``limit`` entries.
    *key* can be: price_change_5m, price_change_1h, price_change_24h.
    Tokens whose change value is None are excluded.
    """
    valid = [t for t in tokens if _attr(t, key) is not None]
    sorted_asc = sorted(valid, key=lambda t: _attr(t, key))
    sorted_desc = sorted(valid, key=lambda t: _attr(t, key), reverse=True)

    gainers = [t for t in sorted_desc[:limit] if _attr(t, key) > 0]
    losers = [t for t in sorted_asc[:limit] if _attr(t, key) < 0]

    return gainers, losers


def get_volume_leaders(tokens: list, limit: int = 10) -> list:
    """Return tokens sorted by 24h volume descending, top ``limit``."""
    valid = [t for t in tokens if (_attr(t, "volume_24h") or 0) > 0]
    return sorted(valid, key=lambda t: _attr(t, "volume_24h"), reverse=True)[:limit]


def format_price(price: float) -> str:
    """Smart price formatting with subscript notation for many leading zeros.

    * >= $1       : ``$1.23``
    * >= $0.01    : ``$0.0123``
    * >= $0.000001: ``$0.000042``
    * <  $0.000001: ``$0.0₅42`` (subscript digit = count of leading zeros after '0.')
    """
    if price is None or math.isnan(price):
        return "$0.00"
    if price == 0:
        return "$0.00"
    if price < 0:
        return "-" + format_price(-price)

    if price >= 1.0:
        return f"${price:,.2f}"

    if price >= 0.01:
        return f"${price:.4f}"

    # Count leading zeros after "0."
    leading_zeros = -math.floor(math.log10(price)) - 1

    if leading_zeros <= 4:
        # Show full zeros: $0.000042
        sig_digits = max(2, 6 - leading_zeros)
        return f"${price:.{leading_zeros + sig_digits}f}"

    # Subscript notation: $0.0₅42
    subscript_map = "₀₁₂₃₄₅₆₇₈₉"
    subscript = "".join(subscript_map[int(d)] for d in str(leading_zeros))
    # Extract 2-3 significant digits (e.g. 0.000000042 -> "42")
    shifted = price * (10 ** (leading_zeros + 2))
    sig_part = str(int(round(shifted))).rstrip("0") or "0"
    return f"$0.0{subscript}{sig_part}"


def format_market_cap(mcap: float) -> str:
    """Format market cap: $48.2M, $1.2B, $892K, etc."""
    return _format_large_number(mcap)


def format_volume(vol: float) -> str:
    """Format volume: $48.2M, $1.2B, $892K, etc."""
    return _format_large_number(vol)


def format_change(pct: float | None) -> str:
    """Format percentage change with color markup.

    Returns strings like ``[green]+32.4%[/green]``,
    ``[red]-8.1%[/red]``, or ``[dim]--[/dim]`` for None.
    """
    if pct is None:
        return "[dim]—[/dim]"
    if pct == 0:
        return "[dim]0.0%[/dim]"
    if pct > 0:
        return f"[green]+{pct:.1f}%[/green]"
    return f"[red]{pct:.1f}%[/red]"


def calculate_momentum_score(token) -> float:
    """Weighted momentum score from multi-timeframe price changes.

    Weights: 5m = 0.5, 1h = 0.3, 24h = 0.2 (recent changes matter more).
    Returns a score where higher = stronger upward momentum.
    Treats None values as 0.
    """
    change_5m = _attr(token, "price_change_5m") or 0.0
    change_1h = _attr(token, "price_change_1h") or 0.0
    change_24h = _attr(token, "price_change_24h") or 0.0

    return change_5m * 0.5 + change_1h * 0.3 + change_24h * 0.2


def classify_token_status(token) -> str:
    """Classify token as pumping, recovering, stable, dumping, or crashed.

    Classification logic based on multi-timeframe price changes:
    - pumping:    5m > 5 AND 1h > 10
    - recovering: 24h < -10 AND 1h > 0
    - crashed:    24h < -30
    - dumping:    1h < -5 AND 5m < 0
    - stable:     everything else
    """
    change_5m = _attr(token, "price_change_5m") or 0.0
    change_1h = _attr(token, "price_change_1h") or 0.0
    change_24h = _attr(token, "price_change_24h") or 0.0

    if change_5m > 5 and change_1h > 10:
        return "pumping"
    if change_24h < -10 and change_1h > 0:
        return "recovering"
    if change_24h < -30:
        return "crashed"
    if change_1h < -5 and change_5m < 0:
        return "dumping"
    return "stable"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _attr(obj, name: str):
    """Access an attribute by name, supporting both objects and dicts."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _format_large_number(value: float) -> str:
    """Format a number as $X.XB / $X.XM / $X.XK / $X."""
    if value is None or math.isnan(value):
        return "$0"
    if value < 0:
        return "-" + _format_large_number(-value)
    if value == 0:
        return "$0"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"
