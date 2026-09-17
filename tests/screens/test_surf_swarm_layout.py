"""Task 12 -- the `s` SWARM body's own measured layout.

Two pins live here and nowhere else: ``SURF_SWARM_FULL_LAYOUT_COLUMNS`` and
``SURF_SWARM_FULL_LAYOUT_ROWS``. Their measurement method, their binding
panel/container and their per-panel derivation are in their own ``#:``
blocks in ``screens/surf.py``; this file is what makes those blocks fail
when they stop being true.

**Re-swept three times over three consecutive days.** 2026-09-16: the body
went from THE FIELD beside a QUEUE-over-THROUGHPUT rail (JUST SHIPPED
full-width beneath) to THE FIELD beside QUEUE on top and JUST SHIPPED
beside THROUGHPUT beneath -- a change to the grid, so both pins moved
(93 -> 128, 42 -> 26). **2026-09-17, review round 1:** 128 was corrected to
**115** -- it had grown the column pin instead of shortening JUST SHIPPED's
own fixed width, the wrong side of "the column for the tx hash can be
shortened to fit into the space right to the JUST SHIPPED widget" and of
the terminal-layout skill's own "shorten the value, do not raise the pin"
rule. JUST SHIPPED gained a third, narrower ``tight`` width tier
(``swarm_shipped.py``) and was fixed at *that* tier's own need (68) --
which meant it marked ``‹ widen`` permanently on this body, at every
terminal size, since a fixed CSS width never grows. **2026-09-17, review
round 2, same day:** that permanence was itself the wrong outcome -- a
marker that is always lit carries no information and actively lies
("widen and you will see more" being false at every size it was checked).
JUST SHIPPED's CSS moved from a bare fixed number to ``1fr`` bounded by
``min-width: 68; max-width: 81;``, reproducing round 1's own arithmetic
exactly through the pin (measured, not assumed) while letting the panel
grow to ``full`` once the terminal genuinely has the room, at outer width
164. The pin did **not** move for this: 115 stands, re-confirmed against
all four payloads. The row pin (26) did not move on any of the three
days; this file re-measured it each time anyway rather than assuming.
Nothing here still compares against the launch-day or round-1 numbers;
``screens/surf.py``'s own ``#:`` blocks carry that history.

**2026-09-17, a fourth round, the owner's own live screenshot: 115 -> 95,
and the column pin's own binding set widened from one panel to two.** The
complaint was the opposite shape from every round above: THE FIELD and
JUST SHIPPED were genuinely clipping while QUEUE and THROUGHPUT carried a
wide band of empty space neither needed. Two changes, together:
:data:`swarm_throughput._MAX_TX_COLS` (12) caps the tx-hash column's own
ceiling for the first time (:data:`swarm_throughput._MIN_TX_COLS` was
always a floor, never a ceiling, and the panel spent every free column on
the hash whenever it had one to spend -- the module docstring's own
captured example, a hash windowed most of the way across the screen); and
QUEUE/THROUGHPUT's CSS moved from an unbounded ``1fr`` (QUEUE) or a
``1fr`` sharing growth with JUST SHIPPED (THROUGHPUT) to **the same**
``width: 1fr; max-width: 46;`` on both -- a size sized to the wider of the
two panels' own real content need (:data:`swarm_queue.FULL_WIDTH`, 27, for
QUEUE; THROUGHPUT's own agent-row need once the hash reaches its 12-cell
cap, 41, both plus the shared 2-column title padding, plus 2 more columns
this row pair's own scrollbar-gutter/seam overhead costs a `max-width`
sibling that a bare fixed number does not -- read off the sweep, not
summed) rather than two different numbers, because they sit in two
separate row containers and a reader compares their seam, not their own
independent needs.

**Why bounded ``1fr`` and not a bare fixed number, on THE FIELD/JUST
SHIPPED precedent.** The first attempt used a bare fixed ``width: 46;`` on
both, and it reproduced the exact defect JUST SHIPPED's own round 1 shipped
one row up: at any outer width below where the row's OTHER fixed-or-floored
sibling (JUST SHIPPED's own ``min-width: 68``) could also fit, Textual does
not shrink a fixed-width or min-width-bounded child to make room -- it
lays both out at their stated size regardless, and the overflow is not a
CSS ellipsis or a ``DataTable`` scrollbar (both of which this file's own
``_swarm_clipped``/``marked`` checks already catch): it is the sibling's
own rendered *region* extending past its container's, silently cropped by
the compositor at the container edge with **no** ``…``, no glyph, no
scrollbar, nothing -- a genuinely different, worse failure shape than
every other one this file names, and one the existing detectors cannot
see at all (confirmed: a synthetic sweep with the bare-fixed CSS showed
"whole" -- no marks, no clips -- at outer widths where THROUGHPUT's own
agent row was visibly cut off mid-hex-digit on the composited screen).
``width: 1fr; max-width: 46;`` (no floor) restores THE FIELD/JUST
SHIPPED's own precedent one row over: below the point where a panel's
sibling has genuine room, the bounded ``1fr`` shrinks smoothly, all the
way to 0 if it must, rather than holding its ground and forcing an
overflow -- exactly what let THROUGHPUT (previously bare ``1fr``, no
bound at all) absorb JUST SHIPPED's own ``min-width`` pressure safely
before this round, and what a hard fixed number cannot do. Below the new
column pin this reproduces THROUGHPUT's own pre-existing, already-accepted
silent-below-75 exception (below) rather than a new, unbounded one -- **the
same** threshold, unmoved, because below the point where either panel
would hit its own 46-column cap, a bounded ``1fr`` and a bare unbounded
``1fr`` behave identically; the cap only ever narrows growth, never
raises a floor.

**Two panels bind now, not one, and the widest of this file's own
exceptions folded into the pin rather than staying separate from it.**
JUST SHIPPED's own "never clears below" exception -- present in every
round back to launch, most recently 164 -- is **gone**: at the new pin
(95) JUST SHIPPED is already whole, because it no longer has to share
growth with an unbounded THROUGHPUT past QUEUE's own 46-column cap. One
column under the pin, JUST SHIPPED marks alongside THROUGHPUT, both for
the first time at the same boundary, so
:func:`test_the_swarm_binding_panel_is_the_one_the_block_names`'s own
assertion widens from one name to two. THE FIELD's own exception is not
gone, but it shrank sharply for the identical structural reason QUEUE's
own cap gave THROUGHPUT and JUST SHIPPED more of the row: 246 -> **170**,
because THE FIELD is now the *only* unbounded panel in its own row (QUEUE
capped at 46 no longer takes half of every column above its own cap), so
outer-width growth reaches THE FIELD's own content need roughly twice as
fast as it did when QUEUE was still absorbing half of it.
:data:`THROUGHPUT_NEVER_MARKS_BELOW` (75) is the one named exception this
round did **not** move, for the reason two paragraphs up: below that
width THROUGHPUT behaves identically to its pre-round shape, bounded or
not. Every number in this section was re-swept in situ, over a range that
straddles the new pin rather than starting at it, on all four payloads
this file already carries -- none of them moved the boundary by a single
column from any other.

Six things this file exists to pin above the rest
----------------------------------------------------
1. **The column pin fails in both directions**, once THE FIELD's own
   exception is set aside. THE FIELD's ``‹`` never clears below 170 columns
   (measured, not assumed -- see the constant's own ``#:`` block, and
   :data:`FIELD_NEVER_CLEARS_BELOW` below); that threshold sits past this
   file's own width-sweep range, so within it THE FIELD is *expected* to
   keep marking, and a sweep that demanded "no marker anywhere" would never
   find a pin at all. JUST SHIPPED carried a matching exception through
   three earlier rounds (most recently 164) and does **not** any more --
   the 2026-09-17 column-balance change (above) made it whole exactly where
   the rest of the body is, so it is an ordinary panel in this property now,
   not a second named carve-out. "Whole" here therefore means "no marker
   outside THE FIELD's own named exception, and no CSS-clipped line, and no
   hidden DataTable column" -- and that claim is checked in both
   directions, exactly the way every other body's own pin is.
2. **The claims are properties, never literals**, with the remaining
   exception named rather than silently absorbed: "whenever a row would
   clip, some panel *other than* THE FIELD on this body advertises the
   loss" cannot go stale the way "the marker lights below 95" can.
3. **The sweeps do not start at the pin.** The width sweep runs 60..159 --
   thirty-five columns below the pin and sixty-four above it, still
   crossing ``p``'s 99, so agreeing with either would show up as a
   measurement rather than an assumption. The height sweep runs 20..61 at
   the column pin, six rows under the row pin and thirty-five over.
4. **The row pin's own honesty is scoped, not implied.** None of THE FIELD,
   QUEUE, THROUGHPUT or JUST SHIPPED has a payload-independent content
   height (``SURF_SWARM_FULL_LAYOUT_ROWS``'s own ``#:`` block has the
   argument), so "whole from the pin" is asserted only against the
   committed capture -- the reference payload every swarm widget test
   already uses -- never against an arbitrarily busy swarm. A second,
   heavier payload is swept too, and its own claim is the opposite one: the
   marker keeps lighting rather than the body ever coming out silently
   short.
5. **A third measured exception, below the pin.** Below outer width 75
   (:data:`THROUGHPUT_NEVER_MARKS_BELOW` -- moved down from round one's 88
   when JUST SHIPPED's own floor shrank by exactly that much),
   THROUGHPUT's own column is under three cells -- too narrow to paint a
   CSS ellipsis or the bare ``‹`` glyph -- so a hash-and-chain-word pair it
   has already dropped internally can go both unmarked and un-clipped.
   Named and excluded from the "below the pin, something marks" property
   the same way THE FIELD's own exception is excluded from the "at the
   pin, nothing marks" one, and proven bounded in both directions by
   :func:`test_throughput_can_lose_its_presentation_silently_below_a_measured_width`.
   A narrower gap directly above that floor (title fits, glyph does not,
   now 75-86, previously 88-113) was closed instead of named -- see
   ``swarm_throughput.SurfSwarmThroughput._title_text`` and
   :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`'s own ``#:`` block for why that
   one could be fixed and the other two cannot.
6. **JUST SHIPPED's own exception did not just move again -- it is gone,
   and that is proven rather than assumed too.** Round 1 shipped it as an
   unbounded, always-lit marker; round 2 gave it THE FIELD's own bounded
   shape, clearing at a real, measured, reachable width (164). The
   2026-09-17 column-balance change removed the exception outright: JUST
   SHIPPED now clears at the ordinary column pin (95) the same way QUEUE
   and THROUGHPUT do, because it no longer shares unbounded growth with an
   uncapped THROUGHPUT past QUEUE's own new ceiling.
   :func:`test_the_shipped_panel_now_clears_with_the_rest_of_the_body`
   proves it the same two-sided way its predecessor proved permanence and
   then boundedness: marked one column under the pin (alongside
   THROUGHPUT, the pin's own binding pair now), clear at the pin. There is
   no ``SHIPPED_NEVER_CLEARS_BELOW`` constant any more; a reader looking
   for one should read this paragraph instead of assuming the name moved.

A named gap, found and closed in fix round 1, re-confirmed after both re-sweeps
--------------------------------------------------------------------------------
``SurfScreen._SCROLL_COLUMNS[MODE_SWARM]`` used to check only
``#surf-swarm-left`` and ``#surf-swarm-rail``, not ``#surf-swarm-body`` --
a placeholder Task 10 left in both CSS copies' own comments. A synthetic
worst case (light rail content, thirty JUST SHIPPED rows, no field/queue/
score stress at all) opened a genuine one-row-wide window at height 25,
eleven rows under the then-row-pin (42): the body's own container was
scrolling and cutting JUST SHIPPED's table while the screen-wide
``‹ taller`` stayed dark. That is the ``p`` body's own F6 shape, one
container over, and rows disappearing with nothing saying so is exactly
what the marker exists to prevent. (This "fix round 1" is Task 12's own,
dated 2026-09-16, and is unrelated to the layout-change review round dated
2026-09-17 that moved the column pin to 115 -- the two share a phrase, not
a date or a finding.)

**Closed by registering ``#surf-swarm-body`` in ``_SCROLL_COLUMNS[MODE_SWARM]``**,
the same shape ``_SCROLL_COLUMNS[MODE_POOL4_USER]`` already uses for
``#surf-pool4-user-body``, rather than by raising a floor (a floor only
moves the window; a different content mix reopens it, because none of this
body's panels has a payload-independent content height for a floor to sit
above -- see :data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s own ``#:`` block). The
2x2-grid restructure renamed the two rows (:data:`SWARM_TOP_ID`/
:data:`SWARM_BOTTOM_ID` for launch day's ``#surf-swarm-left``/
``#surf-swarm-rail``) but kept the same three-container registration, and
the same adversarial payload still reproduces a body-only-scrollbar window
at the row pin's own boundary (height 25) -- re-confirmed after both
re-sweeps rather than assumed to still hold.
``test_the_body_only_scrollbar_case_now_lights_the_marker`` reproduces it
and is the one test in this file with its own failing-first history: red
against the pre-fix code, green after the registration, red again with the
registration removed. ``test_no_height_loses_a_row_of_this_body_in_silence``
is the property version, swept over a band that includes height 25 on the
adversarial payload as well as the reference and heavy ones -- it now holds
everywhere this file checks, not merely at and above the row pin.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.screens.surf import (
    SURF_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
    SURF_SWARM_FULL_LAYOUT_COLUMNS,
    SURF_SWARM_FULL_LAYOUT_ROWS,
    SWARM_BODY_ID,
    SWARM_BOTTOM_ID,
    SWARM_TOP_ID,
    SurfScreen,
    TALLER_HINT,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmField,
    SurfSwarmQueue,
    SurfSwarmShipped,
    SurfSwarmThroughput,
)

# The screen-test module owns the payload fixtures and the themed harness.
# Imported rather than restated: a second copy of the capture would drift,
# and a pin measured against a private fixture is a pin measured against
# nothing the rest of the suite can see.
from tests.screens.test_surf_screen import (
    _css_clipped_lines,
    _frozen_payload,
    _region_text,
    _screen_text,
    _surf_app,
)

#: Independent literals for the same reason ``MEASURED_MARKET_COLUMNS`` is
#: one next door: a test that aliased the screen's constant would compare a
#: number against itself and pin nothing.
MEASURED_SWARM_COLUMNS = 95
MEASURED_SWARM_ROWS = 26

#: THE FIELD's own permanent exception (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s
#: own ``#:`` block): its ``‹`` never clears below this width, which is past
#: every other pin in this repo. Named here so the "whole" check can exclude
#: it explicitly rather than by silent construction. **246 -> 170 on
#: 2026-09-17** (the column-balance change): QUEUE's own new ``max-width``
#: cap means THE FIELD is the only unbounded panel left in its row, so it no
#: longer halves its growth with QUEUE above QUEUE's own ceiling -- the ratio
#: this comment used to describe as unmoved is exactly what moved.
FIELD_NEVER_CLEARS_BELOW = 170

#: JUST SHIPPED carried an exception of this same shape through three
#: rounds (most recently 164) and does not any more: the 2026-09-17
#: column-balance change (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own
#: ``#:`` block) made it whole exactly where the rest of the body is, so it
#: needs no constant here at all -- see
#: :func:`test_the_shipped_panel_now_clears_with_the_rest_of_the_body`.

#: THE FIELD's own permanent exception is the only one left within this
#: file's own width-sweep range, named so the "whole" check can exclude it
#: explicitly rather than by silent construction.
_EXCLUDED_FROM_WHOLE = {"SurfSwarmField"}

#: THROUGHPUT's own third, narrower exception (see
#: ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:`` block): below this outer
#: width THROUGHPUT's own column is under three cells, too narrow to paint a
#: CSS ellipsis or the bare ``‹`` glyph, so a hash-and-chain-word pair it has
#: already dropped internally can go both unmarked and un-clipped. Moved
#: from round one's 88 to 75 in the 2026-09-17 layout-change review round;
#: **unmoved by the same-dated column-balance round**, re-confirmed by
#: re-sweep rather than assumed: below this width neither QUEUE's nor
#: THROUGHPUT's own new ``max-width`` cap has been reached yet, so a bounded
#: ``1fr`` and the previous unbounded ``1fr`` occupy the identical column at
#: every width under it -- the cap only ever narrows growth above itself, it
#: never raises a floor below it. Measured, not assumed: 74 is silent on
#: both the committed capture and the heavy payload; 75 is caught (as a CSS
#: clip, not yet a marker -- the marker itself does not appear until width
#: 87, inside the excluded band, and that is fine: everything from 75 up is
#: already covered by ``clipped``).
#: Comfortably below :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`, so it can only
#: ever affect the "something marks below the pin" half of the property,
#: never the "nothing marks at or above it" half.
THROUGHPUT_NEVER_MARKS_BELOW = 75

#: The height every column-pin render below uses -- tall enough that no
#: payload this file sweeps by width ever needs its own row's scrollbar at
#: this height, so a width-sweep render never confounds a row-level marker
#: with a height-level one. Confirmed in situ: 80 rows clears every payload
#: this file sweeps by width, on the 2x2 grid exactly as it did on the
#: launch-day rail.
_COLUMN_SWEEP_HEIGHT = 80

_SWARM_CLASSES = {
    "SurfSwarmField": SurfSwarmField,
    "SurfSwarmQueue": SurfSwarmQueue,
    "SurfSwarmThroughput": SurfSwarmThroughput,
    "SurfSwarmShipped": SurfSwarmShipped,
}

_TS = 1_757_000_000.0


# ---------------------------------------------------------------------------
# Payloads -- the magnitudes the pins were swept against
# ---------------------------------------------------------------------------


def _heavy_swarm_payload() -> dict:
    """Five jobs, seven job states, eight blocked reasons, four scored
    agents, four shipped rows -- worst-case *cell* content, not merely worst
    row counts, used to confirm the column pin does not move with the data.
    """
    jobs = [
        ("job-A", "build the ERC-4626 vault", "build_contract_project",
         "implement", "accepted", 2, 1,
         "a review needs a contributor who did not author this work and has context"),
        ("job-B", "throughput panel review", "adversarial_review", "review",
         "waiting", None, 0, None),
        ("job-C", "scaffold a new dapp shell", "scaffold_project",
         "implement", "ready", 123456, 3,
         "runtime_error: node scaffold_project failed on the sandbox host"),
        ("job-D", "deploy launch artifact", "deploy_launch_artifact",
         "review", "failed", 42, 12,
         "blocked pending a second reviewer with no conflict of interest"),
        ("job-E", "publish ENS site record", "publish_site_record",
         "implement", "blocked", 7, 2, None),
    ]
    field_rows = []
    age = 30.0
    for job_id, objective, node_key, role, state, token, revisions, note in jobs:
        for i in range(2):
            field_rows.append({
                "job_id": job_id, "template": "surf-swarm-view",
                "objective": objective,
                "node_key": f"{node_key}_{i}" if i else node_key,
                "role": role, "node_state": state, "agent_token": token,
                "agent_id": f"agent-{token}" if token else None,
                "revisions": revisions, "dispatch_note": note,
                "moved_ts": _TS - age, "age_s": age,
            })
            age += 45.0

    queue_rows = [
        {"state": s, "count": c} for s, c in (
            ("executing", 4), ("waiting", 2), ("ready", 1), ("blocked", 3),
            ("completed", 19), ("cancelled", 2), ("failed", 1),
        )
    ]
    blocked_rows = [
        {"job_id": f"job-block-{i}", "template": "identity-md-fix",
         "reason": r, "moved_ts": _TS - 1200.0 - i * 60}
        for i, r in enumerate([
            "node scaffold_project: runtime_error",
            "waiting on review from a contributor who did not author this work",
            "blocked pending a second reviewer with no conflict of interest",
            "awaiting keeper confirmation on a stalled rebalance transaction",
            "node build_contract_project: compile_error in vault module",
            "waiting on a human decision about the launch artifact name",
            "blocked: dependency job has not completed yet",
            "node publish_site_record: ens_resolution_error",
        ])
    ]
    score_rows = [
        {"agent_id": f"agent-{i}", "agent_token": tok, "jobs_scored": js,
         "mean_score": ms, "last_tx_hash": "0x" + f"{i:02x}" * 32,
         "last_chain_id": chain}
        for i, (tok, js, ms, chain) in enumerate([
            (2, 12, 0.91, 11_155_111),
            (123456, 99, 100.0, 1),
            (7, 1, 0.0, 11_155_111),
            (None, 0, None, None),
        ])
    ]
    shipped_rows = [
        {"kind": "launch", "job_id": "job-4390",
         "label": "skill:build-contract-project", "commit": "a1b2c3d",
         "chain_id": 11_155_111,
         "address": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
         "tx_hash": "0x" + "11" * 32, "ens_name": None, "cid": None,
         "at_ts": _TS - 3600.0},
        {"kind": "site", "job_id": "job-4392", "label": "publish site",
         "commit": None, "chain_id": None, "address": None, "tx_hash": None,
         "ens_name": "swarm-artifact-fourteen.eth",
         "cid": "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi",
         "at_ts": _TS - 5400.0},
        {"kind": "delivery", "job_id": "job-4381",
         "label": "swarm queue panel implementation", "commit": "d4e5f6a1234",
         "chain_id": None, "address": None, "tx_hash": None,
         "ens_name": None, "at_ts": _TS - 7200.0},
        {"kind": "launch", "job_id": "job-4395", "label": "identity-md-fix",
         "commit": "b2c3d4e", "chain_id": 1, "address": None,
         "tx_hash": "0x" + "22" * 32, "ens_name": None, "cid": None,
         "at_ts": _TS - 9000.0},
    ]

    return _frozen_payload(
        swarm_agents_online=7, swarm_agents_enrolled=9, swarm_working_now=3,
        swarm_accepted_today=21, swarm_jobs_in_flight=4, swarm_jobs_blocked=1,
        swarm_services_up={
            "verifier": True, "publisher": False, "deployer": False,
        },
        swarm_field_rows=field_rows,
        swarm_queue_rows=queue_rows,
        swarm_blocked_rows=blocked_rows,
        swarm_shipped_rows=shipped_rows,
        swarm_score_rows=score_rows,
        swarm_throughput={
            "accepted_per_day": 3.0, "median_delivery_s": 5400.0,
            "revision_rate": 0.35, "window_days": 7,
        },
        swarm_network="SEPOLIA", swarm_as_of_hhmm="14:35",
        swarm_scores_as_of_hhmm="13:50", swarm_stale=False,
    )


def _many_shipped_payload(n: int) -> dict:
    rows = [
        {"kind": "launch", "job_id": f"job-{i}",
         "label": "skill:build-contract-project", "commit": "a1b2c3d",
         "chain_id": 11_155_111, "address": "0x" + f"{i:x}".rjust(40, "e"),
         "tx_hash": "0x" + "11" * 32, "ens_name": None, "cid": None,
         "at_ts": _TS - i * 60}
        for i in range(n)
    ]
    return _frozen_payload(swarm_shipped_rows=rows)


def _moderate_swarm_payload() -> dict:
    """A busy-but-ordinary day: still well short of :func:`_heavy_swarm_payload`."""
    field_rows = [
        {"job_id": f"job-{i}", "template": "t", "objective": f"objective {i}",
         "node_key": f"node_{i}", "role": "implement", "node_state": "ready",
         "agent_token": i, "agent_id": f"a-{i}", "revisions": 0,
         "dispatch_note": None, "moved_ts": _TS - i * 60, "age_s": i * 60.0}
        for i in range(3)
    ]
    queue_rows = [
        {"state": s, "count": c} for s, c in (
            ("executing", 4), ("waiting", 2), ("ready", 1), ("completed", 6),
        )
    ]
    blocked_rows = [
        {"job_id": f"job-b{i}", "template": "t", "reason": "waiting on review",
         "moved_ts": _TS - i * 90}
        for i in range(3)
    ]
    score_rows = [
        {"agent_id": f"agent-{i}", "agent_token": i, "jobs_scored": 5,
         "mean_score": 0.8, "last_tx_hash": "0x" + f"{i:02x}" * 32,
         "last_chain_id": 11_155_111}
        for i in range(2)
    ]
    shipped_rows = [
        {"kind": "launch", "job_id": f"job-s{i}", "label": "some launch",
         "commit": "abc1234", "chain_id": 11_155_111,
         "address": "0x" + f"{i:x}".rjust(40, "e"), "tx_hash": "0x" + "11" * 32,
         "ens_name": None, "cid": None, "at_ts": _TS - i * 300}
        for i in range(3)
    ]
    return _frozen_payload(
        swarm_field_rows=field_rows, swarm_queue_rows=queue_rows,
        swarm_blocked_rows=blocked_rows, swarm_score_rows=score_rows,
        swarm_shipped_rows=shipped_rows,
    )


def _shipped_heavy_light_rail_payload(n: int = 30) -> dict:
    """Minimal FIELD/QUEUE/THROUGHPUT content, a large JUST SHIPPED table.

    The one payload in this file built to *find* the named gap rather than
    to sweep past it: light content in the other three panels never lights
    either row's own scrollbar (:data:`SWARM_TOP_ID`/:data:`SWARM_BOTTOM_ID`,
    launch day's ``#surf-swarm-left``/``#surf-swarm-rail``), so if
    ``#surf-swarm-body`` alone needs to scroll, nothing in
    :data:`SurfScreen._SCROLL_COLUMNS` sees it. Kept its launch-day name
    (there is no rail on this body any more) because every call site already
    spells it and a rename buys nothing but a diff.
    """
    rows = [
        {"kind": "delivery", "job_id": f"job-{i}", "label": "swarm queue panel",
         "commit": "d4e5f6a", "chain_id": None, "address": None,
         "tx_hash": None, "ens_name": None, "at_ts": _TS - i * 60}
        for i in range(n)
    ]
    return _frozen_payload(
        swarm_field_rows=[{
            "job_id": "job-1", "template": "t", "objective": "x",
            "node_key": "n", "role": "implement", "node_state": "ready",
            "agent_token": 1, "agent_id": "a-1", "revisions": 0,
            "dispatch_note": None, "moved_ts": _TS, "age_s": 5.0,
        }],
        swarm_queue_rows=[{"state": "executing", "count": 1}],
        swarm_blocked_rows=[],
        swarm_score_rows=[],
        swarm_shipped_rows=rows,
    )


SWARM_PAYLOADS = {
    "capture": lambda: None,
    "heavy": _heavy_swarm_payload,
    "30-shipped": lambda: _many_shipped_payload(30),
    "50-shipped": lambda: _many_shipped_payload(50),
}


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def _swarm_widgets(screen) -> dict:
    """The `s` body's own four panels, resolved through the body container.

    Never ``screen.query_one(cls)`` -- ``_market_widgets``'s own reasoning
    applies just as much here: a pin measured on a widget resolved from the
    wrong body would be measuring a body that is not on screen.
    """
    body = screen.query_one(f"#{SWARM_BODY_ID}")
    out = {}
    for name, cls in _SWARM_CLASSES.items():
        found = list(body.query(cls))
        assert len(found) == 1, f"{name}: {len(found)} instances inside the body"
        out[name] = found[0]
    return out


def _swarm_marked(app, screen) -> set[str]:
    """Which swarm-body panels have a ``‹`` marker lit, by class name.

    ``‹`` rather than ``‹ widen``: these panels fall back to the bare glyph
    once the title no longer has room for the long spelling
    (``widgets/surf/_pool4.GLYPH_HINT``), and a check written against the
    long spelling alone would call a marked panel unmarked exactly where it
    is under the most pressure.
    """
    return {
        name
        for name, widget in _swarm_widgets(screen).items()
        if "‹" in _region_text(app, widget)
    }


def _swarm_clipped(app, screen) -> list[tuple[str, str]]:
    """Every composited line in the `s` body that CSS truncated."""
    out: list[tuple[str, str]] = []
    for name, widget in _swarm_widgets(screen).items():
        out.extend((name, body) for body in _css_clipped_lines(app, widget))
    return out


async def _render(payload, size):
    """Open the `s` body at *size* and hand back everything measured from it."""
    app = _surf_app(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        widgets = _swarm_widgets(screen)
        shipped_table = widgets["SurfSwarmShipped"].query_one("DataTable")
        body = screen.query_one(f"#{SWARM_BODY_ID}")
        top = screen.query_one(f"#{SWARM_TOP_ID}")
        bottom = screen.query_one(f"#{SWARM_BOTTOM_ID}")
        marked = _swarm_marked(pilot.app, screen)
        return {
            "marked": marked,
            "marked_besides_exceptions": marked - _EXCLUDED_FROM_WHOLE,
            "clipped": _swarm_clipped(pilot.app, screen),
            "shipped_hidden_cols": shipped_table.max_scroll_x,
            "taller": TALLER_HINT in _screen_text(pilot.app).split("\n")[0],
            "body_scroll": body.show_vertical_scrollbar,
            "top_scroll": top.show_vertical_scrollbar,
            "bottom_scroll": bottom.show_vertical_scrollbar,
        }


# ---------------------------------------------------------------------------
# The column pin
# ---------------------------------------------------------------------------


#: The width sweep, as an explicit ``(payload, width)`` list rather than two
#: crossed ``parametrize`` decorators, on the pool4-market file's own
#: precedent. The committed capture runs the whole 60..159 range; the
#: cell-content-heavy payload and the two large JUST SHIPPED tables run
#: fifteen columns either side of the pin (re-centred from 78..108 to
#: 113..143 when the pin moved 93 -> 128, to 100..130 when it moved to 115,
#: and to **80..110** when it moved again to 95 for the column-balance
#: change), the only band where a payload that moved the threshold could
#: show it.
_WIDTH_SWEEP = [("capture", w) for w in range(60, 160)] + [
    (name, w) for name in ("heavy", "30-shipped", "50-shipped")
    for w in range(80, 110)
]


@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP)
async def test_the_swarm_body_is_whole_from_its_pinned_width(
    payload_name, width
) -> None:
    """The sweep. THE FIELD's own exception is named, not implied; JUST
    SHIPPED carries none any more (see the module docstring's 2026-09-17
    column-balance section).

    **Whole means every panel but THE FIELD, plus no CSS-clipped line and
    no hidden ``DataTable`` column anywhere.** THE FIELD's own ``‹`` never
    clears below 170 columns (measured, not assumed -- see the constant's
    own ``#:`` block, and :data:`FIELD_NEVER_CLEARS_BELOW`); that threshold
    sits past this file's own 60-159 width-sweep range, so folding it into
    "whole" would mean no width in this sweep -- not even 159 -- could ever
    pass, which would make the property untestable rather than strict.
    Excluding it by name is what keeps this a property about the panels
    this pin can actually buy back columns for.

    Below the pin the claim is the marker's: something *other than* THE
    FIELD must be asking for the columns, or a line must be genuinely
    clipped -- **except below** :data:`THROUGHPUT_NEVER_MARKS_BELOW`,
    THROUGHPUT's own third, narrower named exception, where its column is
    too few cells wide to paint either signal at all.
    """
    r = await _render(SWARM_PAYLOADS[payload_name](), (width, _COLUMN_SWEEP_HEIGHT))
    if width >= SURF_SWARM_FULL_LAYOUT_COLUMNS:
        assert not r["marked_besides_exceptions"], (
            width, sorted(r["marked_besides_exceptions"])
        )
        assert not r["clipped"], (
            f"at {width} the s body is clipping a line and nothing on screen "
            f"says so: {r['clipped']}"
        )
        assert r["shipped_hidden_cols"] == 0, (
            f"{payload_name} at {width}: JUST SHIPPED's table hides "
            f"{r['shipped_hidden_cols']} column(s) behind a horizontal "
            "scroll with no marker"
        )
    elif width < THROUGHPUT_NEVER_MARKS_BELOW:
        pass
    else:
        assert r["marked_besides_exceptions"] or r["clipped"], (
            f"{payload_name} at {width}: nothing besides THE FIELD's own "
            "named exception advertises the loss"
        )


@pytest.mark.parametrize("payload_name", sorted(SWARM_PAYLOADS))
async def test_the_swarm_column_pin_does_not_move_with_the_payload(
    payload_name,
) -> None:
    """Every payload state, asked at the boundary rather than over the range."""
    pin = SURF_SWARM_FULL_LAYOUT_COLUMNS
    at = await _render(SWARM_PAYLOADS[payload_name](), (pin, _COLUMN_SWEEP_HEIGHT))
    under = await _render(SWARM_PAYLOADS[payload_name](), (pin - 1, _COLUMN_SWEEP_HEIGHT))
    assert not at["marked_besides_exceptions"], (payload_name, sorted(at["marked_besides_exceptions"]))
    assert not at["clipped"], (payload_name, at["clipped"])
    assert under["marked_besides_exceptions"] or under["clipped"], (
        f"{payload_name}: nothing besides THE FIELD's own exception asks "
        f"for a column at {pin - 1}, so the pin is loose for this payload"
    )


async def test_the_swarm_binding_panel_is_the_one_the_block_names() -> None:
    """Pinned by a test, not by a sentence, on both axes.

    **Two panels bind the column pin now, not one** (2026-09-17
    column-balance change): one column under it, both THROUGHPUT and JUST
    SHIPPED light ``‹`` at once -- they share the bottom row's own
    ``1fr``/``1fr`` seam, so whichever one is short of its own ``full``
    tier at this width is short together with the other, not
    independently. THROUGHPUT drops its transaction hash and chain word
    together, exactly the arithmetic :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`'s
    own ``#:`` block names; JUST SHIPPED falls one column short of its own
    ``full`` tier, the same tier its own former exception used to guard
    from a much narrower width. One row under the row pin, the **body
    itself** is the container that is scrolling, not either row -- both
    rows' own content fits inside their own floors, but the two floors
    summed ask for more than the body's own ``1fr`` share
    (:data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s own ``#:`` block has the
    argument).
    """
    at_col = await _render(
        _heavy_swarm_payload(), (SURF_SWARM_FULL_LAYOUT_COLUMNS - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert at_col["marked_besides_exceptions"] == {"SurfSwarmThroughput", "SurfSwarmShipped"}, (
        sorted(at_col["marked_besides_exceptions"])
    )

    at_row = await _render(
        None, (SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS - 1)
    )
    assert at_row["body_scroll"], "the body should be the one scrolling"
    assert not at_row["top_scroll"], (
        "THE FIELD/QUEUE row should not need to scroll at this payload"
    )
    assert not at_row["bottom_scroll"], (
        "the JUST SHIPPED/THROUGHPUT row should not need to scroll at this payload"
    )


async def test_the_shipped_panel_now_clears_with_the_rest_of_the_body() -> None:
    """The inverse of the claim this test replaced, proven the same
    two-sided way.

    Through three rounds (round 1's unbounded always-lit marker, round 2's
    bounded-but-still-164-wide exception) JUST SHIPPED needed its own
    wider threshold, separate from the body's own column pin. The
    2026-09-17 column-balance change removed that gap: JUST SHIPPED no
    longer shares growth with an unbounded THROUGHPUT above QUEUE's own new
    cap, so it now reaches its ``full`` tier at the same width the rest of
    the body does. One column short of the pin it is marked -- alongside
    THROUGHPUT, the pin's own binding pair now
    (:func:`test_the_swarm_binding_panel_is_the_one_the_block_names`) --
    and at the pin itself it is clear, so this is a property with a
    measured edge, not an unfalsifiable "always clear" claim either.
    """
    just_under = await _render(
        None, (SURF_SWARM_FULL_LAYOUT_COLUMNS - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert "SurfSwarmShipped" in just_under["marked"], (
        "JUST SHIPPED is not marked one column under the pin -- either the "
        "pin moved or JUST SHIPPED no longer binds it the way this file's "
        "own #: block claims"
    )

    at_pin = await _render(None, (SURF_SWARM_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmShipped" not in at_pin["marked"], (
        "JUST SHIPPED is still marked at the column pin -- its own "
        "exception is not actually gone and SURF_SWARM_FULL_LAYOUT_COLUMNS's "
        "own #: block needs its caveat rewritten, not just this test"
    )


async def test_throughput_can_lose_its_presentation_silently_below_a_measured_width() -> None:
    """THROUGHPUT's own third, narrower permanent exception, proven rather
    than narrated -- :data:`FIELD_NEVER_CLEARS_BELOW`'s own shape, one panel
    over.

    Below :data:`THROUGHPUT_NEVER_MARKS_BELOW` THROUGHPUT's own column is
    under three cells, too narrow to paint a CSS ellipsis or the bare ``‹``
    glyph, so a hash-and-chain-word pair it has already dropped internally
    goes both unmarked and un-clipped. One column above that boundary
    something is already caught (a CSS clip -- the marker itself needs more
    room still, and does not appear until width 87, which is why this test
    checks ``clipped`` at the boundary rather than ``marked``): the
    exception has a measured edge rather than being an unfalsifiable
    "always silent" claim.

    **Scoped to THROUGHPUT itself, not the body-wide ``marked_besides_
    exceptions``** (2026-09-17, column-balance change): at this width THE
    FIELD *and* JUST SHIPPED are both ordinarily marked too -- correctly,
    on the general "below the pin, something marks" property -- and JUST
    SHIPPED no longer carries its own excluded exception (the module
    docstring's "a fourth round" section), so the body-wide set is no
    longer a proxy for "THROUGHPUT alone said nothing" the way it was
    before that panel's own exception collapsed into the ordinary pin.
    """
    silent = await _render(
        _heavy_swarm_payload(), (THROUGHPUT_NEVER_MARKS_BELOW - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert "SurfSwarmThroughput" not in silent["marked"], sorted(silent["marked"])
    assert not any(name == "SurfSwarmThroughput" for name, _ in silent["clipped"]), (
        silent["clipped"]
    )

    caught = await _render(
        _heavy_swarm_payload(), (THROUGHPUT_NEVER_MARKS_BELOW, _COLUMN_SWEEP_HEIGHT)
    )
    assert caught["clipped"], (
        THROUGHPUT_NEVER_MARKS_BELOW,
        "nothing caught the loss at the boundary this constant names",
    )


def test_the_swarm_body_fits_inside_the_documented_app_width() -> None:
    """The standing rule, asserted rather than assumed: a body measured wider
    than ``__main__.FULL_LAYOUT_COLUMNS`` means shortening a value, never
    raising the app's number.

    THE FIELD's own permanent exception is exactly why this assertion is
    about the *pin* rather than about "every marker THE FIELD could ever
    show": chasing THE FIELD's own 170-column threshold would break this
    the moment it was tried, for every one of the assertions below.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    # Restored 2026-09-17 (the layout-change review round): the 2026-09-16
    # 2x2-grid re-sweep put this body's pin at 128, past
    # SURF_POOL4_USER_FULL_LAYOUT_COLUMNS (119), and this assertion was
    # removed rather than forced. Shortening JUST SHIPPED's own fixed width
    # (a tighter address/site window, `swarm_shipped.TIGHT_WIDTH`) brought
    # the pin back down to 115, under 119 again, so the relation is
    # reinstated -- it holds today because both numbers happen to say so,
    # not because one derives the other (terminal-layout skill's own
    # "coincidence with a date" note), and it will be removed again the day
    # it stops holding, not chased back into truth. The 2026-09-17
    # column-balance round moved the pin again, to 95 -- still under 119,
    # so the assertion stands unchanged, on the same coincidental terms.
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    # No relation is asserted against SURF_POOL4_FULL_LAYOUT_COLUMNS (99),
    # even though 95 <= 99 holds today: this body's own sweep is
    # independent of it and the two have never been compared.
    assert MEASURED_SWARM_COLUMNS == SURF_SWARM_FULL_LAYOUT_COLUMNS


async def test_the_field_panel_cannot_clear_its_own_full_tier_at_the_pinned_width() -> None:
    """THE FIELD's own permanent exception, proven rather than narrated.

    At the column pin THE FIELD is still marked -- confirming the exclusion
    in :func:`test_the_swarm_body_is_whole_from_its_pinned_width` is excusing
    a real, present condition rather than silently widening the property.
    One column short of :data:`FIELD_NEVER_CLEARS_BELOW` it is marked too;
    at that width it finally clears, so the exception has a measured edge
    rather than being an unfalsifiable "always marked" claim.
    """
    at_pin = await _render(None, (SURF_SWARM_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmField" in at_pin["marked"], (
        "THE FIELD cleared at the column pin -- if its own FULL_WIDTH "
        "threshold moved, SURF_SWARM_FULL_LAYOUT_COLUMNS's own #: block "
        "needs its caveat rewritten, not just this test"
    )

    just_under = await _render(None, (FIELD_NEVER_CLEARS_BELOW - 1, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmField" in just_under["marked"], (
        FIELD_NEVER_CLEARS_BELOW - 1, sorted(just_under["marked"]),
    )

    whole = await _render(None, (FIELD_NEVER_CLEARS_BELOW, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmField" not in whole["marked"], (
        FIELD_NEVER_CLEARS_BELOW, sorted(whole["marked"]),
    )


# ---------------------------------------------------------------------------
# The row pin
# ---------------------------------------------------------------------------


#: The height sweep: the committed capture over 20..61 (re-centred from
#: 24..60 when the pin moved 42 -> 26 -- six rows under the new pin and
#: thirty-five over, comfortably straddling it in both directions and
#: verified in situ against the render harness before being pinned), plus
#: the moderate and heavy payloads checked separately at the pin itself
#: (below) -- neither clears there (see :data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s
#: own ``#:`` block for why that is correct rather than a defect: the heavy
#: payload does not clear until height 48, well past this sweep's own
#: range), so their own claim is that the marker never goes quiet at the
#: pin, not that they reach "whole" inside this range.
_HEIGHT_SWEEP = [("capture", r) for r in range(20, 62)]


@pytest.mark.parametrize("payload_name,rows", _HEIGHT_SWEEP)
async def test_the_swarm_body_is_whole_from_its_pinned_height(
    rows, payload_name
) -> None:
    """150 columns is comfortably past the width pin, so nothing here is
    measuring a width.

    At and above the pin, on the reference capture, the screen-wide
    ``‹ taller`` is dark. Below it the marker is lit -- stated as a property
    of the pin rather than of one height, the same shape every other body's
    row-pin test uses.
    """
    r = await _render(SWARM_PAYLOADS[payload_name](), (150, rows))
    if rows >= SURF_SWARM_FULL_LAYOUT_ROWS:
        assert not r["taller"], (rows, payload_name)
    else:
        assert r["taller"], (
            f"{payload_name}: at {rows} rows the body claims to be whole "
            "one row under its own pin -- the pin is loose"
        )


@pytest.mark.parametrize("payload_name", ["moderate", "heavy"])
async def test_a_busier_swarm_still_lights_the_marker_at_the_pin(
    payload_name,
) -> None:
    """The row pin's own honesty, the other half of it.

    Neither a moderately busy day nor a genuinely heavy one is promised to
    fit at :data:`SURF_SWARM_FULL_LAYOUT_ROWS` -- see that constant's own
    ``#:`` block for why none of this body's panels has a payload-independent
    content height. What *is* promised is that the marker keeps reporting
    the overflow rather than ever going quiet on a swarm the reference
    payload did not anticipate.
    """
    payload = _moderate_swarm_payload() if payload_name == "moderate" else _heavy_swarm_payload()
    r = await _render(payload, (150, SURF_SWARM_FULL_LAYOUT_ROWS))
    assert r["taller"], (
        f"{payload_name}: the marker went quiet at the pin for a swarm "
        "busier than the reference payload -- if this payload now fits, "
        "that is real news for SURF_SWARM_FULL_LAYOUT_ROWS's own docstring, "
        "not a silent pass"
    )
    assert r["top_scroll"] or r["bottom_scroll"], (
        f"{payload_name}: some row should still be genuinely scrolling"
    )


async def test_the_body_only_scrollbar_case_now_lights_the_marker() -> None:
    """Fix round 1's own reproduction, at the exact case that found the gap.

    Before this fix, ``_SCROLL_COLUMNS[MODE_SWARM]`` checked only the two
    rows (launch day's ``#surf-swarm-left``/``#surf-swarm-rail``, today's
    :data:`SWARM_TOP_ID`/:data:`SWARM_BOTTOM_ID`), never ``#surf-swarm-body``
    itself. :func:`_shipped_heavy_light_rail_payload` starves both rows (one
    field row, one queue state, no blocked jobs, no scored agents) so
    neither row needs to scroll on its own, while a thirty-row JUST SHIPPED
    table gives the body itself something genuine to lose. At the column
    pin and height 25 the body was, and still is, genuinely scrolling
    (``show_vertical_scrollbar`` true) -- what changed is whether the
    screen-wide marker agrees.

    This test is its own failing-first record: it reddened against the
    pre-fix code (``taller`` false while ``body_scroll`` was true), passed
    once ``SWARM_BODY_ID`` was added to ``_SCROLL_COLUMNS[MODE_SWARM]``, and
    reddened again with that registration removed -- see the task's own
    report for the three runs.
    """
    r = await _render(_shipped_heavy_light_rail_payload(30),
                      (SURF_SWARM_FULL_LAYOUT_COLUMNS, 25))
    assert r["body_scroll"], (
        "the body should still be genuinely scrolling at this case -- if it "
        "is not, this test is no longer measuring the gap it was built for"
    )
    assert r["taller"], (
        "the body is scrolling and JUST SHIPPED is losing rows, but the "
        "screen-wide marker is dark -- the SWARM_BODY_ID registration is "
        "missing or was reverted"
    )


async def test_no_height_loses_a_row_of_this_body_in_silence() -> None:
    """The property fix round 1 closes: whenever the body's own container
    needs to scroll, the screen-wide marker says so -- everywhere this file
    checks, not merely at and above the row pin.

    Swept from six rows under the row pin (20, the bottom of this file's
    own height sweep, and below the height-25 case that found the gap) to
    seven over it, on the reference capture and the heavier payload, plus
    the adversarial light-rows/heavy-JUST-SHIPPED payload that found the gap
    in the first place. All three now agree at every height in range --
    confirmed against the pre-fix code, this range reddened at height 25 on
    the adversarial payload alone; it is green here only because it is run
    against the fix.
    """
    cases = [
        ("capture", SWARM_PAYLOADS["capture"]()),
        ("heavy", SWARM_PAYLOADS["heavy"]()),
        ("shipped-heavy-light-rail", _shipped_heavy_light_rail_payload(30)),
    ]
    for payload_name, payload in cases:
        for rows in range(SURF_SWARM_FULL_LAYOUT_ROWS - 6,
                          SURF_SWARM_FULL_LAYOUT_ROWS + 7):
            r = await _render(payload, (SURF_SWARM_FULL_LAYOUT_COLUMNS, rows))
            if r["body_scroll"]:
                assert r["taller"], (
                    payload_name, rows,
                    "the body is scrolling with the screen-wide marker dark"
                )


async def test_the_registration_does_not_light_the_marker_when_nothing_is_cut() -> None:
    """The other half of a marker fix: it must not cry wolf either.

    Registering ``#surf-swarm-body`` could in principle make ``‹ taller``
    fire on its own scrollbar appearing for a reason that costs no content --
    the repo's own cautionary case is ``DataTable.show_horizontal_scrollbar``,
    which goes true several columns before anything is actually lost. Swept
    well above the row pin, on the same adversarial payload that found the
    gap, the body's own scrollbar and the marker both go quiet together and
    stay quiet -- confirmed at every height in range, not merely the first
    one past the threshold.
    """
    payload = _shipped_heavy_light_rail_payload(30)
    for rows in range(SURF_SWARM_FULL_LAYOUT_ROWS, SURF_SWARM_FULL_LAYOUT_ROWS + 20):
        r = await _render(payload, (SURF_SWARM_FULL_LAYOUT_COLUMNS, rows))
        if not r["body_scroll"]:
            assert not r["taller"], (
                rows, "the marker is lit with nothing scrolling -- a false "
                "positive, report rather than silence it"
            )


# ---------------------------------------------------------------------------
# The key hint
# ---------------------------------------------------------------------------

KEY_HINT_PHRASE = "l launchpad · 4 pool4 · s swarm"


def test_the_key_hint_fits_the_status_bar_at_the_full_layout() -> None:
    assert SurfScreen.KEY_HINTS == f"[dim]{KEY_HINT_PHRASE}[/]"


async def test_the_key_hint_still_fits_below_the_full_layout_width() -> None:
    """The hint's own width has slack under the app-wide pin -- confirmed
    at the swarm body's own (narrower) column pin, not just at 143."""
    async with _surf_app(_frozen_payload()).run_test(
        size=(SURF_SWARM_FULL_LAYOUT_COLUMNS, 50)
    ) as pilot:
        await pilot.pause()
        assert KEY_HINT_PHRASE in _screen_text(pilot.app)
