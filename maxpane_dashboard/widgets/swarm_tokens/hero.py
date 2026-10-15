"""Six source-aware LAUNCHES cards sharing the approved rack renderer."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.widgets.address import PROSE_ADDRESS_RE
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, LocalSourceHeroCard, _count, _number


def _quantity(value):
    number = _number(value)
    if number is None:
        return "--"
    if number >= 1e12:
        return f"{number:.2e}"
    return fmt_compact(number).replace("K", "k") if number >= 1000 else f"{number:.4g}"


def _volume_face(value):
    number = _number(value)
    if number is None:
        return "kUSD / 24H", "--"
    scale, unit = (1e6, "MUSD") if number >= 1e6 else (1000, "kUSD") if number >= 1000 else (1, "USD")
    return f"{unit} / 24H", f"{number / scale:.4g}"


def token_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    """Format only the selected projection; never infer unread totals as zero."""
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("tokens", "TOKENS", "STATS", "SELECTION"),
        ("volume", "VOLUME", "kUSD / 24H", "MEASURED"),
        ("liquidity", "LIQUIDITY", "PAIRED", "QUOTE ASSETS"),
        ("pools", "POOLS", "STATE", "LIQUIDITY"),
        ("momentum", "MOMENTUM", "24H", "PRICE CHANGE"),
        ("top_volume", "TOP VOLUME", "USD / 24H", "LEADERS"),
    ):
        section = payload.get(key)
        section = section if isinstance(section, dict) else {}
        state = section.get("state")
        state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
        available = state != "unavailable"
        fields = dict(key=key.replace("_", "-"), title=title, heading=heading, footer=footer,
                      state=state, read_ts=_number(section.get("read_ts")), accent=state == "ok")
        if key in ("volume", "liquidity", "momentum") or key == "top_volume" and state in ("partial", "stale"):
            fields["subtitle"] = f"{_count(section.get('known'))}/{_count(section.get('total'))} known"
        if key in ("tokens", "pools", "momentum"):
            columns = {
                "tokens": (("tracked", "tracked"), ("new 24h", "new_24h"), ("chains", "chains")),
                "pools": (("two-sided", "two_sided"), ("one-sided", "one_sided"), ("unknown", "unknown")),
                "momentum": (("rising", "rising"), ("falling", "falling"), ("flat", "flat")),
            }[key]
            fields["stats"] = tuple((label, _count(section.get(field)) if available else "--") for label, field in columns)
            if key == "pools":
                other = _number(section.get("other")) if available else None
                fields["subtitle"] = f"{_count(other)} other" if other is not None and other > 0 else ""
        elif key == "volume":
            fields["heading"], fields["digits"] = _volume_face(section.get("amount") if available else None)
            fields["accent"] = state == "ok" and fields["digits"] != "--"
        elif key == "liquidity":
            rows = []
            for asset in ("imd", "eth"):
                amount = _quantity(section.get(asset)) if available else "--"
                prefix = "≥" if section.get("partial") and amount != "--" else ""
                rows.append(f"{prefix}{amount} {asset.upper()}")
            fields["rows"] = tuple(rows)
        else:
            rows = section.get("rows") if available else None
            if isinstance(rows, list) and rows:
                stats = []
                for row in rows[:3]:
                    if not isinstance(row, dict):
                        continue
                    # The detail popup owns address links; a symbol remains a label.
                    symbol = PROSE_ADDRESS_RE.sub("token", flatten(row.get("symbol"))) or "--"
                    amount = _quantity(row.get("volume_usd"))
                    stats.append((symbol, "$" + amount if amount != "--" else amount))
                fields["stats"] = tuple(stats)
                if not stats:
                    fields["preview"] = "unavailable"
            else:
                fields["preview"] = "No matching tokens" if available and rows == [] and _number(section.get("total")) == 0 else "unavailable"
        records.append(HeroRecord(**fields))
    return tuple(records)


class TokensHeroCard(LocalSourceHeroCard):
    """LAUNCHES card using the shared local source footer."""

    def _text_rows(self, label_style, value_style):
        rows = super()._text_rows(label_style, value_style)
        if self.data.key == "liquidity":
            for row in rows:
                row.stylize(value_style, 0, len(row.plain.rpartition(" ")[0]))
        return rows


class TokensHero(Grid):
    DEFAULT_CSS = """
    TokensHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in token_records(None):
            yield TokensHeroCard(record)

    def update_data(self, *, tokens_hero=None):
        for record in token_records(tokens_hero):
            self.query_one(f"#hero-{record.key}", TokensHeroCard).set_record(record)
