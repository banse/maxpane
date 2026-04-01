"""FrenPetScreen -- FrenPet game dashboard with General, Wallet, and Pet views."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Static

from maxpane_dashboard.analytics.frenpet_signals import (
    calculate_battle_efficiency,
    calculate_rank,
    calculate_tod_status,
    determine_growth_phase,
    generate_pet_recommendation,
)
from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.widgets.frenpet import (
    ActionQueue,
    AggregateStats,
    AlertsPanel,
    BattleFeed,
    BattleLog,
    FrenPetLogo,
    GameStats,
    MarketConditions,
    NextActions,
    PetCard,
    PetSignals,
    PetStats,
    PetsInContext,
    Population,
    ScoreDistribution,
    ScoreTrend,
    SniperQueue,
    TargetLandscape,
    TopLeaderboard,
    TrainingStatus,
    WalletActivity,
)
from maxpane_dashboard.widgets.frenpet.overview import (
    FPBattleActivity,
    FPBestPlays,
    FPGameSignals,
    FPOverviewHero,
    FPOverviewLeaderboard,
    FPScoreTrends,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class FrenPetScreen(Screen):
    """FrenPet game dashboard with 4 views."""

    BINDINGS = [
        Binding("1", "show_general", "General", show=False),
        Binding("2", "show_wallet", "Wallet", show=False),
        Binding("3", "show_pet", "Pet", show=False),
        Binding("4", "show_overview", "Overview", show=False),
        Binding("left", "prev_pet", "Prev Pet", show=False),
        Binding("right", "next_pet", "Next Pet", show=False),
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(
        self,
        manager: FrenPetManager,
        poll_interval: int = 30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    DEFAULT_CSS = """
    #wallet-header {
        width: 100%;
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }
    #wallet-pet-row {
        width: 100%;
        height: auto;
        padding: 0 1;
        overflow-x: auto;
    }
    #wallet-mid {
        width: 100%;
        height: auto;
        padding: 1 0 0 0;
    }
    #wallet-mid-left {
        width: 1fr;
    }
    #wallet-mid-right {
        width: 1fr;
    }
    #wallet-mid-divider {
        width: 1;
        height: 100%;
        color: $text-muted;
    }
    #wallet-bottom {
        width: 100%;
        height: 1fr;
        padding: 1 0 0 0;
    }
    #wallet-bottom-left {
        width: 1fr;
    }
    #wallet-bottom-right {
        width: 1fr;
    }
    #wallet-bottom-divider {
        width: 1;
        height: 100%;
        color: $text-muted;
    }
    #pet-header {
        width: 100%;
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }
    #pet-top-row {
        width: 100%;
        height: auto;
    }
    #pet-mid-row {
        width: 100%;
        height: 1fr;
    }
    #pet-mid-left {
        width: 1fr;
    }
    #pet-mid-right {
        width: 1fr;
    }
    #pet-mid-divider {
        width: 1;
        height: 100%;
        color: $text-muted;
    }
    #pet-bottom-row {
        width: 100%;
        height: 1fr;
        padding: 1 0 0 0;
    }
    #pet-bottom-left {
        width: 1fr;
    }
    #pet-bottom-right {
        width: 1fr;
    }
    #pet-bottom-divider {
        width: 1;
        height: 100%;
        color: $text-muted;
    }
    #pet-separator {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    #pet-no-pets {
        width: 100%;
        padding: 2 4;
        color: $text-muted;
    }
    TrainingStatus {
        height: 1fr;
        overflow-y: auto;
    }
    PetSignals {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("FrenPet \u00b7 Base L2", id="fp-title")

        # View selector indicator
        yield Static(
            "[bold reverse] 1 General [/]  [dim][2] Wallet[/]  [dim][3] Pet[/]  [dim][4] Overview[/]",
            id="fp-view-selector",
        )

        with ContentSwitcher(initial="general"):
            # ── General View ──────────────────────────────────
            with Vertical(id="general"):
                # Top row: Population + Score Distribution
                with Horizontal(id="fp-top-row"):
                    yield Population()
                    yield ScoreDistribution()

                # Middle row: Top 10 Leaderboard + Battle Feed
                with Horizontal(id="fp-middle-row"):
                    yield TopLeaderboard()
                    yield BattleFeed()

                # Separator
                yield Static(
                    "\u2500" * 300,
                    id="fp-separator",
                )

                # Bottom row: Game Stats (left) + Pets In Context + Market (right)
                with Horizontal(id="fp-bottom-row"):
                    yield GameStats()
                    with Vertical(id="fp-right-bottom"):
                        yield PetsInContext()
                        yield MarketConditions()

            # ── Wallet View ──────────────────────────────────
            with Vertical(id="wallet"):
                yield Static(
                    "[dim]No wallet configured[/]",
                    id="wallet-header",
                )
                yield Horizontal(id="wallet-pet-row")
                with Horizontal(id="wallet-mid"):
                    yield AggregateStats(id="wallet-mid-left")
                    yield Static("\u2502", id="wallet-mid-divider")
                    yield ActionQueue(id="wallet-mid-right")
                with Horizontal(id="wallet-bottom"):
                    yield WalletActivity(id="wallet-bottom-left")
                    yield Static("\u2502", id="wallet-bottom-divider")
                    yield AlertsPanel(id="wallet-bottom-right")

            # ── Pet View ─────────────────────────────────────
            with Vertical(id="pet"):
                yield Static(
                    "[dim]No pets[/]",
                    id="pet-header",
                )

                # Top row: Stats + Score Trend + Next Actions
                with Horizontal(id="pet-top-row"):
                    yield PetStats()
                    yield ScoreTrend()
                    yield NextActions()

                # Separator
                yield Static(
                    "\u2500" * 300,
                    id="pet-separator",
                )

                # Middle row: Battle Log (left) | Target Landscape + Sniper Queue (right)
                with Horizontal(id="pet-mid-row"):
                    yield BattleLog(id="pet-mid-left")
                    yield Static("\u2502", id="pet-mid-divider")
                    with Vertical(id="pet-mid-right"):
                        yield TargetLandscape()
                        yield SniperQueue()

                # Bottom separator
                yield Static(
                    "\u2500" * 300,
                    id="pet-separator-2",
                )

                # Bottom row: Training (left) | Signals (right)
                with Horizontal(id="pet-bottom-row"):
                    yield TrainingStatus(id="pet-bottom-left")
                    yield Static("\u2502", id="pet-bottom-divider")
                    yield PetSignals(id="pet-bottom-right")

            # -- Overview View (Bakery-style) ----------------------
            with Vertical(id="overview"):
                yield Static("FrenPet \u00b7 Overview", id="fpo-title")
                yield FPOverviewHero()
                with Horizontal(id="fpo-middle-row"):
                    yield FPOverviewLeaderboard()
                    with Vertical(id="fpo-right-col"):
                        yield FPScoreTrends()
                        yield FPGameSignals()
                yield Static("\u2500" * 300, id="fpo-separator")
                with Horizontal(id="fpo-bottom-row"):
                    yield FPBattleActivity()
                    yield FPBestPlays()

        # Status bar
        yield StatusBar()

    _current_pet_index: int = 0
    _last_data: dict | None = None

    def on_screen_resume(self) -> None:
        """Start polling when this screen is active."""
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        # Update status bar with current theme name
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("frenpet \u00b7 base")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        """Stop polling when switching away."""
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        """Trigger an immediate refresh when the screen appears."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")

    def _schedule_refresh(self) -> None:
        """Schedule a refresh via a worker so it runs async."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")

    async def _do_refresh(self) -> None:
        """Fetch data and update all widgets across all 3 views."""
        try:
            data = await self._manager.fetch_and_compute()
        except Exception as exc:
            logger.error("FrenPet refresh failed: %s", exc)
            # Update status bar to reflect the error
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=self._manager._error_count,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Store for pet navigation
        self._last_data = data

        # Update all three views
        try:
            self.update_general_view(data)
        except Exception as exc:
            logger.warning("Failed to update General view: %s", exc)

        try:
            self.update_wallet_view(data)
        except Exception as exc:
            logger.warning("Failed to update Wallet view: %s", exc)

        try:
            self.update_pet_view(data)
        except Exception as exc:
            logger.warning("Failed to update Pet view: %s", exc)

        try:
            self.update_overview_view(data)
        except Exception as exc:
            logger.warning("Failed to update Overview view: %s", exc)

        # Update status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data["last_updated_seconds_ago"],
                error_count=data["error_count"],
                poll_interval=data["poll_interval"],
            )
        except Exception as exc:
            logger.warning("Failed to update StatusBar: %s", exc)

    def action_refresh(self) -> None:
        """Immediate refresh triggered by the 'r' keybinding."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")

    def action_show_general(self) -> None:
        self.query_one(ContentSwitcher).current = "general"
        self._update_selector(1)

    def action_show_wallet(self) -> None:
        self.query_one(ContentSwitcher).current = "wallet"
        self._update_selector(2)

    def action_show_pet(self) -> None:
        self.query_one(ContentSwitcher).current = "pet"
        self._update_selector(3)

    def action_show_overview(self) -> None:
        self.query_one(ContentSwitcher).current = "overview"
        self._update_selector(4)

    def _update_selector(self, active: int) -> None:
        labels = ["General", "Wallet", "Pet", "Overview"]
        parts = []
        for i, label in enumerate(labels, 1):
            if i == active:
                parts.append(f"[bold reverse] {i} {label} [/]")
            else:
                parts.append(f"[dim][{i}] {label}[/]")
        self.query_one("#fp-view-selector", Static).update("  ".join(parts))

    # ------------------------------------------------------------------
    # General View data binding
    # ------------------------------------------------------------------

    def update_general_view(self, data: dict) -> None:
        """Push fresh data into General View widgets.

        Called by ``_do_refresh()`` whenever new data arrives.
        """
        # Population overview
        try:
            self.query_one(Population).update_data(
                data.get("population_stats", {}),
            )
        except Exception as exc:
            logger.warning("Failed to update Population: %s", exc)

        # Score distribution
        try:
            self.query_one(ScoreDistribution).update_data(
                data.get("score_distribution", {}),
            )
        except Exception as exc:
            logger.warning("Failed to update ScoreDistribution: %s", exc)

        # Top leaderboard
        try:
            self.query_one(TopLeaderboard).update_data(
                data.get("top_pets", []),
            )
        except Exception as exc:
            logger.warning("Failed to update TopLeaderboard: %s", exc)

        # Battle feed
        try:
            self.query_one(BattleFeed).update_data(
                data.get("recent_attacks", []),
                data.get("global_battle_rate", 0.0),
            )
        except Exception as exc:
            logger.warning("Failed to update BattleFeed: %s", exc)

        # Game stats
        try:
            self.query_one(GameStats).update_data(
                data.get("population_stats", {}),
            )
        except Exception as exc:
            logger.warning("Failed to update GameStats: %s", exc)

        # Pets in context
        try:
            self.query_one(PetsInContext).update_data(
                data.get("pet_ranks", {}),
                data.get("managed_pets", []),
            )
        except Exception as exc:
            logger.warning("Failed to update PetsInContext: %s", exc)

        # Market conditions
        try:
            self.query_one(MarketConditions).update_data(
                data.get("market_conditions", {}),
            )
        except Exception as exc:
            logger.warning("Failed to update MarketConditions: %s", exc)

    # ------------------------------------------------------------------
    # Wallet View data binding
    # ------------------------------------------------------------------

    def update_wallet_view(self, data: dict) -> None:
        """Push fresh data from FrenPetManager.fetch_and_compute() into wallet widgets.

        Called by the app's polling loop whenever new data arrives.
        """
        managed_pets = data.get("managed_pets", [])
        pet_evaluations = data.get("pet_evaluations", {})
        pet_velocities = data.get("pet_velocities", {})
        pet_score_histories = data.get("pet_score_histories", {})
        total_score = data.get("total_score", 0.0)
        alerts = data.get("alerts", [])
        recent_attacks = data.get("recent_attacks", [])

        # -- Header --------------------------------------------------------
        header = self.query_one("#wallet-header", Static)
        if not managed_pets:
            header.update("[dim]No wallet configured[/]")
            return

        owner = managed_pets[0].owner
        short_addr = (
            f"{owner[:6]}...{owner[-4:]}" if len(owner) > 10 else owner
        )
        pet_count = len(managed_pets)
        header.update(
            f"WALLET: {short_addr}"
            f"    [dim]{pet_count} pet{'s' if pet_count != 1 else ''}[/]"
        )

        # -- Pet cards -----------------------------------------------------
        pet_row = self.query_one("#wallet-pet-row", Horizontal)

        existing_ids = {w.pet_id for w in pet_row.query(PetCard)}
        needed_ids = {p.id for p in managed_pets}

        # Remove cards for pets no longer managed.
        for card in list(pet_row.query(PetCard)):
            if card.pet_id not in needed_ids:
                card.remove()

        # Add cards for new pets.
        for pet in managed_pets:
            if pet.id not in existing_ids:
                pet_row.mount(PetCard(pet.id, id=f"pet-card-{pet.id}"))

        # Update all cards with latest data.
        for pet in managed_pets:
            try:
                card = pet_row.query_one(f"#pet-card-{pet.id}", PetCard)
            except Exception:
                continue

            eval_data = pet_evaluations.get(pet.id, {})
            phase = eval_data.get("phase", "Hatchling")
            tod_status = eval_data.get(
                "tod_status",
                {"hours_remaining": 0.0, "status": "critical", "color": "red"},
            )
            velocity = pet_velocities.get(pet.id, 0.0)
            win_rate = eval_data.get("battle_efficiency", 0.0)
            history = pet_score_histories.get(pet.id, [])

            card.update_data(pet, phase, tod_status, velocity, win_rate, history)

        # -- Aggregate stats -----------------------------------------------
        self.query_one(AggregateStats).update_data(
            managed_pets, pet_velocities, total_score,
        )

        # -- Action queue --------------------------------------------------
        self.query_one(ActionQueue).update_data(managed_pets)

        # -- Wallet activity -----------------------------------------------
        managed_ids = {p.id for p in managed_pets}
        wallet_attacks = [
            a for a in recent_attacks
            if a.get("attacker_id") in managed_ids
            or a.get("defender_id") in managed_ids
        ]
        self.query_one(WalletActivity).update_data(wallet_attacks)

        # -- Alerts --------------------------------------------------------
        self.query_one(AlertsPanel).update_data(alerts)

    # ------------------------------------------------------------------
    # Pet View navigation
    # ------------------------------------------------------------------

    def action_prev_pet(self) -> None:
        """Cycle to the previous managed pet (wraps around)."""
        if not self._last_data:
            return
        managed = self._last_data.get("managed_pets", [])
        if not managed:
            return
        self._current_pet_index = (self._current_pet_index - 1) % len(managed)
        self.update_pet_view(self._last_data)

    def action_next_pet(self) -> None:
        """Cycle to the next managed pet (wraps around)."""
        if not self._last_data:
            return
        managed = self._last_data.get("managed_pets", [])
        if not managed:
            return
        self._current_pet_index = (self._current_pet_index + 1) % len(managed)
        self.update_pet_view(self._last_data)

    # ------------------------------------------------------------------
    # Pet View data binding
    # ------------------------------------------------------------------

    def update_pet_view(self, data: dict) -> None:
        """Push fresh data into Pet View widgets for the currently selected pet.

        Called by the app's polling loop whenever new data arrives.
        """
        self._last_data = data
        managed_pets = data.get("managed_pets", [])
        pet_evaluations = data.get("pet_evaluations", {})
        pet_velocities = data.get("pet_velocities", {})
        pet_score_histories = data.get("pet_score_histories", {})
        recent_attacks = data.get("recent_attacks", [])
        market_conditions = data.get("market_conditions", {})
        threat_levels = data.get("threat_levels", {})
        all_scores = data.get("all_scores", [])
        population_pets = data.get("population_pets", [])

        header = self.query_one("#pet-header", Static)

        if not managed_pets:
            header.update("[dim]No pets managed[/]")
            return

        # Clamp index in case managed list shrank
        if self._current_pet_index >= len(managed_pets):
            self._current_pet_index = 0

        pet = managed_pets[self._current_pet_index]

        # -- Header --------------------------------------------------------
        eval_data = pet_evaluations.get(pet.id, {})
        phase = eval_data.get("phase", determine_growth_phase(pet.score))
        header.update(
            f"PET #{pet.id}"
            f"  [dim]\u00b7[/]  {phase}"
            f"  [dim]({self._current_pet_index + 1}/{len(managed_pets)})[/]"
        )

        # -- Pet Stats -----------------------------------------------------
        tod_status = eval_data.get(
            "tod_status",
            calculate_tod_status(pet.time_until_starving),
        )
        try:
            self.query_one(PetStats).update_data(pet, phase, tod_status)
        except Exception:
            pass

        # -- Score Trend ---------------------------------------------------
        history = pet_score_histories.get(pet.id, [])
        velocity = pet_velocities.get(pet.id, 0.0)
        try:
            self.query_one(ScoreTrend).update_data(history, velocity)
        except Exception:
            pass

        # -- Next Actions --------------------------------------------------
        try:
            self.query_one(NextActions).update_data(pet)
        except Exception:
            pass

        # -- Battle Log ----------------------------------------------------
        try:
            self.query_one(BattleLog).update_data(recent_attacks, pet.id)
        except Exception:
            pass

        # -- Target Landscape ----------------------------------------------
        try:
            self.query_one(TargetLandscape).update_data(market_conditions)
        except Exception:
            pass

        # -- Sniper Queue --------------------------------------------------
        try:
            self.query_one(SniperQueue).update_data(
                population_pets, pet.attack_points, pet.defense_points,
                float(pet.score),
            )
        except Exception:
            pass

        # -- Training Status -----------------------------------------------
        try:
            self.query_one(TrainingStatus).update_data(pet)
        except Exception:
            pass

        # -- Pet Signals ---------------------------------------------------
        threat_info = threat_levels.get(pet.id, {
            "threat_count": 0, "threat_level": "low",
        })
        rank_info = {}
        if all_scores:
            rank_info = calculate_rank(float(pet.score), all_scores)
        else:
            rank_info = {"rank": 0, "total": 0, "distance_to_next": 0.0}

        battle_efficiency = eval_data.get(
            "battle_efficiency",
            calculate_battle_efficiency(pet.win_qty, pet.loss_qty),
        )
        recommendation = eval_data.get("recommendation", "")
        if not recommendation:
            recommendation = generate_pet_recommendation(
                phase,
                battle_efficiency,
                velocity,
                threat_info.get("threat_level", "low"),
                market_conditions,
            )

        try:
            self.query_one(PetSignals).update_data(
                eval_data, threat_info, velocity, rank_info, recommendation,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Overview View data binding
    # ------------------------------------------------------------------

    def update_overview_view(self, data: dict) -> None:
        """Push fresh data into Overview (Bakery-style) widgets.

        Uses ``.get()`` with defaults for all keys so the view works
        even before the data manager adds the overview_* fields.
        """
        top_pets = data.get("top_pets", [])
        population_stats = data.get("population_stats", {})

        # Hero metrics
        try:
            fp_reward_pool = data.get("fp_reward_pool", 0.0)
            game_start_ts = data.get("game_start_timestamp", 1709251200)
            leader_pet = data.get("top_pet") or (top_pets[0] if top_pets else None)
            self.query_one(FPOverviewHero).update_data(
                fp_reward_pool=fp_reward_pool,
                game_start_timestamp=game_start_ts,
                top_pet=leader_pet,
            )
        except Exception as exc:
            logger.warning("Failed to update FPOverviewHero: %s", exc)

        # Leaderboard
        try:
            self.query_one(FPOverviewLeaderboard).update_data(top_pets)
        except Exception as exc:
            logger.warning("Failed to update FPOverviewLeaderboard: %s", exc)

        # Score trends
        try:
            score_histories = data.get("overview_score_histories", {})
            self.query_one(FPScoreTrends).update_data(
                top_pets=top_pets,
                score_histories=score_histories,
            )
        except Exception as exc:
            logger.warning("Failed to update FPScoreTrends: %s", exc)

        # Game signals
        try:
            self.query_one(FPGameSignals).update_data(
                battle_rate=data.get("global_battle_rate", 0.0),
                win_rate=data.get("global_win_rate", 50.0),
                hibernation_rate=data.get("hibernation_rate", 0.0),
                dominance=data.get("top_dominance", 1.0),
                recommendation=data.get("overview_recommendation", ""),
            )
        except Exception as exc:
            logger.warning("Failed to update FPGameSignals: %s", exc)

        # Battle activity
        try:
            self.query_one(FPBattleActivity).update_data(
                recent_attacks=data.get("recent_attacks", []),
            )
        except Exception as exc:
            logger.warning("Failed to update FPBattleActivity: %s", exc)

        # Best plays
        try:
            self.query_one(FPBestPlays).update_data(
                top_earners=data.get("top_earners", []),
                rising_stars=data.get("rising_stars", []),
            )
        except Exception as exc:
            logger.warning("Failed to update FPBestPlays: %s", exc)
