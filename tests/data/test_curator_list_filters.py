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
