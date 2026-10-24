"""The fixed four-row equipment rack; widgets publish navigation intent only."""
from __future__ import annotations

import math

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.color import Color
from textual.constants import DIM_FACTOR
from textual.containers import Grid
from textual.message import Message
from textual.renderables.digits import Digits
from textual.widgets import Input, Static

from maxpane_dashboard.analytics.surfboard import SURFBOARD_AGENT_KEYS as AGENT_KEYS
from maxpane_dashboard.widgets.address import is_copy_click, is_explorer_click
from maxpane_dashboard.widgets.card_inner import LoadingCard, inner_styles, loading_fraction, padded_inner_row
from maxpane_dashboard.widgets.explorer import for_network
from maxpane_dashboard.widgets.fmt import fmt_age, worked_duration
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from maxpane_dashboard.widgets.sparkline_common import build_sparkline, fmt_compact

GREEN = "green"
MUTED = "dim"
AMBER = "yellow"
RED = "red"

# Fixed rack identities; the four agent cards carry independent assignments.
SLOTS = (
    ("announce", "ONCHAIN FEED", 0, 0), ("swarm", "BUILT BY SWARM", 0, 1),
    ("work", "WIP", 0, 2), ("oracles", "ORACLES", 0, 3),
    ("pool4", "POOL4", 0, 4), ("board", "FLEET", 0, 5),
    ("surf-nft", "NFTS", 1, 0), ("swarm-tokens", "TOKENS", 1, 5),
    ("agent", "AGENT", 2, 0), ("agent-2", "AGENT", 2, 5),
    ("agent-3", "AGENT", 3, 0), ("agent-4", "AGENT", 3, 5),
)
METER_LABELS = {"swarm": "24H", "swarm-tokens": "24h", "launchpad": "2H"}


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _token_line(row, width, style, value_style):
    """Fit age and literal ticker while preserving address copy/link units."""
    age = fmt_age(row.get('age_s')) if _number(row.get('age_s')) else '—'
    chain = flatten(row.get('chain')).upper()
    symbol, lost = fit_prose(row.get('symbol') or '—', max(0, width-4),
                             style=value_style if row.get('symbol') else style,
                             explorer=for_network('MAINNET' if chain == 'ETH' else chain))
    line = Text(clip(clip(age, 3).ljust(3) + ' ', width), style=style).append_text(symbol)
    return line, lost or cell_len(age) > 3


def _price_indicator(direction):
    return {'up': ('↑', GREEN), 'down': ('↓', RED)}.get(direction, ('', ''))


def _token_preview(rows, width, style, value_style, render_value=None):
    """Three ranked rows; the data layer owns ordering and price comparison."""
    lines = [(Text('', style=style), False) for _ in range(3)]
    if not rows:
        line, lost = fit_prose('—' if rows is None else 'no launches', max(0, width-2), style=style)
        if render_value is not None:
            line = render_value(line)
        lines[1] = padded_inner_row(line, width), lost
        return lines
    for index, row in enumerate(rows[:3]):
        marker, ink = _price_indicator(row.get('price_direction'))
        line, lost = _token_line(row, max(0, width-4), style, value_style)
        line.align('left', max(0, width-4))
        line.append(' ').append(marker or ' ', style=ink or style)
        lines[index] = padded_inner_row(line, width), lost
    return lines


def _fleet_preview(summary, width, style, value_style, render_value=None):
    """Three fixed rows, with only observed values in the leaderboard ink."""
    values = []
    for key in ('tokens', 'jobs', 'capacity'):
        value = summary.get(key)
        values.append((fmt_compact(value) if key == 'tokens' else f'{value:,}')
                      if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else '—')
    lines = []
    for label, value in zip(('tokens', 'jobs', 'capacity'), values):
        if label == 'tokens' and cell_len(label) + cell_len(value) + 3 > width:
            value = f"{summary['tokens']:.2e}"
        if label == 'capacity' and cell_len(label) + cell_len(value) + 3 > width:
            label = 'cap.'
        prefix = label + ' '
        available = max(0, width - 2 - cell_len(prefix))
        fitted, lost = fit_prose(value, available, style=value_style if value != '—' else style)
        if render_value is not None:
            fitted = render_value(fitted)
        fitted.align('right', available)
        line = Text(clip(prefix, max(0, width-2)), style=style).append_text(fitted)
        lines.append((padded_inner_row(line, width), lost or cell_len(prefix) + 3 > width))
    return lines


def _fleet_accept_rate(summary):
    rate = summary.get('accept_rate')
    return f'{rate:.2f}%' if _number(rate) and rate <= 100 else '—'


def _protocol_footer(card, width):
    share = flatten(card.get('secondary'))
    text = share.removesuffix(' of supply') + ' burned' if share.endswith('% of supply') else '—'
    return fit_prose(text, width, style=MUTED)


def _work_footer(card, width):
    value = (card.get("work_summary") or {}).get("workflows")
    count = f"{int(value):,}" if _number(value) and value == int(value) else "—"
    return fit_prose(LoadingCard.count_caption(Text(f"{count} workflows")).plain, width, style=MUTED)


def _fleet_footer(card, width):
    ms = card.get('numerator') if card.get('meter_kind') == 'duration' else None
    return fit_prose(worked_duration(ms), width, style=MUTED)


def meter_text(card: dict, width: int | None = None) -> Text:
    """Width-fitted meters and history; missing values never imply zero."""
    key, status = card.get("key"), card.get("status")
    state = card.get("meter_state")
    if key == "surf-nft":
        summary = card.get("nft_summary") or {}
        shown = lambda value: str(int(value)) if _number(value) and value == int(value) else "—"
        building, opened = (shown(summary.get(name)) for name in ("building", "mint_open"))
        width = 24 if width is None else width
        text = LoadingCard.count_caption(Text(f"{building} build · {opened} open")).plain
        if cell_len(text) > width:
            text = LoadingCard.count_caption(Text(f"{building}bld · {opened}open")).plain
        return fit_prose(text, width, style=MUTED)[0]
    if key == "protocol":
        return _protocol_footer(card, 24 if width is None else width)[0]
    if key == "oracles":
        count = card.get("numerator")
        value = f"{int(count):,}" if _number(count) and count == int(count) else "—"
        return fit_prose(LoadingCard.count_caption(Text(f"{value} chains")).plain, 24 if width is None else width, style=MUTED)[0]
    if key == "work":
        return _work_footer(card, 24 if width is None else width)[0]
    if key == "board":
        return _fleet_footer(card, 24 if width is None else width)[0]
    if key in AGENT_KEYS and state == "empty":
        return Text("Identity.md", style=MUTED)
    if key == "pool4":
        price = card.get("share_price")
        value = "1 sIMD = — IMD"
        if _number(price):
            for decimals in range(6, -1, -1):
                candidate = f"1 sIMD = {price:,.{decimals}f} IMD"
                if width is None or cell_len(candidate) <= width:
                    value = candidate
                    break
        return Text(value, style=MUTED)
    if key == "swarm-tokens":
        value = card.get("numerator")
        amount = ("≥" if state == "partial" else "") + "$" + (fmt_compact(value) if value >= 1000 else f"{value:.2f}") if _number(value) else "—"
        return Text("24h " + amount, style=MUTED)
    label = METER_LABELS.get(key, "AUX")
    label_ink = MUTED
    if key in (*AGENT_KEYS, "board"):
        label = {"busy": "BUSY", "idle": "IDLE", "offline": "OFF", "empty": "EMPTY"}.get(state, "—")
        label_ink = MUTED if state in ("idle", "empty") else RED if state == "offline" else AMBER
    elif key == "launchpad" and state == "partial":
        label = "~" + label
        label_ink = AMBER
    out = Text().append(label + " ", style=label_ink)
    cells = 8 if width is None else max(0, width - cell_len(label) - 1)
    if state == "empty":
        return out.append("▱" * cells, style=MUTED)
    if card.get("meter_kind") == "sparkline" or key in ("launchpad", "swarm-tokens"):
        points = card.get("points")
        if (isinstance(points, list) and len(points) == 8
                and (all(_number(point) for point in points) or key in ("launchpad", "swarm-tokens")
                     and any(_number(point) for point in points)
                     and all(point is None or _number(point) for point in points))):
            known = [point for point in points if _number(point)]
            glyphs = iter(build_sparkline(known, width=len(known), pad=False))
            chart = "".join(next(glyphs) if _number(point) else "·" for point in points)
            if width is not None:
                # Stretch each existing time bucket; do not invent more samples.
                chart = "".join(chart[column * len(chart) // cells] for column in range(cells))
            return out.append(chart, style=GREEN)
        return out.append("—", style=AMBER)
    numerator, denominator = card.get("numerator"), card.get("denominator")
    if key in (*AGENT_KEYS, "board"):
        if state == "offline":
            return out.append("▱" * cells, style=MUTED)
        if state == "busy":
            return out.append("▰" * cells, style=GREEN)
        if state != "idle":
            return out.append("—", style=AMBER)
    if not _number(numerator) or not _number(denominator) or denominator == 0 or numerator > denominator:
        return out.append("—", style=AMBER)
    full = int(numerator * cells / denominator)
    if card.get("meter_kind") == "activity":
        # Quantization must not imply a full day idle before 24h has elapsed.
        if numerator > 0 and cells:
            full = max(1, full)
        return out.append("▰" * full, style=GREEN).append("▰" * (cells - full), style=AMBER)
    if card.get("meter_kind") == "activity-cooldown":
        return out.append("▰" * full, style=AMBER).append("▱" * (cells - full), style=MUTED)
    return out.append("▰" * full, style=AMBER if key == "protocol" else GREEN).append("▱" * (cells - full), style=MUTED)


def signal_meter_text(card: dict, width: int) -> Text:
    """One lit cell per signal; the rest of the footer is an empty track."""
    count, total = card.get("numerator"), card.get("denominator")
    if (not _number(count) or not _number(total) or total == 0
            or count > total or count != int(count) or total != int(total)):
        return Text("— SIGNALS", style=MUTED)
    full = int(count)
    label = f"{full} SIGNALS"
    cells = max(0, width - len(label) - 1)
    if not full or full > cells:
        return Text(label, style=MUTED)
    return (Text().append(label + " ", style=MUTED).append("▰" * full, style=GREEN)
            .append("▱" * (cells - full), style=MUTED))


# Surf's agent rack imports meter_text while terminal loads the Surf icon helpers.
from .terminal import SurfboardTerminal, fit_prose


class SurfboardCard(LoadingCard, can_focus=True):
    """A focusable faceplate with an inset readout."""
    DEFAULT_CSS = "SurfboardCard { link-color: $foreground; }"
    BINDINGS = [Binding("enter", "activate", "Open", show=False)]
    COMPONENT_CLASSES = {"surfboard-card--muted"}

    class Activated(Message):
        def __init__(self, card):
            super().__init__()
            self.card = card

    class Focused(Message):
        def __init__(self, card):
            super().__init__()
            self.card = card

    def __init__(self, key, title, row, column):
        super().__init__(id=f"surfboard-card-{key}")
        self.key, self.title, self.rack_row, self.rack_column = key, title, row, column
        self.seat_slot = AGENT_KEYS.index(key) if key in AGENT_KEYS else None
        self.data = {}
        self._price_direction = None
        self._seat_error = ""
        self.set_data(None)

    @property
    def empty_seat(self):
        return self.seat_slot is not None and self.data.get("token_id") is None

    def _can_load_card(self):
        return not self.empty_seat and self.data.get('status') in (
            None, 'loading', 'active', 'idle', 'working', 'ready', 'assessing', 'falling')

    def set_card_loading(self, busy, frame):
        previous = self._card_loading, self._card_loading_frame
        super().set_card_loading(busy, frame)
        if previous != (self._card_loading, self._card_loading_frame) and self._footer_has_missing_value:
            self._update_meter()

    def compose(self):
        if self.seat_slot is not None:
            yield Input(placeholder="seat number", restrict=r"#?[0-9]*", max_length=11,
                        id=f"surfboard-seat-{self.seat_slot}", classes="seat-input", compact=True)

    def on_mount(self):
        self._update_input()

    def _update_input(self):
        for field in self.query(Input):
            if not self.empty_seat and field.has_focus:
                self.focus()
            field.display = self.empty_seat
            width = min(11, max(3, self.content_size.width - 4))
            field.styles.width = width
            field.styles.offset = (max(1, (self.content_size.width - width) // 2),
                                   max(0, (self.content_size.height - 5) // 2) + 2)

    @property
    def detail(self):
        return flatten(self.data.get("detail")) or self.title

    def set_data(self, data, *, footer_data=None):
        self.data = dict(data) if isinstance(data, dict) else {}
        self.data.update(key=self.key, title=self.title)
        if self.key == 'pool4' and self.data.get('status') != 'loading':
            self._price_direction = {'active': 'up', 'falling': 'down'}.get(self.data.get('status'))
        if self.seat_slot is not None:
            self.data["seat_slot"] = self.seat_slot
            self.data.setdefault("token_id", None)
        if self.key == "surf-nft":
            self.data["destination"] = "surf-nft"
            self.data.setdefault("detail", "NFTS · observed collections · Enter to open")
        if self.key == "swarm-tokens":
            self.data["destination"] = "swarm-tokens"
            self.data.setdefault("detail", "TOKENS · production-chain markets · Enter to open")
            self.tooltip = Text(self.detail)
        if self.key == "oracles":
            self.data["destination"] = "oracles"
            self.data.setdefault("primary", "—")
            self.data.setdefault("secondary", "— agents")
            self.data.setdefault("detail", "ORACLES · Enter to open")
            self.tooltip = Text(self.detail)
        if self.key == "board":
            self.data["destination"] = "board"
        if self.key == "work":
            self.data["destination"] = "work"
            self.data.setdefault("primary", "—")
            self.data.setdefault("secondary", "—")
            self.data.setdefault("detail", "WORK IN PROGRESS · Enter to open")
            self.tooltip = Text(self.detail)
        if self.empty_seat:
            self.data.update(status="empty", primary="", secondary="type in", destination=None,
                             meter_state="empty", detail="AGENT · empty seat · Enter to type a seat number")
        else:
            self._seat_error = ""
        self.footer_data = dict(footer_data) if isinstance(footer_data, dict) else self.data
        self.tooltip = Text(self.detail)
        if self.key == "board":
            summary = self.data.get("fleet_summary") or {}
            model = flatten(summary.get("model"))
            effort = flatten(summary.get("effort"))
            self.tooltip.append("\nModel: " + (" ".join(filter(None, (model, effort))) if model else "—"))
            self.tooltip.append("\nDaemon: " + (flatten(summary.get("daemon")) or "—"))
        if self.footer_data.get("key") != self.key and self.footer_data.get("detail"):
            self.tooltip.append("\nFooter: " + flatten(self.footer_data["detail"]))
        self.set_class(self.empty_seat, "empty")
        self._update_title()
        self._update_meter()
        self._update_input()
        self.refresh()

    def _update_meter(self):
        self.styles.border_subtitle_align = "center"
        self._footer_has_missing_value = False
        if self.footer_data.get("status") == "loading" and self.footer_data.get("key") not in ('work', 'oracles', 'surf-nft', 'announce'):
            self.border_subtitle = Text("◌ loading", style=AMBER)
        elif self.key == "announce":
            # Textual reserves six cells for corners, border stubs and padding.
            self.border_subtitle = self.count_caption(signal_meter_text(self.data, max(0, self.region.width - 6)))
        else:
            footer = self.count_caption(meter_text(self.footer_data, max(0, self.region.width - 6)))
            if self.footer_data.get('key') in ('work', 'oracles', 'surf-nft', 'pool4', 'swarm-tokens', 'board'):
                self._footer_has_missing_value = '—' in footer.plain
                footer = self.loading_caption(footer)
            self.border_subtitle = footer

    def on_resize(self):
        self._update_meter()
        self._update_input()

    def _update_title(self, clipped=False):
        available = max(0, self.region.width - 6)
        numbered = self.seat_slot is not None and available >= 5
        title = Text(title_with_hint("⊙ " + self.title, clipped, max(0, available - 5) if numbered else max(0, self.size.width - 4)))
        if numbered:
            title.append(" " + "─" * max(0, available - title.cell_len - 5) + " ",
                         style=Style(color=self.styles.border_top[1].rich_color))
            title.append(f"'{self.seat_slot + 1}'", style=Style(dim=True, meta={"seat_edit": self.seat_slot}))
        self.border_title = title

    def render(self):
        self._has_missing_value = False
        width = max(4, self.content_size.width)
        inside = width - 2
        status = flatten(self.data.get("status")) or "unavailable"
        muted = self.empty_seat
        color = MUTED if muted else {"active": GREEN, "working": GREEN, "ready": "bright_yellow",
            "stale": AMBER, "unavailable": AMBER, "paused": AMBER,
            "offline": RED, "error": RED, "failed": RED}.get(status, AMBER)
        primary = flatten(self.data.get("primary")) or "—"
        secondary = flatten(self.data.get("secondary"))
        if self.key != "announce" and primary == "unavailable":
            primary = "—"
        if secondary == "unavailable":
            secondary = ""
        ranking = self.data.get("token_ranking") or {}
        if self.key == "swarm-tokens" and ranking.get("state", "unavailable") != "ok":
            color = AMBER
        working = secondary.removesuffix(" working").replace(",", "")
        if (self.key == "swarm" and secondary.endswith(" working")
                and working.isascii() and working.isdecimal() and working.strip("0")):
            color = GREEN
        elif self.key == "swarm" and status == "active":
            color = AMBER
        if self.seat_slot is not None:
            if status == "active":
                color = AMBER
            secondary = (secondary or "offline") if status == "offline" else secondary.removesuffix(" slots")
        if self.key == "announce":
            secondary = secondary.removesuffix(" replies").removesuffix(" reply")
        elif self.key == "protocol":
            secondary = secondary.removesuffix(" of supply")
        if status in ("offline", "error", "failed") and not muted:
            color = RED
        palette = self.app.get_css_variables()
        inset = Style.parse(palette["accent"] if color == GREEN else color) + Style(bgcolor=palette["background"])
        border_inset = (Style.parse(MUTED) + Style(bgcolor=palette["background"])
                        if color == AMBER else inset)
        if self.key in ("protocol", "surf-nft", "board", "pool4"):
            border_inset = Style.parse(MUTED) + Style(bgcolor=palette["background"])
        elif self.key == "work":
            jobs = primary.replace(",", "")
            active = jobs.isascii() and jobs.isdecimal() and jobs.strip("0")
            border_inset = Style.parse(palette["accent"] if active else MUTED) + Style(bgcolor=palette["background"])
        elif self.key == "announce" and status == "active":
            border_inset = Style(color=self.rich_style.color, bgcolor=palette["background"])
        elif self.key == "oracles" and status == "assessing":
            border_inset = Style.parse(palette["accent"]) + Style(bgcolor=palette["background"])
        label_style, value_style, readout_style = inner_styles(
            palette, active=border_inset.color in (Style.parse(palette['accent']).color, Style.parse(GREEN).color),
            frame_color=border_inset.color, ansi_theme=self.app.ansi_theme, text_color=self.rich_style.color)
        label = ""
        marker, marker_ink = _price_indicator(self._price_direction)
        marker_width = 0
        native_digits = False
        numeric_readout = False
        rows = [("", False), (primary, not muted), (secondary, False)]
        if self.key in ("swarm", "launchpad", "oracles", "pool4", "work", "surf-nft") or self.seat_slot is not None:
            label = " SEAT " if self.seat_slot is not None else {"swarm": " AGENTS ",
                     "launchpad": " COINS ", "oracles": " JOBS ",
                     "pool4": " IMD PRICE ", "work": " JOBS ", "surf-nft": " COLLECTIONS "}[self.key]
            count = primary.removesuffix(" online") if self.key == "swarm" else primary.removeprefix("IDMD #")
            digits = count.replace(",", "")
            if self.key == "pool4":
                digits = digits.replace(".", "", 1)
            readout = count if self.key == "pool4" else digits
            # Use the same native 3x3 renderer as Textual's Digits widget.
            numeric_readout = digits.isascii() and digits.isdecimal()
            marker_width = 2 if marker and numeric_readout else 0
            native_digits = numeric_readout and Digits.get_width(readout) <= inside - marker_width
            if native_digits:
                rows = [(segment.text, False) for segment in Digits(readout).render(Style())
                        if segment.text != "\n"]
            else:
                rows = [("", False), (count, False), ("", False)]
        if self.empty_seat:
            label, rows = " EMPTY SEAT ", [("", False), ("", False), ("↑", False)]
            secondary = self._seat_error or secondary
        preview = None
        if self.key == "protocol":
            label = " STATS "
            stats = str(self.data.get("primary") or "").splitlines()
            if len(stats) != 3:
                stats = [f"★ {name} — IMD" for name in ("burned", "rewarded", "fees")]
            fields = [flatten(line).removeprefix("★ ").split() for line in stats]
            available = max(0, inside - 2)
            fields = [('rewards' if row[0] == 'rewarded' and sum(map(cell_len, row)) + 1 > available
                       else row[0], *row[1:]) if len(row) == 3 else row for row in fields]
            label_width = max((cell_len(row[0]) for row in fields if len(row) == 3), default=8)
            amount_width = max((cell_len(row[1]) for row in fields if len(row) == 3), default=1)
            unit_gap = " " if label_width + amount_width + 5 <= available else ""
            preview = []
            for parts in fields:
                name, amount, unit = parts if len(parts) == 3 else ("—", "—", "IMD")
                row = f"{name.ljust(label_width)} {amount.ljust(amount_width)}{unit_gap}{unit}"
                if cell_len(row) > available:
                    row = f"{name} {amount}{unit_gap}{unit}"
                line = Text(clip(row, available), style=label_style)
                if amount != '—':
                    line.stylize(value_style, row.index(amount, len(name)))
                else:
                    rendered = self.loading_value(Text(amount, style=label_style))
                    offset = line.plain.find(amount, len(name))
                    if offset >= 0:
                        line = line[:offset] + rendered + line[offset + len(amount):]
                preview.append((padded_inner_row(line, inside), cell_len(row) > available))
        elif self.key == "announce":
            from maxpane_dashboard.widgets.surf._icons import post_preview as _post_preview
            label = " LATEST "
            prose_style = Style(color=self.rich_style.color, bgcolor=palette["background"], dim=False)
            preview = [(padded_inner_row(line, inside), False)
                       for line in _post_preview(primary, max(0, inside-2), prose_style)]
        elif self.key == "board":
            summary = self.data.get("fleet_summary") or {}
            label, secondary = " STATS ", _fleet_accept_rate(summary)
            preview = _fleet_preview(summary, inside, label_style, value_style, self.loading_value)
        elif self.key == "swarm-tokens":
            label = " LATEST "
            preview = _token_preview(ranking.get("latest"), inside,
                                     label_style, value_style, self.loading_value)
        if preview is None and not native_digits and not self.empty_seat:
            block = self.loading_block(Text(rows[1][0], style=label_style), max(0, inside-2))
            if block is not None:
                preview = [(padded_inner_row(row, inside, align='center'), False) for row in block]
        body = Text()
        body.append("┌" + clip(label, inside).center(inside, "─") + "┐\n", style=border_inset)
        if label and (start := body.plain.find(label.strip())) >= 0:
            body.stylize(Style(bold=False), start, start + len(label.strip()))
        count_label = {'work': 'working', 'oracles': 'agents', 'surf-nft': 'building'}.get(self.key)
        if count_label and secondary.strip() in ('-', '--', '—'):
            secondary += ' ' + count_label
        bottom = f" {self.count_caption(Text(secondary)).plain} " if label else ""
        if self.key == "protocol":
            bottom = ""
        if self.key in ("announce", "swarm-tokens") and secondary == "0 new":
            bottom = ""
        if cell_len(bottom) > inside:
            bottom = bottom.strip()
        if self.seat_slot is not None and len(bottom) > inside:
            bottom = bottom.replace(" of ", "/")
        if self.key == "announce" and len(bottom) > inside:
            bottom = bottom.replace(",", "")
            if len(bottom) > inside:
                bottom = bottom.replace(" new ", " ")
        clipped = cell_len(label) > inside or cell_len(bottom) > inside
        if self.key == "protocol":
            clipped |= _protocol_footer(self.data, max(0, self.region.width - 6))[1]
        if self.footer_data.get("key") == "work":
            clipped |= _work_footer(self.footer_data, max(0, self.region.width - 6))[1]
        if self.key == "board":
            clipped |= _fleet_footer(self.data, max(0, self.region.width - 6))[1]
        for index, (raw, bold) in enumerate(rows):
            style = (readout_style if numeric_readout or self.key == 'pool4' else label_style) + Style(bold=bold)
            if self.empty_seat:
                style += Style(color=GREEN)
            line, lost = (preview[index] if preview is not None else
                          (Text(raw, style=style), False) if native_digits else fit_prose(raw, max(0, inside-2-marker_width), style=style))
            if marker_width:
                line.append(' ').append(marker if index == 1 else ' ', style=marker_ink)
            clipped |= lost
            if preview is None and not native_digits:
                if not self.empty_seat:
                    line = self.loading_value(line)
                line = padded_inner_row(line, inside, align='center')
            line.align("left" if preview is not None else "center", inside)
            if marker_width and index == 1:
                arrow_at = line.plain.index(marker)
                if arrow_at + 1 < len(line):
                    # Move into the next padding cell without shifting the price.
                    line = line[:arrow_at] + Text(' ', style=style) + line[arrow_at:arrow_at+1] + line[arrow_at+2:]
            body.append("│", style=border_inset).append_text(line).append("│\n", style=border_inset)
        self._update_title(clipped)
        fitted_bottom = clip(bottom, inside)
        footer = Text("└" + fitted_bottom.center(inside + len(fitted_bottom) - cell_len(fitted_bottom), "─") + "┘",
                      style=border_inset + Style(bold=False))
        if not self.empty_seat:
            caption = Text(fitted_bottom.strip(), style=border_inset)
            rendered = (self.loading_caption(caption)
                        if self.key in ('work', 'oracles', 'swarm', 'surf-nft', 'pool4', 'swarm-tokens', 'board', 'launchpad')
                        else self.loading_value(caption))
            if rendered.plain != caption.plain:
                offset = footer.plain.index(fitted_bottom.strip())
                count = len(fitted_bottom.strip())
                footer = footer[:offset] + rendered + Text(' ' * (count - len(rendered)), style=border_inset) + footer[offset + count:]
        if self.empty_seat and self._seat_error:
            footer.stylize(Style(color=RED, dim=False), 1, len(footer) - 1)
        return body.append_text(footer)

    def on_focus(self):
        self.post_message(self.Focused(self))

    def on_descendant_focus(self):
        self.post_message(self.Focused(self))

    def action_activate(self):
        if self.empty_seat:
            self.query_one(Input).focus()
        elif self.can_focus:
            self.post_message(self.Activated(self))

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        if self.empty_seat:
            self.post_message(SurfboardRack.SeatSubmitted(self.seat_slot, event.value))

    def on_input_changed(self, event: Input.Changed):
        if self._seat_error:
            self._seat_error = ""
            self.refresh()

    def on_click(self, event):
        if self.seat_slot is not None and event.style.meta.get("seat_edit") == self.seat_slot:
            event.stop()
            self.focus()
            self.post_message(SurfboardRack.SeatEditRequested(self.seat_slot))
            return
        if is_copy_click(event) or is_explorer_click(event):
            return
        if isinstance(event.widget, Input):
            return
        if self.can_focus:
            self.focus()
            self.action_activate()


class SurfboardRack(Grid):
    """Own fixed slots and terminal children; the screen dispatches to both."""
    DEFAULT_CSS = """
    SurfboardRack { layout: grid; grid-size: 6 4; grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr 1fr; grid-gutter: 1 1; height: 1fr; min-height: 33; min-width: 143; }
    SurfboardRack > SurfboardCard { height: 1fr; min-height: 7; padding: 0 1;
        border: round $panel; background: $surface; color: $text; content-align: center middle;
        border-title-color: $text-muted; border-subtitle-color: $text-muted; border-subtitle-align: left; }
    SurfboardRack > SurfboardCard:focus { border: round $accent; }
    SurfboardRack > SurfboardCard.empty { color: $text-muted; }
    SurfboardCard .surfboard-card--muted { color: $text-muted; background: $background; }
    SurfboardCard > Input.seat-input { position: absolute; height: 1; margin: 0; padding: 0;
        border: none; background: $surface; color: $foreground; }
    SurfboardRack > SurfboardTerminal { column-span: 4; row-span: 3; }
    SurfboardRack > .rack-tagline { dock: top; height: 1; color: $text-muted; text-style: none;
        content-align: center middle; }
    SurfboardRack > #surfboard-keep { layer: keep; }
    SurfboardRack > #surfboard-building { layer: building; }
    """

    class CardActivated(Message):
        def __init__(self, key, destination, detail, seat_slot=None, token_id=None):
            super().__init__()
            self.key, self.destination, self.detail = key, destination, detail
            self.seat_slot, self.token_id = seat_slot, token_id

    class SeatSubmitted(Message):
        def __init__(self, seat_slot, value):
            super().__init__()
            self.seat_slot, self.value = seat_slot, value

    class SeatEditRequested(Message):
        def __init__(self, seat_slot):
            super().__init__()
            self.seat_slot = seat_slot

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.focused_card = "announce"
        self._loading_busy = False
        self._loading_frame = 0

    def on_resize(self):
        # Fractional tracks distribute spare lines unevenly between cards.
        rows = self.styles.grid_size_rows
        gaps = (rows - 1) * self.styles.grid_gutter_vertical
        # Reserve two extra side-column lines below TOKENS and PROTOCOL.
        card_height = max(7, (self.content_size.height - gaps - 2) // rows)
        self.query(SurfboardCard).set_styles(height=card_height)
        # The terminal spans the last track and can use its leftover space.
        self.styles.grid_rows = (card_height, card_height + 2, card_height, "1fr")
        self.call_after_refresh(self._position_taglines)
        # Wait for the track changes to reach the children's regions.
        self.call_after_refresh(self.call_after_refresh, self._position_taglines)

    def _position_taglines(self):
        for key, label_id in (("surf-nft", "keep"), ("swarm-tokens", "building")):
            card = self.query_one(f"#surfboard-card-{key}", SurfboardCard)
            label = self.query_one(f"#surfboard-{label_id}", Static)
            label.styles.width = card.region.width
            label.styles.offset = (card.region.x - self.content_region.x,
                card.region.bottom - self.content_region.y + 1)
        self.set_loading_animation(self._loading_busy, self._loading_frame)

    def set_loading_animation(self, busy: bool, frame: int):
        """Fade both captions on the footer clock; restore their original idle ink."""
        self._loading_busy, self._loading_frame = busy, frame
        palette = self.app.get_css_variables()
        for label in self.query('.rack-tagline'):
            base, surface = label.background_colors
            idle = (base + surface).blend(Color.parse(palette['foreground']), DIM_FACTOR)
            label.styles.auto_color = False
            label.styles.color = idle.blend(Color.parse(palette['accent']),
                                            loading_fraction(frame) if busy else 0)

    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield SurfboardCard(*slot)
            if index == 6:
                yield SurfboardTerminal(id="surfboard-terminal")
        yield Static(Text("キープ"), id="surfboard-keep", classes="rack-tagline")
        yield Static(Text("ビルディング"), id="surfboard-building", classes="rack-tagline")

    def update_data(self, surfboard_cards=None, surfboard_sources=None, **_kwargs):
        cards = {card["key"]: card for card in surfboard_cards if isinstance(card, dict) and isinstance(card.get("key"), str)} if isinstance(surfboard_cards, list) else {}
        for card in self.query(SurfboardCard):
            card.set_data(cards.get(card.key))

    def focus_card(self, key=None):
        key = key or self.focused_card
        for card in self.query(SurfboardCard):
            if card.key == key and card.can_focus:
                self.focused_card = key
                card.focus()
                return

    def set_seat_error(self, slot, message):
        card = self.query_one(f"#surfboard-card-{AGENT_KEYS[slot]}", SurfboardCard)
        card._seat_error = flatten(message)
        card.refresh()

    def move_focus(self, direction):
        cards = [card for card in self.query(SurfboardCard) if card.can_focus]
        current = next((card for card in cards if card.key == self.focused_card), cards[0])
        dr, dc = {"left": (0, -1), "right": (0, 1), "up": (-1, 0), "down": (1, 0)}.get(direction, (0, 0))
        candidates = [card for card in cards if ((card.rack_row - current.rack_row) * dr > 0 if dr else
                      card.rack_row == current.rack_row and (card.rack_column - current.rack_column) * dc > 0)]
        if candidates:
            target = min(candidates, key=lambda card: (abs(card.rack_row-current.rack_row), abs(card.rack_column-current.rack_column)))
            self.focus_card(target.key)

    def activate_focused(self):
        for card in self.query(SurfboardCard):
            if card.key == self.focused_card:
                card.action_activate()

    def on_surfboard_card_focused(self, event):
        event.stop()
        self.focused_card = event.card.key

    def on_surfboard_card_activated(self, event):
        event.stop()
        self.post_message(self.CardActivated(event.card.key, event.card.data.get("destination"), event.card.detail,
                                            event.card.seat_slot, event.card.data.get("token_id")))
