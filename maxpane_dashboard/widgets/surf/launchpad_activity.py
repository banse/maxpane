"""LAUNCHPAD ACTIVITY: the launchpad's own event feed -- buys, sells, launches.

One line per event, newest first -- composited at the full tier::

    2m   BUY   ICE       0x047F…54B7    0.0120 ETH
    7m   SELL  K-256     0x84CB…f8e7    0.0031 ETH
    14m  NEW   PYCR      0xe5B1…64F2

(The amount is not a padded column, exactly ``activity.py``'s own
convention: ``_AMOUNT_COLS`` is a budget reserve, so the amount begins where
the wallet cell ends rather than at a fixed column.)

Row shape: ``SURF_ROW_KEYS["launchpad_activity"]`` (Task 1, frozen) --
``kind``, ``ticker``, ``wallet``, ``wallet_known``, ``eth``, ``age_s``.
``data/surf_client._launchpad_feed_from_logs`` (Task 10) is the producer; this module
never imports it, but a **test** may (widgets take primitives only; tests
may see both layers) -- see
``test_the_kind_cell_fits_the_whole_display_vocabulary`` in this module's own
test file, which calls the producer rather than comparing one literal
against another.

``kind`` is a closed, producer-owned vocabulary -- exactly ``{"buy", "sell",
"launch"}`` -- mapped through :data:`KIND_WORDS` to the word the panel shows.
``NEW`` rather than ``LAUNCH``: the cell is sized to the widest member and
``SELL`` is already four characters, so a fifth column here would come out
of the ticker cell beside it. A row whose ``kind`` is not in the vocabulary
is malformed and dropped, the same treatment ``activity.py`` gives a
``dust`` row.

``ticker`` is attacker-chosen exactly as it is in ``widgets/surf/
launchpad.py`` (``LaunchpadFactory.launch(string,string)`` is permissionless
and costs only gas), so it gets that module's own defense: flatten embedded
whitespace, strip complete ``[...]``-shaped bracket runs outright (not
merely escape them -- an escaped ``[/x]`` still *renders* as the literal
text ``[/x]`` once Rich unescapes it for display, which is the second-order
defect ``launchpad.py``'s own docstring records for the identical shape),
truncate, then :func:`~widgets.markup_safety.safe_markup`. Padding happens
*before* escaping in every cell here -- padding an escaped string misaligns
it, the same note ``activity.py`` carries for its own cells.

``wallet`` is never a friendly label -- there is no label field in this row
shape, unlike ``dev_activity``'s ``wallet_label`` -- so it is always the
anti-poisoning short-address window (``0x`` + 4 hex + ``…`` + 4 hex, this
module's own ``_ADDR_COLS``, half of ``activity.py``'s wider 17-column
form and identical to ``launchpad.py``'s own ``_short_addr``), styled cyan
when ``wallet_known`` and dim otherwise. It is put through the same
strip-then-escape treatment as ``ticker`` before windowing, in case a
malformed payload ever puts non-address text there.

``eth is None`` (a launch has no swap size) renders **no amount cell at
all**, never ``0.0000 ETH`` -- CLAUDE.md's "a failed read is None, never 0"
extends to "no such quantity exists on this row", which a launch's missing
swap size is a clean example of.

``launchpad_activity=None`` -> explicit unavailable state; ``[]`` ->
genuinely quiet launchpad. Primitives only.

Width behaviour
---------------

``RichLog`` is composed ``wrap=False`` (``activity.py``'s own convention, for
the same reason: columns stay aligned down the panel, and any line wider
than the log's usable width is narrowed silently at write time unless a
width tier already fitted it). Three tiers, each shedding whole fields
rather than cutting one:

==========  =====  ========================================
Tier        Needs  Row
==========  =====  ========================================
``full``    45     ``age  kind  ticker  wallet  0.0120 ETH``
``compact`` 33     ``age  kind  ticker  wallet``
``minimal`` 20     ``age  kind  ticker``
==========  =====  ========================================

The ``full`` row's 45 is quoted **for the amount in that example** and no
other: a swap has no upper bound, so ``  1234.5678 ETH`` needs 48. The
amount is measured with :func:`rich.cells.cell_len` and the tier chosen
against the widest one in the batch (:func:`_tier_for`), so a row that will
not fit sheds the amount whole and lights ``‹ widen for amounts`` rather
than losing its tail to ``RichLog``. Every other cell is *fitted* on cells
too, never sized on ``len()`` -- ``ticker`` is attacker-chosen and eight
CJK characters are sixteen columns.

:data:`WIDEN_HINTS` names what each tier shed, appended to the title;
:data:`SHORT_HINT` is the fallback for a panel too narrow to carry the
descriptive wording beside its own title.

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

import re

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf import _rowfit
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_age

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "KIND_WORDS",
    "MINIMAL_WIDTH",
    "SHORT_HINT",
    "SurfLaunchpadActivity",
    "TITLE",
    "UNAVAILABLE_LINE",
    "WIDEN_HINTS",
]

#: Max rows rendered per refresh -- mirrors ``surf_client._MAX_ACTIVITY_ROWS``
#: (Task 10). A widget may not import ``data/``, so this is a re-stated
#: literal, the same defensive re-cap ``launchpad.py``'s own
#: ``MAX_COIN_ROWS`` takes against ``LAUNCHPAD_RENDER_LIMIT``.
_MAX_ROWS = 40

#: The explicit degraded line. Tested verbatim.
UNAVAILABLE_LINE = "activity unavailable"

#: The explicit quiet line -- a sweep that ran and found nothing, distinct
#: from one that did not run at all.
EMPTY_LINE = "no launchpad activity"

#: Panel title. A hint is appended to it, never substituted for it, so
#: ``"LAUNCHPAD ACTIVITY" in text`` stays true at every width.
TITLE = "LAUNCHPAD ACTIVITY"

#: Display vocabulary, and it is CLOSED -- the producer emits exactly
#: ``{"buy", "sell", "launch"}`` (``surf_client._launchpad_feed_from_logs``) and this
#: maps each to the word the panel shows. ``NEW`` rather than ``LAUNCH``
#: because the cell is sized to the widest member and ``SELL`` is already
#: four: a fifth column here would come out of the ticker beside it.
#: ``test_the_kind_cell_fits_the_whole_display_vocabulary`` asserts the
#: sizing in both directions, so a new kind reddens here rather than
#: reaching a user as a cut word.
KIND_WORDS = {"buy": "BUY", "sell": "SELL", "launch": "NEW"}

_AGE_COLS = 4        # `fmt_age`: "2m", "14m", "3h", "2d"
_KIND_COLS = 4        # max(len(w) for w in KIND_WORDS.values()) == len("SELL")
_TICKER_COLS = 8      # the coin table's own `_TICKER_COLS`
_ADDR_COLS = 11       # the coin table's own `_short_addr` window

#: The amount cell's **nominal** reserve: exactly ``cell_len("  0.0120 ETH")``
#: for this panel's own ``f"  {eth:.4f} ETH"``, two leading spaces like
#: ``activity.py``. It is what :data:`FULL_WIDTH` advertises, and it is *not*
#: a promise that every row fits it: a swap has no upper bound, so ten ETH is
#: 13 columns and four figures is 15. The amount is therefore the one cell on
#: this row whose real width is **measured** (:func:`_row_cols`,
#: :func:`_tier_for`) rather than assumed -- ``activity.py``'s own
#: ``_AMOUNT_COLS``/``_budget`` split, which this module had copied only half
#: of.
#:
#: Copying only half of it was a live defect and not a theoretical one: this
#: constant arrived from ``activity.py:157``, where the format is
#: ``{value:,.3f}``. One more decimal, the same budget -- so ``  0.0120 ETH``
#: was exactly 12 and anything at or above ten ETH was 13, overflowing a row
#: that :func:`_row_markup` then declared already fitted. ``RichLog(wrap=
#: False)`` narrows such a line at write time with no ``…`` and no marker, so
#: ``1234.5678 ETH`` reached the reader as ``1234.5678`` -- and one cell to
#: the left, as ``0.`` where the value was ``0.0120 ETH``. A cut *number* is
#: a wrong number, not a missing one.
_AMOUNT_COLS = 12

#: The gap between two cells.  Shared machinery: it lives in
#: ``widgets/surf/_rowfit.py`` and is re-exported here under the name this
#: module's own docstrings have always used.
_GAP = _rowfit.GAP

#: The widest row layout's requirement **for an amount of :data:`_AMOUNT_COLS`**
#: -- what the panel advertises and what a screen sweep pins, exactly as
#: ``activity.py``'s own ``FULL_WIDTH`` is quoted for ``"  33.250 ETH"``. A
#: batch carrying a larger swap needs ``_row_cols("full", cell_len(amount))``
#: and the panel drops to ``compact`` (marker lit) rather than overflow.
FULL_WIDTH = (
    _AGE_COLS + _GAP + _KIND_COLS + _GAP + _TICKER_COLS + _GAP
    + _ADDR_COLS + _AMOUNT_COLS
)                                                              # 45
COMPACT_WIDTH = FULL_WIDTH - _AMOUNT_COLS                      # 33
MINIMAL_WIDTH = _AGE_COLS + _GAP + _KIND_COLS + _GAP + _TICKER_COLS  # 20

WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen for amounts",
    "minimal": "‹ widen: wallet, ETH",
}
SHORT_HINT = "‹ widen"

#: A complete ``[...]`` bracket run with no nested bracket -- ``launchpad.
#: py``'s own ``_TAG_LIKE``, duplicated here rather than imported: that
#: module is owned by a different work package and its private helpers are
#: not a contract this one should couple to.
_TAG_LIKE = re.compile(r"\[[^\[\]]*\]")


def _flatten(value: object) -> str:
    """Collapse embedded newlines/control whitespace to single spaces."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _strip_tags(value: object) -> str:
    """Flatten, then strip complete ``[...]``-shaped runs outright.

    Neither ``ticker`` nor ``wallet`` has a legitimate use for a literal
    square bracket. Stripping rather than merely escaping matters because an
    *escaped* ``[/x]`` still renders as the literal text ``[/x]`` once
    Rich's parser unescapes it for display -- escaping alone stops a crash,
    not the tag characters showing up on screen.
    """
    flat = _flatten(value)
    stripped = _TAG_LIKE.sub("", flat)
    return " ".join(stripped.split())


#: Truncate to ``width`` **terminal cells**, marking a cut with ``…``, and
#: left-align in ``width`` cells. Both moved to ``widgets/surf/_rowfit.py``
#: on 2026-09-01 -- they were about to be copied a third time -- and are
#: aliased here under the names this module's own docstrings use.
#:
#: The defect they carry the memory of is this panel's: ``ticker`` is
#: attacker-chosen (``LaunchpadFactory.launch(string,string)`` is
#: permissionless and costs only gas), so ``海豚海豚海豚海豚`` is eight
#: characters and sixteen columns. A ``len()``-sized ticker cell was eight
#: columns wider than the budget it was checked against, and pushed the
#: *amount* off the end of the row -- ``0.`` where the value was
#: ``0.0120 ETH``.
_clip = _rowfit.clip
_pad = _rowfit.pad


def _row_cols(tier: str, amount_cols: int) -> int:
    """Rendered width of a row at ``tier`` carrying an ``amount_cols``-wide
    amount -- this panel's cells, handed to the shared
    :func:`~widgets.surf._rowfit.row_cols`.

    An absent cell takes its :data:`_GAP` with it (the shared function's own
    rule); the amount carries its own two leading spaces
    (:func:`_row_fields`) and is passed as ``trailing``, added rather than
    joined.
    """
    present = [_AGE_COLS, _KIND_COLS, _TICKER_COLS]
    if tier != "minimal":
        present.append(_ADDR_COLS)
    return _rowfit.row_cols(present, amount_cols)


def _tier_for(width: int, amount_cols: int = _AMOUNT_COLS) -> str:
    """Widest row layout that fits ``width`` rendered columns, given a batch
    whose widest amount is ``amount_cols`` cells.

    ``amount_cols`` is why this takes a second argument at all: a swap has no
    upper bound, so ``full`` is not a fixed 45 columns -- it is 45 for the
    documented ``0.0120 ETH`` and 48 for ``1234.5678 ETH``. Comparing against
    :data:`FULL_WIDTH` alone selected ``full`` for a row that did not fit it,
    and ``RichLog(wrap=False)`` then took the difference off the end of the
    line with no ``…`` and no marker. Shedding the amount **whole** (which is
    what ``compact`` is) and lighting ``‹ widen for amounts`` is the honest
    answer to the same width.

    ``width <= 0`` means "not laid out yet" and optimistically picks
    ``full``; :meth:`SurfLaunchpadActivity.on_resize` re-lays it out once it
    has a size.
    """
    return _rowfit.tier_for(
        width,
        (
            ("full", _row_cols("full", amount_cols)),
            ("compact", COMPACT_WIDTH),
            ("minimal", 0),
        ),
    )


def _tier_cols(tier: str, amount_cols: int = _AMOUNT_COLS) -> int:
    """Columns the given tier's row layout needs, whole. Only ``full``
    carries an amount, so the other two ignore ``amount_cols``.
    """
    return _row_cols(tier, amount_cols if tier == "full" else 0)


def _ticker_cell(value: object) -> str:
    """Ticker cell, padded to :data:`_TICKER_COLS` cells then escaped."""
    cleaned = _clip(_strip_tags(value), _TICKER_COLS)
    if not cleaned:
        return f"[dim]{safe_markup(_pad(DASH, _TICKER_COLS))}[/]"
    return f"[bold]{safe_markup(_pad(cleaned, _TICKER_COLS))}[/]"


def _short_addr(value: object) -> str:
    """``0x`` + first 4 hex + ``…`` + last 4 -- this panel's own 11-column
    anti-poisoning window, identical to ``launchpad.py``'s ``_short_addr``
    (duplicated rather than imported -- see the note on :data:`_TAG_LIKE`).

    Stripped of bracket-tag-shaped content first: a real on-chain address
    never contains one, so this only ever fires on a malformed payload, but
    a stripped-to-empty value still degrades to :data:`DASH` rather than an
    empty cell.

    The window is measured in cells and re-fitted through :func:`_clip`. For
    a real address that is a no-op -- hex is one cell per character, so the
    window is exactly eleven -- but this field is only *conventionally* an
    address: it comes off the same payload the ticker does, and a value with
    wide glyphs in it would otherwise hand back an eleven-character,
    twenty-two-column "window" that no caller measures again.
    """
    s = _strip_tags(value)
    if not s:
        return DASH
    window = s if cell_len(s) <= _ADDR_COLS else f"{s[:6]}…{s[-4:]}"
    return _clip(window, _ADDR_COLS)


def _wallet_cell(value: object, known: bool) -> str:
    """The wallet window, padded to :data:`_ADDR_COLS` cells, styled cyan when
    ``known`` and dim otherwise -- never a friendly label (this row shape
    carries no label field, unlike ``dev_activity``'s ``wallet_label``).
    """
    window = _short_addr(value)
    colour = "cyan" if known else "dim"
    return f"[{colour}]{safe_markup(_pad(window, _ADDR_COLS))}[/]"


def _row_fields(
    row: object,
) -> tuple[str, str, object, object, bool, str] | None:
    """Decompose one row into its cells; ``None`` drops it.

    ``None`` means the row is malformed (not a dict, or ``kind`` outside the
    closed vocabulary) and must never reach a pixel -- a decision about
    *content*, taken before any decision about width, so the panel can tell
    "nothing to show" from "no room to show it".

    Returns ``(age, kind_word, ticker_raw, wallet_raw, known, amount)``,
    ``ticker_raw``/``wallet_raw`` raw and unescaped; ``amount`` carries its
    own two leading spaces and is empty only when ``eth`` is ``None``.

    It no longer takes a ``tier``: the amount is what *decides* the tier now
    (:func:`_tier_for`), so it has to be measurable before one has been
    picked. :func:`_row_markup` drops it for the layouts that do not carry
    one.
    """
    if not isinstance(row, dict):
        return None
    try:
        kind_raw = str(row.get("kind") or "").strip().lower()
        kind_word = KIND_WORDS.get(kind_raw)
        if kind_word is None:
            # Not a member of the closed vocabulary: malformed, or a kind
            # this panel has not been taught yet. Either way, never guessed.
            return None
        age = fmt_age(row.get("age_s"))
        ticker_raw = row.get("ticker")
        wallet_raw = row.get("wallet")
        known = bool(row.get("wallet_known"))
        eth = as_float(row.get("eth"))
        # A launch has no swap size: `None`, never a `0.0000 ETH` beside it
        # -- the same defect that put a LayerZero fee beside a five-figure
        # burn on the dev feed (see `activity.py`'s own note on `imd_burned`).
        amount = "" if eth is None else f"  {eth:.4f} ETH"
        return age, kind_word, ticker_raw, wallet_raw, known, amount
    except Exception:
        # A single malformed row must never take down the panel.
        return None


def _row_markup(row: object, tier: str = "full", width: int = 0) -> str | None:
    """Format one activity row at ``tier``; ``None`` drops it.

    ``width`` **is** consulted, and the docstring that said it was not was
    the defect: it claimed "every cell in this row is already fixed-width",
    which was false at both ends. The amount is unbounded (a swap can be any
    size, and ``{eth:.4f}`` at ten ETH is already one column past
    :data:`_AMOUNT_COLS`), and the ticker was *sized* on ``len()`` rather
    than *fitted* on ``cell_len`` -- so a two-cell-per-character ticker made
    the row eight columns wider than the arithmetic said. Either one pushed
    the last cell off a ``RichLog(wrap=False)`` line with no ``…`` and no
    marker.

    A markup string that is returned is therefore **guaranteed to fit**
    ``width`` (``activity.py``'s own contract), so ``RichLog.write()`` never
    has to narrow it. ``None`` on a row that cannot be fitted even after the
    tier has shed what it can: the caller withholds the batch and says
    :data:`SHORT_HINT` rather than render a cut number.
    """
    fields = _row_fields(row)
    if fields is None:
        return None
    try:
        age, kind_word, ticker_raw, wallet_raw, known, amount = fields
        if tier != "full":
            amount = ""
        if 0 < width < _row_cols(tier, cell_len(amount)):
            return None
        cells = [
            _pad(_clip(age, _AGE_COLS), _AGE_COLS),
            f"[dim]{_pad(kind_word, _KIND_COLS)}[/]",
            _ticker_cell(ticker_raw),
        ]
        if tier != "minimal":
            cells.append(_wallet_cell(wallet_raw, known))
        return (" " * _GAP).join(cells) + amount
    except Exception:
        # A single malformed row must never take down the panel.
        return None


class SurfLaunchpadActivity(Vertical):
    """Recent launchpad buys, sells and launches, newest first."""

    DEFAULT_CSS = """
    SurfLaunchpadActivity > .surf-lpa-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfLaunchpadActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw rows, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(TITLE, classes="surf-lpa-title", id="surf-lpa-title")
        yield Static(" ", classes="surf-lpa-spacer")
        yield RichLog(
            id="surf-lpa-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(self, launchpad_activity=None, as_of_hhmm=None, **_kwargs) -> None:
        """Rewrite the log. ``launchpad_activity`` is the PRD §5 key;
        ``as_of_hhmm`` is accepted (the launchpad's own slower-tier clock)
        but this panel has no note line to put it in yet, so it is
        currently unused -- accepted rather than raising, the same contract
        ``SurfBurnPipeline.update_data`` documents for its own un-rewired
        callers.
        """
        self._payload = {"rows": launchpad_activity, "seen": True}
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the layout depends on the width (see
        ``activity.py``'s own ``on_resize`` for why this hook exists).
        """
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _log_width(self, log: RichLog) -> int:
        """Rendered columns available to one line -- ``activity.py``'s own
        measurement and its own note: ``scrollable_content_region``, not
        ``content_size``, because ``RichLog``'s permanent scrollbar gutter
        is reserved even for a two-line log.
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _set_title(self, hint: str = "") -> bool:
        """``LAUNCHPAD ACTIVITY  ‹ widen for amounts``, width permitting.

        Returns whether the marker was placed. The hint is appended, never
        substituted, so ``"LAUNCHPAD ACTIVITY" in text`` holds at every
        width; a panel too narrow for even :data:`SHORT_HINT` returns
        ``False`` and the caller writes the marker into the log instead.
        """
        title = self.query_one("#surf-lpa-title", Static)
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
            log = self.query_one("#surf-lpa-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        rows_payload = self._payload.get("rows")
        if rows_payload is None:
            self._set_title()
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            rows = list(rows_payload)[:_MAX_ROWS]
        except TypeError:
            rows = []

        width = self._log_width(log)

        # Which rows may be shown at all -- a content question, decided
        # before any width question, so "nothing to show" stays distinct
        # from "no room to show it".
        showable = [f for f in (_row_fields(row) for row in rows) if f is not None]
        if not showable:
            self._set_title("")
            log.write(f"[dim]  {EMPTY_LINE}[/]")
            return

        # One layout for the whole batch (`activity.py`'s own rule, for the
        # same reason: `RichLog` is composed `wrap=False` so the cells line
        # up down the panel, which only holds if every row was fitted to the
        # same plan). The amount is the one unbounded cell here, so the
        # **widest** amount in the batch is what the tier is chosen against
        # -- picking `full` off `FULL_WIDTH` alone selected it for a batch
        # holding a four-figure swap that did not fit, and the difference
        # came off the end of every such line unannounced.
        amount_cols = max(cell_len(fields[5]) for fields in showable)
        tier = _tier_for(width, amount_cols)

        if 0 < width < _tier_cols(tier, amount_cols):
            # Even the narrowest tier does not fit: withhold the rows
            # rather than let `RichLog(wrap=False)` shrink them with no
            # marker (`activity.py`'s `FLOOR_WIDTH` precedent).
            self._set_title(WIDEN_HINTS.get(tier, "") or SHORT_HINT)
            log.write(f"[yellow]{SHORT_HINT}[/]")
            return

        lines = [
            line
            for line in (_row_markup(row, tier, width) for row in rows)
            if line is not None
        ]
        if len(lines) < len(showable):
            # A row the tier could not fit after all. Rendering the rest
            # would leave the panel looking complete while an event went
            # missing, so they all wait for width and the panel says so.
            self._set_title(WIDEN_HINTS.get(tier, "") or SHORT_HINT)
            log.write(f"[yellow]{SHORT_HINT}[/]")
            return

        hint = WIDEN_HINTS.get(tier, "")
        if not self._set_title(hint):
            # The title bar is too narrow to carry the marker. Say it in
            # the log rather than not at all.
            log.write(f"[yellow]{SHORT_HINT}[/]")
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
