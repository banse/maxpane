"""Offline C64 house rendering spike; normal MaxPane startup is untouched.

.venv/bin/python scripts/seat_house_demo.py
F fullscreen, Z overview/close-up, Space pause, R replay, Enter terminal, Q quit.
Optional pixel graphics: --renderer tgp (see docs/seat_house_demo_plan.md).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App
from textual.containers import Container, VerticalScroll
from textual.geometry import Region
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Input, Static

from maxpane_dashboard.intro.matrix import THEME
from maxpane_dashboard.widgets.surfboard.rack import SurfboardRack
from maxpane_dashboard.widgets.surfboard.terminal import SurfboardTerminal
from scripts.seat_house_scene import RGB, W, H, base_house, camera, frame_at
from tests.surfboard_fixtures import hub_payload

BACKGROUND = '#1d1d1d'


@lru_cache(maxsize=256)
def pixel_style(top, bottom):
    return Style(color='rgb(%d,%d,%d)' % top, bgcolor='rgb(%d,%d,%d)' % bottom)


def halfblock_strips(pixels, width, height, *, rgb=RGB):
    """Center a native pixel crop; one terminal cell holds two palette pixels."""
    ph = min(len(pixels), height * 2)
    pw = min(len(pixels[0]) if ph else 0, width)
    xpad, ypad = (width - pw) // 2, (height - (ph + 1) // 2) // 2
    blank = Strip.blank(width, Style(bgcolor=BACKGROUND))
    result = [blank] * height
    for y in range(0, ph, 2):
        parts = [Segment(' ' * xpad, Style(bgcolor=BACKGROUND))]
        top, bottom = pixels[y], pixels[min(y + 1, ph - 1)]
        start = 0
        while start < pw:
            pair, end = (top[start], bottom[start]), start + 1
            while end < pw and (top[end], bottom[end]) == pair:
                end += 1
            parts.append(Segment('▀' * (end - start), pixel_style(rgb[pair[0]], rgb[pair[1]])))
            start = end
        parts.append(Segment(' ' * (width - pw - xpad), Style(bgcolor=BACKGROUND)))
        result[ypad + y // 2] = Strip(parts, width)
    return result


def solid_strips(pixels, width, height, *, rgb=RGB):
    """One source pixel per two background-painted cells: no font-shaped edges."""
    ph = min(len(pixels), height)
    pw = min(len(pixels[0]) if ph else 0, max(1, width // 2))
    xpad, ypad = max(0, (width - pw * 2) // 2), (height - ph) // 2
    blank = Strip.blank(width, Style(bgcolor=BACKGROUND))
    result = [blank] * height
    for y in range(ph):
        parts = [Segment(' ' * xpad, Style(bgcolor=BACKGROUND))]
        start = 0
        while start < pw:
            color, end = pixels[y][start], start + 1
            while end < pw and pixels[y][end] == color:
                end += 1
            parts.append(Segment(' ' * ((end - start) * 2), pixel_style(rgb[color], rgb[color])))
            start = end
        parts.append(Segment(' ' * max(0, width - pw * 2 - xpad), Style(bgcolor=BACKGROUND)))
        result[ypad + y] = Strip(parts).crop(0, width)
    return result


def overview(pixels, width, height):
    """Nearest-neighbor overview, never claim a reduced image is native resolution."""
    if width <= 0 or height <= 0:
        return []
    scale = min(1.0, width / W, height / H)
    w, h = max(1, int(W * scale)), max(1, int(H * scale))
    return [bytearray(pixels[min(H - 1, int(y / scale))][min(W - 1, int(x / scale))]
                      for x in range(w)) for y in range(h)]


def release_image(renderable, send):
    """Free only this demo's image. textual-image 0.14.2 uses the wrong selector."""
    if renderable.terminal_image_id is not None:
        send(a='d', d='I', i=renderable.terminal_image_id, q=2)
        renderable.terminal_image_id = None


@dataclass(frozen=True)
class Graphics:
    widget: type
    make_image: object
    max_cells: tuple[int, int] = (256, 256)


def load_graphics():
    # These imports probe the terminal. Run ONLY before App.run, never in paint.
    from importlib.metadata import version
    if version('textual-image') != '0.14.2':
        raise RuntimeError('graphics demo requires textual-image==0.14.2')
    from PIL import Image
    from textual_image.renderable import tgp
    from textual_image.widget import TGPImage
    from textual_image._terminal import get_cell_size
    if not tgp.query_terminal_support():
        raise RuntimeError('terminal does not advertise Kitty graphics')
    cell = get_cell_size()

    class OwnedImage(tgp.Image):
        def cleanup(self):
            release_image(self, tgp._send_tgp_message)

    class HouseImage(TGPImage, Renderable=OwnedImage):
        def on_unmount(self):
            self.image = None

    def make_image(frame, cols, rows):
        # Bound allocation on unusually large terminals. Widget has the same cap.
        width, height = cols * cell.width, rows * cell.height
        if width <= 0 or height <= 0:
            return None
        source = Image.frombytes('P', (len(frame[0]), len(frame)), b''.join(frame))
        source.putpalette([channel for color in RGB for channel in color])
        scale = min(width // source.width, height // source.height)
        if scale < 1:
            raise ValueError('terminal pixel area is smaller than the native scene')
        source = source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST)
        canvas = Image.new('P', (width, height), 16)
        canvas.putpalette([channel for color in RGB for channel in color] + [29, 29, 29])
        canvas.paste(source, ((width - source.width) // 2, (height - source.height) // 2))
        return canvas

    # Limit both placeholder coordinates and backing pixel memory (~4 MiB RGB).
    limits = min(256, 1536 // max(1, cell.width)), min(256, 1024 // max(1, cell.height))
    result = Graphics(HouseImage, make_image, limits)
    HouseImage.DEFAULT_CSS = f'HouseImage {{ max-width: {limits[0]}; max-height: {limits[1]}; }}'
    return result


def select_graphics(renderer, *, tty, loader=load_graphics):
    if renderer in ('halfblock', 'cells'):
        return None, 'half-block' if renderer == 'halfblock' else 'solid pixels'
    if not tty:
        return None, 'solid pixels · graphics needs a TTY'
    try:
        return loader(), 'Kitty graphics · native 320×200'
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        return None, f'solid-pixel fallback: {error}'


class HousePixels(Widget):
    """Cached strips: Textual owns the terminal and paints only changed rows."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rows = []

    def render_line(self, y):
        return self.rows[y] if y < len(self.rows) else Strip.blank(self.size.width, Style(bgcolor=BACKGROUND))


class HouseLayer(Container):
    def on_unmount(self):
        self.app.clear_image()


class HouseTerminal(SurfboardTerminal):
    def on_resize(self):
        self.call_after_refresh(self.app.paint)


class HouseRack(SurfboardRack):
    def compose(self):
        for widget in super().compose():
            yield HouseTerminal(id=widget.id) if isinstance(widget, SurfboardTerminal) else widget


class HouseDemo(App):
    TITLE = 'MAXPANE · C64 house rendering test'
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [('q,escape', 'quit', 'Quit'), ('f', 'fullscreen', 'Fullscreen'),
                ('z', 'zoom', 'Close-up'), ('space', 'pause', 'Pause'),
                ('r', 'replay', 'Replay'), ('enter', 'terminal', 'Terminal')]
    CSS_PATH = Path(__file__).resolve().parent.parent / 'maxpane_dashboard/themes/minimal.tcss'
    CSS = '''
    Screen { background: $background; layers: base house; }
    #demo-title { height: 1; color: $text-muted; content-align: center middle; }
    #viewport { height: 1fr; padding: 1 0; overflow: auto auto;
        scrollbar-gutter: auto; scrollbar-size: 1 1; }
    #house-layer { position: absolute; layer: house; background: #1d1d1d;
        padding: 0; border: none; overflow: hidden; align: center middle; }
    #house-pixels, #house-image { width: 100%; height: 100%; padding: 0; border: none; }
    #keys { dock: bottom; height: 1; background: $surface; color: $text-muted;
        text-wrap: nowrap; content-align: center middle; }
    '''

    def __init__(self, *, clock=monotonic, graphics=None, fullscreen=False,
                 note='solid pixels', pixel_mode='cells', closeup=True):
        super().__init__()
        self.register_theme(THEME)
        self.theme = 'matrix'
        self.clock, self.graphics, self.note = clock, graphics, note
        self.fullscreen, self.closeup, self.visible, self.paused = fullscreen, closeup, True, False
        self.pixel_mode = pixel_mode
        self.elapsed, self.last_tick = 0.0, clock()
        self.base = base_house()
        self._paint_key = None
        self.image_widget = graphics.widget(id='house-image') if graphics else None

    def compose(self):
        yield Static(Text('IMD BOARDROOM · HOUSE DEMO / SAMPLE DATA · OFFLINE'), id='demo-title')
        with VerticalScroll(id='viewport'):
            yield HouseRack(id='surfboard-rack')
        with HouseLayer(id='house-layer'):
            yield HousePixels(id='house-pixels')
            if self.image_widget is not None:
                yield self.image_widget
        yield Static(Text(), id='keys')

    def on_mount(self):
        for field in self.query(Input):
            field.disabled = True
        data = hub_payload()
        self.query_one(SurfboardRack).update_data(**data)
        self.query_one(SurfboardTerminal).update_data(**data)
        self.last_tick = self.clock()
        self.timer = self.set_interval(0.1, self.tick)
        self.call_after_refresh(self.call_after_refresh, self.paint)

    def on_resize(self):
        self.call_after_refresh(self.call_after_refresh, self.paint)

    def clear_image(self):
        if self.image_widget is not None:
            self.image_widget.image = None

    def on_unmount(self):
        self.clear_image()

    def tick(self):
        now = self.clock()
        if not self.paused and self.visible:
            self.elapsed += max(0.0, now - self.last_tick)
        self.last_tick = now
        self.paint()

    def paint(self):
        if not self.is_mounted:
            return
        layer = self.query_one('#house-layer')
        viewport = self.query_one('#viewport')
        self.query_one('#demo-title').display = not self.fullscreen
        viewport.display = not self.fullscreen
        region = (Region(0, 0, self.size.width, max(0, self.size.height - 1)) if self.fullscreen else
                  self.query_one(SurfboardTerminal).region.intersection(viewport.content_region))
        layer.display = self.visible and bool(region)
        if (layer.styles.offset.x.value, layer.styles.offset.y.value,
            layer.size.width, layer.size.height) != (region.x, region.y, region.width, region.height):
            self.clear_image()
            layer.styles.offset = region.offset
            layer.styles.width, layer.styles.height = region.width, region.height
            self.call_after_refresh(self.paint)
        image = next(iter(self.query('#house-image')), None)
        key = (int(self.elapsed * 10), region, layer.size, self.closeup, self.visible,
               image.size if image else None, self.fullscreen, self.paused)
        if self._paint_key == key:
            return
        self._paint_key = key
        frame, actor, label = frame_at(self.base, self.elapsed)
        cols, rows = layer.size
        pw, ph = (max(1, cols // 2), rows) if self.pixel_mode == 'cells' else (cols, rows * 2)
        if not self.visible:
            self.clear_image()
        elif cols and rows:
            if self.closeup:
                x, y, w, h = camera(actor, min(pw, W), min(ph, H))
                frame = [row[x:x+w] for row in frame[y:y+h]]
            use_graphics = image is not None
            if image:
                try:
                    image.image = self.graphics.make_image(
                        frame, min(cols, self.graphics.max_cells[0]), min(rows, self.graphics.max_cells[1]))
                    use_graphics = image.image is not None
                except ValueError:
                    image.image = None
                    use_graphics = False
            self.query_one('#house-pixels').display = not use_graphics
            if image:
                image.styles.position = 'absolute'
                image.styles.visibility = 'visible' if use_graphics else 'hidden'
            if not use_graphics:
                pixels = frame if self.closeup else overview(frame, pw, ph)
                widget = self.query_one(HousePixels)
                render = solid_strips if self.pixel_mode == 'cells' else halfblock_strips
                widget.rows = render(pixels, cols, rows)
                widget.refresh()
        native = (image is not None and image.image is not None) or (pw >= W and ph >= H)
        mode = 'close-up 1:1' if self.closeup else ('native 320×200' if native else 'overview · reduced')
        self.query_one('#keys', Static).update(Text(
            f'DEMO · {label} · {mode}' + (' · PAUSED' if self.paused else '') +
            ' | f full · z zoom · space pause · r replay · ↵ terminal · q quit'))
        self.query_one('#demo-title', Static).update(Text(
            f'IMD BOARDROOM · HOUSE DEMO / SAMPLE DATA · OFFLINE · {self.note}'))

    def action_fullscreen(self):
        self.clear_image()
        self.fullscreen = not self.fullscreen
        self._paint_key = None
        self.paint()
        self.call_after_refresh(self.paint)

    def action_zoom(self):
        self.closeup = not self.closeup
        self.paint()

    def action_pause(self):
        self.paused = not self.paused
        self.last_tick = self.clock()
        self.paint()

    def action_replay(self):
        self.elapsed, self.last_tick = 0.0, self.clock()
        self.paint()

    def action_terminal(self):
        self.visible = not self.visible
        self.last_tick = self.clock()
        if not self.visible:
            self.fullscreen = False
        self._paint_key = None
        self.paint()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', choices=('cells', 'halfblock', 'tgp'), default='cells')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--overview', action='store_true', help='start with the reduced whole house')
    args = parser.parse_args(argv)
    graphics, note = select_graphics(args.renderer, tty=sys.stdin.isatty() and sys.stdout.isatty())
    HouseDemo(graphics=graphics, fullscreen=args.fullscreen, note=note,
              pixel_mode='halfblock' if args.renderer == 'halfblock' else 'cells',
              closeup=not args.overview).run()


if __name__ == '__main__':
    main()
