"""Recent transactions of both dev wallets, poisoning-defended.

One line per tx, newest first -- composited at the full tier::

    08-07 06:26  dev  transfer   0x61CC704c…73f14E  0.310 ETH
    08-07 06:22  ops  lp         NFPM  33.250 ETH
    08-07 06:12  dev  bridge     OFT endpoint

(The amount is not a padded column: ``_AMOUNT_COLS`` is a budget reserve,
so the amount begins where its counterparty ends.  This example used to
show a 12-column wallet cell and an 8-column kind cell, neither of which
has been what the widget renders since 2026-08-10.)

``wallet_label`` is the producer's two-value vocabulary -- ``"dev"`` /
``"ops"``, from ``surf_client._DEV_WALLET_LABELS``, re-checked by the
manager against the address each label names.  It is deliberately *not* an
ENS name: the ENS spellings live in ``KNOWN_LABELS`` ("dev · surfsurf.eth"
/ "ops · frenpet.eth") and reach the user through the hero's ``owner ✓``
line.  This widget renders whatever string it is handed, so if the labels
should ever read as ENS names that is a change to the producer, not here.

Rendering rules (PRD §4, address-poisoning defense -- live spoofs of both
fee recipients exist in frenpet.eth's history today):

* ``counterparty_known`` truthy -> ``counterparty`` is a label from the
  vendored ``KNOWN_LABELS`` map, resolved upstream; rendered cyan.  The
  map itself lives in ``data/surf_addresses.py`` and is deliberately NOT
  imported here -- widgets receive primitives only.  ``LAUNCHPAD_HOOK``,
  ``LAUNCHPAD_FACTORY`` and ``BURN_EXECUTOR_V2`` joined that map for the
  v3->v4 migration (2026-08-23): LaunchpadHook was the dev's single most
  frequent counterparty and used to render as an anonymous truncated hex
  address purely because it was absent from the allowlist.  This module
  needed no change for the fix -- it already renders whatever
  ``counterparty``/``counterparty_known`` it is handed -- which is exactly
  why the allowlist, not a fallback or fuzzy match here, is the right place
  for that decision to live.
* unknown -> dimmed ``0x`` + first 8 + ``…`` + last 6, never styled as
  trusted.  The window is wide enough to distinguish the live spoof pair
  (``0xF3084Bc7…D60eE6`` vs ``0xF3083828…f60Ee6``), which the classic
  first-6/last-4 short form is not.  A launchpad-address lookalike absent
  from the allowlist falls through to this same window -- no fallback, no
  fuzzy match, no prefix match, ever (PRD §4).
* dust never renders: ``kind == "dust"`` rows are dropped outright, and a
  ``transfer`` at-or-below dust value (see ``_DUST_ETH`` below) from an
  unknown counterparty -- exactly the poisoning shape -- is dropped even
  if the manager's own filter missed it.  Defense in depth; the manager
  keys on tx sender (PRD §6.5), this widget keys on the rendered row.
  The threshold is a *value* check, not a zero check: the real captured
  poisoning rows carry 1 gwei (``1_000_000_000`` wei), not 0 wei, and a
  bare falsiness test (``not value``) lets that exact shape through.

``dev_activity=None`` -> explicit unavailable state; ``[]`` -> genuinely
quiet wallets.  Primitives only.

Width behaviour
---------------

``RichLog`` is composed ``wrap=False`` so the columns stay aligned down the
panel, and ``RichLog.write()`` defaults to ``shrink=True``: any line wider
than ``scrollable_content_region.width`` is narrowed *at write time*, with
no ``…``, no marker and nothing in the title.  ``wrap=False`` and a width
tier are therefore a package deal -- choosing the first without the second
is what let this panel drop the ETH amount at 100 columns and cut the
address window to ``0xF308`` at 80, silently, in both cases.

The panel lives in the screen's right rail under ``SurfSignals`` (it shared
the announce feed's slot behind a ``c`` swap until 2026-08-10), so it sees
roughly ``0.4 * terminal - 5`` columns and legitimately selects a narrower
tier than it used to at the same terminal width.  Every tier says what it
shed; :data:`SHORT_HINT` covers the widths too narrow to say it in words.

The row sheds whole fields as the width drops (see :func:`_tier_for`) and
the title names the ones that went.  The order is fixed (:func:`_budget`):
the ``HH:MM`` half of the stamp, the amount, the kind, the wallet cell, and
last the ``MM-DD`` date, which these rows need because they span months.
Each goes *whole* -- a cell cut to ``de`` or ``fwa clai`` is the same silent
defect one column to the left.

**One thing is never traded away: the unknown-counterparty window**
(``0x``+8+``…``+6, ``ADDR_COLS``).  Cut to the classic first-6/last-4 form
both live spoofs collide with their targets, which is the one failure this
panel exists to prevent, so every other field goes before a single hex digit
does -- and below :data:`FLOOR_WIDTH`, where there is no other field left,
the rows are withheld and :data:`SHORT_HINT` is written in their place
rather than cut to fit.
"""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf import _rowfit
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_imd,
    hhmm,
    long_addr,
    mmdd,
)

#: Max rows rendered per refresh.
_MAX_ROWS = 25

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "activity unavailable"

#: Panel title.  A hint is appended to it, never substituted for it, so the
#: screen tests' ``"DEV ACTIVITY" in text`` stays true at every width.
TITLE = "DEV ACTIVITY"

# -- the column budget, in rendered columns ----------------------------
#
# Measured from the format strings in :func:`_row_markup`, not rounded.
#
# Two of the cells hold a value from a *closed vocabulary the producer owns*
# (``data/surf_client.py``), and are sized to its widest member exactly.  A
# widget may not import from ``data/``, so those two numbers are literals
# here -- but a **test** may import both layers, and
# ``test_activity_cells_are_sized_from_the_producers_own_vocabularies``
# (tests/widgets/test_surf_widgets_b.py) asserts each cell against the real
# vocabulary in both directions.  That test is what makes a cell this tight
# safe: a producer that grows a longer label reddens there instead of
# reaching a user as a truncated cell.

#: ``MM-DD HH:MM`` and its narrow-tier ``MM-DD`` half.
_STAMP_COLS = 11
_STAMP_SHORT_COLS = 5

#: The gap between two cells.  Shared machinery: it lives in
#: ``widgets/surf/_rowfit.py`` and is re-exported here under the name this
#: module's own tests and docstrings have always used.
_GAP = _rowfit.GAP

#: ``wallet_label`` cell: the widest member of the producer's *whole*
#: vocabulary, ``surf_client._DEV_WALLET_LABELS`` == ``{"dev", "ops"}``, and
#: the ``DASH`` this cell falls back to.  Three columns, not a column more.
#:
#: It was **12** -- padded, the comment said, "so a longer label cannot
#: reflow the columns".  There is no longer label: the vocabulary is closed,
#: two members wide, and the manager re-checks each one against the address
#: it names.  Nine columns were therefore dead on every single row, and the
#: user saw them as a gulf between the wallet and the kind column.
_WALLET_COLS = 3

#: ``kind`` cell: the widest member of ``surf_client.DEV_TX_KINDS`` ==
#: ``{"deploy", "lp", "burn", "bridge", "fwa claim", "transfer", "other"}``,
#: i.e. ``len("fwa claim")``.
#:
#: It was **8**, one short, so ``fwa claim`` rendered ``fwa clai`` -- cut
#: mid-word, with no ``…`` and nothing in the title.  A silent cut is the
#: defect this module exists to prevent, so the cell fits its widest real
#: member and the row sheds whole fields instead (:func:`_budget`).
_KIND_COLS = 9

#: Widest amount cell these ETH values produce: ``"  33.250 ETH"``.
_AMOUNT_COLS = 12

#: The anti-poisoning window: ``0x`` + 8 hex + ``…`` + 6 (``_fmt.long_addr``).
#: **Never shrinks.**  See the module docstring.
ADDR_COLS = 17

#: Floor for a *known* counterparty label before it is cut with a visible
#: ``…``.  A label is descriptive text, unlike the window above.
_MIN_LABEL_COLS = 6

#: Columns each row layout needs.
FULL_WIDTH = (
    _STAMP_COLS + _GAP + _WALLET_COLS + _GAP + _KIND_COLS + _GAP
    + ADDR_COLS + _AMOUNT_COLS
)                                                                    # 58
COMPACT_WIDTH = FULL_WIDTH - _AMOUNT_COLS                            # 46
MINIMAL_WIDTH = _STAMP_SHORT_COLS + _GAP + _WALLET_COLS + _GAP + ADDR_COLS  # 29

#: Narrowest log a row can be *honestly* rendered in: the anti-poisoning
#: window alone, every other field already shed.  Below it the only way to
#: fit a row is to cut hex digits, which this panel never does, so the rows
#: are withheld and :data:`SHORT_HINT` is written in their place.
#:
#: This floor is why :func:`_row_cols` exists.  The budget used to charge the
#: row for *both* gaps whether or not the wallet cell was there, and never
#: re-checked the result, so a dropped wallet left ``MM-DD`` + gap + window ==
#: 24 columns going into a log the right rail had sized at 23 (``ceil(6W/13) -
#: 5`` at a 59-60 column terminal).  ``RichLog(wrap=False)`` narrowed it at
#: write time: ``0x61CC704c…73f14`` at 60 columns, ``0x61CC704c…7`` at 50 and
#: ``0x61CC7`` at 40 -- the last with the ``…`` gone too, so a truncated
#: address stopped looking truncated.  At a log width of 13 the live spoof
#: pair both render ``0xF308``, which is the one collision this panel exists
#: to prevent.
FLOOR_WIDTH = ADDR_COLS                                              # 17

#: Marker appended to the title when the layout had to shed a field.  Each
#: one names what went, so the user knows what they are not looking at.
#: ``DEV ACTIVITY`` + 2 + 24 == 38 columns for the longest of them, which the
#: panel's old ``3fr`` slot always had.  In the right rail it does not below
#: ~110 terminal columns, and :data:`SHORT_HINT` is the fallback there.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for amounts",
    "minimal": "‹ widen: time, kind, ETH",
}

#: Fallback marker for a panel too narrow to carry the descriptive hint beside
#: its title.  It names nothing, which is a real loss -- but "columns were
#: dropped here" is the contract, and going silent is not an option this
#: codebase allows.  Reachable since the panel moved into the screen's right
#: rail: at 80 terminal columns it is 30 wide against the 38 the minimal hint
#: needs, where the old ``3fr`` slot was never below 46.
SHORT_HINT = "‹ widen"


def _tier_for(width: int) -> str:
    """Widest row layout that fits ``width`` rendered columns.

    ==========  =====  ==================================================
    Tier        Needs  Row
    ==========  =====  ==================================================
    ``full``    58     ``MM-DD HH:MM  wallet  kind  who  0.310 ETH``
    ``compact`` 46     ``MM-DD HH:MM  wallet  kind  who``
    ``minimal`` 29     ``MM-DD  wallet  who``
    ==========  =====  ==================================================

    The real slot is the screen's right rail, 6fr of a 7:6 split minus this
    widget's padding, the log's padding and the log's permanent scrollbar
    gutter.  The feed takes ``floor(7W/13)`` and leaves the rail
    ``ceil(6W/13)``, so this widget has **``ceil(6W/13) - 5``** usable
    columns: 58 at 135, 61 at 142, 61 at 143 and 73 at 169.  ``ceil(6W/13) -
    5 >= FULL_WIDTH`` therefore first holds at ``W = 135``.  Measured on the
    real screen and pinned by
    ``test_the_activity_rail_reaches_full_width_well_below_the_pinned_width``;
    this note carried a ``0.46``-slope approximation of it until final review
    I-2 -- off by one everywhere that matters.

    That 135 used to be 152, and 152 was in turn the app's whole documented
    floor, because this panel was the widest thing on the screen: the row
    needed 66 columns, ``ceil(6W/13) - 5 >= 66`` first holds at 152, and the
    identity was load-bearing.  It is gone on purpose.  Sizing the wallet and
    kind cells to the producer's real vocabularies took the row 66 -> 58 (see
    the column budget above), so the panel now clears seven columns *below*
    ``SurfFeed``, which is the binding constraint again.  That reconciliation
    has since landed -- the surf screen documents 142 and the app 143, FWA's
    number -- but this module still deliberately quotes no floor of the app's:
    it is not this panel's to set any more, and it was the identity between
    the two that made the last one rot.

    The rail was ``2fr`` of a 3:2 split until the seam moved on 2026-08-10,
    i.e. ``ceil(2W/5) - 5``, where the same widths gave 53/56/63 and ``full``
    arrived only at 176; that 24-column gap is exactly what re-seaming to 7:6
    removed, and it is why this panel set ``FULL_LAYOUT_COLUMNS`` for as long
    as it did.  It no longer does.  It was a ``3fr`` slot of
    its own until 2026-08-10, where those same widths gave 80/96/101; the
    panel traded columns for being on screen at the same time as the announce
    feed instead of behind a ``c`` swap, and the narrower tier it now selects
    is advertised in the title like any other shed column.

    ``width <= 0`` means "not laid out yet" and optimistically picks
    ``full``; :meth:`SurfDevActivity.on_resize` re-lays it out once it has a
    size.
    """
    return _rowfit.tier_for(
        width,
        (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("minimal", 0)),
    )


def _row_cols(tier: str, stamp_cols: int, wallet_cols: int, who_cols: int,
              amount_cols: int) -> int:
    """Rendered width of a row made of exactly these cells.

    This panel's four cells, handed to the shared
    :func:`~widgets.surf._rowfit.row_cols` -- which is where the rule lives:
    **a cell of zero width is absent, and an absent cell takes its ``_GAP``
    with it.**  That is the arithmetic :func:`_budget` used to get wrong: it
    charged the row for both gaps unconditionally and never re-measured the
    result, so dropping the wallet cell neither freed the gap it had been
    charged for nor proved the row now fitted.  See :data:`FLOOR_WIDTH` for
    what that cost on screen.

    The amount carries its own two leading spaces (see :func:`_row_fields`),
    so it is passed as ``trailing`` and added rather than joined.
    """
    return _rowfit.row_cols(
        (
            stamp_cols,
            wallet_cols,
            _KIND_COLS if tier != "minimal" else 0,
            who_cols,
        ),
        amount_cols,
    )


def _budget(tier: str, width: int, stamp_cols: int, who: str, known: bool,
            amount_cols: int, wallet_cols: int = _WALLET_COLS,
            keep_stamp: bool = True) -> tuple[bool, int, str]:
    """Fit one row to ``width``; returns ``(keep_stamp, wallet_cols, who)``.

    This panel's cells, handed to the shared
    :func:`~widgets.surf._rowfit.budget`.  Order of sacrifice, after the tier
    has already dropped whole columns:

    1. a **known** label is cut with a visible ``…`` (down to
       ``_MIN_LABEL_COLS``) -- it is descriptive text;
    2. the **wallet** cell goes, whole.  It is three columns wide against a
       two-member vocabulary, so there is nothing in it to shrink: cut to two
       it renders ``de`` / ``op`` with no ``…``, which is the same silent-cut
       defect one cell to the left;
    3. the **``MM-DD`` date** goes, whole.  It outranks the ``HH:MM`` half
       (which the ``minimal`` tier already dropped) and both the cells above,
       but it does not outrank the window -- only widths below
       :data:`FLOOR_WIDTH` ever reach here, and there the alternative is
       cutting hex digits;
    4. the **unknown-counterparty window** is never touched at all.

    ``wallet_cols`` / ``keep_stamp`` are the *starting* plan, so a caller can
    fit every row of a batch to one shared layout -- see
    :meth:`SurfDevActivity._render_view`.  Passing a cell already dropped can
    only ever leave this function more room, never less, so a batch plan is a
    fixed point of it.

    ``width <= 0`` (not laid out yet) leaves everything at its natural size.
    """

    def needed(who_cols: int, wallet: int, stamp: bool) -> int:
        return _row_cols(tier, stamp_cols if stamp else 0, wallet,
                         who_cols, amount_cols)

    return _rowfit.budget(
        width, who, known, needed, wallet_cols, keep_stamp, _MIN_LABEL_COLS,
    )

#: Mirrors ``surf_client._DUST_WEI = 10**9`` (1 gwei), converted to the ETH
#: float unit this row's ``value_eth`` field carries -- ``value_eth`` is
#: whole ETH (e.g. ``33.25``), not wei, so the client's wei threshold has
#: to be divided by ``10**18`` (wei per ETH) to compare in the same unit;
#: getting that conversion wrong by that same factor would silently
#: disable the filter again. The client's own docstring calls the boundary
#: "at or below" dust, so the comparison here is inclusive (``<=``): the
#: real captured poisoning rows carry exactly ``1_000_000_000`` wei, i.e.
#: exactly this threshold, and a strict ``<`` would let that exact value
#: through untouched.
_DUST_ETH = 10**9 / 10**18  # == 1e-9 ETH == 1 gwei == surf_client._DUST_WEI


def _row_fields(row, tier: str) -> tuple[str, str, str, str, bool, str] | None:
    """Decompose one row into its cells; ``None`` drops it.

    ``None`` means the row is malformed or poisonous and must never reach a
    pixel -- a decision about *content*, taken before any decision about
    width, so the panel can tell "nothing to show" from "no room to show it"
    (:meth:`SurfDevActivity._render_view`).

    Returns ``(stamp, wallet_label, kind, who, known, amount)``, all raw and
    unescaped; the amount carries its own two leading spaces.
    """
    if not isinstance(row, dict):
        return None
    try:
        kind = str(row.get("kind") or "").strip().lower()
        if kind == "dust":
            return None
        known = bool(row.get("counterparty_known"))
        value = as_float(row.get("value_eth"))
        if kind == "transfer" and not known and (
            value is None or abs(value) <= _DUST_ETH
        ):
            # A transfer at or below dust value from an unknown
            # counterparty: the address-poisoning shape.  Testing exact
            # zero here (``not value``) missed the real attack, which
            # arrives as 1 gwei, not 0 wei.  Never rendered (PRD §4).
            return None

        ts = row.get("ts")
        stamp = mmdd(ts) if tier == "minimal" else f"{mmdd(ts)} {hhmm(ts)}"
        who = (
            str(row.get("counterparty") or DASH)
            if known
            else long_addr(row.get("counterparty"))
        )
        # A burn row reads in IMD, not in the fee it paid to send it: the ETH
        # on `bridgeToBaseBurnReceiver` is the LayerZero message cost, three
        # zeros beside a five-figure burn. Where the IMD is known it replaces
        # the ETH rather than joining it -- the cell has room for one amount
        # -- and where it is not, the row keeps exactly the cell it always had.
        burned = as_float(row.get("imd_burned"))
        if burned is not None and tier == "full":
            amount = f"  {fmt_imd(burned)} IMD"
        else:
            amount = f"  {value:,.3f} ETH" if (value and tier == "full") else ""
        return (
            stamp,
            str(row.get("wallet_label") or DASH),
            kind or DASH,
            who,
            known,
            amount,
        )
    except Exception:
        # A single malformed row must never take down the panel.
        return None


def _row_markup(row, tier: str = "full", width: int = 0,
                wallet_cols: int = _WALLET_COLS,
                keep_stamp: bool = True) -> str | None:
    """Format one activity row at ``tier``; ``None`` drops it.

    ``None`` means one of two things, and the caller must distinguish them:
    the row is malformed or poisonous (:func:`_row_fields`), or ``width`` is
    too narrow to render it without cutting the anti-poisoning window
    (below :data:`FLOOR_WIDTH`).  Rendering nothing in the second case would
    read as quiet wallets, so :meth:`SurfDevActivity._render_view` writes
    :data:`SHORT_HINT` instead.

    ``width`` is the real number of columns the log can show, and a markup
    string that is returned is **guaranteed to fit it**, so
    ``RichLog.write()`` never has to shrink -- and therefore never clips
    without a visible ``…``.  ``wallet_cols`` / ``keep_stamp`` pass in a
    layout shared by the whole batch (see :func:`_budget`).
    """
    fields = _row_fields(row, tier)
    if fields is None:
        return None
    try:
        stamp, label, kind, who, known, amount = fields
        keep_stamp, wallet_cols, who = _budget(
            tier, width, cell_len(stamp), who, known, cell_len(amount),
            wallet_cols, keep_stamp,
        )
        cols = _row_cols(
            tier, cell_len(stamp) if keep_stamp else 0, wallet_cols,
            cell_len(who), cell_len(amount),
        )
        if 0 < width < cols:
            # Every field that may be shed has been, and the row is still
            # too wide: what is left is the window, and the window never
            # shrinks.  Withheld rather than cut.
            return None

        # Pad raw, escape after -- padding an escaped string misaligns it.
        cells = []
        if keep_stamp:
            cells.append(stamp)
        if wallet_cols:
            cells.append(
                "[bold]"
                + safe_markup(
                    _rowfit.pad(_rowfit.clip(label, wallet_cols), wallet_cols)
                )
                + "[/]"
            )
        if tier != "minimal":
            cells.append(
                "[dim]"
                + safe_markup(
                    _rowfit.pad(_rowfit.clip(kind, _KIND_COLS), _KIND_COLS)
                )
                + "[/]"
            )
        colour = "cyan" if known else "dim"
        cells.append(f"[{colour}]{safe_markup(who)}[/]")
        return (" " * _GAP).join(cells) + amount
    except Exception:
        # A single malformed row must never take down the panel.
        return None


class SurfDevActivity(Vertical):
    """Feed of both dev wallets' recent transactions."""

    DEFAULT_CSS = """
    SurfDevActivity > .surf-activity-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfDevActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw rows, not formatted lines, so a resize re-lays them out.
        # Empty until the first ``update_data`` -- ``on_resize`` before that
        # has nothing to render and must not blank the panel.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(TITLE, classes="surf-activity-title", id="surf-act-title")
        yield Static(" ", classes="surf-activity-spacer")
        yield RichLog(
            id="surf-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(self, dev_activity=None, **_kwargs) -> None:
        """Rewrite the log.  ``dev_activity`` is the PRD §5 activity key."""
        self._payload = {"rows": dev_activity, "seen": True}
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the layout depends on the width.

        The rows are formatted at write time against the width they were
        written at, and nothing else re-renders them, so without this hook a
        widened or narrowed terminal would show the previous size's tier --
        padded, or silently shrunk by ``RichLog`` -- for the life of the
        screen.  It was written for a different reason (the panel used to be
        composed hidden behind a ``c`` swap, so its first ``update_data`` ran
        at zero width and picked the optimistic ``full`` tier); that reason is
        gone and this one is not.
        """
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _log_width(self, log: RichLog) -> int:
        """Rendered columns available to one line.

        ``scrollable_content_region``, not ``content_size``: ``RichLog``'s own
        ``DEFAULT_CSS`` sets ``overflow-y: scroll`` (always on, not ``auto``),
        so the gutter is reserved even for a two-line log and
        ``content_size.width`` overstates the usable width by one column --
        which is exactly the column ``write()`` shrinks away.  ``SurfFeed``
        carries the same measurement and the same note.
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _set_title(self, hint: str = "") -> bool:
        """``DEV ACTIVITY  ‹ widen for amounts``, width permitting.

        Returns whether the marker was placed, so the caller can say it
        somewhere else when it was not.

        The hint is *appended*: the title itself never changes, so the screen
        tests' ``"DEV ACTIVITY" in text`` holds at every width.  It degrades
        to :data:`SHORT_HINT` rather than to nothing when the descriptive
        wording will not fit beside the title, and a panel too narrow for even
        that gets no marker *here* -- this Static has no ``text-overflow``, so
        an over-long title wraps onto a second line and pushes a row out of
        the log instead of announcing anything.

        That last case is not an excuse to go silent, which is what this
        module exists to prevent.  It was accepted while the panel had a
        ``3fr`` slot that never got near it; the right rail reaches it at 46
        and 50 columns, where the log is 17-19 wide, the ``MM-DD`` date is
        shed and the title bar has 19-21 columns against the 21 the bare
        marker needs.  ``False`` sends the marker into the log instead
        (:meth:`_render_view`), which is where the withheld-rows state
        already puts it.
        """
        title = self.query_one("#surf-act-title", Static)
        width = max(self.content_size.width - 2, 0)
        text = TITLE
        placed = not hint
        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or (
                    cell_len(TITLE) + 2 + cell_len(candidate) <= width
                ):
                    text += f"  [yellow]{candidate}[/]"
                    placed = True
                    break
        title.update(text)
        return placed

    def _render_view(self) -> None:
        try:
            log = self.query_one("#surf-activity-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        dev_activity = self._payload.get("rows")
        if dev_activity is None:
            self._set_title()
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            rows = list(dev_activity)[:_MAX_ROWS]
        except TypeError:
            rows = []

        width = self._log_width(log)
        tier = _tier_for(width)

        # Which rows may be shown at all -- a content question, decided
        # before any width question so "nothing to show" stays distinct from
        # "no room to show it".
        showable = [f for f in (_row_fields(row, tier) for row in rows)
                    if f is not None]
        if not showable:
            # Nothing was shed, so nothing is advertised: a marker over "no
            # recent activity" would point at columns that do not exist.
            self._set_title("")
            log.write("[dim]  no recent activity[/]")
            return

        # One layout for the whole batch.  ``RichLog`` is composed
        # ``wrap=False`` so the cells line up down the panel, which only
        # holds if every row is fitted to the same plan -- budgeting each row
        # against its own counterparty put a 17-column window's row (wallet
        # cell dropped) directly above an ``NFPM`` row that could still
        # afford one, so the counterparty column moved between two adjacent
        # lines.  The most constrained row sets the layout for all of them.
        plans = [
            _budget(tier, width, cell_len(stamp), who, known,
                    cell_len(amount))
            for stamp, _label, _kind, who, known, amount in showable
        ]
        keep_stamp = all(plan[0] for plan in plans)
        wallet_cols = min(plan[1] for plan in plans)

        lines = [
            m
            for m in (
                _row_markup(row, tier, width, wallet_cols, keep_stamp)
                for row in rows
            )
            if m is not None
        ]
        if len(lines) < len(showable):
            # At least one row cannot be fitted without cutting its
            # counterparty window.  Rendering the rest would hide exactly the
            # rows this panel exists to show -- an unknown counterparty is
            # always the widest one -- so they all wait for width, and the
            # panel says so rather than reading as quiet wallets.
            self._set_title(WIDEN_HINTS.get(tier, "") or SHORT_HINT)
            log.write(f"[yellow]{SHORT_HINT}[/]")
            return

        hint = WIDEN_HINTS.get(tier, "")
        if not self._set_title(hint):
            # The title bar is too narrow to carry the marker. Say it in the
            # log rather than not at all -- one row is a far smaller loss
            # than a column that went unannounced.
            log.write(f"[yellow]{SHORT_HINT}[/]")
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
