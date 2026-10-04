"""CONTROL is a pure PANELS consumer of the shared flow projection."""
import re
from collections.abc import Mapping
from rich.text import Text
from textual.widgets import Static
from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import PanelBase

VERB_KEYS = {"r": "restart", "d": "drain-restart", "s": "stop", "S": "start", "b": "enable-boot", "o": "kill-orphans",
             "D": "doctor", "x": "cancel-drain"}
#: The procedures that are NOT verbs in v1 (spec §11): one static line each, no broker round-trip.
STATIC_LINES = (
    "skills, boot, capacity, tiers → CONFIG & SKILLS (3)",
    "update: {installed} → {available} — runbook §2.1 (drained restart)",
)
#: The broker's ``skill_id`` grammar (spec §11 skills row), applied here before an id can enter a plan.
SKILL_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
NODE8_RE = re.compile(r"[0-9a-f]{8}", re.ASCII)
LOCAL_ONLY_ACK = "local-only"
CONFIRM_CHARS = 4
AUDIT_LINES = 20
#: Verbs the idle gate G applies to at apply (spec §11).
GATED_VERBS = ("restart", "stop", "drain-restart")
_VERB_WORDS = {"restart": "restart", "drain-restart": "drain-restart", "stop": "stop", "start": "start", "enable-boot": "enable at boot",
               "disable-boot": "disable at boot", "skills-set": "skill on/off", "kill-orphans": "kill orphans", "doctor": "doctor", "cancel-drain": "cancel drain"}


def _word(value: object) -> str:
    return strip_tags(redact(value)).replace("$", "") if value is not None else ""


def _clock(iso: object) -> str:
    return as_of_hhmm(iso if isinstance(iso, str) else None) or DASH


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def verb_lines(flat: Mapping) -> list[Text]:
    """The verb list with live gate words, from the flat dict (pure; spec §8 CONTROL)."""
    gate = _dict(flat.get("seat_control_gate"))
    in_flight = _dict(flat.get("seat_control_in_flight"))
    drain = _dict(flat.get("seat_control_drain"))
    reachable = flat.get("seat_control_broker_reachable")
    graceful = flat.get("seat_unit_graceful_stop_possible")
    boot = flat.get("seat_unit_boot_enabled")
    orphans = flat.get("seat_machine_orphans") if isinstance(flat.get("seat_machine_orphans"), list) else []
    members = sum(len(o.get("pgidMembers") or []) for o in orphans if isinstance(o, dict))
    audit = flat.get("seat_control_last_audit") if isinstance(flat.get("seat_control_last_audit"), list) else []
    last_doctor = next((a.get("ts") for a in reversed(audit) if isinstance(a, dict) and a.get("verb") == "doctor"), None)
    lines: list[Text] = []

    def gate_words() -> tuple[str, str]:
        if in_flight:
            return f"BUSY: plan {_word(in_flight.get('planId'))[:4]} in flight", "yellow"
        if not gate:
            return "gate unavailable", "yellow"
        if gate.get("safe") is True:
            running = gate.get("planeRunning")
            plane = "none" if running == 0 else (str(running) if running is not None else DASH)
            if gate.get("planeMode") == "local-only":
                plane = f"{DASH} (local-only)"
            last = _word(gate.get("lastLifecycleLine"))
            stamp, _, rest = last.partition(" ")
            verb = rest.split(" ")[0] if rest else DASH
            return (f"safe now (idle {gate.get('idleBeats')} beats · plane running: {plane} · last line {verb} {_clock(stamp)} · outbox {gate.get('outboxFiles')})", "green")
        reason = _word(gate.get("reason")) or "blocked"
        force = " · force disabled (no init)" if graceful is False else " · force: type the running node8"
        if reason.startswith("gate unknown"):
            force = ""
        return f"BLOCKED: {reason}{force}", "red"

    for key, verb in VERB_KEYS.items():
        if verb == "enable-boot" and boot is True:
            verb = "disable-boot"
        word = _VERB_WORDS[verb]
        text = Text(f"[{key}] ", style="bold")
        if reachable is False:
            text.append(f"{word} — broker unreachable — read-only", style="dim")
        elif verb in ("restart", "stop"):
            words, colour = gate_words()
            text.append(f"{word} — ").append(words, style=colour)
        elif verb == "drain-restart":
            armed = f"yes since {_clock(drain.get('armedAtUtc'))} · {drain.get('idleBeats')}/{gate.get('idleBeatsRequired') or 4} idle beats" if drain else "no"
            text.append(f"{word} — waits for {gate.get('idleBeatsRequired') or 4} idle beats, then restarts (armed: {armed})")
        elif verb == "cancel-drain":
            text.append(f"{word} — armed: {'yes' if drain else 'no'}", style="" if drain else "dim")
        elif verb == "start":
            text.append(f"{word} — plain confirm")
        elif verb in ("enable-boot", "disable-boot"):
            if flat.get('seat_host_kind') == 'docker':
                text.append('boot — container restart policy · read-only', style='dim')
            else:
                state = "enabled" if boot is True else ("disabled" if boot is False else DASH)
                text.append(f"{word} — {state}", style="yellow" if boot is False else "")
        elif verb == "skills-set":
            text.append(f"{word} — restart required")
        elif verb == "kill-orphans":
            n = len(orphans)
            text.append(f"{word} — {n} candidate{'s' if n != 1 else ''}" + (f" ({members} pgid member{'s' if members != 1 else ''} shown)" if n else ""),
                        style="yellow" if n else "")
        elif verb == "doctor":
            text.append(f"{word} — spends one runtime turn · last {_clock(last_doctor) if last_doctor else 'never'}")
        lines.append(text)
    return lines


class SeatControl(PanelBase):
    TITLE = 'CONTROL'

    def compose_body(self):
        yield Static('', id='seat-control-body-content')

    def update_data(self, seat_control_gate=None, seat_control_drain=None, seat_control_in_flight=None,
                    seat_control_broker_reachable=None, seat_unit_boot_enabled=None, seat_unit_graceful_stop_possible=None,
                    seat_unit_active_state=None, seat_host_kind=None, seat_machine_orphans=None, seat_daemon_version=None,
                    seat_release_available=None, seat_control_plan=None, seat_control_status=None, seat_control_status_parts=None,
                    seat_control_mode=None, seat_control_last_audit=None, seat_sources=None, **_kwargs):
        flat = {key:value for key,value in locals().items() if key.startswith('seat_')}
        text = Text('\n').join(verb_lines(flat))
        installed = _word(seat_daemon_version) or DASH
        available = _word(seat_release_available) or 'none'
        for line in STATIC_LINES:
            text.append('\n' + line.format(installed=installed, available=available), style='dim')
        plan = seat_control_plan or {}
        if plan:
            text.append(f'\n\nplan {_word(plan.get("planId"))} · {_word(plan.get("verb"))} · expires {_clock(plan.get("expiresAtUtc"))}', style='bold')
            for label, key in (('argv','command'),('preconditions','preconditions'),('warning','warning'),('inverse','inverse'),('verify','verification')):
                if plan.get(key):
                    text.append('\n' + label + ': ' + _word(plan[key]), style='yellow' if key=='warning' else 'dim')
        text.append('\n')
        if seat_control_status_parts:
            for part in seat_control_status_parts:
                text.append(part['text'],style=part['colour'])
        elif seat_control_status:
            text.append(_word(seat_control_status))
        self.write('#seat-control-body-content', text)
