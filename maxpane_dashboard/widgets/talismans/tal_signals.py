"""4-line signals panel for the Talismans dashboard.

Renders up to four analytical signal rows:

1. **Conservation**    -- whether the core-conservation invariant holds.
2. **Cut/Merge**       -- net cut-vs-merge flow signal.
3. **Forge momentum**  -- recent Mythic forge momentum.
4. **Mythic scarcity** -- how scarce Mythics currently are.

Each signal dict (per WP3 schema) carries:

```
{"label": str, "value_str": str, "indicator": str, "color": str}
```

Missing keys collapse to safe defaults; the row never crashes.  A blank
line precedes the FORGE MOMENTUM row, matching the TTT convention of a
blank-line separator before one signal.

Copied from ``ttt_signals.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _fmt_signal(sig: dict | None) -> str:
    """Render one signal row using Textual markup.

    Returns an empty string when ``sig`` is ``None`` / not a dict; in practice
    callers pass ``{"value_str": "--"}`` rather than ``None`` so each of the
    four rows always renders.

    The label prefix is intentionally dropped -- the value string already
    restates the concept, so dropping the redundant label gives the value
    more horizontal room.
    """
    if not sig:
        return ""
    if not isinstance(sig, dict):
        return ""
    value = sig.get("value_str") or "--"
    color = sig.get("color") or "dim"
    indicator = sig.get("indicator") or "●"
    return f"  [{color}]{indicator}[/] [{color}]{value}[/]"


class TalismansSignals(Vertical):
    """Analytical signals panel with up to four rows."""

    DEFAULT_CSS = """
    TalismansSignals > .tal-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansSignals > .tal-signals-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="tal-signals-title")
        # Blank line below the title (doubles as the title spacer).
        yield Static("", classes="tal-signals-body", id="tal-sig-spacer")
        yield Static("", classes="tal-signals-body", id="tal-sig-conservation")
        yield Static("", classes="tal-signals-body", id="tal-sig-cutmerge")
        # Blank-line separator before the forge-momentum row.
        yield Static("", classes="tal-signals-body", id="tal-sig-sep")
        yield Static("", classes="tal-signals-body", id="tal-sig-forge")
        yield Static("", classes="tal-signals-body", id="tal-sig-scarcity")

    def update_data(
        self,
        conservation_signal=None,
        cutmerge_signal=None,
        forge_momentum_signal=None,
        mythic_scarcity_signal=None,
        **_kwargs,
    ) -> None:
        """Refresh the four signal rows."""
        conservation_widget = self.query_one(
            "#tal-sig-conservation", Static
        )
        conservation_widget.update(
            _fmt_signal(conservation_signal)
            or _fmt_signal({"value_str": "--"})
        )

        cutmerge_widget = self.query_one("#tal-sig-cutmerge", Static)
        cutmerge_widget.update(
            _fmt_signal(cutmerge_signal) or _fmt_signal({"value_str": "--"})
        )

        forge_widget = self.query_one("#tal-sig-forge", Static)
        forge_widget.update(
            _fmt_signal(forge_momentum_signal)
            or _fmt_signal({"value_str": "--"})
        )

        scarcity_widget = self.query_one("#tal-sig-scarcity", Static)
        scarcity_widget.update(
            _fmt_signal(mythic_scarcity_signal)
            or _fmt_signal({"value_str": "--"})
        )
