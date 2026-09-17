"""THE FIELD -- who is working on what, and what is stuck (Task 7)."""

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets.surf.swarm_field import (
    COMPACT_WIDTH, EMPTY_LINE, FULL_WIDTH, MINIMAL_WIDTH, SurfSwarmField,
    UNAVAILABLE_LINE,
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
    # Fix round 1: a marker is now load-bearing for *any* content to render
    # (see swarm_field.py's own docstring) -- every test in this file except
    # the empty/unavailable one is about row rendering, not about the
    # marker itself, so it needs one present by default the way
    # ``swarm_network`` already gets one. The empty/unavailable test passes
    # its own value (or ``None``) explicitly and is unaffected.
    kwargs.setdefault("swarm_as_of_hhmm", "12:00")
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
    """``[]`` is the frozen shape for both states (fold's own contract, see
    the module docstring) -- so the marker, not the list, is the signal.
    A real read that found nothing in flight carries an ``as of`` marker; a
    slot that has never been written carries none.
    """
    _lines, empty = await _field(swarm_field_rows=[], swarm_as_of_hhmm="13:18")
    assert EMPTY_LINE in empty
    _lines, unread = await _field(swarm_field_rows=[], swarm_as_of_hhmm=None)
    assert UNAVAILABLE_LINE in unread


async def test_a_marker_absent_with_rows_still_present_shows_no_rows():
    """Task 11: the real producer can never hand this widget a marker-absent,
    rows-non-empty payload (``data/surf_swarm.field_rows`` always returns
    ``[]`` while ``SLOT_SWARM`` is cold, per this module's own *"swarm_field_
    rows and the read/empty split"* docstring section) -- but a hand-edited
    or partially written cache file is third-party input too, and
    ``_render_view``'s own ``rows_input is None`` half of the gate is the
    part that exists purely for that scenario (the docstring says so in as
    many words: "the widget stays honest if it is ever handed that sentinel
    directly").

    Every other test in this file either sets a marker with real rows, or
    sets no marker with an empty list (the state the real producer *does*
    emit for "never read"). None of them drives a marker-absent payload
    whose rows are a real, non-empty list -- the shape a corrupted cache
    file could produce, and the one this test closes. Mutate the gate to
    drop the marker check (leaving only ``rows_input is None``) and this
    test reddens: the row content would leak as a confident "nothing is
    wrong" render instead of the unavailable state.
    """
    _lines, text = await _field(swarm_field_rows=ROWS, swarm_as_of_hhmm=None)
    assert "build_website" not in text
    assert "adversarial_review" not in text
    assert UNAVAILABLE_LINE in text


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


# ---------------------------------------------------------------------------
# Fix round 2 (review findings 1-6, 2026-09-16)
# ---------------------------------------------------------------------------


async def test_an_over_long_agent_token_does_not_break_column_alignment():
    """``#123456`` (7 cells) against ``_AGENT_COLS``'s 6 must be clipped, not
    left to overflow -- an unclipped cell pushes every column after it out of
    alignment with the row above it. Reproduced live before fix round 2,
    where ``agent``/``age``/``revisions`` were padded but never clipped.
    """
    rows = [
        dict(ROWS[1], job_id="job-long", node_key="alpha_task", agent_token="123456"),
        dict(ROWS[1], job_id="job-short", node_key="beta_task", agent_token="2"),
    ]
    _lines, text = await _field(swarm_field_rows=rows)
    long_line = next(ln for ln in text.split("\n") if "alpha_task" in ln)
    short_line = next(ln for ln in text.split("\n") if "beta_task" in ln)
    assert long_line.index("alpha_task") == short_line.index("beta_task")


async def test_the_stale_marker_prints_only_when_stale():
    _lines, stale_text = await _field(swarm_as_of_hhmm="13:18", swarm_stale=True)
    assert "stale" in stale_text
    _lines, fresh_text = await _field(swarm_as_of_hhmm="13:18", swarm_stale=False)
    assert "stale" not in fresh_text


async def test_the_chain_word_never_appears():
    """Design §5: the chain word belongs only to panels that show chain data
    (JUST SHIPPED, any score quoting a transaction) -- THE FIELD shows
    neither, so ``swarm_network`` must never reach the screen.
    """
    _lines, sepolia_text = await _field(swarm_network="SEPOLIA")
    assert "SEPOLIA" not in sepolia_text
    _lines, mainnet_text = await _field(swarm_network="MAINNET")
    assert "MAINNET" not in mainnet_text


async def test_groups_order_by_their_own_newest_subtask_and_subtasks_newest_first_within_a_group():
    """Two jobs, two subtasks each, fed in the producer's own newest-first
    order (ages 10s, 50s, 200s, 250s for a1, b1, a2, b2).

    Pins both halves of the ordering: within a group, newest first
    (``a1`` before ``a2``, ``b1`` before ``b2``); groups ordered by their own
    newest subtask (job-a's newest, 10s, outranks job-b's newest, 50s, so all
    of job-a renders before job-b starts) -- which means job-a's *oldest*
    subtask (``a2``, 200s) still renders ahead of job-b's newest (``b1``,
    50s), even though ``b1`` is globally more recent. That interleaving is
    the module docstring's own worked example.
    """
    rows = [
        dict(ROWS[1], job_id="job-a", node_key="a1", age_s=10.0, dispatch_note=None),
        dict(ROWS[1], job_id="job-b", node_key="b1", age_s=50.0, dispatch_note=None),
        dict(ROWS[1], job_id="job-a", node_key="a2", age_s=200.0, dispatch_note=None),
        dict(ROWS[1], job_id="job-b", node_key="b2", age_s=250.0, dispatch_note=None),
    ]
    _lines, text = await _field(swarm_field_rows=rows)
    pos = {key: text.index(key) for key in ("a1", "a2", "b1", "b2")}
    assert pos["a1"] < pos["a2"], "job-a's own subtasks are not newest-first"
    assert pos["b1"] < pos["b2"], "job-b's own subtasks are not newest-first"
    assert pos["a2"] < pos["b1"], (
        "job-a's group (newest subtask 10s) should render whole before "
        "job-b's group (newest subtask 50s) starts"
    )


async def test_the_minimal_tier_drops_role_and_revisions_but_keeps_the_rest():
    _lines, text = await _field(size=(MINIMAL_WIDTH + 5, 14))
    assert "#2" in text
    assert "build_website" in text
    assert "accepted" in text
    assert "implement" not in text
    assert "rev1" not in text
    assert "‹" in text


async def test_an_empty_string_marker_is_treated_as_no_marker():
    """``swarm_as_of_hhmm=""`` is not a clock -- treating it as one would let
    the body claim a read happened while the title shows no time it
    happened at (:meth:`SurfSwarmField._set_title` has always required a
    non-empty string).
    """
    _lines, text = await _field(swarm_field_rows=[], swarm_as_of_hhmm="")
    assert UNAVAILABLE_LINE in text


async def test_a_blank_row_separates_the_title_from_the_log():
    """The repo-wide sweep (``tests/widgets/test_title_blank_row.py``)
    excludes surf; this is this panel's own copy of that mandatory contract,
    composited under the app stylesheet the way that sweep's own panels are.
    """
    rows = await composite_lines(
        SurfSwarmField, (120, 14), css_path=CSS_PATH, region_only=True,
        swarm_field_rows=ROWS, swarm_as_of_hhmm="12:00", swarm_network="SEPOLIA",
    )
    assert rows[0].strip(), "no title row at all"
    assert not rows[1].strip(), (
        f"content directly under the title, no blank row: {rows[:4]}"
    )
    assert rows[2].strip(), f"nothing under the blank row: {rows[:4]}"
