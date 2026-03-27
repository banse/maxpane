"""Calculate cookie production rates, velocity, and trends."""


def calculate_production_rate(cookie_samples: list[tuple[float, float]]) -> float:
    """Given [(timestamp, cookie_count), ...], calculate cookies/hour.

    Uses linear regression over the provided samples for smoothing.
    Returns 0.0 if insufficient data (<2 samples).
    """
    if len(cookie_samples) < 2:
        return 0.0

    n = len(cookie_samples)
    timestamps = [s[0] for s in cookie_samples]
    counts = [s[1] for s in cookie_samples]

    # Convert timestamps to hours relative to the first sample
    t0 = timestamps[0]
    hours = [(t - t0) / 3600.0 for t in timestamps]

    # If all timestamps are the same, no rate can be computed
    if hours[-1] == 0.0:
        return 0.0

    # Linear regression: rate = slope of best-fit line (cookies per hour)
    sum_x = sum(hours)
    sum_y = sum(counts)
    sum_xy = sum(x * y for x, y in zip(hours, counts))
    sum_x2 = sum(x * x for x in hours)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0.0:
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return max(slope, 0.0)


def classify_trend(rates: list[float]) -> str:
    """Given recent rate measurements, classify as 'rising', 'falling', or 'flat'.

    Compare last 3 samples. Rising if latest > average of previous by >5%.
    Falling if latest < average of previous by >5%. Otherwise flat.
    Returns 'flat' if fewer than 2 samples.
    """
    if len(rates) < 2:
        return "flat"

    # Use last 3 samples (or fewer if not enough)
    window = rates[-3:] if len(rates) >= 3 else rates[:]

    previous = window[:-1]
    latest = window[-1]

    avg_previous = sum(previous) / len(previous)

    if avg_previous == 0.0:
        if latest > 0.0:
            return "rising"
        return "flat"

    change_ratio = (latest - avg_previous) / avg_previous

    if change_ratio > 0.05:
        return "rising"
    elif change_ratio < -0.05:
        return "falling"
    return "flat"


def format_rate(rate: float) -> str:
    """Format rate as human string: '+5,800/hr', '+120/hr', etc.

    Always includes a '+' prefix for positive rates and '-' for negative.
    Rounds to nearest integer and uses comma separators.
    """
    rounded = round(rate)
    if rounded >= 0:
        return f"+{rounded:,}/hr"
    return f"{rounded:,}/hr"
