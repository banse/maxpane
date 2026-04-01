"""Multi-token price sparkline panel for Base Terminal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.base_tokens import format_price
from maxpane_dashboard.data.base_models import BaseToken

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 12
_MAX_TOKENS = 5


def _build_sparkline(
    points: list[tuple[float, float]], width: int = _SPARK_WIDTH
) -> str:
    """Convert time-series points into a sparkline string."""
    if len(points) < 2:
        return "\u2581" * width

    values = [p[1] for p in points]
    if len(values) > width:
        values = values[-width:]

    lo = min(values)
    hi = max(values)
    span = hi - lo

    chars: list[str] = []
    for v in values:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])

    return "".join(chars)


class PriceSparklines(Vertical):
    """Panel showing price trend sparklines for top tokens."""

    DEFAULT_CSS = """
    PriceSparklines > .spark-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PriceSparklines > .spark-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("PRICE SPARKLINES", classes="spark-title")
        yield Static("[dim]  Loading...[/]", classes="spark-line", id="spark-0")
        for i in range(1, _MAX_TOKENS):
            yield Static("", classes="spark-line", id=f"spark-{i}")

    def update_data(
        self,
        tokens: list[BaseToken],
        price_histories: dict[str, list[tuple[float, float]]],
    ) -> None:
        """Render sparklines for top tokens using cached price histories."""
        display_tokens = tokens[:_MAX_TOKENS]

        for i in range(_MAX_TOKENS):
            widget = self.query_one(f"#spark-{i}", Static)
            if i >= len(display_tokens):
                widget.update("")
                continue

            token = display_tokens[i]
            history = price_histories.get(token.address.lower(), [])
            sparkline = _build_sparkline(history)
            price_str = format_price(token.price_usd)

            # Determine trend from 24h change
            change_24h = token.price_change_24h
            if change_24h is not None and change_24h > 0:
                arrow = "[green]\u25b2[/]"
                color = "green"
            elif change_24h is not None and change_24h < 0:
                arrow = "[red]\u25bc[/]"
                color = "red"
            else:
                arrow = "[dim]\u25cf[/]"
                color = "dim"

            symbol = token.symbol[:8].ljust(8)

            widget.update(
                f"  [dim]{symbol}[/] [{color}]{sparkline}[/]  "
                f"[bold]{price_str}[/]  {arrow}"
            )
