"""THROUGHPUT -- how fast work moves through the swarm (swarm v2, WP5).

A ``panels.SignalsPanelBase`` reading the plan §1.3 ``swarm_throughput``
dict **only**::

    { window_start_ts, window_end_ts, window_n,          # what /jobs returned
      states: [{state, count}],                          # open vocabulary
      dur_median_s, dur_p90_s, dur_max_s,                # None under 2 samples
      cancel_reasons: [{reason, count}],                 # verbatim, open
      completed_24h, seen_since_ts }                     # None while accumulating

**Transitional names, unwired until WP7.** The live screen still mounts the
old ``swarm_throughput.SurfSwarmThroughput``; this module is
``swarm_throughput_v2`` / ``SurfSwarmThroughputV2`` so both exist in one
tree while WP6/WP6a write beside it. WP7 deletes the old module, renames
this one to ``swarm_throughput.py`` / ``SurfSwarmThroughput`` in one commit,
exports it and writes its stylesheet block; its tests bind to the final
name's signature already.

Rows, top to bottom
-------------------
1. a **label-less** window row: ``over 14 min · 100 jobs`` from
   ``window_end_ts - window_start_ts`` and ``window_n``; ``over --`` when
   either stamp is ``None``; a 0-job window says :data:`NO_JOBS_LINE`
   rather than ``0 jobs`` -- the read happened and found nothing;
2. a separator, then ``median`` / ``p90`` / ``max`` -- two-unit durations
   (``54m``, ``1h 12m``, ``3h 5m``); ``None`` says :data:`SAMPLE_FLOOR_WORD`
   (``-- (n<2)``), the analytics' own floor: one duration is a data point,
   not a distribution. The WP3 note asked for the sample count beside the
   percentiles; §1.3 carries no such field, so the floor word is what this
   panel can honestly say about the sample and ``window_n`` on the window
   row is the count it can print (reported to the controller);
3. a separator, then ``completed 24h``: :data:`ACCUMULATING_WORD` ``since
   HH:MM`` off ``seen_since_ts`` while ``completed_24h is None`` (the seen
   slot has under 24 h of history), and a real ``0`` once it has (plan R-A:
   never ``0`` for "not yet measured");
4. a separator, then the **state rollup** -- ``states`` is an open list, so
   the fixed ``ROWS`` cannot name them: one body ``Static``
   (:data:`STATES_ID`) carries ``state  count`` lines sorted by count
   descending, built as a single ``rich.text.Text`` inside
   ``write_guarded``; then the **cancel reasons** block (:data:`CANCELS_ID`)
   the same way -- ``none`` for ``[]``, ``unavailable`` for ``None``.

**A ``None`` dict is every row ``unavailable``; a dict missing a field is
that row ``--``.** Two different facts (the read failed / the read came
back without this number), kept apart per row: a duration *key absent* is
``--``, a duration *present as ``None``* is the sample floor. The fixed
rows go through ``render_signal`` → ``fmt_signal``, which escapes
``value_str``; every value here is the widget's own formatting of a number,
so nothing third-party reaches that path.

Third-party text renders literally
----------------------------------
State words and cancel reasons are the host's. Each is appended to a
``Text`` with ``Text.append`` after ``markup_safety.flatten`` and
``rowfit.clip`` (``cell_len``); ``Text.append`` parses nothing, so ``[/x]``
renders as the literal four characters and ``[$error]`` cannot raise.
``sanitize_cell`` was not used on purpose: its ``strip_tags`` deletes a
complete ``[...]`` run, and the plan (WP5) requires a hostile tag in a
cancel reason to **render literally**. A reason is clipped to the panel's
own measured width; the panel re-renders on resize for that.

Title: ``THROUGHPUT``, ``· as of HH:MM`` when ``rowfit.has_marker``, and
``· stale`` (:data:`STALE_WORD`, the old panel's word) **only when
``swarm_stale is True``** -- never on ``None`` (not measured) or ``False``.

Purity: stdlib, ``rich``, ``textual``, ``widgets/panels``, ``widgets/fmt``,
``widgets/rowfit``, ``widgets/markup_safety``. No ``data/``, no
``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, as_float, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE_LINE, SignalsPanelBase

__all__ = [
    "ACCUMULATING_WORD",
    "CANCELS_ID",
    "NO_JOBS_LINE",
    "ROW_IDS",
    "SAMPLE_FLOOR_WORD",
    "STALE_WORD",
    "STATES_ID",
    "TITLE",
    "SurfSwarmThroughputV2",
]

TITLE = "THROUGHPUT"

#: Appended to the title when the manager says the two swarm tiers' markers
#: drifted apart (``swarm_stale is True``). The old panel's word, tested verbatim.
STALE_WORD = "stale"

#: The 24 h count's state while the seen slot has under a day of history.
ACCUMULATING_WORD = "accumulating"

#: A duration row's state under the analytics' two-sample floor.
SAMPLE_FLOOR_WORD = "-- (n<2)"

#: A window that returned no jobs -- a read that found nothing, not a ``0``.
NO_JOBS_LINE = "no jobs in window"

_WINDOW_ID = "surf-swarm-throughput-window"
_MEDIAN_ID = "surf-swarm-throughput-median"
_P90_ID = "surf-swarm-throughput-p90"
_MAX_ID = "surf-swarm-throughput-max"
_COMPLETED_ID = "surf-swarm-throughput-completed"
STATES_ID = "surf-swarm-throughput-states"
CANCELS_ID = "surf-swarm-throughput-cancels"

ROW_IDS = (_WINDOW_ID, _MEDIAN_ID, _P90_ID, _MAX_ID, _COMPLETED_ID)

_GAP = rowfit.GAP
#: The rollup lines' own indent, the same two cells ``fmt_signal`` spends.
_INDENT = "  "
#: A state word: corpus ``completed`` / ``executing`` (9), ``cancelled`` (9);
#: the vocabulary is open, so a longer word clips with ``…``.
_STATE_COLS = 12
#: A count, right-aligned: ``100`` in the corpus; four covers 9,999.
_COUNT_COLS = 4

#: The sentinel for "the key is not in the dict at all" -- ``--`` -- as
#: opposed to "present and ``None``", which each row reads its own way.
_MISSING = object()


# -- pure formatters -----------------------------------------------------------------


def _fmt_span(seconds) -> str:
    """The window's span in words: ``14 min`` / ``2 h 5 min`` / ``3 d 2 h``."""
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    minutes = int(round(s / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def _fmt_duration(seconds) -> str:
    """A job's duration, two units at most: ``45s`` / ``54m`` / ``1h 12m`` / ``3d 4h``."""
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 60:
        return f"{s:.0f}s"
    minutes = int(round(s / 60))
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def _int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _signal(label: str, value_str: str, color: str) -> dict:
    return {"label": label, "value_str": value_str, "color": color, "indicator": "●"}


def _window_signal(tp: dict) -> dict:
    n = tp.get("window_n", _MISSING)
    if n is _MISSING:
        return _signal("window", DASH, "dim")
    count = _int(n)
    if count == 0:
        return _signal("window", NO_JOBS_LINE, "dim")
    start = as_float(tp.get("window_start_ts"))
    end = as_float(tp.get("window_end_ts"))
    span = _fmt_span(None if start is None or end is None else end - start)
    jobs = f"{count:,} jobs" if count is not None else f"{DASH} jobs"
    return _signal("window", f"over {span} · {jobs}", "white")


def _duration_signal(label: str, tp: dict, key: str) -> dict:
    raw = tp.get(key, _MISSING)
    if raw is _MISSING:
        return _signal(label, DASH, "dim")
    if raw is None:
        return _signal(label, SAMPLE_FLOOR_WORD, "dim")
    text = _fmt_duration(raw)
    return _signal(label, text, "dim" if text == DASH else "white")


def _completed_signal(tp: dict) -> dict:
    raw = tp.get("completed_24h", _MISSING)
    if raw is _MISSING:
        return _signal("completed 24h", DASH, "dim")
    if raw is None:
        since = hhmm(tp.get("seen_since_ts"))
        return _signal("completed 24h", f"{ACCUMULATING_WORD} since {since}", "dim")
    count = _int(raw)
    if count is None:
        return _signal("completed 24h", DASH, "dim")
    return _signal("completed 24h", f"{count:,}", "green")


def _count_cell(value) -> str:
    count = _int(value)
    return f"{count:,}" if count is not None else DASH


def _rollup_text(heading: str, entries, name_key: str, name_cols: int) -> Text:
    """``heading`` then one ``name  count`` line per entry, count-descending.

    ``None`` (could not look) writes the base's ``UNAVAILABLE_LINE`` under
    the heading; ``[]`` writes ``none``. A non-dict entry or one without a
    name is skipped; a missing or non-numeric count is ``--`` and sorts last.
    """
    text = Text()
    text.append(_INDENT + heading, style="dim")
    if entries is None:
        text.append("\n")
        text.append_text(Text.from_markup(UNAVAILABLE_LINE))
        return text
    rows: list[tuple[str, int | None]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = flatten(entry.get(name_key))
        if not name:
            continue
        rows.append((name, _int(entry.get("count"))))
    if not rows:
        text.append("\n" + _INDENT + "none", style="dim")
        return text
    rows.sort(key=lambda item: (item[1] is None, -(item[1] or 0)))
    for name, count in rows:
        text.append("\n" + _INDENT)
        text.append(rowfit.pad(rowfit.clip(name, name_cols), name_cols))
        text.append(" " * _GAP)
        text.append(f"{_count_cell(count):>{_COUNT_COLS}}", style="bold")
    return text


class SurfSwarmThroughputV2(SignalsPanelBase):
    """THROUGHPUT -- window, three durations, the 24 h count, states, cancels."""

    TITLE = TITLE
    LABEL_WIDTH = 14
    DIM_LABEL = True

    ROWS = (
        (_WINDOW_ID, None),
        None,
        (_MEDIAN_ID, "median"),
        (_P90_ID, "p90"),
        (_MAX_ID, "max"),
        None,
        (_COMPLETED_ID, "completed 24h"),
        None,
    )

    #: ``.panel-line``'s own ``padding: 0 1`` (``PanelBase``).
    _LINE_PADDING_COLS = 2

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._payload: dict | None = None

    def compose_body(self) -> ComposeResult:
        """The base's fixed rows, then the two open-vocabulary blocks."""
        yield from super().compose_body()
        yield Static("", classes="panel-line", id=STATES_ID)
        yield Static("", classes="panel-line", id=CANCELS_ID)

    def update_data(
        self,
        swarm_throughput=None,
        swarm_as_of_hhmm=None,
        swarm_stale=None,
        **_kwargs,
    ) -> None:
        """Refresh every row from the §1.3 dict; ``**_kwargs`` is mandatory."""
        self._payload = {
            "tp": swarm_throughput,
            "as_of": swarm_as_of_hhmm,
            "stale": swarm_stale,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._render_view()

    # -- rendering ---------------------------------------------------------------

    def _line_width(self) -> int:
        return max(self.content_size.width - self._LINE_PADDING_COLS, 0)

    def _set_title(self) -> None:
        try:
            title = self.query_one(".panel-title", Static)
        except Exception:  # not composed yet
            return
        payload = self._payload or {}
        text = TITLE
        if rowfit.has_marker(payload.get("as_of")):
            text += f" · as of {payload['as_of']}"
        if payload.get("stale") is True:
            text += f" · {STALE_WORD}"
        title.update(Text(text))

    def _render_view(self) -> None:
        self._set_title()
        raw = (self._payload or {}).get("tp")
        tp = raw if isinstance(raw, dict) else None

        def sig(build):
            return None if tp is None else build()

        self.render_signal(
            f"#{_WINDOW_ID}", "window", sig(lambda: _window_signal(tp)), labelled=False,
        )
        self.render_signal(
            f"#{_MEDIAN_ID}", "median", sig(lambda: _duration_signal("median", tp, "dur_median_s")),
        )
        self.render_signal(
            f"#{_P90_ID}", "p90", sig(lambda: _duration_signal("p90", tp, "dur_p90_s")),
        )
        self.render_signal(
            f"#{_MAX_ID}", "max", sig(lambda: _duration_signal("max", tp, "dur_max_s")),
        )
        self.render_signal(
            f"#{_COMPLETED_ID}", "completed 24h", sig(lambda: _completed_signal(tp)),
        )

        # The open-vocabulary blocks: a reason gets the panel's remaining width.
        width = self._line_width()
        reason_cols = max(width - len(_INDENT) - _GAP - _COUNT_COLS, 1)
        states = None if tp is None else tp.get("states")
        cancels = None if tp is None else tp.get("cancel_reasons")
        self.write_guarded(
            f"#{STATES_ID}",
            lambda: _rollup_text("states", states, "state", _STATE_COLS),
            Text.from_markup(UNAVAILABLE_LINE),
        )
        self.write_guarded(
            f"#{CANCELS_ID}",
            lambda: _rollup_text("cancel reasons", cancels, "reason", reason_cols),
            Text.from_markup(UNAVAILABLE_LINE),
        )
