"""LOW-3: ``--poll-interval`` must reject values that break the refresh timer.

The flag used to be a bare ``type=int``, so ``0`` and negative numbers were
accepted and handed to every screen's ``set_interval``.  Neither merely polls
fast -- both break Textual's timer (reproduced against Textual 8.1.1):

* ``--poll-interval 0``: ``Timer._run``'s skip branch computes
  ``int((now - start) / _interval + 1)`` and raises ``ZeroDivisionError``.
  The timer task dies unobserved, so the dashboard silently stops refreshing
  after the initial fetch and the stored exception resurfaces as a traceback
  on exit.
* ``--poll-interval -5``: the same branch recomputes the identical count and
  ``continue``s with no ``await``, starving the asyncio event loop and
  freezing the entire TUI.

The parser is driven for real -- ``main()`` is called with a patched
``sys.argv`` -- rather than calling the type function in isolation: the bug
was that the *argument declaration* used the wrong type, and a test that
exercised the validator directly would pass even if nothing wired it up.

No Textual app is started and no network is touched: ``MaxPaneApp`` is
stubbed and ``logging.basicConfig`` neutered so a run never truncates the
user's ``~/.maxpane/maxpane.log``.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.__main__ import _MIN_POLL_INTERVAL


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, returning the app's kwargs."""
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):  # never starts a real TUI
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli, "_maximize_terminal", lambda: None)
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


# ---------------------------------------------------------------------------
# the values that used to get through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0", "-1", "-5", "-3600"])
def test_non_positive_intervals_are_rejected(monkeypatch, capsys, value) -> None:
    """Zero and negatives are refused loudly instead of freezing the TUI."""
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, ["--poll-interval", value])

    assert exc.value.code == 2, "argparse should report a usage error"
    message = capsys.readouterr().err
    assert "--poll-interval" in message
    assert str(_MIN_POLL_INTERVAL) in message, (
        f"the error should name the minimum, got: {message!r}"
    )


@pytest.mark.parametrize("value", ["1", "2", "4"])
def test_intervals_below_the_floor_are_rejected(monkeypatch, value) -> None:
    """Positive-but-hammering values are refused too.

    Every dashboard polls public, keyless endpoints; a one-second interval
    is a way to get rate-limited, not a way to see fresher data.
    """
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--poll-interval", value])


@pytest.mark.parametrize("value", ["", "abc", "1.5", "30s", "None"])
def test_non_integer_intervals_are_rejected(monkeypatch, value) -> None:
    """A non-integer must still be a usage error, not a traceback."""
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--poll-interval", value])


# ---------------------------------------------------------------------------
# the values that must still work
# ---------------------------------------------------------------------------


def test_the_floor_itself_is_accepted(monkeypatch) -> None:
    """The boundary is inclusive -- rejecting it would be a silent tightening."""
    captured = _run_cli(monkeypatch, ["--poll-interval", str(_MIN_POLL_INTERVAL)])

    assert captured["poll_interval"] == _MIN_POLL_INTERVAL
    assert captured.get("ran") is True


@pytest.mark.parametrize("value", [6, 15, 30, 120, 3600])
def test_ordinary_intervals_reach_the_app_unchanged(monkeypatch, value) -> None:
    """Validation must not clamp or rewrite a perfectly good value."""
    captured = _run_cli(monkeypatch, ["--poll-interval", str(value)])

    assert captured["poll_interval"] == value
    assert isinstance(captured["poll_interval"], int)


def test_default_interval_is_unchanged(monkeypatch) -> None:
    """No flag still means 30 seconds."""
    captured = _run_cli(monkeypatch, [])

    assert captured["poll_interval"] == 30


def test_the_floor_is_a_usable_interval() -> None:
    """The minimum must be a value the timer can actually run.

    Guards against 'fixing' the crash by picking another degenerate floor.
    """
    assert _MIN_POLL_INTERVAL > 0


def test_nothing_below_the_floor_can_reach_the_app(monkeypatch) -> None:
    """The end-to-end invariant, stated once.

    Whatever the parser accepts is what ``MaxPaneApp`` receives, and it is
    always an interval Textual's ``set_interval`` can drive.
    """
    for value in range(-3, 12):
        argv = ["--poll-interval", str(value)]
        if value < _MIN_POLL_INTERVAL:
            with pytest.raises(SystemExit):
                _run_cli(monkeypatch, argv)
        else:
            assert _run_cli(monkeypatch, argv)["poll_interval"] == value
