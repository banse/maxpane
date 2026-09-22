"""SEAT: identity and lifetime details for the selected IDMD seat.

The historical SurfSwarmSeatVerdicts class/module names remain to avoid
unnecessary import churn. Accept rate is accepted / attempts; BY NODE uses
accepted / reviewed. Historical ``win_rate`` remains the contract key. Independent feedback lines keep four-digit backlogs whole.
Runtime/daemon/roles use strip-then-escape; owner metadata uses address_text.
"""
from __future__ import annotations
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import fmt_int, fmt_float
from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.surf._fmt import ANTI_POISONING_COLS, EXPLORER, fmt_win_rate, mmdd_hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import seat_state_line, seat_token

PANEL_MAX_WIDTH = 57
VALUE_COLS = PANEL_MAX_WIDTH - 4
NO_FEEDBACK_LINE = "no scores yet"
_NAMES = ("identity", "owner", "paired", "runtime", "daemon", "attempts",
          "reviewed", "feedback", "queued", "score", "roles")
ROW_IDS = tuple(f"surf-swarm-verdicts-{name}" for name in _NAMES)
BLOCK_IDS = {}

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


class SurfSwarmSeatVerdicts(SignalsPanelBase):
    TITLE = "SEAT"
    ROWS = tuple((row_id, None) for row_id in ROW_IDS)
    DEFAULT_CSS = """
    SurfSwarmSeatVerdicts > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None

    def on_resize(self):
        if self._data is not None:
            self.update_data(**self._data)

    def update_data(self, swarm_seat_summary=None, swarm_seat_selected=None,
                    swarm_seat_state=None, swarm_seat_as_of_hhmm=None, **_kwargs):
        self._data = dict(swarm_seat_summary=swarm_seat_summary,
                         swarm_seat_selected=swarm_seat_selected,
                         swarm_seat_state=swarm_seat_state,
                         swarm_seat_as_of_hhmm=swarm_seat_as_of_hhmm)
        title = self.TITLE
        if rowfit.has_marker(swarm_seat_as_of_hhmm):
            title += f" · as of {swarm_seat_as_of_hhmm}"
        self.write(".panel-title", Text(title))
        selected = swarm_seat_selected if isinstance(swarm_seat_selected, dict) else {}
        line = seat_state_line(swarm_seat_state, selected.get("token_id"))
        if line is not None or not isinstance(swarm_seat_summary, dict):
            for i, row_id in enumerate(ROW_IDS):
                value = line if i == 0 and line is not None else Text("")
                if swarm_seat_state not in ("pending", "unknown_seat"):
                    value = Text("unavailable", style="yellow")
                self.write(f"#{row_id}", value)
            return
        summary = swarm_seat_summary
        for name, row_id in zip(_NAMES, ROW_IDS):
            self.write_guarded(f"#{row_id}", lambda name=name: self._line(name, summary, selected),
                               Text(f"{name} unavailable", style="yellow"))

    def _room(self):
        return max(self.size.width - 2, 0) if self.size.width else VALUE_COLS

    def _word(self, value, width, empty="none"):
        if value is None:
            return "unavailable"
        return sanitize_cell(value, max(width, 0)) if value != "" else empty

    @staticmethod
    def _number(value):
        n = seat_token(value)
        return "unavailable" if n is None else fmt_int(n)

    def _line(self, name, summary, selected):
        room = self._room()
        n = self._number
        if name == "identity":
            token = seat_token(selected.get("token_id"))
            agent = summary.get("agent_id") or selected.get("agent_id")
            return Text.from_markup(f"IDMD #{token if token is not None else '--'} · agent {self._word(agent, 12)}")
        if name == "owner":
            owner = summary.get("owner")
            return Text("owner ") + (address_text(owner, width=ANTI_POISONING_COLS, explorer=EXPLORER)
                                     if isinstance(owner, str) else Text("unavailable"))
        if name == "paired":
            stamp = mmdd_hhmm(summary["paired_ts"]) if summary.get("paired_ts") is not None else "unavailable"
            online = {True:"online ●",False:"offline ○"}.get(summary.get("online"),"unavailable")
            return Text(f"paired {stamp} · {online}")
        if name == "runtime":
            return Text.from_markup("runtime " + self._word(summary.get("runtime"), room-8))
        if name == "daemon":
            devices = n(summary.get("devices"))
            tail = f" · {devices} device" + ("" if summary.get("devices") == 1 else "s")
            daemon = self._word(summary.get("daemon"), room-7-rowfit.cell_len(tail), "not reported")
            return Text.from_markup("daemon " + daemon + tail)
        if name == "attempts":
            rate = summary.get("win_rate")
            suffix = " (no attempts)" if summary.get("attempts") == 0 else (
                f" ({fmt_win_rate(rate)} of attempts)" if isinstance(rate, (float, int)) and not isinstance(rate, bool) else "")
            return Text(f"attempts {n(summary.get('attempts'))} · accepted {n(summary.get('accepted'))}{suffix}")
        if name == "reviewed":
            reviewed, entries = summary.get("reviewed"), summary.get("review_entries")
            text = f"reviewed {n(reviewed)} submissions"
            if reviewed is not None and entries is not None and reviewed != entries:
                text += f" · {n(entries)} entries served"
            return Text(text)
        status = summary.get("review_status") or {}
        if name == "feedback":
            return Text(f"feedback {n(status.get('sent'))} sent · {n(status.get('submitted'))} submitted")
        if name == "queued":
            return Text(f"         {n(status.get('queued'))} queued")
        if name == "score":
            mean = summary.get("mean_score")
            value = NO_FEEDBACK_LINE if mean is None and summary.get("scored") == 0 else (
                f"{fmt_float(mean, '.2f')} on {n(summary.get('scored'))} scored" if mean is not None else "unavailable")
            return Text(f"score {value}")
        roles = summary.get("roles")
        if not isinstance(roles, list):
            return Text("by role unavailable")
        parts = [f"{sanitize_cell(r.get('role'),16)} {n(r.get('count'))}" for r in roles if isinstance(r,dict)]
        return Text.from_markup("by role " + (_fit_roles(parts, room-8) if parts else "none"))
