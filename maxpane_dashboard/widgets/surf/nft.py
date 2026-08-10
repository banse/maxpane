"""IDENTITY.MD panel: holders, velocity, identities, honest floor, last sales.

Rows: title · stats · dev holdings · floor · last-sales block.

The stats row carries the three *collection* figures -- ``holders``,
``transfers/24h`` and the ``N/2000 written`` count -- and the dev's own
holdings get a row of their own, phrased as the sentence it is: ``dev holds
3 identities``.  It used to be the other way round (``dev holds 3`` was the
tail of the stats row and the written count was a row reading ``identities
1/2000 written``), which put the one figure that is about a *person* inside
a row of figures about the *collection*, and spent a whole row on a count
that is a single fraction.

**The floor line is the honesty flagship.**  There is no keyless floor
source for IDMD (OpenSea is keyed/Cloudflare-gated -- game_mechanics
§recipes), so PRD §5 pins ``nft_floor`` to ``None`` in v1 and this widget
renders the explicit ``n/a — no keyless source`` state.  It is never
faked, never ``0``, never silently blank.  If a future version ships a
real source and hands us a float, it renders with units -- the escape
hatch costs nothing today.

That absent state renders **muted**, at the same ``[dim]`` the panel's own
labels use.  It was ``[yellow]`` -- warning vocabulary -- for a condition
that cannot change: no keyless floor source exists for this collection at
all, so the line is a permanent statement rather than an alert about
something wrong *now*, and a colour that shouts on a standing fact is a
colour the eye is trained to skip.  Muting it is not hiding it: ``[dim]``
composites at 4.65:1 or better against the background in all ten registered
themes, pinned per theme by
``test_nft_muted_floor_is_still_legible_in_every_theme``.  The *real* floor
branch keeps its ``[bold]`` -- a number is news, a permanent absence is not.

There is no de-emphasis token to reach for instead: ``[$text-muted]`` in
inline markup does **not** resolve to the muted colour the same name gives
in CSS -- it composites at ``#ffffff``, i.e. brighter than the row it is
meant to recede behind (the alpha the token carries is dropped on the way
through markup).  ``[dim]`` is the inline idiom in this package for exactly
that reason.

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
- 4`` columns against the 49 its stats row needs (46 while the row ended in
``dev holds 3``), and at 122 columns and below it ellipsised that tail --
and at 90, ``38 transfers/24…``, which is a number wearing a different unit.

So the stats row now sheds whole labelled fields (see :func:`_tier_for`) and
the title names them.  Only *that* row has fields to trade: ``dev holds N
identities`` and the floor line are single statements, and the sales block
is already the narrowest thing here.  When one of those is what overflows --
the floor line's ``n/a — no keyless source`` is 31 columns and is the
binding row once the stats row has reached its narrowest tier -- there is no
field to name, and :data:`SHORT_HINT` carries the bare marker.

**The ladder was re-derived when the rows were rearranged, not re-pointed.**
It used to shed ``dev holds`` first and that field has left the stats row
entirely, so every tier below ``full`` measured a string the row no longer
renders -- the failure mode this module keeps warning about, a budget taken
on one string and a paint of another.  The order of sacrifice is now:

1. ``N/2000 written`` -- **the only figure on the row that is also on the
   screen somewhere else.**  ``SurfHero``'s IDENTITY GATE box renders
   ``N/2000 written`` from ``identities_written``, which the manager
   publishes from the same lifetime count as ``nft_written``
   (``surf_manager._nft_payload``).  Shedding it here costs the *dashboard*
   nothing; shedding either of the other two would take the figure off the
   screen outright.  It is also the slowest thing on the row -- 1 of 2000
   since deploy -- so it is the field least likely to have moved since the
   reader last looked at it, and it frees 17 of the 36 columns between the
   widest and narrowest tiers.
2. ``transfers/24h`` -- the velocity signal, and unique to this panel.
3. the holder count, which is the last thing standing.
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
#: ``compact`` has 35 to play with and spells the field out; below a panel of
#: 38 usable columns even that falls back.
#:
#: Both name their fields with text the shed row renders **verbatim** --
#: ``/2000`` out of ``1/2000 written``, ``24h`` out of ``transfers/24h`` --
#: so a hint cannot drift into naming a field that is still on screen (which
#: is what the previous ``dev``-shaped pair became the moment the dev
#: holdings moved to a row of their own).  Pinned by
#: ``test_nft_every_widen_hint_names_text_the_tier_actually_dropped``.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for /2000 written",
    "minimal": "‹ widen: 24h /2000",
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


def _stats_variants(holders: str, transfers: str, written: str) -> dict[str, str]:
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
        "full": (
            f"  {holders} holders · {transfers} transfers/24h "
            f"· {written}/2000 written"
        ),
        "compact": f"  {holders} holders · {transfers} transfers/24h",
        "minimal": f"  {holders} holders",
    }


def _stats_markup(tier: str, holders: str, transfers: str, written: str) -> str:
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
        f"[bold]{written}[/][dim]/2000 written[/]"
    )


def _dev_row(dev: str) -> tuple[str, str]:
    """``(plain, markup)`` for the dev-holdings row.

    Its own row, and a sentence rather than a figure: ``dev holds 3
    identities`` is a statement about a person, which is why it no longer
    rides the row of collection-wide counters.  A ``--`` mutes whole,
    following the ``written`` row it replaced -- ``dev holds 0 identities``
    would be a claim about the dev's wallet that no read was able to make.
    """
    plain = f"  dev holds {dev} identities"
    if dev == DASH:
        return plain, f"  [dim]dev holds {DASH} identities[/]"
    return plain, f"  [dim]dev holds[/] [bold]{dev}[/] [dim]identities[/]"


def _tier_for(width: int, variants: dict[str, str]) -> str:
    """Widest stats row that fits ``width`` rendered columns.

    ==========  =========================================================
    Tier        Row
    ==========  =========================================================
    ``full``    ``667 holders · 38 transfers/24h · 1/2000 written``
    ``compact`` ``667 holders · 38 transfers/24h``
    ``minimal`` ``667 holders``
    ==========  =========================================================

    Measured against the *rendered* strings rather than pinned constants:
    the counts are comma-grouped, so a collection an order of magnitude
    larger moves every threshold and a hardcoded 49 would silently stop
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
        # ``#surf-nft-dev``, not the ``#surf-nft-written`` this row used to be:
        # the written count moved onto the stats row and the dev holdings took
        # the row, so keeping the old id would leave a selector naming the one
        # field the row no longer carries.
        yield Static("", classes="surf-nft-line", id="surf-nft-dev")
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
            dev_row = self.query_one("#surf-nft-dev", Static)
            floor_row = self.query_one("#surf-nft-floor", Static)
            sales_head = self.query_one("#surf-nft-sales-head", Static)
            sales_body = self.query_one("#surf-nft-sales", Static)
        except Exception:  # not composed yet
            return

        payload = self._payload
        width = self._line_width()

        # -- the one row with fields to trade ---------------------------
        holders = _fmt_count(payload.get("nft_holders"))
        transfers = _fmt_count(payload.get("nft_transfers_24h"))
        written = _fmt_count(payload.get("nft_written"))
        variants = _stats_variants(holders, transfers, written)
        tier = _tier_for(width, variants)
        stats.update(_stats_markup(tier, holders, transfers, written))
        # Every row's rendered width, so a marker can be lit for a line the
        # tiers cannot help -- the floor line above all, at 31 columns.
        widths = [len(variants[tier])]

        dev_plain, dev_markup = _dev_row(_fmt_count(payload.get("nft_dev_holdings")))
        dev_row.update(dev_markup)
        widths.append(len(dev_plain))

        floor = as_float(payload.get("nft_floor"))
        if floor is None:
            # Muted, not warned: the absence is structural and permanent (see
            # the module docstring), so it recedes to the panel's own label
            # weight instead of wearing the ``[yellow]`` it used to.
            floor_row.update(f"  [dim]floor {FLOOR_UNAVAILABLE}[/]")
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
