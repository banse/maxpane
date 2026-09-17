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

Six things this file exists to pin above the rest
----------------------------------------------------
1. **The column pin fails in both directions**, once THE FIELD's and JUST
   SHIPPED's own exceptions are set aside. THE FIELD's ``‹`` never clears
   below 246 columns and JUST SHIPPED's own never clears below 164 (both
   measured, not assumed -- see each constant's own ``#:`` block); both
   thresholds sit past this file's own 70-159 width-sweep range, so within
   that range both panels are *expected* to keep marking, and a sweep that
   demanded "no marker anywhere" would never find a pin at all. "Whole"
   here therefore means "no marker outside those two named exceptions, and
   no CSS-clipped line, and no hidden DataTable column" -- and that claim
   is checked in both directions, exactly the way every other body's own
   pin is.
2. **The claims are properties, never literals**, with both exceptions
   named rather than silently absorbed: "whenever a row would clip, some
   panel *other than* THE FIELD or JUST SHIPPED on this body advertises
   the loss" cannot go stale the way "the marker lights below 115" can.
3. **The sweeps do not start at the pin.** The width sweep runs 70..159 --
   forty-five columns below the pin and forty-four above it, crossing
   ``p``'s 99, so agreeing with it would show up as a measurement rather
   than an assumption. The height sweep runs 20..61 at the column pin, six
   rows under the row pin and thirty-five over.
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
6. **JUST SHIPPED's own exception is bounded, not permanent, and proven
   both ways.** Round 1 shipped it as an unbounded, always-lit marker;
   review round 2 gave it the same shape THE FIELD's exception already
   has -- a real, measured, *reachable* width (164) above which the
   marker genuinely goes dark. :data:`SHIPPED_NEVER_CLEARS_BELOW` names
   it and
   :func:`test_the_shipped_panel_cannot_clear_its_own_full_tier_at_the_pinned_width`
   proves both edges: marked at the pin, marked one column under 164,
   clear at 164 -- THE FIELD's own test shape, reused rather than
   invented fresh, replacing the earlier (round 1) test that proved the
   wrong claim (permanence).

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
MEASURED_SWARM_COLUMNS = 115
MEASURED_SWARM_ROWS = 26

#: THE FIELD's own permanent exception (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s
#: own ``#:`` block): its ``‹`` never clears below this width, which is past
#: every other pin in this repo. Named here so the "whole" check can exclude
#: it explicitly rather than by silent construction. Unmoved by either
#: re-sweep: THE FIELD still shares a halved 1fr:1fr seam with QUEUE alone,
#: and that ratio was never touched.
FIELD_NEVER_CLEARS_BELOW = 246

#: JUST SHIPPED's own exception, added in the 2026-09-17 layout-change
#: review round 1 and given THE FIELD's own bounded shape in review round 2
#: (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:`` block): its ``‹``
#: never clears below this width, past this file's own 70-159 width-sweep
#: range, exactly the reason THE FIELD's own exception is named rather than
#: chased. Round 1 shipped this as an *unbounded* always-lit marker (a bare
#: fixed CSS width, never regrowing); round 2 replaced the fixed width with
#: ``1fr`` bounded by ``min-width``/``max-width``, so this now has a real,
#: reachable upper edge the way :data:`FIELD_NEVER_CLEARS_BELOW` always
#: did -- :func:`test_the_shipped_panel_cannot_clear_its_own_full_tier_at_the_pinned_width`
#: proves it rather than merely asserting it here.
SHIPPED_NEVER_CLEARS_BELOW = 164

#: Both panels whose own ``‹`` never clears within this file's own 70-159
#: width-sweep range, named so the "whole" check can exclude them
#: explicitly rather than by silent construction. THE FIELD's own
#: threshold (246) and JUST SHIPPED's own (164,
#: :data:`SHIPPED_NEVER_CLEARS_BELOW`) are both real, measured, reachable
#: widths -- neither panel is stuck the way JUST SHIPPED was for one round
#: on 2026-09-17 -- they are simply past what this file's main sweep
#: covers, on THE FIELD's own long-standing precedent.
_EXCLUDED_FROM_WHOLE = {"SurfSwarmField", "SurfSwarmShipped"}

#: THROUGHPUT's own third, narrower exception (see
#: ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:`` block): below this outer
#: width THROUGHPUT's own column is under three cells, too narrow to paint a
#: CSS ellipsis or the bare ``‹`` glyph, so a hash-and-chain-word pair it has
#: already dropped internally can go both unmarked and un-clipped. Moved
#: from round one's 88 to 75 in the 2026-09-17 layout-change review round,
#: thirteen columns down -- exactly JUST SHIPPED's own new saving (81 -> 68),
#: confirmed by re-sweep rather than shifted by arithmetic. Measured, not
#: assumed: 74 is silent on both the committed capture and the heavy
#: payload; 75 is caught (as a CSS clip, not yet a marker -- the marker
#: itself does not appear until width 87, inside the excluded band, and
#: that is fine: everything from 75 up is already covered by ``clipped``).
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
#: precedent. The committed capture runs the whole 70..159 range; the
#: cell-content-heavy payload and the two large JUST SHIPPED tables run the
#: fifteen columns either side of the pin (re-centred from 78..108 to
#: 113..143 when the pin moved 93 -> 128, then to 100..130 when the pin
#: moved again to 115), the only band where a payload that moved the
#: threshold could show it.
_WIDTH_SWEEP = [("capture", w) for w in range(70, 160)] + [
    (name, w) for name in ("heavy", "30-shipped", "50-shipped")
    for w in range(100, 130)
]


@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP)
async def test_the_swarm_body_is_whole_from_its_pinned_width(
    payload_name, width
) -> None:
    """The sweep. THE FIELD's and JUST SHIPPED's own exceptions are named,
    not implied.

    **Whole means every panel but THE FIELD and JUST SHIPPED, plus no
    CSS-clipped line and no hidden ``DataTable`` column anywhere.** THE
    FIELD's own ``‹`` never clears below 246 columns and JUST SHIPPED's own
    never clears below 164 (both measured, not assumed -- see each
    constant's own ``#:`` block); both thresholds sit past this file's own
    70-159 width-sweep range, so folding either into "whole" would mean no
    width in this sweep -- not even 159 -- could ever pass, which would
    make the property untestable rather than strict. Excluding them by name
    is what keeps this a property about the panels this pin can actually
    buy back columns for.

    Below the pin the claim is the marker's: something *other than* THE
    FIELD or JUST SHIPPED must be asking for the columns, or a line must be
    genuinely clipped -- **except below** :data:`THROUGHPUT_NEVER_MARKS_BELOW`,
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
            f"{payload_name} at {width}: nothing besides THE FIELD's and "
            "JUST SHIPPED's own named exceptions advertises the loss"
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
        f"{payload_name}: nothing besides THE FIELD's and JUST SHIPPED's own "
        f"exceptions asks for a column at {pin - 1}, so the pin is loose for "
        "this payload"
    )


async def test_the_swarm_binding_panel_is_the_one_the_block_names() -> None:
    """Pinned by a test, not by a sentence, on both axes.

    One column under the column pin, THROUGHPUT is the only panel besides
    THE FIELD's and JUST SHIPPED's own permanent exceptions that lights
    ``‹`` -- it drops the transaction hash and its chain word together,
    exactly the arithmetic :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`'s own
    ``#:`` block names. One row under the row pin, the **body itself** is
    the container that is scrolling, not either row -- both rows' own
    content fits inside their own floors, but the two floors summed ask
    for more than the body's own ``1fr`` share
    (:data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s own ``#:`` block has the
    argument).
    """
    at_col = await _render(
        _heavy_swarm_payload(), (SURF_SWARM_FULL_LAYOUT_COLUMNS - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert at_col["marked_besides_exceptions"] == {"SurfSwarmThroughput"}, (
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


async def test_the_shipped_panel_cannot_clear_its_own_full_tier_at_the_pinned_width() -> None:
    """JUST SHIPPED's own exception, proven rather than narrated --
    :data:`FIELD_NEVER_CLEARS_BELOW`'s own shape, one panel over, and a very
    different claim from the one review round 1 shipped: round 1 gave
    JUST SHIPPED a bare fixed CSS width, which meant its own ``‹`` marker
    was lit at *every* terminal size with no upper edge -- a lit marker
    carrying no information, since widening never changed anything.
    Review round 2 replaced the fixed width with ``1fr`` bounded by
    ``min-width``/``max-width``, so this threshold now has a genuine,
    reachable upper edge the way THE FIELD's own always has.

    At the column pin JUST SHIPPED is still marked -- confirming the
    exclusion in :func:`test_the_swarm_body_is_whole_from_its_pinned_width`
    is excusing a real, present condition (the ``tight`` tier, still bound
    by its own ``min-width``) rather than silently widening the property.
    One column short of :data:`SHIPPED_NEVER_CLEARS_BELOW` it is marked
    too; at that width it finally clears (``full`` tier, ``self.size.width``
    reaches ``swarm_shipped.FULL_WIDTH``), so the exception has a measured
    edge rather than being an unfalsifiable "always marked" claim.
    """
    at_pin = await _render(None, (SURF_SWARM_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmShipped" in at_pin["marked"], (
        "JUST SHIPPED cleared at the column pin -- if its own tight-tier "
        "min-width threshold moved, SURF_SWARM_FULL_LAYOUT_COLUMNS's own "
        "#: block needs its caveat rewritten, not just this test"
    )

    just_under = await _render(None, (SHIPPED_NEVER_CLEARS_BELOW - 1, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmShipped" in just_under["marked"], (
        SHIPPED_NEVER_CLEARS_BELOW - 1, sorted(just_under["marked"]),
    )

    whole = await _render(None, (SHIPPED_NEVER_CLEARS_BELOW, _COLUMN_SWEEP_HEIGHT))
    assert "SurfSwarmShipped" not in whole["marked"], (
        SHIPPED_NEVER_CLEARS_BELOW, sorted(whole["marked"]),
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
    """
    silent = await _render(
        _heavy_swarm_payload(), (THROUGHPUT_NEVER_MARKS_BELOW - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert not silent["marked_besides_exceptions"], sorted(silent["marked_besides_exceptions"])
    assert not silent["clipped"], silent["clipped"]

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
    show": chasing THE FIELD's own 246-column threshold would break this
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
    # it stops holding, not chased back into truth.
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    # No relation is asserted against SURF_POOL4_FULL_LAYOUT_COLUMNS (99):
    # this body's own sweep is independent of it and the two have never
    # been compared.
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
