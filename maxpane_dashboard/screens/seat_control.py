"""CONTROL: the fixed verb set through the broker, plan → typed confirm → apply → verify (spec §8 CONTROL, §11).

The TUI stays read-only (spec §11 charter break): every write here is a broker
verb, two-phase and race-free on the broker's side (single-use plan ids, one
write in flight). This modal owns the operator's side of it:

* the verb list with **live gate words** (``safe now (idle 9 beats · plane
  running: none · …)``, ``BLOCKED: 1 task running 0:42 · force disabled (no init)``,
  ``BUSY: plan 7f3a in flight``) and three **static lines with no broker
  round-trip** for the procedures that are not verbs in v1 (tiers, capacity,
  update -- spec §11 "Not verbs in v1");
* ``plan`` shows the broker's plan block (argv, preconditions incl. ``standing_age_s``
  and ``last_lifecycle_line``, warning, inverse, verify expectation);
* ``apply`` needs the plan id's first four characters typed within its 60 s;
  a **forced** restart needs the running node8 typed at plan **and** at apply
  and is disabled when a graceful stop is impossible (Docker until
  ``--stop-timeout 45 --init``); a **local-only** gate (the plane half
  unavailable, or ``--offline``) needs ``local-only`` typed instead;
* ``apply`` returns at once; the modal then polls ``verify <plan_id>`` on its own
  tick until ``verified`` is not ``None`` (``verifying … 3 s`` meanwhile) and
  shows ``verified ✓ · connected: …`` or ``verify: not seen — check LOG``. It
  **never re-plans or re-applies on its own** (header Review Focus #5): a
  terminal verdict ends the flow; a lost apply reply keeps its plan and checks
  verification before the operator decides;
* the footer is the last :data:`AUDIT_LINES` audit lines via ``audit-tail``.

Broker calls are synchronous with a 20 s client timeout; they run in a thread
(``asyncio.to_thread``) so the UI never blocks. Every string from the broker is
redacted and tag-stripped before it is painted -- ``imd doctor`` output has its
``$`` figure stripped (spec §10, §11 doctor row).

Plan deviation 2: ``flat`` (the screen's last folded payload), ``poll_s`` and
``on_payload`` are additive keyword arguments. The PEPEPANE screen is suspended under
this modal (textual posts ``ScreenSuspend``; ``DashboardScreen`` stops its timer),
so each tick runs ``manager.fetch_and_compute()`` here and hands the flat to
``on_payload`` (``SeatScreen.apply_payload``): gate words stay live and
``plan_open``'s 15 s standing cadence is scheduled (spec §6).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Mapping

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
from maxpane_dashboard.data.seat_broker_client import CLIENT_TIMEOUT_S, BrokerError
from maxpane_dashboard.data.seat_models import fold_status_document
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.markup_safety import strip_tags

__all__ = ["AUDIT_LINES", "CONFIRM_CHARS", "GATED_VERBS", "LOCAL_ONLY_ACK", "NODE8_RE", "SKILL_ID_RE", "STATIC_LINES", "VERB_KEYS",
           "SeatControlScreen", "verb_lines"]

Clock = Callable[[], float]

VERB_KEYS = {"r": "restart", "d": "drain-restart", "s": "stop", "S": "start", "b": "enable-boot", "k": "skills-set", "o": "kill-orphans",
             "D": "doctor", "x": "cancel-drain"}
#: The procedures that are NOT verbs in v1 (spec §11): one static line each, no broker round-trip.
STATIC_LINES = (
    "tiers: shown above (CONFIG) · change = edit config.json as imd-worker + drained restart — runbook §2.1",
    "capacity: 1 by decision — drop-in + drained restart — runbook §4c",
    "update: {installed} → {available} — runbook §2.1 (drained restart)",
)
#: The broker's ``skill_id`` grammar (spec §11 skills row), applied here before an id can enter a plan.
SKILL_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
NODE8_RE = re.compile(r"[0-9a-f]{8}", re.ASCII)
LOCAL_ONLY_ACK = "local-only"
CONFIRM_CHARS = 4
AUDIT_LINES = 5
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


class SeatControlScreen(ModalScreen[None]):
    """The CONTROL modal -- see the module docstring."""

    BINDINGS = [Binding(key, f"verb('{key}')", verb, show=False) for key, verb in VERB_KEYS.items()] + [
        Binding("escape", "close", "Close", show=False, priority=True),
    ]
    #: ``S`` and ``D`` are the shifted letters as Textual names them (``Key.key == "S"``); if a Textual
    #: bump renames them, the fallback spelling is ``shift+s`` / ``shift+d`` and this test file's
    #: ``pilot.press("S")`` moves with it.

    def __init__(self, manager, *, now: Clock = time.time, flat: Mapping | None = None, poll_s: float = 5.0,
                 on_payload: Callable[[dict], None] | None = None) -> None:
        super().__init__()
        self._manager = manager
        self._now = now
        self._flat: dict = dict(flat) if flat is not None else {}
        self._poll_s = poll_s
        #: The PEPEPANE screen's ``apply_payload``: every flat this modal's own manager cycle returns is painted there too.
        self._on_payload = on_payload
        self._mode = "idle"
        self._pending_verb: str | None = None
        self._plan = None
        self._plan_started: float | None = None
        self._force_node8: str | None = None
        self._force_confirmed = False
        self._submit_pending = False
        self._status = Text("")
        self._outcome_unknown = False
        self._partial_note: str | None = None
        #: kept under every later status until a restart is applied (spec §11 skills set: drain-restart is step 2)
        self._restart_note: str | None = None
        self._timer = None
        self._busy = False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def _broker(self):
        return self._manager.broker

    # -- lifecycle ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="seat-control-box"):
            yield Static(Text("CONTROL", style="bold"), id="seat-control-title")
            with VerticalScroll(id="seat-control-scroll"):
                yield Static("", id="seat-control-verbs")
                yield Static("", id="seat-control-static")
                yield Static("", id="seat-control-plan")
                yield Static("", id="seat-control-status")
            yield Input(placeholder="type to confirm · esc closes", id="seat-control-input")
            yield Static("", id="seat-control-audit")

    def on_mount(self) -> None:
        if not self._flat:
            self._refresh_flat()
        self._paint()
        # Idle, the confirm field is NOT focused: ``Input`` consumes printable keys, so a focused field would
        # swallow ``r``/``k``/``b``/``o``/``D``. The verb bindings stay non-priority so a typed confirm or skill id
        # never fires a verb while a prompt is open.
        self._focus_input(False)
        self._timer = self.set_interval(self._poll_s, self._tick)
        self.run_worker(self._load_audit(), exclusive=True, group="seat-control-audit")

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._set_plan_open(False)

    def action_close(self) -> None:
        self._set_plan_open(False)
        self.dismiss(None)

    def _focus_input(self, on: bool) -> None:
        """Focus the confirm field while a prompt is open; otherwise park focus on the scroll area."""
        try:
            if on:
                self.query_one(Input).focus()
            else:
                self.query_one("#seat-control-scroll").focus()
        except Exception:  # noqa: BLE001 -- not composed yet / already unmounted
            pass

    def _set_plan_open(self, flag: bool) -> None:
        """``SeatManager.plan_open`` drives the 15 s standing cadence while a plan is open (spec §6, WP7)."""
        try:
            self._manager.plan_open = flag
        except Exception:  # noqa: BLE001 -- a manager without the attribute keeps its own cadence
            pass

    # -- facts ----------------------------------------------------------------

    def _refresh_flat(self) -> None:
        try:
            self._flat = fold_status_document(self._manager.document())
        except Exception:  # noqa: BLE001 -- a missing document leaves the last facts up
            pass

    def _write(self, selector: str, content) -> None:
        try:
            widget = self.query_one(selector, Static)
            if widget.content != content:
                widget.update(content)
        except Exception:  # noqa: BLE001
            pass

    def _paint(self) -> None:
        # Not ``_render``: that name is ``Widget._render()``, the method Textual calls for a widget's visual.
        verbs = Text("\n").join(verb_lines(self._flat))
        self._write("#seat-control-verbs", verbs)
        installed = _word(self._flat.get("seat_daemon_version")) or DASH
        available = _word(self._flat.get("seat_release_available")) or "none"
        static = Text("\n").join(Text(line.format(installed=installed, available=available), style="dim") for line in STATIC_LINES)
        self._write("#seat-control-static", static)
        self._write("#seat-control-status", self._status)

    def _set_status(self, words: str | Text, style: str = "") -> None:
        self._status = words.copy() if isinstance(words, Text) else Text.assemble((words, style))
        if self._partial_note:
            self._status.append("\n" + self._partial_note, style="yellow")
        if self._restart_note:
            self._status.append("\n" + self._restart_note, style="yellow")
        self._write("#seat-control-status", self._status)

    # -- the tick: live gate words, verify polling --------------------------

    async def _tick(self) -> None:
        await self._refresh_live()
        self._paint()
        if self._mode == "verifying" and self._plan is not None and not self._busy:
            await self._poll_verify()

    async def _refresh_live(self) -> None:
        """One manager cycle per tick while the modal is up (spec §8 CONTROL live gate words; spec §6 plan cadence).

        Textual suspends the PEPEPANE screen under a pushed modal and ``DashboardScreen.on_screen_suspend`` stops its
        refresh timer, so without this no ``fetch_and_compute`` runs while CONTROL is open: the gate words would
        freeze at open and ``manager.plan_open`` (read only inside the cycle's tier scheduling) would never take
        effect. The flat also goes to ``on_payload`` -- ``fetch_and_compute`` emits each LOG line exactly once, so a
        line the modal's cycle drew must still reach ``SeatLog``. A failed cycle keeps the last document's facts.
        """
        try:
            flat = await self._manager.fetch_and_compute()
        except Exception:  # noqa: BLE001 -- a failed cycle leaves the last facts up
            flat = None
        if not isinstance(flat, Mapping):
            self._refresh_flat()
            return
        self._flat = dict(flat)
        if self._on_payload is not None:
            try:
                self._on_payload(dict(flat))
            except Exception:  # noqa: BLE001 -- the PEPEPANE screen's paint never breaks the modal
                pass

    async def _load_audit(self) -> None:
        try:
            data = await asyncio.to_thread(self._broker.read, "audit-tail", {"n": AUDIT_LINES})
        except Exception:  # noqa: BLE001
            self._write("#seat-control-audit", Text("audit: unavailable", style="dim"))
            return
        lines = data.get("lines") if isinstance(data, dict) else None
        rows = []
        for entry in (lines or [])[-AUDIT_LINES:]:
            if not isinstance(entry, dict):
                continue
            words = f"{_clock(entry.get('ts'))} {_word(entry.get('verb'))} {_word(entry.get('phase'))} {_word(entry.get('outcome')) or ''}".strip()
            if entry.get("verified") is not None:
                words += f" · verified {entry.get('verified')}"
            if entry.get("connected") is not None:
                words += f" · connected {_word(entry.get('connected'))}"
            if entry.get("seq") is not None:
                words += f" (#{entry.get('seq')})"
            rows.append(Text(words, style="dim"))
        self._write("#seat-control-audit", Text("\n").join(rows) if rows else Text("audit: empty", style="dim"))

    # -- keys -----------------------------------------------------------------

    def action_verb(self, key: str) -> None:
        verb = VERB_KEYS.get(key)
        if verb is None or self._busy or self._submit_pending:
            return
        if self._flat.get("seat_control_broker_reachable") is False:
            self._set_status("broker unreachable — read-only", "yellow")
            return
        if self._mode in ("planned", "verifying"):
            self._set_status("a plan is open — esc to abandon it, or type its confirm", "yellow")
            return
        self._force_node8 = None
        self._force_confirmed = False
        if verb == "enable-boot" and self._flat.get("seat_unit_boot_enabled") is True:
            verb = "disable-boot"
        if verb == "skills-set":
            self._mode = "skill"
            self._pending_verb = verb
            self._set_status("type <skill-id> on|off then enter")
            self._focus_input(True)
            return
        if verb in GATED_VERBS and verb != "drain-restart":
            gate = _dict(self._flat.get("seat_control_gate"))
            if gate and gate.get("safe") is not True and not _dict(self._flat.get("seat_control_in_flight")):
                reason = _word(gate.get("reason")) or "blocked"
                if reason.startswith("gate unknown"):
                    self._set_status(f"BLOCKED: {reason} — no typed ack can override a fail-closed gate", "red")
                    return
                if self._flat.get("seat_unit_graceful_stop_possible") is not True:
                    self._set_status(f"BLOCKED: {reason} · force disabled (no init)", "red")
                    return
                self._mode = "force"
                self._pending_verb = verb
                self._set_status(f"BLOCKED: {reason} · type the running node8 to plan a forced {verb}", "red")
                self._focus_input(True)
                return
        args: dict = {}
        if verb == "kill-orphans":
            orphans = self._flat.get("seat_machine_orphans") if isinstance(self._flat.get("seat_machine_orphans"), list) else []
            args = {"pids": [o.get("pid") for o in orphans if isinstance(o, dict) and isinstance(o.get("pid"), int)]}
        self.run_worker(self._plan_verb(verb, args), exclusive=True, group="seat-control-broker")

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.action_submit()

    def action_submit(self) -> None:
        field = self.query_one(Input)
        typed = field.value.strip()
        field.value = ""
        if self._busy or self._submit_pending or not typed:
            return
        self._submit_pending = True
        self.run_worker(self._submit(typed), group="seat-control-submit")

    async def _submit(self, typed: str) -> None:
        try:
            await self._submit_value(typed)
        finally:
            self._submit_pending = False

    async def _submit_value(self, typed: str) -> None:
        if self._mode == "force":
            running = _word(_dict(self._flat.get("seat_current")).get("nodeId8"))
            if not running:
                reason = _word(_dict(self._flat.get("seat_control_gate")).get("reason"))
                match = NODE8_RE.search(reason)
                running = match.group(0) if match else ""
            if not NODE8_RE.fullmatch(typed) or typed != running:
                self._set_status("that is not the running node8", "red")
                return
            self._force_node8 = typed
            await self._plan_verb(self._pending_verb or "restart", {"force_node8": typed})
            return
        if self._mode == "skill":
            match = re.fullmatch(r"(\S+)\s+(on|off)", typed)
            if match is None or SKILL_ID_RE.fullmatch(match.group(1)) is None:
                self._set_status("invalid skill id — ^[a-z0-9][a-z0-9._-]{0,63}$ then on|off", "red")
                return
            skill_id, state = match.group(1), match.group(2) == "on"
            listed = {r.get("id") for r in (self._flat.get("seat_skills_rows") or []) if isinstance(r, dict)}
            if listed and skill_id not in listed:
                self._set_status(f"{skill_id} is not in the current imd skills listing (consistency check)", "yellow")
                return
            await self._plan_verb("skills-set", {"skill_id": skill_id, "on": state})
            return
        if self._mode == "planned" and self._plan is not None:
            await self._apply(typed)
            return
        self._set_status("no plan open — press a verb key first", "dim")

    # -- plan / apply / verify ------------------------------------------------

    async def _plan_verb(self, verb: str, args: dict) -> None:
        self._outcome_unknown = False
        self._partial_note = None
        self._busy = True
        try:
            plan = await asyncio.to_thread(self._broker.plan, verb, args)
        except BrokerError as exc:
            detail = " ".join(f"{k}={_word(v)}" for k, v in _dict(exc.detail).items())
            self._set_status(f"error: {_word(exc.code)} {detail}".strip(), "red")
            self._mode = "idle"
            self._plan = None
            self._focus_input(False)
            return
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"error: {_word(type(exc).__name__)}", "red")
            self._mode = "idle"
            self._focus_input(False)
            return
        finally:
            self._busy = False
        self._plan = plan
        self._pending_verb = verb
        self._plan_started = self._now()
        self._mode = "planned"
        self._set_plan_open(True)
        self._focus_input(True)
        self._write("#seat-control-plan", self._plan_block(plan))
        confirm = plan.plan_id[:CONFIRM_CHARS]
        if self._force_node8:
            self._set_status(f"plan {confirm} (forced) · type the running node8 again then enter to apply", "yellow")
        elif self._local_only(plan):
            self._set_status(f"plan {confirm} · plane half local-only · type {LOCAL_ONLY_ACK} then enter to apply", "yellow")
        else:
            self._set_status(f"plan {confirm} · type {confirm} then enter to apply (60 s)")

    def _local_only(self, plan) -> bool:
        plane = _dict(_dict(plan.preconditions).get("plane"))
        return plane.get("mode") == "local-only" or bool(getattr(self._broker, "offline", False))

    def _plan_block(self, plan) -> Text:
        pre = _dict(plan.preconditions)
        plane = _dict(pre.get("plane"))
        lines = [
            Text(f"plan {_word(plan.plan_id)} · {_word(plan.verb)} · expires {_clock(plan.expires_at)}", style="bold"),
            Text("argv: " + " ".join(_word(a) for a in (plan.argv or [])), style="dim"),
            Text(f"preconditions: idle_beats {pre.get('idle_beats')}/{pre.get('idle_beats_required')} · plane {plane.get('mode')} running {plane.get('running')} "
                 f"standing_age_s {plane.get('standing_age_s')} · outbox_files {pre.get('outbox_files')} · unit_active {pre.get('unit_active')} · "
                 f"graceful {pre.get('graceful_stop_possible')}"),
            Text(f"last_lifecycle_line: {_word(pre.get('last_lifecycle_line')) or DASH} (open: {pre.get('lifecycle_open')})", style="dim"),
            Text(f"warning: {_word(plan.warning)}", style="yellow"),
            Text(f"inverse: {_word(_dict(plan.inverse).get('verb')) or 'none'}", style="dim"),
            Text(f"verify: {' → '.join(_word(w) for w in _dict(plan.verify).get('verified_when', []))} within {_dict(plan.verify).get('within_s')} s · "
                 f"connected when {_word(_dict(plan.verify).get('connected_when'))} (reported separately)", style="dim"),
        ]
        return Text("\n").join(lines)

    async def _apply(self, typed: str) -> None:
        plan = self._plan
        confirm = plan.plan_id[:CONFIRM_CHARS]
        kwargs: dict = {}
        if self._force_node8:
            if not self._force_confirmed and typed != self._force_node8:
                self._set_status("a forced plan is applied by typing the running node8 again", "red")
                return
            if not self._force_confirmed:
                self._force_confirmed = True
                if self._local_only(plan):
                    self._set_status(f"node8 confirmed · type {LOCAL_ONLY_ACK} to acknowledge the local-only gate", "yellow")
                    return
            kwargs["force_node8"] = self._force_node8
        if self._local_only(plan):
            if typed != LOCAL_ONLY_ACK:
                self._set_status(f"type {LOCAL_ONLY_ACK} to acknowledge the local-only gate", "red")
                return
            kwargs["local_only_ack"] = typed
        elif not self._force_node8 and typed != confirm:
            self._set_status(f"type {confirm} to apply (or esc)", "red")
            return
        if self._plan_started is not None and self._now() - self._plan_started > 60:
            self._set_status("plan expired (60 s) — press the verb again to plan afresh", "yellow")
            self._mode = "idle"
            self._plan = None
            self._set_plan_open(False)
            self._focus_input(False)
            return
        self._busy = True
        self._apply_at = self._now()  # include time spent waiting for the apply reply
        try:
            result = await asyncio.to_thread(self._broker.apply, plan.plan_id, confirm, **kwargs)
        except BrokerError as exc:
            detail = _dict(exc.detail)
            if detail.get("partial") is True:
                killed = []
                for action in detail.get("killed") or []:
                    if isinstance(action, dict):
                        killed.extend(action.get("pids") or [action.get("pid")])
                skipped = [row.get("pid") for row in detail.get("skipped") or [] if isinstance(row, dict)]
                self._partial_note = ("partial action — killed pids: " + ", ".join(_word(pid) for pid in killed if pid is not None)
                                      + "; skipped pids: " + ", ".join(_word(pid) for pid in skipped if pid is not None))
                self._mode = "verifying"
                self._set_status(f"error: {_word(exc.code)} · checking verify", "yellow")
            elif exc.code in ("transport", "bad_response") or (exc.code == "timeout" and detail.get("outcome") == "timeout"):
                self._outcome_unknown = True
                self._mode = "verifying"
                self._set_status("outcome unknown — checking verify", "yellow")
            else:
                unspent = exc.code == "apply_late" and detail.get("plan_spent") is False
                if exc.code == "apply_late":
                    spent_word = "unspent" if unspent else "spent"
                    self._set_status(f"apply_late — plan is {spent_word} · {_word(detail.get('hint'))}", "yellow")
                else:
                    words = " ".join(f"{k}={_word(v)}" for k, v in detail.items())
                    self._set_status(f"error: {_word(exc.code)} {words}".strip(), "red")
                self._mode = "planned" if unspent else "idle"
                if not unspent:
                    self._plan = None
                    self._force_node8 = None
                    self._set_plan_open(False)
            self._focus_input(self._mode == "planned")
            self.run_worker(self._load_audit(), exclusive=True, group="seat-control-audit")
            return
        finally:
            self._busy = False
        self._mode = "verifying"
        self._focus_input(False)
        if plan.verb in ("restart", "drain-restart"):
            self._restart_note = None  # step 2 taken: the restart the note asked for is applied
        if getattr(plan, "restart_required_after", False):
            # spec §11 skills set: sets restartRequired (hero amber, spec §8) and CONTROL offers drain-restart as step 2
            set_required = getattr(self._manager, "set_restart_required", None)
            if callable(set_required):
                set_required(True)
            self._restart_note = "restart required — press [d] to drain-restart"
        self._set_status(f"{_word(result.outcome)} · verifying …", "yellow")
        self.run_worker(self._load_audit(), exclusive=True, group="seat-control-audit")

    async def _poll_verify(self) -> None:
        plan = self._plan
        self._busy = True
        try:
            result = await asyncio.to_thread(self._broker.verify, plan.plan_id)
        except BrokerError as exc:
            if self._outcome_unknown and exc.code == "transport":
                self._set_status("outcome unknown — checking verify", "yellow")
                return
            if self._outcome_unknown and exc.code == "unknown_plan":
                if self._now() - self._apply_at < CLIENT_TIMEOUT_S:
                    self._set_status("outcome unknown — checking verify", "yellow")
                    return
                self._set_status("not applied — the plan is spent; press the verb to plan afresh", "yellow")
            else:
                self._set_status(f"verify: error {_word(exc.code)} — check LOG", "red")
            self._mode = "done"
            self._set_plan_open(False)
            self._force_node8 = None
            self.run_worker(self._load_audit(), exclusive=True, group="seat-control-audit")
            return
        finally:
            self._busy = False
        elapsed = self._now() - getattr(self, "_apply_at", self._now())
        if result.verified is None:
            self._set_status(f"verifying … {max(elapsed, result.elapsed_s or 0):.0f} s", "yellow")
            return
        self._mode = "done"
        self._set_plan_open(False)
        self._force_node8 = None
        lines = [_word(line) for line in (result.verify_lines or [])]
        if result.verified is True:
            connected = result.connected
            connected_word = "yes" if connected is True else (_word(connected) if connected else "not yet reported")
            status = Text.assemble(("verified ✓", "green"))
            if connected is not None:
                status.append(" · connected: " + connected_word, style="green" if connected is True else "yellow")
            if lines:
                status.append("\n" + "\n".join(lines), style="green")
            self._set_status(status)
        else:
            self._set_status(f"verify: not seen — check LOG ({_word(result.reason) or 'no reason'})" + ("\n" + "\n".join(lines) if lines else ""), "red")
        self.run_worker(self._load_audit(), exclusive=True, group="seat-control-audit")
