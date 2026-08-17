"""WP1.8 — the no-I/O gate over the core.

WP0's freeze already asserts stdlib-only against ``sys.stdlib_module_names``;
this gate adds the *named* transports and frameworks — including ``asyncio``,
which is stdlib and therefore invisible to the stdlib-only check — and proves
the whole public surface imports under ``python -I -S``, where site-packages
does not exist and only the standard library can answer.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "sybilkit"

#: WP2's optional fetchers and CLI may import a transport; nothing else may.
EXEMPT = ("sources",)
EXEMPT_FILES = ("cli.py",)

BANNED = {"httpx", "asyncio", "requests", "maxpane", "maxpane_dashboard", "textual"}


def _core_modules() -> list[Path]:
    modules = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        if rel.parts[0] in EXEMPT or rel.name in EXEMPT_FILES:
            continue
        modules.append(path)
    return modules


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_core_imports_no_io() -> None:
    """Every core module — signals included, ``sources/`` and ``cli.py``
    excluded — imports none of the banned transports and frameworks.  The
    scan walks the AST, so an aliased or nested import cannot slip past a
    spelling nobody thought of."""
    modules = _core_modules()
    assert len(modules) >= 12  # the core actually got scanned
    offenders = [
        f"{path.relative_to(SRC)}: {clash}"
        for path in modules
        if (clash := BANNED & _imported_roots(path))
    ]
    assert not offenders, offenders


def test_the_public_surface_imports_with_zero_third_party_packages() -> None:
    """PRD §3.5, checked genuinely: ``python -I -S`` never adds site-packages
    to ``sys.path``, so the import below succeeds only if the whole surface is
    standard library plus this package."""
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(SRC.parent)!r}); "
        "import sybilkit; "
        "from sybilkit import detect, Dataset, DetectConfig; "
        "assert not any('site-packages' in p for p in sys.path); "
        "print('stdlib-only ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "stdlib-only ok" in proc.stdout
