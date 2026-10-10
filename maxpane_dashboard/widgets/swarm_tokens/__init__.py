"""Render-only widgets for the Swarm Tokens market overview."""

from __future__ import annotations

from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.fmt import as_float, fmt_age, fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import HeroBoxBase, HeroRow, PanelBase, RichLogFeed, TableLeaderboard
from maxpane_dashboard.widgets.rowfit import clip, pad
from maxpane_dashboard.widgets.sparkline_common import build_sparkline, fmt_compact
from maxpane_dashboard.widgets.explorer import is_address

__all__ = ["TokensHero", "TokensTable", "NewlyLaunched", "BestPlays", "TokenActivity"]

# Explicit neutral ink renders identically in RichLog and Static; ANSI dim
# white is resolved differently by the two renderers.
_COLUMN_HEADER_STYLE = "#b1b1b1"

def _cell(value, width, style="", *, right=False):
    clean = clip(flatten(value), width)
    return Text(clean.rjust(width) if right else pad(clean, width), style=style)


def _quantity(value):
    number = as_float(value)
    if number is None:
        return "--"
    if abs(number) >= 1000:
        return fmt_compact(number)
    return f"{number:.4g}"


def _usd(value, *, price=False):
    number = as_float(value)
    if number is None:
        return "--"
    return "$" + (f"{number:.5g}" if price else _quantity(number))


def _change(value):
    number = as_float(value)
    return "--" if number is None else f"{number:+.1f}%"


def _change_color(value):
    number = as_float(value)
    return "dim white" if number is None else "red" if number < 0 else "green" if number > 0 else "white"


def _lp_color(state):
    return {"two-sided": "green", "one-token": "yellow", "one-quote": "yellow",
            "withdrawn": "red"}.get(state, "dim white")


def _age(token, as_of):
    stamp, now = as_float(token.get("launched_at")), as_float(as_of)
    return fmt_age(now - stamp) if stamp is not None and now is not None else "--"


def _paired(token):
    amount = _quantity(token.get("paired_amount"))
    symbol = token.get('paired_symbol')
    # The full address and its explorer/copy actions live in the detail popup.
    return amount if amount == "--" else f"{amount} {'token' if is_address(symbol) else flatten(symbol)}"


def _chart(token, width):
    series = token.get("sparkline")
    if not isinstance(series, list):
        return "--"
    points = [as_float(value) for value in series]
    if len(points) > width:
        points = [points[round(i * (len(points) - 1) / (width-1))] for i in range(width)]
    known = [point for point in points if point is not None]
    if len(known) < 2:
        return 'new' if known else '--'
    glyphs = iter(build_sparkline(known, width=len(known), pad=False))
    return ''.join(next(glyphs) if point is not None else ' ' for point in points).rjust(width)


class TokensHeroBox(HeroBoxBase):
    """Dashboard-owned hero geometry is supplied by its screen."""


class TokensHero(HeroRow):
    BOX_CLASS = TokensHeroBox
    BOXES = (("st-hero-total", "TOKENS"), ("st-hero-new", "NEW / 24H"),
             ("st-hero-volume", "VOLUME / 24H"), ("st-hero-liquidity", "LIQUIDITY"))

    def update_data(self, metrics=None):
        data = metrics or {}
        total = fmt_int(data.get("total"))
        liquidity = []
        for asset in ('IMD', 'ETH'):
            value = data.get('liquidity_' + asset.lower())
            prefix = '≥ ' if data.get('liquidity_partial') and value is not None else ''
            liquidity.append(f'{prefix}{_quantity(value)} {asset}')
        bodies = (
            (f"{total} deployed", f"{fmt_int(data.get('two_sided'))} two-sided"),
            (f"{fmt_int(data.get('new_24h'))} launches", "last 24 hours"),
            (_usd(data.get("volume_24h")), f"{fmt_int(data.get('volume_known'))}/{total} volumes known"),
            tuple(liquidity),
        )
        for (widget_id, label), (main, sub) in zip(self.BOXES, bodies):
            self.render_box(f"#{widget_id}", label,
                lambda main=main, sub=sub: Text(main, style="bold white") + Text("\n" + sub, style="dim white"))


class TokensTable(TableLeaderboard):
    TITLE = "ALL TOKENS"
    TABLE_ID = "st-token-table"
    ROW_CAP = None
    SPARK_WIDTH = 20
    COLUMNS = (("LAUNCH", 6), ("TOKEN", 9), ("CHAIN", 5), ("AGE", 4),
               ("PRICE", 11), ("24H %", 8), ("MCAP", 9), ("VOL 24H", 9),
               ("BUY/SELL", 9), ("PAIRED LP", 11), ("PRICE 24H", SPARK_WIDTH+1),
               ("VERDICT", 8))

    class Selected(Message):
        def __init__(self, token):
            super().__init__()
            self.token = token

    class Highlighted(Message):
        def __init__(self, token):
            super().__init__()
            self.token = token

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tokens = {}
        self._as_of = None

    def compose_body(self):
        yield DataTable(id=self.TABLE_ID, cell_padding=1)

    def selected_token(self):
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self._tokens.get(key)

    def build_row(self, index, item):
        change = item.get("change_24h")
        values = (fmt_int(item.get("launch_id")), item.get("symbol", "--"),
            flatten(item.get("chain", "--")).upper(), _age(item, self._as_of),
            ('~' if item.get('market_state') == 'stale' else '') + _usd(item.get("price_usd"), price=True), _change(change),
            _usd(item.get("mcap_usd")), _usd(item.get("volume_24h")),
            f"{_quantity(item.get('buys_24h'))}/{_quantity(item.get('sells_24h'))}",
            _paired(item), ('~' if item.get('history_state') == 'stale' else '') + _chart(item,self.SPARK_WIDTH), item.get("verdict", "--"))
        styles = {1: "bold", 5: _change_color(change), 10: _change_color(change)}
        return tuple(Text(pad(value, width), style=styles[i]) if i == 10 else
                     _cell(value, width, styles.get(i, ""), right=4 <= i <= 9)
                     for i, (value, (_, width)) in enumerate(zip(values, self.COLUMNS)))

    def update_data(self, tokens=None, as_of=None):
        table = self.query_one(DataTable)
        selected = self.selected_token()
        selected_id = str(selected["id"]) if selected else None
        self._as_of = as_of
        self._tokens = {str(row["id"]): row for row in (tokens or []) if isinstance(row, dict) and row.get("id") is not None}
        with table.prevent(DataTable.RowHighlighted):
            table.clear()
            for index, (key, row) in enumerate(self._tokens.items()):
                table.add_row(*self.build_row(index, row), key=key)
            if not self._tokens:
                text = "Unavailable" if tokens is None else "No matching tokens"
                # The message has its own first row and never pretends to be a token.
                table.add_row(Text("--", style="dim white"), Text(text, style="dim white"),
                              *[Text("") for _ in range(len(self.COLUMNS) - 2)], key="_empty")
                self.query_one(".panel-title", Static).update(Text(f"{self.TITLE} · {text}", style="dim white"))
            else:
                keys = list(self._tokens)
                table.move_cursor(row=keys.index(selected_id) if selected_id in keys else 0)
                self.query_one(".panel-title", Static).update(Text(f"{self.TITLE} · {len(keys)} tokens", style="bold"))
        self.post_message(self.Highlighted(self.selected_token()))

    def on_data_table_row_selected(self, event):
        event.stop()
        token = self._tokens.get(event.row_key.value)
        if token is not None:
            self.post_message(self.Selected(token))

    def on_data_table_row_highlighted(self, event):
        event.stop()
        self.post_message(self.Highlighted(self._tokens.get(event.row_key.value)))


class _CompactFeed(RichLogFeed):
    SNAPSHOT = True
    WRAP = False
    HIGHLIGHT = False

    def compose_body(self):
        for log in super().compose_body():
            log.min_width = 1
            yield log


class NewlyLaunched(_CompactFeed):
    TITLE = "NEWLY LAUNCHED / 24H"
    LOG_ID = "st-new-log"
    HEADER_LINE = Text("AGE  TOKEN      CHAIN PAIRED LP\n", style=_COLUMN_HEADER_STYLE)
    EMPTY_LINE = Text("No launches in the last 24h", style="dim white")

    def update_data(self, newly_launched=None, as_of=None):
        self._as_of = as_of
        self.render_events(newly_launched)

    def format_row(self, event):
        return (Text() + _cell(_age(event, self._as_of), 5, "dim") +
                _cell(event.get("symbol", "--"), 11, "bold") +
                _cell(flatten(event.get("chain", "--")).upper(), 6) +
                _cell(_paired(event), 18, right=True))


class BestPlays(PanelBase):
    DEFAULT_CSS = "BestPlays > #st-best-body { color: $foreground; }"
    TITLE = "BEST PLAYS / 24H · TOP 5"

    def compose_body(self):
        yield Static(Text("--", style="dim white"), id="st-best-body")

    def update_data(self, gainers=None, losers=None):
        result = Text().append("GAINERS               LOSERS\n\n", style=_COLUMN_HEADER_STYLE)
        markers = {}
        for index in range(min(5, max(len(gainers or []), len(losers or []), 1))):
            for side, entries in enumerate((gainers, losers)):
                if index < len(entries or []):
                    item = entries[index]
                    name = f"{flatten(item.get('symbol', '--'))} {flatten(item.get('chain', '--')).upper()}"
                    state = item.get("lp_state", "unknown")
                    marker, meaning = {"one-token": ("*", "one-sided"), "one-quote": ("*", "one-sided"),
                                       "withdrawn": ("!", "withdrawn"), "unknown": ("?", "unknown")}.get(state, ("", ""))
                    if marker:
                        markers[marker] = (meaning, _lp_color(state))
                    result += Text() + _cell(marker, 2, _lp_color(state)) + _cell(name, 11) + _cell(_change(item.get("change_24h")), 8,
                        _change_color(item.get("change_24h")), right=True)
                else:
                    result += _cell("unavailable" if entries is None and index == 0 else "none" if index == 0 else "", 21, "dim white")
                if not side:
                    result += Text(" ")
            result += Text("\n")
        result += Text("  ").join(Text(f"{marker} {meaning}", style=color)
                                  for marker, (meaning, color) in markers.items())
        self.write("#st-best-body", result)


class TokenActivity(_CompactFeed):
    TITLE = "ACTIVITY"
    LOG_ID = "st-activity-log"
    EMPTY_LINE = Text("No matching activity", style="dim white")

    def update_data(self, activity=None, tokens=None):
        self._tokens = {row["id"]: row for row in (tokens or []) if isinstance(row, dict)}
        self.render_events(activity)

    def format_row(self, event):
        token = self._tokens.get(event.get("token_id"), {})
        kind = flatten(event.get("kind", "--")).upper()
        color = {"BUY": "green", "SELL": "red", "LAUNCH": "yellow"}.get(kind, "")
        amount = _quantity(event.get("amount"))
        amount = amount if amount == "--" else f"{amount} {flatten(event.get('asset'))}"
        return (Text() + _cell(hhmm(event.get("ts")), 6, "dim") + _cell(kind, 8, color) +
                _cell(flatten(token.get("chain", "--")).upper(), 5) +
                _cell(token.get("symbol", "--"), 8) + _cell(amount, 13))
