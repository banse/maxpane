"""Signal generators for the Base Trading Overview dashboard.

Pure functions -- no I/O, no side effects.  Each signal function returns
a dict with ``label`` and ``color`` (and optionally ``value``) that the
dashboard template can render directly.
"""

from __future__ import annotations


def compute_buy_sell_ratio(tokens: list) -> dict:
    """Aggregate buy/sell ratio across all tokens.

    Each token may carry optional ``buys_24h`` and ``sells_24h`` integer
    fields (may be ``None``).  Returns a signal dict with the computed
    ratio, a human label, and a color.
    """
    total_buys = 0
    total_sells = 0
    for t in tokens:
        buys = (t.get("buys_24h") if isinstance(t, dict) else getattr(t, "buys_24h", None))
        sells = (t.get("sells_24h") if isinstance(t, dict) else getattr(t, "sells_24h", None))
        if buys is not None:
            total_buys += buys
        if sells is not None:
            total_sells += sells

    if total_sells == 0:
        if total_buys > 0:
            return {"value": float("inf"), "label": "Bullish", "color": "green"}
        return {"value": 0.0, "label": "Neutral", "color": "yellow"}

    ratio = total_buys / total_sells

    if ratio > 1.2:
        return {"value": ratio, "label": "Bullish", "color": "green"}
    if ratio < 0.8:
        return {"value": ratio, "label": "Bearish", "color": "red"}
    return {"value": ratio, "label": "Neutral", "color": "yellow"}


def compute_volume_trend(current_volume: float, previous_volume: float) -> dict:
    """Classify volume trend as Rising / Flat / Falling.

    A >5% increase is Rising (green), >5% decrease is Falling (red),
    and anything in between is Flat (yellow).  Handles zero previous
    volume gracefully.
    """
    if previous_volume <= 0:
        if current_volume > 0:
            return {"label": "Rising", "color": "green"}
        return {"label": "Flat", "color": "yellow"}

    change = (current_volume - previous_volume) / previous_volume

    if change > 0.05:
        return {"label": "Rising", "color": "green"}
    if change < -0.05:
        return {"label": "Falling", "color": "red"}
    return {"label": "Flat", "color": "yellow"}


def compute_whale_activity(whale_count: int) -> dict:
    """Classify whale activity level by large-transaction count.

    >5 is High (green), 2-5 is Moderate (yellow), <2 is Low (dim).
    """
    if whale_count > 5:
        return {"label": "High", "color": "green"}
    if whale_count >= 2:
        return {"label": "Moderate", "color": "yellow"}
    return {"label": "Low", "color": "dim"}


def generate_recommendation(
    buy_sell_label: str,
    volume_label: str,
    whale_label: str,
) -> str:
    """Generate a one-line analytical recommendation from signal labels."""
    # All bullish
    if (
        buy_sell_label == "Bullish"
        and volume_label == "Rising"
        and whale_label == "High"
    ):
        return "Strong momentum with whale accumulation \u2014 trend favors longs"

    # All bearish
    if (
        buy_sell_label == "Bearish"
        and volume_label == "Falling"
        and whale_label == "Low"
    ):
        return "Declining volume with sell pressure \u2014 wait for reversal"

    # Whale accumulation in quiet market
    if whale_label == "High" and volume_label != "Rising":
        return "Whale accumulation in quiet market \u2014 potential breakout setup"

    # Bearish with rising volume -- selling accelerating
    if buy_sell_label == "Bearish" and volume_label == "Rising":
        return "Rising volume with sell pressure \u2014 caution advised"

    # Volume rising but mixed signals
    if volume_label == "Rising" and buy_sell_label != "Bullish":
        return "Volume rising but mixed signals \u2014 watch for confirmation"

    # Bullish ratio but volume not confirming
    if buy_sell_label == "Bullish" and volume_label != "Rising":
        return "Buy pressure without volume confirmation \u2014 watch for follow-through"

    return "Mixed signals across indicators \u2014 wait for clearer setup"


def compute_all_signals(
    tokens: list,
    prev_volume: float,
    whale_count: int,
) -> dict:
    """Orchestrator: compute every signal and return a flat dict.

    Derives ``current_volume`` by summing each token's ``volume_24h``.
    """
    # Current volume from token data
    current_volume = 0.0
    for t in tokens:
        vol = (t.get("volume_24h") if isinstance(t, dict) else getattr(t, "volume_24h", None))
        if vol is not None:
            current_volume += vol

    buy_sell = compute_buy_sell_ratio(tokens)
    volume = compute_volume_trend(current_volume, prev_volume)
    whale = compute_whale_activity(whale_count)
    rec = generate_recommendation(buy_sell["label"], volume["label"], whale["label"])

    return {
        "buy_sell_ratio": buy_sell["value"],
        "buy_sell_label": buy_sell["label"],
        "buy_sell_color": buy_sell["color"],
        "volume_label": volume["label"],
        "volume_color": volume["color"],
        "whale_label": whale["label"],
        "whale_color": whale["color"],
        "recommendation": rec,
    }
