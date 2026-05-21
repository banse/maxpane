"""Signal analytics for the Ten Thousand Tokens (TTT) dashboard.

Pure functions that take raw state (TTTFactoryState, TTTLaunchedToken,
TTTActivityEvent) and return `TTTSignal` instances (or scalar derived values).

All `TTTSignal` instances expose the same four keys when serialized via
`model_dump()`: `label`, `value_str`, `indicator`, `color`. `color` is always
one of `"green"`, `"yellow"`, `"red"`, `"dim"`.

Constants in this module are sourced from the TTT whitepaper and validated
against the on-chain reconnaissance in `docs/tenthousandtokens_abi_recon.md`.
Notably:

  * `HOLDER_FEE_SHARE = 0.30` is the protocol-level slice routed to the holder
    pool. The `Deposited` event already emits the four pre-split slices
    inline, so this constant is documentation/projection input only --
    holder-amount math reads `holderShare` directly from the event when
    consuming live deposits.
  * The FeeSplitter's `accETHPerShare` is SCALE-fixed at `1e30`, NOT `1e18`
    (see recon doc). Conversion to ETH lives in the data layer; this module
    operates on already-converted scalars.

Pattern: `maxpane_dashboard/analytics/ocm_signals.py`.
"""

from __future__ import annotations

from maxpane_dashboard.data.ttt_models import (
    TTTActivityEvent,
    TTTFactoryState,
    TTTLaunchedToken,
    TTTSignal,
)

# --- Whitepaper / protocol constants --------------------------------------

DECAY_BLOCKS = 98              # 99% -> 1% over 98 blocks
BUY_TAX_START_PCT = 99
BUY_TAX_FLOOR_PCT = 1
SELL_TAX_PCT = 1
HOLDER_FEE_SHARE = 0.30
DEPLOYER_FEE_SHARE = 0.50
PROTOCOL_FEE_SHARE = 0.10      # TokenWorks
PUNKSTRATEGY_FEE_SHARE = 0.10
BUYBACK_BOUNTY_FRAC = 0.005    # 0.5%
BUYBACK_MAX_DRAW_WEI = 10**18  # 1 ETH per block
FRESH_LAUNCH_WINDOW_SEC = 600  # 10 minutes
BUYBACK_READY_THRESHOLD_WEI = 10**17  # 0.1 ETH
MAX_NFTS = 10_000

_WEI = 10**18


# --- Scalar helpers --------------------------------------------------------


def decay_tax_pct(blocks_since_launch: int) -> int:
    """Current buy-tax percent for a token N blocks past launch.

    Block 0 -> 99, Block 50 -> 49, Block 98 and beyond -> 1. Returns 99 for
    negative input (shouldn't happen, but guards against bad block math).
    """
    if blocks_since_launch < 0:
        return BUY_TAX_START_PCT
    return max(BUY_TAX_START_PCT - blocks_since_launch, BUY_TAX_FLOOR_PCT)


def per_nft_share(unburned: int) -> float:
    """Fraction of each holder-pool deposit accruing to ONE un-burned NFT.

    Returns 0.0 when `unburned <= 0` (handles divide-by-zero safely).
    """
    if unburned <= 0:
        return 0.0
    return HOLDER_FEE_SHARE / unburned


def concentration_multiplier(unburned: int) -> float:
    """How much more an NFT claims now vs. a day-1 holder (10,000 unburned).

    `per_nft_share(unburned) / per_nft_share(MAX_NFTS)`. Returns 0.0 if either
    side is zero (i.e. nobody to claim).
    """
    baseline = per_nft_share(MAX_NFTS)
    if baseline <= 0:
        return 0.0
    return per_nft_share(unburned) / baseline


# --- Aggregations over launched-token lists -------------------------------


def count_buybacks_ready(tokens: list[TTTLaunchedToken]) -> tuple[int, int]:
    """Count tokens whose buyback reservoir is worth surfacing + total bounty.

    Returns `(count, total_bounty_wei)`. A token "counts" if
    `reservoir_wei >= BUYBACK_READY_THRESHOLD_WEI` (0.1 ETH). Bounty for each
    qualifying token is `0.5% * min(reservoir, 1 ETH)` -- mirrors the on-chain
    cap of `BUYBACK_MAX_DRAW_WEI` per block.
    """
    count = 0
    total_bounty_wei = 0
    for t in tokens:
        if t.reservoir_wei >= BUYBACK_READY_THRESHOLD_WEI:
            draw = min(t.reservoir_wei, BUYBACK_MAX_DRAW_WEI)
            total_bounty_wei += int(draw * BUYBACK_BOUNTY_FRAC)
            count += 1
    return count, total_bounty_wei


def count_decay_window(tokens: list[TTTLaunchedToken], current_block: int) -> int:
    """Number of tokens still inside the 98-block buy-tax decay window."""
    return sum(
        1 for t in tokens if (current_block - t.launch_block) < DECAY_BLOCKS
    )


def aggregate_recent_launches(
    events: list[TTTActivityEvent], window_sec: int = 86400
) -> int:
    """Count `event_type == "burn"` activity events within the trailing window.

    `window_sec` is anchored to the most-recent event timestamp in the list,
    so this works whether `events` is fresh-from-chain or replayed from cache.
    Returns 0 if no burn events are present.
    """
    burns = [e for e in events if e.event_type == "burn"]
    if not burns:
        return 0
    anchor_ts = max(e.timestamp for e in burns)
    cutoff = anchor_ts - window_sec
    return sum(1 for e in burns if e.timestamp >= cutoff)


# --- Signal builders -------------------------------------------------------


def fresh_launch_alert(
    recent_events: list[TTTActivityEvent],
    current_block: int,
    now_ts: float,
) -> TTTSignal | None:
    """Highlight the most recent launch if it happened in the last 10 minutes.

    Scans `recent_events` for `event_type == "burn"` within
    `FRESH_LAUNCH_WINDOW_SEC` of `now_ts` and returns a `TTTSignal` describing
    it. Returns `None` if no burn event qualifies.
    """
    cutoff = now_ts - FRESH_LAUNCH_WINDOW_SEC
    candidates = [
        e
        for e in recent_events
        if e.event_type == "burn" and e.timestamp >= cutoff
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda e: e.timestamp)
    age_sec = max(0.0, now_ts - latest.timestamp)
    mins = int(age_sec // 60)
    tax_pct = decay_tax_pct(current_block - latest.block_number)
    symbol = latest.token_symbol or "???"
    return TTTSignal(
        label="Fresh launch",
        value_str=f"NEW: {symbol} launched {mins}m ago -- {tax_pct}% buy tax",
        indicator="\U0001f525",  # fire emoji
        color="yellow",
    )


def buybacks_ready_signal(tokens: list[TTTLaunchedToken]) -> TTTSignal:
    """One-line summary of tokens with buyback-ready reservoirs."""
    count, bounty_wei = count_buybacks_ready(tokens)
    bounty_eth = bounty_wei / _WEI
    color = "green" if count > 0 else "dim"
    return TTTSignal(
        label="Buybacks ready",
        value_str=f"{count} buybacks ready (Σ {bounty_eth:.4f} Ξ bounty)",
        indicator="►",
        color=color,
    )


def decay_window_signal(
    tokens: list[TTTLaunchedToken], current_block: int
) -> TTTSignal:
    """One-line summary of how many tokens are still inside their tax decay."""
    count = count_decay_window(tokens, current_block)
    color = "yellow" if count > 0 else "dim"
    return TTTSignal(
        label="Decay window",
        value_str=f"{count} tokens in decay window (>1% buy tax)",
        indicator="►",
        color=color,
    )


def concentration_signal(
    state: TTTFactoryState, eth_to_holders_24h: float
) -> TTTSignal:
    """Render the 'each NFT claims 1/N of the pool' status row."""
    unburned = state.unburned
    if unburned > 0:
        per_nft_24h = eth_to_holders_24h / unburned
    else:
        per_nft_24h = 0.0
    return TTTSignal(
        label="Concentration",
        value_str=(
            f"Each NFT claims 1/{unburned:,} of pool "
            f"-- ≈{per_nft_24h:.5f} Ξ/day at current rate"
        ),
        indicator="►",
        color="green",
    )


# --- Tabular outputs -------------------------------------------------------


def claim_math_scenarios(
    state: TTTFactoryState, eth_to_holders_24h: float
) -> list[dict]:
    """Rows for the gamma-view scenario table.

    Each row:
        {
            "scenario": str,
            "unburned": int,
            "share_pct": float,        # 30 / unburned, expressed as a percent
            "projected_24h_eth": float,
            "multiplier_vs_today": float,
        }

    Projection assumes today's ETH-to-holders flow holds constant. The
    `multiplier_vs_today` is computed relative to the "Today" row's per-NFT
    projection.
    """
    today_unburned = max(state.unburned, 0)
    scenarios: list[tuple[str, int]] = [
        ("Today", today_unburned),
        ("25% burned", 7500),
        ("50% burned", 5000),
        ("75% burned", 2500),
        ("90% burned", 1000),
        ("Sole survivor", 1),
    ]

    today_per_nft = (
        eth_to_holders_24h / today_unburned if today_unburned > 0 else 0.0
    )

    rows: list[dict] = []
    for label, unburned in scenarios:
        if unburned > 0:
            share_pct = (HOLDER_FEE_SHARE / unburned) * 100.0
            projected = eth_to_holders_24h / unburned
        else:
            share_pct = 0.0
            projected = 0.0
        if today_per_nft > 0 and unburned > 0:
            multiplier = projected / today_per_nft
        else:
            multiplier = 0.0
        rows.append(
            {
                "scenario": label,
                "unburned": unburned,
                "share_pct": share_pct,
                "projected_24h_eth": projected,
                "multiplier_vs_today": multiplier,
            }
        )
    return rows


def top_fee_engines(
    tokens: list[TTTLaunchedToken], top_n: int = 10
) -> list[TTTLaunchedToken]:
    """Top N launched tokens ranked by 24h fees, descending."""
    return sorted(tokens, key=lambda t: t.fees_eth_24h, reverse=True)[:top_n]
