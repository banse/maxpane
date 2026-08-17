"""Fan-out patterns in the deposit data (PRD §4, the other half of the ``c`` slot).

One row per cluster: the shape, the block window it landed in, the points it
holds together and its share of all points::

    9× 60.00Ξ · 28 blocks    69,705    12.4%

The captured example is real: ranks 4-12 of the 2026-08-16 leaderboard were
nine wallets that each sent exactly 60 ETH inside a six-minute window — the
shape the sqrt curve rewards and the one the contract's own documentation
predicts a consumer will look for.

Pattern language only
---------------------

``fan-out`` describes what is in the event data.  ``sybil``, ``farm``
(as a verb), ``cheat``, ``fraud`` and ``attack`` describe an intent this
dashboard cannot read and has no standing to assert: one person spreading a
deposit and nine people copying a trade produce identical logs.  The same
forbidden-word list guards the analytics layer (WP3.10) and this panel, and
it is asserted on the rendered output, not on the source.

The share column is a percentage or a dash — never ``0.0%``
------------------------------------------------------------

``points_share_pct`` is ``None`` whenever total points are unknown, which is
a division this dashboard refuses to perform rather than approximate.
``0.0%`` there would assert that these wallets hold none of the score, which
is a measurement nobody made.  (The dash is ``--``, the package's "we could
not read this"; ``—`` is reserved for "there is deliberately nothing here",
which is the FORCED ETH row's healthy state and not this.)

Width behaviour
---------------

=========  ====  ==========================================
Tier       Cost  Columns
=========  ====  ==========================================
full        47   PATTERN (with the block window) POINTS SHARE
compact     35   PATTERN POINTS SHARE
minimal     23   PATTERN SHARE
=========  ====  ==========================================

Every cell width here is *derived* from what the fold can emit, and the two
costs above moved 45 → 47 and 33 → 35 the day the last hand-typed one
(``_POINTS_COLS``) was: see its note.

The block window sheds first — it is provenance, and the pattern itself is
the finding.  ``SHARE`` never sheds: a cluster's size means nothing without
what fraction of the board it holds.

Primitives only — this module imports nothing from ``data/`` or ``analytics/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    COMPACT_ETH_COLS,
    DASH,
    as_float,
    fmt_eth_compact,
    fmt_pct,
    fmt_points,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
)
from maxpane_dashboard.widgets.curator.signals import MAX_CURVE_POINTS
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended, never substituted.
CLUSTERS_TITLE = "FAN-OUT PATTERNS"

#: The explicit states, tested verbatim and deliberately different: one is a
#: real, meaningful negative and the other is a failure.
CLUSTERS_UNAVAILABLE = "clusters unavailable"
CLUSTERS_EMPTY = "no fan-out patterns found"

#: Rows rendered.
MAX_ROWS = 8

#: The producer's widest ``size``, in columns.  A cluster holds at least
#: ``CLUSTER_MIN_SIZE`` (3) wallets and at most every wallet on THE LIST —
#: 252 at capture time — so three digits is the vocabulary, not the nine of
#: the one captured example.
MAX_SIZE_COLS = 3

#: ``CLUSTER_MAX_BLOCK_SPAN`` from ``analytics/curator_signals``, restated
#: because widgets may not import ``analytics/``; the agreement is asserted
#: from the test side, the ``_GAME_CYCLE`` pattern CLAUDE.md documents.  The
#: fold cannot emit a wider window, so two digits is the whole vocabulary.
MAX_BLOCK_SPAN = 32

#: The pattern cell, **derived from what the fold can emit** rather than from
#: the one captured row.
#:
#: This was a hand-typed 21, which is exactly ``9× 60.00Ξ · 28 blocks`` — the
#: single captured example.  Ten wallets or more is 22, and ``DataTable`` cut
#: it to ``· 32 block`` — the trailing ``s`` gone, mid-word, on the panel's
#: headline value, at full width, with no ``‹ widen``.  That is the
#: ``dev``/``ops`` defect in CLAUDE.md in the direction that cuts, and the
#: fix is the same one: size the cell from the producer's vocabulary.
_PATTERN_COLS = len(
    f"{'9' * MAX_SIZE_COLS}× {'9' * COMPACT_ETH_COLS}Ξ · {MAX_BLOCK_SPAN} blocks"
)                                                                          # 24
_PATTERN_SHORT_COLS = len(f"{'9' * MAX_SIZE_COLS}× {'9' * COMPACT_ETH_COLS}Ξ")  # 12
#: The points cell, derived from the same two bounds the pattern cell uses.
#:
#: This was a hand-typed 8 — the last hand-typed cell width in this module —
#: and it cut the panel's headline value at **every** width, marker-free: the
#: live board's top row holds 2,663,784 points and rendered ``2,663,78`` at
#: 138, 143, 200 and 250 columns.  No terminal was wide enough to fix it,
#: because a fixed cell width does not grow with the panel.
#:
#: A cluster's ``points`` is the **sum** over its members (``_cluster_rows``
#: in ``analytics/curator_signals``), so its ceiling is the largest cluster
#: this module admits — ``MAX_SIZE_COLS`` digits of ``size``, the same bound
#: the pattern cell is built from — times the highest score the curve can
#: return for one wallet.  The suite asserts that ceiling against
#: ``analytics.curator_signals.points_for_weight``, since a widget may not
#: import ``analytics/``.
MAX_CLUSTER_POINTS = (10**MAX_SIZE_COLS - 1) * MAX_CURVE_POINTS
_POINTS_COLS = len(f"{MAX_CLUSTER_POINTS:,}")                              # 10
_SHARE_COLS = 7

_TIERS = (
    (
        "full",
        47,
        (
            ("pattern", "PATTERN", _PATTERN_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("share", "SHARE", _SHARE_COLS),
        ),
        "",
    ),
    (
        "compact",
        35,
        (
            ("pattern", "PATTERN", _PATTERN_SHORT_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("share", "SHARE", _SHARE_COLS),
        ),
        "‹ widen: block window",
    ),
    (
        "minimal",
        23,
        (
            ("pattern", "PATTERN", _PATTERN_SHORT_COLS),
            ("share", "SHARE", _SHARE_COLS),
        ),
        "‹ widen: block window + POINTS",
    ),
)


def _block_window(row: dict) -> int | None:
    """``last_block - first_block``, or ``None`` when either is unreadable."""
    try:
        first = int(row["first_block"])
        last = int(row["last_block"])
    except (KeyError, TypeError, ValueError):
        return None
    span = last - first
    return span if span >= 0 else None


def _row_values(row: dict, with_window: bool) -> dict:
    size = row.get("size")
    try:
        size_str = f"{int(size)}×"
    except (TypeError, ValueError):
        size_str = f"{DASH}×"
    amount = as_float(row.get("amount_eth"))
    pattern = f"{size_str} {fmt_eth_compact(amount)}Ξ"
    if with_window:
        span = _block_window(row)
        pattern += f" · {span} blocks" if span is not None else f" · {DASH} blocks"
    share = row.get("points_share_pct")
    return {
        "pattern": safe_markup(pattern),
        "points": fmt_points(row.get("points")),
        # None means total points were unknown -- a division refused, not a
        # zero measured.
        "share": fmt_pct(share) if share is not None else DASH,
    }


class CuratorClusters(Vertical):
    """Fan-out patterns, in pattern language, with a real empty state."""

    DEFAULT_CSS = """
    /* `margin-bottom: 1` on both the title and the note: a blank row under the
       title and another above the table header.  This slot has spare rows and
       no spare columns, so air is the cheap thing to spend here. */
    CuratorClusters > .curator-cl-title {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorClusters > .curator-cl-note {
        width: 100%;
        height: 1;
        margin: 0 0 1 0;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorClusters > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""
        self._tier: str = "full"

    def compose(self) -> ComposeResult:
        yield Static(CLUSTERS_TITLE, classes="curator-cl-title", id="curator-cl-title")
        yield Static("", classes="curator-cl-note", id="curator-cl-note")
        yield DataTable(id="curator-cl-table", classes="curator-cl-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-cl-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"pattern": "[dim]…[/]"}, columns, default=""))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    # -- layout ------------------------------------------------------------

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
        text, placed = title_with_hint(CLUSTERS_TITLE, self._hint, width)
        self.query_one("#curator-cl-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        """The explicit-state line, prefixed with the widen marker when the
        title bar was too narrow to carry it (:func:`title_with_hint`)."""
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-cl-note", Static).update(text)

    # -- rendering ---------------------------------------------------------

    def update_data(
        self,
        cluster_rows=None,
        clusters_count=None,
        flagged_points_share_pct=None,
        **_kwargs,
    ) -> None:
        """Refresh the table and its one-line summary."""
        self._payload = {
            "rows": cluster_rows,
            "count": clusters_count,
            "share": flagged_points_share_pct,
            "seen": True,
        }
        self._render_view()

    def _summary(self) -> str:
        count = self._payload.get("count")
        share = self._payload.get("share")
        if not isinstance(count, int):
            return ""
        plural = "" if count == 1 else "s"
        text = f"{count} fan-out group{plural}"
        if share is not None:
            text += f" · {fmt_pct(share)} of all points"
        return f"[dim]{text}[/]"

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-cl-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()

        rows = self._payload["rows"]
        if rows is None:
            self._set_note(f"[$warning]⚠ {CLUSTERS_UNAVAILABLE}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            usable = [r for r in list(rows) if isinstance(r, dict)]
        except TypeError:
            usable = []

        if not usable:
            # A real negative: the fold ran and the shape is not there.
            self._set_note(f"[dim]{CLUSTERS_EMPTY}[/]")
            table.add_row(*cells({}, columns, default=DASH))
            return

        self._set_note(self._summary())
        with_window = self._tier == "full"
        for row in usable[:MAX_ROWS]:
            try:
                values = _row_values(row, with_window)
            except Exception:
                values = {"pattern": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))
