"""Source-backed capacity guidance, never a live quote or a word quota."""

from html.parser import HTMLParser
from pathlib import Path
from copy import deepcopy
import builtins
import socket

import pytest

from maxpane_dashboard.data.workflow_guide_catalog import CATALOG
from maxpane_dashboard.data.workflow_guide_profiles import add_guidance


def selected(topic_id, node_id):
    topic = next(topic for topic in CATALOG["topics"] if topic["id"] == topic_id)
    return next(node for node in topic["nodes"] if node["id"] == node_id)


def cards(topic_id, node_id):
    return {card["title"]: card for card in selected(topic_id, node_id)["guidance"]}


def notes(topic_id, node_id):
    return " ".join(selected(topic_id, node_id)["guidance_notes"])


def test_every_source_node_has_six_compact_cards_and_dated_guidance():
    nodes = [node for topic in CATALOG["topics"] for node in topic["nodes"]]
    assert len(nodes) == 79
    for node in nodes:
        assert [card["title"] for card in node["guidance"]] == [
            "STEP INPUT", "RENDERED", "BODY", "MORE ROOM", "INTEGRATED", "COST",
        ]
        for card in node["guidance"]:
            assert set(card) == {"title", "heading", "value", "rows", "caption", "footer"}
            assert bool(card["value"]) != bool(card["rows"])
            assert len(card["rows"]) <= 3
            assert all(len(line) <= 15 for line in card["rows"])
            assert len(card["heading"]) <= 15 and len(card["caption"]) <= 15
            assert len(card["footer"]) <= 16
        text = " ".join(node["guidance_notes"])
        assert "2026-10-18" in text
        assert "swarm-workflows.html" in text and "swarm-work-options.html" in text
        assert "not a live quote" in text


@pytest.mark.parametrize("topic_id,node_id", [
    ("shapes", "chain_docs"), ("shapes", "integrate"), ("site", "build"),
    ("contracts", "adapt"), ("growth", "feature"),
])
def test_authored_step_words_are_estimates_of_two_distinct_character_limits(topic_id, node_id):
    result = cards(topic_id, node_id)
    assert result["STEP INPUT"]["value"] == "≈500"
    assert result["STEP INPUT"]["caption"] == "3,000 chars"
    assert result["RENDERED"]["value"] == "≈1,333"
    assert result["RENDERED"]["caption"] == "8,000 chars"
    assert result["BODY"]["value"] == "16"
    assert result["BODY"]["heading"] == "KiB / REQUEST"
    text = notes(topic_id, node_id)
    assert "6 characters per word including spaces" in text
    assert "not a word quota or output limit" in text
    assert "objective + this step" in text
    assert "16,384 bytes" in text and "not converted to words" in text


def test_single_skill_objective_is_not_given_the_authored_step_limit():
    result = cards("single_skill", "working")
    assert result["STEP INPUT"]["heading"] == "OBJECTIVE WORDS"
    assert result["STEP INPUT"]["value"] == "≈1,333"
    assert result["STEP INPUT"]["caption"] == "8,000 chars"
    assert "no separate authored-step text" in notes("single_skill", "working")
    assert result["MORE ROOM"]["heading"] == "FRESH BUDGET"
    assert "not a larger per-job allowance" in notes("single_skill", "working")


@pytest.mark.parametrize("topic_id,node_id", [
    ("contracts", "tests"), ("contracts", "judge"), ("shapes", "critic"),
    ("site", "critic"), ("oracle", "panel"), ("single_skill", "blocked"),
])
def test_managed_or_failure_nodes_never_claim_an_editable_step_budget(topic_id, node_id):
    result = cards(topic_id, node_id)
    assert result["STEP INPUT"]["value"] == "N/A"
    assert result["RENDERED"]["value"] == "N/A"
    assert "no editable instruction budget" in notes(topic_id, node_id)


def test_company_limit_is_shared_and_never_the_request_field_limit():
    for node in next(topic for topic in CATALOG["topics"] if topic["id"] == "company")["nodes"]:
        result = cards("company", node["id"])
        assert result["STEP INPUT"]["value"] == "N/A"
        assert result["RENDERED"]["value"] == "≈1,333"
        assert result["RENDERED"]["heading"] == "SHARED WORDS"
        assert "request + context + draft objective" in notes("company", node["id"])
        assert "not 16,000" in notes("company", node["id"])


def test_more_room_and_integrated_docs_options_keep_scope_and_cost_constraints():
    text = notes("site", "docs")
    assert "single-skill job.continue" in text and "8,000" in text
    assert "0.5 IMD" in text and "same payer" in text and "newest parentJobId" in text
    assert "build objective" in text and "dependsOn build" in text
    assert "not extra text capacity" in text
    assert "not equivalent" in notes("contracts", "adapt")
    assert "does not deploy" in notes("contracts", "adapt")
    assert "not an existing project" in notes("site", "build")
    assert "not separately charged" in notes("contracts", "tests")


def test_costs_are_per_action_not_per_node_and_schedule_total_is_unknown():
    assert cards("purchase", "check")["COST"]["value"] == "0"
    assert cards("purchase", "quote")["COST"]["value"] == "0.5"
    assert cards("contracts", "tests")["COST"]["caption"] == "per launch"
    assert cards("oracle", "panel")["COST"]["caption"] == "per request"
    assert cards("schedules", "create")["COST"]["rows"] == ["0.5 IMD", "+ prepaid runs"]
    assert "total unknown" in notes("schedules", "create")
    assert cards("schedules", "topup")["COST"]["value"] == "—"
    assert cards("schedules", "failed")["COST"]["value"] == "0"
    assert "not per node" in notes("contracts", "tests")
    assert "result not guaranteed" in notes("site", "build")
    assert cards("growth", "launch")["COST"]["caption"] == "per launch"
    assert cards("growth", "fresh")["COST"]["caption"] == "per job"


def test_guidance_construction_is_pure_and_nodes_do_not_share_mutable_cards(monkeypatch):
    topic = deepcopy(next(topic for topic in CATALOG["topics"] if topic["id"] == "site"))

    def forbidden(*args, **kwargs):
        raise AssertionError("Guidance cannot read files or contact a service")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    add_guidance("site", topic["nodes"])
    assert topic["nodes"] == next(item for item in CATALOG["topics"] if item["id"] == "site")["nodes"]
    topic["nodes"][0]["guidance"][0]["value"] = "changed"
    topic["nodes"][0]["guidance_notes"].clear()
    assert topic["nodes"][1]["guidance"][0]["value"] == "≈500"
    assert topic["nodes"][1]["guidance_notes"]


def test_new_or_missing_nodes_require_explicit_guidance_membership():
    with pytest.raises(ValueError, match="guidance membership"):
        add_guidance("single_skill", [{"id": "working"}])


def test_committed_companion_source_supports_capacity_and_cost_facts():
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    parser.feed((Path(__file__).parents[1] / "fixtures/workflow_guide/work-options.html").read_text())
    source = " ".join(" ".join(parser.parts).split())
    for fact in (
        "State as of 2026-10-18", "every paid action 0.5 IMD", "request + context + draft objective ≤ 8,000",
        "step text itself (3,000 characters", "whole request body (16 KiB", "0.5 IMD + runs",
        "Docs-only continuation", "single skill write-readme-and-docs", "the 8,000 objective",
        "the build step writes the README itself", "refuses parentJobId",
    ):
        assert fact in source
