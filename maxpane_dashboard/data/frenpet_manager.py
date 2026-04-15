"""Orchestrates FrenPet data fetching, caching, and analytics computation.

The ``FrenPetManager`` is the single coordination point between the async
API client, the time-series cache, and the analytics modules.  It exposes
one public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.frenpet_population import (
    calculate_market_conditions,
    calculate_population_stats,
    calculate_score_distribution,
    calculate_threat_level,
)
from maxpane_dashboard.analytics.frenpet_signals import (
    calculate_battle_efficiency,
    calculate_rank,
    calculate_tod_status,
    calculate_velocity,
    determine_growth_phase,
    generate_pet_recommendation,
)
from maxpane_dashboard.data.frenpet_cache import FrenPetCache
from maxpane_dashboard.data.frenpet_client import FrenPetClient
from maxpane_dashboard.data.frenpet_models import FrenPet, FrenPetSnapshot
from maxpane_dashboard.data.price import PriceClient

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "frenpet_cache.json"


def _pet_to_analytics_dict(pet: FrenPet, now: float) -> dict[str, Any]:
    """Convert a FrenPet model to the dict format expected by population analytics.

    The analytics functions use dict-style access with keys:
    ``score``, ``atk``, ``def``, ``hibernated``, ``shielded``, ``in_cooldown``.
    """
    return {
        "id": pet.id,
        "score": pet.score,
        "atk": pet.attack_points,
        "def": pet.defense_points,
        "hibernated": pet.status != 0 or (pet.time_until_starving > 0 and pet.time_until_starving <= now),
        "shielded": pet.shield_expires > now,
        "in_cooldown": pet.last_attacked > (now - 3600),
        "name": pet.name,
        "owner": pet.owner,
    }


class FrenPetManager:
    """Orchestrates FrenPet data fetching, caching, and analytics.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    wallet_address:
        If provided, the manager fetches the user's managed pets.
        When ``None`` (spectator mode), ``managed_pets`` is empty.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        wallet_address: str | None = None,
    ) -> None:
        self.client = FrenPetClient()
        self.cache = FrenPetCache(max_history=120)
        self._price_client = PriceClient()
        self._poll_interval = poll_interval
        self._wallet_address = wallet_address
        self._error_count = 0

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a dict with keys organized by view:

        General view:
            ``population_stats``, ``score_distribution``, ``top_pets``,
            ``recent_attacks``, ``global_battle_rate``.

        Wallet view (only if wallet_address set):
            ``managed_pets``, ``total_score``, ``combined_win_rate``,
            ``pet_score_histories``, ``alerts``.

        Pet view (per managed pet):
            ``pet_evaluations``, ``market_conditions``, ``threat_levels``.

        Signals:
            ``pet_velocities``, ``pet_ranks``.

        Meta:
            ``error_count``, ``last_updated_seconds_ago``, ``poll_interval``.
        """
        try:
            snapshot = await self.client.fetch_snapshot(
                self._wallet_address, remote_only=True,
            )
        except Exception:
            self._error_count += 1
            raise

        now = snapshot.fetched_at

        # -- Pet name lookup (id -> name) for activity feed ----------------
        pet_names: dict[int, str] = {
            p.id: p.name for p in snapshot.population.pets if p.name
        }

        # -- Convert all pets to analytics dicts --------------------------
        all_pet_dicts = [
            _pet_to_analytics_dict(p, now)
            for p in snapshot.population.pets
        ]
        all_scores = [float(p.score) for p in snapshot.population.pets]

        # -- Population-wide analytics ------------------------------------
        population_stats = _safe_call(
            calculate_population_stats, all_pet_dicts,
            default={"total": 0, "active": 0, "hibernated": 0,
                     "avg_score": 0.0, "median_score": 0.0,
                     "avg_atk": 0.0, "avg_def": 0.0, "total_score": 0.0},
        )
        score_distribution = _safe_call(
            calculate_score_distribution, all_pet_dicts,
            default={},
        )

        # -- Recent attacks (best-effort) ---------------------------------
        recent_attacks: list[dict[str, Any]] = []
        global_battle_rate = 0.0
        try:
            recent_attacks = await self.client.get_recent_attacks(limit=50)
            if recent_attacks and len(recent_attacks) >= 2:
                first_ts = recent_attacks[-1].get("timestamp", 0)
                last_ts = recent_attacks[0].get("timestamp", 0)
                span_hours = max((last_ts - first_ts) / 3600.0, 0.001)
                global_battle_rate = len(recent_attacks) / span_hours
        except Exception as exc:
            logger.warning("Failed to fetch recent attacks: %s", exc)

        # -- Update cache with population + battle rate history -----------
        self.cache.update(snapshot, battle_rate=global_battle_rate)

        # -- Managed pets analytics ---------------------------------------
        managed_pets = list(snapshot.managed_pets)
        total_score = 0.0
        combined_wins = 0
        combined_losses = 0
        pet_score_histories: dict[int, list[tuple[float, float]]] = {}
        pet_evaluations: dict[int, dict[str, Any]] = {}
        pet_velocities: dict[int, float] = {}
        pet_ranks: dict[int, dict[str, Any]] = {}
        threat_levels: dict[int, dict[str, Any]] = {}
        alerts: list[dict[str, Any]] = []

        # Reference ATK/DEF for market conditions (first managed pet, or zeros)
        ref_atk = 0
        ref_def = 0

        for pet in managed_pets:
            total_score += pet.score
            combined_wins += pet.win_qty
            combined_losses += pet.loss_qty

            if ref_atk == 0:
                ref_atk = pet.attack_points
                ref_def = pet.defense_points

            # Score history from cache
            history = self.cache.get_pet_score_history(pet.id)
            pet_score_histories[pet.id] = history

            # Growth phase
            phase = _safe_call(
                determine_growth_phase, float(pet.score),
                default="Hatchling",
            )

            # TOD status
            tod = _safe_call(
                calculate_tod_status, pet.time_until_starving,
                default={"hours_remaining": 0.0, "status": "critical", "color": "red"},
            )

            # Battle efficiency
            efficiency = _safe_call(
                calculate_battle_efficiency, pet.win_qty, pet.loss_qty,
                default=0.0,
            )

            # Velocity
            velocity = _safe_call(
                calculate_velocity, history,
                default=0.0,
            )
            pet_velocities[pet.id] = velocity

            # Rank
            rank_info = _safe_call(
                calculate_rank, float(pet.score), all_scores,
                default={"rank": 0, "total": 0, "percentile": 0.0,
                         "distance_to_next": 0.0, "distance_from_prev": 0.0},
            )
            pet_ranks[pet.id] = rank_info

            # Threat level
            threat = _safe_call(
                calculate_threat_level, all_pet_dicts,
                float(pet.score), pet.defense_points,
                default={"threat_count": 0, "threat_level": "low"},
            )
            threat_levels[pet.id] = threat

            pet_evaluations[pet.id] = {
                "name": pet.name,
                "rank": rank_info.get("rank", 0),
                "phase": phase,
                "tod_status": tod,
                "battle_efficiency": efficiency,
                "velocity": velocity,
            }

            # -- Alerts: TOD warnings ------------------------------------
            tod_hours = tod.get("hours_remaining", float("inf"))
            if tod_hours < 6.0:
                alerts.append({
                    "pet_id": pet.id,
                    "pet_name": pet.name,
                    "type": "tod_critical",
                    "severity": "critical",
                    "message": (
                        f"{pet.name} (#{pet.id}) starves in "
                        f"{tod_hours:.1f}h -- feed immediately"
                    ),
                })
            elif tod_hours < 24.0:
                alerts.append({
                    "pet_id": pet.id,
                    "pet_name": pet.name,
                    "type": "tod_warning",
                    "severity": "warning",
                    "message": (
                        f"{pet.name} (#{pet.id}) starves in "
                        f"{tod_hours:.1f}h -- consider feeding"
                    ),
                })

        # Combined win rate
        combined_total = combined_wins + combined_losses
        combined_win_rate = (
            (combined_wins / combined_total * 100.0) if combined_total > 0 else 0.0
        )

        # -- Wallet rewards (on-chain ETH/FP data) -----------------------
        wallet_rewards: dict[str, Any] | None = None
        if self._wallet_address and managed_pets:
            try:
                wallet_rewards = await self._fetch_wallet_rewards(
                    managed_pets, self._wallet_address,
                )
            except Exception as exc:
                logger.warning("Wallet rewards fetch failed: %s", exc)

        # -- Market conditions --------------------------------------------
        market_conditions = _safe_call(
            calculate_market_conditions, all_pet_dicts, ref_atk, ref_def,
            default={
                "available_targets": 0, "sweet_spot_count": 0,
                "avg_opponent_def": 0.0, "hibernation_rate": 0.0,
                "shield_rate": 0.0, "target_density": "low",
                "verdict": "conservative",
            },
        )

        # -- Overview computations ---------------------------------------
        top_pets = list(snapshot.top_pets)
        fp_reward_pool = snapshot.fp_reward_pool

        # Top pet (#1 by score)
        top_pet: FrenPet | None = top_pets[0] if top_pets else None

        # Total score across all pets in population
        overview_total_score = sum(
            float(p.score) for p in snapshot.population.pets
        )

        # Global win rate from recent attacks
        if recent_attacks:
            attack_wins = sum(
                1 for a in recent_attacks if a.get("attacker_won")
            )
            global_win_rate = (
                (attack_wins / len(recent_attacks) * 100.0)
                if len(recent_attacks) > 0
                else 50.0
            )
        else:
            global_win_rate = 50.0

        # Shield rate (% of pets with active shield — reliable on-chain data)
        _now = time.time()
        pop_total = len(snapshot.population.pets)
        shielded_count = sum(
            1 for p in snapshot.population.pets
            if (p.shield_expires or 0) > _now
        )
        shield_rate = (
            (shielded_count / pop_total * 100.0) if pop_total > 0 else 0.0
        )

        # Top dominance (#1 score / #2 score)
        if len(top_pets) >= 2 and top_pets[1].score > 0:
            top_dominance = top_pets[0].score / top_pets[1].score
        else:
            top_dominance = float("inf")

        # Overview recommendation
        overview_recommendation = _generate_overview_recommendation(
            shield_rate=shield_rate,
            top_dominance=top_dominance,
            global_battle_rate=global_battle_rate,
        )

        # Top fighters: best win rate among pets with 10+ battles
        active_fighters = [
            p for p in snapshot.population.pets
            if (p.win_qty + p.loss_qty) >= 10 and p.status == 0
        ]
        active_fighters.sort(
            key=lambda p: p.win_qty / max(1, p.win_qty + p.loss_qty),
            reverse=True,
        )
        top_earners = [
            (p.name or f"#{p.id}", f"{p.win_qty / (p.win_qty + p.loss_qty) * 100:.0f}%")
            for p in active_fighters[:10]
        ]

        # Most active: pets with most total battles (the grinders)
        by_battles = sorted(
            [p for p in snapshot.population.pets if p.status == 0],
            key=lambda p: p.win_qty + p.loss_qty,
            reverse=True,
        )
        rising_stars = [
            (p.name or f"#{p.id}", f"{p.win_qty + p.loss_qty:,}")
            for p in by_battles[:10]
        ]

        # Score histories for top pets (for leaderboard sparklines)
        top_pet_ids = [p.id for p in top_pets[:5]]
        overview_score_histories = self.cache.get_top_pet_score_histories(
            top_pet_ids
        )

        # -- Staleness ---------------------------------------------------
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # -- Assemble widget data dict -----------------------------------
        return {
            # General view
            "population_stats": population_stats,
            "score_distribution": score_distribution,
            "top_pets": top_pets,
            "recent_attacks": recent_attacks,
            "global_battle_rate": global_battle_rate,
            # Wallet view
            "managed_pets": managed_pets,
            "total_score": total_score,
            "combined_win_rate": combined_win_rate,
            "pet_score_histories": pet_score_histories,
            "alerts": alerts,
            # Pet view
            "pet_evaluations": pet_evaluations,
            "market_conditions": market_conditions,
            "threat_levels": threat_levels,
            # Signals
            "pet_velocities": pet_velocities,
            "pet_ranks": pet_ranks,
            # Overview hero cards
            "fp_reward_pool": fp_reward_pool,
            "game_start_timestamp": 1709251200,
            "top_pet": top_pet,
            "overview_total_score": overview_total_score,
            # Overview signals
            "global_win_rate": global_win_rate,
            "shield_rate": shield_rate,
            "top_dominance": top_dominance,
            "overview_recommendation": overview_recommendation,
            # Overview best plays
            "top_earners": top_earners,
            "rising_stars": rising_stars,
            # Overview sparklines
            "overview_score_histories": overview_score_histories,
            "active_pets_history": list(self.cache.active_pets_history),
            "total_score_history": list(self.cache.total_score_history),
            "battle_rate_history": list(self.cache.battle_rate_history),
            # Name lookup
            "pet_names": pet_names,
            # Wallet rewards (on-chain)
            "wallet_rewards": wallet_rewards,
            # Meta
            "error_count": self._error_count,
            "last_updated_seconds_ago": last_updated_seconds_ago,
            "poll_interval": self._poll_interval,
        }

    async def _fetch_wallet_rewards(
        self,
        pets: list[FrenPet],
        wallet_address: str,
    ) -> dict[str, Any]:
        """Fetch on-chain reward data for all managed pets and the wallet.

        Serializes RPC calls with 100ms delays to avoid Base public RPC
        rate limits.  Returns a dict matching the ``wallet_rewards`` shape
        described in the implementation plan.
        """
        _RPC_DELAY = 0.1  # 100ms between calls

        pet_rewards: dict[int, dict[str, Any]] = {}
        total_pending_eth = 0
        total_eth_owed = 0
        total_fp_per_second = 0

        for pet in pets:
            pid = pet.id
            try:
                pending = await self.client.get_pending_eth(pid)
                await asyncio.sleep(_RPC_DELAY)
                owed = await self.client.get_eth_owed(pid)
                await asyncio.sleep(_RPC_DELAY)
                fps = await self.client.get_fp_per_second(pid)
                await asyncio.sleep(_RPC_DELAY)
            except Exception as exc:
                logger.warning("RPC reward read failed for pet %d: %s", pid, exc)
                pending, owed, fps = 0, 0, 0

            pet_rewards[pid] = {
                "pending_eth_wei": pending,
                "eth_owed_wei": owed,
                "fp_per_second": fps,
            }
            total_pending_eth += pending
            total_eth_owed += owed
            total_fp_per_second += fps

        # Global staking pool reads
        try:
            user_shares = await self.client.get_user_shares(wallet_address)
            await asyncio.sleep(_RPC_DELAY)
            total_shares = await self.client.get_total_shares()
            await asyncio.sleep(_RPC_DELAY)
            total_fp_in_pool = await self.client.get_total_fp_in_pool()
        except Exception as exc:
            logger.warning("RPC pool read failed: %s", exc)
            user_shares, total_shares, total_fp_in_pool = 0, 0, 0

        # Pool share percentage
        pool_share_pct = (
            (user_shares / total_shares * 100.0) if total_shares > 0 else 0.0
        )

        # ETH price for USD conversion
        eth_price_usd = await self._price_client.get_eth_usd()

        total_eth_wei = total_pending_eth + total_eth_owed

        return {
            "pet_rewards": pet_rewards,
            "total_pending_eth_wei": total_pending_eth,
            "total_eth_owed_wei": total_eth_owed,
            "total_eth_wei": total_eth_wei,
            "total_fp_per_second": total_fp_per_second,
            "user_shares": user_shares,
            "total_shares": total_shares,
            "total_fp_in_pool": total_fp_in_pool,
            "pool_share_pct": pool_share_pct,
            "eth_price_usd": eth_price_usd,
        }

    def save_cache(self) -> None:
        """Persist cache to disk."""
        self.cache.save_to_file(str(_CACHE_FILE))

    async def close(self) -> None:
        """Shut down the HTTP client and persist cache."""
        self.save_cache()
        await self.client.close()
        await self._price_client.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_overview_recommendation(
    shield_rate: float,
    top_dominance: float,
    global_battle_rate: float,
) -> str:
    """Generate a short recommendation string based on current game state."""
    if shield_rate > 50.0:
        return "Most pets shielded \u2014 fewer exposed targets available"
    if shield_rate < 20.0:
        return "Low shield rate \u2014 many exposed targets for bonking"
    if top_dominance > 3.0:
        return "One pet dominates \u2014 focus on closing the gap"
    if global_battle_rate > 200.0:
        return "Active meta \u2014 battles frequent, train to compete"
    return "Meta is balanced \u2014 focus on training ATK/DEF"


def _safe_call(fn: Any, *args: Any, default: Any = None) -> Any:
    """Call *fn* with *args*, returning *default* on any exception.

    Logs a warning so failures are visible but never crash the dashboard.
    """
    try:
        return fn(*args)
    except Exception as exc:
        logger.warning("Analytics call %s failed: %s", fn.__name__, exc)
        return default
