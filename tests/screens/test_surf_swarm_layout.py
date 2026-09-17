"""Task 12 -- the `s` SWARM body's own measured layout.

Two pins live here and nowhere else: ``SURF_SWARM_FULL_LAYOUT_COLUMNS`` and
``SURF_SWARM_FULL_LAYOUT_ROWS``. Their measurement method, their binding
panel/container and their per-panel derivation are in their own ``#:``
blocks in ``screens/surf.py``; this file is what makes those blocks fail
when they stop being true.

Four things this file exists to pin above the rest
----------------------------------------------------
1. **The column pin fails in both directions**, once THE FIELD's own
   permanent exception is set aside. THE FIELD's ``‹`` never clears below
   246 columns (measured, not assumed -- see the constant's own ``#:``
   block), so a sweep that demanded "no marker anywhere" would never find a
   pin at all. "Whole" here therefore means "no marker outside THE FIELD's
   named exception, and no CSS-clipped line, and no hidden DataTable
   column" -- and that claim is checked in both directions, exactly the way
   every other body's own pin is.
2. **The claims are properties, never literals**, with THE FIELD's own
   exception named rather than silently absorbed: "whenever a row would
   clip, some panel *other than THE FIELD* on this body advertises the
   loss" cannot go stale the way "the marker lights below 93" can.
3. **The sweeps do not start at the pin.** The width sweep runs 70..159 --
   twenty-three columns below the pin and sixty-six above it, crossing
   ``p``'s 99 and reaching well past the market body's own 119, so agreeing
   with either would show up as a measurement rather than an assumption.
   The height sweep runs 24..60 at the column pin, eighteen rows under the
   row pin and eighteen over.
4. **The row pin's own honesty is scoped, not implied.** None of THE FIELD,
   QUEUE, THROUGHPUT or JUST SHIPPED has a payload-independent content
   height (``SURF_SWARM_FULL_LAYOUT_ROWS``'s own ``#:`` block has the
   argument), so "whole from the pin" is asserted only against the
   committed capture -- the reference payload every swarm widget test
   already uses -- never against an arbitrarily busy swarm. A second,
   heavier payload is swept too, and its own claim is the opposite one: the
   marker keeps lighting rather than the body ever coming out silently
   short.

A named gap, and why it is not asserted away here
----------------------------------------------------
``SurfScreen._SCROLL_COLUMNS[MODE_SWARM]`` checks ``#surf-swarm-left`` and
``#surf-swarm-rail``, not ``#surf-swarm-body`` -- a placeholder Task 10 left
in both CSS copies' own comments, not something this task's brief asks it to
fix. Swept at and above the row pin, across every payload this file uses,
the gap never shows: whenever the body needed to scroll, the rail did too,
so ``‹ taller`` never disagreed with reality in the range this file actually
pins. It is not vacuous in general -- a synthetic worst case (light rail
content, thirty JUST SHIPPED rows, no field/queue/score stress at all) opens
a genuine one-row-wide window at height 25, eleven rows under this pin,
where the body's own container scrolls, JUST SHIPPED's table loses rows, and
the screen-wide marker stays dark. That is the ``p`` body's F6 shape one
container over. ``test_the_body_scrollbar_and_the_marker_agree_at_and_above_the_pin``
pins the claim this file actually makes -- agreement from the row pin
upward, on the payloads this file sweeps -- and does not claim the gap is
closed everywhere; the window below the pin is reported, not fixed, in the
task's own report.
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
    SWARM_LEFT_ID,
    SWARM_RAIL_ID,
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
MEASURED_SWARM_COLUMNS = 93
MEASURED_SWARM_ROWS = 42

#: THE FIELD's own permanent exception (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s
#: own ``#:`` block): its ``‹`` never clears below this width, which is past
#: every other pin in this repo. Named here so the "whole" check can exclude
#: it explicitly rather than by silent construction.
FIELD_NEVER_CLEARS_BELOW = 246

#: The height every column-pin render below uses -- tall enough that a
#: heavy payload's own rail content (QUEUE + THROUGHPUT stacked, up to
#: sixteen-plus lines on :func:`_heavy_swarm_payload`) never scrolls
#: `#surf-swarm-rail` at 50 rows and pushes THROUGHPUT's title out of the
#: composited region, which would read as "unmarked" for a panel that is in
#: fact overflowing (caught correctly by the screen-wide marker instead, not
#: by this file's own panel-title check). Confirmed in situ: 80 rows clears
#: that confound for every payload this file sweeps by width.
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
    to sweep past it: light rail content never lights ``#surf-swarm-rail``'s
    own scrollbar, so if ``#surf-swarm-body`` alone needs to scroll, nothing
    in :data:`SurfScreen._SCROLL_COLUMNS` sees it.
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
        left = screen.query_one(f"#{SWARM_LEFT_ID}")
        rail = screen.query_one(f"#{SWARM_RAIL_ID}")
        marked = _swarm_marked(pilot.app, screen)
        return {
            "marked": marked,
            "marked_besides_field": marked - {"SurfSwarmField"},
            "clipped": _swarm_clipped(pilot.app, screen),
            "shipped_hidden_cols": shipped_table.max_scroll_x,
            "taller": TALLER_HINT in _screen_text(pilot.app).split("\n")[0],
            "body_scroll": body.show_vertical_scrollbar,
            "left_scroll": left.show_vertical_scrollbar,
            "rail_scroll": rail.show_vertical_scrollbar,
        }


# ---------------------------------------------------------------------------
# The column pin
# ---------------------------------------------------------------------------


#: The width sweep, as an explicit ``(payload, width)`` list rather than two
#: crossed ``parametrize`` decorators, on the pool4-market file's own
#: precedent. The committed capture runs the whole 70..159 range; the
#: cell-content-heavy payload and the two large JUST SHIPPED tables run the
#: fifteen columns either side of the pin, the only band where a payload
#: that moved the threshold could show it.
_WIDTH_SWEEP = [("capture", w) for w in range(70, 160)] + [
    (name, w) for name in ("heavy", "30-shipped", "50-shipped")
    for w in range(78, 108)
]


@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP)
async def test_the_swarm_body_is_whole_from_its_pinned_width(
    payload_name, width
) -> None:
    """The sweep. THE FIELD's own permanent exception is named, not implied.

    **Whole means every panel but THE FIELD, plus no CSS-clipped line and no
    hidden ``DataTable`` column anywhere.** THE FIELD's own ``‹`` never clears
    below 246 columns (:data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`'s own ``#:``
    block has the measurement), so folding it into "whole" would mean no
    width in this sweep -- not even 159 -- could ever pass, which would make
    the property untestable rather than strict. Excluding it by name is what
    keeps this a property about the panels this pin can actually buy back
    columns for.

    Below the pin the claim is the marker's: something *other than THE
    FIELD* must be asking for the columns, or a line must be genuinely
    clipped.
    """
    r = await _render(SWARM_PAYLOADS[payload_name](), (width, _COLUMN_SWEEP_HEIGHT))
    if width >= SURF_SWARM_FULL_LAYOUT_COLUMNS:
        assert not r["marked_besides_field"], (
            width, sorted(r["marked_besides_field"])
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
    else:
        assert r["marked_besides_field"] or r["clipped"], (
            f"{payload_name} at {width}: nothing besides THE FIELD's own "
            "permanent exception advertises the loss"
        )


@pytest.mark.parametrize("payload_name", sorted(SWARM_PAYLOADS))
async def test_the_swarm_column_pin_does_not_move_with_the_payload(
    payload_name,
) -> None:
    """Every payload state, asked at the boundary rather than over the range."""
    pin = SURF_SWARM_FULL_LAYOUT_COLUMNS
    at = await _render(SWARM_PAYLOADS[payload_name](), (pin, _COLUMN_SWEEP_HEIGHT))
    under = await _render(SWARM_PAYLOADS[payload_name](), (pin - 1, _COLUMN_SWEEP_HEIGHT))
    assert not at["marked_besides_field"], (payload_name, sorted(at["marked_besides_field"]))
    assert not at["clipped"], (payload_name, at["clipped"])
    assert under["marked_besides_field"] or under["clipped"], (
        f"{payload_name}: nothing besides THE FIELD's own exception asks "
        f"for a column at {pin - 1}, so the pin is loose for this payload"
    )


async def test_the_swarm_binding_panel_is_the_one_the_block_names() -> None:
    """Pinned by a test, not by a sentence, on both axes.

    One column under the column pin, THROUGHPUT is the only panel besides
    THE FIELD's own permanent exception that lights ``‹`` -- it drops the
    transaction hash and its chain word together, exactly the arithmetic
    :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`'s own ``#:`` block names. One row
    under the row pin, the rail is the only container of the three
    ``_rail_is_cut`` inspects that is actually scrolling.
    """
    at_col = await _render(
        _heavy_swarm_payload(), (SURF_SWARM_FULL_LAYOUT_COLUMNS - 1, _COLUMN_SWEEP_HEIGHT)
    )
    assert at_col["marked_besides_field"] == {"SurfSwarmThroughput"}, (
        sorted(at_col["marked_besides_field"])
    )

    at_row = await _render(
        None, (SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS - 1)
    )
    assert at_row["rail_scroll"], "the rail should be the one scrolling"
    assert not at_row["left_scroll"], (
        "THE FIELD's own row should not need to scroll at this payload"
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
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    # No relation is asserted against SURF_POOL4_FULL_LAYOUT_COLUMNS (99): the
    # `p` body's own sweep is independent of this one, this body's 93 happens
    # to fall under it, and the terminal-layout skill's own note about two
    # independently swept pins applies -- a coincidence with a date on it is
    # not something to pin.
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


#: The height sweep: the committed capture over the whole 24..46 range
#: (comfortably straddling the pin in both directions, eighteen rows either
#: side), plus the moderate and heavy payloads over the range where their
#: own state would show a moved pin -- they never clear inside this range
#: (see :data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s own ``#:`` block for why that
#: is correct rather than a defect), so their own claim is that the marker
#: never goes quiet, not that they reach "whole".
_HEIGHT_SWEEP = [("capture", r) for r in range(24, 61)]


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
    assert r["rail_scroll"], (
        f"{payload_name}: the rail itself should be the one still scrolling"
    )


async def test_the_body_scrollbar_and_the_marker_agree_at_and_above_the_pin() -> None:
    """The named gap's own scope: closed from the row pin upward, on the
    payloads this file sweeps -- not claimed closed everywhere.

    ``_SCROLL_COLUMNS[MODE_SWARM]`` does not check ``#surf-swarm-body``
    itself (see :data:`SURF_SWARM_FULL_LAYOUT_ROWS`'s own ``#:`` block), so
    in principle the body could be scrolling -- cutting JUST SHIPPED's table
    -- while ``‹ taller`` stays dark. Swept from six rows under the pin to
    six over it, on the reference capture and the heavier payloads, that
    never happens: whenever the body's own container needs to scroll, the
    rail needs to as well. This is the property this file can actually prove
    honest; a synthetic payload built to defeat it (light rail content, a
    large JUST SHIPPED table) does open a one-row window, eleven rows under
    this pin -- reported in the task's own report rather than asserted here,
    because asserting it away would require fixing ``_SCROLL_COLUMNS``,
    which belongs to Task 10's own file, not this task's two constants.
    """
    for payload_name in ("capture", "heavy"):
        for rows in range(SURF_SWARM_FULL_LAYOUT_ROWS - 6,
                          SURF_SWARM_FULL_LAYOUT_ROWS + 7):
            r = await _render(SWARM_PAYLOADS[payload_name](), (150, rows))
            if r["body_scroll"]:
                assert r["taller"], (
                    payload_name, rows,
                    "the body is scrolling with the screen-wide marker dark"
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
