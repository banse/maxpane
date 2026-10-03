"""The seat widgets' self-imposed contract (spec §14 "Rules", purity walk two-sided; contract §C.15, §E).

Three families, and every one is a walk off disk rather than a typed list:

1. **Side one** -- ``widgets/seat/*`` import no ``maxpane_dashboard.data``, no ``subprocess``/``socket``/``httpx``,
   and from ``maxpane_dashboard.analytics`` only ``_PURE_SEAT_ANALYTICS_ALLOWED``, each of which is scanned
   transitively to a fixed point (``tests/widgets/test_surf_widget_contract.py:387`` is the shape).
2. **Side two** -- ``analytics/seat_*.py`` and ``data/seat_models.py`` import no ``textual``, ``subprocess``,
   ``socket``, ``httpx``.
3. **Side three** -- ``data/seat_tail.py`` and ``data/seat_broker_client.py`` are the only seat modules whose AST
   contains ``subprocess.run``/``Popen``/``socket.socket``, every ``run`` carries ``timeout=`` and a list argv.

Plus the link helper (``_chain.job_link_style``) and, from Task 8.7, the ``update_data`` signatures against
``SEAT_WIDGET_SIGNATURES`` and the grammar-word restatement of ``SeatLog``.

Mutations that redden this file: ``from maxpane_dashboard.data import seat_models`` in any ``widgets/seat``
module -> ``test_seat_widgets_import_only_allowed_pure_analytics``; ``import subprocess`` in
``analytics/seat_signals.py`` -> ``test_the_allowed_seat_analytics_are_themselves_pure``; a
``subprocess.run(argv)`` without ``timeout=`` in ``data/seat_tail.py`` -> ``test_only_the_two_seams_use_subprocess_or_socket``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest
from rich.style import Style

import maxpane_dashboard
from maxpane_dashboard.widgets import seat as seat_widgets
from maxpane_dashboard.widgets.explorer import IMD, open_action, url_for
from maxpane_dashboard.widgets.seat import _chain

PKG = Path(maxpane_dashboard.__file__).parent

#: Contract §E (1): the analytics modules a seat widget may import, each scanned transitively.
_PURE_SEAT_ANALYTICS_ALLOWED = frozenset({
    "maxpane_dashboard.analytics.seat_redact",
    "maxpane_dashboard.analytics.seat_signals",
    "maxpane_dashboard.analytics.seat_tiers",
    "maxpane_dashboard.analytics.seat_cost",
    "maxpane_dashboard.analytics.seat_auth",
    "maxpane_dashboard.analytics.seat_records",
})

#: Contract §E (3): the only two seat modules allowed a subprocess or a socket.
_SEAMS = ("maxpane_dashboard/data/seat_tail.py", "maxpane_dashboard/data/seat_broker_client.py")

_FORBIDDEN_IN_WIDGETS = ("maxpane_dashboard.data", "subprocess", "socket", "httpx", "aiohttp")
_FORBIDDEN_IN_PURE = ("textual", "subprocess", "socket", "httpx", "aiohttp", "maxpane_dashboard.data", "maxpane_dashboard.widgets")


def _imported_names(module) -> list[str]:
    """Every dotted name a module's own source imports (``from X import Y`` yields X and X.Y)."""
    tree = ast.parse(inspect.getsource(module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported += [f"{base}.{a.name}" if base else a.name for a in node.names]
    return imported


def _module_of(name: str) -> str:
    """``maxpane_dashboard.analytics.seat_redact.redact`` -> its module (the longest importable prefix)."""
    parts = name.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = ".".join(parts[:cut])
        try:
            importlib.import_module(candidate)
        except ImportError:
            continue
        if candidate in importlib.sys.modules and hasattr(importlib.sys.modules[candidate], "__file__"):
            return candidate
    return name


def _seat_widget_modules() -> tuple:
    """Every module under ``maxpane_dashboard/widgets/seat/``, imported, ``__init__`` included."""
    package = Path(seat_widgets.__file__).parent
    stems = sorted(path.stem if path.stem != "__init__" else "" for path in package.glob("*.py"))
    modules = tuple(
        importlib.import_module(f"{seat_widgets.__name__}.{stem}" if stem else seat_widgets.__name__)
        for stem in stems
    )
    assert len(modules) >= 2, "the walk is not seeing the package and would prove nothing"
    return modules


def test_the_module_walk_sees_every_file_in_the_package():
    on_disk = {path.stem for path in Path(seat_widgets.__file__).parent.glob("*.py")}
    walked = {
        module.__name__.rsplit(".", 1)[-1] if module is not seat_widgets else "__init__"
        for module in _seat_widget_modules()
    }
    assert walked == on_disk


@pytest.mark.parametrize("module", _seat_widget_modules(), ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_seat_widgets_import_only_allowed_pure_analytics(module):
    # spec §14 purity walk side (1); contract §E (1)
    for imported in _imported_names(module):
        for forbidden in _FORBIDDEN_IN_WIDGETS:
            assert not imported.startswith(forbidden), (module.__name__, imported)
        if imported.startswith("maxpane_dashboard.analytics"):
            assert _module_of(imported) in _PURE_SEAT_ANALYTICS_ALLOWED, (module.__name__, imported)


def test_the_allowed_seat_analytics_are_themselves_pure():
    # spec §14 purity walk side (1), transitive half; side (2) for analytics/seat_* and data/seat_models
    assert _PURE_SEAT_ANALYTICS_ALLOWED
    seen: set[str] = set()
    queue = sorted(_PURE_SEAT_ANALYTICS_ALLOWED) + ["maxpane_dashboard.data.seat_models"]
    scanned = 0
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if not hasattr(module, "__file__"):
            continue
        scanned += 1
        for imported in _imported_names(module):
            for forbidden in ("textual", "subprocess", "socket", "httpx", "aiohttp", "maxpane_dashboard.widgets"):
                assert not imported.startswith(forbidden), (name, imported)
            if name != "maxpane_dashboard.data.seat_models":
                assert not imported.startswith("maxpane_dashboard.data"), (name, imported)
            if imported.startswith("maxpane_dashboard.analytics"):
                queue.append(_module_of(imported))
    assert scanned >= len(_PURE_SEAT_ANALYTICS_ALLOWED) + 1


def _seat_source_files() -> list[Path]:
    files = sorted((PKG / "data").glob("seat_*.py")) + sorted((PKG / "analytics").glob("seat_*.py"))
    files += sorted((PKG / "widgets" / "seat").glob("*.py")) + sorted((PKG / "screens").glob("seat*.py"))
    files.append(PKG / "seat_cli.py")
    return [f for f in files if f.exists()]


def _calls(tree: ast.AST, *names: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            dotted = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if dotted in names:
                out.append(node)
    return out


def _io_calls(tree: ast.AST) -> list[ast.Call]:
    """Real subprocess/socket calls only: ``subprocess.X(...)`` / ``socket.X(...)`` attribute calls, plus bare
    names bound by ``from subprocess import …`` / ``from socket import …``. A local coroutine named ``run``
    (``asyncio.ensure_future(run())`` in ``data/seat_manager.py``), ``asyncio.run(...)`` and ``App.run()`` are
    not I/O seams and must not trip the walk."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in ("subprocess", "socket"):
            bound |= {a.asname or a.name for a in node.names}
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {"subprocess", "socket"}:
            out.append(node)
        elif isinstance(func, ast.Name) and func.id in bound:
            out.append(node)
    return out


def test_only_the_two_seams_use_subprocess_or_socket():
    # spec §14 purity walk side (3); contract §E (3)
    for path in _seat_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(PKG.parent).as_posix()
        imports = {n for node in ast.walk(tree) for n in (
            [a.name for a in node.names] if isinstance(node, ast.Import)
            else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        )}
        uses_io = any(n.split(".")[0] in ("subprocess", "socket") for n in imports)
        if rel not in _SEAMS:
            assert not uses_io, f"{rel} imports subprocess/socket; only {_SEAMS} may"
            assert not _io_calls(tree), rel
            continue
        for call in _calls(tree, "run", "check_output"):
            kwargs = {kw.arg for kw in call.keywords}
            assert "timeout" in kwargs, f"{rel}: subprocess call without timeout= at line {call.lineno}"
            assert "shell" not in kwargs, f"{rel}: shell= at line {call.lineno}"
            assert call.args and isinstance(call.args[0], (ast.List, ast.Name, ast.Attribute, ast.Call, ast.Subscript)), rel
        if _calls(tree, "Popen"):
            assert "stop_timeout_s" in path.read_text(encoding="utf-8"), f"{rel}: Popen without a documented stop_timeout_s"


# -- _chain -----------------------------------------------------------------------------


def test_the_seat_explorer_is_the_imd_job_explorer():
    assert _chain.EXPLORER is IMD
    assert IMD.kinds == ("job",)
    assert _chain.JOB_COLS == 8


def test_job_link_style_links_a_canonical_uuid_and_nothing_else():
    job = "b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70"
    style = _chain.job_link_style(job)
    assert isinstance(style, Style)
    assert style.link == url_for(IMD, "job", job) == f"https://explorer.imd.fun/jobs/{job}"
    assert style.meta == {"@click": open_action(IMD, "job", job)}
    for bad in (None, "", job.upper(), "day1abcd-not-a-uuid", 7, "../../x" + job[7:]):
        assert _chain.job_link_style(bad) is None, bad


# -- the update_data signatures against the frozen contract (Task 8.7) ---------------------

from maxpane_dashboard.data.seat_models import SEAT_KEYS, SEAT_WIDGET_SIGNATURES  # noqa: E402  (a test may import data)


def test_seat_package_exports_exactly_the_fifteen_names():
    assert seat_widgets.__all__ == ["SeatHero", "SeatNow", "SeatJob", "SeatLog", "SeatMachine", "SeatCost", "SeatOutputTokens",
                                  "SeatLedgerTable", "SeatConfig", "SeatSkills", "SeatRecords", "SeatNodes", "SeatControl", "SeatGate", "SeatAudit"]
    assert set(SEAT_WIDGET_SIGNATURES) == set(seat_widgets.__all__)


@pytest.mark.parametrize("name", sorted(SEAT_WIDGET_SIGNATURES))
def test_update_data_names_exactly_the_contract_signature(name):
    # contract §C.4/§C.15: every keyword is a SEAT_KEYS name with default None, in the contract's order, plus **_kwargs
    cls = getattr(seat_widgets, name)
    params = inspect.signature(cls.update_data).parameters
    named = [p for p in params.values() if p.name != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(p.name for p in named) == SEAT_WIDGET_SIGNATURES[name]
    assert all(p.default is None for p in named), name
    assert all(p.name in SEAT_KEYS for p in named), name
    assert any(p.kind is p.VAR_KEYWORD for p in params.values()), f"{name}.update_data lacks **_kwargs"


def test_now_signature_independently_names_the_daemon_running_count():
    assert SEAT_WIDGET_SIGNATURES['SeatNow'] == (
        'seat_current', 'seat_queue', 'seat_last_task', 'seat_daemon_work', 'seat_daemon_state', 'seat_daemon_running',
        'seat_auth_degraded', 'seat_auth_reasons', 'seat_auth_credential_file_mtime_utc',
        'seat_standing_running', 'seat_sources', 'seat_as_of_hhmm', 'seat_offline',
    )
