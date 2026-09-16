"""THE FIELD -- who is working on what, and what is stuck (Task 7)."""

from maxpane_dashboard.widgets.surf.swarm_field import (
    COMPACT_WIDTH, EMPTY_LINE, FULL_WIDTH, SurfSwarmField, UNAVAILABLE_LINE,
)
from tests.widgets.surf_compositing import composite_lines

ROWS = [
    {"job_id": "4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6", "template": "shape:chain",
     "objective": "Build an ERC-4626 vault", "node_key": "adversarial_review",
     "role": "review", "node_state": "ready", "agent_token": None, "agent_id": None,
     "revisions": 0, "dispatch_note": "a review needs a contributor who did not author this work",
     "moved_ts": 1_789_000_000.0, "age_s": 3600.0},
    {"job_id": "9c6543f5-1111-2222-3333-444455556666", "template": "shape:chain",
     "objective": "Build a dapp", "node_key": "build_website", "role": "implement",
     "node_state": "accepted", "agent_token": "2", "agent_id": "10303",
     "revisions": 1, "dispatch_note": None,
     "moved_ts": 1_789_003_600.0, "age_s": 120.0},
]


async def _field(size=(120, 14), **kwargs):
    kwargs.setdefault("swarm_field_rows", ROWS)
    kwargs.setdefault("swarm_network", "SEPOLIA")
    lines = await composite_lines(SurfSwarmField, size, **kwargs)
    return lines, "\n".join(lines)


async def test_a_held_subtask_names_its_agent_and_its_age():
    _lines, text = await _field()
    assert "#2" in text
    assert "build_website" in text
    assert "2m" in text or "120" in text


async def test_an_unheld_subtask_shows_a_dash_not_an_agent():
    _lines, text = await _field()
    field_rows = [ln for ln in text.split("\n") if "adversarial_review" in ln]
    assert field_rows and "#" not in field_rows[0].split("adversarial_review")[0]


async def test_the_dispatch_note_explains_the_stall_at_full_width():
    _lines, text = await _field(size=(FULL_WIDTH + 4, 14))
    assert "did not author" in text


async def test_the_note_is_dropped_with_a_marker_when_narrow():
    _lines, text = await _field(size=(COMPACT_WIDTH + 2, 14))
    assert "did not author" not in text
    assert "‹" in text


async def test_an_empty_field_is_not_an_unread_field():
    _lines, empty = await _field(swarm_field_rows=[])
    assert EMPTY_LINE in empty
    _lines, unread = await _field(swarm_field_rows=None)
    assert UNAVAILABLE_LINE in unread


async def test_the_title_carries_the_as_of_marker():
    _lines, text = await _field(swarm_as_of_hhmm="13:18")
    assert "13:18" in text


async def test_a_hostile_objective_renders_as_text():
    rows = [dict(ROWS[0], objective="[/x] crash me", dispatch_note="[bold]no[/]")]
    _lines, text = await _field(swarm_field_rows=rows)
    assert "crash me" in text or "[/x]" in text


# ---------------------------------------------------------------------------
# The standing requirement from the previous task's review (task-6): a
# hostile row's composited region must carry no literal `[` or `]` at all --
# not merely "the payload text is still findable as a substring", which
# ``test_a_hostile_objective_renders_as_text`` above already checks and which
# a regression that renders `\[red]…\[/]` verbatim would still pass. Every
# text field a row carries gets the hostile treatment: job/template feed only
# the grouping key and are not painted, but node_key/role/node_state/
# objective/dispatch_note all reach the screen.
# ---------------------------------------------------------------------------

async def test_a_hostile_row_paints_no_literal_brackets():
    rows = [dict(
        ROWS[0],
        objective="[a] the objective [b]",
        node_key="[c]build_website",
        role="[d]review",
        node_state="[e]ready",
        dispatch_note="[f] a note [g]",
    )]
    _lines, text = await _field(swarm_field_rows=rows, size=(FULL_WIDTH + 20, 20))
    assert "[" not in text
    assert "]" not in text
