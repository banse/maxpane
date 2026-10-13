"""Offline option-1 preview: ORACLES in the boardroom's LAUNCHPAD slot.

Run: .venv/bin/python scripts/surfboard_oracle_card_demo.py
Export: add --export /tmp/boardroom-oracle.svg --size 149x45
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.style import Style
from rich.text import Text
from textual.app import App
from textual.containers import VerticalScroll
from textual.renderables.digits import Digits
from textual.widgets import Input, Static

from maxpane_dashboard.screens.surfboard import SurfboardScreen
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surfboard.rack import SLOTS, SurfboardCard, SurfboardRack
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal
from scripts.surf_start_demo import parse_size
from tests.surfboard_fixtures import hub_payload


class OracleMockCard(SurfboardCard):
    def __init__(self, key, title, row, column):
        super().__init__(key, "ORACLES", row, column)

    def _update_meter(self):
        self.border_subtitle = Text("86 attested", style="dim")

    def render(self):
        inside = max(4, self.content_size.width) - 2
        background = self.app.get_css_variables()["background"]
        frame = Style(color="yellow", bgcolor=background)
        ink = Style(color=self.rich_style.color, bgcolor=background)
        result = Text("┌" + " ASSESSING ".center(inside, "─") + "┐\n", style=frame)
        for segment in Digits("7").render(Style()):
            if segment.text != "\n":
                line = Text(segment.text, style=ink)
                line.align("center", inside)
                result.append("│").append_text(line).append("│\n")
        return result.append("└" + " 100 loaded ".center(inside, "─") + "┘")


class OracleMockRack(SurfboardRack):
    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield (OracleMockCard if slot[0] == "oracles" else SurfboardCard)(*slot)
            if index == 6:
                yield SurfboardTerminal(id="surfboard-terminal")
        yield Static(Text("キープ"), id="surfboard-keep", classes="rack-tagline")
        yield Static(Text("ビルディング"), id="surfboard-building", classes="rack-tagline")


class MockManager:
    _error_count = 0

    async def fetch_hub_snapshot(self):
        return hub_payload()


class OracleMockScreen(SurfboardScreen):
    def compose(self):
        yield Static(Text(), id="surfboard-title")
        with VerticalScroll(id="surfboard-viewport"):
            yield OracleMockRack(id="surfboard-rack")
        yield StatusBar()

    def on_mount(self):
        for field in self.query(Input):
            field.disabled = True

    def _prime_status_bar(self, bar):
        bar.set_key_hints("MOCK DATA · ORACLES card option 1 · no API")

    def on_surfboard_rack_card_activated(self, event):
        event.stop()
        self.app.notify("Mock preview: this card will open ORACLES when connected.")

    def _render_chrome(self):
        self.query_one("#surfboard-title", Static).update(Text("IMD BOARDROOM · MOCK DATA"))


class OracleCardDemo(App):
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    ENABLE_COMMAND_PALETTE = False

    def __init__(self):
        super().__init__()
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def on_mount(self):
        self.push_screen(OracleMockScreen(MockManager()))

    def open_surf_mode(self, *args, **kwargs):
        self.notify("Mock preview only — no API connection.")

    def action_show_menu(self):
        self.exit()


async def export(path, size):
    async with OracleCardDemo().run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        path.write_text(pilot.app.export_screenshot(title="ORACLES CARD · MOCK DATA"))
        print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path)
    parser.add_argument("--size", type=parse_size, default=(149, 45))
    args = parser.parse_args()
    if args.export:
        asyncio.run(export(args.export, args.size))
    else:
        OracleCardDemo().run()
