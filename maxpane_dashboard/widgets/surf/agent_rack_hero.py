"""Twelve AGENT rack cards over independently observed primitive facts."""
from __future__ import annotations

from dataclasses import replace

from rich.color import Color, blend_rgb
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid
from textual.filter import dim_color
from textual.renderables.digits import Digits

from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.analytics.surf_swarm_signals import runtime_semver
from maxpane_dashboard.widgets.address import ICON_COLS, address_text, is_address, wallet_text
from maxpane_dashboard.widgets.card_inner import inner_styles, padded_inner_row
from maxpane_dashboard.widgets.explorer import IMD
from maxpane_dashboard.widgets.fmt import hhmm, mmdd
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from maxpane_dashboard.widgets.surfboard.rack import meter_text
from ._fmt import EXPLORER, mmdd_hhmm, short_model
from .news_hero import HeroRecord, _count, _number
from .pool4_hero import Pool4HeroCard, _amount, _face

_STATES = ("ok", "partial", "stale", "unavailable", "pending", "busy", "unknown_seat", "stale_unknown_seat", "empty", "failed")
_AVAILABLE = ("ok", "partial", "stale")
_CURRENT_ACTIONS = ("oracling", "auditing", "reviewing", "building", "manifesting",
                    "researching", "testing", "designing", "frontending", "implementing")


def _source(payload, key):
    source = payload.get(key) if isinstance(payload, dict) else None
    return source if isinstance(source, dict) else {}


def _card_source(payload, key):
    source = _source(payload, "nodes" if key == "models" else key)
    if key == "runtime":
        return dict(source, models=_source(payload, "models"))
    return source


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
        ("seat", "AGENT", "SEAT", "ERC-8004 #--"),
        ("status", "STATUS", "WORKER", "UNKNOWN"),
        ("accepted", "ACCEPTED WORK", "JOBS", ""),
        ("nodes", "LAUNCHES", "JOBS", ""),
        ("models", "RESEARCH", "JOBS", ""),
        ("effort", "EFFORT", "HOURS", ""),
        ("runtime", "RUNTIME", "SOFTWARE", ""),
        ("owner", "OWNER", "WALLET", ""),
        ("rank", "RANK", "POSITION", ""),
        ("collab", "COLLAB", "SEATS", ""),
        ("rewards", "REWARDS", "IMD", ""),
        ("earnings", "EARNINGS", "TOKENS", ""),
    ):
        raw = _card_source(payload, key)
        state = raw.get("state")
        state = state if state in _STATES else "pending" if payload is None else "unavailable"
        section = raw if state in _AVAILABLE else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=number(raw.get("read_ts")), accent=state == "ok")
        if key == "seat":
            token = count(raw.get("token_id"))
            fields["digits"] = str(token) if token is not None and number(token) is not None else "--"
            presence = _source(payload, "status").get("live_state")
            fields["subtitle"] = {"working": "swarming", "idle": "ready", "paused": "ON", "offline": "offline"}.get(presence, "status --")
            agent_id = raw.get("agent_id")
            agent_id = agent_id if isinstance(agent_id, str) and agent_id.isascii() and agent_id.isdecimal() else "--"
            fields["footer"] = f"ERC-8004 #{agent_id}"
            if token is None and state == "empty":
                fields.update(digits="", preview="no seat selected", subtitle="")
            fields["accent"] = token is not None and presence in ("working", "idle", "paused")
        elif key in ("accepted", "effort", "rank") and section.get("listed") is False:
            fields.update(preview="no receipts" if key == "effort" else "not recorded", accent=False)
        elif key == "accepted":
            accepted, attempts = (count(section.get(name)) for name in ("accepted", "attempts"))
            fields["digits"] = f"{accepted:,}" if accepted is not None else "--"
            percent = number(section.get("percent"))
            if attempts == 0 and accepted == 0:
                fields.update(digits="", preview="no attempts", accent=False)
            else:
                valid = percent is not None and percent <= 100 and accepted is not None and attempts is not None and 0 <= accepted <= attempts and attempts > 0
                fields["subtitle"] = f"{percent:.4g}%" if valid else "--%"
                fields["accent"] = False
        elif key == "effort":
            fields["digits"] = _face(number(section.get("hours")), 0)
            fields["subtitle"] = f"{_amount(count(section.get('output_tokens')))} tokens"
            fields["accent"] = False
        elif key == "rewards":
            fields["digits"] = _face(number(section.get("imd")), 2)
            usd_state = section.get("usd_state")
            usd = number(section.get("usd")) if usd_state in _AVAILABLE else None
            fields["subtitle"] = "$" + (f"{usd:.2f}" if usd is not None and (usd == 0 or .01 <= usd < 100000) else _face(usd, 2))
            fields["accent"] = section.get("paid_recent") is True
        elif key == "rank":
            fields["digits"] = _digits(section.get("rank"))
            fields["subtitle"] = "of " + _count(count(section.get("ranked_of")))
            delta = _number(section.get("delta"), signed=True)
            fields["footer"] = f"{'↑' if delta > 0 else '↓'} {abs(delta):g}" if delta else ""
            fields["accent"] = delta is not None and delta > 0
        elif key == "status":
            fields["digits"] = f"{_count(count(section.get('working')))} 0F {_count(count(section.get('capacity')))}"
            fields["footer"] = _status_word(section)
            kind = section.get("last_work_kind")
            kind = kind if kind in ("worked", "accepted") else "work"
            fields["subtitle"] = f"{kind} {hhmm(number(section.get('last_work_ts')), unknown='--:--')}"
            if (count(section.get("working")) or 0) > 0:
                action = section.get("current_action")
                fields["subtitle"] = action if action in _CURRENT_ACTIONS else "working"
            elif section.get("live_state") == "paused":
                fields["subtitle"] = "until " + hhmm(number(section.get("paused_until_ts")), unknown="--:--")
            fields["accent"] = section.get("meter_state") == "busy"
        elif key == "owner":
            fields["digits"] = "--"  # Width-fitted address with rich actions in AgentRackCard.
            fields["subtitle"] = "paired " + mmdd(number(section.get("paired_ts")), unknown="--")
            fields["accent"] = False
        elif key == "runtime":
            runtime = flatten(section.get("runtime"))
            runtime_id, _, version = runtime.partition(" ")
            if runtime_semver(runtime_id, version) is not None:
                version = version.removesuffix(" (Claude Code)").removeprefix("codex-cli ")
            models = _source(raw, "models")
            rows = _rows(models) if models.get("state") in _AVAILABLE else None
            model = "none" if rows == [] else "--"
            if rows:
                model = short_model(rows[0].get("model")) or "--"
                if len(rows) > 1:
                    model += f" +{len(rows) - 1}"
            fields["stats"] = ((runtime_id or "runtime", version or "--"),
                               ("daemon", flatten(section.get("daemon")).partition("+")[0] or "--"),
                               ("model", model))
            fields["subtitle"] = (flatten(rows[0].get("effort")) or "--") if rows else "" if rows == [] else "--"
            fields["accent"] = False
        elif key == "earnings":
            fields["digits"] = _count(count(section.get("wallet_total")))
            fields["subtitle"] = _count(count(section.get("earned"))) + " shipped"
            fields["accent"] = False
        elif key == "collab":
            fields["digits"] = _digits(section.get("count"))
            fields["subtitle"] = "collaborators"
            fields["accent"] = False
        elif key in ("nodes", "models"):
            category = "launches" if key == "nodes" else "research"
            accepted, total = count(section.get(category)), count(section.get(category + "_total"))
            fields["digits"] = _digits(total)
            valid = accepted is not None and total is not None and 0 <= accepted <= total and total > 0
            fields["subtitle"] = f"{100 * accepted / total:.4g}%" if valid else "" if total == 0 else "--%"
            fields["accent"] = False
        if state in ("unknown_seat", "stale_unknown_seat") and key not in ("models", "nodes", "runtime"):
            fields["subtitle"] = "never paired"
        records.append(HeroRecord(**fields))
    return tuple(records)


class AgentRackCard(Pool4HeroCard):
    """Shared rack rendering with seat meters and the rich owner affordance."""

    DEFAULT_CSS = "AgentRackCard { link-color: $foreground; }"

    def __init__(self, record):
        self.source = {}
        self.raw_record = record
        self.owner_text = Text()
        super().__init__(record)
        self.styles.border_subtitle_align = "center"

    def _present_record(self, record):
        if record.key in ('accepted', 'nodes', 'models'):
            record = replace(record, subtitle=self._values.field('job-rate', record.subtitle))
        if record.key == "earnings":
            record = replace(record, subtitle=self._values.field(
                "shipped-caption", record.subtitle, numeric=True))
        return super()._present_record(record)

    def _fit_content(self, record):
        if record.key == "owner":
            address = self.source.get("address")
            address = self._values.field('owner-address', address if record.state in _AVAILABLE and is_address(address) else '--')
            name = self._values.field('owner-name', (flatten(self.source.get('name')) or '') if record.state in _AVAILABLE and is_address(self.source.get('address')) else '--')
            room = max(1, self.content_size.width - 4 - ICON_COLS)
            self.owner_text = (wallet_text(address, label=name or None, width=min(17, room), explorer=IMD)
                               if is_address(address) else Text(''))
            # Below the safe address-window width keep the link, copy and full tooltip.
            if self.owner_text.cell_len > room + ICON_COLS:
                self.owner_text = wallet_text(address, label="wallet", width=room, explorer=IMD)
            record = replace(record, digits=self.owner_text.plain)
        elif record.key == "runtime" and record.stats:
            runtime, version = record.stats[0]
            if cell_len(runtime) + cell_len(version) + 1 > max(0, self.content_size.width - 4):
                runtime = {"claude": "cld", "codex": "cdx"}.get(runtime, runtime)
            label, daemon = record.stats[1]
            suffix = "↑" if self.source.get("daemon_differs") is True and record.state in _AVAILABLE else ""
            room = max(1, self.content_size.width - 5 - cell_len(label) - cell_len(suffix))
            fitted = clip(daemon, room) + suffix
            model_label, model = record.stats[2]
            rows = _rows(_source(self.source, "models"))
            suffix = f" +{len(rows) - 1}" if rows and len(rows) > 1 and model.endswith(f" +{len(rows) - 1}") else ""
            room = max(1, self.content_size.width - 5 - cell_len(model_label) - cell_len(suffix))
            model = clip(model.removesuffix(suffix) if suffix else model, room) + suffix
            record = replace(record, stats=((runtime, version), (label, fitted), (model_label, model)))
        elif record.key == "status" and cell_len(record.digits) > max(0, self.content_size.width - 4):
            record = replace(record, digits=record.digits.replace(",", ""))
        return record

    def set_source(self, record, source):
        self.source = source
        self.raw_record = record
        category = {'models': 'oracle', 'nodes': 'launches'}.get(record.key)
        if category and record.state in _AVAILABLE and count(source.get(category)) == 0 and count(source.get(category + '_total')) == 0:
            self._values.field('subtitle', '')
        super().set_record(record)
        self.tooltip = self._source_tooltip(record, source)

    def on_resize(self):
        super().on_resize()

    def _update_title(self):
        super()._update_title()
        if (self.data.key == "owner" and self.data.state in _AVAILABLE
                and cell_len(flatten(self.source.get("name"))) > max(1, self.content_size.width - 4 - ICON_COLS)):
            self.border_title = Text(title_with_hint("⊙ OWNER", True, max(0, self.region.width - 6)))
        elif (self.data.key == "runtime" and self._display_record.stats
              and self._display_record.stats[2] != self.data.stats[2]):
            self.border_title = Text(title_with_hint("⊙ RUNTIME", True, max(0, self.region.width - 6)))

    def _footer(self):
        data = self.data
        if data.key in ("owner", "models", "nodes", "runtime", "accepted", "effort", "earnings", "collab", "rewards"):
            self.border_subtitle = Text()
        elif data.state in ("unknown_seat", "stale_unknown_seat", "empty", "unavailable"):
            word = {"unknown_seat": "never paired", "stale_unknown_seat": "never paired", "empty": "EMPTY"}.get(data.state, "")
            # The selected identity remains meaningful if only its detail read failed.
            self.border_subtitle = Text().append(data.footer if data.key == "seat" else word, style="dim" if data.key == "seat" or data.state == "empty" else "yellow")
        elif data.key == "status":
            room = max(5, self.region.width - 6)
            meter = {key: self.source.get(key) for key in ("meter_kind", "meter_state", "numerator", "denominator")}
            self.border_subtitle = self.retained_meter(meter_text(dict(meter, key="agent"), width=room))
        else:
            delta = _number(self.source.get("delta"), signed=True) if data.key == "rank" else None
            color = "green" if delta and delta > 0 else "red" if delta and delta < 0 else "dim"
            self.border_subtitle = Text().append(flatten(data.footer), style=color)

    def _frame_style(self):
        palette = self.app.get_css_variables()
        color = palette["accent"] if self.data.accent else "dim"
        offline = (self.data.key == "seat" and self.source.get("live_state") == "offline"
                   or self.data.key == "status" and self.source.get("meter_state") == "offline")
        delta = _number(self.source.get("delta"), signed=True) if self.data.key == "rank" else None
        if self.data.key == "runtime" and self.data.state in _AVAILABLE and self.source.get("update_state") == "outdated":
            return Style(color=Color.from_triplet(self.app.ansi_theme.ansi_colors[3]), bgcolor=palette["background"], dim=False)
        if offline or delta is not None and delta < 0:
            color = Color.from_triplet(self.app.ansi_theme.ansi_colors[1])
            return Style(color=color, bgcolor=palette["background"], dim=False)
        return Style.parse(color) + Style(bgcolor=palette["background"])

    def _subtitle_value(self, value):
        if self.data.key in ('accepted', 'effort', 'rewards', 'rank', 'earnings', 'nodes', 'models'):
            return self.loading_caption(value)
        return super()._subtitle_value(value)

    def _inner_footer(self, subtitle, inside, frame, value_ink):
        if self.data.key != "runtime":
            return super()._inner_footer(subtitle, inside, frame, value_ink)
        ink = value_ink if subtitle.strip() not in ("", "--") else frame
        caption = Text(subtitle, style=ink)
        rendered = self.loading_value(caption)
        if rendered is not caption:
            rendered = Text(' ').append_text(rendered).append(' ')
        footer = Text("└" + "─" * max(0, inside - rendered.cell_len), style=frame)
        return footer.append_text(rendered).append("┘", style=frame)

    def _status_content(self):
        """One tall readout with an independently muted 0F separator."""
        self._has_missing_value = False
        data = self.data
        inside = max(4, self.content_size.width) - 2
        palette = self.app.get_css_variables()
        frame = self._frame_style()
        ink = Style(color=self.rich_style.color, bgcolor=palette["background"], dim=False)
        active = frame.color in (Color.parse(palette["accent"]), Color.parse("green"))
        _, _, digits = inner_styles(palette, active=active, frame_color=frame.color,
                                    ansi_theme=self.app.ansi_theme, text_color=self.rich_style.color)
        base, surface = self.background_colors
        previous = dim_color(ink.bgcolor, ink.color)
        # Halfway between the card background and the original dim text.
        middle = blend_rgb((base + surface).rich_color.get_truecolor(), previous.get_truecolor())
        separator = ink + Style(color=Color.from_triplet(middle))
        values = data.digits.split()
        groups = [[segment.text for segment in Digits(value).render(Style()) if segment.text != "\n"] for value in values]
        rows = []
        if not values:
            rows = [Text(''), Text(''), Text('')]
        elif len(groups) == 3 and all(value != "--" for value in values) and sum(len(group[0]) for group in groups) + 2 <= inside:
            for n in range(3):
                rows.append(Text(groups[0][n] + " ", style=digits).append(groups[1][n], style=separator).append(" " + groups[2][n], style=digits))
        else:
            row = Text(values[0], style=digits).append(' 0F ', style=separator).append(values[-1], style=digits)
            rows = [Text(''), row, Text('')]
            rows = [padded_inner_row(row, inside, align='center') for row in rows]
        heading = " " + clip(data.heading, inside - 2) + " "
        content = Text("┌" + heading.center(inside, "─") + "┐\n", style=frame)
        for row in rows:
            row.align("center", inside)
            content.append("│", style=frame).append_text(row).append("│\n", style=frame)
        subtitle = " " + clip(data.subtitle, inside - 2) + " " if data.subtitle else ""
        return content.append("└" + subtitle.center(inside, "─") + "┘", style=frame)

    def render(self):
        content = self._status_content() if self.data.key == "status" else super().render()
        if self.data.key == "owner":
            offset = content.plain.find(self.owner_text.plain)
            if offset >= 0:
                for span in self.owner_text.spans:
                    content.stylize(span.style, offset + span.start, offset + span.end)
        return content

    @staticmethod
    def _source_tooltip(record, source):
        coverage = " · partial" if record.state == "partial" else ""
        tip = Text(f"{record.title}{coverage} · as of {hhmm(record.read_ts, unknown='--:--')} local")
        rows = _rows(source)
        if record.key in ("nodes", "models"):
            tip.append("\nDistinct jobs; testnet launches and oracle requests excluded.")
            tip.append("\nVerified live launches and linked workflow jobs." if record.key == 'nodes'
                       else "\nOracle requests plus goal, research and report jobs.")
            category = "launches" if record.key == "nodes" else "research"
            tip.append(f"\nAccepted / total jobs: {_count(count(source.get(category)))} / {_count(count(source.get(category + '_total')))}")
            tip.append(f"\nlaunch evidence known for {_count(count(source.get('known_jobs')))} of {_count(count(source.get('total_jobs')))} accepted non-oracle jobs")
            tip.append(f"\nlaunch reads · as of {hhmm(number(source.get('launch_read_ts')), unknown='--:--')} local")
        if record.key == "owner" and record.state in _AVAILABLE and is_address(source.get("address")):
            tip.append("\n").append_text(wallet_text(source["address"], explorer=IMD))
            tip.append("\npaired " + mmdd_hhmm(number(source.get("paired_ts"))))
        elif record.key == "effort":
            premium, known, total = (_count(count(source.get(key))) for key in ("premium_jobs", "model_jobs", "work_jobs"))
            tip.append(f"\nPremium models: {premium}/{known} known-model work attempts; model coverage {known}/{total} recorded attempts. Astra, Opus, Fable.")
        elif record.key == "runtime":
            tip.append(f"\n{flatten(source.get('runtime'))} · daemon {flatten(source.get('daemon'))}"
                       f"\nlast connected {mmdd_hhmm(number(source.get('connected_ts')))} local; connection time, not a verified restart"
                       f"\nconnection read · as of {hhmm(number(source.get('connected_read_ts')), unknown='--:--')} local"
                       f"\nlatest {flatten(source.get('latest_version')) or '--'} · checked {hhmm(number(source.get('checked_ts')), unknown='--:--')} local"
                       f"\nfleet daemon {flatten(source.get('fleet_daemon')) or '--'} · {_count(count(source.get('fleet_count')))}/{_count(count(source.get('fleet_total')))} workers")
            if source.get("daemon_differs") is True:
                tip.append(" · daemon differs")
            models = _source(source, "models")
            tip.append(f"\nadvertised models · {flatten(models.get('state')) or 'unavailable'}"
                       f" · as of {hhmm(number(models.get('read_ts')), unknown='--:--')} local")
            model_rows = _rows(models) if models.get("state") in _AVAILABLE else None
            if model_rows == []:
                tip.append("\nnot advertised")
            for row in model_rows or []:
                tip.append("\n" + flatten(row.get("model")) + " · " + flatten(row.get("effort")))
        elif record.key == "seat":
            api_status = source.get("api_status")
            if isinstance(api_status, str) and flatten(api_status):
                tip.append("\nAPI pairing status: " + flatten(api_status))
        elif record.key == "rewards":
            tip.append(f"\nowner share across {_count(count(source.get('seats')))} seats"
                       f"\nlast paid {mmdd_hhmm(number(source.get('last_paid_ts')))} local"
                       f"\nUSD · as of {hhmm(number(source.get('usd_read_ts')), unknown='--:--')} local")
        elif record.key == "status":
            tip.append(f"\nlast work {mmdd_hhmm(number(source.get('last_work_ts')))}"
                       f"\nwork read {hhmm(number(source.get('work_read_ts')), unknown='--:--')} local")
            if source.get("live_state") == "paused":
                tip.append(f"\npaused until {mmdd_hhmm(number(source.get('paused_until_ts')))} · {_count(count(source.get('failures')))} failures")
        elif record.key == "rank":
            delta = _number(source.get("delta"), signed=True)
            tip.append("\nrank change " + (f"{delta:+g}" if delta is not None else "--"))
        elif record.key == "accepted":
            tip.append("\nDistinct jobs with accepted work / all attempted jobs; each job counted once.")
            tip.append(f"\n{_count(count(source.get('accepted')))} / {_count(count(source.get('attempts')))} · {_face(source.get('percent'), 1)}%")
        elif record.key == "earnings":
            recent, worked = (count(source.get(key)) for key in ("earned_24h", "worked_on_24h"))
            total = count(source.get('wallet_total'))
            tip.append(f"\nWallet total (mainnet only): {_count(total)}; includes builder, swarm and early rewards."
                       f"\nShipped: {_count(count(source.get('earned')))} distinct token assets linked to this agent's accepted work."
                       f"\nLast 24h: {_count(recent)} earned; {_count(worked)} worked on by this agent."
                       "\nRecent counts use each token's earliest launch/earned timestamp. Seat-specific counts require this agent's accepted work and a builder reward for its current owner.")
            if total is None or recent is None or worked is None:
                tip.append("\n-- means unknown.")
            if is_address(source.get("owner")):
                tip.append("\n").append_text(address_text(source["owner"], explorer=EXPLORER))
        elif record.key == "collab" and rows is not None:
            for row in rows:
                tip.append(f"\n#{_count(count(row.get('token_id')))} x{_count(count(row.get('shared_jobs')))}")
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
        seat = _source(surf_agent_hero, 'seat').get('token_id')
        owner = _source(surf_agent_hero, 'owner').get('address')
        if seat != getattr(self, '_display_seat', None):
            self._display_owner = None
        self._display_seat = seat
        if is_address(owner):
            self._display_owner = owner.lower()
        for record in agent_records(surf_agent_hero):
            source = _card_source(surf_agent_hero, record.key)
            if record.key == "seat":
                source = dict(source, live_state=_source(surf_agent_hero, "status").get("live_state"))
            card = self.query_one(f"#hero-{record.key}", AgentRackCard)
            card.set_value_scope((seat, getattr(self, '_display_owner', None)))
            card.set_source(record, source)
