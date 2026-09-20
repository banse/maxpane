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

``widgets/ocm/`` and ``widgets/cattown/`` are the worked examples.

Branch 7 (WP-A, 2026-09-20) added :class:`TableLeaderboard` -- deferred out
of Branch 6 because a base with no subclass is a template by another name --
with cattown's leaderboard as its first user, and widened three of the
bases so cattown, dota and (in WP-B) talismans and ttt fit them without a
pixel moving. Every one of those widenings is a **class attribute carrying
the Branch 6 default**, so ocm reads exactly as it did.
"""

from __future__ import annotations

import logging
from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline_from_points,
    coerce_points,
    fmt_compact,
    trend_arrow,
)

__all__ = [
    "UNAVAILABLE",
    "LOADING",
    "LOADING_ROW",
    "UNAVAILABLE_LINE",
    "PanelBase",
    "HeroBoxBase",
    "HeroRow",
    "SignalsPanelBase",
    "SparklinePanel",
    "RichLogFeed",
    "TableLeaderboard",
    "fmt_signal",
]

logger = logging.getLogger(__name__)

#: Shown in place of a value the backend could not supply this poll. Distinct
#: from a value the analytics *did* compute as empty (``--``): a failed read
#: is ``None``, never ``0``, and never a blank cell.
UNAVAILABLE = "[yellow]unavailable[/]"

#: The seed a panel composes with, before its first poll lands.
LOADING = "[dim]Loading...[/]"

#: :data:`LOADING` indented into a signals row's own column -- every signal
#: row starts two spaces in, and the seed sits in the same column as the
#: value it is standing in for. Derived, not re-typed: the two strings drift
#: apart the moment somebody edits one of them.
LOADING_ROW = LOADING.replace("[dim]", "[dim]  ", 1)

#: :data:`UNAVAILABLE` on a feed line of its own, in the same two-space
#: column every feed row starts in. What a **snapshot** feed writes when the
#: manager could not look at all -- distinct from ``EMPTY_LINE``, which is
#: the real negative ("there is nothing"). Derived from :data:`UNAVAILABLE`
#: for the same reason :data:`LOADING_ROW` is derived from :data:`LOADING`.
UNAVAILABLE_LINE = f"  {UNAVAILABLE}"


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

        **And it logs.** Before Branch 6 the two panels that write this way
        (ocm's staking overview and supply breakdown) used a bare
        ``query_one(...).update(...)``, so a missing target raised into
        ``DashboardScreen._do_refresh`` and got a ``warning`` line. Swallowing
        it here without a line would have made a panel that cannot render
        invisible in ``~/.maxpane/maxpane.log``, which is the one place it
        would ever be noticed.
        """
        try:
            self.query_one(selector, Static).update(content)
        except Exception as exc:
            logger.warning(
                "%s: could not write %s: %s", type(self).__name__, selector, exc
            )
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


class HeroBoxBase(Static):
    """One hero metric box: a dim label, a blank row, then the value.

    ``DEFAULT_CSS = ""`` because every dimension a hero box has is the
    theme's (``minimal.tcss`` gives it ``width: 1fr``, a border and the
    padding that makes the box); a widget default here would be a second
    place to look.

    The ``Base`` suffix is not decoration: a base class's **name is a CSS
    type selector for every subclass**, and ``widgets/hero_metrics.py`` (the
    bakery-only one) already owns a class called ``HeroBox`` with a bare
    ``HeroBox { … }`` block in ``minimal.tcss``. Without the suffix that
    bakery block would have styled every hero box in the app.
    """

    DEFAULT_CSS = ""


class HeroRow(Horizontal):
    """A row of hero boxes. **Not** a :class:`PanelBase`: it has no title.

    The blank row between a box's label and its value is the ``\\n\\n``
    inside the box string, not a margin -- the box is one ``Static``.
    """

    #: The box class to compose. A package subclasses :class:`HeroBoxBase`
    #: when the stylesheet names its own class (ocm's ``OCMHeroBox``).
    BOX_CLASS: type[HeroBoxBase] = HeroBoxBase

    #: ``(widget id, label)`` per box, in row order.
    BOXES: tuple[tuple[str, str], ...] = ()

    DEFAULT_CSS = """
    HeroRow > HeroBoxBase {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        for box_id, label in self.BOXES:
            yield self.BOX_CLASS(f"[dim]{label}[/]\n\n{LOADING}", id=box_id)

    def render_box(self, selector: str, label: str,
                   build: Callable[[], "str | Text"]) -> bool:
        """Write one box, degrading to an explicit unavailable state.

        The body is built inside the guard (MEDI-38): a string where a
        number was expected must land on ``unavailable`` here.

        ``build`` may return a **``rich.text.Text``** instead of a markup
        string, and then the head is parsed rather than interpolated:
        ``Text.from_markup(f"[dim]{label}[/]\\n\\n") + body``. cattown's
        LEADER box is why (Branch 7) -- it carries an address through
        ``widgets/address.py``, whose copy icon lives in a ``Style`` with a
        click ``meta`` that only survives outside markup parsing, so
        interpolating that body into an f-string would flatten the icon into
        inert text. The ``str`` path is untouched.
        """
        try:
            box = self.query_one(selector, HeroBoxBase)
        except Exception:
            return False
        try:
            body = build()
            if isinstance(body, Text):
                box.update(Text.from_markup(f"[dim]{label}[/]\n\n") + body)
            else:
                box.update(f"[dim]{label}[/]\n\n{body}")
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{UNAVAILABLE}")
            except Exception:
                return False
        return True


def fmt_signal(sig: dict, *, label_width: int, dim_label: bool,
               labelled: bool = True) -> str:
    """Format one signal row: indicator, optional label, coloured value.

    The spellings the eight copies differed on: ``label_width=18,
    dim_label=False`` is ocm's and dota's, ``label_width=15,
    dim_label=True`` is cattown's and ``templates/signals_template.py``'s,
    and ``labelled=False`` is talismans' and ttt's ``  [c]●[/] [c]{value}[/]``
    -- a row whose *value string already says what it is*, so a label column
    would only repeat it (Branch 7).

    **``value_str`` is escaped** (``markup_safety.safe_markup``). A signal
    value is analytics output today, but analytics reads token symbols, and
    a symbol is attacker-controlled: anyone can deploy an ERC-20 called
    ``[/x]``. Textual defers ``Text.from_markup`` into the message pump, so
    an unescaped one raises *outside* the panel's guard and kills the app.
    ttt already escaped here and talismans did not -- one copy fixed, seven
    not, which is the divergence this module exists to end.
    """
    label = sig.get("label", "")
    value = safe_markup(sig.get("value_str", ""))
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "●")
    if not labelled:
        return f"  [{color}]{indicator}[/] [{color}]{value}[/]"
    cell = f"{label:<{label_width}}"
    if dim_label:
        cell = f"[dim]{cell}[/]"
    return f"  [{color}]{indicator}[/] {cell} [{color}]{value}[/]"


class SignalsPanelBase(PanelBase):
    """A signals panel: one row per signal, optionally a recommendation.

    Every row is written on every poll (MEDI-38): a signal the manager could
    not compute arrives as ``None`` and renders an explicit ``unavailable``
    marker beside its label -- distinct from a signal whose own
    ``value_str`` is ``--``, which is the analytics saying "nothing to
    report".

    ``Base`` suffix: see :class:`HeroBoxBase`. ``widgets/signals_panel.py``
    (bakery-only) owns a class called ``SignalsPanel`` with a bare
    ``SignalsPanel { height: 1fr; … }`` block in ``minimal.tcss``, which
    would otherwise have reached every signals panel in the app.
    """

    #: One item per row, in panel order:
    #:
    #: * ``(widget id, label)`` -- a labelled row;
    #: * ``(widget id, None)`` -- a **label-less** row, whose value string
    #:   already says what it is (talismans, ttt);
    #: * ``None`` -- a blank ``.panel-line`` **separator** between two groups
    #:   of rows. Not the title's blank row, which is ``PanelBase``'s margin.
    ROWS: tuple = ()

    #: Label column width. 18 in ocm/dota, 15 in cattown/the template.
    LABEL_WIDTH: int = 18

    #: Wrap the label cell in ``[dim]``. cattown and the template do.
    DIM_LABEL: bool = False

    #: Widget id of the centred recommendation line; ``None`` for a panel
    #: that has none.
    RECOMMENDATION_ID: str | None = None

    DEFAULT_CSS = """
    SignalsPanelBase > .panel-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose_body(self) -> ComposeResult:
        seeded = False
        for row in self.ROWS:
            if row is None:
                # A separator between two groups of rows. It carries no id:
                # nothing writes to it, and an id would invite something to.
                yield Static("", classes="panel-line")
                continue
            row_id, _label = row
            # The first *row* carries the seed; the rest start empty so a
            # panel that has never polled does not claim three rows of
            # nothing. "First row", not "index 0": a panel whose ``ROWS``
            # opens with a separator would otherwise seed nothing at all.
            seed = "" if seeded else LOADING_ROW
            seeded = True
            yield Static(seed, classes="panel-line", id=row_id)
        if self.RECOMMENDATION_ID is not None:
            # Not the title's blank row: this one separates the rows from the
            # recommendation, and the template keeps it too.
            yield Static("", classes="panel-line")
            yield Static("", classes="panel-rec", id=self.RECOMMENDATION_ID)

    def render_signal(self, selector: str, label, sig, *,
                      labelled: bool = True) -> bool:
        """Write one signal row. ``None``, ``{}`` or a non-dict says so.

        ``labelled=False`` is the talismans/ttt row whose value already
        names itself; its *label* is then only the word the degraded row
        falls back to, and the panel's ``ROWS`` entry carries ``None``.
        """

        def build() -> str:
            source = sig if isinstance(sig, dict) and sig else {
                "label": label, "value_str": "unavailable", "color": "yellow",
            }
            return fmt_signal(
                source, label_width=self.LABEL_WIDTH, dim_label=self.DIM_LABEL,
                labelled=labelled,
            )

        fallback = (
            f"  [yellow]●[/] {label} {UNAVAILABLE}" if labelled
            else f"  [yellow]●[/] {UNAVAILABLE}"
        )
        return self.write_guarded(selector, build, fallback)

    def render_recommendation(self, text: str | None) -> bool:
        """Write the recommendation line, or blank it when there is none.

        *text* is escaped: a recommendation is assembled in ``analytics/``
        out of names the chain and the game API supplied -- dota's names the
        winning faction, cattown's a species -- and an unescaped ``[/x]`` in
        one of them makes ``Static.update`` raise ``MarkupError``
        synchronously (Textual 8.1.1), which :meth:`PanelBase.write` catches
        and logs: the line silently vanishes rather than rendering (review
        M5, wording corrected in re-review N3). A plain recommendation is
        unaffected; the ``[bold]`` around it is this panel's own markup.
        """
        if self.RECOMMENDATION_ID is None:
            return False
        return self.write(
            f"#{self.RECOMMENDATION_ID}",
            f"  [bold]-> {safe_markup(text)}[/]" if text else "",
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

    #: Label column width. 8 in ocm and cattown, 9 in dota, 16 in talismans
    #: and 12 in ttt -- each measured against its own panel, so the base
    #: states the majority and every other panel says so in one line.
    LABEL_WIDTH: int = 8

    #: Append the trend arrow after the value. talismans and ttt draw none.
    SHOW_ARROW: bool = True

    #: What an unusable series writes. ``""`` -- never a flat baseline,
    #: which would read as a real run of zeroes. talismans and ttt say
    #: ``waiting for data...`` instead, which is the same claim in words.
    EMPTY_TEXT: str = ""

    def compose_body(self) -> ComposeResult:
        for index, line_id in enumerate(self.LINE_IDS):
            # A panel with an EMPTY_TEXT seeds *that*: its "nothing yet" and
            # its "nothing usable" are the same sentence, and seeding
            # ``Loading...`` under it would be a second word for one state.
            yield Static(
                (self.EMPTY_TEXT or LOADING) if index == 0 else "",
                classes="panel-line",
                id=line_id,
            )

    def fmt_value(self, value, unit: str) -> str:
        """The current value's cell. ``sparkline_common.fmt_compact``.

        The hook exists because three subscribers' formatters differ from
        ``fmt_compact`` **on values their own panel actually shows** -- dota's
        frontline positions (``abs >= 100`` -> no decimal, and no K/M/B at
        all), talismans' grouped integers, ttt's ``$…B`` at two places. A
        hoist that changed those digits would be a pixel change wearing a
        refactor's clothes. ``unit`` is passed so one override can switch on
        which line it is drawing.
        """
        return fmt_compact(value, unit)

    def render_series(self, series) -> None:
        """Draw ``(label, points, color, unit)`` tuples in line order.

        An empty or unusable series writes :attr:`EMPTY_TEXT` -- never a
        flat baseline that would read as a real run of zeroes.
        """
        for line_id, entry in zip(self.LINE_IDS, series):
            selector = f"#{line_id}"
            try:
                label, points, color, unit = entry
            except Exception:
                self.write(selector, self.EMPTY_TEXT)
                continue
            pts = coerce_points(points)
            if not pts:
                self.write(selector, self.EMPTY_TEXT)
                continue
            sparkline = build_sparkline_from_points(pts)
            current = self.fmt_value(pts[-1][1], unit)
            width = self.LABEL_WIDTH
            cell = f"{str(label)[:width]:<{width}}"
            row = (
                f"  [dim]{cell}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current}[/]"
            )
            if self.SHOW_ARROW:
                row = f"{row} {trend_arrow(pts)}"
            self.write(selector, row)


class RichLogFeed(PanelBase):
    """A ``RichLog`` activity feed, newest on top.

    Two hooks: :meth:`dedupe_key` (what makes two polls' events the same
    event) and :meth:`format_row` (abstract). ``format_row`` returns a
    ``rich.text.Text``, never a markup string -- the address copy icon's
    click action lives in a ``Style`` that only survives outside markup
    parsing, and ``Static``/``RichLog`` defer markup parsing into the
    message pump where this widget's ``try`` cannot reach it.

    **Two modes, and the difference is what a poll means.**

    A **stream** (:attr:`SNAPSHOT` ``False``, the default) is a log of events
    that happened: ocm's mints, cattown's catches, fwa's pulls. A poll that
    brings nothing adds nothing, and the rows already on screen are still
    true -- so a transient empty poll leaves them alone, and the placeholder
    is written only while nothing has ever been drawn.

    A **snapshot** (:attr:`SNAPSHOT` ``True``) is the current state of
    something: dota's hero roster, where every row carries an HP and an
    ALIVE/DEAD flag that is only true of the poll it came from. It re-paints
    the whole panel every poll and **never** keeps a row from a previous one,
    because a kept row is a stale number presented as live. That makes the
    two falsy inputs different facts rather than one: ``None`` is "the read
    failed, I could not look" and writes :data:`UNAVAILABLE_LINE`; ``[]`` is
    the real negative, "there is nothing", and writes :attr:`EMPTY_LINE`. A
    manager that serves ``[]`` for a failed read defeats this and is the bug,
    not the panel (review C1: ``data/dota_manager.py`` did exactly that).
    """

    #: Widget id of the log.
    LOG_ID: str = ""

    #: Shown while the feed has nothing to show. In snapshot mode this is
    #: specifically the *real negative* -- see the class docstring.
    EMPTY_LINE = "[dim]  No activity yet[/]"

    #: ``False`` = a stream of events (the Branch 6 contract, unchanged);
    #: ``True`` = a snapshot of current state. See the class docstring.
    SNAPSHOT: bool = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()
        #: Has a row ever reached the log? The "do not wipe a populated feed"
        #: contract hangs off this and **not** off ``_seen_keys``, which only
        #: fills on the hashable-key path: a feed whose ``dedupe_key`` returns
        #: ``None`` (always new) or whose keys arrive unhashable draws rows
        #: while the key set stays empty, and keying the contract on the set
        #: wiped exactly those feeds on the next empty poll.
        self._drawn = False

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

        In **snapshot** mode (:attr:`SNAPSHOT`) the first bullet is replaced:
        a ``None`` poll clears and writes :data:`UNAVAILABLE_LINE`, an empty
        list clears and writes :attr:`EMPTY_LINE`, and a non-empty list
        re-paints -- the dedupe guard is skipped entirely, so no row ever
        survives a poll. The rest of this contract is the **stream** mode
        that every other feed in the repo uses:

        * an empty poll writes the placeholder **only while nothing has ever
          been shown** -- a transient empty poll must not wipe a populated
          feed -- and ``clear()``s first, so the placeholder is written once
          rather than once per refresh interval (ocm appended another copy
          every poll). "Ever been shown" is ``self._drawn``, set when a row
          lands, *not* ``self._seen_keys``: a key-less feed (``dedupe_key``
          returning ``None``, or an unhashable key) draws rows without ever
          filling the key set, and keying the contract on the set blanked
          those feeds on the next empty poll;
        * every key is recorded, and when nothing is new and something is
          already drawn the log is left alone (ocm's flicker guard). With
          ``dedupe_key`` returning ``None`` every event is new, so the guard
          never applies and every poll redraws -- that is what always-new
          means;
        * otherwise the log is cleared and every row is written inside its
          own guard: one unwritable row is skipped and the rest still land,
          because nothing may escape after ``clear()``.
        """
        try:
            log = self.query_one(f"#{self.LOG_ID}", RichLog)
        except Exception:
            return

        if not events:
            if self.SNAPSHOT:
                # Two different facts, and a reader must be able to tell them
                # apart: ``None`` could not look, ``[]`` looked and found
                # nothing. Both clear, because a snapshot never keeps a row.
                log.clear()
                log.write(
                    UNAVAILABLE_LINE if events is None else self.EMPTY_LINE
                )
                self._drawn = False
                return
            if not self._drawn:
                log.clear()
                log.write(self.EMPTY_LINE)
            return

        # Snapshot mode skips the dedupe guard outright: every poll is the
        # whole state, so "nothing is new" is not a reason to leave last
        # poll's rows up -- it is a reason to paint the same state again.
        if not self.SNAPSHOT:
            has_new = False
            for event in events:
                try:
                    key = self.dedupe_key(event)
                except Exception:
                    # Not even a key. The event may still render;
                    # ``format_row``'s own guard decides. Not counted as new,
                    # so an all-malformed poll leaves a populated feed alone.
                    continue
                if key is None:
                    has_new = True
                    continue
                try:
                    seen = key in self._seen_keys
                except TypeError:
                    # A third-party payload can hand us an unhashable
                    # ``tx_hash`` (a JSON list). It cannot be deduped, so it
                    # is always new -- and the membership test must not raise
                    # out of ``update_data`` and blank the whole feed.
                    has_new = True
                    continue
                if seen:
                    continue
                self._seen_keys.add(key)
                has_new = True

            if not has_new and self._drawn:
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
            except NotImplementedError:
                # A subclass that never implemented the hook is a programming
                # error, not a bad row: it must fail loudly rather than paint
                # "No activity yet" forever.
                raise
            except Exception:
                continue
            written += 1

        if written == 0:
            # Rows arrived and none could be shown. A stream with nothing
            # drawn says "no activity yet"; a snapshot may not -- the read
            # succeeded and returned a state, so "there is nothing" is a
            # false negative. It says it could not show the state instead
            # (re-review N1).
            log.write(UNAVAILABLE_LINE if self.SNAPSHOT else self.EMPTY_LINE)
        else:
            self._drawn = True

        self.call_after_refresh(log.scroll_home, animate=False)


class TableLeaderboard(PanelBase):
    """A title over a ``DataTable``: the eighth copy of one shape.

    Branch 7. ``CTLeaderboard``, ``DOTALeaderboard``, ``TalismansLeaderboard``,
    ``TalismansMaterialsTable``, ``TalismansMatrixTable``, ``TTTLeaderboard``,
    ``TTTFeesTable`` and ``TTTClaimsTable`` had each hand-written the same
    five steps -- ``cursor_type="row"``, ``zebra_stripes=True``, the columns,
    an optional ``Loading...`` seed row, and then ``clear()`` followed by
    either a "No data" row or a capped slice. They agreed on all five and
    differed only in the numbers, which is what a base class is for.

    **The base owns mechanics, never a cell's formatting.** Address cells,
    rank-1 bolding, the symbol column's measured width, a dict payload and a
    "Today" stamp stay in :meth:`build_row`, where the dashboard that knows
    what they mean can see them.

    :class:`TableLeaderboard`, not ``Leaderboard``: ``widgets/leaderboard.py``
    (bakery-only) owns that name and has a **bare** block in
    ``minimal.tcss``, and a base class's name is a CSS type selector for
    every subclass (Branch 6, fix round 1 I1 -- the two guard tests in
    ``tests/widgets/test_panels.py`` enforce it).
    """

    #: Widget id of the table.
    TABLE_ID: str = ""

    #: ``(label, width)`` per column, in table order.
    COLUMNS: tuple[tuple[str, int], ...] = ()

    #: ``DataTable.cursor_type``. All eight tables select a whole row.
    CURSOR_TYPE: str = "row"

    #: ``DataTable.zebra_stripes``.
    ZEBRA: bool = True

    #: How many items to draw; ``None`` draws every one. 10 / 20 / 12 / 6
    #: across the eight, each a measurement of its own panel's height.
    ROW_CAP: int | None = 10

    #: A seed row shown from ``on_mount`` until the first poll lands, or
    #: ``None`` for a table that starts empty. The **whole tuple**, because
    #: which cell says ``Loading...`` differs per table and a base that
    #: guessed the column would put the word under the wrong heading.
    LOADING_ROW: tuple[str, ...] | None = None

    #: The row a ``None`` or empty payload paints -- an explicit "nothing to
    #: show", never a silently empty table, which reads as a panel that has
    #: not polled yet.
    EMPTY_ROW: tuple[str, ...] = ()

    def compose_body(self) -> ComposeResult:
        yield DataTable(id=self.TABLE_ID)

    def on_mount(self) -> None:
        """Columns, then the seed row -- after checking both row tuples fit.

        A tuple of the wrong width is a **programming error in the
        subclass**, so it fails here, loudly, at mount, naming the class:
        ``DataTable.add_row`` raises on a surplus cell but pads a short one
        in silence, and :attr:`EMPTY_ROW` is added on the one path
        :meth:`render_table` reaches when there is nothing else to show --
        a wrong tuple there means the *degraded* state is the one that
        paints nothing, which is exactly when nobody is looking closely
        (review M2). Checking at mount makes it a red test rather than an
        empty panel in production.
        """
        table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        table.cursor_type = self.CURSOR_TYPE
        table.zebra_stripes = self.ZEBRA
        for label, width in self.COLUMNS:
            table.add_column(label, width=width)

        name = type(self).__name__
        width = len(self.COLUMNS)
        if self.EMPTY_ROW and len(self.EMPTY_ROW) != width:
            raise TypeError(
                f"{name}.EMPTY_ROW has {len(self.EMPTY_ROW)} cells for "
                f"{width} columns"
            )
        if self.LOADING_ROW is not None:
            if len(self.LOADING_ROW) != width:
                raise TypeError(
                    f"{name}.LOADING_ROW has {len(self.LOADING_ROW)} cells "
                    f"for {width} columns"
                )
            table.add_row(*self.LOADING_ROW)

    # -- hook -------------------------------------------------------------

    def build_row(self, index: int, item) -> tuple | None:
        """The cells for one item, or ``None`` to skip it.

        ``index`` is the item's position in the **capped** slice, which is
        what a subclass needs to bold its first row. Returning ``None`` is
        the non-dict guard talismans and ttt carry: a payload entry that is
        not the shape this table reads is dropped, not rendered as junk.
        """
        raise NotImplementedError

    # -- rendering --------------------------------------------------------

    def render_table(self, rows, *, footer=None) -> None:
        """Clear and repopulate the table.

        ``None`` or empty paints :attr:`EMPTY_ROW`; otherwise the capped
        slice goes through :meth:`build_row`, then the optional *footer*
        tuple (the matrix table's bold TOTAL line) lands last.

        **Every row is built and added inside its own guard.** One item the
        formatter cannot read is one missing line; without the guard the
        exception escapes after ``clear()`` and the table is left *empty*,
        which is worse than the row it could not draw and, on a leaderboard,
        reads as "nobody is playing". ``NotImplementedError`` is re-raised
        past it, as in :class:`RichLogFeed`: a subclass that never wired up
        :meth:`build_row` is a programming error and must fail loudly.
        """
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:
            logger.warning(
                "%s: could not find %s", type(self).__name__, self.TABLE_ID
            )
            return

        table.clear()

        if not rows:
            if self.EMPTY_ROW:
                table.add_row(*self.EMPTY_ROW)
            return

        capped = rows if self.ROW_CAP is None else rows[: self.ROW_CAP]
        for index, item in enumerate(capped):
            try:
                cells = self.build_row(index, item)
                if cells is None:
                    continue
                table.add_row(*cells)
            except NotImplementedError:
                raise
            except Exception as exc:
                # Logged, never silent: a panel that cannot render a row is
                # worth a line in ``~/.maxpane/maxpane.log``, the same
                # reasoning as ``PanelBase.write`` (review M1).
                logger.warning(
                    "%s: row %d skipped: %s", type(self).__name__, index, exc
                )
                continue

        if footer is not None:
            try:
                table.add_row(*footer)
            except Exception:
                logger.warning("%s: could not add the footer row",
                               type(self).__name__)
