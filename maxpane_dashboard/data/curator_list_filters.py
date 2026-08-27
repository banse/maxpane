from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

FILTER_FAMILIES = frozenset({"amount", "sequence", "cadence", "gas", "funding"})
ENS_VALUES = frozenset({"any", "set", "unset"})
WINDOW_VALUES = frozenset({"any", "grace", "judged"})
BAND_VALUES = frozenset({"any", "clean", "low", "high", "review", "unknown"})

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


NFT_CHAINS = frozenset({"ethereum", "base"})
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True, slots=True)
class NftCollectionRef:
    chain: str
    address: str
    label: str

    @property
    def key(self) -> str:
        return nft_collection_key(self.chain, self.address)


def nft_collection_key(chain: str, address: str) -> str:
    return f"{chain}:{address.casefold()}"


def custom_nft_label(chain: str, address: str) -> str:
    prefix = "ETH" if chain == "ethereum" else "BASE"
    return f"{prefix} {address[:6]}…{address[-4:]}"


def parse_nft_collection(value: object) -> NftCollectionRef:
    if isinstance(value, NftCollectionRef):
        raw_chain, raw_address, raw_label = (
            value.chain,
            value.address,
            value.label,
        )
    elif isinstance(value, Mapping):
        raw_chain = value.get("chain")
        raw_address = value.get("address")
        raw_label = value.get("label")
    else:
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection"
        )
    if not isinstance(raw_chain, str) or raw_chain not in NFT_CHAINS:
        raise FilterValidationError(
            "nft_collections", "NFT chain must be Ethereum or Base"
        )
    if not isinstance(raw_address, str) or not _ADDRESS_RE.fullmatch(
        raw_address.strip()
    ):
        raise FilterValidationError(
            "nft_collections", "NFT contract must be a 20-byte 0x address"
        )
    address = raw_address.strip().casefold()
    label = (
        " ".join(raw_label.split())
        if isinstance(raw_label, str) and raw_label.strip()
        else custom_nft_label(raw_chain, address)
    )
    return NftCollectionRef(raw_chain, address, label)


PREDEFINED_NFT_COLLECTIONS = (
    NftCollectionRef(
        "ethereum",
        "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d",
        "Identity.md",
    ),
    NftCollectionRef(
        "base",
        "0x5b51cf49cb48617084ef35e7c7d7a21914769ff1",
        "Fren Pet",
    ),
    NftCollectionRef(
        "ethereum",
        "0x5af0d9827e0c53e4799bb226655a1de152a425a5",
        "Milady",
    ),
)


def _parse_nft_collections(value: object) -> tuple[NftCollectionRef, ...]:
    if value in (None, (), []):
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection list"
        )
    try:
        candidates = tuple(value)
    except TypeError as exc:
        raise FilterValidationError(
            "nft_collections", "invalid NFT collection list"
        ) from exc
    out: list[NftCollectionRef] = []
    seen: set[str] = set()
    for candidate in candidates:
        item = parse_nft_collection(candidate)
        if item.key not in seen:
            out.append(item)
            seen.add(item.key)
    return tuple(out)


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
    nft_collections: tuple[NftCollectionRef, ...] = ()

    @property
    def active(self) -> bool:
        ranged = any(getattr(self, field) is not None for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS))
        return (
            ranged
            or self.ens != "any"
            or self.window != "any"
            or self.band != "any"
            or bool(self.families)
            or self.whale
            or bool(self.nft_collections)
        )


@dataclass(frozen=True, slots=True)
class FilterContext:
    families_by_address: Mapping[str, frozenset[str]] | None = None
    whale_addresses: frozenset[str] | None = None
    nft_holders_by_collection: Mapping[str, frozenset[str]] | None = None


def empty_filter_values() -> dict[str, object]:
    values = {field: "" for field in (*_INTEGER_FIELDS, *_DECIMAL_FIELDS)}
    values.update(
        ens="any",
        window="any",
        band="any",
        families=frozenset(),
        whale=False,
        nft_collections=(),
    )
    return values


def _parse_number(field: str, value: object, *, integer: bool):
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
    parsed["nft_collections"] = _parse_nft_collections(
        values.get("nft_collections", ())
    )
    for low_field, high_field, _row_field in _RANGES:
        low, high = parsed[low_field], parsed[high_field]
        if low is not None and high is not None and low > high:
            raise FilterValidationError(low_field, f"{low_field} must not exceed {high_field}")
    return FilterSpec(**parsed)


def _row_number(
    row: Mapping[str, object], field: str, *, integer: bool
) -> int | float | None:
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


def filter_rows(rows: Any, spec: FilterSpec, context: FilterContext) -> list[dict]:
    if not spec.active:
        return []
    if spec.families and context.families_by_address is None:
        raise FilterDataUnavailable("linked analysis unavailable")
    if spec.whale and context.whale_addresses is None:
        raise FilterDataUnavailable("deposit history unavailable")
    if spec.nft_collections:
        holders = context.nft_holders_by_collection
        if holders is None or any(
            collection.key not in holders
            for collection in spec.nft_collections
        ):
            raise FilterDataUnavailable("NFT holder data unavailable")
    selected: list[dict] = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        rejected = False
        for low_field, high_field, row_field in _RANGES:
            low, high = getattr(spec, low_field), getattr(spec, high_field)
            if low is None and high is None:
                continue
            number = _row_number(
                row, row_field, integer=low_field in _INTEGER_FIELDS
            )
            if number is None or (low is not None and number < low) or (high is not None and number > high):
                rejected = True
                break
        if rejected:
            continue
        has_ens = isinstance(row.get("name"), str) and bool(row["name"].strip())
        if spec.ens == "set" and not has_ens or spec.ens == "unset" and has_ens:
            continue
        hour = _row_number(row, "first_hour", integer=True)
        window = None if hour is None else ("grace" if hour < 24 else "judged")
        if spec.window != "any" and window != spec.window:
            continue
        raw_band = row.get("link_conf")
        band = raw_band if isinstance(raw_band, str) and raw_band in {"clean", "low", "high", "review"} else "unknown"
        if spec.band != "any" and band != spec.band:
            continue
        address = row.get("address")
        key = address.casefold() if isinstance(address, str) else ""
        if spec.families and not (context.families_by_address.get(key, frozenset()) & spec.families):
            continue
        if spec.whale and key not in context.whale_addresses:
            continue
        if spec.nft_collections and not any(
            key in context.nft_holders_by_collection[collection.key]
            for collection in spec.nft_collections
        ):
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
    if spec.nft_collections:
        clauses.append(
            "NFT " + " or ".join(
                collection.label for collection in spec.nft_collections
            )
        )
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
