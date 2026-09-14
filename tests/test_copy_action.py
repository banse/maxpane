from textual.app import App

from maxpane_dashboard import clipboard as C
from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.widgets.status_bar import StatusBar

ADDR = "0x" + "abcdef0123" * 4


class _App(CopyAddressMixin, App):
    COPY_MESSAGE_S = 0.05

    def compose(self):
        yield StatusBar()


class _BareApp(CopyAddressMixin, App):
    COPY_MESSAGE_S = 0.05


async def test_a_copy_posts_the_outcome_and_clears_it(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test() as pilot:
        await app.run_action(f"copy_address('{ADDR}')")
        bar = app.screen.query_one(StatusBar)
        assert bar.message == C.copy_message(C.COPIED, ADDR)
        await pilot.pause(0.2)
        assert bar.message == ""


async def test_the_clear_never_erases_a_newer_message(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test() as pilot:
        await app.run_action(f"copy_address('{ADDR}')")
        bar = app.screen.query_one(StatusBar)
        bar.set_message("fetching ENS …")
        await pilot.pause(0.2)
        assert bar.message == "fetching ENS …"


async def test_an_invalid_address_never_reaches_the_clipboard(monkeypatch):
    called = []

    async def fake_copy(text, **kw):  # pragma: no cover - must not run
        called.append(text)
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _App()
    async with app.run_test():
        await app.action_copy_address(ADDR + "\n")
        assert called == []
        assert app.screen.query_one(StatusBar).message == "copy unavailable"


async def test_a_screen_without_a_status_bar_does_not_raise(monkeypatch):
    async def fake_copy(text, **kw):
        return C.COPIED

    monkeypatch.setattr(C, "copy_text", fake_copy)
    app = _BareApp()
    async with app.run_test():
        await app.action_copy_address(ADDR)


def test_the_real_app_carries_the_action():
    assert issubclass(MaxPaneApp, CopyAddressMixin)
