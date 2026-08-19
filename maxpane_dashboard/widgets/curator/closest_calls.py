"""Completed judged hours through hour 65 (PRD §4).

One row per **completed judged hour**, newest first, with hours above 65
omitted. The row is ``hour · volume · margin · savior``.

Three states, all explicit
--------------------------

* ``None`` — the fold could not be built: ``closest calls unavailable``.
* ``[]`` **during grace** — there is nothing to judge yet, and the panel
  says when that changes: ``no judged hours yet — judging begins <UTC>``,
  with the instant taken from ``grace_ends_utc``.  Never a hardcoded date:
  the deployment's grace window is read live off the ``once`` tier, and this
  dashboard may outlive this deployment.
* ``[]`` **after grace** — the same sentence without the instant, because
  ``grace_ends_utc`` is behind us and the panel has nothing to promise.

A margin of exactly ``0.00`` is a number, not a dash
----------------------------------------------------

An hour that survived by nothing at all is the tightest possible call and
the single most interesting row this panel can ever show.  ``—`` is reserved
for the **savior** column, where it means the honest thing: this hour was
never pulled back from the line, because ``HourSaved`` never fired for it —
an event that has never fired on chain at all, and may never.

Width behaviour
---------------

=========  ====  =============================
Tier       Cost  Columns
=========  ====  =============================
full        42   HOUR VOLUME MARGIN SAVIOR
compact     31   HOUR MARGIN SAVIOR
minimal     18   HOUR MARGIN
=========  ====  =============================

``VOLUME`` sheds first: it is the only column on the row a reader can
reconstruct, since the margin is the volume measured against the same
threshold the hero and the sparkline both label.  Each drop is announced.

The note line **wraps**; it does not ellipsise
----------------------------------------------

The tiers above govern the table.  The note under the title carries the
whole pre-judging sentence — ``no judged hours yet — judging begins
2026-08-17 19:58:47 UTC · hour 24``, **70 columns** against the ~49 this
panel gets from a ``3fr`` slot of the curator screen's bottom row at the
screen's own full-layout width — and it used to be ``text-wrap: nowrap``
plus ``text-overflow: ellipsis``.  So the panel silently ate ``· hour 24``,
then ``UTC``, then the seconds: the tail of the one sentence the empty state
exists to say, dropped with a clean ``CLOSEST CALLS`` title above it.  A
reader could not tell the truncation from a payload that had no hour number
in it, which is the exact confusion every explicit state in this package
exists to prevent.

Two fixes were available and the cheap one is not the marker.  Announcing it
with ``‹ widen`` would be honest, but it would light a marker on the curator
screen at its measured full-layout width for the whole grace period — the
phase the panel spends most of its life in — and the only way to clear it
would be a screen 72 columns wider than the one FWA binds.  This panel has
no spare columns and plenty of spare rows (title, note and a four-row table
inside a seventeen-row slot), so the sentence buys its width in **rows**:
the note is ``height: auto`` and wraps.  It is the surf announce feed's
lever, and CLAUDE.md records why it was the right one there too — the panel
a layout hands its spare rows to should spend them.

Nothing is shed, so nothing is announced.  The relocated ``‹ widen`` the
*table* raises when the title bar is too narrow to carry it still rides in
front of this note (:meth:`CuratorClosestCalls._set_note`), and it wraps
with it.

Primitives only — this module imports nothing from ``data/`` or ``analytics/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    ADDR_COLS,
    DASH,
    EMDASH,
    as_float,
    fmt_eth_compact,
    short_addr,
    NAME_COLS,
    short_label,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended, never substituted.
CLOSEST_CALLS_TITLE = "CLOSEST CALLS"

#: The explicit states, tested verbatim.
CLOSEST_CALLS_UNAVAILABLE = "closest calls unavailable"
NO_JUDGED_HOURS = "no judged hours yet"

#: Rows rendered.  The board is a "closest" list, not a history.
MAX_ROWS = 10
MAX_HOUR = 65

_HOUR_COLS = 5
_VOLUME_COLS = 9
_MARGIN_COLS = 9

_TIERS = (
    (
        "full",
        43,
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("volume", "VOLUME", _VOLUME_COLS),
            ("margin", "MARGIN", _MARGIN_COLS),
            ("savior", "SAVIOR", NAME_COLS),
        ),
        "",
    ),
    (
        "compact",
        32,
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("margin", "MARGIN", _MARGIN_COLS),
            ("savior", "SAVIOR", NAME_COLS),
        ),
        "‹ widen: VOLUME",
    ),
    (
        "minimal",
        18,
        (
            ("hour", "HOUR", _HOUR_COLS),
            ("margin", "MARGIN", _MARGIN_COLS),
        ),
        "‹ widen: VOLUME + SAVIOR",
    ),
)


def _hour_value(row: dict) -> int | None:
    value = row.get("hour")
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hour_key(row: dict) -> tuple[int, int]:
    """Sort valid hours descending and leave malformed rows at the bottom."""
    hour = _hour_value(row)
    return (1, 0) if hour is None else (0, -hour)


def _row_values(row: dict) -> dict:
    hour = _hour_value(row)
    hour_str = f"h{hour}" if hour is not None else DASH
    margin = as_float(row.get("margin_eth"))
    # 0.00 is a number here: an hour that survived by nothing is the
    # tightest call on the board, and the most interesting row on it.
    margin_str = f"{fmt_eth_compact(margin)}" if margin is not None else DASH
    savior = row.get("savior")
    savior_str = (
        safe_markup(short_label(row.get("savior_name"), savior))
        if savior
        else f"[dim]{EMDASH}[/]"
    )
    tight = margin is not None and margin <= 0.0
    return {
        "hour": hour_str,
        "volume": fmt_eth_compact(row.get("volume_eth")),
        "margin": f"[bold yellow]{margin_str}[/]" if tight else margin_str,
        "savior": savior_str,
    }


class CuratorClosestCalls(Vertical):
    """Judged hours newest first, with an explicit pre-judging state."""

    DEFAULT_CSS = """
    /* The note is the same single spacer row Activity carries. */
    CuratorClosestCalls > .curator-cc-title {
        width: 100%;
        margin: 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    /* height: auto + wrap, never nowrap/ellipsis -- see the module
       docstring: the pre-judging sentence is 70 columns and this panel's
       slot is ~49, so it is bought with rows rather than clipped. */
    CuratorClosestCalls > .curator-cc-note {
        width: 100%;
        height: auto;
        min-height: 1;
        margin: 0;
        padding: 0 1;
    }
    CuratorClosestCalls > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""

    def compose(self) -> ComposeResult:
        yield Static(
            CLOSEST_CALLS_TITLE, classes="curator-cc-title", id="curator-cc-title"
        )
        # The note doubles as the spacer: the pre-judging state is a sentence
        # with an absolute instant in it and no DataTable cell is that wide.
        # It wraps (``height: auto``) rather than ellipsising, so the sentence
        # survives a slot narrower than itself.
        yield Static("", classes="curator-cc-note", id="curator-cc-note")
        yield DataTable(id="curator-cc-table", classes="curator-cc-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-cc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"hour": "[dim]…[/]"}, columns, default=""))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    # -- layout ------------------------------------------------------------

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        _name, columns, hint = pick_tier(_TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        return columns

    def _set_title(self) -> None:
        """Title plus the widen marker; the note carries it when it does not fit."""
        width = max(self.content_size.width - 2, 0)
        text, placed = title_with_hint(CLOSEST_CALLS_TITLE, self._hint, width)
        self.query_one("#curator-cc-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        """The explicit-state line, prefixed with the widen marker when the
        title bar was too narrow to carry it (:func:`title_with_hint`)."""
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-cc-note", Static).update(text)

    # -- rendering ---------------------------------------------------------

    def update_data(
        self,
        closest_call_rows=None,
        first_judged_hour=None,
        grace_ends_utc=None,
        **_kwargs,
    ) -> None:
        """Refresh the board.

        ``first_judged_hour`` and ``grace_ends_utc`` are both chain-derived
        and both only used by the empty state — which is the state this panel
        spends the whole grace period in, so they are not optional decoration.
        """
        self._payload = {
            "rows": closest_call_rows,
            "first_judged_hour": first_judged_hour,
            "grace_ends_utc": grace_ends_utc,
            "seen": True,
        }
        self._render_view()

    def _empty_note(self) -> str:
        """``no judged hours yet — judging begins <UTC> · hour N``.

        Built whole and handed to a wrapping ``Static``: neither half is
        dropped to make it fit, because ``· hour N`` is the fact a reader
        counts down to and the instant is the fact they set a timer by.
        """
        ends = str(self._payload.get("grace_ends_utc") or "").strip()
        first = self._payload.get("first_judged_hour")
        text = NO_JUDGED_HOURS
        if ends:
            text += f" — judging begins {safe_markup(ends)}"
        if isinstance(first, int):
            text += f" · hour {first}"
        return f"[dim]{text}[/]"

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-cc-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()

        rows = self._payload["rows"]
        if rows is None:
            self._set_note(f"[$warning]⚠ {CLOSEST_CALLS_UNAVAILABLE}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            usable = [r for r in list(rows) if isinstance(r, dict)]
        except TypeError:
            usable = []

        if not usable:
            self._set_note(self._empty_note())
            table.add_row(*cells({}, columns, default=DASH))
            return

        bounded = [
            row
            for row in usable
            if (hour := _hour_value(row)) is None or hour <= MAX_HOUR
        ]
        self._set_note("")
        for row in sorted(bounded, key=_hour_key)[:MAX_ROWS]:
            try:
                values = _row_values(row)
            except Exception:
                values = {"hour": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))
