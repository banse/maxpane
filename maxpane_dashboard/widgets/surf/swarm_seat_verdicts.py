"""VERDICTS -- the selected seat's counters as a signals panel (swarm v2 plan A1, WP6a).

Mounted on the AGENT body (``a``) beside ROSTER since WP7; this module
only paints the frozen ``swarm_seat_summary`` dict: ``nodes, jobs,
accepted, rejected, revisions, mean_score, scored, working_now,
first_seen_ts, last_active_ts, roles: [{role, count}], rejection_codes:
[{code, count}]`` -- or ``None``.

Seven fixed rows on :class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`
(``accepted``, ``rejected``, ``revisions``, a separator, ``score``,
``working``, ``first seen``, ``last active``), each an indicator that is
``●`` when the count is above zero and a dim ``○`` when it is a **real
zero** -- ``0`` renders ``0``, never ``unavailable`` -- then two
open-vocabulary blocks (``by role``, ``rejection codes``) that are not
signal rows: each is a body ``Static`` written through ``write_guarded`` as
a pre-built ``rich.text.Text`` (``Text.append`` parses nothing, so a role
or code spelled ``[/x]`` renders literally and a theme token cannot raise).

Three states of the summary, kept apart (CLAUDE.md: never a false
degradation). A summary **dict** paints the rows. ``None`` **under a
marker** -- the sweep ran and found no seat to summarise -- paints
:data:`NO_SEAT_LINE` on every row: a real empty. ``None`` with **no
marker** -- nothing was swept -- paints the base's ``unavailable``. The
brief said "summary ``None`` -> every row unavailable"; CLAUDE.md's
convention outranks it, and the hero's SEAT box draws the same line.

``mean_score`` ``None`` is "no feedback yet", not a score of zero; the row
says so in words. No clock: the two stamps are ``hhmm(ts)``.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, SignalsPanelBase
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm

__all__ = [
    "BLOCK_IDS",
    "NO_FEEDBACK_LINE",
    "NO_SEAT_LINE",
    "ROW_IDS",
    "SurfSwarmSeatVerdicts",
]

NO_FEEDBACK_LINE = "no feedback yet"
NO_SEAT_LINE = "no seat seen"

#: Signal rows, in panel order; ``None`` is the separator before the
#: informational group.
ROW_IDS = (
    "surf-swarm-verdicts-accepted",
    "surf-swarm-verdicts-rejected",
    "surf-swarm-verdicts-revisions",
    "surf-swarm-verdicts-score",
    "surf-swarm-verdicts-working",
    "surf-swarm-verdicts-first",
    "surf-swarm-verdicts-last",
)

#: The two open-vocabulary blocks under the rows.
BLOCK_IDS = {
    "roles": "surf-swarm-verdicts-roles",
    "codes": "surf-swarm-verdicts-codes",
}

_LABELS = {
    ROW_IDS[0]: "accepted",
    ROW_IDS[1]: "rejected",
    ROW_IDS[2]: "revisions",
    ROW_IDS[3]: "score",
    ROW_IDS[4]: "working",
    ROW_IDS[5]: "first seen",
    ROW_IDS[6]: "last active",
}

#: Indicator colour per counter row when the count is above zero.
_COUNT_COLORS = {ROW_IDS[0]: "green", ROW_IDS[1]: "red", ROW_IDS[2]: "yellow"}
_COUNT_KEYS = {ROW_IDS[0]: "accepted", ROW_IDS[1]: "rejected", ROW_IDS[2]: "revisions"}

ON, OFF, INFO = "●", "○", "·"


def _sig(label: str, value_str: str, *, indicator: str = INFO, color: str = "dim") -> dict:
    return {"label": label, "value_str": value_str, "indicator": indicator, "color": color}


def _count_sig(label: str, value: object, on_color: str) -> dict:
    n = fmt_int(value)
    if n == DASH:
        return _sig(label, DASH)
    positive = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    return _sig(label, n, indicator=ON if positive else OFF,
                color=on_color if positive else "dim")


def _score_sig(summary: dict) -> dict:
    mean = summary.get("mean_score")
    if mean is None:
        return _sig("score", NO_FEEDBACK_LINE, indicator=OFF)
    score = fmt_float(mean, ".1f")
    return _sig("score", f"{score} ({fmt_int(summary.get('scored'))} scored)",
                indicator=ON, color="white")


def _working_sig(summary: dict) -> dict:
    if summary.get("working_now"):
        return _sig("working", "yes", indicator=ON, color="green")
    return _sig("working", "no", indicator=OFF)


class SurfSwarmSeatVerdicts(SignalsPanelBase):
    """VERDICTS -- the selected seat's counters and open-vocabulary blocks."""

    TITLE = "VERDICTS"
    LABEL_WIDTH = 14
    DIM_LABEL = True

    ROWS = (
        (ROW_IDS[0], _LABELS[ROW_IDS[0]]),
        (ROW_IDS[1], _LABELS[ROW_IDS[1]]),
        (ROW_IDS[2], _LABELS[ROW_IDS[2]]),
        None,
        (ROW_IDS[3], _LABELS[ROW_IDS[3]]),
        (ROW_IDS[4], _LABELS[ROW_IDS[4]]),
        (ROW_IDS[5], _LABELS[ROW_IDS[5]]),
        (ROW_IDS[6], _LABELS[ROW_IDS[6]]),
    )

    DEFAULT_CSS = """
    SurfSwarmSeatVerdicts > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose_body(self) -> ComposeResult:
        yield from super().compose_body()
        # A separator before the two blocks -- not the title's blank row.
        yield Static("", classes="panel-line")
        yield Static("", classes="panel-line", id=BLOCK_IDS["roles"])
        yield Static("", classes="panel-line", id=BLOCK_IDS["codes"])

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_summary=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh every row and both blocks (MEDI-38: every poll, every row)."""
        self._render_title(swarm_seat_as_of_hhmm)
        summary = swarm_seat_summary if isinstance(swarm_seat_summary, dict) else None
        if summary is None:
            self._render_no_summary(rowfit.has_marker(swarm_seat_as_of_hhmm))
            return
        for row_id, key in _COUNT_KEYS.items():
            self.render_signal(f"#{row_id}", _LABELS[row_id],
                               _count_sig(_LABELS[row_id], summary.get(key), _COUNT_COLORS[row_id]))
        self.render_signal(f"#{ROW_IDS[3]}", "score", _score_sig(summary))
        self.render_signal(f"#{ROW_IDS[4]}", "working", _working_sig(summary))
        self.render_signal(f"#{ROW_IDS[5]}", "first seen",
                           _sig("first seen", hhmm(summary.get("first_seen_ts"))))
        self.render_signal(f"#{ROW_IDS[6]}", "last active",
                           _sig("last active", hhmm(summary.get("last_active_ts"))))
        self.write_guarded(f"#{BLOCK_IDS['roles']}",
                           lambda: self._block("by role", summary.get("roles"), "role"),
                           self._block_fallback("by role"))
        self.write_guarded(f"#{BLOCK_IDS['codes']}",
                           lambda: self._block("rejection codes", summary.get("rejection_codes"), "code"),
                           self._block_fallback("rejection codes"))

    # -- rendering ----------------------------------------------------------

    def _render_title(self, as_of: object) -> None:
        base = self.TITLE
        if rowfit.has_marker(as_of):
            base += f" · as of {as_of}"
        self.write(".panel-title", Text(base))

    def _render_no_summary(self, swept: bool) -> None:
        for row_id, label in _LABELS.items():
            if swept:
                self.render_signal(f"#{row_id}", label, _sig(label, NO_SEAT_LINE, indicator=OFF))
            else:
                self.render_signal(f"#{row_id}", label, None)
        for label, block_id in (("by role", BLOCK_IDS["roles"]),
                                ("rejection codes", BLOCK_IDS["codes"])):
            if swept:
                self.write_guarded(f"#{block_id}",
                                   lambda label=label: self._block_line(label, NO_SEAT_LINE, "dim"),
                                   self._block_fallback(label))
            else:
                self.write(f"#{block_id}", self._block_fallback(label))

    def _block_line(self, label: str, body: str, style: str) -> Text:
        text = Text("  ")
        text.append(f"{label:<{self.LABEL_WIDTH}}", style="dim")
        text.append(" ")
        text.append(body, style=style)
        return text

    def _block_fallback(self, label: str) -> str:
        return f"  [dim]{label:<{self.LABEL_WIDTH}}[/] {UNAVAILABLE}"

    def _block(self, label: str, entries: object, key: str) -> Text:
        """``label  word n · word n``; ``none`` for an empty list, dim."""
        if not isinstance(entries, list):
            raise TypeError("not a list")
        parts = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            word = flatten(entry.get(key)) or DASH
            parts.append(f"{word} {fmt_int(entry.get('count'))}")
        if not parts:
            return self._block_line(label, "none", "dim")
        return self._block_line(label, " · ".join(parts), "")
