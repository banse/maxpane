"""Offline fullscreen preview: cards fade in first, then the whole terminal.

Run: .venv/bin/python scripts/matrix_boardroom_demo.py
Space pauses, R replays, Enter reveals the boardroom, Q/Escape exits.
The separate matrix_terminal_demo.py retains the terminal-only version.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual.containers import Container, VerticalScroll
from textual.widgets import Input, Static

from maxpane_dashboard.widgets.surfboard.rack import SurfboardRack
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal
from scripts.matrix_demo import DURATION, MatrixDemo
from scripts.matrix_terminal_demo import TerminalRain
from tests.surfboard_fixtures import hub_payload


class BoardroomRain(TerminalRain):
    SNAPSHOT_TARGET = '#demo-scene'
    REVEAL_START = 1.0
    REVEAL_SPACES = True

    def render(self):
        self._terminal_region = self.app.query_one(SurfboardTerminal).region
        return super().render()

    def reveal_start(self, x, y):
        return 3.0 if self._terminal_region.contains(x, y) else self.REVEAL_START


class BoardroomMatrixDemo(MatrixDemo):
    TITLE = 'BOARDROOM · Fullscreen animation demo'
    CSS_PATH = Path(__file__).resolve().parent.parent / 'maxpane_dashboard/themes/minimal.tcss'
    CSS = MatrixDemo.CSS + """
    Screen { layers: scene rain; }
    #demo-scene { width: 100%; height: 100%; layer: scene; }
    #demo-title { height: 1; color: $text-muted; content-align: center middle; }
    #viewport { height: 1fr; padding: 1 0; overflow: auto auto;
                scrollbar-gutter: auto; scrollbar-size: 1 1; }
    #rain { position: absolute; width: 100%; height: 100%; layer: rain;
            background: $background; }
    """

    def compose(self):
        with Container(id='demo-scene'):
            yield Static(Text('IMD BOARDROOM · DEMO / SAMPLE DATA · OFFLINE'), id='demo-title')
            with VerticalScroll(id='viewport'):
                yield SurfboardRack(id='surfboard-rack')
            yield Static('space pause · r replay · ↵ reveal boardroom · esc exit', id='keys')
        yield BoardroomRain(id='rain')

    def prepare(self):
        for field in self.query(Input):
            field.disabled = True
        data = hub_payload()
        self.query_one(SurfboardRack).update_data(**data)
        self.query_one(SurfboardTerminal).update_data(**data)

    def paint(self):
        rain = self.query_one(BoardroomRain)
        if self.elapsed == 0:
            rain._snapshot_size = None
        rain.display = self.elapsed < DURATION
        super().paint()


if __name__ == '__main__':
    BoardroomMatrixDemo().run()
