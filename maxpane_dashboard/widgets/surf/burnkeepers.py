"""BURNKEEPERS: who has called ``bridgeToBaseBurnReceiver()``, ranked by IMD
burned, with the fee each has paid so far.

**Read-only** (CLAUDE.md hard constraint 1 -- no signer, no transactor, no
calldata construction anywhere in this repo): this panel *displays* that
``bridgeToBaseBurnReceiver()`` is callable by anyone and what it has cost
each caller so far. It never offers to call it, never builds calldata, and
never quotes a fee for the purpose of sending. Same framing
``widgets/surf/launchpad.py``'s ``SurfBurnPipeline`` and ``hero.py``'s BURN
box already use for the same executor. ``BURN_EXECUTOR_V1`` is out of
scope -- it was drained 2026-08-20 -- this ranks calls to its v2
replacement.

Row shape: ``SURF_ROW_KEYS["launchpad_burnkeepers"]`` (Task 1, frozen) --
``wallet``, ``wallet_known``, ``imd_burned``, ``eth_paid``, ``burns``.
``imd_burned`` and ``burns`` are already the *summed* per-wallet totals
(``data/surf_client._rank_burnkeepers``, Task 10); this panel is a pure
renderer over rows it trusts are already ranked and does not re-aggregate
or re-sort them.

``eth_paid`` is the LayerZero fee actually paid to bridge-and-burn, never
the value of any transfer that rode along with the call -- a wallet that
sent 0.001 ETH alongside a burn of a few thousand IMD really paid a few
millionths of that in fee, and showing "0.001" here would answer a
different question than the column asks. ``None`` means the fee could not
be read for any of a wallet's burns and renders :data:`~._fmt.DASH`, never
a confident ``0.000000`` -- CLAUDE.md's "a failed read is None, never 0"
applies to a summed fee exactly as it does to a single one; the rest of the
row (``imd_burned``, ``burns``) is unaffected by an unread fee.

This panel lives in the launchpad's right rail beside ``SurfCurveFlow`` and
``SurfBurnPipeline`` (both plain ``Static``s), so it renders a fitted
``Static`` block too, not a ``DataTable``: a nine-gutter table does not fit
~34 rail columns.

``wallet`` is stripped of complete ``[...]``-shaped bracket runs (through
``widgets/markup_safety.strip_tags``) before it is windowed and escaped --
the same "strip the known-hostile shape, then escape whatever remains"
defense ``widgets/surf/launchpad.py``'s ticker/name cells use, and for the
same reason: an *escaped* ``[/x]`` still renders as the literal text
``[/x]`` once Rich unescapes it for display, which merely escaping does not
prevent. A real on-chain address never contains a bracket, so this only
ever fires on a malformed payload.

The panel builds one ``rich.text.Text`` per line via ``Text.from_markup``
inside its own ``try`` and joins the parsed ``Text`` objects with
``Text("\\n").join(...)`` before handing the result to ``Static.update()`` --
never a joined markup *string*. ``Static.update()`` defers
``Content.from_markup`` into the message pump, so a parse failure there
raises outside the screen's own ``try/except`` and takes the app down;
parsed here, the identical failure degrades to a skipped row instead
(``SurfFeed._row_text`` is the worked example this mirrors).

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.address import ICON_COLS, address_text, is_address
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.rowfit import Ladder, WIDEN_HINT
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_imd

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "MAX_ROWS",
    "SurfBurnkeepers",
    "TITLE",
    "UNAVAILABLE_LINE",
    "WIDEN_HINT",
]

TITLE = "BURNKEEPERS"
UNAVAILABLE_LINE = "burnkeepers unavailable"
EMPTY_LINE = "no burns yet"
# ``WIDEN_HINT`` (in ``__all__``) is the repo-wide marker, shared in
# ``widgets/rowfit.py`` since Branch 3.

#: Rows drawn. Four wallets exist today; the rail has room for a few more
#: before it would have to scroll.
MAX_ROWS = 8

#: `0x047F…54B7` -- the coin table's own window, through
#: ``widgets/address.short_address``. Already ``MIN_SHORT_COLS``.
_WALLET_WINDOW_COLS = 11
#: The wallet cell as painted: the window plus its copy icon. **Grown, not
#: shortened** (2026-09-14, ``docs/address_copy_PRD.md`` §5): this panel's
#: text budget is 41 at ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` (138) against
#: a full row of 34, so the icon came out of slack and moved no pin.
_WALLET_COLS = _WALLET_WINDOW_COLS + ICON_COLS                      # 13
_IMD_COLS = 8        # `fmt_imd`: "15.7K", "29.98", "0.00"
_ETH_COLS = 8        # "0.000028"
_BURNS_COLS = 2
_GAP = 1

FULL_WIDTH = (
    _WALLET_COLS + _GAP + _IMD_COLS + _GAP + _ETH_COLS + _GAP + _BURNS_COLS
)                                                                    # 34
#: One tier below full: the burn COUNT goes, because it is the only cell
#: whose absence costs a reader the least -- the ranking key and the cost
#: both stay. Shedding a column is this repo's answer to a value that does
#: not fit; widening the rail's seam is not.
COMPACT_WIDTH = FULL_WIDTH - _GAP - _BURNS_COLS                      # 31


def _wallet_cell(value: object, known: bool) -> Text:
    """The wallet cell, padded to :data:`_WALLET_COLS` for column alignment,
    styled cyan when ``known`` and dim otherwise -- never a friendly label
    (this row shape carries no label field).

    A valid address is the 11-cell window plus its copy icon
    (``widgets/address.address_text``), and the icon copies the whole
    address. Anything else gets no icon and is fitted to the cell on cells
    (the helper's own fit, with a visible ``…``). Built as ``Text``, never
    markup: nothing here is parsed, so there is nothing to escape.
    """
    colour = "cyan" if known else "dim"
    s = strip_tags(value)
    if is_address(s):
        cell = address_text(s, width=_WALLET_WINDOW_COLS, style=colour)
    else:
        cell = address_text(s or DASH, width=_WALLET_COLS, style=colour)
    cell.append(" " * max(_WALLET_COLS - cell.cell_len, 0))
    return cell


def _eth_cell(value: object) -> str:
    """The LayerZero fee actually paid; :data:`DASH` when unread, never a
    confident ``0.000000``.
    """
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) < 1:
        return f"{v:.6f}"
    return f"{v:,.3f}"


#: ``_tier_for``: ``full`` at or above :data:`FULL_WIDTH`; ``compact`` (burn
#: count shed) below it.
#: (:class:`~maxpane_dashboard.widgets.rowfit.Ladder`: the last step is the fallback and its
#: threshold is not consulted, so it is written ``0``.)
_LADDER = Ladder(("full", FULL_WIDTH), ("compact", 0))
_tier_for = _LADDER.tier_for


def _row_fields(
    row: object,
) -> tuple[object, bool, object, object, object] | None:
    """Decompose one row into its raw cells; ``None`` drops it."""
    if not isinstance(row, dict):
        return None
    try:
        wallet_raw = row.get("wallet")
        known = bool(row.get("wallet_known"))
        imd = row.get("imd_burned")
        eth = row.get("eth_paid")
        burns = row.get("burns")
        return wallet_raw, known, imd, eth, burns
    except Exception:
        return None


def _row_text(row: object, tier: str) -> Text | None:
    """Format one burnkeeper row at ``tier``; ``None`` drops it.

    Every cell here is fixed-width (a windowed address plus its icon, a
    compact numeric cell, a bare digit count), so -- exactly as
    ``launchpad_activity._row_text`` notes for its own row -- there is no
    per-row negotiation once the tier has picked which whole fields appear.

    Built as ``Text`` from the first cell on, never as a markup string: the
    wallet cell carries the copy icon's click action, and the numeric cells
    are this module's own formatting, so nothing on the row is ever parsed
    and no ``Static.update()`` can raise on it inside the message pump
    (``SurfFeed._row_text``'s concern, answered without a parse at all).
    """
    fields = _row_fields(row)
    if fields is None:
        return None
    try:
        wallet_raw, known, imd, eth, burns = fields
        cells = [
            f"{fmt_imd(imd):>{_IMD_COLS}}",
            f"{_eth_cell(eth):>{_ETH_COLS}}",
        ]
        if tier == "full":
            try:
                burns_str = str(int(burns))
            except (TypeError, ValueError):
                burns_str = DASH
            cells.append(f"{burns_str:>{_BURNS_COLS}}")
        line = _wallet_cell(wallet_raw, known)
        line.append(" " * _GAP + (" " * _GAP).join(cells))
        return line
    except Exception:
        # A single malformed row must never take down the panel.
        return None


class SurfBurnkeepers(Vertical):
    """Ranked leaderboard of wallets that have called
    ``bridgeToBaseBurnReceiver()`` -- most IMD burned first, with the fee
    each has paid so far.

    Read-only (CLAUDE.md hard constraint 1): see the module docstring.
    """

    DEFAULT_CSS = """
    SurfBurnkeepers {
        height: auto;
    }
    SurfBurnkeepers > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    #: ``SurfBurnkeepers > Static``'s own ``padding: 0 1`` (``DEFAULT_CSS``
    #: above) eats one column on each side of the *child* ``Static``'s
    #: content box, so the text budget a fit decision must compare against
    #: is ``self.size.width`` (this container's own width) minus these two
    #: columns, never ``self.size.width`` itself. This is the identical
    #: mistake ``SurfLaunchpadCoins`` (``widgets/surf/launchpad.py``) made
    #: and was fixed for earlier this session, as its own
    #: ``_TITLE_PADDING_COLS`` records: comparing a fit candidate against
    #: the unpadded container width can accept a tier that is too wide for
    #: the padded box and hand the overflow to CSS ``text-overflow:
    #: ellipsis``, which eats real content in silence -- the exact
    #: silent-clipping shape this repo's layout rules forbid, reproduced
    #: here with a leaderboard row instead of a coin-table title.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw rows, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(TITLE, id="surf-bk-body")

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the layout depends on the width."""
        if self._payload:
            self._render_view()

    def update_data(
        self, launchpad_burnkeepers=None, as_of_hhmm=None, **_kwargs
    ) -> None:
        """Refresh the panel.

        ``launchpad_burnkeepers`` is spelled exactly as the PRD §5 contract
        key it carries, so this panel lands in
        ``tests/widgets/test_surf_widget_contract.py``'s strict kwarg check
        by default rather than in its ``_SHORT_KWARG_WIDGETS`` escape list
        -- which is what that list's own docstring asks of a new widget, and
        the opposite of how the ``l`` view's first three panels (``coins``,
        ``burned_total``, ...) escaped every check in that file. It was
        ``burnkeepers`` for one wave; the screen never called it under that
        name.

        ``as_of_hhmm`` is accepted (the launchpad's own slower-tier clock,
        ``launchpad_as_of_hhmm`` in the contract) but this panel has no note
        line to put it in yet, so it is currently unused -- accepted rather
        than raising, the same contract ``SurfBurnPipeline.update_data``
        documents for its own un-rewired callers.
        """
        self._payload = {"rows": launchpad_burnkeepers, "seen": True}
        self._render_view()

    def _text_budget(self) -> int:
        """Real rendered columns available inside the child ``Static``'s
        own padded content box.

        ``self.size.width`` is this *container*'s width; the ``padding: 0
        1`` that actually eats columns lives on the child ``Static``
        (``DEFAULT_CSS`` above), not on this ``Vertical`` itself, so a fit
        decision that compares against ``self.size.width`` directly is
        comparing against two columns more room than a row really has.
        ``_title_text`` (the marker) and ``_render_view`` (the row's own
        tier) both fit against this single number, so the marker can never
        promise a room the row underneath does not actually get, and vice
        versa -- the two disagreeing is exactly how a row ended up
        silently ellipsised by CSS while the title stayed unmarked.
        """
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``BURNKEEPERS  ‹ widen``, width permitting -- appended, never
        substituted, so ``TITLE in text`` holds at every width
        (``SurfLaunchpadCoins._set_title``'s pattern: fit against the real
        text budget, never the raw container width).

        Compares :meth:`_text_budget`, not ``self.size.width`` itself --
        this container's own ``padding: 0 1`` claim used to say the
        padding was "already inside ``self.size``", which was false: the
        padding lives on the child ``Static``, not on this widget, so
        comparing the raw width let the marker stay dark for two columns'
        worth of widths where a row was already being silently truncated
        by CSS ``text-overflow: ellipsis`` -- the exact silent-clipping
        failure this repo's layout rules exist to prevent.
        """
        width = self.size.width
        if width and self._text_budget() < FULL_WIDTH:
            return f"{TITLE}  {WIDEN_HINT}"
        return TITLE

    def _render_view(self) -> None:
        try:
            body = self.query_one("#surf-bk-body", Static)
        except Exception:  # not composed yet
            return

        title = Text(self._title_text(), style="dim")
        if not self._payload:
            # Geometry may still be worth showing before the first
            # `update_data`, but there is nothing else to render yet.
            body.update(title)
            return

        lines = [title, Text("")]
        rows_payload = self._payload.get("rows")

        if rows_payload is None:
            lines.append(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))
            body.update(Text("\n").join(lines))
            return

        try:
            rows = list(rows_payload)[:MAX_ROWS]
        except TypeError:
            rows = []

        if not rows:
            lines.append(Text(EMPTY_LINE, style="dim"))
            body.update(Text("\n").join(lines))
            return

        # The real text budget, not `self.size.width` -- see `_text_budget`.
        # Deciding the tier against the unpadded container width is the
        # other half of the same bug `_title_text` fixes: even with the
        # marker now lit correctly, a tier decision still made against the
        # wrong number would keep asking for a row two columns too wide for
        # the padded box and hand the overflow to CSS to clip in silence.
        tier = _tier_for(self._text_budget())
        rendered = [
            t for t in (_row_text(row, tier) for row in rows) if t is not None
        ]
        if not rendered:
            # Every row was malformed: nothing was shed by width, so this is
            # a content state, not a "no room" one -- say so plainly rather
            # than leave a title with nothing under it.
            lines.append(Text(EMPTY_LINE, style="dim"))
        else:
            lines.extend(rendered)
        body.update(Text("\n").join(lines))
