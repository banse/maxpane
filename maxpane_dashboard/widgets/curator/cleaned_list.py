"""The de-sybilled leaderboard (PRD §5.3) — the ``f`` view's third panel.

The list as it reads with the linked groups removed: one row per survivor,
by ``clean_rank`` — deliberately not ``rank``, because the two are rendered
side by side elsewhere ("#412 raw, #47 with farms removed") and one name for
both would make that line impossible to write.

The summary line carries the **clean** side of the contract — survivor
count, clean points, the reader's own clean rank — and names what the
numbers are *after*: "linked groups removed".  The totals they are down
*from* live on other panels (the leaderboard's board, OPERATORS' share) and
are not routed here, so this panel never invents the comparison.

The export path is a receipt, not a payload
-------------------------------------------

``clean_list_export_path`` is **deliberately not an ``update_data`` kwarg**
(controller ruling R4; plan §6 risk 1): the export is an ``e`` keypress the
*screen* acts on, the write is the screen's, and the widget only renders the
path it is handed through :meth:`CuratorCleanList.mark_exported` — the
``CuratorWalletAddress.mark_pending`` precedent.  The path line is sticky
across refreshes because the file it names is still on disk.

``None`` vs ``[]``
------------------

``clean_list_rows is None`` is "the sweep could not answer" and renders
:data:`CLEAN_LIST_UNAVAILABLE`; ``[]`` is the sweep answering "nobody
survives the removals" — a real, if alarming, negative — and renders
:data:`CLEAN_LIST_EMPTY`.

Width behaviour
---------------

==========  ====  ==============================================
Tier        Cost  Columns
==========  ====  ==============================================
full          39  RANK  WALLET(12)  POINTS  CREDIT
no-credit     31  RANK  WALLET(12)  POINTS
minimal       23  RANK  WALLET(12)
==========  ====  ==============================================

The identity cell is the leaderboard's exactly: ``short_label`` over
``NAME_COLS``, so a stranger's 255-character registration can never widen
this table, and every cell is escaped before it reaches the ``DataTable``.

Primitives only — this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    COMPACT_ETH_COLS,
    DASH,
    NAME_COLS,
    fmt_eth_compact,
    fmt_points,
    short_label,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
    with_optional_suffix,
)
from maxpane_dashboard.widgets.curator.signals import MAX_CURVE_POINTS
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended, never substituted.
CLEAN_LIST_TITLE = "CLEANED LIST"

#: The explicit states, tested verbatim: a sweep that could not answer and a
#: sweep that answered "nobody survives" are different facts.
CLEAN_LIST_UNAVAILABLE = "clean list unavailable"
CLEAN_LIST_EMPTY = "every wallet is in a linked group"

#: The reader's own line when no clean rank came back.  The brief's exact
#: instruction ("set a wallet"), prefixed with whose rank the gap is about.
YOU_CLEAN_UNSET = "you: set a wallet"

#: The receipt line's failure state.  The screen's writer replaces the JSON
#: and *then* the CSV (temp file + ``os.replace`` each), so a JSON-succeeds /
#: CSV-fails window leaves the JSON newly written while the CSV is a step
#: behind — "nothing new was written" was a lie in exactly that window.  The
#: wording is honest for both halves: the both-failed case (neither replace
#: ran, the old files are byte-identical) and the torn-pair case (the two
#: files *may* be out of step).  Either way the ``e`` retry is the fix, and
#: any earlier ``saved →`` receipt must not keep standing — its *freshness* is
#: now a lie about the keypress that just failed.  Kept short: this is a
#: nowrap/ellipsis line, and it fits the panel's full-layout width with room.
EXPORT_FAILED = "export failed · files may be out of step · press e to retry"

#: Rows rendered.  Eight survivors: the analysis body stacks three panels
#: and the screen's ANALYSIS_MIN_HEIGHT is measured against exactly these
#: caps — grow one only with the screen's sweep open.
MAX_ROWS = 8

#: ``#99,999`` — the survivor rank under the same five-digit population
#: bound every cell in this package uses (15,576 contributors at capture).
_RANK_COLS = len(f"#{99_999:,}")

#: ``44,721`` is the highest score the curve can return for one wallet
#: (``signals.MAX_CURVE_POINTS``, itself pinned against the analytics
#: layer's own arithmetic from the test side).  A survivor is one wallet,
#: so six columns hold every score with the separator.
_PTS_COLS = len(f"{MAX_CURVE_POINTS:,}")

#: ``fmt_eth_compact``'s measured worst case and the ``CREDIT`` header are
#: both six.
_CREDIT_COLS = max(COMPACT_ETH_COLS, len("CREDIT"))

_TIERS = (
    (
        "full",
        39,
        (
            ("rank", "RANK", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
            ("points", "POINTS", _PTS_COLS),
            ("credit", "CREDIT", _CREDIT_COLS),
        ),
        "",
    ),
    (
        "no-credit",
        31,
        (
            ("rank", "RANK", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
            ("points", "POINTS", _PTS_COLS),
        ),
        "‹ widen: CREDIT",
    ),
    (
        "minimal",
        23,
        (
            ("rank", "RANK", _RANK_COLS),
            ("wallet", "WALLET", NAME_COLS),
        ),
        "‹ widen: CREDIT + POINTS",
    ),
)


def _as_int(value) -> int | None:
    """``int`` or ``None`` — never raise, never bool-coerce.

    ``True`` is not one point and not one wallet; a flag reaching a count
    field is a bug worth rendering as unknown rather than as a quantity
    (the ``as_float`` rule, for the summary's integers).
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_values(row: dict) -> dict:
    """One survivor's cells.  Every field degrades on its own."""
    rank = row.get("clean_rank")
    try:
        rank_str = f"#{int(rank):,}"
    except (TypeError, ValueError):
        rank_str = DASH
    return {
        "rank": rank_str,
        "wallet": safe_markup(short_label(row.get("name"), row.get("address"))),
        "points": fmt_points(row.get("points")),
        "credit": fmt_eth_compact(row.get("credit_eth")),
    }


class CuratorCleanList(Vertical):
    """The survivors, their clean ranks, and the reader's own — plus the
    export receipt the screen hands over after ``e``."""

    DEFAULT_CSS = """
    /* One blank row under the title and NONE under the note: this panel
       shares a stacked, height-budgeted body with two siblings.  The path
       line is display-toggled rather than blank so the body costs no row
       until there is actually a receipt to show. */
    CuratorCleanList > .curator-clean-title {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorCleanList > .curator-clean-note {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorCleanList > .curator-clean-path {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorCleanList > DataTable {
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""
        self._tier: str = "full"
        #: The written export path, set by the screen after the `e` write.
        #: Sticky across refreshes: the file it names is still on disk.
        self._export_path: str | None = None
        #: True after a failed `e` write (and until a retry succeeds).
        self._export_failed: bool = False

    def compose(self) -> ComposeResult:
        yield Static(
            CLEAN_LIST_TITLE, classes="curator-clean-title", id="curator-clean-title"
        )
        yield Static("", classes="curator-clean-note", id="curator-clean-note")
        path_line = Static("", classes="curator-clean-path", id="curator-clean-path")
        path_line.display = False
        yield path_line
        yield DataTable(id="curator-clean-table", classes="curator-clean-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-clean-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"rank": "[dim]…[/]"}, columns, default=""))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    # -- the export receipt (screen-supplied, never a manager key) ---------

    def mark_exported(self, path) -> None:
        """Render the path the screen just wrote — the ``mark_pending``
        precedent: a state only a keypress can set, handed over directly.
        Clears any earlier failure: this call *is* the successful retry."""
        self._export_path = str(path) if path else None
        self._export_failed = False
        self._render_path()

    def mark_export_failed(self) -> None:
        """The `e` write failed: say so, visibly, and drop any earlier
        ``saved →`` receipt — the file it named survives (the screen's writer
        is atomic) but the receipt's freshness would now be a lie.  Sticky
        across refreshes for the same reason the path is: the payload says
        nothing about the write, so a refresh may not un-say a failure."""
        self._export_path = None
        self._export_failed = True
        self._render_path()

    def _render_path(self) -> None:
        """The receipt line, three states: hidden (no export yet), the saved
        path, or the visible failure.  A path too long for the row keeps its
        **tail** behind a leading ``…`` — the filename is the half a reader
        needs to find the file, and a trailing ellipsis would cut exactly
        that."""
        try:
            line = self.query_one("#curator-clean-path", Static)
        except Exception:  # not composed yet
            return
        if getattr(self, "_export_failed", False):
            line.display = True
            line.update(f"[$warning]⚠ {EXPORT_FAILED}[/]")
            return
        if not self._export_path:
            line.display = False
            line.update("")
            return
        line.display = True
        prefix = "saved → "
        path = self._export_path
        width = max(self.content_size.width - 2, 0)
        if width and len(prefix) + len(path) > width:
            keep = max(width - len(prefix) - 1, 1)
            path = f"…{path[-keep:]}"
        line.update(f"[dim]{prefix}{safe_markup(path)}[/]")

    # -- rendering ---------------------------------------------------------

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        name, columns, hint = pick_tier(_TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        self._tier = name
        return columns

    def _set_title(self) -> None:
        """Title plus the widen marker; the note carries it when it does not fit."""
        width = max(self.content_size.width - 2, 0)
        text, placed = title_with_hint(CLEAN_LIST_TITLE, self._hint, width)
        self.query_one("#curator-clean-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-clean-note", Static).update(text)

    def update_data(
        self,
        clean_list_rows=None,
        clean_points=None,
        clean_contributors=None,
        points_total=None,
        you_clean_rank=None,
        analysis_as_of_hhmm=None,
        analysis_version=None,
        **_kwargs,
    ) -> None:
        """Refresh the table and its one-line summary.

        ``points_total`` (R14) is the population's total at the **same**
        analysis snapshot as ``clean_points``, which is what makes the
        summary's "X of Y pts" an honest comparison; ``None`` — the manager's
        state until the adapter runs — renders the clean side alone rather
        than a total borrowed from another panel's sweep.
        """
        self._payload = {
            "rows": clean_list_rows,
            "points": clean_points,
            "contributors": clean_contributors,
            "total": points_total,
            "you": you_clean_rank,
            "as_of": analysis_as_of_hhmm,
            "version": analysis_version,
            "seen": True,
        }
        self._render_view()

    def _as_of(self, prefix: str = "") -> str:
        """The freshness marker, plus THE LIST's analysis version when it fits.

        ``prefix`` is the plain text already set to render before this
        marker on the same note line -- passed in only so the fit check sees
        the whole line.  The marker is load-bearing and always renders whole
        once ``as_of`` is set; the version is decorative and is what sheds on
        a panel too narrow for both.
        """
        stamp = self._payload.get("as_of")
        if not (isinstance(stamp, str) and stamp.strip()):
            return ""
        marker = f" · as of {safe_markup(stamp.strip())}"
        version = self._payload.get("version")
        if isinstance(version, str) and version.strip():
            width = max(self.content_size.width - 2 - cell_len(prefix), 0)
            suffix = f" · {safe_markup(version.strip())}"
            return with_optional_suffix(marker, suffix, width)
        return marker

    def _summary(self) -> str:
        parts: list[str] = []
        contributors = _as_int(self._payload.get("contributors"))
        points = _as_int(self._payload.get("points"))
        total = _as_int(self._payload.get("total"))
        if contributors is not None:
            parts.append(f"{contributors:,} wallets")
        if points is not None:
            # PRD §5.3: total VS clean.  The comparison renders only when both
            # halves come from the payload -- a missing total costs the "of",
            # never invents one, and a total without readable clean points is
            # not a comparison at all.
            if total is not None:
                parts.append(f"{points:,} of {total:,} pts")
            else:
                parts.append(f"{points:,} pts")
        parts.append("linked groups removed")
        you = self._payload.get("you")
        if isinstance(you, int) and not isinstance(you, bool):
            parts.append(f"you #{you:,}")
        else:
            parts.append(YOU_CLEAN_UNSET)
        prefix = " · ".join(parts)
        return f"[dim]{prefix}{self._as_of(prefix)}[/]"

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-clean-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()
        self._render_path()

        rows = self._payload["rows"]
        if rows is None:
            self._set_note(
                f"[$warning]⚠ {CLEAN_LIST_UNAVAILABLE}[/]"
                f"{self._as_of(f'⚠ {CLEAN_LIST_UNAVAILABLE}')}"
            )
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            raw = list(rows)
        except TypeError:
            raw = None
        usable = (
            [r for r in raw if isinstance(r, dict)] if raw is not None else []
        )

        if raw is None or (raw and not usable):
            # A torn payload (uniterable, or rows that are not rows) is not a
            # finding: rendered as the empty state it would be a confident
            # "nobody survives" drawn from bytes nobody could read (M2).
            self._set_note(
                f"[$warning]⚠ {CLEAN_LIST_UNAVAILABLE}[/]"
                f"{self._as_of(f'⚠ {CLEAN_LIST_UNAVAILABLE}')}"
            )
            table.add_row(*cells({}, columns, default=DASH))
            return

        if not usable:
            # A real negative: the sweep ran and no wallet survives it.
            self._set_note(
                f"[dim]{CLEAN_LIST_EMPTY}{self._as_of(CLEAN_LIST_EMPTY)}[/]"
            )
            return

        self._set_note(self._summary())
        for row in usable[:MAX_ROWS]:
            try:
                values = _row_values(row)
            except Exception:
                values = {"rank": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))
