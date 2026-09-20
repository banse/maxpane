"""Hero metric boxes for the Onchain Monsters dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero shape states): a value the manager could not read arrives as ``None``
and renders an explicit ``unavailable`` marker, while a real ``0`` renders
as ``0``.  The old ``> 0`` guards collapsed both into "Loading..." forever
-- and, because the screen passes ``data.get(...)`` straight through, a
``None`` raised inside the comparison and the screen's ``try/except``
silently kept the previous contents on screen as if live.

The row itself, the boxes' seed text and the build-inside-the-guard write
are :class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 6).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBox, HeroRow


def _pct(value: float | None) -> str:
    return UNAVAILABLE if value is None else f"{value:.1f}%"


class OCMHeroBox(HeroBox):
    """A single hero metric box with label and value.

    Kept as its own class because ``minimal.tcss`` names ``OCMHeroBox`` for
    this dashboard's box geometry, as does the MEDI-38 harness CSS.
    """


class OCMHeroMetrics(HeroRow):
    """Row of three hero metric boxes: Supply, Staked, Reward / Monster."""

    BOX_CLASS = OCMHeroBox

    BOXES = (
        ("ocm-hero-supply", "SUPPLY"),
        ("ocm-hero-staked", "STAKED"),
        ("ocm-hero-reward", "REWARD / MONSTER"),
    )

    def update_data(
        self,
        total_supply: int | None = None,
        minted_pct: float | None = None,
        total_staked: int | None = None,
        staking_ratio: float | None = None,
        current_minting_cost_ocmd: float | None = None,
        **_kwargs,
    ) -> None:
        """Refresh all three hero boxes; a missing value says so."""
        self.render_box(
            "#ocm-hero-supply", "SUPPLY",
            lambda: self._supply_body(total_supply, minted_pct),
        )
        self.render_box(
            "#ocm-hero-staked", "STAKED",
            lambda: self._staked_body(total_staked, staking_ratio),
        )
        self.render_box(
            "#ocm-hero-reward", "REWARD / MONSTER",
            lambda: self._reward_body(current_minting_cost_ocmd),
        )

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _supply_body(total_supply, minted_pct) -> str:
        if total_supply is None:
            return UNAVAILABLE
        return (
            f"[bold white]{total_supply:,} / 10K[/]\n"
            f"[dim]{_pct(minted_pct)} minted[/]"
        )

    @staticmethod
    def _staked_body(total_staked, staking_ratio) -> str:
        if total_staked is None:
            return UNAVAILABLE
        return (
            f"[bold white]{total_staked:,}[/]\n"
            f"[dim]{_pct(staking_ratio)} of net supply[/]"
        )

    @staticmethod
    def _reward_body(current_minting_cost_ocmd) -> str:
        if current_minting_cost_ocmd is None:
            cost = UNAVAILABLE
        elif current_minting_cost_ocmd >= 1:
            cost = f"{current_minting_cost_ocmd:,.0f} $OCMD"
        else:
            cost = f"{current_minting_cost_ocmd} $OCMD"
        return f"[bold white]1 $OCMD/day[/]\n[dim]mint cost: {cost}[/]"
