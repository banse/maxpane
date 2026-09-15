from rich.text import Text
from textual.app import App
from textual.widgets import Static

from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text
from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4


class _App(CopyRecorder, App):
    def compose(self):
        line = Text("名前 ")                         # 5 cells, 3 characters
        line.append_text(address_text(ADDR, width=17))
        yield Static(line)


async def test_icon_targets_reads_cell_positions_and_the_copied_address():
    app = _App()
    async with app.run_test(size=(60, 4)) as pilot:
        await pilot.pause()
        [(x, y, target)] = icon_targets(app)
        assert target == ADDR
        assert x == 5 + 17 + 1                       # cells, not characters
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]
