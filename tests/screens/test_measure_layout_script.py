"""``scripts/measure_layout.py`` reads the SWARM pin the layout sweep certifies.

The script wraps ``_render()`` from ``test_surf_swarm_layout.py``; this checks that its
whole/not-whole reading and its ``whole_from`` agree with the pinned constants, so a script
that drifted from the sweep's checks would redden here, not mislead a measurement.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from maxpane_dashboard.screens.surf import (
    SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS,
    SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "measure_layout.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_layout_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ml = _load()


async def test_the_swarm_column_pin_reads_as_the_first_whole_width() -> None:
    pin, rows = SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS
    measured = await ml.measure("s", "capture", [(pin - 1, rows), (pin, rows), (pin + 1, rows)])
    assert measured[0]["problems"], measured[0]
    assert not measured[1]["problems"] and not measured[2]["problems"], measured
    assert ml.whole_from(measured, 0) == pin


async def test_the_swarm_row_pin_reads_as_the_first_whole_height() -> None:
    pin, rows = SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS
    measured = await ml.measure("s", "capture", [(pin, rows - 1), (pin, rows)])
    assert measured[0]["problems"] == ["‹ taller lit"], measured[0]
    assert ml.whole_from(measured, 1) == rows


#: A composite that ``problems()`` reads as whole: only the keys it reads.
_WHOLE = {"status_whole": True, "marked_besides_exceptions": set(), "clipped": [],
          "hidden": {"SurfSwarmLaunches": 0}, "overflow": [], "taller": False}


@pytest.mark.parametrize("field,broken,word", [
    ("status_whole", False, "status bar cropped"),
    ("marked_besides_exceptions", {"SurfSwarmWorkflows"}, "marked"),
    ("clipped", [("SurfSwarmSites", "a line")], "clipped"),
    ("hidden", {"SurfSwarmLaunches": 3}, "hidden columns"),
    ("overflow", [("SurfSwarmThroughput", 2)], "overflow"),
    ("taller", True, "‹ taller lit"),
])
def test_problems_names_each_way_a_composite_breaks(field, broken, word) -> None:
    """Each of ``problems()``'s six checks, alone (follow-up #83: four were unpinned)."""
    assert ml.problems(_WHOLE) == []
    found = ml.problems(dict(_WHOLE, **{field: broken}))
    assert len(found) == 1 and found[0].startswith(word), found


async def test_board_problems_judge_with_the_sweeps_board_check() -> None:
    """BOARD's wholeness is ``_assert_board_whole``, not ``problems()`` (follow-up #82):
    LEADERBOARD's marker is excused on ``worst`` only, and its tier, its twelve columns and
    its clipped fields count. The worst payload at the BOARD pin is whole, as the pin test
    says; one real composite, then the variants are built from it."""
    size = (SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS)
    [row] = await ml.measure("b", "board-worst", [size])
    assert row["problems"] == [], row["problems"]

    r = await ml.layout._render(ml.layout._board_payload("worst"), size, "b")
    lb = "SurfSwarmLeaderboard"
    marked = dict(r, marked_besides_exceptions={lb})
    assert ml.board_problems(marked, "worst") == []
    assert ml.board_problems(marked, "capture")
    assert ml.board_problems(dict(r, tiers=dict(r["tiers"], **{lb: "compact"})), "worst")
    assert ml.board_problems(dict(r, columns=dict(r["columns"], **{lb: r["columns"][lb][:-1]})), "worst")
    clipped = dict(r, clipped_fields=dict(r["clipped_fields"], **{lb: {"runtime"}}))
    assert ml.board_problems(clipped, "worst") == []
    assert ml.board_problems(clipped, "capture")
    assert ml.board_problems(dict(r, taller=True), "worst") == ["‹ taller lit"]


def test_sizes_parse_as_inclusive_ranges() -> None:
    assert ml.parse_size("136:138x35") == ([136, 137, 138], [35])
    assert ml.parse_size("140X30:31") == ([140], [30, 31])
    for bad in ("140", "140x", "139:137x35"):
        with pytest.raises(ValueError):
            ml.parse_size(bad)


def test_whole_from_stops_at_the_first_broken_size_from_the_top() -> None:
    rows = [{"size": (w, 35), "problems": p} for w, p in
            ((136, []), (137, ["x"]), (138, []), (139, []))]
    assert ml.whole_from(rows, 0) == 138
    assert ml.whole_from([{"size": (140, 35), "problems": ["x"]}], 0) is None


def test_every_named_payload_builds() -> None:
    """A board kind ``_board_payload`` no longer knows would build the capture silently, so
    each ``board-`` payload must differ from the plain capture or name it."""
    built = {name: build() for name, build in ml.payloads().items()}
    assert all(isinstance(p, dict) and p for p in built.values())
    plain = ml.layout._board_payload("capture")
    for kind in ml.BOARD_KINDS:
        assert kind == "capture" or built[f"board-{kind}"] != plain, kind
