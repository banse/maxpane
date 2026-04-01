"""Pydantic models for Onchain Monsters dashboard data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_WEI = 10**18


class OCMCollectionStats(BaseModel):
    """NFT collection mint and supply stats."""

    model_config = ConfigDict(frozen=True)

    total_supply: int
    max_supply: int
    current_minting_cost: int  # raw wei (OCMD 18 decimals)
    burned_count: int
    net_supply: int            # total_supply - burned_count
    remaining: int             # max_supply - total_supply
    minted_pct: float          # total_supply / max_supply * 100


class OCMStakingStats(BaseModel):
    """OCMD staking and emission stats."""

    model_config = ConfigDict(frozen=True)

    total_staked: int
    ocmd_total_supply: float   # converted from wei
    daily_emission: float      # total_staked * 1.0
    staking_ratio: float       # percentage
    days_to_earn_mint: float


class OCMActivityEvent(BaseModel):
    """Single onchain activity event."""

    model_config = ConfigDict(frozen=True)

    tx_hash: str
    block_number: int
    timestamp: int
    event_type: str            # "mint", "burn", "stake", "unstake"
    actor_address: str
    token_id: int | None
    count: int


class OCMSnapshot(BaseModel):
    """Top-level container for all Onchain Monsters data in a single poll cycle."""

    model_config = ConfigDict(frozen=True)

    fetched_at: float
    collection: OCMCollectionStats
    staking: OCMStakingStats
    holder_count: int
    faucet_open: bool = True
    recent_events: list[OCMActivityEvent] = []
