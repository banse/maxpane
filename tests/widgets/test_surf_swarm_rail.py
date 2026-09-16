"""QUEUE and THROUGHPUT -- the swarm body's rail panels (Task 8)."""

from maxpane_dashboard.widgets.surf.swarm_queue import NO_BLOCKED_LINE, SurfSwarmQueue
from maxpane_dashboard.widgets.surf.swarm_throughput import STALE_WORD, SurfSwarmThroughput
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


async def test_the_stale_word_appears_only_when_told():
    fresh = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=False))
    stale = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=True))
    assert STALE_WORD not in fresh
    assert STALE_WORD in stale


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
