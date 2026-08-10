"""IDENTITY.MD panel: holders, velocity, identities, honest floor, last sales.

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

Width behaviour
---------------

The rows are ``Static``\\ s at ``text-wrap: nowrap; text-overflow: ellipsis``,
so an over-long row is cut with a visible ``…``.  That is half the house
contract; the other half -- a word in the *title* naming what went -- this
panel had no machinery for at all, because it did not need any: until
2026-08-10 it was the sole child of ``#bottom-row`` at ``width: 1fr``, i.e.
the whole terminal.  The three-row restructure put ``SurfMarket`` beside it
and made it ``2fr`` of a 3:2 split, so it now sees roughly ``0.4 * terminal
- 4`` columns against the 46 its stats row needs, and at 122 columns and
below it ellipsised ``dev holds 3`` -- and at 90, ``38 transfers/24…``,
which is a number wearing a different unit.

So the stats row now sheds whole labelled fields (see :func:`_tier_for`) and
the title names them.  Only *that* row has fields to trade: ``identities
N/2000 written`` and the floor line are single statements, and the sales
block is already the narrowest thing here.  When one of those is what
overflows -- the floor line's ``n/a — no keyless source`` is 31 columns and
is the binding row once the stats row has reached its narrowest tier --
there is no field to name, and :data:`SHORT_HINT` carries the bare marker.

The order of sacrifice is the reverse of the PRD's ordering of the figures:
``dev holds`` (a dev-behaviour detail) goes first, ``transfers/24h`` (the
velocity signal) second, and the holder count is the last thing standing.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, mmdd

#: Panel title.  The collection calls itself identity.md, which is what the
#: NFT *is* -- an onchain identity record -- so the panel says that rather
#: than the ticker.  Deliberately *not* imported by the tests that assert
#: it: they spell the string out, so a rename reddens them and has to be
#: made on purpose.  A test comparing this constant against itself would
#: pass through any rename at all.
PANEL_TITLE = "IDENTITY.MD"

#: The explicit floor state.  Tested verbatim (PRD §5 nft group).
FLOOR_UNAVAILABLE = "n/a — no keyless source"

#: Sales lines rendered at most.
_MAX_SALES = 4

#: Marker appended to the title when the stats row had to shed a field, one
#: per tier, naming what went.  They are terse for a measured reason: the
#: hint has to fit beside an 11-column title inside a panel that is *at most*
#: as wide as the tier that triggered it, which leaves 18 columns at the
#: ``minimal`` tier (31 usable, minus ``IDENTITY.MD`` and two of gap).  A
#: longer ``minimal`` wording would be unreachable in every layout this
#: widget has -- dead string, permanently replaced by :data:`SHORT_HINT`.
#: ``compact`` has more room and spells the field out; below ~101 terminal
#: columns even that falls back.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for dev holdings",
    "minimal": "‹ widen: 24h, dev",
}

#: Fallback marker for a panel too narrow to carry a descriptive hint beside
#: its title, and for the case where the row that overflows is not the stats
#: row at all (the floor line is 31 columns and has no field to shed).  It
#: names nothing, which is a real loss -- but "columns were dropped here" is
#: the contract, and going silent is not an option this codebase allows.
SHORT_HINT = "‹ widen"


def _fmt_count(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return DASH


def _stats_variants(holders: str, transfers: str, dev: str) -> dict[str, str]:
    """Plain text of the stats row at each tier, widest first.

    Plain, not markup: this is what :func:`_tier_for` measures, and
    ``len()`` of a markup string counts the tags.  Every character here is
    one cell wide (digits, ASCII and ``·``), so ``len`` is the rendered
    width.  ``_stats_markup`` below must render exactly these strings --
    pinned by ``test_nft_stats_budget_matches_what_the_markup_actually_renders``,
    because a budget that disagrees with the render picks a tier by one
    width and paints another, i.e. clips with the marker dark.
    """
    return {
        "full": f"  {holders} holders · {transfers} transfers/24h · dev holds {dev}",
        "compact": f"  {holders} holders · {transfers} transfers/24h",
        "minimal": f"  {holders} holders",
    }


def _stats_markup(tier: str, holders: str, transfers: str, dev: str) -> str:
    """The same three rows, styled."""
    if tier == "minimal":
        return f"  [bold]{holders}[/] [dim]holders[/]"
    if tier == "compact":
        return (
            f"  [bold]{holders}[/] [dim]holders ·[/] "
            f"[bold]{transfers}[/] [dim]transfers/24h[/]"
        )
    return (
        f"  [bold]{holders}[/] [dim]holders ·[/] "
        f"[bold]{transfers}[/] [dim]transfers/24h ·[/] "
        f"[dim]dev holds[/] [bold]{dev}[/]"
    )


def _tier_for(width: int, variants: dict[str, str]) -> str:
    """Widest stats row that fits ``width`` rendered columns.

    ==========  ===================================================
    Tier        Row
    ==========  ===================================================
    ``full``    ``667 holders · 38 transfers/24h · dev holds 3``
    ``compact`` ``667 holders · 38 transfers/24h``
    ``minimal`` ``667 holders``
    ==========  ===================================================

    Measured against the *rendered* strings rather than pinned constants:
    the counts are comma-grouped, so a collection an order of magnitude
    larger moves every threshold and a hardcoded 46 would silently stop
    being the truth.

    ``width <= 0`` means "not laid out yet" and optimistically picks
    ``full``; :meth:`SurfNft.on_resize` re-lays it out once it has a size.
    Nothing narrower than ``minimal`` exists -- a panel that cannot fit the
    holder count is advertised through :data:`SHORT_HINT` instead.
    """
    if width <= 0:
        return "full"
    for tier in ("full", "compact", "minimal"):
        if len(variants[tier]) <= width:
            return tier
    return "minimal"


def _sale_line(sale) -> tuple[str, str] | None:
    """``(plain, markup)`` for one sale, or ``None`` for a malformed row.

    The plain half exists so the panel can tell whether the sales block is
    what overflows -- a token id long enough to push the row past the stats
    row is unlikely but not impossible, and an unadvertised cut is the one
    outcome that is not allowed.
    """
    if not isinstance(sale, dict):
        return None
    try:
        token = int(sale["token_id"])
        eth = float(sale["eth"])
    except (KeyError, TypeError, ValueError):
        return None
    stamp = mmdd(sale.get("ts"))
    return (
        f"  {stamp}  #{token}  {eth:.3f} ETH",
        f"  [dim]{stamp}[/]  #{token}  [bold]{eth:.3f} ETH[/]",
    )


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: The last payload, not the formatted rows, so a resize can re-lay
        #: them out at the new width.  Empty until the first ``update_data``
        #: -- ``on_resize`` before that has nothing to render and must not
        #: blank the panel.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(PANEL_TITLE, classes="surf-nft-title", id="surf-nft-title")
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
        self._payload = {
            "nft_holders": nft_holders,
            "nft_transfers_24h": nft_transfers_24h,
            "nft_dev_holdings": nft_dev_holdings,
            "nft_written": nft_written,
            "nft_last_sales": nft_last_sales,
            "nft_floor": nft_floor,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the stats tier depends on the width.

        The row is formatted once per refresh against the width it was
        formatted at, and nothing else re-renders it, so without this hook a
        widened or narrowed terminal would show the previous size's tier --
        padded, or ellipsised by ``text-overflow`` with the title still
        claiming nothing was shed -- until the next 30-second poll.
        """
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _line_width(self) -> int:
        """Rendered columns one row of this panel can show.

        Every row (and the title) is a ``width: 100%`` ``Static`` at
        ``padding: 0 1`` inside this widget's own content box, so they all
        have the same usable width and one number answers for the lot.
        """
        return max(self.content_size.width - 2, 0)

    def _set_title(self, hint: str = "") -> None:
        """``IDENTITY.MD  ‹ widen for dev holdings``, width permitting.

        The hint is *appended*: the title itself never changes, so the screen
        tests' ``"IDENTITY.MD" in text`` holds at every width.  It degrades to
        :data:`SHORT_HINT` rather than to nothing when the descriptive wording
        will not fit beside the title -- silence is what the tiers exist to
        prevent -- and only a panel too narrow for even that goes unmarked,
        because this ``Static`` has no ``text-overflow`` and an over-long
        title wraps onto a second line, pushing a sales row out of a panel
        whose row is ``height: auto``.
        """
        title = self.query_one("#surf-nft-title", Static)
        width = self._line_width()
        text = PANEL_TITLE
        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or len(PANEL_TITLE) + 2 + len(candidate) <= width:
                    text += f"  [yellow]{candidate}[/]"
                    break
        title.update(text)

    def _render_view(self) -> None:
        try:
            stats = self.query_one("#surf-nft-stats", Static)
            written_row = self.query_one("#surf-nft-written", Static)
            floor_row = self.query_one("#surf-nft-floor", Static)
            sales_head = self.query_one("#surf-nft-sales-head", Static)
            sales_body = self.query_one("#surf-nft-sales", Static)
        except Exception:  # not composed yet
            return

        payload = self._payload
        width = self._line_width()

        # -- the one row with fields to trade ---------------------------
        variants = _stats_variants(
            _fmt_count(payload.get("nft_holders")),
            _fmt_count(payload.get("nft_transfers_24h")),
            _fmt_count(payload.get("nft_dev_holdings")),
        )
        tier = _tier_for(width, variants)
        stats.update(
            _stats_markup(
                tier,
                _fmt_count(payload.get("nft_holders")),
                _fmt_count(payload.get("nft_transfers_24h")),
                _fmt_count(payload.get("nft_dev_holdings")),
            )
        )
        # Every row's rendered width, so a marker can be lit for a line the
        # tiers cannot help -- the floor line above all, at 31 columns.
        widths = [len(variants[tier])]

        written = _fmt_count(payload.get("nft_written"))
        widths.append(len(f"  identities {written}/2000 written"))
        written_row.update(
            f"  [dim]identities[/] [bold]{written}[/][dim]/2000 written[/]"
            if written != DASH
            else f"  [dim]identities {DASH}/2000 written[/]"
        )

        floor = as_float(payload.get("nft_floor"))
        if floor is None:
            floor_row.update(f"  [dim]floor[/] [yellow]{FLOOR_UNAVAILABLE}[/]")
            widths.append(len(f"  floor {FLOOR_UNAVAILABLE}"))
        else:
            floor_row.update(f"  [dim]floor[/] [bold]{floor:.3f} ETH[/]")
            widths.append(len(f"  floor {floor:.3f} ETH"))

        nft_last_sales = payload.get("nft_last_sales")
        if nft_last_sales is None:
            sales_head.update("  [dim]last sales[/]")
            sales_body.update("  [yellow]⚠ sales unavailable[/]")
            widths += [len("  last sales"), len("  ⚠ sales unavailable")]
        else:
            try:
                rows = list(nft_last_sales)[:_MAX_SALES]
            except TypeError:
                rows = []
            lines = [l for l in (_sale_line(s) for s in rows) if l is not None]
            sales_head.update("  [dim]last sales (Seaport)[/]")
            widths.append(len("  last sales (Seaport)"))
            if lines:
                sales_body.update("\n".join(markup for _plain, markup in lines))
                widths += [len(plain) for plain, _markup in lines]
            else:
                sales_body.update("  [dim]no sales in window[/]")
                widths.append(len("  no sales in window"))

        # ``WIDEN_HINTS`` names the fields the stats row shed; the bare
        # marker covers a row that overflowed with no field to shed.
        hint = WIDEN_HINTS.get(tier, "")
        if not hint and width and max(widths) > width:
            hint = SHORT_HINT
        self._set_title(hint)
