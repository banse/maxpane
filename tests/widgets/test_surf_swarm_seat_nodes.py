"""BY NODE renders the lifetime node fold and fitted teammates."""
import inspect
import pytest
from textual.app import App
from textual.widgets import DataTable
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_node_rows, seat_teammates
from maxpane_dashboard.widgets.surf.swarm_seat_nodes import SurfSwarmSeatNodes
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.surf_compositing import composite_lines

SEAT = swarm_seat_capture("seat_420")
ROWS = seat_node_rows(SEAT)

async def _nodes(size=(92, 15), **kwargs):
    data = dict(swarm_seat_node_rows=ROWS, swarm_seat_teammates=seat_teammates(SEAT),
                swarm_seat_state="ok", swarm_seat_as_of_hhmm="04:06")
    data.update(kwargs)
    return "\n".join(await composite_lines(SurfSwarmSeatNodes, size, **data))

def test_signature():
    params = inspect.signature(SurfSwarmSeatNodes.update_data).parameters
    assert tuple(k for k,p in params.items() if k != "self" and p.kind != p.VAR_KEYWORD) == SWARM_WIDGET_SIGNATURES["SurfSwarmSeatNodes"]

async def test_nodes_and_reviewed_denominator():
    text = await _nodes()
    assert "BY NODE" in text and "TEAMMATES" in text
    for row in ROWS:
        assert row["node_key"] in text
        if row["reviewed"]:
            assert f"{row['won']/row['reviewed']*100:.1f}%" in text
    assert "⧉" not in text

@pytest.mark.parametrize("value,word", [([], "none yet"), (None, "unavailable")])
async def test_teammates_empty_differs_from_unavailable(value, word):
    text = await _nodes(swarm_seat_teammates=value)
    assert f"TEAMMATES  {word}" in text

async def test_teammates_marker_counts_every_omitted_member():
    teammates = [{"token_id": i, "agent_id": None, "shared_jobs": 999-i} for i in range(999)]
    text = await _nodes(size=(74,15), swarm_seat_teammates=teammates)
    line = next(line for line in text.splitlines() if "TEAMMATES" in line)
    shown = line.count("#")
    assert shown > 0 and f"+{999-shown}" in line and "…" not in line

async def test_markup_node_uses_established_strip_then_escape():
    # Handover literal-tag wording conflicts with widgets.md's sanitizer contract.
    rows = [dict(ROWS[0], node_key="[/x]visible", roles=["[$success]review"])]
    text = await _nodes(swarm_seat_node_rows=rows)
    assert "visible" in text and "review" in text and "[/x]" not in text
    assert "unavailable" not in text

@pytest.mark.parametrize("state,expected", [
    ("pending", ["Loading..."]),
    ("unknown_seat", ["never paired"]),
    (None, ["unavailable", "TEAMMATES unavailable"]),
    ("ok", ["unavailable", "TEAMMATES unavailable"]),
])
async def test_state_footer_is_separate_from_teammates(state, expected):
    text = await _nodes(swarm_seat_state=state, swarm_seat_node_rows=None,
                        swarm_seat_teammates=[] if state == "unknown_seat" else None)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    assert lines == ["BY NODE · as of 04:06", "node roles reviewed won win chain", *expected]

async def test_every_node_is_retained_in_the_scrollable_table():
    class Harness(App):
        def compose(self):
            yield SurfSwarmSeatNodes()
    async with Harness().run_test(size=(92,15)) as pilot:
        panel = pilot.app.query_one(SurfSwarmSeatNodes)
        panel.update_data(swarm_seat_node_rows=[dict(ROWS[0], node_key=f"node{i}") for i in range(30)], swarm_seat_teammates=[], swarm_seat_state="ok")
        await pilot.pause()
        assert panel.query_one(DataTable).row_count == 30


async def test_oversized_win_percentage_cannot_clip_silently():
    text = await _nodes(swarm_seat_node_rows=[dict(ROWS[0], reviewed=1, won=12)])
    assert "1200.0%" in text or ("‹ widen" in text and "1200." in text)
