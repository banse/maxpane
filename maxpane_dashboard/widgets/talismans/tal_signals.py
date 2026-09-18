"""4-line signals panel for the Talismans dashboard.

Renders up to four analytical signal rows:

1. **Conservation**    -- whether the core-conservation invariant holds.
2. **Cut/Merge**       -- whether the cut/merge layer is LIVE or LOCKED.
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

#: Shown in place of a signal the backend could not compute this poll
#: (MEDI-38) -- distinct from a signal whose own ``value_str`` is ``--``.
_UNAVAILABLE_SIGNAL = {"value_str": "unavailable", "color": "yellow"}


def _fmt_signal(sig: dict | None) -> str:
    """Render one signal row using Textual markup.

    Returns an empty string when ``sig`` is ``None`` / not a dict; the panel
    then renders :data:`_UNAVAILABLE_SIGNAL` in that row (MEDI-38), so a
    signal the manager could not compute is named as such rather than
    shown as the ``--`` a computed signal uses for "nothing to report".

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
        """Refresh the four signal rows; a missing signal says so."""
        self._render_row("#tal-sig-conservation", conservation_signal)
        self._render_row("#tal-sig-cutmerge", cutmerge_signal)
        self._render_row("#tal-sig-forge", forge_momentum_signal)
        self._render_row("#tal-sig-scarcity", mythic_scarcity_signal)

    def _render_row(self, selector: str, sig) -> None:
        """Write one row, degrading to an explicit unavailable state.

        The row is formatted inside the guard so a malformed signal cannot
        raise into the screen's ``except`` and leave the previous poll's
        rows on screen as if they were live.
        """
        try:
            widget = self.query_one(selector, Static)
        except Exception:
            return
        try:
            widget.update(_fmt_signal(sig) or _fmt_signal(_UNAVAILABLE_SIGNAL))
        except Exception:
            try:
                widget.update(_fmt_signal(_UNAVAILABLE_SIGNAL))
            except Exception:
                pass
