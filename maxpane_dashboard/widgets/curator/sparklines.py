"""Two sparklines for THE LIST: hourly routed volume and cumulative wallets.

Both series are folded from ``Deposited`` logs alone.  That is the whole
point of H2 and it is worth restating where a reader of this file will see
it: ``currentHourTotal()`` legitimately drops to **0** at every hour
boundary while ``lastActiveHour()`` still names the previous bucket (9987.26
→ 51.48 ETH across 2026-08-16 21:58:47 UTC, captured), so a series fed from
the fast tier renders a normal boundary as a 99.5% crash and then *persists*
that zero.  This widget cannot make that mistake itself — it renders what it
is handed — but the copy it renders ("hourly, from logs") is what makes a
wrong series visible to a reader.

The survival bar is labelled
----------------------------

A volume sparkline for this game without the ``5.00 ETH bar`` beside it is a
pretty picture with no meaning: the only thing that matters about an hour's
volume is whether it cleared the hourly threshold, and the sparkline's own
scale is relative to its window.  The bar's value comes from the payload
(``hourly_threshold_eth``, read live off the ``once`` tier) and never from a
literal — CLAUDE.md's rule about documented values, and this one is exactly
the kind that gets quoted in research and then differs on chain.

``None`` and ``[]`` render the *same* state here
------------------------------------------------

Everywhere else in this package the two are different facts and are rendered
differently.  Not here: both mean "there is no history to draw", and a
sparkline has no honest rendering of either — a flat baseline would be a
line the data never justified.  The distinction is not lost, it moves: a
failed log read reaches the reader through the title bar's ``degraded``
groups, which is where a source-level failure belongs.

Sparkline primitives are **imported** from ``widgets/sparkline_common``,
never copied (MEDI-36).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    fmt_eth,
    fmt_eth_compact,
    fmt_points,
)
from maxpane_dashboard.widgets.curator._table import WIDEN_HINT, title_with_hint
from maxpane_dashboard.widgets.markup_safety import visible_len
from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_WIDTH,
    build_sparkline,
    coerce_points,
    trend_arrow,
)

#: Panel title.  The hint is appended, never substituted.
SPARKLINES_TITLE = "TRENDS"

#: Rendered when a series holds fewer than two usable points — no history,
#: from either a dead fold or a game one hour old (see the module docstring).
WAITING = "waiting for data..."

#: Marker appended to the title, naming what the row gave up.  The bar label
#: has one of its own: it used to shed *silently* between 38 and 45 columns —
#: the title stayed a bare ``TRENDS`` while ``· 5.00 ETH bar`` disappeared,
#: which is the one thing this module's docstring says the volume line cannot
#: mean anything without.  Both markers degrade to the bare
#: ``_table.WIDEN_HINT`` when the title bar cannot carry the descriptive form.
WIDEN_BAR = "‹ widen: bar"
WIDEN_VALUE = "‹ widen: bar + value"

#: Row labels, sized to the wider of the two.
_LABELS = ("VOL/h", "WALLETS")
_LABEL_COLS = max(len(label) for label in _LABELS)

#: Narrowest sparkline still worth drawing.  Below this the row drops the
#: bar label and then the trend value rather than drawing four blocks.
_MIN_SPARK = 6

#: Fixed furniture per row: two leading spaces, the label cell, two gaps of
#: two columns, the trend arrow and the space after it.
_ROW_OVERHEAD = 2 + _LABEL_COLS + 2 + 2 + 1 + 1


def _plan(width: int, tails: list[str]) -> tuple[int, bool, bool]:
    """One layout for **both** rows: ``(spark_cols, keep_suffix, keep_value)``.

    The two rows must share a sparkline width or their blocks do not line up
    down the panel, and a row budgeted against its own tail is exactly how
    that goes wrong: the volume row carries ``· 5.00 ETH bar`` and the wallet
    row carries four digits, so budgeting separately gave them 20 and 22
    columns of spark and moved the column between two adjacent lines.  The
    longest tail sets the layout for both.

    Order of sacrifice as the panel narrows: the bar label first (a constant
    a reader learns once), then the spark shrinks to :data:`_MIN_SPARK`, then
    the trend value goes.  The row label never goes — a nameless sparkline is
    decoration.

    Both losses are *announced* by the caller (:data:`WIDEN_BAR` /
    :data:`WIDEN_VALUE`).  "A constant a reader learns once" is a reason to
    shed the label first, never a reason to shed it quietly.
    """
    if width <= 0:
        return SPARK_WIDTH, True, True
    longest = max((visible_len(t) for t in tails), default=0)
    spare = width - _ROW_OVERHEAD - longest
    if spare >= _MIN_SPARK:
        return max(_MIN_SPARK, min(SPARK_WIDTH, spare)), True, True
    # Drop the bar label: recompute against the values alone.
    values_only = max((visible_len(t.split(" · ")[0]) for t in tails), default=0)
    spare = width - _ROW_OVERHEAD - values_only
    if spare >= _MIN_SPARK:
        return max(_MIN_SPARK, min(SPARK_WIDTH, spare)), False, True
    spare = width - _ROW_OVERHEAD
    return max(_MIN_SPARK, min(SPARK_WIDTH, spare)), False, False


def _spark_row(label: str, points, tail: str, spark_cols: int) -> str:
    """One sparkline row at an already-decided width.

    ``pad=False`` is not a detail: ``build_sparkline``'s default left-pads a
    short series with the *lowest block*, so a game four hours old would draw
    eighteen columns of flat floor before its first real bar — a history of
    quiet hours that never happened, on the panel whose whole subject is
    whether an hour was quiet.  Spaces instead.
    """
    pts = coerce_points(points)
    if len(pts) < 2:
        return f"  [dim]{label:<{_LABEL_COLS}}[/]  [dim]{WAITING}[/]"
    spark = build_sparkline([v for _ts, v in pts], width=spark_cols, pad=False)
    row = f"  [dim]{label:<{_LABEL_COLS}}[/]  [cyan]{spark}[/]  {trend_arrow(pts)}"
    if tail:
        row += f" [bold]{tail}[/]"
    return row


class CuratorSparklines(Vertical):
    """Hourly routed volume over the survival bar, and cumulative wallets."""

    DEFAULT_CSS = """
    CuratorSparklines > .curator-spark-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorSparklines > .curator-spark-line {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(
            SPARKLINES_TITLE, classes="curator-spark-title", id="curator-spark-title"
        )
        yield Static("", classes="curator-spark-line", id="curator-spark-spacer")
        yield Static(
            f"[dim]{WAITING}[/]", classes="curator-spark-line", id="curator-spark-volume"
        )
        yield Static(
            f"[dim]{WAITING}[/]", classes="curator-spark-line", id="curator-spark-people"
        )

    def update_data(
        self,
        volume_series=None,
        contributors_series=None,
        hourly_threshold_eth=None,
        **_kwargs,
    ) -> None:
        """Refresh both rows from the two ``CURATOR_SERIES_KEYS`` payloads."""
        self._payload = {
            "volume_series": volume_series,
            "contributors_series": contributors_series,
            "hourly_threshold_eth": hourly_threshold_eth,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render: the sparkline's width is a function of the panel's."""
        if self._payload:
            self._render_view()

    # -- rendering ---------------------------------------------------------

    def _set_marker_fallback(self, placed: bool) -> None:
        """Put the bare marker on the spacer line when the title cannot hold it.

        The three ``DataTable`` panels use their note line for this; this one
        has no note, so the blank line between the title and the two spark
        rows carries it.  Going silent is not an option this codebase allows.
        """
        try:
            spacer = self.query_one("#curator-spark-spacer", Static)
        except Exception:
            return
        spacer.update("" if placed else f"[yellow]{WIDEN_HINT}[/]")

    def _render_view(self) -> None:
        try:
            volume_row = self.query_one("#curator-spark-volume", Static)
            people_row = self.query_one("#curator-spark-people", Static)
            title = self.query_one("#curator-spark-title", Static)
        except Exception:  # not composed yet
            return

        data = self._payload
        width = max(self.content_size.width - 2, 0)

        volume_points = coerce_points(data.get("volume_series"))
        last_volume = (
            f"{fmt_eth_compact(volume_points[-1][1])} ETH" if volume_points else DASH
        )
        bar = fmt_eth(data.get("hourly_threshold_eth"))
        # The bar is the only reason the volume line means anything; it is
        # labelled with the live threshold, never with a remembered "5.00".
        suffix = f" · {bar} ETH bar"

        people_points = coerce_points(data.get("contributors_series"))
        last_people = fmt_points(people_points[-1][1]) if people_points else DASH

        volume_tail = f"{last_volume}{suffix}"
        people_tail = last_people
        spark_cols, keep_suffix, keep_value = _plan(
            width, [volume_tail, people_tail]
        )
        if not keep_value:
            volume_tail = people_tail = ""
        elif not keep_suffix:
            volume_tail = last_volume

        volume_row.update(
            _spark_row(_LABELS[0], data.get("volume_series"), volume_tail, spark_cols)
        )
        people_row.update(
            _spark_row(_LABELS[1], data.get("contributors_series"), people_tail,
                       spark_cols)
        )
        # The marker fires for **either** loss.  A shorter sparkline is still
        # not one — it is a smaller window, not a hidden column, and a marker
        # that is always on says nothing (the fwa_signals trap) — but the bar
        # label and the trend value are columns, and a shed column that is
        # not announced is indistinguishable from data that is not there.
        if not keep_value:
            hint = WIDEN_VALUE
        elif not keep_suffix:
            hint = WIDEN_BAR
        else:
            hint = ""
        text, placed = title_with_hint(SPARKLINES_TITLE, hint, width)
        title.update(text)
        self._set_marker_fallback(placed or not hint)
