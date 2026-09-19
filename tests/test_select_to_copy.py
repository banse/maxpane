"""Select-to-copy and ``ctrl+c`` after a drag (refactor programme 2026-09, branch 0).

Textual owns the mouse, so the terminal never has a selection of its own and
Cmd+C copies nothing.  The fix routes Textual's own copy entry point
(``Screen.action_copy_text`` -> ``App.copy_to_clipboard``) through
``clipboard.copy_text`` -- native tool first, OSC 52 second -- and copies the
selection on mouse-up so the key is optional.

Zero clipboard: ``clipboard.copy_text`` is replaced by a recorder in every
test here, and ``tests/conftest.py`` refuses the real runner suite-wide.

Mutation-checked (2026-09-19):
* drop ``CopyAddressMixin.on_text_selected`` -> the drag test fails
  (recorded == [] after the release);
* ``action_copy_address`` back on ``osc52=self.copy_to_clipboard`` -> the
  recursion test fails (``copy_text`` called twice, not once).
The click test is deliberately not on that list (see its docstring).
"""

from __future__ import annotations

from textual.app import App
from textual.widgets import Static

from maxpane_dashboard import clipboard as C
from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.widgets.status_bar import StatusBar

ADDR = "0x" + "abcdef0123" * 4
LINE = "hello world selection probe"


class _App(CopyAddressMixin, App):
    COPY_MESSAGE_S = 60.0  # the message must still be there when we look

    def compose(self):
        yield Static(LINE, id="s")
        yield StatusBar()


def _recorder(monkeypatch, outcome: str = C.COPIED) -> list[str]:
    recorded: list[str] = []

    async def fake_copy(text, **kw):
        recorded.append(text)
        return outcome

    monkeypatch.setattr(C, "copy_text", fake_copy)
    return recorded


async def _drag(pilot, start: int, end: int) -> None:
    await pilot.mouse_down("#s", offset=(start, 0))
    await pilot.hover("#s", offset=(end, 0))
    await pilot.mouse_up("#s", offset=(end, 0))
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def test_releasing_a_drag_copies_the_selection(monkeypatch):
    recorded = _recorder(monkeypatch)
    app = _App()
    async with app.run_test(size=(60, 10)) as pilot:
        await _drag(pilot, 0, 10)
        assert recorded == [LINE[:10]]
        assert app.screen.query_one(StatusBar).message == "copied selection"


async def test_ctrl_c_after_a_drag_copies_the_same_way(monkeypatch):
    recorded = _recorder(monkeypatch)
    app = _App()
    async with app.run_test(size=(60, 10)) as pilot:
        await _drag(pilot, 6, 11)
        recorded.clear()
        await pilot.press("ctrl+c")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert recorded == [LINE[6:11]]


async def test_a_click_without_a_drag_copies_nothing(monkeypatch):
    """System-level guard, not a proof of the handler: Textual clears the
    selection on a same-offset mouse-up *before* it posts ``TextSelected``,
    so this stays green with ``on_text_selected`` removed.  It pins that a
    plain click -- on a ``⧉`` glyph, a feed line, anywhere -- never copies.
    """
    recorded = _recorder(monkeypatch)
    app = _App()
    async with app.run_test(size=(60, 10)) as pilot:
        await pilot.click("#s", offset=(3, 0))
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert recorded == []
        assert app.screen.query_one(StatusBar).message == ""


async def test_an_unconfirmed_selection_copy_says_so(monkeypatch):
    _recorder(monkeypatch, C.UNCONFIRMED)
    app = _App()
    async with app.run_test(size=(60, 10)) as pilot:
        await _drag(pilot, 0, 5)
        assert app.screen.query_one(StatusBar).message == C.copy_message(C.UNCONFIRMED, None)


async def test_the_icon_copy_falls_back_to_osc52_without_re_entering_the_override(monkeypatch):
    """The override must not be the OSC 52 fallback of the path it wraps.

    With no native tool, ``copy_text`` calls its ``osc52`` argument.  If that
    were the (overridden) ``copy_to_clipboard`` it would start a second
    ``copy_text`` in a worker -- one copy request, two clipboard writes and
    two status messages.
    """
    calls: list[str] = []
    real = C.copy_text

    async def counting(text, **kw):
        calls.append(text)
        return await real(text, **kw)

    monkeypatch.setattr(C, "copy_text", counting)
    monkeypatch.setattr(C, "native_commands", lambda platform=None: ())
    app = _App()
    async with app.run_test(size=(60, 10)) as pilot:
        await app.action_copy_address(ADDR)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert calls == [ADDR]
        assert app._clipboard == ADDR  # Textual's own OSC 52 writer ran once
        assert app.screen.query_one(StatusBar).message == C.copy_message(C.UNCONFIRMED, ADDR)


async def test_a_screen_without_a_status_bar_does_not_raise_on_the_selection_path(monkeypatch):
    """The wallet prompt has an ``Input`` and no ``StatusBar``; Textual's
    ``Input`` binds its own ``ctrl+c`` straight to ``app.copy_to_clipboard``.
    """
    recorded = _recorder(monkeypatch)

    class _Bare(CopyAddressMixin, App):
        pass

    app = _Bare()
    async with app.run_test() as pilot:
        app.copy_to_clipboard("0xabc")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert recorded == ["0xabc"]


def test_the_real_app_routes_textuals_copy_through_the_mixin():
    assert MaxPaneApp.copy_to_clipboard is CopyAddressMixin.copy_to_clipboard
    assert MaxPaneApp.on_text_selected is CopyAddressMixin.on_text_selected
