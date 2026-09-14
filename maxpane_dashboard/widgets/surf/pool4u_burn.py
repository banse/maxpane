"""The `4` body's chart slot: BURN & SUPPLY -- what the hook has retired.

A sparkline of recent burns, the pace those burns imply, the cumulative total
retired, and that total as a share of supply (PRD §6.2).

Where the series comes from, and the contract gap behind that sentence
----------------------------------------------------------------------
The plan's WP5 step says *"sparkline over ``pool4_burn_points``"*. **There is
no such key.** WP0 froze nine fast-tier names and a burn series is not one of
them; ``SURF_KEYS`` carries exactly three series (``supply_series``,
``price_series``, ``pool4_reserve_series``) and none of them is it. Naming it
anyway is not an option either -- ``tests/widgets/test_surf_widget_contract.py
::test_update_data_kwargs_are_frozen_contract_keys`` refuses a kwarg that is
not a contract key, so the panel would have had a signature the screen could
never satisfy.

So the series is folded here out of ``pool4_flow``, and the three candidates
were weighed rather than the first one taken:

* **``pool4_flow``** -- chosen. Same tier, same sweep, **same network** as
  every other number on this panel, with ``ts`` and ``burned_imd`` already
  pinned per row in ``SURF_ROW_KEYS`` and already carrying the
  representable-zero contract this panel needs (a BUY has no burn leg, so
  ``0.00`` is a real value and ``None`` is reserved for unread).
* **``supply_series``** -- rejected. IMD's supply steps down as it burns, so
  the deltas *are* a burn series -- but it is the **surf fast tier's** series
  off mainnet IMD, while this body renders Sepolia whenever no mainnet hook is
  adopted. A panel titled ``· SEPOLIA`` drawing a mainnet supply history is
  the five-panels-disagreeing-about-which-chain defect the network word exists
  to prevent, one layer in.
* **``pool4_reserve_series``** -- rejected. It is the hook's IMD *reserve*, not
  its burns. A plausible-looking wrong number is worse than a missing one.

What the panel is honest about as a result: ``pool4_flow`` is capped at
``POOL4_FLOW_LIMIT`` (25) recent events, so this is **recent** burn, not all of
history, and the pace carries its own window in the label the way the hero's
trailing return carries ``7d``. The cumulative ``pool4_total_burned`` beside it
is the all-time number and is read, not folded.

Sparkline helpers are imported, never copied
--------------------------------------------
``build_sparkline_from_points`` comes from ``widgets/sparkline_common.py``.
Three dashboards once carried byte-identical copies of those helpers and a fix
reached none of the others (MEDI-36).

A ``None`` sample is a gap, never a zero
----------------------------------------
``coerce_points`` drops a malformed or ``None``-valued pair rather than
substituting anything, which is what this panel needs: a zero written into a
burn series reads as *burning stopped*, a different and wrong claim. A genuine
``0.0`` on a BUY row is a real sample and stays.

Purity
------
Stdlib, ``rich``, ``textual`` and this package's own primitives. No ``data/``,
no ``analytics/``, no clock, no I/O -- the window below is measured from the
rows' own timestamps, never from ``time.time()``. Rich colour names only.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline_from_points,
    coerce_points,
)
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_age, fmt_compact
from maxpane_dashboard.widgets.surf._pool4 import (
    TITLE_CLASS,
    join_lines,
    market_title_text,
    parse_line,
    widest_line,
)
from maxpane_dashboard.widgets.surf._rowfit import pad

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "LABEL_COLS",
    "MIN_PACE_WINDOW_S",
    "PACE_UNAVAILABLE",
    "ROW_LABELS",
    "SPARK_COLS",
    "TITLE",
    "UNAVAILABLE_LINE",
    "SurfPool4UBurn",
    "burn_points",
    "burn_window",
    "pace_per_day",
]

TITLE = "BURN & SUPPLY"

#: Nothing was read at all -- every input to this panel is ``None``.
UNAVAILABLE_LINE = "burn & supply unavailable"

#: The sweep ran and the flow window holds no events. A real state, and a
#: different sentence from :data:`UNAVAILABLE_LINE`: the curator rail bug is a
#: dead group's "unknown" and a genuine "none yet" reading identically.
EMPTY_LINE = "no flow observed"

#: What the pace reads when the window is too short to annualise -- see
#: :func:`pace_per_day`.
PACE_UNAVAILABLE = f"{DASH}/day"

#: Below this, a per-day figure is an extrapolation and not a measurement.
#:
#: One hour. A five-minute window multiplied by 288 turns one trim into a
#: headline burn rate, and the panel would report a pace that the next poll
#: contradicts by an order of magnitude. Above an hour the number is still
#: lumpy -- trims only happen when sells exceed headroom -- which is why the
#: window rides in the label either way.
MIN_PACE_WINDOW_S = 3600.0

#: Sparkline width per tier. Narrower than ``sparkline_common.SPARK_WIDTH`` even
#: at full, because the pace sits on the same line and because ``pool4_flow`` is
#: capped at ``POOL4_FLOW_LIMIT`` (25) events -- a 22-cell line drawn from at
#: most 25 samples is already close to one cell per sample, and asking for more
#: cells than there are samples buys resolution that is not in the data.
#:
#: **The line itself is a tier.** It has to be: it is the widest fixed thing on
#: the panel, so a compact tier that shed only words would light the widen
#: marker and still overflow by however much the sparkline is over budget.
SPARK_COLS = {"full": 12, "compact": 10}

#: The label column, in **terminal cells** -- ``SurfPool4USignals.LABEL_COLS``
#: restated, deliberately, because the two panels are the rail's only two
#: occupants and a reader's eye runs straight down from one to the other. Two
#: different label widths one above the other is exactly the "ragged" the
#: 2026-09-12 screenshot review named.
#:
#: **Restated and not imported.** A widget importing a sibling widget's
#: constant is a coupling across an ownership seam, not a hoist (the reason
#: ``NO_BAND`` is spelled twice in this body too); the repo's answer is
#: redundancy plus an agreement test, and
#: ``test_the_rail_panels_share_one_label_column`` imports both and compares
#: them, so the two cannot drift apart in silence.
#:
#: Wide enough for this panel's own labels with room to spare -- ``burn rate``
#: is nine -- because the number it has to match is the *neighbour's*.
LABEL_COLS = 13

#: The three row labels, in render order, at the full tier. A tuple so a test
#: can assert the panel paints exactly these three and in this order.
#:
#: ``burn rate`` and not ``burn``: the value beside it is a per-day rate over
#: a named window, and the two rows under it are cumulative quantities. A
#: label that did not say which was which would put a rate and a total in one
#: column and let the reader assume they were the same kind of number.
ROW_LABELS: tuple[str, ...] = ("burn rate", "retired", "supply")

_BODY_ID = "surf-pool4u-burn-body"
_TITLE_ID = "surf-pool4u-burn-title"

#: Widest part of each line, in cells: ``fmt_compact`` tops out at ``999.9B``
#: and ``fmt_age`` at ``999d``.
_AMOUNT_COLS = 6
_AGE_COLS = 4

#: Widest full-tier line: the label column plus the pace cell,
#: ``{spark}  {amount}/day over {age}``. The retired cell (``999.9B ·
#: 100.00% of supply``, 26) and the supply cell (``999.9B IMD``, 10) both fit
#: under it.
#:
#: **The sparkline shed four cells (16 -> 12) to pay for the label column**,
#: rather than the panel asking the body for four more. That is the standing
#: "shorten the value, do not raise the pin" rule, and it costs nothing this
#: panel had: ``pool4_flow`` is capped at ``POOL4_FLOW_LIMIT`` (25) events, so
#: even twelve cells is half a cell per sample at the cap and the resolution
#: lost is resolution that was never in the data. What it buys is the
#: neighbour's alignment -- see :data:`LABEL_COLS`.
FULL_WIDTH = (
    LABEL_COLS + SPARK_COLS["full"] + 2 + _AMOUNT_COLS
    + len("/day over ") + _AGE_COLS
)                                                                        # 47

#: One tier down, and the pace line is still what sets it:
#: ``{spark} {amount}/day {age}``.
#:
#: **The label column is a full-tier affordance and is the first thing shed.**
#: That is not a retreat from the alignment above: a panel narrow enough to
#: reach this tier has already lit its widen marker, and thirteen cells spent
#: on labels at that width would come out of the *values*, which is where a
#: reader is actually looking. Alignment is a full-width virtue; at the
#: compact tier the panel's job is to keep every number whole.
#:
#: **The window is never what gets shed.** It is the clause that stops the pace
#: reading as a measured daily rate -- the panel folds at most 25 events, so
#: without it a reader would take a four-hour extrapolation for a daily burn
#: figure. What goes instead is the label column, the word ``over``, the
#: totals line's ``retired`` and ``of supply``, and the supply line's unit.
COMPACT_WIDTH = (
    SPARK_COLS["compact"] + 1 + _AMOUNT_COLS + len("/day ") + _AGE_COLS
)                                                                        # 26


def burn_points(rows) -> list[tuple[float, float]] | None:
    """``(ts, burned_imd)`` pairs from ``pool4_flow``; ``None`` when unread.

    ``None`` for the whole series and never an empty list on an unread
    payload: an empty series draws a flat baseline, which is the picture of a
    hook that has stopped burning -- a confident wrong answer to a question we
    could not answer at all.

    An empty *list* in, an empty list out: that is the real "we looked and the
    window is quiet" state, and the caller tells the two apart.
    """
    if rows is None:
        return None
    try:
        items = list(rows)
    except TypeError:
        return None
    pairs: list[tuple[float, float]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        ts = as_float(row.get("ts"))
        burned = as_float(row.get("burned_imd"))
        # ``burned is None`` means the leg was not read; dropping the sample
        # leaves a gap. Substituting 0.0 would draw "nothing burned here",
        # which is a claim.
        if ts is None or burned is None:
            continue
        pairs.append((ts, burned))
    pairs.sort(key=lambda pair: pair[0])
    return pairs


def burn_window(points) -> float | None:
    """Seconds spanned by *points*, or ``None`` when fewer than two remain.

    Measured from the rows' own timestamps. This module never reads a clock,
    so a committed capture replays to the same window forever.
    """
    pts = coerce_points(points)
    if len(pts) < 2:
        return None
    span = pts[-1][0] - pts[0][0]
    return span if span > 0 else None


def pace_per_day(points) -> float | None:
    """IMD burned per day over the window *points* spans.

    ``None`` -- never ``0.0`` -- when the window is unusable: fewer than two
    samples, a zero span, or a span under :data:`MIN_PACE_WINDOW_S`. A zero
    pace is a real answer and is returned whenever a usable window genuinely
    contains no burns.
    """
    window = burn_window(points)
    if window is None or window < MIN_PACE_WINDOW_S:
        return None
    total = sum(value for _, value in coerce_points(points))
    return total / window * 86400.0


class SurfPool4UBurn(Vertical):
    """BURN & SUPPLY: the recent-burn sparkline, the pace, and the totals."""

    DEFAULT_CSS = """
    SurfPool4UBurn {
        height: auto;
    }
    SurfPool4UBurn > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfPool4UBurn > .pool4u-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1``: a fit decision compares against
    #: ``self.size.width`` minus two, never ``self.size.width``. The same
    #: number, for the same reason, as ``SurfPool4Hatches``'s.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw payload, not formatted lines, so a resize re-lays it out.
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID,
                     classes=TITLE_CLASS)
        yield Static(Text(""), id=_BODY_ID)

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_flow=None,
        pool4_total_burned=None,
        pool4_burned_supply_pct=None,
        pool4_total_supply=None,
        pool4_network=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        ``pool4_flow`` is shared with RECENT FLOW, which renders the same rows
        as a log. That is reuse of a *key*, not of a widget: the two panels
        answer different questions off one read, and folding a second copy of
        the same events into the payload so this panel could have its own would
        buy nothing and cost a sweep.

        **``pool4_as_of_hhmm`` is accepted and not rendered** (2026-09-12).
        The ``4`` MARKET body prints one ``as of`` marker, on the screen's own
        title row, and no panel repeats it -- see ``_pool4``'s *One clock on
        the `4` body* section for the whole of that decision, and for the one
        panel it does not settle.
        The kwarg stays in the signature because every pool4 panel spells
        every contract key in full (``test_no_pool4_widget_needs_a_kwarg_
        alias``), and dropping it would leave the screen's splat handing it to
        ``**_kwargs`` with nothing recording why.
        """
        self._payload = {
            "flow": pool4_flow,
            "total_burned": pool4_total_burned,
            "burned_supply_pct": pool4_burned_supply_pct,
            "total_supply": pool4_total_supply,
            "network": pool4_network,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``market_title_text``, not ``title_text``: this is the ``4`` body.

        The one difference is that ``MAINNET`` is left unsaid here while the
        ``p`` body's four panels go on printing it -- see
        ``_pool4.QUIET_NETWORK`` for why silence is available for exactly one
        network and for nothing else.
        """
        return market_title_text(
            TITLE, self._payload.get("network"), self._widen, self._text_budget()
        )

    def _is_blank(self) -> bool:
        """True when not one of this panel's inputs has been read."""
        payload = self._payload
        return all(
            payload.get(name) is None
            for name in ("flow", "total_burned", "burned_supply_pct", "total_supply")
        )

    def _spark_cell(self, tier: str) -> str | None:
        """The sparkline and the pace beside it -- the ``burn rate`` value.

        Three states, kept apart: unread (``None`` flow), read-and-empty, and
        a real series. The first two would render the same flat baseline if
        this branched on the point count alone, and they return ``None`` here
        so the caller can paint them as a whole line with no label rather
        than filing a sentence under a column heading.
        """
        points = burn_points(self._payload.get("flow"))
        if points is None or not points:
            return None

        spark = build_sparkline_from_points(points, width=SPARK_COLS[tier])
        pace = pace_per_day(points)
        pace_text = PACE_UNAVAILABLE if pace is None else f"{fmt_compact(pace)}/day"
        window = burn_window(points)
        if window is not None:
            joiner = " over " if tier == "full" else " "
            pace_text = f"{pace_text}{joiner}{fmt_age(window)}"
        gap = "  " if tier == "full" else " "
        return f"{safe_markup(spark)}{gap}[dim]{safe_markup(pace_text)}[/]"

    def _spark_line(self, tier: str) -> str:
        """The ``burn rate`` row, label column included at the full tier.

        The two flow states with no series of their own keep their own
        sentence and lose the label: ``⚠ burn & supply unavailable`` under a
        ``burn rate`` heading would read as a *value*, and the whole point of
        keeping those two apart is that neither is one.
        """
        cell = self._spark_cell(tier)
        if cell is None:
            points = burn_points(self._payload.get("flow"))
            if points is None:
                return f"[yellow]⚠ {safe_markup(UNAVAILABLE_LINE)}[/]"
            return f"[dim]{safe_markup(EMPTY_LINE)}[/]"
        return f"{self._label(ROW_LABELS[0], tier)}{cell}"

    def _label(self, label: str, tier: str) -> str:
        """The padded, dimmed label column -- empty below the full tier.

        Padded **raw and escaped after**: ``pad`` measures terminal cells and
        an escaped ``\\[`` is two characters for one cell, so escaping first
        would misalign the column. ``SurfPool4USignals._content_lines``
        records the same order for the same reason.
        """
        if tier != "full":
            return ""
        return f"[dim]{safe_markup(pad(label, LABEL_COLS))}[/]"

    def _totals_line(self, tier: str) -> str:
        """``retired      26.3K · 0.12% of supply`` -- all-time, not the window.

        Each half of the value degrades on its own: an unread total does not
        take the share with it, because the two come from different reads and
        folding one failure into both would overstate the outage.
        """
        burned = as_float(self._payload.get("total_burned"))
        shown = fmt_compact(burned) if burned is not None else DASH
        pct = as_float(self._payload.get("burned_supply_pct"))
        pct_shown = f"{pct:.2f}%" if pct is not None else DASH
        if tier == "full":
            cell = f"{shown} · {pct_shown} of supply"
        else:
            cell = f"{shown} burned · {pct_shown}"
        return f"{self._label(ROW_LABELS[1], tier)}[dim]{safe_markup(cell)}[/]"

    def _supply_line(self, tier: str) -> str:
        supply = as_float(self._payload.get("total_supply"))
        shown = fmt_compact(supply) if supply is not None else DASH
        if tier == "full":
            cell = f"{shown} IMD"
        else:
            cell = f"sup {shown}"
        return f"{self._label(ROW_LABELS[2], tier)}[dim]{safe_markup(cell)}[/]"

    def _content_lines(self, tier: str) -> list[Text]:
        markup = [
            self._spark_line(tier),
            self._totals_line(tier),
            self._supply_line(tier),
        ]
        return [t for t in (parse_line(m) for m in markup) if t is not None]

    def _render_view(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
            body = self.query_one(f"#{_BODY_ID}", Static)
        except Exception:  # not composed yet
            return

        def paint(*content: Text) -> None:
            """Title into its own ``Static``, content into the body's.

            Two ``Static``s and not one joined ``Text``: the blank row under
            the title is CSS (``margin: 0 0 1 0`` on :data:`TITLE_CLASS`),
            the repo-wide convention every reference dashboard already
            carries. A ``Text("")`` spliced between them would paint the same
            pixels today and would be invisible to the rule that keeps the
            eight other dashboards agreeing with each other.
            """
            title.update(Text(self._title_text(), style="dim"))
            body.update(join_lines(list(content)))

        if not self._payload:
            self._widen = False
            paint()
            return

        if self._is_blank():
            self._widen = False
            paint(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))
            return

        # Measure what was actually built rather than comparing the budget
        # against a constant: the pace and the totals are data-dependent and a
        # marker keyed off ``budget < FULL_WIDTH`` would stay dark while an
        # unusually wide line was being clipped by CSS in silence.
        budget = self._text_budget()
        content = self._content_lines("full")
        if budget and widest_line(content) > budget:
            self._widen = True
            content = self._content_lines("compact")
        else:
            self._widen = False

        paint(*content)
