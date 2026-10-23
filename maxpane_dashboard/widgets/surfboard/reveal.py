"""A temporary paint layer over the real terminal; no data access or timer."""
from rich.text import Text
from textual._compositor import Compositor
from textual.strip import Strip
from textual.widgets import Static

from maxpane_dashboard.intro.matrix import frame, reveal_frame


class TerminalReveal(Static):
    can_focus = False
    DEFAULT_CSS = """
    TerminalReveal {
        position: absolute; layer: terminal-reveal;
        background: $background; padding: 0; border: none;
        overflow: hidden; text-wrap: nowrap;
    }
    """

    def __init__(self):
        super().__init__()
        self.display = False
        self.elapsed = 0.0
        self.target = None
        self.crop = None
        self._snapshot = Compositor()

    def align_to(self, terminal, viewport):
        self.target = terminal
        region = terminal.region.intersection(viewport.content_region)
        self.crop = region - terminal.region.offset
        self.styles.offset = region.offset
        self.styles.width = region.width
        self.styles.height = region.height

    def render(self):
        if self.target is None or not self.crop:
            return Text()
        size = self.target.region.size
        rain = frame(size.width, size.height, self.elapsed, logo=False)
        if self.elapsed > 2.2:
            self._snapshot.reflow(self.target, size)
            # Read current widget strips each frame; never reveal an old data snapshot.
            rain = reveal_frame(rain, self._snapshot.render_strips(), size.width,
                                self.elapsed, self.app.ansi_theme)
        rows = rain.split('\n')
        visible = []
        for row in rows[self.crop.y:self.crop.bottom]:
            # Crop terminal cells, not string offsets (wide CJK and emoji).
            strip = Strip(row.render(self.app.console)).crop(self.crop.x, self.crop.right)
            visible.append(Text.assemble(*((part.text, part.style) for part in strip)))
        return Text('\n').join(visible)

    def on_mouse_down(self, event):
        # No hidden link/action activation. A click reveals and focuses the prompt.
        event.stop()
        self.screen.action_command_input()
