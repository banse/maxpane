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
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.screens.bakery import BakeryScreen
from maxpane_dashboard.screens.base_terminal import BaseTerminalScreen
from maxpane_dashboard.screens.cattown import CatTownScreen
from maxpane_dashboard.screens.dota import DOTAScreen
from maxpane_dashboard.screens.frenpet import FrenPetScreen
from maxpane_dashboard.screens.game_select import GameSelectScreen
from maxpane_dashboard.screens.ocm import OCMScreen
from maxpane_dashboard.screens.splash import SplashScreen
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
        Binding("tab", "switch_game", "Switch Game", show=False),
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
        self._base_manager = BaseManager(remote_only=True)
        self._cattown_manager = CatTownManager(poll_interval=poll_interval)
        self._ocm_manager = OCMManager(poll_interval=poll_interval)
        self._dota_manager = DOTAManager(poll_interval=poll_interval)
        self._current_game = initial_game

    def on_mount(self) -> None:
        """Register themes, show splash, then start the first game screen."""
        # Register all themes and apply the initial one
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = self._initial_theme

        # Start fetching data in background while splash is showing
        if self._initial_game == "bakery":
            self.run_worker(
                self._bakery_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )
        elif self._initial_game == "frenpet":
            self.run_worker(
                self._frenpet_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )
        elif self._initial_game == "base":
            self.run_worker(
                self._base_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )
        elif self._initial_game == "cattown":
            self.run_worker(
                self._cattown_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )
        elif self._initial_game == "ocm":
            self.run_worker(
                self._ocm_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )
        elif self._initial_game == "dota":
            self.run_worker(
                self._dota_manager.fetch_and_compute(),
                exclusive=True,
                name="prefetch",
            )

        # Show splash screen → game select → dashboard
        self.push_screen(SplashScreen(), callback=self._on_splash_dismissed)

    def _on_splash_dismissed(self, _result=None) -> None:
        """After splash, show the game selection screen."""
        self.push_screen(GameSelectScreen(), callback=self._on_game_selected)

    def _on_game_selected(self, game_id: str | None = None) -> None:
        """Launch the selected game dashboard."""
        if game_id is None:
            game_id = self._initial_game
        self._current_game = game_id
        self._launch_game(game_id, first=True)

    _GAME_CYCLE = ["base", "frenpet", "cattown", "ocm", "dota", "bakery"]

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
        else:
            return

        if first:
            self.push_screen(game_id)
        else:
            self.switch_screen(game_id)

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
        self.exit()
