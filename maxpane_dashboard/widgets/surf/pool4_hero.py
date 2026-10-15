"""The approved POOL4 rack hero, accepting only projected primitive values."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from maxpane_dashboard.widgets.rowfit import GLYPH_HINT, cell_len, clip, title_with_hint
from ._icons import post_preview
from .news_hero import HeroRecord, LocalSourceHeroCard, _count, _number


def _face(value, places, *, signed=False):
    """Four significant digits when the approved fixed precision cannot fit."""
    number = _number(value, signed=signed)
    if number is None:
        return "--"
    fixed = f"{number:.{places}f}"
    if (0 < abs(number) < 1) or len(fixed.replace(".", "").lstrip("-")) > 4:
        return f"{number:.4g}"
    return fixed


def _amount(value):
    """Four significant figures retain the smaller units and queue precision."""
    number = _number(value)
    if number is None:
        return "--"
    if number >= 1e12:
        return f"{number:.4g}"
    for scale, unit in ((1e9, "B"), (1e6, "M"), (1000, "k")):
        if number >= scale:
            return f"{number / scale:.4g}{unit}"
    return f"{number:.4g}"


def pool4_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("price", "IMD PRICE", "USD", "POOL4"),
        ("rate", "sIMD RATE", "IMD", "EXCHANGE"),
        ("staking", "STAKING", "APR %", "REALISED"),
        ("vault", "VAULT", "STATS", "STAKED"),
        ("bid", "DOWNSIDE BID", "ETH", "BID"),
        ("queue", "DRIP QUEUE", "DELIVERY", "RATE LIMITED"),
    ):
        section = payload.get(key)
        section = section if isinstance(section, dict) else {}
        state = section.get("state")
        state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
        available = state != "unavailable"
        fields = dict(key=key, title=title, heading=heading, footer=footer,
                      state=state, read_ts=_number(section.get("read_ts")), accent=state == "ok")
        if key in ("price", "rate", "staking"):
            field, places = {"price": ("usd", 3), "rate": ("imd", 3), "staking": ("apr", 1)}[key]
            fields["digits"] = _face(section.get(field) if available else None, places, signed=key == "staking")
            fields["accent"] = state == "ok" and fields["digits"] != "--"
            if key == "price":
                gap = _number(section.get("gap_pct"), signed=True) if available else None
                venue = flatten(section.get("venue"))
                venue = "ref" if venue == "reference" else venue
                fields["subtitle"] = (f"{venue} {_face(-abs(gap), 2, signed=True)}%" if gap is not None and venue in ("here", "ref")
                                      else "no venue edge" if gap is not None else "venue --")
            else:
                fields["subtitle"] = "per 1 sIMD" if key == "rate" else "trailing 7d"
        elif key == "vault":
            holders = _count(section.get("holders")) if available else "--"
            if (section.get("holders_partial") is True or section.get("holders_state") == "partial") and holders != "--":
                holders = "≥" + holders
            fields["stats"] = (("IMD", _amount(section.get("imd")) if available else "--"),
                               ("sIMD", _amount(section.get("simd")) if available else "--"),
                               ("addresses", holders))
        elif key == "bid":
            status = flatten(section.get("status")) if available else ""
            if status == "deployed":
                fields["digits"] = _face(section.get("eth"), 2)
                distance = _number(section.get("distance_pct"))
                fields["subtitle"] = f"{_face(distance, 2)}% under" if distance is not None else "distance --"
                fields["footer"] = "DEPLOYED"
                fields["accent"] = state == "ok" and fields["digits"] != "--"
            else:
                fields["preview"] = "none deployed" if status == "none" else "unavailable"
                fields["accent"] = False
        else:
            fields["stats"] = tuple((label, (_amount(section.get(field)) if available else "--") + unit)
                                    for label, field, unit in (("queued", "imd", " IMD"), ("cap", "per_day", " IMD/d"), ("queue", "days", "d")))
        records.append(HeroRecord(**fields))
    return tuple(records)


class Pool4HeroCard(LocalSourceHeroCard):
    """Advertise lost content using the actual inset and border budgets."""

    def set_record(self, data):
        super().set_record(data)
        self._update_title()

    def on_resize(self):
        super().on_resize()
        self._update_title()

    def _update_title(self):
        data = self.data
        inside = max(4, self.content_size.width) - 2
        # Textual reserves corners, border stubs and spaces around labels.
        room = max(0, self.region.width - 6)
        title = "⊙ " + flatten(data.title)
        footer = self.border_subtitle
        footer = footer.plain if hasattr(footer, "plain") else strip_tags(footer)
        clipped = (cell_len(title) > room or cell_len(footer) > room
                   or cell_len(flatten(data.heading)) + 2 > inside
                   or bool(data.subtitle) and cell_len(flatten(data.subtitle)) + 2 > inside
                   or bool(data.digits) and cell_len(data.digits) > inside
                   or any(cell_len(flatten(label)) + cell_len(flatten(value)) + 1 + 2 * self.STAT_PADDING > inside
                          for label, value in data.stats)
                   or any(cell_len(flatten(row)) > inside for row in data.rows))
        if data.preview:
            clipped |= any(row.plain.endswith("...") for row in post_preview(data.preview, inside, ""))
        if clipped:
            fitted = title_with_hint(title, True, room)
            if GLYPH_HINT not in fitted:
                fitted = clip(title, max(0, room - 3)) + "  " + GLYPH_HINT
            title = fitted
        self.border_title = Text(title)


class SurfPool4RackHero(Grid):
    DEFAULT_CSS = """
    SurfPool4RackHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in pool4_records(None):
            yield Pool4HeroCard(record)

    def update_data(self, *, surf_pool4_hero=None, **kwargs):
        for record in pool4_records(surf_pool4_hero):
            card = self.query_one(f"#hero-{record.key}", Pool4HeroCard)
            card.set_record(record)
            if record.key == "vault":
                source = surf_pool4_hero.get("vault") if isinstance(surf_pool4_hero, dict) else None
                source = source if isinstance(source, dict) else {}
                state = source.get("holders_state")
                state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
                card.tooltip = Text(str(card.tooltip) + f"\nholders {state} · as of {hhmm(source.get('holders_read_ts'), unknown='--:--')} local")
