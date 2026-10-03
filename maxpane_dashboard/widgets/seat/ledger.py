"""LEDGER: one row per ``accepted`` line, the plane's verdict beside it (spec §8 LEDGER; §5.1 ledger rules).

The daemon keeps no history and logs failures like successes (fill6 §1), so this
is where the local lifecycle (accepted → submitted → stored, with its marks) and
the plane's verdict (joined by ``hash12``) meet on one key, side by side and
never on one line. Columns ``when · node · role · model~tier · took · turns ·
out tok · stored · verdict · lag``; three width tiers on
:class:`~maxpane_dashboard.widgets.swarm_table.SwarmTableBase` (``full`` costs
:data:`FULL_WIDTH` = 123 cells and clears at 126 terminal columns in the
full-width SEAT body; no width exception remains).

Row states, each a mark the reader learns once: a pre-agent failure reads
``0.4 s`` under *took* and ``no agent`` under *model*; a lease-closed row (a
``submitted`` with no ``stored``, not an attempt) reads ``no row``; a cancelled
one ``cancelled <reason>``; a repaired run ``✓↻``, a re-sent one ``✓⟲``, a
multi-session attempt ``✓×N`` under *stored*; an open row shows ``—`` where its
verdict will be. The verdict cell: ``accepted +17m`` green, ``rejected`` red,
``failed <reason>`` red (``failed ·`` while the bounded reason fetch is pending),
``pending`` yellow -- **never green** (spec §6 rule 2) -- ``?`` when the API is
unavailable, ``local only`` under ``--offline``.

The node cell is the ``nodeId8`` the daemon prints, linked to the row's full
``jobId`` on the IMD explorer (``_chain.job_link_style``); an API-only history
row (no local accept) reads ``api``. Every third-party cell is redacted and
sanitised here again (spec §13; proof 12's ledger half).
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.analytics.seat_tiers import tier_label
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, EMDASH, as_float, fmt_age, fmt_int, mmdd_hhmm, short_model
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.seat._chain import job_link_style
from maxpane_dashboard.widgets.seat_words import seat_token
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.swarm_table import table_cols
from maxpane_dashboard.widgets.seat.seat_table import SeatTable

__all__ = ["COMPACT_WIDTH", "FULL_WIDTH", "TIGHT_WIDTH", "SeatLedgerTable", "older_line"]

_SPECS = (
    ("when", "when", 11),
    ("node", "node", 8),
    ("role", "role", 9),
    ("model", "model~tier", 22),
    ("took", "took", 7),
    ("turns", "turns", 5),
    ("out", "out tok", 7),
    ("stored", "stored", 6),
    ("verdict", "verdict", 22),
    ("lag", "lag", 6),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key not in ("lag", "role"))
_TIGHT = ("when", "node", "took", "stored", "verdict")
_TIERS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: Width tiers include DataTable cell padding (``table_cols``); the screen sweep certifies the onsets in situ.
FULL_WIDTH = _tier_width(_ALL)        # 123
COMPACT_WIDTH = _tier_width(_COMPACT)  # 104
TIGHT_WIDTH = _tier_width(_TIGHT)      # 64

_count = seat_token

_VERDICT_STYLE = {"accepted": "green", "rejected": "red", "failed": "red", "pending": "yellow"}
_KIND_ROLE = {"research": "question", "fuzz": "campaign"}


from maxpane_dashboard.widgets.seat.hero import _word


def _took(seconds: object) -> str:
    """``0.4 s`` · ``32 s`` · ``4m12s`` -- fits the seven-cell *took* column."""
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 10 and s != int(s):
        return f"{s:.1f} s"
    if s < 60:
        return f"{s:.0f} s"
    minutes, sec = divmod(int(s), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _tokens(value: object) -> str:
    n = _count(value)
    if n is None:
        return DASH
    return fmt_int(n) if n < 1000 else fmt_compact(n)


def older_line(total: object, cap: int) -> str | None:
    """``+N older · more`` for rows the window holds past *cap*, or ``None`` when all fit."""
    count = _count(total)
    if count is None or count <= cap:
        return None
    return f"+{fmt_int(count - cap)} older · more"


class SeatLedgerTable(SeatTable):
    """LEDGER -- the seat's accepted lines, newest first (module docstring)."""

    TITLE = "LEDGER"
    TABLE_ID = "seat-ledger-table"
    ROW_CAP = 20
    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = _TIERS
    LADDER = rowfit.Ladder(("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH))
    EMPTY_LINE = "no tasks in the window"
    UNAVAILABLE_LINE = "ledger unavailable"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._offline = False
        self._verdicts_unavailable = False

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        seat_tasks_rows=None, seat_tasks_window=None, seat_ledger_footer=None, seat_sources=None, seat_as_of_hhmm=None, seat_offline=None,
        seat_today_p50_s=None, seat_today_longest_s=None, seat_today_divergence=None,
        **_kwargs,
    ) -> None:
        self._offline = seat_offline is True
        source = seat_sources.get("seatWork") if isinstance(seat_sources, dict) else None
        source = source if isinstance(source, dict) else {}
        self._verdicts_unavailable = source.get("unavailable") is True or (source.get("ok") is None and not self._offline)
        as_of = seat_as_of_hhmm.get("tail") if isinstance(seat_as_of_hhmm, dict) else None
        rows = seat_tasks_rows if isinstance(seat_tasks_rows, list) else None
        window = seat_tasks_window if isinstance(seat_tasks_window, dict) else {}
        total = _count(window.get("rows"))
        if total is None and rows is not None:
            total = len(rows)
        self.store(rows, as_of, {"footer": seat_ledger_footer, "total": total})

    # -- rendering ----------------------------------------------------------

    def compose_body(self) -> ComposeResult:
        # ``cursor_foreground_priority="renderable"``: the cursor row keeps its verdict colour (a pending row under
        # the cursor stays yellow); the default ``"css"`` repaints it with ``datatable--cursor``'s ``color: $text``.
        # The surf precedent is ``widgets/surf/swarm_leaderboard.py`` ``compose_body``.
        yield DataTable(id=self.TABLE_ID, cursor_foreground_priority="renderable")
        yield Static("", id=self.footer_id, classes=self.FOOTER_CLASS)

    def _repaint(self) -> None:
        if not self.is_mounted:
            return
        super()._repaint()
        payload = self._payload or {}
        rows = payload.get("rows")
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        if not isinstance(rows, list):
            return  # the base wrote UNAVAILABLE_LINE
        parts = []
        older = older_line(summary.get("total"), self.ROW_CAP)
        if older:
            parts.append(older)
        footer = _word(summary.get("footer"))
        if footer:
            parts.append(footer)
        if not rows:
            parts.insert(0, self.EMPTY_LINE)
        if parts:
            self._write_footer(tuple(parts))

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        node8 = _word(item.get("nodeId8"))
        link = job_link_style(item.get("jobId"))
        node = Text(sanitize_cell(node8, 8) if node8 else "api", style=link if link is not None else ("" if node8 else "dim"))
        if not node8 and link is not None:
            node.stylize(link)
        kind = _word(item.get("kind"))
        role = _KIND_ROLE.get(kind) or _word(item.get("role")) or DASH
        pre_agent = item.get("preAgentFailure") is True
        if pre_agent:
            model = "[dim]no agent[/]"
        else:
            short = short_model(_word(item.get("model")))
            tier = tier_label(item.get("tierDerived") if isinstance(item.get("tierDerived"), str) else None)
            model = sanitize_cell(f"{short or DASH} {tier}", 22)
        stored = "✓" if item.get("storedUtc") else EMDASH
        marks = ""
        if item.get("repair") is True:
            marks += "↻"
        if item.get("resent") is True:
            marks += "⟲"
        files = _count(item.get("sessionFiles"))
        if files is not None and files > 1:
            marks += f"×{files}"
        cells = {
            "when": mmdd_hhmm(parse_iso(item.get("acceptedUtc"))),
            "node": node,
            "role": sanitize_cell(role, 9),
            "model": model,
            "took": _took(item.get("durationS")),
            "turns": fmt_int(item.get("turns")) if _count(item.get("turns")) is not None else DASH,
            "out": _tokens((item.get("tokens") or {}).get("output") if isinstance(item.get("tokens"), dict) else None),
            "stored": sanitize_cell(stored + marks, 6),
            "verdict": self._verdict_cell(item),
            "lag": fmt_age(item.get("verdictLagS")),
        }
        return cells

    def _verdict_cell(self, item: dict) -> str:
        cancelled = _word(item.get("cancelled"))
        if cancelled:
            return f"[dim]{sanitize_cell(f'cancelled {cancelled}', 22)}[/]"
        if item.get("interruptedByRestart") is True and not item.get("storedUtc"):
            return "[dim]interrupted by restart[/]"
        if item.get("leaseClosed") is True:
            return "[dim]no row[/]"
        if not item.get("submittedUtc"):
            return f"[dim]{EMDASH}[/]"
        if not item.get("storedUtc"):
            return "[dim]not stored[/]"
        if self._offline:
            return "[dim]local only[/]"
        outcome = _word(item.get("outcome"))
        if outcome == "accepted":
            lag = fmt_age(item.get("verdictLagS"))
            return f"[green]{sanitize_cell('accepted' + (f' +{lag}' if lag != DASH else ''), 22)}[/]"
        if outcome == "rejected":
            return "[red]rejected[/]"
        if outcome == "failed":
            reason = _word(item.get("failureReason")) or "·"
            return f"[red]{sanitize_cell(f'failed {reason}', 22)}[/]"
        if outcome == "pending":
            return "[yellow]pending[/]"  # spec §6 rule 2: never green, never "running"
        return "[yellow]?[/]" if self._verdicts_unavailable or outcome in ("", "unknown") else f"[yellow]{sanitize_cell(outcome, 22)}[/]"
