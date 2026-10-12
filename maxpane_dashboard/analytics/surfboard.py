"""Pure arithmetic and command parsing for the SURFBOARD rack."""
from __future__ import annotations

import math
import re

SURFBOARD_AGENT_KEYS = ('agent', 'agent-2', 'agent-3', 'agent-4')
SEAT_TOKEN_MAX = 9_999_999_999


def seat_token(value: object) -> int | None:
    """A saved seat number within the existing ten-digit input bound."""
    return value if type(value) is int and 0 <= value <= SEAT_TOKEN_MAX else None


def count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def number(value: object) -> float | int | None:
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def ratio(numerator: object, denominator: object) -> float | None:
    n, d = number(numerator), number(denominator)
    return n / d if n is not None and d is not None and d > 0 and n <= d else None


def hourly_points(accepted: object) -> list[int] | None:
    if not isinstance(accepted, list) or len(accepted) != 24 or any(count(x) is None for x in accepted):
        return None
    return [sum(accepted[i:i + 3]) for i in range(0, 24, 3)]


def parse_command(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or len(value) > 512 or any(ord(c) < 32 for c in value):
        return None
    text = value.strip()
    if not text:
        return ("help", "")
    if re.fullmatch(r"#?[0-9]+", text):
        return ("seat", text)
    parts = text.split(maxsplit=1)
    return (parts[0].casefold(), parts[1] if len(parts) == 2 else "")


def compact_age(value: object) -> str:
    """Two elapsed units fit a rack readout without claiming subsecond precision."""
    if number(value) is None:
        return "unavailable"
    seconds = int(value)
    if seconds >= 86400:
        return f"{seconds // 86400}d {seconds % 86400 // 3600}h ago"
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m ago"
    return f"{seconds // 60}m ago" if seconds >= 60 else f"{seconds}s ago"


def recent_launch_news(events: object, *, now: object) -> list[dict]:
    """Detected launch news shared by the SWARM title and TOKENS card (one hour)."""
    if type(now) not in (int, float) or not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)
            and type(event.get("ts")) in (int, float)
            and 0 <= now - event["ts"] < 3600
            and type(event.get("number")) is int]
