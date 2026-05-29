"""Hero metric boxes for the Talismans NFT dashboard.

Four boxes laid out horizontally:

* LIVE TOKENS    -- currently live token supply, with a drift subtitle
  showing the signed delta from the 1,536 genesis mint.
* MYTHICS        -- count of Mythic talismans, with a "% · forged"
  subtitle.
* TOTAL CORES    -- total cores in the system, with a conservation
  subtitle (green ``conserved`` when the invariant holds, else a
  warning ``DRIFT``).
* 24H OPERATIONS -- count of operations in the last 24h, with an
  all-time-total subtitle.

Each value is rendered exception-safe: a missing/None scalar collapses to
``"--"`` rather than raising.  This matches the project rule that widgets
must never crash on partial data.

Copied from ``ttt_hero_metrics.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

_GENESIS = 1536


class TalismansHeroBox(Static):
    """A single hero metric box: title, big number, subtitle."""

    DEFAULT_CSS = ""


class TalismansHeroMetrics(Horizontal):
    """Row of four hero metric boxes for the Talismans dashboard."""

    DEFAULT_CSS = """
    TalismansHeroMetrics > TalismansHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TalismansHeroBox(
            "[dim]LIVE TOKENS[/]\n\n[dim]Loading...[/]",
            id="tal-hero-tokens",
            classes="tal-hero-box",
        )
        yield TalismansHeroBox(
            "[dim]MYTHICS[/]\n\n[dim]Loading...[/]",
            id="tal-hero-mythics",
            classes="tal-hero-box",
        )
        yield TalismansHeroBox(
            "[dim]TOTAL CORES[/]\n\n[dim]Loading...[/]",
            id="tal-hero-cores",
            classes="tal-hero-box",
        )
        yield TalismansHeroBox(
            "[dim]24H OPERATIONS[/]\n\n[dim]Loading...[/]",
            id="tal-hero-ops",
            classes="tal-hero-box",
        )

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _fmt_int(value) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _fmt_float(value, fmt: str) -> str:
        try:
            return format(float(value), fmt)
        except (TypeError, ValueError):
            return "--"

    # -- update ---------------------------------------------------------

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

        # -- LIVE TOKENS ------------------------------------------------
        tokens_box = self.query_one("#tal-hero-tokens", TalismansHeroBox)
        if live_tokens is None:
            tokens_box.update(
                "[dim]LIVE TOKENS[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_int(live_tokens)
            try:
                drift = int(token_drift)
                sub = f"{drift:+d} from genesis"
            except (TypeError, ValueError):
                sub = "--"
            tokens_box.update(
                f"[dim]LIVE TOKENS[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
            )

        # -- MYTHICS ----------------------------------------------------
        mythics_box = self.query_one("#tal-hero-mythics", TalismansHeroBox)
        if mythic_count is None:
            mythics_box.update(
                "[dim]MYTHICS[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_int(mythic_count)
            pct = self._fmt_float(mythic_pct, ".1f")
            forged = self._fmt_int(mythics_ever_forged)
            sub = f"{pct}% · {forged} forged"
            mythics_box.update(
                f"[dim]MYTHICS[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
            )

        # -- TOTAL CORES ------------------------------------------------
        cores_box = self.query_one("#tal-hero-cores", TalismansHeroBox)
        if total_cores is None:
            cores_box.update(
                "[dim]TOTAL CORES[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_int(total_cores)
            if cores_invariant_intact:
                sub = "[green]conserved[/]"
            else:
                sub = "[yellow]DRIFT[/]"
            cores_box.update(
                f"[dim]TOTAL CORES[/]\n\n[bold white]{big}[/]\n{sub}"
            )

        # -- 24H OPERATIONS ---------------------------------------------
        ops_box = self.query_one("#tal-hero-ops", TalismansHeroBox)
        if operations_24h is None:
            ops_box.update(
                "[dim]24H OPERATIONS[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_int(operations_24h)
            total = self._fmt_int(operations_total)
            sub = f"{total} all-time"
            ops_box.update(
                f"[dim]24H OPERATIONS[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
            )
