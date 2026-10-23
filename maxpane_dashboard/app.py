"""MaxPane Dashboard -- main Textual application."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.widgets import Input

from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.launch_notifications import (
    LaunchNotifications, SurfLaunchesUpdated, launch_toast_message,
)
from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.data.cattown_manager import CatTownManager
from maxpane_dashboard.data.curator_manager import CuratorManager
from maxpane_dashboard.data.dota_manager import DOTAManager
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.data.fwa_manager import FWAManager
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.reader import ReaderHandle, ReaderRuntime
from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.data.sworn_manager import SwornManager
from maxpane_dashboard.screens.bakery import BakeryScreen
from maxpane_dashboard.screens.base_terminal import BaseTerminalScreen
from maxpane_dashboard.screens.cattown import CatTownScreen
from maxpane_dashboard.screens.curator import CuratorScreen
from maxpane_dashboard.screens.dota import DOTAScreen
from maxpane_dashboard.screens.frenpet import FrenPetScreen
from maxpane_dashboard.screens.frenpet_full import FrenPetFullScreen
from maxpane_dashboard.screens.frenpet_perf import FrenPetPerfScreen
from maxpane_dashboard.screens.frenpet_wallet import FrenPetWalletScreen
from maxpane_dashboard.screens.fwa import FWAScreen
from maxpane_dashboard.screens.game_select import GameSelectScreen
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.config import get_wallet
from maxpane_dashboard.screens.ocm import OCMScreen
from maxpane_dashboard.screens.surf import MODE_AGENT, SurfScreen
from maxpane_dashboard.screens.surfboard import SurfboardScreen
from maxpane_dashboard.screens.talismans import TalismansScreen
from maxpane_dashboard.screens.ttt import TTTScreen
from maxpane_dashboard.screens.sworn_screen import SwornScreen
from maxpane_dashboard.themes import THEMES, THEME_NAMES
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)

CSS_PATH = Path(__file__).parent / "themes" / "minimal.tcss"


class MaxPaneApp(CopyAddressMixin, ExplorerLinkMixin, App):
    """Fullscreen TUI dashboard supporting multiple blockchain games."""

    CSS_PATH = CSS_PATH
    TITLE = "MaxPane"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("t", "cycle_theme", "Theme", show=False),
        # priority=True: without it textual's built-in Screen binding
        # tab -> app.focus_next sits earlier in the binding chain and this
        # never fires (see check_action for where it is stood down again).
        Binding("tab", "switch_game", "Switch Game", show=False, priority=True),
        Binding("m", "show_menu", "Menu", show=False),
    ]

    def __init__(
        self,
        poll_interval: int = 30,
        theme: str = "matrix",
        # Sixth registration surface: kept a hand-typed literal, like
        # _GAME_CYCLE below and __main__'s --game choices, so the test that
        # compares it to GAMES[0] compares two surfaces rather than a constant
        # against itself.  It must name the menu's *first* entry -- a bare
        # MaxPaneApp() prefetches this while the menu opens on GAMES[0], and
        # it is also the `game_id is None` fallback in _on_game_selected.
        initial_game: str = "surf",
        wallet_address: str | None = None,
        seat: int | None = None,
        surfboard_seats: tuple[int | None, ...] | None = None,
        sworn_graphics: dict | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.poll_interval = poll_interval
        self.sworn_graphics = sworn_graphics or {}
        self._initial_theme = theme if theme in THEMES else "minimal"
        self._initial_game = initial_game
        # Factories run lazily on one reader loop. App construction never loads
        # a cache or creates an HTTP client on Textual's event loop.
        self._reader = ReaderRuntime(poll_interval=poll_interval)
        register = self._reader.register
        self._bakery_manager = register(
            "bakery", lambda: DataManager(poll_interval=poll_interval))
        self._frenpet_manager = register(
            "frenpet", lambda: FrenPetManager(
                poll_interval=poll_interval, wallet_address=wallet_address),
            {"_wallet_address": wallet_address})

        def frenpet_variant(*, fetch_rewards=False):
            manager = FrenPetManager(poll_interval=poll_interval,
                                     wallet_address=wallet_address,
                                     fetch_rewards=fetch_rewards)
            # Every variant persists the same cache file; preserve one live
            # cache even when a variant is opened before the ordinary board.
            manager.cache = self._reader.get_manager("frenpet").cache
            return manager

        self._frenpet_full_manager = register(
            "frenpet_full", frenpet_variant, {"_wallet_address": wallet_address})
        self._frenpet_wallet_manager = register(
            "frenpet_wallet", lambda: frenpet_variant(fetch_rewards=True),
            {"_wallet_address": wallet_address})
        self._frenpet_perf_manager = register(
            "frenpet_perf", frenpet_variant, {"_wallet_address": wallet_address})
        self._base_manager = register("base", lambda: BaseManager(remote_only=True))
        self._cattown_manager = register(
            "cattown", lambda: CatTownManager(poll_interval=poll_interval))
        self._ocm_manager = register(
            "ocm", lambda: OCMManager(poll_interval=poll_interval))
        self._dota_manager = register(
            "dota", lambda: DOTAManager(poll_interval=poll_interval))
        self._ttt_manager = register(
            "ttt", lambda: TTTManager(poll_interval=poll_interval))
        self._talismans_manager = register(
            "talismans", lambda: TalismansManager(poll_interval=poll_interval))

        def surf_manager():
            manager = SurfManager(poll_interval=poll_interval, seat=seat)
            if surfboard_seats is not None:
                manager.set_hub_seats(surfboard_seats)
                manager.set_seat(manager.get_hub_seats()[0])
            return manager

        self._surf_manager = register("surf", surf_manager, {
            "seat": surfboard_seats[0] if surfboard_seats is not None else seat,
            "hub_seats": tuple(surfboard_seats) if surfboard_seats is not None
                         else (seat, None, None, None),
        })
        self._surfboard_wallet_address = wallet_address
        self._curator_manager = register(
            "curator", lambda: CuratorManager(
                poll_interval=poll_interval, wallet=wallet_address),
            {"wallet": wallet_address or None})
        self._fwa_manager = register(
            "fwa", lambda: FWAManager(poll_interval=poll_interval))
        self._sworn_manager = register("sworn", SwornManager)
        self._current_game = initial_game
        self._launch_notifications = LaunchNotifications()

    def on_surf_launches_updated(self, event: SurfLaunchesUpdated) -> None:
        if event.screen is not self.screen or not isinstance(self.screen, (SurfScreen, SurfboardScreen)):
            return
        for launch in self._launch_notifications.consume(event.data):
            self.notify(launch_toast_message(launch), title="Token launched", timeout=10)

    def on_mount(self) -> None:
        """Open the idle menu; the CLI owns the optional native intro."""
        # Register all themes and apply the initial one
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = self._initial_theme

        # The visible dashboard owns acquisition; the menu starts no readers.
        self.push_screen(GameSelectScreen(), callback=self._on_game_selected)

    def _prefetch_manager(self, game_id: str):
        """Return the manager that warms the cache for *game_id*, if any.

        A single mapping instead of a branch per game: a new dashboard that
        forgets to add itself here simply gets no prefetch (the screen fetches
        on mount anyway) rather than a hand-copied ``run_worker`` call that
        may forget the error guard below.
        """
        return {
            "sworn": self._sworn_manager,
            "bakery": self._bakery_manager,
            "frenpet": self._frenpet_manager,
            "frenpet_full": self._frenpet_full_manager,
            "frenpet_wallet": self._frenpet_wallet_manager,
            "frenpet_perf": self._frenpet_perf_manager,
            "base": self._base_manager,
            "cattown": self._cattown_manager,
            "ocm": self._ocm_manager,
            "dota": self._dota_manager,
            "ttt": self._ttt_manager,
            "talismans": self._talismans_manager,
            "surf": self._surf_manager,
            "surfboard": self._surf_manager,
            "curator": self._curator_manager,
            "fwa": self._fwa_manager,
        }.get(game_id)

    async def _prefetch(self, manager, game_id: str) -> None:
        """Warm *manager*'s cache while the splash is showing.

        Never propagates.  Managers whose ``fetch_and_compute`` re-raises
        (bakery, frenpet, ocm, ...) would otherwise fail this worker, and a
        failed worker panics Textual with ``WorkerFailed`` and exits the
        process with return code 1 — so launching with no network, a DNS
        failure or a game API 5xx killed the app instead of showing the
        dashboard.  Every screen's own ``_do_refresh`` already swallows and
        surfaces fetch errors in the status bar; the prefetch does the same,
        and ``exit_on_error=False`` on the worker is the second belt.
        """
        try:
            await manager.fetch_and_compute()
        except Exception as exc:
            logger.error("Startup prefetch for %s failed: %s", game_id, exc)

    def _on_game_selected(self, game_id: str | None = None) -> None:
        """Launch the selected game dashboard."""
        if game_id is None:
            game_id = self._initial_game
        self._current_game = game_id
        self._launch_game(game_id, first=True)

    # FrenPet variants ("frenpet_full", "frenpet_wallet", "frenpet_perf") are
    # temporarily hidden from cycling — code intact, restore by re-adding them.
    # "dota" is omitted: its game backend is NXDOMAIN. The manager, screen and
    # shutdown wiring below are intact so it can be restored by re-adding the id.
    _GAME_CYCLE = [
        "surf",
        "curator",
        "fwa",
        "base",
        "frenpet",
        "cattown",
        "ttt",
        "talismans",
        "surfboard",
        "sworn",
    ]

    def _launch_game(self, game_id: str, *, first: bool = False) -> None:
        """Install and switch to a game screen.

        When *first* is True, uses push_screen (no existing screen to pop).
        Otherwise uses switch_screen (replaces current screen).
        """
        self._clear_surf_navigation()
        if game_id == "bakery":
            if not self.is_screen_installed("bakery"):
                self.install_screen(
                    BakeryScreen(self._bakery_manager, self.poll_interval, name="bakery"),
                    name="bakery",
                )
        elif game_id == "frenpet":
            if not self.is_screen_installed("frenpet"):
                self.install_screen(
                    FrenPetScreen(self._frenpet_manager, self.poll_interval, name="frenpet"),
                    name="frenpet",
                )
        elif game_id == "frenpet_full":
            wallet = get_wallet()
            if not wallet:
                self.push_screen(
                    WalletInputScreen(),
                    callback=self._on_wallet_entered,
                )
                return
            self._ensure_frenpet_full_screen(wallet)
        elif game_id == "frenpet_wallet":
            wallet = get_wallet()
            if not wallet:
                self.push_screen(
                    WalletInputScreen(),
                    callback=self._on_wallet_entered,
                )
                return
            self._ensure_frenpet_wallet_screen(wallet)
        elif game_id == "frenpet_perf":
            wallet = get_wallet()
            if not wallet:
                self.push_screen(
                    WalletInputScreen(),
                    callback=self._on_wallet_entered,
                )
                return
            self._ensure_frenpet_perf_screen(wallet)
        elif game_id == "base":
            if not self.is_screen_installed("base"):
                self.install_screen(
                    BaseTerminalScreen(self._base_manager, self.poll_interval, name="base"),
                    name="base",
                )
        elif game_id == "cattown":
            if not self.is_screen_installed("cattown"):
                self.install_screen(
                    CatTownScreen(self._cattown_manager, self.poll_interval, name="cattown"),
                    name="cattown",
                )
        elif game_id == "ocm":
            if not self.is_screen_installed("ocm"):
                self.install_screen(
                    OCMScreen(self._ocm_manager, self.poll_interval, name="ocm"),
                    name="ocm",
                )
        elif game_id == "dota":
            if not self.is_screen_installed("dota"):
                self.install_screen(
                    DOTAScreen(self._dota_manager, self.poll_interval, name="dota"),
                    name="dota",
                )
        elif game_id == "ttt":
            if not self.is_screen_installed("ttt"):
                self.install_screen(
                    TTTScreen(self._ttt_manager, self.poll_interval, name="ttt"),
                    name="ttt",
                )
        elif game_id == "talismans":
            if not self.is_screen_installed("talismans"):
                self.install_screen(
                    TalismansScreen(
                        self._talismans_manager,
                        self.poll_interval,
                        name="talismans",
                    ),
                    name="talismans",
                )
        elif game_id == "fwa":
            if not self.is_screen_installed("fwa"):
                self.install_screen(
                    FWAScreen(
                        self._fwa_manager,
                        self.poll_interval,
                        name="fwa",
                    ),
                    name="fwa",
                )
        elif game_id == "surf":
            self._ensure_surf_screen()
        elif game_id == "surfboard":
            if not self.is_screen_installed("surfboard"):
                self.install_screen(SurfboardScreen(
                    self._surf_manager, self.poll_interval, name="surfboard",
                    wallet=self._surfboard_wallet_address,
                ), name="surfboard")
            self.get_screen("surfboard").prepare_entry_animation()
        elif game_id == "curator":
            if not self.is_screen_installed("curator"):
                self.install_screen(
                    CuratorScreen(
                        self._curator_manager,
                        self.poll_interval,
                        name="curator",
                        wallet=self._curator_manager.wallet,
                    ),
                    name="curator",
                )
        elif game_id == "sworn":
            if not self.is_screen_installed("sworn"):
                self.install_screen(SwornScreen(
                    self._sworn_manager, self.poll_interval, name="sworn",
                ), name="sworn")
        else:
            return

        if first:
            self.push_screen(game_id)
        else:
            self.switch_screen(game_id)

    def _ensure_surf_screen(self) -> SurfScreen:
        if not self.is_screen_installed("surf"):
            self.install_screen(SurfScreen(
                self._surf_manager, self.poll_interval, name="surf",
            ), name="surf")
        return self.get_screen("surf")

    def _clear_surf_navigation(self) -> None:
        """Menu and dashboard cycling end the rack's transient body visit."""
        if self.is_screen_installed("surf"):
            self.get_screen("surf").clear_return_context()
        setter = getattr(self._surf_manager, "set_agent_active", None)
        if setter is not None:
            setter(False)

    def open_surf_mode(self, mode: str, *, token_id: int | None = None,
                       seat_slot: int | None = None) -> None:
        """Open the installed native SURF body on behalf of dashboard nine."""
        if seat_slot is not None and (type(seat_slot) is not int or not 0 <= seat_slot < 4
                                      or mode != MODE_AGENT or token_id is None):
            raise ValueError("A seat slot needs a valid AGENT seat")
        if token_id is not None:
            from maxpane_dashboard.screens.seat_input import parse_seat
            token = parse_seat(str(token_id)) if not isinstance(token_id, bool) else None
            if token is None or mode != MODE_AGENT:
                raise ValueError("A seat route needs a valid AGENT seat")
        screen = self._ensure_surf_screen()
        screen.open_mode(mode, return_context="surfboard", seat_slot=seat_slot)
        if token_id is not None:
            screen.select_seat(token, persist=seat_slot is None)
        self._current_game = "surfboard"
        self.switch_screen("surf")

    def return_to_surfboard(self) -> None:
        """Restore the retained rack, draft and scroll position."""
        self._clear_surf_navigation()
        self._current_game = "surfboard"
        self.switch_screen("surfboard")

    def _on_wallet_entered(self, address: str | None) -> None:
        """Callback after the wallet input screen is dismissed."""
        if not address:
            return
        if self._current_game == "frenpet_wallet":
            self._frenpet_wallet_manager.set_wallet(address)
            self._launch_game("frenpet_wallet", first=True)
        elif self._current_game == "frenpet_perf":
            self._frenpet_perf_manager.set_wallet(address)
            self._launch_game("frenpet_perf", first=True)
        else:
            self._frenpet_full_manager.set_wallet(address)
            self._current_game = "frenpet_full"
            self._launch_game("frenpet_full", first=True)

    def _ensure_frenpet_full_screen(self, wallet: str) -> None:
        """Install the FrenPet Full screen if not already installed."""
        if not self.is_screen_installed("frenpet_full"):
            self._frenpet_full_manager.set_wallet(wallet)
            self.install_screen(
                FrenPetFullScreen(self._frenpet_full_manager, self.poll_interval, name="frenpet_full"),
                name="frenpet_full",
            )

    def _ensure_frenpet_wallet_screen(self, wallet: str) -> None:
        """Install the FrenPet Wallet screen if not already installed."""
        if not self.is_screen_installed("frenpet_wallet"):
            self._frenpet_wallet_manager.set_wallet(wallet)
            self.install_screen(
                FrenPetWalletScreen(self._frenpet_wallet_manager, self.poll_interval, name="frenpet_wallet"),
                name="frenpet_wallet",
            )

    def _ensure_frenpet_perf_screen(self, wallet: str) -> None:
        """Install the FrenPet Performance screen if not already installed."""
        if not self.is_screen_installed("frenpet_perf"):
            self._frenpet_perf_manager.set_wallet(wallet)
            self.install_screen(
                FrenPetPerfScreen(self._frenpet_perf_manager, self.poll_interval, name="frenpet_perf"),
                name="frenpet_perf",
            )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Stand the priority ``tab`` binding down outside game dashboards.

        ``switch_game`` is bound with ``priority=True`` so it beats Screen's
        built-in ``tab -> focus_next``.  Returning False here makes
        ``run_action`` skip it and the key falls through to the normal binding
        chain, so Tab still moves focus on the splash, the game-select screen
        and the wallet-input form (where stealing Tab from an Input would be
        actively hostile).
        """
        if action == "switch_game":
            if isinstance(self.focused, Input):
                return False
            try:
                screen_name = self.screen.name
            except Exception:  # no screen on the stack yet
                return False
            return screen_name in self._GAME_CYCLE
        return True

    def action_show_menu(self) -> None:
        """Return to the game selection screen."""
        self._clear_surf_navigation()
        self.pop_screen()
        self.push_screen(GameSelectScreen(), callback=self._on_game_selected)

    def action_switch_game(self) -> None:
        """Tab cycles through games."""
        current_idx = (
            self._GAME_CYCLE.index(self._current_game)
            if self._current_game in self._GAME_CYCLE
            else 0
        )
        next_idx = (current_idx + 1) % len(self._GAME_CYCLE)
        next_game = self._GAME_CYCLE[next_idx]
        self._current_game = next_game
        self._launch_game(next_game)

    def action_cycle_theme(self) -> None:
        """Cycle through available themes."""
        current_idx = (
            THEME_NAMES.index(self.theme)
            if self.theme in THEME_NAMES
            else 0
        )
        next_idx = (current_idx + 1) % len(THEME_NAMES)
        next_theme = THEME_NAMES[next_idx]
        self.theme = next_theme
        # Update status bar on the active screen
        try:
            self.screen.query_one(StatusBar).set_theme_name(next_theme)
        except Exception:
            pass

    async def _close_readers(self) -> None:
        if getattr(self, "_readers_closed", False):
            return
        self._readers_closed = True
        await self._reader.close()
        # Injected offline managers remain supported by app harnesses.
        for name, manager in vars(self).items():
            if name.endswith("_manager") and not isinstance(manager, ReaderHandle):
                try:
                    await manager.close()
                except Exception as exc:
                    logger.warning("Error during %s shutdown: %s", name, exc)

    async def on_unmount(self) -> None:
        await self._close_readers()

    async def action_quit(self) -> None:
        """Persist and close data on its reader loop, then exit Textual."""
        await self._close_readers()
        self.exit()
