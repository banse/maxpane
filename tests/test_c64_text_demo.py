"""The offline C64 boot screen keeps all 40×25 logical cells visible."""
import httpx
import pytest

from scripts.c64_text_demo import C64TextDemo, boot_screen


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('The C64 text demo must stay offline')
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)


async def until(pilot, predicate):
    for _ in range(30):
        await pilot.pause()
        if predicate():
            return
    assert predicate(), 'render did not settle'


def test_boot_screen_is_40_by_25_with_the_basic_startup_message():
    rows = boot_screen()
    assert len(rows) == 25 and all(len(row) == 40 for row in rows)
    assert rows[1].strip() == '**** COMMODORE 64 BASIC V2 ****'
    assert rows[3].strip() == '64K RAM SYSTEM  38911 BASIC BYTES FREE'
    assert rows[5] == 'READY.' + ' ' * 34
    assert all(not row.strip() for i, row in enumerate(rows) if i not in (1, 3, 5))


def monitor_strips(app):
    region = app.query_one('#monitor').region
    return [row.crop(region.x, region.right) for row in
            app.screen._compositor.render_strips()[region.y:region.bottom]]


@pytest.mark.parametrize('size', [(149, 45), (88, 34)])
@pytest.mark.asyncio
async def test_composited_monitor_preserves_all_1000_cells_and_blue_border(size):
    app = C64TextDemo(clock=lambda: 0)
    async with app.run_test(size=size) as pilot:
        await until(pilot, lambda: app.query_one('#monitor').region.size == (88, 33))
        painted = monitor_strips(app)
        assert len(painted) == 33 and all(row.cell_length == 88 for row in painted)
        # Read every second terminal column back as one logical C64 character.
        assert [row.text[4:84:2] for row in painted[4:29]] == list(boot_screen())
        assert all(not row.text.strip() for row in painted[:4] + painted[29:])
        for y, row in enumerate(painted):
            for x in range(88):
                color = row.crop(x, x + 1)._segments[0].style.bgcolor.get_truecolor()
                border = y < 4 or y >= 29 or x < 4 or x >= 84
                cursor = y == 10 and x in (4, 5)
                assert color == ((108, 94, 181) if border or cursor else (53, 40, 121))
        assert not app.query_one('#stage').show_vertical_scrollbar


@pytest.mark.asyncio
async def test_cursor_blinks_without_changing_text_and_reset_restarts_it():
    clock = [20.0]
    app = C64TextDemo(clock=lambda: clock[0])
    async with app.run_test(size=(149, 45)) as pilot:
        await until(pilot, lambda: app.query_one('#monitor').region.size == (88, 33))
        initial = monitor_strips(app)
        for now, expected in [(20.49, (108, 94, 181)), (20.5, (53, 40, 121)),
                              (21.0, (108, 94, 181)), (21.5, (53, 40, 121))]:
            clock[0] = now
            app.tick()
            def cursor_color():
                return monitor_strips(app)[10].crop(4, 6)._segments[0].style.bgcolor.get_truecolor()
            await until(pilot, lambda: cursor_color() == expected)
            assert [row.text for row in monitor_strips(app)] == [row.text for row in initial]
        await pilot.press('r')
        await until(pilot, lambda: cursor_color() == (108, 94, 181))
        await pilot.press('escape')
        assert not app.is_running


@pytest.mark.asyncio
async def test_resize_never_crops_the_logical_screen():
    app = C64TextDemo(clock=lambda: 0)
    async with app.run_test(size=(88, 34)) as pilot:
        for size in [(87, 34), (88, 33), (40, 25), (1, 1)]:
            await pilot.resize_terminal(*size)
            await until(pilot, lambda: not app.query_one('#monitor').display)
            strips = app.screen._compositor.render_strips()
            assert len(strips) == size[1] and all(row.cell_length == size[0] for row in strips)
            if size != (1, 1):
                assert '88×34' in '\n'.join(row.text for row in strips)
        await pilot.resize_terminal(149, 45)
        await until(pilot, lambda: app.query_one('#monitor').display)
        assert [row.text[4:84:2] for row in monitor_strips(app)[4:29]] == list(boot_screen())
