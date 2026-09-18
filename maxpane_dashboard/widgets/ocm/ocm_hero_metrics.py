"""Hero metric boxes for the Onchain Monsters dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero template states): a value the manager could not read arrives as
``None`` and renders an explicit ``unavailable`` marker, while a real ``0``
renders as ``0``.  The old ``> 0`` guards collapsed both into "Loading..."
forever -- and, because the screen passes ``data.get(...)`` straight
through, a ``None`` raised inside the comparison and the screen's
``try/except`` silently kept the previous contents on screen as if live.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

#: Shown in place of a value the backend could not supply this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


def _pct(value: float | None) -> str:
    return _UNAVAILABLE if value is None else f"{value:.1f}%"


class OCMHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class OCMHeroMetrics(Horizontal):
    """Row of three hero metric boxes: Supply, Holders, Reward / Monster."""

    DEFAULT_CSS = """
    OCMHeroMetrics > OCMHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield OCMHeroBox(
            "[dim]SUPPLY[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-supply",
        )
        yield OCMHeroBox(
            "[dim]STAKED[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-staked",
        )
        yield OCMHeroBox(
            "[dim]REWARD / MONSTER[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-reward",
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
        self._render_box("#ocm-hero-supply", "SUPPLY",
                         self._supply_body, total_supply, minted_pct)
        self._render_box("#ocm-hero-staked", "STAKED",
                         self._staked_body, total_staked, staking_ratio)
        self._render_box("#ocm-hero-reward", "REWARD / MONSTER",
                         self._reward_body, current_minting_cost_ocmd)

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _supply_body(total_supply, minted_pct) -> str:
        if total_supply is None:
            return _UNAVAILABLE
        return (
            f"[bold white]{total_supply:,} / 10K[/]\n"
            f"[dim]{_pct(minted_pct)} minted[/]"
        )

    @staticmethod
    def _staked_body(total_staked, staking_ratio) -> str:
        if total_staked is None:
            return _UNAVAILABLE
        return (
            f"[bold white]{total_staked:,}[/]\n"
            f"[dim]{_pct(staking_ratio)} of net supply[/]"
        )

    @staticmethod
    def _reward_body(current_minting_cost_ocmd) -> str:
        if current_minting_cost_ocmd is None:
            cost = _UNAVAILABLE
        elif current_minting_cost_ocmd >= 1:
            cost = f"{current_minting_cost_ocmd:,.0f} $OCMD"
        else:
            cost = f"{current_minting_cost_ocmd} $OCMD"
        return f"[bold white]1 $OCMD/day[/]\n[dim]mint cost: {cost}[/]"

    def _render_box(self, selector: str, label: str, build, *args) -> None:
        """Write one box, degrading to an explicit unavailable state.

        The body is built inside the guard: a malformed value (a string
        where a number was expected) must land on ``unavailable`` here, not
        raise into the screen's ``except`` and leave the previous poll's
        number on screen as if it were live.
        """
        try:
            box = self.query_one(selector, OCMHeroBox)
        except Exception:
            return
        try:
            box.update(f"[dim]{label}[/]\n\n{build(*args)}")
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{_UNAVAILABLE}")
            except Exception:
                pass
