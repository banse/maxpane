"""Signals panel showing key game metrics and recommendations.

On ``widgets/panels.py`` since Branch 8 WP-B: a
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase` whose rows are
the **trailing** shape (label, value, then the dot and a word) that
:func:`~maxpane_dashboard.widgets.panels.fmt_signal_trailing` states, shared
with the base terminal's ``BTSignals``. Every row is built inside its own
guard: a signal the manager could not compute says ``unavailable`` beside
its label instead of raising into the screen's ``except`` and leaving
``Loading...`` up (MEDI-38).
"""

from __future__ import annotations

from typing import Any

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import (
    UNAVAILABLE,
    SignalsPanelBase,
    fmt_signal_trailing,
)

_REC_PREFIX = "  [dim]→ Recommendation:[/]"
_REC_UNAVAILABLE = f"{_REC_PREFIX} {UNAVAILABLE}"


def _ev_color(value: float) -> str:
    if value > 0:
        return "green"
    elif value < 0:
        return "red"
    return "white"


def _gap_trend_label(gap_rate: float) -> tuple[str, str]:
    """Return (label, color) for gap trend."""
    if gap_rate > 0:
        return "widening", "red"
    elif gap_rate < 0:
        return "closing", "green"
    return "stable", "white"


def _dominance_color(dominance: float) -> str:
    if dominance >= 3.0:
        return "yellow"
    elif dominance >= 2.0:
        return "white"
    return "green"


def _late_join_cells(late_join_ev: dict[str, Any]) -> tuple[str, str, str]:
    ev_usd = late_join_ev.get("ev_usd", 0.0)
    value = "${:,.2f}".format(ev_usd)
    return value, "positive" if ev_usd > 0 else "negative", _ev_color(ev_usd)


def _gap_trend_cells(gap_analysis: dict[str, Any]) -> tuple[str, str, str]:
    gap_rate = gap_analysis.get("gap_rate", 0.0)
    trend_label, trend_color = _gap_trend_label(gap_rate)
    return trend_label, trend_label, trend_color


def _dominance_cells(dominance: float) -> tuple[str, str, str]:
    value = f"{dominance:.1f}x" if dominance < float("inf") else "∞x"
    return value, "warning" if dominance >= 3.0 else "healthy", _dominance_color(dominance)


class SignalsPanel(SignalsPanelBase):
    """Panel displaying analytical signals and recommendation."""

    TITLE = "SIGNALS"
    ROWS = (
        ("sig-late-join", "Late-Join EV"),
        ("sig-gap-trend", "Gap Trend"),
        ("sig-dominance", "Leader Dominance"),
    )
    RECOMMENDATION_ID = "sig-recommendation"

    def update_data(
        self,
        late_join_ev: dict[str, Any],
        gap_analysis: dict[str, Any],
        dominance: float,
        recommendation: str,
    ) -> None:
        """Update all signal lines with computed analytics."""
        self._signal_row("#sig-late-join", "Late-Join EV",
                         lambda: _late_join_cells(late_join_ev))
        self._signal_row("#sig-gap-trend", "Gap Trend",
                         lambda: _gap_trend_cells(gap_analysis))
        self._signal_row("#sig-dominance", "Leader Dominance",
                         lambda: _dominance_cells(dominance))

        def recommend() -> str:
            if recommendation is None:
                return _REC_UNAVAILABLE
            # Assembled in ``analytics/`` out of names the game API supplied.
            return f"{_REC_PREFIX} [bold]{safe_markup(str(recommendation))}[/]"

        self.write_guarded(f"#{self.RECOMMENDATION_ID}", recommend, _REC_UNAVAILABLE)

    def _signal_row(self, selector: str, label: str, cells) -> bool:
        """One trailing-shape row; *cells* builds ``(value, indicator, color)``."""

        def build() -> str:
            value, indicator, color = cells()
            return fmt_signal_trailing(label, value, indicator=indicator, color=color)

        return self.write_guarded(
            selector, build,
            fmt_signal_trailing(
                label, "unavailable", indicator="", color="yellow", value_color="yellow"
            ),
        )
