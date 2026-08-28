"""Cross-widget purity and dispatch contract for FWA NETWORK."""

from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path

import maxpane_dashboard.widgets.fwa as package
from maxpane_dashboard.data.fwa_ecosystem_models import (
    FWA_NETWORK_DATA_KEYS,
    FWA_NETWORK_WIDGET_SIGNATURES,
)
from maxpane_dashboard.widgets.fwa import (
    FWAEcosystemRegistry,
    FWAFlowRail,
    FWAIRDropBoard,
    FWANetworkActivity,
    FWANetworkHero,
)

_CLASSES = {
    "FWANetworkHero": FWANetworkHero,
    "FWAFlowRail": FWAFlowRail,
    "FWAIRDropBoard": FWAIRDropBoard,
    "FWAEcosystemRegistry": FWAEcosystemRegistry,
    "FWANetworkActivity": FWANetworkActivity,
}


def test_package_exports_every_network_widget() -> None:
    for name, widget in _CLASSES.items():
        assert name in package.__all__
        assert getattr(package, name) is widget


def test_every_network_signature_is_exact_keyword_only_and_dispatchable() -> None:
    assert set(_CLASSES) == set(FWA_NETWORK_WIDGET_SIGNATURES)
    dispatched: set[str] = set()
    for name, widget in _CLASSES.items():
        signature = inspect.signature(widget.update_data)
        parameters = tuple(key for key in signature.parameters if key != "self")
        assert parameters == FWA_NETWORK_WIDGET_SIGNATURES[name]
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for key, parameter in signature.parameters.items()
            if key != "self"
        )
        dispatched.update(parameters)
    assert dispatched <= set(FWA_NETWORK_DATA_KEYS)


def _local_widget_imports(module_name: str) -> tuple[Path, set[str]]:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    path = Path(spec.origin)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module_name.rsplit(".", node.level)[0]
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            imports.add(target)
    return path, imports


def test_network_widget_import_graph_cannot_reach_data_io_or_clocks() -> None:
    pending = [widget.__module__ for widget in _CLASSES.values()]
    visited: set[str] = set()
    forbidden = (
        "maxpane_dashboard.data",
        "maxpane_dashboard.analytics",
        "httpx",
        "aiohttp",
        "requests",
        "urllib",
        "pathlib",
        "datetime",
        "time",
        "os",
    )

    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        path, imports = _local_widget_imports(module_name)
        bad = sorted(
            imported
            for imported in imports
            if any(
                imported == prefix or imported.startswith(prefix + ".")
                for prefix in forbidden
            )
        )
        assert not bad, f"{path.name} reaches forbidden imports: {bad}"
        pending.extend(
            imported
            for imported in imports
            if imported.startswith("maxpane_dashboard.widgets")
        )
