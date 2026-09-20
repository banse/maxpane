"""The shared panel bases -- **subclass these, do not copy them** (HANDOVER §3.4).

Branch 6 of the refactor programme. Five shapes were hand-copied into every
dashboard package in this repo, and a fix applied to one copy reached none of
the others:

* ``_UNAVAILABLE = "[yellow]unavailable[/]"`` -- nine copies across
  ``widgets/`` and ``templates/``; ``UNAVAILABLE`` below is the one.
* ``Loading...`` -- typed in 68 files; ``LOADING`` below is the one.
* ``_render_row`` (seven copies) and ``_render_box`` (four) -- the same
  query-guard / build-inside-the-guard / fallback shape, hoisted here as
  :meth:`PanelBase.write_guarded` and :meth:`HeroRow.render_box`. Building
  the body *inside* the guard is the MEDI-38 rule: a malformed value must
  land on ``unavailable`` here, not raise into the screen's ``except`` and
  leave the previous poll's number on screen as if it were live.
* ``_fmt(sig)`` / ``_fmt_signal(sig)`` -- eight copies differing only in the
  label width (18 in ocm and dota, 15 and ``[dim]``-wrapped in cattown and
  the template); :func:`fmt_signal` takes both as keywords.
* ``_fmt_value`` -- three copies; ``sparkline_common.fmt_compact`` is the
  hoisted form and :class:`SparklinePanel` calls it.
* ``_format_event_time`` -- five copies; ``widgets/fmt.hhmm`` is the hoisted
  form and a feed's ``format_row`` calls it.
* a ``_seen_tx_hashes`` / ``_seen_keys`` dedupe set -- ten copies;
  :class:`RichLogFeed` owns one and exposes ``dedupe_key`` as the hook.

**The blank row under a title is this module's ``margin: 0 0 1 0``.** Two
mechanisms used to paint it -- a ``Static("")`` spacer yielded from
``compose``, or the margin stated on a per-panel title class -- and ocm's
staking overview had *both*, so it painted two. A subclass yields no spacer
for it. ``tests/widgets/test_title_blank_row.py`` is the contract.

**Textual matches a type selector against every base class**, so
``PanelBase > .panel-title`` in this module's ``DEFAULT_CSS`` reaches every
subclass (``_css_type_names`` of an ``OCMSignals(PanelBase)`` instance is
``{OCMSignals, PanelBase, Vertical, Widget, DOMNode}``). The per-panel title
classes each dashboard invented are therefore unnecessary, and being
unnecessary is how ``TTTSparkline > .chart-title`` matched nothing for the
life of ``minimal.tcss``.

``widgets/ocm/`` is the worked example. ``TableLeaderboard`` is deliberately
absent: it arrives in Branch 7 with its first subscriber, because a base
with no subclass is a template by another name, and ``templates/`` is what
this module exists to stop.
"""

from __future__ import annotations

from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline_from_points,
    coerce_points,
    fmt_compact,
    trend_arrow,
)

__all__ = [
    "UNAVAILABLE",
    "LOADING",
    "PanelBase",
    "HeroBox",
    "HeroRow",
    "SignalsPanel",
    "SparklinePanel",
    "RichLogFeed",
    "fmt_signal",
]

#: Shown in place of a value the backend could not supply this poll. Distinct
#: from a value the analytics *did* compute as empty (``--``): a failed read
#: is ``None``, never ``0``, and never a blank cell.
UNAVAILABLE = "[yellow]unavailable[/]"

#: The seed a panel composes with, before its first poll lands.
LOADING = "[dim]Loading...[/]"


class PanelBase(Vertical):
    """A titled panel: one title row, one blank row, then the body.

    A subclass sets :attr:`TITLE` and implements :meth:`compose_body`; it
    never yields the title itself and never yields a spacer for the blank
    row (see the module docstring).
    """

    #: The title row's words.
    TITLE: str = ""

    DEFAULT_CSS = """
    PanelBase > .panel-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
        margin: 0 0 1 0;
    }
    PanelBase > .panel-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="panel-title")
        yield from self.compose_body()

    def compose_body(self) -> ComposeResult:
        """The panel's own widgets, under the title and its blank row."""
        return iter(())

    # -- writing ----------------------------------------------------------

    def write(self, selector: str, content) -> bool:
        """Write *content* into the ``Static`` at *selector*; report success.

        The guard is the widget's, not the screen's: a panel whose target is
        missing degrades to writing nothing rather than raising into the
        screen's ``except``, which would silently keep the previous poll's
        contents on screen as if they were live.
        """
        try:
            self.query_one(selector, Static).update(content)
        except Exception:
            return False
        return True

    def write_guarded(self, selector: str, build: Callable[[], object],
                      fallback) -> bool:
        """Build *inside* the guard and write *fallback* when it raises.

        The shape every ``_render_row`` in the tree had. ``build`` is called
        only after the target resolves, and a malformed value lands on
        *fallback* -- an explicit degraded state -- instead of escaping.
        """
        try:
            widget = self.query_one(selector, Static)
        except Exception:
            return False
        try:
            widget.update(build())
        except Exception:
            try:
                widget.update(fallback)
            except Exception:
                return False
        return True


class HeroBox(Static):
    """One hero metric box: a dim label, a blank row, then the value.

    ``DEFAULT_CSS = ""`` because every dimension a hero box has is the
    theme's (``minimal.tcss`` gives it ``width: 1fr``, a border and the
    padding that makes the box); a widget default here would be a second
    place to look.
    """

    DEFAULT_CSS = ""


class HeroRow(Horizontal):
    """A row of hero boxes. **Not** a :class:`PanelBase`: it has no title.

    The blank row between a box's label and its value is the ``\\n\\n``
    inside the box string, not a margin -- the box is one ``Static``.
    """

    #: The box class to compose. A package subclasses :class:`HeroBox` when
    #: the stylesheet names its own class (ocm's ``OCMHeroBox``).
    BOX_CLASS: type[HeroBox] = HeroBox

    #: ``(widget id, label)`` per box, in row order.
    BOXES: tuple[tuple[str, str], ...] = ()

    DEFAULT_CSS = """
    HeroRow > HeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        for box_id, label in self.BOXES:
            yield self.BOX_CLASS(f"[dim]{label}[/]\n\n{LOADING}", id=box_id)

    def render_box(self, selector: str, label: str,
                   build: Callable[[], str]) -> bool:
        """Write one box, degrading to an explicit unavailable state.

        The body is built inside the guard (MEDI-38): a string where a
        number was expected must land on ``unavailable`` here.
        """
        try:
            box = self.query_one(selector, HeroBox)
        except Exception:
            return False
        try:
            box.update(f"[dim]{label}[/]\n\n{build()}")
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{UNAVAILABLE}")
            except Exception:
                return False
        return True


def fmt_signal(sig: dict, *, label_width: int, dim_label: bool) -> str:
    """Format one signal row: indicator, label, coloured value.

    The two spellings the eight copies differed on: ``label_width=18,
    dim_label=False`` is ocm's and dota's, ``label_width=15,
    dim_label=True`` is cattown's and ``templates/signals_template.py``'s.
    """
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "●")
    cell = f"{label:<{label_width}}"
    if dim_label:
        cell = f"[dim]{cell}[/]"
    return f"  [{color}]{indicator}[/] {cell} [{color}]{value}[/]"


class SignalsPanel(PanelBase):
    """A signals panel: one row per signal, optionally a recommendation.

    Every row is written on every poll (MEDI-38): a signal the manager could
    not compute arrives as ``None`` and renders an explicit ``unavailable``
    marker beside its label -- distinct from a signal whose own
    ``value_str`` is ``--``, which is the analytics saying "nothing to
    report".
    """

    #: ``(widget id, label)`` per row, in panel order.
    ROWS: tuple[tuple[str, str], ...] = ()

    #: Label column width. 18 in ocm/dota, 15 in cattown/the template.
    LABEL_WIDTH: int = 18

    #: Wrap the label cell in ``[dim]``. cattown and the template do.
    DIM_LABEL: bool = False

    #: Widget id of the centred recommendation line; ``None`` for a panel
    #: that has none.
    RECOMMENDATION_ID: str | None = None

    DEFAULT_CSS = """
    SignalsPanel > .panel-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose_body(self) -> ComposeResult:
        for index, (row_id, _label) in enumerate(self.ROWS):
            # The first row carries the seed; the rest start empty so a panel
            # that has never polled does not claim three rows of nothing.
            # Two leading spaces inside the markup: every signal row is
            # indented by two, and this row sits in the same column.
            seed = "[dim]  Loading...[/]" if index == 0 else ""
            yield Static(seed, classes="panel-line", id=row_id)
        if self.RECOMMENDATION_ID is not None:
            # Not the title's blank row: this one separates the rows from the
            # recommendation, and the template keeps it too.
            yield Static("", classes="panel-line")
            yield Static("", classes="panel-rec", id=self.RECOMMENDATION_ID)

    def render_signal(self, selector: str, label: str, sig) -> bool:
        """Write one signal row. ``None``, ``{}`` or a non-dict says so."""

        def build() -> str:
            source = sig if isinstance(sig, dict) and sig else {
                "label": label, "value_str": "unavailable", "color": "yellow",
            }
            return fmt_signal(
                source, label_width=self.LABEL_WIDTH, dim_label=self.DIM_LABEL
            )

        return self.write_guarded(
            selector, build, f"  [yellow]●[/] {label} {UNAVAILABLE}"
        )

    def render_recommendation(self, text: str | None) -> bool:
        """Write the recommendation line, or blank it when there is none."""
        if self.RECOMMENDATION_ID is None:
            return False
        return self.write(
            f"#{self.RECOMMENDATION_ID}",
            f"  [bold]-> {text}[/]" if text else "",
        )


class SparklinePanel(PanelBase):
    """One block sparkline per line, with its current value and trend arrow.

    The primitives come from ``widgets/sparkline_common`` (MEDI-36): this
    loop was carried by ocm, cattown, dota and
    ``templates/sparkline_template.py``, and the older copies raised
    ``TypeError`` on a ``None`` entry in a cached history.
    """

    #: Widget id per line, in panel order.
    LINE_IDS: tuple[str, ...] = ()

    def compose_body(self) -> ComposeResult:
        for index, line_id in enumerate(self.LINE_IDS):
            yield Static(
                LOADING if index == 0 else "", classes="panel-line", id=line_id
            )

    def render_series(self, series) -> None:
        """Draw ``(label, points, color, unit)`` tuples in line order.

        An empty or unusable series writes ``""`` -- never a flat baseline
        that would read as a real run of zeroes.
        """
        for line_id, entry in zip(self.LINE_IDS, series):
            selector = f"#{line_id}"
            try:
                label, points, color, unit = entry
            except Exception:
                self.write(selector, "")
                continue
            pts = coerce_points(points)
            if not pts:
                self.write(selector, "")
                continue
            sparkline = build_sparkline_from_points(pts)
            current = fmt_compact(pts[-1][1], unit)
            arrow = trend_arrow(pts)
            cell = f"{str(label)[:8]:<8}"
            self.write(
                selector,
                f"  [dim]{cell}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current}[/] {arrow}",
            )


class RichLogFeed(PanelBase):
    """A ``RichLog`` activity feed, newest on top.

    Two hooks: :meth:`dedupe_key` (what makes two polls' events the same
    event) and :meth:`format_row` (abstract). ``format_row`` returns a
    ``rich.text.Text``, never a markup string -- the address copy icon's
    click action lives in a ``Style`` that only survives outside markup
    parsing, and ``Static``/``RichLog`` defer markup parsing into the
    message pump where this widget's ``try`` cannot reach it.
    """

    #: Widget id of the log.
    LOG_ID: str = ""

    #: Shown while the feed has nothing to show.
    EMPTY_LINE = "[dim]  No activity yet[/]"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose_body(self) -> ComposeResult:
        yield RichLog(id=self.LOG_ID, wrap=True, highlight=True, markup=True)

    # -- hooks ------------------------------------------------------------

    def dedupe_key(self, event: dict) -> str | None:
        """What makes two polls' events the same event; ``None`` = always new.

        The default is the transaction hash, which is what ocm, fwa and the
        shared bakery feed all keyed on.
        """
        return event.get("tx_hash") or None

    def format_row(self, event: dict) -> Text | None:
        """One composited line, or ``None`` to skip this event."""
        raise NotImplementedError

    # -- rendering --------------------------------------------------------

    def render_events(self, events) -> None:
        """Rewrite the log with the given events, newest on top.

        The merged contract of ``templates/activity_feed_template.py`` and
        ocm's own feed:

        * an empty poll writes the placeholder **only while nothing has ever
          been shown** -- a transient empty poll must not wipe a populated
          feed -- and ``clear()``s first, so the placeholder is written once
          rather than once per refresh interval (ocm appended another copy
          every poll);
        * every key is recorded, and when nothing is new and something is
          already shown the log is left alone (ocm's flicker guard);
        * otherwise the log is cleared and every row is written inside its
          own guard: one unwritable row is skipped and the rest still land,
          because nothing may escape after ``clear()``.
        """
        try:
            log = self.query_one(f"#{self.LOG_ID}", RichLog)
        except Exception:
            return

        if not events:
            if not self._seen_keys:
                log.clear()
                log.write(self.EMPTY_LINE)
            return

        has_new = False
        for event in events:
            try:
                key = self.dedupe_key(event)
            except Exception:
                continue
            if key is None:
                has_new = True
                continue
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            has_new = True

        if not has_new and self._seen_keys:
            return

        log.clear()
        log.auto_scroll = False
        written = 0
        for event in events:
            try:
                row = self.format_row(event)
                if row is None:
                    continue
                log.write(row)
            except Exception:
                continue
            written += 1

        if written == 0:
            log.write(self.EMPTY_LINE)

        self.call_after_refresh(log.scroll_home, animate=False)
