"""Pydantic v2 models for FrenPet game data.

All models are frozen (immutable) and map to the JSON shapes returned
by the Ponder GraphQL indexer at https://api.pet.game.  Field names
use snake_case; a ``from_api`` classmethod on each model handles the
camelCase-to-snake_case translation from raw API dicts.

Score convention
----------------
Ponder returns raw scores with 12 decimal places.  Values above 1e15
are assumed raw and divided by 1e12 for display.  The ``score`` field
on ``FrenPet`` always holds the *display* value.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

_RAW_SCORE_THRESHOLD = 1_000_000_000_000_000  # 1e15
_SCORE_DIVISOR = 1_000_000_000_000           # 1e12


def normalize_score(raw: int | str) -> int:
    """Convert a Ponder raw score to display scale.

    If the value exceeds 1e15 it is treated as a raw 12-decimal value
    and divided accordingly.  Smaller values pass through unchanged.
    """
    value = int(raw) if isinstance(raw, str) else raw
    if value > _RAW_SCORE_THRESHOLD:
        return value // _SCORE_DIVISOR
    return value


# ---------------------------------------------------------------------------
# Core pet model
# ---------------------------------------------------------------------------

class FrenPet(BaseModel):
    """A single pet from the Ponder GraphQL indexer."""

    model_config = ConfigDict(frozen=True)

    id: int
    score: int
    """Display-scale points (raw / 1e12 when applicable)."""
    attack_points: int
    defense_points: int
    level: int
    status: int
    """Pet lifecycle status: 0 = alive, 2 = hibernated."""
    last_attacked: int
    """Unix timestamp of last incoming attack."""
    last_attack_used: int
    """Unix timestamp of last outgoing attack."""
    shield_expires: int
    """Unix timestamp when shield protection ends."""
    time_until_starving: int
    """Unix timestamp (time-of-death) when the pet starves."""
    staking_perks_until: int
    """Unix timestamp when staking perks expire."""
    wheel_last_spin: int
    """Unix timestamp of last wheel spin."""
    pet_wins: int
    win_qty: int
    loss_qty: int
    shrooms: int
    name: str
    owner: str
    """Wallet address of the pet owner (lowercase hex)."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> FrenPet:
        """Construct from a raw Ponder GraphQL pet dict (camelCase keys)."""
        return cls(
            id=int(data["id"]),
            score=normalize_score(data.get("score", 0)),
            attack_points=int(data.get("attackPoints", 0)),
            defense_points=int(data.get("defensePoints", 0)),
            level=int(data.get("level", 0)),
            status=int(data.get("status", 0)),
            last_attacked=int(data.get("lastAttacked", 0)),
            last_attack_used=int(data.get("lastAttackUsed", 0)),
            shield_expires=int(data.get("shieldExpires", 0)),
            time_until_starving=int(data.get("timeUntilStarving", 0)),
            staking_perks_until=int(data.get("stakingPerksUntil", 0)),
            wheel_last_spin=int(data.get("wheelLastSpin", 0)),
            pet_wins=int(data.get("petWins", 0)),
            win_qty=int(data.get("winQty", 0)),
            loss_qty=int(data.get("lossQty", 0)),
            shrooms=int(data.get("shrooms", 0)),
            name=data.get("name", ""),
            owner=data.get("owner", ""),
        )


# ---------------------------------------------------------------------------
# Population aggregate
# ---------------------------------------------------------------------------

class FrenPetPopulation(BaseModel):
    """Snapshot of the entire pet population with computed stats."""

    model_config = ConfigDict(frozen=True)

    total: int
    active: int
    """Alive (status == 0) and not yet starving."""
    hibernated: int
    """Hibernated (status == 2) or past time-of-death."""
    shielded: int
    """Pets with an active shield (shield_expires > now)."""
    in_cooldown: int
    """Pets attacked within the last hour (last_attacked > now - 3600)."""
    pets: tuple[FrenPet, ...]

    @classmethod
    def from_pets(cls, pets: list[FrenPet], now: float | None = None) -> FrenPetPopulation:
        """Compute population stats from a list of pets.

        Parameters
        ----------
        pets:
            Full list of pets retrieved from the indexer.
        now:
            Unix timestamp to use as "now".  Defaults to ``time.time()``.
        """
        ts = int(now if now is not None else time.time())
        cooldown_threshold = ts - 3600

        total = len(pets)
        active = 0
        hibernated = 0
        shielded = 0
        in_cooldown = 0

        for pet in pets:
            # status=0 means alive; time_until_starving=0 means unknown (indexer DB)
            if pet.status == 0 and (pet.time_until_starving == 0 or pet.time_until_starving > ts):
                active += 1
            else:
                hibernated += 1

            if pet.shield_expires > ts:
                shielded += 1

            if pet.last_attacked > cooldown_threshold:
                in_cooldown += 1

        return cls(
            total=total,
            active=active,
            hibernated=hibernated,
            shielded=shielded,
            in_cooldown=in_cooldown,
            pets=tuple(pets),
        )


# ---------------------------------------------------------------------------
# Unified dashboard snapshot
# ---------------------------------------------------------------------------

class FrenPetSnapshot(BaseModel):
    """Unified snapshot for dashboard consumption.

    Combines population stats, managed pets, and the top-10 leaderboard
    into a single immutable object.
    """

    model_config = ConfigDict(frozen=True)

    population: FrenPetPopulation
    managed_pets: tuple[FrenPet, ...]
    """User's own pets (empty tuple in spectator mode)."""
    top_pets: tuple[FrenPet, ...]
    """Top 10 pets by score."""
    fp_reward_pool: float = 0.0
    """FP token balance of the Diamond contract (reward pool)."""
    fetched_at: float
    """Unix timestamp when this snapshot was created."""
