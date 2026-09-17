"""QUEUE and THROUGHPUT -- the swarm body's rail panels (Task 8).

The chain-id-word agreement test that used to live here moved to
``tests/widgets/test_surf_swarm_chain.py`` in Task 9, alongside the map and
helper it protects (``_swarm_chain.CHAIN_ID_WORDS``/``chain_word``, hoisted
out of ``swarm_throughput.py`` so JUST SHIPPED does not need a third copy).
"""

from maxpane_dashboard.widgets.surf import swarm_throughput as _throughput_mod
from maxpane_dashboard.widgets.surf.swarm_queue import EMPTY_LINE as QUEUE_EMPTY_LINE
from maxpane_dashboard.widgets.surf.swarm_queue import FULL_WIDTH as QUEUE_FULL_WIDTH
from maxpane_dashboard.widgets.surf.swarm_queue import NO_BLOCKED_LINE, SurfSwarmQueue
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
    """Task 11: no committed test drove ``UNAVAILABLE_LINE`` before this one
    -- ``_is_unavailable`` (a cold ``SLOT_SWARM``, or an all-failed read: no
    ``swarm_as_of_hhmm`` marker and both lists empty) is reachable in
    production (``data/surf_manager._swarm_keys`` publishes ``None`` for
    both list keys whenever ``jobs`` is falsy, exactly the frozen ``[]``
    the module docstring names), but nothing asserted the string it renders
    for it. Everything is left at its default (no kwargs at all), which
    resolves through ``update_data``'s own ``None`` defaults to the cold-slot
    shape.
    """
    text = "\n".join(await composite_lines(SurfSwarmQueue, (60, 14)))
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


async def test_the_agent_section_is_unavailable_with_no_marker_and_no_rows():
    """Task 11: like QUEUE's own gap, no committed test drove
    ``AGENTS_UNAVAILABLE_LINE`` before this one -- ``_agents_unavailable``
    (no ``swarm_scores_as_of_hhmm`` marker and an empty ``swarm_score_rows``)
    is reachable in production (``data/surf_manager._swarm_scores_keys``
    publishes ``[]`` for ``swarm_score_rows`` whenever the sweep has never
    run, exactly the frozen empty shape ``data/surf_swarm.score_rows``
    always returns), but nothing asserted the string it renders for it.
    The four rate rows print dashes unconditionally (see
    ``test_an_unread_throughput_is_dashes_not_zeroes`` above), so this test
    is scoped to the agent section's own degraded state alone.
    """
    text = "\n".join(await composite_lines(SurfSwarmThroughput, (60, 14)))
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


async def test_throughput_sheds_the_hash_and_its_chain_word_together():
    """Below the reserved-together threshold, both the hash and the chain
    word vanish -- never a bare hash, per the fix-round-1 contract -- and
    the title's widen marker agrees; the agent identity and score cells,
    which are never shed, survive at both widths.

    The threshold is derived from the module's own private constants
    (``_AGENT_COLS``/``_SCORE_COLS``/``_JOBS_COLS``/``_MIN_TX_COLS``/
    ``_CHAIN_COLS``/``_GAP``) rather than a hand-typed number, so a later
    re-sweep of any one of them cannot make this test lie about which tier
    it is driving.
    """
    T = _throughput_mod
    fixed = T._rowfit.row_cols((T._AGENT_COLS, T._SCORE_COLS, T._JOBS_COLS))
    chain_reserve = T._GAP + T._CHAIN_COLS
    threshold_available = T._MIN_TX_COLS + chain_reserve
    threshold_budget = threshold_available + fixed + T._GAP
    threshold_width = threshold_budget + SurfSwarmThroughput._TITLE_PADDING_COLS

    wide_width = threshold_width + 15
    narrow_width = threshold_width - 5
    assert narrow_width > 0, "the derived threshold leaves no room to test below it"

    row = [_SEPOLIA_ROW]
    wide_text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (wide_width, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=row))
    narrow_text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (narrow_width, 14), swarm_throughput=THROUGHPUT,
        swarm_score_rows=row))

    # Wide: hash and chain word both present, no widen hint.
    assert "SEPOLIA" in wide_text
    assert "0x8370" in wide_text
    assert "‹" not in wide_text

    # Narrow: neither the hash nor the chain word survives -- reserved
    # together, shed together -- while the never-shed cells still do, and
    # the title agrees that a column was dropped.
    assert "SEPOLIA" not in narrow_text
    assert "0x8370" not in narrow_text
    assert "97.8" in narrow_text
    assert "#2" in narrow_text
    assert "‹" in narrow_text
