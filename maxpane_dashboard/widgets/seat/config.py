"""CONFIG & SKILLS: what the control verbs change and what the plane offers work against (spec §8).

Group 1 is the seat's configuration as the broker's ``imd status``/projection saw it
(server, capacity, offers, runtime, daemon build vs the release available, the
advertised premium model, the inference table -- this **is** ``tier show``, there
is no separate verb -- the #7 codex wrapper note (systemd + codex only: the wrapper
sets its own model/effort and the daemon's ``-m`` wins; no model name is hardcoded),
the task-hints fingerprint, and whether ``config.json``
changed after the daemon started, which means *restart required*). Group 2 is the
skills table (``id · on/off · needs``, :data:`SeatConfig.SKILLS_ROW_CAP` rows and
``+N more``) with the configured tool ids in its footer.

Values are sentences and a half-width panel is ~71 cells, so every sentence is a
tuple of honest forms (plan deviation 6, :func:`pick_form`): the same fact,
shorter, never a silent cut; the title carries ``‹ widen`` only when the shortest
form still had to be clipped (FWA's SIGNALS precedent). Degraded per source (spec
§7 ``sources`` per field): ``unavailable (broker: <reason>)`` when the broker is
out, ``unavailable (<reason>)`` naming the daemon version when ``imd status``
did not parse, and the projection canary's refusal in red. On the Mac the group
titles carry ``(container)``: every CLI-fed value there is container-reported
(spec §4.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, as_float, fmt_int, mmdd, short_model
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.seat_words import seat_token
from maxpane_dashboard.widgets.seat.hero import _word

__all__ = ["SKILLS_ROW_CAP", "SeatConfig", "pick_form"]

#: (invented, contract §B) 31 skill rows would not fit a half-height panel; the footer counts the rest.
SKILLS_ROW_CAP = 12

_count = seat_token

#: ``fmt_signal`` spends ``"  ● "`` (4) + label + ``" "`` (1) before the value; the panel-line spends ``padding: 0 1`` (2).
_ROW_OVERHEAD = 4 + 1 + 2


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


class SeatConfig(SignalsPanelBase):
    """CONFIG & SKILLS -- see the module docstring."""

    TITLE = "CONFIG & SKILLS"
    LABEL_WIDTH = 12
    DIM_LABEL = True
    ROWS = (
        ("seat-cfg-server", "server"), ("seat-cfg-capacity", "capacity"), ("seat-cfg-offers", "offers"), ("seat-cfg-runtime", "runtime"),
        ("seat-cfg-daemon", "daemon"), ("seat-cfg-premium", "premium"), ("seat-cfg-inference", "inference"),
        ("seat-cfg-wrapper", "wrapper"), ("seat-cfg-hints", "hints"),
        ("seat-cfg-changed", "config"), None, ("seat-cfg-skills-title", None),
    )
    #: The #7 codex wrapper note (spec §8 group 1; plan deviation 14): shown only on a systemd host running codex.
    WRAPPER_ROW_ID = "seat-cfg-wrapper"
    WRAPPER_FORMS = (
        "/opt/imd-worker/bin/codex sets its own model/effort; the daemon's -m wins (effort precedence: source-proven only)",
        "the codex wrapper's model/effort lose to the daemon's -m",
        "the daemon's -m wins over the wrapper",
    )
    SKILLS_TABLE_ID = "seat-cfg-skills"
    SKILLS_FOOTER_ID = "seat-cfg-skills-footer"
    SKILLS_ROW_CAP = SKILLS_ROW_CAP

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

    def compose_body(self) -> ComposeResult:
        yield from super().compose_body()
        yield DataTable(id=self.SKILLS_TABLE_ID)
        yield Static("", id=self.SKILLS_FOOTER_ID, classes="panel-line")

    def on_mount(self) -> None:
        table = self.query_one(f"#{self.SKILLS_TABLE_ID}", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("id", width=24)
        table.add_column("on", width=3)
        table.add_column("needs", width=14)

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        seat_server=None, seat_capacity=None, seat_offers=None, seat_runtime_id=None, seat_runtime_version=None, seat_daemon_version=None,
        seat_release_available=None, seat_premium_advertised=None, seat_inference=None, seat_hints=None,
        seat_config_changed_since_start=None, seat_skills_rows=None, seat_skills_offered=None, seat_skills_on=None, seat_tools=None,
        seat_sources=None, seat_as_of_hhmm=None, seat_host_kind=None,
        **_kwargs,
    ) -> None:
        self._facts = {k: v for k, v in locals().items() if k.startswith("seat_")}
        self._repaint()

    def on_resize(self, _event=None) -> None:
        if self._facts is not None:
            self._repaint()

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

    def _repaint(self) -> None:
        if self._facts is None:
            return
        f = self._facts
        docker = f.get("seat_host_kind") == "docker"
        room = max(self.content_region.width - self.LABEL_WIDTH - _ROW_OVERHEAD, 0)
        cut = False
        for row_id, label, forms, colour in self._rows():
            degraded = self._degraded(row_id)
            if degraded is not None:
                colour = "red" if "canary" in degraded else "yellow"
                forms = (degraded, degraded.split(" (")[0])
            value, was_cut = pick_form(forms, room if label is not None else room + self.LABEL_WIDTH + 1)
            cut = cut or was_cut
            self.render_signal(f"#{row_id}", label or "", {"label": label or "", "value_str": value, "color": colour},
                               labelled=label is not None)
        self._skills_table()
        try:
            self.query_one(f"#{self.WRAPPER_ROW_ID}").display = self._shows_wrapper()
        except Exception:  # noqa: BLE001 -- not composed yet
            pass
        as_of = f.get("seat_as_of_hhmm") if isinstance(f.get("seat_as_of_hhmm"), dict) else {}
        marker = as_of.get("status")
        title = self.TITLE + (" (container)" if docker else "") + (f" · as of {rowfit.clip(marker, 5)}" if rowfit.has_marker(marker) else "")
        self.write(".panel-title", Text(rowfit.title_with_hint(title, cut, max(self.content_region.width, 0))))

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

    def _skills_table(self) -> None:
        f = self._facts or {}
        try:
            table = self.query_one(f"#{self.SKILLS_TABLE_ID}", DataTable)
        except Exception:  # noqa: BLE001
            return
        table.clear()
        rows = f.get("seat_skills_rows") if isinstance(f.get("seat_skills_rows"), list) else None
        degraded = self._degraded("seat-cfg-skills-title")
        parts: list[str] = []
        if degraded is not None or rows is None:
            table.add_row(f"[yellow]{sanitize_cell(degraded or 'unavailable', 24)}[/]", "", "")
        else:
            for row in rows[: self.SKILLS_ROW_CAP]:
                if not isinstance(row, dict):
                    continue
                on = row.get("on")
                table.add_row(sanitize_cell(_word(row.get("id")) or DASH, 24), "on" if on is True else ("off" if on is False else DASH),
                              sanitize_cell(_word(row.get("needs")) or "", 14))
            if len(rows) > self.SKILLS_ROW_CAP:
                parts.append(f"+{fmt_int(len(rows) - self.SKILLS_ROW_CAP)} more")
        tools = f.get("seat_tools") if isinstance(f.get("seat_tools"), list) else None
        if tools is None:
            parts.append("tools: unavailable")
        elif tools:
            parts.append("tools: " + ", ".join(_word(t) for t in tools if _word(t)))
        else:
            parts.append("tools: none configured")
        room = max(self.content_region.width - 2, 0)
        self.write(f"#{self.SKILLS_FOOTER_ID}", Text(rowfit.clip(" · ".join(parts), room) if room else " · ".join(parts), style="dim"))
