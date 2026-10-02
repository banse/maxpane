"""Shared, pure pieces of a from/to filter: parse a field, order a pair, word a range.

Hoisted from ``data/curator_list_filters.py`` (THE LIST's record filter) when
surf's RECORD filter needed the same rules (``docs/surf_record_filter_spec.md``):
a blank field is unset, a number is non-negative and finite, an integer field
takes digits only, ``from`` may not exceed ``to`` and the error names the
``from`` field. Stdlib only, no clock, no I/O.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping


class FilterValidationError(ValueError):
    """An editor value the filter cannot use; ``field`` names the control."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def parse_number(field: str, value: object, *, integer: bool) -> int | float | None:
    """``None`` for a blank field, else a non-negative number or :class:`FilterValidationError`."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise FilterValidationError(field, f"{field} must be a non-negative number")
    if integer:
        if isinstance(value, int):
            number = value
        elif isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                raise FilterValidationError(
                    field, f"{field} must be a non-negative number"
                )
            number = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
        else:
            raise FilterValidationError(
                field, f"{field} must be a non-negative number"
            )
        if number < 0:
            raise FilterValidationError(
                field, f"{field} must be a non-negative number"
            )
        return number
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FilterValidationError(
            field, f"{field} must be a non-negative number"
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise FilterValidationError(
            field, f"{field} must be a non-negative number"
        )
    return number


def check_order(parsed: Mapping[str, object], pairs: Iterable[tuple[str, str]]) -> None:
    """Raise on the first ``(low, high)`` pair whose set bounds are inverted."""
    for low_field, high_field in pairs:
        low, high = parsed.get(low_field), parsed.get(high_field)
        if low is not None and high is not None and low > high:
            raise FilterValidationError(low_field, f"{low_field} must not exceed {high_field}")


def row_number(row: Mapping[str, object], field: str, *, integer: bool) -> int | float | None:
    """A row's own number for *field*, or ``None`` when it carries none usable."""
    value = row.get(field)
    if isinstance(value, bool):
        return None
    if integer:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def number_text(value: int | float) -> str:
    return f"{value:,}" if isinstance(value, int) else f"{value:g}"


def range_text(label: str, low, high, *, unit: str = "") -> str | None:
    """``label`` + ``a-b`` / ``>=a`` / ``<=b`` / ``a``, or ``None`` when both are unset."""
    if low is None and high is None:
        return None
    if low is not None and high is not None:
        value = number_text(low) if low == high else f"{number_text(low)}-{number_text(high)}"
        return f"{label}{value}{unit}"
    operator, value = (">=", low) if low is not None else ("<=", high)
    return f"{label}{operator}{number_text(value)}{unit}"
