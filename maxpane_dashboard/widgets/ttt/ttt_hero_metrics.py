"""Hero metric boxes for the Ten Thousand Tokens (TTT) dashboard.

Four boxes laid out horizontally:

* UNBURNED NFTs -- remaining NFT supply out of 10,000
* TOKEN LAUNCHES -- total burns/launches with a 24h delta
* HOLDER POOL -- cumulative ETH paid to NFT holders, with a 24h delta
* TOTAL MCAP -- aggregated market cap (USD) across launched tokens with
  data, plus the Ξ-equivalent and the count of tokens contributing to
  the sum.

The row, the boxes and their guard are
:class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 7, WP-B).
**That guard is the change this migration makes here** (named change 2):
the four boxes were four bare ``query_one(...).update(...)`` calls, so a
missing box -- or a value the formatter could not read -- raised into the
screen's ``except`` and left the previous poll's numbers on screen as if
they were live. Each body is now built *inside* ``render_box``'s guard
and a build that raises lands on an explicit ``unavailable``.

``--`` is still what a scalar the manager served as ``None`` renders:
that is a deliberate "nothing to report", not a failed read.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.panels import HeroBoxBase, HeroRow

#: What a box whose scalar arrived as ``None`` shows -- a different claim
#: from ``unavailable`` (the guard's, for a read that failed).
_NO_VALUE = "[dim]--[/]\n[dim]--[/]"


class TTTHeroBox(HeroBoxBase):
    """A single hero metric box: title, big number, subtitle."""

    DEFAULT_CSS = ""


class TTTHeroMetrics(HeroRow):
    """Row of four hero metric boxes for the TTT dashboard."""

    BOX_CLASS = TTTHeroBox

    BOXES = (
        ("ttt-hero-unburned", "UNBURNED NFTs"),
        ("ttt-hero-launches", "TOKEN LAUNCHES"),
        ("ttt-hero-holders", "HOLDER POOL"),
        ("ttt-hero-mcap", "TOTAL MCAP"),
    )

    DEFAULT_CSS = """
    TTTHeroMetrics > TTTHeroBox {
        margin: 0 1;
    }
    """

    def update_data(
        self,
        unburned: int | None = None,
        burned_pct: float | None = None,
        launches: int | None = None,
        launches_24h: int | None = None,
        holder_pool_eth_total: float | None = None,
        holder_pool_eth_24h: float | None = None,
        total_mcap_usd: float | None = None,
        total_mcap_eth: float | None = None,
        total_mcap_token_count: int | None = None,
        **_kwargs,
    ) -> None:
        """Refresh all four hero boxes from the manager's flat dict."""

        def unburned_body() -> str:
            if unburned is None:
                return _NO_VALUE
            try:
                remaining_pct = 100.0 - float(burned_pct or 0.0)
                sub = f"{remaining_pct:.2f}% of 10,000"
            except (TypeError, ValueError):
                sub = "--"
            return f"[bold white]{fmt_int(unburned)}[/]\n[dim]{sub}[/]"

        def launches_body() -> str:
            if launches is None:
                return _NO_VALUE
            try:
                n24 = int(launches_24h or 0)
            except (TypeError, ValueError):
                n24 = 0
            color = "green" if n24 > 0 else "dim"
            return (
                f"[bold white]{fmt_int(launches)}[/]\n"
                f"[{color}]+{n24} 24h[/]"
            )

        def holders_body() -> str:
            if holder_pool_eth_total is None:
                return _NO_VALUE
            big = fmt_float(holder_pool_eth_total, ".3f")
            sub = fmt_float(holder_pool_eth_24h, ".4f")
            return f"[bold white]{big} Ξ[/]\n[dim]+{sub} Ξ 24h[/]"

        def mcap_body() -> str:
            # No ``None`` early return: this box reports "--" for a zero
            # market cap as well as an absent one, and still shows the
            # token count beneath it either way.
            try:
                usd_val = (
                    float(total_mcap_usd) if total_mcap_usd is not None
                    else None
                )
            except (TypeError, ValueError):
                usd_val = None

            if usd_val is None or usd_val == 0:
                big = "--"
            elif usd_val >= 1_000_000:
                big = f"${usd_val / 1e6:.2f}M"
            else:
                big = f"${usd_val / 1e3:.1f}K"

            try:
                token_count = (
                    int(total_mcap_token_count)
                    if total_mcap_token_count is not None else 0
                )
            except (TypeError, ValueError):
                token_count = 0

            if total_mcap_eth is None:
                sub = f"{token_count} tokens"
            else:
                try:
                    sub = f"{float(total_mcap_eth):,.1f} Ξ · {token_count} tokens"
                except (TypeError, ValueError):
                    sub = f"{token_count} tokens"

            return f"[bold white]{big}[/]\n[dim]{sub}[/]"

        self.render_box("#ttt-hero-unburned", "UNBURNED NFTs", unburned_body)
        self.render_box("#ttt-hero-launches", "TOKEN LAUNCHES", launches_body)
        self.render_box("#ttt-hero-holders", "HOLDER POOL", holders_body)
        self.render_box("#ttt-hero-mcap", "TOTAL MCAP", mcap_body)
