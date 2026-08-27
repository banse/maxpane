"""Terminal-cell regression tests for the shared fitter and padder."""

from __future__ import annotations

import ast
import inspect

from rich.cells import cell_len

from maxpane_dashboard.widgets import cell_fitting
from maxpane_dashboard.widgets.cell_fitting import fit_cell, pad_cell
from maxpane_dashboard.widgets.surf import feed, launchpad_activity


def test_ascii_is_unchanged_when_it_fits_and_marked_when_it_does_not() -> None:
    assert fit_cell("alpha", 5) == ("alpha", False)
    assert fit_cell("alphabet", 5) == ("alph…", True)


def test_cjk_width_mutation_cannot_pass_as_character_width() -> None:
    fitted, clipped = fit_cell("海豚ABC", 5)
    assert (fitted, clipped) == ("海豚…", True)
    assert cell_len(fitted) == 5


def test_wide_boundary_never_emits_half_a_glyph() -> None:
    assert fit_cell("A海B", 3) == ("A…", True)
    assert fit_cell("海豚", 3) == ("海…", True)
    assert fit_cell("海豚", 2) == ("…", True)


def test_emoji_is_measured_as_terminal_cells() -> None:
    fitted, clipped = fit_cell("🙂🙂x", 4)
    assert (fitted, clipped) == ("🙂…", True)
    assert cell_len(fitted) <= 4


def test_markup_looking_text_is_fitted_as_literal_text() -> None:
    # The helper neither parses nor escapes. This ordering lets the widget
    # fit raw text first and call safe_markup afterwards without bisecting an
    # escape pair.
    assert fit_cell("[red]boom[/]", 8) == ("[red]bo…", True)


def test_zero_and_one_cell_budgets_are_explicit() -> None:
    assert fit_cell("", 0) == ("", False)
    assert fit_cell("x", 0) == ("", True)
    assert fit_cell("wide", 1) == ("…", True)


def test_padding_normalizes_ascii_cjk_and_emoji_without_truncating() -> None:
    for raw, width, expected in (
        ("abc", 5, "abc  "),
        ("海", 3, "海 "),
        ("🙂x", 5, "🙂x  "),
        ("海豚", 3, "海豚"),
        ("abc", 0, "abc"),
    ):
        padded = pad_cell(raw, width)
        assert padded == expected
        assert cell_len(padded) == max(width, cell_len(raw))


def test_surf_keeps_its_compatibility_helpers() -> None:
    assert feed._cell_fit is fit_cell
    assert launchpad_activity._pad is pad_cell
    assert launchpad_activity._clip("海豚", 3) == fit_cell("海豚", 3)[0]


def test_shared_cell_helpers_have_no_data_clock_or_io_imports() -> None:
    tree = ast.parse(inspect.getsource(cell_fitting))
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports <= {"__future__", "rich.cells"}
