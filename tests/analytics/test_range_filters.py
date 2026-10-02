"""``analytics/range_filters``: the from/to rules THE LIST and surf's RECORD filter share."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import range_filters
from maxpane_dashboard.analytics.range_filters import (
    FilterValidationError,
    check_order,
    number_text,
    parse_number,
    range_text,
    row_number,
)


@pytest.mark.parametrize("blank", (None, "", "   "))
@pytest.mark.parametrize("integer", (True, False))
def test_a_blank_field_is_unset(blank, integer):
    assert parse_number("rank_min", blank, integer=integer) is None


@pytest.mark.parametrize(
    ("value", "integer", "expected"),
    (
        ("12", True, 12),
        (" 7 ", True, 7),
        (3, True, 3),
        (4.0, True, 4),
        ("1.5", False, 1.5),
        ("0", False, 0.0),
        (2, False, 2.0),
    ),
)
def test_a_usable_number_parses(value, integer, expected):
    parsed = parse_number("f", value, integer=integer)
    assert parsed == expected and type(parsed) is type(expected)


@pytest.mark.parametrize(
    ("value", "integer"),
    (
        (True, True),
        (False, False),
        ("1.5", True),
        (1.5, True),
        (-1, True),
        ("-1", True),
        ("abc", True),
        (math.inf, True),
        (math.nan, True),
        ("-0.5", False),
        ("nan", False),
        ("inf", False),
        ("abc", False),
        (object(), False),
    ),
)
def test_an_unusable_number_names_its_field(value, integer):
    with pytest.raises(FilterValidationError) as raised:
        parse_number("took_min", value, integer=integer)
    assert raised.value.field == "took_min"
    assert str(raised.value) == "took_min must be a non-negative number"


def test_order_names_the_from_field_of_the_first_inverted_pair():
    parsed = {"a_min": 1, "a_max": 2, "b_min": 9, "b_max": 3, "c_min": 8, "c_max": 1}
    with pytest.raises(FilterValidationError) as raised:
        check_order(parsed, (("a_min", "a_max"), ("b_min", "b_max"), ("c_min", "c_max")))
    assert raised.value.field == "b_min"
    assert str(raised.value) == "b_min must not exceed b_max"


@pytest.mark.parametrize(
    "parsed",
    ({"lo": 3, "hi": 3}, {"lo": 3, "hi": None}, {"lo": None, "hi": 1}, {}),
)
def test_equal_or_half_open_bounds_are_in_order(parsed):
    check_order(parsed, (("lo", "hi"),))


@pytest.mark.parametrize(
    ("value", "integer", "expected"),
    (
        (5, True, 5),
        ("6", True, 6),
        (True, True, None),
        (2.0, True, None),
        ("x", True, None),
        (None, True, None),
        (1.25, False, 1.25),
        ("2.5", False, 2.5),
        (math.nan, False, None),
        ("inf", False, None),
        (False, False, None),
        (None, False, None),
    ),
)
def test_a_row_value_is_a_finite_number_or_none(value, integer, expected):
    assert row_number({"f": value}, "f", integer=integer) == expected


def test_number_text_groups_integers_and_trims_floats():
    assert number_text(1234567) == "1,234,567"
    assert number_text(2.5) == "2.5"
    assert number_text(3.0) == "3"


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    (
        (None, None, None),
        (1, 1, "took 1 min"),
        (1, 2.5, "took 1-2.5 min"),
        (3, None, "took >=3 min"),
        (None, 1500, "took <=1,500 min"),
    ),
)
def test_range_text_words_every_bound_shape(low, high, expected):
    assert range_text("took ", low, high, unit=" min") == expected


def test_range_text_without_a_unit_is_curators_spelling():
    assert range_text("rank ", 1, 1000) == "rank 1-1,000"


def test_curator_uses_the_one_validation_error():
    """THE LIST's data module re-exports the hoisted class rather than keeping its own."""
    from maxpane_dashboard.data import curator_list_filters

    assert curator_list_filters.FilterValidationError is FilterValidationError
    for name in ("_parse_number", "_row_number", "_number_text"):
        assert not hasattr(curator_list_filters, name), name


@pytest.mark.guard
def test_range_filters_is_stdlib_only():
    tree = ast.parse(Path(range_filters.__file__).read_text())
    imported = {
        (node.module or "").split(".")[0] if isinstance(node, ast.ImportFrom)
        else alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported <= {"__future__", "math", "typing"}, imported
