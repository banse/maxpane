"""Standalone SURFBOARD equipment-rack design with replaceable mock records.

Run: .venv/bin/python scripts/surf_start_demo.py --rows 5
Render: add --export /tmp/surf-rack-5.svg --size 149x45
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer
from textual.events import Click
from textual.message import Message
from textual.widgets import Button, Input, RichLog, Static

from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import HeroBoxBase, PanelBase
from maxpane_dashboard.widgets.rowfit import clip


GREEN = "#a2d84a"
TEXT = "#d8ddd5"
MUTED = "#8b968b"
AMBER = "#d5a24e"


@dataclass(frozen=True)
class DashboardCard:
    """Display data only; replace these records without changing the rack."""

    key: str
    title: str
    status: str
    primary: str
    secondary: str
    meter_label: str
    meter: int


MOCK_CARDS = (
    DashboardCard("announce", "ANNOUNCE", "receiving", "12 new posts", "3 signals", "RX", 5),
    DashboardCard("swarm", "SWARM", "online", "856 online", "14 working", "BUSY", 2),
    DashboardCard("agent", "AGENT", "working", "seat #420", "95.9% accepted", "JOBS", 7),
    DashboardCard("board", "BOARD", "tracking", "829 seats", "rank #68", "FLEET", 6),
    DashboardCard("launchpad", "LAUNCHPAD", "watching", "24 coins", "3 new today", "NEW", 3),
    DashboardCard("pool4", "POOL4", "market", "$8.25 IMD", "+2.4% / 24h", "VOL", 5),
    DashboardCard("protocol", "PROTOCOL", "experimental", "4.2K burned", "18 swaps", "FLOW", 4),
    DashboardCard("swarm-tokens", "SWARM TOKENS", "planned", "coming soon", "token overview", "TOKENS", 0),
    DashboardCard("portfolio", "PORTFOLIO", "planned", "coming soon", "holdings & P/L", "ASSETS", 0),
    DashboardCard("earnings", "EARNINGS", "planned", "coming soon", "rewards & fees", "EARN", 0),
)

# Fixed demo history: no timers, connections, generated timestamps, or shell.
MOCK_EVENTS = (
    ("22:03:01", "swarm", "posted", "build a new dashboard"),
    ("22:03:02", "  ├─ 0473", "building", "workspace ready"),
    ("22:03:08", "  ├─ 0498", "reviewing", "checking the layout"),
    ("22:03:12", "  └─ 0528", "accepted", "review complete"),
    ("22:03:20", "launchpad", "detected", "new launch indexed"),
    ("22:03:26", "agent", "accepted", "seat #420 · job complete"),
    ("22:03:41", "announce", "received", "new message from surfsurf.eth"),
    ("22:03:44", "board", "updated", "seat #420 moves to rank #68"),
    ("22:04:02", "pool4", "observed", "buy · 142 IMD"),
    ("22:04:09", "protocol", "observed", "burn counter updated"),
    ("22:04:16", "swarm", "ready", "waiting for the next job"),
)


class RackCard(HeroBoxBase, can_focus=True):
    BINDINGS = [Binding("enter", "open", "Preview", show=False)]

    class Opened(Message):
        def __init__(self, card: DashboardCard) -> None:
            super().__init__()
            self.card = card

    def __init__(self, slot: int, data: DashboardCard | None) -> None:
        super().__init__(id=f"slot-{slot:02d}", classes="empty" if data is None else "populated")
        self.data = data
        self.can_focus = data is not None
        label = flatten(data.title) if data else f"BAY {slot:02d}"
        self.border_title = Text(f"⊙ {label}")
        accent = AMBER if data and data.status == "experimental" else GREEN
        level = max(0, min(8, data.meter)) if data else 0
        meter = Text(f"{flatten(data.meter_label) if data else 'AUX'} ", style=MUTED)
        meter.append("▰" * level, style=accent)
        meter.append("▱" * (8 - level), style="#657065")
        self.border_subtitle = meter

    def render(self) -> Text:
        width = max(4, self.content_size.width)
        inside = width - 2
        data = self.data
        accent = {"experimental": AMBER, "planned": MUTED}.get(data.status, GREEN) if data else MUTED
        result = Text()
        lamp = "○" if data and data.status == "planned" else "●"
        status = f"{lamp} {flatten(data.status)}" if data else "○ unassigned"
        status_text = Text(clip(status, width), style=accent if data else MUTED)
        status_text.align("center", width)
        result.append_text(status_text)
        result.append("\n")
        result.append("┌" + "─" * inside + "┐\n", style="#475047 on #101410")
        for value, style in (
            (data.primary if data else "empty slot", f"bold {TEXT}" if data else MUTED),
            (data.secondary if data else "· · ·", MUTED),
        ):
            fitted = Text(clip(flatten(value), inside), style=f"{style} on #101410")
            fitted.align("center", inside)
            result.append("│", style="#475047 on #101410")
            result.append_text(fitted)
            result.append("│\n", style="#475047 on #101410")
        result.append("└" + "─" * inside + "┘", style="#475047 on #101410")
        return result

    def action_open(self) -> None:
        if self.data is not None:
            self.post_message(self.Opened(self.data))

    def on_click(self, event: Click) -> None:
        self.action_open()


class MockTerminal(PanelBase):
    TITLE = "TERMINAL / swarm monitor"

    def compose_body(self) -> ComposeResult:
        yield Static(Text("● 856 online   ·   14 working   ·   1,271 jobs / 24h", style=GREEN), id="telemetry")
        yield RichLog(id="events", wrap=True, min_width=1, max_lines=200, markup=False)
        yield Input(placeholder="? for commands", id="command")
        yield Static(Text("MOCK STREAM    /    local preview", style=MUTED), id="terminal-foot")

    def on_mount(self) -> None:
        self.seed()

    def seed(self) -> None:
        log = self.query_one(RichLog)
        log.clear()
        for time, source, state, detail in MOCK_EVENTS:
            row = Text(f"{time}  ", style="#738471")
            row.append(f"{source:<12} ", style="#a9b8a4")
            row.append(f"{state:<10} ", style=GREEN if state in ("accepted", "ready") else "#b2c7a9")
            row.append(detail, style="#8b9d83")
            log.write(row)
        log.scroll_home(animate=False)

    def preview(self, card: DashboardCard) -> None:
        log = self.query_one(RichLog)
        log.write(Text(f"> {flatten(card.title)} preview · mock data", style=GREEN))
        log.write(Text(f"  {flatten(card.primary)} / {flatten(card.secondary)}", style=TEXT))
        log.scroll_end(animate=False)

    @on(Input.Submitted)
    def command(self, event: Input.Submitted) -> None:
        command = event.value.strip().lower()
        event.input.value = ""
        log = self.query_one(RichLog)
        if command == "clear":
            log.clear()
        elif command == "reset":
            self.seed()
        elif command in ("?", "help"):
            log.write(Text("help / clear / reset · click a card for its mock preview", style=GREEN))
        elif command:
            log.write(Text("Unknown demo command. Try help, clear, or reset.", style=AMBER))
        log.scroll_end(animate=False)


class SurfStartDemo(App):
    """Isolated design template; no production screen or manager is created."""

    TITLE = "SURFBOARD · Equipment Rack"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("4", "set_rows(4)", "4 rows", show=False),
        Binding("5", "set_rows(5)", "5 rows", show=False),
        Binding("/", "terminal", "Terminal", show=False),
        Binding("escape", "cards", "Cards", show=False),
        Binding("q", "quit", "Quit", show=False),
    ]
    CSS = """
    Screen { background: #141714; color: #d8ddd5; }
    #top { height: 2; padding: 0 2; background: #1c201c; align-vertical: middle; }
    #brand { width: 1fr; height: 1; text-style: bold; }
    #mode { width: auto; height: 1; color: #a2d84a; padding-right: 2; }
    #top Button { height: 1; min-width: 10; width: 10; border: none;
                  padding: 0; margin: 0 0 0 1; background: #303730; color: #a5b09f; }
    #top Button.active { background: #a2d84a; color: #141714; text-style: bold; }
    #viewport { height: 1fr; padding: 1 2; overflow: auto auto; scrollbar-size: 1 1; }
    #rack { grid-size: 6; grid-columns: 1fr; grid-rows: 1fr; grid-gutter: 1 2;
            width: 100%; height: 100%; min-width: 134; }
    RackCard { width: 1fr; height: 1fr; min-height: 7; border: solid #424b40;
               background: #252a24; padding: 0 1; content-align: center middle;
               border-title-color: #c1cbb9; border-title-style: bold;
               border-subtitle-align: center; }
    RackCard.empty { background: #20241f; border: solid #343d32;
                     border-title-color: #899582; }
    RackCard.populated:hover { border: solid #778969; }
    RackCard:focus { border: solid #a2d84a; border-title-color: #a2d84a;
                     background: #2a3025; }
    MockTerminal { height: 1fr; min-height: 9; padding: 0 1; border: double #53644a;
                   background: #080c09; }
    MockTerminal > .panel-title { height: 1; margin: 0 0 1 0; padding: 0;
                                  color: #a6b59e; text-style: bold; }
    #telemetry { height: 2; border-bottom: solid #263323; text-wrap: nowrap; }
    #events { height: 1fr; min-height: 2; background: #080c09; padding: 0;
              scrollbar-size: 1 1; scrollbar-color: #3c5133; scrollbar-background: #080c09; }
    #command { height: 3; padding: 0 1; border: round #304929; background: #080c09;
               color: #a2d84a; }
    #command:focus { border: round #779753; }
    #terminal-foot { height: 1; color: #84927d; }
    #footer { height: 1; padding: 0 2; color: #a0ad96; background: #1c201c; }
    """

    def __init__(self, rows: int = 5, cards: tuple[DashboardCard, ...] = MOCK_CARDS) -> None:
        if rows not in (4, 5):
            raise ValueError("rows must be 4 or 5")
        if len(cards) > 12:
            raise ValueError("the switchable demo has room for at most 12 populated cards")
        super().__init__()
        self.rows = rows
        self.cards = cards

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static(Text("SURFBOARD  /  equipment rack"), id="brand")
            yield Static(Text("MOCK DATA"), id="mode")
            yield Button("4 rows", id="four")
            yield Button("5 rows", id="five")
        with ScrollableContainer(id="viewport"):
            yield self.make_rack()
        yield Static(Text("tab select   enter preview   / terminal   4/5 layout   q quit"), id="footer")

    def make_rack(self) -> Grid:
        widgets = []
        full_row_slots = (self.rows - 3) * 6
        for slot in range(1, full_row_slots + 7):
            data = self.cards[slot - 1] if slot <= len(self.cards) else None
            widgets.append(RackCard(slot, data))
            if slot == full_row_slots + 1:
                terminal = MockTerminal(id="terminal")
                terminal.styles.column_span = 4
                terminal.styles.row_span = 3
                widgets.append(terminal)
        rack = Grid(*widgets, id="rack")
        rack.styles.grid_size_rows = self.rows
        rack.styles.min_height = self.rows * 7 + self.rows - 1
        return rack

    def on_mount(self) -> None:
        self.update_buttons()
        self.action_cards()

    def update_buttons(self) -> None:
        self.query_one("#four").set_class(self.rows == 4, "active")
        self.query_one("#five").set_class(self.rows == 5, "active")

    async def action_set_rows(self, rows: int) -> None:
        if rows == self.rows:
            return
        self.rows = rows
        await self.query_one("#rack").remove()
        await self.query_one("#viewport").mount(self.make_rack())
        self.update_buttons()
        self.action_cards()

    @on(Button.Pressed)
    async def choose_variant(self, event: Button.Pressed) -> None:
        await self.action_set_rows(4 if event.button.id == "four" else 5)

    @on(RackCard.Opened)
    def preview_card(self, event: RackCard.Opened) -> None:
        self.query_one(MockTerminal).preview(event.card)

    def action_terminal(self) -> None:
        self.query_one(Input).focus()

    def action_cards(self) -> None:
        for card in self.query(RackCard):
            if card.data is not None:
                card.focus()
                break


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x"))
        if width < 1 or height < 1:
            raise ValueError
        return width, height
    except ValueError as error:
        raise argparse.ArgumentTypeError("size must be positive WIDTHxHEIGHT") from error


async def export_demo(app: SurfStartDemo, path: Path, size: tuple[int, int]) -> None:
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(app.export_screenshot(title=f"SURFBOARD / {app.rows} rows / mock data"))
        print(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, choices=(4, 5), default=5)
    parser.add_argument("--export", type=Path, help="export an SVG preview instead of launching")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    app = SurfStartDemo(rows=args.rows)
    if args.export:
        asyncio.run(export_demo(app, args.export, args.size))
    else:
        app.run()


if __name__ == "__main__":
    main()
