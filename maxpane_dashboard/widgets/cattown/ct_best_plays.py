"""Best plays two-column table for Cat Town dashboard.

A two-column text board with no sibling outside its dota twin, so it keeps
its body bespoke on :class:`~maxpane_dashboard.widgets.panels.PanelBase`
(Branch 7, WP-A) rather than being forced into one of the four shaped
bases. What the base takes over is the title, its blank row and the guarded
write; ``_RARITY_COLORS`` moved to the package's ``_fmt.py``, where the
leaderboard reads the same mapping.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets.cattown._fmt import _RARITY_COLORS
from maxpane_dashboard.widgets.panels import LOADING_ROW, PanelBase

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
    star = "★ " if is_top else "  "
    val = f"{w_min:.0f}-{w_max:.0f}kg"
    return f"[{color}]{star}{name:<{_F_NAME_W}} {val:>{_F_VAL_W}}[/]"


def _treasure_entry(t: dict, is_top: bool) -> str:
    name = t.get("name", "")[:_T_NAME_W]
    v_min = t.get("value_min", 0.0)
    v_max = t.get("value_max", 0.0)
    rarity = t.get("rarity", "Common")
    color = _RARITY_COLORS.get(rarity, "dim")
    star = "★ " if is_top else "  "
    if v_min == v_max:
        val = f"{v_max:.0f}k"
    else:
        val = f"{v_min:.0f}-{v_max:.0f}k"
    return f"[{color}]{star}{name:<{_T_NAME_W}} {val:>{_T_VAL_W}}[/]"


class CTBestPlays(PanelBase):
    """Side-by-side tables showing top fish and top treasures."""

    TITLE = "BEST PLAYS"

    def compose_body(self) -> ComposeResult:
        # Column headers
        yield Static(
            f"  {'Top Fish Now':<{_HALF_W - 2}}{' ' * _GAP}  {'Top Treasures Now'}",
            classes="panel-line",
            id="ct-bp-header",
        )
        yield Static(
            f"  [dim]{'weight (kg)':<{_HALF_W - 2}}{' ' * _GAP}  {'value (KIBBLE)'}[/]",
            classes="panel-line",
            id="ct-bp-subheader",
        )
        # Blank line between the headers and the rows. Not the title's row,
        # which is PanelBase's margin.
        yield Static("", classes="panel-line", id="ct-bp-spacer")
        # Data rows
        for index in range(5):
            yield Static(
                LOADING_ROW if index == 0 else "",
                classes="panel-line",
                id=f"ct-bp-row-{index}",
            )

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
            left = _fish_entry(fish[i], i == 0) if i < len(fish) else empty_left
            right = _treasure_entry(treasures[i], i == 0) if i < len(treasures) else ""
            self.write(f"#ct-bp-row-{i}", f"{left}{' ' * _GAP}{right}")
