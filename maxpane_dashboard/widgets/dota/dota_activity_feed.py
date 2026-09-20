"""Activity feed (hero roster) for Defense of the Agents dashboard.

The "activity feed" slot carries the **hero roster** on this dashboard: the
same ``RichLog`` shape, but the list is a snapshot of who is alive rather
than a stream of events, so it is rewritten whole on every poll.
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed` calls that
"always new" -- ``dedupe_key`` returns ``None``, nothing is deduped, the
flicker guard never fires (Branch 7, WP-A).

That inherits one behaviour change the base documents: an **empty poll no
longer wipes a drawn roster**. The manager serves ``None`` for a failed
read and a list for a real one, so what an empty list used to do here --
clear the roster and paint ``No heroes yet`` over it -- was a false
degradation whenever the read itself failed. The last roster now stays
under the status bar's ``as of`` marker, which is what every other feed in
the app does.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import RichLogFeed


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
    name = safe_markup(_truncate_name(hero.get("name", "Unknown")))
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


def _hero_to_text(hero: dict) -> Text:
    """The ``format_row`` hook: a parsed ``Text``, never a markup string.

    ``RichLogFeed`` requires it. The parse happens here, inside the feed's
    own per-row guard, so a hero whose name is malformed markup is one
    skipped line instead of a ``MarkupError`` raised deep in Textual's
    message pump where no ``try`` can reach it.
    """
    return Text.from_markup(_hero_to_markup(hero))


class DOTAActivityFeed(RichLogFeed):
    """Hero roster display for Defense of the Agents."""

    TITLE = "HERO ROSTER"

    LOG_ID = "dota-activity-log"

    EMPTY_LINE = "[dim]  No heroes yet[/]"

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    DOTAActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    #: The ``format_row`` hook. A ``staticmethod``: the row is a function of
    #: the hero alone.
    format_row = staticmethod(_hero_to_text)

    def dedupe_key(self, event: dict) -> None:
        """Always new: a roster is a snapshot, not a stream.

        A hero carries no ``tx_hash``, and the same hero reappearing with a
        different HP is the whole point of the panel -- deduping it would
        freeze the roster at its first poll.
        """
        return None

    def update_data(
        self,
        heroes: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with the current hero roster.

        Sorted alive-first, then by level descending -- the order is the
        panel's, so it is applied before the base writes the rows.
        """
        if heroes:
            heroes = sorted(
                heroes,
                key=lambda h: (not h.get("alive", False), -h.get("level", 0)),
            )
        self.render_events(heroes)
