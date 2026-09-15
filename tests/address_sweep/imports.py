"""Which modules import the address helper, in any import form (PRD §7 E3).

Two sweep checks ask the same question and must agree on the answer: E2's
per-widget coverage ("a mounted widget whose module imports the helper must
produce an icon") and E3's agreement test ("a dashboard whose widgets import the
helper cannot be declared address-free"). A text search for the dotted path
misses ``from maxpane_dashboard.widgets import address`` and every relative
form (``from ..address import address_text``), so the imports are resolved from
the AST instead.
"""

from __future__ import annotations

import ast
import functools
import importlib
import importlib.util
import pkgutil

HELPER = "maxpane_dashboard.widgets.address"
WIDGETS = "maxpane_dashboard.widgets"


def _base_of(module_name: str, is_package: bool, level: int, module: str | None) -> str:
    """The absolute module a ``from … import`` statement names."""
    if level == 0:
        return module or ""
    package = module_name if is_package else module_name.rpartition(".")[0]
    parts = package.split(".")
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    base = ".".join(parts)
    return f"{base}.{module}" if module else base


def imported_names(source: str, module_name: str, is_package: bool = False) -> set[str]:
    """Every absolute dotted name ``source`` imports.

    ``from pkg import name`` contributes both ``pkg`` and ``pkg.name``: whether
    ``name`` is a submodule or an attribute is not knowable from the AST, and a
    spurious ``pkg.Class`` entry never equals a module path.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _base_of(module_name, is_package, node.level, node.module)
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


@functools.lru_cache(maxsize=None)
def module_imports(module_name: str) -> frozenset[str]:
    spec = importlib.util.find_spec(module_name)
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return frozenset()
    with open(spec.origin, encoding="utf-8") as handle:
        source = handle.read()
    return frozenset(imported_names(source, module_name, spec.submodule_search_locations is not None))


@functools.lru_cache(maxsize=None)
def imports_helper(module_name: str) -> bool:
    return module_name != HELPER and HELPER in module_imports(module_name)


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def widget_modules_of(module_name: str) -> set[str]:
    """The ``maxpane_dashboard.widgets.*`` modules ``module_name`` imports,
    each expanded to every module under it when it is a package."""
    out: set[str] = set()
    for name in module_imports(module_name):
        if not name.startswith(WIDGETS + ".") or not _is_module(name):
            continue
        out.add(name)
        pkg = importlib.import_module(name)
        if hasattr(pkg, "__path__"):
            out.update(m.name for m in pkgutil.walk_packages(pkg.__path__, prefix=name + "."))
    return out
