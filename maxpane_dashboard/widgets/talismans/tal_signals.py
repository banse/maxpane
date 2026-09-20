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

The rows, their guard, the blank separator and the formatter are
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 7,
WP-B). Two things this panel contributes to that base: its rows are
**label-less** (``(id, None)`` -- the value string already restates the
concept, so a label column would only repeat it and take the room), and
the blank row before FORGE MOMENTUM is a bare ``None`` item, a
**separator**, distinct from the title's blank row, which is
``PanelBase``'s margin.

``_UNAVAILABLE_SIGNAL`` is gone with the copy it belonged to: the base
renders the same ``  ● unavailable`` for a signal the manager could not
compute, and it now **escapes** ``value_str`` on the way (change 3) --
this copy did not, and a signal value is read off a chain where a token
symbol may be spelled ``[/x]``.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SignalsPanelBase


class TalismansSignals(SignalsPanelBase):
    """Analytical signals panel with up to four rows."""

    TITLE = "SIGNALS"

    ROWS = (
        ("tal-sig-conservation", None),
        ("tal-sig-cutmerge", None),
        # Blank-line separator before the forge-momentum row.
        None,
        ("tal-sig-forge", None),
        ("tal-sig-scarcity", None),
    )

    def update_data(
        self,
        conservation_signal=None,
        cutmerge_signal=None,
        forge_momentum_signal=None,
        mythic_scarcity_signal=None,
        **_kwargs,
    ) -> None:
        """Refresh the four signal rows; a missing signal says so."""
        self.render_signal(
            "#tal-sig-conservation", "Conservation", conservation_signal,
            labelled=False,
        )
        self.render_signal(
            "#tal-sig-cutmerge", "Cut/Merge", cutmerge_signal, labelled=False,
        )
        self.render_signal(
            "#tal-sig-forge", "Forge", forge_momentum_signal, labelled=False,
        )
        self.render_signal(
            "#tal-sig-scarcity", "Scarcity", mythic_scarcity_signal,
            labelled=False,
        )
