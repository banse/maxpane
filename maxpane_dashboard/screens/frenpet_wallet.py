"""FrenPetWalletScreen -- FrenPet wallet-level dashboard as a Textual Screen.

Six of this screen's panels *compute* between the fetch and the dispatch, so
their ``PANELS`` rows are module-level adapters rather than
:func:`~maxpane_dashboard.screens.dashboard_screen.keys` rows. Each one is the
arithmetic that used to sit inside the screen's own ``try`` block, moved out
whole: same helpers, same order, same values.

**The clock is not injected here.** :func:`_wallet_trends` samples
``time.time()`` for the single-point ETH and win-rate histories, exactly as the
hand-written block did. That contradicts CLAUDE.md's "Inject the clock" and is a
pre-existing hazard this migration carried across rather than fixed -- filed as
follow-up 19 in ``docs/handover_followups_2026_09.md``.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.frenpet_wallet_signals import (
    classify_fp_rate,
    classify_pool_share,
    classify_win_rate,
    compute_win_rate,
    find_most_efficient,
    find_top_earner,
    generate_wallet_recommendation,
)
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.frenpet._chain import EXPLORER
from maxpane_dashboard.widgets.frenpet.wallet import (
    FPWalletActivity,
    FPWalletBestPlays,
    FPWalletHero,
    FPWalletPets,
    FPWalletSignals,
    FPWalletTrends,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

#: Display budget for the wallet address in the title bar, excluding the
#: icon (``ICON_COLS``). No layout pin covers this hidden screen.
_WALLET_COLS = 11


def _wallet_hero(data: dict) -> dict:
    """ETH owed, pool share and APR -- or the all-zero box with no rewards read.

    ``userShares()`` and ``totalFpInPool()`` are raw uint256 values with 18
    decimals, exactly like the FP token itself. They are scaled to display FP
    here (as ``total_fp_per_second`` is in :func:`_wallet_signals`) -- passing
    the raw integers made the hero read "of 37325669265659.0B FP pool" instead
    of "of 37.3K FP pool".
    """
    managed_pets = data.get("managed_pets", [])
    wallet_rewards = data.get("wallet_rewards")
    if not wallet_rewards:
        return {
            "total_eth_wei": 0,
            "eth_price_usd": 0.0,
            "pool_share_pct": 0.0,
            "total_fp_in_pool": 0,
            "apr": 0.0,
            "user_shares": 0,
            "pet_count": len(managed_pets),
        }
    return {
        "total_eth_wei": wallet_rewards.get("total_eth_wei", 0),
        "eth_price_usd": wallet_rewards.get("eth_price_usd", 0.0),
        "pool_share_pct": wallet_rewards.get("pool_share_pct", 0.0),
        "total_fp_in_pool": wallet_rewards.get("total_fp_in_pool", 0) / 1e18,
        "apr": wallet_rewards.get("apr", 0.0),
        "user_shares": wallet_rewards.get("user_shares", 0) / 1e18,
        "pet_count": len(managed_pets),
    }


def _wallet_pets(data: dict) -> dict:
    """One row per pet, with its pending plus owed ETH from the rewards map."""
    managed_pets = data.get("managed_pets", [])
    wallet_rewards = data.get("wallet_rewards")
    pet_rewards_map = wallet_rewards.get("pet_rewards", {}) if wallet_rewards else {}
    pets_for_table = []
    for pet in managed_pets:
        pr = pet_rewards_map.get(pet.id, {})
        pets_for_table.append({
            "id": pet.id,
            "name": pet.name,
            "score": pet.score,
            "wins": pet.win_qty,
            "losses": pet.loss_qty,
            "atk": pet.attack_points,
            "def": pet.defense_points,
            "pending_eth_wei": pr.get("pending_eth_wei", 0)
            + pr.get("eth_owed_wei", 0),
        })
    return {"pets": pets_for_table}


def _wallet_trends(data: dict) -> dict:
    """The three sparklines, each derived rather than served.

    ``time.time()`` is sampled here for the one-point ETH and win-rate series;
    see this module's docstring (follow-up 19).
    """
    managed_pets = data.get("managed_pets", [])
    wallet_rewards = data.get("wallet_rewards")
    pet_score_histories = data.get("pet_score_histories", {})

    # Build aggregated score history from per-pet histories
    score_history: list[tuple[float, float]] = []
    if pet_score_histories:
        # Sum scores across all pets at each timestamp
        # Use the first pet's timestamps as reference
        all_histories = list(pet_score_histories.values())
        if all_histories:
            ref = all_histories[0]
            for i, (ts, _val) in enumerate(ref):
                total = 0.0
                for hist in all_histories:
                    if i < len(hist):
                        total += hist[i][1]
                score_history.append((ts, total))

    # ETH rewards history -- we only have the current value,
    # so build a single-point series or use None
    eth_total_wei = wallet_rewards.get("total_eth_wei", 0) if wallet_rewards else 0
    eth_history: list[tuple[float, float]] = [
        (time.time(), eth_total_wei / 1e18)
    ] if eth_total_wei > 0 else []

    # Win rate history -- single point from current data
    total_wins = sum(p.win_qty for p in managed_pets)
    total_losses = sum(p.loss_qty for p in managed_pets)
    wr = compute_win_rate(total_wins, total_losses)
    win_rate_history: list[tuple[float, float]] = [
        (time.time(), wr)
    ] if (total_wins + total_losses) > 0 else []

    return {
        "score_history": score_history or None,
        "eth_history": eth_history or None,
        "win_rate_history": win_rate_history or None,
    }


def _wallet_signals(data: dict) -> dict:
    """FP emission rate, win rate and pool share, each classified."""
    managed_pets = data.get("managed_pets", [])
    wallet_rewards = data.get("wallet_rewards")

    total_fp_per_second_raw = (
        wallet_rewards.get("total_fp_per_second", 0) if wallet_rewards else 0
    )
    # Convert from wei (18 decimals) to human-readable FP
    total_fp_per_second = total_fp_per_second_raw / 1e18
    fp_status, fp_color = classify_fp_rate(total_fp_per_second_raw)

    total_wins = sum(p.win_qty for p in managed_pets)
    total_losses = sum(p.loss_qty for p in managed_pets)
    win_rate = compute_win_rate(total_wins, total_losses)
    win_status, win_color = classify_win_rate(win_rate)

    pool_share_pct = (
        wallet_rewards.get("pool_share_pct", 0.0) if wallet_rewards else 0.0
    )
    pool_status, pool_color = classify_pool_share(pool_share_pct)

    total_eth_wei = wallet_rewards.get("total_eth_wei", 0) if wallet_rewards else 0

    return {
        "fp_per_second": total_fp_per_second,
        "fp_status": fp_status,
        "fp_color": fp_color,
        "win_rate": win_rate,
        "win_status": win_status,
        "win_color": win_color,
        "pool_share": pool_share_pct,
        "pool_status": pool_status,
        "pool_color": pool_color,
        "recommendation": generate_wallet_recommendation(
            pool_share_pct, win_rate, total_fp_per_second_raw, total_eth_wei,
        ),
    }


def _wallet_activity(data: dict) -> dict:
    """The wallet's own pets keyed by id, over the global name map."""
    managed_pets = data.get("managed_pets", [])
    # Merge with global pet_names for opponent resolution
    full_names = dict(data.get("pet_names", {}))
    full_names.update({p.id: p.name for p in managed_pets})
    return {
        "recent_attacks": data.get("recent_attacks", []),
        "pet_ids": {p.id for p in managed_pets},
        "pet_names": full_names,
    }


def _wallet_best_plays(data: dict) -> dict:
    """Top earner and most efficient, off name/score/wins/losses only."""
    pets_for_analytics = [
        {
            "name": p.name,
            "score": p.score,
            "wins": p.win_qty,
            "losses": p.loss_qty,
        }
        for p in data.get("managed_pets", [])
    ]
    return {
        "top_earner": find_top_earner(pets_for_analytics),
        "most_efficient": find_most_efficient(pets_for_analytics),
    }


class FrenPetWalletScreen(DashboardScreen):
    """FrenPet wallet-level dashboard: ETH rewards, pool share, APR."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "frenpet wallet"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "fpw-refresh"

    #: Transcribed from the six hand-written dispatch blocks, arithmetic for
    #: arithmetic; the status bar is updated by the base. The pets table was
    #: the one positional call (``update_data(pets_for_table)``); its parameter
    #: is named ``pets``, so the keyword row is the same call.
    PANELS = (
        (FPWalletHero, _wallet_hero),
        (FPWalletPets, _wallet_pets),
        (FPWalletTrends, _wallet_trends),
        (FPWalletSignals, _wallet_signals),
        (FPWalletActivity, _wallet_activity),
        (FPWalletBestPlays, _wallet_best_plays),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "FrenPet · Wallet · Loading...",
            id="fpw-title",
        )

        yield FPWalletHero()

        with Horizontal(id="fpw-middle-row"):
            yield FPWalletPets()
            with Vertical(id="fpw-right-col"):
                yield FPWalletTrends()
                yield FPWalletSignals()

        yield Static("─" * 300, id="fpw-separator")

        with Horizontal(id="fpw-bottom-row"):
            yield FPWalletActivity()
            yield FPWalletBestPlays()

        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        # A Text, never a markup string: Static.update() defers markup
        # parsing into the message pump, and the icon's click action lives
        # in a Style that only survives outside markup parsing.
        title = self.query_one("#fpw-title", Static)
        wallet_addr = getattr(self._data_manager, "_wallet_address", "")
        pet_count = len(data.get("managed_pets", []))
        line = Text("FrenPet · Wallet · ")
        if wallet_addr:
            line.append_text(address_text(wallet_addr, width=_WALLET_COLS, explorer=EXPLORER))
        else:
            line.append("?")
        line.append(f" · {pet_count} pets")
        title.update(line)
