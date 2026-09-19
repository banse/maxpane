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


# ---------------------------------------------------------------------------
# Fix round 1 (2026-09-18): the copy-icon reservation was per line/text, once,
# regardless of how many addresses actually landed there -- the same defect
# in both this module's own :func:`_wrap_objective` and, unchanged since
# before this file existed, :func:`_fit_prose`'s note-column clip. A line
# carrying two addresses rendered one icon's width too wide with no marker;
# three could push a real address most of the way onto the screen with no
# ellipsis at all -- a partial hex run that reads as a whole address. The
# reviewer's own reproduction widths are pinned directly below.
# ---------------------------------------------------------------------------

_HEX_RUN = re.compile(r"0x[0-9a-fA-F]{6,}")


def _assert_no_bad_partial_hex(lines, addrs):
    """Every hex run on screen is address-safe, in both directions the
    reviewer's reproductions found broken:

    * a **partial** address (not one of *addrs* verbatim) must be
      immediately followed by ``…`` -- never left to look like a shorter,
      genuine one with no mark at all;
    * a **whole** address (one of *addrs* verbatim) must be immediately
      followed by `` ⧉`` -- :func:`address_prose`'s own contract -- never
      rendered complete with its icon silently missing (the reviewer's
      "two addresses, only one icon" and "whole but iconless" reports are
      exactly this half, which a partial-only check cannot see).
    """
    for line in lines:
        for match in _HEX_RUN.finditer(line):
            found = match.group(0)
            tail = line[match.end():match.end() + 2]
            if found in addrs:
                assert tail == " ⧉", (
                    f"a whole address rendered with no copy icon: {line!r}"
                )
            else:
                assert tail[:1] == "…", (
                    f"a partial address with no ellipsis reached the screen: {line!r}"
                )


async def test_two_addresses_survive_whole_with_two_icons_at_the_reviewers_widths():
    """The reviewer's own first reproduction, reconstructed against this
    module's own tight-word objective rather than the reviewer's exact
    wording (unavailable here): two addresses close enough together that
    the old, single-reservation code merged them onto one wrapped line at
    outer width 100-101 while budgeting room for only **one** icon --
    swept and pinned at those exact widths (``find_real_window.py``'s own
    search, not guessed): both addresses rendered whole while only one
    icon appeared. Fixed, both addresses are whole *and* both carry their
    own icon at both widths.
    """
    addr1 = "0x" + "ab" * 20
    addr2 = "0x" + "cd" * 20
    objective = f"chk {addr1} and {addr2} now"
    rows = [dict(ROWS[1], objective=objective, dispatch_note=None)]
    for width in (100, 101):
        lines, text = await _field(swarm_field_rows=rows, size=(width, 20))
        assert any(addr1 in ln for ln in lines), f"width={width}: addr1 not whole"
        assert any(addr2 in ln for ln in lines), f"width={width}: addr2 not whole"
        assert text.count("⧉") == 2, (
            f"width={width}: expected 2 copy icons, found {text.count('⧉')}"
        )
        _assert_no_bad_partial_hex(lines, {addr1, addr2})


async def test_three_addresses_survive_whole_with_three_icons_at_the_reviewers_widths():
    """The reviewer's own second reproduction, reconstructed the same way:
    three addresses in one objective, swept to outer width 141-144, where
    the old code's single reservation under-charged a three-address line by
    two whole icons' worth (6 needed, 2 reserved) and reproduced the
    reviewer's exact symptom progression verbatim -- 40 of the third
    address's 42 characters with no trailing ``…`` at 141, 41 of 42 at 142,
    whole but iconless at 143-144. Every one of those widths reports the
    row tier as ``full`` (the note is visible) and the marker dark, exactly
    the false "nothing was shed" claim the docstring makes and this input
    broke. Fixed, all three addresses are whole, all three carry an icon,
    and the marker is honestly dark because nothing is actually lost any
    more.
    """
    addr1 = "0x" + "ab" * 20
    addr2 = "0x" + "cd" * 20
    addr3 = "0x" + "ef" * 20
    objective = f"a {addr1} b {addr2} c {addr3} d"
    rows = [dict(
        ROWS[0], objective=objective,
        dispatch_note="a review needs a contributor who did not author this work",
    )]
    for width in (141, 142, 143, 144):
        lines, text = await _field(swarm_field_rows=rows, size=(width, 20))
        for addr in (addr1, addr2, addr3):
            assert any(addr in ln for ln in lines), f"width={width}: {addr} not whole"
        assert text.count("⧉") == 3, (
            f"width={width}: expected 3 copy icons, found {text.count('⧉')}"
        )
        _assert_no_bad_partial_hex(lines, {addr1, addr2, addr3})
        assert "did not author" in text, f"width={width}: tier itself shed the note"
        assert "‹" not in text, (
            f"width={width}: nothing is actually lost here, the marker must stay dark"
        )


async def test_the_note_columns_multiple_addresses_are_fixed_through_the_same_primitive():
    """Reviewer item 4: :func:`_fit_prose` (the note column's own single-line
    clip) had the identical one-reservation-per-call defect, predating this
    branch, and is now fixed by delegating to the same
    :func:`_fit_address_aware` :func:`_wrap_objective` uses -- one place,
    not two. Two addresses in ``dispatch_note``, swept at width 250 (both
    comfortably fit: two icons) and 166 -- swept, not guessed: at 166 the
    unfixed single reservation rendered the second address whole with **no**
    icon (the reviewer's own "whole but iconless" shape, one call site
    over); the fixed code correctly withholds it (not rendered at all)
    rather than render it unsafely.
    """
    addr1 = "0x" + "ab" * 20
    addr2 = "0x" + "cd" * 20
    note = f"chk {addr1} and {addr2} now"
    rows = [dict(ROWS[0], objective="short objective", dispatch_note=note)]

    lines, text = await _field(swarm_field_rows=rows, size=(250, 14))
    assert any(addr1 in ln for ln in lines) and any(addr2 in ln for ln in lines)
    assert text.count("⧉") == 2, f"expected 2 icons at width 250, got {text.count('⧉')}"
    _assert_no_bad_partial_hex(lines, {addr1, addr2})

    lines, text = await _field(swarm_field_rows=rows, size=(166, 14))
    assert any(addr1 in ln for ln in lines), "the first address should still fit"
    assert not any(addr2 in ln for ln in lines), (
        "the second address should not render whole with no icon"
    )
    _assert_no_bad_partial_hex(lines, {addr1, addr2})


async def test_a_multi_address_line_that_genuinely_cannot_fit_sheds_visibly_and_lights_the_marker():
    """Four addresses, deliberately narrow: enough content that the
    objective is both wrapped across :data:`MAX_OBJECTIVE_LINES` lines
    *and* forced to shed one address's own text on the final line. Every
    address that does appear is either whole with its icon, or a partial
    hex run immediately followed by ``…`` -- never the reverse -- and the
    marker lights because something genuinely was lost.
    """
    addrs = ["0x" + f"{n}" * 40 for n in ("1", "2", "3", "4")]
    objective = (
        f"filler filler filler filler {addrs[0]} filler filler filler {addrs[1]} "
        f"filler filler filler {addrs[2]} filler filler filler {addrs[3]} filler "
        "filler filler filler filler filler filler filler filler filler"
    )
    rows = [dict(ROWS[1], objective=objective, dispatch_note=None)]
    lines, text = await _field(swarm_field_rows=rows, size=(53, 20))
    _assert_no_bad_partial_hex(lines, set(addrs))
    assert "‹" in text, "four addresses could not all fit -- the marker must light"
    # At least one address must have been shed entirely or partially --
    # otherwise this input is not exercising the claim at all.
    assert not all(addr in text for addr in addrs), (
        "this fixture no longer forces a real shed; widen the objective or "
        "narrow the panel so it does"
    )


def test_swarm_field_tier_ladder_agrees_with_the_body_it_replaced():
    """Branch 3 WP-A agreement test: the module's ``_tier_for`` is now
    ``rowfit.Ladder(...).tier_for``; the body it replaced is pasted here
    verbatim (against the module's own constants) and must agree with it at
    every width from -1 to just past the widest tier, every rung reached.
    """
    from maxpane_dashboard.widgets import rowfit
    from maxpane_dashboard.widgets.surf import swarm_field as module

    def _old_tier_for(width: int) -> str:
        return rowfit.tier_for(
            width, (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("minimal", 0)),
        )

    widths = range(-1, FULL_WIDTH + 6)
    for w in widths:
        assert module._tier_for(w) == _old_tier_for(w), w
    assert {module._tier_for(w) for w in widths} == {"full", "compact", "minimal"}
