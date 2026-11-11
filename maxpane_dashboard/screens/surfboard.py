"""Dashboard nine: a retained SURFBOARD rack and native IMD command monitor."""
from __future__ import annotations

from time import monotonic
from urllib.parse import urlsplit

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.constants import DIM_FACTOR
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from maxpane_dashboard.data.surf_models import SURFBOARD_WIDGET_SIGNATURES
from maxpane_dashboard.launch_notifications import SurfLaunchesUpdated
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.screens.surf import MODE_AGENT, MODE_WORK, MODE_ORACLES, MODE_POOL4
from maxpane_dashboard.widgets.explorer import IMD, is_job_id, job_url
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.reveal import TerminalReveal
from maxpane_dashboard.intro.matrix import DURATION

#: Rechecked 2026-10-15 after removing the horizontal reserve, live at 149×45.
#: Six equal fractional columns fill the viewport, matching the AGENT board.
#: At 149×45 every card is 24 columns wide, separated by one-cell gutters;
#: widths at other terminal sizes differ by at most one rounding cell.
#: The previous first-column/ORACLES transfer is removed. FLEET remains top-right,
#: TOKENS sits below it; NFTS replaced PROTOCOL below ONCHAIN FEED on 2026-10-17.
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
#: Gaps below NFTS and TOKENS are three lines, with regular muted captions
#: centered in the middle line above AGENT seats. Other card gaps are one line.
#: All cards remain equally tall, measuring nine rows at the owner size.
#: The terminal fills the four center columns down to the rack bottom,
#: measuring 95 columns at the pin and 99 at 149×45.
#: NFTS and TOKENS retain equal inset padding. NFTS shows native collection digits,
#: building inset footer and build/open outer counts; token arrows stay right-aligned.
#: WIP keeps job digits and a busy-seat count; its outer footer counts open workflows.
#: SHIPPED shows LAUNCHES with completed workflows inside and 24H history below.
#: Rechecked 2026-11-11 after live 149×45 preview: 939 launches / 163 workflows and
#: 15 working fit at 143×37. Boundary samples span 110–160 columns and 25–55 rows;
#: 142×45 scrolls, 143×45 clears; 143×36 scrolls both axes and 144×36 only vertically.
#: SWARM shows AGENTS digits and working-seat counts; the worked-duration footer remains.
#: Live 2026-11-11: 1,053 agents / 17 working and orange NOT ACCEPTING / NA-red-bar
#: fit at 143×37 and 149×45. Eleven boundary samples retain the existing scroll onsets.
#: Rechecked 2026-10-21 after live preview: 143×37 is unchanged. The title occupies
#: its original top row; navigation now flanks the title with symmetric spacing.
#: Normal, stress, unavailable and wide payloads fit at 143×37 and 149×45.
#: Resize checks preserve card/terminal alignment, captions and visible footers
#: in both the screen's default CSS and the production stylesheet.
#: Settled geometry refreshes Textual's scrollbar decision after resizing, so
#: repeated short/tall transitions retain reachable edges and honest title hints.
#: App-wide width stays 143.
#: Rechecked 2026-11-11 for standing-based AGENT states: NOT ACCEPTING and 0 of 1
#: fit at 143×37 and live 149×45; the 110–160 by 25–55 boundary samples are unchanged.
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
        Binding("n", "nfts", "NFTs", show=False),
        Binding("u", "wallet_usage", "Wallet / Swarm", show=False),
        Binding("o", "portfolio", "Portfolio", show=False),
        Binding("g", "workflows", "Workflow guide", show=False),
        Binding("p", "protocol", "Protocol", show=False),
        Binding("ctrl+o", "oracles", "Oracles", show=False),
        Binding("slash", "command_input", "Command", show=False),
        Binding("1", "edit_seat(0)", "Seat 1", show=False),
        Binding("2", "edit_seat(1)", "Seat 2", show=False),
        Binding("3", "edit_seat(2)", "Seat 3", show=False),
        Binding("4", "edit_seat(3)", "Seat 4", show=False),
        Binding("left", "card('left')", show=False),
        Binding("right", "card('right')", show=False),
        Binding("up", "card('up')", show=False),
        Binding("down", "card('down')", show=False),
        Binding("enter", "open_card", "Open", show=False),
        Binding("escape", "back", show=False),
    ]
    DEFAULT_CSS = """
    SurfboardScreen { background: $background; color: $text; layers: default terminal-reveal; }
    SurfboardScreen #surfboard-title { height: 1; color: $text-muted; content-align: center middle; }
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
        self._cached_hub_snapshot = None
        self._last_hub_snapshot = None
        self._nft_view_state = {}
        self._wallet_view_state = {}
        self._portfolio_view_state = {}
        self._workflow_guide_manager = None
        self._workflow_guide_view_state = {}
        self._entry_pending = False
        self._entry_started = None
        self._entry_timer = None
        self._terminal_reveal = TerminalReveal()

    def compose(self) -> ComposeResult:
        yield Static(Text("IMD BOARDROOM"), id="surfboard-title")
        with VerticalScroll(id="surfboard-viewport"):
            yield SurfboardRack(id="surfboard-rack")
        yield SurfStatusBar()
        yield self._terminal_reveal

    def prepare_entry_animation(self) -> None:
        """Arm only an explicit dashboard entry, never a subview return."""
        self._entry_pending = True

    def _begin_entry_animation(self) -> None:
        if not self._entry_pending or not self.is_current:
            return
        self._entry_pending = False
        self._entry_started = self._age_clock()
        self._terminal_reveal.display = True
        self._entry_timer = self.set_interval(1 / 20, self._tick_entry_animation)
        self._tick_entry_animation()

    def _tick_entry_animation(self) -> None:
        if self._entry_timer is None:
            return
        elapsed = max(0, self._age_clock() - self._entry_started)
        if not self.is_current or elapsed >= DURATION:
            self._stop_entry_animation()
            return
        self._terminal_reveal.elapsed = elapsed
        self._terminal_reveal.align_to(self.query_one(SurfboardTerminal),
                                       self.query_one('#surfboard-viewport'))
        self._terminal_reveal.refresh()

    def _stop_entry_animation(self) -> None:
        self._entry_pending = False
        if self._entry_timer is not None:
            self._entry_timer.stop()
            self._entry_timer = None
        self._terminal_reveal.display = False

    @on(events.ScreenResume)
    def _resume_hub(self) -> None:
        setter = getattr(self._data_manager, "set_hub_active", None)
        if setter is not None:
            setter(True)
        if self._age_timer is None:
            self._age_timer = self.set_interval(1, self._tick_terminal_age)
        self.call_after_refresh(self.query_one(SurfboardRack).focus_card)
        self.call_after_refresh(self._begin_entry_animation)

    @on(events.ScreenSuspend)
    def _suspend_hub(self) -> None:
        self._stop_entry_animation()
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
        self._stop_entry_animation()
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
                snapshot = self._data_manager.get_hub_snapshot()
                if snapshot == self._last_hub_snapshot:
                    return
                self._cache_only = True
                self._cached_hub_snapshot = snapshot
                self.start_refresh()

    async def _fetch_data(self) -> dict:
        if self._cache_only:
            self._cache_only = False
            snapshot, self._cached_hub_snapshot = self._cached_hub_snapshot, None
            return snapshot
        return await super()._fetch_data()

    def _snapshot_data(self):
        getter = getattr(self._data_manager, 'get_hub_snapshot', None)
        return getter() if callable(getter) else super()._snapshot_data()

    async def _fetch_live_data(self):
        return await self._data_manager.fetch_hub_snapshot()

    def _loading_view(self):
        return "surfboard"

    def _set_loading(self, busy):
        super()._set_loading(busy)
        for rack in self.query(SurfboardRack):
            rack.set_loading_animation(busy and self.is_current, self._card_loading_frame)

    def _prime_status_bar(self, bar: StatusBar) -> None:
        bar.set_key_hints("arrows · enter · o portfolio · u wallet · n NFTs · p protocol · w work · / cmd · esc")

    def _update_title(self, data: dict) -> None:
        self._last_hub_snapshot = data
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
        title = Text.assemble(
            ("IMD BOARDROOM", f"dim {self.app.get_css_variables()['foreground']}"),
            (" · " + " · ".join(hints) if hints else "") + self.loading_suffix)
        heading = self.query_one("#surfboard-title", Static)
        width = heading.content_size.width
        left, right = "↑ ↓ ← → to navigate cards", "↵ open · o portfolio · u wallet"
        # Equal side widths keep the title centered, with the same gap on each side.
        side = max(len(left), len(right))
        if 2 * side + title.cell_len + 4 > width:
            left, right = "↑ ↓ ← → navigate", "↵ open · o portfolio"
            side = max(len(left), len(right))
        if 2 * side + title.cell_len + 4 <= width:
            gap = max(1, (width - 2 * side - title.cell_len) // 4)
            card = self.query_one("#surfboard-card-agent")
            base, surface = card.background_colors
            background = base + surface
            # Match the footer's dim ink despite the header's different background.
            ink = background.blend(background + card.styles.border_subtitle_color, DIM_FACTOR).hex
            title = Text(left.rjust(side) + " " * gap, style=ink) + title + Text(" " * gap + right.ljust(side), style=ink)
        heading.update(title)

    def on_surfboard_rack_card_activated(self, event: SurfboardRack.CardActivated) -> None:
        if event.seat_slot is not None:
            self.app.open_surf_mode(MODE_AGENT, token_id=event.token_id, seat_slot=event.seat_slot)
            return
        if event.key == "surf-nft":
            self.action_nfts()
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
        self._seat_entered(event.seat_slot, token)

    def on_surfboard_rack_seat_edit_requested(self, event: SurfboardRack.SeatEditRequested) -> None:
        event.stop()
        self.action_edit_seat(event.seat_slot)

    def action_edit_seat(self, slot: int) -> None:
        if isinstance(self.focused, Input):
            return
        from maxpane_dashboard import config
        from maxpane_dashboard.screens.seat_input import SeatInputScreen

        prompt = SeatInputScreen(current=self._data_manager.get_hub_seats()[slot],
                                 saver=lambda token: config.save_surfboard_seat(slot, token))
        self.app.push_screen(prompt, callback=lambda token: self._seat_entered(slot, token))

    def _seat_entered(self, slot: int, token: int | None) -> None:
        if token is None:
            return
        seats = list(self._data_manager.get_hub_seats())
        seats[slot] = token
        self._data_manager.set_hub_seats(seats)
        if slot == 0:
            self._data_manager.set_seat(token)
        self.start_refresh()

    def action_command_input(self) -> None:
        self._stop_entry_animation()
        self.query_one(SurfboardTerminal).focus_input()

    def action_work(self) -> None:
        self.app.open_surf_mode(MODE_WORK)

    def action_nfts(self) -> None:
        if not isinstance(self.focused, Input):
            from maxpane_dashboard.screens.surf_nft import SurfNftScreen
            self.app.push_screen(SurfNftScreen(self._data_manager.nft_manager(),
                                             view_state=self._nft_view_state))

    def action_wallet_usage(self) -> None:
        if not isinstance(self.focused, Input):
            from maxpane_dashboard.screens.surf_wallet import SurfWalletScreen
            wallet = self._wallet_view_state.get('wallet', self._wallet)
            self.app.push_screen(SurfWalletScreen(self._data_manager.wallet_manager(wallet),
                                                  view_state=self._wallet_view_state))

    def action_protocol(self) -> None:
        if not isinstance(self.focused, Input):
            self.app.open_surf_mode(MODE_POOL4)

    def action_portfolio(self) -> None:
        if not isinstance(self.focused, Input):
            from maxpane_dashboard.screens.swarm_portfolio import SwarmPortfolioScreen
            from maxpane_dashboard import config
            wallet = self._wallet or config.get_wallet()
            self.app.push_screen(SwarmPortfolioScreen(
                self._data_manager.swarm_portfolio_manager(wallet),
                view_state=self._portfolio_view_state))

    def action_workflows(self) -> None:
        if not isinstance(self.focused, Input):
            from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager
            from maxpane_dashboard.screens.workflow_guide import WorkflowGuideScreen
            if self._workflow_guide_manager is None:
                self._workflow_guide_manager = WorkflowGuideManager()
            self.app.push_screen(WorkflowGuideScreen(
                self._workflow_guide_manager, view_state=self._workflow_guide_view_state))

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
