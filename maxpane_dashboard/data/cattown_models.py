"""Pydantic models for Cat Town Fishing dashboard data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_WEI = 10**18


class KibbleEconomy(BaseModel):
    """KIBBLE token economy snapshot."""

    model_config = ConfigDict(frozen=True)

    price_usd: float
    total_supply: float
    circulating: float
    burned: float
    staked_total: float
    price_change_24h: float

    @classmethod
    def from_raw(
        cls,
        price_usd: float,
        total_supply_wei: int,
        burned_wei: int,
        staked_wei: int,
        price_change_24h: float = 0.0,
    ) -> KibbleEconomy:
        total = total_supply_wei / _WEI
        burned = burned_wei / _WEI
        staked = staked_wei / _WEI
        return cls(
            price_usd=price_usd,
            total_supply=total,
            circulating=total - burned,
            burned=burned,
            staked_total=staked,
            price_change_24h=price_change_24h,
        )


class CompetitionEntry(BaseModel):
    """Individual fishing competition leaderboard entry."""

    model_config = ConfigDict(frozen=True)

    fisher_address: str
    fish_weight_kg: float
    fish_species: str
    rarity: str
    rank: int


class CompetitionState(BaseModel):
    """Weekly competition state."""

    model_config = ConfigDict(frozen=True)

    week_number: int
    is_active: bool
    total_volume_kibble: float
    prize_pool_kibble: float      # 10% of total volume
    treasure_pool_kibble: float   # 70% of total volume
    staker_revenue_kibble: float  # 10% of total volume
    num_participants: int
    start_time: int
    end_time: int
    entries: list[CompetitionEntry] = []


class FishCatch(BaseModel):
    """Individual fish catch event from onchain logs."""

    model_config = ConfigDict(frozen=True)

    tx_hash: str
    fisher_address: str
    species: str
    weight_kg: float
    rarity: str
    timestamp: int
    block_number: int


class StakingState(BaseModel):
    """KIBBLE staking / revenue share state."""

    model_config = ConfigDict(frozen=True)

    total_staked: float
    user_staked: float
    pending_rewards: float
    weekly_revenue: float

    @classmethod
    def from_raw(
        cls,
        total_staked_wei: int,
        user_staked_wei: int,
        pending_rewards_wei: int,
        weekly_revenue_wei: int,
    ) -> StakingState:
        return cls(
            total_staked=total_staked_wei / _WEI,
            user_staked=user_staked_wei / _WEI,
            pending_rewards=pending_rewards_wei / _WEI,
            weekly_revenue=weekly_revenue_wei / _WEI,
        )


class CatTownSnapshot(BaseModel):
    """Top-level container for all Cat Town data in a single poll cycle."""

    model_config = ConfigDict(frozen=True)

    fetched_at: float
    kibble: KibbleEconomy
    competition: CompetitionState
    recent_catches: list[FishCatch] = []
    staking: StakingState
