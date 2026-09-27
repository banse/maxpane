"""PEPEPANE hero: SEAT · LIVE · TODAY · VERDICTS · GATE · UNIT (spec §8 HERO).

The 3 a.m. glance: alive?, doing what?, how did today go?, verdicts?, safe to
touch?, will it survive a reboot or an OOM? Six :class:`SeatHeroBox` on a
``HeroRow``; every value is the manager's flat dict (WP1's ``SEAT_KEYS``), so
this file learns no source -- it reads ``seat_sources[<name>]["ok"]`` for the
degraded wordings of the §8 table and nothing else.

**Honest forms, not marks** (plan deviation 6). The spec's wordings do not fit
six boxes at 143 columns (~17 content cells each), so every line is a tuple of
*forms*, longest first, and :func:`fit_forms` paints the first one that fits
the box's content width -- ``widgets/seat_words._num``'s rule ("a shorter
honest number, never a cut one") applied to sentences. Only when the shortest
form still does not fit is it clipped with ``…`` and the box raises
``rowfit.WIDEN_HINT`` in its bottom border, the surf hero's own marker.

**Colour is meaning-bound and red beats amber beats green** (spec §8). The
fold hands the hero its word (``seat_hero_state``, WP7's ``hero_state``);
this widget derives a local word from the LIVE facts it paints (two
``disconnected`` beats, a dead tail, an inactive unit -> red; a stale heartbeat,
a pause, degraded auth -> amber) and paints :func:`worst` of the two, so a
red fact is never painted green. :meth:`SeatHero.hero_colour` is the word
painted; the LIVE box's border takes it (``seat-hero-<word>`` classes).
UNIT's ``docker unavailable`` is amber *in its cell* and never reaches the
hero colour: the tail owns liveness (spec §8 UNIT, §9).

Geometry lives in ``SeatScreen.DEFAULT_CSS`` (spec §8); seven tall = label, blank, three lines.
"""

from __future__ import annotations

from collections.abc import Sequence

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
from maxpane_dashboard.widgets.seat_words import seat_token

__all__ = ["BOX_IDS", "SEVERITY", "SeatHero", "SeatHeroBox", "fit_forms", "worst"]

BOX_IDS = {
    "seat": "seat-hero-seat",
    "live": "seat-hero-live",
    "today": "seat-hero-today",
    "verdicts": "seat-hero-verdicts",
    "gate": "seat-hero-gate",
    "unit": "seat-hero-unit",
}

#: The hero's colour words, least severe first (spec §8: red > amber > green).
SEVERITY = ("green", "amber", "red")

#: Textual border colour per word; ``$success``/``$warning``/``$error`` are
#: required ``Theme`` fields, so they resolve under every theme (status_bar.py).
_BORDER = {"green": "$success", "amber": "$warning", "red": "$error"}

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
        (BOX_IDS["today"], "TODAY"),
        (BOX_IDS["verdicts"], "VERDICTS"),
        (BOX_IDS["gate"], "GATE"),
        (BOX_IDS["unit"], "UNIT"),
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

    def _repaint(self) -> None:
        if self._facts is None:
            return
        self._local = None
        builders = {
            "seat": self._seat_body, "live": self._live_body, "today": self._today_body,
            "verdicts": self._verdicts_body, "gate": self._gate_body, "unit": self._unit_body,
        }
        for key, label in ((box_id, label) for box_id, label in self.BOXES):
            name = key.rsplit("-", 1)[-1]
            room = self._room(key)
            cut: list[bool] = []

            def build(name=name, room=room, cut=cut):
                body, was_cut = builders[name](room)
                cut.append(was_cut)
                return body

            self.render_box(f"#{key}", label, build)
            try:
                self.query_one(f"#{key}").border_subtitle = rowfit.WIDEN_HINT if any(cut) else ""
            except Exception:  # noqa: BLE001
                pass
        self._colour = worst(self._facts.get("seat_hero_state"), self._local)
        for word in SEVERITY:
            self.set_class(self._colour == word, f"seat-hero-{word}")

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
        runtime = _word(f.get("seat_runtime_version")) or _word(f.get("seat_runtime_id")) or DASH
        runtime_id = _word(f.get("seat_runtime_id"))
        runtime_short = f"{runtime_id} {runtime.split()[-1]}" if runtime_id and " " in runtime else runtime
        daemon = _word(f.get("seat_daemon_version")) or DASH
        build = daemon.rsplit("+", 1)[-1][:8]
        avail = _word(f.get("seat_release_available"))
        avail8 = avail.rsplit("+", 1)[-1][:8] if avail else ""
        style = "yellow" if avail else ""
        suffix = " (container)" if f.get("seat_host_kind") == "docker" else ""
        full = f"{runtime} · daemon {daemon}" + (f" [↑ {avail8}]" if avail else "") + suffix
        line2 = fit_forms((
            _t((full, style)),
            _t((f"{runtime} · {build}" + ("↑" if avail else ""), style)),
            _t((runtime_short + (" ↑" if avail else ""), style)),
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
        return _lines(line1, line2, line3)

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
            local = "amber"
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

    # -- TODAY ----------------------------------------------------------------

    def _today_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        tail = self._source("tail")
        if tail.get("ok") is False:
            reason = _word(tail.get("reason")) or "unavailable"
            return _lines(fit_forms((_t((f"ledger unavailable — tail: {reason}", "yellow")), _t(("ledger unavailable", "yellow")),
                                     _t(("unavailable", "yellow"))), room))
        tasks = _count(f.get("seat_today_tasks"))
        if tasks is None:
            return _lines((Text.from_markup(UNAVAILABLE), False))
        if tasks == 0:
            last = f.get("seat_last_task") if isinstance(f.get("seat_last_task"), dict) else {}
            node = _word(last.get("nodeId8")) or DASH
            when = _clock(last.get("acceptedUtc"))
            return _lines(
                fit_forms((_t(("no tasks yet today", "dim")), _t(("none today", "dim"))), room),
                fit_forms((_t((f"last {node} {when}", "dim")), _t((f"last {node}", "dim"))), room),
            )
        stored = _count(f.get("seat_today_stored"))
        not_stored = _count(f.get("seat_today_not_stored"))
        ns_style = "yellow" if not_stored else "dim"
        stored_word = str(stored) if stored is not None else DASH
        ns_word = str(not_stored) if not_stored is not None else DASH
        line1 = fit_forms((
            _t((f"{tasks} tasks", "bold"), (" · ", "dim"), (f"{stored_word} stored", "bold"), (" · ", "dim"), (f"{ns_word} not stored", ns_style)),
            _t((f"{tasks} tasks", "bold"), (" · ", "dim"), (f"{stored_word} stored", "bold")),
            _t((str(tasks), "bold"), (" · ", "dim"), (f"{stored_word} stored", "bold")),
        ), room)
        p50, longest = f.get("seat_today_p50_s"), f.get("seat_today_longest_s")
        line2 = fit_forms((
            _t((f"p50 {_dur(p50)} · longest {_dur(longest)}", "dim")),
            _t((f"p50 {_dur(p50)} · max {_dur_short(longest)}", "dim")),
            _t((f"p50 {_dur(p50)}", "dim")),
        ), room)
        div = f.get("seat_today_divergence") if isinstance(f.get("seat_today_divergence"), dict) else None
        if div is None:
            third = (_t(("local only", "dim")),) if f.get("seat_offline") else (_t((f"plane {EMDASH}", "dim")),)
        else:
            local_n, plane_n = _count(div.get("localStored")), _count(div.get("planeRowsSubmittedToday"))
            ln = str(local_n) if local_n is not None else DASH
            pn = str(plane_n) if plane_n is not None else DASH
            if div.get("ok") is True:
                third = (_t((f"local {ln} = plane {pn} ✓", "green")), _t((f"{ln} = {pn} ✓", "green")))
            else:
                third = (_t((f"⚠ local {ln} ≠ plane {pn} — grammar drift?", "yellow")), _t((f"⚠ {ln} ≠ {pn}", "yellow")))
        return _lines(line1, line2, fit_forms(third, room))

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
        acc, rej, fail, pend = (_count(f.get(k)) for k in ("seat_today_accepted", "seat_today_rejected", "seat_today_failed", "seat_today_pending"))
        life_acc, life_att = _count(f.get("seat_standing_accepted")), _count(f.get("seat_standing_attempts"))
        if src.get("unavailable") is True or (acc is None and life_acc is None):
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
        line1 = fit_forms((_t(("today ", "dim"), *counts), _t(*counts), _t(*short)), room)
        if f.get("seat_standing_counters_inconsistent") is True:
            # spec §6 seats row / §14 proof 36: never the sum, never the API's total
            line2 = fit_forms((_t(("counters inconsistent (api)", "yellow")), _t(("inconsistent (api)", "yellow"))), room)
        else:
            lag = fmt_age(f.get("seat_today_verdict_lag_p50_s"))
            line2 = fit_forms((
                _t((f"life {n(life_acc)} of {n(life_att)} · lag p50 {lag}", "dim")),
                _t((f"{n(life_acc)} of {n(life_att)} · lag {lag}", "dim")),
                _t((f"{n(life_acc)}/{n(life_att)}", "dim")),
            ), room)
        if src.get("ok") is False:
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

    # -- UNIT -----------------------------------------------------------------

    def _unit_body(self, room: int) -> tuple[Text, bool]:
        f = self._facts or {}
        docker = f.get("seat_host_kind") == "docker"
        unit = self._source("unit")
        what = "docker" if docker else "unit"
        when = _clock(unit.get("asOfUtc"))

        def unavailable(reason: str) -> tuple[Text, bool]:
            # Amber in the cell only: the tail owns liveness, so ``self._local`` is untouched (spec §8 UNIT).
            return fit_forms((_t((f"{what} unavailable — {reason} · last {when}", "yellow")), _t((f"unavailable · last {when}", "yellow")),
                              _t(("unavailable", "yellow"))), room)

        if unit.get("ok") is False:
            return _lines(unavailable(_word(unit.get("reason")) or "unavailable"))
        # WP7 deviation 6: one sub-read failed while the other answered (docker ``inspect`` timed out, ``stats``
        # answered -- or the reverse). ``ok`` stays True, the reason rides ``sources.unit`` and the failed half's
        # fields are None. Line 1 says so amber (never a silent ``--``); the half that answered keeps its line.
        # A ``host read failed`` reason leaves every unit field present, so it is MACHINE's to show, not UNIT's.
        partial_reason = _word(unit.get("reason"))
        inspect_missing = f.get("seat_unit_active_state") is None
        stats_missing = f.get("seat_unit_memory_current_b") is None
        partial = bool(partial_reason) and (inspect_missing or stats_missing)
        active = _word(f.get("seat_unit_active_state")) or DASH
        active_style = "green" if active in ("active", "running") else ("red" if active != DASH else "dim")
        mem, peak, mx = _mib(f.get("seat_unit_memory_current_b")), _mib(f.get("seat_unit_memory_peak_b")), _gib(f.get("seat_unit_memory_max_b"))
        restarts = _count(f.get("seat_unit_restarts"))
        restarts_word = str(restarts) if restarts is not None else DASH
        line1 = fit_forms((
            _t((active, active_style), (f" · {mem} / {mx} · peak {peak} · restarts {restarts_word}", "dim")),
            _t((active, active_style), (f" · {mem}/{mx} · peak {peak}", "dim")),
            _t((active, active_style), (f" · {mem}", "dim")),
        ), room)
        boot = f.get("seat_unit_boot_enabled")
        if docker:
            second = (_t(("restart: unless-stopped", "dim")), _t(("unless-stopped", "dim")))
        elif boot is True:
            second = (_t(("boot: enabled", "dim")), _t(("boot ✓", "dim")))
        elif boot is False:
            second = (_t(("boot: disabled ⚠ — a reboot leaves this seat down", "yellow")), _t(("boot: disabled ⚠", "yellow")), _t(("boot ⚠", "yellow")))
        else:
            second = (_t((f"boot: {DASH}", "dim")),)
        graceful = f.get("seat_unit_graceful_stop_possible")
        stop_s = as_float(f.get("seat_unit_stop_timeout_s"))
        stop_word = f"{stop_s:.0f} s" if stop_s is not None else DASH
        kill = _word(f.get("seat_unit_kill_mode")) or "kill mode --"
        if graceful is True:
            third = (_t((f"stop: SIGTERM cgroup-wide, {stop_word} → graceful", "green")), _t((f"stop {stop_word} → graceful", "green")),
                     _t(("graceful ✓", "green")))
        elif graceful is False and docker:
            third = (_t((f"stop-timeout {stop_word} · no init → ungraceful", "yellow")), _t((f"{stop_word} · no init ✗", "yellow")),
                     _t(("ungraceful", "yellow")))
        elif graceful is False:
            third = (_t((f"stop: {kill}, {stop_word} → ungraceful", "yellow")), _t((f"stop {stop_word} → ungraceful", "yellow")),
                     _t(("ungraceful", "yellow")))
        else:
            third = (_t((f"stop: {DASH}", "dim")),)
        if partial:
            kept = [] if inspect_missing and stats_missing else [line1]
            if not inspect_missing:
                kept.append(fit_forms(third, room))   # inspect answered: the stop facts are live
            return _lines(unavailable(partial_reason), *kept)
        return _lines(line1, fit_forms(second, room), fit_forms(third, room))
