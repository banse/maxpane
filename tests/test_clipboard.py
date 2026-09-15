import asyncio

import pytest

from maxpane_dashboard import clipboard as C
from maxpane_dashboard.widgets.address import short_address

ADDR = "0x" + "abcdef0123" * 4


async def test_a_native_tool_that_succeeds_is_copied_and_osc52_is_untouched():
    calls, osc = [], []

    async def runner(cmd, data):
        calls.append((cmd, data))
        return 0

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: f"/usr/bin/{name}", platform="darwin")
    assert out == C.COPIED
    assert calls == [(("pbcopy",), ADDR.encode())]
    assert osc == []


async def test_no_native_tool_falls_back_to_osc52_and_says_unconfirmed():
    osc = []

    async def runner(cmd, data):  # pragma: no cover - must not be reached
        raise AssertionError("no tool exists, so none may run")

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: None, platform="darwin")
    assert out == C.UNCONFIRMED
    assert osc == [ADDR]


async def test_linux_tries_each_tool_in_order_then_osc52():
    tried, osc = [], []

    async def runner(cmd, data):
        tried.append(cmd[0])
        if cmd[0] == "xclip":
            raise OSError("broken")
        if cmd[0] == "xsel":
            raise asyncio.TimeoutError
        return 1

    out = await C.copy_text(ADDR, osc52=osc.append, runner=runner,
                            which=lambda name: f"/usr/bin/{name}", platform="linux")
    assert tried == ["wl-copy", "xclip", "xsel"]
    assert out == C.UNCONFIRMED and osc == [ADDR]


async def test_osc52_failing_too_is_unavailable():
    def osc52(text):
        raise RuntimeError("no driver")

    out = await C.copy_text(ADDR, osc52=osc52, which=lambda name: None, platform="darwin")
    assert out == C.UNAVAILABLE


async def test_the_default_runner_is_looked_up_at_call_time(monkeypatch):
    """A default bound at definition time would let tests escape the conftest guard."""
    seen = []

    async def fake(cmd, data):
        seen.append(cmd)
        return 0

    monkeypatch.setattr(C, "_run", fake)
    out = await C.copy_text(ADDR, osc52=lambda t: None,
                            which=lambda name: "/x", platform="darwin")
    assert out == C.COPIED and seen == [("pbcopy",)]


async def test_the_suite_cannot_reach_the_real_clipboard():
    with pytest.raises(AssertionError, match="real clipboard"):
        await C._run(("pbcopy",), b"x")


async def test_a_timeout_kills_and_reaps_the_child(monkeypatch):
    """The real ``_run``: ``kill()`` alone can leave a zombie behind.

    ``monkeypatch.undo()`` lifts the autouse guard on ``C._run`` for this
    test only -- the guard fixture (``tests/conftest.py``) and this test
    share one function-scoped ``monkeypatch`` instance, so undo() removes
    exactly that one patch and nothing else's; the guard is back for every
    other test via a fresh instance next call. Never invokes a real
    clipboard tool: the command under test is ``sleep``, used only because
    it reliably outlives a shrunk timeout.
    """
    monkeypatch.undo()  # lift the autouse patch on C._run, for this test only
    monkeypatch.setattr(C, "NATIVE_TIMEOUT_S", 0.05)

    procs = []
    real_create = asyncio.create_subprocess_exec

    async def capturing_create(*args, **kwargs):
        proc = await real_create(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capturing_create)

    with pytest.raises(asyncio.TimeoutError):
        await C._run(("sleep", "5"), b"")

    assert procs and procs[0].returncode is not None, "child was killed but never reaped"


def test_the_messages_are_honest_and_contain_no_markup():
    messages = {
        C.COPIED: C.copy_message(C.COPIED, ADDR),
        C.UNCONFIRMED: C.copy_message(C.UNCONFIRMED, ADDR),
        C.UNAVAILABLE: C.copy_message(C.UNAVAILABLE, None),
    }
    assert messages[C.COPIED] == f"copied {short_address(ADDR, 17)}"
    assert messages[C.UNCONFIRMED] == "sent to terminal clipboard (unconfirmed)"
    assert messages[C.UNAVAILABLE] == "copy unavailable"
    for text in messages.values():
        assert "[" not in text and "]" not in text   # StatusBar.set_message wraps in markup
