"""Visible graph geometry and literal node text, using the packaged document."""
from copy import deepcopy

import pytest
from rich.cells import cell_len
from rich.console import Console

from maxpane_dashboard.data.workflow_guide_catalog import CATALOG
from maxpane_dashboard.widgets.workflow_guide_diagrams import render_diagram

PALETTE = dict(background="#1c1c1c", accent="#00ff41", error="#ff0040",
               success="#00ff41", warning="#33ff33", foreground="#00dd33")
CONSOLE = Console()


def render(topic, width=140, selected=None):
    return render_diagram(topic, selected, width=width, palette=PALETTE, text_color="#dddddd")


def cell_style(result, x, y):
    line = result.text.split("\n")[y]
    position = 0
    for index, char in enumerate(line.plain):
        if position == x:
            return line.get_style_at_offset(CONSOLE, index)
        position += cell_len(char)
    raise AssertionError((x, y))


@pytest.mark.parametrize("topic", CATALOG["topics"], ids=lambda item: item["id"])
@pytest.mark.parametrize("width", [109, 111, 140])
def test_every_documented_node_has_a_disjoint_clickable_inner_card(topic, width):
    result = render(topic, width)
    assert set(result.boxes) == {node["id"] for node in topic["nodes"]}
    assert result.width <= width
    assert result.height <= 24
    lines = result.text.plain.splitlines()
    assert len(lines) == result.height
    assert {cell_len(line) for line in lines} == {result.width}
    occupied = set()
    for index, node in enumerate(topic["nodes"]):
        x, y, w, h = result.boxes[node["id"]]
        cells = {(cx, cy) for cy in range(y, y + h) for cx in range(x, x + w)}
        assert not cells & occupied
        occupied |= cells
        assert h == 4
        for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + 2, y + 1)):
            style = cell_style(result, cx, cy)
            assert style.meta["@click"] == f"choose_node({index})"
            assert style.bgcolor.name == PALETTE["background"]


def test_contract_audits_are_parallel_with_split_and_join_ports():
    topic = next(t for t in CATALOG["topics"] if t["id"] == "contracts")
    result = render(topic, selected="adapt")
    lines = result.text.plain.splitlines()
    assert "6 PARALLEL STAGES" in result.text.plain
    audit_ids = ("tests", "manifest", "audit_math", "audit_permissions", "audit_economics", "audit_flow")
    assert len({result.boxes[key][0] for key in audit_ids}) == 1
    for key in audit_ids:
        x, y, w, _ = result.boxes[key]
        assert lines[y + 2][x - 1] == "▶"
        assert lines[y + 2][x + w] in "─┼┤├"
        assert lines[y][x] == "┌" and lines[y + 3][x] == "└"
    x, y, _, _ = result.boxes["adapt"]
    assert cell_style(result, x, y).color.name == PALETTE["accent"]
    x, y, w, _ = result.boxes["blocked"]
    assert cell_style(result, x + w // 2, y).color.name == PALETTE["error"]


def test_three_shapes_are_distinct_and_proposed_recovery_is_identified():
    shapes = render(next(t for t in CATALOG["topics"] if t["id"] == "shapes"))
    assert all(label in shapes.text.plain for label in ("CHAIN", "FAN_OUT_JOIN", "DAG"))
    site = render(next(t for t in CATALOG["topics"] if t["id"] == "site"))
    assert "PROPOSED" in site.text.plain
    assert "NOT REACHED" in site.text.plain
    growth = render(next(t for t in CATALOG["topics"] if t["id"] == "growth"))
    assert "OBSERVED" in growth.text.plain and "PROPOSED" in growth.text.plain


@pytest.mark.parametrize("width", [109, 111, 140])
@pytest.mark.parametrize("topic_id,node_id,side", [
    ("site", "critic", "t"), ("site", "blocked", "t"),
    ("contracts", "blocked", "t"), ("single_skill", "blocked", "t"),
    ("single_skill", "dispatch", "t"), ("schedules", "topup", "t"),
    ("schedules", "topup", "b"),
])
def test_branch_arrowheads_touch_their_target_without_caption_overwrite(topic_id, node_id, side, width):
    result = render(next(t for t in CATALOG["topics"] if t["id"] == topic_id), width)
    x, y, w, h = result.boxes[node_id]
    row, glyph = (y - 1, "▼") if side == "t" else (y + h, "▲")
    assert result.text.plain.splitlines()[row][x + w // 2] == glyph


def test_hyphenated_skill_names_wrap_at_the_hyphen():
    result = render(next(t for t in CATALOG["topics"] if t["id"] == "site"), width=111)
    x, y, w, _ = result.boxes["check"]
    rows = result.text.plain.splitlines()
    assert "site-content-" in rows[y + 1][x:x + w]
    assert "check" in rows[y + 2][x:x + w]


def test_unrecognized_node_set_has_no_invented_arrows_and_literal_safe_cells():
    topic = deepcopy(CATALOG["topics"][0])
    topic["nodes"] = [dict(id="custom", kind="step", label="[界界 [bold]safe[/bold]\x1b\u202e]")]
    result = render(topic, width=20)
    assert list(result.boxes) == ["custom"]
    assert "▶" not in result.text.plain and "▼" not in result.text.plain
    assert "界界" in result.text.plain and "[bold]" in result.text.plain
    assert "\x1b" not in result.text.plain and "\u202e" not in result.text.plain
    assert all(cell_len(line) == result.width for line in result.text.plain.splitlines())
    x, y, w, _ = result.boxes["custom"]
    assert cell_style(result, x + w - 1, y + 1).meta["@click"] == "choose_node(0)"


def test_narrow_view_keeps_every_box_with_explicit_measured_overflow():
    topic = next(t for t in CATALOG["topics"] if t["id"] == "contracts")
    result = render(topic, width=65)
    assert result.width > 65
    assert len(result.boxes) == 12
    assert "…" not in result.text.plain  # Native labels remain readable in the narrow plan.
