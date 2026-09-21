"""SEAT RECORD -- the selected seat's lifetime record from ``/seats`` (plan WP3).

Was VERDICTS (swarm v2 A1), which folded window-scoped counters out of the
newest 100 jobs and printed them as the seat's record
(``docs/surf_agent_seats_spec.md`` §1). The class name is kept so the
signature map stays stable (plan §9 H); the title is ``SEAT RECORD``.

This module only paints ``swarm_seat_summary`` (fields
``data/surf_models.SWARM_SEAT_SUMMARY_FIELDS``, folded by
``data/surf_swarm.seat_summary_from_seat``), on
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`::

    accepted    ● 12 of 74
    reviewed    ● 72 · 6 pending
    sent        ● 66
    pending     ● 5 submitted · 1 queued
    score       ● 1.00 (72 scored)

    paired      · 09-19 04:14
    runtime     · claude 2.1.278 (Claude Code)
    owner       · 0xe5b1275f…f64f2a ⧉

    by role     implement 71 · review 1

*pending* is ``submitted + queued``, a subset of *reviewed* (plan Q-M);
the three status rows add up to it. A counter row is ``●`` above zero and a
dim ``○`` at a **real zero**, which renders ``0`` (``0 of 0``) -- only a
``None`` field renders ``unavailable``, on its own row. The same split holds
for text: a ``runtime`` of ``""`` (the seat's ``runtimes`` list was served
empty) renders a dim ``none``, never ``unavailable``.

**Third-party text** -- the runtime, the role words -- goes through
``markup_safety.sanitize_cell`` (flatten, strip bracket runs, clip, escape)
into a line parsed here, synchronously, inside the row's own guard; the
**owner** is ``widgets/address.address_text`` in surf's anti-poisoning window
(``_fmt.ANTI_POISONING_COLS``) with its copy icon, linked on the package
``EXPLORER`` (spec D5, plan Q-C) -- a pre-built ``Text``, never markup, so the
icon's click ``meta`` and the link survive. The full 42 characters plus the
label do not fit the panel's ``max-width: 46``.

``swarm_seat_state`` (``widgets/surf/_swarm_seat.py``) is read before any
number: ``"pending"`` puts ``Loading...`` on the first row, ``"unknown_seat"``
puts ``never paired`` there (a real negative; this panel's signature has no
token, and the hero's SEAT box names it), and ``None`` or a malformed state
paints ``unavailable`` on every row, behind the title's ``as of HH:MM`` when
the tier has one. No clock: stamps are ``mmdd`` / ``hhmm``.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.panels import UNAVAILABLE, SignalsPanelBase, fmt_signal
from maxpane_dashboard.widgets.surf._fmt import ANTI_POISONING_COLS, EXPLORER, hhmm, mmdd
from maxpane_dashboard.widgets.surf._swarm_seat import seat_state_line

__all__ = [
    "BLOCK_IDS",
    "NO_FEEDBACK_LINE",
    "PANEL_MAX_WIDTH",
    "ROW_IDS",
    "RUNTIME_COLS",
    "SurfSwarmSeatVerdicts",
    "VALUE_COLS",
]

#: The score row when no review carried a value: not a score of zero.
NO_FEEDBACK_LINE = "no scores yet"

#: Signal rows, in panel order (``SignalsPanelBase.ROWS`` adds the separator).
ROW_IDS = (
    "surf-swarm-verdicts-accepted",
    "surf-swarm-verdicts-reviewed",
    "surf-swarm-verdicts-sent",
    "surf-swarm-verdicts-pending",
    "surf-swarm-verdicts-score",
    "surf-swarm-verdicts-paired",
)

#: The lines that carry third-party text or an address: a pre-built ``Text``
#: each, written through ``write_guarded``, never a markup signal row.
BLOCK_IDS = {
    "runtime": "surf-swarm-verdicts-runtime",
    "owner": "surf-swarm-verdicts-owner",
    "roles": "surf-swarm-verdicts-roles",
}

_LABELS = {
    ROW_IDS[0]: "accepted",
    ROW_IDS[1]: "reviewed",
    ROW_IDS[2]: "sent",
    ROW_IDS[3]: "pending",
    ROW_IDS[4]: "score",
    ROW_IDS[5]: "paired",
    BLOCK_IDS["runtime"]: "runtime",
    BLOCK_IDS["owner"]: "owner",
    BLOCK_IDS["roles"]: "by role",
}

#: The label column: the longest label is ``accepted`` / ``reviewed`` (8).
_LABEL_WIDTH = 11

#: The panel's ``max-width`` in ``minimal.tcss`` -- a hand-typed copy of the
#: stylesheet's number, bound to it by an agreement test in
#: ``tests/widgets/test_surf_swarm_seat_verdicts.py``. Not a layout pin: the
#: panel's width is WP6's to sweep, and the fits below follow it.
PANEL_MAX_WIDTH = 46

#: The panel's own and the line's ``padding: 0 1``, both sides.
_PADDING_COLS = 2 + 2

#: What a row spends before its value: ``"  " + indicator + " " + label + " "``.
_HEAD_COLS = 2 + 1 + 1 + _LABEL_WIDTH + 1

#: The cells a row's value has at the panel's max-width (26 today).
VALUE_COLS = PANEL_MAX_WIDTH - _PADDING_COLS - _HEAD_COLS

#: The runtime's clip, in cells: the value column --
#: ``claude 2.1.278 (Claude Code)`` (28) is clipped with a visible ``…``.
RUNTIME_COLS = VALUE_COLS

#: One role word's clip: a role is third-party text of no fixed length.
_ROLE_COLS = 16

ON, OFF, INFO = "●", "○", "·"


def _fit_roles(parts: list[str], cols: int) -> str:
    """Join role cells (escaped markup) into at most *cols* cells.

    Every role whole when they all fit; otherwise the longest prefix, in the
    fold's order (count descending), that fits beside ``+N more`` -- the roles
    left out are counted on screen, never clipped away in silence.
    """
    def width(cells: list[str]) -> int:
        return Text.from_markup(" · ".join(cells)).cell_len

    if width(parts) <= cols:
        return " · ".join(parts)
    for keep in range(len(parts) - 1, -1, -1):
        cells = parts[:keep] + [f"+{len(parts) - keep} more"]
        if width(cells) <= cols:
            return " · ".join(cells)
    return f"+{len(parts)} more"


def _count(value: object) -> int | None:
    """A lifetime counter, or ``None``: an ``int``, not a ``bool``, not negative."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sig(label: str, value_str: str, *, indicator: str = INFO, color: str = "dim") -> dict:
    return {"label": label, "value_str": value_str, "indicator": indicator, "color": color}


def _count_sig(label: str, value_str: str, n: int, on_color: str = "green") -> dict:
    """``●`` above zero, a dim ``○`` at a real zero -- which still renders ``0``."""
    if n > 0:
        return _sig(label, value_str, indicator=ON, color=on_color)
    return _sig(label, value_str, indicator=OFF)


def _accepted_sig(summary: dict) -> dict | None:
    accepted = _count(summary.get("accepted"))
    attempts = _count(summary.get("attempts"))
    if accepted is None or attempts is None:
        return None
    return _count_sig("accepted", f"{fmt_int(accepted)} of {fmt_int(attempts)}", accepted)


def _status_counts(summary: dict) -> dict | None:
    status = summary.get("review_status")
    if not isinstance(status, dict):
        return None
    counts = {key: _count(status.get(key)) for key in ("sent", "submitted", "queued")}
    return None if any(v is None for v in counts.values()) else counts


def _reviewed_sig(summary: dict) -> dict | None:
    reviewed = _count(summary.get("reviewed"))
    if reviewed is None:
        return None
    counts = _status_counts(summary)
    pending = fmt_int(counts["submitted"] + counts["queued"]) if counts else "--"
    return _count_sig("reviewed", f"{fmt_int(reviewed)} · {pending} pending", reviewed, "white")


def _sent_sig(summary: dict) -> dict | None:
    counts = _status_counts(summary)
    if counts is None:
        return None
    return _count_sig("sent", fmt_int(counts["sent"]), counts["sent"], "white")


def _pending_sig(summary: dict) -> dict | None:
    counts = _status_counts(summary)
    if counts is None:
        return None
    submitted, queued = counts["submitted"], counts["queued"]
    return _count_sig("pending", f"{fmt_int(submitted)} submitted · {fmt_int(queued)} queued",
                      submitted + queued, "yellow")


def _score_sig(summary: dict) -> dict | None:
    scored = _count(summary.get("scored"))
    if scored is None:
        return None
    mean = summary.get("mean_score")
    if mean is None or isinstance(mean, bool):
        return _sig("score", NO_FEEDBACK_LINE, indicator=OFF)
    return _sig("score", f"{fmt_float(mean, '.2f')} ({fmt_int(scored)} scored)",
                indicator=ON, color="white")


def _paired_sig(summary: dict) -> dict | None:
    ts = summary.get("paired_ts")
    if ts is None:
        return None
    return _sig("paired", f"{mmdd(ts)} {hhmm(ts)}")


_ROW_BUILDERS = (
    (ROW_IDS[0], _accepted_sig),
    (ROW_IDS[1], _reviewed_sig),
    (ROW_IDS[2], _sent_sig),
    (ROW_IDS[3], _pending_sig),
    (ROW_IDS[4], _score_sig),
    (ROW_IDS[5], _paired_sig),
)


class SurfSwarmSeatVerdicts(SignalsPanelBase):
    """SEAT RECORD -- the selected seat's lifetime counters, pairing and owner."""

    TITLE = "SEAT RECORD"
    LABEL_WIDTH = _LABEL_WIDTH
    DIM_LABEL = True

    ROWS = (
        (ROW_IDS[0], _LABELS[ROW_IDS[0]]),
        (ROW_IDS[1], _LABELS[ROW_IDS[1]]),
        (ROW_IDS[2], _LABELS[ROW_IDS[2]]),
        (ROW_IDS[3], _LABELS[ROW_IDS[3]]),
        (ROW_IDS[4], _LABELS[ROW_IDS[4]]),
        None,
        (ROW_IDS[5], _LABELS[ROW_IDS[5]]),
    )

    DEFAULT_CSS = """
    SurfSwarmSeatVerdicts > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose_body(self) -> ComposeResult:
        yield from super().compose_body()
        yield Static("", classes="panel-line", id=BLOCK_IDS["runtime"])
        yield Static("", classes="panel-line", id=BLOCK_IDS["owner"])
        # A separator before the role block -- not the title's blank row.
        yield Static("", classes="panel-line")
        yield Static("", classes="panel-line", id=BLOCK_IDS["roles"])

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_summary=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh every row and block (MEDI-38: every poll, every row)."""
        self._render_title(swarm_seat_as_of_hhmm)
        line = seat_state_line(swarm_seat_state)
        if line is not None:
            self._render_state(swarm_seat_state, line)
            return
        summary = swarm_seat_summary if isinstance(swarm_seat_summary, dict) else None
        if summary is None:
            self._render_unavailable()
            return
        for row_id, build in _ROW_BUILDERS:
            label = _LABELS[row_id]
            self.write_guarded(
                f"#{row_id}",
                lambda build=build, label=label: self._signal_markup(label, build(summary)),
                self._signal_markup(label, None),
            )
        self.write_guarded(f"#{BLOCK_IDS['runtime']}",
                           lambda: self._runtime_line(summary.get("runtime")),
                           self._text_fallback("runtime"))
        self.write_guarded(f"#{BLOCK_IDS['owner']}",
                           lambda: self._owner_line(summary.get("owner")),
                           self._text_fallback("owner"))
        self.write_guarded(f"#{BLOCK_IDS['roles']}",
                           lambda: self._roles_line(summary.get("roles")),
                           self._text_fallback("by role"))

    # -- rendering ----------------------------------------------------------

    def _render_title(self, as_of: object) -> None:
        base = self.TITLE
        if rowfit.has_marker(as_of):
            base += f" · as of {as_of}"
        self.write(".panel-title", Text(base))

    def _signal_markup(self, label: str, sig: dict | None) -> str:
        """One signal row through the base's formatter; ``None`` is ``unavailable``."""
        source = sig if sig else {"label": label, "value_str": "unavailable", "color": "yellow"}
        return fmt_signal(source, label_width=self.LABEL_WIDTH, dim_label=self.DIM_LABEL)

    def _every_line(self) -> list[str]:
        return [*ROW_IDS, *BLOCK_IDS.values()]

    def _render_state(self, state: object, line: Text) -> None:
        """``pending`` / ``unknown_seat``: the word on the first row, the rest empty.
        ``None`` or a malformed state: ``unavailable`` on every row."""
        if state not in ("pending", "unknown_seat"):
            self._render_unavailable()
            return
        first, *rest = self._every_line()
        self.write(f"#{first}", Text("  ") + line)
        for line_id in rest:
            self.write(f"#{line_id}", "")

    def _render_unavailable(self) -> None:
        for row_id in ROW_IDS:
            self.write(f"#{row_id}", self._signal_markup(_LABELS[row_id], None))
        for block_id in BLOCK_IDS.values():
            self.write(f"#{block_id}", self._text_fallback(_LABELS[block_id]))

    def _head(self, label: str, indicator: str = INFO) -> Text:
        """A text line's head in the signal row's own columns."""
        return Text.from_markup(f"  [dim]{indicator}[/] [dim]{label:<{self.LABEL_WIDTH}}[/] ")

    def _text_fallback(self, label: str) -> Text:
        return Text.from_markup(f"  [yellow]●[/] [dim]{label:<{self.LABEL_WIDTH}}[/] {UNAVAILABLE}")

    def _runtime_line(self, runtime: object) -> Text:
        """``runtime · <id> <version>``; ``none`` for ``""`` -- the fold's word
        for a served, empty ``runtimes`` list (seat #0 runs nothing: a real
        negative, never ``unavailable``); ``unavailable`` only for ``None``."""
        if runtime is None:
            return self._text_fallback("runtime")
        if runtime == "":
            return self._head("runtime") + Text("none", style="dim")
        # Escaped by ``sanitize_cell`` and parsed right here, inside the guard.
        return self._head("runtime") + Text.from_markup(sanitize_cell(runtime, RUNTIME_COLS))

    def _owner_line(self, owner: object) -> Text:
        if owner is None:
            return self._text_fallback("owner")
        # ``address_text`` validates with ``fullmatch``: anything that is not
        # a whole 0x address renders plain, with no icon and no link.
        return self._head("owner") + address_text(
            owner if isinstance(owner, str) else str(owner),
            width=ANTI_POISONING_COLS, explorer=EXPLORER,
        )

    def _roles_line(self, roles: object) -> Text:
        """``by role     implement 71 · review 1``; ``none`` for an empty list.

        Fitted to ``VALUE_COLS``: roles that do not fit are counted as
        ``+N more`` (``implement 196 · +2 more`` for seat #0), never clipped.
        """
        if not isinstance(roles, list):
            return self._text_fallback("by role")
        parts = []
        for entry in roles:
            if not isinstance(entry, dict):
                continue
            n = _count(entry.get("count"))
            word = sanitize_cell(entry.get("role"), _ROLE_COLS) or "--"
            parts.append(f"{word} {fmt_int(n) if n is not None else '--'}")
        # No indicator: an open-vocabulary list, not a signal -- but its label
        # and its value sit in the signal rows' own columns.
        head = self._head("by role", indicator=" ")
        if not parts:
            return head + Text("none", style="dim")
        return head + Text.from_markup(_fit_roles(parts, VALUE_COLS))
