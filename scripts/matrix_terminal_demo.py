"""Offline BOARDROOM preview: Matrix rain over the entire central terminal.

Run: .venv/bin/python scripts/matrix_terminal_demo.py
Space pauses, R replays, Enter reveals the terminal, Q/Escape exits.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual._compositor import Compositor
from textual.containers import Container, VerticalScroll
from textual.widgets import Input, Static

from maxpane_dashboard.intro.matrix import reveal_frame
from maxpane_dashboard.widgets.surfboard.rack import SLOTS, SurfboardCard, SurfboardRack
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal
from scripts.matrix_demo import BACKGROUND, DURATION, GREEN, MatrixDemo, Rain, frame
from tests.surfboard_fixtures import hub_payload


class TerminalRain(Rain):
    SNAPSHOT_TARGET = SurfboardTerminal
    REVEAL_START = 2.2
    REVEAL_SPACES = False

    def reveal_start(self, x, y):
        return self.REVEAL_START

    def render(self):
        elapsed = self.app.elapsed
        rain = frame(self.size.width, self.size.height, elapsed, logo=False)
        if elapsed <= self.REVEAL_START:
            return rain
        if getattr(self, '_snapshot_size', None) != self.size:
            # Snapshot the real terminal subtree, including its border and children.
            compositor = Compositor()
            compositor.reflow(self.app.query_one(self.SNAPSHOT_TARGET), self.size)
            self._snapshot = compositor.render_strips()
            self._snapshot_size = self.size
        return reveal_frame(rain, self._snapshot, self.size.width, elapsed,
                            self.app.ansi_theme, reveal_start=self.reveal_start,
                            reveal_spaces=self.REVEAL_SPACES)


class DemoRack(SurfboardRack):
    def compose(self):
        for index, slot in enumerate(SLOTS):
            yield SurfboardCard(*slot)
            if index == 6:
                with Container(id="matrix-terminal"):
                    yield SurfboardTerminal(id="surfboard-terminal")
                    yield TerminalRain(id="rain")
        yield Static(Text("キープ"), id="surfboard-keep", classes="rack-tagline")
        yield Static(Text("ビルディング"), id="surfboard-building", classes="rack-tagline")


class TerminalMatrixDemo(MatrixDemo):
    TITLE = "BOARDROOM · Terminal animation demo"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    CSS = MatrixDemo.CSS + """
    #demo-title { height: 1; color: $text-muted; content-align: center middle; }
    #viewport { height: 1fr; padding: 1 0; overflow: auto auto;
                scrollbar-gutter: auto; scrollbar-size: 1 1; }
    #matrix-terminal { height: 1fr; min-height: 12; column-span: 4; row-span: 3;
        layers: terminal rain; }
    #matrix-terminal > SurfboardTerminal { width: 100%; height: 100%; layer: terminal; }
    #matrix-terminal > #rain { position: absolute; width: 100%; height: 100%;
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
        self.query_one(SurfboardTerminal).update_data(**data)

    def paint(self):
        rain = self.query_one(TerminalRain)
        if self.elapsed == 0:
            rain._snapshot_size = None
        rain.display = self.elapsed < DURATION
        super().paint()


if __name__ == "__main__":
    TerminalMatrixDemo().run()
