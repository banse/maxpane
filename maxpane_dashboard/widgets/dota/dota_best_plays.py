"""Best plays two-column table for Defense of the Agents dashboard.

A two-column text board with no sibling outside its cattown twin, so it
keeps its body bespoke on
:class:`~maxpane_dashboard.widgets.panels.PanelBase` (Branch 7, WP-A)
rather than being forced into one of the four shaped bases. What the base
takes over is the title, its blank row and the guarded write.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import LOADING_ROW, PanelBase

# Layout widths (plain text characters)
_L_NAME_W = 16   # hero name column (left)
_L_VAL_W = 6     # level value column
_HALF_W = _L_NAME_W + _L_VAL_W + 2  # star(2) + name + val
_GAP = 1         # gap between left and right halves
_R_NAME_W = 16   # hero name column (right)
_R_VAL_W = 6     # abilities value column


def _level_entry(name: str, level: int, is_top: bool) -> str:
    name = safe_markup(name[:_L_NAME_W])
    star = "★ " if is_top else "  "
    val = f"Lv{level}"
    color = "yellow" if level >= 5 else "white" if level >= 3 else "dim"
    return f"[{color}]{star}{name:<{_L_NAME_W}} {val:>{_L_VAL_W}}[/]"


def _ability_entry(name: str, count: int, is_top: bool) -> str:
    name = safe_markup(name[:_R_NAME_W])
    star = "★ " if is_top else "  "
    val = f"{count} abl"
    color = "cyan" if count >= 4 else "white" if count >= 2 else "dim"
    return f"[{color}]{star}{name:<{_R_NAME_W}} {val:>{_R_VAL_W}}[/]"


class DOTABestPlays(PanelBase):
    """Side-by-side tables showing top heroes by level and by abilities."""

    TITLE = "BEST PLAYS"

    def compose_body(self) -> ComposeResult:
        # Column headers
        yield Static(
            f"  {'Top by Level':<{_HALF_W - 2}}{' ' * _GAP}  {'Top by Abilities'}",
            classes="panel-line",
            id="dota-bp-header",
        )
        yield Static(
            f"  [dim]{'hero level':<{_HALF_W - 2}}{' ' * _GAP}  {'ability count'}[/]",
            classes="panel-line",
            id="dota-bp-subheader",
        )
        # Blank line between the headers and the rows. Not the title's row,
        # which is PanelBase's margin.
        yield Static("", classes="panel-line", id="dota-bp-spacer")
        # Data rows
        for index in range(5):
            yield Static(
                LOADING_ROW if index == 0 else "",
                classes="panel-line",
                id=f"dota-bp-row-{index}",
            )

    def update_data(
        self,
        heroes_by_level: list[tuple[str, int]] | None = None,
        heroes_by_abilities: list[tuple[str, int]] | None = None,
    ) -> None:
        """Show top 5 heroes by level and top 5 heroes by ability count."""
        by_level = (heroes_by_level or [])[:5]
        by_abilities = (heroes_by_abilities or [])[:5]

        empty_left = " " * _HALF_W

        for i in range(5):
            left = (
                _level_entry(by_level[i][0], by_level[i][1], i == 0)
                if i < len(by_level)
                else empty_left
            )
            right = (
                _ability_entry(by_abilities[i][0], by_abilities[i][1], i == 0)
                if i < len(by_abilities)
                else ""
            )
            self.write(f"#dota-bp-row-{i}", f"{left}{' ' * _GAP}{right}")
