"""The argv recorder every broker test injects for ``subprocess.run`` (contract §E "Argv recorder")."""
from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence


class RecordingRunner:
    """Records every ``(argv, kwargs)``; answers from a script keyed by an argv prefix.

    ``script`` maps a tuple prefix of argv to either a ``CompletedProcess``, a ``(rc, stdout)`` pair,
    an exception instance to raise, or a callable ``(argv, kwargs) -> CompletedProcess``. The longest
    matching prefix wins; an unmatched argv returns rc 0 with empty output.
    """

    def __init__(self, script: dict[tuple[str, ...], object] | None = None) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.script: dict[tuple[str, ...], object] = dict(script or {})

    def __call__(self, argv: Sequence[str], **kw) -> subprocess.CompletedProcess:
        argv = list(argv)
        self.calls.append((argv, kw))
        best: tuple[str, ...] | None = None
        for prefix in self.script:
            if tuple(argv[:len(prefix)]) == prefix and (best is None or len(prefix) > len(best)):
                best = prefix
        if best is None:
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        answer = self.script[best]
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer) and not isinstance(answer, subprocess.CompletedProcess):
            return answer(argv, kw)
        if isinstance(answer, tuple):
            rc, out = answer
            return subprocess.CompletedProcess(argv, rc, out if isinstance(out, bytes) else str(out).encode(), b"")
        return answer

    def argvs(self, *prefix: str) -> list[list[str]]:
        return [argv for argv, _ in self.calls if tuple(argv[:len(prefix)]) == prefix]


def timeout_for(argv: Sequence[str], seconds: float) -> Callable:
    """A script entry that raises ``TimeoutExpired`` for *argv*."""
    def raise_timeout(_argv, _kw):
        raise subprocess.TimeoutExpired(list(argv), seconds, output=b"partial", stderr=b"")
    return raise_timeout
