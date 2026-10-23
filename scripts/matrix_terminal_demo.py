"""Offline BOARDROOM preview: Matrix rain inside the terminal log only.

Run: .venv/bin/python scripts/matrix_terminal_demo.py
Space pauses, R replays, Enter reveals the terminal, Q/Escape exits.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual.containers import Container, VerticalScroll
from textual.widgets import Input, RichLog, Static

from maxpane_dashboard.widgets.surfboard.rack import SLOTS, SurfboardCard, SurfboardRack
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal
from scripts.matrix_demo import DURATION, MatrixDemo, Rain, frame
from tests.surfboard_fixtures import hub_payload


class TerminalRain(Rain):
    def render(self):
        return frame(self.size.width, self.size.height, self.app.elapsed, logo=False)


class DemoTerminal(SurfboardTerminal):
    def compose(self):
        for widget in super().compose():
            if isinstance(widget, RichLog):
                with Container(id="matrix-log"):
                    yield widget
                    yield TerminalRain(id="rain")
            else:
                yield widget


class DemoRack(SurfboardRack):
    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield SurfboardCard(*slot)
            if index == 6:
                yield DemoTerminal(id="surfboard-terminal")
        yield Static(Text("キープ"), id="surfboard-keep", classes="rack-tagline")
        yield Static(Text("ビルディング"), id="surfboard-building", classes="rack-tagline")


class TerminalMatrixDemo(MatrixDemo):
    TITLE = "BOARDROOM · Terminal animation demo"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    CSS = MatrixDemo.CSS + """
    #demo-title { height: 1; color: $text-muted; content-align: center middle; }
    #viewport { height: 1fr; padding: 1 0; overflow: auto auto;
                scrollbar-gutter: auto; scrollbar-size: 1 1; }
    #matrix-log { height: 1fr; min-height: 3; layers: log rain; }
    #matrix-log > RichLog { height: 1fr; background: $background; layer: log;
        scrollbar-size-vertical: 1; scrollbar-gutter: stable; scrollbar-color: #345533; }
    #matrix-log > #rain { position: absolute; width: 100%; height: 100%;
        layer: rain; background: $background; }
    """

    def compose(self):
        yield Static(Text("IMD BOARDROOM · DEMO / SAMPLE DATA · OFFLINE"), id="demo-title")
        with VerticalScroll(id="viewport"):
            yield DemoRack(id="surfboard-rack")
        yield Static("space pause · r replay · ↵ reveal terminal · esc exit", id="keys")

    def prepare(self):
        for field in self.query(Input):
            field.disabled = True
        data = hub_payload()
        self.query_one(DemoRack).update_data(**data)
        self.query_one(DemoTerminal).update_data(**data)

    def paint(self):
        self.query_one(TerminalRain).display = self.elapsed < DURATION
        super().paint()


if __name__ == "__main__":
    TerminalMatrixDemo().run()
