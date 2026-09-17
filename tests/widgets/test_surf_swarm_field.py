"""THE FIELD -- who is working on what, and what is stuck (Task 7)."""

import re

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets.surf.swarm_field import (
    COMPACT_WIDTH, EMPTY_LINE, FULL_WIDTH, MAX_OBJECTIVE_LINES, MINIMAL_WIDTH,
    SurfSwarmField, UNAVAILABLE_LINE,
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


async def test_the_stale_word_never_prints_here_even_when_told_to():
    """F-A: this panel reads only the live tier, and ``swarm_stale`` measures
    the *scores* tier drifting from it -- a claim about a clock THE FIELD
    does not show. An earlier version of this test pinned the opposite
    (accepting ``swarm_stale=True`` and asserting the word appeared), which
    is exactly the false-degradation bug the review construction caught: a
    fresh live marker labelled stale on the evidence of an unrelated, slower
    sweep falling behind. ``swarm_stale`` is fed here anyway (a screen that
    still passed it would be exactly the fix-round-1-reversed mistake) to
    prove the widget itself refuses to render it, not merely that nobody
    currently sends it.
    """
    _lines, stale_text = await _field(swarm_as_of_hhmm="13:18", swarm_stale=True)
    assert "stale" not in stale_text
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


# ---------------------------------------------------------------------------
# 2026-09-17 field-wrap fix: the objective context line wraps rather than
# clips. The owner's own live screenshot showed a two-column-indented
# objective line cut mid-word with a silent ``…`` and no marker; the four
# tests below are the worked proof of the replacement contract -- full text
# on real data, a bounded cap on hostile data, a marker that tells the truth
# about which of the two happened, and an address that survives the wrap
# whole.
# ---------------------------------------------------------------------------

#: This capture's own median/max objective (``docs/imd_swarm_api.md``,
#: ``/jobs``: "median 156 and max 159 characters ... containing newlines and
#: punctuation") -- real user-written text, not a synthetic string, so a
#: test built on it is a test built on the same data the panel's own
#: :data:`MAX_OBJECTIVE_LINES` was sized against.
_MAX_REAL_OBJECTIVE = (
    "Build a polished, mobile-friendly DeFi Yield Lab. Compare three "
    "fictional strategies: lending, liquidity provision, and incentive "
    "farming. Explain where yield…"
)


async def test_the_full_real_objective_reaches_the_screen_with_no_marker():
    """The exact defect from the screenshot: at a width comfortable enough
    for both the row tier and the wrap (``FULL_WIDTH + 4``, this file's own
    full-tier probe), the *whole* objective -- including its own tail,
    "Explain where yield…" -- must reach the panel, wrapped rather than cut,
    and the ``‹ widen`` marker must stay dark: neither the tier (full) nor
    the objective (comfortably inside :data:`MAX_OBJECTIVE_LINES`) shed
    anything here.
    """
    rows = [dict(ROWS[1], objective=_MAX_REAL_OBJECTIVE, dispatch_note=None)]
    _lines, text = await _field(swarm_field_rows=rows, size=(FULL_WIDTH + 4, 14))
    assert "Build a polished" in text
    assert "Explain where yield" in text, "the objective's own tail was lost"
    assert "‹" not in text, "neither the tier nor the objective sheds here"


async def test_a_hostile_objective_is_capped_not_wrapped_without_bound():
    """A single job's objective cannot be allowed to grow without limit --
    THE FIELD is a shared ``RichLog`` and every line a flood of text spends
    is a line the other jobs' subtask rows do not get (see
    :data:`MAX_OBJECTIVE_LINES`'s own ``#:`` block). 300 repeats of one word
    plus a tail marker only the *end* of the text carries: if the wrap were
    unbounded the tail would reach the screen; capped, it must not, and the
    number of repeats that do reach the screen must stay small.
    """
    # A tall viewport (40 rows, comfortably more than the ~6 lines the cap
    # allows) on purpose: at the default 14 rows an unbounded wrap would
    # also fail to show the tail, simply because the screen is shorter than
    # the flood -- that would prove nothing about the cap itself. At 40 rows
    # a genuinely unbounded wrap (this text needs ~22 lines at this width)
    # would still fit and show its tail; only the cap keeps it from doing so.
    hostile = ("PADWORD " * 300) + "ZZZ_TAIL_END"
    rows = [dict(ROWS[1], objective=hostile, dispatch_note=None)]
    _lines, text = await _field(swarm_field_rows=rows, size=(FULL_WIDTH + 4, 40))
    assert "ZZZ_TAIL_END" not in text, "an unbounded wrap would have reached the tail"
    assert text.count("PADWORD") < 100, (
        "the flood was not bounded to a handful of lines"
    )


async def test_the_widen_marker_lights_from_the_objective_alone_at_full_tier():
    """Judgement call 2's own proof: at a width where the row *tier* is
    ``full`` (the note column is present, not shed -- proven here by the
    dispatch note's own clause still reaching the screen, the same
    assertion :func:`test_the_dispatch_note_explains_the_stall_at_full_width`
    makes), a hostile objective must still light ``‹ widen`` on its own.
    Before this fix the marker was wired to the tier ladder alone, so this
    exact combination -- tier whole, objective shed -- rendered a dark
    marker over content that was silently missing its tail.
    """
    hostile = ("PADWORD " * 300) + "ZZZ_TAIL_END"
    rows = [dict(
        ROWS[0], objective=hostile,
        dispatch_note="a review needs a contributor who did not author this work",
    )]
    _lines, text = await _field(swarm_field_rows=rows, size=(FULL_WIDTH + 4, 14))
    assert "did not author" in text, "the tier itself sheds the note -- not what this proves"
    assert "‹" in text, "the objective shed text but the marker stayed dark"


async def test_continuation_lines_are_capped_at_max_objective_lines():
    """White-box proof that the cap is a line *count*, not a width-dependent
    accident: at a width narrow enough that the real, non-hostile maximum
    objective needs more than one line, the number of composited lines this
    one job's header ever occupies is never more than
    :data:`MAX_OBJECTIVE_LINES`, counted directly off the dim-indented block
    between the blank title spacer and the subtask row.
    """
    rows = [dict(ROWS[1], objective=_MAX_REAL_OBJECTIVE, dispatch_note=None)]
    lines, _text = await _field(swarm_field_rows=rows, size=(70, 14))
    subtask_idx = next(i for i, ln in enumerate(lines) if "build_website" in ln)
    # ``lines[2:]``: index 0 is the title, 1 is the mandatory blank spacer
    # (see the previous test); only what the log itself wrote is the header.
    header_lines = [ln for ln in lines[2:subtask_idx] if ln.strip()]
    assert 1 < len(header_lines) <= MAX_OBJECTIVE_LINES, header_lines


async def test_continuation_lines_align_under_the_first_lines_text():
    """Every wrapped line of one objective carries the same indent, so the
    block reads as one continued sentence rather than a disconnected second
    row -- exactly the requirement behind the two-column dim indent.
    """
    rows = [dict(ROWS[1], objective=_MAX_REAL_OBJECTIVE, dispatch_note=None)]
    lines, _text = await _field(swarm_field_rows=rows, size=(70, 14))
    subtask_idx = next(i for i, ln in enumerate(lines) if "build_website" in ln)
    header_lines = [ln for ln in lines[2:subtask_idx] if ln.strip()]
    assert len(header_lines) > 1, "need at least two lines to prove alignment"
    indents = {len(ln) - len(ln.lstrip(" ")) for ln in header_lines}
    assert len(indents) == 1, f"continuation lines do not share one indent: {header_lines}"


async def test_an_address_in_the_objective_is_never_split_across_a_wrap():
    """An embedded ``0x…`` address is one word (hex has no whitespace), so
    the wrap must never break it in half the way a naive character-column
    clip would. At a width comfortable for the whole address plus its icon,
    the address renders whole, on one line, with its copy icon -- never
    straddling two composited rows.
    """
    addr = "0x" + "ab" * 20
    objective = (
        f"Please verify the vault at {addr} before the deploy continues today."
    )
    rows = [dict(ROWS[1], objective=objective, dispatch_note=None)]
    lines, text = await _field(swarm_field_rows=rows, size=(90, 14))
    assert any(addr in ln for ln in lines), "the address did not survive whole on one line"
    assert "⧉" in text, "the address lost its copy icon"


async def test_an_address_too_wide_for_any_line_degrades_without_a_fake_whole():
    """The documented, deliberate fallback for the case the brief calls out
    as hard to guarantee: at a width narrower than the address itself plus
    its icon, the address cannot be kept whole *and* fit the panel. It must
    not render as a bare, unclipped 42-character string with no icon (which
    would look like a valid, copyable address that silently lost its click
    action) -- so the full address must simply not appear at all, and the
    marker must say the panel actually shed something.

    Deliberately a **short** objective (three words) so the line count
    never approaches :data:`MAX_OBJECTIVE_LINES` -- the marker here can only
    be lit by the single over-width word's own clip, isolating that half of
    :func:`_wrap_objective` from the line-count cap the other tests already
    cover.
    """
    addr = "0x" + "ab" * 20
    rows = [dict(ROWS[1], objective=f"at {addr} ok", dispatch_note=None)]
    lines, text = await _field(swarm_field_rows=rows, size=(40, 14))
    assert not any(addr in ln for ln in lines), (
        "a half-protected whole address reached the screen"
    )
    assert "⧉" not in text, "an icon appeared beside an address that was not kept whole"
    assert "‹" in text, "the over-width address was shed silently"
    # The decisive check: any partial hex run left on screen must be
    # immediately followed by the clip's own ``…`` -- a bare, un-ellipsised
    # prefix of a real address is indistinguishable from a genuine, shorter
    # one and is exactly the "looks whole" failure this test exists to
    # catch. ``RichLog(wrap=False)``'s own silent narrowing (no ellipsis, no
    # marker) would otherwise produce exactly this shape if our own clip is
    # ever skipped.
    hex_run = re.compile(r"0x[0-9a-fA-F]{6,}")
    for line in lines:
        for match in hex_run.finditer(line):
            found = match.group(0)
            if found == addr:
                continue
            assert line[match.end():match.end() + 1] == "…", (
                f"a partial address with no ellipsis reached the screen: {line!r}"
            )
