"""The lean entrypoint's import graph, by AST (spec §15 "Lean entrypoint and versioning"; contract §C.17).

``pepepane`` constructs no manager other than ``SeatManager`` and never imports
``maxpane_dashboard.app``, ``data.surf_manager``, ``data.curator_manager``, ``data.fwa_*``
or ``sybilkit``. What it cannot claim: ``data/__init__.py`` eagerly imports the
FrenPet/base manager *modules* -- imported, never constructed (fill7 §4). The
``start_tail`` call site is ``main()`` alone, guarded by ``if not … once``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import maxpane_dashboard

PKG = Path(maxpane_dashboard.__file__).parent
SEAT_CLI = PKG / "seat_cli.py"
FORBIDDEN = ("maxpane_dashboard.app", "maxpane_dashboard.data.surf_manager", "maxpane_dashboard.data.curator_manager",
             "maxpane_dashboard.data.fwa_manager", "maxpane_dashboard.data.fwa_client", "sybilkit", "maxpane_dashboard.__main__",
             "maxpane_dashboard.screens.game_select", "maxpane_dashboard.screens.splash")

pytestmark = pytest.mark.guard


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.add(base)
            names.update(f"{base}.{a.name}" for a in node.names)
    return names


def test_seat_cli_imports_no_app_or_other_managers():
    tree = ast.parse(SEAT_CLI.read_text(encoding="utf-8"))
    imported = _imports(tree)
    for name in imported:
        for forbidden in FORBIDDEN:
            assert not (name == forbidden or name.startswith(forbidden + ".")), (name, forbidden)
    assert "maxpane_dashboard.data.seat_manager.SeatManager" in imported


def test_seat_cli_constructs_only_a_seat_manager():
    tree = ast.parse(SEAT_CLI.read_text(encoding="utf-8"))
    constructed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.endswith("Manager") or name == "build_fixture_manager":
                constructed.add(name)
    assert constructed == {"SeatManager", "build_fixture_manager"}, constructed
    init = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "SeatApp")
    init_fn = next(n for n in init.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    assert not [n for n in ast.walk(init_fn) if isinstance(n, ast.Call) and (getattr(n.func, "id", "") or getattr(n.func, "attr", "")).endswith("Manager")]


def test_start_tail_call_site_is_main_and_guarded_by_once():
    call_files = []
    for path in PKG.rglob("*.py"):
        if path == PKG / "data" / "seat_manager.py":
            continue  # the definition
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "start_tail" for n in ast.walk(tree)):
            call_files.append(path.relative_to(PKG).as_posix())
    assert call_files == ["seat_cli.py"], call_files
    tree = ast.parse(SEAT_CLI.read_text(encoding="utf-8"))
    main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")

    def guarded(node, guards):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "start_tail":
                assert any("once" in ast.unparse(g.test) for g in guards), "start_tail must sit under an `if … once` guard"
                found.append(True)
            guarded(child, guards + [child] if isinstance(child, ast.If) else guards)

    found: list[bool] = []
    guarded(main_fn, [])
    assert found == [True]
