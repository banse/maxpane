"""Two-row sparkline widget for the Talismans dashboard.

Renders two parallel ASCII sparklines:

* **MYTHIC COUNT**     -- Mythic talisman count over time (violet).
* **DAILY OPERATIONS** -- operation count sampled per day (cyan).

Each input is a list of ``[ts, value]`` lists (or 2-element tuples --
some serializers degrade tuples to lists).  When a series has fewer than
2 samples we render ``"waiting for data..."`` instead of an empty bar, so
the user sees the dashboard is alive but the series isn't ready yet.

Copied from ``ttt_sparkline.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_SPARK_WIDTH = 22
_WAITING = "[dim]waiting for data...[/]"


def _coerce_points(points) -> list[tuple[float, float]]:
    """Normalize input to a list of ``(ts, value)`` floats.

    Tolerates ``None`` entries, malformed shapes, and ``None`` values
    by skipping them.  Returns ``[]`` for any non-iterable input.
    """
    if not points:
        return []
    result: list[tuple[float, float]] = []
    try:
        iterator = list(points)
    except TypeError:
        return []
    for pt in iterator:
        if pt is None:
            continue
        try:
            ts, val = pt[0], pt[1]
        except (IndexError, TypeError, KeyError):
            continue
        if val is None:
            continue
        try:
            result.append((float(ts), float(val)))
        except (TypeError, ValueError):
            continue
    return result


def _build_sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Render a list of floats as a ``width``-wide block sparkline."""
    if not values:
        return _SPARK_CHARS[0] * width
    sample = values[-width:] if len(values) > width else values

    lo = min(sample)
    hi = max(sample)
    span = hi - lo

    chars: list[str] = []
    for v in sample:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    # Left-pad with the lowest block so short series stay right-aligned.
    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])
    return "".join(chars)


def _fmt_count(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "--"


class TalismansSparkline(Vertical):
    """Two stacked sparklines: Mythic count + daily operations."""

    DEFAULT_CSS = """
    TalismansSparkline > .tal-spark-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansSparkline > .tal-spark-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS", classes="tal-spark-title")
        yield Static("", classes="tal-spark-line", id="tal-spark-spacer")
        yield Static(
            _WAITING,
            classes="tal-spark-line",
            id="tal-spark-mythic",
        )
        yield Static(
            _WAITING,
            classes="tal-spark-line",
            id="tal-spark-ops",
        )

    def update_data(
        self,
        mythic_history=None,
        operations_history=None,
        **_kwargs,
    ) -> None:
        """Refresh both rows.

        ``*_history`` may be ``None``, an empty list, or a list of
        ``[ts, value]`` lists / tuples.  Anything shorter than 2 points
        renders the ``waiting for data...`` placeholder.
        """
        # MYTHIC COUNT (violet)
        mythic_widget = self.query_one("#tal-spark-mythic", Static)
        mythic_pts = _coerce_points(mythic_history)
        if len(mythic_pts) < 2:
            mythic_widget.update(f"  [dim]MYTHIC COUNT    [/]  {_WAITING}")
        else:
            spark = _build_sparkline([v for _, v in mythic_pts])
            current = _fmt_count(mythic_pts[-1][1])
            mythic_widget.update(
                f"  [dim]MYTHIC COUNT    [/]  [#8a6fd6]{spark}[/]  "
                f"[bold]{current}[/]"
            )

        # DAILY OPERATIONS (cyan)
        ops_widget = self.query_one("#tal-spark-ops", Static)
        ops_pts = _coerce_points(operations_history)
        if len(ops_pts) < 2:
            ops_widget.update(f"  [dim]DAILY OPERATIONS[/]  {_WAITING}")
        else:
            spark = _build_sparkline([v for _, v in ops_pts])
            current = _fmt_count(ops_pts[-1][1])
            ops_widget.update(
                f"  [dim]DAILY OPERATIONS[/]  [cyan]{spark}[/]  "
                f"[bold]{current}[/]"
            )
