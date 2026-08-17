"""Newest-first deposit feed for THE LIST (PRD §4, bottom left).

One line per log row, at the widest tier::

    22:58  deposit  0x381f…cdef    3.60Ξ  (+2.80 credit → 7.03 wt)  tx#4
    22:57  joined   0x200e…0fb1    0.05Ξ  (+0.05 credit → 0.10 wt)  tx#1
    22:41  saved    0xcb0b…da91   60.00Ξ  (+60.00 credit → 60.00 wt)  tx#1

``kind`` is the producer's three-value vocabulary — ``deposit`` /
``joined`` (a ``FirstDeposit``) / ``saved`` (a ``HourSaved``) — and the cell
is sized to the widest of exactly those three.  Not to a remembered
vocabulary: a cell padded for a word the producer never emits costs a column
on every row, and a cell one character short cuts a real value mid-word with
no ``…`` and nothing in the title.  That is the ``dev``/``ops`` defect
CLAUDE.md records, and it cost the surf feed nine columns and a ``fwa clai``.
:data:`KIND_COLS` is asserted against ``CURATOR_ACTIVITY_KINDS`` from the
test side (widgets may not import ``data/``).

De-duplication is by ``(tx_hash, log_index)``
---------------------------------------------

Both halves, and this is not defensive programming: an incremental sweep
that overlaps the previous window by a block, or a re-org replay, resends
rows, and without the pair as the key every deposit renders twice and the
feed silently doubles the game's apparent activity.  Keying on the
transaction hash **alone** is worse than nothing — a single transaction
legitimately emits several logs (a ``Deposited`` and the ``FirstDeposit``
that accompanies a wallet's first send, a ``HourSaved`` and the
``Deposited`` that saved the hour) — so that spelling both fails to
de-duplicate a replay *and* deletes a real row.

Three degradation rules
-----------------------

* ``ts is None`` renders ``--:--``.  A ``0`` would render ``00:00`` on
  1970-01-01, which looks like data (H14).
* One unparseable field costs **its own cell**, not the row and not the
  panel (MEDI-37).  A row that cannot be read at all is dropped, and the
  panel still renders the rest.
* ``activity_rows=None`` is ``activity unavailable``; ``[]`` is ``no
  deposits yet``.  A dead log endpoint must never read as a quiet game.

``credited_eth == 0`` is legitimate
-----------------------------------

A deposit above the 1000 ETH credit cap credits nothing and still counts
**fully** toward the hour's survival (H3).  ``+0.00 credit`` is therefore a
real reading and renders as the number; only ``None`` renders ``--``.
Nothing here divides by it.

Width behaviour
---------------

=========  ====  ================================================
Tier       Cost  Row
=========  ====  ================================================
full        74   stamp kind addr amount (+credit → wt) tx
compact     64   ...with the delta's words dropped: ``(+2.80 → 7.03)``
narrow      44   ...delta gone
minimal     36   ...tx gone
floor       27   ...kind gone
=========  ====  ================================================

``RichLog`` is composed ``wrap=False`` and ``RichLog.write()`` narrows any
over-wide line **at write time** with no ``…`` and nothing in the title — so
``wrap=False`` and a width tier are a package deal.  Every tier below the
widest names what it shed in the panel title.

**Every cost above is measured against the widest row the producer can
emit, not against the example in this docstring.**  The two are not the
same row: the sample line above is 68 columns and the captured 461.1 ETH
whale is 74, so a tier sized to the sample clipped the whale dark at four
widths where the panel reported no marker at all.  ``_DELTA_COLS`` and
``AMOUNT_COLS`` are therefore derived from ``COMPACT_ETH_COLS``, which is
itself measured off ``fmt_eth_compact``.

Rich markup, not Textual markup: ``RichLog.write`` parses with Rich's own
``Text.from_markup``, which does not know Textual's ``$token`` extension and
raises ``MarkupError`` on ``[$warning]`` instead of degrading (the FWA
activity-feed crash).  Colours here are spelled as plain names.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.curator._fmt import (
    ADDR_COLS,
    COMPACT_ETH_COLS,
    DASH,
    as_float,
    fmt_eth_compact,
    hhmm,
    short_addr,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended to it, never substituted for it.
ACTIVITY_TITLE = "ACTIVITY"

#: The two explicit states, tested verbatim and deliberately different.
ACTIVITY_UNAVAILABLE = "activity unavailable"
ACTIVITY_EMPTY = "no deposits yet"

#: Rows rendered per refresh.  The feed is a *recent* window, not a history:
#: the whole log set is 377 rows at capture time and grows unbounded while
#: the game lives (H15), so the panel documents its cap rather than
#: discovering it as a scroll performance problem.
MAX_ROWS = 25

#: ``HH:MM`` / ``--:--`` — both five columns, so a missing stamp cannot
#: re-flow the row.
STAMP_COLS = 5

#: The producer's whole vocabulary is ``{deposit, joined, saved}``
#: (``CURATOR_ACTIVITY_KINDS``), so the cell is ``len("deposit")`` and not a
#: column more.  Pinned from both sides by
#: ``test_the_kind_cell_is_sized_to_the_vocabulary_its_producer_emits``.
KIND_COLS = 7

#: ``fmt_eth_compact``'s measured worst case plus the Ξ.  ``COMPACT_ETH_COLS``
#: is measured off the formatter over ``COMPACT_ETH_PROBE`` rather than
#: remembered: this constant used to be a hand-typed 7 justified by
#: "``999.99`` plus the Ξ", which happened to agree, while its two siblings
#: below did not.
AMOUNT_COLS = COMPACT_ETH_COLS + 1                                       # 7

#: ``tx#999`` — the ladder is a per-wallet escalation count, not a global one.
TX_COLS = 6

#: Gap between two cells.
_GAP = 2

#: The delta cell, at both tiers, **derived from the formatter** rather than
#: from an example row.
#:
#: These were 24 and 14, and 24 was documented as
#: ``(+461.10 credit → 899.00 wt)`` "measured at the largest real send in the
#: captures".  That literal is **28** columns; 24 is the width of the small
#: example one line up in the docstring, ``(+2.80 credit → 7.03 wt)``.  The
#: consequence was not a cosmetic four columns: ``FULL_WIDTH`` came out 70
#: where the whale row needs 74, ``RichLog`` is composed ``wrap=False`` so
#: ``write()`` narrows the line at write time with no ``…``, and the tier
#: check said "full fits" — so the largest deposit the game has ever seen
#: rendered with its ``tx#`` cut off and nothing in the title.  Building both
#: widths out of ``COMPACT_ETH_COLS`` makes an example row unable to set them.
_DELTA_COLS = len(f"(+{'9' * COMPACT_ETH_COLS} credit → {'9' * COMPACT_ETH_COLS} wt)")
_DELTA_SHORT_COLS = len(f"(+{'9' * COMPACT_ETH_COLS} → {'9' * COMPACT_ETH_COLS})")

FULL_WIDTH = (
    STAMP_COLS + _GAP + KIND_COLS + _GAP + ADDR_COLS + _GAP + AMOUNT_COLS
    + _GAP + _DELTA_COLS + _GAP + TX_COLS
)                                                                        # 74
COMPACT_WIDTH = FULL_WIDTH - (_DELTA_COLS - _DELTA_SHORT_COLS)           # 64
NARROW_WIDTH = COMPACT_WIDTH - _GAP - _DELTA_SHORT_COLS                  # 44
MINIMAL_WIDTH = NARROW_WIDTH - _GAP - TX_COLS                            # 36
FLOOR_WIDTH = MINIMAL_WIDTH - _GAP - KIND_COLS                           # 27

#: What each tier shed, named in the title.  Never nothing.
WIDEN_HINTS = {
    "full": "",
    "compact": "‹ widen: credit wording",
    "narrow": "‹ widen: credit + weight",
    "minimal": "‹ widen: credit, weight, tx",
    "floor": "‹ widen: kind, credit, weight, tx",
}

#: Fallback for a title bar too narrow to carry the descriptive hint.
SHORT_HINT = "‹ widen"

#: Row colours, by kind.  Rich colour names — see the module docstring.
_KIND_COLOUR = {
    "saved": "bold yellow",   # the hour was pulled back from the line
    "joined": "cyan",         # a FirstDeposit: a new wallet on THE LIST
    "deposit": "dim",
}


def _tier_for(width: int) -> str:
    """Widest row layout that fits ``width`` rendered columns."""
    if width <= 0 or width >= FULL_WIDTH:
        return "full"
    if width >= COMPACT_WIDTH:
        return "compact"
    if width >= NARROW_WIDTH:
        return "narrow"
    if width >= MINIMAL_WIDTH:
        return "minimal"
    return "floor"


def _dedupe_key(row: dict):
    """``(tx_hash, log_index)`` — or ``None`` when the row cannot be keyed.

    ``None`` means "never merge this row with another": a payload missing
    both halves is malformed, and collapsing two unkeyable rows into one
    would delete a real event to hide a defect.
    """
    tx_hash = row.get("tx_hash")
    log_index = row.get("log_index")
    if tx_hash is None and log_index is None:
        return None
    return (str(tx_hash).strip().lower(), log_index)


def _amount_cell(row: dict) -> str:
    value = fmt_eth_compact(row.get("amount_eth"))
    return f"{value}Ξ"


def _delta_cell(row: dict, tier: str) -> str:
    """``(+2.80 credit → 7.03 wt)`` — the credited delta and the new weight.

    ``credited_eth`` of ``0`` is a real reading (a deposit over the credit
    cap) and prints as ``+0.00``; only ``None`` prints ``--``.
    """
    credited = as_float(row.get("credited_eth"))
    weight = as_float(row.get("new_weight"))
    credit_str = f"+{fmt_eth_compact(credited)}" if credited is not None else DASH
    weight_str = fmt_eth_compact(weight) if weight is not None else DASH
    if tier == "compact":
        return f"({credit_str} → {weight_str})"
    return f"({credit_str} credit → {weight_str} wt)"


def _row_markup(row: dict, tier: str) -> str | None:
    """One feed line, or ``None`` when the row is unusable.

    Every cell is built in its own ``try``: MEDI-37's rule is that one
    unparseable field costs its own cell.  The address and the stamp are
    what make a row identifiable, so the row survives anything else.
    """
    if not isinstance(row, dict):
        return None
    try:
        kind = str(row.get("kind") or "").strip().lower()
        colour = _KIND_COLOUR.get(kind, "dim")
        stamp = hhmm(row.get("ts"))
        address = safe_markup(short_addr(row.get("address")))
        amount = _amount_cell(row)

        cells = [f"[dim]{stamp:<{STAMP_COLS}}[/]"]
        if tier != "floor":
            shown = kind if kind else DASH
            cells.append(
                f"[{colour}]{safe_markup(f'{shown[:KIND_COLS]:<{KIND_COLS}}')}[/]"
            )
        cells.append(f"[{colour}]{address}[/]")
        cells.append(f"[bold]{amount:>{AMOUNT_COLS}}[/]")
        if tier in ("full", "compact"):
            cells.append(f"[dim]{safe_markup(_delta_cell(row, tier))}[/]")
        if tier in ("full", "compact", "narrow"):
            tx_count = row.get("tx_count")
            try:
                tx_str = f"tx#{int(tx_count)}"
            except (TypeError, ValueError):
                tx_str = f"tx#{DASH}"
            cells.append(f"[dim]{safe_markup(tx_str)}[/]")
        return (" " * _GAP).join(cells)
    except Exception:
        # A single malformed row never takes down the panel.
        return None


class CuratorActivity(Vertical):
    """The deposit feed, newest first, de-duplicated by (tx, log index)."""

    DEFAULT_CSS = """
    CuratorActivity > .curator-activity-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(
            ACTIVITY_TITLE, classes="curator-activity-title", id="curator-act-title"
        )
        yield Static(" ", classes="curator-activity-spacer")
        yield RichLog(
            id="curator-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(self, activity_rows=None, **_kwargs) -> None:
        """Rewrite the feed.

        The producer supplies rows **newest first**; this widget preserves
        the order it is given and never re-sorts by ``ts``, because a missing
        stamp is a legitimate state and sorting by it would shuffle exactly
        the rows whose provenance already degraded.
        """
        self._payload = {"rows": activity_rows, "seen": True}
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the tier is a function of the width."""
        if self._payload:
            self._render_view()

    # -- rendering ---------------------------------------------------------

    def _log_width(self, log: RichLog) -> int:
        """Columns one line really has.

        ``scrollable_content_region``, not ``content_size``: ``RichLog``'s own
        CSS sets ``overflow-y: scroll`` (always, not ``auto``), so the gutter
        is reserved even for a two-line log and ``content_size.width``
        overstates the usable width by the one column ``write()`` shrinks.
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _set_title(self, hint: str = "") -> None:
        title = self.query_one("#curator-act-title", Static)
        width = max(self.content_size.width - 2, 0)
        text = ACTIVITY_TITLE
        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or len(ACTIVITY_TITLE) + 2 + len(candidate) <= width:
                    text += f"  [yellow]{candidate}[/]"
                    break
        title.update(text)

    def _render_view(self) -> None:
        try:
            log = self.query_one("#curator-activity-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        rows = self._payload.get("rows")
        if rows is None:
            self._set_title()
            log.write(f"[yellow]⚠ {ACTIVITY_UNAVAILABLE}[/]")
            return

        try:
            candidates = [r for r in list(rows) if isinstance(r, dict)]
        except TypeError:
            candidates = []

        # De-duplicate before capping, so a replayed window cannot push real
        # rows off the end of the feed.
        seen: set = set()
        unique: list[dict] = []
        for row in candidates:
            key = _dedupe_key(row)
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            unique.append(row)
            if len(unique) >= MAX_ROWS:
                break

        if not unique:
            self._set_title()
            log.write(f"[dim]  {ACTIVITY_EMPTY}[/]")
            return

        width = self._log_width(log)
        tier = _tier_for(width)
        self._set_title(WIDEN_HINTS.get(tier, ""))

        for row in unique:
            markup = _row_markup(row, tier)
            if markup is not None:
                log.write(markup)
        self.call_after_refresh(log.scroll_home, animate=False)
