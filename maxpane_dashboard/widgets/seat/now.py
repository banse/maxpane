"""NOW: the current task, the plane's view of it, the agent's sentence, the queue, the auth line (spec §8 NOW).

Five ``.panel-line`` Statics (:data:`SeatNow.LINE_IDS`). The task line has four
states -- working (a ``seat_current`` block), plane-assigned (``standing.running[0]``
exists but no local ``accepted`` line yet; the plane leads by 1–4 s, fill5 §1),
idle (the last task, its hash12 and its verdict lag), and ``unavailable (tail: …)``.
The **queue line** is the only keyless answer to "idle because of me or because of
the swarm": ``queue: nothing waiting · 396 online — the network is quiet, not this
machine`` is the wording ``imd doctor`` prints (fill5 §1). It is absent under
``--offline`` and reads ``queue: unavailable (api)`` when the standing read is out.

The agent's sentence (``» …``) is the one line whose bytes a network-selected model
chose, so it goes through ``redact_agent_sentence`` (control characters first, spec
§13) and is **fitted** to the panel with a visible ``…`` -- never CSS-cut, never a
``‹ widen``: the daemon caps it at 160 and its length is the agent's, not a layout
defect (terminal-layout skill, "a caveat the pin does not cover").

Plan deviation 5: the task line says ``on <model>``, not ``<runtime> on <model>`` --
the frozen signature carries no runtime key.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.analytics.seat_redact import redact, redact_agent_sentence
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.analytics.seat_tiers import tier_label
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, EMDASH, as_float, fmt_age
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import LOADING_ROW, PanelBase
from maxpane_dashboard.widgets.seat.hero import _t as text_of
from maxpane_dashboard.widgets.seat.hero import fit_forms, _word, _clock
from maxpane_dashboard.widgets.seat_words import seat_token

__all__ = ["QUIET_NETWORK", "SeatNow"]

#: What ``imd doctor`` prints for an empty queue (fill5 §1) -- the seat's idleness is the swarm's.
QUIET_NETWORK = "the network is quiet, not this machine"

#: The objective is third-party prose; spec §8 shows it at ≤ 80 cells.
_OBJECTIVE_COLS = 80

_count = seat_token






class SeatNow(PanelBase):
    """The present activity of the seat -- see the module docstring."""

    TITLE = "NOW"
    LINE_IDS = ("seat-now-task", "seat-now-plane", "seat-now-sentence", "seat-now-queue", "seat-now-auth")

    #: ``nowrap`` keeps a long line on its row; every line is fitted before it is written.

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._facts: dict | None = None

    def compose_body(self) -> ComposeResult:
        for index, line_id in enumerate(self.LINE_IDS):
            yield Static(LOADING_ROW if index == 0 else "", classes="panel-line", id=line_id)

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        seat_current=None, seat_queue=None, seat_last_task=None, seat_daemon_work=None, seat_daemon_state=None,
        seat_auth_degraded=None, seat_auth_reasons=None, seat_auth_credential_file_mtime_utc=None,
        seat_standing_running=None, seat_sources=None, seat_as_of_hhmm=None, seat_offline=None,
        **_kwargs,
    ) -> None:
        self._facts = {k: v for k, v in locals().items() if k.startswith("seat_")}
        self._repaint()

    def on_resize(self, _event=None) -> None:
        if self._facts is not None:
            self._repaint()

    # -- painting -----------------------------------------------------------

    def _room(self) -> int:
        return max(self.content_region.width - 2, 0)

    def _source(self, name: str) -> dict:
        sources = (self._facts or {}).get("seat_sources")
        source = sources.get(name) if isinstance(sources, dict) else None
        return source if isinstance(source, dict) else {}

    def _repaint(self) -> None:
        if self._facts is None:
            return
        room = self._room()
        f = self._facts
        as_of = f.get("seat_as_of_hhmm") if isinstance(f.get("seat_as_of_hhmm"), dict) else {}
        marker = as_of.get("tail")
        title = self.TITLE + (f" · as of {rowfit.clip(marker, 5)}" if rowfit.has_marker(marker) else "")
        self.write(".panel-title", Text(title))
        lines = (self._task_line(room), self._plane_line(room), self._sentence_line(room), self._queue_line(room), self._auth_line(room))
        for line_id, text in zip(self.LINE_IDS, lines):
            self.write(f"#{line_id}", text)

    def _task_line(self, room: int) -> Text:
        f = self._facts or {}
        tail = self._source("tail")
        if tail.get("ok") is False:
            return text_of((f"unavailable (tail: {_word(tail.get('reason')) or 'unavailable'})", "yellow"))
        current = f.get("seat_current") if isinstance(f.get("seat_current"), dict) else None
        running = f.get("seat_standing_running") if isinstance(f.get("seat_standing_running"), list) else []
        if current is not None:
            node = _word(current.get("nodeId8")) or DASH
            role = _word(current.get("role")) or _word(current.get("kind")) or DASH
            phase = _word(current.get("phase")) or DASH
            elapsed = as_float(current.get("elapsedS"))
            elapsed_word = f"{elapsed:.0f} s" if elapsed is not None else DASH
            max_turns = _count(current.get("maxTurns"))
            model = _word(current.get("model")) or "runtime default"
            tier = tier_label(current.get("tierDerived") if isinstance(current.get("tierDerived"), str) else None)
            turns = f" of max {max_turns} turns" if max_turns is not None else ""
            forms = (
                text_of((node, "bold"), (f" · {role} · {phase} · {elapsed_word}{turns} · on {model} ({tier})", "")),
                text_of((node, "bold"), (f" · {role} · {phase} · {elapsed_word}", "")),
                text_of((node, "bold"), (f" · {phase}", "")),
            )
            return fit_forms(forms, room)[0]
        if running and isinstance(running[0], dict):
            key = _word(running[0].get("nodeKey")) or DASH
            forms = (text_of((f"plane assigned {key} — waiting for the daemon line", "yellow")), text_of((f"plane assigned {key}", "yellow")))
            return fit_forms(forms, room)[0]
        last = f.get("seat_last_task") if isinstance(f.get("seat_last_task"), dict) else None
        if last is None:
            return text_of(("idle · no tasks yet", "dim"))
        since = _clock(last.get("storedUtc") or last.get("acceptedUtc"))
        node = _word(last.get("nodeId8")) or "api"
        hash12 = _word(last.get("hash12"))
        stored = f" stored {hash12}" if hash12 else " not stored"
        outcome = _word(last.get("outcome")) or "unknown"
        lag = fmt_age(last.get("verdictLagS"))
        if f.get("seat_offline") and outcome == "unknown":
            verdict = ("→ local only", "dim")
        elif outcome in ("accepted", "rejected", "failed"):
            verdict = (f"→ {outcome}" + (f" (+{lag})" if lag != DASH else ""), {"accepted": "green"}.get(outcome, "red"))
        elif outcome == "pending":
            verdict = ("→ pending", "yellow")
        else:
            verdict = ("→ ?", "dim")
        forms = (
            text_of((f"idle since {since} · last {node}{stored} ", "dim"), verdict),
            text_of((f"idle since {since} · last {node} ", "dim"), verdict),
            text_of((f"idle since {since}", "dim")),
        )
        return fit_forms(forms, room)[0]

    def _plane_line(self, room: int) -> Text:
        f = self._facts or {}
        current = f.get("seat_current") if isinstance(f.get("seat_current"), dict) else None
        running = f.get("seat_standing_running") if isinstance(f.get("seat_standing_running"), list) else []
        row = current if current and current.get("nodeKey") else (running[0] if running and isinstance(running[0], dict) else None)
        if row is None or self._source("tail").get("ok") is False:
            return Text("")
        key = _word(row.get("nodeKey")) or DASH
        objective = rowfit.clip(_word(row.get("objective")), _OBJECTIVE_COLS)
        when = _clock(self._source("standing").get("asOfUtc"))
        forms = (
            text_of((key, "bold"), (f' · "{objective}" · api {when}', "dim")),
            text_of((key, "bold"), (f" · api {when}", "dim")),
            text_of((key, "bold")),
        )
        return fit_forms(forms, room)[0]

    def _sentence_line(self, room: int) -> Text:
        f = self._facts or {}
        current = f.get("seat_current") if isinstance(f.get("seat_current"), dict) else None
        if current is None or current.get("lastMessage") is None:
            return Text("")
        sentence = strip_tags(redact_agent_sentence(current.get("lastMessage")))
        if not sentence:
            return Text("")
        line = f"» {sentence}"
        return Text(rowfit.clip(line, room) if room else line, style="italic")

    def _queue_line(self, room: int) -> Text:
        f = self._facts or {}
        if f.get("seat_offline"):
            return Text("")
        queue = f.get("seat_queue") if isinstance(f.get("seat_queue"), dict) else None
        if queue is None:
            standing = self._source("standing")
            if standing.get("ok") is False or standing.get("ok") is None:
                return text_of(("queue: unavailable (api)", "yellow"))
            return Text("")
        ready = _count(queue.get("ready"))
        eligible = _count(queue.get("eligible"))
        online = _count(queue.get("fleetOnline"))
        if ready == 0:
            online_word = f"{online} online" if online is not None else f"{DASH} online"
            forms = (text_of(("queue: nothing waiting", "dim"), (f" · {online_word} — {QUIET_NETWORK}", "dim")),
                     text_of(("queue: nothing waiting", "dim"), (f" · {online_word}", "dim")), text_of(("queue: nothing waiting", "dim")))
            return fit_forms(forms, room)[0]
        blocked = queue.get("blocked") if isinstance(queue.get("blocked"), list) else []
        blocks = ", ".join(f"{_word(b.get('reason'))} {_count(b.get('nodes')) if _count(b.get('nodes')) is not None else DASH}"
                           for b in blocked if isinstance(b, dict))
        ready_word = str(ready) if ready is not None else DASH
        eligible_word = str(eligible) if eligible is not None else DASH
        forms = (
            text_of(("queue: ", "dim"), (f"{ready_word} ready", "bold"), (f" · {eligible_word} eligible", "dim"), (f" · blocked: {blocks}" if blocks else "", "dim")),
            text_of(("queue: ", "dim"), (f"{ready_word} ready", "bold"), (f" · {eligible_word} eligible", "dim")),
            text_of(("queue: ", "dim"), (f"{ready_word} ready", "bold")),
        )
        return fit_forms(forms, room)[0]

    def _auth_line(self, room: int) -> Text:
        f = self._facts or {}
        if f.get("seat_auth_degraded") is not True:
            return Text("")
        reasons = f.get("seat_auth_reasons") if isinstance(f.get("seat_auth_reasons"), list) else []
        words = " · ".join(_word(r) for r in reasons if _word(r)) or "reason unknown"
        mtime = f.get("seat_auth_credential_file_mtime_utc")
        refreshed = f"; credential file refreshed {_clock(mtime)} (not read)" if isinstance(mtime, str) else ""
        forms = (
            text_of((f"⚠ runtime auth degraded — {words}{refreshed}", "yellow")),
            text_of((f"⚠ runtime auth degraded — {words}", "yellow")),
            text_of(("⚠ runtime auth degraded", "yellow")),
        )
        return fit_forms(forms, room)[0]
