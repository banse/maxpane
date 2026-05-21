"""Pydantic models for Ten Thousand Tokens (TTT) dashboard data.

These are the internal data shapes the TTT dashboard manipulates between the
data layer (WP3) and the widgets/screen (WP4/WP5). All models are frozen so
they can be safely shared across the snapshot pipeline.

Naming notes (see ``docs/tenthousandtokens_abi_recon.md``):

* The factory's launch event is ``Launched(uint256,address,address,string)`` —
  NOT ``BurnAndLaunch``. The activity feed uses ``event_type="burn"`` for
  rendering, which corresponds to this on-chain event.
* The fee event is ``FeeSplitter.Deposited(token, sender, total, launcherShare,
  tokenWorksShare, punkStrategyShare, holderShare)`` — 7 fields, with the
  30%-bucket already pre-split inline in ``holderShare``.
* The buyback event is ``TTT.Bought(caller, ethSpent, amountBought,
  callerReward)`` — NOT ``Buyback``.
* ``burnCount()`` lives on the FeeSplitter, not the factory.
* The FeeSplitter ``SCALE`` constant is 1e30 (confirmed on-chain), not 1e18.
* There is no ``reservoir()`` view on the per-token ERC20 — the buyback
  reservoir is the ERC20 contract's plain ETH balance (``eth_getBalance``).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_WEI = 10**18
_ETH_PER_LAUNCH = 10.0  # whitepaper-hardcoded initial pool value


class TTTFactoryState(BaseModel):
    """NFT factory + FeeSplitter state read in one multicall.

    ``burn_count`` and ``unburned`` (``activeShares``) are both derivable from
    each other (``unburned == max_supply - burn_count``) — we carry both for
    convenience so widgets don't have to recompute.
    """

    model_config = ConfigDict(frozen=True)

    max_supply: int                  # constant 10_000
    burn_count: int                  # FeeSplitter.burnCount()
    total_minted: int                # 10_000 once mint closed (already true in May 2026)
    unburned: int                    # max_supply - burn_count == FeeSplitter.activeShares()
    burned_pct: float                # burn_count / max_supply * 100
    acc_eth_per_share: int           # raw FeeSplitter cumulative, SCALE-fixed (uint256)
    total_eth_to_holders_wei: int    # cumulative 30%-bucket ETH all-time, wei
    current_block: int


class TTTLaunchedToken(BaseModel):
    """One ERC20 launched from a burned NFT.

    Market data fields (``price_usd``, ``price_change_h24``, ``volume_usd_h24``,
    ``market_cap_usd``) come from DexScreener and may be missing for very fresh
    launches — they default to ``None``.

    ``reservoir_wei`` is populated by the data layer (WP3) via
    ``eth_getBalance(address)`` — there is no ``reservoir()`` view on the
    contract.
    """

    model_config = ConfigDict(frozen=True)

    token_id: int                    # source NFT id
    address: str                     # ERC20 contract address, lowercased 0x...
    deployer: str                    # ETH address of burner (NFT holder)
    launch_block: int                # canonical deploymentBlock from TTTHook
    symbol: str | None               # discovered once per token, cached
    decimals: int                    # default 18
    # Market data from DexScreener (None if unavailable)
    price_usd: float | None = None
    price_change_h24: float | None = None
    volume_usd_h24: float | None = None
    market_cap_usd: float | None = None
    # On-chain
    reservoir_wei: int = 0           # ETH waiting to be buyback-drawn (eth_getBalance)
    # Fee history (aggregated locally from FeeSplitter.Deposited events)
    fees_eth_24h: float = 0.0
    fees_eth_lifetime: float = 0.0


class TTTNFTFloor(BaseModel):
    """NFT collection floor + 24h sales from Reservoir."""

    model_config = ConfigDict(frozen=True)

    floor_eth: float | None
    floor_usd: float | None
    sales_24h: int | None


class TTTActivityEvent(BaseModel):
    """Single event for the activity feed.

    ``event_type`` is one of:
    * ``"burn"``  — NFT burned & ERC20 launched (factory.Launched)
    * ``"swap"``  — Uniswap V4 swap on a launched token (TTTHook.Trade)
    * ``"fee"``   — FeeSplitter.Deposited (fee bucket filling)
    * ``"buyback"`` — TTT.Bought (anyone-callable buyback)
    * ``"sale"``  — NFT secondary-market sale (from Reservoir)

    ``eth_amount_wei`` semantics:
    * For ``"swap"`` it is SIGNED: positive = ETH spent by buyer (a buy),
      negative = ETH received by seller (a sell).
    * For all other event types it is unsigned (always >= 0).

    ``extra`` is a free-form, type-specific dict, e.g.
    ``{"tax_pct": 47.0}`` on swaps, ``{"bounty_wei": 12345}`` on buyback,
    ``{"price_eth": 0.0498}`` on sales.
    """

    model_config = ConfigDict(frozen=True)

    tx_hash: str
    block_number: int
    timestamp: int                   # unix seconds
    event_type: str                  # "burn", "swap", "fee", "buyback", "sale"
    token_symbol: str | None
    token_address: str | None        # for swap/fee/buyback
    actor_address: str | None        # deployer / swap-sender / buyback-caller / buyer
    eth_amount_wei: int              # signed for swaps (+ buy, - sell), unsigned otherwise
    token_id: int | None             # for burn / sale
    extra: dict | None = None        # tax pct, bounty amount, etc.


class TTTSignal(BaseModel):
    """One row of the Signals panel."""

    model_config = ConfigDict(frozen=True)

    label: str
    value_str: str
    indicator: str                   # colored dot or emoji (e.g. "●", "🔥", "►")
    color: str                       # "green" / "yellow" / "red" / "dim"


class TTTSnapshot(BaseModel):
    """Top-level container for one TTT poll cycle."""

    model_config = ConfigDict(frozen=True)

    fetched_at: float
    factory: TTTFactoryState | None
    floor: TTTNFTFloor | None
    eth_usd: float | None
    launched_tokens: list[TTTLaunchedToken]
    recent_events: list[TTTActivityEvent]
    # Signals
    fresh_launch_signal: TTTSignal | None  # None if no launch in last 10 min
    buybacks_ready_signal: TTTSignal
    decay_window_signal: TTTSignal
    concentration_signal: TTTSignal
    # 24h derived counters
    launches_24h: int
    eth_to_holders_24h: float
