"""MaxPane Dashboard -- main Textual application."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.data.cattown_manager import CatTownManager
from maxpane_dashboard.data.dota_manager import DOTAManager
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.data.fwa_manager import FWAManager
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.screens.bakery import BakeryScreen
from maxpane_dashboard.screens.base_terminal import BaseTerminalScreen
from maxpane_dashboard.screens.cattown import CatTownScreen
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
from maxpane_dashboard.screens.splash import SplashScreen
from maxpane_dashboard.screens.talismans import TalismansScreen
from maxpane_dashboard.screens.ttt import TTTScreen
from maxpane_dashboard.themes import THEMES, THEME_NAMES
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)

CSS_PATH = Path(__file__).parent / "themes" / "minimal.tcss"


class MaxPaneApp(App):
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
        initial_game: str = "bakery",
        wallet_address: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.poll_interval = poll_interval
        self._initial_theme = theme if theme in THEMES else "minimal"
        self._initial_game = initial_game
        self._bakery_manager = DataManager(poll_interval=poll_interval)
        self._frenpet_manager = FrenPetManager(
            poll_interval=poll_interval,
            wallet_address=wallet_address,
        )
        self._frenpet_full_manager = FrenPetManager(
            poll_interval=poll_interval,
            wallet_address=wallet_address,
        )
        self._frenpet_wallet_manager = FrenPetManager(
            poll_interval=poll_interval,
            wallet_address=wallet_address,
            fetch_rewards=True,
        )
        self._frenpet_perf_manager = FrenPetManager(
            poll_interval=poll_interval,
            wallet_address=wallet_address,
        )
        self._base_manager = BaseManager(remote_only=True)
        self._cattown_manager = CatTownManager(poll_interval=poll_interval)
        self._ocm_manager = OCMManager(poll_interval=poll_interval)
        self._dota_manager = DOTAManager(poll_interval=poll_interval)
        self._ttt_manager = TTTManager(poll_interval=poll_interval)
        self._talismans_manager = TalismansManager(poll_interval=poll_interval)
        # FWAManager builds its own market client with coingecko_min_spacing=6.0
        # (COINGECKO_MIN_SPACING); do not pass one in here.
        self._fwa_manager = FWAManager(poll_interval=poll_interval)
        # All four FrenPet managers persist to the same
        # ~/.maxpane/frenpet_cache.json and FrenPetCache.save_to_file is a
        # full overwrite invoked from close(), so on quit the three managers
        # whose screens never polled used to rewrite the file with their
        # construction-time snapshot — discarding the score history the active
        # manager had just saved.  One shared cache means every writer holds
        # the same live state, whichever of them writes last.
        _shared_frenpet_cache = self._frenpet_manager.cache
        for _frenpet_variant in (
            self._frenpet_full_manager,
            self._frenpet_wallet_manager,
            self._frenpet_perf_manager,
        ):
            _frenpet_variant.cache = _shared_frenpet_cache
        self._current_game = initial_game

    def on_mount(self) -> None:
        """Register themes, show splash, then start the first game screen."""
        # Register all themes and apply the initial one
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = self._initial_theme

        # Start fetching data in background while splash is showing
        manager = self._prefetch_manager(self._initial_game)
        if manager is not None:
            self.run_worker(
                self._prefetch(manager, self._initial_game),
                exclusive=True,
                name="prefetch",
                exit_on_error=False,
            )

        # Show splash screen → game select → dashboard
        self.push_screen(SplashScreen(), callback=self._on_splash_dismissed)

    def _prefetch_manager(self, game_id: str):
        """Return the manager that warms the cache for *game_id*, if any.

        A single mapping instead of a branch per game: a new dashboard that
        forgets to add itself here simply gets no prefetch (the screen fetches
        on mount anyway) rather than a hand-copied ``run_worker`` call that
        may forget the error guard below.
        """
        return {
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

    def _on_splash_dismissed(self, _result=None) -> None:
        """After splash, show the game selection screen."""
        self.push_screen(GameSelectScreen(), callback=self._on_game_selected)

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
    _GAME_CYCLE = ["base", "frenpet", "cattown", "bakery", "ocm", "ttt", "talismans", "fwa"]

    def _launch_game(self, game_id: str, *, first: bool = False) -> None:
        """Install and switch to a game screen.

        When *first* is True, uses push_screen (no existing screen to pop).
        Otherwise uses switch_screen (replaces current screen).
        """
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
        else:
            return

        if first:
            self.push_screen(game_id)
        else:
            self.switch_screen(game_id)

    def _on_wallet_entered(self, address: str | None) -> None:
        """Callback after the wallet input screen is dismissed."""
        if not address:
            return
        if self._current_game == "frenpet_wallet":
            self._frenpet_wallet_manager._wallet_address = address
            self._launch_game("frenpet_wallet", first=True)
        elif self._current_game == "frenpet_perf":
            self._frenpet_perf_manager._wallet_address = address
            self._launch_game("frenpet_perf", first=True)
        else:
            self._frenpet_full_manager._wallet_address = address
            self._current_game = "frenpet_full"
            self._launch_game("frenpet_full", first=True)

    def _ensure_frenpet_full_screen(self, wallet: str) -> None:
        """Install the FrenPet Full screen if not already installed."""
        if not self.is_screen_installed("frenpet_full"):
            self._frenpet_full_manager._wallet_address = wallet
            self.install_screen(
                FrenPetFullScreen(self._frenpet_full_manager, self.poll_interval, name="frenpet_full"),
                name="frenpet_full",
            )

    def _ensure_frenpet_wallet_screen(self, wallet: str) -> None:
        """Install the FrenPet Wallet screen if not already installed."""
        if not self.is_screen_installed("frenpet_wallet"):
            self._frenpet_wallet_manager._wallet_address = wallet
            self.install_screen(
                FrenPetWalletScreen(self._frenpet_wallet_manager, self.poll_interval, name="frenpet_wallet"),
                name="frenpet_wallet",
            )

    def _ensure_frenpet_perf_screen(self, wallet: str) -> None:
        """Install the FrenPet Performance screen if not already installed."""
        if not self.is_screen_installed("frenpet_perf"):
            self._frenpet_perf_manager._wallet_address = wallet
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
            try:
                screen_name = self.screen.name
            except Exception:  # no screen on the stack yet
                return False
            return screen_name in self._GAME_CYCLE
        return True

    def action_show_menu(self) -> None:
        """Return to the game selection screen."""
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

    async def action_quit(self) -> None:
        """Shut down gracefully: persist cache and close HTTP clients."""
        try:
            await self._bakery_manager.close()
        except Exception as exc:
            logger.warning("Error during bakery shutdown: %s", exc)
        try:
            await self._frenpet_manager.close()
        except Exception as exc:
            logger.warning("Error during frenpet shutdown: %s", exc)
        try:
            await self._frenpet_full_manager.close()
        except Exception as exc:
            logger.warning("Error during frenpet_full shutdown: %s", exc)
        try:
            await self._frenpet_wallet_manager.close()
        except Exception as exc:
            logger.warning("Error during frenpet_wallet shutdown: %s", exc)
        try:
            await self._frenpet_perf_manager.close()
        except Exception as exc:
            logger.warning("Error during frenpet_perf shutdown: %s", exc)
        try:
            await self._base_manager.close()
        except Exception as exc:
            logger.warning("Error during base shutdown: %s", exc)
        try:
            await self._cattown_manager.close()
        except Exception as exc:
            logger.warning("Error during cattown shutdown: %s", exc)
        try:
            await self._ocm_manager.close()
        except Exception as exc:
            logger.warning("Error during ocm shutdown: %s", exc)
        try:
            await self._dota_manager.close()
        except Exception as exc:
            logger.warning("Error during dota shutdown: %s", exc)
        try:
            await self._ttt_manager.close()
        except Exception as exc:
            logger.warning("Error during ttt shutdown: %s", exc)
        try:
            await self._talismans_manager.close()
        except Exception as exc:
            logger.warning("Error during talismans shutdown: %s", exc)
        try:
            await self._fwa_manager.close()
        except Exception as exc:
            logger.warning("Error during fwa shutdown: %s", exc)
        self.exit()
