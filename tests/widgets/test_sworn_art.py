"""Composited Sworn images and quiet terminal-graphics ownership."""
import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.sworn.art import SwornArt
from maxpane_dashboard.terminal_graphics import probe_terminal_graphics


ART = {'hash': 'a' * 64, 'png': 'YWJj',
       'pixels': [['ff0000', '00ff00'], ['0000ff', 'ffffff']]}


class Harness(App):
    def __init__(self, *, graphics=False, sent=None):
        super().__init__()
        self.sworn_graphics = {'kitty': graphics, 'cell_width': 10, 'cell_height': 20}
        self.sent = [] if sent is None else sent
    def compose(self) -> ComposeResult:
        yield SwornArt(send=self.sent.append, id='art')


async def until(pilot, predicate):
    for _ in range(30):
        await pilot.pause()
        if predicate():
            return
    assert predicate(), 'art did not settle'


@pytest.mark.asyncio
async def test_halfblocks_show_the_whole_square_and_center_it():
    app = Harness()
    async with app.run_test(size=(12, 4)) as pilot:
        art = app.query_one(SwornArt)
        art.update_art(ART)
        await until(pilot, lambda: any('▀' in row.text for row in app.screen._compositor.render_strips()))
        strips = app.screen._compositor.render_strips()
        assert len(strips) == 4 and all(row.cell_length == 12 for row in strips)
        assert strips[0].text == '  ' + '▀' * 8 + '  '
        assert strips[0].crop(2, 3)._segments[0].style.color.get_truecolor() == (255, 0, 0)
        assert strips[-1].crop(9, 10)._segments[0].style.bgcolor.get_truecolor() == (255, 255, 255)
        assert not app.sent
        art.update_art(None)
        await until(pilot, lambda: not any('▀' in row.text for row in app.screen._compositor.render_strips()))


@pytest.mark.asyncio
async def test_tgp_uploads_once_and_deletes_only_owned_image_on_replacement_and_release():
    app = Harness(graphics=True)
    async with app.run_test(size=(12, 4)) as pilot:
        art = app.query_one(SwornArt)
        art.update_art(ART)
        await until(pilot, lambda: any('f=100' in command for command in app.sent))
        old_id = art.image_id
        assert any('U=1' in command and 'c=8,r=4' in command for command in app.sent)
        assert all('q=2' in command for command in app.sent)
        strips = app.screen._compositor.render_strips()
        assert all('\U0010eeee' in row.text for row in strips)
        count = len(app.sent)
        art.update_art(ART)
        art.render_line(0)
        await pilot.pause()
        assert len(app.sent) == count
        await pilot.resize_terminal(16, 4)
        await until(pilot, lambda: art.size.width == 16)
        assert sum('f=100' in command for command in app.sent) == 1
        await pilot.resize_terminal(16, 6)
        await until(pilot, lambda: any('c=12,r=6' in command for command in app.sent))
        assert all('p=1' in command for command in app.sent if 'U=1' in command)
        assert sum('f=100' in command for command in app.sent) == 1
        art.update_art({**ART, 'hash': 'b' * 64})
        await until(pilot, lambda: art.image_id != old_id)
        assert f'\x1b_Ga=d,d=I,i={old_id},q=2\x1b\\' in app.sent
        new_id = art.image_id
        art.release()
        assert art.image_id is None
        assert f'\x1b_Ga=d,d=I,i={new_id},q=2\x1b\\' in app.sent
        art.resume()
        await until(pilot, lambda: art.image_id is not None)
        final_id = art.image_id
    assert f'\x1b_Ga=d,d=I,i={final_id},q=2\x1b\\' in app.sent


def test_probe_does_nothing_outside_supported_real_ttys(monkeypatch):
    class NotTTY:
        def isatty(self): return False
        def write(self, text): raise AssertionError('unexpected terminal output')
    import sys
    monkeypatch.setattr(sys, '__stdin__', NotTTY())
    monkeypatch.setattr(sys, '__stdout__', NotTTY())
    monkeypatch.setenv('TERM_PROGRAM', 'ghostty')
    assert probe_terminal_graphics() == {'kitty': False, 'cell_width': 10, 'cell_height': 20}


@pytest.mark.asyncio
async def test_halfblock_uses_both_vertical_pixels_and_tolerates_empty_cached_rows():
    app = Harness()
    async with app.run_test(size=(2, 1)) as pilot:
        art = app.query_one(SwornArt)
        art.update_art(ART)
        await until(pilot, lambda: any('▀' in row.text for row in app.screen._compositor.render_strips()))
        segment = app.screen._compositor.render_strips()[0].crop(0, 1)._segments[0]
        assert segment.style.color.get_truecolor() == (255, 0, 0)
        assert segment.style.bgcolor.get_truecolor() == (0, 0, 255)
        art.update_art({**ART, 'hash': 'c' * 64, 'pixels': [[]]})
        await until(pilot, lambda: not any('▀' in row.text for row in app.screen._compositor.render_strips()))


@pytest.mark.asyncio
async def test_tgp_chunks_keep_metadata_only_in_first_chunk():
    app = Harness(graphics=True)
    png = 'AAAA' * 2300
    async with app.run_test(size=(12, 4)) as pilot:
        app.query_one(SwornArt).update_art({**ART, 'png': png})
        await until(pilot, lambda: len(app.sent) >= 4)
        chunks = [command.removeprefix('\x1b_G').removesuffix('\x1b\\').split(';')
                  for command in app.sent if ';' in command]
        assert [len(payload) for _, payload in chunks] == [4096, 4096, 1008]
        assert ''.join(payload for _, payload in chunks) == png
        assert chunks[1][0] == 'q=2,m=1'
        assert chunks[2][0] == 'q=2,m=0'


@pytest.mark.parametrize('response, expected', [
    (b'\x1b_Gi=915731;OK\x1b\\\x1b[6;24;12t\x1b[?1;2c',
     {'kitty': True, 'cell_width': 12, 'cell_height': 24}),
    (b'', {'kitty': False, 'cell_width': 10, 'cell_height': 20}),
])
def test_probe_is_bounded_and_restores_terminal(monkeypatch, response, expected):
    import sys
    import termios
    import tty
    import maxpane_dashboard.terminal_graphics as graphics

    class TTY:
        def isatty(self): return True
        def fileno(self): return 7
        def write(self, text): sent.append(text)
        def flush(self): pass

    sent, restored, timeouts = [], [], []
    monkeypatch.setenv('TERM_PROGRAM', 'ghostty')
    monkeypatch.delenv('TMUX', raising=False)
    monkeypatch.setattr(sys, '__stdin__', TTY())
    monkeypatch.setattr(sys, '__stdout__', TTY())
    monkeypatch.setattr(termios, 'tcgetattr', lambda fd: 'previous')
    monkeypatch.setattr(termios, 'tcsetattr', lambda *args: restored.append(args))
    monkeypatch.setattr(tty, 'setcbreak', lambda fd: None)
    monkeypatch.setattr(graphics.select, 'select', lambda *args: (
        timeouts.append(args[-1]) or ([7] if response else []), [], []))
    monkeypatch.setattr(graphics.os, 'read', lambda *args: response)
    assert probe_terminal_graphics(timeout=99) == expected
    assert restored == [(7, termios.TCSANOW, 'previous')]
    assert timeouts and all(0 < seconds <= 0.5 for seconds in timeouts)
    assert len(sent) == 1
