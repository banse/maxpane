"""Measured PEPEPANE layout (spec §8 layout paragraph, §14 "Layout pins on textual 8.2.8").

The geometry invariants are ``test_surf_swarm_layout.py``'s: at and above the column pin **whole**
means no panel marked besides the named exception (LEDGER, plan deviation 7), no CSS-clipped line
(the hero's boxes ellipsise, so they count), no hidden ``DataTable`` column, no widget region past
its own row and a whole status bar; below it something other than the exception must advertise the
loss. At and above the row pin the screen-wide ``‹ taller`` is dark, the body does not scroll and no
panel's own line (e.g. CONFIG's skills footer) is laid out past the panel; below it, lit whenever it does.

Sizes are boundary sets (``tests/screens/_sweeps.py``): the band's ends, the pin ±1 and every
measured threshold ±1 -- never the pin alone (terminal-layout skill, "Certifying a pin").
``measure()`` at the bottom is the instrument that found the numbers in ``screens/seat.py``'s
``#:`` blocks; ``MEASURED_*`` restate them by hand so a pin cannot drift on its own.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from textual.widgets import DataTable, RichLog

from maxpane_dashboard.screens.seat import (
    BODY_ID,
    KEY_HINTS,
    LEDGER_NEVER_CLEARS_BELOW,
    ROW_IDS,
    SEAT_FULL_LAYOUT_COLUMNS,
    SEAT_FULL_LAYOUT_ROWS,
    TALLER_HINT,
    SeatScreen,
)
from maxpane_dashboard.screens.surf import TALLER_HINT as SURF_TALLER_HINT
from maxpane_dashboard.widgets.seat import SeatConfig, SeatCost, SeatHero, SeatLedgerTable, SeatLog, SeatMachine, SeatNow
from maxpane_dashboard.widgets.seat.ledger import COMPACT_WIDTH, FULL_WIDTH, TIGHT_WIDTH
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.swarm_table import SwarmTableBase
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens._sweeps import boundary_set
from tests.screens.test_surf_screen import _css_clipped_lines, _region_text, _screen_text, _status_bar_whole

# ---------------------------------------------------------------------------
# The measured numbers, restated by hand (a pin that moves without a re-sweep reddens the agreement test)
# ---------------------------------------------------------------------------

#: Filled by the executor from ``measure()`` (Step 3). The contract's starting values are 143 / 42 / 210.
MEASURED_SEAT_COLUMNS = 134
MEASURED_SEAT_ROWS = 50
MEASURED_LEDGER_CLEARS = 210

#: Tier edges the width sweep straddles (±1 each): the LEDGER's three tiers as screen widths (its
#: 3fr share of row 2 plus the gutter) and its clearance; ``measure()`` prints the in-situ onsets to add.
_GUTTER = SwarmTableBase.GUTTER_COLS
_THRESHOLDS = (LEDGER_NEVER_CLEARS_BELOW, MEASURED_LEDGER_CLEARS, 108, 134, 178)
_ROW_THRESHOLDS = (50,)

_EXCLUDED_FROM_WHOLE = {"SeatLedgerTable"}
_CONTAINER_OF = {SeatNow: ROW_IDS[0], SeatLog: ROW_IDS[0], SeatLedgerTable: ROW_IDS[1], SeatCost: ROW_IDS[1], SeatConfig: ROW_IDS[2], SeatMachine: ROW_IDS[2]}
_COLUMN_SWEEP_HEIGHT = 80
_ROW_SWEEP_WIDTH = 150
KEY_HINT_PHRASE = "c control · l log · h beats · enter detail"


# ---------------------------------------------------------------------------
# Payloads: the healthy fixture and the spec §14 worst case
# ---------------------------------------------------------------------------


def worst_payload() -> dict:
    """Spec §14: 20 ledger rows, a 400-char ``working:`` sentence, 31 skills, 3 orphans, every hero box populated, 40 log lines."""
    flat = _seat_payload()
    base = flat["seat_tasks_rows"][0]
    flat["seat_tasks_rows"] = [dict(copy.deepcopy(base), key=f"7/{i:08x}/2026-09-26T03:{i % 60:02d}:00.000Z", nodeId8=f"{i:08x}",
                                    turns=1234, tokens={"input": 9_999_999, "output": 999_999, "cached": 99_999_999, "cacheWrite": 0},
                                    verdictLagS=86_399, outcome=("accepted", "rejected", "failed", "pending")[i % 4],
                                    failureReason="local_build_failed" if i % 4 == 2 else None, repair=i % 5 == 0, resent=i % 7 == 0, sessionFiles=3)
                               for i in range(20)]
    flat["seat_tasks_window"] = dict(flat["seat_tasks_window"], rows=291)
    flat["seat_current"] = {"nodeId8": "0c1f9727", "jobId": base["jobId"], "role": "integrate", "kind": "code", "phase": "repairing", "startedUtc": "2026-09-26T03:39:30Z",
                            "elapsedS": 3599, "maxTurns": 120, "model": "gpt-6-astra", "tierDerived": "premium", "lastMessage": "x" * 400,
                            "lastMessageUtc": "2026-09-26T03:40:10Z", "planeSince": "2026-09-26T03:39:27Z", "objective": "o" * 200, "nodeKey": "build_contract_project"}
    flat["seat_daemon_running"] = 1
    flat["seat_daemon_work"] = "1 task running"
    flat["seat_skills_rows"] = [{"id": f"skill-with-a-long-name-{i:02d}", "on": i % 3 != 0, "needs": "network" if i % 4 == 0 else ("tool:forge" if i % 5 == 0 else None)} for i in range(31)]
    flat["seat_skills_offered"] = 31
    flat["seat_skills_on"] = 21
    orphan = {"pid": 64861, "pgid": 64861, "uid": 1000, "cgroup": "user-0.slice/session-147.scope", "ageS": 127000, "rssB": 130000000, "cmd": "codex exec --json",
              "pgidMembers": [{"pid": 64855, "uid": 0, "cgroup": "user-0.slice/session-147.scope", "cmd": "runuser"}]}
    flat["seat_machine_orphans"] = [dict(orphan, pid=orphan["pid"] + i) for i in range(3)]
    flat["seat_release_available"] = "0.1.0+5c1d2e3f"
    flat["seat_auth_degraded"] = True
    flat["seat_auth_reasons"] = ["paused after 3 failed runs", "api_error 401", "token refreshed 23:38 (not read)"]
    flat["seat_auth_credential_file_mtime_utc"] = "2026-09-25T23:38:43Z"
    flat["seat_hero_state"] = "amber"
    flat["seat_today_tasks"], flat["seat_today_stored"], flat["seat_today_not_stored"] = 999, 998, 1
    flat["seat_standing_attempts"], flat["seat_standing_accepted"] = 99_999, 88_888
    flat["seat_log_lines"] = [{"seq": i, "ts": f"2026-09-26T03:{i % 60:02d}:00.000Z", "kind": "phase", "invocation": None, "cursor": None,
                               "text": f"2026-09-26T03:{i % 60:02d}:00.000Z   working: " + "w" * 160} for i in range(1, 41)]
    flat["seat_log_seq"] = 40
    return flat


def unattributed_payload() -> dict:
    flat = worst_payload()
    flat.update(seat_current=None, seat_daemon_running=3)
    return flat


PAYLOADS = {"healthy": _seat_payload, "worst": worst_payload, "unattributed": unattributed_payload}


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def _overflow(screen, widgets: dict) -> list[tuple[str, int]]:
    out = []
    for cls, row_id in _CONTAINER_OF.items():
        container = screen.query_one(f"#{row_id}")
        c, w = container.region, widgets[cls.__name__].region
        over = max(w.x + w.width - (c.x + c.width), 0) + max(c.x - w.x, 0)
        if not screen.query_one(f"#{BODY_ID}").show_vertical_scrollbar:
            over += max(w.y + w.height - (c.y + c.height), 0) + max(c.y - w.y, 0)
        if over:
            out.append((cls.__name__, over))
    return out


def _child_overflow(widgets: dict) -> list[tuple[str, str]]:
    """A displayed direct child of a panel laid out past the panel's own bottom edge -- a line lost in silence.

    ``_overflow`` compares a panel with its row; this compares each painting child with its panel (e.g.
    ``#seat-cfg-skills-footer`` at y=18 of an 18-row CONFIG). ``Widget.region`` of a child laid out outside the
    viewport is still its layout region (textual's ``find_widget`` falls back to the full map), so it is seen here.
    """
    out = []
    for name, panel in widgets.items():
        p = panel.region
        for child in panel.children:
            c = child.region
            if child.display and c.height and c.y + c.height > p.y + p.height:
                out.append((name, child.id or type(child).__name__))
    return out


async def _render(payload: dict, size: tuple[int, int]) -> dict:
    app = _seat_app(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        widgets = {cls.__name__: screen.query_one(cls) for cls in _CONTAINER_OF}
        hero = screen.query_one(SeatHero)
        marked = {name for name, w in widgets.items() if "‹" in _region_text(pilot.app, w)}
        hidden = {name: w.query_one(DataTable).max_scroll_x for name, w in widgets.items() if list(w.query(DataTable))}
        clipped = [(name, line) for name, w in widgets.items() for line in _css_clipped_lines(pilot.app, w)]
        clipped += [("SeatHero", line) for line in _css_clipped_lines(pilot.app, hero)]
        hero_marked = "‹" in _region_text(pilot.app, hero)
        hero_cut = "…" in _region_text(pilot.app, hero)
        bar = screen.query_one(StatusBar)
        bar_line = _screen_text(pilot.app).split("\n")[bar.region.y]
        return {
            "marked": marked,
            "marked_besides_exceptions": marked - _EXCLUDED_FROM_WHOLE,
            "hero_marked": hero_marked,
            "hero_cut": hero_cut,
            "hidden": hidden,
            "clipped": clipped,
            "overflow": _overflow(screen, widgets),
            "child_overflow": _child_overflow(widgets),
            "taller": TALLER_HINT in _screen_text(pilot.app).split("\n")[0],
            "scroll": screen.query_one(f"#{BODY_ID}").show_vertical_scrollbar,
            "status_whole": KEY_HINT_PHRASE in bar_line and _status_bar_whole(pilot.app),
            "ledger_tier": widgets["SeatLedgerTable"]._tier,
            "heights": {name: w.region.height for name, w in widgets.items()},
        }


def _assert_whole(r: dict, where: str) -> None:
    assert r["status_whole"], (where, "status bar cropped")
    assert not r["marked_besides_exceptions"], (where, sorted(r["marked_besides_exceptions"]))
    assert not r["hero_marked"] and not r["hero_cut"], (where, "a hero box was cut")
    assert not r["clipped"], f"{where}: a line is CSS-clipped and nothing says so: {r['clipped']}"
    assert not any(r["hidden"].values()), f"{where}: a table hides columns behind a horizontal scroll: {r['hidden']}"
    assert not r["overflow"], f"{where}: a panel's region extends past its row: {r['overflow']}"


# ---------------------------------------------------------------------------
# The column pin
# ---------------------------------------------------------------------------

_WIDTH_SWEEP = [(name, w) for name in PAYLOADS for w in boundary_set(SEAT_FULL_LAYOUT_COLUMNS, 100, 230, *_THRESHOLDS)]


@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP, ids=lambda v: str(v))
async def test_the_body_is_whole_from_its_pinned_width(payload_name, width) -> None:
    r = await _render(PAYLOADS[payload_name](), (width, _COLUMN_SWEEP_HEIGHT))
    where = f"{payload_name} at {width}"
    assert not r["overflow"], f"{where}: {r['overflow']}"
    if width >= SEAT_FULL_LAYOUT_COLUMNS:
        _assert_whole(r, where)
    else:
        assert r["marked_besides_exceptions"] or r["hero_marked"] or r["clipped"] or any(r["hidden"].values()), (
            f"{where}: nothing besides the named exception advertises the loss")


@pytest.mark.parametrize("payload_name", sorted(PAYLOADS))
async def test_the_column_pin_is_not_loose(payload_name) -> None:
    """One column under the pin something other than the LEDGER must mark or clip -- on at least one payload."""
    below = await _render(PAYLOADS[payload_name](), (SEAT_FULL_LAYOUT_COLUMNS - 1, _COLUMN_SWEEP_HEIGHT))
    at = await _render(PAYLOADS[payload_name](), (SEAT_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT))
    _assert_whole(at, f"{payload_name} at the pin")
    if payload_name == "worst":
        assert below["marked_besides_exceptions"] or below["hero_marked"] or below["hero_cut"] or below["clipped"], "the pin is loose: the previous column is whole too"


@pytest.mark.parametrize("width", [LEDGER_NEVER_CLEARS_BELOW - 1, LEDGER_NEVER_CLEARS_BELOW, LEDGER_NEVER_CLEARS_BELOW + 1])
async def test_the_ledger_clears_where_its_block_says(width) -> None:
    r = await _render(_seat_payload(), (width, _COLUMN_SWEEP_HEIGHT))
    if width >= LEDGER_NEVER_CLEARS_BELOW:
        assert "SeatLedgerTable" not in r["marked"] and r["ledger_tier"] == "full", (width, r["ledger_tier"])
    else:
        assert "SeatLedgerTable" in r["marked"]


async def test_the_ledger_never_hides_a_column_at_any_swept_width() -> None:
    # Only at and above the column pin: the ladder bottoms out at ``tight`` (64 cells) and ``rowfit.tier_for``
    # returns that last tier even where it does not fit, so below ~110 columns (LEDGER panel < 64 cells) the table
    # scrolls sideways -- an advertised loss below the pin, which ``test_the_body_is_whole_from_its_pinned_width``
    # already accepts. From the pin up the LEDGER is the named *mark* exception, never a hidden-column one.
    widths = [w for w in boundary_set(SEAT_FULL_LAYOUT_COLUMNS, 100, 230, *_THRESHOLDS) if w >= SEAT_FULL_LAYOUT_COLUMNS]
    assert widths, "the sweep must reach the pin"
    for width in widths:
        r = await _render(worst_payload(), (width, _COLUMN_SWEEP_HEIGHT))
        assert not r["hidden"].get("SeatLedgerTable"), (width, "the LEDGER sheds a tier, it never scrolls sideways")


# ---------------------------------------------------------------------------
# The row pin
# ---------------------------------------------------------------------------

_HEIGHT_SWEEP = [(name, h) for name in PAYLOADS for h in boundary_set(SEAT_FULL_LAYOUT_ROWS, 24, 70, *_ROW_THRESHOLDS)]


@pytest.mark.parametrize("payload_name,rows", _HEIGHT_SWEEP, ids=lambda v: str(v))
async def test_the_body_is_whole_from_its_pinned_height(payload_name, rows) -> None:
    r = await _render(PAYLOADS[payload_name](), (_ROW_SWEEP_WIDTH, rows))
    where = f"{payload_name} at {rows} rows"
    if rows >= SEAT_FULL_LAYOUT_ROWS:
        assert not r["taller"] and not r["scroll"], (where, "the body scrolls at or above the row pin")
        assert not r["child_overflow"], (where, "a panel's line is laid out past the panel", r["child_overflow"])
    else:
        assert r["taller"] == r["scroll"], (where, "the marker disagrees with the body's scrollbar")
    for name, height in r["heights"].items():
        assert height >= 3, (where, name, "a panel lost its title row in silence")


async def test_the_row_pin_holds_at_the_column_pin_too() -> None:
    for name, build in PAYLOADS.items():
        r = await _render(build(), (SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS))
        assert not r["taller"] and not r["scroll"], (name, "the row pin is measured at 150 columns; it must hold at the column pin")
        assert not r["child_overflow"], (name, r["child_overflow"])


async def test_the_row_pin_is_not_loose() -> None:
    below = await _render(worst_payload(), (SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS - 1))
    assert below["taller"] and below["scroll"], "one row below must advertise the loss"


async def test_long_raw_log_rows_have_a_scrollbar_and_remain_accessible() -> None:
    payload = worst_payload()
    payload["seat_log_lines"][-1]["text"] += " END-SCROLLBACK"
    async with _seat_app(payload).run_test(size=(SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        panel = pilot.app.screen.query_one(SeatLog)
        log = panel.query_one(RichLog)
        assert log.max_scroll_x > 0 and log.show_horizontal_scrollbar
        assert "END-SCROLLBACK" in log.lines[-1].text
        log.scroll_to(x=log.max_scroll_x, animate=False, immediate=True)
        await pilot.pause()
        assert "END-SCROLLBACK" in _region_text(pilot.app, panel)


# ---------------------------------------------------------------------------
# Agreement: the pins are the measured numbers; the hint spellings are the repo's
# ---------------------------------------------------------------------------


def test_the_pins_are_the_measured_numbers() -> None:
    assert SEAT_FULL_LAYOUT_COLUMNS == MEASURED_SEAT_COLUMNS
    assert SEAT_FULL_LAYOUT_ROWS == MEASURED_SEAT_ROWS
    assert LEDGER_NEVER_CLEARS_BELOW == MEASURED_LEDGER_CLEARS > SEAT_FULL_LAYOUT_COLUMNS
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH


def test_the_taller_hint_is_the_repo_spelling() -> None:
    # contract §C.16: restated, never imported from surf; bound here
    assert TALLER_HINT == SURF_TALLER_HINT == "‹ taller"
    assert SeatScreen.KEY_HINTS == KEY_HINTS == f"[dim]{KEY_HINT_PHRASE}[/]"


# ---------------------------------------------------------------------------
# The instrument (not a test): prints the onsets the #: blocks record
# ---------------------------------------------------------------------------


async def _first_whole_width(payload: dict, lo: int = 100, hi: int = 230) -> int | None:
    """The smallest width from which every width up to *hi* is whole (walking down from *hi*)."""
    onset = None
    for width in range(hi, lo - 1, -1):
        r = await _render(payload, (width, _COLUMN_SWEEP_HEIGHT))
        try:
            _assert_whole(r, str(width))
        except AssertionError:
            break
        onset = width
    return onset


async def _first_whole_height(payload: dict, lo: int = 24, hi: int = 70) -> int | None:
    onset = None
    for rows in range(hi, lo - 1, -1):
        r = await _render(payload, (_ROW_SWEEP_WIDTH, rows))
        if r["taller"] or r["scroll"] or r["child_overflow"]:
            break
        onset = rows
    return onset


async def _ledger_clearance(payload: dict, lo: int = 140, hi: int = 260) -> int | None:
    onset = None
    for width in range(hi, lo - 1, -1):
        r = await _render(payload, (width, _COLUMN_SWEEP_HEIGHT))
        if "SeatLedgerTable" in r["marked"] or r["ledger_tier"] != "full":
            break
        onset = width
    return onset


async def measure() -> dict:
    out: dict = {}
    for name, build in PAYLOADS.items():
        out[f"columns/{name}"] = await _first_whole_width(build())
        out[f"rows/{name}"] = await _first_whole_height(build())
    out["ledger_clears/healthy"] = await _ledger_clearance(_seat_payload())
    return out


if __name__ == "__main__":  # pragma: no cover -- `.venv/bin/python -m tests.screens.test_seat_layout`
    print(asyncio.run(measure()))
