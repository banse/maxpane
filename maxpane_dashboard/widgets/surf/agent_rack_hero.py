"""Twelve AGENT rack cards over independently observed primitive facts."""
from __future__ import annotations

from dataclasses import replace

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.analytics.surf_swarm_signals import runtime_semver
from maxpane_dashboard.widgets.address import address_text, is_address
from maxpane_dashboard.widgets.fmt import hhmm, mmdd
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from maxpane_dashboard.widgets.surfboard.rack import meter_text
from ._fmt import EXPLORER, mmdd_hhmm, short_model
from ._swarm_seat import NODE_TITLES
from .news_hero import HeroRecord, _count, _number
from .pool4_hero import Pool4HeroCard, _amount, _face

_STATES = ("ok", "partial", "stale", "unavailable", "pending", "busy", "unknown_seat", "stale_unknown_seat", "empty")
_AVAILABLE = ("ok", "partial", "stale")


def _source(payload, key):
    source = payload.get(key) if isinstance(payload, dict) else None
    return source if isinstance(source, dict) else {}


def _digits(value):
    value = count(value)
    return str(value) if value is not None and value < 10000 else _amount(value)


def _rows(source):
    rows = source.get("rows")
    return rows if isinstance(rows, list) and all(isinstance(row, dict) for row in rows) else None


def _status_word(source):
    live = source.get("live_state")
    live = live if live in ("working", "idle", "offline", "paused") else None
    return {"working": "BUSY", "idle": "IDLE", "offline": "OFF", "paused": "PAUSED"}.get(live, "UNKNOWN")


def agent_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    records = []
    for key, title, heading, footer in (
        ("seat", "SEAT", "IDMD", "SELECTED"),
        ("accepted", "ACCEPTED", "WORK", "--%"),
        ("effort", "EFFORT", "HOURS", "CONTRIBUTORS"),
        ("rewards", "REWARDS", "IMD", "OWNER SHARE"),
        ("rank", "RANK", "POSITION", "RECORDS"),
        ("status", "STATUS", "WORKER", "UNKNOWN"),
        ("owner", "OWNER", "WALLET", "OPEN / COPY"),
        ("runtime", "RUNTIME", "SOFTWARE", "VERSION"),
        ("models", "MODELS", "ADVERTISED", "CONFIGURATION"),
        ("feedback", "FEEDBACK", "DELIVERY", "-- QUEUED"),
        ("collab", "COLLAB", "SEATS", "TOP --"),
        ("nodes", "NODES", "ACCEPTED", "HISTORY"),
    ):
        raw = _source(payload, key)
        state = raw.get("state")
        state = state if state in _STATES else "unavailable"
        section = raw if state in _AVAILABLE else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=number(raw.get("read_ts")), accent=state == "ok")
        if key == "seat":
            token = count(raw.get("token_id"))
            fields["digits"] = str(token) if token is not None and number(token) is not None else "--"
            selected = raw.get("selected_by")
            fields["subtitle"] = "saved seat" if selected == "saved" else "most active" if selected == "most_active" else "selection --"
            if token is None and state == "empty":
                fields.update(digits="", preview="no seat selected", subtitle="")
            fields["accent"] &= token is not None and not raw.get("read_error")
        elif key in ("accepted", "effort", "rank") and section.get("listed") is False:
            fields.update(preview="no receipts" if key == "effort" else "not recorded", accent=False)
        elif key == "accepted":
            accepted, attempts = (count(section.get(name)) for name in ("accepted", "attempts"))
            fields["digits"] = _digits(accepted)
            fields["subtitle"] = f"{_count(attempts)} attempts"
            percent = number(section.get("percent"))
            if attempts == 0 and accepted == 0:
                fields.update(digits="", preview="no attempts", footer="NO ATTEMPTS", accent=False)
            else:
                valid = percent is not None and percent <= 100 and accepted is not None and attempts is not None and 0 <= accepted <= attempts and attempts > 0
                fields["footer"] = f"{percent:.4g}%" if valid else "--%"
                fields["accent"] &= valid
        elif key == "effort":
            fields["digits"] = _face(number(section.get("hours")), 0)
            fields["subtitle"] = f"{_amount(count(section.get('output_tokens')))} tokens"
            fields["accent"] &= fields["digits"] != "--" and not fields["subtitle"].startswith("--")
        elif key == "rewards":
            fields["digits"] = _face(number(section.get("imd")), 2)
            usd_state = section.get("usd_state")
            usd = number(section.get("usd")) if usd_state in _AVAILABLE else None
            fields["subtitle"] = "$" + (f"{usd:.2f}" if usd is not None and (usd == 0 or .01 <= usd < 100000) else _face(usd, 2))
            if usd_state in ("partial", "stale"):
                fields["subtitle"] += " " + usd_state
            fields["accent"] &= fields["digits"] != "--"
        elif key == "rank":
            fields["digits"] = _digits(section.get("rank"))
            fields["subtitle"] = "of " + _count(count(section.get("ranked_of")))
            fields["accent"] &= fields["digits"] != "--" and not fields["subtitle"].endswith("--")
        elif key == "status":
            fields["stats"] = tuple((name, _count(count(section.get(name)))) for name in ("working", "capacity", "devices"))
            fields["footer"] = _status_word(section)
            kind = section.get("last_work_kind")
            kind = kind if kind in ("worked", "accepted") else "work"
            fields["subtitle"] = f"{kind} {hhmm(number(section.get('last_work_ts')), unknown='--:--')}"
            if section.get("live_state") == "paused":
                fields["subtitle"] = "until " + hhmm(number(section.get("paused_until_ts")), unknown="--:--")
            elif state != "ok" and fields["footer"] != "UNKNOWN":
                fields["subtitle"] = fields["footer"]
            fields["accent"] &= section.get("live_state") == "working" and all(value != "--" for _, value in fields["stats"])
        elif key == "owner":
            fields["digits"] = "--"  # Width-fitted address with rich actions in AgentRackCard.
            fields["subtitle"] = "paired " + mmdd(number(section.get("paired_ts")), unknown="--")
            fields["accent"] &= is_address(section.get("address"))
        elif key == "runtime":
            runtime = flatten(section.get("runtime"))
            runtime_id, _, version = runtime.partition(" ")
            if runtime_semver(runtime_id, version) is not None:
                version = version.removesuffix(" (Claude Code)").removeprefix("codex-cli ")
            fields["stats"] = ((runtime_id or "runtime", version or "--"),
                               ("daemon", flatten(section.get("daemon")) or "--"),
                               ("devices", _count(count(section.get("devices")))))
            update = section.get("update_state")
            current = state == "ok" and update == "current" and hhmm(number(section.get("checked_ts")), unknown="--") != "--"
            fields["subtitle"] = "up to date" if current else "update available" if update == "outdated" else "check pending" if update == "pending" else "not checked" if update == "not_checked" else "check unknown"
            if section.get("daemon_differs") is True:
                fields["subtitle"] = "runtime + daemon ↑" if update == "outdated" else "daemon differs"
            fields["accent"] &= all(value != "--" for _, value in fields["stats"])
        elif key == "feedback":
            fields["stats"] = tuple((name, _count(count(section.get(name)))) for name in ("sent", "submitted", "queued"))
            fields["subtitle"] = "review msgs"
            fields["footer"] = _count(count(section.get("queued"))) + " QUEUED"
            fields["accent"] &= all(value != "--" for _, value in fields["stats"])
        elif key == "collab":
            fields["digits"] = _digits(section.get("count"))
            fields["subtitle"] = "collaborators"
            rows = _rows(section)
            if rows:
                top = rows[0]
                fields["footer"] = f"TOP #{_count(count(top.get('token_id')))} x{_amount(count(top.get('shared_jobs')))}"
            elif rows == []:
                fields["footer"] = "NONE YET"
            fields["accent"] &= fields["digits"] != "--" and rows is not None
        else:
            rows = _rows(section)
            fields["subtitle"] = (f"{len(rows)} model{'s' if len(rows) != 1 else ''}" if rows is not None else "models --") if key == "models" else "work by node"
            if rows == []:
                fields.update(preview="not advertised" if key == "models" else "no nodes yet", accent=False)
            elif rows is None:
                fields.update(digits="--", accent=False)
            else:
                shown = rows if len(rows) <= 3 else rows[:2]
                if key == "models":
                    stats = [(short_model(row.get("model")) or "--", flatten(row.get("effort")) or "--") for row in shown]
                else:
                    stats = [(NODE_TITLES.get(flatten(row.get("node_key")), flatten(row.get("node_key"))).lower() or "--",
                              _count(count(row.get("accepted")))) for row in shown]
                if len(rows) > 3:
                    stats.append((f"+{len(rows) - 2} more", ""))
                fields["stats"] = tuple(stats)
                fields["accent"] &= all(label != "--" and value != "--" for label, value in stats)
        if state == "stale_unknown_seat":
            fields["subtitle"] = "never paired"
        records.append(HeroRecord(**fields))
    return tuple(records)


class AgentRackCard(Pool4HeroCard):
    """Shared rack rendering with seat meters and the rich owner affordance."""

    def __init__(self, record):
        self.source = {}
        self.raw_record = record
        self.runtime_clipped = False
        self.owner_text = Text()
        super().__init__(record)

    def _fit_content(self, record):
        if record.key == "owner":
            address = self.source.get("address")
            room = max(1, self.content_size.width - 4)
            self.owner_text = (address_text(address, label=self.source.get("name"), width=min(17, room), explorer=EXPLORER)
                               if record.state in _AVAILABLE and is_address(address) else Text("--"))
            record = replace(record, digits=self.owner_text.plain)
        elif record.key == "runtime" and record.stats:
            label, daemon = record.stats[1]
            suffix = "↑" if self.source.get("daemon_differs") is True and record.state in _AVAILABLE else ""
            room = max(1, self.content_size.width - 3 - len(label) - len(suffix))
            self.runtime_clipped = cell_len(daemon) > room
            fitted = clip(daemon, room) + suffix
            record = replace(record, stats=(record.stats[0], (label, fitted), record.stats[2]))
        return record

    def set_source(self, record, source):
        self.source = source
        self.raw_record = record
        super().set_record(self._fit_content(record))
        self.tooltip = self._source_tooltip(record, source)

    def on_resize(self):
        self.data = self._fit_content(self.raw_record)
        super().on_resize()

    def _update_title(self):
        super()._update_title()
        if self.data.key == "runtime" and self.runtime_clipped:
            self.border_title = Text(title_with_hint("⊙ RUNTIME", True, max(0, self.region.width - 6)))
        if (self.data.key == "owner" and self.data.state in _AVAILABLE
                and cell_len(flatten(self.source.get("name"))) > max(1, self.content_size.width - 4)):
            self.border_title = Text(title_with_hint("⊙ OWNER", True, max(0, self.region.width - 6)))

    def _footer(self):
        data = self.data
        if data.state in ("pending", "busy", "unknown_seat", "empty"):
            word = {"unknown_seat": "never paired", "empty": "EMPTY"}.get(data.state, data.state)
            self.border_subtitle = Text().append(word, style="dim" if data.state == "empty" else "yellow")
        elif data.state == "stale_unknown_seat":
            self.border_subtitle = Text().append("stale " + hhmm(data.read_ts, unknown="--:--"), style="yellow")
        elif data.state != "ok":
            super()._footer()
        elif data.key == "status":
            room = max(5, self.size.width - 6)
            word = _status_word(self.source)
            if word in ("PAUSED", "UNKNOWN"):
                self.border_subtitle = Text().append(word, style="red" if word == "PAUSED" else "yellow")
            else:
                meter = {key: self.source.get(key) for key in ("meter_kind", "meter_state", "numerator", "denominator")}
                self.border_subtitle = meter_text(dict(meter, key="agent"), width=room)
        elif data.key == "accepted" and data.footer not in ("NO ATTEMPTS", "--%"):
            label = data.footer + " "
            track = meter_text(dict(key="accepted", numerator=number(self.source.get("accepted")), denominator=number(self.source.get("attempts"))),
                               width=max(4, self.size.width - 6 - len(label) + 4))[4:]
            self.border_subtitle = Text(label, style="dim").append_text(track)
        else:
            super()._footer()

    def render(self):
        content = super().render()
        if self.data.key == "status" and self.data.state in _AVAILABLE:
            live = self.source.get("live_state")
            if live in ("offline", "paused"):
                content.stylize(Style(color=Color.from_triplet(self.app.ansi_theme.ansi_colors[1]), dim=False))
            elif live == "idle":
                content.stylize(Style(color=self.rich_style.color, dim=True))
        if self.data.key == "owner":
            offset = content.plain.find(self.owner_text.plain)
            if offset >= 0:
                for span in self.owner_text.spans:
                    content.stylize(span.style, offset + span.start, offset + span.end)
        return content

    @staticmethod
    def _source_tooltip(record, source):
        state = "stale · never paired" if record.state == "stale_unknown_seat" else record.state
        tip = Text(f"{record.title} · {state} · as of {hhmm(record.read_ts, unknown='--:--')} local")
        rows = _rows(source)
        if record.key == "owner" and record.state in _AVAILABLE and is_address(source.get("address")):
            tip.append("\n").append_text(address_text(source["address"], explorer=EXPLORER))
            tip.append("\npaired " + mmdd_hhmm(number(source.get("paired_ts"))))
        elif record.key == "runtime":
            tip.append(f"\n{flatten(source.get('runtime'))} · daemon {flatten(source.get('daemon'))}"
                       f"\nlatest {flatten(source.get('latest_version')) or '--'} · checked {hhmm(number(source.get('checked_ts')), unknown='--:--')} local"
                       f"\nfleet daemon {flatten(source.get('fleet_daemon')) or '--'} · {_count(count(source.get('fleet_count')))}/{_count(count(source.get('fleet_total')))} workers")
            if source.get("daemon_differs") is True:
                tip.append(" · daemon differs")
        elif record.key == "rewards":
            usd_state = source.get("usd_state") if source.get("usd_state") in _STATES else "unavailable"
            tip.append(f"\nowner share across {_count(count(source.get('seats')))} seats"
                       f"\nUSD {usd_state} · as of {hhmm(number(source.get('usd_read_ts')), unknown='--:--')} local")
        elif record.key == "status":
            work_state = source.get("work_state") if source.get("work_state") in _STATES else "unavailable"
            tip.append(f"\nlast work {mmdd_hhmm(number(source.get('last_work_ts')))} · {work_state}"
                       f"\nwork read {hhmm(number(source.get('work_read_ts')), unknown='--:--')} local")
            if source.get("live_state") == "paused":
                tip.append(f"\npaused until {mmdd_hhmm(number(source.get('paused_until_ts')))} · {_count(count(source.get('failures')))} failures")
        elif record.key == "rank":
            delta = _number(source.get("delta"), signed=True)
            tip.append("\nrank change " + (f"{delta:+g}" if delta is not None else "--"))
        elif record.key == "accepted":
            tip.append(f"\n{_count(count(source.get('accepted')))} / {_count(count(source.get('attempts')))} · {_face(source.get('percent'), 1)}%")
        elif record.key in ("models", "collab", "nodes") and rows is not None:
            for row in rows:
                if record.key == "models":
                    line = flatten(row.get("model")) + " · " + flatten(row.get("effort"))
                elif record.key == "collab":
                    line = f"#{_count(count(row.get('token_id')))} x{_count(count(row.get('shared_jobs')))}"
                else:
                    accepted, attempts = count(row.get("accepted")), count(row.get("attempts"))
                    rate = f"{100 * accepted / attempts:.4g}%" if accepted is not None and attempts and accepted <= attempts else "--"
                    line = f"{flatten(row.get('node_key'))} · {_count(accepted)} accepted / {_count(attempts)} attempts · {rate}"
                tip.append("\n" + line)
        return tip


class SurfSwarmAgentRackHero(Grid):
    DEFAULT_CSS = """
    SurfSwarmAgentRackHero { width: 1fr; height: 19; grid-size: 6 2;
        grid-columns: 1fr; grid-rows: 9; grid-gutter: 1 1; }
    """

    def compose(self) -> ComposeResult:
        for record in agent_records(None):
            yield AgentRackCard(record)

    def update_data(self, *, surf_agent_hero=None, **kwargs):
        for record in agent_records(surf_agent_hero):
            self.query_one(f"#hero-{record.key}", AgentRackCard).set_source(record, _source(surf_agent_hero, record.key))
