# Curator Filtered List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third, sortable and exportable filtered list to THE LIST dashboard, with keyboard presets, a custom filter editor, and list-aware hero cards.

**Architecture:** A pure filter module owns typed criteria, validation, matching, and summaries. `CuratorManager` supplies validated raw source rows plus cached linked-pattern and whale evidence; `CuratorScreen` owns editor/navigation state; list-only Textual widgets render the editor, tables, and current-list hero. No filter path performs network I/O.

**Tech Stack:** Python 3.11+, Textual >=0.80, Rich, pytest/pytest-asyncio, existing MaxPane curator cache and export helpers.

**Spec:** `docs/superpowers/specs/2026-08-20-curator-filtered-list-design.md`

## Global Constraints

- Work only on `feature/curator-list-record-hero`; never commit this work to `main`.
- Follow KISS and frontend MVC: model/manager computes, screen controls, widgets render.
- Do not modify shared hero cards or any non-curator view.
- Do not remove Linked Analysis code; only remove its reachable binding and status hint.
- Do not add network reads, polling tiers, cache slots, dependencies, or persistent filter settings.
- Keep tests keyless and offline.
- Preserve the 42-column full wallet address and 19-column ENS allocations.
- Do not reduce POINTS. Use the already-approved CREDIT reduction needed to keep all three full tables inside 143 columns.
- Never stage the pre-existing untracked `tests/fixtures/curator/captures/live/` files. Every commit stages explicit paths only.
- Use `apply_patch` for manual edits.
- Follow TDD in every task: red test, minimal implementation, green test, explicit-path commit.

## File Map

**Create**

- `maxpane_dashboard/data/curator_list_filters.py`: typed filter criteria, parsing, validation, presets, matching, and active-condition summaries.
- `maxpane_dashboard/widgets/curator/list_filter.py`: render-only custom filter editor.
- `tests/data/test_curator_list_filters.py`: pure filter-model contract.

**Modify**

- `maxpane_dashboard/data/curator_manager.py`: complete/fallback source selection and cached evidence projection.
- `maxpane_dashboard/widgets/curator/lists.py`: INDEX mechanics, LINK removal, filtered table, ordering message, and ordered export rows.
- `maxpane_dashboard/widgets/curator/list_hero.py`: current-list summary, current-list wallet facts, fixed filter-help card.
- `maxpane_dashboard/widgets/curator/__init__.py`: export the editor, filtered table, titles, and messages.
- `maxpane_dashboard/screens/curator.py`: keyboard behavior, editor state, filtering, hero dispatch, source receipts, and filtered export.
- `maxpane_dashboard/themes/minimal.tcss`: place the editor and third list table without changing other views.
- `tests/data/test_curator_manager.py`: manager adapter and evidence tests.
- `tests/widgets/test_curator_widgets.py`: editor, tables, sorting/index, hero, and width tests.
- `tests/screens/test_curator_screen.py`: full keyboard, state, source, export, and regression flows.

---

### Task 1: Pure Filter Model

**Files:**
- Create: `maxpane_dashboard/data/curator_list_filters.py`
- Create: `tests/data/test_curator_list_filters.py`

**Interfaces:**
- Produces: `FilterSpec`, `FilterContext`, `FilterValidationError`, `FilterDataUnavailable`.
- Produces: `empty_filter_values() -> dict[str, object]`.
- Produces: `parse_filter_values(values: Mapping[str, object]) -> FilterSpec`.
- Produces: `preset_filter(key: str) -> FilterSpec`.
- Produces: `filter_rows(rows: Any, spec: FilterSpec, context: FilterContext) -> list[dict]`.
- Produces: `filter_summary(spec: FilterSpec) -> tuple[str, ...]`.
- Depends on: no Textual, manager, cache, filesystem, clock, or network module.

- [ ] **Step 1: Write the failing filter contract tests**

Create `tests/data/test_curator_list_filters.py` with fixed row builders and direct assertions. Use this shape so every field is exercised without a manager fixture:

```python
from __future__ import annotations

import pytest

from maxpane_dashboard.data.curator_list_filters import (
    FilterContext,
    FilterDataUnavailable,
    FilterValidationError,
    empty_filter_values,
    filter_rows,
    filter_summary,
    parse_filter_values,
    preset_filter,
)


def _address(number: int) -> str:
    return f"0x{number:040x}"


def _row(
    rank: int,
    *,
    first_index: int | None = None,
    first_hour: int = 0,
    name: str | None = None,
    points: int | None = None,
    credit: float | None = None,
    weight: float | None = None,
    deposits: int | None = None,
    band: str | None = "clean",
) -> dict:
    return {
        "rank": rank,
        "address": _address(rank),
        "first_index": rank if first_index is None else first_index,
        "first_hour": first_hour,
        "name": name,
        "points": rank * 100 if points is None else points,
        "credit_eth": float(rank) if credit is None else credit,
        "weight_eth": float(rank * 2) if weight is None else weight,
        "tx_count": rank if deposits is None else deposits,
        "link_conf": band,
    }


ROWS = [
    _row(1, first_index=1, first_hour=0, name="one.eth", band="high"),
    _row(2, first_index=1_000, first_hour=23, band="low"),
    _row(3, first_index=1_001, first_hour=24, name="three.eth", band=None),
]


def _context() -> FilterContext:
    return FilterContext(
        families_by_address={
            _address(1): frozenset({"amount", "funding"}),
            _address(2): frozenset({"cadence"}),
        },
        whale_addresses=frozenset({_address(3)}),
    )


@pytest.mark.parametrize(
    ("key", "expected"),
    (("1", [1, 2]), ("2", [1]), ("3", [3])),
)
def test_presets_have_the_approved_exact_boundaries(key, expected):
    result = filter_rows(ROWS, preset_filter(key), _context())
    assert [row["rank"] for row in result] == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        ({"join_min": "1000", "join_max": "1000"}, [2]),
        ({"hour_min": "23", "hour_max": "24"}, [2, 3]),
        ({"rank_min": "2", "rank_max": "3"}, [2, 3]),
        ({"points_min": "200", "points_max": "200"}, [2]),
        ({"credit_min": "2", "credit_max": "2"}, [2]),
        ({"weight_min": "6", "weight_max": "6"}, [3]),
        ({"deposits_min": "3", "deposits_max": "3"}, [3]),
        ({"ens": "set"}, [1, 3]),
        ({"ens": "unset"}, [2]),
        ({"window": "grace"}, [1, 2]),
        ({"window": "judged"}, [3]),
        ({"band": "unknown"}, [3]),
        ({"families": frozenset({"cadence", "funding"})}, [1, 2]),
        ({"whale": True}, [3]),
    ),
)
def test_each_custom_field_is_inclusive(values, expected):
    raw = empty_filter_values()
    raw.update(values)
    result = filter_rows(ROWS, parse_filter_values(raw), _context())
    assert [row["rank"] for row in result] == expected


def test_categories_are_and_but_selected_families_are_or():
    values = empty_filter_values()
    values.update(
        hour_max="23",
        ens="any",
        families=frozenset({"cadence", "funding"}),
    )
    result = filter_rows(ROWS, parse_filter_values(values), _context())
    assert [row["rank"] for row in result] == [1, 2]


def test_no_active_filter_is_an_honest_empty_result():
    spec = parse_filter_values(empty_filter_values())
    assert filter_rows(ROWS, spec, _context()) == []


@pytest.mark.parametrize(
    ("values", "field"),
    (
        ({"hour_min": "-1"}, "hour_min"),
        ({"points_min": "1.5"}, "points_min"),
        ({"credit_min": "nan"}, "credit_min"),
        ({"join_min": "10", "join_max": "9"}, "join_min"),
        ({"ens": "sometimes"}, "ens"),
        ({"families": frozenset({"banana"})}, "families"),
    ),
)
def test_invalid_values_name_the_field(values, field):
    raw = empty_filter_values()
    raw.update(values)
    with pytest.raises(FilterValidationError) as caught:
        parse_filter_values(raw)
    assert caught.value.field == field


def test_missing_evidence_is_reported_only_when_that_filter_needs_it():
    family_values = empty_filter_values()
    family_values["families"] = frozenset({"amount"})
    with pytest.raises(FilterDataUnavailable, match="linked analysis unavailable"):
        filter_rows(ROWS, parse_filter_values(family_values), FilterContext())

    whale_values = empty_filter_values()
    whale_values["whale"] = True
    with pytest.raises(FilterDataUnavailable, match="deposit history unavailable"):
        filter_rows(ROWS, parse_filter_values(whale_values), FilterContext())


def test_summaries_are_stable_and_contain_only_active_values():
    values = empty_filter_values()
    values.update(
        hour_min="0",
        hour_max="0",
        credit_min="25",
        ens="set",
        window="grace",
        families=frozenset({"amount", "funding"}),
    )
    assert filter_summary(parse_filter_values(values)) == (
        "joined hour 0",
        "credit >=25 ETH",
        "ENS set",
        "window grace",
        "amount or funding",
    )
```

- [ ] **Step 2: Run the new tests and verify the import failure**

Run:

```bash
.venv/bin/pytest tests/data/test_curator_list_filters.py -q
```

Expected: collection fails with `ModuleNotFoundError: maxpane_dashboard.data.curator_list_filters`.

- [ ] **Step 3: Implement the typed filter module**

Create `maxpane_dashboard/data/curator_list_filters.py`. Keep all rules in this file and expose only the interfaces listed above. The implementation must use these exact field names and enum vocabularies:

```python
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
    parsed = {
        field: _parse_number(field, values.get(field), integer=True)
        for field in _INTEGER_FIELDS
    }
    parsed.update({
        field: _parse_number(field, values.get(field), integer=False)
        for field in _DECIMAL_FIELDS
    })
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
```

The parser uses `int()` for integer fields and `float()` plus
`math.isfinite()` for decimal fields. It rejects booleans, negative numbers,
bad enum values, unknown families, and reversed ranges with a field-specific
`FilterValidationError`.

Implement presets exactly:

```python
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
```

The matching order is inactive-spec, context availability, numeric ranges, ENS,
window, band, evidence families, then whale membership. The summary order is
join, score, contribution, identity, window, then linked patterns, as encoded
above.

- [ ] **Step 4: Run pure tests green**

Run:

```bash
.venv/bin/pytest tests/data/test_curator_list_filters.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1 explicitly**

```bash
git add maxpane_dashboard/data/curator_list_filters.py tests/data/test_curator_list_filters.py
git commit -m "feat(curator): add pure list filters"
```

---

### Task 2: Manager-Backed Source And Evidence

**Files:**
- Modify: `maxpane_dashboard/data/curator_manager.py`
- Modify: `tests/data/test_curator_manager.py`

**Interfaces:**
- Consumes: Task 1 `FilterSpec`, `FilterContext`, and `filter_rows()`.
- Consumes: existing `load_export_list()`, `CuratorCache.analysis_last_good()`, `events()`, `fold_rows()`, and `first_deposits()`.
- Produces: frozen `FilteredListResult(rows, complete, source_reason)`.
- Produces: `CuratorManager.filtered_list_rows(directory, *, expected_count, live_rows, you_row, spec) -> FilteredListResult`.

- [ ] **Step 1: Write failing manager adapter tests**

Append tests that construct cache state directly, never call `fetch_and_compute()`, and assert the client call list remains empty:

```python
def _deposit(address: str, amount_wei: int, index: int) -> DepositEvent:
    return DepositEvent(
        contributor=address,
        hour=0,
        amount_wei=amount_wei,
        credited_delta_wei=amount_wei,
        weight_added_wei=amount_wei,
        new_weight_wei=amount_wei,
        tx_count=1,
        hour_total_wei=amount_wei,
        early_bps=10_000,
        block_number=index,
        tx_hash=f"0x{index:064x}",
        log_index=0,
        ts=NOW,
    )


def test_filtered_rows_use_a_valid_complete_export_and_cached_evidence(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    slot, fold = _legacy_clean_slot(count=3)
    addresses = [row.address for row in fold]
    slot["groups"] = [{
        "size": 2,
        "conf": "high",
        "families": ["amount", "funding"],
        "reasons": ["matching send amounts", "shared funder chain"],
        "members": addresses[:2],
    }]
    manager.cache.store_fold(fold, last_block=None, now=NOW)
    manager.cache.store_first_deposits([
        {"contributor": address, "index": index, "ts": NOW}
        for index, address in enumerate(addresses, start=1)
    ])
    manager.cache.store_events([
        _deposit(addresses[0], 1 * 10**18, 1),
        _deposit(addresses[1], 25 * 10**18, 2),
        _deposit(addresses[2], 25 * 10**18 - 1, 3),
    ])
    manager.cache.store_last_good(SLOT_LOGS, {}, ts=NOW)
    manager.cache.store_analysis(slot, ts=NOW)

    exported = manager.full_list_rows(cleaned=False)
    (tmp_path / "curator_raw_list.json").write_text(json.dumps(exported))
    spec = parse_filter_values({
        **empty_filter_values(),
        "families": frozenset({"funding"}),
        "whale": True,
    })
    result = manager.filtered_list_rows(
        tmp_path,
        expected_count=3,
        live_rows=exported[:1],
        you_row=None,
        spec=spec,
    )

    assert result.complete is True
    assert result.source_reason is None
    assert [row["address"] for row in result.rows] == [addresses[1]]
    assert manager.client.calls == []


def test_filtered_rows_fall_back_to_the_live_slice_when_export_is_short(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    live = [{
        "rank": 1, "address": "0x" + "01" * 20, "points": 1,
        "credit_eth": 1.0, "tx_count": 1, "flagged": False, "name": None,
        "weight_eth": 1.0, "first_hour": 0, "first_index": 1,
        "link_conf": "clean",
    }]
    (tmp_path / "curator_raw_list.json").write_text(json.dumps(live))
    result = manager.filtered_list_rows(
        tmp_path,
        expected_count=2,
        live_rows=live,
        you_row=None,
        spec=preset_filter("2"),
    )
    assert result.rows == live
    assert result.complete is False
    assert result.source_reason == "count_mismatch"


def test_family_and_whale_filters_refuse_missing_evidence(tmp_path, clock):
    manager = _manager(tmp_path, clock)
    row = {"rank": 1, "address": "0x" + "01" * 20, "first_index": 1, "first_hour": 0}
    values = empty_filter_values()
    values["families"] = frozenset({"amount"})
    with pytest.raises(FilterDataUnavailable, match="linked analysis unavailable"):
        manager.filtered_list_rows(tmp_path, expected_count=1, live_rows=[row], you_row=None, spec=parse_filter_values(values))

    with pytest.raises(FilterDataUnavailable, match="deposit history unavailable"):
        manager.filtered_list_rows(tmp_path, expected_count=1, live_rows=[row], you_row=None, spec=preset_filter("3"))
```

Add the required imports from `curator_list_filters`, `pathlib.Path`, and `json` if not already present.

- [ ] **Step 2: Run the focused manager tests red**

Run:

```bash
.venv/bin/pytest tests/data/test_curator_manager.py -k "filtered_rows or family_and_whale" -q
```

Expected: failures because `FilteredListResult` and `CuratorManager.filtered_list_rows` do not exist.

- [ ] **Step 3: Implement the manager adapter**

Import `Path` from `pathlib` and `dataclass` from `dataclasses`, then add this
frozen result contract near the manager's other local contracts:

```python
@dataclass(frozen=True, slots=True)
class FilteredListResult:
    rows: list[dict] | None
    complete: bool
    source_reason: str | None
```

Import `WHALE_MIN_ETH`, `load_export_list`, and Task 1's types/functions. Add private helpers with these rules:

```python
def _filter_families(self) -> dict[str, frozenset[str]] | None:
    entry = self.cache.analysis_last_good()
    payload = entry.payload if entry is not None else None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("groups"), list):
        return None
    found: dict[str, set[str]] = {}
    for group in payload["groups"]:
        if not isinstance(group, Mapping):
            continue
        families = {
            value for value in group.get("families", ())
            if isinstance(value, str) and value in FILTER_FAMILIES
        }
        for member in group.get("members", ()):
            if isinstance(member, str) and member.strip():
                found.setdefault(member.casefold(), set()).update(families)
    return {address: frozenset(values) for address, values in found.items()}


def _filter_whales(self, expected_count: Any) -> frozenset[str] | None:
    fold = self.cache.fold_rows()
    trusted_count = isinstance(expected_count, int) and not isinstance(expected_count, bool)
    if not trusted_count or len(fold) != expected_count or not self._history_complete(fold):
        return None
    floor_wei = int(WHALE_MIN_ETH * 10**18)
    return frozenset(
        event.contributor.casefold()
        for event in self.cache.events()
        if event.amount_wei >= floor_wei
    )
```

`filtered_list_rows()` must call `load_export_list()` with the exact arguments
shown below, preserve `None` if the selected raw source is unavailable, build
only the context required by the active spec, and call pure `filter_rows()`:

```python
def filtered_list_rows(self, directory, *, expected_count, live_rows, you_row, spec):
    source = load_export_list(
        Path(directory),
        cleaned=False,
        expected_count=expected_count,
        live_rows=live_rows,
        you_row=you_row,
    )
    if not isinstance(source.rows, list):
        return FilteredListResult(None, source.complete, source.reason)
    context = FilterContext(
        families_by_address=self._filter_families() if spec.families else None,
        whale_addresses=self._filter_whales(expected_count) if spec.whale else None,
    )
    return FilteredListResult(
        filter_rows(source.rows, spec, context),
        source.complete,
        source.reason,
    )
```

This method is synchronous and must never call the client.

- [ ] **Step 4: Run manager and source-loader tests green**

Run:

```bash
.venv/bin/pytest tests/data/test_curator_manager.py -k "filtered_rows or family_and_whale or full_list" -q
.venv/bin/pytest tests/data/test_curator_list_source.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2 explicitly**

```bash
git add maxpane_dashboard/data/curator_manager.py tests/data/test_curator_manager.py
git commit -m "feat(curator): filter complete list sources"
```

---

### Task 3: Indexed Raw, Cleaned, And Filtered Tables

**Files:**
- Modify: `maxpane_dashboard/widgets/curator/lists.py`
- Modify: `maxpane_dashboard/widgets/curator/__init__.py`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- Produces: `CuratorFilteredList` with `update_data(filtered_rows, you_list_row, filtered_complete)`.
- Produces: `ListOrderChanged(kind: str, addresses: tuple[str, ...])` Textual message.
- Produces: `CuratorFilteredList.export_rows() -> list[dict]` in visible order with one-based `index`.
- Keeps: raw/clean source selection, fixed YOU row, blank line, typed sorting, receipts, and 1,000-row fallback cap.

- [ ] **Step 1: Write failing table/index tests**

Update existing list assertions and add a three-kind parametrized test. The key assertions are:

```python
@pytest.mark.parametrize("kind", ("raw", "clean", "filtered"))
async def test_every_list_has_dynamic_index_and_no_link(kind):
    from textual.widgets import DataTable
    from maxpane_dashboard.widgets.curator import CuratorCleanedList, CuratorFilteredList, CuratorRawList

    rows = [
        {
            "rank": rank, "clean_rank": rank, "first_index": rank,
            "address": f"0x{rank:040x}", "name": None,
            "points": points, "weight_eth": float(points),
            "credit_eth": float(points), "tx_count": rank,
            "first_hour": rank, "link_conf": "clean",
        }
        for rank, points in ((1, 9), (2, 10_000), (3, 100))
    ]
    widget = {"raw": CuratorRawList(), "clean": CuratorCleanedList(), "filtered": CuratorFilteredList()}[kind]
    kwargs = {
        "raw": {"leaderboard_rows": rows},
        "clean": {"clean_list_rows": rows},
        "filtered": {"filtered_rows": rows, "filtered_complete": True},
    }[kind]
    app = _Harness(widget)
    async with app.run_test(size=(143, 18)) as pilot:
        widget.update_data(**kwargs)
        await pilot.pause()
        table = widget.query_one(".curator-list-table", DataTable)
        keys = [column[0] for column in widget._columns]
        assert keys[0] == "index"
        assert "link" not in keys
        assert [table.get_row_at(i)[0] for i in range(3)] == ["1", "2", "3"]

        points_index = keys.index("points")
        x = table._get_column_region(points_index).x + 1
        assert await pilot.click(table, offset=(x, 0))
        await pilot.pause()
        assert [table.get_row_at(i)[0] for i in range(3)] == ["1", "2", "3"]
        assert [table.get_row_at(i)[keys.index("rank")] for i in range(3)] == ["1", "3", "2"]


async def test_filtered_export_rows_follow_the_current_sort_and_indexes():
    widget = CuratorFilteredList()
    rows = [
        {
            "rank": rank, "first_index": rank,
            "address": f"0x{rank:040x}", "name": None,
            "points": points, "weight_eth": float(points),
            "credit_eth": float(points), "tx_count": rank,
            "first_hour": rank, "link_conf": "clean",
        }
        for rank, points in ((1, 9), (2, 10_000), (3, 100))
    ]
    app = _Harness(widget)
    async with app.run_test(size=(143, 18)) as pilot:
        widget.update_data(filtered_rows=rows, filtered_complete=True)
        await pilot.pause()
        table = widget.query_one(".curator-list-table", DataTable)
        points_index = [column[0] for column in widget._columns].index("points")
        x = table._get_column_region(points_index).x + 1
        assert await pilot.click(table, offset=(x, 0))
        assert await pilot.click(table, offset=(x, 0))
        await pilot.pause()
    exported = widget.export_rows()
    assert [row["rank"] for row in exported] == [2, 3, 1]
    assert [row["index"] for row in exported] == [1, 2, 3]
```

Also update the requested-width test to assert ADDRESS 42, ENS 19, POINTS 7, WEIGHT 8, CREDIT 6 at their new indexes. Replace raw `LINK` header/glyph expectations with `INDEX` and `RANK` expectations. Add a footer test proving a filtered non-match has `--` in INDEX while a match gets its current visible index.

- [ ] **Step 2: Run the focused widget tests red**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "list and (index or link or sort or width or footer or export_rows)" -q
```

Expected: failures because INDEX, `CuratorFilteredList`, and `export_rows()` do not exist and raw still renders LINK.

- [ ] **Step 3: Implement shared indexed-table mechanics**

In `lists.py`:

1. Add `_INDEX_COLS = 6`, keep `_ADDRESS_COLS = 42`, `_ENS_COLS = 19`, `_POINTS_COLS = 7`, set `_CREDIT_COLS = 6`.
2. Remove every LINK column/tier/sort branch and `_link_glyph` import.
3. Start each full/tier column tuple with `("index", "INDEX", 6)` followed by `("rank", "RANK", 6)`.
4. Ensure every minimum tier still contains INDEX, RANK, ADDRESS, ENS, and POINTS.
5. Add `FILTERED_LIST_TITLE = "THE FILTERED LIST"`, `FILTERED_LIST_UNAVAILABLE = "filtered list unavailable"`, and `FILTERED_LIST_EMPTY = "no wallets match"`.
6. Add `index` to `_NUMERIC_SORT_COLUMNS`; it uses `_source_order` rather than a row dictionary field.

Add a module-level message:

```python
class ListOrderChanged(Message):
    def __init__(self, kind: str, addresses: tuple[str, ...]) -> None:
        super().__init__()
        self.kind = kind
        self.addresses = addresses
```

Give `_ListTable` a `KIND`, `_source_order`, `_ordered_addresses`, and `_visible_indexes`. During row insertion, render the initial index. After initial rendering and after `_apply_sort()`, call one helper that:

```python
def _renumber_and_publish(self, table: DataTable) -> None:
    index_column = next(i for i, column in enumerate(self._columns) if column[0] == "index")
    addresses: list[str] = []
    visible: dict[str, int] = {}
    for row_index in range(table.row_count):
        values = table.get_row_at(row_index)
        table.update_cell_at(Coordinate(row_index, index_column), _rank(row_index + 1))
        source = self._source_row(values)
        address = self._address_key(source.get("address")) if isinstance(source, dict) else None
        if address is not None:
            addresses.append(address)
            visible[address] = row_index + 1
    self._ordered_addresses = tuple(addresses)
    self._visible_indexes = visible
    self._render_you(self._columns, clear=True)
    self.post_message(ListOrderChanged(self.KIND, self._ordered_addresses))
```

Import `Coordinate` from `textual.coordinate` and `Message` from
`textual.message`. INDEX sorting uses each row's original insertion position
from `_source_order`; ascending restores source order and descending reverses
it. INDEX itself still renders `1..N` after either sort.

Move footer rendering until after the visible-index map is ready. `_render_you()` adds `values["index"]` only if the configured wallet is present in `_visible_indexes`, otherwise DASH.

Add:

```python
class CuratorFilteredList(_ListTable):
    TITLE = FILTERED_LIST_TITLE
    TABLE_ID = "curator-filtered-list-table"
    TIERS = _RAW_TIERS
    UNAVAILABLE = FILTERED_LIST_UNAVAILABLE
    EMPTY = FILTERED_LIST_EMPTY
    KIND = "filtered"

    def update_data(self, filtered_rows=None, you_list_row=None, filtered_complete=False) -> None:
        self._payload = {
            "rows": filtered_rows,
            "you_list_row": you_list_row,
            "wallet_count": len(filtered_rows) if isinstance(filtered_rows, list) else None,
            "complete": bool(filtered_complete),
            "seen": True,
        }
        self._render_view()

    def _rows(self):
        return self._payload["rows"]

    def _row_values(self, row: dict) -> dict:
        return _raw_values(row)

    def export_rows(self) -> list[dict]:
        rows = []
        for index, address in enumerate(self._ordered_addresses, start=1):
            source = self._rows_by_address[address]
            rows.append({**source, "index": index})
        return rows
```

Set `KIND = "raw"` and `KIND = "cleaned"` on the existing subclasses. Export the new class, title, empty/unavailable strings, and message from `widgets/curator/__init__.py`.

- [ ] **Step 4: Run list widget tests green**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "list" -q
```

Expected: all list-focused widget tests pass.

- [ ] **Step 5: Commit Task 3 explicitly**

```bash
git add maxpane_dashboard/widgets/curator/lists.py maxpane_dashboard/widgets/curator/__init__.py tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): add indexed filtered table"
```

---

### Task 4: Custom Filter Editor Widget

**Files:**
- Create: `maxpane_dashboard/widgets/curator/list_filter.py`
- Modify: `maxpane_dashboard/widgets/curator/__init__.py`
- Modify: `maxpane_dashboard/themes/minimal.tcss`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- Produces: `CuratorListFilterEditor.values() -> dict[str, object]`.
- Produces: `CuratorListFilterEditor.set_values(values: Mapping[str, object]) -> None`.
- Produces: `show_error(field: str | None, message: str) -> None` and `clear_error() -> None`.
- Depends only on primitive dictionaries; the widget package must continue importing nothing from `data/` or `analytics/`.

- [ ] **Step 1: Write failing editor rendering/round-trip tests**

Add tests that mount the editor directly:

```python
async def test_filter_editor_renders_every_approved_category_and_control():
    from maxpane_dashboard.widgets.curator import CuratorListFilterEditor
    editor = CuratorListFilterEditor()
    app = _Harness(editor)
    async with app.run_test(size=(143, 30)) as pilot:
        await pilot.pause()
        text = _screen_text(app)
        for label in ("JOIN", "SCORE", "CONTRIBUTION", "IDENTITY", "WINDOW", "LINKED PATTERNS"):
            assert label in text
        for label in ("matching amounts", "consecutive joins", "cadence", "gas fingerprint", "shared funding"):
            assert label in text
        for control_id in (
            "filter-join-min", "filter-join-max", "filter-hour-min", "filter-hour-max",
            "filter-rank-min", "filter-rank-max", "filter-points-min", "filter-points-max",
            "filter-credit-min", "filter-credit-max", "filter-weight-min", "filter-weight-max",
            "filter-deposits-min", "filter-deposits-max", "filter-ens", "filter-window",
            "filter-band", "filter-whale", "filter-family-amount", "filter-family-sequence",
            "filter-family-cadence", "filter-family-gas", "filter-family-funding",
        ):
            assert editor.query_one(f"#{control_id}") is not None


async def test_filter_editor_round_trips_values_and_names_an_error():
    editor = CuratorListFilterEditor()
    app = _Harness(editor)
    async with app.run_test(size=(143, 30)) as pilot:
        editor.set_values({
            "hour_min": "0", "hour_max": "0", "ens": "set", "window": "grace",
            "band": "high", "whale": True, "families": frozenset({"amount", "funding"}),
        })
        editor.show_error("hour_min", "joined hour must be non-negative")
        await pilot.pause()
        values = editor.values()
        assert values["hour_min"] == "0" and values["hour_max"] == "0"
        assert values["ens"] == "set" and values["window"] == "grace"
        assert values["band"] == "high" and values["whale"] is True
        assert values["families"] == frozenset({"amount", "funding"})
        assert "joined hour must be non-negative" in _screen_text(app)
        assert editor.query_one("#filter-hour-min").has_class("filter-invalid")
```

- [ ] **Step 2: Run the editor tests red**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "filter_editor" -q
```

Expected: import failure for `CuratorListFilterEditor`.

- [ ] **Step 3: Implement the render-only editor**

Create `list_filter.py` with declarative constants rather than hand-copying control logic:

```python
RANGE_FIELDS = (
    ("JOIN", (("join_min", "join from"), ("join_max", "join to"), ("hour_min", "hour from"), ("hour_max", "hour to"))),
    ("SCORE", (("rank_min", "rank from"), ("rank_max", "rank to"), ("points_min", "points from"), ("points_max", "points to"))),
    ("CONTRIBUTION", (("credit_min", "credit from"), ("credit_max", "credit to"), ("weight_min", "weight from"), ("weight_max", "weight to"), ("deposits_min", "deposits from"), ("deposits_max", "deposits to"))),
)
FAMILIES = ("amount", "sequence", "cadence", "gas", "funding")
FAMILY_LABELS = {
    "amount": "matching amounts",
    "sequence": "consecutive joins",
    "cadence": "cadence",
    "gas": "gas fingerprint",
    "funding": "shared funding",
}
```

Compose unframed category bands with `Label`, numeric
`Input(type="number", valid_empty=True)`, `Checkbox` for whale/families, and
these exact selects:

```python
Select((("Any", "any"), ("Set", "set"), ("Unset", "unset")), allow_blank=False, value="any", id="filter-ens")
Select((("Any", "any"), ("Grace", "grace"), ("Judged", "judged")), allow_blank=False, value="any", id="filter-window")
Select((("Any", "any"), ("Clean", "clean"), ("Low", "low"), ("High", "high"), ("Unknown", "unknown")), allow_blank=False, value="any", id="filter-band")
```

IDs must exactly match the tests. The first focusable control is join minimum.

`values()` returns every Task 1 field, including blank strings for untouched ranges and a `frozenset` for families. `set_values()` must reset unspecified controls to their defaults before applying the provided values. `show_error()` clears the old class, adds `filter-invalid` to the named control when it exists, updates a one-line `#curator-filter-error` Static, and focuses the invalid control. `clear_error()` removes the class and clears the line.

Add component `DEFAULT_CSS` and matching rules in `minimal.tcss`:

```css
CuratorScreen CuratorListFilterEditor {
    width: 100%;
    height: 100%;
    padding: 0 2;
    overflow-y: auto;
}
CuratorScreen .curator-filter-category {
    height: auto;
    margin-bottom: 1;
}
CuratorScreen .curator-filter-fields {
    height: auto;
    layout: grid;
    grid-size: 4;
    grid-columns: 1fr 1fr 1fr 1fr;
    grid-gutter: 0 1;
}
CuratorScreen .curator-filter-field {
    width: 100%;
    min-width: 14;
}
CuratorScreen CuratorListFilterEditor.compact-filter .curator-filter-fields {
    grid-size: 2;
    grid-columns: 1fr 1fr;
}
CuratorScreen .filter-invalid {
    border: tall $error;
}
CuratorScreen #curator-filter-error {
    height: 1;
    color: $error;
}
```

Compose each field group with Textual `Grid`. In `on_resize`, toggle the
`compact-filter` class when `self.content_size.width < 100`; the CSS above then
switches from four tracks to two. Do not introduce nested cards or rounded
containers.

Export the editor from `widgets/curator/__init__.py`.

- [ ] **Step 4: Run editor and import-boundary tests green**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "filter_editor or primitive or imports" -q
```

Expected: editor tests and the widget package's no-data-import guard pass.

- [ ] **Step 5: Commit Task 4 explicitly**

```bash
git add maxpane_dashboard/widgets/curator/list_filter.py maxpane_dashboard/widgets/curator/__init__.py maxpane_dashboard/themes/minimal.tcss tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): add list filter editor"
```

---

### Task 5: Current-List Hero Cards

**Files:**
- Modify: `maxpane_dashboard/widgets/curator/list_hero.py`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- Consumes primitives only: `list_view`, raw/clean/filtered aggregates, wallet ranks/index, join facts, identity, points, and `filter_summary` clauses.
- Produces three list-only cards: visible-list summary, current-list wallet, fixed filter help.

- [ ] **Step 1: Write failing hero-state tests**

Replace fixed raw/clean card assumptions with a mode-parametrized contract:

```python
@pytest.mark.parametrize(
    ("view", "expected", "absent"),
    (
        ("raw", ("THE LIST", "19,522 wallets", "28,353 tx", "128.1K ETH", "join #88", "hour 12"), ("THE CLEANED LIST", "THE FILTERED LIST")),
        ("cleaned", ("THE CLEANED LIST", "8,750 wallets", "12,345,678 pts", "#7,042 of 8,750 (clean)", "join #88", "hour 12"), ("128.1K ETH", "THE FILTERED LIST")),
        ("filtered", ("THE FILTERED LIST", "568 wallets", "1,234,567 pts", "#14 of 568 (filtered)", "single deposit >=25 ETH"), ("#15,234 of 19,522 (raw)", "after linked removal")),
    ),
)
async def test_list_hero_follows_the_visible_list(view, expected, absent):
    text = await _rendered(
        CuratorListHero,
        size=(143, 12),
        list_view=view,
        phase="settled",
        contributors_total=19_522,
        deposits_total=28_353,
        volume_routed_eth=128_130.76,
        clean_contributors=8_750,
        clean_points=12_345_678,
        filtered_contributors=568,
        filtered_points=1_234_567,
        you_address="0x1234567890abcdef1234567890abcdef12345678",
        you_ens="reader.eth",
        you_rank=15_234,
        you_clean_rank=7_042,
        you_filtered_index=14,
        you_first_index=88,
        you_first_hour=12,
        you_points=42_721,
        filter_summary=("single deposit >=25 ETH",),
    )
    for value in expected:
        assert value in text
    for value in absent:
        assert value not in text


async def test_third_list_hero_card_is_exact_white_regular_filter_help():
    widget = CuratorListHero()
    app = _Harness(widget)
    async with app.run_test(size=(143, 12)) as pilot:
        widget.update_data(list_view="raw")
        await pilot.pause()
        box = widget.query_one("#curator-list-hero-filter")
        plain = box.render().plain
        assert plain.splitlines() == [
            "THE FILTER",
            "'1' - first 1000 wallets",
            "'2' - joined hour 0",
            "'3' - whale splash",
            "'f' - for more filters",
        ]
        assert "bold" not in str(box.render().style)
```

Keep the hostile ENS/full-address tests and add a filtered non-match assertion for `-- of 568 (filtered)`.

- [ ] **Step 2: Run list-hero tests red**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "list_hero" -q
```

Expected: failures because the hero still renders fixed raw/wallet/cleaned cards.

- [ ] **Step 3: Implement mode-aware list-only builders**

Change the box IDs to summary, wallet, and filter. Keep `_lines()` for ordinary dim-title cards, but return literal unstyled lines for the filter card.

Add these exact dispatch rules:

```python
def _summary_lines(data: dict, tier: str) -> list[str]:
    view = data.get("list_view")
    if view == "cleaned":
        return _cleaned_summary_lines(data, tier)
    if view == "filtered":
        return _filtered_summary_lines(data, tier)
    return _raw_summary_lines(data, tier)


def _wallet_lines(data: dict, tier: str) -> list[str]:
    view = data.get("list_view")
    if view == "filtered":
        standing = f"{_rank(data.get('you_filtered_index'))} of {_total(data.get('filtered_contributors'))} (filtered)"
        detail = _compact_filter_summary(data.get("filter_summary"), tier)
    elif view == "cleaned":
        standing = f"{_rank(data.get('you_clean_rank'))} of {_total(data.get('clean_contributors'))} (clean)"
        detail = _join_detail(data)
    else:
        standing = f"{_rank(data.get('you_rank'))} of {_total(data.get('contributors_total'))} (raw)"
        detail = _join_detail(data)
    return _lines("THE WALLET", f"[bold]{standing}[/]", detail, _wallet_identity(data, tier), f"[bold]{fmt_points(data.get('you_points'))} pts[/]")
```

`_join_detail()` renders both `join #N` and `hour N` when available. `_compact_filter_summary()` accepts only a tuple/list of non-empty strings, keeps clauses in supplied order, and appends `+N` when the rendered tier cannot carry all clauses. It must return DASH when no filter is active.

Filtered summary aggregates use `filtered_contributors` and `filtered_points`; sorting never changes them. The third builder returns the five exact lines with no Rich style tags.

Add a list-local CSS rule for `#curator-list-hero-filter` with
`color: $text` and `text-style: none`; do not alter `CuratorHero` or any shared
hero selector.

Use this explicit update signature so the screen signature-agreement test can
pin every screen-supplied primitive:

```python
def update_data(
    self,
    phase=None,
    list_view="raw",
    contributors_total=None,
    deposits_total=None,
    volume_routed_eth=None,
    you_address=None,
    you_ens=None,
    you_rank=None,
    you_clean_rank=None,
    you_filtered_index=None,
    you_first_index=None,
    you_first_hour=None,
    you_points=None,
    clean_contributors=None,
    clean_points=None,
    filtered_contributors=None,
    filtered_points=None,
    filter_summary=None,
    **_kwargs,
) -> None:
    self._payload = {
        "phase": phase,
        "list_view": list_view,
        "contributors_total": contributors_total,
        "deposits_total": deposits_total,
        "volume_routed_eth": volume_routed_eth,
        "you_address": you_address,
        "you_ens": you_ens,
        "you_rank": you_rank,
        "you_clean_rank": you_clean_rank,
        "you_filtered_index": you_filtered_index,
        "you_first_index": you_first_index,
        "you_first_hour": you_first_hour,
        "you_points": you_points,
        "clean_contributors": clean_contributors,
        "clean_points": clean_points,
        "filtered_contributors": filtered_contributors,
        "filtered_points": filtered_points,
        "filter_summary": filter_summary,
    }
    self._render_view()
```

- [ ] **Step 4: Run hero tests green**

Run:

```bash
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "list_hero" -q
```

Expected: all list-hero tests pass.

- [ ] **Step 5: Commit Task 5 explicitly**

```bash
git add maxpane_dashboard/widgets/curator/list_hero.py tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): make list hero follow view"
```

---

### Task 6: Screen Navigation, Presets, And Custom Apply Flow

**Files:**
- Modify: `maxpane_dashboard/screens/curator.py`
- Modify: `maxpane_dashboard/themes/minimal.tcss`
- Modify: `tests/screens/test_curator_screen.py`

**Interfaces:**
- Consumes: manager `filtered_list_rows()`, Task 1 parsing/presets/summaries, Task 3 filtered table/order message, Task 4 editor, Task 5 hero inputs.
- Produces: Raw -> Cleaned -> Filtered `c` cycle.
- Produces: list-only `1`, `2`, `3`, and `f` actions.
- Keeps: legacy `action_toggle_analysis()` callable but unbound.

- [ ] **Step 1: Extend the screen fake and write failing key-flow tests**

Update `_FakeManager` with a synchronous `filtered_list_rows()` using Task 1's
pure matcher and configurable cached evidence:

```python
class _FakeManager:
    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        # Keep the existing initialization, then add:
        self.families_by_address: dict[str, frozenset[str]] | None = {}
        self.whale_addresses: frozenset[str] | None = frozenset()

    def filtered_list_rows(
        self, directory, *, expected_count, live_rows, you_row, spec
    ) -> FilteredListResult:
        if not isinstance(live_rows, list):
            return FilteredListResult(None, False, "missing")
        context = FilterContext(
            families_by_address=self.families_by_address if spec.families else None,
            whale_addresses=self.whale_addresses if spec.whale else None,
        )
        return FilteredListResult(
            filter_rows(live_rows, spec, context),
            False,
            "missing",
        )
```

Import `FilteredListResult` from `curator_manager` and `FilterContext` plus
`filter_rows` from Task 1. Then add these flows:

```python
async def test_c_cycles_raw_cleaned_filtered_and_remembers_filtered():
    screen = _screen(_list_payload(3))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l")
        assert screen._list_view == "raw"
        await pilot.press("c")
        assert screen._list_view == "cleaned"
        await pilot.press("c")
        assert screen._list_view == "filtered"
        await pilot.press("c")
        assert screen._list_view == "raw"


@pytest.mark.parametrize(("key", "ranks", "summary"), (("1", [1, 2, 3], "join #1-1,000"), ("2", [], "joined hour 0"), ("3", [3], "single deposit >=25 ETH")))
async def test_list_presets_switch_to_filtered_and_apply_immediately(key, ranks, summary):
    payload = _list_payload(3)
    payload["leaderboard_rows"][2]["first_hour"] = 24
    screen = _screen(payload)
    screen._data_manager.whale_addresses = frozenset({payload["leaderboard_rows"][2]["address"].casefold()})
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", key)
        await pilot.pause()
        assert screen._list_view == "filtered"
        assert [row["rank"] for row in screen.query_one(CuratorFilteredList).export_rows()] == ranks
        assert summary in _region_text(app, screen.query_one(CuratorListHero), screen)


async def test_f_opens_blank_editor_then_applies_and_retains_custom_values():
    screen = _screen(_list_payload(3))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f")
        editor = screen.query_one(CuratorListFilterEditor)
        assert screen._list_view == "filtered" and editor.display is True
        assert editor.values()["hour_min"] == ""
        editor.query_one("#filter-hour-min", Input).value = "0"
        editor.query_one("#filter-hour-max", Input).value = "0"
        await pilot.press("f")
        assert editor.display is False
        await pilot.press("f")
        assert editor.values()["hour_min"] == "0"


async def test_filter_shortcuts_are_list_only_and_editor_blocks_cycle_and_presets():
    screen = _screen(_list_payload(3))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("1", "2", "3", "f")
        assert screen._mode == MODE_DASHBOARD
        await pilot.press("l", "f")
        editor = screen.query_one(CuratorListFilterEditor)
        await pilot.press("1", "2", "3", "c")
        assert editor.display is True and screen._list_view == "filtered"
```

Add assertions that the filtered table is composed from startup but hidden, cycling to an inactive filter shows zero rows, `f linked` is absent from `KEY_HINTS`, and dashboard `c` remains unchanged. Existing analysis tests that used `pilot.press("f")` must call `screen.action_toggle_analysis()` directly; this proves the hidden implementation remains functional without preserving its binding.

- [ ] **Step 2: Run screen flow tests red**

Run:

```bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "cycle or preset or filter_shortcuts or blank_editor or linked" -q
```

Expected: failures because only two list views exist and `f` still opens analysis.

- [ ] **Step 3: Implement screen-owned filter state and actions**

Add constants:

```python
LIST_FILTERED = "filtered"
LIST_VIEWS = (LIST_RAW, LIST_CLEANED, LIST_FILTERED)
SCREEN_SUPPLIED = frozenset({
    "you_address", "list_view", "filtered_contributors", "filtered_points",
    "you_filtered_index", "you_first_index", "you_first_hour", "filter_summary",
    "filtered_rows", "filtered_complete",
})
```

Compose `CuratorFilteredList()` and `CuratorListFilterEditor()` inside
`LIST_BODY_ID`; the editor starts hidden. Extend `_PANELS` and add
`"CuratorFilteredList": ("filtered_rows", "you_list_row", "filtered_complete")`
to `WIDGET_SIGNATURES`. The editor remains controller-driven rather than
payload-dispatched.

Initialize:

```python
self._list_view = LIST_RAW
self._filter_editor_open = False
self._custom_filter_values = empty_filter_values()
self._active_filter: FilterSpec | None = None
self._filter_summary: tuple[str, ...] = ()
self._filtered_rows: list[dict] | None = []
self._filtered_complete = False
self._filtered_source_reason: str | None = None
self._you_filtered_index: int | None = None
```

Change `c` list behavior to index `LIST_VIEWS` modulo three. While the editor is open, return without cycling. `_show_list_view()` displays exactly one table or the editor.

Replace the visible `f` binding with
`Binding("f", "toggle_filter", "Filter", show=False, priority=True)` so the
second `f` applies even while an Input owns focus. Make the existing `e` binding
priority too so editor-open export always reports the apply-first receipt. Keep
`action_toggle_analysis()` but do not bind it. Add these non-priority hidden
bindings so numeric Inputs retain digit entry:

```python
Binding("1", "apply_filter_preset('1')", "First 1000", show=False),
Binding("2", "apply_filter_preset('2')", "Hour 0", show=False),
Binding("3", "apply_filter_preset('3')", "Whale splash", show=False),
```

Update the binding contract to the exact key set
`{"r", "c", "w", "y", "f", "l", "e", "escape", "1", "2", "3"}`.
`action_apply_filter_preset(key: str)` returns unless `_mode == MODE_LIST` and
the editor is closed.

Implement one filter application helper:

```python
def _apply_filter(self, spec: FilterSpec) -> bool:
    data = self._title_data or {}
    result = self._data_manager.filtered_list_rows(
        self._export_dir or Path.home() / ".maxpane",
        expected_count=data.get("contributors_total"),
        live_rows=data.get("leaderboard_rows"),
        you_row=data.get("you_list_row"),
        spec=spec,
    )
    self._active_filter = spec
    self._filter_summary = filter_summary(spec)
    self._filtered_rows = result.rows
    self._filtered_complete = result.complete
    self._filtered_source_reason = result.source_reason
    self._you_filtered_index = None
    self._dispatch_filtered_list(data)
    self._dispatch_list_hero(data)
    return True
```

Catch `FilterDataUnavailable` at the caller: custom apply shows the error and stays in the editor; a preset switches to the filtered table and shows an unavailable receipt without crashing.

`action_toggle_filter()` does nothing outside list mode. On first/next open it switches to Filtered, calls `editor.set_values(self._custom_filter_values)`, clears the error, and shows the editor. On apply it reads and stores `editor.values()`, calls `parse_filter_values()`, focuses/names validation errors, then calls `_apply_filter()` and shows the table only on success.

`_dispatch_filtered_list()` passes current rows, the payload's `you_list_row`, and completeness. `_dispatch_list_hero()` merges the manager payload with:

```python
{
    "list_view": self._list_view,
    "filtered_contributors": len(self._filtered_rows) if isinstance(self._filtered_rows, list) else None,
    "filtered_points": sum(row["points"] for row in self._filtered_rows if isinstance(row.get("points"), int)),
    "you_filtered_index": self._you_filtered_index,
    "you_first_index": (data.get("you_list_row") or {}).get("first_index"),
    "you_first_hour": (data.get("you_list_row") or {}).get("first_hour"),
    "filter_summary": self._filter_summary,
}
```

Remove `CuratorListHero` from the ordinary payload-only dispatch loop and call
`_dispatch_list_hero(data)` in its place. Add `CuratorFilteredList` to the
mounted widget inventory but dispatch it only through `_dispatch_filtered_list()`;
its state belongs to the screen, not `CURATOR_KEYS`. Call `_dispatch_list_hero()`
from `_show_list_view()` whenever `_title_data` exists so `c` repaints both hero
cards immediately without waiting for the next poll.

Handle the message in
`on_list_order_changed(self, event: ListOrderChanged)`. Only when
`event.kind == "filtered"`, find the configured wallet's casefolded address in
`event.addresses`, set one-based `_you_filtered_index`, and redispatch the list
hero without changing aggregates.

Remove `f linked` from `KEY_HINTS`. Keep the existing `e` analysis-mode branch and legacy action method intact.

- [ ] **Step 4: Run navigation and dispatch tests green**

Run:

```bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "list or preset or filter or dispatch or binding or linked" -q
```

Expected: selected screen tests pass, including existing raw/clean behaviors adapted to the three-view cycle.

- [ ] **Step 5: Commit Task 6 explicitly**

```bash
git add maxpane_dashboard/screens/curator.py maxpane_dashboard/themes/minimal.tcss tests/screens/test_curator_screen.py
git commit -m "feat(curator): wire filtered list controls"
```

---

### Task 7: Filtered Export, Receipts, And Validation Degradation

**Files:**
- Modify: `maxpane_dashboard/screens/curator.py`
- Modify: `maxpane_dashboard/widgets/curator/lists.py`
- Modify: `maxpane_dashboard/widgets/curator/list_filter.py`
- Modify: `tests/screens/test_curator_screen.py`
- Modify: `tests/widgets/test_curator_widgets.py`

**Interfaces:**
- Produces: `~/.maxpane/curator_filtered_list.json` as a plain ordered JSON array.
- Produces: `CuratorFilteredList.mark_filter_applied(limited: bool)` and visible fallback/error receipts.
- Keeps: raw/clean and hidden-analysis export paths unchanged.

- [ ] **Step 1: Write failing export and receipt tests**

Add screen tests for exact ordering, empty export, editor rejection, and fallback receipt:

```python
async def test_e_exports_filtered_rows_in_visible_sort_order_with_indexes(tmp_path):
    payload = _list_payload(3)
    screen = _export_screen(tmp_path, payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "1")
        table = screen.query_one("#curator-filtered-list-table", DataTable)
        points = [column[0] for column in screen.query_one(CuratorFilteredList)._columns].index("points")
        x = table._get_column_region(points).x + 1
        assert await pilot.click(table, offset=(x, 0))
        assert await pilot.click(table, offset=(x, 0))
        await pilot.press("e")
        await pilot.pause()

    rows = json.loads((tmp_path / "curator_filtered_list.json").read_text())
    assert [row["rank"] for row in rows] == [3, 2, 1]
    assert [row["index"] for row in rows] == [1, 2, 3]
    assert not (tmp_path / "curator_filtered_list.json.tmp").exists()


async def test_filtered_empty_table_exports_an_empty_array(tmp_path):
    screen = _export_screen(tmp_path, _list_payload(3))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "c", "c", "e")
    assert json.loads((tmp_path / "curator_filtered_list.json").read_text()) == []


async def test_e_in_filter_editor_writes_nothing_and_names_apply_first(tmp_path):
    screen = _export_screen(tmp_path, _list_payload(3))
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "f", "e")
        await pilot.pause()
        assert "press f to apply filters first" in _screen_text(app)
    assert not (tmp_path / "curator_filtered_list.json").exists()


async def test_fallback_filter_receipt_says_only_first_1000_were_filtered(tmp_path):
    payload = _list_payload(3)
    payload["contributors_total"] = 19_522
    screen = _export_screen(tmp_path, payload)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        await pilot.press("l", "1")
        await pilot.pause()
        panel = _region_text(app, screen.query_one(CuratorFilteredList), screen)
    assert "first 1,000 wallets only" in panel
```

Add a write-failure test mirroring the existing raw list atomicity test: export once, monkeypatch the filtered writer to raise, press `e` again, assert the old bytes remain and the filtered panel shows `EXPORT_FAILED` without a stale saved receipt.

- [ ] **Step 2: Run filtered export tests red**

Run:

```bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "filtered and (export or receipt or apply_first or empty)" -q
```

Expected: missing filtered file and missing receipt failures.

- [ ] **Step 3: Implement atomic filtered export and source receipts**

Add:

```python
FILTERED_LIST_BASENAME = "curator_filtered_list"


def _write_filtered_list(directory: Path, rows: list[dict]) -> Path:
    path = directory / f"{FILTERED_LIST_BASENAME}.json"

    def write_json(temporary: Path) -> None:
        temporary.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    _atomic_write(directory, ((path, write_json),))
    return path
```

In the list export action, branch on `LIST_FILTERED` before raw/clean manager export:

1. If the editor is open, call `editor.show_error(None, "press f to apply filters first")` and return.
2. Read `rows = self.query_one(CuratorFilteredList).export_rows()`; an empty list is valid.
3. Atomically write with `_write_filtered_list()`.
4. On failure call `mark_export_failed()`; on success call `mark_exported(path)`.
5. Do not reload raw or cleaned sources after a filtered export.

Extend `_ListTable` receipt state with an optional plain source receipt. `mark_filter_applied(limited=True)` sets `first 1,000 wallets only`; a complete result clears it. Export success/failure takes display priority until the next filter application. In `_apply_filter()`, call the filtered panel's method with `limited=not result.complete` after updating its rows.

For a preset `FilterDataUnavailable`, show the exception message on the filtered panel receipt and render an unavailable filtered state. For custom filters, keep the editor open and use its field/error line as Task 6 specifies.

- [ ] **Step 4: Run export and existing atomic-write tests green**

Run:

```bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "export or receipt or apply_first" -q
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "receipt or export" -q
```

Expected: filtered and existing raw/clean/analysis export tests pass.

- [ ] **Step 5: Commit Task 7 explicitly**

```bash
git add maxpane_dashboard/screens/curator.py maxpane_dashboard/widgets/curator/lists.py maxpane_dashboard/widgets/curator/list_filter.py tests/screens/test_curator_screen.py tests/widgets/test_curator_widgets.py
git commit -m "feat(curator): export filtered list order"
```

---

### Task 8: Width, Regression, And Full Verification

**Files:**
- Modify: `tests/screens/test_curator_screen.py`
- Modify: `tests/widgets/test_curator_widgets.py`
- Modify only if a measured test fails: `maxpane_dashboard/themes/minimal.tcss`, `maxpane_dashboard/widgets/curator/lists.py`, `maxpane_dashboard/widgets/curator/list_filter.py`

**Interfaces:**
- Verifies: all three list modes fit at 143 columns and retain the two footer rows.
- Verifies: non-list curator views and shared heroes are unchanged.
- Verifies: the complete curator suite and repository suite remain at baseline.

- [ ] **Step 1: Add the final measured/regression tests before any layout adjustment**

Generalize `_first_list_width()` to accept `raw`, `cleaned`, or `filtered`, navigate with the required number of `c` presses, and require:

```python
@pytest.mark.parametrize("kind", ("raw", "cleaned", "filtered"))
async def test_every_list_clears_inside_the_143_column_app_pin(kind):
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
    width = await _first_list_width(kind)
    assert width == 143
    assert width <= FULL_LAYOUT_COLUMNS == 143
```

Add one test at 143x30 for each table asserting vertical scrollbar true, horizontal scrollbar false, and full-tier WINDOW present. Add one layout test proving the filtered YOU row and one blank line remain immediately above the status bar.

Add source-level regression assertions:

```python
def test_filter_changes_are_confined_to_the_curator_list_view():
    source = (_ROOT / "maxpane_dashboard" / "screens" / "curator.py").read_text()
    shared_hero = (_ROOT / "maxpane_dashboard" / "widgets" / "curator" / "hero.py").read_text()
    assert "CuratorListFilterEditor" in source
    assert "THE FILTERED LIST" not in shared_hero


async def test_dashboard_wallet_and_hidden_analysis_bodies_still_render():
    screen = _screen(_analysis_payload())
    app = _ThemedHarness(screen)
    async with app.run_test(size=(143, _TALL)) as pilot:
        await screen._do_refresh()
        assert "CLOCK" in _region_text(app, screen.query_one(CuratorHero), screen)
        await pilot.press("y")
        assert screen._mode == MODE_WALLET
        screen.action_back_to_dashboard()
        screen.action_toggle_analysis()
        assert screen._mode == MODE_ANALYSIS
        assert screen.query_one(f"#{ANALYSIS_BODY_ID}").display is True
```

- [ ] **Step 2: Run the measured tests and verify any failure is specific**

Run:

```bash
.venv/bin/pytest tests/screens/test_curator_screen.py -k "143_column or footer or confined or hidden_analysis" -q
.venv/bin/pytest tests/widgets/test_curator_widgets.py -k "list and width" -q
```

Expected: pass. If a width fails, inspect the declared `tier_cost()` and actual table `content_size.width`; adjust only CREDIT or secondary-tier shedding. Do not change ADDRESS, ENS, POINTS, or the global 143-column pin.

- [ ] **Step 3: Run the entire curator suite**

Run:

```bash
.venv/bin/pytest tests/data/test_curator*.py tests/analytics/test_curator_signals.py tests/widgets/test_curator_widgets.py tests/screens/test_curator_screen.py tests/test_curator_registration.py -q
```

Expected: all curator tests pass with no network access.

- [ ] **Step 4: Run the repository suite and compare with the known baseline**

Run:

```bash
.venv/bin/pytest -q
```

Expected: no new failures. The pre-feature baseline was `4754 passed` with 13 known unrelated FWA/Surf accessibility failures and 6 warnings; any changed failure in curator files is a regression and must be fixed before continuing.

- [ ] **Step 5: Inspect the final diff and commit only verification adjustments**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Confirm no live capture is staged. If Step 1 required test/layout edits not already committed, commit only those explicit paths:

```bash
git add tests/screens/test_curator_screen.py tests/widgets/test_curator_widgets.py maxpane_dashboard/themes/minimal.tcss maxpane_dashboard/widgets/curator/lists.py maxpane_dashboard/widgets/curator/list_filter.py
git commit -m "test(curator): verify filtered list layout"
```

If those files are unchanged because earlier tasks already satisfied the final tests, do not create an empty commit.

---

## Completion Checklist

- [ ] `c` cycles raw, cleaned, and filtered in that order.
- [ ] `1`, `2`, and `3` apply the exact approved presets only in list mode.
- [ ] `f` opens/applies the custom editor only in list mode; Linked Analysis remains implemented but unbound.
- [ ] Empty custom criteria produce an empty table.
- [ ] All custom ranges, ENS, window, band, evidence-family, and whale filters work with approved AND/OR semantics.
- [ ] All tables show dynamic INDEX, preserve domain rank, remove LINK, and fit at 143 columns.
- [ ] The first hero card and configured-wallet card always describe the visible list.
- [ ] The third hero card contains the exact five white, regular-weight filter-help lines.
- [ ] The configured-wallet footer remains aligned and has a blank line below it.
- [ ] Filtered export preserves visible sort order and one-based indexes.
- [ ] Complete raw export yields all filtered matches; absent/invalid export limits filtering to the first 1,000 with a visible receipt.
- [ ] No network call occurs while filtering or exporting.
- [ ] Curator suite passes; repository suite has no new failures.
