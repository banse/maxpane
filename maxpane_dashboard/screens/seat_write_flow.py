"""One screen-owned plan/confirm/apply/verify state machine for CONTROL and CONFIG."""
from __future__ import annotations
import asyncio
import time
from rich.text import Text
from maxpane_dashboard.data.seat_broker_client import CLIENT_TIMEOUT_S, BrokerError
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.seat.seat_control import (VERB_KEYS, SKILL_ID_RE, NODE8_RE, LOCAL_ONLY_ACK,
    CONFIRM_CHARS, GATED_VERBS, _word, _dict)

class SeatWriteFlow:
    def __init__(self, manager, owner, *, now=time.time) -> None:
        self._owner = owner
        self._generation = 0
        self._closed = False
        self._manager = manager
        self._now = now
        self._flat: dict = {}
        self._mode = "idle"
        self._pending_verb: str | None = None
        self._plan = None
        self._plan_started: float | None = None
        self._force_node8: str | None = None
        self._force_confirmed = False
        self._submit_pending = False
        self._status = Text("")
        self._success_effects_plan_id: str | None = None
        self._outcome_unknown = False
        self._unknown_until = None
        self._plan_consumed = False
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

    def _set_plan_open(self, flag: bool) -> None:
        """``SeatManager.plan_open`` drives the 15 s standing cadence while a plan is open (spec §6, WP7)."""
        try:
            self._manager.plan_open = flag
        except Exception:  # noqa: BLE001 -- a manager without the attribute keeps its own cadence
            pass

    def run_worker(self, work, **kwargs):
        async def finish():
            try:
                await work
            finally:
                self.publish()
        return self._owner.run_worker(finish(), **kwargs)

    def publish(self):
        if self._closed:
            return
        parts = []
        # Text's spans become only the approved fixed colour names, never Rich in data.
        for segment in self._status.render(self._owner.app.console):
            style = segment.style
            colour = style.color.name if style and style.color else ('dim' if style and style.dim else '')
            parts.append({'text':segment.text, 'colour':colour})
        display = dict(plan=self._plan_projection(),status=self._status.plain,statusParts=parts,mode=self.mode)
        update = getattr(self._manager,'update_control_flow',None)
        if update:
            update(display)
        self._owner.flow_changed()

    def _focus_input(self, _on):
        self.publish()

    def cancel_prompt(self):
        active_prompt = self.mode in ("planned", "force", "planning")
        self._generation += 1
        self._set_plan_open(False)
        if self.mode in ('planned','force','planning'):
            plan_id = self._plan.plan_id[:4] if self._plan else ''
            self._mode = 'idle'
            self._plan = None
            self._force_node8 = None
            self._set_status(f'plan {plan_id} dropped — not applied', 'dim')
        if active_prompt:
            self.publish()

    def close(self):
        self._closed = True
        self.cancel_prompt()
        if self._timer is not None:
            self._timer.stop()

    def submit(self, typed):
        typed = typed.strip()
        if self.mode not in ("force", "planned") or not typed or self._busy or self._submit_pending:
            return
        self._submit_pending = True
        self.run_worker(self._submit(typed),group='seat-control-submit')

    def _schedule_tick(self):
        if self.mode in ("verifying", "planned") and not self._busy:
            self.run_worker(self._tick(), group="seat-control-verify")

    async def _tick(self):
        if self.mode not in ("verifying", "planned"):
            return
        try:
            if self.mode == 'verifying' and self._plan is not None and not self._busy:
                await self._poll_verify()
            elif self.mode == 'planned' and self._plan_started is not None and self._now()-self._plan_started > 60:
                self.cancel_prompt()
                self._set_status('plan expired (60 s) — press the verb again to plan afresh','yellow')
        finally:
            self.publish()

    def _set_status(self, words: str | Text, style: str = "") -> None:
        self._status = words.copy() if isinstance(words, Text) else Text.assemble((words, style))
        if self._partial_note:
            self._status.append("\n" + self._partial_note, style="yellow")
        if self._restart_note:
            self._status.append("\n" + self._restart_note, style="yellow")
        self.publish()

    def request(self, verb: str, args: dict | None = None) -> None:
        if verb not in (*VERB_KEYS.values(), "skills-set", "disable-boot") or self._busy or self._submit_pending:
            return
        if self._mode not in ("planned", "verifying"):
            self._partial_note = None
        if self._flat.get("seat_control_broker_reachable") is False:
            self._set_status("broker unreachable — read-only", "yellow")
            return
        if self._mode in ("planned", "verifying"):
            self._set_status("a plan is open — esc to abandon it, or type its confirm", "yellow")
            return
        if verb in ('enable-boot', 'disable-boot') and self._flat.get('seat_host_kind') == 'docker':
            self._set_status('boot follows the container restart policy; fixed here', 'dim')
            return
        self._force_node8 = None
        self._force_confirmed = False
        if verb == "enable-boot" and self._flat.get("seat_unit_boot_enabled") is True:
            verb = "disable-boot"
        if verb == "skills-set":
            skill_id = (args or {}).get("skill_id")
            listed = {row.get('id') for row in self._flat.get('seat_skills_rows') or []}
            if not isinstance(skill_id, str) or SKILL_ID_RE.fullmatch(skill_id) is None:
                self._set_status("invalid skill id — ^[a-z0-9][a-z0-9._-]{0,63}$", "red")
                return
            if skill_id not in listed or type((args or {}).get('on')) is not bool:
                self._set_status("skill is not in the current imd skills listing (consistency check)", "yellow")
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
                self._partial_note = None
                self._mode = "force"
                self._pending_verb = verb
                self._set_status(f"BLOCKED: {reason} · type the running node8 to plan a forced {verb}", "red")
                self._focus_input(True)
                return
        args = dict(args or {})
        if verb == "kill-orphans":
            orphans = self._flat.get("seat_machine_orphans") if isinstance(self._flat.get("seat_machine_orphans"), list) else []
            args = {"pids": [o.get("pid") for o in orphans if isinstance(o, dict) and isinstance(o.get("pid"), int)]}
        self.run_worker(self._plan_verb(verb, args, generation=self._generation), exclusive=True, group="seat-control-broker")

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
        if self._mode == "planned" and self._plan is not None:
            await self._apply(typed)
            return
        if self._mode != "verifying":
            self._partial_note = None
        self._set_status("no plan open — press a verb key first", "dim")

    async def _plan_verb(self, verb: str, args: dict, *, generation=None) -> None:
        generation = self._generation if generation is None else generation
        self._mode = "planning"
        self._outcome_unknown = False
        self._unknown_until = None
        self._plan_consumed = False
        self._partial_note = None
        self._busy = True
        try:
            plan = await asyncio.to_thread(self._broker.plan, verb, args)
            if generation != self._generation:
                self._set_status(f"plan {plan.plan_id[:4]} dropped — not applied", "dim")
                return
        except BrokerError as exc:
            if generation != self._generation:
                return
            self._set_plan_open(False)
            detail = " ".join(f"{k}={_word(v)}" for k, v in _dict(exc.detail).items())
            self._set_status(f"error: {_word(exc.code)} {detail}".strip(), "red")
            self._mode = "idle"
            self._plan = None
            self._focus_input(False)
            return
        except Exception as exc:  # noqa: BLE001
            if generation != self._generation:
                return
            self._set_plan_open(False)
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

    def _plan_projection(self):
        plan = self._plan
        if plan is None:
            return None
        pre = _dict(plan.preconditions)
        plane = _dict(pre.get('plane'))
        verify = _dict(plan.verify)
        within = verify.get('within_s')
        within = str(int(within)) if isinstance(within,(int,float)) else _word(within)
        return dict(planId=plan.plan_id, verb=plan.verb, command=' '.join(_word(a) for a in plan.argv or []),
                    confirm=plan.plan_id[:CONFIRM_CHARS], warning=_word(plan.warning), expiresAtUtc=plan.expires_at,
                    forced=bool(self._force_node8), localOnly=self._local_only(plan),
                    preconditions=f"idle_beats {pre.get('idle_beats')}/{pre.get('idle_beats_required')} · plane {plane.get('mode')} running {plane.get('running')} "
                    f"standing_age_s {plane.get('standing_age_s')} · outbox_files {pre.get('outbox_files')} · unit_active {pre.get('unit_active')} · "
                    f"graceful {pre.get('graceful_stop_possible')}\nlast_lifecycle_line: {_word(pre.get('last_lifecycle_line')) or DASH} (open: {pre.get('lifecycle_open')})",
                    inverse=_word(_dict(plan.inverse).get('verb')) or 'none',
                    verification=f"{' → '.join(_word(w) for w in verify.get('verified_when', []))} within {within} s · "
                    f"connected when {_word(verify.get('connected_when'))} (reported separately)")

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
        self._mode = "applying"
        self._set_plan_open(False)
        self._focus_input(False)
        self._apply_at = self._now()  # include time spent waiting for the apply reply
        try:
            result = await asyncio.to_thread(self._broker.apply, plan.plan_id, confirm, **kwargs)
        except BrokerError as exc:
            detail = _dict(exc.detail)
            if "killed" in detail or "skipped" in detail:
                killed = []
                for action in detail.get("killed") or []:
                    if isinstance(action, dict):
                        killed.extend(action.get("pids") or [action.get("pid")])
                skipped = [row.get("pid") for row in detail.get("skipped") or [] if isinstance(row, dict)]
                pid_note = "skipped pids: " + (", ".join(_word(pid) for pid in skipped if pid is not None) or "none")
                reason = " · ".join(_word(detail.get(key)) for key in ("what", "reason", "hint") if detail.get(key))
                error = f"error: {_word(exc.code)}" + (f" · {reason}" if reason else "")
                if detail.get("partial") is True:
                    self._partial_note = ("partial action — killed pids: "
                                          + ", ".join(_word(pid) for pid in killed if pid is not None) + "; " + pid_note)
                    self._mode = "verifying"
                    self._set_status(error + " · checking verify", "yellow")
                else:
                    signal_state = "signal state unknown — check LOG" if detail.get("outcome") == "timeout" else "nothing signalled"
                    self._set_status(error + "\n" + signal_state + " · " + pid_note, "red")
                    self._mode = "idle"
                    self._plan = None
                    self._force_node8 = None
                    self._set_plan_open(False)
            elif exc.code in ("transport", "bad_response") or (exc.code == "timeout" and detail.get("outcome") == "timeout"):
                self._outcome_unknown = True
                self._unknown_until = max(self._apply_at + CLIENT_TIMEOUT_S, self._now() + 10)
                self._plan_consumed = detail.get("plan_spent") is True or exc.code == "timeout"
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
            self.publish()
            return
        finally:
            self._busy = False
        self._mode = "verifying"
        self._focus_input(False)
        self._set_status(f"{_word(result.outcome)} · verifying …", "yellow")
        self.publish()

    def _apply_success_effects(self, plan) -> None:
        """Apply the verified plan's UI effects once, including recovered replies."""
        if self._success_effects_plan_id == plan.plan_id:
            return
        self._success_effects_plan_id = plan.plan_id
        if plan.verb in ("restart", "drain-restart"):
            self._restart_note = None  # step 2 taken: the restart the note asked for is applied
        if getattr(plan, "restart_required_after", False):
            # spec §11 skills set: sets restartRequired (hero amber, spec §8) and CONTROL offers drain-restart as step 2
            set_required = getattr(self._manager, "set_restart_required", None)
            if callable(set_required):
                set_required(True)
            self._restart_note = "restart required — press [d] to drain-restart"

    async def _poll_verify(self) -> None:
        plan = self._plan
        self._busy = True
        try:
            result = await asyncio.to_thread(self._broker.verify, plan.plan_id)
        except BrokerError as exc:
            if self._outcome_unknown and exc.code in ("transport", "bad_response", "unreachable", "unknown_plan"):
                if self._unknown_until is not None and self._now() < self._unknown_until:
                    self._set_status("outcome unknown — checking verify", "yellow")
                    return
                plan_state = "plan is spent" if self._plan_consumed else "plan state unknown"
                self._set_status(f"outcome unknown — {plan_state}; check LOG and audit before planning afresh", "yellow")
            else:
                self._set_status(f"verify: error {_word(exc.code)} — check LOG", "red")
            self._mode = "done"
            self._set_plan_open(False)
            self._force_node8 = None
            self.publish()
            return
        finally:
            self._busy = False
        self._plan_consumed = True  # a verification watch exists only after consume
        elapsed = self._now() - getattr(self, "_apply_at", self._now())
        if result.verified is None:
            self._set_status(f"verifying … {max(elapsed, result.elapsed_s or 0):.0f} s", "yellow")
            return
        self._mode = "done"
        self._set_plan_open(False)
        self._force_node8 = None
        lines = [_word(line) for line in (result.verify_lines or [])]
        if result.verified is True:
            self._apply_success_effects(plan)
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
        self.publish()
