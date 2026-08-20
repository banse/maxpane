from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

FILTER_FAMILIES = frozenset({"amount", "sequence", "cadence", "gas", "funding"})
ENS_VALUES = frozenset({"any", "set", "unset"})
WINDOW_VALUES = frozenset({"any", "grace", "judged"})
BAND_VALUES = frozenset({"any", "clean", "low", "high", "unknown"})

_INTEGER_FIELDS = (
    "join_min", "join_max", "hour_min", "hour_max", "rank_min",
    "rank_max", "points_min", "points_max", "deposits_min", "deposits_max",
)
_DECIMAL_FIELDS = ("credit_min", "credit_max", "weight_min", "weight_max")
_RANGES = (
    ("join_min", "join_max", "first_index"),
    ("hour_min", "hour_max", "first_hour"),
    ("rank_min", "rank_max", "rank"),
    ("points_min", "points_max", "points"),
    ("credit_min", "credit_max", "credit_eth"),
    ("weight_min", "weight_max", "weight_eth"),
    ("deposits_min", "deposits_max", "tx_count"),
)


class FilterValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class FilterDataUnavailable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FilterSpec:
    join_min: int | None = None
    join_max: int | None = None
    hour_min: int | None = None
    hour_max: int | None = None
    rank_min: int | None = None
    rank_max: int | None = None
    points_min: int | None = None
    points_max: int | None = None
    credit_min: float | None = None
    credit_max: float | None = None
    weight_min: float | None = None
    weight_max: float | None = None
    deposits_min: int | None = None
    deposits_max: int | None = None
    ens: str = "any"
    window: str = "any"
    band: str = "any"
    families: frozenset[str] = frozenset()
    whale: bool = False

    @property
    def active(self) -> bool:
        ranged = any(getattr(self, field) is not None for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS))
        return ranged or self.ens != "any" or self.window != "any" or self.band != "any" or bool(self.families) or self.whale


@dataclass(frozen=True, slots=True)
class FilterContext:
    families_by_address: Mapping[str, frozenset[str]] | None = None
    whale_addresses: frozenset[str] | None = None


def empty_filter_values() -> dict[str, object]:
    values = {field: "" for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS)}
    values.update(ens="any", window="any", band="any", families=frozenset(), whale=False)
    return values


def _parse_number(field: str, value: object, *, integer: bool):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise FilterValidationError(field, f"{field} must be a non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FilterValidationError(field, f"{field} must be a non-negative number") from exc
    if not math.isfinite(number) or number < 0 or (integer and not number.is_integer()):
        raise FilterValidationError(field, f"{field} must be a non-negative number")
    return int(number) if integer else number


def parse_filter_values(values: Mapping[str, object]) -> FilterSpec:
    parsed = {field: _parse_number(field, values.get(field), integer=True) for field in _INTEGER_FIELDS}
    parsed.update({field: _parse_number(field, values.get(field), integer=False) for field in _DECIMAL_FIELDS})
    for field, allowed in (("ens", ENS_VALUES), ("window", WINDOW_VALUES), ("band", BAND_VALUES)):
        value = values.get(field, "any")
        if not isinstance(value, str) or value not in allowed:
            raise FilterValidationError(field, f"invalid {field}")
        parsed[field] = value
    raw_families = values.get("families", frozenset())
    if isinstance(raw_families, str):
        raise FilterValidationError("families", "invalid evidence family")
    try:
        families = frozenset(raw_families)
    except TypeError as exc:
        raise FilterValidationError("families", "invalid evidence family") from exc
    if not families <= FILTER_FAMILIES:
        raise FilterValidationError("families", "invalid evidence family")
    parsed["families"] = families
    whale = values.get("whale", False)
    if not isinstance(whale, bool):
        raise FilterValidationError("whale", "whale must be enabled or disabled")
    parsed["whale"] = whale
    for low_field, high_field, _row_field in _RANGES:
        low, high = parsed[low_field], parsed[high_field]
        if low is not None and high is not None and low > high:
            raise FilterValidationError(low_field, f"{low_field} must not exceed {high_field}")
    return FilterSpec(**parsed)


def _row_number(row: Mapping[str, object], field: str) -> float | None:
    value = row.get(field)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def filter_rows(rows: Any, spec: FilterSpec, context: FilterContext) -> list[dict]:
    if not spec.active:
        return []
    if spec.families and context.families_by_address is None:
        raise FilterDataUnavailable("linked analysis unavailable")
    if spec.whale and context.whale_addresses is None:
        raise FilterDataUnavailable("deposit history unavailable")
    selected: list[dict] = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        rejected = False
        for low_field, high_field, row_field in _RANGES:
            low, high = getattr(spec, low_field), getattr(spec, high_field)
            if low is None and high is None:
                continue
            number = _row_number(row, row_field)
            if number is None or (low is not None and number < low) or (high is not None and number > high):
                rejected = True
                break
        if rejected:
            continue
        has_ens = isinstance(row.get("name"), str) and bool(row["name"].strip())
        if spec.ens == "set" and not has_ens or spec.ens == "unset" and has_ens:
            continue
        hour = _row_number(row, "first_hour")
        window = None if hour is None else ("grace" if hour < 24 else "judged")
        if spec.window != "any" and window != spec.window:
            continue
        raw_band = row.get("link_conf")
        band = raw_band if isinstance(raw_band, str) and raw_band in {"clean", "low", "high"} else "unknown"
        if spec.band != "any" and band != spec.band:
            continue
        address = row.get("address")
        key = address.casefold() if isinstance(address, str) else ""
        if spec.families and not (context.families_by_address.get(key, frozenset()) & spec.families):
            continue
        if spec.whale and key not in context.whale_addresses:
            continue
        selected.append(row)
    return selected


def _number_text(value: int | float) -> str:
    return f"{value:,}" if isinstance(value, int) else f"{value:g}"


def _range_text(label: str, low, high, *, unit: str = "") -> str | None:
    if low is None and high is None:
        return None
    if low is not None and high is not None:
        value = _number_text(low) if low == high else f"{_number_text(low)}-{_number_text(high)}"
        return f"{label}{value}{unit}"
    operator, value = (">=", low) if low is not None else ("<=", high)
    return f"{label}{operator}{_number_text(value)}{unit}"


def filter_summary(spec: FilterSpec) -> tuple[str, ...]:
    clauses: list[str] = []
    join = _range_text("join #", spec.join_min, spec.join_max)
    if join:
        clauses.append(join)
    if spec.hour_min is not None and spec.hour_min == spec.hour_max:
        clauses.append(f"joined hour {_number_text(spec.hour_min)}")
    else:
        hour = _range_text("joined hours ", spec.hour_min, spec.hour_max)
        if hour:
            clauses.append(hour)
    for clause in (
        _range_text("raw rank ", spec.rank_min, spec.rank_max),
        _range_text("points ", spec.points_min, spec.points_max),
        _range_text("credit ", spec.credit_min, spec.credit_max, unit=" ETH"),
        _range_text("weight ", spec.weight_min, spec.weight_max, unit=" ETH"),
        _range_text("deposits ", spec.deposits_min, spec.deposits_max),
    ):
        if clause:
            clauses.append(clause)
    if spec.whale:
        clauses.append("single deposit >=25 ETH")
    if spec.ens != "any":
        clauses.append(f"ENS {spec.ens}")
    if spec.window != "any":
        clauses.append(f"window {spec.window}")
    if spec.band != "any":
        clauses.append(f"band {spec.band}")
    if spec.families:
        clauses.append(" or ".join(family for family in ("amount", "sequence", "cadence", "gas", "funding") if family in spec.families))
    return tuple(clauses)


def preset_filter(key: str) -> FilterSpec:
    presets = {
        "1": FilterSpec(join_min=1, join_max=1_000),
        "2": FilterSpec(hour_min=0, hour_max=0),
        "3": FilterSpec(whale=True),
    }
    try:
        return presets[str(key)]
    except KeyError as exc:
        raise ValueError(f"unknown filter preset: {key}") from exc
