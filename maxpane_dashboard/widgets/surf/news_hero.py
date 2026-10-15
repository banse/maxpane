"""Six rack-style news highlights; accepts projected primitives only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid
from textual.renderables.digits import Digits

from maxpane_dashboard.widgets.card_inner import inner_styles, padded_inner_row
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import HeroBoxBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip
from maxpane_dashboard.widgets.sparkline_common import build_sparkline, fmt_compact
from ._fmt import as_float, fmt_age, fmt_price
from ._icons import post_preview


@dataclass(frozen=True)
class HeroRecord:
    key: str
    title: str
    heading: str
    footer: str
    subtitle: str = ""
    preview: str = ""
    rows: tuple[str, ...] = ()
    stats: tuple[tuple[str, str], ...] = ()
    digits: str = ""
    accent: bool = True
    points: tuple[float, ...] | None = ()
    state: str = "ok"
    read_ts: float | None = None


def _number(value, *, signed=False):
    try:
        value = as_float(value)
    except OverflowError:
        return None
    return value if value is not None and (signed or value >= 0) else None


def _count(value):
    value = _number(value)
    if value is None or not value.is_integer():
        return "--"
    if value >= 1e12:
        return f"{value:.2e}"
    return fmt_compact(value) if value >= 100000 else f"{int(value):,}"


def _price(value):
    value = _number(value)
    if value is None:
        return "--"
    if value >= 1e9:
        return f"{value:.2e}"
    if 0 < value < 0.000001:
        return f"{value:.3g}"
    return fmt_price(value).removeprefix("$")


def _clock(value):
    value = _number(value)
    try:
        return datetime.fromtimestamp(value, timezone.utc).strftime("%H:%M") if value is not None else "--:--"
    except (ValueError, OSError, OverflowError):
        return "--:--"


def news_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    """Format the fixed projection without guessing unavailable data."""
    payload = payload if isinstance(payload, dict) else {}
    result = []
    for key, title, heading, footer in (
        ("announcement", "ANNOUNCEMENT", "LATEST", "OFFICIAL"),
        ("reply", "LATEST REPLY", "COMMUNITY", "REPLY"),
        ("signals", "SIGNALS", "STATUS", "KNOWN"),
        ("activity", "DEV ACTIVITY", "RECENT", "RECENT"),
        ("market", "IMD MARKET", "USD", "PRICE"),
        ("boards", "NFT BOARDS", "STATS", "IDENTITY.MD"),
    ):
        section = payload.get(key)
        section = section if isinstance(section, dict) else {}
        state = section.get("state")
        state = state if state in ("ok", "stale", "unavailable") else "unavailable"
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=_number(section.get("read_ts")), accent=state == "ok")
        available = state != "unavailable"
        if key in ("announcement", "reply"):
            text = flatten(section.get("text")) if available else ""
            fields["preview"] = text or (f"No {'posts' if key == 'announcement' else 'replies'} in cache" if available else "unavailable")
            age = _number(section.get("age_s"))
            fields["subtitle"] = fmt_age(age) + " ago" if text and age is not None else ""
            fields["accent"] = state == "ok" and key == "announcement" and bool(text)
        elif key == "signals":
            known, total = _count(section.get("known", 0)), _count(section.get("total", 11))
            fields["stats"] = tuple((label, _count(section.get(label)) if available and known not in ("0", "--") else "--")
                                    for label in ("fired", "watch", "quiet"))
            fields["footer"] = f"KNOWN {known}/{total}"
            fields["subtitle"] = f"known {known}/{total}" if state != "ok" else ""
            fields["accent"] = False
        elif key == "activity":
            rows = section.get("rows") if available else None
            if isinstance(rows, list):
                fields["rows"] = tuple(f"{fmt_age(_number(row.get('age_s')))} {flatten(row.get('wallet_label'))} {flatten(row.get('kind'))}"
                                       for row in rows[:3] if isinstance(row, dict))
                if not rows:
                    fields["preview"] = "No recent activity"
            else:
                fields["preview"] = "unavailable"
            count = _count(section.get("wallet_count"))
            fields["subtitle"] = f"{count} {'wallet' if count == '1' else 'wallets'}" if count != "--" else ""
        elif key == "market":
            fields["digits"] = _price(section.get("price_usd")) if available else "--"
            change = _number(section.get("change_24h_pct"), signed=True) if available else None
            fields["subtitle"] = f"{change:+.1f}% · 24h" if change is not None else "24h --"
            raw_points = section.get("points")
            points = tuple(value for raw in raw_points if (value := _number(raw)) is not None) if isinstance(raw_points, (list, tuple)) else ()
            fields["points"] = points if available and isinstance(raw_points, (list, tuple)) else None
            fields["accent"] = state == "ok" and _number(section.get("price_usd")) is not None
        else:
            fields["stats"] = tuple((label, _count(section.get(field)) if available else "--")
                                    for label, field in (("holders", "holders"), ("written", "written"), ("24h moves", "moves_24h")))
        result.append(HeroRecord(**fields))
    return tuple(result)


class NewsHeroCard(HeroBoxBase):
    """The rack's five-line inset with a source-aware outer footer."""

    STAT_PADDING = 1
    VALUE_BOLD = False

    DEFAULT_CSS = """
    NewsHeroCard { height: 9; padding: 0 1; border: round $panel; background: $surface;
        color: $text; content-align: center middle; border-title-color: $text-muted;
        border-subtitle-color: $text-muted; border-subtitle-align: left;
        link-color: $foreground; }
    """

    def __init__(self, data: HeroRecord):
        super().__init__(id=f"hero-{data.key}")
        self.set_record(data)

    def set_record(self, data: HeroRecord):
        self.data = data
        self.border_title = Text("⊙ " + flatten(data.title))
        self.tooltip = Text(f"{data.title} · {data.state} · as of {_clock(data.read_ts)} UTC")
        self._footer()
        self.refresh()

    def _footer(self):
        data = self.data
        if data.state != "ok":
            label = "stale " + _clock(data.read_ts) if data.state == "stale" else "unavailable"
            footer = Text(label, style="yellow")
        else:
            footer = Text(flatten(data.footer), style="dim")
            available = max(0, self.size.width - cell_len(data.footer) - 7)
            if data.points and len(data.points) >= 2 and available:
                footer.append(" " + build_sparkline(list(data.points), width=available, pad=False), style=Style(color="green", dim=False))
            elif data.key == "market":
                footer = Text("history unavailable" if data.points is None else "history pending", style="dim")
        self.border_subtitle = footer

    def on_resize(self):
        self._footer()
        self.refresh()

    def _frame_style(self):
        palette = self.app.get_css_variables()
        return Style.parse(palette["accent"] if self.data.accent else "dim") + Style(bgcolor=palette["background"])

    def _text_rows(self, label_style, value_style):
        rows = [Text(flatten(row), style=label_style) for row in self.data.rows[:3]]
        if self.data.key == "activity":
            for row in rows:
                # The news projection formats age first, then wallet and kind.
                row.stylize(value_style, 0, len(row.plain.partition(" ")[0]))
        return rows

    def render(self) -> Text:
        data = self.data
        inside = max(4, self.content_size.width) - 2
        palette = self.app.get_css_variables()
        frame = self._frame_style()
        ink, value_ink, digit_ink = inner_styles(
            palette, active=frame.color in (Color.parse(palette["accent"]), Color.parse("green")),
            frame_color=frame.color, ansi_theme=self.app.ansi_theme)
        if self.VALUE_BOLD:
            value_ink += Style(bold=True)
            digit_ink += Style(bold=True)
        room = max(0, inside - 2)
        centered = False
        if data.preview:
            rows = [padded_inner_row(row, inside) for row in post_preview(data.preview, room, ink)]
        elif data.digits:
            digit_ink = digit_ink if data.digits != "--" else ink
            digits = [Text(segment.text, style=digit_ink) for segment in Digits(data.digits).render(Style()) if segment.text != "\n"]
            if data.digits != "--" and all(character in "0123456789.," for character in data.digits) and all(row.cell_len <= inside for row in digits):
                rows = digits
            else:
                rows = [Text(""), padded_inner_row(Text(data.digits, style=digit_ink), inside, align="center"), Text("")]
            centered = True
        elif data.stats:
            rows = []
            for label, value in data.stats[:3]:
                label, value = flatten(label), clip(flatten(value), room)
                fitted_label = clip(label, max(0, room - cell_len(value) - 1))
                gap = max(0, room - cell_len(fitted_label) - cell_len(value))
                row = Text(fitted_label + " " * gap, style=ink).append(value, style=value_ink if value != "--" else ink)
                rows.append(padded_inner_row(row, inside))
        else:
            rows = [padded_inner_row(row, inside) for row in self._text_rows(ink, value_ink)]
        rows += [Text("", style=ink)] * (3 - len(rows))
        heading = " " + clip(flatten(data.heading), max(0, inside - 2)) + " "
        result = Text("┌" + heading.center(inside, "─") + "┐\n", style=frame)
        for row in rows[:3]:
            row.truncate(inside, overflow="ellipsis")
            row.align("center" if centered else "left", inside)
            result.append("│", style=frame).append_text(row).append("│\n", style=frame)
        subtitle = " " + clip(flatten(data.subtitle), max(0, inside - 2)) + " " if data.subtitle else ""
        result.append("└" + subtitle.center(inside, "─") + "┘", style=frame)
        return result


class LocalSourceHeroCard(NewsHeroCard):
    """Partial coverage is distinct from both an old read and a failed read."""

    def set_record(self, data: HeroRecord):
        super().set_record(data)
        self.tooltip = Text(f"{data.title} · {data.state} · as of {hhmm(data.read_ts, unknown='--:--')} local")

    def _footer(self):
        if self.data.state in ("partial", "stale", "unavailable"):
            label = self.data.state
            if label != "unavailable":
                label += " " + hhmm(self.data.read_ts, unknown="--:--")
            orange = Color.from_triplet(self.app.ansi_theme.ansi_colors[3])
            self.border_subtitle = Text(label, style=Style(color=orange))
        else:
            super()._footer()


class SurfNewsHero(Grid):
    """Six equal cards for the default ONCHAIN NEWS body only."""

    DEFAULT_CSS = """
    SurfNewsHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in news_records(None):
            yield NewsHeroCard(record)

    def update_data(self, *, surf_news_hero: dict | None = None, **kwargs):
        for record in news_records(surf_news_hero):
            self.query_one(f"#hero-{record.key}", NewsHeroCard).set_record(record)
