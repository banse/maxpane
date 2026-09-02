"""POOL4 FLOW: every swap through the capped-burn hook, and where its fee went.

One line per swap, newest first -- composited at the full tier::

    AGE   SIDE   SIZE     BURNED   STAKERS    INFERENCE
    2m    SELL   1.2K     111.42     12.38    0.0057 ETH
    7m    BUY    980.00     0.00      0.00    12.38 IMD
    14m   SELL~  4.5K       0.00      0.00    0.0031 ETH

    ~ accrued, not settled yet

**The load-bearing rule of this panel.** A BUY has no burn leg and no staker
leg: the hook only splits a fee out of a *sell*, so ``burned_imd`` and
``stakers_imd`` arrive as ``0.0`` on a buy and that is a **representable
zero**.  It renders ``0.00``.  ``None`` is reserved for one thing only --
``pool4_flow is None``, the whole-panel unavailable state, which gets its own
explicit line (:data:`UNAVAILABLE_LINE`) and never a row.  ``[]`` is a third
state again: swept, and genuinely quiet (:data:`EMPTY_LINE`).

That distinction is the defect CLAUDE.md records shipping on curator's rail,
where FARM said ``-- unknown`` off a dead read while HOUR SAVED and WHALE,
folded from the *same* dead group, said ``none yet`` -- so the panel read
confident and green straight through an outage.  Here the three states are
three different strings on screen, and
``test_a_buy_row_and_a_dead_panel_do_not_say_the_same_thing`` (plus its
``[]``-vs-``None`` sibling) is what keeps them different.

``settled`` is the fourth state and it is why the SIDE cell is five columns
rather than four.  A sell whose ``ClaimsSettled`` has not fired yet *also*
carries ``0.00`` legs -- a true zero, for a completely different reason -- so
the row is flagged ``~`` and the panel spells the flag out in a legend it
writes only when such a row is present.  Without that, "the hook took nothing"
and "the hook has not paid out yet" are the same three characters.

Row shape: ``SURF_ROW_KEYS["pool4_flow"]`` (``data/surf_models.py``, frozen by
WP0).  ``side`` is a closed, producer-owned vocabulary -- exactly
``POOL4_FLOW_SIDES`` == ``{"buy", "sell"}`` -- mapped through
:data:`SIDE_WORDS` to the word the panel shows; a row whose ``side`` is not a
member is malformed and dropped, the same treatment ``launchpad_activity.py``
gives an unknown ``kind``.  This module never imports ``data/``, but its
**test file may**, and
``test_the_side_cell_fits_the_producers_whole_vocabulary`` asserts the cell
against the real tuple in both directions, so a producer that grows a third
side reddens there rather than reaching a reader as a cut word.

``age_s`` is precomputed by the manager: this widget is **clock-free**, which
is the only reason a committed capture replays forever.

The network word
----------------

Every pool4 panel title ends ``· <NETWORK WORD>`` and ``· —`` when
``pool4_network`` is ``None`` -- a panel title never goes networkless
(implementation plan §5 R4).  On the day this ships there is no mainnet pool4
deployment, so the numbers on screen are *testnet* numbers, and a testnet
number on an unmarked panel is not merely stale: it is fictional presented as
live.

:func:`~widgets.surf._pool4.panel_title` is **imported**, and this module no
longer defines it.  It lived here for one wave, during which WP4 wrote the
same helper for the rail with *different semantics on unknown input* -- an
allowlist here, a pass-through there -- which was not two opinions but a
defect: one body could paint ``THE SPLIT · —`` beside ``THE RATCHET · BASE``,
five panels disagreeing about which chain the numbers above them came from.
Amendment A13 ruled for the allowlist and for one implementation, and
``_pool4.py`` is it.  ``tests/widgets/test_surf_pool4_shared.py`` reddens if
any pool4 module grows a local copy again.

Width behaviour
---------------

``RichLog`` is composed ``wrap=False`` (``activity.py``'s convention, for its
reason: the columns stay aligned down the panel, and any line wider than the
log's usable width is narrowed **at write time, with no ``…``, no marker and
nothing in the title**).  ``wrap=False`` and a width tier are a package deal.

The ladder is :func:`~widgets.surf._rowfit.tier_for`, the row arithmetic is
:func:`~widgets.surf._rowfit.row_cols` and the cell fitting is
:func:`~widgets.surf._rowfit.clip` / :func:`~widgets.surf._rowfit.pad` --
**imported, never copied.**  That module was hoisted out of ``activity.py``
and ``launchpad_activity.py`` on 2026-09-01 precisely so this panel would be
the first consumer that does not add a fourth copy of a helper whose
``len()``-vs-``cell_len()`` bug then has to be fixed four times.

==========  ==============  ==================================================
Tier        Needs (nominal) Row
==========  ==============  ==================================================
``full``    48              ``age  side  size  burned  stakers  0.0057 ETH``
``compact`` 36              ``age  side  size  burned  stakers``
``minimal`` 28              ``age  side  burned  stakers``
==========  ==============  ==================================================

Those three numbers are **nominal** and no tier is chosen against them.  Every
numeric cell here is unbounded -- ``fmt_imd`` delegates above 1000 to
``fmt_compact``, whose widest form grows with the value, and an ETH fee has no
ceiling either -- so the four data columns are **measured per batch**
(:func:`_batch_cols`) against their own header labels as a floor, and the tier
requirement is computed from the measurement.  Sizing them from a constant is
exactly the defect ``launchpad_activity``'s ``_AMOUNT_COLS`` records: a cell
one column short took the difference off the end of the line, and a *cut
number is a wrong number, not a missing one.*

Because every cell is padded to a width that already fits its own content, no
number is ever clipped.  What gets sacrificed instead is a whole column
(:data:`WIDEN_HINTS` names which), and below the narrowest layout the rows are
**withheld** and :data:`SHORT_HINT` written in their place -- never shrunk.

The two chrome lines are fitted by the same arithmetic: the header row is
built from the batch's own column widths, so it fits by construction, and the
legend is descriptive text and is the one string here that may be clipped.

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``.
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
    fmt_age,
    fmt_imd,
)
from maxpane_dashboard.widgets.surf._pool4 import (
    WIDEN_HINT,
    panel_title,
    parse_line,
    strip_tags,
)

#: The title vocabulary this module used to export -- ``NETWORK_WORDS``,
#: ``NETWORK_UNKNOWN``, ``TITLE_SEP``, ``network_word``, ``panel_title`` --
#: now lives in ``widgets/surf/_pool4.py`` and is imported, not re-exported:
#: a second import path to one definition is how the fourth copy gets written.
__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "HEADER_CELLS",
    "LEGEND_ACCRUED",
    "LEGEND_UNKNOWN",
    "MINIMAL_WIDTH",
    "SETTLED_FLAGS",
    "SHORT_HINT",
    "SIDE_WORDS",
    "SurfPool4Flow",
    "TITLE",
    "UNAVAILABLE_LINE",
    "WIDEN_HINTS",
]

#: Max rows rendered per refresh.  Mirrors ``surf_models.POOL4_FLOW_LIMIT``,
#: the cap the manager applies; a widget may not import ``data/``, so this is
#: a restated literal and ``test_the_row_cap_matches_the_producers_own`` pins
#: the two together, the same defensive re-cap ``launchpad_activity.py`` takes
#: against ``surf_client._MAX_ACTIVITY_ROWS``.
_MAX_ROWS = 25

#: The explicit unavailable line -- ``pool4_flow is None``.  Tested verbatim,
#: and tested to be **different text** from what a quiet sweep or a zero-legged
#: buy renders.
UNAVAILABLE_LINE = "pool4 flow unavailable"

#: The explicit quiet line -- ``pool4_flow == []``, a sweep that ran and found
#: no swaps.  A different sentence from :data:`UNAVAILABLE_LINE` on purpose.
EMPTY_LINE = "no pool4 swaps yet"

#: Panel title.  The network word is appended to it (:func:`panel_title`) and
#: a widen hint after that -- both appended, never substituted, so a screen
#: test's ``"POOL4 FLOW" in text`` holds at every width and in every state.
TITLE = "POOL4 FLOW"

#: Display vocabulary, CLOSED: the producer emits exactly
#: ``surf_models.POOL4_FLOW_SIDES`` == ``{"buy", "sell"}``.  A row outside it
#: is dropped rather than guessed.
SIDE_WORDS = {"buy": "BUY", "sell": "SELL"}

#: The settled flag, appended to the side word inside the same cell.  ``True``
#: (paid out by ``ClaimsSettled``) is the unmarked, quiet case; ``False`` is
#: accrued-but-unpaid; anything else is a state the payload did not tell us.
#: Three glyphs that share no substring with each other, ``SurfBurnPipeline.
#: _ready_word``'s rule applied to a row cell.
SETTLED_FLAGS = {True: "", False: "~", None: "?"}

LEGEND_ACCRUED = "~ accrued, not settled yet"
LEGEND_UNKNOWN = "? settled state unread"

# -- the column budget, in rendered columns ------------------------------
#
# Measured from the format strings in :func:`_row_fields` and from the header
# labels below, whichever is wider.  Only :data:`_SIDE_COLS` is a hard size:
# it holds a closed two-member vocabulary plus one flag column, so it has an
# exact widest member and a test pins it against the producer's own tuple.
# Every other data cell is **measured per batch** (:func:`_batch_cols`) --
# see the module docstring.

#: ``fmt_age``: ``45s`` / ``12m`` / ``2h`` / ``3d``.  Nominal; measured.
_AGE_COLS = 4

#: ``max(len(w) for w in SIDE_WORDS.values())`` == ``len("SELL")``, plus one
#: column for the settled flag.  Not measured per batch: the vocabulary is
#: closed and the flag is one cell, so there is nothing here that a payload
#: can grow.  ``test_the_side_cell_fits_the_producers_whole_vocabulary``
#: asserts it in both directions.
_SIDE_COLS = 5

#: Nominal widths, i.e. the widths of the header labels, which are the floor
#: every measured column starts from.  ``fmt_imd``'s two-decimal form is six
#: columns and its compact form grows past that, which is exactly why these
#: are a floor and not a size.
_SIZE_COLS = 6
_BURN_COLS = 6
_STAKERS_COLS = 7

#: Nominal inference cell: ``cell_len("  0.0057 ETH")``, two leading spaces
#: like both sibling panels.  It is what :data:`FULL_WIDTH` advertises and it
#: is **not** a promise that every fee fits it.
_FEE_COLS = 12

#: The gap between two cells.  Shared machinery: it lives in
#: ``widgets/surf/_rowfit.py`` and is aliased here under the name this
#: module's own docstrings use.
_GAP = _rowfit.GAP

#: Column headings.  This panel carries one and its two siblings do not,
#: because it is the only one of the three with **three same-unit numeric
#: columns** side by side: unlabelled, ``111.42  12.38`` says nothing about
#: which leg burned and which leg paid stakers, and that distinction is the
#: entire subject of the panel.  Each label is also the floor width of its
#: column, so the header can never be the thing that gets cut.
HEADER_CELLS = {
    "age": "AGE",
    "side": "SIDE",
    "size": "SIZE",
    "burn": "BURNED",
    "stakers": "STAKERS",
    "fee": "INFERENCE",
}

#: Nominal tier requirements -- advertised, never used to *choose* a tier.
#: See the module docstring: every data column is measured per batch.
FULL_WIDTH = (
    _AGE_COLS + _GAP + _SIDE_COLS + _GAP + _SIZE_COLS + _GAP
    + _BURN_COLS + _GAP + _STAKERS_COLS + _FEE_COLS
)                                                                    # 48
COMPACT_WIDTH = FULL_WIDTH - _FEE_COLS                               # 36
MINIMAL_WIDTH = COMPACT_WIDTH - _SIZE_COLS - _GAP                    # 28

#: Marker appended to the title when the layout had to shed a column.  Each
#: names what went, so the reader knows what they are not looking at.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for inference",
    "minimal": "‹ widen: size, inference",
}

#: Fallback marker for a panel too narrow to carry the descriptive hint beside
#: its title, and the line written in place of withheld rows.  It names
#: nothing, which is a real loss -- but "columns were dropped here" is the
#: contract and going silent is not an option this codebase allows.
#:
#: The **shared spelling** (``_pool4.WIDEN_HINT``) under the name this family
#: of ``RichLog`` panels already uses for it in ``activity.py`` and
#: ``launchpad_activity.py`` -- an alias, deliberately not a second literal, so
#: there is one string to change and ``test_the_widen_vocabulary_means_one_
#: thing_across_the_repo`` cannot find a spelling that drifted.  The rail's
#: narrower ``_pool4.GLYPH_HINT`` is a *different* marker and does not belong
#: under this name; this panel does not use it, because it has a log to write
#: the full marker into and that is louder than a bare glyph.
SHORT_HINT = WIDEN_HINT


def _fee_cell(fee_imd, fee_eth) -> str:
    """The inference cell, in the currency the fee was actually taken in.

    ``fee_imd`` and ``fee_eth`` are documented as mutually exclusive -- one
    leg carries the fee and the other is ``None`` -- so the cell names its own
    unit rather than the panel naming it once for both.  Tested against
    ``is not None`` and never against truthiness: a fee of exactly zero in
    either currency is a **read that succeeded**, and ``not 0.0`` would send
    it down the unread branch and print a dash over a number we have.

    Both legs unread is the one dash here: no fee was reported at all.  Two
    leading spaces, ``activity.py``'s convention for a trailing cell that
    begins where its neighbour ends.
    """
    imd = as_float(fee_imd)
    if imd is not None:
        return f"  {fmt_imd(imd)} IMD"
    eth = as_float(fee_eth)
    if eth is not None:
        return f"  {eth:,.4f} ETH"
    return f"  {DASH}"


def _row_fields(row: object) -> tuple[str, str, str, str, str, str] | None:
    """Decompose one row into its cells; ``None`` drops it.

    ``None`` means the row is malformed -- not a dict, or a ``side`` outside
    the closed vocabulary -- and must never reach a pixel.  A decision about
    *content*, taken before any decision about width, so the panel can tell
    "nothing to show" from "no room to show it".

    Returns ``(age, side, size, burned, stakers, fee)``, every one already a
    finished string; ``fee`` carries its own two leading spaces.

    ``burned`` and ``stakers`` go through ``fmt_imd`` **unconditionally**,
    which renders ``0`` as ``0.00`` and only a genuinely unreadable value as
    ``--``.  That is the whole contract of this panel: a buy's absent legs are
    zeros, not gaps.
    """
    if not isinstance(row, dict):
        return None
    try:
        side_raw = str(row.get("side") or "").strip().lower()
        side = SIDE_WORDS.get(side_raw)
        if side is None:
            # Not a member of the closed vocabulary: malformed, or a side
            # this panel has not been taught.  Either way, never guessed.
            return None
        settled = row.get("settled")
        flag = SETTLED_FLAGS.get(settled if isinstance(settled, bool) else None)
        return (
            fmt_age(row.get("age_s")),
            f"{side}{flag}",
            fmt_imd(row.get("size_imd")),
            fmt_imd(row.get("burned_imd")),
            fmt_imd(row.get("stakers_imd")),
            _fee_cell(row.get("fee_imd"), row.get("fee_eth")),
        )
    except Exception:
        # A single malformed row must never take down the panel.
        return None


def _batch_cols(showable) -> tuple[int, int, int, int, int]:
    """Column widths for a whole batch: ``(age, size, burn, stakers, fee)``.

    Each is the widest **rendered** cell in the batch, floored at its own
    header label, and measured on :func:`rich.cells.cell_len`.  Measured
    rather than sized because every one of them is unbounded: ``fmt_imd``
    delegates above 1000 to ``fmt_compact``, whose form grows with the
    magnitude, and an ETH fee has no ceiling at all.

    One layout for the whole batch is not decoration -- ``RichLog`` is
    composed ``wrap=False`` so the columns line up down the panel, and that
    only holds if every row was fitted to the same plan.  The widest row sets
    the layout for all of them, and because each column already fits its own
    widest member, no number in the batch is ever cut.
    """
    def widest(index: int, header: str) -> int:
        return max(
            [cell_len(HEADER_CELLS[header])]
            + [cell_len(fields[index]) for fields in showable]
        )

    return (
        widest(0, "age"),
        widest(2, "size"),
        widest(3, "burn"),
        widest(4, "stakers"),
        max(
            cell_len(f"  {HEADER_CELLS['fee']}"),
            *[cell_len(fields[5]) for fields in showable],
        ),
    )


def _row_cols(tier: str, cols: tuple[int, int, int, int, int]) -> int:
    """Rendered width of a row at ``tier`` given the batch's measured ``cols``.

    This panel's cells, handed to the shared
    :func:`~widgets.surf._rowfit.row_cols` -- which is where the rule lives:
    **a cell of zero width is absent, and an absent cell takes its gap with
    it.**  The inference cell carries its own leading gap inside its own
    string, so it is passed as ``trailing`` and added rather than joined.
    """
    age_cols, size_cols, burn_cols, stakers_cols, fee_cols = cols
    present = [age_cols, _SIDE_COLS]
    if tier != "minimal":
        present.append(size_cols)
    present += [burn_cols, stakers_cols]
    return _rowfit.row_cols(present, fee_cols if tier == "full" else 0)


def _tier_for(width: int, cols: tuple[int, int, int, int, int]) -> str:
    """Widest row layout that fits ``width`` rendered columns.

    Every threshold is derived from the batch's own measured columns, so a
    batch carrying a nine-figure burn selects a narrower tier -- and says so
    -- rather than overflowing the tier a constant said it fitted.

    ``width <= 0`` means "not laid out yet" and optimistically picks ``full``;
    :meth:`SurfPool4Flow.on_resize` re-lays it out once there is a size.
    """
    return _rowfit.tier_for(
        width,
        (
            ("full", _row_cols("full", cols)),
            ("compact", _row_cols("compact", cols)),
            ("minimal", _row_cols("minimal", cols)),
        ),
    )


def _cells_for(tier: str, fields, cols: tuple[int, int, int, int, int]):
    """The padded cell strings of one row (or of the header) at ``tier``."""
    age_cols, size_cols, burn_cols, stakers_cols, _fee = cols
    age, side, size, burned, stakers, _fee_str = fields
    out = [
        _rowfit.pad(age, age_cols),
        _rowfit.pad(side, _SIDE_COLS),
    ]
    if tier != "minimal":
        out.append(_rowfit.pad(size, size_cols))
    out.append(_rowfit.pad(burned, burn_cols))
    out.append(_rowfit.pad(stakers, stakers_cols))
    return out


def _header_markup(tier: str, cols: tuple[int, int, int, int, int]) -> str:
    """The column heading line, built from the batch's own widths.

    It therefore fits by construction: it is exactly as wide as the rows it
    labels, never wider, so it can never be the line ``RichLog`` shrinks.
    """
    fields = (
        HEADER_CELLS["age"],
        HEADER_CELLS["side"],
        HEADER_CELLS["size"],
        HEADER_CELLS["burn"],
        HEADER_CELLS["stakers"],
        "",
    )
    cells = _cells_for(tier, fields, cols)
    line = (" " * _GAP).join(cells)
    if tier == "full":
        line += f"  {HEADER_CELLS['fee']}"
    return f"[dim]{safe_markup(line)}[/]"


def _row_markup(fields, tier: str, cols: tuple[int, int, int, int, int]) -> str:
    """Format one already-decomposed row at ``tier``.

    Guaranteed to fit the width :func:`_tier_for` was given, because every
    cell is padded to a batch width that already fits its own content -- so
    ``RichLog.write`` never has to narrow this line and therefore never clips
    a number without a visible ``…``.

    Pad raw, escape after: padding an escaped string misaligns it.  Nothing
    on this row is free text (the frozen row shape's only such field,
    ``tx_hash``, has no column here), but every cell is escaped anyway rather
    than argued about -- ``safe_markup`` on a formatted number is the
    identity, and an invariant that is local beats one that depends on the
    producer staying numeric.
    """
    cells = _cells_for(tier, fields, cols)
    side_cell = f"[bold]{safe_markup(cells[1])}[/]"
    body = (" " * _GAP).join(
        [safe_markup(cells[0]), side_cell]
        + [safe_markup(cell) for cell in cells[2:]]
    )
    if tier == "full":
        body += safe_markup(fields[5])
    return body


def _legend(showable) -> str:
    """The flag legend, or ``""`` when no flagged row is on screen.

    Written only when it is needed: a legend for a glyph nothing is carrying
    is a line spent saying nothing, and this panel's rows are the scarce
    resource.
    """
    sides = [fields[1] for fields in showable]
    parts = []
    if any(side.endswith(SETTLED_FLAGS[False]) for side in sides):
        parts.append(LEGEND_ACCRUED)
    if any(side.endswith(SETTLED_FLAGS[None]) for side in sides):
        parts.append(LEGEND_UNKNOWN)
    return " · ".join(parts)


class SurfPool4Flow(Vertical):
    """Recent pool4 swaps and the three legs each one's fee was split into."""

    DEFAULT_CSS = """
    SurfPool4Flow > .surf-p4flow-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfPool4Flow > .surf-p4flow-note {
        width: 100%;
        padding: 0 1;
        color: $text-muted;
    }
    SurfPool4Flow > RichLog {
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
        yield Static(TITLE, classes="surf-p4flow-title", id="surf-p4flow-title")
        yield Static(" ", classes="surf-p4flow-note", id="surf-p4flow-note")
        yield RichLog(
            id="surf-p4flow-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(
        self,
        pool4_flow=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log.  Signature frozen by ``docs/surf_pool4_contract.md``
        §0.4 -- every key spelled with its full ``pool4_`` prefix, and
        ``**_kwargs`` mandatory because the screen splats the whole payload.
        """
        self._payload = {
            "rows": pool4_flow,
            "network": pool4_network,
            "as_of": pool4_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the layout depends on the width.

        The rows are formatted at write time against the width they were
        written at and nothing else re-renders them, so without this hook a
        widened or narrowed terminal shows the previous size's tier -- padded,
        or silently shrunk by ``RichLog`` -- for the life of the screen.
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
        exactly the column ``write()`` would shrink away.  Both sibling panels
        carry the same measurement and the same note.
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _static(self, selector: str, markup: str) -> None:
        """Update one of the two chrome ``Static``\\ s from a markup string.

        The parse happens **here**, synchronously, inside this ``try`` --
        ``Static.update("…[/x]…")`` parses nothing at call time: Textual defers
        ``Content.from_markup`` into the message pump, so a malformed string
        raises outside the screen's own ``try/except`` and takes the app down
        (CLAUDE.md, ``SurfFeed._row_text``).  Handing over a pre-built
        ``rich.text.Text`` moves that failure inside a handler that can
        degrade instead.
        """
        parsed = parse_line(markup)
        if parsed is None:
            return
        try:
            self.query_one(selector, Static).update(parsed)
        except Exception:  # not composed yet
            pass

    def _set_title(self, hint: str = "") -> bool:
        """``POOL4 FLOW · SEPOLIA  ‹ widen for inference``, width permitting.

        Returns whether the marker was placed, so the caller can say it
        somewhere else when it was not.  The title and its network word are
        never substituted -- only the hint is conditional -- so
        ``"POOL4 FLOW" in text`` holds at every width, and so does the network
        word beside it.
        """
        title = panel_title(TITLE, self._payload.get("network"))
        width = max(self.content_size.width - 2, 0)
        text = title
        placed = not hint
        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or (
                    cell_len(title) + 2 + cell_len(candidate) <= width
                ):
                    text += f"  [yellow]{candidate}[/]"
                    placed = True
                    break
        self._static("#surf-p4flow-title", text)
        return placed

    def _set_note(self) -> None:
        """``as of 14:32`` -- this tier's own slower clock, or a blank line.

        The pool4 sweep runs on a long detached tier, so this marker
        deliberately lags the title bar's; it advances only when new data
        actually lands.  It occupies the line the sibling panels spend on a
        blank spacer, so the panel is the same height with it as without.
        """
        # ``strip_tags`` before ``safe_markup``: an *escaped* ``[/x]`` still
        # paints the literal text ``[/x]`` once Rich unescapes it for display,
        # so escaping alone stops the crash and not the bracket noise.  A
        # persisted cache file is third-party input too.
        as_of = strip_tags(self._payload.get("as_of"))
        if as_of:
            self._static("#surf-p4flow-note", f"[dim]as of {safe_markup(as_of)}[/]")
        else:
            self._static("#surf-p4flow-note", " ")

    def _render_view(self) -> None:
        try:
            log = self.query_one("#surf-p4flow-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False
        self._set_note()

        width = self._log_width(log)

        def note(style: str, plain: str) -> None:
            """Write one chrome line, **fitted**.

            The rows are fitted by the column budget; these are not, and a
            chrome line handed to ``RichLog(wrap=False)`` wider than the log
            is narrowed at write time with no ``…`` and no marker -- the same
            silence the whole panel is built to avoid.  Descriptive text is
            the one thing here that may be clipped, so it is, visibly.
            """
            text = _rowfit.clip(plain, width) if width > 0 else plain
            log.write(f"[{style}]{safe_markup(text)}[/]")

        rows_payload = self._payload.get("rows")
        if rows_payload is None:
            # The whole-panel unavailable state, and the only thing ``None``
            # ever means here.  A row's own zero legs are zeros.
            self._set_title()
            note("yellow", f"⚠ {UNAVAILABLE_LINE}")
            return

        try:
            rows = list(rows_payload)[:_MAX_ROWS]
        except TypeError:
            rows = []

        showable = [f for f in (_row_fields(row) for row in rows) if f is not None]
        if not showable:
            # Swept and quiet -- a different sentence from unavailable, and
            # nothing was shed, so nothing is advertised.
            self._set_title("")
            note("dim", EMPTY_LINE)
            return

        cols = _batch_cols(showable)
        tier = _tier_for(width, cols)

        if 0 < width < _row_cols(tier, cols):
            # Even the narrowest layout does not fit.  Withheld rather than
            # cut: a shrunk row loses a number's tail with no ``…`` and no
            # marker, and a cut number is a wrong number.
            self._set_title(WIDEN_HINTS.get(tier, "") or SHORT_HINT)
            note("yellow", SHORT_HINT)
            return

        hint = WIDEN_HINTS.get(tier, "")
        if not self._set_title(hint):
            # The title bar is too narrow to carry the marker.  Say it in the
            # log rather than not at all -- one row is a far smaller loss than
            # a column that went unannounced.
            note("yellow", SHORT_HINT)

        log.write(_header_markup(tier, cols))
        for fields in showable:
            log.write(_row_markup(fields, tier, cols))

        legend = _legend(showable)
        if legend:
            log.write("")
            note("dim", legend)

        self.call_after_refresh(log.scroll_home, animate=False)
