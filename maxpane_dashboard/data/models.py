"""Pydantic v2 models for the RugPull Bakery blockchain game API.

All models are frozen (immutable) and map directly to the JSON shapes
returned by the game's tRPC endpoints and agent.json bootstrap file.

tRPC response wrapper
---------------------
Most tRPC GET endpoints return data nested as:
    {"result": {"data": {"json": <payload>}}}
The models here represent the *inner* payload (<payload>), not the
wrapper.  A helper ``unwrap_trpc`` function is provided at the bottom
of this module to extract the payload from a raw response dict.

Endpoint parameter notes (discovered via probing 2026-03-27)
------------------------------------------------------------
- leaderboard.getActiveSeason        -> no input needed
- leaderboard.getTopBakeries         -> input={"json":{}}  (empty object required)
- leaderboard.getBakeryById           -> input={"json":{"bakeryId": <int>}}
- leaderboard.getBakeryMembers        -> input={"json":{"bakeryId": <int>, "seasonId": <int>}}
- leaderboard.getActivityFeed         -> input={"json":{"bakeryId": <int>, "seasonId": <int>}}
- leaderboard.getPlayerBakery         -> input={"json":{"address": "<hex>", "seasonId": <int>}}
- leaderboard.getMyBakeryInit         -> NOT PROBED (likely requires wallet auth / session)

Key naming divergence: the tRPC zod schema uses ``bakeryId`` (not ``id``)
for input parameters, even though the response objects use ``id`` as the
primary key.  The original task URLs used ``{"id": 58}`` which returns 400.
"""

from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------

class Season(BaseModel):
    """A single competitive season returned by ``getActiveSeason``.

    The endpoint returns a *list* of Season objects (typically one active).
    Monetary values (seedAmount, prizePool) are stringified wei.
    Time values (startTime, endTime) are stringified unix epoch seconds.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    start_time: str
    """Unix epoch seconds as a string."""
    end_time: str
    """Unix epoch seconds as a string."""
    claim_deadline: str | None
    """Unix epoch seconds as a string, or null if not yet set."""
    protocol_fee_bps: int
    seed_amount: str
    """Prize pool seed in wei (stringified big-int)."""
    results_root: str | None
    """Merkle root for finalized results, null while season is live."""
    finalized: bool
    ended: bool
    is_active: bool
    prize_pool: str
    """Current total prize pool in wei (stringified big-int)."""

    # -- alias mapping from camelCase API fields --
    model_config = ConfigDict(  # type: ignore[assignment]
        frozen=True,
        populate_by_name=True,
        alias_generator=None,
    )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Season:
        """Construct from the raw camelCase API dict."""
        return cls(
            id=data["id"],
            start_time=data["startTime"],
            end_time=data["endTime"],
            claim_deadline=data.get("claimDeadline"),
            protocol_fee_bps=data["protocolFeeBps"],
            seed_amount=data["seedAmount"],
            results_root=data.get("resultsRoot"),
            finalized=data["finalized"],
            ended=data["ended"],
            is_active=data["isActive"],
            prize_pool=data["prizePool"],
        )


# ---------------------------------------------------------------------------
# Boost / Debuff effect models (nested inside Bakery leaderboard entries)
# ---------------------------------------------------------------------------

class ActiveBuff(BaseModel):
    """An active boost effect on a bakery (from ``getTopBakeries``)."""

    model_config = ConfigDict(frozen=True)

    name: str
    multiplier_bps: int
    """Boost multiplier in basis points (e.g. 12500 = 1.25x)."""
    is_shield: bool
    end_time: str
    """Unix epoch seconds as a string."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ActiveBuff:
        return cls(
            name=data["name"],
            multiplier_bps=data["multiplierBps"],
            is_shield=data["isShield"],
            end_time=data["endTime"],
        )


class ActiveDebuff(BaseModel):
    """An active debuff (attack) effect on a bakery."""

    model_config = ConfigDict(frozen=True)

    name: str
    debuff_bps: int
    """Debuff penalty in basis points (e.g. 2500 = 25% penalty)."""
    end_time: str
    """Unix epoch seconds as a string."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ActiveDebuff:
        return cls(
            name=data["name"],
            debuff_bps=data["debuffBps"],
            end_time=data["endTime"],
        )


# ---------------------------------------------------------------------------
# Bakery models
# ---------------------------------------------------------------------------

class BakerySummary(BaseModel):
    """A bakery entry from the ``getTopBakeries`` paginated list.

    Includes live buff/debuff arrays and active cook counts that the
    ``getBakeryById`` detail endpoint does NOT include.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    creator: str
    """Wallet address of the bakery creator."""
    leader: str
    """Wallet address of the current leader (0x0... if vacant)."""
    top_cook: str | None
    """Wallet address of the top cookie producer, or null."""
    member_count: int
    active_cook_count: int | None
    """Number of members actively baking. Present in top-bakeries, null in detail."""
    season_id: int
    created_at: str
    """Unix epoch seconds as a string."""
    tx_count: str
    """Effective (boosted) cookie count as a stringified big-int."""
    raw_tx_count: str
    """Raw (unboosted) cookie count as a stringified big-int."""
    buffs: int
    """Number of active buff slots used."""
    debuffs: int
    """Number of active debuff slots used."""
    active_buffs: tuple[ActiveBuff, ...]
    active_debuffs: tuple[ActiveDebuff, ...]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BakerySummary:
        return cls(
            id=data["id"],
            name=data["name"],
            creator=data["creator"],
            leader=data["leader"],
            top_cook=data.get("topCook"),
            member_count=data["memberCount"],
            active_cook_count=data.get("activeCookCount"),
            season_id=data["seasonId"],
            created_at=data["createdAt"],
            tx_count=data["txCount"],
            raw_tx_count=data["rawTxCount"],
            buffs=data["buffs"],
            debuffs=data["debuffs"],
            active_buffs=tuple(
                ActiveBuff.from_api(b) for b in data.get("activeBuffs", [])
            ),
            active_debuffs=tuple(
                ActiveDebuff.from_api(d) for d in data.get("activeDebuffs", [])
            ),
        )


class BakeryDetail(BaseModel):
    """A single bakery from ``getBakeryById``.

    This endpoint returns fewer fields than the leaderboard summary --
    notably missing activeBuffs, activeDebuffs, and activeCookCount.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    creator: str
    leader: str
    top_cook: str | None
    member_count: int
    active_cook_count: int | None
    season_id: int
    created_at: str
    tx_count: str
    raw_tx_count: str
    buffs: int
    debuffs: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BakeryDetail:
        return cls(
            id=data["id"],
            name=data["name"],
            creator=data["creator"],
            leader=data["leader"],
            top_cook=data.get("topCook"),
            member_count=data["memberCount"],
            active_cook_count=data.get("activeCookCount"),
            season_id=data["seasonId"],
            created_at=data["createdAt"],
            tx_count=data["txCount"],
            raw_tx_count=data["rawTxCount"],
            buffs=data["buffs"],
            debuffs=data["debuffs"],
        )


# Union alias -- any code that accepts "a bakery" can use this.
Bakery = Union[BakerySummary, BakeryDetail]


# ---------------------------------------------------------------------------
# Bakery member
# ---------------------------------------------------------------------------

class BakeryMember(BaseModel):
    """A single member row from ``getBakeryMembers``.

    Returned inside a paginated wrapper with ``items`` and ``nextCursor``.
    """

    model_config = ConfigDict(frozen=True)

    season_id: int
    address: str
    """Wallet address of the member."""
    bakery_id: int
    tx_count: str
    """Raw bake count as a stringified big-int."""
    effective_tx_count: str
    """Effective (with referral bonus) bake count as a stringified big-int."""
    referrer_bonus: str
    """Bonus cookies earned from referrals as a stringified big-int."""
    referral_count: int
    referrer: str | None
    """Wallet address of whoever referred this member, or null."""
    registered_at: str
    """Unix epoch seconds as a string."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BakeryMember:
        return cls(
            season_id=data["seasonId"],
            address=data["address"],
            bakery_id=data["bakeryId"],
            tx_count=data["txCount"],
            effective_tx_count=data["effectiveTxCount"],
            referrer_bonus=data["referrerBonus"],
            referral_count=data["referralCount"],
            referrer=data.get("referrer"),
            registered_at=data["registeredAt"],
        )


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------

class ActivityEvent(BaseModel):
    """A single entry from ``getActivityFeed``.

    The ``type`` field discriminates between event kinds:
    - ``"simple"``  -- join/leave events (boost fields are null)
    - ``"rug"``     -- attack events (boost fields populated)
    """

    model_config = ConfigDict(frozen=True)

    type: str
    """Event type discriminator: 'simple' or 'rug'."""
    title: str
    description: str
    launcher: str
    """Wallet address that triggered the event."""
    timestamp: str
    """Unix epoch seconds as a string."""
    boost_type_name: str | None
    """Name of the boost/attack, or null for simple events."""
    boost_multiplier_bps: int | None
    """Multiplier/debuff in basis points, or null."""
    boost_duration: str | None
    """Duration in seconds as a string, or null."""
    is_shield: bool | None
    is_outgoing: bool
    """True if this bakery launched the action, false if received."""
    success: bool
    """Whether the action succeeded (attacks can fail)."""
    linked_bakery_id: int | None
    """ID of the other bakery involved, or null for joins."""
    linked_bakery_name: str | None
    """Name of the other bakery involved, or null for joins."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ActivityEvent:
        return cls(
            type=data["type"],
            title=data["title"],
            description=data["description"],
            launcher=data["launcher"],
            timestamp=data["timestamp"],
            boost_type_name=data.get("boostTypeName"),
            boost_multiplier_bps=data.get("boostMultiplierBps"),
            boost_duration=data.get("boostDuration"),
            is_shield=data.get("isShield"),
            is_outgoing=data["isOutgoing"],
            success=data["success"],
            linked_bakery_id=data.get("linkedBakeryId"),
            linked_bakery_name=data.get("linkedBakeryName"),
        )


# ---------------------------------------------------------------------------
# Player bakery
# ---------------------------------------------------------------------------

class PlayerBakery(BaseModel):
    """Player-to-bakery mapping from ``getPlayerBakery``.

    Requires ``address`` (hex string) and ``seasonId`` as input.
    """

    model_config = ConfigDict(frozen=True)

    season_id: int
    address: str
    bakery_id: int
    tx_count: str
    registered_at: str
    referrer: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PlayerBakery:
        return cls(
            season_id=data["seasonId"],
            address=data["address"],
            bakery_id=data["bakeryId"],
            tx_count=data["txCount"],
            registered_at=data["registeredAt"],
            referrer=data.get("referrer"),
        )


# ---------------------------------------------------------------------------
# Pagination cursors
# ---------------------------------------------------------------------------

class TopBakeriesCursor(BaseModel):
    """Cursor for paginating ``getTopBakeries`` results."""

    model_config = ConfigDict(frozen=True)

    tx_count: str
    id: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> TopBakeriesCursor:
        return cls(tx_count=data["txCount"], id=data["id"])


class BakeryMembersCursor(BaseModel):
    """Cursor for paginating ``getBakeryMembers`` results."""

    model_config = ConfigDict(frozen=True)

    tx_count: str
    address: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BakeryMembersCursor:
        return cls(tx_count=data["txCount"], address=data["address"])


class PaginatedBakeries(BaseModel):
    """Paginated response from ``getTopBakeries``."""

    model_config = ConfigDict(frozen=True)

    items: tuple[BakerySummary, ...]
    next_cursor: TopBakeriesCursor | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PaginatedBakeries:
        return cls(
            items=tuple(BakerySummary.from_api(b) for b in data["items"]),
            next_cursor=(
                TopBakeriesCursor.from_api(data["nextCursor"])
                if data.get("nextCursor")
                else None
            ),
        )


class PaginatedMembers(BaseModel):
    """Paginated response from ``getBakeryMembers``."""

    model_config = ConfigDict(frozen=True)

    items: tuple[BakeryMember, ...]
    next_cursor: BakeryMembersCursor | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PaginatedMembers:
        return cls(
            items=tuple(BakeryMember.from_api(m) for m in data["items"]),
            next_cursor=(
                BakeryMembersCursor.from_api(data["nextCursor"])
                if data.get("nextCursor")
                else None
            ),
        )


# ---------------------------------------------------------------------------
# agent.json models -- BoostCatalogItem, LiveState, Network, AgentConfig
# ---------------------------------------------------------------------------

class BoostCatalogItem(BaseModel):
    """A boost or attack definition from ``agent.json`` liveState.activeBoostCatalog.

    The ``type`` field is either ``'boost'`` or ``'attack'``.
    Costs are denominated in cookies (``cost`` is display-scale,
    ``actualCookieCost`` is the raw on-chain value).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    """Either 'boost' or 'attack'."""
    success_chance_bps: int
    """Probability of success in basis points (e.g. 6000 = 60%)."""
    cost: str
    """Display-scale cookie cost."""
    actual_cookie_cost: str
    """Raw cookie cost (cost * cookieScale)."""
    multiplier_bps: int
    """Effect strength in basis points."""
    duration_seconds: str
    """Effect duration in seconds as a string."""
    is_shield: bool
    active: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BoostCatalogItem:
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            success_chance_bps=data["successChanceBps"],
            cost=data["cost"],
            actual_cookie_cost=data["actualCookieCost"],
            multiplier_bps=data["multiplierBps"],
            duration_seconds=data["durationSeconds"],
            is_shield=data["isShield"],
            active=data["active"],
        )


class ReferralWeights(BaseModel):
    """Referral bonus configuration from ``liveState.referralWeights``."""

    model_config = ConfigDict(frozen=True)

    referred_weight_bps: int
    """Weight for referred players (e.g. 10500 = 1.05x)."""
    not_referred_weight_bps: int
    """Weight for non-referred players (e.g. 10000 = 1.0x)."""
    referral_bonus_bps: int
    """Bonus awarded to referrer in basis points."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ReferralWeights:
        return cls(
            referred_weight_bps=data["referredWeightBps"],
            not_referred_weight_bps=data["notReferredWeightBps"],
            referral_bonus_bps=data["referralBonusBps"],
        )


class GameplayCaps(BaseModel):
    """Gameplay limits from ``liveState.gameplayCaps``."""

    model_config = ConfigDict(frozen=True)

    cookie_scale: int
    """Multiplier between display cookies and raw on-chain values."""
    max_active_boosts: int
    max_active_debuffs: int
    leave_penalty_bps: int
    """Penalty for leaving a bakery in basis points (10000 = 100%)."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GameplayCaps:
        return cls(
            cookie_scale=data["cookieScale"],
            max_active_boosts=data["maxActiveBoosts"],
            max_active_debuffs=data["maxActiveDebuffs"],
            leave_penalty_bps=data["leavePenaltyBps"],
        )


class LiveState(BaseModel):
    """Real-time game state from ``agent.json`` liveState block."""

    model_config = ConfigDict(frozen=True)

    current_season_id: int
    is_season_active: bool
    buy_in_wei: str
    buy_in_eth: str
    vrf_fee_wei: str
    vrf_fee_eth: str
    minimum_required_wei_excluding_gas: str
    minimum_required_eth_excluding_gas: str
    referral_weights: ReferralWeights
    gameplay_caps: GameplayCaps
    active_boost_catalog: tuple[BoostCatalogItem, ...]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> LiveState:
        return cls(
            current_season_id=data["currentSeasonId"],
            is_season_active=data["isSeasonActive"],
            buy_in_wei=data["buyInWei"],
            buy_in_eth=data["buyInEth"],
            vrf_fee_wei=data["vrfFeeWei"],
            vrf_fee_eth=data["vrfFeeEth"],
            minimum_required_wei_excluding_gas=data["minimumRequiredWeiExcludingGas"],
            minimum_required_eth_excluding_gas=data["minimumRequiredEthExcludingGas"],
            referral_weights=ReferralWeights.from_api(data["referralWeights"]),
            gameplay_caps=GameplayCaps.from_api(data["gameplayCaps"]),
            active_boost_catalog=tuple(
                BoostCatalogItem.from_api(b)
                for b in data["activeBoostCatalog"]
            ),
        )


class Network(BaseModel):
    """Blockchain network configuration from ``agent.json``."""

    model_config = ConfigDict(frozen=True)

    name: str
    chain_id: int
    rpc_http: str
    explorer: str
    currency: str
    wallet_model: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Network:
        return cls(
            name=data["name"],
            chain_id=data["chainId"],
            rpc_http=data["rpcHttp"],
            explorer=data["explorer"],
            currency=data["currency"],
            wallet_model=data["walletModel"],
        )


class Contracts(BaseModel):
    """Smart contract addresses from ``agent.json``."""

    model_config = ConfigDict(frozen=True)

    season_manager: str
    prize_pool: str
    player_registry: str
    clan_registry: str
    boost_manager: str
    bakery: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Contracts:
        return cls(
            season_manager=data["seasonManager"],
            prize_pool=data["prizePool"],
            player_registry=data["playerRegistry"],
            clan_registry=data["clanRegistry"],
            boost_manager=data["boostManager"],
            bakery=data["bakery"],
        )


class AgentConfig(BaseModel):
    """Full parsed ``agent.json`` bootstrap file.

    This is the top-level model that aggregates all configuration
    needed to operate the dashboard: network info, contract addresses,
    live game state with boost catalog, and the list of available tRPC
    procedures.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    generated_at: str
    network: Network
    contracts: Contracts
    live_state: LiveState
    live_data_status: str
    """Either 'fresh' or 'stale'."""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AgentConfig:
        return cls(
            name=data["name"],
            version=data["version"],
            generated_at=data["generatedAt"],
            network=Network.from_api(data["network"]),
            contracts=Contracts.from_api(data["contracts"]),
            live_state=LiveState.from_api(data["liveState"]),
            live_data_status=data["liveDataStatus"],
        )


# ---------------------------------------------------------------------------
# tRPC response unwrapper
# ---------------------------------------------------------------------------

def unwrap_trpc(response: dict[str, Any]) -> Any:
    """Extract the inner payload from a tRPC GET response envelope.

    tRPC responses are shaped as::

        {"result": {"data": {"json": <payload>}}}

    This helper drills through the wrapper and returns ``<payload>``.
    Raises ``KeyError`` if the response is not in the expected shape
    (e.g. an error response).
    """
    return response["result"]["data"]["json"]
