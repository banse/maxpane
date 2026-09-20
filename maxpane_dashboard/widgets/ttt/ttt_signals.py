"""4-line signals panel for the TTT dashboard.

Renders up to four analytical signal rows:

1. **Fresh launch** -- only present when a token was just minted (the
   manager forwards ``None`` when there is no fresh launch, and the
   widget collapses the row in that case, leaving a 3-row panel).
2. **Buybacks ready** -- count / TVL of buyback bounties currently
   redeemable.
3. **Decay window** -- aggregate decay tax info across active tokens.
4. **Concentration** -- holder-pool concentration multiplier vs today.

Each signal dict (per WP3 schema) carries:

```
{"label": str, "value_str": str, "indicator": str, "color": str}
```

The rows, their guard, the blank separator and the formatter are
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 7,
WP-B); the rows are **label-less** (``(id, None)``) because each value
string already restates its own concept, and the blank row before
CONCENTRATION is a bare ``None`` item -- a separator, not the title's
blank row, which is ``PanelBase``'s margin.

**Named change 2 lands here.** The four rows were four bare
``query_one(...).update(...)`` calls, so a malformed signal dict raised
into the screen's ``except`` and left the previous poll's rows on screen
as if they were live. Every row now goes through
``render_signal``/``write_guarded``, which builds inside the guard, and a
signal the manager could not compute renders ``unavailable`` instead of
the ``--`` this copy used -- ``--`` is the analytics saying "nothing to
report", and a failed read may not wear a real negative's clothes.
``data/ttt_manager.py`` masks every ``None`` signal with a ``--`` dict of
its own before it reaches this panel, so the new state is not reachable
from the live manager; it is reachable from a payload that serves ``None``
(a cache file, a test), and *that* is the case it exists for.
"""

from __future__ import annotations

from textual.app import ComposeResult

from maxpane_dashboard.widgets.panels import SignalsPanelBase

#: The optional row: shown only when there IS a fresh launch. It used to
#: double as the title spacer (CR2.2), which meant the blank row came and
#: went with the payload -- the state that removes the row is the state the
#: panel exists to announce. The blank row is ``PanelBase``'s title margin
#: now, and cannot be cancelled by a payload; this row collapses with
#: ``display = False`` so an absent launch costs no row at all.
_FRESH_ID = "ttt-sig-fresh"


class TTTSignals(SignalsPanelBase):
    """Analytical signals panel with up to four rows."""

    TITLE = "SIGNALS"

    ROWS = (
        (_FRESH_ID, None),
        ("ttt-sig-buybacks", None),
        ("ttt-sig-decay", None),
        # Blank-line separator between the two activity dots (buybacks /
        # decay) and the informational concentration row.
        None,
        ("ttt-sig-concentration", None),
    )

    def compose_body(self) -> ComposeResult:
        """The base's rows, with the optional fresh-launch row collapsed."""
        for widget in super().compose_body():
            if widget.id == _FRESH_ID:
                widget.display = False
            yield widget

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
        remaining three rows. It is collapsed rather than left empty
        because the blank row under the title is the title's own margin: an
        always-present empty row would sit *below* that margin and read as
        a second blank.
        """
        self.render_signal(
            f"#{_FRESH_ID}", "Fresh launch", fresh_launch_signal,
            labelled=False,
        )
        # The toggle reads the *payload*, not the row it just wrote: the
        # row now says ``unavailable`` for a signal that could not be
        # computed, and "there is no fresh launch" is the only reason this
        # panel hides a row.
        try:
            fresh = self.query_one(f"#{_FRESH_ID}")
        except Exception:
            pass
        else:
            fresh.display = bool(
                isinstance(fresh_launch_signal, dict) and fresh_launch_signal
            )

        self.render_signal(
            "#ttt-sig-buybacks", "Buybacks ready", buybacks_ready_signal,
            labelled=False,
        )
        self.render_signal(
            "#ttt-sig-decay", "Decay window", decay_window_signal,
            labelled=False,
        )
        self.render_signal(
            "#ttt-sig-concentration", "Concentration", concentration_signal,
            labelled=False,
        )
