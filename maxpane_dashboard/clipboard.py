"""Write-only local clipboard for the copy icon (PRD §4).

Never reads the clipboard. Native tools first: ``App.copy_to_clipboard`` writes
OSC 52, which Apple Terminal ignores, so on the owner's machine the native path
is the one that actually works. OSC 52 is the fallback (SSH), and because it
cannot confirm anything, its outcome is reported as unconfirmed.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Awaitable, Callable

from maxpane_dashboard.widgets.address import short_address

__all__ = ["COPIED", "UNCONFIRMED", "UNAVAILABLE", "OUTCOMES", "NATIVE_TIMEOUT_S",
           "copy_message", "copy_text", "native_commands"]

COPIED = "copied"
UNCONFIRMED = "unconfirmed"
UNAVAILABLE = "unavailable"
OUTCOMES = (COPIED, UNCONFIRMED, UNAVAILABLE)

#: A native tool that has not finished in this long is abandoned for the next.
NATIVE_TIMEOUT_S = 2.0

Runner = Callable[[tuple[str, ...], bytes], Awaitable[int]]


def native_commands(platform: str = sys.platform) -> tuple[tuple[str, ...], ...]:
    if platform == "darwin":
        return (("pbcopy",),)
    if platform.startswith("win"):
        return (("clip",),)
    return (("wl-copy",), ("xclip", "-selection", "clipboard"), ("xsel", "--clipboard", "--input"))


async def _run(cmd: tuple[str, ...], data: bytes) -> int:
    """Run one tool with ``data`` on stdin. No shell; an argument list only."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.communicate(data), NATIVE_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        # Reap the child: kill() only sends the signal, it does not wait for
        # the process to actually exit, and an un-reaped child left behind on
        # a long-lived process is a zombie / "subprocess is still running"
        # warning waiting to happen the next time a native tool hangs.
        await proc.wait()
        raise
    return proc.returncode if proc.returncode is not None else 1


async def copy_text(
    text: str,
    *,
    osc52: Callable[[str], None],
    runner: Runner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    platform: str = sys.platform,
) -> str:
    """Copy ``text``; return one of :data:`OUTCOMES`.

    ``runner`` defaults to ``_run`` **looked up at call time**, never bound as a
    default argument, so the suite-wide guard in ``tests/conftest.py`` cannot be
    escaped by a default captured before it was installed.
    """
    run = runner if runner is not None else _run
    data = text.encode()
    for cmd in native_commands(platform):
        if which(cmd[0]) is None:
            continue
        try:
            if await run(cmd, data) == 0:
                return COPIED
        except (OSError, asyncio.TimeoutError):
            continue
    try:
        osc52(text)
    except Exception:  # noqa: BLE001 — any driver failure is "could not copy"
        return UNAVAILABLE
    return UNCONFIRMED


def copy_message(outcome: str, address: str | None) -> str:
    """The status-bar sentence for an outcome. Plain words and validated hex only.

    ``StatusBar.set_message`` wraps its argument in markup, so nothing
    third-party may ever reach it; an address here has already passed
    ``is_address``.
    """
    if outcome == COPIED and address:
        return f"copied {short_address(address, 17)}"
    if outcome == UNCONFIRMED:
        return "sent to terminal clipboard (unconfirmed)"
    return "copy unavailable"
