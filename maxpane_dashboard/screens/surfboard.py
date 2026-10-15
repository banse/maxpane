"""Dashboard nine: a retained SURFBOARD rack and native IMD command monitor."""
from __future__ import annotations

from time import monotonic
from urllib.parse import urlsplit

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from maxpane_dashboard.data.surf_models import SURFBOARD_WIDGET_SIGNATURES
from maxpane_dashboard.launch_notifications import SurfLaunchesUpdated
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.screens.surf import MODE_AGENT, MODE_WORK, MODE_ORACLES
from maxpane_dashboard.widgets.explorer import IMD, is_job_id, job_url
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal

#: Rechecked 2026-10-15 after removing the horizontal reserve, live at 149×45.
#: Six equal fractional columns fill the viewport, matching the AGENT board.
#: At 149×45 every card is 24 columns wide, separated by one-cell gutters;
#: widths at other terminal sizes differ by at most one rounding cell.
#: The previous first-column/ORACLES transfer is removed. FLEET remains top-right,
#: TOKENS sits below it, and PROTOCOL remains below ONCHAIN FEED.
#: The viewport keeps vertical padding but no horizontal padding or idle gutter.
#: Owner exception to the stable-gutter rule: the vertical scrollbar consumes
#: one column only while needed. Width onset therefore depends on viewport height.
#: The rack retains its 143-column minimum and 23-column card floor.
#: Measured at 37 and 45 rows: 142 columns scroll horizontally, 143 do not.
#: At 36 rows vertical scrolling consumes a column: 143 scrolls horizontally,
#: 144 does not. Normal, stress, unavailable and wide boundary composites agree.
#: The full-layout pin is 143×37; short screens can need a 144-column viewport.
#: At width 143, height 36 scrolls on both axes and 37 clears both bars.
#: Four seven-row card floors, three gutters and two extra side-gap rows need
#: a 33-row rack; vertical padding and title/status rows retain the 37-row pin.
#: Gaps below PROTOCOL and TOKENS are three lines, with regular muted captions
#: centered in the middle line above AGENT seats. Other card gaps are one line.
#: All cards remain equally tall, measuring nine rows at the owner size.
#: The terminal fills the four center columns down to the rack bottom,
#: measuring 95 columns at the pin and 99 at 149×45.
#: PROTOCOL and TOKENS retain equal inset padding and leading blanks; stats
#: retain the full stress values and IMD units, and token arrows stay right-aligned.
#: WORK IN PROGRESS keeps job digits and workflow subtitle. Its outer footer
#: shows SWARM's 24H history; build/review counts stay under BUILT BY SWARM.
#: FLEET keeps three RUNTIMES rows and the model/effort footer. A nine-cell base
#: daemon fits the trailing value cell; model footers retain both lower corners.
#: Normal, stress, unavailable and wide payloads fit at 143×37 and 149×45.
#: Resize checks preserve card/terminal alignment, captions and visible footers
#: in both the screen's default CSS and the production stylesheet.
#: Settled geometry refreshes Textual's scrollbar decision after resizing, so
#: repeated short/tall transitions retain reachable edges and honest title hints.
#: App-wide width stays 143.
SURFBOARD_FULL_LAYOUT_COLUMNS = 143
SURFBOARD_FULL_LAYOUT_ROWS = 37


class SurfboardScreen(SurfDashboardScreen):
    GAME_NAME = "SURFBOARD HUB"
    LOADING_CHROME = "_render_chrome"
    REFRESH_WORKER_NAME = "surfboard-refresh"
    JOIN_STARTUP_PREFETCH = False
    PANELS = (
        (SurfboardRack, keys(*SURFBOARD_WIDGET_SIGNATURES["SurfboardRack"])),
        (SurfboardTerminal, keys(*SURFBOARD_WIDGET_SIGNATURES["SurfboardTerminal"])),
    )
    BINDINGS = [
        Binding("w", "work", "Work in progress", show=False),
        Binding("ctrl+o", "oracles", "Oracles", show=False),
        Binding("slash", "command_input", "Command", show=False),
        Binding("left", "card('left')", show=False),
        Binding("right", "card('right')", show=False),
        Binding("up", "card('up')", show=False),
        Binding("down", "card('down')", show=False),
        Binding("enter", "open_card", "Open", show=False),
        Binding("escape", "back", show=False),
    ]
    DEFAULT_CSS = """
    SurfboardScreen { background: $background; color: $text; }
    SurfboardScreen #surfboard-title { height: 1; background: $surface; color: $text-muted; padding: 0 1; content-align: center middle; }
    SurfboardScreen #surfboard-viewport { height: 1fr; padding: 1 0; overflow: auto auto;
        scrollbar-gutter: auto; scrollbar-size-vertical: 1; scrollbar-size-horizontal: 1; }
    """

    def __init__(self, manager, poll_interval=30, name="surfboard", *, wallet=None, clock=monotonic, **kwargs):
        if isinstance(poll_interval, bool) or poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        super().__init__(manager, 30, name=name, **kwargs)
        self._wallet = wallet
        self._command_generation = 0
        self._command_worker = None
        self._command_busy = False
        self._age_clock = clock
        self._age_captured = None
        self._age_timer = None
        self._loading = False
        self._cache_only = False

    def compose(self) -> ComposeResult:
        yield Static(Text("IMD BOARDROOM"), id="surfboard-title")
        with VerticalScroll(id="surfboard-viewport"):
            yield SurfboardRack(id="surfboard-rack")
        yield SurfStatusBar()

    @on(events.ScreenResume)
    def _resume_hub(self) -> None:
        setter = getattr(self._data_manager, "set_hub_active", None)
        if setter is not None:
            setter(True)
        if self._age_timer is None:
            self._age_timer = self.set_interval(1, self._tick_terminal_age)
        self.call_after_refresh(self.query_one(SurfboardRack).focus_card)

    @on(events.ScreenSuspend)
    def _suspend_hub(self) -> None:
        self._stop_age_timer()
        self._cache_only = False
        setter = getattr(self._data_manager, "set_hub_active", None)
        if setter is not None:
            setter(False)
        self._command_generation += 1
        self._command_busy = False
        if self._command_worker is not None:
            self._command_worker.cancel()
            self._command_worker = None

    def on_unmount(self) -> None:
        self._stop_age_timer()

    def _stop_age_timer(self) -> None:
        if self._age_timer is not None:
            self._age_timer.stop()
            self._age_timer = None

    def _tick_terminal_age(self) -> None:
        if self._age_timer is not None and self.is_current and self._age_captured is not None:
            self.query_one(SurfboardTerminal).update_age(
                max(0, self._age_clock() - self._age_captured))
            if self._loading and not self._refresh_in_flight:
                self._cache_only = True
                self.start_refresh()

    async def _fetch_data(self) -> dict:
        if self._loading_projection:
            return await super()._fetch_data()
        if self._cache_only:
            self._cache_only = False
            return self._data_manager.get_hub_snapshot()
        return await self._data_manager.fetch_hub_snapshot()

    def _loading_view(self):
        return "surfboard"

    def _prime_status_bar(self, bar: StatusBar) -> None:
        bar.set_key_hints("arrows cards · enter open · w work · / command · esc menu")

    def _update_title(self, data: dict) -> None:
        self.post_message(SurfLaunchesUpdated(self, data))
        self._age_captured = self._age_clock()
        self._loading = any(card.get('status') == 'loading' for card in data.get('surfboard_cards') or [])
        self.call_after_refresh(self._render_chrome)

    def on_resize(self) -> None:
        self.call_after_refresh(self._render_chrome)

    def _render_chrome(self) -> None:
        viewport = self.query_one("#surfboard-viewport", VerticalScroll)
        # Textual's auto/auto oscillation guard can retain a previous resize's
        # scrollbar decision. Reconcile against the settled viewport geometry.
        viewport._scrollbar_changes.clear()
        viewport._refresh_scrollbars()
        hints = []
        if viewport.show_horizontal_scrollbar:
            hints.append("‹ widen")
        if viewport.show_vertical_scrollbar:
            hints.append("‹ taller")
        self.query_one("#surfboard-title", Static).update(Text(
            "IMD BOARDROOM" + (" · " + " · ".join(hints) if hints else "") + self.loading_suffix))

    def on_surfboard_rack_card_activated(self, event: SurfboardRack.CardActivated) -> None:
        if event.seat_slot is not None:
            self.app.open_surf_mode(MODE_AGENT, token_id=event.token_id, seat_slot=event.seat_slot)
            return
        if event.key == "swarm-tokens":
            from maxpane_dashboard.screens.swarm_tokens import SwarmTokensScreen
            self.app.push_screen(SwarmTokensScreen(self._data_manager.swarm_tokens_manager()))
            return
        if event.destination is None:
            return
        self.app.open_surf_mode(event.destination)

    def on_surfboard_rack_seat_submitted(self, event: SurfboardRack.SeatSubmitted) -> None:
        from maxpane_dashboard import config
        from maxpane_dashboard.screens.seat_input import parse_seat

        event.stop()
        token = parse_seat(event.value)
        if token is None:
            self.query_one(SurfboardRack).set_seat_error(event.seat_slot, "invalid seat no")
            return
        try:
            config.save_surfboard_seat(event.seat_slot, token)
        except OSError:
            self.query_one(SurfboardRack).set_seat_error(event.seat_slot, "save failed")
            return
        seats = list(self._data_manager.get_hub_seats())
        seats[event.seat_slot] = token
        self._data_manager.set_hub_seats(seats)
        if event.seat_slot == 0:
            self._data_manager.set_seat(token)
        self.start_refresh()

    def action_command_input(self) -> None:
        self.query_one(SurfboardTerminal).focus_input()

    def action_work(self) -> None:
        self.app.open_surf_mode(MODE_WORK)

    def action_oracles(self) -> None:
        self.app.open_surf_mode(MODE_ORACLES)

    def action_card(self, direction: str) -> None:
        if not isinstance(self.focused, Input):
            self.query_one(SurfboardRack).move_focus(direction)

    def action_open_card(self) -> None:
        if not isinstance(self.focused, Input):
            self.query_one(SurfboardRack).activate_focused()

    def action_back(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one(SurfboardRack).focus_card()
        else:
            self.app.action_show_menu()

    def on_surfboard_terminal_command_requested(self, event: SurfboardTerminal.CommandRequested) -> None:
        """Only schedule a lookup here; the manager owns all external reads."""
        event.stop()
        if self._command_busy:
            self.query_one(SurfboardTerminal).add_reply("lookup in progress")
            return
        if not event.command.strip():
            return
        self._command_busy = True
        generation = self._command_generation
        self._command_worker = self.run_worker(
            self._execute_command(event.command, generation),
            group="surfboard-command", name="surfboard-command", exit_on_error=False,
        )

    async def _execute_command(self, command: str, generation: int) -> None:
        try:
            result = await self._data_manager.execute_hub_command(command, wallet=self._wallet)
            if generation != self._command_generation or not self.is_current:
                return
            terminal = self.query_one(SurfboardTerminal)
            if result.get("clear"):
                terminal.clear_replies()
            else:
                terminal.add_reply(result.get("lines") or [])
            if result.get("intent") == "open_seat":
                self.app.open_surf_mode(MODE_AGENT, token_id=result.get("token_id"))
            elif result.get("intent") == "open_url":
                url = result.get("url")
                if isinstance(url, str):
                    parsed = urlsplit(url)
                    job_id = parsed.path.removeprefix("/jobs/")
                    if is_job_id(job_id) and url == job_url(IMD, job_id):
                        self.app.action_open_explorer(IMD.name, "job", job_id)
        except Exception:
            if generation == self._command_generation and self.is_current:
                self.query_one(SurfboardTerminal).add_reply("lookup unavailable; try again")
        finally:
            if generation == self._command_generation:
                self._command_busy = False
                self._command_worker = None
