"""The fixed four-row equipment rack; widgets publish navigation intent only."""
from __future__ import annotations

import math

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.containers import Grid
from textual.message import Message
from textual.renderables.digits import Digits

from maxpane_dashboard.widgets.address import is_copy_click, is_explorer_click
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import HeroBoxBase
from maxpane_dashboard.widgets.rowfit import cell_len, clip, title_with_hint
from maxpane_dashboard.widgets.sparkline_common import build_sparkline, fmt_compact
from maxpane_dashboard.widgets.surf._icons import mark_addresses, unmark, link_in_order
from .terminal import SurfboardTerminal, fitted_prose, fit_prose

GREEN = "green"
MUTED = "dim"
AMBER = "yellow"
RED = "red"

# Layout identities, not data: future and empty bays deliberately have no route.
SLOTS = (
    ("announce", "SURFBOARD", 0, 0), ("swarm", "SWARM", 0, 1),
    ("swarm-tokens", "LAUNCHES", 0, 2), ("pool4", "POOL4", 0, 3),
    ("protocol", "PROTOCOL", 0, 4), ("board", "LEADERBOARD", 0, 5),
    ("launchpad", "LAUNCHPAD", 1, 0), ("agent", "AGENT", 1, 5),
    ("portfolio", "PORTFOLIO", 2, 0), ("earnings", "EARNINGS", 2, 5),
    ("bay-11", "BAY 11", 3, 0), ("bay-12", "BAY 12", 3, 5),
)
PLANNED = frozenset(("portfolio", "earnings"))
METER_LABELS = dict(announce="ALERT", swarm="24H", agent="PASS", board="PASS",
                    launchpad="TRADE", pool4="STAKE", protocol="BURN",
                    **{"swarm-tokens": "TOKENS", "portfolio": "ASSETS", "earnings": "EARN"})


def _post_preview(value, width, style):
    """Three cell-fitted literal lines; address/copy pairs remain indivisible."""
    marked, addresses, spans = mark_addresses(flatten(value), width=max(5, width-5))
    lines, cursor = [], 0
    for index in range(3):
        remaining = marked[cursor:]
        truncated = index == 2 and cell_len(remaining) > width
        limit = max(0, width-3 if truncated else width)
        end, used = cursor, 0
        for char in remaining:
            cells = cell_len(char)
            if used + cells > limit:
                break
            end += 1
            used += cells
        for start, stop in spans:
            if start < end < stop:
                end = start
                break
        if index < 2 and end < len(marked) and marked[end:end+1] != " ":
            space = marked.rfind(" ", cursor, end)
            if space > cursor:
                end = space
        line = marked[cursor:end].rstrip() + ("..." if truncated else "")
        lines.append(Text(unmark(line), style=style))
        cursor = end
        while cursor < len(marked) and marked[cursor] == " ":
            cursor += 1
    link_in_order(lines, addresses)  # A post can mention addresses on any chain.
    return lines


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def meter_text(card: dict) -> Text:
    """An eight-cell scale; unavailable and zero denominators never imply zero."""
    key, status = card.get("key"), card.get("status")
    label = METER_LABELS.get(key, "AUX")
    out = Text().append(label + " ", style=MUTED)
    if key in PLANNED or key == "swarm-tokens" or str(key).startswith("bay-"):
        return out.append("▱" * 8, style=MUTED)
    if card.get("meter_kind") == "sparkline":
        points = card.get("points")
        if isinstance(points, list) and len(points) == 8 and all(_number(point) for point in points):
            return out.append(build_sparkline(points, width=8, pad=False), style=GREEN)
        return out.append("—", style=AMBER)
    numerator, denominator = card.get("numerator"), card.get("denominator")
    if not _number(numerator) or not _number(denominator) or denominator == 0 or numerator > denominator:
        return out.append("—", style=AMBER)
    full = int(numerator * 8 / denominator)
    return out.append("▰" * full, style=AMBER if key == "protocol" else GREEN).append("▱" * (8 - full), style=MUTED)


class SurfboardCard(HeroBoxBase, can_focus=True):
    """A focusable faceplate with an inset readout."""
    BINDINGS = [Binding("enter", "activate", "Open", show=False)]

    class Activated(Message):
        def __init__(self, card):
            super().__init__()
            self.card = card

    class Focused(Message):
        def __init__(self, card):
            super().__init__()
            self.card = card

    def __init__(self, key, title, row, column):
        super().__init__(id=f"surfboard-card-{key}", classes="empty" if key.startswith("bay-") else "populated")
        self.key, self.title, self.rack_row, self.rack_column = key, title, row, column
        self.can_focus = not key.startswith("bay-")
        self.data = {}
        self.set_data(None)

    @property
    def detail(self):
        return flatten(self.data.get("detail")) or f"{self.title} · unavailable"

    def set_data(self, data):
        planned, empty = self.key in PLANNED, self.key.startswith("bay-")
        self.data = dict(data) if isinstance(data, dict) else {}
        self.data.update(key=self.key, title=self.title)
        if self.key == "swarm-tokens":
            self.data["destination"] = "swarm-tokens"
            self.data.setdefault("detail", "TOKENS · production-chain markets · unavailable · Enter to open")
        if planned or empty:
            self.data.update(status="planned" if planned else "unassigned", primary="coming soon" if planned else "empty slot",
                             secondary="future dashboard" if planned else "· · ·", destination=None,
                             detail=f"{self.title} · planned / coming soon" if planned else f"{self.title} · empty expansion slot")
        self.border_title = Text("⊙ " + self.title)
        self.border_subtitle = meter_text(self.data)
        self.refresh()

    def render(self):
        width = max(4, self.content_size.width)
        inside = width - 2
        status = flatten(self.data.get("status")) or "unavailable"
        muted = self.key in PLANNED or not self.can_focus
        color = MUTED if muted else {"active": GREEN, "working": GREEN, "ready": "bright_yellow",
            "stale": AMBER, "unavailable": AMBER, "paused": AMBER,
            "offline": RED, "error": RED, "failed": RED}.get(status, AMBER)
        primary = flatten(self.data.get("primary")) or "unavailable"
        secondary = flatten(self.data.get("secondary")) or "unavailable"
        working = secondary.removesuffix(" working").replace(",", "")
        if (self.key == "swarm" and secondary.endswith(" working")
                and working.isascii() and working.isdecimal() and working.strip("0")):
            color = GREEN
        elif self.key == "swarm" and status == "active":
            color = AMBER
        if self.key == "agent":
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
        label = ""
        native_digits = False
        rows = [("", False), (primary, not muted), (secondary, False)]
        if self.key in ("swarm", "agent", "board", "launchpad", "protocol", "swarm-tokens", "pool4"):
            label = {"swarm": " AGENTS ", "agent": " SEAT ",
                     "board": " TOP AGENT ", "launchpad": " COINS ",
                     "protocol": " IMD BURNED ", "pool4": " IMD PRICE ",
                     "swarm-tokens": " TOKENS "}[self.key]
            count = primary.removesuffix(" online") if self.key == "swarm" else primary.removeprefix("IDMD #")
            digits = count.replace(",", "")
            if self.key == "pool4":
                digits = digits.replace(".", "", 1)
            readout = count if self.key in ("protocol", "swarm-tokens", "pool4") else digits
            # Use the same native 3x3 renderer as Textual's Digits widget.
            native_digits = digits.isascii() and digits.isdecimal() and Digits.get_width(readout) <= inside
            if native_digits:
                rows = [(segment.text, False) for segment in Digits(readout).render(Style())
                        if segment.text != "\n"]
            else:
                rows = [("", False), (count, False), ("", False)]
        preview = None
        if self.key == "announce":
            label = " LATEST POST "
            ink = self.rich_style.color if status == "active" else self.parent.query_one(".empty").rich_style.color
            preview = _post_preview(primary, inside, Style(color=ink, bgcolor=palette["background"], dim=status != "active"))
        body = Text()
        body.append("┌" + clip(label, inside).center(inside, "─") + "┐\n", style=inset)
        if label and (start := body.plain.find(label.strip())) >= 0:
            body.stylize(Style(color=self.rich_style.color, bold=True), start, start + len(label.strip()))
        bottom = f" {secondary} " if label else ""
        if len(bottom) > inside:
            bottom = bottom.strip()
        if self.key == "agent" and len(bottom) > inside:
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
        for index, (raw, bold) in enumerate(rows):
            style = Style(
                color=self.rich_style.color, bgcolor=palette["background"],
                bold=bold, dim=muted)
            line, lost = ((preview[index], False) if preview is not None else
                          (Text(raw, style=style), False) if native_digits else fit_prose(raw, inside, style=style))
            clipped |= lost
            line.align("left" if preview is not None else "center", inside)
            body.append("│", style=inset).append_text(line).append("│\n", style=inset)
        self.border_title = Text(title_with_hint("⊙ " + self.title, clipped, max(0, self.size.width - 4)))
        return body.append("└" + clip(bottom, inside).center(inside, "─") + "┘",
                           style=inset + Style(bold=False))

    def on_focus(self):
        self.post_message(self.Focused(self))

    def action_activate(self):
        if self.can_focus:
            self.post_message(self.Activated(self))

    def on_click(self, event):
        if is_copy_click(event) or is_explorer_click(event):
            return
        if self.can_focus:
            self.focus()
            self.action_activate()


class SurfboardRack(Grid):
    """Own fixed slots and terminal children; the screen dispatches to both."""
    DEFAULT_CSS = """
    SurfboardRack { layout: grid; grid-size: 6 4; grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr 1fr; grid-gutter: 1 1; height: 1fr; min-height: 31; min-width: 137; }
    SurfboardRack > SurfboardCard { height: 1fr; min-height: 7; padding: 0 1;
        border: round $panel; background: $surface; color: $text; content-align: center middle;
        border-title-color: $text-muted; border-subtitle-color: $text-muted; }
    SurfboardRack > SurfboardCard:focus { border: round $accent; }
    SurfboardRack > SurfboardCard.empty { border: dashed $panel; color: $text-muted; background: $background; }
    SurfboardRack > SurfboardTerminal { column-span: 4; row-span: 3; }
    """

    class CardActivated(Message):
        def __init__(self, key, destination, detail):
            super().__init__()
            self.key, self.destination, self.detail = key, destination, detail

    class CardFocused(Message):
        def __init__(self, key, detail):
            super().__init__()
            self.key, self.detail = key, detail

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.focused_card = "announce"

    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield SurfboardCard(*slot)
            if index == 6:
                yield SurfboardTerminal(id="surfboard-terminal")

    def update_data(self, surfboard_cards=None, surfboard_sources=None, **_kwargs):
        cards = {card["key"]: card for card in surfboard_cards if isinstance(card, dict) and isinstance(card.get("key"), str)} if isinstance(surfboard_cards, list) else {}
        for card in self.query(SurfboardCard):
            card.set_data(cards.get(card.key))
            if card.key == self.focused_card:
                self.post_message(self.CardFocused(card.key, card.detail))

    def focus_card(self, key=None):
        key = key or self.focused_card
        for card in self.query(SurfboardCard):
            if card.key == key and card.can_focus:
                self.focused_card = key
                card.focus()
                return

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
        self.post_message(self.CardFocused(event.card.key, event.card.detail))

    def on_surfboard_card_activated(self, event):
        event.stop()
        self.post_message(self.CardActivated(event.card.key, event.card.data.get("destination"), event.card.detail))
