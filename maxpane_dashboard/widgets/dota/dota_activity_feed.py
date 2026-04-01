"""Activity feed (hero roster) for Defense of the Agents dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


_FACTION_COLORS = {
    "human": "cyan",
    "orc": "red",
}


_NAME_WIDTH = 14


def _truncate_name(name: str, width: int = _NAME_WIDTH) -> str:
    """Strip non-ASCII, truncate, and pad to fixed width."""
    clean = "".join(ch for ch in name if ord(ch) < 128).strip()
    if len(clean) > width:
        return clean[: width - 1] + "."
    return clean.ljust(width)


def _hero_to_markup(hero: dict) -> str:
    """Convert a hero dict into a Rich-markup formatted line."""
    name = _truncate_name(hero.get("name", "Unknown"))
    faction = hero.get("faction", "")
    hero_class = hero.get("hero_class", "")
    lane = hero.get("lane", "")
    hp = hero.get("hp", 0)
    max_hp = hero.get("max_hp", 0)
    alive = hero.get("alive", False)
    level = hero.get("level", 1)

    color = _FACTION_COLORS.get(faction, "dim")
    status = "[green]ALIVE[/]" if alive else "[red]DEAD[/]"
    hp_str = f"{hp}/{max_hp}" if max_hp > 0 else "--"

    return (
        f"  [{color}]{faction[:1].upper()}[/] "
        f"[bold]{name}[/] "
        f"[dim]{hero_class:<6}[/] "
        f"[dim]{lane:<4}[/] "
        f"Lv{level:<3} "
        f"HP {hp_str:<10} "
        f"{status}"
    )


class DOTAActivityFeed(Vertical):
    """Hero roster display for Defense of the Agents."""

    DEFAULT_CSS = """
    DOTAActivityFeed > .dota-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    DOTAActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("HERO ROSTER", classes="dota-feed-title")
        yield RichLog(id="dota-activity-log", wrap=True, highlight=True, markup=True)

    def update_data(
        self,
        heroes: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with the current hero roster."""
        log = self.query_one("#dota-activity-log", RichLog)
        log.clear()

        if not heroes:
            log.write("[dim]  No heroes yet[/]")
            return

        # Sort: alive first, then by level descending
        sorted_heroes = sorted(
            heroes,
            key=lambda h: (not h.get("alive", False), -h.get("level", 0)),
        )

        for hero in sorted_heroes:
            log.write(_hero_to_markup(hero))
