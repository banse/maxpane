"""Offline agreement between the supplied document and the curated atlas."""

import ast
from html.parser import HTMLParser
import inspect
from pathlib import Path
import re
import socket

import pytest

from maxpane_dashboard.data.workflow_guide_catalog import CATALOG
from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager
from maxpane_dashboard.data.workflow_guide_models import (
    WORKFLOW_GUIDE_KEYS,
    WORKFLOW_GUIDE_WIDGET_SIGNATURES,
)


class Figures(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.figures = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "figure":
            self.current = []

    def handle_data(self, data):
        if self.current is not None and data.strip():
            self.current.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "figure":
            self.figures.append(" ".join(self.current))
            self.current = None


def topic(name):
    return next(item for item in CATALOG["topics"] if item["id"] == name)


def test_frozen_contract_and_all_ten_source_figures_are_preserved():
    assert WORKFLOW_GUIDE_KEYS == ("workflow_guide",)
    assert WORKFLOW_GUIDE_WIDGET_SIGNATURES == {"WorkflowGuideView": ("workflow_guide",)}
    html = (Path(__file__).parents[1] / "fixtures/workflow_guide/source.html").read_text()
    figures = Figures(html).figures
    assert len(figures) == len(CATALOG["topics"]) == 10
    assert [item["number"] for item in CATALOG["topics"]] == list(range(1, 11))
    assert [item["id"] for item in CATALOG["topics"]] == [
        "purchase", "single_skill", "shapes", "contracts", "site",
        "company", "oracle", "intake", "schedules", "growth",
    ]
    for item, source in zip(CATALOG["topics"], figures):
        assert item["source_excerpt"] == source
        assert item["title"] in source


def test_provenance_remains_explicitly_historical_and_stats_fit_hero_cards():
    source = CATALOG["source"]
    assert source["date"] == "2026-10-18"
    assert source["plane"] == "745c1db4"
    assert source["worker"] == "0.1.2"
    assert source["title"] == "Swarm Workflows"
    assert any("Identity-md/worker#6" in ref for ref in source["references"])
    for item in CATALOG["topics"]:
        assert len(item["stats"]) == 6
        for stat in item["stats"]:
            assert all(isinstance(stat[key], str) and stat[key] for key in ("title", "value", "caption"))
            assert len(stat["caption"]) <= 16
            assert len(stat["value"]) <= 16
        for node in item["nodes"]:
            assert "2026-10-18" in node["example"]
            assert "source" in node["example"].lower()


@pytest.mark.parametrize("item", CATALOG["topics"], ids=lambda item: item["id"])
def test_every_node_has_context_and_a_selectable_bounded_diagram(item):
    assert item["short_title"] and item["summary"]
    nodes = item["nodes"]
    assert len({node["id"] for node in nodes}) == len(nodes)
    labels = {node["id"]: node["label"] for node in nodes}
    referenced = set(re.findall(r"\{([a-z_]+)\}", "\n".join(item["diagram"])))
    assert referenced == set(labels)
    assert len(item["diagram"]) <= 20
    for line in item["diagram"]:
        assert len(line.format(**labels)) <= 108
    for node in nodes:
        assert node["kind"] in {"step", "plane", "merge", "failure", "state"}
        assert len(node["explanation"]) >= 45
        assert node["limits"] and all(node["limits"])
        assert node["source_excerpt"] in item["source_excerpt"]
        assert node["label"].startswith("[") and node["label"].endswith("]")
        if node["kind"] == "plane":
            assert node["label"].startswith("[- ") and node["label"].endswith(" -]")


def test_contract_launch_contains_all_parallel_audits_and_atomic_deployment():
    item = topic("contracts")
    assert {node["id"] for node in item["nodes"]} >= {
        "import_audit", "adapt", "tests", "manifest", "audit_math", "audit_permissions",
        "audit_economics", "audit_flow", "judge", "deploy", "live",
    }
    assert "#2147" in str(item)
    assert "07:48" in str(item) and "08:26" in str(item)
    assert "all or nothing" in str(item)
    assert "blocking finding" in str(item)


def test_known_failure_and_recommendations_are_not_claimed_as_successes():
    site = topic("site")
    assert "README.md" in str(site) and "DESIGN.md" in str(site)
    assert "clone_failed" in str(site) and "53f5fb2b" in str(site)
    recovery = next(node for node in site["nodes"] if node["id"] == "recovery")
    assert "recommendation" in recovery["explanation"].lower()
    assert "not verified" in recovery["example"].lower()
    growth = topic("growth")
    assert "open question" in str(growth)
    assert "cannot be resumed" in str(growth)
    assert "08" in topic("purchase")["summary"]
    assert "docs dependsOn build" in "\n".join(topic("shapes")["diagram"])
    assert "one is unspecified" in topic("company")["summary"]
    assert "accessibility label" in topic("intake")["summary"]


def test_edge_cases_and_limits_survive_curation():
    assert all(text in str(topic("oracle")) for text in ("2 of 3", "reason 5", "reason 8", "701", "11 / 7", "2,112"))
    assert all(text in str(topic("company")) for text in ("70 completed", "29 blocked", "24 before deployment", "parentJobId", "8,000"))
    assert all(text in str(topic("schedules")) for text in ("PT11M", "P1D", "missedSlots", "nothing spent", "never queue"))
    assert all(text in str(topic("single_skill")) for text in ("100/200 MB", "references", "paths", "three attempts"))


@pytest.mark.asyncio
async def test_manager_reuses_local_snapshot_without_io_and_returns_deep_copies(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The documentation manager must not read a file or open a socket")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    manager = WorkflowGuideManager()
    first = manager.get_snapshot()
    assert tuple(first) == WORKFLOW_GUIDE_KEYS
    assert first["workflow_guide"] == CATALOG
    first["workflow_guide"]["source"]["references"].clear()
    first["workflow_guide"]["topics"][0]["nodes"][0]["limits"].clear()
    first["workflow_guide"]["topics"][0]["nodes"][0]["guidance"].clear()
    first["workflow_guide"]["topics"][0]["nodes"][0]["guidance_notes"].clear()
    second = await manager.fetch_and_compute()
    assert second["workflow_guide"] == CATALOG
    second["workflow_guide"]["topics"].clear()
    assert manager.get_snapshot()["workflow_guide"] == CATALOG
    assert "/Library/" not in inspect.getsource(inspect.getmodule(WorkflowGuideManager))


def test_manager_retains_its_own_snapshot_if_catalogue_reference_changes(monkeypatch):
    import maxpane_dashboard.data.workflow_guide_manager as module

    manager = WorkflowGuideManager()
    monkeypatch.setattr(module, "CATALOG", {"topics": []})
    assert manager.get_snapshot()["workflow_guide"] == CATALOG


@pytest.mark.guard
def test_packaged_data_modules_import_only_their_contract_and_copy():
    modules = (
        "workflow_guide_models", "workflow_guide_catalog", "workflow_guide_manager", "workflow_guide_profiles",
    )
    allowed = {
        "typing", "copy", "maxpane_dashboard.data.workflow_guide_models",
        "maxpane_dashboard.data.workflow_guide_catalog",
        "maxpane_dashboard.data.workflow_guide_profiles",
    }
    root = Path(__file__).parents[2] / "maxpane_dashboard/data"
    for module in modules:
        source = (root / f"{module}.py").read_text()
        assert "/Library/" not in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert {name.name for name in node.names} <= allowed
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed
