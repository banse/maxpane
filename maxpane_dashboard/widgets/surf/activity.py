"""Recent transactions of both dev wallets, poisoning-defended.

One line per tx, newest first::

    08-07 04:23  ops           lp        NFPM  33.250 ETH
    08-07 04:21  ops           bridge    OFT endpoint
    07-17 04:12  ops           transfer  0x61CC704c…73f14E  8.000 ETH

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
  imported here -- widgets receive primitives only.
* unknown -> dimmed ``0x`` + first 8 + ``…`` + last 6, never styled as
  trusted.  The window is wide enough to distinguish the live spoof pair
  (``0xF3084Bc7…D60eE6`` vs ``0xF3083828…f60Ee6``), which the classic
  first-6/last-4 short form is not.
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
the title names the ones that went.  Two things are never traded away:

* **the unknown-counterparty window** (``0x``+8+``…``+6, ``ADDR_COLS``).
  Cut to the classic first-6/last-4 form both live spoofs collide with
  their targets, which is the one failure this panel exists to prevent, so
  the *wallet* column shrinks and then goes whole before a single hex digit
  is cut (:func:`_budget`).
* **the ``MM-DD`` date**, because these rows span months -- the ``HH:MM``
  half is what goes at the narrowest tier.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
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

#: The gap between two cells.
_GAP = 2

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
    ``SurfFeed``, which is the binding constraint again.  Reconciling the
    documented floor with that is a step of its own; this module deliberately
    quotes no floor of the app's.

    The rail was ``2fr`` of a 3:2 split until the seam moved on 2026-08-10,
    i.e. ``ceil(2W/5) - 5``, where the same widths gave 53/56/63 and ``full``
    arrived only at 176; that 24-column gap is exactly what re-seaming to 7:6
    removed, and it is why this panel is the one that sets
    ``FULL_LAYOUT_COLUMNS``.  It was a ``3fr`` slot of
    its own until 2026-08-10, where those same widths gave 80/96/101; the
    panel traded columns for being on screen at the same time as the announce
    feed instead of behind a ``c`` swap, and the narrower tier it now selects
    is advertised in the title like any other shed column.

    ``width <= 0`` means "not laid out yet" and optimistically picks
    ``full``; :meth:`SurfDevActivity.on_resize` re-lays it out once it has a
    size.
    """
    if width <= 0 or width >= FULL_WIDTH:
        return "full"
    if width >= COMPACT_WIDTH:
        return "compact"
    return "minimal"


def _budget(tier: str, width: int, stamp_cols: int, who: str, known: bool,
            amount_cols: int) -> tuple[int, str]:
    """Fit one row to ``width``; returns ``(wallet_cols, who)``.

    Order of sacrifice, after the tier has already dropped whole columns:

    1. a **known** label is cut with a visible ``…`` (down to
       ``_MIN_LABEL_COLS``) -- it is descriptive text;
    2. the **wallet** cell shrinks, and then goes whole;
    3. the **unknown-counterparty window** is never touched at all.

    ``width <= 0`` (not laid out yet) leaves everything at its natural size.
    """
    wallet_cols = _WALLET_COLS
    if width <= 0:
        return wallet_cols, who

    # Everything except the wallet cell, the counterparty and the amount.
    fixed = stamp_cols + _GAP + _GAP
    if tier != "minimal":
        fixed += _KIND_COLS + _GAP

    spare = width - (fixed + wallet_cols + len(who) + amount_cols)
    if spare >= 0:
        return wallet_cols, who

    if known and len(who) > _MIN_LABEL_COLS:
        room = max(len(who) + spare, _MIN_LABEL_COLS)
        spare += len(who) - room
        who = who[: room - 1] + "…"

    if spare < 0:
        wallet_cols = max(wallet_cols + spare, 0)
    return wallet_cols, who

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


def _row_markup(row, tier: str = "full", width: int = 0) -> str | None:
    """Format one activity row at ``tier``; ``None`` drops it.

    ``None`` means the row is malformed or poisonous and must never reach a
    pixel.  ``width`` is the real number of columns the log can show; the
    returned markup is guaranteed to fit it (see :func:`_budget`), so
    ``RichLog.write()`` never has to shrink -- and therefore never clips
    without a visible ``…``.
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
        who_raw = (
            str(row.get("counterparty") or DASH)
            if known
            else long_addr(row.get("counterparty"))
        )
        amount = f"  {value:,.3f} ETH" if (value and tier == "full") else ""

        wallet_cols, who_raw = _budget(
            tier, width, len(stamp), who_raw, known, len(amount)
        )

        # Pad raw, escape after -- padding an escaped string misaligns it.
        cells = [stamp]
        if wallet_cols:
            label = f"{str(row.get('wallet_label') or DASH)[:wallet_cols]:<{wallet_cols}}"
            cells.append(f"[bold]{safe_markup(label)}[/]")
        if tier != "minimal":
            kind_cell = f"{(kind or DASH)[:_KIND_COLS]:<{_KIND_COLS}}"
            cells.append(f"[dim]{safe_markup(kind_cell)}[/]")
        colour = "cyan" if known else "dim"
        cells.append(f"[{colour}]{safe_markup(who_raw)}[/]")
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

    def _set_title(self, hint: str = "") -> None:
        """``DEV ACTIVITY  ‹ widen for amounts``, width permitting.

        The hint is *appended*: the title itself never changes, so the screen
        tests' ``"DEV ACTIVITY" in text`` holds at every width.  It degrades
        to :data:`SHORT_HINT` rather than to nothing when the descriptive
        wording will not fit beside the title -- silence is what this whole
        module exists to prevent -- and only a panel too narrow for even that
        goes unmarked, because this Static has no ``text-overflow`` and an
        over-long title wraps onto a second line, pushing a row out of the log
        instead of announcing anything.
        """
        title = self.query_one("#surf-act-title", Static)
        width = max(self.content_size.width - 2, 0)
        text = TITLE
        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or len(TITLE) + 2 + len(candidate) <= width:
                    text += f"  [yellow]{candidate}[/]"
                    break
        title.update(text)

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
        lines = [
            m
            for m in (_row_markup(row, tier, width) for row in rows)
            if m is not None
        ]
        # No rows means nothing was shed, so nothing is advertised: a marker
        # over "no recent activity" would point at columns that do not exist.
        self._set_title(WIDEN_HINTS.get(tier, "") if lines else "")
        if not lines:
            log.write("[dim]  no recent activity[/]")
            return
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
