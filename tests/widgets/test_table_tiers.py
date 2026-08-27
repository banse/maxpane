"""Contract tests for the screen-neutral table tier helpers."""

from __future__ import annotations

import ast
import inspect

from maxpane_dashboard.widgets import table_tiers
from maxpane_dashboard.widgets.curator import _table as curator_table
from maxpane_dashboard.widgets.table_tiers import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    tier_cost,
    title_with_hint,
    with_optional_suffix,
)


class _TableProbe:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def clear(self, *, columns: bool = False) -> None:
        self.calls.append(("clear", columns))

    def add_column(self, header: str, *, width: int) -> None:
        self.calls.append(("add_column", header, width))


_FULL = (("name", "NAME", 8), ("state", "STATE", 5))
_NARROW = (("name", "NAME", 8),)
_TIERS = (
    ("full", tier_cost(_FULL), _FULL, ""),
    ("narrow", tier_cost(_NARROW), _NARROW, "‹ widen: STATE"),
)


def test_tier_cost_counts_only_present_columns_and_their_padding() -> None:
    assert tier_cost(()) == 0
    assert tier_cost(_NARROW) == 10
    assert tier_cost(_FULL) == 17


def test_pick_tier_uses_tight_boundaries_and_a_narrow_fallback() -> None:
    assert pick_tier(_TIERS, 0) == ("full", _FULL, "")
    assert pick_tier(_TIERS, 17) == ("full", _FULL, "")
    assert pick_tier(_TIERS, 16) == (
        "narrow",
        _NARROW,
        "‹ widen: STATE",
    )
    assert pick_tier(_TIERS, 1)[0] == "narrow"


def test_install_columns_rebuilds_only_when_the_tier_changed() -> None:
    table = _TableProbe()
    assert install_columns(table, _FULL, _NARROW) is True
    assert table.calls == [
        ("clear", True),
        ("add_column", "NAME", 8),
        ("add_column", "STATE", 5),
    ]

    table.calls.clear()
    assert install_columns(table, _FULL, _FULL) is False
    assert table.calls == [("clear", False)]


def test_cells_projects_in_tier_order_without_inventing_absent_values() -> None:
    values = {"state": "open", "name": "FWA", "extra": "not a column"}
    assert cells(values, _FULL) == ["FWA", "open"]
    assert cells({"name": "FWA"}, _FULL, default="n/a") == ["FWA", "n/a"]
    assert cells(values, ()) == []


def test_title_hint_measures_cjk_and_emoji_in_terminal_cells() -> None:
    title = "海🙂"
    hint = "‹ widen: amounts"

    # This is 20 Python characters but 22 terminal cells. A len-based
    # implementation incorrectly places the descriptive hint at width 20.
    assert title_with_hint(title, hint, 20) == (
        f"{title}  [yellow]{WIDEN_HINT}[/]",
        True,
    )
    # The bare form is 11 characters but 13 cells for the same reason.
    assert title_with_hint(title, hint, 12) == (title, False)


def test_title_markup_is_measured_as_painted_and_too_narrow_is_explicit() -> None:
    assert title_with_hint("[bold]APP[/]", "‹ widen: amount", 12) == (
        f"[bold]APP[/]  [yellow]{WIDEN_HINT}[/]",
        True,
    )
    assert title_with_hint("APP", "‹ widen: amount", 11) == ("APP", False)
    assert title_with_hint("APP", "", 1) == ("APP", True)


def test_optional_suffix_uses_cell_width_not_character_count() -> None:
    assert with_optional_suffix("海", "🙂", 4) == "海🙂"
    assert with_optional_suffix("海", "🙂", 3) == "海"
    assert with_optional_suffix("base", "", 1) == "base"


def test_curator_keeps_the_original_import_contract() -> None:
    for name in table_tiers.__all__:
        assert getattr(curator_table, name) is getattr(table_tiers, name)


def test_shared_table_helpers_have_no_data_clock_or_io_imports() -> None:
    tree = ast.parse(inspect.getsource(table_tiers))
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports <= {"__future__", "rich.cells", "rich.errors", "rich.text"}
