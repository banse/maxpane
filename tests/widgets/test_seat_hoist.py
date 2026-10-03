"""The pepepane hoist (spec §15 "Hoist commit"; contract §A.1, §C.1, §C.2).

Three moves, each with a re-export shim at the old path so no ``widgets/surf``
body or test changes: ``widgets/surf/_swarm_table.py`` -> ``widgets/swarm_table.py``,
``widgets/surf/_swarm_seat.py`` -> ``widgets/seat_words.py``, and ``mmdd_hhmm`` /
``short_model`` from ``widgets/surf/_fmt.py`` into ``widgets/fmt.py``.

Mutations that redden this file (spec §14; WP0 proofs): delete one line of a
shim -> ``test_shims_reexport_every_public_name``; put ``from
maxpane_dashboard.widgets.surf._fmt import DASH`` back into ``swarm_table.py`` ->
``test_swarm_table_imports_dash_from_shared_fmt``; re-declare ``short_model`` in
``_fmt.py`` -> ``test_surf_fmt_reexports_the_moved_formatters``.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from maxpane_dashboard.widgets import fmt
from maxpane_dashboard.widgets.surf import _fmt as surf_fmt

_WIDGETS = Path(fmt.__file__).parent

#: (old shim path, new shared module, the private names the shim must also carry).
_SHIMS = [
    pytest.param(
        "maxpane_dashboard.widgets.surf._icons",
        "maxpane_dashboard.widgets.seat_icons",
        ("_styles", "_shows", "_LINKED_RE", "_SHOWN_BEFORE_RE",
         "re", "Iterable", "Style", "Text", "COPY_GLYPH", "PROSE_ADDRESS_RE",
         "address_text", "short_address", "Explorer"),
        id="_icons",
    ),
    pytest.param(
        "maxpane_dashboard.widgets.surf._swarm_table",
        "maxpane_dashboard.widgets.swarm_table",
        ("_EMPTY_ITEM",),
        id="_swarm_table",
    ),
    pytest.param(
        "maxpane_dashboard.widgets.surf._swarm_seat",
        "maxpane_dashboard.widgets.seat_words",
        ("_whole", "_forms", "_num", "_reading"),
        id="_swarm_seat",
    ),
]

#: The hoisted shared modules: none may import back into ``widgets/surf/``
#: (spec §15: "otherwise the hoisted shared module would import back into widgets/surf/").
_SHARED = ["swarm_table.py", "seat_words.py", "fmt.py", "seat_icons.py"]

def _imports(path: Path) -> list[tuple[str, str]]:
    """``(module, name)`` for every import statement in *path*; ``("x", "*")`` for a star."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(alias.name, "") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            out += [(node.module or "", alias.name) for alias in node.names]
    return out


def _declared(path: Path) -> list[str]:
    """Top-level names a module *declares* (def/class/assignment), imports excluded."""
    names: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names += [t.id for t in targets if isinstance(t, ast.Name)]
    return names


# -- move 1: the swarm table base ---------------------------------------------


def test_swarm_table_imports_dash_from_shared_fmt():
    """Spec §15 hoist (1): ``_swarm_table.py:72`` becomes ``from widgets.fmt import DASH``."""
    imports = _imports(_WIDGETS / "swarm_table.py")
    assert ("maxpane_dashboard.widgets.fmt", "DASH") in imports
    surf_imports = [(m, n) for m, n in imports if "widgets.surf" in m]
    assert surf_imports == [], f"widgets/swarm_table.py imports back into surf: {surf_imports}"


@pytest.mark.parametrize("filename", _SHARED)
def test_no_hoisted_module_imports_back_into_surf(filename):
    """The three shared homes stay dashboard-agnostic (spec §15; rules/widgets.md)."""
    surf_imports = [(m, n) for m, n in _imports(_WIDGETS / filename) if "widgets.surf" in m]
    assert surf_imports == [], (filename, surf_imports)


def test_swarm_table_public_api_survived_the_move():
    """Contract preamble: the verified ``SwarmTableBase`` surface, byte-identical in meaning."""
    from maxpane_dashboard.widgets import swarm_table
    from maxpane_dashboard.widgets.panels import TableLeaderboard

    assert swarm_table.__all__ == ["CELL_PADDING", "UNAVAILABLE_ITEM", "SwarmTableBase", "table_cols"]
    assert issubclass(swarm_table.SwarmTableBase, TableLeaderboard)
    assert swarm_table.CELL_PADDING == 2
    assert swarm_table.table_cols([12, 8, 6]) == 32
    for hook in ("build_cells", "build_footer", "column_width", "column_plan", "store"):
        assert callable(getattr(swarm_table.SwarmTableBase, hook)), hook


# -- the shims ------------------------------------------------------------------


@pytest.mark.parametrize("shim_name, shared_name, private", _SHIMS)
def test_shims_reexport_every_public_name(shim_name, shared_name, private):
    """Contract §A.1: the old path re-exports every ``__all__`` name plus the named privates,
    as the *same objects* (``is``), and declares nothing of its own (hoist, never re-declare)."""
    shim = importlib.import_module(shim_name)
    shared = importlib.import_module(shared_name)
    assert list(shim.__all__) == list(shared.__all__)
    for name in (*shared.__all__, *private):
        assert getattr(shim, name) is getattr(shared, name), f"{shim_name}.{name} is not the shared object"
    assert _declared(Path(shim.__file__)) == [], "a shim re-exports; it declares nothing"


def test_seat_words_docstring_says_shared():
    """Contract §C.2: the 'Private to the surf package' sentence is replaced."""
    from maxpane_dashboard.widgets import seat_words

    assert "Private to the surf package" not in (seat_words.__doc__ or "")
    assert "Shared by the surf AGENT body and PEPEPANE" in (seat_words.__doc__ or "")
    assert seat_words.NODE_TITLES == {
        "oracle_assess": "ORACLE",
        "adversarial_review": "REVIEW",
        "build_contract_project": "BUILD",
    }
    assert seat_words.seat_token(420) == 420 and seat_words.seat_token(True) is None
    assert seat_words.count(1490) == "1,490" and seat_words.count(-1) is None
    assert seat_words.seat_state_line("ok") is None


# -- move 3: the two formatters -----------------------------------------------


def test_fmt_owns_mmdd_hhmm_and_short_model():
    """Contract §C.1: both bodies moved verbatim into ``widgets/fmt.py`` and joined ``__all__``."""
    assert "mmdd_hhmm" in fmt.__all__ and "short_model" in fmt.__all__
    assert fmt.mmdd_hhmm(0) == "??-?? ??:??"
    assert fmt.mmdd_hhmm(None) == "??-?? ??:??"
    stamp = 1_790_000_000
    assert fmt.mmdd_hhmm(stamp) == f"{fmt.mmdd(stamp)} {fmt.hhmm(stamp)}"
    assert re.fullmatch(r"\d\d-\d\d \d\d:\d\d", fmt.mmdd_hhmm(stamp))


@pytest.mark.parametrize("raw, expected", [
    ("claude-sonnet-5", "sonnet 5"), ("claude-opus-5-5", "opus 5.5"), ("claude-fable-5-1", "fable 5.1"),
    ("gpt-6-luna", "luna 6"), ("gpt-5.6-terra", "terra 5.6"), ("gpt-5.5", "gpt-5.5"),
    ("[/x]", None), (None, None), ("", None), ("claude-opus-5-5\n", "opus 5.5"),
    ("claude-opus-5-5-extra", "claude-opus-5-5-extra"),
])
def test_short_model_exact_cleaned_patterns_from_the_shared_home(raw, expected):
    """The surf cases of ``test_surf_swarm_seat_record.py::test_short_model_exact_cleaned_patterns``,
    asserted against ``widgets.fmt`` so the move changed no rendering."""
    assert fmt.short_model(raw) == expected


def test_surf_fmt_reexports_the_moved_formatters():
    """Contract §A.1: ``_fmt.py`` re-exports both (same objects), keeps them in its ``__all__``
    and no longer declares either. Mutation: paste ``short_model`` back into ``_fmt.py`` -> red."""
    assert surf_fmt.mmdd_hhmm is fmt.mmdd_hhmm
    assert surf_fmt.short_model is fmt.short_model
    assert "mmdd_hhmm" in surf_fmt.__all__ and "short_model" in surf_fmt.__all__
    declared = _declared(Path(surf_fmt.__file__))
    assert "mmdd_hhmm" not in declared and "short_model" not in declared
    imports = _imports(Path(surf_fmt.__file__))
    assert ("maxpane_dashboard.widgets.fmt", "mmdd_hhmm") in imports
    assert ("maxpane_dashboard.widgets.fmt", "short_model") in imports


def test_record_detail_and_submission_detail_still_import_through_the_shim():
    """``screens/record_detail.py:12`` and ``screens/submission_detail.py:9`` are never edited
    (contract §A.4); they must keep resolving through ``widgets/surf/_fmt.py``."""
    from maxpane_dashboard.screens import record_detail, submission_detail

    assert record_detail.mmdd_hhmm is fmt.mmdd_hhmm
    assert submission_detail.short_model is fmt.short_model
