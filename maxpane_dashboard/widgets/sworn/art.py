"""Prepared Sworn artwork: native pixels when supported, colored blocks otherwise."""
from __future__ import annotations

from itertools import count
import re
from secrets import randbelow

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

from maxpane_dashboard.terminal_graphics import DIACRITICS


_IDS = count(1 + randbelow(1 << 23))
_BACKGROUND = Style(bgcolor='#0a0a0a')


class SwornArt(Widget):
    DEFAULT_CSS = 'SwornArt { width: 1fr; height: 1fr; overflow: hidden; background: #0a0a0a; }'

    def __init__(self, *, send=None, **kwargs):
        super().__init__(**kwargs)
        self._send_override = send
        self._art = None
        self._rows = []
        self._key = None
        self._placement = None
        self._suspended = False
        self.image_id = None

    def _send(self, command):
        if self._send_override is not None:
            self._send_override(command)
        elif self.app._driver is not None:
            self.app._driver.write(command)
            self.app._driver.flush()

    def _command(self, fields, payload=''):
        self._send('\x1b_G' + fields + (';' + payload if payload else '') + '\x1b\\')

    def _delete(self):
        if self.image_id is not None:
            self._command(f'a=d,d=I,i={self.image_id},q=2')
            self.image_id = None
        self._placement = None

    def update_art(self, art: dict | None):
        if (art or {}).get('hash') != (self._art or {}).get('hash'):
            self._delete()
            self._key = None
        self._art = art
        if self.is_mounted:
            self.call_after_refresh(self._paint)

    def release(self):
        self._suspended = True
        self._delete()
        self._rows, self._key = [], None
        self.refresh()

    def resume(self):
        self._suspended = False
        if self.is_mounted:
            self.call_after_refresh(self._paint)

    def on_mount(self):
        self.resume()

    def on_resize(self):
        self.resume()

    def on_show(self):
        self.resume()

    def on_hide(self):
        self.release()

    def on_unmount(self):
        self.release()

    def _paint(self):
        if not self.is_mounted or self._suspended or not self.screen.is_active or not self.visible:
            return
        width, height = self.size
        capability = getattr(self.app, 'sworn_graphics', None) or {}
        cw, ch = capability.get('cell_width', 10), capability.get('cell_height', 20)
        side = min(width * cw, height * ch, len(DIACRITICS) * min(cw, ch))
        cols, rows = side // cw, side // ch
        key = ((self._art or {}).get('hash'), width, height, bool(capability.get('kitty')), cw, ch)
        if key == self._key:
            return
        self._key = key
        self._rows = [Strip.blank(width, _BACKGROUND) for _ in range(height)]
        if not self._art or not cols or not rows:
            self.refresh()
            return
        xpad, ypad = (width - cols) // 2, (height - rows) // 2
        png = self._art.get('png')
        native = capability.get('kitty') and isinstance(png, str) and 0 < len(png) <= 8_000_000 and re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', png)
        if native:
            if self.image_id is None:
                self.image_id = next(_IDS) % (1 << 24) or 1
                for offset in range(0, len(png), 4096):
                    metadata = f'i={self.image_id},f=100,' if offset == 0 else ''
                    self._command(f'{metadata}q=2,m={int(offset + 4096 < len(png))}', png[offset:offset + 4096])
            if self._placement != (cols, rows):
                # One stable virtual placement: resize replaces it without re-upload.
                self._command(f'a=p,U=1,i={self.image_id},p=1,c={cols},r={rows},q=2')
                self._placement = cols, rows
            style = Style(color=f'#{self.image_id:06x}', bgcolor='#0a0a0a')
            for y in range(rows):
                chars = ''.join('\U0010eeee' + chr(DIACRITICS[y]) + chr(DIACRITICS[x]) for x in range(cols))
                self._rows[ypad + y] = Strip([Segment(' ' * xpad, _BACKGROUND), Segment(chars, style),
                    Segment(' ' * (width - xpad - cols), _BACKGROUND)], width)
        else:
            self._delete()
            pixels = self._art.get('pixels') or []
            if (not isinstance(pixels, list) or not 0 < len(pixels) <= 128
                    or not isinstance(pixels[0], list) or not 0 < len(pixels[0]) <= 128
                    or not all(isinstance(row, list) and len(row) == len(pixels[0]) for row in pixels)):
                self.refresh()
                return
            if not all(isinstance(c, str) and re.fullmatch(r'[0-9a-fA-F]{6}', c) for row in pixels for c in row):
                self.refresh()
                return
            for y in range(rows):
                parts = [Segment(' ' * xpad, _BACKGROUND)]
                for x in range(cols):
                    sx = min(len(pixels[0]) - 1, x * len(pixels[0]) // cols)
                    top = pixels[min(len(pixels) - 1, y * 2 * len(pixels) // (rows * 2))][sx]
                    bottom = pixels[min(len(pixels) - 1, (y * 2 + 1) * len(pixels) // (rows * 2))][sx]
                    parts.append(Segment('▀', Style(color='#' + top, bgcolor='#' + bottom)))
                parts.append(Segment(' ' * (width - xpad - cols), _BACKGROUND))
                self._rows[ypad + y] = Strip(parts, width)
        self.refresh()

    def render_line(self, y):
        return self._rows[y] if y < len(self._rows) else Strip.blank(self.size.width, _BACKGROUND)
