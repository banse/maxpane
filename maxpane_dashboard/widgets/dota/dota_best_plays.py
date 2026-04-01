"""Best plays two-column table for Defense of the Agents dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


# Layout widths (plain text characters)
_L_NAME_W = 16   # hero name column (left)
_L_VAL_W = 6     # level value column
_HALF_W = _L_NAME_W + _L_VAL_W + 2  # star(2) + name + val
_GAP = 1         # gap between left and right halves
_R_NAME_W = 16   # hero name column (right)
_R_VAL_W = 6     # abilities value column


def _level_entry(name: str, level: int, is_top: bool) -> str:
    name = name[:_L_NAME_W]
    star = "\u2605 " if is_top else "  "
    val = f"Lv{level}"
    color = "yellow" if level >= 5 else "white" if level >= 3 else "dim"
    return f"[{color}]{star}{name:<{_L_NAME_W}} {val:>{_L_VAL_W}}[/]"


def _ability_entry(name: str, count: int, is_top: bool) -> str:
    name = name[:_R_NAME_W]
    star = "\u2605 " if is_top else "  "
    val = f"{count} abl"
    color = "cyan" if count >= 4 else "white" if count >= 2 else "dim"
    return f"[{color}]{star}{name:<{_R_NAME_W}} {val:>{_R_VAL_W}}[/]"


class DOTABestPlays(Vertical):
    """Side-by-side tables showing top heroes by level and by abilities."""

    DEFAULT_CSS = """
    DOTABestPlays > .dota-bp-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    DOTABestPlays > .dota-bp-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="dota-bp-title")
        yield Static("", classes="dota-bp-body")
        # Column headers
        yield Static(
            f"  {'Top by Level':<{_HALF_W - 2}}{' ' * _GAP}  {'Top by Abilities'}",
            classes="dota-bp-body",
            id="dota-bp-header",
        )
        yield Static(
            f"  [dim]{'hero level':<{_HALF_W - 2}}{' ' * _GAP}  {'ability count'}[/]",
            classes="dota-bp-body",
            id="dota-bp-subheader",
        )
        # Blank spacer
        yield Static("", classes="dota-bp-body", id="dota-bp-spacer")
        # Data rows
        yield Static("[dim]  Loading...[/]", classes="dota-bp-body", id="dota-bp-row-0")
        yield Static("", classes="dota-bp-body", id="dota-bp-row-1")
        yield Static("", classes="dota-bp-body", id="dota-bp-row-2")
        yield Static("", classes="dota-bp-body", id="dota-bp-row-3")
        yield Static("", classes="dota-bp-body", id="dota-bp-row-4")

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
            widget = self.query_one(f"#dota-bp-row-{i}", Static)
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
            widget.update(f"{left}{' ' * _GAP}{right}")
