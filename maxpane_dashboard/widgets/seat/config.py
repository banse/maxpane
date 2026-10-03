"""Cursor-selectable CONFIG table; value/source formatting retained from the original panel."""

from __future__ import annotations

from collections.abc import Sequence

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, as_float, mmdd, short_model
from maxpane_dashboard.widgets.seat.seat_table import SeatTable
from maxpane_dashboard.widgets.seat_words import seat_token
from maxpane_dashboard.widgets.seat.hero import _word

__all__ = ["SeatConfig", "pick_form"]

_count = seat_token

def pick_form(forms: Sequence[str], room: int) -> tuple[str, bool]:
    """The first of *forms* that fits *room* cells; else the last, clipped. The flag marks a cut."""
    if not forms:
        return "", False
    if room <= 0:
        return forms[0], False
    for form in forms:
        if cell_len(form) <= room:
            return form, False
    return rowfit.clip(forms[-1], room), True




def _kb(value: object) -> str:
    b = as_float(value)
    return DASH if b is None or b < 0 else f"{b / 1000:.1f} KB"


class SeatConfig(SeatTable):
    """CONFIG settings, with SKILLS composed beside it by the screen."""

    TITLE = "CONFIG"
    TABLE_ID = "seat-config-table"
    ROW_CAP = None
    EMPTY_LINE = "config unavailable"
    COLUMN_SPECS = (("setting", "setting", 12), ("value", "value", 25), ("change", "change", 10))
    TIER_COLUMNS = {"full": ("setting", "value", "change")}
    LADDER = rowfit.Ladder(("full", 0))
    #: The #7 codex wrapper note (spec §8 group 1; plan deviation 14): shown only on a systemd host running codex.
    WRAPPER_ROW_ID = "seat-cfg-wrapper"
    WRAPPER_FORMS = (
        "/opt/imd-worker/bin/codex sets its own model/effort; the daemon's -m wins (effort precedence: source-proven only)",
        "the codex wrapper's model/effort lose to the daemon's -m",
        "the daemon's -m wins over the wrapper",
        "daemon -m wins over wrapper",
    )

    #: Rows never wrap (every value is fitted first); the table takes the rest of the panel, floored at a header plus three rows.

    #: Which source gates which row (spec §7 ``sources`` per field; contract §C.4 rule of thumb).
    _ROW_SOURCE = {
        "seat-cfg-server": "seat", "seat-cfg-capacity": "status", "seat-cfg-offers": "status", "seat-cfg-runtime": "status",
        "seat-cfg-daemon": "tail", "seat-cfg-premium": "standing", "seat-cfg-inference": "seat", "seat-cfg-wrapper": "status",
        "seat-cfg-hints": "hints",
        "seat-cfg-changed": "seat", "seat-cfg-skills-title": "skills",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._facts: dict | None = None

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        seat_server=None, seat_capacity=None, seat_offers=None, seat_runtime_id=None, seat_runtime_version=None, seat_daemon_version=None,
        seat_release_available=None, seat_premium_advertised=None, seat_inference=None, seat_hints=None,
        seat_config_changed_since_start=None, seat_skills_rows=None, seat_skills_offered=None, seat_skills_on=None, seat_tools=None,
        seat_sources=None, seat_as_of_hhmm=None, seat_host_kind=None,
        seat_token_id=None, seat_agent_id=None, seat_wallet=None, seat_device_key_public=None, seat_unit_boot_enabled=None,
        seat_unit_restart_policy=None, seat_auto_update=None, seat_runtime_wrapper=None, seat_control_restart_required=None,
        **_kwargs,
    ) -> None:
        self._facts = {k: v for k, v in locals().items() if k.startswith("seat_")}
        rows = self._config_rows()
        self.store(rows, (seat_as_of_hhmm or {}).get("status"))

    # -- painting -----------------------------------------------------------

    def _source(self, name: str) -> dict:
        sources = (self._facts or {}).get("seat_sources")
        source = sources.get(name) if isinstance(sources, dict) else None
        return source if isinstance(source, dict) else {}

    def _degraded(self, row_id: str) -> str | None:
        """The degraded sentence for *row_id*, or ``None`` when its sources are fine."""
        broker = self._source("broker")
        if broker.get("ok") is False:
            return f"unavailable (broker: {_word(broker.get('reason')) or 'unreachable'})"
        name = self._ROW_SOURCE.get(row_id)
        source = self._source(name) if name else {}
        if source.get("ok") is False:
            reason = _word(source.get("reason")) or "unavailable"
            if name == "seat" and "canary" in reason.lower():
                return "config projection unavailable — broker refused payload (canary)"
            return f"unavailable ({reason})"
        return None

    def column_width(self, key, tier, budget, width):
        return max(8, budget - 28) if key == "value" else width

    def _config_rows(self):
        rows = []
        for row_id, label, forms, colour in self._rows():
            if label is None or (row_id == self.WRAPPER_ROW_ID and not self._shows_wrapper()):
                continue
            degraded = self._degraded(row_id)
            rows.append(dict(key=label, setting=label, forms=(degraded,) if degraded else forms,
                             colour=("red" if "canary" in degraded else "yellow") if degraded else colour,
                             change={"capacity": "runbook", "runtime": "start flag", "inference": "runbook",
                                     "server": "fixed", "offers": "derived", "hints": "never", "daemon": "runbook"}.get(label, "—")))
        f = self._facts
        extra = [("seat", f"{f.get('seat_token_id') or DASH} · agent {f.get('seat_agent_id') or DASH}", "fixed"),
                 ("wallet", _word(f.get('seat_wallet')) or DASH, "fixed"),
                 ("device key", _word(f.get('seat_device_key_public')) or DASH, "fixed"),
                 ("boot", (_word(f.get('seat_unit_restart_policy')) or DASH) if f.get('seat_host_kind') == 'docker'
                  else ('enabled' if f.get('seat_unit_boot_enabled') is True else 'disabled' if f.get('seat_unit_boot_enabled') is False else 'unavailable'),
                  "fixed" if f.get('seat_host_kind') == 'docker' else "space"),
                 ("auto-update", 'on' if f.get('seat_auto_update') is True else 'off' if f.get('seat_auto_update') is False else 'unavailable', "never")]
        for name, value, change in extra:
            rows.append(dict(key=name, setting=name, forms=(value,), colour="dim", change=change))
        return rows

    def build_cells(self, item):
        room = dict((key, width) for key, _, width in self._installed).get("value", 25)
        value, cut = pick_form(item['forms'], room)
        self._clipped |= cut
        return {"setting": Text(item['setting']), "value": Text(value, style=item['colour']), "change": Text(item['change'], style="dim")}

    def _render_title(self, as_of):
        self.TITLE = "CONFIG" + (" (container)" if (self._facts or {}).get('seat_host_kind') == 'docker' else "")
        super()._render_title(as_of)

    def _shows_wrapper(self) -> bool:
        f = self._facts or {}
        return f.get("seat_host_kind") == "systemd" and _word(f.get("seat_runtime_id")) == "codex"

    def _rows(self):
        f = self._facts or {}
        docker = f.get("seat_host_kind") == "docker"
        wrapper_forms = self.WRAPPER_FORMS if self._shows_wrapper() else ("",)
        server = _word(f.get("seat_server"))
        host = server.split("://", 1)[-1].split("/")[0] if server else DASH
        cap = _count(f.get("seat_capacity"))
        offers = f.get("seat_offers") if isinstance(f.get("seat_offers"), list) else []
        offers_word = " · ".join(_word(o) for o in offers if _word(o)) or DASH
        runtime = _word(f.get("seat_runtime_version")) or _word(f.get("seat_runtime_id")) or DASH
        daemon = _word(f.get("seat_daemon_version")) or DASH
        avail = _word(f.get("seat_release_available"))
        if avail:
            daemon_forms = (f"{daemon} → {avail} · update: see runbook §2.1 — drained restart", f"{daemon} → {avail} · update pending", f"↑ {avail}")
            daemon_colour = "yellow"
        else:
            daemon_forms = (f"{daemon} · up to date", daemon)
            daemon_colour = "dim"
        premium = f.get("seat_premium_advertised") if isinstance(f.get("seat_premium_advertised"), dict) else None
        if premium:
            pm = f"{_word(premium.get('model')) or DASH}/{_word(premium.get('effort')) or DASH}"
            premium_forms = (f"{pm} advertised (api)", f"{pm} (api)", short_model(premium.get("model")) or pm)
        else:
            premium_forms = ("none advertised", DASH)
        inference_forms = self._inference_forms(f.get("seat_inference"), _word(f.get("seat_runtime_id")))
        hints = f.get("seat_hints") if isinstance(f.get("seat_hints"), dict) else None
        if hints:
            path, sha8 = _word(hints.get("path")) or DASH, _word(hints.get("sha8")) or DASH
            when = mmdd(parse_iso(hints.get("mtimeUtc")))
            hints_forms = (f"{path} · {_kb(hints.get('bytes'))} · sha {sha8} · {when}", f"{path.rsplit('/', 1)[-1]} · sha {sha8} · {when}", f"sha {sha8}")
        else:
            hints_forms = ("no task-hints file", DASH)
        changed = f.get("seat_config_changed_since_start")
        if changed is True:
            changed_forms, changed_colour = ("changed after start → restart required", "restart required"), "yellow"
        elif changed is False:
            changed_forms, changed_colour = ("unchanged since start", "unchanged"), "dim"
        else:
            changed_forms, changed_colour = ("unavailable",), "yellow"
        offered, on = _count(f.get("seat_skills_offered")), _count(f.get("seat_skills_on"))
        rows = f.get("seat_skills_rows") if isinstance(f.get("seat_skills_rows"), list) else []
        needs_network = sum(1 for r in rows if isinstance(r, dict) and _word(r.get("needs")) == "network")
        suffix = " (container)" if docker else ""
        skills_forms = (
            f"skills {offered if offered is not None else DASH} offered · {on if on is not None else DASH} on · {needs_network} need network{suffix}",
            f"skills {on if on is not None else DASH}/{offered if offered is not None else DASH}{suffix}",
        )
        return (
            ("seat-cfg-server", "server", (host,), "dim"),
            ("seat-cfg-capacity", "capacity", (f"{cap} concurrent" if cap is not None else DASH, str(cap) if cap is not None else DASH), "dim"),
            ("seat-cfg-offers", "offers", (offers_word,), "dim"),
            ("seat-cfg-runtime", "runtime", (runtime,), "dim"),
            ("seat-cfg-daemon", "daemon", daemon_forms, daemon_colour),
            ("seat-cfg-premium", "premium", premium_forms, "dim"),
            ("seat-cfg-inference", "inference", inference_forms, "dim"),
            ("seat-cfg-wrapper", "wrapper", wrapper_forms, "dim"),
            ("seat-cfg-hints", "hints", hints_forms, "dim"),
            ("seat-cfg-changed", "config", changed_forms, changed_colour),
            ("seat-cfg-skills-title", None, skills_forms, "dim"),
        )

    @staticmethod
    def _inference_forms(block: object, runtime_id: str) -> tuple[str, ...]:
        if not isinstance(block, dict) or not block:
            return ("runtime default",)
        full, mid, short = [], [], []
        previous = None
        for tier in ("economy", "standard", "premium"):
            entry = block.get(tier) if isinstance(block.get(tier), dict) else None
            if not entry:
                continue
            per_runtime = entry.get(runtime_id) if runtime_id and isinstance(entry.get(runtime_id), dict) else next(
                (v for v in entry.values() if isinstance(v, dict)), None)
            if not per_runtime:
                continue
            model, effort = _word(per_runtime.get("model")) or DASH, _word(per_runtime.get("effort")) or DASH
            pair = f"{model}/{effort}"
            if pair == previous:
                full.append(f"{tier} same")
                mid.append(f"{tier[:3]} same")
                short.append("same")
            else:
                full.append(f"{tier} {runtime_id + ' ' if runtime_id and tier == 'economy' else ''}{pair}")
                mid.append(f"{tier[:3]} {pair}")
                short.append(f"{short_model(per_runtime.get('model')) or model}/{effort[:3]}")
            previous = pair
        if not full:
            return ("runtime default",)
        return (" · ".join(full), " · ".join(mid), " · ".join(short))
