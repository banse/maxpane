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
from maxpane_dashboard.widgets.markup_safety import safe_markup


def _fmt_signal(sig: dict | None) -> str:
    """Render one signal row using Textual markup.

    Returns an empty string when ``sig`` is ``None`` so callers can hide
    the row entirely (used for the optional ``fresh_launch`` slot).

    The label prefix is intentionally dropped (CR6) -- the value string
    already restates the concept (e.g. "0 buybacks ready"), so dropping
    the redundant label gives the value more horizontal room.
    """
    if not sig:
        return ""
    if not isinstance(sig, dict):
        return ""
    value = safe_markup(sig.get("value_str") or "--")
    color = sig.get("color") or "dim"
    indicator = sig.get("indicator") or "●"
    return f"  [{color}]{indicator}[/] [{color}]{value}[/]"


class TTTSignals(Vertical):
    """Analytical signals panel with up to four rows."""

    DEFAULT_CSS = """
    /* `margin: 0 0 1 0` is the repo-wide blank row under a widget title and it
       is not optional. CR2.2 deleted the dedicated spacer here and let the
       optional fresh-launch row stand in for it, which is right exactly half
       the time: with no fresh launch the row renders empty and the blank is
       there, and the moment a launch IS fresh the row fills with content and
       the title loses its blank without anything saying so. The state that
       removes the row is the state the panel exists to announce. The margin
       cannot be cancelled by a payload; the fresh row now hides itself when it
       has nothing to say, so there is still exactly one blank row either way. */
    TTTSignals > .ttt-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
        margin: 0 0 1 0;
    }
    TTTSignals > .ttt-signals-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="ttt-signals-title")
        # Optional row: present only when there IS a fresh launch. It used to
        # double as the title spacer (CR2.2), which meant the blank row came
        # and went with the payload -- see the note on the title's margin.
        # `display = False` collapses it, so an absent launch costs no row at
        # all and the panel is the same height it was before the margin.
        fresh = Static("", classes="ttt-signals-body", id="ttt-sig-fresh")
        fresh.display = False
        yield fresh
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
        # Blank-line separator between the two activity dots (buybacks /
        # decay) and the informational concentration row.
        yield Static("", classes="ttt-signals-body", id="ttt-sig-sep")
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

        ``fresh_launch_signal`` may be ``None`` -- in that case the row is
        collapsed with ``display = False`` and the panel shows only the
        remaining three rows. It is collapsed rather than left empty because
        the blank row under the title is now the title's own margin: an
        always-present empty row would sit *below* that margin and read as a
        second blank.
        """
        # Fresh launch (optional)
        fresh_widget = self.query_one("#ttt-sig-fresh", Static)
        fresh_text = _fmt_signal(fresh_launch_signal)
        fresh_widget.update(fresh_text)
        fresh_widget.display = bool(fresh_text)

        # Buybacks ready
        bb_widget = self.query_one("#ttt-sig-buybacks", Static)
        bb_widget.update(_fmt_signal(buybacks_ready_signal) or
                         _fmt_signal({"value_str": "--"}))

        # Decay window
        decay_widget = self.query_one("#ttt-sig-decay", Static)
        decay_widget.update(_fmt_signal(decay_window_signal) or
                            _fmt_signal({"value_str": "--"}))

        # Concentration
        conc_widget = self.query_one("#ttt-sig-concentration", Static)
        conc_widget.update(_fmt_signal(concentration_signal) or
                           _fmt_signal({"value_str": "--"}))
