"""Expected-value tables for boosts and attacks.

On ``widgets/panels.py`` since Branch 8 WP-B: a
:class:`~maxpane_dashboard.widgets.panels.PanelBase` whose three rows are
each built inside :meth:`~maxpane_dashboard.widgets.panels.PanelBase.write_guarded`,
so a ranking the manager could not produce says ``unavailable`` on every
row instead of raising into the screen's ``except`` and leaving
``Loading...`` up (MEDI-38).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.analytics.ev import CATALOG_SOURCE_LIVE
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import LOADING_ROW, UNAVAILABLE_LINE, PanelBase

_HEADER = f"  {'Boosts':<14} {'EV':>10}    {'Attacks':<14} {'Gap':>8}"
_ROW_IDS = ("ev-row-0", "ev-row-1", "ev-row-2")
_STALE_TITLE = "BEST PLAYS  [yellow]⚠ STALE CATALOG (live fetch failed)[/]"


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


def _row(i: int, boost_rankings, attack_rankings) -> str:
    """Row *i* of the side-by-side table; raises on a ranking it cannot read."""
    # Boost side
    if i < len(boost_rankings):
        b_name, b_ev = boost_rankings[i]
        star = "[yellow]★[/] " if i == 0 else "  "
        b_name_str = safe_markup(_truncate(b_name, 14))
        b_ev_raw = f"+{b_ev:,.0f}" if b_ev >= 0 else f"{b_ev:,.0f}"
        b_ev_str = (
            f"[green]{b_ev_raw:>10}[/]" if b_ev >= 0 else f"[red]{b_ev_raw:>10}[/]"
        )
    else:
        star = "  "
        b_name_str = " " * 14
        b_ev_str = " " * 10

    # Attack side
    if i < len(attack_rankings):
        a_name, a_ratio = attack_rankings[i]
        a_star = "[yellow]★[/] " if i == 0 else "  "
        a_name_str = safe_markup(_truncate(a_name, 14))
        a_ratio_raw = f"{a_ratio:.1f}x"
        a_ratio_str = (
            f"[green]{a_ratio_raw:>8}[/]" if a_ratio > 0 else f"[dim]{a_ratio_raw:>8}[/]"
        )
    else:
        a_star = "  "
        a_name_str = ""
        a_ratio_str = ""

    return f"{star}{b_name_str} {b_ev_str}  {a_star}{a_name_str} {a_ratio_str}"


class EVTable(PanelBase):
    """Side-by-side tables showing best boost and attack plays."""

    TITLE = "BEST PLAYS"

    def compose_body(self) -> ComposeResult:
        yield Static(_HEADER, classes="panel-line", id="ev-header")
        # Between the header and the rows -- not the title's blank row, which
        # is ``PanelBase``'s margin.
        yield Static("", classes="panel-line")
        yield Static(LOADING_ROW, classes="panel-line", id=_ROW_IDS[0])
        yield Static("", classes="panel-line", id=_ROW_IDS[1])
        yield Static("", classes="panel-line", id=_ROW_IDS[2])

    def update_data(
        self,
        boost_rankings: list[tuple[str, float]],
        attack_rankings: list[tuple[str, float]],
        catalog_source: str = CATALOG_SOURCE_LIVE,
    ) -> None:
        """Show top 3 boosts by EV and top 3 attacks by gap-closure ratio.

        ``catalog_source`` says where the boost/attack parameters came from.
        Anything other than ``"live"`` means the ranking was computed from the
        hardcoded fallback table, whose costs/durations are season-old -- that
        is labelled in the title rather than passed off as current data.

        The manager always hands over two lists (``analytics.ev.rank_*``), so
        a ranking that is not one is a read that failed: each row says
        ``unavailable`` rather than painting three blank lines.
        """
        self.write(
            ".panel-title",
            self.TITLE if catalog_source == CATALOG_SOURCE_LIVE else _STALE_TITLE,
        )
        for i, row_id in enumerate(_ROW_IDS):
            self.write_guarded(
                f"#{row_id}",
                lambda i=i: _row(i, boost_rankings, attack_rankings),
                UNAVAILABLE_LINE,
            )
