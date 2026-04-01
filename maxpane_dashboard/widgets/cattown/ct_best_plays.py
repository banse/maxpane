"""Best plays two-column table for Cat Town dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}

# Layout widths (plain text characters)
_F_NAME_W = 15  # fish name column
_F_VAL_W = 9    # weight value column
_HALF_W = _F_NAME_W + _F_VAL_W + 2  # star(2) + name + val
_GAP = 1        # gap between left and right halves
_T_NAME_W = 13  # treasure name column (shorter to fit)
_T_VAL_W = 8    # treasure value column


def _fish_entry(f: dict, is_top: bool) -> str:
    name = f.get("name", "")[:_F_NAME_W]
    w_min = f.get("weight_min", 0.0)
    w_max = f.get("weight_max", 0.0)
    rarity = f.get("rarity", "Common")
    color = _RARITY_COLORS.get(rarity, "dim")
    star = "\u2605 " if is_top else "  "
    val = f"{w_min:.0f}-{w_max:.0f}kg"
    return f"[{color}]{star}{name:<{_F_NAME_W}} {val:>{_F_VAL_W}}[/]"


def _treasure_entry(t: dict, is_top: bool) -> str:
    name = t.get("name", "")[:_T_NAME_W]
    v_min = t.get("value_min", 0.0)
    v_max = t.get("value_max", 0.0)
    rarity = t.get("rarity", "Common")
    color = _RARITY_COLORS.get(rarity, "dim")
    star = "\u2605 " if is_top else "  "
    if v_min == v_max:
        val = f"{v_max:.0f}k"
    else:
        val = f"{v_min:.0f}-{v_max:.0f}k"
    return f"[{color}]{star}{name:<{_T_NAME_W}} {val:>{_T_VAL_W}}[/]"


class CTBestPlays(Vertical):
    """Side-by-side tables showing top fish and top treasures."""

    DEFAULT_CSS = """
    CTBestPlays > .ev-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTBestPlays > .ev-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="ev-title")
        yield Static("", classes="ev-body")
        # Column headers
        yield Static(
            f"  {'Top Fish Now':<{_HALF_W - 2}}{' ' * _GAP}  {'Top Treasures Now'}",
            classes="ev-body",
            id="ct-bp-header",
        )
        yield Static(
            f"  [dim]{'weight (kg)':<{_HALF_W - 2}}{' ' * _GAP}  {'value (KIBBLE)'}[/]",
            classes="ev-body",
            id="ct-bp-subheader",
        )
        # Blank spacer line
        yield Static("", classes="ev-body", id="ct-bp-spacer")
        # Data rows
        yield Static("[dim]  Loading...[/]", classes="ev-body", id="ct-bp-row-0")
        yield Static("", classes="ev-body", id="ct-bp-row-1")
        yield Static("", classes="ev-body", id="ct-bp-row-2")
        yield Static("", classes="ev-body", id="ct-bp-row-3")
        yield Static("", classes="ev-body", id="ct-bp-row-4")

    def update_data(
        self,
        available_fish: list[dict] | None = None,
        available_treasures: list[dict] | None = None,
    ) -> None:
        """Show top 5 fish by weight and top 5 treasures by value."""
        fish = sorted(
            available_fish or [],
            key=lambda f: f.get("weight_max", 0),
            reverse=True,
        )[:5]

        treasures = sorted(
            available_treasures or [],
            key=lambda t: t.get("value_max", 0),
            reverse=True,
        )[:5]

        empty_left = " " * _HALF_W

        for i in range(5):
            widget = self.query_one(f"#ct-bp-row-{i}", Static)
            left = _fish_entry(fish[i], i == 0) if i < len(fish) else empty_left
            right = _treasure_entry(treasures[i], i == 0) if i < len(treasures) else ""
            widget.update(f"{left}{' ' * _GAP}{right}")
