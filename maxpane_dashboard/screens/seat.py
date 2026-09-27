"""PEPEPANE: the one dashboard of the pepepane fork (spec §8 layout; contract §C.16).

Hero row (six boxes) over a 2+2+2 body -- row 1 NOW | LOG, row 2 LEDGER | COST,
row 3 CONFIG & SKILLS | MACHINE -- with the status bar docked below. The screen
declares its panels as :attr:`SeatScreen.PANELS` and writes no lifecycle method:
``DashboardScreen`` owns resume/suspend/refresh, and
``tests/screens/test_dashboard_screen.py`` walks the rows against ``compose`` and
against every widget's real ``update_data`` signature.

**CSS lives here only** (spec §15 decision): fresh ids (``#seat-title-bar``,
``#seat-hero``, ``#seat-body``, ``#seat-row-N``) so surf's ``#title-bar``/``#middle-row``
rules never apply; ``SeatApp`` loads the shared ``themes/minimal.tcss`` for the
theme, base-widget and ``panels.py`` rules, and nothing seat-specific is appended
to that sheet. Every id in :attr:`SeatScreen.DEFAULT_CSS` starts with ``seat-``
(``tests/screens/test_seat_screen.py::test_seat_default_css_uses_only_seat_ids``).

**Layout pins** :data:`SEAT_FULL_LAYOUT_COLUMNS` / :data:`SEAT_FULL_LAYOUT_ROWS`
are **measured** by ``tests/screens/test_seat_layout.py`` on textual 8.2.8 and
recorded in their ``#:`` blocks; LEDGER is the body's named width exception
(:data:`LEDGER_NEVER_CLEARS_BELOW`). ``‹ taller`` rides the title bar when the
body scrolls (surf's ``_rail_is_cut`` shape, with the one deferred re-check).
"""

from __future__ import annotations

import logging

from rich.text import Text
from rich.markup import escape

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.seat_control import SeatControlScreen
from maxpane_dashboard.screens.seat_task_detail import SeatTaskDetail
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.seat import SeatConfig, SeatCost, SeatHero, SeatLedgerTable, SeatLog, SeatMachine, SeatNow
from maxpane_dashboard.widgets.status_bar import StatusBar

__all__ = [
    "BODY_ID", "HERO_ID", "INITIAL_TITLE", "KEY_HINTS", "LEDGER_NEVER_CLEARS_BELOW", "ROW_IDS", "SEAT_FULL_LAYOUT_COLUMNS",
    "SEAT_FULL_LAYOUT_ROWS", "TALL_ROW_CLASS", "TALLER_HINT", "TITLE_BAR_ID", "SeatScreen", "title_line",
]

logger = logging.getLogger(__name__)

#: PEPEPANE full-layout width, measured 2026-09-27 on textual 8.2.8.
#: Both healthy and spec §14 worst payloads first stay whole at 134 columns,
#: measured downward from 230 through 100 in the real screen containers.
#: COST binds: at 133 it marks ‹ widen; at 134 only the named LEDGER exception
#: marks. No hero clipping, hidden table columns, CSS-clipped line, row overflow
#: or cropped status bar remains at the pin. The same pin holds at 50 rows.
#: Six hero boxes remain 1fr; NOW/LOG 2:3, LEDGER/COST 3:2, CONFIG/MACHINE 1:1.
#: The body reserves its scrollbar gutter, so height does not change this seam.
#: The boundary certificate straddles 108 (tight table fits), 134 (body clears),
#: 178 (compact tier), and 210 (full tier), plus the 100/230 band endpoints.
#: LOG is raw unbounded scrollback: its own horizontal scrollbar advertises long
#: lines and keeps their full redacted text accessible; it has no fixed row budget.
SEAT_FULL_LAYOUT_COLUMNS = 134

#: PEPEPANE full-layout height, measured 2026-09-27 on textual 8.2.8.
#: Both healthy and worst payloads first stay whole at 50 rows, measured down
#: from 70 through 24 at 150 columns and checked again at the column pin.
#: At 49 the body scrolls and the screen-wide ‹ taller is lit; at 50 both are
#: dark and no direct painting child lies below its panel. CONFIG binds row 3:
#: twelve facts + title/blank + four-row skills table + its footer need 19 rows.
#: Row floors are NOW/LOG 7, LEDGER/COST 14 and CONFIG/MACHINE 19; title 1,
#: hero 7 plus bottom margin 1, and status bar 1 complete the measured height.
#: The worst payload includes 31 skills, 20 ledger rows, 40 long log lines,
#: three orphans and all hero states; unbounded tables/logs scroll internally.
#: Boundary tests straddle 50 and the 24/70 endpoints; a tightness test rejects
#: a larger pin even when every at-or-above geometry assertion would pass.
SEAT_FULL_LAYOUT_ROWS = 50

#: LEDGER full-tier clearance, measured 2026-09-27 on textual 8.2.8.
#: Healthy fixture: first continuously full at 210 terminal columns (downward
#: sweep from 260). At 209 it still marks; 210 and 211 show all ten columns.
#: The full tier costs 123 content cells plus table gutter inside its 3fr share.
#: Actual in-situ transitions: tight ceases horizontal scrolling at 108;
#: compact begins at 178; full begins at 210. The body pin uses tight and an
#: honest ‹ widen. Hidden columns remain forbidden from the body pin upward.
#: Width boundary sets straddle each onset for healthy and worst payloads;
#: the exception is the LEDGER mark, never hidden columns or region overflow.
LEDGER_NEVER_CLEARS_BELOW = 210

#: Restated from ``screens/surf.py`` (never imported from there -- the fork touches no surf module);
#: bound by ``tests/screens/test_seat_layout.py::test_the_taller_hint_is_the_repo_spelling``.
TALLER_HINT = "‹ taller"

TITLE_BAR_ID = "seat-title-bar"
HERO_ID = "seat-hero"
BODY_ID = "seat-body"
ROW_IDS = ("seat-row-1", "seat-row-2", "seat-row-3")
#: ``l`` puts this on row 1 so the LOG gets two shares of the body.
TALL_ROW_CLASS = "seat-row-tall"
KEY_HINTS = "[dim]c control · l log · h beats · enter detail[/]"
INITIAL_TITLE = "PEPEPANE · connecting…"


def title_line(data: dict, *, row_hint: bool) -> str:
    """``PEPEPANE · IDMD #7 · systemd · as of HH:MM`` plus the row marker and the offline word.

    Built from an int token, our own host word and a clock: nothing third-party, nothing to escape.
    """
    token = data.get("seat_token_id")
    token_word = str(token) if isinstance(token, int) and not isinstance(token, bool) else DASH
    kind = data.get("seat_host_kind") if isinstance(data.get("seat_host_kind"), str) else DASH
    as_of = data.get("seat_as_of_hhmm") if isinstance(data.get("seat_as_of_hhmm"), dict) else {}
    clock = as_of.get("tail") if isinstance(as_of.get("tail"), str) else "--:--"
    line = f"PEPEPANE · IDMD #{token_word} · {escape(kind)} · as of {escape(clock)}"
    if row_hint:
        line += f" · [yellow]{TALLER_HINT}[/]"
    if data.get("seat_offline") is True:
        line += " · [dim]offline[/]"
    return line


class SeatScreen(DashboardScreen):
    """The PEPEPANE dashboard -- see the module docstring."""

    GAME_NAME = "PEPEPANE"
    REFRESH_WORKER_NAME = "seat-refresh"

    BINDINGS = [
        Binding("c", "control", "Control", show=False),
        Binding("l", "toggle_log", "Log", show=False),
        Binding("h", "toggle_heartbeats", "Heartbeats", show=False),
        # priority: a focused LEDGER DataTable binds enter to select_cursor and would swallow it (spec §8 LEDGER Enter).
        Binding("enter", "task_detail", "Detail", show=False, priority=True),
    ]

    #: The key-hint line (module constant bound as a class attribute; Task 8.13 reads ``SeatScreen.KEY_HINTS``).
    KEY_HINTS = KEY_HINTS

    #: Only ``#seat-*`` ids and ``Seat*`` type selectors (spec §8; the test binds it). Rows are
    #: ``1fr`` with floors equal to their tallest panel's fixed lines, so no panel shrinks under
    #: its content; the body scrolls and ``‹ taller`` says so (terminal-layout skill).
    SCOPED_CSS = False
    DEFAULT_CSS = """
    SeatScreen #seat-title-bar {
        width: 100%;
        height: 1;
        content-align: center middle;
        text-align: center;
        background: $surface;
        color: $text-muted;
        text-style: bold;
        padding: 0 2;
    }
    SeatScreen #seat-hero {
        height: 7;
        margin: 0 0 1 0;
    }
    SeatScreen #seat-body {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SeatScreen #seat-row-1 { height: 1fr; min-height: 7; }
    SeatScreen #seat-row-1.seat-row-tall { height: 2fr; }
    SeatScreen #seat-row-2 { height: 1fr; min-height: 14; }
    SeatScreen #seat-row-3 { height: 1fr; min-height: 19; }
    SeatScreen SeatNow { width: 2fr; height: 100%; }
    SeatScreen SeatLog { width: 3fr; height: 100%; }
    SeatScreen SeatLedgerTable { width: 3fr; height: 100%; }
    SeatScreen SeatCost { width: 2fr; height: 100%; }
    SeatScreen SeatConfig { width: 1fr; height: 100%; }
    SeatScreen SeatMachine { width: 1fr; height: 100%; }
    
    SeatHero {
        height: 7;
        padding: 0 1 0 0;
    }
    SeatHero > SeatHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center top;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SeatHero.seat-hero-green > #seat-hero-live { border: solid $success; }
    SeatHero.seat-hero-amber > #seat-hero-live { border: solid $warning; }
    SeatHero.seat-hero-red > #seat-hero-live { border: solid $error; }
    
    SeatNow > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    
    SeatLog > RichLog {
        height: 1fr;
    }
    SeatLog > #seat-log-footer {
        height: 1;
    }
    
    SeatConfig > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SeatConfig > DataTable {
        height: 1fr;
        min-height: 4;
    }
    SeatConfig > #seat-cfg-skills-footer {
        height: 1;
    }
    
    SeatMachine > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    
    SeatCost > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SeatCost > SeatCostSpark {
        height: 3;
    }
    
    SeatControlScreen { align: center middle; padding: 1 0; }
    SeatControlScreen #seat-control-box { width: 100%; max-width: 120; height: 100%; border: solid $accent; padding: 0 2; }
    SeatControlScreen #seat-control-title { height: 1; margin: 0 0 1 0; }
    SeatControlScreen #seat-control-scroll { height: 1fr; min-height: 4; overflow-x: hidden; }
    SeatControlScreen #seat-control-scroll Static { height: auto; width: 100%; }
    SeatControlScreen #seat-control-static { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-plan { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-status { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-input { height: 3; margin: 1 0 0 0; }
    SeatControlScreen #seat-control-audit { height: auto; max-height: 6; margin: 1 0 0 0; }
    """

    PANELS = (
        (SeatHero, keys(*SEAT_WIDGET_SIGNATURES["SeatHero"])),
        (SeatNow, keys(*SEAT_WIDGET_SIGNATURES["SeatNow"])),
        (SeatLog, keys(*SEAT_WIDGET_SIGNATURES["SeatLog"])),
        (SeatLedgerTable, keys(*SEAT_WIDGET_SIGNATURES["SeatLedgerTable"])),
        (SeatCost, keys(*SEAT_WIDGET_SIGNATURES["SeatCost"])),
        (SeatConfig, keys(*SEAT_WIDGET_SIGNATURES["SeatConfig"])),
        (SeatMachine, keys(*SEAT_WIDGET_SIGNATURES["SeatMachine"])),
    )

    def __init__(self, manager, poll_interval: int = 5, name: str | None = None, **kwargs) -> None:
        super().__init__(manager, poll_interval, name=name, **kwargs)
        #: The last folded payload (plan deviation 13): the CONTROL modal opens on the facts the hero shows.
        self._last_payload: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static(Text(INITIAL_TITLE), id=TITLE_BAR_ID)
        yield SeatHero(id=HERO_ID)
        with Vertical(id=BODY_ID):
            with Horizontal(id=ROW_IDS[0]):
                yield SeatNow()
                yield SeatLog()
            with Horizontal(id=ROW_IDS[1]):
                yield SeatLedgerTable()
                yield SeatCost()
            with Horizontal(id=ROW_IDS[2]):
                yield SeatConfig()
                yield SeatMachine()
        yield StatusBar()

    # -- hooks ----------------------------------------------------------------

    def _prime_status_bar(self, bar: StatusBar) -> None:
        bar.set_key_hints(KEY_HINTS)

    def _update_title(self, data: dict) -> None:
        self._last_payload = data
        self._render_title()

    def on_resize(self, _event=None) -> None:
        self.call_after_refresh(self._render_title)

    def _body_is_cut(self) -> bool:
        try:
            return bool(self.query_one(f"#{BODY_ID}").show_vertical_scrollbar)
        except Exception:  # noqa: BLE001 -- not composed yet, or torn down
            return False

    def _render_title(self, _recheck: bool = True) -> None:
        """The title from the last payload plus the row marker, re-checked once (surf's boundary lesson)."""
        cut = self._body_is_cut()
        if self._last_payload is None:
            line = INITIAL_TITLE + (f" · [yellow]{TALLER_HINT}[/]" if cut else "")
        else:
            line = title_line(self._last_payload, row_hint=cut)
        try:
            self.query_one(f"#{TITLE_BAR_ID}", Static).update(Text.from_markup(line))
        except Exception as exc:  # noqa: BLE001 -- a title must never crash
            logger.debug("Failed to update the seat title bar: %s", exc)
        if _recheck:
            self.call_after_refresh(self._recheck_row_marker, cut)

    def _recheck_row_marker(self, rendered: bool) -> None:
        try:
            if self._body_is_cut() != rendered:
                self._render_title(_recheck=False)
        except Exception as exc:  # noqa: BLE001
            logger.debug("seat row marker re-check failed: %s", exc)

    # -- keys -----------------------------------------------------------------

    def apply_payload(self, data: dict) -> None:
        """Paint one flat the CONTROL modal's own manager cycle returned while this screen is suspended under it.

        Textual suspends the screen under a pushed modal and ``DashboardScreen.on_screen_suspend`` stops the refresh
        timer, so the modal runs ``fetch_and_compute`` itself (live gate words, spec §8; the 15 s standing cadence
        while a plan is open, spec §6) and hands each flat here. Same dispatch as ``DashboardScreen._do_refresh``
        -- title, every ``PANELS`` row, the status bar, each contained on its own -- so a LOG line that cycle
        emitted (``fetch_and_compute`` emits each seq once) still reaches ``SeatLog``. Not a lifecycle method.
        """
        try:
            self._update_title(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to update the title bar: %s", exc)
        for widget_class, adapt in self.PANELS:
            try:
                self.query_one(widget_class).update_data(**adapt(data))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to update %s: %s", widget_class.__name__, exc)
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to update StatusBar: %s", exc)

    def action_control(self) -> None:
        self.app.push_screen(SeatControlScreen(self._data_manager, flat=self._last_payload, poll_s=max(1.0, float(self._poll_interval)),
                                               on_payload=self.apply_payload))

    def action_toggle_log(self) -> None:
        tall = self.query_one(SeatLog).toggle_tall()
        self.query_one(f"#{ROW_IDS[0]}").set_class(tall, TALL_ROW_CLASS)
        self.call_after_refresh(self._render_title)

    def action_toggle_heartbeats(self) -> None:
        self.query_one(SeatLog).toggle_heartbeats()

    def action_task_detail(self) -> None:
        row = self.query_one(SeatLedgerTable).selected_row()
        if row is None:
            return
        self.app.push_screen(SeatTaskDetail(row))
