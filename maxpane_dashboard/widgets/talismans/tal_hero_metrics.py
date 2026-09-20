"""Hero metric boxes for the Talismans NFT dashboard.

Four boxes laid out horizontally:

* LIVE TOKENS    -- currently live token supply, with a drift subtitle
  showing the signed delta from the genesis mint.
* MYTHICS        -- count of Mythic talismans, with a "% · forged"
  subtitle.
* TOTAL CORES    -- total cores in the system, with a conservation
  subtitle (green ``conserved`` when the invariant holds, else a
  warning ``DRIFT``).
* 24H OPERATIONS -- count of operations in the last 24h, with an
  all-time-total subtitle.

The row, the boxes and their guard are
:class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 7, WP-B).
**That guard is the change this migration makes here** (named change 2):
the four boxes were four bare ``query_one(...).update(...)`` calls, so a
missing box raised into the screen's ``except`` and left the previous
poll's numbers on screen as if they were live, and a value the formatter
could not read did the same. Each body is now built *inside*
:meth:`~maxpane_dashboard.widgets.panels.HeroRow.render_box`'s guard and
a build that raises lands on an explicit ``unavailable``.

``--`` is still what a scalar the manager served as ``None`` renders:
that is a deliberate "nothing to report" (``total_cores`` while the
enumeration syncs), not a failed read, and the two must stay tellable
apart.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.panels import HeroBoxBase, HeroRow

#: What a box whose scalar arrived as ``None`` shows: the value and its
#: subtitle both say "nothing to report", which is not the same claim as
#: ``unavailable`` (the guard's, for a read that failed).
_NO_VALUE = "[dim]--[/]\n[dim]--[/]"


class TalismansHeroBox(HeroBoxBase):
    """A single hero metric box: title, big number, subtitle."""

    DEFAULT_CSS = ""


class TalismansHeroMetrics(HeroRow):
    """Row of four hero metric boxes for the Talismans dashboard."""

    BOX_CLASS = TalismansHeroBox

    BOXES = (
        ("tal-hero-tokens", "LIVE TOKENS"),
        ("tal-hero-mythics", "MYTHICS"),
        ("tal-hero-cores", "TOTAL CORES"),
        ("tal-hero-ops", "24H OPERATIONS"),
    )

    DEFAULT_CSS = """
    TalismansHeroMetrics > TalismansHeroBox {
        margin: 0 1;
    }
    """

    def update_data(
        self,
        live_tokens=None,
        token_drift=None,
        mythic_count=None,
        mythic_pct=None,
        mythics_ever_forged=None,
        total_cores=None,
        cores_invariant_intact=None,
        genesis_minted=None,
        operations_24h=None,
        operations_total=None,
        **_kwargs,
    ) -> None:
        """Refresh all four hero boxes from the manager's flat dict."""

        def tokens() -> str:
            if live_tokens is None:
                return _NO_VALUE
            try:
                sub = f"{int(token_drift):+d} from genesis"
            except (TypeError, ValueError):
                sub = "--"
            return f"[bold white]{fmt_int(live_tokens)}[/]\n[dim]{sub}[/]"

        def mythics() -> str:
            if mythic_count is None:
                return _NO_VALUE
            pct = fmt_float(mythic_pct, ".1f")
            forged = fmt_int(mythics_ever_forged)
            return (
                f"[bold white]{fmt_int(mythic_count)}[/]\n"
                f"[dim]{pct}% · {forged} forged[/]"
            )

        def cores() -> str:
            if total_cores is None:
                return _NO_VALUE
            sub = "[green]conserved[/]" if cores_invariant_intact \
                else "[yellow]DRIFT[/]"
            return f"[bold white]{fmt_int(total_cores)}[/]\n{sub}"

        def ops() -> str:
            if operations_24h is None:
                return _NO_VALUE
            return (
                f"[bold white]{fmt_int(operations_24h)}[/]\n"
                f"[dim]{fmt_int(operations_total)} all-time[/]"
            )

        self.render_box("#tal-hero-tokens", "LIVE TOKENS", tokens)
        self.render_box("#tal-hero-mythics", "MYTHICS", mythics)
        self.render_box("#tal-hero-cores", "TOTAL CORES", cores)
        self.render_box("#tal-hero-ops", "24H OPERATIONS", ops)
