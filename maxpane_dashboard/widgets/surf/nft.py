"""IDMD NFT panel: holders, velocity, identities, honest floor, last sales.

Rows: title · stats · written · floor · last-sales block.

**The floor line is the honesty flagship.**  There is no keyless floor
source for IDMD (OpenSea is keyed/Cloudflare-gated -- game_mechanics
§recipes), so PRD §5 pins ``nft_floor`` to ``None`` in v1 and this widget
renders the explicit ``n/a — no keyless source`` state.  It is never
faked, never ``0``, never silently blank.  If a future version ships a
real source and hands us a float, it renders with units -- the escape
hatch costs nothing today.

Realized Seaport sales (``nft_last_sales``) are the closest keyless proxy
and get their own block: ``MM-DD  #token  x.xxx ETH``.  Those prices come
from decoded ``OrderFulfilled`` logs, not from the ERC-721 transfer list --
a transfer row carries a token id and nothing about money, which is why
``nft_last_sales[].eth`` is the manager's job and not a field this widget
can synthesise when it is missing.  A sale row without a usable ``eth`` is
skipped, never rendered at ``0.000``.

``None`` scalars render ``--``; a dead Blockscout is not a collection
with zero holders.  Primitives only: every field this widget consumes is
numeric (counts, a timestamp, a token id, an ETH amount) -- there is no
collection name/symbol string in the PRD §5 ``nft`` key group, so unlike
``hero``/``feed``/``activity`` there is no third-party text here for
``safe_markup`` to guard.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, mmdd

#: The explicit floor state.  Tested verbatim (PRD §5 nft group).
FLOOR_UNAVAILABLE = "n/a — no keyless source"

#: Sales lines rendered at most.
_MAX_SALES = 4


def _fmt_count(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return DASH


def _sale_line(sale) -> str | None:
    """``08-08  #1821  0.219 ETH`` or ``None`` for a malformed row."""
    if not isinstance(sale, dict):
        return None
    try:
        token = int(sale["token_id"])
        eth = float(sale["eth"])
    except (KeyError, TypeError, ValueError):
        return None
    return f"  [dim]{mmdd(sale.get('ts'))}[/]  #{token}  [bold]{eth:.3f} ETH[/]"


class SurfNft(Vertical):
    """IDMD collection panel."""

    DEFAULT_CSS = """
    SurfNft > .surf-nft-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfNft > .surf-nft-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("IDMD NFT", classes="surf-nft-title")
        yield Static("", classes="surf-nft-line", id="surf-nft-spacer")
        yield Static("", classes="surf-nft-line", id="surf-nft-stats")
        yield Static("", classes="surf-nft-line", id="surf-nft-written")
        yield Static("", classes="surf-nft-line", id="surf-nft-floor")
        yield Static("", classes="surf-nft-line", id="surf-nft-sales-head")
        yield Static("", classes="surf-nft-line", id="surf-nft-sales")

    def update_data(
        self,
        nft_holders=None,
        nft_transfers_24h=None,
        nft_dev_holdings=None,
        nft_written=None,
        nft_last_sales=None,
        nft_floor=None,
        **_kwargs,
    ) -> None:
        """Refresh all rows.  Kwargs are exactly the PRD §5 nft keys."""
        self.query_one("#surf-nft-stats", Static).update(
            f"  [bold]{_fmt_count(nft_holders)}[/] [dim]holders ·[/] "
            f"[bold]{_fmt_count(nft_transfers_24h)}[/] [dim]transfers/24h ·[/] "
            f"[dim]dev holds[/] [bold]{_fmt_count(nft_dev_holdings)}[/]"
        )

        written = _fmt_count(nft_written)
        self.query_one("#surf-nft-written", Static).update(
            f"  [dim]identities[/] [bold]{written}[/][dim]/2000 written[/]"
            if written != DASH
            else f"  [dim]identities {DASH}/2000 written[/]"
        )

        floor = as_float(nft_floor)
        if floor is None:
            floor_markup = f"  [dim]floor[/] [yellow]{FLOOR_UNAVAILABLE}[/]"
        else:
            floor_markup = f"  [dim]floor[/] [bold]{floor:.3f} ETH[/]"
        self.query_one("#surf-nft-floor", Static).update(floor_markup)

        sales_head = self.query_one("#surf-nft-sales-head", Static)
        sales_body = self.query_one("#surf-nft-sales", Static)
        if nft_last_sales is None:
            sales_head.update("  [dim]last sales[/]")
            sales_body.update("  [yellow]⚠ sales unavailable[/]")
            return
        try:
            rows = list(nft_last_sales)[:_MAX_SALES]
        except TypeError:
            rows = []
        lines = [l for l in (_sale_line(s) for s in rows) if l is not None]
        sales_head.update("  [dim]last sales (Seaport)[/]")
        sales_body.update("\n".join(lines) if lines else "  [dim]no sales in window[/]")
