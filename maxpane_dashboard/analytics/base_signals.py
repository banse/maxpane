"""Trading signals for Base chain tokens."""

from __future__ import annotations


def detect_volume_spike(
    current_vol: float,
    avg_vol: float,
    threshold: float = 3.0,
) -> bool:
    """Return True if *current_vol* exceeds *threshold* times *avg_vol*.

    Returns False when *avg_vol* is zero or negative to avoid division
    issues -- there is no meaningful baseline to compare against.
    """
    if avg_vol <= 0:
        return False
    return current_vol > threshold * avg_vol


def calculate_liquidity_ratio(liquidity: float, market_cap: float) -> float:
    """Liquidity-to-market-cap ratio.

    Higher values indicate healthier liquidity.  A ratio below 0.05 is
    considered thin liquidity and should be flagged.

    Returns 0.0 when *market_cap* is zero or negative.
    """
    if market_cap <= 0:
        return 0.0
    return liquidity / market_cap


def generate_token_signal(token) -> dict:
    """Produce an aggregate signal dict for a single token.

    Returns::

        {
            "momentum": float,          # weighted momentum score
            "volume_spike": bool,        # True if volume >> average
            "liq_health": "healthy" | "thin" | "unknown",
            "overall": "bullish" | "neutral" | "bearish",
        }

    The function imports helpers from ``base_tokens`` to keep all
    momentum logic in one place.
    """
    from maxpane_dashboard.analytics.base_tokens import calculate_momentum_score, _attr

    momentum = calculate_momentum_score(token)

    # Volume spike -- requires both current and average volume fields
    current_vol = _attr(token, "volume_24h") or 0.0
    avg_vol = _attr(token, "avg_volume_24h") or 0.0
    volume_spike = detect_volume_spike(current_vol, avg_vol)

    # Liquidity health
    liquidity = _attr(token, "liquidity") or 0.0
    market_cap = _attr(token, "market_cap") or 0.0
    if market_cap > 0:
        liq_ratio = calculate_liquidity_ratio(liquidity, market_cap)
        liq_health = "healthy" if liq_ratio >= 0.05 else "thin"
    else:
        liq_health = "unknown"

    # Aggregate signal
    bullish_signals = 0
    bearish_signals = 0

    if momentum > 2.0:
        bullish_signals += 1
    elif momentum < -2.0:
        bearish_signals += 1

    if volume_spike:
        # Volume spike amplifies the momentum direction
        if momentum >= 0:
            bullish_signals += 1
        else:
            bearish_signals += 1

    if liq_health == "thin":
        bearish_signals += 1

    if bullish_signals > bearish_signals:
        overall = "bullish"
    elif bearish_signals > bullish_signals:
        overall = "bearish"
    else:
        overall = "neutral"

    return {
        "momentum": momentum,
        "volume_spike": volume_spike,
        "liq_health": liq_health,
        "overall": overall,
    }
