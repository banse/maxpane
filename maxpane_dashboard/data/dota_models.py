"""Pydantic models for DOTA dashboard data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DOTAAbility(BaseModel):
    """Single hero ability."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    level: int


class DOTAHero(BaseModel):
    """Hero unit on the battlefield."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str
    faction: str
    hero_class: str = Field(alias="class")
    lane: str
    hp: int
    max_hp: int = Field(alias="maxHp")
    alive: bool
    level: int
    xp: int
    xp_to_next: int = Field(alias="xpToNext")
    abilities: list[DOTAAbility]
    ability_choices: list[str] = Field(
        default_factory=list, alias="abilityChoices"
    )


class DOTALane(BaseModel):
    """Lane troop counts per faction."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    human: int
    orc: int
    frontline: int


class DOTATower(BaseModel):
    """Defensive tower on a lane."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    faction: str
    lane: str
    hp: int
    max_hp: int = Field(alias="maxHp")
    alive: bool


class DOTABase(BaseModel):
    """Faction base structure."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    hp: int
    max_hp: int = Field(alias="maxHp")


class DOTAGameState(BaseModel):
    """Full game state for a single tick."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    tick: int
    agents: dict[str, list[str]]
    lanes: dict[str, DOTALane]
    towers: list[DOTATower]
    bases: dict[str, DOTABase]
    heroes: list[DOTAHero]
    winner: str | None


class DOTALeaderboardEntry(BaseModel):
    """Single row in the leaderboard."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    rank: int = 0
    name: str = ""
    wins: int = 0
    games: int = 0
    win_rate: float = 0.0
    player_type: str = "Human"


class DOTASnapshot(BaseModel):
    """Top-level container for all DOTA data in a single poll cycle."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    fetched_at: float
    game_state: DOTAGameState | None = None
    leaderboard: list[DOTALeaderboardEntry] = []
    token_price_usd: float | None = None
    token_price_change_24h: float | None = None
    token_market_cap: float | None = None
