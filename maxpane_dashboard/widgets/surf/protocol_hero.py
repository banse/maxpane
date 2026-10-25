"""Six protocol rack cards over the manager's read-only projection."""
from __future__ import annotations

from dataclasses import replace

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.widgets.rowfit import cell_len
from .news_hero import HeroRecord, _number
from .pool4_hero import Pool4HeroCard, _amount, _face
from .pool4_split import COUNTER_WORDS, PATH_DIRECT, PATH_VIA_DISTRIBUTOR


def _signed_amount(value):
    number = _number(value, signed=True)
    return "--" if number is None else ("-" if number < 0 else "") + _amount(abs(number))


def protocol_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    """Keep source state, unknown values and reward routing explicit."""
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("totals", "TOTALS", "IMD", "CUMULATIVE"),
        ("inventory", "INVENTORY", "IMD", "RATCHET"),
        ("split", "REWARD SPLIT", "REWARD %", "* DERIVED"),
        ("unsettled", "UNSETTLED", "IMD", "PENDING"),
        ("delivery", "DELIVERY", "IMD", "RATE LIMITED"),
        ("checks", "CHECKS", "STATUS", "ACCOUNTING"),
    ):
        source = payload.get(key)
        source = source if isinstance(source, dict) else {}
        state = source.get("state")
        state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
        section = source if state != "unavailable" else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=_number(source.get("read_ts")), accent=state == "ok")
        if key in ("totals", "inventory", "unsettled", "delivery"):
            columns = {
                "totals": (("settled", "burned", ""), ("rewarded", "rewarded", ""), ("fees", "fees", "")),
                "inventory": (("cap", "cap", ""), ("reserve", "reserve", ""), ("headroom", "headroom", "")),
                "unsettled": (("burn", "burn", ""), ("rewards", "rewards", "")),
                "delivery": (("queued", "queued", ""), ("ready", "ready", ""), ("cap", "per_day", "/d")),
            }[key]
            fields["stats"] = tuple(
                (label, (_signed_amount(section.get(field)) if field == "headroom"
                         else _amount(section.get(field))) + suffix)
                for label, field, suffix in columns)
            fields["accent"] &= all(not value.startswith("--") for _, value in fields["stats"])
        elif key == "split":
            path = section.get("path")
            if path == PATH_VIA_DISTRIBUTOR:
                stats = []
                for label, field in (("staking", "staking_pct"), ("nodes", "nodes_pct"), ("bonding*", "bonding_pct")):
                    percent = _number(section.get(field))
                    stats.append((label, f"{percent:.4g}%" if percent is not None and percent <= 100 else "--"))
                fields["stats"] = tuple(stats)
                fields["accent"] &= all(value != "--" for _, value in stats)
                fields["subtitle"] = "* derived" if state != "ok" else ""
            else:
                fields["heading"] = "ROUTE"
                fields["rows"] = ("to stakers" if path == PATH_DIRECT else "route --",)
                fields["footer"] = "DIRECT" if path == PATH_DIRECT else "CONFIGURATION"
                fields["accent"] &= path == PATH_DIRECT
        else:
            counters = section.get("counters")
            counters = counters if isinstance(counters, str) and counters in COUNTER_WORDS else None
            word = ("MISMATCH" if counters == "mismatch" else "reconciled"
                    if counters == "reconciled" else "not established")
            if counters in ("window-limited", "unchecked"):
                fields["subtitle"] = counters
            drift = _number(section.get("drift_bps"), signed=True)
            path = section.get("path")
            route = "distributor" if path == PATH_VIA_DISTRIBUTOR else "direct" if path == PATH_DIRECT else "route --"
            fields["rows"] = (word, f"drift {_face(drift, 1, signed=True)} bps", route)
            alarm = counters == "mismatch" or drift is not None and drift != 0
            fields["accent"] &= counters == "reconciled" and drift == 0 and route != "route --"
            if alarm:
                fields["footer"] = "CHECK FAILED"
        records.append(HeroRecord(**fields))
    return tuple(records)


class ProtocolHeroCard(Pool4HeroCard):
    """Accounting failures stay alarming even when their source becomes stale."""

    def _fit_content(self, record):
        room = max(0, self.content_size.width - 4)
        short_labels = {"rewarded": "rewards", "headroom": "room"}
        stats = tuple((short_labels.get(label, label) if cell_len(label) + cell_len(value) + 1 > room else label, value)
                      for label, value in record.stats)
        return replace(record, stats=stats)

    def set_record(self, record):
        self.raw_record = record
        super().set_record(record)

    def on_resize(self):
        super().on_resize()

    def _footer(self):
        super()._footer()
        if self.data.footer == "CHECK FAILED" and self.data.state == "ok":
            self.border_subtitle = Text(self.data.footer, style=Style(
                color=Color.from_triplet(self.app.ansi_theme.ansi_colors[1]), dim=False))

    def _frame_style(self):
        frame = super()._frame_style()
        if self.data.footer == "CHECK FAILED":
            frame += Style(color=Color.from_triplet(self.app.ansi_theme.ansi_colors[1]), dim=False)
        return frame

    def _text_rows(self, label_style, value_style):
        rows = super()._text_rows(label_style, value_style)
        if self.data.key == "checks" and len(rows) > 1:
            rows[1].stylize(value_style, len("drift "), len(rows[1].plain) - len(" bps"))
        return rows


class SurfProtocolHero(Grid):
    DEFAULT_CSS = """
    SurfProtocolHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in protocol_records(None):
            yield ProtocolHeroCard(record)

    def update_data(self, *, surf_protocol_hero=None, **kwargs):
        for record in protocol_records(surf_protocol_hero):
            self.query_one(f"#hero-{record.key}", ProtocolHeroCard).set_record(record)
