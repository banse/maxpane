"""Volume sparklines widget showing trading volume trends per token."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from dashboard.analytics.base_tokens import format_volume
from dashboard.data.base_models import BaseToken

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 35
_MAX_TOKENS = 5


def _build_sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Build a sparkline from numeric values."""
    if len(values) < 2:
        return _SPARK_CHARS[0] * width
    if len(values) > width:
        values = values[-width:]
    lo, hi = min(values), max(values)
    span = hi - lo
    chars: list[str] = []
    for v in values:
        idx = 0 if span == 0 else int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])
    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])
    return "".join(chars)


class VolumeSparklines(Vertical):
    """Volume trend sparklines for top tokens — pairs with PriceSparklines."""

    def compose(self) -> ComposeResult:
        yield Static("VOLUME TRENDS", classes="volspark-title")
        yield Static("[dim]Loading...[/]", id="volspark-body")

    def update_data(
        self,
        tokens: list[BaseToken],
        volume_histories: dict[str, list[tuple[float, float]]],
    ) -> None:
        """Update sparklines from token list and cached volume histories."""
        display = tokens[:_MAX_TOKENS]

        if not display:
            self.query_one("#volspark-body", Static).update(
                "[dim]No tokens tracked yet[/]"
            )
            return

        lines: list[str] = []
        for token in display:
            history = volume_histories.get(token.address.lower(), [])
            vol_values = [p[1] for p in history] if history else []
            sparkline = _build_sparkline(vol_values)
            vol_str = format_volume(token.volume_24h)
            symbol = token.symbol[:8].ljust(8)

            # Color by volume relative to top token
            if display and token.volume_24h >= display[0].volume_24h * 0.5:
                colour = "cyan"
            elif token.volume_24h > 0:
                colour = "dim"
            else:
                colour = "red"

            line = (
                f"[bold]{symbol}[/]"
                f" {vol_str:>10}  "
                f"[{colour}]{sparkline}[/]"
            )
            lines.append(line)

        self.query_one("#volspark-body", Static).update("\n".join(lines))
