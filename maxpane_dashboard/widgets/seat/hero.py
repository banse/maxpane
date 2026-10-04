"""Six selectable dashboard cards; selection borders and health labels are independent."""

from __future__ import annotations

from collections.abc import Sequence
import re
from textual.message import Message

from rich.text import Text

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import (
    DISCONNECTED_BEATS_RED,
    HEARTBEAT_STALE_S,
    as_of_hhmm,
    gate_preview,
)
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, EMDASH, as_float, fmt_age, fmt_int
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.seat_words import NODE_TITLES, seat_token

__all__ = ["BOX_IDS", "SEVERITY", "SeatHero", "SeatHeroBox", "fit_forms", "worst"]

BOX_IDS = {
    "seat": "seat-hero-seat",
    "live": "seat-hero-live",
    "config": "seat-hero-config",
    "records": "seat-hero-records",
    "nodes": "seat-hero-nodes",
    "control": "seat-hero-control",
}

#: The hero's colour words, least severe first (spec §8: red > amber > green).
SEVERITY = ("green", "amber", "red")

_count = seat_token


def worst(*states: object) -> str | None:
    """The most severe of *states* that is a colour word; ``None`` when none is."""
    known = [s for s in states if isinstance(s, str) and s in SEVERITY]
    if not known:
        return None
    return max(known, key=SEVERITY.index)


def fit_forms(forms: Sequence[Text], room: int) -> tuple[Text, bool]:
    """The first of *forms* that fits *room* cells; else the last, clipped with ``…``.

    ``room <= 0`` means "not laid out yet" and picks the longest form
    (``rowfit.tier_for``'s convention). The flag says whether a cut happened --
    a shorter *form* is not a cut.
    """
    if not forms:
        return Text(), False
    if room <= 0:
        return forms[0], False
    for form in forms:
        if form.cell_len <= room:
            return form, False
    last = forms[-1].copy()
    last.truncate(room, overflow="ellipsis")
    return last, True


def _t(*parts: tuple[str, str] | str) -> Text:
    """A ``Text`` from ``(words, style)`` pairs (a bare string is unstyled). Nothing is parsed."""
    out = Text()
    for part in parts:
        if isinstance(part, str):
            out.append(part)
        else:
            out.append(part[0], style=part[1] or None)
    return out


def _word(value: object) -> str:
    """A third-party string redacted, tag-stripped and flattened; ``""`` for nothing."""
    return strip_tags(redact(value)) if value is not None else ""


def _clock(iso: object) -> str:
    return as_of_hhmm(iso if isinstance(iso, str) else None) or DASH


def _dur(seconds: object) -> str:
    """``32 s`` · ``4 m 12 s`` · ``1 h 05 m`` · ``1 d 11 h``; ``--`` for unknown."""
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 10 and s != int(s):
        return f"{s:.1f} s"
    if s < 60:
        return f"{s:.0f} s"
    minutes, sec = divmod(int(s), 60)
    if minutes < 60:
        return f"{minutes} m {sec:02d} s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes:02d} m"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"


def _dur_short(seconds: object) -> str:
    """``4m12s`` -- the same duration without spaces, for a narrow form."""
    return _dur(seconds).replace(" ", "")


def _mmss(seconds: object) -> str:
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    minutes, sec = divmod(int(s), 60)
    return f"{minutes}:{sec:02d}"


def _mib(value: object) -> str:
    b = as_float(value)
    return DASH if b is None or b < 0 else f"{b / 2 ** 20:.0f} MiB"


def _gib(value: object) -> str:
    b = as_float(value)
    if b is None or b < 0:
        return DASH
    g = b / 2 ** 30
    return f"{g:.0f} G" if g == int(g) else f"{g:.1f} G"


def _lines(*lines: tuple[Text, bool]) -> tuple[Text, bool]:
    """Join fitted lines with newlines; the flag is any line's cut."""
    body = Text()
    cut = False
    for index, (text, was_cut) in enumerate(lines):
        if index:
            body.append("\n")
        body.append_text(text)
        cut = cut or was_cut
    return body, cut


class SeatHeroBox(HeroBoxBase):
    """One box of the PEPEPANE hero; its geometry is :attr:`SeatScreen.DEFAULT_CSS`'s."""


class SeatHero(HeroRow):
    """Six boxes for one seat -- see the module docstring."""

    BOX_CLASS = SeatHeroBox
    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["live"], "LIVE"),
        (BOX_IDS["config"], "CONFIG & SKILLS"),
        (BOX_IDS["records"], "RECORDS"),
        (BOX_IDS["nodes"], "NODES"),
        (BOX_IDS["control"], "CONTROL"),
    )

    #: Seven tall: label, blank, three value lines, inside a one-cell border.
    #: ``text-overflow: ellipsis`` is a backstop the layout sweep treats as a
    #: defect at the pin (``_css_clipped_lines``); :func:`fit_forms` fits first.

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._facts: dict | None = None
        self._colour: str | None = None
        self._local: str | None = None

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        seat_token_id=None, seat_agent_id=None, seat_eligibility=None, seat_runtime_id=None, seat_runtime_version=None,
        seat_daemon_version=None, seat_release_available=None, seat_skills_offered=None, seat_skills_on=None, seat_capacity=None,
        seat_daemon_state=None, seat_daemon_uptime=None, seat_daemon_work=None, seat_daemon_running=None,
        seat_daemon_heartbeat_age_s=None, seat_daemon_consecutive_disconnected_beats=None, seat_daemon_paused_hint=None,
        seat_daemon_fleet_online=None, seat_daemon_fleet_enrolled=None, seat_daemon_last_admitted_utc=None, seat_daemon_offline=None,
        seat_auth_degraded=None, seat_auth_since_utc=None, seat_current=None,
        seat_today_tasks=None, seat_today_stored=None, seat_today_not_stored=None, seat_today_p50_s=None, seat_today_longest_s=None,
        seat_today_divergence=None, seat_last_task=None,
        seat_today_accepted=None, seat_today_rejected=None, seat_today_failed=None, seat_today_pending=None, seat_today_verdict_lag_p50_s=None,
        seat_standing_attempts=None, seat_standing_accepted=None, seat_standing_counters_inconsistent=None, seat_standing_paused_until=None,
        seat_control_broker_reachable=None, seat_control_gate=None, seat_control_drain=None, seat_control_in_flight=None, seat_control_last_audit=None,
        seat_unit_active_state=None, seat_unit_memory_current_b=None, seat_unit_memory_peak_b=None, seat_unit_memory_max_b=None,
        seat_unit_restarts=None, seat_unit_boot_enabled=None, seat_unit_kill_mode=None, seat_unit_stop_timeout_s=None,
        seat_unit_graceful_stop_possible=None,
        seat_hero_state=None, seat_hero_reasons=None, seat_sources=None, seat_as_of_hhmm=None, seat_offline=None, seat_host_kind=None,
        seat_nodes_all_rows=None, seat_nodes_coverage=None, seat_control_restart_required=None, seat_config_changed_since_start=None,
        **_kwargs,
    ) -> None:
        """Store the facts and repaint all six boxes (``**_kwargs``: the screen may splat)."""
        self._facts = {k: v for k, v in locals().items() if k.startswith("seat_")}
        self._repaint()

    def hero_colour(self) -> str | None:
        """The colour word painted on the last repaint: ``"green" | "amber" | "red" | None``."""
        return self._colour

    def on_resize(self, _event=None) -> None:
        if self._facts is not None:
            self._repaint()

    # -- painting -----------------------------------------------------------

    def _room(self, box_id: str) -> int:
        try:
            return max(self.query_one(f"#{box_id}").content_region.width, 0)
        except Exception:  # noqa: BLE001 -- not composed yet
            return 0

    def _source(self, name: str) -> dict:
        sources = (self._facts or {}).get("seat_sources")
        source = sources.get(name) if isinstance(sources, dict) else None
        return source if isinstance(source, dict) else {}

    class Selected(Message):
        def __init__(self, dashboard: str):
            super().__init__()
            self.dashboard = dashboard

    def select_dashboard(self, dashboard: str) -> None:
        for box_id, label in self.BOXES:
            self.query_one(f"#{box_id}").set_class(label == dashboard, "seat-selected")

    def on_click(self, event) -> None:
        widget = event.widget
        while widget is not None and widget is not self:
            for box_id, label in self.BOXES:
                if widget.id == box_id:
                    self.post_message(self.Selected(label))
                    event.stop()
                    return
            widget = widget.parent

    def _label_state(self, name: str) -> str | None:
        f = self._facts or {}
        if name == "seat":
            if f.get("seat_unit_active_state") not in (None, "active", "running", "activating", "reloading"):
                return "red"
            return "amber" if f.get("seat_unit_boot_enabled") is False else None
        if name == "live":
            return worst(f.get("seat_hero_state"), self._local)
        if name == "config":
            if self._source("seat").get("ok") is False and "refus" in _word(self._source("seat").get("reason")):
                return "red"
            if f.get("seat_control_restart_required") or f.get("seat_config_changed_since_start"):
                return "amber"
        if name == "control":
            if f.get("seat_control_broker_reachable") is False:
                return "amber"
            gate = f.get("seat_control_gate")
            if gate is None or (isinstance(gate, dict) and (gate.get("safe") is not True and (not gate.get("reason") or str(gate.get("reason")).startswith("gate unknown")))):
                return "red"
            if f.get("seat_control_drain") or f.get("seat_control_in_flight"):
                return "amber"
        return None

    def _repaint(self) -> None:
        if self._facts is None:
            return
        self._local = None
        builders = {"seat": self._seat_body, "live": self._live_body, "config": self._config_body,
                    "records": self._verdicts_body, "nodes": self._nodes_body, "control": self._gate_body}
        for box_id, label in self.BOXES:
            name = box_id.rsplit("-", 1)[-1]
            room = self._room(box_id)
            body, cut = builders[name](room)
            severity = self._label_state(name)
            warning = severity in ("amber", "red")
            style = {"amber": "yellow", "red": "red"}.get(severity, "dim")
            heading, heading_cut = fit_forms((Text(label + (" ⚠" if warning else ""), style=style),), room)
            content = Text()
            content.append_text(heading)
            content.append("\n\n")
            content.append_text(body)
            self.write_box(box_id, content, cut or heading_cut)
        self._colour = worst(self._facts.get("seat_hero_state"), self._local)

    def write_box(self, box_id: str, content: Text, cut: bool):
        try:
            box = self.query_one(f"#{box_id}")
            box.update(content)
            box.border_subtitle = rowfit.WIDEN_HINT if cut else ""
        except Exception:
            pass  # before composition; the resize repaint uses the retained facts

    # -- SEAT -----------------------------------------------------------------

    def _seat_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        token = _count(f.get("seat_token_id"))
        idmd = f"IDMD #{token if token is not None else DASH}"
        agent = _count(f.get("seat_agent_id"))
        agent_word = f"agent {agent}" if agent is not None else f"agent {EMDASH if f.get('seat_offline') else DASH}"
        status = self._source("status")
        if status.get("ok") is False:
            reason = _word(status.get("reason")) or "unavailable"
            return _lines(
                fit_forms((_t((f"{idmd} (saved) — imd status unavailable", "bold")), _t((f"{idmd} (saved)", "bold")), _t((idmd, "bold"))), room),
                fit_forms((_t((f"broker: {reason}", "yellow")), _t(("unavailable", "yellow"))), room),
                fit_forms((_t((agent_word, "dim")),), room),
            )
        elig = _word(f.get("seat_eligibility"))
        elig_short = "eligible" if elig.startswith("eligible") else (rowfit.clip(elig, 12) if elig else DASH)
        line1 = fit_forms((
            _t((f"{idmd} · {agent_word} · {elig_short}", "bold")),
            _t((f"{idmd} · {agent_word}", "bold")),
            _t((f"{idmd} · {agent if agent is not None else DASH}", "bold")),
        ), room)
        unit = self._source("unit")
        active = _word(f.get("seat_unit_active_state")) or DASH
        boot = f.get("seat_unit_boot_enabled") is False
        suffix = " · boot ⚠" if boot else ""
        style = "yellow" if boot else "dim"
        if unit.get("ok") is False or (unit.get("reason") and f.get("seat_unit_active_state") is None):
            reason = _word(unit.get("reason")) or "unavailable"
            what = "docker" if f.get("seat_host_kind") == "docker" else "unit"
            memory = f" · {_mib(f.get('seat_unit_memory_current_b'))}" if f.get("seat_unit_memory_current_b") is not None else ""
            forms = (f"{what} unavailable — {reason}{memory}", f"{what} unavailable", "unavailable")
            style = "yellow"
        else:
            forms = (f"{active} · {_mib(f.get('seat_unit_memory_current_b'))} / {_gib(f.get('seat_unit_memory_max_b'))}{suffix}",
                     f"{active} · {_mib(f.get('seat_unit_memory_current_b'))}{suffix}", f"{active}{suffix}")
        line2 = fit_forms(tuple(Text(word, style=style) for word in forms), room)
        tasks, stored = _count(f.get("seat_today_tasks")), _count(f.get("seat_today_stored"))
        if self._source("tail").get("ok") is False:
            forms = (f"ledger unavailable — tail: {_word(self._source('tail').get('reason'))}", "ledger unavailable", "unavailable")
        elif tasks is None:
            forms = ("today unavailable", "unavailable")
        elif tasks == 0:
            forms = ("no tasks yet today", "none today")
        else:
            forms = (f"today {tasks} tasks · {stored if stored is not None else DASH} stored",
                     f"{tasks} tasks · {stored if stored is not None else DASH} stored", f"{tasks} · {stored if stored is not None else DASH} stored")
        return _lines(line1, line2, fit_forms(tuple(Text(word, style="dim") for word in forms), room))

    def _config_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        runtime = _word(f.get("seat_runtime_version")) or _word(f.get("seat_runtime_id")) or DASH
        runtime_id = _word(f.get("seat_runtime_id"))
        version = re.search(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?", runtime)
        runtime_short = f"{runtime_id} {version.group(0)}" if runtime_id and version else runtime
        daemon = _word(f.get("seat_daemon_version")) or DASH
        build = daemon.rsplit("+", 1)[-1][:8]
        avail = _word(f.get("seat_release_available"))
        avail8 = avail.rsplit("+", 1)[-1][:8] if avail else ""
        style = "yellow" if avail else ""
        suffix = " (container)" if f.get("seat_host_kind") == "docker" else ""
        full = f"{runtime} · daemon {daemon}" + (f" [↑ {avail8}]" if avail else "") + suffix
        line2 = fit_forms((
            _t((full, style)),
            _t((f"{runtime_short} · {build}" + ("↑" if avail else "") + suffix, style)),
            _t((runtime_short + (" ↑" if avail else "") + suffix, style)),
        ), room)
        on, offered = _count(f.get("seat_skills_on")), _count(f.get("seat_skills_offered"))
        skills = f"{on}/{offered}" if on is not None and offered is not None else DASH
        cap = _count(f.get("seat_capacity"))
        cap_word = str(cap) if cap is not None else DASH
        line3 = fit_forms((
            _t((f"skills {skills} · capacity {cap_word}", "dim")),
            _t((f"skills {skills} · cap {cap_word}", "dim")),
            _t((f"{skills} · cap {cap_word}", "dim")),
        ), room)
        changed = f.get("seat_config_changed_since_start")
        if f.get("seat_control_restart_required"):
            words, style = "restart required", "yellow"
        elif changed is True:
            words, style = "changed since start", "yellow"
        elif changed is False:
            words, style = "unchanged since start", "dim"
        else:
            words, style = "change unavailable", "yellow"
        return _lines(line2, line3, fit_forms((Text(words, style=style), Text(words.split(" since")[0], style=style)), room))

    # -- LIVE -----------------------------------------------------------------

    def _live_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        tail = self._source("tail")
        hb = as_float(f.get("seat_daemon_heartbeat_age_s"))
        hb_word = f"{hb:.0f} s" if hb is not None else DASH
        beats = _count(f.get("seat_daemon_consecutive_disconnected_beats")) or 0
        running = _count(f.get("seat_daemon_running")) or 0
        state = _word(f.get("seat_daemon_state"))
        uptime = _word(f.get("seat_daemon_uptime")) or DASH
        current = f.get("seat_current") if isinstance(f.get("seat_current"), dict) else None
        local: str | None
        if tail.get("ok") is False:
            when = _clock(tail.get("asOfUtc"))
            first = ((f"tail died {when} — restarting", "red"), (f"tail died {when}", "red"), ("tail died", "red"))
            local = "red"
        elif f.get("seat_unit_active_state") not in (None, "active"):
            active = _word(f.get("seat_unit_active_state"))
            when = _clock(self._source("unit").get("asOfUtc"))
            first = ((f"○ unit inactive since {when}", "red"), (f"○ unit {active}", "red"), ("○ inactive", "red"))
            local = "red"
        elif beats >= DISCONNECTED_BEATS_RED or f.get("seat_daemon_offline") is True:
            first = ((f"○ disconnected {beats} beats · reconnecting", "red"), (f"○ disconnected ×{beats}", "red"), ("○ offline", "red"))
            local = "red"
        elif hb is not None and hb > HEARTBEAT_STALE_S:
            said = state or "alive"
            first = ((f"◐ heartbeat {hb:.0f} s old — last said {said}", "yellow"), (f"◐ hb {hb:.0f} s · was {said}", "yellow"), (f"◐ hb {hb:.0f} s old", "yellow"))
            local = "amber"
        elif running > 0 and current is not None:
            node = _word(current.get("nodeId8")) or DASH
            elapsed = _mmss(current.get("elapsedS"))
            phase = _word(current.get("phase")) or "working"
            plural = "s" if running > 1 else ""
            first = ((f"⚙ {running} task{plural} · {node} · {elapsed} · {phase}", "green"), (f"⚙ {node} · {elapsed}", "green"), (f"⚙ {node}", "green"))
            local = "green"
        elif running > 0:
            plural = "s" if running > 1 else ""
            first = ((f"⚙ {running} task{plural} running", "yellow"),)
            local = "green"
        elif state == "alive":
            first = ((f"● alive {uptime} · idle · hb {hb_word}", "green"), (f"● alive {uptime} · idle", "green"), ("● alive · idle", "green"))
            local = "green"
        elif state:
            # One ``disconnected`` beat is not the seat's fault (spec §3 B, §6 rule 3): said, not coloured.
            first = ((f"○ {state} {uptime}", "dim"), (f"○ {state}", "dim"))
            local = "green"
        else:
            first = (("unavailable", "yellow"),)
            local = None
        line1 = fit_forms(tuple(_t(part) for part in first), room)
        line2 = fit_forms((_t((f"up {uptime} · hb {hb_word}", "dim")), _t((f"hb {hb_word}", "dim"))), room)
        third, third_colour = self._live_third_line()
        line3 = fit_forms(third, room)
        self._local = worst(self._local, local, third_colour)
        return _lines(line1, line2, line3)

    def _live_third_line(self) -> tuple[tuple[Text, ...], str | None]:
        f = self._facts or {}
        hint = f.get("seat_daemon_paused_hint") if isinstance(f.get("seat_daemon_paused_hint"), dict) else None
        fold_amber = f.get("seat_hero_state") in ("amber", "red")
        paused_api = isinstance(f.get("seat_standing_paused_until"), str) and f.get("seat_standing_paused_until")
        if paused_api or (hint and fold_amber):
            until = _clock(paused_api) if paused_api else (_word(hint.get("until")) if hint else DASH)
            runs = _count(hint.get("failedRuns")) if hint else None
            runs_word = f" · {runs} failed runs (api)" if runs is not None else ""
            return (_t((f"⏸ paused until {until}{runs_word}", "yellow")), _t((f"⏸ paused → {until}", "yellow")),
                    _t(("⏸ paused", "yellow"))), "amber"
        if hint:
            # Review Focus #3: the lingering suffix after ``until`` has passed is said dim, never ambered.
            until = _word(hint.get("until")) or DASH
            return (_t((f"paused earlier until {until}", "dim")), _t((f"paused earlier {until}", "dim")), _t(("paused earlier", "dim"))), None
        if f.get("seat_auth_degraded") is True:
            since = _clock(f.get("seat_auth_since_utc"))
            return (_t((f"⚠ runtime auth degraded since {since}", "yellow")), _t(("⚠ auth degraded", "yellow")),
                    _t(("⚠ auth", "yellow"))), "amber"
        audit = f.get("seat_control_last_audit")
        newest = audit[-1] if isinstance(audit, list) and audit and isinstance(audit[-1], dict) else None
        if newest and newest.get("verb") in ("restart", "start") and newest.get("phase") in ("apply", "verify"):
            when = _clock(newest.get("ts"))
            connected = newest.get("connected")
            if connected is True:
                return (_t((f"↻ restarted {when} · connected", "dim")), _t((f"↻ {when} ✓", "dim"))), None
            pending = _word(connected)
            since = pending.rsplit(" ", 1)[-1].rstrip(")") if "since" in pending else when
            return (_t((f"↻ restarted {when} · reconnecting since {since}", "yellow")),
                    _t((f"↻ {when} · reconnecting", "yellow")), _t((f"↻ {when} …", "yellow"))), "amber"
        online, enrolled = _count(f.get("seat_daemon_fleet_online")), _count(f.get("seat_daemon_fleet_enrolled"))
        if online is not None and enrolled is not None:
            return (_t((f"fleet {online} online · {enrolled} enrolled", "dim")), _t((f"fleet {online}/{enrolled}", "dim"))), None
        return (Text(""),), None

    # -- VERDICTS -------------------------------------------------------------

    def _verdicts_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        if f.get("seat_offline"):
            stored = _count(f.get("seat_today_stored"))
            stored_word = str(stored) if stored is not None else DASH
            return _lines(
                fit_forms((_t((f"stored {stored_word} today", "bold")), _t((f"{stored_word} stored", "bold"))), room),
                fit_forms((_t(("local only (stored ≠ accepted)", "dim")), _t(("local only", "dim"))), room),
            )
        src = self._source("seatWork")
        when = _clock(src.get("asOfUtc"))
        reason = _word(src.get("reason"))
        standing = self._source("standing")
        if not (src.get("ok") is False or src.get("unavailable") is True) and (
            standing.get("ok") is False or standing.get("unavailable") is True
        ):
            src = standing
            when = _clock(src.get("asOfUtc"))
            reason = f"standing: {_word(src.get('reason')) or 'unavailable'}"
        acc, rej, fail, pend = (_count(f.get(k)) for k in ("seat_today_accepted", "seat_today_rejected", "seat_today_failed", "seat_today_pending"))
        life_acc, life_att = _count(f.get("seat_standing_accepted")), _count(f.get("seat_standing_attempts"))
        # Source availability describes this read; populated ledger facts survive it.
        if all(value is None for value in (acc, rej, fail, pend, life_acc, life_att)):
            return _lines(
                fit_forms((_t(("verdicts unavailable", "yellow")), _t(("unavailable", "yellow"))), room),
                fit_forms((_t((reason or "api", "dim")),), room),
                fit_forms((_t((f"last {when}", "dim")),), room),
            )

        def n(value):
            return str(value) if value is not None else DASH

        def colour(value, ok_style):
            return ok_style if value else "dim"

        counts = ((f"acc {n(acc)}", colour(acc, "green")), (" · ", "dim"), (f"rej {n(rej)}", colour(rej, "red")), (" · ", "dim"),
                  (f"fail {n(fail)}", colour(fail, "red")), (" · ", "dim"), (f"pend {n(pend)}", colour(pend, "yellow")))
        short = ((f"{n(acc)}a", colour(acc, "green")), (" · ", "dim"), (f"{n(rej)}r", colour(rej, "red")), (" · ", "dim"),
                 (f"{n(fail)}f", colour(fail, "red")), (" · ", "dim"), (f"{n(pend)}p", colour(pend, "yellow")))
        tight = tuple((" " if word == " · " else word, style) for word, style in short)
        if all(value is None for value in (acc, rej, fail, pend)):
            line1 = fit_forms((_t(("today unavailable", "dim")),), room)
        else:
            line1 = fit_forms((_t(("today ", "dim"), *counts), _t(*counts), _t(*short), _t(*tight)), room)
        if f.get("seat_standing_counters_inconsistent") is True:
            # spec §6 seats row / §14 proof 36: never the sum, never the API's total
            line2 = fit_forms((_t(("counters inconsistent (api)", "yellow")), _t(("inconsistent (api)", "yellow"))), room)
        elif life_acc is None and life_att is None:
            line2 = fit_forms((_t(("life unavailable", "dim")),), room)
        else:
            lag = fmt_age(f.get("seat_today_verdict_lag_p50_s"))
            line2 = fit_forms((
                _t((f"life {n(life_acc)} of {n(life_att)} · lag p50 {lag}", "dim")),
                _t((f"{n(life_acc)} of {n(life_att)} · lag {lag}", "dim")),
                _t((f"{n(life_acc)}/{n(life_att)}", "dim")),
            ), room)
        if src.get("ok") is False or src.get("unavailable") is True:
            line3 = fit_forms((_t((f"⚠ {reason or 'api'} · last {when}", "yellow")), _t((f"⚠ {reason or 'api'}", "yellow")),
                               _t(("⚠ retrying", "yellow"))), room)
        else:
            line3 = fit_forms((_t((f"api · as of {when}", "dim")), _t((f"api {when}", "dim"))), room)
        return _lines(line1, line2, line3)

    # -- GATE -----------------------------------------------------------------

    def _gate_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        gate = f.get("seat_control_gate") if isinstance(f.get("seat_control_gate"), dict) else None
        flight = f.get("seat_control_in_flight") if isinstance(f.get("seat_control_in_flight"), dict) else None
        drain = f.get("seat_control_drain") if isinstance(f.get("seat_control_drain"), dict) else None
        if flight is not None:
            verb = _word(flight.get("verb")) or "verb"
            plan4 = _word(flight.get("planId"))[:4] or DASH
            first = (_t((f"{verb} in flight (plan {plan4}) · verifying", "yellow")), _t((f"in flight ({plan4})", "yellow")), _t(("in flight", "yellow")))
            colour = "amber"
        elif drain is not None:
            when = _clock(drain.get("armedAtUtc"))
            idle = _count(drain.get("idleBeats"))
            req = _count((gate or {}).get("idleBeatsRequired")) or 4
            idle_word = str(idle) if idle is not None else DASH
            first = (_t((f"drain armed {when} · {idle_word}/{req} idle beats", "yellow")), _t((f"drain {when} · {idle_word}/{req}", "yellow")),
                     _t(("drain armed", "yellow")))
            colour = "amber"
        else:
            word, colour = gate_preview(gate, broker_reachable=f.get("seat_control_broker_reachable"))
            word = _word(word) or "unavailable"
            colour = {"yellow": "amber"}.get(colour, colour) if isinstance(colour, str) else None
            style = {"green": "green", "amber": "yellow", "red": "red"}.get(colour or "", "yellow")
            forms = [word]
            for sep in (" — ", " · "):
                head = word.split(sep)[0]
                if head != word and head not in forms:
                    forms.append(head)
            if word.startswith("broker unreachable"):
                forms.append("read-only")
            first = tuple(_t((form, style)) for form in forms)
        line1 = fit_forms(first, room)
        if gate is None:
            return _lines(line1)
        idle = _count(gate.get("idleBeats"))
        req = _count(gate.get("idleBeatsRequired")) or 4
        idle_word = str(idle) if idle is not None else DASH
        running = _count(gate.get("planeRunning"))
        if gate.get("planeMode") == "local-only":
            plane = f"plane {EMDASH} (local-only)"
            plane_short = "local-only"
        else:
            plane = "plane []" if running == 0 else f"plane running {running if running is not None else DASH}"
            plane_short = "plane ok" if running == 0 else f"plane {running if running is not None else DASH}"
        line2 = fit_forms((_t((f"idle {idle_word} beats · {plane}", "dim")), _t((f"idle {idle_word} · {plane_short}", "dim")),
                           _t((f"idle {idle_word}/{req}", "dim"))), room)
        last = _word(gate.get("lastLifecycleLine"))
        stamp, _, rest = last.partition(" ")
        verb = rest.split(" ")[0] if rest else DASH
        when = _clock(stamp) if stamp else DASH
        outbox = _count(gate.get("outboxFiles"))
        outbox_word = str(outbox) if outbox is not None else "?"
        outbox_style = "red" if outbox is None else "dim"
        line3 = fit_forms((
            _t((f"last line {verb} {when} · ", "dim"), (f"outbox {outbox_word}", outbox_style)),
            _t((f"outbox {outbox_word}", outbox_style), (f" · {when}", "dim")),
            _t((f"outbox {outbox_word}", outbox_style)),
        ), room)
        return _lines(line1, line2, line3)

    def _nodes_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        rows = f.get("seat_nodes_all_rows")
        if not isinstance(rows, list) or not rows:
            coverage = f.get("seat_nodes_coverage") or {}
            return _lines(fit_forms((Text("nodes unavailable", style="yellow"),), room),
                          fit_forms((Text(_word(coverage.get("reason")) or "no rows yet", style="dim"),), room))
        attempts = sum(_count(r.get("attempts")) or 0 for r in rows)
        accepted = sum(_count(r.get("accepted")) or 0 for r in rows)
        rate = f"{100 * accepted / attempts:.0f} %" if attempts else DASH
        top = max(rows, key=lambda r: _count(r.get("attempts")) or 0)
        top_rate = as_float(top.get("acceptedPercent"))
        paid = [r.get("paid") for r in rows if _count(r.get("paid")) is not None]
        launch = [r.get("launch") for r in rows if _count(r.get("launch")) is not None]
        node = _word(top.get('nodeKey'))
        rate_suffix = f" · {top_rate:.0f} %" if top_rate is not None else ""
        node_forms = (Text(node + rate_suffix), Text(NODE_TITLES.get(node, node) + rate_suffix))
        paid_count, launch_count = sum(paid) if paid else '·', sum(launch) if launch else '·'
        return _lines(
            fit_forms((Text(f"{len(rows)} node types · {rate} accepted"), Text(f"{len(rows)} types · {rate}")), room),
            fit_forms(node_forms, room),
            fit_forms((Text(f"paid {paid_count} · launch {launch_count}", style="dim"),
                       Text(f"paid{paid_count} launch{launch_count}", style="dim")), room))
