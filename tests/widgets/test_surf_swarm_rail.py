"""QUEUE and THROUGHPUT -- the swarm body's rail panels (Task 8).

The chain-id-word agreement test that used to live here moved to
``tests/widgets/test_surf_swarm_chain.py`` in Task 9, alongside the map and
helper it protects (``_swarm_chain.CHAIN_ID_WORDS``/``chain_word``, hoisted
out of ``swarm_throughput.py`` so JUST SHIPPED does not need a third copy).
"""

from maxpane_dashboard.widgets.surf import swarm_throughput as _throughput_mod
from maxpane_dashboard.widgets.surf.swarm_queue import EMPTY_LINE as QUEUE_EMPTY_LINE
from maxpane_dashboard.widgets.surf.swarm_queue import FULL_WIDTH as QUEUE_FULL_WIDTH
from maxpane_dashboard.widgets.surf.swarm_queue import (
    NO_BLOCKED_LINE,
    PENDING_LABEL,
    SurfSwarmQueue,
)
from maxpane_dashboard.widgets.surf.swarm_queue import (
    UNAVAILABLE_LINE as QUEUE_UNAVAILABLE_LINE,
)
from maxpane_dashboard.widgets.surf.swarm_throughput import (
    AGENTS_UNAVAILABLE_LINE,
    NO_AGENTS_LINE,
    STALE_WORD,
    SurfSwarmThroughput,
)
from tests.widgets.surf_compositing import composite_lines

QUEUE_ROWS = [{"state": "completed", "count": 43}, {"state": "cancelled", "count": 11},
              {"state": "blocked", "count": 6}, {"state": "executing", "count": 2}]
BLOCKED = [{"job_id": "9c6543f5-aaaa", "template": "shape:chain",
            "reason": "node build_dapp: runtime_error", "moved_ts": 1_789_000_000.0}]
THROUGHPUT = {"accepted_per_day": 1.86, "median_delivery_s": 943,
              "revision_rate": 0.125, "window_days": 7}
#: F6 (``docs/surf_swarm_followups.md``): a genuine read of a fully-drained
#: pipeline -- every one of the seven ``pending*`` counters real and zero.
QUEUE_DEPTHS_ZERO = {
    "verification": 0, "attestation": 0, "deployment": 0, "delivery": 0,
    "feedback": 0, "fuzz": 0, "sites": 0,
}
#: A genuine read with a mixed backlog -- some counters idle, some not.
QUEUE_DEPTHS_MIXED = {
    "verification": 2, "attestation": 0, "deployment": 1, "delivery": 0,
    "feedback": 3, "fuzz": 0, "sites": 1,
}
SCORES = [{"agent_id": "10303", "agent_token": "2", "jobs_scored": 9,
           "mean_score": 97.8, "last_tx_hash": "0x8370" + "7e" * 30, "last_chain_id": 11155111}]


async def test_the_queue_counts_every_state_and_names_what_is_blocked():
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED))
    assert "completed" in text and "43" in text
    assert "runtime_error" in text


async def test_nothing_blocked_is_said_out_loud():
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=[]))
    assert NO_BLOCKED_LINE in text


async def test_the_queue_panel_is_unavailable_with_no_marker_and_nothing_to_show():
    """Task 11 fix round 1: the first draft of this test fed the widget its
    bare ``update_data`` defaults (no kwargs at all -> ``queue_rows=None,
    blocked_rows=None``), a shape the real producer can never emit --
    ``data/surf_manager._swarm_keys`` calls ``sw.queue_rows(jobs)``/
    ``sw.blocked_rows(jobs)`` unconditionally, and both always return a
    ``list`` (``[]`` at the cold-slot least: ``data/surf_swarm.queue_rows``
    and ``.blocked_rows`` both open ``if not jobs: return []``), never
    ``None``. A gate narrowed from ``not queue_rows`` to
    ``queue_rows is None`` left the whole file green against that bare-default
    payload, because ``None is None`` is exactly as true as ``not None`` --
    the test could not tell the two gates apart.

    Driven now through the shape the manager actually publishes for a cold
    ``SLOT_SWARM`` (``swarm_entry is None`` -> ``swarm_slot = {}`` ->
    ``jobs = None`` -> both row keys ``[]``, marker ``None``), taken from
    ``data/surf_manager.py``'s own cold-start path rather than from a widget
    default.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=[], swarm_blocked_rows=[],
        swarm_as_of_hhmm=None))
    assert QUEUE_UNAVAILABLE_LINE in text
    assert QUEUE_EMPTY_LINE not in text
    assert NO_BLOCKED_LINE not in text


async def test_a_genuine_empty_queue_read_differs_from_unavailable():
    """The other half of the same gap: a real marker with both lists
    genuinely empty must print the two *empty* lines, never the unavailable
    one -- the curator rail bug the whole body exists to avoid, now pinned
    for QUEUE specifically rather than only argued for in its docstring.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=[], swarm_blocked_rows=[],
        swarm_as_of_hhmm="12:00"))
    assert QUEUE_EMPTY_LINE in text
    assert NO_BLOCKED_LINE in text
    assert QUEUE_UNAVAILABLE_LINE not in text


async def test_queue_carries_the_live_marker_not_the_scores_one():
    """F-B: QUEUE used to serve last-good rows with no ``as of`` marker at
    all. Its rows come off ``SLOT_SWARM`` (the live tier), never the slower
    scores sweep, so the title must carry ``swarm_as_of_hhmm`` -- and only
    that marker. Feeding a distinct ``swarm_scores_as_of_hhmm`` alongside it
    (a value QUEUE's own ``update_data`` has no parameter for) proves it
    could not have been wired to the wrong clock, not merely that the right
    one happens to be the only one available.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED,
        swarm_as_of_hhmm="14:00", swarm_scores_as_of_hhmm="13:20"))
    assert "as of 14:00" in text
    assert "13:20" not in text


async def test_queue_shows_no_marker_when_it_has_never_been_read():
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=[], swarm_blocked_rows=[],
        swarm_as_of_hhmm=None))
    assert "as of" not in text


# ---------------------------------------------------------------------------
# F6 (docs/surf_swarm_followups.md): swarm_queue_depths -- the pipeline's own
# backlog counters, gated on the same live-tier marker as the rest of the
# panel rather than on the depths dict's own truthiness.
# ---------------------------------------------------------------------------


async def test_a_real_zero_backlog_renders_its_total_not_unavailable():
    """A genuine read of a fully-drained pipeline (every counter real and
    zero) must print the real total, never fall back to the panel's
    unavailable line -- the curator rail bug, one instrument over: a dict of
    zeros is truthy and real, and gating on a *derived* total's truthiness
    (rather than on whether the dict was read at all) would render this
    identically to a never-read backlog.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED,
        swarm_as_of_hhmm="14:00", swarm_queue_depths=QUEUE_DEPTHS_ZERO))
    assert f"{PENDING_LABEL} 0" in text
    assert QUEUE_UNAVAILABLE_LINE not in text


async def test_a_populated_backlog_names_only_its_nonzero_counters():
    """A mixed real read prints the total and every counter that is
    actually nonzero, by name -- and leaves the idle ones unnamed, the
    compact form the module docstring argues for over seven fixed rows.

    Rendered at a width comfortably past what the full line needs (measured
    at 64 cells): this test is about which names appear, not about the
    clip boundary -- :func:`test_the_pending_line_clips_like_every_other_line`
    below covers the narrow case on its own terms.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (90, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED,
        swarm_as_of_hhmm="14:00", swarm_queue_depths=QUEUE_DEPTHS_MIXED))
    assert f"{PENDING_LABEL} 7" in text
    assert "verification 2" in text
    assert "deployment 1" in text
    assert "feedback 3" in text
    assert "sites 1" in text
    # The idle counters are real too, but this compact form does not name
    # them individually -- only the running total accounts for them.
    assert "attestation 0" not in text
    assert "fuzz 0" not in text
    assert "delivery 0" not in text


async def test_the_pending_line_clips_like_every_other_line():
    """At a width too narrow for the full pending line, it clips honestly
    with ``…`` rather than overflowing -- the same fitted-not-sized
    behaviour every other line in this panel already gets from
    ``rowfit.clip``.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED,
        swarm_as_of_hhmm="14:00", swarm_queue_depths=QUEUE_DEPTHS_MIXED))
    assert f"{PENDING_LABEL} 7" in text
    assert "sites 1" not in text
    assert "…" in text


async def test_an_unread_backlog_never_renders_pending_even_with_no_rows_either():
    """The ordinary never-read case: no marker, no rows at all -- the whole
    panel is the existing unavailable state, and the pending block (fed a
    real, truthy dict here to prove it is not what is keeping it hidden) is
    invisible inside it.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=[], swarm_blocked_rows=[],
        swarm_as_of_hhmm=None, swarm_queue_depths=QUEUE_DEPTHS_MIXED))
    assert QUEUE_UNAVAILABLE_LINE in text
    assert PENDING_LABEL not in text
    assert "verification" not in text


async def test_an_unread_backlog_stays_hidden_even_when_rows_prove_a_real_read():
    """The trap this block exists to close, proven at the instrument that
    actually gates it rather than at the outer whole-panel gate above.

    ``swarm_queue_depths`` can be a genuinely truthy dict -- even one with
    real, nonzero counters -- and still must not reach the screen when
    ``swarm_as_of_hhmm`` says this tier was never read this cycle. Feeding
    real ``swarm_queue_rows`` alongside no marker (QUEUE's own escape hatch,
    module docstring's *"The unread/empty split"* section) keeps the panel
    out of its whole-unavailable state -- state counts render fine -- so
    this isolates the pending block's *own* gate: a version keyed off the
    depths dict's own truthiness (rather than off the marker) would pass
    populated data through right here, with the rest of the panel looking
    perfectly healthy beside it.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=[],
        swarm_as_of_hhmm=None, swarm_queue_depths=QUEUE_DEPTHS_MIXED))
    assert "completed" in text, "the escape hatch should keep the panel out of its unavailable state"
    assert QUEUE_UNAVAILABLE_LINE not in text
    assert PENDING_LABEL not in text
    assert "verification" not in text


async def test_throughput_names_its_window_and_the_agents():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_score_rows=SCORES))
    assert "7d" in text
    assert "1.86" in text
    assert "97.8" in text and "#2" in text


async def test_an_unread_throughput_is_dashes_not_zeroes():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=None, swarm_score_rows=None))
    assert "--" in text
    assert "0.0" not in text


async def test_an_unread_throughput_carries_no_as_of_marker_either():
    """F10's never-read half, pinned at the panel: no ``swarm_throughput``
    and no ``swarm_scores_as_of_hhmm`` means nothing was ever read, so the
    title carries no marker at all -- the signal a genuine empty read (below)
    does carry, and the one thing that tells the two all-dash states apart.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=None, swarm_score_rows=None,
        swarm_scores_as_of_hhmm=None))
    assert "as of" not in text


async def test_a_genuine_empty_throughput_read_shows_a_real_zero_not_a_dash():
    """F10: the other half of the never-read/genuinely-empty split, at the
    panel rather than the dict. Feeding the dict ``data/surf_swarm.throughput``
    now returns for a real read that found no jobs (``accepted_per_day: 0.0``,
    ``median_delivery_s``/``revision_rate`` still ``None`` -- neither has a
    representable zero) alongside a real ``swarm_scores_as_of_hhmm`` marker:
    ``accepted`` prints the genuine zero rather than a dash, the title
    carries the marker, and the two fields with no honest zero still dash --
    the marker beside them is what tells a reader that dash means "read,
    nothing to measure" rather than "never read" (the state the test above
    pins). Never a stale number presented as live, and never a real zero
    rendered as if nothing had been read.
    """
    genuinely_empty = {"accepted_per_day": 0.0, "median_delivery_s": None,
                        "revision_rate": None, "window_days": 7}
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=genuinely_empty,
        swarm_score_rows=[], swarm_scores_as_of_hhmm="04:06"))
    assert "as of 04:06" in text
    assert "0.00/day" in text
    assert "--" in text


async def test_the_agent_section_is_unavailable_with_no_marker_and_no_rows():
    """Task 11 fix round 1: like QUEUE's own gap above, the first draft fed
    the widget its bare ``update_data`` defaults (no kwargs -> ``score_rows=
    None``), a shape ``data/surf_manager._swarm_scores_keys`` can never
    emit -- it calls ``sw.score_rows(details)`` unconditionally, and
    ``data/surf_swarm.score_rows`` opens ``if not details: return []``,
    never ``None``. A gate narrowed from ``not score_rows`` to
    ``score_rows is None`` left this test green against that bare-default
    payload for the identical reason QUEUE's did.

    Driven now through the manager's own cold-``SLOT_SWARM_SCORES`` shape
    (``scores_entry is None`` -> ``scores_slot = {}`` -> ``details = None``
    -> ``swarm_score_rows = []``, marker ``None``), taken from
    ``data/surf_manager.py`` rather than from a widget default. The four
    rate rows print dashes unconditionally (see
    ``test_an_unread_throughput_is_dashes_not_zeroes`` above), so this test
    stays scoped to the agent section's own degraded state alone.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_score_rows=[],
        swarm_scores_as_of_hhmm=None))
    assert AGENTS_UNAVAILABLE_LINE in text
    assert NO_AGENTS_LINE not in text


async def test_a_genuine_empty_score_read_differs_from_unavailable():
    """A real scores marker with no agents scored yet must print
    ``NO_AGENTS_LINE``, never ``AGENTS_UNAVAILABLE_LINE`` -- the same
    unread-vs-empty distinction QUEUE's own pair of tests pins.
    """
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_score_rows=[],
        swarm_scores_as_of_hhmm="04:06"))
    assert NO_AGENTS_LINE in text
    assert AGENTS_UNAVAILABLE_LINE not in text


async def test_the_stale_word_appears_only_when_told():
    fresh = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=False))
    stale = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=True))
    assert STALE_WORD not in fresh
    assert STALE_WORD in stale


# ---------------------------------------------------------------------------
# Fix round 1: THROUGHPUT names the chain per score row, from that row's own
# ``last_chain_id`` -- an allowlist beside the hash, never in the title, and
# never printed for a row with no hash at all.
# ---------------------------------------------------------------------------

_SEPOLIA_ROW = {"agent_id": "10303", "agent_token": "2", "jobs_scored": 9,
                "mean_score": 97.8, "last_tx_hash": "0x8370" + "7e" * 30,
                "last_chain_id": 11155111}
_UNKNOWN_CHAIN_ROW = dict(_SEPOLIA_ROW, last_chain_id=999999999)
_NO_HASH_ROW = dict(_SEPOLIA_ROW, last_tx_hash=None)


async def test_a_known_chain_id_names_itself_beside_the_hash():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=[_SEPOLIA_ROW]))
    assert "SEPOLIA" in text


async def test_an_unknown_chain_id_renders_the_dash():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=[_UNKNOWN_CHAIN_ROW]))
    assert "—" in text
    assert "SEPOLIA" not in text and "MAINNET" not in text


async def test_a_row_with_no_hash_names_no_chain_either():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=[_NO_HASH_ROW]))
    assert "SEPOLIA" not in text and "MAINNET" not in text and "—" not in text


# ---------------------------------------------------------------------------
# The standing no-bracket requirement (task brief): each panel's composited
# region carries no literal ``[`` or ``]`` when it renders a hostile
# third-party string, proven by routing that same string through markup
# instead of a pre-built ``Text`` (see each mutation section in the report
# for the monkeypatch that demonstrates this bites).
# ---------------------------------------------------------------------------

_HOSTILE = "[/][red]PWNED[/] boom"
#: The agent-token cell is only six terminal columns wide (``#`` plus five
#: digits at full strength) -- a hostile string here has to survive being
#: clipped to that budget and still leave a checkable word behind, unlike
#: the blocked-reason cell above which has room to spare.
_HOSTILE_AGENT = "[/]PWNED[/]"


async def test_a_hostile_blocked_reason_renders_with_no_literal_brackets():
    hostile = [{"job_id": "x", "template": "shape:chain", "reason": _HOSTILE,
                "moved_ts": 1_789_000_000.0}]
    lines = await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=hostile,
        region_only=True,
    )
    region = "\n".join(lines)
    assert "[" not in region and "]" not in region
    assert "PWNED" in region


async def test_a_hostile_agent_token_renders_with_no_literal_brackets():
    hostile = [{"agent_id": "10303", "agent_token": _HOSTILE_AGENT, "jobs_scored": 9,
                "mean_score": 97.8, "last_tx_hash": "0x8370" + "7e" * 30,
                "last_chain_id": 11155111}]
    lines = await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_score_rows=hostile,
        region_only=True,
    )
    region = "\n".join(lines)
    assert "[" not in region and "]" not in region
    assert "PWNED" in region


# ---------------------------------------------------------------------------
# Fix round 2, finding 1's own agreement test (the restated chain-id map vs.
# ``data/surf_swarm._NETWORKS``) moved to ``tests/widgets/test_surf_swarm_
# chain.py`` in Task 9, with the map and helper it protects
# (``_swarm_chain.CHAIN_ID_WORDS``/``chain_word``).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fix round 2, finding 2: the narrow-tier code paths, exercised as
# properties rather than pinned to today's threshold numbers -- those
# numbers are the implementer's own measurements and a later task re-sweeps
# them in situ against the real screen (CLAUDE.md, the POOL4 MARKET section).
# A test pinned to a literal threshold would redden the day that sweep lands
# for a reason that is not a defect; deriving the two widths from the
# modules' own constants survives it.
# ---------------------------------------------------------------------------


async def test_the_queue_blocked_line_sheds_its_time_column_below_full_width():
    """At the full tier the blocked line leads with ``HH:MM``; below it, the
    time column is gone and the title says so.

    ``moved_ts=None`` makes ``_fmt.hhmm`` return the fixed sentinel
    ``"??:??"`` (``ts <= 0`` short-circuits before any clock read), which is
    a deterministic **formatter output for a controlled degenerate input**,
    not a pinned threshold -- unlike a real epoch value it does not depend on
    the test machine's timezone, so this remains a property assertion.
    """
    row = [{"job_id": "y", "template": "shape:chain", "reason": "boom", "moved_ts": None}]
    padding = SurfSwarmQueue._TITLE_PADDING_COLS
    full_width = QUEUE_FULL_WIDTH + padding + 10
    compact_width = QUEUE_FULL_WIDTH + padding - 5

    full_text = "\n".join(await composite_lines(
        SurfSwarmQueue, (full_width, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=row))
    compact_text = "\n".join(await composite_lines(
        SurfSwarmQueue, (compact_width, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=row))

    # Full tier: the time column is there, the reason is there, no widen hint.
    assert "??:??" in full_text
    assert "boom" in full_text
    assert "‹" not in full_text

    # Below the threshold: the time column is gone (never a stray "??:??"),
    # the reason still renders (it is what the column budget was freed for),
    # and the title's own marker agrees that something was shed.
    assert "??:??" not in compact_text
    assert "boom" in compact_text
    assert "‹" in compact_text


async def test_throughput_caps_the_hash_window_well_short_of_a_bare_address():
    """2026-09-17 (swarm column-balance change): ``_MIN_TX_COLS`` above is a
    *floor* -- below it the hash and its chain word are dropped together, on
    the test above. Until this task there was no matching *ceiling*: handed
    enough budget, ``_agent_lines`` spent every free column on the hash
    window, which is exactly the owner's own complaint off a live
    screenshot (the module docstring's captured example,
    ``0xe5b157220cea6871f035466bd4247d0…a69617``). ``_MAX_TX_COLS`` (12)
    caps it instead, and the cap is real: :func:`widgets.address.short_hex`
    renders a genuinely different (longer) window at 12 cells than at the
    11-cell floor (one more head character -- ``0x22222…2222`` vs
    ``0x2222…2222``), so this is not a value indistinguishable from the
    floor it sits one cell above.

    Driven at an absurdly wide budget (500 columns) so the assertion is
    about the *cap*, not about some particular screen width happening to
    land under it -- the same "wide enough that CSS cannot be the reason"
    shape :func:`test_throughput_sheds_the_hash_and_its_chain_word_together`
    already uses at its own floor.
    """
    from maxpane_dashboard.widgets.address import short_hex

    T = _throughput_mod
    expected = short_hex(_SEPOLIA_ROW["last_tx_hash"], T._MAX_TX_COLS)
    uncapped = short_hex(_SEPOLIA_ROW["last_tx_hash"], 61)
    assert len(expected) < len(uncapped), (
        "the two windows are the same length -- this test cannot tell a "
        "capped render from an uncapped one at this budget"
    )

    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (500, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=[_SEPOLIA_ROW],
    ))
    assert expected in text, (500, expected)
    assert uncapped not in text, (
        "the hash window grew past MAX_TX_COLS at a 500-column budget -- "
        "the cap is not being applied"
    )
    assert "‹" not in text, "500 columns is not a width this panel should ever mark at"


async def test_throughput_sheds_the_hash_and_its_chain_word_together():
    """Never a bare hash, per the fix-round-1 contract: at every width in a
    swept range, the hash and its chain word are shown together or not at
    all, the never-shed agent identity/score cells survive regardless, and
    at the boundary the sweep finds, the title's widen marker agrees with
    whether anything was genuinely shed there.

    F1 (``docs/surf_swarm_followups.md``): this used to derive its two
    check widths from the module's own private constants
    (``_AGENT_COLS``/``_SCORE_COLS``/``_JOBS_COLS``/``_MIN_TX_COLS``/
    ``_CHAIN_COLS``/``_GAP``) by re-implementing ``_agent_lines``'s own
    arithmetic inline. That values-agree-with-themselves shape bites a
    mutation to the formula's *behaviour* (drop the hash without the chain
    word, or the reverse, at the two sampled widths) but not one that
    changes the formula's *shape* -- a different reservation order, an
    added term -- and moves both the re-derived numbers and the widget's
    real crossover together, in lockstep, while a genuine pairing violation
    opens up at some *other* width neither sample point ever visits. The
    terminal-layout skill's "sweep the boundary, not a comfortable width"
    rule, taken literally: render across a real range and let the
    composited text say where the pair is actually shed, at every width in
    the bracket, rather than trusting two numbers computed from the same
    arithmetic under test.
    """
    row = [_SEPOLIA_ROW]

    # A generous, hand-picked bracket -- comfortably below any width this
    # panel could plausibly need the pair at, comfortably above it. Not
    # derived from the module's own constants; that re-derivation is
    # exactly the bug this test used to have.
    lo, hi = 15, 90

    boundary = None
    shed_seen = False
    for width in range(lo, hi):
        text = "\n".join(await composite_lines(
            SurfSwarmThroughput, (width, 14), swarm_throughput=THROUGHPUT,
            swarm_score_rows=row))
        has_hash = "0x8370" in text
        has_chain = "SEPOLIA" in text
        # Reserved together, shed together -- at every width, not merely
        # two sampled ones.
        assert has_hash == has_chain, (
            width, has_hash, has_chain,
            "the hash and its chain word disagree at this width -- one "
            "shed without the other",
        )
        if has_hash:
            if boundary is None:
                boundary = width
        else:
            shed_seen = True
        # The agent identity and score cells are never shed, at any width
        # in the bracket.
        assert "97.8" in text, width
        assert "#2" in text, width

    assert boundary is not None, "the bracket never showed the pair -- widen it upward"
    assert shed_seen, "the bracket never shed the pair -- widen it downward"

    at_text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (boundary, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=row))
    below_text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (boundary - 1, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=row))

    # At the true boundary the sweep found: nothing shed, no widen hint.
    assert "0x8370" in at_text and "SEPOLIA" in at_text
    assert "‹" not in at_text

    # One column narrower: the pair is genuinely shed, and the marker
    # agrees that something was.
    assert "0x8370" not in below_text and "SEPOLIA" not in below_text
    assert "‹" in below_text


async def test_the_marker_survives_dropping_the_as_of_suffix_when_neither_fits_together():
    """2026-09-16 layout change: THROUGHPUT moved beside JUST SHIPPED,
    narrower than sharing a rail with QUEUE, and reachable widths now exist
    where the bare title fits alongside the ``‹`` glyph but the title with
    its own freshness suffix (``· as of HH:MM``) does not. ``_title_text``
    drops the suffix and tries the glyph again against the bare title,
    rather than giving up and showing neither -- see
    ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:`` block in
    ``screens/surf.py`` for why this could not be bought back with CSS.

    The width is derived, not hand-typed: it is exactly wide enough for
    ``"THROUGHPUT"`` plus the bare glyph and no wider, so the full title
    (with its ``as of`` suffix) plus the glyph provably does not fit at it
    either -- the test would be vacuous at any width where both fit.
    """
    from rich.cells import cell_len

    T = _throughput_mod
    as_of = "13:50"
    padding = SurfSwarmThroughput._TITLE_PADDING_COLS
    bare_needs = cell_len(T.TITLE) + 2 + 1  # base + "  " + the bare "‹" glyph
    full_needs = cell_len(f"{T.TITLE} · as of {as_of}") + 2 + 1
    assert bare_needs < full_needs, "the suffix must cost real budget for this test to mean anything"
    width = bare_needs + padding

    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (width, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=[_SEPOLIA_ROW], swarm_scores_as_of_hhmm=as_of,
    ))
    assert "‹" in text, (
        "the bare title plus the glyph fits this width -- the marker should "
        "survive by dropping the as-of suffix rather than disappear with it"
    )
    assert as_of not in text, (
        "the as-of suffix should have been dropped to make room for the "
        "marker at this width, not kept alongside a marker that does not fit"
    )


def test_swarm_queue_tier_ladder_agrees_with_the_body_it_replaced():
    """Branch 3 WP-A agreement test: the module's ``_tier_for`` is now
    ``rowfit.Ladder(...).tier_for``; the body it replaced is pasted here
    verbatim (against the module's own constants) and must agree with it at
    every width from -1 to just past the widest tier, every rung reached.
    """
    from maxpane_dashboard.widgets import rowfit
    from maxpane_dashboard.widgets.surf import swarm_queue as module
    from maxpane_dashboard.widgets.surf.swarm_queue import COMPACT_WIDTH, FULL_WIDTH

    def _old_tier_for(width: int) -> str:
        return rowfit.tier_for(width, (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH)))

    widths = range(-1, FULL_WIDTH + 6)
    for w in widths:
        assert module._tier_for(w) == _old_tier_for(w), w
    assert {module._tier_for(w) for w in widths} == {"full", "compact"}
