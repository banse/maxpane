from rich.text import Text
from textual.app import App
from textual.widgets import Static

from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.widgets import explorer as X
from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text
from tests.widgets.address_probe import CopyRecorder, LinkRecorder, icon_targets, link_targets

ADDR = "0x" + "abcdef0123" * 4


class _App(LinkRecorder, CopyRecorder, ExplorerLinkMixin, App):
    def compose(self):
        line = Text("名前 ")                         # 5 cells, 3 characters
        line.append_text(address_text(ADDR, width=17, explorer=X.BASE))
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
        assert app.opened == []


async def test_link_targets_reads_cell_positions_the_explorer_and_the_url():
    app = _App()
    async with app.run_test(size=(60, 4)) as pilot:
        await pilot.pause()
        cells = link_targets(app)
        url = X.address_url(X.BASE, ADDR)
        assert [c[0] for c in cells] == list(range(5, 5 + 17)), "cells, not characters"
        assert {c[1:] for c in cells} == {(0, "basescan", "address", ADDR, url)}
        [(ix, iy, _)] = icon_targets(app)
        assert (ix, iy) not in {(c[0], c[1]) for c in cells}, "the glyph is not a link"
        await pilot.click(offset=(cells[0][0], cells[0][1]))
        await pilot.pause()
        assert app.opened == [url]
        assert app.copied == []


async def test_link_targets_is_empty_without_an_explorer():
    class _Plain(LinkRecorder, CopyRecorder, ExplorerLinkMixin, App):
        def compose(self):
            yield Static(address_text(ADDR, width=17))

    app = _Plain()
    async with app.run_test(size=(60, 4)) as pilot:
        await pilot.pause()
        assert link_targets(app) == []
        assert len(icon_targets(app)) == 1
