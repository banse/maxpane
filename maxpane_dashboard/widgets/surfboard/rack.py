"""The fixed four-row equipment rack; widgets publish navigation intent only."""
from __future__ import annotations

import math

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.containers import Grid
from textual.message import Message
from textual.renderables.digits import Digits
from textual.widgets import Input

from maxpane_dashboard.analytics.surfboard import SURFBOARD_AGENT_KEYS as AGENT_KEYS
from maxpane_dashboard.widgets.address import is_copy_click, is_explorer_click
from maxpane_dashboard.widgets.explorer import for_network
from maxpane_dashboard.widgets.fmt import fmt_age, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import HeroBoxBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from maxpane_dashboard.widgets.sparkline_common import build_sparkline, fmt_compact

GREEN = "green"
MUTED = "dim"
AMBER = "yellow"
RED = "red"

# Fixed rack identities; the four agent cards carry independent assignments.
SLOTS = (
    ("announce", "ONCHAIN NEWS", 0, 0), ("swarm", "SWARM", 0, 1),
    ("swarm-tokens", "TOKENS", 0, 2), ("pool4", "POOL4", 0, 3),
    ("protocol", "PROTOCOL", 0, 4), ("board", "LEADERBOARD", 0, 5),
    ("launchpad", "LAUNCHPAD", 1, 0), ("portfolio", "PORTFOLIO", 1, 5),
    ("agent", "AGENT", 2, 0), ("agent-2", "AGENT", 2, 5),
    ("agent-3", "AGENT", 3, 0), ("agent-4", "AGENT", 3, 5),
)
METER_LABELS = dict(swarm="24H", launchpad="2H", protocol="BURN", portfolio="ASSETS")


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _token_line(row, width, style):
    """Fit age and literal ticker while preserving address copy/link units."""
    age = fmt_age(row.get('age_s')) if _number(row.get('age_s')) else '—'
    chain = flatten(row.get('chain')).upper()
    symbol, lost = fit_prose(row.get('symbol') or '—', max(0, width-4), style=style,
                             explorer=for_network('MAINNET' if chain == 'ETH' else chain))
    line = Text(clip(clip(age, 3).ljust(3) + ' ', width), style=style).append_text(symbol)
    return line, lost or cell_len(age) > 3


def _newest_token(ranking, width):
    newest = ranking.get('newest')
    if isinstance(newest, dict):
        return _token_line(newest, width, MUTED)
    empty = ranking.get('rows') == [] and ranking.get('state') == 'ok'
    return fit_prose('no launches' if empty else 'unavailable', width, style=MUTED)


def _token_preview(rows, width, style):
    """Three ranked rows; the data layer owns ordering and price comparison."""
    lines = [(Text('', style=style), False) for _ in range(3)]
    if not rows:
        lines[1] = fit_prose('unavailable' if rows is None else 'no launches', width, style=style)
        return lines
    for index, row in enumerate(rows[:3]):
        marker, ink = {'up': ('▲', Style.parse(GREEN)), 'down': ('▼', Style.parse(RED))}.get(
            row.get('price_direction'), ('—', style))
        line, lost = _token_line(row, max(0, width-2), style)
        line.align('left', max(0, width-2))
        line.append(' ').append(marker, style=ink)
        lines[index] = line, lost
    return lines


def meter_text(card: dict, width: int | None = None) -> Text:
    """Width-fitted meters and history; missing values never imply zero."""
    key, status = card.get("key"), card.get("status")
    state = card.get("meter_state")
    if key == "swarm-tokens":
        return _newest_token(card.get("token_ranking") or {}, 20 if width is None else width)[0]
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
    label = METER_LABELS.get(key, "AUX")
    label_ink = MUTED
    if key in (*AGENT_KEYS, "board"):
        label = {"busy": "BUSY", "idle": "IDLE", "offline": "OFF", "empty": "EMPTY"}.get(state, "—")
        label_ink = MUTED if state in ("idle", "empty") else RED if state == "offline" else AMBER
    elif key == "launchpad" and state in ("partial", "stale"):
        label = "~" + label
        label_ink = AMBER
    out = Text().append(label + " ", style=label_ink)
    cells = 8 if width is None else max(0, width - cell_len(label) - 1)
    if key == "portfolio" or state == "empty":
        return out.append("▱" * cells, style=MUTED)
    if card.get("meter_kind") == "sparkline" or key == "launchpad":
        points = card.get("points")
        if (isinstance(points, list) and len(points) == 8
                and (all(_number(point) for point in points) or key == "launchpad"
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
        if numerator is None and card.get("meter_kind") == "activity":
            # Keep the track visible before the first observed work-to-idle transition.
            return out.append("▰" * cells, style=AMBER)
    if not _number(numerator) or not _number(denominator) or denominator == 0 or numerator > denominator:
        return out.append("—", style=AMBER)
    full = int(numerator * cells / denominator)
    if card.get("meter_kind") == "activity":
        return out.append("▰" * full, style=GREEN).append("▰" * (cells - full), style=AMBER)
    if card.get("meter_kind") == "activity-cooldown":
        return out.append("▰" * full, style=AMBER).append("▱" * (cells - full), style=MUTED)
    return out.append("▰" * full, style=AMBER if key == "protocol" else GREEN).append("▱" * (cells - full), style=MUTED)


def signal_meter_text(card: dict, width: int) -> Text:
    """One lit cell per signal; the rest of the footer is an empty track."""
    count, total = card.get("numerator"), card.get("denominator")
    label = "SIGNALS"
    if (not _number(count) or not _number(total) or total == 0
            or count > total or count != int(count) or total != int(total)):
        return Text().append(label + " ", style=MUTED).append("—", style=AMBER)
    full = int(count)
    gap = " " if full < width - len(label) else ""
    cells = max(0, width - len(label) - len(gap))
    if full > cells:
        return Text(f"{label} {full}", style=MUTED)
    return (Text().append(label + gap, style=MUTED).append("▰" * full, style=GREEN)
            .append("▱" * (cells - full), style=MUTED))


# Surf's agent rack imports meter_text while terminal loads the Surf icon helpers.
from .terminal import SurfboardTerminal, fit_prose


class SurfboardCard(HeroBoxBase, can_focus=True):
    """A focusable faceplate with an inset readout."""
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
        self._seat_error = ""
        self.set_data(None)

    @property
    def empty_seat(self):
        return self.seat_slot is not None and self.data.get("token_id") is None

    def compose(self):
        if self.seat_slot is not None:
            yield Input(placeholder="seat no", restrict=r"#?[0-9]*", max_length=11,
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
        return flatten(self.data.get("detail")) or f"{self.title} · unavailable"

    def set_data(self, data):
        self.data = dict(data) if isinstance(data, dict) else {}
        self.data.update(key=self.key, title=self.title)
        if self.seat_slot is not None:
            self.data["seat_slot"] = self.seat_slot
            self.data.setdefault("token_id", None)
        if self.key == "swarm-tokens":
            self.data["destination"] = "swarm-tokens"
            self.data.setdefault("detail", "TOKENS · production-chain markets · unavailable · Enter to open")
            self.tooltip = Text(self.detail)
        if self.key == "portfolio":
            self.data.update(status="active", primary="PORTFOLIO", secondary="wallet holdings",
                             destination="portfolio", detail="PORTFOLIO · holdings and ready claims · Enter to open")
        if self.empty_seat:
            self.data.update(status="empty", primary="", secondary="type in seat no", destination=None,
                             meter_state="empty", detail="AGENT · empty seat · Enter to type a seat number")
        else:
            self._seat_error = ""
        self.set_class(self.empty_seat, "empty")
        self.border_title = Text("⊙ " + self.title)
        self._update_meter()
        self._update_input()
        self.refresh()

    def _update_meter(self):
        if self.key == "announce":
            # Textual reserves six cells for corners, border stubs and padding.
            self.border_subtitle = signal_meter_text(self.data, max(0, self.region.width - 6))
        else:
            self.border_subtitle = meter_text(self.data, max(0, self.region.width - 6))

    def on_resize(self):
        self._update_meter()
        self._update_input()

    def render(self):
        width = max(4, self.content_size.width)
        inside = width - 2
        status = flatten(self.data.get("status")) or "unavailable"
        muted = self.empty_seat
        color = MUTED if muted else {"active": GREEN, "working": GREEN, "ready": "bright_yellow",
            "stale": AMBER, "unavailable": AMBER, "paused": AMBER,
            "offline": RED, "error": RED, "failed": RED}.get(status, AMBER)
        primary = flatten(self.data.get("primary")) or "unavailable"
        secondary = flatten(self.data.get("secondary")) or "unavailable"
        ranking = self.data.get("token_ranking") or {}
        if self.key == "swarm-tokens":
            state = ranking.get("state", "unavailable")
            if state != "ok":
                color = AMBER
                secondary = (f"{state} {hhmm(ranking.get('read_ts'))}" if state in ("partial", "stale")
                             else f"as of {hhmm(ranking['read_ts'])}" if ranking.get("read_ts") else "")
        working = secondary.removesuffix(" working").replace(",", "")
        if (self.key == "swarm" and secondary.endswith(" working")
                and working.isascii() and working.isdecimal() and working.strip("0")):
            color = GREEN
        elif self.key == "swarm" and status == "active":
            color = AMBER
        if self.seat_slot is not None:
            if status == "active":
                color = AMBER
            secondary = "offline" if status == "offline" else secondary.removesuffix(" slots")
        if self.key == "announce":
            secondary = secondary.removesuffix(" replies").removesuffix(" reply")
        elif self.key == "board":
            secondary = secondary.replace(" accepted", "")
        elif self.key == "protocol":
            secondary = secondary.removesuffix(" of supply")
        if status in ("offline", "error", "failed") and not muted:
            color = RED
        palette = self.app.get_css_variables()
        inset = Style.parse(palette["accent"] if color == GREEN else color) + Style(bgcolor=palette["background"])
        border_inset = (Style.parse(MUTED) + Style(bgcolor=palette["background"])
                        if color == AMBER else inset)
        label = ""
        native_digits = False
        rows = [("", False), (primary, not muted), (secondary, False)]
        if self.key in ("swarm", "board", "launchpad", "pool4") or self.seat_slot is not None:
            label = " SEAT " if self.seat_slot is not None else {"swarm": " AGENTS ",
                     "board": " TOP AGENT ", "launchpad": " COINS ",
                     "pool4": " IMD PRICE "}[self.key]
            count = primary.removesuffix(" online") if self.key == "swarm" else primary.removeprefix("IDMD #")
            digits = count.replace(",", "")
            if self.key == "pool4":
                digits = digits.replace(".", "", 1)
            readout = count if self.key == "pool4" else digits
            # Use the same native 3x3 renderer as Textual's Digits widget.
            native_digits = digits.isascii() and digits.isdecimal() and Digits.get_width(readout) <= inside
            if native_digits:
                rows = [(segment.text, False) for segment in Digits(readout).render(Style())
                        if segment.text != "\n"]
            else:
                rows = [("", False), (count, False), ("", False)]
        if self.empty_seat:
            label, rows = " EMPTY SEAT ", [("", False)] * 3
            secondary = self._seat_error or secondary
        preview = None
        if self.key == "protocol":
            label = " STATS "
            stats = str(self.data.get("primary") or "").splitlines()
            if len(stats) != 3:
                stats = [f"★ {name} — IMD" for name in ("burned", "rewarded", "fees")]
            fields = [flatten(line).removeprefix("★ ").split() for line in stats]
            label_width = max((cell_len(row[0]) for row in fields if len(row) == 3), default=8)
            amount_width = max((cell_len(row[1]) for row in fields if len(row) == 3), default=1)
            preview = []
            for parts in fields:
                name, amount, unit = parts if len(parts) == 3 else ("unavailable", "—", "IMD")
                row = f"{name.ljust(label_width)} {amount.ljust(amount_width)} {unit}"
                available = max(0, inside - 2)
                if cell_len(row) > available:
                    row = f"{name} {amount} {unit}"
                preview.append((Text(" " + clip(row, available) + " ", style=Style(
                    color=self.rich_style.color, bgcolor=palette["background"])), cell_len(row) > available))
        elif self.key == "announce":
            from maxpane_dashboard.widgets.surf._icons import post_preview as _post_preview
            label = " LATEST "
            ink = self.rich_style.color if status == "active" else self.get_component_rich_style("surfboard-card--muted").color
            preview = [(line, False) for line in _post_preview(primary, inside, Style(color=ink, bgcolor=palette["background"], dim=status != "active"))]
        elif self.key == "swarm-tokens":
            label = " LAST 24h "
            preview = _token_preview(ranking.get("rows"), inside,
                                     Style(color=self.rich_style.color, bgcolor=palette["background"]))
        body = Text()
        body.append("┌" + clip(label, inside).center(inside, "─") + "┐\n", style=border_inset)
        if label and (start := body.plain.find(label.strip())) >= 0:
            body.stylize(Style(bold=False), start, start + len(label.strip()))
        bottom = f" {secondary} " if label else ""
        if self.key == "protocol":
            bottom = ""
        if self.key in ("announce", "swarm-tokens") and secondary == "0 new":
            bottom = ""
        if len(bottom) > inside:
            bottom = bottom.strip()
        if self.seat_slot is not None and len(bottom) > inside:
            bottom = bottom.replace(" of ", "/")
        if self.key == "board" and len(bottom) > inside:
            bottom = bottom.replace(",", "")
            amount = bottom.removesuffix(" jobs")
            if len(bottom) > inside and amount.isascii() and amount.isdecimal():
                bottom = fmt_compact(int(amount)) + " jobs"
        if self.key == "announce" and len(bottom) > inside:
            bottom = bottom.replace(",", "")
            if len(bottom) > inside:
                bottom = bottom.replace(" new ", " ")
        clipped = len(label) > inside or len(bottom) > inside
        if self.key == "swarm-tokens":
            clipped |= _newest_token(ranking, max(0, self.region.width - 6))[1]
        for index, (raw, bold) in enumerate(rows):
            style = Style(
                color=self.rich_style.color, bgcolor=palette["background"],
                bold=bold, dim=muted)
            line, lost = (preview[index] if preview is not None else
                          (Text(raw, style=style), False) if native_digits else fit_prose(raw, inside, style=style))
            clipped |= lost
            line.align("left" if preview is not None else "center", inside)
            body.append("│", style=border_inset).append_text(line).append("│\n", style=border_inset)
        self.border_title = Text(title_with_hint("⊙ " + self.title,
            clipped, max(0, self.size.width - 4)))
        footer = Text("└" + clip(bottom, inside).center(inside, "─") + "┘",
                      style=border_inset + Style(bold=False))
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
        grid-rows: 1fr 1fr 1fr 1fr; grid-gutter: 1 1; height: 1fr; min-height: 31; min-width: 141; }
    SurfboardRack > SurfboardCard { height: 1fr; min-height: 7; padding: 0 1;
        border: round $panel; background: $surface; color: $text; content-align: center middle;
        border-title-color: $text-muted; border-subtitle-color: $text-muted; border-subtitle-align: left; }
    SurfboardRack > SurfboardCard:focus { border: round $accent; }
    SurfboardRack > #surfboard-card-protocol { padding: 0; }
    SurfboardRack > SurfboardCard.empty { color: $text-muted; }
    SurfboardCard .surfboard-card--muted { color: $text-muted; background: $background; }
    SurfboardCard > Input.seat-input { position: absolute; height: 1; margin: 0; padding: 0;
        border: none; background: $surface; color: $foreground; }
    SurfboardRack > SurfboardTerminal { column-span: 4; row-span: 3; }
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.focused_card = "announce"

    def on_resize(self):
        # Fractional tracks distribute spare lines unevenly between cards.
        rows = self.styles.grid_size_rows
        gaps = (rows - 1) * self.styles.grid_gutter_vertical
        card_height = max(7, (self.content_size.height - gaps) // rows)
        self.query(SurfboardCard).set_styles(height=card_height)
        # The terminal spans the last track and can use its leftover space.
        self.styles.grid_rows = (card_height,) * (rows - 1) + ("1fr",)

    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield SurfboardCard(*slot)
            if index == 6:
                yield SurfboardTerminal(id="surfboard-terminal")

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
