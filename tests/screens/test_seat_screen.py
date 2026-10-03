"""``SeatScreen`` (spec §8 layout paragraph, §14 "Widgets/screen"; contract §C.16).

The screen declares its seven panels as ``PANELS`` and writes no lifecycle method; the
shared walks (``test_dashboard_screen.py`` PANELS agreement, ``test_refresh_guard.py``
guard, the address sweep) collect it through ``tests/address_sweep/builders.CASES``.
Here: compose, ids, bindings, the title line and the four key actions.
"""

from __future__ import annotations

import re
from pathlib import Path

from textual.widgets import DataTable

import maxpane_dashboard
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES
from maxpane_dashboard.screens import seat as seat_mod
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.screens.seat import (
    BODY_ID,
    HERO_ID,
    INITIAL_TITLE,
    KEY_HINTS,
    BODY_IDS,
    TALLER_HINT,
    TITLE_BAR_ID,
    SeatScreen,
    title_line,
)
from maxpane_dashboard.screens.seat_control import SeatControlScreen
from maxpane_dashboard.screens.seat_task_detail import SeatTaskDetail
from maxpane_dashboard.widgets.seat import (SeatConfig, SeatCost, SeatHero, SeatLedgerTable, SeatLog, SeatMachine, SeatNow,
    SeatJob, SeatOutputTokens, SeatSkills, SeatRecords, SeatNodes, SeatControl, SeatGate, SeatAudit)
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens.test_seat_control import _broker  # the FakeBroker factory with the plan/apply/verify/audit responses

TCSS = Path(maxpane_dashboard.__file__).parent / "themes" / "minimal.tcss"
SIZE = (170, 60)


def _text(pilot) -> str:
    return "\n".join("".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips())


def test_the_screen_declares_data_not_control_flow():
    assert issubclass(SeatScreen, DashboardScreen)
    assert SeatScreen.GAME_NAME == "PEPEPANE" and SeatScreen.REFRESH_WORKER_NAME == "seat-refresh"
    for name in ("on_screen_resume", "on_screen_suspend", "_do_refresh", "_do_initial_refresh", "_schedule_refresh", "action_refresh"):
        assert name not in vars(SeatScreen), name
    assert [cls for cls, _ in SeatScreen.PANELS] == [SeatHero, SeatNow, SeatJob, SeatLog, SeatMachine, SeatCost, SeatOutputTokens, SeatLedgerTable,
        SeatConfig, SeatSkills, SeatRecords, SeatNodes, SeatControl, SeatGate, SeatAudit]
    for cls, adapt in SeatScreen.PANELS:
        assert tuple(adapt({})) == SEAT_WIDGET_SIGNATURES[cls.__name__], cls.__name__
    assert {b.key for b in SeatScreen.BINDINGS} == set("123456crdsSboDxh nfmw".replace(" ", "")) | {"escape", "enter", "space", "tab"}
    assert not next(b for b in SeatScreen.BINDINGS if b.key == "enter").priority
    assert set(KEY_HINTS) == set(BODY_IDS)
    assert TALLER_HINT == "‹ taller" and (TITLE_BAR_ID, HERO_ID, BODY_ID) == ("seat-title-bar", "seat-hero", "seat-body")
    assert len(BODY_IDS) == 6


def test_seat_default_css_uses_only_seat_ids():
    # spec §8 layout / §14 Widgets-screen: fresh ids so surf's #title-bar/#middle-row rules never apply; nothing in the tcss
    ids = set(re.findall(r"#([A-Za-z0-9_-]+)", SeatScreen.DEFAULT_CSS))
    assert ids and all(i.startswith("seat-") for i in ids), sorted(ids)
    assert "#seat-" not in TCSS.read_text(encoding="utf-8") and "SeatScreen" not in TCSS.read_text(encoding="utf-8")
    for selector in re.findall(r"^\s*([A-Za-z#.][^{}]*)\{", SeatScreen.DEFAULT_CSS, flags=re.M):
        assert selector.strip().startswith(("SeatScreen", "#seat-", "Seat")), selector


def test_title_line_names_the_seat_the_host_and_the_clock():
    flat = _seat_payload()
    line = title_line(flat, row_hint=False)
    assert line.startswith("PEPEPANE · IDMD #7 · systemd · as of ") and TALLER_HINT not in line
    assert TALLER_HINT in title_line(flat, row_hint=True)
    assert title_line({}, row_hint=False) == "PEPEPANE · IDMD #-- · -- · as of --:--"
    assert title_line({**flat, "seat_offline": True}, row_hint=False).endswith("· [dim]offline[/]")


async def test_compose_mounts_every_panel_once_and_a_refresh_fills_them():
    app = _seat_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, SeatScreen)
        for widget_id in (TITLE_BAR_ID, HERO_ID, BODY_ID, *BODY_IDS.values()):
            screen.query_one(f"#{widget_id}")
        for cls, _ in SeatScreen.PANELS:
            assert len(list(screen.query(cls))) == 1, cls.__name__
        await screen._do_refresh()
        await pilot.pause()
        text = _text(pilot)
        assert "IDMD #7" in text and "safe to restart" in text and "0c1f9727" in text and "CONFIG & SKILLS" in text and "JOB" in text
        assert text.split("\n")[0].strip().startswith("PEPEPANE · IDMD #7 · systemd · as of ")
        bar = screen.query_one(StatusBar)
        assert "h beats" in _text(pilot).split("\n")[bar.region.y]


async def test_the_taller_marker_lights_when_the_body_scrolls():
    async with _seat_app().run_test(size=(150, 24)) as pilot:
        await pilot.pause()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT in _text(pilot).split("\n")[0]
        assert pilot.app.screen._body_is_cut()


async def test_c_selects_control_and_escape_returns_to_live():
    async with _seat_app().run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatScreen)
        assert pilot.app.screen.selected_dashboard == "CONTROL"
        assert "[r] restart — safe to restart" in _text(pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.screen.selected_dashboard == "LIVE"


async def test_h_collapses_live_heartbeat_lines():
    async with _seat_app().run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("h")
        await pilot.pause()
        assert "heartbeats hidden" in _text(pilot)


async def test_enter_opens_the_detail_when_the_ledger_table_has_focus():
    # RowSelected handles a focused table; Enter remains non-priority for the shared confirm Input.
    async with _seat_app().run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        table = screen.query_one("#seat-ledger-table", DataTable)
        table.focus()
        await pilot.pause()
        assert pilot.app.focused is table
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatTaskDetail)


async def test_enter_with_no_ledger_row_opens_nothing():
    payload = _seat_payload()
    payload["seat_tasks_rows"] = []
    app = _seat_app(payload)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatScreen)


def test_the_initial_title_and_the_pins_are_declared():
    assert INITIAL_TITLE == "PEPEPANE · connecting…"
    assert isinstance(seat_mod.SEAT_FULL_LAYOUT_COLUMNS, int) and isinstance(seat_mod.SEAT_FULL_LAYOUT_ROWS, int)
    assert not hasattr(seat_mod, "LEDGER_NEVER_CLEARS_BELOW")
    assert seat_mod.SEAT_FULL_LAYOUT_COLUMNS == max(w for w, _ in seat_mod.SEAT_BODY_PINS.values())
    assert seat_mod.SEAT_FULL_LAYOUT_ROWS == max(h for _, h in seat_mod.SEAT_BODY_PINS.values())
