"""Leaderboard rack cards over independently observed projected facts."""
from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from ._fmt import worked_duration
from ._swarm_seat import seat_token
from .news_hero import HeroRecord, _count, _number
from .pool4_hero import Pool4HeroCard, _amount, _face


def _state(value):
    return value if value in ("ok", "partial", "stale", "unavailable", "pending", "failed") else "unavailable"


def _percent(value):
    value = _number(value)
    return _face(value if value is not None and value <= 100 else None, 1).removesuffix('.0') + '%'


def leaderboard_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("top", "TOP SEAT", "AGENT", "-- accepted"),
        ("recorded", "RECORDED", "SEATS", "-- attempts"),
        ("rate", "ACCEPT RATE", "ACCEPTED", "-- / --"),
        ("launches", "LAUNCHES", "CONTRIBUTORS", "--%"),
        ("workers", "WORKERS", "NOW", "--% run --"),
        ("effort", "EFFORT", "RECEIPTS", "CONTRIBUTORS"),
    ):
        source = payload.get(key)
        source = source if isinstance(source, dict) else {}
        state = _state(source.get("state"))
        section = source if state != "unavailable" else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=_number(source.get("read_ts")), accent=False)
        if key == "top":
            token = seat_token(section.get("token_id"))
            accepted = _amount(seat_token(section.get("accepted")))
            if section.get("empty") is True:
                fields.update(preview="no recorded seats", footer="NO RECORDS")
            else:
                # The canonical identifier never passes through a compact or
                # floating-point formatter; a long ID uses the normal text face.
                fields["digits"] = str(token) if token is not None and _number(token) is not None else "--"
                percent = _number(section.get("percent"))
                fields["subtitle"] = f"{_face(percent if percent is not None and percent <= 100 else None, 1)}%"
                fields["footer"] = f"{accepted} accepted"
        elif key == "recorded":
            seats = seat_token(section.get("seats"))
            fields["digits"] = str(seats) if seats is not None and seats < 10000 else _amount(seats)
            attempts = _amount(seat_token(section.get("attempts")))
            fields["subtitle"] = f"{_amount(seat_token(section.get('online')))} online"
            fields["footer"] = f"{attempts} attempts"
        elif key == "rate":
            accepted, attempts = (seat_token(section.get(field)) for field in ("accepted", "attempts"))
            if accepted == 0 and attempts == 0:
                fields.update(preview="no attempts")
            else:
                percent = _number(section.get("percent"))
                if (percent is None or percent > 100 or accepted is None or attempts is None
                        or attempts == 0 or accepted > attempts):
                    percent = None
                fields["digits"] = _face(percent, 1)
            fields["subtitle"] = "%"
            fields["footer"] = f"{_amount(accepted)} / {_amount(attempts)}"
        else:
            columns = {"launches": ("seats", "claude", "codex"),
                       "workers": ("live", "working", "capacity"),
                       "effort": ("tokens", "turns", "hours")}[key]
            stats = []
            for column in columns:
                value = section.get(column)
                value = _number(value) if column == "hours" else seat_token(value)
                stats.append((column, _count(value) if key == "workers" else _amount(value)))
            fields["stats"] = tuple(stats)
            if key == "launches":
                fields["footer"] = _percent(section.get('percent'))
            elif key == "workers":
                runtime = strip_tags(flatten(section.get('runtime'))) or '--'
                fields["footer"] = f"{_percent(section.get('runtime_percent'))} run {runtime}"
            elif key == "effort":
                fields["footer"] = worked_duration(section.get("wall_clock_ms"))
        records.append(HeroRecord(**fields))
    return tuple(records)


class BoardHeroCard(Pool4HeroCard):
    """BOARD keeps metric footers while source qualifications live on hover."""

    STAT_PADDING = 1
    VALUE_COLOR = "foreground"

    DEFAULT_CSS = "BoardHeroCard { border-subtitle-align: center; }"

    def render(self):
        content = super().render()
        value_color = Style(color=self.app.get_css_variables()[self.VALUE_COLOR]).color
        for span in tuple(content.spans):
            if isinstance(span.style, Style) and span.style.color == value_color:
                content.stylize(Style(color=value_color if self.data.stats else "green", bold=True),
                                span.start, span.end)
            elif (self.data.stats and isinstance(span.style, Style)
                  and span.style.color == self.rich_style.color and span.style.dim is False):
                content.stylize("green", span.start, span.end)
        return content

    def _footer(self):
        data = self.data
        if data.state == "unavailable":
            super()._footer()
        elif (data.key == "launches" and data.state in ("pending", "failed")
              and all(value == "--" for _, value in data.stats) and data.footer == "--%"):
            self.border_subtitle = Text("◌ loading" if data.state == "pending" else "load failed",
                                        style="dim" if data.state == "pending" else "red")
        else:
            self.border_subtitle = Text(data.footer, style="dim")


class SurfSwarmBoardHero(Grid):
    DEFAULT_CSS = """
    SurfSwarmBoardHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in leaderboard_records(None):
            yield BoardHeroCard(record)

    def update_data(self, *, surf_leaderboard_hero=None, **kwargs):
        payload = surf_leaderboard_hero if isinstance(surf_leaderboard_hero, dict) else {}
        for record in leaderboard_records(surf_leaderboard_hero):
            self._set_record(record, payload.get(record.key))

    def set_launch_contribution(self, snapshot):
        """Paint the background contribution read without changing other cards."""
        summary = snapshot.get("summary") if isinstance(snapshot, dict) else None
        record = next(record for record in leaderboard_records({"launches": summary}) if record.key == "launches")
        self._set_record(record, summary)

    def _set_record(self, record, source):
        source = source if isinstance(source, dict) else {}
        card = self.query_one(f"#hero-{record.key}", BoardHeroCard)
        card.set_record(record)
        details = [card.tooltip.plain, {
            "top": "Canonical recorded seats", "recorded": "Canonical recorded seats",
            "rate": "Canonical recorded seats", "launches": "Launch contributions",
            "workers": "Current worker roster", "effort": "Contributor receipts",
        }[record.key]]
        if record.state == "stale":
            details.append("retained values")
        if record.key in ("recorded", "launches"):
            prefix = "online" if record.key == "recorded" else "runtime"
            state = _state(source.get(f"{prefix}_state"))
            clock = hhmm(source.get(f"{prefix}_read_ts"), unknown="--:--")
            details.append(f"{prefix} workers {state} · as of {clock} local")
        if record.key == "launches":
            known, seats = (_count(seat_token(source.get(key))) for key in ("runtime_known", "seats"))
            details.append(f"{known} of {seats} seats have current reported runtimes.")
            details.append("Seats reporting both runtimes count once in each; current metadata, not historical usage.")
            total = _count(seat_token(source.get('total_seats')))
            details.append(f"{seats} of {total} recorded seats contributed to launches.")
            state = _state(source.get('records_state'))
            clock = hhmm(source.get('records_read_ts'), unknown='--:--')
            details.append(f"recorded seats {state} · as of {clock} local")
        elif record.key == "workers":
            known, total, count = (_count(seat_token(source.get(key))) for key in
                                   ('runtime_known', 'runtime_total', 'runtime_count'))
            runtime = strip_tags(flatten(source.get('runtime'))) or '--'
            details.append(f"{count} of {total} online seats run {runtime}.")
            details.append(f"{known} of {total} online seats have complete runtime metadata.")
            details.append("Seats reporting both runtimes count once in each; ties sort by runtime name.")
        card.tooltip = Text("\n".join(details))
