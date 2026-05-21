"""4-line signals panel for the TTT dashboard.

Renders up to four analytical signal rows:

1. **Fresh launch** -- only present when a token was just minted (the
   manager forwards ``None`` when there is no fresh launch, and the
   widget omits the row in that case, leaving a 3-row panel).
2. **Buybacks ready** -- count / TVL of buyback bounties currently
   redeemable.
3. **Decay window** -- aggregate decay tax info across active tokens.
4. **Concentration** -- holder-pool concentration multiplier vs today.

Each signal dict (per WP3 schema) carries:

```
{"label": str, "value_str": str, "indicator": str, "color": str}
```

Missing keys collapse to safe defaults; the row never crashes.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _fmt_signal(sig: dict | None) -> str:
    """Render one signal row using Textual markup.

    Returns an empty string when ``sig`` is ``None`` so callers can hide
    the row entirely (used for the optional ``fresh_launch`` slot).
    """
    if not sig:
        return ""
    if not isinstance(sig, dict):
        return ""
    label = sig.get("label") or ""
    value = sig.get("value_str") or "--"
    color = sig.get("color") or "dim"
    indicator = sig.get("indicator") or "●"
    return (
        f"  [{color}]{indicator}[/] {label:<22} "
        f"[{color}]{value}[/]"
    )


class TTTSignals(Vertical):
    """Analytical signals panel with up to four rows."""

    DEFAULT_CSS = """
    TTTSignals > .ttt-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTSignals > .ttt-signals-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="ttt-signals-title")
        yield Static("", classes="ttt-signals-body", id="ttt-sig-spacer")
        yield Static(
            "[dim]  Loading...[/]",
            classes="ttt-signals-body",
            id="ttt-sig-fresh",
        )
        yield Static(
            "",
            classes="ttt-signals-body",
            id="ttt-sig-buybacks",
        )
        yield Static(
            "",
            classes="ttt-signals-body",
            id="ttt-sig-decay",
        )
        yield Static(
            "",
            classes="ttt-signals-body",
            id="ttt-sig-concentration",
        )

    def update_data(
        self,
        fresh_launch_signal=None,
        buybacks_ready_signal=None,
        decay_window_signal=None,
        concentration_signal=None,
        **_kwargs,
    ) -> None:
        """Refresh the four rows.

        ``fresh_launch_signal`` may be ``None`` -- in that case the row
        is hidden (rendered as an empty Static) and the panel shows only
        the remaining three rows.
        """
        # Fresh launch (optional)
        fresh_widget = self.query_one("#ttt-sig-fresh", Static)
        fresh_widget.update(_fmt_signal(fresh_launch_signal))

        # Buybacks ready
        bb_widget = self.query_one("#ttt-sig-buybacks", Static)
        bb_widget.update(_fmt_signal(buybacks_ready_signal) or
                         _fmt_signal({"label": "Buybacks ready", "value_str": "--"}))

        # Decay window
        decay_widget = self.query_one("#ttt-sig-decay", Static)
        decay_widget.update(_fmt_signal(decay_window_signal) or
                            _fmt_signal({"label": "Decay window", "value_str": "--"}))

        # Concentration
        conc_widget = self.query_one("#ttt-sig-concentration", Static)
        conc_widget.update(_fmt_signal(concentration_signal) or
                           _fmt_signal({"label": "Concentration", "value_str": "--"}))
