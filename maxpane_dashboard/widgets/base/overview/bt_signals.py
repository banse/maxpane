"""Trading signals panel for the Base Trading Overview view.

The rows, the ``Loading...`` seed, the guard and the recommendation *slot*
are :class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 8,
WP-A); the row **shape** is :func:`~maxpane_dashboard.widgets.panels.fmt_signal_trailing`,
the older of the two in the tree -- label, the value right-aligned, then a
coloured dot trailing it with nothing after -- which this panel shares with
bakery's ``SignalsPanel``. The classifier stays here: this panel is handed
plain strings, not signal dicts, and ``_signal_indicator`` turns each into
a value and a colour (``None`` -> a dim ``...``, the copy's own word for a
signal the manager could not compute this poll).

The recommendation line is not the base's ``-> …``: it is labelled
(``→ Recommendation: …``) and **blank when empty**, so this panel writes it
through ``write`` exactly as before rather than the base growing an option.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import SignalsPanelBase, fmt_signal_trailing


def _signal_indicator(label: str, value: str | None) -> tuple[str, str]:
    """Return (display_value, color) for a signal."""
    if value is None:
        return "...", "dim"
    val_lower = str(value).lower()
    if val_lower in ("bullish", "strong_buy", "buy", "high", "rising"):
        return str(value), "green"
    elif val_lower in ("bearish", "strong_sell", "sell", "low", "falling"):
        return str(value), "red"
    elif val_lower in ("neutral", "hold", "normal", "flat", "moderate"):
        return str(value), "yellow"
    return str(value), "white"


class BTSignals(SignalsPanelBase):
    """Panel displaying Base Trading analytical signals and recommendation."""

    TITLE = "SIGNALS"

    #: No separator item: the blank row between the last signal and the
    #: recommendation is the one ``SignalsPanelBase`` yields itself when
    #: ``RECOMMENDATION_ID`` is set (the copy's ``bto-sig-spacer-2``).
    ROWS = (
        ("bto-sig-buy-sell", "Buy/Sell"),
        ("bto-sig-volume", "Volume"),
        ("bto-sig-whale", "Whale Activity"),
    )

    RECOMMENDATION_ID = "bto-sig-recommendation"

    def _signal_row(self, selector: str, label: str, value: str | None) -> None:
        def build() -> str:
            display, color = _signal_indicator(label, value)
            return fmt_signal_trailing(label, display, indicator="", color=color)

        # The degraded row: the word in yellow like every other degraded
        # signal row in the tree, not the live rows' bold white (review M3).
        self.write_guarded(
            selector, build,
            fmt_signal_trailing(label, "unavailable", indicator="",
                                color="yellow", value_color="yellow"),
        )

    def update_data(
        self,
        buy_sell_signal: str | None = None,
        volume_signal: str | None = None,
        whale_signal: str | None = None,
        recommendation: str = "",
    ) -> None:
        """Update all signal lines with computed analytics."""
        self._signal_row("#bto-sig-buy-sell", "Buy/Sell", buy_sell_signal)
        self._signal_row("#bto-sig-volume", "Volume", volume_signal)
        self._signal_row("#bto-sig-whale", "Whale Activity", whale_signal)
        self.write(
            f"#{self.RECOMMENDATION_ID}",
            f"  [dim]→ Recommendation:[/] [bold]{safe_markup(recommendation)}[/]"
            if recommendation else "",
        )
