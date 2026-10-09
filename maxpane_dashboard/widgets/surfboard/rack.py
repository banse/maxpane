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
from maxpane_dashboard.widgets.rowfit import clip, title_with_hint
from maxpane_dashboard.widgets.sparkline_common import build_sparkline
from .terminal import SurfboardTerminal, fitted_prose, fit_prose

GREEN = "green"
MUTED = "dim"
AMBER = "yellow"

# Layout identities, not data: future and empty bays deliberately have no route.
SLOTS = (
    ("announce", "ANNOUNCE", 0, 0), ("swarm", "SWARM", 0, 1),
    ("agent", "AGENT", 0, 2), ("board", "BOARD", 0, 3),
    ("launchpad", "LAUNCHPAD", 0, 4), ("pool4", "POOL4", 0, 5),
    ("protocol", "PROTOCOL", 1, 0), ("swarm-tokens", "SWARM TOKENS", 1, 5),
    ("portfolio", "PORTFOLIO", 2, 0), ("earnings", "EARNINGS", 2, 5),
    ("bay-11", "BAY 11", 3, 0), ("bay-12", "BAY 12", 3, 5),
)
PLANNED = frozenset(("swarm-tokens", "portfolio", "earnings"))
METER_LABELS = dict(announce="ALERT", swarm="24H", agent="PASS", board="PASS",
                    launchpad="TRADE", pool4="STAKE", protocol="BURN",
                    **{"swarm-tokens": "TOKENS", "portfolio": "ASSETS", "earnings": "EARN"})


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
    if key in PLANNED or str(key).startswith("bay-"):
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
        if self.key == "protocol" and status == "active":
            status = "experimental"
        muted = self.key in PLANNED or not self.can_focus
        color = MUTED if muted else AMBER if status in ("unavailable", "stale", "experimental") else GREEN
        primary = flatten(self.data.get("primary")) or "unavailable"
        secondary = flatten(self.data.get("secondary")) or "unavailable"
        working = secondary.removesuffix(" working").replace(",", "")
        if (self.key == "swarm" and secondary.endswith(" working")
                and working.isascii() and working.isdecimal() and working.strip("0")):
            color = GREEN
        palette = self.app.get_css_variables()
        inset = Style.parse(color) + Style(bgcolor=palette["background"])
        label = ""
        native_digits = False
        rows = [("", False), (primary, not muted), (secondary, False)]
        if self.key == "swarm":
            label = " AGENTS "
            count = primary.removesuffix(" online")
            digits = count.replace(",", "")
            # Use the same native 3x3 renderer as Textual's Digits widget.
            native_digits = digits.isascii() and digits.isdecimal() and Digits.get_width(digits) <= inside
            if native_digits:
                rows = [(segment.text, False) for segment in Digits(digits).render(Style())
                        if segment.text != "\n"]
            else:
                rows = [("", False), (count, False), ("", False)]
        body = Text()
        body.append("┌" + clip(label, inside).center(inside, "─") + "┐\n", style=inset)
        if label and (start := body.plain.find(label.strip())) >= 0:
            body.stylize("bold", start, start + len(label.strip()))
        bottom = f" {secondary} " if self.key == "swarm" else ""
        if len(bottom) > inside:
            bottom = bottom.strip()
        clipped = len(label) > inside or len(bottom) > inside
        for raw, bold in rows:
            style = Style(
                color=self.rich_style.color, bgcolor=palette["background"],
                bold=bold, dim=muted)
            line, lost = (Text(raw, style=style), False) if native_digits else fit_prose(raw, inside, style=style)
            clipped |= lost
            line.align("center", inside)
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
