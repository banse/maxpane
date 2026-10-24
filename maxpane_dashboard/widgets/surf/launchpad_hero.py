"""Launchpad rack cards over projected, independently observed facts."""
from __future__ import annotations

from dataclasses import replace

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.rowfit import cell_len
from .news_hero import HeroRecord, _count
from .pool4_hero import Pool4HeroCard, _amount, _face


def launchpad_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("coins", "COINS", "COINS", "FACTORY"),
        ("flow", "CURVE FLOW", "HISTORY", "OBSERVED"),
        ("volume", "VOLUME", "kUSD", "2H"),
        ("fees", "CREATOR FEES", "ETH", "UNCLAIMED"),
        ("queue", "BURN QUEUE", "IMD", "UNKNOWN"),
        ("burned", "BURNED", "kIMD", "EVENT TOTAL"),
    ):
        source = payload.get(key)
        source = source if isinstance(source, dict) else {}
        state = source.get("state")
        state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
        section = source if state != "unavailable" else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=number(source.get("read_ts")), accent=state == "ok")
        if key == "coins":
            total = count(section.get("count"))
            new = _amount(count(section.get("new_24h")))
            fields["digits"] = str(total) if total is not None and total < 10000 else _amount(total)
            fields["subtitle"] = f"{new} new /24h"
            fields["accent"] &= fields["digits"] != "--" and new != "--" and count(section.get("swept")) == total
        elif key in ("flow", "queue"):
            columns = ("swaps", "traders", "creators") if key == "flow" else ("accrued", "staged", "sendable")
            validate = count if key == "flow" else number
            stats = []
            for column in columns:
                value = validate(section.get(column))
                amount = _amount(value)
                if key == "flow" and value is not None:
                    # Exact small counts can be shorter than a compact suffix.
                    amount = min(amount, f"{value:,}", key=cell_len)
                stats.append((column, amount))
            stats = tuple(stats)
            fields["stats"] = stats
            fields["accent"] &= all(value != "--" for _, value in stats)
            if key == "queue":
                ready = section.get("ready")
                fields["footer"] = "READY" if ready is True else "WAITING" if ready is False else "UNKNOWN"
                fields["accent"] &= type(ready) is bool
                if state != "ok":
                    fields["subtitle"] = fields["footer"]
        elif key == "fees":
            fields["digits"] = _face(number(section.get("eth")), 4)
            fields["subtitle"] = "owed"
            fields["accent"] &= fields["digits"] != "--"
        else:
            value = number(section.get("usd" if key == "volume" else "imd"))
            # Keep the approved thousand-unit face, switching units for tiny
            # positive balances so scaling cannot underflow to a false zero.
            scale = 1 if value is not None and 0 < value < 1 else 1000
            fields["heading"] = ("k" if scale == 1000 else "") + ("USD" if key == "volume" else "IMD")
            fields["digits"] = _face(value / scale if value is not None else None, 1)
            fields["subtitle"] = "cumulative"
            fields["accent"] &= value is not None
            if key == "volume":
                until = hhmm(number(section.get("until")), unknown="--:--")
                fields["subtitle"] = f"2h to {until}"
                raw = section.get("points")
                points = tuple(number(point) for point in raw) if isinstance(raw, (list, tuple)) and len(raw) == 8 else ()
                fields["points"] = points if points and all(point is not None for point in points) else None
                fields["accent"] &= fields["points"] is not None and until != "--:--"
        records.append(HeroRecord(**fields))
    return tuple(records)


class LaunchpadHeroCard(Pool4HeroCard):
    """Keep complete queue amounts within the padded inset at narrow sizes."""

    def _fit_content(self, record):
        room = max(0, self.content_size.width - 4)
        stats = tuple(("ready" if label == "sendable" and cell_len(label) + cell_len(value) + 1 > room else label, value)
                      for label, value in record.stats)
        return replace(record, stats=stats)

    def set_record(self, record):
        self.raw_record = record
        super().set_record(record)
        if record.stats:
            self.tooltip = Text(str(self.tooltip) + "\n" + "\n".join(f"{label} {value}" for label, value in record.stats))

    def on_resize(self):
        super().on_resize()


class SurfLaunchpadHero(Grid):
    DEFAULT_CSS = """
    SurfLaunchpadHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in launchpad_records(None):
            yield LaunchpadHeroCard(record)

    def update_data(self, *, surf_launchpad_hero=None, **kwargs):
        for record in launchpad_records(surf_launchpad_hero):
            card = self.query_one(f"#hero-{record.key}", Pool4HeroCard)
            card.set_record(record)
            source = surf_launchpad_hero.get(record.key) if isinstance(surf_launchpad_hero, dict) else None
            source = source if isinstance(source, dict) else {}
            detail = ""
            if record.key == "coins":
                detail = f"observed history {_count(count(source.get('swept')))}/{_count(count(source.get('count')))} factory coins; new /24h uses block-based day estimate"
            elif record.key == "volume":
                clock = lambda field: hhmm(number(source.get(field)), unknown="--:--")
                detail = (f"8 completed 15m buckets · until {clock('until')} local"
                          f"\npools {_count(count(source.get('known')))}/{_count(count(source.get('total')))}"
                          f" · volume read {clock('volume_read_ts')} local"
                          f"\ncurrent ETH/USD {_amount(number(source.get('quote')))}"
                          f" · quote read {clock('quote_read_ts')} local")
            if detail:
                card.tooltip = Text(str(card.tooltip) + "\n" + detail)
